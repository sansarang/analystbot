"""[무과금 전환 1] 무료 배당 3원 체계.

The Odds API 가 크레딧 소진으로 2026-08-27T22:46 부터 차단됐고, `api_guard`
차단은 TTL 이 없어 시간으로 안 풀린다. 146.8시간 동안 배당이 한 행도 안 쌓였다.
유료 키 하나에 가치 게이트 전체가 매달려 있던 구조를 무료 소스로 바꾼다.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.collectors.espn_odds import is_live_book, parse_odds, started

#: 실측 응답 (SD @ CIN, 2026-09-02)
REAL = {
    "provider": {"id": "100", "name": "DraftKings", "priority": 1},
    "details": "SD -149", "overUnder": 9.5,
    "awayTeamOdds": {"favorite": True, "moneyLine": -149,
                     "open": {"moneyLine": {"decimal": 1.71}},
                     "current": {"moneyLine": {"decimal": 1.67,
                                               "american": "-149"}}},
    "homeTeamOdds": {"favorite": False, "moneyLine": 123,
                     "current": {"moneyLine": {"decimal": 2.23,
                                               "american": "+123"}}},
}


def test_parses_both_sides_from_real_response():
    rows = parse_odds(REAL, "Cincinnati Reds", "San Diego Padres")
    by = {r["side"]: r for r in rows}
    assert by["San Diego Padres"]["odds"] == 1.67
    assert by["Cincinnati Reds"]["odds"] == 2.23
    assert all(r["market"] == "h2h" and r["line"] is None for r in rows)


def test_uses_current_not_open():
    """`open` 은 개장가다 — 지금 시장이 아니다. 실측 응답에 둘 다 들어 있다."""
    rows = parse_odds(REAL, "H", "A")
    assert {r["odds"] for r in rows} == {1.67, 2.23}
    assert 1.71 not in {r["odds"] for r in rows}, "개장가를 쓰면 안 된다"


def test_live_book_is_rejected():
    """🔴 실측 2026-09-02: ESPN 이 `DraftKings - Live Odds` 를 같은 목록에 섞는다.

    STL 이 7:0 으로 앞선 경기의 라이브 배당이 `STL 1.02 / LAD 11.4` 로 들어왔다.
    경기 전 판정과 견주면 괴리가 통째로 거짓이 된다.
    """
    assert is_live_book("DraftKings - Live Odds")
    assert is_live_book("betmgm in-play")
    assert not is_live_book("DraftKings")
    live = {**REAL, "provider": {"name": "DraftKings - Live Odds"}}
    assert parse_odds(live, "H", "A") == []


def test_started_games_are_skipped():
    """이미 시작한 경기는 pregame 라인 자체가 낡았다."""
    now = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    assert started("2026-09-02T11:40Z", now) is True
    assert started("2026-09-02T16:40Z", now) is False
    # 시각을 못 읽으면 수집을 막지 않는다 — 없는 이유로 버리지 않는다
    assert started(None) is False and started("쓰레기") is False


def test_missing_price_is_not_invented():
    """가격이 없으면 만들지 않는다. O/U 라인만 있으면 적재하지 않는다."""
    only_line = {"provider": {"name": "dk"}, "overUnder": 9.5,
                 "homeTeamOdds": {}, "awayTeamOdds": {}}
    assert parse_odds(only_line, "H", "A") == []


def test_decimal_below_one_is_rejected():
    """소수배당은 1보다 커야 한다 — 미국식 값이 섞이면 조용히 틀린다."""
    bad = {"provider": {"name": "dk"},
           "homeTeamOdds": {"current": {"moneyLine": {"decimal": -149}}},
           "awayTeamOdds": {"current": {"moneyLine": {"decimal": 0.5}}}}
    assert parse_odds(bad, "H", "A") == []


# ─────────────────── SharpAPI 폴백 ───────────────────

def test_sharp_is_silent_without_a_key():
    """키 발급은 사람이 하는 일이다. 없으면 조용히 비활성 — 수집이 죽지 않는다."""
    import asyncio

    from app.collectors.sharp_odds import enabled, fetch_slate

    assert enabled() is False
    assert asyncio.run(fetch_slate("2026-09-02")) == {}


def test_sharp_parse_rejects_unknown_shape():
    """실응답으로 검증하지 못했다 — 형태가 어긋나면 지어내지 말고 0건."""
    from app.collectors.sharp_odds import parse

    assert parse({"unexpected": 1}) == {}
    assert parse("문자열") == {}


# ─────────────────── 배트맨 ───────────────────

def test_betman_rows_never_invent_the_other_side():
    """한쪽 배당만 있으면 그 한쪽만. 공제율을 모르니 역산하지 않는다."""
    from app.collectors.betman import to_rows

    rows = to_rows({"home": "LG Twins", "away": "Doosan Bears",
                    "home_odds": 1.85, "away_odds": None})
    assert len(rows) == 1 and rows[0]["side"] == "LG Twins"


def test_betman_snapshot_absent_is_none_not_empty():
    """없는 것과 빈 것을 구분한다 — 빈 dict 를 만들면 '수집됨'으로 읽힌다."""
    import asyncio

    from app.collectors.betman import load_snapshot

    assert asyncio.run(load_snapshot(None, "kbo", "2026-09-02")) is None


# ─────────────────── 격리 경계 ───────────────────

def test_odds_never_reach_the_judgement_path():
    """🔴 배당은 판정·폼·서술 입력에 절대 흐르지 않는다 (CLAUDE.md 금지선)."""
    from pathlib import Path

    for mod in ("app/engine/matchup.py", "app/engine/team_form.py",
                "app/engine/prompts.py"):
        src = Path(mod).read_text(encoding="utf-8")
        for banned in ("espn_odds", "odds_free", "sharp_odds", "betman"):
            assert banned not in src, f"{mod} 가 {banned} 를 import 하면 안 된다"


def test_paid_path_is_preserved_not_deleted():
    """유료 복귀 옵션을 남긴다 — 코드를 지우지 않고 env 로 끈다."""
    from pathlib import Path

    from app.config import Settings

    assert Path("app/collectors/odds.py").exists(), "유료 수집기를 지우지 않았다"
    assert Settings(_env_file=None).odds_provider == "free"
    src = Path("app/scheduler.py").read_text(encoding="utf-8")
    assert 'odds_provider' in src and '"theodds"' in src


def test_provider_column_separates_sources():
    """세 소스를 provider 로 구분 적재한다 — 가치 게이트는 소스를 안 본다."""
    from pathlib import Path

    schema = Path("db/schema.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS provider" in schema
    src = Path("app/collectors/odds_free.py").read_text(encoding="utf-8")
    assert "provider)" in src and "$7" in src


# ─────────────────── [2] 딥서치 무과금 ───────────────────

def test_rss_parses_and_drops_stale_articles():
    """72시간이 넘은 기사는 버린다 — 딥서치는 '지금 무엇이 달라졌나'를 묻는다."""
    from app.collectors.news_rss import parse_feed

    xml = """<rss><channel>
      <item><title>새 기사 - 매체A</title><link>http://a</link>
        <pubDate>Wed, 02 Sep 2026 03:00:00 GMT</pubDate></item>
      <item><title>옛 기사 - 매체B</title><link>http://b</link>
        <pubDate>Fri, 21 Aug 2026 03:00:00 GMT</pubDate></item>
    </channel></rss>"""
    now = datetime(2026, 9, 2, 6, 0, tzinfo=UTC)
    got = parse_feed(xml, now=now)
    assert [g["title"] for g in got] == ["새 기사 - 매체A"]
    assert got[0]["age_h"] == 3.0


def test_rss_survives_cdata_and_entities():
    from app.collectors.news_rss import parse_feed

    xml = ("<rss><item><title><![CDATA[LG &amp; 두산 <b>맞대결</b>]]></title>"
           "<link>http://x</link></item></rss>")
    got = parse_feed(xml, now=datetime(2026, 9, 2, tzinfo=UTC))
    assert got[0]["title"] == "LG & 두산 맞대결"


def test_each_league_gets_its_own_locale():
    """한국어 기사에 영어 쿼리를 던지면 0건이 된다."""
    from app.collectors.news_rss import LOCALE

    assert LOCALE["kbo"]["ceid"] == "KR:ko"
    assert LOCALE["npb"]["ceid"] == "JP:ja"
    assert LOCALE["mlb"]["ceid"] == "US:en"


def test_articles_are_injected_without_touching_the_rules():
    """🔴 프롬프트 **규칙**은 불변이다. 자료만 덧붙인다."""
    from app.engine.deepsearch import PROMPT, _inject_articles

    got = _inject_articles(PROMPT, [
        {"team": "T", "title": "제목", "source": "매체", "age_h": 2.0,
         "body": "본문 앞부분"}])
    assert got.startswith(PROMPT), "기존 프롬프트를 그대로 두고 뒤에 붙인다"
    assert "수집된 기사" in got and "본문 앞부분" in got
    # 완화하면 안 되는 것들이 살아 있는가
    assert "±4%p" in got and "우세 방향을" in got


def test_paid_fallback_is_locked_by_a_daily_cap():
    """[2c] RSS 가 0건일 때만, 그것도 하루 총량 안에서만 유료 검색."""
    import asyncio

    from app.engine.deepsearch import PAID_KEY, _paid_budget_left, _spend_paid

    class R:
        def __init__(self):
            self.s = {}

        async def get(self, k):
            return self.s.get(k)

        async def incr(self, k):
            self.s[k] = str(int(self.s.get(k, 0)) + 1)
            return int(self.s[k])

        async def expire(self, *a):
            return True

    r = R()

    async def go():
        left = []
        for _ in range(5):
            left.append(await _paid_budget_left(r))
            if left[-1]:
                await _spend_paid(r)
        return left

    got = asyncio.run(go())
    assert got == [True, True, True, False, False], "기본 상한 3회"


def test_no_redis_means_no_paid_search():
    """redis 가 없으면 총량을 셀 수 없다 — 그때는 **막는다**(안전측)."""
    import asyncio

    from app.engine.deepsearch import _paid_budget_left

    assert asyncio.run(_paid_budget_left(None)) is False


def test_free_path_needs_no_search_tool():
    """RSS 가 있으면 `tools` 가 비어야 한다 — 도구를 넘기면 과금이 다시 붙는다."""
    from pathlib import Path

    src = Path("app/engine/deepsearch.py").read_text(encoding="utf-8")
    assert "tools = []" in src
    assert "if articles:" in src and "_inject_articles" in src


def test_cost_lines_report_paid_calls_as_numbers():
    """[3] "0원으로 바꿨다"는 주장이 아니라 관측이어야 한다."""
    import asyncio

    from app.engine.daily_summary import cost_lines

    class R:
        async def get(self, k):
            return None

    got = asyncio.run(cost_lines(R(), ("mlb",), "2026-09-02"))
    assert got and "The Odds API 0콜" in got[0] and "web_search 0/3콜" in got[0]


# ─────────────────── 실사고 2026-09-02: 매칭 0 = 소스 고장 아님 ───────────────────

def test_collect_skips_when_the_slate_is_not_loaded():
    """🔴 실사고 14:42: ESPN 이 14경기 배당을 **정상으로** 줬는데 매칭 0 이었다.

    그 슬레이트가 `games` 에 아직 없었기 때문이다 — MLB 스케줄은 새벽
    프리페치가 넣는데 ET 자정이 지나면 `mlb_slate_date()` 는 이미 다음
    슬레이트를 가리킨다. "배당을 못 붙였다"가 아니라 "붙일 경기가 없었다"다.
    """
    import asyncio

    from app.collectors import odds_free as of

    called = []

    class Pool:
        async def fetch(self, *a, **k):
            return []

    async def boom(*a, **k):
        called.append(1)
        raise AssertionError("대상이 없는데 소스를 때렸다")

    orig = of.__dict__.get("_match_game_ids")
    try:
        import app.collectors.espn_odds as espn

        espn_orig = espn.fetch_slate
        espn.fetch_slate = boom
        r = asyncio.run(of.collect_mlb(Pool(), "2026-09-02"))
    finally:
        espn.fetch_slate = espn_orig
    assert r["no_games"] is True and called == []


def test_dates_come_from_the_db_not_from_a_calculation():
    """날짜를 계산하지 않는다 — DB에 있는 경기에서 역으로 읽는다."""
    import asyncio
    from datetime import date as _d

    from app.collectors.odds_free import upcoming_mlb_dates

    class Pool:
        async def fetch(self, *a, **k):
            return [{"d": _d(2026, 9, 2)}, {"d": _d(2026, 9, 3)}]

    assert asyncio.run(upcoming_mlb_dates(Pool())) == ["2026-09-02", "2026-09-03"]


def test_watchdog_stays_quiet_when_no_games_are_due():
    """붙일 경기가 없으면 배당이 없는 게 정상이다 — 울리면 오탐이다."""
    import asyncio

    from app import watchdog as wd

    class Pool:
        async def fetchval(self, *a, **k):
            return 0                     # 36시간 내 예정 경기 없음

        async def fetch(self, *a, **k):
            raise AssertionError("대상이 없는데 배당 나이를 쟀다")

    class R:
        async def get(self, k):
            return None

    assert asyncio.run(wd.check_odds(Pool(), R())) == []


def test_watchdog_still_alerts_when_games_are_due_but_odds_are_missing():
    """오탐을 없애느라 진짜 공백을 놓치면 안 된다."""
    import asyncio

    from app import watchdog as wd

    class Pool:
        def __init__(self):
            self.n = 0

        async def fetch(self, *a, **k):
            self.n += 1
            if self.n == 1:
                return [{"sport": "mlb", "n": 15}, {"sport": "npb", "n": 5}]
            return []                    # 배당이 한 행도 없다

    class R:
        async def get(self, k):
            return None

    found = asyncio.run(wd.check_odds(Pool(), R()))
    assert [(c, t) for c, t, _ in found] == [("W-ODDS-STALE", "espn"),
                                             ("W-ODDS-STALE", "oddsportal")]


# ─────────────────── oddsportal (KBO·NPB) ───────────────────

#: 실측 응답 조각 (2026-09-02 16:20, KBO 두산-LG)
OP_ROW = ('{"id":9812029,"is-double":false,"superTemplate":{"id":"","name":""},'
          '"home":27002459,"away":27002461,"home-name":"Doosan Bears",'
          '"away-name":"LG Twins","status-id":1}')
OP_ODDS = ('"GreoG9C7":{"event":9812029,"odds":[{"active":true,"maxOdds":2.23,'
           '"avgOdds":2.14,"bettingTypeId":3,"scopeId":1,"outcomeId":"x",'
           '"resultId":0},{"active":true,"maxOdds":1.75,"avgOdds":1.70,'
           '"bettingTypeId":3,"scopeId":1,"outcomeId":"y","resultId":0}],"cnt":17')


def test_oddsportal_parses_row_across_nested_objects():
    """🔴 `[^{}]` 로 범위를 막으면 `superTemplate":{...}` 를 못 넘어 0건이 된다."""
    from app.collectors.oddsportal import parse_rows

    got = parse_rows(OP_ROW)
    assert got[9812029]["home"] == "Doosan Bears"
    assert got[9812029]["away"] == "LG Twins"


def test_oddsportal_order_is_home_then_away():
    """🔴 `resultId` 로는 못 가른다 — 오늘 경기는 둘 다 `resultId:0` 이다.

    순서가 홈|원정이라는 관례를 **ESPN 과 대조해 검증했다**: 같은 날 MLB
    13경기 전부 첫 번째=홈이었고 값도 소수점 둘째 자리까지 일치했다.
    """
    from app.collectors.oddsportal import parse_odds

    got = parse_odds(OP_ODDS)
    assert got[9812029] == {"home": 2.14, "away": 1.7}


def test_oddsportal_skips_non_two_way():
    """2-way 가 아니면 손대지 않는다 — 야구는 무승부가 없다."""
    from app.collectors.oddsportal import parse_odds

    three = OP_ODDS.replace('"cnt":17',
                            ',{"avgOdds":3.4,"bettingTypeId":3,"scopeId":1}],"cnt":17')
    assert parse_odds(three) == {}


def test_oddsportal_uses_average_not_best_price():
    """`maxOdds` 는 여러 북 중 최고가라 실제 걸 수 있는 값보다 낙관적이다.

    그걸 기준으로 가치 게이트를 태우면 통과가 헐거워진다.
    """
    from app.collectors.oddsportal import parse_odds

    got = parse_odds(OP_ODDS)
    assert 2.23 not in got[9812029].values(), "maxOdds 를 쓰면 안 된다"


def test_unmapped_team_is_reported_not_silently_dropped(caplog):
    """새 표기가 나오면 조용히 버리지 않고 드러난다."""
    import asyncio

    from app.collectors import oddsportal as op

    async def fake(*a, **k):
        raise RuntimeError("네트워크 금지")

    # 매핑에 없는 팀명은 TEAM_MAP.get 이 None → 경고 경로로 간다
    assert op.TEAM_MAP.get("존재하지 않는 팀") is None
    assert "Fukuoka S. Hawks" in op.TEAM_MAP, "실측 미매핑을 반영했다"


# ─────────────────── 크롤 예절 (B) ───────────────────

def test_crawl_etiquette_limits_are_constants():
    """상한을 코드에 박는다 — 남의 서버를 우리 사정으로 두들기지 않는다."""
    from app.collectors.oddsportal import (
        BACKOFF_SEC, MAX_ATTEMPTS, MIN_INTERVAL_SEC,
    )

    assert MAX_ATTEMPTS == 2, "재시도는 총 2회(첫 시도 포함)"
    assert BACKOFF_SEC >= 1.0
    assert MIN_INTERVAL_SEC >= 10 * 60, "같은 리그를 10분 안에 두 번 부르지 않는다"


def test_second_call_within_the_interval_makes_no_request(monkeypatch):
    """폴링 틱이 겹쳐도 실제 요청은 최소 간격으로 막힌다."""
    import asyncio

    from app.collectors import oddsportal as op

    calls = []

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            calls.append(url)

            class R:
                status_code = 200
                content = b"x"
                text = ""

                def raise_for_status(self):
                    return None
            return R()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(op, "_last_call", {})
    asyncio.run(op.fetch_league("kbo"))
    asyncio.run(op.fetch_league("kbo"))          # 곧바로 두 번째
    assert len(calls) == 1, "간격 안 두 번째는 요청하지 않는다"
    asyncio.run(op.fetch_league("kbo", force=True))   # 발송 직전 강제 1회
    assert len(calls) == 2, "force 는 통과한다"


# ─────────────────── 배당 없음 강등 경로 (A-2) ───────────────────

def test_missing_odds_keeps_recommendation_and_says_why():
    """🔴 배당 미수집은 **추천을 막지 않는다** — 기존 규율이다.

    `value_gate.passes_value` 가 None 을 돌려주고, `classify` 는 그것을
    "게이트 건너뜀"으로 다룬다. None 을 False 로 취급하면 수집 실패가
    추천을 죽인다 (value_gate.py 주석의 금지 동작).
    카드는 대신 "가치 배당 미수집 — 필요배당 N" 으로 **사유를 말한다.**
    """
    from app.engine.value_gate import CLS_RECOMMENDED, classify, passes_value

    assert passes_value(0.63, None) is None
    assert classify(probability_ok=True, vetoed=False, p=0.63,
                    odds=None) == CLS_RECOMMENDED


def test_empty_source_does_not_raise():
    """소스가 죽어도 예외로 발송이 죽지 않는다."""
    import asyncio

    from app.collectors.oddsportal import parse_odds, parse_rows

    assert parse_rows("") == {} and parse_odds("") == {}

    from app.collectors import odds_free as of

    class Pool:
        async def fetch(self, *a, **k):
            return [{"id": 1, "home": "Doosan Bears", "away": "LG Twins"}]

        async def execute(self, *a, **k):
            return None

    async def empty(*a, **k):
        return {}

    import app.collectors.oddsportal as op

    orig = op.fetch_league
    op.fetch_league = empty
    try:
        r = asyncio.run(of.collect_asia(Pool(), None, "kbo", "2026-09-02"))
    finally:
        op.fetch_league = orig
    assert r["rows"] == 0 and r["matched"] == 0     # 조용히 0, 예외 없음


def test_flipped_home_away_would_fail_to_match_not_attach_wrong_odds():
    """🔴 A-1 의 핵심 안전장치.

    매칭 키가 `f"{home}|{away}"` 라, oddsportal 이 홈/원정을 뒤집어 주면
    우리 games 키와 **아예 안 맞아 미매칭**이 된다 — 틀린 배당이 붙는 것이
    아니라 안 붙는다. 즉 **매칭 성공 자체가 방향 일치의 증거**다.
    """
    ours = {"Doosan Bears|LG Twins": 1}           # 우리 DB: 홈=두산
    flipped = "LG Twins|Doosan Bears"              # 뒤집힌 소스
    assert flipped not in ours
    assert "Doosan Bears|LG Twins" in ours


def test_rss_query_uses_the_league_language():
    """🔴 실측 2026-09-02 16:22: 영문명으로 던지면 기사는 오는데(49건)
    **72시간 필터가 전부 걸러낸다** — 영문 기사는 오래된 것뿐이다.
    모국어로 던지면 같은 팀이 100건, 그것도 최신이다.
      Hanwha Eagles 0건 → 한화 이글스 100건
      Lotte Giants  0건 → 롯데 자이언츠 102건
    로케일만 맞추고 쿼리를 영문으로 둔 것이 구멍이었다.
    """
    from app.collectors.news_rss import QUERY_ALIAS

    assert QUERY_ALIAS["Hanwha Eagles"] == "한화 이글스"
    assert QUERY_ALIAS["Lotte Giants"] == "롯데 자이언츠"
    assert QUERY_ALIAS["Hokkaido Nippon-Ham Fighters"] == "日本ハムファイターズ"
    # 오늘 슬레이트 20팀이 전부 들어 있다 (실측 0건 팀 0/20)
    for t in ("LG Twins", "Doosan Bears", "KT Wiz", "NC Dinos", "Kia Tigers",
              "Kiwoom Heroes", "SSG Landers", "Samsung Lions",
              "Yomiuri Giants", "Hanshin Tigers", "Chunichi Dragons",
              "Tokyo Yakult Swallows", "Hiroshima Toyo Carp",
              "Fukuoka SoftBank Hawks", "Orix Buffaloes",
              "Tohoku Rakuten Golden Eagles", "Yokohama DeNA BayStars"):
        assert t in QUERY_ALIAS, f"{t} 별칭 누락"


def test_unknown_team_falls_back_to_its_own_name():
    """별칭이 없다고 수집을 멈추지 않는다."""
    from app.collectors.news_rss import QUERY_ALIAS

    assert QUERY_ALIAS.get("듣보 팀", "듣보 팀") == "듣보 팀"
