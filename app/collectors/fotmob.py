"""[FOT-1] FotMob — 라인업·결장을 **구조 JSON 으로** 받는다 (사용자 지시).

🔴 **추출 1순위는 LLM 이 아니라 이것이다.** 기사에서 뽑던 방식은 groq 무료
   한도에 막혔고(실측 2026-09-14: 429 백오프 340~527초), 뽑아도 로마 `out` 이
   비었다. 같은 사실이 FotMob JSON 에는 칸으로 들어 있다.

🔴 **경로는 실측한 것을 쓴다.** 지시문의 `/api/matches`·`/api/matchDetails` 는
   404(HTML)였고, 실제로 200 을 주는 것은 `/api/data/...` 다 (실측 2026-09-14).

🔴 **`unavailable` 키가 없는 것은 "결장 0명"이 아니라 "모른다"** 다.
   실측: 토리노에는 있고 로마에는 **키 자체가 없었다.** None 으로 돌려주고
   호출부가 교차검증(API-Football)·`missing` 으로 넘긴다.

⚠️ UA·Referer 헤더가 필요하다. 요청 간격 2초(사용자 지시).
⚠️ 이 모듈은 **받아서 모양만 고른다.** 판정·가공은 호출부의 일이다.
"""
from __future__ import annotations

import asyncio
import logging
import time
import unicodedata

logger = logging.getLogger(__name__)

BASE = "https://www.fotmob.com/api/data"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "application/json",
           "Referer": "https://www.fotmob.com/"}

#: 요청 최소 간격(초) — 사용자 지시.
MIN_GAP_SEC = 2.0
TIMEOUT = 25

#: 라인업 단계. 🔴 **그대로 저장한다** — T-60 재호출에서 이 값이 바뀌는 것이
#  Part 1-B 이동 분류의 입력이다.
PREDICTED, CONFIRMED = "predicted", "confirmed"

_last_at = 0.0


async def _pace() -> None:
    global _last_at
    gap = MIN_GAP_SEC - (time.monotonic() - _last_at)
    if _last_at and gap > 0:
        await asyncio.sleep(gap)
    _last_at = time.monotonic()


async def _get(path: str, params: dict) -> dict | None:
    """실패는 **결측**이다 — 예외를 올리지 않고 None 을 준다."""
    import httpx

    await _pace()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True,
                                     headers=HEADERS) as c:
            r = await c.get(f"{BASE}/{path}", params=params)
        if r.status_code != 200:
            logger.warning("[fotmob] %s %s — status %s", path, params, r.status_code)
            return None
        return r.json()
    except Exception as exc:
        logger.warning("[fotmob] %s %s 실패: %s", path, params, exc)
        return None


def norm(name: str) -> str:
    """비교용 정규화. 🔴 퍼지 금지 — 악센트·기호만 지운다."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace("-", " ").split())


async def slate(date_yyyymmdd: str) -> list[dict]:
    """그 날짜의 전 경기. `[{id, league, home, away, utc}]`. 실패면 빈 목록."""
    d = await _get("matches", {"date": date_yyyymmdd})
    out: list[dict] = []
    for lg in (d or {}).get("leagues") or []:
        for m in lg.get("matches") or []:
            out.append({
                "id": m.get("id"),
                "league": lg.get("name"),
                "ccode": lg.get("ccode"),
                "home": ((m.get("home") or {}).get("name")),
                "away": ((m.get("away") or {}).get("name")),
                "utc": ((m.get("status") or {}).get("utcTime")),
            })
    logger.info("[fotmob] %s — %d경기", date_yyyymmdd, len(out))
    return out


def find_match(rows: list[dict], *, home: str, away: str) -> dict | None:
    """우리 경기 ↔ FotMob 경기. **양쪽 이름이 다 맞아야** 붙인다.

    🔴 퍼지 유사도를 쓰지 않는다(AC밀란 오매칭 전례). 정규화 후 한쪽이
       다른 쪽을 **포함**하면 같은 팀으로 본다(`Torino` ⊂ `Torino FC`).
    """
    h, a = norm(home), norm(away)
    for r in rows or []:
        rh, ra = norm(r.get("home")), norm(r.get("away"))
        if not rh or not ra:
            continue
        if (rh in h or h in rh) and (ra in a or a in ra):
            return r
    return None


def _players(side: dict) -> list[dict]:
    """선발 명단 → `[{id, name}]`. 🔴 **id 를 반드시 싣는다** — 주전 판정은
    이름이 아니라 id 로 센다(사용자 지시)."""
    out: list[dict] = []
    for grp in (side or {}).get("starters") or []:
        items = grp if isinstance(grp, list) else [grp]
        for x in items:
            if isinstance(x, dict) and (x.get("id") or x.get("name")):
                out.append({"id": x.get("id"), "name": x.get("name") or x.get("fullName")})
    return out


def _unavailable(side: dict):
    """결장 명단. 🔴 **키가 없으면 None**(모른다) — 빈 목록(0명)과 다르다."""
    if "unavailable" not in (side or {}):
        return None
    out = []
    for x in (side.get("unavailable") or []):
        if not isinstance(x, dict):
            continue
        u = x.get("unavailability") or {}
        out.append({"id": x.get("id"), "name": x.get("name"),
                    "type": u.get("type"), "expected_return": u.get("expectedReturn")})
    return out


def parse_lineup(details: dict) -> dict | None:
    """matchDetails → 라인업 요약. 없으면 None."""
    lu = ((details or {}).get("content") or {}).get("lineup") or {}
    if not lu.get("homeTeam") and not lu.get("awayTeam"):
        return None
    out = {"lineup_type": lu.get("lineupType"), "source": lu.get("source"),
           "match_id": lu.get("matchId")}
    for key, side in (("home", "homeTeam"), ("away", "awayTeam")):
        t = lu.get(side) or {}
        out[key] = {
            "team_id": t.get("id"), "team": t.get("name"),
            "formation": t.get("formation"),
            "starters": _players(t),
            "bench": [{"id": x.get("id"), "name": x.get("name")}
                      for x in (t.get("subs") or []) if isinstance(x, dict)],
            "unavailable": _unavailable(t),
            "coach": ((t.get("coach") or {}) or {}).get("name")
            if isinstance(t.get("coach"), dict) else t.get("coach"),
        }
    return out


async def match_lineup(match_id) -> dict | None:
    """경기 하나의 라인업 요약. 실패·결측이면 None."""
    d = await _get("matchDetails", {"matchId": match_id})
    return parse_lineup(d) if d else None


def diff_xi(before: dict | None, after: dict | None) -> dict:
    """[사용자 지시 2] 예상 XI → 공식 XI **차이를 코드가 센다.**

    반환 `{side: {"bench_notable": [...], "surprise_in": [...]}}`.
    🔴 **id 로 센다.** 이름 매칭은 금지(동명이인·표기 흔들림).
    ⚠️ 한쪽이라도 없으면 빈 dict — 모르는 것을 "변화 없음"으로 만들지 않는다.
    """
    if not before or not after:
        return {}
    out: dict = {}
    for side in ("home", "away"):
        b = {p.get("id") for p in ((before.get(side) or {}).get("starters") or [])
             if p.get("id")}
        a_list = (after.get(side) or {}).get("starters") or []
        a = {p.get("id") for p in a_list if p.get("id")}
        if not b or not a:
            continue
        names = {p.get("id"): p.get("name") for p in a_list}
        bnames = {p.get("id"): p.get("name")
                  for p in ((before.get(side) or {}).get("starters") or [])}
        out[side] = {
            # 예상 선발이었는데 공식에서 빠졌다
            "bench_notable": [bnames.get(i) for i in sorted(b - a, key=str)],
            # 예상에 없었는데 공식에 들어왔다
            "surprise_in": [names.get(i) for i in sorted(a - b, key=str)],
        }
    return out


#: 예상 XI 보관 키 — T-60 재호출에서 `confirmed` 와 대조하려고 남긴다.
XI_KEY = "fotmob:xi:{game_id}"


async def attach(jg: dict, *, redis=None, date_yyyymmdd: str | None = None) -> dict:
    """[FOT-1] 경기 하나에 라인업·결장을 붙인다. 반환은 붙인 요약(없으면 {}).

    `jg["fotmob"]` 에 넣는다:
      lineup_type · formation · starters(id·이름) · bench · unavailable(None=모름)
      · diff(예상→공식, confirmed 일 때만) · missing(모르는 칸)

    🔴 **`unavailable` 이 None 이면 `missing` 에 남긴다.** 0명으로 쓰지 않는다.
    ⚠️ 실패는 결측이다 — 예외를 올리지 않는다.
    """
    import json as _json
    from datetime import datetime, timezone

    d = date_yyyymmdd
    if not d:
        ts = jg.get("starts_at")
        ts = ts if isinstance(ts, datetime) else datetime.now(timezone.utc)
        d = ts.astimezone(timezone.utc).strftime("%Y%m%d")
    rows = await slate(d)
    m = find_match(rows, home=jg.get("home") or "", away=jg.get("away") or "")
    if m is None:
        logger.info("[fotmob] %s@%s — 그 날짜 표에 없다(%s)",
                    jg.get("away"), jg.get("home"), d)
        return {}
    lu = await match_lineup(m["id"])
    if not lu:
        logger.info("[fotmob] match=%s — 라인업 칸이 없다", m["id"])
        return {}

    before = None
    if redis is not None and jg.get("game_id"):
        try:
            raw = await redis.get(XI_KEY.format(game_id=jg["game_id"]))
            before = _json.loads(raw) if raw else None
        except Exception:
            before = None

    missing = [f"{side} 결장 명단 미제공" for side in ("home", "away")
               if (lu.get(side) or {}).get("unavailable") is None]
    out = dict(lu)
    out["missing"] = missing
    # 🔴 [사용자 지시 2] confirmed 로 바뀌면 예상 XI 와 **코드가** 대조한다.
    if lu.get("lineup_type") == CONFIRMED and before:
        out["diff"] = diff_xi(before, lu)
    jg["fotmob"] = out

    if redis is not None and jg.get("game_id"):
        try:
            await redis.set(XI_KEY.format(game_id=jg["game_id"]),
                            _json.dumps(lu, ensure_ascii=False), ex=12 * 3600)
        except Exception as exc:
            logger.debug("[fotmob] XI 보관 실패 game=%s: %s", jg.get("game_id"), exc)
    logger.info("[fotmob] %s@%s match=%s %s — 선발 %d/%d · 결장 %s/%s%s",
                jg.get("away"), jg.get("home"), m["id"], lu.get("lineup_type"),
                len((lu.get("home") or {}).get("starters") or []),
                len((lu.get("away") or {}).get("starters") or []),
                _n(lu, "home"), _n(lu, "away"),
                f" · diff {out.get('diff')}" if out.get("diff") else "")
    return out


def _n(lu: dict, side: str) -> str:
    v = (lu.get(side) or {}).get("unavailable")
    return "모름" if v is None else str(len(v))
