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


def test_market_comparison_is_removed():
    """[§8-18] 시장 대비 괴리 판정을 **삭제**했다.

    우리 확률을 시장 환산값과 비교해 5% 넘게 벗어나면 '데이터 오류'로 지웠다.
    그러면 시장을 넘어설 방법이 영원히 없다 — 실사고: 판정이 근거를 대고 낸
    지바 롯데 70%가 시장 37%와 어긋난다는 이유로 삭제됐다(2026-08-26).
    """
    import app.engine.scoring as sc

    assert not hasattr(sc, "edge_vs_market")
    assert not hasattr(sc, "edge_exceeds_limit")

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


# ---------------------------------------------------------------- §8 문서 계약

def test_model_doc_records_the_hard_limits():
    """[§8] 한계값이 문서에 근거와 함께 박혀 있어야 임의 완화를 막을 수 있다."""
    import pathlib

    doc = pathlib.Path("docs/MODEL.md").read_text()
    assert "임의로 완화하지 마라" in doc
    assert "61.77" in doc                       # 학계 최고 정확도
    assert "27.8" in doc                        # MLB 운 비중
    assert "Starlizard" in doc and "1~2%" in doc
    for token in ("0.68", "0.72", "0.05", "58~60%"):
        assert token in doc, token
    # 미완 항목을 숨기지 않는다
    assert "계수 학습이 미완" in doc


def test_claude_md_registers_model_doc():
    """[§8] 향후 세션이 MODEL.md를 먼저 읽도록 CLAUDE.md에 등재돼 있어야 한다."""
    import pathlib

    doc = pathlib.Path("CLAUDE.md").read_text()
    assert "docs/MODEL.md" in doc
    assert "절대 완화하면 안 되는 한계값" in doc


def test_low_sample_starter_is_marked_in_trace():
    """표본 부족으로 리그 평균이 대체된 투수는 트레이스에 사유가 보여야 한다.

    값이 채워졌다는 것과 그 투수를 안다는 것은 다르다 — 구분이 안 되면
    '리그 평균 투수'를 실제 실력으로 오해하게 된다.
    """
    from app.config import get_settings
    from app.engine.scoring import mlb_lambdas

    s = get_settings()
    jg = {"home": "Detroit Tigers", "away": "Tampa Bay Rays"}
    research = {
        "home_offense": {"xwoba_30d": 0.320},
        "away_offense": {"xwoba_30d": 0.320},
        "home_pitcher": {"xwoba_allowed": 0.320},
        "away_pitcher": {"xwoba_allowed": 0.320, "low_sample": True,
                         "sample_note": "표본 부족 — 리그 평균 적용"},
    }
    lam = mlb_lambdas(jg, research, s)
    joined = " ".join(lam.trace)
    assert "표본 부족 — 리그 평균 적용" in joined


# ---------------------------------------------------------------- [§8-5] 타선 대칭 적용

def test_offense_symmetric_removes_team_difference():
    """대칭 적용이면 타선 지표 차이가 **승률로 새어 나가지 않는다**.

    실측(2026-08-26, 1324경기): 타선 지표는 두 팀의 '차이'를 틀리게 잡고 '합계'는
    맞게 잡는다 — 비대칭 적용 시 승패 0.5257(기준선 미달), 대칭 0.5355(기준선 초과).
    선발·구장은 그대로 두고 타선만 대칭화한다.
    """
    sym = Settings(_env_file=None, offense_symmetric=True)
    res = _res(home_offense={"woba_30d": 0.350}, away_offense={"woba_30d": 0.290})
    r = mlb_lambdas(_jg(), res, sym)
    assert r.usable
    # 선발·구장이 같으므로 λ는 홈 이점만큼만 차이 나야 한다
    assert r.home > r.away                                   # 홈 이점은 살아 있다
    flat = mlb_lambdas(_jg(), _res(), sym)                   # 타선이 동일한 경우
    # λ는 소수 3자리로 반올림돼 나오므로 1e-9는 반올림 잡음에 걸린다.
    # 1e-3이면 잡음(≈3e-5)보다 크고, 실제 누출(비대칭 모드는 아래에서 0.05↑)보다 훨씬 작다.
    assert abs((r.home / r.away) - (flat.home / flat.away)) < 1e-3, (
        "대칭 적용인데 타선 차이가 홈/원정 비율을 바꿨다")


def test_offense_symmetric_keeps_total_level():
    """대칭 적용은 **합계 수준을 보존**한다 — 제거와 다른 점이 이것이다."""
    sym = Settings(_env_file=None, offense_symmetric=True)
    strong = mlb_lambdas(_jg(), _res(home_offense={"woba_30d": 0.350},
                                     away_offense={"woba_30d": 0.350}), sym)
    weak = mlb_lambdas(_jg(), _res(home_offense={"woba_30d": 0.290},
                                   away_offense={"woba_30d": 0.290}), sym)
    assert strong.home + strong.away > weak.home + weak.away, (
        "양 팀이 모두 강타선인데 총득점 기대가 오르지 않았다")


def test_offense_asymmetric_mode_still_available():
    """스위치를 끄면 종전 비대칭 동작 — 재측정 가능성을 남긴다."""
    asym = Settings(_env_file=None, offense_symmetric=False)
    res = _res(home_offense={"woba_30d": 0.350}, away_offense={"woba_30d": 0.290})
    r = mlb_lambdas(_jg(), res, asym)
    flat = mlb_lambdas(_jg(), _res(), asym)
    # 위 대칭 테스트의 허용오차(1e-3)보다 훨씬 큰 차이가 나야 그 테스트가 의미를 갖는다
    assert abs((r.home / r.away) - (flat.home / flat.away)) > 0.05, (
        "비대칭 모드인데 타선 차이가 반영되지 않았다")


def test_offense_symmetric_needs_both_sides():
    """한쪽 타선 지표가 없으면 평균을 낼 수 없다 — 있는 쪽만 종전대로 적용한다."""
    sym = Settings(_env_file=None, offense_symmetric=True)
    res = _res(home_offense={"woba_30d": 0.350})
    res["away_offense"] = {}
    r = mlb_lambdas(_jg(), res, sym)
    assert any("타선" in line for line in r.trace)
    assert any("타선 지표" in m for m in r.missing)


def test_offense_symmetric_trace_says_so():
    """확률을 움직인 근거는 표시된다 — '(확률 미반영)' 규율의 반대편."""
    sym = Settings(_env_file=None, offense_symmetric=True)
    r = mlb_lambdas(_jg(), _res(home_offense={"woba_30d": 0.350},
                                away_offense={"woba_30d": 0.290}), sym)
    assert any("양 팀 평균" in line for line in r.trace)


# ---------------------------------------------------------------- [§8-8] 종목별 분산모수

def test_dispersion_is_sport_specific():
    """야구는 과분산(음이항), 축구는 **미측정이라 포아송**이다.

    실측(2026-08-26, 1496경기): 야구 총득점 분산 20.52 / 평균 8.92 → 비율 2.302.
    포아송은 1.0을 가정하므로 확률이 과신 쪽으로 치우쳤다.
    축구는 같은 측정을 한 적이 없다 — 같은 값을 쓰면 임의 튜닝이 된다.
    """
    from app.engine.scoring import dispersion_for

    s = Settings(_env_file=None)
    assert dispersion_for("mlb", s) == pytest.approx(3.3)
    assert dispersion_for("soccer", s) is None


def test_global_dispersion_overrides_sport():
    """전역 강제값이 있으면 종목값을 덮는다 — 실험용 탈출구."""
    from app.engine.scoring import dispersion_for

    s = Settings(_env_file=None, score_dispersion=7.0)
    assert dispersion_for("mlb", s) == 7.0
    assert dispersion_for("soccer", s) == 7.0


def test_overdispersion_widens_scores_and_tempers_confidence():
    """과분산은 득점 분포를 넓히고 승률을 0.5 쪽으로 되돌린다.

    이것이 목적이다 — 포아송은 '58%'라고 해놓고 실제로는 55.4%만 맞혔다
    (실측 1496경기). 음이항 r=3.3에서 58%↑ 픽은 41.5%→18.0%로 줄지만
    그 적중률은 55.4%→57.2%로 올랐다.
    """
    pois = mlb_market_probs(5.2, 3.6, None, None, settings=S)["h2h"]["home"]
    nb = mlb_market_probs(5.2, 3.6, None, 3.3, settings=S)["h2h"]["home"]
    assert pois > nb > 0.5, "과분산인데 확률이 0.5 쪽으로 오지 않았다"


def test_f5_share_matches_measurement():
    """F5 득점 비중은 5/9 근사가 아니라 **실측값**이다 (6807경기 · 0.561)."""
    s = Settings(_env_file=None)
    assert s.f5_share == pytest.approx(0.561, abs=0.001)
    probs = mlb_market_probs(4.8, 4.2, None, None, settings=s)
    lam5 = probs["f5"]["lambda"]
    assert lam5["home"] == pytest.approx(4.8 * 0.561, abs=0.002)


# ---------------------------------------------------------------- [§8-14] KBO

def _kbo_jg():
    return {"game_id": 1, "home": "LG Twins", "away": "NC Dinos", "league": "KBO",
            "sport": "kbo", "alt_markets": [], "best_odds": {}}


def _kbo_res(**over):
    r = {"league_baselines": {"obp": 0.3478, "ops": 0.7521, "slg": 0.4043},
         "home_offense": {"obp_30d": 0.357}, "away_offense": {"obp_30d": 0.353},
         "home_pitcher": {"era_season": 4.14}, "away_pitcher": {"era_season": 3.89}}
    r.update(over)
    return r


def test_kbo_uses_baseball_markets_not_soccer():
    """[§8-14] KBO는 야구다 — 승패 합이 1이어야 하고 무승부 행이 없어야 한다.

    실사고(2026-08-26): λ만 야구로 바꾸고 마켓 확률을 축구 함수로 보냈다.
    결과가 승패 43.6%/43.8%(합 87.4%, 나머지는 무승부 질량)로 나왔고
    토탈 기본 라인이 축구값 1.5/2.5/3.5로 찍혔다.
    """
    d = game_distribution(_kbo_jg(), _kbo_res(), "kbo", S)
    assert d is not None
    h = d["probs"]["h2h"]
    assert "draw" not in h, "야구에 무승부 행이 생겼다"
    assert abs(h["home"] + h["away"] - 1.0) < 0.01, f"승패 합이 1이 아니다: {h}"
    # 토탈 기본 라인이 야구 수준(9~12점)이어야 한다
    lines = list((d["probs"].get("totals") or {}).keys())
    assert lines and min(lines) >= 7.0, f"토탈 라인이 축구값이다: {lines}"


def test_kbo_lambda_matches_league_run_environment():
    """[§8-14] KBO 리그 평균 득점은 MLB보다 0.69점 높다(실측 5.094 vs 4.40).

    MLB 상수를 그대로 쓰면 λ 합계가 리그 평균보다 1.4점 낮게 나온다.
    """
    d = game_distribution(_kbo_jg(), _kbo_res(), "kbo", S)
    total = d["lam"].home + d["lam"].away
    assert 9.0 < total < 11.5, f"KBO λ 합계가 리그 득점 환경(약 10.2)과 어긋난다: {total:.2f}"
    mlb = game_distribution(
        {**_kbo_jg(), "sport": "mlb"},
        {k: v for k, v in _kbo_res().items() if k != "league_baselines"}, "mlb", S)
    assert (mlb["lam"].home + mlb["lam"].away) < total, "KBO가 MLB보다 낮게 나왔다"


def test_kbo_offense_baseline_from_league_not_mlb_constant():
    """[§8-14] 타선 계수 분모는 **그 리그 평균**이다.

    KBO 리그 OBP는 0.348 수준인데 MLB 상수(0.318)로 나누면 평균 타선인 팀이
    ×1.14를 받아 λ가 통째로 부풀어 오른다(실측: LG λ 5.76 → 수정 후 5.17).
    """
    with_base = game_distribution(_kbo_jg(), _kbo_res(), "kbo", S)
    without = game_distribution(
        _kbo_jg(), {k: v for k, v in _kbo_res().items() if k != "league_baselines"},
        "kbo", S)
    assert with_base["lam"].home < without["lam"].home, (
        "리그 평균을 넣었는데 λ가 줄지 않았다 — _baseline이 무시되고 있다")
    assert any("양 팀 평균" in t for t in with_base["lam"].trace)


def test_kbo_dispersion_is_poisson_until_measured():
    """KBO 과분산은 측정한 적이 없다 — 야구라는 이유로 MLB의 3.3을 빌려오지 않는다."""
    from app.engine.scoring import dispersion_for

    assert dispersion_for("kbo", S) is None
    assert dispersion_for("npb", S) is None
    assert dispersion_for("mlb", S) == pytest.approx(3.3)


def test_npb_needs_material_like_everyone_else():
    """[§8-20] NPB도 재료가 있으면 λ를 낸다 — 없으면 안 낸다.

    한때 "NPB는 지표 소스가 없으니 λ를 만들지 않는다"고 하드코딩했다.
    Yahoo!スポーツ 크롤링으로 선발 지표가 생겼으므로 그 예외는 사라졌다.
    남은 규율은 종목 무관하게 동일하다 — **재료 없으면 분석 생성 금지.**
    """
    have = {"home_pitcher": {"era_season": 2.15}, "away_pitcher": {"era_season": 2.15}}
    assert game_distribution(_npb_jg(), have, "npb", S) is not None
    assert game_distribution(_npb_jg(), {}, "npb", S) is None

def test_kbo_prob_bounds_are_baseball():
    """무승부가 없으므로 축구의 비대칭 하한을 쓰면 안 된다."""
    from app.engine.scoring import prob_bounds

    assert prob_bounds("kbo", S) == prob_bounds("mlb", S)
    assert prob_bounds("npb", S) == prob_bounds("mlb", S)


# ---------------------------------------------------------------- [§8-20] NPB

def _npb_jg():
    return {"game_id": 1, "home": "Tokyo Yakult Swallows", "away": "Yomiuri Giants",
            "league": "NPB", "sport": "npb", "alt_markets": [], "best_odds": {}}


def test_npb_uses_baseball_markets():
    """[§8-20] NPB도 야구다 — 무승부 행이 없고 승패 합이 1이어야 한다.

    실사고(2026-08-26): `is_baseball = sport in ("mlb", "kbo")`에 **NPB를 빠뜨려**
    축구 함수로 갔다. h2h에 draw 0.1634가 생기고 홈 승률이 51.4% → 43.3%로
    뒤집혔다. KBO에서 같은 사고를 겪고도 NPB λ를 켜면서 목록을 갱신하지 않았다.
    """
    res = {"home_pitcher": {"era_season": 2.15}, "away_pitcher": {"era_season": 2.15}}
    d = game_distribution(_npb_jg(), res, "npb", S)
    assert d is not None
    h = d["probs"]["h2h"]
    assert "draw" not in h, "야구에 무승부 행이 생겼다"
    assert abs(h["home"] + h["away"] - 1.0) < 0.01
    assert h["home"] > 0.5, "λ가 홈이 높은데 홈 승률이 5할 미만이다"


def test_npb_total_lines_match_run_environment():
    """NPB는 팀당 3.61점 리그다 — 토탈 라인이 MLB(8~9점)로 나오면 안 된다."""
    res = {"home_pitcher": {"era_season": 3.34}, "away_pitcher": {"era_season": 3.34}}
    d = game_distribution(_npb_jg(), res, "npb", S)
    lines = list((d["probs"].get("totals") or {}).keys())
    assert lines and max(lines) <= 9.0, f"NPB 토탈 라인이 너무 높다: {lines}"
    total = d["lam"].home + d["lam"].away
    assert 6.0 < total < 8.5, f"NPB λ 합계가 리그 득점 환경(7.22)과 어긋난다: {total:.2f}"


def test_baseball_sports_is_single_source_of_truth():
    """[§8-20] 종목 분기가 여러 곳에 흩어져 있으면 **한 곳만 고치고 나머지를 놓친다.**

    실제로 그 사고를 두 번 냈다(KBO 마켓확률, NPB is_baseball).
    → `BASEBALL_SPORTS` 한 곳에서만 정의하고 전부 그것을 참조한다.
    """
    import re
    from pathlib import Path

    from app.engine.scoring import BASEBALL_SPORTS

    assert set(BASEBALL_SPORTS) == {"mlb", "kbo", "npb"}
    for path in ("app/engine/scoring.py", "app/engine/markets.py"):
        src = Path(path).read_text(encoding="utf-8")
        # 하드코딩된 종목 튜플이 남아 있으면 다음 종목 추가 때 또 샌다
        leaked = re.findall(r'sport in \("mlb",\s*"kbo"', src)
        assert not leaked, f"{path}에 하드코딩된 야구 목록이 남아 있다"


def test_npb_league_constants_differ_from_kbo():
    """[§8-20] NPB는 팀당 3.61점 — KBO(5.09)보다 1.5점 낮다.

    야구라고 KBO 값을 빌려오면 λ가 통째로 틀린다(실측: npb.jp 공식 12팀).
    """
    from app.engine.scoring import league_baseline_runs

    assert league_baseline_runs("npb", S) == pytest.approx(3.61, abs=0.01)
    assert league_baseline_runs("kbo", S) > league_baseline_runs("npb", S) + 1.0
