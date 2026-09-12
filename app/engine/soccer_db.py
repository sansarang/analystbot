"""[SOC-10] `lineups` 테이블 → `jg`. 제미나이가 **DB에서** 보게 하는 다리.

사용자 지시 2026-09-13: "부상자 명단 라인업 등등 경기와 관련된 내용을 db에
저장하면 된다..그리고 제미나이가 판단해서 가져다 쓰면 된다..그게 우리 원칙이다"

🔴 그 원칙은 `dbref.py` 머리말에 이미 있다 — "경기 관련 DB를 통째로 주고,
   AI가 그 안에서 필요한 걸 찾아 쓰게 한다". **축구 자료만 그 통에 없었다.**
⚠️ 새 테이블을 만들지 않는다 — 위성이 `lineups` 에 쓴 것을 그대로 읽는다.
   `batting_order`=선발, `scratches`=결장자, `starter`=포메이션.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

SQL = """
    SELECT side, source, status, starter, batting_order, scratches
      FROM lineups
     WHERE game_id = $1
     ORDER BY captured_at
"""


def _arr(v) -> list:
    if isinstance(v, list):
        return v
    try:
        out = json.loads(v or "[]")
    except (TypeError, ValueError):
        return []
    return out if isinstance(out, list) else []


async def attach(pool, jg: dict) -> None:
    """이 경기의 라인업·결장자를 DB에서 읽어 `jg` 에 붙인다.

    ⚠️ 실패는 조용한 통과다 — DB가 없다고 판정을 막지 않는다.
    """
    if pool is None or not jg.get("game_id"):
        return
    try:
        rows = await pool.fetch(SQL, jg["game_id"])
    except Exception as exc:
        logger.warning("[soccer_db] 조회 실패 game=%s: %s", jg.get("game_id"), exc)
        return
    lineup: dict[str, dict] = {}
    inj: dict[str, list] = {}
    for r in rows or []:
        side = r["side"]
        starters, outs = _arr(r["batting_order"]), _arr(r["scratches"])
        if r["status"] == "injury":
            if outs:
                inj[side] = outs
            continue
        if starters:
            lineup[side] = {"포메이션": r["starter"] or "", "선발": starters,
                            "교체": outs}
    if lineup:
        jg["soccer_lineup"] = lineup
    if inj:
        jg["soccer_injuries"] = inj
    logger.info("[soccer_db] game=%s 라인업 %d팀 · 결장자 %d팀",
                jg.get("game_id"), len(lineup), len(inj))
