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
#  🔴 **TTL 을 함께 들고 있어야 한다.** 스케줄러는 며칠씩 도는 프로세스라
#     만료 없는 dict 에 넣으면 명단이 기동 시점으로 굳는다 — 콜업된 선수는
#     영원히 "미확보"가 되고, 그 타자의 시즌 라인이 계속 빈다.
#     redis 쪽은 12시간인데 메모리만 안 따라가던 결함이다
#     (`lineup_season._mem` 에서 같은 것을 이미 잡았다).
_roster_mem: dict[int, tuple[float, dict[str, int]]] = {}


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


def _register(roster: dict[str, int]) -> dict[str, int]:
    """명단을 실명 사전에 등록한다 — 타순 파서가 하이픈 이름을 복원할 수 있게.

    🔴 `Ha-Seong Kim` 같은 실명이 `order.split("-")` 에 두 조각으로 잘려
       타순 슬롯이 통째로 밀리던 결함(실측 2026-09-02, MLB 라인업 12%)의
       수정이다. 명단을 받는 **모든 경로**가 여기를 지나므로 한 곳이면 된다.
    """
    try:
        from app.engine.lineup_diff import register_names

        register_names(roster)
    except Exception as exc:        # 등록 실패가 시즌 라인을 막지 않는다
        logger.debug("[starter_season] 실명 사전 등록 실패: %s", exc)
    return roster


async def _roster(season: int, redis=None) -> dict[str, int]:
    """이름 → 선수 id. **슬레이트당 1회.** 캐시 우선(redis → 프로세스 → 네트워크)."""
    import json as _json

    if redis is not None:
        try:
            raw = await redis.get(_ROSTER_KEY.format(season=season))
            if raw:
                return _register(_json.loads(raw))
        except Exception as exc:
            logger.debug("[starter_season] 명단 캐시 읽기 실패: %s", exc)
    import time as _time

    hit = _roster_mem.get(season)
    if hit is not None:
        exp, val = hit
        if exp > _time.time():
            return _register(val)
        _roster_mem.pop(season, None)
    data = await StatsAPIClient(mock=False).get("/sports/1/players",
                                                {"season": season})
    ids = {p["fullName"]: p["id"] for p in (data or {}).get("people", [])
           if p.get("fullName") and p.get("id")}
    if not ids:
        return {}
    _roster_mem[season] = (_time.time() + _ROSTER_TTL, ids)
    if redis is not None:
        try:
            await redis.set(_ROSTER_KEY.format(season=season),
                            _json.dumps(ids, ensure_ascii=False), ex=_ROSTER_TTL)
        except Exception as exc:
            logger.debug("[starter_season] 명단 캐시 기록 실패: %s", exc)
    logger.info("[starter_season] 명단 %d명 적재 (season=%d)", len(ids), season)
    return _register(ids)


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
    sport = (jg.get("sport") or "").lower()
    if sport not in ("mlb", "kbo", "npb"):
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
    want = [n for n in names.values() if n]
    if sport == "mlb":
        lines = await fetch_mlb(want, season, redis)
    else:
        # [v1.3 B-2·B-3] KBO·NPB 도 선발 시즌 라인을 받는다.
        #   🔴 종전에는 MLB 만 받았다. 그래서 KBO·NPB 는 최근 등판 표본이
        #      얇으면 그 투수가 어떤 투수인지 볼 방법 없이 0.50 으로 당겼다 —
        #      실측 2026-09-02 LG@두산: "김윤식은 선발등판 0경기 → 대표성
        #      없음" 으로 끝났다. 시즌 라인이 있었으면 판단할 수 있었다.
        table = await fetch_asia(sport, season, redis)
        lines = {}
        for n in want:
            hit = lookup_asia(table, sport, n)
            if hit:
                lines[n] = hit
    research = jg.setdefault("research", {})
    for side, name in names.items():
        research[f"{side}_starter_season"] = lines.get(name) or {}
    got = sum(1 for v in research.values() if isinstance(v, dict) and v.get("ERA"))
    logger.info("[starter_season] %s 선발 시즌 game=%s 확보 %d/2",
                sport.upper(), jg.get("game_id"), min(got, 2))


# ─────────────── [v1.3 B-2·B-3] KBO·NPB 선발 시즌 라인 ───────────────
#
# 🔴 MLB 만 받던 자료7 을 세 리그로 대칭화한다. 실측 2026-09-02 LG@두산에서
#    "김윤식은 선발등판 0경기 → 대표성 없음" 으로 판정이 멈췄다 — 그 투수의
#    시즌이 어떤지 볼 수 있었다면 표본 부족을 보정할 수 있었다.
#
# ⚠️ **용도는 MLB 와 같다: 표본 보정 전용.** 프롬프트가 "이것으로 우세를
#    정하지 마라"로 막는 그 칸에 들어간다. 승패(W-L)는 담지 않는다.

_ASIA_TTL = 26 * 3600
_ASIA_KEY = "starter_season:{sport}:{season}"
_asia_mem: dict[str, tuple[float, dict]] = {}

#: NPB 팀별 개인 투수표. 타자표(`idb1_`)와 같은 구조다 — 실측 2026-09-03:
#  24칸 헤더 `選手…防御率`, 팀당 전 투수.
_NPB_PITCH_PATH = "/bis/{season}/stats/idp1_{code}.html"
_NPB_COLS = 24
#: 열 인덱스 (0-based). 헤더 실측으로 고정한다.
_NPB_IDX = {"선발": None, "登板": 1, "이닝": 12, "안타": 13, "四球": 15,
            "三振": 18, "자책": 22, "ERA": 23}

#: KBO 기록실 투수 기본. `kbo_stats` 가 쓰는 그 페이지다.
_KBO_PITCH = "/Record/Player/PitcherBasic/Basic1.aspx"
_KBO_PITCH2 = "/Record/Player/PitcherBasic/Basic2.aspx"


def slim_asia(*, era=None, ip=None, g=None, bb=None, so=None, whip=None,
              starts=None) -> dict:
    """아시아 리그 선발 라인. MLB `slim_season` 과 **같은 키**를 쓴다 —
    프롬프트가 리그를 구분하지 않게 하려면 모양이 같아야 한다."""
    from app.collectors.lineup_season import _f

    out = {}
    for key, val in (("선발", starts), ("등판", g), ("이닝", ip), ("ERA", era),
                     ("WHIP", whip), ("BB", bb), ("K", so)):
        v = _f(val)
        if v is not None:
            out[key] = v
    return out


def _ratio(a, b):
    try:
        fa, fb = float(a), float(b)
        return round(fa / fb, 2) if fb > 0 else None
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _session():
    """쿠키를 유지하는 클라이언트. ASP.NET 폼처럼 세션이 필요한 소스에 쓴다."""
    import httpx

    return httpx.AsyncClient(
        timeout=30.0, follow_redirects=True,
        headers={"User-Agent": _UA, "Accept-Language": "ko-KR,ko;q=0.9"})


async def _try(fn, *a, **kw):
    """지수 백오프 3회. 실패하면 None — 한 팀 실패가 나머지를 막지 않는다."""
    import asyncio

    last = None
    for attempt in range(3):
        try:
            r = await fn(*a, **kw)
            r.raise_for_status()
            return r
        except Exception as exc:
            last = exc
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
    logger.warning("[starter_season] 조회 실패: %s", last)
    return None


async def _get_html(url: str, *, data: dict | None = None,
                    headers: dict | None = None) -> str | None:
    """지수 백오프 3회 + 타임아웃. **raw httpx 를 그대로 쓰지 않는다** —
    CLAUDE.md "모든 외부 HTTP 호출은 재시도 필수". 실패하면 None."""
    import asyncio

    import httpx

    last = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(
                    timeout=30.0, follow_redirects=True,
                    headers={"User-Agent": _UA, **(headers or {})}) as c:
                r = (await c.post(url, data=data) if data is not None
                     else await c.get(url))
                r.raise_for_status()
                return r.text
        except Exception as exc:
            last = exc
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
    logger.warning("[starter_season] 조회 실패 %s: %s", url[-40:], last)
    return None


async def _fetch_npb_pitchers(season: int) -> dict[str, dict]:
    from app.collectors.lineup_season import NPB_TEAMS, _cells, norm_jp

    out: dict[str, dict] = {}
    if True:
        for code in NPB_TEAMS:
            html = await _get_html("https://npb.jp"
                                   + _NPB_PITCH_PATH.format(season=season, code=code))
            if html is None:
                continue
            import re as _re

            for row in _re.findall(r"<tr[^>]*>(.*?)</tr>", html, _re.S):
                cs = _cells(row)
                if len(cs) != _NPB_COLS:
                    continue
                ip, h, bb = cs[12], cs[13], cs[15]
                try:
                    walks_hits = float(h) + float(bb)
                except (TypeError, ValueError):
                    walks_hits = None
                out[norm_jp(cs[0])] = slim_asia(
                    era=cs[23], ip=ip, g=cs[1], bb=bb, so=cs[18],
                    whip=_ratio(walks_hits, ip))
    logger.info("[starter_season] NPB 투수 %d명 적재 (season=%d)", len(out), season)
    return out


async def _fetch_kbo_pitchers(season: int) -> dict[str, dict]:
    """KBO 기록실 투수 — 팀 드롭다운 POST. `lineup_season.fetch_kbo` 와 같은 방식."""
    from app.collectors.lineup_season import (
        KBO_BASE, KBO_TEAMS, _KBO_P, _cells, _form_fields,
    )

    out: dict[str, dict] = {}
    # 🔴 **세션을 유지해야 한다.** ASP.NET 폼은 GET 이 준 `JSESSIONID` 쿠키와
    #    `__VIEWSTATE` 를 함께 돌려줘야 표가 온다. 요청마다 새 클라이언트를
    #    쓰면 쿠키가 끊겨 **0건**이 된다(실측 2026-09-03).
    async with _session() as c:
        url = KBO_BASE + _KBO_PITCH
        base = await _try(c.get, url)
        if base is None:
            return {}
        fields = _form_fields(base.text)
        for code, team in KBO_TEAMS.items():
            f = dict(fields)
            f.update({"__EVENTTARGET": _KBO_P + "ddlTeam$ddlTeam",
                      "__EVENTARGUMENT": "", "__LASTFOCUS": "",
                      _KBO_P + "ddlTeam$ddlTeam": code})
            r = await _try(c.post, url, data=f, headers={
                "Referer": url,
                "Content-Type": "application/x-www-form-urlencoded"})
            if r is None:
                continue
            html = r.text
            import re as _re

            for row in _re.findall(r"<tr[^>]*>(.*?)</tr>", html, _re.S):
                cs = _cells(row)
                # 순위·선수명·팀명·ERA·G·W·L·SV·HLD·WPCT·IP …
                if len(cs) < 11 or not cs[0].isdigit():
                    continue
                out[cs[1].strip()] = slim_asia(era=cs[3], g=cs[4], ip=cs[10])
    logger.info("[starter_season] KBO 투수 %d명 적재 (season=%d)", len(out), season)
    return out


async def fetch_asia(sport: str, season: int, redis=None) -> dict[str, dict]:
    """KBO·NPB 투수 시즌 라인. 26시간 캐시 (시즌 누적이라 하루 1회면 충분)."""
    import json as _json
    import time as _time

    from app.config import get_settings

    if get_settings().force_mock:
        return {}
    key = _ASIA_KEY.format(sport=sport, season=season)
    hit = _asia_mem.get(key)
    if hit and hit[0] > _time.time():
        return hit[1]
    if redis is not None:
        try:
            raw = await redis.get(key)
            if raw:
                val = _json.loads(raw)
                _asia_mem[key] = (_time.time() + _ASIA_TTL, val)
                return val
        except Exception as exc:
            logger.debug("[starter_season] 아시아 캐시 읽기 실패: %s", exc)
    out = (await _fetch_npb_pitchers(season) if sport == "npb"
           else await _fetch_kbo_pitchers(season))
    if out:
        _asia_mem[key] = (_time.time() + _ASIA_TTL, out)
        if redis is not None:
            try:
                await redis.set(key, _json.dumps(out, ensure_ascii=False),
                                ex=_ASIA_TTL)
            except Exception as exc:
                logger.debug("[starter_season] 아시아 캐시 기록 실패: %s", exc)
    return out


def lookup_asia(table: dict, sport: str, name: str) -> dict:
    """이름 정규화 조회. NPB 는 전각 공백을 지운다(타선 시즌과 같은 규칙)."""
    from app.collectors.lineup_season import norm_jp, strip_pos

    if not name:
        return {}
    key = norm_jp(name) if sport == "npb" else strip_pos(name)
    return table.get(key) or {}


_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
