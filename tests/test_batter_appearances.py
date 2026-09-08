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


# ═══════════════ [BAT-2] KBO·NPB 파서 — 열 순서가 리그마다 다르다
#
# 🔴 **원본 구조를 실제로 열어 확인했다(2026-09-08). 추측하지 않았다.**
#
#   KBO 공식 `arrHitter` — 원소 2개(0=원정, 1=홈), 각 `table1/2/3`:
#     table1 = [타순, 포지션, 이름]
#     table3 = [타수, 안타, 타점, 득점, 타율]      ← **헤더가 없다**
#     교체 선수는 **같은 타순 번호를 공유**한다(5,5 / 9,9,9,9)
#     검증: 두산 4열 합계 1 = DB home_score 1 · 양의지(타점1·득점0)·
#           안재석(타점0·득점1)이 의미와 맞는다
#
#   NPB Yahoo `/stats` 의 `打撃成績` — **헤더가 있다**:
#     位置 | 選手名 | 打率 | 打数 | 得点 | 安打 | 打点 | 三振 | 四球 | 死球 | …
#
# ⚠️ **두 리그의 열 순서가 다르다** — KBO 는 `타수·안타·타점·득점`,
#    NPB 는 `打数·得点·安打·打点`. 확인하지 않았으면 득점과 안타를 뒤바꿨다.
#    NPB 는 헤더로 매핑하고, 헤더가 없는 KBO 는 **합계 대조 가드**를 둔다.


def _kbo_block(rows1, rows3, tfoot=None):
    import json

    def tbl(rows, tf=None):
        return json.dumps({
            "rows": [{"row": [{"Text": c} for c in r]} for r in rows],
            "tfoot": [{"row": [{"Text": c} for c in tf]}] if tf else [],
        }, ensure_ascii=False)
    return {"table1": tbl(rows1), "table2": tbl([]), "table3": tbl(rows3, tfoot)}


def test_kbo_타자표를_읽는다():
    from app.collectors.kbo_boxscore import parse_batting

    box = {"arrHitter": [
        _kbo_block([["1", "二", "신민재"], ["2", "중", "박해민"]],
                   [["4", "1", "0", "1", "0.263"], ["4", "1", "0", "0", "0.286"]],
                   ["8", "2", "0", "1", "0.270"]),
        _kbo_block([["1", "유", "박찬호"]], [["3", "0", "0", "0", "0.291"]],
                   ["3", "0", "0", "0", "0.291"]),
    ]}
    out = parse_batting(box)
    assert set(out) == {"home", "away"}
    # arrHitter[0] 이 원정이다 (실측: LG@두산 에서 [0]=LG)
    away = {b["batter"]: b for b in out["away"]}
    assert set(away) == {"신민재", "박해민"}
    s = away["신민재"]
    assert (s["slot"], s["pos"], s["ab"], s["h"], s["rbi"], s["r"]) == (
        1, "2루수", 4, 1, 0, 1)   # 🔴 `normalize_position` 원본을 쓴다
    assert {b["batter"] for b in out["home"]} == {"박찬호"}


def test_kbo_교체선수는_같은_타순을_쓴다():
    """실측: 두산 9번 자리에 정수빈·박지훈·류승민·김기연 네 명이 들어갔다."""
    from app.collectors.kbo_boxscore import parse_batting

    box = {"arrHitter": [
        _kbo_block([["9", "중", "정수빈"], ["9", "타중", "박지훈"]],
                   [["2", "0", "0", "0", "0.258"], ["1", "0", "0", "0", "0.264"]]),
        _kbo_block([], []),
    ]}
    out = parse_batting(box)
    assert [b["slot"] for b in out["away"]] == [9, 9]
    assert [b["batter"] for b in out["away"]] == ["정수빈", "박지훈"]
    assert [b["sub"] for b in out["away"]] == [False, True]


def test_kbo_열이_바뀌면_알아챈다():
    """🔴 헤더가 없으니 열 순서를 합계로 검증한다 — 조용히 뒤바뀌면 안 된다."""
    from app.collectors.kbo_boxscore import parse_batting

    box = {"arrHitter": [
        _kbo_block([["1", "二", "신민재"]], [["4", "1", "0", "1", "0.263"]],
                   ["99", "99", "99", "99", "0.000"]),   # 합계가 행과 안 맞는다
        _kbo_block([], []),
    ]}
    out = parse_batting(box)
    assert out.get("_mismatch"), "합계 불일치를 알리지 않는다"


_NPB_HEAD = ("<tr><th>位置</th><th>選手名</th><th>打率</th><th>打数</th><th>得点</th>"
             "<th>安打</th><th>打点</th><th>三振</th><th>四球</th><th>死球</th>"
             "<th>犠打</th><th>盗塁</th><th>失策</th><th>本塁打</th></tr>")


def _npb_table(rows):
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table>{_NPB_HEAD}{body}</table>"


def test_npb_타자표를_헤더로_읽는다():
    """⚠️ NPB 는 `打数·得点·安打·打点` 순이다 — KBO(`타수·안타·타점·득점`)와 다르다."""
    from app.collectors.npb_boxscore import parse_batting

    away = _npb_table([
        ["(右)", "カナリオ", ".246", "4", "2", "1", "0", "1", "1", "0", "0", "0", "0", "0"],
        ["(二)", "滝澤 夏央", ".280", "4", "0", "0", "0", "1", "0", "0", "0", "0", "0", "0"],
        ["合計", "", "8", "2", "1", "0", "2", "1", "0", "0", "0", "0", "0"],
    ])
    home = _npb_table([
        ["(中)", "岡林 勇希", ".234", "4", "1", "1", "3", "0", "0", "0", "0", "0", "0", "0"],
    ])
    out = parse_batting(away + home)
    assert set(out) == {"home", "away"}
    assert len(out["away"]) == 2, out["away"]
    c = {r["batter"]: r for r in out["away"]}["カナリオ"]
    assert c["ab"] == 4 and c["r"] == 2 and c["h"] == 1 and c["rbi"] == 0
    assert c["so"] == 1 and c["bb"] == 1 and c["hr"] == 0
    assert c["pos"] == "右" and c["slot"] == 1
    assert {r["batter"] for r in out["home"]} == {"岡林 勇希"}


def test_npb_교체선수는_앞_타순을_이어받는다():
    """🔴 실측: 괄호 있는 위치가 선발, 괄호 없는 행(`投`·`打`)이 교체다."""
    from app.collectors.npb_boxscore import parse_batting

    t = _npb_table([
        ["(二)", "福永 裕基", ".282", "4", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0"],
        ["投", "松山 晋也", "-", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0"],
        ["(遊)", "村松 開人", ".259", "4", "0", "0", "0", "0", "0", "0", "0", "0", "0", "0"],
    ])
    out = parse_batting(t + t)
    assert [(r["batter"], r["slot"]) for r in out["away"]] == [
        ("福永 裕基", 1), ("松山 晋也", 1), ("村松 開人", 2)]
    assert out["away"][1]["ab"] == 0
    assert [r["sub"] for r in out["away"]] == [False, True, False]


def test_npb_헤더가_없으면_지어내지_않는다():
    """⚠️ 위치로 추측하면 得点과 安打가 뒤바뀐다. 헤더가 없으면 빈 목록이다."""
    from app.collectors.npb_boxscore import parse_batting

    out = parse_batting("<table><tr><td>4</td><td>2</td></tr></table>")
    assert out == {"home": [], "away": []}
