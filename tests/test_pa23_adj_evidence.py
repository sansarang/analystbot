"""PA-23 계약 — 변수마다 근거를 남긴다 (지시문 5단계).

> 각 변수는 **(name, value, delta_pp, source, evidence)** 튜플로 원장에 남김.

🔴 **`adj_pp` 모양은 안 바꿨다.** 소비자가 다섯이다(실측):
     pipeline:2861 · pick_ledger 합산(PA-16) · pick_ledger:1260 ·
     analyze:85(`{v:+g}` — 숫자 가정) · confidence:209(len)
   모양을 바꾸면 그 다섯이 조용히 깨진다. `delta_pp` 는 `adj_pp`,
   나머지(value·source·evidence)는 새 칸이 맡는다.
"""
import asyncio
import json
import pathlib

import pytest

from app.collectors.lineups import STATUS_CONFIRMED
from app.engine import adjust as A


class _Pool:
    async def fetch(self, sql, *a):
        return []

    async def fetchval(self, sql, *a):
        return None


def _jg(**over):
    jg = {"game_id": 7, "sport": "mlb", "home": "Orix", "away": "SoftBank",
          "starts_at": "2026-09-18T09:00:00+00:00",
          "lineup_status": STATUS_CONFIRMED, "_redis": None,
          "research": {"today_nine": {"home": ["X"], "away": ["Y"]}}}
    jg.update(over)
    return jg


@pytest.fixture
def attached():
    jg = _jg()
    asyncio.run(A.attach(jg, _Pool()))
    return jg


def test_근거가_만들어진다(attached):
    ev = attached.get("adj_evidence")
    assert ev, "adj_evidence 가 비었다"
    for name, box in ev.items():
        assert set(box) >= {"value", "source", "evidence"}, name


def test_근거는_사람이_읽을_수_있다(attached):
    """🔴 "이 −2%p 가 어디서 왔나"에 답해야 한다 — 숫자만으로는 못 답한다."""
    for box in attached["adj_evidence"].values():
        assert isinstance(box["evidence"], str) and len(box["evidence"]) >= 8
        assert box["source"], "출처가 비었다"


def test_출처는_실재하는_소스다(attached):
    ok = {"lineup_events", "pitcher_appearances", "games", "statcast"}
    for name, box in attached["adj_evidence"].items():
        assert box["source"] in ok, (name, box["source"])


def test_값이_없으면_남기지_않는다():
    """🔴 반대 위험 — 지어내지 않는다. 못 잰 변수는 근거도 없다."""
    jg = _jg(lineup_status="none")          # 타순 미확정 → 결장 미계산
    asyncio.run(A.attach(jg, _Pool()))
    assert "주전결장" not in (jg.get("adj_evidence") or {})


def test_adj_pp_모양은_안_바뀐다(attached):
    """🔴 반대 위험 — 소비자 다섯이 숫자 dict 를 가정한다."""
    adj = attached.get("adj_pp")
    if adj:
        assert all(isinstance(v, (int, float)) for v in adj.values())


def test_analyze_렌더가_안_깨진다(attached):
    """`analyze:85` 가 `f"{k} {v:+g}"` 로 찍는다 — 숫자여야 한다."""
    for v in (attached.get("adj_pp") or {}).values():
        assert f"{v:+g}"


def test_원장이_근거를_저장한다():
    src = pathlib.Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    assert '"adj_evidence"' in src
    assert "adj_evidence," in src, "INSERT 칸 목록에 없다"
    assert "$22::jsonb" in src, "자리표가 jsonb 가 아니다"


def test_INSERT_자리표_수가_맞는다():
    """🔴 칸을 늘리고 자리표를 안 늘리면 저장이 통째로 터진다."""
    src = pathlib.Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    blk = src.split("INSERT INTO pick_ledger")[1].split('"""')[0]
    cols = blk.split("(", 1)[1].split(")")[0]
    n_cols = len([c for c in cols.replace("\n", " ").split(",") if c.strip()])
    vals = blk.split("VALUES")[1]
    n_vals = len([v for v in vals.split(",") if v.strip()])
    assert n_cols == n_vals, f"칸 {n_cols} vs 값 {n_vals}"


def test_칸이_스키마에_있다():
    src = pathlib.Path("db/schema.sql").read_text(encoding="utf-8")
    assert "adj_evidence JSONB" in src


def test_근거가_JSON으로_직렬화된다(attached):
    s = json.dumps(attached["adj_evidence"], ensure_ascii=False)
    assert json.loads(s) == attached["adj_evidence"]
