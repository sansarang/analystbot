"""[DS-10] 종합 판단 — 카드 마지막에 "그래서 누가 이긴다"를 남긴다.

🔴 **왜 필요한가 (사용자 지적 2026-09-10).**
   "분석은 다 됐어. 그래서 종합평가는? 그래서 이렇게 됐으니 누가 이길 것이라는
    서술이 있어야 해."
   "자료가 사용자가 선택하게 하지 말고 결정은 AI 가 다 해야 한다."

   실측(TB@ATL): 카드가 결론(원정 승)·근거 3줄·갈림길·변수 2줄·조사·뉴스반영·
   심의(홈 강화)를 나열했는데 **결론과 심의가 정면으로 충돌**했다. 아무도
   정리하지 않으니 사용자가 여섯 조각을 들고 스스로 판단해야 했다.

🔴 **뼈대는 규칙이다.** 확률·이동·시장 괴리·모순 여부는 전부 **기존 값에서**
   꺼내 조립한다 — 지어내기가 구조적으로 불가능하다. 마지막 실전 판단 한 줄만
   나중에 LLM 이 쓴다(다음 증분).

⚠️ **확률과 게이트는 건드리지 않는다.** 종합은 서술이지 계산이 아니다.
   조사·심의가 결론과 반대라도 여기서는 그 사실을 **말할** 뿐이고, p_home 과
   추천 라벨은 기존 경로가 정한 그대로다.
"""
from __future__ import annotations


def _team(name: str) -> str:
    from app.bot.aliases import kr_team

    return kr_team(name or "?")


def _favored(jg: dict) -> tuple[str | None, float | None]:
    """우세 사이드와 그 확률. form_card 와 같은 규약을 쓴다(사본 금지)."""
    from app.engine.form_card import favored_side_and_p

    return favored_side_and_p(jg)


def synthesize(jg: dict) -> str | None:
    """종합 문단. 판정이 없으면 None(없는 것을 지어내지 않는다)."""
    m = jg.get("matchup") or {}
    side, p = _favored(jg)
    if side is None or p is None:
        return None

    home, away = jg.get("home") or "", jg.get("away") or ""
    fav_name = _team(home if side == "home" else away)
    bits: list[str] = []

    # ① 최종 확률 — 조사가 움직였으면 그 폭을 함께 적는다.
    ds = jg.get("deepsearch") or {}
    moved = ds.get("이동_pp")
    head = f"{fav_name} 우세 {p * 100:.0f}%"
    if isinstance(moved, (int, float)) and abs(float(moved)) > 1e-9:
        head += f" (조사 반영 {float(moved):+.1f}%p)"
    bits.append(head)

    # ② 시장과의 관계 — 홈 기준끼리 비교한다(MKT-9 와 같은 규약).
    mkt = jg.get("p_market_send")
    p_home = m.get("p_home")
    if p_home is None:
        p_home = jg.get("p_claude")
    if mkt is not None and p_home is not None:
        gap = (float(p_home) - float(mkt)) * 100
        rel = "시장도 같은 쪽" if abs(gap) < 4.0 else "시장은 다른 쪽"
        bits.append(f"{rel}({abs(gap):.0f}%p 차)")

    # ③ 현지 상황 — **동의든 반대든 말한다.** 침묵은 고려가 아니다
    #    (사용자 지시 2026-09-10: "심의가 같은 방향일 때도 명시해라").
    #    실측(CHC@MIL): 심의가 같은 방향이라 종합이 아예 언급하지 않아
    #    사용자가 "심의를 보긴 했나"를 알 수 없었다.
    sit = jg.get("situation_check") or {}
    sdir = (sit.get("direction") or "").strip().lower()
    if sdir in ("home", "away"):
        who = _team(home if sdir == "home" else away)
        if sdir != side:
            bits.append(f"다만 현지 상황은 {who} 쪽을 가리켜 근거와 반대다")
        else:
            bits.append(f"현지 상황도 {who} 쪽을 뒷받침한다")

    # ④ 무엇이 이 픽을 깨는가 — 갈림길을 실전 문장으로.
    branch = ((m.get("전개") or {}).get("분기점") or "").strip()
    tail = f" 이 픽이 깨지는 지점은 «{branch}» 다." if branch else ""

    # ⑤ 조사가 답을 찾았는가 — 못 찾았으면 그것도 결과다.
    summary = str(ds.get("요약") or "").strip()
    if summary:
        tail += f" 조사: {summary}."

    return "🧭 종합 — " + " · ".join(bits) + "." + tail


# ── [DS-11 2026-09-10 사용자 지시] 판단 한 줄 ────────────────────────────
#   🔴 규칙 뼈대만으로는 값을 옮길 뿐 **견줘본 판단**이 없다. 실측(CHC@MIL):
#      종합이 갈림길 문장과 조사 문장을 통째로 재인용했고, 근거1이 갈림길의
#      답을 이미 갖고 있다는 사실(Henderson 최근 5경기 전부 6이닝+)을 아무도
#      말하지 않았다. 사용자 지적: "고려해서 종합을 낸 것 같냐?"
#   ⚠️ 숫자는 **여기서 만들지 않는다.** 뼈대가 이미 다 적었고, 이 줄은 그것들이
#      서로 지지하는지 충돌하는지만 말한다.

#: [DS-13 2026-09-10 사용자 지시] **종합은 최종 판정과 같은 사슬로.**
#  "최종 결론 글도 gemini로 해라."
#  실측 사슬: deepsearch = nvidia→groq→openrouter (**gemini 없음**)
#            matchup    = **gemini/gemini-3.7-flash** → groq
#  종합은 카드의 마지막 판단이므로 조사 요약이 아니라 판정과 같은 급을 쓴다.
#  ⚠️ matchup 은 유료(anthropic)가 허용되는 유일한 역할이다 — `_verdict_line`
#     이 anthropic 을 걸러 유료로 새지 않는다(계약 테스트가 잠근다).
VERDICT_ROLE = "matchup"


_VERDICT_PROMPT = """아래는 한 야구 경기의 분석 조각들이다. 조각을 **서로 견줘**
한 문장으로 실전 판단을 써라.

[우세] {fav} {pct}
[결론 근거]
{reasons}
[갈림길] {branch}
[변수]
{variables}
[조사 결과] {ds}
[현지 상황 심의] {sit}
[시장] {market}

써야 할 것 — 다음을 **한 문장**에 담아라:
- 근거·갈림길·조사·심의가 서로 **지지하는가 충돌하는가**
- 그래서 이 확률을 믿을 만한가, 무엇이 발목을 잡는가

🔴 규칙
- **새 수치를 만들지 마라.** 위에 없는 숫자·이름을 쓰면 안 된다.
- 위 문장을 그대로 베끼지 마라. **관계를 말하라.**
- 한국어 한 문장, 120자 이내.

[출력] 아래 JSON만 출력한다. 다른 텍스트, 마크다운 백틱 금지.
{{"판단": "한 문장"}}"""


async def _verdict_line(prompt: str, *, max_tokens: int = 300) -> str | None:
    """무료 사슬 1콜. 실패하면 None — 뼈대만 나간다."""
    from app.config import get_settings
    from app.engine.team_form import _complete_free
    from app.llm.judge_route import chain

    routes = [r for r in chain(VERDICT_ROLE) if r[0] != "anthropic"]
    if not routes:
        return None
    try:
        import asyncio

        body = await asyncio.wait_for(
            _complete_free(routes, prompt, max_tokens, VERDICT_ROLE), timeout=45)
    except Exception:
        return None
    # 🔴 [DS-12] `_complete_free` 는 **JSON 파싱까지가 성공 조건**이다(의도된
    #    설계 — Nemotron 이 영어 사고문을 돌려주는 회차를 걸러낸다). 실측
    #    2026-09-10: 평문을 요구했더니 groq 가 좋은 문장을 냈는데도
    #    "응답이 JSON 이 아니다"로 통째로 버려졌다. 그래서 JSON 으로 받는다.
    from app.engine.team_form import parse_json_object

    data = parse_json_object(body or "")
    if isinstance(data, dict):
        got = str(data.get("판단") or "").strip()
        if got:
            return got
    return (body or "").strip() or None


def _verdict_prompt(jg: dict) -> str:
    m = jg.get("matchup") or {}
    side, p = _favored(jg)
    home, away = jg.get("home") or "", jg.get("away") or ""
    ds = jg.get("deepsearch") or {}
    sit = jg.get("situation_check") or {}
    mkt, p_home = jg.get("p_market_send"), (m.get("p_home") or jg.get("p_claude"))
    market = "미수집"
    if mkt is not None and p_home is not None:
        market = f"시장 {float(mkt):.0%} vs 우리(홈) {float(p_home):.0%}"
    return _VERDICT_PROMPT.format(
        fav=_team(home if side == "home" else away),
        pct=f"{(p or 0) * 100:.0f}%",
        reasons="\n".join(f"  - {x}" for x in (m.get("근거") or [])[:3]) or "  - (없음)",
        branch=((m.get("전개") or {}).get("분기점") or "(없음)"),
        variables="\n".join(f"  - {x}" for x in (m.get("변수") or [])[:2]) or "  - (없음)",
        ds=(ds.get("요약") or "(조사 없음)"),
        sit=(sit.get("summary") or sit.get("verdict") or "(심의 없음)"),
        market=market)


async def synthesize_async(jg: dict) -> str | None:
    """규칙 뼈대 + LLM 판단 한 줄. LLM 이 실패하면 뼈대만."""
    base = synthesize(jg)
    if not base:
        return None
    line = await _verdict_line(_verdict_prompt(jg))
    if not line:
        return base
    line = " ".join(line.split())[:160]
    return f"{base}\n   → {line}"
