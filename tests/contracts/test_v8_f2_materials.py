"""🔴🔴 **F2 — 변수·깃발·전략이 상성 재료로 들어간다**(지시서 2026-10-11 §2 F2).

> 순서: ⑦ 전략 판정을 ⑧ 상성 재료보다 **먼저**.
> ⑧ 입력 시그니처: `(ref, facts, varset_axis, turnover, strategy)`.
>   · 결장·징계 변수 → 그 선수가 쥔 무기 **꺼짐**, 복귀 변수 → **켜짐**
>   · 교체 운용 선수(선발 비율 30% 미만) → **후반 무기**
>   · turnover r → 폼·골 내용·스타일 집계에서 **과거 경기 가중**
>   · 전략(수비 위주·3백 전환 등) → 스타일 6축 조정
> 규칙 T1~T13 발동은 **이 조정된 재료**로 판정한다.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _order(name: str, who: tuple[str, ...]) -> dict[str, int]:
    """🔴 그 함수 안에서 **누가 먼저 불리나** — 줄 번호로 센다."""
    src = (ROOT / "app/core/pipeline.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == name)
    got: dict[str, int] = {}
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            key = f"{getattr(n.func.value, 'id', '')}.{n.func.attr}"
            if key in who and key not in got:
                got[key] = n.lineno
    return got


def test_F2_전략_판정이_상성_재료보다_먼저다():
    """🔴 ⑦ 전략 → ⑧ 재료 순서. ⚠️ 돌연변이: 둘을 바꾸면 빨개진다.

    🔴 왜 — 전략(수비 위주·3백 전환)이 **스타일 6축을 조정**해야 규칙 T1~T13 이
       오늘의 모양으로 발동한다. 재료가 먼저 굳으면 전략은 **뒤늦은 장식**이 된다.
    """
    got = _order("analyze", ("_s2d.run", "_s2e.run"))
    assert "_s2d.run" in got and "_s2e.run" in got, got
    assert got["_s2d.run"] < got["_s2e.run"], (
        f"🔴 전략(:{got['_s2d.run']})이 재료(:{got['_s2e.run']}) 뒤에 있다")


def test_F2_재료가_변수_깃발_전략을_받는다():
    """🔴 ⑧ 입력 시그니처 — `(ref, facts, varset, turnover, strategy)`.

    ⚠️ 돌연변이: `varset` 을 안 넘기면(또는 인자를 지우면) 빨개진다.
    """
    from app.core.stages import s2e_matchup as _s2e
    got = inspect.signature(_s2e.run).parameters
    for want in ("varset", "turnover", "strategy"):
        assert want in got, f"🔴 재료가 `{want}` 를 안 받는다"
    src = (ROOT / "app/core/pipeline.py").read_text(encoding="utf-8")
    call = src.split("_s2e.run(")[1][:200]
    for want in ("varset", "turnover", "strategy"):
        assert want in call, f"🔴 파이프라인이 `{want}` 를 안 넘긴다 — {call[:120]!r}"


def test_F2_R2_결장_선수의_무기는_꺼진_채로_발동하지_않는다():
    """🔴🔴 **계약 R2** — 결장 변수가 있는데 그 선수의 무기가 **켜진 채로** 규칙이
    발동하면 실패.

    ⚠️ 돌연변이: `off_weapons` 를 규칙 발동에서 빼면 빨개진다.
    """
    from app.core import style as _style
    said = inspect.getsource(_style.fire)
    assert "off" in inspect.signature(_style.fire).parameters, (
        "🔴 규칙 발동이 **꺼진 무기**를 안 본다")
    assert "off" in said, said[:200]
    # 🔴 실물로 센다 — 꺼진 무기가 있으면 그 규칙은 **안 나온다**
    def _mk(side: str) -> _style.Style:
        return _style.Style(team=side, n=10, aerial=0.5, axis={
            "forward": 0.9, "box_entry": 2.0, "press": 0.01,
            "low_block": 0.01, "direct": 0.5, "setpiece": 0.1})
    on = _style.fire(_mk("home"), _mk("away"), off={})
    assert on, "🔴 전제가 바뀌었다 — 아무 규칙도 안 발동한다"
    kept = _style.fire(_mk("home"), _mk("away"),
                       off={"home": ["forward", "box_entry"]})
    assert len(kept) < len(on), (
        f"🔴 무기를 껐는데 발동 수가 그대로다 — {len(on)} → {len(kept)}")


def test_F2_R3_r_가중이_상성에_남는다():
    """🔴🔴 **계약 R3** — turnover 팀의 폼·골 내용 계산에서 **r 가중이 적용됐다**
    (경기별 가중 기록이 `MatchupReport` 에 남는다).

    ⚠️ 돌연변이: `MatchupReport.r` 를 지우거나 `axis1`·`axis3` 이 r 를 안 받으면
       빨개진다.
    """
    import dataclasses

    from app.core import matchup as _mu
    got = {f.name for f in dataclasses.fields(_mu.MatchupReport)}
    assert "r" in got, "🔴 상성 판정이 r 를 안 들고 있다"
    for fn in (_mu.axis1, _mu.axis3):
        assert "r" in inspect.signature(fn).parameters, f"🔴 {fn.__name__} 가 r 를 안 받는다"
    # 🔴 **재료 쪽에도** 남아야 한다 — 집계에 쓰인 가중을 보고가 적는다
    from app.core.stages import s2e_matchup as _s2e
    said = inspect.getsource(_s2e.run)
    assert "r" in said and "turnover" in said, "🔴 재료가 r 를 안 쓴다"
