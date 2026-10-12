"""🔴🔴 **3b 반증 딥서치(⑫b)** — 수정 지시서 2026-10-12.

> [3b] 위치: ⑫ 검증 다음 새 단계 ⑫b. 새 모듈 `s5b_falsify`. pipeline.py에서
> ⑫ 호출 **직후**·⑬ 앞에서 **조건 없이** 부른다(재생 모드 포함 — 재생 땐
> 저장된 결과 사용). … 구조 사실로 확인 가능한 것(K2·K3·K4)은 **질의 없이**
> 기존 사실로 판정. … 로그: 자기 줄
> "[s5b] 반증 — 조건 n · 질의 m · 무너짐 a · 없음 b · 미확인 c"
> (점검표 증거, 다른 단계와 겹치면 계약 실패).

🔴 B1 "간다"는 조건 목록 전부에 확인 결과가 있을 때만(→ `test_v11_3`).
🔴 B3 반증 단계 전후 S3 해시 같다(재실행 경로 제외) — 이 단계는 **확률을
   만지지 않는다**: 모듈이 확률 모듈을 아예 import 하지 않는다.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD = "app/core/stages/s5b_falsify.py"


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_module_exists_with_run() -> None:
    import importlib
    mod = importlib.import_module("app.core.stages.s5b_falsify")
    assert hasattr(mod, "run")


def test_wired_after_check_before_scenarios() -> None:
    """🔴 ⑫ 직후 · ⑬(시나리오) 앞.

    ⚠️ D46 — **주석을 세지 않는다**: `s5b_falsify` 라는 글자는 ⑩b 주석에도
       있다(거기서 *"갈아 주는 자리는 ⑫b 하나다"* 라고 적는다). 🔴 그래서
       **호출 글자**(`s5b_falsify.run(`)의 자리를 본다.
    """
    said = _src("app/core/pipeline.py")
    i_check = said.index("_s6c.run(")
    i_falsify = said.index("s5b_falsify.run(")
    i_scen = said.index("s6_hypo.scenarios(")
    assert i_check < i_falsify < i_scen, (i_check, i_falsify, i_scen)


def test_called_unconditionally() -> None:
    """🔴 *"조건 없이 부른다"* — 호출이 `if` 안에 들어 있으면 실패."""
    tree = ast.parse(_src("app/core/pipeline.py"))
    hit = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.If, ast.While)):
            continue
        if "s5b_falsify.run(" in ast.unparse(node):
            hit.append(ast.unparse(node)[:120])
    assert not hit, hit


def test_structure_kinds_never_search() -> None:
    """🔴 K2·K3·K4 는 **질의 없이** 기존 사실로 판정한다."""
    from app.core.stages import s5b_falsify as fx
    assert set(fx.NO_QUERY_KINDS) == {"K2", "K3", "K4", "K5"}


def test_log_line_is_its_own() -> None:
    """🔴 점검표 증거 — 그 글자가 **이 모듈에만** 있다."""
    said = _src(MOD)
    assert "[s5b] 반증 —" in said
    others = [p for p in (ROOT / "app").rglob("*.py")
              if p != (ROOT / MOD) and "[s5b] 반증" in p.read_text(
                  encoding="utf-8")]
    assert not others, [str(p) for p in others]


def test_no_probability_import() -> None:
    """🔴 B3 — 이 단계는 확률을 만들지도 바꾸지도 않는다."""
    said = _src(MOD)
    for bad in ("probmodel", "import simulate", "ProbOut"):
        assert bad not in said, bad


def test_no_new_searcher() -> None:
    """🔴 *"새 검색기 만들지 않는다"* — ③ 딥서치의 문을 그대로 쓴다."""
    said = _src(MOD)
    assert "s3_docs" in said, "🔴 ③ 의 검색·신원·날짜 문을 안 쓴다"
    for bad in ("httpx", "SearXNG", "search.query("):
        assert bad not in said, bad


def test_states_are_the_three_words() -> None:
    from app.core.stages import s5b_falsify as fx
    assert fx.BROKEN == "확인-무너짐"
    assert fx.INTACT == "확인-무너짐 없음"
    assert fx.UNKNOWN == "미확인"


def test_replay_uses_recorded_results() -> None:
    """⚠️ 재생에서는 **새로 검색하지 않는다**(카세트가 모른다)."""
    said = _src(MOD)
    assert "cassette" in said and "REPLAY" in said


def test_structure_verdicts_without_net() -> None:
    """🔴 K2·K4 는 통신 없이 판정된다 — 그 판정이 코드에 있다."""
    from app.core.schema import BreakCondition
    from app.core.stages import s5b_falsify as fx
    rows = [BreakCondition(id="BRK:K4:1", kind="K4", how="구조 사실",
                           said="라인업 미확정"),
            BreakCondition(id="BRK:K2:2", kind="K2", how="구조 사실",
                           said="꺼진 무기 ['forward']")]
    got = fx.by_structure(rows, xi_state="predicted")
    by = {c.id: c for c in got}
    # 🔴 라인업이 예상이면 K4 는 **무너짐**이다(판정이 흔들린다)
    assert by["BRK:K4:1"].state == fx.BROKEN
    assert by["BRK:K4:1"].strength in ("hard", "soft")
    # 🔴 꺼진 무기가 적혀 있으면 K2 도 무너짐이다
    assert by["BRK:K2:2"].state == fx.BROKEN


def test_structure_intact_when_confirmed() -> None:
    from app.core.schema import BreakCondition
    from app.core.stages import s5b_falsify as fx
    rows = [BreakCondition(id="BRK:K4:1", kind="K4", how="구조 사실",
                           said="라인업 미확정")]
    got = fx.by_structure(rows, xi_state="confirmed")
    assert got[0].state == fx.INTACT
