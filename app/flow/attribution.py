"""[MOV-C 4·5단계] **배당이 왜 움직였는지 시각으로 맞춘다.**

사용자 2026-09-23: "왜 이렇게 배당이 이동되었는지…초기 가설과 접목" ·
**"이유 미상은 없다"**

🔴 **"이유 미상"을 만들지 않는다.** 모든 이동에 분류가 붙는다:
```
정보(news)   창 안에 관측된 변화·기사가 있다        → 그 근거를 적는다
자금(money)  찾아봤는데 없다                        → 자금 이동이다. 회피가 아닌 답
```
⚠️ **"자금"이라 말하려면 실제로 찾아봤어야 한다.** MOV-T7 커밋이 그 자백을
   남겼다 — `"{pp}%p 이동 — 뉴스 근거 없음(**딥서치 미실행** 또는 무소득)"`.
   찾지 않고 자금이라 부르면 `none` 에 이름만 바꾼 것이다. 그래서 이 모듈은
   **관측이 실제로 있었는지**(`observed`)를 함께 낸다 — 관측이 없으면
   `money` 라고 말하지 않고 `unobserved` 다.

🔴 **중요도·방향 판단을 하지 않는다.** `diff.go` 와 같은 규약이다
   ("크롤러가 임의 가중치를 만들면 측정되지 않은 튜닝이 된다"). 여기서는
   "무엇이 언제 있었다"를 이동에 붙이기만 하고, 그것이 유리한지는 ⑦이 정한다.

⚠️ **순수 함수다** — DB·HTTP·LLM 0건. 계약이 잠근다.
"""
from __future__ import annotations

import datetime as dt
import logging

from app.flow import rules as R

logger = logging.getLogger(__name__)

#: 원인이 붙지 않은 이동의 분류.
MONEY = "money"           # 관측은 있었는데 창 안에 아무것도 없었다
UNOBSERVED = "unobserved"  # 관측 자체가 없었다 — 자금이라 부를 수 없다
NEWS = "news"


def _to_dt(v):
    """`at` · `captured_at` → aware datetime. 못 읽으면 None(지어내지 않는다)."""
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=dt.UTC)
    if not isinstance(v, str) or not v.strip():
        return None
    try:
        t = dt.datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.UTC)


def _is_noise(c: dict) -> bool:
    """볼 가치가 없는 변화인가.

    🔴 목록의 원본은 `config/rules.yaml` 이다 — 이름을 여기 적지 않는다.
    ⚠️ 실측 2026-09-23: 크롤러 변화 154건 중 **83건이 `status`**(9회초→9회말)
       였다. 회 진행은 이동의 원인이 아니라 경기 중계다.
    ⚠️ `확정 → 미상` 같은 역행은 파싱이 깨진 것이지 사건이 아니다.
    """
    field = str(c.get("field") or "")
    if field in {str(x) for x in (R.get("move.ignore_fields") or [])}:
        return True
    pair = f"{c.get('from') or ''}→{c.get('to') or ''}"
    return pair in {str(x) for x in (R.get("move.ignore_transitions") or [])}


def _when(c: dict):
    """그 변화가 **실제로 일어난** 시각.

    🔴 기사는 크롤 시각(`at`)이 아니라 **발행시각**이 맞다. `news.go` 가
       값에 `<RFC3339>|<제목>` 으로 실어 보낸다.
    """
    to = str(c.get("to") or "")
    if "|" in to:
        t = _to_dt(to.split("|", 1)[0])
        if t is not None:
            return t
    return _to_dt(c.get("at"))


def _label(c: dict) -> str:
    """사람이 읽을 한 줄. 값이 길면 자른다."""
    field = str(c.get("field") or "?")
    to = str(c.get("to") or "")
    if "|" in to:
        to = to.split("|", 1)[1]
    frm = str(c.get("from") or "")
    if frm and not to:
        return f"{field} 사라짐: {frm[:60]}"
    if frm:
        return f"{field}: {frm[:30]} → {to[:40]}"
    return f"{field}: {to[:60]}"


def explain(points, changes, *, window_min=None, min_pp=None) -> dict:
    """이동 구간마다 원인을 붙인다.

    `points`  `[(시각, 홈확률)]` — `n02_market._sets` 가 낸 것, 오래된 것부터
    `changes` `[{at, field, from, to, game}]` — `crawler_feed.load_changes`

    반환 `{"moves": [...], "observed": bool, "unexplained_pp": float}`.
    각 move 는 `{from_p, to_p, pp, at, kind, causes: [라벨]}`.
    """
    win = dt.timedelta(minutes=float(
        window_min if window_min is not None else R.get("move.window_min", 30)))
    floor = float(min_pp if min_pp is not None else R.get("move.min_pp", 1.0))

    seq = []
    for ts, p in (points or []):
        t = _to_dt(ts)
        if t is None:
            continue
        try:
            seq.append((t, float(p)))
        except (TypeError, ValueError):
            continue
    seq.sort(key=lambda x: x[0])

    cand = []
    for c in (changes or []):
        if not isinstance(c, dict) or _is_noise(c):
            continue
        t = _when(c)
        if t is not None:
            cand.append((t, c))
    observed = bool(cand)

    moves, unexplained = [], 0.0
    for i in range(len(seq) - 1):
        t0, p0 = seq[i]
        t1, p1 = seq[i + 1]
        pp = round((p1 - p0) * 100, 2)
        if abs(pp) < floor:
            continue
        hits = [_label(c) for t, c in cand if t0 - win <= t <= t1 + win]
        # 🔴 **`none` 을 만들지 않는다.** 관측이 있었는데 못 찾았으면 자금이고,
        #    관측 자체가 없었으면 자금이라 부를 수 없다(찾아보지 않았으므로).
        kind = NEWS if hits else (MONEY if observed else UNOBSERVED)
        if not hits:
            unexplained += abs(pp)
        moves.append({"from_p": round(p0, 4), "to_p": round(p1, 4), "pp": pp,
                      "at": t1.isoformat(), "kind": kind, "causes": hits[:4]})
    return {"moves": moves, "observed": observed,
            "unexplained_pp": round(unexplained, 2)}


def summary(bag: dict) -> str:
    """한 줄 요약. 🔴 이동이 없으면 **빈 문자열** — 없는 말을 만들지 않는다."""
    moves = (bag or {}).get("moves") or []
    if not moves:
        return ""
    n = {NEWS: 0, MONEY: 0, UNOBSERVED: 0}
    for m in moves:
        n[m.get("kind", UNOBSERVED)] = n.get(m.get("kind", UNOBSERVED), 0) + 1
    parts = []
    if n[NEWS]:
        parts.append(f"근거 있음 {n[NEWS]}")
    if n[MONEY]:
        parts.append(f"자금 {n[MONEY]}")
    if n[UNOBSERVED]:
        parts.append(f"관측 없음 {n[UNOBSERVED]}")
    return f"이동 {len(moves)}구간 — " + " · ".join(parts)
