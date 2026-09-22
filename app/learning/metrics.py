"""[LE-1a / learning_engine_0922] 학습 지표 — **순수 함수만.**

🔴 **지표가 적중률이 아니다.** 지시문 §1:

> "지표는 Brier·로그손실·CLV·ROI. 적중률은 보고에 넣되 **결정 기준으로 쓰지
>  않는다.** 확신 등급은 보정 곡선이 단조가 될 때까지 카드·export 에서 뺀다."

이유는 실측이다(2026-09-22 · 운영 원장):
```
확신 상 68.1%(n=47) · 확신 하 57.7%(n=359) · 확신 중 53.2%(n=945)
                      ↑ '하'가 '중'보다 잘 맞는다 — 순서가 깨져 있다
```
적중률로 고르면 이런 것을 못 본다. 보정 곡선은 본다.

🔴 **DB·HTTP·LLM 을 부르지 않는다.** 입력은 dict 목록, 출력은 숫자·표다.
   그래야 손으로 계산한 픽스처와 대조할 수 있다(계약 `test_metrics_on_known_fixture`).

⚠️ **표본 하한의 원본은 `config/learning.yaml` 의 `learning.min_samples` 다.**
   여기에 숫자를 박지 않는다(사본 금지).
"""
from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

#: 결과 어휘. 🔴 `push`·`void` 는 **분모에서 빠진다** — 무승부를 손실로 세면
#  적중률과 ROI 가 동시에 거짓이 된다(`pick_ledger` 가 같은 규약을 쓴다).
WIN, LOSS, PUSH, VOID = "win", "loss", "push", "void"
SCORED = (WIN, LOSS)


def min_samples() -> int:
    """표본 하한. 🔴 원본은 `config/learning.yaml` 하나다.

    ⚠️ 폴백 30 은 **파일이 없을 때만** 쓰인다(그때 로더가 경고를 남긴다).
       여기 숫자를 보고 판단하지 마라 — 원본은 설정이다.
    """
    from app.learning import get as _cfg

    v = _cfg("learning.min_samples")
    return int(v) if v else 30


def deciles() -> int:
    """보정 곡선 분위 수. 원본은 `config/learning.yaml` 다."""
    from app.learning import get as _cfg

    v = _cfg("learning.calibration_deciles")
    return int(v) if v else 10


def _pairs(rows) -> list[tuple[float, int]]:
    """`(p_model, 결과 1/0)` 만 남긴다. 🔴 `push`·`void`·확률 없음은 버린다.

    ⚠️ **버린 것을 조용히 넘기지 않는다** — 호출부가 `dropped()` 로 센다.
    """
    out: list[tuple[float, int]] = []
    for r in rows or []:
        p, res = (r or {}).get("p_model"), (r or {}).get("result")
        if p is None or res not in SCORED:
            continue
        try:
            pf = float(p)
        except (TypeError, ValueError):
            continue
        if not (0.0 <= pf <= 1.0):
            # 🔴 확률이 아닌 값이 들어오면 **버린다.** 클립하지 않는다 —
            #    클립은 결함을 숨기고 Brier 를 좋아 보이게 만든다.
            logger.info("[learning] 확률 범위 밖 %r — 버린다", p)
            continue
        out.append((pf, 1 if res == WIN else 0))
    return out


def dropped(rows) -> int:
    """지표에서 빠진 행 수. 🔴 "조용한 0"을 막는다."""
    return len(list(rows or [])) - len(_pairs(rows))


def brier(rows) -> float | None:
    """Brier = mean((p − y)²). 낮을수록 좋다. **항상 0.5로 찍으면 0.25.**

    🔴 0.25 를 못 이기는 모델은 50% 고정보다 나쁘다 — 그 사실이 이 지표의 값어치다.
    """
    pr = _pairs(rows)
    return round(sum((p - y) ** 2 for p, y in pr) / len(pr), 4) if pr else None


def log_loss(rows, *, eps: float = 1e-9) -> float | None:
    """로그손실. 🔴 확신 있게 틀리는 것을 Brier 보다 무겁게 벌한다.

    ⚠️ 0·1 을 그대로 넣으면 무한이 된다 — `eps` 로만 막고 값은 **바꾸지 않는다**.
    """
    pr = _pairs(rows)
    if not pr:
        return None
    s = 0.0
    for p, y in pr:
        q = min(max(p, eps), 1.0 - eps)
        s += -(y * math.log(q) + (1 - y) * math.log(1.0 - q))
    return round(s / len(pr), 4)


def calibration_curve(rows, *, bins: int | None = None) -> list[dict]:
    """보정 곡선. 분위별 `{bin, lo, hi, n, mean_p, freq}`.

    🔴 **이것이 모델 선택 기준이다**(Walsh & Joshi 2024 · 지시문 §0-b).
       `mean_p` 와 `freq` 가 가까우면 보정된 것이고, 분위를 따라 `freq` 가
       **단조 증가**해야 확신 표시를 쓸 수 있다.
    ⚠️ 빈 분위는 목록에서 빼지 않는다 — 빠지면 "단조"가 거짓으로 보인다.
    """
    k = int(bins or deciles())
    pr = _pairs(rows)
    out: list[dict] = []
    for i in range(k):
        lo, hi = i / k, (i + 1) / k
        sel = [(p, y) for p, y in pr if (lo <= p < hi or (i == k - 1 and p == 1.0))]
        n = len(sel)
        out.append({
            "bin": i + 1, "lo": round(lo, 3), "hi": round(hi, 3), "n": n,
            "mean_p": round(sum(p for p, _ in sel) / n, 4) if n else None,
            "freq": round(sum(y for _, y in sel) / n, 4) if n else None,
        })
    return out


def is_monotone(curve, *, min_n: int | None = None) -> bool | None:
    """보정 곡선이 단조 증가인가. 🔴 아니면 확신 등급을 쓰지 않는다.

    ⚠️ 표본이 얇은 분위는 **판단하지 않는다** — 2건짜리 분위의 상하로
       "깨졌다"고 말하면 오탐이다. 남은 분위가 2개 미만이면 `None`.
    """
    floor = int(min_n if min_n is not None else min_samples())
    pts = [c["freq"] for c in (curve or [])
           if c.get("n", 0) >= floor and c.get("freq") is not None]
    if len(pts) < 2:
        return None
    return all(b >= a for a, b in zip(pts, pts[1:]))


def clv(row) -> float | None:
    """CLV = 종가 확률 − 결정 시점 확률. **우리가 고른 쪽 기준.**

    🔴 **부호 규약**: 종가가 **우리 쪽으로** 움직이면 양수다. 우리가 고른 쪽의
       확률이 올랐다 = 시장이 우리 방향으로 왔다 = 우리가 좋은 가격을 잡았다.
       지시문 §0-e: "수익 지표는 적중률이 아니라 CLV(종가 대비 가격)".
    ⚠️ 그래서 두 확률은 **같은 쪽 기준**이어야 한다. 홈 기준 확률을 원정 픽에
       그대로 쓰면 부호가 뒤집힌다 — 변환은 `decisions.py` 가 적재할 때 한다.
    """
    a = (row or {}).get("p_market_at_decision")
    b = (row or {}).get("p_close")
    if a is None or b is None:
        return None
    try:
        return round(float(b) - float(a), 4)
    except (TypeError, ValueError):
        return None


def roi_unit(row) -> float | None:
    """단위 스테이크 손익. 이기면 `배당 − 1`, 지면 `−1`, push·void 는 `0`.

    🔴 **금액이 아니다.** 1단위를 걸었다면 얼마가 되는지이고, 금액·비중은
       제안하지 않는다(절대 규칙 R6 · 지시문 §1).
    """
    res = (row or {}).get("result")
    if res in (PUSH, VOID):
        return 0.0
    if res not in SCORED:
        return None
    if res == LOSS:
        return -1.0
    price = (row or {}).get("price_at_decision")
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    return round(p - 1.0, 4) if p > 1.0 else None


def summarize(rows, *, bins: int | None = None) -> dict:
    """한 묶음의 지표 전부. 🔴 표본이 하한 미만이면 **숫자를 내지 않는다.**

    지시문 LE-1-3: "30건 미만 셀은 '표본 부족'으로만."
    ⚠️ `n` 과 `dropped` 는 하한 미만이어도 낸다 — 몇 건인지는 사실이다.
    """
    rows = list(rows or [])
    pr = _pairs(rows)
    floor = min_samples()
    out: dict = {"n": len(pr), "dropped": dropped(rows), "min_samples": floor}
    if len(pr) < floor:
        out["insufficient"] = True
        return out
    clvs = [c for c in (clv(r) for r in rows) if c is not None]
    rois = [v for v in (roi_unit(r) for r in rows) if v is not None]
    curve = calibration_curve(rows, bins=bins)
    out.update({
        "insufficient": False,
        "brier": brier(rows),
        "log_loss": log_loss(rows),
        # ⚠️ 적중률은 **보고용**이다. 결정 기준으로 쓰지 않는다(지시문 §1).
        "hit_rate": round(sum(y for _, y in pr) / len(pr), 4),
        "clv_mean": round(sum(clvs) / len(clvs), 4) if clvs else None,
        "clv_n": len(clvs),
        "clv_positive_rate": (round(sum(1 for c in clvs if c > 0) / len(clvs), 4)
                              if clvs else None),
        "roi_mean": round(sum(rois) / len(rois), 4) if rois else None,
        "roi_n": len(rois),
        "calibration": curve,
        "monotone": is_monotone(curve),
    })
    return out


def group_by(rows, keys) -> dict:
    """`keys` 조합별 `summarize`. 🔴 엔진을 섞지 않는다(지시문 LE-6-1).

    ⚠️ 키가 없는 행은 `None` 키로 **따로** 묶는다 — 조용히 합치면 어느 엔진의
       성적인지 알 수 없게 된다.
    """
    ks = tuple(keys if isinstance(keys, (list, tuple)) else (keys,))
    buckets: dict = {}
    for r in rows or []:
        buckets.setdefault(tuple((r or {}).get(k) for k in ks), []).append(r)
    return {k: summarize(v) for k, v in sorted(
        buckets.items(), key=lambda kv: tuple(str(x) for x in kv[0]))}
