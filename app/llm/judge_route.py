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


def _cfg():
    from app.config import get_settings

    return get_settings()


#: OpenRouter 는 같은 모델 이름으로 **유료·무료 두 변형**을 판다. 무료판만
#  `:free` 로 끝난다 — 접미사가 없으면 과금된다(실측 2026-09-04).
#  다른 제공자(nvidia NIM·groq)는 계정 자체가 무료 티어라 이름으로 갈리지 않는다.
_SUFFIX_REQUIRED = {"openrouter"}


def is_free(provider: str, model: str) -> bool:
    """이 후보가 **돈이 안 드는가.** 확실하지 않으면 False 다.

    ⚠️ 사본 금지: 무료 모델 목록을 여기 적지 않는다. 규칙만 둔다 —
       목록은 제공자가 바꾸고, 우리 사본은 따라가지 않는다.
    """
    if (provider or "").strip().lower() in _SUFFIX_REQUIRED:
        return (model or "").strip().endswith(":free")
    return True


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
        return [("anthropic", s.matchup_model)]
    # 🔴 무료 후보를 **여럿** 둔다. Nemotron 이 오디션에서 6건 중 1건을
    #    `503 Service temporarily overloaded` 로 놓쳤다 — 무료 인프라는
    #    가끔 밀린다. 하나만 두면 그 경기는 카드가 못 나간다.
    #    형식: "provider/model,provider/model" (앞이 주전)
    raw = (s.free_judge_model if role == "matchup" else s.free_form_model)
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
            #    조용히 지나가지 않는다 — 태우고, 사슬에서 뺀다.
            logger.warning("[judge-route] 유료 후보 제외 %s/%s — "
                           "무료 전환 중이다(:free 접미사 필요)", prv, mdl)
            continue
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
        logger.error("[judge-route] role=%s 무료 후보가 하나도 없다 — "
                     "유료로 되돌아가지 않는다. FREE_%s_MODEL 을 확인하라",
                     role, "JUDGE" if role == MATCHUP_ROLE else "FORM")
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
_PAID_WARN_RATIO = 0.8


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
    if primary and n < max(1, int(cap * _PAID_WARN_RATIO)):
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
