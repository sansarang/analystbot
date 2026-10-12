"""🔴🔴 **계수 판 관리(walk-forward)** — 사용자 지시 2026-10-12(3번 · 계약 L3).

> 3. 계수 판 관리: `state_rates`·`goal_baselines`·ρ·`league_elo`·(나중의)
> `matchup_model` 을 **as-of 날짜별 판**으로 저장(`data/<표>/<as_of>.yaml`).
> 로더는 **as_of 이전 최신 판**만 고른다. 운영은 오늘 판, 재현·백필은 그 경기
> 날짜 **이전** 판.
> 계약 L3: 재현이 as_of **이후** 날짜의 판을 고르면 실패.
"""
from __future__ import annotations

from datetime import UTC, datetime


def _mk(tmp_path, *days: str):
    """🔴 판 파일 몇 개를 만든다(내용은 날짜만 들고 있으면 된다)."""
    for day in days:
        (tmp_path / f"{day}.yaml").write_text(
            f"source: 시험\nday: '{day}'\n", encoding="utf-8")
    return tmp_path


def test_picks_the_newest_version_before_as_of(tmp_path) -> None:
    from app.core import versions as vz
    box = _mk(tmp_path, "2026-09-01", "2026-10-05", "2026-10-12")
    got, said = vz.pick(box, as_of=datetime(2026, 10, 11, 6, 26, tzinfo=UTC))
    assert str(got.get("day")) == "2026-10-05", (got, said)
    assert "2026-10-05" in said


def test_l3_never_picks_a_future_version(tmp_path) -> None:
    """🔴 L3 — as_of **이후** 판을 고르면 실패다."""
    from app.core import versions as vz
    box = _mk(tmp_path, "2026-10-12", "2026-11-01")
    got, said = vz.pick(box, as_of=datetime(2026, 10, 11, tzinfo=UTC))
    assert got == {}, got
    assert "이전 판이 없다" in said


def test_same_day_version_is_not_used_for_that_day(tmp_path) -> None:
    """⚠️ **같은 날 판은 쓰지 않는다** — 그 판이 그날 경기를 먹었을 수 있다.

    🔴 그래서 `as_of` **이전**(엄격히 작은 날짜)만 고른다.
    """
    from app.core import versions as vz
    box = _mk(tmp_path, "2026-10-11")
    got, _said = vz.pick(box, as_of=datetime(2026, 10, 11, 23, tzinfo=UTC))
    assert got == {}, got


def test_as_of_is_required(tmp_path) -> None:
    import pytest

    from app.core import versions as vz
    with pytest.raises(ValueError):
        vz.pick(_mk(tmp_path, "2026-10-01"), as_of=None)


def test_naive_as_of_is_refused(tmp_path) -> None:
    import pytest

    from app.core import versions as vz
    with pytest.raises(ValueError):
        vz.pick(_mk(tmp_path, "2026-10-01"), as_of=datetime(2026, 10, 11))


def test_state_rates_loader_goes_through_versions() -> None:
    """🔴 `staterates.load` 가 판 로더를 지난다(as_of 필수)."""
    import inspect

    from app.core import staterates as sr
    sig = inspect.signature(sr.load)
    got = sig.parameters.get("as_of")
    assert got is not None and got.default is inspect.Parameter.empty
    assert "versions" in inspect.getsource(sr.load)


def test_store_layout_is_one_dir_per_table() -> None:
    """🔴 자리 — `data/<표>/<as_of>.yaml`."""
    from app.core import versions as vz
    assert vz.ROOT.name == "data"
    assert vz.path_of("state_rates", "league:PD").name == "league_PD"
