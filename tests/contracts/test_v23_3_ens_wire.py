"""🔴🔴 **앙상블 배선 — ⑯ 안에서 격자로 섞는다**(C2).

> 채택되면 ⑯ 안 격자 혼합으로 배선(모든 시장 줄이 한 분포 — C2).
> (사용자 지시 2026-10-13 밤 다섯째 1번)

🔴 **판정**(누설 제거 뒤 2,582경기 · 규칙 v2+(d)): **E1 채택**
   — 로그 손실 **1.0498** vs E0 1.0525 · 짝지은 −0.0026(95% −0.0058~+0.0007) ·
   맥니마 p 0.1334 · 상위 20% 61.43% vs 60.85%.
   ⚠️ 방향은 **E0 가 낫다**(46.51% vs 47.37%) — 규칙 (b) 는 *"B 우세가 유의하지
   않으면 통과"* 이므로 통과했고, 그 사실을 카드가 적는다.
🔴 **EW1** — 혼합은 **격자**로 한다(승무패만 섞지 않는다) · **EW2** 판이 없으면
   **M1 단독**이고 사유를 적는다 · **EW3** 섞은 뒤의 승무패·오버·BTTS·핸디캡은
   **그 격자 하나**에서 나온다(`probfloor.markets_of`).
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_probmodel_blends_grids() -> None:
    """🔴🔴 **EW1 — 앙상블은 운영 경로에 없다**(사용자 지시 2026-10-17).

    ⚠️ 이 시험은 *"⑯ 이 `ensemble.of`(격자 혼합)를 부른다"*(2026-10-13 밤
       다섯째)를 세고 있었다. 🔴 앙상블은 **격자를 섞는 것**이고 그 격자는
       걷혔다 — `flat_prob`(1/3 균등 + 변수)이 승무패를 덮고 λ·오버·스코어는
       비운다. 실측으로 세어 **효과 0** 이었고 그 180줄을 지웠다.
    🔴 그래서 세는 것을 뒤집는다 — 운영이 **앙상블을 부르지 않는다**.
    ⚠️ `core/ensemble` 모듈은 **안 지웠다**(백필·비교가 읽는다).
    """
    from app.core import probmodel as pm
    said = ast.unparse(ast.parse(inspect.getsource(pm.run)))
    assert "ensemble" not in said, "🔴 운영이 앙상블을 다시 부른다"
    assert ".mix(" not in said


def test_markets_come_from_the_blended_grid() -> None:
    """🔴 **EW3** — 섞은 뒤 줄은 `_lines_from`(→ `markets_of`) 하나에서 온다.

    ⚠️ `run` 안에는 `market` 글자를 둘 수 없다(**C1**: S3 가 시장 정보를 읽는
       것을 막는 계약이 그 글자를 센다) — 그래서 **모듈 함수**로 뺐다.
    """
    # ⚠️ **전제가 바뀌었다**(2026-10-17) — 격자를 걷었으니 `run` 안에서 줄을
    #    만들지 않는다. 🔴 그래도 **그 함수가 제 일을 하는지는 그대로 센다**
    #    (백필·비교가 그것을 읽는다 · 운영이 안 부를 뿐이다).
    from app.core import probmodel as pm
    said = ast.unparse(ast.parse(inspect.getsource(pm.run)))
    assert "_lines_from" not in said, "🔴 운영이 격자 줄을 다시 만든다"
    inner = ast.unparse(ast.parse(inspect.getsource(pm._lines_from)))
    assert "markets_of" in inner


def test_ens_field_exists() -> None:
    """🔴 카드가 읽는 칸 — 무엇을 어떤 가중치로 섞었나."""
    from app.core import probmodel as pm
    assert "ens" in pm.ProbOut.__dataclass_fields__


def test_card_says_the_blend() -> None:
    """🔴 카드가 **앙상블 줄**을 적는다(판·가중치·방향 주의)."""
    said = _src("app/core/render.py")
    assert "앙상블" in said


def test_blend_matches_the_linear_mix() -> None:
    """🔴🔴 **EW1 의 근거** — 격자 혼합의 승무패 = 승무패 선형 혼합.

    🔴 그래서 적합·판정을 세 수로 한 것과 운영이 격자로 섞는 것이 **같은 답**이다.
    """
    from app.core import ensemble as en
    from app.core import probfloor as pf
    g1 = pf.score_grid(lam_home=1.6, lam_away=1.1, rho=0.0)
    g2 = pf.score_grid(lam_home=1.2, lam_away=1.4, rho=0.0)
    n1, _w1 = en.normalise(g1)
    n2, _w2 = en.normalise(g2)
    got, why = en.of({"M1": n1, "M3": n2},
                     plate={"w": {"M1": 0.5, "M3": 0.5}})
    assert got, why
    a = pf.markets_of(got)
    b, _w = en.mix({"M1": [pf.markets_of(n1)[k] for k in
                          ("home", "draw", "away")],
                    "M3": [pf.markets_of(n2)[k] for k in
                           ("home", "draw", "away")]},
                   {"M1": 0.5, "M3": 0.5})
    for i, k in enumerate(("home", "draw", "away")):
        assert abs(a[k] - b[i]) < 1e-9, (k, a[k], b[i])


def test_no_plate_means_m1_alone() -> None:
    """🔴 **EW2** — 판이 없으면 섞지 않는다(사유를 남긴다)."""
    from app.core import ensemble as en
    got, why = en.of({"M1": {(0, 0): 1.0}}, plate={})
    assert not got and "판이 없다" in why
