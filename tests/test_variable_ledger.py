"""[C3] 변수 원장 — 주장과 실측의 대조. **발명하지 않는다.**

🔴 변수가 서술이던 동안에는 맞았는지 틀렸는지 셀 수 없었다.
   "이닝 소화력 예측 불가"는 참도 거짓도 아니다.
"""
import pytest

from app.engine import variable_ledger as VL

JG = {"game_id": 7, "sport": "kbo", "home": "두산", "away": "LG",
      "research": {"home_pitcher": {"name": "곽빈"},
                   "away_pitcher": {"name": "박시원"}}}


def test_threshold_is_read_not_invented():
    assert VL.threshold_of("3이닝 미만 조기 강판") == {
        "value": 3.0, "unit": "이닝", "cmp": "미만"}
    assert VL.threshold_of("타선 침체가 이어질 수 있다") is None


def test_no_threshold_means_unverifiable():
    """🔴 임계가 없으면 **채점하지 않는다.** 우리가 상상해 붙이면 우리 상상을
    채점하는 것이다."""
    assert VL.judge_realized(None, {"innings": 2.0}) == VL.UNVERIFIABLE


def test_realized_true_and_false():
    thr = VL.threshold_of("3이닝 미만")
    assert VL.judge_realized(thr, {"innings": 2.1}) == VL.TRUE
    assert VL.judge_realized(thr, {"innings": 5.0}) == VL.FALSE


def test_missing_actual_is_unverifiable():
    assert VL.judge_realized(VL.threshold_of("3이닝 미만"), None) == VL.UNVERIFIABLE
    assert VL.judge_realized(VL.threshold_of("3이닝 미만"), {}) == VL.UNVERIFIABLE


def test_comparators():
    for expr, actual, want in (("5실점 이상", 5, VL.TRUE),
                               ("5실점 초과", 5, VL.FALSE),
                               ("2득점 이하", 2, VL.TRUE),
                               ("2득점 미만", 2, VL.FALSE)):
        assert VL.judge_realized(VL.threshold_of(expr), {"runs": actual}) == want, expr


def test_subject_prefers_the_pitcher_then_team():
    assert VL.subject_of("박시원 3이닝 미만", JG) == ("박시원", "pitcher")
    assert VL.subject_of("LG 타선 침체", JG) == ("LG", "team")


def test_unknown_subject_is_not_forced():
    """이름이 안 잡히면 None 이다 — 잘못된 주체로 채점하면 더 나쁘다."""
    assert VL.subject_of("날씨 변수", JG) == (None, None)


class Pool:
    def __init__(self):
        self.rows = []

    async def execute(self, sql, *a):
        self.rows.append(a)


@pytest.mark.asyncio
async def test_format_violation_is_stored_not_dropped():
    """🔴 파싱 실패도 **행으로 남긴다** — 형식 위반율을 재는 게 절반이다."""
    pool = Pool()
    jg = {**JG, "matchup": {"변수": ["예측 불가 (종전 서술형)"]}}
    assert await VL.record(pool, jg) == 1
    args = pool.rows[0]
    assert args[3] == "예측 불가 (종전 서술형)"          # raw 보존
    assert args[7] is None and args[8] is None           # claimed_n/m 없음
    assert args[10] == VL.UNVERIFIABLE


@pytest.mark.asyncio
async def test_quantified_variable_is_stored_with_numbers():
    pool = Pool()
    jg = {**JG, "matchup": {"변수": [
        "박시원 3이닝 미만 조기 강판 — 발생 시 홈 방향 약 8%p · "
        "현재 p에 3%p 기반영 · 근거 자료10"]}}
    await VL.record(pool, jg)
    a = pool.rows[0]
    assert a[4] == "박시원" and a[5] == "pitcher"
    assert a[6] == "home" and float(a[7]) == 8.0 and float(a[8]) == 3.0
    assert a[9] == "자료10" and a[10] is None            # 채점 전이다


@pytest.mark.asyncio
async def test_record_without_pool_is_safe():
    assert await VL.record(None, JG) == 0


def test_grading_runs_inside_the_existing_job():
    """따로 돌면 한쪽만 밀린다 — 픽 채점과 같은 잡에서 돈다."""
    from pathlib import Path

    src = Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    assert "from app.engine.variable_ledger import grade" in src


def test_grade_pending_return_contract_is_unchanged():
    """🔴 `{graded, void}` 는 호출부·테스트가 정확히 비교하는 계약이다."""
    from pathlib import Path

    src = Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    assert 'out["variables"]' not in src


def test_record_hook_is_after_the_judge_call():
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    seg = src[src.index("async def _run_baseball_matchups"):]
    assert seg.index("await judge_matchup") < seg.index("variable_ledger import record")
