"""🔴🔴 **§3 확률 변환** — 지시서 2026-10-12(엔진 교체) §3.

> `app/core/probfloor.py` 개편 — **손값 β 삭제.**
>   log λ홈  = b0 + b1·diff + b2·player_diff + h_league [+ 채택 항]
>   log λ원정 = b0 − b1·diff − b2·player_diff
> 그 위에 **Dixon-Coles ρ**(리그별) → **스코어 격자** → 승무패·오버·핸디·BTTS
> **전부 같은 격자에서**.
> 계약 **P1**: ⑯ 에서 λ를 만드는 식이 `probfloor` **하나**.
> 계약 **P2**: 오버·핸디·승무패가 **같은 격자 합**(소수 넷째 자리).
> 계약 **P3**: 홈 이점이 `h_league` **외 경로**로 들어가면 실패.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AS_OF = datetime(2026, 10, 11, 5, 0, tzinfo=UTC)

COEF = {"b0": 0.25, "b1": 0.31, "b2": 0.0, "h_league": 0.07, "rho": -0.08}


def test_lambdas_come_from_the_formula() -> None:
    """🔴 λ 는 **그 식 하나**에서 나온다(손값 β 가 없다)."""
    import math

    from app.core import probfloor as pf
    got, why = pf.lambdas(diff=0.6, player_diff=0.0, coef=COEF)
    assert abs(got["home"] - math.exp(0.25 + 0.31 * 0.6 + 0.07)) < 1e-9, why
    assert abs(got["away"] - math.exp(0.25 - 0.31 * 0.6)) < 1e-9, why
    assert "b1" in why and "h_league" in why


def test_no_hand_beta_left() -> None:
    """🔴🔴 **손값 β 삭제** — 코드가 `matchup_model` 의 β 로 λ 를 만들지 않는다."""
    said = (ROOT / "app/core/probfloor.py").read_text(encoding="utf-8")
    # ⚠️ D46 — 독스트링을 뺀 코드만 본다
    import ast
    tree = ast.parse(said)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    code = ast.unparse(tree)
    assert "beta" not in code, "🔴 손값 β 가 아직 코드에 있다"


def test_grid_is_one_source_for_every_market() -> None:
    """🔴🔴 **P2** — 승무패·오버·핸디·BTTS 가 **같은 격자**에서 나온다."""
    from app.core import probfloor as pf
    grid = pf.score_grid(lam_home=1.6, lam_away=1.1, rho=-0.08)
    out = pf.markets_of(grid)
    assert abs(out["home"] + out["draw"] + out["away"] - 1.0) < 1e-4
    # 🔴 오버 0.5 = 1 − P(0-0) · 같은 격자에서 나온 수여야 한다
    assert abs(out["over"][0.5] - (1.0 - grid[(0, 0)])) < 1e-4
    # 🔴 핸디 −0.5(홈) = 홈 승
    assert abs(out["ah"]["home-0.5"] - out["home"]) < 1e-4
    # 🔴 BTTS 예 + 아니오 = 1
    assert abs(out["btts_yes"] + out["btts_no"] - 1.0) < 1e-4


def test_rho_moves_the_low_scores_only() -> None:
    """🔴 Dixon-Coles ρ — **0-0·1-0·0-1·1-1 네 칸**만 고친다(합은 1 이다)."""
    from app.core import probfloor as pf
    flat = pf.score_grid(lam_home=1.4, lam_away=1.2, rho=0.0)
    bent = pf.score_grid(lam_home=1.4, lam_away=1.2, rho=-0.1)
    assert abs(sum(bent.values()) - 1.0) < 1e-6
    moved = {k for k in flat if abs(flat[k] - bent.get(k, 0.0)) > 1e-9}
    assert moved <= {(0, 0), (1, 0), (0, 1), (1, 1)}, moved
    assert bent[(1, 1)] > flat[(1, 1)]      # ρ<0 → 1-1 이 늘어난다


def test_p3_home_edge_only_through_h_league() -> None:
    """🔴🔴 **P3** — 홈 이점은 `h_league` **한 자리**로만 들어간다."""
    from app.core import probfloor as pf
    a, _w1 = pf.lambdas(diff=0.0, player_diff=0.0,
                        coef={**COEF, "h_league": 0.0})
    assert abs(a["home"] - a["away"]) < 1e-9, a
    b, _w2 = pf.lambdas(diff=0.0, player_diff=0.0, coef=COEF)
    assert b["home"] > b["away"]


def test_coef_comes_from_a_version_file() -> None:
    """🔴 계수는 **판 파일**이다(손값 금지 · §0). 없으면 🔴 사유 + 확률 미산출."""
    from app.core import probfloor as pf
    got, why = pf.load_coef(league="league:없는리그", as_of=AS_OF)
    assert got is None and "🔴" in why


def test_p1_one_place_makes_lambda() -> None:
    """🔴🔴 **P1** — ⑯ 에서 λ 를 만드는 식이 `probfloor` 하나다."""
    said = (ROOT / "app/core/probmodel.py").read_text(encoding="utf-8")
    import ast
    tree = ast.parse(said)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    code = ast.unparse(tree)
    # ⚠️ 승격 전까지 옛 식이 남는다 — 그러나 **새 식이 두 벌이 되는 것**은 막는다
    assert code.count("math.exp(m0 + rmove)") <= 1, "🔴 λ 식이 두 곳에 있다"
    assert "probfloor" in code


def test_fit_tool_exists_and_splits() -> None:
    """🔴 `tools/fit_probfloor.py` — 포아송 최대우도 · 판 저장 · E1 을 지난다."""
    said = (ROOT / "tools/fit_probfloor.py").read_text(encoding="utf-8")
    for want in ("rho", "h_league", "as_of", "versions_write", "b1"):
        assert want in said, want


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **§4 P4 · §9 S1** — 채택되지 않은 항은 λ 에 **닿지 않는다**
# ══════════════════════════════════════════════════════════════════
#
#  > 식(후보 항은 **채택된 것만** 남는다 — 미채택 항은 식에 없음)
#  > 계약 P4: `adopted=False` 항이 λ에 닿으면 실패.
#  > 계약 S1: 채택 판정 없이 항이 λ에 들어가면 실패.

FULL = {**COEF, "c1": 0.02, "c2": -0.01, "c5": -0.03, "c3": 0.3,
        "c4": 0.05, "c6": 0.1}
COV = {"diff": 0.6, "pdiff": 0.1, "rest_d": 7.0, "load_d": -3,
       "cup_d": -1, "pb_home": 1, "abs_d": -0.2, "form3_d": 0.33}


def test_terms_are_named_and_ordered() -> None:
    """🔴 후보 항 이름표가 있다 — 전진 선택이 **이 목록만** 흔든다."""
    from app.core import probfloor as pf
    assert tuple(pf.TERMS) == ("rest_d", "load_d", "cup_d", "pb_home",
                               "abs_d", "form3_d")


def test_p4_unadopted_terms_do_nothing() -> None:
    """🔴🔴 **P4·S1** — 채택 목록이 비면 λ 는 **바닥 식 그대로**다."""
    from app.core import probfloor as pf
    bare, _w1 = pf.lambdas(diff=0.6, player_diff=0.1, coef=FULL)
    got, why = pf.compute(COV, coef=FULL, adopted=set())
    assert abs(got["home"] - bare["home"]) < 1e-12, (got, bare, why)
    assert abs(got["away"] - bare["away"]) < 1e-12
    assert "채택 0" in why or "채택된 항 없음" in why


def test_adopted_term_moves_lambda_both_ways() -> None:
    from app.core import probfloor as pf
    base, _w = pf.compute(COV, coef=FULL, adopted=set())
    got, why = pf.compute(COV, coef=FULL, adopted={"rest_d"})
    # 🔴 홈이 더 쉬었으면(restΔ>0) 홈 λ 가 오르고 **원정 λ 가 내려간다**
    assert got["home"] > base["home"] and got["away"] < base["away"], why
    assert "rest_d" in why


def test_pb_home_scales_the_rating_gap() -> None:
    """🔴 §9 F1 — `pb_home` 은 **diff 의 설명력을 깎는다**(c3 상호작용)."""
    from app.core import probfloor as pf
    off = dict(COV, pb_home=0)
    on = dict(COV, pb_home=1)
    a, _w1 = pf.compute(off, coef=FULL, adopted={"pb_home"})
    b, why = pf.compute(on, coef=FULL, adopted={"pb_home"})
    # 🔴 diff>0 이므로 깎이면 홈 λ 가 **내려간다**
    assert b["home"] < a["home"], (a, b, why)


def test_contributions_are_reported_per_term() -> None:
    """🔴 §4 — `ProbOut` 이 적을 **항별 기여**(log λ 단위)를 함께 돌려준다."""
    from app.core import probfloor as pf
    got, why, parts = pf.compute(COV, coef=FULL, adopted={"rest_d", "load_d"},
                                 detail=True)
    assert set(parts) >= {"바닥", "홈 이점", "rest_d", "load_d"}
    assert abs(sum(v for k, v in parts.items()) - __import__("math").log(
        got["home"])) < 1e-9, parts
