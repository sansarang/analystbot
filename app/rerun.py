"""🔴🔴 **v5 §7-1 — T-60 재실행.** 확정 XI 를 가져오고 §5~§6 을 다시 돈다.

지시문 §7-1 원문:

> 킥오프 **60분 전(야구는 70분 전)** 코드가 확정 XI 를 가져온다. 순서:
> **어댑터**(statsapi probable/lineup, fotmob HTML 경기 페이지) → **공식 사이트
> 직독** → **에이전트 search**(검색어에 starting XI / 스타멘 / 선발 라인업 +
> 날짜 강제). 가져오면 `lineup_state` 를 `confirmed` 로 올리고 §5~§6 을 재실행,
> **카드 1회 갱신**(R10). 못 가져오면 카드에 **XI 미확정 — 발표 전/미검증**을
> 적고 **상한 0.85 를 강제**한다. **낡은 XI 를 기준 XI 로 쓰면 계약 실패**
> (크로아티아 카드: 트래퍼드 선발).

══════════════════════════════════════════════════════════════════
🔴 왜 — 카드는 **킥오프 전에 한 번 더** 맞을 기회가 있다
══════════════════════════════════════════════════════════════════

⚠️ 확정 XI 는 보통 킥오프 1시간 전에 나온다. 그때까지의 카드는 **예상 XI** 로
   세운 것이고 상한 0.85 다(§6-5). 🔴 확정을 받으면 상한이 풀리고, 그 한 번의
   갱신이 **등급을 바꾼다.**

🔴 **한 번뿐이다**(R10). 두 번 갱신하면 *"예측을 언제 했나"* 가 흐려지고 채점이
   거짓이 된다 — §3 불변이 *"맞았나를 예측이 끝난 뒤에 고치지 않는다"* 다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app import rules, survive, trigcond

#: 🔴 §7-1 원문 순서. ⚠️ **순서가 뜻이다** — 어댑터가 1층(공식 API)이고 에이전트
#  검색이 가장 약하다(§4-3 도메인 등급). 뒤집으면 약한 자료가 확정 XI 로 선다.
ORDER: tuple[str, ...] = ("adapter", "official", "agent")


def window_min(sport: str) -> int:
    """🔴 그 종목의 재실행 창(분). ⚠️ 수를 코드에 박지 않는다(§7-1 · yaml)."""
    cfg = rules.rerun_window()
    mins = cfg.get("minutes") or {}
    got = mins.get(str(sport or ""))
    if got is None:
        # ⚠️ 지시문이 **두 종목만** 이름 댔다 — 나머지는 기본값이다
        return int(cfg.get("default") or 60)
    return int(got)


def due(kickoff, *, now=None, sport: str = "") -> bool:
    """🔴 **지금이 그 창인가.** ⚠️ 이미 시작한 경기는 아니다(경기 전만이다)."""
    if kickoff is None:
        return False
    at = now or datetime.now(timezone.utc)
    mins = (kickoff - at).total_seconds() / 60.0
    return 0 < mins <= window_min(sport)


@dataclass(frozen=True)
class NoXi:
    """🔴 확정 XI 를 **못 가져왔다** — 상한을 강제한다."""

    cap: float
    state_word: str = "미확정"

    def line(self) -> str:
        """🔴 카드에 적는 글. ⚠️ *"발표 전"* 과 *"미검증"* 을 **둘 다** 적는다.

        §6-5 가 같은 가름을 요구했다 — 미공개(기다리면 온다)와 미검증(우리가
        대조를 못 했다)은 **고칠 곳이 다르다**(§8-6).
        """
        return (f"🔴 **XI {self.state_word}** — 발표 전이거나 받았지만 미검증이다"
                f"(§7-1). 등급 상한 **{self.cap}** 을 강제한다")


def without_xi() -> NoXi:
    """🔴 §7-1 — *"못 가져오면 … 상한 0.85 를 강제한다."*"""
    cfg = rules.rerun_window()
    cap = cfg.get("cap_without_xi")
    if cap is None:
        raise KeyError("`rerun_window.cap_without_xi` 가 없다 — §7-1 이 원본이다")
    return NoXi(cap=float(cap))


@dataclass(frozen=True)
class GotXi:
    """🔴 확정 XI 를 **받았다** — §6-5 의 어느 칸인가."""

    state: str
    cap: float | None

    def line(self) -> str:
        return (f"✅ **XI {self.state}**(§7-1 재실행) → 등급 상한 "
                + (f"**{self.cap}**" if self.cap is not None else "없음"))


def with_xi(*, both: bool, verified: bool) -> GotXi:
    """🔴 받은 XI 를 **§6-5 의 칸 이름**으로 옮긴다.

    ⚠️ 칸 이름을 여기서 **새로 짓지 않는다** — `xi_state_cap.caps` 가 원본이고
       상한도 그 표가 정한다(#1 사본 금지).
    🔴 미검증이면 **한 단계 아래**다(§6-5) — `survive.step_down` 이 그 사다리다.
    """
    state = "양쪽확정" if both else "한쪽확정"
    caps = {str(k): float(v) for k, v in
            (rules.xi_state_cap().get("caps") or {}).items()}
    cap = caps[state]
    if not verified:
        state += survive.UNVERIFIED_MARK
        cap = survive.step_down(cap)
    return GotXi(state=state, cap=cap if cap < 1.0 else None)


def fresh_xi(xi: dict | None, *, kickoff) -> tuple[bool, str]:
    """🔴🔴 **낡은 XI 를 기준 XI 로 쓰면 계약 실패**(§7-1).

    ⚠️ 실사고(크로아티아 카드): 카드가 **트래퍼드 선발**을 적었다 — 그것은
       **지난 경기**의 XI 였다. 🔴 지난 XI 는 *"이 경기의 기준"* 이 아니다.

    🔴 **날짜가 없으면 받지 않는다**(fail-closed) — 낡았는지 **알 수 없다**.
       ⚠️ 받아 주면 그 XI 가 확정으로 서고 상한이 풀린다(우리에게 유리한 거짓).
    """
    got = dict(xi or {})
    if not got.get("players"):
        return False, "🔴 XI 에 선수가 없다 — 기준 XI 가 아니다"
    said = str(got.get("match_date") or "").strip()
    if not said:
        return False, ("🔴 XI 에 **경기 날짜가 없다** — 이 경기 것인지 **모른다**. "
                       "§7-1: 낡은 XI 를 기준으로 쓰지 않는다(fail-closed)")
    want = kickoff.date().isoformat()
    if said != want:
        return False, (f"🔴 **낡은 XI** 다 — 적힌 날짜 `{said}` 가 이 경기 "
                       f"`{want}` 가 아니다(§7-1 · 크로아티아 카드 사례)")
    return True, f"✅ XI 날짜 `{said}` 가 이 경기와 같다"


def may_update(*, done_at) -> tuple[bool, str]:
    """🔴 §7-1 — *"카드 **1회** 갱신(R10)"*. 두 번째는 거절한다.

    ⚠️ 그 기억은 **DB 에 있어야** 한다(`sufficiency.rerun_at`) — 프로세스가
       죽으면 메모리는 사라지고 카드를 또 바꾼다.
    """
    if done_at is None:
        return True, "§7-1 재실행 — 아직 갱신하지 않았다"
    return False, (f"🔴 **이미 갱신했다**({done_at}) — §7-1 은 **1회**다(R10). "
                   f"두 번 바꾸면 *'예측을 언제 했나'* 가 흐려진다")


def check_scenarios(*, before: int, after: int) -> tuple[bool, str]:
    """🔴🔴 **M2 — 재실행에서 시나리오 수가 줄면 실패.**

    ⚠️ 판정은 `trigcond.rerun_ok` 하나다 — 여기서 다시 세지 않는다(#1).
    """
    return trigcond.rerun_ok(before=before, after=after)
