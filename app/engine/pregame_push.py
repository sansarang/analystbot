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
from zoneinfo import ZoneInfo

#: 표시는 언제나 KST. 저장·비교는 UTC (CLAUDE.md 절대규칙 4).
KST = ZoneInfo("Asia/Seoul")

#: 타순 확정으로 보는 최소 인원. 야구는 9명이다.
LINEUP_FULL = 9


def lineup_confirmed(home_order, away_order, known=None) -> bool:
    """[v1.3 A-1] **확정의 정의는 하나다: 양 팀 타순 9명이 다 있는가.**

    🔴 실사고 2026-09-02 (NPB 4경기): 종전에는 `is_final_window`(경기 N분
       전인가)로 확정 여부를 정했다. NPB 창은 T-30인데 타순이 T-44에 도착해
       `predicted` 로 기록됐고, 그 뒤로 라인업이 안 바뀌니 영영 확정으로
       올라갈 경로가 없었다. **타순이 제때 온 것이 오히려 손해가 됐다.**
       17:51(T-9)에 "라인업 미확정 — 관망" 카드 4장이 나갔고, 같은 경기가
       17:35에는 T6(확정일 때만 걸림)를 통과한 상태였다.

    ⚠️ **"언제 왔는가"는 확정 여부가 아니다.** 시각 규칙(`is_final_window`)은
       확정 판정에서 폐기한다 — 발송 창·종료선 용도로만 남는다.
    ⚠️ 하이픈 이름 때문에 9명이 10조각으로 갈리던 결함이 있었다.
       `known`(명단 사전)이 있으면 재결합해서 센다.
    """
    from app.engine.lineup_diff import parse_order

    for order in (home_order, away_order):
        if len(parse_order(order, known)) < LINEUP_FULL:
            return False
    return True

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
# [창 이원화] NPB 라인업 공시는 보통 T-30이다. 풀 분석을 T-15에 닫는 것은
#   맞지만, **캐시 폼 + 매치업만 다시 도는 경량 재판정까지 같이 닫으면**
#   T-30~T-15 사이 15분 안에 확정을 못 받은 경기는 영영 잠정으로 남아
#   추천 자격을 못 얻는다. 경량 경로만 T-10까지 연다.
NPB_REJUDGE_FINISH_MIN = 10

#: 🔴 [2026-09-03 사용자 결정] **수정 카드가 T-15 에 손에 있어야 한다.**
#   종전에는 KBO 에 마감선이 아예 없어 이론상 T-2 에 재판정이 돌 수 있었다 —
#   그 카드는 정확해도 걸 수가 없다.
CARD_IN_HAND_MIN = 15

#: 재판정 **시작 → 카드 도착**까지 확보하는 예산(분).
#  🔴 마감선은 "재판정을 시작할 수 있는 마지막 시점"이지 도착 시각이 아니다.
#     카드 도착 = 폴링 틱 + 재판정 소요. 그래서 도착을 T-15 로 **보장**하려면
#     마감선이 그만큼 앞이어야 한다.
#     · 폴링 주기 5분(`asia_pregame_5m`)
#     · 경량 재판정 소요 — **아직 측정 전.** 풀 분석 실측이 경기당 78~91초
#       (리허설 2026-09-03)이고 경량은 그보다 짧다. 5분이면 덮는다.
#  ⚠️ 오늘 밤 실측 후 조정한다. 지금은 안전 쪽으로 잡았다.
REJUDGE_BUDGET_MIN = 5

#: 리그별 재판정 마감(분). 여기 없는 종목(MLB)은 마감선 없음 — 공시가
#  T-180 이라 사정이 다르다.
#  ⚠️ KBO 는 **풀·경량 모두 같은 선**이다. NPB 의 15/10 이원화를 옮기면
#     경량이 더 늦게까지 열려 도착 보장이 깨진다.
#  ⚠️ **NPB 는 종전 그대로** (풀 T-15 · 경량 T-10). 그 이원화는 공시가
#     T-30 으로 늦어 15분 창이 너무 좁다는 실측에서 나온 것이다. 지시 범위는
#     KBO 였고, NPB 까지 바꾸면 요청 밖에서 커버리지가 줄어든다.
KBO_FINISH_MIN = CARD_IN_HAND_MIN + REJUDGE_BUDGET_MIN          # T-20
ANALYSIS_FINISH_MIN = {"npb": NPB_FINISH_MIN, "kbo": KBO_FINISH_MIN}
REJUDGE_FINISH_MIN = {"npb": NPB_REJUDGE_FINISH_MIN, "kbo": KBO_FINISH_MIN}

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


#: 🔴 [2026-09-03 사용자 결정] **첫 카드 보장선 — 시작 T-30.**
#   그 시점에 카드가 없으면 라인업이 미공시여도 지금 있는 재료로 판정해
#   내보낸다. "라인업을 기다리다 카드가 아예 안 나가는" 것이 가장 나쁘다.
#   ⚠️ 이건 **첫 카드 보장선**이지 마감이 아니다. 확정 공시가 오면
#      재판정 수정 카드가 뒤따르고, 재판정 창은 종전 그대로다
#      (KBO 시작 전 · NPB T-15, 경량 T-10).
FIRST_CARD_GUARANTEE_MIN = 30


def guarantee_due(starts_at, now=None) -> bool:
    """지금이 그 경기의 보장선 안인가 (0 < 남은 시간 ≤ T-30)."""
    left = minutes_until_start(starts_at, now)
    return left is not None and 0 < left <= FIRST_CARD_GUARANTEE_MIN


async def already_sent(redis, game_id) -> bool:
    """카드가 한 번이라도 나갔는가. **나간 경기는 건드리지 않는다.**"""
    if redis is None:
        return False
    try:
        return bool(await redis.get(card_sig_key(game_id)))
    except Exception as exc:
        logger.debug("[pregame] 발송 이력 조회 실패 game=%s: %s", game_id, exc)
        return False          # 모르면 보장 쪽으로 — 중복은 해시가 막는다


def analysis_open(sport: str, starts_at, now=None) -> bool:
    """풀 분석(크롤·리서치 재실행) 창. 마감선은 `ANALYSIS_FINISH_MIN` 이 원본.

    NPB T-15 · KBO T-15 (2026-09-03 신설) · MLB 마감선 없음.
    """
    if not still_upcoming(starts_at, now):
        return False
    finish = ANALYSIS_FINISH_MIN.get(sport)
    if finish is None:
        return True
    left = minutes_until_start(starts_at, now)
    return left is not None and left > finish


def rejudge_open(sport: str, starts_at, now=None) -> bool:
    """**경량 재판정**(캐시 폼 + 매치업 재실행) 창. 풀 분석보다 5분 더 연다.

    🔴 `analysis_open`(풀 분석)과 분리한 이유: 리서치·크롤을 새로 도는 것과
       이미 있는 재료로 매치업만 다시 부르는 것은 비용이 다르다. NPB 라인업
       공시가 T-30이라 T-15로 함께 닫으면 창이 15분뿐이고, 놓친 경기는
       잠정으로 남아 추천 게이트(`qualifies`)에서 통째로 탈락한다.
    """
    if not still_upcoming(starts_at, now):
        return False
    finish = REJUDGE_FINISH_MIN.get(sport)
    if finish is None:
        return True
    left = minutes_until_start(starts_at, now)
    return left is not None and left > finish


def lineup_pending_card(sport: str, home: str, away: str, left_min: float) -> str:
    """T-10에도 확정이 안 온 경기 — **조용히 잠정으로 두지 않는다.**

    사용자 입장에서 "카드가 안 온 것"과 "라인업이 안 나온 것"은 다르다.
    말하지 않으면 봇이 죽은 줄 안다.
    """
    from app.engine.form_card import _team

    return "\n".join([
        f"⏰ {SPORT_LABEL.get(sport, sport.upper())} · 라인업 미확정 — 관망",
        f"{_team(away)} @ {_team(home)}",
        "",
        f"경기 시작 {left_min:.0f}분 전인데 확정 타순이 공시되지 않았습니다.",
        "확정 라인업 없이는 추천하지 않습니다 (보드만).",
        "공시되면 즉시 재판정해 다시 보냅니다.",
    ])


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


#: 🔴 [2026-09-06 사용자 지시] **픽은 경기당 두 장이다.**
#   1차 `🕐 잠정`(타순 전, 무료 판정) · 2차 `✅ 최종`(타순 확정, Anthropic).
#   종전에는 라인업이나 판정 해시가 바뀔 때마다 무제한으로 나갔다.
CARD_CAP = 2


def _sent_payload(jg: dict, n: int) -> str:
    return json.dumps({"lineup": lineup_hash(jg), "verdict": verdict_hash(jg),
                       "n": int(n)})


def _parse_sent(raw) -> dict:
    """저장된 발송 기록. `n` 이 없으면 **1장 나갔다**고 읽는다(구키 호환)."""
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            obj.setdefault("n", 1)
            return obj
    except (TypeError, ValueError):
        pass
    return {"legacy": str(raw), "n": 1}


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


#: "판정 불가" 카드를 같은 경기에 다시 보내지 않게 하는 키.
UNAVAILABLE_KEY = "pregame:unavailable:{}"
UNAVAILABLE_TTL = 12 * 3600


def compose_unavailable_card(row, sport: str, reason: str, kst: str) -> str:
    """[운영 안정화 3a] 판정을 못 냈을 때 **침묵 대신** 보내는 카드.

    🔴 실사고 2026-09-02: Anthropic 크레딧이 끊겨 판정이 0건이 됐는데 카드도
       경보도 없었다. 사용자는 "봇이 죽었나"와 "오늘 픽이 없나"를 구분할 수
       없었다. **침묵이 가장 나쁜 출력이다.**

    ⚠️ 추천이 아니다. 확률·우세를 쓰지 않는다 — 재료가 없으니 판정도 없다.
       "무엇이 없어서 못 냈는지"만 말한다.
    """
    away = row["away"] or "원정"
    home = row["home"] or "홈"
    return "\n".join([
        f"⚠️ {sport.upper()} 판정 불가 — {away} @ {home}",
        f"🕐 {kst}",
        "",
        f"사유: {reason}",
        "오늘 이 경기는 추천을 내지 않습니다.",
        "(관망 권장이 아니라 **분석 미완**입니다 — 복구되면 다시 보냅니다)",
    ])


async def send_unavailable(redis, row, sport: str, reason: str) -> bool:
    """판정 불가 카드 1장. 같은 경기에 두 번 보내지 않는다."""
    gid = row["id"]
    key = UNAVAILABLE_KEY.format(gid)
    try:
        if not await redis.set(key, reason[:120], ex=UNAVAILABLE_TTL, nx=True):
            return False
    except Exception as exc:
        logger.debug("[pregame] 판정불가 중복 가드 실패 game=%s: %s", gid, exc)
    kst = _kst_label(row["starts_at"])
    text = compose_unavailable_card(row, sport, reason, kst)
    ok = await _send_card(text)
    logger.warning("[pregame] %s game=%s 판정 불가 카드 %s — %s",
                   sport, gid, "발송" if ok else "발송 실패", reason)
    return ok


def _kst_label(starts_at) -> str:
    try:
        return starts_at.astimezone(KST).strftime("%m/%d %H:%M")
    except Exception:
        return "시각 미상"


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

    ⚠️ [운영 안정화 1] 모든 갈래가 **사유와 함께** 기록된다. 반환 계약은
       종전 그대로이고, 사유는 `dispatch_stats` 에만 남는다 — 호출부를
       바꾸지 않으면서 "조용한 0"을 없앤다.
    """
    from app.engine import dispatch_stats as ds

    now = now or datetime.now(UTC)
    sport = row["sport"]
    gid = row["id"]
    starts_at = row["starts_at"]

    async def _skip(reason: str) -> str:
        await ds.record(redis, sport, date_s, reason)
        return "skipped"

    if sport not in SPORTS:
        return await _skip("not_supported")
    if not still_upcoming(starts_at, now):
        return await _skip("already_started")
    if not in_send_window(sport, starts_at, now):
        return await _skip("window_not_open")
    raw = await redis.get(f"analysis:{sport}:{date_s}")
    if not raw:
        _log_deadline(sport, gid, starts_at, now, "캐시 없음 — 빈 카드 안 보냄")
        return await _skip("cache_missing")
    try:
        analysis = json.loads(raw)
    except (TypeError, ValueError):
        return await _skip("cache_missing")
    jg = next((g for g in analysis.get("games") or []
               if g.get("game_id") == gid), None)
    if jg is None or not _judged(jg):
        _log_deadline(sport, gid, starts_at, now, "미판정 — 빈 카드 안 보냄")
        return await _skip("unjudged")
    if jg.get("judgement_void") or jg.get("status") in ("cancelled", "suspended"):
        return await _skip("void")
    # [시장 기준선] 카드 표기용 값만 얹는다. **표기 전용이다.**
    #   🔴 `verdict_hash` 는 이 값을 보지 않는다(p_claude·우세·확신도만) —
    #      배당이 흔들렸다고 수정 카드가 나가면 안 된다. 테스트로 잠금.
    try:
        from app.db import get_pool as _gp
        from app.engine.market_baseline import SEND, p_market

        _snap = await p_market(await _gp(), {**jg, "id": gid,
                                             "starts_at": starts_at},
                               purpose=SEND)
        jg["p_market_send"] = _snap.get("p")
    except Exception as exc:
        logger.debug("[pregame] 시장 확률 생략 game=%s: %s", gid, exc)
    lu, vd = lineup_hash(jg), verdict_hash(jg)
    prev = _parse_sent(await redis.get(card_sig_key(gid)))
    # 🔴 [2026-09-06 사용자 지시] 두 장을 넘기지 않는다. 판정 쪽에도 문이
    #    있지만(최종은 경기당 1회) 발송 쪽에도 둔다 — 라인업만 바뀌어도
    #    카드가 나가는 갈래가 있어서, 판정 문 하나로는 두 장이 보장되지 않는다.
    _n = int(prev.get("n") or 0)
    if _n >= CARD_CAP:
        logger.info("[pregame] %s game=%s skipped skip_reason=card_cap "
                    "(이미 %d장)", sport, gid, _n)
        return await _skip("card_cap")
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
        # 이미 도달한 카드다 — 미발송이 아니다. 분자에 넣는다.
        return await _skip("unchanged")
    # 🔴 **두 번째 자리는 최종 카드의 몫이다.** 타순 확정 전에도 예비 재판정이
    #    돌면 판정 해시가 바뀌고, 그 카드가 두 번째 자리를 먹으면 정작
    #    `✅ 최종` 이 상한에 막혀 못 나간다 — 사용자가 기다린 그 한 장이다.
    #    ⚠️ 해시 비교 **뒤**에 둔다. 아무것도 안 바뀐 카드의 사유는 종전대로
    #       `변경 없음` 이어야 한다 — 사유가 뭉개지면 집계를 못 읽는다.
    if _n >= 1 and not jg.get("final_verdict"):
        logger.info("[pregame] %s game=%s skipped skip_reason=card_reserved "
                    "(예비 재판정 — 2장째는 최종 카드 몫)", sport, gid)
        return await _skip("card_reserved")
    revision = bool(prev) and "legacy" not in prev
    if prev.get("legacy"):
        revision = True
    # 🔴 최종 판정이 돈 경기는 **전체 카드**로 나간다. 라인업만 바뀐 것으로
    #    보고 라인업 전용 카드를 내면, 두 장뿐인 픽 중 마지막 장에서 바뀐
    #    판정을 사용자가 못 본다.
    if revision and lineup_changed and not verdict_changed \
            and not jg.get("final_verdict"):
        # 라인업만 바뀌었다 — 전체 카드를 다시 보내면 무엇이 달라졌는지 묻힌다.
        changes = lineup_diff(prev.get("lineup"), lu)
        text = compose_lineup_only_card(jg, sport, changes)
        logger.info("[pregame] %s game=%s 라인업만 변경 · diff %d건",
                    sport, gid, len(changes))
    else:
        text = compose_card(jg, analysis.get("news") or "", sport, revision=revision)
        # 🔴 [실사고 2026-09-02] 전체 카드만 다시 보내면 **무엇이 달라졌는지**
        #    묻힌다. 그때 축약 카드를 만든 이유가 그것이었다. 최종 카드는
        #    전체 카드여야 하므로, 축약본 대신 **diff 줄을 얹는다** — 두
        #    계약(전체 카드 · 변경점 노출)을 둘 다 지킨다.
        if revision and lineup_changed:
            changes = lineup_diff(prev.get("lineup"), lu)
            if changes:
                text += "\n\n🔄 라인업 변경\n" + "\n".join(
                    f"  · {c}" for c in changes[:8])
                if len(changes) > 8:
                    text += f"\n  · 외 {len(changes) - 8}건"
                logger.info("[pregame] %s game=%s 라인업 diff %d건 첨부",
                            sport, gid, len(changes))
    if await _send_card(text):
        await redis.set(card_sig_key(gid),
                        _sent_payload(jg, int(prev.get("n") or 0) + 1),
                        ex=SENT_TTL_SEC)
        outcome = "revised" if revision else "sent"
        # [G1] 게이트 결과와 발송을 **같은 문자열**로 남긴다. 리포트 ④·⑤절이
        #   "무엇이 어떤 자격으로 나갔나"를 이 두 줄로 재구성한다.
        #   ⚠️ 새 계측이 아니다 — jg 에 이미 있는 값을 찍는다.
        _pick = jg.get("pick_summary") or {}
        _gate_msg = ("[gate] %s game=%s 결과=%s 확신도=%s p=%.3f 시장p=%s" % (
            sport, gid, _pick.get("desc") or jg.get("gate_result") or "-",
            jg.get("judge_confidence"), float(jg.get("p_claude") or 0),
            jg.get("p_market_send")))
        _send_msg = "[pregame] %s game=%s %s" % (sport, gid, outcome)
        logger.info("%s", _gate_msg)
        logger.info("%s", _send_msg)
        await ds.record(redis, sport, date_s, outcome)
        try:
            from app.db import get_pool as _gp2
            from app.engine.game_trace import GATE, SEND, note as _tnote

            _pool2 = await _gp2()
            await _tnote(_pool2, game_id=gid, sport=sport, date=date_s,
                         stage=GATE, summary=_gate_msg)
            await _tnote(_pool2, game_id=gid, sport=sport, date=date_s,
                         stage=SEND, summary=_send_msg,
                         ref={"revision": bool(revision)})
        except Exception as exc:
            logger.debug("[trace] 발송 기록 생략 game=%s: %s", gid, exc)
        # [시장 기준선] 발송된 경기만 원장에 남긴다 — 시장과 우리를 **같은
        #   경기 집합**에서 비교하기 위해서다. 실패해도 발송에 영향 없다.
        try:
            from app.db import get_pool
            from app.engine.market_baseline import record_send

            await record_send(await get_pool(), jg, date_s)
        except Exception as exc:
            logger.debug("[pregame] 시장 원장 기록 생략 game=%s: %s", gid, exc)
        return outcome
    logger.warning("[pregame] %s game=%s 발송 실패", sport, gid)
    await ds.record(redis, sport, date_s, "send_failed")
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
    sent = skipped = failed = revised = unavailable = 0
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
            # [운영 안정화 3a] **침묵 금지.** 판정이 없는 채로 발송 창을 지나면
            #   사용자는 "봇이 죽었나"와 "오늘 픽이 없나"를 구분할 수 없다.
            #   재료가 없어서 못 낸 것이면 그 사실이라도 보낸다.
            if await _should_say_unavailable(redis, r, now):
                if await send_unavailable(redis, r, r["sport"],
                                          await _unavailable_reason(redis)):
                    unavailable += 1
    return {"due": len(rows), "sent": sent, "revised": revised,
            "skipped": skipped, "failed": failed, "unavailable": unavailable}


async def _should_say_unavailable(redis, row, now) -> bool:
    """판정 불가 카드를 보낼 상황인가.

    ⚠️ **발송 창 안이고, 판정 캐시가 없거나 미판정일 때만.** 창 전이거나
       이미 시작한 경기, 혹은 판정이 멀쩡히 있는데 변경이 없어 건너뛴 것은
       대상이 아니다 — 그건 정상 동작이지 고장이 아니다.
    """
    sport = row["sport"]
    if sport not in SPORTS:
        return False
    if not still_upcoming(row["starts_at"], now) or \
            not in_send_window(sport, row["starts_at"], now):
        return False
    try:
        raw = await redis.get(f"analysis:{sport}:{cache_date(sport)}")
    except Exception:
        return False
    if not raw:
        return True
    try:
        analysis = json.loads(raw)
    except (TypeError, ValueError):
        return True
    jg = next((g for g in analysis.get("games") or []
               if g.get("game_id") == row["id"]), None)
    if jg is None:
        return True
    if jg.get("judgement_void") or jg.get("status") in ("cancelled", "suspended"):
        return False              # 취소는 고장이 아니다
    return not _judged(jg)


async def _unavailable_reason(redis) -> str:
    """왜 판정이 없는지 — 아는 만큼만 쓴다. 모르면 모른다고 쓴다."""
    try:
        from app.watchdog import LLM_FAIL_KEY

        n = int(await redis.get(LLM_FAIL_KEY) or 0)
        if n:
            last = await redis.get(f"{LLM_FAIL_KEY}:last") or ""
            return (f"LLM 호출 연속 {n}회 실패"
                    + (f" — {last[:120]}" if last else ""))
    except Exception:
        pass
    try:
        from app.engine.credit_guard import stopped_at

        if stopped_at():
            return f"크레딧 소진 (중단 지점 {stopped_at()})"
    except Exception:
        pass
    return "판정 재료 미확보 (원인 조사 중)"
