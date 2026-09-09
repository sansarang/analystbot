"""[MKT-5] 괴리를 **변수**로 등록한다 — 자료가 아니라 변수다.

🔴 **왜 이 형태인가.** 앞서 MKT-4 로 시장 확률을 **자료15**(판정 입력)로
   줘 봤고, A/B 가 막았다:
       |p − 시장| 중앙값 OFF 0.0163 → ON 0.0061 · 평균 0.0187 → 0.0060
       수축률 **+67.9%** · ON 반복 2회가 전부 동일값(0.53/0.53 · 0.55/0.55 …)
   프롬프트에 "베끼지 마라 · 정답이 아니다"를 명시했는데도 **판정이 시장
   숫자에 고정됐다.** 앵커링이 지시보다 강하다. 그래서 자료로는 주지 않는다.

✅ **변수는 판정 뒤에 만들어진다.** `p_home` 이 이미 확정된 다음이라
   오염 경로가 **구조적으로 없다.** 그리고 변수는 이 시스템이 이미
   - 원장에 적재하고(`variable_ledger.record`)
   - 채점하며(`realized`/`actual`)
   - 자료14가 다음 회차에 조사한다 → **"왜 갈렸는지"가 거기서 나온다**

📐 **괴리의 뜻은 실측이 정한다** (운영 원장, 시장값 있는 141경기):
       |차| 0~2%p   n=23  우리 47.8% · 시장 47.8%
       |차| 2~4%p   n=20  우리 55.0% · 시장 55.0%
       |차| 4~8%p   n=39  우리 51.3% · 시장 43.6%
       |차| 8%p+    n=59  우리 49.2% · 시장 **69.5%**
   **8%p 넘게 갈릴 때만 시장이 이긴다.** 그래서 그 구간에서만 변수를 낸다 —
   4%p 대역까지 변수를 내면 잡음이고, 잡음이 잦으면 변수 대장이 죽는다.
"""
from __future__ import annotations


def _v(mkt, ours):
    from app.engine.market_variable import divergence_variable

    return divergence_variable({"p_market_send": mkt, "p_claude": ours,
                                "home": "H팀", "away": "A팀"})


def test_큰_괴리는_변수가_된다():
    v = _v(0.52, 0.66)          # 14%p
    assert v, "8%p 넘게 갈렸는데 변수를 안 냈다"
    assert "14.0%p" in v


def test_작은_괴리는_변수가_아니다():
    """⚠️ 실측상 8%p 아래에서는 시장이 우리를 못 이긴다 — 잡음을 만들지 않는다."""
    assert _v(0.52, 0.56) is None      # 4%p
    assert _v(0.55, 0.57) is None      # 2%p


def test_시장값이_없으면_변수도_없다():
    assert _v(None, 0.66) is None
    assert _v(0.52, None) is None


def test_방향은_시장_쪽이다():
    """괴리가 실현된다는 것은 **시장이 맞았다**는 뜻이다."""
    assert "원정 방향" in _v(0.40, 0.60)     # 시장은 원정 우세
    assert "홈 방향" in _v(0.62, 0.42)       # 시장은 홈 우세


def test_변수_형식을_지킨다():
    """🔴 형식이 어긋나면 파서가 버리고 원장·조사·채점에서 통째로 빠진다."""
    from app.engine.variable_parse import parse_variable

    p = parse_variable(_v(0.52, 0.66))
    assert p is not None, "형식 위반 — 정량 파싱 불가"
    assert p["n"] == 14.0
    # ⚠️ 파서가 `홈`→`home` 으로 정규화한다 — 원문이 아니라 파서 규약을 본다.
    assert p["side"] in ("home", "away")
    assert p["m"] == 0.0, "이미 반영된 것이 아니다 — 기반영은 0 이어야 한다"


def test_발생확률은_실측에서_온다():
    """지어낸 수가 아니라 우리 원장에서 잰 수다 (8%p+ 대역 시장 적중 69.5%)."""
    from app.engine.market_variable import MARKET_WIN_RATE_PP8

    assert 0.60 <= MARKET_WIN_RATE_PP8 <= 0.75
    assert f"{MARKET_WIN_RATE_PP8 * 100:.0f}%" in _v(0.52, 0.66)


def test_판정_뒤에_붙는다():
    """🔴 이 설계의 전부다 — 판정이 이 변수를 보면 앵커링이 되살아난다."""
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    i = src.index("async def _run_baseball_matchups")
    body = src[i:src.index("async def ", i + 10)]
    assert "market_variable" in body, "괴리 변수를 등록하지 않는다"
    assert body.index("judge_matchup(") < body.index("market_variable"), \
        "괴리 변수가 판정보다 앞에 있다 — 판정이 시장을 보게 된다"
    # 그리고 **변수 적재보다는 앞**이어야 원장에 실린다
    assert body.index("market_variable") < body.index("variable_ledger"), \
        "괴리 변수가 원장 적재보다 뒤다 — 등록해도 원장에 안 들어간다"
