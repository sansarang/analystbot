"""🔴🔴 **v5 §7-5 — 자료 부족을 선언할 자격.**

지시문 §7-5 원문:

> **사다리 2단계 이상 · 도구 호출 6회 이상**을 실제로 돈 **로그가 있을 때만**
> R5 자료 부족을 선언한다. 그 전에 선언하면 `premature_insufficient` 실패.

══════════════════════════════════════════════════════════════════
🔴 왜 — *"자료가 안 왔다"* 와 *"우리가 안 찾았다"* 는 다른 말이다
══════════════════════════════════════════════════════════════════

⚠️ 실측 2026-10-02(중국 vs 팔레스타인 친선): 사실 6건 · 변수 **0건** ·
   §7 R5 자료 부족. 🔴 그런데 그 경기의 **자료 주소는 `ext_id` 에 적혀 있었다**
   (`fotmob-6280453`) — 깊이 라우팅이 안 돌아 **아예 안 찾은** 것이다.
   그것을 *"자료 부족"* 이라 적으면 **우리 결함이 자료 탓으로 기록된다.**

🔴 §8-6 이 막는 거짓 사유가 이 섞임이다:

    insufficient              fix_where = 수집   (자료가 없다)
    premature_insufficient    fix_where = 판정   🔴 **우리 버그다**
"""
from __future__ import annotations

from dataclasses import dataclass

from app import thresholds
from app.reasons import Reason


@dataclass(frozen=True)
class Verdict:
    """선언해도 되나 · 왜 아닌가 · **얼마나 돌았나**."""

    ok: bool
    reason: Reason
    why: str
    tool_calls: int
    angles: int | None

    def line(self) -> str:
        """🔴 카드에 적는 한 줄. ⚠️ **수를 그대로** 적는다(#3 조용한 0 금지)."""
        ang = "못 쟀다" if self.angles is None else str(self.angles)
        return (f"§7-5 — 도구 {self.tool_calls}회 · 사다리 각도 {ang} "
                f"(문턱 {_min_calls()}회 · {_min_steps()}단계) → "
                + ("선언 가능" if self.ok else self.why))


def _min_steps() -> int:
    return int(thresholds.value("r5_min_ladder_steps"))


def _min_calls() -> int:
    return int(thresholds.value("r5_min_tool_calls"))


def tool_calls_of(fun) -> int:
    """🔴 **도구 호출 수** = 던진 검색어 + 받은 페이지.

    ⚠️ §3 도구는 `search`·`fetch` 둘이다(`done` 은 끝내는 것이라 세지 않는다) —
       그 둘이 깔때기의 `queries`·`fetched` 다. 🔴 새 계수기를 만들지 않는다.
    """
    counts = getattr(fun, "counts", {}) or {}
    return int(counts.get("queries", 0)) + int(counts.get("fetched", 0))


def may_declare(fun) -> Verdict:
    """🔴🔴 **R5 를 선언해도 되나.**

    🔴 **fail-closed**: 각도를 **안 쟀으면**(`None`) 선언할 수 없다.
       ⚠️ 0 으로 보고 *"안 돌았다"* 로 읽으면 맞게 보이지만, 그러면 `None` 과
          `0` 이 한 글자가 된다 — *"안 쟀다"* 와 *"재 봤는데 0"* 은 고칠 곳이
          다르다.
    """
    calls = tool_calls_of(fun)
    angles = getattr(fun, "angles", None)
    if angles is None:
        return Verdict(
            False, Reason.PREMATURE_INSUFFICIENT,
            (f"🔴 사다리 각도를 **못 쟀다** — 몇 각도로 물었는지 모르는 채로는 "
             f"*'자료가 없다'* 고 말할 수 없다(§7-5 · fail-closed)"),
            calls, None)
    if angles < _min_steps():
        return Verdict(
            False, Reason.PREMATURE_INSUFFICIENT,
            (f"🔴 사다리 각도가 **{angles}** 뿐이다(문턱 {_min_steps()}) — "
             f"우리가 **덜 찾았다**. 자료 탓이 아니다(§7-5)"),
            calls, angles)
    if calls < _min_calls():
        return Verdict(
            False, Reason.PREMATURE_INSUFFICIENT,
            (f"🔴 도구를 **{calls}회** 밖에 부르지 않았다(문턱 {_min_calls()}) — "
             f"우리가 **덜 찾았다**. 자료 탓이 아니다(§7-5)"),
            calls, angles)
    return Verdict(True, Reason.OK,
                   f"§7-5 충족 — 도구 {calls}회 · 각도 {angles}", calls, angles)
