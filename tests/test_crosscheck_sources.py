"""[§8-22] 소스 교차검증 — 여러 곳에서 모은 값이 서로 맞는지 대조한다.

사용자 지시(2026-08-26): "그 내용이 맞는지 검증해서 보태면 된다."

실사고가 바로 나왔다 — 같은 경기(NC @ LG)에서:
    딥서치·네이버 → NC 선발 "구창모"
    X 구단 공식   → NC 선발 "박준현"
"""

import pytest

from app.research.crosscheck_sources import (
    SOURCE_RANK,
    apply,
    compare_field,
    crosscheck_starters,
    missing_fields,
    norm_name,
)


def test_name_normalisation_ignores_spacing():
    """'山野 太一' · '山野太一'는 같은 사람이다 — 공백 차이로 불일치를 만들면 안 된다."""
    assert norm_name("山野 太一") == norm_name("山野太一")
    assert norm_name("구창모") == norm_name(" 구창모 ")
    assert norm_name(None) == ""


def test_freshest_source_wins_not_majority():
    """[§8-22] ⚠️ **다수결이 아니다.** 오래된 소스 둘이 새 소스 하나를 이기면 안 된다.

    실사고: 딥서치·네이버가 '구창모'(2표), X 구단 공식이 '박준현'(1표).
    다수결이면 틀린 값을 고른다 — 구단 공식이 라인업을 가장 먼저 올린다.
    """
    r = compare_field({"deep_search": "구창모", "portal": "구창모",
                       "official_x": "박준현"})
    assert r["value"] == "박준현"
    assert r["source"] == "official_x"
    assert len(r["conflict"]) == 2


def test_agreement_has_no_conflict():
    r = compare_field({"portal": "임찬규", "deep_search": "임찬규"})
    assert r["value"] == "임찬규" and r["conflict"] == []
    assert set(r["agree"]) == {"portal", "deep_search"}


def test_missing_values_are_ignored():
    r = compare_field({"portal": None, "deep_search": "구창모", "community": ""})
    assert r["value"] == "구창모" and r["conflict"] == []


def test_all_empty_returns_none():
    r = compare_field({"portal": None, "deep_search": ""})
    assert r["value"] is None and r["source"] is None


def test_source_ranking_puts_official_x_first():
    """구단 공식 X가 가장 빠르다 — 실측으로 확인했다(확정 라인업이 X에만 있었다)."""
    assert SOURCE_RANK["official_x"] > SOURCE_RANK["portal"] > SOURCE_RANK["news"]
    assert SOURCE_RANK["community"] == min(SOURCE_RANK.values())


# ---------------------------------------------------------------- 적용

def test_conflict_revokes_final_pick_status():
    """[§8-22] 소스가 갈리면 **최종 픽 자격을 박탈**한다.

    문서화된 과거 사고: "선발이 누구인지 모르는 채로 최종 픽을 냈다."
    """
    from app.collectors.lineups import STATUS_CONFLICT, pick_state

    research, jg = {}, {"lineup_status": "confirmed"}
    apply(research, jg, {"deep_search": {"home": "임찬규", "away": "구창모"},
                         "official_x": {"home": "임찬규", "away": "박준현"}})
    assert jg["lineup_status"] == STATUS_CONFLICT
    assert pick_state(jg["lineup_status"])[0] == "preliminary"
    assert "source_conflict" in research
    assert "박준현" in research["source_conflict"]


def test_conflict_clears_stats_of_the_wrong_pitcher():
    """⚠️ 이름이 바뀌면 이전 소스의 ERA는 **그 투수 것이 아니다.**

    안 지우면 박준현 이름에 구창모 ERA가 붙어 λ가 통째로 틀린다.
    """
    research = {"away_pitcher": {"name": "구창모", "era_season": 3.89, "whip": 1.27}}
    apply(research, {}, {"portal": {"away": "구창모"},
                         "official_x": {"away": "박준현"}})
    assert research["away_pitcher"]["name"] == "박준현"
    assert "era_season" not in research["away_pitcher"]
    assert "whip" not in research["away_pitcher"]


def test_agreement_keeps_stats_and_status():
    """일치하면 아무것도 건드리지 않는다 — 정상 경기를 망치면 안 된다."""
    research = {"home_pitcher": {"name": "임찬규", "era_season": 4.14}}
    jg = {"lineup_status": "confirmed"}
    out = apply(research, jg, {"portal": {"home": "임찬규"},
                               "deep_search": {"home": "임찬규"}})
    assert jg["lineup_status"] == "confirmed"
    assert research["home_pitcher"]["era_season"] == 4.14
    assert out["conflict"] is False


def test_crosscheck_reports_both_sides():
    out = crosscheck_starters({"portal": {"home": "A", "away": "B"},
                               "official_x": {"home": "A", "away": "C"}})
    assert out["home"]["conflict"] == []
    assert out["away"]["value"] == "C"
    assert out["conflict"] is True


# ---------------------------------------------------------------- 빈칸 전용

def test_missing_fields_finds_gaps_only():
    """[§8-22] 딥서치를 **빈칸에만** 쓴다 — 크롤링이 채운 것을 다시 묻지 않는다."""
    research = {"home_pitcher": {"name": "임찬규", "era_season": 4.14},
                "away_pitcher": {"name": "구창모"},
                "absences": []}
    gaps = missing_fields(research, (
        "home_pitcher.era_season", "away_pitcher.era_season",
        "absences", "motivation"))
    assert "home_pitcher.era_season" not in gaps      # 이미 있다
    assert "away_pitcher.era_season" in gaps
    assert "absences" in gaps                        # 빈 배열도 빈칸이다
    assert "motivation" in gaps


def test_missing_fields_handles_broken_shapes():
    """리서치가 이상한 모양이어도 크래시하지 않는다."""
    assert missing_fields({}, ("a.b.c",)) == ["a.b.c"]
    assert missing_fields({"a": "문자열"}, ("a.b",)) == ["a.b"]
