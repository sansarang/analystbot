"""[C 2026-09-01] 선발투수의 **시즌 라인** — 표본 보정 전용.

🔴 **규율 개정이다.** `CLAUDE.md`는 "시즌 ERA/xwOBA 금지"를 명시한다. 그 규칙은
   시즌 통념이 최근 폼을 덮는 것을 막으려는 것이고, **타선에는 그대로 유효하다.**
   여기서 푸는 것은 **선발투수 한 칸뿐**이다.

   실사고 2026-09-01 (NYY @ LAA, 1:7 패):
     Rodríguez 최근 등판 표본 1경기(6이닝 3실점) → 판정 "안정적" → NYY 66% 추천
     시즌: 6선발 26.2이닝 ERA 5.40 WHIP 1.58 **BB 16개(BB/9 5.4)**
     오늘: 3.2이닝 3볼넷 4실점 — 시즌 평균 그대로였다
     Ureña 최근 3경기가 부진 구간 → "이닝 소화력 불안"
     시즌: 23선발 123.1이닝 ERA 2.85 — 정상급. 오늘 7이닝 1실점 0볼넷 8K
   시즌 데이터가 결과를 예측하고 있었는데 판정이 볼 수 없게 되어 있었다.

⚠️ **용도는 표본 보정뿐이다.** 프롬프트가 이 값으로 우세를 정하지 못하게 막는다 —
   최근 등판이 시즌 성향과 크게 어긋날 때 "그 표본을 얼마나 믿을지"만 판단한다.
⚠️ 실패해도 판정을 막지 않는다. 못 받으면 빈 dict 이고, 그러면 종전과 같다.
"""
from __future__ import annotations

import logging

from app.collectors.base import BaseAPIClient

logger = logging.getLogger(__name__)

#: 선수 id 캐시 TTL. 명단은 하루에 바뀌지 않는다.
#   🔴 실측 2026-09-01: `attach` 가 경기마다 전체 명단(1,421명 · 1.4MB · 1.1초)을
#      다시 받고 있었다. 11경기 슬레이트면 15.3MB · 약 12초를 그냥 태운다.
#      저녁 아시아 창처럼 시간이 촉박할 때 이 12초는 그대로 손해다.
_ROSTER_TTL = 12 * 3600
_ROSTER_KEY = "starter_season:roster:{season}"
#: 프로세스 내 폴백 캐시 — redis 가 없을 때도 슬레이트 안에서는 1회로 줄인다.
_roster_mem: dict[int, dict[str, int]] = {}


class StatsAPIClient(BaseAPIClient):
    """statsapi 전용. **지수 백오프 3회 + 타임아웃**은 BaseAPIClient 가 준다.

    🔴 종전에는 raw httpx 한 방이었다 — CLAUDE.md 의 "모든 외부 HTTP 호출은
       지수 백오프 3회 재시도 + 타임아웃 필수"를 어겼다. 일시적 5xx 하나에
       표본 보정이 통째로 빠진다.
    """

    name = "mlb"
    base_url = "https://statsapi.mlb.com/api/v1"
    timeout = 20.0
    max_retries = 3

    async def get(self, path: str, params: dict | None = None):
        return await self._request("GET", path, params=params)


def slim_season(stat: dict) -> dict:
    """시즌 라인 한 줄. **승패(W-L)는 담지 않는다** — 기존 규율 그대로."""
    def _f(k):
        v = stat.get(k)
        return v if v not in ("", None) else None

    ip = _f("inningsPitched")
    bb, k = _f("baseOnBalls"), _f("strikeOuts")
    out = {"선발": _f("gamesStarted"), "이닝": ip, "ERA": _f("era"),
           "WHIP": _f("whip"), "K": k, "BB": bb}
    try:
        innings = float(ip)
        if innings > 0 and bb is not None:
            out["BB9"] = round(float(bb) * 9 / innings, 2)
        if innings > 0 and k is not None:
            out["K9"] = round(float(k) * 9 / innings, 2)
    except (TypeError, ValueError):
        pass
    return {k2: v for k2, v in out.items() if v is not None}


async def _roster(season: int, redis=None) -> dict[str, int]:
    """이름 → 선수 id. **슬레이트당 1회.** 캐시 우선(redis → 프로세스 → 네트워크)."""
    import json as _json

    if redis is not None:
        try:
            raw = await redis.get(_ROSTER_KEY.format(season=season))
            if raw:
                return _json.loads(raw)
        except Exception as exc:
            logger.debug("[starter_season] 명단 캐시 읽기 실패: %s", exc)
    if season in _roster_mem:
        return _roster_mem[season]
    data = await StatsAPIClient(mock=False).get("/sports/1/players",
                                                {"season": season})
    ids = {p["fullName"]: p["id"] for p in (data or {}).get("people", [])
           if p.get("fullName") and p.get("id")}
    if not ids:
        return {}
    _roster_mem[season] = ids
    if redis is not None:
        try:
            await redis.set(_ROSTER_KEY.format(season=season),
                            _json.dumps(ids, ensure_ascii=False), ex=_ROSTER_TTL)
        except Exception as exc:
            logger.debug("[starter_season] 명단 캐시 기록 실패: %s", exc)
    logger.info("[starter_season] 명단 %d명 적재 (season=%d)", len(ids), season)
    return ids


async def fetch_mlb(names: list[str], season: int, redis=None) -> dict[str, dict]:
    """이름 → 시즌 라인. 명단은 캐시에서, 선수별로 1콜."""
    want = {n for n in names if n}
    if not want:
        return {}
    try:
        roster = await _roster(season, redis)
    except Exception as exc:
        logger.warning("[starter_season] 명단 조회 실패 — 표본 보정 없이 간다: %s", exc)
        return {}
    cli = StatsAPIClient(mock=False)
    out: dict[str, dict] = {}
    for name in sorted(want):
        pid = roster.get(name)
        if pid is None:
            continue
        try:
            d = await cli.get(f"/people/{pid}",
                              {"hydrate": f"stats(group=[pitching],type=[season],"
                                          f"season={season})"})
            for st in ((d or {}).get("people") or [{}])[0].get("stats", []):
                for sp in st.get("splits", []):
                    line = slim_season(sp.get("stat") or {})
                    if line:
                        out[name] = line
        except Exception as exc:
            logger.warning("[starter_season] %s 조회 실패: %s", name, exc)
    missing = want - set(out)
    if missing:
        logger.info("[starter_season] 미확보 %s — 표본 보정 없이 간다",
                    ", ".join(sorted(missing)))
    return out


async def attach(jg: dict, season: int | None = None, redis=None,
                 *, replay: bool = False) -> None:
    """research.{side}_starter_season 을 채운다. MLB 전용, 실패해도 조용히 넘어간다.

    ⚠️ `replay=True` 면 **시즌 라인을 붙이지 않는다.**
       🔴 statsapi 시즌 스탯은 언제나 "지금" 값이다. 실전 판정은 경기 전에
          하므로 그 경기가 자연히 빠지지만, **끝난 경기를 재현하면 그 경기
          자체가 시즌 라인에 들어간다.**
          실측 2026-09-01 (MIA @ WSH 재현): Will Dion 시즌 `선발 1 · 17.2이닝
          · ERA 2.04` 를 넣었는데, 그 유일한 선발이 **바로 그 경기**(8/31
          3이닝 0실점)였다. 경기 전 그의 선발 등판은 0회다.
          "성능이 갑자기 좋아 보이면 먼저 누수를 의심하라" 는 그대로다.
    """
    if (jg.get("sport") or "") != "mlb":
        return
    from datetime import UTC, datetime

    from app.config import get_settings
    from app.engine.starter_recent import pitcher_name

    research0 = jg.setdefault("research", {})
    if replay:
        for side in ("home", "away"):
            research0[f"{side}_starter_season"] = {}
        jg["season_line_suppressed"] = True     # 카드·로그가 사유를 말할 수 있게
        logger.info("[starter_season] 재현 모드 — 시즌 라인 제외(누수 차단) game=%s",
                    jg.get("game_id"))
        return

    # 🔴 목 모드에서는 **호출하지 않는다.** 판정 경로에 새 외부 호출을 붙일
    #    때는 목 분기를 같은 커밋에 넣어야 한다 — 딥서치 배선에서 이미 겪었다
    #    (스위트가 api.anthropic.com 을 때려 35초 → 419초).
    #    실측 2026-09-01: 이 가드 없이 커밋했더니 P5-2 외부 차단이 테스트 4건에서
    #    statsapi.mlb.com 접근을 잡아냈다.
    if get_settings().force_mock:
        research = jg.setdefault("research", {})
        for side in ("home", "away"):
            research.setdefault(f"{side}_starter_season", {})
        return

    season = season or datetime.now(UTC).year
    names = {side: pitcher_name(jg, side) for side in ("home", "away")}
    lines = await fetch_mlb([n for n in names.values() if n], season, redis)
    research = jg.setdefault("research", {})
    for side, name in names.items():
        research[f"{side}_starter_season"] = lines.get(name) or {}
