"""[7] 실행 중 오류의 실시간 전달 — **조용한 실패 금지**.

실사고(2026-08-25): 프리페치가 λ 0/15, judge 전 배치 실패, 축구 크래시로
사실상 전부 실패했는데 사용자는 아무것도 몰랐다. 로그에만 남고 끝났다.

원칙:
- 단계가 실패하면 **그 시점에** 알린다 (끝나고 요약하는 게 아니라).
- 실패해도 성공해도 **프리페치 실행 리포트는 항상 보낸다**.
- 같은 오류 반복은 억제하되(스팸 방지), 억제 건수를 밝힌다.
- 억제 예외: 실행 리포트와 크래시는 언제나 보낸다.
"""

import logging
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from app.notify import send_telegram

logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

SUPPRESS_WINDOW_SEC = 30 * 60      # [7-6] 동일 오류는 30분에 1회

# ⚠️ 억제 상태는 **반드시 프로세스 밖(Redis)** 에 둔다.
#    실사고(2026-08-25): 프로세스 메모리 딕셔너리로 구현했더니 전혀 억제되지 않았다.
#    알림을 보내는 주체가 매번 새 프로세스(스케줄러 잡·CLI·프리페치)라
#    딕셔너리가 매번 비어 있었기 때문이다. 단일 프로세스 테스트만으로는
#    이 결함이 드러나지 않는다 — 억제는 프로세스 경계를 넘어야 의미가 있다.
SUP_KEY = "alert:sup:{}"
HELD_KEY = "alert:held:{}"

# 폭주 방어: 어떤 이유로든 10분 안에 이 수를 넘으면 전부 막는다.
GLOBAL_BUDGET = 12
GLOBAL_WINDOW_SEC = 600
BUDGET_KEY = "alert:budget"

_last_sent: dict[str, float] = {}      # Redis 불가 시 폴백 (단일 프로세스 한정)
_suppressed: dict[str, int] = {}

# 원인 분류 라벨 — 사용자가 "충전하면 되는지 기다리면 되는지"를 즉시 알 수 있게
CAUSE_LABELS = {
    "credit": "크레딧 부족",
    "auth": "키 오류",
    "rate_limit": "레이트리밋",
    "parse": "파싱 실패",
    "timeout": "타임아웃",
    "exception": "예외",
    "missing": "데이터 없음",
}


def reset() -> None:
    """테스트용 — 프로세스 내 폴백 상태 초기화."""
    _last_sent.clear()
    _suppressed.clear()


async def reset_shared() -> None:
    """운영용 — Redis에 남은 억제 키를 지운다 (알림 재개)."""
    r = await _redis()
    if r is None:
        return
    try:
        keys = await r.keys("alert:*")
        if keys:
            await r.delete(*keys)
    finally:
        await r.aclose()


def classify_exception(exc: BaseException) -> str:
    """예외를 원인 분류 키로. 알림 문구의 '무엇을 하면 되는지'를 좌우한다."""
    from app.collectors.base import (
        ApiAuthError,
        ApiQuotaError,
        ApiRateLimitError,
        classify_api_error,
    )

    if isinstance(exc, ApiQuotaError):
        return "credit"
    if isinstance(exc, ApiAuthError):
        return "auth"
    if isinstance(exc, ApiRateLimitError):
        return "rate_limit"
    text = str(exc)
    if isinstance(exc, TimeoutError) or "timeout" in text.lower():
        return "timeout"
    if isinstance(exc, (ValueError, KeyError, TypeError)) and "json" in text.lower():
        return "parse"
    # SDK 예외처럼 status가 붙어 있으면 본문으로 분류 (Anthropic 크레딧은 400)
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        kind = classify_api_error(status, text)
        if kind in CAUSE_LABELS:
            return kind
    return "exception"


def our_frames(exc: BaseException, limit: int = 5) -> list[str]:
    """스택 트레이스에서 **우리 코드 프레임만** 최대 limit줄.

    라이브러리 내부 프레임은 원인 파악에 도움이 안 되고 메시지만 길어진다.
    """
    frames = traceback.extract_tb(exc.__traceback__)
    ours = [f for f in frames if "/app/" in f.filename or f.filename.startswith("app/")]
    picked = (ours or frames)[-limit:]
    out = []
    for f in picked:
        name = f.filename.split("/app/")[-1] if "/app/" in f.filename else f.filename
        out.append(f"  app/{name}:{f.lineno} in {f.name}()")
    return out


async def _redis():
    """알림용 Redis. 실패해도 알림 자체를 막지 않는다 (None 반환)."""
    try:
        import redis.asyncio as aioredis

        from app.config import get_settings

        return aioredis.from_url(get_settings().redis_url, decode_responses=True)
    except Exception as exc:
        logger.warning("[alerts] Redis 연결 불가 — 프로세스 내 억제로 폴백: %s", exc)
        return None


async def _over_budget(r) -> int | None:
    """10분 창의 전역 알림 예산. 초과하면 초과 건수를 반환한다."""
    if r is None:
        return None
    try:
        n = await r.incr(BUDGET_KEY)
        if n == 1:
            await r.expire(BUDGET_KEY, GLOBAL_WINDOW_SEC)
        return n - GLOBAL_BUDGET if n > GLOBAL_BUDGET else None
    except Exception:
        return None


async def _claim(r, key: str) -> tuple[bool, int]:
    """이 키로 지금 보내도 되는가. (보내도 됨, 그동안 억제된 건수)."""
    if r is None:      # Redis 없음 — 프로세스 내 폴백 (억제가 약해진다)
        now = time.monotonic()
        last = _last_sent.get(key)
        if last is not None and now - last < SUPPRESS_WINDOW_SEC:
            _suppressed[key] = _suppressed.get(key, 0) + 1
            return False, 0
        _last_sent[key] = now
        return True, _suppressed.pop(key, 0)
    try:
        # SET NX EX — 창이 비어 있을 때만 선점한다 (프로세스가 달라도 공유된다)
        got = await r.set(SUP_KEY.format(key), "1", nx=True, ex=SUPPRESS_WINDOW_SEC)
        if not got:
            await r.incr(HELD_KEY.format(key))
            await r.expire(HELD_KEY.format(key), SUPPRESS_WINDOW_SEC * 2)
            return False, 0
        held = await r.get(HELD_KEY.format(key))
        await r.delete(HELD_KEY.format(key))
        return True, int(held or 0)
    except Exception as exc:
        logger.warning("[alerts] 억제 상태 조회 실패 — 발송은 진행: %s", exc)
        return True, 0


async def _send(key: str, text: str, *, bypass_suppression: bool = False) -> bool:
    """억제 규칙을 적용해 발송. key가 같으면 30분에 1회 — **프로세스 경계를 넘어서**."""
    r = await _redis()
    try:
        over = await _over_budget(r)
        if over is not None and not bypass_suppression:
            logger.warning("[alerts] 전역 예산 초과(%d분 %d건) — 억제: %s",
                           GLOBAL_WINDOW_SEC // 60, GLOBAL_BUDGET, key)
            return False
        if not bypass_suppression:
            ok, held = await _claim(r, key)
            if not ok:
                logger.info("[alerts] 억제(%s)", key)
                return False
            if held:
                text += f"\n\n(같은 오류 {held}건은 30분 억제 후 합산 표기)"
        return await send_telegram(text)
    finally:
        if r is not None:
            try:
                await r.aclose()
            except Exception:
                pass


# ---------------------------------------------------------------- [7-2] 단계 실패

@dataclass
class StageResult:
    """한 단계의 결과. 실행 리포트와 즉시 알림이 같은 객체를 쓴다."""

    name: str
    ok: int = 0
    total: int = 0
    cause: str | None = None       # CAUSE_LABELS 키
    detail: str = ""               # 예외 메시지 등
    frames: list[str] = field(default_factory=list)
    impact: str = ""               # 이것이 최종 결과에 주는 영향 한 줄

    @property
    def failed(self) -> bool:
        return self.cause is not None or (self.total > 0 and self.ok < self.total)

    @property
    def icon(self) -> str:
        if not self.failed:
            return "✅"
        return "🔴" if self.ok == 0 else "🟡"

    def line(self) -> str:
        count = f"{self.ok}/{self.total}" if self.total else ("실패" if self.failed else "완료")
        parts = [f"{self.icon} {self.name} {count}"]
        if self.cause:
            parts.append(f"— {CAUSE_LABELS.get(self.cause, self.cause)}")
        if self.detail:
            parts.append(f"({self.detail[:110]})")
        return " ".join(parts)


async def stage_failed(stage: StageResult) -> bool:
    """[7-2] 단계 실패 즉시 알림. 원인·영향까지 담는다."""
    if not stage.failed:
        return False
    lines = [f"{stage.icon} 단계 실패 — {stage.name}",
             f"진행 {stage.ok}/{stage.total}" if stage.total else "진행 불가",
             f"원인 {CAUSE_LABELS.get(stage.cause or 'exception', stage.cause)}"]
    if stage.detail:
        lines.append(f"내용 {stage.detail[:200]}")
    if stage.frames:
        lines.append("위치\n" + "\n".join(stage.frames))
    if stage.impact:
        lines.append(f"→ 영향: {stage.impact}")
    return await _send(f"stage:{stage.name}:{stage.cause}", "\n".join(lines))


# ---------------------------------------------------------------- [7-3] 크래시

async def crashed(where: str, exc: BaseException, *, next_retry: str = "") -> bool:
    """[7-3] 예외로 중단됨 — 억제 없이 항상 발송."""
    lines = [f"💥 중단 — {where}",
             f"{type(exc).__name__}: {str(exc)[:250]}",
             "위치(우리 코드)", *our_frames(exc)]
    if next_retry:
        lines.append(f"다음 재시도 {next_retry}")
    return await _send(f"crash:{where}", "\n".join(lines), bypass_suppression=True)


async def job_failed(job_name: str, exc: BaseException, next_run: str = "") -> bool:
    """[7-3] 스케줄러 잡 실패 — 잡 이름과 다음 실행 시각."""
    return await crashed(f"스케줄러 잡 {job_name}", exc, next_retry=next_run)


# ---------------------------------------------------------------- [7-1] 실행 리포트

async def prefetch_report(
    stages: list[StageResult], elapsed_sec: float, verdict_line: str,
) -> bool:
    """[7-1] 프리페치 실행 리포트 — 성공·실패 무관하게 **항상** 발송."""
    from app.version import boot_info

    now = datetime.now(KST)
    mins, secs = divmod(int(elapsed_sec), 60)
    head = f"📋 프리페치 완료 {now:%Y-%m-%d %H:%M} (소요 {mins}분 {secs}초)"
    body = "\n".join(s.line() for s in stages)
    tail = f"→ 결과: {verdict_line}"
    foot = f"코드 {boot_info().short}"
    return await _send("prefetch:report", f"{head}\n{body}\n{tail}\n{foot}",
                       bypass_suppression=True)


def overall_verdict(stages: list[StageResult]) -> str:
    """단계 결과를 한 줄 결론으로. 사용자가 오늘 리포트를 믿어도 되는지 판단하게."""
    hard = [s for s in stages if s.failed and s.ok == 0]
    soft = [s for s in stages if s.failed and s.ok > 0]
    if not hard and not soft:
        return "정상 — 오늘 리포트는 전 단계 데이터를 반영합니다"
    if any(s.name.startswith("판정") for s in hard):
        return "오늘 리포트는 **판정 없이** 나갑니다 — 추천·조합이 생성되지 않습니다"
    if any(s.name.startswith("λ") for s in hard):
        return "λ 미산출 — 확률이 폴백(경기력 %p 조정) 경로로 계산됩니다"
    if hard:
        return f"{', '.join(s.name for s in hard)} 전량 실패 — 리포트 신뢰도가 낮습니다"
    return f"{', '.join(s.name for s in soft)} 일부 실패 — 해당 경기만 데이터가 얕습니다"
