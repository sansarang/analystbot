"""🔴🔴 **경기 양상 판정** — 사용자 지시 2026-10-07 ②. **코드만**(LLM 없음).

> 시나리오 무게를 **스코어 단위로 나눠** 총 득점 분포를 계산한다(기존 `our_prob` 과
> **같은 나눔 규칙**). 저득점 / 난타전 / 한쪽 우세 / 접전 — 둘 이상 걸리면 **비중이
> 가장 큰 것**.

🔴 문턱은 `config/interpret_rules.yaml` 의 `shape` 가 든다(코드에 수를 안 적는다).
⚠️ 그 수는 **임시값**이다 — 실측 전이고, 고치는 것은 사용자다.
"""
from __future__ import annotations

import logging


logger = logging.getLogger(__name__)

#: 🔴 양상 이름 — 카드·논평이 **이 글자**를 본다(자유 문자열 금지)
SHAPES = ("저득점", "난타전", "한쪽 우세", "접전")


def rules() -> dict:
    """🔴 문턱 표 — `config/interpret_rules.yaml` 의 `shape` 하나다."""
    from app import rules as _r
    return dict((_r._load("config/interpret_rules.yaml").get("shape") or {}))


def of(grid: dict | None) -> dict:
    """🔴🔴 ② — 양상·비중·가장 무거운 스코어 셋. ⚠️ **격자가 없으면 빈 표**.

    🔴🔴 **바뀐 입력 2026-10-12(셋째 §1 처분)**: 종전에는 **시나리오 무게**를 받아
       스코어로 쪼갰다. 시나리오가 지워졌으므로 이제 **스코어 격자**(`{(홈, 원정):
       확률}`)를 그대로 받는다 — ⑯ 이 만든 그 격자다(사본 금지 · 한 출처).

    돌려주는 꼴:
    `{"shape": 양상, "low": 비중, "high": 비중, "one_sided": 비중,
      "close": 비중, "top_scores": [("2-1", 무게), …], "why": 사유, "total": 무게 합}`
    """
    spots_in = dict(grid or {})
    if not spots_in:
        return {}
    box = rules()
    lo_at = float(box.get("low_total_at") or 0.55)
    hi_at = float(box.get("high_total_at") or 0.40)
    one_at = float(box.get("one_sided_at") or 0.45)
    lo_max = int(box.get("low_total_max") or 2)
    hi_min = int(box.get("high_total_min") or 4)
    margin = int(box.get("one_sided_margin") or 2)
    # 🔴 격자를 그대로 쓴다 — 쪼갤 것이 없다(확률이 이미 스코어마다 있다)
    spots: dict[tuple[int, int], float] = {}
    total = 0.0
    for key, val in spots_in.items():
        if isinstance(key, str) and "-" in key:
            h, a = (int(x) for x in key.split("-", 1))
        else:
            h, a = (int(key[0]), int(key[1]))
        got = float(val or 0.0)
        if got <= 0:
            continue
        spots[(h, a)] = spots.get((h, a), 0.0) + got
        total += got
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
    # 🔴🔴 **오버 비중**(사용자 지시 2026-10-10(둘째) §4 — `오버 1.5/2.5/3.5`)
    #
    #  🔴 여기서 센다 — 스코어 비중을 나누는 규칙이 **이 함수 하나**이기 때문이다
    #     (카드가 따로 세면 같은 수를 두 곳에서 짓는다 · 사본 금지).
    #  ⚠️ `오버 2.5` 는 **총골 ≥ 3** 이다(2.5 를 넘는 정수는 3 부터다).
    over = {f"{x}": round(sum(v for (h, a), v in spots.items()
                              if (h + a) > x) / total, 4)
            for x in (0.5, 1.5, 2.5, 3.5, 4.5)}
    return {"shape": shape, "low": round(low, 4), "high": round(high, 4),
            "over": over,
            "one_sided": round(one, 4), "close": round(close, 4),
            "top_scores": [(f"{h}-{a}", round(v, 3)) for (h, a), v in top],
            "why": why, "total": round(total, 3)}
