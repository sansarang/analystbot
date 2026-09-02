"""[운영 안정화 4] 하이픈 실명이 타순 파서를 깨뜨리던 결함.

🔴 실측 2026-09-02: MLB 24개 라인업 중 **3개(12%)** 가 10명으로 파싱됐다.
   컵스는 1번 타자 `Pete Crow-Armstrong` 이 쪼개져 **9개 슬롯이 전부 한 칸씩
   밀렸다.** 어긋난 슬롯은 `usual_from`·`diff_lineup` 을 거쳐 **라인업 의도**와
   **T5 딥서치 트리거**로 흘러간다 — 없는 "타순 이동"이 신호가 됐다.
   판정 로직이 아니라 **파서 버그**다.
"""
from __future__ import annotations

import pytest

from app.engine.lineup_diff import (
    NAME_REGISTRY, parse_order, register_names, rejoin_hyphenated,
)

#: 실제 2026-09-01 슬레이트 라인업 (statsapi battingOrder 순서)
CUBS = ("Pete Crow-Armstrong-Seiya Suzuki-Alex Bregman-Tyrone Taylor-"
        "Nico Hoerner-Michael Busch-Carson Kelly-BJ Murray Jr.-Matt Shaw")
BRAVES = ("Drake Baldwin-Ronald Acuña Jr.-Matt Olson-Michael Harris II-"
          "Mauricio Dubón-Ozzie Albies-Austin Riley-Brewer Hicklen-Ha-Seong Kim")
TIGERS = ("Kevin McGonigle-Gleyber Torres-Dillon Dingler-Riley Greene-"
          "Hao-Yu Lee-Spencer Torkelson-Max Clark-Javier Báez-John Peck")

REAL_NAMES = {"Pete Crow-Armstrong", "Ha-Seong Kim", "Hao-Yu Lee",
              "Ronald Acuña Jr.", "Michael Harris II"}


@pytest.fixture(autouse=True)
def _clean_registry():
    before = set(NAME_REGISTRY)
    NAME_REGISTRY.clear()
    yield
    NAME_REGISTRY.clear()
    NAME_REGISTRY.update(before)


@pytest.mark.parametrize("team,order,first,last", [
    ("컵스", CUBS, "Pete Crow-Armstrong", "Matt Shaw"),
    ("브레이브스", BRAVES, "Drake Baldwin", "Ha-Seong Kim"),
    ("타이거스", TIGERS, "Kevin McGonigle", "John Peck"),
])
def test_real_lineups_parse_to_nine(team, order, first, last):
    """실라인업 3팀 — 사전을 등록하면 정확히 9명이다."""
    register_names(REAL_NAMES)
    got = parse_order(order)
    assert len(got) == 9, f"{team}: {[x[0] for x in got]}"
    assert got[0][0] == first
    assert got[-1][0] == last


def test_slot_shift_is_what_the_bug_caused():
    """컵스는 1번이 쪼개져 **모든 슬롯이 밀렸다** — 그게 가짜 '타순 이동'의 정체다."""
    broken = parse_order(CUBS)                       # 사전 없음 = 종전 동작
    register_names(REAL_NAMES)
    fixed = parse_order(CUBS)
    assert len(broken) == 10 and len(fixed) == 9
    # 종전에는 2번 자리에 'Armstrong'(사람이 아님)이 앉아 있었다
    assert broken[1][0] == "Armstrong"
    assert fixed[1][0] == "Seiya Suzuki"


def test_empty_registry_does_not_guess():
    """사전이 없으면 손대지 않는다 — 추측으로 이름을 만들지 않는다."""
    assert rejoin_hyphenated(["Ha", "Seong Kim"]) == ["Ha", "Seong Kim"]


def test_registry_keeps_only_hyphenated_names():
    """사전은 하이픈 이름만 담는다 — 1,440명을 통째로 들고 있을 이유가 없다."""
    register_names({"Aaron Judge", "Ha-Seong Kim", "Mike Trout"})
    assert NAME_REGISTRY == {"Ha-Seong Kim"}


def test_position_suffix_still_parses():
    """KBO·NPB는 포지션이 붙는다 — 재결합이 그걸 깨면 안 된다."""
    register_names(REAL_NAMES)
    got = parse_order("김도영(3루수)-최형우(지명타자)")
    assert got == [("김도영", "3루수"), ("최형우", "지명타자")]


def test_list_input_is_untouched():
    """목록으로 들어오면 이미 갈라져 있지 않다 — 재결합 대상이 아니다."""
    register_names(REAL_NAMES)
    assert parse_order(["Ha-Seong Kim(유격수)"]) == [("Ha-Seong Kim", "유격수")]


def test_roster_load_registers_names(monkeypatch):
    """명단을 받는 경로가 사전을 채운다 — 호출부가 따로 등록하지 않아도 된다."""
    import asyncio

    from app.collectors import starter_season as ss

    monkeypatch.setitem(ss._roster_mem, 2026,
                        {"Ha-Seong Kim": 1, "Aaron Judge": 2})
    asyncio.run(ss._roster(2026, None))
    assert "Ha-Seong Kim" in NAME_REGISTRY
