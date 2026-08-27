"""[#73] provider 사용량·장애 이력.

**왜 기록하는가.** 지금 폴백 체인은 Gemini → Groq → Anthropic 순인데, 그 순서가
옳다는 근거가 없다. 어느 provider가 실제로 가장 안정적인지는 **며칠 치 장애
이력을 봐야** 안다. 순서를 바꾸기 전에 이 표를 먼저 본다.

기록하는 것은 두 가지뿐이다.
  ① 호출 수 — provider별 성공/실패 (`llm_calls:{date}`)
  ② 장애 이력 — 언제 어느 provider가 왜 죽었는지 (`llm_outage:{date}`)

⚠️ **성공률로 순위를 매기지 마라.** 1순위 provider가 대부분의 호출을 받으므로
   표본이 비대칭이다. 이 표는 "언제 무엇이 죽었나"를 보는 것이지 우열표가 아니다.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

TTL = 14 * 24 * 3600        # 2주 — 폴백 순서를 재검토할 최소 관측 기간
MAX_OUTAGES = 200           # 하루치 상한. 넘치면 오래된 것부터 밀어낸다


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


async def record_call(redis, provider: str, role: str, ok: bool) -> None:
    """호출 1건. redis가 없으면 조용히 넘어간다(키 없이도 동작해야 한다)."""
    if redis is None:
        return
    try:
        key = f"llm_calls:{_today()}"
        await redis.hincrby(key, f"{provider}:{'ok' if ok else 'fail'}", 1)
        await redis.expire(key, TTL)
    except Exception as exc:                 # 계측이 본체를 죽이지 않는다
        logger.debug("[llm] 사용량 기록 실패: %s", exc)


async def record_outage(redis, provider: str, role: str, kind: str,
                        detail: str = "") -> None:
    """장애 1건. kind는 `quota`·`rate_limit`·`auth`·`budget`·`other`."""
    if redis is None:
        return
    try:
        key = f"llm_outage:{_today()}"
        await redis.lpush(key, json.dumps(
            {"at": datetime.now(UTC).isoformat(timespec="seconds"),
             "provider": provider, "role": role, "kind": kind,
             "detail": detail[:200]}, ensure_ascii=False))
        await redis.ltrim(key, 0, MAX_OUTAGES - 1)
        await redis.expire(key, TTL)
    except Exception as exc:
        logger.debug("[llm] 장애 기록 실패: %s", exc)


async def summary(redis, days: int = 3) -> dict:
    """최근 며칠 치 사용량·장애를 모은다."""
    if redis is None:
        return {"calls": {}, "outages": []}
    from datetime import timedelta

    calls: dict[str, dict[str, int]] = {}
    outages: list[dict] = []
    now = datetime.now(UTC)
    for i in range(max(1, days)):
        day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            for field, n in (await redis.hgetall(f"llm_calls:{day}") or {}).items():
                prov, _, kind = field.partition(":")
                calls.setdefault(prov, {"ok": 0, "fail": 0})[kind] = \
                    calls.setdefault(prov, {"ok": 0, "fail": 0}).get(kind, 0) + int(n)
            for raw in (await redis.lrange(f"llm_outage:{day}", 0, 20) or []):
                outages.append(json.loads(raw))
        except Exception as exc:
            logger.debug("[llm] 집계 실패 %s: %s", day, exc)
    outages.sort(key=lambda o: o.get("at", ""), reverse=True)
    return {"calls": calls, "outages": outages}


_KIND_KR = {"quota": "크레딧 소진", "rate_limit": "레이트리밋", "auth": "키 오류",
            "budget": "토큰 예산 부족", "other": "기타"}


def format_summary(data: dict, show_outages: int = 3) -> list[str]:
    """/health 줄. **잔여 크레딧은 쓰지 않는다** — 벤더가 알려주지 않는 값을
    추정해서 보여주면 그 추정이 근거로 쓰인다. 아는 것만 쓴다."""
    calls, outages = data.get("calls") or {}, data.get("outages") or []
    if not calls and not outages:
        return ["🤖 LLM: 기록 없음"]
    lines = []
    if calls:
        parts = []
        for prov, c in sorted(calls.items()):
            ok, fail = c.get("ok", 0), c.get("fail", 0)
            parts.append(f"{prov} {ok}건" + (f"(실패 {fail})" if fail else ""))
        lines.append("🤖 LLM 3일 사용: " + " · ".join(parts))
    for o in outages[:show_outages]:
        when = (o.get("at") or "")[5:16].replace("T", " ")
        lines.append(f"  ⚠️ {when} {o.get('provider')} — "
                     f"{_KIND_KR.get(o.get('kind'), o.get('kind'))} ({o.get('role')})")
    if len(outages) > show_outages:
        lines.append(f"  … 장애 {len(outages)}건 중 {show_outages}건 표시")
    return lines
