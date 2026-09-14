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
    # ⚠️ [SCT-4 2026-09-14] 질의 조립 루프가 **호출 위**로 옮겨졌다(현지어
    #    검색어를 먼저 고르고 부른다). 창을 호출 앞까지 넓힌다 — 세는 것은
    #    그대로 "팀당 1질의"다.
    assert src[i - 900:i + 400].count('for side in ("home", "away")') == 1


def test_지원_목록을_로그에_손으로_적지_않는다():
    """🔴 사본 드리프트 — 리그가 늘면 로그만 옛것이 된다.
    실제로 그럴 뻔했다: SAT-S1 의 로그가 "K리그1·J1 만 지원" 이었고
    SAT-S2 에서 일곱 리그가 됐는데 문구는 그대로였다."""
    import inspect

    src = inspect.getsource(SOC.gather_soccer)
    i = src.index("위성 소스가 없다")
    assert "_SOCCER_SOURCE" in src[i:i + 400], "지원 목록을 원본에서 만들지 않는다"
    assert "K리그1·J1 만" not in src


# ═══════════════ ⑦ [SAT-S4] 층1 — Transfermarkt 부상표
#
# 🔴 **왜 필요한가.** 지금 축구 위성은 전부 "검색"이다(다음·야후 뉴스 + 토르
#    DDG). 야구에는 그 아래 **층1 — 구조화된 표**가 있다(`transactions_to_articles`
#    · `_kbo_official` · `_mlb_velocity_articles`). 축구에는 그 층이 **없었다.**
#
#    실측 2026-09-12(운영 컨테이너, 7리그 전수):
#      한 URL 모양(`verletztespieler/wettbewerb/{code}`)으로 **7리그 전부** 파싱된다.
#      행 수 — 세리에A 67 · 분데스 67 · EPL 60 · J1 50 · 덴마크 35 · 라리가 24 · K리그1 18
#      선수·소속·부위·복귀예정일이 **칸으로** 들어 있다. 기사 제목 추정이 아니다.
#
# 🔴 **가장 큰 반대 위험은 빈손이 아니라 오매칭이다.** 남의 팀 부상자를 이
#    경기에 붙이면 판정이 조용히 틀린다. 실측이 그것을 잡아냈다 —
#    자카드 퍼지 매칭은 `AC Milan → Inter Milan`(0.50, 2위 0.00)을 **통과시켰다.**
#    `AC` 가 두 글자라 토큰에서 빠지고 `milan` 만 남았기 때문이고, 부상표에는
#    그날 부상자가 있는 팀만 있어서 **진짜 AC밀란이라는 선택지 자체가 없었다.**
#    → 퍼지를 버리고 **법인격 토큰 제거 후 완전일치 + 실측 별칭표**로 간다.
#      전수 재측정: 맞음 76 · 표에없음 14 · **오매칭 0 · 키충돌 0**.

#: 🔴 **실제 마크업 그대로다**(2026-09-12 운영에서 원문을 떠 왔다). 고정구가
#  실제와 다르면 그 고정구는 계약이 아니라 거짓말이다.
_TM_ROW = """
<tr class="{cls}">
  <td><table class="inline-table">
    <tr><td rowspan="2"><img title="{player}" class="bilderrahmen-fixed"/></td>
    <td class="hauptlink"><a title="{player}" href="/x/profil/spieler/{pid}">{player}</a></td></tr>
    <tr><td>Right Winger</td></tr></table></td>
  <td class="zentriert no-border-rechts"><a title="{team}" href="/x/startseite/verein/{vid}"><img/></a></td>
  <td class="links">{inj}</td>
  <td class="zentriert">{until}</td>
  <td class="rechts">€45.00m</td>
</tr>
"""

#: 🔴 페이지 **뒤에 붙는 순위표 위젯**. 실측에서 이 칸이 행 청크로 흘러들어
#  `Uche — Knee injury (복귀 예정 9)` 를 만들었다.
_TM_STANDINGS = """
<table class="items"><tbody><tr class="odd">
  <td class="zentriert">9</td><td class="hauptlink">Getafe CF</td>
  <td class="zentriert">-3</td><td class="zentriert">12</td>
</tr></tbody></table>
"""


def _tm_html(*rows):
    """중첩 `inline-table` 과 뒤따르는 순위표까지 실제처럼 붙인다 — 실측
    2026-09-12에 비탐욕 `</tr>` 는 중첩에서 0행을 냈고, 마지막 칸을 집는
    방식은 순위표의 `9` 를 복귀일로 적었다."""
    body = "".join(
        _TM_ROW.format(cls=("odd" if i % 2 == 0 else "even"), pid=100 + i,
                       vid=900 + i, player=p, team=t, inj=j, until=u)
        for i, (p, t, j, u) in enumerate(rows))
    return f'<table class="items"><tbody>{body}</tbody></table>{_TM_STANDINGS}'


_K1_HTML = _tm_html(
    ("Young-jae Seo", "Daejeon Hana Citizen", "Ankle injury", "Oct 15, 2026"),
    ("Ki-hun Yeom", "Ulsan HD FC", "Knee injury", "Sep 30, 2026"),
    ("Seung-ho Paik", "Pohang Steelers", "Muscle injury", "-"),
)


@pytest.fixture(autouse=True)
def _tm_봉인(monkeypatch):
    """🔴 부상표를 **기본으로 막는다.** 이걸 안 걸면 이 파일의 기존 계약들이
    전부 실제 Transfermarkt 를 때린다(SAT-S2 에서 `리그앙` 으로 한 번 당했다).
    쓰는 시험만 `_tm_fetch` 를 제 것으로 덮는다.

    ⚠️ 예외가 아니라 **빈 페이지**를 준다 — 어댑터의 try/except 가 예외를
       삼키면 봉인이 풀린 것을 아무도 모른다.
    ⚠️ 캐시도 비운다 — 프로세스 전역이라 앞 시험의 표가 다음 시험에 남는다."""
    async def _empty_page(code):
        return ""
    monkeypatch.setattr(SOC, "_tm_fetch", _empty_page, raising=True)
    SOC._tm_cache_clear()


@pytest.fixture
def _조용한_뉴스(monkeypatch):
    """부상표만 남긴다 — 뉴스·토르는 빈손."""
    async def _empty(q):
        return ""
    monkeypatch.setattr(SAT, "_daum_fetch", _empty)
    monkeypatch.setattr(SAT, "_yahoo_fetch", _empty)
    monkeypatch.setattr(SAT, "parse_daum_news", lambda h: [])
    monkeypatch.setattr(SAT, "parse_yahoo_news", lambda h: [])
    async def _notor(jg, queries, **kw):
        return []
    monkeypatch.setattr(SAT, "_tor_supplement", _notor)


def _tm_고정(monkeypatch, html, seen=None):
    async def _fetch(code):
        if seen is not None:
            seen.append(code)
        return html
    monkeypatch.setattr(SOC, "_tm_fetch", _fetch)


# ── 재현: 층1 이 통째로 없다

@pytest.mark.asyncio
async def test_부상표가_기사로_들어온다(monkeypatch, _조용한_뉴스):
    """🔴 재현. HEAD 에서는 `_tm_fetch` 조차 없어 이 계약이 성립하지 않는다."""
    _tm_고정(monkeypatch, _K1_HTML)
    out = await SOC.gather_soccer(_jg("K리그1", home="Ulsan Hyundai FC",
                                      away="Daejeon Citizen"))
    assert out, "부상표에서 한 건도 오지 않았다"
    teams = {a["team"] for a in out}
    assert teams == {"Ulsan Hyundai FC", "Daejeon Citizen"}, teams
    blob = " ".join(a["body"] for a in out)
    assert "Young-jae Seo" in blob and "Ankle injury" in blob
    assert "Oct 15, 2026" in blob, "복귀예정일이 빠졌다"


@pytest.mark.asyncio
async def test_경기에_없는_팀은_새지_않는다(monkeypatch, _조용한_뉴스):
    """🔴 가장 큰 반대 위험. 포항은 이 경기와 무관하다."""
    _tm_고정(monkeypatch, _K1_HTML)
    out = await SOC.gather_soccer(_jg("K리그1", home="Ulsan Hyundai FC",
                                      away="Daejeon Citizen"))
    blob = " ".join(f"{a['team']} {a['title']} {a['body']}" for a in out)
    assert "Pohang" not in blob and "Seung-ho Paik" not in blob, blob


@pytest.mark.asyncio
async def test_AC밀란이_인테르_부상자를_가져가지_않는다(monkeypatch, _조용한_뉴스):
    """🔴 **실측된 오매칭.** 자카드 0.50(2위 0.00)으로 통과했었다 —
    `AC` 가 두 글자라 빠지고 `milan` 만 남았고, 부상표에 AC밀란이 없었다."""
    html = _tm_html(("Marcus Thuram", "Inter Milan", "Thigh problems", "-"))
    _tm_고정(monkeypatch, html)
    out = await SOC.gather_soccer(_jg("세리에A", home="AC Milan", away="AS Roma"))
    blob = " ".join(f"{a['team']} {a['body']}" for a in out)
    assert "Thuram" not in blob and "Inter" not in blob, blob
    # 반대로 진짜 인테르 경기에서는 들어와야 한다
    out2 = await SOC.gather_soccer(
        _jg("세리에A", home="FC Internazionale Milano", away="AS Roma"))
    assert any("Thuram" in a["body"] for a in out2), out2


def test_퍼지_매칭을_쓰지_않는다():
    """🔴 완전일치 + 별칭표만. 점수·임계값이 들어오면 AC밀란 사고가 돌아온다."""
    import inspect

    src = inspect.getsource(SOC)
    i = src.index("def tm_key")
    assert "jaccard" not in src.lower()
    for w in ("0.5", "ratio", "floor"):
        assert w not in src[i:i + 1200], f"매칭에 임계값이 들어왔다: {w}"


def test_별칭표가_실측_그대로다():
    """🔴 실측 2026-09-12 (운영, 우리 DB 90팀 × TM 7리그 부상표 전수).
    이 열 줄이 없으면 그 팀만 조용히 층1 이 0 이 된다."""
    want = {
        "rayo vallecano madrid": "rayo vallecano",
        "real racing santander": "racing santander",
        "athletic": "athletic bilbao",
        "internazionale milano": "inter milan",
        "bayern munchen": "bayern munich",
        "agf aarhus": "aarhus",
        "ob odense": "odense",
        "daejeon citizen": "daejeon hana citizen",
        "jeju united": "jeju",
        "ulsan hyundai": "ulsan",
    }
    assert SOC.TM_ALIAS == want


def test_우리이름과_TM이름이_같은_키로_간다():
    """실측 76쌍 중 대표. 왼쪽은 우리 DB 표기, 오른쪽은 TM 표기다."""
    for ours, tm in [
        ("Ulsan Hyundai FC", "Ulsan HD FC"),
        ("Daejeon Citizen", "Daejeon Hana Citizen"),
        ("Jeju United FC", "Jeju SK"),
        ("Manchester City FC", "Manchester City"),
        ("Manchester United FC", "Manchester United"),
        ("Bournemouth", "AFC Bournemouth"),
        ("Brighton and Hove Albion", "Brighton &amp; Hove Albion"),
        ("FC Bayern München", "Bayern Munich"),
        ("FC Internazionale Milano", "Inter Milan"),
        ("RCD Espanyol de Barcelona", "RCD Espanyol Barcelona"),
        ("Real Madrid CF", "Real Madrid"),
        ("Real Sociedad de Fútbol", "Real Sociedad"),
        ("SonderjyskE", "Sönderjyske Fodbold"),
        ("OB Odense BK", "Odense Boldklub"),
        ("AGF Aarhus", "Aarhus GF"),
        ("US Sassuolo Calcio", "US Sassuolo"),
        ("1. FC Köln", "1.FC Köln"),
    ]:
        assert SOC.tm_key(ours) == SOC.tm_key(tm), (ours, tm)


def test_다른_팀은_다른_키다():
    """🔴 키가 겹치면 남의 부상자가 붙는다. 실측에서 충돌 0 이었다."""
    names = ["AC Milan", "Inter Milan", "Real Madrid", "Real Betis Balompié",
             "Real Sociedad", "Deportivo Alavés", "Deportivo A Coruña",
             "Manchester City", "Manchester United", "Hull City",
             "FC Seoul", "Seoul E-Land FC", "Jeju SK", "Jeonbuk Hyundai Motors"]
    keys = [SOC.tm_key(n) for n in names]
    assert len(set(keys)) == len(keys), sorted(zip(keys, names))


# ── 층1 이 잘려나가지 않는다

@pytest.mark.asyncio
async def test_부상표는_맨앞으로_간다(monkeypatch, _조용한_뉴스):
    """🔴 `gather._satellite` 는 `age_h is None` 을 **뒤로 보내고**
    `MAX_SAT=15` 에서 자른다. 층1 을 None 으로 두면 질이 가장 높은 자료가
    가장 먼저 버려진다. 방금 읽은 **살아 있는 표**이므로 0.0 이 정직하다."""
    _tm_고정(monkeypatch, _K1_HTML)
    out = await SOC.gather_soccer(_jg("K리그1", home="Ulsan Hyundai FC",
                                      away="Daejeon Citizen"))
    assert out and all(a["age_h"] == 0.0 for a in out), out


# ── 리그 코드는 레지스트리가 원본이다

def test_리그코드를_손으로_적지_않는다():
    """🔴 사본 금지. 리그의 외부 소스 코드는 `fd_code`·`odds_key`·`elo` 와
    같은 자리(`app/leagues.py`)에 산다."""
    from app.leagues import LEAGUES

    assert not hasattr(SOC, "_TM_CODE"), "위성이 리그 코드를 따로 들고 있다"
    for key, cfg in LEAGUES.items():
        assert cfg.get("tm_code"), f"{key} 에 tm_code 가 없다"
    assert {c["tm_code"] for c in LEAGUES.values()} == {
        "GB1", "ES1", "IT1", "L1", "JAP1", "DK1", "RSK1"}


@pytest.mark.asyncio
async def test_위성_소스가_있는_리그는_전부_부상표도_받는다(monkeypatch, _조용한_뉴스):
    """🔴 리그를 빠뜨리면 그 리그만 조용히 층1 이 0 이다."""
    for label in sorted(SOC._SOCCER_SOURCE):
        seen = []
        _tm_고정(monkeypatch, _tm_html(), seen)
        await SOC.gather_soccer(_jg(label, home="A", away="B"))
        assert seen, f"{label} 은 부상표를 받지 않았다"


@pytest.mark.asyncio
async def test_리그당_한_번만_받는다(monkeypatch, _조용한_뉴스):
    """같은 리그 두 경기면 표는 한 번이면 된다."""
    seen = []
    _tm_고정(monkeypatch, _K1_HTML, seen)
    SOC._tm_cache_clear()
    for away in ("Daejeon Citizen", "Pohang Steelers"):
        await SOC.gather_soccer(_jg("K리그1", home="Ulsan Hyundai FC", away=away))
    assert len(seen) == 1, seen


# ── 조용히 실패하지 않는다

@pytest.mark.asyncio
async def test_부상표가_터져도_뉴스가_산다(monkeypatch, caplog):
    """⚠️ 층1 은 보강이다. 터지면 로그 한 줄이고 검색 경로는 그대로 돈다."""
    import logging

    async def _boom(code):
        raise RuntimeError("502")
    monkeypatch.setattr(SOC, "_tm_fetch", _boom)
    monkeypatch.setattr(SAT, "_daum_fetch", lambda q: _아무거나())
    async def _아무거나():
        return ""
    monkeypatch.setattr(SAT, "parse_daum_news",
                        lambda h: [{"title": "기사", "url": "http://x/1"}])
    async def _body(u):
        return "본문"
    monkeypatch.setattr(SAT, "_fetch_article_body", _body)
    async def _notor(jg, queries, **kw):
        return []
    monkeypatch.setattr(SAT, "_tor_supplement", _notor)
    with caplog.at_level(logging.WARNING):
        out = await SOC.gather_soccer(_jg("K리그1"))
    assert any(a["source"] == "다음뉴스" for a in out), out
    assert any("부상표" in r.getMessage() for r in caplog.records), caplog.text


@pytest.mark.asyncio
async def test_표에_없는_팀은_부상자가_없다고_말하지_않는다(monkeypatch, _조용한_뉴스, caplog):
    """🔴 표에 없는 이유는 둘이다 — 부상자가 없거나, 이름이 안 맞거나.
    우리는 그것을 **가를 수 없다.** 그러니 "부상자 없음"이라고 쓰지 않고
    아무것도 안 붙인다. 대신 키를 로그에 남겨 별칭표를 늘릴 수 있게 한다."""
    import logging

    _tm_고정(monkeypatch, _K1_HTML)
    with caplog.at_level(logging.INFO):
        out = await SOC.gather_soccer(_jg("K리그1", home="FC Anyang",
                                          away="Gangwon FC"))
    assert out == [], out
    msgs = " ".join(r.getMessage() for r in caplog.records)
    assert "anyang" in msgs and "gangwon" in msgs, msgs


# ── 토르는 DDG 검색 전용이다

def test_부상표는_토르를_경유하지_않는다():
    """🔴 실측 2026-09-12: 콘텐츠 사이트에 토르는 **해롭다.**
      Transfermarkt  직접 200 · 토르 **202 · 본문 0자**
      PremierInjuries 직접 200 · 44KB · 토르 **403**
      DDG 검색        직접 **불가**(AWS IP) · 토르 200
    → 토르는 **검색엔진 전용**이다."""
    import inspect

    src = inspect.getsource(SOC._tm_fetch)
    assert "tor" not in src.lower(), src


def test_토르_규칙이_코드에_적혀_있다():
    """🔴 이 실측이 코드에서 떨어지면 다음 사람이 층1 에 토르를 붙인다."""
    import inspect

    from app.collectors import tor_search

    doc = inspect.getsource(tor_search)[:3000]
    assert "검색엔진 전용" in doc
    assert "Transfermarkt" in doc and "202" in doc


def test_복귀일이_아닌_칸을_복귀일로_적지_않는다():
    """🔴 실측 2026-09-12 운영: 마지막 `zentriert` 칸을 그냥 집었더니
    `Christantus Uche — Knee injury (복귀 예정 9)` 가 나왔다. `9` 는 날짜가
    아니다. **없는 사실을 지어내느니 비운다.**"""
    html = _tm_html(("Christantus Uche", "Getafe CF", "Knee injury", ""))
    rows = SOC.parse_tm_injuries(html)
    assert len(rows) == 1 and rows[0]["복귀"] == "", rows
    # 진짜 날짜는 두 표기 다 살아야 한다
    for shape in ("30/06/2027", "Oct 15, 2026"):
        r = SOC.parse_tm_injuries(_tm_html(("X", "Getafe CF", "Knee", shape)))
        assert r[0]["복귀"] == shape, (shape, r)


@pytest.mark.asyncio
async def test_복귀일이_없으면_문구도_없다(monkeypatch, _조용한_뉴스):
    _tm_고정(monkeypatch, _tm_html(("Y", "FC Seoul", "Knee injury", "")))
    out = await SOC.gather_soccer(_jg("K리그1", home="FC Seoul", away="없는팀"))
    assert out and "복귀 예정" not in out[0]["body"], out
