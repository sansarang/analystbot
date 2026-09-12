"""[ORD-12 · 3단계] **조사 결과만으로 승자를 낸다.** DB 는 4단계다.

사용자 지시 2026-09-12: "ai가 db 참조 승패를 예측한다" · "나로 해라..확신 한
칸만 살려라"

🔴 ORD-3 에서 지운 것 중 **`확신` 하나만** 되살린다. 그건 설명이 아니라
   라벨이고, 4단계에서 DB 와 모순이 났을 때 낮출 곳이 필요하다. 확률·근거·
   변수·전개는 여전히 없다.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 확신 눈금. 원본은 `prompts.MATCHUP` 의 `확신도` 다 — 새 눈금을 만들지 않는다.
LEVELS = ("상", "중", "하")


def level(raw) -> str:
    """모르는 라벨은 `하` 로 떨어뜨린다.

    🔴 그대로 실으면 카드가 못 읽는다. 낮은 쪽이 안전한 방향이다 — 확신을
       높게 쓰는 것이 이 구조에서 가장 나쁜 실패다.
    """
    t = str(raw or "").strip()
    return t if t in LEVELS else "하"


def fmt_kept(rows: list[dict]) -> str:
    """채택 자료를 번호 붙여 싣는다. 원문 그대로 — 다시 쓰지 않는다."""
    out = []
    for i, r in enumerate(rows or [], 1):
        src = r.get("소스") or ""
        acct = f" {r.get('계정')}" if r.get("계정") else ""
        when = f"[{r.get('시점')}] " if r.get("시점") else ""
        out.append(f"{i}. [{src}{acct}] {when}"
                   + " ".join(str(r.get("답") or "").split())[:300])
    return "\n".join(out) or "(없음)"


def fmt_branches(items: list[dict]) -> str:
    out = []
    for i, b in enumerate(items or [], 1):
        q = str((b or {}).get("질문") or "").strip()
        if q:
            out.append(f"{i}. {q}")
    return "\n".join(out) or "(없음)"


def fmt_missing(items: list[str]) -> str:
    return "\n".join(f"· {x}" for x in (items or [])) or "(없음)"


def render(jg: dict, brief: str, tri: dict) -> str:
    """③-a 프롬프트. **자료1~14 가 들어가지 않는다.**"""
    from app.engine.deepsearch import _today_kst
    from app.engine.prompts import JUDGE2, fill

    return fill(JUDGE2,
                LEAGUE=jg.get("league") or (jg.get("sport") or "").upper(),
                AWAY=jg.get("away") or "", HOME=jg.get("home") or "",
                TODAY=_today_kst(), BRIEF=brief or "(없음)",
                BRANCHES=fmt_branches(tri.get("갈림길")),
                KEPT=fmt_kept(tri.get("채택")),
                MISSING=fmt_missing(tri.get("없는것")))


async def decide(jg: dict, brief: str, tri: dict, *,
                 role: str | None = None) -> dict | None:
    """③-a 판정. 반환 `{"승자","확신"}` 또는 None.

    🔴 **채택 0 건이면 판정하지 않는다.** 2단계가 전부 기각했다는 뜻이고,
       팀 이름 위에서 승자를 고르는 것이 곧 "기억으로 판정하기"다
       (절대 규칙 6: 재료 없으면 분석 생성 금지).
    ⚠️ 실패는 None 이다. 호출부(5단계)가 탈락 처리한다 — 여기서 지어내지 않는다.
    """
    from app.config import get_settings
    from app.engine.team_form import complete_json, parse_json_object
    from app.llm.judge_route import PRELIM_ROLE

    if not (tri or {}).get("채택"):
        logger.warning("[verdict] %s@%s 채택 0건 — 판정하지 않는다",
                       jg.get("away"), jg.get("home"))
        return None
    s = get_settings()
    prompt = render(jg, brief, tri)
    try:
        text = await complete_json(prompt, model=s.matchup_model,
                                   max_tokens=int(s.matchup_max_tokens),
                                   role=role or PRELIM_ROLE, mock=False)
    except Exception as exc:
        logger.warning("[verdict] 호출 실패 %s@%s: %s",
                       jg.get("away"), jg.get("home"), exc)
        return None
    parsed = parse_json_object(text or "")
    if not isinstance(parsed, dict) or not str(parsed.get("승자") or "").strip():
        logger.warning("[verdict] 승자 없음 %s@%s · %d자: %.200s",
                       jg.get("away"), jg.get("home"), len(text or ""),
                       (text or "").replace("\n", " ")[:200])
        return None
    out = {"승자": str(parsed["승자"]).strip(), "확신": level(parsed.get("확신"))}
    logger.info("[verdict] %s@%s 승자 %s · 확신 %s (채택 %d · 없는것 %d)",
                jg.get("away"), jg.get("home"), out["승자"], out["확신"],
                len(tri.get("채택") or []), len(tri.get("없는것") or []))
    return out
