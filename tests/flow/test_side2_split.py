"""[SIDE-2] `pick_side` 가 두 일을 겸하고 있었다 — 나눈다.

사용자 2026-09-23: "페이블처럼 경기분석을 해야 한다..논문을 찾아서 프로그램
수정해라...딥서치를 하든..." → 계획 승인

🔴 **한 칸이 서로 다른 두 질문에 답하고 있었다.**
```
무엇을 조사할까 (③④⑤)   ← 사전값이 맞다. 시장을 보면 앵커링이고 CLV 가 안 선다
누구를 고르나   (⑦⑧⑨⑪⑫⑬) ← 최종 확률이 맞다 (사용자 결정)
```
둘 다 ①이 정하는 바람에, 확률은 시장에서 나오므로 ①과 시장이 갈리면
**고른 쪽의 승률이 50% 미만**이 됐다 — 실측 30일 **17/58 = 29.3%**.

실측 근거 (walk-forward · 누수 없음 · docs/FORKS.md F-22):
```
model_w    KBO(n=76)  NPB(n=92)  MLB(n=294)   ← 섞을수록 단조 악화. 0.0 이 정답
  0.0 ★    0.65837    0.65281    0.65945
  1.0      0.67371    0.68661    0.69181

괴리 12%p~ 적중  사전값 64.3/45.5/56.2  vs  시장 71.4/90.9/78.1
```
"""
from __future__ import annotations

import ast
import inspect

import pytest

from app.flow.nodes import n01_prior as N1
from app.flow.nodes import n03_gate as N3
from app.flow.nodes import n04_hyp as N4
from app.flow.nodes import n05_evidence as N5
from app.flow.nodes import n07_adjust as N7
from app.flow.nodes import n08_pcode as N8


def _code(obj) -> str:
    """독스트링·주석을 뗀 **코드 본문**.

    🔴 원문 grep 은 "`pick_side` 를 안 쓴다"는 **설명 자체**에 걸린다 —
       이 저장소가 겪은 D46 이 13회다.
    """
    tree = ast.parse(inspect.getsource(obj).strip())
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not (body and isinstance(body, list)):
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            body.pop(0)
    return ast.unparse(tree)


class _S:
    run_id = "r1"
    game_id = "7"
    sport = "baseball"
    league = "KBO"
    home = "두산"
    away = "KIA"
    hyp_side = "home"
    pick_side = "home"
    n01_prior = {"p_home": 0.5046, "p_draw": None, "p_away": 0.4954}
    n02_market = {"p": {"home": 0.48, "draw": None, "away": 0.52},
                  "odds": {"home": 2.05, "away": 1.85}, "market_missing": False}
    n03_gate = {"gate": "가치의심"}
    n07_adjust = []


class _Ctx:
    inject = {}
    pool = None


# ── 누가 무엇을 읽나 ────────────────────────────────────────────────

def test_조사_방향은_사전값이_정한다():
    """🔴 ③④⑤는 `hyp_side` 만 본다 — 시장이 고른 쪽을 조사하면 앵커링이다."""
    for fn in (N3.run, N4.run, N4._prior_strength):
        src = _code(fn)
        assert "hyp_side" in src, f"{fn.__qualname__} 이 조사 방향을 안 읽는다"
        assert "pick_side" not in src, f"{fn.__qualname__} 이 아직 픽을 읽는다"


def test_수집도_사전값_방향을_본다():
    """🔴 ⑤ 전체에 `state.pick_side` 가 한 곳도 없어야 한다."""
    src = inspect.getsource(N5)
    assert "state.pick_side" not in src, "⑤가 아직 픽 방향으로 수집한다"
    assert "state.hyp_side" in src


def test_가설이_시장을_보지_않는다():
    """🔴 페이블식 순서의 핵심 — 판단이 먼저고 시장은 검증이다."""
    src = _code(N4.run)
    assert "n02_market" not in src, "가설이 시장을 읽는다 — 앵커링이다"


def test_조정은_홈_기준이다():
    """🔴 ⑦이 픽 기준이면 ⑧의 시장 기준과 어긋난다 — 그게 29.3% 의 자리다.

    ⚠️ **문자열이 아니라 AST 로 본다.** `ast.unparse` 가 따옴표를 바꿔서
       원문 대조는 거짓으로 실패한다(D46 의 친척).
    """
    tree = ast.parse(inspect.getsource(N7.run).strip())
    args = [c.args[1] for c in ast.walk(tree)
            if isinstance(c, ast.Call)
            and getattr(c.func, "id", "") == "_direction_of" and len(c.args) > 1]
    assert args, "⑦이 방향 부호를 안 낸다"
    for a in args:
        assert isinstance(a, ast.Constant) and a.value == "home", ast.dump(a)
    assert "pick_side" not in _code(N7.run)


def test_방향_부호가_반대칭이다():
    """🔴 홈 기준 표준화의 **전제**다. 반대칭이 아니면 원정 조정이 틀린다."""
    for d in ({"home": 1, "away": 0}, {"home": -1, "away": 1},
              {"home": 0, "away": 0}, {"home": 1, "away": 1}):
        assert N7._direction_of(d, "home") == -N7._direction_of(d, "away"), d


def test_사전값이_픽을_정하지_않는다():
    """🔴 ①은 조사 방향만 정한다."""
    src = _code(N1.run)
    assert "state.hyp_side =" in src
    i_h, i_p = src.index("state.hyp_side ="), src.index("state.pick_side =")
    assert i_h < i_p, "픽을 조사 방향보다 먼저 정한다"
    assert "state.pick_side = state.hyp_side" in src, "잠정값이 조사 방향이 아니다"


# ── ⑧이 픽을 정한다 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_조정이_픽을_뒤집는다():
    """🔴 **이 단위가 값을 내는 자리다.** 시장이 원정 우세여도 증거가 세면
    홈을 고른다 — 우리가 더하는 값이 거기 있다."""
    s = _S()
    s.n07_adjust = [{"pp": 4.0}]          # 홈 기준 +4%p
    await N8.run(s, _Ctx())
    assert s.pick_side == "home", s.n08_pcode
    assert s.n08_pcode["p_home"] == 0.52
    assert s.n08_pcode["p_code_pick"] == 0.52
    assert s.n08_pcode["sum_adj_pp"] == 4.0


@pytest.mark.asyncio
async def test_조정이_없으면_시장_우세측이다():
    s = _S()
    s.n07_adjust = []
    await N8.run(s, _Ctx())
    assert s.pick_side == "away"
    assert s.n08_pcode["p_code_pick"] == 0.52     # 1 − 0.48
    assert s.n08_pcode["p_home"] == 0.48


@pytest.mark.asyncio
async def test_원정_픽이면_조정_부호도_뒤집힌다():
    """⚠️ 표시는 **픽 기준**이다 — 홈에 −3%p 는 원정에 +3%p 다."""
    s = _S()
    s.n07_adjust = [{"pp": -3.0}]
    await N8.run(s, _Ctx())
    assert s.pick_side == "away"
    assert s.n08_pcode["p_home"] == 0.45
    assert s.n08_pcode["p_code_pick"] == 0.55
    assert s.n08_pcode["sum_adj_pp"] == 3.0, "픽 기준으로 안 돌렸다"


@pytest.mark.asyncio
@pytest.mark.parametrize("mkt_home,adj", [(0.48, 0.0), (0.48, 4.0), (0.48, -3.0),
                                          (0.64, 0.0), (0.36, 0.0), (0.50, 0.0),
                                          (0.64, -10.0), (0.36, 10.0)])
async def test_픽_확률은_항상_절반_이상이다(mkt_home, adj):
    """🔴 **29.3% 가 0 이 되는 계약이다.** 어떤 조합에서도 모순이 없다."""
    s = _S()
    s.n02_market = {"p": {"home": mkt_home, "draw": None, "away": 1 - mkt_home},
                    "odds": {"home": 2.0, "away": 2.0}, "market_missing": False}
    s.n07_adjust = [{"pp": adj}] if adj else []
    await N8.run(s, _Ctx())
    assert s.n08_pcode["p_code_pick"] >= 0.5, (mkt_home, adj, s.n08_pcode)
    assert s.pick_side in ("home", "away")


@pytest.mark.asyncio
async def test_시장이_없으면_조사_방향을_그대로_둔다():
    """⚠️ 사전값단독 경로 — ⑫⑬이 읽을 것이 있어야 한다."""
    s = _S()
    s.hyp_side = "away"
    s.pick_side = "away"
    s.n02_market = {"p": None, "market_missing": True}
    await N8.run(s, _Ctx())
    assert s.pick_side == "away"
    assert s.n08_pcode["p_code_pick"] is None
    assert s.n08_pcode["p_home"] is None


@pytest.mark.asyncio
async def test_상하한을_넘지_않는다():
    s = _S()
    s.n02_market = {"p": {"home": 0.97, "draw": None, "away": 0.03},
                    "odds": {"home": 1.03, "away": 20.0}, "market_missing": False}
    s.n07_adjust = [{"pp": 10.0}]
    await N8.run(s, _Ctx())
    assert s.n08_pcode["p_home"] == N8.P_MAX


# ── 축구: 무승부 질량 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_축구는_1빼기_홈이_원정이_아니다():
    """🔴 **구현 중에 내가 넣었다가 기존 가드가 잡은 결함이다.**
    (`test_종목_분기가_한_곳에만_있다`)

    축구 3-way 는 `홈 0.42 · 무 0.28 · 원정 0.30` 처럼 합이 1 이다.
    `1 − 홈 = 0.58` 을 원정으로 읽으면 **무승부를 원정 승리로 세는 것**이고,
    그러면 축구는 거의 언제나 원정 픽이 된다.
    """
    s = _S()
    s.sport = "soccer"
    s.n02_market = {"p": {"home": 0.42, "draw": 0.28, "away": 0.30},
                    "odds": {"home": 2.3, "draw": 3.4, "away": 3.1},
                    "market_missing": False}
    s.n07_adjust = []
    await N8.run(s, _Ctx())
    assert s.pick_side == "home", "무승부 질량을 원정으로 셌다"
    assert s.n08_pcode["p_code_pick"] == 0.42
    assert s.n08_pcode["p_away"] == 0.30, "1 − 홈 으로 만들었다"


@pytest.mark.asyncio
async def test_축구도_조정은_반대칭이다():
    """⚠️ 무승부는 조정에 안 쓸린다 — 홈에 +3%p 면 원정은 −3%p 다."""
    s = _S()
    s.sport = "soccer"
    s.n02_market = {"p": {"home": 0.42, "draw": 0.28, "away": 0.30},
                    "odds": {"home": 2.3, "draw": 3.4, "away": 3.1},
                    "market_missing": False}
    s.n07_adjust = [{"pp": -3.0}]
    await N8.run(s, _Ctx())
    assert s.n08_pcode["p_home"] == 0.39
    assert s.n08_pcode["p_away"] == 0.33
    assert s.pick_side == "home"


@pytest.mark.asyncio
async def test_야구는_양쪽이_1을_이룬다():
    """⚠️ 반대 위험 — 양쪽을 따로 받는다고 야구 값이 바뀌면 안 된다."""
    s = _S()
    s.n02_market = {"p": {"home": 0.48, "draw": None, "away": 0.52},
                    "odds": {"home": 2.05, "away": 1.85}, "market_missing": False}
    s.n07_adjust = [{"pp": -3.0}]
    await N8.run(s, _Ctx())
    assert s.n08_pcode["p_home"] == 0.45
    assert s.n08_pcode["p_away"] == 0.55
    assert round(s.n08_pcode["p_home"] + s.n08_pcode["p_away"], 4) == 1.0


@pytest.mark.asyncio
async def test_한쪽만_있으면_지어내지_않는다():
    """🔴 LED-1 부류 — ②가 안 만드는 모양으로 굴러오면 멈춘다."""
    s = _S()
    s.n02_market = {"p": {"away": 0.687}, "market_missing": False}
    await N8.run(s, _Ctx())
    assert s.n08_pcode["p_code_pick"] is None


# ── 되돌릴 길 ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_prior_로_되돌리면_종전_동작이다(monkeypatch):
    """🔴 나빠지면 한 줄로 되돌린다. 되돌릴 길을 막지 않는다."""
    monkeypatch.setattr(N8.R, "get",
                        lambda k, d=None: "prior" if k == "flow.pick_from" else d)
    s = _S()
    s.hyp_side = "home"
    s.n07_adjust = []
    await N8.run(s, _Ctx())
    assert s.pick_side == "home", "되돌림이 안 먹는다"
    assert s.n08_pcode["p_code_pick"] == 0.48, "종전처럼 50% 미만이 나와야 한다"


def test_기본값은_확률이다():
    from app.flow import rules as _R
    assert str(_R.get("flow.pick_from", "probability")) == "probability"


# ── 원장까지 이어진다 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_원장이_8의_방향을_받는다():
    """🔴 배선의 끝 — `record.pick_of` 는 `pick_side` 를 읽는다(SIDE-1)."""
    from app.flow import record as R

    s = _S()
    s.n07_adjust = [{"pp": -3.0}]
    await N8.run(s, _Ctx())
    s.n09_conf = {"grade": "B"}
    s.stop_reason = None
    side, ours, mkt = R.pick_of(s)
    assert side == "away" == s.pick_side
    assert ours == 0.55
    assert mkt == round(1 - 0.48, 4)
    assert R.price_of(s) == 1.85
