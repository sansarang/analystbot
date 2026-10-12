"""🔴🔴 **고급 지표(xG) 두 판** — 사용자 지시 2026-10-12 + 결정 1·2·3번.

> 1번 100% xG로, 2번 대리지표 쓰고, 3번 b로 해라

① 축1 xG 판은 **100% xG** 이고 **운 할인을 안 본다**(이중 반영 금지)
② 축2 대리 지표: `press` 분모는 **상대** 패스 · `low_block` 은 **상대 슈팅 위치**
③ 계수는 **섞지 않는다** — `xg:` 블록이 `weights`·`lambda_model`·`fit` 을 덮는다
④ 카드가 **두 판을 나란히** 적고 **기본값은 득실판**이다(백필 브라이어 전)
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════
# ① 축1 — 100% xG · 운 할인 끔
# ══════════════════════════════════════════════════════════════════

def test_1_xg_only_is_pure_and_ignores_luck() -> None:
    from app.core import form
    rows = [{"gf": 4, "ga": 0, "opp": "X"}] * 5
    games = [{"gf": 4, "ga": 0, "xgf": 0.9, "xga": 1.4, "xg_n": 1}] * 5
    got = form.form_of("t", rows, elo={}, games=games, luck_goals=3.0,
                       xg_only=True)
    # 🔴 xG 가 음수이므로 지수도 음수다 — 득실 4-0 도, 운 할인도 안 본다
    assert got.index() is not None and got.index() < 0, (got.index(), got.why)
    assert abs(got.index() - (0.9 - 1.4)) < 1e-9, got.index()


def test_1_xg_판_없으면_득실판으로_간다() -> None:
    """⚠️ 팀 xG 를 읽은 경기가 문턱 미만이면 xG 판을 **만들지 않는다**."""
    from app.core import form
    rows = [{"gf": 1, "ga": 0, "opp": "X"}] * 5
    games = [{"gf": 1, "ga": 0, "xgf": 1.0, "xga": 0.5, "xg_n": 1}] * 2
    got = form.form_of("t", rows, elo={}, games=games, xg_only=True)
    assert got.xg_only is False
    assert any("xG 판 못 만듦" in x for x in [got.why]), got.why


# ══════════════════════════════════════════════════════════════════
# ② 축2 대리 지표 — 분모가 **상대** 쪽이다
# ══════════════════════════════════════════════════════════════════

def test_2_press_denominator_is_opponent() -> None:
    from app.core import style
    conf = style.axes()["press"]
    assert conf.get("per_side") == "opponent", conf
    assert conf.get("per") == "accurate_passes", conf


def test_2_low_block_reads_opponent_shot_location() -> None:
    from app.core import style
    conf = style.axes()["low_block"]
    assert conf.get("num_side") == "opponent", conf
    assert "shots_outside_box" in dict(conf.get("num") or {}), conf


def test_2_ratio_uses_the_other_column() -> None:
    """🔴 같은 통계로 **우리/상대**를 바꿔 읽는다(실측 꼴)."""
    from app.core.style import _ratio
    st = {"a": ({"n": 10}, {"n": 2}), "b": ({"n": 100}, {"n": 50})}
    mine = _ratio(st, {"num": {"a": 1.0}, "per": "b"}, 0)
    theirs = _ratio(st, {"num": {"a": 1.0}, "per": "b",
                         "per_side": "opponent"}, 0)
    assert abs(mine - 0.1) < 1e-9 and abs(theirs - 0.2) < 1e-9


# ══════════════════════════════════════════════════════════════════
# ③ 계수 — 섞지 않는다
# ══════════════════════════════════════════════════════════════════

def test_3_two_coefficient_sets() -> None:
    from app.core import matchup
    plain, xg = matchup.table(), matchup.table(xg=True)
    for key in ("weights", "lambda_model", "fit"):
        assert key in plain and key in xg
    # 🔴 xG 판 `fit` 은 **그 블록의 것**이다(위 칸을 덮는다)
    assert "백필" in str(xg["fit"].get("why") or "")


def test_3_xg_context_restores() -> None:
    from app.core import matchup
    before = matchup.table()["fit"]
    with matchup.xg_coeffs():
        assert matchup.table()["fit"] != before
    assert matchup.table()["fit"] == before


def test_3_xg_pass_runs_only_sync_calls() -> None:
    """🔴 전역 깃발의 안전 근거 — `with` 안에서 **await 가 없다**."""
    tree = ast.parse(_src("app/core/pipeline.py"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.With):
            continue
        said = ast.unparse(node)
        if "xg_coeffs()" in said:
            found.append(said)
    assert found, "🔴 xG 패스가 없다"
    for said in found:
        assert "await" not in said, said


# ══════════════════════════════════════════════════════════════════
# ④ 카드 — 두 판 나란히 · 기본값은 득실판
# ══════════════════════════════════════════════════════════════════

def test_4_card_prints_both_boards() -> None:
    from app.core import render
    box = {"sim": {"home": 0.4, "draw": 0.3, "away": 0.3},
           "xg_pass": {"sim": {"home": 0.3, "draw": 0.3, "away": 0.4},
                       "gaps": {"axis1": -0.2}, "form": {"home": -0.1,
                                                         "away": 0.2},
                       "why": ""}}
    said = render._xg_board(box, now={"home": 0.4, "draw": 0.3, "away": 0.3})
    body = "\n".join(said)
    assert "두 판 나란히" in body and "기본값은 득실판" in body
    assert "xG 판" in body
    # 🔴 방향이 갈리면 그 사실을 적는다(검수 재료)
    assert "갈린다" in body, body


def test_4_card_names_the_reason_when_no_xg() -> None:
    from app.core import render
    said = render._xg_board({"xg_pass": {"sim": {}, "why": "🔴 xG 판 없음 — X"}},
                            now={"home": 0.4, "draw": 0.3, "away": 0.3})
    assert said and "xG 판 없음" in said[0]


def test_4_grade_path_untouched() -> None:
    """🔴 등급·보드는 **득실판**으로 간다 — xG 판이 거기 닿지 않는다."""
    said = _src("app/core/pipeline.py")
    head = said.split("xg_coeffs()")[1][:1200]
    for word in ("board", "grade", "등급"):
        assert word not in head, head[:200]
