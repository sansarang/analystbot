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
    # [BIG-2] 사용자가 K리그1·J1·덴마크를 채웠다.
    assert len(lgs["kleague1"]) == 4 and len(lgs["j1"]) == 4
    assert len(lgs["denmark"]) == 2


# ── BIG-2: 태그를 FOT-3·FOT-4 에 연결

import json  # noqa: E402

import pytest  # noqa: E402

from app.collectors import satellite as SAT  # noqa: E402
from app.collectors import satellite_soccer as SOC  # noqa: E402


def test_초기값_더비가_리그별로_있다():
    """사용자가 준 목록 — K리그1 4 · J1 4 · 덴마크 2."""
    assert B.is_derby("kleague1", "Ulsan Hyundai FC", "Pohang Steelers")
    assert B.is_derby("kleague1", "Jeonbuk Hyundai Motors", "Ulsan Hyundai FC")
    assert B.is_derby("j1", "Gamba Osaka", "Cerezo Osaka")
    assert B.is_derby("j1", "Tokyo Verdy", "FC Tokyo")
    assert B.is_derby("denmark", "FC Copenhagen", "Brondby IF")
    assert not B.is_derby("kleague1", "Daegu", "Gwangju FC")


@pytest.mark.asyncio
async def test_빅매치가_아니어도_LLM_추출을_한다(monkeypatch):
    """🔴 [EXT-2 / STEP 1-g 2026-09-20] **BIG-2 의 "빅매치에만" 은 폐기됐다.**

    종전 계약: 빅매치가 아니면 구조 JSON 만으로 간다.
    뒤집은 이유(사용자 결정 `two_gates_0920`): 그 조건이 **구경로 게이트**와
    함께 추출을 갈랐고, 흐름의 가설이 수집에 닿지 못했다.
    실측 2026-09-20 KBO 5경기 — 기사 6~14건을 모으고 `out` 이 찬 것은 한 경기뿐.

    ⚠️ 무료 한도는 **다른 장치로** 막는다 — 경기당 기사 상한(depth)과
       일일 LLM 상한. `test_ext2_extract_all_games.py` 가 그것을 잰다.
    """
    calls = []

    async def _f(routes, prompt, max_tokens, role):
        calls.append(prompt)
        return json.dumps({"teams": []}, ensure_ascii=False)

    monkeypatch.setattr("app.engine.team_form._complete_free", _f)
    # ⚠️ [DEC-3] 본문에 증거 낱말·팀 이름을 넣는다 — 새 규칙이 "관련 문단
    #    ≥1 일 때만 추출"이라 증거 없는 픽스처는 이 시험의 대상에 닿지 못한다.
    #    시험하는 것(빅매치가 아니어도 부르는가)은 **그대로다**.
    arts = [{"team": "US Lecce", "url": "https://www.gazzetta.it/a",
             "body": "US Lecce 경기 프리뷰 — 오늘 선발 라인업이 발표됐고 "
                     "결장 선수는 없는 것으로 확인됐다 " * 3}]

    await SAT.extract_game_facts(arts, home="US Lecce", away="AC Monza",
                                 league="serie_a",
                                 jg={"rank_home": 14, "rank_away": 19})

    assert calls, "빅매치가 아니라고 추출을 건너뛰었다"


@pytest.mark.asyncio
async def test_빅매치면_LLM_을_부른다(monkeypatch):
    calls = []

    async def _f(routes, prompt, max_tokens, role):
        calls.append(prompt)
        return json.dumps({"teams": [{"team": "AS Roma", "out": []}]},
                          ensure_ascii=False)

    monkeypatch.setattr("app.engine.team_form._complete_free", _f)
    arts = [{"team": "AS Roma", "url": "https://www.gazzetta.it/a",
             "body": "AS Roma 경기 프리뷰 — 오늘 선발 라인업이 발표됐고 "
                     "결장 선수는 없는 것으로 확인됐다 " * 3}]

    await SAT.extract_game_facts(arts, home="AS Roma", away="SS Lazio",
                                 league="serie_a", jg={})

    assert len(calls) == 1, "더비는 순위를 몰라도 빅매치다"


def test_둘_다_미상인_빅매치를_표시한다():
    """Phase D3(구단 공식 RSS)가 붙을 자리 — 지금은 대상 수를 센다."""
    jg = {"home": "AS Roma", "away": "SS Lazio",
          "fotmob": {"home": {"unavailable": None}, "away": {"unavailable": None},
                     "missing": ["home 결장 명단 미제공", "away 결장 명단 미제공"]}}

    rep = SOC.cross_check_unavailable(jg, {}, league_key="serie_a")

    assert "빅매치" in rep["home"] and "빅매치" in rep["away"]
    assert any("빅매치 · 더비" in m for m in jg["fotmob"]["missing"])
