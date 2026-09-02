"""매치업 판정 — 라인업 확정 시 경기당 1회. 팀 폼 캐시 히트면 재호출하지 않는다."""
from __future__ import annotations

import json
import logging

from app.collectors.base import ApiQuotaError
from app.config import get_settings
from app.engine.prompts import MATCHUP, fill
from app.engine.team_form import (
    FORM_TTL,
    analysis_game_key,
    complete_json,
    parse_json_object,
)

logger = logging.getLogger(__name__)

CONF_MAP = {"상": "high", "중": "medium", "하": "low"}


def clip_p_home(p, settings=None) -> float:
    """프롬프트가 벗어나도 코드에서 0.32–0.68로 자른다."""
    s = settings or get_settings()
    try:
        val = float(p)
    except (TypeError, ValueError):
        val = 0.5
    lo, hi = s.min_win_prob_mlb, s.max_win_prob_mlb
    return max(lo, min(hi, val))


def _mock_matchup(home: str, away: str) -> dict:
    return {
        "p_home": 0.55,
        "우세": "home",
        "근거": [
            f"홈 평가서 {home} 흐름 유지",
            f"원정 평가서 {away} 표본 3경기",
            "오늘 선발 최근 등판 목 모드",
        ],
        "변수": ["목 모드"],
        "뉴스반영": {"적용": False, "조정폭": "0", "사유": "목 모드"},
        "확신도": "중",
        "model": "mock",
    }


def lineups_payload(jg: dict) -> dict:
    r = jg.get("research") or {}
    return {
        "home": {
            "pitcher": ((r.get("home_pitcher") or {}).get("name")
                        or jg.get("home_pitcher")),
            "order": (r.get("home_lineup") or {}).get("order") or jg.get("lineup_home"),
        },
        "away": {
            "pitcher": ((r.get("away_pitcher") or {}).get("name")
                        or jg.get("away_pitcher")),
            "order": (r.get("away_lineup") or {}).get("order") or jg.get("lineup_away"),
        },
    }


def intent_payload(jg: dict) -> dict:
    """[라인업 의도] 감독이 **왜** 그렇게 짰는가. 판정 입력 6번.

    🔴 **사실이 아니라 해석이다.** `lineup_intent` 모듈의 규율("사실과 해석을
       끝까지 분리한다 — 섞으면 3단이 추측을 사실로 읽는다")을 여기서도
       지킨다. 프롬프트가 이 칸을 "해석"으로 명시해 받는다.

    ⚠️ `보류`는 **버리지 않고 그대로 넘긴다.** '보류'를 '='로 바꾸면
       "판단했는데 중립"과 "판단 못 함"이 섞인다(interpreter 의 같은 규율).
       다만 판정 규칙이 보류를 근거로 쓰지 못하게 막는다.

    실측 2026-09-01: 이 값이 카드에만 실리고 매치업 프롬프트에는 없었다.
    수집한 정보가 확률을 움직이지 않는 상태였다 — 이 저장소가 파드리스전에서
    이미 겪은 실패와 같은 모양이다.
    """
    it = jg.get("lineup_intent") or {}
    if not it:
        return {}
    out = {}
    for side in ("home", "away"):
        items = [
            {"변경": i.get("change_type"), "부호": i.get("symbol"),
             "득점방향": i.get("scoring_dir"), "사유": i.get("reason")}
            for i in (it.get("items") or {}).get(side) or []
        ]
        head = (it.get("headline") or {}).get(side)
        if items or head:
            out[side] = {"요약": head, "해석": items}
    if it.get("scoring"):
        out["총득점방향"] = it["scoring"]
    if it.get("handicap"):
        out["점수차메모"] = it["handicap"]
    return out


def starters_recent_payload(jg: dict) -> dict:
    """선발 등판. 표본이 얇으면 **구원 등판을 따로 붙인다.**

    ⚠️ 한 배열에 섞지 않는다 — 1이닝 구원과 6이닝 선발은 다른 일이다.
       프롬프트가 "구원은 구위·제구의 참고이지 이닝 소화력의 근거가 아니다"로
       다루게 하려면 라벨이 분리돼 있어야 한다.
    """
    r = jg.get("research") or {}
    out = {}
    for side in ("home", "away"):
        blk = {"선발등판": r.get(f"{side}_starter_recent") or []}
        relief = r.get(f"{side}_starter_relief") or []
        if relief:
            blk["구원등판"] = relief
        out[side] = blk
    return out


def lineup_season_payload(jg: dict) -> dict:
    """[D 2026-09-02] 오늘 타순 9명의 시즌 타격 라인 — **정식 근거.**

    선발 시즌 라인(`starters_season_payload`)과 달리 표본 보정 전용이 아니다.
    3경기 팀 총득점보다 표본이 크므로 프롬프트가 타선 평가의 주 근거로 쓴다.
    ⚠️ 재료가 없으면 그 쪽을 **넣지 않는다** — 빈 칸을 만들면 판정이 "타선
       자료 없음"과 "타선이 나쁨"을 구분하지 못한다.
    """
    r = jg.get("research") or {}
    out = {}
    for side in ("home", "away"):
        blk = r.get(f"{side}_lineup_season") or {}
        if blk.get("타자"):
            out[side] = blk
    return out


def starters_season_payload(jg: dict) -> dict:
    """[C] 선발 시즌 라인 — **표본 보정 전용.** 타선은 8번 자료가 따로 있다."""
    r = jg.get("research") or {}
    out = {}
    for side in ("home", "away"):
        line = r.get(f"{side}_starter_season") or {}
        n = len(r.get(f"{side}_starter_recent") or [])
        if line or n:
            out[side] = {"시즌": line, "최근등판수": n}
    return out


def apply_matchup(jg: dict, verdict: dict, settings=None) -> None:
    s = settings or get_settings()
    p = clip_p_home(verdict.get("p_home"), s)
    conf_kr = verdict.get("확신도") or "중"
    model = verdict.get("model") or s.matchup_model
    jg["p_claude"] = p
    jg["matchup"] = {**verdict, "p_home": p, "model": model}
    jg["model"] = model
    jg["judge_confidence"] = CONF_MAP.get(conf_kr, "medium")
    jg["judge_pass"] = conf_kr == "하"
    reasons = verdict.get("근거") or []
    jg["verdict"] = " ".join(str(x) for x in reasons) or "매치업 판정"
    jg["form_unavailable"] = False


async def persist_matchup_record(redis, jg: dict, date: str) -> None:
    """analysis:{league}:{game_id}:{date} 에 사용 모델 ID를 남긴다."""
    if redis is None:
        return
    sport = jg.get("sport") or ""
    gid = jg.get("game_id")
    if not sport or gid is None:
        return
    m = jg.get("matchup") or {}
    blob = {
        "model": jg.get("model") or m.get("model"),
        "p_home": jg.get("p_claude"),
        "우세": m.get("우세"),
    }
    try:
        await redis.set(
            analysis_game_key(sport, gid, date),
            json.dumps(blob, ensure_ascii=False, default=str),
            ex=FORM_TTL)
    except Exception as exc:
        logger.warning("[matchup] analysis 키 기록 실패 game=%s: %s", gid, exc)


async def _form_or_analyze(jg: dict, redis, date: str, side: str, mock: bool | None):
    """캐시 히트면 그대로. 미스면 그 자리에서 팀 분석 후 저장."""
    from app.engine.team_form import analyze_team, load_form, packet_from_usage

    sport = jg.get("sport") or ""
    team = jg.get(side) or ""
    cached = await load_form(redis, sport, team, date)
    if cached is not None:
        return cached
    research = jg.get("research") or {}
    usage = research.get(f"{side}_usage") or {}
    news = research.get(f"{side}_news") or research.get("news") or []
    if isinstance(news, dict):
        news = news.get("headlines") or []
    pkt = packet_from_usage(team, sport, date, usage)
    logger.info("[matchup] %s %s 폼 캐시 미스 — 현장 분석", sport, team)
    return await analyze_team(redis, sport, team, date, pkt, news, mock=mock)


#: 직전 판정에서 넘길 필드. 전체를 넘기면 프롬프트가 불필요하게 커지고,
#: 모델이 옛 서술을 그대로 베낄 유인이 생긴다 — **판정의 뼈대만** 넘긴다.
PREV_FIELDS = ("p_home", "우세", "근거", "변수", "확신도")


def prev_verdict(jg: dict) -> dict | None:
    """이 경기의 직전 판정. 최초 판정이면 None.

    ⚠️ 재판정에서만 값이 있다. jg["matchup"]은 직전 회차가 남긴 것이고,
       이번 회차 결과는 apply_matchup이 나중에 덮어쓴다.
    """
    m = jg.get("matchup") or {}
    if m.get("p_home") is None:
        return None
    return {k: m[k] for k in PREV_FIELDS if k in m}


async def judge_matchup(jg: dict, redis, date: str, *,
                        mock: bool | None = None) -> dict | None:
    """form: 히트면 재분석하지 않는다. 미스면 팀 분석을 한 뒤 매치업을 돌린다."""
    from app.engine.scoring import BASEBALL_SPORTS

    sport = jg.get("sport") or ""
    if sport not in BASEBALL_SPORTS:
        return None
    if jg.get("judgement_void") or jg.get("status") in ("cancelled", "suspended"):
        jg["judgement_void"] = True
        return None
    from app.engine.credit_guard import abort_if_credit_gone, trip_credit

    abort_if_credit_gone(f"matchup:{jg.get('away')}@{jg.get('home')}")
    settings = get_settings()
    is_mock = settings.mock_judge if mock is None else mock
    home, away = jg.get("home") or "", jg.get("away") or ""
    home_form = await _form_or_analyze(jg, redis, date, "home", mock)
    away_form = await _form_or_analyze(jg, redis, date, "away", mock)
    if not home_form or home_form.get("unavailable") or not away_form \
            or away_form.get("unavailable"):
        jg["form_unavailable"] = True
        logger.info("[matchup] %s vs %s 폼 없음·불가 — 추천 탈락", home, away)
        return None
    if is_mock:
        verdict = _mock_matchup(home, away)
        apply_matchup(jg, verdict, settings)
        await persist_matchup_record(redis, jg, date)
        return verdict

    model = settings.matchup_model
    # [v1.1 2단계] 직전 판정을 입력 6번으로 넘긴다 — 재판정이 "처음부터 다시"가
    #   아니라 "무엇이 바뀌어 어디로 움직였나"가 되게 한다.
    #   (실측 사례: 안우진 등판 확인 → 두산 0.62→0.59 철회)
    prev = prev_verdict(jg)
    prompt = fill(
        MATCHUP,
        HOME_FORM_JSON=json.dumps(home_form, ensure_ascii=False, default=str),
        AWAY_FORM_JSON=json.dumps(away_form, ensure_ascii=False, default=str),
        LINEUPS_JSON=json.dumps(lineups_payload(jg), ensure_ascii=False, default=str),
        STARTERS_RECENT_JSON=json.dumps(
            starters_recent_payload(jg), ensure_ascii=False, default=str),
        PREV_VERDICT_JSON=json.dumps(prev, ensure_ascii=False, default=str),
        LINEUP_INTENT_JSON=json.dumps(intent_payload(jg), ensure_ascii=False,
                                      default=str),
        STARTER_SEASON_JSON=json.dumps(starters_season_payload(jg),
                                       ensure_ascii=False, default=str),
        LINEUP_SEASON_JSON=json.dumps(lineup_season_payload(jg),
                                      ensure_ascii=False, default=str),
    )
    parsed = None
    for attempt in (1, 2):
        try:
            text = await complete_json(
                prompt, model=model, max_tokens=settings.matchup_max_tokens,
                role="matchup", mock=False)
        except ApiQuotaError as exc:
            trip_credit(f"matchup:{away}@{home}", exc)
            jg["form_unavailable"] = True
            logger.warning("[matchup] 크레딧 소진 model=%s prompt_chars=%d: %s",
                           model, len(prompt), exc)
            raise
        except Exception as exc:
            logger.warning("[matchup] 호출 실패 %d회 model=%s prompt_chars=%d: %s",
                           attempt, model, len(prompt), exc)
            text = ""
        parsed = parse_json_object(text)
        if parsed and "p_home" in parsed:
            parsed["model"] = model
            break
        parsed = None
        logger.warning("[matchup] JSON 파싱 실패 %d회 model=%s prompt_chars=%d",
                       attempt, model, len(prompt))
    if parsed is None:
        jg["form_unavailable"] = True
        logger.warning("[matchup] %s vs %s 분석 불가 model=%s — 추천 탈락",
                       home, away, model)
        return None
    apply_matchup(jg, parsed, settings)
    await persist_matchup_record(redis, jg, date)
    return parsed
