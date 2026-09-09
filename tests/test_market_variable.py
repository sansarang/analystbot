"""[MKT-5] 괴리를 **변수**로 등록한다 — 자료가 아니라 변수다.

🔴 **왜 이 형태인가.** 앞서 MKT-4 로 시장 확률을 **자료15**(판정 입력)로
   줘 봤고, A/B 가 막았다:
       |p − 시장| 중앙값 OFF 0.0163 → ON 0.0061 · 평균 0.0187 → 0.0060
       수축률 **+67.9%** · ON 반복 2회가 전부 동일값(0.53/0.53 · 0.55/0.55 …)
   프롬프트에 "베끼지 마라 · 정답이 아니다"를 명시했는데도 **판정이 시장
   숫자에 고정됐다.** 앵커링이 지시보다 강하다. 그래서 자료로는 주지 않는다.

✅ **변수는 판정 뒤에 만들어진다.** `p_home` 이 이미 확정된 다음이라
   오염 경로가 **구조적으로 없다.** 그리고 변수는 이 시스템이 이미
   - 원장에 적재하고(`variable_ledger.record`)
   - 채점하며(`realized`/`actual`)
   - 자료14가 다음 회차에 조사한다 → **"왜 갈렸는지"가 거기서 나온다**

📐 **괴리의 뜻은 실측이 정한다** (운영 원장, 시장값 있는 141경기):
       |차| 0~2%p   n=23  우리 47.8% · 시장 47.8%
       |차| 2~4%p   n=20  우리 55.0% · 시장 55.0%
       |차| 4~8%p   n=39  우리 51.3% · 시장 43.6%
       |차| 8%p+    n=59  우리 49.2% · 시장 **69.5%**
   **8%p 넘게 갈릴 때만 시장이 이긴다.** 그래서 그 구간에서만 변수를 낸다 —
   4%p 대역까지 변수를 내면 잡음이고, 잡음이 잦으면 변수 대장이 죽는다.
"""
from __future__ import annotations


def _v(mkt, ours):
    from app.engine.market_variable import divergence_variable

    return divergence_variable({"p_market_send": mkt, "p_claude": ours,
                                "home": "H팀", "away": "A팀"})


def test_큰_괴리는_변수가_된다():
    v = _v(0.52, 0.66)          # 14%p
    assert v, "8%p 넘게 갈렸는데 변수를 안 냈다"
    assert "14.0%p" in v


def test_작은_괴리는_변수가_아니다():
    """⚠️ 실측상 8%p 아래에서는 시장이 우리를 못 이긴다 — 잡음을 만들지 않는다."""
    assert _v(0.52, 0.56) is None      # 4%p
    assert _v(0.55, 0.57) is None      # 2%p


def test_시장값이_없으면_변수도_없다():
    assert _v(None, 0.66) is None
    assert _v(0.52, None) is None


def test_방향은_시장_쪽이다():
    """괴리가 실현된다는 것은 **시장이 맞았다**는 뜻이다."""
    assert "원정 방향" in _v(0.40, 0.60)     # 시장은 원정 우세
    assert "홈 방향" in _v(0.62, 0.42)       # 시장은 홈 우세


def test_변수_형식을_지킨다():
    """🔴 형식이 어긋나면 파서가 버리고 원장·조사·채점에서 통째로 빠진다."""
    from app.engine.variable_parse import parse_variable

    p = parse_variable(_v(0.52, 0.66))
    assert p is not None, "형식 위반 — 정량 파싱 불가"
    assert p["n"] == 14.0
    # ⚠️ 파서가 `홈`→`home` 으로 정규화한다 — 원문이 아니라 파서 규약을 본다.
    assert p["side"] in ("home", "away")
    assert p["m"] == 0.0, "이미 반영된 것이 아니다 — 기반영은 0 이어야 한다"


def test_발생확률은_실측에서_온다():
    """지어낸 수가 아니라 우리 원장에서 잰 수다 (8%p+ 대역 시장 적중 69.5%)."""
    from app.engine.market_variable import MARKET_WIN_RATE_PP8

    assert 0.60 <= MARKET_WIN_RATE_PP8 <= 0.75
    assert f"{MARKET_WIN_RATE_PP8 * 100:.0f}%" in _v(0.52, 0.66)


def test_판정_뒤에_붙는다():
    """🔴 이 설계의 전부다 — 판정이 이 변수를 보면 앵커링이 되살아난다."""
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    i = src.index("async def _run_baseball_matchups")
    body = src[i:src.index("async def ", i + 10)]
    assert "market_variable" in body, "괴리 변수를 등록하지 않는다"
    assert body.index("judge_matchup(") < body.index("market_variable"), \
        "괴리 변수가 판정보다 앞에 있다 — 판정이 시장을 보게 된다"
    # 그리고 **변수 적재보다는 앞**이어야 원장에 실린다
    assert body.index("market_variable") < body.index("variable_ledger"), \
        "괴리 변수가 원장 적재보다 뒤다 — 등록해도 원장에 안 들어간다"


# ── [MKT-6] 괴리 변수를 **채점**한다 ─────────────────────────────────────
#
# 🔴 MKT-5 로 변수를 만들었더니 **채점이 안 됐다.** `variable_ledger.grade` 는
#    `subject_kind` 가 `pitcher`/`team` 일 때만 실측을 조회한다. 괴리 변수는
#      subject_of  → (None, None)
#      threshold_of → None
#      judge_realized(None, None) → **unverifiable**
#    로 떨어져 전건이 검증불가로 쌓인다. 만들어 놓고 재지 않는 것은
#    이 저장소가 가장 자주 데인 형태다(BAT-10 · 자료13 · 감시 3층).
#
# ✅ **이 변수는 채점이 가장 쉽다.** "시장 방향이 이겼는가" 한 줄이면 끝난다.
#    실측(운영 원장 141경기 중 발화 59건): 41/59 = **69.5%** 가 실현됐고,
#    변수가 주장한 발생 확률 70% 와 일치했다.

def test_시장_방향이_이기면_현실화다():
    from app.engine.market_variable import realized_of

    # 변수 방향이 away 인데 원정이 이겼다 → 현실화
    assert realized_of("away", home_score=3, away_score=5) is True
    assert realized_of("home", home_score=6, away_score=1) is True


def test_시장_방향이_지면_현실화가_아니다():
    from app.engine.market_variable import realized_of

    assert realized_of("away", home_score=6, away_score=1) is False
    assert realized_of("home", home_score=1, away_score=6) is False


def test_점수가_없으면_판정하지_않는다():
    """⚠️ 모르는 것을 False 로 적으면 채점이 거짓말이 된다."""
    from app.engine.market_variable import realized_of

    assert realized_of("home", home_score=None, away_score=2) is None
    assert realized_of(None, home_score=1, away_score=2) is None


def test_무승부는_판정하지_않는다():
    """야구는 연장이 있지만 NPB 는 무승부가 있다 — 방향이 맞았다고 못 한다."""
    from app.engine.market_variable import realized_of

    assert realized_of("home", home_score=3, away_score=3) is None


def test_채점기가_괴리_변수를_안다():
    """🔴 `grade()` 가 이 변수를 검증불가로 버리지 않는다."""
    from pathlib import Path

    src = Path("app/engine/variable_ledger.py").read_text(encoding="utf-8")
    assert "market_variable" in src or "시장 기준선" in src, \
        "채점기가 괴리 변수를 모른다 — 전건이 unverifiable 로 쌓인다"


async def test_채점기가_실제로_채점한다(db_pool):
    """🔴 순수 함수가 아니라 `grade()` 전체가 도는지 본다 — 실제 DB로."""
    from datetime import UTC, datetime

    from app.engine.variable_ledger import grade

    gid = await db_pool.fetchval(
        "INSERT INTO games (sport, league, ext_id, starts_at, home, away, status,"
        " home_score, away_score) VALUES ('mlb','MLB','mkt6',$1,'H팀','A팀','final',"
        " 2, 7) RETURNING id", datetime(2026, 5, 1, tzinfo=UTC))
    raw = ("우리와 시장이 14.0%p 갈렸다(우리 60% vs 시장 46%) — 발생 시 원정 방향 "
           "약 14.0%p · 발생 확률 70% · 현재 p에 0.0%p 기반영 · 근거 시장 기준선")
    await db_pool.execute(
        "INSERT INTO variable_ledger (game_id, sport, raw, direction, claimed_n,"
        " claimed_m, source_ref) VALUES ($1,'mlb',$2,'away','14.0','0.0','시장 기준선')",
        gid, raw)

    out = await grade(db_pool, "mlb")
    assert out["graded"] == 1, out
    assert out["unverifiable"] == 0, f"괴리 변수가 검증불가로 떨어졌다: {out}"
    assert out["realized"] == 1, "원정이 7-2 로 이겼는데 현실화로 안 잡혔다"
    row = await db_pool.fetchrow(
        "SELECT realized, actual FROM variable_ledger WHERE game_id=$1", gid)
    assert row["realized"] == "true", row["realized"]
