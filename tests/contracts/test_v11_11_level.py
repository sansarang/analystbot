"""🔴🔴 **ⓒ 대회 수준 — 폼 창은 리그 경기만** (사용자 지시 2026-10-12).

> ⓒ 대회 수준: 폼 창은 **리그 경기만**이 기본. 컵은 상대가 **같은 리그면 포함**,
> **하위 리그 상대면 제외**(또는 상대 Elo 보정 후 가중 0.5). 창에서 뺀 경기를
> **사유에 적는다**.

🔴 왜 — 실측 2026-10-12(가와사키–나고야): 가와사키 창 9경기 중 **3경기가 컵**
   (`Tochigi SC 3-1[Cup]`·`Roasso Kumamoto[League Cup]`·`Tegevajaro Miyazaki
   2-0[Cup]`)이었고 상대가 **하위 리그**였다. 그 득점이 폼을 끌어올려 축1 이
   +1.085(강)로 섰다.
"""
from __future__ import annotations


def _row(league: str, opp: str, *, gf: int = 2, ga: int = 0) -> dict:
    return {"league": league, "opp": opp, "gf": gf, "ga": ga,
            "side": "home", "date": "2026-09-01"}


def test_league_rows_are_kept() -> None:
    from app.core import level
    rows = [_row("J. League", "Kashima Antlers")]
    got, why = level.keep(rows, league="J. League", elo={})
    assert len(got) == 1 and not why


def test_cup_vs_lower_side_is_dropped() -> None:
    """🔴 컵 + **하위 리그 상대** → 창에서 뺀다(사유를 적는다)."""
    from app.core import level
    rows = [_row("Cup", "Tegevajaro Miyazaki"),
            _row("J. League", "Kashima Antlers")]
    got, why = level.keep(rows, league="J. League", elo={})
    assert len(got) == 1, got
    assert "Tegevajaro" in why and "뺐다" in why


def test_cup_vs_same_league_is_kept() -> None:
    """✅ 컵이라도 상대가 **같은 리그**면 센다(Elo 로 안다)."""
    from app.core import level
    rows = [_row("Cup", "Kashima Antlers")]
    got, why = level.keep(rows, league="J. League",
                          elo={"Kashima Antlers": 1600.0})
    assert len(got) == 1, (got, why)
    assert "같은 리그" in why or not why


def test_weight_half_option_is_named() -> None:
    """🔴 지시의 다른 길 — *"상대 Elo 보정 후 가중 0.5"*. 🔴 임시값으로 둔다."""
    from app.core import level
    assert level.CUP_WEIGHT == 0.5


def test_dropped_rows_are_reported_not_silent() -> None:
    """🔴 #3 — 뺀 경기를 **이름으로** 남긴다(조용한 0 금지)."""
    from app.core import level
    rows = [_row("Cup", "A"), _row("League Cup", "B"),
            _row("J. League", "C")]
    got, why = level.keep(rows, league="J. League", elo={})
    assert len(got) == 1
    assert "2경기" in why and "A" in why and "B" in why


def test_form_window_uses_it() -> None:
    """🔴 배선 — ⑧ 의 폼 창이 그 문을 지난다."""
    from pathlib import Path
    said = (Path(__file__).resolve().parents[2]
            / "app/core/stages/s2e_matchup.py").read_text(encoding="utf-8")
    assert "level.keep" in said or "_level.keep" in said


def test_unknown_league_keeps_everything() -> None:
    """⚠️ 그 경기의 리그를 모르면 **아무것도 빼지 않는다**(#4 추측 금지)."""
    from app.core import level
    rows = [_row("Cup", "A"), _row("J. League", "C")]
    got, why = level.keep(rows, league="", elo={})
    assert len(got) == 2, got
    assert "모른다" in why
