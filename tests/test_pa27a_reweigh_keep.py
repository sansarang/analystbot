"""PA-27-a 계약 — 재판정이 기존 가감을 지우지 않는다.

🔴 실측 2026-09-17: `adj={'주전결장': -1.5}` 에 홈 결장 1명을 더하니
   `adj_after={}` 가 되고 확률이 **0.55 → 0.5575 로 올랐다.**
   결장을 확인했는데 홈이 유리해지는 거꾸로 된 신호였다.

   지점: `kept, dropped = A.drop_small(merged)` — `drop_small` 이 각 변수를
   **개별로** 보고 |1.5| < 2.0 이라 **기존 것까지** 버렸다.

⚠️ 기존 가감은 **이미 이 규칙을 통과해** adj_pp 에 들어온 값이다. U8 의
   "contrib < 2%p 제외"는 adj 를 **만들 때** 거는 규칙이다.
"""
import pytest

from app.engine import adjust as A
from app.engine import rejudge as RJ

BASE = {"주전결장": -1.5}
PLAYERS = {"A": {"importance": 1.2}, "B": {"importance": 1.4},
           "C": {"importance": 1.3}}


def _run(diff, adj=None, p=0.55):
    return RJ.reweigh(adj=dict(BASE if adj is None else adj), p_code=p,
                      diff=diff, players=PLAYERS, grade="중")


def test_기존_가감이_보존된다():
    g = _run({"home": {"bench_notable": ["A"], "surprise_in": []}})
    assert "주전결장" in g["adj_after"]
    assert g["adj_after"]["주전결장"] == -1.5


def test_한_명_결장은_확률을_안_올린다():
    """🔴 결장을 확인했는데 홈이 유리해지면 신호가 거꾸로다."""
    g = _run({"home": {"bench_notable": ["A"], "surprise_in": []}})
    assert g["p_code_after"] <= 0.55


def test_두_명_결장은_확률을_내린다():
    """합 3.0%p 는 문턱(2.0)을 넘는다 — 반영돼야 한다."""
    g = _run({"home": {"bench_notable": ["A", "B"], "surprise_in": []}})
    assert g["p_code_after"] < 0.55
    assert "라인업결장:home" in g["adj_after"]


def test_원정_결장은_홈에_유리하다():
    g = _run({"away": {"bench_notable": ["A", "B"], "surprise_in": []}})
    assert g["p_code_after"] > 0.55


def test_복귀는_반대_방향이다():
    g = _run({"home": {"bench_notable": [], "surprise_in": ["A"]}})
    assert g["p_code_after"] > 0.55
    assert "라인업복귀:home" in g["adj_after"]


def test_잡음은_여전히_제외된다():
    """🔴 반대 위험 — U8 규칙을 없애는 것이 아니다. **새로 더한 것**에만 건다."""
    g = _run({"home": {"bench_notable": ["A"], "surprise_in": []}})
    assert "라인업결장:home" not in g["adj_after"]
    assert "라인업결장:home" in (g.get("adj_dropped_after") or {})


def test_diff가_없으면_아무것도_안_바꾼다():
    """🔴 반대 위험 — 종전 동작 그대로."""
    g = _run(None)
    assert g["adj_after"] == BASE
    assert g["changed"] is False


def test_변화_인원_0이면_안_바꾼다():
    g = _run({"home": {"bench_notable": [], "surprise_in": []}})
    assert g["changed"] is False
    assert g["adj_after"] == BASE


def test_기존_가감이_비어도_터지지_않는다():
    g = _run({"home": {"bench_notable": ["A", "B"], "surprise_in": []}}, adj={})
    assert g["p_code_after"] is not None


def test_문턱을_손으로_안_적었다():
    """🔴 사본 금지 — 2.0 은 adjust 가 원본이다."""
    import inspect
    # ⚠️ **주석이 아니라 코드 줄**만 본다. 주석에 "문턱(2.0)"이라 설명한 것을
    #    결함으로 세면 설명을 못 쓰게 된다(처음에 그렇게 잡았다).
    code = [ln for ln in inspect.getsource(RJ.reweigh).splitlines()
            if ln.strip() and not ln.strip().startswith("#")]
    body = "\n".join(code)
    assert "A.drop_small(" in body, "잡음 제외를 직접 구현했다"
    assert "2.0" not in body, "문턱을 손으로 적었다"
    assert A.MIN_CONTRIB_PP == 2.0


@pytest.mark.parametrize("side,want_sign", [("home", -1), ("away", 1)])
def test_부호가_홈_기준이다(side, want_sign):
    g = _run({side: {"bench_notable": ["A", "B", "C"], "surprise_in": []}})
    delta = g["p_code_after"] - 0.55
    assert delta * want_sign > 0
