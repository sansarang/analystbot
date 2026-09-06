"""[소식통 2026-09-06] 상황이 승률을 뒷받침하는가 — 확신도 강등.

🔴 **확률을 건드리지 않는다.** 상황 정보는 확률의 입력이 아니라 **검증**이다.
   은퇴식이 몇 %p 인지 우리는 모르고, 모르는 것에 숫자를 붙이면 지어낸
   계수가 된다. 대신 "숫자와 현지 상황이 어긋난다"는 사실을 확신도로 말한다.

🔴 **소식통이 관건이다** (사용자 지시). `[미확인]` 항목만으로는 강등하지
   않는다 — 익명 계정의 카더라로 픽을 죽일 수는 없다. 구단 공식 계정·리그·
   언론이 말한 것일 때만 무게가 있다.

⚠️ 강등은 **거부권으로 이어진다.** 확신도 '하'는 추천 자격을 박탈한다
   (`form_card.rec_label`). 그래서 게이트를 좁게 잡는다:
     결론이 `불일치` **그리고** 공식 소식통이 하나라도 있을 때만.

⚠️ 모델이 확신도를 직접 내리게 하지 않는다. 모델은 `상황판정` 만 내고,
   소식통 검사와 강등은 **코드가** 한다 — 모델에게 거부권을 주지 않는다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

CONTRADICTS = "불일치"
SUPPORTS = "지지"
NEUTRAL = "무관"

#: 확신도 1단계 강등. '하'는 더 내리지 않는다.
_DEMOTE = {"high": "medium", "medium": "low",
           "상": "중", "중": "하"}


def official_tags(jg: dict) -> list[dict]:
    """공식 소식통에서 온 상황 태그만."""
    out = []
    for rows in (jg.get("situation_tags") or {}).values():
        out += [t for t in (rows or []) if (t or {}).get("확인") == "공식"]
    return out


def verdict_of(jg: dict) -> dict:
    """판정이 낸 `상황판정`. 없으면 무관으로 읽는다 — 지어내지 않는다."""
    v = (jg.get("matchup") or {}).get("상황판정")
    if not isinstance(v, dict):
        return {"결론": NEUTRAL, "사유": "", "출처": ""}
    return {"결론": str(v.get("결론") or NEUTRAL),
            "사유": str(v.get("사유") or ""),
            "출처": str(v.get("출처") or "")}


def apply(jg: dict) -> dict:
    """판정 확정 후 호출. 강등이 필요하면 확신도를 1단계 내린다.

    반환: `{결론, 강등, 이전, 이후, 공식출처수}` — 카드·로그가 읽는다.
    """
    v = verdict_of(jg)
    officials = official_tags(jg)
    res = {"결론": v["결론"], "사유": v["사유"], "출처": v["출처"],
           "공식출처수": len(officials), "강등": False,
           "이전": jg.get("judge_confidence"), "이후": jg.get("judge_confidence")}

    if v["결론"] != CONTRADICTS:
        return res
    if not officials:
        # 소식통이 확인되지 않았다 — 서술만 남기고 확신도는 건드리지 않는다.
        logger.info("[situation-gate] game=%s 불일치이나 공식 소식통 0건 "
                    "— 강등하지 않는다", jg.get("game_id"))
        res["결론"] = NEUTRAL
        res["사유"] = (v["사유"] + " (소식통 미확인 — 판정에 반영하지 않음)").strip()
        return res

    before = jg.get("judge_confidence")
    after = _DEMOTE.get(str(before), before)
    jg["judge_confidence"] = after
    jg["situation_demoted"] = True
    res.update(강등=(after != before), 이후=after)
    logger.info("[situation-gate] game=%s 상황 불일치 — 확신도 %s→%s "
                "(공식 소식통 %d건: %s)", jg.get("game_id"), before, after,
                len(officials), v["출처"][:60])
    return res


def card_line(res: dict) -> str:
    """카드에 실을 한 줄. 결론이 무관이고 사유도 없으면 빈 줄(생략)."""
    concl, why = res.get("결론"), (res.get("사유") or "").strip()
    if concl == SUPPORTS:
        head = "✅ 현지 상황이 뒷받침"
    elif concl == CONTRADICTS:
        head = "⚠️ 현지 상황이 뒷받침하지 않음"
    else:
        if not why:
            return ""
        head = "· 현지 상황"
    tail = f" — {why}" if why else ""
    if res.get("강등"):
        tail += f" · 확신도 {res.get('이전')}→{res.get('이후')}"
    return f"{head}{tail}"
