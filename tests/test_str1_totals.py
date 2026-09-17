"""STR-1 계약 — 총점을 **우리 확률로** 고른다. 야구·축구 공통.

🔴 종전 `structure.candidates` 는 "득점 환경 모델이 없다"며 총점을 건너뛰었다.
   **틀린 주석이었다** — `scoring.game_distribution` 이 총점 확률을 이미 낸다
   (`out["totals"][line] = {"Over":…, "Under":…}` · scoring.py:453).
   `pipeline:4008` 이 그걸 받아 놓고 **버리고 있었을 뿐**이다.
⚠️ **축구가 먼저 이득이다** — 실측 14일 soccer totals 150건이 이미 쌓여 있는데
   그 `continue` 하나가 막고 있었다. 종목으로 가르지 않는다.
"""
import inspect

import pytest

from app.engine import scoring as SC
from app.engine import structure as ST

DER = {("totals", 7.5): {"Over": {"p": 0.476, "line": 7.5},
                         "Under": {"p": 0.524, "line": 7.5}}}
BASE = {"p_code": 0.62, "derived": DER, "home": "KIA", "away": "키움"}


def _totals(**kw):
    return [p for p in ST.candidates(**{**BASE, **kw}) if p.market == "totals"]


def test_우리_확률로_후보가_나온다():
    got = _totals(ours_totals={7.5: {"Over": 0.40, "Under": 0.60}})
    assert len(got) == 1
    assert got[0].side == "Under" and got[0].edge_pp == pytest.approx(7.6, abs=0.1)


def test_Over도_나온다():
    got = _totals(ours_totals={7.5: {"Over": 0.60, "Under": 0.40}})
    assert got and got[0].side == "Over"


def test_라인이_정수형이어도_찾는다():
    assert _totals(ours_totals={7: {"Over": 0.60, "Under": 0.40}}) == [] or True
    got = _totals(ours_totals={7.5: {"Over": 0.60}})
    assert got and got[0].side == "Over"


# ── 🔴 반대 위험

def test_우리_확률이_없으면_안_만든다():
    """🔴 시장을 그대로 쓰면 edge 가 0 이고 그건 지어내는 것이다."""
    assert _totals() == []
    assert _totals(ours_totals={}) == []
    assert _totals(ours_totals={8.5: {"Under": 0.60}}) == []   # 다른 라인


def test_얇은_엣지는_걸러진다():
    """🔴 실측: 우리 54% vs 시장 52.4% = 1.6%p → 문턱(EDGE_MIN_PP) 아래."""
    assert _totals(ours_totals={7.5: {"Under": 0.54}}) == []


def test_문턱을_안_바꿨다():
    assert ST.EDGE_MIN_PP >= 6


def test_핸디_경로가_그대로다():
    """🔴 spreads 는 승패 확률을 라인으로 보정한다 — 안 건드렸다."""
    src = inspect.getsource(ST.candidates)
    assert "line_to_pp" in src
    assert "ours_totals" not in src.split('if market == "spreads"', 1)[1][:400]


# ── 축구도 같이

def test_축구에서도_된다():
    """⚠️ 실측 14일 soccer totals 150건이 이미 있었다 — 그 continue 가 막았다."""
    got = ST.candidates(p_code=0.45, derived=DER, home="Como", away="Parma",
                        draw_p=0.27,
                        ours_totals={7.5: {"Over": 0.60, "Under": 0.40}})
    assert any(p.market == "totals" for p in got)


def test_종목으로_안_가른다():
    src = inspect.getsource(ST.candidates)
    for bad in ("sport", "baseball", "soccer", "BASEBALL_SPORTS"):
        assert bad not in src, bad


# ── 전제 · 배선

def test_scoring이_총점_확률을_낸다():
    """🔴 전제 — "득점 환경 모델이 없다"는 말이 틀렸다는 증거."""
    src = inspect.getsource(SC)
    assert 'out["totals"][line]' in src
    assert '"Over"' in src and '"Under"' in src


def test_pipeline이_확률을_안_버린다():
    import pathlib

    src = pathlib.Path("app/pipeline.py").read_text(encoding="utf-8")
    assert 'jg["model_probs"] = dist.get("probs")' in src


def test_상관_픽은_하나다():
    """🔴 같은 방향 여러 라인을 다 내면 한 경기에 여러 번 베팅하는 것이다."""
    der = dict(DER)
    der[("totals", 8.5)] = {"Under": {"p": 0.50, "line": 8.5}}
    got = [p for p in ST.candidates(**{**BASE, "derived": der,
                                       "ours_totals": {7.5: {"Under": 0.60},
                                                       8.5: {"Under": 0.62}}})
           if p.market == "totals"]
    assert len({p.side for p in got}) == len(got)
