"""🔴🔴 **§2 바닥 점수** — 지시서 2026-10-12(엔진 교체) §2.

> `app/core/ratings/` 신설 — `elo.py` · `elog.py` · `pi.py`. 공통 인터페이스:
>   `rate(matches_before_as_of, params)` → `RatingTable{team_id: {home, away,
>   overall}, as_of, n_matches}`
>   `prob_input(home_id, away_id, table)` → `diff`(숫자 하나)
> 표에 없는 팀(승격·신생) → **리그 하위 25% 점수로 시작** + 🔴 "신규 팀 초기값".
> 계약 **R1**: `RatingTable` 계산에 `as_of` 이후 경기가 하나라도 들어가면 실패.
> 계약 **R2**: **손값 학습률이면 실패**(판 파일 필수).
"""
from __future__ import annotations

from datetime import UTC, datetime

AS_OF = datetime(2026, 10, 11, 5, 0, tzinfo=UTC)


def _games() -> list[dict]:
    """🔴 `(시각, 홈, 원정, 홈골, 원정골)` 을 담은 **경기 목록**(어댑터 꼴 하나)."""
    out = []
    for i in range(10):
        out.append({"utc": f"2026-0{1 + i // 5}-0{1 + i % 5}T05:00:00Z",
                    "home": "A", "away": "B", "hg": 2, "ag": 0})
        out.append({"utc": f"2026-0{1 + i // 5}-0{1 + i % 5}T08:00:00Z",
                    "home": "C", "away": "A", "hg": 0, "ag": 1})
    # 🔴 **킥오프 뒤** 경기 — R1 이 이것을 막는다
    out.append({"utc": "2026-10-12T05:00:00Z", "home": "B", "away": "A",
                "hg": 9, "ag": 0})
    return out


def _mods():
    from app.core.ratings import elo, elog, pi
    return (("elo", elo), ("elog", elog), ("pi", pi))


def test_every_rating_has_the_same_interface() -> None:
    """🔴 셋이 **같은 입구**를 준다(부르는 쪽에 분기가 없다)."""
    for name, mod in _mods():
        assert hasattr(mod, "rate"), name
        assert hasattr(mod, "prob_input"), name
        assert hasattr(mod, "PARAMS"), name          # 🔴 격자 탐색이 읽는 이름표


def test_rate_returns_a_rating_table() -> None:
    from app.core.ratings import load_params
    for name, mod in _mods():
        got = mod.rate(_games(), params=load_params(name, league="league:TEST"),
                       as_of=AS_OF)
        assert got.as_of == AS_OF, name
        assert got.n_matches == 20, (name, got.n_matches)   # 🔴 뒤 경기는 뺀다
        for team in ("A", "B", "C"):
            box = got.teams[team]
            assert {"home", "away", "overall"} <= set(box), (name, box)


def test_r1_future_games_never_enter() -> None:
    """🔴🔴 **R1** — `as_of` 이후 경기가 하나라도 들어가면 **실패**다."""
    from app.core.ratings import load_params
    for name, mod in _mods():
        p = load_params(name, league="league:TEST")
        with_future = mod.rate(_games(), params=p, as_of=AS_OF)
        # 🔴 9-0 이 들어갔다면 B 가 A 보다 높아진다 — 들어가지 않았음을 수로 센다
        a = mod.prob_input("A", "B", with_future)
        assert a > 0, (name, a)
        assert with_future.n_matches == 20, name


def test_r1_refuses_naive_as_of() -> None:
    import pytest

    from app.core.ratings import load_params
    for name, mod in _mods():
        with pytest.raises(ValueError):
            mod.rate(_games(), params=load_params(name, league="league:TEST"),
                     as_of=datetime(2026, 10, 11, 5, 0))


def test_r2_params_must_come_from_a_version_file() -> None:
    """🔴🔴 **R2** — 손값 학습률은 **거부**다(판 파일이 있어야 한다)."""
    import pytest

    from app.core import ratings
    with pytest.raises(ValueError):
        ratings.load_params("pi", league="league:없는리그", strict=True)
    # ⚠️ 느슨한 호출은 **임시값**을 주되 그 사실을 적는다
    got = ratings.load_params("pi", league="league:없는리그")
    assert got.provisional is True and "🔴" in got.why


def test_new_team_starts_at_the_bottom_quarter() -> None:
    """🔴 표에 없는 팀 → **리그 하위 25% 점수** + 🔴 신규 팀 초기값."""
    from app.core.ratings import load_params
    from app.core.ratings import pi
    got = pi.rate(_games(), params=load_params("pi", league="league:TEST"),
                  as_of=AS_OF)
    said, why = got.of("처음보는팀")
    assert "신규" in why
    known = sorted(float(got.teams[t]["overall"]) for t in got.teams)
    assert said <= known[max(0, len(known) // 4)], (said, known)


def test_prob_input_is_one_number_and_antisymmetric() -> None:
    from app.core.ratings import load_params
    for name, mod in _mods():
        got = mod.rate(_games(), params=load_params(name, league="league:TEST"),
                       as_of=AS_OF)
        a = mod.prob_input("A", "B", got)
        b = mod.prob_input("B", "A", got)
        assert isinstance(a, float), name
        # 🔴 pi 는 홈·원정 점수를 따로 들어 **대칭이 아니다** — 부호만 센다
        assert a > 0 > b, (name, a, b)


def test_elog_uses_the_goal_margin() -> None:
    """🔴 ELOg — `k = k0·(1+δ)^λ`(δ=절대 골 차)다. 골 차가 커지면 더 움직인다."""
    from app.core.ratings import elo, elog, load_params
    small = [{"utc": "2026-05-01T05:00:00Z", "home": "A", "away": "B",
              "hg": 1, "ag": 0}]
    big = [{"utc": "2026-05-01T05:00:00Z", "home": "A", "away": "B",
            "hg": 5, "ag": 0}]
    p = load_params("elog", league="league:TEST")
    s = elog.rate(small, params=p, as_of=AS_OF).teams["A"]["overall"]
    b = elog.rate(big, params=p, as_of=AS_OF).teams["A"]["overall"]
    assert b > s, (s, b)
    # ⚠️ Elo 는 골 차를 **안 본다** — 두 수가 같아야 한다
    q = load_params("elo", league="league:TEST")
    assert (elo.rate(small, params=q, as_of=AS_OF).teams["A"]["overall"]
            == elo.rate(big, params=q, as_of=AS_OF).teams["A"]["overall"])


def test_pi_keeps_home_and_away_apart() -> None:
    """🔴 pi-ratings — **홈·원정 점수를 따로** 든다(한 수로 합치지 않는다)."""
    from app.core.ratings import load_params, pi
    got = pi.rate(_games(), params=load_params("pi", league="league:TEST"),
                  as_of=AS_OF)
    box = got.teams["A"]
    assert box["home"] != box["away"], box
