"""[STD-1 2026-09-17] 팀 성적표 — **우리 DB 의 종료 경기로 만든다.**

사용자 목표 분석(2026-09-17)의 첫 축이 이것이다:
  "팀 축: 격차 극대. KIA .544(4위 …) vs 키움 .352(최하위, **3연패**)"

🔴 **새 소스가 없다.** `games(status='final')` 만 쓴다 — 실측 보유량
   mlb 496 · kbo 259 · npb 195 · soccer 121.
   그걸로 뽑으면 KIA .551(3위) · 키움 .373(9위) 로 사장님 값과 가깝다.

⚠️ **"시즌 순위"가 아니다.** 우리 DB 는 KBO 를 2026-06-28 부터만 갖고 있다
   (시즌은 3월 시작). 그래서 **"보유 구간 성적"** 이고, 그렇게 밝혀 적는다 —
   없는 것을 있다고 쓰면 그게 곧 거짓 재료다(절대 규칙 6).

🔴 **순수 함수다.** DB·HTTP 를 부르지 않는다(`report.py` 와 같은 규약) —
   그래야 표본 0 에서도 골격이 나오고 테스트가 DB 없이 돈다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 최근 폼 창. 야구 관례.
RECENT_N = 10


def _score(row, key):
    try:
        v = row[key]
    except (KeyError, IndexError, TypeError):
        v = row.get(key) if hasattr(row, "get") else None
    return None if v is None else int(v)


def table(rows: list | None) -> dict:
    """종료 경기 목록 → `{팀: {gp, win, loss, draw, pct, rank, streak, last10}}`.

    행 모양: `{"home","away","home_score","away_score"}` (오래된 순).

    🔴 **무승부는 승률에서 뺀다**(야구 관례 승/(승+패)). KBO·NPB 는 무가 있다.
    🔴 **점수가 없는 경기는 안 센다** — 진행 중·취소를 세면 성적이 거짓이 된다.
    🔴 경기가 없으면 **빈 표**다. 0 으로 채우지 않는다(0.000 과 "모름"은 다르다).
    """
    box: dict[str, dict] = {}
    seq: dict[str, list] = {}
    for r in rows or []:
        hs, as_ = _score(r, "home_score"), _score(r, "away_score")
        home = str((r["home"] if not hasattr(r, "get") else r.get("home")) or "")
        away = str((r["away"] if not hasattr(r, "get") else r.get("away")) or "")
        if hs is None or as_ is None or not home or not away:
            continue
        for team, mine, yours in ((home, hs, as_), (away, as_, hs)):
            b = box.setdefault(team, {"gp": 0, "win": 0, "loss": 0, "draw": 0})
            b["gp"] += 1
            if mine > yours:
                b["win"] += 1
                seq.setdefault(team, []).append("W")
            elif mine < yours:
                b["loss"] += 1
                seq.setdefault(team, []).append("L")
            else:
                b["draw"] += 1
                seq.setdefault(team, []).append("D")

    for team, b in box.items():
        decided = b["win"] + b["loss"]
        b["pct"] = round(b["win"] / decided, 3) if decided else None
        s = seq.get(team) or []
        b["last10"] = "".join(s[-RECENT_N:])
        b["streak"] = _streak(s)
    for i, team in enumerate(sorted(box, key=lambda t: (
            box[t]["pct"] is None, -(box[t]["pct"] or 0.0))), 1):
        box[team]["rank"] = i
    return box


def _streak(seq: list) -> str | None:
    """`"3연패"`·`"2연승"`. 무승부에서 끊고, 없으면 None(지어내지 않는다)."""
    if not seq:
        return None
    last = seq[-1]
    if last == "D":
        return None
    n = 0
    for x in reversed(seq):
        if x != last:
            break
        n += 1
    return f"{n}{'연승' if last == 'W' else '연패'}"


def line_of(st: dict | None, team: str) -> str | None:
    """`"KIA 27승22패1무 · 승률 0.551 · 3위 · 2연승 · 최근10 WWLWL…"`.

    🔴 없으면 **None** — 빈 줄을 만들지 않는다.
    """
    b = (st or {}).get(team)
    if not isinstance(b, dict) or not b.get("gp"):
        return None
    # 🔴 **모양을 믿지 않는다.** 칸이 없으면 그 조각을 빼고 쓴다 — ANL-8 에서
    #    `구조_후보` 항목을 dict 라고 믿었다가 운영에서 터진 것과 같은 자리다.
    w, ls, d = b.get("win"), b.get("loss"), b.get("draw")
    head = team
    if w is not None and ls is not None:
        head += f" {w}승{ls}패" + (f"{d}무" if d else "")
    bits = [head]
    if b.get("pct") is not None:
        bits.append(f"승률 {b['pct']}")
    if b.get("rank"):
        bits.append(f"{b['rank']}위")
    if b.get("streak"):
        bits.append(b["streak"])
    if b.get("last10"):
        bits.append(f"최근{len(b['last10'])} {b['last10']}")
    return " · ".join(bits)
