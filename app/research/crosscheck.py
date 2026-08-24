"""리서치 수치 ↔ API 실데이터 교차검증 샘플링 — '지어내기' 감시 장치.

배경: 1차 프롬프트에 "못 찾은 이유를 설명하지 말고 null을 써라"는 금지문을 넣으면
설명 산문은 사라지지만, 모델이 빈칸을 **지어내** 채울 유인이 생긴다. 검증기는
'데이터처럼 생긴 값'을 막지 못하므로, 하루 표본 2경기를 뽑아 리서치가 반환한
수치를 API 실데이터와 대조한다.

절대 규칙 2("LLM 수치와 API 숫자가 충돌하면 API가 이긴다")의 감시 구현이다.
불일치가 반복되면 금지문 롤백 신호 — 판단 기준은 docs/RESEARCH_VALIDATION.md.
"""

import logging
import random

logger = logging.getLogger(__name__)

SAMPLE_SIZE = 2          # 하루 표본 경기 수
ERA_TOLERANCE = 0.30     # 선발 시즌 ERA 허용 오차 (자책점 반올림·집계 시점 차)
FORM_TOLERANCE = 0.40    # 최근 폼 승률 vs API 최근 10경기 승률 허용 오차 (표본 길이 차)


def _form_win_rate(form: str | None) -> float | None:
    """'WWLWL' → 0.6. 무승부(D)는 0.5승으로 센다."""
    if not form:
        return None
    seq = [c for c in str(form).upper() if c in "WLD"]
    if not seq:
        return None
    return (seq.count("W") + 0.5 * seq.count("D")) / len(seq)


def compare_game(jg_or_game: dict, research: dict | None, stats: dict) -> list[dict]:
    """경기 1건의 리서치 수치 ↔ statsapi 수치 대조 결과.

    각 항목: {field, research, api, diff, mismatch}
    """
    out: list[dict] = []
    research = research or {}
    era_map = stats.get("era") or {}
    win_pct = stats.get("win_pct") or {}

    for side, team_key in (("home_pitcher", "home"), ("away_pitcher", "away")):
        block = research.get(side) or {}
        name, era = block.get("name"), block.get("era_season")
        if not name or era is None:
            continue
        api_era = era_map.get(name)
        if api_era is None:
            continue
        diff = abs(float(era) - float(api_era))
        out.append({
            "field": f"{side}.era_season", "player": name,
            "research": round(float(era), 2), "api": round(float(api_era), 2),
            "diff": round(diff, 2), "mismatch": diff > ERA_TOLERANCE,
        })

    for side, team_key in (("home_recent_form", "home"), ("away_recent_form", "away")):
        rate = _form_win_rate((research.get(side) or {}).get("form"))
        team = jg_or_game.get(team_key)
        api_rate = win_pct.get(team)
        if rate is None or api_rate is None:
            continue
        diff = abs(rate - float(api_rate))
        out.append({
            "field": f"{side}.form", "player": team,
            "research": round(rate, 2), "api": round(float(api_rate), 2),
            "diff": round(diff, 2), "mismatch": diff > FORM_TOLERANCE,
        })
    return out


def sample_games(games: list[dict], n: int = SAMPLE_SIZE, rng=None) -> list[dict]:
    rng = rng or random
    pool = [g for g in games if g.get("status", "scheduled") == "scheduled"]
    return rng.sample(pool, min(n, len(pool))) if pool else []


async def crosscheck_sample(
    redis, games: list[dict], research_map: dict, stats: dict, sport: str,
    n: int = SAMPLE_SIZE, rng=None, date: str | None = None,
) -> list[dict]:
    """하루 표본 n경기 교차검증 → 불일치를 로그·카운터에 남기고 결과 반환.

    축구는 대조 가능한 무료 실데이터 소스가 얇아 현재 MLB(statsapi)만 대상이다.
    """
    if sport != "mlb":
        logger.info("[crosscheck] %s는 대조 대상 아님 (statsapi 미적용) — 생략", sport)
        return []
    results: list[dict] = []
    for g in sample_games(games, n, rng):
        gid = g.get("game_id") or g.get("id")
        for row in compare_game(g, research_map.get(gid), stats):
            row["game_id"] = gid
            results.append(row)

    mismatches = [r for r in results if r["mismatch"]]
    if mismatches:
        for r in mismatches:
            logger.warning(
                "[crosscheck] 불일치 game=%s %s(%s): 리서치 %s vs API %s (차이 %s)",
                r["game_id"], r["field"], r["player"], r["research"], r["api"], r["diff"])
    else:
        logger.info("[crosscheck] 표본 %d항목 전부 API와 일치 (불일치 0)", len(results))

    if redis is not None:
        from app.pipeline import today_kst

        key = f"research_crosscheck:{date or today_kst()}"
        await redis.hincrby(key, "checked", len(results))
        await redis.hincrby(key, "mismatch", len(mismatches))
        await redis.expire(key, 86400 * 30)
    return results


async def crosscheck_report(redis, date: str) -> dict:
    key = f"research_crosscheck:{date}"
    raw = await redis.hgetall(key) or {}
    checked = int(raw.get("checked", 0) or 0)
    mismatch = int(raw.get("mismatch", 0) or 0)
    return {"checked": checked, "mismatch": mismatch,
            "rate": round(mismatch / checked, 3) if checked else None}
