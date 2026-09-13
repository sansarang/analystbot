"""MBF-1 — 모델 확률을 운영 `jg` 에 붙인다 (3차 결정 F(C) + G).

🔴 **결정 F(C)**: 모델 확률은 **코드 쪽(`prob.py`)에만** 들어간다.
   Gemini 프롬프트는 종전·v3 어느 쪽도 건드리지 않는다.
🔴 **결정 G**: `p_code = p_market + Σadj + model_w·(p_model − p_market)`,
   `model_w = 0.0` 으로 시작한다 — **기록만 하고 발송 숫자에 영향이 없다.**
   상향은 300건 뒤 사용자 판정이다.

⚠️ 입력은 **이미 `jg` 에 붙어 있는 재료만** 쓴다(새로 수집하지 않는다).
   재료가 없으면 그 축은 사전값으로 대체하고 `missing` 에 적는다.
"""
import inspect
import json

import pytest

from app.model_baseball import forward as F


def _jg(**kw):
    base = {
        "sport": "mlb", "game_id": 1, "home": "H", "away": "A",
        "research": {
            "home_starter_recent": [{"innings": 6.0, "r": 2},
                                    {"innings": 5.0, "r": 4}],
            "away_starter_recent": [{"innings": 7.0, "r": 1}],
            "home_bullpen": {"최근3경기": {"실점": 6, "이닝": 12.0}},
            "away_bullpen": {"최근3경기": {"실점": 3, "이닝": 11.0}},
        },
    }
    base.update(kw)
    return base


# ── 재료 사용

def test_이미_붙어_있는_재료만_쓴다():
    """🔴 새로 수집하지 않는다 — DB·HTTP 를 부르지 않는다."""
    src = inspect.getsource(F)
    for bad in ("pool.fetch", "httpx", "sqlite3", "await "):
        assert bad not in src, bad


def test_선발_기록으로_축을_만든다():
    out = F.build(_jg())
    assert out["p_model"] is not None
    c = out["components"]
    assert c["sp_home"] > 0 and c["sp_away"] > 0
    # 원정 선발이 더 좋으니(1실점/7이닝) 원정 sp_ra9 가 더 낮다
    assert c["sp_away"] < c["sp_home"]


def test_재료가_없으면_사전값과_missing():
    out = F.build({"sport": "mlb", "home": "H", "away": "A"})
    assert out["p_model"] is not None
    assert "sp_home" in out["missing"] and "bp_home" in out["missing"], out["missing"]


def test_종목별_리그_득점을_설정에서_읽는다():
    """⚠️ 사본 금지 — 4.40·5.09·3.61 을 여기 적지 않는다."""
    src = inspect.getsource(F)
    for bad in ("4.40", "5.09", "3.61"):
        assert bad not in src, bad
    assert F.league_rpg("kbo") != F.league_rpg("npb")


# ── 결정 G: 가중치 0

def test_초기_가중치가_0이다():
    from app.engine import prob as P

    assert P.MODEL_W == 0.0


def test_가중치_0이면_p_code가_그대로다():
    """🔴 결정 G 완료 조건 — 항등이어야 한다."""
    from app.engine import prob as P

    adj = {"주전결장": -3.0}
    base = P.p_code(0.55, adj, "mlb")
    with_model = P.p_code(0.55, adj, "mlb", p_model=0.70)
    assert with_model == base


def test_가중치를_올리면_모델_쪽으로_당겨진다():
    from app.engine import prob as P

    out = P.p_code(0.50, {}, "mlb", p_model=0.60, model_w=0.5)
    assert out == pytest.approx(0.55, abs=1e-9)


def test_모델이_없으면_영향이_없다():
    from app.engine import prob as P

    assert P.p_code(0.55, {}, "mlb", p_model=None, model_w=1.0) == pytest.approx(0.55)


def test_괴리는_모델과_시장의_차이다():
    from app.engine import prob as P

    assert P.model_gap_pp(0.60, 0.55) == pytest.approx(5.0)
    assert P.model_gap_pp(None, 0.55) is None


# ── 배선·원장

def test_두_러너에_배선돼_있다():
    from app import pipeline as PL

    src = inspect.getsource(PL._attach_market_spine)
    assert "forward" in src and "p_model" in src, src[-600:]


def test_원장에_네_칸이_있다():
    s = open("db/schema.sql", encoding="utf-8").read()
    for col in ("p_model", "model_src", "model_w", "model_gap_pp"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in s, col


def test_프롬프트에_모델_숫자가_없다():
    """🔴 결정 F(C) — Gemini 는 모델 확률을 보지 않는다."""
    import pathlib
    import re

    # ⚠️ 낱말 경계로 본다 — `matchup_model` 이 `p_model` 을 품는다(무딘 계약 전례).
    pat = re.compile(r"\b(p_model|model_gap_pp|model_w)\b")
    for name in ("app/engine/prompts.py", "app/engine/verdict.py",
                 "app/engine/triage.py", "app/engine/dbref.py"):
        t = pathlib.Path(name).read_text(encoding="utf-8")
        assert not pat.search(t), (name, pat.search(t).group())
