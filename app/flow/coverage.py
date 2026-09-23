"""[HYC-6] **잴 수 없는 칸을 운영에 드러낸다.** 순수 함수 — LLM·HTTP·DB 0건.

사용자 2026-09-23: "hyc 전부 다 해라"
계획서 `hyp_conditions_0920` §4(HYC-6):
> 조건별 상태 = **성립 / 불성립 / 미상 / 미실행**. ⑥ 스냅샷과 ⑫ 서술에
> 싣는다. **⑦ 조정에는 넣지 않는다**(observe_only).
> `/health` 한 줄 + `app/export/for_fable.py` 의 `coverage` 블록.

🔴 **왜.** HYC-3 로 `미실행`(볼 방법이 없다)이 생겼지만 운영에서 볼 방법이
   없었다 — ⑥ 스냅샷과 ⑫ 글에만 있었다. 그러면 "왜 이 변수는 영원히 비어
   있나"를 사람이 DB 를 파야 안다.

   실측 (전 기간): `weather`·`travel_backtoback` 은 **확인 0 / 등장 2,129**.

🔴 **관측 장치는 판정을 건드리지 않는다**(감시 3층 규약). ⑦은 이 모듈을
   읽지 않고, 계약이 그것을 잠근다.
⚠️ 이름의 원본은 `config/rules.yaml` 의 `flow.var_names` 하나다(사본 금지).
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)

#: 🔴 상태값의 원본은 `labels` 다 — 여기에 문자열을 적지 않는다.
try:
    from app.flow.labels import CONFIRMED, REFUTED, UNKNOWN, UNRUN
except Exception:                                    # pragma: no cover
    CONFIRMED, REFUTED, UNKNOWN, UNRUN = ("confirmed", "refuted",
                                          "unknown", "미실행")

STATES = (CONFIRMED, REFUTED, UNKNOWN, UNRUN)


def _var_ko(var: str) -> str:
    """변수의 **사람 이름**. 🔴 원본은 config 다(VIS-1 과 같은 규약)."""
    try:
        from app.flow import rules as R

        return str((R.get("var_names") or {}).get(var) or var)
    except Exception:
        return var


def summarize(verdicts) -> dict:
    """⑥ 스냅샷 여러 개 → 변수별 상태 집계.

    반환 `{"games": n, "vars": {var: {상태: 수}}, "always_unrun": [var, ...]}`.

    🔴 `always_unrun` 은 **한 번도 잴 수 없었던** 칸이다 — 가끔 되는 칸을
       "영원히 안 됨"으로 적으면 거짓이라, 등장했고 전건이 미실행인 것만 센다.
    """
    by: dict = defaultdict(Counter)
    games = 0
    for v in (verdicts or []):
        per = (v or {}).get("per_var") or {}
        if not per:
            continue
        games += 1
        for var, st in per.items():
            by[var][str(st)] += 1
    always = sorted(var for var, c in by.items()
                    if c.get(UNRUN, 0) and c[UNRUN] == sum(c.values()))
    return {"games": games,
            "vars": {var: dict(c) for var, c in by.items()},
            "always_unrun": always}


def line(verdicts) -> str | None:
    """`/health` 한 줄. 🔴 **잴 수 없는 칸이 없으면 None** — 할 말이 없다.

    ⚠️ `/health` 를 길게 만들지 않는다(계획서 규율). 상세는 export 다.
    """
    got = summarize(verdicts)
    if not got["always_unrun"]:
        return None
    names = " · ".join(_var_ko(v) for v in got["always_unrun"])
    return (f"🔧 잴 방법이 없는 칸 {len(got['always_unrun'])}개 — {names} "
            f"(최근 {got['games']}경기 전건 미실행 · 수집 경로가 없습니다)")


def block(verdicts) -> dict:
    """export 의 `coverage` 블록. 🔴 **항상 전체 목록**이다(계획서 규율)."""
    got = summarize(verdicts)
    return {"games": got["games"],
            "always_unrun": [{"var": v, "name": _var_ko(v)}
                             for v in got["always_unrun"]],
            "by_var": {v: {"name": _var_ko(v), **c}
                       for v, c in got["vars"].items()}}
