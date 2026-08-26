"""[A-3단계] 기사 원문 발췌 — 세 개의 게이트.

뉴스는 지금까지 중 **오염 위험이 가장 큰 소스**다. 정형 데이터가 아니라
기존 물리 검사(게이트 ①)가 통하지 않는다.
"""

from datetime import datetime, timedelta

import pytest

from app.collectors.kbo_news import (
    extract_quotes,
    fetch_for_games,
    merge_into_research,
    quote_key,
)

KST = "+09:00"
KICK = datetime.fromisoformat(f"2026-08-26T18:30:00{KST}")

QUOTE_HTML = """<div><p>김 감독은 26일 광주 KIA 타이거즈전에 앞서
"김원중을 앞쪽으로 빼려고 한다. 오늘부터 이이무라가 마무리다"라고 말했다.</p>
<p>롯데는 최근 3연패를 당했다.</p>
<p>이 경기는 롯데에 반등의 계기가 될 것으로 기대된다.</p>
<p>한화 김경문 감독은 "노시환이 오늘 쉰다"고 밝혔다.</p></div>"""


# ---------------------------------------------------------------- 발췌 원칙

def test_only_direct_quotes_are_extracted():
    """🔴 기자의 전망·평가는 사실이 아니라 의견이고, 2단이 할 일을 미리 해버린다.

    인용은 정의상 "누가 무슨 말을 했다"는 사실이라, 인용만 뽑으면
    의견/사실 분류라는 어려운 문제를 통째로 우회한다.
    """
    out = extract_quotes(QUOTE_HTML, {"롯데", "KIA"})
    assert len(out) == 1
    assert "이이무라가 마무리다" in out[0]
    joined = " ".join(out)
    assert "기대된다" not in joined, "기자의 전망이 발췌됐다"
    assert "3연패를 당했다" not in joined, "인용 없는 서술이 발췌됐다"


def test_extracted_text_is_verbatim_not_summarized():
    """요약하지 않는다 — 원문 문장 그대로여야 2단이 인용할 수 있다."""
    # ⚠️ 이 문장에는 "KIA"가 있고 "롯데"는 없다 — 게이트 ②는 문장 단위다.
    out = extract_quotes(QUOTE_HTML, {"KIA"})
    assert "김원중을 앞쪽으로 빼려고 한다" in out[0]
    assert "앞서" in out[0], "문장이 잘렸다"


def test_no_verdict_symbols_are_attached():
    """🔴 '5선발 당겨쓰기'가 붕괴(▼)인지 승부수(▲)인지는 2단이 정한다."""
    for s in extract_quotes(QUOTE_HTML, {"롯데", "한화"}):
        assert "▲" not in s and "▼" not in s


# ---------------------------------------------------------------- 게이트 ②

def test_other_teams_quote_does_not_leak_into_this_game():
    """🔴 실사고 유형: 화이트삭스-텍사스 경기에 보스턴 라인업이 들어갔다."""
    out = extract_quotes(QUOTE_HTML, {"롯데", "KIA"})
    assert not any("노시환" in s for s in out), "한화 기사가 롯데-KIA 칸에 들어갔다"
    hanwha = extract_quotes(QUOTE_HTML, {"한화"})
    assert any("노시환" in s for s in hanwha)


def test_no_names_means_no_extraction():
    """관련성을 확인할 수 없는데 넣으면 다른 경기 이야기가 들어간다."""
    assert extract_quotes(QUOTE_HTML, set()) == []


# ---------------------------------------------------------------- 게이트 ③

def test_quote_key_ignores_punctuation_and_spacing():
    a = '김 감독은 "이이무라가 마무리다"라고 말했다.'
    b = '김 감독은 “이이무라가 마무리다” 라고 말했다'
    assert quote_key(a) == quote_key(b)
    assert quote_key(a) != quote_key('다른 문장이다 "전혀" 말했다')


# ---------------------------------------------------------------- 게이트 ① (누출)

class _FakeClient:
    """기사 2건 — 하나는 경기 전, 하나는 경기 후(결과 포함)."""

    def __init__(self):
        self.mock = False

    async def index(self, date):
        return ["u/pre", "u/post"]

    async def article(self, url):
        if url == "u/pre":
            return (QUOTE_HTML, KICK - timedelta(minutes=19), "경기 전")
        post = ('<p>박 감독은 "우리 타자들이 전반적으로 잘 치지 못했다"고 '
                '말했다. 롯데가 이겼다.</p>')
        return (post, KICK + timedelta(hours=3), "경기 후")


@pytest.mark.asyncio
async def test_post_game_article_is_blocked_as_leakage():
    """🔴 가장 위험한 구멍 — 경기 후 기사는 **결과를 담고 있다.**

    한 번 새면 그 뒤 모든 측정을 못 믿게 된다.
    """
    games = [{"home": "Kia Tigers", "away": "Lotte Giants",
              "starts_at": KICK.isoformat(),
              "research": {"home_pitcher": {"name": "황동하"}}}]
    out = await fetch_for_games(games, "2026-08-26", client=_FakeClient())
    rows = out.get("Lotte Giants@Kia Tigers") or []
    assert rows, "경기 전 인용까지 함께 버렸다"
    text = " ".join(r["text"] for r in rows)
    assert "잘 치지 못했다" not in text, "경기 후 발언이 들어왔다 — 누출"
    assert "이이무라가 마무리다" in text


@pytest.mark.asyncio
async def test_url_and_published_time_are_stored(db_pool=None):
    """발췌 문장에는 반드시 기사 URL과 게시 시각이 함께 있어야 한다."""
    games = [{"home": "Kia Tigers", "away": "Lotte Giants",
              "starts_at": KICK.isoformat(), "research": {}}]
    out = await fetch_for_games(games, "2026-08-26", client=_FakeClient())
    row = (out.get("Lotte Giants@Kia Tigers") or [{}])[0]
    assert row.get("url") and row.get("at"), f"출처가 없다: {row}"


@pytest.mark.asyncio
async def test_same_quote_is_not_used_in_two_games():
    """게이트 ③ — 같은 문장이 여러 경기에 중복 발췌되면 안 된다."""
    games = [
        {"home": "Kia Tigers", "away": "Lotte Giants",
         "starts_at": KICK.isoformat(), "research": {}},
        {"home": "LG Twins", "away": "Lotte Giants",
         "starts_at": KICK.isoformat(), "research": {}},
    ]
    out = await fetch_for_games(games, "2026-08-26", client=_FakeClient())
    keys = [quote_key(r["text"]) for rows in out.values() for r in rows]
    assert len(keys) == len(set(keys)), "같은 문장이 두 경기에 붙었다"


# ---------------------------------------------------------------- 병합

def test_merge_marks_collected_even_with_no_quotes():
    """🔴 '인용 0건'과 '조사 실패'를 구분하지 못하면 딥서치를 영원히 부른다."""
    from app.research.crosscheck_sources import missing_fields

    research: dict = {}
    merge_into_research(research, {"home": "A", "away": "B"}, {})
    assert missing_fields(research, ("rotation_plan",)) == []


def test_merge_keeps_text_unprocessed():
    research: dict = {}
    jg = {"home": "Kia Tigers", "away": "Lotte Giants"}
    table = {"Lotte Giants@Kia Tigers": [
        {"text": '김 감독은 "이이무라가 마무리다"라고 말했다.',
         "url": "http://x", "at": "2026-08-26T18:11:00+09:00"}]}
    merge_into_research(research, jg, table)
    assert research["news_quotes"][0]["text"].startswith("김 감독은")
    assert research["news_quotes"][0]["url"] == "http://x"
    assert "이이무라가 마무리다" in research["rotation_plan"]


# ---------------------------------------------------------------- 본문 구간

NAV_HTML = """<html><head><title>롯데, 마무리 김원중 포기 - 스포츠경향</title></head>
<body><nav>홈 연예 야구 축구 많이 본 기사 랭킹</nav>
<h1>롯데, 마무리 김원중 포기</h1>
<p>김태형 롯데 감독은 "이이무라가 앞으로 마무리다"라고 밝혔다.</p>
<p>롯데는 롯데답게 롯데의 뒷문을 정리했다.</p>
<div>많이 본 기사 30대 여배우 체포 아이유 음모론</div></body></html>"""


def test_body_text_survives_navigation_tail_marks():
    """🔴 꼬리 표식은 **네비게이션에도 있다.**

    처음 나오는 것에서 자르면 본문이 통째로 날아간다 — 실측(2026-08-27):
    4,734자 기사가 309자로 잘려 수율이 0이 됐다.
    """
    from app.collectors.kbo_news import body_text

    out = body_text(NAV_HTML, "롯데, 마무리 김원중 포기")
    assert "이이무라가 앞으로 마무리다" in out, "본문이 잘렸다"
    assert "여배우" not in out, "추천기사가 남았다"


def test_body_text_without_title_does_not_truncate():
    """제목을 못 찾으면 자르지 않는다 — 자르는 편이 더 위험하다."""
    from app.collectors.kbo_news import body_text

    out = body_text(NAV_HTML, "전혀 다른 제목")
    assert "이이무라가 앞으로 마무리다" in out


def test_article_level_gate_rejects_incidental_mentions():
    """🔴 실측 오염: 삼성 후라도 기사가 'KIA와의 2군 경기' 한 마디로 롯데-KIA 칸에 들어갔다."""
    from app.collectors.kbo_news import article_is_about, article_teams

    samsung = """<html><head><title>삼성 후라도 복귀</title></head><body>
    <h1>삼성 후라도 복귀</h1>
    <p>이종열 삼성 단장은 "후라도가 1~2번 더 던진다"고 말했다.</p>
    <p>삼성은 삼성대로 삼성의 로테이션을 짠다. 후라도는 KIA와의 2군 경기에 등판했다.</p>
    </body></html>"""
    counts = article_teams(samsung, "삼성 후라도 복귀")
    assert counts["Samsung Lions"] > counts["Kia Tigers"]
    assert article_is_about(samsung, {"Samsung Lions"}) is True
    assert article_is_about(samsung, {"Lotte Giants", "Kia Tigers"}) is False, \
        "부수적 언급으로 다른 경기 기사가 통과했다"


def test_curly_quotes_do_not_merge_sentences():
    """🔴 한국어 기사는 곡선 따옴표를 쓴다 — 여는 것만 세면 문장이 뭉친다."""
    from app.collectors.kbo_news import _sentences

    text = '김 감독은 “이이무라가 마무리다”라고 말했다. 롯데는 3연패를 당했다.'
    out = _sentences(text)
    assert len(out) == 2, f"문장이 뭉쳤다: {out}"
    assert "마무리다" in out[0] and "3연패" in out[1]


def test_article_without_published_time_is_dropped():
    """시각을 모르면 경기 전인지 후인지 알 수 없다 — 누출 경로가 된다."""
    import asyncio

    from app.collectors.kbo_news import fetch_for_games

    class _NoTime:
        mock = False

        async def index(self, date):
            return ["u/1"]

        async def article(self, url):
            return (NAV_HTML, None, "롯데, 마무리 김원중 포기")

    games = [{"home": "Kia Tigers", "away": "Lotte Giants",
              "starts_at": "2026-08-26T18:30:00+09:00", "research": {}}]
    out = asyncio.run(fetch_for_games(games, "2026-08-26", client=_NoTime()))
    assert out == {}, "게시 시각 없는 기사가 통과했다"
