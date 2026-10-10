"""🔴🔴 **s6c — 가설 검증**. 순서 재편 지시서(2026-10-10 다섯째) 단계 4.

> 4-1 가설마다 예측 신호를 시뮬레이션 출력과 대조(코드): **지지 / 반박 /
>     판단 불가**(지표 없음·표본 부족).
> 4-2 반박된 가설은 **원인을 코드가 분류**한다 — (a) 입력 누락 · (b) 기준 낡음 ·
>     (c) 가설 오류.
> 4-3 **재실행은 최대 1회**: (a) 는 그 변수의 효과가 **적합돼 있는데 빠졌을 때만**
>     넣고 다시 돈다. (b) 는 기준 항 가중을 규칙대로 다시 계산해 한 번 더 돈다.
>     **적합값이 없는 변수를 검증을 맞추려고 임의로 넣지 않는다.**
> 4-5 산출: **가설 검증표** — 가설·신호·시뮬 값·판정·반박 원인.

🔴 이 단계는 **확률을 만들지 않는다** — 읽고 견주고, (4-3 에 해당할 때만) 시뮬을
   **같은 함수로** 한 번 더 돌린다.
🔴 LLM 을 **부르지 않는다**(전부 코드다).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.schema import Facts, HypoSet, MatchRef
from app.core.state import RunState

logger = logging.getLogger(__name__)

#: 🔴 §4-2 원인 글자
MISS, STALE, WRONG = "입력 누락", "기준 낡음", "가설 오류"
#: 🔴 §4-2 (b) — **핵심 몇 명 결장**이면 기준이 낡았다고 보나(지시서가 적은 3)
ABSENT_STALE = 3
#: 🔴 §4-2 (b) 의 **못 센 칸** — 카드가 적고, **모델에 가는 글에는 안 섞는다**
GAP_COACH = "⚠️ 감독 교체 직후는 **못 센다**(취임일 자료가 없다)"
#: 🔴 §4-3 — 재실행 상한
MAX_RERUN = 1


@dataclass
class Row:
    """🔴 검증표 한 줄(§4-5)."""

    side: str = ""
    kind: str = ""          # `reasons`·`breaks`
    text: str = ""
    var_ids: list = field(default_factory=list)
    signal: str = ""
    value: float | None = None
    want: float | None = None
    verdict: str = ""
    cause: str = ""
    why: str = ""

    def as_dict(self) -> dict:
        return {"side": self.side, "kind": self.kind, "text": self.text,
                "var_ids": list(self.var_ids), "signal": self.signal,
                "value": self.value, "want": self.want,
                "verdict": self.verdict, "cause": self.cause, "why": self.why}


def run(ref: MatchRef, facts: Facts, hypo: HypoSet, sim: dict, *,
        variables: list | None = None, turnover: dict | None = None,
        state: RunState) -> dict:
    """🔴🔴 §4 — 검증표를 만든다. 돌려주는 표:

    ```
    {"rows": [검증표 줄…], "supported": [지지된 줄…],
     "counts": {"지지": n, "반박": n, "판단 불가": n},
     "stale": "사유"|"", "rerun": "사유"|"", "why": "한 줄"}
    ```

    ⚠️ **재실행 판단만** 한다 — 실제 재실행은 파이프라인이 `rerun` 을 보고 한 번
       돈다(시뮬 함수는 한 곳이다 · 사본 금지).
    """
    from app.core import signals as _sg
    league = _sg.league_of(facts)
    rows: list[Row] = []
    for one in (hypo.hypotheses or []):
        side = str(getattr(one, "team", "") or "")
        for kind in ("reasons", "breaks"):
            for line in (getattr(one, kind, None) or []):
                rows.append(_one(line, side=side, kind=kind, sim=sim,
                                 league=league))
    stale = _stale(ref, facts, turnover)
    for r in rows:
        if r.verdict == _sg.NO:
            r.cause, r.why = _cause(r, variables=variables, stale=stale,
                                    why=r.why)
    counts = {k: sum(1 for r in rows if r.verdict == k)
              for k in (_sg.OK, _sg.NO, _sg.NA)}
    rerun = _rerun_why(rows, stale=stale)
    said = (f"가설 {len(rows)}줄 — 지지 {counts[_sg.OK]} · 반박 {counts[_sg.NO]}"
            f" · 판단 불가 {counts[_sg.NA]}"
            + (f" · {stale}" if stale else ""))
    state.note(f"s6c 단계 4 — {said}"
               + (f" · 🔴 재실행 사유: {rerun}" if rerun else ""))
    logger.info("[s6c] %s · 재실행 %s", said, rerun or "없다")
    return {"rows": [r.as_dict() for r in rows],
            "supported": [r.as_dict() for r in rows if r.verdict == _sg.OK],
            "counts": counts, "stale": stale, "rerun": rerun,
            # 🔴 **못 센 칸**은 따로 든다(카드가 적는다 · 모델 글에는 안 섞인다)
            "gaps": [GAP_COACH], "why": said}


def _one(line, *, side: str, kind: str, sim: dict, league: dict) -> Row:
    """🔴 §4-1 — 한 줄을 대조한다."""
    from app.core import signals as _sg
    got = _sg.check(getattr(line, "signal", None), sim, league=league)
    sig = getattr(line, "signal", None)
    return Row(side=side, kind=kind, text=str(getattr(line, "text", "") or ""),
               var_ids=[str(x) for x in (getattr(line, "var_ids", None) or [])],
               signal=(_sg._say(sig) if sig is not None else "없다"),
               value=got.get("value"), want=got.get("want"),
               verdict=str(got.get("verdict") or ""), why=str(got.get("why")
                                                              or ""))


def _stale(ref: MatchRef, facts: Facts, turnover: dict | None) -> str:
    """🔴🔴 §4-2 (b) — **기준 낡음 의심**인가. 맞으면 사유, 아니면 빈 글자.

    > 한쪽이 `squad_turnover`·**감독 교체 직후**·**핵심 3명 이상 결장**
    """
    said: list[str] = []
    for side, one in dict(turnover or {}).items():
        if dict(one).get("on"):
            name = str(getattr(ref, f"{side}_name", "") or "")
            said.append(f"{name} 선수단 교체")
    for side in ("home", "away"):
        key = str(getattr(ref, side))
        name = str(getattr(ref, f"{side}_name", "") or "")
        rows = list((facts.missing or {}).get(key) or [])
        if len(rows) >= ABSENT_STALE:
            said.append(f"{name} 결장 {len(rows)}명")
    # ⚠️ **감독 교체 직후**를 세는 자료가 없다 — `facts.coach` 는 이름뿐이고
    #    취임일이 없다(실측 2026-10-10). 🔴 그 칸은 비워 두고 그 사실을 **따로**
    #    적는다(`GAP_COACH`).
    #    ⚠️ 실사고 2026-10-10: 그 문장을 `stale` 글귀 **안에** 붙였더니 최종 평이
    #       *"선수단 교체는 **감독 교체 직후라** 취임일 자료가 없어 못 센다"* 로
    #       두 사실을 하나로 붙여 **거짓을 만들었다**. 🔴 모델에 가는 글에 군더더기를
    #       넣지 않는다.
    if not said:
        return ""
    return "🔴 **기준 낡음 의심** — " + " · ".join(said)


def _cause(row: Row, *, variables: list | None, stale: str,
           why: str) -> tuple[str, str]:
    """🔴🔴 §4-2 — 반박된 가설의 **원인 분류**. `(원인, 사유)`.

    | 원인 | 언제 |
    |---|---|
    | (a) `입력 누락` | 근거 변수가 **적합된 효과를 갖고도** 시뮬에 안 들어갔다 |
    | (b) `기준 낡음` | 한쪽이 선수단 교체·핵심 3명 이상 결장 |
    | (c) `가설 오류` | 위 둘이 아니다 — 시뮬과 정면으로 반대다 |
    """
    gone = _missing_inputs(row, variables)
    if gone:
        return MISS, f"{why} · 🔴 (a) **입력 누락** — {gone}"
    if stale:
        return STALE, f"{why} · 🔴 (b) {stale}"
    return WRONG, f"{why} · 🔴 (c) **가설 오류** — 시뮬과 반대다"


def _missing_inputs(row: Row, variables: list | None) -> str:
    """🔴 §4-2 (a) — 그 가설의 근거 변수가 **시뮬에 안 들어갔나**.

    🔴 "들어갔다"의 뜻: 그 변수가 **무게를 갖고 근거로 쓰일 수 있다**
       (`usable_as_basis` 이고 `weight > 0`). ⚠️ 무게 0 이거나 근거 불가면 ③ 이
       그것을 **안 움직였다**는 뜻이다.
    ⚠️ 변수 목록이 없으면 빈 글자다(모르면 (a) 라고 하지 않는다 · #4).
    """
    if not variables:
        return ""
    box = {str(v.id): v for v in variables}
    out: list[str] = []
    for vid in row.var_ids:
        one = box.get(str(vid))
        if one is None:
            out.append(f"`{vid}` 없는 변수")
            continue
        if not bool(getattr(one, "usable_as_basis", False)):
            out.append(f"`{vid}` 근거 불가")
        elif float(getattr(one, "weight", 0.0) or 0.0) <= 0.0:
            out.append(f"`{vid}` 무게 0")
    return " · ".join(out)


def _rerun_why(rows: list[Row], *, stale: str) -> str:
    """🔴🔴 §4-3 — **재실행 사유**(없으면 빈 글자). ⚠️ 최대 **한 번**이다.

    🔴 (a) 는 *"그 변수의 효과가 **적합돼 있는데** 빠졌을 때만"* 이다 — 우리
       계수는 **전부 임시값**이므로(실측 2026-10-10) 그 조건이 **아직 성립하지
       않는다**. 그래서 (a) 로는 재실행하지 않고 그 사실을 적는다(#4: 적합값이
       없는 변수를 검증을 맞추려고 임의로 넣지 않는다).
    🔴 (b) 기준 낡음은 **가중을 규칙대로 다시 계산해** 한 번 더 돈다 — 그 규칙은
       `config/squad_turnover.yaml` 의 `weaken` 이고 이미 적용돼 있다. 그러면
       **다시 돌 이유가 없다**(같은 수가 나온다) — 적용 안 됐을 때만 돈다.
    """
    from app.core import signals as _sg
    miss = [r for r in rows if r.verdict == _sg.NO and r.cause == MISS]
    if miss:
        return ("🔴 (a) 입력 누락 "
                f"{len(miss)}건이지만 **재실행하지 않는다** — 그 변수의 효과가 "
                "적합돼 있지 않다(전부 임시값이다 · §4-3 금지: 적합값 없는 변수를 "
                "검증을 맞추려고 넣지 않는다)")
    return ""


def rerun_needed(got: dict) -> bool:
    """🔴 §4-3 — **실제로 다시 돌아야 하나**. 지금은 늘 거짓이다.

    🔴 위 `_rerun_why` 가 적은 대로다: (a) 는 적합값이 없어 금지, (b) 는 가중이
       이미 적용돼 있다. ⚠️ 그래서 **재실행 0회**이고 그 사실이 카드에 남는다.
       🔴 적합이 들어오면 이 함수가 참을 돌려주고 파이프라인이 **한 번** 돈다.
    """
    return bool(dict(got or {}).get("rerun_do"))
