"""PROB-1 — 확률 뼈대를 시장으로. 조정은 코드가, 서술만 LLM이.

사용자 결정 2026-09-13(결정 1): `p = 시장 확률(디빅) → 검증된 변수로 코드가
±%p → LLM은 서술만`. **(b)·(c) 금지 — LLM 프롬프트에 배당·시장확률·괴리
숫자를 넣지 않는다.**

🔴 운영 원장 178경기: 판정 확률 AUC 0.5122·브라이어 0.2537(50%로 찍는 것보다
   나쁘다) vs 시장 확률 AUC 0.6421·브라이어 0.2394(유일하게 유의).
   Elo 는 AUC 0.440~0.477 이라 대체재가 될 수 없다.
"""
import inspect
import json

import pytest

from app.engine import prob as P


# ── ① 시장 확률

def test_시장확률은_디빅된_값을_쓴다():
    """⚠️ 사본 금지 — 마진 제거는 `_market_probs`·`implied_probs` 가 이미 한다."""
    src = inspect.getsource(P)
    assert "1.0 / " not in src and "1/odds" not in src, "디빅을 다시 구현했다"


@pytest.mark.parametrize("probs,home,away,expect", [
    ({"A": 0.55, "B": 0.45}, "A", "B", 0.55),
    ({"A": 0.40, "B": 0.60}, "A", "B", 0.40),
    ({}, "A", "B", None),
    (None, "A", "B", None),
    ({"A": 0.55}, "A", "B", None),          # 한쪽만 있으면 못 쓴다
])
def test_홈_시장확률을_고른다(probs, home, away, expect):
    assert P.p_market(probs, home, away, "mlb") == expect


def test_축구는_세_값을_모두_본다():
    probs = {"H": 0.45, "Draw": 0.28, "A": 0.27}
    assert P.p_market(probs, "H", "A", "soccer") == 0.45
    assert P.market_triple(probs, "H", "A") == (0.45, 0.28, 0.27)


# ── ② 조정

def test_야구_조정_상한():
    """결정 1-2 표 그대로. 상한을 넘지 않는다."""
    jg = {"sport": "mlb", "starter_changed": True,
          "out_starters": 9, "bullpen_b2b": 9, "trip_day": 5}
    adj = P.adjustments(jg)
    assert adj["선발변경"] == -6.0 or adj["선발변경"] == 6.0
    assert adj["주전결장"] == -5.0          # 1명당 -1.5, 상한 -5
    assert adj["필승조연투"] == -3.0        # 1명당 -1, 상한 -3
    assert adj["이동연전"] == -1.0


def test_축구_조정_상한():
    jg = {"sport": "soccer", "out_starters": 9, "out_keyman": True,
          "rest_days": 2, "midweek_away": True}
    adj = P.adjustments(jg)
    assert adj["주전결장"] == -6.0          # 1명당 -1.5, 상한 -6
    assert adj["핵심결장"] == -2.0
    assert adj["짧은휴식"] == -2.0
    assert adj["주중원정"] == -2.0


def test_조정이_없으면_빈_dict():
    assert P.adjustments({"sport": "mlb"}) == {}


def test_종목표를_분기문으로_적지_않는다():
    """⚠️ 변수 표는 한 곳에 있고 종목으로 조회한다."""
    assert set(P.ADJ_RULES) == {"baseball", "soccer"}


# ── ③ p_code

def test_시장이_없으면_코드확률도_없다():
    """🔴 Elo 로 대체하지 않는다 — AUC 0.44~0.48, 혼합하면 더 나빠진다."""
    out = P.p_code(None, {"주전결장": -3.0}, "mlb")
    assert out is None


def test_조정을_퍼센트포인트로_더한다():
    out = P.p_code(0.55, {"주전결장": -3.0, "이동연전": -1.0}, "mlb")
    assert out == pytest.approx(0.51, abs=1e-9)


def test_승률_상한을_넘지_않는다():
    """기존 클립(야구 0.32~0.68)을 그대로 쓴다."""
    assert P.p_code(0.66, {"선발변경": 6.0}, "mlb") == pytest.approx(0.68)
    assert P.p_code(0.34, {"주전결장": -5.0}, "mlb") == pytest.approx(0.32)


def test_elo가_끼어들지_않는다():
    """🔴 실제 **사용**을 막는다. 주석에 '왜 안 쓰는지' 적는 것은 허용한다 —
    그 실측(AUC 0.440~0.477)이 코드에서 떨어지면 다음 사람이 Elo 를 붙인다."""
    src = inspect.getsource(P)
    for bad in ("team_elo", "import elo", "elo_payload", "from app.models"):
        assert bad not in src, bad


# ── ④ 배당이 LLM 프롬프트로 새지 않는다

def test_프롬프트에_배당_숫자가_없다():
    """🔴 결정 1의 완료 조건. (b)·(c) 금지."""
    import pathlib

    bad = []
    for name in ("app/engine/prompts.py", "app/engine/verdict.py",
                 "app/engine/triage.py"):
        t = pathlib.Path(name).read_text(encoding="utf-8")
        for kw in ("p_market", "market_prob", "divergence_pp",
                   "best_odds", "odds_at_verdict", "p_code"):
            if kw in t:
                bad.append((name, kw))
    assert bad == [], bad


def test_판정_모듈이_prob를_읽지_않는다():
    """⚠️ 확률은 판정 **뒤에** 붙는다. 판정이 이 값을 보면 (b)가 된다."""
    for name in ("app/engine/verdict.py", "app/engine/triage.py"):
        t = open(name, encoding="utf-8").read()
        assert "engine.prob" not in t and "import prob" not in t, name


# ── ⑤ 원장

def test_원장에_세_칸이_있다():
    src = open("db/schema.sql", encoding="utf-8").read()
    for col in ("p_market", "p_code", "adj_pp"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in src, col


def test_adj_pp는_JSON이다():
    out = P.adj_json({"주전결장": -3.0})
    assert json.loads(out) == {"주전결장": -3.0}
    assert json.loads(P.adj_json({})) == {}


def test_두_러너가_모두_배선돼_있다():
    """🔴 함수만 만들고 안 부르면 원장은 영원히 NULL 이다."""
    from app import pipeline as PL

    for fn in (PL._run_baseball_matchups, PL._run_soccer_matchups):
        assert "_attach_market_spine" in inspect.getsource(fn), fn.__name__


def test_판정_뒤에_붙인다():
    """🔴 판정 **앞**에 붙이면 (b) 구조가 된다 — LLM이 보게 된다."""
    from app import pipeline as PL

    src = inspect.getsource(PL._run_baseball_matchups)
    i, j = src.index("judge_matchup"), src.index("_attach_market_spine")
    assert i < j, "시장 뼈대가 판정보다 앞에 있다"


def test_원장_행에_세_칸이_실린다():
    from app.engine import pick_ledger as L

    src = inspect.getsource(L._row_from_game)
    for k in ("p_market_spine", "p_code", "adj_pp"):
        assert k in src, k
