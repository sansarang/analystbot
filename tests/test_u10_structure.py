"""U10 — 구조 픽 · 파생 디빅 · 상태기계.

🔴 `analyze.py:157` 은 `blk["derived"]` 를 **읽는데 만드는 곳이 0건**이었다.
   그래서 구조 후보가 나와도 전건 반려됐다. 이 모듈이 그 생산자다.
🔴 실측 2026-09-15: U2 가 핸디 양쪽을 **반대 부호**로 저장한다(홈 −0.5 /
   원정 +0.5). 부호를 그대로 키로 쓰면 한 핸디가 두 버킷으로 갈려 전건 유실된다.
"""
from __future__ import annotations

import inspect
import pathlib

import pytest

from app.engine import confidence as C
from app.engine import structure as S
from app.engine import watch_state as W

AH = [{"market": "spreads", "line": -0.5, "side": "H", "odds": 1.55},
      {"market": "spreads", "line": 0.5, "side": "A", "odds": 2.45}]
OU = [{"market": "totals", "line": 2.5, "side": "Over", "odds": 1.95},
      {"market": "totals", "line": 2.5, "side": "Under", "odds": 1.85}]


# ── 파생 디빅

def test_핸디_양쪽이_반대부호여도_묶인다():
    """🔴 실측 결함 — 부호를 키로 쓰면 전건 유실된다."""
    d = S.derived_probs(AH)
    assert len(d) == 1, d
    box = next(iter(d.values()))
    assert set(box) == {"H", "A"}
    assert box["H"]["line"] == -0.5 and box["A"]["line"] == 0.5


def test_파생_디빅이_양쪽_있을_때만():
    """🔴 반대 위험 — 한쪽만으로 디빅하면 마진이 안 빠져 확률이 부푼다."""
    assert S.derived_probs(AH[:1]) == {}
    assert S.derived_probs(OU[:1]) == {}


def test_마진이_빠진다():
    d = S.derived_probs(OU)
    box = next(iter(d.values()))
    assert sum(b["p"] for b in box.values()) == pytest.approx(1.0, abs=1e-6)


def test_h2h는_파생이_아니다():
    assert S.derived_probs([{"market": "h2h", "side": "H", "odds": 2.0},
                            {"market": "h2h", "side": "A", "odds": 2.0}]) == {}


# ── edge · 후보

def test_edge는_우리_빼기_시장():
    assert S._edge(0.60, 0.50) == 10.0
    assert S._edge(0.40, 0.50) == -10.0
    assert S._edge(None, 0.5) is None and S._edge(0.5, None) is None


def test_edge_6미만은_후보가_아니다():
    assert S.EDGE_MIN_PP == 6.0
    d = S.derived_probs(AH)
    # p_code 를 시장과 거의 같게 주면 edge 가 작아 후보가 없다
    assert S.candidates(p_code=0.62, derived=d, home="H", away="A",
                        draw_p=0.20) == []


def test_후보가_나온다():
    d = S.derived_probs(AH)
    got = S.candidates(p_code=0.72, derived=d, home="H", away="A", draw_p=0.157)
    assert got and got[0].side == "H" and got[0].line == -0.5
    assert got[0].edge_pp >= S.EDGE_MIN_PP


def test_상관_픽은_하나만():
    """🔴 반대 위험 — 같은 팀 여러 라인을 다 내면 한 경기에 여러 번 베팅이다."""
    rows = AH + [{"market": "spreads", "line": -1.0, "side": "H", "odds": 2.1},
                 {"market": "spreads", "line": 1.0, "side": "A", "odds": 1.75}]
    got = S.candidates(p_code=0.80, derived=S.derived_probs(rows),
                       home="H", away="A", draw_p=0.10)
    sides = [p.side for p in got]
    assert len(sides) == len(set(sides)), sides


def test_토탈은_후보로_안_만든다():
    """⚠️ 득점 환경 모델이 없다. 시장을 그대로 쓰면 edge 0 — 지어내지 않는다."""
    got = S.candidates(p_code=0.72, derived=S.derived_probs(OU),
                       home="H", away="A")
    assert got == []


def test_p_code가_없으면_후보도_없다():
    assert S.candidates(p_code=None, derived=S.derived_probs(AH),
                        home="H", away="A") == []


def test_핸디는_정해진_라인만():
    assert S.AH_LINES == (0.5, 1.0, 1.5)
    rows = [{"market": "spreads", "line": -2.5, "side": "H", "odds": 1.5},
            {"market": "spreads", "line": 2.5, "side": "A", "odds": 2.5}]
    assert S.candidates(p_code=0.90, derived=S.derived_probs(rows),
                        home="H", away="A") == []


# ── 등급

@pytest.mark.parametrize("edge,want", [(9.0, "상"), (8.0, "상"),
                                       (7.9, "중"), (6.0, "중"),
                                       (5.9, None), (None, None)])
def test_구조등급_8상_6중(edge, want):
    assert S.grade(edge) == want
    assert C.structure_grade(edge) == want


def test_구조등급이_숫자를_베끼지_않는다():
    src = inspect.getsource(C.structure_grade)
    assert "structure" in src and "8" not in src


# ── snippet 상한

def test_snippet이면_승패상한_하():
    assert C.cap_by_snippet("상", True) == C.LOW
    assert C.cap_by_snippet("중", True) == C.LOW


def test_조각이_아니면_그대로다():
    """⚠️ 반대 위험 — 올리지 않는다."""
    for lv in ("상", "중", "하"):
        assert C.cap_by_snippet(lv, False) == lv


def test_기존_등급_경로가_그대로다():
    """🔴 반대 위험 — CONF-1 을 건드리면 안 된다."""
    assert (C.CODE_HIGH_P, C.CODE_MID_P) == (0.63, 0.58)
    assert (C.HIGH, C.MID, C.LOW) == ("상", "중", "하")


# ── 상태기계

def test_상태_전이_전_경로():
    s = "관측"
    for want in (W.CANDIDATE, W.PENDING, W.PICKED, W.DONE):
        step = W.next_state(s, want, reason="t")
        assert step.changed is True, (s, want)
        s = step.state
    assert s == W.DONE


def test_역방향_전이는_없다():
    """🔴 반대 위험 — 추천에서 후보로 돌아가면 나간 카드를 되돌려야 한다."""
    step = W.next_state(W.PICKED, W.CANDIDATE)
    assert step.changed is False and step.state == W.PICKED
    assert "거부" in step.reason


def test_취소와_종료로만_나간다():
    for s in (W.OBSERVE, W.CANDIDATE, W.PENDING, W.PICKED):
        assert W.CANCELLED in W.ALLOWED[s] and W.DONE in W.ALLOWED[s]
    assert W.ALLOWED[W.DONE] == ()


def test_같은_상태면_변화없음():
    step = W.next_state(W.CANDIDATE, W.CANDIDATE)
    assert step.changed is False and step.state == W.CANDIDATE


def test_모르는_상태는_관측으로_읽는다():
    assert W.next_state("이상한값", W.CANDIDATE).state == W.CANDIDATE


def test_전이가_예외를_던지지_않는다():
    """⚠️ 상태기계가 판정을 막으면 안 된다."""
    assert W.next_state(W.DONE, W.PICKED).state == W.DONE


# ── 조건 A

def test_조건A_네_항목():
    ok = W.condition_a(gate_label="가치 의심", confirmed_n=2, sufficient=True,
                       swap_agree=True, structure_n=1)
    assert ok["ok"] is True and ok["missing"] == []
    assert set(ok["checks"]) == {"게이트 대상", "확인 충족", "스왑 일치", "구조 후보"}


@pytest.mark.parametrize("kw,missing", [
    ({"gate_label": "동의"}, "게이트 대상"),
    ({"sufficient": False}, "확인 충족"),
    ({"swap_agree": None}, "스왑 일치"),
    ({"structure_n": 0}, "구조 후보"),
])
def test_하나라도_빠지면_불가(kw, missing):
    base = dict(gate_label="가치 의심", confirmed_n=2, sufficient=True,
                swap_agree=True, structure_n=1)
    base.update(kw)
    got = W.condition_a(**base)
    assert got["ok"] is False and missing in got["missing"]


def test_스왑을_모르면_불가():
    """⚠️ None 은 '모른다'다 — 통과시키지 않는다."""
    got = W.condition_a(gate_label="시장 과대", confirmed_n=3, sufficient=True,
                        swap_agree=None, structure_n=2)
    assert got["ok"] is False


def test_순수함수다():
    for mod in (S, W):
        src = inspect.getsource(mod)
        for bad in ("asyncpg", "httpx", "get_pool", "await "):
            assert bad not in src, (mod.__name__, bad)


def test_원장_두_칸이_있다():
    src = pathlib.Path("db/schema.sql").read_text(encoding="utf-8")
    for col in ("watch_state", "structure_pick"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in src, col


# ── 파생 디빅 부착(항목 2)

def test_derived_키를_붙인다():
    """🔴 analyze.py:157 이 이 키를 읽는다. 종전에는 생산자가 0건이라
    구조 후보가 전건 반려됐다("구조_후보가 파생 디빅에 없는 시장이다")."""
    blk = S.attach_derived({"경기": "x"}, AH + OU)
    assert "derived" in blk and blk["경기"] == "x"
    시장 = {d["시장"] for d in blk["derived"]}
    assert 시장 == {"spreads", "totals"}
    assert all(set(d) == {"시장", "라인", "쪽", "확률"} for d in blk["derived"])


def test_행이_없어도_키는_남는다():
    """⚠️ 없는 것과 안 본 것은 다르다 — 키를 없애지 않는다."""
    assert S.attach_derived({}, [])["derived"] == []
    assert S.attach_derived({}, None)["derived"] == []


def test_analyze가_읽는_모양이다():
    src = inspect.getsource(__import__("app.engine.analyze",
                                       fromlist=["x"]))
    assert 'get("derived")' in src or '"derived"' in src
    blk = S.attach_derived({}, AH)
    names = {d["시장"] for d in blk["derived"]}
    assert names <= {"spreads", "totals"}
