"""계약 — **당일·내일 슬레이트**(사용자 지시 2026-10-01)와 시간대 경계.

> 서버에서 당일 날짜 및 그다음 날짜 터울은 하루, 어떤 경기가 있는지 저장이 되어
> 있어야 한다. 야구 축구 하키 농구 배구 경기를.

⚠️ **v4 §9 밖의 확장이다** — §9 단계 9 는 `KBO·NPB·MLB·K리그·해외축구`(야구·축구)만
   이름을 댔다. 사용자 지시가 문서보다 위라서 구현했고, 그 사실을
   `docs/fable/questions/2026-10-01_five_sports.md` 에 적었다.
"""
from __future__ import annotations

import inspect
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app import config
from app.collect import fdorg, ingest, nhl
from app.net import Fetched
from tests._helpers import strip_docs

ROOT = Path(__file__).resolve().parents[2]
KST = timezone(timedelta(hours=9))


def test_이틀치를_쌓는다():
    """🔴 *"당일 날짜 및 그다음 날짜 터울은 하루"* — 하루만 쌓으면 지시를 못 지킨다."""
    assert config.SLATE_DAYS >= 2, config.SLATE_DAYS
    src = inspect.getsource(__import__("app.scheduler", fromlist=["x"]).run_once)
    assert "SLATE_DAYS" in src, "스케줄러가 이틀치를 안 돈다"
    assert "timedelta(days=ahead)" in src


def test_확장한_종목이_어댑터_표에_있다():
    """🔴 야구·축구·하키가 표에 있다. **농구·배구는 없고, 없는 것이 맞다.**

    ⚠️ 무료 일정 소스를 못 찾았다(실측 2026-10-01: NBA 두 경로 ReadTimeout ·
       배구는 API 자체가 없다). 🔴 **있는 척하지 않는다** — 빈 어댑터를 넣으면
       "오늘 농구 경기가 없다"로 읽힌다.
    """
    sports = set()
    for mod in ingest.ADAPTERS.values():
        got = getattr(mod, "SPORT", None)
        if got:
            sports.add(got)
    assert {"baseball", "soccer", "hockey"} <= sports, sports
    assert "basketball" not in sports, "소스도 없이 농구 어댑터가 들어왔다"
    assert "volleyball" not in sports, "소스도 없이 배구 어댑터가 들어왔다"


def test_못_붙인_종목이_문서에_이름으로_남아_있다():
    """🔴 조용한 0 금지 — 못 한 것을 **이름과 사유로** 남긴다."""
    doc = (ROOT / "docs" / "fable" / "questions"
           / "2026-10-01_five_sports.md").read_text(encoding="utf-8")
    for word in ("농구", "배구", "ReadTimeout", "일정 API 가 없다"):
        assert word in doc, word


# ══════════════════════════════════════════════════════════════════
# 🔴 시간대 경계 — 실측이 잡은 결함
# ══════════════════════════════════════════════════════════════════

def test_NHL은_창으로_거른다():
    """🔴🔴 **창으로 거른다 — 지금부터 36시간(UTC)**. 사용자 지시 2026-10-04.

    ⚠️ 이 시험은 *"KST 달력 날짜로 거른다"* 였다. 🔴 그 규칙이 **유럽·북미
       저녁 경기를 통째로 버렸다**(실측: 포르투갈 vs 노르웨이가
       *"날짜가 다르다"* 로 떨어졌다) — 유럽 20:45 = KST 다음날 03:45 이다.
    🔴 그래서 **시계를 고정해서** 잰다 — 고정물은 지난 날짜이고, 창은 *"지금"*
       을 기준으로 하므로 고정 없이는 **창을 시험할 수가 없다**.
    """
    # 10-01 22:00 ET = 10-02 02:00 UTC = 10-02 11:00 KST
    body = ('{"gameWeek":[{"date":"2026-10-01","games":[{"id":1,'
            '"startTimeUTC":"2026-10-02T02:00:00Z","gameState":"FUT",'
            '"homeTeam":{"placeName":{"default":"Toronto"},'
            '"commonName":{"default":"Maple Leafs"},"id":10},'
            '"awayTeam":{"placeName":{"default":"Montreal"},'
            '"commonName":{"default":"Canadiens"},"id":8}}]}]}')
    got = Fetched("https://x", True, 200, body)

    from app import window
    # 🔴 창 안(킥오프 10-02 02:00Z · 지금 10-01 06:00Z → 20시간 뒤)
    window.set_clock(datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc))
    try:
        rows = nhl.parse_schedule(got, date(2026, 10, 2))
        assert len(rows) == 1, rows
        assert rows[0]["starts_kst"].date() == date(2026, 10, 2)
        assert rows[0]["sport"] == "hockey"
        # 🔴 **API 버킷 날짜는 이제 상관없다** — 같은 응답을 10-01 로 물어도
        #    창 안이면 들어온다(버킷이 아니라 **킥오프 시각**으로 센다).
        assert len(nhl.parse_schedule(got, date(2026, 10, 1))) == 1
        # 🔴 그리고 **창 밖이면 버린다** — 이틀 뒤로 시계를 돌린다
        window.set_clock(datetime(2026, 10, 3, 6, 0, tzinfo=timezone.utc))
        assert nhl.parse_schedule(got, date(2026, 10, 2)) == [], (
            "🔴 이미 지난 경기를 슬레이트에 넣었다")
    finally:
        window.set_clock(None)


def test_NHL_요청창이_하루_앞에서_시작한다():
    """🔴 KST 기준 그날 경기가 응답 안에 들어오려면 **하루 앞**에서 받아야 한다."""
    assert "2026-09-30" in nhl.schedule_url(date(2026, 10, 1))


def test_해외축구_요청창이_하루씩_넓다():
    """🔴 UTC 날짜로 요청하고 KST 로 거르면 **경계 경기를 통째로 놓친다.**

    ⚠️ 실측 2026-10-01: 브라질 경기가 `10-02` UTC 저녁 → KST **10-03** 이라
       10-02 요청에서 사라졌다(그날 해외축구 0건의 원인). 창을 넓히자 잡혔다.
    """
    srcs = fdorg.sources_slate(date(2026, 10, 2))
    if not srcs:                       # 🔴 키가 없으면 소스를 안 만든다
        return
    url = srcs[0].url
    assert "dateFrom=2026-10-01" in url and "dateTo=2026-10-03" in url, url


def test_해외축구_키가_없으면_소스를_안_만든다():
    """🔴 키 없이 부르면 401 이 오고 그것이 *"오늘 경기가 없다"* 로 읽힌다.

    없는 것은 없다고 하는 편이 낫다(§19-b-6) — 세포가 unknown + 사유를 남긴다.
    """
    import app.collect.fdorg as F
    orig = F.api_key
    F.api_key = lambda: ""
    try:
        assert F.sources_slate(date(2026, 10, 1)) == []
    finally:
        F.api_key = orig


def test_해외축구_키가_URL이_아니라_헤더로_간다():
    """🔴 키를 URL 에 실으면 **카세트 파일 본문에 남는다.**

    ⚠️ 카세트 열쇠는 url+질의로 만든다(`app/cassette.py`) — URL 에 키가 있으면
       저장소에 커밋되는 파일에 들어간다.
    """
    srcs = fdorg.sources_slate(date(2026, 10, 1))
    if not srcs:
        return
    src = srcs[0]
    assert src.headers and "X-Auth-Token" in src.headers
    assert "X-Auth-Token" not in (src.url or "")
    assert src.headers["X-Auth-Token"] not in (src.url or "")


def test_모르는_상태를_예정으로_때우지_않는다():
    """🔴 모르는 `status` 를 `scheduled` 로 읽으면 **끝난 경기를 분석 대상**에 넣는다.

    §2: 진행 중·종료 경기는 분석 대상이 아니다.
    """
    body = ('{"gameWeek":[{"date":"2026-10-01","games":[{"id":2,'
            '"startTimeUTC":"2026-10-01T10:00:00Z","gameState":"처음보는값",'
            '"homeTeam":{"placeName":{"default":"A"},"commonName":{"default":"X"}},'
            '"awayTeam":{"placeName":{"default":"B"},"commonName":{"default":"Y"}}}]}]}')
    from app import window
    # 🔴 **시계를 고정한다** — 창이 *"지금부터 36시간"* 이라 고정물(지난 날짜)은
    #    고정 없이는 전부 창 밖이다(지시 2026-10-04).
    window.set_clock(datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc))
    try:
        rows = nhl.parse_schedule(Fetched("https://x", True, 200, body),
                                  date(2026, 10, 1))
    finally:
        window.set_clock(None)
    assert rows and rows[0]["status"].startswith("unknown:"), rows


# ══════════════════════════════════════════════════════════════════
# 🔴 조회 — "질문하면 바로 답한다"
# ══════════════════════════════════════════════════════════════════

def test_창을_KST_날짜로_자른다():
    """🔴 **timestamptz 를 날짜와 바로 비교하지 않는다.**

    ⚠️ 실측 2026-10-01: `starts_kst >= $1::date` 는 서버 시간대(UTC)로 비교된다.
       이틀 창(10-01~10-02)을 물었는데 `10-03 07:30 KST`(= 10-02 22:30 UTC) 경기가
       들어왔다 — **질의는 UTC 로 자르고 화면은 KST 로 그려서** 둘이 어긋났다.
    🔴 `app/main.py`·`app/sources.py` 는 이미 `AT TIME ZONE 'Asia/Seoul'` 를
       쓰고 있었다 — `app/slate.py` 만 빠져 있었다.
    """
    from app import slate
    assert "AT TIME ZONE 'Asia/Seoul'" in slate._BASE, slate._BASE
    # 🔴 timestamptz 를 날짜와 **직접** 비교하는 줄이 없어야 한다
    assert "starts_kst >= $1::date" not in slate._BASE


def test_못_찾으면_왜인지_답한다():
    """🔴 조용한 0 금지 — *"아직 안 쌓였다"* 와 *"그런 경기가 없다"* 는 다르다.

    ⚠️ 빈 목록만 내면 사용자가 "경기가 없다"로 읽고 다시 묻지 않는다.
    """
    from app import slate
    empty = slate.Found()
    got = slate.render(empty, title="x")
    assert "찾은 경기 0건" in got and "이유:" in got

    # 🔴 쌓인 것이 있는데 조건이 안 맞은 경우와, 아예 안 쌓인 경우를 가른다
    src = inspect.getsource(slate.find)
    assert "아직 안 쌓였다" in inspect.getsource(slate.window)
    assert "창에는" in src, "조건 불일치와 미수집을 구분하지 않는다"


def test_조회가_웹에_나가지_않는다():
    """🔴 **물을 때마다 검색하지 않는다.**

    ⚠️ 실측 2026-09-30: 측정이 연달아 검색을 던져 SearXNG 엔진 셋을 전부
       정지시켰다. 사용자 질문마다 검색하면 그것이 운영에서 일어난다.
       🔴 스케줄러가 미리 쌓고, 조회는 **DB 만** 읽는다.
    """
    from tests._helpers import strip_docs

    from app import slate
    src = strip_docs(inspect.getsource(slate))
    for bad in ("Net(", "build_chain", "httpx", "search"):
        assert bad not in src, f"조회 경로가 웹에 나간다: {bad}"


def test_여러_경기가_맞으면_전부_낸다():
    """🔴 하나를 골라 주지 않는다 — 잘못 고르면 **남의 경기**를 답한다(§17-g-3 · M14)."""
    from app import slate
    src = inspect.getsource(slate.find)
    assert "ILIKE" in src, "부분 일치로 찾지 않는다"
    # 🔴 `LIMIT 1` 로 하나만 고르는 자리가 없어야 한다
    assert "LIMIT 1" not in src and "limit 1" not in src


def test_끝난_경기를_예정으로_보이지_않는다():
    """🔴 §2 — 진행 중·종료 경기는 분석 대상이 아니다. 화면이 그것을 구분해야 한다."""
    from datetime import datetime as _dt

    from app import slate
    g = {"sport": "hockey", "league": "NHL", "home": "A", "away": "B",
         "starts_kst": _dt(2026, 10, 1, 20, 0, tzinfo=KST),
         "status": "final", "home_score": 3, "away_score": 1,
         "round_note": None, "venue": None}
    got = slate.render(slate.Found(games=[g]))
    assert "[final]" in got, got
    assert "1-3" in got, got


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **남의 경기를 분석하지 않는다** (실측 2026-10-02 · §17-g-3 · M14)
# ══════════════════════════════════════════════════════════════════
#
# 사용자가 *"중국 vs 팔레스타인"* 을 물었는데 봇이 **아시안게임 `China W`** 경기
# (한국 vs 중국 여자)를 분석했다. `China` 부분 일치가 그것을 잡았고, 한 건이
# 맞았으니 *"찾았다"* 로 끝났다. 🔴 그 카드는 통째로 거짓이다.


def test_상대를_주면_양_팀이_다_든_경기만_찾는다():
    """🔴 조회가 **상대도 조건으로** 쓰나 — 안 쓰면 부분 일치가 남의 경기를 잡는다."""
    from app import slate
    src = inspect.getsource(slate.find)
    assert "opponent" in inspect.signature(slate.find).parameters
    # 🔴 SQL 에 상대 조건이 **실제로** 붙는다(주석이 아니라 코드다)
    body = src.split('"""')[-1]
    assert body.count("home ILIKE") >= 2, \
        "상대 조건이 SQL 에 안 붙는다 — 팀 하나만 보고 있다"


def test_질문_경로가_상대를_조회에_넘긴다():
    """🔴 `slate.find` 가 받을 수 있어도 **부르는 곳이 안 넘기면** 뜻이 없다.

    ⚠️ 2단계(2026-10-03)로 그 자리가 **입구**(`resolve.match_of`)로 옮겨졌다 —
       이름 해석이 한 곳이어야 한다는 설계 때문이다. 🔴 묻는 것은 그대로다.
    """
    from app import resolve
    src = inspect.getsource(resolve.match_of)
    assert "opponent" in src, "입구가 상대를 조회에 안 넘긴다"
    # 🔴 표에 없으면 **봇이 직접 찾는다**(사람이 행을 넣는 것이 아니다)
    assert "findgame" in src, "표에 없을 때 봇이 직접 찾지 않는다"
    # 🔴🔴 **표준 표기로 찾는다** — 사용자가 쓴 말로 찾으면 저장한 이름과 갈린다
    #    (실측 2026-10-03: `Croatia` 로 적어 놓고 `크로아티아` 로 되찾아 실패했다)
    assert "canon(" in src


def test_경기_페이지의_사전_칸을_글자로_저장하지_않는다():
    """🔴 실측 2026-10-02: `games.venue` 에 **사전이 통째로 글자로** 들어갔다.

    `{'name': 'Chongqing Longxing Football Stadium', 'city': …, 'lat': …}`
    ⚠️ CLAUDE.md §5 가 적어 둔 병이다 — *"JSONB 가 문자열로 오고…"*.
    """
    from app.collect import fotmob
    assert fotmob._name_of({"name": "A Stadium", "city": "X"}) == "A Stadium"
    assert fotmob._name_of("Friendlies") == "Friendlies"
    # 🔴 이름 칸이 없으면 **빈 문자열** — 사전을 글자로 만들지 않는다
    assert fotmob._name_of({"lat": 1.0}) == ""
    src = inspect.getsource(fotmob.slate_row)
    for cell in ("venue", "league"):
        assert f'"{cell}": _name_of(' in src or f"{cell} = _name_of(" in src, cell


def test_슬레이트_열쇠가_주소_표기에_흔들리지_않는다():
    """🔴 `ext_id` 는 **안정적인 열쇠**다 — 표기가 바뀌면 같은 경기가 두 행이 된다.

    ⚠️ fotmob 은 같은 경기를 `/matches/…` 와 `/ko/matches/…` 로 준다.
    """
    from app.collect import fotmob
    src = inspect.getsource(fotmob.slate_row)
    i = src.index("ext =")
    line = src[i:src.index("\n", i)]
    assert "matchId" in line and line.index("matchId") < line.index("match_id"), \
        f"주소 꼬리를 열쇠로 쓴다 — {line}"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **축구가 깊이 0 이었다** (실측 2026-10-02 · 중국 vs 팔레스타인)
# ══════════════════════════════════════════════════════════════════
#
# `analyze.depth_sources` 는 어댑터의 `sources_context` 를 찾는데 **fotmob 에 그
# 함수가 없었다.** 파서는 다 있었고(`parse_context`·`follow_links`) **부르는 곳이
# 없었을 뿐이다**(CLAUDE.md #2 배선). 라이브: 사실 6건 · 변수 **0건** · R5 자료 부족.


def test_fotmob_경기는_ext_id_로_깊이를_다시_연다():
    """🔴 봇이 적은 행의 `ext_id` 가 **자료 주소**다 — 그것으로 다시 열 수 있어야 한다."""
    from app import analyze
    from app.collect import fotmob
    got = analyze.depth_sources({"ext_id": "fotmob-6280453",
                                 "league": "Friendlies"})
    assert len(got) == 1, got
    assert got[0].url == fotmob.match_url("6280453")
    # 🔴 파서가 §13-c ①②(날짜·두 팀)를 집행하므로 `dateless_ok` 를 켜도 안전하다
    assert got[0].dateless_ok and got[0].parse is fotmob.parse_context
    assert got[0].follow is fotmob.follow_links


def test_다른_종목의_ext_id_에_축구_깊이를_붙이지_않는다():
    """🔴 MLB `ext_id` 는 숫자다(`849844`) — 접두를 요구하지 않으면 통과한다.

    ⚠️ 그러면 야구 경기에 fotmob **축구 페이지**가 붙는다 — 남의 경기다(§17-g-3).
    """
    from app.collect import fotmob
    assert fotmob.sources_context("849844") == []
    assert fotmob.sources_context("npb-20261002-m-h") == []
    assert fotmob.sources_context("") == []


def test_번호만으로_경기_페이지를_알아본다():
    """🔴 `ext_id` 에는 슬러그가 없다 — `/match/<번호>` 꼴을 못 읽으면 깊이가 끊긴다."""
    from app.collect import fotmob
    assert fotmob.is_match_page("https://www.fotmob.com/match/6280453")
    assert fotmob.is_match_page(
        "https://www.fotmob.com/matches/china-vs-palestine/17zll3")
    assert not fotmob.is_match_page("https://www.fotmob.com/leagues/47/overview")
    # 🔴 같은 경기의 두 주소가 **같은 번호**를 낸다(중복 열기를 막는다)
    assert fotmob.match_id("https://www.fotmob.com/ko/matches/a-vs-b/17zll3") \
        == fotmob.match_id("https://www.fotmob.com/matches/a-vs-b/17zll3")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **ESPN** — 사용자 지시 2026-10-03: *"espn 소스로 쓰고"*
# ══════════════════════════════════════════════════════════════════


def test_espn_결정이_문서에_적혀_있다():
    """🔴 갈림길은 **문서로 닫는다** — 코드만 바꾸면 왜 썼는지가 사라진다."""
    doc = (ROOT / "docs/fable/questions/2026-10-01_espn_robots.md") \
        .read_text(encoding="utf-8")
    assert "닫혔다" in doc and "2026-10-03" in doc, "ESPN 결정이 안 적혀 있다"
    # 🔴 `site.api.espn.com` 은 **그대로 안 쓴다**(robots 가 거부로 답한다)
    assert "site.api.espn.com" in doc


def test_espn_파서가_배당을_읽지_않는다():
    """🔴🔴 **절대규칙 6** — 배당은 `research` 스키마에만. 판정 경로 접근 0건.

    ⚠️ ESPN 경기 페이지 페이로드에 `betConfigSettings` 같은 칸이 있다. D46 대로
       **독스트링·주석을 뺀 코드만** 본다 — 문서가 금지어를 *설명하는* 것과 코드가
       그것을 *읽는* 것은 다르다.
    """
    from app.collect import espn
    src = strip_docs(inspect.getsource(espn))
    for bad in ("betconfig", "odds", "spread", "moneyline", "wllclck",
                "pickcenter"):
        assert bad not in src.lower(), f"ESPN 파서가 `{bad}` 를 읽는다"


def test_경기를_읽는_어댑터가_같은_규약을_지킨다():
    """🔴 `findgame` 이 둘을 **같은 자리**에서 쓴다(§19-b-4 대체).

    ⚠️ 규약이 갈리면 그 자리에 분기가 생기고, 분기는 소스가 늘 때마다 자란다.
    """
    from app import findgame
    assert len(findgame.READERS) >= 2, findgame.READERS
    for mod in findgame.READERS:
        for name in ("is_match_page", "match_id", "slate_row", "payload",
                     "sources_context", "EXT_PREFIX"):
            assert hasattr(mod, name), (mod.__name__, name)
        # 🔴 접두가 서로 달라야 한다 — 같으면 깊이 표가 한쪽을 먹는다
    prefixes = [m.EXT_PREFIX for m in findgame.READERS]
    assert len(set(prefixes)) == len(prefixes), prefixes


def test_깊이_표가_두_접두를_다_안다():
    """🔴 봇이 적은 행은 접두로 자기 자료 주소를 가리킨다."""
    from app.collect.ingest import DEPTH_BY_EXT
    from app.collect import espn, fotmob
    assert DEPTH_BY_EXT[fotmob.EXT_PREFIX] is fotmob
    assert DEPTH_BY_EXT[espn.EXT_PREFIX] is espn
    from app import analyze
    got = analyze.depth_sources({"ext_id": "espn-401914141",
                                 "league": "fifa.friendly"})
    assert len(got) == 1 and "401914141" in got[0].url


def test_espn_접두_없는_ext_id_에는_붙지_않는다():
    """🔴 접두를 요구하지 않으면 다른 어댑터의 숫자 `ext_id` 도 통과한다."""
    from app.collect import espn
    assert espn.sources_context("849844") == []
    assert espn.sources_context("fotmob-6280453") == []
