"""[위성 Phase1] 계약 테스트 — 태어나는 날 함께.

위성은 **수집기**다. DB에 없는 경기 정보를 미리 긁어 캐시에 쌓고, 딥서치가
그 캐시를 읽는다. 이 테스트가 잠그는 것:

- 어댑터 산출 dict 가 `_inject_articles`(deepsearch.py) 가 읽는 키를 전부 갖는다
  (모양 계약 — 하나라도 빠지면 판정 경로에서 조용히 렌더가 깨진다).
- transactions 는 **그 경기 두 팀** 것만 남는다 (지금 RSS 의 76% 오라벨을 반복하지
  않는다 — 마이너 팀·상대 밖 팀은 버린다).
- 재료가 없으면 빈 리스트로 안전하게 끝난다 (조용한 0 금지 — 크래시하지 않는다).
- 캐시 왕복: `gather` 가 쓴 것을 `read_cache` 가 그대로 돌려준다.
"""
from __future__ import annotations

import pytest

from app.collectors import satellite


# _inject_articles(deepsearch.py) 가 실제로 읽는 키. 원본이 바뀌면 여기서 깨져야 한다.
_SHAPE_KEYS = ("title", "source", "age_h", "team", "body")


_SAMPLE_TX = {
    "transactions": [
        {"id": 1, "person": {"id": 11, "fullName": "Kyle Karros"},
         "typeCode": "SC", "typeDesc": "Status Change",
         "description": "Colorado Rockies activated 3B Kyle Karros from the 7-day injured list.",
         "date": "2026-09-07", "fromTeam": None,
         "toTeam": {"id": 115, "name": "Colorado Rockies"}},
        {"id": 2, "person": {"id": 22, "fullName": "Someone Else"},
         "typeCode": "REL", "typeDesc": "Released",
         "description": "ACL Brewers released OF Someone Else.",
         "date": "2026-09-07", "fromTeam": None,
         "toTeam": {"id": 406, "name": "ACL Brewers"}},
        {"id": 3, "person": {"id": 33, "fullName": "Trade Guy"},
         "typeCode": "TR", "typeDesc": "Trade",
         "description": "San Francisco Giants traded RHP Trade Guy to Colorado Rockies.",
         "date": "2026-09-08",
         "fromTeam": {"id": 137, "name": "San Francisco Giants"},
         "toTeam": {"id": 115, "name": "Colorado Rockies"}},
    ]
}


def test_transactions_filtered_to_game_teams():
    """경기가 SF@COL 이면 COL·SF 관련 트랜잭션만 남고 ACL Brewers 는 버린다."""
    teams = {"Colorado Rockies", "San Francisco Giants"}
    arts = satellite.transactions_to_articles(_SAMPLE_TX["transactions"], teams)
    descs = [a["title"] for a in arts]
    assert any("Kyle Karros" in d for d in descs)          # COL 활성화
    assert any("traded RHP Trade Guy" in d for d in descs)  # SF↔COL 트레이드
    assert not any("ACL Brewers" in d for d in descs)       # 마이너 팀 — 버린다
    assert len(arts) == 2


def test_article_shape_matches_inject_contract():
    """산출 dict 는 _inject_articles 가 읽는 키를 전부 가진다."""
    teams = {"Colorado Rockies", "San Francisco Giants"}
    arts = satellite.transactions_to_articles(_SAMPLE_TX["transactions"], teams)
    assert arts
    for a in arts:
        for k in _SHAPE_KEYS:
            assert k in a, f"기사 dict 에 {k} 키가 없다 — 판정 경로에서 렌더가 깨진다"
        assert a["body"], "본문이 비면 RSS 의 0% 본문 문제를 반복하는 것이다"
        assert a["team"] in teams


def test_empty_transactions_safe():
    """재료가 없으면 빈 리스트 — 크래시하지 않는다."""
    assert satellite.transactions_to_articles([], {"Colorado Rockies"}) == []
    assert satellite.transactions_to_articles(
        _SAMPLE_TX["transactions"], set()) == []


def test_duplicate_transactions_deduped():
    """🔴 실측 2026-09-09: statsapi 가 같은 이벤트를 중복 행으로 준다
    (Riley Greene 재활·Tommy Pham 트레이드가 각각 두 번). 같은 문장을 요약기에
    두 번 먹이지 않도록 description 으로 중복을 없앤다."""
    dup = {"typeCode": "SC", "description": "Colorado Rockies activated 3B Kyle Karros from the 7-day injured list.",
           "date": "2026-09-07", "toTeam": {"id": 115, "name": "Colorado Rockies"}}
    txs = [dict(dup, id=1), dict(dup, id=2)]   # 같은 문장, 다른 id
    arts = satellite.transactions_to_articles(txs, {"Colorado Rockies"})
    assert len(arts) == 1, "같은 이벤트 중복이 제거되지 않았다"


class _MemRedis:
    def __init__(self):
        self.store: dict = {}

    async def set(self, k, v, nx=False, ex=None):
        self.store[k] = v
        return True

    async def get(self, k):
        return self.store.get(k)

    async def expire(self, k, sec):
        return True


class _FakeMLB:
    def __init__(self, payload):
        self._payload = payload

    async def fetch_transactions(self, start, end):
        return self._payload


@pytest.mark.asyncio
async def test_gather_writes_and_read_cache_roundtrips():
    """gather 가 캐시에 쓰고, read_cache 가 그대로 돌려준다."""
    r = _MemRedis()
    jg = {"sport": "mlb", "game_id": 999,
          "home": "Colorado Rockies", "away": "San Francisco Giants"}
    n = await satellite.gather(jg, r, client=_FakeMLB(_SAMPLE_TX))
    assert n == 2
    got = await satellite.read_cache(r, "mlb", 999)
    assert len(got) == 2
    assert all(k in got[0] for k in _SHAPE_KEYS)


@pytest.mark.asyncio
async def test_read_cache_empty_when_absent():
    """캐시가 없으면 빈 리스트 — 딥서치는 news_rss 로 폴백한다(회귀 없음)."""
    r = _MemRedis()
    assert await satellite.read_cache(r, "mlb", 12345) == []


@pytest.mark.asyncio
async def test_gather_empty_still_writes_marker():
    """재료 0건이어도 gather 는 크래시하지 않고 0을 돌려준다(조용한 0 금지)."""
    r = _MemRedis()
    jg = {"sport": "mlb", "game_id": 7, "home": "X Team", "away": "Y Team"}
    n = await satellite.gather(jg, r, client=_FakeMLB({"transactions": []}))
    assert n == 0


# ── 증분 1b: run_satellite (대상 경기 선정 + 컷오프) ──────────────────────

from datetime import datetime, timedelta, timezone


class _FakePool:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, sql, *args):
        return self._rows


def _row(gid, sport, home, away, mins_ahead, now):
    return {"id": gid, "sport": sport, "home": home, "away": away,
            "starts_at": now + timedelta(minutes=mins_ahead)}


@pytest.mark.asyncio
async def test_run_satellite_gathers_due_games_and_skips_cutoff():
    """컷오프(T-N) 안에 든 경기는 더 긁지 않는다 — 위성이 정지한다."""
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    rows = [
        _row(1, "mlb", "Colorado Rockies", "San Francisco Giants", 300, now),  # 5h 전 → 수집
        _row(2, "mlb", "X Team", "Y Team", 5, now),                            # T-5분 → 정지
    ]
    r = _MemRedis()
    out = await satellite.run_satellite(
        _FakePool(rows), r, sports=["mlb"], now=now,
        cutoff_min=10, client=_FakeMLB(_SAMPLE_TX))
    assert out["games"] == 1                    # 컷오프 안 경기는 셈에서 빠진다
    assert await satellite.read_cache(r, "mlb", 1)   # 대상 경기는 캐시가 찼다
    assert await satellite.read_cache(r, "mlb", 2) == []  # 정지 경기는 안 긁었다


@pytest.mark.asyncio
async def test_run_satellite_no_adapter_sport_noop():
    """어댑터 없는 종목(kbo)은 지금은 건너뛴다 — 크래시하지 않는다."""
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    rows = [_row(9, "kbo", "한화 이글스", "LG 트윈스", 200, now)]
    r = _MemRedis()
    out = await satellite.run_satellite(
        _FakePool(rows), r, sports=["kbo"], now=now, client=_FakeMLB(_SAMPLE_TX))
    assert out["gathered"] == 0


# ── 증분 2: 딥서치가 위성 캐시를 읽는다 (SAT-3) ───────────────────────────

_SAT_ITEM = {"title": "Colorado Rockies activated 3B Kyle Karros from the 7-day injured list.",
             "url": "https://www.mlb.com/player/11", "source": "MLB Transactions",
             "team": "Colorado Rockies", "age_h": 24.0,
             "body": "Colorado Rockies activated 3B Kyle Karros from the 7-day injured list."}


# ── 증분 6: NPB 어댑터 (야후재팬 뉴스검색) ───────────────────────────────

_YAHOO_HTML = '''
<a href="https://news.yahoo.co.jp/articles/aaaa1111bbbb2222" class="x">【西武】菅井信也が5月以来の1軍先発へ</a>
<a href="https://news.yahoo.co.jp/articles/aaaa1111bbbb2222">サムネ</a>
<a href="https://news.yahoo.co.jp/articles/cccc3333dddd4444">西武 桑原が右脚負傷で登録抹消の見込み</a>
'''


def test_parse_yahoo_news_dedups():
    """야후 검색: 같은 기사가 여러 번 링크된다. URL 중복 제거·최장 제목."""
    from app.collectors import satellite
    items = satellite.parse_yahoo_news(_YAHOO_HTML)
    assert len({i["url"] for i in items}) == 2
    first = [i for i in items if "aaaa1111" in i["url"]][0]
    assert "菅井" in first["title"] and first["title"] != "サムネ"


@pytest.mark.asyncio
async def test_gather_npb_shape_and_team(monkeypatch):
    """NPB 어댑터가 야후 결과를 news_rss 모양으로 정규화하고 팀을 붙인다."""
    from app.collectors import satellite

    async def fake_yahoo(query):
        return _YAHOO_HTML

    async def fake_body(url):
        return "本文 " + url[-6:]

    monkeypatch.setattr(satellite, "_yahoo_fetch", fake_yahoo)
    monkeypatch.setattr(satellite, "_fetch_article_body", fake_body)
    jg = {"sport": "npb", "game_id": 4783,
          "home": "Orix Buffaloes", "away": "Saitama Seibu Lions"}
    arts = await satellite.gather_npb(jg)
    assert arts
    for a in arts:
        for k in _SHAPE_KEYS:
            assert k in a
        assert a["team"] in ("Orix Buffaloes", "Saitama Seibu Lions")
        assert a["body"]


@pytest.mark.asyncio
async def test_tor_supplement_respects_flag(monkeypatch):
    """satellite_tor_enabled 가 게이트한다 — 꺼지면 호출조차 안 하고, 켜지면 부른다.
    (기본값은 2026-09-09 사용자 지시로 True 지만, 이 테스트는 default 와 무관하게
    게이트 동작을 잠근다.)"""
    from app.collectors import satellite, tor_search
    import app.config as cfg

    called = {"tor": False}

    async def spy_search(q, **kw):
        called["tor"] = True
        return []

    monkeypatch.setattr(tor_search, "search", spy_search)

    class _Off:
        satellite_tor_enabled = False

    monkeypatch.setattr(cfg, "get_settings", lambda: _Off())
    out = await satellite._tor_supplement({"home": "A", "away": "B"}, [("A", "A injury")])
    assert out == [] and called["tor"] is False    # 꺼짐 → 호출 안 함

    class _On:
        satellite_tor_enabled = True

    monkeypatch.setattr(cfg, "get_settings", lambda: _On())
    await satellite._tor_supplement({"home": "A", "away": "B"}, [("A", "A injury")])
    assert called["tor"] is True                    # 켜짐 → 호출함


@pytest.mark.asyncio
async def test_gather_dispatches_npb(monkeypatch):
    """gather 디스패처가 npb 를 NPB 어댑터로 보낸다."""
    from app.collectors import satellite

    async def fake_yahoo(query):
        return _YAHOO_HTML

    async def fake_body(url):
        return "本文"

    monkeypatch.setattr(satellite, "_yahoo_fetch", fake_yahoo)
    monkeypatch.setattr(satellite, "_fetch_article_body", fake_body)
    r = _MemRedis()
    jg = {"sport": "npb", "game_id": 4783,
          "home": "Orix Buffaloes", "away": "Saitama Seibu Lions"}
    n = await satellite.gather(jg, r)
    assert n > 0
    assert await satellite.read_cache(r, "npb", 4783)


@pytest.mark.asyncio
async def test_free_articles_prefers_satellite(monkeypatch):
    """위성 캐시에 재료가 있으면 그것을 쓰고, RSS 는 부르지 않는다."""
    from app.engine import deepsearch
    from app.collectors import news_rss, satellite as sat_mod

    called = {"rss": False}

    async def fake_read_cache(redis, sport, gid):
        return [dict(_SAT_ITEM)]

    async def fake_for_game(jg, redis):
        called["rss"] = True
        return [{"title": "x", "url": "y", "source": "z", "age_h": 1.0, "team": "t"}]

    monkeypatch.setattr(sat_mod, "read_cache", fake_read_cache)
    monkeypatch.setattr(news_rss, "for_game", fake_for_game)
    jg = {"sport": "mlb", "game_id": 1,
          "home": "Colorado Rockies", "away": "San Francisco Giants"}
    arts = await deepsearch._free_articles(jg, None)
    assert arts and arts[0]["source"] == "MLB Transactions"
    assert arts[0]["body"], "위성 재료는 본문이 이미 채워져 있어야 한다"
    assert called["rss"] is False, "위성이 있으면 RSS 를 부르지 않는다"


# ── 증분 5: KBO 어댑터 (다음 뉴스검색) ───────────────────────────────────

_DAUM_HTML = '''
<ul><li class="c-item"><div class="item-title">
  <a href="http://v.daum.net/v/20260909180837574" class="tit-g">3</a>
  <a href="http://v.daum.net/v/20260909180837574" class="tit_main">'대만 초대형 변수' 왕옌청, 한국전 선발?</a>
  <a href="http://v.daum.net/v/20260909180837574">투수가 아닌 대만의 에이스 역할이 부상으로</a>
</div></li>
<li class="c-item"><div class="item-title">
  <a href="http://v.daum.net/v/20260909133000000" class="tit_main">한화 문현빈 결장, 라인업 변경</a>
</div></li></ul>
'''


def test_parse_daum_news_dedups_by_url_keeps_longest_title():
    """다음 검색: 같은 기사가 썸네일·제목·요약으로 3번 링크된다. URL 중복 제거,
    제목은 가장 긴 앵커텍스트('3' 같은 배지는 버린다)."""
    from app.collectors import satellite
    items = satellite.parse_daum_news(_DAUM_HTML)
    urls = {i["url"] for i in items}
    assert len(urls) == 2                       # 중복 제거
    first = [i for i in items if "20260909180837574" in i["url"]][0]
    assert "왕옌청" in first["title"]            # 배지 '3' 이 아니라 진짜 제목
    assert first["title"] != "3"


def test_daum_age_from_url_timestamp():
    """v.daum.net URL 에 박힌 시각(KST)으로 나이를 잰다."""
    from datetime import datetime, timezone
    from app.collectors import satellite
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)  # = 21:00 KST
    age = satellite._daum_age_h("http://v.daum.net/v/20260909180837574", now)
    assert age is not None and 2.5 < age < 3.5   # 18:08 KST → 약 3시간 전


def test_kbo_title_mentions_team():
    """🔴 [SAT-12 실측 2026-09-09] 다음검색은 팀 쿼리에 KBO 일반 기사를 섞어 준다.
    36건 중 5건(14%)이 딴 팀 기사였다 — 키움@두산 경기에 롯데 결장 기사가 재료로
    들어갔다. 제목에 그 팀이 없으면 버린다(별칭 전체 또는 앞토큰으로 판정)."""
    from app.collectors import satellite

    assert satellite._mentions_team("삼성 라이온즈 외야수 김지찬이 결장", "Samsung Lions")
    assert satellite._mentions_team("KT 위즈 이강철 감독은", "KT Wiz")      # 앞토큰 'KT'
    assert satellite._mentions_team("LG는 18일부터 잠실구장에서", "LG Twins")  # 축약 'LG'
    # 딴 팀 기사 — 버려야 한다
    assert not satellite._mentions_team(
        "김태형 롯데 자이언츠 감독은 12일 잠실에서", "Kiwoom Heroes")
    assert not satellite._mentions_team("", "Samsung Lions")


@pytest.mark.asyncio
async def test_gather_kbo_drops_other_team_articles(monkeypatch):
    """딴 팀 기사는 캐시에 넣지 않는다 — 판정이 엉뚱한 근거로 움직이지 않게."""
    from app.collectors import satellite

    html = (
        '<a href="http://v.daum.net/v/20260909180000000">한화 이글스 문현빈 결장</a>'
        '<a href="http://v.daum.net/v/20260909170000000">롯데 자이언츠 손성빈 말소</a>'
    )

    async def fake_daum(query):
        return html

    async def fake_body(url):
        return "본문"

    monkeypatch.setattr(satellite, "_daum_fetch", fake_daum)
    monkeypatch.setattr(satellite, "_fetch_article_body", fake_body)
    from datetime import datetime, timezone
    jg = {"sport": "kbo", "game_id": 1, "home": "한화 이글스", "away": "LG 트윈스"}
    arts = await satellite.gather_kbo(jg, now=datetime(2026, 9, 9, 12, tzinfo=timezone.utc))
    titles = [a["title"] for a in arts]
    assert any("한화" in t for t in titles)
    assert not any("롯데" in t for t in titles), "딴 팀 기사가 재료로 들어갔다"


@pytest.mark.asyncio
async def test_gather_kbo_shape_and_team(monkeypatch):
    """KBO 어댑터가 다음 결과를 news_rss 모양으로 정규화하고 팀을 붙인다."""
    from datetime import datetime, timezone
    from app.collectors import satellite

    async def fake_daum(query):
        return _DAUM_HTML

    async def fake_body(url):
        return "본문 " + url[-6:]

    monkeypatch.setattr(satellite, "_daum_fetch", fake_daum)
    monkeypatch.setattr(satellite, "_fetch_article_body", fake_body)
    jg = {"sport": "kbo", "game_id": 1, "home": "한화 이글스", "away": "LG 트윈스"}
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    arts = await satellite.gather_kbo(jg, now=now)
    assert arts
    for a in arts:
        for k in _SHAPE_KEYS:
            assert k in a
        assert a["team"] in ("한화 이글스", "LG 트윈스")
        assert a["body"]


@pytest.mark.asyncio
async def test_gather_dispatches_kbo(monkeypatch):
    """gather 디스패처가 kbo 를 KBO 어댑터로 보낸다(캐시 적재까지).

    🔴 [2026-09-12] `now` 를 **반드시 고정한다.** 종전에는 실제 시각을 썼는데
       `_DAUM_HTML` 의 기사 날짜가 2026-09-09 로 고정이라, 실행 시각이
       `news_rss.MAX_AGE_HOURS` 를 넘기는 순간 기사가 전부 걸러져 0건이 됐다.
       실측: 오전 스위트는 통과(3211 passed)했고 오후 13:5x 에 같은 코드가
       실패했다 — 코드가 아니라 **시계가 바꾼 실패**다.
       바로 위 `test_gather_kbo_shape` 는 이미 `now` 를 넣고 있었다.
    """
    from app.collectors import satellite

    async def fake_daum(query):
        return _DAUM_HTML

    async def fake_body(url):
        return "본문"

    monkeypatch.setattr(satellite, "_daum_fetch", fake_daum)
    monkeypatch.setattr(satellite, "_fetch_article_body", fake_body)
    r = _MemRedis()
    jg = {"sport": "kbo", "game_id": 55, "home": "한화 이글스", "away": "LG 트윈스"}
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    n = await satellite.gather(jg, r, now=now)
    assert n > 0
    assert await satellite.read_cache(r, "kbo", 55)


@pytest.mark.asyncio
async def test_free_articles_falls_back_to_rss(monkeypatch):
    """위성 캐시가 비면 기존 RSS 경로로 폴백 — 회귀 없음."""
    from app.engine import deepsearch
    from app.collectors import news_rss, satellite as sat_mod

    async def empty_cache(redis, sport, gid):
        return []

    async def fake_for_game(jg, redis):
        return [{"title": "폴백 기사", "url": "https://x", "source": "s",
                 "age_h": 2.0, "team": jg["home"]}]

    async def fake_body(url):
        return "폴백 본문"

    monkeypatch.setattr(sat_mod, "read_cache", empty_cache)
    monkeypatch.setattr(news_rss, "for_game", fake_for_game)
    monkeypatch.setattr(deepsearch, "_fetch_body", fake_body)
    jg = {"sport": "kbo", "game_id": 5, "home": "한화 이글스", "away": "LG 트윈스"}
    arts = await deepsearch._free_articles(jg, None)
    assert arts and arts[0]["title"] == "폴백 기사"
    assert arts[0]["body"] == "폴백 본문"
