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

#: [SOC-2] 3-way 결과 라벨. 축구는 무승부가 **정상 결과**다.
#  🔴 이 셋이 원본이다 — 프롬프트·판정·카드가 전부 여기를 쓴다.
#     문자열을 손으로 옮겨 적으면 한쪽만 고쳐진다.
THREEWAY = ("홈승", "무", "원정승")
DRAW = "무"

#: 재요청 상한. 🔴 원본은 `websearch.MAX_ASKS` — 숫자를 두 곳에 적지 않는다.
from app.collectors.websearch import MAX_ASKS as _MAX_ASKS  # noqa: E402


def shadow_level(raw) -> str:
    """LLM 자기신고 등급을 **라벨로만** 정규화한다. 🔴 섀도 전용이다.

    🔴 [P0-1 2026-09-15] 이 값은 **카드에 실리지 않는다.** 원장의
       `llm_level` 로만 간다 — "무료 판정이 얼마나 틀리는가"를 재는 칸이다.
       카드로 가는 등급은 `level(raw, expected)` 를 거친 코드 등급뿐이다.
    ⚠️ 모르는 라벨은 `하` 로 떨어뜨린다. 낮은 쪽이 안전하다.
    """
    t = str(raw or "").strip()
    return t if t in LEVELS else LEVELS[-1]


def level(raw, expected: str):
    """[CONF-1] 등급은 **코드가 정하고**, LLM 출력은 그것과 같은지만 본다.

    🔴 사용자 결정(1차 결정 3): 종전에는 이 함수가 라벨 정규화만 하고 등급은
       LLM 자기신고였다 — AUC 0.5122 짜리 판정에 AI 가 붙인 등급을 그대로
       실어 보냈다.
    🔴 [P0-1 2026-09-15 사용자 지시] `expected` 는 **필수**다. 종전에는 기본값
       `None` 이 있었고, 그 모양이 곧 빠져나갈 구멍이었다 — `decide()` 가
       `level(parsed.get("확신"))` 로 불러 자기신고를 그대로 통과시켰고,
       7432 가 "파르마 승 · 확신 상"으로 나왔다. 기본값을 없애 **부르는 쪽이
       기대값을 대지 않으면 터지게** 한다. 정규화만 필요하면 `shadow_level`.
    🔴 다르면 `None` — 호출부가 반려한다. 모르는 라벨을 조용히 `하` 로
       떨어뜨리지 않는다.
    """
    if expected is None:
        raise ValueError("level() 은 expected 가 필수다 — 정규화는 shadow_level()")
    t = str(raw or "").strip()
    return t if t == expected else None


#: 기사 한 줄의 상한. 🔴 [PRM-2] **DB 행에는 쓰지 않는다.**
_NEWS_CAP = 300


def fmt_kept(rows: list[dict]) -> str:
    """채택 자료를 번호 붙여 싣는다. 원문 그대로 — 다시 쓰지 않는다.

    🔴 [PRM-2] **상한을 소스로 가른다.** 300자는 기사 한 줄에 맞춘 값인데
       DB 행(실측 1331자)이 같은 줄로 들어가 `{"home": …}` 까지만 남고
       `"away"` 가 통째로 사라졌다. 실측 2026-09-13(Seattle@Athletics):
       프롬프트에 `선발등판` 이 1회뿐이었고(두 블록이면 2회), 복사만 시키는
       분리 실험에서도 모델이 "없음"이라 답했다 — 정말 없었다.
    ⚠️ DB 행의 길이 원본은 `dbref.ITEM_MAX` 다. 숫자를 두 곳에 적지 않는다.
    """
    from app.engine import dbref

    out = []
    for i, r in enumerate(rows or [], 1):
        src = r.get("소스") or ""
        acct = f" {r.get('계정')}" if r.get("계정") else ""
        when = f"[{r.get('시점')}] " if r.get("시점") else ""
        cap = dbref.ITEM_MAX if src == dbref.SOURCE else _NEWS_CAP
        out.append(f"{i}. [{src}{acct}] {when}"
                   + " ".join(str(r.get("답") or "").split())[:cap])
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

    # 🔴 [SRCH-7] **DB 항목 이름을 프롬프트에 손으로 적지 않는다** — 원본은
    #    `dbref.ITEMS` 다. 손으로 옮기면 항목이 늘 때 프롬프트만 옛것이 된다.
    from app.engine.dbref import ITEMS as _ITEMS

    menu = "\n".join(f"      · {n}" for n, _ in _ITEMS)
    return fill(JUDGE2, DB_MENU=menu,
                LEAGUE=jg.get("league") or (jg.get("sport") or "").upper(),
                AWAY=jg.get("away") or "", HOME=jg.get("home") or "",
                TODAY=_today_kst(), BRIEF=brief or "(없음)",
                BRANCHES=fmt_branches(tri.get("갈림길")),
                KEPT=fmt_kept(tri.get("채택")),
                MISSING=fmt_missing(tri.get("없는것")))


async def decide(jg: dict, brief: str, tri: dict, *,
                 role: str | None = None) -> dict | None:
    """③-a 판정. 반환 `{"승자","확신","서술"}` 또는 None.

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
    # 🔴 [SRCH-6] 서술은 **선택 칸**이다 — 없어도 판정은 산다. 승자가 본체다.
    #    사용자 지시 2026-09-12: "제미니가 분석한 글을 그대로 보여달라고 해라".
    out = {"승자": str(parsed["승자"]).strip(), "확신": shadow_level(parsed.get("확신")),   # 🔴 섀도 — 카드로 안 간다
           "서술": " ".join(str(parsed.get("서술") or "").split()),
           # 🔴 [SRCH-7] 재요청. **코드가 자른다** — 상한 원본은 websearch 다.
           "추가요청": [str(x).strip() for x in (parsed.get("추가요청") or [])
                        if str(x).strip()][:_MAX_ASKS]}
    logger.info("[verdict] %s@%s 승자 %s · 확신 %s · 서술 %d자 (채택 %d · 없는것 %d)",
                jg.get("away"), jg.get("home"), out["승자"], out["확신"],
                len(out["서술"]), len(tri.get("채택") or []),
                len(tri.get("없는것") or []))
    return out
