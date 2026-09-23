"""[F-17 + HYC-4] **질문의 출처를 시장에서 사전값으로.**

사용자 2026-09-23: "지시 분석하는게 페이블 분석법 맞니?" → 측정 → "둘다 해라"
갈림길 결정: **(가) 해석(refuted_means)은 게이트가 계속 정한다.**

🔴 실측 (7일) — 가설이 **게이트의 함수**였다:
```
게이트      가설       경기      조사 변수
동의       H_deriv     48      3개 고정
가치의심     H_break     30      6개 고정
시장과대     H_fade      24      6개 고정
→ 게이트 5종 · 조합 7종  (조합 수 == 게이트 수)
```
즉 **시장을 보기 전에는 무엇을 조사할지 몰랐다.** CLAUDE.md 는 그것을 금한다:
> "떼는 것은 **조사 방향**이다 — 무엇을 조사할지는 우리 사전값이 정한다."
그리고 같은 문서가 "F-17(시장 없이도 가설)은 미착수"라고 적고 있었다.

🔴 **질문은 하나다** — "우리 사전 판단을 무너뜨릴 근거". 게이트를 안 본다.
🔴 **해석은 게이트가 정한다**(사용자 결정 (가)) — 시장과대에서 반증 없음이
   '철회'인 것은 그대로다. 질문만 떼고 해석은 시장을 본다.

🔴 [HYC-4] 변수 목록도 **경기별**이어야 한다. 종전에는 `H_break` 40회가
   전부 같은 6개였다 — "그 판단을 무너뜨릴 근거"는 경기마다 다르다.
"""
from __future__ import annotations

import inspect

import pytest

from app.flow import labels as L
from app.flow.nodes import n04_hyp as N4


class _S:
    sport = "baseball"
    league = "KBO"
    home = "두산"
    away = "KIA"
    hyp_side = "home"    # [SIDE-2] ④는 조사 방향을 본다
    pick_side = "home"
    game_id = "1"

    def __init__(self, gate, *, prior=None, market=None):
        self.n03_gate = {"gate": gate, "gap_pp": 3.0}
        self.n01_prior = prior or {"p_home": 0.58, "p_away": 0.42,
                                   "source": "team_elo"}
        self.n02_market = market or {"p": {"home": 0.55, "away": 0.45}}
        self.n04_hyp = None


async def _hyp(gate, **kw):
    st = _S(gate, **kw)
    out = await N4.run(st, None)
    return (out.n04_hyp or [{}])[0]


# ── F-17: 질문이 게이트에서 안 나온다 ──────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("gate", [L.AGREE, L.DOUBT, L.OVER, L.PRIOR_ONLY])
async def test_질문이_언제나_사전값을_무너뜨리는_것이다(gate):
    """🔴 이 단위의 전부 — 게이트가 달라도 **묻는 것은 같다.**"""
    h = await _hyp(gate)
    assert h.get("id") == "H_break", h
    assert "무너뜨릴" in str(h.get("text")), h


@pytest.mark.asyncio
async def test_조사_변수가_게이트와_무관하다():
    """🔴 종전에는 `동의`만 3개였다(파생만 본다)."""
    got = {}
    for gate in (L.AGREE, L.DOUBT, L.OVER):
        h = await _hyp(gate)
        got[gate] = sorted(v["var"] for v in (h.get("vars") or []))
    assert got[L.AGREE] == got[L.DOUBT] == got[L.OVER], got


# ── 사용자 결정 (가): 해석은 게이트가 정한다 ────────────────────────

@pytest.mark.asyncio
async def test_시장과대는_여전히_철회다():
    """🔴 **갈림길의 결정이다.** 질문을 떼도 해석은 시장을 본다 —
    시장이 우리보다 훨씬 높게 보는데 반대 근거를 못 찾으면 시장이 맞다."""
    assert (await _hyp(L.OVER)).get("refuted_means") == L.R_RETRACT


@pytest.mark.asyncio
async def test_가치의심은_강화다():
    assert (await _hyp(L.DOUBT)).get("refuted_means") == L.R_STRENGTHEN


@pytest.mark.asyncio
async def test_동의는_중립이고_파생_마켓을_지정한다():
    """⚠️ 파생 마켓 지정은 **걸 대상**이지 질문이 아니다 — 그대로 둔다."""
    h = await _hyp(L.AGREE)
    assert h.get("refuted_means") == L.R_NEUTRAL, h
    assert h.get("market") == "total", h


@pytest.mark.asyncio
async def test_시장이_없으면_마켓을_지정하지_않는다():
    h = await _hyp(L.PRIOR_ONLY)
    assert h.get("market") is None, h


# ── HYC-4: 변수가 경기별로 갈린다 ──────────────────────────────────

@pytest.mark.asyncio
async def test_사전값이_강할수록_핵심을_앞에_둔다():
    """🔴 [HYC-4] "그 판단을 무너뜨릴 근거"는 경기마다 다르다. 사전값이
    셀수록 그것을 깨뜨릴 **핵심 변수**를 먼저 묻는다."""
    strong = await _hyp(L.DOUBT, prior={"p_home": 0.72, "p_away": 0.28})
    order = [v["var"] for v in strong.get("vars") or []]
    cores = [v["var"] for v in strong.get("vars") or [] if v.get("is_core")]
    assert order[:len(cores)] == cores, f"핵심이 앞에 없다: {order}"


@pytest.mark.asyncio
async def test_경기마다_조사_순서가_달라질_수_있다():
    """🔴 종전에는 `H_break` 40회가 **전부 같은 목록**이었다."""
    a = await _hyp(L.DOUBT, prior={"p_home": 0.72, "p_away": 0.28})
    b = await _hyp(L.DOUBT, prior={"p_home": 0.51, "p_away": 0.49})
    assert [v["var"] for v in a["vars"]] != [v["var"] for v in b["vars"]] or \
        a.get("why") != b.get("why"), "경기가 달라도 가설이 똑같다"


@pytest.mark.asyncio
async def test_왜_그걸_묻는지_적는다():
    """⚠️ 조용한 목록을 만들지 않는다 — 사용자가 읽을 이유가 붙는다."""
    h = await _hyp(L.DOUBT, prior={"p_home": 0.72, "p_away": 0.28})
    assert h.get("why"), h
    assert "72" in str(h["why"]) or "0.72" in str(h["why"]), h["why"]


@pytest.mark.asyncio
async def test_사전값이_없으면_지어내지_않는다():
    h = await _hyp(L.DOUBT, prior={})
    assert h.get("vars"), "변수까지 사라지면 안 된다"
    assert h.get("id") == "H_break"


# ── 규약 ────────────────────────────────────────────────────────────

def test_LLM_을_부르지_않는다():
    import ast

    tree = ast.parse(inspect.getsource(N4))
    calls = {getattr(c.func, "id", "") or getattr(c.func, "attr", "")
             for c in ast.walk(tree) if isinstance(c, ast.Call)}
    for banned in ("complete_json", "ask_json", "generate", "post"):
        assert banned not in calls, banned


def test_변수_이름을_손으로_적지_않았다():
    """🔴 원본은 `config/rules.yaml` 이다(사본 금지)."""
    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(N4.run).splitlines())
    for name in ("starter_recent3", "bullpen_3d", "xi_confirmed"):
        assert name not in src, f"{name} 을 손으로 적었다"
