"""🔴🔴 **확률 요약 — 카드 맨 위 고정 블록**(사용자 지시 2026-10-13).

> 카드 맨 위에 "확률 요약" 고정 블록을 둔다 — 승무패 · 핸디 양쪽 ±0.5/1.5/2.5 ·
> 오버/언더 0.5~4.5 를 **표 3개**로. 터미널 폭 때문에 줄이 잘리지 않게 표로
> 출력하고, **잘린 칸이 하나라도 있으면 출력 실패** 처리.

🔴 **SM1** 블록이 카드 **맨 위**(머리 다음 · 역배 줄보다 앞)다 · **SM2** 표가
   **셋**이고 핸디는 양쪽 **여섯 칸**·총골은 **다섯 칸**이다 · **SM3** 줄 폭이
   상한 안이다 · **SM4** 잘림 글자가 하나라도 있으면 **`CardCut`**(출력 실패) ·
   **SM5** 격자가 없어도 **표를 그린다**(칸마다 ⬜ + 사유) · **SM6** 수는
   표준 확률 블록과 **같은 격자**에서 온다.
"""
from __future__ import annotations

import pytest


def _ref():
    from app.core.schema import MatchRef
    return MatchRef(id="m", sport="soccer",
                    competition="AFC Champions League Elite",
                    competition_short="ACLE", home="team:999901",
                    away="team:999902", home_name="HOME", away_name="AWAY",
                    kickoff_utc="2026-10-13T10:00:00Z")


def _card(with_grid: bool):
    from app.core import probfloor as pf
    from app.core.schema import Card, Facts
    card = Card(match=_ref(), facts=Facts(), conclusion="🔴 미산출")
    if not with_grid:
        return card
    grid = pf.score_grid(lam_home=1.345, lam_away=1.550, rho=0.0)
    said = {f"{h}-{a}": v for (h, a), v in grid.items()}
    return card.model_copy(update={"matchup": {"sim": {
        "home": 0.33, "draw": 0.247, "away": 0.422,
        "lam": {"home": 1.345, "away": 1.55}, "scores": said,
        "why": "시험"}}})


def test_sm1_block_is_at_the_top() -> None:
    """🔴 **SM1** — 머리 바로 다음이고 역배 줄보다 **앞**이다."""
    import inspect

    from app.core import render
    said = inspect.getsource(render.card_text)
    i = said.index("prob_summary(card)")
    j = said.index("_underdog_line(card)")
    assert i < j, "🔴 확률 요약이 역배 줄보다 뒤에 있다"
    assert said.index("_head(card)") < i


def test_sm2_three_tables_with_the_right_columns() -> None:
    from app.core import render
    said = render.prob_summary(_card(True))
    # ⚠️ 구분선은 **줄로** 센다 — `"|---"` 글자 수를 세면 한 줄에서 여러 번
    #    맞는다(내 계약이 그 함정을 밟았다: 3 이 아니라 17 이 나왔다).
    bars = [ln for ln in said.splitlines() if set(ln) <= set("|- ")
            and ln.startswith("|")]
    assert len(bars) == 3, bars
    for one in ("| 승무패 |", "| 핸디 |", "| 총골 |"):
        assert one in said, one
    ah = [ln for ln in said.splitlines() if ln.startswith("| 홈 |")][0]
    assert len(ah.strip().strip("|").split("|")) == 1 + len(render.AH_LINES)
    ou = [ln for ln in said.splitlines() if ln.startswith("| 오버 |")][0]
    assert len(ou.strip().strip("|").split("|")) == 1 + len(render.OU_LINES)


def test_sm3_lines_fit_the_width() -> None:
    from app.core import render
    said = render.prob_summary(_card(True))
    for ln in said.splitlines():
        assert len(ln) <= render.CUT_WIDTH, (len(ln), ln)


def test_sm4_truncation_is_an_output_failure() -> None:
    """🔴🔴 **SM4** — 잘린 칸이 하나라도 있으면 **출력 실패**다."""
    from app.core import render
    with pytest.raises(render.CardCut):
        render.check("| 핸디 | -2.5 | -1.5 |\n|---|---|---|\n| 홈 | 5.2%…(잘림) |")
    with pytest.raises(render.CardCut):
        render.check("| 홈 | " + " | ".join(["12.3%"] * 30) + " |")
    with pytest.raises(render.CardCut):
        render.check("| 핸디 | a | b |\n|---|---|---|\n| 홈 | 1 |")


def test_sm5_empty_grid_still_draws_the_tables() -> None:
    from app.core import render
    said = render.prob_summary(_card(False))
    bars = [ln for ln in said.splitlines() if set(ln) <= set("|- ")
            and ln.startswith("|")]
    assert len(bars) == 3, bars
    assert said.count("⬜") >= 16 and "칸이 비었다" in said


def test_sm6_same_numbers_as_the_standard_block() -> None:
    """🔴 **SM6** — 두 블록이 **같은 격자**를 말한다(두 줄이 다르면 안 된다)."""
    from app.core import render
    card = _card(True)
    top = render.prob_summary(card)
    body = render.prob_block(card)
    said = [ln for ln in top.splitlines() if ln.startswith("| 확률 |")][0]
    for one in said.strip().strip("|").split("|")[1:]:
        assert one.strip() in body, one
