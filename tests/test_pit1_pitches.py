"""[PIT-1] 투구수를 파서가 뽑는데 DB 가 버리고 있었다.

🔴 실측: `mlb_boxscore.py:68` 이 `row["pitches"] = pit` 를 넣고 있다
   (`numberOfPitches` · `pitchesThrown` 둘 다 본다). KBO 박스스코어에도
   투구수 칸이 있고 NPB 야후 파서도 `pitches` 를 넣는다.
   그런데 `pitcher_appearances` 에 **그 컬럼이 없다** — 적재에서 통째로
   사라졌다. export 는 `"pitches": None, "pitches_reason": "투구수 저장 없음"`
   을 적고 있었다.
🔴 투구수는 로커 65구 같은 **한도 신호**의 원천이다 — 그게 없으면
   `innings_cap_flag` 를 지어낼 수밖에 없다.
"""
from __future__ import annotations

import pathlib
import re

SCHEMA = (pathlib.Path(__file__).resolve().parents[1] / "db" / "schema.sql"
          ).read_text(encoding="utf-8")


def test_컬럼이_스키마에_있다():
    assert re.search(r"ADD COLUMN IF NOT EXISTS\s+pitches\b", SCHEMA)


def test_적재가_투구수를_싣는다():
    import inspect

    from app.collectors import pitcher_log as P

    src = inspect.getsource(P)
    assert "pitches" in src.split("INSERT INTO pitcher_appearances")[1][:400]
    assert 'p.get("pitches")' in src, "파서가 준 값을 넘기지 않는다"


def test_days_rest_는_뺄셈이다():
    from app.export.for_fable import days_rest

    assert days_rest("2026-09-19", "2026-09-13") == 6
    assert days_rest("2026-09-19", None) is None
    assert days_rest(None, "2026-09-13") is None


def test_한도_깃발은_두_조건_중_하나다():
    """🔴 최근 3등판 중 **2회 이상** 투구수 ≤ 75, **또는** 오프너 뒤 등판 1회 이상."""
    from app.export.for_fable import innings_cap_flag

    assert innings_cap_flag([{"pitches": 70}, {"pitches": 72}, {"pitches": 95}]) is True
    assert innings_cap_flag([{"pitches": 70}, {"pitches": 95}, {"pitches": 98}]) is False
    assert innings_cap_flag([{"pitches": 70}, {"pitches": 95}],
                            after_opener=1) is True


def test_투구수를_모르면_깃발도_모른다():
    """🔴 **지어내지 않는다.** 투구수가 없으면 `False` 가 아니라 `None` 이다 —
       "한도가 없다"와 "모른다"는 다르다."""
    from app.export.for_fable import innings_cap_flag

    assert innings_cap_flag([{"pitches": None}, {"pitches": None}]) is None
    assert innings_cap_flag([]) is None
