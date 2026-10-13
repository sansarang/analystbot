"""🔴🔴 **§5-3 대륙 클럽 대회** — 리그 오프셋 · 대회 홈 이점(CC1·CC2·CC3).

> 계약 **CC1**: 국내 리그 홈 이점·Elo 를 **오프셋 없이** 대륙 대회에 쓰면 실패.
> **CC2**: 오프셋 계산에 `as_of` 이후 경기 실패. **CC3**: 중립 경기에 홈 이점
> 적용 실패. (지시서 2026-10-13 밤 셋째 §5-3)

🔴 왜 **지금** — `rules.goal_baseline("league:UCL")` 이 열쇠 앞머리(`league`)로
   떨어져 **국내 리그 9개 합계**(경기당 2.7458 · 홈 몫 없음)를 조용히 빌렸다
   (실측 2026-10-13). 그것이 CC1 이 막으려는 바로 그 일이다.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

AT = datetime(2026, 10, 13, tzinfo=timezone.utc)


# ══════════════════════════════════════════════════════════════════
# 🔴 CC1 — 빌리지 않는다
# ══════════════════════════════════════════════════════════════════

def test_continental_does_not_borrow_the_domestic_baseline() -> None:
    """🔴🔴 **CC1** — 대륙 대회는 국내 리그 기준을 **빌리지 않는다**.

    🔴 **빈 칸이어야 한다는 뜻이 아니다** — *"그 대회 자체 실측이거나, 아니면
       없다"* 는 뜻이다(§5-3-c). 그래서 두 가지만 센다:
       ① 앞머리 퇴로(`kinds.league` 합계)와 **같은 수가 아니다**
       ② 있으면 그 `source` 가 **그 대회 자체 실측**이라고 말한다.
    ⚠️ 2026-10-13 에 ACLE·ACL2·UCL 은 `tools/fit_comp_goals.py` 로 **실측**해
       적었다(ACLE 235경기 · ACL2 254 · UCL 370 · 중립 단계 제외).
    """
    from app import rules
    said_pool = dict(rules.goal_baseline("league:fotmob9999"))
    for key in ("league:UCL", "league:ACLE", "league:ACL2"):
        got = rules.goal_baseline(key)
        if not got:
            continue                      # 🔴 없는 것도 맞다(미산출)
        assert got.get("goals_per_match") != said_pool.get("goals_per_match"), \
            (key, "🔴 국내 리그 합계를 그대로 쓰고 있다(CC1)")
        assert key in str(got.get("source") or ""), (key, got.get("source"))
        assert "자체 실측" in str(got.get("source") or ""), got.get("source")


def test_domestic_league_still_falls_back() -> None:
    """⚠️ 국내 리그는 그대로다 — 앞머리 퇴로가 살아 있다(회귀 방지)."""
    from app import rules
    assert rules.goal_baseline("league:PL").get("goals_per_match")
    # 🔴 표에 없는 **국내** 리그 열쇠는 앞머리(`league`) 합계로 떨어진다
    assert rules.goal_baseline("league:fotmob9999").get("goals_per_match")


def test_score_needs_the_offset() -> None:
    """🔴 **CC1** — 오프셋이 없으면 대회 점수도 **없다**(국내 Elo 그대로 금지)."""
    from app.core import offsets as off
    got, why = off.score_of(elo=1500.0, league="league:J1",
                            confederation="AFC", as_of=AT)
    assert got is None and ("미산출" in why or "🔴" in why), why


def test_home_advantage_is_not_borrowed() -> None:
    """🔴 **CC1** — 대회 홈 이점 판이 없으면 `None`(국내 값을 안 빌린다)."""
    from app.core import offsets as off
    got, why = off.home_of("league:UCL", as_of=AT, stage="league phase")
    assert got is None and "빌리지 않는다" in why, why


# ══════════════════════════════════════════════════════════════════
# 🔴 CC2 — 판은 `as_of` 이전만
# ══════════════════════════════════════════════════════════════════

def test_plate_comes_from_versions_pick_file() -> None:
    """🔴 **CC2** — **확률에 쓰는** 판 고르기는 `versions.pick_file` 하나다.

    ⚠️ 범위를 함수로 좁혔다 — `plate_of`·`of`·`score_of`·`home_of` 는 확률
       경로가 보는 길이고 거기서 날짜를 직접 고르면 안 된다. 🔴 **표시 전용**
       함수(`latest_plate`·`league_of`·`gap_said` · P1 "리그 간 전력 차")는
       *"가장 최근 판"* 을 읽는다 — 그 수는 확률에 닿지 않는다(계약 LG5).
    """
    import ast
    import inspect
    from app.core import offsets as off
    for fn in (off.plate_of, off.of, off.score_of, off.home_of):
        said = ast.unparse(ast.parse(inspect.getsource(fn)))
        assert "glob(" not in said and "sorted(" not in said, fn.__name__
    assert "pick_file" in ast.unparse(
        ast.parse(inspect.getsource(off.plate_of)))
    # 🔴 표시 전용 함수는 **그렇다고 적혀 있어야** 한다
    said_mod = inspect.getsource(off)
    assert "표시 전용" in said_mod or "표시만" in said_mod


def test_naive_as_of_is_refused() -> None:
    """🔴 **CC2** — 시간대 없는 `as_of` 는 받지 않는다(누설 규율)."""
    from app.core import offsets as off
    with pytest.raises(ValueError):
        off.plate_of(confederation="UEFA", as_of=datetime(2026, 10, 13))


# ══════════════════════════════════════════════════════════════════
# 🔴 CC3 — 중립은 0
# ══════════════════════════════════════════════════════════════════

def test_neutral_stage_has_no_home_advantage() -> None:
    """🔴🔴 **CC3** — 중립(결승)이면 배율 **1.0** 이다."""
    from app.core import offsets as off
    got, why = off.home_of("league:UCL", as_of=AT, stage="Final")
    assert got == 1.0 and "중립" in why, why


def test_min_sample_is_twenty() -> None:
    from app.core import offsets as off
    assert off.MIN_GAMES == 20
