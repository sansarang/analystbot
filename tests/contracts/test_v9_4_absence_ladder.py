"""🔴🔴 **결장 사다리** — 사용자 지시 2026-10-11(연쇄를 앞에서부터 고친다) ①.

> 결장 사다리: fotmob 결장 → (없으면) 명단 대조 → 연맹 징계 공지 → 국내 기사 2매체.
> 명단 대조: 최근 리그 5경기 선발 3회 이상인데 오늘 출전 명단(선발+벤치)에 없으면
> "명단 제외(사유 미상)" — 구조 사실, soft. 징계(경고 누적·퇴장)는 hard.
> "결장 명단 미확보"는 **네 칸 모두 0일 때만**, 칸별 시도 결과를 적는다.

⚠️ 왜 — 광주–울산 카드의 연쇄: 결장 미확보 → 기사 0 → 전략 버림 → 전술 템플릿.
   fotmob 의 `unavailable` 칸이 비면 그 뒤가 전부 비었다(그 칸 하나에 매달려 있었다).
"""
from __future__ import annotations

import ast
import inspect


def _src(fn) -> str:
    tree = ast.parse(inspect.getsource(fn))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Module)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def _xi(key: str, players: list[str], bench: list[str] | None = None):
    from app.core.schema import XI, Player
    return XI(team=key, state="confirmed",
              lineup=[Player(name=x) for x in players],
              players=list(players), bench=list(bench or []))


def _facts(**kw):
    from app.core.schema import Facts
    return Facts(**kw)


# ══════════════════════════════════════════════════════════════════
# 칸 2 — 명단 대조
# ══════════════════════════════════════════════════════════════════

def test_roster_gap_finds_the_regular_who_is_not_in_the_squad() -> None:
    """🔴 최근 5경기 **선발 3회 이상**인데 오늘 명단(선발+벤치)에 없으면 결장."""
    from app.core import absence
    key = "team:000319"
    past = [_xi(key, ["A", "B", "C"]), _xi(key, ["A", "B", "D"]),
            _xi(key, ["A", "C", "D"]), _xi(key, ["B", "C", "D"]),
            _xi(key, ["A", "B", "C"])]
    facts = _facts(xi={key: _xi(key, ["B", "C", "D"], bench=["E"])},
                   past_xi={key: past},
                   squad={key: ["B", "C", "D", "E"]})
    got = absence.roster_gap(facts, key)
    #: A 는 5경기 중 4회 선발인데 오늘 명단에 없다
    assert [x.name for x in got] == ["A"], [x.name for x in got]
    one = got[0]
    assert one.source == "roster" and one.reason == "other"
    assert "명단 제외" in one.why and "사유 미상" in one.why


def test_roster_gap_ignores_the_rotation_player() -> None:
    """🔴 선발 2회(<3)면 **세지 않는다** — 로테이션을 결장으로 바꾸지 않는다."""
    from app.core import absence
    key = "team:000319"
    past = [_xi(key, ["A", "B"]), _xi(key, ["A", "C"]),
            _xi(key, ["B", "C"]), _xi(key, ["B", "C"]), _xi(key, ["B", "C"])]
    facts = _facts(xi={key: _xi(key, ["B", "C"])},
                   past_xi={key: past}, squad={key: ["B", "C"]})
    assert absence.roster_gap(facts, key) == []


def test_roster_gap_needs_the_squad_list() -> None:
    """⚠️ 오늘 명단을 못 받았으면 **아무도 세지 않는다**(없는 자료로 결장 금지)."""
    from app.core import absence
    key = "team:000319"
    past = [_xi(key, ["A", "B", "C"])] * 5
    facts = _facts(xi={key: _xi(key, ["B", "C"])}, past_xi={key: past})
    assert absence.roster_gap(facts, key) == []


def test_roster_gap_uses_the_bench_too() -> None:
    """🔴 **선발+벤치**가 오늘 명단이다 — 벤치에 있으면 결장이 아니다."""
    from app.core import absence
    key = "team:000319"
    past = [_xi(key, ["A", "B", "C"])] * 5
    facts = _facts(xi={key: _xi(key, ["B", "C"], bench=["A"])},
                   past_xi={key: past}, squad={key: ["B", "C", "A"]})
    assert absence.roster_gap(facts, key) == []


# ══════════════════════════════════════════════════════════════════
# 사다리 — 칸별 결과를 적는다
# ══════════════════════════════════════════════════════════════════

def test_ladder_reports_every_rung() -> None:
    """🔴🔴 네 칸의 **시도 결과**를 다 적는다 — 0 이어도 이름으로 남는다(#3)."""
    from app.core import absence
    key = "team:000319"
    facts = _facts(xi={key: _xi(key, ["B", "C"])}, past_xi={}, squad={})
    got = absence.ladder(facts, keys=[key], league="league:KL1")
    names = [str(r["rung"]) for r in got["rungs"]]
    assert names == list(absence.RUNGS), names
    for row in got["rungs"]:
        assert "why" in row and str(row["why"]).strip(), row
        assert "got" in row


def test_ladder_stops_when_fotmob_has_the_list() -> None:
    """🔴 *"fotmob 결장 → (없으면) 명단 대조"* — 있으면 아래 칸을 **안 센다**."""
    from app.core import absence
    from app.core.schema import Missing
    key = "team:000319"
    past = [_xi(key, ["A", "B", "C"])] * 5
    facts = _facts(xi={key: _xi(key, ["B", "C"])}, past_xi={key: past},
                   squad={key: ["B", "C"]},
                   missing={key: [Missing(name="Z", reason="injury")]})
    got = absence.ladder(facts, keys=[key], league="league:KL1")
    rung = {str(r["rung"]): r for r in got["rungs"]}
    assert rung["fotmob"]["got"] == 1
    assert "건너뛰었다" in str(rung["명단 대조"]["why"])
    assert not got["add"].get(key)


def test_unknown_only_when_all_rungs_are_zero() -> None:
    """🔴🔴 *"결장 명단 미확보"는 네 칸 모두 0일 때만*."""
    from app.core import absence
    key = "team:000319"
    past = [_xi(key, ["A", "B", "C"])] * 5
    facts = _facts(xi={key: _xi(key, ["B", "C"])}, past_xi={key: past},
                   squad={key: ["B", "C"]})
    got = absence.ladder(facts, keys=[key], league="league:KL1")
    assert got["add"].get(key), "명단 대조가 A 를 찾아야 한다"
    assert not absence.unknown(got), "칸이 찼는데 미확보라고 적었다"
    empty = absence.ladder(_facts(), keys=[key], league="league:KL1")
    assert absence.unknown(empty), "네 칸이 다 0 인데 미확보가 아니다"


def test_s2_facts_runs_the_ladder() -> None:
    """🔴 배선 — `s2_facts` 가 사다리를 돌리고 그 결과를 `Facts` 에 담는다."""
    from app.core.schema import Facts
    from app.core.stages import s2_facts
    src = _src(s2_facts)
    assert "absence" in src and "ladder" in src
    assert "absence_rungs" in Facts.model_fields


def test_gap_text_comes_from_the_ladder() -> None:
    """🔴 *"결장 명단 미확보"* 글자는 **사다리 결과**로만 적는다."""
    from app.core.stages import s2_facts
    src = _src(s2_facts._gaps)
    assert "결장 명단 미확보" in src
    assert "rungs" in src or "absence" in src, "fotmob 칸만 보고 적는다"


def test_card_prints_the_rungs() -> None:
    """🔴 카드 블록 2b 가 **칸별 결과**를 적는다."""
    from app.core import render
    src = _src(render)
    assert "absence_rungs" in src
