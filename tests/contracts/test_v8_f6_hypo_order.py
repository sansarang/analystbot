"""🔴🔴 **F6 — 가설 순서**(지시서 2026-10-11 §2 F6).

> 가설 세우기를 ⑨ 상성 판정 **직후**·⑪ 확률 **앞**으로 옮긴다.
> 입력: `MatchupReport` + `VariableSet`(hypo 자리) — **시뮬 출력 없음**.
> **R8**: 가설 세우기 호출이 확률 계산보다 **먼저**(호출 순서 테스트). C3 유지.

🔴 실측 2026-10-11(옮기기 전): 상성(260) → **확률(263)** → 가설(316) → 검증(319).
   가설이 확률 **뒤**에 있었다 — C3(가설이 시뮬 숫자를 안 본다)는 지켜졌지만
   *"상성 결론에서 가설이 뻗어 나간다"* 는 순서가 아니었다.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _lines(name: str) -> dict[str, int]:
    src = (ROOT / "app/core/pipeline.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == name)
    got: dict[str, int] = {}
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            key = f"{getattr(n.func.value, 'id', '')}.{n.func.attr}"
            got.setdefault(key, n.lineno)
    return got


def test_F6_R8_가설이_확률보다_먼저다():
    """🔴🔴 **계약 R8** — ⑩ 가설 → ⑪ 확률. ⚠️ 돌연변이: 둘을 바꾸면 빨개진다."""
    got = _lines("analyze")
    for want in ("_mu.report", "s6_hypo.claims", "_pm.run"):
        assert want in got, f"🔴 `{want}` 를 안 부른다 — {sorted(got)}"
    assert got["_mu.report"] < got["s6_hypo.claims"], (
        f"🔴 가설(:{got['s6_hypo.claims']})이 상성(:{got['_mu.report']}) 앞이다")
    assert got["s6_hypo.claims"] < got["_pm.run"], (
        f"🔴 가설(:{got['s6_hypo.claims']})이 확률(:{got['_pm.run']}) **뒤**다")


def test_F6_C3_가설은_시뮬_숫자를_안_본다():
    """🔴 C3 유지 — `claims()` 는 확률·시뮬을 **인자로도 본문으로도** 안 받는다."""
    from app.core.stages import s6_hypo as _s6
    got = set(inspect.signature(_s6.claims).parameters)
    for ban in ("sim", "prob", "ours", "dist", "scores"):
        assert ban not in got, f"🔴 가설이 `{ban}` 를 받는다(C3)"
    said = inspect.getsource(_s6.claims)
    code = "\n".join(x for x in said.splitlines()
                     if not x.strip().startswith("#"))
    for ban in ("ProbOut", "sim_input", "sim_extras", ".scores"):
        assert ban not in code, f"🔴 가설 본문이 `{ban}` 를 본다(C3)"


def test_F6_가설_입력이_상성과_변수다():
    """🔴 입력: `MatchupReport` + `VariableSet`(hypo 자리)."""
    from app.core.stages import s6_hypo as _s6
    got = set(inspect.signature(_s6.claims).parameters)
    assert {"mr", "varset"} <= got, sorted(got)


def test_F6_상성_우위로_가설_수를_정한다():
    """🔴 상성 우위 팀 기준 — 주 가설 2~3 · 반대 가설 2~3. 우위 없음이면 양 팀 각 2.

    🔴 그 수를 **어디서 정하는지**가 코드에 있어야 한다(지어내지 않는다).
    """
    from app.core.stages import s6_hypo as _s6
    said = inspect.getsource(_s6)
    assert "우위" in said and ("edge" in said or "verdict" in said), (
        "🔴 상성 우위를 안 본다")
