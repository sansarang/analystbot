"""🔴🔴 **선수 가치 v2 — 박스 기록**(사용자 결정 2026-10-13 저녁 · 1번).

> fotmob `playerStats`(`before_as_of`)로 선수별 **90분당 xG+xA**(공격), 출전 분
> 가중 · 시간 감쇠 · 출전 **< 450분**은 리그·포지션 평균으로 수축.
> 수비수·GK 는 일단 **출전 분 비중만**(후속 과제). 안정성: 시즌 반분 상관
> — **0.3 이상**이어야 다음 단계.

🔴 왜 ± 를 버렸나 — 구간 ±(`player_pm`)는 실측에서 **반분 상관 +0.06~+0.09** 였고
   시즌 교차가 *"거의 전부 수축하라"* 고 했다(λ 3200·12800 뒤 평평). 300~400경기
   표본에서 11명 공선형을 풀 수 없다. 박스 기록은 **그 선수가 직접 만든 것**이라
   팀 효과가 덜 섞이고 표본이 선수마다 **분으로** 쌓인다.
🔴 **PB1** 누설 — `as_of` 이후 경기는 안 본다(문은 `fotmob.before_as_of` 하나).
🔴 **PB2** 조용한 0 금지 — 안 뛴 선수는 **칸이 없다**. ⚠️ 다만 **xG 를 잰 경기**에서
   기록이 없는 선수는 그 경기 xG 가 **진짜 0** 이다(그 둘을 가른다).
🔴 **PB3** 수비수·GK 의 수는 **공격 기여가 아니다** — `kind` 가 *"출전 분"* 이라고
   적는다. ⚠️ 수비 가치는 **후속 과제**다(지어내지 않는다).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: 🔴 이 분 미만이면 리그·포지션 평균 쪽으로 수축한다(사용자 결정 §1)
MIN_MINUTES = 450

#: 🔴 수축 가중의 K — `분/(분+K)`
SHRINK_K = 450.0

#: 🔴 한 경기 길이(분)
FULL = 90

#: 🔴 뒷선 — 지금은 **출전 분 비중만** 센다(후속 과제)
BACK = ("GK", "DF")


@dataclass
class Table:
    """🔴 선수 가치 v2 한 판 — 수와 **그 수가 무엇인지**(`kind`)를 함께 든다."""

    value: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)
    minutes: dict = field(default_factory=dict)
    pos: dict = field(default_factory=dict)
    kind: dict = field(default_factory=dict)
    mean: float = 0.0
    as_of: object = None
    n_matches: int = 0
    shrunk: int = 0
    why: str = ""


def measured(match: dict) -> bool:
    """🔴 그 경기에서 **xG 를 쟀나** — 한 선수라도 수가 있으면 잰 경기다."""
    for one in dict(dict(match or {}).get("pstat") or {}).values():
        if "expected_goals" in dict(one) or "expected_assists" in dict(one):
            return True
    return False


def fit(matches: list[dict], *, as_of, half_life: float = 365.0) -> Table:
    """🔴🔴 선수 가치 v2 — `(90분당 xG+xA | 출전 분 비중)`. **`as_of` 이전만**(PB1).

    공격(MF·FW): `Σ w·(xg+xa) / Σ w·분 × 90` — `w = exp(−ξ·경과일)`.
    뒷선(GK·DF): `Σ w·분 / Σ w·90` (출전 분 비중 · 0~1) — **공격 기여가 아니다**.
    """
    from datetime import datetime

    from app.collect import fotmob as fm
    said = fm.before_as_of(list(matches or []), as_of=as_of, key="utc")
    got = Table(as_of=as_of, n_matches=len(said))
    if not said:
        return Table(as_of=as_of, why="🔴 **적합 못 했다** — 경기가 없다")
    decay = math.log(2.0) / max(1.0, float(half_life))
    num: dict[str, float] = {}
    den: dict[str, float] = {}
    mins: dict[str, float] = {}
    pos: dict[str, str] = {}
    blind = 0
    for m in said:
        when = datetime.fromisoformat(str(m["utc"]).replace("Z", "+00:00"))
        if when.tzinfo is None:                     # 🔴 절대규칙 2
            continue
        w = math.exp(-decay * max(0, (as_of.date() - when.date()).days))
        pos.update({str(k): str(v) for k, v in
                    dict(m.get("pos") or {}).items() if v})
        said_xg = measured(m)
        if not said_xg:
            blind += 1
        for pid, one in dict(m.get("pstat") or {}).items():
            box = dict(one)
            played = float(box.get("minutes_played") or 0.0)
            if played <= 0:
                continue                 # 🔴 **PB2** — 안 뛴 선수는 칸이 없다
            key = str(pid)
            mins[key] = mins.get(key, 0.0) + played
            back = str(pos.get(key, "")).upper() in BACK
            if back:
                num[key] = num.get(key, 0.0) + w * played
                den[key] = den.get(key, 0.0) + w * FULL
                continue
            if not said_xg:
                # 🔴 xG 를 **안 잰** 경기다 — 그 경기는 공격 가치에 **안 쓴다**
                continue
            val = (float(box.get("expected_goals") or 0.0)
                   + float(box.get("expected_assists") or 0.0))
            num[key] = num.get(key, 0.0) + w * val
            den[key] = den.get(key, 0.0) + w * played / FULL
    for key, top in num.items():
        bottom = den.get(key, 0.0)
        if bottom <= 0:
            continue
        got.raw[key] = top / bottom
    got.minutes = {k: v for k, v in mins.items() if k in got.raw}
    got.pos = {k: v for k, v in pos.items() if k in got.raw}
    got.kind = {k: ("출전 분" if str(got.pos.get(k, "")).upper() in BACK
                    else "공격") for k in got.raw}
    if not got.raw:
        return Table(as_of=as_of, why="🔴 **적합 못 했다** — 쓸 기록이 없다")
    got.mean = sum(got.raw.values()) / len(got.raw)
    # 🔴 수축은 `player_pm.shrink` 하나다(사본 금지) — 뒷선과 공격을 **따로** 센다
    from app.core.ratings import player_pm as _pm
    out: dict[str, float] = {}
    notes: list[str] = []
    for want in ("공격", "출전 분"):
        pick = {k: v for k, v in got.raw.items() if got.kind[k] == want}
        if not pick:
            continue
        said_v, why = _pm.shrink(
            pick, minutes={k: got.minutes[k] for k in pick},
            pos={k: got.pos.get(k, "") for k in pick},
            floor=MIN_MINUTES, k=SHRINK_K)
        out.update(said_v)
        notes.append(f"{want} {len(pick)}명 · {why}")
    got.value = out
    got.shrunk = sum(1 for k in got.raw
                     if got.minutes.get(k, 0.0) < MIN_MINUTES)
    got.why = ("선수 가치 v2(90분당 xG+xA · 반감기 "
               f"{half_life:g}일 · 경기 {len(said)}건 · 선수 {len(got.raw)}명) · "
               + " · ".join(notes)
               + (f" · 🔴 **xG 를 안 잰 경기 {blind}건**은 공격 가치에서 "
                  f"**뺐다**(출전 분은 센다)" if blind else "")
               + " · ⚠️ 뒷선(GK·DF)은 **출전 분 비중**이다 — 수비 가치는 "
                 "**후속 과제**다(지어내지 않는다)")
    return got
