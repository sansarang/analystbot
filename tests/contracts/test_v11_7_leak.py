"""🔴🔴 **ⓐ 누설 금지 — `as_of` 필수** — 사용자 지시 2026-10-12.

> ⓐ 누설(1순위): `_history`만이 아니라 과거 경기·라인업·골 시간·xG·Elo를 읽는
> 모든 함수를 grep으로 목록화 → 전부 `as_of` 인자 **필수**(기본값 없음, 없으면
> 예외). 계약 L1: as-of 재현에서 킥오프 시각 **이후** 경기가 어떤 목록에도 없다
> (**분석 대상 경기 자신 포함**).

🔴 왜 1순위인가(실사고 2026-10-12 가와사키–나고야 재현): `_history` 가 *"끝난
   경기"* 만 거르고 as-of 를 안 봐서, 재현 카드의 폼 목록에 **그 경기 자신**
   (1-2 · xG 0.85/1.04)이 들어갔다. 누설된 계수·재현으로는 다른 고침의 효과를
   판단할 수 없다.
"""
from __future__ import annotations

import inspect
from datetime import UTC, datetime

#: 🔴 as-of 기준 시각 — 이 시각 **이후** 경기는 어떤 목록에도 없어야 한다
AS_OF = datetime(2026, 10, 11, 6, 26, tzinfo=UTC)

#: 🔴 과거 자료를 고르는 **입구 목록**(2026-10-12 grep 으로 찍었다)
#  ⚠️ 새 입구가 생기면 여기 더한다 — 빠지면 그 길로 누설이 다시 들어온다.
GATES: tuple[tuple[str, str], ...] = (
    ("app.core.stages.s2e_matchup", "_history"),
    ("app.collect.fotmob", "team_recent"),
    ("app.collect.leagueelo", "_rows"),
)


def test_every_gate_requires_as_of() -> None:
    """🔴🔴 **Elo 를 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*.

    ⚠️ 이 시험(test_every_gate_requires_as_of)이 지키던 것은 **기준 확률(Elo → 승·무·패)** 경로다.
    🔴 **확률은 이미 그 수를 안 보고 있었다** — 승무패는 `flat_prob`
       (1/3 균등 + 변수)이 내고 `probmodel.run` 은 `floor` 를 안 읽는다.
       쓰이던 곳은 카드의 **기준 열**과 **방향 판정**뿐이었고 둘 다 표시인데,
       `eloratings.net/World.tsv` 를 **매 실행** 받고 있었다.
    🔴 그래서 지웠고, 이 시험은 *"되살아나지 않는다"* 를 지킨다.
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    #  ① Elo 모듈 넷이 **없다**
    for rel in ("app/collect/elo.py", "app/collect/leagueelo.py",
                "app/core/domesticelo.py"):
        assert not (root / rel).exists(), f"🔴 `{rel}`(Elo)가 되살아났다"
    #  ② 기준 확률 함수가 **없다**
    from app.core import base as _b
    for one in ("we", "triple_of", "triple_from", "base_prob"):
        assert not hasattr(_b, one), f"🔴 `core.base.{one}`(Elo)가 되살아났다"
    from app.core.stages import s2b_base as _s2b
    for one in ("_base", "continental_elo", "league_level"):
        assert not hasattr(_s2b, one), f"🔴 `s2b_base.{one}`(Elo)가 되살아났다"
    #  ③ ② 는 **남아 있다** — 오늘 XI 가 평소보다 약/강한가는 Elo 를 안 쓴다
    for one in ("strength_of", "fill_values", "adjust"):
        assert hasattr(_b, one), f"🔴 `core.base.{one}`(선수 전력)이 같이 지워졌다"
    #  ④ 기준은 **늘 비어 있고 사유가 붙는다**(#3 조용한 0 금지)
    said = (root / "app/core/stages/s2b_base.py").read_text(encoding="utf-8")
    assert "BaseProb(probs=None" in said, "🔴 기준을 빈 값으로 안 낸다"
    assert "기준(Elo)은 지웠다" in said, "🔴 그 사실을 사유에 안 적는다"


def test_rows_after_as_of_are_dropped() -> None:
    """🔴 L1 — **그 경기 자신**과 이후 경기가 목록에서 빠진다."""
    from app.collect import fotmob as fm
    rows = [
        {"utc": "2026-10-05T10:00:00Z", "finished": True},
        {"utc": "2026-10-11T07:00:00Z", "finished": True},   # 🔴 분석 대상
        {"utc": "2026-10-12T07:00:00Z", "finished": True},   # 🔴 그 뒤
    ]
    got = fm.before_as_of(rows, as_of=AS_OF)
    assert [r["utc"][:10] for r in got] == ["2026-10-05"], got


def test_gate_refuses_a_missing_as_of() -> None:
    """🔴 *"없으면 예외"* — `None` 을 주면 거부한다(조용히 넘어가지 않는다)."""
    import pytest

    from app.collect import fotmob as fm
    with pytest.raises(ValueError):
        fm.before_as_of([{"utc": "2026-10-05T00:00:00Z"}], as_of=None)


def test_naive_as_of_is_refused() -> None:
    """⚠️ tz 없는 시각은 거부한다 — naive 가 새면 창 판단이 거짓이 된다."""
    import pytest

    from app.collect import fotmob as fm
    with pytest.raises(ValueError):
        fm.before_as_of([{"utc": "2026-10-05T00:00:00Z"}],
                        as_of=datetime(2026, 10, 11, 6, 26))


def test_history_passes_as_of_down() -> None:
    """🔴 `_history` 가 받은 `as_of` 로 **거른다**(글자로 센다)."""
    said = inspect.getsource(
        __import__("app.core.stages.s2e_matchup", fromlist=["x"])._history)
    assert "before_as_of" in said, said[:200]


def test_fit_tools_pass_as_of() -> None:
    """🔴 감사 — 백필·적합 도구가 `as_of` 를 넘긴다(미래를 본 계수 금지)."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    for rel in ("tools/fit_state_rates.py", "tools/fit_matchup_model.py"):
        said = (root / rel).read_text(encoding="utf-8")
        assert "as_of" in said, rel


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **맞대결에도 문을 건다** — 실사고 2026-10-12(광주–울산 as-of 재현)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 끝난 경기의 맞대결 표에는 **그 경기 자신**이 들어 있었다(광주 4-3 울산) —
#     가설이 그 스코어를 근거로 적었다. 🔴 날짜만 있는 줄이라 자정으로 읽혀
#     "킥오프보다 앞"으로 통과했다.


def test_day_strict_drops_the_same_day() -> None:
    """🔴 `day_strict` — **같은 날** 줄은 버린다(날짜만 있는 표의 자기 경기)."""
    from app.collect import fotmob as fm
    rows = [{"date": "2026-10-11", "score": "4-3"},
            {"date": "2026-07-05", "score": "1-1"}]
    got = fm.before_as_of(rows, as_of=datetime(2026, 10, 11, 5, 0,
                                               tzinfo=UTC),
                          key="date", day_strict=True)
    assert [r["date"] for r in got] == ["2026-07-05"], got


def test_h2h_goes_through_the_one_door() -> None:
    """🔴 `parse_h2h` 가 **그 문**으로 거른다(글자로 센다 · 사본 금지)."""
    said = inspect.getsource(
        __import__("app.collect.fotmob", fromlist=["x"]).parse_h2h)
    assert "before_as_of" in said and "day_strict=True" in said, said[:200]
