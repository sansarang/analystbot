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


STALE_AFTER_HOURS = 6      # 시작 후 이만큼 지났는데 final이 아니면 상태가 밀린 것


async def reconcile_stale_games(pool: asyncpg.Pool) -> dict:
    """시작 후 STALE_AFTER_HOURS 지났는데 final이 아닌 경기의 상태를 다시 받아온다.

    실사고(2026-08-25): 8/22~8/23 경기가 'live'(점수는 있음)·'scheduled'(점수 없음)로
    멈춰 있었다. 점수 갱신이 **채점 대상 날짜에만** 돌아 그 전날들이 영영 밀렸다.
    채점은 status='final'만 보므로, 밀린 경기의 픽은 영원히 미채점으로 남는다.
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT sport, (starts_at AT TIME ZONE 'UTC')::date AS d
        FROM games
        WHERE status <> 'final'
          AND starts_at < now() - make_interval(hours => $1)
        ORDER BY 1, 2
        """,
        STALE_AFTER_HOURS,
    )
    fixed = {"mlb": 0, "soccer": 0}
    for r in rows:
        sport, day = r["sport"], r["d"].strftime("%Y-%m-%d")
        try:
            if sport == "mlb":
                fixed["mlb"] += await upsert_final_scores(pool, day)
            else:
                from app.collectors.football import (
                    FootballDataClient,
                    upsert_games_from_football_data,
                )

                # 축구는 KST 날짜 기준으로 조회한다 (수집기 계약)
                kst_day = (r["d"]).strftime("%Y-%m-%d")
                ids = await upsert_games_from_football_data(
                    pool, kst_day, client=FootballDataClient())
                fixed["soccer"] += len(ids)
        except Exception as exc:   # 정합 실패가 채점을 막지 않는다
            logger.warning("[grader] stale 정합 실패 %s %s: %s", sport, day, exc)
    if any(fixed.values()):
        logger.info("[grader] stale 경기 정합 — %s", fixed)
    return fixed


# [§8-18] CLV(마감 배당 대비 가치) 수집 삭제.
#   우리 가격을 시장 마감가와 비교하는 지표라 **시장에 앵커링**된다.
#   "시장보다 좋은 가격을 잡았나"가 아니라 **"우리가 맞혔나"**가 유일한 질문이다.
#   남은 평가 축은 ①방향 적중률 ②점수 오차(MAE) 둘뿐이다.
#   (predictions.closing_odds 컬럼은 과거 기록 보존을 위해 남기되 더 이상 채우지 않는다)


async def grade_date(pool: asyncpg.Pool, date: str, sport: str = "mlb") -> dict:
    """해당 날짜 final 경기의 미채점 픽·예측을 채점. 집계 카운트 반환."""
    if sport == "mlb":
        await upsert_final_scores(pool, date, client=MLBClient())
    elif sport in ("kbo", "npb"):
        # [§8-14] statsapi가 껍데기(sportId 31/32는 팀 명단만)라 외부 소스가 필요하다.
        #   KBO: 공식 기록실 1순위 → 실패하면 Odds API `/scores` 폴백
        #   NPB: 공식 파서가 없다 → Odds API `/scores`가 유일한 경로
        #   최근 7일(KBO)·2일(Odds)을 훑는 이유: 우천 순연으로 어제 경기가 오늘 확정된다.
        from app.collectors.odds import upsert_final_scores as odds_finals

        if sport == "kbo":
            try:
                from app.collectors.kbo import upsert_final_scores as kbo_finals

                await kbo_finals(pool, date, days=7)
            except Exception as exc:      # 공식 사이트 구조 변경 — 채점을 멈추지 않는다
                logger.warning("[grader] KBO 공식 기록실 실패, Odds 폴백: %s", exc)
                await odds_finals(pool, date, days=2, sport="kbo")
        else:
            # [§8-28] NPB는 **Yahoo가 1순위**다. Odds `/scores`는 완료 경기가
            #   한 건도 안 잡혀 채점이 증명되지 않았다(실측 2026-08-26).
            try:
                from app.collectors.yahoo_npb import upsert_final_scores as yahoo_finals

                await yahoo_finals(pool, date, days=3)
            except Exception as exc:
                logger.warning("[grader] Yahoo NPB 실패, Odds 폴백: %s", exc)
                await odds_finals(pool, date, days=2, sport="npb")

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

CALIBRATION_BANDS = ((0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 1.01))


def brier_score(rows) -> float | None:
    """[§7] Brier score = mean((예측확률 - 실제결과)^2). 낮을수록 좋다.

    적중률만 보면 "60% 픽을 60% 맞혔다"와 "60% 픽을 90% 맞혔다"를 구분 못 한다.
    Brier는 확률 자체가 얼마나 잘 캘리브레이션됐는지를 잰다.
    기준선: 항상 0.5를 찍으면 0.25. 그보다 낮아야 예측에 값이 있다.
    """
    vals = []
    for r in rows:
        p, res = r.get("model_p"), r.get("result")
        if p is None or res not in ("win", "loss"):
            continue
        vals.append((float(p) - (1.0 if res == "win" else 0.0)) ** 2)
    return round(sum(vals) / len(vals), 4) if vals else None


def calibration_bands(rows) -> list[dict]:
    """[§7] 예측 확률 구간별 실제 승률 — "60%라고 한 픽이 정말 60% 이겼나".

    캘리브레이션이 무너지면(예측 65% 구간의 실제 승률 45%) 적중률이 좋아도
    확률을 믿을 수 없다는 뜻이다.
    """
    buckets: dict[tuple, list] = {b: [] for b in CALIBRATION_BANDS}
    for r in rows:
        p, res = r.get("model_p"), r.get("result")
        if p is None or res not in ("win", "loss"):
            continue
        p = float(p)
        for lo, hi in CALIBRATION_BANDS:
            if lo <= p < hi:
                buckets[(lo, hi)].append(1 if res == "win" else 0)
                break
    out = []
    for (lo, hi), hits in buckets.items():
        if not hits:
            continue
        actual = sum(hits) / len(hits)
        out.append({
            "band": f"{lo:.0%}~{min(hi, 1.0):.0%}", "n": len(hits),
            "predicted": round((lo + min(hi, 1.0)) / 2, 3),
            "actual": round(actual, 3),
            "gap": round(actual - (lo + min(hi, 1.0)) / 2, 3),
        })
    return out


async def three_way_ledger(pool) -> list[dict]:
    """[§6-4] 세 방식(임의 계수 / 학습 계수 / Claude 판정)을 실전 결과로 비교.

    같은 픽 행에 세 확률이 함께 기록돼 있으므로 **동일 표본**에서 비교된다
    (방식별로 다른 픽을 고른 게 아니라, 같은 경기를 셋이 어떻게 봤는지를 본다).
    """
    rows = await pool.fetch(
        "SELECT p_heuristic, p_learned, p_claude, result FROM predictions "
        "WHERE result IN ('win','loss')")
    out = []
    for col, label in (("p_heuristic", "임의 계수 λ"), ("p_learned", "학습 계수 λ"),
                       ("p_claude", "Claude 판정")):
        detail = [{"model_p": float(r[col]), "result": r["result"]}
                  for r in rows if r[col] is not None]
        if not detail:
            out.append({"method": col, "label": label, "n": 0})
            continue
        hits = sum(1 for d in detail
                   if (d["model_p"] >= 0.5) == (d["result"] == "win"))
        out.append({
            "method": col, "label": label, "n": len(detail),
            "accuracy": round(hits / len(detail), 4),
            "brier": brier_score(detail),
            "calibration": calibration_bands(detail),
        })
    return out


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
        method = r["method"] or "performance"
        graded = r["graded"] or 0
        decided = (r["wins"] or 0) + (r["losses"] or 0)
        detail = await pool.fetch(
            "SELECT model_p, result FROM predictions "
            "WHERE method = $1 AND result IN ('win','loss')", method)
        detail = [dict(d) for d in detail]
        out.append({
            "method": method,
            "graded": graded,
            "wins": r["wins"] or 0,
            "losses": r["losses"] or 0,
            "hit_rate": round((r["wins"] or 0) / decided, 4) if decided else None,
            "pnl_units": float(r["pnl_units"] or 0),
            "avg_p": float(r["avg_p"]) if r["avg_p"] is not None else None,
            # [§7] 적중률만으로는 확률의 질을 못 잰다
            "brier": brier_score(detail),
            "calibration": calibration_bands(detail),
        })
    return out
