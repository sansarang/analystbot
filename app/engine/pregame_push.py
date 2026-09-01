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
    tag = "라인업 변경 재판정" if revision else "1차"
    return f"⏰ {label} · {tag}"


def compose_card(jg: dict, news: str, sport: str, *, revision: bool = False) -> str:
    from app.engine.form_card import render_form_card

    del news  # 뉴스 반영은 매치업 JSON의 뉴스반영 칸만 쓴다
    body = render_form_card(jg, sport, revision=revision)
    return f"{header_line(sport, revision=revision)}\n{body}"


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


def lineup_hash(jg: dict) -> str:
    """발송 1차 키. 라인업이 같으면 재발송하지 않는다."""
    return roster_signature(
        _pitcher_name(jg, "home"),
        _pitcher_name(jg, "away"),
        _nine_sig(jg, "home"),
        _nine_sig(jg, "away"),
    )


def verdict_hash(jg: dict) -> str:
    """판정이 같으면 재발송하지 않는다.

    🔴 **"temperature 0 이라 같은 입력이면 같은 출력"은 사실이 아니었다.**
       실측 2026-09-01 (같은 입력으로 matchup 2회 연속 호출, claude-sonnet-5,
       mock 아님):
         1회차 p_home=0.38  우세=away  확신도=중
         2회차 p_home=0.34  우세=away  확신도=중
         diff  0.0400
       우세·확신도는 같았고 확률만 흔들렸다. 매치업 경로는 temperature 를
       아예 넘기지 않는다(2026-08-29: sonnet-5 가 non-default sampling 을
       400 으로 거부해 extra_body 를 뺐다).

    ⚠️ 소수 **2자리**로 자른다. 4자리면 0.5842 vs 0.5847 이 다른 해시가 되어
       입력이 그대로인데도 수정 카드가 나간다. 2자리면 0.38 vs 0.34 처럼
       사람이 볼 만한 차이만 재발송을 부른다.
    ⚠️ 우세·확신도 칸은 그대로다 — 그 둘은 실측에서 흔들리지 않았고,
       바뀌면 반드시 알려야 한다.
    """
    m = jg.get("matchup") or {}
    p = jg.get("p_claude")
    p_s = f"{float(p):.2f}" if isinstance(p, (int, float)) else ""
    return "|".join([
        p_s,
        str(m.get("우세") or (jg.get("compare") or {}).get("favored") or ""),
        str(m.get("확신도") or jg.get("judge_confidence") or ""),
    ])


def card_signature(jg: dict) -> str:
    """테스트·구키 호환. 발송 판단은 lineup_hash + verdict_hash."""
    return f"{lineup_hash(jg)}|{verdict_hash(jg)}"


def _sent_payload(jg: dict) -> str:
    return json.dumps({"lineup": lineup_hash(jg), "verdict": verdict_hash(jg)})


def _parse_sent(raw) -> dict:
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except (TypeError, ValueError):
        pass
    return {"legacy": str(raw)}


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


async def void_analysis_games(redis, sport: str, date_s: str, ids) -> None:
    """우천취소·서스펜디드 판정을 무효로 표시한다. 이미 보낸 카드는 취소 안내하지 않는다."""
    ids = [int(i) for i in (ids or [])]
    if not ids:
        return
    key = f"analysis:{sport}:{date_s}"
    raw = await redis.get(key)
    if not raw:
        return
    try:
        analysis = json.loads(raw)
    except (TypeError, ValueError):
        return
    want = set(ids)
    changed = False
    for g in analysis.get("games") or []:
        try:
            gid = int(g.get("game_id"))
        except (TypeError, ValueError):
            continue
        if gid in want:
            g["judgement_void"] = True
            changed = True
    if not changed:
        return
    from app.config import get_settings

    ex = get_settings().report_cache_ttl
    try:
        ttl = await redis.ttl(key)
        if isinstance(ttl, int) and ttl > 0:
            ex = ttl
    except Exception:
        pass
    await redis.set(key, json.dumps(analysis, ensure_ascii=False, default=str), ex=ex)


def _log_deadline(sport: str, gid: int, starts_at, now, reason: str) -> None:
    left = minutes_until_start(starts_at, now)
    if left is None or left >= STAGE1_DEADLINE_MIN:
        return
    tag = "NPB 17:45 종료선" if sport == "npb" and left <= NPB_FINISH_MIN \
        else ("T-15" if left < HARD_TARGET_MIN else "1차 마감(T-30)")
    logger.warning("[pregame] %s game=%s %s 지났는데 %s left=%.0f분",
                   sport, gid, tag, reason, left)


def lineup_diff(prev_sig: str | None, cur_sig: str | None) -> list[str]:
    """직전 발송의 라인업 서명과 현재를 비교해 **바뀐 것만** 사람 말로 돌려준다.

    `roster_signature`는 "홈선발|원정선발|홈타순|원정타순" 이고 타순은
    `_nine_sig`가 만든 "1:이름,2:이름…" 이다. 서명 자체가 읽을 수 있는
    형식이라 별도 저장 없이 diff 를 만들 수 있다.

    ⚠️ 이전 서명이 없거나(최초 발송) 형식이 다르면 빈 목록이다 — 지어내지
       않는다. 호출부는 빈 목록이면 "세부 변경 미상"으로 처리한다.
    """
    if not prev_sig or not cur_sig:
        return []
    a, b = str(prev_sig).split("|"), str(cur_sig).split("|")
    if len(a) != 4 or len(b) != 4:
        return []
    out: list[str] = []
    for idx, label in ((0, "홈 선발"), (1, "원정 선발")):
        if a[idx] != b[idx]:
            out.append(f"{label} {a[idx] or '미정'} → {b[idx] or '미정'}")
    for idx, label in ((2, "홈"), (3, "원정")):
        prev_order = _order_map(a[idx])
        cur_order = _order_map(b[idx])
        for slot in sorted(set(prev_order) | set(cur_order), key=_slot_key):
            was, now_ = prev_order.get(slot), cur_order.get(slot)
            if was != now_:
                out.append(f"{label} {slot}번 {was or '없음'} → {now_ or '없음'}")
    return out


def _order_map(sig: str) -> dict:
    """"1:이름,2:이름" → {"1": "이름"}. 옛 형식(그냥 문자열)이면 빈 dict."""
    out: dict[str, str] = {}
    for part in (sig or "").split(","):
        if ":" not in part:
            continue
        slot, _, name = part.partition(":")
        slot, name = slot.strip(), name.strip()
        if slot:
            out[slot] = name
    return out


def _slot_key(s: str):
    try:
        return (0, int(s))
    except (TypeError, ValueError):
        return (1, s)


def compose_lineup_only_card(jg: dict, sport: str, changes: list[str]) -> str:
    """라인업만 바뀌고 **판정은 그대로**일 때의 축약 카드.

    🔴 전체 폼 카드를 다시 보내면 사용자는 무엇이 달라졌는지 못 찾는다.
       바뀐 것(선수 diff)만 싣고, 확률·우세·확신도는 **"변동 없음"이라고
       명시**한다 — 침묵하면 "판정도 바뀌었나" 하고 되묻게 된다.
    """
    from app.engine.form_card import _team, favored_side_and_p

    home, away = _team(jg.get("home") or "?"), _team(jg.get("away") or "?")
    side, p = favored_side_and_p(jg)
    m = jg.get("matchup") or {}
    lines = [f"⏰ {SPORT_LABEL.get(sport, sport.upper())} · 라인업 변경 반영 — 판정 동일",
             f"{away} @ {home}", ""]
    lines.append("🔄 라인업 변경")
    if changes:
        lines += [f"  · {c}" for c in changes[:8]]
        if len(changes) > 8:
            lines.append(f"  · 외 {len(changes) - 8}건")
    else:
        lines.append("  · 세부 변경 미상 (직전 서명 없음)")
    lines += ["", "📊 판정 변동 없음"]
    if p is not None:
        who = home if side == "home" else away
        lines.append(f"  승률 {who} {p:.0%} · 우세 {m.get('우세') or '-'}"
                     f" · 확신도 {m.get('확신도') or '-'}")
    state = jg.get("pick_state_label")
    if state:
        lines.append(f"  {state}")
    return "\n".join(lines)


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
    if jg.get("judgement_void") or jg.get("status") in ("cancelled", "suspended"):
        return "skipped"
    lu, vd = lineup_hash(jg), verdict_hash(jg)
    prev = _parse_sent(await redis.get(card_sig_key(gid)))
    # 🔴 재발송은 **(라인업 변경) OR (판정 변경)** 이다.
    #    종전에는 둘 중 하나라도 같으면 스킵했다. 그래서 라인업이 실제로
    #    바뀌었는데 확률·우세·확신도가 우연히 같으면 사용자는 **바뀐
    #    라인업을 영영 못 봤다.** 야구 추천은 확정 라인업이 요건이므로
    #    "무엇으로 확정됐나"를 못 보는 것은 그 자체로 결함이다.
    lineup_changed = bool(prev) and prev.get("lineup") != lu
    verdict_changed = bool(prev) and prev.get("verdict") != vd
    if prev and not prev.get("legacy") and not lineup_changed and not verdict_changed:
        logger.info("[pregame] %s game=%s skipped skip_reason=both_hash_same",
                    sport, gid)
        return "skipped"
    revision = bool(prev) and "legacy" not in prev
    if prev.get("legacy"):
        revision = True
    if revision and lineup_changed and not verdict_changed:
        # 라인업만 바뀌었다 — 전체 카드를 다시 보내면 무엇이 달라졌는지 묻힌다.
        changes = lineup_diff(prev.get("lineup"), lu)
        text = compose_lineup_only_card(jg, sport, changes)
        logger.info("[pregame] %s game=%s 라인업만 변경 · diff %d건",
                    sport, gid, len(changes))
    else:
        text = compose_card(jg, analysis.get("news") or "", sport, revision=revision)
    if await _send_card(text):
        await redis.set(card_sig_key(gid), _sent_payload(jg), ex=SENT_TTL_SEC)
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
        newly = await mark_cancelled_games(pool, sport_rows, snap)
        cancelled_ids.update(newly)
        if newly:
            await void_analysis_games(redis, sport, cache_date(sport), newly)
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
