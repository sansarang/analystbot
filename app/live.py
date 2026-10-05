"""🔴🔴 **v5 §7-3 — 라이브 재판정.** 일곱 규칙이 전부 *거절*에 관한 것이다.

지시문 §7-3 원문:

> 입력은 스코어·경과 분·지표 캡처(또는 어댑터 라이브 피드). 규칙:
> **스코어·경과 분 없이 재판정 금지** / **스코어로는 시나리오를 제거, 지표로는
> 약화만** / **지표 2개 이상이 같은 메커니즘을 가리킬 때만 인정** /
> **"GK 선방 0"은 상대 유효슈팅 부재가 아니다** / **라이브로 새 마켓을 만들지
> 않는다** / **15분 간격**. 라이브 판정은 **등급 승격 없이** 생존 여부만
> 갱신한다. [M29]

══════════════════════════════════════════════════════════════════
🔴 왜 — 라이브는 **고치는 자리가 아니다**
══════════════════════════════════════════════════════════════════

⚠️ 경기 중에 등급을 올리면 *"예측"* 이 아니라 *"따라가기"* 가 된다. 🔴 §3 불변:
   *"맞았나를 예측이 끝난 뒤에 고치지 않는다."* 라이브가 할 수 있는 일은
   **죽은 시나리오를 죽었다고 적는 것**뿐이다.

⚠️ **라이브 입구는 아직 없다** — 보드 캡처·라이브 피드를 받는 통로가 없다.
   🔴 그 사실을 `tests/test_wiring.py` 의 `NOT_WIRED` 가 들고 있다(#2).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app import rules
from app.reasons import Reason


@dataclass(frozen=True)
class Gate:
    """재판정해도 되나 · 왜 아닌가."""

    ok: bool
    reason: Reason
    why: str


def may_judge(*, score: object = None, minute: object = None,
              since_min: object = None) -> Gate:
    """🔴🔴 **§7-3 — 스코어·경과 분 없이 재판정 금지.**

    ⚠️ `""`·`0`·음수는 *"받았다"* 가 아니다 — fail-closed. 🔴 경과 분 `0` 은
       **킥오프 전**이고 그때는 라이브가 아니다.
    """
    got_score = str(score or "").strip()
    try:
        mins = int(minute) if minute is not None else 0
    except (TypeError, ValueError):
        mins = 0
    if not got_score or mins <= 0:
        return Gate(False, Reason.LIVE_NO_INPUT, (
            f"🔴 §7-3 — 스코어 `{got_score or '없음'}` · 경과 분 "
            f"`{minute if minute is not None else '없음'}`. **둘 다** 있어야 한다"))
    if since_min is not None:
        want = int(rules.live_rules()["interval_min"])
        if int(since_min) < want:
            return Gate(False, Reason.LIVE_WEAK_METRIC, (
                f"🔴 §7-3 — 지난 판정에서 {since_min}분밖에 안 지났다"
                f"(간격 **{want}분**)"))
    return Gate(True, Reason.OK, f"§7-3 — 스코어 {got_score} · {mins}분")


def effect_of(kind: str) -> str:
    """🔴 그 입력이 **무엇을 할 수 있나** — `제거` · `약화` · `없음`.

    ⚠️ 지표(점유율·xG)는 **일어난 일이 아니다** — 경향이다. 🔴 경향으로
       시나리오를 지우면 아직 가능한 결과를 카드에서 없애는 것이다.
    🔴 모르는 입력은 **아무 일도 하지 않는다**(지어내지 않는다 · #4).
    """
    got = (rules.live_rules().get("effects") or {}).get(str(kind or ""))
    return str(got or "없음")


def metrics_ok(metrics: list) -> tuple[bool, str]:
    """🔴 *"지표 2개 이상이 **같은 메커니즘**을 가리킬 때만 인정"*(§7-3).

    ⚠️ 메커니즘이 다른 지표 둘은 *"둘"* 이 아니다 — 다른 이야기 하나씩이다.
    """
    cfg = rules.live_rules()
    need = int(cfg.get("metrics_min") or 2)
    items = [m for m in (metrics or []) if isinstance(m, dict)]
    if len(items) < need:
        return False, (f"🔴 §7-3 — 지표 {len(items)}개로는 인정하지 않는다"
                       f"(**{need}개 이상**)")
    if cfg.get("metrics_same_mechanism"):
        mechs = {str(m.get("mechanism") or "") for m in items}
        if len(mechs) != 1 or "" in mechs:
            return False, (f"🔴 §7-3 — 지표들이 **다른 메커니즘**을 가리킨다"
                           f"({sorted(mechs)}). 같은 것을 가리킬 때만 인정한다")
    return True, (f"§7-3 — 지표 {len(items)}개가 같은 메커니즘을 가리킨다 "
                  f"→ **약화**(제거는 스코어만)")


def reads_as_no_shots(stats: dict | None) -> tuple[bool, str]:
    """🔴🔴 **"GK 선방 0"은 상대 유효슈팅 부재가 아니다**(§7-3 이 이름으로 댄 함정).

    ⚠️ `saves == 0` 은 *"상대가 유효슈팅을 못 냈다"* 가 아니다 — **골이 들어갔을
       때도** 선방은 0 이다. 🔴 그 둘을 같게 보면 수비 시나리오가 **살아남는다.**
    🔴 **유효슈팅 수를 직접 받았을 때만** 그렇게 읽는다.
    """
    got = dict(stats or {})
    if "shots_on_target" not in got:
        return False, ("🔴 §7-3 — `GK 선방 0` 을 *상대 **유효슈팅** 부재* 로 읽지 "
                       "않는다(골이 들어가도 선방은 0 이다). 유효슈팅 수를 "
                       "직접 받아야 한다")
    n = got.get("shots_on_target")
    try:
        n = int(n)
    except (TypeError, ValueError):
        return False, f"🔴 유효슈팅 수가 수가 아니다({n!r})"
    return n == 0, f"유효슈팅 {n}개"


@dataclass
class Markets:
    """🔴 라이브가 **건드릴 수 있는** 마켓과 거절한 것."""

    kept: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)
    why: str = ""


def keep_markets(before: list, *, proposed: list) -> Markets:
    """🔴 *"라이브로 새 마켓을 만들지 않는다"*(§7-3).

    ⚠️ 있던 마켓의 **생존만** 갱신한다. 🔴 거절한 것을 **이름으로** 남긴다(#3).
    """
    had = [str(x) for x in (before or [])]
    want = [str(x) for x in (proposed or [])]
    kept = [x for x in had if x in want]
    refused = [x for x in want if x not in had]
    out = Markets(kept=kept, refused=refused)
    out.why = (f"§7-3 — 유지 {len(kept)}개"
               + (f" · 🔴 **새 마켓** {refused} 는 거절했다(라이브로 만들지 "
                  f"않는다)" if refused else ""))
    return out


def cap_verdict(*, before: str, after: str) -> str:
    """🔴🔴 **등급 승격 없이**(M29) — 올라가는 것은 전 등급으로 **묶는다.**

    ⚠️ 내려가는 것은 된다 — 죽은 시나리오를 죽었다고 적는 것이 라이브의 일이다.
    🔴 순위는 `survive` 가 들고 있다(여기서 다시 적지 않는다 · #1).
    """
    if rules.live_rules().get("promote"):
        return str(after)
    # 🔴 순위표는 `triggers._RANK` 하나다 — 여기서 다시 적지 않는다(#1 사본 금지).
    #    ⚠️ 그 표가 늘면(등급이 생기면) 이 함수가 따라간다.
    from app.triggers import _RANK
    b, a = _RANK.get(str(before), 0), _RANK.get(str(after), 0)
    return str(after) if a <= b else str(before)
