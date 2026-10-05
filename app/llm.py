"""§17 — LLM 은 **로컬 Ollama 뿐이다.** 봇의 눈이지 손이 아니다.

🔴 유료 API 호출 0건(§14-13): Anthropic · Gemini 유료 · Perplexity ·
   API-Football. **`:cloud` 접미 모델도 0건.**
🔴 LLM 이 하는 일은 여섯뿐이다(§17-b): L1 결장 · L2 인용+의도 · L3 순위·동기 ·
   L4 경기전후·중복·시점 · L5 반증조건→검색어 · L6 카드 슬롯.
🔴 LLM 이 쓰지 않는 것(§17-c): 승자·확신·확률·λ·등급·방아쇠.

§17-g-1: **프롬프트로 "JSON만"이라고 부탁하지 않는다** — 7B급은 마크다운
펜스를 섞어 낸다. 디코드 시점에 `format` 으로 스키마를 강제한다.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")          # §17-a 기본
MODEL_LIGHT = os.getenv("OLLAMA_MODEL_LIGHT", "llama3.2:1b")  # 분류만
SEED = int(os.getenv("LLM_SEED", "7"))

#: §17-e 경기당 L1~L5 합계 상한. 초과분은 unknown 처리.
BUDGET_PER_GAME = 20

#: 🔴 §17-a — 이 접미가 붙은 모델은 부르지 않는다.
_BANNED_SUFFIX = ":cloud"

#: §17-d 공통 머리말. **파일이 아니라 상수로 두고 여기 하나만 고친다.**
PREAMBLE = (
    "기사에 명시된 것만 추출한다. 추론·보완·요약 금지. 없으면 null."
)


class LLMUnavailable(RuntimeError):
    """Ollama 가 없거나 응답이 스키마를 못 맞췄다. 🔴 추측 보정 금지 — 폐기한다."""


@dataclass
class Budget:
    """§17-e 호출 예산. 초과하면 **unknown 으로 둔다** — 억지로 부르지 않는다."""

    limit: int = BUDGET_PER_GAME
    used: int = 0
    rejected: list[dict] = field(default_factory=list)

    def take(self) -> bool:
        if self.used >= self.limit:
            return False
        self.used += 1
        return True


def _check_model(model: str) -> None:
    if model.endswith(_BANNED_SUFFIX):
        raise LLMUnavailable(f"`:cloud` 모델은 호출 0건이다(§17-a): {model}")


async def call(prompt: str, schema: dict, *, model: str = MODEL,
               system: str = PREAMBLE, budget: Budget | None = None,
               timeout: float = 120.0, retry: int = 1) -> dict:
    """Ollama 한 번. 🔴 `format` 에 **JSON Schema 를 넘긴다.**

    §17-d: 출력은 스키마로 파싱하고 **실패 시 1회 재시도 후 폐기**한다.
    추측 보정은 하지 않는다 — 못 읽으면 예외다.
    """
    _check_model(model)
    if budget is not None and not budget.take():
        raise LLMUnavailable(f"호출 예산 {budget.limit} 초과 — unknown 으로 둔다")

    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "format": schema,                  # 🔴 디코드 시점 강제
        "options": {"temperature": 0, "seed": SEED,
                    # ⚠️ thinking 함정 — qwen3 는 reasoning 에 토큰을 다 쓰고
                    #    content 를 0자로 낼 수 있다. JSON 모드에서는 끈다.
                    "num_predict": 2048},
        "think": False,
    }
    last: Exception | None = None
    for attempt in range(retry + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as cli:
                r = await cli.post(f"{BASE_URL}/api/generate", json=payload)
                r.raise_for_status()
                raw = (r.json() or {}).get("response") or ""
            logger.info("[llm] model=%s attempt=%d bytes=%d", model, attempt,
                        len(raw))
            return json.loads(_strip_fence(raw))
        except Exception as exc:              # noqa: BLE001 — 폐기 전 1회 재시도
            last = exc
            logger.warning("[llm] model=%s attempt=%d 실패: %s", model,
                           attempt, exc)
    raise LLMUnavailable(f"{model}: {last}")


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


def _strip_fence(s: str) -> str:
    """⚠️ 스키마를 강제해도 펜스가 섞여 오는 모델이 있다 — 방어만 한다."""
    return _FENCE.sub("", s).strip()


# ══════════════════════════════════════════════════════════════════
# L1~L6 스키마 (§17-b)
# ══════════════════════════════════════════════════════════════════

#: 🔴 §17-g-2 — 항목마다 그것이 기댄 **원문 문장**을 반드시 함께 낸다.
#   문장이 본문에 실재하지 않으면 코드가 그 항목을 버린다.
L1_ABSENCE = {
    "type": "object",
    "properties": {
        "absences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "player_name": {"type": "string"},
                    "team_hint": {"type": ["string", "null"]},
                    "basis": {"type": "string", "enum": [
                        "injury", "national_team", "suspension",
                        "deregistered", "rest", "gone", "personal"]},
                    "until_hint": {"type": ["string", "null"]},
                    "evidence_sentence": {"type": "string"},
                },
                "required": ["player_name", "basis", "evidence_sentence"],
            },
        },
    },
    "required": ["absences"],
}

#: 🔴🔴 **좁은 질문** — *"이 기사가 X 를 말하나?"* (사용자 설계 2026-10-02 ③)
#
#  > 유형별 좁은 질문 → **yes/no/unknown + 본문 인용**, 인용이 원문에 실제로 있는지
#  > 코드가 검사
#
#  ⚠️ `unknown` 이 **enum 에 있는 것이 핵심이다.** 없으면 7B 는 모르는 것도 `no` 로
#     답한다 — 그러면 *"기사에 없다"* 와 *"기사가 아니라고 말한다"* 가 섞인다.
#  🔴 `quote` 는 `yes` 일 때 **필수**다(코드가 집행한다 — 스키마로는 조건부 필수를
#     못 적는다). 본문 대조는 `verify.quote_grounded` 가 한다.
ASK_TYPE = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "enum": ["yes", "no", "unknown"]},
        "quote": {"type": ["string", "null"]},
        # 🔴 **누구/무엇에 대한 것인가** — 명단 대조(④)가 이 칸을 쓴다
        "subject": {"type": ["string", "null"]},
    },
    "required": ["answer"],
}

L2_INTENT = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": [
            "조정_등판", "육성_검증", "주전_휴식", "CS_대비", "총력전",
            "복귀_관리", "로테이션_땜질", "소집_전_마지막"]},
        "quote": {"type": ["string", "null"]},
        "speaker": {"type": ["string", "null"]},
    },
    "required": ["type"],
}

L3_STANDINGS = {
    "type": "object",
    "properties": {
        "standings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "team": {"type": "string"},
                    "w": {"type": ["integer", "null"]},
                    "l": {"type": ["integer", "null"]},
                    "d": {"type": ["integer", "null"]},
                    "remaining": {"type": ["integer", "null"]},
                    "note": {"type": ["string", "null"]},
                },
                "required": ["team"],
            },
        },
    },
    "required": ["standings"],
}

L4_STAGE = {
    "type": "object",
    "properties": {
        "stage": {"type": "string", "enum": ["pre", "post", "live"]},
        "as_of": {"type": ["string", "null"]},
    },
    "required": ["stage"],
}

L5_QUERIES = {
    "type": "object",
    "properties": {
        "queries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "lang": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["lang", "text"],
            },
        },
    },
    "required": ["queries"],
}

L6_SLOTS = {
    "type": "object",
    "properties": {"facts": {"type": "array", "items": {"type": "string"}}},
    "required": ["facts"],
}


# ══════════════════════════════════════════════════════════════════
# L5 — 반증 조건 → 검색어 (§12-b 규칙을 코드가 검사한다)
# ══════════════════════════════════════════════════════════════════

_BAD_QUERY = re.compile(r'site:|["\'()]|-\w|\b20\d\d\b')


def query_ok(text: str) -> bool:
    """§12-b — 1~6단어 · 사이트 연산자·따옴표·마이너스 금지 · **연도 금지**.

    연도를 붙이면 지난 시즌 기사가 섞인다.
    """
    t = (text or "").strip()
    if not t or _BAD_QUERY.search(t):
        return False
    return 1 <= len(t.split()) <= 6
