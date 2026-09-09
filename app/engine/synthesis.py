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

    # ③ 모순 — 상황 심의가 결론과 반대 방향인가.
    sit = jg.get("situation_check") or {}
    sdir = (sit.get("direction") or "").strip().lower()
    if sdir in ("home", "away") and sdir != side:
        who = _team(home if sdir == "home" else away)
        bits.append(f"다만 현지 상황은 {who} 쪽을 가리켜 근거와 반대다")

    # ④ 무엇이 이 픽을 깨는가 — 갈림길을 실전 문장으로.
    branch = ((m.get("전개") or {}).get("분기점") or "").strip()
    tail = f" 이 픽이 깨지는 지점은 «{branch}» 다." if branch else ""

    # ⑤ 조사가 답을 찾았는가 — 못 찾았으면 그것도 결과다.
    summary = str(ds.get("요약") or "").strip()
    if summary:
        tail += f" 조사: {summary}."

    return "🧭 종합 — " + " · ".join(bits) + "." + tail
