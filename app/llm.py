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


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **Ollama 호출을 지웠다** — 사용자 지시 2026-10-06(2차) ⑤
# ══════════════════════════════════════════════════════════════════
#
# > v6 가 안 쓰는 옛 LLM 경로(`openworld.read_names` 의 `solar.chat`, Ollama 경로)는
# > **v6 가 안 부르는 게 확인되면 삭제.**
#
# 🔴 실측 2026-10-06: s1~s7 전 단계에 염탐을 걸어 재생으로 돌렸다 —
#    `app.llm.call` 호출 **0건**(옛 세포 경로만 불렀다). 그래서 지웠다.
# ⚠️ `solar.chat` 은 **지우지 않았다** — 같은 실측에서 s1 이 `openworld.read_names`
#    를 통해 **부른다**(이름표가 `한국` 을 못 풀 때 ⑥-1 로 간다).
# 🔴 이 파일에 남은 것은 **문지기 하나**(`query_ok`)와 스키마 선언이다 — 그 둘은
#    망에 나가지 않는다.


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


#: 🔴 문지기 낱말 범위 — **질의를 쓰는 쪽이 이 수를 읽는다**(사본 금지 · #1).
#   ⚠️ 실사고 2026-10-15: 이 규칙을 모델에게 **안 알려 줘서** solar 가
#      `Svay Rieng starting lineup AFC Champions League Two`(낱말 8개)를
#      냈고 문지기가 **매 하위마다 막았다** — 라인업·결장을 직접 겨눈 질의가
#      그 경기에서 **한 번도 안 나갔다**(3+5 통합 0건의 직접 원인).
WORDS_MIN, WORDS_MAX = 1, 6


def query_ok(text: str) -> bool:
    """§12-b — 1~6단어 · 사이트 연산자·따옴표·마이너스 금지 · **연도 금지**.

    연도를 붙이면 지난 시즌 기사가 섞인다.
    """
    t = (text or "").strip()
    if not t or _BAD_QUERY.search(t):
        return False
    return WORDS_MIN <= len(t.split()) <= WORDS_MAX
