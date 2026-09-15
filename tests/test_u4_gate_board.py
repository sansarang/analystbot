"""U4 — 게이트 4분류. **코드는 이미 있었고 계약이 없었다.**

🔴 내 감사표가 "3분류"라고 적었는데 틀렸다 — `gate.py:24` 의 `BOARD` 를
   놓쳤다(21~23행만 grep 했다). 실동작은 처음부터 정확했다.
   U3 이 `p_prior=None` 을 만들기 시작했으므로, 그 None 이 보드 고정으로
   간다는 사실을 잠그는 계약이 필요하다. 종전에는 `BOARD` 를 단언하는
   테스트가 저장소 전체에 0건이었다.
"""
from __future__ import annotations

import pytest

from app.engine import gate as G

PRI = (0.45, 0.28, 0.27)
MKT = (0.44, 0.28, 0.28)


def test_네_분류가_전부_있다():
    assert {G.AGREE, G.OVER, G.DOUBT, G.BOARD} == {
        "동의", "시장 과대", "가치 의심", "보드 고정"}
    assert len({G.AGREE, G.OVER, G.DOUBT, G.BOARD}) == 4


@pytest.mark.parametrize("prior,market,why", [
    (None, MKT, "사전값 없음"),
    (PRI, None, "시장 없음"),
    (None, None, "둘 다 없음"),
    ((None, None, None), MKT, "사전값 3칸이 전부 빔"),
    (PRI, (None, None, None), "시장 3칸이 전부 빔"),
])
def test_한쪽이라도_없으면_보드고정(prior, market, why):
    v = G.classify(prior, market, "soccer")
    assert v.label == G.BOARD, why
    assert v.gap_pp is None and v.side is None
    assert "없다" in v.reason


def test_없는_값을_0으로_읽지_않는다():
    """🔴 반대 위험 — None 을 0 으로 읽으면 gap 이 −45%p 가 되어
    엉뚱한 경기가 최우선 딥서치 대상이 된다."""
    v = G.classify(None, MKT, "soccer")
    assert v.gap_pp is None, f"0 으로 읽어 gap 을 만들었다: {v.gap_pp}"
    v2 = G.classify((0.0, 0.0, 0.0), MKT, "soccer")
    assert v2.gap_pp is not None, "진짜 0 은 값이다 — None 과 구분해야 한다"


def test_빈_칸은_건너뛴다():
    """🔴 반대 위험 — 축구 3칸 중 하나만 비었을 때 그 칸을 0 으로 읽으면
    그것이 최대 괴리가 된다."""
    v = G.classify((0.45, None, 0.27), (0.44, 0.28, 0.28), "soccer")
    assert v.label != G.BOARD, "한 칸 비었다고 통째로 버린다"
    assert v.side in ("home", "away"), v.side


@pytest.mark.parametrize("gap_pp,want", [
    (3.9, G.AGREE), (-3.9, G.AGREE),
    (4.0, G.DOUBT), (-4.0, G.OVER),
    (15.0, G.DOUBT), (-15.0, G.OVER),
])
def test_경계는_4pp다(gap_pp, want):
    p = 0.50 + gap_pp / 100.0
    v = G.classify((p, 0.25, 0.75 - p), (0.50, 0.25, 0.25), "soccer")
    assert v.label == want, (gap_pp, v.label, v.gap_pp)
    assert G.THRESHOLD_PP == 4.0


def test_축구는_가장_크게_갈린_칸을_쓴다():
    v = G.classify((0.46, 0.20, 0.34), (0.44, 0.28, 0.28), "soccer")
    assert v.side == "draw", v.side          # |20−28| = 8 이 최대
    assert v.gap_pp == pytest.approx(-8.0)


def test_야구는_홈_한_칸이다():
    v = G.classify(0.55, 0.52, "mlb")
    assert v.side == "home" and v.gap_pp == pytest.approx(3.0)


def test_예산은_30퍼센트_2에서_8():
    assert (G.BUDGET_RATIO, G.BUDGET_MIN, G.BUDGET_MAX) == (0.30, 2, 8)
    rows = [{"gap_pp": g, "label": G.OVER if g < 0 else G.DOUBT}
            for g in (20, -18, 15, -12, 9, -7, 5, -4, 3, 2)]
    got = G.select(rows)
    assert len(got) == min(G.BUDGET_MAX,
                           max(G.BUDGET_MIN, round(len(rows) * G.BUDGET_RATIO)))
    assert [abs(r["gap_pp"]) for r in got] == sorted(
        (abs(r["gap_pp"]) for r in got), reverse=True), "|gap| 순이 아니다"


def test_보드고정과_동의는_예산을_안_먹는다():
    """🔴 gap 이 None 인 경기나 '동의' 가 상위로 올라가면 진짜 대상이 밀린다."""
    rows = [{"gap_pp": None, "label": G.BOARD},
            {"gap_pp": 1.0, "label": G.AGREE},
            {"gap_pp": 20, "label": G.DOUBT},
            {"gap_pp": -18, "label": G.OVER}]
    got = G.select(rows)
    assert {r["label"] for r in got} <= {G.OVER, G.DOUBT}, got
    assert all(r["gap_pp"] is not None for r in got)


def test_대상이_하나면_하나다():
    """⚠️ "최소 2" 는 대상 안에서의 최소다 — 없는 것을 만들어 채우지 않는다."""
    rows = [{"gap_pp": 20, "label": G.DOUBT},
            {"gap_pp": None, "label": G.BOARD}]
    assert len(G.select(rows)) == 1


def test_대상이_없으면_빈_목록():
    assert G.select([{"gap_pp": 1.0, "label": G.AGREE}]) == []
    assert G.select([]) == []
