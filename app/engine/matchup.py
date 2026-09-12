"""매치업 판정 — 라인업 확정 시 경기당 1회. 팀 폼 캐시 히트면 재호출하지 않는다."""
from __future__ import annotations

import json
import logging

from app.collectors.base import ApiQuotaError
from app.config import get_settings
from app.engine.prompts import MATCHUP, baseball_material_note, fill
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


#: 창 길이는 `batter_recent` 한 곳에만 산다. 여기서 숫자를 다시 적지 않는다.
from app.engine.batter_recent import RECENT_GAMES as BATTER_RECENT_GAMES


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
        # 🔴 [BAT-4 2026-09-08] 이름 옆에 **최근 창의 숫자**를 얹는다.
        #    종전 자료3 은 이름·포지션뿐이고 숫자가 0개였다. 그래서 판정은
        #    타자를 **순서에서 추론**할 수밖에 없었다(잠정 70.4% vs 확정 51.5%).
        #    ⚠️ 여기는 **읽기만 한다.** 집계·창 길이는 `batter_recent` 가
        #       원본이고, 자료 번호를 새로 만들지 않는다.
        # 🔒 [BAT-6] 동결 게이트. 꺼져 있으면 자료3 은 BAT-4 이전과 같다.
        from app.config import get_settings

        recent = ((r.get(f"{side}_batter_recent") or {})
                  if get_settings().batter_material_enabled else {})
        rkey = f"최근{BATTER_RECENT_GAMES}"
        if slots:
            blk["타순"] = []
            for x in slots:
                if not isinstance(x, dict):
                    continue
                item = {"타순": x.get("slot"), "이름": x.get("name"),
                        "포지션": x.get("pos")}
                # ⚠️ 자료가 없는 선수에게 **빈 칸을 만들지 않는다** — 0으로
                #    채우면 수집 실패가 부진으로 읽힌다.
                stat = recent.get(str(x.get("name") or "").strip())
                if stat:
                    item[rkey] = stat
                blk["타순"].append(item)
        else:
            # 🔴 [2026-09-07] 폴백이 **문자열을 그대로** 넣고 있었다.
            #    `"최원준-김민혁-…"` 이 들어가면 길이를 세는 계측이 문자 수를
            #    센다 — 실측 `[materials] 자료3=Y(타순 35명)`.
            #    9명 확인이 곧 확정 판정의 조건(v1.3 A-1)이므로 이 착시는
            #    "확정인데 확정 아님"·"아닌데 확정"을 둘 다 만들 수 있다.
            #    ⚠️ 이름 분해 규칙은 `lineup_diff.parse_order` 가 원본이다 —
            #       여기서 `split("-")` 를 다시 쓰지 않는다(사본 금지).
            raw = ((r.get(f"{side}_lineup") or {}).get("order")
                   or jg.get(f"lineup_{side}"))
            if isinstance(raw, str) and raw:
                from app.engine.lineup_diff import parse_order

                blk["타순"] = []
                for i, (nm, pos) in enumerate(parse_order(raw), 1):
                    item = {"타순": i, "이름": nm, "포지션": pos}
                    if recent.get(nm):
                        item[rkey] = recent[nm]
                    blk["타순"].append(item)
            else:
                blk["타순"] = raw
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
        # [상대 보정 2026-09-07] **읽기만 한다** — 조립·I/O 는 파이프라인이
        #   끝냈다(`opponent_adjust.attach`). 자료10·11 과 같은 규약이다.
        adj = ((jg.get("m1_adjust") or {}).get(side)) or {}
        if adj:
            blk["상대보정"] = adj
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
     🔴 `주의`가 붙어 **분위수가 없으면** 표본이 얇아 일부러 뺀 것이다.
     그때는 `이닝` 배열을 직접 읽어라. **없는 p25·p50 을 지어내지 마라** —
     분위수는 추정이고 배열은 사실이다.
   `선발기준선`: 같은 리그 선발들의 **최근 창** 평균 이닝·실점. 표본이 얇은
     선발이 리그 평균과 견줘 어디쯤인지 볼 때만 쓴다. 특정 투수의 값이
     아니므로 그 자체를 우열의 근거로 쓰지 마라.
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


def branch_payload(jg: dict) -> dict:
    """자료14 — 분기점 조사 결과. **읽기만 한다** — 조립은 파이프라인이 끝냈다.

    🔴 판정이 지목한 분기점을 유형별로 갈라 답한 것이다. 기록형은 우리 DB 가
       즉답한다 — 실측 2026-09-07: 퍼플렉시티가 "미확인"으로 돌려준 질문
       6건이 전부 기록으로 답할 수 있는 것이었다.
    """
    from app.engine.branch_resolve import payload as _bp

    return _bp(jg)


def ledger_payload(jg: dict) -> dict:
    """변수 대장의 두 축. **읽기만 한다** — 조립은 파이프라인이 끝냈다."""
    return {"ref": jg.get("material10") or {},
            "ctx": jg.get("material11") or {}}


def insert_scout(prompt: str, scout: dict | None) -> str:
    """[SCT-1] 정찰 결과를 자료15 로 규칙 앞에 끼운다.

    🔴 정찰이 비면 **원문 그대로** 돌려준다 — 프롬프트가 바이트 동일이라
       `test_batter_freeze_gate`(BAT-1 시점 대조)가 깨지지 않는다.
    ⚠️ `.format` 을 쓰지 않는다 — 블록 안 중괄호가 포맷으로 해석되면 터진다
       (`insert_ledger` 가 같은 이유로 replace 를 쓴다).
    """
    if not scout or not (scout.get("변수") or scout.get("발견")):
        return prompt
    import json as _json

    from app.engine.prompts import SCOUT_BLOCK

    body = _json.dumps({"발견": scout.get("발견") or [],
                        "변수": scout.get("변수") or [],
                        "요약": scout.get("요약")},
                       ensure_ascii=False, default=str)
    return prompt.replace(_RULES_MARK,
                          SCOUT_BLOCK.replace("{{SCOUT}}", body) + _RULES_MARK, 1)


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


#: MLB 정규시즌은 연장으로 승부를 가른다 — 무승부 최종 스코어가 없다.
#  KBO·NPB 는 무승부가 있다(`elo_core` 가 `D` 를 다룬다).
_DRAW_LEAGUES = ("kbo", "npb")


def check_flow(verdict: dict, sport: str) -> list[str]:
    """`전개.예상점수` 가 판정과 어긋나는지 본다. 반환은 무효 사유 목록.

    🔴 **프롬프트에 적는 것만으로는 부족하다** — `clamp_adjustment` 와 같은
       태도다. 모델이 규칙을 어겨도 틀린 값이 카드로 나가면 안 된다.

    실측 2026-09-07 NYY@SD: `승자 = San Diego Padres` 인데 `예상점수 3-3`
    (무승부)이었다. MLB 는 무승부로 끝나지 않으므로 그 스코어는 존재할 수
    없는 값이고, 승자 지목과도 어긋난다. 프롬프트는 "예상 점수와 p 가
    어긋나면 다시 보라"고 이미 적고 있었는데 통과하지 못했다.

    ⚠️ **고쳐 쓰지 않고 지운다.** 점수를 우리가 지어내면 그건 판정이 아니라
       우리 추정이다. 틀린 값을 빼고 왜 뺐는지 남긴다.
    """
    flow = (verdict or {}).get("전개") or {}
    sc = flow.get("예상점수") or {}
    if not sc:
        return []
    bad: list[str] = []
    try:
        h, a = int(sc.get("홈")), int(sc.get("원정"))
    except (TypeError, ValueError):
        return ["예상점수가 정수가 아니다"]
    if h < 0 or a < 0:
        bad.append(f"예상점수가 음수다 ({a}-{h})")
    if h == a and (sport or "").lower() not in _DRAW_LEAGUES:
        bad.append(f"{sport.upper()} 는 무승부로 끝나지 않는데 예상점수가 "
                   f"동점이다 ({a}-{h})")
    p = verdict.get("p_home")
    if p is not None and h != a:
        try:
            pf = float(p)
        except (TypeError, ValueError):
            pf = None
        # 확률과 점수가 **반대**를 가리키면 무효. 0.50 은 어느 쪽도 아니다.
        if pf is not None and pf != 0.5 and (pf > 0.5) != (h > a):
            bad.append(f"예상점수({a}-{h})와 p_home({pf})가 반대를 가리킨다")
    return bad


def _name_hits(winner: str, team: str) -> bool:
    """승자 표기가 그 팀을 가리키는가.

    🔴 판정은 **현지어 약칭**으로 쓴다("삼성"·"西武"). `jg` 의 팀명은 Odds 표기
       ("Samsung Lions")라 문자열로는 안 맞는다 — 내 계약 테스트가 이것을 잡았다.
    ⚠️ 대응표를 여기 적지 않는다. 원본은 `news_rss.QUERY_ALIAS`(Odds→현지어)다.
       없는 팀은 그대로 두므로 KBO·NPB 밖에서도 안전하다.
    """
    w = (winner or "").strip().lower()
    if not w:
        return False
    cands = [team]
    try:
        from app.collectors.news_rss import QUERY_ALIAS

        alias = QUERY_ALIAS.get(team)
        if alias:
            cands.append(alias)
    except Exception:          # 별칭을 못 읽어도 Odds 표기로는 본다
        pass
    for c in cands:
        t = (c or "").strip().lower()
        if t and (w == t or w in t or t in w):
            return True
    return False


def normalize_winner(verdict: dict, jg: dict) -> str | None:
    """`결론.승자` 가 **이 경기의 팀**을 가리키는지 본다. 아니면 p_home 으로 정정.

    🔴 **아무도 이 칸을 검사하지 않았다.** `check_flow` 는 예상점수만 본다.
       절제 실험 2026-09-11 (운영 재료 game=1733 키움@삼성, 4회 호출):
         승자='home' 2회 · 승자='KT Wiz'(**경기에 없는 팀**) 1회 · 정상 2회
       gemini 는 seed 를 받지 않아(`openai_compat._NO_SEED`) 회차마다 흔들린다.

    ⚠️ **정정은 창작이 아니다** — 방향은 `p_home` 이 이미 정했다. 원장 쪽
       `predicted_side` 도 "favored 가 없으면 p_home 으로 환산한다"는 같은 규약을
       쓴다. 다만 **정정했다는 사실을 숨기지 않는다**(로그 + `승자_정정`).
       ⚠️ 모듈 이름을 여기 적지 않는다 — `test_judgement_paths_do_not_read_the_ledger`
          가 판정 코드에서 그 문자열을 소스로 막는다(판정 비개입). 가드가 맞다.
    ⚠️ 모호하면 손대지 않는다: p_home 이 없거나 0.50 이거나, 승자 표기가 두 팀
       **모두**에 걸리면 그대로 둔다.
    """
    c = (verdict or {}).get("결론") or {}
    w = str(c.get("승자") or "").strip()
    home, away = jg.get("home") or "", jg.get("away") or ""
    hit_h, hit_a = _name_hits(w, home), _name_hits(w, away)
    if hit_h != hit_a:                 # 한쪽에만 걸린다 = 정상
        return None
    p = verdict.get("p_home")
    try:
        pf = float(p)
    except (TypeError, ValueError):
        return None
    if pf == 0.5:
        return None                    # 방향이 없다 — 손대지 않는다
    want = home if pf > 0.5 else away
    if not want:
        return None
    why = (f"승자 {w!r} 가 이 경기의 팀이 아니다"
           if not (hit_h or hit_a) else f"승자 {w!r} 가 두 팀 모두에 걸린다")
    c["승자"] = want
    verdict["결론"] = c
    verdict["승자_정정"] = f"{why} — p_home={pf} 로 {want} 로 정정"
    logger.warning("[matchup] 🔴 %s → %s (game=%s)", why, want, jg.get("game_id"))
    return want


def apply_winner(jg: dict, verdict: dict) -> bool:
    """[ORD-3 2026-09-11 사용자 지시] **어느 팀이 이기는지만 싣는다.**

    "추천 로직도 다 삭제…수치는 전부다 삭제…" / "설명도 삭제…서치에 의한
     정보만 명시…" / "그리고 어느팀이 승리한다만 제미나이가 판다…"

    🔴 확률이 없으므로 `normalize_winner` 의 정정도 없다 — 고칠 근거가 사라졌다.
       그래서 **경기의 팀이 아니면 판정을 버린다.** 실측 2026-09-11: gemini 가
       경기에 없는 `KT Wiz` 를 4회 중 1회 냈다. 고쳐 쓰지 않고 버린다.

    반환: 실었으면 True, 승자가 이 경기의 팀이 아니면 False.
    """
    w = str((verdict or {}).get("승자") or "").strip()
    home, away = jg.get("home") or "", jg.get("away") or ""
    hit_h, hit_a = _name_hits(w, home), _name_hits(w, away)
    if hit_h == hit_a:                      # 둘 다거나 둘 다 아니다
        logger.warning("[order] 🔴 승자 %r 가 이 경기(%s@%s)의 팀이 아니다 — "
                       "판정을 버린다 (game=%s)", w, away, home, jg.get("game_id"))
        return False
    jg["matchup"] = {"승자": home if hit_h else away,
                     "model": verdict.get("model")}
    # [ORD-12 사용자 지시] "확신 한 칸만 살려라." 온 경우에만 싣는다 —
    #   ORD-3 경로(승자만)는 이 칸이 없고, 그쪽 동작은 바뀌지 않는다.
    #   ⚠️ 모르는 라벨은 `하` 로 떨어뜨린다(`verdict.level`). 낮은 쪽이 안전하다.
    if verdict.get("확신") is not None:
        from app.engine.verdict import level as _lvl

        jg["matchup"]["확신"] = _lvl(verdict.get("확신"))
    # 🔴 [SRCH-6] 제미니가 쓴 분석글. **왔을 때만 싣는다** — ORD-3 경로(승자만)와
    #    ORDER_V2 는 이 칸이 없고, 그쪽 동작은 바뀌지 않는다.
    #    ⚠️ 한 글자도 고치지 않는다(사용자 지시 "그대로 보여달라").
    if str(verdict.get("서술") or "").strip():
        jg["matchup"]["서술"] = str(verdict["서술"]).strip()
    jg["winner"] = jg["matchup"]["승자"]
    return True


def apply_matchup(jg: dict, verdict: dict, settings=None) -> None:
    from app.engine.starter_recent import (THIN_SHRINK, THIN_STARTS,
                                           thin_sample_sides)

    s = settings or get_settings()
    # [WIN-1] 승자 칸이 이 경기의 팀을 가리키는지 **먼저** 본다. 클립 전에 해야
    #   p_home 원값으로 방향을 판단한다.
    normalize_winner(verdict, jg)
    p = clip_p_home(verdict.get("p_home"), s)
    conf_kr = verdict.get("확신도") or "중"
    model = verdict.get("model") or s.matchup_model
    jg["p_claude"] = p
    # 🔴 전개 정합 — 어긋난 예상점수는 **싣지 않는다.** 고쳐 쓰지 않는다.
    v = dict(verdict)
    why = check_flow({**v, "p_home": p}, jg.get("sport") or "")
    if why:
        flow = dict(v.get("전개") or {})
        flow.pop("예상점수", None)
        flow["예상점수_생략"] = " · ".join(why)
        v["전개"] = flow
        logger.warning("[matchup] game=%s 예상점수 생략 — %s",
                       jg.get("game_id"), " · ".join(why))
    # 🔴 [SR-1 2026-09-10] **표본이 얇으면 확신을 깎는다.** 규칙은 대원칙에
    #    이미 있었는데(`app/engine/CLAUDE.md`) 코드가 강제하지 않아 안 지켜졌다.
    #    실사고 2026-09-09 LAA@Boston: 근거2 가 "최근 **2경기** 12이닝 3실점
    #    14K 0BB — 뛰어난 제구 안정감"이었고 그걸로 홈 54% 를 냈다. 실제
    #    5.1이닝 6자책, 원정 6-4 승.
    #    ⚠️ **방향은 바꾸지 않는다** — 0.50 쪽으로 당기는 것이지 넘기는 것이
    #       아니다. 적중률은 그대로고 보정만 좋아진다(실측 확인).
    thin = thin_sample_sides(jg)
    if thin:
        p = round(0.5 + (p - 0.5) * THIN_SHRINK, 4)
        # 🔴 **`중` → `하` 로는 낮추지 않는다.** `하` 는 단순한 낮은 확신이
        #    아니라 **거부권**이다(CLAUDE.md: "확신도 '하'/패스는 거부권").
        #    한 단계씩 기계적으로 내리면 얇은 표본 경기가 전부 "판정 패스"로
        #    바뀐다 — 대원칙이 말한 "낮춘다"가 아니라 "죽인다"가 된다.
        #    계약 테스트(test_flagged_pick_never_recommended_regression)가
        #    이것을 잡았다: 목 슬레이트 전 경기가 거부권으로 넘어갔다.
        conf_kr = "중" if conf_kr == "상" else conf_kr
        v = {**v, "확신도": conf_kr,
             "표본축소": f"선발 최근 등판 {THIN_STARTS}경기 이하 ({','.join(thin)})"}
        jg["p_claude"] = p
        logger.info("[matchup] game=%s 표본 얇음 %s — p→%.3f 확신도→%s",
                    jg.get("game_id"), ",".join(thin), p, conf_kr)
    jg["matchup"] = {**v, "p_home": p, "model": model}
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
        # 🔒 [BAT-6] 동결 게이트가 꺼져 있으면 빈 문자열이다.
        BATTER_MATERIAL_NOTE=baseball_material_note(),
        STARTERS_RECENT_JSON=json.dumps(
            starters_recent_payload(jg), ensure_ascii=False, default=str),
        PREV_VERDICT_JSON=json.dumps(prev, ensure_ascii=False, default=str),
        LINEUP_INTENT_JSON=json.dumps(intent_payload(jg), ensure_ascii=False,
                                      default=str),
        BULLPEN_JSON=json.dumps(bullpen_payload(jg), ensure_ascii=False, default=str),
        ELO_JSON=json.dumps(elo_payload(jg), ensure_ascii=False, default=str),
        BRANCH_JSON=json.dumps(branch_payload(jg), ensure_ascii=False,
                               default=str),
    )
    # [C4 변수 대장] 자료10·11 을 한 블록으로. 둘 다 비면 원문 그대로다.
    prompt = insert_ledger(prompt, ledger_payload(jg))
    return prompt


# ═══════════════════════════════════════════════════════════════════
# [ORD-1 2026-09-11 사용자 지시] ③ 결론 · ④ 애매할 때만 DB.
#   ①② 는 `deepsearch.prescout` · `deepsearch.reinforce` 다.
# ═══════════════════════════════════════════════════════════════════

def game_brief(jg: dict) -> str:
    """① 이 보는 **경기 정보 전부.** 수치·DB 는 들어가지 않는다.

    🔴 여기 무엇을 넣느냐가 이 수정의 경계선이다. 성적·레이팅·최근 폼을 한 줄이라도
       넣으면 그 순간 다시 "DB 먼저"가 된다. 넣는 것은 **경기 자체**뿐이다 —
       누가 어디서 언제 붙고, 선발이 누구이며, 일정·환경이 어떤가.
    ⚠️ 값은 전부 `jg` 가 원본이다. 여기서 계산하거나 손으로 적지 않는다.
    """
    sport = (jg.get("sport") or "").lower()
    lines = [f"· 종목/리그: {jg.get('league') or sport.upper()}",
             f"· 대진: {jg.get('away')} (원정) @ {jg.get('home')} (홈)"]
    st = jg.get("starts_at")
    if st:
        lines.append(f"· 시작(UTC): {st}")
    for side, label in (("away", "원정"), ("home", "홈")):
        lines.append(f"· {label} 선발: {_starter(jg, side) or '미정'}")
    if jg.get("venue"):
        lines.append(f"· 구장: {jg.get('venue')}")
    lines.append(f"· 타순 상태: {jg.get('lineup_status') or 'none'}")
    ctx = jg.get("material11") or {}
    for side, label in (("away", "원정"), ("home", "홈")):
        c = ctx.get(side) or {}
        if c:
            lines.append(f"· {label} 일정: "
                         + " · ".join(f"{k} {_short(v)}" for k, v in c.items()))
    w = ctx.get("날씨")
    if w:
        lines.append("· 날씨: " + (" · ".join(f"{k} {_short(v)}"
                                             for k, v in w.items())
                                  if isinstance(w, dict) else _short(w)))
    return "\n".join(lines)


#: 한 항목의 길이 상한. 자료11 `날씨.수치` 는 LLM 산문이라 400자가 넘게 온다 —
#  그것이 통째로 들어가면 ① 이 "경기 한 장"이 아니라 남의 분석문을 읽게 된다.
_BRIEF_MAX = 120


def _short(v) -> str:
    t = " ".join(str(v).split())
    return t if len(t) <= _BRIEF_MAX else t[:_BRIEF_MAX] + "…"


def _starter(jg: dict, side: str) -> str:
    """오늘 선발 이름. **API 예고 선발(games 컬럼)이 먼저다.**

    🔴 `starter_recent.pitcher_name` 은 `research.{side}_pitcher` 를 먼저 본다.
       그 칸은 LLM 이 채운 것이라 실측 2026-09-11 game=5624 에서
       `"Baltimore SP (확정 선발 불명)"` 이 들어 있었고 — 같은 경기의 games
       컬럼에는 `Chris Bassitt` 이 있었다. ① 은 경기 사실만 봐야 하므로
       **API 값을 먼저 쓰고, 없을 때만** 종전 함수로 내려간다.
    ⚠️ `pitcher_name` 자체는 건드리지 않는다 — 자료4 조립이 그것을 쓴다.
    """
    api = str(jg.get(f"{side}_pitcher") or "").strip()
    if api:
        return api
    from app.engine.starter_recent import pitcher_name

    return pitcher_name(jg, side)


def _fmt_branches(pre: dict) -> str:
    out = []
    for i, b in enumerate(pre.get("갈림길") or [], 1):
        q = str(b.get("질문") or "").strip()
        why = str(b.get("왜") or "").strip()
        out.append(f"{i}. {q}" + (f"  ← {why}" if why else ""))
    return "\n".join(out) or "(없음)"


def _fmt_evidence(reinf: dict) -> str:
    """🔴 0건이면 **0건이라고 쓴다.** 빈 칸으로 두면 결론이 지어내기 시작한다."""
    rows = (reinf or {}).get("자료") or []
    if not rows:
        asks = (reinf or {}).get("질문") or []
        return ("🔴 **조사 결과 0건.** 위 갈림길에 대해 위성·퍼플렉시티·X 가 오늘 "
                "아무것도 찾지 못했다"
                + (f" (던진 질문 {len(asks)}개)." if asks else ".")
                + " 답을 모르는 상태로 결론을 내라 — 모르는 것을 아는 척하지 마라.")
    # 🔴 **답과 참고를 갈라 싣는다.** 위성은 질문에 답한 것이 아니라 오늘
    #    긁어 둔 공시·이적 목록이다(실측 2026-09-11 game=5624: 48건 전부
    #    트랜잭션). 한 칸에 섞으면 결론이 무관한 줄을 갈림길의 근거로 읽는다.
    ans = [r for r in rows if r.get("소스") != "satellite"]
    ref = [r for r in rows if r.get("소스") == "satellite"]
    out = []
    if ans:
        out.append("【질문에 대한 답】")
        for i, r in enumerate(ans, 1):
            q = str(r.get("질문") or "").strip()
            tag = (f"[{r.get('소스')}"
                   + (f"/{r.get('소스유형')}" if r.get("소스유형") else "") + "]")
            out.append(f"{i}. {tag} " + (f"({q}) " if q else "")
                       + str(r.get("답") or "")
                       + (f"  {r.get('url')}" if r.get("url") else ""))
    else:
        out.append("【질문에 대한 답】 🔴 0건 — 위 갈림길에 아무도 답하지 못했다.")
    if ref:
        out.append("\n【참고 · 오늘 구단 공시/이적】 — **질문에 대한 답이 아니다.** "
                   "갈림길과 직접 닿는 줄만 골라 쓰고, 나머지는 무시하라.")
        for i, r in enumerate(ref, 1):
            out.append(f"참고{i}. {str(r.get('답') or '')[:200]}")
    return "\n".join(out)


def render_conclude_prompt(jg: dict, brief: str, pre: dict, reinf: dict) -> str:
    """③ 결론 프롬프트. **자료1~14 가 들어가지 않는다.**"""
    from app.engine.deepsearch import _today_kst
    from app.engine.prompts import CONCLUDE

    sport = (jg.get("sport") or "").lower()
    return fill(CONCLUDE,
                LEAGUE=jg.get("league") or sport.upper(),
                AWAY=jg.get("away") or "", HOME=jg.get("home") or "",
                TODAY=_today_kst(), BRIEF=brief,
                BRANCHES=_fmt_branches(pre),
                VARIABLES="\n".join(f"· {v}" for v in (pre.get("변수") or []))
                or "(없음)",
                EVIDENCE=_fmt_evidence(reinf))


async def _judge_v3(jg: dict, redis, date: str, *, final: bool,
                    pool=None) -> dict | None:
    """[ORD-20 · SRCH-1] 수집 → 선별 → 판정 → DB 참조. **제미니 1회로 끝난다.**

    사용자 지시 2026-09-12: "경기에 대한 것만 서치해 온다…ai가 거른다…
    ai가 db 참조 승패를 예측한다" · "db 관련도 ai 판단에 의해…자율적으로"

    🔴 **탈락 사유를 전부 남긴다.** 어느 단계에서 멈췄는지 모르면 "봇이 죽었나"와
       "재료가 없었나"를 사용자가 구분할 수 없다(실측 2026-09-01 전례).
    🔴 최종 권한을 잡았다가 실패하면 **반납한다** — 안 그러면 다음 폴링이
       "이미 완료"로 막혀 그 경기는 카드가 0장이 된다(P0 전례 2026-09-06).
    """
    from app.engine import dbref, gather, triage, verdict

    async def _drop(why: str):
        jg["form_unavailable"] = True
        jg.setdefault("order_v3", {})["탈락"] = why
        if final:
            await release_final(redis, jg, date)
        logger.warning("[v3] %s@%s 탈락 — %s",
                       jg.get("away"), jg.get("home"), why)
        return None

    # ① 수집 — 질문 없이. collect 가 크롤러 선발로 jg 를 먼저 메운다(ORD-16).
    col = await gather.collect(jg, redis, date, pool=pool)
    if not col["자료"]:
        return await _drop("수집 0건")
    brief = game_brief(jg)

    # ② 선별 — AI 가 거르고 갈림길을 세운다.
    tri = await triage.run(jg, brief, col["자료"])
    if tri is None:
        return await _drop("선별 실패")
    if not tri["채택"]:
        # 🔴 재료 없이 판정하지 않는다(절대 규칙 6).
        return await _drop("채택 0건")

    # 🔴 [SRCH-3] **검색 — 선별이 요청했을 때만.** 여기가 이 경로의 유일한
    #    유료 검색 지점이다. 요청이 비면 한 채널도 안 부른다(경기당 $0.10).
    #    ⚠️ 결과를 `채택` 에 **합친다** — 검색해 놓고 ③이 못 보면 돈만 쓴 것이다.
    #       다만 `계측` 은 덮지 않는다. 선별이 센 숫자와 섞으면 상태 이원화다.
    asks = tri.get("검색요청") or []
    found = await gather.search(jg, asks, date) if asks else {"자료": [], "출처": {}}
    if found["자료"]:
        tri["채택"] = list(tri["채택"]) + found["자료"]

    # ③ 판정 — 조사 결과 + 검색 결과로 승자 + 확신.
    v = await verdict.decide(jg, brief, tri)
    if v is None:
        return await _drop("판정 실패")

    # ④ DB 참조 — 통째로 주고 AI 가 자율 판단. 실패해도 ③ 판정을 쓴다.
    #    🔴 [SRCH-1 2026-09-12] **여기가 끝이다.** 2차 검증(Anthropic)을 지웠다 —
    #       사용자 지시 "최종 판정 2단계는 삭제..1단계로 제미니 최종 판정으로 간다".
    #       ⚠️ 2차가 검색 요청자였다. 그 역할은 ②선별(`triage.없는것`)로 간다
    #          (SRCH-3). 그전까지 이 경로의 외부 유료 호출은 **0** 이다.
    ref = await dbref.recheck(jg, tri, v)
    jg["order_v3"] = {
        "수집": col["출처"], "계측": tri["계측"],
        "갈림길목록": tri["갈림길"], "자료": tri["채택"],
        "질문": [], "출처": col["출처"],
        "없는것": tri["없는것"],
        "DB있음": ref["있음"], "DB없음": ref["없음"], "DB본것": ref["본것"],
        "DB판정": ref["판정"], "승자변경": ref["승자변경"], "DB사유": ref["사유"],
        # 🔴 [SRCH-3] 조용한 0 금지 — "검색을 안 했다"와 "했는데 0건"은 다르다.
        "검색요청": list(asks), "검색n": len(found["자료"]),
        "검색출처": found["출처"],
    }
    if not apply_winner(jg, {"승자": ref["승자"], "확신": ref["확신"]}):
        return await _drop("승자가 이 경기의 팀이 아니다")
    jg["final_verdict"] = final
    jg["judge_stage"] = "final" if final else "prelim"
    await persist_matchup_record(redis, jg, date)
    logger.info("[v3] %s@%s 승자 %s · 확신 %s · 수집%s 채택%d · 검색%d→%d · DB %s%s",
                jg.get("away"), jg.get("home"), jg.get("winner"),
                (jg.get("matchup") or {}).get("확신"), col["출처"],
                tri["계측"]["채택"], len(asks), len(found["자료"]), ref["판정"],
                " 🔴승자변경" if ref["승자변경"] else "")
    return {"승자": ref["승자"], "확신": ref["확신"]}


async def judge_matchup(jg: dict, redis, date: str, *,
                        mock: bool | None = None,
                        allow_final: bool = False, pool=None) -> dict | None:
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
    # 🔴 [ORD-2 2026-09-11 사용자 지시] **최근 3경기 폼도 삭제.** 새 순서에서
    #    판정은 오늘 조사 결과만 본다 — 폼을 만들어 봐야 프롬프트에 들어가지
    #    않는다. 만들지 않으면 팀당 LLM 호출 1회도 함께 사라진다.
    #    ⚠️ 스위치가 꺼진 종전 경로는 한 글자도 바뀌지 않는다.
    _order_v2 = bool(getattr(settings, "order_v2", False)) and not is_mock
    # 🔴 [ORD-20] v3 도 자료1~14 를 안 쓴다 — 여기서 함께 건너뛰지 않으면
    #    **팀 폼 LLM 2콜을 만들어 놓고 버린다.** 계약 테스트가 이 자리를 잠근다.
    _order_v3 = bool(getattr(settings, "order_v3", False)) and not is_mock
    _skip_db = _order_v2 or _order_v3
    if _skip_db:
        home_form, away_form = {}, {}
    else:
        home_form = await _form_or_analyze(jg, redis, date, "home", mock)
        away_form = await _form_or_analyze(jg, redis, date, "away", mock)
    # 🔴 [E 2026-09-02] 게이트를 **폼이 아니라 숫자**에 건다.
    #    판정 입력이 등급에서 원본 박스스코어로 바뀌었으므로, 없으면 못 하는 것은
    #    "헤이쿠 평가서"가 아니라 "3경기 숫자"다. 뉴스(평가서)는 보조 신호라
    #    빠져도 판정은 성립한다 — 없으면 뉴스 없이 간다.
    #    ⚠️ 숫자가 없으면 종전과 똑같이 탈락이다. 재료 없이 분석을 만들지 않는다.
    boxes = {} if _skip_db else boxscore_payload(jg)
    if not _skip_db and (not boxes.get("home") or not boxes.get("away")):
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

        # [ORD-2] 새 순서에서는 심의록이 들어갈 칸(자료2)이 없다 — 돌리면
        #   쓰이지 않는 LLM 호출만 나간다.
        if not _skip_db:
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
    # 🔴 [ORD-20 2026-09-12] **새 순서(1~4단계).** 수집 → 선별 → 판정 → DB 참조.
    #    ⚠️ 호출 순서가 계약이다: collect → game_brief → triage → decide →
    #       recheck. collect 가 먼저여야 game_brief 가 선발을 본다(ORD-16).
    #    ⚠️ 단계마다 탈락 사유가 다르고 **전부 남긴다** — 조용한 0 을 만들지 않는다.
    if _order_v3:
        return await _judge_v3(jg, redis, date, final=final, pool=pool)
    # 🔴 [ORD-2 2026-09-11 사용자 지시] **DB 를 판정 입력에서 전부 뺀다.**
    #    "데이타 베이스는 전부 삭제...최근 3경기 폼도 삭제...db가 답을 바꾼다."
    #    그래서 새 순서에서는 `render_matchup_prompt` 를 **부르지 않는다** —
    #    빈 자료로 부르면 "자료1 없음"이 찍힌 프롬프트가 만들어질 뿐이다.
    #
    #    ⚠️ **종전 경로로 폴백하지 않는다.** ORD-1 에는 폴백이 있었지만, 이제
    #       자료가 조립돼 있지 않아 폴백해도 빈 프롬프트다. 조사가 안 됐으면
    #       **판정하지 않는다** — 절대 규칙 6 "재료 없으면 분석 생성 금지".
    #       미발송에는 사유가 남는다(`form_unavailable` + 로그).
    _pre = _reinf = None
    if _order_v2:
        from app.engine.deepsearch import prescout as _prescout
        from app.engine.deepsearch import reinforce as _reinforce

        _brief = game_brief(jg)
        try:
            _pre = await _prescout(jg, _brief)
        except Exception as exc:
            logger.warning("[order] game=%s 갈림길 실패: %s", jg.get("game_id"), exc)
            _pre = None
        if _pre is None:
            jg["form_unavailable"] = True
            if final:
                await release_final(redis, jg, date)
            logger.warning("[order] %s vs %s 갈림길을 못 세웠다 — 추천 탈락",
                           away, home)
            return None
        try:
            _reinf = await _reinforce(jg, _pre, redis, pool=pool)
        except Exception as exc:
            logger.warning("[order] game=%s 보강 실패: %s", jg.get("game_id"), exc)
            _reinf = {"자료": [], "출처": {}, "질문": _pre.get("조사요청") or []}
        # 🔴 조사가 통째로 비면 남는 것은 팀 이름뿐이다. 그 위에서 확률을 만드는
        #    것이 바로 "기억으로 판정하기"다. 만들지 않는다.
        if not (_reinf.get("자료") or []):
            jg["form_unavailable"] = True
            jg["order_v2"] = {"갈림길": len(_pre.get("갈림길") or []),
                              "질문": len(_reinf.get("질문") or []),
                              "보강": 0, "출처": {}, "탈락": "보강 0건"}
            if final:
                await release_final(redis, jg, date)
            logger.warning("[order] %s vs %s 보강 자료 0건 — 추천 탈락 "
                           "(질문 %d개를 던졌으나 아무도 답하지 못했다)",
                           away, home, len(_reinf.get("질문") or []))
            return None
        prompt = render_conclude_prompt(jg, _brief, _pre, _reinf)
    else:
        prompt = render_matchup_prompt(jg, boxes, news, prev)
    # 🔴 [SCT-1 2026-09-11] 종전 경로의 정찰. 스위치가 꺼져 있을 때만 돈다.
    if not _order_v2 and getattr(settings, "deepsearch_first", False):
        try:
            from app.engine.deepsearch import scout as _scout

            jg["scout"] = await _scout(jg, prompt, redis)
        except Exception as exc:
            logger.warning("[matchup] 정찰 실패 — 종전 경로로 간다 game=%s: %s",
                           jg.get("game_id"), exc)
            jg["scout"] = None
        prompt = insert_scout(prompt, jg.get("scout"))
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
    async def _ask(prompt: str) -> dict | None:
        """모델 1문. **루프 본문은 종전 그대로다** — 들여쓰기만 바뀌었다.
        꺼낸 이유: ④(애매하면 DB 붙여 재질의)가 같은 루프를 써야 하는데,
        인라인이면 그 자리에 루프를 한 벌 더 적게 된다 — 사본이다.
        """
        parsed = None
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
            # 🔴 [ORD-4 P0 2026-09-12] **수락 키가 경로마다 다르다.**
            #    새 순서의 출력은 `{"승자": "..."}` 하나이고 확률이 없다.
            #    종전 조건(`"p_home" in parsed`)이 그대로 남아 있어 정상
            #    판정을 전부 버렸다 — 실사고 09:4x MLB 5632·5633 둘 다
            #    "응답19자 · 분석 불가 · 추천 탈락". 슬레이트가 통째로
            #    카드 0장이 되는 길이었다.
            #    ⚠️ 종전 경로는 **느슨해지지 않는다** — 그쪽은 확률이 필수다.
            _want = "승자" if _order_v2 else "p_home"
            if parsed and _want in parsed:
                parsed["model"] = model
                break
            parsed = None
            truncated = bool(text) and not str(text).rstrip().endswith("}")
            # 🔴 **무엇을 기대했는지 함께 적는다.** ORD-4 실사고에서 이 줄이
            #    "응답19자"만 말해 모델 탓처럼 읽혔다 — 실제로는 그 19자가
            #    정상 답이었고 우리가 엉뚱한 키를 찾고 있었다.
            logger.warning("[matchup] JSON 파싱 실패 %d회 model=%s prompt_chars=%d "
                           "max_tokens=%d 응답%d자 절단추정=%s 기대키=%s 받은키=%s",
                           attempt, model, len(prompt), budget, len(text or ""),
                           truncated, _want,
                           sorted(parse_json_object(text) or {}) or "(없음)")
            if truncated and attempt == 1:
                budget = min(budget * 2, MAX_TOKENS_CEILING)
                logger.warning("[matchup] 절단으로 보인다 — 한도 %d 로 올려 재시도",
                               budget)
        return parsed

    parsed = await _ask(prompt)
    # 🔴 [ORD-2 2026-09-11 사용자 지시] **④ 는 없다.** "데이타 베이스는 전부
    #    삭제…db가 답을 바꾼다."  실측(ORD-1 리허설 3경기)이 그 말대로였다 —
    #    ④ 가 3/3 돌았고 NYM@NYY 는 0.54 NYY → 0.46 NYM 으로 승자째 뒤집혔다.
    #    DB 를 **뒤에** 붙여도 DB 가 답을 정하면 순서를 바꾼 것이 아니다.
    if _order_v2 and parsed is not None:
        # 🔴 카드가 읽을 **조사 원문**을 그대로 싣는다. 카드가 자료를 다시
        #    모으면 그것이 사본이고, 두 곳이 다른 것을 보게 된다.
        jg["order_v2"] = {"갈림길목록": _pre.get("갈림길") or [],
                          "자료": (_reinf or {}).get("자료") or [],
                          "질문": (_reinf or {}).get("질문") or [],
                          "출처": (_reinf or {}).get("출처") or {}}
        if not apply_winner(jg, parsed):
            jg["form_unavailable"] = True
            jg["order_v2"]["탈락"] = "승자가 이 경기의 팀이 아니다"
            if final:
                await release_final(redis, jg, date)
            return None
        jg["final_verdict"] = final
        jg["judge_stage"] = "final" if final else "prelim"
        await persist_matchup_record(redis, jg, date)
        logger.info("[order] game=%s 승자 %s (갈림길 %d · 조사 %d건 %s)",
                    jg.get("game_id"), jg.get("winner"),
                    len(jg["order_v2"]["갈림길목록"]),
                    len(jg["order_v2"]["자료"]), jg["order_v2"]["출처"])
        return parsed
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
