"""[§6-1] 피처 → λ 매핑 학습 — 포아송 회귀(log-link).

예측 대상은 **팀별 득점**이다. 학습된 λ에서 기존과 동일하게 포아송 분포로
승패·런라인·언더오버·F5를 산출하므로 **마켓 확률의 출처는 여전히 하나**다.

과적합 방지(§6-3):
- L2 정규화(alpha)를 반드시 건다.
- 시간순 교차검증으로 alpha를 고른다 — 무작위 분할은 미래로 과거를 맞히는 셈이다.
- 학습셋이 작으면 학습 자체를 거부한다.

기존 임의 계수 모델은 병렬 채점용으로 남긴다(app/engine/scoring.py).
"""

import json
import logging
import pathlib

logger = logging.getLogger(__name__)

ARTIFACT = pathlib.Path("data/lambda_poisson.json")
MIN_RECORDS = 1000
ALPHA_GRID = (0.01, 0.1, 0.5, 1.0, 3.0, 10.0)


def fit_poisson(X_train, y_train, alpha: float):
    from sklearn.linear_model import PoissonRegressor

    model = PoissonRegressor(alpha=alpha, max_iter=2000, tol=1e-7)
    model.fit(X_train, y_train)
    return model


def poisson_deviance(model, X, y) -> float:
    """포아송 이탈도 — 득점 예측의 적합도. 낮을수록 좋다."""
    import numpy as np

    pred = np.clip(model.predict(X), 1e-6, None)
    with np.errstate(divide="ignore", invalid="ignore"):
        term = np.where(y > 0, y * np.log(y / pred), 0.0)
    return float(2.0 * np.mean(term - (y - pred)))


def choose_alpha(X, y, folds: int = 4) -> tuple[float, list[dict]]:
    """[§6-3] 시간순 교차검증으로 정규화 강도 결정.

    데이터는 이미 시간순으로 정렬돼 있어야 한다 — 앞쪽으로 학습해 뒤쪽을 검증한다.
    """
    import numpy as np

    n = len(y)
    trace = []
    best, best_dev = ALPHA_GRID[0], float("inf")
    for alpha in ALPHA_GRID:
        devs = []
        for k in range(1, folds + 1):
            cut = int(n * (0.4 + 0.15 * (k - 1)))
            end = int(n * (0.4 + 0.15 * k))
            if end - cut < 50 or cut < 200:
                continue
            model = fit_poisson(X[:cut], y[:cut], alpha)
            devs.append(poisson_deviance(model, X[cut:end], y[cut:end]))
        if not devs:
            continue
        mean_dev = float(np.mean(devs))
        trace.append({"alpha": alpha, "cv_deviance": round(mean_dev, 5)})
        if mean_dev < best_dev:
            best, best_dev = alpha, mean_dev
    return best, trace


def permutation_importance(model, X, y, feature_names, repeats: int = 5) -> list[dict]:
    """[§6-5] 피처 중요도 — 값을 섞었을 때 이탈도가 얼마나 나빠지는가.

    기여도가 0에 가까운 피처는 제거 대상이다.
    """
    import numpy as np

    rng = np.random.default_rng(0)
    base = poisson_deviance(model, X, y)
    out = []
    for j, name in enumerate(feature_names):
        drops = []
        for _ in range(repeats):
            Xp = X.copy()
            rng.shuffle(Xp[:, j])
            drops.append(poisson_deviance(model, Xp, y) - base)
        out.append({"feature": name, "importance": round(float(np.mean(drops)), 5)})
    out.sort(key=lambda r: r["importance"], reverse=True)
    return out


def game_probabilities(model, records: list[dict], X) -> list[dict]:
    """팀-경기 λ 예측 → 경기 단위 승패 확률 (포아송 결합).

    반환: [{game_pk, p_home, home_win, lam_home, lam_away}]
    """
    import numpy as np

    from app.config import get_settings
    from app.engine.scoring import cap_probability, mlb_market_probs

    s = get_settings()
    lam = np.clip(model.predict(X), s.lam_min, s.lam_max)
    by_game: dict[int, dict] = {}
    for rec, value in zip(records, lam):
        slot = by_game.setdefault(rec["game_pk"], {})
        side = "home" if rec.get("is_home") else "away"
        slot[side] = float(value)
        slot[f"{side}_runs"] = rec["runs"]
    out = []
    for gp, slot in by_game.items():
        if "home" not in slot or "away" not in slot:
            continue
        probs = mlb_market_probs(slot["home"], slot["away"], settings=s)
        p_home, _note = cap_probability(probs["h2h"]["home"], "mlb", s)
        out.append({
            "game_pk": gp, "p_home": round(p_home, 4),
            "home_win": 1 if slot["home_runs"] > slot["away_runs"] else 0,
            "lam_home": round(slot["home"], 3), "lam_away": round(slot["away"], 3),
            "total_runs": float(slot["home_runs"] + slot["away_runs"]),
        })
    return out


TOTAL_LINES = (7.5, 8.5, 9.5)


def evaluate_totals(games: list[dict], lines=TOTAL_LINES) -> dict:
    """[§6] 토탈(언더오버) 예측을 승패와 **분리해** 평가한다.

    파크팩터는 양 팀 λ를 함께 올리므로 승패 확률을 거의 바꾸지 않는다(절제 실험에서
    확인). 반면 총득점은 직접 움직이므로 토탈 마켓에서는 유효할 수 있다 — 그 가설을
    여기서 검증한다.

    시장 라인의 과거 데이터가 없으므로 대표 라인 몇 개로 평가한다.
    """
    from app.config import get_settings
    from app.engine.scoring import mlb_market_probs
    from app.engine.metrics import brier_score, calibration_bands

    s = get_settings()
    out: dict = {"lines": {}}
    all_rows = []
    for line in lines:
        rows = []
        for g in games:
            if g.get("total_runs") is None:
                continue
            probs = mlb_market_probs(g["lam_home"], g["lam_away"],
                                     lines={"totals": [line]}, settings=s)
            block = probs["totals"].get(line)
            if not block:
                continue
            rows.append({"model_p": block["Over"],
                         "result": "win" if g["total_runs"] > line else "loss"})
        if not rows:
            continue
        hits = sum(1 for r in rows
                   if (r["model_p"] >= 0.5) == (r["result"] == "win"))
        out["lines"][line] = {
            "n": len(rows),
            "accuracy": round(hits / len(rows), 4),
            "brier": brier_score(rows),
            "over_rate_actual": round(
                sum(1 for r in rows if r["result"] == "win") / len(rows), 4),
            "over_rate_predicted": round(
                sum(r["model_p"] for r in rows) / len(rows), 4),
        }
        all_rows += rows
    if all_rows:
        hits = sum(1 for r in all_rows
                   if (r["model_p"] >= 0.5) == (r["result"] == "win"))
        out["overall"] = {
            "n": len(all_rows),
            "accuracy": round(hits / len(all_rows), 4),
            "brier": brier_score(all_rows),
            "calibration": calibration_bands(all_rows),
        }
    return out


def evaluate_games(games: list[dict]) -> dict:
    """[§6-5] 승패 정확도·Brier·캘리브레이션·확률 분포."""
    from app.engine.metrics import brier_score, calibration_bands

    rows = [{"model_p": g["p_home"], "result": "win" if g["home_win"] else "loss"}
            for g in games]
    if not rows:
        return {"n": 0}
    hits = sum(1 for r in rows if (r["model_p"] >= 0.5) == (r["result"] == "win"))
    probs = sorted(r["model_p"] for r in rows)
    return {
        "n": len(rows),
        "accuracy": round(hits / len(rows), 4),
        "brier": brier_score(rows),
        "calibration": calibration_bands(rows),
        "p_max": probs[-1], "p_p95": probs[int(len(probs) * 0.95)],
        "share_over_55": round(sum(1 for p in probs if p >= 0.55) / len(probs), 4),
        "share_over_58": round(sum(1 for p in probs if p >= 0.58) / len(probs), 4),
    }


def train(records: list[dict]) -> dict:
    """[§6] 전체 학습 절차 — 시간순 분할, 정규화 선택, 평가, 중요도."""
    from app.models.features import FEATURES, time_split, to_matrix

    if len(records) < MIN_RECORDS:
        return {"ok": False, "reason": f"레코드 {len(records)} < 최소 {MIN_RECORDS}"}

    train_recs, test_recs = time_split(records)
    X_tr, y_tr = to_matrix(train_recs)
    X_te, y_te = to_matrix(test_recs)

    alpha, cv_trace = choose_alpha(X_tr, y_tr)
    model = fit_poisson(X_tr, y_tr, alpha)

    result = {
        "ok": True,
        "n_train": len(train_recs), "n_test": len(test_recs),
        "alpha": alpha, "cv": cv_trace,
        "deviance_train": round(poisson_deviance(model, X_tr, y_tr), 5),
        "deviance_test": round(poisson_deviance(model, X_te, y_te), 5),
        "importance": permutation_importance(model, X_te, y_te, FEATURES),
        "coefficients": {f: round(float(c), 5)
                         for f, c in zip(FEATURES, model.coef_)},
        "intercept": round(float(model.intercept_), 5),
        "test": evaluate_games(game_probabilities(model, test_recs, X_te)),
        "train_fit": evaluate_games(game_probabilities(model, train_recs, X_tr)),
        "train_period": (str(train_recs[0]["date"]), str(train_recs[-1]["date"])),
        "test_period": (str(test_recs[0]["date"]), str(test_recs[-1]["date"])),
    }
    result["drop_candidates"] = [
        r["feature"] for r in result["importance"] if abs(r["importance"]) < 1e-4]
    return result


def save(result: dict, path: pathlib.Path = ARTIFACT) -> None:
    if not result.get("ok"):
        logger.warning("[lambda_model] 학습 실패 — 저장하지 않음: %s", result.get("reason"))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    logger.info("[lambda_model] 저장 %s — test Brier %s / 정확도 %s",
                path, result["test"].get("brier"), result["test"].get("accuracy"))


# ---------------------------------------------------------------- 실전 적용 (병렬 채점용)

_CACHE: dict = {}


def load_artifact(path: pathlib.Path = ARTIFACT) -> dict | None:
    """학습 결과(계수·절편)를 읽어 캐시. 없으면 None."""
    key = str(path)
    if key in _CACHE:
        return _CACHE[key]
    if not path.exists():
        _CACHE[key] = None
        return None
    try:
        data = json.loads(path.read_text())
        art = {"coefficients": data.get("coefficients"),
               "intercept": data.get("intercept"),
               "test": data.get("test", {})}
        _CACHE[key] = art if art["coefficients"] else None
    except (ValueError, OSError):
        _CACHE[key] = None
    return _CACHE[key]


def predict_game(jg: dict, research: dict, settings=None) -> dict | None:
    """[§6-4] 학습 계수로 이 경기의 승패 확률을 계산한다 (병렬 채점 기록용).

    실전 피처는 학습 피처보다 얇을 수 있다 — 없는 값은 계수를 적용하지 않는다
    (0으로 채우면 절편만 남아 리그 평균이 나오는 편이 정직하다).
    """
    import math

    from app.config import get_settings
    from app.engine.scoring import cap_probability, mlb_market_probs

    art = load_artifact()
    if not art:
        return None
    s = settings or get_settings()
    coef, b0 = art["coefficients"], art["intercept"]

    lam = {}
    for side, opp in (("home", "away"), ("away", "home")):
        feats = _live_features(jg, research, side, opp)
        z = b0 + sum(coef.get(k, 0.0) * v for k, v in feats.items())
        lam[side] = max(s.lam_min, min(s.lam_max, math.exp(z)))
    probs = mlb_market_probs(lam["home"], lam["away"], settings=s)
    p_home, _ = cap_probability(probs["h2h"]["home"], "mlb", s)
    return {jg["home"]: round(p_home, 4), jg["away"]: round(1 - p_home, 4)}


def _live_features(jg: dict, research: dict, side: str, opp: str) -> dict:
    """실전 리서치/Statcast 페이로드 → 학습 피처 이름으로 매핑 (있는 것만)."""
    off = research.get(f"{side}_offense") or {}
    sp = research.get(f"{opp}_pitcher") or {}
    bp = research.get(f"{opp}_bullpen") or {}
    out: dict[str, float] = {"is_home": 1.0 if side == "home" else 0.0}
    for key, src, name in (
        ("off_xwoba", off, "xwoba_30d"), ("off_k_pct", off, "k_pct"),
        ("off_bb_pct", off, "bb_pct"),
        ("sp_xwoba_allowed", sp, "xwoba_allowed"), ("sp_velo", sp, "velo_window"),
        ("bp_xwoba_allowed", bp, "xwoba_allowed"), ("bp_pitches_3d", bp, "ip_last3d"),
    ):
        val = src.get(name)
        if val is not None:
            out[key] = float(val)
    if research.get("park_factor") is not None:
        out["park_factor"] = float(research["park_factor"])
    return out
