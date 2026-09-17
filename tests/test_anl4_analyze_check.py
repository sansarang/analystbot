"""ANL-4 계약 — L1·L2·금지어 판정이 **원장에 남는다.**

🔴 실측 2026-09-17: 배포 직후 분석이 살아났는데 그 값이
   `L1=(False, '결정축_근거 에 확률·배당 숫자가 있다')` 였다. 원장에는
   `main_axis='주전 결장'` 만 남아 **반려당한 값인지 알 수 없었다.**
🔴 로그에만 있으면 재배포 때 날아간다 — 오늘 실제로 그래서 원인을 못 봤다.
   `llm_winner`·`model`·`analyze_model` 에 이어 **네 번째** 같은 병이다.
⚠️ 반려가 원장을 막지는 않는다(ANL-2 에서 잠근 성질) — **반려당했다는 사실이
   옆에 남을 뿐**이다.
"""
import inspect
import json
import re

import pytest

from app.engine import analyze as AN
from app.engine import pick_ledger as PL


def test_통과도_반려도_남는다():
    ok = AN.check_row(True, "", True, "", [], None)
    no = AN.check_row(False, "숫자가 있다", True, "", [], None)
    assert ok["l1"] is True and ok["l1_why"] is None
    assert no["l1"] is False and no["l1_why"] == "숫자가 있다"


def test_금지어가_남는다():
    assert AN.check_row(True, "", True, "", ["확실"], None)["banned"] == ["확실"]


def test_왜_못했는지도_남는다():
    """🔴 '안 했다'와 '했는데 반려'는 다르다."""
    r = AN.check_row(None, None, None, None, [], "JSON 이 아니다")
    assert r["skipped"] == "JSON 이 아니다" and r["l1"] is None


def test_JSON으로_직렬화된다():
    r = AN.check_row(False, "why", False, "why2", ["확실"], None)
    assert json.loads(json.dumps(r, ensure_ascii=False)) == r


# ── run 이 세 가지 길 모두에서 남긴다

def test_run이_세_길_모두에서_남긴다():
    src = inspect.getsource(AN.run)
    assert src.count('["analyze_check"]') + src.count('"analyze_check"] =') >= 3 \
        or src.count("analyze_check") >= 3, "실패 가지 두 곳 + 정상 한 곳"


def test_반려해도_결정축은_남는다():
    """🔴 ANL-2 에서 잠근 성질 — 이번에도 안 바뀐다."""
    tail = inspect.getsource(AN.run).split("ok1, why1 = l1(", 1)[1]
    assert "to_ledger(parsed" in tail
    assert "failed=True" not in tail


# ── 원장 저장

def test_저장_SQL이_칸을_적는다():
    assert "analyze_check" in PL._ANALYZE_SAVE


@pytest.mark.asyncio
async def test_자리표_수가_실제로_맞는다():
    """🔴 PA-23 에서 칸만 늘리고 $N 을 안 늘려 저장이 통째로 터질 뻔했다.

    ⚠️ **글자를 세지 않는다.** 처음에 소스에서 쉼표를 세다가 `led.get("…")` 의
       괄호에 걸려 틀렸다. **실제로 부르고 넘어간 인자 수**를 센다.
    """
    from app.engine import gate as G

    n = max(int(x) for x in re.findall(r"\$(\d+)", PL._ANALYZE_SAVE))
    assert n == 10

    saved = []

    class _Conn:
        async def fetchrow(self, sql, *a):
            if "FROM games" in sql:
                return {"id": 1, "sport": "mlb", "league": "MLB",
                        "home": "H", "away": "A", "starts_at": None}
            return {"hypothesis": {}, "p_code": 0.62, "adj_pp": {},
                    "p_market": 0.55, "predicted_side": "home",
                    "confidence": "중"}

        async def fetch(self, sql, *a):
            return []

        async def execute(self, sql, *a):
            saved.append((sql, a))

    async def _fake(*a, **k):
        return {"ledger": {"main_axis": "축", "analyze_check":
                           AN.check_row(False, "숫자", True, "", [], None)}}

    import unittest.mock as mock

    with mock.patch.object(AN, "run", _fake):
        await PL.record_confirm_and_analysis(
            _Conn(), game_id=1, gate={"label": G.OVER, "gap_pp": -9.0},
            redis=None)
    hits = [a for sql, a in saved if "analyze_check" in sql]
    assert hits, "분석 저장이 안 일어났다"
    assert len(hits[-1]) == n, f"자리표 {n} 개인데 인자 {len(hits[-1])} 개"
    assert json.loads(hits[-1][9])["l1"] is False


def test_칸이_스키마에_있다():
    import pathlib

    sql = pathlib.Path("db/schema.sql").read_text(encoding="utf-8")
    assert "analyze_check" in sql


# ── 🔴 반대 위험

def test_검사_자체를_안_바꿨다():
    """🔴 판정 기준이 바뀌면 이 커밋이 재는 대상 자체를 흔든다."""
    src = inspect.getsource(AN.l1)
    assert "NO_NUM_KEYS" in src and "REASON_BANNED" in src
    assert "analyze_check" not in src
    assert "analyze_check" not in inspect.getsource(AN.l2)


@pytest.mark.parametrize("bad", ["send", "dispatch", "telegram"])
def test_발송을_켜지_않는다(bad):
    assert bad not in inspect.getsource(AN.check_row).lower()
