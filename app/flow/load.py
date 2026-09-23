"""[LOAD-1] 부하 — 일정(연전)과 출전을 **주전/후보로 무게를 나눠** 센다.

사용자 2026-09-23: "출전부하도 배선에 넣어라...그리고 이것은 **후배선수인지
메인선수인지 확인해서 숫자를 바꿔야 한다**"

🔴 **왜 무게를 나누나.** 후보 선수가 다섯 경기 나온 것과 3번 타자가 다섯 경기
   나온 것은 같은 부하가 아니다. 승패에 걸리는 무게가 다르다.

🔴 **주전 판정을 여기서 짓지 않는다.** 원본은 `lineup_diff.usual_from` 이고
   최근 10경기 중 **절반 이상 나온 선수**를 `regulars`, 최빈 타순을 `slots`
   로 준다. `flow/direction.py` 가 이미 그것을 쓴다 — 사본을 만들지 않는다.

⚠️ **축구는 넣지 않았다.** `lineup_history.minutes` 가 전 리그 **0건**이고
   날짜가 2026-08-22~08-29 8일치뿐이다(9월 0경기). 잴 자료가 없다.

⚠️ 가중치·창은 전부 **미검증 사전값**이다. `config/rules.yaml` 이 원본이고
   BT-9 백테스트가 그 값을 재는 것이 목적이다.
⚠️ 순수 함수다 — DB·HTTP·LLM 0건. 계약이 잠근다.
"""
from __future__ import annotations

import datetime as dt
import logging

from app.flow import rules as R

logger = logging.getLogger(__name__)


def _canon(name: str) -> str:
    """표기 흔들림 흡수. 🔴 `lineup_diff.canon_name` 이 원본이다."""
    from app.engine.lineup_diff import canon_name

    return canon_name(str(name or ""))


def player_weight(name: str, usual: dict) -> float:
    """그 선수 한 경기 출장의 **무게**. 모르면 **0.0**.

    🔴 무게는 두 가지에서 나온다 — 둘 다 `usual_from` 이 준 **사실**이다:
         주전인가(`regulars`)      · 평소 타순이 위인가(`slots`)
    ⚠️ 평소 타순을 모르면 **0** 이다. 지어내지 않는다 — 그래야 자료가 얇은
       선수가 부하를 부풀리지 않는다.
    """
    if not name or not isinstance(usual, dict):
        return 0.0
    slots = usual.get("slots") or {}
    key = _canon(name)
    slot = slots.get(key)
    if slot is None:
        return 0.0
    base = float(R.get("load.weight_regular", 1.0)
                 if key in (usual.get("regulars") or set())
                 else R.get("load.weight_sub", 0.4))
    # 타순 가중: 1번이 가장 무겁고 9번이 가장 가볍다. 폭은 config 가 준다.
    top = float(R.get("load.slot_top_bonus", 0.5))
    try:
        s = max(1, min(9, int(slot)))
    except (TypeError, ValueError):
        return 0.0
    return round(base * (1.0 + top * (9 - s) / 8.0), 4)


def _aware(v):
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=dt.UTC)
    if isinstance(v, str) and v.strip():
        try:
            t = dt.datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return t if t.tzinfo else t.replace(tzinfo=dt.UTC)
    return None


def play_load(apps, usual: dict, *, today=None, at=None, window_d=None) -> dict | None:
    """창 안의 출장을 **무게를 실어** 합산. 🔴 자료가 없으면 **None**.

    `apps`  `[{batter, slot, starts_at}]` — `batter_appearances ⋈ games`
    `today` **오늘 선발 명단**(이름들). 주면 그 선수들의 부하만 센다.
    반환 `{"score", "n", "top": [이름…], "scoped": bool}`.

    🔴 [2026-09-23 사용자 지시] **"그날 경기에 그 선수가 선발이냐도 예측에
       적용되어야 한다."** 많이 뛴 선수가 오늘 안 나오면 그 피로는 오늘
       경기에 들어오지 않는다 — 그건 `lineup_out` 이 보는 다른 사실이다.
       `today` 를 주면 **오늘 나오는 선수의 누적 부하**만 센다.
    ⚠️ `today` 가 없으면(타순 미확정) 종전대로 전부 센다 — 그때는
       `scoped=False` 로 남겨 **덜 정확하다는 사실**이 보이게 한다.

    ⚠️ **None 과 0 은 다르다.** None 은 "못 봤다"(⑤가 `미실행` 으로 적는다),
       0 은 "봤는데 없다"다.
    """
    if not apps:
        return None
    days = float(window_d if window_d is not None else R.get("load.window_d", 7))
    now = _aware(at) or max((_aware(a.get("starts_at")) for a in apps
                             if _aware(a.get("starts_at"))), default=None)
    if now is None:
        return None
    lo = now - dt.timedelta(days=days)
    want = {_canon(x) for x in (today or []) if x} or None
    score, n, who = 0.0, 0, []
    for a in apps:
        t = _aware(a.get("starts_at"))
        if t is None or not (lo <= t <= now):
            continue
        name = a.get("batter")
        if want is not None and _canon(name) not in want:
            continue          # 오늘 안 나오는 선수의 피로는 오늘 경기에 없다
        w = player_weight(name, usual)
        if w <= 0:
            continue
        score += w
        n += 1
        who.append(str(name))
    return {"score": round(score, 3), "n": n,
            "top": sorted(set(who))[:4], "scoped": want is not None}
