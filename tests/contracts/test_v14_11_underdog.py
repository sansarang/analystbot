"""🔴🔴 **§11 역배 확률 · 보호 줄** — 지시서 2026-10-12(둘째) §11 · **즉시 적용**.

> 강팀 = 승 확률 높은 쪽(차 **3%p 미만 → "강팀 없음"**).
> 같은 격자에서: 약팀 승(역배)% · 강팀 미승% · 약팀 +0.5/+1.5/+2.5 생존% ·
> 약팀 더블찬스% · 약팀 DNB%.
> 카드 1겹 맨 위: *"강팀 울산 41% · 🔁 광주 승 33% · 울산 미승 59% · 광주 +1.5
> 84% · 광주 더블찬스 59%"*
> 계약 **U1**: 격자 합과 **소수 넷째 자리 일치**. **U2**: "강팀 없음"이 아니면
> **모든 카드에** 표시.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _grid():
    from app.core import probfloor as pf
    return pf.score_grid(lam_home=1.18, lam_away=1.60, rho=-0.08)


def test_favourite_is_the_higher_side() -> None:
    from app.core import underdog as ud
    got = ud.read(_grid(), home_name="광주", away_name="울산")
    assert got.fav == "away" and got.fav_name == "울산"
    assert got.dog == "home" and got.dog_name == "광주"


def test_no_favourite_within_three_points() -> None:
    """🔴 승 확률 차가 **3%p 미만**이면 `강팀 없음`이다."""
    from app.core import probfloor as pf
    from app.core import underdog as ud
    even = pf.score_grid(lam_home=1.35, lam_away=1.35, rho=-0.08)
    got = ud.read(even, home_name="A", away_name="B")
    assert got.fav == "" and "강팀 없음" in got.why


def test_u1_numbers_match_the_grid() -> None:
    """🔴🔴 **U1** — 모든 줄이 **그 격자**에서 나온다(소수 넷째 자리 일치)."""
    from app.core import probfloor as pf
    from app.core import underdog as ud
    grid = _grid()
    mk = pf.markets_of(grid)
    got = ud.read(grid, home_name="광주", away_name="울산")
    # 🔴 약팀(홈) 승 = 격자의 홈 승
    assert abs(got.dog_win - mk["home"]) < 1e-4
    # 🔴 강팀 미승 = 1 − 강팀 승
    assert abs(got.fav_nowin - (1.0 - mk["away"])) < 1e-4
    # 🔴 약팀 더블찬스 = 약팀 승 + 무
    assert abs(got.dog_dc - (mk["home"] + mk["draw"])) < 1e-4
    # 🔴 약팀 DNB = 약팀 승 / (약팀 승 + 강팀 승)
    assert abs(got.dog_dnb - (mk["home"] / (mk["home"] + mk["away"]))) < 1e-4
    # 🔴 핸디 생존도 같은 격자다
    assert abs(got.dog_ah[1.5] - mk["ah"]["home+1.5"]) < 1e-4


def test_handicap_lines_are_three() -> None:
    from app.core import underdog as ud
    got = ud.read(_grid(), home_name="광주", away_name="울산")
    assert sorted(got.dog_ah) == [0.5, 1.5, 2.5]


def test_line_reads_like_the_instruction() -> None:
    """🔴 카드 한 줄 — 지시의 **그 꼴**이다."""
    from app.core import underdog as ud
    said = ud.line(ud.read(_grid(), home_name="광주", away_name="울산"))
    for want in ("강팀 울산", "🔁", "광주 승", "울산 미승", "광주 +1.5",
                 "광주 더블찬스", "DNB"):
        assert want in said, (want, said)


def test_u2_every_card_shows_it() -> None:
    """🔴🔴 **U2** — 카드 렌더러가 그 줄을 **1겹 맨 위**에 낸다."""
    said = (ROOT / "app/core/render.py").read_text(encoding="utf-8")
    assert "underdog" in said
    i = said.index("def card_text")
    assert "_underdog_line" in said[i:i + 3000], "🔴 1겹에 그 줄이 없다"
