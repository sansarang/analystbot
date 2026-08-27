"""[§9] 카드 → 마켓 매핑. **승패 말고 언더오버·핸디캡까지 카드로 답한다.**

다섯 칸은 "누가 이기나"만 답한다. 총득점과 점수차는 다른 질문이고, 다른 재료를
쓴다 — 그래서 6번째 칸(득점 환경)과 칸 격차를 각각의 근거로 삼는다.

⚠️ **시장 배당은 라인 확인용이지 확률 근거가 아니다.** 어떤 라인이 걸려 있는지
   알아야 "그 라인 대비 위인가 아래인가"를 말할 수 있을 뿐이고, 시장 확률을
   우리 확률로 쓰지 않는다(#38·#39, 시장 배제).

⚠️ **기준 총득점은 모델이 아니라 카드의 산술이다.** 양 팀 최근 3경기 회당 득점의
   합이며, 그렇게 표시한다. λ를 되살리는 것이 아니다 — 되살릴 거면 카드를
   만들 이유가 없었다.
"""
from __future__ import annotations

import logging

from app.engine.card import CELLS, SCORING_CELL

logger = logging.getLogger(__name__)

# [핸디캡] 칸 격차 → 어떤 핸디를 볼 만한가.
#   ⚠️ 사용자가 정한 운용 규칙이지 실측이 아니다. `cell_ledger`에 칸별 적중률이
#      쌓이면 "몇 칸 차이에서 -1.5가 실제로 맞는가"로 교체한다.
HANDICAP_DOMINANT = 5      # 이만큼 가져가면 -1.5를 검토
HANDICAP_CLOSE = 1         # 이 이하면 +1.5 / 더블찬스


# 리그 기준 총득점을 낼 최소 표본. 이하면 **라인 비교를 아예 하지 않는다.**
MIN_TOTAL_SAMPLE = 30


def expected_total(scoring_metrics: dict) -> float | None:
    """카드 기준 총득점 — 양 팀 최근 3경기 회당 득점의 합(파크팩터 보정).

    ⚠️ **라인 비교에 쓰지 마라.** 3경기 표본은 총득점 기준으로 쓰기엔 너무
       흔들린다 — 실측 2026-08-27 KBO 5경기에서 5.86~14.43이 나왔고, 같은 날
       실제 리그 중앙값은 9였다(37경기). 이 값으로 라인을 고르면 판정이 표본
       잡음을 따라간다.
       라인 비교의 기준은 `league_total_baseline`(실측 중앙값)이다.
       이 함수는 **참고 표시용**으로만 남긴다.
    """
    base = (scoring_metrics or {}).get("runs_per_game_both")
    if base is None:
        return None
    pf = (scoring_metrics or {}).get("park_factor")
    return round(base * pf, 2) if pf else round(base, 2)


async def league_total_baseline(pool, sport: str, days: int = 120) -> dict:
    """그 리그의 **실측 총득점 중앙값**. 라인 비교의 유일한 기준이다.

    반환 {"median", "n"} — 표본 미달이면 {"median": None, "n": n}.

    ⚠️ 중앙값이다. 평균은 난타전 한 경기에 끌려간다(실측: 중앙값 9 · 평균 10.89).
    ⚠️ 표본이 얇으면 **아무 값도 돌려주지 않는다.** 얇은 기준으로 라인을 고르면
       그 기준의 오차가 그대로 판정 오차가 된다.
    """
    if pool is None:
        return {"median": None, "n": 0}
    rows = await pool.fetch(
        """SELECT (home_score + away_score) AS t FROM games
           WHERE sport = $1 AND status = 'final'
             AND home_score IS NOT NULL AND away_score IS NOT NULL
             AND starts_at > now() - make_interval(days => $2)""",
        sport, int(days))
    vals = sorted(r["t"] for r in rows)
    if len(vals) < MIN_TOTAL_SAMPLE:
        return {"median": None, "n": len(vals)}
    mid = len(vals) // 2
    med = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
    return {"median": float(med), "n": len(vals)}


def totals_call(level: str | None, lines: list[float],
                baseline: dict | None = None) -> dict:
    """언더오버 판정. 반환 {"side", "line", "basis", "note"} — 없으면 빈 dict.

    규칙은 하나다 — **판정과 라인이 같은 방향을 가리킬 때만** 부른다.
      다득점 예상 = 리그 평소보다 많이 난다  → 중앙값 **이하** 라인에 오버
      저득점 예상 = 리그 평소보다 적게 난다  → 중앙값 **이상** 라인에 언더
    '보통'이거나 맞는 라인이 없으면 부르지 않는다. 억지로 고르지 않는다.

    ⚠️ 기준은 **실측 리그 중앙값**이다. 3경기 표본(`expected_total`)을 쓰면
       판정이 표본 잡음을 따라간다(실측 2026-08-27).
    ⚠️ 표본 미달이면 아무 판정도 하지 않는다.
    """
    ref = (baseline or {}).get("median")
    if level not in ("다득점 예상", "저득점 예상") or ref is None:
        return {}
    n = (baseline or {}).get("n") or 0
    side_only = "오버" if level == "다득점 예상" else "언더"
    if not lines:
        # 🔴 **시장 라인이 없으면 라인을 고르지 않는다.** 방향만 말한다.
        #   실측 2026-08-27: KBO는 배당을 수집하지 않아 시장 라인이 0건이고,
        #   남은 후보는 λ가 만든 것인데 그 λ가 실제보다 총득점을 높게 본다
        #   (리그 실측 중앙값 9 vs λ 라인 중앙 10.5~11.5).
        #   틀린 라인에 판정을 붙이면 그 라인이 근거처럼 읽힌다.
        return {"side": side_only, "line": None, "basis": [SCORING_CELL[0]],
                "note": (f"{level} — 리그 실측 중앙값 {ref:g}점({n}경기)보다 "
                         f"{'많이' if side_only == '오버' else '적게'} 날 경기 "
                         f"(시장 라인 미수집이라 라인은 고르지 않음)")}
    if level == "다득점 예상":
        cand = [x for x in lines if x <= ref]
        side, pick = "오버", max(cand) if cand else None
    else:
        cand = [x for x in lines if x >= ref]
        side, pick = "언더", min(cand) if cand else None
    if pick is None:
        return {}
    return {"side": side, "line": pick,
            "basis": [SCORING_CELL[0]],
            "note": (f"리그 실측 중앙값 {ref:g}점({n}경기) 대비 "
                     f"라인 {pick:g} — {level}이므로 {side}")}


def handicap_call(counts: dict, favored: str | None) -> dict:
    """핸디캡 판정. 승패 카드의 **칸 격차**로만 정한다.

    반환 {"side", "line", "basis", "note"} — 볼 만한 자리가 없으면 빈 dict.
    """
    if favored not in ("home", "away") or not counts:
        return {}
    won = counts.get(favored, 0)
    lost = counts.get("away" if favored == "home" else "home", 0)
    basis = [k for k, _ in CELLS]
    if won >= HANDICAP_DOMINANT:
        return {"side": favored, "line": -1.5, "basis": basis,
                "note": f"{won}칸 대 {lost}칸 압도 — 큰 점수차 핸디 검토"}
    if won <= HANDICAP_CLOSE:
        return {"side": favored, "line": +1.5, "basis": basis,
                "note": f"{won}칸 대 {lost}칸 — 접전, 받는 핸디/더블찬스"}
    return {"side": favored, "line": None, "basis": basis,
            "note": f"{won}칸 대 {lost}칸 — 승패 단식까지만"}


def market_calls(jg: dict) -> list[dict]:
    """이 경기의 카드 기반 마켓 판정 목록. **근거 칸을 반드시 달아 돌려준다.**

    ⚠️ 재료가 없으면 그 마켓을 만들지 않는다. 빈 판정을 '보통'으로 채우면
       판정한 것처럼 보인다.
    """
    out = []
    cmp_ = jg.get("compare") or {}
    hc = handicap_call(cmp_.get("counts") or {}, cmp_.get("favored"))
    if hc:
        name = jg.get(f"{hc['side']}_kr") or jg.get(hc["side"])
        desc = (f"{name} 승" if hc["line"] is None
                else f"{name} 핸디 {hc['line']:+g}")
        out.append({"market": "handicap", "desc": desc, "basis": hc["basis"],
                    "note": hc["note"]})
    sc = jg.get("scoring") or {}
    # ⚠️ **시장 라인만 쓴다.** market_board의 라인은 λ가 만든 후보이지 시장이
    #   건 라인이 아니다. 우리 모델이 만든 라인에 우리 판정을 붙이는 것은
    #   비교가 아니라 자기확인이다.
    lines = sorted({m["line"] for m in (jg.get("alt_markets") or [])
                    if isinstance(m, dict) and m.get("market") == "totals"
                    and m.get("line") is not None})
    tc = totals_call(sc.get("level"), lines, jg.get("total_baseline"))
    if tc:
        desc = (f"{tc['side']} {tc['line']:g}" if tc["line"] is not None
                else f"{tc['side']} 쪽")
        out.append({"market": "totals", "desc": desc,
                    "basis": tc["basis"], "note": tc["note"]})
    return out


_LABELS = dict(CELLS) | {SCORING_CELL[0]: SCORING_CELL[1]}


def render_market_calls(jg: dict) -> list[str]:
    """마켓 판정 줄. **근거 칸을 함께 쓴다** — 어느 칸이 이 판정을 만들었는지."""
    calls = market_calls(jg)
    if not calls:
        return []
    lines = ["🎯 카드 기반 마켓"]
    for c in calls:
        basis = ", ".join(_LABELS.get(k, k) for k in c["basis"][:3])
        lines.append(f"  {c['desc']} — {c['note']} [근거: {basis}]")
    return lines
