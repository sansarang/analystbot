"""🔴🔴 **v5 §7-2 — 방아쇠의 *기계 조건*.** 사람 글이 아니라 평가되는 식이다.

지시문 §7-2 원문:

> 카드마다 명단에서 확인할 항목을 **1개 이상 기계 조건**으로 적는다
> (`"player:… in XI"`, `"changes_from_last >= 5"`, `"formation == 5-back"`).
> T-60 재실행이 조건을 **평가**해 걸리면 등급을 그 자리에서 바꾸고, **평가
> 불가면** 결론을 `trigger_unresolved` 로 표시해 **베팅 등급이 아님**을
> 명시한다(M28). 재실행에서 **시나리오 수가 줄면 실패**(M2).

══════════════════════════════════════════════════════════════════
🔴 왜 — 사람이 읽는 글은 **기계가 평가할 수 없다**
══════════════════════════════════════════════════════════════════

종전 방아쇠의 `watch` 는 사람 글이었다(*"`lineup` 세포가 깨는 T-70분"*).
⚠️ T-60 재실행이 그 글을 보고 **무엇을 참으로 볼지** 정할 수 없다. 🔴 그러면
   재실행이 등급을 바꿀 수 없고, *"바꾸지 못했다"* 와 *"조건이 안 걸렸다"* 가
   **한 글자**가 된다(§8-6).

══════════════════════════════════════════════════════════════════
🔴🔴 **세 값이다 — `True` · `False` · `None`**
══════════════════════════════════════════════════════════════════

    True   걸렸다          → 등급을 그 자리에서 바꾼다
    False  안 걸렸다       → 등급 그대로
    None   **평가 불가**    → `trigger_unresolved` · **베팅 등급이 아니다**(M28)

⚠️ `None` 을 `False` 로 때우면 *"명단에 그 선수가 없다"* 와 *"명단을 못 받았다"*
   가 한 글자가 되고, 등급이 **그대로 남는다** — 그것이 돈을 잃는 자리다.

🔴 **식을 지어내지 않는다** — 못 읽는 글은 `None` 이고 조건이 아니다(#4).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.reasons import Reason

#: 🔴 지시문이 **보기로 든 세 꼴**. ⚠️ 여기 없는 꼴은 조건이 아니다.
KINDS: tuple[str, ...] = ("in_xi", "changes_from_last", "formation")

#: 🔴 꼴마다 **읽는 정규식**과 **명단의 어느 칸**을 보나.
#  ⚠️ 글자를 두 곳에 적지 않는다 — 파싱도 평가도 이 표를 본다.
_GRAMMAR: dict[str, tuple[re.Pattern, str]] = {
    "in_xi": (re.compile(r"^player:(?P<v>.+?)\s+in\s+XI$", re.I), "players"),
    "changes_from_last": (
        re.compile(r"^changes_from_last\s*(?P<op>>=|<=|==|>|<)\s*(?P<v>\d+)$"),
        "changes_from_last"),
    "formation": (re.compile(r"^formation\s*==\s*(?P<v>\S+)$"), "formation"),
}

_OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b,
        "==": lambda a, b: a == b, ">": lambda a, b: a > b,
        "<": lambda a, b: a < b}


@dataclass(frozen=True)
class Cond:
    """읽어 둔 조건 하나."""

    kind: str
    value: str
    op: str = "=="
    raw: str = ""


def parse(expr: object) -> Cond | None:
    """식 → `Cond`. 🔴 **못 읽으면 `None`** — 대충 참으로 보지 않는다."""
    s = " ".join(str(expr or "").split())
    if not s:
        return None
    for kind, (rx, _field) in _GRAMMAR.items():
        m = rx.match(s)
        if m:
            got = m.groupdict()
            return Cond(kind=kind, value=str(got.get("v") or "").strip(),
                        op=str(got.get("op") or "=="), raw=s)
    return None




def evaluate(expr: object, xi: dict | None) -> tuple[bool | None, str]:
    """🔴🔴 **세 값**: `True` 걸렸다 · `False` 안 걸렸다 · `None` 평가 불가.

    ⚠️ 칸마다 따로다 — 선수 목록은 있는데 포메이션이 없는 명단이 실제로 온다
       (예상 XI 는 포메이션을 안 적는 매체가 많다).
    """
    cond = parse(expr)
    if cond is None:
        return None, f"조건을 **읽을 수 없다**(기계 조건이 아니다): {expr!r}"
    got = dict(xi or {})
    key = _GRAMMAR[cond.kind][1]
    if key not in got or got[key] in (None, [], ""):
        return None, (f"**평가 불가** — 명단의 `{key}` 를 못 받았다"
                      f"(§7-2 M28: `trigger_unresolved`)")
    if cond.kind == "in_xi":
        names = [str(x) for x in (got[key] or [])]
        hit = cond.value.casefold() in {n.casefold() for n in names}
        return hit, (f"`{cond.value}` 가 명단에 "
                     f"{'있다' if hit else '없다'}({len(names)}명)")
    if cond.kind == "formation":
        hit = str(got[key]).strip().casefold() == cond.value.casefold()
        return hit, f"포메이션 `{got[key]}` vs `{cond.value}`"
    # changes_from_last
    try:
        n = int(got[key])
        want = int(cond.value)
    except (TypeError, ValueError):
        return None, f"**평가 불가** — `{key}` 가 수가 아니다({got[key]!r})"
    fn = _OPS.get(cond.op)
    if fn is None:
        return None, f"**평가 불가** — 모르는 비교 `{cond.op}`"
    return bool(fn(n, want)), f"변경 {n}명 {cond.op} {want}"


@dataclass
class Resolution:
    """🔴 **카드 하나의** 방아쇠 평가 결과."""

    fired: list[str] = field(default_factory=list)
    quiet: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    whys: list[str] = field(default_factory=list)
    #: 🔴 조건이 **0 개**였나(§7-2: 카드마다 1개 이상)
    none_given: bool = False

    @property
    def betting_grade(self) -> bool:
        """🔴🔴 **평가 불가가 하나라도 있으면 베팅 등급이 아니다**(M28)."""
        return not self.unresolved and not self.none_given

    @property
    def reason(self) -> Reason:
        return (Reason.OK if self.betting_grade
                else Reason.TRIGGER_UNRESOLVED)

    def line(self) -> str:
        """카드에 적는 한 줄. 🔴 **수를 그대로** 적는다(#3)."""
        if self.none_given:
            return ("🔴 §7-2 — 기계 조건이 **0개**다(카드마다 **1개 이상**이어야 "
                    "한다). `trigger_unresolved` · **베팅 등급이 아니다**")
        head = (f"§7-2 — 걸림 {len(self.fired)} · 안 걸림 {len(self.quiet)} · "
                f"평가 불가 {len(self.unresolved)}")
        if self.unresolved:
            return (f"{head} 🔴 `trigger_unresolved`({', '.join(self.unresolved)}) "
                    f"— **베팅 등급이 아니다**(M28)")
        return head


def resolve(exprs: list, xi: dict | None) -> Resolution:
    """🔴 조건 목록을 명단에 대고 평가한다.

    ⚠️ 조건이 **0 개**면 그것 자체가 실패다 — §7-2 는 *"카드마다 1개 이상"* 이다.
    """
    out = Resolution()
    items = [e for e in (exprs or []) if str(e or "").strip()]
    if not items:
        out.none_given = True
        return out
    for e in items:
        ok, why = evaluate(e, xi)
        out.whys.append(f"{e} → {why}")
        if ok is None:
            out.unresolved.append(str(e))
        elif ok:
            out.fired.append(str(e))
        else:
            out.quiet.append(str(e))
    return out




