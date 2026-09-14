"""BIG-1 — 빅매치 태그 (사용자 지시).

셋 중 하나면 빅매치: 순위 3계단 이내 · 더비 목록 · 상위 6팀 간.
🔴 FOT-3(3순위 구단 RSS)·FOT-4(LLM 한정)가 이 태그를 기다리느라 막혀 있었다.
"""
from app.engine import bigmatch as B


def test_순위가_3계단_이내면_빅매치다():
    t = B.is_big_match(league="serie_a", home="AS Roma", away="AC Milan",
                       rank_home=2, rank_away=4)
    assert t.big and "3계단" in t.reason
    assert B.RANK_GAP == 3


def test_더비는_순위와_무관하다():
    t = B.is_big_match(league="serie_a", home="AS Roma", away="SS Lazio",
                       rank_home=2, rank_away=15)
    assert t.big and t.reason == "더비"
    # 이름 표기가 달라도 잡는다(정규화 후 비교).
    assert B.is_derby("serie_a", "as roma", "SS Lazio ")


def test_상위_6팀_간이면_빅매치다():
    t = B.is_big_match(league="serie_a", home="Juventus FC", away="SSC Napoli",
                       rank_home=6, rank_away=1)
    assert t.big and "상위 6팀" in t.reason
    assert B.TOP_N == 6


def test_아무것도_아니면_아니다():
    t = B.is_big_match(league="serie_a", home="US Lecce", away="AC Monza",
                       rank_home=14, rank_away=19)
    assert not t.big and "14위" in t.reason


def test_순위를_모르면_0위로_읽지_않는다():
    """🔴 모르는 것을 1위로 읽으면 전 경기가 빅매치가 된다."""
    t = B.is_big_match(league="serie_a", home="US Lecce", away="AC Monza")
    assert not t.big and "순위 모름" in t.reason
    # 순위를 몰라도 더비는 잡힌다.
    d = B.is_big_match(league="serie_a", home="AC Milan",
                       away="FC Internazionale Milano")
    assert d.big and d.reason == "더비"


def test_더비표는_설정_파일이_원본이다():
    import pathlib

    import yaml

    doc = yaml.safe_load(pathlib.Path("config/derbies.yaml").read_text())
    lgs = doc["derbies"]
    assert {"serie_a", "la_liga", "epl", "bundesliga"} <= set(lgs)
    # 사용자가 채울 자리는 비어 있어도 된다 — 빈 목록이 곧 "없다"다.
    assert lgs["kleague1"] == []
