"""[BUD-1 2026-09-11] 유료 LLM 일일 **토큰** 상한 — 콜 수가 아니라 토큰을 센다.

🔴 **왜 필요한가.** 2026-09-11 유료 전면 전환(gemini 주전 · xai 폴백) 뒤,
   상한이 걸리는 경로는 `anthropic_daily_cap` 하나뿐이었다. 그 캡은
   Anthropic 만 보고, 지금 실제로 도는 gemini·xai 에는 **상한도 카운터도
   없었다.** 15경기 슬레이트 실측 122콜이고, 콜 하나의 크기가 역할마다
   10배 넘게 차이 난다(판정 프롬프트 15k자 vs 의도 해석 몇 줄) —
   그래서 축은 **콜이 아니라 토큰**이어야 한다.

⚠️ **토큰 수를 추정하지 않는다.** provider 응답의 `usage` 가 원본이다.
   글자 수 ÷ 4 같은 환산은 여기 없다 — 그건 숫자를 지어내는 것이다.
   usage 가 안 오면 **세지 않고 그 사실을 로그로 남긴다**(0 으로 덮지 않는다).

⚠️ **상한 기본값은 0 = 관측만이다.** 하루치 실측이 아직 없어서 숫자를 정할
   근거가 없다(CLAUDE.md 추측 금지). 값을 넣기 전까지 이 모듈은 **세고
   보고할 뿐 막지 않는다.** 그 상태가 로그에 그대로 드러난다 —
   "가드를 넣었다"고 조용히 말하지 않기 위해서다.

경보는 새 코드를 만들지 않고 `W-LLM-PAID` 를 쓴다. 라벨이 이미
"유료 판정이 일일 상한에 도달"이고 뜻이 정확히 같다(사본 금지).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: provider 별 일일 누적 토큰. 날짜가 키에 있어 자정에 자연히 갈린다.
KEY = "llm:tokens:{provider}:{date}"
#: 하루보다 조금 길게 — 자정 직후에도 어제 값을 볼 수 있다.
TTL_SEC = 30 * 3600


def _cfg():
    from app.config import get_settings

    return get_settings()


def cap_for(provider: str) -> int:
    """그 provider 의 일일 토큰 상한. **0 이면 관측만 하고 막지 않는다.**

    ⚠️ 원본은 config 하나다 — 숫자를 여기 적지 않는다.
    """
    del provider          # 지금은 provider 별로 가르지 않는다. 갈리면 여기서 갈린다.
    try:
        return max(0, int(_cfg().token_cap_daily))
    except Exception:
        return 0


def _today() -> str:
    from app.pipeline import today_kst

    return today_kst()


async def spent_today(redis, provider: str) -> int:
    """오늘 그 provider 가 쓴 토큰 누적. 모르면 0 — 모른다고 막지는 않는다."""
    if redis is None or not provider:
        return 0
    try:
        return int(await redis.get(KEY.format(provider=provider, date=_today())) or 0)
    except Exception as exc:
        logger.debug("[token-budget] 조회 실패 %s: %s", provider, exc)
        return 0


async def allowed(redis, provider: str) -> tuple[bool, str | None]:
    """지금 이 provider 를 불러도 되는가. `(가능한가, 사유)`.

    🔴 **넘은 채로 계속 부르면 상한이 무의미하다** — `judge_route.paid_allowed`
       와 같은 태도다.
    ⚠️ 상한이 0(미설정)이면 **언제나 통과**한다. 그 사실을 숨기지 않는다.
    """
    from app.llm.judge_route import is_paid_provider

    if not is_paid_provider(provider):
        return True, None
    cap = cap_for(provider)
    if cap <= 0:
        return True, None
    n = await spent_today(redis, provider)
    if n < cap:
        return True, None
    why = f"{provider} 일일 토큰 상한 {cap:,} 도달 (누적 {n:,})"
    logger.error("[token-budget] 🔴 %s — 호출 차단", why)
    return False, why


async def note_usage(redis, provider: str, *, role: str, model: str,
                     input_tokens, output_tokens) -> int:
    """유료 호출 1건의 토큰을 누적한다. 반환은 오늘 누적(모르면 0).

    ⚠️ **무료 provider 는 세지 않는다.** 상한의 목적이 지출이기 때문이다.
    ⚠️ usage 가 없으면(둘 다 None) 누적하지 않고 경고만 남긴다 —
       0 으로 덮으면 "안 썼다"와 "모른다"가 같아진다.
    """
    from app.llm.judge_route import PAID_WARN_RATIO, is_paid_provider

    if redis is None or not is_paid_provider(provider):
        return 0
    if input_tokens is None and output_tokens is None:
        logger.warning("[token-budget] %s/%s usage 없음 (role=%s) — "
                       "누적하지 못했다. 상한이 이만큼 헐거워진다",
                       provider, model, role)
        return 0
    used = int(input_tokens or 0) + int(output_tokens or 0)
    if used <= 0:
        return 0
    key = KEY.format(provider=provider, date=_today())
    try:
        n = int(await redis.incrby(key, used))
        await redis.expire(key, TTL_SEC)
    except Exception as exc:
        logger.debug("[token-budget] 기록 실패 %s: %s", provider, exc)
        return 0
    cap = cap_for(provider)
    logger.info("[token-budget] %s +%d = %d%s (role=%s model=%s)",
                provider, used, n, f"/{cap}" if cap > 0 else " (상한 미설정)",
                role, model)
    if cap > 0 and n >= max(1, int(cap * PAID_WARN_RATIO)):
        detail = (f"{provider} 토큰 {n:,}/{cap:,} — 상한에 근접했다. "
                  f"넘으면 그 뒤 경기는 판정 없이 간다 (role={role})")
        try:
            from app.alerts import watchdog as _wd

            await _wd("W-LLM-PAID", detail, target=provider)
        except Exception as exc:
            logger.debug("[token-budget] 경보 실패: %s", exc)
    return n


async def snapshot(redis) -> dict[str, int]:
    """오늘 provider 별 누적. 일일 요약·점검이 읽는다. 실패하면 빈 dict."""
    from app.llm.judge_route import PAID_PROVIDER_HINTS

    out: dict[str, int] = {}
    for p in PAID_PROVIDER_HINTS:
        n = await spent_today(redis, p)
        if n:
            out[p] = n
    return out
