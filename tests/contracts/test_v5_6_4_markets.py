"""🔴🔴 **v5 §6-4·§6-3·§6-6** — 종목별 마켓 생성 · 보드 없는 기준선 · pick 규칙.

§6-4 원문:

> **야구·하키도 총점 마켓을 만든다**(§6-c-3 폐지). 야구 무승부는 KBO·NPB 만
> (연장 상한 리그), **MLB 는 무승부 시나리오 없음**. 하키 승무패는 정규시간
> 3-way, +0.5 는 정규시간 무패, 총점은 연장·엠프티넷 포함. [#25 #29]

§6-3 원문:

> 보드가 없으면 **종목별 기준선 후보에 복수 대입**한다(축구 1.5/2.5/3.5 ·
> 유스 토너먼트 1.5 · **야구 7.5/8.5/9.5** · **하키 5.5/6.5**)하고 전부
> "보드 오면 무효" 꼬리표. [#19 M8 M19 M32]

§6-6 원문:

> 같은 경기에서 등급이 선 줄이 여럿이면 **생존율 높은 순**, 동률이면 **더 강한
> 주장**(승 > 무패 > 핸디 > 총점). **선언 순서로 고르지 않는다.** [#26]

══════════════════════════════════════════════════════════════════
🔴 왜 — 실측 2026-10-04(밀워키 vs 샌디에이고)
══════════════════════════════════════════════════════════════════

```
§6-c-3 총점 기준선을 못 구했다 — 총점 마켓을 이름으로 적지 않는다 · §6-f 표만 낸다
```
⚠️ 야구 카드에 **총점 마켓이 한 줄도 없었다.** 🔴 뿌리는 `common_lines` 에
   **축구만** 있던 것이다(`soccer: [2.5, 3.5]`).

그리고 `_pick_one` 이 **선언 순서**로 골라 `홈 무패`(1.0)가 `홈 승`(1.0)을,
`btts 예`(**0.8**)가 `오버 2.5`(**1.0**)를 이겼다 — §6-6 이 그것을 뒤집는다.

🔴 **§10-4 M39** — 선언 순서 pick(10-04) — 생존율 순 · 강한 주장 순
   ⚠️ 이 계약이 그 줄을 집행한다(`tests/test_contract_coverage.py` 가 번호로 대조한다).
"""
from __future__ import annotations

import pytest


def _game(sport: str = "baseball", league: str = "MLB"):
    from app import classify
    return classify.Game(home="A", away="B", sport=sport, league=league)


def _d(did, scores, strength=1.0):
    from app.scenarios import Draft
    return Draft(id=did, scores=scores, strength=strength,
                 template_id="t", why="시험")


def _five():
    from app import classify
    return [classify.Classified(text="x", source_url="u", hardness="hard",
                                type=t, direction=d, why="x")
            for t, d in (("pitcher_state", "home"), ("recent_pattern", "home"),
                         ("travel_schedule", "home"), ("h2h_pattern", "away"),
                         ("individual", "away"))]


# ══════════════════════════════════════════════════════════════════
# §6-3 — 종목별 기준선
# ══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("sport,want", [
    ("soccer", [1.5, 2.5, 3.5]),
    ("baseball", [7.5, 8.5, 9.5]),
    ("hockey", [5.5, 6.5]),
])
def test_v5_6_3_종목별_기준선이_선언돼_있다(sport, want):
    """🔴 §6-3 이 **이름 댄 수** 그대로다 — 내가 고른 것이 아니다."""
    from app import rules
    assert rules.common_total_lines(sport) == want, (
        sport, rules.common_total_lines(sport))


def test_v5_6_3_모르는_종목은_빈_목록이다():
    """🔴 지어내지 않는다 — 선언에 없으면 그 종목은 총점을 안 낸다."""
    from app import rules
    assert rules.common_total_lines("배구") == []


# ══════════════════════════════════════════════════════════════════
# §6-4 — 야구·하키도 총점 마켓을 만든다
# ══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("sport,league", [("baseball", "MLB"),
                                          ("hockey", "NHL")])
def test_v5_6_4_야구_하키도_총점_마켓을_만든다_M40(sport, league):
    """🔴🔴 §6-4 — *"§6-c-3 폐지."* ⚠️ 실측에서 야구 총점이 **0줄**이었다."""
    from app import survive
    res = survive.run([_d("A", ["3-1"], 2.0), _d("B", ["1-3"], 1.0)],
                      _game(sport, league), variables=_five())
    tot = [m for m in res.markets if str(m.market_type) == "total"]
    assert tot, [
        (m.market_type, m.team, m.line) for m in res.markets]
    lines = sorted({float(m.line) for m in tot if m.line is not None})
    from app import rules
    assert lines == sorted(rules.common_total_lines(sport)), lines
    # 🔴 §6-3 — *"전부 '보드 오면 무효' 꼬리표."*
    assert any("보드 오면 무효" in n for n in res.notes), res.notes


def test_v5_6_4_MLB는_무승부_시나리오가_없다():
    """🔴 §6-4 — *"야구 무승부는 KBO·NPB 만(연장 상한 리그), MLB 는 없음."*"""
    from app import scenarios
    sc = scenarios.generate(_five(), _game("baseball", "MLB"), standings=None)
    joined = " ".join(sc.notes)
    assert "무승부" in joined, sc.notes
    for d in (sc.drafts or []):
        for s in d.scores:
            a, b = s.split("-")
            assert a != b, f"🔴 MLB 에 무승부 스코어가 있다: {s}"


@pytest.mark.parametrize("league", ["KBO", "NPB"])
def test_v5_6_4_KBO_NPB는_무승부가_있을_수_있다(league):
    """⚠️ 연장 상한 리그다 — 무승부가 **가능하다**.

    🔴 선언은 `config/league_rules.yaml` 의 `draw_possible` 이다 — **이미 있던
       문**이고 내가 같은 이름의 함수를 하나 더 지으려 했다(`ruff F811` 이 잡았다).
    ⚠️ 실측 2026-10-04: **KBO 가 선언에 없었다**(`None` = *"선언되지 않았다"*).
       v5 §6-4 가 이름 댔는데 빠져 있었다.
    """
    from app import rules
    ok, why = rules.draw_possible(league)
    assert ok is True, (league, ok, why)
    assert str(why or "").strip(), (league, why)
    # 🔴 MLB 는 **없다**
    mlb_ok, mlb_why = rules.draw_possible("MLB")
    assert mlb_ok is False, (mlb_ok, mlb_why)
    assert "무제한" in mlb_why or "무승부가 없다" in mlb_why, mlb_why


# ══════════════════════════════════════════════════════════════════
# §6-6 — pick 은 **생존율 순**
# ══════════════════════════════════════════════════════════════════


def test_v5_6_6_생존율_높은_줄을_고른다_M25():
    """🔴🔴 §6-6 — *"**생존율 높은 순** … **선언 순서로 고르지 않는다**."*

    ⚠️ 실측 2026-10-04: `btts 예`(**0.8**)가 `오버 2.5`(**1.0**)를 이겼다 —
       선언 순서(`win → btts → total → handicap`)가 그렇게 시켰다.
    """
    from app import survive
    res = survive.run([_d("A", ["1-0"], 2.0), _d("B", ["0-1"], 1.0)],
                      _game("soccer", "EPL"), variables=_five(),
                      xi_state="확정")
    graded = [m for m in res.markets if str(m.verdict) != "none"]
    if not graded:
        pytest.skip("이 세트는 등급이 서는 줄이 없다 — 아래 단위 시험이 본다")
    best = max(float(m.survival or 0) for m in res.markets)
    for m in graded:
        assert float(m.survival or 0) >= best - 1e-9, (
            f"🔴 생존율이 낮은 줄이 뽑혔다(§6-6): {m.market_type} "
            f"{m.survival} < 최고 {best}")


def test_v5_6_4_무승부_선언이_없으면_만들지_않는다():
    """🔴 모르면 **만들지 않는다** — 있는 척하지 않는다(기존 규율)."""
    from app import rules
    ok, why = rules.draw_possible("없는리그")
    assert ok is None, (ok, why)
    assert "선언되지 않았다" in why, why


def test_v5_6_6_동률이면_더_강한_주장():
    """🔴 §6-6 — *"동률이면 **더 강한 주장**(승 > 무패 > 핸디 > 총점)."*

    ⚠️ 종전 선언은 `[win, btts, total, handicap]` 이고 *"무패 우선"* 이었다 —
       🔴 §6-6 이 그것을 뒤집었다(더 **강한** 주장이 먼저다).
    """
    from app import rules
    order = rules.claim_strength()
    assert order[:1] == ["win"], order
    assert order.index("win") < order.index("handicap") < order.index("total")
    # 🔴 `home_dc`(무패)는 `home`(승)보다 **뒤**다
    assert order.index("win") < order.index("dc"), order


def test_v5_6_6_선언_순서로_고르지_않는다_M39():
    """🔴 구조 계약 — `_rank` 의 **첫 칸이 생존율**이어야 한다(§6-6).

    ⚠️ *"생존율을 어디선가 본다"* 로는 약하다 — 종전 코드도 **둘째 칸**에서 봤다.
       🔴 §6-6 은 *"**생존율 높은 순**, 동률이면 더 강한 주장"* 이므로 **순서**가
       뜻이다. 그래서 `_rank` 가 돌려주는 tuple 의 **첫 원소**를 본다.
    """
    import ast
    import inspect
    import textwrap

    from app import survive
    src = textwrap.dedent(inspect.getsource(survive._pick_one))
    tree = ast.parse(src)
    rank = next((n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == "_rank"), None)
    assert rank is not None, "🔴 `_rank` 가 없다"
    ret = next(n for n in ast.walk(rank) if isinstance(n, ast.Return))
    assert isinstance(ret.value, ast.Tuple), ast.unparse(ret)
    first = ast.unparse(ret.value.elts[0])
    assert "survival" in first, (
        f"🔴 `_rank` 의 **첫 칸이 생존율이 아니다**(§6-6): {first}")
    # 🔴 그리고 **주장 강도**가 둘째다(동률 가리기)
    second = ast.unparse(ret.value.elts[1])
    assert "claim" in second.lower(), second
    # ⚠️ 종전의 `order.index(kind)`(선언 순서)가 **사라졌다**
    assert "order.index" not in ast.unparse(rank), ast.unparse(rank)
