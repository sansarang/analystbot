"""[§9-라인업 의도] 라인업 관측을 **이력으로 쌓고** 평소 모습을 만든다.

`lineups` 테이블은 경기당 최종 1행만 남기므로 "18:05에 4번이 빠졌다"가 사라진다.
→ `lineup_events`에 관측할 때마다 append 하고, 팀별 과거 경기에서 평소를 만든다.

⚠️ **같은 라인업을 반복 저장하지 않는다.** 폴링이 10분마다 도는데 그대로 쌓으면
   "변경 이력"이 아니라 폴링 로그가 된다. 유일 제약이 그것을 막는다.
"""
from __future__ import annotations

import json
import logging

from app.engine.lineup_diff import USUAL_WINDOW, parse_order, usual_from

logger = logging.getLogger(__name__)

_INSERT = """
    INSERT INTO lineup_events (game_id, side, team, batting_order, starter,
                               source, is_final, observed_at)
    VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, now())
    ON CONFLICT (game_id, side, batting_order) DO UPDATE
       SET is_final = lineup_events.is_final OR EXCLUDED.is_final
    RETURNING (xmax = 0) AS inserted
"""


async def record(pool, game_id, side: str, team: str | None, order_text,
                 starter: str | None = None, source: str = "crawler",
                 is_final: bool = False) -> bool:
    """관측 1건. **새 라인업일 때만** True를 돌려준다(= 변경이 있었다)."""
    if not pool or not game_id or side not in ("home", "away"):
        return False
    parsed = parse_order(order_text)
    if not parsed:
        return False
    blob = json.dumps([f"{n}({p})" if p else n for n, p in parsed],
                      ensure_ascii=False)
    try:
        async with pool.acquire() as con:
            return bool(await con.fetchval(_INSERT, int(game_id), side, team,
                                           blob, starter, source, is_final))
    except Exception as exc:            # 이력 기록이 분석을 막지 않는다
        logger.warning("[라인업이력] 기록 실패 %s/%s: %s", game_id, side, exc)
        return False


def _as_dt(v):
    """문자열 시각을 datetime으로. asyncpg는 str을 timestamptz로 안 받는다.

    ⚠️ 이 프로젝트에서 같은 유형의 사고가 세 번 났다(`$4::timestamptz` 캐스트,
       `apply_result`, 그리고 여기). 호출부마다 고치지 말고 **경계에서 흡수**한다.
    """
    from datetime import datetime

    if v is None or isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


async def history(pool, sport: str, team: str, before, limit: int = USUAL_WINDOW
                  ) -> list[list[tuple[str, str]]]:
    """그 팀의 **과거 경기** 라인업들 (최신순). 오늘 경기는 제외한다.

    ⚠️ `before`(오늘 경기 시각) 이전만 본다 — 오늘 라인업을 평소에 넣으면
       자기 자신과 비교하게 되어 변경점이 영원히 0이 된다.
    """
    before = _as_dt(before)
    if not pool or not team or before is None:
        return []
    rows = await pool.fetch(
        """SELECT e.batting_order, e.source FROM lineup_events e
           JOIN games g ON g.id = e.game_id
           WHERE g.sport = $1 AND e.team = $2 AND g.starts_at < $3
             AND NOT e.contaminated
           ORDER BY g.starts_at DESC, e.observed_at DESC
           LIMIT $4""", sport, team, before, int(limit))
    out = []
    for r in rows:
        raw = r["batting_order"]
        out.append(parse_order(json.loads(raw) if isinstance(raw, str) else raw))
    return out


# 출처별 사람이 읽을 이름 — **두 소스는 같은 것이 아니다.**
SOURCE_KR = {"boxscore": "실제 출전 기록", "crawler": "발표 라인업",
             "statsapi": "발표 라인업"}


async def sources(pool, sport: str, team: str, before,
                  limit: int = USUAL_WINDOW) -> dict[str, int]:
    """평소 기준이 **어느 출처로 만들어졌는지**. 섞였으면 둘 다 센다."""
    if not pool or not team:
        return {}
    before = _as_dt(before)
    if before is None:
        return {}
    rows = await pool.fetch(
        """SELECT e.source, count(*) AS n FROM lineup_events e
           JOIN games g ON g.id = e.game_id
           WHERE g.sport = $1 AND e.team = $2 AND g.starts_at < $3
           GROUP BY e.source""", sport, team, before)
    return {r["source"]: r["n"] for r in rows}


def source_note(counts: dict[str, int]) -> str:
    """"실제 출전 기록 10경기" 같은 한 줄.

    ⚠️ 박스스코어는 **실제 출전 기록**이지 발표 라인업이 아니다. 경기 중 교체가
       섞일 수 있고, 발표 후 경기 전 교체는 아예 알 수 없다. 같은 것처럼
       쓰면 안 되므로 기준을 낼 때마다 어느 쪽인지 밝힌다.
    """
    if not counts:
        return ""
    bits = [f"{SOURCE_KR.get(k, k)} {v}경기" for k, v in sorted(counts.items())]
    return " + ".join(bits)


async def usual(pool, sport: str, team: str, before) -> dict:
    """그 팀의 평소 라인업. 표본 미달이면 빈 dict. 출처를 함께 담는다."""
    u = usual_from(await history(pool, sport, team, before))
    if u:
        u["sources"] = await sources(pool, sport, team, before)
        u["source_note"] = source_note(u["sources"])
    return u


async def changes_since(pool, game_id, side: str) -> list[dict]:
    """이 경기에서 **언제 무엇이 바뀌었는지**. 관측 시각과 함께 돌려준다.

    "18:05에 4번 타자가 빠졌다"는 그 자체로 신호다 — 시각을 버리면 안 된다.
    """
    if not pool or not game_id:
        return []
    rows = await pool.fetch(
        """SELECT batting_order, observed_at, is_final FROM lineup_events
           WHERE game_id = $1 AND side = $2 AND NOT contaminated
           ORDER BY observed_at""",
        int(game_id), side)
    out, prev = [], None
    for r in rows:
        raw = r["batting_order"]
        cur = parse_order(json.loads(raw) if isinstance(raw, str) else raw)
        if prev is not None:
            gone = [n for n, _ in prev if n not in {x for x, _ in cur}]
            added = [n for n, _ in cur if n not in {x for x, _ in prev}]
            if gone or added:
                bits = []
                if gone:
                    bits.append("빠짐 " + ", ".join(gone))
                if added:
                    bits.append("투입 " + ", ".join(added))
                out.append({"at": r["observed_at"], "is_final": r["is_final"],
                            "detail": " · ".join(bits)})
        prev = cur
    return out
