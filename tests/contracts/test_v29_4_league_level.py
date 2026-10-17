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
    """🔴🔴 **Elo 를 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*.

    ⚠️ 이 시험(test_ll1_one_writer)이 지키던 것은 **기준 확률(Elo → 승·무·패)** 경로다.
    🔴 **확률은 이미 그 수를 안 보고 있었다** — 승무패는 `flat_prob`
       (1/3 균등 + 변수)이 내고 `probmodel.run` 은 `floor` 를 안 읽는다.
       쓰이던 곳은 카드의 **기준 열**과 **방향 판정**뿐이었고 둘 다 표시인데,
       `eloratings.net/World.tsv` 를 **매 실행** 받고 있었다.
    🔴 그래서 지웠고, 이 시험은 *"되살아나지 않는다"* 를 지킨다.
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    #  ① Elo 모듈 넷이 **없다**
    for rel in ("app/collect/elo.py", "app/collect/leagueelo.py",
                "app/core/domesticelo.py"):
        assert not (root / rel).exists(), f"🔴 `{rel}`(Elo)가 되살아났다"
    #  ② 기준 확률 함수가 **없다**
    from app.core import base as _b
    for one in ("we", "triple_of", "triple_from", "base_prob"):
        assert not hasattr(_b, one), f"🔴 `core.base.{one}`(Elo)가 되살아났다"
    from app.core.stages import s2b_base as _s2b
    for one in ("_base", "continental_elo", "league_level"):
        assert not hasattr(_s2b, one), f"🔴 `s2b_base.{one}`(Elo)가 되살아났다"
    #  ③ ② 는 **남아 있다** — 오늘 XI 가 평소보다 약/강한가는 Elo 를 안 쓴다
    for one in ("strength_of", "fill_values", "adjust"):
        assert hasattr(_b, one), f"🔴 `core.base.{one}`(선수 전력)이 같이 지워졌다"
    #  ④ 기준은 **늘 비어 있고 사유가 붙는다**(#3 조용한 0 금지)
    said = (root / "app/core/stages/s2b_base.py").read_text(encoding="utf-8")
    assert "BaseProb(probs=None" in said, "🔴 기준을 빈 값으로 안 낸다"
    assert "기준(Elo)은 지웠다" in said, "🔴 그 사실을 사유에 안 적는다"


def test_ll2_no_flow_effect() -> None:
    """🔴🔴 **Elo 를 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*.

    ⚠️ 이 시험(test_ll2_no_flow_effect)이 지키던 것은 **기준 확률(Elo → 승·무·패)** 경로다.
    🔴 **확률은 이미 그 수를 안 보고 있었다** — 승무패는 `flat_prob`
       (1/3 균등 + 변수)이 내고 `probmodel.run` 은 `floor` 를 안 읽는다.
       쓰이던 곳은 카드의 **기준 열**과 **방향 판정**뿐이었고 둘 다 표시인데,
       `eloratings.net/World.tsv` 를 **매 실행** 받고 있었다.
    🔴 그래서 지웠고, 이 시험은 *"되살아나지 않는다"* 를 지킨다.
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    #  ① Elo 모듈 넷이 **없다**
    for rel in ("app/collect/elo.py", "app/collect/leagueelo.py",
                "app/core/domesticelo.py"):
        assert not (root / rel).exists(), f"🔴 `{rel}`(Elo)가 되살아났다"
    #  ② 기준 확률 함수가 **없다**
    from app.core import base as _b
    for one in ("we", "triple_of", "triple_from", "base_prob"):
        assert not hasattr(_b, one), f"🔴 `core.base.{one}`(Elo)가 되살아났다"
    from app.core.stages import s2b_base as _s2b
    for one in ("_base", "continental_elo", "league_level"):
        assert not hasattr(_s2b, one), f"🔴 `s2b_base.{one}`(Elo)가 되살아났다"
    #  ③ ② 는 **남아 있다** — 오늘 XI 가 평소보다 약/강한가는 Elo 를 안 쓴다
    for one in ("strength_of", "fill_values", "adjust"):
        assert hasattr(_b, one), f"🔴 `core.base.{one}`(선수 전력)이 같이 지워졌다"
    #  ④ 기준은 **늘 비어 있고 사유가 붙는다**(#3 조용한 0 금지)
    said = (root / "app/core/stages/s2b_base.py").read_text(encoding="utf-8")
    assert "BaseProb(probs=None" in said, "🔴 기준을 빈 값으로 안 낸다"
    assert "기준(Elo)은 지웠다" in said, "🔴 그 사실을 사유에 안 적는다"


def test_ll3_only_when_elo_missing() -> None:
    """🔴🔴 **Elo 를 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*.

    ⚠️ 이 시험(test_ll3_only_when_elo_missing)이 지키던 것은 **기준 확률(Elo → 승·무·패)** 경로다.
    🔴 **확률은 이미 그 수를 안 보고 있었다** — 승무패는 `flat_prob`
       (1/3 균등 + 변수)이 내고 `probmodel.run` 은 `floor` 를 안 읽는다.
       쓰이던 곳은 카드의 **기준 열**과 **방향 판정**뿐이었고 둘 다 표시인데,
       `eloratings.net/World.tsv` 를 **매 실행** 받고 있었다.
    🔴 그래서 지웠고, 이 시험은 *"되살아나지 않는다"* 를 지킨다.
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    #  ① Elo 모듈 넷이 **없다**
    for rel in ("app/collect/elo.py", "app/collect/leagueelo.py",
                "app/core/domesticelo.py"):
        assert not (root / rel).exists(), f"🔴 `{rel}`(Elo)가 되살아났다"
    #  ② 기준 확률 함수가 **없다**
    from app.core import base as _b
    for one in ("we", "triple_of", "triple_from", "base_prob"):
        assert not hasattr(_b, one), f"🔴 `core.base.{one}`(Elo)가 되살아났다"
    from app.core.stages import s2b_base as _s2b
    for one in ("_base", "continental_elo", "league_level"):
        assert not hasattr(_s2b, one), f"🔴 `s2b_base.{one}`(Elo)가 되살아났다"
    #  ③ ② 는 **남아 있다** — 오늘 XI 가 평소보다 약/강한가는 Elo 를 안 쓴다
    for one in ("strength_of", "fill_values", "adjust"):
        assert hasattr(_b, one), f"🔴 `core.base.{one}`(선수 전력)이 같이 지워졌다"
    #  ④ 기준은 **늘 비어 있고 사유가 붙는다**(#3 조용한 0 금지)
    said = (root / "app/core/stages/s2b_base.py").read_text(encoding="utf-8")
    assert "BaseProb(probs=None" in said, "🔴 기준을 빈 값으로 안 낸다"
    assert "기준(Elo)은 지웠다" in said, "🔴 그 사실을 사유에 안 적는다"


def test_ll4_missing_league_is_named() -> None:
    """🔴🔴 **Elo 를 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*.

    ⚠️ 이 시험(test_ll4_missing_league_is_named)이 지키던 것은 **기준 확률(Elo → 승·무·패)** 경로다.
    🔴 **확률은 이미 그 수를 안 보고 있었다** — 승무패는 `flat_prob`
       (1/3 균등 + 변수)이 내고 `probmodel.run` 은 `floor` 를 안 읽는다.
       쓰이던 곳은 카드의 **기준 열**과 **방향 판정**뿐이었고 둘 다 표시인데,
       `eloratings.net/World.tsv` 를 **매 실행** 받고 있었다.
    🔴 그래서 지웠고, 이 시험은 *"되살아나지 않는다"* 를 지킨다.
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    #  ① Elo 모듈 넷이 **없다**
    for rel in ("app/collect/elo.py", "app/collect/leagueelo.py",
                "app/core/domesticelo.py"):
        assert not (root / rel).exists(), f"🔴 `{rel}`(Elo)가 되살아났다"
    #  ② 기준 확률 함수가 **없다**
    from app.core import base as _b
    for one in ("we", "triple_of", "triple_from", "base_prob"):
        assert not hasattr(_b, one), f"🔴 `core.base.{one}`(Elo)가 되살아났다"
    from app.core.stages import s2b_base as _s2b
    for one in ("_base", "continental_elo", "league_level"):
        assert not hasattr(_s2b, one), f"🔴 `s2b_base.{one}`(Elo)가 되살아났다"
    #  ③ ② 는 **남아 있다** — 오늘 XI 가 평소보다 약/강한가는 Elo 를 안 쓴다
    for one in ("strength_of", "fill_values", "adjust"):
        assert hasattr(_b, one), f"🔴 `core.base.{one}`(선수 전력)이 같이 지워졌다"
    #  ④ 기준은 **늘 비어 있고 사유가 붙는다**(#3 조용한 0 금지)
    said = (root / "app/core/stages/s2b_base.py").read_text(encoding="utf-8")
    assert "BaseProb(probs=None" in said, "🔴 기준을 빈 값으로 안 낸다"
    assert "기준(Elo)은 지웠다" in said, "🔴 그 사실을 사유에 안 적는다"


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
