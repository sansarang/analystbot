"""[MKT-7] 죽어 있던 `T2_시장괴리` 를 괴리 변수로 살린다.

🔴 **T2 는 한 번도 발동한 적이 없다** (운영 실측 2026-09-09):
       딥서치 기록 400건 중 발동 87건 —
       T5_라인업이상 83 · T6_라인업최초확정 37 · T4_선발변경 25
       **T1 0 · T2 0 · T3 0**
       `edge_status` 는 원장 763건 전부 NULL

   T2 의 두 조건(`edge_status == "candidate"` · `market_divergence`)을 세팅하는
   곳은 `market_edge.py` 하나뿐인데, **그 모듈은 운영에서 아무도 안 부른다**
   (FINDINGS E-1, 오늘 확인: 참조 1곳은 주석이다). 배선된 채 죽어 있었다.

✅ **괴리는 `market_edge` 없이도 안다** — `p_market_send` 와 `p_claude` 뿐이고
   둘 다 판정 뒤에 손에 있다. MKT-5 가 이미 그 계산(`DIVERGENCE_PP=8.0`)을
   갖고 있으므로 **그것을 그대로 부른다**(사본 금지).

🔴 **왜 밖에서 찾아야 하는가.** 괴리 8%p 초과 59건에서 시장이 고른 팀은
       최근5 승률 우위 23/59 = **39.0%**  ← 오히려 열세
       최근5 득실차 우위 28/59 = 47.5% · 득점 우위 26/59 = 44.1%
       연승 중앙값 +1 · 3연승 11건 vs 3연패 7건
   **우리 자료로는 괴리가 설명되지 않는다.** 그런데 시장은 69.5% 맞는다.
   시장이 보는 것은 우리 자료 밖에 있다 — 그래서 딥서치다.
"""
from __future__ import annotations


def _jg(mkt, ours, **kw):
    jg = {"sport": "mlb", "p_claude": ours, "p_market_send": mkt,
          "matchup": {"우세": "home" if ours and ours > 0.5 else "away"}}
    jg.update(kw)
    return jg


def _trig(jg):
    from app.config import get_settings
    from app.engine.deepsearch import triggers

    return triggers(jg, get_settings())


def test_큰_괴리가_T2를_발동시킨다():
    from app.engine.deepsearch import T2_MARKET

    assert T2_MARKET in _trig(_jg(0.52, 0.66))     # 14%p


def test_작은_괴리는_발동시키지_않는다():
    """⚠️ 실측상 8%p 아래에서는 시장이 우리를 못 이긴다 — 크레딧을 태우지 않는다."""
    from app.engine.deepsearch import T2_MARKET

    assert T2_MARKET not in _trig(_jg(0.52, 0.56))  # 4%p
    assert T2_MARKET not in _trig(_jg(0.55, 0.57))  # 2%p


def test_시장값이_없으면_발동하지_않는다():
    from app.engine.deepsearch import T2_MARKET

    assert T2_MARKET not in _trig(_jg(None, 0.66))


def test_옛_경로도_그대로_산다():
    """⚠️ `market_edge` 가 언젠가 배선되면 그 경로도 계속 T2 를 켜야 한다."""
    from app.engine.deepsearch import T2_MARKET

    assert T2_MARKET in _trig(_jg(None, 0.60, edge_status="candidate"))
    assert T2_MARKET in _trig(_jg(None, 0.60, market_divergence=True))


def test_임계값을_두_곳에_적지_않는다():
    """🔴 괴리 임계는 `market_variable.DIVERGENCE_PP` 하나뿐이다."""
    from pathlib import Path

    src = Path("app/engine/deepsearch.py").read_text(encoding="utf-8")
    assert "DIVERGENCE_PP" in src, "임계값을 딥서치가 직접 적었다 — 사본이다"
    assert "8.0" not in src.split("T2 —")[1][:600], "숫자를 손으로 박았다"
