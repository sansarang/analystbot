"""축구 Elo 모델 — football-data.co.uk 무료 CSV 기반 (API 키 불필요).

- 메이저 리그(시즌 파일) + Extra 리그(덴마크 DNK·일본 JPN 단일 파일) 다운로드·파싱
- 리그별 Elo(K=20) + 홈 어드밴티지, ordered-logit 컷포인트로 승/무/패 확률 산출
- 학습(과거 시즌)에서 (HA, c1, c2) 그리드 피팅, 최근 2시즌 walk-forward 백테스트
  (Brier score + 캘리브레이션 표, CSV의 마감 배당 디빅 확률을 벤치마크로 병기)
- 아티팩트(data/elo/*.json) 저장 → 파이프라인은 로드만 (주 1회 스케줄러가 refresh)

CLI: python -m app.models.soccer_elo --refresh [--backtest]
"""

import argparse
import csv
import json
import logging
import math
import pathlib
from collections import defaultdict
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "elo"
CSV_DIR = DATA_DIR / "csv"
RATINGS_FILE = DATA_DIR / "ratings.json"
PARAMS_FILE = DATA_DIR / "params.json"

BASE = "https://www.football-data.co.uk"
MAIN_LEAGUES = ["E0", "E1", "D1", "SP1", "I1", "F1", "N1", "P1"]
MAIN_SEASONS = ["2223", "2324", "2425", "2526"]
EXTRA_LEAGUES = ["DNK", "JPN"]

# games.league 라벨 → CSV 코드 (부분 문자열 매칭)
LABEL_TO_CODE = [
    ("premier league", "E0"), ("epl", "E0"), ("championship", "E1"),
    ("bundesliga", "D1"), ("primera", "SP1"), ("la liga", "SP1"),
    ("serie a", "I1"), ("ligue 1", "F1"), ("eredivisie", "N1"),
    ("primeira", "P1"), ("j1", "JPN"), ("j리그", "JPN"), ("japan", "JPN"),
    ("덴마크", "DNK"), ("superliga", "DNK"), ("denmark", "DNK"),
]

K_FACTOR = 20.0
# 🔴 [C7 2026-09-07] ELO 커널을 `elo_core` 로 뽑았다 — 야구 자료12 가 같은
#    식을 쓴다. 여기서 다시 정의하지 않는다(사본 금지).
from app.models.elo_core import LOG10, replay, sigmoid as _sigmoid  # noqa: E402

# 배당 컬럼 우선순위 (마감가 → 평균가 → 개장가)
ODDS_COLS = [
    ("PSCH", "PSCD", "PSCA"), ("AvgCH", "AvgCD", "AvgCA"), ("B365CH", "B365CD", "B365CA"),
    ("PH", "PD", "PA"), ("PSH", "PSD", "PSA"), ("AvgH", "AvgD", "AvgA"),
    ("B365H", "B365D", "B365A"),
]


def probs_from_diff(d: float, c1: float, c2: float) -> tuple[float, float, float]:
    """Elo 차 d(홈 어드밴티지 포함) → (p_home, p_draw, p_away). ordered logit."""
    z = d * LOG10 / 400.0
    p_away = _sigmoid(c1 - z)
    p_home = _sigmoid(z - c2)
    p_draw = max(1e-9, 1.0 - p_home - p_away)
    return p_home, p_draw, p_away


# ---------------------------------------------------------------- CSV 수집·파싱

def _download(url: str, dest: pathlib.Path) -> bool:
    try:
        resp = httpx.get(url, timeout=30.0, follow_redirects=True)
        if resp.status_code != 200 or len(resp.content) < 200:
            logger.warning("[elo] download failed %s -> %s", url, resp.status_code)
            return False
        dest.write_bytes(resp.content)
        return True
    except httpx.HTTPError as exc:
        logger.warning("[elo] download error %s: %s", url, exc)
        return False


def download_csvs() -> int:
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    for code in MAIN_LEAGUES:
        for season in MAIN_SEASONS:
            ok += _download(f"{BASE}/mmz4281/{season}/{code}.csv",
                            CSV_DIR / f"{code}_{season}.csv")
    for code in EXTRA_LEAGUES:
        ok += _download(f"{BASE}/new/{code}.csv", CSV_DIR / f"{code}.csv")
    logger.info("[elo] downloaded %d csv files", ok)
    return ok


def _parse_date(s: str) -> datetime | None:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def _market_probs_from_row(row: dict) -> list[float] | None:
    for h, d, a in ODDS_COLS:
        try:
            oh, od, oa = float(row[h]), float(row[d]), float(row[a])
            total = 1 / oh + 1 / od + 1 / oa
            return [1 / oh / total, 1 / od / total, 1 / oa / total]
        except (KeyError, ValueError, ZeroDivisionError, TypeError):
            continue
    return None


def _parse_csv(path: pathlib.Path, season_hint: str | None) -> list[dict]:
    if not path.exists():
        return []
    matches = []
    with path.open(encoding="latin-1", newline="") as f:
        for row in csv.DictReader(f):
            home = (row.get("HomeTeam") or row.get("Home") or "").strip()
            away = (row.get("AwayTeam") or row.get("Away") or "").strip()
            res = (row.get("FTR") or row.get("Res") or "").strip()
            date = _parse_date(row.get("Date", ""))
            if not home or not away or res not in ("H", "D", "A") or date is None:
                continue
            matches.append({
                "date": date, "home": home, "away": away, "res": res,
                "season": season_hint or (row.get("Season") or "?").strip(),
                "market": _market_probs_from_row(row),
            })
    return matches


def load_matches(code: str) -> list[dict]:
    if code in EXTRA_LEAGUES:
        matches = _parse_csv(CSV_DIR / f"{code}.csv", None)
    else:
        matches = []
        for season in MAIN_SEASONS:
            matches.extend(_parse_csv(CSV_DIR / f"{code}_{season}.csv", season))
    matches.sort(key=lambda m: m["date"])
    return matches


# ---------------------------------------------------------------- 리플레이·피팅

RES_IDX = {"H": 0, "D": 1, "A": 2}


def _log_loss(records, c1: float, c2: float) -> float:
    total = 0.0
    for d, res, _, _ in records:
        p = probs_from_diff(d, c1, c2)[RES_IDX[res]]
        total -= math.log(max(p, 1e-9))
    return total / max(len(records), 1)


def _brier(records, c1: float, c2: float) -> float:
    total = 0.0
    for d, res, _, _ in records:
        p = probs_from_diff(d, c1, c2)
        total += sum((p[i] - (1.0 if i == RES_IDX[res] else 0.0)) ** 2 for i in range(3))
    return total / max(len(records), 1)


def _brier_market(records) -> tuple[float | None, int]:
    total, n = 0.0, 0
    for _, res, market, _ in records:
        if not market:
            continue
        total += sum((market[i] - (1.0 if i == RES_IDX[res] else 0.0)) ** 2 for i in range(3))
        n += 1
    return (total / n if n else None), n


def _calibration(records, c1: float, c2: float) -> list[dict]:
    buckets: dict[int, list] = defaultdict(list)
    for d, res, _, _ in records:
        ph = probs_from_diff(d, c1, c2)[0]
        buckets[min(int(ph * 10), 9)].append((ph, 1.0 if res == "H" else 0.0))
    return [
        {"bucket": f"{b/10:.1f}-{(b+1)/10:.1f}", "n": len(v),
         "pred": round(sum(p for p, _ in v) / len(v), 3),
         "actual": round(sum(o for _, o in v) / len(v), 3)}
        for b, v in sorted(buckets.items()) if v
    ]


def fit_league(code: str) -> tuple[dict, dict] | None:
    """리그 하나 피팅 → (ratings, params+metrics). 데이터 없으면 None."""
    matches = load_matches(code)
    if len(matches) < 200:
        logger.warning("[elo] %s: 데이터 부족 (%d경기) — 스킵", code, len(matches))
        return None
    seasons = sorted({m["season"] for m in matches})
    eval_seasons = set(seasons[-2:])  # 최근 2시즌 백테스트
    best = None
    for ha in (30.0, 60.0, 90.0):
        _, records = replay(matches, ha)
        train = [r for r in records if r[3] not in eval_seasons]
        if not train:
            train = records
        for c1_i in range(-14, -1):
            c1 = c1_i / 10.0
            for c2_i in range(1, 15):
                c2 = c2_i / 10.0
                loss = _log_loss(train, c1, c2)
                if best is None or loss < best[0]:
                    best = (loss, ha, c1, c2)
    _, ha, c1, c2 = best
    ratings, records = replay(matches, ha)
    eval_recs = [r for r in records if r[3] in eval_seasons]
    brier_market, n_market = _brier_market(eval_recs)
    params = {
        "home_adv": ha, "c1": c1, "c2": c2, "k": K_FACTOR,
        "n_matches": len(matches), "eval_seasons": sorted(eval_seasons),
        "metrics": {
            "n_eval": len(eval_recs),
            "brier_model": round(_brier(eval_recs, c1, c2), 4),
            "brier_market_benchmark": round(brier_market, 4) if brier_market else None,
            "n_with_market_odds": n_market,
            "log_loss_eval": round(_log_loss(eval_recs, c1, c2), 4),
            "calibration": _calibration(eval_recs, c1, c2),
        },
    }
    return ratings, params


def refresh(download: bool = True) -> dict:
    """CSV 갱신 + 전 리그 재피팅 + 아티팩트 저장. 리그별 메트릭 반환."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if download:
        download_csvs()
    all_ratings, all_params = {}, {}
    for code in MAIN_LEAGUES + EXTRA_LEAGUES:
        fitted = fit_league(code)
        if fitted:
            all_ratings[code], all_params[code] = fitted
    RATINGS_FILE.write_text(json.dumps(all_ratings, ensure_ascii=False))
    PARAMS_FILE.write_text(json.dumps(all_params, ensure_ascii=False, indent=1))
    logger.info("[elo] refreshed %d leagues", len(all_params))
    return all_params


# ---------------------------------------------------------------- 추론용 로더

class SoccerElo:
    def __init__(self, ratings: dict, params: dict):
        self.ratings = ratings
        self.params = params

    @classmethod
    def load(cls) -> "SoccerElo":
        if not RATINGS_FILE.exists() or not PARAMS_FILE.exists():
            raise FileNotFoundError("Elo 아티팩트 없음 — python -m app.models.soccer_elo --refresh")
        return cls(json.loads(RATINGS_FILE.read_text()), json.loads(PARAMS_FILE.read_text()))

    @staticmethod
    def league_code(label: str) -> str | None:
        lowered = (label or "").lower()
        for key, code in LABEL_TO_CODE:
            if key in lowered:
                return code
        return None

    def probs(self, home: str, away: str, league_label: str) -> tuple[float, float, float] | None:
        """(p_home, p_draw, p_away) — 리그/팀 매칭 실패 시 None (모델 무효)."""
        from app.collectors.football import match_team_name

        code = self.league_code(league_label)
        if code not in self.ratings:
            return None
        table = self.ratings[code]
        names = list(table.keys())
        h = match_team_name(home, names)
        a = match_team_name(away, names)
        if not h or not a or h == a:
            return None
        p = self.params[code]
        d = table[h] + p["home_adv"] - table[a]
        ph, pd_, pa = probs_from_diff(d, p["c1"], p["c2"])
        return round(ph, 4), round(pd_, 4), round(pa, 4)


def _print_backtest(params: dict) -> None:
    for code, p in params.items():
        m = p["metrics"]
        print(f"\n== {code} (eval {p['eval_seasons']}, n={m['n_eval']}, "
              f"HA={p['home_adv']}, c1={p['c1']}, c2={p['c2']}) ==")
        print(f"  Brier(model)  = {m['brier_model']}")
        print(f"  Brier(market) = {m['brier_market_benchmark']} (n={m['n_with_market_odds']})")
        print(f"  log-loss      = {m['log_loss_eval']}")
        print("  calibration (p_home 예측 vs 실제 홈승률):")
        for b in m["calibration"]:
            print(f"    {b['bucket']}: pred {b['pred']:.3f} vs actual {b['actual']:.3f} (n={b['n']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="CSV 다운로드 + 재피팅")
    parser.add_argument("--backtest", action="store_true", help="백테스트 리포트 출력")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.refresh:
        params = refresh()
    else:
        params = SoccerElo.load().params
    if args.backtest or not args.refresh:
        _print_backtest(params)
