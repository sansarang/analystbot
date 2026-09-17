"""U11 — T-60 재판정. diff 를 **다시 계산에 넣는다**.

🔴 `fotmob.diff_xi` 는 이미 bench_notable·surprise_in 을 냈는데
   `_lineup_recheck` 는 그것을 game_trace 에 적고 끝났다. 확정 라인업이
   예상과 달라도 p_code 도 등급도 그대로였다 — 재판정이 이름뿐이었다.
"""
from __future__ import annotations

import inspect
import pathlib

import pytest

from app.engine import confidence as C
from app.engine import rejudge as R

TT = 6352468
PLAYERS = {"Star": {"market_value": 3000000}, "Sub": {"market_value": 200000}}
BASE = {"주전결장": -3.0}


def _rw(diff, **kw):
    kw.setdefault("adj", dict(BASE))
    kw.setdefault("p_code", 0.60)
    kw.setdefault("players", PLAYERS)
    kw.setdefault("grade", "중")
    kw.setdefault("team_total_value", TT)
    return R.reweigh(diff=diff, **kw)


# ── 🔴 반대 위험

def test_diff가_비면_아무것도_안_바뀐다():
    for d in (None, {}, {"home": {}}):
        got = _rw(d)
        assert got["changed"] is False
        assert got["p_code_after"] == 0.60 and got["grade_after"] == "중"
        assert got["why"]


def test_원래_값을_덮지_않는다():
    """🔴 덮으면 '판정이 어떻게 바뀌었나'를 잃는다."""
    adj = dict(BASE)
    got = _rw({"home": {"surprise_in": ["Star"]}}, adj=adj)
    assert adj == BASE, adj
    assert got["adj_after"] is not adj
    assert BASE["주전결장"] in got["adj_after"].values()


def test_원정은_부호가_뒤집힌다():
    """🔴 원정 결장은 홈 확률에 **+** 다. 한 규칙으로 뭉치면 거꾸로 간다."""
    home_out = _rw({"home": {"bench_notable": ["Star"]}})
    away_out = _rw({"away": {"bench_notable": ["Star"]}})
    hv = home_out["adj_after"][f"{R.KEY_OUT}:home"]
    av = away_out["adj_after"][f"{R.KEY_OUT}:away"]
    assert hv < 0 < av, (hv, av)
    assert hv == -av


def test_surprise_in은_플러스_bench_notable은_마이너스():
    ins = _rw({"home": {"surprise_in": ["Star"]}})
    outs = _rw({"home": {"bench_notable": ["Star"]}})
    assert ins["adj_after"][f"{R.KEY_IN}:home"] > 0
    assert outs["adj_after"][f"{R.KEY_OUT}:home"] < 0


def test_복귀는_결장보다_크다():
    """U8: 복귀 = ×1.5×1.5 · 결장 = ×1.5.
    ⚠️ 상한(−6)과 잡음 문턱(2%p) 사이 크기여야 둘 다 살아남는다 —
       importance ≈ 1.5 (contrib_out −2.25 · contrib_return +3.375)."""
    from app.engine import adjust as A

    mid = {"Mid": {"market_value": int(1.5 * TT / 11)}}
    ins = _rw({"home": {"surprise_in": ["Mid"]}}, players=mid)
    outs = _rw({"home": {"bench_notable": ["Mid"]}}, players=mid)
    iv = ins["adj_after"][f"{R.KEY_IN}:home"]
    ov = outs["adj_after"][f"{R.KEY_OUT}:home"]
    assert abs(iv) == pytest.approx(abs(ov) * A.RETURN_MULT, abs=0.02)
    assert abs(iv) < A.OUT_CAP, "상한에 걸려 비교가 무의미하다"


def test_기여가_작으면_재판정에서도_빠진다():
    """⚠️ 잡음 문턱은 U8 규칙 그대로다 — 후보급 한 명은 조정이 아니다."""
    small = {"Sub": {"market_value": 200000}}
    got = _rw({"home": {"surprise_in": ["Sub"]}}, players=small)
    assert f"{R.KEY_IN}:home" not in got["adj_after"]
    assert f"{R.KEY_IN}:home" in got["adj_dropped_after"]


def test_상한을_지난다():
    """🔴 반대 위험 — 재계산이 승률 상한을 우회하면 그 경기만 규칙 밖이다."""
    got = _rw({"home": {"surprise_in": ["Star", "Star", "Star"]}},
              p_code=0.68)
    assert got["p_code_after"] <= 0.72, got["p_code_after"]
    src = inspect.getsource(R.reweigh)
    assert "P.p_code(" in src, "상한을 지나는 함수를 안 쓴다"


def test_시장값을_다시_안_읽는다():
    """🔴 반대 위험 — 재판정이 배당을 또 긁으면 요청이 는다."""
    src = inspect.getsource(R)
    for bad in ("implied_probs", "odds_snapshots", "httpx", "get_pool", "await "):
        assert bad not in src, bad
    assert "_market_of" in src


def test_되짚기가_원래_시장값을_준다():
    from app.engine import prob as P

    mkt = 0.55
    adj = {"a": -3.0}
    p = P.p_code(mkt, adj, "soccer")
    assert R._market_of(p, adj) == pytest.approx(mkt, abs=1e-6)


# ── 등급

def test_등급이_따라_움직인다():
    up = _rw({"home": {"surprise_in": ["Star"]}}, p_code=0.60, grade="중")
    assert up["p_code_after"] > 0.60
    assert up["grade_after"] == C.HIGH

    down = _rw({"home": {"bench_notable": ["Star"]}}, p_code=0.60, grade="중")
    assert down["p_code_after"] < 0.60
    assert down["grade_after"] == C.LOW


def test_조각_자료면_등급이_눌린다():
    got = _rw({"home": {"surprise_in": ["Star"]}}, snippet=True)
    assert got["grade_after"] == C.LOW


def test_결정축도_다시_고른다():
    got = _rw({"home": {"surprise_in": ["Star"]}})
    assert "axes_after" in got and got["axes_after"]["main_axis"]


def test_잡음은_재판정에서도_빠진다():
    """🔴 [PA-27-a 2026-09-17] **새로 더한 것**에만 건다.

    종전에는 `merged` 전체에 `drop_small` 을 걸어 **기존 가감까지** 지웠다.
    그런데 `ADJ_RULES` 의 기본 delta 는 -1.0 · -1.5 로 전부 문턱(2.0) 아래라,
    그 규칙을 기존 가감에 걸면 **설계된 조정 대부분이 지워진다.**
    실측: adj={'주전결장': -1.5} + 홈 결장 1명 → adj_after={} 가 되고
    확률이 시장으로 되돌아가 **0.55 → 0.5575 로 올랐다**(결장인데 홈 유리).

    그래서 이 계약의 뜻을 **"새로 더한 잡음이 빠진다"**로 좁힌다 —
    기존 가감을 소급해 지우는 것은 U8 의 규칙이 아니었다.
    """
    # ⚠️ 중요도는 `market_value`/`team_total_value` 로 정해진다 —
    #    `{"importance": …}` 키는 읽지 않는다(기본 1.0 중립).
    got = _rw({"home": {"surprise_in": ["Tiny"]}},
              adj={"주전결장": -3.0},
              players={"Tiny": {"market_value": 1}},
              team_total_value=1000)
    # 새로 더한 복귀 기여(0.1 × 1.5 × 1.5 ≈ 0.2%p)는 문턱 아래라 빠진다
    assert not [k for k in got["adj_after"] if k.startswith("라인업복귀")]
    assert [k for k in (got.get("adj_dropped_after") or {})
            if k.startswith("라인업복귀")]
    # 기존 가감은 **그대로 남는다**
    assert got["adj_after"]["주전결장"] == -3.0


# ── 야구

@pytest.mark.parametrize("before,after,changed", [
    ("Kim", "Lee", True), ("Kim", "Kim", False),
    (None, "Lee", False), ("Kim", None, False), ("", "", False),
])
def test_starter_changed(before, after, changed):
    got = R.starter_changed(before, after)
    assert got["changed"] is changed
    assert got["why"]


def test_starter_changed는_야구_전용():
    """⚠️ 축구 XI diff 와 이름이 다르다 — 한 명 vs 열한 명."""
    doc = inspect.getdoc(R.starter_changed) or ""
    assert "야구" in doc and "축구" in doc


def test_원장_세_칸이_있다():
    src = pathlib.Path("db/schema.sql").read_text(encoding="utf-8")
    for col in ("adj_after", "p_code_after", "grade_after"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in src, col


def test_순수함수다():
    src = inspect.getsource(R)
    for bad in ("asyncpg", "httpx", "get_pool", "await "):
        assert bad not in src, bad
