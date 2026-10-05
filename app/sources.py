"""자료 공급 — DB 에 있는 것을 흐름에 넘긴다.

🔴 **v4 단계 1(폐기 코드 제거)에서 동기 계산과 판정 적재를 지웠다.**
   종전 `motivation()` 은 순위표로 §3 동기 4등급을 계산했고, `persist()` 는
   `motivation`·`hypotheses`·`counters`·`verdicts`·`grades`·`triggers` 에 적었다.
   v4 §8 이 그 전부를 폐기했다. 그 자리에 들어갈 것은 `variables`·`scenarios`·
   `survival`·`ledger` 이고 **단계 2 에서 표로 세운다.**

🔴 **흐름은 어디서 왔는지 모른다**(§모든 종목). 수집기가 표를 채우고, 이 파일이
   그것을 읽어 `GameCtx` 로 만든다. 종목이 늘어도 흐름을 고치지 않는다.
🔴 **못 구하면 빈 값을 돌려주고 예외를 내지 않는다**(§1) — 멈추면 카드가 0건이
   된다.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from app import judge as J
from app.run import GameCtx, Sources

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

_SLATE = """
SELECT id, league, sport, home, away, venue, starts_kst, status,
       home_score, away_score, round_note
  FROM games
 WHERE starts_kst >= $1::date
   AND starts_kst <  $1::date + INTERVAL '1 day'
   AND ($2::text[] IS NULL OR league = ANY($2))
 ORDER BY starts_kst, id
"""


class DbSources(Sources):
    """운영 경로. 🔴 **종목 필터가 없다** — 종목별 분기는 노드 안에서만 한다."""

    def __init__(self, pool):
        self.pool = pool

    async def slate(self, day: date, leagues: list[str] | None
                    ) -> list[GameCtx]:
        """STEP 0 — 🔴 **요청받은 날짜·리그만**(§14-9)."""
        rows = await self.pool.fetch(_SLATE, day, leagues or None)
        out: list[GameCtx] = []
        for r in rows:
            score = None
            if r["home_score"] is not None and r["away_score"] is not None:
                score = f"{r['away_score']}-{r['home_score']}"
            out.append(GameCtx(
                game_id=int(r["id"]), league=r["league"], sport=r["sport"],
                home=r["home"], away=r["away"], venue=r["venue"],
                starts_kst=r["starts_kst"], status=r["status"], score=score,
                round_note=r["round_note"]))
        logger.info("[slate] %s %s → %d경기", day, leagues or "전부", len(out))
        return out

    async def absences(self, g: GameCtx) -> list[J.Absence]:
        """STEP 2 — 열린 원장에서 오늘 유효한 것만(§4)."""
        rows = await self.pool.fetch(
            "SELECT team, player_name, player_id, basis, line, confidence, "
            "       replacement, source_url "
            "  FROM absences "
            " WHERE league = $1 AND team = ANY($2) AND resolved_at IS NULL "
            "   AND (until_expected IS NULL OR until_expected >= $3::date)",
            g.league, [g.home, g.away], g.starts_kst.date())
        out: list[J.Absence] = []
        for r in rows:
            side = "home" if r["team"] == g.home else "away"
            try:
                out.append(J.Absence(
                    side=side, player_name=r["player_name"], basis=r["basis"],
                    line=r["line"], confidence=r["confidence"],
                    player_id=r["player_id"], replacement=r["replacement"],
                    source_url=r["source_url"]))
            except ValueError as exc:
                # 🔴 조용히 버리지 않는다 — 원장에 잘못 든 행을 알아야 고친다
                logger.warning("[absence] game=%s 버렸다: %s", g.game_id, exc)
        return out

    async def starters(self, g: GameCtx) -> dict[str, J.Starter]:
        """STEP 3 — 🔴 **최근 창만** 판정 입력이다(§5). 시즌 누적은 여기 없다."""
        rows = await self.pool.fetch(
            "SELECT side, name, status, recent, vs_opponent, flags "
            "  FROM starters WHERE game_id = $1", g.game_id)
        out: dict[str, J.Starter] = {}
        for r in rows:
            out[r["side"]] = J.Starter(
                side=r["side"], name=r["name"], status=r["status"],
                recent=list(r["recent"] or []),
                vs_opponent=r["vs_opponent"],
                flags=list(r["flags"] or []))
        return out

    async def intents(self, g: GameCtx) -> list[J.Intent]:
        """STEP 4 — 🔴 인용이 본문에 실재할 때만 hard(§6 · §12-c-6)."""
        rows = await self.pool.fetch(
            "SELECT side, type, quote, speaker, hardness "
            "  FROM intent WHERE game_id = $1", g.game_id)
        return [J.Intent(side=r["side"], type=r["type"], quote=r["quote"],
                         speaker=r["speaker"], hardness=r["hardness"])
                for r in rows]


async def persist(pool, g: GameCtx) -> None:
    """수집 결과를 원장에 남긴다 — 지금은 **실행 추적뿐**이다.

    🔴 **판정 적재가 없다.** `verdicts`·`grades`·`triggers` 는 v4 §8 폐기고,
       `variables`·`scenarios`·`survival` 은 단계 2 에서 표로 세운다.
    🔴 `runs.unknowns` 에 **못 잰 칸의 이름**을 적는다(§2). 개수만 세면 되짚을
       수 없다.
    """
    await pool.execute(
        "INSERT INTO runs (game_id, slate_date, steps_done, unknowns, "
        "llm_calls, finished_at) VALUES ($1,$2,$3,$4,$5,now())",
        g.game_id, g.starts_kst.date(), g.steps_done, g.unknowns,
        g.budget.used)


# 🔴 `score_finals` 는 삭제했다 — v3 채점(승자 적중)이었고 v4 §8 이 폐기했다.
#    v4 STEP 8 채점은 "어느 시나리오가 실현됐는지 · 못 찾은 변수가 있었는지"이고
#    **단계 8** 에서 짓는다(§3 STEP 8 → `ledger`).
