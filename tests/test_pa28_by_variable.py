"""PA-28 계약 — 변수 하나하나를 채점한다 (지시문 10단계).

🔴 `by_axis` 는 **결정축(상위 2개)** 으로만 묶어서 `이동연전` 처럼 늘 3등인
   변수는 영영 채점되지 않았다.
🔴 채점 기준은 **CLV** 다(prob.py 결정 B · 1차 결정 6 · docs/FORKS.md F-4).
   적중률은 함께 내되 **판정 근거로 쓰지 않는다** — 이 저장소 실측에서
   판정 확률은 AUC 0.5122 로 판별력이 없었다.
⚠️ **제안일 뿐이다.** 표 크기(`prob.ADJ_SHRINK`)를 바꾸는 것은 사용자 결정이다.
"""
import inspect

import pytest

from app.engine import report as RP

NAME = "이동연전"


def _rows(n, *, delta=-1.0, side="home", clv=-3.0, hit=1, ev=None):
    r = {"adj_pp": {NAME: delta}, "predicted_side": side, "clv": clv,
         "hit": hit}
    if ev:
        r["adj_evidence"] = {NAME: {"source": ev}}
    return [dict(r) for _ in range(n)]


def _v(rows, **kw):
    return RP.by_variable(rows, **kw)["variables"].get(NAME) or {}


# ── 부호 — 🔴 여기가 틀리면 원정 픽이 통째로 뒤집힌다

def test_홈픽은_그대로다():
    assert RP.toward_pick(-2.0, "home") == -2.0


def test_원정픽은_부호가_돈다():
    """`adj_pp` 는 홈 기준, CLV 는 **고른 쪽** 기준이다."""
    assert RP.toward_pick(-2.0, "away") == 2.0


def test_픽을_모르면_None이다():
    """🔴 0 으로 읽으면 '조정 없음'과 '모름'이 같아진다."""
    for side in (None, "", "미상"):
        assert RP.toward_pick(-2.0, side) is None


def test_원정픽_기여가_양수로_집계된다():
    assert _v(_rows(3, side="away"))["평균_기여_픽기준"] == 1.0


# ── 판정

def test_문턱을_넘고_부호가_같으면_유지():
    v = _v(_rows(RP.VAR_MIN_N, delta=-1.0, clv=-3.0))
    assert v["표본_충분"] is True
    assert v["제안"] == RP.KEEP


def test_문턱을_넘고_부호가_반대면_끄기검토():
    v = _v(_rows(RP.VAR_MIN_N, delta=-1.0, clv=3.0))
    assert v["제안"] == RP.DROP


def test_문턱_미만이면_판단하지_않는다():
    """🔴 반대 위험 — 적은 표본으로 끄면 다시 켜 볼 기회가 없다."""
    v = _v(_rows(RP.VAR_MIN_N - 1))
    assert v["표본_충분"] is False and v["제안"] == RP.THIN


def test_CLV가_없으면_판단하지_않는다():
    v = _v(_rows(RP.VAR_MIN_N, clv=None))
    assert v["평균_CLV"] is None and v["제안"] == RP.THIN


def test_적중률은_참고일_뿐_판정을_안_바꾼다():
    """🔴 CLV 가 같으면 적중률이 0 이든 1 이든 제안이 같아야 한다."""
    a = _v(_rows(RP.VAR_MIN_N, delta=-1.0, clv=-3.0, hit=1))
    b = _v(_rows(RP.VAR_MIN_N, delta=-1.0, clv=-3.0, hit=0))
    assert a["제안"] == b["제안"] == RP.KEEP
    assert a["적중률"] == 1.0 and b["적중률"] == 0.0


# ── 집계

def test_발생한_행만_센다():
    """🔴 안 나온 경기를 0 으로 세면 모든 변수가 '거의 0'으로 수렴한다."""
    rows = _rows(2) + [{"adj_pp": {}, "predicted_side": "home", "clv": 9.0}]
    got = RP.by_variable(rows)
    assert got["n"] == 3
    assert got["variables"][NAME]["n"] == 2


def test_축_밖_변수도_잰다():
    """`by_axis` 는 상위 2개만 본다 — 여기는 전부 본다."""
    rows = [{"adj_pp": {"주전결장": -5.0, "필승조연투": -3.0, NAME: -1.0},
             "predicted_side": "home", "clv": -2.0, "hit": 1}]
    assert set(RP.by_variable(rows)["variables"]) == {
        "주전결장", "필승조연투", NAME}


def test_출처가_집계된다():
    v = _v(_rows(2, ev="games"))
    assert v["출처"] == {"games": 2}


def test_출처가_없으면_None이다():
    assert _v(_rows(2))["출처"] is None


def test_표본_0에서도_골격이_나온다():
    got = RP.by_variable([])
    assert got["n"] == 0 and got["variables"] == {}


def test_adj_pp가_이상해도_안_터진다():
    RP.by_variable([{"adj_pp": None}, {"adj_pp": "이상"}, {}])


# ── 🔴 반대 위험 · 사본 금지

def test_문턱을_손으로_안_적었다():
    """🔴 100 은 `config/rules.yaml` 이 원본이다."""
    src = inspect.getsource(RP.by_variable)
    assert "100" not in src
    assert RP.VAR_MIN_N == 100


def _code_only() -> str:
    """🔴 **주석이 아니라 코드 줄**만 본다. 주석에 "ADJ_SHRINK 는 사용자
    결정"이라고 설명한 것을 위반으로 세면 설명을 못 쓰게 된다 —
    처음에 그렇게 잡았다(PA-27-a 에서도 같은 실수를 했다)."""
    lines = [ln for ln in inspect.getsource(RP).splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    return "\n".join(lines)


def test_표_크기를_건드리지_않는다():
    """🔴 `ADJ_SHRINK`·`ADJ_RULES` 는 **사용자 결정**이다 — 제안만 낸다."""
    body = _code_only()
    for bad in ("ADJ_SHRINK", "ADJ_RULES", "shrink_and_cap"):
        assert bad not in body, bad


def test_DB도_HTTP도_안_부른다():
    """🔴 `report.py` 규약 — 순수 함수다."""
    body = _code_only()
    for bad in ("asyncpg", "aiohttp", "httpx", "await ", "SELECT"):
        assert bad not in body, bad


@pytest.mark.parametrize("side,want", [("home", -1.0), ("away", 1.0)])
def test_부호가_픽을_따라간다(side, want):
    assert _v(_rows(5, side=side))["평균_기여_픽기준"] == want
