"""[BAT-1] 타자 성적 적재. MLB statsapi·KBO 공식·NPB Yahoo 가 같은 표에 쓴다.

🔴 `pitcher_log` 와 **같은 규약**이다 — 파서가 리그마다 다르고 적재는 하나다.
   그래야 뒤에서 `starter_recent` 와 같은 방식으로 읽을 수 있다(사본 금지).

⚠️ **판정에는 아직 주입하지 않는다.** `app/engine/CLAUDE.md` 가 "경로가 생길 때
   3리그 동시에 넣는다"고 못박았다. 여기는 수집까지다.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_UPSERT = """
    INSERT INTO batter_appearances (
        game_id, sport, team, opponent, batter, slot, pos,
        ab, h, r, rbi, hr, bb, so, source)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
    ON CONFLICT (game_id, team, batter) DO UPDATE SET
        slot = EXCLUDED.slot,
        pos = EXCLUDED.pos,
        ab = EXCLUDED.ab,
        h = EXCLUDED.h,
        r = EXCLUDED.r,
        rbi = EXCLUDED.rbi,
        hr = EXCLUDED.hr,
        bb = EXCLUDED.bb,
        so = EXCLUDED.so,
        source = EXCLUDED.source
"""

_SIDES = """
    SELECT home, away FROM games WHERE id = $1
"""


async def store_batting(pool, game_id: int, sport: str, parsed: dict,
                        *, source: str) -> int:
    """`{"home": [...], "away": [...]}` 를 적재한다. 반환: 적재 행 수.

    팀·상대 이름은 **`games` 에서 읽는다** — 파서가 팀 이름을 만들지 않게 한다
    (박스스코어의 표기와 우리 표기가 갈리면 조회가 조용히 0이 된다).

    ⚠️ **멱등하다.** 같은 경기를 몇 번 적재해도 행이 늘지 않는다.
    """
    if pool is None or not parsed:
        return 0
    row = await pool.fetchrow(_SIDES, game_id)
    if row is None:
        logger.warning("[batter_log] game=%s 가 games 에 없다 — 적재 생략", game_id)
        return 0
    names = {"home": row["home"], "away": row["away"]}
    n = 0
    for side in ("home", "away"):
        team, opp = names[side], names["away" if side == "home" else "home"]
        for b in (parsed.get(side) or []):
            name = (b.get("batter") or "").strip()
            if not name:
                continue
            try:
                await pool.execute(
                    _UPSERT, game_id, sport, team, opp, name,
                    b.get("slot"), b.get("pos"), b.get("ab"), b.get("h"),
                    b.get("r"), b.get("rbi"), b.get("hr"), b.get("bb"),
                    b.get("so"), source)
                n += 1
            except Exception as exc:
                logger.warning("[batter_log] game=%s %s 적재 실패: %s",
                               game_id, name, exc)
    if n:
        logger.info("[batter_log] game=%s %s 타자 %d행 적재 (%s)",
                    game_id, sport, n, source)
    return n
