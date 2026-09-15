"""[U10 2026-09-15] 구조 픽 — 승패에 값이 없을 때 **파생으로 옮긴다.**

🔴 **페이블 픽의 절반이 여기다.** 시장이 승패를 정확히 매겨 놓았어도 핸디·
   언더오버에는 값이 남아 있는 경우가 많다. 지금까지 그 길이 통째로 없었다.

🔴 `analyze.py:157` 은 `blk["derived"]` 를 **읽는데 만드는 곳이 0건**이었다.
   그래서 구조 후보가 나와도 전건 반려됐다. 이 모듈이 그 생산자다.

⚠️ 순수 함수다. DB·HTTP 를 부르지 않는다(`gate.py`·`hypothesis.py` 와 같은 규칙).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)
# 🔴 [U13] 값은 `config/rules.yaml` 이 원본이다. 여기에 숫자를 **다시
#    적지 마라** — 두 곳에 적으면 사본이 되고, 사본은 원본이 바뀔 때
#    따라가지 않는다(실사고 2026-09-02 워치독 오탐 4건).
from app.engine import rules as _R


#: 채택 문턱(%p). 우리 확률 − 시장 확률이 이만큼은 돼야 후보다.
EDGE_MIN_PP = _R.get("structure.edge_min_pp")

#: 구조 등급. 지시문 3-3.
GRADE_HIGH_PP = _R.get("structure.grade_high_pp")

#: 약팀 핸디는 이 범위만 본다. +2.5 이상은 경기 성격이 달라진다.
AH_LINES = tuple(_R.get("structure.ah_lines"))


@dataclass(frozen=True)
class Pick:
    market: str          # spreads | totals
    side: str
    line: float | None
    p_ours: float
    p_market: float
    edge_pp: float
    reason: str

    @property
    def key(self) -> str:
        return f"{self.market}:{self.side}:{self.line}"


def derived_probs(rows: list | None) -> dict:
    """파생 시장 행 → `{(market, line): {side: 확률}}`. 마진을 뺀다.

    🔴 **양쪽이 다 있을 때만** 만든다. 한쪽만으로 디빅하면 마진이 안 빠져
       확률이 부푼다(`market_edge` 와 같은 규칙).
    """
    from app.engine.market_edge import implied_probs

    buckets: dict = {}
    for r in rows or []:
        mk = (r.get("market") or "").lower()
        if mk not in ("spreads", "totals"):
            continue
        line = r.get("line")
        # 🔴 핸디는 **양쪽 라인이 반대 부호**다(U2 가 그렇게 저장한다:
        #    홈 −0.5 / 원정 +0.5). 부호를 그대로 키로 쓰면 한 핸디가 두
        #    버킷으로 갈려 "한쪽만 있다"로 버려진다(실측: 전건 유실).
        #    절대값으로 묶고, 각 행의 원래 라인은 side 와 함께 들고 있는다.
        key = (mk, abs(float(line)) if line is not None else None)
        buckets.setdefault(key, {})[str(r.get("side"))] = {
            "odds": r.get("odds"), "line": line}
    out = {}
    for key, sides in buckets.items():
        if len(sides) < 2:
            continue                       # 한쪽만 있다 — 만들지 않는다
        names = sorted(sides)
        q = implied_probs({"home": sides[names[0]]["odds"],
                           "away": sides[names[1]]["odds"]})
        if not q:
            continue
        out[key] = {names[0]: {"p": q.get("home"), "line": sides[names[0]]["line"]},
                    names[1]: {"p": q.get("away"), "line": sides[names[1]]["line"]}}
    return out


def _edge(p_ours, p_market) -> float | None:
    """우리 − 시장 (%p). 🔴 부호를 뒤집으면 손해 보는 쪽을 고른다."""
    if p_ours is None or p_market is None:
        return None
    return round((float(p_ours) - float(p_market)) * 100, 2)


def candidates(*, p_code: float | None, derived: dict | None,
               home: str, away: str, draw_p: float | None = None) -> list:
    """구조 픽 후보. `edge >= 6%p` 만 남기고 **상관 픽은 하나**로 줄인다.

    `p_code` 는 홈 승 확률이다. 약팀(=낮은 쪽) 핸디는 그 반대다.
    """
    if p_code is None or not derived:
        return []
    ph = float(p_code)
    pa = max(0.0, 1.0 - ph - float(draw_p or 0.0))
    out: list[Pick] = []
    for (market, _abs_line), sides in (derived or {}).items():
        for side, box in sides.items():
            p_mkt, line = box.get("p"), box.get("line")
            if market == "spreads":
                if line is None or abs(float(line)) not in AH_LINES:
                    continue
                # 🔴 핸디 확률은 승패 확률이 아니다. 라인만큼 보정한다.
                from app.engine.odds_move import line_to_pp

                shift = (line_to_pp(float(line)) or 0.0) / 100.0
                base = ph if side == home else pa
                p_ours = max(0.0, min(1.0, base - shift))
                why = f"{side} {line:+.1f} — 우리 {p_ours*100:.1f}%"
            elif market == "totals":
                # ⚠️ 득점 환경 모델이 없다. 시장을 그대로 쓰면 edge 가 0 이다 —
                #    **후보로 만들지 않는다**(지어내지 않는다).
                continue
            else:
                continue
            e = _edge(p_ours, p_mkt)
            if e is None or e < EDGE_MIN_PP:
                continue
            out.append(Pick(market, side, line, p_ours, float(p_mkt), e, why))
    return _one_per_direction(out)


def _one_per_direction(picks: list) -> list:
    """🔴 **상관 픽은 하나만.** 같은 팀의 여러 라인을 다 내면 한 경기에 여러 번
    베팅하는 것이다. 팀별로 edge 가 가장 큰 하나만 남긴다."""
    best: dict = {}
    for p in picks:
        cur = best.get(p.side)
        if cur is None or p.edge_pp > cur.edge_pp:
            best[p.side] = p
    return sorted(best.values(), key=lambda p: -p.edge_pp)


def grade(edge_pp: float | None) -> str | None:
    """구조 등급. edge >= 8 상 · >= 6 중 · 그 미만은 **후보가 아니다**."""
    from app.engine.confidence import HIGH, MID

    if edge_pp is None:
        return None
    e = float(edge_pp)
    if e >= GRADE_HIGH_PP:
        return HIGH
    return MID if e >= EDGE_MIN_PP else None


def attach_derived(blk: dict, rows: list | None, *, home: str = "",
                   away: str = "") -> dict:
    """[U10 항목 2] 파생 디빅을 `blk["derived"]` 에 **붙인다.**

    🔴 `analyze.py:157-160` 이 이 키를 읽어 구조 후보를 대조한다. 종전에는
       **읽기만 하고 만드는 곳이 0건**이라 후보가 전건 반려됐다:
         "구조_후보가 파생 디빅에 없는 시장이다: …"
    ⚠️ 모양은 analyze 가 쓰는 대로다 — `[{"시장", "라인", "쪽", "확률"}]`.
       없으면 **빈 목록**이다(키를 없애지 않는다 — 없는 것과 안 본 것은 다르다).
    """
    out = []
    for (market, _abs_line), sides in (derived_probs(rows) or {}).items():
        for side, box in sides.items():
            out.append({"시장": market, "라인": box.get("line"),
                        "쪽": side, "확률": box.get("p")})
    blk = dict(blk or {})
    blk["derived"] = sorted(out, key=lambda d: (d["시장"], str(d["쪽"])))
    return blk
