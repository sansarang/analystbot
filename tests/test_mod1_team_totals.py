"""[MOD-1] ⑪이 쓸 확률 — 팀토탈이 같은 분포에서 나오는데 안 내고 있었다.

🔴 실측 2026-09-19: `mlb_market_probs` 가 내는 키는
     ['f5', 'h2h', 'lambda', 'spreads', 'totals']
   **팀토탈이 없다.** 그런데 그 함수는 이미 `score_pmf(lam_away)` 를 갖고 있다 —
   원정 팀토탈 언더 3.5 는 그 분포에서 `P(X ≤ 3)` 이다. 새 가정이 0이다.
🔴 λ 자체는 이미 선다(`mlb_lambdas`, 실측 `missing=[]`):
     g10085 λ home=3.486 away=4.378
   그런데 야구는 파이프라인이 λ 경로를 **통째로 건너뛴다**
   (`pipeline.py:3763  if sport in BASEBALL_SPORTS: ... continue`, SEND-1 결정
   B-1 2026-09-13). 그래서 `pick_ledger.model_probs` 가 1,382행 전건 NULL 이고
   ⑪의 구조 후보가 0 이었다.
⚠️ 옛 발송 경로의 그 결정을 **되돌리지 않는다.** v1.4 흐름에서 따로 계산한다.
"""
from __future__ import annotations

import pytest


def test_팀토탈이_나온다():
    from app.engine.scoring import mlb_market_probs

    p = mlb_market_probs(4.0, 4.5, lines={"team_totals": [3.5, 4.5]})
    assert "team_totals" in p, sorted(p)
    tt = p["team_totals"]
    assert set(tt) >= {"home", "away"}, tt
    assert set(tt["away"][3.5]) == {"Over", "Under"}, tt["away"][3.5]


def test_팀토탈은_그_팀_분포에서_나온다():
    """🔴 λ 가 클수록 언더 확률이 낮아진다 — 같은 분포를 쓴다는 증거다."""
    from app.engine.scoring import mlb_market_probs

    low = mlb_market_probs(4.0, 2.5, lines={"team_totals": [3.5]})["team_totals"]
    high = mlb_market_probs(4.0, 6.0, lines={"team_totals": [3.5]})["team_totals"]
    assert low["away"][3.5]["Under"] > high["away"][3.5]["Under"]
    # 홈은 둘 다 λ=4.0 이라 같아야 한다
    assert low["home"][3.5]["Under"] == high["home"][3.5]["Under"]


def test_오버언더_합이_1이다():
    from app.engine.scoring import mlb_market_probs

    tt = mlb_market_probs(4.0, 4.5, lines={"team_totals": [3.5]})["team_totals"]
    for side in ("home", "away"):
        d = tt[side][3.5]
        assert abs(d["Over"] + d["Under"] - 1.0) < 1e-6, d


def test_정수_라인을_기본으로_만들지_않는다():
    """⚠️ 반 점 라인만 — 정수는 푸시가 생겨 오버/언더 합이 1이 아니다
       (`_default_total_lines` 머리말과 같은 이유)."""
    from app.engine.scoring import mlb_market_probs

    tt = mlb_market_probs(4.0, 4.5)["team_totals"]
    for line in tt["home"]:
        assert abs(float(line) * 2 % 2) == 1.0, line


@pytest.mark.asyncio
async def test_흐름이_파생확률을_스스로_만든다():
    """🔴 원장이 비어 있어도 ⑪이 쓸 확률이 있어야 한다."""
    from app.flow.bridge import model_probs_from_cache

    jg = {"sport": "mlb", "home": "H", "away": "A",
          "research": {"home_offense": {"xwoba": 0.320},
                       "away_offense": {"xwoba": 0.330}}}
    got = model_probs_from_cache(jg, lines={"team_totals": [3.5]})
    assert got and "team_totals" in got, got
    assert got["lambda"]["home"] > 0
