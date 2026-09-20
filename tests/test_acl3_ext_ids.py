"""ACL-3 — 축구 슬레이트는 적재 함수의 **반환값이 곧 명단**이다.

🔴 실측 2026-09-15: ACL 8경기를 저장하고도 카드가 "축구 5경기"였고
   [v3]·[prob] 줄이 0이었다. DB 에는 `fotmob:6049977` 로 들어 있었는데
   반환값은 `fotmob:acl` × 8 이었다 — 하나도 안 맞는다.
   ⚠️ ext_id 재조회 분기(`pipeline.py:1476`)는 **야구 전용**이다.
"""
from __future__ import annotations

import inspect

import pytest

from app import pipeline as PL
from app.collectors import fotmob as FM


class _Pool:
    def __init__(self):
        self.rows = []

    async def fetchrow(self, sql, *a):
        # ⚠️ [FMR-1] `upsert_slate` 이 점수 충돌 확인차 기존 행을 읽는다.
        #    빈 DB 픽스처라 None(충돌 없음).
        return None

    async def execute(self, sql, *a):
        self.rows.append(a)


def _slate(n=2, bad=False):
    out = []
    for i in range(n):
        out.append({"id": 6049970 + i, "league": "AFC Champions League Elite East",
                    "ccode": "INT", "home": f"H{i}", "away": f"A{i}",
                    "utc": "2026-09-15T10:00:00.000Z"})
    if bad:                       # canonical 을 못 찾는 행 하나
        out.append({"id": 999, "league": "AFC Champions League Elite East",
                    "ccode": "INT", "home": "", "away": "X",
                    "utc": "2026-09-15T10:00:00.000Z"})
    return out


@pytest.mark.asyncio
async def test_upsert_slate가_실제_ext_id를_돌려준다(monkeypatch):
    monkeypatch.setattr(FM, "slate", lambda _d: _ok(_slate(2)))
    p = _Pool()
    out = await FM.upsert_slate(p, "20260915", league_key="acl")
    assert out["ext_ids"] == ["fotmob:6049970", "fotmob:6049971"]
    assert [a[1] for a in p.rows] == out["ext_ids"], "DB 에 넣은 값과 다르다"


async def _ok(v):
    return v


@pytest.mark.asyncio
async def test_saved와_ext_ids_길이가_같다(monkeypatch):
    monkeypatch.setattr(FM, "slate", lambda _d: _ok(_slate(3)))
    out = await FM.upsert_slate(_Pool(), "20260915", league_key="acl")
    assert out["saved"] == len(out["ext_ids"]) == 3


@pytest.mark.asyncio
async def test_제외된_경기는_ext_ids에_없다(monkeypatch):
    """🔴 조용한 누락 금지 — 제외했으면 명단에도 없어야 한다."""
    monkeypatch.setattr(FM, "slate", lambda _d: _ok(_slate(1, bad=True)))
    out = await FM.upsert_slate(_Pool(), "20260915", league_key="acl")
    assert out["saved"] == 1 and len(out["ext_ids"]) == 1
    assert out["skipped"], "제외했는데 기록이 없다"
    assert "fotmob:999" not in out["ext_ids"]


def test_호출부가_ext_ids를_그대로_더한다():
    src = inspect.getsource(PL._load_soccer_fixtures)
    assert 'out += list(_r.get("ext_ids") or [])' in src
    assert 'f"fotmob:{_k}"' not in src, "리그키를 ext_id 로 쓰고 있다"


def test_형제_적재함수와_반환_계약이_같다():
    """🔴 축구 슬레이트는 이 반환값이 전부다 — 셋이 같은 모양이어야 한다."""
    src = inspect.getsource(PL._load_soccer_fixtures)
    # 세 소스 모두 `out +=` 로 **목록**을 더한다(개수가 아니라).
    assert src.count("out +=") == 3, src.count("out +=")
    assert "out += await upsert_games_from_football_data" in src
    assert "out += await upsert_games_from_odds_events" in src
