"""[§6] λ 모델 계수 학습 — 임의값을 데이터로 교체한다.

문제: 현재 계수(exp_offense 1.20, exp_pitcher 0.50, home_run_edge 0.03 …)는
근거 있는 것이 *변수 중요도 순서*와 *상한값*뿐이고 숫자 자체는 임의값이다.
docs/MODEL.md §9가 이 사실을 명시하고 있다.

방법:
1. Statcast 과거 경기로 학습셋을 만든다 — 각 경기의 **경기 이전** 30일 팀 지표와
   선발 지표, 그리고 실제 결과. (경기 당일 데이터를 쓰면 미래 정보 누수다)
2. 우리 λ 모델을 그 피처로 돌려 홈 승리 확률을 산출한다.
3. Brier score를 최소화하도록 계수를 탐색한다.
4. 학습 전후 Brier·캘리브레이션을 비교한다 — **좋아지지 않으면 채택하지 않는다.**

계수 변경은 DISCIPLINE 5-1 대상이다: 전후 값·이유·영향을 반드시 보고한다.
"""

import json
import logging
import pathlib
from dataclasses import dataclass, replace

logger = logging.getLogger(__name__)

ARTIFACT = pathlib.Path("data/lambda_coefficients.json")
MIN_PRIOR_PA = 120        # 이보다 표본이 얇은 팀-경기는 학습에서 제외
MIN_GAMES = 200           # 이보다 적으면 학습하지 않는다 (과적합 방지)


@dataclass(frozen=True)
class Coefficients:
    """학습 대상 계수. config 기본값에서 시작한다."""

    exp_offense: float
    exp_pitcher: float
    home_run_edge: float
    league_runs_per_game: float

    @classmethod
    def from_settings(cls, s) -> "Coefficients":
        return cls(s.exp_offense, s.exp_pitcher, s.home_run_edge, s.league_runs_per_game)

    def as_dict(self) -> dict:
        return {"exp_offense": round(self.exp_offense, 4),
                "exp_pitcher": round(self.exp_pitcher, 4),
                "home_run_edge": round(self.home_run_edge, 4),
                "league_runs_per_game": round(self.league_runs_per_game, 3)}


# ---------------------------------------------------------------- 학습셋

def build_training_set(df, window_days: int = 30) -> list[dict]:
    """투구 원본 → 경기별 (사전 지표, 결과) 레코드.

    **경기 이전** 데이터만 쓴다 — 당일 타석을 포함하면 결과를 미리 아는 셈이 된다.
    """
    import pandas as pd

    if df is None or len(df) == 0:
        return []
    d = df[df["game_type"] == "R"].copy()
    d["game_date"] = pd.to_datetime(d["game_date"])
    d["bat_team"] = d.apply(
        lambda r: r["away_team"] if str(r.get("inning_topbot", "")).startswith("Top")
        else r["home_team"], axis=1)
    d["xwoba"] = pd.to_numeric(d["estimated_woba_using_speedangle"], errors="coerce")

    games = (d.groupby("game_pk")
             .agg(date=("game_date", "first"), home=("home_team", "first"),
                  away=("away_team", "first"),
                  hs=("post_home_score", "max"), as_=("post_away_score", "max"))
             .reset_index().sort_values("date"))

    # 팀-일자 단위 타석 집계 (rolling의 재료)
    team_day = (d.groupby(["bat_team", "game_date"])
                .agg(xwoba_sum=("xwoba", "sum"), xwoba_n=("xwoba", "count"))
                .reset_index())
    # 선발(각 경기 첫 투수)의 허용 xwOBA
    starters = _starter_frame(d)

    out: list[dict] = []
    for _i, g in games.iterrows():
        rec = {"game_pk": int(g["game_pk"]), "date": g["date"],
               "home": str(g["home"]), "away": str(g["away"])}
        try:
            rec["home_win"] = 1 if float(g["hs"]) > float(g["as_"]) else 0
        except (TypeError, ValueError):
            continue
        if float(g["hs"]) == float(g["as_"]):
            continue                      # 무승부(서스펜디드)는 제외
        ok = True
        for side in ("home", "away"):
            woba, n = _prior_xwoba(team_day, rec[side], g["date"], window_days)
            if woba is None or n < MIN_PRIOR_PA:
                ok = False
                break
            rec[f"{side}_xwoba"] = woba
            rec[f"{side}_starter_xwoba"] = _prior_starter(
                starters, int(g["game_pk"]), rec[side], g["date"], window_days)
        if ok:
            out.append(rec)
    logger.info("[calibrate] 학습셋 %d경기 (원본 %d경기)", len(out), len(games))
    return out


def _starter_frame(d):
    """경기별 각 팀 선발과 그 투구의 허용 xwOBA."""
    import pandas as pd

    first = (d.sort_values(["game_pk", "inning", "at_bat_number"])
             .groupby(["game_pk", "bat_team"], as_index=False).first()
             [["game_pk", "bat_team", "pitcher", "game_date"]])
    first = first.rename(columns={"bat_team": "opp_bat_team"})
    allowed = (d.groupby(["game_pk", "pitcher", "game_date"], as_index=False)
               .agg(xwoba_sum=("xwoba", "sum"), xwoba_n=("xwoba", "count")))
    return pd.merge(first, allowed, on=["game_pk", "pitcher", "game_date"], how="left")


def _prior_xwoba(team_day, team: str, date, window_days: int):
    """경기 **이전** window_days간 그 팀 타선의 xwOBA (누수 방지)."""
    import pandas as pd

    lo = date - pd.Timedelta(days=window_days)
    sub = team_day[(team_day["bat_team"] == team)
                   & (team_day["game_date"] < date)
                   & (team_day["game_date"] >= lo)]
    n = int(sub["xwoba_n"].sum())
    if n == 0:
        return None, 0
    return round(float(sub["xwoba_sum"].sum()) / n, 4), n


def _prior_starter(starters, game_pk: int, team: str, date, window_days: int):
    """이 경기에서 그 팀을 상대할 선발의 **이전** 허용 xwOBA. 없으면 None."""
    import pandas as pd

    row = starters[(starters["game_pk"] == game_pk) & (starters["opp_bat_team"] == team)]
    if row.empty or pd.isna(row.iloc[0]["pitcher"]):
        return None
    pid = row.iloc[0]["pitcher"]
    lo = date - pd.Timedelta(days=window_days)
    hist = starters[(starters["pitcher"] == pid)
                    & (starters["game_date"] < date)
                    & (starters["game_date"] >= lo)]
    n = float(hist["xwoba_n"].sum())
    if n < 30:
        return None
    return round(float(hist["xwoba_sum"].sum()) / n, 4)


# ---------------------------------------------------------------- 모델 적용·평가

def predict(rec: dict, coef: Coefficients, s) -> float:
    """학습셋 1건 → 홈 승리 확률 (현행 λ 모델과 같은 구조)."""
    from app.engine.scoring import cap_probability, mlb_market_probs

    lam = {}
    for side, opp in (("home", "away"), ("away", "home")):
        val = coef.league_runs_per_game
        val *= _clamp((rec[f"{side}_xwoba"] / s.league_woba) ** coef.exp_offense,
                      s.off_coef_min, s.off_coef_max)
        opp_sp = rec.get(f"{opp}_starter_xwoba")
        if opp_sp:
            val *= _clamp((opp_sp / s.league_woba) ** coef.exp_pitcher,
                          s.pit_coef_min, s.pit_coef_max)
        lam[side] = _clamp(val, s.lam_min, s.lam_max)
    lam["home"] *= 1 + coef.home_run_edge
    probs = mlb_market_probs(lam["home"], lam["away"], settings=s)
    return cap_probability(probs["h2h"]["home"], "mlb", s)[0]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def evaluate(records: list[dict], coef: Coefficients, s) -> dict:
    """Brier + 캘리브레이션 + 방향 적중률."""
    from app.grader import brier_score, calibration_bands

    rows = [{"model_p": predict(r, coef, s),
             "result": "win" if r["home_win"] else "loss"} for r in records]
    hits = sum(1 for r in rows if (r["model_p"] >= 0.5) == (r["result"] == "win"))
    return {
        "n": len(rows),
        "brier": brier_score(rows),
        "accuracy": round(hits / len(rows), 4) if rows else None,
        "calibration": calibration_bands(rows),
    }


# ---------------------------------------------------------------- 탐색

SEARCH_GRID = {
    "exp_offense": (0.6, 0.9, 1.2, 1.5, 1.8, 2.2),
    "exp_pitcher": (0.2, 0.35, 0.5, 0.7, 0.9),
    "home_run_edge": (0.00, 0.02, 0.03, 0.05, 0.07),
}


def fit(records: list[dict], s, base: Coefficients | None = None) -> dict:
    """좌표 하강으로 Brier를 최소화하는 계수를 찾는다.

    전 조합 탐색(6×5×5=150)은 학습셋이 작을 때 과적합 위험이 있어,
    한 축씩 순차 개선하고 개선이 멈추면 종료한다.
    """
    if len(records) < MIN_GAMES:
        return {"ok": False, "reason": f"학습셋 {len(records)}경기 < 최소 {MIN_GAMES}경기"}

    base = base or Coefficients.from_settings(s)
    before = evaluate(records, base, s)
    best, best_brier = base, before["brier"]

    for _round in range(3):
        improved = False
        for field, grid in SEARCH_GRID.items():
            for value in grid:
                cand = replace(best, **{field: value})
                brier = evaluate(records, cand, s)["brier"]
                if brier is not None and brier < best_brier - 1e-5:
                    best, best_brier, improved = cand, brier, True
        if not improved:
            break

    after = evaluate(records, best, s)
    return {
        "ok": True, "before": before, "after": after,
        "coefficients_before": base.as_dict(), "coefficients_after": best.as_dict(),
        "improved": bool(after["brier"] is not None and before["brier"] is not None
                         and after["brier"] < before["brier"]),
    }


def save(result: dict, path: pathlib.Path = ARTIFACT) -> None:
    """학습 결과 저장 — **개선됐을 때만** 채택한다."""
    if not result.get("ok") or not result.get("improved"):
        logger.warning("[calibrate] 개선 없음 — 계수를 채택하지 않는다: %s",
                       result.get("reason") or "brier 미개선")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    logger.info("[calibrate] 계수 저장 %s — Brier %.4f → %.4f",
                path, result["before"]["brier"], result["after"]["brier"])


def load_learned(path: pathlib.Path = ARTIFACT) -> dict | None:
    """저장된 학습 계수. 없으면 None(=config 기본값 사용)."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text()).get("coefficients_after")
    except (ValueError, OSError):
        return None
