"""[LE-4] 역사 경기 → 피처. **전부 개장 시점에 알 수 있는 값만.**

🔴 **마감가·결과·경기 후 정보는 여기 없다.** 있으면 `split.usable` 이 터진다.
🔴 `elo_diff` 는 그 경기 **이전까지만** 리플레이한 값이다 — 시즌 전체를 미리
   피팅한 Elo 를 쓰면 미래를 본다. 계약이 그것을 잠근다.

⚠️ 구조 카드(선발·결장·구장·날씨)는 **역사 자료에 없다.** 그래서 이 백테스트는
   "가격과 일정만으로 시장의 오차를 맞힐 수 있나"를 묻는다. 구조 정보의
   값어치는 실시간 축적분에서 따로 잰다.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timezone

logger = logging.getLogger(__name__)

#: 피처 이름 — 순서가 곧 모델 입력 순서다. 🔴 **한 곳에서만 정한다.**
NAMES = ("p_open", "elo_diff", "rest_home", "rest_away",
         "book_spread", "overround", "month")

#: 🔴 Elo 기본값·K 는 `app/models/elo_core` 가 원본이다. 여기서 정하지 않는다.
_ELO_START = None          # elo_core 에서 읽는다


def _elo_start() -> float:
    global _ELO_START
    if _ELO_START is None:
        try:
            from app.models import elo_core

            _ELO_START = float(getattr(elo_core, "START", 1500.0))
        except Exception:                                   # pragma: no cover
            _ELO_START = 1500.0
    return _ELO_START


def _elo_k() -> float:
    from app.models.soccer_elo import K_FACTOR

    return float(K_FACTOR)


def _as_dt(d) -> datetime:
    """`date` → 그날 00:00 UTC. 🔴 개장 시각을 모르므로 **경기일 0시**로 둔다 —
    그러면 `available_at` 이 실제보다 **이르게** 잡혀 누설 쪽으로 관대해지지
    않는다(늦게 잡는 것이 위험한 방향이다)."""
    if isinstance(d, datetime):
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return datetime.combine(d, time(0, 0), tzinfo=timezone.utc)


def running_elo(matches) -> list[dict]:
    """경기 목록(시간순) → 각 경기에 **그 직전까지의** Elo 를 붙인다.

    🔴 리플레이는 앞에서 뒤로만 간다. 한 경기를 처리할 때 그 경기의 결과는
       **아직 반영되지 않은** 값을 쓴다 — 그게 누설을 막는 지점이다.
    ⚠️ Elo 식을 다시 짜지 않는다 — 기대 승률은 `elo_core.sigmoid` 를 쓴다.
    """
    from app.models.elo_core import LOG10, sigmoid

    k, start = _elo_k(), _elo_start()
    r: dict = {}
    last: dict = {}
    out = []
    for m in sorted(matches, key=lambda x: x["match_date"]):
        h, a = m["home"], m["away"]
        rh, ra = r.get(h, start), r.get(a, start)
        d = _as_dt(m["match_date"])
        out.append({
            **m,
            # 🔴 **그 경기 이전까지의** 값이다
            "elo_diff": round(rh - ra, 2),
            "rest_home": ((d - _as_dt(last[h])).days if h in last else None),
            "rest_away": ((d - _as_dt(last[a])).days if a in last else None),
        })
        # 그 다음에야 결과를 반영한다
        ftr = m.get("ftr")
        if ftr in ("H", "D", "A"):
            exp = sigmoid((rh - ra) * LOG10 / 400.0)
            score = 1.0 if ftr == "H" else (0.5 if ftr == "D" else 0.0)
            r[h] = rh + k * (score - exp)
            r[a] = ra - k * (score - exp)
            last[h] = last[a] = m["match_date"]
    return out


def build(row) -> dict:
    """한 경기 → `{이름: 값}`. 못 만드는 값은 **None**(0 으로 채우지 않는다).

    ⚠️ `HistGradientBoosting` 은 결측을 **네이티브로** 다룬다. 0 으로 채우면
       "쉬는 날 0일"과 "모른다"가 같은 값이 된다.
    """
    return {
        "p_open": row.get("p_open"),
        "elo_diff": row.get("elo_diff"),
        "rest_home": row.get("rest_home"),
        "rest_away": row.get("rest_away"),
        "book_spread": row.get("book_spread"),
        "overround": row.get("overround"),
        "month": (row["match_date"].month
                  if row.get("match_date") is not None else None),
    }


def as_features(row) -> list:
    """`split.Feature` 목록. 🔴 **`available_at` 을 붙여야 학습에 쓸 수 있다.**

    개장 시점을 모르므로 **경기일 0시**를 쓴다 — 실제 개장은 그보다 앞이므로
    이 값은 보수적이다.
    """
    from app.learning.split import Feature

    at = _as_dt(row["match_date"])
    return [Feature(k, v, at) for k, v in build(row).items()]
