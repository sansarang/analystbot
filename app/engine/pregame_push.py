"""KBO·NPB 당일 예측 카드 — 매일 17:45 KST에 한꺼번에 발송.

사용자 지시(2026-08-28):
  · 라인업 공시: KBO 경기 1시간 전, NPB 30분 전 (둘 다 17:30).
  · 그 다음 공통 발송: 17:45. 경기마다 15분 전이 아니다.
  · MLB·축구는 요청할 때만. 베팅 집행 없음.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from app import notify as _notify_mod
from app.engine.lineup_timing import _parse
from app.pipeline import (
    DETAIL_SEP,
    ensure_analysis_cache,
    render_game_easy,
    today_kst,
)
from app.collectors.crawler_feed import load_snapshot, mark_cancelled_games

logger = logging.getLogger(__name__)

SPORTS = ("kbo", "npb")
PUSH_HOUR = 17
PUSH_MINUTE = 45
SENT_TTL_SEC = 12 * 3600
SPORT_LABEL = {"kbo": "KBO", "npb": "NPB"}
TELEGRAM_LIMIT = 4096


def sent_key(game_id: int) -> str:
    return f"pregame_push:{game_id}"


def still_upcoming(starts_at, now=None) -> bool:
    """아직 시작하지 않았는가. 이미 시작한 경기는 보내지 않는다."""
    d = _parse(starts_at)
    if d is None:
        return False
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return (d - now).total_seconds() > 0


def header_line(sport: str) -> str:
    label = SPORT_LABEL.get(sport, sport.upper())
    return f"⏰ {label} · {PUSH_HOUR:02d}:{PUSH_MINUTE:02d} 예측"


def compose_card(jg: dict, news: str, sport: str) -> str:
    return f"{header_line(sport)}\n{render_game_easy(jg, news)}"


def missing_cache_text(sport: str, home: str, away: str) -> str:
    return (
        f"{header_line(sport)}\n"
        f"{away} @ {home}\n"
        "오늘 분석 캐시가 없어 예측을 만들지 못했습니다."
    )


def missing_game_text(sport: str, home: str, away: str) -> str:
    return (
        f"{header_line(sport)}\n"
        f"{away} @ {home}\n"
        "오늘 슬레이트 분석에 이 경기가 없습니다."
    )


async def _send_card(text: str) -> bool:
    """봇 카드와 같은 2층 HTML. 실패하면 플레인으로 한 번 더."""
    from app.bot.main import two_layer_html

    html = two_layer_html(text)
    if html:
        ok = await _notify_mod.send_telegram(
            html[:TELEGRAM_LIMIT], parse_mode="HTML",
            disable_web_page_preview=True)
        if ok:
            return True
    plain = text.replace(DETAIL_SEP, "\n\n— 상세 데이터 —\n")[:TELEGRAM_LIMIT]
    return await _notify_mod.send_telegram(plain, disable_web_page_preview=True)


async def _claim(redis, game_id: int) -> bool:
    got = await redis.set(sent_key(game_id), "1", nx=True, ex=SENT_TTL_SEC)
    return bool(got)


async def _release(redis, game_id: int) -> None:
    try:
        await redis.delete(sent_key(game_id))
    except Exception:
        pass


async def run_pregame_push(pool, redis, now=None) -> dict:
    """오늘 아직 안 시작한 KBO·NPB 전 경기의 예측 카드. 경기당 1회."""
    now = now or datetime.now(UTC)
    date = today_kst()
    rows = await pool.fetch(
        """
        SELECT id, sport, home, away, starts_at, league
        FROM games
        WHERE sport = ANY($1::text[])
          AND status = 'scheduled'
          AND starts_at > now()
          AND (starts_at AT TIME ZONE 'Asia/Seoul')::date = $2::date
        ORDER BY starts_at, id
        """,
        list(SPORTS),
        date,
    )
    sent = skipped = failed = 0
    ensured: set[str] = set()
    cancelled_ids: set[int] = set()
    for sport in SPORTS:
        snap = await load_snapshot(redis, sport, date)
        sport_rows = [r for r in rows if r["sport"] == sport]
        cancelled_ids.update(await mark_cancelled_games(pool, sport_rows, snap))
    for r in rows:
        sport = r["sport"]
        gid = r["id"]
        if gid in cancelled_ids:
            skipped += 1
            logger.info("[pregame] %s game=%s 취소 — 발송 생략", sport, gid)
            continue
        if sport not in SPORTS or not still_upcoming(r["starts_at"], now):
            skipped += 1
            continue
        if not await _claim(redis, gid):
            skipped += 1
            continue
        try:
            if sport not in ensured:
                ok = await ensure_analysis_cache(pool, redis, sport, date)
                ensured.add(sport)
            else:
                ok = True
            raw = await redis.get(f"analysis:{sport}:{date}") if ok else None
            if not raw:
                text = missing_cache_text(sport, r["home"], r["away"])
            else:
                analysis = json.loads(raw)
                jg = next((g for g in analysis.get("games") or []
                           if g.get("game_id") == gid), None)
                if jg is None:
                    text = missing_game_text(sport, r["home"], r["away"])
                else:
                    text = compose_card(
                        jg, analysis.get("news") or "", sport)
            if await _send_card(text):
                sent += 1
                logger.info("[pregame] %s game=%s sent", sport, gid)
            else:
                await _release(redis, gid)
                failed += 1
        except Exception as exc:
            logger.warning("[pregame] %s game=%s 실패: %s", sport, gid, exc)
            await _release(redis, gid)
            failed += 1
    return {"due": len(rows), "sent": sent, "skipped": skipped, "failed": failed}
