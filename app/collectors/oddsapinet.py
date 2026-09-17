"""[ODN-1 2026-09-17] odds-api.net — **KBO·NPB 총점·핸디·팀토탈.**

앞서 셋이 막혔다(실측 2026-09-17):
  배트맨      엔드포인트 전부 폐기 (`registry` wired=False)
  oddsportal  리그 페이지에 승패(bettingTypeId 3)뿐 — 총점은 JS 뒤
  betexplorer 경기 페이지 `data-odd` 는 **과거 상대전적** 배당이었다

여기는 된다:
  /events?sport=baseball → KBO 2 · NPB 5 (오늘) · 경기당 북 44
  /events/{id}/odds/snapshot → 1,405행
    total/over 7.5 33북 · handicap/home -1.5 39북 · team total 272행
  **Pinnacle 이 북 목록에 있다** — `book_gap`(샤프 대 사설)이 처음 제 일을 한다.

🔴 **월 1,000 크레딧(sandbox)** 이다. 기존 30분 주기로 붙이면 월 11,520콜이
   필요해 이틀이면 끝난다. 그래서 **KBO·NPB 만 · 하루 2회**로 따로 돈다.
   기존 `odds_snapshot_30m`(ESPN·oddsportal, 무료 무제한)은 **안 건드린다** —
   거기서 CLV 와 라인 이동 스냅샷이 나온다.
🔴 **예산 가드가 먼저다.** `/usage` 를 읽어 80% 를 넘으면 멈추고 로그를 남긴다.
⚠️ 키가 없으면 **조용히 비활성**이다(절대 규칙 3 — 키 부재로 크래시하지 않는다).
⚠️ 키는 `.env` 에만 둔다. 코드·커밋·로그에 남기지 않는다.
"""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

PROVIDER = "oddsapinet"
BASE = "https://api.odds-api.net/v1"
TIMEOUT = 30.0

#: 🔴 이 리그만. MLB·축구는 ESPN 무료로 이미 된다 — 크레딧을 아낀다.
LEAGUES = {"kbo": "Korean KBO", "npb": "Japan NPB"}

#: 🔴 **정규 이닝만.** 실측에서 첫 행이 `5 innings` 였다 — 섞으면 라인이
#   통째로 어긋난다(5이닝 −0.5 와 정규 −1.5 는 다른 시장이다).
PERIOD = "full time"

#: 우리 스키마 이름으로. 🔴 `odds_snapshots.market` 값이 원본이다.
MARKET_MAP = {"total": "totals", "handicap": "spreads",
              "team total": "team_totals"}

#: 예산 가드. 이 비율을 넘으면 **멈춘다.** 조용히 초과하면 다음 달까지 죽는다.
BUDGET_STOP_RATIO = 0.8


def _key() -> str:
    from app.config import get_settings

    return (getattr(get_settings(), "oddsapinet_key", "") or "").strip()


def _num(v):
    """`"+0.5"`·`"7.5"` → 숫자. 못 읽으면 None(지어내지 않는다)."""
    try:
        return float(str(v).replace("+", "").strip())
    except (TypeError, ValueError):
        return None


async def _get(path: str, params: dict | None = None):
    """GET 한 번. 키가 없거나 실패하면 None — 예외를 올리지 않는다."""
    key = _key()
    if not key:
        return None
    import httpx

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(BASE + path, params=params,
                            headers={"X-API-Key": key,
                                     "Accept": "application/json"})
        if r.status_code != 200:
            logger.info("[oddsapinet] %s → %s", path, r.status_code)
            return None
        return r.json()
    except Exception as exc:
        logger.warning("[oddsapinet] %s 실패: %s", path, exc)
        return None


async def budget_ok() -> bool:
    """남은 크레딧이 문턱 안인가. **모르면 멈춘다**(안전한 쪽).

    🔴 월 1,000 이다. 조용히 넘기면 다음 달까지 이 소스가 죽는다.
    """
    j = await _get("/usage")
    if not isinstance(j, dict):
        return False
    lim = j.get("api_credits_limit") or j.get("limit")
    used = j.get("api_credits_used") or j.get("used")
    if not lim:
        return False
    ratio = float(used or 0) / float(lim)
    if ratio >= BUDGET_STOP_RATIO:
        logger.warning("[oddsapinet] 예산 %.0f%% 사용 (%s/%s) — 멈춘다",
                       ratio * 100, used, lim)
        return False
    logger.info("[oddsapinet] 예산 %.0f%% 사용 (%s/%s)", ratio * 100, used, lim)
    return True


async def fetch_events(sport: str, *, hours_back: int = 6,
                       hours_ahead: int = 30) -> list[dict]:
    """그 리그의 경기 목록. ⚠️ `start_from`·`start_to` 는 **epoch 정수**다."""
    lg = LEAGUES.get((sport or "").lower())
    if not lg:
        return []
    now = int(time.time())
    j = await _get("/events", params={
        "sport": "baseball", "league": lg,
        "start_from": now - hours_back * 3600,
        "start_to": now + hours_ahead * 3600, "limit": 100})
    return list((j or {}).get("items") or [])


async def fetch_odds(event_id) -> list[dict]:
    """경기 하나의 배당 스냅샷 행."""
    j = await _get(f"/events/{event_id}/odds/snapshot", params={"limit": 4000})
    return list((j or {}).get("items") or [])


def to_rows(items: list[dict], *, home: str, away: str) -> list[dict]:
    """API 행 → `odds_snapshots` 행. **버리는 규칙이 본체다.**

    🔴 `is_available` 이 거짓이면 버린다 — 닫힌 배당을 시장으로 읽으면 안 된다.
    🔴 `period` 가 정규 이닝이 아니면 버린다(5이닝은 다른 시장이다).
    🔴 라인이 없으면 버린다 — 라인 없는 총점·핸디는 쓸 수 없다.
    ⚠️ 승패(moneyline)는 **안 싣는다.** oddsportal 이 이미 준다 — 두 소스가
       같은 칸을 채우면 디빅이 흔들린다.
    """
    out = []
    for it in items or []:
        if not isinstance(it, dict) or it.get("is_available") is False:
            continue
        if (it.get("period") or "") != PERIOD:
            continue
        market = MARKET_MAP.get(it.get("bet_type") or "")
        if not market:
            continue
        odds = _num(it.get("odds"))
        line = _num(it.get("line"))
        if odds is None or odds <= 1.0 or line is None:
            continue
        side = str(it.get("side") or "").lower()
        if market == "totals":
            name = "Over" if side.startswith("o") else "Under"
        else:
            name = home if side == "home" else away if side == "away" else None
            if market == "team_totals":
                # 팀토탈은 `selection_name` 이 팀이다(side 는 over/under).
                name = str(it.get("selection_name") or "").strip() or None
        if not name:
            continue
        # ⚠️ 핸디는 API 가 **쪽마다 라인을 따로** 준다(home −1.5 / away +1.5) —
        #    부호를 우리가 뒤집지 않는다. ESPN 경로(홈 기준 하나)와 다르다.
        out.append({"book": str(it.get("bookmaker") or "").strip() or "?",
                    "market": market, "side": name,
                    "line": line, "odds": odds})
    return out
