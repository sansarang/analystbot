"""[투명 리포트 G1] 경기 서사 원장 — 경기 하나가 어떻게 통과했는가.

🔴 **원장은 로그보다 많이 알지 않는다.** 각 행의 `summary` 는 그 자리에서
   이미 찍히는 로그 문자열을 **그대로 복사**한 것이다. 새 계측을 추가해
   원장에만 있는 사실을 만들면, 리포트를 로그로 검증할 수 없게 된다 —
   그 순간 리포트는 "투명"이 아니라 제2의 주장이 된다.

   그래서 호출 규약이 이렇다:
       msg = "[materials] game=%s …" % (...)
       logger.info(msg)
       await note(pool, ..., summary=msg)
   포맷을 두 번 쓰지 않는다. 두 번 쓰면 언젠가 갈린다.

⚠️ **기록·표시 층이다.** 판정·게이트·발송은 이 테이블을 읽지 않는다.
⚠️ **절대 예외를 밖으로 던지지 않는다.** 원장 적재 실패가 판정이나 발송을
   막으면 기록하려다 본체를 죽이는 것이다. 실패는 debug 로그 한 줄이다.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

#: 단계 이름. 리포트 절 구성이 이 순서를 따른다 — 문자열을 호출부에 흩지 않는다.
COLLECT = "수집"
ASSEMBLE = "조립"
JUDGE = "판정"
REJUDGE = "재판정"
DEEPSEARCH = "딥서치"
GATE = "게이트"
SEND = "발송"

STAGES: tuple[str, ...] = (COLLECT, ASSEMBLE, JUDGE, REJUDGE, DEEPSEARCH,
                           GATE, SEND)

_INSERT = """
    INSERT INTO game_trace (game_id, sport, slate_date, stage, summary, ref)
    VALUES ($1, $2, $3, $4, $5, $6)
"""


async def note(pool, *, game_id, sport: str, date: str, stage: str,
               summary: str, ref: dict | None = None) -> bool:
    """원장 1행. 적재했으면 True. **어떤 경우에도 예외를 던지지 않는다.**"""
    if pool is None or game_id is None or not summary:
        return False
    if stage not in STAGES:
        # 🔴 오타 하나가 리포트에서 그 단계를 통째로 사라지게 한다.
        #    조용히 넣지 말고 거절하고 남긴다.
        logger.warning("[trace] 알 수 없는 단계 %r — 적재하지 않는다", stage)
        return False
    try:
        await pool.execute(_INSERT, int(game_id), (sport or "").lower(),
                           date or "", stage, summary[:2000],
                           json.dumps(ref, ensure_ascii=False,
                                      default=str) if ref else None)
        return True
    except Exception as exc:
        logger.debug("[trace] 적재 실패 game=%s stage=%s: %s", game_id, stage, exc)
        return False


async def timeline(pool, game_id) -> list[dict]:
    """그 경기의 전 이력. **시간순** — 리포트가 이 순서를 그대로 쓴다."""
    if pool is None or game_id is None:
        return []
    try:
        rows = await pool.fetch(
            "SELECT stage, at, summary, ref FROM game_trace"
            " WHERE game_id = $1 ORDER BY at, id", int(game_id))
    except Exception as exc:
        logger.debug("[trace] 조회 실패 game=%s: %s", game_id, exc)
        return []
    out = []
    for r in rows:
        ref = r["ref"]
        if isinstance(ref, str):
            try:
                ref = json.loads(ref)
            except ValueError:
                ref = None
        out.append({"stage": r["stage"], "at": r["at"],
                    "summary": r["summary"], "ref": ref})
    return out


async def slate(pool, sport: str, date: str) -> dict[int, list[dict]]:
    """슬레이트 전체의 원장. {game_id: [행…]}. 없으면 빈 dict."""
    if pool is None:
        return {}
    try:
        rows = await pool.fetch(
            "SELECT game_id, stage, at, summary FROM game_trace"
            " WHERE sport = $1 AND slate_date = $2 ORDER BY game_id, at, id",
            (sport or "").lower(), date or "")
    except Exception as exc:
        logger.debug("[trace] 슬레이트 조회 실패 %s %s: %s", sport, date, exc)
        return {}
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(int(r["game_id"]), []).append(
            {"stage": r["stage"], "at": r["at"], "summary": r["summary"]})
    return out
