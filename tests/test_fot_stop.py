"""[FOT-STOP / 결정 1a] FotMob **대량 호출 중단.**

사용자 결정 2026-09-21: "결정 1 (FotMob): 끄는 방향. 순서 —
  a. 즉시: FotMob 대량 호출 중단(1-i-3 소급 날짜 루프·신규 확장 금지)."

🔴 **일일 호출 수를 먼저 쟀다(계산값):**
```
satellite_15m  96회/일 × 축구 26경기 × 2호출
   slate(날짜)      2,496   ← 같은 날짜를 **매 경기마다 다시 받는다**
   matchDetails     2,496
finals_job · upsert_slate                22
────────────────────────────────────────────
하루 합계        ≈ 5,014 회 · 그중 중복 slate **2,400회(48%)**
```
🔴 **절반이 순수한 낭비였다.** `attach` 가 경기마다 `slate(날짜)` 를 새로
   받는데, 같은 사이클의 26경기가 **같은 날짜**다.

⚠️ 축구 경기 수는 실측이다(최근 7일 평균 26.1경기/일).
⚠️ MIN_GAP_SEC=2 라 한 사이클 52호출 = 104초 — 15분 주기 안에 들어간다.
   즉 계산값이 실제로 나간다.
"""
from __future__ import annotations

import pytest


def test_소급_날짜_루프는_막혀_있다():
    """🔴 `backfill(dates)` 은 날짜마다 slate + 경기마다 matchDetails 를 돈다 —
    45일치면 수백 호출이다. **사용자 승인 없이는 안 돈다.**"""
    import inspect

    from app.collectors import fotmob

    src = inspect.getsource(fotmob.backfill)
    assert "bulk_allowed" in src, "대량 루프에 관문이 없다"


@pytest.mark.asyncio
async def test_소급_루프를_부르면_막힌다(monkeypatch):
    from app.collectors import fotmob

    called: list = []

    async def _spy(*a, **k):
        called.append(a)
        return []

    monkeypatch.setattr(fotmob, "slate", _spy)
    out = await fotmob.backfill(None, ["20260901", "20260902"])
    assert called == [], "막혔는데 요청이 나갔다"
    assert out.get("blocked"), out


@pytest.mark.asyncio
async def test_승인하면_돈다(monkeypatch):
    """⚠️ 끄는 것이 아니라 **관문**이다 — 사용자가 켜면 돈다."""
    from app.collectors import fotmob

    called: list = []

    async def _spy(d):
        called.append(d)
        return []

    monkeypatch.setattr(fotmob, "slate", _spy)
    await fotmob.backfill(None, ["20260901"], bulk_allowed=True)
    assert called == ["20260901"]


@pytest.mark.asyncio
async def test_같은_사이클의_slate_를_다시_받지_않는다(monkeypatch):
    """🔴 **하루 2,400회(48%)가 이 중복이었다.**

    같은 날짜를 경기마다 다시 받고 있었다. 한 번만 받아 나눠 쓴다.
    """
    from app.collectors import fotmob

    hits: list[str] = []

    async def _slate(d):
        hits.append(d)
        return [{"id": "1", "home": "AC Milan", "away": "Inter",
                 "league": "Serie A", "ccode": "ITA", "utc": None}]

    async def _lineup(mid):
        return None

    monkeypatch.setattr(fotmob, "_get_slate_uncached", _slate)
    monkeypatch.setattr(fotmob, "match_lineup", _lineup)
    fotmob.clear_slate_cache()
    for _ in range(5):
        await fotmob.attach({"home": "AC Milan", "away": "Inter",
                             "starts_at": None}, date_yyyymmdd="20260921")
    assert len(hits) == 1, f"같은 날짜를 {len(hits)}번 받았다"


@pytest.mark.asyncio
async def test_캐시는_날짜별로_갈린다(monkeypatch):
    from app.collectors import fotmob

    hits: list[str] = []

    async def _slate(d):
        hits.append(d)
        return [{"id": d, "home": "A", "away": "B"}]

    monkeypatch.setattr(fotmob, "_get_slate_uncached", _slate)
    fotmob.clear_slate_cache()
    await fotmob.slate("20260921")
    await fotmob.slate("20260922")
    await fotmob.slate("20260921")
    assert hits == ["20260921", "20260922"], hits


@pytest.mark.asyncio
async def test_빈손은_캐시하지_않는다(monkeypatch):
    """🔴 실패를 굳히면 안 된다. 한 번 빈손이 TTL 동안 빈손으로 남으면
    그 사이 자료가 들어와도 못 본다."""
    from app.collectors import fotmob

    hits: list[str] = []

    async def _slate(d):
        hits.append(d)
        return []

    monkeypatch.setattr(fotmob, "_get_slate_uncached", _slate)
    fotmob.clear_slate_cache()
    await fotmob.slate("20260921")
    await fotmob.slate("20260921")
    assert len(hits) == 2, "빈손을 캐시했다"


def test_캐시가_영원하지_않다():
    """⚠️ 진행 중인 경기 상태가 바뀐다 — 오래 들고 있으면 안 된다."""
    from app.collectors import fotmob

    assert 0 < fotmob.SLATE_TTL_SEC <= 600
