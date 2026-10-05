"""🔴🔴 **에이전트 출력 꼴** — v5 §3-6. [#10]

> ```json
> {"variables": [{"id":"R1","type":"absence_def","team":"team:000151",
>   "direction_hint":"opp_goals_up","claim":"...","quote":"...","url":"...",
>   "published_at":"...","lang":"en","conflict":false,"reverified":true}],
>  "hypotheses": {...}, "scenarios": [...], "gaps": [...], "notes": "..."}
> ```

🔴 §1 의 한 줄이 이 파일의 까닭이다: *"에이전트는 **제안만** 한다. 변수·시나리오·
   마켓 등급 어느 것도 에이전트 출력이 **그대로 카드로 가지 않는다**. 검증층을
   통과한 변수만 변수이고, 판정층이 계산한 등급만 등급이다."*

⚠️ 그래서 이 꼴은 **신뢰 0**에서 시작한다 — `app/verifylayer.py` 가 관문이다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

#: 🔴 §3-6 `direction_hint` — ⚠️ **참고일 뿐**이다(§5-4 가 다시 정한다).
HINTS: tuple[str, ...] = ("home", "away", "both", "goals_up", "goals_down",
                          "opp_goals_up", "opp_goals_down")

#: 🔴 같은 목록의 **다른 이름** — 프롬프트·스키마·계약이 이 이름으로 부른다.
#   ⚠️ 값을 **베끼지 않는다**(`HINTS` 하나가 원본이다 · 사본 금지).
#
#  🔴 실측 2026-10-05: 이 목록을 **모델에게 한 번도 말하지 않아서** 변수
#     **10줄이 전부** 버려졌다(`direction_hint` 에 자유 문장을 썼다).
#     ⚠️ 프롬프트에도 스키마에도 없었다 — 코드가 **아는 것을 안 알려 주고**
#     그 답을 버린 꼴이다(§1-1 의 `12→0` 과 같다).
DIRECTION_HINTS = HINTS


@dataclass(frozen=True)
class AgentVar:
    """🔴 에이전트가 낸 **변수 후보 하나**(§3-6). ⚠️ 아직 변수가 아니다."""

    id: str
    type: str
    team: str | None
    claim: str
    quote: str
    url: str
    published_at: datetime | None
    direction_hint: str = "both"
    #: 🔴🔴 **누구에 관한 사실인가**(팀 열쇠) — 지시 2026-10-05.
    #
    #  ⚠️ `direction_hint` 는 *"누구에게 유리한가"* 를 묻는 칸이었는데 모델이
    #     *"누구에 관한 사실인가"* 로 썼다 — 실측: 포르투갈 결장이 **포르투갈
    #     근거**로, 포르투갈 8강 확정이 **포르투갈 근거**로 들어갔다(둘 다 거꾸로).
    #  🔴 두 질문을 **두 칸**으로 가른다: `subject`(관한) · `favors`(유리).
    #     ⚠️ `favors` 는 **코드가** 카탈로그 규칙으로 계산한다(모델이 안 낸다).
    #  🔴 비면 `team` 을 쓴다 — 종전 호출부가 살아 있다.
    subject: str | None = None
    lang: str = "en"
    conflict: bool = False
    #: 🔴 §5-8 · M31 — 이전 슬레이트의 변수를 재검색 없이 썼나
    reverified: bool = True

    def __post_init__(self):
        if not str(self.id or "").strip():
            raise ValueError("🔴 변수에 `id` 가 없다(§3-6)")
        if self.direction_hint not in HINTS:
            raise ValueError(
                f"🔴 모르는 `direction_hint` 다: {self.direction_hint!r} — "
                f"§3-6 이 이름 댄 것은 {list(HINTS)}")
        if self.team is not None and not str(self.team).startswith("team:"):
            raise ValueError(
                f"🔴 `team` 은 **열쇠**여야 한다(§8-1): {self.team!r}")


@dataclass
class AgentOutput:
    """🔴 §3-6 전체. ⚠️ `scenarios` 는 **초안**이고 §6-2 가 보강한다."""

    variables: list[AgentVar] = field(default_factory=list)
    hypotheses: dict = field(default_factory=dict)
    scenarios: list[dict] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    notes: str = ""
