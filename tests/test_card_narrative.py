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


# ── [CARD-5 2026-09-10 사용자 지시] "날씨영향도.." ─────────────────────────
#   🔴 WX-2 로 카드 머리에 날씨 **수치**는 올랐지만, 서술은 날씨를 모른다.
#      실측: 서술 프롬프트에 날씨 칸이 아예 없다. 필라델피아 카드가 "외야 방향
#      바람"을 말한 것은 딥서치가 그 사실을 **우연히 찾았을 때**뿐이고, 조사가
#      날씨를 안 물으면 29도·강수 0% 를 눈앞에 두고도 한 줄도 못 쓴다.

@pytest.mark.asyncio
async def test_narrative_gets_weather(monkeypatch):
    from app.engine import narrative_card as nc

    seen = {}

    async def fake(prompt, **kw):
        seen["p"] = prompt
        return {"서술": "본문"}

    monkeypatch.setattr(nc, "_ask", fake)
    jg = _jg()
    jg["weather_card"] = {"temp_c": 29.0, "wind_ms": 4.6,
                          "precip_pct": 0, "wind_from_deg": 200}
    await nc.build(jg)
    p = seen["p"]
    assert "29" in p and "날씨" in p, "서술 재료에 날씨가 없다"
    assert "득점" in p, "날씨를 어떻게 읽어야 하는지 지시가 없다"


@pytest.mark.asyncio
async def test_narrative_without_weather_says_so(monkeypatch):
    """⚠️ 반대 위험 — 날씨가 없는데 있는 척하면 지어낸 것이다."""
    from app.engine import narrative_card as nc

    seen = {}

    async def fake(prompt, **kw):
        seen["p"] = prompt
        return {"서술": "본문"}

    monkeypatch.setattr(nc, "_ask", fake)
    await nc.build(_jg())
    assert "미수집" in seen["p"] or "없음" in seen["p"]


# ── [CARD-6 2026-09-10] 1차 카드는 서술을 받지 못했다 ─────────────────────
#   🔴 사용자 지적: "la 다저스는 또 왜 이렇게 나오냐?"
#      08:13 에 나간 CIN@LAD **1차 카드**가 종전 구조 카드 그대로였다.
#   실측(운영 캐시 `analysis:mlb:2026-09-09` 10경기): **서술 0/10 · 날씨 0/10.**
#      `narrative_card` 를 채우는 곳은 `_renarrate` 하나뿐인데(전수 grep),
#      그것은 재판정 3곳에서만 불린다 —
#        `_refresh_stale_research` · `rejudge_after_lineup` · `ensure_game_fresh`
#      슬레이트 본경로(프리페치→판정→1차 발송)는 서술을 **아예 만들지 않는다.**
#      그래서 사용자가 실제로 T-30 에 받는 첫 카드는 항상 구 형식이었다.
#   ⚠️ 서술은 딥서치 **뒤에** 만들어야 조사 사실을 해석할 수 있다.

def test_slate_path_builds_narrative_after_deepsearch():
    """배선 계약 — 딥서치 직후에 서술이 붙는가.

    구조 검사인 이유: 이 배선은 4천 줄짜리 함수 한가운데 있어 단위 호출로
    떼어낼 수 없다. 그래도 **빠지면 알려주는 것**이 없는 것보다는 낫다 —
    실제로 빠져 있었고 6일 넘게 아무도 몰랐다.
    """
    import pathlib
    import re

    src = pathlib.Path("app/pipeline.py").read_text()
    m = re.search(r"await run_for_slate\(.*?\)", src, re.S)
    assert m, "딥서치 슬레이트 호출을 못 찾았다"
    tail = src[m.end():m.end() + 1200]
    assert "_renarrate(" in tail, (
        "딥서치 뒤에 서술 생성이 없다 — 1차 카드가 구조 카드로 나간다")
