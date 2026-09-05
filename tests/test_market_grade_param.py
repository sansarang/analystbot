"""[A · P1 2026-09-05] 시장 채점이 **한 건도** 기록되지 않고 있었다.

🔴 운영 13:00 잡 로그(2026-09-05):
     WARNING [market] 채점 기록 실패 id=1: could not determine data type of parameter $2
   id 1~10 · 30~37 · 40~43 · 47 — **22건**이 같은 오류로 실패했다.

🔴 재현(로컬 Postgres, 같은 스키마·같은 쿼리):
     종전 p_close=None  → AmbiguousParameterError: could not determine data type of parameter $2
     종전 p_close=0.512 → AmbiguousParameterError (동일)
   **값과 무관하게 항상** 실패한다 — 프리페어 단계의 타입 추론 실패이기
   때문이다. 그래서 2026-09-04 도입 이후 채점이 0건이었다.

원인: 같은 `$2` 가 두 문맥에 쓰였다 —
     SET p_market_close = $2      (컬럼 타입 NUMERIC)
     divergence = … our_p - $2    (산술)
   Postgres 가 둘을 통일하지 못한다.

수정: `$2::numeric` 캐스팅. **파라미터 개수를 바꾸지 않는다** — 호출부
     불변이 최소 침습이다.

소급: `_PENDING` 이 `WHERE b.graded_at IS NULL` 로 고르므로 실패한 22건은
     다음 `grade()` 에서 **자동으로 다시 잡힌다.** 백필 코드가 필요 없다.
"""
import re
from pathlib import Path

SRC = Path("app/engine/market_baseline.py").read_text(encoding="utf-8")


def test_ambiguous_parameter_is_cast():
    """🔴 캐스팅이 빠지면 값과 무관하게 항상 실패한다."""
    m = re.search(r"UPDATE market_baseline_ledger.*?WHERE id = \$1", SRC, re.S)
    assert m, "채점 UPDATE 문을 찾지 못했다"
    sql = m.group(0)
    # `$2` 가 나오는 모든 자리가 캐스팅돼 있어야 한다
    bare = re.findall(r"\$2(?!::)", sql)
    assert not bare, f"캐스팅 없는 $2 가 {len(bare)}곳 남았다"
    assert "$2::numeric" in sql


def test_parameter_count_unchanged():
    """호출부를 안 건드리는 것이 최소 침습이다."""
    m = re.search(r"UPDATE market_baseline_ledger.*?WHERE id = \$1", SRC, re.S)
    nums = {int(x) for x in re.findall(r"\$(\d)", m.group(0))}
    assert nums == {1, 2, 3, 4, 5, 6}, nums
    assert 'r["id"], p_close, fav, market_hit, our_hit, void)' in SRC


def test_retroactive_is_automatic_not_a_backfill_script():
    """소급을 위해 별도 스크립트를 만들지 않는다 — 대기 조건이 이미 그렇다."""
    m = re.search(r"_PENDING = \"\"\"(.*?)\"\"\"", SRC, re.S)
    assert "graded_at IS NULL" in m.group(1)


def test_incident_numbers_are_recorded_in_code():
    """🔴 실측 수치를 지우면 다음 사람이 같은 자리에서 다시 판다."""
    assert "AmbiguousParameterError" in SRC or "could not determine data type" in SRC
    assert "2026-09-04" in SRC or "2026-09-05" in SRC
