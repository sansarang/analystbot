"""🔴🔴 **§2 선수 점수 — 구간 ± · 팀 고정효과 · 시즌 교차 벌**(지시서 2026-10-13).

> 구간 플러스마이너스: 교체·골·퇴장 시점으로 구간 분할 → 응답 = 구간
> (득점−실점)/90분 · 설명 = 구간 출전 선수 ±1 · **팀 고정효과 항 포함**(팀이
> 좋아서 생긴 ± 제거) · 가중 = 구간 길이 × 시간 감쇠.
> 릿지 강도: **시즌 교차**. 출전 < 300분 → **리그·포지션 평균** 쪽 수축.
> 교체 시각 없는 리그: 경기 단위 판 — 표시 **"거친 판"**.
> 판 `data/player_pm/<league>/<as_of>.parquet` · 안정성: 시즌 반분 상관
> (0.3 미만 **"신뢰 낮음"**).

🔴 왜 팀 고정효과인가 — 한 팀의 11명은 거의 늘 함께 뛴다. 팀 항이 없으면 **팀의
   힘이 선수 점수로 새어** 강팀 선수가 모두 좋아 보인다(그러면 라인업 신호가
   "누가 강팀인가"를 다시 말하는 것이고, 그것은 **이미 M1 축0 에 있다**).
"""
from __future__ import annotations

from datetime import datetime, timezone

UTC = timezone.utc


def _match(day: str, *, home, away, goals, box=None) -> dict:
    """🔴 한 경기 — `home_box`/`away_box` 가 **구간**(없으면 거친 판)이다."""
    got = {"utc": f"{day}T12:00:00Z", "league": "league:T1",
           "home": "H", "away": "A", "home_ids": list(home),
           "away_ids": list(away), "goals": list(goals)}
    if box:
        got["home_box"] = dict(box[0])
        got["away_box"] = dict(box[1])
    return got


# ══════════════════════════════════════════════════════════════════
# 구간
# ══════════════════════════════════════════════════════════════════

def test_segments_come_from_the_intervals_and_goal_minutes() -> None:
    """🔴 구간은 **출전 구간 + 골 분**으로 쪼갠다(45분에 몰아 넣지 않는다)."""
    from app.core.ratings import player_pm as pm
    one = _match("2026-08-10", home=["h1", "h2"], away=["a1"],
                 goals=[{"min": 30, "home": True}],
                 box=({"h1": [0, 60], "h2": [60, 90]}, {"a1": [0, 90]}))
    got = pm.segments(one)
    assert [s["minutes"] for s in got] == [30, 30, 30], got
    assert [s["gf"] for s in got] == [1, 0, 0], got
    # 🔴 60분에 들어온 선수는 **앞 구간에 없다**
    assert got[0]["home_on"] == ["h1"] and got[2]["home_on"] == ["h2"], got


def test_coarse_plate_is_named() -> None:
    """⚠️ 구간이 없으면 **거친 판**(선발 90분)이고 판이 그렇게 **적는다**."""
    from app.core.ratings import player_pm as pm
    one = _match("2026-08-10", home=["h1"], away=["a1"], goals=[])
    got = pm.fit([one], as_of=datetime(2026, 9, 1, tzinfo=UTC), lam=10.0)
    assert "거친 판" in got.why, got.why


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 팀 고정효과 — **팀의 힘이 선수 점수로 새지 않는다**
# ══════════════════════════════════════════════════════════════════

def test_team_strength_does_not_leak_into_player_scores() -> None:
    """🔴 늘 1골 차로 이기는 팀의 선수들은 ± 가 **팀 항으로** 간다.

    두 팀이 **서로만** 만나고 홈이 늘 1-0 으로 이기면, 선수 점수는 그 차를
    설명할 수 없다(같은 11명이 늘 같은 쪽에 있다) → **팀 항**이 받아야 한다.
    """
    from app.core.ratings import player_pm as pm
    h = [f"h{i}" for i in range(11)]
    a = [f"a{i}" for i in range(11)]
    rows = [_match(f"2026-0{m}-1{d}", home=h, away=a,
                   goals=[{"min": 40, "home": True}])
            for m in (3, 4, 5) for d in range(1, 7)]
    got = pm.fit(rows, as_of=datetime(2026, 9, 1, tzinfo=UTC), lam=5.0,
                 teams=True)
    said = [abs(v) for k, v in got.raw.items() if not k.startswith("team:")]
    team = {k: v for k, v in got.raw.items() if k.startswith("team:")}
    assert team, got.why                        # 🔴 팀 항이 **있다**
    assert max(said) < max(abs(v) for v in team.values()), (said, team)
    # 🔴 팀 항은 `value_of` 가 **선수로 내주지 않는다**
    assert all(not k.startswith("team:") for k in got.value), list(got.value)


# ══════════════════════════════════════════════════════════════════
# 벌(λ) — **시즌 교차로 고른다**(손값 금지)
# ══════════════════════════════════════════════════════════════════

def test_lam_is_chosen_by_season_cross() -> None:
    """🔴 `pick_lam` — 한 시즌으로 적합해 **다른 시즌**의 구간 골 차를 맞춘다."""
    from app.core.ratings import player_pm as pm
    h = [f"h{i}" for i in range(11)]
    a = [f"a{i}" for i in range(11)]
    rows = [_match(f"202{y}-0{m}-1{d}", home=h, away=a,
                   goals=[{"min": 40, "home": True}])
            for y, m in ((5, 3), (5, 4), (6, 3), (6, 4)) for d in range(1, 6)]
    lam, why = pm.pick_lam(rows, as_of=datetime(2026, 9, 1, tzinfo=UTC),
                           lams=(1.0, 10.0, 100.0))
    assert lam in (1.0, 10.0, 100.0), (lam, why)
    assert "시즌" in why and "오차" in why, why


def test_fit_refuses_a_hand_value() -> None:
    """🔴 `lam=0` 은 **적합하지 않는다**(벌 없는 풀이는 공선형에서 발산한다)."""
    from app.core.ratings import player_pm as pm
    got = pm.fit([_match("2026-08-10", home=["h"], away=["a"], goals=[])],
                 as_of=datetime(2026, 9, 1, tzinfo=UTC), lam=0.0)
    assert not got.value and "🔴" in got.why


# ══════════════════════════════════════════════════════════════════
# 수축 — **리그·포지션 평균** 쪽
# ══════════════════════════════════════════════════════════════════

def test_short_minutes_shrink_toward_the_position_mean() -> None:
    """🔴 300분 미만은 **그 포지션 평균** 쪽으로 간다(없으면 리그 평균 · 사유)."""
    from app.core.ratings import player_pm as pm
    got = pm.shrink({"p1": 1.0, "p2": -1.0, "p3": 3.0},
                    minutes={"p1": 900.0, "p2": 900.0, "p3": 10.0},
                    pos={"p1": "GK", "p2": "FW", "p3": "GK"})
    # 🔴 p3 는 GK 평균(= p1 의 1.0) 쪽으로 끌린다 — 전체 평균(1.0) 이 아니라
    assert got[0]["p3"] < 1.5, got
    assert "GK" in got[1] or "포지션" in got[1], got[1]
    # ⚠️ 포지션이 없으면 **리그 평균**이고 그 사실을 적는다
    _v, why = pm.shrink({"p1": 1.0, "p2": 3.0},
                        minutes={"p1": 900.0, "p2": 10.0}, pos={})
    assert "리그 평균" in why, why


# ══════════════════════════════════════════════════════════════════
# 안정성 · 판
# ══════════════════════════════════════════════════════════════════

def test_stability_says_when_it_is_weak() -> None:
    """🔴 반분 두 추정의 상관이 0.3 미만이면 **"신뢰 낮음"**."""
    from app.core.ratings import player_pm as pm
    good = pm.stability({"a": 1.0, "b": 2.0, "c": 3.0},
                        {"a": 1.1, "b": 1.9, "c": 3.2})
    bad = pm.stability({"a": 1.0, "b": 2.0, "c": 3.0},
                       {"a": 3.0, "b": 1.0, "c": 2.0})
    assert good[0] > 0.3 and "신뢰 낮음" not in good[1], good
    assert "신뢰 낮음" in bad[1], bad


def test_plate_is_parquet_and_strictly_before(tmp_path) -> None:
    """🔴🔴 판은 `data/player_pm/<league>/<as_of>.parquet` · **엄격히 이전**(L3)."""
    from app.core import versions
    from app.core.ratings import player_pm as pm
    box = tmp_path / "player_pm" / "league_T1"
    box.mkdir(parents=True)
    pm.save(box / "2026-08-01.parquet",
            value={"p1": 0.5}, minutes={"p1": 900.0}, pos={"p1": "FW"})
    pm.save(box / "2026-09-20.parquet",
            value={"p1": 9.9}, minutes={"p1": 900.0}, pos={"p1": "FW"})
    got, why = pm.load(box, as_of=datetime(2026, 9, 20, tzinfo=UTC))
    assert got.value == {"p1": 0.5}, (got.value, why)   # 🔴 같은 날 판은 안 쓴다
    said, why2 = versions.pick_file(box, as_of=datetime(2026, 8, 1, tzinfo=UTC),
                                    ext="parquet")
    assert said is None and "이전 판이 없다" in why2, why2
