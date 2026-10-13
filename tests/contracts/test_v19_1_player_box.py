"""🔴🔴 **선수 가치 v2 — 박스 기록**(사용자 결정 2026-10-13 저녁 · 1번).

> 선수 가치 v2 (`app/core/ratings/player_box.py`): fotmob playerStats
> (`before_as_of`)로 선수별 **90분당 xG+xA**(공격), 출전 분 가중 · 시간 감쇠 ·
> 출전 < 450분은 **리그·포지션 평균으로 수축**. 수비수·GK 는 일단 **출전 분
> 비중만**(후속 과제 표시). 안정성 보고: 시즌 반분 상관 — **0.3 이상**이어야
> 다음 단계로.

🔴 왜 바꿨나 — 구간 ±(`player_pm`)는 실측에서 **반분 상관 +0.06~+0.09** 였고
   시즌 교차가 *"거의 전부 수축하라"* 고 했다(λ 3200·12800). 박스 기록은 **그
   선수가 직접 만든 것**이라 팀 효과가 덜 섞인다.
🔴 **PB1** — `as_of` 이후 경기는 안 본다(문은 `fotmob.before_as_of` 하나).
🔴 **PB2** — 안 뛴 선수를 **0 으로 넣지 않는다**(칸이 없다). ⚠️ 반면 **xG 를 잰
   경기에서 기록이 없는 선수**는 그 경기에서 xG 가 **진짜 0** 이다 — 그 둘을 가른다.
🔴 **PB3** — 수비수·GK 의 수는 **공격 기여가 아니다**(출전 분 비중이고 그 이름을
   표가 들고 있다). 섞어 쓰면 수비수가 "약한 선수"가 된다.
"""
from __future__ import annotations

from datetime import datetime, timezone

UTC = timezone.utc


def _m(day: str, pstat: dict, pos: dict | None = None) -> dict:
    return {"utc": f"{day}T12:00:00Z", "league": "league:T1",
            "pstat": dict(pstat), "pos": dict(pos or {})}


def test_value_is_xg_plus_xa_per_90() -> None:
    """🔴 공격 가치 = **90분당 xG+xA**(합이 아니라 **분당**이다)."""
    from app.core.ratings import player_box as pb
    rows = [_m("2026-03-01",
               {"p1": {"minutes_played": 90.0, "expected_goals": 0.5,
                       "expected_assists": 0.1},
                "p2": {"minutes_played": 45.0, "expected_goals": 0.5,
                       "expected_assists": 0.1}},
               {"p1": "FW", "p2": "FW"})]
    got = pb.fit(rows, as_of=datetime(2026, 4, 1, tzinfo=UTC))
    # 🔴 같은 xG 를 **절반 시간**에 낸 p2 가 **두 배**다
    #    ⚠️ 잰 수는 `raw` 다 — `value` 는 그 위에 **수축**이 걸린 값이다
    #       (450분 미만이면 평균 쪽으로 끌린다 · 그 자리는 아래 계약이 센다).
    assert abs(got.raw["p1"] - 0.6) < 1e-6, got.raw
    assert abs(got.raw["p2"] - 1.2) < 1e-6, got.raw


def test_backline_is_minutes_share_and_says_so() -> None:
    """🔴🔴 **PB3** — GK·DF 는 **출전 분 비중**이고 표가 그 이름을 든다."""
    from app.core.ratings import player_box as pb
    rows = [_m("2026-03-01",
               {"g1": {"minutes_played": 90.0},
                "d1": {"minutes_played": 45.0},
                "f1": {"minutes_played": 90.0, "expected_goals": 0.3}},
               {"g1": "GK", "d1": "DF", "f1": "FW"})]
    got = pb.fit(rows, as_of=datetime(2026, 4, 1, tzinfo=UTC))
    assert got.kind["g1"] == "출전 분" and got.kind["d1"] == "출전 분", got.kind
    assert got.kind["f1"] == "공격", got.kind
    # 🔴 수비 쪽 수는 **0~1 비중**이다(xG 단위가 아니다)
    assert 0.0 <= got.raw["g1"] <= 1.0 and got.raw["g1"] > got.raw["d1"], got.raw
    assert "후속 과제" in got.why


def test_missing_xg_is_zero_only_in_measured_matches() -> None:
    """🔴🔴 **PB2** — xG 를 잰 경기의 빈칸은 **진짜 0**, 안 잰 경기는 **버린다**."""
    from app.core.ratings import player_box as pb
    measured = _m("2026-03-01",
                  {"a": {"minutes_played": 90.0, "expected_goals": 0.4},
                   "b": {"minutes_played": 90.0}}, {"a": "FW", "b": "FW"})
    blind = _m("2026-03-08", {"c": {"minutes_played": 90.0}}, {"c": "FW"})
    got = pb.fit([measured, blind], as_of=datetime(2026, 4, 1, tzinfo=UTC))
    assert got.raw["b"] == 0.0, got.raw              # 🔴 잰 경기의 0 은 0 이다
    assert "c" not in got.raw, got.raw               # 🔴 안 잰 경기는 버린다
    assert "xG 를 안 잰 경기" in got.why


def test_short_minutes_shrink_at_450() -> None:
    """🔴 출전 **450분** 미만은 리그·포지션 평균 쪽으로 간다(§1 문턱)."""
    from app.core.ratings import player_box as pb
    assert pb.MIN_MINUTES == 450
    rows = [_m(f"2026-0{m}-0{d}",
               {"big": {"minutes_played": 90.0, "expected_goals": 0.2},
                "big2": {"minutes_played": 90.0, "expected_goals": 0.2}},
               {"big": "FW", "big2": "FW"})
            for m in (3, 4, 5) for d in (1, 2)]
    rows.append(_m("2026-05-09",
                   {"tiny": {"minutes_played": 10.0, "expected_goals": 0.5},
                    "big": {"minutes_played": 90.0, "expected_goals": 0.2}},
                   {"tiny": "FW", "big": "FW"}))
    got = pb.fit(rows, as_of=datetime(2026, 6, 1, tzinfo=UTC))
    # 🔴 10분에 0.5 는 90분당 4.5 다 — 수축이 그것을 **평균 쪽으로** 끌어야 한다
    assert got.raw["tiny"] > 4.0, got.raw        # 🔴 잰 수는 90분당 4.5 다
    assert got.value["tiny"] < 1.0, got.value    # 🔴 수축이 평균 쪽으로 끌었다
    assert "수축" in got.why


def test_leak_door_is_one() -> None:
    """🔴 **PB1** — `as_of` 이후 경기는 안 본다(문은 `before_as_of` 하나)."""
    import inspect

    from app.core.ratings import player_box as pb
    said = inspect.getsource(pb.fit)
    assert "before_as_of" in said
    rows = [_m("2026-09-01", {"late": {"minutes_played": 90.0,
                                       "expected_goals": 1.0}},
               {"late": "FW"})]
    got = pb.fit(rows, as_of=datetime(2026, 4, 1, tzinfo=UTC))
    assert not got.value and "🔴" in got.why


def test_stability_uses_the_one_metric() -> None:
    """🔴 안정성은 `player_pm.stability` **하나**다(사본 금지 · #1)."""
    import ast
    from pathlib import Path
    said = (Path(__file__).resolve().parents[2]
            / "app/core/ratings/player_box.py").read_text(encoding="utf-8")
    tree = ast.parse(said)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    code = ast.unparse(tree)
    assert "corrcoef" not in code, "🔴 상관을 여기서 다시 세지 않는다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **신호 재정의 L6·L7·L8**(사용자 결정 2026-10-13 저녁 · 2번)
# ══════════════════════════════════════════════════════════════════
#
#  > L6 attackΔ_⊥  : 오늘 XI 공격 기여 **합**(90분당 xG+xA) 홈−원정
#  > L7 keyoutΔ_v2 : usual_xi 중 공격 기여 **상위 3명 결장 수**의 차
#  > L8 absΔ_v2_⊥  : (빠진 usual 기여 − 대체 선수 기여)의 홈−원정 차
#  🔴 전부 **차분값**이고 직교화를 지나야 들어온다(LF1).

def test_v2_signals_exist_and_are_differences() -> None:
    from app.core import lineupfix as lf
    assert set(("L6", "L7", "L8")) <= set(lf.SIGNALS)
    box = {"value": {"f1": 0.9, "f2": 0.5, "f3": 0.2, "d1": 0.8,
                     "q1": 0.3, "q2": 0.3, "q3": 0.3},
           "kind": {"f1": "공격", "f2": "공격", "f3": "공격",
                    "d1": "출전 분", "q1": "공격", "q2": "공격",
                    "q3": "공격"}}
    home = {"xi": ["f2", "f3", "d1"], "usual": ["f1", "f2", "f3"],
            "bench": []}
    away = {"xi": ["q1", "q2", "q3"], "usual": ["q1", "q2", "q3"],
            "bench": []}
    got, why = lf.raw_v2_of(home=home, away=away, box=box)
    # 🔴 L6 — 홈은 공격 **합** 0.5+0.2 = 0.7(뒷선 d1 은 **0 으로 안 센다**),
    #    원정은 0.9 → 차 **음수**
    assert abs(got["L6"] - (0.7 - 0.9)) < 1e-9, (got, why)
    # 🔴 L7 — 홈은 상위 3명(f1·f2·f3) 중 f1 이 빠졌다 → 1, 원정 0 → **+1**
    assert got["L7"] == 1.0, got
    # 🔴 L8 — 홈은 f1(0.9)이 빠지고 d1 이 들어왔다(공격 기여 **안 센다**) → +0.9
    assert abs(got["L8"] - 0.9) < 1e-9, got
    assert "뒷선" in why


def test_v2_signals_need_the_v2_table() -> None:
    """🔴 가치 v2 표가 없으면 **0 이 아니라 빠진다**(#3)."""
    from app.core import lineupfix as lf
    got, why = lf.raw_v2_of(home={"xi": ["a"], "usual": [], "bench": []},
                            away={"xi": ["b"], "usual": [], "bench": []},
                            box={})
    assert got == {} and "🔴" in why, (got, why)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **(나) 가 찾은 결함 둘**(2026-10-13 밤 · 43경기 감사)
# ══════════════════════════════════════════════════════════════════
#
#  ① **표에 없는 선수를 0 으로 셌다** — 들어온 선수 303명 중 **28명(9%)** 이
#     가치 표에 없었고 `_sum` 이 그들을 **0** 으로 셌다. 빠진 선수는 거의 전부
#     표에 있으므로(3/303) 차이가 **한 방향으로 부풀었다**. 🔴 **PL2** — 모르는
#     선수는 **0 이 아니라 평균**이다.
#  ② 로테이션 — 빠진 선수 298명 중 **132명(44%)이 다음 경기에 선발 복귀**했다.
#     🔴 그래서 L8 은 *"결장"* 이 아니라 **"XI 변화량"** 이다(이름이 틀렸다).
#     ⚠️ 그 사실은 **고쳐서 살릴 수 없다** — 표본 전체 상관이 +0.026(평균으로
#     메우면 +0.055)이고 넓은 구간에서 −0.10 이다(방향 정보가 없다).
#     그래서 **L9**(오늘 − 그 팀 평소)로 간다 — 로테이션을 "결장"으로 부르지 않는다.


def test_unknown_player_counts_as_the_mean_not_zero() -> None:
    """🔴🔴 **PL2** — 가치 표에 없는 선수는 **평균**으로 센다(0 금지)."""
    from app.core import lineupfix as lf
    box = {"value": {"f1": 1.0, "f2": 0.0}, "kind": {"f1": "공격",
                                                     "f2": "공격"}}
    # 🔴 홈은 f1(1.0)이 빠지고 **표에 없는 선수**가 들어왔다 — 평균 0.5 로 센다
    got, why = lf.raw_v2_of(
        home={"xi": ["new"], "usual": ["f1"], "bench": []},
        away={"xi": ["f2"], "usual": ["f2"], "bench": []}, box=box)
    assert abs(got["L8"] - 0.5) < 1e-9, (got, why)       # 1.0 − 0.5
    assert "표에 없는" in why, why


def test_l9_is_today_minus_the_teams_usual() -> None:
    """🔴🔴 **L9** — `(오늘 합 − 그 팀 평소 합)` 의 홈−원정 차(팀 수준이 빠진다).

    🔴 왜 — L6(오늘 합의 차)은 *"원래 공격이 센 팀인가"* 를 주로 잰다. 그 수준은
       **M1 축0·축1 이 이미** 들고 있다 → 같은 정보를 두 번 넣는 꼴이었다
       (실측: 확률은 2.42%p 움직였는데 선택 적중이 55.0% → 52.9% 로 떨어졌다).
    """
    from app.core import lineupfix as lf
    # ⚠️ 원정 두 선수의 **수준을 낮게** 둔다 — 그래야 "평소대로 나온 날"에
    #    L9 는 0 이고 L6 은 **0 이 아님**을 가를 수 있다(둘이 다른 것을 잰다).
    box = {"value": {"a": 1.0, "b": 0.4, "c": 0.1, "x": 0.5, "y": 0.5},
           "kind": {k: "공격" for k in ("a", "b", "c", "x", "y")}}
    # 🔴 홈은 평소 a+b(1.4) 인데 오늘 b+c(0.5) → −0.9 · 원정은 평소대로 → 0
    got, why = lf.raw_v2_of(
        home={"xi": ["b", "c"], "usual": ["a", "b"], "bench": []},
        away={"xi": ["x", "y"], "usual": ["x", "y"], "bench": []}, box=box)
    assert abs(got["L9"] - (-0.9)) < 1e-9, (got, why)
    # 🔴 **평소대로 나온 날은 0 이다** — 그것이 L6 과 다른 점이다
    same, _w = lf.raw_v2_of(
        home={"xi": ["a", "b"], "usual": ["a", "b"], "bench": []},
        away={"xi": ["x", "y"], "usual": ["x", "y"], "bench": []}, box=box)
    assert abs(same["L9"]) < 1e-9, same
    # ⚠️ 같은 자리에서 L6 은 **0 이 아니다**(두 팀의 수준 차가 남는다)
    assert abs(same["L6"]) > 0.0, same
