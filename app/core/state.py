"""🔴🔴 **v6 §2 — 실행 상태 하나.** `RunState` 가 단계마다 함께 다닌다.

지시서 §2: *"실행 중 누적되는 것(비용, 장부, 깔때기, 폐기 사유)은 `RunState`
객체 **하나**에 담아 각 단계에 넘긴다. **전역 변수·모듈 캐시에 실행 상태를 두지
않는다**(병렬·재생에서 새는 원인이었다)."*

⚠️ 실사고 2026-10-06: `solar.SAW_429`·`GdeltSearch._state`·`get_settings` 캐시가
   모듈에 살아 **다른 계약을 흔들었다**(병렬 스위트에서 실측). 🔴 그래서 여기 둔다.

🔴 이것은 **`schema.py` 에 못 둔다** — 그쪽은 전부 `frozen` 이고, 이쪽은 **쌓이는
   것**이다. 두 성질을 한 파일에 섞으면 `frozen` 규칙이 흐려진다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.schema import Cost, Drop, DropReason

#: 🔴 깔때기 칸 이름 — 순서가 뜻이다(앞 칸이 뒷 칸의 입력이다).
#   ⚠️ **안 잰 칸은 `None`** 으로 둔다 — `0` 은 *"재 봤는데 없다"* 다(#3).
STAGES: tuple[str, ...] = ("queries", "hits", "kept_date", "docs",
                           "candidates", "variables", "scenarios",
                           "markets_graded")


@dataclass
class Wallet:
    """🔴 그 경기의 **지갑 하나** — 예산 판정은 여기서만 한다(§4)."""

    usd: float = 0.0
    calls: int = 0
    in_tokens: int = 0
    out_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    #: 🔴 **막혔으면 그 사유** — 비면 아직 쓸 수 있다
    blocked: str = ""

    def took(self, *, usd: float, in_: int, out: int, cached: int,
             reasoning: int) -> None:
        self.usd = round(self.usd + float(usd), 6)
        self.calls += 1
        self.in_tokens += int(in_)
        self.out_tokens += int(out)
        self.cached_tokens += int(cached)
        self.reasoning_tokens += int(reasoning)

    def snapshot(self) -> Cost:
        """🔴 카드에 싣는 꼴로 — `schema.Cost` 는 얼려 있다."""
        return Cost(usd=self.usd, calls=self.calls, in_tokens=self.in_tokens,
                    out_tokens=self.out_tokens,
                    cached_tokens=self.cached_tokens,
                    reasoning_tokens=self.reasoning_tokens)


@dataclass
class RunState:
    """🔴🔴 **한 실행의 전부** — 비용·깔때기·장부·사유가 여기 모인다."""

    #: 🔴 ⑦(2026-10-11) — **마지막 LLM 실패 사유**(`llm_truncated` 등).
    #  ⚠️ 잘린 것과 못 쓴 것은 다르다 — 호출부가 그것으로 **축약판**을 고른다.
    last_llm_reason: str = ""

    match_key: str = ""
    wallet: Wallet = field(default_factory=Wallet)
    #: 🔴 칸별로 **센 수**. ⚠️ 안 잰 칸은 넣지 않는다(`None` 으로 보인다)
    counts: dict[str, int] = field(default_factory=dict)
    drops: list[Drop] = field(default_factory=list)
    #: 🔴 하위 과제 장부 — `SubtaskId → 상태`(옛 `ledgerbook` 을 대체한다 · §6)
    book: dict[str, str] = field(default_factory=dict)
    #: 🔴 사람이 읽을 자취 — 카드가 블록 1 에 적는다
    notes: list[str] = field(default_factory=list)

    def set(self, stage: str, n: int) -> None:
        """🔴 그 칸을 **셌다**. ⚠️ 모르는 칸 이름은 터진다(사본 금지)."""
        if stage not in STAGES:
            raise KeyError(f"🔴 모르는 깔때기 칸이다: {stage!r} — {STAGES}")
        self.counts[stage] = int(n)

    def drop(self, what: str, reason: DropReason, detail: str = "") -> None:
        """🔴 버린다 — **까닭이 반드시 남는다**(#3)."""
        self.drops.append(Drop(what=str(what), reason=reason,
                               detail=str(detail)))

    def note(self, said: str) -> None:
        self.notes.append(str(said))

    def counted(self) -> dict[str, int | None]:
        """🔴 깔때기 칸 전부 — **안 잰 칸은 `None`**(0 이 아니다 · #3)."""
        return {s: self.counts.get(s) for s in STAGES}
