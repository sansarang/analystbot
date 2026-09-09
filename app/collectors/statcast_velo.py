"""[SAT-8] 선발 최근 구속 추세 — 박스스코어에 없는 투수 건강/폼 신호.

🔴 **왜 고급정보인가.** 박스스코어는 실점·이닝만 준다. 하지만 선발이 최근 등판에서
   속구 평균 구속이 2mph 떨어졌다면 피로·부상 신호이고, 시장은 그걸 보는데 우리
   DB 에는 없다 — 괴리의 후보다. 최근 등판만 보므로 대원칙(최근 3~5경기)에 맞는다.

🔴 원천은 Baseball Savant CSV (무키·AWS IP 로 도달, 실측 2026-09-09). **hfSea
   (시즌) 파라미터가 필수**다 — 없으면 0행이 온다.

⚠️ 구속 하락 단독은 약한 예측자다(연구: 적중 54.7%·오탐 41%). 그래서 판정을 직접
   움직이지 않고 **재료(발견)**로만 넣는다 — 요약기·변수 대장이 다른 신호와 합친다.
"""
from __future__ import annotations

import csv
import io
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_SAVANT_CSV = "https://baseballsavant.mlb.com/statcast_search/csv"

#: 속구 계열만 구속 추세에 쓴다(변화구는 원래 느리다).
_FASTBALLS = ("FF", "SI", "FC")
#: 이만큼(mph) 넘게 변해야 신호로 본다. 그 아래는 소음.
VELO_DELTA_MIN = 1.0
#: 추세에 쓰는 최근 등판 수(직전 1 vs 그 이전 최대 N-1). 대원칙 최근 5경기.
RECENT_GAMES = 5


def parse_statcast_csv(text: str) -> list[dict]:
    """Savant CSV → [{game_date, pitch_type, release_speed(str)}]."""
    if not text:
        return []
    # 🔴 [SAT-9] Savant CSV 는 BOM(﻿)이 앞에 붙어 온다 — 벗기지 않으면 첫
    #    컬럼명이 '﻿pitch_type' 이 돼 조회가 전부 실패한다(실측: 371KB·0행).
    text = text.lstrip("﻿")
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        if row.get("game_date") and row.get("pitch_type"):
            out.append(row)
    return out


def velocity_by_game(rows: list[dict]) -> dict[str, float]:
    """등판일 → 속구 평균 구속. 속구가 없는 날은 뺀다."""
    byg: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if r.get("pitch_type") not in _FASTBALLS:
            continue
        try:
            byg[r["game_date"]].append(float(r["release_speed"]))
        except (TypeError, ValueError):
            continue
    return {d: round(sum(v) / len(v), 2) for d, v in byg.items() if v}


def velocity_trend(by_game: dict[str, float]) -> dict | None:
    """직전 등판 vs 그 이전 평균. 신호(|Δ|>=VELO_DELTA_MIN)가 없으면 None.

    반환: {last, prior_avg, delta_mph, games}
    """
    if len(by_game) < 2:
        return None
    dates = sorted(by_game)[-RECENT_GAMES:]
    last = by_game[dates[-1]]
    prior = [by_game[d] for d in dates[:-1]]
    prior_avg = round(sum(prior) / len(prior), 2)
    delta = round(last - prior_avg, 2)
    if abs(delta) < VELO_DELTA_MIN:
        return None
    return {"last": last, "prior_avg": prior_avg, "delta_mph": delta,
            "games": len(dates)}


def describe(name: str, trend: dict) -> str:
    """발견 기사 본문 한 줄. 경기 고유 숫자를 담는다."""
    d = trend["delta_mph"]
    tag = "구속 저하 — 피로·부상 신호" if d < 0 else "구속 상승"
    return (f"{name} 최근 등판 속구 평균 {trend['last']:.1f}mph — 직전 "
            f"{trend['games'] - 1}등판 평균 {trend['prior_avg']:.1f}mph 대비 "
            f"{d:+.1f}mph ({tag}). 최근 {trend['games']}등판 Statcast.")


async def fetch_pitcher_statcast(pitcher_id: int, *, season: int,
                                 start: str, end: str, client=None) -> str:
    """투수 1명의 최근 Statcast CSV. `client` 주입 가능(테스트). 실패는 빈 문자열.

    🔴 hfSea(시즌)가 없으면 0행이 온다 — 실측으로 확인된 필수 파라미터.
    """
    if client is not None:
        return await client(pitcher_id, season, start, end)
    import httpx

    params = {
        "all": "true", "hfSea": f"{season}|", "hfGT": "R|",
        "player_type": "pitcher", "pitchers_lookup[]": str(pitcher_id),
        "game_date_gt": start, "game_date_lt": end, "type": "details",
    }
    try:
        async with httpx.AsyncClient(timeout=40.0, follow_redirects=True,
                                     headers={"User-Agent": _UA}) as c:
            r = await c.get(_SAVANT_CSV, params=params)
            r.raise_for_status()
            return r.text
    except Exception as exc:
        logger.warning("[statcast_velo] Savant 조회 실패 id=%s: %s", pitcher_id, exc)
        return ""


async def pitcher_trend(pitcher_id: int, name: str, *, season: int,
                        start: str, end: str, client=None) -> dict | None:
    """투수 1명의 구속 추세 신호. 없으면 None. 발견 기사용 dict 를 함께 담는다."""
    text = await fetch_pitcher_statcast(
        pitcher_id, season=season, start=start, end=end, client=client)
    trend = velocity_trend(velocity_by_game(parse_statcast_csv(text)))
    if trend is None:
        return None
    return {**trend, "name": name, "body": describe(name, trend)}
