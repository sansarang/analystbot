"""파레이 — 전수 탐색(best_parlays) + 리스크 등급제 조합(build_tiered_parlays)."""

from itertools import combinations
from math import prod

CONF_RANK = {"high": 2, "medium": 1, "low": 0}


def _combo(legs: list[dict]) -> dict:
    return {
        "legs": legs,
        "odds": round(prod(leg["odds"] for leg in legs), 2),
        "p": round(prod(leg["p"] for leg in legs), 4),
    }


def _pick_combo(cands: list[dict], sizes: tuple[int, ...],
                lo: float, hi: float, usage: dict) -> tuple[dict | None, bool]:
    """합산배당 [lo, hi] 범위에서 적중률 최대 조합. 범위 불가 시 최근접(완화 플래그).

    usage: 레그 재사용 카운터 — 동일 레그는 최대 2개 조합까지.
    """
    avail = [c for c in cands if usage.get(c["key"], 0) < 2]
    best_in, best_near, near_dist = None, None, None
    for n in sizes:
        if len(avail) < n:
            continue
        for combo_legs in combinations(avail, n):
            if len({leg["game_id"] for leg in combo_legs}) < n:
                continue  # 동일 경기 중복 금지
            c = _combo(list(combo_legs))
            if lo <= c["odds"] <= hi:
                if best_in is None or c["p"] > best_in["p"]:
                    best_in = c
            else:
                dist = lo - c["odds"] if c["odds"] < lo else c["odds"] - hi
                if best_near is None or dist < near_dist:
                    best_near, near_dist = c, dist
    if best_in:
        return best_in, False
    return best_near, best_near is not None  # (조합, 범위완화 여부)


def build_tiered_parlays(
    singles: list[dict], low_var: list[dict], flat_stake_krw: int | None,
) -> dict:
    """리스크 등급제 조합 1(안정)·2(균형)·3(고배당).

    singles: 판정 통과(제외·플래그 아님) 승패 픽 [{game_id, side, odds, p, confidence, league, starts_at_kst}]
    low_var: 저분산 마켓 레그 [{game_id, desc, odds, p, confidence, league, starts_at_kst}]
    규칙: 동일 레그 최대 2개 조합, 판정 제외/저신뢰 레그 금지(입력 전 필터),
          기준 미달 시 억지로 채우지 않고 '성립 안 됨'.
    """
    def key(leg):
        return f"{leg['game_id']}:{leg.get('desc') or leg.get('side')}"

    h2h = sorted(
        [{**s, "key": key(s), "desc": s.get("desc") or f"{s['side']} 승"} for s in singles],
        key=lambda x: (CONF_RANK.get(x.get("confidence", "medium"), 1), x["p"]),
        reverse=True,
    )
    lv = sorted(
        [{**s, "key": key(s)} for s in low_var],
        key=lambda x: (CONF_RANK.get(x.get("confidence", "medium"), 1), x["p"]),
        reverse=True,
    )
    all_cands = h2h + lv
    if len({c["key"] for c in all_cands}) < 2:
        return {"combos": [], "reason": "판정 통과 레그가 2개 미만 — 조합 성립 불가",
                "all_fail_prob": None}

    usage: dict[str, int] = {}
    combos, relaxed_any = [], False
    tiers = [
        ("안정형", lv[:8] or h2h[:8], (2,), 1.8, 2.5,
         f"권장 {flat_stake_krw:,}원 (플랫 100%)" if flat_stake_krw else "플랫 100%"),
        ("균형형", h2h[:8], (2, 3), 3.0, 6.0,
         f"권장 {flat_stake_krw // 2:,}원 (50%)" if flat_stake_krw else "플랫 50%"),
        ("고배당형·고위험 로또형", (h2h + lv)[:10], (3, 4), 8.0, 20.0, "소액 고정 (자금 0.3%)"),
    ]
    for name, pool_, sizes, lo, hi, stake_note in tiers:
        combo, relaxed = _pick_combo(pool_, sizes, lo, hi, usage)
        if combo is None:
            combos.append({"tier": name, "ok": False, "reason": "오늘은 성립 안 됨 (레그 부족)"})
            continue
        for leg in combo["legs"]:
            usage[leg["key"]] = usage.get(leg["key"], 0) + 1
        relaxed_any = relaxed_any or relaxed
        combos.append({
            "tier": name, "ok": True, "stake_note": stake_note,
            "relaxed": relaxed, **combo,
        })
    ok_combos = [c for c in combos if c.get("ok")]
    all_fail = round(prod(1 - c["p"] for c in ok_combos), 4) if ok_combos else None
    low_conf = all(
        CONF_RANK.get(leg.get("confidence", "medium"), 1) < 2
        for c in ok_combos for leg in c["legs"]
    ) if ok_combos else False
    return {
        "combos": combos, "all_fail_prob": all_fail,
        "low_confidence": low_conf or relaxed_any, "reason": None,
    }


def best_parlays(
    legs: list[dict], min_legs: int = 2, max_legs: int = 4, top: int = 3
) -> list[dict]:
    """legs: [{game_id, pick, p, odds, ev}] (ev > 0인 레그만 전달할 것).

    같은 경기 레그 2개가 들어간 조합은 제외. EV 내림차순 상위 top개 반환.
    """
    candidates = [leg for leg in legs if leg["ev"] > 0]
    parlays = []
    for n in range(min_legs, min(max_legs, len(candidates)) + 1):
        for combo in combinations(candidates, n):
            if len({leg["game_id"] for leg in combo}) < n:
                continue  # 동일 경기 중복 레그 금지
            p = prod(leg["p"] for leg in combo)
            odds = prod(leg["odds"] for leg in combo)
            parlays.append({
                "legs": [{"game_id": leg["game_id"], "pick": leg["pick"]} for leg in combo],
                "p": p,
                "odds": round(odds, 4),
                "ev": p * odds - 1.0,
            })
    parlays.sort(key=lambda x: x["ev"], reverse=True)
    return parlays[:top]
