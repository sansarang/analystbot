"""오프라인 모델 평가용 Brier·캘리브레이션."""


def test_brier_score_rewards_calibration():
    from app.engine.metrics import brier_score

    confident_right = brier_score([{"model_p": 0.90, "result": "win"}] * 4)
    coin_flip = brier_score([{"model_p": 0.50, "result": "win"}] * 4)
    confident_wrong = brier_score([{"model_p": 0.90, "result": "loss"}] * 4)
    assert confident_right < coin_flip < confident_wrong
    assert coin_flip == 0.25
    assert brier_score([]) is None
    assert brier_score([{"model_p": 0.6, "result": None},
                        {"model_p": 0.6, "result": "push"}]) is None


def test_calibration_bands_report_actual_vs_predicted():
    from app.engine.metrics import calibration_bands

    rows = ([{"model_p": 0.62, "result": "win"}] * 6
            + [{"model_p": 0.62, "result": "loss"}] * 4
            + [{"model_p": 0.72, "result": "loss"}] * 2)
    bands = {b["band"]: b for b in calibration_bands(rows)}
    b60 = bands["60%~65%"]
    assert b60["n"] == 10 and b60["actual"] == 0.6
    assert abs(b60["gap"]) < 0.03
    b70 = bands["70%~100%"]
    assert b70["actual"] == 0.0 and b70["gap"] < -0.5


def test_calibration_skips_empty_bands():
    from app.engine.metrics import calibration_bands

    assert calibration_bands([]) == []
    bands = calibration_bands([{"model_p": 0.51, "result": "win"}])
    assert len(bands) == 1 and bands[0]["band"] == "50%~55%"
