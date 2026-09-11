"""[시장 기준선 C1] 우리 판정 vs 시장 — **사후 전용, 게이트 아님.**

🔴 이번 구현은 계산·표기·채점뿐이다. "시장 동의 → 추천 강등"은 게이트
   변경이라 동결 대상이고 v1.4 후보로만 예약한다. 이 파일이 그 경계를 잠근다.
"""
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.engine import market_baseline as MB

SRC = Path("app/engine/market_baseline.py").read_text(encoding="utf-8")
NOW = datetime.now(UTC)


# ═════════ 1. de-vig — 실배당 표본 ═════════

def test_devig_with_real_odds():
    """어제 실배당(LAD 1.32 / STL 3.42, espn/draftkings).

    1/1.32=0.7576 · 1/3.42=0.2924 · 합 1.0500 → 0.7576/1.0500 = **0.7215**.
    ⚠️ 지시서의 "≈0.715" 는 어림값이고 정확값은 0.7215 다.
       마진(5.0%)을 빼지 않으면 0.7576 으로 5.6%p 부푼다.
    """
    assert MB.devig_two_way(1.32, 3.42) == 0.7215
    assert MB.devig_two_way(1.32, 3.42) < 1.0 / 1.32   # 마진이 실제로 빠졌다


def test_devig_guards():
    for bad in ((None, 2.0), (1.32, None), (1.0, 3.42), (1.01, 3.42),
                ("x", 2.0), (0.5, 2.0)):
        assert MB.devig_two_way(*bad) is None, bad


def test_devig_symmetry():
    p = MB.devig_two_way(2.0, 2.0)
    assert p == 0.5


# ═════════ 2. 시장 우세 · even ═════════

def test_even_band():
    assert MB.favored_of(0.505) == MB.EVEN
    assert MB.favored_of(0.495) == MB.EVEN
    assert MB.favored_of(0.511) == "home"
    assert MB.favored_of(0.489) == "away"
    assert MB.favored_of(None) is None


# ═════════ 3. 기준 스냅샷 — 나이·결측·팀명 ═════════

class Pool:
    def __init__(self, rows=None, our_hit=None):
        self._rows = rows or []
        self._our_hit = our_hit
        self.updates = []

    async def fetch(self, sql, *a):
        return self._rows

    async def fetchval(self, sql, *a):
        return self._our_hit

    async def execute(self, sql, *a):
        self.updates.append(a)


def _row(side, odds, age_min):
    return {"side": side, "odds": odds,
            "captured_at": NOW - timedelta(minutes=age_min)}


GAME = {"id": 1, "sport": "mlb", "home": "Los Angeles Dodgers",
        "away": "St. Louis Cardinals", "starts_at": NOW + timedelta(hours=1)}


@pytest.mark.asyncio
async def test_fresh_snapshot_is_used():
    pool = Pool([_row("Los Angeles Dodgers", 1.32, 10),
                 _row("St. Louis Cardinals", 3.42, 10)])
    out = await MB.p_market(pool, GAME, purpose=MB.SEND)
    assert out["p"] == 0.7215 and out["reason"] is None
    # ⚠️ **정확히 10.0 을 요구하지 마라.** `NOW` 는 모듈 임포트 시각이고
    #    `p_market` 은 호출 시각을 쓴다 — 스위트가 길어지면 그 차이만큼
    #    나이가 늘어난다. 단독 실행은 통과하고 전체 실행은 깨진다.
    #    (오늘 세 번째 시간 의존 테스트 실수다 → ENGINEERING §3)
    assert 10.0 <= out["age_min"] < 90.0


@pytest.mark.asyncio
async def test_stale_snapshot_is_refused_for_the_card():
    """🔴 오래된 배당은 **지금 시장이 아니다.** 상한은 config 가 원본."""
    from app.config import get_settings

    assert get_settings().market_snapshot_max_age_min == 90
    pool = Pool([_row("Los Angeles Dodgers", 1.32, 91),
                 _row("St. Louis Cardinals", 3.42, 91)])
    out = await MB.p_market(pool, GAME, purpose=MB.SEND)
    assert out["p"] is None and out["reason"] == "stale"


@pytest.mark.asyncio
async def test_close_purpose_has_no_age_limit():
    """마감 근사치는 오래돼도 그게 마감이다."""
    pool = Pool([_row("Los Angeles Dodgers", 1.32, 500),
                 _row("St. Louis Cardinals", 3.42, 500)])
    out = await MB.p_market(pool, GAME, purpose=MB.CLOSE)
    assert out["p"] == 0.7215 and out["reason"] is None


@pytest.mark.asyncio
async def test_missing_side_is_refused():
    pool = Pool([_row("Los Angeles Dodgers", 1.32, 5)])
    out = await MB.p_market(pool, GAME)
    assert out["p"] is None and out["reason"] == "no_snapshot"


@pytest.mark.asyncio
async def test_bad_odds_is_refused():
    pool = Pool([_row("Los Angeles Dodgers", 1.00, 5),
                 _row("St. Louis Cardinals", 3.42, 5)])
    out = await MB.p_market(pool, GAME)
    assert out["p"] is None and out["reason"] == "bad_odds"


def test_provider_comes_from_the_registry():
    """담당 provider 는 레지스트리가 원본 — 우선순위를 손으로 적지 않는다."""
    assert "from app.registry import active_providers" in SRC
    assert MB.provider_for("mlb") in ("espn", "sharp", None)
    assert MB.provider_for("nonexistent") is None


# ═════════ 4. 채점 — void · our_hit 복사 ═════════

def _pending(status="final", h=5, a=3):
    return [{"id": 9, "game_id": 1, "sport": "mlb", "home": "H", "away": "A",
             "starts_at": NOW - timedelta(hours=3), "status": status,
             "home_score": h, "away_score": a}]


@pytest.mark.asyncio
async def test_draw_is_void_and_market_hit_null(monkeypatch):
    pool = Pool(_pending(h=4, a=4), our_hit=None)

    async def fake_p(_pool, _g, purpose=MB.SEND):
        return {"p": 0.62, "provider": "oddsportal", "age_min": 5, "reason": None}

    monkeypatch.setattr(MB, "p_market", fake_p)
    out = await MB.grade(pool)
    assert out == {"graded": 1, "void": 1}
    # UPDATE 인자 순서: (id, p_close, fav, market_hit, our_hit, void)
    args = pool.updates[0]
    assert args[3] is None            # market_hit — 무승부는 비교 불가
    assert args[5] is True            # void


@pytest.mark.asyncio
async def test_market_hit_is_computed_from_close(monkeypatch):
    pool = Pool(_pending(h=5, a=3), our_hit=True)

    async def fake_p(_pool, _g, purpose=MB.SEND):
        return {"p": 0.62, "provider": "oddsportal", "age_min": 5, "reason": None}

    monkeypatch.setattr(MB, "p_market", fake_p)
    await MB.grade(pool)
    args = pool.updates[0]
    assert args[1] == 0.62 and args[2] == "home"
    assert args[3] is True            # 시장이 홈 우세, 홈 승 → 적중
    assert args[4] is True            # our_hit 복사


@pytest.mark.asyncio
async def test_our_hit_is_copied_never_recomputed():
    """🔴 재계산하면 두 숫자가 어긋난다 — 원본은 `pick_ledger` 다."""
    assert "SELECT hit FROM pick_ledger" in SRC
    assert "predicted_side" not in SRC, "우리 적중을 다시 계산하고 있다"


@pytest.mark.asyncio
async def test_even_market_gives_null_hit(monkeypatch):
    pool = Pool(_pending(), our_hit=True)

    async def fake_p(_pool, _g, purpose=MB.SEND):
        return {"p": 0.502, "provider": "espn", "age_min": 3, "reason": None}

    monkeypatch.setattr(MB, "p_market", fake_p)
    await MB.grade(pool)
    args = pool.updates[0]
    assert args[2] == MB.EVEN and args[3] is None


# ═════════ 5. 동결 정합 — 게이트가 아니다 ═════════

def test_this_layer_is_not_a_gate():
    """🔴 게이트는 동결 대상이다. 이 모듈은 게이트 판정을 만들지 않는다."""
    for banned in ("gate_result", "GATE_RECOMMENDED", "qualifies",
                   "judge_confidence =", "demote"):
        assert banned not in SRC, f"{banned} — 게이트를 건드린다"


def test_grading_reuses_the_existing_job():
    """새 잡 금지 — 기존 grade 잡에 이어붙인다(타이밍 결합 회피)."""
    pl = Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    assert "from app.engine.market_baseline import grade" in pl
    sch = Path("app/scheduler.py").read_text(encoding="utf-8")
    assert "market_baseline" not in sch, "스케줄러에 새 잡이 생겼다"


def test_draw_odds_are_not_collected():
    """무승부 배당 수집 확장 금지 — 2-way 로만 계산한다."""
    assert "Draw" not in SRC and "무승부" in SRC
    assert "devig_two_way" in SRC and "three" not in SRC.lower()


# ═════════ 프롬프트 렌더 추출이 동작을 안 바꿨는가 ═════════

def test_render_matchup_prompt_is_pure():
    """🔴 `judge_matchup` 에서 꺼낸 것이지 새로 쓴 게 아니다."""
    import inspect

    from app.engine.matchup import render_matchup_prompt

    src = inspect.getsource(render_matchup_prompt)
    # 모델을 부르지 않는다
    for banned in ("complete_json", "await ", "anthropic", "client"):
        assert banned not in src, f"{banned} — 순수 함수가 아니다"
    # 자리표시자를 전부 채운다
    for slot in ("BOXSCORE_JSON", "NEWS_JSON", "LINEUPS_JSON",
                 "STARTERS_RECENT_JSON", "PREV_VERDICT_JSON",
                 "LINEUP_INTENT_JSON", "BULLPEN_JSON"):
        assert slot in src, slot
    assert "insert_ledger" in src


def test_judge_matchup_calls_the_extracted_renderer():
    import inspect

    from app.engine.matchup import judge_matchup

    src = inspect.getsource(judge_matchup)
    assert "render_matchup_prompt(jg, boxes, news, prev)" in src
    assert "fill(" not in src, "렌더가 두 곳에 남아 있다 — 복제는 드리프트다"


def test_no_placeholder_survives_render():
    """자리표시자가 남으면 모델이 `{{...}}` 를 그대로 읽는다."""
    from app.engine.matchup import render_matchup_prompt

    import re

    out = render_matchup_prompt({"sport": "mlb"}, {"home": {}, "away": {}},
                                {}, None)
    # ⚠️ `}}` 만 보면 안 된다 — 출력 JSON 예시의 **중첩 중괄호**가 걸린다.
    #    자리표시자는 `{{대문자}}` 형태다.
    assert not re.findall(r"\{\{[A-Z_]+\}\}", out)


# ── [MB-1 2026-09-11] 이견 적중률의 분모가 "모르는 것"을 포함했다 ─────────
#   🔴 운영 요약이 이렇게 나갔다:
#        🎯 시장 39승31패 · 우리 8승5패 · **이견 51건 중 4적중**
#      바로 앞 줄이 "우리 8승5패"(13경기)인데 이견은 51건이다 — 안 맞는다.
#
#   실측(운영 DB · MLB · 임계 4.0%p):
#        채점행 80 · **our_hit 이 NULL 인 것 67**
#        이견 53건 — 그중 our_hit 을 아는 것은 **8건뿐**
#        이견 적중 4
#        요약 표기  4/53 = 7.5%     ← "시장과 갈리면 92% 틀린다"로 읽힌다
#        실제 값    4/8  = 50.0%
#
#   원인: `diverged` 는 `our_hit IS NULL` 까지 세고 `diverged_hit` 은 참만 센다.
#         **모르는 것이 틀린 것으로 계산된다.**
#   ⚠️ 이 줄은 "시장을 이기고 있는가"를 보는 벤치마크다. 분모가 틀리면
#      사람이 정반대 결론을 내린다.

@pytest.mark.asyncio
async def test_diverged_denominator_excludes_unknown(db_pool):
    """이견 분모는 **채점된 것만** 센다."""
    from app.engine.market_baseline import summary

    async with db_pool.acquire() as c:
        await c.execute("DELETE FROM market_baseline_ledger")
        # 이견 3건: 적중1 · 실패1 · **our_hit 모름1** (+ 이견 아닌 것 1)
        for gid, our_hit, div in ((9001, True, 0.10), (9002, False, 0.10),
                                  (9003, None, 0.10), (9004, True, 0.01)):
            await c.execute(
                """INSERT INTO games (id, sport, league, ext_id, starts_at,
                                        home, away)
                   VALUES ($1,'mlb','MLB',$2,now(),'H','A')
                   ON CONFLICT (id) DO NOTHING""", gid, str(gid))
            await c.execute(
                """INSERT INTO market_baseline_ledger
                     (game_id, sport, slate_date, divergence, our_hit,
                      market_hit, graded_at, void)
                   VALUES ($1,'mlb','2026-09-11',$2,$3,TRUE,now(),FALSE)""",
                gid, div, our_hit)
    row = await summary(db_pool, ("mlb",))
    assert row is not None
    assert row["diverged_hit"] == 1
    assert row["diverged"] == 2, (
        f"모르는 것(our_hit NULL)이 분모에 들어갔다: {row['diverged']}")


@pytest.mark.asyncio
async def test_diverged_counts_losses(db_pool):
    """⚠️ 반대 위험 — 실패를 분모에서 빼버리면 100%가 되어버린다."""
    from app.engine.market_baseline import summary

    async with db_pool.acquire() as c:
        await c.execute("DELETE FROM market_baseline_ledger")
        for gid, our_hit in ((9101, True), (9102, False), (9103, False)):
            await c.execute(
                """INSERT INTO games (id, sport, league, ext_id, starts_at,
                                        home, away)
                   VALUES ($1,'mlb','MLB',$2,now(),'H','A')
                   ON CONFLICT (id) DO NOTHING""", gid, str(gid))
            await c.execute(
                """INSERT INTO market_baseline_ledger
                     (game_id, sport, slate_date, divergence, our_hit,
                      market_hit, graded_at, void)
                   VALUES ($1,'mlb','2026-09-11',0.10,$2,TRUE,now(),FALSE)""",
                gid, our_hit)
    row = await summary(db_pool, ("mlb",))
    assert row["diverged"] == 3 and row["diverged_hit"] == 1
