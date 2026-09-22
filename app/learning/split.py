"""[LE-2] 시간순 검증 틀 — **누설을 구조로 막는다.**

지시문 §1:
> "학습·검증은 시간순(walk-forward)만. 무작위 분할·미래 정보 누설(종가·결과·
>  경기 후 기사)이 학습 입력에 들어가면 **그 결과는 무효다.**"

🔴 **검사가 아니라 구조로 막는 이유.** 검사 함수를 두면 그것을 안 부르는 경로가
   생긴다 — 이 저장소가 "만들어 놓고 안 이음"을 겪은 횟수가 그 증거다
   (D48 · D52 · WIR-3 · `source_types.py` 임포트 0건). 그래서 피처는
   **`(value, available_at)` 쌍으로만** 만들어진다. `available_at` 없이는
   피처 자체가 생성되지 않는다.

🔴 **미래 정보의 목록**(지시문): 종가 · 결과 · 경기 후 기사 · "현재" 순위
   (경기 후 갱신본). 이들은 `available_at` 이 결정 시각 이후이므로 자동으로 걸린다.

⚠️ **무작위 분할을 쓰지 않는다.** `train_test_split`·`shuffle`·`random_state`
   를 이 패키지에서 부르지 않는 것을 계약이 잠근다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


class LeakError(ValueError):
    """미래 정보가 학습 입력에 들어갔다. 🔴 **조용히 버리지 않는다** —
    누설은 결과를 무효로 만들므로 시끄럽게 터져야 한다."""


@dataclass(frozen=True)
class Feature:
    """피처 하나. 🔴 **`available_at` 없이는 만들 수 없다.**

    `available_at` 은 "이 값을 **알 수 있게 된 시각**"이다. 구조 카드는
    `fetched_at`, 배당 스냅샷은 `captured_at` 이다.
    ⚠️ 경기 시작 시각이 아니다 — 킥오프 3시간 전에 받은 라인업은 그때가
       `available_at` 이고, 킥오프 뒤에 받은 것은 **쓸 수 없다.**
    """

    name: str
    value: object
    available_at: datetime

    def __post_init__(self):
        if not isinstance(self.available_at, datetime):
            raise LeakError(
                f"피처 {self.name!r} 에 available_at 이 없다 — "
                "언제부터 알 수 있었는지 모르는 값은 학습에 못 쓴다")


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def usable(features, decision_ts: datetime) -> list:
    """결정 시각에 **이미 알 수 있던** 피처만. 🔴 아니면 터진다.

    ⚠️ "버리고 계속"이 아니라 예외인 이유: 누설 피처가 섞인 학습은 조용히
       좋은 점수를 내고, 그 점수를 보고 배포하면 실전에서 무너진다.
    """
    ts = _aware(decision_ts)
    bad = [f.name for f in (features or []) if _aware(f.available_at) > ts]
    if bad:
        raise LeakError(
            f"결정 시각({ts.isoformat()}) 이후에야 알 수 있던 피처: {bad}")
    return list(features or [])


@dataclass(frozen=True)
class Window:
    """학습 창 하나와 그 뒤의 검증 창. 🔴 경계는 **배타**라 겹치지 않는다."""

    train_start: datetime
    train_end: datetime      # 이 시각 **미만**이 학습
    valid_end: datetime      # `train_end` 이상 이 시각 미만이 검증

    def split(self, rows, *, ts_key: str = "ts"):
        """행 목록 → `(학습, 검증)`."""
        tr, va = [], []
        for r in rows or []:
            t = (r or {}).get(ts_key)
            if not isinstance(t, datetime):
                continue
            t = _aware(t)
            if self.train_start <= t < self.train_end:
                tr.append(r)
            elif self.train_end <= t < self.valid_end:
                va.append(r)
        return tr, va


def _cfg(path: str, default):
    from app.learning import get as g

    v = g(path)
    return default if v is None else v


def walk_forward(rows, *, ts_key: str = "ts", train_weeks: int | None = None,
                 valid_weeks: int | None = None, min_train: int = 1) -> list:
    """시간순 창 목록. 🔴 **미래에서 과거로 배우지 않는다.**

    학습 창(처음~지금) → 검증 창(다음 M주) → 한 칸 이동. 창 크기의 원본은
    `config/learning.yaml` 의 `learning.residual.train_weeks`·`valid_weeks` 다.

    ⚠️ 학습 표본이 `min_train` 미만인 창은 **건너뛴다**(빈 학습으로 낸 점수는
       의미가 없다). 건너뛴 창 수를 로그에 남긴다 — 조용히 줄이지 않는다.
    """
    tw = int(train_weeks if train_weeks is not None
             else _cfg("learning.residual.train_weeks", 12))
    vw = int(valid_weeks if valid_weeks is not None
             else _cfg("learning.residual.valid_weeks", 1))
    ts = sorted(_aware(r[ts_key]) for r in (rows or [])
                if isinstance((r or {}).get(ts_key), datetime))
    if not ts:
        return []
    first, last = ts[0], ts[-1]
    out, skipped = [], 0
    cur = first + timedelta(weeks=tw)
    while cur <= last:
        w = Window(train_start=first, train_end=cur,
                   valid_end=min(cur + timedelta(weeks=vw),
                                 last + timedelta(seconds=1)))
        tr, va = w.split(rows, ts_key=ts_key)
        if len(tr) >= min_train and va:
            out.append(w)
        else:
            skipped += 1
        cur += timedelta(weeks=vw)
    if skipped:
        logger.info("[learning] walk-forward 창 %d개 건너뜀(학습 표본 부족)",
                    skipped)
    return out


def by_league(rows, *, league_key: str = "league") -> dict:
    """🔴 **리그별로 독립**이다(지시문 LE-2-1). 리그를 섞어 학습하면 한 리그의
    가격 습관이 다른 리그로 샌다."""
    out: dict = {}
    for r in rows or []:
        out.setdefault((r or {}).get(league_key), []).append(r)
    return out


def calibration_halves(valid_rows, *, ts_key: str = "ts"):
    """검증 창을 앞뒤로 쪼갠다 — **앞에서 보정을 맞추고 뒤에서 잰다.**

    지시문 LE-2-3: "보정은 검증 창의 **앞부분에서만** 맞추고 뒤에서 잰다."
    🔴 앞에서 맞추고 앞에서 재면 그건 학습 성적이다.
    """
    rows = sorted((r for r in (valid_rows or [])
                   if isinstance((r or {}).get(ts_key), datetime)),
                  key=lambda r: _aware(r[ts_key]))
    if len(rows) < 2:
        return rows, []
    mid = len(rows) // 2
    return rows[:mid], rows[mid:]
