"""[BAT-1] 타자 개인 성적 수집 — 판정 재료의 절반이 비어 있었다.

🔴 **왜 (실측 2026-09-08).** 판정이 타자에 대해 아는 것과 투수에 대해 아는 것의
   두께가 다르다.

     투수  자료4  [{"innings":7.0,"r":1,"hits":4,"k":7,"bb":0,
                    "run_support":2,"date":"2026-09-02"}, ×5]   ← 개인 경기별 로그
           자료9 불펜 최근 3경기 · 자료10 이닝 분포 · 자료14(실측 80%가 투수·불펜)

     타자  자료1  팀 3경기 합계
           자료3  [{"slot":1,"name":"度会 隆輝","pos":"左"}, …]  ← **이름·포지션뿐, 숫자 0**
           자료6  "사실이 아니라 해석이다"(프롬프트 자신의 말)

   프롬프트가 그 빈자리를 **"순서가 곧 정보다"** 로 메운다. 숫자가 없으니 타순
   순서에서 추론하라는 뜻이다.

   결과(경기 단위 `is_final`, 157경기, 기준 54.8%):
     잠정(투수 재료만으로 낸 1차)  27경기  **70.4%**
     확정(라인업 받고 재판정)     130경기  **51.5%**
   **이름 아홉 개가 도착해 재판정을 촉발하고, 그 재판정이 예측을 나쁘게 한다.**

🔴 **수집원이 없는 게 아니라 이미 손에 들어오는 것을 버리고 있었다:**
     MLB  statsapi 박스스코어 `teams.*.players.*.stats.batting` — 선수별
          `atBats`·`hits`·`homeRuns`·`rbi` … **11명분이 응답에 온다.**
          `mlb_boxscore.parse_pitching` 이 투수만 읽고 타자를 버린다.
     KBO  공식 박스스코어 `arrHitter` **123,623바이트** (arrPitcher 50,043과 같은 구조)
     NPB  Yahoo `/stats` 의 `打撃成績` 표 — 打率·打数·得点·安打·打点·三振·四球·
          死球·犠打·盗塁·失策·本塁打. **투수 자료보다 두껍다.**

⚠️ **판정에는 아직 주입하지 않는다.** `app/engine/CLAUDE.md` 가
   "경로가 생길 때 **3리그 동시**에 넣는다"고 못박았다. 여기(BAT-1)는 표와
   MLB 파서까지다. KBO·NPB 파서가 붙은 뒤에 자료3 을 채운다.
"""
from __future__ import annotations

import pytest


def _mlb_box(*players):
    """statsapi `/game/{pk}/boxscore` 응답 모양(필요한 부분만)."""
    return {"teams": {
        "home": {"team": {"name": "Los Angeles Dodgers"},
                 "players": {f"ID{p['id']}": p["blob"] for p in players}},
        "away": {"team": {"name": "Cincinnati Reds"}, "players": {}}}}


def _bat(pid, name, order=None, **stats):
    blob = {"person": {"id": pid, "fullName": name},
            "position": {"abbreviation": "CF"},
            "stats": {"batting": stats}}
    if order is not None:
        blob["battingOrder"] = str(order)
    return {"id": pid, "blob": blob}


# ── 표가 있는가 ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_타자_표가_투수_표와_대칭이다(db_pool):
    """🔴 `pitcher_appearances` 를 본떠 만든다 — 같은 모양이어야 같은 규약으로 읽는다."""
    cols = {r["column_name"] for r in await db_pool.fetch(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='batter_appearances'")}
    assert cols, "batter_appearances 표가 없다"
    for need in ("game_id", "sport", "team", "opponent", "batter",
                 "slot", "pos", "ab", "h", "r", "rbi", "hr", "bb", "so", "source"):
        assert need in cols, f"{need} 칸이 없다"


@pytest.mark.asyncio
async def test_경기당_선수당_한_행이다(db_pool):
    """⚠️ 유니크가 없으면 폴링마다 같은 타석이 쌓인다."""
    rows = await db_pool.fetch("""
        SELECT pg_get_indexdef(i.oid) def FROM pg_index ix
        JOIN pg_class i ON i.oid=ix.indexrelid JOIN pg_class t ON t.oid=ix.indrelid
        WHERE t.relname='batter_appearances' AND ix.indisunique""")
    defs = " ".join(r["def"] for r in rows)
    assert "game_id" in defs and "batter" in defs, f"유니크 제약이 없다: {defs}"


@pytest.mark.asyncio
async def test_경기가_지워지면_함께_지워진다(db_pool):
    """⚠️ CASCADE 여야 GM-2 의 카탈로그 기반 이관에 자동으로 들어간다."""
    from app.collectors.game_match import _CASCADE_TABLES

    tabs = {r["t"] for r in await db_pool.fetch(_CASCADE_TABLES)}
    assert "batter_appearances" in tabs, (
        "CASCADE 가 아니다 — 병합 이관 목록에 자동으로 들어가지 않는다")


# ── MLB 파서 ────────────────────────────────────────────────
def test_mlb_박스스코어에서_타자_성적을_읽는다():
    """🔴 종전에는 이 응답을 받아 놓고 투수만 읽고 버렸다."""
    from app.collectors.mlb_boxscore import parse_batting

    box = _mlb_box(
        _bat(1, "Shohei Ohtani", order=100, atBats=4, hits=2, runs=1, rbi=3,
             homeRuns=1, baseOnBalls=0, strikeOuts=1),
        _bat(2, "Mookie Betts", order=200, atBats=5, hits=1, runs=0, rbi=0,
             homeRuns=0, baseOnBalls=1, strikeOuts=2))
    out = parse_batting(box)
    assert set(out) == {"home", "away"}, out
    home = {b["batter"]: b for b in out["home"]}
    assert set(home) == {"Shohei Ohtani", "Mookie Betts"}
    o = home["Shohei Ohtani"]
    assert (o["ab"], o["h"], o["r"], o["rbi"], o["hr"], o["bb"], o["so"]) == (4, 2, 1, 3, 1, 0, 1)
    assert o["slot"] == 1, "battingOrder 100 → 1번 타순"


def test_타석이_없는_선수는_싣지_않는다():
    """⚠️ 대주자·투수는 `atBats` 가 없다. 0으로 채우면 타율이 오염된다."""
    from app.collectors.mlb_boxscore import parse_batting

    out = parse_batting(_mlb_box(
        _bat(3, "Pinch Runner", order=300),
        _bat(4, "Starting Pitcher", order=None, atBats=0, hits=0)))
    names = {b["batter"] for b in out["home"]}
    assert "Pinch Runner" not in names, "타석 기록이 없는 선수를 실었다"


def test_교체_타순은_선발_슬롯으로_읽는다():
    """battingOrder 는 `501` 처럼 소수 자리로 교체를 표시한다 — 앞자리가 타순이다."""
    from app.collectors.mlb_boxscore import parse_batting

    out = parse_batting(_mlb_box(
        _bat(5, "Sub Guy", order=501, atBats=2, hits=1)))
    assert out["home"][0]["slot"] == 5


@pytest.mark.asyncio
async def test_적재는_멱등하다(db_pool):
    """⚠️ 폴링·백필이 몇 번이고 다시 돌 수 있어야 한다."""
    from app.collectors.mlb_boxscore import parse_batting
    from app.collectors.batter_log import store_batting

    gid = await db_pool.fetchval(
        """INSERT INTO games (sport, league, ext_id, starts_at, home, away, status)
           VALUES ('mlb','MLB','bat-1','2026-04-01T23:05:00Z',
                   'Los Angeles Dodgers','Cincinnati Reds','final') RETURNING id""")
    box = _mlb_box(_bat(6, "Freddie Freeman", order=300, atBats=4, hits=3, rbi=2))
    parsed = parse_batting(box)
    await store_batting(db_pool, gid, "mlb", parsed, source="statsapi")
    await store_batting(db_pool, gid, "mlb", parsed, source="statsapi")
    n = await db_pool.fetchval(
        "SELECT count(*) FROM batter_appearances WHERE game_id=$1", gid)
    assert n == 1, f"같은 타석이 {n}행 쌓였다"
