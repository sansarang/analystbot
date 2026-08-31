"""[v1.1 6단계] 트리거형 딥서치 — 판정이 막힌 경기만 스스로 조사한다.

**전 경기 상시 검색 금지.** 비용·외부 의존이 걸린 최고위험 단계라 상한을
세 겹으로 둔다: 트리거(발동 조건) · 경기당 검색 수 · 하루 발동 비율.

**야구·축구 공통이다.** 종목 분기 없이 하나의 모듈이 양쪽 판정 경로에 붙는다.
언어만 종목별로 다르다 — 원문 소스가 그 언어로 쓰여 있기 때문이다.

⚠️ 검색 결과는 **크롤 정형 데이터보다 낮은 신뢰 등급**이다. 조정은 ±4%p로
   묶고 우세 방향은 단독으로 뒤집지 못한다. 이 두 가지는 프롬프트 지시가
   아니라 **코드가 강제**한다 — 모델이 규칙을 어겨도 값이 새어 나가지 않게.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

#: 확률 조정 상한. 클리핑과 같은 방식으로 코드가 강제한다.
ADJUST_CAP_PP = 4.0

#: 게이트 임계 ±이 값 안이면 경계 경기(T1).
BOUNDARY_PP = 3.0

# 트리거 이름
T1_BOUNDARY = "T1_경계확률"
T2_MARKET = "T2_시장괴리"
T3_ASKED = "T3_추가확인"
T4_STARTER = "T4_선발변경"
T5_LINEUP = "T5_라인업이상"

#: 조사 언어 — 원문 소스가 그 언어로 쓰여 있다. 영어로만 찾으면
#: KBO 구단 공지·NPB 스포츠지가 통째로 빠진다.
SEARCH_LANG = {"kbo": "한국어", "npb": "일본어", "mlb": "영어", "soccer": "영어"}

CACHE_KEY = "deepsearch:{league}:{game_id}:{date}"
CACHE_TTL = 6 * 3600


# ---------------------------------------------------------------- 트리거

def _gate_threshold(sport: str, favored: str | None, settings) -> float:
    """그 경기의 확률 임계. 원정은 프리미엄이 붙는다."""
    from app.engine.scoring import BASEBALL_SPORTS

    if sport in BASEBALL_SPORTS:
        base = float(settings.min_win_prob)
        return base + 0.05 if favored == "away" else base
    return 0.60 if favored == "away" else 0.55      # 축구 (수동 프로토콜과 동일)


def triggers(jg: dict, settings, *, prev_lineup: dict | None = None) -> list[str]:
    """이 경기가 조사 대상인가. 걸린 트리거 목록(빈 목록이면 발동 안 함).

    ⚠️ 하나라도 걸리면 발동하되 **경기당 1회**다. 여러 개가 걸려도 조사는 한 번.
    """
    m = jg.get("matchup") or {}
    p_home = jg.get("p_claude")
    favored = m.get("우세")
    sport = jg.get("sport") or ""
    out: list[str] = []

    # T1 — 게이트 임계 ±3%p (경계 경기)
    if p_home is not None and favored in ("home", "away"):
        p = float(p_home) if favored == "home" else 1.0 - float(p_home)
        need = _gate_threshold(sport, favored, settings)
        if abs(p - need) * 100 <= BOUNDARY_PP:
            out.append(T1_BOUNDARY)

    # T2 — 4단계 플래그 (엣지 승격의 필수 관문 / 시장 우위 검토)
    if jg.get("edge_status") == "candidate" or jg.get("market_divergence"):
        out.append(T2_MARKET)

    # T3 — 판정이 스스로 "이건 더 봐야 한다"고 말했다
    if [x for x in (m.get("추가확인") or []) if str(x).strip()]:
        out.append(T3_ASKED)

    # T4 — 재판정에서 선발이 바뀌었다
    if any("선발" in str(x) for x in ((m.get("직전대비") or {}).get("변경입력") or [])):
        out.append(T4_STARTER)

    # T5 — 라인업 이상 (2026-08-31 신설)
    if lineup_anomaly(jg, prev_lineup):
        out.append(T5_LINEUP)
    return out


def lineup_anomaly(jg: dict, prev_lineup: dict | None = None) -> bool:
    """직전 대비 주전 2명 이상 교체, 또는 폼 평가서 핵심 선수 결장.

    🔴 **숫자가 경계에 안 걸려도 라인업 이상 자체가 조사 사유다.**
       확률이 편안한 구간에 있어도, 폼 평가서가 근거로 삼은 선수가 빠졌다면
       그 판정의 토대가 무너진 것이다.
    """
    for side in ("home", "away"):
        cur = _names(jg.get(f"lineup_{side}"))
        prev = _names((prev_lineup or {}).get(f"lineup_{side}"))
        if cur and prev and len(prev - cur) >= 2:
            return True
    # 폼 평가서가 이름을 댄 선수가 오늘 결장 명단에 있는가
    key_names = _form_key_players(jg)
    if key_names:
        out = _absent_names(jg)
        if key_names & out:
            return True
    return False


def _names(v) -> set[str]:
    if not v:
        return set()
    if isinstance(v, str):
        parts = [p.split("(")[0].strip() for p in v.split("-")]
    elif isinstance(v, (list, tuple)):
        parts = [str(p).split("(")[0].strip() for p in v]
    else:
        return set()
    return {p for p in parts if p}


def _form_key_players(jg: dict) -> set[str]:
    """폼 평가서 서술에 이름이 등장한 선수 — 판정의 토대가 된 사람들."""
    out: set[str] = set()
    for side in ("home", "away"):
        form = (jg.get("research") or {}).get(f"{side}_form") or {}
        blob = json.dumps(form, ensure_ascii=False) if form else ""
        for nm in _names(jg.get(f"lineup_{side}")):
            if nm and nm in blob:
                out.add(nm)
    return out


def _absent_names(jg: dict) -> set[str]:
    out: set[str] = set()
    for side in ("home", "away"):
        lu = (jg.get(f"{side}_lineup") or {})
        out |= {str(x).strip() for x in (lu.get("결장") or []) if str(x).strip()}
        res = (jg.get("research") or {}).get(f"{side}_absent") or []
        out |= {str(x).strip() for x in res if str(x).strip()}
    return out


# ---------------------------------------------------------------- 상한

def daily_cap(slate_size: int, settings) -> int:
    """하루 발동 상한 = 슬레이트의 N%. 최소 1건은 허용한다.

    슬레이트가 3경기인 날 30%면 0.9라 아무것도 조사 못 한다 — 경계 경기가
    있어도 손을 놓는 것은 이 단계의 취지가 아니다.
    """
    if slate_size <= 0:
        return 0
    return max(1, int(slate_size * float(settings.deepsearch_daily_cap)))


def clamp_adjustment(p_before: float, p_after: float | None,
                     favored: str | None) -> tuple[float, str | None]:
    """조정 ±4%p 상한 + 우세 방향 단독 뒤집기 금지. **코드가 강제한다.**

    반환: (적용할 p, 사람이 읽는 사유 or None)

    ⚠️ 프롬프트에 적는 것만으로는 부족하다. 모델이 규칙을 어겨도 값이 새어
       나가지 않아야 한다 — 클리핑과 같은 태도다.
    """
    if p_after is None:
        return p_before, None
    lo, hi = p_before - ADJUST_CAP_PP / 100, p_before + ADJUST_CAP_PP / 100
    p = max(lo, min(hi, float(p_after)))
    note = None
    if abs(float(p_after) - p) > 1e-9:
        note = f"조정 상한 ±{ADJUST_CAP_PP:g}%p 적용 ({p_after:.3f}→{p:.3f})"
    # 우세 방향이 뒤집히면 되돌린다 — 검색 결과 단독으로는 방향을 못 바꾼다.
    if favored == "home" and p_before >= 0.5 > p:
        p, note = 0.5, "우세 방향 단독 뒤집기 금지 — 0.50에서 멈춤"
    elif favored == "away" and p_before <= 0.5 < p:
        p, note = 0.5, "우세 방향 단독 뒤집기 금지 — 0.50에서 멈춤"
    return round(p, 4), note


# ---------------------------------------------------------------- 조사 엔진

PROMPT = """당신은 스포츠 경기 조사원이다. 아래 판정이 확신을 세우지 못한
지점만 조사한다. 판정을 처음부터 다시 하지 않는다.

[경기] {league} · {away} (원정) @ {home} (홈) · {kickoff} KST
[현재 판정] {verdict}
[발동 트리거] {triggers}
[판정이 요청한 추가확인] {asked}

[조사 언어] 검색어는 **{lang}**로 만든다. 원문 소스가 그 언어로 쓰여 있다 —
영어로만 찾으면 구단 공지·현지 스포츠지가 통째로 빠진다.

[승률 관련 확인 항목] 아래 중 **해당하는 것만** 조사한다. 전부 훑지 마라.
① 결장자의 사유·복귀 시점 (부상 정도·로테이션·징계)
② 오늘 선발 자원의 컨디션 이상 (구속 저하·복귀전·등판 간격 / 부상 복귀·주중 경기 피로)
③ 팀 내부 이슈 (감독 발언·경질설, 라커룸, 연전·원정 이동 피로)
④ 시장이 아는데 우리가 모르는 정보 (배당 급변·역방향 사유)
⑤ 날씨·구장 특이사항 (우천 취소/지연 가능성 포함)

[소스 규칙]
① 조회 우선순위: 공식 소스(구단 공홈·리그 공시·경기 기록 페이지) → 기록·통계
   사이트 → 뉴스 기사. **뉴스만으로 조사를 끝내지 않는다.**
② 확률 조정의 근거가 **단일 기사 하나뿐이면 조정 폭을 절반으로** 줄인다.
   서로 다른 소스 2개 이상이 같은 사실을 확인할 때만 전액 반영한다.
③ 근거마다 소스 유형(공식/기록/뉴스)과 URL을 남긴다.
④ **루머·익명 소스·커뮤니티발 내용은 근거로 쓰지 않는다.**

[결과의 지위]
- 검색 결과는 **크롤 정형 데이터보다 낮은 신뢰 등급**이다.
- 확률 조정은 **±4%p 이내**. 우세 방향을 검색 결과 단독으로 뒤집지 않는다.
- 조사해도 새 사실이 없으면 **조정 0**으로 두고 그렇게 적는다. 억지로 움직이지 마라.

[출력] 아래 JSON만 출력한다. 다른 텍스트, 마크다운 백틱 금지.
{{
  "발견": [{{"사실": "1문장", "소스유형": "공식|기록|뉴스", "url": "..."}}],
  "조정": {{"p_home": 0.00, "사유": "1문장", "단일기사여부": true|false}},
  "요약": "카드에 실을 1문장"
}}"""


async def investigate(jg: dict, trig: list[str], *, timeout: float | None = None):
    """경기 1건 조사. 반환: (결과 dict | None, 검색 사용 수).

    ⚠️ 실패·타임아웃이면 (None, 0) — **원판정을 그대로 둔다.** 조사가 안 됐다고
       판정을 흔들지 않는다. 폴백이 곧 "조사 없음"이다.
    """
    import asyncio

    import anthropic

    from app.config import get_settings
    from app.engine.credit_guard import abort_if_credit_gone, trip_credit

    s = get_settings()
    sport = jg.get("sport") or ""
    abort_if_credit_gone(f"deepsearch:{jg.get('away')}@{jg.get('home')}")
    m = jg.get("matchup") or {}
    prompt = PROMPT.format(
        league=jg.get("league") or sport.upper(),
        home=jg.get("home"), away=jg.get("away"),
        kickoff=jg.get("starts_at_kst") or "",
        verdict=json.dumps({k: m.get(k) for k in ("p_home", "우세", "근거", "확신도")},
                           ensure_ascii=False, default=str),
        triggers=", ".join(trig),
        asked=json.dumps(m.get("추가확인") or [], ensure_ascii=False),
        lang=SEARCH_LANG.get(sport, "영어"))
    tool = {"type": "web_search_20260318", "name": "web_search",
            "max_uses": int(s.deepsearch_max_searches)}   # API가 검색 수를 강제
    cli = anthropic.AsyncAnthropic(api_key=s.anthropic_api_key)
    try:
        resp = await asyncio.wait_for(
            cli.messages.create(model=s.matchup_model, max_tokens=2000,
                                tools=[tool],
                                messages=[{"role": "user", "content": prompt}]),
            timeout=timeout if timeout is not None else float(s.deepsearch_timeout_sec))
    except TimeoutError:
        logger.warning("[deepsearch] 타임아웃 — 원판정 유지 %s@%s",
                       jg.get("away"), jg.get("home"))
        return None, 0
    except anthropic.APIStatusError as exc:
        if exc.status_code == 400 and "credit" in str(exc).lower():
            trip_credit(f"deepsearch/{s.matchup_model}", exc)
        logger.warning("[deepsearch] 호출 실패 %s@%s: %s",
                       jg.get("away"), jg.get("home"), exc)
        return None, 0
    except Exception as exc:
        logger.warning("[deepsearch] 예기치 못한 실패 %s@%s: %s",
                       jg.get("away"), jg.get("home"), exc)
        return None, 0
    used = sum(1 for b in resp.content
               if getattr(b, "type", "") == "server_tool_use")
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    try:
        data = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        logger.warning("[deepsearch] JSON 파싱 실패 %s@%s", jg.get("away"), jg.get("home"))
        return None, used
    return data, used


def apply_findings(jg: dict, data: dict) -> dict:
    """조사 결과를 판정에 반영. 상한·방향은 코드가 강제한다.

    ⚠️ 소스 규칙 ②(단일 기사면 조정 절반)를 **코드로도 집행한다.** 프롬프트에
       적어 두는 것만으로는 지켜졌는지 알 수 없다.
    """
    m = jg.get("matchup") or {}
    p_before = jg.get("p_claude")
    adj = (data or {}).get("조정") or {}
    p_after = adj.get("p_home")
    if p_before is None or p_after is None:
        return {"moved": 0.0, "note": None}
    p_before = float(p_before)
    if adj.get("단일기사여부"):
        p_after = p_before + (float(p_after) - p_before) / 2
    p, note = clamp_adjustment(p_before, p_after, m.get("우세"))
    jg["p_claude"] = p
    m["p_home"] = p
    jg["deepsearch"] = {
        "발견": (data or {}).get("발견") or [],
        "요약": (data or {}).get("요약"),
        "조정_사유": adj.get("사유"),
        "단일기사": bool(adj.get("단일기사여부")),
        "이동_pp": round((p - p_before) * 100, 1),
        "상한_적용": note,
    }
    if abs(p - p_before) > 1e-9 or (data or {}).get("요약"):
        jg.setdefault("breaking_changes", []).append(
            "🔍 추가 조사 반영: " + str((data or {}).get("요약") or "새 사실 없음"))
    return {"moved": round((p - p_before) * 100, 1), "note": note}
