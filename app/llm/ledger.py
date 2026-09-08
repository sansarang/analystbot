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

from app.secrets_mask import mask_secrets

logger = logging.getLogger(__name__)

TTL = 14 * 24 * 3600        # 2주 — 폴백 순서를 재검토할 최소 관측 기간
MAX_OUTAGES = 200           # 하루치 상한. 넘치면 오래된 것부터 밀어낸다


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


LAST_OK_KEY = "llm_last_ok"      # provider → 마지막 성공 ISO 시각
BLACKOUT_KEY = "llm_blackout:{}"  # 그날 전 provider 전멸 횟수
# 하루에 이만큼 전멸하면 provider를 늘려야 한다는 신호다.
#  ⚠️ 실측으로 정한 값이 아니라 **운영 판단선**이다. 2주 치 장애 이력이 쌓이면
#     실제 전멸 빈도를 보고 교체한다.
BLACKOUT_WARN = 3


async def record_call(redis, provider: str, role: str, ok: bool) -> None:
    """호출 1건. redis가 없으면 조용히 넘어간다(키 없이도 동작해야 한다)."""
    if redis is None:
        return
    try:
        key = f"llm_calls:{_today()}"
        await redis.hincrby(key, f"{provider}:{'ok' if ok else 'fail'}", 1)
        await redis.expire(key, TTL)
        if ok:
            # 마지막 성공 시각 — "지금 이 provider가 살아 있나"의 유일한 증거다.
            await redis.hset(LAST_OK_KEY, provider,
                             datetime.now(UTC).isoformat(timespec="seconds"))
    except Exception as exc:                 # 계측이 본체를 죽이지 않는다
        logger.debug("[llm] 사용량 기록 실패: %s", exc)


async def record_blackout(redis, role: str) -> int:
    """전 provider 전멸 1건. 반환: 그날 누적 횟수(모르면 0)."""
    if redis is None:
        return 0
    try:
        key = BLACKOUT_KEY.format(_today())
        n = await redis.incr(key)
        await redis.expire(key, TTL)
        if n == BLACKOUT_WARN:
            logger.error("[llm] 🔴 오늘 전 provider 전멸 %d회 — provider 추가가 필요하다", n)
        return int(n)
    except Exception:
        return 0


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
             # 🔴 [SEC-1] **자르기 전에 가린다.** 먼저 자르면 키가 200자
             #    경계에서 잘려 앞부분이 그대로 남는다. 로그는 회전되지만
             #    이 값은 TTL 14일 동안 조회 가능하다 (실사고 2026-09-07).
             "detail": mask_secrets(detail)[:200]}, ensure_ascii=False))
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
    last_ok, blackouts = {}, 0
    try:
        last_ok = await redis.hgetall(LAST_OK_KEY) or {}
        blackouts = int(await redis.get(BLACKOUT_KEY.format(_today())) or 0)
    except Exception as exc:
        logger.debug("[llm] 최근 성공/전멸 조회 실패: %s", exc)
    return {"calls": calls, "outages": outages,
            "last_ok": last_ok, "blackouts": blackouts}


def _alive(iso: str | None, now: datetime, hours: int = 6) -> bool:
    """최근 성공이 이 안에 있으면 '가용'으로 본다.

    ⚠️ 이것은 **관측**이지 헬스체크가 아니다. 부르지 않은 provider는 성공 기록도
       없으므로 '미확인'이지 '죽음'이 아니다 — 둘을 뭉치면 멀쩡한 provider를
       죽었다고 표시한다.
    """
    if not iso:
        return False
    try:
        return (now - datetime.fromisoformat(iso)).total_seconds() < hours * 3600
    except ValueError:
        return False


_KIND_KR = {"quota": "크레딧 소진", "rate_limit": "레이트리밋", "auth": "키 오류",
            "budget": "토큰 예산 부족", "other": "기타"}


def format_summary(data: dict, show_outages: int = 3) -> list[str]:
    """/health 줄. **잔여 크레딧은 쓰지 않는다** — 벤더가 알려주지 않는 값을
    추정해서 보여주면 그 추정이 근거로 쓰인다. 아는 것만 쓴다."""
    calls, outages = data.get("calls") or {}, data.get("outages") or []
    if not calls and not outages and not data.get("last_ok") \
            and not data.get("blackouts"):
        return ["🤖 LLM: 기록 없음"]
    lines = []
    last_ok = data.get("last_ok") or {}
    blackouts = int(data.get("blackouts") or 0)
    if last_ok:
        now = datetime.now(UTC)
        parts = []
        for prov, iso in sorted(last_ok.items()):
            mark = "🟢" if _alive(iso, now) else "🔴"
            parts.append(f"{mark}{prov} {(iso or '')[11:16]}")
        lines.append("🤖 provider 마지막 성공: " + " · ".join(parts)
                     + "  (6시간 내 성공이면 🟢 · 부르지 않은 provider는 표시되지 않음)")
    if blackouts:
        icon = "🔴" if blackouts >= BLACKOUT_WARN else "⚠️"
        lines.append(f"{icon} 오늘 전 provider 전멸 {blackouts}회"
                     + (" — provider 추가가 필요하다" if blackouts >= BLACKOUT_WARN else ""))
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
