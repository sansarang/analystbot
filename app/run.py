"""오케스트레이터 — v4 STEP 0~1 만 남았다.

🔴 **v4 단계 1(폐기 코드 제거)에서 판정 경로를 걷어냈다.** 종전 이 파일은
   `build_lean` → `build_counters` → `apply_counters` → `decide` → `grade` →
   `evaluate_triggers` → `regrade` 를 돌렸다. v4 §8 이 그 전부를 폐기했다.

🔴 **v4 는 승자를 고르지 않는다. 자리를 고른다**(§0). 지금 이 파일이 하는 일은
   **변수의 재료를 모으는 것**까지다:

| v4 STEP | 어디 | 언제 |
|---|---|---|
| 0 슬레이트·보드 | `sources.DbSources.slate` | 있음 |
| 1 변수 수집 | `collect.ingest` + 아래 `collect_game` | 재료까지 있음 |
| 2 전제 재검증 | ★ 단계 5 | 없음 |
| 3 반대 방향 변수 | ★ 단계 5 | 없음 |
| 4 자료 충분성 | ★ 단계 6 | 없음 |
| 5 시나리오 | ★ 단계 6 | 없음 |
| 6 생존·결론 | ★ 단계 7 | 없음 |
| 7 카드 | ★ 단계 8 | 임시 나열만 |
| 8 명단 재실행·채점 | ★ 단계 8 | 없음 |

⚠️ **그 칸들이 비어 있는 것이 지금 맞다**(v4 §0 절대 전제: 딥서치 세포망이 §9
   게이트를 통과하기 전에는 시나리오 엔진을 한 줄도 짓지 않는다).

🔴 **어느 단계에서 자료가 없어도 멈추지 않는다**(§2). 못 잰 칸은 **이름으로**
   남긴다 — 조용히 빼면 카드가 실제보다 근거가 많아 보인다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from app import timefmt
from app import card as card_mod
from app import judge as J
from app.llm import Budget

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))


@dataclass
class GameCtx:
    """경기 하나가 STEP 0~1 을 도는 동안 쌓이는 것.

    ⚠️ 종전에 있던 `motive`·`hyp`·`verdict`·`grade` 칸은 **삭제됐다**(v4 §8).
       그 자리에 들어갈 것은 `variables[]`·`scenarios[]`·`survival[]` 이고
       단계 2 에서 타입으로 세운다.
    """

    game_id: int
    league: str
    sport: str
    home: str
    away: str
    venue: str | None
    starts_kst: datetime
    status: str = "scheduled"
    score: str | None = None
    round_note: str | None = None

    absences: list[J.Absence] = field(default_factory=list)
    starters: dict[str, J.Starter] = field(default_factory=dict)
    intents: list[J.Intent] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)

    steps_done: list[int] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    budget: Budget = field(default_factory=Budget)

    def done(self, step: int) -> None:
        if step not in self.steps_done:
            self.steps_done.append(step)

    def unknown(self, what: str) -> None:
        """🔴 못 잰 칸은 **이름을 적어** 남긴다. 개수만 세면 되짚을 수 없다."""
        if what not in self.unknowns:
            self.unknowns.append(what)
            logger.info("[run] game=%s 미확인: %s", self.game_id, what)


class Sources:
    """자료 공급자. 🔴 **흐름은 어디서 왔는지 모른다** — 종목이 늘어도 안 고친다.

    각 메서드는 못 구하면 **빈 값을 돌려주고 예외를 내지 않는다**(§2) —
    멈추면 카드가 0건이 된다.
    """

    async def slate(self, day: date, leagues: list[str]) -> list[GameCtx]:
        return []

    async def absences(self, g: GameCtx) -> list[J.Absence]:
        return []

    async def starters(self, g: GameCtx) -> dict[str, J.Starter]:
        return {}

    async def intents(self, g: GameCtx) -> list[J.Intent]:
        return []


async def collect_game(g: GameCtx, src: Sources) -> GameCtx:
    """v4 STEP 1 의 재료 수집. 🔴 **판정하지 않는다.**

    종전 이름은 `run_game` 이었고 STEP 1~7 을 돌렸다. 지금은 모으는 것까지다.
    """
    g.done(0)

    # 🔴 진행 중·종료 경기는 분석 대상이 아니다(v3 §2 유지). 시작 후엔 손대지 않는다.
    if g.status in ("inprogress", "final", "postponed"):
        return g

    g.absences = await src.absences(g)
    if not g.absences:
        g.unknown("결장")

    g.starters = await src.starters(g)
    for side in ("home", "away"):
        st = g.starters.get(side)
        if not st or not st.known:
            g.unknown(f"{side} 선발")
            g.starters.setdefault(side, J.Starter(side))
        elif not st.recent:
            g.unknown(f"{side} 선발 최근 창")

    g.intents = await src.intents(g)
    if not g.intents:
        g.unknown("감독 의도")

    g.done(1)
    return g


async def collect_slate(day: date, leagues: list[str], src: Sources
                        ) -> tuple[str, list[GameCtx]]:
    """슬레이트 하나 → 수집 결과 나열 + 경기 맥락들.

    ⚠️ **결론 줄이 없다.** "낸다/소액/없음"은 v4 STEP 6 생존 계산의 산출이고
       단계 7 에서 짓는다. 지금 그 줄을 만들면 근거 없이 이름을 적는 것이다
       (v4 §12 가 금지하는 바로 그것).
    """
    games = await src.slate(day, leagues)
    bodies: list[str] = []
    for i, g in enumerate(games, 1):
        g = await collect_game(g, src)
        bodies.append(card_mod.render_collected(
            home=g.home, away=g.away, venue=g.venue,
            kst=kst_label(g.starts_kst), status=g.status,
            absences=g.absences, starters=g.starters, intents=g.intents,
            facts=g.facts, unknowns=g.unknowns, score=g.score, idx=i))
    return card_mod.render_slate(bodies, n_games=len(games)), games


def kst_label(when: datetime) -> str:
    """🔴 **사용자에게 보이는 것은 KST 다.** DB 는 UTC 저장, 표시만 KST.

    실측 2026-09-27: `timestamptz` 를 그대로 `strftime` 하면 asyncpg 가 UTC 로
    돌려주므로 18:05 경기가 **09:05** 로 찍혔다.

    🔴 **변환은 `app/timefmt.py` 하나다** — 여기 다시 적지 않는다. 실측 2026-10-03:
       이 함수가 있는데도 새 코드 둘(`analyze`·`findgame`)이 같은 결함을 다시 냈다.
       ⚠️ 이 꼴(`%m/%d`)은 스케줄러 카드가 쓰던 것이라 그대로 둔다.
    """
    return timefmt.kst_label(when, fmt="%m/%d %H:%M")
