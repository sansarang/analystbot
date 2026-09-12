"""SAT-S3 — 위성 검색을 야구/축구로 **파일부터** 분리한다.

사용자 지시 2026-09-12: "인공위성 서치기능은 야구와 축구를 분리해라"

🔴 왜. 한 파일(`satellite.py`)에 MLB·KBO·NPB·축구가 다 들어 있어서,
   축구 검색어를 만지다 야구 상수를 건드릴 위험이 그대로 있다. 실제로
   SAT-S1~S2 에서 같은 파일을 네 번 고쳤다.

⚠️ **반대 위험이 전부다.** 야구 세 어댑터는 운영에서 돈다 — 옮기다 끊으면 P0 다.
   밖에서 쓰는 심볼은 넷뿐이다(전수 확인):
     kbo_roster → _article · deepsearch/gather → read_cache · scheduler → 모듈
   그래서 **야구는 제자리에 두고 축구만 떼어낸다.** 움직이는 코드가 적을수록
   끊길 곳도 적다.
"""

import pytest

from app.collectors import satellite as SAT
from app.collectors import satellite_soccer as SOC


# ═══════════════ ① 축구가 제 파일로 나갔다

def test_축구_모듈이_따로_있다():
    assert hasattr(SOC, "gather_soccer")
    assert hasattr(SOC, "SOCCER_ALIAS")
    assert hasattr(SOC, "soccer_query")


def test_축구_코드가_야구_파일에_남아_있지_않다():
    """🔴 두 곳에 있으면 한쪽만 고쳐진다 — 이 저장소의 사본 드리프트다."""
    src = open("app/collectors/satellite.py", encoding="utf-8").read()
    for sym in ("SOCCER_ALIAS", "_SOCCER_TERMS", "_SOCCER_SOURCE",
                "_SOCCER_TOR_TAIL", "def gather_soccer", "def soccer_query"):
        assert sym not in src, f"{sym} 가 야구 파일에 남아 있다"


def test_야구_어댑터는_제자리다():
    """🔴 움직이지 않은 것이 가장 안전하다."""
    src = open("app/collectors/satellite.py", encoding="utf-8").read()
    for sym in ("def gather_mlb", "def gather_kbo", "def gather_npb",
                "def transactions_to_articles", "def _kbo_official"):
        assert sym in src, f"{sym} 가 야구 파일에서 사라졌다"


def test_축구_파일에_야구가_섞이지_않았다():
    """⚠️ **주석은 보지 않는다.** 축구 파일은 "야구와 반대다 — KBO 는
    `_KBO_TERMS_LIST` 4개를 돌지만…" 처럼 야구를 **참조**한다. 그건 근거이고
    남아야 한다. 지워야 하는 것은 **코드**다."""
    code = "\n".join(
        ln for ln in open("app/collectors/satellite_soccer.py",
                          encoding="utf-8").read().splitlines()
        if not ln.lstrip().startswith("#"))
    for sym in ("gather_mlb", "gather_kbo", "gather_npb", "_KBO_TERMS_LIST",
                "_NPB_TERMS", "transactions_to_articles"):
        assert sym not in code, f"{sym} 가 축구 파일 코드에 섞였다"


# ═══════════════ ② 배선은 그대로 — 넷 다 등록돼 있다

def test_어댑터_넷이_전부_등록돼_있다():
    assert SAT._ADAPTERS["kbo"] is SAT.gather_kbo
    assert SAT._ADAPTERS["npb"] is SAT.gather_npb
    assert SAT._ADAPTERS["mlb"] is SAT.gather_mlb
    assert SAT._ADAPTERS["soccer"] is SOC.gather_soccer


def test_밖에서_쓰는_심볼이_그대로다():
    """🔴 전수 확인한 넷 — 하나라도 사라지면 임포트가 끊긴다."""
    for sym in ("_article", "read_cache", "run_satellite", "gather"):
        assert hasattr(SAT, sym), sym


def test_기존_임포트_경로가_산다():
    """실제 호출부가 쓰는 그 줄을 그대로 돌려 본다."""
    from app.collectors.satellite import _article, read_cache  # noqa: F401


# ═══════════════ ③ 공용 검색은 한 벌만 — 사본 금지

def test_검색_원시함수를_축구가_다시_만들지_않았다():
    """🔴 다음·야후 검색과 본문 수집은 **한 벌**이다. 축구가 제 것을 만들면
    한쪽을 고칠 때 다른 쪽이 안 따라온다."""
    src = open("app/collectors/satellite_soccer.py", encoding="utf-8").read()
    for banned in ("_DAUM_URL", "_YAHOO_URL", "def parse_daum_news",
                   "def parse_yahoo_news", "def _fetch_article_body",
                   "def _article"):
        assert banned not in src, f"{banned} 를 축구가 다시 만들었다"
    assert "satellite" in src, "공용 함수를 야구 파일에서 가져오지 않는다"


# ═══════════════ ④ 동작은 한 글자도 안 바뀐다

def test_별칭표가_그대로다():
    for en, kr in (("Ulsan Hyundai FC", "울산 HD"), ("Arsenal FC", "아스널"),
                   ("SSC Napoli", "나폴리"), ("FC Machida Zelvia", "FC町田ゼルビア")):
        assert SOC.soccer_query(en) == kr


def test_리그_표가_그대로다():
    from app.leagues import LEAGUES

    labels = {c["label"] for c in LEAGUES.values()}
    assert labels - set(SOC._SOCCER_SOURCE) == set()
    assert SOC._SOCCER_SOURCE["J1 리그"] == "yahoo"


def test_검색어가_여전히_비어_있다():
    assert SOC._SOCCER_TERMS == ""


@pytest.mark.asyncio
async def test_축구가_공용_검색을_쓴다(monkeypatch):
    """🔴 배선 확인 — 야구 파일의 함수를 패치하면 축구가 그것을 쓴다."""
    seen = []

    async def _daum(q):
        seen.append(q)
        return ""

    monkeypatch.setattr(SAT, "_daum_fetch", _daum)
    monkeypatch.setattr(SAT, "parse_daum_news", lambda h: [])

    async def _no_tor(jg, queries):
        return []

    monkeypatch.setattr(SAT, "_tor_supplement", _no_tor)
    await SOC.gather_soccer({"game_id": 1, "sport": "soccer", "league": "K리그1",
                             "home": "Ulsan Hyundai FC", "away": "FC Seoul"})
    assert seen, "공용 다음 검색을 쓰지 않았다"
