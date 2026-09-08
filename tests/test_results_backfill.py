"""[ELO-1] 리그 전체 경기 결과 적재 — 자료12(실력 레이팅)를 실력으로 만든다.

🔴 왜 필요한가 (실측 2026-09-08):
   `games` 표는 **리그 이력이 아니라 봇이 건드린 경기만** 갖고 있었다.
     mlb 357경기 / 2년  (실제 MLB 는 시즌당 2,430경기)
     kbo 224경기 / 3개월 · npb 154경기 / 1개월
   `app/models/team_elo.py` 가 "원천은 우리 `games` 테이블뿐"이라고 적어 두었다.
   그래서 자료12 는 팀당 13~24경기로 계산됐고, 재구성 Elo 의 AUC 가 **0.449** 였다.

   statsapi 로 2025~2026 정규시즌 4,593경기를 리플레이해 다시 재니
   **AUC 0.558**(평가 2,756경기, K=4~8·HFA 0~50 안정, 브라이어 0.2464~0.2484).
   **+0.109.** 적재의 값어치가 실측으로 확인됐다.
   ⚠️ 같은 표본에서 우리 LLM 판정은 0.470~0.519 · 브라이어 0.2530 —
      **단순 Elo보다 못하다.**

⚠️ **`apply_result`(경기 자체로 찾기)를 쓰면 안 된다.** 그것은 시각 근접
   ±20시간으로 찾는데, 야구는 3연전이라 **야간→주간 경기(18시간 차)나
   더블헤더가 같은 창에 걸린다.** 전 시즌을 넣으면 엉뚱한 경기의 스코어를
   덮어쓸 수 있다. MLB 는 `ext_id` 가 gamePk 그 자체라 **정확한 유니크 키**이므로
   `ON CONFLICT (sport, ext_id)` 로 넣는다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _sched(*games):
    """statsapi `/schedule` 범위 응답 모양."""
    return {"dates": [{"date": "2026-04-01", "games": list(games)}]}


def _g(pk, home, away, hs=None, as_=None, state="Final"):
    return {
        "gamePk": pk, "gameDate": "2026-04-01T23:05:00Z",
        "officialDate": "2026-04-01",
        "status": {"abstractGameState": state},
        "teams": {"home": {"team": {"name": home}, "score": hs},
                  "away": {"team": {"name": away}, "score": as_}},
    }


@pytest.mark.asyncio
async def test_범위_일정을_적재한다(db_pool):
    from app.collectors.backfill import backfill_mlb

    out = await backfill_mlb(db_pool, schedule=_sched(
        _g(1001, "Los Angeles Dodgers", "San Diego Padres", 5, 3),
        _g(1002, "New York Yankees", "Boston Red Sox", 2, 7)))
    assert out["loaded"] == 2, out
    n = await db_pool.fetchval("SELECT count(*) FROM games WHERE sport='mlb'")
    assert n == 2


@pytest.mark.asyncio
async def test_두_번_돌려도_행이_늘지_않는다(db_pool):
    """⚠️ 백필은 몇 번이고 다시 돌 수 있어야 한다."""
    from app.collectors.backfill import backfill_mlb

    s = _sched(_g(2001, "Chicago Cubs", "St. Louis Cardinals", 4, 1))
    await backfill_mlb(db_pool, schedule=s)
    await backfill_mlb(db_pool, schedule=s)
    assert await db_pool.fetchval("SELECT count(*) FROM games WHERE sport='mlb'") == 1


@pytest.mark.asyncio
async def test_기존_행의_라인업과_선발을_덮지_않는다(db_pool):
    """🔴 반대 위험 — 백필이 오늘 경기의 라인업 상태를 되돌리면 카드가 죽는다."""
    from app.collectors.backfill import backfill_mlb

    await db_pool.execute(
        """INSERT INTO games (sport, league, ext_id, starts_at, home, away,
                              status, lineup_status, home_pitcher, away_pitcher)
           VALUES ('mlb','MLB','3001','2026-04-01T23:05:00Z','Athletics','Seattle Mariners',
                   'scheduled','confirmed','Luis Severino','Logan Gilbert')""")
    await backfill_mlb(db_pool, schedule=_sched(
        _g(3001, "Athletics", "Seattle Mariners", 6, 2)))
    row = await db_pool.fetchrow(
        "SELECT lineup_status, home_pitcher, home_score, status FROM games WHERE ext_id='3001'")
    assert row["lineup_status"] == "confirmed", "라인업 상태가 되돌아갔다"
    assert row["home_pitcher"] == "Luis Severino", "선발이 지워졌다"
    assert row["home_score"] == 6 and row["status"] == "final", "스코어는 들어와야 한다"


@pytest.mark.asyncio
async def test_미종료_경기는_스코어_없이_들어간다(db_pool):
    from app.collectors.backfill import backfill_mlb

    await backfill_mlb(db_pool, schedule=_sched(
        _g(4001, "Texas Rangers", "Houston Astros", state="Preview")))
    row = await db_pool.fetchrow("SELECT status, home_score FROM games WHERE ext_id='4001'")
    assert row["status"] == "scheduled" and row["home_score"] is None


@pytest.mark.asyncio
async def test_18시간_차_같은_대진을_한_경기로_합치지_않는다(db_pool):
    """🔴 야구는 3연전이다. 야간 경기와 다음 날 주간 경기가 18시간 차인 일이 흔하다.

    `apply_result` 는 시각 근접 ±20시간으로 찾으므로 그 둘을 **같은 경기로 본다.**
    백필이 그 방식을 쓰면 엉뚱한 경기의 스코어를 덮어쓴다.
    ⚠️ 소스 문자열로 재지 않는다 — 독스트링이 그 이름을 설명에 쓰기 때문이다.
       **실제로 넣어 보고 두 행인지 본다.**
    """
    from app.collectors.backfill import backfill_mlb

    night = _g(5001, "Baltimore Orioles", "Tampa Bay Rays", 3, 1)
    night["gameDate"] = "2026-04-01T23:05:00Z"
    day = _g(5002, "Baltimore Orioles", "Tampa Bay Rays", 8, 0)
    day["gameDate"] = "2026-04-02T17:05:00Z"          # 18시간 뒤
    await backfill_mlb(db_pool, schedule=_sched(night, day))

    rows = await db_pool.fetch(
        "SELECT ext_id, home_score FROM games WHERE sport='mlb' ORDER BY ext_id")
    assert len(rows) == 2, f"18시간 차 두 경기가 한 행으로 합쳐졌다: {rows}"
    assert [r["home_score"] for r in rows] == [3, 8], "스코어가 서로 덮어썼다"


@pytest.mark.asyncio
async def test_중복_그룹이_늘면_반환값이_알려준다(db_pool):
    """⚠️ 늘어난 중복은 다음 13:00 finals_job 이 병합하고, 병합은 되돌릴 수 없다.

    조용히 넘기지 않는다 — 전후 수를 세어 반환한다.
    """
    from app.collectors.backfill import backfill_mlb

    out = await backfill_mlb(db_pool, schedule=_sched(
        _g(6001, "New York Mets", "Atlanta Braves", 1, 0)))
    assert "dup_before" in out and "dup_after" in out
    assert out["dup_after"] == out["dup_before"], out
