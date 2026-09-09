"""[CARD-3] 손님상 카드 — 주방을 보여주지 않는다.

🔴 **사용자 지시 2026-09-10.**
   "갈림길 현지상황들을 저렇게 다 안 보여줘도 된다. 우리는 어떤 근거로 이런
    도출을 했다… 서술형으로 바꿔야 하고. 식당에서 음식을 파는데 굳이 주방은
    보여줄 필요가 없다."

   종전 카드는 아홉 줄이 전부 "우리가 어떻게 만들었나"였다 — 자료 번호(자료4·
   자료12), 표본 수(리그 동류 238), 기반영 %p, 조사 이동폭, 심의 메커니즘.
   손님은 요리를 받고 싶은데 조리 과정을 읽고 있었다.

   숫자는 **문장 안에** 녹이고 내부 표기는 치운다.

⚠️ 헤더(확률·시장·가치)와 베팅 라벨은 **규칙이 만든다** — 서술이 숫자를 지어낼
   수 없게 하는 유일한 방어선이다. 이 모듈은 본문 두 문단만 만든다.
⚠️ 실패하면 None → 카드는 종전 구조 카드로 폴백한다(회귀 없음).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 최종 판정과 같은 사슬(gemini 우선). DS-13 과 같은 이유다 — 손님에게 나가는
#  글은 조사 요약이 아니라 판정 급이어야 한다.
NARRATIVE_ROLE = "matchup"

_PROMPT = """당신은 스포츠 분석 카드를 쓰는 필자다. 아래 내부 자료를 읽고
**독자에게 나갈 본문**을 쓴다.

[경기] {away} (원정) @ {home} (홈)
[우리 판정] {fav} 우세 {pct}
[시장] {market}
[근거]
{reasons}
[승부의 갈림길] {branch}
[리스크 변수]
{variables}
[추가 조사 결과] {ds}
[현지 상황 심의] {sit}

🔴 **쓰는 법**
1문단 — **왜 이 팀이 이긴다고 보는가.** 근거를 이야기로 풀어라. 구체적인
        숫자(이닝·득점·레이팅)는 문장 안에 자연스럽게 녹인다.
2문단 — **무엇이 이 판단을 흔드는가.** 갈림길과 리스크를 말하고, 조사·현지
        상황이 그것을 지지하는지 반박하는지 함께 적는다.

🔴 **금지**
- "자료4", "자료12", "리그 동류 표본", "기반영", "심의", "딥서치" 같은
  **내부 용어를 쓰지 마라.** 독자는 우리 시스템을 모른다.
- 위 자료에 **없는 숫자·선수 이름을 만들지 마라.**
- 확률을 다시 말하지 마라(카드 머리에 이미 있다).
- 각 문단 2~4문장. 한국어. 담백하게.

[출력] 아래 JSON만 출력한다. 다른 텍스트, 마크다운 백틱 금지.
{{"서술": "1문단\\n\\n2문단"}}"""


async def _ask(prompt: str, *, max_tokens: int = 1200) -> dict | None:
    """무료 사슬(gemini 우선) 1콜 → JSON dict. 실패하면 None.

    ⚠️ `matchup` 은 유료(anthropic)가 허용되는 유일한 역할이라 명시적으로 뺀다 —
       카드 본문 한 편에 유료 호출이 붙으면 안 된다.
    """
    import asyncio

    from app.engine.team_form import _complete_free, parse_json_object
    from app.llm.judge_route import chain

    routes = [r for r in chain(NARRATIVE_ROLE) if r[0] != "anthropic"]
    if not routes:
        return None
    try:
        body = await asyncio.wait_for(
            _complete_free(routes, prompt, max_tokens, NARRATIVE_ROLE), timeout=60)
    except Exception:
        return None
    got = parse_json_object(body or "")
    return got if isinstance(got, dict) else None


def _prompt(jg: dict) -> str:
    from app.engine.form_card import favored_side_and_p

    m = jg.get("matchup") or {}
    side, p = favored_side_and_p(jg)
    home, away = jg.get("home") or "", jg.get("away") or ""
    ds = jg.get("deepsearch") or {}
    sit = jg.get("situation_check") or {}
    mkt, p_home = jg.get("p_market_send"), (m.get("p_home") or jg.get("p_claude"))
    market = "미수집"
    if mkt is not None and p_home is not None:
        gap = (float(p_home) - float(mkt)) * 100
        market = (f"시장은 홈 {float(mkt):.0%} — 우리와 {abs(gap):.0f}%p 차이"
                  + ("(같은 방향)" if abs(gap) < 4 else "(다른 방향)"))
    return _PROMPT.format(
        home=home, away=away,
        fav=(home if side == "home" else away),
        pct=f"{(p or 0) * 100:.0f}%",
        market=market,
        reasons="\n".join(f"  - {x}" for x in (m.get("근거") or [])[:3]) or "  - (없음)",
        branch=((m.get("전개") or {}).get("분기점") or "(없음)"),
        variables="\n".join(f"  - {x}" for x in (m.get("변수") or [])[:2]) or "  - (없음)",
        ds=(ds.get("요약") or "(조사 없음)"),
        sit=(sit.get("summary") or sit.get("verdict") or "(심의 없음)"))


async def build(jg: dict) -> str | None:
    """카드 본문 두 문단. 실패하면 None(구조 카드로 폴백)."""
    m = jg.get("matchup") or {}
    if not m:
        return None
    data = await _ask(_prompt(jg))
    if not isinstance(data, dict):
        return None
    text = str(data.get("서술") or "").strip()
    if not text:
        return None
    logger.info("[narrative] game=%s 서술 %d자", jg.get("game_id"), len(text))
    return text
