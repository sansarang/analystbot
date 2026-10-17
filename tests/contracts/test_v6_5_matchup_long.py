"""🔴🔴 **긴 카드의 상성 네 덩이** — 사용자 지시 2026-10-10(셋째) §5.

> 긴 카드: **골 목록 표(분·유형·상태·xG), 시간대 분포, 리드 유지력·추격력,
> 발동 규칙과 적합 효과.**

🔴 이 계약이 막는 것: 그 넷 중 하나라도 **조용히 빠지는 것**(#3). 긴 카드는
   1겹에서 잘린 수를 드러내는 자리이고, 그 넷이 상성 판정의 **재료 전부**다.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: 🔴 두 경기의 **골 목록** — 분·유형·상태·xG 가 다 다르게 들어 있다
ROWS_HOME = [
    {"home_name": "A", "away_name": "B", "mine_home": True,
     "goals": [
         {"minute": 12, "home": True, "before": (0, 0), "after": (1, 0),
          "situation": "FromCorner", "xg": 0.09},
         {"minute": 77, "home": False, "before": (1, 0), "after": (1, 1),
          "situation": "RegularPlay", "xg": 0.31},
         {"minute": 88, "home": False, "before": (1, 1), "after": (1, 2),
          "desc": "Penalty", "xg": 0.76}]},
    {"home_name": "C", "away_name": "A", "mine_home": False,
     "goals": [
         {"minute": 30, "home": False, "before": (0, 0), "after": (0, 1),
          "situation": "FastBreak", "xg": 0.22},
         {"minute": 45, "home": True, "before": (0, 1), "after": (1, 1),
          "situation": "RegularPlay"}]},
]
ROWS_AWAY = [
    {"home_name": "B", "away_name": "D", "mine_home": True,
     "goals": [
         {"minute": 20, "home": False, "before": (0, 0), "after": (0, 1),
          "situation": "FromCorner", "xg": 0.14},
         {"minute": 65, "home": True, "before": (0, 1), "after": (1, 1),
          "situation": "SetPiece"},
         {"minute": 80, "home": True, "before": (1, 1), "after": (2, 1),
          "situation": "RegularPlay", "xg": 0.44},
         # 🔴 **앞선 상태**에서 넣은 골 — 상태 칸 세 값이 다 나와야 표다
         {"minute": 85, "home": True, "before": (2, 1), "after": (3, 1),
          "situation": "FastBreak", "xg": 0.51}]},
]


def _matchup():
    """🔴 `s2e` 가 담는 그 모양을 **그 함수들로** 만든다(손으로 짓지 않는다)."""
    from app.core import goals as _g
    prof = {"home": _g.profile_of("A", ROWS_HOME),
            "away": _g.profile_of("B", ROWS_AWAY)}
    return {"profile": prof,
            "table": {"home": _g.table_of(ROWS_HOME),
                      "away": _g.table_of(ROWS_AWAY)},
            "fired": _g.fire(prof["home"], prof["away"], rest={}),
            "fired2": [], "why": "시험"}


def _card():
    from datetime import datetime, timedelta, timezone

    from app.core.schema import Card, Facts, MatchRef
    ref = MatchRef(id="x:1", sport="soccer", competition="K-League 1",
                   competition_short="K리그1", home="team:000001", away="team:000002",
                   home_name="A", away_name="B",
                   kickoff_utc=datetime.now(timezone.utc) + timedelta(hours=2))
    # 🔴 `Card` 는 얼었다 — `matchup` 은 **낳을 때** 넣는다(`pipeline` 과 같다)
    return Card(match=ref, facts=Facts(), matchup=_matchup())


def test_v6_긴카드가_골목록_표를_분유형상태xG_로_낸다() -> None:
    """🔴🔴 **지운 경로를 계약하던 시험이다** — 사용자 지시 2026-10-17.

    > 상성이 왜 들어가 있냐?? · **상성 삭제해라** · **시뮬도 삭제해라**

    ⚠️ 이 시험이 지키던 것(test_v6_긴카드가_골목록_표를_분유형상태xG_로_낸다)은 **상성 축 · λ(기대 득점) · 몬테카를로
       시뮬** 경로다. 그 경로의 결과가 **전부 버려지고 있었다** —
       `probmodel.run` 마지막 세 줄이 승무패를 `flat_prob`(1/3 균등 + 변수)로
       덮고 `lam`·`over`·`scores` 를 비웠기 때문이다.
    🔴 그래서 **지웠고**, 이 시험은 *"되살아나지 않는다"* 를 지키는 쪽으로
       바꾼다(지우면 되살아나도 아무도 안 본다).
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    def _code(rel: str) -> str:
        """🔴 D46 — 독스트링·주석을 뺀 **코드만** 본다."""
        t = _ast.parse((root / rel).read_text(encoding="utf-8"))
        for n in _ast.walk(t):
            if isinstance(n, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef,
                              _ast.ClassDef)) and _ast.get_docstring(n):
                n.body = n.body[1:]
        return _ast.unparse(t)

    #  ① 상성 단계가 **안 돈다**
    assert "_s2e.run(" not in _code("app/core/pipeline.py"), (
        "🔴 상성 단계가 되살아났다")
    from app.core.stages import s2e_matchup as _s2e
    assert not hasattr(_s2e, "run"), "🔴 `s2e_matchup.run`(상성)이 되살아났다"
    #  ② 확률 경로가 **시뮬을 안 부른다**
    said = _code("app/core/probmodel.py")
    assert "_sim.run(" not in said, "🔴 확률 경로가 몬테카를로를 다시 부른다"
    assert "flat_prob(varset" in said, "🔴 승무패가 `flat_prob` 에서 안 나온다"
    #  ③ λ 재료 함수들이 **없다**
    from app.core import probmodel as _pm
    for one in ("league_mean", "away_mul", "_share", "league_base"):
        assert not hasattr(_pm, one), f"🔴 `probmodel.{one}`(λ 재료)가 되살아났다"


def test_v6_긴카드가_시간대_리드유지력_발동규칙을_낸다() -> None:
    """🔴🔴 **지운 경로를 계약하던 시험이다** — 사용자 지시 2026-10-17.

    > 상성이 왜 들어가 있냐?? · **상성 삭제해라** · **시뮬도 삭제해라**

    ⚠️ 이 시험이 지키던 것(test_v6_긴카드가_시간대_리드유지력_발동규칙을_낸다)은 **상성 축 · λ(기대 득점) · 몬테카를로
       시뮬** 경로다. 그 경로의 결과가 **전부 버려지고 있었다** —
       `probmodel.run` 마지막 세 줄이 승무패를 `flat_prob`(1/3 균등 + 변수)로
       덮고 `lam`·`over`·`scores` 를 비웠기 때문이다.
    🔴 그래서 **지웠고**, 이 시험은 *"되살아나지 않는다"* 를 지키는 쪽으로
       바꾼다(지우면 되살아나도 아무도 안 본다).
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    def _code(rel: str) -> str:
        """🔴 D46 — 독스트링·주석을 뺀 **코드만** 본다."""
        t = _ast.parse((root / rel).read_text(encoding="utf-8"))
        for n in _ast.walk(t):
            if isinstance(n, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef,
                              _ast.ClassDef)) and _ast.get_docstring(n):
                n.body = n.body[1:]
        return _ast.unparse(t)

    #  ① 상성 단계가 **안 돈다**
    assert "_s2e.run(" not in _code("app/core/pipeline.py"), (
        "🔴 상성 단계가 되살아났다")
    from app.core.stages import s2e_matchup as _s2e
    assert not hasattr(_s2e, "run"), "🔴 `s2e_matchup.run`(상성)이 되살아났다"
    #  ② 확률 경로가 **시뮬을 안 부른다**
    said = _code("app/core/probmodel.py")
    assert "_sim.run(" not in said, "🔴 확률 경로가 몬테카를로를 다시 부른다"
    assert "flat_prob(varset" in said, "🔴 승무패가 `flat_prob` 에서 안 나온다"
    #  ③ λ 재료 함수들이 **없다**
    from app.core import probmodel as _pm
    for one in ("league_mean", "away_mul", "_share", "league_base"):
        assert not hasattr(_pm, one), f"🔴 `probmodel.{one}`(λ 재료)가 되살아났다"


def test_v6_축마다_0건을_따로_적는다() -> None:
    """🔴🔴 **지운 경로를 계약하던 시험이다** — 사용자 지시 2026-10-17.

    > 상성이 왜 들어가 있냐?? · **상성 삭제해라** · **시뮬도 삭제해라**

    ⚠️ 이 시험이 지키던 것(test_v6_축마다_0건을_따로_적는다)은 **상성 축 · λ(기대 득점) · 몬테카를로
       시뮬** 경로다. 그 경로의 결과가 **전부 버려지고 있었다** —
       `probmodel.run` 마지막 세 줄이 승무패를 `flat_prob`(1/3 균등 + 변수)로
       덮고 `lam`·`over`·`scores` 를 비웠기 때문이다.
    🔴 그래서 **지웠고**, 이 시험은 *"되살아나지 않는다"* 를 지키는 쪽으로
       바꾼다(지우면 되살아나도 아무도 안 본다).
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    def _code(rel: str) -> str:
        """🔴 D46 — 독스트링·주석을 뺀 **코드만** 본다."""
        t = _ast.parse((root / rel).read_text(encoding="utf-8"))
        for n in _ast.walk(t):
            if isinstance(n, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef,
                              _ast.ClassDef)) and _ast.get_docstring(n):
                n.body = n.body[1:]
        return _ast.unparse(t)

    #  ① 상성 단계가 **안 돈다**
    assert "_s2e.run(" not in _code("app/core/pipeline.py"), (
        "🔴 상성 단계가 되살아났다")
    from app.core.stages import s2e_matchup as _s2e
    assert not hasattr(_s2e, "run"), "🔴 `s2e_matchup.run`(상성)이 되살아났다"
    #  ② 확률 경로가 **시뮬을 안 부른다**
    said = _code("app/core/probmodel.py")
    assert "_sim.run(" not in said, "🔴 확률 경로가 몬테카를로를 다시 부른다"
    assert "flat_prob(varset" in said, "🔴 승무패가 `flat_prob` 에서 안 나온다"
    #  ③ λ 재료 함수들이 **없다**
    from app.core import probmodel as _pm
    for one in ("league_mean", "away_mul", "_share", "league_base"):
        assert not hasattr(_pm, one), f"🔴 `probmodel.{one}`(λ 재료)가 되살아났다"


def test_v6_상성이_못돌면_사유를_적는다() -> None:
    """🔴🔴 **지운 경로를 계약하던 시험이다** — 사용자 지시 2026-10-17.

    > 상성이 왜 들어가 있냐?? · **상성 삭제해라** · **시뮬도 삭제해라**

    ⚠️ 이 시험이 지키던 것(test_v6_상성이_못돌면_사유를_적는다)은 **상성 축 · λ(기대 득점) · 몬테카를로
       시뮬** 경로다. 그 경로의 결과가 **전부 버려지고 있었다** —
       `probmodel.run` 마지막 세 줄이 승무패를 `flat_prob`(1/3 균등 + 변수)로
       덮고 `lam`·`over`·`scores` 를 비웠기 때문이다.
    🔴 그래서 **지웠고**, 이 시험은 *"되살아나지 않는다"* 를 지키는 쪽으로
       바꾼다(지우면 되살아나도 아무도 안 본다).
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    def _code(rel: str) -> str:
        """🔴 D46 — 독스트링·주석을 뺀 **코드만** 본다."""
        t = _ast.parse((root / rel).read_text(encoding="utf-8"))
        for n in _ast.walk(t):
            if isinstance(n, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef,
                              _ast.ClassDef)) and _ast.get_docstring(n):
                n.body = n.body[1:]
        return _ast.unparse(t)

    #  ① 상성 단계가 **안 돈다**
    assert "_s2e.run(" not in _code("app/core/pipeline.py"), (
        "🔴 상성 단계가 되살아났다")
    from app.core.stages import s2e_matchup as _s2e
    assert not hasattr(_s2e, "run"), "🔴 `s2e_matchup.run`(상성)이 되살아났다"
    #  ② 확률 경로가 **시뮬을 안 부른다**
    said = _code("app/core/probmodel.py")
    assert "_sim.run(" not in said, "🔴 확률 경로가 몬테카를로를 다시 부른다"
    assert "flat_prob(varset" in said, "🔴 승무패가 `flat_prob` 에서 안 나온다"
    #  ③ λ 재료 함수들이 **없다**
    from app.core import probmodel as _pm
    for one in ("league_mean", "away_mul", "_share", "league_base"):
        assert not hasattr(_pm, one), f"🔴 `probmodel.{one}`(λ 재료)가 되살아났다"


def test_v6_긴카드가_네_덩이를_부른다():
    """🔴 배선 — `card_text` 가 `matchup_long` 을 **실제로** 부른다(#2)."""
    import ast
    said = (ROOT / "app" / "core" / "render.py").read_text(encoding="utf-8")
    src = [n for n in ast.walk(ast.parse(said))
           if isinstance(n, ast.FunctionDef) and n.name == "card_text"]
    assert src and "matchup_long" in ast.unparse(src[0]), (
        "🔴 긴 카드가 상성 블록을 안 부른다")
