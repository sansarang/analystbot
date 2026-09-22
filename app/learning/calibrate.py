"""[LE-2] 확률 보정 — isotonic(기본) · platt(선택).

지시문 LE-2-3: "`isotonic` 을 기본, `platt` 선택. 보정은 **검증 창의 앞부분에서만
맞추고 뒤에서 잰다**."

🔴 **왜 보정인가.** 모델 선택 기준은 적중률이 아니라 **보정**이다
   (Walsh & Joshi 2024 · 지시문 §0-b). 0.65 라고 말한 것들이 실제로 65% 나와야
   그 확률을 값으로 쓸 수 있다.

⚠️ 표본이 얇으면 isotonic 은 **계단을 과적합**한다. 하한 미만이면 보정하지
   않고 **원값을 그대로 돌려준다** — 억지로 보정한 값은 더 나쁘다.
⚠️ sklearn 은 여기(보정)에만 쓴다. 모델은 LE-4 다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

ISOTONIC, PLATT = "isotonic", "platt"


class Calibrator:
    """`fit(p, y)` 뒤 `apply(p)`. 🔴 **맞춘 적이 없으면 원값을 돌려준다.**"""

    def __init__(self, method: str = ISOTONIC):
        self.method = method if method in (ISOTONIC, PLATT) else ISOTONIC
        self._m = None
        self.n = 0
        self.reason: str | None = None

    def fit(self, ps, ys) -> "Calibrator":
        from app.learning.metrics import min_samples

        pairs = [(float(p), int(y)) for p, y in zip(ps or [], ys or [])
                 if p is not None and y in (0, 1) and 0.0 <= float(p) <= 1.0]
        self.n = len(pairs)
        floor = min_samples()
        if self.n < floor:
            self.reason = f"표본 부족 {self.n} < {floor}"
            logger.info("[calib] %s — 보정하지 않는다", self.reason)
            return self
        if len({y for _, y in pairs}) < 2:
            # 🔴 한쪽 결과만 있으면 보정은 상수 함수가 된다 — 그건 보정이 아니다.
            self.reason = "결과가 한쪽뿐"
            return self
        try:
            if self.method == PLATT:
                from sklearn.linear_model import LogisticRegression

                m = LogisticRegression()
                m.fit([[p] for p, _ in pairs], [v for _, v in pairs])
                self._m = ("platt", m)
            else:
                from sklearn.isotonic import IsotonicRegression

                m = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
                m.fit([p for p, _ in pairs], [v for _, v in pairs])
                self._m = ("iso", m)
        except Exception as exc:                            # pragma: no cover
            self.reason = f"적합 실패: {exc}"
            logger.warning("[calib] %s", self.reason)
        return self

    def apply(self, ps) -> list:
        """보정된 확률. ⚠️ 못 맞췄으면 **원값 그대로**(조용한 변형 금지)."""
        vals = [None if p is None else float(p) for p in (ps or [])]
        if self._m is None:
            return vals
        kind, m = self._m
        out = []
        for p in vals:
            if p is None:
                out.append(None)
                continue
            try:
                q = (m.predict_proba([[p]])[0][1] if kind == "platt"
                     else float(m.predict([p])[0]))
            except Exception:                               # pragma: no cover
                q = p
            out.append(round(min(max(float(q), 0.0), 1.0), 4))
        return out

    @property
    def fitted(self) -> bool:
        return self._m is not None
