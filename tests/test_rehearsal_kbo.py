"""[리허설 · KBO] 사전 예측 — 격리와 **시점 규칙의 차이**를 잠근다.

🔴 MLB 리허설과 시점 규칙이 **반대**다. MLB 는 끝난 경기라 지금 긁으면
   안 됐고, KBO 는 **아직 안 한 경기**라 지금 재료가 곧 그 시점 재료다.
   그 차이를 코드에 적어 두지 않으면 다음 사람이 한쪽 규칙을 다른 쪽에
   적용한다.
"""
from pathlib import Path

SRC = Path("tools/rehearsal_kbo.py").read_text(encoding="utf-8")


def test_the_time_rule_difference_is_written_down():
    assert "시점 규칙이 **반대다**" in SRC or "시점 규칙이 반대다" in SRC
    assert "아직 안 한 경기" in SRC and "누수가 아니다" in SRC


def test_collection_is_allowed_but_isolated():
    """미래 경기라 수집은 허용 — 단 격리 안에서만."""
    assert "build_analysis" in SRC
    assert "redis=rredis" in SRC, "격리 redis 로 수집하지 않는다"


def test_isolation_is_reused():
    assert "from tools.rehearsal import" in SRC
    for name in ("RehearsalRedis", "_cleanup", "_install_guards",
                 "_remove_guards"):
        assert name in SRC, name


def test_no_writes_to_real_tables():
    for banned in ("INSERT INTO", "UPDATE ", "record_send", "_store(",
                   "grade(", "record_analysis"):
        assert banned not in SRC, f"{banned} — 실 테이블에 쓴다"


def test_stops_after_17_kst():
    """🔴 저녁 창에 리허설이 남으면 실슬레이트와 섞인다."""
    assert "now.hour >= 17" in SRC
    assert "실슬레이트가 정본" in SRC


def test_provisional_is_flagged():
    """잠정 기반임을 숨기면 저녁에 판정이 움직였을 때 설명할 수 없다."""
    assert "provisional" in SRC
    assert "slots < 9" in SRC
    assert "잠정 라인업 기반" in SRC


def test_l2_is_capped_for_cost():
    assert "L2_LIMIT = 2" in SRC
    assert "do_l2" in SRC


def test_not_counted_in_clean_sample():
    assert "클린" in SRC and "카운터" in SRC


def test_hook_is_flag_gated():
    sch = Path("app/scheduler.py").read_text(encoding="utf-8")
    assert 'os.getenv("REHEARSAL_KBO") == "1"' in sch
