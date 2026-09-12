"""[무료 전환] 판정·폼 라우팅 — provider 하나만 바꾼다.

🔴 **프롬프트·게이트·클립·트리거는 건드리지 않는다.** 바꾸는 것은
   "어느 모델에 보내는가" 뿐이다.

폴백 사슬: 무료 주전 → 무료 후보 → (둘 다 죽으면) Anthropic.
⚠️ Anthropic 은 **하루 `anthropic_daily_cap` 콜 하드캡** + `W-LLM-PAID` 경보다.
   비상용이 일상용으로 새는 것을 캡이 막는다.
⚠️ Anthropic 경로를 **삭제하지 않았다** — `JUDGE_PROVIDER=anthropic` 한 줄로
   되돌아온다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PAID_KEY = "llm:anthropic:calls:{date}"

#: 🔴 **유료가 허용되는 유일한 역할.** 다른 역할은 어떤 설정에서도 무료다.
#   문자열을 호출부마다 적지 않는다 — 여기가 원본이다.
MATCHUP_ROLE = "matchup"
#: 🔴 [2026-09-06 사용자 지시] **1차 예비 판정.** 픽은 두 장이다 —
#   T-30 잠정 카드와 라인업 확정 뒤의 최종 카드. 앞의 것은 **어떤 설정에서도
#   무료**로 간다. 종전에는 역할이 하나라 `JUDGE_PROVIDER=anthropic` 하나가
#   경기당 3~5회를 전부 유료로 보냈다 (실측 2026-09-06 11:15~11:27, 12분에 11콜).
PRELIM_ROLE = "matchup_prelim"
#: 판정 역할 전체. 같은 프롬프트·같은 자료를 쓰고 **모델만 다르다.**
JUDGE_ROLES = (MATCHUP_ROLE, PRELIM_ROLE)

#: [ORD-17 2026-09-12 사용자 지시] **2차 검증 역할.** 판정 사슬과 분리한다.
#   "1차는 제미니로 하고 2차를 안트로픽을 추가하자…2차검증을 하는거다."
#   🔴 `chain()` 의 기존 분기를 건드리지 않는다. 실측 2026-09-12:
#      `JUDGE_PROVIDER=gemini` 라 `chain(matchup)` 에 Anthropic 이 없다.
#      1차 사슬을 만지면 판정 전체가 흔들린다 — 2차만 켜고 끌 수 있어야 한다.
#   ⚠️ 이 역할은 `chain()` 을 타지 않는다. `verify` 가 `verify_model` 로 직접 부른다.
VERIFY_ROLE = "verify"


def _cfg():
    from app.config import get_settings

    return get_settings()


#: OpenRouter 는 같은 모델 이름으로 **유료·무료 두 변형**을 판다. 무료판만
#  `:free` 로 끝난다 — 접미사가 없으면 과금된다(실측 2026-09-04).
_SUFFIX_REQUIRED = {"openrouter"}

#: 🔴 **비용이 0 임이 확인된 provider 만 여기 있다.**
#   · ollama = 로컬 실행 · mock = 호출 자체가 없음
#   · groq · nvidia NIM = 계정이 무료 티어라 모델 이름으로 갈리지 않는다
#   ⚠️ 모델 목록이 아니라 **provider 규칙**이다. 모델 이름은 적지 않는다.
FREE_PROVIDERS = {"ollama", "mock", "groq", "nvidia"}

#: 유료로 보는 provider — `snapshot()` 이 훑을 후보다. **판정 근거가 아니다**
#  (판정은 `is_paid_provider` 의 규칙이 한다). 여기 없는 이름도 규칙상
#  유료면 유료로 취급된다.
PAID_PROVIDER_HINTS = ("gemini", "xai", "anthropic", "deepseek", "openrouter")


def is_paid_provider(provider: str) -> bool:
    """이 provider 는 **돈이 드는가.** 모르면 유료로 본다.

    🔴 [BUD-1 2026-09-11] **이 방향이 원래 계약이었다.** 종전 `is_free` 의
       독스트링은 "확실하지 않으면 False(=무료 아님)"라고 적어 놓고, 구현은
       그 반대로 **모르는 provider 를 전부 무료로 통과**시켰다. 그래서
       2026-09-11 유료 전환 뒤 gemini·xai 가 "무료 후보"로 사슬에 앉았고,
       **상한이 걸리는 경로가 Anthropic 하나뿐**이 됐다.
    """
    return (provider or "").strip().lower() not in FREE_PROVIDERS


def is_free(provider: str, model: str) -> bool:
    """이 후보가 **돈이 안 드는가.** 확실하지 않으면 False 다.

    ⚠️ 사본 금지: 무료 모델 목록을 여기 적지 않는다. 규칙만 둔다 —
       목록은 제공자가 바꾸고, 우리 사본은 따라가지 않는다.
    """
    prov = (provider or "").strip().lower()
    if prov in _SUFFIX_REQUIRED:
        return (model or "").strip().endswith(":free")
    return not is_paid_provider(prov)


def _anthropic_gone() -> bool:
    """Anthropic 잔액이 소진됐는가. **읽기만 한다** — 판정의 원본은 provider 다."""
    try:
        from app.llm.provider import _is_exhausted

        return bool(_is_exhausted("anthropic"))
    except Exception as exc:      # 모르면 "안 끊겼다" — 대체를 함부로 켜지 않는다
        logger.debug("[judge-route] 소진 여부 조회 실패: %s", exc)
        return False


def chain(role: str) -> list[tuple[str, str]]:
    """`[(provider, model), ...]`. 첫 항목이 주전이다.

    ⚠️ 모델은 config 가 원본 — 여기 이름을 적지 않는다.
    """
    s = _cfg()
    prov = (s.judge_provider or "anthropic").lower()
    # 🔴 [2026-09-06 사용자 지시] **Anthropic 은 최종 판정에서만 쓴다.**
    #    "안트로픽 폴백하는 거 전부 삭제하고 맨 나중에 최종 판정만 하게."
    #    종전에는 `JUDGE_PROVIDER=anthropic` 이 역할을 안 가려 **팀 폼까지**
    #    유료로 끌고 갔다 — 실측 2026-09-06 11:15~11:27, 12분에 11콜이 나갔다
    #    (경기당 Fable 2회 + haiku 2회). 그게 자금 누수였다.
    if prov == "anthropic" and role == MATCHUP_ROLE:
        # 🔴 [2026-09-07 사용자 지시] **소진이면 grok 으로 대체한다.**
        #    실측 400: "Your credit balance is too low to access the
        #    Anthropic API" (req_011CeopbocAgP9C1UneLpve6). 종전에는 이때
        #    최종 판정이 응답 0자로 실패하고 그 경기는 카드가 안 나갔다.
        #    ⚠️ **"한 판정은 한 모델이 낸다"를 깨지 않는다.** 호출 중에
        #       갈아타는 것이 아니라, 부르기 **전에** 소진을 확인해 사슬
        #       자체를 바꾼다. 그 판정은 처음부터 끝까지 grok 하나가 낸다.
        #    ⚠️ 소진 판정의 원본은 `provider._is_exhausted` 다 — 여기서
        #       400 문자열을 다시 해석하지 않는다(사본 금지).
        if _anthropic_gone() and s.xai_api_key:
            logger.warning("[judge-route] Anthropic 소진 — 최종 판정을 "
                           "grok(%s) 로 대체한다", s.grok_model)
            return [("xai", s.grok_model)]
        return [("anthropic", s.matchup_model)]
    # 🔴 무료 후보를 **여럿** 둔다. Nemotron 이 오디션에서 6건 중 1건을
    #    `503 Service temporarily overloaded` 로 놓쳤다 — 무료 인프라는
    #    가끔 밀린다. 하나만 두면 그 경기는 카드가 못 나간다.
    #    형식: "provider/model,provider/model" (앞이 주전)
    #: 예비 판정도 **판정용** 무료 모델을 쓴다. 폼 모델이 아니다 —
    #  같은 프롬프트를 받으므로 폼 사슬로 보내면 재료 대신 다른 답이 온다.
    raw = (s.judge_chain if role in JUDGE_ROLES else s.form_chain)
    out: list[tuple[str, str]] = []
    for item in (raw or "").split(","):
        item = item.strip()
        if not item or "/" not in item:
            continue
        prv, _, mdl = item.partition("/")
        # ⚠️ 모델 ID 자체에 `/` 가 있다(예: nvidia/nemotron-...). 첫 `/` 만 쪼갠다.
        prv, mdl = prv.strip(), mdl.strip()
        if not is_free(prv, mdl):
            # 🔴 "무료 전환"이라 해놓고 유료 모델이 사슬에 앉아 있었다.
            #    실측 2026-09-04: `openrouter/deepseek/deepseek-r1` 은 무료판이
            #    아니어서 키 사용액이 $0 이 아니었다(usage 0.0002594).
            # 🔴 [BUD-1 2026-09-11] 그때는 **무료 전용 정책**이라 빼는 것이
            #    맞았다. 2026-09-11 유료 전환으로 정책이 바뀌었다 — 이제
            #    유료 후보를 **빼지 않고 태우되, 토큰 상한이 잡는다.**
            #    ⚠️ 여기서 빼버리면 지금 운영 사슬(gemini,xai)이 통째로
            #       비어 **전 슬레이트 판정이 0건**이 된다.
            #    ⚠️ 무료 전용으로 되돌리는 길은 열어 둔다 — 설정 한 줄이다.
            if not _cfg().paid_llm_allowed:
                logger.warning("[judge-route] 유료 후보 제외 %s/%s — "
                               "무료 전용 모드다(PAID_LLM_ALLOWED=0)", prv, mdl)
                continue
            logger.info("[judge-route] 💸 유료 후보 %s/%s — 일일 토큰 상한이 "
                        "적용된다(token_budget)", prv, mdl)
        out.append((prv, mdl))
    if not out and raw:
        # ⚠️ provider 를 못 쪼갠 한 덩어리 문자열. **anthropic 은 넣지 않는다.**
        if prov != "anthropic":
            out.append((prov, raw))
    # 🔴 [2026-09-04] **비상 꼬리를 붙이지 않는다.** 사용자 지시: 무료 사슬로
    #    진행한다. 종전에는 사슬 끝에 Anthropic 을 두고 "캡이 지킨다"고 했는데,
    #    잔액이 0 이면 캡은 아무것도 지키지 못한다 — 호출은 400 을 받고,
    #    그 400 이 `ApiQuotaError` → `trip_credit` 으로 번져 **종목 전체가
    #    멈췄다** (실측 2026-09-04 16:37, NPB 판정 0건 · 카드 0장).
    # 🔴 [2026-09-06 사용자 지시] **유료 폴백을 삭제했다.**
    #    종전에는 무료 후보가 없으면 Anthropic 으로 되돌아갔다. 그 경로가
    #    판정 아닌 역할(폼·심의)까지 유료로 끌고 갔다.
    #    이제 무료 후보가 없으면 **빈 목록**이다 — 호출부가 재료 없이 간다.
    #    조용하지 않다: error 로그 한 줄이 남고 일일 요약 성공률에 잡힌다.
    if not out:
        logger.error("[judge-route] role=%s 후보가 하나도 없다 — "
                     "유료로 되돌아가지 않는다. %s_CHAIN 을 확인하라",
                     role, "JUDGE" if role in JUDGE_ROLES else "FORM")
    return out


async def paid_calls_today(redis) -> int:
    from app.pipeline import today_kst

    if redis is None:
        return 0
    try:
        return int(await redis.get(PAID_KEY.format(date=today_kst())) or 0)
    except Exception as exc:
        logger.debug("[judge-route] 유료 카운터 조회 실패: %s", exc)
        return 0


#: 캡의 몇 %를 넘으면 경보할지. 주전이 유료일 때는 **잔량**이 신호다.
#  ⚠️ `token_budget` 이 같은 값을 읽는다 — 두 캡(콜·토큰)이 같은 비율로 운다.
#     사본을 만들지 않기 위해 공개 이름이다.
PAID_WARN_RATIO = 0.8


async def note_paid_call(redis, role: str) -> int:
    """Anthropic 1콜 기록. 반환 오늘 누적.

    🔴 [2026-09-06] 경보 조건이 바뀌었다. 이 경보는 Anthropic 이 **비상용**
       이던 시절에 만들었다 — 불리면 곧 "무료가 실패했다"는 뜻이었다.
       사용자 지시로 **Fable 이 주전**이 된 지금은 유료 호출이 정상 동작이고,
       종전 조건이면 경기마다(하루 26회+) 울린다.
       그 상태를 만든 적이 있다 — 워치독 오탐 4건이 15분마다 울려 **진짜 고장
       하나가 묻힐 뻔했다**(실사고 2026-09-02).

       이제 두 갈래로 나눈다:
         · 유료가 **폴백**일 때 → 종전대로 1콜부터 경보(무료가 죽었다는 신호)
         · 유료가 **주전**일 때 → 캡의 80%를 넘을 때만 경보(잔량이 신호)
    """
    from app.pipeline import today_kst

    if redis is None:
        return 0
    key = PAID_KEY.format(date=today_kst())
    try:
        n = int(await redis.incr(key))
        await redis.expire(key, 30 * 3600)
    except Exception as exc:
        logger.debug("[judge-route] 유료 카운터 기록 실패: %s", exc)
        return 0
    cap = int(_cfg().anthropic_daily_cap)
    primary = (_cfg().judge_provider or "").lower() == "anthropic"
    logger.info("[judge-route] Anthropic %s %d/%d (role=%s)",
                "주전" if primary else "💸 폴백", n, cap, role)
    if primary and n < max(1, int(cap * PAID_WARN_RATIO)):
        return n        # 주전이면 잔량이 넉넉할 때 조용히 간다
    detail = (f"유료 주전 사용량 {n}/{cap}회 (role={role}) — 캡에 근접했다. "
              f"넘으면 그 뒤 경기는 판정 없이 간다"
              if primary else
              f"Anthropic 폴백 {n}/{cap}회 (role={role}) — 무료 provider 가 실패하고 있다")
    try:
        from app.alerts import watchdog as _wd

        await _wd("W-LLM-PAID", detail, target=role)
    except Exception as exc:
        logger.debug("[judge-route] 경보 실패: %s", exc)
    return n


async def paid_allowed(redis) -> bool:
    """캡을 넘었으면 **부르지 않는다.** 넘은 채로 계속 부르면 캡이 무의미하다."""
    n = await paid_calls_today(redis)
    cap = int(_cfg().anthropic_daily_cap)
    if n >= cap:
        logger.error("[judge-route] 🔴 Anthropic 일일 캡 %d 도달 — 호출 차단", cap)
        return False
    return True
