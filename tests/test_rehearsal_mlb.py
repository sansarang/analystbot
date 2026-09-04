"""[리허설 · MLB] **시점 동결**과 격리를 잠근다.

🔴 경기가 이미 끝났다. 지금 무엇이든 다시 긁으면 경기 중·후 데이터가
   섞이고, 그러면 "잘 맞혔다"가 전부 거짓이 된다.
"""
from pathlib import Path

SRC = Path("tools/rehearsal_mlb.py").read_text(encoding="utf-8")


def test_no_recollection():
    """🔴 재수집 금지 — 아침 판정이 쓴 캐시를 **읽기만** 한다."""
    for banned in ("build_analysis", "run_pipeline", "ensure_analysis_cache",
                   "attach_starter_recent", "fetch_month", "refresh_mlb_lineup"):
        assert banned not in SRC, f"{banned} — 재수집 경로다"
    assert 'inner_redis.get(f"analysis:mlb:{date}")' in SRC


def test_season_lines_are_not_attached_in_replay():
    """시즌 값은 언제나 "지금" 값 — 끝난 경기가 자기 시즌 라인에 들어간다."""
    assert "attach_opp_starter_era" not in SRC
    assert "starter_season" not in SRC
    assert "시즌 라인" in SRC and "붙이지 않는다" in SRC


def test_odds_use_the_close_cutoff():
    """배당은 `purpose=CLOSE` — `captured_at < starts_at` 이 이미 그 조건이다."""
    assert "purpose=CLOSE" in SRC
    assert "purpose=SEND" not in SRC, "SEND 는 '지금' 배당이라 라이브가 섞인다"


def test_cutoff_is_per_game_starts_at():
    assert 'cutoff = _aw(row["starts_at"])' in SRC
    assert "violations" in SRC, "위반을 기록하지 않으면 증명이 안 된다"
    assert "materials_newest" in SRC, "사용 데이터 최신 시각을 남겨야 한다"


def test_isolation_is_reused_not_rebuilt():
    """격리를 두 벌 만들면 한 벌이 샌다."""
    assert "from tools.rehearsal import" in SRC
    for name in ("RehearsalRedis", "_cleanup", "_install_guards",
                 "_remove_guards"):
        assert name in SRC, name


def test_no_writes_to_real_tables():
    for banned in ("INSERT INTO", "UPDATE ", "record_send", "record(",
                   "_store(", "grade("):
        assert banned not in SRC, f"{banned} — 실 테이블에 쓴다"


def test_scoring_is_flagged_as_reference_only():
    """표본 1일치다 — 클린 카운터에 넣지 않는다."""
    assert "클린 카운터에 넣지 않는다" in SRC
    assert "1일치 표본" in SRC


def test_hook_is_flag_gated():
    sch = Path("app/scheduler.py").read_text(encoding="utf-8")
    assert 'os.getenv("REHEARSAL_MLB") == "1"' in sch
