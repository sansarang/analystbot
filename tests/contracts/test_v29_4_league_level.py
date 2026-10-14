"""🔴🔴 **리그 수준 대체 계약** — 사용자 지시 2026-10-14.

> elo가 없는 리그는 그팀이 속한 리그를 쓰되 **봇 흐름에 영향을 주어서는 안된다**

지키는 것:
  LL1 글자를 만드는 곳은 `offsets.gap_said` **하나**다(사본 금지)
  LL2 🔴🔴 **흐름에 영향이 없다** — `probs`·`dr`·`home_elo`·`away_elo` 를 안 만든다
  LL3 Elo 를 **받은** 경기에서는 그 칸이 **비어 있다**(쓸 데가 없다)
  LL4 판에 없는 리그는 ⬜ 와 **사유**가 남는다(#3 조용한 0 금지)
  LL5 그 칸이 확률 경로에서 **읽히지 않는다**
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD = "app/core/stages/s2b_base.py"


def _code(rel: str) -> str:
    """🔴 D46 — 독스트링·주석을 뺀 **코드만**."""
    said = (ROOT / rel).read_text(encoding="utf-8")
    drop: set[int] = set()
    for node in ast.walk(ast.parse(said)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = list(getattr(node, "body", []) or [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                one = body[0]
                for ln in range(one.lineno, (one.end_lineno or one.lineno) + 1):
                    drop.add(ln)
    return "\n".join(x for i, x in enumerate(said.splitlines(), 1)
                     if i not in drop and not x.strip().startswith("#"))


def _body(name: str) -> str:
    code = _code(MOD)
    i = code.index(f"def {name}(")
    j = code.find("\ndef ", i + 10)
    k = code.find("\nasync def ", i + 10)
    end = min([x for x in (j, k) if x > i] or [len(code)])
    return code[i:end]


def test_ll1_one_writer() -> None:
    """LL1 — `offsets.gap_said` 를 쓴다(같은 일을 다시 짓지 않는다)."""
    said = _body("league_level")
    assert "gap_said(" in said, (
        "LL1 🔴 `offsets.gap_said` 를 안 쓴다 — 카드 블록 3c 가 쓰는 그 글자와 "
        "둘이 되면 한쪽만 고쳐진다(사본 금지)")
    for bad in ("latest_plate(", "league_of("):
        assert bad not in said, (
            f"LL1 🔴 `{bad}` 를 직접 부른다 — 그 조회는 `gap_said` 안에 있다")


def test_ll2_no_flow_effect() -> None:
    """LL2 🔴🔴 — **흐름에 영향이 없다**. 확률·Elo·dr 을 안 만든다."""
    said = _body("league_level")
    for bad in ("probs", "home_elo", "away_elo", "\"dr\"", "'dr'",
                "base_prob", "ProbTriple"):
        assert bad not in said, (
            f"LL2 🔴🔴 `{bad}` 를 건드린다 — 사용자 지시는 *\"봇 흐름에 영향을 "
            "주어서는 안된다\"* 다")
    # 🔴 부르는 자리도 **`league_level` 칸만** 덮는지 센다
    code = _code(MOD)
    i = code.find("league_level(ref, kind=kind")
    assert i > 0, "LL2 🔴 부르는 자리를 못 찾았다"
    near = code[max(0, i - 260):i + 60]
    assert "model_copy" in near and '"league_level"' in near, (
        "LL2 🔴 `model_copy(update={\"league_level\": …})` 꼴이 아니다")
    for bad in ("\"probs\"", "\"dr\"", "\"home_elo\"", "\"away_elo\""):
        assert bad not in near, (
            f"LL2 🔴🔴 그 자리가 {bad} 도 덮는다 — 흐름을 바꾼 것이다")


def test_ll3_only_when_elo_missing() -> None:
    """LL3 — Elo 를 **받은** 경기에서는 그 칸을 안 만든다."""
    code = _code(MOD)
    i = code.find("league_level(ref, kind=kind")
    before = code[max(0, i - 320):i]
    assert "home_elo is None or away_elo is None" in before, (
        "LL3 🔴 Elo 가 있는 경기에서도 리그 수준을 적는다 — 쓸 데가 없고 "
        "카드에 군더더기가 된다")


def test_ll4_missing_league_is_named() -> None:
    """LL4 — 판에 없는 리그는 ⬜ 와 사유. `gap_said` 가 그것을 한다."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core import offsets
    got = offsets.gap_said(conf="UEFA", home="없는팀FC", away="또없는팀FC")
    assert "⬜" in got, f"LL4 🔴 모르는 팀에 ⬜ 가 없다 — {got[:120]}"
    # 🔴 대륙을 모르면 그 사실을 적는다
    said = _body("league_level")
    assert "대륙을 모른다" in said, "LL4 🔴 대륙 미상의 사유가 없다"


def test_ll5_not_read_by_probability() -> None:
    """LL5 — 확률을 만드는 모듈이 그 칸을 **안 읽는다**."""
    bad = []
    for rel in ("app/core/probmodel.py", "app/core/sim.py",
                "app/core/matchup.py", "app/core/probfloor.py",
                "app/core/survive.py", "app/core/picks.py",
                "app/core/stages/s7_judge.py",
                "app/core/legacy/old_engine.py"):
        if (ROOT / rel).is_file() and "league_level" in _code(rel):
            bad.append(rel)
    assert not bad, (
        f"LL5 🔴🔴 확률 경로가 리그 수준을 읽는다: {bad} — *\"흐름에 영향을 "
        "주어서는 안된다\"* 를 깬다")
