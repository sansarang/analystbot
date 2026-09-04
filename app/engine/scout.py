"""[정찰층 C2] 경기 전 정찰 — **무엇을 아직 모르는가**를 먼저 센다.

🔴 왜 필요한가. 판정은 "재료가 있으면 판정하고, 없으면 탈락"만 안다. 그래서
   재료가 **언제** 들어오는지, **어느 소스가 조용해졌는지**는 아무도 모른다.
   실사고 2026-09-01: KBO 5경기 판정이 14:00 에 끝났는데 카드가 한 장도 안
   나갔고, 사용자는 "봇이 죽었나"와 "라인업이 안 떴다"를 구분할 수 없었다.
   정찰은 그 구분을 **데이터로** 만든다.

무엇을 하는가 (세 축)
  요인  최근 뉴스가 이 경기에 몇 건 붙어 있는가            (`news_rss` 재사용)
  라인업 공시됐는가 · 언제 처음 보였는가 · 확정인가         (`lineup_events`)
  시장  담당 배당 소스가 이 경기 값을 갖고 있는가           (`odds_snapshots`)

🔴 **새로 크롤하지 않는다.** 세 축 모두 **이미 수집된 것을 읽기만** 한다.
   정찰이 트래픽을 만들면 정찰 때문에 소스가 막힌다.
🔴 **시장은 정찰 기록에만 남고 딥서치·판정으로 흐르지 않는다.** 배당이
   판정 입력이 아니라는 절대 규칙은 정찰층에도 그대로 적용된다.
🔴 **새 스케줄 잡을 만들지 않는다.** 기존 프리게임 폴링이 이 함수를 부른다.
⚠️ 종목 문자열을 하드코딩하지 않는다 — `registry.SCOUT_SPORTS` 가 원본이다.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

#: 정찰 기록 키. 판정 캐시(`analysis:…`)와 **다른 이름공간**이다 —
#  섞이면 정찰이 판정을 덮어쓸 수 있다.
KEY = "scout:{sport}:{game_id}:{date}"
TTL_SEC = 36 * 3600

#: 라인업 상태
LINEUP_NONE, LINEUP_PARTIAL, LINEUP_CONFIRMED = "없음", "잠정", "확정"


def _now() -> datetime:
    return datetime.now(UTC)


def hours_to_start(starts_at, *, now=None) -> float | None:
    """시작까지 남은 시간(시간 단위). 못 재면 None."""
    if starts_at is None:
        return None
    if isinstance(starts_at, str):
        try:
            starts_at = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
        except ValueError:
            return None
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=UTC)
    return (starts_at - (now or _now())).total_seconds() / 3600.0


def in_window(sport: str, starts_at, *, now=None) -> bool:
    """정찰 창 안인가. 창의 길이는 `registry` 가 원본이다(사본 금지)."""
    from app.registry import scout_sport

    sc = scout_sport(sport)
    if sc is None:
        return False
    h = hours_to_start(starts_at, now=now)
    return h is not None and 0 <= h <= float(sc.scout_open_h)


async def _lineup_state(pool, game_id) -> dict:
    """공시 여부·최초 관측 시각·확정 여부. `lineup_events` 가 원본이다.

    ⚠️ 컬럼은 `is_final` 이다 — `status` 가 아니다(실사고 2026-09-03:
       `l.status='confirmed'` 를 넣어 쿼리가 통째로 깨졌다).
    """
    out = {"state": LINEUP_NONE, "sides": 0, "first_seen": None, "lead_min": None}
    if pool is None or game_id is None:
        return out
    try:
        rows = await pool.fetch(
            """
            SELECT side, bool_or(is_final) AS final, min(observed_at) AS first_seen
              FROM lineup_events
             WHERE game_id = $1
             GROUP BY side
            """, int(game_id))
    except Exception as exc:
        logger.warning("[scout] 라인업 조회 실패 game=%s: %s", game_id, exc)
        return out
    if not rows:
        return out
    out["sides"] = len(rows)
    out["state"] = (LINEUP_CONFIRMED if all(r["final"] for r in rows) and len(rows) >= 2
                    else LINEUP_PARTIAL)
    first = min(r["first_seen"] for r in rows if r["first_seen"])
    out["first_seen"] = first.isoformat() if first else None
    return out


async def _market_state(pool, game_id, sport: str) -> dict:
    """담당 배당 소스가 이 경기 값을 갖고 있는가. **읽기만 한다.**

    🔴 여기서 나온 값은 정찰 기록에만 남는다. 딥서치·판정으로 넘기지 않는다.
    """
    from app.registry import odds_provider_for

    out = {"provider": odds_provider_for(sport), "rows": 0, "age_min": None}
    if pool is None or game_id is None or not out["provider"]:
        return out
    try:
        row = await pool.fetchrow(
            """
            SELECT count(*) AS n,
                   EXTRACT(EPOCH FROM (now() - max(captured_at))) / 60 AS age
              FROM odds_snapshots
             WHERE game_id = $1
            """, int(game_id))
    except Exception as exc:
        logger.warning("[scout] 배당 조회 실패 game=%s: %s", game_id, exc)
        return out
    if row:
        out["rows"] = int(row["n"] or 0)
        out["age_min"] = round(float(row["age"]), 1) if row["age"] is not None else None
    return out


def _factor_state(jg: dict) -> dict:
    """이 경기에 붙은 뉴스가 몇 건인가. 이미 수집된 것을 센다.

    ⚠️ `research` 자체가 없으면 **`None`** 이다 — "0건"과 "안 봤다"는 다르다.
       폴링 경로는 재료를 싣지 않으므로 여기서 0 을 적으면 매 틱마다
       "뉴스 0건"이라는 거짓 사실이 쌓인다.
    """
    if "research" not in jg:
        return {"news": None}
    r = jg.get("research") or {}
    n = 0
    for side in ("home", "away"):
        items = r.get(f"{side}_news") or []
        if isinstance(items, dict):
            items = items.get("headlines") or []
        n += len(items)
    if not n:
        items = r.get("news") or []
        n = len(items if isinstance(items, list) else (items.get("headlines") or []))
    return {"news": n}


async def observe(pool, redis, jg: dict, date: str, *, now=None) -> dict | None:
    """경기 1건 정찰. 창 밖이거나 정찰 대상이 아니면 None.

    ⚠️ **판정을 부르지 않는다.** 카드도 만들지 않는다. 기록만 남긴다.
    """
    from app.registry import scout_sport

    sport = (jg.get("sport") or "").lower()
    sc = scout_sport(sport)
    if sc is None:
        return None
    if not in_window(sport, jg.get("starts_at"), now=now):
        return None
    gid = jg.get("game_id")
    rec = {
        "sport": sport, "game_id": gid, "date": date,
        "observed_at": (now or _now()).isoformat(),
        "hours_to_start": round(hours_to_start(jg.get("starts_at"), now=now) or 0, 2),
        "active": sc.active,
        "lineup": await _lineup_state(pool, gid),
        "market": await _market_state(pool, gid, sport),
        "factor": _factor_state(jg),
    }
    lead = rec["lineup"].get("first_seen")
    if lead:
        try:
            h = hours_to_start(jg.get("starts_at"),
                               now=datetime.fromisoformat(lead))
            rec["lineup"]["lead_min"] = round((h or 0) * 60)
        except ValueError:
            pass
    if redis is not None:
        try:
            await redis.set(KEY.format(sport=sport, game_id=gid, date=date),
                            json.dumps(rec, ensure_ascii=False), ex=TTL_SEC)
        except Exception as exc:
            logger.debug("[scout] 기록 저장 실패 game=%s: %s", gid, exc)
    logger.info("[scout] %s game=%s T-%.1fh 라인업=%s(%d면) 배당=%s %d행 뉴스=%d",
                sport, gid, rec["hours_to_start"], rec["lineup"]["state"],
                rec["lineup"]["sides"], rec["market"]["provider"],
                rec["market"]["rows"], rec["factor"]["news"])
    return rec


async def observe_slate(pool, redis, games: list[dict], date: str,
                        *, now=None) -> list[dict]:
    """슬레이트 정찰. 실패한 경기는 건너뛰고 나머지를 계속한다."""
    out = []
    for jg in games or []:
        try:
            rec = await observe(pool, redis, jg, date, now=now)
        except Exception as exc:
            logger.warning("[scout] 정찰 실패 game=%s: %s", jg.get("game_id"), exc)
            continue
        if rec is not None:
            out.append(rec)
    return out

async def scan_scout(redis, pattern: str, *, limit: int = 200) -> list[dict]:
    """`scout:*` 기록을 **SCAN 으로** 모은다. 반환은 파싱된 dict 목록.

    🔴 **`KEYS` 를 쓰지 않는다.** 운영 Redis 는 판정 캐시·해시·서명으로
       키가 수만 개다. `KEYS` 는 전체를 훑는 O(N) 이고 그동안 다른 명령이
       막힌다 — 워치독이 5분마다 그것을 하면 워치독이 고장의 원인이 된다.
    ⚠️ 상한을 둔다. 슬레이트는 종목당 5~15경기라 200 이면 충분하고,
       패턴이 잘못돼 폭주하는 경우를 여기서 끊는다.
    """
    import json as _json

    out: list[dict] = []
    if redis is None:
        return out
    try:
        async for key in redis.scan_iter(match=pattern, count=100):
            raw = await redis.get(key)
            if raw:
                try:
                    out.append(_json.loads(raw))
                except (TypeError, ValueError):
                    continue
            if len(out) >= limit:
                break
    except Exception as exc:
        logger.debug("[scout] 기록 조회 실패 %s: %s", pattern, exc)
    return out
