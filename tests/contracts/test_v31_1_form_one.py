"""🔴🔴 **S01 폼도 집안 하나 — 부등호로 센다**(사용자 지시 2026-10-18).

> 은 꼬리표가 양 팀에 동시에 걸리면 서로 지웁니다..어떤종류인지 보여주라
> → **S01 부터 고쳐라 집안마다 부등호 하나**

⚠️ 실측 2026-10-18(여섯 경기) — 양 팀에 같이 걸려 **서로 지운** 꼬리표:
   `S01` **4경기**(오카야마 빼고 전부) · `IR02` 2 · `IR12` 2 · `TURN` 1 · `AB2` 1.
   서울–김천은 변수 **17개**가 서고도 순 쏠림이 **1단계**였다(홈 34.2%).
   모양은 늘 같았다 — `[S01-home] away ×1.05` ↔ `[S01-away] home ×1.05`.
"""
from __future__ import annotations

import importlib

from app.core.schema import Facts
from app.core.stages import s5_verify as s5
from app.core.state import RunState

ROW = {"type": "recent_pattern"}


def _ref():
    return importlib.import_module("tests.e2e.test_v6_replay")._ref()


def _recent(scored: float, conceded: float, n: int = 5) -> dict:
    """🔴 폼 칸 한 팀 — 보정 득점 평균과 **경기마다** 실점."""
    return {"matches": n, "last5": ["W"] * n,
            "recent_scored_avg": scored, "recent_trimmed_avg": scored,
            "sequence": [{"goals_against": int(conceded)} for _ in range(n)]}


def _run(ref, home: dict, away: dict):
    facts = Facts(recent={str(ref.home): home, str(ref.away): away})
    return s5._ir_recent("S01", ROW, ref, facts, state=RunState(match_key="x"))


def test_양_팀_폼이_같이_걸리면_부등호_하나만_확률에_닿는다() -> None:
    """🔴 돌연변이: `_form_one` 을 지우면 두 변수가 서로 반대쪽을 밀어 상쇄한다."""
    ref = _ref()
    got = _run(ref, _recent(1.8, 1), _recent(0.6, 1))
    assert len(got) == 2, got            # 🔴 줄 수는 그대로다(둘 다 카드에 남는다)
    box = {("home" if v.subject == ref.home else "away"): v for v in got}
    # 🔴 보정 득점이 **큰** 홈이 낫다 → 홈 쪽으로 민다
    assert box["home"].favors == "home", box["home"].claim
    assert box["home"].usable_as_basis, box["home"].claim
    assert ">" in box["home"].claim and "보정 득점 평균" in box["home"].claim
    # 🔴 못한 쪽은 **맥락 전용** — 확률에 안 닿는다(상쇄가 사라진다)
    assert box["away"].usable_as_basis is False, box["away"].claim
    assert "집안 하나" in box["away"].claim, box["away"].claim


def test_득점이_같으면_실점으로_가린다() -> None:
    """🔴 사다리 ② — 득점 차가 문턱 미만이면 **실점 적은 쪽**이 낫다."""
    ref = _ref()
    got = _run(ref, _recent(1.2, 2), _recent(1.2, 0))
    box = {("home" if v.subject == ref.home else "away"): v for v in got}
    assert box["away"].favors == "away", box["away"].claim
    assert "실점 평균" in box["away"].claim, box["away"].claim
    assert box["home"].usable_as_basis is False


def test_둘_다_같으면_같다고_적고_확률에_안_넣는다() -> None:
    """🔴 *"같다고 해라"* — 두 자 다 문턱 미만이면 **둘 다 맥락**(확률 0)."""
    ref = _ref()
    got = _run(ref, _recent(1.2, 1), _recent(1.2, 1))
    assert len(got) == 2
    for one in got:
        assert one.usable_as_basis is False, one.claim
        assert "폼 같다" in one.claim, one.claim


def test_한쪽만_있으면_종전대로_둔다() -> None:
    """⚠️ 견줄 상대가 없으면 **건드리지 않는다** — `goals` 칸이 그대로 민다."""
    ref = _ref()
    facts = Facts(recent={str(ref.home): _recent(0.4, 2)})
    got = s5._ir_recent("S01", ROW, ref, facts, state=RunState(match_key="x"))
    assert len(got) == 1 and got[0].subject == ref.home
    assert "집안 하나" not in got[0].claim and "폼 같다" not in got[0].claim


def test_폼_부등호가_확률_보정표에_있다() -> None:
    """🔴 자리와 λ 표가 **둘 다** 있어야 센다 — `favors` 목록에 유형이 있나."""
    from app.core import routing
    fav = (((routing.table().get("lambda_rules") or {}).get("by_var") or {})
           .get("favors") or {})
    assert "recent_pattern" in {str(x) for x in (fav.get("types") or [])}, fav
    # 🔴 사다리는 **둘**이고 방향이 못 박혀 있다(득점은 큰 쪽 · 실점은 적은 쪽)
    assert [(k, d) for k, d, _l in s5.FORM_LADDER] == [
        ("scored", "more"), ("conceded", "less")], s5.FORM_LADDER


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **집안 하나 — 공통 자리**(`_family_one`) · 사용자 지시 2026-10-18
# ══════════════════════════════════════════════════════════════════
#
#  > 그래 수정해라  (→ `TURN`·`IR02`·`IR12` 도 같은 모양으로)
#
#  🔴 네 집안이 **한 함수**를 쓴다(사본 금지) — 사다리 값은 각 규칙이 담는다.

def _var(vid: str, subject: str):
    from app.core.schema import Variable
    return Variable(id=vid, type="squad_rotation", subject=subject,
                    favors="both", goals="none", target="t", hardness="soft",
                    weight=0.7, claim=f"{vid} 글", quote="q", doc_ids=[],
                    from_rule=vid)


def test_집안하나_센_쪽만_남고_못한_쪽은_맥락이다() -> None:
    """🔴 돌연변이: `_family_one` 을 빼면 두 변수가 서로 반대쪽을 밀어 상쇄한다."""
    ref = _ref()
    rows = [_var("X-home", ref.home), _var("X-away", ref.away)]
    got = s5._family_one(rows, {"home": (5,), "away": (2,)}, ref, "X",
                         label="바꾼 자리", state=RunState(match_key="x"))
    box = {("home" if v.subject == ref.home else "away"): v for v in got}
    assert box["home"].usable_as_basis, box["home"].claim
    assert "집안 대표" in box["home"].claim and ">" in box["home"].claim
    assert box["away"].usable_as_basis is False, box["away"].claim
    assert "집안 하나" in box["away"].claim


def test_집안하나_같으면_둘_다_맥락이고_같다고_적는다() -> None:
    ref = _ref()
    rows = [_var("X-home", ref.home), _var("X-away", ref.away)]
    got = s5._family_one(rows, {"home": (3,), "away": (3,)}, ref, "X",
                         label="바꾼 자리", state=RunState(match_key="x"))
    assert all(not v.usable_as_basis for v in got), [v.claim for v in got]
    assert all("같다" in v.claim for v in got), [v.claim for v in got]


def test_집안하나_못_쟀거나_한쪽만이면_종전대로다() -> None:
    """⚠️ 견줄 상대가 없으면 **건드리지 않는다**(#3 — 사유는 기록에 남는다)."""
    ref = _ref()
    rows = [_var("X-home", ref.home), _var("X-away", ref.away)]
    same = s5._family_one(rows, {"home": (3,)}, ref, "X", label="바꾼 자리",
                          state=RunState(match_key="x"))
    assert same == rows
    one = s5._family_one(rows[:1], {"home": (3,), "away": (1,)}, ref, "X",
                         label="바꾼 자리", state=RunState(match_key="x"))
    assert one == rows[:1]


def test_네_집안이_같은_함수를_쓴다() -> None:
    """🔴 #1 사본 금지 — `TURN`·`IR02`·`IR12` 가 `_family_one` 을 부른다."""
    import ast
    import pathlib
    src = pathlib.Path("app/core/stages/s5_verify.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    want = {"_turn_vars": 0, "_ir_soccer": 0, "_ir_absence": 0}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        calls = {c.func.id for c in ast.walk(node)
                 if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
        if "_family_one" in calls:
            want[node.name] = want.get(node.name, 0) + 1
    assert want.get("_turn_vars"), "🔴 `TURN` 이 집안 하나를 안 부른다"
    assert want.get("_ir_soccer"), "🔴 `IR12` 가 집안 하나를 안 부른다"
    assert sum(want.values()) >= 3, f"🔴 집안 셋이 안 이어졌다 — {want}"
