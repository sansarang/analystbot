"""[MBL-1] statsapi → 로컬 SQLite 적재 (야구 모델 2단계).

🔴 **`season` 파라미터만 쓴다.** 실측 2026-09-13:
     schedule?sportId=1&season=2024&gameType=R  → totalGames=2469
     schedule?sportId=1&date=2024-07-01         → totalGames=3   ← 날짜 조회 결함
   날짜별로 긁으면 경기를 통째로 놓친다.

🔴 **머니라인은 원값으로 저장한다.** 디빅은 4단계다 — 여기서 확률로 바꾸면
   그 변환이 두 곳에 생기고, 한쪽만 고쳐진다.
⚠️ 팀·선수 키는 statsapi id 다(`teams.py`). 이름 매칭을 하지 않는다.
"""
from __future__ import annotations

import logging
import sqlite3

from app.model_baseball import teams

logger = logging.getLogger(__name__)

BASE = "https://statsapi.mlb.com/api/v1"
SCHEDULE = BASE + "/schedule"
BOXSCORE = BASE + "/game/{game_pk}/boxscore"

#: 종료 경기만 쓴다. statsapi 코드값.
FINAL_STATES = {"F", "FR", "FT"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    game_id     INTEGER PRIMARY KEY,
    league      TEXT NOT NULL,
    season      INTEGER NOT NULL,
    kickoff_utc TEXT NOT NULL,
    home        INTEGER NOT NULL,
    away        INTEGER NOT NULL,
    park        INTEGER,
    home_sp     INTEGER,
    away_sp     INTEGER,
    home_runs   INTEGER,
    away_runs   INTEGER,
    ml_open_h   REAL, ml_open_a  REAL,
    ml_close_h  REAL, ml_close_a REAL
);
CREATE TABLE IF NOT EXISTS pitch_app (
    game_id INTEGER NOT NULL, pitcher_id INTEGER NOT NULL,
    team INTEGER, role TEXT, ip REAL, er INTEGER, r INTEGER,
    k INTEGER, bb INTEGER, h INTEGER, pitches INTEGER,
    PRIMARY KEY (game_id, pitcher_id)
);
CREATE TABLE IF NOT EXISTS bat_app (
    game_id INTEGER NOT NULL, batter_id INTEGER NOT NULL,
    team INTEGER, "order" INTEGER, pa INTEGER, ab INTEGER, h INTEGER,
    b2 INTEGER, b3 INTEGER, hr INTEGER, bb INTEGER, hbp INTEGER, so INTEGER,
    PRIMARY KEY (game_id, batter_id)
);
CREATE INDEX IF NOT EXISTS idx_games_season ON games (league, season, kickoff_utc);
"""


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)
    con.commit()


def parse_ip(v) -> float:
    """야구 이닝 표기 → 실수. 🔴 `6.1` 은 6.1이 아니라 **6과 1/3**이다."""
    if v is None:
        return 0.0
    s = str(v).strip()
    if not s:
        return 0.0
    try:
        whole, _, frac = s.partition(".")
        out = float(whole or 0)
        if frac:
            out += int(frac[0]) / 3.0
        return out
    except (TypeError, ValueError):
        return 0.0


def parse_schedule(payload: dict, *, season: int) -> list[dict]:
    """일정 응답 → `games` 행. **종료 경기만.**"""
    out = []
    for d in (payload or {}).get("dates") or []:
        for g in d.get("games") or []:
            state = ((g.get("status") or {}).get("codedGameState") or "").upper()
            if state not in FINAL_STATES:
                continue
            t = g.get("teams") or {}
            h, a = (t.get("home") or {}), (t.get("away") or {})
            ht, at = (h.get("team") or {}), (a.get("team") or {})
            teams.remember(ht.get("id"), ht.get("name"))
            teams.remember(at.get("id"), at.get("name"))
            out.append({
                "game_id": g.get("gamePk"), "league": "mlb", "season": int(season),
                "kickoff_utc": g.get("gameDate") or "",
                "home": ht.get("id"), "away": at.get("id"),
                "park": (g.get("venue") or {}).get("id"),
                "home_runs": h.get("score"), "away_runs": a.get("score"),
            })
    return [r for r in out if r["game_id"] and r["home"] and r["away"]]


def _players(box: dict, side: str):
    blk = ((box or {}).get("teams") or {}).get(side) or {}
    return blk, (blk.get("players") or {})


def parse_pitching(box: dict, *, game_id: int) -> list[dict]:
    out = []
    for side in ("home", "away"):
        blk, players = _players(box, side)
        team = (blk.get("team") or {}).get("id")
        for p in players.values():
            st = ((p.get("stats") or {}).get("pitching") or {})
            if not st:
                continue
            starter = bool((p.get("gameStatus") or {}).get("isStarter"))
            out.append({
                "game_id": game_id, "pitcher_id": (p.get("person") or {}).get("id"),
                "team": team, "role": "SP" if starter else "RP",
                "ip": parse_ip(st.get("inningsPitched")),
                "er": st.get("earnedRuns"), "r": st.get("runs"),
                "k": st.get("strikeOuts"), "bb": st.get("baseOnBalls"),
                "h": st.get("hits"), "pitches": st.get("numberOfPitches"),
            })
    return [r for r in out if r["pitcher_id"]]


def parse_batting(box: dict, *, game_id: int) -> list[dict]:
    out = []
    for side in ("home", "away"):
        blk, players = _players(box, side)
        team = (blk.get("team") or {}).get("id")
        order = {int(pid): i + 1
                 for i, pid in enumerate(blk.get("battingOrder") or [])}
        for p in players.values():
            st = ((p.get("stats") or {}).get("batting") or {})
            if not st:
                continue
            pid = (p.get("person") or {}).get("id")
            out.append({
                "game_id": game_id, "batter_id": pid, "team": team,
                "order": order.get(int(pid)) if pid else None,
                "pa": st.get("plateAppearances"), "ab": st.get("atBats"),
                "h": st.get("hits"), "b2": st.get("doubles"),
                "b3": st.get("triples"), "hr": st.get("homeRuns"),
                "bb": st.get("baseOnBalls"), "hbp": st.get("hitByPitch"),
                "so": st.get("strikeOuts"),
            })
    return [r for r in out if r["batter_id"]]


def starters(pitch_rows: list[dict], home: int, away: int) -> tuple:
    """선발 둘. 없으면 None."""
    hs = next((r["pitcher_id"] for r in pitch_rows
               if r["role"] == "SP" and r["team"] == home), None)
    as_ = next((r["pitcher_id"] for r in pitch_rows
                if r["role"] == "SP" and r["team"] == away), None)
    return hs, as_


_G_COLS = ("game_id", "league", "season", "kickoff_utc", "home", "away", "park",
           "home_sp", "away_sp", "home_runs", "away_runs")


def upsert_games(con: sqlite3.Connection, rows: list[dict]) -> int:
    q = (f"INSERT INTO games ({', '.join(_G_COLS)}) "
         f"VALUES ({', '.join('?' * len(_G_COLS))}) "
         "ON CONFLICT(game_id) DO UPDATE SET "
         + ", ".join(f"{c}=excluded.{c}" for c in _G_COLS[1:]))
    con.executemany(q, [tuple(r.get(c) for c in _G_COLS) for r in rows])
    con.commit()
    return len(rows)


def upsert_pitch(con: sqlite3.Connection, rows: list[dict]) -> int:
    cols = ("game_id", "pitcher_id", "team", "role", "ip", "er", "r", "k",
            "bb", "h", "pitches")
    con.executemany(
        f"INSERT OR REPLACE INTO pitch_app ({', '.join(cols)}) "
        f"VALUES ({', '.join('?' * len(cols))})",
        [tuple(r.get(c) for c in cols) for r in rows])
    con.commit()
    return len(rows)


def upsert_bat(con: sqlite3.Connection, rows: list[dict]) -> int:
    cols = ("game_id", "batter_id", "team", "order", "pa", "ab", "h", "b2",
            "b3", "hr", "bb", "hbp", "so")
    quoted = ", ".join(f'"{c}"' for c in cols)
    con.executemany(
        f"INSERT OR REPLACE INTO bat_app ({quoted}) "
        f"VALUES ({', '.join('?' * len(cols))})",
        [tuple(r.get(c) for c in cols) for r in rows])
    con.commit()
    return len(rows)


# ── 다운로드 ──────────────────────────────────────────────────────────
#   🔴 `season` 파라미터만 쓴다(위 실측). 날짜 단일 조회는 경기를 놓친다.

async def fetch_season(client, season: int) -> dict:
    """정규시즌 일정 한 시즌. `gameType=R`."""
    r = await client.get(SCHEDULE, params={"sportId": 1, "season": int(season),
                                           "gameType": "R"})
    r.raise_for_status()
    return r.json()


async def fetch_box(client, game_pk: int) -> dict:
    r = await client.get(BOXSCORE.format(game_pk=int(game_pk)))
    r.raise_for_status()
    return r.json()


async def load_season(con, season: int, *, client=None, limit: int | None = None,
                      concurrency: int = 8) -> dict:
    """한 시즌을 SQLite 에 적재한다. 반환 `{games, pitch, bat, requests, sec}`.

    ⚠️ 경기별 박스스코어를 받으므로 요청 수가 곧 경기 수다. 동시 실행은
       `concurrency` 로 묶는다 — statsapi 에 예의를 지키고 우리도 안 막힌다.
    """
    import asyncio
    import time

    import httpx

    own = client is None
    client = client or httpx.AsyncClient(timeout=30.0)
    t0 = time.monotonic()
    reqs = 0
    try:
        sched = await fetch_season(client, season)
        reqs += 1
        games = parse_schedule(sched, season=season)
        if limit:
            games = games[:limit]
        sem = asyncio.Semaphore(concurrency)
        pitch_all: list[dict] = []
        bat_all: list[dict] = []

        async def one(g):
            nonlocal reqs
            async with sem:
                try:
                    box = await fetch_box(client, g["game_id"])
                    reqs += 1
                except Exception as exc:
                    logger.warning("[mbl] box 실패 game=%s: %s", g["game_id"], exc)
                    return
            pr = parse_pitching(box, game_id=g["game_id"])
            br = parse_batting(box, game_id=g["game_id"])
            hs, as_ = starters(pr, g["home"], g["away"])
            g["home_sp"], g["away_sp"] = hs, as_
            pitch_all.extend(pr)
            bat_all.extend(br)

        await asyncio.gather(*(one(g) for g in games))
        upsert_games(con, games)
        upsert_pitch(con, pitch_all)
        upsert_bat(con, bat_all)
        return {"games": len(games), "pitch": len(pitch_all),
                "bat": len(bat_all), "requests": reqs,
                "sec": round(time.monotonic() - t0, 1)}
    finally:
        if own:
            await client.aclose()
