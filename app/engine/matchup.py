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


#: 재시도 상향의 천장. 이 위로 올리면 SDK 가 비스트리밍 요청을 거부한다 —
#  실사고 2026-08-2x: 16000→32000 임의 상향이 judge 전 배치를 실패시켰다.
MAX_TOKENS_CEILING = 16000


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
    """오늘 선발 + 타순 9명. **슬롯 번호와 포지션을 붙인다.**

    🔴 종전에는 `"이름-이름-…"` 문자열 하나였다. 판정은 **누가 몇 번 타자인지
       모른 채** 이름 나열만 받았다. 1번과 8번은 타석 수가 다르고, 3~5번은
       득점권 상황이 다르다 — 순서가 곧 정보다.
       `today_nine`(수집기가 이미 만들어 둔 슬롯·포지션)이 있으면 그것을 쓰고,
       없으면 종전 문자열로 폴백한다.
    """
    r = jg.get("research") or {}
    nine = r.get("today_nine") or {}
    out = {}
    for side in ("home", "away"):
        blk = {"선발투수": ((r.get(f"{side}_pitcher") or {}).get("name")
                            or jg.get(f"{side}_pitcher"))}
        slots = ((nine.get(side) or {}).get("order")
                 if isinstance(nine.get(side), dict) else None)
        if slots:
            blk["타순"] = [{"타순": x.get("slot"), "이름": x.get("name"),
                            "포지션": x.get("pos")}
                           for x in slots if isinstance(x, dict)]
        else:
            blk["타순"] = ((r.get(f"{side}_lineup") or {}).get("order")
                           or jg.get(f"lineup_{side}"))
        out[side] = blk
    return out


def boxscore_payload(jg: dict) -> dict:
    """[E 2026-09-02] 최근 3경기 **원본 박스스코어**. 판정 입력 1번.

    🔴 **다른 모델이 만든 등급을 판정에 넣지 않는다.**
       종전 자료1·2는 헤이쿠가 이 박스스코어를 읽고 만든 `{"타선":{"평가":"중"}}`
       같은 등급·산문이었다. 판정은 숫자를 못 보고 다섯 글자만 받았고, 실제로
       근거에 **"자료2 원정팀 종합: 선발진 평가 '상'과 '흐름 상승'이 자료1 홈팀
       '중' 대비 우위를 뒷받침한다"** 라고 적었다 — 다른 모델의 해석을 근거로
       인용한 것이다 (실측 2026-09-02, 한신@야쿠르트 직전 판정).

       "수치는 있는 그대로 판단하게 하고 분석만 AI가 한다" (사용자 지시
       2026-09-02). 그래서 등급을 버리고 원본을 준다.

    ⚠️ 없는 칸은 만들지 않는다. 수집기가 준 그대로 넘긴다.
    """
    r = jg.get("research") or {}
    out = {}
    for side in ("home", "away"):
        u = r.get(f"{side}_usage") or {}
        games = u.get("games")
        if not isinstance(games, list) or not games:
            continue
        blk = {"경기": games}
        for k in ("results_l3", "runs_l3", "runs_allowed_l3", "runs_per_game_l3"):
            if u.get(k) is not None:
                blk[k] = u[k]
        out[side] = blk
    return out


def bullpen_payload(jg: dict) -> dict:
    """양팀 불펜 — 팀 ERA + 등록 투수 개별. 경기 후반을 결정한다.

    ⚠️ `roster` 의 괄호는 `ERA·컨디션` 이다. 컨디션은 야후의
       `絶好調/好調/普通/不調/絶不調` 를 옮긴 것으로 **ERA 와 별개 항목**이다
       (실측 2026-09-02: `清水 昇(2.16·매우 나쁨)` 은 라벨 반전이 아니라
       "시즌 ERA 2.16, 현재 컨디션 나쁨"이다).
    """
    r = jg.get("research") or {}
    out = {}
    for side in ("home", "away"):
        blk = r.get(f"{side}_bullpen") or {}
        if blk:
            out[side] = blk
    return out


def material10_payload(jg: dict) -> dict:
    """자료10(변수 참조). **읽기만 한다** — 조립·I/O 는 파이프라인이 끝냈다."""
    return jg.get("material10") or {}


#: 자료10 을 끼워 넣을 자리. 이 문구 **앞**에 붙는다.
_RULES_MARK = "[판정 규칙]"

#: [C4 변수 대장 2026-09-05] 자료10·11 을 **한 블록**으로 낸다.
#  🔴 종전에는 두 블록이 따로 붙어 판정이 "이닝분포"(자료10)와 "연전"(자료11)을
#     다른 성격의 자료로 읽었다. 둘 다 **변수의 크기를 뒷받침하는 참조**이고
#     쓰임이 같다. 한 대장으로 묶어 순서를 고정한다:
#       불펜(자료9 참조) → 이동·연전 → 날씨 → [플래툰: 보류]
#  ⚠️ prior 헤더는 `config.variable_ledger_prior` 가 원본이다 — 여기 적지 않는다.
_LEDGER_HEAD = """10. 변수 대장 — **변수의 크기를 여기서 가져온다** (해당 경기만):
   {{PRIOR}}

"""

_LEDGER_REF = """   [참조] {{REF}}
   `이닝분포`: 그 투수 최근 등판의 실제 이닝 배열과 분위수(p25/p50/p75)·최장.
     `선발등판`이 0~2면 "예측 불가"가 아니라 **이 분포가 답**이다.
   `부진후회귀`: 같은 리그에서 직전 3등판이 부진했던 선발의 **다음 등판**
     평균 이닝·실점과 표본 수. `주의`에 "참조 불충분"이 있으면 표본이 적다는
     뜻이니 단정하지 마라.

"""

_LEDGER_CTX = """   [맥락] {{CTX}}
   `연전`: **오늘까지 며칠 연속** 경기인가. 휴식일이 끼면 거기서 끊긴 값이다.
     불펜 가용성(자료9)과 **함께** 읽어라 — 연전 4일차의 '가용'은 3일차와 다르다.
   `원정연전`: 직전까지 연속 원정 경기 수.
   `이동`·`구장변경`: 홈/원정 **전환**과 구장이 바뀌었는지.
     ⚠️ 거리가 아니다 — 구장 좌표가 없어 실제 이동량은 모른다.
     ⚠️ `구장변경` 이 없으면 **알 수 없다는 뜻**이다(원정→원정은 상대가
        같은지 모른다). 없는 것을 '안 바뀜'으로 읽지 마라.
   `날씨`: `라벨`{타자 유리|투수 유리|중립}과 `계수`. 계수는 리그 득점
     환경 계수이지 이 경기의 예측이 아니다. **총득점 방향으로만** 읽어라.
   `선발손`: 오늘 선발의 투구 손. **사실이지 스플릿이 아니다** —
     좌우 상대 성적(시즌 누적)은 판정 입력이 아니다.
   ⚠️ 플래툰 성적은 **보류**다(3리그 모두 최근 창×손타입 조합 불가, 2026-09-05 실측).

"""

_LEDGER_TAIL = """   ⚠️ 이 대장은 **변수의 크기를 뒷받침하는 참조**다. 이것으로 우세를 정하지 마라.

"""


def elo_payload(jg: dict) -> dict:
    """자료12 — 팀 실력 레이팅. 한쪽이라도 없으면 **빈 dict**.

    🔴 **팀당 숫자 하나만 넘긴다.** 시즌 집계표를 여기 얹으면 대원칙 위반이다
       (`app/engine/CLAUDE.md` — 집계표 금지, 레이팅만 예외).
    ⚠️ 한 팀만 있으면 격차를 낼 수 없다. 반쪽 정보를 실력차로 읽게 하느니
       자료12 자체를 생략한다.
    """
    e = jg.get("elo") or {}
    h, a = e.get("home"), e.get("away")
    if not h or not a:
        return {}
    return {"홈": {"레이팅": h.get("레이팅"), "리그평균대비": h.get("리그평균대비"),
                   "경기수": h.get("경기수")},
            "원정": {"레이팅": a.get("레이팅"), "리그평균대비": a.get("리그평균대비"),
                     "경기수": a.get("경기수")},
            "격차": round(float(h.get("레이팅") or 0) - float(a.get("레이팅") or 0), 1)}


def ledger_payload(jg: dict) -> dict:
    """변수 대장의 두 축. **읽기만 한다** — 조립은 파이프라인이 끝냈다."""
    return {"ref": jg.get("material10") or {},
            "ctx": jg.get("material11") or {}}


def insert_ledger(prompt: str, payload: dict, settings=None) -> str:
    """대장을 규칙 앞에 끼운다. 두 축이 모두 비면 **원문 그대로** 돌려준다."""
    ref, ctx = (payload or {}).get("ref") or {}, (payload or {}).get("ctx") or {}
    if not ref and not ctx:
        return prompt
    import json as _json

    from app.config import get_settings

    s = settings or get_settings()
    # ⚠️ `.format` 을 쓰지 않는다 — 블록 안에 `{타자 유리|…}` 같은 중괄호가
    #    있어 포맷 문자열로 해석되면 KeyError 가 난다(실측). 자리표시자만 바꾼다.
    blk = _LEDGER_HEAD.replace("{{PRIOR}}", s.variable_ledger_prior)
    if ref:
        blk += _LEDGER_REF.replace(
            "{{REF}}", _json.dumps(ref, ensure_ascii=False, default=str))
    if ctx:
        blk += _LEDGER_CTX.replace(
            "{{CTX}}", _json.dumps(ctx, ensure_ascii=False, default=str))
    blk += _LEDGER_TAIL
    return prompt.replace(_RULES_MARK, blk + _RULES_MARK, 1)


def news_payload(home_form: dict, away_form: dict, jg: dict | None = None) -> dict:
    """팀 평가서에서 **뉴스태그만** 꺼낸다.

    🔴 등급(`타선`·`선발진`·`불펜`·`흐름`·`종합`)은 넘기지 않는다 — 그건 다른
       모델이 숫자를 압축한 해석이고, 판정은 자료1에서 그 숫자를 직접 본다.
       뉴스는 다르다. 3경기 박스스코어에 없는 **새 정보**(부상·트레이드·감독
       교체)이고 태그 사전으로 이미 걸러져 있다.
    """
    out = {}
    for side, form in (("home", home_form), ("away", away_form)):
        tags = list((form or {}).get("뉴스태그") or [])
        # [상황 변수 2026-09-06] 팀의 공기. **키워드 매칭이라 LLM 0회**이고,
        #   `[미확인]` 출처는 라벨만 붙여 넘긴다 — 버리지 않는다. 확률 오염은
        #   프롬프트 규칙(±1.0%p 상한 · 미확인 0%p 고정)이 막는다.
        for sit in ((jg or {}).get("situation_tags") or {}).get(side) or []:
            tags.append({"tag": f"{sit.get('라벨')} {sit.get('유형')}",
                         "dir": "=",          # 방향은 판정이 정한다 — 우리가 정하지 않는다
                         "근거": f"{sit.get('제목')} ({sit.get('출처') or '출처불명'})",
                         "확인": sit.get("확인")})
        if tags:
            out[side] = tags
    # [변수 평의회] 심의록을 자료2 **확장**으로 싣는다 — 프롬프트 구조 불변.
    #   ⚠️ %p 를 담지 않는다. 심의가 만든 것은 사실이고, 결론은 판정이 낸다.
    try:
        from app.engine.council import payload as _council_payload

        blk = _council_payload(jg or {})
        if blk:
            out.update(blk)
    except Exception:      # 심의록 한 칸 때문에 판정을 막지 않는다
        pass
    return out


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


def _real_model(configured: str | None) -> str:
    """**실제로 응답한** provider/model. 못 읽으면 설정값 그대로.

    ⚠️ `LAST_USAGE` 는 이 프로세스의 **직전 호출** 값이다. 판정 직후에만
       읽는다 — 다른 역할(폼)이 그 사이에 끼면 그 모델이 잡힌다.
       그래서 role 이 matchup 인지 확인하고, 아니면 설정값으로 돌아간다.
    """
    from app.engine.team_form import LAST_USAGE

    from app.llm.judge_route import JUDGE_ROLES

    if (LAST_USAGE or {}).get("role") in JUDGE_ROLES and LAST_USAGE.get("model"):
        return str(LAST_USAGE["model"])
    return str(configured or "")


def _sha(text: str) -> str:
    """프롬프트 원문의 지문. 리포트가 "이 판정이 본 프롬프트"를 가리키는 열쇠다.

    ⚠️ 원문 자체는 이미 `fact_audit.PROMPT_KEY` 로 Redis 에 보관된다.
       원장에는 **지문만** 둔다 — 같은 원문을 두 곳에 복제하지 않는다.
    """
    import hashlib

    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:12]


#: [투명 리포트 G1] 원장 단계 이름 — `game_trace` 가 원본이다(사본 금지).
from app.engine.game_trace import ASSEMBLE as TRACE_ASSEMBLE  # noqa: E402
from app.engine.game_trace import JUDGE as TRACE_JUDGE  # noqa: E402


async def _trace(jg: dict, date: str, stage: str, *, summary: str,
                 ref: dict | None = None) -> None:
    """원장 1행. **실패해도 판정을 막지 않는다** — 기록이 본체를 죽이면 안 된다."""
    try:
        from app.db import get_pool
        from app.engine.game_trace import note

        await note(await get_pool(), game_id=jg.get("game_id"),
                   sport=jg.get("sport") or "", date=date, stage=stage,
                   summary=summary, ref=ref)
    except Exception as exc:
        logger.debug("[trace] 기록 생략 game=%s: %s", jg.get("game_id"), exc)


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
    # [소식통 2026-09-06] 상황이 승률을 뒷받침하는가. **확률은 안 건드린다** —
    #   확신도만 1단계 내리고, 그것도 공식 소식통이 있을 때만이다.
    #   ⚠️ 판정이 확신도를 직접 내리게 하지 않는다. 모델은 `상황판정` 만 내고
    #      소식통 검사와 강등은 코드가 한다 — 모델에게 거부권을 주지 않는다.
    try:
        from app.engine.situation_gate import apply as _sit_gate

        jg["situation_check"] = _sit_gate(jg)
        # 강등이 '하'까지 갔으면 거부권도 함께 선다.
        if jg.get("judge_confidence") == "low":
            jg["judge_pass"] = True
    except Exception as exc:
        logger.warning("[situation-gate] game=%s 실패 — 판정은 그대로: %s",
                       jg.get("game_id"), exc)


async def _keep_prompt(redis, game_id, prompt: str) -> None:
    """감시층이 읽을 프롬프트 원문 보관. 실패해도 판정을 막지 않는다."""
    if redis is None or game_id is None:
        return
    try:
        from app.config import get_settings
        from app.engine.fact_audit import PROMPT_KEY

        await redis.set(PROMPT_KEY.format(game_id=game_id), prompt,
                        ex=int(get_settings().prompt_keep_ttl_sec))
    except Exception as exc:
        logger.debug("[matchup] 프롬프트 보관 실패 game=%s: %s", game_id, exc)


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


#: 🔴 [2026-09-06 사용자 지시] **최종 분석은 경기당 딱 한 번이다.**
#   "픽은 두 번만 오고, 두 번째가 왔을 때만 Anthropic 이 최종 분석한다."
#   라인업이 두 번 이상 바뀌어도 유료 호출이 두 번 나가지 않게 코드가 잠근다.
FINAL_KEY = "matchup:final:{sport}:{game_id}:{date}"
FINAL_TTL_SEC = 12 * 3600


def _final_key(jg: dict, date: str) -> str:
    return FINAL_KEY.format(sport=jg.get("sport") or "", date=date,
                            game_id=jg.get("game_id"))


async def final_done(redis, jg: dict, date: str) -> bool:
    """이 경기의 최종 판정이 **이미 나갔는가.** 읽기만 한다.

    선점(`claim_final`)보다 앞서 부른다 — 이미 끝났으면 폼·심의까지 돌릴
    이유가 없다. 못 읽으면 "안 나갔다"로 본다: 판정을 막는 쪽이 더 나쁘다.
    """
    if redis is None:
        return False
    try:
        return bool(await redis.get(_final_key(jg, date)))
    except Exception as exc:
        logger.warning("[matchup] 최종 여부 조회 실패 game=%s — 진행한다: %s",
                       jg.get("game_id"), exc)
        return False


async def release_final(redis, jg: dict, date: str) -> None:
    """최종 권한을 **되돌린다.** 판정을 못 냈으면 권한만 태운 것이다.

    🔴 [P0 실사고 2026-09-06] 락은 잡혔는데 판정이 없는 상태가 실제로 났다
       (npb game=3603, 니혼햄@라쿠텐). 그러면 그 뒤 모든 재판정이 "이미 완료"로
       막혀 **카드가 영영 안 나간다** — `W-SEND-PENDING` 이 그것을 잡았다.
       실패했으면 권한을 돌려놓아 다음 폴링이 다시 시도하게 한다.
    """
    if redis is None:
        return
    try:
        await redis.delete(_final_key(jg, date))
        logger.warning("[matchup] game=%s 최종 판정 실패 — 권한 반납(다음 폴링 재시도)",
                       jg.get("game_id"))
    except Exception as exc:
        logger.warning("[matchup] 최종 락 반납 실패 game=%s: %s",
                       jg.get("game_id"), exc)


def has_verdict(jg: dict) -> bool:
    """이 경기에 이미 판정이 붙어 있는가. `pregame_push._judged` 와 같은 기준."""
    return isinstance(jg.get("p_claude"), (int, float))


async def claim_final(redis, jg: dict, date: str) -> bool:
    """이 경기의 최종 판정 권한을 **선착순 1회**만 준다.

    🔴 **재료 게이트를 모두 통과한 뒤에 부른다.** 박스스코어가 없어 판정이
       탈락하는 자리에서 먼저 잠그면, 나중에 자료가 도착해도 그 경기는 영영
       최종을 못 받는다 — 권한만 태우고 판정은 안 한 꼴이다.

    ⚠️ redis 가 없으면(테스트·도구) 잠그지 못한다 — 그때는 허용한다.
       잠금 실패로 판정이 통째로 막히는 쪽이 더 나쁘다.
    """
    if redis is None:
        return True
    try:
        return bool(await redis.set(_final_key(jg, date), "1",
                                    ex=FINAL_TTL_SEC, nx=True))
    except Exception as exc:
        logger.warning("[matchup] 최종 락 실패 game=%s — 허용한다: %s",
                       jg.get("game_id"), exc)
        return True


#: 최종 픽 자격이 있는 라인업 상태. **규칙을 여기 베끼지 않는다** —
#  타순 9명을 세는 것은 `pregame_push.lineup_confirmed` 이고, 그 결과를
#  `pipeline.promote_lineup_status` 가 이 필드에 새긴다. 우리는 결과만 읽는다.
#  ⚠️ `conflict`(소스 불일치)는 확정이 아니다 — 자격 박탈이 그 상태의 뜻이다.
LINEUP_FINAL_STATUS = "confirmed"


def lineup_is_confirmed(jg: dict) -> bool:
    """타순이 확정됐는가. 확정의 정의는 다른 곳에 있고 여기는 읽기만 한다."""
    return (jg.get("lineup_status") or "") == LINEUP_FINAL_STATUS


def prev_verdict(jg: dict) -> dict | None:
    """이 경기의 직전 판정. 최초 판정이면 None.

    ⚠️ 재판정에서만 값이 있다. jg["matchup"]은 직전 회차가 남긴 것이고,
       이번 회차 결과는 apply_matchup이 나중에 덮어쓴다.
    """
    m = jg.get("matchup") or {}
    if m.get("p_home") is None:
        return None
    return {k: m[k] for k in PREV_FIELDS if k in m}


def render_matchup_prompt(jg: dict, boxes: dict, news: dict,
                          prev: dict | None) -> str:
    """매치업 프롬프트 렌더. **순수 함수 — 모델을 부르지 않는다.**

    🔴 `judge_matchup` 안에 인라인이던 것을 그대로 꺼냈다. 동작은 한 글자도
       바뀌지 않는다(테스트가 자리표시자 잔여 0을 확인한다).
       꺼낸 이유: 오디션·리허설이 **모델 호출 없이** 프롬프트만 필요할 때가
       있는데, 인라인이면 그 재료를 복제해야 한다 — 복제는 곧 드리프트다.
    """
    prompt = fill(
        MATCHUP,
        BOXSCORE_JSON=json.dumps(boxes, ensure_ascii=False, default=str),
        NEWS_JSON=json.dumps(news, ensure_ascii=False, default=str),
        LINEUPS_JSON=json.dumps(lineups_payload(jg), ensure_ascii=False, default=str),
        STARTERS_RECENT_JSON=json.dumps(
            starters_recent_payload(jg), ensure_ascii=False, default=str),
        PREV_VERDICT_JSON=json.dumps(prev, ensure_ascii=False, default=str),
        LINEUP_INTENT_JSON=json.dumps(intent_payload(jg), ensure_ascii=False,
                                      default=str),
        BULLPEN_JSON=json.dumps(bullpen_payload(jg), ensure_ascii=False, default=str),
        ELO_JSON=json.dumps(elo_payload(jg), ensure_ascii=False, default=str),
    )
    # [C4 변수 대장] 자료10·11 을 한 블록으로. 둘 다 비면 원문 그대로다.
    prompt = insert_ledger(prompt, ledger_payload(jg))
    return prompt


async def judge_matchup(jg: dict, redis, date: str, *,
                        mock: bool | None = None,
                        allow_final: bool = False) -> dict | None:
    """form: 히트면 재분석하지 않는다. 미스면 팀 분석을 한 뒤 매치업을 돌린다.

    🔴 [2026-09-06 사용자 지시] **판정은 경기당 두 번, 최종은 한 번이다.**
       "픽은 딱 두 번만 오고, 두 번째가 왔을 때만 Anthropic 이 최종 분석한다."

         1차(예비) — 타순 전. `PRELIM_ROLE` → 어떤 설정에서도 **무료 사슬**.
                     `🕐 잠정` 카드가 여기서 나간다.
         2차(최종) — 타순 확정 뒤. `MATCHUP_ROLE` → 유료가 허용되는 유일한
                     역할. `✅ 최종` 카드가 여기서 나가고, 그 뒤로는 없다.

       `allow_final` 은 호출부가 "여기는 최종이 될 수 있는 자리인가"만 말한다.
       **실제 판단은 코드가 한다** — 타순이 확정됐는가(`lineup_is_confirmed`)와
       아직 아무도 최종을 쓰지 않았는가(`claim_final`). 호출부마다 조건을
       적으면 그것이 사본이고, 사본은 원본이 바뀔 때 따라가지 않는다.
    """
    from app.engine.scoring import BASEBALL_SPORTS
    from app.llm.judge_route import MATCHUP_ROLE, PRELIM_ROLE

    sport = jg.get("sport") or ""
    if sport not in BASEBALL_SPORTS:
        return None
    if jg.get("judgement_void") or jg.get("status") in ("cancelled", "suspended"):
        jg["judgement_void"] = True
        return None
    final = bool(allow_final) and lineup_is_confirmed(jg)
    if await final_done(redis, jg, date):
        if has_verdict(jg):
            # 이미 최종을 낸 경기다. **예비로도 다시 돌지 않는다** — 재판정이
            # 한 번 더 돌면 카드가 한 장 더 나가고, 픽은 두 장이어야 한다.
            logger.info("[matchup] game=%s 최종 판정 이미 완료 — 재판정하지 않는다",
                        jg.get("game_id"))
            return None
        # 🔴 [P0 실사고 2026-09-06] **락은 있는데 판정이 없다.** 그 최종은
        #    실패했거나(파싱 실패·크레딧) 중간에 프로세스가 끊겼다.
        #    종전에는 여기서도 그냥 반환해서 **그 경기는 영영 카드가 못 나갔다**
        #    (npb game=3603 니혼햄@라쿠텐, W-SEND-PENDING 이 잡았다).
        #    잠긴 것은 "유료 최종을 또 부르지 않는다"까지다 — 판정 자체를
        #    막는 것이 아니다. 무료 예비로 내려가 **한 장은 낸다.**
        logger.warning("[matchup] game=%s 최종 락은 있는데 판정이 없다 — "
                       "예비(무료)로 진행한다. 카드 0장을 만들지 않는다",
                       jg.get("game_id"))
        final = False
    role = MATCHUP_ROLE if final else PRELIM_ROLE
    from app.engine.credit_guard import abort_if_credit_gone, trip_credit
    from app.engine.team_form import _free_primary

    # 🔴 [P0 2026-09-06] **Anthropic 차단기는 Anthropic 경로에만 걸린다.**
    #    종전에는 경로를 보기 전에 무조건 불렀다. 그래서 축구 실험
    #    (`soccer_trial`)이 Anthropic 400 을 맞고 공용 차단기를 내리자,
    #    무료 사슬(Gemini)로 도는 야구 판정이 **호출도 못 해보고** 죽었다.
    #      실사고 2026-09-05~06: MLB 발송 0/85 (0%). 오류 문자열이 구조를
    #      그대로 보여준다 —
    #      "잔액 소진으로 중단 (matchup:SF@NYM): soccer-trial/claude-sonnet-5"
    #      앞은 야구 호출부, 뒤는 축구가 남긴 사유다.
    #    무료가 주전이면 Anthropic 잔액은 이 판정과 무관하다.
    #    ⚠️ 예비 판정은 정의상 무료다 — Anthropic 잔액과 무관하므로 가드도 걸지
    #       않는다. 걸면 최종이 잔액을 다 쓴 순간 다음 슬레이트의 1차가 죽는다.
    if final and not _free_primary(role):
        abort_if_credit_gone(f"matchup:{jg.get('away')}@{jg.get('home')}")
    settings = get_settings()
    is_mock = settings.mock_judge if mock is None else mock
    home, away = jg.get("home") or "", jg.get("away") or ""
    home_form = await _form_or_analyze(jg, redis, date, "home", mock)
    away_form = await _form_or_analyze(jg, redis, date, "away", mock)
    # 🔴 [E 2026-09-02] 게이트를 **폼이 아니라 숫자**에 건다.
    #    판정 입력이 등급에서 원본 박스스코어로 바뀌었으므로, 없으면 못 하는 것은
    #    "헤이쿠 평가서"가 아니라 "3경기 숫자"다. 뉴스(평가서)는 보조 신호라
    #    빠져도 판정은 성립한다 — 없으면 뉴스 없이 간다.
    #    ⚠️ 숫자가 없으면 종전과 똑같이 탈락이다. 재료 없이 분석을 만들지 않는다.
    boxes = boxscore_payload(jg)
    if not boxes.get("home") or not boxes.get("away"):
        jg["form_unavailable"] = True
        logger.info("[matchup] %s vs %s 3경기 박스스코어 없음 — 추천 탈락 "
                    "(home=%s away=%s)", home, away,
                    bool(boxes.get("home")), bool(boxes.get("away")))
        return None
    # 상황 태그를 먼저 새긴다 — 실패해도 판정은 계속된다(로그 1줄).
    try:
        from app.engine.situation import attach as _sit_attach

        _sit_attach(jg)
    except Exception as exc:
        logger.warning("[situation] game=%s 부착 실패 — 판정은 계속: %s",
                       jg.get("game_id"), exc)
    # [변수 평의회 2026-09-06] 심의는 판정 **앞**에 선다 — 재판정이 아니라
    #   재료를 만드는 단계다. 자료1~11 과 같은 줄에서 한 상에 올라간다.
    #   실패해도 판정은 계속된다(심의록 없이 간다).
    try:
        from app.engine.council import run as _council

        await _council(jg, date, redis)
    except Exception as exc:
        logger.warning("[council] game=%s 실패 — 심의 없이 판정한다: %s",
                       jg.get("game_id"), exc)
    # 🔴 재료가 다 모인 지금 최종 권한을 선점한다. 박스스코어가 없어 위에서
    #    탈락했다면 권한은 아직 남아 있고, 자료가 도착한 다음 호출이 가져간다.
    if final and not await claim_final(redis, jg, date):
        logger.info("[matchup] game=%s 최종 권한을 다른 호출이 가져갔다 — 중단",
                    jg.get("game_id"))
        return None
    news = news_payload(home_form, away_form, jg)
    if not news:
        logger.info("[matchup] %s vs %s 뉴스 없음 — 숫자만으로 판정한다", home, away)
    if is_mock:
        verdict = _mock_matchup(home, away)
        apply_matchup(jg, verdict, settings)
        jg["final_verdict"] = final
        jg["judge_stage"] = "final" if final else "prelim"
        await persist_matchup_record(redis, jg, date)
        return verdict

    model = settings.matchup_model
    # [v1.1 2단계] 직전 판정을 입력 6번으로 넘긴다 — 재판정이 "처음부터 다시"가
    #   아니라 "무엇이 바뀌어 어디로 움직였나"가 되게 한다.
    #   (실측 사례: 안우진 등판 확인 → 두산 0.62→0.59 철회)
    prev = prev_verdict(jg)
    prompt = render_matchup_prompt(jg, boxes, news, prev)
    # [M-2 계측] 재료가 **실제로 프롬프트에 실렸는가.** 수집률(100%)과
    #   주입률이 갈리던 것을 잡는다 — 2026-09-02 카드 2장이 "자료8 부재"라
    #   적었는데 로그는 매칭 18/18 이었다.
    #   🔴 [2026-09-04] 자료8(타선 시즌)이 폐지되어 계측 대상을 **자료3(오늘
    #      타순 9명)** 으로 옮긴다. 같은 결함(수집≠주입)을 보는 자리이고,
    #      자료8이 사라졌다고 이 감시까지 사라지면 안 된다.
    # ⚠️ [2026-09-03] 자료3 은 **타순 9명이 있을 때만** Y 다.
    #    `lineups_payload` 는 선발투수 키를 항상 넣어 dict 가 비지 않는다 —
    #    비어있음으로 재면 타순이 없어도 Y 가 나온다(리허설에서 확인:
    #    `slots=0` 인데 자료3=Y). 로그·계측만 고친다. 조립은 불변.
    _m3 = lineups_payload(jg)
    _slots = min(len((( _m3.get(side) or {}).get("타순") or []))
                 for side in ("home", "away")) if _m3 else 0
    _has3 = _slots >= 9
    # [G1] 로그 문자열을 **한 번만** 만든다. 로그와 원장이 같은 것을 쓴다 —
    #   포맷을 두 번 적으면 언젠가 갈리고, 그때 리포트는 로그로 검증할 수 없다.
    _mat_msg = ("[materials] game=%s 자료3=%s(타순 %d명) 자료9=%s 자료10=%s "
                "자료11=%s" % (
                    jg.get("game_id"), "Y" if _has3 else "N", _slots,
                    "Y" if bullpen_payload(jg) else "N",
                    jg.get("material10_status") or "해당없음",
                    jg.get("material11_status") or "해당없음"))
    logger.info("%s", _mat_msg)
    await _trace(jg, date, TRACE_ASSEMBLE, summary=_mat_msg)
    # 같은 사실을 일일 요약이 읽을 수 있게 센다. 세기만 한다 — 이 결과는
    #   프롬프트에도 판정에도 되돌아가지 않는다.
    from app.engine.monitor_metrics import note_materials

    await note_materials(redis, sport, date, _has3)
    # [감시 L1] 판정 **시점의** 프롬프트를 남긴다. 사실 감사가 재렌더하면
    #   그 사이 바뀐 재료를 보게 되므로, 그때 그 원문이어야 한다.
    #   ⚠️ 이것은 **기록이다.** 판정 입력·프롬프트·모델 호출을 바꾸지 않는다.
    await _keep_prompt(redis, jg.get("game_id"), prompt)
    parsed = None
    # 🔴 [v1.3 A-3] **절단은 한도를 올려 재시도한다.** "짧게 쓰라"고 지시하면
    #    근거가 잘려 판정이 얇아진다 — 고칠 것은 출력이 아니라 그릇이다.
    #    실측 2026-09-02: output=4000 stop=max_tokens 로 잘린 응답이 JSON
    #    파싱에 2회 실패해 KIA@NC 판정이 통째로 탈락했다.
    budget = int(settings.matchup_max_tokens)
    for attempt in (1, 2):
        try:
            text = await complete_json(
                prompt, model=model, max_tokens=budget,
                role=role, mock=False)
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
        truncated = bool(text) and not str(text).rstrip().endswith("}")
        logger.warning("[matchup] JSON 파싱 실패 %d회 model=%s prompt_chars=%d "
                       "max_tokens=%d 응답%d자 절단추정=%s",
                       attempt, model, len(prompt), budget, len(text or ""),
                       truncated)
        if truncated and attempt == 1:
            budget = min(budget * 2, MAX_TOKENS_CEILING)
            logger.warning("[matchup] 절단으로 보인다 — 한도 %d 로 올려 재시도",
                           budget)
    if parsed is None:
        jg["form_unavailable"] = True
        # 🔴 최종이 답을 못 냈으면 **권한을 돌려놓는다.** 안 그러면 다음
        #    폴링이 "이미 완료"로 막혀 그 경기는 카드가 0장이 된다.
        if final:
            await release_final(redis, jg, date)
        logger.warning("[matchup] %s vs %s 분석 불가 model=%s — 추천 탈락",
                       home, away, model)
        return None
    apply_matchup(jg, parsed, settings)
    # 🔴 카드가 이 값을 읽는다. 최종 판정이 돈 경기는 **전체 카드**로 나가야
    #    한다 — 라인업만 바뀐 것으로 보고 라인업 전용 카드를 내면, 사용자는
    #    두 장뿐인 픽 중 한 장에서 바뀐 판정을 못 본다.
    jg["final_verdict"] = final
    jg["judge_stage"] = "final" if final else "prelim"
    # [G1] 판정 결과 1줄. 종전에는 판정이 **끝났다는 로그가 아예 없어서**
    #   "언제 어떤 확률이 나왔나"를 레저 스냅샷으로 역추적해야 했다.
    #   ⚠️ 새 계측이 아니다 — 이미 jg 에 들어간 값을 그대로 찍는다.
    #      원장은 이 줄을 복사할 뿐 더 알지 않는다.
    _jm = jg.get("matchup") or {}
    # 🔴 [2026-09-06] **설정값이 아니라 실제 응답 모델을 찍는다.**
    #    종전에는 `_jm["model"]`(= settings.matchup_model)을 찍었다. 무료
    #    사슬로 옮긴 뒤에는 그것이 거짓이다 — 시뮬 실측 2026-09-05:
    #      free provider=nvidia model=nvidia/nemotron-3-ultra-550b-a55b ok=True
    #      [matchup] … model=claude-sonnet-5      ← 로그와 원장이 다른 말을 했다
    #    폴백이 일어나면 어느 모델이 그 판정을 했는지가 사라지고, 그러면
    #    모델별 성적을 영영 못 가른다.
    #    `LAST_USAGE` 는 무료 경로(`_complete_free`)와 유료 경로 양쪽이
    #    호출 직후 채운다 — 그것이 원본이다.
    _actual = _real_model(_jm.get("model"))
    if _actual != _jm.get("model"):
        _jm["model_configured"] = _jm.get("model")
        _jm["model"] = _actual
        jg["model"] = _actual
    _judge_msg = ("[matchup] game=%s %s vs %s p_home=%.3f 우세=%s 확신도=%s "
                  "model=%s 회차=%s" % (
                      jg.get("game_id"), home, away, float(jg.get("p_claude") or 0),
                      _jm.get("우세"), _jm.get("확신도"), _actual,
                      "최종" if final else "예비"))
    logger.info("%s", _judge_msg)
    await _trace(jg, date, TRACE_JUDGE, summary=_judge_msg,
                 ref={"prompt_sha": _sha(prompt), "근거": _jm.get("근거"),
                      "변수": _jm.get("변수")})
    await persist_matchup_record(redis, jg, date)
    return parsed
