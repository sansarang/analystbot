"""KBO·NPB·MLB 당일 예측 카드 — 경기마다 1차 발송, 라인업 변동 시 재발송.

사용자 지시(2026-08-28):
  · NPB 크롤·분석은 시작 15분 전(18:00 → **17:45**)에 끝낸다. 그 시각 이후
    NPB 재판정은 하지 않는다. 이미 판정된 카드 발송은 시작 전까지.
  · 타순이 뜨면 그 경기만 바로 판정하고, 끝나는 대로 보낸다. 슬레이트를 기다리지 않는다.
  · 선발·타순이 바뀌면 다시 보낸다. predicted/confirmed 시계만 지난 것은 재판정 사유가 아니다.
  · 캐시·판정이 없으면 빈 카드를 보내지 않는다. 축구는 요청할 때만.
  · 이 모듈은 Judge·파이프라인을 호출하지 않는다. 이미 판정된 캐시만 보낸다.

사용자 지시(2026-08-29): MLB도 KBO·NPB와 같은 자동 발송. 사이트만 statsapi.
  캐시 키 날짜는 미국 동부 슬레이트(`mlb_slate_date`). 발송 창은 라인업 공시
  3시간 전(`lineup_lead_mlb` = 180분).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime

from app import notify as _notify_mod
from app.engine.lineup_timing import _parse
from app.pipeline import (
    DETAIL_SEP,
    mlb_slate_date,
    render_game_easy,
    today_kst,
)
from app.collectors.crawler_feed import load_snapshot, mark_cancelled_games

logger = logging.getLogger(__name__)

SPORTS = ("kbo", "npb", "mlb")
STAGE1_DEADLINE_MIN = 30
# NPB 18:00 → 17:45. 경기 시각이 다르면 그 경기의 시작 15분 전.
NPB_FINISH_MIN = 15
HARD_TARGET_MIN = NPB_FINISH_MIN
# KBO 18:30=T-70, NPB 18:00=T-40, MLB 라인업 공시 3시간 전=T-180.
SEND_OPEN_MIN = {"kbo": 70, "npb": 40, "mlb": 180}
SENT_TTL_SEC = 12 * 3600
SPORT_LABEL = {"kbo": "KBO", "npb": "NPB", "mlb": "MLB"}
TELEGRAM_LIMIT = 4096


def cache_date(sport: str) -> str:
    """분석 캐시 키의 날짜. MLB는 미국 동부 슬레이트, 나머지는 KST 오늘."""
    return mlb_slate_date() if sport == "mlb" else today_kst()


def card_sig_key(game_id: int) -> str:
    return f"pregame_card_sig:{game_id}"


def still_upcoming(starts_at, now=None) -> bool:
    """아직 시작하지 않았는가. 이미 시작한 경기는 보내지 않는다."""
    d = _parse(starts_at)
    if d is None:
        return False
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return (d - now).total_seconds() > 0


def minutes_until_start(starts_at, now=None) -> float | None:
    d = _parse(starts_at)
    if d is None:
        return None
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return (d - now).total_seconds() / 60.0


def in_send_window(sport: str, starts_at, now=None, settings=None) -> bool:
    """17:20 전후부터 시작 전까지. settings는 호출부 호환용."""
    del settings
    left = minutes_until_start(starts_at, now)
    if left is None or left <= 0:
        return False
    open_m = SEND_OPEN_MIN.get(sport)
    return open_m is not None and left <= open_m


def analysis_open(sport: str, starts_at, now=None) -> bool:
    """NPB는 T-15 이후 재판정하지 않는다. KBO는 시작 전까지."""
    if not still_upcoming(starts_at, now):
        return False
    if sport != "npb":
        return True
    left = minutes_until_start(starts_at, now)
    return left is not None and left > NPB_FINISH_MIN


def roster_signature(home_pitcher, away_pitcher, lineup_home, lineup_away) -> str:
    """선발·타순만. 잠정/확정 시계는 재판정 사유가 아니다."""
    return "|".join([
        (home_pitcher or "").strip(),
        (away_pitcher or "").strip(),
        (lineup_home or "").strip(),
        (lineup_away or "").strip(),
    ])


def header_line(sport: str, *, revision: bool = False) -> str:
    label = SPORT_LABEL.get(sport, sport.upper())
    tag = "변동" if revision else "1차"
    return f"⏰ {label} · {tag}"


def compose_card(jg: dict, news: str, sport: str, *, revision: bool = False) -> str:
    return f"{header_line(sport, revision=revision)}\n{render_game_easy(jg, news)}"


def _nine_sig(jg: dict, side: str) -> str:
    block = (jg.get("today_nine") or {}).get(side) or {}
    rows = block.get("order") or []
    if not rows:
        r = jg.get("research") or {}
        lu = r.get(f"{side}_lineup") or {}
        order = lu.get("order") if isinstance(lu, dict) else lu
        return str(order or "").strip()
    return ",".join(
        f"{row.get('slot', '')}:{row.get('name') or ''}" for row in rows)


def _pitcher_name(jg: dict, side: str) -> str:
    r = jg.get("research") or {}
    p = r.get(f"{side}_pitcher") or {}
    if isinstance(p, dict):
        return (p.get("name") or "").strip()
    return str(p or "").strip()


def card_signature(jg: dict) -> str:
    """같은 카드면 재발송하지 않고, 선발·타순·판정이 바뀌면 다시 보낸다."""
    cmp_ = jg.get("compare") or {}
    p = jg.get("p_claude")
    p_s = f"{float(p):.4f}" if isinstance(p, (int, float)) else ""
    return "|".join([
        _pitcher_name(jg, "home"),
        _pitcher_name(jg, "away"),
        _nine_sig(jg, "home"),
        _nine_sig(jg, "away"),
        p_s,
        str(cmp_.get("favored") or ""),
        str((jg.get("scoring") or {}).get("level") or ""),
        str((jg.get("pick_summary") or {}).get("desc") or ""),
    ])


def _judged(jg: dict) -> bool:
    return isinstance(jg.get("p_claude"), (int, float))


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


def _log_deadline(sport: str, gid: int, starts_at, now, reason: str) -> None:
    left = minutes_until_start(starts_at, now)
    if left is None or left >= STAGE1_DEADLINE_MIN:
        return
    tag = "NPB 17:45 종료선" if sport == "npb" and left <= NPB_FINISH_MIN \
        else ("T-15" if left < HARD_TARGET_MIN else "1차 마감(T-30)")
    logger.warning("[pregame] %s game=%s %s 지났는데 %s left=%.0f분",
                   sport, gid, tag, reason, left)


async def send_game_prediction(redis, row, date_s: str, *, now=None) -> str:
    """한 경기 카드. 'sent' | 'revised' | 'skipped' | 'failed'.

    Judge·ensure_analysis_cache를 호출하지 않는다. 판정된 캐시가 없으면 건너뛴다.
    """
    now = now or datetime.now(UTC)
    sport = row["sport"]
    gid = row["id"]
    starts_at = row["starts_at"]
    if sport not in SPORTS:
        return "skipped"
    if not still_upcoming(starts_at, now):
        return "skipped"
    if not in_send_window(sport, starts_at, now):
        return "skipped"
    raw = await redis.get(f"analysis:{sport}:{date_s}")
    if not raw:
        _log_deadline(sport, gid, starts_at, now, "캐시 없음 — 빈 카드 안 보냄")
        return "skipped"
    try:
        analysis = json.loads(raw)
    except (TypeError, ValueError):
        return "skipped"
    jg = next((g for g in analysis.get("games") or []
               if g.get("game_id") == gid), None)
    if jg is None or not _judged(jg):
        _log_deadline(sport, gid, starts_at, now, "미판정 — 빈 카드 안 보냄")
        return "skipped"
    sig = card_signature(jg)
    prev = await redis.get(card_sig_key(gid))
    if prev == sig:
        return "skipped"
    revision = prev is not None
    text = compose_card(jg, analysis.get("news") or "", sport, revision=revision)
    if await _send_card(text):
        await redis.set(card_sig_key(gid), sig, ex=SENT_TTL_SEC)
        logger.info("[pregame] %s game=%s %s", sport, gid,
                    "revised" if revision else "sent")
        return "revised" if revision else "sent"
    logger.warning("[pregame] %s game=%s 발송 실패", sport, gid)
    return "failed"


async def run_pregame_push(pool, redis, now=None) -> dict:
    """오늘 창 안의 KBO·NPB·MLB를 경기마다 발송. 파이프라인은 돌리지 않는다."""
    now = now or datetime.now(UTC)
    kst_date = today_kst()
    mlb_date = mlb_slate_date()
    rows = await pool.fetch(
        """
        SELECT id, sport, home, away, starts_at, league
        FROM games
        WHERE sport = ANY($1::text[])
          AND status = 'scheduled'
          AND starts_at > now()
          AND (
            (sport <> 'mlb' AND (starts_at AT TIME ZONE 'Asia/Seoul')::date = $2)
            OR (sport = 'mlb' AND (starts_at AT TIME ZONE 'America/New_York')::date = $3)
          )
        ORDER BY starts_at, id
        """,
        list(SPORTS),
        date.fromisoformat(kst_date),
        date.fromisoformat(mlb_date),
    )
    sent = skipped = failed = revised = 0
    cancelled_ids: set[int] = set()
    for sport in SPORTS:
        snap = await load_snapshot(redis, sport, cache_date(sport))
        sport_rows = [r for r in rows if r["sport"] == sport]
        cancelled_ids.update(await mark_cancelled_games(pool, sport_rows, snap))
    for r in rows:
        gid = r["id"]
        if gid in cancelled_ids:
            skipped += 1
            logger.info("[pregame] %s game=%s 취소 — 발송 생략", r["sport"], gid)
            continue
        result = await send_game_prediction(redis, r, cache_date(r["sport"]), now=now)
        if result == "sent":
            sent += 1
        elif result == "revised":
            revised += 1
        elif result == "failed":
            failed += 1
        else:
            skipped += 1
    return {"due": len(rows), "sent": sent, "revised": revised,
            "skipped": skipped, "failed": failed}
