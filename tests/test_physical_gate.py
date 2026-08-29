"""[§9 게이트 ①-파이썬] 수집기 경로의 물리 검사.

Go의 `internal/gate`는 크롤러 필드(선발 이름·라인업)만 본다. λ와 카드에 실제로
들어가는 수치(ERA·WHIP·OPS·순위)는 파이썬 수집기가 넣으며 무검증이었다 —
2026-08-27 측정에서 드러났다(오늘 90개 값 중 오염은 0이었으나 **검사가 없었다**).
"""

from app.engine.physical import LIMITS, check, screen


def test_impossible_era_is_rejected():
    """실사고: Yahoo에서 齋藤 響介 ERA 189.00을 그대로 받아 억제 계수가 무너졌다."""
    assert check("home_pitcher.era_season", 189.0) is not None
    assert check("home_pitcher.era_season", 4.82) is None


def test_plausible_but_high_values_pass():
    """반대 방향 — 13.50은 부진한 투수의 실제 값이다. 버리면 정상 데이터 손실이다."""
    assert check("away_pitcher.era_season", 13.5) is None
    assert check("home_offense.ops", 0.788) is None
    assert check("home_standing.rank", 10) is None
    assert check("home_standing.rank", 15) is None
    assert check("home_standing.rank", 16) is not None


def test_empty_and_unknown_fields_pass():
    assert check("home_pitcher.era_season", None) is None
    assert check("home_pitcher.pitch_mix", "FAST 141km") is None
    assert check("brand_new_metric", 99999) is None


def test_screen_removes_and_reports():
    """조용히 버리지 않는다 — 무엇을 왜 버렸는지 남아야 과잉도 측정할 수 있다."""
    research = {"home_pitcher": {"era_season": 189.0, "whip": 1.49, "name": "X"}}
    dropped = screen(research, ["home_pitcher.era_season", "home_pitcher.whip",
                                "home_pitcher.name"])
    assert [d[0] for d in dropped] == ["home_pitcher.era_season"]
    assert dropped[0][1] == 189.0 and "물리 범위" in dropped[0][2]
    assert "era_season" not in research["home_pitcher"]
    assert research["home_pitcher"]["whip"] == 1.49, "멀쩡한 값까지 지웠다"


def test_dropped_value_never_gets_a_provenance_stamp():
    """🔴 순서 규율 — 각인이 먼저면 범위 밖 값이 '단일 소스·사용 가능'으로 통과한다."""
    from app.pipeline import _absorb
    from app.engine.provenance import label_all

    research = {"home_pitcher": {"era_season": 189.0, "whip": 1.49}}
    _absorb(research, ["home_pitcher.era_season", "home_pitcher.whip"], "portal")
    labels = label_all(research)
    assert "home_pitcher.era_season" not in labels, "폐기된 값에 출처가 각인됐다"
    assert labels["home_pitcher.whip"].usable


def test_go_and_python_gates_cover_disjoint_fields():
    """두 언어에 같은 규칙을 복제하지 않는다 — 드리프트가 없어야 한다.

    Go는 크롤러 필드(이름·라인업·상태), 파이썬은 수집기 수치 필드를 본다.
    """
    go_only = {"home_pitcher", "away_pitcher", "lineup_home", "lineup_away",
               "stadium", "status", "starter_status"}
    assert not (go_only & set(LIMITS)), "두 게이트가 같은 필드를 검사한다 — 드리프트 위험"
