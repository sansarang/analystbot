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
import pathlib
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
    # 🔴 [STC-1 2026-09-08] **원본이 주는 코드는 `AZ` 다.** `ARI` 는 한 번도
    #    오지 않는다(실측: statcast 응답 팀코드 30종에 AZ 있고 ARI 없음).
    #    그래서 애리조나 행이 전부 `None` 이 되어 조용히 버려졌고, 캐시가
    #    29팀이었다 — 애리조나 경기 25건에서 λ 타선 축·불펜 과소모·타자
    #    랭킹이 통째로 비었다. `ARI` 는 남겨 둔다(OAK/ATH 와 같은 이유).
    "AZ": "Arizona Diamondbacks",
    "CWS": "Chicago White Sox", "DET": "Detroit Tigers", "HOU": "Houston Astros",
    "KC": "Kansas City Royals", "LAD": "Los Angeles Dodgers", "WSH": "Washington Nationals",
    "NYM": "New York Mets", "OAK": "Athletics", "ATH": "Athletics",
    "PIT": "Pittsburgh Pirates", "SD": "San Diego Padres", "SEA": "Seattle Mariners",
    "SF": "San Francisco Giants", "STL": "St. Louis Cardinals", "TB": "Tampa Bay Rays",
    "TEX": "Texas Rangers", "TOR": "Toronto Blue Jays", "MIN": "Minnesota Twins",
    "PHI": "Philadelphia Phillies", "NYY": "New York Yankees", "MIL": "Milwaukee Brewers",
    "MIA": "Miami Marlins",
}


#: MLB 구단 수. 캐시가 이보다 적으면 **어떤 팀의 재료가 통째로 빈 것**이다.
#  ⚠️ 0건이 아니라 29/30 이라 종전에는 아무도 못 봤다. 로그는 "팀 29개"라고
#     정확히 찍었지만 **30이어야 한다고 말해 줄 것이 없었다.**
MLB_TEAM_COUNT = 30


def audit_team_coverage(seen_codes, team_names) -> dict:
    """원본 팀코드·집계 팀명을 대사한다. 문제가 있으면 **시끄럽게** 남긴다.

    반환: {"unknown_codes": [...], "missing_teams": [...]}

    🔴 '조용한 성공' — 분모가 사라지는 실패에는 경보를 함께 넣는다
       (ENGINEERING §1-④). 모르는 코드는 `_team_of_batter` 가 `None` 으로
       만들고 `notna()` 가 버린다. 버리는 것 자체는 옳지만, **버렸다는
       사실이 어디에도 남지 않는 것**이 결함이었다.
    """
    unknown = sorted(str(c) for c in seen_codes if str(c) not in TEAM_CODE_TO_NAME)
    missing = sorted(set(TEAM_CODE_TO_NAME.values()) - set(team_names))
    if unknown:
        logger.error("[statcast] 🔴 매핑에 없는 팀코드 %s — 그 팀 재료가 통째로 "
                     "빈다 (팀 코드가 바뀌었을 수 있다)", unknown)
    if missing:
        logger.error("[statcast] 🔴 집계에서 빠진 팀 %s", missing)
    return {"unknown_codes": unknown, "missing_teams": missing}


async def _alert_coverage(gaps: dict) -> None:
    """대사 결과를 워치독으로. 실패해도 수집을 막지 않는다."""
    if not gaps["unknown_codes"] and not gaps["missing_teams"]:
        return
    try:
        from app.alerts import watchdog

        await watchdog("W-SOURCE-DRIFT",
                       f"statcast 팀 매핑 어긋남 — 모르는 코드 "
                       f"{gaps['unknown_codes']} · 빠진 팀 {gaps['missing_teams']}",
                       target="statcast")
    except Exception as exc:
        logger.debug("[statcast] 커버리지 경보 실패: %s", exc)


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


# [§2] 표본 가드 — 타선 스플릿과 같은 기준을 투수에도 적용한다.
#      가드가 없어 허용 xwOBA 분포가 0.012~1.010까지 벌어졌다(실력값일 수 없다).
MIN_PITCHER_PITCHES = 50       # 이만큼 던졌거나
MIN_PITCHER_APPEARANCES = 3    # 이만큼 등판했으면 채택
LOW_SAMPLE_NOTE = "표본 부족 — 리그 평균 적용"


def _xwoba(frame, pd) -> float | None:
    """정식 xwOBA — **삼진·볼넷을 포함한다**.

    `estimated_woba_using_speedangle`은 인플레이 타구에만 값이 있다. 그것만
    평균 내면 삼진(wOBA 0)이 통째로 빠져 **부호가 뒤집힌다**: 삼진이 많은
    투수가 나쁘게, 삼진을 많이 당하는 타선이 좋게 나온다.
    (실측 2026-08-25: Paul Skenes 0.368 > 리그 중앙 0.310 — 정반대 결과)

    정식 정의: Σ(타구는 추정치, 그 외는 실제 woba_value) / Σ woba_denom
    """
    if "woba_denom" not in frame or "woba_value" not in frame:
        return None
    denom = pd.to_numeric(frame["woba_denom"], errors="coerce")
    mask = denom.notna() & (denom > 0)
    total = denom[mask].sum()
    if not total:
        return None
    actual = pd.to_numeric(frame["woba_value"], errors="coerce")
    est = pd.to_numeric(frame.get("estimated_woba_using_speedangle"), errors="coerce")
    # 타구는 추정치 우선, 삼진·볼넷 등은 실제값
    num = est.fillna(actual)[mask].fillna(0).sum()
    return float(num / total)


def _tail_games(g, n: int, key: str = "game_date"):
    """그 그룹의 **최근 n경기** 행만 남긴다. n이 0 이하면 그대로 둔다.

    [§8-6] 관측 창을 일수가 아니라 경기 수로 자른다. 팀마다 휴식일이 달라
    "최근 30일"이 팀별로 다른 경기 수를 뜻했다 — 창 길이 비교가 불가능했다.
    """
    if not n or n <= 0 or key not in g:
        return g
    keys = sorted(g[key].dropna().unique())
    if len(keys) <= n:
        return g
    return g[g[key].isin(set(keys[-n:]))]


def aggregate_team_offense(df, window_games: int = 0) -> dict[str, dict]:
    """팀별 타선 지표 — xwOBA·배럴률·하드히트율·평균 타구속도·K%/BB%·좌우 스플릿.

    `window_games`가 양수면 각 팀의 **최근 그 경기 수**만 집계한다(기본 0 = 전량).
    ⚠️ 출력 키 `xwoba_30d`는 창이 30일이 아니어도 **이름을 바꾸지 않는다** —
       scoring·merge_into_research가 이 키로 읽는다. 이름 변경은 계약 파손이다.
    """
    import pandas as pd

    if df is None or len(df) == 0:
        return {}
    d = df.copy()
    d["team"] = d.apply(_team_of_batter, axis=1)
    d = d[d["team"].notna()]

    out: dict[str, dict] = {}
    for team, g_all in d.groupby("team"):
        g = _tail_games(g_all, window_games)
        # 타석 종료 이벤트만으로 비율 지표를 만든다
        pa = g[g["events"].notna() & (g["events"] != "")]
        bip = g[g["launch_speed"].notna()]
        xwoba = _xwoba(g, pd)      # 삼진 포함 정식 계산
        stats = {
            "xwoba_30d": _round(xwoba, 3),
            "barrel_pct": _pct(bip, lambda x: x["launch_speed_angle"] == 6),
            "hardhit_pct": _pct(bip, lambda x: x["launch_speed"] >= 95),
            "exit_velo": _round(pd.to_numeric(bip["launch_speed"], errors="coerce").mean(), 1),
            "k_pct": _pct(pa, lambda x: x["events"].astype(str).str.startswith("strikeout")),
            "bb_pct": _pct(pa, lambda x: x["events"].astype(str) == "walk"),
            "pa": int(len(pa)),
            "games": int(g["game_date"].nunique()),
        }
        for hand, key in (("L", "vs_lhp_woba"), ("R", "vs_rhp_woba")):
            sub = g[g["p_throws"] == hand]
            if len(sub) >= 50:      # 표본이 얇으면 스플릿을 만들지 않는다
                stats[key] = _round(_xwoba(sub, pd), 3)
        out[team] = {k: v for k, v in stats.items() if v is not None}
    return out


# [§2] 불펜 소모 — 최근 3경기 구원 투구 수. 리그 중앙값 대비 이 배수를 넘으면 '과소모'.
#      KBO usage는 최근 3경기. 달력 3일은 더블헤더·휴식일에 창이 어긋난다.
BULLPEN_RECENT_GAMES = 3
BULLPEN_OVERUSE_RATIO = 1.30


def _with_fielding_team(df):
    """투구 행에 수비 팀(fld_team)을 붙인다. 'Top'이면 홈이 수비다."""
    if df is None or len(df) == 0 or "inning_topbot" not in df or "game_pk" not in df:
        return None
    d = df[df["pitcher"].notna() & df["game_pk"].notna()].copy()
    d["fld_team"] = d.apply(
        lambda r: TEAM_CODE_TO_NAME.get(str(
            r.get("home_team") if str(r.get("inning_topbot") or "").startswith("Top")
            else r.get("away_team"))), axis=1)
    return d[d["fld_team"].notna()]


def league_baselines(offense: dict, pitchers: dict) -> dict:
    """같은 데이터셋에서 뽑은 리그 평균 — 계수의 분모로 쓴다.

    실사고(2026-08-26): config의 `league_woba = 0.320`을 xwOBA의 분모로 썼는데
    실제 팀 xwOBA 평균은 **0.309**였다. 0.011 차이가 지수 1.2로 증폭돼
    **평균적인 팀도 계수 0.959배**를 받았고, 전 팀 타선이 일괄 −4% 하향됐다.
    그 결과 λ 합계가 리그 평균(8.80)보다 0.63점 낮아져 토탈이 언더로 쏠렸고,
    시장 대비 엣지가 ±26%까지 벌어져 엣지 가드에 대량 탈락했다.

    상수는 지표가 바뀌면 틀린다(wOBA용 상수를 xwOBA에 쓴 것이 이 사고다).
    **같은 데이터에서 계산한 평균**을 쓰면 이 종류의 불일치가 원천적으로 없다.
    """
    xs = [v["xwoba_30d"] for v in (offense or {}).values()
          if v.get("xwoba_30d") is not None]
    ps = [v["xwoba_allowed"] for v in (pitchers or {}).values()
          if v.get("xwoba_allowed") is not None and not v.get("low_sample")]
    out = {}
    if xs:
        out["xwoba"] = round(sum(xs) / len(xs), 4)
    if ps:
        out["xwoba_allowed"] = round(sum(ps) / len(ps), 4)
    return out


def aggregate_batters(df) -> dict[str, list[dict]]:
    """팀별 타자 랭킹 — 타석 수 내림차순. 결장자 '주전 여부' 판정의 기준.

    IL 명단만으로는 그 선수가 팀에 얼마나 중요한지 알 수 없다. 최근 30일
    타석 상위 9명이면 사실상 주전 라인업이므로, 그 안의 결장은 λ를 크게 움직인다.

    **선수 식별은 MLBAM id로 한다** — Statcast의 `player_name`은 투수 이름이라
    타자에는 쓸 수 없고, statsapi도 같은 id 체계를 쓰므로 이름 매칭보다 정확하다.
    반환: {팀: [{"id", "pa", "xwoba"}, ...]}
    """
    import pandas as pd

    if df is None or len(df) == 0 or "batter" not in df:
        return {}
    d = df.copy()
    d["team"] = d.apply(_team_of_batter, axis=1)
    d = d[d["team"].notna() & d["batter"].notna()]
    pa = d[d["events"].notna() & (d["events"] != "")]
    if pa.empty:
        return {}
    out: dict[str, list[dict]] = {}
    for team, g in pa.groupby("team"):
        rows = []
        for bid, gb in g.groupby("batter"):
            rows.append({"id": int(bid), "pa": int(len(gb)),
                         "xwoba": _round(_xwoba(gb, pd), 3)})
        rows.sort(key=lambda r: -r["pa"])
        out[str(team)] = rows[:20]      # 상위 20명이면 주전 판정에 충분하다
    return out


def aggregate_bullpen(df) -> dict[str, dict]:
    """팀별 불펜 최근 소모 — 최근 3경기 구원 투구 수와 과소모 여부.

    선발/구원 구분: 경기별로 그 팀의 **첫 투수**를 선발로 보고 나머지를 불펜으로 센다
    (Statcast에 선발 플래그가 없다). 키 `bp_pitches_3d`는 KBO 카드와 같은 자리.
    창은 달력 3일이 아니라 **최근 3경기**다.
    """
    import pandas as pd

    if df is None or len(df) == 0:
        return {}
    d = _with_fielding_team(df)
    if d is None or d.empty:
        return {}
    d["game_date"] = pd.to_datetime(d["game_date"], errors="coerce")
    # 경기·팀별 첫 등판 투수 = 선발
    order = (d.sort_values(["game_pk", "fld_team", "at_bat_number"])
             if "at_bat_number" in d else d.sort_values(["game_pk", "fld_team"]))
    first = order.groupby(["game_pk", "fld_team"])["pitcher"].first().rename("starter")
    j = order.join(first, on=["game_pk", "fld_team"])
    relief = j[j["pitcher"] != j["starter"]]
    if relief.empty:
        return {}
    per_game = (relief.groupby(["fld_team", "game_pk"])
                .agg(n=("pitcher", "size"), game_date=("game_date", "max"))
                .reset_index())
    per_game = per_game.sort_values(["fld_team", "game_date"],
                                    ascending=[True, False])
    last = per_game.groupby("fld_team").head(BULLPEN_RECENT_GAMES)
    counts = last.groupby("fld_team")["n"].sum()
    if counts.empty:
        return {}
    median = float(counts.median())
    out: dict[str, dict] = {}
    for team, n in counts.items():
        out[str(team)] = {
            "bp_pitches_3d": int(n),
            "bp_overused": bool(median > 0 and n >= median * BULLPEN_OVERUSE_RATIO),
        }
    return out


def starter_innings(df) -> dict[str, float]:
    """선발별 등판당 평균 이닝 — 불펜 노출 신호(`ip_avg_recent`).

    `_bullpen_factor`가 "상대 선발이 5이닝을 못 채우면 불펜 노출↑"에 쓴다.
    그동안 Perplexity 산문에서만 왔지만 Statcast 원본으로 계산할 수 있다.
    근사: 그 등판에서 던진 **서로 다른 이닝 수**(6이닝 선발은 1~6회에 등장).
    """
    import pandas as pd

    if df is None or len(df) == 0 or "inning" not in df:
        return {}
    d = _with_fielding_team(df)
    if d is None or d.empty:
        return {}
    order = (d.sort_values(["game_pk", "fld_team", "at_bat_number"])
             if "at_bat_number" in d else d.sort_values(["game_pk", "fld_team"]))
    first = order.groupby(["game_pk", "fld_team"])["pitcher"].first().rename("starter")
    j = order.join(first, on=["game_pk", "fld_team"])
    st = j[j["pitcher"] == j["starter"]]
    if st.empty:
        return {}
    per_start = st.groupby(["pitcher", "game_pk"])["inning"].nunique()
    avg = per_start.groupby("pitcher").mean()
    names = st.groupby("pitcher").apply(_pitcher_name, include_groups=False)
    out: dict[str, float] = {}
    for pid, ip in avg.items():
        nm = names.get(pid)
        if nm:
            out[str(nm)] = round(float(ip), 2)
    return out


def aggregate_pitchers(df, window_starts: int = 0) -> dict[str, dict]:
    """선발별 최근 지표 — 허용 xwOBA·평균 구속(피로 신호)·던진 손·최근 등판 수.

    표본 가드: 50투구 또는 3등판 미만이면 허용 xwOBA를 **리그 평균으로 대체**하고
    `low_sample` 플래그와 사유를 남긴다. 가드 없이 쓰면 1~2등판 투수의 잡음이
    그대로 λ에 들어가 상·하한을 때린다(실측: 0.012~1.010).
    """
    import pandas as pd

    if df is None or len(df) == 0:
        return {}
    d = df[df["pitcher"].notna()].copy()
    league = _xwoba(d, pd)          # 같은 구간의 리그 평균 — 대체값의 기준
    out: dict[str, dict] = {}
    for _pid, g_all in d.groupby("pitcher"):
        g = _tail_games(g_all, window_starts)
        name = _pitcher_name(g)
        if not name:
            continue
        games = g["game_pk"].nunique() if "game_pk" in g else 0
        pitches = len(g)
        recent = g.sort_values("game_date").tail(400)
        enough = pitches >= MIN_PITCHER_PITCHES or games >= MIN_PITCHER_APPEARANCES
        own = _xwoba(g, pd)
        stats = {
            "xwoba_allowed": _round(own if enough else league, 3),
            "velo_recent": _round(
                pd.to_numeric(recent["release_speed"], errors="coerce").mean(), 1),
            "velo_window": _round(
                pd.to_numeric(g["release_speed"], errors="coerce").mean(), 1),
            "appearances": int(games),
            "pitches": int(pitches),
        }
        if not enough:
            stats["low_sample"] = True
            stats["sample_note"] = LOW_SAMPLE_NOTE
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


MOCK_FIXTURE = pathlib.Path(__file__).resolve().parents[2] / "mock_data" / "statcast.json"


async def _refresh_from_fixture(redis, date: str) -> dict:
    """[P5-1] 무인증 목 모드 — baseballsavant 대신 픽스처를 캐시에 넣는다.

    🔴 픽스처는 **원본 CSV가 아니라 집계 결과**다. 원본 30일치는 12만 행이라
       저장소에 넣을 수 없고, 소비자(`load`·`merge_into_research`)가 읽는 것도
       집계뿐이다. 2026-08-22 기준 1회 캡처(122,016행 → 팀 29·투수 556).

    `refresh`와 **같은 키·같은 TTL**로 쓴다. 그래야 `load` 이후의 경로
    (폴백·병합·λ 산출)가 실제와 같은 모양으로 돌아간다 — 여기서 모양이
    갈라지면 목이 지켜주는 것이 없다.
    """
    import json

    if not MOCK_FIXTURE.exists():
        logger.warning("[statcast] 목 모드지만 픽스처가 없다 (%s) — 빈 결과",
                       MOCK_FIXTURE)
        return {"ok": False, "error": "fixture missing", "mock": True}
    payloads = json.loads(MOCK_FIXTURE.read_text(encoding="utf-8"))
    for kind in ("offense", "pitchers", "bullpen", "batters", "league"):
        await redis.set(_key(kind, date),
                        json.dumps(payloads.get(kind) or {}, ensure_ascii=False),
                        ex=CACHE_TTL)
    logger.info("[statcast] %s 목 픽스처 적재 — 팀 %d개, 투수 %d명",
                date, len(payloads.get("offense") or {}),
                len(payloads.get("pitchers") or {}))
    return {"ok": True, "mock": True,
            "teams": len(payloads.get("offense") or {}),
            "pitchers": len(payloads.get("pitchers") or {}),
            "bullpen": len(payloads.get("bullpen") or {}), "rows": 0}


async def refresh(redis, date: str | None = None) -> dict:
    """일 1회 갱신 — 팀 타선·투수 지표를 계산해 Redis에 저장. 반환: 요약."""
    import json

    from app.config import get_settings as _gs
    from app.pipeline import mlb_slate_date

    date = date or mlb_slate_date()
    # [P5-1] baseballsavant는 무인증이라 FORCE_MOCK이 걸리지 않았고, 테스트가
    #        30일치 원본을 실제로 받아 3파일이 사실상 실행 불가였다.
    if _gs().mock_freesource:
        return await _refresh_from_fixture(redis, date)
    end = dt.date.fromisoformat(date)
    start = end - dt.timedelta(days=WINDOW_DAYS)
    try:
        df = await asyncio.to_thread(_fetch_statcast, str(start), str(end))
    except Exception as exc:
        logger.error("[statcast] 수집 실패 %s~%s: %s", start, end, exc)
        return {"ok": False, "error": str(exc)[:200]}

    # [§8-6] 원본은 30일치를 받되 **집계는 최근 N경기로 자른다.**
    #        30일을 받는 이유: 15경기(≈17일)를 담고도 휴식일·우천취소 여유가 필요하다.

    _s = get_settings()
    offense = aggregate_team_offense(df, window_games=_s.recent_window_games)
    pitchers = aggregate_pitchers(df, window_starts=_s.recent_window_starts)
    bullpen = aggregate_bullpen(df)
    for name, ip in starter_innings(df).items():
        if name in pitchers:
            pitchers[name]["ip_avg_recent"] = ip
    batters = aggregate_batters(df)
    baselines = league_baselines(offense, pitchers)
    for kind, payload in (("offense", offense), ("pitchers", pitchers),
                          ("bullpen", bullpen), ("batters", batters),
                          ("league", baselines)):
        await redis.set(_key(kind, date), json.dumps(payload, ensure_ascii=False),
                        ex=CACHE_TTL)
    # 🔴 [STC-1] **버렸다는 사실을 남긴다.** 원본 팀코드와 집계 결과를 대사해
    #    매핑이 어긋나면 로그 + 워치독으로 시끄럽게 알린다.
    seen = set()
    for col in ("home_team", "away_team"):
        if col in df.columns:
            seen |= {str(x) for x in df[col].dropna().unique()}
    gaps = audit_team_coverage(seen, set(offense))
    await _alert_coverage(gaps)
    logger.info("[statcast] %s 갱신 — 팀 %d/%d, 투수 %d명, 불펜 %d팀 (원본 %d행)",
                date, len(offense), MLB_TEAM_COUNT, len(pitchers), len(bullpen), len(df))
    return {"ok": True, "teams": len(offense), "pitchers": len(pitchers),
            "bullpen": len(bullpen), "rows": len(df)}


# 당일 키가 없을 때 거슬러 올라갈 최대 일수. 30일 누적 지표라 하루이틀 차이는
# 무의미하지만, 오래된 값을 쓰면 최근 폼을 놓치므로 3일로 제한한다.
STALE_FALLBACK_DAYS = 3


async def load(redis, date: str | None = None) -> tuple[dict, dict, dict, dict, dict]:
    """캐시된 (팀 타선, 투수 지표). 없으면 빈 dict — 모델은 해당 보정을 건너뛴다.

    당일 키가 없으면 최근 STALE_FALLBACK_DAYS일 안의 키로 폴백한다.
    실사고(2026-08-25): 03:30 갱신 잡이 돌지 않아 당일 키가 없었고,
    폴백이 없어 15경기 **전부** λ 산출에 실패했다. 30일 누적 지표이므로
    하루 지난 값이 값 없음보다 훨씬 낫다.
    """
    import json
    from datetime import datetime, timedelta

    from app.pipeline import mlb_slate_date

    date = date or mlb_slate_date()
    base = datetime.strptime(date, "%Y-%m-%d")
    for back in range(STALE_FALLBACK_DAYS + 1):
        day = (base - timedelta(days=back)).strftime("%Y-%m-%d")
        raws = [await redis.get(_key(kind, day))
                for kind in ("offense", "pitchers", "bullpen", "batters", "league")]
        if not any(raws):
            continue
        if back:
            logger.warning("[statcast] %s 캐시 없음 — %s 캐시로 폴백(%d일 전). "
                           "03:30 갱신 잡 점검 필요", date, day, back)
        return tuple(json.loads(x) if x else {} for x in raws)
    logger.warning("[statcast] %s 기준 최근 %d일 캐시가 모두 없다 — λ 산출 불가",
                   date, STALE_FALLBACK_DAYS)
    return {}, {}, {}, {}, {}


def merge_into_research(research: dict, jg: dict, offense: dict, pitchers: dict,
                        bullpen: dict | None = None,
                        parks: dict | None = None,
                        baselines: dict | None = None) -> list[str]:
    """Statcast 지표를 리서치 페이로드에 얹는다. 반환: 실제로 채운 항목.

    리서치가 이미 채운 값은 덮지 않는다(setdefault) — 수집 실패 항목만 메운다.
    """
    filled: list[str] = []
    # 계수의 분모 — 상수 대신 같은 데이터셋의 리그 평균을 쓴다
    if baselines and not research.get("league_baselines"):
        research["league_baselines"] = baselines
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
    # [§2] 불펜 소모 — _bullpen_factor는 research["bullpen_overused"]를 '홈'/'원정'으로 읽는다
    if bullpen and research.get("bullpen_overused") is None:
        pair = [(label, (bullpen.get(jg.get(k)) or {}))
                for label, k in (("홈", "home"), ("원정", "away"))]
        over = [(label, b) for label, b in pair if b.get("bp_overused")]
        if len(over) == 1:   # 양쪽 다 과소모면 상대적 이점이 없다 → 표기하지 않는다
            research["bullpen_overused"] = over[0][0]
            filled.append(f"불펜 과소모 {over[0][0]} ({over[0][1]['bp_pitches_3d']}구/3경기)")
    # [§2] 파크팩터 — statsapi 기반 자체 산출값
    if parks:
        from app.collectors.park import merge_into_research as merge_park

        note = merge_park(research, jg, parks)
        if note:
            filled.append(note)
    return filled


def enrich_mlb_research(research: dict, jg: dict, ctx: dict) -> list[str]:
    """[§2] 정식 API 입력을 리서치 페이로드에 한 번에 얹는다.

    ctx: {"offense","pitchers","bullpen","batters","parks","weather","absences"}
    리서치(Perplexity)가 이미 채운 값은 어느 항목도 덮지 않는다 — 이 함수는
    **수집 실패 항목을 메우는** 역할이지 리서치를 대체하는 게 아니다.
    """
    from app.collectors.absences import merge_into_research as merge_absences
    from app.collectors.weather import merge_into_research as merge_weather

    filled = merge_into_research(
        research, jg,
        ctx.get("offense") or {}, ctx.get("pitchers") or {},
        ctx.get("bullpen") or {}, ctx.get("parks") or {},
        ctx.get("league") or {},
    )
    note = merge_weather(research, jg, ctx.get("weather") or {})
    if note:
        filled.append(note)
    gid = jg.get("game_id")
    info = (ctx.get("absences") or {}).get(gid) or {}
    note = merge_absences(research, jg, ctx.get("batters") or {},
                          info.get("lineup"), info.get("injured"))
    if note:
        filled.append(note)
    return filled
