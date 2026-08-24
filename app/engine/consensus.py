"""전문가 컨센서스 — expert_ledger 최근 90일 ROI 기반 가중치(0.2~2.0)로 픽 가중 합산."""

from collections import defaultdict

import asyncpg

WEIGHT_MIN, WEIGHT_MAX = 0.2, 2.0


def expert_weight(roi_90d: float | None) -> float:
    """가중치 = clamp(1 + roi_90d, 0.2, 2.0). 이력 없으면 중립 1.0."""
    if roi_90d is None:
        return 1.0
    return max(WEIGHT_MIN, min(WEIGHT_MAX, 1.0 + roi_90d))


async def load_expert_weights(pool: asyncpg.Pool) -> dict[str, float]:
    rows = await pool.fetch("SELECT expert, roi_90d FROM expert_ledger")
    return {
        r["expert"]: expert_weight(float(r["roi_90d"]) if r["roi_90d"] is not None else None)
        for r in rows
    }


async def load_expert_market_ledger(pool: asyncpg.Pool) -> dict[tuple[str, str], dict]:
    """[5] 전문가 전적을 마켓별(h2h/spreads/totals/dc)로 분리 집계."""
    rows = await pool.fetch(
        """
        SELECT expert, split_part(pick, ':', 1) AS market,
               count(*) FILTER (WHERE result IN ('win', 'loss')) AS graded,
               count(*) FILTER (WHERE result = 'win') AS wins,
               CASE WHEN count(*) FILTER (WHERE result IN ('win', 'loss')) > 0
                    THEN sum(CASE WHEN result = 'win'  THEN coalesce(odds, 1.91) - 1
                                  WHEN result = 'loss' THEN -1 ELSE 0 END)
                         / count(*) FILTER (WHERE result IN ('win', 'loss'))
               END AS roi
        FROM expert_picks GROUP BY expert, split_part(pick, ':', 1)
        """
    )
    return {
        (r["expert"], r["market"]): {
            "graded": r["graded"], "wins": r["wins"],
            "roi": round(float(r["roi"]), 4) if r["roi"] is not None else None,
        }
        for r in rows
    }


MIN_GRADED_FOR_ADOPTION = 5  # 이 표본 미만이면 전적 미상 취급 (불채택 아님, 0.5표)


def expert_pick_adopted(ledger: dict | None) -> bool:
    """[5] 해당 마켓 전적이 마이너스(표본 5+)면 불채택 — 인용 데이터만 참고."""
    if not ledger or (ledger.get("graded") or 0) < MIN_GRADED_FOR_ADOPTION:
        return True  # 전적 미상 — 채택하되 0.5표 가중
    roi = ledger.get("roi")
    return roi is None or roi >= 0


def consensus_scores(
    picks: list[tuple[str, str]], weights: dict[str, float]
) -> dict[str, float]:
    """picks: [(expert, 정규화된 pick)] → {pick: 정규화 점수(0~1)}. 전적 미상 0.5표."""
    raw: dict[str, float] = defaultdict(float)
    for expert, pick in picks:
        raw[pick] += weights.get(expert, 0.5)
    total = sum(raw.values())
    if total == 0:
        return {}
    return {pick: score / total for pick, score in raw.items()}
