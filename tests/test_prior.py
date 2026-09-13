"""PRI-1 — 사전값(티어 + 올해 성적). 지시문 Phase 2.

🔴 **사전값은 검색 전에 확정한다.** 검색 후 적으면 뉴스 어조에 끌린다
   (지시문 0. 핵심 원칙).
🔴 **p_prior 는 `p_code` 에 더하지 않는다**(3차 결정 G: model_w=0).
   게이트(Phase 3)와 서술에만 쓴다. 계약이 그 격리를 잠근다.
"""
import math

import pytest

from app.engine import prior as P


# ── 가중치

def test_경기가_없으면_티어가_전부다():
    assert P.w_tier(0) == 1.0


def test_열두경기부터는_티어가_0_3이다():
    assert P.w_tier(12) == pytest.approx(0.3)
    assert P.w_tier(30) == pytest.approx(0.3)


def test_그_사이는_선형이다():
    assert P.w_tier(6) == pytest.approx(0.5)


# ── 티어 표

def test_티어_상수는_지시문_그대로다():
    assert P.TIER_ELO == {1: 1700, 2: 1620, 3: 1560, 4: 1510, 5: 1460}


def test_미기입_팀은_중앙_3이고_그_사실이_남는다():
    """🔴 Claude Code 가 티어를 추측해 채우지 않는다 — 빈 칸은 빈 칸이다."""
    e, src = P.team_elo(None, w=0, d=0, lose=0)
    assert e == P.TIER_ELO[3]
    assert src == "tier:미기입"


def test_승격팀은_5다():
    e, _ = P.team_elo(5, w=0, d=0, lose=0)
    assert e == 1460


# ── 올해 성적 섞기

def test_성적이_쌓이면_티어에서_멀어진다():
    full = P.team_elo(1, w=12, d=0, lose=0)[0]      # 12경기 전승
    none = P.team_elo(1, w=0, d=0, lose=0)[0]
    assert full > none, (full, none)
    # pts_rate 1.0 → elo_this 1900 · w_tier 0.3 → 0.3*1700 + 0.7*1900
    assert full == pytest.approx(0.3 * 1700 + 0.7 * 1900)


def test_전패면_티어보다_낮아진다():
    assert P.team_elo(1, w=0, d=0, lose=12)[0] == pytest.approx(
        0.3 * 1700 + 0.7 * 1400)


# ── 축구 3-way

def test_축구는_홈어드밴티지_60이다():
    h, dr, a = P.soccer_prior(1560, 1560)
    assert h > a, (h, a)          # 홈 이점
    assert h + dr + a == pytest.approx(1.0, abs=1e-9)


def test_무승부는_격차가_클수록_작아진다():
    _, d_even, _ = P.soccer_prior(1560, 1560)
    _, d_gap, _ = P.soccer_prior(1700, 1460)
    assert d_gap < d_even


def test_무승부는_상하한_안이다():
    for dh in (0, 100, 300, 600, 1000):
        _, d, _ = P.soccer_prior(1560 + dh, 1560)
        assert 0.10 - 1e-9 <= d <= 0.34 + 1e-9, (dh, d)


# ── 야구 2-way

def test_야구는_홈어드밴티지_25이고_절사된다():
    assert P.baseball_prior(1560, 1560) > 0.5
    assert P.baseball_prior(2500, 1000) == pytest.approx(0.68)
    assert P.baseball_prior(1000, 2500) == pytest.approx(0.32)


# ── 최근 폼 보정

@pytest.mark.parametrize("last5,delta", [
    ("WWWWW", +4.0), ("LLLLL", -4.0),
    ("WWWWD", +4.0),          # 무패
    ("LLLLD", -4.0),          # 무승
    ("WWWLL", 0.0), ("WDLWD", 0.0), ("", 0.0), ("WWW", 0.0),
])
def test_폼_보정은_극단일_때만_준다(last5, delta):
    assert P.form_pp(last5) == pytest.approx(delta)


# ── 격리

def test_p_prior는_p_code에_들어가지_않는다():
    """🔴 지시문 금지 사항 — 게이트·서술용으로만 쓴다."""
    import inspect

    from app.engine import prob

    assert "p_prior" not in inspect.getsource(prob.p_code)
    assert "p_prior" not in inspect.getsource(prob.p_send)


def test_원장에_두_칸이_있다():
    s = open("db/schema.sql", encoding="utf-8").read()
    for col in ("p_prior", "prior_src"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in s, col


# ── 티어 파일

def test_리그별_티어_파일이_전부_있다():
    """🔴 목록을 손으로 적지 않는다 — `leagues.LEAGUES` + 야구 3종목."""
    from pathlib import Path

    from app.leagues import LEAGUES

    want = set(LEAGUES) | {"mlb", "kbo", "npb"}
    have = {p.stem for p in Path("config/tiers").glob("*.yaml")}
    assert want <= have, want - have


def test_티어_파일의_팀은_우리_표기다():
    """골격은 운영 DB 표기로 만들었다. 값은 비어 있어도 된다."""
    t = P.load_tiers("la_liga")
    assert "FC Barcelona" in t and "RC Celta de Vigo" in t
