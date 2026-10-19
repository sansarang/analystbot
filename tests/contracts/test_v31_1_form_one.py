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


def test_폼은_확률_보정표에서_빠졌다() -> None:
    """🔴🔴 **뒤집혔다**(사용자 지시 2026-10-18 — *"과거 경기력 폼 제외"*).

    ⚠️ 2026-10-18 낮에는 폼 부등호를 λ 표에 **넣었다**. 같은 날 저녁 실측
       (즈볼러 4-1 · 우디네세 0-3)에서 과거 층이 결과와 반대로 가자 **뺐다**.
    🔴 부등호 자체는 남는다 — 카드·⑯ 이 읽는 글자다(확률만 안 움직인다).
    """
    from app.core import routing
    box = routing.table().get("lambda_rules") or {}
    fav = ((box.get("by_var") or {}).get("favors") or {})
    gls = ((box.get("by_var") or {}).get("goals") or {})
    for name in ("recent_pattern", "form_streak", "squad_rotation"):
        assert name not in {str(x) for x in (fav.get("types") or [])}, name
        assert name not in {str(x) for x in (gls.get("types") or [])}, name
    # 🔴 자리도 `hypo` 뿐이다(한쪽만 걷으면 다시 샌다)
    types = routing.table().get("types") or {}
    for name in ("recent_pattern", "form_streak", "squad_rotation"):
        assert list((types.get(name) or {}).get("places") or []) == ["hypo"], name
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


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **한 사실 한 표** — 사용자 지시 2026-10-19(구조적 결함)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측(우디네세 0-3 레체): 결장자 **한 명**(Ivan Ilić)이 확률에 **두 표**로
#     들어갔다 — `IR02-away`(몇 명 빠졌나) + `AB2-away`(누가 빠졌나).
#     그 둘이 홈을 밀어 홈 1위(36.5%)가 됐고 결과는 0-3 원정 완승이다.
#  🔴 둘은 **다른 모듈**에서 온다(s5_verify ↔ datavars) — 그래서 각자 집안
#     규칙으로는 못 묶이고, 합쳐진 뒤 `pipeline` 이 한 번 본다.

def test_같은_결장은_한_표만_센다() -> None:
    """🔴 대표는 `AB2`(품질까지 센다) · `IR02` 는 맥락으로 내려간다.

    🔴 돌연변이: `one_fact_one_vote` 를 빼면 한 결장이 두 표가 된다.
    """
    from app.core import datavars as dv
    from app.core.schema import Variable
    from app.core.state import RunState

    def _v(vid: str, kind: str):
        return Variable(id=vid, type=kind, subject="team:000001", favors="home",
                        goals="none", target="t", hardness="soft", weight=0.7,
                        claim=f"{vid} 글", quote="q", doc_ids=[], from_rule=vid)
    rows = [_v("IR02-away", "def_absence"), _v("AB2-away", "absence_quality"),
            _v("IR02-home", "def_absence")]
    got = dv.one_fact_one_vote(rows, state=RunState(match_key="x"))
    box = {str(v.id): v for v in got}
    assert len(got) == 3, got                   # 🔴 줄 수는 그대로다
    assert box["AB2-away"].usable_as_basis, box["AB2-away"].claim
    # 🔴 같은 쪽(`-away`)의 `IR02` 는 맥락으로 내려간다
    assert box["IR02-away"].usable_as_basis is False, box["IR02-away"].claim
    assert "한 사실 한 표" in box["IR02-away"].claim
    # 🔴 **다른 쪽**(`-home`)은 대표가 없으니 그대로 선다
    assert box["IR02-home"].usable_as_basis, box["IR02-home"].claim


def test_한_사실_한_표가_파이프라인에_이어져_있다() -> None:
    """🔴 #2 배선 — 만든 것은 부르는 곳이 있어야 한다."""
    import ast
    import pathlib
    src = pathlib.Path("app/core/pipeline.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = {c.func.attr for c in ast.walk(tree)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)}
    assert "one_fact_one_vote" in calls, "🔴 파이프라인이 그 자리를 안 부른다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **인원 수가 다른 평균·합은 견주지 않는다** — 사용자 지시 2026-10-19
# ══════════════════════════════════════════════════════════════════
#
#  > 점수차가 많이 나는거는 실제로 우리 코드에 문제가 있다는거다 → **고쳐라**
#
#  ⚠️ 실측 — 큰 점수차 네 판 중 인원이 **같은** 셋은 다 맞췄고, 유일하게 틀린
#     판이 인원이 **다른** 판이었다(르아브르 1-3 · 0.50(8명) ↔ 0.37(10명) → 홈).
#  🔴 능력치를 못 받는 선수는 보통 출전이 적은 선수다 — 빼고 낸 평균은 위로
#     치우친다. 가치 **합**은 인원 수에 그대로 비례한다.

def test_인원이_다르면_능력치_평균을_안_센다() -> None:
    """🔴 돌연변이: `nh != na` 검사를 지우면 8명 ↔ 10명 평균이 다시 선다."""
    import ast
    import pathlib
    src = pathlib.Path("app/core/datavars.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "from_ability")
    seg = ast.get_source_segment(src, fn) or src
    # 🔴 허용값(`count_slack`)은 **설정**이 든다(사용자 결정 2026-10-19 ㄴ)
    assert "count_slack" in seg, "🔴 A1 이 인원 차를 안 본다"
    assert "인원 차" in seg, "🔴 사유를 이름으로 안 남긴다(#3)"


def test_인원이_다르면_가치_합을_안_센다() -> None:
    """🔴 가치 합은 인원에 비례한다 — 같은 수가 아니면 견주지 않는다."""
    import ast
    import pathlib
    src = pathlib.Path("app/core/datavars.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_squad_value")
    seg = ast.get_source_segment(src, fn) or ""
    assert "count_slack" in seg, "🔴 C3 이 인원 차를 안 본다"
    assert "인원 차" in seg, seg[-200:]
