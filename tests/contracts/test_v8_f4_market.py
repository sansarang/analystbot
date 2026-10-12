"""🔴🔴 **F4 — 시장·옛 세 열 규칙 제거**(지시서 2026-10-11 §2 F4).

> `compare.grade_step` 에서 시장(V6) 입력 삭제. 시장은 **카드 표시만**(C12).
> `s7_judge` 의 `_lower`(세 열 규칙) 삭제. 등급 조정은 ⑫ 검증 규칙
> (5-3: 상성 사각 hard 반대·가설 지지 0)만.
> **R6**: 시장 배당을 바꿔도 **등급·확률이 같다**.
"""
from __future__ import annotations

import inspect


def test_F4_세_열_규칙이_등급을_안_내린다():
    """🔴 `_lower`(세 열 규칙) 삭제 — 등급 조정은 ⑫ 검증 하나다.

    ⚠️ 돌연변이: 파이프라인이 다시 `_lower` 를 부르면 빨개진다.
    """
    from app.core import pipeline as _pl
    said = inspect.getsource(_pl)
    code = "\n".join(x for x in said.splitlines()
                     if not x.strip().startswith("#"))
    assert "_lower(" not in code, "🔴 세 열 규칙이 아직 등급을 내린다"
    assert not hasattr(_pl, "_lower"), "🔴 `_lower` 가 남아 있다"


def test_F4_세_열_등급_규칙이_아예_없다():
    """🔴 `compare.grade_step`(세 열 규칙) **삭제** — 표의 절반이 시장이었다.

    ⚠️ 돌연변이: 그 함수를 되살리면 빨개진다.
    🔴 세 열 **비교**(`verdict_of`)는 남는다 — 카드 표시용이다(C12).
    """
    from app.core import compare as _cmp
    assert not hasattr(_cmp, "grade_step"), (
        "🔴 세 열 등급 규칙이 돌아왔다 — 시장이 등급에 닿는 길이다")
    assert hasattr(_cmp, "verdict_of"), "🔴 표시용 비교까지 지웠다"


def test_F4_R6_배당을_바꿔도_등급과_확률이_같다():
    """🔴🔴 **계약 R6** — 시장 배당을 바꿔도 등급·확률이 **같다**.

    🔴 실물로 센다 — 등급 경로(`_grade_by_check`)에 **시장 열만** 다르게 넣고
       같은 판정이 나오는지 본다. ⚠️ 돌연변이: 그 함수가 `layers["compare"]`·
       `layers["market"]` 를 보면 두 수가 갈린다.
    """
    from app.core import pipeline as _pl
    from app.core.schema import BoardLine, Judgement, MarketEval
    from app.core.state import RunState

    def _run(layers: dict) -> str:
        evals = [MarketEval(line=BoardLine(market="win", side="home"),
                            marks={}, survival=0.9, cap=1.0, grade="낸다")]
        said = Judgement(evals=evals, direction="d", conclusion="c")
        return _pl._grade_by_check(said, layers, state=RunState()).evals[0].grade

    base = _run({"check": {"grade": {}}})
    for mk in ("세 열 일치", "시장이 다르다", "시장만 튄다", "우리만 반대"):
        assert _run({"check": {"grade": {}}, "compare": mk}) == base, (
            f"🔴 시장 판정 `{mk}` 가 등급을 움직였다")
    # 🔴 등급을 움직이는 것은 **검증 하나**다
    assert _run({"check": {"grade": {"steps": 1, "why": ["x"]}}}) != base


# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_F4_등급_조정은_검증_하나다`
