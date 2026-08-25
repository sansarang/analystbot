"""[2-1] Statcast 수집기 — 확률 모델(λ)의 1차 입력.

pybaseball로 MLB 투구 단위 원본을 받아 팀·투수 단위로 집계한다. 무료·무인증.

왜 Statcast인가:
- xwOBA(기대 wOBA)는 **타구 질**에서 계산돼 수비 시프트·구장·시퀀싱 같은 운 요소가
  가장 적게 섞인다. Wharton 논문의 변수 중요도(OBP>ISO>WHIP/FIP)가 가리키는
  "타선 지표가 예측력이 높다"를 가장 깨끗하게 구현하는 값이다.
- 배럴률·하드히트율·평균 타구속도는 최근 폼의 선행지표다(결과가 따라오기 전에 움직인다).

비용 관리: 조회가 무겁다(3일치 1.3만 행). 일 1회만 갱신하고 Redis에 캐시한다.
"""

import asyncio
import datetime as dt
import logging
import warnings

from app.config import get_settings

logger = logging.getLogger(__name__)

CACHE_TTL = 26 * 3600          # 하루 1회 갱신 + 여유
WINDOW_DAYS = 30               # 최근 30일 (모델이 요구하는 구간)
STARTER_WINDOW_DAYS = 35       # 선발 최근 5경기를 담기 위한 여유 구간

# statcast 팀 약어 → games 테이블 팀명
TEAM_CODE_TO_NAME = {
    "LAA": "Los Angeles Angels", "ARI": "Arizona Diamondbacks", "ATL": "Atlanta Braves",
    "BAL": "Baltimore Orioles", "BOS": "Boston Red Sox", "CHC": "Chicago Cubs",
    "CIN": "Cincinnati Reds", "CLE": "Cleveland Guardians", "COL": "Colorado Rockies",
    "CWS": "Chicago White Sox", "DET": "Detroit Tigers", "HOU": "Houston Astros",
    "KC": "Kansas City Royals", "LAD": "Los Angeles Dodgers", "WSH": "Washington Nationals",
    "NYM": "New York Mets", "OAK": "Athletics", "ATH": "Athletics",
    "PIT": "Pittsburgh Pirates", "SD": "San Diego Padres", "SEA": "Seattle Mariners",
    "SF": "San Francisco Giants", "STL": "St. Louis Cardinals", "TB": "Tampa Bay Rays",
    "TEX": "Texas Rangers", "TOR": "Toronto Blue Jays", "MIN": "Minnesota Twins",
    "PHI": "Philadelphia Phillies", "NYY": "New York Yankees", "MIL": "Milwaukee Brewers",
    "MIA": "Miami Marlins",
}


def _fetch_statcast(start: str, end: str):
    """블로킹 호출 — 반드시 to_thread로 감싸 쓴다."""
    warnings.filterwarnings("ignore")
    from pybaseball import statcast

    return statcast(start_dt=start, end_dt=end, verbose=False)


def _team_of_batter(row) -> str | None:
    """타석의 공격 팀 — inning_topbot이 'Top'이면 원정 공격."""
    top = str(row.get("inning_topbot") or "")
    code = row.get("away_team") if top.startswith("Top") else row.get("home_team")
    return TEAM_CODE_TO_NAME.get(str(code))


def aggregate_team_offense(df) -> dict[str, dict]:
    """팀별 최근 30일 타선 지표 — xwOBA·배럴률·하드히트율·평균 타구속도·K%/BB%·좌우 스플릿."""
    import pandas as pd

    if df is None or len(df) == 0:
        return {}
    d = df.copy()
    d["team"] = d.apply(_team_of_batter, axis=1)
    d = d[d["team"].notna()]

    out: dict[str, dict] = {}
    for team, g in d.groupby("team"):
        # 타석 종료 이벤트만으로 비율 지표를 만든다
        pa = g[g["events"].notna() & (g["events"] != "")]
        bip = g[g["launch_speed"].notna()]
        xwoba = pd.to_numeric(g["estimated_woba_using_speedangle"], errors="coerce").mean()
        stats = {
            "xwoba_30d": _round(xwoba, 3),
            "barrel_pct": _pct(bip, lambda x: x["launch_speed_angle"] == 6),
            "hardhit_pct": _pct(bip, lambda x: x["launch_speed"] >= 95),
            "exit_velo": _round(pd.to_numeric(bip["launch_speed"], errors="coerce").mean(), 1),
            "k_pct": _pct(pa, lambda x: x["events"].astype(str).str.startswith("strikeout")),
            "bb_pct": _pct(pa, lambda x: x["events"].astype(str) == "walk"),
            "pa": int(len(pa)),
        }
        for hand, key in (("L", "vs_lhp_woba"), ("R", "vs_rhp_woba")):
            sub = g[g["p_throws"] == hand]
            if len(sub) >= 50:      # 표본이 얇으면 스플릿을 만들지 않는다
                stats[key] = _round(
                    pd.to_numeric(sub["estimated_woba_using_speedangle"],
                                  errors="coerce").mean(), 3)
        out[team] = {k: v for k, v in stats.items() if v is not None}
    return out


def aggregate_pitchers(df) -> dict[str, dict]:
    """선발별 최근 지표 — 허용 xwOBA·평균 구속(피로 신호)·던진 손·최근 등판 수."""
    import pandas as pd

    if df is None or len(df) == 0:
        return {}
    d = df[df["pitcher"].notna()].copy()
    out: dict[str, dict] = {}
    for pid, g in d.groupby("pitcher"):
        name = _pitcher_name(g)
        if not name:
            continue
        games = g["game_pk"].nunique() if "game_pk" in g else 0
        recent = g.sort_values("game_date").tail(400)
        stats = {
            "xwoba_allowed": _round(
                pd.to_numeric(g["estimated_woba_using_speedangle"], errors="coerce").mean(), 3),
            "velo_recent": _round(
                pd.to_numeric(recent["release_speed"], errors="coerce").mean(), 1),
            "velo_window": _round(
                pd.to_numeric(g["release_speed"], errors="coerce").mean(), 1),
            "appearances": int(games),
        }
        hand = g["p_throws"].dropna()
        if len(hand):
            stats["throws"] = str(hand.iloc[0])
        out[name] = {k: v for k, v in stats.items() if v is not None}
    return out


def _pitcher_name(g) -> str | None:
    for col in ("player_name",):
        if col in g and g[col].notna().any():
            raw = str(g[col].dropna().iloc[0])
            if "," in raw:                     # statcast는 "Last, First" 형식
                last, first = (x.strip() for x in raw.split(",", 1))
                return f"{first} {last}"
            return raw
    return None


def _round(v, n):
    try:
        import math

        f = float(v)
        return None if math.isnan(f) else round(f, n)
    except (TypeError, ValueError):
        return None


def _pct(frame, mask_fn) -> float | None:
    if frame is None or len(frame) == 0:
        return None
    try:
        return round(100.0 * float(mask_fn(frame).sum()) / len(frame), 1)
    except Exception:
        return None


# ---------------------------------------------------------------- 캐시 접근

def _key(kind: str, date: str) -> str:
    return f"statcast:{kind}:{date}"


async def refresh(redis, date: str | None = None) -> dict:
    """일 1회 갱신 — 팀 타선·투수 지표를 계산해 Redis에 저장. 반환: 요약."""
    import json

    from app.pipeline import mlb_slate_date

    date = date or mlb_slate_date()
    end = dt.date.fromisoformat(date)
    start = end - dt.timedelta(days=WINDOW_DAYS)
    try:
        df = await asyncio.to_thread(_fetch_statcast, str(start), str(end))
    except Exception as exc:
        logger.error("[statcast] 수집 실패 %s~%s: %s", start, end, exc)
        return {"ok": False, "error": str(exc)[:200]}

    offense = aggregate_team_offense(df)
    pitchers = aggregate_pitchers(df)
    for kind, payload in (("offense", offense), ("pitchers", pitchers)):
        await redis.set(_key(kind, date), json.dumps(payload, ensure_ascii=False),
                        ex=CACHE_TTL)
    logger.info("[statcast] %s 갱신 — 팀 %d개, 투수 %d명 (원본 %d행)",
                date, len(offense), len(pitchers), len(df))
    return {"ok": True, "teams": len(offense), "pitchers": len(pitchers), "rows": len(df)}


async def load(redis, date: str | None = None) -> tuple[dict, dict]:
    """캐시된 (팀 타선, 투수 지표). 없으면 빈 dict — 모델은 해당 보정을 건너뛴다."""
    import json

    from app.pipeline import mlb_slate_date

    date = date or mlb_slate_date()
    out = []
    for kind in ("offense", "pitchers"):
        raw = await redis.get(_key(kind, date))
        out.append(json.loads(raw) if raw else {})
    return out[0], out[1]


def merge_into_research(research: dict, jg: dict, offense: dict, pitchers: dict) -> list[str]:
    """Statcast 지표를 리서치 페이로드에 얹는다. 반환: 실제로 채운 항목."""
    filled: list[str] = []
    for side, team_key in (("home", "home"), ("away", "away")):
        team = jg.get(team_key)
        stats = offense.get(team)
        if stats:
            block = research.setdefault(f"{side}_offense", {})
            for k, v in stats.items():
                block.setdefault(k, v)
            filled.append(f"{side} 타선({len(stats)}개 지표)")
        name = (research.get(f"{side}_pitcher") or {}).get("name") or jg.get(f"{side}_pitcher")
        pstats = pitchers.get(name) if name else None
        if pstats:
            block = research.setdefault(f"{side}_pitcher", {})
            for k, v in pstats.items():
                block.setdefault(k, v)
            filled.append(f"{side} 선발 {name}")
    return filled
