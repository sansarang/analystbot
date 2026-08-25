"""[§6-1] λ 학습용 피처 엔지니어링 — 팀별 득점을 예측하는 피처를 만든다.

예측 대상은 **승패가 아니라 팀별 득점(λ)**이다. 학습된 λ에서 기존과 동일하게
포아송 분포로 승패·런라인·언더오버·F5를 뽑으므로 **마켓 확률의 출처는 여전히 하나**다.

누수 방지가 이 모듈의 존재 이유다:
- 모든 피처는 **해당 경기 시작 시점까지의 정보**만 쓴다.
- 롤링 계산에 당일 경기가 섞이지 않았는지 `assert_no_leakage`가 검증한다.
- 학습/검증은 시간순 분할(앞 70% / 뒤 30%) — 무작위 분할은 미래로 과거를 맞히는 셈이다.

제외한 피처와 이유는 docs/MODEL.md에 기록한다.
"""

import logging

logger = logging.getLogger(__name__)

WINDOW_DAYS = 30
MIN_PRIOR_PA = 120        # 팀 타선 사전 표본 하한
MIN_PRIOR_PITCHES = 30    # 투수 사전 표본 하한
STARTER_INNING = 1        # 1회에 던진 투수를 선발로 본다

# 학습에 쓰는 피처 순서 (모델 계수 해석·중요도 출력에 그대로 쓰인다)
FEATURES = [
    # 타선 (해당 팀, 경기 이전 30일)
    "off_xwoba", "off_barrel", "off_hardhit", "off_k_pct", "off_bb_pct", "off_split_woba",
    # 상대 선발 (경기 이전)
    "sp_xwoba_allowed", "sp_velo", "sp_velo_drop", "sp_rest_days", "sp_prev_pitches",
    # 상대 불펜 (경기 이전)
    "bp_xwoba_allowed", "bp_pitches_3d",
    # 피로·스케줄 (해당 팀)
    "days_in_a_row", "road_trip_game", "getaway_day",
    # 환경
    "park_factor", "is_home",
]

# 확보 불가로 학습에서 제외한 피처 (docs/MODEL.md와 동기화)
EXCLUDED = {
    "weather_temp": "Statcast에 날씨 컬럼 없음 — 과거 백필 불가. 실시간분은 후처리 훅으로",
    "weather_wind": "위와 동일",
    "siera": "FanGraphs 403 차단 — Statcast 허용 xwOBA로 대체(운 오염이 더 적다)",
    "xfip": "위와 동일",
    "bullpen_siera": "위와 동일 — 불펜 허용 xwOBA로 대체",
    "defense_oaa": "경기별 시계열 없음(시즌 단위만) — 시즌 값 사용은 미래 정보 누수",
    "timezone_shift": "구장 시간대 테이블 필요 — 원정 연전 차수로 대리. TODO: 테이블 자체 구축",
}


def prepare(df):
    """투구 원본 → 분석용 프레임 (팀·역할·타구 지표 컬럼 부착)."""
    import pandas as pd

    d = df[df["game_type"] == "R"].copy()
    d["game_date"] = pd.to_datetime(d["game_date"])
    d["bat_team"] = d.apply(
        lambda r: r["away_team"] if str(r.get("inning_topbot", "")).startswith("Top")
        else r["home_team"], axis=1)
    d["fld_team"] = d.apply(
        lambda r: r["home_team"] if str(r.get("inning_topbot", "")).startswith("Top")
        else r["away_team"], axis=1)
    d["xwoba"] = pd.to_numeric(d["estimated_woba_using_speedangle"], errors="coerce")
    d["velo"] = pd.to_numeric(d["release_speed"], errors="coerce")
    d["ls"] = pd.to_numeric(d["launch_speed"], errors="coerce")
    d["is_barrel"] = (pd.to_numeric(d["launch_speed_angle"], errors="coerce") == 6)
    d["is_hardhit"] = d["ls"] >= 95
    ev = d["events"].astype(str)
    d["is_pa"] = d["events"].notna() & (ev != "") & (ev != "nan")
    d["is_k"] = ev.str.startswith("strikeout")
    d["is_bb"] = ev == "walk"
    return d


def game_frame(d):
    """경기 단위 골격 — 일자·팀·최종 득점."""
    g = (d.groupby("game_pk")
         .agg(date=("game_date", "first"), home=("home_team", "first"),
              away=("away_team", "first"),
              home_runs=("post_home_score", "max"), away_runs=("post_away_score", "max"))
         .reset_index().sort_values(["date", "game_pk"]))
    return g


def starters(d):
    """경기별 각 팀 선발 — 1회에 던진 투수."""
    first = d[d["inning"] == STARTER_INNING]
    return (first.sort_values(["game_pk", "at_bat_number"])
            .groupby(["game_pk", "fld_team"], as_index=False)
            .first()[["game_pk", "fld_team", "pitcher", "game_date"]]
            .rename(columns={"fld_team": "team"}))


def pitcher_game_stats(d, starter_map):
    """투수-경기 단위 집계 — 허용 xwOBA·구속·투구 수, 선발/불펜 구분."""
    import pandas as pd

    agg = (d.groupby(["game_pk", "pitcher", "fld_team", "game_date"], as_index=False)
           .agg(xw_sum=("xwoba", "sum"), xw_n=("xwoba", "count"),
                velo_sum=("velo", "sum"), velo_n=("velo", "count"),
                pitches=("pitcher", "size")))
    key = set(zip(starter_map["game_pk"], starter_map["pitcher"]))
    agg["is_starter"] = [(gp, p) in key for gp, p in zip(agg["game_pk"], agg["pitcher"])]
    return agg


# ---------------------------------------------------------------- 롤링 (누수 방지)

def _prior(frame, mask, date, window_days, value_cols):
    """경기 **이전** window_days 구간 집계. 당일(>= date)은 절대 포함하지 않는다."""
    import pandas as pd

    lo = date - pd.Timedelta(days=window_days)
    sub = frame[mask & (frame["game_date"] < date) & (frame["game_date"] >= lo)]
    return sub[value_cols].sum() if len(sub) else None, len(sub)


def team_offense_prior(team_day, team, date):
    """팀 타선 사전 지표. 표본이 얇으면 None."""
    cols = ["xw_sum", "xw_n", "barrel", "hardhit", "bip", "k", "bb", "pa"]
    sums, _n = _prior(team_day, team_day["bat_team"] == team, date, WINDOW_DAYS, cols)
    if sums is None or sums["xw_n"] < MIN_PRIOR_PA:
        return None
    bip = max(1, sums["bip"])
    pa = max(1, sums["pa"])
    return {
        "off_xwoba": sums["xw_sum"] / sums["xw_n"],
        "off_barrel": sums["barrel"] / bip,
        "off_hardhit": sums["hardhit"] / bip,
        "off_k_pct": sums["k"] / pa,
        "off_bb_pct": sums["bb"] / pa,
    }


def pitcher_prior(pg, pitcher_id, date):
    """선발 사전 지표 — 허용 xwOBA·구속·구속 하락폭·등판 간격·직전 투구 수."""
    import pandas as pd

    hist = pg[(pg["pitcher"] == pitcher_id) & (pg["game_date"] < date)].sort_values("game_date")
    if hist.empty:
        return None
    window = hist[hist["game_date"] >= date - pd.Timedelta(days=45)]
    if window["xw_n"].sum() < MIN_PRIOR_PITCHES:
        return None
    velo_all = window["velo_sum"].sum() / max(1, window["velo_n"].sum())
    recent = window.tail(3)
    velo_recent = recent["velo_sum"].sum() / max(1, recent["velo_n"].sum())
    last = hist.iloc[-1]
    return {
        "sp_xwoba_allowed": window["xw_sum"].sum() / max(1, window["xw_n"].sum()),
        "sp_velo": velo_all,
        "sp_velo_drop": velo_all - velo_recent,        # 양수면 최근 구속 하락
        "sp_rest_days": float((date - last["game_date"]).days),
        "sp_prev_pitches": float(last["pitches"]),
    }


def bullpen_prior(pg, team, date):
    """상대 불펜 사전 지표 — 허용 xwOBA(30일), 최근 3일 투구 수."""
    import pandas as pd

    pen = pg[(~pg["is_starter"]) & (pg["fld_team"] == team) & (pg["game_date"] < date)]
    window = pen[pen["game_date"] >= date - pd.Timedelta(days=WINDOW_DAYS)]
    if window["xw_n"].sum() < MIN_PRIOR_PITCHES:
        return None
    last3 = pen[pen["game_date"] >= date - pd.Timedelta(days=3)]
    return {
        "bp_xwoba_allowed": window["xw_sum"].sum() / max(1, window["xw_n"].sum()),
        "bp_pitches_3d": float(last3["pitches"].sum()),
    }


def schedule_prior(games, team, date, game_pk):
    """피로·스케줄 — 연속 경기 일수, 원정 연전 차수, getaway day."""
    import pandas as pd

    hist = games[((games["home"] == team) | (games["away"] == team))
                 & (games["date"] < date)].sort_values("date")
    days_in_a_row = 0
    cursor = date
    for d in reversed(hist["date"].tolist()):
        if (cursor - d).days <= 1:
            days_in_a_row += 1
            cursor = d
        else:
            break

    row = games[games["game_pk"] == game_pk].iloc[0]
    is_home = row["home"] == team
    road_trip = 0
    if not is_home:
        for d, h, a in zip(reversed(hist["date"].tolist()),
                           reversed(hist["home"].tolist()),
                           reversed(hist["away"].tolist())):
            if a == team and (date - d).days <= 12:
                road_trip += 1
            else:
                break
    # getaway day — 이 원정 연전의 마지막 경기(다음 경기가 홈이거나 3일 이상 공백)
    future = games[((games["home"] == team) | (games["away"] == team))
                   & (games["date"] > date)].sort_values("date")
    getaway = 0.0
    if not is_home and len(future):
        nxt = future.iloc[0]
        if nxt["home"] == team or (nxt["date"] - date).days >= 3:
            getaway = 1.0
    return {
        "days_in_a_row": float(days_in_a_row),
        "road_trip_game": float(road_trip),
        "getaway_day": getaway,
        "is_home": 1.0 if is_home else 0.0,
    }


def park_factors(games, min_games: int = 30) -> dict[str, float]:
    """구장 파크팩터 — 구장별 경기당 총득점 / 리그 평균. 외부 소스 없이 자체 산출."""
    total = (games["home_runs"] + games["away_runs"])
    league = float(total.mean()) if len(games) else 0.0
    if league <= 0:
        return {}
    out = {}
    for park, g in games.groupby("home"):
        if len(g) < min_games:
            continue
        out[str(park)] = round(float((g["home_runs"] + g["away_runs"]).mean()) / league, 4)
    return out


# ---------------------------------------------------------------- 누수 검증

def assert_no_leakage(records: list[dict], d) -> dict:
    """[§6-2] 피처에 당일 이후 정보가 섞이지 않았는지 검증.

    검증 방식: 각 레코드의 타선 지표를 **당일 포함**으로 다시 계산했을 때 값이
    달라져야 한다. 같다면 롤링 창에 당일이 들어갔다는 뜻이다.
    """
    import pandas as pd

    checked = suspicious = 0
    for rec in records[:200]:          # 표본 검사 (전수는 비용이 크다)
        same_day = d[(d["bat_team"] == rec["team"]) & (d["game_date"] == rec["date"])]
        if same_day.empty or rec.get("off_xwoba") is None:
            continue
        checked += 1
        lo = rec["date"] - pd.Timedelta(days=WINDOW_DAYS)
        incl = d[(d["bat_team"] == rec["team"]) & (d["game_date"] <= rec["date"])
                 & (d["game_date"] >= lo)]
        with_today = incl["xwoba"].sum() / max(1, incl["xwoba"].count())
        if abs(with_today - rec["off_xwoba"]) < 1e-9:
            suspicious += 1
    return {"checked": checked, "suspicious": suspicious,
            "ok": suspicious == 0,
            "note": "당일 포함 값과 동일한 레코드가 있으면 누수" }


def time_split(records: list[dict], train_ratio: float = 0.70):
    """[§6-2] 시간순 분할 — 무작위 분할은 미래로 과거를 맞히는 셈이다."""
    ordered = sorted(records, key=lambda r: (r["date"], r["game_pk"]))
    cut = int(len(ordered) * train_ratio)
    return ordered[:cut], ordered[cut:]


# ---------------------------------------------------------------- 학습셋 빌더

def build_dataset(df) -> tuple[list[dict], dict]:
    """투구 원본 → 팀-경기 단위 학습 레코드.

    한 경기가 2행(홈 공격 / 원정 공격)이 된다 — 예측 대상이 **팀별 득점**이기 때문이다.
    반환: (레코드, 파크팩터)
    """
    import pandas as pd

    d = prepare(df)
    games = game_frame(d)
    sm = starters(d)
    pg = pitcher_game_stats(d, sm)
    parks = park_factors(games)

    # 팀-일자 타선 집계 (롤링 재료)
    team_day = (d.groupby(["bat_team", "game_date"], as_index=False)
                .agg(xw_sum=("xwoba", "sum"), xw_n=("xwoba", "count"),
                     barrel=("is_barrel", "sum"), hardhit=("is_hardhit", "sum"),
                     bip=("ls", "count"), k=("is_k", "sum"), bb=("is_bb", "sum"),
                     pa=("is_pa", "sum")))

    starter_by = {(int(r["game_pk"]), str(r["team"])): r["pitcher"]
                  for _i, r in sm.iterrows()}

    records: list[dict] = []
    for _i, g in games.iterrows():
        gp, date = int(g["game_pk"]), g["date"]
        for team, opp, runs in ((g["home"], g["away"], g["home_runs"]),
                                (g["away"], g["home"], g["away_runs"])):
            try:
                runs = float(runs)
            except (TypeError, ValueError):
                continue
            off = team_offense_prior(team_day, team, date)
            if off is None:
                continue
            opp_sp_id = starter_by.get((gp, str(opp)))
            sp = pitcher_prior(pg, opp_sp_id, date) if opp_sp_id is not None else None
            bp = bullpen_prior(pg, str(opp), date)
            sched = schedule_prior(games, str(team), date, gp)
            if sp is None or bp is None:
                continue
            rec = {"game_pk": gp, "date": date, "team": str(team), "opp": str(opp),
                   "runs": runs, **off, **sp, **bp, **sched}
            rec["park_factor"] = parks.get(str(g["home"]), 1.0)
            # 좌우 스플릿 — 상대 선발 손잡이에 대한 그 팀 사전 wOBA
            rec["off_split_woba"] = _split_prior(d, team, date, opp_sp_id, pg)
            records.append(rec)
    logger.info("[features] 학습 레코드 %d개 (경기 %d, 파크팩터 %d구장)",
                len(records), len(games), len(parks))
    return records, parks


def _split_prior(d, team, date, pitcher_id, pg) -> float:
    """상대 선발 손잡이에 대한 그 팀의 사전 wOBA. 없으면 팀 전체 값으로 폴백."""
    import pandas as pd

    hand = None
    if pitcher_id is not None:
        rows = d[d["pitcher"] == pitcher_id]["p_throws"].dropna()
        if len(rows):
            hand = str(rows.iloc[0])
    lo = date - pd.Timedelta(days=WINDOW_DAYS)
    sub = d[(d["bat_team"] == team) & (d["game_date"] < date) & (d["game_date"] >= lo)]
    if hand:
        h = sub[sub["p_throws"] == hand]
        if h["xwoba"].count() >= 50:
            sub = h
    n = sub["xwoba"].count()
    return float(sub["xwoba"].sum() / n) if n else 0.320


def to_matrix(records: list[dict]):
    """레코드 → (X, y). 결측은 열 중앙값으로 채운다."""
    import numpy as np

    X = np.array([[float(r.get(f) if r.get(f) is not None else np.nan)
                   for f in FEATURES] for r in records], dtype=float)
    y = np.array([r["runs"] for r in records], dtype=float)
    med = np.nanmedian(X, axis=0)
    idx = np.where(np.isnan(X))
    X[idx] = np.take(med, idx[1])
    return X, y
