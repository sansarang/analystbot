"""[v1.3 B-1] MLB 팀 투수 지표 → 자료9(불펜) 채움. **기존 statsapi 재사용.**

🔴 왜 필요한가: 자료9 를 채우는 수집기가 네이버(KBO)·야후·npb.jp(NPB)뿐이라
   **MLB 만 불펜 칸이 비어 있었다.** 오늘 아침 카드가 그대로 말했다:
     "불펜 자료(9번)가 없어 선발 조기강판 시 양팀 불펜 격차를 판단할 수 없음"
   같은 날 KBO 카드는 불펜을 근거3 에 세 번 썼다(5.39 vs 5.38 등).

⚠️ **KBO·NPB 와 같은 기준을 쓴다.** 두 리그 모두 `team_era`(팀 투수 방어율)를
   자료9 에 넣는다(`naver_kbo.py:319`, `npb_stats.py:225`) — 구원 전용 ERA 가
   아니다. MLB 만 다른 정의를 쓰면 리그 간 비교가 거짓이 된다.
   ⚠️ 그래서 라벨도 "팀 투수 ERA"로 정직하게 적는다.

⚠️ 실패해도 판정을 막지 않는다. 못 받으면 종전과 같이 빈 칸이다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

CACHE_TTL = 12 * 3600          # 시즌 누적이라 하루 두 번이면 충분
KEY = "mlb_team_pitching:{season}"
_mem: dict[str, tuple[float, dict]] = {}


async def fetch(season: int, redis=None) -> dict[str, dict]:
    """팀명 → {era, whip, so9, bb9}. 실패하면 빈 dict."""
    import json as _json
    import time as _time

    from app.config import get_settings

    if get_settings().force_mock:
        return {}
    key = KEY.format(season=season)
    hit = _mem.get(key)
    if hit and hit[0] > _time.time():
        return hit[1]
    if redis is not None:
        try:
            raw = await redis.get(key)
            if raw:
                val = _json.loads(raw)
                _mem[key] = (_time.time() + CACHE_TTL, val)
                return val
        except Exception as exc:
            logger.debug("[mlb_team_pitching] 캐시 읽기 실패: %s", exc)

    from app.collectors.starter_season import StatsAPIClient

    try:
        data = await StatsAPIClient(mock=False).get(
            "/teams/stats", {"season": season, "group": "pitching",
                             "stats": "season", "sportIds": 1})
    except Exception as exc:
        logger.warning("[mlb_team_pitching] 조회 실패 — 자료9 없이 간다: %s", exc)
        return {}
    out: dict[str, dict] = {}
    for sp in ((data or {}).get("stats") or [{}])[0].get("splits") or []:
        name = ((sp.get("team") or {}).get("name") or "").strip()
        st = sp.get("stat") or {}
        if not name:
            continue
        blk = {}
        for src, dst in (("era", "era"), ("whip", "whip"),
                         ("strikeoutsPer9Inn", "k9"), ("walksPer9Inn", "bb9")):
            v = st.get(src)
            if v not in (None, "", "-"):
                try:
                    blk[dst] = round(float(v), 2)
                except (TypeError, ValueError):
                    continue
        if blk.get("era") is not None:
            out[name] = blk
    if out:
        _mem[key] = (_time.time() + CACHE_TTL, out)
        if redis is not None:
            try:
                await redis.set(key, _json.dumps(out, ensure_ascii=False),
                                ex=CACHE_TTL)
            except Exception as exc:
                logger.debug("[mlb_team_pitching] 캐시 기록 실패: %s", exc)
    logger.info("[mlb_team_pitching] 팀 %d개 적재 (season=%d)", len(out), season)
    return out


async def attach(jg: dict, redis=None, season: int | None = None) -> int:
    """`research.{side}_bullpen.era` 를 채운다. 반환 채운 쪽 수."""
    from datetime import UTC, datetime

    if (jg.get("sport") or "").lower() != "mlb":
        return 0
    table = await fetch(season or datetime.now(UTC).year, redis)
    if not table:
        return 0
    research = jg.setdefault("research", {})
    n = 0
    for side in ("home", "away"):
        blk = table.get(jg.get(side) or "")
        if not blk:
            continue
        # ⚠️ `setdefault` 다 — 이미 다른 소스가 채웠으면 덮지 않는다.
        dst = research.setdefault(f"{side}_bullpen", {})
        if dst.get("era") is None:
            dst["era"] = blk["era"]
            n += 1
        for k in ("whip", "k9", "bb9"):
            if blk.get(k) is not None:
                dst.setdefault(k, blk[k])
    if n:
        logger.info("[mlb_team_pitching] 자료9 채움 game=%s %d/2", jg.get("game_id"), n)
    return n
