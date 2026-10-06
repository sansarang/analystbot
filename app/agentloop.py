"""🔴🔴 **에이전트 루프** — v5 §3. 변수 → 가설 → 시나리오 **초안**. [#10 #14 #15]

> 에이전트는 경기 하나를 받아 변수 → 가설 → 시나리오 초안까지 JSON 으로
> 돌려준다. **그 뒤는 전부 코드다.**

🔴 §1 의 한 줄이 이 파일의 경계다:

> 에이전트는 **제안만** 한다. 변수·시나리오·마켓 등급 어느 것도 에이전트 출력이
> **그대로 카드로 가지 않는다**. **검증층을 통과한 변수만 변수**이고, 판정층이
> 계산한 등급만 등급이다.

══════════════════════════════════════════════════════════════════
🔴 왜 — 규칙을 덧대는 길에 끝이 없다
══════════════════════════════════════════════════════════════════

§1: *"산문의 롱테일(망명, 은퇴 경기, 감독 이탈, 자선 경기)이 들어올 때마다
규칙을 덧대야 하고, 그 규칙은 **끝이 없다**."*

⚠️ 실측 2026-10-04: `typed 20 → variables 3` 의 뿌리가 정규식 유형표였다.
🔴 그 자리를 **도구를 든 LLM** 하나로 바꾸고, 코드가 **검증·판정**한다.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime

from app.reasons import Reason

logger = logging.getLogger(__name__)

#: 🔴 §3-2 — **도구 셋.** ⚠️ 전부 코드 구현이고 에이전트는 **호출만** 한다.
TOOL_NAMES: tuple[str, ...] = ("search", "fetch", "done")

#: 🔴 §3-7 — *"`done` 스키마 **2회 실패**."*
SCHEMA_RETRIES = 2

#: 🔴🔴 **에이전트에게 주는 본문 길이.**
#
#  ⚠️ 실측 2026-10-04: 턴마다 받은 본문이 **통째로** 대화에 쌓여 16턴에
#     `경기당 입력 161475/150000 토큰` 으로 예산이 터졌다.
#  🔴 고침은 `readtext` 가 이미 아는 것이다: *"팀·선수 이름이 나오는 문단만
#     BM25 로 골라 넘긴다. **입력이 짧아야 8B 모델도 정확하다.**"* 그 말은
#     Solar 에게도 맞고 **예산에도** 맞는다.
#  🔴 §4-5 의 본문 상한(50,000자)보다 **훨씬 작다** — 그 상한은 *한 페이지를
#     얼마나 받나*이고 이것은 *한 턴에 모델에게 얼마를 보이나*다.
AGENT_BODY_CHARS = 3_000

#: 🔴🔴 **턴 상한.** ⚠️ 모델이 `done` 을 안 부르면 예산이 터질 때까지 돈다.
#
#  🔴 수는 §2 의 **도구 호출 상한**에서 자란다(검색 24 + 받기 16 = 40) — 턴마다
#     도구를 하나씩 부르므로 그보다 몇 턴 여유를 둔다. ⚠️ 코드에 박지 않는다.
#: 🔴🔴 **매 몇 턴마다 리마인드하나**(작업 지시서 §1 추가 한 줄).
#
#  > 매 **8턴마다** 시스템이 *"지금까지 모은 변수로 `done` 을 부를 수 있다.
#  > 카탈로그에서 안 찾은 유형: …"* 를 리마인드로 넣는다. **48턴 배회의 재발
#  > 방지**이고, 턴 상한(32)은 그대로 둔다.
REMIND_EVERY = 8


def remind_line(missing: list) -> str:
    """🔴 그 리마인드 한 줄. ⚠️ **안 찾은 유형을 이름으로** 적는다(#3)."""
    said = ", ".join(str(x) for x in (missing or [])[:12]) or "없다"
    return (f"🔴 지금까지 모은 변수로 **`done` 을 부를 수 있다.** "
            f"카탈로그에서 안 찾은 유형: {said}. "
            f"더 찾을 것이 없으면 `done` 으로 마친다(§3-7).")




def max_turns() -> int:
    """🔴 §3-7 — 턴 상한 **32**.

    ⚠️ 종전에 §2 도구 상한에서 계산해 **44** 였다. 🔴 작업 지시서 §1 이
       *"턴 상한(**32**)은 그대로 둔다"* 라고 그 수를 적었다 — **문서가
       이긴다**(내 계산은 그 수를 몰랐다).
    🔴 48턴 배회의 재발 방지는 **리마인드**가 맡고(§1 추가 한 줄), 상한은
       그 뒤의 바닥이다.
    """
    return 32


#: ⚠️ 뒤로 호환 — 계약이 상수로 읽던 자리. 🔴 값은 위 함수가 정한다.
MAX_TURNS = max_turns()


@dataclass
class AgentInput:
    """🔴 §3-1 — **코드가 만든다.** ⚠️ 에이전트는 이 밖의 사실을 모른다."""

    match_key: str
    home: str
    away: str
    kickoff_utc: datetime
    home_names: tuple[str, ...] = ()
    away_names: tuple[str, ...] = ()
    competition: str = ""
    sport: str = ""
    venue: str = ""
    langs: tuple[str, ...] = ()
    #: 🔴 §3-1 — **마켓 종류와 기준선만**(배당 숫자 없음 · 절대규칙 6)
    board: tuple = ()
    structured_facts: tuple = ()
    #: §3-4 변수 카탈로그 전 유형
    #: 🔴🔴 **하위 과제** — 딥서치 재구축 §2 (2026-10-05).
    #   ⚠️ 칸으로 든다 — `getattr` 기본값은 없는 칸을 숨겨 분할을 **조용히**
    #      끈다(`Card.kickoff` 와 같은 함정 · 실측 2026-10-05).
    subtask: object = None
    checklist: tuple[str, ...] = ()
    #: 🔴 구조 사실로 못 채운 칸(예: 감독 이름 미상)
    gaps: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ("home", "away"):
            got = str(getattr(self, name) or "")
            if not got.startswith("team:"):
                raise ValueError(
                    f"🔴 `{name}` 은 **열쇠**여야 한다(§8-1): {got!r} — 이름이 "
                    f"들어오면 1~3단계가 고친 병이 입구에서 되살아난다")
        w = self.kickoff_utc
        if not isinstance(w, datetime) or w.tzinfo is None \
                or w.tzinfo.utcoffset(w) is None:
            raise ValueError(f"🔴 **시간대 없는** 킥오프다(§8-7): {w!r}")


def tool_specs() -> list[dict]:
    """🔴 §3-2 — OpenAI 호환 `tools`. ⚠️ 설명이 **에이전트가 읽는 규칙**이다."""
    return [
        {"type": "function", "function": {
            "name": "search",
            "description": (
                "검색어를 던진다. 🔴 검색어는 {팀}{상대}{대회명}{종목 낱말}"
                "{날짜 또는 preview/lineup/injury} 중 **세 요소 이상**을 "
                "가져야 한다(§4-1). 이름 하나짜리는 거부된다. "
                "같은 검색어를 두 번 던지면 거부된다 — 각도를 바꿔라."),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"},
                               "lang": {"type": "string"}},
                "required": ["query", "lang"]}}},
        {"type": "function", "function": {
            "name": "fetch",
            "description": (
                "그 URL 의 본문을 받는다. 🔴 **검색 결과에 있던 URL 만** 받는다"
                "(§4-4). robots·도메인 등급·크기 상한을 코드가 검사한다."),
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"]}}},
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **`done` 의 인자가 스키마 그 자체다**(실측 2026-10-04)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 종전 인자는 `{"output": "문자열"}` 이었다. 🔴 모델은 그 문자열에
        #     **무엇을 넣어야 하는지 모른다** — 스키마는 *다음* 턴에서야 보여
        #     주는데 그 턴이 오지 않는다(닭과 알이다).
        #  🔴 실측: 48턴을 돌고 **`done` 을 한 번도 안 불렀다**. 턴 1~17 은
        #     `search`·`fetch` 를 잘 돌았고, 턴 18 에 **산문으로 끝냈다** →
        #     스키마 2회 실패 → 변수 0개.
        #  ✅ §3-2 의 *"마지막 `done` 턴에서만 스키마를 강제한다"* 와 어긋나지
        #     않는다 — **그 턴의 인자**가 스키마다.
        {"type": "function", "function": {
            "name": "done",
            "description": (
                "🔴 **끝낸다.** 찾은 변수·가설·시나리오를 여기 넣는다. "
                "⚠️ 이것을 부르지 않으면 아무것도 기록되지 않는다 — "
                "조사를 마쳤으면 **반드시** 부른다."),
            "parameters": output_schema()["schema"]}},
    ]


def output_schema() -> dict:
    """🔴 §3-6 `AgentOutput` — **구조화 출력으로 강제한다**(§2)."""
    var = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "team": {"type": "string"},
            # 🔴 **누구에 관한 사실인가**(열쇠) — `team` 과 같은 값이어도 된다.
            #    ⚠️ *누구에게 유리한가*는 **코드가 정한다**(모델이 안 낸다).
            "subject": {"type": "string"},
            # 🔴🔴 **enum 으로 막는다** — 실측 2026-10-05: 이 칸이 자유
            #    문자열이라 모델이 문장을 썼고 변수 **10줄이 전부** 버려졌다.
            #    ⚠️ 목록은 `agentschema` 가 원본이다(사본 금지).
            "direction_hint": {"type": "string", "enum": list(_hints())},
            # 🔴 유형도 **카탈로그로 막는다** — 실측: 에이전트가 지은 이름과
            #    카탈로그의 겹침이 **0개**였다(`form`·`context`…).
            "type": {"type": "string", "enum": list(_catalog())},
            "claim": {"type": "string"},
            "quote": {"type": "string"},
            "url": {"type": "string"},
            "published_at": {"type": "string"},
            "lang": {"type": "string"},
            "conflict": {"type": "boolean"},
            "reverified": {"type": "boolean"},
        },
        "required": ["id", "type", "team", "subject",
                         "direction_hint", "claim", "quote",
                     "url", "published_at", "lang", "conflict", "reverified"],
        "additionalProperties": False,
    }
    scen = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "driver_vars": {"type": "array", "items": {"type": "string"}},
            "mechanism": {"type": "string"},
            "outcomes": {"type": "array",
                         "items": {"type": "array",
                                   "items": {"type": "integer"}}},
            "required_type": {"type": "string"},
            "weak": {"type": "boolean"},
        },
        "required": ["id", "driver_vars", "mechanism", "outcomes",
                     "required_type", "weak"],
        "additionalProperties": False,
    }
    return {
        "name": "analyst_output", "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "variables": {"type": "array", "items": var},
                "hypotheses": {"type": "string"},
                "scenarios": {"type": "array", "items": scen},
                "gaps": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "string"},
            },
            "required": ["variables", "hypotheses", "scenarios", "gaps",
                         "notes"],
            "additionalProperties": False,
        },
    }


def _hints() -> tuple[str, ...]:
    """🔴 `direction_hint` 허용값. ⚠️ `agentschema` 가 원본이다(사본 금지)."""
    from app.agentschema import DIRECTION_HINTS
    return tuple(DIRECTION_HINTS)


def _catalog() -> tuple[str, ...]:
    """🔴 v5 §3-4 카탈로그 **전 유형**. ⚠️ `variable_types.yaml` 이 원본이다."""
    from app import rules
    return tuple(sorted(rules.variable_types()))


def _must_try() -> tuple[str, ...]:
    """🔴 `done` 을 막는 네 유형. ⚠️ 목록은 `ledgerbook` 하나다(사본 금지)."""
    from app.ledgerbook import MUST_TRY
    return MUST_TRY


def system_prompt() -> str:
    """🔴 §3-3 — **페이블의 15단계를 그대로** 적는다(고정 문자열).

    ⚠️ §2: *"시스템 프롬프트(규칙·카탈로그·스키마)는 **고정 문자열로 앞에** 두어
       캐시 입력 단가를 받는다."* 🔴 그래서 경기별 내용이 **여기 섞이지 않는다.**
    """
    return (
        "너는 스포츠 경기 하나를 조사한다. 도구로만 일한다.\n"
        "\n"
        "1. 두 팀 폼을 먼저 본다: 최근 5경기·연속·직전 결과·직전 경기의 득점 "
        "내역. structured_facts 에 있으면 검색하지 않는다.\n"
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **gaps 우선** — 지시서 §3-3 (2026-10-05)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 시스템 프롬프트에 *"gaps 의 구조 칸은 카탈로그 유형보다 **먼저**
        #  > 찾아라"* 를 둔다.
        #
        #  ⚠️ 미등록 리그(라네로스 등)는 어댑터가 순위·최근 결과·상대전·XI 를
        #     **안 준다**. 🔴 그것이 없으면 시나리오가 **설 바닥이 없다** —
        #     카탈로그 유형보다 먼저다.
        "1-1. 🔴 `gaps` 에 적힌 **구조 칸**(순위·최근 5경기·상대전·XI·선발)이 "
        "있으면 **그것을 카탈로그 유형보다 먼저** 찾는다 — 그 바닥이 없으면 "
        "시나리오가 서지 않는다.\n"
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **카탈로그를 실제로 적는다** — 사용자 지시 2026-10-05
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 이 줄은 *"카탈로그 유형마다 찾는다"* 라고 **말만** 했다 — 그
        #     목록이 **어디에도 없었다.** 🔴 실측 2026-10-05: 에이전트가 낸
        #     유형과 카탈로그의 **겹침이 0개**였다(`form`·`context`·
        #     `squad_offence` 처럼 **자기가 지은 이름**을 썼다).
        #  🔴 그러면 §4 유형표의 방향 규칙·hardness 규칙이 **하나도 안 걸린다.**
        #  ⚠️ 목록은 `config/variable_types.yaml` 이 원본이다(사본 금지) —
        #     여기 손으로 적지 않는다. 🔴 계약이 그것을 잠근다.
        "2. 아래 **카탈로그 유형마다** 적어도 한 번 찾는다. '없음'도 답이지만, "
        "사다리 2단계 이상 돌린 뒤에만 없음이라고 적는다.\n"
        "   🔴 **`type` 은 이 목록의 글자 그대로** 쓴다(다른 이름을 지으면 그 "
        "변수는 버려진다):\n"
        + "".join(f"     · {t}\n" for t in sorted(_catalog()))
        + "   🔴 그중 **이 넷은 반드시** 찾아본다(안 찾으면 `done` 이 거부된다): "
        + ", ".join(_must_try()) + "\n"
        "3. 영어 → 팀 현지어 순서. 별칭(애칭·감독·주장·현지 매체명)을 검색어에 "
        "쓴다.\n"
        "4. 결과를 읽고 엉뚱한 것(다른 종목·다른 성별·연령·과거 시즌·다른 경기)"
        "은 버린다.\n"
        "5. 매체 간 충돌은 둘 다 적고 conflict:true. 🔴 베팅 팁·예측 사이트의 "
        "숫자는 변수 근거로 쓰지 않는다. 상대 전적은 작동 메커니즘(세트피스·"
        "역습 등)이 보일 때만 변수다.\n"
        "   🔴 `team` 은 **입력의 `home`/`away` 열쇠 글자 그대로**(`team:000338`) "
        "쓴다. 팀 이름을 쓰면 코드가 옮기지만, 못 옮기면 그 변수는 버려진다.\n"
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **`direction_hint` 허용값을 말한다** — 실측 2026-10-05
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 이 목록을 **한 번도 말하지 않아서** 모델이 자유 문장을 썼고
        #     변수 **10줄이 전부** 버려졌다(`parse_args` → 후보 0개).
        #  🔴 목록은 `agentschema.DIRECTION_HINTS` 하나다(사본 금지).
        "   🔴 `direction_hint` 는 **다음 글자 중 하나**만 쓴다(다른 말을 쓰면 "
        "그 변수는 버려진다): " + ", ".join(_hints()) + "\n"
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **`lang` 도 말한다** — 전수 점검이 집은 칸(2026-10-05)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 코드는 그 값을 쓴다(현지어 판정·검색 언어). 🔴 그런데 프롬프트가
        #     **무엇을 넣으라고 말하지 않았다** — 전수 점검 11칸 중 **하나**가
        #     그 꼴이었다(나머지 10칸은 이미 설명돼 있었다).
        "   🔴 `subject` 는 **그 사실이 누구에 관한 것인가**(팀 열쇠)다. "
        "⚠️ *누구에게 유리한가*는 **적지 마라** — 코드가 카탈로그 규칙으로 "
        "정한다(예: 결장은 그 팀에 **불리**하다).\n"
        "   🔴 `lang` 은 **그 기사의 언어**를 두 글자로 적는다(`en`·`pt`·`ko`"
        "·`ja`·`es`…) — 네가 읽은 그 글의 언어다(질의 언어가 아니다).\n"
        "6. 변수마다: 유형, 방향, 작동 설명 1문장, 출처 URL, 발행 시각, "
        "🔴 **원문 인용(원어 그대로, 25단어 이내)**, 재검증 여부.\n"
        "   ⚠️ 인용은 **그 본문에 문자 그대로 있어야** 한다 — 코드가 대조하고 "
        "없으면 그 변수를 버린다.\n"
        "7. 팀별 가설: 이기는 이유(변수 번호들) + 무너지는 조건(변수 번호들).\n"
        # 🔴 글자는 여덟이다(결정 ① 2026-10-04) — 모델에게 **그대로** 말한다
        "8. 시나리오 A~H(최대 8): 작동 변수 번호 + 전개 1~2문장 + "
        "결과 스코어(1~2개). "
        "필수형 3종(우세팀 실점 동반형·대량득점형·회귀 반전형)을 반드시 "
        "포함하되, 근거 변수가 없으면 weak:true 로 표시한다.\n"
        "9. 경기외 변수(대표팀 복귀·징계·은퇴·행사·감독 거취·타이틀 경쟁·이동·"
        "날씨·구장·무관중)를 못 찾았으면 gaps 에 그 유형을 적는다.\n"
        "10. 🔴 **등급·확률·배당·승자 단어를 쓰지 않는다. 그것은 네 일이 "
        "아니다.**\n"
        "\n"
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **끝내는 법**(§3-2 규약 · 위 열 단계와 다른 것이다)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 실측 2026-10-04: 모델이 48턴을 돌고 **`done` 을 한 번도 안 불렀다** —
        #     턴 18 에 **산문으로 끝냈다.** 🔴 열 단계는 *무엇을 조사하나*이고
        #     *어떻게 끝내나*는 안 적혀 있었다.
        "🔴 **끝내는 법**: 조사를 마쳤으면 **반드시 `done` 을 부른다.** "
        "그 인자에 변수·가설·시나리오를 넣는다 — 산문으로 끝내면 **아무것도 "
        "기록되지 않는다.**\n"
        "⚠️ `search` 가 거부하면(요소 3개 미만·중복) **각도를 바꿔** 다시 "
        "던진다. 거부가 쌓여도 조사를 멈추지 말고, 더 찾을 것이 없으면 "
        "`done` 으로 마친다.\n"
    )


@dataclass
class Tools:
    """🔴 §3-2 — 도구 셋의 **코드 쪽**. 에이전트는 호출만 한다."""

    inp: AgentInput
    budget: object = None
    querylog: object = None
    #: 🔴🔴 **v5 §3-2 — 세포가 받아 둔 것**(`cells.Seen`). `None` 이면 빈손이다.
    #
    #  ⚠️ 새로 긁지 않는다 — 세포들이 이미 검색하고 본문을 받았다. 🔴 또 긁으면
    #     같은 페이지를 **두 배로** 두드리고 예산도 두 배가 된다.
    seen: object = None
    #: 🔴 §4-4 — **검색 결과에 있던 URL 만** `fetch` 가 받는다
    seen_urls: set = field(default_factory=set)
    #: 🔴🔴 **검색 스니펫** — ②층(fetch 전 거름)이 날짜를 찾는 글이다
    #   (사용자 지시 2026-10-05). ⚠️ 칸으로 든다 — `getattr` 기본값은 없는 칸을
    #   숨겨 그 층을 **조용히 끈다**(`Card.kickoff` 와 같은 함정).
    snippets: dict = field(default_factory=dict)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **스스로 찾는 수단** — 결정 ③ (사용자 2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 결정 ③이 세포 검색을 껐다. 🔴 그런데 이 도구는 **세포가 받아 둔
    #     것**(`seen`)을 되돌려 주고 있었다 — 세포가 안 찾으면 **빈손**이다.
    #     (실측: `seen.urls` 가 0건이면 에이전트가 입구에서 아무것도 못 한다.)
    #  🔴 그래서 세포가 안 찾을 때는 **에이전트가 직접 찾는다** — 그것이
    #     *"에이전트가 켜져 있으면 세포는 장부다"* 의 뜻이다.
    #  ⚠️ `None` 이면 종전대로 `seen` 만 쓴다(퇴로를 남긴다).
    chain: object = None        # `app.search.build_chain()` 의 결과
    net: object = None          # `app.net.Net` — 본문을 직접 연다
    #: 🔴 직접 찾고 연 것을 **깔때기에 센다**(#3 조용한 0 금지)
    funnel: object = None
    #: 🔴🔴 **장부**(`ledgerbook.Book`) — 유형 × 팀 칸마다 무엇을 해봤나.
    #
    #  사용자 지시 2026-10-05: *"세포를 장부로 되살린다 … `done` 호출 시 네
    #  유형이 `not_tried` 면 `done` 을 거부한다(예산이 남아 있을 때만).
    #  이게 **계획기는 버리고 장부는 남긴다**의 실제 모양이다."*
    book: object = None
    #: 🔴 직접 찾은 결과를 **여기 쌓는다**(다음 턴·`fetch` 가 쓴다)
    mine: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.budget is None:
            from app.solar import MatchBudget
            self.budget = MatchBudget()
        if self.querylog is None:
            from app.querygate import QueryLog
            self.querylog = QueryLog()
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **받아 둔 문서의 저장소는 `Seen` 하나다**(사용자 지시 2026-10-06)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 본문 캐시를 `url → {body, published_at, date_source}` 로 바꿔
        #  > **Seen 하나**에 담는다. `bodies` 와 `dates` 를 따로 들고 다니는
        #  > 경로를 없앤다.
        #
        #  ⚠️ 종전엔 `Tools.bodies`·`Tools.dates` 가 **칸으로** 따로 있었다.
        #     본문은 `seen.bodies`(하위를 가로질러 쌓인다)에서도 오는데 날짜는
        #     `Tools.dates`(하위마다 새로 생긴다)에만 쌓였다 — 🔴 그래서 **다른
        #     하위가 받아 둔 본문을 인용한 변수**는 본문·인용은 통과하고
        #     **날짜만 비어** `date_missing` 으로 죽었다(실측 2026-10-06: 6건,
        #     받은 문서 24건 전부 날짜가 있었는데도).
        #  🔴 `seen` 이 없으면 제 것을 하나 만든다 — **두 길을 두지 않는다.**
        from app.cells import Seen as _Seen
        if self.seen is None or not hasattr(self.seen, "docs"):
            self.seen = _Seen()

    def search(self, query: str, lang: str = "en") -> dict:
        """🔴 §4 규칙을 전부 적용한다. ⚠️ 거부면 **사유를 돌려준다.**"""
        ok, why = self.budget.can_tool("search")
        if not ok:
            return {"ok": False, "reason": Reason.BUDGET_CUT.value, "why": why}
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **§4-1 — 조각을 *선언*한다**(짐작보다 선언이 낫다)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 종전엔 `check(query)` 였다 — 문지기가 **글에서 짐작**했고 팀·상대
        #     이름은 *"보이지 않는다"*(이름을 모르니까). 🔴 그래서 제대로 만든
        #     질의도 2개로 세어 거부됐다(실측 2026-10-04).
        #  🔴 그런데 **우리는 안다** — `inp` 에 두 팀 이름·대회·종목이 다 있다.
        #     ⚠️ 선언은 *"그 글자가 질의에 실제로 있을 때만"* 한다(없는 조각을
        #        선언하면 그것이 문지기를 속이는 것이다).
        # 🔴 유형은 **질의가 말한다**(`variable_types.yaml` 의 선언으로 가른다)
        from app import querygate as _QG
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **씨앗은 자동 통과**(딥서치 재구축 §4-3)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 1차(씨앗): §2 표의 템플릿 그대로 — 3~6단어. **씨앗 템플릿은 자동
        #  > 통과.** 🔴 넓게 시작해 판을 본 뒤 좁힌다.
        task = getattr(self.inp, "subtask", None)
        is_seed = bool(task is not None
                       and str(query or "").strip()
                       == str(getattr(task, "seed", "")).strip())
        ok_q, reason, why = self.querylog.check(
            query, parts=self._parts(query), kind=_QG.kind_of(query),
            seed=is_seed)
        if not ok_q:
            return {"ok": False, "reason": reason.value, "why": why}
        self.budget.took_tool("search")
        # 🔴🔴 **장부에 적는다**(사용자 지시 2026-10-05) — 유형 × 팀 칸.
        #    ⚠️ 질의가 어느 유형을 노렸나는 **낱말로** 안다(카탈로그 이름이
        #       질의에 있거나, 그 유형의 선언된 `match` 낱말이 있다).
        #    🔴 장부는 **계획하지 않는다** — 적기만 한다.
        self._book_search(query)
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **§3-2 — 세포가 받아 둔 검색 결과를 낸다**(게이트 2)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 종전엔 `hits: []` 를 냈다 — **통로만 열어 둔** 상태였고 카드가
        #     *"도구 미배선"* 을 적었다.
        #  🔴 새로 긁지 않는다: 세포들이 이미 검색했다(실측 2026-10-04: 깔때기
        #     `queries` 23 · `fetched` 107). 또 긁으면 예산이 두 배다.
        #  ⚠️ `seen` 이 없으면 **빈손**이고 그 사실을 사유로 돌려준다(#3).
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **결정 ③ 이후 — 받아 둔 것이 없으면 *직접* 찾는다**
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 세포 검색을 끄자(결정 ③) `seen.urls` 가 **0건**이 됐다. 🔴 그러면
        #     이 도구가 빈손을 돌려주고 에이전트는 입구에서 끝난다 — 그것은
        #     ③의 뜻이 아니다(*"검색은 에이전트가 한다"*).
        #  🔴 그래서 **쌓인 것을 먼저 쓰고, 없으면 직접 던진다.** 둘 다 같은
        #     문지기(§4-1)를 이미 지났다(위에서 쳤다).
        pool = dict(self.mine)
        if self.seen is not None:
            for u in self.seen.urls:
                pool.setdefault(u, dict(self.seen.meta.get(u, {})))
        if not pool and self.chain is None:
            return {"ok": True, "reason": Reason.OK.value, "hits": [],
                    "why": ("⚠️ 받아 둔 검색 결과가 **없고** 직접 찾을 수단도 "
                            "없다(`seen`·`chain` 미전달) — 줄 것이 없다")}
        said = ""
        if self.chain is not None:
            # 🔴 **1차 언어**(§4-4) — 씨앗은 영어(한국 리그는 한국어)
            use = str(lang or "en")
            if is_seed and task is not None:
                from app.research import subtasks as _st
                use = _st.first_lang(league=str(self.inp.competition or ""),
                                     langs=tuple(self.inp.langs or ()))
            got, said = self._hunt(query, use)
            pool.update(got)
            # 🔴 **좁히기 낱말을 알려 준다**(§4-2) — 2차를 지어내지 않게.
            #    ⚠️ 모델이 아니라 **받은 글**에서 나온다(#4 추측 금지).
            from app.research import subtasks as _st2
            words = _st2.narrow_words(
                [{"title": m.get("title") or "",
                  "snippet": self.snippets.get(u) or ""}
                 for u, m in got.items()])
            if words and task is not None:
                nxt = _st2.narrow_query(str(getattr(task, "seed", "")), words)
                said += (f" · 🔴 **다음은 좁혀라**: `{nxt}` "
                         f"(결과에서 본 낱말 {words[:5]})")
        hits = [{"url": u, **meta,
                 "has_body": (u in self.bodies) or (
                     self.seen is not None and u in self.seen.bodies)}
                for u, meta in pool.items()]
        # 🔴 §4-4 — 준 URL 만 `fetch` 가 받는다
        self.seen_urls.update(h["url"] for h in hits)
        line = self.seen.line() if self.seen is not None else "쌓인 것 없음"
        return {"ok": True, "reason": Reason.OK.value,
                "why": " · ".join(x for x in (why, said, line) if x),
                "hits": hits}

    def _hunt(self, query: str, lang: str) -> tuple[dict, str]:
        """🔴🔴 **직접 던진다** — 결정 ③ 이후 검색은 에이전트 몫이다.

        ⚠️ 비동기 사슬을 **동기 루프에서** 부른다 — 이 도구 루프는
           `asyncio.to_thread` 안에서 돌므로 자기 이벤트 루프를 세워도 된다.
        🔴 실패를 **삼키지 않는다** — 사유를 글로 돌려준다(#3).
        """
        import asyncio

        got: dict = {}
        # 🔴 **동시성 가드**(M66) — 병렬 하위 8개가 SearXNG 를 동시에 때리면
        #    429 가 난다. ⚠️ 상한은 `config/llm.yaml` 이 든다.
        from app.research import lead as _lead

        async def _ask():
            async with _lead.gate("searx"):
                return await self.chain.query(query, lang=lang)

        try:
            hits = asyncio.run(_ask())
        except Exception as exc:                            # noqa: BLE001
            return got, f"🔴 직접 검색 실패: {exc!r}"
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **§5 1단 — 받기 전 재정렬**(딥서치 재구축 2026-10-05)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 입력: 질의당 결과 최대 30건의 `(질의문, 제목+스니펫)` 쌍.
        #  > 🔴 재정렬은 **순서만** 바꾼다 — fetch 수를 늘리지 않고(M62),
        #  >    필터를 통과 못 한 결과를 되살리지 않는다.
        #
        #  ⚠️ 질의문에 **유형 핵심어**를 붙인다(하위가 있을 때) — 그것이
        #     동의어를 잡는 재료다. 🔴 모델이 없으면 순서가 그대로다.
        from app.research import rerank as _rr
        said = str(query or "")
        task = getattr(self.inp, "subtask", None)
        if task is not None and getattr(task, "rerank_query", ""):
            said = f"{said} {task.rerank_query}"
        rows = [{"url": str(getattr(h, "url", "") or ""),
                 "title": str(getattr(h, "title", "") or ""),
                 "snippet": str(getattr(h, "snippet", "") or ""),
                 "_hit": h} for h in (hits or [])]
        ranked, why_rr = _rr.order(said, [r for r in rows if r["url"]])
        # 🔴 **fetch 상한까지만 앞에 둔다**(§5 1단) — 재정렬은 순서만 바꾸고
        #    받는 건수를 늘리지 않는다(M62). ⚠️ 뒤쪽도 **버리지 않는다** —
        #    모델에게는 다 보여 주고, 받는 것은 그가 고른다.
        cap = int(getattr(getattr(task, "budget", None), "fetch_cap", 0) or 0)
        head = _rr.take(ranked, cap=cap) if cap else ranked
        rest = [r for r in ranked if r not in head]
        hits = [r["_hit"] for r in [*head, *rest]]
        for h in (hits or []):
            url = str(getattr(h, "url", "") or (h.get("url") if
                                                isinstance(h, dict) else ""))
            if not url:
                continue
            meta = {"title": str(getattr(h, "title", "") or ""),
                    "published_at": str(getattr(h, "published_at", "") or "")}
            got[url] = meta
            self.mine[url] = meta
            # 🔴 ②층이 쓸 **스니펫을 싣는다**(지시 2026-10-05) — 제목도 날짜를
            #    들고 있을 수 있어 함께 넘긴다.
            self.snippets[url] = " ".join(
                x for x in (str(getattr(h, "snippet", "") or ""),
                            meta["title"]) if x)
        self.last_rerank = why_rr
        if self.funnel is not None:
            self.funnel.add("hits", len(got), sample=query)
        return got, f"직접 검색 {len(got)}건"

    def _book_search(self, query: str) -> list[str]:
        """🔴 그 질의가 **어느 유형을 노렸나**를 장부에 적는다.

        ⚠️ 낱말을 **여기 적지 않는다** — `config/variable_types.yaml` 의
           `match`·`query_match` 정규식이 원본이다(사본 금지).
        🔴 못 가리면 **아무것도 적지 않는다** — 안 해본 칸을 *"해봤다"* 로
           바꾸면 `done` 막기가 뜻을 잃는다(거짓 통과).
        """
        if self.book is None:
            return []
        import re as _re

        from app import rules
        low = " ".join(str(query or "").lower().split())
        hit: list[str] = []
        for kind, box in (rules.variable_types() or {}).items():
            # 🔴 ① **유형 이름 자체**(프롬프트가 그 글자를 쓰라고 했다)
            if kind.lower() in low:
                hit.append(kind)
                continue
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 ② **개념 낱말표**를 본다 — 새 표를 만들지 않는다
            # ══════════════════════════════════════════════════════════
            #
            #  ⚠️ `match` 는 **기사 본문**을 가리는 정규식이다(§1-1 에서 본 그
            #     구분). 🔴 실측 2026-10-05: 영어 질의
            #     `"… injury news October 4"` 에 다섯 유형 패턴이 **하나도**
            #     안 맞았다(`\bruled out\b`·`\bsidelined\b` 같은 기사 표현).
            #  🔴 그런데 유형 선언에 **`word:` 가 이미 있다**(`word: injury`)
            #     — `config/search_words.yaml` 의 개념 낱말을 가리킨다.
            #     그것이 **질의 낱말**이다(사다리가 던지는 바로 그 말).
            #  ⚠️ 그래서 표를 새로 만들지 않고 **그 선언을 따라간다**(사본 금지).
            word = str((box or {}).get("word") or "")
            if word:
                for lang in ("en", "ko", "ja", "es", "zh"):
                    got = rules.local_words(word, lang) if hasattr(
                        rules, "local_words") else []
                    if any(str(w).lower() in low for w in (got or [])):
                        hit.append(kind)
                        break
                if hit and hit[-1] == kind:
                    continue
            # 🔴 ③ 그 다음에야 본문 패턴을 본다(맞으면 그것도 단서다)
            pats = list((box or {}).get("query_match") or []) \
                + list((box or {}).get("match") or [])
            for pat in pats:
                try:
                    if _re.search(str(pat), low, _re.I):
                        hit.append(kind)
                        break
                except _re.error:                       # pragma: no cover
                    continue
        for kind in hit:
            # ⚠️ 어느 팀인지 질의가 말하면 그 팀, 아니면 **양 팀**에 적는다
            for side, names in (("home", self.inp.home_names),
                                ("away", self.inp.away_names)):
                said = any(str(n).lower() in low for n in names if n)
                if said or not hit:
                    self.book.searched(kind, str(
                        self.inp.home if side == "home" else self.inp.away))
            if not any(str(n).lower() in low
                       for ns in (self.inp.home_names, self.inp.away_names)
                       for n in ns if n):
                # 🔴 팀을 못 가렸다 — **양 팀**에 적는다(질의가 둘 다 노렸다)
                self.book.searched(kind, str(self.inp.home))
                self.book.searched(kind, str(self.inp.away))
        return hit


    def _parts(self, query: str) -> dict:
        """🔴 이 질의에 **실제로 든** 조각만 선언한다(§4-1).

        ⚠️ 없는 조각을 선언하면 문지기를 **속이는** 것이다 — 그래서 글자가
           질의에 있는지 **확인한 것만** 넣는다.
        """
        low = " ".join(str(query or "").lower().split())
        # ══════════════════════════════════════════════════════════════════
        # 🔴🔴 **경기장 글자를 먼저 뺀다** — 실측 2026-10-05 (프랑스–벨기에)
        # ══════════════════════════════════════════════════════════════════
        #
        #  ⚠️ 실사고: 경기장이 `Stade de France` 라서 질의
        #     `'Stade de France weather forecast October 5 2026'` 의 `France`
        #     가 **팀 이름**으로 세어졌다. 결정 ⑥(*"경기장+날짜만 있는 질의는
        #     여전히 bare"*)이 무력화되고, 그 질의는 **본 URL 0개 · 본문 0개**
        #     를 냈다 — 결정 ⑥ 이 막으려던 바로 그 쓰레기다.
        #  🔴 팀을 찾을 때는 **경기장을 지운 글**에서 찾는다. 경기장 자체는
        #     아래에서 원래 글로 센다(지운 글로 세면 경기장이 사라진다).
        ven_low = " ".join(str(getattr(self.inp, "venue", "") or "")
                           .lower().split())
        team_low = low.replace(ven_low, " ") if ven_low else low
        got: dict = {}
        for key, names in (("team", self.inp.home_names),
                           ("opponent", self.inp.away_names)):
            for n in names:
                if str(n or "").strip() and str(n).lower() in team_low:
                    got[key] = str(n)
                    break
        comp = str(self.inp.competition or "")
        # 🔴 판정은 `querygate.comp_in` **한 곳**이다(#1 사본 금지).
        #    ⚠️ 종전엔 `comp.lower() in low` — 정식명 한 덩어리만 봐서
        #       `… 2026 Nations League` 가 대회를 0개로 셌다(실측 2026-10-05).
        from app import querygate as _QG2
        if comp and _QG2.comp_in(comp, low):
            got["competition"] = comp
        # 🔴🔴 **경기장** — 결정 ⑥ (2026-10-04). ⚠️ 문지기가 `kind` 로 조건을
        #    건다(`venue_weather` 유형에서만 세고, 경기장+날짜만은 bare).
        ven = str(getattr(self.inp, "venue", "") or "")
        if ven and ven.lower() in low:
            got["venue"] = ven
        return got

    def fetch(self, url: str) -> dict:
        """🔴 §4-4 — 검색 결과에 **있던 URL 만**. §4-3·§4-5 를 코드가 본다."""
        ok, why = self.budget.can_tool("fetch")
        if not ok:
            return {"ok": False, "reason": Reason.BUDGET_CUT.value, "why": why}
        if url not in self.seen_urls:
            return {"ok": False, "reason": Reason.DOMAIN_DENIED.value,
                    "why": (f"🔴 **검색 결과에 없던 URL** 이다(§4-4): "
                            f"{str(url)[:70]}")}
        from app import domains
        ok_d, tier, said = domains.verdict(url, sport=self.inp.sport)
        if not ok_d:
            return {"ok": False, "reason": Reason.DOMAIN_DENIED.value,
                    "why": said}
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **§3-2 — 받아 둔 본문을 낸다**(게이트 2). 다시 긁지 않는다.
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ **URL 은 봤는데 본문이 없는** 경우가 있다 — 세포의 열기 예산이
        #     그 URL 까지 못 갔다. 🔴 그때 **빈 글을 주지 않는다**: 빈 본문을
        #     주면 §5-1 이 *"인용이 본문에 없다"*(= 지어냈다)로 적고, 그것은
        #     **거짓 사유**다(§8-6). 고칠 곳이 다르다 — 그 URL 을 안 열었다.
        body = self.bodies.get(url) or (
            (self.seen.bodies.get(url) if self.seen is not None else "") or "")
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **없으면 직접 연다** — 결정 ③ 이후(세포가 안 열어 둔다)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 세포 검색을 끄자 **받아 둔 본문도 0건**이 됐다(세포가 열지 않으니).
        #  🔴 그래서 열기도 에이전트 몫이다. ⚠️ `net` 이 없으면 종전대로
        #     *"받아 두지 않았다"* 를 돌려준다(퇴로).
        if not str(body).strip() and self.net is not None:
            body = self._open(url)
        if not str(body).strip():
            return {"ok": False, "reason": Reason.NOT_COLLECTED.value,
                    "tier": tier,
                    "why": (f"⚠️ 그 URL 의 **본문을 못 얻었다**(받아 둔 것도 없고 "
                            f"직접 열기도 실패했다) — 지어낸 것이 아니다: "
                            f"{str(url)[:70]}")}
        self.budget.took_tool("fetch")
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **좁혀 준다** — 예산이 그것을 요구한다(실측 2026-10-04)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 통째로 주면 16턴에 150k 토큰을 넘는다. 🔴 `readtext` 가 질의와
        #     가까운 문단을 골라 준다 — **버리는 것이 아니라 고르는 것**이다.
        #  🔴 **줄인 사실을 적는다**(#3 조용한 0 금지).
        short, cut = _narrow(body, self._query_hint())
        return {"ok": True, "reason": Reason.OK.value,
                "why": f"{said}{cut}", "tier": tier, "body": short}

    def _open(self, url: str) -> str:
        """🔴 **직접 연다** — `net` 이 robots·도메인을 이미 본다(절대규칙 3).

        ⚠️ `readtext` 로 본문을 뽑는다(광고·메뉴를 걷는다). 🔴 실패를 삼키지
           않는다 — 빈 글을 돌려주고 호출부가 *"못 얻었다"* 를 적는다.
        """
        import asyncio

        from app import datehint, readtext
        # ══════════════════════════════════════════════════════════════════
        # 🔴🔴 **②층 — 받기 전에 거른다**(사용자 지시 2026-10-05)
        # ══════════════════════════════════════════════════════════════════
        #
        #  > URL 날짜 패턴과 스니펫 날짜 표현을 파싱해 **7일 밖이 확실하면 받지
        #  > 않는다. 날짜 힌트가 없으면 받는다.**
        #
        #  ⚠️ SearXNG 은 발행 시각을 **안 준다**(실측 2026-10-05: 엔진 전부
        #     `publishedDate` 0건) — 그래서 종전엔 *"받아 본 뒤에"* 날짜를
        #     알았고 7일 밖 문서에 예산을 썼다(`date_missing` 10건).
        #  🔴 **fail-open 이다** — 힌트가 없으면 받는다.
        skip, why = datehint.too_old(url, self._snippet_of(url))
        if skip:
            logger.info("[agent] ②층 — 받지 않는다: %s · %s", why, url[:70])
            if self.funnel is not None:
                self.funnel.drop(Reason.STALE_SAMPLE, "fetched")
            return ""
        from app.research import lead as _lead2

        async def _grab():
            async with _lead2.gate("fetch"):
                return await self.net.get(url)

        try:
            got = asyncio.run(_grab())
        except Exception as exc:                            # noqa: BLE001
            logger.info("[agent] 직접 열기 실패(%s): %r", url[:60], exc)
            return ""
        if not getattr(got, "ok", False):
            return ""
        text, when, _why, _n = readtext.read(
            getattr(got, "text", "") or "", url=url,
            query=self._query_hint())
        body = text or (getattr(got, "text", "") or "")
        if body:
            # 🔴 **발행일을 들고 있는다**(M109) — ③층이 원본이고 검색 날짜는
            #    보조다. ⚠️ 순위는 `net.pick_published` **한 곳**이 정한다(#1).
            from app import net as _N
            said, why_d = _N.pick_published(
                when, (self.mine.get(url) or {}).get("published_at") or "")
            # 🔴🔴 **본문·발행일·출처를 한 번에** 넣는다(사용자 지시 2026-10-06) —
            #    셋을 따로 넣는 길이 있으면 또 갈린다(그것이 `date_missing` 6건의
            #    까닭이었다).
            from app.cells import store_doc
            store_doc(self.store, url, body, published_at=said,
                      date_source=str(why_d or ""))
            logger.info("[agent] 발행일 — %s (%s) · %s",
                        said or "없다", why_d, url[:60])
            if self.funnel is not None:
                self.funnel.add("fetched", 1, sample=url)
        return body

    def _snippet_of(self, url: str) -> str:
        """🔴 그 URL 의 **검색 스니펫** — ②층이 날짜를 찾는 글이다.

        ⚠️ 없으면 빈 글이고, 그때 ②층은 *"힌트가 없다"* 로 **받는다**.
        """
        return str((self.snippets or {}).get(str(url)) or "")

    @property
    def store(self):
        """🔴 받아 둔 문서의 **유일한 저장소**(`cells.Seen`)."""
        return self.seen

    @property
    def bodies(self):
        """🔴 `url → 본문`. **뷰다** — 쓰면 저장소에 들어간다(사본이 아니다)."""
        return self.seen.bodies

    @property
    def dates(self):
        """🔴 `url → 발행 시각`. 같은 저장소다 — 그래서 **하위를 가로질러** 보인다."""
        return self.seen.dates

    def _query_hint(self) -> str:
        """🔴 본문을 고를 때 쓰는 **질의** — 이 경기의 두 팀과 대회다."""
        return " ".join([*self.inp.home_names[:1], *self.inp.away_names[:1],
                         self.inp.competition])


def stop_note(reason: Reason, *, kept: int) -> str:
    """🔴 §3-7 — *"그때까지의 변수로 §5 로 넘기고 **사유를 적는다**."*"""
    from app.reasons import say
    return (f"{say(reason)} — 모은 변수 **{kept}개**로 **§5** 검증층으로 "
            f"넘긴다(§3-7)")


def finish(vars_: list, *, funnel=None) -> tuple[list, str]:
    """🔴 §3-7 — 변수 **0개면 `agent_zero`**(자료 부족)."""
    if not vars_:
        if funnel is not None:
            funnel.drop(Reason.AGENT_ZERO, "agent_vars")
            funnel.set("agent_vars", 0)
        from app.reasons import say
        return [], say(Reason.AGENT_ZERO)
    if funnel is not None:
        funnel.set("agent_vars", len(vars_))
    return list(vars_), f"변수 후보 {len(vars_)}개"


def parse_args(box: object, *, inp: AgentInput | None = None,
               dates: dict | None = None) -> tuple[list, str]:
    """🔴 `done` 이 준 **사전**을 `AgentVar` 들로. ⚠️ 글자로 다시 돌리지 않는다.

    🔴 실측 2026-10-04: 종전에는 `done(output="…")` 의 **문자열**을 JSON 으로
       읽었다. 그 꼴이 모델을 막았다(무엇을 넣을지 모른다) — 이제 **인자가
       스키마**이므로 사전이 바로 온다.
    """
    if not isinstance(box, dict):
        return [], f"🔴 `done` 인자가 사전이 아니다: {type(box).__name__}"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **꼴을 들어오는 자리에서 맞춘다** — 실측 2026-10-05 (프랑스–벨기에)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고: 모델이 `variables` 를 **JSON 문자열**로 보냈다
    #     (`'[{"id": "V1", …'`). 스키마는 `{"type":"array"}` 로 맞았지만 모델이
    #     안 지켰고, 뒤에서 `row.get` 이 터졌다 — `'str' object has no
    #     attribute 'get'`. 🔴 **15,455자(변수 전부)가 버려졌다.**
    #  🔴 모델을 믿는 대신 **여기서 한 번** 바꾼다(§8-3). 뒤에서 `getattr`·
    #     `isinstance` 로 더듬으면 그런 자리가 끝없이 늘어난다.
    box = dict(box)
    for key in ("variables", "scenarios", "gaps"):
        said = box.get(key)
        if not isinstance(said, str) or not said.strip():
            continue
        try:
            back = json.loads(said)
        except ValueError as exc:
            # 🔴 **조용히 버리지 않는다**(#3) — 무엇이 왜 안 읽혔나
            logger.info("[agent] ⚠️ `%s` 가 문자열인데 JSON 이 아니다(%d자): %r",
                        key, len(said), str(exc)[:80])
            continue
        if isinstance(back, list):
            logger.info("[agent] 🔴 `%s` 를 **문자열로 받았다** — 목록 %d개로 "
                        "바꿨다(모델이 스키마를 안 지켰다)", key, len(back))
            box[key] = back
    return _vars_from(box, inp=inp, dates=dates)


def parse_output(text: str) -> tuple[list, str]:
    """🔴 §3-6 JSON **글자** → `AgentVar` 들. ⚠️ 못 읽으면 `([], 사유)`.

    ⚠️ 이 길은 **대체**다 — 모델이 `done` 을 안 부르고 산문으로 끝낼 때 쓴다
       (실측 2026-10-04 에 그 일이 났다). 🔴 정상 길은 `parse_args` 다.
    """
    box, said = _json_in(text)
    if box is None:
        return [], f"🔴 `done` 이 JSON 이 아니다(§3-2): {said}"
    return _vars_from(box)


def _json_in(text: object) -> tuple[dict | None, str]:
    """🔴🔴 **산문 속 JSON 을 꺼낸다.** `(사전 또는 None, 사유)`.

    ══════════════════════════════════════════════════════════════════
    🔴 실측 2026-10-04 — 모델이 산문에 JSON 을 섞어 냈다
    ══════════════════════════════════════════════════════════════════

    ```
    Stubs (공식 등급, hardness 2) returning probable pitchers …

    확보한 사실(스텁 본문 인용 가능):
    - Brewers probable starter: Michael King (home)

    ```json
    done({ "variables": [ … ] })
    ```
    ```

    🔴 `json.loads(전체)` 는 당연히 터진다. ⚠️ 그것을 *"모델이 스키마를 못
       지켰다"* 로 적으면 **거짓 사유**다 — 모델은 **지켰고** 우리가 **못
       꺼냈다**(§8-6).
    🔴 꺼내기는 해킹이 아니다: 울타리(```json)와 `done(` 은 모델이 **흔히 쓰는
       꼴**이고 그 안은 그냥 JSON 이다.
    ⚠️ **지어내지 않는다** — 못 찾으면 `None` 이고 사유를 돌려준다.
    """
    raw = str(text or "").strip()
    if not raw:
        return None, "빈 글이다"
    tries: list[str] = [raw]
    # ① 울타리 안쪽(```json … ``` 또는 ``` … ```)
    import re as _re
    for m in _re.finditer(r"```(?:json)?\s*\n(.*?)```", raw, _re.S):
        tries.append(m.group(1).strip())
    # ② `done(` … `)` 안쪽 — 모델이 도구 호출을 **글자로** 쓴 꼴
    for m in _re.finditer(r"done\s*\(\s*(\{.*)", raw, _re.S):
        tries.append(m.group(1).strip())
    # ③ 첫 `{` 부터 — 괄호 수를 세어 **짝이 맞는 데까지**
    i = raw.find("{")
    if i >= 0:
        depth, end, instr, esc = 0, -1, False, False
        for j in range(i, len(raw)):
            ch = raw[j]
            if instr:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    instr = False
                continue
            if ch == '"':
                instr = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = j + 1
                    break
        if end > i:
            tries.append(raw[i:end])
    last = ""
    for cand in tries:
        try:
            got = json.loads(cand)
        except ValueError as exc:
            last = str(exc)
            continue
        if isinstance(got, dict):
            return got, "꺼냈다"
    return None, (last or "JSON 블록을 못 찾았다")


def _vars_from(box: dict, *, inp: AgentInput | None = None,
               dates: dict | None = None) -> tuple[list, str]:
    """🔴 사전 → `AgentVar` 들. ⚠️ 꼴이 틀린 줄은 **이름으로** 남긴다(#3).

    🔴 `inp` 를 주면 **팀 이름을 열쇠로 옮긴다**(§8-1: 해석은 한 곳에서만).
    """
    from app.agentschema import AgentVar
    out = []
    bad: list[str] = []
    for row in (box.get("variables") or []):
        try:
            # 🔴🔴 **③층 날짜가 원본이다**(지시서 M109) — 모델이 안 적어도
            #    우리가 뽑은 발행일을 쓴다.
            #    ⚠️ 실사고 it5: 모델이 적은 값만 봐서 `date_missing` 7건이
            #       났다 — `htmldate` 는 돌았는데 그 결과가 안 쓰였다.
            when = (dates or {}).get(str(row.get("url") or "")) \
                or row.get("published_at")
            got = None
            if when:
                from app import timefmt
                got = timefmt.aware(datetime.fromisoformat(
                    str(when).replace("Z", "+00:00")))
            out.append(AgentVar(
                id=str(row.get("id") or ""), type=str(row.get("type") or ""),
                team=(row.get("team") or None),
                # 🔴 **누구에 관한 사실인가** — 비면 `team` 을 쓴다
                subject=(row.get("subject") or row.get("team") or None),
                claim=str(row.get("claim") or ""),
                quote=str(row.get("quote") or ""),
                url=str(row.get("url") or ""), published_at=got,
                direction_hint=str(row.get("direction_hint") or "both"),
                lang=str(row.get("lang") or "en"),
                conflict=bool(row.get("conflict")),
                reverified=bool(row.get("reverified", True))))
        except (ValueError, TypeError) as exc:
            bad.append(f"{row.get('id')}: {exc}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **M48 — `team` 이 이름이면 폐기**(작업 지시서 §1)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 나는 이 세션에서 이름을 **열쇠로 옮겼다**(`_team_key`). 🔴 지시서가
    #     그것을 뒤집었다: *"이름이면 그 항목 **폐기** `name_not_key`"*.
    #  🔴 왜 폐기가 맞나: 옮기면 모델의 그 버릇이 **숨는다.** 폐기하면
    #     `name_not_key` 가 수로 쌓이고 프롬프트를 고칠 근거가 된다.
    #  ⚠️ 사유를 **이름으로** 적는다(#3) — 몇 줄이 왜 떨어졌나가 보여야 한다.
    named = [str(r.get("team") or "") for r in (box.get("variables") or [])
             if str(r.get("team") or "").strip()
             and not str(r.get("team") or "").startswith("team:")]
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **카탈로그 밖 유형은 버린다** — 실측 2026-10-05
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측: 에이전트가 낸 유형과 카탈로그의 **겹침이 0개**였다
    #     (`form`·`context`·`squad_offence`…). 🔴 그런데 코드는 그것을
    #     **버리지도 않았다** — 조용히 통과시켰다.
    #  🔴 그러면 §4 유형표의 **방향 규칙·hardness 규칙이 하나도 안 걸린다** —
    #     유형이 **뜻을 잃는다**(힌트가 그대로 방향이 되고 무게가 기본값이다).
    #  ⚠️ enum 으로 막았지만 모델이 **스키마를 어길 수 있다**(실측: 두 번 그
    #     일이 났다). 그래서 **받은 뒤에도** 검사한다(fail-closed).
    cat = set(_catalog())
    off = [f"{v.id}:{v.type}" for v in out if v.type not in cat]
    if off:
        out = [v for v in out if v.type in cat]
    why = f"후보 {len(out)}개"
    if off:
        why += (f" · 🔴 **{Reason.TYPE_OFF_CATALOG.value} {len(off)}개** — "
                f"`type` 이 카탈로그 밖이다({off[:3]}) · §3-4")
    if named:
        why += (f" · 🔴 **{Reason.NAME_NOT_KEY.value} {len(named)}개** — "
                f"`team` 이 이름이다({named[:2]}) · §3-8 M48")
    if bad:
        why += f" · ⚠️ **꼴이 틀린 것 {len(bad)}개**: {bad[:2]}"
    return out, why


def _narrow(body: object, query: str) -> tuple[str, str]:
    """🔴 긴 본문을 **질의와 가까운 문단**으로 좁힌다. `(글, 사유)`.

    ⚠️ `AGENT_BODY_CHARS` 아래면 **그대로** 준다 — 짧은 글을 또 자르면 문맥이
       끊긴다.
    🔴 `readtext.top_paragraphs` 가 그 일을 한다(BM25) — 여기서 다시 짓지
       않는다(#1 사본 금지).
    """
    raw = str(body or "")
    if len(raw) <= AGENT_BODY_CHARS:
        return raw, ""
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **§5 2단 하이브리드**(딥서치 재구축 2026-10-05)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > BM25 상위 20 → reranker 로 재점수 → **상위 8 문단만** 프롬프트에.
    #  > 이게 BM25 가 놓치는 동의어(`"won't feature"`·`"이탈"`·`"欠場"`)를
    #  > 잡는 자리다.
    #
    #  ⚠️ 모델이 없으면 `rerank` 가 **BM25 상위 8**로 폴백한다(M62) — 분석은
    #     멈추지 않고, 어느 단으로 돌았는지 사유에 남는다(#3).
    from app import readtext
    from app.research import rerank
    paras = readtext.paragraphs(raw)
    got, said = rerank.paragraphs(query, paras)
    out = "\n".join(got)
    if not out:
        out = raw[:AGENT_BODY_CHARS]
    elif len(out) > AGENT_BODY_CHARS:
        out = out[:AGENT_BODY_CHARS]
    # 🔴 **어느 단으로 돌았나를 사유에 적는다**(#3) — 모델이 없으면 BM25
    #    상위 8 로 돌았고, 그 사실이 안 보이면 카드가 거짓이 된다.
    return out, (f" · 🔴 본문 {len(raw)}자 → **{len(out)}자**로 좁혔다"
                 f"(§5 2단: {said})")


def call_tool(tools, name: str, args: dict) -> dict:
    """🔴 §3-2 — 도구 하나를 부른다. ⚠️ 모르는 이름은 **사유**다(크래시 아니다).

    🔴 `done` 은 **도구가 아니라 신호**다 — 호출부가 루프를 끝낸다.
    """
    got = str(name or "")
    if got == "search":
        return tools.search(str(args.get("query") or ""),
                            str(args.get("lang") or "en"))
    if got == "fetch":
        return tools.fetch(str(args.get("url") or ""))
    if got == "done":
        return {"ok": True, "reason": Reason.OK.value, "why": "끝낸다",
                "output": str(args.get("output") or "")}
    return {"ok": False, "reason": Reason.AGENT_ZERO.value,
            "why": (f"🔴 **모르는 도구**다(`{got}`) — 선언한 것은 "
                    f"{list(TOOL_NAMES)} 뿐이다(§3-2)")}


def _msg_of(got: dict) -> dict:
    return ((got.get("choices") or [{}])[0].get("message") or {})


def _calls_of(msg: dict) -> list:
    out = []
    for c in (msg.get("tool_calls") or []):
        fn = dict(c.get("function") or {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            args = {}
        out.append((str(c.get("id") or ""), str(fn.get("name") or ""),
                    args if isinstance(args, dict) else {}))
    return out


def _why_of(exc) -> Reason:
    """🔴🔴 **예산이 막은 것을 `llm_unavailable` 로 세지 않는다**(사용자 지시 ④).

    ⚠️ 실측 2026-10-06(북아일랜드–조지아): 깔때기가 `llm_unavailable 14` 를
       적었는데 로그의 실제 전송 실패는 **1건**(`RemoteDisconnected`)이었다.
       나머지는 전부 `budget_cut`(하위 출력 상한)이 `SolarUnavailable` 로
       올라온 것이다 — §8-6 이 금지한 **거짓 사유**다.
    🔴 그리고 그 거짓은 **일을 더 만든다**: CLAUDE.md #11 이 *"`llm_unavailable`
       로 끊긴 실행은 오염된 것이므로 다시 돌린다"* 라고 적었다. 예산에 막힌
       정상 종료를 그렇게 읽으면 **쓸데없이 재실행한다.**
    """
    from app import solar
    if isinstance(exc, solar.SolarBudgetCut):
        return Reason.BUDGET_CUT
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **상태 코드가 사유를 정한다** — 지시서 2026-10-06 §3 (M136)
    # ══════════════════════════════════════════════════════════════
    #
    #  > `llm_timeout`·`llm_http_5xx`·`llm_429`·`budget_cut` 은 서로 다른 사유다.
    #
    #  🔴 고칠 곳이 다르다: 응답없음은 **망/응답 길이**, 5xx 는 **서버**,
    #     429 는 **속도**. ⚠️ 섞으면 어디를 고칠지 못 고른다.
    status = getattr(exc, "status", None)
    if status == 429:
        return Reason.LLM_429
    if isinstance(status, int) and 500 <= status < 600:
        return Reason.LLM_HTTP_5XX
    if status is None:
        # 🔴 **응답조차 못 받았다** — 타임아웃·끊김·DNS
        return Reason.LLM_TIMEOUT
    return Reason.LLM_UNAVAILABLE


def merge_bodies(ctx, tools) -> int:
    """🔴🔴 **에이전트가 연 본문을 검증층에 합친다.** 돌려주는 것은 합친 수.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 — 지시서(오픈월드) §1-1 의 진단 (실측 2026-10-04)
    ══════════════════════════════════════════════════════════════════

    포르투갈 카드의 후보 **12개가 전부** 떨어졌고 사유가 하나였다:

    ```
    verified_vars 탈락: quote_not_found 12
    [verify] 폐기 V8 — 🔴 그 URL 의 **본문을 받아 두지 않았다**(fail-closed)
    ```

    ⚠️ 정규화 문제도, 지어낸 것도 **아니었다** — 인용을 **대조조차 못 했다.**
    🔴 까닭: `analyze` 가 `ctx.bodies` 를 **`seen.bodies` 로만** 채운다. 결정
       ③(세포는 장부)으로 그것이 **비었고**, 에이전트가 제 손으로 연 본문은
       `Tools.bodies` 에 쌓여 **아무도 넘기지 않았다.**

    🔴 이 저장소가 반복해 다친 자리다(#2) — *"만든 것은 부르는 곳이 있어야 한다.
       안 이어진 코드는 없는 코드보다 나쁘다."*
    """
    got = dict(getattr(tools, "bodies", {}) or {})
    if not got:
        return 0
    box = getattr(ctx, "bodies", None)
    if box is None:
        return 0
    n = 0
    for url, body in got.items():
        # 🔴 **세포가 받아 둔 것을 덮지 않는다** — 그쪽이 먼저 열었다면 그것이
        #    원본이다(같은 URL 을 두 번 열지 않는다는 전제가 거기 있다).
        if url not in box and str(body or "").strip():
            box[url] = body
            n += 1
    return n


def run(inp: AgentInput, ctx, *, funnel=None, net=None, seen=None,
        budget=None, chain=None, fetcher=None) -> tuple[list, str]:
    """🔴🔴 §3 전체 — **도구를 돌려** 조사하고 검증층을 지난 변수를 돌려준다.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 루프인가 — 한 번 묻는 것은 **기억으로 짓게** 하는 것이다
    ══════════════════════════════════════════════════════════════════

    ⚠️ 종전 이 함수는 `solar.chat(msgs, schema=…)` 를 **한 번** 불렀고 `tools`
       를 **안 넘겼다.** 프롬프트는 *"도구로만 일한다"* 라고 적었는데 도구가
       없었다. 🔴 그러면 모델은 **기억으로** 변수를 짓고 인용을 **지어낸다** —
       §5-1 이 전부 폐기하므로 수는 안 틀리지만 **토큰만 쓰고 0건**이 된다.

    흐름(§3-2):

        [system(고정) + user(경기)]
          → chat(tools=…)            🔴 스키마는 **안 준다**
          → tool_calls 를 코드가 실행하고 결과를 대화에 **되돌려 준다**
          → `done` 이 오면 루프를 끝내고
          → chat(schema=…)           🔴 **그 턴에만** 스키마를 강제한다
          → §5 검증층                🔴 여기를 지난 것만 변수다(§1)

    🔴 §3-7 중단 셋: 턴 상한 · `done` 스키마 2회 실패 · 예산 소진. ⚠️ 어느
       쪽이든 **그때까지의 변수로 §5 로 넘기고 사유를 적는다.**
    """
    from app import solar
    bud = budget if budget is not None else solar.MatchBudget()
    # 🔴 결정 ③ — 세포가 안 찾으므로 **수단을 들려 보낸다**(없으면 종전대로)
    from app.ledgerbook import Book
    book = Book()
    tools = Tools(inp=inp, seen=seen, budget=bud, funnel=funnel, book=book,
                  # ══════════════════════════════════════════════════════
                  # 🔴🔴 **`net` 과 `fetcher` 는 다른 것이다**(실측 2026-10-04)
                  # ══════════════════════════════════════════════════════
                  #
                  #  ⚠️ `run(net=…)` 은 **이미 쓰이고 있었다** — `solar.chat(_net=…)`
                  #     의 **시험용 대역**(호출 가능한 것)이다. 🔴 내가 거기에
                  #     `app.net.Net` 객체를 넣어 터뜨렸다:
                  #       `TypeError("'Net' object is not callable")`
                  #     → 5경기 재실행 첫 경기가 **에이전트 0턴**으로 끝났다.
                  #  🔴 세포 검색을 끈 뒤였으므로 **아무도 찾지 않았다** —
                  #     `cell_search_off 52` 와 `verified_vars 5`(격자 잔재)만 남았다.
                  #  ⚠️ 이름이 겹친 것을 **몰랐다** — 쓰기 전에 `grep` 하지 않았다.
                  chain=chain, net=fetcher)
    # 🔴🔴 **하위 프롬프트 꼬리**(딥서치 재구축 §2·§4) — 담당 유형과 검색어
    #    규칙을 붙인다. ⚠️ 하위가 없으면(옛 경로) **아무것도 안 붙는다** —
    #    그 사실이 사유로 남는다.
    tail = ""
    if inp.subtask is not None:
        from app.research import subtasks as _st
        tail = _st.prompt_tail(inp.subtask)
    msgs: list[dict] = [
        {"role": "system", "content": system_prompt() + tail},
        {"role": "user", "content": json.dumps(
            {"match_key": inp.match_key, "home": inp.home,
             "away": inp.away, "home_names": list(inp.home_names),
             "away_names": list(inp.away_names),
             "competition": inp.competition, "sport": inp.sport,
             "kickoff_utc": inp.kickoff_utc.isoformat(),
             "venue": inp.venue, "langs": list(inp.langs),
             "checklist": list(inp.checklist), "gaps": list(inp.gaps)},
            ensure_ascii=False)}]
    steps: list[str] = []
    limit = max_turns()
    draft = ""
    done_args: dict | None = None
    stop = ""
    for turn in range(limit):
        # 🔴🔴 **매 8턴 리마인드**(작업 지시서 §1) — 48턴 배회의 재발 방지.
        #    ⚠️ 시스템 줄이 아니라 **사용자 줄**로 넣는다 — 시스템 프롬프트는
        #       §2 가 *"고정 문자열"* 이라 했고(캐시 단가) 중간에 바꿀 수 없다.
        if turn and turn % REMIND_EVERY == 0:
            msgs.append({"role": "user",
                         "content": remind_line(list(inp.checklist))})
        try:
            got = solar.chat(msgs, tools=tool_specs(), budget=bud,
                             match=inp.match_key, _net=net)
        except solar.SolarUnavailable as exc:
            if funnel is not None:
                funnel.drop(_why_of(exc), "agent_vars")
            return [], f"{exc} · 밟은 턴 {turn}"
        msg = _msg_of(got)
        calls = _calls_of(msg)
        if not calls:
            # ⚠️ 도구도 안 부르고 글만 냈다 — **끝낸 것**이다
            draft = str(msg.get("content") or "")
            # 🔴 **그 글을 로그에 남긴다** — 왜 `done` 을 안 불렀는지는 그 글에
            #    있다. ⚠️ 실측 2026-10-04: 두 번 그 자리에 왔는데 모델이 무슨
            #    말을 했는지 알 수 없었다(사유에 글이 안 실렸다).
            logger.info("[agent] 🔴 턴 %d — 도구 없이 글을 냈다: %s",
                        turn + 1, draft[:600])
            stop = f"모델이 도구 없이 글을 냈다(턴 {turn + 1})"
            break
        msgs.append({"role": "assistant", "content": msg.get("content"),
                     "tool_calls": msg.get("tool_calls")})
        done = False
        for cid, name, args in calls:
            res = call_tool(tools, name, args)
            steps.append(f"{name}:{'ok' if res.get('ok') else res.get('reason')}")
            # 🔴 **로그에 남긴다** — 카드가 줄을 걸러도 로그엔 남아야 한다.
            #    ⚠️ 실측 2026-10-04: 턴 상한에 걸렸는데 카드가 그 줄을 걸러
            #       **무슨 도구를 몇 번 불렀는지** 알 수 없었다.
            logger.info("[agent] 턴 %d · %s(%s) → %s %s", turn + 1, name,
                        str(args)[:80], "ok" if res.get("ok") else "거부",
                        str(res.get("why") or "")[:120])
            if name == "done":
                # 🔴 **`done` 거부 루프를 지웠다**(지시서 2026-10-05 §1).
                #    ⚠️ 거부가 예산을 태웠다(실측: 출력 25k 소진 · 변수
                #       18→0). 🔴 커버리지 보장은 **거부에서 분할로**
                #       옮겼다(§2 하위 과제 8개) — 승계 계약은 M59 와
                #       장부 `found` 배선이다.
                # 🔴 **인자가 스키마다** — 글자로 다시 돌리지 않는다
                done_args = dict(args)
                done = True
                # 🔴 **인자를 로그에 남긴다** — 변수 0개일 때 *무엇을 받았나*를
                #    볼 수 있어야 한다(실측 2026-10-04: 두 번 그 자리에 왔다).
                # 🔴 **꼴을 함께 적는다** — 실측 2026-10-05: `변수 15455줄`
                #    이라 적혀 있었고 그것은 **문자 수**였다(모델이 문자열을
                #    보냈다). 터지기 전 유일한 단서가 거짓을 말했다.
                _got = done_args.get("variables")
                logger.info("[agent] 🔴 `done` 인자 칸=%s · 변수 %s %d · 머리=%s",
                            sorted(done_args), type(_got).__name__,
                            len(_got or []),
                            (str(_got[0])[:400] if isinstance(_got, list)
                             and _got else str(_got)[:120]))
            msgs.append({"role": "tool", "tool_call_id": cid,
                         "content": json.dumps(res, ensure_ascii=False)[:8000]})
        if done:
            stop = f"`done`(턴 {turn + 1})"
            break
    else:
        # 🔴 §3-7 — **턴 상한**. ⚠️ 그때까지의 변수로 넘긴다
        stop = f"🔴 **턴 상한** {limit}회를 다 썼다 — `done` 이 안 왔다(§3-7)"
        if funnel is not None:
            funnel.drop(Reason.BUDGET_CUT, "agent_vars")
        return [], f"{stop} · 밟은 도구 {steps[-6:]}"

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **마지막 턴에만 스키마를 강제한다**(§3-2)
    # ══════════════════════════════════════════════════════════════════
    cands: list = []
    why = ""
    if done_args is not None:
        # 🔴 **정상 길** — `done` 의 인자를 그대로 읽는다(§3-2)
        # 🔴 **받은 본문의 발행일을 함께 넘긴다**(M109) — 모델이 안 적어도
        #    ③층이 뽑은 날짜가 변수에 붙는다.
        cands, why = parse_args(done_args, inp=inp, dates=tools.dates)
    first_why = why
    for attempt in range(SCHEMA_RETRIES + 1):
        if cands:
            break
        cands, why = parse_output(draft)
        # 🔴 **첫 사유를 잃지 않는다** — 그것이 *무엇이 왜 떨어졌나*를 안다.
        #    ⚠️ 실측 2026-10-04: 예산 사유가 그것을 덮어 *"후보 0개"* 만 남았고
        #       **열한 줄이 `team` 꼴 때문에 떨어진 것**을 못 봤다(#3).
        why = f"{first_why} → {why}" if first_why and not cands else why
        if cands:
            break
        if attempt >= SCHEMA_RETRIES:
            break
        msgs.append({"role": "user", "content": (
            "🔴 그 출력이 스키마를 못 지켰다 — 다시 낸다. "
            f"({attempt + 1}/{SCHEMA_RETRIES}) 사유: {why}")})
        try:
            got = solar.chat(msgs, schema=output_schema(), budget=bud,
                             match=inp.match_key, _net=net)
        except solar.SolarUnavailable as exc:
            if funnel is not None:
                funnel.drop(_why_of(exc), "agent_vars")
            return [], f"{exc} · {stop}"
        draft = str(_msg_of(got).get("content") or "")
    if not cands:
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **M47 — 추출 실패 2회면 `done_parse_fail`**(작업 지시서 §1)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 종전 사유는 `schema_fail` 이었다. 🔴 그런데 실측 2026-10-04 에
        #     모델은 **스키마를 지켰고**(산문 속 ```json) 우리가 **못 꺼냈다** —
        #     그 둘을 한 사유로 적으면 고칠 곳이 섞인다(§8-6).
        #  🔴 `done` 이 **왔는데 못 읽은** 것이면 `done_parse_fail` 이다.
        #     ⚠️ 변수가 **0줄**인 것은 다른 일이다(`agent_zero` · `finish` 가 센다).
        bad = (Reason.DONE_PARSE_FAIL if done_args is not None or draft
               else Reason.AGENT_ZERO)
        if funnel is not None:
            funnel.drop(bad, "agent_vars")
        return [], (f"🔴 §3-7 — `{bad.value}`(추출 {SCHEMA_RETRIES}회 실패): "
                    f"{why} · {stop}")

    kept, why2 = finish(cands, funnel=funnel)
    if not kept:
        return [], f"{why2} · {stop}"
    # 🔴🔴 §5 — **관문**이다. 여기를 지난 것만 변수다.
    from app.verifylayer import verify_all
    # 🔴 `verify_all` 은 **통과한 것만** 돌려준다(폐기는 깔때기에 사유로 쌓인다).
    #    ⚠️ 내 첫 판은 `(ok, var, why)` 세 쪽을 기대했다 — 그 함수는 그렇게
    #       생기지 않았다(실측 2026-10-04: `'AgentVar' object is not subscriptable`).
    # 🔴🔴 **에이전트가 연 본문을 넘긴다** — 지시서 §1-1(안 넘기면 12/12 폐기)
    added = merge_bodies(ctx, tools)
    if added:
        logger.info("[agent] 직접 연 본문 %d건을 검증층에 넘겼다(§1-1)", added)
    ok = verify_all(kept, ctx, funnel=funnel)
    return list(ok), (
        f"{stop} · 후보 {len(kept)}개 → **검증 통과 {len(ok)}개** · "
        f"도구 {len(steps)}회 · {bud.line()}")


