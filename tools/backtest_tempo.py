"""[백테스트] 자료13 전개 계산기 — 주입 전 관문.

관문(2026-09-07 사용자 확정): 종료 경기 소급으로
**전개 우위 방향의 승자 일치율**과 **기대득점 오차**를 재고,
**일치율 55% 미만이면 주입 보류.**

산출 형태(사용자 확정): `{홈 기대득점, 원정 기대득점, 우위, 격차, 합계}`
계산 축(사용자 확정): 선발/불펜 이닝 분할 × 타선 배율. **자료11 전면 제외.**

    E(홈 득점) = p50(원정선발 이닝) × 원정선발 R/이닝
               + (9 − p50)         × 원정불펜 R/이닝
               × (홈 최근 3경기 평균 득점 / 리그평균 득점)

⚠️ 누수 방지: 모든 피처는 **그 경기 시작 이전**(`starts_at <`)의 행으로만 만든다.
   리그평균·elo 도 마찬가지로 as-of 시점까지만 리플레이한다.

⚠️ 한계 — 정직하게 적는다:
   - **자료11(날씨·연전·이동)은 쓰지 않는다.** 사용자 확정 사항이기도 하고,
     날씨는 애초에 과거값이 저장돼 있지 않아 소급 재현이 불가하다.
   - **선발 신원은 실제 등판 기록에서 가져온다.** 운영은 판정 시점에 확정
     라인업으로 같은 정보를 알지만, 여기서는 결과 표에서 읽으므로 신원에
     한해 사후 정보다. 성적은 전부 그 경기 **이전** 등판만 쓴다.
   - 불펜 실점은 표본 3경기라 얇다(`bullpen_recent.py` 의 경고와 같은 이유).

정의는 기존 구현을 **다시 적지 않고 그대로 가져온다**:
   이닝 분위수 → `app.engine.variable_ref.quantiles` (비보간)
   등판 창 10 · 얇은 선발 기준 3 · 불펜 창 3경기 → `app.config`
   elo → `app.models.team_elo.compute`

사용법:
    PYTHONPATH=. uv run python tools/backtest_tempo.py            # 세 리그 전부
    PYTHONPATH=. uv run python tools/backtest_tempo.py --sport kbo --last 30
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

INNINGS = 9.0

_GAMES = """
    SELECT id, sport, home, away, home_score, away_score, starts_at
      FROM games
     WHERE sport = $1 AND status = 'final'
       AND home_score IS NOT NULL AND away_score IS NOT NULL
     ORDER BY starts_at, id
"""

#: 총득점 재시험용. 경기 시작 **이전** 마지막 스냅샷만 본다(누수 방지).
_TOTALS = """
    SELECT o.game_id, o.line, o.captured_at
      FROM odds_snapshots o JOIN games g ON g.id = o.game_id
     WHERE g.sport = $1 AND o.market = 'totals' AND o.line IS NOT NULL
       AND o.captured_at < g.starts_at
     ORDER BY o.game_id, o.captured_at
"""

_APPS = """
    SELECT a.game_id, a.team, a.pitcher, a.is_starter, a.innings, a.r,
           g.starts_at
      FROM pitcher_appearances a
      JOIN games g ON g.id = a.game_id
     WHERE g.sport = $1 AND g.status = 'final'
     ORDER BY g.starts_at, a.id
"""


# ─────────────────────────────────────────────────────────── 계산기 (순수 함수)

def expected_runs(sp_ip_p50: float, sp_r_per_ip: float,
                  bp_r_per_ip: float, off_mult: float,
                  innings: float = INNINGS) -> float:
    """한 팀의 기대득점. **상대** 선발·불펜과 **자기** 타선 배율을 받는다.

    선발 소화 이닝은 [0, innings] 로 자른다 — 연장 이닝을 예측하지 않는다.
    """
    ip = min(max(float(sp_ip_p50), 0.0), innings)
    return (ip * float(sp_r_per_ip)
            + (innings - ip) * float(bp_r_per_ip)) * float(off_mult)


def build_sides(*, home_sp: dict, away_sp: dict,
                home_bp: float, away_bp: float,
                home_off: float, away_off: float) -> tuple[dict, dict]:
    """교차 배선. **한 팀의 득점은 상대 투수진과 자기 타선에서 나온다.**

    🔴 여기가 부호가 뒤집히는 자리다 (`backtest_lambda.py` 가 기록한
       2026-08-26 실사고와 같은 유형). 홈 블록에 홈 선발을 넣으면
       모든 지표가 그럴듯하게 나오면서 방향만 반대가 된다.
    """
    return ({"sp_ip_p50": away_sp["p50"], "sp_r_per_ip": away_sp["r_per_ip"],
             "bp_r_per_ip": away_bp, "off_mult": home_off},
            {"sp_ip_p50": home_sp["p50"], "sp_r_per_ip": home_sp["r_per_ip"],
             "bp_r_per_ip": home_bp, "off_mult": away_off})


def tempo(home: dict, away: dict) -> dict:
    """자료13 페이로드. 팀당 값만 낸다 — 집계표를 얹지 않는다."""
    eh = expected_runs(**home)
    ea = expected_runs(**away)
    return {"홈": {"기대득점": round(eh, 2)},
            "원정": {"기대득점": round(ea, 2)},
            "우위": "홈" if eh > ea else "원정" if ea > eh else "동률",
            "격차": round(eh - ea, 2),
            "합계": round(eh + ea, 2)}


# ─────────────────────────────────────────────────────────── as-of 피처 조립

def _shrunk(runs: float, ip: float, lg_rate: float, k_ip: float) -> float:
    """이닝당 실점을 리그평균 쪽으로 수축. `k_ip=0` 이면 원래 비율 그대로.

    가상 이닝 `k_ip` 를 리그평균 성적으로 얹는 표준 축소 추정량이다 —
    표본 2이닝짜리 불펜이 리그 최악으로 읽히는 것을 막는다.
    """
    if k_ip <= 0:
        return runs / ip
    return (runs + k_ip * lg_rate) / (ip + k_ip)


class History:
    """리그 하나의 종료 경기·등판 이력. 전부 메모리에서 as-of 로 자른다."""

    def __init__(self, games: list[dict], apps: list[dict]):
        self.games = games
        self.by_pitcher: dict[str, list[dict]] = defaultdict(list)
        self.starter_of: dict[tuple[int, str], str] = {}
        self.relief_of: dict[tuple[int, str], list[dict]] = defaultdict(list)
        for a in apps:
            self.by_pitcher[a["pitcher"]].append(a)
            key = (a["game_id"], a["team"])
            if a["is_starter"]:
                self.starter_of.setdefault(key, a["pitcher"])
            else:
                self.relief_of[key].append(a)
        self.by_team: dict[str, list[dict]] = defaultdict(list)
        for g in games:
            self.by_team[g["home"]].append(g)
            self.by_team[g["away"]].append(g)

    # ── 자료10 축: 그 투수가 몇 이닝 던지는 사람인가 + 이닝당 실점
    def starter_profile(self, pitcher: str, before, window: int,
                        low_start_max: int, all_apps: bool,
                        lg_rate: float = 0.0, shrink_ip: float = 0.0,
                        min_apps: int = 1) -> dict | None:
        from app.engine.variable_ref import quantiles

        rows = [a for a in self.by_pitcher.get(pitcher, [])
                if a["starts_at"] < before and a["innings"] is not None]
        if not rows:
            return None
        starts = [a for a in rows if a["is_starter"]]
        # 운영 규칙과 같은 갈래: 선발 표본이 `low_start_max` 이상이면 선발만,
        # 얇으면 자료10 처럼 구원까지 합쳐 본다(`var_ref.innings_profile`).
        use = rows if (all_apps or len(starts) < low_start_max) else starts
        use = use[-window:]
        if len(use) < min_apps:
            return None
        ip = [float(a["innings"]) for a in use]
        tot_ip, tot_r = sum(ip), sum(float(a["r"] or 0) for a in use)
        if tot_ip <= 0:
            return None
        q = quantiles(ip)
        if not q:
            return None
        return {"p50": q["p50"],
                "r_per_ip": _shrunk(tot_r, tot_ip, lg_rate, shrink_ip),
                "n": len(use), "starts": len(starts)}

    # ── 자료9 축: 팀 최근 3경기 구원진 이닝당 실점
    def bullpen_rate(self, team: str, before, games_window: int,
                     lg_rate: float = 0.0, shrink_ip: float = 0.0) -> float | None:
        prev = [g for g in self.by_team.get(team, []) if g["starts_at"] < before]
        if not prev:
            return None
        ip = r = 0.0
        for g in prev[-games_window:]:
            for a in self.relief_of.get((g["id"], team), []):
                ip += float(a["innings"] or 0)
                r += float(a["r"] or 0)
        if ip <= 0:
            return None
        return _shrunk(r, ip, lg_rate, shrink_ip)

    # ── 자료1 축: 최근 3경기 팀 득점 / 리그평균 (사용자 지시로 자료8 대체)
    def offense_mult(self, team: str, before, league_rpg: float,
                     games_window: int, shrink: float = 0.0) -> float | None:
        prev = [g for g in self.by_team.get(team, []) if g["starts_at"] < before]
        prev = prev[-games_window:]
        if len(prev) < games_window or league_rpg <= 0:
            return None
        runs = sum(float(g["home_score"] if g["home"] == team else g["away_score"])
                   for g in prev)
        mult = (runs / len(prev)) / league_rpg
        if shrink > 0:
            w = len(prev) / (len(prev) + shrink)
            mult = w * mult + (1.0 - w) * 1.0
        return mult


def league_rpg_asof(games: list[dict], idx: int) -> float | None:
    """as-of 시점까지의 팀·경기당 평균 득점. 리그 정규화 상수일 뿐이다."""
    if idx <= 0:
        return None
    runs = sum(float(g["home_score"]) + float(g["away_score"]) for g in games[:idx])
    return runs / (2.0 * idx)


# ─────────────────────────────────────────────────────────── 채점

def _mae(xs):
    return statistics.fmean(xs) if xs else float("nan")


def _rmse(xs):
    return (statistics.fmean([x * x for x in xs]) ** 0.5) if xs else float("nan")


def score(rows: list[dict]) -> dict:
    """행 → 관문 지표. 무승부는 방향 채점에서 뺀다(우열이 없다)."""
    dec = [r for r in rows if r["actual_margin"] != 0]
    hit = sum(1 for r in dec
              if (r["pred_margin"] > 0) == (r["actual_margin"] > 0)
              and r["pred_margin"] != 0)
    err = [abs(r["e_home"] - r["a_home"]) for r in rows]
    err += [abs(r["e_away"] - r["a_away"]) for r in rows]
    bias = [r["e_home"] - r["a_home"] for r in rows]
    bias += [r["e_away"] - r["a_away"] for r in rows]
    home_hit = sum(1 for r in dec if r["actual_margin"] > 0)
    elo_dec = [r for r in dec if r.get("elo_gap") is not None and r["elo_gap"] != 0]
    elo_hit = sum(1 for r in elo_dec if (r["elo_gap"] > 0) == (r["actual_margin"] > 0))
    return {
        "n": len(rows), "판정가능": len(dec), "무승부": len(rows) - len(dec),
        "일치율": (hit / len(dec)) if dec else float("nan"),
        "MAE_팀득점": _mae(err), "RMSE_팀득점": _rmse(err),
        "편향": _mae(bias),
        "MAE_합계": _mae([abs(r["e_home"] + r["e_away"]
                              - r["a_home"] - r["a_away"]) for r in rows]),
        "MAE_격차": _mae([abs(r["pred_margin"] - r["actual_margin"]) for r in rows]),
        "기준선_홈고정": (home_hit / len(dec)) if dec else float("nan"),
        "기준선_elo": (elo_hit / len(elo_dec)) if elo_dec else float("nan"),
        "기준선_elo_n": len(elo_dec),
    }


def wilson(hit: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """(비율, 하한, 상한). 표본 0이면 nan."""
    if n <= 0:
        return (float("nan"),) * 3
    p = hit / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return p, c - h, c + h


def score_totals(rows: list[dict]) -> dict:
    """[총득점 관문 2026-09-07] 예측 총득점의 오버/언더 방향과 오차.

    🔴 관문은 **실행 전에** 선언됐다 (사용자 지시):
       (a) 방향 일치율의 Wilson 95% **하한**이 세 기준선을 전부 이길 것
           — 항상 오버 · 항상 언더 · 리그평균선 예측기
       (b) 총득점 MAE 가 리그평균 상수 기준선보다 개선될 것

    푸시 규약: 실제 총득점 == 선 이면 **방향 분모에서 제외**(승패가 없다).
    예측 == 선 이면 **미적중**으로 센다 — 우리와 기준선에 같은 자를 댄다.
    """
    dec = [r for r in rows if r["actual_total"] != r["line"]]
    n = len(dec)

    def _hits(pred_of) -> int:
        return sum(1 for r in dec
                   if (pred := pred_of(r)) != r["line"]
                   and (pred > r["line"]) == (r["actual_total"] > r["line"]))

    hit = _hits(lambda r: r["pred_total"])
    p, lo, hi = wilson(hit, n)
    over = sum(1 for r in dec if r["actual_total"] > r["line"]) / n if n else float("nan")
    under = sum(1 for r in dec if r["actual_total"] < r["line"]) / n if n else float("nan")
    lg_hit = _hits(lambda r: r["league_total"])
    lg = lg_hit / n if n else float("nan")
    degenerate = sum(1 for r in dec if r["league_total"] == r["line"])
    mae = _mae([abs(r["pred_total"] - r["actual_total"]) for r in rows])
    mae_lg = _mae([abs(r["league_total"] - r["actual_total"]) for r in rows])
    return {
        "n": len(rows), "판정가능": n, "푸시": len(rows) - n,
        "일치율": p, "하한": lo, "상한": hi,
        "기준_항상오버": over, "기준_항상언더": under,
        "기준_리그평균선": lg, "리그평균선_무의미": degenerate,
        "MAE": mae, "MAE_리그평균": mae_lg,
        "시장라인": sum(1 for r in rows if r["line_src"] == "시장"),
        "a_통과": bool(n and lo > max(over, under, lg)),
        "b_통과": bool(mae < mae_lg),
    }


def baseline_league_mae(rows: list[dict]) -> float:
    """비교선: 양팀 모두 리그평균 득점으로 찍었을 때의 MAE."""
    err = []
    for r in rows:
        err.append(abs(r["league_rpg"] - r["a_home"]))
        err.append(abs(r["league_rpg"] - r["a_away"]))
    return _mae(err)


# ─────────────────────────────────────────────────────────── 실행

async def run_sport(pool, sport: str, *, all_apps: bool = False,
                    shrink: float = 0.0, elo: bool = True,
                    sp_shrink: float = 0.0, bp_shrink: float = 0.0,
                    min_apps: int = 1) -> tuple[list[dict], dict]:
    from app.config import get_settings

    s = get_settings()
    window = int(s.var_ref_appearances)
    low_start_max = int(s.var_ref_low_start_max)
    bp_games = int(s.bullpen_recent_games)

    games = [dict(r) for r in await pool.fetch(_GAMES, sport)]
    apps = [dict(r) for r in await pool.fetch(_APPS, sport)]
    hist = History(games, apps)

    # 시장 totals 라인: 경기별 **시작 직전 스냅샷**의 북 중앙값.
    by_game: dict[int, list] = defaultdict(list)
    for r in await pool.fetch(_TOTALS, sport):
        by_game[r["game_id"]].append((r["captured_at"], float(r["line"])))
    market_line: dict[int, float] = {}
    for gid, xs in by_game.items():
        last = max(t for t, _ in xs)
        market_line[gid] = statistics.median([v for t, v in xs if t == last])

    elo_gap_of: dict[int, float] = {}
    if elo:
        from app.models.team_elo import compute
        seen_date = None
        ratings: dict = {}
        for i, g in enumerate(games):
            d = g["starts_at"].date()
            if d != seen_date:                       # 하루 한 번만 리플레이
                ratings = compute(games[:i], decay=float(s.elo_decay))
                seen_date = d
            h, a = ratings.get(g["home"]), ratings.get(g["away"])
            if h and a:
                elo_gap_of[g["id"]] = float(h["레이팅"]) - float(a["레이팅"])

    rows: list[dict] = []
    drops: dict[str, int] = defaultdict(int)
    for i, g in enumerate(games):
        before = g["starts_at"]
        lg = league_rpg_asof(games, i)
        if lg is None:
            drops["리그평균 없음"] += 1
            continue
        sp_h = hist.starter_of.get((g["id"], g["home"]))
        sp_a = hist.starter_of.get((g["id"], g["away"]))
        if not sp_h or not sp_a:
            drops["선발 기록 없음"] += 1
            continue
        lg_rate = lg / INNINGS                      # 리그 이닝당 실점
        ph = hist.starter_profile(sp_h, before, window, low_start_max, all_apps,
                                  lg_rate, sp_shrink, min_apps)
        pa = hist.starter_profile(sp_a, before, window, low_start_max, all_apps,
                                  lg_rate, sp_shrink, min_apps)
        if not ph or not pa:
            drops["선발 이전 등판 부족"] += 1
            continue
        bh = hist.bullpen_rate(g["home"], before, bp_games, lg_rate, bp_shrink)
        ba = hist.bullpen_rate(g["away"], before, bp_games, lg_rate, bp_shrink)
        if bh is None or ba is None:
            drops["불펜 이전 이닝 없음"] += 1
            continue
        oh = hist.offense_mult(g["home"], before, lg, 3, shrink)
        oa = hist.offense_mult(g["away"], before, lg, 3, shrink)
        if oh is None or oa is None:
            drops["직전 3경기 부족"] += 1
            continue

        hside, aside = build_sides(home_sp=ph, away_sp=pa, home_bp=bh,
                                   away_bp=ba, home_off=oh, away_off=oa)
        t = tempo(home=hside, away=aside)
        rows.append({
            "date": g["starts_at"].date().isoformat(),
            "home": g["home"], "away": g["away"],
            "e_home": t["홈"]["기대득점"], "e_away": t["원정"]["기대득점"],
            "a_home": float(g["home_score"]), "a_away": float(g["away_score"]),
            "pred_margin": t["격차"],
            "actual_margin": float(g["home_score"]) - float(g["away_score"]),
            "league_rpg": lg, "elo_gap": elo_gap_of.get(g["id"]),
            "sp_p50_home": ph["p50"], "sp_p50_away": pa["p50"],
            # ── 총득점 관문
            "pred_total": t["합계"],
            "actual_total": float(g["home_score"]) + float(g["away_score"]),
            "league_total": round(2.0 * lg, 2),
            "line": market_line.get(g["id"], round(2.0 * lg, 2)),
            "line_src": "시장" if g["id"] in market_line else "리그평균",
        })
    return rows, dict(drops)


def report(sport: str, rows: list[dict], drops: dict, last: int) -> None:
    print(f"\n{'=' * 72}\n[{sport.upper()}] 유효 표본 {len(rows)}건"
          f"  (제외: {drops or '없음'})")
    if not rows:
        print("  표본 0 — 채점 불가")
        return
    for label, subset in (("전체", rows), (f"최근 {last}건", rows[-last:])):
        m = score(subset)
        gate = "통과" if m["일치율"] >= 0.55 else "미달"
        print(f"\n  ── {label} (n={m['n']}, 판정가능 {m['판정가능']},"
              f" 무승부 {m['무승부']})")
        print(f"     승자 일치율      {m['일치율'] * 100:5.1f}%   [관문 55% → {gate}]")
        print(f"       기준선 홈고정  {m['기준선_홈고정'] * 100:5.1f}%")
        print(f"       기준선 elo     {m['기준선_elo'] * 100:5.1f}%"
              f"   (n={m['기준선_elo_n']})")
        print(f"     기대득점 MAE     {m['MAE_팀득점']:5.2f}점"
              f"   (RMSE {m['RMSE_팀득점']:.2f}, 편향 {m['편향']:+.2f})")
        print(f"       기준선 리그평균 {baseline_league_mae(subset):5.2f}점")
        print(f"     합계 MAE {m['MAE_합계']:.2f}점 · 격차 MAE {m['MAE_격차']:.2f}점")
    p50s = [r["sp_p50_home"] for r in rows] + [r["sp_p50_away"] for r in rows]
    print(f"\n     선발 p50 이닝 분포: 중앙 {statistics.median(p50s):.1f} ·"
          f" 3이닝 미만 {sum(1 for x in p50s if x < 3) / len(p50s) * 100:.0f}%")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", default="kbo,npb,mlb")
    ap.add_argument("--last", type=int, default=30, help="관문 표본 수")
    ap.add_argument("--all-apps", action="store_true",
                    help="선발 표본이 두터워도 구원 등판까지 합쳐 이닝 분포를 낸다")
    ap.add_argument("--shrink", type=float, default=0.0,
                    help="타선 배율을 1.0 쪽으로 수축(가중 n/(n+k))")
    ap.add_argument("--sp-shrink", type=float, default=0.0,
                    help="선발 이닝당 실점을 리그평균 쪽으로 수축(가상 이닝 k)")
    ap.add_argument("--bp-shrink", type=float, default=0.0,
                    help="불펜 이닝당 실점을 리그평균 쪽으로 수축(가상 이닝 k)")
    ap.add_argument("--min-apps", type=int, default=1,
                    help="선발의 이전 등판이 이 수 미만이면 그 경기를 뺀다")
    ap.add_argument("--no-elo", action="store_true")
    args = ap.parse_args()

    from app.db import close_pool, get_pool

    pool = await get_pool()
    try:
        for sport in [x.strip() for x in args.sport.split(",") if x.strip()]:
            rows, drops = await run_sport(
                pool, sport, all_apps=args.all_apps, shrink=args.shrink,
                elo=not args.no_elo, sp_shrink=args.sp_shrink,
                bp_shrink=args.bp_shrink, min_apps=args.min_apps)
            report(sport, rows, drops, args.last)
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
