"""🔴🔴 **변수 배치** — 상성 중심 확률 엔진 지시서(2026-10-10 여섯째) S1V V-3·V-4.

> 변수마다 배치표로 자리를 정한다 — ① 상성 축의 입력 ② 검증 출처 ③ 가설의 근거.
> **확률에 닿는 길은 ①(상성 축을 통해, 적합된 크기로)뿐이다.**
> 표에 없는 유형이 나오면 **배치 실패** → 근거 불가로 내리고 운영자 알림.
> 근거 불가 변수는 ①②에 못 들어가고 ③에서도 맥락으로만.

🔴 표는 `config/variable_routing.yaml` 하나다(사본 금지 — 여기 자리를 적지 않는다).
🔴 이 파일은 **배치만** 한다 — 축이 그 변수를 어떻게 쓰는지는 S2 가 정한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

CONF = "config/variable_routing.yaml"
#: 🔴 자리 열거값 — 표의 `places` 칸과 같아야 한다(계약이 센다)
AXES = ("axis0", "axis1", "axis2", "axis3")
VERIFY = ("V1", "V2", "V3", "V4", "V5", "V6")
CONST = "lambda_const"
HYPO = "hypo"


def table() -> dict:
    """🔴 배치표 — `config/variable_routing.yaml`."""
    from app import rules
    return dict(rules._load(CONF) or {})


@dataclass
class VarRow:
    """🔴 V-4 — 변수 한 줄 + **배치 자리 목록**."""

    id: str = ""
    type: str = ""
    claim: str = ""
    subject: str = ""
    favors: str = ""
    hardness: str = ""
    weight: float = 0.0
    goals: str = ""
    #: 🔴 근거 불가(맥락)인가 — 그러면 ①② 자리에 못 간다
    context_only: bool = False
    places: list = field(default_factory=list)
    why: str = ""

    def axes(self) -> list:
        return [x for x in self.places if x in AXES]


@dataclass
class VariableSet:
    """🔴 V-4 산출. ⚠️ **배치 실패**와 **미배치**를 이름으로 든다(#3)."""

    rows: list = field(default_factory=list)
    #: 🔴 표에 없는 유형 — 운영자 알림 글
    fails: list = field(default_factory=list)
    #: 🔴 C5 — 근거 가능인데 **어느 자리에도 없는** 변수 id(0 이어야 한다)
    unplaced: list = field(default_factory=list)

    def of(self, place: str) -> list:
        """🔴 그 자리에 배치된 변수들(축·검증·가설 모두 같은 길)."""
        return [one for one in self.rows if str(place) in one.places]

    def ids(self, place: str) -> list:
        return [one.id for one in self.of(place)]

    def why(self) -> str:
        box = {p: len(self.of(p)) for p in (*AXES, CONST, *VERIFY, HYPO)}
        said = " · ".join(f"{k} {v}" for k, v in box.items() if v)
        return (f"변수 {len(self.rows)}개 — {said}"
                + (f" · 🔴 배치 실패 {len(self.fails)}건" if self.fails else "")
                + (f" · 🔴 미배치 {self.unplaced}" if self.unplaced else ""))


def place(variables: list, *, fitted: tuple = (), xi_match: set | None = None,
          ) -> VariableSet:
    """🔴🔴 V-3 — 변수들을 **자리에 배치**한다.

    `fitted` 는 **적합이 끝난 계수 이름들**이다(`("T2",)` 처럼) — 표의
    `axis_needs_fit` 칸이 참인 유형은 그 적합이 있을 때만 축으로 간다.
    `xi_match` 는 **확정 XI 와 일치한** 변수 id 들이다(감독 발언이 축2 로 가는 조건).

    🔴 돌려주는 것은 `VariableSet` 이고, 그 안에 **배치 실패·미배치**가 이름으로
       남는다(#3 조용한 0 금지 · C5·C6).
    """
    box = dict(table().get("types") or {})
    said_fail = dict(table().get("fail") or {})
    got = VariableSet()
    for one in (variables or []):
        kind = str(getattr(one, "type", "") or "")
        ctx = not bool(getattr(one, "usable_as_basis", True))
        row = dict(box.get(kind) or {})
        if not row:
            # 🔴 C6 — 표에 없는 유형: **근거 불가로 내리고** 알린다
            got.fails.append(
                f"🔴 **배치 실패** — `{one.id}` 유형 `{kind}` 가 배치표에 없다 "
                f"({said_fail.get('note') or '근거 불가로 내렸다'})")
            logger.info("[routing] 배치 실패 — %s `%s`", one.id, kind)
            got.rows.append(_row(one, places=[HYPO], ctx=True,
                                 why="🔴 배치표에 없는 유형 — 근거 불가(맥락)"))
            continue
        want = [str(x) for x in (row.get("places") or [])]
        # 🔴 조건부 축 자리를 **먼저** 걷어낸다
        if row.get("axis_needs_fit") and not _fit_ok(kind, fitted):
            want = [x for x in want if x not in AXES]
        if row.get("axis_needs_xi_match") and str(one.id) not in (xi_match
                                                                  or set()):
            want = [x for x in want if x not in AXES]
        if ctx:
            # 🔴 C5 — 근거 불가는 ①②(축·검증·상수)에 못 간다. 맥락만 남는다.
            want = [x for x in want if x == HYPO] or [HYPO]
        got.rows.append(_row(one, places=want, ctx=ctx,
                             why=str(row.get("why") or "")))
    # 🔴 C5 — 근거 가능인데 자리가 없는 변수(0 이어야 한다)
    got.unplaced = [r.id for r in got.rows if not r.context_only
                    and not r.places]
    return got


def _fit_ok(kind: str, fitted: tuple) -> bool:
    """🔴 그 유형의 축 자리를 열어 줄 **적합**이 있나.

    ⚠️ 지금 우리 계수는 전부 임시값이라 **거의 늘 거짓**이다 — 그래서 피로는 축2 로
       안 간다(지시서 *"적합된 경우"*). 🔴 적합이 들어오면 `fitted` 에 그 이름을
       넣어 길이 열린다.
    """
    want = {"fatigue": "T2", "travel_schedule": "T2"}.get(str(kind), "")
    return bool(want) and want in {str(x) for x in (fitted or ())}


def _row(one, *, places: list, ctx: bool, why: str) -> VarRow:
    return VarRow(
        id=str(getattr(one, "id", "") or ""),
        type=str(getattr(one, "type", "") or ""),
        claim=str(getattr(one, "claim", "") or ""),
        subject=str(getattr(one, "subject", "") or ""),
        favors=str(getattr(one, "favors", "") or ""),
        hardness=str(getattr(one, "hardness", "") or ""),
        weight=float(getattr(one, "weight", 0.0) or 0.0),
        goals=str(getattr(one, "goals", "") or ""),
        context_only=bool(ctx), places=list(places), why=why)
