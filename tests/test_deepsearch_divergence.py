"""[DS-2] 괴리가 딥서치를 발동시키는데 **딥서치가 괴리를 묻지 않는다**.

🔴 **실측 2026-09-09.** MKT-7 로 `T2_시장괴리` 를 살렸다. 그런데 조사
   프롬프트의 체크리스트 ①~⑤ 어디에도 시장이 없다. 오히려 이렇게 적혀 있다:
       "🔴 배당·머니라인·스포츠북·시장 내재확률을 조사하지 마라.
          근거로도 쓰지 마라."
   즉 **T2 가 발동해도 조사는 아무것도 묻지 않는다.**

🔴 **그 금지는 옳다 — 이유가 실사고다.**
   "실측 2026-09-01: 조사가 스포츠북 머니라인 내재확률 51~53%를 근거로
    p_home 을 0.59→0.56 으로 내렸다. 추천 1건이 보드만으로 떨어졌다."
   그리고 나도 같은 사고를 다시 냈다 — MKT-4 에서 시장 확률을 판정 자료로
   줬더니 |p−시장| 이 **67.9% 수축**했다(반복 호출이 전부 동일값).
   **숫자를 보여주면 베낀다.** 그건 조사가 아니다.

✅ **그래서 가르는 선은 "숫자를 주느냐"가 아니라 "무엇의 근거로 쓰느냐"다.**
       시장 방향  = **검색 방향**   (어디를 팔지 알려준다)
       시장 숫자  = **근거 아님**   (조정 사유가 될 수 없다)
       조정 근거  = **발견한 사실만** (부상·결장·구속·날씨·로스터)
   사실을 못 찾으면 조정 0 이다. 못 찾았다는 것 자체가 결과다.

📐 왜 밖에서 찾아야 하는가 (실측 141경기):
       괴리 8%p 초과 60건 — 우리 50.0% · 시장 68.3%
       시장이 고른 팀은 최근5 승률 우위가 **39%**(오히려 열세)·득실차 47.5%
       변수가 시장 방향을 가리켰든(38건) 아니든(22건) 우리 적중률 **둘 다 50.0%**
   → 우리 수치로도, 판정이 스스로 적은 변수로도 설명되지 않는다.
      **원인은 수치가 아니라 정보다.**
"""
from __future__ import annotations

import pytest


def _prompt(**over):
    """실제 렌더 경로와 같은 인자로 프롬프트를 만든다."""
    from app.engine.deepsearch import T2_MARKET, build_prompt

    base = {"jg": {"sport": "mlb", "league": "MLB", "home": "H팀", "away": "A팀",
                   "starts_at_kst": "09/09 08:00",
                   "p_claude": 0.62, "p_market_send": 0.41,
                   "matchup": {"p_home": 0.62, "우세": "home", "근거": [],
                               "확신도": "중", "추가확인": []}},
            "trig": [T2_MARKET]}
    base.update(over)
    return build_prompt(base["jg"], base["trig"])


def test_T2가_걸리면_괴리를_묻는다():
    p = _prompt()
    assert "시장" in p and "21" in p, "괴리의 방향·크기가 프롬프트에 없다"
    assert "원정" in p, "시장이 어느 쪽을 보는지 없다"


def test_T2가_없으면_괴리_문단도_없다():
    """⚠️ 안 걸린 경기에 시장 이야기를 넣으면 그게 앵커가 된다."""
    from app.engine.deepsearch import T4_STARTER

    p = _prompt(trig=[T4_STARTER])
    assert "[🔴 시장 괴리" not in p


def test_조사는_허용하되_숫자를_사유로_쓰지_못한다():
    """🔴 [사용자 지시 2026-09-09] **조사 금지는 푼다.** 다만 실사고의 교훈은 남긴다.

    종전 문구는 "배당·머니라인·시장 내재확률을 **조사하지 마라**"였다. 그래서
    T2 가 발동해도 아무것도 못 물었다. 금지의 근거였던 사고를 다시 읽으면:
      "조사가 스포츠북 머니라인 내재확률 51~53%를 **근거로** p_home 을
       0.59→0.56 으로 내렸다"
    문제는 **조사**가 아니라 **숫자를 조정 사유로 쓴 것**이었다. 그래서
      조사한다   ← 시장이 왜 그렇게 봤는지 · 라인이 언제 움직였는지
      근거로는 못 쓴다 ← 시장 숫자 그 자체
      조정 근거  ← 발견한 **사실**만 (부상·결장·구속·날씨·로스터)
    """
    p = _prompt()
    assert "조사하지 마라" not in p, "조사 금지가 남아 있다 — 풀기로 했다"
    assert "사유가 될 수 없다" in p, \
        "숫자를 사유로 쓰는 것까지 풀렸다 — 그건 2026-09-01 사고다"
    assert "가격 자체" in p, "무엇이 금지인지가 구체적이지 않다"


def test_사실을_못_찾으면_조정하지_말라고_한다():
    p = _prompt()
    i = p.index("[🔴 시장 괴리")
    seg = p[i:i + 900]
    assert "조정" in seg and "0" in seg
    assert "미확인" in seg, "못 찾았을 때 무엇을 적을지가 없다"


def test_괴리가_없으면_문단이_없다():
    """시장값이 없거나 작으면 넣지 않는다 — 없는 것을 지어내지 않는다."""
    from app.engine.deepsearch import T2_MARKET

    p = _prompt(jg={"sport": "mlb", "league": "MLB", "home": "H", "away": "A",
                    "starts_at_kst": "", "p_claude": 0.55, "p_market_send": None,
                    "matchup": {"p_home": 0.55, "우세": "home", "근거": [],
                                "확신도": "중", "추가확인": []}},
                trig=[T2_MARKET])
    assert "[🔴 시장 괴리" not in p


# ── [DS-3 2026-09-10 사용자 지시] 전 경기 조사 + Perplexity 병행 ──────────

def test_every_game_is_investigated():
    """🔴 사용자 지시: "트리거 걸린 경기만 하지 말고 전부 다 해라."

    종전에는 T1~T5 가 하나도 안 걸리면 그 경기는 조사되지 않았다. 이제 아무것도
    안 걸려도 최소 1개(T0_전수)가 붙어 전 경기가 조사 대상이 된다.
    ⚠️ 상한(daily_cap)은 별개 축이고 이미 1.0(100%)이다.
    """
    from app.config import Settings
    from app.engine.deepsearch import T0_ALL, triggers

    s = Settings(_env_file=None)
    # 경계도 아니고 괴리도 없고 추가확인도 없는 '조용한' 경기
    quiet = {"sport": "kbo", "p_claude": 0.66, "home": "H", "away": "A",
             "matchup": {"p_home": 0.66, "우세": "home", "추가확인": []}}
    trig = triggers(quiet, s)
    assert trig, "조용한 경기가 조사에서 빠졌다 — 전수 조사가 아니다"
    assert T0_ALL in trig


def test_t0_does_not_mask_real_triggers():
    """전수 트리거가 붙어도 진짜 트리거는 그대로 보인다(원인 추적이 죽지 않게)."""
    from app.config import Settings
    from app.engine.deepsearch import T0_ALL, T3_ASKED, triggers

    s = Settings(_env_file=None)
    jg = {"sport": "kbo", "p_claude": 0.66, "home": "H", "away": "A",
          "matchup": {"p_home": 0.66, "우세": "home", "추가확인": ["선발 컨디션"]}}
    trig = triggers(jg, s)
    assert T3_ASKED in trig
    assert T0_ALL in trig          # 함께 붙되
    assert trig[0] != T0_ALL       # 전수는 맨 뒤(진짜 트리거가 앞)


@pytest.mark.asyncio
async def test_pplx_findings_are_injected_as_material(monkeypatch):
    """🔴 사용자 지시: "퍼플렉시티도 딥서치에 연결해라."

    PPLX 가 찾은 사실이 **재료**로 프롬프트에 들어간다. 확률 조정은 여전히
    기존 요약기(무료 사슬)가 정한다 — PPLX 에 판정을 넘기지 않는다.
    """
    from app.engine import deepsearch

    async def fake_pplx(prompt, **kw):
        return {"발견": [{"사실": "선발 A가 우측 팔꿈치 통증으로 결장 예정",
                          "소스유형": "뉴스", "url": "https://x"}]}

    monkeypatch.setattr(deepsearch, "_pplx_findings", fake_pplx)
    jg = {"sport": "mlb", "league": "MLB", "home": "H", "away": "A",
          "p_claude": 0.55, "matchup": {"p_home": 0.55, "우세": "home"}}
    arts = await deepsearch._pplx_articles(jg)
    assert arts, "PPLX 사실이 재료로 변환되지 않았다"
    a = arts[0]
    for k in ("title", "source", "age_h", "team", "body"):
        assert k in a, f"{k} 키가 없다 — _inject_articles 가 렌더하지 못한다"
    assert "팔꿈치" in a["body"]
    assert a["source"].startswith("Perplexity")


@pytest.mark.asyncio
async def test_pplx_failure_is_silent(monkeypatch):
    """PPLX 가 죽어도(크레딧 소진·타임아웃) 조사는 무료 사슬로 계속된다."""
    from app.engine import deepsearch

    async def dead(prompt, **kw):
        return None

    monkeypatch.setattr(deepsearch, "_pplx_findings", dead)
    jg = {"sport": "mlb", "home": "H", "away": "A", "p_claude": 0.5,
          "matchup": {"p_home": 0.5, "우세": "home"}}
    assert await deepsearch._pplx_articles(jg) == []
