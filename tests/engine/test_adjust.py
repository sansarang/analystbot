"""ADJ-1 — 조정 변수를 DB 원자료에서 계산한다 (결정 A).

사용자 결정 2026-09-13(2차 결정 A): `prob.py` 는 순수 함수로 두고,
`adjust.attach(jg, pool)` 가 `_attach_market_spine` **직전**에 `jg` 에 키만
세팅한다. 수집기(`gather`·`bullpen_recent`)는 건드리지 않는다.

🔴 **실측 2026-09-13**: 결정 1 구현 직후 오늘 MLB 8경기의 `adj_pp` 가 전부
   `{}` 였다 — `p_code == p_market`, 즉 코드가 시장을 그대로 베꼈다.
   조정 변수를 읽는 키를 아무도 채우지 않았기 때문이다.

⚠️ **적용 시점 규칙**: 라인업/타순이 `confirmed`(=official)가 아니면 결장·
   선발변경 변수를 계산하지 않고 `adj_pending=True`. 잠정 상태에서 조정하지 않는다.
⚠️ 계산 불가(원자료 없음)는 0이 아니라 **미계산**(`adj_missing`)이다.
"""
import pytest

from app.engine import adjust as A


def test_임계값이_한_곳에_있다():
    """⚠️ 사본 금지 — 숫자를 함수 안에 흩어 적지 않는다."""
    for k in ("regular_window", "regular_min", "pen_top_n",
              "pen_window_days", "trip_min"):
        assert k in A.ADJ_DEFS, k


def test_official이_아니면_계산하지_않는다():
    """🔴 잠정 타순으로 조정하면 확정 뒤 뒤집힌다."""
    jg = {"sport": "mlb", "lineup_status": "predicted"}
    assert A.gate(jg) is False
    jg2 = {"sport": "mlb", "lineup_status": "confirmed"}
    assert A.gate(jg2) is True


def test_official_상태값을_손으로_적지_않는다():
    import inspect

    from app.collectors.lineups import STATUS_CONFIRMED

    src = inspect.getsource(A)
    assert "STATUS_CONFIRMED" in src, "상태 상수를 원본에서 가져오지 않았다"
    assert A.gate({"lineup_status": STATUS_CONFIRMED}) is True


# ── 주전 결장

def test_주전결장을_최근10경기_7선발_기준으로_센다():
    regulars = {"A", "B", "C", "D"}
    today = ["A", "B", "X", "Y"]
    assert A.count_out(regulars, today) == 2          # C·D 빠짐


def test_오늘_타순이_비면_미계산이다():
    assert A.count_out({"A"}, []) is None


# ── 불펜 연투

def test_연투는_직전_2일_연속_등판이다():
    from datetime import date

    d = date(2026, 9, 13)
    apps = {"P1": [date(2026, 9, 12), date(2026, 9, 11)],   # 2일 연속 → 연투
            "P2": [date(2026, 9, 12)],                       # 하루만
            "P3": [date(2026, 9, 10), date(2026, 9, 9)]}     # 오래됨
    assert A.count_b2b(apps, d) == 1


def test_연투는_상위_3명만_본다():
    assert A.ADJ_DEFS["pen_top_n"] == 3


# ── 이동 연전

@pytest.mark.parametrize("streak,expect", [(0, 0), (2, 0), (3, 1), (7, 1)])
def test_이동연전은_3연전_이상에서만_발생한다(streak, expect):
    assert A.trip_flag(streak) == expect


# ── 축구

def test_축구_주전은_최근10경기_8선발이다():
    assert A.ADJ_DEFS["soccer_regular_min"] == 8


@pytest.mark.parametrize("days,expect", [(2, True), (3, True), (4, False), (None, False)])
def test_짧은휴식은_3일_이하다(days, expect):
    assert A.short_rest(days) is expect


def test_대항전_소스가_없으면_미계산이다():
    """⚠️ 소스가 없으면 0 이 아니라 unknown 이다 — 0 은 '조사했는데 없었다'다."""
    jg = {"sport": "soccer"}
    assert A.midweek_away(jg) is None


# ── 붙이기

@pytest.mark.asyncio
async def test_미계산은_adj_missing에_남는다():
    class _Pool:
        async def fetch(self, *a, **k): return []
        async def fetchval(self, *a, **k): return None

    jg = {"sport": "mlb", "game_id": 1, "home": "H", "away": "A",
          "lineup_status": "confirmed"}
    await A.attach(jg, _Pool())
    assert "adj_missing" in jg
    # 🔴 T-24h 선발 스냅샷 테이블이 없다 — starter_changed 는 미계산이어야 한다
    assert "starter_changed" in jg["adj_missing"], jg["adj_missing"]
    assert jg.get("starter_changed") in (None, 0, False)


@pytest.mark.asyncio
async def test_잠정이면_adj_pending이_선다():
    class _Pool:
        async def fetch(self, *a, **k): return []
        async def fetchval(self, *a, **k): return None

    jg = {"sport": "mlb", "game_id": 1, "lineup_status": "predicted"}
    await A.attach(jg, _Pool())
    assert jg.get("adj_pending") is True
    assert not jg.get("out_starters")


@pytest.mark.asyncio
async def test_원자료_요약을_남긴다():
    """서술 규격의 `reason_vars` 가 여기서 나온다."""
    class _Pool:
        async def fetch(self, *a, **k): return []
        async def fetchval(self, *a, **k): return None

    jg = {"sport": "mlb", "game_id": 1, "lineup_status": "confirmed"}
    await A.attach(jg, _Pool())
    assert isinstance(jg.get("adj_inputs"), dict)


def test_수집기를_건드리지_않는다():
    """⚠️ 결정 A — gather·bullpen_recent 는 그대로 둔다."""
    import inspect

    src = inspect.getsource(A)
    for bad in ("gather.collect", "bullpen_recent", "attach_starter_recent"):
        assert bad not in src, bad


# ── 결정 B: 축소 계수

def test_조정_크기를_절반으로_시작한다():
    from app.engine import prob as P

    assert P.ADJ_SHRINK == 0.5


def test_합계_절사가_6퍼센트포인트다():
    from app.engine import prob as P

    assert P.ADJ_SUM_CAP == 6.0
    big = {"a": -5.0, "b": -5.0, "c": -5.0}
    assert abs(sum(P.shrink_and_cap(big).values())) == pytest.approx(6.0)


def test_축소가_p_code에_반영된다():
    from app.engine import prob as P

    # 표 -1.5/명 × 2명 = -3.0 → 축소 0.5 → -1.5%p
    adj = P.adjustments({"sport": "mlb", "out_starters": 2})
    assert adj["주전결장"] == -3.0                      # 표 그대로 기록
    assert P.p_code(0.55, adj, "mlb") == pytest.approx(0.535, abs=1e-9)


def test_뼈대_직전에_배선돼_있다():
    """🔴 결정 A — `_attach_market_spine` **직전**이어야 한다."""
    import inspect

    from app import pipeline as PL

    src = inspect.getsource(PL._attach_market_spine)
    i, j = src.index("_adjust.attach"), src.index("_market_probs(")
    assert i < j, "조정 부착이 시장 확률 계산보다 뒤에 있다"


def test_원장에는_축소_전_값을_남긴다():
    """사후 검증의 재료는 '어떤 변수가 얼마로 발생했나'다."""
    from app.engine import prob as P

    adj = P.adjustments({"sport": "mlb", "out_starters": 2})
    assert adj["주전결장"] == -3.0            # 표 그대로
    assert P.shrink_and_cap(adj)["주전결장"] == -1.5   # 적용은 절반
