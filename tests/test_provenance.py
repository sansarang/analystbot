"""[§9 게이트 ③] 출처 대조 — 값·소스·시각·라벨.

게이트 ①②(물리·자기일관성)를 통과한 값이 여기로 온다. 여기서 묻는 것은
"가능한 값인가"가 아니라 **"믿을 수 있는 값인가"**다.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.engine.provenance import (
    CONFIRMED,
    CONFLICT,
    CROSS,
    FRESHNESS_MARGIN,
    SINGLE,
    UNVERIFIED,
    Observation,
    blocked_fields,
    distribution,
    label_field,
    resolve,
    stamp,
    strip_unusable,
)

T0 = datetime(2026, 8, 26, 9, 0, tzinfo=UTC)


def obs(value, source, minutes=0):
    return Observation(value, source, T0 + timedelta(minutes=minutes))


# ---------------------------------------------------------------- 라벨 판정

def test_two_independent_sources_agreeing_is_cross():
    r = resolve([obs("황동하", "portal"), obs("황동하", "news", 5)])
    assert r.label == CROSS and r.value == "황동하" and r.usable
    assert r.sources == ["news", "portal"]


def test_single_source_is_single_and_shows_its_origin():
    r = resolve([obs("황동하", "portal")])
    assert r.label == SINGLE and r.usable
    assert "단일" in r.note and "portal" in r.note, "근거의 두께가 카드에 보여야 한다"


def test_official_announcement_is_confirmed():
    r = resolve([obs("황동하", "official_x")])
    assert r.label == CONFIRMED and r.usable and r.note == ""


def test_portal_is_not_treated_as_official():
    """포털은 공식을 받아 싣지만 편집이 들어간다 — 예상을 확정처럼 실은 사고가 있었다."""
    assert resolve([obs("황동하", "portal")]).label == SINGLE


def test_same_name_written_differently_still_agrees():
    """'山野 太一' · '山野太一' 는 같은 값이다 — 표기 차이로 모순을 만들면 안 된다."""
    r = resolve([obs("山野 太一", "portal"), obs("山野太一", "news", 3)])
    assert r.label == CROSS


# ---------------------------------------------------------------- 모순 해소

def test_conflict_with_large_time_gap_takes_the_fresher_value():
    """🔴 다수결 금지 — 낡은 소스 **둘**이 신선한 소스 **하나**를 이기면 안 된다."""
    r = resolve([
        obs("황동하", "news", 0), obs("황동하", "deep_search", 5),   # 낡은 값 2개
        obs("김태형", "portal", 90),                                  # 신선한 값 1개
    ])
    assert r.value == "김태형", "다수결로 낡은 값이 이겼다"
    assert r.label == SINGLE and r.usable
    assert "더 신선한 값 채택" in r.detail and "황동하" in r.detail


def test_conflict_within_margin_is_dropped_as_unknown():
    """시각이 비슷한 충돌은 최신성 문제가 아니다 — 둘 중 하나가 틀렸다."""
    inside = int(FRESHNESS_MARGIN.total_seconds() // 60) - 1
    r = resolve([obs("황동하", "portal", 0), obs("김태형", "news", inside)])
    assert r.label == CONFLICT and r.value is None and not r.usable
    assert "신선도로 가릴 수 없다" in r.detail


def test_margin_boundary_is_exclusive_not_inclusive():
    m = int(FRESHNESS_MARGIN.total_seconds() // 60)
    assert resolve([obs("A", "portal", 0), obs("B", "news", m)]).label == CONFLICT
    assert resolve([obs("A", "portal", 0), obs("B", "news", m + 1)]).value == "B"


def test_fresh_official_conflict_keeps_confirmed_label():
    r = resolve([obs("황동하", "news", 0), obs("김태형", "official_x", 90)])
    assert r.value == "김태형" and r.label == CONFIRMED


# ---------------------------------------------------------------- 커뮤니티

def test_community_only_is_unverified_and_unusable():
    r = resolve([obs("에이스 결장", "community")])
    assert r.label == UNVERIFIED and not r.usable
    assert "판정 미사용" in r.note


def test_community_cannot_outrank_official_by_being_newer():
    """🔴 신선도는 **같은 급끼리** 비교하는 기준이다.

    목격담이 5분 새것이라는 이유로 공식 발표를 이기면 미확인 규율이 무너진다.
    """
    r = resolve([obs("황동하", "official_x", 0), obs("김태형", "community", 120)])
    assert r.value == "황동하" and r.label == CONFIRMED


def test_no_observation_is_unverified_not_a_value():
    r = resolve([])
    assert r.value is None and r.label == UNVERIFIED and not r.usable
    assert resolve([obs("", "portal"), obs(None, "news")]).value is None


# ---------------------------------------------------------------- 값 단위 라벨

def test_labels_are_per_value_not_per_source_or_game():
    """🔴 같은 응답이라도 선발은 확정, 부상은 단일일 수 있다.

    소스 하나에 라벨 하나를 붙이면 그 구분이 사라진다.
    """
    research = {"home_pitcher": {"name": "황동하"}, "absences": ["나성범"]}
    stamp(research, ["home_pitcher.name"], "official_x", T0)
    stamp(research, ["home_pitcher.name"], "portal", T0 + timedelta(minutes=2))
    stamp(research, ["absences"], "news", T0)

    assert label_field(research, "home_pitcher.name").label == CONFIRMED
    assert label_field(research, "absences").label == SINGLE
    assert distribution(research) == {CONFIRMED: 1, CROSS: 0, SINGLE: 1,
                                      UNVERIFIED: 0, CONFLICT: 0, "대조됨": 1}


def test_stamp_accumulates_instead_of_overwriting():
    """🔴 마지막 소스만 남기면 교차인지 모순인지 영원히 알 수 없다."""
    research = {"home_pitcher": {"name": "황동하"}}
    stamp(research, ["home_pitcher.name"], "portal", T0)
    stamp(research, ["home_pitcher.name"], "news", T0 + timedelta(minutes=1))
    assert label_field(research, "home_pitcher.name").label == CROSS


def test_stamp_ignores_removal_markers():
    """kbo_stats가 미공개 지표를 지울 때 남기는 '-필드' 표기는 관측이 아니다."""
    research = {"home_pitcher": {}}
    stamp(research, ["-home_pitcher.woba"], "official_record", T0)
    assert distribution(research)[SINGLE] == 0


# ---------------------------------------------------------------- 판정 입력 차단

def test_unusable_values_are_removed_from_judgement_input():
    """🔴 표시만 하고 남겨두면 다음 단계가 그것을 사실로 읽는다."""
    research = {"home_pitcher": {"name": "황동하", "era_season": 4.82},
                "absences": ["에이스 결장(목격담)"]}
    stamp(research, ["home_pitcher.era_season"], "portal", T0)
    stamp(research, ["absences"], "community", T0)
    # 선발 이름은 비슷한 시각에 충돌 → 모순
    stamp(research, ["home_pitcher.name"], "portal", T0)
    research["home_pitcher"]["name"] = "김태형"
    stamp(research, ["home_pitcher.name"], "news", T0 + timedelta(minutes=5))

    assert set(blocked_fields(research)) == {"absences", "home_pitcher.name"}
    removed = strip_unusable(research)
    assert set(removed) == {"absences", "home_pitcher.name"}
    assert "name" not in research["home_pitcher"], "모순 값이 판정 입력에 남았다"
    assert "absences" not in research, "미확인 값이 판정 입력에 남았다"
    assert research["home_pitcher"]["era_season"] == 4.82, "멀쩡한 값까지 지웠다"


def test_naive_datetime_is_rejected():
    """시각에 timezone이 없으면 모순 해소가 조용히 틀어진다."""
    with pytest.raises(ValueError):
        Observation("x", "portal", datetime(2026, 8, 26, 9, 0))


def test_crosschecked_counts_multi_source_values_separately():
    """🔴 `교차` 라벨만 보면 대조가 되는지 알 수 없다 — 공식이 끼면 `확정`이 이긴다.

    실측(2026-08-27): 교차 라벨 0건인데 실제로는 20개 값을 두 소스가 보고 있었다.
    라벨과 **직교하는** 지표가 있어야 교차검증의 작동 여부가 보인다.
    """
    research = {"home_offense": {"avg": 0.274}}
    stamp(research, ["home_offense.avg"], "official_record", T0)
    stamp(research, ["home_offense.avg"], "portal", T0 + timedelta(minutes=1))
    d = distribution(research)
    assert d[CONFIRMED] == 1, "공식이 끼면 확정이 우선이다"
    assert d[CROSS] == 0
    assert d["대조됨"] == 1, "두 소스가 본 사실이 안 보인다"


def test_crosschecked_ignores_same_source_twice():
    """같은 원본을 두 수집기가 긁은 것은 대조가 아니다 — 스스로를 확증한다."""
    research = {"home_pitcher": {"name": "황동하"}}
    stamp(research, ["home_pitcher.name"], "portal", T0)
    stamp(research, ["home_pitcher.name"], "portal", T0 + timedelta(minutes=1))
    assert distribution(research)["대조됨"] == 0
