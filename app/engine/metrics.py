"""오프라인 모델 평가용 Brier·캘리브레이션. 라이브 픽 채점기가 아니다."""

CALIBRATION_BANDS = ((0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 1.01))


def brier_score(rows) -> float | None:
    """Brier = mean((예측확률 - 실제결과)^2). 낮을수록 좋다. 항상 0.5면 0.25."""
    vals = []
    for r in rows:
        p, res = r.get("model_p"), r.get("result")
        if p is None or res not in ("win", "loss"):
            continue
        vals.append((float(p) - (1.0 if res == "win" else 0.0)) ** 2)
    return round(sum(vals) / len(vals), 4) if vals else None


def calibration_bands(rows) -> list[dict]:
    """예측 확률 구간별 실제 승률."""
    buckets: dict[tuple, list] = {b: [] for b in CALIBRATION_BANDS}
    for r in rows:
        p, res = r.get("model_p"), r.get("result")
        if p is None or res not in ("win", "loss"):
            continue
        p = float(p)
        for lo, hi in CALIBRATION_BANDS:
            if lo <= p < hi:
                buckets[(lo, hi)].append(1 if res == "win" else 0)
                break
    out = []
    for (lo, hi), hits in buckets.items():
        if not hits:
            continue
        actual = sum(hits) / len(hits)
        out.append({
            "band": f"{lo:.0%}~{min(hi, 1.0):.0%}", "n": len(hits),
            "predicted": round((lo + min(hi, 1.0)) / 2, 3),
            "actual": round(actual, 3),
            "gap": round(actual - (lo + min(hi, 1.0)) / 2, 3),
        })
    return out
