"""[§3] 라인 무브먼트 — **검증 지표로만** 쓴다.

검증된 사실: 마감 배당이 개장 배당보다 예측 정확도가 높다(시장이 정보를 흡수한다).
그러나 "움직임은 맥락이지 전략이 아니다" — 라인이 움직였다는 사실 자체가 픽의 근거가
될 수는 없다. 그래서:

- 확률 계산(λ·포아송)에는 **절대 넣지 않는다.**
- 우리 모델 방향과 시장 이동 방향이 **일치하면 신뢰도 +1단계**,
  **역행하면 -1단계 + "시장이 반대로 움직임 — 우리가 모르는 정보 가능성" 경고**.

역행이 경고인 이유: 시장은 라인업·부상·기상까지 흡수한 가격이다. 우리만 반대를 보는데
이유를 못 대면, 우리가 못 본 정보가 가격에 이미 들어있다고 보는 쪽이 안전하다.
"""

import logging

import asyncpg

logger = logging.getLogger(__name__)

MIN_MOVE = 0.02          # 이만큼 미만은 노이즈로 본다 (배당 환산 확률 2%p)
CONF_ORDER = ["low", "medium", "high"]


async def opening_and_current(pool: asyncpg.Pool, game_id: int, market: str,
                              side: str, line: float | None = None) -> tuple[float, float] | None:
    """(개장 배당, 현재 배당). 스냅샷이 2개 미만이면 None."""
    rows = await pool.fetch(
        """
        SELECT odds, captured_at FROM odds_snapshots
        WHERE game_id = $1 AND market = $2 AND side = $3
          AND ($4::numeric IS NULL OR line = $4)
        ORDER BY captured_at
        """,
        game_id, market, side, line,
    )
    if len(rows) < 2:
        return None
    return float(rows[0]["odds"]), float(rows[-1]["odds"])


def move_direction(opening: float, current: float) -> tuple[str, float]:
    """배당 이동을 확률 변화로 환산.

    배당이 내려가면(1.90 → 1.75) 그 사이드로 돈이 몰린 것 = 시장 확률 상승.
    반환: ("toward" | "away" | "flat", 확률 변화폭)
    """
    p_open, p_now = 1.0 / opening, 1.0 / current
    delta = p_now - p_open
    if abs(delta) < MIN_MOVE:
        return "flat", round(delta, 4)
    return ("toward" if delta > 0 else "away"), round(delta, 4)


def agreement(model_side_favored: bool, direction: str) -> str:
    """모델 방향과 시장 이동의 일치 여부.

    model_side_favored: 우리 모델이 이 사이드를 우세로 보는가.
    반환: "agree" | "diverge" | "neutral"
    """
    if direction == "flat":
        return "neutral"
    moved_toward = direction == "toward"
    return "agree" if moved_toward == model_side_favored else "diverge"


def adjust_confidence(confidence: str | None, verdict: str) -> tuple[str, str | None]:
    """[§3] 신뢰도 ±1단계. 확률은 건드리지 않는다.

    반환: (조정된 신뢰도, 경고 문구 또는 None)
    """
    conf = confidence if confidence in CONF_ORDER else "medium"
    idx = CONF_ORDER.index(conf)
    if verdict == "agree":
        return CONF_ORDER[min(len(CONF_ORDER) - 1, idx + 1)], None
    if verdict == "diverge":
        return (CONF_ORDER[max(0, idx - 1)],
                "시장이 반대로 움직임 — 우리가 모르는 정보 가능성")
    return conf, None


def describe(opening: float, current: float, delta: float, verdict: str) -> str:
    """상세 데이터에 찍을 한 줄."""
    arrow = "↓" if current < opening else ("↑" if current > opening else "→")
    label = {"agree": "모델과 같은 방향", "diverge": "모델과 반대 방향",
             "neutral": "유의미한 이동 없음"}[verdict]
    return (f"라인 이동 {opening:.2f} {arrow} {current:.2f} "
            f"(시장 확률 {delta:+.1%}) — {label}")


async def attach_line_move(pool: asyncpg.Pool, jg: dict) -> dict | None:
    """경기의 대표 마켓에 대해 라인 이동을 계산하고 신뢰도를 조정한다.

    확률에는 반영하지 않는다 — jg["p_final"] 계열을 건드리지 않는 것이 계약이다.
    """
    from app.engine.markets import best_market

    top = best_market(jg.get("market_board") or [])
    if not top or not top.get("odds") or top.get("p") is None:
        return None
    pair = await opening_and_current(
        pool, jg["game_id"], top["market"], top["side"], top.get("line"))
    if pair is None:
        return None

    opening, current = pair
    direction, delta = move_direction(opening, current)
    verdict = agreement(top["p"] >= 0.5, direction)
    before = jg.get("judge_confidence", "medium")
    after, warning = adjust_confidence(before, verdict)

    info = {
        "market": top["market"], "side": top["side"], "desc": top["desc"],
        "opening": opening, "current": current, "delta": delta,
        "direction": direction, "verdict": verdict,
        "confidence_before": before, "confidence_after": after,
        "warning": warning, "line": describe(opening, current, delta, verdict),
    }
    jg["line_move"] = info
    if after != before:
        jg["judge_confidence"] = after
        logger.info("[linemove] game=%s %s → 신뢰도 %s → %s%s",
                    jg["game_id"], verdict, before, after,
                    f" ({warning})" if warning else "")
    return info
