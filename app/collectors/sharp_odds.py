"""[무과금 전환 1b] SharpAPI 무료 티어 — MLB 2순위(교차검증·폴백).

무료 티어: 12 req/분 · 일 17,280콜 · 카드등록 불필요 · 60초 지연.
60초 지연은 우리 용도(경기 전 스냅샷)와 무관하다.

⚠️ **키가 없으면 조용히 비활성이다.** 계정 발급은 사람이 하는 일이라
   여기서 만들 수 없다. `SHARPAPI_KEY` 가 비면 빈 dict 를 돌려주고,
   `odds_free` 체인은 ESPN 결과만 쓴다 — 폴백이 없다고 수집이 죽지 않는다.

⚠️ h2h(머니라인)만 받는다. 스프레드·토탈은 요청하지 않는다 — 가치 게이트가
   쓰는 것은 승부 배당뿐이고, 안 쓰는 것을 받아 두면 그게 언젠가 판정에 샌다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PROVIDER = "sharp"
BASE = "https://api.sharpapi.com/v1"
TIMEOUT = 25.0
MAX_RETRIES = 3


def _key() -> str:
    from app.config import get_settings

    return (getattr(get_settings(), "sharpapi_key", "") or "").strip()


def enabled() -> bool:
    return bool(_key())


async def fetch_slate(date: str, sport: str = "mlb") -> dict[str, dict]:
    """`YYYY-MM-DD` → {event_id: {home, away, rows[]}}. 키 없으면 빈 dict."""
    import asyncio

    import httpx

    if not enabled():
        logger.info("[sharp_odds] SHARPAPI_KEY 없음 — 폴백 비활성")
        return {}
    url = f"{BASE}/odds/{sport}"
    last = None
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as c:
                r = await c.get(url, params={"date": date, "markets": "h2h"},
                                headers={"Authorization": f"Bearer {_key()}",
                                         "Accept": "application/json"})
                r.raise_for_status()
                return parse(r.json())
        except Exception as exc:
            last = exc
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)
    logger.warning("[sharp_odds] 조회 실패 %s: %s", date, last)
    return {}


def parse(data) -> dict[str, dict]:
    """응답 → 우리 계약. **구조가 어긋나면 빈 dict** — 지어내지 않는다.

    ⚠️ 실응답으로 검증하지 못했다(키 미발급, 2026-09-02). 키가 들어오면
       첫 호출 로그로 구조를 확인하고 이 함수를 실측에 맞춘다. 그때까지는
       ESPN 만으로 동작하며, 여기서 형태가 안 맞으면 조용히 0건이다.
    """
    events = data.get("events") if isinstance(data, dict) else data
    if not isinstance(events, list):
        logger.warning("[sharp_odds] 응답 구조 불일치 — 키 %s",
                       sorted(data)[:8] if isinstance(data, dict) else type(data))
        return {}
    out: dict[str, dict] = {}
    for ev in events:
        if not isinstance(ev, dict):
            continue
        home = (ev.get("home_team") or ev.get("home") or "").strip()
        away = (ev.get("away_team") or ev.get("away") or "").strip()
        if not home or not away:
            continue
        rows = []
        for bm in ev.get("bookmakers") or []:
            book = (bm.get("key") or bm.get("title") or "sharp").lower()
            for mk in bm.get("markets") or []:
                if (mk.get("key") or "") != "h2h":
                    continue
                for oc in mk.get("outcomes") or []:
                    try:
                        price = float(oc.get("price"))
                    except (TypeError, ValueError):
                        continue
                    if price > 1.0 and oc.get("name"):
                        rows.append({"book": book, "market": "h2h",
                                     "side": oc["name"], "line": None,
                                     "odds": round(price, 3)})
        if rows:
            out[str(ev.get("id") or f"{away}@{home}")] = {
                "home": home, "away": away, "rows": rows}
    return out
