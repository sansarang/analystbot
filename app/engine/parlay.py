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
    legs: list[dict], flat_stake_krw: int | None = None, sport: str | None = None,
) -> dict:
    """[9] 전 마켓 승인 레그 풀에서 리스크 등급제 조합 1(안정)·2(균형)·3(고배당).

    legs: [{game_id, desc, market, odds, p, confidence, league, starts_at_kst}]
    - 안정형: 레그당 확률 60%+ (더블찬스·+핸디·강한 언더오버 위주), 합산 1.8~2.5
    - 균형형: 승패+토탈 혼합, 3~6
    - 고배당형: 역배·-1.5 허용, 8~20
    규칙: 동일 레그 최대 2개 조합, 같은 경기 레그 2개(상관 마켓)는 한 조합에 금지
          (_pick_combo의 game_id 중복 배제), 기준 미달 시 억지로 채우지 않는다.
    '조합 성립 불가'는 전 마켓 검토 후 승인 레그 2개 미만일 때만 — 사유에 검토 범위 명시.
    sport: 검토 범위 문구의 종목 분기 ('mlb'는 더블찬스 없음·핸디캡=런라인). None이면 전체 표기.
    """
    from app.engine.markets import reviewed_markets_kr

    reviewed = f"{reviewed_markets_kr(sport)} 전 마켓 검토"  # [4] 종목별 용어
    cands = sorted(
        [{**l, "key": f"{l['game_id']}:{l.get('desc') or l.get('side')}",
          "desc": l.get("desc") or f"{l.get('side')} 승"} for l in legs],
        key=lambda x: (CONF_RANK.get(x.get("confidence", "medium"), 1), x["p"]),
        reverse=True,
    )
    distinct_games = len({c["game_id"] for c in cands})
    if distinct_games < 2:
        return {"combos": [],
                "reason": f"{reviewed} — 승인 레그가 {distinct_games}경기분뿐이라 조합 성립 불가",
                "all_fail_prob": None}

    stable = [c for c in cands if c["p"] >= 0.60]
    mixed = [c for c in cands if c.get("market") in ("h2h", "totals", None)]
    usage: dict[str, int] = {}
    combos, relaxed_any = [], False
    tiers = [
        ("안정형", stable[:10], (2,), 1.8, 2.5,
         f"권장 {flat_stake_krw:,}원 (플랫 100%)" if flat_stake_krw else "플랫 100%"),
        ("균형형", mixed[:10], (2, 3), 3.0, 6.0,
         f"권장 {flat_stake_krw // 2:,}원 (50%)" if flat_stake_krw else "플랫 50%"),
        ("고배당형·고위험 로또형", cands[:12], (3, 4), 8.0, 20.0, "소액 고정 (자금 0.3%)"),
    ]
    for name, pool_, sizes, lo, hi, stake_note in tiers:
        combo, relaxed = _pick_combo(pool_, sizes, lo, hi, usage)
        if combo is None:
            combos.append({"tier": name, "ok": False,
                           "reason": f"오늘은 성립 안 됨 ({reviewed} 후 조건 맞는 레그 부족)"})
            continue
        for leg in combo["legs"]:
            usage[leg["key"]] = usage.get(leg["key"], 0) + 1
        relaxed_any = relaxed_any or relaxed
        from app.engine.markets import payout_10k

        combos.append({
            "tier": name, "ok": True, "stake_note": stake_note,
            "relaxed": relaxed, **combo,
            # [3-5] 조합도 돈으로 말한다 — 합산 배당 기준 1만 원 실수령액
            "payout_10k": payout_10k(combo["odds"]),
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
