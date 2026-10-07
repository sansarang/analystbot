"""🔴🔴 **경기 양상 판정** — 사용자 지시 2026-10-07 ②. **코드만**(LLM 없음).

> 시나리오 무게를 **스코어 단위로 나눠** 총 득점 분포를 계산한다(기존 `our_prob` 과
> **같은 나눔 규칙**). 저득점 / 난타전 / 한쪽 우세 / 접전 — 둘 이상 걸리면 **비중이
> 가장 큰 것**.

🔴 문턱은 `config/interpret_rules.yaml` 의 `shape` 가 든다(코드에 수를 안 적는다).
⚠️ 그 수는 **임시값**이다 — 실측 전이고, 고치는 것은 사용자다.
"""
from __future__ import annotations

import logging

from app.core.schema import HypoSet

logger = logging.getLogger(__name__)

#: 🔴 양상 이름 — 카드·논평이 **이 글자**를 본다(자유 문자열 금지)
SHAPES = ("저득점", "난타전", "한쪽 우세", "접전")


def rules() -> dict:
    """🔴 문턱 표 — `config/interpret_rules.yaml` 의 `shape` 하나다."""
    from app import rules as _r
    return dict((_r._load("config/interpret_rules.yaml").get("shape") or {}))


def of(hypo: HypoSet | None) -> dict:
    """🔴🔴 ② — 양상·비중·가장 무거운 스코어 셋. ⚠️ 시나리오가 없으면 빈 표.

    돌려주는 꼴:
    `{"shape": 양상, "low": 비중, "high": 비중, "one_sided": 비중,
      "close": 비중, "top_scores": [("2-1", 무게), …], "why": 사유, "total": 무게 합}`
    """
    rows = list(getattr(hypo, "scenarios", []) or [])
    if not rows:
        return {}
    box = rules()
    lo_at = float(box.get("low_total_at") or 0.55)
    hi_at = float(box.get("high_total_at") or 0.40)
    one_at = float(box.get("one_sided_at") or 0.45)
    lo_max = int(box.get("low_total_max") or 2)
    hi_min = int(box.get("high_total_min") or 4)
    margin = int(box.get("one_sided_margin") or 2)
    # 🔴 **스코어 단위**로 나눈다 — `compare.our_prob` 과 같은 규칙(무게 ÷ 스코어 수)
    spots: dict[tuple[int, int], float] = {}
    total = 0.0
    for sc in rows:
        w = float(sc.strength or 0.0)
        pairs = list(sc.outcomes or [])
        if w <= 0 or not pairs:
            continue
        share = w / len(pairs)
        for h, a in pairs:
            spots[(int(h), int(a))] = spots.get((int(h), int(a)), 0.0) + share
            total += share
    if total <= 0:
        return {}
    low = sum(v for (h, a), v in spots.items() if h + a <= lo_max) / total
    high = sum(v for (h, a), v in spots.items() if h + a >= hi_min) / total
    one = sum(v for (h, a), v in spots.items() if abs(h - a) >= margin) / total
    close = sum(v for (h, a), v in spots.items() if abs(h - a) <= 1) / total
    hits = [(name, got, at) for name, got, at in
            (("저득점", low, lo_at), ("난타전", high, hi_at),
             ("한쪽 우세", one, one_at)) if got >= at]
    if hits:
        # 🔴 둘 이상 걸리면 **비중이 가장 큰 것**(지시 ②)
        hits.sort(key=lambda x: -x[1])
        shape, got, at = hits[0]
        why = (f"{shape} 비중 {got:.0%} ≥ 문턱 {at:.0%}"
               + (f" · 함께 걸린 것 {[h[0] for h in hits[1:]]}"
                  if len(hits) > 1 else ""))
    else:
        shape = "접전"
        why = (f"문턱을 넘은 양상이 없다(저득점 {low:.0%}<{lo_at:.0%} · "
               f"난타전 {high:.0%}<{hi_at:.0%} · 한쪽 우세 {one:.0%}<{one_at:.0%})")
    top = sorted(spots.items(), key=lambda kv: -kv[1])[:3]
    return {"shape": shape, "low": round(low, 4), "high": round(high, 4),
            "one_sided": round(one, 4), "close": round(close, 4),
            "top_scores": [(f"{h}-{a}", round(v, 3)) for (h, a), v in top],
            "why": why, "total": round(total, 3)}
