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


async def _ask(payload: dict, ctx) -> str:
    if "narration" in (ctx.inject or {}):
        return str(ctx.inject["narration"] or "")
    try:
        from app.llm.provider import complete_text

        prompt = PROMPT_PATH.read_text(encoding="utf-8") + json.dumps(
            payload, ensure_ascii=False, default=str)
        return await complete_text(prompt, role="narrator")
    except Exception as exc:
        logger.warning("[flow:n12] 서술 실패: %s", exc)
        return ""


async def run(state, ctx):
    """⑫ 서술."""
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
