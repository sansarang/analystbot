"""🔴🔴 **§8 앙상블**(통합 지시서 2026-10-13 밤).

> `G = Σ w_k·G_k` (`w_k ≥ 0`, `Σ=1`) → **모든 시장 줄은 G 하나에서**.
> 대조 판: 승무패만 평균한 값 — 격자 혼합과 **같은지** 확인.
> 계약 **EN2** 판 없이 섞으면 실패 · **EN3** 합=1(소수 여섯째) · **EN4** 0-0 0건
> 실패 · **EN6** 미정규화 격자 실패 · **EN7** 음수·합≠1 실패.
"""
from __future__ import annotations

from datetime import datetime, timezone

UTC = timezone.utc


def _grid(h: float, a: float) -> dict:
    from app.core import probfloor as pf
    return pf.score_grid(lam_home=h, lam_away=a, rho=0.0)


def test_en3_blend_sums_to_one() -> None:
    from app.core import ensemble as en
    got, why = en.blend([_grid(1.5, 1.1), _grid(1.1, 1.5)], [0.6, 0.4])
    assert abs(sum(got.values()) - 1.0) < 1e-6, (sum(got.values()), why)
    assert "w" in why


def test_en7_bad_weights_are_refused() -> None:
    from app.core import ensemble as en
    one = _grid(1.4, 1.2)
    for bad in ([0.5, 0.4], [1.2, -0.2], [0.0, 0.0]):
        got, why = en.blend([one, one], bad)
        assert got == {} and "🔴" in why, (bad, why)


def test_en4_the_grid_has_zero_zero() -> None:
    """🔴🔴 **EN4** — `0-0` 칸이 **없으면 실패**다(그 병으로 무승부가 덜 세졌다)."""
    from app.core import ensemble as en
    got, _why = en.blend([_grid(1.4, 1.2)], [1.0])
    assert (0, 0) in got and got[(0, 0)] > 0


def test_en6_unnormalised_grid_is_refused() -> None:
    """🔴 **EN6** — 합이 1 이 아닌 격자를 받으면 **섞지 않는다**(꼬리를 적고 정규화)."""
    from app.core import ensemble as en
    said = {(0, 0): 0.4, (1, 0): 0.4}        # 합 0.8
    got, why = en.blend([said], [1.0])
    assert got == {} and "정규" in why


def test_normalise_records_the_tail() -> None:
    """🔴 0~10골로 자르고 **꼬리를 적은 뒤** 정규화한다(몰래 버리지 않는다)."""
    from app.core import ensemble as en
    got, why = en.normalise(_grid(3.0, 3.0))
    assert abs(sum(got.values()) - 1.0) < 1e-9
    assert "꼬리" in why and all(h <= en.MAXG and a <= en.MAXG
                                 for h, a in got)


def test_markets_come_from_the_blended_grid_only() -> None:
    """🔴 승무패 **대조 판** — 확률만 평균한 값과 격자 혼합이 **같다**."""
    from app.core import ensemble as en
    from app.core import probfloor as pf
    g1, g2 = _grid(1.6, 1.0), _grid(1.0, 1.6)
    mixed, _w = en.blend([g1, g2], [0.7, 0.3])
    mk = pf.markets_of(mixed)
    m1, m2 = pf.markets_of(g1), pf.markets_of(g2)
    for key in ("home", "draw", "away"):
        assert abs(mk[key] - (0.7 * m1[key] + 0.3 * m2[key])) < 1e-9, key


def test_en2_no_plate_no_blend() -> None:
    """🔴🔴 **EN2** — 가중치 **판이 없으면 섞지 않는다**(M1 단독 + 사유)."""
    from app.core import ensemble as en
    got, why = en.plate_of(league="league:J1",
                           as_of=datetime(2000, 1, 1, tzinfo=UTC))
    assert got == {} and "🔴" in why
    said, why2 = en.of({"M1": _grid(1.4, 1.2), "M3": _grid(1.2, 1.4)},
                       plate={})
    assert said == {} and "🔴" in why2 and "판" in why2


def test_of_uses_the_plate_weights() -> None:
    from app.core import ensemble as en
    from app.core import probfloor as pf
    box = {"M1": _grid(1.6, 1.0), "M3": _grid(1.0, 1.6)}
    got, why = en.of(box, plate={"w": {"M1": 0.8, "M3": 0.2}})
    mk = pf.markets_of(got)
    m1 = pf.markets_of(box["M1"])
    assert mk["home"] < m1["home"], (mk, m1)
    assert "M1 0.80" in why
    # 🔴 구성 격자가 하나라도 없으면 **섞지 않는다**(재정규화 금지 · §9)
    said, why2 = en.of({"M1": box["M1"]}, plate={"w": {"M1": 0.8,
                                                      "M3": 0.2}})
    assert said == {} and "누락" in why2


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **§11 운영 실전 대조 — 그림자 기록**(확률·등급 불변)
# ══════════════════════════════════════════════════════════════════
#
#  > 지금부터 운영 카드마다 **E1·E2(최신 판)·seasonfix 후보 확률**을 그림자로 기록.
#  > `score_cards` **30경기마다**: 운영·B·M3·Elo·E1·E2 — 로그 손실·방향·상위 20%…
#  🔴 **E0 유지**(채택 없음)이므로 이 수는 **운영 확률이 아니다** — 기록·채점용이다.
#  🔴 **EN8** — 그림자·구성 확률이 **등급·생존에 닿으면 실패**.

def test_mix_triples_is_linear_and_checked() -> None:
    from app.core import ensemble as en
    got, why = en.mix({"M1": [0.5, 0.3, 0.2], "M3": [0.3, 0.3, 0.4]},
                      {"M1": 0.5, "M3": 0.5})
    assert [round(x, 6) for x in got] == [0.4, 0.3, 0.3], (got, why)
    # 🔴 구성 확률이 빠지면 **섞지 않는다**(재정규화 금지)
    said, why2 = en.mix({"M1": [0.5, 0.3, 0.2]}, {"M1": 0.5, "M3": 0.5})
    assert said == [] and "누락" in why2


def test_card_prints_the_shadow_line() -> None:
    from pathlib import Path
    said = (Path(__file__).resolve().parents[2]
            / "app/core/render.py").read_text(encoding="utf-8")
    assert "앙상블 그림자" in said
    assert "E1" in said and "E2" in said


def test_en8_shadow_cannot_touch_grade_or_survival() -> None:
    """🔴🔴 **EN8** — 판정·생존 코드에 `ensemble`·그림자 이름이 **없다**."""
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    for rel in ("app/core/stages/s7_judge.py", "app/core/survive.py",
                "app/core/bands.py"):
        path = root / rel
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if (isinstance(body, list) and body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
        code = ast.unparse(tree)
        for bad in ("ensemble", "shadow", "ens_shadow"):
            assert bad not in code, (rel, bad)


def test_score_cards_reads_the_shadow_line() -> None:
    from pathlib import Path
    said = (Path(__file__).resolve().parents[2]
            / "tools/score_cards.py").read_text(encoding="utf-8")
    assert "ENS" in said and "E1" in said
