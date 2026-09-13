"""MBL-1 — 야구 모델 로더 (야구 모델 지시문 2단계).

🔴 statsapi 는 **`season` 파라미터만 신뢰한다.** 실측 2026-09-13:
     schedule?sportId=1&season=2024&gameType=R  → totalGames=2469
     schedule?sportId=1&date=2024-07-01         → totalGames=3   ← 날짜 단일 조회 결함
   날짜별로 긁으면 경기를 통째로 놓친다.

⚠️ 팀·선수 키는 **statsapi id** 를 그대로 쓴다 — 이름 매칭을 피한다(2단계 지시).
⚠️ 머니라인은 **원값으로 저장**한다. 디빅은 4단계다.
"""
import json
import sqlite3

import pytest

from app.model_baseball import load as L


def test_시즌_파라미터를_쓴다():
    """🔴 날짜 단일 조회는 결함이 있다 — 시즌으로만 긁는다."""
    import inspect

    # 실제 **호출**만 본다 — 주석에 실측을 적는 것은 허용한다(그 근거가
    # 코드에서 떨어지면 다음 사람이 날짜 조회로 되돌린다)
    fs = inspect.getsource(L.fetch_season)
    assert '"season"' in fs, fs
    assert '"date"' not in fs, fs
    assert '"gameType": "R"' in fs, fs


_SCHED = {"dates": [{"date": "2024-04-01", "games": [{
    "gamePk": 745001, "gameDate": "2024-04-01T17:10:00Z",
    "teams": {"home": {"team": {"id": 147, "name": "New York Yankees"}},
              "away": {"team": {"id": 111, "name": "Boston Red Sox"}}},
    "venue": {"id": 3313, "name": "Yankee Stadium"},
    "status": {"codedGameState": "F"}}]}]}


def test_일정을_행으로_바꾼다():
    rows = L.parse_schedule(_SCHED, season=2024)
    assert len(rows) == 1
    g = rows[0]
    assert g["game_id"] == 745001 and g["league"] == "mlb" and g["season"] == 2024
    assert g["home"] == 147 and g["away"] == 111          # statsapi id
    assert g["park"] == 3313
    assert g["kickoff_utc"].startswith("2024-04-01T17:10")


def test_종료되지_않은_경기는_건너뛴다():
    s = json.loads(json.dumps(_SCHED))
    s["dates"][0]["games"][0]["status"]["codedGameState"] = "S"
    assert L.parse_schedule(s, season=2024) == []


_BOX = {"teams": {
    "home": {"team": {"id": 147},
             "battingOrder": [592450, 519317],
             "players": {
                 "ID592450": {"person": {"id": 592450},
                              "stats": {"batting": {"atBats": 4, "hits": 2, "doubles": 1,
                                                    "triples": 0, "homeRuns": 1,
                                                    "baseOnBalls": 0, "hitByPitch": 0,
                                                    "strikeOuts": 1, "plateAppearances": 4}}},
                 # ⚠️ [MBL-2] 종전 고정구는 `gameStatus.isStarter` 를 썼는데
                 #    statsapi 에 **그런 키가 없다**. 실제 신호로 바꿨다.
                 "ID543037": {"person": {"id": 543037},
                              "stats": {"pitching": {"gamesStarted": 1,
                                                     "inningsPitched": "6.1",
                                                     "earnedRuns": 2, "runs": 3,
                                                     "strikeOuts": 7, "baseOnBalls": 1,
                                                     "hits": 5, "numberOfPitches": 95}}}}},
    "away": {"team": {"id": 111}, "battingOrder": [], "players": {}}}}


def test_투구_기록을_뽑는다():
    rows = L.parse_pitching(_BOX, game_id=745001)
    assert len(rows) == 1
    r = rows[0]
    assert r["pitcher_id"] == 543037 and r["team"] == 147 and r["role"] == "SP"
    assert r["ip"] == pytest.approx(6 + 1 / 3)        # 6.1 = 6과 1/3이닝
    assert r["er"] == 2 and r["k"] == 7 and r["pitches"] == 95


@pytest.mark.parametrize("v,expect", [("6.1", 6 + 1/3), ("0.2", 2/3),
                                      ("7.0", 7.0), (None, 0.0), ("", 0.0)])
def test_이닝_표기를_바르게_읽는다(v, expect):
    """🔴 야구 이닝은 소수가 아니다 — `6.1` 은 6.1이 아니라 6과 1/3이다."""
    assert L.parse_ip(v) == pytest.approx(expect)


def test_타격_기록을_뽑는다():
    rows = L.parse_batting(_BOX, game_id=745001)
    assert len(rows) == 1
    r = rows[0]
    assert r["batter_id"] == 592450 and r["order"] == 1
    assert r["h"] == 2 and r["hr"] == 1 and r["pa"] == 4


def test_스키마가_지시문_표와_같다(tmp_path):
    db = tmp_path / "m.sqlite"
    con = sqlite3.connect(db)
    L.ensure_schema(con)
    cols = {t: {r[1] for r in con.execute(f"PRAGMA table_info({t})")}
            for t in ("games", "pitch_app", "bat_app")}
    assert {"game_id", "league", "season", "kickoff_utc", "home", "away", "park",
            "home_sp", "away_sp", "home_runs", "away_runs",
            "ml_open_h", "ml_open_a", "ml_close_h", "ml_close_a"} <= cols["games"]
    assert {"game_id", "pitcher_id", "team", "role", "ip", "er", "r", "k", "bb",
            "h", "pitches"} <= cols["pitch_app"]
    assert {"game_id", "batter_id", "team", "order", "pa", "ab", "h", "b2", "b3",
            "hr", "bb", "hbp", "so"} <= cols["bat_app"]
    con.close()


def test_같은_경기를_두_번_넣지_않는다(tmp_path):
    db = tmp_path / "m.sqlite"
    con = sqlite3.connect(db)
    L.ensure_schema(con)
    g = L.parse_schedule(_SCHED, season=2024)
    L.upsert_games(con, g)
    L.upsert_games(con, g)
    assert con.execute("SELECT count(*) FROM games").fetchone()[0] == 1
    con.close()


def test_배당은_원값으로_저장한다():
    """⚠️ 디빅은 4단계다. 여기서 확률로 바꾸지 않는다."""
    import inspect

    src = inspect.getsource(L)
    for bad in ("devig", "implied_prob", "1.0 /"):
        assert bad not in src, bad


# ── [MBL-2] 선발 식별

_BOX2 = {"teams": {"home": {
    "team": {"id": 147},
    "pitchers": [571760, 592351],
    "battingOrder": [],
    "players": {
        "ID571760": {"person": {"id": 571760},
                     "gameStatus": {"isCurrentPitcher": False, "isSubstitute": False},
                     "stats": {"pitching": {"gamesStarted": 1, "inningsPitched": "5.2",
                                            "earnedRuns": 3, "strikeOuts": 5}}},
        "ID592351": {"person": {"id": 592351},
                     "gameStatus": {"isCurrentPitcher": False, "isSubstitute": True},
                     "stats": {"pitching": {"gamesStarted": 0, "inningsPitched": "1.0",
                                            "earnedRuns": 0, "strikeOuts": 2}}}}},
    "away": {"team": {"id": 111}, "pitchers": [], "battingOrder": [], "players": {}}}}


def test_선발은_gamesStarted로_가른다():
    """🔴 **실측 2026-09-13**: `gameStatus` 에 `isStarter` 가 **없다**.
    내가 그 키를 가정해 한 시즌 2,429경기 전부 `home_sp = NULL` 이었다.
    확실한 신호는 `stats.pitching.gamesStarted == 1` 이다.
    """
    rows = L.parse_pitching(_BOX2, game_id=1)
    by = {r["pitcher_id"]: r["role"] for r in rows}
    assert by[571760] == "SP", rows
    assert by[592351] == "RP", rows


def test_gamesStarted가_없으면_첫_투수를_선발로_본다():
    """⚠️ 폴백. `teams.{side}.pitchers[0]` 가 선발이다(등판 순서)."""
    box = json.loads(json.dumps(_BOX2))
    for p in box["teams"]["home"]["players"].values():
        p["stats"]["pitching"].pop("gamesStarted", None)
    rows = L.parse_pitching(box, game_id=1)
    by = {r["pitcher_id"]: r["role"] for r in rows}
    assert by[571760] == "SP" and by[592351] == "RP", rows


def test_선발이_경기행에_실린다():
    rows = L.parse_pitching(_BOX2, game_id=1)
    hs, as_ = L.starters(rows, home=147, away=111)
    assert hs == 571760 and as_ is None
