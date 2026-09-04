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


def _cfg():
    from app.config import get_settings

    return get_settings()


def chain(role: str) -> list[tuple[str, str]]:
    """`[(provider, model), ...]`. 첫 항목이 주전이다.

    ⚠️ 모델은 config 가 원본 — 여기 이름을 적지 않는다.
    """
    s = _cfg()
    prov = (s.judge_provider or "anthropic").lower()
    if prov == "anthropic":
        return [("anthropic", s.matchup_model if role == "matchup"
                 else s.team_form_model)]
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
        out.append((prv.strip(), mdl.strip()))
    if not out and raw:
        out.append((prov, raw))
    # 비상 복귀는 사슬 끝에만 — 캡이 지킨다.
    out.append(("anthropic", s.matchup_model if role == "matchup"
                else s.team_form_model))
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


async def note_paid_call(redis, role: str) -> int:
    """Anthropic 1콜 기록 + 캡 근접 시 경보. 반환 오늘 누적."""
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
    logger.warning("[judge-route] 💸 Anthropic 폴백 %d/%d (role=%s) — "
                   "무료 경로가 실패했다", n, cap, role)
    try:
        from app.alerts import watchdog as _wd

        await _wd("W-LLM-PAID", f"Anthropic 폴백 {n}/{cap}회 (role={role}) — "
                                f"무료 provider 가 실패하고 있다", target=role)
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
