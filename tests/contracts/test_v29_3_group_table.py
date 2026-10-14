"""🔴🔴 **조 순위표 이름 맞추기 계약** — 실사고 2026-10-14.

> fotmob에 받아서 llm이 그컵이나 리그정보 분석만 해서 변수에 넣는다
> (사용자 지시 2026-10-14)

🔴 그 지시의 **앞칸**이 막혀 있었다: `fotmob.group_table` 이 이름을 **글자 그대로
   소문자 비교**해서, UCL 표 36팀 안에 `Feyenoord`·`Como` 가 **있는데도** 우리
   이름(`Feyenoord Rotterdam`·`Como 1907`)과 안 맞아 *"두 팀이 든 표를 못
   찾았다"* 가 됐다 → 순위·승점·라운드가 **전부 ⬜**.

지키는 것:
  GT1 맞추는 규칙은 `core/teamname.pick` **하나**다(사본 금지)
  GT2 글자 그대로 비교(`want <= got`)로 **돌아가지 않는다**
  GT3 **두 팀 다** 있어야 그 표를 쓴다(한 팀만 있으면 다른 조다)
  GT4 돌려주는 줄에 **순위·경기수·승점**이 있다(라운드는 `played` 다)
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD = "app/collect/fotmob.py"


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


def _body() -> str:
    code = _code(MOD)
    i = code.index("def group_table(")
    j = code.find("\ndef ", i + 10)
    return code[i:j if j > i else len(code)]


def test_gt1_uses_teamname_pick() -> None:
    """GT1 — `teamname.pick` 을 쓴다(새 비교를 짓지 않는다)."""
    said = _body()
    assert "teamname" in said and ".pick(" in said, (
        "GT1 🔴 `core/teamname.pick` 을 안 쓴다 — 이름 맞추기 규칙이 둘이 되면 "
        "한쪽만 고쳐진다(사본 금지)")


def test_gt2_no_literal_compare() -> None:
    """GT2 — 글자 그대로 비교로 **돌아가지 않는다**(그것이 사고의 원인이었다)."""
    said = _body().replace(" ", "")
    assert "want<=got" not in said, (
        "GT2 🔴🔴 글자 그대로 집합 비교가 돌아왔다 — `Feyenoord Rotterdam` 이 "
        "표의 `Feyenoord` 와 안 맞아 순위표를 통째로 잃는다(실측 2026-10-14)")


def test_gt3_both_teams_required() -> None:
    """GT3 — **두 팀 다** 있어야 쓴다. 돌려서 센다."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.collect import fotmob as fm

    def _row(i: int, n: str, played: int = 2, pts: int = 3) -> dict:
        return {"idx": i, "name": n, "played": played, "wins": 1, "draws": 0,
                "losses": 1, "scoresStr": "3-2", "goalConDiff": 1, "pts": pts}

    def _page(rows: list[dict], name: str = "T") -> dict:
        """🔴 `_tables` 가 보는 **실물 자리** — `props.pageProps.table[].data`.

        ⚠️ 그 함수의 머리말이 그렇게 적고 있다(조가 하나면 `data` 자체가 표다).
        """
        return {"props": {"pageProps": {"table": [
            {"data": {"leagueName": name, "table": {"all": rows}}}]}}}

    # 🔴 두 팀 다 있다(꼴이 달라도) → 표를 쓴다
    got = fm.group_table(
        _page([_row(1, "Feyenoord"), _row(2, "Como"), _row(3, "Arsenal")]),
        ["Feyenoord Rotterdam", "Como 1907"])
    assert got and len(got.get("rows") or []) == 3, (
        f"GT3 🔴 두 팀이 다 있는데 표를 못 찾았다 — {got}")
    # 🔴 한 팀만 있다 → 안 쓴다(다른 조다)
    bad = fm.group_table(_page([_row(1, "Feyenoord"), _row(2, "Arsenal")]),
                         ["Feyenoord Rotterdam", "Como 1907"])
    assert not bad, f"GT3 🔴 한 팀만 든 표를 썼다 — {bad}"


def test_gt4_rows_carry_round_and_points() -> None:
    """GT4 — 줄에 **순위·경기수(=라운드)·승점**이 있다."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.collect import fotmob as fm
    got = fm.group_table(
        {"props": {"pageProps": {"table": [{"data": {
            "leagueName": "UCL",
            "table": {"all": [
                {"idx": 5, "name": "Como", "played": 1, "wins": 1, "draws": 0,
                 "losses": 0, "scoresStr": "4-1", "goalConDiff": 3, "pts": 3},
                {"idx": 33, "name": "Feyenoord", "played": 1, "wins": 0,
                 "draws": 0, "losses": 1, "scoresStr": "1-5",
                 "goalConDiff": -4, "pts": 0}]}}}]}}},
        ["Feyenoord Rotterdam", "Como 1907"])
    rows = {str(r.get("name")): r for r in (got.get("rows") or [])}
    assert rows, f"GT4 🔴 줄이 없다 — {got}"
    for name, want in (("Como", (5, 1, 3)), ("Feyenoord", (33, 1, 0))):
        one = rows.get(name) or {}
        said = (one.get("rank"), one.get("played"), one.get("points"))
        assert said == want, (
            f"GT4 🔴 `{name}` 의 (순위, 경기수, 승점)이 {said} 다 — {want} 여야 "
            "한다. ⚠️ `played` 가 **라운드**다(지시 2026-10-14: *'지금 몇 "
            "라운드인데 승점이 필요하다'*)")
