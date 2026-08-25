"""[1-2] 경기력 정보가 승률을 실제로 움직이는지 검증.

실사고(2026-08-25 파드리스전): "애덤·머스그로브·피베타·지올리토 이탈"을 서술에 써놓고
승률은 58.7% 그대로였다. 수집한 정보가 확률에 반영되지 않으면 그 정보는 장식일 뿐이다.
"""

from app.config import Settings
from app.engine.performance import WinProbAdjuster, _name_of, _split_absences

S = Settings(_env_file=None)


def adj():
    return WinProbAdjuster(S)


def _jg():
    return {"home": "San Diego Padres", "away": "Pittsburgh Pirates"}


# ---------------------------------------------------------------- 개별 계수

def test_starter_matchup_uses_recent_form_not_season():
    """[1-2] 선발 매치업은 최근 5경기 ERA 기준, 1.00당 ±3%p."""
    a = adj()
    assert abs(a.starter_matchup(2.80, 4.10) - 0.039) < 1e-6      # (4.10-2.80)*0.03
    assert a.starter_matchup(4.10, 2.80) < 0                       # 방향이 반대면 마이너스
    assert a.starter_matchup(None, 3.0) == 0.0                     # 한쪽이 없으면 조정 없음


def test_starter_matchup_is_capped():
    """[1-2] 극단적 ERA 차가 확률을 지배하지 않도록 상한을 둔다."""
    assert adj().starter_matchup(1.00, 9.00) == S.adj_starter_era_cap


def test_short_outings_penalise_bullpen_exposure():
    """[1-2] 최근 평균 5이닝 미만이면 -2%p."""
    a = adj()
    assert a.short_outings(4.2) == -S.adj_short_start
    assert a.short_outings(6.1) == 0.0
    assert a.short_outings(None) == 0.0


def test_absences_weighted_by_role():
    """[1-2] 주전 -2%p / 팀 최다 기여 타자 -4%p / 핵심 불펜 -2%p."""
    a = adj()
    d_top, _ = a.absences(["Oneil Cruz 팀 최다 홈런 타자 결장"])
    d_pen, _ = a.absences(["Jason Adam 마무리 부상 결장"])
    d_reg, _ = a.absences(["Ha-Seong Kim 결장"])
    assert d_top == -S.adj_top_batter_out
    assert d_pen == -S.adj_key_reliever_out
    assert d_reg == -S.adj_key_batter_out


def test_absence_total_is_capped():
    """[1-2] 결장 누적 보정에 상한 — 한 요소가 확률을 무너뜨리지 않게."""
    many = [f"Player{i} 결장" for i in range(10)]
    total, notes = adj().absences(many)
    assert total == -S.adj_absence_cap
    assert any("상한" in n for n in notes)


def test_recent_form_thresholds():
    a = adj()
    assert a.recent_form("WWWWL") == S.adj_form_hot        # 4승
    assert a.recent_form("LLLLW") == -S.adj_form_cold      # 4패
    assert a.recent_form("WWLLW") == 0.0                   # 3승2패
    assert a.recent_form("WWL") == 0.0                     # 표본 부족


def test_home_edge_by_sport():
    a = adj()
    assert a.home_edge("mlb") == S.adj_home_mlb == 0.03
    assert a.home_edge("soccer") == S.adj_home_soccer == 0.05


def test_bullpen_overuse_detected_from_prose():
    a = adj()
    assert a.bullpen_overuse("파드리스 불펜 최근 3일 연투로 피로 누적") == -S.adj_bullpen_overuse
    assert a.bullpen_overuse("불펜 소모 보통, 전원 대기 가능") == 0.0
    assert a.bullpen_overuse(None) == 0.0


# ---------------------------------------------------------------- 순차 적용

def test_padres_case_absences_actually_move_the_number():
    """[1-2] 회귀: 핵심 이탈 4명이 기록됐는데 승률이 그대로면 안 된다."""
    research = {
        "home_pitcher": {"name": "Ray", "era_recent": 2.80},
        "away_pitcher": {"name": "Ashcraft", "era_recent": 4.10},
        "absences": [
            "San Diego Padres의 Jason Adam 마무리 부상 결장",
            "San Diego Padres의 Joe Musgrove 선발 이탈",
            "San Diego Padres의 Nick Pivetta 선발 결장",
        ],
    }
    out = adj().adjust(0.587, _jg(), research, "mlb")
    assert out["p"] != 0.587, "결장 정보가 확률을 움직이지 않았다"
    # 홈 이탈 3명 = -6%p, 선발 우위 +3.9%p → 순변화는 음수여야 한다
    assert out["p"] < 0.587
    assert any("Jason Adam" in step for step in out["trace"])
    assert any("선발 매치업" in step for step in out["trace"])


def test_trace_shows_every_step_with_base_and_final():
    """[1-2] 조정 과정을 상세 데이터에 그대로 찍을 수 있어야 한다."""
    research = {"home_recent_form": {"form": "WWWWL"}, "absences": []}
    out = adj().adjust(0.55, _jg(), research, "mlb")
    assert out["trace"][0].startswith("기준 55%")
    assert out["trace"][-1].startswith("최종 ")
    assert all("%p" in s for s in out["trace"][1:-1])


def test_opponent_absence_helps_home():
    """[1-2] 원정 팀 결장은 홈 승률을 올린다 (방향이 뒤집히지 않게)."""
    research = {"absences": ["Pittsburgh Pirates의 Oneil Cruz 팀 최다 홈런 타자 결장"]}
    out = adj().adjust(0.50, _jg(), research, "mlb")
    assert out["p"] > 0.50


def test_probability_stays_in_bounds():
    research = {"absences": [f"San Diego Padres의 P{i} 결장" for i in range(20)]}
    out = adj().adjust(0.10, _jg(), research, "mlb")
    assert 0.05 <= out["p"] <= 0.95


def test_unused_material_is_reported():
    """[4-3] 서술에 쓰였지만 확률에 반영되지 않은 재료를 표시한다."""
    research = {"splits": "홈 12승 5패", "h2h_history": "최근 3연승"}
    out = adj().adjust(0.5, _jg(), research, "mlb")
    assert "홈/원정 스플릿" in out["unused"] and "상대전적" in out["unused"]


# ---------------------------------------------------------------- 헬퍼

def test_name_extraction_skips_team_name():
    """결장 사유에 팀명이 아니라 선수명이 나와야 한다."""
    assert _name_of("San Diego Padres의 Jason Adam 마무리 결장", "San Diego Padres") == "Jason Adam"
    assert _name_of("Oneil Cruz 결장") == "Oneil Cruz"


def test_absences_split_by_team():
    home, away = _split_absences(
        ["San Diego Padres의 Jason Adam 결장", "Pittsburgh Pirates의 Oneil Cruz 결장",
         "소속 불명 선수 결장"], _jg())
    assert len(home) == 1 and len(away) == 1        # 소속 불명은 어느 쪽에도 넣지 않는다


# ---------------------------------------------------------------- [4-3] 정보 → 계수 매핑

def test_every_mapped_field_has_a_coefficient():
    """[4-3] 수집 필드가 어느 조정 계수로 가는지 표로 명시돼 있어야 한다."""
    from app.engine.performance import FIELD_TO_COEFFICIENT, UNMAPPED_FIELDS

    assert "absences" in FIELD_TO_COEFFICIENT
    assert "adj_key_reliever_out" in FIELD_TO_COEFFICIENT["absences"]
    assert "bullpen_overused" in FIELD_TO_COEFFICIENT
    # 계수가 없는 필드는 미반영 목록에 있어야 한다 (양쪽에 동시에 있으면 안 됨)
    assert set(FIELD_TO_COEFFICIENT) & set(UNMAPPED_FIELDS) == set()
    for key in ("splits", "h2h_history", "park", "weather", "rotation_plan"):
        assert key in UNMAPPED_FIELDS


def test_unmapped_fields_are_reported_as_unused():
    """[4-3] 서술에 쓰였지만 확률에 반영되지 않은 정보는 반드시 표기된다."""
    research = {"park": "쿠어스필드 — 타자 친화", "weather": "기온 28도 맞바람",
                "rotation_plan": "불펜데이 예고", "splits": "홈 12승 5패"}
    out = adj().adjust(0.5, _jg(), research, "mlb")
    for name in ("구장 특성", "날씨", "로테이션 계획", "홈/원정 스플릿"):
        assert name in out["unused"]


def test_bullpen_side_flag_moves_the_right_team():
    """[4-1] bullpen_overused가 어느 쪽인지 알려주면 방향까지 정확히 반영한다."""
    a = adj()
    home_worn = a.adjust(0.50, _jg(), {"bullpen_overused": "홈"}, "mlb")
    away_worn = a.adjust(0.50, _jg(), {"bullpen_overused": "원정"}, "mlb")
    both = a.adjust(0.50, _jg(), {"bullpen_overused": "양팀"}, "mlb")
    assert home_worn["p"] < 0.50 < away_worn["p"]
    assert both["p"] == 0.50                       # 상쇄 — 조정 없음
    assert any("상쇄" in s for s in both["trace"])


def test_ip_avg_uses_dedicated_field_first():
    """[4-1] 전용 필드(ip_avg_recent)가 있으면 서술 파싱보다 우선한다."""
    from app.engine.performance import _ip_avg

    assert _ip_avg({"ip_avg_recent": 4.1, "last5": "평균 6.0이닝"}) == 4.1
    assert _ip_avg({"last5": "최근 5경기 평균 4.2이닝"}) == 4.2
    assert _ip_avg({}) is None
