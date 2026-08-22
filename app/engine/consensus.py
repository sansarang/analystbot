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


def consensus_scores(
    picks: list[tuple[str, str]], weights: dict[str, float]
) -> dict[str, float]:
    """picks: [(expert, 정규화된 pick)] → {pick: 정규화 점수(0~1)}."""
    raw: dict[str, float] = defaultdict(float)
    for expert, pick in picks:
        raw[pick] += weights.get(expert, 1.0)
    total = sum(raw.values())
    if total == 0:
        return {}
    return {pick: score / total for pick, score in raw.items()}
