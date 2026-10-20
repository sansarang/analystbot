"""🔴🔴 **방향 줄은 우리 확률만 있어도 적는다** — 예측 지시 2026-10-13 §0.

> 배당·시장 확률 쓰지 않는다 … **결론은 봇 확률(%)만으로**.

⚠️ 실측 2026-10-13(ACL 세 경기): 기준(Elo)도 시장도 없어 열이 **우리 하나**였고
   `pipeline._direction` 이 **아예 안 돌아** 방향 줄이 빈 글자였다 → 카드가
   *"🔴 방향 줄이 비었다 — 이것은 결함이다(§2-2)"* 를 찍었다.
🔴 **DR1** 한 열뿐이면 그 열의 0.15 차로 정한다 · **DR2** 그때 *"열이 하나"* 라는
   사실을 글자에 남긴다(두 열이 동의한 것처럼 보이지 않게) · **DR3** 세 열 규칙은
   그대로다(열이 둘 이상이면 2열 이상이 앞세울 때만 팀을 적는다).
"""
from __future__ import annotations


def _ref():
    from app.core.schema import MatchRef
    return MatchRef(id="m", sport="soccer",
                    competition="AFC Champions League Elite",
                    competition_short="ACLE",
                    home="team:000001", away="team:000002",
                    home_name="HOME", away_name="AWAY",
                    kickoff_utc="2026-10-13T10:00:00Z")


def _triple(h, d, a):
    from app.core.schema import ProbTriple
    return ProbTriple(home=h, draw=d, away=a)


def test_single_column_decides() -> None:
    """🔴 **DR1·DR2** — 우리 열 하나로 정하고 그 사실을 적는다."""
    from app.core import compare as survive
    from app.core.schema import BaseProb, MarketProb
    got = survive.direction_line(BaseProb(probs=None, why="x"),
                                 _triple(0.52, 0.18, 0.30), MarketProb(),
                                 _ref())
    assert "HOME" in got and "하나" in got, got


def test_single_column_can_be_even() -> None:
    from app.core import compare as survive
    from app.core.schema import BaseProb, MarketProb
    got = survive.direction_line(BaseProb(probs=None, why="x"),
                                 _triple(0.34, 0.24, 0.42), MarketProb(),
                                 _ref())
    assert "반반" in got and "하나" in got, got


def test_three_column_rule_unchanged() -> None:
    """🔴 **DR3** — 열이 둘이면 **둘 다 0.15 이상** 앞세워야 팀을 적는다."""
    from app.core import compare as survive
    from app.core.schema import BaseProb, MarketProb
    got = survive.direction_line(BaseProb(probs=_triple(0.5, 0.2, 0.3),
                                          why="x"),
                                 _triple(0.52, 0.18, 0.30), MarketProb(),
                                 _ref())
    assert "HOME" in got and "두" not in got.split("—")[0] or "열" in got, got
    said = survive.direction_line(BaseProb(probs=_triple(0.36, 0.28, 0.36),
                                           why="x"),
                                  _triple(0.37, 0.26, 0.37), MarketProb(),
                                  _ref())
    assert "반반" in said, said


def test_pipeline_calls_it_without_base_or_market() -> None:
    """🔴 배선 — 기준·시장이 없어도 `_direction` 이 줄을 만든다."""
    import inspect

    from app.core import pipeline as pl
    said = inspect.getsource(pl._direction)
    assert "said_ours is None" in said
    assert "direction_line" in said
