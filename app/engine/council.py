"""[변수 평의회 2026-09-06] 상황 변수를 심의해 **판정의 재료**로 만든다.

🔴 **재판정이 아니다.** 심의는 판정 **앞**에 선다. 자료1~11 과 같은 줄에서
   한 상에 올라가고, 판정은 그 전부를 보고 **한 번** 결론을 낸다.
   그래서 "원판정 63% → 최종 64%" 같은 이동도, 이동 상한도, 잡음 판별도
   없다 — 움직일 원판정이 애초에 없다.
   (사용자 지시 2026-09-06: "최종 숫자를 내는 게 아니라 우리가 모은 데이터·
    변수·딥서치를 한 흐름으로 해서 최종 결론을 AI 가 내는 것. 수치는 그냥
    확률이잖아.")

🔴 **%p 를 만들지 않는다.** 심의가 만드는 것은 **사실**이다 —
   "은퇴 선수가 오늘 선발 출전한다" 처럼. 그 사실을 판정이 읽고 결론을 낸다.
   심의가 숫자를 붙이면 그건 다시 지어낸 계수다.

⚠️ 발동은 **상황 태그가 수집된 경기만**이고 슬레이트당 상한이 있다.
   판정 앞에 서므로 시간 예산이 곧 발송 마감선이다.

조사(ⓐ)는 퍼플렉시티가 주전이고, 못 쓰면 무료 사슬로 **축소 조사**한다 —
수집된 기사 제목만 보고 실마리를 뽑는다. 어느 경로였는지 로그에 남는다.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

CAP_KEY = "council:calls:{date}"
ONCE_KEY = "council:done:{sport}:{game_id}:{date}"
#: 🔴 [2026-09-06] **심의록을 저장한다.** 종전에는 `jg["council"]` 메모리에만
#   새겼다. 그래서 분석 캐시가 재생성되면 심의록은 날아가고 `council:done`
#   플래그만 남아, 그 뒤 전부 "이미 심의함 — 생략"으로 반환됐다 —
#   **되살릴 경로가 없었다** (실측 2026-09-06 15:34: KBO 4경기·NPB 2경기의
#   심의록이 통째로 사라졌고, 니혼햄 카드의 サンスポ 근거도 함께 잃었다).
#   같은 날 아침 최종 판정 락에서 고친 것과 같은 결함이다 —
#   **표식과 결과를 따로 두면, 결과가 유실될 때 표식이 복구를 막는다.**
REC_KEY = "council:rec:{sport}:{game_id}:{date}"
TTL = 26 * 3600

#: 🔴 [2026-09-06] 심의·조사는 **절대 유료 판정 경로를 타지 않는다.**
#   종전에는 `role="matchup"` 으로 불러서 `JUDGE_PROVIDER=anthropic` 일 때
#   심의와 조사 폴백까지 Fable 로 갔다 — 경기당 유료 3콜이었다(실측 2026-09-06).
#   `judge_route.chain()` 은 `matchup` 역할에만 유료를 허용하므로, 다른 이름을
#   쓰는 것만으로 무료가 보장된다.
COUNCIL_ROLE = "council"

SRC_PPLX = "perplexity"
SRC_FREE = "free_chain"
SRC_NONE = "none"

#: 조사 질문. **"없으면 없다고 답하라"** 가 이 프롬프트의 핵심이다 —
#  실마리를 못 찾았을 때 지어내면 심의 전체가 오염된다.
INVESTIGATE = """당신은 스포츠 경기 조사원이다. 아래 상황이 오늘 경기에
실제로 어떻게 작용하는지, **수집된 기사에서 확인되는 것만** 찾아라.

경기: {away} @ {home} ({league}, {date})
상황: {situation}

수집된 기사 제목:
{headlines}

찾을 것 (기사에서 확인되는 것만):
① 라인업·기용 변화 — 그 선수가 오늘 선발인가, 빠지는가, 대타인가
② 과거 유사 사례 언급 — 기사가 비슷한 상황의 전례를 말하는가
③ 현장 분위기 서술 — 감독·선수 코멘트, 구단 조치

🔴 기사에 없으면 **"없음"** 이 답이다. 추측·일반론·네가 아는 지식을 쓰지 마라.
🔴 요약하지 마라. 확인된 사실만 짧게 적어라.

JSON 만 출력한다:
{{"라인업변화": "확인된 사실 또는 없음",
  "유사사례": "확인된 사실 또는 없음",
  "현장분위기": "확인된 사실 또는 없음",
  "인용": ["근거가 된 기사 제목", "..."]}}"""

#: 심의 3문. 검사역 모델(무료)이 답한다. **%p 를 묻지 않는다.**
DELIBERATE = """당신은 야구 판정의 검사역이다. 아래 상황 변수가 오늘 경기에
작용하는 **기전**을 판단하라. 확률이나 %p 를 말하지 마라 — 그건 판정가의 몫이다.

경기: {away} @ {home}
상황: {situation}
조사 결과: {findings}

세 문항에 답하라:
① 기전 — 이 상황이 경기력에 작용한다면 **무엇을 통해서인가**
   (라인업 변화 / 동기 / 어수선함 / 없음)
② 방향 — 어느 팀에 유리한가 (홈 / 원정 / 불명)
③ 확실성 — 조사 결과가 이 판단을 뒷받침하는가 (뒷받침 / 약함 / 없음)

🔴 **"불명"으로 답해도 된다.** 단 왜 불명인지 한 줄을 반드시 적어라.
   근거 없이 방향을 정하는 것보다 불명이 정직하다.

JSON 만 출력한다:
{{"기전": "라인업변화|동기|어수선함|없음",
  "방향": "홈|원정|불명",
  "확실성": "뒷받침|약함|없음",
  "사유": "1~2문장. 왜 그렇게 읽었는지. 불명이면 왜 불명인지."}}"""


def _cfg():
    from app.config import get_settings

    return get_settings()


def targets(games: list[dict], settings=None) -> list[dict]:
    """심의 대상 — **상황 태그가 수집된 경기만.**

    ⚠️ "상황판정이 무관인 경기"가 아니다. 그건 판정 뒤에나 알 수 있는데,
       심의는 판정 **앞**에 서기 때문이다.
    """
    s = settings or _cfg()
    out = []
    for jg in games or []:
        tags = jg.get("situation_tags") or {}
        if sum(len(v or []) for v in tags.values()):
            out.append(jg)
    cap = int(s.council_slate_cap)
    if len(out) > cap:
        logger.warning("[council] 대상 %d경기 — 상한 %d로 자른다 "
                       "(나머지는 심의 없이 간다)", len(out), cap)
        out = out[:cap]
    return out


def _headlines(jg: dict, limit: int = 12) -> str:
    rows = []
    for side in ("home", "away"):
        for it in ((jg.get("research") or {}).get(f"{side}_news") or [])[:limit]:
            t = str((it or {}).get("title") or "").strip()
            if t:
                rows.append(f"- {t}")
    return "\n".join(rows[:limit]) or "(없음)"


def _situation_text(jg: dict) -> str:
    from app.engine.situation import as_lines

    lines = []
    for side, rows in (jg.get("situation_tags") or {}).items():
        for ln in as_lines(rows):
            lines.append(f"[{side}] {ln}")
    return "\n".join(lines) or "(없음)"


async def _cap_ok(redis, date: str) -> bool:
    """일일 캡. 셀 수 없으면 **부르지 않는다** — 캡 없는 AI 호출을 만들지 않는다."""
    if redis is None:
        logger.info("[council] Redis 없음 — 캡을 셀 수 없어 생략한다")
        return False
    cap = int(_cfg().council_daily_cap)
    try:
        n = int(await redis.get(CAP_KEY.format(date=date)) or 0)
    except Exception as exc:
        logger.warning("[council] 캡 조회 실패 — 생략: %s", exc)
        return False
    if n >= cap:
        logger.warning("[council] 일일 캡 도달 %d/%d", n, cap)
        return False
    return True


async def load_record(redis, sport: str, gid, date: str) -> dict | None:
    """저장된 심의록. 캐시가 재생성돼도 여기서 되살린다."""
    if redis is None:
        return None
    try:
        raw = await redis.get(REC_KEY.format(sport=sport, game_id=gid, date=date))
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("[council] 심의록 조회 실패 game=%s: %s", gid, exc)
        return None


async def _save_record(redis, sport: str, gid, date: str, rec: dict) -> None:
    if redis is None:
        return
    try:
        await redis.set(REC_KEY.format(sport=sport, game_id=gid, date=date),
                        json.dumps(rec, ensure_ascii=False, default=str), ex=TTL)
    except Exception as exc:
        logger.warning("[council] 심의록 저장 실패 game=%s: %s", gid, exc)


async def _once_ok(redis, sport: str, gid, date: str) -> bool:
    if redis is None:
        return False
    try:
        return bool(await redis.set(ONCE_KEY.format(sport=sport, game_id=gid,
                                                    date=date),
                                    "1", ex=TTL, nx=True))
    except Exception as exc:
        logger.warning("[council] 1회 표식 실패 — 생략: %s", exc)
        return False


async def _release_once(redis, sport: str, gid, date: str) -> None:
    """1회 표식 반납. 조사가 실패했으면 권한만 태운 것이다."""
    if redis is None:
        return
    try:
        await redis.delete(ONCE_KEY.format(sport=sport, game_id=gid, date=date))
    except Exception as exc:
        logger.warning("[council] 표식 반납 실패 game=%s: %s", gid, exc)


async def _note(redis, date: str) -> None:
    if redis is None:
        return
    try:
        k = CAP_KEY.format(date=date)
        await redis.incr(k)
        await redis.expire(k, TTL)
    except Exception as exc:
        logger.debug("[council] 카운터 기록 실패: %s", exc)


async def investigate(jg: dict) -> tuple[dict | None, str]:
    """ⓐ 조사 — 퍼플렉시티 주전, 실패하면 무료 사슬로 축소 조사.

    반환 `(결과 | None, 사용한 경로)`. **실패는 None 이고 판정을 막지 않는다.**
    """
    prompt = INVESTIGATE.format(
        away=jg.get("away"), home=jg.get("home"),
        league=(jg.get("league") or jg.get("sport") or "").upper(),
        date=jg.get("starts_at_kst") or "",
        situation=_situation_text(jg), headlines=_headlines(jg))

    # 🔴 [2026-09-22 사용자 지시] **퍼플렉시티는 검색에 쓰지 않는다.**
    #    종전 주석은 "주전 — 퍼플렉시티" 였다. 지금은 `DISABLED_PROVIDERS`
    #    에 들어 있어 `ask_json` 이 조용히 None 을 주고 **아래 무료 사슬이
    #    주전**이다. 요청은 나가지 않는다(실측 2026-09-22: 오늘 0콜).
    #    ⚠️ 코드를 지우지 않는다 — 스위치 한 줄로 되돌린다.
    try:
        from app.research.perplexity import ask_json

        got = await ask_json(prompt)
        if got:
            return got, SRC_PPLX
    except Exception as exc:
        logger.info("[council] 퍼플렉시티 조사 실패 — 무료 사슬로 축소 조사: %s",
                    str(exc)[:120])

    # 폴백 — 무료 사슬. 수집된 제목만 보고 실마리를 뽑는다(검색은 못 한다).
    try:
        from app.engine.team_form import complete_json

        txt = await complete_json(prompt, model="", max_tokens=800,
                                  role=COUNCIL_ROLE)
        from app.engine.matchup import parse_json_object

        got = parse_json_object(txt or "")
        if isinstance(got, dict):
            return got, SRC_FREE
    except Exception as exc:
        logger.warning("[council] 축소 조사도 실패 — 심의 없이 간다: %s",
                       str(exc)[:120])
    return None, SRC_NONE


async def deliberate(jg: dict, findings: dict) -> dict | None:
    """ⓑ 심의 — 검사역 모델(무료). **%p 를 묻지 않는다.**"""
    from app.engine.matchup import parse_json_object
    from app.engine.team_form import complete_json

    prompt = DELIBERATE.format(
        away=jg.get("away"), home=jg.get("home"),
        situation=_situation_text(jg),
        findings=json.dumps(findings or {}, ensure_ascii=False))
    try:
        txt = await complete_json(prompt, model="", max_tokens=600,
                                  role=COUNCIL_ROLE)
    except Exception as exc:
        logger.warning("[council] 심의 실패 — 조사 결과만 넘긴다: %s",
                       str(exc)[:120])
        return None
    got = parse_json_object(txt or "")
    return got if isinstance(got, dict) else None


async def run(jg: dict, date: str, redis=None) -> dict | None:
    """경기 1건 심의. 판정 **앞**에서 부른다. 실패해도 판정은 계속된다.

    성공하면 `jg["council"]` 에 심의록을 새기고 그것을 돌려준다.
    """
    if not _cfg().council_enabled:
        return None
    tags = jg.get("situation_tags") or {}
    if not sum(len(v or []) for v in tags.values()):
        return None
    sport, gid = (jg.get("sport") or "").lower(), jg.get("game_id")
    # 🔴 저장된 심의록이 있으면 **되살린다.** 캐시가 재생성돼 jg 에서 사라져도
    #    심의를 다시 하지 않고 그대로 붙인다 — 유료 조사를 두 번 하지 않으면서
    #    카드가 심의록을 잃지도 않는다.
    saved = await load_record(redis, sport, gid, date)
    if saved:
        jg["council"] = saved
        logger.info("[council] game=%s 저장된 심의록 복원", gid)
        return saved
    if not await _cap_ok(redis, date):
        return None
    if not await _once_ok(redis, sport, gid, date):
        # 표식은 있는데 심의록이 없다 — 그 심의는 실패했거나 중간에 끊겼다.
        logger.info("[council] game=%s 이미 심의함(심의록 없음) — 생략", gid)
        return None

    findings, src = await investigate(jg)
    await _note(redis, date)
    if findings is None:
        # 🔴 조사가 실패했으면 **1회 표식을 반납한다.** 안 그러면 그 경기는
        #    오늘 다시 심의할 길이 없다(최종 판정 락과 같은 이유).
        await _release_once(redis, sport, gid, date)
        logger.warning("[council] game=%s 조사 실패 — 심의록 없이 간다 "
                       "(표식 반납, 다음 회차 재시도)", gid)
        return None
    verdict = await deliberate(jg, findings)
    rec = {"조사": findings, "조사경로": src, "심의": verdict or {},
           "상황": _situation_text(jg)}
    jg["council"] = rec
    await _save_record(redis, sport, gid, date, rec)
    logger.info("[council] game=%s 심의 완료 (조사=%s 기전=%s 방향=%s 확실성=%s)",
                gid, src, (verdict or {}).get("기전"),
                (verdict or {}).get("방향"), (verdict or {}).get("확실성"))
    return rec


def payload(jg: dict) -> dict:
    """판정 프롬프트에 실을 [상황·심의] 블록. 없으면 빈 dict.

    ⚠️ **자료2 확장이다.** 프롬프트 구조를 바꾸지 않는다 — 자료2 JSON 안에
       한 항목으로 들어간다.
    """
    rec = jg.get("council") or {}
    if not rec:
        return {}
    d = rec.get("심의") or {}
    return {"상황·심의": {
        "기전": d.get("기전"), "방향": d.get("방향"),
        "확실성": d.get("확실성"), "사유": d.get("사유"),
        "조사": rec.get("조사"), "조사경로": rec.get("조사경로")}}


def card_line(jg: dict) -> str:
    """카드 한 줄. 심의가 없거나 알맹이가 없으면 빈 줄."""
    rec = jg.get("council") or {}
    d = (rec.get("심의") or {})
    if not d:
        return ""
    why = str(d.get("사유") or "").strip()
    if d.get("방향") == "불명":
        return f"심의 [상황·심의] 심의 후에도 불명 — {why}" if why else ""
    return (f"심의 [상황·심의] 기전 {d.get('기전')} · {d.get('방향')} 방향 "
            f"({d.get('확실성')}) — {why}").strip()
