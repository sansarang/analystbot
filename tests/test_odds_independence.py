"""[Odds] 야구 일정은 Odds API 없이, 배당·언더오버 라인도 조회하지 않는다.

🔴 실사고 2026-08-27: Odds 크레딧이 마르자 KBO 응답 전체가
   "⚠️ odds API 사용량/크레딧이 소진되어 분석을 완료하지 못했습니다" 한 줄로
   대체됐다. 일정 소스만 Odds였기 때문이다. 일정 분기는 그대로 Odds를 부르지 않는다.

승부 배당·언더오버 라인 모두 쓰지 않는다 (2026-08-29).
"""
import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _branch_source(sport_marker: str) -> str:
    src = (ROOT / "app/pipeline.py").read_text(encoding="utf-8")
    start = src.index(sport_marker)
    return src[start:src.index("    else:", start)]


def test_kbo_npb_branch_does_not_call_the_odds_api():
    """🔴 일정 분기에서 OddsClient를 부르면 크레딧이 마를 때 다시 죽는다."""
    branch = _branch_source('    elif sport in ("kbo", "npb"):')
    for banned in ("OddsClient", "upsert_games_from_scores", "snapshot_odds"):
        assert banned not in branch, f"KBO·NPB 일정 경로에 {banned}이 남아 있다"
    assert "upsert_schedule" in branch, "공식 일정 소스가 배선되지 않았다"


def test_baseball_does_not_fetch_odds():
    """야구 언더오버 삭제 — Odds API를 호출하지 않는다."""
    from app.collectors.odds import odds_markets_for

    src = (ROOT / "app/pipeline.py").read_text(encoding="utf-8")
    i = src.index('    if sport in ("mlb", "kbo", "npb"):')
    block = src[i:src.index("    else:", i)]
    assert "active_keys = []" in block
    assert odds_markets_for("soccer") == "h2h,spreads,totals"
    assert odds_markets_for("mlb") == ""

def test_odds_snapshot_is_skipped_when_no_keys():
    src = (ROOT / "app/pipeline.py").read_text(encoding="utf-8")
    fn = src[src.index("async def _odds_or_none():"):src.index("stats, _odds_rows")]
    assert "if not active_keys:" in fn and "return []" in fn


def test_official_schedule_entrypoints_exist_and_share_a_contract():
    """KBO·NPB가 같은 계약을 돌려줘야 파이프라인이 한 갈래로 처리한다."""
    from app.collectors import kbo, yahoo_npb

    for mod in (kbo, yahoo_npb):
        fn = getattr(mod, "upsert_schedule", None)
        assert fn is not None, f"{mod.__name__}에 upsert_schedule이 없다"
        args = [a.arg for a in ast.parse(
            (ROOT / mod.__file__.split("analystbot/")[-1]).read_text(encoding="utf-8")
        ).body[-1].args.args]
        assert args[:2] == ["pool", "date"], f"{mod.__name__} 시그니처 불일치: {args}"


@pytest.mark.asyncio
async def test_kbo_schedule_upsert_counts_by_status(monkeypatch):
    """예정/종료 집계가 Odds 경로와 같은 키로 나와야 호출부가 안 깨진다."""
    from app.collectors import kbo

    async def fake_month(season, month, client=None):
        return [
            {"date": "2026-08-27", "time": "18:30", "home": "H1", "away": "A1",
             "status": "scheduled", "home_score": None, "away_score": None,
             "ext_id": "kbo:1"},
            {"date": "2026-08-27", "time": "18:30", "home": "H2", "away": "A2",
             "status": "final", "home_score": 5, "away_score": 3, "ext_id": "kbo:2"},
            {"date": "2026-08-26", "time": "18:30", "home": "H3", "away": "A3",
             "status": "final", "home_score": 1, "away_score": 0, "ext_id": "kbo:3"},
        ]

    seen = []

    async def fake_upsert(pool, games):
        seen.extend(games)
        return len(games)

    monkeypatch.setattr(kbo, "fetch_month", fake_month)
    monkeypatch.setattr(kbo, "upsert_games", fake_upsert)
    counts = await kbo.upsert_schedule(None, "2026-08-27")
    assert counts == {"scheduled": 1, "final": 1, "total": 2}
    assert all(g["date"] == "2026-08-27" for g in seen), "다른 날 경기가 섞였다"


def test_kbo_card_shows_no_odds_warnings():
    """🔴 안 쓰는 배당의 경고를 띄우면 사용자가 고칠 수 없는 잡음이 된다."""
    from app.pipeline import _render_card, data_limitation_line

    for sport in ("kbo", "npb", "mlb"):
        out = _render_card({"date": "2026-08-27", "sport": sport, "games": [],
                            "picks": [], "recommended": [], "quota_warning": True})
        assert "배당 데이터 잔여 쿼터" not in out
    soccer = _render_card({"date": "2026-08-27", "sport": "soccer", "games": [],
                           "picks": [], "recommended": [], "quota_warning": True})
    assert "배당 데이터 잔여 쿼터" in soccer


def test_odds_stage_is_not_recorded_without_odds_leagues():
    import ast
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1]
           / "app/pipeline.py").read_text(encoding="utf-8")
    i = src.index('await record("배당 수집"')
    assert "if active_keys:" in src[i - 400:i], "배당 계측이 무조건 실행된다"


def test_baseball_never_loads_h2h_market_probs():
    src = (ROOT / "app/pipeline.py").read_text(encoding="utf-8")
    assert "market_probs, best_odds = None, {}" in src
    fn = src[src.index("def _compute_picks"):src.index("picks_out.sort")]
    assert 'c.get("ev") is not None' not in fn
    assert 'c.get("p") is not None' in fn


@pytest.mark.asyncio
async def test_mlb_snapshot_drops_h2h_even_if_api_returns_it(db_pool):
    """요청 필터가 깨져도 적재 단계에서 h2h를 버린다."""
    from datetime import UTC, datetime, timedelta

    from app.collectors.odds import snapshot_odds

    now = datetime.now(UTC) + timedelta(days=1)
    gid = await db_pool.fetchval(
        "INSERT INTO games (sport, league, ext_id, starts_at, home, away) "
        "VALUES ('mlb', 'MLB', 'drop-h2h', $1, 'Home Nine', 'Away Nine') RETURNING id",
        now,
    )

    class Fake:
        mock = False
        last_headers: dict = {}

        async def fetch_odds(self, sport_key, markets=None):
            return [{
                "home_team": "Home Nine", "away_team": "Away Nine",
                "commence_time": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "bookmakers": [{"key": "dk", "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": "Home Nine", "price": 1.5},
                        {"name": "Away Nine", "price": 2.6}]},
                    {"key": "totals", "outcomes": [
                        {"name": "Over", "price": 1.91, "point": 8.5},
                        {"name": "Under", "price": 1.91, "point": 8.5},
                    ]},
                ]}],
            }]

    n = await snapshot_odds(db_pool, "mlb", client=Fake(), only_keys=["baseball_mlb"])
    assert n == 0
    markets = await db_pool.fetch(
        "SELECT market, line FROM odds_snapshots WHERE game_id = $1", gid)
    assert markets == []


@pytest.mark.asyncio
async def test_totals_line_numbers_ignore_price_and_integer_lines(db_pool):
    from datetime import UTC, datetime, timedelta

    from app.pipeline import _attach_alt_markets, _totals_line_numbers

    now = datetime.now(UTC) + timedelta(days=1)
    gid = await db_pool.fetchval(
        "INSERT INTO games (sport, league, ext_id, starts_at, home, away, status) "
        "VALUES ('mlb', 'MLB', 'lines-only', $1, 'H', 'A', 'scheduled') RETURNING id",
        now,
    )
    await db_pool.execute(
        "INSERT INTO odds_snapshots (game_id, book, market, side, line, odds) VALUES "
        "($1, 'dk', 'totals', 'Over', 8.5, 1.91),"
        "($1, 'dk', 'totals', 'Under', 8.5, 1.91),"
        "($1, 'dk', 'totals', 'Over', 9.0, 1.80),"
        "($1, 'dk', 'h2h', 'H', NULL, 1.70)",
        gid,
    )
    assert await _totals_line_numbers(db_pool, gid) == [8.5]
    jg = {"game_id": gid, "sport": "mlb", "status": "scheduled",
          "home": "H", "away": "A"}
    await _attach_alt_markets(db_pool, [jg])
    assert jg["alt_markets"] == []


def test_odds_formatters_and_value_line_tolerate_missing_price():
    """야구 승부는 배당이 없다. 렌더가 @None 으로 죽으면 안 된다."""
    from app.pipeline import _odds_slash, _odds_tag, _value_candidates, render_game_section

    assert _odds_tag(None) == ""
    assert _odds_tag(1.62) == " @1.62"
    assert _odds_slash(None) == ""
    lines = _value_candidates(
        {"market_board": [
            {"market": "h2h", "side": "H", "desc": "홈 승", "odds": None,
             "p": 0.64, "grade": "🟢", "approved": True},
        ], "home": "H", "away": "A"},
        "홈", "원정",
    )
    assert any("걸 만합니다" in x for x in lines)
    assert all("@None" not in x for x in lines)

    out = render_game_section({
        "game_id": 1, "sport": "mlb", "home": "H", "away": "A",
        "league": "MLB", "status": "scheduled", "starts_at_kst": "08/29 08:00",
        "best_odds": {},
        "research": {"home_recent_form": {"form": "WWL"},
                     "away_recent_form": {"form": "LWW"}},
        "pick_summary": {"side": "H", "desc": "홈 승", "odds": None,
                         "p_final": 0.60, "ev": None, "approved": True,
                         "axes": "실데이터+모델"},
        "market_board": [],
    })
    assert "대표 마켓: 홈 승" in out
    assert "@None" not in out
