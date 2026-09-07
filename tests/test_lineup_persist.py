"""라인업 확정의 원본과 영속화 — KBO·NPB 가 12시간 뒤 사라지지 않게.

🔴 실측 2026-09-07 (운영 DB, 최근 14일):
   `lineups` 표에 **MLB 558행뿐이고 KBO·NPB 는 0행**이었다.
   `save_lineup` 호출처가 `refresh_mlb_lineup` 하나뿐이라 두 리그의 타순은
   분석 캐시(Redis TTL 12시간)에만 있었다 — 12시간 뒤면 그 경기에 누가
   나왔는지 DB 로 알 수 없다.

🔴 그리고 확정 플래그가 타순 실물과 갈렸다 (실측 game=2881 원장):
     12:10 [조립] 자료3=N(타순 0명)
     12:12 [판정] model=claude-sonnet-5  ← 유료 = 최종 판정
     22:05 lineups 표에 confirmed 타순 9명 (시작 T-5분)
   타순 0명으로 최종을 냈고 `claim_final` 락이 걸려 진짜 타순이 온 뒤의
   재판정 30여 회가 전부 조기 반환됐다. 09-05 MLB 13경기가 그 상태였다.
"""

import pytest


# ═══════════════ ① 확정의 정의는 하나다

def test_소스가_확정이라도_타순이_없으면_확정이_아니다():
    """🔴 이 파일이 존재하는 이유. 플래그만 보고 유료 최종을 내면 안 된다."""
    from app.pipeline import _merge_mlb

    jg = {"game_id": 1, "lineup_status": "none"}
    ctx = {"absences": {1: {"lineup": {"confirmed": True,
                                       "home": {"batting_order": []},
                                       "away": {"batting_order": []}}}}}
    _merge_mlb({}, jg, ctx)
    assert jg["lineup_status"] == "predicted", \
        "타순 0명인데 확정으로 올렸다 — 유료 최종이 재료 없이 나간다"


def test_양쪽_타순_9명이면_확정이다():
    from app.pipeline import _merge_mlb

    nine = [f"타자{i}" for i in range(9)]
    jg = {"game_id": 1, "lineup_status": "none"}
    ctx = {"absences": {1: {"lineup": {
        "confirmed": False,
        "home": {"batting_order": nine}, "away": {"batting_order": nine}}}}}
    _merge_mlb({}, jg, ctx)
    assert jg["lineup_status"] == "confirmed"


def test_한쪽만_9명이면_확정이_아니다():
    """한쪽만 와도 확정으로 읽으면 반쪽 재료로 최종을 낸다."""
    from app.pipeline import _merge_mlb

    nine = [f"타자{i}" for i in range(9)]
    jg = {"game_id": 1, "lineup_status": "none"}
    ctx = {"absences": {1: {"lineup": {
        "confirmed": True,
        "home": {"batting_order": nine}, "away": {"batting_order": []}}}}}
    _merge_mlb({}, jg, ctx)
    assert jg["lineup_status"] == "predicted"


def test_확정_규칙을_베끼지_않는다():
    """⚠️ 확정의 정의는 `pregame_push.lineup_confirmed` 하나다(v1.3 A-1)."""
    src = open("app/pipeline.py", encoding="utf-8").read()
    i = src.index("def _merge_mlb")
    seg = src[i:src.index("\ndef ", i + 10)]
    assert "from app.engine.pregame_push import lineup_confirmed" in seg


def test_충돌_상태는_확정으로_올라가지_않는다():
    """소스 불일치는 최종 픽 자격 박탈이다."""
    from app.pipeline import _merge_mlb

    nine = [f"타자{i}" for i in range(9)]
    jg = {"game_id": 1, "lineup_status": "conflict"}
    ctx = {"absences": {1: {"lineup": {
        "confirmed": True,
        "home": {"batting_order": nine}, "away": {"batting_order": nine}}}}}
    _merge_mlb({}, jg, ctx)
    assert jg["lineup_status"] == "conflict"


# ═══════════════ ② 영속화 — 12시간 뒤에도 남는다

class _Pool:
    def __init__(self):
        self.rows = []

    async def execute(self, sql, *a):
        self.rows.append(("execute", sql, a))


@pytest.mark.asyncio
async def test_확정_타순이_lineups_표에_기록된다():
    from app.pipeline import _persist_lineup_rows

    nine = "-".join(f"타자{i}" for i in range(9))
    jg = {"game_id": 7, "sport": "npb", "lineup_source": "crawler",
          "research": {"home_lineup": {"order": nine},
                       "away_lineup": {"order": nine}}}
    pool = _Pool()
    assert await _persist_lineup_rows(pool, jg) == 2
    sqls = " ".join(r[1] for r in pool.rows)
    assert "INSERT INTO lineups" in sqls


@pytest.mark.asyncio
async def test_타순이_9명_미만인_쪽은_넣지_않는다():
    from app.pipeline import _persist_lineup_rows

    jg = {"game_id": 7, "sport": "kbo",
          "research": {"home_lineup": {"order": "-".join(f"T{i}" for i in range(9))},
                       "away_lineup": {"order": "T1-T2"}}}
    assert await _persist_lineup_rows(_Pool(), jg) == 1


@pytest.mark.asyncio
async def test_이름만_넣는다_포지션_튜플이_아니다():
    """⚠️ `parse_order` 는 (이름, 포지션) 튜플을 준다. 스키마는 이름 배열이다."""
    import json

    from app.pipeline import _persist_lineup_rows

    jg = {"game_id": 7, "sport": "kbo",
          "research": {"home_lineup": {"order": "-".join(f"T{i}" for i in range(9))}}}
    pool = _Pool()
    await _persist_lineup_rows(pool, jg)
    order_json = [a for r in pool.rows for a in r[2]
                  if isinstance(a, str) and a.startswith("[")][0]
    parsed = json.loads(order_json)
    assert all(isinstance(x, str) for x in parsed), f"튜플이 들어갔다: {parsed[:2]}"


@pytest.mark.asyncio
async def test_저장_실패가_발송을_막지_않는다():
    from app.pipeline import _persist_lineup_rows

    class _Boom:
        async def execute(self, *a):
            raise RuntimeError("db down")

    jg = {"game_id": 7, "sport": "kbo",
          "research": {"home_lineup": {"order": "-".join(f"T{i}" for i in range(9))}}}
    assert await _persist_lineup_rows(_Boom(), jg) == 0


def test_sync_가_영속화를_부른다():
    src = open("app/pipeline.py", encoding="utf-8").read()
    i = src.index("async def sync_lineup_status")
    seg = src[i:src.index("\nasync def _persist_lineup_rows")]
    assert "await _persist_lineup_rows(pool, jg)" in seg


# ═══════════════ ③ 원장은 실제로 한 일만 적는다

def test_판정이_돌았을_때만_재판정을_기록한다():
    """🔴 실측 game=2881: `라인업 확정 반영` 이 30회 넘게 찍혔는데 판정이
    돈 것은 한 번뿐이었다. 하지도 않은 일을 적으면 아무것도 셀 수 없다."""
    src = open("app/pipeline.py", encoding="utf-8").read()
    i = src.index("async def rejudge_after_lineup")
    seg = src[i:src.index("\nasync def ", i + 10)]
    assert "judged = await _run_baseball_matchups(" in seg
    assert "if judged or sport not in BASEBALL_SPORTS:" in seg
