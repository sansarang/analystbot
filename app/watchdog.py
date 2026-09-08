"""[운영 안정화 2] 워치독 — **고장을 시스템이 먼저 알린다.**

사람이 먼저 발견하는 고장은 0건이어야 한다. 5분마다 다섯 가지를 보고,
하나라도 걸리면 관리자 채널로 코드가 붙은 1줄 경보를 보낸다.

🔴 **코드 목록을 여기 적지 않는다.** 원본은 `app.alerts.WATCHDOG_CODES` 다.
   이 모듈은 숫자(주기·문턱·보장선)를 전부 원본에서 읽으면서 **코드 목록만
   손으로 적고 있었고**, 그래서 네 곳(코드 16 · 라벨 14 · 이 독스트링 9 ·
   CLAUDE.md 9)이 전부 달랐다(실측 2026-09-08 WD-1).
   지금 무엇이 있는지 보려면:  python -c "from app.alerts import WATCHDOG_CODES
   as W; [print(k, '·', v) for k, v in W.items()]"

🔴 왜 필요한가 (이번 주 실사고):
   · 배당이 **차단 상태로 며칠간 조용히 멈춰 있었다** — 매 실행 로그는
     `odds snapshot skipped — 차단 중`뿐이고 아무도 알림을 못 받았다.
     `api_guard` 차단은 TTL이 없어 시간으로 풀리지 않는다.
   · 크레딧이 소진돼 판정이 멈췄는데 카드도 경보도 없었다.
   · 판정 캐시 구제가 1회 실패로 20시간 잠겨 그 종목이 통째로 침묵했다.

⚠️ 이 모듈은 **읽기만 한다.** 고치지 않고, 차단을 임의로 풀지도 않는다 —
   자동 해제는 크레딧을 다시 태울 수 있어 사람이 결정할 일이다.
⚠️ 점검 하나가 실패해도 나머지는 계속한다. 워치독이 죽으면 눈이 없어진다.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

logger = logging.getLogger(__name__)

#: 배당 스냅샷이 이보다 오래되면 경보. 잡 주기가 30분이라 60분이면 2회 연속 실패다.
ODDS_STALE_MIN = 60
#: LLM 연속 실패 몇 번부터 경보인가. 크레딧 소진은 보통 즉시 연속으로 난다.
LLM_FAIL_STREAK = 3
#: 잡이 주기의 몇 배를 넘기면 늦은 것으로 보는가.
JOB_LATE_FACTOR = 2

LLM_FAIL_KEY = "watchdog:llm_fail"
ODDS_SNAP_KEY = "oddsnap:{}"

#: 🔴 **사본을 두지 않는다.** 담당 리그·활성 여부는 `app.registry` 가 원본이다.
#     오탐 ①(espn 이 KBO·NPB 경기 때문에 울림)이 이 분리로 사라진다.

#: 🔴 잡 유예도 `app.registry` 가 원본이다. **주기는 어디에도 적지 않는다** —
#     다음 실행 시각은 `scheduler._JOB_TRIGGERS` 가 계산한다(cron 창이든 인터벌이든).
#
#  실사고 2026-09-02 (배포 당일 오탐 4건이 전부 "사본이 원본과 어긋남"):
#    · `mlb_pregame_5m` 은 `CronTrigger(hour="5-11")` 인데 "주기 5분"으로 적어
#      12:40(창 밖)에 울렸다.
#    · 재기동 직후 인메모리 잡스토어가 초기화되는 것을 셈에 넣지 않았다.
#    · 미구현 소스(betman)를 감시 목록에 적었다.
#    · `due` 를 전 종목 합산으로 세어 MLB 전용 소스가 KBO 경기 때문에 울렸다.

#: 재기동 직후 유예. 인메모리 잡스토어가 초기화돼 첫 실행이 한 주기 뒤다.
BOOT_GRACE_MIN = 60


async def note_llm_failure(redis, detail: str = "") -> int:
    """LLM 호출 실패 1건. 반환은 현재 연속 실패 수."""
    if redis is None:
        return 0
    try:
        n = await redis.incr(LLM_FAIL_KEY)
        await redis.expire(LLM_FAIL_KEY, 3 * 3600)
        if detail:
            await redis.set(f"{LLM_FAIL_KEY}:last", detail[:300], ex=3 * 3600)
        return int(n)
    except Exception as exc:
        logger.debug("[watchdog] LLM 실패 기록 실패: %s", exc)
        return 0


async def clear_llm_failures(redis) -> None:
    """성공하면 연속 실패를 끊는다 — 이걸 빼면 경보가 영원히 남는다."""
    if redis is None:
        return
    try:
        await redis.delete(LLM_FAIL_KEY)
    except Exception as exc:
        logger.debug("[watchdog] LLM 실패 초기화 실패: %s", exc)


# ─────────────────────────── 점검 ───────────────────────────

async def check_odds(pool, redis) -> list[tuple[str, str, str]]:
    """배당 차단 · **provider 별** 스냅샷 나이. 반환 [(코드, 대상, 상세)].

    🔴 [무과금 전환 2026-09-02] 배당이 세 소스로 갈렸다. "배당이 낡았다"는
       이제 소스마다 따로 판정해야 한다 — ESPN 이 죽어도 배트맨이 살아 있으면
       KBO 는 멀쩡하고, 그 반대도 마찬가지다. 하나로 묶으면 어느 쪽이
       죽었는지 경보를 보고도 모른다.
    ⚠️ 유료 경로가 꺼져 있으면 `theodds` 차단은 경보하지 않는다 — 끈 것을
       고장이라고 울리면 그게 오탐이다.
    """
    out = []
    from app.config import get_settings

    paid = (get_settings().odds_provider or "free").lower() == "theodds"
    if paid:
        try:
            from app.api_guard import block_info

            info = await block_info("odds")
            if info:
                at = str(info.get("at") or "?")[:19]
                out.append(("W-ODDS-BLOCKED", "theodds",
                            f"{at} 부터 차단({info.get('reason')}) — TTL이 없어 "
                            f"스스로 풀리지 않는다. tools/unblock 로 해제"))
                return out      # 차단 중이면 stale 은 당연한 결과다. 중복 경보 금지.
        except Exception as exc:
            logger.debug("[watchdog] 배당 차단 조회 실패: %s", exc)
    if pool is None:
        return out
    # 🔴 **소스마다 담당 리그가 다르다.** 전 종목을 한 덩어리로 세면
    #    MLB 전용 소스(ESPN)가 KBO·NPB 경기 때문에 울린다 —
    #    실사고 2026-09-02 14:32~16:33, 베팅 시간대에 15분마다.
    #    담당 리그는 `app.registry` 가 원본이고 여기서 사본을 만들지 않는다.
    # 🔴 **붙일 경기가 없으면 배당이 없는 게 정상이다.** ESPN 은 14경기 배당을
    #    정상으로 줬는데 그 슬레이트가 `games` 에 아직 없어 매칭이 0이었다.
    from app.registry import active_providers

    try:
        rows = await pool.fetch(
            """SELECT sport, count(*) AS n FROM games
                WHERE status = 'scheduled' AND starts_at > now()
                  AND starts_at < now() + interval '36 hours'
                GROUP BY sport""")
        due_by_sport = {r["sport"]: int(r["n"]) for r in rows}
    except Exception as exc:
        logger.debug("[watchdog] 대상 경기 조회 실패: %s", exc)
        return out
    try:
        aged = await pool.fetch(
            """SELECT provider,
                      EXTRACT(EPOCH FROM (now() - max(captured_at))) / 60 AS age
                 FROM odds_snapshots
                WHERE captured_at > now() - interval '7 days'
                GROUP BY provider""")
    except Exception as exc:
        logger.debug("[watchdog] provider 나이 조회 실패: %s", exc)
        return out
    seen = {r["provider"]: float(r["age"] or 0) for r in aged}
    for prov in active_providers():
        due = sum(due_by_sport.get(sp, 0) for sp in prov.sports)
        if not due:
            logger.debug("[watchdog] %s — 담당 종목(%s) 예정 경기 0. 판정 생략",
                         prov.name, "·".join(prov.sports))
            continue
        age = seen.get(prov.name)
        if age is None:
            out.append(("W-ODDS-STALE", prov.name,
                        f"담당 {'·'.join(prov.sports).upper()} {due}경기가 "
                        f"36시간 안에 있는데 이 소스로 적재된 배당이 없다"))
        elif age > ODDS_STALE_MIN:
            out.append(("W-ODDS-STALE", prov.name,
                        f"마지막 적재 {age:.0f}분 전 (상한 {ODDS_STALE_MIN}분) · "
                        f"담당 {'·'.join(prov.sports).upper()} {due}경기 예정"))
    return out


async def check_llm(redis) -> list[tuple[str, str, str]]:
    """(c) LLM 연속 실패."""
    try:
        n = int(await redis.get(LLM_FAIL_KEY) or 0)
    except Exception:
        return []
    if n < LLM_FAIL_STREAK:
        return []
    try:
        last = await redis.get(f"{LLM_FAIL_KEY}:last") or ""
    except Exception:
        last = ""
    # 🔴 [2026-09-04] 종전 문구는 **"판정이 멈춰 있다"** 였는데 사실이 아니었다.
    #    이 카운터를 올리는 것은 구 체인(`llm/provider.py`)뿐이고, 그것이
    #    맡는 역할은 narrator·interpreter·intent·judge_a 다. **매치업 판정은
    #    무료 사슬(`judge_route`)이라 이 카운터와 무관하다.**
    #    실측 2026-09-04: 이 경보가 24회로 울리는 동안 KBO·NPB 카드는 정상
    #    발송됐다. 틀린 문구가 사람을 엉뚱한 곳으로 보냈다.
    #    ⚠️ 역할 이름은 `last` 안에 이미 들어 있다("narrator: …"). 지어내지 않고
    #       그것을 그대로 보여준다.
    role = (last.split(":", 1)[0] or "").strip() if last else ""
    what = f"{role} 계열" if role else "보조 LLM 역할(서술·해석·의도)"
    return [("W-LLM-FAIL", role or "aux",
             f"연속 {n}회 실패 — {what}이 멈춰 있다 "
             f"(매치업 판정은 별도 무료 사슬이라 무관)"
             + (f" ({last})" if last else ""))]


async def check_store(pool, redis) -> list[tuple[str, str, str]]:
    """(d) DB·Redis 실제 왕복. 연결 객체가 있는 것과 도는 것은 다르다."""
    out = []
    try:
        await redis.ping()
    except Exception as exc:
        out.append(("W-STORE-DOWN", "redis", f"{type(exc).__name__}: {exc}"[:200]))
    if pool is not None:
        try:
            await pool.fetchval("SELECT 1")
        except Exception as exc:
            out.append(("W-STORE-DOWN", "postgres",
                        f"{type(exc).__name__}: {exc}"[:200]))
    return out


def _next_expected(job_id: str, after: datetime):
    """마지막 실행 이후 **트리거가 말하는** 다음 실행 시각. 모르면 None.

    🔴 주기를 손으로 적지 않는다. cron 창(예: `hour="5-11"`)이든 인터벌이든
       트리거가 정답을 안다 — 이 함수가 오탐 방지의 핵심이다.
    """
    try:
        from app.scheduler import _JOB_TRIGGERS

        trig = _JOB_TRIGGERS.get(job_id)
        if trig is None:
            return None
        return trig.get_next_fire_time(after, after)
    except Exception as exc:
        logger.debug("[watchdog] 트리거 조회 실패 %s: %s", job_id, exc)
        return None


def _boot_time() -> datetime | None:
    """이 프로세스의 기동 시각. 모르면 None — 추측하지 않는다."""
    try:
        from app.version import boot_info

        started = boot_info().started_at
        return started.replace(tzinfo=UTC) if started.tzinfo is None else started
    except Exception as exc:
        logger.debug("[watchdog] 기동 시각 조회 실패: %s", exc)
        return None


def _booted_recently(now: datetime) -> bool:
    """이 프로세스가 방금 떴는가. 재기동 직후 경보를 막는다."""
    try:
        from app.version import boot_info

        started = boot_info().started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        return (now - started) < timedelta(minutes=BOOT_GRACE_MIN)
    except Exception as exc:
        logger.debug("[watchdog] 기동 시각 조회 실패: %s", exc)
        return False


async def check_jobs(redis) -> list[tuple[str, str, str]]:
    """(e) 잡이 **트리거가 말하는 다음 실행**을 지나도 안 돌았는가."""
    from app.health import _job_runs

    now = datetime.now(UTC)
    fresh = _booted_recently(now)
    booted = _boot_time()
    try:
        runs = await _job_runs(redis)
    except Exception as exc:
        logger.debug("[watchdog] 잡 실행 조회 실패: %s", exc)
        return []
    out = []
    from app.registry import JOB_GRACE

    for job_id, grace in JOB_GRACE.items():
        row = runs.get(job_id)
        if not row:
            continue          # 한 번도 안 돈 잡은 판단하지 않는다 (기동 직후 오탐)
        try:
            at = datetime.fromisoformat(row["at"])
        except (KeyError, ValueError):
            continue
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        expected = _next_expected(job_id, at)
        if expected is None:
            continue          # 트리거를 모르면 판단하지 않는다 — 추측 금지
        if expected.tzinfo is None:
            expected = expected.replace(tzinfo=UTC)

        # 🔴 [2026-09-03 신설] **배포 후 미실행** — 기동 유예를 뚫는 유일한 경우.
        #    APScheduler 는 in-memory jobstore 라 **재기동마다 인터벌이 처음부터
        #    다시 센다.** 배포를 주기보다 자주 하면 그 잡은 영원히 굶는다.
        #    실사고 2026-09-03: 감시 3층·Gemini·프로브를 10·6·15분 간격으로
        #    연달아 배포해 `odds_snapshot_30m` 이 88분간 한 번도 못 돌았다.
        #    `W-ODDS-STALE`(증상)만 15분마다 울고, 원인을 아는
        #    `W-JOB-LATE` 는 기동 유예에 막혀 침묵했다.
        #    → 마지막 실행이 **주기의 2배**를 넘었고 그 뒤 재기동이 있었다면,
        #      유예 중이라도 이름을 붙여 알린다.
        stale_min = (now - at).total_seconds() / 60
        period_min = max((expected - at).total_seconds() / 60, 1.0)
        if (booted is not None and booted > at
                and stale_min > period_min * 2):
            out.append(("W-JOB-LATE", job_id,
                        f"배포 후 미실행 — 마지막 실행 {stale_min:.0f}분 전"
                        f"(주기 {period_min:.0f}분), 그 뒤 재기동. 재기동은 "
                        f"인터벌을 초기화한다 — 주기보다 잦은 배포를 멈춰라"))
            continue
        if fresh:
            continue          # 재기동 직후의 통상 지연은 경보하지 않는다
        overdue = (now - expected).total_seconds() / 60
        if overdue > grace:
            out.append(("W-JOB-LATE", job_id,
                        f"예정 {expected.astimezone(KST):%H:%M} KST 를 "
                        f"{overdue:.0f}분 지났다 (유예 {grace}분)"))
    return out


async def check_pending_sends(pool, redis) -> list[tuple[str, str, str]]:
    """(f) 발송 창 안인데 아직 안 나간 경기.

    ⚠️ **판정이 있는데 안 나간 것만** 센다. 판정 자체가 없는 것은
       구제·크레딧 경보가 따로 잡는다 — 같은 고장을 두 번 울리지 않는다.
    """
    if pool is None:
        return []
    from app.engine.pregame_push import (
        SPORTS, card_sig_key, in_send_window, still_upcoming,
    )
    from app.pipeline import mlb_slate_date, today_kst

    now = datetime.now(UTC)
    try:
        rows = await pool.fetch(
            """SELECT id, sport, home, away, starts_at FROM games
                WHERE sport = ANY($1::text[]) AND status = 'scheduled'
                  AND starts_at > now()
                ORDER BY starts_at""", list(SPORTS))
    except Exception as exc:
        logger.debug("[watchdog] 미발송 조회 실패: %s", exc)
        return []
    pending = []
    for r in rows:
        sport = r["sport"]
        if not still_upcoming(r["starts_at"], now) or \
                not in_send_window(sport, r["starts_at"], now):
            continue
        try:
            if await redis.get(card_sig_key(r["id"])):
                continue                      # 이미 카드가 나갔다
            date_s = mlb_slate_date() if sport == "mlb" else today_kst()
            if not await redis.get(f"analysis:{sport}:{date_s}"):
                continue                      # 판정 캐시 자체가 없다 — 다른 경보 소관
        except Exception:
            continue
        pending.append(f"{r['away']}@{r['home']}")
    if not pending:
        return []
    return [("W-SEND-PENDING", f"{len(pending)}경기",
             "발송 창인데 카드가 없다: " + ", ".join(pending[:5])
             + (" 외" if len(pending) > 5 else ""))]


async def check_card_late(pool, redis) -> list[tuple[str, str, str]]:
    """(g) 🔴 **첫 카드 보장선(T-30)을 넘겼는데 카드가 없다.**

    `W-SEND-PENDING` 과 다르다: 그쪽은 "판정이 있는데 안 나갔다"만 센다.
    보장선은 **판정 유무를 묻지 않는다** — 사용자 결정(2026-09-03)은
    "그 시점엔 잠정이라도 나가야 한다"이므로, 판정이 없어서 못 나간 것도
    보장선 위반이다. 사유를 함께 적어 어느 쪽인지 구분한다.

    ⚠️ 보장선 값은 `pregame_push.FIRST_CARD_GUARANTEE_MIN` 이 원본이다 —
       여기 숫자를 적지 않는다(사본 금지).
    """
    if pool is None:
        return []
    from app.engine.pregame_push import (
        FIRST_CARD_GUARANTEE_MIN, SPORTS, card_sig_key, guarantee_due,
        still_upcoming,
    )
    from app.pipeline import mlb_slate_date, today_kst

    now = datetime.now(UTC)
    try:
        rows = await pool.fetch(
            """SELECT id, sport, home, away, starts_at, lineup_status FROM games
                WHERE sport = ANY($1::text[]) AND status = 'scheduled'
                  AND starts_at > now()
                ORDER BY starts_at""", list(SPORTS))
    except Exception as exc:
        logger.debug("[watchdog] 보장선 조회 실패: %s", exc)
        return []
    late = []
    for r in rows:
        if not still_upcoming(r["starts_at"], now):
            continue
        if not guarantee_due(r["starts_at"], now):
            continue
        try:
            if await redis.get(card_sig_key(r["id"])):
                continue                      # 첫 카드가 나갔다
            date_s = mlb_slate_date() if r["sport"] == "mlb" else today_kst()
            why = ("판정 캐시 없음"
                   if not await redis.get(f"analysis:{r['sport']}:{date_s}")
                   else "판정 있음·발송 안 됨")
        except Exception:
            continue
        late.append(f"{r['away']}@{r['home']}({why})")
    if not late:
        return []
    return [("W-CARD-LATE", f"{len(late)}경기",
             f"T-{FIRST_CARD_GUARANTEE_MIN} 보장선을 넘겼는데 첫 카드가 없다: "
             + ", ".join(late[:5]) + (" 외" if len(late) > 5 else ""))]


async def check_invisible_games(pool, redis) -> list[tuple[str, str, str]]:
    """(h) 🔴 **폴링 조회에서 사라진 경기.** 오늘 고장의 부류를 잡는다.

    실사고 2026-09-03: KBO 4경기가 `status='live'` 로 오적재돼 폴링 조회
    (`WHERE status='scheduled'`)에서 통째로 빠졌다. 카드도, 구제도, 경보도
    없이 `잡 executed successfully` + `워치독 이상 없음` 이 찍혔다.
    **미발송으로도 안 잡혔다 — 대상 목록 자체가 비었기 때문이다.**

    🔴 그래서 이 점검은 **폴링과 다른 눈으로 센다.** `status` 를 조건에 넣지
       않고 "곧 시작하는 경기"를 전부 센 뒤, 그중 폴링이 볼 수 있는 것이
       몇 개인지 비교한다. 같은 눈으로 감시하면 폴링이 못 보는 것을 감시도
       못 본다.

    ⚠️ 함께 **고친다.** 시작 전 `live` 는 불변식 위반이므로 워치독이 5분마다
       복구한다 — 기동 시 1회로는 오늘처럼 낮에 생긴 오염을 저녁 내내 못 푼다.
    """
    if pool is None:
        return []
    from app.engine.pregame_push import SPORTS

    out: list[tuple[str, str, str]] = []
    # ① 불변식 복구 — 워치독은 읽기만 한다는 원칙의 **예외**다.
    #    이건 "차단 해제"가 아니라 **불가능한 상태의 교정**이고, 사람이
    #    개입할 판단 여지가 없다(시작 전 경기는 진행 중일 수 없다).
    try:
        from app.scheduler import _repair_impossible_live

        fixed = await _repair_impossible_live(pool)
    except Exception as exc:
        logger.warning("[watchdog] 불변식 복구 실패: %s", exc)
        fixed = []
    if fixed:
        names = ", ".join(f"{r['away']}@{r['home']}" for r in fixed[:5])
        out.append(("W-GAME-INVISIBLE", f"{len(fixed)}경기",
                    f"시작 전인데 live 여서 폴링에서 빠져 있었다 → 복구함: {names}"))
    # ② 그래도 안 보이는 경기가 있는가 — status 를 조건에 넣지 않고 센다.
    try:
        rows = await pool.fetch(
            """SELECT sport,
                      count(*) AS total,
                      count(*) FILTER (WHERE status = 'scheduled') AS visible,
                      count(*) FILTER (
                          WHERE status NOT IN ('scheduled', 'cancelled',
                                               'postponed', 'suspended')) AS odd
                 FROM games
                WHERE sport = ANY($1::text[])
                  AND starts_at > now() AND starts_at < now() + interval '6 hours'
                GROUP BY sport""", list(SPORTS))
    except Exception as exc:
        logger.debug("[watchdog] 보이지 않는 경기 조회 실패: %s", exc)
        return out
    for r in rows:
        if int(r["odd"]) and not int(r["visible"]):
            out.append(("W-GAME-INVISIBLE", r["sport"].upper(),
                        f"6시간 내 {r['total']}경기가 있는데 폴링이 볼 수 있는 것이 "
                        f"0건이다 (비정상 상태 {r['odd']}건) — 카드가 통째로 "
                        f"안 나갈 수 있다"))
    return out


#: `finals.STALE_AFTER_HOURS` 의 몇 배가 지나야 경보할 것인가. 정합 잡은
#  하루 한 번(13:00 KST) 도므로 **한 사이클은 지나고** 알린다 — 그 전에
#  울리면 "아직 정합 잡이 안 돌았다"를 결함으로 보고하는 셈이다.
STALE_ALERT_MULT = 4

#: 이미 알린 미확정 경기. **서 있는 더미를 다시 울리지 않기 위한 상태**다.
STALE_SEEN_KEY = "watchdog:stale-games:seen"
STALE_SEEN_TTL = 30 * 24 * 3600


async def check_stale_games(pool, redis) -> list[tuple[str, str, str]]:
    """(i) 🔴 **소스가 끝내 확정하지 않은 경기.** 유령 행을 드러낸다.

    실측 2026-09-07 (운영 DB, 24시간 문턱): `scheduled` 로 굳은 경기가
    **kbo 7(최장 1531h·63.8일) · npb 4(643h) · soccer 16(354h) = 27건**.
    워치독 어느 코드도 이것을 보지 않았다 — `W-GAME-INVISIBLE` 은 **앞으로
    6시간**만 보고, `W-CARD-LATE` 는 발송 창만 본다. 지난 경기는 아무의
    관할도 아니었다. 이 행들은 `final` 이 아니라서 자료12 elo·자료1 표본에서
    조용히 빠진다.

    🔴 **`reconcile_stale_games` 가 매일 집어가면서 "고쳤다 0" 으로 조용히
       끝난다.** 그 잡은 `ingest_finals` 를 부르는데 수집기는 소스가 `final`
       이라고 한 것만 반영하므로, 소스가 확정을 안 주면 영원히 비-final 이다.
       원인은 둘 다 소스 쪽이었다 — KBO 공식 소스가 10일 뒤에도 `scheduled`,
       NPB 야후는 `試合中止`(취소)인데 우리가 취소를 사후 반영하지 않는다.

    🔴 **서 있는 더미가 아니라 늘어난 것만 울린다.** 27건이 남아 있는 한
       상시 경보는 15분마다 영원히 울리고, 그러면 내일 슬레이트에서 정작
       봐야 할 `W-SEND-PENDING`·`W-CARD-LATE` 가 묻힌다. 코드가 답할 질문은
       "지금 유령이 몇 개냐"(→ `evidence/OPEN.md` #15 가 든다)가 아니라
       **"오늘 새로 안 끝난 경기가 있냐"** 다. 등록부가 할 일을 사이렌에
       시키지 않는다.
    ⚠️ 그래서 **첫 실행은 기준선만 심고 울리지 않는다.** 배포 직후 27건이
       한꺼번에 터지는 것이야말로 이 설계가 막으려는 것이다.
    ⚠️ 상태를 못 읽으면(Redis 부재·오류) **점검을 건너뛴다.** 기준선 없이
       울리면 그게 곧 27건 폭주다.

    ⚠️ **취소 계열은 뺀다.** 안 빼면 KBO 우천취소가 매일 오탐으로 뜬다
       (실측: 취소 미제외 시 kbo 53건 → 제외 시 7건, 오탐 46건 차단).
       반대 위험(정상 데이터를 경보로 태우는 것)이 이 필터의 값이다.
    ⚠️ 문턱은 `finals.STALE_AFTER_HOURS` 를 **원본으로 참조**한다 — 숫자를
       여기 베껴 적으면 원본이 바뀔 때 따라가지 않는다(사본 금지).
    """
    if pool is None or redis is None:
        return []
    from app.collectors.finals import STALE_AFTER_HOURS

    hours = STALE_AFTER_HOURS * STALE_ALERT_MULT
    try:
        rows = await pool.fetch(
            """SELECT id, sport, home, away,
                      round(extract(epoch FROM (now() - starts_at)) / 3600) AS hrs
                 FROM games
                WHERE status NOT IN ('final', 'cancelled', 'postponed', 'suspended')
                  AND starts_at < now() - make_interval(hours => $1)
                ORDER BY starts_at""", hours)
    except Exception as exc:
        logger.debug("[watchdog] 미확정 경기 조회 실패: %s", exc)
        return []

    cur = {str(r["id"]) for r in rows}
    try:
        raw = await redis.get(STALE_SEEN_KEY)
        await redis.set(STALE_SEEN_KEY, ",".join(sorted(cur)), ex=STALE_SEEN_TTL)
    except Exception as exc:
        logger.warning("[watchdog] 미확정 경기 상태 접근 실패 — 점검 생략: %s", exc)
        return []
    if raw is None:
        # 기준선을 심는 첫 실행. 서 있는 더미는 등록부의 몫이다.
        logger.info("[watchdog] 미확정 경기 기준선 %d건 기록 — 이번엔 알리지 않는다",
                    len(cur))
        return []
    if isinstance(raw, bytes):
        raw = raw.decode()
    prev = {x for x in str(raw).split(",") if x}
    fresh = [r for r in rows if str(r["id"]) not in prev]
    if not fresh:
        return []

    by_sport: dict[str, list] = {}
    for r in fresh:
        by_sport.setdefault(r["sport"], []).append(r)
    out: list[tuple[str, str, str]] = []
    for sport, gs in sorted(by_sport.items()):
        names = ", ".join(f"{g['away']}@{g['home']}" for g in gs[:3])
        out.append(("W-STALE-GAME", sport.upper(),
                    f"시작한 지 {hours}시간 넘게 종료로 확정되지 않은 경기가 "
                    f"{len(gs)}건 **새로** 생겼다 (최장 {int(max(g['hrs'] for g in gs))}"
                    f"시간) — 소스가 결과를 주지 않거나 취소가 반영되지 않았다: "
                    f"{names}"))
    return out


def _today(sport: str) -> str:
    """그 종목의 오늘 슬레이트 날짜. **원본은 파이프라인이다** — 여기서
    날짜 계산 규칙을 다시 쓰지 않는다(MLB 는 미국 동부 기준이라 다르다)."""
    from app.pipeline import mlb_slate_date, today_kst

    return mlb_slate_date() if (sport or "").lower() == "mlb" else today_kst()


async def check_source_drift(pool, redis) -> list[tuple[str, str, str]]:
    """[정찰 C5] 같은 슬레이트에서 **한 소스만** 비어 있으면 그 소스가 바뀐 것이다.

    🔴 왜 "전체가 0"이 아니라 "하나만 0"을 보는가.
       전체가 0 이면 시각(너무 이르다)이나 우리 쪽 고장이고, 그건 이미
       `W-CARD-LATE`·`W-STORE-DOWN` 이 본다. 반면 **다른 경기는 다 들어왔는데
       한 축만 비어 있으면** 그 소스의 페이지 구조·경로가 바뀐 것이다 —
       조용히 0 을 반환하는 파서가 제일 늦게 발견된다.

    ⚠️ 정찰 기록(`scout:…`)만 읽는다. 새 크롤도, 새 쿼리도 하지 않는다.
    ⚠️ 정찰 창 안이면서 **라인업 공시 시각을 지난** 경기만 센다 — 아직
       발표 전인 것을 고장이라 부르면 매일 저녁 오탐이 난다.
    """
    from app.engine.scout import scan_scout
    from app.registry import scout_sports

    out: list[tuple[str, str, str]] = []
    if redis is None:
        return out
    for sc in scout_sports():
        # 🔴 [오탐 수정 2026-09-06] **오늘 슬레이트만 본다.** 종전에는
        #    `scout:{sport}:*` 로 전 날짜를 긁었고, 기록 TTL 이 36시간이라
        #    **어제 경기가 오늘 판정에 섞였다.** 어제 경기는 시작 직전에
        #    관측돼 `hours_to_start` 가 작고, 그때 라인업이 없었으면 sides=0 —
        #    그래서 "전부 0"이 성립해 버린다.
        #    실사고 2026-09-05 16:01: KBO 5경기가 T-2.5h(공시 전)인데
        #    `W-SOURCE-DRIFT KBO/라인업` 이 울렸다. 베팅이 걸린 저녁이었다.
        #    ⚠️ 날짜는 키에 이미 있다 — 패턴에 넣으면 된다(사본 아님).
        recs = await scan_scout(redis, f"scout:{sc.sport}:*:{_today(sc.sport)}")
        # 라인업 공시 관행을 지난 경기만 (관행은 config 가 원본이다)
        due = [r for r in recs
               if (r.get("hours_to_start") or 99) <= _lineup_lead_h(sc.sport)]
        if len(due) < 2:                     # 표본이 1건이면 "하나만"이 성립 안 한다
            continue
        for axis, empty in (
            ("라인업", lambda r: (r.get("lineup") or {}).get("sides", 0) == 0),
            ("배당", lambda r: (r.get("market") or {}).get("rows", 0) == 0),
        ):
            n_empty = sum(1 for r in due if empty(r))
            if n_empty == len(due):
                out.append(("W-SOURCE-DRIFT", f"{sc.sport.upper()}/{axis}",
                            f"정찰 {len(due)}경기 전부 {axis} 0 — 소스가 바뀌었을 "
                            f"가능성이 높다(파서가 조용히 0을 반환)"))
    return out


def _lineup_lead_h(sport: str) -> float:
    """그 종목 라인업 공시 관행(시간).

    🔴 사본 금지 — `config.lineup_lead_{sport}` 가 원본이다. 여기 숫자를 적으면
       config 가 바뀔 때 따라가지 않는다(워치독 오탐 4건이 전부 그 실수였다).
    ⚠️ 없는 종목이면 **감시하지 않는다**(0 반환). 관행을 모르는데 "늦었다"고
       말할 수는 없다.
    """
    from app.config import get_settings

    return float(getattr(get_settings(), f"lineup_lead_{sport}", 0.0) or 0.0)


async def run_checks(pool, redis) -> list[tuple[str, str, str]]:
    """전 점검. 하나가 죽어도 나머지는 돈다 — 워치독이 눈을 감으면 안 된다."""
    found: list[tuple[str, str, str]] = []
    for name, coro in (
        ("store", check_store(pool, redis)),
        ("odds", check_odds(pool, redis)),
        ("llm", check_llm(redis)),
        ("jobs", check_jobs(redis)),
        ("sends", check_pending_sends(pool, redis)),
        ("card_late", check_card_late(pool, redis)),
        ("invisible", check_invisible_games(pool, redis)),
        ("source_drift", check_source_drift(pool, redis)),
        ("stale_games", check_stale_games(pool, redis)),
    ):
        try:
            found += await coro
        except Exception as exc:
            logger.warning("[watchdog] 점검 %s 실패: %s", name, exc)
    return found


async def run(pool, redis) -> int:
    """점검 후 경보. 반환은 걸린 건수."""
    from app.alerts import watchdog as alert

    found = await run_checks(pool, redis)
    for code, target, detail in found:
        logger.warning("[watchdog] %s %s — %s", code, target, detail)
        try:
            await alert(code, detail, target=target)
        except Exception as exc:
            logger.warning("[watchdog] 경보 실패 %s: %s", code, exc)
    if not found:
        logger.info("[watchdog] 이상 없음")
    return len(found)
