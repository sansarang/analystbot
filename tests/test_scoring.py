"""기대득점(λ) 기반 확률 엔진 — 포아송(야구)·스켈람(축구) 검증.

학술 근거: Wharton MLB 예측(정확도 61.77%, 변수 중요도 OBP>ISO>WHIP/FIP),
분데스리가 xG 논문(홈 승 ROI +10~15% / 원정 -17%), MLB 표준 포아송 모델링.
"""

import math

import pytest

from app.config import Settings
from app.engine.scoring import (
    cap_probability,
    game_distribution,
    is_away_underdog,
    market_probability,
    mlb_lambdas,
    mlb_market_probs,
    poisson_pmf,
    required_prob,
    score_pmf,
    soccer_lambdas,
    soccer_market_probs,
)

S = Settings(_env_file=None)


def _jg(**over):
    jg = {"game_id": 1, "home": "H", "away": "A", "alt_markets": [],
          "best_odds": {"H": 1.70, "A": 2.30}}
    jg.update(over)
    return jg


def _res(**over):
    r = {"home_offense": {"woba_30d": 0.320}, "away_offense": {"woba_30d": 0.320},
         "home_pitcher": {"era_season": 4.20}, "away_pitcher": {"era_season": 4.20}}
    r.update(over)
    return r


# ---------------------------------------------------------------- 분포 기초

def test_poisson_pmf_sums_to_one():
    assert abs(sum(poisson_pmf(4.4, k) for k in range(30)) - 1.0) < 1e-9
    assert poisson_pmf(0.0, 0) == 1.0


def test_score_pmf_normalised_and_switchable():
    """과분산 관찰 시 음이항으로 바꿀 수 있게 분포 생성이 한 곳에 모여 있다."""
    pois = score_pmf(4.4, 20)
    negb = score_pmf(4.4, 20, dispersion=8.0)
    assert abs(sum(pois) - 1.0) < 1e-9 and abs(sum(negb) - 1.0) < 1e-9
    # 음이항이 과분산 → 꼬리가 더 두껍다
    assert sum(negb[10:]) > sum(pois[10:])


# ---------------------------------------------------------------- λ 산출

def test_lambda_order_follows_spec():
    """[2-2] 타선 → 상대 선발 → 구장 → 날씨 → 불펜 → 좌우 → 홈 이점 순서."""
    r = mlb_lambdas(_jg(), _res(
        home_offense={"woba_30d": 0.330}, away_offense={"woba_30d": 0.300},
        home_pitcher={"siera": 3.60, "throws": "R", "ip_avg_recent": 6.0},
        away_pitcher={"siera": 4.80, "throws": "L", "ip_avg_recent": 4.2},
        park="타자 친화", weather="기온 28도, 뒷바람", bullpen_overused="원정"), S)
    joined = " | ".join(r.trace)
    for token in ("기본 λ", "타선", "상대 선발", "구장", "날씨", "불펜", "홈 이점", "최종 λ"):
        assert token in joined, token
    assert r.usable and r.home > r.away


def test_luck_adjusted_metrics_take_priority_over_era():
    """[2-2] SIERA > xFIP > FIP > ERA — ERA는 운에 오염된 지표라 최후에 쓴다."""
    with_siera = mlb_lambdas(_jg(), _res(
        away_pitcher={"siera": 3.00, "xfip": 4.00, "fip": 4.50, "era_season": 6.00}), S)
    assert "SIERA 3.00" in " ".join(with_siera.trace)

    only_era = mlb_lambdas(_jg(), _res(away_pitcher={"era_season": 6.00}), S)
    assert "시즌 ERA 6.00" in " ".join(only_era.trace)
    # 같은 투수라도 SIERA(3.00)를 쓰면 상대 기대득점이 낮다
    assert with_siera.home < only_era.home


def test_offense_metrics_drive_lambda():
    """[2-1] 타선 지표가 예측력이 높다 — 타선이 좋아지면 λ가 올라간다."""
    weak = mlb_lambdas(_jg(), _res(home_offense={"woba_30d": 0.295}), S)
    strong = mlb_lambdas(_jg(), _res(home_offense={"woba_30d": 0.345}), S)
    assert strong.home > weak.home


def test_missing_core_metrics_blocks_probability():
    """[5] 핵심 지표(타선·선발)가 모두 없으면 확률을 산출하지 않는다."""
    r = mlb_lambdas(_jg(), {"park": "타자 친화"}, S)
    assert r.usable is False
    assert any("타선" in m for m in r.missing)
    assert game_distribution(_jg(), {"park": "타자 친화"}, "mlb", S) is None


def test_lambda_clamped_to_realistic_band():
    """단일 요인이 λ를 지배하지 않도록 현실 범위로 절사한다."""
    r = mlb_lambdas(_jg(), _res(
        home_offense={"woba_30d": 0.500}, away_offense={"woba_30d": 0.200},
        home_pitcher={"siera": 1.00}, away_pitcher={"siera": 9.00}), S)
    assert S.lam_min <= r.home <= S.lam_max
    assert S.lam_min <= r.away <= S.lam_max


def test_missing_optional_metrics_are_reported_not_fatal():
    """[5] 수집 실패 지표는 보정을 건너뛰고 '미반영'으로 남긴다."""
    r = mlb_lambdas(_jg(), _res(), S)
    assert r.usable
    assert "파크팩터" in r.missing and "날씨" in r.missing


# ---------------------------------------------------------------- 마켓 확률

def test_all_markets_come_from_one_distribution():
    """[6] 승패·런라인·토탈·F5가 같은 분포에서 나온다 — 마켓별 근거가 불필요하다."""
    m = mlb_market_probs(4.9, 3.8, settings=S)
    assert abs(m["h2h"]["home"] + m["h2h"]["away"] - 1.0) < 1e-6
    assert m["totals"] and all(
        abs(v["Over"] + v["Under"] - 1.0) < 1e-6 for v in m["totals"].values())
    sp = m["spreads"][1.5]
    assert abs(sp["home_minus"] + sp["away_plus"] - 1.0) < 1e-6
    assert abs(sum(m["f5"][k] for k in ("home", "away", "draw")) - 1.0) < 1e-6
    # 우세한 팀이 승패·런라인 모두에서 앞선다
    assert m["h2h"]["home"] > 0.5 and sp["home_minus"] > sp["away_minus"]


def test_f5_is_partial_game_distribution():
    """[6] F5는 5이닝까지의 부분 분포 — 무승부 확률이 정규 경기보다 높다."""
    m = mlb_market_probs(4.6, 4.4, settings=S)
    assert m["f5"]["draw"] > 0.10
    assert m["f5"]["lambda"]["home"] < m["lambda"]["home"]


def test_totals_monotonic_in_line():
    """라인이 올라가면 오버 확률은 내려간다 (분포 일관성)."""
    m = mlb_market_probs(4.5, 4.5, lines={"totals": [7.5, 8.5, 9.5, 10.5]}, settings=S)
    overs = [m["totals"][l]["Over"] for l in (7.5, 8.5, 9.5, 10.5)]
    assert overs == sorted(overs, reverse=True)


def test_market_probability_lookup():
    jg = _jg(alt_markets=[{"market": "totals", "side": "Under", "line": 8.5},
                          {"market": "spreads", "side": "A", "line": 1.5}])
    d = game_distribution(jg, _res(home_offense={"woba_30d": 0.335}), "mlb", S)
    assert d is not None
    assert market_probability(d, "h2h", "H", None, jg) > 0.5
    assert market_probability(d, "totals", "Under", 8.5, jg) is not None
    assert market_probability(d, "spreads", "A", 1.5, jg) is not None
    assert market_probability(d, "f5", "H", None, jg) is not None
    assert market_probability(d, "btts", "Yes", None, jg) is None      # 야구엔 없다


# ---------------------------------------------------------------- 축구 스켈람

def test_skellam_draw_comes_from_distribution():
    """[3] 무승부를 별도 추정하지 않는다 — 분포에서 P(diff==0)로 나온다."""
    m = soccer_market_probs(1.5, 1.2)
    h, d, a = m["h2h"]["home"], m["h2h"]["draw"], m["h2h"]["away"]
    assert abs(h + d + a - 1.0) < 1e-6
    assert 0.15 < d < 0.35          # 축구 무승부 현실 범위
    assert h > a                     # λ가 높은 쪽이 앞선다


def test_soccer_board_markets_all_present():
    """[6] 승무패·더블찬스 3종·BTTS·토탈·핸디가 한 분포에서 나온다."""
    m = soccer_market_probs(1.6, 1.1)
    assert abs(m["dc"]["home"] - (m["h2h"]["home"] + m["h2h"]["draw"])) < 1e-6
    assert abs(m["dc"]["12"] - (m["h2h"]["home"] + m["h2h"]["away"])) < 1e-6
    assert abs(m["btts"]["Yes"] + m["btts"]["No"] - 1.0) < 1e-6
    assert m["totals"] and m["spreads"]


def test_soccer_lambda_from_xg():
    """[3] 팀 기대 xG = 공격 xG × 상대 수비 xGA × 홈 계수."""
    r = soccer_lambdas({"home": "H", "away": "A"},
                       {"home_recent_form": {"xg6": 1.90, "xga6": 0.90},
                        "away_recent_form": {"xg6": 1.00, "xga6": 1.70}}, S)
    assert r.usable and r.home > r.away
    assert any("xG" in x for x in r.trace)

    none_xg = soccer_lambdas({"home": "H", "away": "A"}, {}, S)
    assert none_xg.usable is False


# ---------------------------------------------------------------- 상한·비대칭

def test_cap_blocks_impossible_probabilities():
    """§0 야구 68%/32%, 축구 72%/10% — 초과는 강한 픽이 아니라 계산 오류다.

    근거: 운의 비중 MLB 27.8%. 완벽한 정보를 가져도 예측 상한은 약 72%이고
    학계 최고 모델은 61.77%다.
    """
    p, note = cap_probability(0.778, "mlb", S)
    assert p == S.max_win_prob_mlb == 0.68 and "원값 78%" in note
    low, note2 = cap_probability(0.234, "mlb", S)
    assert low == S.min_win_prob_mlb == 0.32 and "원값 23%" in note2
    assert cap_probability(0.62, "mlb", S) == (0.62, None)
    assert cap_probability(0.80, "soccer", S)[0] == 0.72
    # 축구는 3-way라 하한이 비대칭이다 (원정 승 확률은 낮게 나올 수 있다)
    assert cap_probability(0.05, "soccer", S)[0] == 0.10


def test_edge_vs_market_limit():
    """§0 세계 최고 조직도 시장 대비 엣지가 1~2%다. 5% 초과는 데이터 오류로 본다."""
    from app.engine.scoring import edge_exceeds_limit, edge_vs_market

    assert edge_vs_market(0.62, 1.72) == pytest.approx(0.0386, abs=1e-3)
    over, edge = edge_exceeds_limit(0.70, 1.72, S)
    assert over is True and edge > S.max_edge_vs_market
    assert edge_exceeds_limit(0.60, 1.72, S)[0] is False
    assert edge_exceeds_limit(None, 1.72, S)[0] is False


def test_away_threshold_is_five_points_higher():
    """[4] 분데스리가 연구: 원정 베팅 ROI -17% — 원정 픽 임계를 5%p 올린다."""
    jg = _jg()
    assert required_prob("h2h", "H", jg, S) == S.min_win_prob
    assert required_prob("h2h", "A", jg, S) == pytest.approx(S.min_win_prob + 0.05)
    assert required_prob("dc", "A", jg, S) > S.min_win_prob
    assert required_prob("totals", "Over", jg, S) == S.min_win_prob   # 팀 픽이 아니다


def test_away_underdog_detected():
    """[4] 원정 언더독 — 통계적으로 가장 불리한 유형."""
    jg = _jg()
    assert is_away_underdog("h2h", "A", jg, 2.30) is True
    assert is_away_underdog("h2h", "H", jg, 1.70) is False
    assert is_away_underdog("totals", "Over", jg, 2.30) is False


# ---------------------------------------------------------------- §1 타선 우선순위·결장

def test_offense_priority_xwoba_first():
    """[1-1] 타선 우선순위 xwOBA > wOBA > OBP+ISO — xwOBA가 운 오염이 가장 적다."""
    with_x = mlb_lambdas(_jg(), _res(home_offense={"xwoba_30d": 0.345, "woba_30d": 0.300}), S)
    assert "xwOBA 0.345" in " ".join(with_x.trace)

    only_woba = mlb_lambdas(_jg(), _res(home_offense={"woba_30d": 0.300}), S)
    assert "wOBA 0.300" in " ".join(only_woba.trace)
    assert with_x.home > only_woba.home     # 더 좋은 지표를 썼으므로 λ가 높다


def test_offense_falls_back_to_obp_plus_iso():
    """[1-1] xwOBA·wOBA가 없으면 OBP와 ISO를 결합해 대용한다."""
    r = mlb_lambdas(_jg(), _res(home_offense={"obp_30d": 0.340, "iso_30d": 0.200}), S)
    joined = " ".join(r.trace)
    assert "OBP 0.340" in joined and "ISO 0.200" in joined
    # 장타력이 높으면 λ도 높다
    low_iso = mlb_lambdas(_jg(), _res(home_offense={"obp_30d": 0.340, "iso_30d": 0.110}), S)
    assert r.home > low_iso.home


def test_recent_30d_beats_season():
    """[1-1] 최근 30일 지표가 시즌 누적보다 우선한다."""
    r = mlb_lambdas(_jg(), _res(home_offense={"woba_30d": 0.350, "woba": 0.290}), S)
    assert "wOBA 0.350" in " ".join(r.trace)


def test_absences_move_lambda_directly():
    """[1-7] 결장이 λ에 직접 반영된다 — 핵심 타자 -2%, 최다 기여자 -4%."""
    base = mlb_lambdas(_jg(), _res(), S)
    top_out = mlb_lambdas(_jg(), _res(
        absences=["H의 Manny Machado 팀 최다 홈런 타자 결장"]), S)
    reg_out = mlb_lambdas(_jg(), _res(absences=["H의 Ha-Seong Kim 결장"]), S)
    assert top_out.home < reg_out.home < base.home


def test_closer_absence_raises_opponent_lambda():
    """[1-7] 마무리 결장은 **상대 팀** λ를 올린다 (그 팀 불펜 억제력이 떨어진다)."""
    base = mlb_lambdas(_jg(), _res(), S)
    out = mlb_lambdas(_jg(), _res(absences=["H의 Jason Adam 마무리 부상 결장"]), S)
    assert out.away > base.away          # 홈 마무리가 빠지면 원정 득점 기대가 오른다
    assert any("상대 불펜 결장" in x for x in out.trace)


def test_absence_effect_is_capped():
    """[1-7] 결장 누적 보정에 상한 — 한 요소가 λ를 무너뜨리지 않게."""
    many = [f"H의 Player{i} 결장" for i in range(12)]
    out = mlb_lambdas(_jg(), _res(absences=many), S)
    base = mlb_lambdas(_jg(), _res(), S)
    assert out.home >= base.home * (1 - S.absence_cap) - 1e-6


def test_absence_names_exclude_team():
    """결장 사유에 팀명이 아니라 선수명이 들어간다."""
    out = mlb_lambdas({"home": "San Diego Padres", "away": "A"}, _res(
        absences=["San Diego Padres의 Manny Machado 팀 최다 홈런 타자 결장"]), S)
    joined = " ".join(out.trace)
    assert "Manny Machado" in joined
