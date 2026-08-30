"""The Odds API v4 수집기 — h2h/spreads/totals decimal 배당을 odds_snapshots에 적재.

주의 (실사고 이력):
- 이미 시작한 경기는 인플레이 배당(스코어 따라 요동)이 내려오므로 적재하지 않는다.
- 같은 매치업이 연전으로 여러 경기 있을 수 있어 (home, away) 이름만으로 매칭하면
  다른 날짜 경기에 배당이 붙는다 → 시작 시각(±2h)까지 맞는 경기에만 매칭한다.
"""

import logging
from datetime import UTC, datetime, timedelta

import asyncpg

from app.collectors.base import BaseAPIClient
from app.config import get_settings

logger = logging.getLogger(__name__)

from app.leagues import LEAGUES

SPORT_KEYS: dict[str, list[str]] = {
    "mlb": ["baseball_mlb"],
    "soccer": [cfg["odds_key"] for cfg in LEAGUES.values()],  # 화이트리스트 7개 리그
    # [§8-14] KBO·NPB — statsapi가 껍데기(sportId 31/32는 팀 명단만, totalGames=0)라
    #   일정·점수를 받을 다른 경로가 없다. Odds API `/scores`가 **일정·완료여부·점수**를
    #   한 번에 주므로 이것이 두 리그의 유일한 채점 경로다.
    #   (실조회 2026-08-26: baseball_kbo·baseball_npb 모두 active=True)
    "kbo": ["baseball_kbo"],
    "npb": ["baseball_npb"],
}

# 야구는 Odds 배당·토탈 라인을 쓰지 않는다 (2026-08-29). /scores 일정·점수는 별도.
BASEBALL_ODDS_SPORTS = ("mlb", "kbo", "npb")


def odds_markets_for(sport: str) -> str:
    """Odds API `markets` 파라미터. 야구 snapshot은 호출하지 않는다."""
    if sport in BASEBALL_ODDS_SPORTS:
        return ""
    return "h2h,spreads,totals"


LEAGUE_LABEL_BY_SPORT = {"kbo": "KBO", "npb": "NPB", "mlb": "MLB"}
SOCCER_LEAGUE_LABELS = {cfg["odds_key"]: cfg["label"] for cfg in LEAGUES.values()}


async def record_odds_quota(client: "OddsClient") -> None:
    """일일 크레딧 사용량·잔여량을 로그 + Redis 기록 (카드 경고용)."""
    remaining = client.last_headers.get("x-requests-remaining")
    used = client.last_headers.get("x-requests-used")
    if remaining is None:
        return
    logger.info("[odds] quota: used=%s remaining=%s", used, remaining)
    try:
        import redis.asyncio as aioredis

        from app.config import get_settings

        r = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        await r.set("odds_quota_remaining", remaining, ex=86400)
        await r.aclose()
    except Exception as exc:
        logger.debug("[odds] quota record skipped: %s", exc)

MATCH_WINDOW = timedelta(hours=2)  # 이벤트 commence_time ↔ games.starts_at 허용 오차


class OddsClient(BaseAPIClient):
    name = "odds"
    base_url = "https://api.the-odds-api.com/v4"

    def __init__(self, mock: bool | None = None):
        settings = get_settings()
        super().__init__(settings.mock_odds if mock is None else mock)
        self.api_key = settings.odds_api_key

    async def fetch_odds(self, sport_key: str = "baseball_mlb",
                        markets: str | None = None) -> list[dict]:
        if markets is None:
            markets = ("totals" if "baseball" in sport_key
                       else "h2h,spreads,totals")
        if self.mock:
            return self.load_mock(f"odds_{'mlb' if 'baseball' in sport_key else 'soccer'}.json")
        return await self._get(
            f"/sports/{sport_key}/odds",
            params={
                "apiKey": self.api_key,
                "regions": "us",
                "markets": markets,
                "oddsFormat": "decimal",
            },
        )

    async def fetch_scores(self, sport_key: str, days_from: int = 2) -> list[dict]:
        """[§8-14] 최근·예정 경기의 **일정 + 완료여부 + 점수**.

        `/scores`는 commence_time·home_team·away_team·completed·scores를 함께 준다.
        KBO·NPB는 이것이 유일한 점수 소스이며, **채점 경로 없이 픽을 내지 않는다**는
        규율상 이 엔드포인트가 두 리그 지원의 전제다.
        ⚠️ daysFrom을 쓰면 요청 비용이 2배다(무료 쿼터 관리 주의).
        """
        if self.mock:
            return self.load_mock(f"scores_{sport_key}.json")
        return await self._get(
            f"/sports/{sport_key}/scores",
            params={"apiKey": self.api_key, "daysFrom": days_from},
        )

    async def fetch_events(self, sport_key: str) -> list[dict]:
        """예정 이벤트 목록 (배당 없음, 저비용) — 일정 소스 폴백용."""
        if self.mock:
            return self.load_mock(f"odds_{'mlb' if 'baseball' in sport_key else 'soccer'}.json")
        return await self._get(
            f"/sports/{sport_key}/events", params={"apiKey": self.api_key}
        )


def _match_game(rows: list, home: str, away: str, commence: datetime) -> int | None:
    """홈/원정 퍼지 매칭 + 시작 시각 ±2h 내에서 가장 가까운 경기를 고른다.

    (소스별 팀명 표기가 다르고, 같은 매치업이 연전으로 여러 경기일 수 있다.)
    """
    from app.collectors.football import similar_team

    for exact in (True, False):  # 정확 일치 우선, 표기 상이 시 퍼지
        best_id, best_diff = None, MATCH_WINDOW
        for r in rows:
            diff = abs(r["starts_at"] - commence)
            if diff > best_diff:
                continue
            if exact:
                ok = r["home"] == home and r["away"] == away
            else:
                ok = similar_team(r["home"], home) and similar_team(r["away"], away)
            if ok:
                best_id, best_diff = r["id"], diff
        if best_id is not None:
            return best_id
    return None


async def snapshot_odds(
    pool: asyncpg.Pool, sport: str = "mlb", client: OddsClient | None = None,
    only_keys: list[str] | None = None,
) -> int:
    """이벤트를 (home, away, 시작시각)으로 games와 매칭해 스냅샷 적재. 적재 행 수 반환.

    only_keys: 크레딧 절약용 — 경기가 있는 리그 키만 조회.
    """
    from app.api_guard import is_blocked, is_disabled

    if sport in BASEBALL_ODDS_SPORTS:
        logger.info("[odds] snapshot skipped — 야구 언더오버 미사용")
        return 0

    if is_disabled("odds") or await is_blocked("odds"):
        logger.info("[odds] snapshot skipped — %s",
                    "disabled" if is_disabled("odds") else "차단 중")
        return 0
    client = client or OddsClient()
    keys = only_keys if only_keys is not None else SPORT_KEYS[sport]
    if client.mock:
        keys = SPORT_KEYS[sport][:1]  # 목 파일은 리그 구분 없이 하나 — 중복 적재 방지
    markets = odds_markets_for(sport)
    events: list[dict] = []
    for sport_key in keys:
        events.extend(await client.fetch_odds(sport_key, markets=markets))
    if not client.mock:
        await record_odds_quota(client)

    rows = await pool.fetch(
        "SELECT id, home, away, starts_at FROM games WHERE sport = $1 AND status = 'scheduled'",
        sport,
    )

    now = datetime.now(UTC)
    inserted = skipped_inplay = 0
    for ev in events:
        commence = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
        # 인플레이 배당 배제 (목 모드는 고정 샘플이라 시간 비교를 건너뜀)
        if not client.mock and commence <= now:
            skipped_inplay += 1
            continue
        game_id = _match_game(rows, ev["home_team"], ev["away_team"], commence)
        if game_id is None:
            logger.warning(
                "[odds] no game match: %s @ %s (%s)",
                ev["away_team"], ev["home_team"], ev["commence_time"],
            )
            continue
        for bm in ev.get("bookmakers", []):
            for market in bm.get("markets", []):
                # 야구는 토탈 라인만 적재한다. 목 파일이 h2h를 줘도 승부 배당은 안 넣는다.
                if sport in BASEBALL_ODDS_SPORTS and market.get("key") != "totals":
                    continue
                for outcome in market.get("outcomes", []):
                    await pool.execute(
                        """
                        INSERT INTO odds_snapshots (game_id, book, market, side, line, odds)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        game_id, bm["key"], market["key"],
                        outcome["name"], outcome.get("point"), outcome["price"],
                    )
                    inserted += 1
    logger.info(
        "[odds] inserted %d snapshot rows (%s), skipped %d in-play events",
        inserted, sport, skipped_inplay,
    )
    return inserted


async def upsert_games_from_odds_events(
    pool: asyncpg.Pool, date: str, client: OddsClient | None = None,
    only_keys: list[str] | None = None,
) -> list[str]:
    """축구 일정 폴백 — API-Football이 현재 시즌을 못 줄 때 Odds API 이벤트로 적재.

    KST 기준 해당 날짜 경기만. ext_id는 'odds:<event id>'. 적재한 ext_id 목록 반환.
    주의: 이 경로로 적재된 경기는 최종 스코어 소스가 없어 자동 채점이 불가하다.
    """
    from zoneinfo import ZoneInfo

    from app.collectors.football import similar_team

    kst = ZoneInfo("Asia/Seoul")
    client = client or OddsClient()
    keys = only_keys if only_keys is not None else SPORT_KEYS["soccer"]
    if client.mock:
        keys = SPORT_KEYS["soccer"][:1]
    # 타 소스(football-data 등)로 이미 적재된 경기는 중복 생성 금지 (이름 표기 상이 대비 퍼지 매칭)
    existing = await pool.fetch(
        "SELECT home, starts_at FROM games WHERE sport = 'soccer' AND ext_id NOT LIKE 'odds:%'"
    )
    ext_ids: list[str] = []
    for sport_key in keys:
        for ev in await client.fetch_events(sport_key):
            commence = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
            if commence.astimezone(kst).strftime("%Y-%m-%d") != date:
                continue
            if any(
                abs(r["starts_at"] - commence) <= MATCH_WINDOW
                and similar_team(r["home"], ev["home_team"])
                for r in existing
            ):
                continue
            ext_id = f"odds:{ev['id']}"
            await pool.execute(
                """
                INSERT INTO games (sport, league, ext_id, starts_at, home, away, status)
                VALUES ('soccer', $1, $2, $3, $4, $5, 'scheduled')
                ON CONFLICT (sport, ext_id) DO UPDATE SET
                    starts_at = EXCLUDED.starts_at, updated_at = now()
                """,
                SOCCER_LEAGUE_LABELS.get(sport_key, sport_key), ext_id,
                commence, ev["home_team"], ev["away_team"],
            )
            ext_ids.append(ext_id)
    logger.info("[odds] soccer schedule fallback: %d games for %s (KST)", len(ext_ids), date)
    return ext_ids


# ---------------------------------------------------------------- [§8-14] KBO·NPB 일정·점수

def _scores_map(ev: dict) -> dict[str, int]:
    """`scores` 배열 → {팀명: 점수}. 숫자로 못 바꾸면 버린다(지어내지 않는다)."""
    out: dict[str, int] = {}
    for row in ev.get("scores") or []:
        try:
            out[row["name"]] = int(row["score"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


async def upsert_games_from_scores(
    pool: asyncpg.Pool, sport: str, date: str | None = None,
    client: OddsClient | None = None, days_from: int = 2,
) -> dict:
    """[§8-14] Odds API `/scores`로 KBO·NPB 일정과 최종 점수를 함께 적재.

    반환: {"scheduled": n, "final": n, "total": n}

    - `date`(KST)를 주면 그날 경기만 일정으로 센다. 점수 반영은 날짜와 무관하게
      완료된 전 경기에 적용한다(우천 순연으로 어제 경기가 오늘 확정되기도 한다).
    - 시간대: commence_time은 UTC다. DB는 UTC 저장 규약이므로 그대로 넣는다.
    - **completed=True이고 점수가 둘 다 있을 때만 final**로 본다. 진행 중 0-0을
      종료로 오판하면 채점이 오염된다(KBO 공식 파서에서 겪은 사고와 같은 유형).
    """
    from zoneinfo import ZoneInfo

    client = client or OddsClient()
    label = LEAGUE_LABEL_BY_SPORT.get(sport, sport.upper())
    kst = ZoneInfo("Asia/Seoul")
    counts = {"scheduled": 0, "final": 0, "total": 0}
    for sport_key in SPORT_KEYS.get(sport, []):
        for ev in await client.fetch_scores(sport_key, days_from=days_from):
            try:
                commence = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
            except (KeyError, ValueError):
                continue
            counts["total"] += 1
            sc = _scores_map(ev)
            hs, as_ = sc.get(ev.get("home_team")), sc.get(ev.get("away_team"))
            done = bool(ev.get("completed")) and hs is not None and as_ is not None
            status = "final" if done else "scheduled"
            if not done and date is not None:
                if commence.astimezone(kst).strftime("%Y-%m-%d") != date:
                    continue          # 그날 경기가 아니면 일정으로 세지 않는다
            await pool.execute(
                """
                INSERT INTO games (sport, league, ext_id, starts_at, home, away,
                                   status, home_score, away_score)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (sport, ext_id) DO UPDATE SET
                    starts_at  = EXCLUDED.starts_at,
                    status     = EXCLUDED.status,
                    home_score = COALESCE(EXCLUDED.home_score, games.home_score),
                    away_score = COALESCE(EXCLUDED.away_score, games.away_score),
                    updated_at = now()
                """,
                sport, label, f"odds:{ev['id']}", commence,
                ev.get("home_team"), ev.get("away_team"), status, hs, as_,
            )
            counts["final" if done else "scheduled"] += 1
    logger.info("[odds] %s 일정·점수 적재 — 예정 %d / 종료 %d (조회 %d)",
                label, counts["scheduled"], counts["final"], counts["total"])
    return counts


async def upsert_final_scores(pool: asyncpg.Pool, date: str, days: int = 2,
                              sport: str = "kbo", client: OddsClient | None = None) -> int:
    """종료 점수 적재 진입점 — `ingest_finals`가 MLB·KBO와 같은 계약으로 부른다."""
    counts = await upsert_games_from_scores(pool, sport, date=None,
                                            client=client, days_from=days)
    return counts["final"]
