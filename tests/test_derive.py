"""[A-1단계] 딥서치 필드의 자체 산출.

실측(2026-08-27, KBO 캐시 5건)이 이관의 근거다:
  bullpen_overused 1/5 · form_reversal 0/5 · splits 2/5 · motivation 4/5
같은 정보를 이미 수집한 값(투수 소모·순위표)에서 유도할 수 있다.
"""

from app.engine import derive

JG = {"home": "Kia Tigers", "away": "Lotte Giants"}


def test_motivation_states_facts_not_conclusions():
    """🔴 '총력전'·'정리 모드'로 단정하지 않는다 — 그것은 2단 해석봇의 일이다.

    딥서치는 산문으로 결론까지 써 줬다. 결론을 사실 칸에 넣으면 3단이
    판단을 사실로 읽는다.
    """
    r = {"home_standing": {"rank": 4, "games_behind": 5.5, "remaining": 31},
         "away_standing": {"rank": 6, "games_behind": 15.5, "remaining": 33}}
    out = derive.motivation(r, JG)
    assert "4위" in out and "5.5G" in out and "잔여 31경기" in out
    for banned in ("총력전", "정리 모드", "노리는", "중요한 상황"):
        assert banned not in out, f"해석이 섞였다: {banned}"


def test_motivation_missing_standing_is_none():
    assert derive.motivation({}, JG) is None


def test_splits_from_standings():
    r = {"home_standing": {"w": 61, "l": 50, "d": 2},
         "away_standing": {"w": 50, "l": 59, "d": 2}}
    out = derive.splits(r)
    assert "61승 50패 2무" in out and "50승 59패 2무" in out


def test_form_reversal_needs_both_values():
    """없는 것을 만들지 않는다 — 비교할 두 값이 다 있어야 문장을 낸다."""
    assert derive.form_reversal({"home_pitcher": {"era_season": 3.86}}, JG) == []
    r = {"home_pitcher": {"name": "황동하", "era_season": 3.86, "era_recent": 5.40}}
    out = derive.form_reversal(r, JG)
    assert len(out) == 1 and "악화" in out[0] and "3.86" in out[0]


def test_form_reversal_ignores_small_gaps():
    r = {"home_pitcher": {"name": "X", "era_season": 4.00, "era_recent": 4.50}}
    assert derive.form_reversal(r, JG) == []


def test_form_reversal_catches_rank_vs_recent_form():
    r = {"home_standing": {"rank": 2}, "home_usage": {"results_l3": "LLL"}}
    out = derive.form_reversal(r, JG)
    assert out and "부진" in out[0]
    r2 = {"away_standing": {"rank": 9}, "away_usage": {"results_l3": "WWW"}}
    assert "상승" in derive.form_reversal(r2, JG)[0]


# ---------------------------------------------------------------- bullpen_overused

def test_bullpen_overused_follows_the_original_definition():
    """정의는 '리그 평균 대비 과다한 쪽'. 새 상수를 만들지 않는다."""
    usage = {f"T{i}": {"relief_batters_l3": v} for i, v in
             enumerate([86, 58, 54, 53, 52, 51, 46, 44, 42, 37])}
    mean = sum(v["relief_batters_l3"] for v in usage.values()) / len(usage)
    assert round(mean, 1) == 52.3
    both = derive.bullpen_overused(usage, {"home": "T1", "away": "T2"})   # 58, 54
    assert both == "양팀"
    one = derive.bullpen_overused(usage, {"home": "T1", "away": "T8"})    # 58, 42
    assert one == "홈"
    none = derive.bullpen_overused(usage, {"home": "T8", "away": "T9"})   # 42, 37
    assert none == "없음"


def test_bullpen_overused_returns_none_without_league_sample():
    """🔴 '없음'으로 채우면 '측정했는데 과다하지 않다'와 '못 쟀다'가 섞인다."""
    assert derive.bullpen_overused({}, JG) is None
    assert derive.bullpen_overused({"A": {"relief_batters_l3": 40}}, JG) is None


def test_bullpen_overused_is_not_applied_to_research():
    """🔴 λ에 넣지 않는다 (2026-08-27 측정).

    원 정의를 그대로 계산하니 10팀 중 4팀이 '과다'로 나왔다 — 진짜 이상치
    (한화 86, 평균의 1.64배)와 3% 초과(NC 54)가 같은 통에 들어간다.
    딥서치와 실제로 갈렸고(#670 NC@LG: "홈" vs "양팀"), `_bullpen_factor`가
    "홈"·"원정"에만 계수를 붙이므로 그 차이가 **λ를 바꾼다.**
    변별력 있는 문턱은 결과 데이터로 재야 하는데 아직 잴 수 없다(#49).
    """
    usage = {f"T{i}": {"relief_batters_l3": v} for i, v in enumerate([86, 58, 54, 40])}
    r: dict = {}
    filled = derive.apply(r, {"home": "T1", "away": "T2"}, usage)
    assert "bullpen_overused" not in filled
    assert "bullpen_overused" not in r


# ---------------------------------------------------------------- apply

def test_apply_never_overwrites_existing_values():
    """이미 있는 값은 덮지 않는다 — 출처가 딥서치든 공식 API든 같다."""
    r = {"motivation": "딥서치가 준 값", "splits": "딥서치 splits",
         "home_standing": {"rank": 1, "w": 65, "l": 42, "d": 3},
         "away_standing": {"rank": 2, "w": 66, "l": 44, "d": 3}}
    filled = derive.apply(r, JG, None)
    assert r["motivation"] == "딥서치가 준 값"
    assert r["splits"] == "딥서치 splits"
    assert filled == []


def test_apply_fills_only_the_gaps():
    r = {"home_standing": {"rank": 4, "w": 61, "l": 50, "d": 2,
                           "games_behind": 5.5, "remaining": 31},
         "away_standing": {"rank": 6, "w": 50, "l": 59, "d": 2,
                           "games_behind": 15.5, "remaining": 33}}
    filled = derive.apply(r, JG, None)
    assert set(filled) == {"motivation", "splits"}
    assert "4위" in r["motivation"]
