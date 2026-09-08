"""[GM-4] 중복이 셋 이상이면 이관이 터지고 **표 전체를 잃는다** — GM-2 의 구멍.

🔴 **재검토에서 나왔다(2026-09-09).** `_move_cascade_rows` 의 충돌 검사는
   `keep` 쪽만 본다:
       NOT EXISTS (SELECT 1 FROM t k WHERE k.game_id = keep AND k.<키> = s.<키>)
   그래서 **dup 끼리 같은 키를 갖고 keep 에는 없을 때** 둘 다 검사를 통과하고,
   같은 UPDATE 안에서 둘이 동시에 keep 으로 가 유니크 제약을 깬다.

   실측 재현(로컬 DB, 합성 경기 3행):
       [game_match] batter_appearances 이관 실패 — 건너뜀:
         duplicate key value violates unique constraint
         "batter_appearances_game_id_team_batter_key"
       결과 {'moved': 0, 'dropped': 0, 'tables': 9}
       keep 0행 · dup 잔여 2행 → **2행 손실**

⚠️ 손실이 두 겹이다.
   ① 예외가 나면 `continue` 라 **그 표를 통째로 건너뛴다** — 충돌하지 않는
      행까지 함께 CASCADE 로 사라진다.
   ② `dropped` 가 0으로 남아 **요약이 손실을 축소 보고**한다. GM-2 의 존재
      이유가 "조용한 삭제를 시끄러운 삭제로 바꾸는 것"인데 조용해진다.

⚠️ `pitcher_appearances` 도 `UNIQUE (game_id, team, pitcher)` 다 — GM-2 가
   지키려고 만든 바로 그 표가 이 구멍에 걸린다.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

_G = ("INSERT INTO games (sport, league, ext_id, starts_at, home, away, status) "
      "VALUES ('gm4','T',$1,$2,'H팀','A팀','final') RETURNING id")
_B = ("INSERT INTO batter_appearances (game_id, sport, team, opponent, batter,"
      " slot, pos, ab, h, r, rbi, source) "
      "VALUES ($1,'gm4','H팀','A팀',$2,1,'중',4,1,0,0,'t')")


async def _three(pool):
    base = datetime(2026, 1, 2, 3, 0, tzinfo=UTC)
    ids = []
    for k in range(3):
        ids.append(await pool.fetchval(_G, f"gm4:{k}",
                                       base + timedelta(minutes=30 * k)))
    return ids[0], ids[1:]


async def test_dup끼리_충돌해도_표를_통째로_잃지_않는다(db_pool):
    """🔴 핵심. 충돌하는 행만 남고, 충돌하지 않는 행은 옮겨져야 한다."""
    from app.collectors.game_match import _move_cascade_rows

    keep, dups = await _three(db_pool)
    # 둘 다 '홍길동'(충돌) · dup[0] 은 '이순신'(충돌 없음)도 갖는다
    for gid in dups:
        await db_pool.execute(_B, gid, "홍길동")
    await db_pool.execute(_B, dups[0], "이순신")

    res = await _move_cascade_rows(db_pool, keep, dups)

    moved = {r["batter"] for r in await db_pool.fetch(
        "SELECT batter FROM batter_appearances WHERE game_id = $1", keep)}
    assert "이순신" in moved, ("충돌하지 않는 행까지 잃었다 — "
                               f"표를 통째로 건너뛴 것이다. {res}")
    assert "홍길동" in moved, "충돌하는 키도 한 행은 살아남아야 한다"
    left = await db_pool.fetchval(
        "SELECT count(*) FROM batter_appearances WHERE game_id = ANY($1::bigint[])",
        dups)
    assert left == 1, f"남는 것은 중복된 '홍길동' 한 행뿐이어야 한다 (남음 {left})"


async def test_잃는_행을_계수가_축소보고하지_않는다(db_pool):
    """⚠️ GM-2 의 존재 이유가 '조용한 삭제를 시끄러운 삭제로' 바꾸는 것이다."""
    from app.collectors.game_match import _move_cascade_rows

    keep, dups = await _three(db_pool)
    for gid in dups:
        await db_pool.execute(_B, gid, "홍길동")

    res = await _move_cascade_rows(db_pool, keep, dups)
    left = await db_pool.fetchval(
        "SELECT count(*) FROM batter_appearances WHERE game_id = ANY($1::bigint[])",
        dups)
    assert res["dropped"] == left, (
        f"CASCADE 로 사라질 행 {left} 인데 dropped={res['dropped']} 로 보고한다")
    assert res["moved"] >= 1, res


async def test_투수표도_같은_보호를_받는다(db_pool):
    """⚠️ `pitcher_appearances` 는 GM-2 가 지키려고 만든 바로 그 표다."""
    from app.collectors.game_match import _move_cascade_rows

    keep, dups = await _three(db_pool)
    for gid in dups:
        await db_pool.execute(
            "INSERT INTO pitcher_appearances (game_id, sport, team, opponent,"
            " pitcher, is_starter, innings, source) "
            "VALUES ($1,'gm4','H팀','A팀','류현진',TRUE,6.0,'t')", gid)
    await db_pool.execute(
        "INSERT INTO pitcher_appearances (game_id, sport, team, opponent,"
        " pitcher, is_starter, innings, source) "
        "VALUES ($1,'gm4','H팀','A팀','오승환',FALSE,1.0,'t')", dups[0])

    await _move_cascade_rows(db_pool, keep, dups)
    names = {r["pitcher"] for r in await db_pool.fetch(
        "SELECT pitcher FROM pitcher_appearances WHERE game_id = $1", keep)}
    assert names == {"류현진", "오승환"}, names
