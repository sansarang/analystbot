"""SAT-S1 — 축구 전용 인공위성 어댑터.

사용자 지시 2026-09-12: "단계별로 하자...우선 축구전용 인공위성을 만들어라"

🔴 왜 필요한가. 실측 2026-09-12: `satellite._ADAPTERS` 는 `{mlb, kbo, npb}`
   뿐이라 축구는 `gather` 가 **0 을 반환하고 끝난다**. v3 수집의 주력이
   위성인데(야구 경기당 12건) 축구는 그 축이 통째로 비어 있다.

🔴 **검색어를 실측으로 골랐다.** 같은 팀·같은 소스인데 검색어 한 단어로
   결과가 완전히 갈린다 — `横浜F・マリノス スタメン 負傷 出場停止 コンディション
   直近` 는 맥도날드·프로야구·연예 기사를 물어왔다(6건 전부 무관).

   측정(상위 8건 중 축구 기사 수):

     K리그1 · 다음   (팀명만) 39/40  ← 최선
                    K리그 선발  37 · 부상 결장 34 · 선발 라인업 32 · 라인업 30
     J1   · 야후    (팀명만)  8/8   ← 최선
                    검색어를 붙이면 다른 종목으로 샌다

   **야구와 반대다.** KBO 는 `_KBO_TERMS_LIST` 4개를 돌지만 축구는
   **팀명만이 가장 정확하다.** 그래서 상수를 따로 둔다.

⚠️ "축구 기사"인 것과 "오늘 이 경기 기사"인 것은 다르다. 야구도 33~67%였다.
   거르는 일은 2단계(제미니)가 한다 — 여기서 줄이려 하면 놓친다.
"""

import pytest

from app.collectors import satellite as SAT
# [SAT-S3] 축구는 제 파일로 나갔다 — 공용 검색은 여전히 `SAT` 에 있다.
from app.collectors import satellite_soccer as SOC


def _jg(league="K리그1", home="Ulsan Hyundai FC", away="FC Seoul"):
    return {"game_id": 1, "sport": "soccer", "league": league,
            "home": home, "away": away}


# ═══════════════ ① 어댑터가 등록돼 있다

def test_축구_어댑터가_등록돼_있다():
    """🔴 실측: `_ADAPTERS` 에 soccer 가 없어 `gather` 가 0 을 반환했다."""
    assert "soccer" in SAT._ADAPTERS
    assert SAT._ADAPTERS["soccer"] is SOC.gather_soccer


def test_기존_세_종목을_건드리지_않았다():
    """🔴 반대 위험 — 야구가 바뀌면 그게 P0 다."""
    assert SAT._ADAPTERS["kbo"] is SAT.gather_kbo
    assert SAT._ADAPTERS["npb"] is SAT.gather_npb
    assert SAT._ADAPTERS["mlb"] is SAT.gather_mlb


# ═══════════════ ② 검색어 — 실측대로 팀명만

def test_팀명만_검색한다():
    """🔴 실측 2026-09-12: 검색어를 붙이면 **떨어진다.**
    K리그1 팀명만 39/40 vs 라인업 30/40. J1 은 검색어를 붙이자 맥도날드·
    프로야구 기사가 왔다."""
    import inspect

    src = inspect.getsource(SOC.gather_soccer)
    assert "_SOCCER_TERMS" in src


def test_검색어_상수가_비어_있다():
    """야구(`_KBO_TERMS_LIST` 4개)와 **반대**다 — 그 근거가 주석에 있어야 한다."""
    assert SOC._SOCCER_TERMS == ""
    src = open("app/collectors/satellite_soccer.py", encoding="utf-8").read()
    i = src.index("_SOCCER_TERMS")
    assert "39" in src[i - 900:i + 300], "실측 근거가 없다"


# ═══════════════ ③ 리그로 소스를 가른다

@pytest.mark.asyncio
async def test_K리그1은_다음을_쓴다(monkeypatch):
    seen = []

    async def _daum(q):
        seen.append(q)
        return ""

    monkeypatch.setattr(SAT, "_daum_fetch", _daum)
    monkeypatch.setattr(SAT, "parse_daum_news", lambda h: [])
    await SOC.gather_soccer(_jg("K리그1"))
    assert seen, "다음 검색을 부르지 않았다"


@pytest.mark.asyncio
async def test_J1은_야후를_쓴다(monkeypatch):
    seen = []

    async def _yahoo(q):
        seen.append(q)
        return ""

    monkeypatch.setattr(SAT, "_yahoo_fetch", _yahoo)
    monkeypatch.setattr(SAT, "parse_yahoo_news", lambda h: [])
    await SOC.gather_soccer(_jg("J1 리그", "FC Machida Zelvia", "Urawa Red Diamonds"))
    assert seen, "야후 검색을 부르지 않았다"


@pytest.mark.asyncio
async def test_소스가_없는_리그는_빈손이고_로그를_남긴다(caplog):
    """🔴 **조용한 0 금지.** 화이트리스트 밖 리그(리그앙·브라질 등)는 소스가
    없다 — 없다고 말해야 "소스가 없다"와 "긁었는데 0건"을 가를 수 있다.

    ⚠️ [SAT-S2] 종전에는 EPL 로 시험했는데 이제 EPL 은 지원된다.
       그대로 뒀다면 이 계약이 **실제 HTTP 를 때리면서 통과**했을 것이다.
    """
    import logging

    with caplog.at_level(logging.INFO):
        out = await SOC.gather_soccer(_jg("리그앙", "Paris SG", "Lyon"))
    assert out == []
    assert any("리그앙" in r.getMessage() for r in caplog.records), caplog.text


# ═══════════════ ④ 팀 이름 — 별칭이 없으면 영어 그대로, 그리고 센다

def test_한국어_별칭을_쓴다():
    """DB 는 영어로 저장한다(`Ulsan Hyundai FC`). 다음 검색은 한국어다."""
    assert SOC.soccer_query("Ulsan Hyundai FC") == "울산 HD"
    assert SOC.soccer_query("FC Seoul") == "FC서울"


def test_일본어_별칭을_쓴다():
    assert SOC.soccer_query("FC Machida Zelvia") == "FC町田ゼルビア"


def test_별칭이_없으면_영어_그대로_쓴다():
    """🔴 **버리지 않는다.** 영어로도 뭔가 나올 수 있고, 0 으로 만들면
    그 팀은 영영 재료가 없다."""
    assert SOC.soccer_query("Unknown United") == "Unknown United"


@pytest.mark.asyncio
async def test_별칭이_없으면_로그로_센다(caplog, monkeypatch):
    """🔴 커버리지를 모르면 별칭표를 언제 늘려야 하는지 알 수 없다."""
    import logging

    async def _daum(q):
        return ""

    monkeypatch.setattr(SAT, "_daum_fetch", _daum)
    monkeypatch.setattr(SAT, "parse_daum_news", lambda h: [])
    with caplog.at_level(logging.INFO):
        await SOC.gather_soccer(_jg("K리그1", "Unknown United", "FC Seoul"))
    assert any("별칭" in r.getMessage() for r in caplog.records), caplog.text


# ═══════════════ ⑤ 기사 모양 — 새 계약을 만들지 않는다

@pytest.mark.asyncio
async def test_기사_모양이_주입_계약을_지킨다(monkeypatch):
    """🔴 원본은 `satellite._article` 이다 — 키를 손으로 늘리지 않는다."""
    async def _daum(q):
        return "<html/>"

    monkeypatch.setattr(SAT, "_daum_fetch", _daum)
    monkeypatch.setattr(SAT, "parse_daum_news",
                        lambda h: [{"url": "https://e.com/1", "title": "제목"}])

    async def _body(u):
        return "본문"

    monkeypatch.setattr(SAT, "_fetch_article_body", _body)
    out = await SOC.gather_soccer(_jg("K리그1"))
    assert out
    for k in ("title", "url", "source", "team", "body"):
        assert k in out[0], k
    assert out[0]["team"] in ("Ulsan Hyundai FC", "FC Seoul")


@pytest.mark.asyncio
async def test_같은_기사를_두_번_싣지_않는다(monkeypatch):
    async def _daum(q):
        return "<html/>"

    monkeypatch.setattr(SAT, "_daum_fetch", _daum)
    monkeypatch.setattr(SAT, "parse_daum_news",
                        lambda h: [{"url": "https://e.com/same", "title": "제목"}])

    async def _body(u):
        return "본문"

    monkeypatch.setattr(SAT, "_fetch_article_body", _body)
    out = await SOC.gather_soccer(_jg("K리그1"))
    assert len(out) == 1, "양 팀 검색에서 같은 url 이 두 번 실렸다"


@pytest.mark.asyncio
async def test_한_팀이_터져도_나머지가_산다(monkeypatch, caplog):
    calls = {"n": 0}

    async def _daum(q):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("터졌다")
        return "<html/>"

    monkeypatch.setattr(SAT, "_daum_fetch", _daum)
    monkeypatch.setattr(SAT, "parse_daum_news",
                        lambda h: [{"url": "https://e.com/2", "title": "제목"}])

    async def _body(u):
        return "본문"

    monkeypatch.setattr(SAT, "_fetch_article_body", _body)
    out = await SOC.gather_soccer(_jg("K리그1"))
    assert len(out) == 1


# ═══════════════ ⑥ 정찰 스위치

def test_위성_대상에_축구가_있다():
    """🔴 어댑터만 만들고 아무도 안 부르면 없는 것과 같다(PGP-2).

    ⚠️ **레버를 틀리면 안 된다.** `ScoutSport.active` 는 정찰
       (`engine/scout.observe_slate`) 스위치이고 위성과 **다른 축**이다.
       처음에 그쪽을 켰다가 `test_every_active_scout_sport_has_a_call_site`
       에 잡혔다 — 스케줄러에 축구 정찰 호출부가 없다.
       위성을 켜는 것은 `satellite_sports` 다(`scheduler.satellite_job`).
    """
    from app.config import Settings

    d = Settings.model_fields["satellite_sports"].default
    assert "soccer" in d, d
    for keep in ("mlb", "kbo", "npb"):
        assert keep in d, f"{keep} 가 빠졌다"


def test_정찰_스위치는_건드리지_않았다():
    """🔴 반대 위험 — 정찰을 켜면 호출부 없는 종목이 생긴다."""
    from app.registry import scout_sport

    sc = scout_sport("soccer")
    assert sc is not None and sc.active is False
    assert sc.reason, "이유 없는 비활성은 다음 사람이 켜 본다"


# ═══════════════ SAT-S2 — 전 리그 + 토르 보강

def test_프로그램의_모든_축구_리그가_위성에_있다():
    """사용자 지시 2026-09-12: "j리그 k리그 국한하지 말고 내 프로그램에 있는
    전 리그를 인공위성에 추가해라".

    🔴 리그 목록의 원본은 `app/leagues.py` 다 — 여기 손으로 적지 않는다.
    """
    from app.leagues import LEAGUES

    labels = {cfg["label"] for cfg in LEAGUES.values()}
    missing = labels - set(SOC._SOCCER_SOURCE)
    assert not missing, f"위성 소스가 없는 리그: {missing}"


def test_유럽은_다음_한국어로_긁는다():
    """🔴 실측 2026-09-12(상위 8건 중 축구 기사): 한국 언론이 유럽 축구를
    두껍게 다룬다 — EPL 33/40 · 라리가 33/40 · 분데스리가 32/40 ·
    세리에A 30/40 · 덴마크 27/40. 다음 하나로 여섯 리그가 된다."""
    for lg in ("EPL", "라리가", "세리에A", "분데스리가", "덴마크 수페르리가"):
        assert SOC._SOCCER_SOURCE[lg] == "daum", lg
    assert SOC._SOCCER_SOURCE["J1 리그"] == "yahoo", "J1 은 일본어가 정확하다"


def test_별칭표가_DB의_팀을_덮는다():
    """🔴 실측: 영어 이름으로는 다음 검색이 거의 안 나온다
    (Arsenal FC 0/8 · SSC Napoli 0/8 · Brondby IF 0/8, 한국어는 7·7·6).
    별칭이 없으면 그 팀은 사실상 재료가 0 이다."""
    need = {
        "EPL": ["Arsenal FC", "Chelsea FC", "Liverpool FC", "Manchester City"],
        "라리가": ["Real Madrid CF", "FC Barcelona", "Sevilla FC"],
        "세리에A": ["Juventus FC", "AC Milan", "SSC Napoli"],
        "분데스리가": ["FC Bayern München", "Borussia Dortmund"],
        "덴마크 수페르리가": ["Brondby IF", "FC Midtjylland"],
        "K리그1": ["Ulsan Hyundai FC", "FC Seoul"],
        "J1 리그": ["FC Machida Zelvia"],
    }
    for lg, teams in need.items():
        for t in teams:
            assert t in SOC.SOCCER_ALIAS, f"{lg} {t} 별칭 없음"


def test_별칭이_영어_이름과_다르다():
    """별칭표에 영어를 그대로 적어 두면 폴백과 구분이 안 된다."""
    for en, alias in SOC.SOCCER_ALIAS.items():
        assert alias != en, en


# ── 토르 보강 (고급 검색)

def test_토르_보강을_부른다():
    """🔴 사용자 지적 2026-09-12: "고급 서치 기능이 있다".
    `tor_search` 는 토르 경유 DDG 다 — MLB·NPB 는 이미 쓰는데 축구는 안 썼다.

    실측: 질이 높다 — "Chelsea vs Hull: predicted lineup, confirmed team news,
    injury/suspension list" 가 한 기사에 다 들어 있다.
    """
    import inspect

    assert "_tor_supplement" in inspect.getsource(SOC.gather_soccer)


def test_토르_질의가_영어다():
    """🔴 한국어는 토르로 보내지 않는다 — 한국 사이트가 출구노드에 깨진다
    (`tor_search.is_tor_safe_query` 가 거부). 영어 꼬리를 붙인다."""
    from app.collectors.tor_search import is_tor_safe_query

    assert is_tor_safe_query(SOC._SOCCER_TOR_TAIL)
    for w in ("injury", "lineup"):
        assert w in SOC._SOCCER_TOR_TAIL


def test_토르는_보강이지_주력이_아니다():
    """🔴 실측 2026-09-12: DDG 는 연속 질의에 403 을 준다. 15초를 띄워도
    1/3 만 통과했다. 경기당 질의를 늘리면 전부 막힌다."""
    import inspect

    src = inspect.getsource(SOC.gather_soccer)
    # ⚠️ [SAT-S3] 첫 `_tor_supplement` 는 **임포트 줄**이다(공용 함수를 함수
    #    안에서 가져온다). 실측 주석이 붙은 곳은 **호출부**다.
    i = src.index("out += await _tor_supplement")
    assert "403" in src[i - 900:i], "속도 제한 실측이 주석에 없다"
    # 팀당 1질의 = 경기당 2질의
    assert src[i:i + 400].count('for side in ("home", "away")') == 1


def test_지원_목록을_로그에_손으로_적지_않는다():
    """🔴 사본 드리프트 — 리그가 늘면 로그만 옛것이 된다.
    실제로 그럴 뻔했다: SAT-S1 의 로그가 "K리그1·J1 만 지원" 이었고
    SAT-S2 에서 일곱 리그가 됐는데 문구는 그대로였다."""
    import inspect

    src = inspect.getsource(SOC.gather_soccer)
    i = src.index("위성 소스가 없다")
    assert "_SOCCER_SOURCE" in src[i:i + 400], "지원 목록을 원본에서 만들지 않는다"
    assert "K리그1·J1 만" not in src
