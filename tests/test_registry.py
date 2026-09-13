"""[설계 규율 · 2026-09-02] 레지스트리 계약 — **사본이 다시 생기지 않게 잠근다.**

오탐 4건이 전부 "시스템에 이미 있는 사실을 코드 옆에 손으로 옮겨 적었고,
사본이 원본과 어긋남"이었다. 이 파일은 그 재발을 막는 잠금장치다.

규율 2번("신규 모듈은 태어나는 날 계약 테스트와 함께 태어난다")의 첫 적용이다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.registry import (
    JOB_GRACE, ODDS_PROVIDERS, WATCHED_JOBS, active_providers, provider,
    sports_of, watched_sports,
)


# ─────────────────── 레지스트리 자체 ───────────────────

def test_every_provider_declares_its_leagues():
    """담당 리그가 없는 소스는 감시 범위를 정할 수 없다."""
    for p in ODDS_PROVIDERS:
        assert p.sports, f"{p.name} 담당 리그 미선언"
        # 🔓 [ODP-1 2026-09-13] 축구가 종목에 들어왔다 — oddsportal 이 1X2 를
        #    낸다. 목록을 손으로 적지 않는다: 우리가 다루는 종목 전부다.
        assert all(sp in ("mlb", "kbo", "npb", "soccer") for sp in p.sports), p.name


def test_provider_names_are_unique():
    names = [p.name for p in ODDS_PROVIDERS]
    assert len(names) == len(set(names))


def test_unwired_and_keyless_sources_are_inactive():
    """🔴 끄거나 미구현인 것을 고장이라 울리는 게 오탐의 최대 원인이다."""
    names = {p.name for p in active_providers()}
    assert "betman" not in names, "수집기 미배선(wired=False)"
    assert "sharp" not in names, "키 없음(key_setting 비어 있음)"
    assert "theodds" not in names, "유료 경로 기본 비활성"


def test_paid_mode_swaps_the_whole_set(monkeypatch):
    """유료 모드로 되돌리면 무료 소스가 아니라 theodds 를 본다."""
    from app.config import Settings

    monkeypatch.setattr("app.config.get_settings",
                        lambda: Settings(_env_file=None, odds_provider="theodds"))
    assert [p.name for p in active_providers()] == ["theodds"]


def test_key_presence_activates_the_fallback(monkeypatch):
    """키를 넣으면 폴백이 자동으로 켜진다 — 코드를 고칠 필요가 없다."""
    from app.config import Settings

    monkeypatch.setattr("app.config.get_settings",
                        lambda: Settings(_env_file=None, sharpapi_key="k"))
    assert "sharp" in {p.name for p in active_providers()}


def test_league_coverage_is_disjoint_where_it_matters():
    """ESPN 은 MLB 전용이다 — 이 사실이 오탐 ①의 해소 근거다."""
    assert sports_of("espn") == ("mlb",)
    # 🔓 [ODP-1] oddsportal 이 축구 1X2 도 담당한다. 종전에는 축구 배당이
    #    **0건**이었다(최근 14일 69경기) — 리그 표에 축구가 없어서였다.
    assert set(sports_of("oddsportal")) == {"kbo", "npb", "soccer"}
    # ⚠️ 축구를 담당하는 소스는 아직 이것 하나다 — 늘면 이 줄이 먼저 깨진다
    assert [p.name for p in ODDS_PROVIDERS if "soccer" in p.sports] == ["oddsportal"]
    # 🔴 사본 금지 — 감시 종목은 **활성 소스에서 파생**된다. 손으로 적은
    #    목록과 비교하면 소스가 늘 때마다 이 줄이 거짓 경보를 낸다.
    expected = []
    for p in ODDS_PROVIDERS:
        if p.wired and not p.key_setting:
            for sp in p.sports:
                if sp not in expected:
                    expected.append(sp)
    assert set(watched_sports()) == set(expected)
    assert "soccer" in watched_sports(), "축구 배당이 감시 범위 밖이다"


# ─────────────────── 사본 금지 (핵심) ───────────────────

def test_watchdog_keeps_no_copy_of_provider_or_job_facts():
    """🔴 **사본 금지.** 워치독은 담당 리그·활성 여부·잡 목록을 자기 안에
    적지 않는다. 적는 순간 레지스트리와 어긋나 오탐이 된다.
    """
    src = Path("app/watchdog.py").read_text(encoding="utf-8")
    for banned in ("ACTIVE_PROVIDERS = (", "WATCHED_JOBS = {"):
        assert banned not in src, f"워치독에 사본이 다시 생겼다: {banned}"
    assert "from app.registry import" in src


def test_no_module_writes_the_job_period_by_hand():
    """🔴 **주기는 어디에도 적지 않는다.** 트리거 객체가 원본이다.

    실사고: `mlb_pregame_5m` 은 `CronTrigger(hour="5-11")` 인데 워치독이
    "주기 5분"으로 적어 창 밖인 12:40 에 울렸다.
    """
    src = Path("app/watchdog.py").read_text(encoding="utf-8")
    assert "_next_expected" in src and "_JOB_TRIGGERS" in src
    reg = Path("app/registry.py").read_text(encoding="utf-8")
    assert "grace_min" in reg
    assert "period" not in reg.replace("주기는 여기 적지 않는다", ""), \
        "레지스트리에 주기를 적으면 그것도 사본이다"


def test_odds_free_reads_the_chain_from_the_registry():
    """수집기도 사본을 두지 않는다 — 워치독과 같은 원본을 본다."""
    src = Path("app/collectors/odds_free.py").read_text(encoding="utf-8")
    assert "MLB_CHAIN" not in src and "ASIA_PROVIDER = " not in src
    assert "active_providers" in src


def test_watched_jobs_match_the_scheduler(monkeypatch):
    """🔴 레지스트리에 적힌 잡이 **실재해야 한다.** 없는 잡을 감시하면
    영원히 '한 번도 안 돔'이고, 있는데 빠지면 고장을 놓친다."""
    from app.scheduler import build_scheduler

    # 🔴 `_job_specs()` 를 읽으면 안 된다 — `heartbeat_2m` 처럼 따로 등록되는
    #    잡이 빠진다(이 테스트가 그걸 잡았다). **빌드된 스케줄러가 원본이다.**
    registered = {j.id for j in build_scheduler().get_jobs()}
    for j in WATCHED_JOBS:
        assert j.job_id in registered, f"{j.job_id} 가 스케줄러에 없다"
    assert set(JOB_GRACE) == {j.job_id for j in WATCHED_JOBS}


def test_grace_is_generous_enough_to_avoid_flapping():
    """유예가 주기보다 짧으면 정상 동작이 경보가 된다."""
    for j in WATCHED_JOBS:
        assert j.grace_min >= 4, f"{j.job_id} 유예 {j.grace_min}분은 너무 짧다"


# ─────────────────── 규율 문서화 ───────────────────

def test_discipline_is_written_where_every_session_reads_it():
    """규율이 코드에만 있으면 다음 세션이 같은 실수를 반복한다."""
    md = Path("CLAUDE.md").read_text(encoding="utf-8")
    assert "사본 금지" in md
    assert "신규 모듈은 태어나는 날 계약 테스트와 함께 태어난다" in md
    assert "자기검증 3문" in md


@pytest.mark.parametrize("code,fact", [
    ("W-JOB-LATE", "CronTrigger"),
    ("W-ODDS-STALE", "담당"),
])
def test_alert_details_name_the_real_cause(code, fact):
    """경보 문구가 '무엇 때문에 울렸는지'를 말해야 사람이 판단할 수 있다."""
    src = Path("app/watchdog.py").read_text(encoding="utf-8")
    assert code in src and fact in src
