"""[§2-3] 축구 정식 데이터 소스 — soccerdata (무료·무인증).

Perplexity 산문에서 xG를 긁던 방식을 대체한다. 정식 소스가 있는데 산문 파싱 리스크를
감수할 이유가 없다.

소스별 용도(명확히 분리):
- **Understat**: 팀별 최근 6경기 xG·xGA, 홈/원정 스플릿 → λ 계산의 1차 입력
- **FBref**: 팀 상세 스탯(슈팅·점유·수비) → 보조
- **ClubElo**: 리그별 Elo 레이팅 → 자체 CSV 피팅 대체 + 팀명 별칭 해소
- **MatchHistory**: 과거 결과 + 마감 배당 → 백테스트·캘리브레이션 학습 데이터

커버리지 한계(2026-08-25 실조회): soccerdata 기본 지원은 Big 5뿐이다.
우리 화이트리스트 7개 중 EPL·라리가·세리에A·분데스리가만 커버되고
J1·덴마크 수페르리가·K리그1은 **미지원 → 기존 Perplexity 수집 유지**.

스크래핑 기반이라 느리다: 라이브러리 내장 캐시 + Redis 일 1회 캐시로 관리한다.
"""

import asyncio
import json
import logging

logger = logging.getLogger(__name__)

CACHE_TTL = 26 * 3600
XG_WINDOW = 6          # 최근 6경기 (모델 요구 구간)

# 우리 리그 라벨 → soccerdata 리그 ID. 없으면 미지원(Perplexity 폴백).
SD_LEAGUES = {
    "EPL": "ENG-Premier League",
    "라리가": "ESP-La Liga",
    "세리에A": "ITA-Serie A",
    "분데스리가": "GER-Bundesliga",
}
UNSUPPORTED = ("J1 리그", "덴마크 수페르리가", "K리그1")


def supported(label: str) -> bool:
    return label in SD_LEAGUES


MIN_XG_MATCHES = 3     # 이보다 표본이 얇으면 xG를 쓰지 않는다 (거짓 정밀도 금지)


def _season_code(season: str | None = None, back: int = 0) -> str:
    """soccerdata 시즌 코드 (예: 2025-26 → '2526'). back=1이면 직전 시즌."""
    import datetime as dt

    if season and not back:
        return season
    today = dt.date.today()
    start = (today.year if today.month >= 7 else today.year - 1) - back
    return f"{start % 100:02d}{(start + 1) % 100:02d}"


# ---------------------------------------------------------------- Understat xG

def _fetch_understat(league_id: str, season: str):
    """블로킹 스크래핑 — 반드시 to_thread로 감싼다."""
    import warnings

    warnings.filterwarnings("ignore")
    import soccerdata as sd

    return sd.Understat(leagues=league_id, seasons=season).read_team_match_stats()


def team_xg_windows(df, window: int = XG_WINDOW) -> dict[str, dict]:
    """경기 단위 표 → 팀별 최근 N경기 xG/xGA + 홈/원정 스플릿.

    반환: {팀명: {xg6, xga6, xg6_home, xga6_home, xg6_away, xga6_away, matches}}
    """
    import pandas as pd

    if df is None or len(df) == 0:
        return {}
    rows = []
    for _idx, r in df.reset_index().iterrows():
        date = r.get("date")
        for side, opp in (("home", "away"), ("away", "home")):
            team = r.get(f"{side}_team")
            if not team:
                continue
            rows.append({
                "team": str(team), "date": date, "venue": side,
                "xg": pd.to_numeric(r.get(f"{side}_xg"), errors="coerce"),
                "xga": pd.to_numeric(r.get(f"{opp}_xg"), errors="coerce"),
            })
    long = pd.DataFrame(rows).dropna(subset=["xg", "xga"])
    if long.empty:
        return {}

    out: dict[str, dict] = {}
    for team, g in long.groupby("team"):
        g = g.sort_values("date")
        recent = g.tail(window)
        stats = {
            "xg6": round(float(recent["xg"].mean()), 3),
            "xga6": round(float(recent["xga"].mean()), 3),
            "matches": int(len(recent)),
        }
        for venue in ("home", "away"):
            sub = g[g["venue"] == venue].tail(window)
            if len(sub) >= 3:      # 표본이 얇으면 스플릿을 만들지 않는다
                stats[f"xg6_{venue}"] = round(float(sub["xg"].mean()), 3)
                stats[f"xga6_{venue}"] = round(float(sub["xga"].mean()), 3)
        out[team] = stats
    return out


# ---------------------------------------------------------------- Club Elo

def _fetch_club_elo():
    import warnings

    warnings.filterwarnings("ignore")
    import soccerdata as sd

    return sd.ClubElo().read_by_date()


def elo_ratings(df) -> dict[str, float]:
    """클럽별 Elo. ClubElo는 리그 무관 전체 클럽을 주므로 미지원 리그도 일부 잡힌다."""
    if df is None or len(df) == 0:
        return {}
    col = "elo" if "elo" in df.columns else df.columns[-1]
    out = {}
    for name, val in df[col].items():
        try:
            out[str(name)] = round(float(val), 1)
        except (TypeError, ValueError):
            continue
    return out


# ---------------------------------------------------------------- 캐시 접근

def _key(kind: str, scope: str, date: str) -> str:
    return f"soccerdata:{kind}:{scope}:{date}"


async def refresh_league(redis, label: str, date: str, season: str | None = None) -> dict:
    """리그 1개의 xG 창을 갱신해 캐시. 미지원 리그는 건너뛴다."""
    if not supported(label):
        return {"ok": False, "skipped": True, "reason": "soccerdata 미지원 리그"}
    league_id = SD_LEAGUES[label]
    # 시즌 초에는 현 시즌 표본이 1~2경기뿐이다 — 직전 시즌을 이어붙여 창을 채운다.
    frames = []
    for back in (0, 1):
        try:
            frames.append(await asyncio.to_thread(
                _fetch_understat, league_id, _season_code(season, back)))
        except Exception as exc:
            logger.warning("[soccerdata] Understat 실패 %s(시즌-%d): %s",
                           label, back, str(exc)[:120])
    if not frames:
        return {"ok": False, "error": "Understat 조회 실패"}
    import pandas as pd

    df = pd.concat(frames) if len(frames) > 1 else frames[0]
    windows = team_xg_windows(df)
    await redis.set(_key("xg", label, date), json.dumps(windows, ensure_ascii=False),
                    ex=CACHE_TTL)
    logger.info("[soccerdata] %s xG 갱신 — 팀 %d개 (경기 %d)", label, len(windows), len(df))
    return {"ok": True, "teams": len(windows), "matches": len(df)}


async def refresh_elo(redis, date: str) -> dict:
    """Club Elo 갱신. 실패 시 기존 CSV 피팅(soccer_elo)이 폴백으로 남는다."""
    try:
        df = await asyncio.to_thread(_fetch_club_elo)
    except Exception as exc:
        logger.warning("[soccerdata] ClubElo 실패 — CSV 피팅 폴백 유지: %s", str(exc)[:160])
        return {"ok": False, "error": str(exc)[:200]}
    ratings = elo_ratings(df)
    await redis.set(_key("elo", "all", date), json.dumps(ratings, ensure_ascii=False),
                    ex=CACHE_TTL)
    logger.info("[soccerdata] ClubElo 갱신 — 클럽 %d개", len(ratings))
    return {"ok": True, "clubs": len(ratings)}


async def load_xg(redis, label: str, date: str) -> dict:
    raw = await redis.get(_key("xg", label, date))
    return json.loads(raw) if raw else {}


async def load_elo(redis, date: str) -> dict:
    raw = await redis.get(_key("elo", "all", date))
    return json.loads(raw) if raw else {}


def merge_xg_into_research(research: dict, jg: dict, windows: dict) -> list[str]:
    """Understat xG를 리서치에 얹는다 (홈/원정 스플릿 우선). 반환: 채운 항목."""
    from app.collectors.football import similar_team

    filled: list[str] = []
    for side, venue in (("home", "home"), ("away", "away")):
        team = jg.get(side)
        stats = windows.get(team) or _fuzzy(windows, team, similar_team)
        if not stats:
            continue
        if stats.get("matches", 0) < MIN_XG_MATCHES:
            continue          # 표본이 얇으면 쓰지 않는다 — 모델이 보정을 건너뛴다
        # 홈팀은 홈 스플릿, 원정팀은 원정 스플릿이 더 정확하다
        block = research.setdefault(f"{side}_recent_form", {})
        block.setdefault("xg6", stats.get(f"xg6_{venue}", stats.get("xg6")))
        block.setdefault("xga6", stats.get(f"xga6_{venue}", stats.get("xga6")))
        block.setdefault("xg_matches", stats["matches"])
        filled.append(f"{side} xG {block['xg6']}/xGA {block['xga6']} ({stats['matches']}경기)")
    return filled


def _fuzzy(windows: dict, team: str | None, matcher) -> dict | None:
    if not team:
        return None
    for name, stats in windows.items():
        if matcher(name, team):
            return stats
    return None
