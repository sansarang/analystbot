"""[무과금 전환 1a] ESPN Core API 배당 — MLB 1순위. **무인증·무료.**

🔴 왜 바꾸나 (실측 2026-09-02): The Odds API 가 크레딧 소진으로
   2026-08-27T22:46 부터 차단됐고, `api_guard` 차단은 TTL 이 없어 시간으로
   풀리지 않는다. 그 사이 146.8시간 동안 배당이 한 행도 안 쌓였다.
   유료 키 하나에 가치 게이트 전체가 매달려 있던 구조가 문제다.

⚠️ **엔드포인트 선택은 실측으로 정했다** (2026-09-02):
     site.api.espn.com  → 403 Access Denied (이 egress IP 차단)
     cdn.espn.com/...?xhr=1 → 202 · 본문 0바이트 (봇 차단)
     sports.core.api.espn.com → **200 JSON** ✅
   그래서 core API 를 쓴다. 참고 문서(pseudo-r/Public-ESPN-API)가 가리키는
   gamepackage 경로는 우리 환경에서 안 열린다 — 문서를 믿지 말고 재보라.

실측 응답 (SD @ CIN, 2026-09-02):
  provider  {"id":"100","name":"DraftKings","priority":1}
  details   "SD -149"   overUnder 9.5
  awayTeamOdds.current.moneyLine {"decimal":1.67,"american":"-149"}
  homeTeamOdds.current.moneyLine {"decimal":2.23,"american":"+123"}

🔴 **배당은 판정 입력에 흐르지 않는다.** 이 수집기는 `odds_snapshots` 에만
   적재하고, 판정 경로(team_form·matchup·prompts)는 이 모듈을 import 하지
   않는다 — import 경계 테스트로 강제한다. 쓰이는 곳은 판정이 끝난 뒤의
   가치 게이트·시장 괴리·레저뿐이다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PROVIDER = "espn"
BASE = "https://sports.core.api.espn.com/v2/sports"

#: 종목 → ESPN 리그 경로. 야구만 쓴다 (KBO·NPB 는 배트맨 담당).
LEAGUE_PATH = {"mlb": "baseball/leagues/mlb"}

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
TIMEOUT = 25.0
MAX_RETRIES = 3


class ESPNOddsClient:
    """ESPN core API. **지수 백오프 3회 + 타임아웃** (CLAUDE.md 코드 규칙)."""

    def __init__(self, mock: bool = False):
        self.mock = mock

    async def get(self, url: str, params: dict | None = None) -> dict:
        import asyncio

        import httpx

        last = None
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(
                        timeout=TIMEOUT, follow_redirects=True,
                        headers={"User-Agent": UA, "Accept": "application/json"}) as c:
                    r = await c.get(url, params=params)
                    r.raise_for_status()
                    return r.json()
            except Exception as exc:
                last = exc
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
        raise RuntimeError(f"ESPN 조회 실패 {url}: {last}")


def _decimal(block: dict) -> float | None:
    """머니라인 소수배당. 없으면 None — 미국식에서 환산하지 않는다.

    ⚠️ ESPN 이 `current` 와 `open` 을 모두 준다. **current 만** 쓴다 —
       open 은 개장가라 지금 시장이 아니다.
    """
    cur = (block or {}).get("current") or {}
    ml = cur.get("moneyLine") or {}
    for key in ("decimal", "value"):
        v = ml.get(key)
        try:
            f = float(v)
            if f > 1.0:
                return round(f, 3)
        except (TypeError, ValueError):
            continue
    return None


#: 인플레이 배당을 내는 provider. **경기 전 가치 게이트에 쓰면 안 된다.**
#  🔴 실측 2026-09-02: ESPN 이 `"DraftKings - Live Odds"` 를 같은 목록에 섞어
#     준다. STL 이 7:0 으로 앞선 경기의 라이브 배당이 `STL 1.02 / LAD 11.4` 로
#     들어왔다 — 이걸 경기 전 판정과 견주면 괴리가 통째로 거짓이 된다.
#     기존 유료 수집기도 in-play 이벤트를 건너뛰고 있었다(같은 규율).
_LIVE_MARKERS = ("live", "in-play", "inplay")


def started(iso: str | None, now=None) -> bool:
    """경기가 이미 시작했는가. 시각을 못 읽으면 **False** (수집을 막지 않는다)."""
    from datetime import UTC, datetime

    if not iso:
        return False
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return t <= (now or datetime.now(UTC))


def is_live_book(name: str) -> bool:
    low = (name or "").lower()
    return any(m in low for m in _LIVE_MARKERS)


def parse_odds(item: dict, home: str, away: str) -> list[dict]:
    """odds 항목 1건 → 적재 행 목록. 없는 칸은 만들지 않는다.

    ⚠️ 라이브 북은 **버린다.** 경기 전 배당만 적재한다.
    """
    out = []
    book = ((item.get("provider") or {}).get("name") or "espn").lower()
    if is_live_book(book):
        return []
    for side_key, team in (("homeTeamOdds", home), ("awayTeamOdds", away)):
        dec = _decimal(item.get(side_key) or {})
        if dec is not None and team:
            out.append({"book": book, "market": "h2h", "side": team,
                        "line": None, "odds": dec})
    # ── [ODF-1 2026-09-17] **언더/오버.** 종전에는 "ESPN 은 O/U 가격을 따로
    #    안 준다"며 라인만 보고 버렸다. **실측으로 그 판단이 틀렸다**(운영에서
    #    Core API 직접 호출, 2026-09-17):
    #      DraftKings … overUnder 7.0 · overOdds 101.0 · underOdds -122.0
    #    같은 파일의 `parse_soccer_odds` 는 **이미 그 필드를 읽고 있었다.**
    #    🔴 원칙은 그대로다 — **가격이 없으면 안 넣는다.** −110 으로 지어내지
    #       않는다. 필드가 있을 때만 넣는다.
    #    ⚠️ O/U·핸디 가격은 야구도 **미국식**이다(101.0 / −122.0). 머니라인만
    #       소수로 온다 — 그래서 `_decimal` 과 `from_american` 을 갈라 쓴다.
    ou = _num(item.get("overUnder"))
    if ou is not None:
        for key, side in (("overOdds", "Over"), ("underOdds", "Under")):
            dec = from_american(item.get(key))
            if dec is not None:
                out.append({"book": book, "market": "totals", "side": side,
                            "line": ou, "odds": dec})

    # ── [ODF-1] **핸디캡.** `spread` 는 홈 기준이다 — 원정은 부호를 뒤집는다
    #    (`parse_soccer_odds` 와 같은 방식. 사본 금지).
    #    ⚠️ 야구는 핸디 **가격이 소수**로 온다(`current.spread.value` = 2.42) —
    #       축구의 `spreadOdds`(미국식)와 자리도 단위도 다르다. 환산하지 않는다.
    sp = _num(item.get("spread"))
    if sp is not None:
        for key, team, sign in (("homeTeamOdds", home, 1.0),
                                ("awayTeamOdds", away, -1.0)):
            cur = ((item.get(key) or {}).get("current") or {})
            dec = _num((cur.get("spread") or {}).get("value"))
            if dec is not None and dec > 1.0 and team:
                out.append({"book": book, "market": "spreads", "side": team,
                            "line": round(sp * sign, 2),
                            "odds": round(float(dec), 3)})
    return out


#: ESPN 팀 id → displayName. 팀 이름은 시즌 중에 안 바뀐다.
_team_cache: dict[str, str] = {}


async def _teams_of(client, comp: dict) -> tuple[str, str]:
    """competition → (home, away) displayName. 못 구하면 빈 문자열."""
    got = {"home": "", "away": ""}
    for cm in comp.get("competitors") or []:
        side = cm.get("homeAway")
        ref = ((cm.get("team") or {}).get("$ref") or "")
        if side not in got or not ref:
            continue
        tid = ref.split("/teams/")[-1].split("?")[0]
        name = _team_cache.get(tid)
        if name is None:
            try:
                name = (await client.get(ref)).get("displayName") or ""
            except Exception as exc:
                logger.debug("[espn_odds] 팀 조회 실패 %s: %s", tid, exc)
                name = ""
            if name:
                _team_cache[tid] = name
        got[side] = name
    return got["home"], got["away"]


async def fetch_slate(date: str, sport: str = "mlb",
                      client: ESPNOddsClient | None = None) -> dict[str, dict]:
    """`YYYY-MM-DD` 슬레이트 → {espn_event_id: {home, away, rows[]}}.

    ⚠️ 한 경기 실패가 나머지를 막지 않는다.
    """
    path = LEAGUE_PATH.get(sport)
    if not path:
        return {}
    c = client or ESPNOddsClient()
    ymd = date.replace("-", "")
    try:
        idx = await c.get(f"{BASE}/{path}/events",
                          {"dates": ymd, "limit": 100})
    except Exception as exc:
        logger.warning("[espn_odds] 슬레이트 조회 실패 %s: %s", date, exc)
        return {}
    out: dict[str, dict] = {}
    for ref in idx.get("items") or []:
        url = (ref or {}).get("$ref")
        if not url:
            continue
        try:
            ev = await c.get(url)
            name = ev.get("name") or ""
            comp = (ev.get("competitions") or [{}])[0]
            odds_ref = (comp.get("odds") or {}).get("$ref")
            if not odds_ref:
                continue
            # 🔴 `name` 문자열을 " at " 로 자르지 않는다. 실측 2026-09-02:
            #    ESPN 이 `'Athletics Athletics at Texas Rangers'` 를 주어
            #    원정팀이 "Athletics Athletics" 가 됐다 — 우리 games 테이블의
            #    "Athletics" 와 안 맞아 그 경기 배당이 통째로 버려진다.
            #    `competitors[].team.displayName` 이 정확하다.
            home, away = await _teams_of(c, comp)
            if not home or not away:
                logger.debug("[espn_odds] 팀명 확보 실패: %r", name)
                continue
            # 🔴 이미 시작한 경기는 통째로 건너뛴다. 라이브 북을 걸러도
            #    경기 중이면 pregame 라인 자체가 낡은 값이다.
            #    ⚠️ `competitions[].status` 는 `$ref` 라 값을 보려면 호출이
            #       하나 더 든다. **경기 시각으로 판단한다** — 15경기 슬레이트에
            #       불필요한 15콜을 태울 이유가 없다.
            if started(ev.get("date")):
                logger.debug("[espn_odds] %s 이미 시작 — 생략", name)
                continue
            od = await c.get(odds_ref)
            rows: list[dict] = []
            for item in od.get("items") or []:
                rows += parse_odds(item, home, away)
            if rows:
                out[str(ev.get("id"))] = {"home": home, "away": away,
                                          "date": ev.get("date"), "rows": rows}
        except Exception as exc:
            logger.warning("[espn_odds] 경기 조회 실패 %s: %s", url[-30:], exc)
    logger.info("[espn_odds] %s %s — 배당 확보 %d경기", sport.upper(), date, len(out))
    return out


# ── [D1-5 2026-09-14 사용자 지시] 축구 배당 — 게이트 대상만 ─────────────
#
# 🔴 **주소는 실측으로 갈렸다**: site.api.espn.com 은 403(우리 egress IP),
#    sports.core.api.espn.com 은 200. 아래는 core 경로다.
# 🔴 **축구는 미국식 배당만 온다**(`moneyLine: -500`). 야구는 decimal 이
#    오므로 `_decimal` 이 환산을 거부한다 — 그 규약을 깨지 않으려고 축구
#    전용 파서를 따로 둔다.

#: 사용자가 준 리그 코드.
SOCCER_LEAGUES = {"epl": "eng.1", "la_liga": "esp.1", "serie_a": "ita.1",
                  "bundesliga": "ger.1", "ligue1": "fra.1", "eredivisie": "ned.1",
                  "kleague1": "kor.1", "j1": "jpn.1"}

#: 경기당 요청 상한(사용자 지시: 5시점 × 1~2).
SOCCER_MAX_REQ_PER_GAME = 10


def from_american(v) -> float | None:
    """미국식 → 소수배당.

    🔴 [ODF-1 2026-09-17 정정] 종전 머리말은 "**축구에서만** 쓴다(야구는
       decimal 이 온다)"였다. **머니라인만 그렇다** — 야구도 O/U 가격은
       미국식으로 온다(실측 overOdds 101.0 · underOdds −122.0).

    항등식이라 추측이 아니다: 음수 −a → 1 + 100/a · 양수 +b → 1 + b/100.
    """
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f == 0:
        return None
    dec = 1 + (100.0 / abs(f)) if f < 0 else 1 + (f / 100.0)
    return round(dec, 3) if dec > 1.0 else None


def _ml(block) -> float | None:
    """`{"moneyLine": -500}` 또는 숫자. 없으면 None."""
    if isinstance(block, dict):
        return from_american(block.get("moneyLine"))
    return from_american(block)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_soccer_odds(item: dict, home: str, away: str) -> list[dict]:
    """odds 항목 1건 → 적재 행. 라이브 북은 버린다.

    🔴 [U2 2026-09-15] **h2h 에 더해 `spreads`·`totals` 도 낸다.** 실소스에
       값이 있는데 버리고 있었다(실측: spread=-0.5 · overUnder=2.5 ·
       overOdds=-110 · underOdds=-115). 그 탓에 S8 라인 이동과 S9 구조 픽이
       통째로 불가능했다.
    🔴 `open` 블록이 있으면 그 행에 `snap_tag='open'` 을 붙인다. ESPN 은
       **진짜 개장가를 주는 첫 소스**다(다른 경로는 전부 `open_proxy`).
       ⚠️ 현재가 행에는 붙이지 않는다 — 거짓 개장가가 된다.
    ⚠️ 요청은 늘지 않는다. **같은 응답을 더 읽을 뿐이다.**
    """
    book = ((item.get("provider") or {}).get("name") or "espn").lower()
    if is_live_book(book):
        return []
    book = book.replace(" ", "")          # "Bet 365" → "bet365"
    out = []
    for key, team in (("homeTeamOdds", home), ("drawOdds", "Draw"),
                      ("awayTeamOdds", away)):
        dec = _ml(item.get(key))
        if dec is not None and team:
            out.append({"book": book, "market": "h2h", "side": team,
                        "line": None, "odds": dec})

    # ── 핸디캡. `spread` 는 **홈 기준**이다 — 원정은 부호를 뒤집는다.
    #    둘 다 있어야 디빅이 된다.
    sp = _num(item.get("spread"))
    if sp is not None:
        for key, team, sign in (("homeTeamOdds", home, 1.0),
                                ("awayTeamOdds", away, -1.0)):
            dec = from_american((item.get(key) or {}).get("spreadOdds"))
            if dec is not None and team:
                out.append({"book": book, "market": "spreads", "side": team,
                            "line": round(sp * sign, 2), "odds": dec})

    # ── 언더/오버. 라인 하나에 양쪽 배당.
    ou = _num(item.get("overUnder"))
    if ou is not None:
        for key, side in (("overOdds", "Over"), ("underOdds", "Under")):
            dec = from_american(item.get(key))
            if dec is not None:
                out.append({"book": book, "market": "totals", "side": side,
                            "line": ou, "odds": dec})

    # ── 개장가. ESPN 만 준다.
    op = (item.get("homeTeamOdds") or {}).get("open") or {}
    if op:
        o_ml = ((op.get("moneyLine") or {}).get("american")
                if isinstance(op.get("moneyLine"), dict) else op.get("moneyLine"))
        dec = from_american(o_ml)
        if dec is not None and home:
            out.append({"book": book, "market": "h2h", "side": home,
                        "line": None, "odds": dec, "snap_tag": "open"})
        o_sp = op.get("pointSpread") or {}
        o_line = _num(o_sp.get("alternateDisplayValue")
                      if isinstance(o_sp, dict) else o_sp)
        o_sp_odds = from_american(
            (o_sp.get("american") if isinstance(o_sp, dict) else None))
        if o_line is not None and o_sp_odds is not None and home:
            out.append({"book": book, "market": "spreads", "side": home,
                        "line": o_line, "odds": o_sp_odds, "snap_tag": "open"})
    return out


def _hit(name: str, want: str) -> bool:
    """ESPN 경기 이름에 우리 팀 이름 조각이 들어 있는가. 퍼지 금지."""
    n, w = (name or "").lower(), (want or "").lower()
    return bool(w) and any(t in n for t in w.split() if len(t) > 2)


def _sides(comp: dict) -> tuple[str, str]:
    home = away = ""
    for t in comp.get("competitors") or []:
        nm = ((t.get("team") or {}).get("displayName")
              or (t.get("team") or {}).get("name") or "")
        if (t.get("homeAway") or "") == "home":
            home = nm
        elif (t.get("homeAway") or "") == "away":
            away = nm
    return home, away


async def fetch_soccer(league_key: str, date_yyyymmdd: str, *,
                       only_names: set | None = None, redis=None) -> dict:
    """[D1-5] 그 리그·날짜의 축구 배당. `{경기이름: [행]}`.

    🔴 `only_names` 가 비면 **아무 요청도 하지 않는다** — 게이트 대상만
       친다는 예산 규칙이 여기서 지켜진다(사용자 지시).
    ⚠️ 실패는 결측이다. 요청 수를 로그에 남긴다.
    """
    import httpx

    code = SOCCER_LEAGUES.get(league_key)
    if not code or not only_names:
        logger.info("[espn_odds] 축구 %s — 대상 없음(요청 0)", league_key)
        return {}
    base = f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/{code}"
    cap = SOCCER_MAX_REQ_PER_GAME * max(1, len(only_names))
    out: dict = {}
    n = 0
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True,
                                     headers={"User-Agent": UA}) as c:
            r = await c.get(f"{base}/events", params={"dates": date_yyyymmdd})
            n += 1
            for it in (r.json() or {}).get("items") or []:
                if n >= cap:
                    logger.warning("[espn_odds] 축구 %s — 요청 상한 도달(%d)",
                                   league_key, n)
                    break
                ev = (await c.get(it["$ref"])).json()
                n += 1
                name = ev.get("name") or ""
                if not any(_hit(name, x) for x in only_names):
                    continue
                comp = (ev.get("competitions") or [{}])[0]
                ref = (comp.get("odds") or {}).get("$ref")
                if not ref:
                    continue
                od = (await c.get(ref)).json()
                n += 1
                home, away = _sides(comp)
                rows = []
                for o in (od or {}).get("items") or []:
                    rows += parse_soccer_odds(o, home, away)
                if rows:
                    out[name] = rows
    except Exception as exc:
        logger.warning("[espn_odds] 축구 %s 실패: %s", league_key, exc)
    # 🔴 [D1-6] 예산 카운터 — 형식은 `llm/ledger.record_call` 과 같다
    #    (일자 해시 + TTL). 새 방식을 만들지 않는다.
    if redis is not None and n:
        try:
            from datetime import UTC, datetime

            key = f"api_calls:{datetime.now(UTC).date().isoformat()}"
            await redis.hincrby(key, "espn_soccer", n)
            await redis.expire(key, 7 * 24 * 3600)
        except Exception as exc:
            logger.debug("[espn_odds] 예산 기록 실패: %s", exc)
    logger.info("[espn_odds] 축구 %s %s — 경기 %d · 요청 %d (상한 %d)",
                league_key, date_yyyymmdd, len(out), n, cap)
    return out
