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

#: 🔴 [SELO-1 2026-09-20] **볼륨에 둔다.** 이미지 안(`/app/data/elo`)에 두면
#   배포할 때마다 날아간다 — 실측: SELO-1 배포 직후 `ratings.json 리그 0` 이라
#   축구 ① 이 전건 `elo 미기입` 이었다. 볼륨 경로는 Railway 가 준다(F-18 이
#   내보내기 산출물에 쓰기로 정한 그 볼륨이다).
#   ⚠️ 로컬·테스트에는 볼륨이 없다 — 그때는 종전 경로 그대로다.
def _data_dir() -> pathlib.Path:
    import os

    vol = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    if vol:
        return pathlib.Path(vol) / "elo"
    return pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "elo"


DATA_DIR = _data_dir()
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
    # 🔴 [SELO-1c] 우리 `games.league` 는 **한글 라벨**이다(라리가·세리에A·
    #    분데스리가·리그앙·에레디비시). 영문 키만 있어 전건 미기입이었다.
    ("라리가", "SP1"), ("세리에", "I1"), ("분데스", "D1"),
    ("리그앙", "F1"), ("에레디비시", "N1"), ("챔피언십", "E1"),
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


# ══════════════════════════════════════════════════════════════════
# [SELO-1 2026-09-20] 축구 ① 사전값 배선 — 레이팅을 **야구와 같은 자리**에 싣는다.
#
# 🔴 왜 — 실측 STEP 0-e: 축구 7리그 전부 `① 사전값 = null(elo 캐시 키 없음)` 이고
#    오늘 슬레이트 `n03_freeze` 21건 중 18건이 축구였다. `bridge.ELO_SPORTS` 가
#    축구를 빼 둔 탓이다.
# 🔴 읽는 쪽을 고치지 않는다 — `n01_prior` 는 이미 `elo:{리그}:{날짜}` 를 읽고
#    축구 3-way(`draw_prior`) 분기도 갖고 있다. 실을 자리만 없었다.
# 🔴 **이름 대조는 `config/elo_names.yaml` 이 원본**이다. 여기서 규칙을 다시
#    짓지 않는다(딥서치: football-data.co.uk 는 공식 대조표가 없다).
# ⚠️ 표에 없는 팀은 **비운다.** 리그 평균으로 메우면 채운 팀과 안 채운 팀이
#    같은 근거를 가진 것처럼 보여 ③ 게이트가 오분류한다.
# ══════════════════════════════════════════════════════════════════

_NAMES_DOC: dict | None = None


def _elo_names() -> dict:
    """`config/elo_names.yaml` 의 `elo_names`. 없으면 빈 dict(예외 금지)."""
    global _NAMES_DOC
    if _NAMES_DOC is None:
        try:
            import yaml

            f = (pathlib.Path(__file__).resolve().parents[2]
                 / "config" / "elo_names.yaml")
            _NAMES_DOC = (yaml.safe_load(f.read_text(encoding="utf-8")) or {}) \
                .get("elo_names") or {}
        except Exception as exc:
            logger.warning("[elo] 이름 대조표 로드 실패: %s", exc)
            _NAMES_DOC = {}
    return _NAMES_DOC


def ratings_for_league(league: str, ratings: dict | None = None) -> dict:
    """그 리그의 `{우리 팀 이름: 레이팅}`. 🔴 대조표에 없는 팀은 **넣지 않는다.**

    `ratings` 는 `ratings.json` 모양(`{CSV코드: {elo이름: 레이팅}}`)이다.
    """
    box = (_elo_names() or {}).get(league) or {}
    if not box:
        return {}
    src = ratings if ratings is not None else _load_ratings_file()
    if not src:
        return {}
    # 🔴 리그 코드는 `LABEL_TO_CODE` 가 원본이다 — 여기서 새 표를 만들지 않는다.
    code = None
    low = str(league or "").lower()
    for key, c in LABEL_TO_CODE:
        if key in low:
            code = c
            break
    pool = src.get(code) if code else None
    if not isinstance(pool, dict):
        # 리그 코드를 못 찾으면 **전 리그에서 찾지 않는다** — 리그 간 비교가 된다.
        return {}
    out: dict = {}
    for ours, elo_name in box.items():
        v = pool.get(elo_name)
        if v is not None:
            out[ours] = float(v)
    return out


def _load_ratings_file() -> dict:
    try:
        return json.loads(RATINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


#: 하루 한 번만 피팅한다. 🔴 CSV 를 매번 내려받으면 슬레이트가 그만큼 느려지고
#  football-data.co.uk 에 부담이다. 주 1회 잡(`elo_refresh_weekly`)이 원래
#  주인이고, 이것은 **배포로 아티팩트가 날아갔을 때의 복구**다.
_FIT_MARK = "elo:soccer:fitted:{date}"


async def ensure_ratings_file(redis, date: str) -> dict:
    """`ratings.json` 이 없으면 **하루 1회** 피팅해서 만든다. 반환: ratings.

    ⚠️ 실패해도 예외를 올리지 않는다 — 없으면 그 리그는 사전값없음 경로다.
    """
    got = _load_ratings_file()
    if got:
        return got
    if redis is not None:
        try:
            if not await redis.set(_FIT_MARK.format(date=date), "1",
                                   ex=26 * 3600, nx=True):
                logger.info("[elo] 오늘 이미 피팅을 시도했다 — 건너뛴다")
                return {}
        except Exception as exc:
            logger.debug("[elo] 피팅 마커 실패: %s", exc)
    try:
        logger.info("[elo] 축구 아티팩트 없음 — 지금 피팅한다 (%s)", DATA_DIR)
        refresh()
    except Exception as exc:
        logger.warning("[elo] 축구 피팅 실패: %s", exc)
        return {}
    return _load_ratings_file()


async def publish_ratings(redis, leagues, date: str, *, ratings=None) -> dict:
    """리그별 레이팅을 `elo:{리그}:{날짜}` 에 싣는다. 반환 `{리그: 팀 수}`.

    🔴 키·TTL 은 `team_elo` 가 원본이다 — 야구와 같은 자리에 같은 모양으로 둔다.
    ⚠️ 빈 리그는 **쓰지 않는다**(빈 키가 있으면 ①이 "있는데 팀이 없다"로 읽는다).
    """
    from app.models.team_elo import CACHE_KEY, CACHE_TTL, code_for

    src = ratings if ratings is not None else await ensure_ratings_file(redis, date)
    out: dict = {}
    for lg in leagues or []:
        got = ratings_for_league(lg, src)
        if not got:
            logger.info("[elo] %s — 대조 가능한 팀 0 (사전값없음 경로로 간다)", lg)
            continue
        if redis is not None:
            # 🔴 코드 생성 규칙은 `team_elo.code_for` 하나다 — 읽는 쪽과
            #    같은 함수를 쓴다(대소문자 어긋남이 SELO-1c 의 원인이었다).
            await redis.set(CACHE_KEY.format(sport=code_for(lg), date=date),
                            json.dumps(got, ensure_ascii=False), ex=CACHE_TTL)
        out[lg] = len(got)
        logger.info("[elo] %s %s — 팀 %d개 실음", lg, date, len(got))
    return out


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
