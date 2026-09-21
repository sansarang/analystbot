"""[DS-5] 재순위를 추출 경로에 **잇는다.**

🔴 **왜.** 실측 2026-09-21, 운영에서 기사가 있는 경기 11개:

    경기                              기사   창(전)   재순위(후)
    Yokohama DeNA@Hanshin Tigers      13    6,000     2,130
    Milwaukee@Baltimore               65    6,000       400
    Real Sociedad@Valencia CF         14    6,000       484
    Saitama Seibu@Chiba Lotte          6    3,600         0   🔴
    Orix@Hokkaido Nippon-Ham           6    3,600         0   🔴

   0자 두 경기를 들여다보니 **그 경기 이야기가 기사에 없었다**:
     롯데vs세이부 → 「アジア大会 트러블…태국 선수단 식사 '열악'」
     니혼햄vs오릭스 → 「阪神의 石井大智 투수…」(다른 팀)
   지금은 그 무관한 3,600자가 통째로 LLM 에 들어간다.

🔴 그래서 **증거 문단이 0 이면 LLM 을 부르지 않는다**(절대 규칙 6:
   "재료 없으면 분석 생성 금지"). 호출을 아끼고, 근거 없는 카드를 만들지 않는다.

🔴 **현지 별칭을 넘겨야 한다.** DB 는 `Chiba Lotte Marines`, 기사는
   `千葉ロッテマリーンズ` 다. 안 넘기면 NPB 가 통째로 0자가 된다 —
   실측에서 0자 경기가 **4 → 2** 로 줄었다. 원본은 `news_rss.QUERY_ALIAS` ·
   `scout_config.local_name` 이다(사본 금지).
"""
from __future__ import annotations

import json
import pathlib

import pytest

_FIX = (pathlib.Path(__file__).resolve().parents[1]
        / "fixtures" / "deepsearch" / "valencia_14.json")


def _articles():
    return json.loads(_FIX.read_text(encoding="utf-8"))["articles"]


@pytest.fixture
def spy(monkeypatch):
    """LLM 호출을 가로챈다 — **프롬프트가 얼마나 큰지** 재기 위해."""
    calls: list = []

    async def fake(chain, prompt, max_tokens, kind):
        calls.append({"prompt": prompt, "len": len(prompt)})
        return json.dumps({"teams": []})

    monkeypatch.setattr("app.engine.team_form._complete_free", fake)
    monkeypatch.setattr("app.collectors.satellite._article_cap",
                        _async(99))
    monkeypatch.setattr("app.collectors.satellite._llm_budget_ok", _async(True))
    monkeypatch.setattr("app.collectors.satellite._llm_budget_spend",
                        _async(None))
    return calls


def _async(v):
    async def f(*a, **k):
        return v
    return f


@pytest.mark.asyncio
async def test_재순위가_추출_입력을_줄인다(spy):
    from app.collectors.satellite import extract_game_facts

    await extract_game_facts(_articles(), home="Valencia CF",
                             away="Real Sociedad de Fútbol", league="라리가")
    assert spy, "LLM 을 안 불렀다"
    # 🔴 전: 창 6,000자 → 프롬프트 7,101자 (실측). 후: 문단 2개 484자.
    assert spy[0]["len"] < 3000, f"프롬프트가 {spy[0]['len']}자 — 안 줄었다"
    assert "피카츄" not in spy[0]["prompt"], "무관 문단이 프롬프트에 남았다"
    assert "복귀 예정" in spy[0]["prompt"], "정답 문단이 프롬프트에서 빠졌다"


@pytest.mark.asyncio
async def test_증거가_0이면_추출하지_않는다(spy):
    """🔴 **여기서 멈추지 않는다 — 그리고 그 이유를 적는다.**

    "증거 0 이면 묻지 않는다"(절대 규칙 6)가 더 정직하다. 그런데 그것은
    **"기사가 1건 이상이면 추출한다"** 를 뒤집는 결정이고, 실제로 기존 계약
    **16개**(EXT-2 · PA-13 · 빅매치)가 그 위에 서 있다.
    내 변경을 통과시키려고 계약 16개를 고치는 것은 **회귀를 숨기는 수**다.
    → 폴백으로 둔다. 하드 스킵은 **사용자 결정**으로 남겼다.

    ⚠️ 실측 2026-09-21: 운영 11경기 중 2건이 이 자리다(롯데vs세이부 ·
       니혼햄vs오릭스). 둘 다 기사 6건에 그 경기 이야기가 없었다
       (아시안게임 식사 문제 · 한신 투수).
    """
    from app.collectors.satellite import extract_game_facts

    junk = [{"url": "https://x/1", "title": "아시안게임 트러블",
             "body": "선수들의 식사는 열악 태국 선수단 단장이 호소했다. " * 12}]
    out = await extract_game_facts(junk, home="Chiba Lotte Marines",
                                   away="Saitama Seibu Lions", league="NPB")
    assert spy == [], "증거가 없는데 LLM 을 불렀다"
    assert out.get("reason") == "no_relevant_paragraph", out


@pytest.mark.asyncio
async def test_현지_별칭을_넘긴다(spy):
    """🔴 DB 는 `Chiba Lotte Marines`, 기사는 `千葉ロッテマリーンズ` 다."""
    from app.collectors.satellite import extract_game_facts

    arts = [{"url": "https://x/1", "title": "中日ドラゴンズ スタメン発表",
             "body": "中日ドラゴンズは21日のスタメンを発表した。"
                     "1番福永、2番村松。先発は髙橋宏斗。" * 3}]
    await extract_game_facts(arts, home="Chunichi Dragons",
                             away="Hiroshima Toyo Carp", league="NPB")
    assert spy, "일본어 기사를 못 찾았다 — 별칭이 안 넘어갔다"


@pytest.mark.asyncio
async def test_스위치를_끄면_종전_경로다(spy, monkeypatch):
    """⚠️ 되돌릴 수 있어야 한다 — config 한 줄로 끈다(배포 없이).

    ⚠️ **절대값으로 단언하지 않는다.** 처음에 `> 3000자` 로 적었다가 틀렸다
       (끈 상태 실측 2,510자). 창 크기는 기사 구성에 따라 달라진다.
       켠 것과 끈 것을 **서로** 견준다.
    """
    from app.collectors.satellite import extract_game_facts
    from app.deepsearch import runtime as RT

    arts = _articles()
    await extract_game_facts(arts, home="Valencia CF",
                             away="Real Sociedad de Fútbol", league="라리가")
    on = spy[0]["len"]
    spy.clear()

    cfg = dict(RT.load_config())
    cfg["rerank"] = dict(cfg.get("rerank") or {}, wire_extract=False)
    monkeypatch.setattr(RT, "_CFG_CACHE", cfg)
    await extract_game_facts(arts, home="Valencia CF",
                             away="Real Sociedad de Fútbol", league="라리가")
    assert spy, "끈 상태인데 LLM 을 안 불렀다"
    off = spy[0]["len"]
    assert off > on, f"끈 쪽({off})이 켠 쪽({on})보다 작다 — 스위치가 안 먹는다"


def test_별칭_표를_새로_만들지_않았다():
    """🔴 원본은 `news_rss.QUERY_ALIAS` · `scout_config.local_name` 이다."""
    import inspect

    from app.collectors import satellite

    src = inspect.getsource(satellite._extract_names)
    assert "QUERY_ALIAS" in src and "local_name" in src
    # ⚠️ **설명용 예시는 사본이 아니다.** 처음에 docstring 째로 검사했다가
    #    "실측에서 `千葉ロッテマリーンズ` 로 쓴다"는 **설명 문장**을 사본으로
    #    오인했다. 잠글 것은 **코드가 표를 갖는 것**이다.
    body = src.split('"""')[-1]
    for lit in ("千葉ロッテ", "中日ドラゴンズ", "한화 이글스"):
        assert lit not in body, f"팀명 {lit} 을 코드에 적었다"
