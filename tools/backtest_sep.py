"""[BT-9] 9월 전수 백테스트 — **경기가 시작 안 했다는 가정**으로 다시 돌린다.

사용자 2026-09-23: "9월달에 우리가 경기가 시작안했다는 가정하에 하루하루
현재 코드로 분석을 해라..바뀐코드의 승률을 전수 검사할려고 하니"

실행:
    python -m tools.backtest_sep --out /tmp/bt9.json
    python -m tools.backtest_sep --selftest          # 자가진단만
    python -m tools.backtest_sep --games 17073,16449 # 몇 경기만

🔴 **이 도구의 성패는 누수 차단 하나다.** 오늘 자료로 9월을 예측하면 미래를
   보고 맞히게 된다. 그 좋은 숫자를 믿고 코드를 고치면 운영이 망가진다.
   그래서 세 가지를 지킨다:
     ① 배당은 `captured_at <= 킥오프` 만
     ② Elo 는 `fit_elo.ratings_asof` 로 **그 경기 직전까지**만
     ③ 출전·라인업은 그 경기 **이전** 경기에서만

🔴 **흐름을 다시 짜지 않는다.** `app.flow.run.run_game` 을 그대로 부른다 —
   하네스가 재현하는 것은 **재료**뿐이다. 흐름을 베끼면 흐름이 아니라
   하네스를 테스트하게 된다.

🔴 **DB 에 쓰지 않는다.** `analysis_runs`·`decision_ledger` 를 오염시키면
   운영 지표가 망가진다 — `_ReadOnly` 풀이 `execute` 를 막는다.

⚠️ 못 재는 것은 못 잰다고 적는다:
     뉴스(`news_injury`) — Redis TTL 26h 라 9월 자료가 **없다**
     축구 출전부하        — `lineup_history.minutes` 가 전건 0
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import logging
import math

logger = logging.getLogger("bt9")

EPS = 1e-9


# ── DB 쓰기를 막는 풀 ────────────────────────────────────────────────

class _ReadOnly:
    """읽기는 그대로, **쓰기는 삼킨다.**

    🔴 `run_game` 은 노드마다 `snapshot()` 으로 `analysis_runs` 에 INSERT
       한다. 백테스트가 그것을 쓰면 운영 지표(단계별 통과율·CLV)가 통째로
       오염된다. `snapshot` 은 실패를 경고만 하므로 여기서 삼켜도 흐름은
       그대로 돈다.
    """

    def __init__(self, pool):
        self._p = pool
        self.blocked = 0

    async def fetch(self, *a, **k):
        return await self._p.fetch(*a, **k)

    async def fetchrow(self, *a, **k):
        return await self._p.fetchrow(*a, **k)

    async def fetchval(self, *a, **k):
        return await self._p.fetchval(*a, **k)

    async def execute(self, *a, **k):
        self.blocked += 1
        return None


# ── as-of 재료 ──────────────────────────────────────────────────────

_ODDS_SQL = """
    SELECT o.market, o.side, o.line, o.odds, o.snap_tag, o.provider, o.captured_at
      FROM odds_snapshots o
     WHERE o.game_id = $1 AND o.captured_at <= $2
     ORDER BY o.captured_at DESC
"""

_APPS_SQL = """
    SELECT b.batter, b.slot, b.team, g.starts_at
      FROM batter_appearances b JOIN games g ON g.id = b.game_id
     WHERE b.sport = $1 AND b.team = $2 AND g.starts_at < $3
       AND g.starts_at >= $3 - ($4 || ' days')::interval
     ORDER BY g.starts_at DESC
"""

_USUAL_SQL = """
    SELECT b.batter, b.slot, g.starts_at
      FROM batter_appearances b JOIN games g ON g.id = b.game_id
     WHERE b.sport = $1 AND b.team = $2 AND g.starts_at < $3
     ORDER BY g.starts_at DESC, b.slot
     LIMIT 200
"""


async def _odds_rows(pool, gid: int, at) -> list:
    return [dict(r) for r in await pool.fetch(_ODDS_SQL, gid, at)]


async def _usual_of(pool, sport: str, team: str, at) -> dict:
    """그 경기 **이전** 기록으로 만든 '평소 모습'.

    🔴 판정은 `lineup_diff.usual_from` 이 한다 — 여기서 다시 짓지 않는다.
    """
    from app.engine.lineup_diff import usual_from

    rows = [dict(r) for r in await pool.fetch(_USUAL_SQL, sport, team, at)]
    by: dict = {}
    for r in rows:
        by.setdefault(r["starts_at"], []).append(r)
    history = []
    for _ts, group in sorted(by.items(), reverse=True):
        order = [(str(x["batter"]), "") for x in
                 sorted(group, key=lambda x: (x["slot"] or 99))]
        if order:
            history.append(order)
    return usual_from(history)


async def _elo_asof(pool, sport: str, at) -> dict:
    """그 경기 **직전**까지로 만든 레이팅. 🔴 누수 차단의 핵심.

    ⚠️ `tools/fit_elo.ratings_asof` 가 원본이다 — 감쇠 기준을 구간 끝으로
       잡아야 미래가 안 샌다(그 파일의 첫 계약이 그것이다).
    """
    from app.config import get_settings
    from app.models.team_elo import HOME_ADV, K_FACTOR
    from tools.fit_elo import _res, ratings_asof

    rows = await pool.fetch(
        """SELECT home, away, home_score, away_score, starts_at
             FROM games
            WHERE sport = $1 AND status = 'final'
              AND home_score IS NOT NULL AND away_score IS NOT NULL
              AND starts_at < $2
            ORDER BY starts_at""", sport, at)
    ms = [{"home": r["home"], "away": r["away"], "ts": r["starts_at"],
           "res": _res(r["home_score"], r["away_score"])} for r in rows]
    if len(ms) < 20:
        return {}
    s = get_settings()
    r = ratings_asof(ms, len(ms), float(s.elo_decay), float(K_FACTOR),
                     float(HOME_ADV))
    return {k: {"레이팅": round(v, 1)} for k, v in r.items()}


async def build_ctx(pool, game: dict):
    """그 경기의 as-of 재료를 담은 Ctx. **DB 쓰기는 막는다.**"""
    from app.flow.ctx import Ctx

    at = game["starts_at"]
    gid = int(game["id"])
    sport = str(game["sport"])
    ro = _ReadOnly(pool)

    inject = {
        "odds_rows": await _odds_rows(pool, gid, at),
        # 🔴 9월 뉴스 자료가 없다(Redis TTL 26h) — 지어내지 않고 빈 목록이다.
        #    ⑤가 `news_injury` 를 `미실행` 으로 적고 ⑥이 분모에서 뺀다.
        "changes": [],
    }
    if sport in ("kbo", "npb", "mlb"):
        elo = await _elo_asof(pool, sport, at)
        if elo:
            inject["elo"] = elo
        load: dict = {}
        for side in ("home", "away"):
            team = str(game[side])
            load[side] = {
                "apps": [dict(r) for r in await pool.fetch(
                    _APPS_SQL, sport, team, at, "7")],
                "usual": await _usual_of(pool, sport, team, at)}
        inject["play_load"] = load
    return Ctx(pool=ro, redis=None,
               now_kst=at.astimezone(dt.timezone(dt.timedelta(hours=9))),
               inject=inject), ro


# ── 실행 ────────────────────────────────────────────────────────────

async def run_one(pool, game: dict) -> dict:
    """경기 1건 → 기록 한 줄. 🔴 흐름은 운영 그대로 돈다."""
    from app.flow.run import run_game

    ctx, ro = await build_ctx(pool, game)
    st = await run_game({"id": game["id"], "sport": game["sport"],
                         "league": game["league"], "home": game["home"],
                         "away": game["away"], "starts_at": game["starts_at"]},
                        ctx)
    hs, aws = game["home_score"], game["away_score"]
    return {
        "game_id": game["id"], "sport": game["sport"], "league": game["league"],
        "kickoff": game["starts_at"].isoformat(),
        "home": game["home"], "away": game["away"],
        "home_score": hs, "away_score": aws,
        "trace": list(st.trace or []), "stop_reason": st.stop_reason,
        "hyp_side": st.hyp_side, "pick_side": st.pick_side,
        "n01": st.n01_prior, "n02_p": (st.n02_market or {}).get("p"),
        "n02_move": {k: v for k, v in ((st.n02_market or {}).get("move") or {}).items()
                     if k != "causes"},
        "n03": st.n03_gate,
        "n05_status": {e["var"]: (e.get("status") or "ok")
                       for e in (st.n05_evidence or [])},
        "n06": st.n06_verdict, "n07": st.n07_adjust,
        "n08": {k: v for k, v in (st.n08_pcode or {}).items()
                if k not in ("ours_markets", "model_probs")},
        "n09": st.n09_conf, "n11": st.n11_value,
        "writes_blocked": ro.blocked,
    }


_GAMES_SQL = """
    SELECT id, sport, league, home, away, starts_at, home_score, away_score
      FROM games
     WHERE starts_at >= $1 AND starts_at < $2 AND status = 'final'
       AND home_score IS NOT NULL AND away_score IS NOT NULL
       AND EXISTS (SELECT 1 FROM odds_snapshots o
                    WHERE o.game_id = games.id AND o.market = 'h2h'
                      AND o.captured_at <= games.starts_at)
     ORDER BY starts_at
"""


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-09-01")
    ap.add_argument("--end", default="2026-09-24")
    ap.add_argument("--out", default="/tmp/bt9.json")
    ap.add_argument("--games", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")

    from app.db import get_pool

    pool = await get_pool()
    if a.selftest:
        await selftest(pool)
        return

    lo = dt.datetime.fromisoformat(a.start).replace(tzinfo=dt.UTC)
    hi = dt.datetime.fromisoformat(a.end).replace(tzinfo=dt.UTC)
    rows = [dict(r) for r in await pool.fetch(_GAMES_SQL, lo, hi)]
    if a.games:
        want = {int(x) for x in a.games.split(",") if x.strip()}
        rows = [r for r in rows if r["id"] in want]
    if a.limit:
        rows = rows[:a.limit]
    print(f"[bt9] 대상 {len(rows)}경기 · {a.start}~{a.end}", flush=True)

    out, fail = [], 0
    for i, g in enumerate(rows, 1):
        try:
            out.append(await run_one(pool, g))
        except Exception as exc:          # 한 경기 실패가 전수를 막지 않는다
            fail += 1
            logger.warning("[bt9] g%s 실패: %s", g["id"], exc)
        if i % 25 == 0:
            print(f"  {i}/{len(rows)} · 실패 {fail}", flush=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, default=str)
    print(f"[bt9] 완료 {len(out)}건 · 실패 {fail} → {a.out}", flush=True)
    summarize(out)


# ── 자가진단 — 이게 없으면 숫자를 못 믿는다 ─────────────────────────

async def selftest(pool) -> None:
    """🔴 하네스가 거짓말하지 않는지 먼저 잰다."""
    print("=== BT-9 자가진단 ===")
    rows = [dict(r) for r in await pool.fetch(
        _GAMES_SQL, dt.datetime(2026, 9, 1, tzinfo=dt.UTC),
        dt.datetime(2026, 9, 24, tzinfo=dt.UTC))]
    if not rows:
        print("  🔴 대상 경기가 0건 — 진단 불가"); return
    g = rows[len(rows) // 2]
    print(f"  표본: g{g['id']} {g['away']}@{g['home']} {g['starts_at']:%m-%d %H:%M}Z")

    # ① 누수 진단 — 시점을 바꾸면 결과가 달라져야 한다
    a = await run_one(pool, g)
    g2 = dict(g); g2["starts_at"] = g["starts_at"] + dt.timedelta(days=3)
    b = await run_one(pool, g2)
    same = (a.get("n01") or {}).get("p_home") == (b.get("n01") or {}).get("p_home")
    print(f"  ① 누수 진단  킥오프 p_home={(a.get('n01') or {}).get('p_home')} · "
          f"+3일 p_home={(b.get('n01') or {}).get('p_home')}  "
          f"→ {'🔴 같다(시점 주입이 안 먹는다)' if same else '✅ 다르다'}")

    # ② DB 쓰기가 막혔나
    print(f"  ② 쓰기 차단  삼킨 execute {a['writes_blocked']}회 "
          f"→ {'✅' if a['writes_blocked'] > 0 else '🔴 스냅샷을 안 막았다'}")

    # ③ 기준선 — 시장 확률만으로 잰 Brier
    n = ll = br = 0
    for r in rows:
        p = ((r.get("home_score") or 0), (r.get("away_score") or 0))
        pass
    print("  ③ 기준선은 전수 실행 뒤 `summarize` 가 낸다")


# ── 집계 ────────────────────────────────────────────────────────────

def _metrics(pairs) -> dict:
    """`[(확률, 실제0/1)]` → Brier·logloss·AUC·적중."""
    if not pairs:
        return {"n": 0}
    n = len(pairs)
    br = sum((p - y) ** 2 for p, y in pairs) / n
    ll = -sum(y * math.log(max(p, EPS)) + (1 - y) * math.log(max(1 - p, EPS))
              for p, y in pairs) / n
    hit = sum(int((p > 0.5) == (y > 0.5)) for p, y in pairs) / n
    pos = [p for p, y in pairs if y > 0.5]
    neg = [p for p, y in pairs if y <= 0.5]
    auc = None
    if pos and neg:
        wins = sum(1 for a in pos for b in neg if a > b)
        ties = sum(1 for a in pos for b in neg if a == b)
        auc = (wins + 0.5 * ties) / (len(pos) * len(neg))
    return {"n": n, "brier": round(br, 4), "logloss": round(ll, 5),
            "hit": round(hit, 4), "auc": None if auc is None else round(auc, 4)}


def summarize(rows: list) -> None:
    from collections import Counter

    print("\n=== ① 확률 품질 (홈 기준) ===")
    ours, mkt, prior = [], [], []
    for r in rows:
        hs, aws = r.get("home_score"), r.get("away_score")
        if hs is None or aws is None or hs == aws:
            continue
        y = 1.0 if hs > aws else 0.0
        p8 = r.get("n08") or {}
        if p8.get("p_home") is not None:
            ours.append((float(p8["p_home"]), y))
        p2 = (r.get("n02_p") or {}).get("home")
        if p2 is not None:
            mkt.append((float(p2), y))
        p1 = (r.get("n01") or {}).get("p_home")
        if p1 is not None:
            prior.append((float(p1), y))
    for name, pairs in (("우리 ⑧", ours), ("시장 ②", mkt), ("사전값 ①", prior)):
        m = _metrics(pairs)
        print(f"  {name:<8s} {m}")

    print("\n=== ② 단계별 도달 ===")
    reach = Counter()
    for r in rows:
        for t in set(r.get("trace") or []):
            reach[t] += 1
    for k in sorted(reach):
        print(f"  {k:<16s} {reach[k]}")
    print("  멈춤:", dict(Counter(r.get("stop_reason") for r in rows)))

    print("\n=== ③ ⑤ 변수 상태 ===")
    st = Counter()
    for r in rows:
        for v, s in (r.get("n05_status") or {}).items():
            st[(v, s)] += 1
    for (v, s), c in sorted(st.items()):
        print(f"  {v:<18s} {s:<8s} {c}")


if __name__ == "__main__":
    asyncio.run(main())
