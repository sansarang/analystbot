"""[§3] 라인 무브먼트 — 검증 지표로만 쓴다.

마감 배당이 개장 배당보다 예측 정확도가 높다는 것은 검증된 사실이지만,
"움직임은 맥락이지 전략이 아니다". 확률에는 넣지 않고 신뢰도만 조정한다.
"""

import pytest

from app.engine.linemove import (
    MIN_MOVE,
    adjust_confidence,
    agreement,
    attach_line_move,
    describe,
    move_direction,
)


# ---------------------------------------------------------------- 방향 판정

def test_shortening_odds_means_money_on_that_side():
    """배당이 내려가면 그 사이드로 돈이 몰린 것 = 시장 확률 상승."""
    direction, delta = move_direction(1.90, 1.70)
    assert direction == "toward" and delta > 0

    direction, delta = move_direction(1.70, 1.90)
    assert direction == "away" and delta < 0


def test_small_moves_are_noise():
    """2%p 미만 이동은 노이즈로 본다."""
    direction, delta = move_direction(1.80, 1.79)
    assert direction == "flat" and abs(delta) < MIN_MOVE


def test_agreement_matrix():
    """모델이 우세로 본 사이드로 시장이 움직이면 일치."""
    assert agreement(True, "toward") == "agree"
    assert agreement(True, "away") == "diverge"
    assert agreement(False, "away") == "agree"      # 모델도 약세, 시장도 이탈
    assert agreement(False, "toward") == "diverge"
    assert agreement(True, "flat") == "neutral"


# ---------------------------------------------------------------- 신뢰도 조정

def test_confidence_moves_one_step_only():
    """[§3] 일치 +1단계 / 역행 -1단계. 두 단계 이상 움직이지 않는다."""
    assert adjust_confidence("medium", "agree") == ("high", None)
    assert adjust_confidence("low", "agree") == ("medium", None)
    assert adjust_confidence("high", "agree") == ("high", None)      # 상한

    conf, warn = adjust_confidence("medium", "diverge")
    assert conf == "low" and "시장이 반대로 움직임" in warn
    assert adjust_confidence("low", "diverge")[0] == "low"           # 하한

    assert adjust_confidence("medium", "neutral") == ("medium", None)


def test_divergence_warning_states_the_risk():
    """역행 경고는 '우리가 모르는 정보 가능성'을 명시해야 한다."""
    _conf, warn = adjust_confidence("high", "diverge")
    assert "우리가 모르는 정보" in warn


def test_describe_line_is_readable():
    line = describe(1.90, 1.70, 0.062, "agree")
    assert "1.90 ↓ 1.70" in line and "모델과 같은 방향" in line
    assert "+6.2%" in line


# ---------------------------------------------------------------- DB 통합

async def _game_with_snapshots(db_pool, moves):
    row = await db_pool.fetchrow(
        """
        INSERT INTO games (sport, league, ext_id, starts_at, home, away)
        VALUES ('mlb', 'MLB', $1, now() + interval '3 hours', 'H', 'A')
        ON CONFLICT (sport, ext_id) DO UPDATE SET home = EXCLUDED.home
        RETURNING id
        """,
        f"linemove-{moves[0]}-{moves[-1]}",
    )
    gid = row["id"]
    await db_pool.execute("DELETE FROM odds_snapshots WHERE game_id = $1", gid)
    for i, odds in enumerate(moves):
        await db_pool.execute(
            "INSERT INTO odds_snapshots (game_id, book, market, side, line, odds, captured_at) "
            "VALUES ($1, 'testbook', 'h2h', 'H', NULL, $2, "
            "        now() - make_interval(hours => $3))",
            gid, odds, len(moves) - i,
        )
    return gid


def _jg(gid, p=0.62):
    from app.engine.markets import grade_candidate

    c = {"market": "h2h", "side": "H", "line": None, "desc": "홈 승",
         "odds": 1.70, "p": p, "ev": 0.05, "axes_kr": "실데이터+모델",
         "approved": True, "reject_reason": None, "two_source": True}
    c["grade"], c["grade_note"] = grade_candidate(c)
    return {"game_id": gid, "home": "H", "away": "A", "status": "scheduled",
            "judge_confidence": "medium", "market_board": [c]}


async def test_agreeing_move_raises_confidence(db_pool):
    """[§3] 모델과 같은 방향으로 라인이 움직이면 신뢰도가 올라간다."""
    gid = await _game_with_snapshots(db_pool, [1.90, 1.80, 1.70])
    jg = _jg(gid)
    info = await attach_line_move(db_pool, jg)
    assert info["verdict"] == "agree"
    assert jg["judge_confidence"] == "high"
    assert info["warning"] is None


async def test_diverging_move_lowers_confidence_and_warns(db_pool):
    """[§3] 시장이 반대로 움직이면 신뢰도를 낮추고 경고한다."""
    gid = await _game_with_snapshots(db_pool, [1.70, 1.85, 2.00])
    jg = _jg(gid)
    info = await attach_line_move(db_pool, jg)
    assert info["verdict"] == "diverge"
    assert jg["judge_confidence"] == "low"
    assert "우리가 모르는 정보" in info["warning"]


async def test_line_move_never_touches_probability(db_pool):
    """[§3] 확률에는 절대 반영하지 않는다 — 맥락이지 전략이 아니다."""
    gid = await _game_with_snapshots(db_pool, [1.90, 1.70])
    jg = _jg(gid)
    before = jg["market_board"][0]["p"]
    await attach_line_move(db_pool, jg)
    assert jg["market_board"][0]["p"] == before
    assert "p_final" not in jg and "distribution" not in jg


async def test_single_snapshot_yields_nothing(db_pool):
    """스냅샷이 하나뿐이면 이동을 계산할 수 없다."""
    gid = await _game_with_snapshots(db_pool, [1.80])
    jg = _jg(gid)
    assert await attach_line_move(db_pool, jg) is None
    assert jg["judge_confidence"] == "medium"
