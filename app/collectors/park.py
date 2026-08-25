"""[§2] 파크팩터 — 구장별 득점 환경. 외부 유료 소스 없이 statsapi로 자체 산출.

왜 필요한가: λ 산출의 ③단계가 파크팩터를 곱한다. 그동안 이 값은 Perplexity
산문("타자 친화 구장")에서만 왔고, 리서치가 없으면 통째로 건너뛰었다
(실측 2026-08-25: 15경기 전부 미반영).

왜 statsapi인가: 파크팩터에 필요한 건 **경기별 최종 득점**뿐이다. Statcast
투구 단위 원본(시즌 60만 행)을 받을 이유가 없다. statsapi `/schedule`은
날짜 범위 조회로 팀 정식명과 점수를 바로 준다 — 무료·무인증·가볍다.

⚠️ 학습용 `features.rolling_park_factors()`와 목적이 다르다. 저쪽은 **그 경기
이전 누적만** 써서 누수를 막아야 하지만(§8-1), 이쪽은 오늘 경기를 예측하는
용도라 과거 전체를 써도 누수가 아니다 — 오늘 경기는 아직 표본에 없다.
"""

import json
import logging
from datetime import date as _date
from datetime import timedelta

from app.collectors.mlb import MLBClient, _parse_games

logger = logging.getLogger(__name__)

CACHE_KEY = "park_factors:mlb"
CACHE_TTL = 8 * 24 * 3600        # 주 1회 갱신 + 여유
WINDOW_DAYS = 150                # 시즌 대부분 — 구장당 60~70경기
MIN_GAMES = 20                   # 이보다 얇으면 파크팩터를 만들지 않는다

# 클램프는 여기서 하지 않는다 — `scoring._park_factor`가 [0.85, 1.20]으로 절사한다.
# 여기서 미리 자르면 원값을 잃어 진단 때 "왜 1.200인가"를 되짚을 수 없다.


def compute(games: list[dict]) -> dict[str, float]:
    """{홈팀 정식명: 파크팩터}. 구장별 경기당 총득점 ÷ 리그 평균.

    표본이 MIN_GAMES 미만인 구장은 넣지 않는다 — 없는 편이 틀린 값보다 낫다.
    """
    scored = [g for g in games
              if g.get("status") == "final"
              and g.get("home_score") is not None and g.get("away_score") is not None]
    if not scored:
        return {}
    totals = [g["home_score"] + g["away_score"] for g in scored]
    league = sum(totals) / len(totals)
    if league <= 0:
        return {}
    by_park: dict[str, list[int]] = {}
    for g in scored:
        by_park.setdefault(g["home"], []).append(g["home_score"] + g["away_score"])
    out = {}
    for park, runs in by_park.items():
        if len(runs) < MIN_GAMES:
            continue
        out[park] = round((sum(runs) / len(runs)) / league, 4)
    return out


async def fetch_games(client: MLBClient, end: str, days: int = WINDOW_DAYS) -> list[dict]:
    """[end - days, end] 구간의 종료 경기. statsapi는 날짜 범위 조회를 지원한다."""
    last = _date.fromisoformat(end)
    first = last - timedelta(days=days)
    data = await client._get(
        "/schedule",
        params={"sportId": 1, "startDate": first.isoformat(), "endDate": last.isoformat()},
    )
    return _parse_games(data)


async def refresh(redis, end: str | None = None, client: MLBClient | None = None) -> dict:
    """파크팩터를 다시 계산해 캐시. 반환: 요약 dict."""
    from app.pipeline import mlb_slate_date

    end = end or mlb_slate_date()
    client = client or MLBClient()
    games = await fetch_games(client, end)
    table = compute(games)
    if not table:
        logger.warning("[park] 파크팩터 산출 실패 — 종료 경기 %d건", len(games))
        return {"ok": False, "parks": 0, "games": len(games)}
    await redis.set(CACHE_KEY, json.dumps(table, ensure_ascii=False), ex=CACHE_TTL)
    hi = max(table.items(), key=lambda kv: kv[1])
    lo = min(table.items(), key=lambda kv: kv[1])
    logger.info("[park] %d개 구장 갱신 (표본 %d경기) — 최고 %s %.3f / 최저 %s %.3f",
                len(table), len(games), hi[0], hi[1], lo[0], lo[1])
    return {"ok": True, "parks": len(table), "games": len(games)}


async def load(redis) -> dict[str, float]:
    """캐시된 파크팩터. 없으면 빈 dict — λ는 그 보정을 건너뛴다."""
    if redis is None:
        return {}
    try:
        raw = await redis.get(CACHE_KEY)
    except Exception as exc:
        logger.warning("[park] 캐시 조회 실패: %s", exc)
        return {}
    return json.loads(raw) if raw else {}


def merge_into_research(research: dict, jg: dict, parks: dict) -> str | None:
    """홈 구장의 파크팩터를 리서치에 얹는다. 반환: 채운 항목 설명 또는 None.

    리서치가 이미 숫자를 채웠으면 덮지 않는다 (setdefault 규약).
    """
    if not parks or research.get("park_factor") is not None:
        return None
    pf = parks.get(jg.get("home"))
    if pf is None:
        return None
    research["park_factor"] = pf
    return f"파크팩터 {jg['home']} {pf:.3f}"
