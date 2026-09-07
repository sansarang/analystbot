"""자료13 전개 계산기 백테스트의 계약.

이 계산기는 **아직 판정에 주입되지 않았다**(관문 미통과, 2026-09-07 실측).
그래도 테스트를 붙이는 이유는 관문 자체가 이 산수 위에 서 있기 때문이다 —
교차 배선이 뒤집히면 모든 지표가 그럴듯하게 나오면서 방향만 반대가 된다.
"""

import pytest

from tools.backtest_tempo import (INNINGS, _shrunk, build_sides,
                                  expected_runs, score, score_totals,
                                  tempo)


def test_선발이_길게_던지면_불펜_이닝이_줄어든다():
    """9이닝을 선발/불펜으로 나눠 쓴다 — 두 축의 이닝 합이 9다."""
    좋은선발 = expected_runs(sp_ip_p50=7.0, sp_r_per_ip=0.3,
                             bp_r_per_ip=1.0, off_mult=1.0)
    짧은선발 = expected_runs(sp_ip_p50=3.0, sp_r_per_ip=0.3,
                             bp_r_per_ip=1.0, off_mult=1.0)
    assert 좋은선발 == pytest.approx(7 * 0.3 + 2 * 1.0)
    assert 짧은선발 == pytest.approx(3 * 0.3 + 6 * 1.0)
    assert 짧은선발 > 좋은선발


def test_선발_이닝은_9를_넘지_않는다():
    """연장 이닝을 예측하지 않는다 — p50 이 9를 넘어도 잘린다."""
    assert expected_runs(sp_ip_p50=12.0, sp_r_per_ip=0.5, bp_r_per_ip=9.9,
                         off_mult=1.0) == pytest.approx(INNINGS * 0.5)


def test_타선_배율은_곱으로_들어간다():
    기준 = expected_runs(sp_ip_p50=5.0, sp_r_per_ip=0.5,
                         bp_r_per_ip=0.5, off_mult=1.0)
    두배 = expected_runs(sp_ip_p50=5.0, sp_r_per_ip=0.5,
                         bp_r_per_ip=0.5, off_mult=2.0)
    assert 두배 == pytest.approx(기준 * 2)


def test_교차_배선_홈득점은_원정_투수진에서_나온다():
    """🔴 부호 뒤집힘 방지. 홈 블록은 **원정** 선발·불펜을 받아야 한다."""
    home_sp = {"p50": 7.0, "r_per_ip": 0.1}     # 홈 선발이 압도적
    away_sp = {"p50": 2.0, "r_per_ip": 2.0}     # 원정 선발이 형편없다
    hside, aside = build_sides(home_sp=home_sp, away_sp=away_sp,
                               home_bp=0.1, away_bp=2.0,
                               home_off=1.0, away_off=1.0)
    assert hside["sp_ip_p50"] == 2.0 and hside["sp_r_per_ip"] == 2.0
    assert hside["bp_r_per_ip"] == 2.0
    assert aside["sp_ip_p50"] == 7.0 and aside["bp_r_per_ip"] == 0.1
    # 원정 투수진이 나쁘므로 우위는 홈이어야 한다.
    assert tempo(home=hside, away=aside)["우위"] == "홈"


def test_타선_배율은_자기_팀_것이다():
    prof = {"p50": 5.0, "r_per_ip": 0.5}
    hside, aside = build_sides(home_sp=prof, away_sp=prof, home_bp=0.5,
                               away_bp=0.5, home_off=2.0, away_off=0.5)
    assert hside["off_mult"] == 2.0 and aside["off_mult"] == 0.5
    assert tempo(home=hside, away=aside)["우위"] == "홈"


def test_페이로드는_팀당_값이고_집계표가_아니다():
    prof = {"p50": 5.0, "r_per_ip": 0.5}
    out = tempo(*build_sides(home_sp=prof, away_sp=prof, home_bp=0.5,
                             away_bp=0.5, home_off=1.0, away_off=1.0))
    assert set(out) == {"홈", "원정", "우위", "격차", "합계"}
    assert set(out["홈"]) == {"기대득점"}
    assert out["우위"] == "동률" and out["격차"] == 0.0


def test_수축은_표본이_얇을수록_리그평균에_가깝다():
    """가상 이닝 k 를 리그평균 성적으로 얹는다. k=0 이면 원래 비율."""
    assert _shrunk(6.0, 2.0, 0.6, 0.0) == pytest.approx(3.0)   # 수축 없음
    얇음 = _shrunk(6.0, 2.0, 0.6, 20.0)     # 2이닝 표본
    두터움 = _shrunk(60.0, 20.0, 0.6, 20.0)  # 같은 비율, 20이닝 표본
    assert 얇음 < 두터움 < 3.0
    assert abs(얇음 - 0.6) < abs(두터움 - 0.6)


def test_채점은_무승부를_방향에서_뺀다():
    """무승부에는 우열이 없다 — 분모에 넣으면 일치율이 조용히 깎인다."""
    rows = [
        {"e_home": 5, "e_away": 3, "a_home": 6, "a_away": 2,
         "pred_margin": 2.0, "actual_margin": 4.0},      # 방향 적중
        {"e_home": 5, "e_away": 3, "a_home": 4, "a_away": 4,
         "pred_margin": 2.0, "actual_margin": 0.0},      # 무승부 → 제외
    ]
    m = score(rows)
    assert m["n"] == 2 and m["판정가능"] == 1 and m["무승부"] == 1
    assert m["일치율"] == pytest.approx(1.0)


def test_예측_동률은_적중으로_치지_않는다():
    rows = [{"e_home": 4, "e_away": 4, "a_home": 5, "a_away": 1,
             "pred_margin": 0.0, "actual_margin": 4.0}]
    assert score(rows)["일치율"] == pytest.approx(0.0)


# ─────────────────────────────────────── 총득점 관문 (2026-09-07 선언)

def _row(pred, actual, line, league=None):
    return {"pred_total": pred, "actual_total": actual, "line": line,
            "league_total": league if league is not None else line,
            "line_src": "리그평균"}


def test_총득점_푸시는_방향_분모에서_빠진다():
    """실제 총득점이 선과 같으면 오버도 언더도 아니다."""
    m = score_totals([_row(11.0, 12.0, 9.5), _row(11.0, 9.5, 9.5)])
    assert m["n"] == 2 and m["판정가능"] == 1 and m["푸시"] == 1
    assert m["일치율"] == pytest.approx(1.0)


def test_예측이_선과_같으면_미적중이다():
    """우리와 기준선에 같은 자를 댄다 — 동률을 적중으로 세지 않는다."""
    assert score_totals([_row(9.5, 12.0, 9.5)])["일치율"] == pytest.approx(0.0)


def test_기준선_오버_언더는_실제_분포에서_나온다():
    rows = [_row(20.0, 12.0, 9.5), _row(20.0, 8.0, 9.5), _row(20.0, 7.0, 9.5)]
    m = score_totals(rows)
    assert m["기준_항상오버"] == pytest.approx(1 / 3)
    assert m["기준_항상언더"] == pytest.approx(2 / 3)
    assert m["일치율"] == pytest.approx(1 / 3)      # 항상 오버라 찍은 셈


def test_리그평균선_기준선이_선과_같으면_구조적_미적중으로_샌다():
    """폴백 구간의 알려진 한계 — 숨기지 말고 건수로 드러낸다."""
    m = score_totals([_row(20.0, 12.0, 9.5, league=9.5)])
    assert m["기준_리그평균선"] == pytest.approx(0.0)
    assert m["리그평균선_무의미"] == 1


def test_관문_두_조건은_따로_판정된다():
    """(a) 하한이 세 기준선 초과 · (b) MAE 개선 — 하나만 맞으면 미달."""
    # 예측이 실제와 정확히 같아 (a)·(b) 모두 통과하는 표본
    rows = [_row(12.0, 12.0, 9.5, league=20.0) for _ in range(60)]
    rows += [_row(7.0, 7.0, 9.5, league=20.0) for _ in range(40)]
    m = score_totals(rows)
    assert m["일치율"] == pytest.approx(1.0)
    assert m["a_통과"] and m["b_통과"]
    # 예측만 뒤집으면 (a) 가 무너진다
    bad = [_row(7.0, 12.0, 9.5, league=20.0) for _ in range(60)]
    bad += [_row(12.0, 7.0, 9.5, league=20.0) for _ in range(40)]
    assert score_totals(bad)["a_통과"] is False


def test_wilson_하한은_표본이_적을수록_낮다():
    from tools.backtest_tempo import wilson

    _, lo_적음, _ = wilson(4, 5)
    _, lo_많음, _ = wilson(80, 100)
    assert lo_적음 < lo_많음
