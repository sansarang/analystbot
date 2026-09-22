"""[LE-4] 엔진 2 — 시초가 잔차 모델. **시장을 복사하면 0점이다.**

사용자 2026-09-22: "시장에 순응하면 안 되고 시장을 이기는 방법을 찾아야 한다."

🔴 **그래서 목표가 결과가 아니라 `p_close − p_open` 이다.**
```
보통 모델   목표 = 누가 이겼나       →  잘 맞히면 시장과 같아진다(둘 다 정답을 향한다)
이 모델     목표 = 시장의 이동량     →  **시장이 틀린 만큼**만 점수가 난다
```
시장 확률을 그대로 내놓으면 예측 이동량이 0 이고, 그건 아무 후보도 못 낸다.
구조상 복사가 불가능하다 — 벌점이 아니라 **목표 자체**다(사용자 결정).

🔴 **학습은 walk-forward 만.** `split.walk_forward` 밖의 경로가 없다.
⚠️ 모델은 sklearn `HistGradientBoostingRegressor` 다(사용자 결정).
   결측을 네이티브로 다루므로 0 으로 채우지 않는다.
⚠️ 검증 창 밖 성적은 보고하지 않는다. 좋아 보이는 설정을 찾아 헤매면 그건
   검증 창을 학습에 쓰는 것이다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

TARGET_RESIDUAL = "residual"     # y = p_close - p_open   ← 기본
TARGET_RESULT = "result"         # y = 홈 승(0/1)          ← 비교군


def _X(rows) -> list[list]:
    from app.learning.features_soccer import NAMES, build

    out = []
    for r in rows:
        f = build(r)
        out.append([None if f.get(n) is None else float(f[n]) for n in NAMES])
    return out


def _y(rows, target: str) -> list:
    """목표값. 🔴 `residual` 은 **시장의 이동량**이지 결과가 아니다."""
    out = []
    for r in rows:
        if target == TARGET_RESULT:
            out.append(1.0 if r.get("ftr") == "H" else 0.0)
        else:
            po, pc = r.get("p_open"), r.get("p_close")
            out.append(None if (po is None or pc is None) else float(pc) - float(po))
    return out


def _fit(rows, target: str):
    """모델 하나. 🔴 학습 행에 **목표가 없는 행은 빼고** 센다."""
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingRegressor

    X, y = _X(rows), _y(rows, target)
    keep = [i for i, v in enumerate(y) if v is not None]
    if len(keep) < 50:
        return None, len(keep)
    m = HistGradientBoostingRegressor(max_depth=3, max_iter=200,
                                      learning_rate=0.05, l2_regularization=1.0)
    m.fit(np.array([X[i] for i in keep], dtype=float),
          np.array([y[i] for i in keep], dtype=float))
    return m, len(keep)


def _predict(m, rows, target: str) -> list:
    """예측 확률(홈). 🔴 잔차 목표면 **`p_open` 에 더한다** — 그 자체가
    "시장에서 얼마나 떨어질 것인가"다."""
    import numpy as np

    if m is None:
        return [None] * len(rows)
    raw = m.predict(np.array(_X(rows), dtype=float))
    out = []
    for r, d in zip(rows, raw):
        if target == TARGET_RESULT:
            out.append(round(min(max(float(d), 0.0), 1.0), 4))
            continue
        po = r.get("p_open")
        out.append(None if po is None
                   else round(min(max(float(po) + float(d), 0.0), 1.0), 4))
    return out


def run(rows, *, target: str = TARGET_RESIDUAL, ts_key: str = "ts",
        train_weeks: int | None = None, valid_weeks: int | None = None) -> dict:
    """한 리그의 walk-forward. 반환: 검증 창에서 모은 예측 행 + 요약.

    흐름 — 창마다:
      학습 창으로 적합 → 검증 창 **앞부분**에서 보정을 맞추고 → **뒷부분**에서
      잰다(LE-2-3). 🔴 앞에서 맞추고 앞에서 재면 그건 학습 성적이다.
    """
    from app.learning import metrics as M
    from app.learning.calibrate import Calibrator
    from app.learning.split import calibration_halves, walk_forward

    scored: list[dict] = []
    windows = walk_forward(rows, ts_key=ts_key, train_weeks=train_weeks,
                           valid_weeks=valid_weeks, min_train=50)
    for w in windows:
        tr, va = w.split(rows, ts_key=ts_key)
        m, n_tr = _fit(tr, target)
        if m is None:
            continue
        cal_rows, test_rows = calibration_halves(va, ts_key=ts_key)
        # 보정은 **결과**로 맞춘다 — 확률을 확률답게 만드는 일이다
        cp = _predict(m, cal_rows, target)
        cy = [1 if r.get("ftr") == "H" else 0 for r in cal_rows]
        cal = Calibrator().fit(cp, cy)
        tp = cal.apply(_predict(m, test_rows, target))
        for r, p in zip(test_rows, tp):
            if p is None:
                continue
            scored.append({**r, "p_model": p, "n_train": n_tr,
                           "calibrated": cal.fitted})
    return {"rows": scored, "windows": len(windows),
            "summary": M.summarize(scored)}


def candidates(scored, *, min_edge: float | None = None) -> list[dict]:
    """후보 규칙 — `p_model − p_market ≥ min_edge`.

    🔴 지시문 LE-4-5: "**방향이 시장 우세팀과 달라도 낸다**"(역행 허용).
    ⚠️ 문턱의 원본은 `config/learning.yaml` 의 `learning.residual.min_edge` 다.
    """
    from app.learning import get as cfg

    thr = float(min_edge if min_edge is not None
                else (cfg("learning.residual.min_edge") or 0.04))
    out = []
    for r in scored or []:
        pm, pmk = r.get("p_model"), r.get("p_market")
        if pm is None or pmk is None:
            continue
        edge = float(pm) - float(pmk)
        if abs(edge) >= thr:
            out.append({**r, "edge": round(edge, 4),
                        "side": "home" if edge > 0 else "away"})
    return out
