"""[v1.1 1단계 묶음] 교차검증으로 선발이 바뀌어도 성적을 잃지 않는다.

🔴 종전: 소스가 갈려 선발 이름이 바뀌면 era_season·whip·ip_avg_recent·
   era_vs_opponent 를 **비우기만 하고 끝냈다.** 비우는 것은 옳다 — 이전
   소스의 성적은 그 투수 것이 아니다. 그러나 새 투수 것으로 다시 채우지
   않아, 소스가 갈린 경기는 판정이 선발 WHIP·ERA를 통째로 잃었다.
"""

import pytest

from app.research.crosscheck_sources import STARTER_STAT_FIELDS, apply

PITCHERS = {
    "박준현": {"era_season": 3.21, "whip": 1.15, "ip_avg_recent": 5.7},
    "구창모": {"era_season": 2.40, "whip": 0.98},
}


def _research(name, **stats):
    return {"home_pitcher": {"name": name, **stats},
            "away_pitcher": {"name": "상대투수"}}


def _sources(home_a, home_b):
    return {"portal": {"home": home_a, "away": "상대투수"},
            "official_x": {"home": home_b, "away": "상대투수"}}


def test_stats_are_refilled_for_the_adopted_starter():
    """이름이 바뀌면 새 투수의 공식 기록으로 다시 채운다."""
    r = _research("구창모", era_season=2.40, whip=0.98)
    jg = {}
    out = apply(r, jg, _sources("구창모", "박준현"), pitcher_stats=PITCHERS)
    blk = r["home_pitcher"]
    assert blk["name"] == "박준현", "최신 소스의 선발이 채택돼야 한다"
    assert blk["whip"] == 1.15 and blk["era_season"] == 3.21, \
        "새 투수 성적으로 다시 채워지지 않았다 — 판정이 WHIP을 잃는다"
    assert "재확보" in blk["stats_status"]
    assert "재확보" in out["starters"]["home"]["stats"]


def test_old_pitchers_stats_never_survive():
    """반대 방향 — 이전 투수의 성적이 남아 있으면 안 된다."""
    r = _research("구창모", era_season=2.40, whip=0.98, era_vs_opponent=1.11)
    apply(r, {}, _sources("구창모", "박준현"), pitcher_stats={})
    blk = r["home_pitcher"]
    for k in STARTER_STAT_FIELDS:
        assert blk.get(k) is None, f"{k}에 이전 투수 값이 남았다"


def test_unavailable_stats_are_recorded_not_silent():
    """채울 수 없으면 **그 사실을 남긴다.** 조용히 비어 있으면 원인을 못 찾는다."""
    r = _research("구창모", whip=0.98)
    out = apply(r, {}, _sources("구창모", "박준현"), pitcher_stats={})
    assert "미확보" in r["home_pitcher"]["stats_status"]
    assert "미확보" in out["starters"]["home"]["stats"]


def test_no_name_change_leaves_stats_untouched():
    """소스가 일치하면 아무것도 건드리지 않는다."""
    r = _research("박준현", era_season=9.99, whip=2.22)
    apply(r, {}, _sources("박준현", "박준현"), pitcher_stats=PITCHERS)
    blk = r["home_pitcher"]
    assert blk["era_season"] == 9.99 and blk["whip"] == 2.22
    assert "stats_status" not in blk


def test_conflict_still_revokes_final_pick():
    """성적을 되찾아도 **최종 픽 자격 박탈은 그대로다.**

    소스가 갈렸다는 사실이 사라지는 것이 아니다 — 값을 채운 것과
    그 값을 믿어도 되는가는 다른 문제다.
    """
    from app.collectors.lineups import STATUS_CONFLICT

    jg = {}
    apply(_research("구창모"), jg, _sources("구창모", "박준현"),
          pitcher_stats=PITCHERS)
    assert jg["lineup_status"] == STATUS_CONFLICT
