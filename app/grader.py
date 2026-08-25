"""경기 결과 채점기 — 최종 스코어로 expert_picks.result / predictions.result·pnl 채점.

정규 픽 포맷: h2h:<팀> | dc:<팀>(더블찬스) | spreads:<팀>:<라인> | totals:Over|Under:<라인>
expert_ledger 뷰는 expert_picks 갱신 시 자동 반영된다.
"""

import logging

import asyncpg

from app.collectors.mlb import MLBClient, upsert_final_scores

logger = logging.getLogger(__name__)

FALLBACK_ODDS = 1.91  # 배당 미기록 픽의 pnl 계산용 (-110 상당)


def grade_pick(pick: str, home: str, away: str, home_score: int, away_score: int) -> str | None:
    """'win' | 'loss' | 'push' | None(파싱 불가)."""
    parts = pick.split(":")
    market = parts[0]

    if market == "h2h" and len(parts) == 2:
        team = parts[1]
        if team not in (home, away):
            return None
        if home_score == away_score:
            return "loss"  # 무승부(축구 3-way) — ML 픽은 패 처리
        winner = home if home_score > away_score else away
        return "win" if team == winner else "loss"

    if market == "dc" and len(parts) == 2:  # 더블찬스: 승 또는 무
        team = parts[1]
        if team not in (home, away):
            return None
        if home_score == away_score:
            return "win"
        winner = home if home_score > away_score else away
        return "win" if team == winner else "loss"

    if market == "totals" and len(parts) == 3:
        side, line = parts[1], float(parts[2])
        total = home_score + away_score
        if total == line:
            return "push"
        went_over = total > line
        return "win" if (side == "Over") == went_over else "loss"

    if market == "spreads" and len(parts) == 3:
        team, line = parts[1], float(parts[2])
        if team not in (home, away):
            return None
        team_score, opp_score = (
            (home_score, away_score) if team == home else (away_score, home_score)
        )
        adjusted = team_score + line
        if adjusted == opp_score:
            return "push"
        return "win" if adjusted > opp_score else "loss"

    return None


def pnl_for(result: str, odds: float | None) -> float:
    """1유닛 플랫 베팅 손익."""
    if result == "win":
        return float(odds or FALLBACK_ODDS) - 1.0
    if result == "loss":
        return -1.0
    return 0.0  # push


async def grade_date(pool: asyncpg.Pool, date: str, sport: str = "mlb") -> dict:
    """해당 날짜 final 경기의 미채점 픽·예측을 채점. 집계 카운트 반환."""
    if sport == "mlb":
        await upsert_final_scores(pool, date, client=MLBClient())

    finals = await pool.fetch(
        """
        SELECT id, home, away, home_score, away_score FROM games
        WHERE sport = $1 AND status = 'final'
          AND home_score IS NOT NULL AND away_score IS NOT NULL
        """,
        sport,
    )
    counts = {"expert_picks": 0, "predictions": 0, "unparseable": 0}
    # [6] 병렬 채점 — 방식별(performance / legacy) 집계도 함께 센다
    for g in finals:
        args = (g["home"], g["away"], g["home_score"], g["away_score"])

        for row in await pool.fetch(
            "SELECT id, pick, odds FROM expert_picks WHERE game_id = $1 AND result IS NULL",
            g["id"],
        ):
            result = grade_pick(row["pick"], *args)
            if result is None:
                counts["unparseable"] += 1
                continue
            await pool.execute(
                "UPDATE expert_picks SET result = $2 WHERE id = $1", row["id"], result
            )
            counts["expert_picks"] += 1

        for row in await pool.fetch(
            "SELECT id, pick, odds, method FROM predictions "
            "WHERE game_id = $1 AND result IS NULL",
            g["id"],
        ):
            result = grade_pick(row["pick"], *args)
            if result is None:
                counts["unparseable"] += 1
                continue
            await pool.execute(
                "UPDATE predictions SET result = $2, pnl = $3 WHERE id = $1",
                row["id"], result, pnl_for(result, row["odds"] and float(row["odds"])),
            )
            counts["predictions"] += 1
            key = f"predictions:{row.get('method') or 'performance'}"
            counts[key] = counts.get(key, 0) + 1

    logger.info("[grader] %s %s -> %s", sport, date, counts)
    return counts


# ---------------------------------------------------------------- [6] 방식별 집계

async def method_ledger(pool) -> list[dict]:
    """[6] 경기력 기반 vs 시장 반영 — 어느 쪽이 실제로 맞히는지 나란히 집계.

    2~3주 뒤 판별이 목적이므로 표본 수를 함께 돌려준다 (적은 표본으로 결론 금지).
    """
    rows = await pool.fetch(
        """
        SELECT method,
               count(*) FILTER (WHERE result IN ('win','loss','push')) AS graded,
               count(*) FILTER (WHERE result = 'win')  AS wins,
               count(*) FILTER (WHERE result = 'loss') AS losses,
               coalesce(sum(pnl), 0)                   AS pnl_units,
               avg(model_p) FILTER (WHERE result IS NOT NULL) AS avg_p
        FROM predictions
        GROUP BY method
        ORDER BY method
        """
    )
    out = []
    for r in rows:
        graded = r["graded"] or 0
        decided = (r["wins"] or 0) + (r["losses"] or 0)
        out.append({
            "method": r["method"] or "performance",
            "graded": graded,
            "wins": r["wins"] or 0,
            "losses": r["losses"] or 0,
            "hit_rate": round((r["wins"] or 0) / decided, 4) if decided else None,
            "pnl_units": float(r["pnl_units"] or 0),
            "avg_p": float(r["avg_p"]) if r["avg_p"] is not None else None,
        })
    return out
