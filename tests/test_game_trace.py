"""[투명 리포트 G1 2026-09-04] 경기 서사 원장.

🔴 이 층의 존재 이유: 지금은 **카드(결론)만** 도착하고, 그 결론이 어떤
   재료·조사·추론을 거쳤는지는 로그를 뒤져야만 보인다.

🔴 **원장은 로그보다 많이 알지 않는다.** 각 행의 `summary` 는 그 자리에서
   이미 찍히는 로그 문자열을 **그대로 복사**한 것이다. 원장에만 있는 사실을
   만들면 리포트를 로그로 검증할 수 없고, 그 순간 리포트는 "투명"이 아니라
   제2의 주장이 된다. 그래서 호출 규약이 "한 번 포맷 → 로그 → 복사" 다.

⚠️ 기록·표시 층이다. 판정·게이트·발송은 이 테이블을 읽지 않는다.
"""
from pathlib import Path

import pytest

from app.engine import game_trace as gt


class _Pool:
    def __init__(self, fail=False):
        self.rows: list[tuple] = []
        self.fail = fail

    async def execute(self, sql, *a):
        if self.fail:
            raise RuntimeError("DB 없음")
        self.rows.append(a)

    async def fetch(self, sql, *a):
        raise RuntimeError("사용 안 함")


# ─────────────────── 적재 계약 ───────────────────

@pytest.mark.asyncio
async def test_note_records_one_row():
    pool = _Pool()
    ok = await gt.note(pool, game_id=1705, sport="KBO", date="2026-09-04",
                       stage=gt.JUDGE, summary="[matchup] game=1705 p_home=0.62")
    assert ok is True
    gid, sport, date, stage, summary, ref = pool.rows[0]
    assert (gid, sport, date, stage) == (1705, "kbo", "2026-09-04", "판정")
    assert summary.startswith("[matchup]")
    assert ref is None


@pytest.mark.asyncio
async def test_unknown_stage_is_refused_loudly_not_stored():
    """🔴 오타 하나가 리포트에서 그 단계를 통째로 사라지게 한다."""
    pool = _Pool()
    assert await gt.note(pool, game_id=1, sport="kbo", date="d",
                         stage="판정중", summary="x") is False
    assert pool.rows == []


@pytest.mark.asyncio
async def test_db_failure_never_raises():
    """🔴 기록하려다 본체를 죽이면 안 된다 — 판정·발송이 원장 때문에 멈추지 않는다."""
    assert await gt.note(_Pool(fail=True), game_id=1, sport="kbo", date="d",
                         stage=gt.SEND, summary="x") is False


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [
    {"game_id": None}, {"summary": ""},
])
async def test_incomplete_rows_are_dropped(bad):
    args = {"game_id": 1, "sport": "kbo", "date": "d", "stage": gt.SEND,
            "summary": "x"}
    args.update(bad)
    assert await gt.note(_Pool(), **args) is False


@pytest.mark.asyncio
async def test_none_pool_is_a_no_op():
    assert await gt.note(None, game_id=1, sport="kbo", date="d",
                         stage=gt.SEND, summary="x") is False


# ─────────────────── 단계 정의 ───────────────────

def test_stages_cover_the_whole_pipeline():
    assert gt.STAGES == ("수집", "조립", "판정", "재판정", "딥서치", "게이트", "발송")


def test_stage_names_are_not_copied_into_call_sites():
    """🔴 사본 금지 — 호출부는 상수를 import 하지 문자열을 적지 않는다."""
    for f in ("app/engine/matchup.py", "app/pipeline.py",
              "app/engine/pregame_push.py"):
        src = Path(f).read_text(encoding="utf-8")
        for lit in ('stage="판정"', 'stage="조립"', 'stage="발송"',
                    'stage="게이트"', 'stage="재판정"', 'stage="딥서치"'):
            assert lit not in src, f"{f}: {lit}"


# ─────────────────── 로그 = 원장 ───────────────────

@pytest.mark.parametrize("path,var", [
    ("app/engine/matchup.py", "_mat_msg"),
    ("app/engine/matchup.py", "_judge_msg"),
    ("app/pipeline.py", "_rj_msg"),
    ("app/pipeline.py", "_ds_msg"),
    ("app/engine/pregame_push.py", "_gate_msg"),
    ("app/engine/pregame_push.py", "_send_msg"),
])
def test_every_hook_formats_once_and_shares_it(path, var):
    """🔴 포맷을 두 번 적으면 언젠가 갈린다 — 그때 원장은 로그와 다른 말을 한다.

    규약: `msg = "..." % (...)` → `logger.info("%s", msg)` → `note(summary=msg)`
    """
    src = Path(path).read_text(encoding="utf-8")
    assert f"{var} = " in src, f"{path}: {var} 가 없다"
    assert f'logger.info("%s", {var})' in src, f"{path}: {var} 를 로그에 안 쓴다"
    assert f"summary={var}" in src, f"{path}: {var} 를 원장에 안 넘긴다"


def test_trace_is_never_read_by_judgement_or_gate():
    """🔴 기록·표시 층이다. 판정·게이트가 이걸 읽으면 층이 무너진다."""
    for f in ("app/engine/matchup.py", "app/engine/value_gate.py",
              "app/engine/pregame_push.py", "app/pipeline.py"):
        src = Path(f).read_text(encoding="utf-8")
        for banned in ("game_trace import timeline", "game_trace import slate",
                       "gt.timeline(", "gt.slate("):
            assert banned not in src, f"{f}: {banned}"


def test_prompt_original_is_not_duplicated_into_the_ledger():
    """원문은 Redis 에 이미 있다 — 원장에는 **지문만** 둔다."""
    src = Path("app/engine/matchup.py").read_text(encoding="utf-8")
    assert "prompt_sha" in src
    assert "summary=prompt" not in src and "ref={\"prompt\":" not in src
