"""수집기 목 모드 검증 — 15경기 적재, 멱등성, 배당 스냅샷, 투수 스탯 분할."""

import pytest

from app.collectors.football import APIFootballClient
from app.collectors.football import upsert_games as upsert_soccer
from app.collectors.mlb import MLBClient, chunked, upsert_final_scores, upsert_games
from app.collectors.odds import OddsClient, snapshot_odds

DATE = "2026-08-22"


async def test_mlb_upsert_loads_15_games(db_pool):
    n = await upsert_games(db_pool, DATE, client=MLBClient(mock=True))
    assert n == 15
    rows = await db_pool.fetch("SELECT * FROM games WHERE sport = 'mlb'")
    assert len(rows) == 15
    assert all(r["home_pitcher"] and r["away_pitcher"] for r in rows)
    assert all(r["status"] == "scheduled" for r in rows)


async def test_mlb_upsert_is_idempotent(db_pool):
    client = MLBClient(mock=True)
    await upsert_games(db_pool, DATE, client=client)
    await upsert_games(db_pool, DATE, client=client)
    assert await db_pool.fetchval("SELECT count(*) FROM games WHERE sport = 'mlb'") == 15


async def test_mlb_final_scores(db_pool):
    client = MLBClient(mock=True)
    await upsert_games(db_pool, DATE, client=client)
    n = await upsert_final_scores(db_pool, DATE, client=client)
    assert n == 15
    row = await db_pool.fetchrow("SELECT * FROM games WHERE sport = 'mlb' LIMIT 1")
    assert row["status"] == "final"
    assert row["home_score"] is not None and row["away_score"] is not None


async def test_pitcher_stats_chunking_and_fetch():
    assert [len(c) for c in chunked(list(range(25)), 10)] == [10, 10, 5]
    client = MLBClient(mock=True)
    people = await client.fetch_pitcher_stats([600000, 600001])
    assert {p["id"] for p in people} == {600000, 600001}
    stat = people[0]["stats"][0]["splits"][0]["stat"]
    assert "era" in stat and "whip" in stat


async def test_odds_snapshot(db_pool):
    await upsert_games(db_pool, DATE, client=MLBClient(mock=True))
    n = await snapshot_odds(db_pool, "mlb", client=OddsClient(mock=True))
    # 야구 Odds 스냅샷은 호출하지 않는다 (언더오버 삭제).
    assert n == 0
    assert await db_pool.fetchval("SELECT count(*) FROM odds_snapshots") == 0


async def test_odds_skips_inplay_and_matches_by_start_time(db_pool):
    """인플레이 이벤트 제외 + 연전(같은 매치업 복수 경기)은 시작 시각으로 매칭."""
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    # 같은 매치업 두 경기: 어제(연전 1차전)와 내일(2차전)
    ids = {}
    for ext, delta in (("g_yesterday", timedelta(days=-1)), ("g_tomorrow", timedelta(days=1))):
        ids[ext] = await db_pool.fetchval(
            "INSERT INTO games (sport, league, ext_id, starts_at, home, away) "
            "VALUES ('soccer', 'EPL', $1, $2, 'Home Nine', 'Away Nine') RETURNING id",
            ext, now + delta,
        )

    def make_event(commence):
        return {
            "home_team": "Home Nine", "away_team": "Away Nine",
            "commence_time": commence.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "bookmakers": [{"key": "dk", "markets": [{"key": "totals", "outcomes": [
                {"name": "Over", "price": 1.9, "point": 8.5},
                {"name": "Under", "price": 1.9, "point": 8.5}]}]}],
        }

    class FakeClient:
        mock = False  # 인플레이 필터 활성화 경로
        last_headers: dict = {}

        async def fetch_odds(self, sport_key, markets=None):
            return [
                make_event(now - timedelta(hours=3)),   # 인플레이 → 스킵
                make_event(now + timedelta(days=1)),    # 내일 경기 → g_tomorrow에 매칭
            ]

    inserted = await snapshot_odds(db_pool, "soccer", client=FakeClient(),
                                   only_keys=["soccer_epl"])
    assert inserted == 2  # 이벤트 1건 × totals Over/Under
    rows = await db_pool.fetch(
        "SELECT game_id, count(*) c FROM odds_snapshots "
        "WHERE game_id = ANY($1::bigint[]) GROUP BY game_id",
        list(ids.values()),
    )
    assert {r["game_id"]: r["c"] for r in rows} == {ids["g_tomorrow"]: 2}


async def test_soccer_schedule_fallback_from_odds_events(db_pool):
    """API-Football이 시즌 미지원일 때 Odds API 이벤트로 KST 당일 경기만 적재."""
    from app.collectors.odds import upsert_games_from_odds_events

    class FakeClient:
        mock = False

        async def fetch_events(self, sport_key):
            if sport_key != "soccer_japan_j_league":
                return []
            return [
                {"id": "ev1", "commence_time": "2026-08-23T10:30:00Z",   # KST 8/23 19:30
                 "home_team": "FC Machida Zelvia", "away_team": "Urawa Red Diamonds"},
                {"id": "ev2", "commence_time": "2026-08-23T16:00:00Z",   # KST 8/24 01:00 → 제외
                 "home_team": "Gamba Osaka", "away_team": "FC Tokyo"},
            ]

    ext_ids = await upsert_games_from_odds_events(db_pool, "2026-08-23", client=FakeClient())
    assert ext_ids == ["odds:ev1"]
    row = await db_pool.fetchrow("SELECT * FROM games WHERE ext_id = 'odds:ev1'")
    assert row["home"] == "FC Machida Zelvia" and row["league"] == "J1 리그"
    # 멱등
    await upsert_games_from_odds_events(db_pool, "2026-08-23", client=FakeClient())
    assert await db_pool.fetchval("SELECT count(*) FROM games WHERE sport='soccer'") == 1


async def test_football_fixtures(db_pool):
    n = await upsert_soccer(db_pool, DATE, client=APIFootballClient(mock=True))
    assert n == 5
    rows = await db_pool.fetch("SELECT * FROM games WHERE sport = 'soccer'")
    assert len(rows) == 5
    assert all(r["league"] == "Premier League" for r in rows)


async def test_football_standings_and_h2h():
    client = APIFootballClient(mock=True)
    standings = await client.fetch_standings()
    table = standings["response"][0]["league"]["standings"][0]
    assert table[0]["rank"] == 1 and "points" in table[0]
    h2h = await client.fetch_h2h(50, 60)
    assert len(h2h["response"]) == 5


# ---------------------------------------------------------------- [§8-14] KBO 공식 지표

_H1 = ("<table><tr><th>순위</th><th>팀명</th><th>AVG</th><th>G</th><th>PA</th>"
       "<th>AB</th><th>R</th><th>H</th></tr>"
       "<tr><td>1</td><td>LG</td><td>0.279</td><td>110</td><td>4300</td>"
       "<td>3700</td><td>568</td><td>1030</td></tr></table>")
_H2 = ("<table><tr><th>순위</th><th>팀명</th><th>AVG</th><th>BB</th><th>IBB</th>"
       "<th>HBP</th><th>SO</th><th>GDP</th><th>SLG</th><th>OBP</th><th>OPS</th></tr>"
       "<tr><td>1</td><td>LG</td><td>0.279</td><td>450</td><td>7</td><td>63</td>"
       "<td>833</td><td>82</td><td>0.405</td><td>0.357</td><td>0.762</td></tr></table>")
_P1 = ("<table><tr><th>순위</th><th>팀명</th><th>ERA</th><th>G</th><th>W</th><th>L</th>"
       "<th>SV</th><th>HLD</th><th>WPCT</th><th>IP</th></tr>"
       "<tr><td>1</td><td>LG</td><td>4.91</td><td>110</td><td>60</td><td>50</td>"
       "<td>30</td><td>45</td><td>0.545</td><td>1008 1/3</td></tr></table>")


def test_kbo_innings_notation_parsed():
    """'1008 1/3' 같은 이닝 표기를 숫자로 바꾼다 — 그냥 float()하면 죽는다."""
    from app.collectors.kbo_stats import _num

    assert _num("1008 1/3") == pytest.approx(1008.333, abs=0.01)
    assert _num("0.279") == pytest.approx(0.279)
    assert _num("해당없음") is None


def test_kbo_header_mismatch_rejects_rows():
    """⚠️ 헤더가 어긋나면 파싱 결과를 버린다 — 컬럼이 밀리면 엉뚱한 값이 ERA가 된다.

    조용한 오염이 조용한 0건보다 나쁘다.
    """
    from app.collectors.kbo_stats import TEAM_HITTER1, parse_table

    bad = _H1.replace("<th>AVG</th>", "<th>타율</th>")
    rows, _ = parse_table(bad, TEAM_HITTER1)
    assert rows == []


def test_kbo_team_stats_shape():
    from app.collectors.kbo_stats import TEAM_HITTER1, TEAM_HITTER2, parse_table

    rows, hdr = parse_table(_H1, TEAM_HITTER1)
    assert len(rows) == 1 and rows[0]["팀명"] == "LG" and rows[0]["R"] == "568"
    rows2, _ = parse_table(_H2, TEAM_HITTER2)
    assert rows2[0]["OBP"] == "0.357"


def test_kbo_league_baselines_come_from_data():
    """[§8-14] 리그 평균은 **수집한 데이터**에서 만든다 — MLB 상수를 쓰지 않는다."""
    from app.collectors.kbo_stats import league_baselines

    teams = {"LG Twins": {"obp": 0.357, "ops": 0.762, "slg": 0.405},
             "NC Dinos": {"obp": 0.339, "ops": 0.742, "slg": 0.403}}
    base = league_baselines(teams)
    assert base["obp"] == pytest.approx(0.348, abs=0.001)
    # wOBA·xwOBA는 KBO 공개 지표가 아니다 — 만들어 넣지 않는다
    assert "woba" not in base and "xwoba" not in base


def test_kbo_merge_prefers_official_over_prose():
    """공식 기록이 딥서치 산문보다 우선이다(LLM 수치는 API와 교차검증, API 승)."""
    from app.collectors.kbo_stats import merge_into_research

    teams = {"LG Twins": {"obp": 0.357, "ops": 0.762, "slg": 0.405,
                          "runs_per_game": 5.17, "team_era": 4.91}}
    pitchers = {"임찬규": {"era_season": 4.14, "whip": 1.389}}
    jg = {"home": "LG Twins", "away": "NC Dinos"}
    research = {"home_pitcher": {"name": "임찬규"}}
    filled = merge_into_research(research, jg, teams, pitchers)
    assert "home_pitcher.era_season" in filled
    assert research["home_pitcher"]["era_season"] == 4.14
    assert research["home_offense"]["obp_30d"] == 0.357
    assert "league_baselines" in research


def test_official_records_override_deep_search():
    """[§8-15] 공식 기록이 딥서치 수치를 **덮어쓴다.**

    실사고(2026-08-26 KBO 첫 실행): 초안이 `if dst not in blk`로 빈칸만 채워
    Perplexity가 준 wOBA 0.325·SIERA 3.50이 그대로 λ에 들어갔고 공식 기록
    (OBP 0.357·ERA 4.14)은 한 번도 쓰이지 않았다.
    규율("LLM 수치는 API와 교차검증, 충돌 시 API 승")이 정반대로 구현돼 있었다.
    """
    from app.collectors.kbo_stats import merge_into_research

    teams = {"LG Twins": {"obp": 0.357, "ops": 0.762, "slg": 0.405,
                          "runs_per_game": 5.17}}
    pitchers = {"임찬규": {"era_season": 4.14, "whip": 1.389}}
    jg = {"home": "LG Twins", "away": "NC Dinos"}
    research = {"home_offense": {"obp_30d": 0.999},          # 딥서치가 준 엉뚱한 값
                "home_pitcher": {"name": "임찬규", "era_season": 9.99}}
    merge_into_research(research, jg, teams, pitchers)
    assert research["home_offense"]["obp_30d"] == 0.357, "딥서치 값이 공식을 이겼다"
    assert research["home_pitcher"]["era_season"] == 4.14


def test_unpublished_metrics_are_stripped():
    """[§8-15] KBO 미공개 지표(wOBA·SIERA 등)는 λ에 들어가기 전에 제거한다.

    KBO는 이 지표들을 공개하지 않는다. LLM이 채워 오면 **출처가 없고**,
    인용인지 지어낸 것인지 구분할 방법이 없다. 없는 것을 있는 척하지 않는다.
    """
    from app.collectors.kbo_stats import merge_into_research

    jg = {"home": "LG Twins", "away": "NC Dinos"}
    research = {"home_offense": {"woba_30d": 0.325, "xwoba_30d": 0.318},
                "home_pitcher": {"name": "임찬규", "siera": 3.50, "xfip": 3.9,
                                 "fip": 4.0, "xwoba_allowed": 0.300}}
    merge_into_research(research, jg, {}, {})
    for k in ("woba_30d", "xwoba_30d"):
        assert k not in research["home_offense"], f"{k}가 남았다"
    for k in ("siera", "xfip", "fip", "xwoba_allowed"):
        assert k not in research["home_pitcher"], f"{k}가 남았다"
    assert research["home_pitcher"]["name"] == "임찬규"    # 이름은 딥서치만 안다


def test_stripping_lets_obp_path_run():
    """미공개 지표를 지워야 OBP 경로가 실제로 쓰인다 — 지우지 않으면 wOBA가 먼저 잡힌다."""
    from app.collectors.kbo_stats import merge_into_research
    from app.config import Settings
    from app.engine.scoring import mlb_lambdas

    teams = {"LG Twins": {"obp": 0.357, "ops": 0.762, "slg": 0.405},
             "NC Dinos": {"obp": 0.353, "ops": 0.755, "slg": 0.402}}
    jg = {"home": "LG Twins", "away": "NC Dinos"}
    research = {"home_offense": {"woba_30d": 0.325}, "away_offense": {"woba_30d": 0.318}}
    merge_into_research(research, jg, teams, {})
    lam = mlb_lambdas(jg, research, Settings(_env_file=None), sport="kbo")
    assert any("OBP" in t for t in lam.trace), f"OBP 경로가 안 쓰였다: {lam.trace}"
    assert not any("wOBA" in t for t in lam.trace)
