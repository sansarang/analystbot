"""🔴🔴 **F7 — 글 단계 통합: 상성 결론에서 한 편**(지시서 2026-10-11 §2 F7).

> 논평(s9_audit 작성)·이유 문단(s8b)·전술 예측(s2f)·최종 평(s9_say)
> → **최종 평 한 번**(작성 1회 + 검열 1회).
> 출력 칸: 헤드라인 한 줄 / 이유 문단 / 전술 예측(팀별 예상 운영·흐름·승부처) /
> 핵심 3줄 / 뒤집히는 조건.
> 첫 줄은 상성 판정(우위 팀·강도) + 검증 요약. 근거 id ⊂ 지지된 가설·
> MatchupReport·VariableSet. 결론 방향 = 확률 방향.
> **R9**: 카드 안 LLM 글 생성 호출이 경기당 **작성 1·검열 1**(재작성 시 +1)을 안 넘는다.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _calls(name: str) -> set[str]:
    src = (ROOT / "app/core/pipeline.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == name)
    got = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Attribute):
                got.add(f"{getattr(n.func.value, 'id', '')}.{n.func.attr}")
            elif isinstance(n.func, ast.Name):
                got.add(n.func.id)
    return got


def test_F7_R9_글을_쓰는_단계가_하나다():
    """🔴🔴 **계약 R9** — 글 생성은 **최종 평 하나**다.

    ⚠️ 돌연변이: 이유 문단·전술 예측·논평을 따로 부르면 빨개진다(경기당 호출이
       그만큼 늘고, 넷이 서로 다른 말을 한다 — 실측 2026-10-11 카드가 그랬다).
    """
    said = _calls("analyze")
    for ban in ("with_reason", "with_tactic", "s9_audit.run",
                "s8_comment.run", "s8b_reason.run", "_s2f.run"):
        assert ban not in said, f"🔴 글 단계가 아직 따로 돈다 — `{ban}`"
    assert "with_say" in said, "🔴 최종 평을 안 부른다"


def test_F7_최종_평이_다섯_칸을_든다():
    """🔴 출력 칸 — 헤드라인 / 이유 문단 / 전술 예측(팀별 운영·흐름·승부처) /
    핵심 3줄 / 뒤집히는 조건."""
    from app.core.schema import SayOut
    got = set(SayOut.model_fields)
    for want in ("one_line", "reason", "ops_home", "ops_away", "flow_first",
                 "flow_second", "decisive_moment", "key_points",
                 "flip_condition"):
        assert want in got, f"🔴 `{want}` 칸이 없다 — {sorted(got)}"


def test_F7_카드가_그_칸들을_보인다():
    """🔴 카드가 다섯 칸을 **그대로** 보인다(합쳤다고 블록이 사라지면 안 된다)."""
    from app.core import render as _r
    said = inspect.getsource(_r)
    for want in ("이유", "전술", "승부처", "뒤집히는 조건"):
        assert want in said, f"🔴 카드가 `{want}` 를 안 보인다"


def test_F7_첫_줄이_상성_판정과_검증_요약이다():
    """🔴 첫 줄 = 상성 판정(우위 팀·강도) + 검증 요약."""
    from app.core import saybundle as _sb
    said = inspect.getsource(_sb)
    assert "상성" in said and ("검증" in said or "verif" in said.lower())


def test_F7_옛_글_단계가_배선에서_빠졌다():
    """🔴 #2 — 안 이은 코드는 없는 코드보다 나쁘다. 지웠으면 **모듈도** 없다."""
    import importlib
    for name in ("s8b_reason", "s2f_tactic"):
        try:
            importlib.import_module(f"app.core.stages.{name}")
        except ModuleNotFoundError:
            continue
        # 🔴 남아 있다면 **부르는 곳**이 있어야 한다(없으면 고아다)
        src = (ROOT / "app/core/pipeline.py").read_text(encoding="utf-8")
        assert name in src, f"🔴 `{name}` 이 고아다 — 지우거나 이어라(#2)"
