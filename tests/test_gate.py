"""GATE-1 — 괴리 게이트. 지시문 Phase 3.

    gap = p_prior − p_market   (홈 기준, 축구는 세 값 중 **최대 절대값**)

    |gap| < 4      → "동의"       딥서치 생략(층1 위성만)
    gap ≤ −4       → "시장 과대"  딥서치 대상 · 구조 픽 후보
    gap ≥ +4       → "가치 의심"  딥서치 대상 · 이유 없으면 p_prior 가 틀린 것
    p_market 없음  → "보드 고정"  딥서치 생략 · 확신 하

딥서치 예산: 슬레이트당 상위 30%(최소 2, 최대 8), |gap| 큰 순.
"""
import pytest

from app.engine import gate as G


# ── 분류

@pytest.mark.parametrize("prior,market,want", [
    (0.55, 0.54, G.AGREE),        # +1.0
    (0.50, 0.54, G.OVER),         # −4.0  경계 포함
    (0.58, 0.54, G.DOUBT),        # +4.0  경계 포함
    (0.40, 0.60, G.OVER),
    (0.70, 0.50, G.DOUBT),
    (0.54, 0.54, G.AGREE),
])
def test_야구_분류(prior, market, want):
    assert G.classify(prior, market, "mlb").label == want


def test_경계는_4_0_포함이다():
    """🔴 `< 4` 와 `≤ −4` 가 지시문 표다. 3.99 는 동의, 4.0 은 대상이다."""
    assert G.classify(0.5399, 0.50, "mlb").label == G.AGREE      # +3.99
    assert G.classify(0.54, 0.50, "mlb").label == G.DOUBT        # +4.00


def test_시장이_없으면_보드_고정이다():
    r = G.classify(0.60, None, "mlb")
    assert r.label == G.BOARD and r.gap_pp is None
    assert r.deepsearch is False
    assert "확신 하" in r.reason


def test_사전값이_없어도_보드_고정이다():
    """⚠️ 티어 미기입으로 사전값을 못 낸 경기도 여기로 온다."""
    assert G.classify(None, 0.54, "mlb").label == G.BOARD


# ── 축구 3-way: 세 값 중 최대 절대값

def test_축구는_세_값_중_가장_크게_갈린_칸을_쓴다():
    prior = (0.50, 0.28, 0.22)
    market = (0.47, 0.27, 0.26)       # 홈 +3.0 · 무 +1.0 · 원정 −4.0
    r = G.classify(prior, market, "soccer")
    assert r.gap_pp == pytest.approx(-4.0)
    assert r.label == G.OVER
    assert r.side == "away"


def test_축구_부호는_그_칸의_방향이다():
    prior = (0.60, 0.22, 0.18)
    market = (0.50, 0.27, 0.23)       # 홈 +10.0 이 최대
    r = G.classify(prior, market, "soccer")
    assert r.gap_pp == pytest.approx(10.0) and r.side == "home"
    assert r.label == G.DOUBT


def test_축구_한_칸이_비면_그_칸은_건너뛴다():
    """🔴 없는 것을 0 으로 읽으면 그 칸이 최대 괴리가 된다."""
    r = G.classify((0.50, 0.28, 0.22), (0.47, None, 0.26), "soccer")
    assert r.gap_pp == pytest.approx(-4.0) and r.side == "away"


# ── 딥서치 예산

def _g(gid, gap):
    return {"game_id": gid, "gap_pp": gap, "label": G.DOUBT}


def test_상위_30퍼센트를_고르되_최소_2다():
    picked = G.select([_g(i, i) for i in range(1, 5)])   # 4경기 → 30% = 1.2
    assert len(picked) == 2                              # 최소 2
    assert [p["game_id"] for p in picked] == [4, 3]      # |gap| 큰 순


def test_최대_8을_넘지_않는다():
    picked = G.select([_g(i, i) for i in range(1, 41)])  # 40경기 → 30% = 12
    assert len(picked) == 8


def test_대상이_아닌_경기는_고르지_않는다():
    rows = [{"game_id": 1, "gap_pp": 20.0, "label": G.AGREE},
            {"game_id": 2, "gap_pp": 9.0, "label": G.BOARD},
            {"game_id": 3, "gap_pp": 5.0, "label": G.DOUBT},
            {"game_id": 4, "gap_pp": -6.0, "label": G.OVER}]
    assert [p["game_id"] for p in G.select(rows)] == [4, 3]


def test_대상이_하나뿐이면_하나만_고른다():
    """⚠️ '최소 2' 는 **대상 안에서** 최소다. 없는 것을 만들지 않는다."""
    rows = [{"game_id": 1, "gap_pp": 5.0, "label": G.DOUBT},
            {"game_id": 2, "gap_pp": 1.0, "label": G.AGREE}]
    assert [p["game_id"] for p in G.select(rows)] == [1]


def test_빈_슬레이트는_빈_목록이다():
    assert G.select([]) == []


# ── 원장

def test_원장에_사유_칸이_있다():
    s = open("db/schema.sql", encoding="utf-8").read()
    assert "ADD COLUMN IF NOT EXISTS gate_reason" in s


# ── 격리

def test_게이트는_확률을_바꾸지_않는다():
    """🔴 게이트는 **고르는 일**만 한다. p_code 를 건드리면 이중 반영이다."""
    import ast
    import inspect

    # ⚠️ **주석·독스트링을 빼고 본다.** 통짜 grep 은 설명에 걸려 헛돈다
    #    (이 저장소에서 무딘 계약으로 여섯 번 헛돌았다).
    tree = ast.parse(inspect.getsource(G))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for bad in ("p_code", "p_send", "adjustments", "shrink_and_cap"):
        assert bad not in names, bad
    # 그리고 이 모듈은 아무것도 임포트하지 않아야 한다(순수 함수)
    mods = {a.name.split(".")[0]
            for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {(n.module or "").split(".")[0]
             for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert mods <= {"__future__", "logging", "dataclasses"}, mods
