"""[CARD-3] 손님상 카드 — 주방을 보여주지 않는다.

🔴 사용자 지시 2026-09-10: "갈림길 현지상황들을 저렇게 다 안 보여줘도 된다.
   우리는 어떤 근거로 이런 도출을 했다… 서술형으로 바꿔야 한다. 식당에서 음식을
   파는데 굳이 주방은 보여줄 필요가 없다."

종전 카드는 아홉 줄이 전부 "우리가 어떻게 만들었나"였다 — 자료 번호, 표본 수,
기반영 %p, 심의 메커니즘, 조사 이동폭. 숫자는 **문장 안에** 녹이고 내부 표기는
치운다.

⚠️ 헤더(확률·시장·가치)와 베팅 라벨은 **규칙이 만든다** — 숫자 지어내기 방지.
"""
from __future__ import annotations

import pytest


def _jg(**over):
    jg = {
        "sport": "mlb", "league": "MLB",
        "home": "Milwaukee Brewers", "away": "Chicago Cubs",
        "p_claude": 0.57, "p_market_send": 0.54, "lineup_status": "confirmed",
        "matchup": {"p_home": 0.57, "우세": "home", "확신도": "중",
                    "결론": {"승자": "Milwaukee Brewers", "판단": "홈 우세"},
                    "근거": ["헨더슨 최근 5경기 모두 6이닝+ (자료4)",
                             "컵스 타선 3경기 9득점 (자료1)",
                             "레이팅 36.2점 우위 (자료12)"],
                    "전개": {"분기점": "헨더슨이 6이닝 이상 막는가"},
                    "변수": ["불펜 피로 — 발생 시 원정 방향 약 3%p · 현재 p에 "
                             "1.5%p 기반영 · 근거 없음 — 보수 반영"]},
        "deepsearch": {"요약": "헨더슨 강세 유지", "이동_pp": -1.0},
        "situation_check": {"direction": "home", "verdict": "뒷받침"},
        "narrative_card": "밀워키가 이긴다고 본다. 헨더슨이 최근 5경기를 모두 "
                          "6이닝 이상 막아냈다.\n\n다만 불펜이 지쳐 있다.",
    }
    jg.update(over)
    return jg


def test_kitchen_is_hidden():
    """자료 번호·표본 수·기반영 %p·심의 메커니즘은 카드에 없다."""
    from app.engine.form_card import render_form_card

    body = render_form_card(_jg(), "mlb")
    for leak in ("자료4", "자료1", "자료12", "자료14",
                 "기반영", "리그 동류", "[상황·심의]", "🔍 추가 조사 반영",
                 "뉴스반영", "근거1", "변수 "):
        assert leak not in body, f"주방이 보인다: {leak}\n{body}"


def test_dish_is_served():
    """손님상에 나가야 할 것: 팀·확률·시장·가치·서술·베팅 라벨."""
    from app.engine.form_card import render_form_card

    body = render_form_card(_jg(), "mlb")
    assert "밀워키 브루어스" in body
    assert "57" in body                       # 확률
    assert "시장" in body and "54" in body     # 시장
    assert "밀워키가 이긴다고 본다" in body     # 서술
    assert "보드만" in body or "추천" in body   # 베팅 라벨


def test_falls_back_to_structured_card_without_narrative():
    """서술이 없으면 종전 구조 카드로 — 빈 카드를 내보내지 않는다."""
    from app.engine.form_card import render_form_card

    jg = _jg()
    jg.pop("narrative_card")
    body = render_form_card(jg, "mlb")
    assert "근거1" in body, "서술이 없는데 근거도 없으면 카드가 빈다"


@pytest.mark.asyncio
async def test_narrative_prompt_carries_everything(monkeypatch):
    """서술 생성에는 근거·갈림길·변수·조사·심의가 전부 들어간다."""
    from app.engine import narrative_card as nc

    seen = {}

    async def fake(prompt, **kw):
        seen["p"] = prompt
        return {"서술": "본문"}

    monkeypatch.setattr(nc, "_ask", fake)
    await nc.build(_jg())
    p = seen["p"]
    for must in ("헨더슨", "갈림길", "불펜 피로", "헨더슨 강세 유지", "뒷받침"):
        assert must in p, f"{must} 가 서술 재료에 없다"


@pytest.mark.asyncio
async def test_narrative_failure_returns_none(monkeypatch):
    """LLM 실패면 None — 카드가 구조 카드로 폴백한다."""
    from app.engine import narrative_card as nc

    async def dead(prompt, **kw):
        return None

    monkeypatch.setattr(nc, "_ask", dead)
    assert await nc.build(_jg()) is None


# ── [CARD-4 2026-09-10] 딥서치 발견을 서술이 분석한다 ────────────────────

@pytest.mark.asyncio
async def test_narrative_gets_findings_not_just_summary(monkeypatch):
    """🔴 사용자 지적: "딥서치한 거는 분석 안 하냐?"

    실측: 서술 프롬프트에 `deepsearch["요약"]` 한 줄만 넘어가고 `발견` 배열은
    버려졌다. 조사가 위성 40여 건 + PPLX 를 뒤져 찾은 사실들이 한 줄로 뭉개져,
    서술은 그것을 **인용**만 하고 의미를 해석하지 못했다.
    """
    from app.engine import narrative_card as nc

    seen = {}

    async def fake(prompt, **kw):
        seen["p"] = prompt
        return {"서술": "본문"}

    monkeypatch.setattr(nc, "_ask", fake)
    jg = _jg(deepsearch={
        "요약": "헨더슨 강세 유지",
        "발견": [{"사실": "바우어스 왼손 통증으로 결장 가능"},
                 {"사실": "컵스 선발이 미시오로스키로 교체됐다"}],
        "이동_pp": -1.0})
    await nc.build(jg)
    p = seen["p"]
    assert "바우어스 왼손 통증" in p, "발견 사실이 서술 재료에 없다"
    assert "미시오로스키" in p
    assert "의미" in p or "해석" in p, "조사를 해석하라는 지시가 없다"
