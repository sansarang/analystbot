"""[v1.4 STEP 11] ⑫ 서술 — **코드가 정한 것을 설명한다. 만들지 않는다.**

🔴 입력은 **확정 사실만**이다. 배당·H2H·시즌 누적은 넣지 않는다
   (CLAUDE.md 대원칙 · 지시문 STEP 11).
🔴 입력에 없는 고유명사·숫자가 나오면 **1회 재생성**, 그래도 나오면 카드를
   만들지 않는다(`hallucination=True` → `run.py` 가 `n12_hallucination` 으로 멈춘다).
🔴 무료 사슬만 쓴다. 승자·확률·확신은 이미 코드가 정했다 — LLM 은 설명만 한다.
⚠️ 프롬프트는 `prompts/narrate_v14.txt` 하나다. 문구를 코드에 적지 않는다.
"""
from __future__ import annotations

import json
import logging
import pathlib
import re

logger = logging.getLogger(__name__)

NODE = "n12_text"

PROMPT_PATH = (pathlib.Path(__file__).resolve().parents[3]
               / "prompts" / "narrate_v14.txt")

#: 🔴 **추론 모델이라 여유가 필요하다.** 운영 사슬의 `openai/gpt-oss-120b` 는
#   `reasoning_tokens` 를 먼저 쓰고, 한도가 작으면 본문이 **빈 채로** 끝난다.
#   실측 2026-09-19 (같은 프롬프트·같은 모델):
#       600  → reasoning 598 · content 0자     ← 서술이 통째로 실패
#       2000 → 4문장 정상
#   ⚠️ 이 값을 줄이면 서술이 조용히 0건이 된다. 바꾸려면 위 실측을 다시 하라.
NARRATE_MAX_TOKENS = 2000

#: 숫자 검출기. 🔴 입력에 없는 숫자가 문장에 나오면 지어낸 것이다.
_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_SENT = re.compile(r"[.!?。]\s*")


def _payload(state) -> dict:
    """LLM 에 주는 것 — 이 목록이 전부다."""
    conf = state.n09_conf or {}
    val = state.n11_value or {}
    return {
        "home": state.home, "away": state.away,
        "kickoff_kst": state.kickoff_utc,
        "pick_type": val.get("pick_type"),
        "pick_market": (val.get("structure") or {}).get("market"),
        "pick_side": state.pick_side,
        "p_code": (state.n08_pcode or {}).get("p_code_pick"),
        "confidence": conf.get("grade"),
        "confirmed_vars": [
            {"var": e["var"], "value": e.get("value"),
             "source_url": e.get("source_url")}
            for e in (state.n05_evidence or [])],
        "adjustments": state.n07_adjust or [],
    }


def _numbers(obj) -> set:
    return set(_NUM.findall(json.dumps(obj, ensure_ascii=False, default=str)))


def _sentences(text: str) -> list:
    parts = [s.strip() for s in _SENT.split(str(text or "")) if s.strip()]
    return parts


def _invented(text: str, allowed: set) -> list:
    """문장에 있는데 입력에 없는 숫자."""
    return [n for n in _NUM.findall(text or "") if n not in allowed]


def _text_of(res) -> str:
    """`LLMResult` → 본문. 🔴 모양을 아는 자리를 **한 곳**에 둔다.

    🔴 못 찾으면 **빈 문자열**이다. 종전 초안은 `str(res)` 를 돌려줬는데
       그러면 `LLMResult(text='', data=None, provider='groq', ...)` 라는
       **객체 표현이 서술로 둔갑한다**(실측으로 잡았다). 빈손은 빈손이어야
       ⑫가 `hallucination` 으로 정직하게 끝난다.
    """
    for attr in ("text", "content", "output"):
        v = getattr(res, attr, None)
        if isinstance(v, str) and v.strip():
            return v
    if isinstance(res, dict):
        for k in ("text", "content", "output"):
            if isinstance(res.get(k), str) and res[k].strip():
                return res[k]
    return ""


async def _ask(payload: dict, ctx) -> str:
    if "narration" in (ctx.inject or {}):
        return str(ctx.inject["narration"] or "")
    try:
        # 🔴 [NAR-2 2026-09-19] 종전에는 `complete_text` 를 불렀는데 **그런
        #    함수가 없다**(실측: ImportError 2회 → 언제나 `hallucination=True`).
        #    진짜 API 는 `complete(role, messages) -> LLMResult` 다.
        #    ⚠️ 역할은 `narrator` 다 — 판정 역할을 쓰면 서술이 판정 예산을 먹는다.
        from app.llm.provider import complete

        prompt = PROMPT_PATH.read_text(encoding="utf-8") + json.dumps(
            payload, ensure_ascii=False, default=str)
        res = await complete("narrator", [{"role": "user", "content": prompt}],
                             max_tokens=NARRATE_MAX_TOKENS, temperature=0.0)
        return _text_of(res)
    except Exception as exc:
        logger.warning("[flow:n12] 서술 실패: %s", exc)
        return ""


async def run(state, ctx):
    """⑫ 서술."""
    # 🔴 [SWAP-3T 2026-09-22 사용자 지시] **서술은 템플릿이다.**
    #    사용자 원문: "서술도 템플릿으로 바꿔라" — 구경로(`narrate.story`)에만
    #    붙여 두면 경로를 갈아끼울 때 다시 LLM 서술로 돌아간다.
    #    스위치의 원본은 `config/rules.yaml` 의 `judge.llm_verdict` 하나다
    #    (판정과 서술을 같은 스위치로 가른다 — 둘 다 "LLM 이 아니라 코드").
    #    ⚠️ 코드를 지우지 않는다. 스위치를 켜면 종전 LLM 서술로 돌아간다.
    #    ⚠️ 템플릿은 **지어낸 숫자가 구조적으로 불가능하다** — 상태에 있는 값만
    #       옮긴다. 아래 `_invented` 검사가 필요 없어지는 이유다.
    from app.engine.matchup import _llm_verdict_on

    if not _llm_verdict_on():
        from app.engine.narrate import story_flow

        sents = story_flow(state)
        state.n12_text = {"sentences": sents, "attempt": 0,
                          "hallucination": False, "source": "template"}
        logger.info("[flow:n12] game=%s 템플릿 %d문장", state.game_id, len(sents))
        return state

    payload = _payload(state)
    allowed = _numbers(payload)

    for attempt in (1, 2):
        text = await _ask(payload, ctx)
        sents = _sentences(text)
        bad = _invented(text, allowed)
        if len(sents) == 4 and not bad:
            state.n12_text = {"sentences": sents, "attempt": attempt,
                              "hallucination": False}
            logger.info("[flow:n12] game=%s 4문장 (시도 %d)", state.game_id, attempt)
            return state
        logger.warning("[flow:n12] game=%s 규격 미달 (문장 %d · 지어낸 숫자 %s)",
                       state.game_id, len(sents), bad[:5])

    state.n12_text = {"sentences": [], "attempt": 2, "hallucination": True}
    return state
