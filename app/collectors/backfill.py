"""[ELO-1] 리그 전체 경기 결과 적재 — 자료12(실력 레이팅)를 실력으로 만든다.

🔴 **왜 필요한가 (실측 2026-09-08).** `games` 표는 리그 이력이 아니라
   **봇이 건드린 경기만** 갖고 있었다:
     mlb 357경기 / 2년   (실제 MLB 는 시즌당 2,430경기)
     kbo 224경기 / 3개월 · npb 154경기 / 1개월
   `app/models/team_elo.py` 가 스스로 적어 두었다 —
   "원천은 우리 `games` 테이블뿐이다. 외부 API 를 부르지 않는다."
   그래서 자료12 는 팀당 13~24경기로 계산됐다.

   statsapi 로 2025~2026 정규시즌 4,593경기를 받아 Elo 를 리플레이하고
   번인 40% 뒤 **2,756경기**로 평가하니:
       조각 이력 Elo   AUC 0.449~0.473
       전 시즌  Elo   AUC **0.558**  (K=4~8 · HFA 0~50 에서 안정)
                      브라이어 0.2464~0.2484 (항상 0.5 로 찍으면 0.2500)
   **+0.109.** 적재의 값어치가 실측으로 확인됐다.
   ⚠️ 같은 표본에서 우리 LLM 판정은 AUC 0.470~0.519 · 브라이어 0.2530 —
      **단순 Elo보다 못하다.** 그것이 이 모듈을 만드는 이유다.
   ⚠️ 다만 Elo 만으로 목표(58~60%)에 닿지는 않는다. 0.558 은 정확도 55~56% 다.
      시장이 0.654(≈61%)이고 그것이 MODEL.md 가 인용한 학계 최고 61.77% 와
      맞물린다. **Elo 는 필요조건이지 충분조건이 아니다.**

🔴 **`apply_result` 를 쓰지 않는다.** 그 함수는 경기를 **시각 근접
   (±`MATCH_WINDOW_HOURS`=20시간)** 으로 찾는다. 야구는 3연전이라 야간 경기와
   다음 날 주간 경기가 18시간 차인 일이 흔하고, 더블헤더는 같은 날이다.
   전 시즌을 그 방식으로 넣으면 **엉뚱한 경기의 스코어를 덮어쓴다.**
   MLB 는 `ext_id` 가 gamePk 그 자체라 정확한 유니크 키이므로
   `ON CONFLICT (sport, ext_id)` 만 쓴다.

⚠️ **KBO·NPB 는 아직 하지 않는다.** NPB 는 `yahoo:{game_id}` 로 규약이 같아
   확장할 수 있지만, KBO 는 합성 `ext_id`(`kbo:날짜:시각:원정:홈`)와 공식
   G_ID(`20260901LGOB0`)의 규약이 달라 **정합을 먼저 정해야 한다**(GM-3 영역).
   규약이 다른 채로 넣으면 같은 경기가 두 행이 된다.

⚠️ **기존 행을 되돌리지 않는다.** `lineup_status`·선발·`lineup_confirmed_at` 은
   건드리지 않고 status·스코어만 채운다. 오늘 경기의 라인업 상태가 백필로
   되돌아가면 카드가 죽는다.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 🔴 파싱을 여기 다시 적지 않는다 — `mlb._parse_games` 가 원본이다.
#   적재 SQL 도 `mlb.upsert_games` 와 같은 형태를 쓴다(사본 금지).
_UPSERT = """
    INSERT INTO games (sport, league, ext_id, starts_at, home, away,
                       status, home_score, away_score)
    VALUES ('mlb', 'MLB', $1, $2, $3, $4, $5, $6, $7)
    ON CONFLICT (sport, ext_id) DO UPDATE SET
        -- 🔴 [ELO-2] **종료를 되돌리지 않는다.** 점수는 COALESCE 로 지켜
        --    놓고 status 는 안 지켰다. 외부가 한 번 'Preview' 를 주면 이미
        --    final 인 경기가 예정으로 돌아가고, 그 경기는 채점에서 빠진 채
        --    카드 경로로 되돌아간다.
        status = CASE WHEN games.status = 'final' THEN games.status
                      ELSE EXCLUDED.status END,
        home_score = COALESCE(EXCLUDED.home_score, games.home_score),
        away_score = COALESCE(EXCLUDED.away_score, games.away_score),
        updated_at = now()
"""

#: 🔴 [ELO-2 2026-09-09] 중복 그룹 수는 **`game_match` 에서 읽는다.**
#   종전에는 여기 같은 뜻의 쿼리를 손으로 적어 뒀고, GM-3 이 병합 창을
#   UTC 날짜 → ±2시간으로 바꿀 때 **이쪽은 따라오지 않았다.** 그래서 이
#   가드가 병합이 하지도 않을 일을 경고했다 — 시즌 백필 직후 "262개 늘었다"
#   인데 실제 병합은 0건. 오탐이 잦으면 사람이 경고를 끄고, 꺼진 가드는
#   없는 가드다.


async def backfill_mlb(pool, *, start: str | None = None, end: str | None = None,
                       client=None, schedule: dict | None = None) -> dict:
    """MLB 일정·결과를 `games` 에 적재한다. 반환 `{loaded, finals, dup_before, dup_after}`.

    `schedule` 을 주면 그것을 쓰고(테스트·재사용), 없으면 `start~end` 를 받는다.
    statsapi `/schedule` 은 인증이 없고 시즌 전체를 한 번에 준다
    (실측 2026-09-08: 2026-03-01~09-08 → 2,208경기 · 종료 2,164).

    ⚠️ **멱등하다.** 같은 범위를 몇 번 돌려도 행이 늘지 않는다.
    """
    from app.collectors.mlb import MLBClient, _parse_games

    if schedule is None:
        if not (start and end):
            raise ValueError("schedule 이 없으면 start·end 가 필요하다")
        schedule = await (client or MLBClient()).fetch_schedule_range(start, end)

    from app.collectors.game_match import duplicate_group_count

    dup_before = await duplicate_group_count(pool, "mlb")
    games = _parse_games(schedule)
    finals = 0
    for g in games:
        await pool.execute(_UPSERT, g["ext_id"], g["starts_at"], g["home"], g["away"],
                           g["status"], g["home_score"], g["away_score"])
        if g["status"] == "final":
            finals += 1
    dup_after = await duplicate_group_count(pool, "mlb")

    out = {"loaded": len(games), "finals": finals,
           "dup_before": int(dup_before), "dup_after": int(dup_after)}
    if out["dup_after"] > out["dup_before"]:
        # 🔴 조용히 넘기지 않는다. 늘어난 중복은 다음 13:00 `finals_job` 이
        #    병합하고, 그 병합은 되돌릴 수 없다.
        logger.warning("[backfill] 🔴 MLB 중복 그룹이 늘었다 %d → %d — "
                       "다음 finals_job 이 병합한다. 확인이 필요하다",
                       out["dup_before"], out["dup_after"])
    logger.info("[backfill] MLB %d경기 적재(종료 %d) · 중복 그룹 %d → %d",
                out["loaded"], out["finals"], out["dup_before"], out["dup_after"])
    return out
