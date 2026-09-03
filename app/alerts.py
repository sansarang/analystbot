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
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app import notify as _notify_mod

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
    "credit_400": "크레딧 부족(credit_400)",
    "auth": "키 오류",
    "rate_limit": "레이트리밋",
    "parse": "파싱 실패",
    "parse_fail": "파싱 실패(parse_fail)",
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
        return "credit_400"
    if isinstance(exc, ApiAuthError):
        return "auth"
    if isinstance(exc, ApiRateLimitError):
        return "rate_limit"
    text = str(exc)
    if isinstance(exc, TimeoutError) or "timeout" in text.lower():
        return "timeout"
    if isinstance(exc, (ValueError, KeyError, TypeError)) and "json" in text.lower():
        return "parse_fail"
    # SDK 예외처럼 status가 붙어 있으면 본문으로 분류 (Anthropic 크레딧은 400)
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        kind = classify_api_error(status, text)
        if kind == "credit":
            return "credit_400"
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


async def _claim(r, key: str, window_sec: int = SUPPRESS_WINDOW_SEC) -> tuple[bool, int]:
    """이 키로 지금 보내도 되는가. (보내도 됨, 그동안 억제된 건수)."""
    if r is None:      # Redis 없음 — 프로세스 내 폴백 (억제가 약해진다)
        now = time.monotonic()
        last = _last_sent.get(key)
        if last is not None and now - last < window_sec:
            _suppressed[key] = _suppressed.get(key, 0) + 1
            return False, 0
        _last_sent[key] = now
        return True, _suppressed.pop(key, 0)
    try:
        # SET NX EX — 창이 비어 있을 때만 선점한다 (프로세스가 달라도 공유된다)
        got = await r.set(SUP_KEY.format(key), "1", nx=True, ex=window_sec)
        if not got:
            await r.incr(HELD_KEY.format(key))
            await r.expire(HELD_KEY.format(key), window_sec * 2)
            return False, 0
        held = await r.get(HELD_KEY.format(key))
        await r.delete(HELD_KEY.format(key))
        return True, int(held or 0)
    except Exception as exc:
        logger.warning("[alerts] 억제 상태 조회 실패 — 발송은 진행: %s", exc)
        return True, 0


def quota_window_sec() -> int:
    """크레딧 소진 알림 창 — KST 다음 자정까지. 최소 60초."""
    now = datetime.now(KST)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(60, int((nxt - now).total_seconds()))


async def _send(key: str, text: str, *, bypass_suppression: bool = False,
                window_sec: int | None = None) -> bool:
    """억제 규칙을 적용해 발송. 기본은 30분에 1회 — **프로세스 경계를 넘어서**.

    크레딧 소진(`quota:*`)은 `window_sec=quota_window_sec()`로 하루 1회.
    """
    window = SUPPRESS_WINDOW_SEC if window_sec is None else window_sec
    r = await _redis()
    try:
        over = await _over_budget(r)
        if over is not None and not bypass_suppression:
            logger.warning("[alerts] 전역 예산 초과(%d분 %d건) — 억제: %s",
                           GLOBAL_WINDOW_SEC // 60, GLOBAL_BUDGET, key)
            return False
        if not bypass_suppression:
            ok, held = await _claim(r, key, window)
            if not ok:
                logger.info("[alerts] 억제(%s)", key)
                return False
            if held:
                span = "오늘" if window >= 12 * 3600 else "30분"
                text += f"\n\n(같은 오류 {held}건은 {span} 억제 후 합산 표기)"
        # ⚠️ **모듈 속성으로 부른다.** `from app.notify import send_telegram`으로
        #   묶으면 발송 지점이 둘로 갈라져, 한쪽만 막으면 다른 쪽으로 새어 나간다.
        #   실제 발송을 막는 자리는 하나여야 한다.
        return await _notify_mod.send_telegram(text)
    finally:
        if r is not None:
            try:
                await r.aclose()
            except Exception:
                pass


# ---------------------------------------------------------------- [7-2] 단계 실패

@dataclass
class StageResult:
    """한 단계의 결과. 실행 리포트와 요약 알림이 같은 객체를 쓴다.

    ⚠️ **단위(`unit`)를 반드시 맞춰라.** 표시 계층이 "N경기"를 붙이는데 팀 수나
       값 개수를 넣으면 5경기 슬레이트에 "출처 대조 438경기"가 나간다
       (실측 2026-08-27). 숫자가 한 번 틀리면 그 숫자를 근거로 한 판단이
       전부 틀어진다.

    ⚠️ **부분 수집은 실패가 아니다.** 5경기 중 3경기에만 기사가 있는 것은 정상이다.
       그런 단계는 `expect_full=False`로 선언한다 — 짐작이 아니라 선언이다.
    """

    name: str
    ok: int = 0
    total: int = 0
    cause: str | None = None       # CAUSE_LABELS 키
    detail: str = ""               # 예외 메시지 등
    frames: list[str] = field(default_factory=list)
    impact: str = ""               # 이것이 최종 결과에 주는 영향 한 줄
    unit: str = "경기"             # ok/total이 무엇을 세는가 (경기·팀·구장·값·건)
    expect_full: bool = True       # 전량 수집이 정상인가 (False면 부분도 정상)
    zero_ok: bool = False          # **지금 시점에** 0건이 정상인가 (예: 라인업 발표 전)
    no_games: bool = False         # 오늘 그 리그에 **경기 자체가 없다**(휴식일)

    @property
    def severity(self) -> str:
        """정상 · 부분 · 실패. **이 셋을 뭉뚱그리면 화면이 못 쓰게 된다.**

        ⚠️ `zero_ok`는 "0이어도 된다"가 아니라 **"지금은 0인 것이 맞다"**이다.
           호출부가 시각 같은 근거로 판단해서 넘겨야 하고, 상시로 켜두면
           수집기가 죽어도 조용해진다.
        """
        # 🔴 "경기가 없는 날"과 "경기가 있는데 못 모은 날"은 다른 사건이다.
        #    뭉뚱그리면 휴식일마다 전량 실패 알림이 나가고(실측 2026-08-31 14:01
        #    KBO·NPB 7건 오경보), 그 소음에 진짜 실패가 묻힌다.
        #    이 구분이 no_games의 전부다 — cause보다 **먼저** 본다.
        if self.no_games:
            return "경기없음"
        if self.cause is not None:
            return "실패"
        if self.total > 0 and self.ok == 0:
            return "정상" if self.zero_ok else "실패"
        if self.total > 0 and self.ok < self.total:
            return "부분" if self.expect_full else "정상"
        return "정상"

    @property
    def failed(self) -> bool:
        return self.severity == "실패"

    @property
    def partial(self) -> bool:
        return self.severity == "부분"

    @property
    def icon(self) -> str:
        # ⚪ 는 성공도 실패도 아닌 제3의 상태다 — ✅로 쓰면 "수집했다"로 읽힌다.
        return {"정상": "✅", "부분": "🟡", "실패": "🔴",
                "경기없음": "⚪"}[self.severity]

    def line(self) -> str:
        if self.no_games:
            return f"{self.icon} {self.name} — 경기 없음(휴식일)"
        count = (f"{self.ok}/{self.total}{self.unit}" if self.total
                 else ("실패" if self.failed else "완료"))
        parts = [f"{self.icon} {self.name} {count}"]
        if self.cause:
            parts.append(f"— {CAUSE_LABELS.get(self.cause, self.cause)}")
            if self.cause in ("credit_400", "parse_fail", "timeout"):
                parts.append(f"[{self.cause}]")
        if self.detail:
            parts.append(f"({self.detail[:110]})")
        return " ".join(parts)


async def stage_failed(stage: StageResult) -> bool:
    """[7-2] **전면 중단만** 즉시 알린다 — 그 수집기가 통째로 0건인 경우.

    ⚠️ 부분 실패는 여기로 오면 안 된다. `stages_summary`가 분석 끝에 한 건으로
       묶는다. 종전에는 부분 실패까지 즉시 발송해 한 번의 분석에서 알림이
       7~8건 쏟아졌고, 정작 카드가 안 보였다(실측 2026-08-27).
    """
    if stage.severity != "실패":
        return False
    lines = [f"🔴 전면 중단 — {stage.name}",
             f"진행 {stage.ok}/{stage.total}{stage.unit}" if stage.total else "진행 불가"]
    # ⚠️ 원인이 없으면 "예외"라고 쓰지 마라 — 종전에는 cause=None이 'exception'으로
    #    폴백해, 예외가 없었는데도 "원인 예외"로 나갔다(실측 2026-08-27).
    if stage.cause:
        lines.append(f"원인 {CAUSE_LABELS.get(stage.cause, stage.cause)}")
    if stage.detail:
        lines.append(f"내용 {stage.detail[:200]}")
    if stage.frames:
        lines.append("위치\n" + "\n".join(stage.frames))
    if stage.impact:
        lines.append(f"→ 영향: {stage.impact}")
    return await _send(f"stage:{stage.name}:{stage.cause}", "\n".join(lines))


async def stages_summary(stages: list[StageResult], *, where: str = "분석") -> bool:
    """[7-2] 한 번의 분석이 끝날 때 **실패 요약 1건**.

    🔴 종전에는 단계마다 즉시 발송했다. 한 번의 분석에서 알림이 7~8건 쏟아져
       **정작 카드가 안 보였다**(실측 2026-08-27). 즉시 발송은 크래시와 전면
       중단(`crashed`)만 한다 — 나머지는 여기서 한 건으로 묶는다.

    정상·부분만 있으면 발송하지 않는다. 부분 수집은 알릴 일이 아니다.
    """
    bad = [s for s in stages if s.failed]
    if not bad:
        return False
    soft = [s for s in stages if s.partial]
    lines = [f"🔴 {where} 단계 실패 {len(bad)}건"]
    lines += [f"  {s.line()}" for s in bad[:8]]
    if len(bad) > 8:
        lines.append(f"  … 외 {len(bad) - 8}건")
    impacts = [s.impact for s in bad if s.impact]
    if impacts:
        lines.append("→ 영향: " + " · ".join(dict.fromkeys(impacts))[:300])
    if soft:
        lines.append("(부분 수집 — 실패 아님: "
                     + ", ".join(f"{s.name} {s.ok}/{s.total}{s.unit}" for s in soft[:5]) + ")")
    key = "stages:" + ",".join(sorted(s.name for s in bad))
    return await _send(key, "\n".join(lines))


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
    extra = ""
    try:
        from app.api_guard import prefetch_status_lines

        lines = await prefetch_status_lines()
        if lines:
            extra = "\n" + "\n".join(lines)
    except Exception as exc:
        logger.debug("[alerts] 미사용/차단 줄 생략: %s", exc)
    return await _send("prefetch:report",
                       f"{head}\n{body}{extra}\n{tail}\n{foot}",
                       bypass_suppression=True)


def _no_game_leagues(stages: list[StageResult]) -> list[str]:
    """`[KBO] 경기 적재` 같은 이름에서 휴식일 리그를 뽑는다."""
    import re

    out: list[str] = []
    for st in stages:
        if not st.no_games:
            continue
        m = re.match(r"\[([^\]]+)\]", st.name)
        lg = m.group(1) if m else None
        if lg and lg not in out:
            out.append(lg)
    return out


def overall_verdict(stages: list[StageResult]) -> str:
    """단계 결과를 한 줄 결론으로. 사용자가 오늘 리포트를 믿어도 되는지 판단하게."""
    # 휴식일은 "신뢰도가 낮다"가 아니라 **확인된 사실**이다. 먼저 답한다.
    rest = _no_game_leagues(stages)
    if rest and not [s for s in stages if s.failed]:
        return f"오늘 {'·'.join(rest)} 경기 없음 확인 — 수집 실패가 아닙니다"
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


# ─────────────────────────────────────────── 사이클 리포트 (2026-09-01)
#
# 🔴 종전에는 저녁 판정 사이클에 **리포트 발송이 아예 없었다.** `prefetch_report`
#    는 프리페치 잡(04:00·14:00·21:00)에서만 불린다. 그래서 KBO·NPB 저녁
#    슬레이트가 어떻게 됐는지 알려면 Railway 로그를 직접 열어야 했다
#    (실측 2026-09-01: 하루 종일 그렇게 했다).
#
# ⚠️ 그렇다고 폴링 틱마다 보내면 안 된다 — 5분 간격이라 하루 100건이 넘고,
#    2026-08-27 의 "알림 7~8건 폭주로 정작 카드가 안 보인" 사고가 재발한다.
#    **한 사이클에 1건**, 그리고 **일이 있었을 때만** 보낸다.


async def cycle_report(where: str, lines: list[str], verdict: str, *,
                       elapsed_sec: float | None = None) -> bool:
    """[1단계] 한 판정 사이클의 결과 1건. 성공·실패 무관하게 **항상** 보낸다.

    호출부가 "보낼 만한 일이 있었는가"를 판단한다 — 빈 폴링 틱에서는 부르지
    않는다. 여기서 억제하지 않는 이유는, 억제하면 30분에 1건이 되어 5분
    간격 사이클에서 6번 중 1번만 도착하기 때문이다.
    """
    from app.version import boot_info

    now = datetime.now(KST)
    head = f"📋 {where} {now:%H:%M}"
    if elapsed_sec is not None:
        mins, secs = divmod(int(elapsed_sec), 60)
        head += f" (소요 {mins}분 {secs}초)"
    body = "\n".join(lines) if lines else "  (기록할 단계 없음)"
    return await _send(f"cycle:{where}:{now:%Y%m%d%H%M}",
                       f"{head}\n{body}\n→ 결과: {verdict}\n"
                       f"코드 {boot_info().short}",
                       bypass_suppression=True)


async def cycle_errors(where: str, errors: list[dict], *,
                       next_run: str = "") -> bool:
    """[2단계] 한 사이클의 이상을 **한 건으로 묶어** 보낸다.

    🔴 부분 실패를 개별 발송하면 다시 폭주한다. 반대로 지금처럼 전면 중단만
       보내면 "12경기 중 3경기 판정 실패"가 통째로 침묵한다. 묶어서 1건이 답이다.

    ⚠️ **파일:라인을 싣는다.** 사용자가 이 메시지를 그대로 전달하면 바로
       어디를 볼지 정해진다 — 로그를 열지 않아도 된다.

    errors: [{"what": str, "cause": str|None, "detail": str, "exc": Exception|None}]
    """
    from app.version import boot_info

    if not errors:
        return False
    now = datetime.now(KST)
    lines = [f"⚠️ {where} 이상 {len(errors)}건 ({now:%H:%M})"]
    for e in errors[:8]:
        row = f"  · {e.get('what')}"
        cause = e.get("cause")
        if cause:
            row += f" — {CAUSE_LABELS.get(cause, cause)}"
        detail = (e.get("detail") or "").strip()
        if detail:
            row += f" ({detail[:120]})"
        lines.append(row)
        exc = e.get("exc")
        if exc is not None:
            lines += our_frames(exc, limit=2)
    if len(errors) > 8:
        lines.append(f"  · 외 {len(errors) - 8}건")
    tail = f"코드 {boot_info().short}"
    if next_run:
        tail += f" · 다음 {next_run}"
    lines.append(tail)
    # 사이클마다 1건 — 30분 억제 창에 걸리면 5분 폴링에서 6번 중 1번만 온다.
    return await _send(f"cycle-err:{where}:{now:%Y%m%d%H%M}", "\n".join(lines),
                       bypass_suppression=True)


#: 워치독 경보 억제 창 — 같은 코드+대상은 이 간격에 1회.
#  🔴 30분(기본)이면 5분 잡에서 6틱 중 1번만 도착한다. 고장은 계속 나는데
#     알림이 드문 것이 더 위험하므로 15분으로 좁힌다. 대신 **코드+대상**이
#     키라서, 서로 다른 고장은 서로를 막지 않는다.
WATCHDOG_WINDOW_SEC = 15 * 60

#: 워치독 코드 → 사람이 읽는 한 줄. 코드는 로그·경보에 그대로 실린다.
WATCHDOG_CODES = {
    "W-SEND-PENDING": "발송 창인데 안 나간 경기",
    "W-ODDS-STALE": "배당 스냅샷이 오래됨",
    "W-ODDS-BLOCKED": "배당 API 차단 상태",
    "W-LLM-FAIL": "LLM 호출 연속 실패",
    "W-STORE-DOWN": "DB·Redis 오류",
    "W-JOB-LATE": "스케줄러 잡이 주기를 넘김",
    "W-RESCUE-DEAD": "판정 캐시 구제 실패",
    # 감시 3층 (v1.3-monitor) — 전부 사후 관측이고 발송을 막지 않는다.
    "W-FACT-MISMATCH": "판정이 인용한 수치가 원문과 다름",
    "W-PANEL-DIVERGE": "독립 판정과 편차 큼",
    "W-JUDGE-OBJECTION": "검사역이 판정에 이의를 냈다",
    "W-MONITOR-DOWN": "감시층 자체가 실패",
}


async def watchdog(code: str, detail: str, *, target: str = "") -> bool:
    """[2단계] 워치독 경보 1줄. **코드 + 대상**이 억제 키다.

    ⚠️ 코드를 반드시 붙인다 — 사람이 로그를 grep 할 수 있어야 하고,
       오탐을 코드 단위로 끌 수 있어야 한다.
    ⚠️ 경보는 "무엇이 잘못됐나"만 말한다. 고치는 것은 사람 몫이다.
    """
    label = WATCHDOG_CODES.get(code, "점검 필요")
    head = f"🚨 {code} · {label}"
    body = detail if not target else f"{target} — {detail}"
    return await _send(f"watchdog:{code}:{target}", f"{head}\n{body}",
                       window_sec=WATCHDOG_WINDOW_SEC)


async def dispatch_report(where: str, stats: dict) -> bool:
    """[1단계] 가동률 1줄 — 대상 / 발송 / 사유별 미발송.

    ⚠️ **"조용한 0"은 결함이다.** 미발송이 있으면 전건에 사유가 붙는다.
    """
    sent = stats.get("sent", 0) + stats.get("revised", 0) + stats.get("unchanged", 0)
    target = stats.get("target", 0)
    pct = f"{sent * 100 // target}%" if target else "—"
    lines = [f"📮 {where} 발송률 {pct} ({sent}/{target})"]
    misses = stats.get("misses") or {}
    if misses:
        lines.append("미발송:")
        lines += [f"  · {reason} {n}건" for reason, n in sorted(misses.items())]
    elif target:
        lines.append("미발송 0건")
    return await _send(f"dispatch:{where}", "\n".join(lines),
                       bypass_suppression=True)
