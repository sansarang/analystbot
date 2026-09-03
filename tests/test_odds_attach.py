"""[구멍 C] 야구 첫 카드에 배당이 안 붙던 문제.

🔴 실측 2026-09-03: KBO 4경기가 나갔는데 `배당 재부착` 로그는 **1건**뿐이었다
   (타순 변동으로 재판정한 game=1704). 나머지 3장은 배당이 DB 에 있는데도
   "가치 배당 미수집"으로 나갔다. NPB 도 같았다 — 재판정을 탄 2541 만 값이
   있었고 잠정으로 나간 2540 은 없었다.

원인: `build_analysis` 가 야구에 대해 `best_odds={}` 로 두는데(판정 격리 —
   이건 옳다), **판정이 끝난 뒤에 다시 붙여주는 곳이 없었다.**
   `refresh_odds_for_game`(v1.3 A-2)이 재판정 경로에만 배선돼 있었다.
"""
from pathlib import Path

SRC = Path("app/pipeline.py").read_text(encoding="utf-8")


def test_judgement_isolation_is_kept():
    """🔴 배당은 여전히 **판정 입력이 아니다.** 이 줄이 사라지면 금지선이 무너진다."""
    assert 'market_probs, best_odds = None, {}' in SRC
    i = SRC.index("market_probs, best_odds = None, {}")
    assert "승부 배당·암시확률은 야구 판정에 넣지 않는다" in SRC[i - 200:i]


def test_odds_are_attached_for_baseball_after_judgement():
    """판정이 끝난 뒤, 픽 계산 **앞**에서 붙는다."""
    attach = SRC.index("await refresh_odds_for_game(pool, _g)")
    picks = SRC.index("picks_out, parlays, recommended = _compute_picks(")
    assert attach < picks, "픽이 배당을 못 읽는다"


def test_attach_is_after_the_judge_call():
    """🔴 판정보다 **뒤**여야 배당이 `p_home` 에 닿을 수 없다."""
    judge = SRC.index("_judged = await _run_baseball_matchups(")
    attach = SRC.index("await refresh_odds_for_game(pool, _g)")
    assert judge < attach, "배당이 판정보다 먼저 붙는다 — 금지선 위반"


def test_attach_is_baseball_only():
    i = SRC.index("await refresh_odds_for_game(pool, _g)")
    assert "if sport in _BB:" in SRC[i - 900:i]


def test_failure_does_not_block_the_card():
    """배당이 없어도 카드는 나간다 — 없는 값을 만들지 않을 뿐이다."""
    i = SRC.index("await refresh_odds_for_game(pool, _g)")
    seg = SRC[i:i + 400]
    assert "except Exception" in seg and "logger.warning" in seg


def test_rejudge_path_still_attaches():
    """재판정 경로의 기존 부착은 그대로다 — 두 경로 모두 붙는다."""
    assert SRC.count("await refresh_odds_for_game(") == 2
