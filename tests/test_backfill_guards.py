"""[ELO-2] 백필의 안전장치 둘이 잘못 서 있다 — 배포 전 재검토에서 나왔다.

🔴 **① 중복 정의가 두 개다(사본).** `backfill._DUP_GROUPS` 는 아직
   `date_trunc('day', starts_at AT TIME ZONE 'UTC')` 로 센다. 그런데 GM-3 이
   병합을 **±2시간 창**으로 바꿨다. 그래서 백필 직후 이 가드는
   "중복 그룹이 0 → 262 로 늘었다, 다음 finals_job 이 병합한다"고 경고하는데
   **실제 병합은 0건**이다. 실측 2026-09-09 운영: 옛 정의 0그룹 · 새 정의
   0그룹이지만, 시즌 전체를 넣으면 옛 정의만 262개로 튄다(GM-3 커밋 실측).
   ⚠️ 이 저장소가 네 번 데인 병이다 — **손으로 옮겨 적은 정의는 원본이
      바뀔 때 따라가지 않는다.** 오탐이 잦으면 사람이 경고를 끄고, 꺼진
      가드는 없는 가드다.

🔴 **② status 역행 가드가 없다.** `ON CONFLICT ... SET status = EXCLUDED.status`
   에는 `COALESCE` 도 조건도 없다. 점수는 `COALESCE` 로 지켜 놓고 status 는
   안 지켰다. 오늘을 포함한 범위를 백필하면 이미 `final` 인 경기가 외부
   응답 한 번에 `scheduled` 로 되돌 수 있다. 운영 실측 2026-09-09: 최근 하루
   MLB 26경기 중 **final 10 · scheduled 16**, 전부 라인업 상태를 갖고 있다.
   `final` 이 풀리면 그 경기는 채점 대상에서 빠지고 카드 경로로 되돌아간다.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta


def _sched(games):
    return {"dates": [{"games": games}]}


def _g(pk, home, away, when, *, state="Final", hs=3, as_=1):
    return {
        "gamePk": pk,
        "gameDate": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": {"abstractGameState": state, "detailedState": state},
        "teams": {
            "home": {"team": {"name": home}, "score": hs},
            "away": {"team": {"name": away}, "score": as_},
        },
    }


async def test_중복_정의를_한_곳에서만_읽는다(db_pool):
    """🔴 백필의 가드와 실제 병합이 **같은 것**을 세야 한다."""
    from app.collectors import backfill
    from app.collectors.game_match import duplicate_group_count

    base = datetime(2026, 5, 1, 23, 5, tzinfo=UTC)
    # 금요일 야간(토 00:05 UTC)과 토요일 낮(토 18:05 UTC) — 같은 UTC 날짜,
    # 18시간 차. **다른 경기**이므로 어느 가드도 중복으로 세면 안 된다.
    sched = _sched([
        _g(1, "H팀", "A팀", base + timedelta(hours=1)),
        _g(2, "H팀", "A팀", base + timedelta(hours=19)),
    ])
    out = await backfill.backfill_mlb(db_pool, schedule=sched)
    assert out["loaded"] == 2
    assert out["dup_after"] == 0, (
        f"18시간 떨어진 두 경기를 중복으로 셌다 — 병합은 세지 않는다: {out}")
    assert await duplicate_group_count(db_pool, "mlb") == 0


async def test_백필이_final_을_되돌리지_않는다(db_pool):
    """🔴 점수는 COALESCE 로 지키면서 status 는 안 지켰다."""
    from app.collectors import backfill

    when = datetime(2026, 5, 1, 23, 5, tzinfo=UTC)
    await backfill.backfill_mlb(db_pool, schedule=_sched(
        [_g(7, "H팀", "A팀", when, state="Final", hs=5, as_=2)]))
    row = await db_pool.fetchrow(
        "SELECT status, home_score FROM games WHERE sport='mlb' AND ext_id=$1",
        str(7))
    assert row["status"] == "final" and row["home_score"] == 5

    # 같은 경기를 외부가 다시 'Preview' 로 준다 (일정 재공시·응답 오류)
    await backfill.backfill_mlb(db_pool, schedule=_sched(
        [_g(7, "H팀", "A팀", when, state="Preview", hs=None, as_=None)]))
    row2 = await db_pool.fetchrow(
        "SELECT status, home_score FROM games WHERE sport='mlb' AND ext_id=$1",
        str(7))
    assert row2["status"] == "final", "종료된 경기가 예정으로 되돌아갔다"
    assert row2["home_score"] == 5, "점수가 사라졌다"


async def test_진짜_중복은_여전히_센다(db_pool):
    """⚠️ 반대 위험 — 가드를 고치면서 진짜 중복을 놓치면 안 된다."""
    from app.collectors.game_match import duplicate_group_count

    base = datetime(2026, 5, 1, 23, 5, tzinfo=UTC)
    for k, off in enumerate((0, 10)):        # 10분 차 = 같은 경기가 두 행
        await db_pool.execute(
            "INSERT INTO games (sport, league, ext_id, starts_at, home, away, status)"
            " VALUES ('mlb','MLB',$1,$2,'H팀','A팀','final')",
            f"dup{k}", base + timedelta(minutes=off))
    assert await duplicate_group_count(db_pool, "mlb") == 1
