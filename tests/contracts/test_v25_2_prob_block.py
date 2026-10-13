"""🔴🔴 **표준 확률 블록** — 수정 지시 2026-10-13 2번·6번.

> 2. 카드에 반드시 들어갈 확률 블록(세 장 모두 같은 틀 · **값 없으면 칸은 그리고
>    ⬜ + 사유**) … 6. 위 2번 확률 블록을 **카드 표준으로 고정**(대회 무관).
>    블록이 빠진 카드는 **출력 단계에서 실패 처리**하는 계약 테스트 추가.

🔴 **PB1** 긴 카드에 그 블록이 있다 · **PB2** 줄 이름 **전부**가 있다(격자가
   없어도) · **PB3** 격자가 없으면 칸마다 **⬜ + 사유** · **PB4** 핸디는 양쪽
   **여섯 줄씩** · 오버/언더는 **다섯 줄** · **PB5** 블록에 **시장·배당 글자가
   없다**.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _card(with_grid: bool):
    from app.core.schema import Card, Facts, MatchRef
    ref = MatchRef(id="m", sport="soccer",
                   competition="AFC Champions League Elite",
                   competition_short="ACLE", home="team:999901",
                   away="team:999902", home_name="HOME", away_name="AWAY",
                   kickoff_utc="2026-10-13T10:00:00Z")
    card = Card(match=ref, facts=Facts(), conclusion="🟡 조건부 — …")
    if not with_grid:
        return card
    from app.core import probfloor as pf
    grid = pf.score_grid(lam_home=1.5, lam_away=1.1, rho=0.0)
    said = {f"{h}-{a}": v for (h, a), v in grid.items()}
    return card.model_copy(update={"matchup": {
        "sim": {"home": 0.5, "draw": 0.25, "away": 0.25,
                "lam": {"home": 1.5, "away": 1.1}, "scores": said,
                "why": "시험"},
        "shadow": {"home": 0.45, "draw": 0.27, "away": 0.28},
        "floor": {"home": 0.4, "draw": 0.3, "away": 0.3}}})


def test_pb1_block_is_in_the_long_card() -> None:
    said = (ROOT / "app/core/render.py").read_text(encoding="utf-8")
    assert "prob_block(card)" in said


def test_pb2_every_row_exists_with_a_grid() -> None:
    from app.core import render
    said = render.prob_block(_card(True))
    for name in render.PROB_ROWS:
        assert f"**{name}**" in said, (name, said[:200])


def test_pb3_every_row_exists_without_a_grid() -> None:
    """🔴🔴 **PB3** — 격자가 없어도 **칸은 그린다**(⬜ + 사유)."""
    from app.core import render
    said = render.prob_block(_card(False))
    for name in render.PROB_ROWS:
        assert f"**{name}**" in said, (name, said[:200])
    assert said.count("⬜") >= 10, said


def test_pb4_handicap_and_total_lines() -> None:
    from app.core import render
    said = render.prob_block(_card(True))
    for line in ("-2.5", "-1.5", "-0.5", "+0.5", "+1.5", "+2.5"):
        assert line in said, line
    for one in ("0.5 오버", "1.5 오버", "2.5 오버", "3.5 오버", "4.5 오버"):
        assert one in said, one
    assert render.AH_LINES == (-2.5, -1.5, -0.5, 0.5, 1.5, 2.5)
    assert render.OU_LINES == (0.5, 1.5, 2.5, 3.5, 4.5)


def test_pb5_no_market_or_odds_words() -> None:
    """🔴 **PB5** — 이 블록에 **시장·배당**이 없다(예측 지시 §0)."""
    from app.core import render
    said = render.prob_block(_card(True))
    for bad in ("배당", "시장", "북메이커", "오즈"):
        assert bad not in said, bad


def test_pb6_shadow_has_four_plates() -> None:
    from app.core import render
    said = render.prob_block(_card(True))
    for nm in ("M1(운영)", "E1", "M3", "Elo"):
        assert nm in said, nm
