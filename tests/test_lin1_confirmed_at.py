"""[LIN-1] KBO·NPB 는 확정 시각을 **한 번도 적은 적이 없다.**

🔴 실측 2026-09-19:
     최근 7일 npb 33경기 · 확정 0    ← lineup_confirmed_at 기준
     최근 7일 kbo 61경기 · 확정 0
   그런데 오늘 NPB 3경기는 `lineup_status='confirmed'` 다. 상태는 올라가는데
   **시각이 안 적힌다.**

🔴 확정을 쓰는 경로가 **둘**이고 한쪽만 시각을 적는다:
     app/collectors/lineups.py:258   (MLB)
        SET lineup_status = $2,
            lineup_confirmed_at = CASE WHEN $2='confirmed' THEN now() ELSE ... END
     app/pipeline.py:785  sync_lineup_status  (KBO·NPB)
        SET lineup_status = 'confirmed', updated_at = now()      ← 시각이 없다

   그래서 MLB 는 "라인업이 T-190분에 떴다"를 잴 수 있고(1-2 실측),
   KBO·NPB 는 **영원히 못 잰다.**
⚠️ 되돌리지 않는다 — 이미 적힌 시각을 덮지 않는다(첫 확정이 사실이다).
"""
from __future__ import annotations

import inspect
import re


def test_두_경로가_같은_칸을_적는다():
    from app.pipeline import sync_lineup_status

    src = inspect.getsource(sync_lineup_status)
    assert "lineup_confirmed_at" in src, \
        "KBO·NPB 경로가 확정 시각을 적지 않는다"


def test_이미_적힌_시각을_덮지_않는다():
    """🔴 첫 확정이 사실이다. 재판정 때마다 갱신하면 T-N 이 0 에 수렴한다."""
    from app.pipeline import sync_lineup_status

    src = inspect.getsource(sync_lineup_status)
    assert re.search(r"COALESCE\s*\(\s*games\.lineup_confirmed_at", src) or \
        "lineup_confirmed_at IS NULL" in src, src


def test_MLB_경로는_그대로다():
    """⚠️ 반대 위험 — 고치려다 이미 되던 쪽을 깨지 않는다."""
    from app.collectors import lineups as L

    src = inspect.getsource(L)
    assert "lineup_confirmed_at = CASE WHEN" in src
