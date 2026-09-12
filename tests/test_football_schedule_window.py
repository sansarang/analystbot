"""SOC-3 — 축구 일정 창이 KST 하루를 덮지 못했다. 저녁 경기가 통째로 없었다.

🔴 **실측 2026-09-12 (운영, football-data.org 실호출).**
   API 는 `dateTo` 를 **그날 00:00 시각까지**로 본다:

     from=2026-09-12 to=2026-09-12  → 1건  (2026-09-12T00:00:00Z 하나)
     from=2026-09-12 to=2026-09-13  → 49건 (09-12 UTC 48 + 09-13 00:00 1)

   우리 코드는 `dateFrom=D-1, dateTo=D` 였다. 그래서 **UTC D-1 하루만** 받았다.
   KST 날짜 D 는 UTC `[D-1 15:00, D 15:00)` 인데, 뒤쪽 `D 00:00~15:00`
   (= **KST D 09:00~24:00**)이 통째로 빠졌다.

   그날 실제로 놓친 것: KST 22:00 세리에A 1 · 22:30 분데스 5 · 23:00 EPL 5.
   함수 독스트링은 "UTC로는 전날 15:00~당일 15:00"이라고 **맞게** 적혀 있었다 —
   의도는 옳았고 파라미터만 틀렸다. 상태값(HTTP 200)은 아무것도 알려주지 않았다.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.collectors.football import FootballDataClient

KST = timezone(timedelta(hours=9))


@pytest.mark.asyncio
async def test_일정_창이_KST_하루를_전부_덮는다(monkeypatch):
    seen = {}

    async def _get(self, path, **kw):
        seen.update(kw.get("params") or {})
        return {"matches": []}

    monkeypatch.setattr(FootballDataClient, "_get", _get, raising=True)
    c = FootballDataClient(mock=False)
    await c.fetch_matches("2026-09-12")

    lo = date.fromisoformat(seen["dateFrom"])
    hi = date.fromisoformat(seen["dateTo"])
    # 🔴 `dateTo` 는 그 날짜의 00:00 까지다 — 하루를 덮으려면 **다음 날**이어야 한다.
    assert lo == date(2026, 9, 11), seen
    assert hi == date(2026, 9, 13), seen

    # KST 하루의 양 끝이 창 안에 있는가 (경계를 손으로 적지 않고 계산한다)
    start = datetime(2026, 9, 12, 0, 0, tzinfo=KST).astimezone(timezone.utc)
    end = datetime(2026, 9, 13, 0, 0, tzinfo=KST).astimezone(timezone.utc)
    assert lo <= start.date(), (lo, start)
    assert end.date() <= hi, (hi, end)


@pytest.mark.asyncio
async def test_KST_저녁_경기가_창에_든다(monkeypatch):
    """🔴 실제로 놓쳤던 시각. KST 22:30 = 같은 날 13:30Z 다."""
    seen = {}

    async def _get(self, path, **kw):
        seen.update(kw.get("params") or {})
        return {"matches": []}

    monkeypatch.setattr(FootballDataClient, "_get", _get, raising=True)
    await FootballDataClient(mock=False).fetch_matches("2026-09-12")

    kickoff = datetime(2026, 9, 12, 13, 30, tzinfo=timezone.utc)
    lo = date.fromisoformat(seen["dateFrom"])
    hi = date.fromisoformat(seen["dateTo"])
    assert lo <= kickoff.date() < hi, (seen, kickoff)
