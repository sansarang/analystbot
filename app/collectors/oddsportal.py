"""[배당 크롤 2026-09-02] oddsportal — KBO·NPB h2h 배당. **무인증·무료.**

🔴 후보 5곳을 실측해 고른 결과다 (2026-09-02 16:00, 응답 원문 기준):
     와이즈토토       2,585B  JS 셸 — 배당·KBO 문자열 0
     와이즈토토/proto 4,980B  JS 셸 — 동일
     플래시스코어      404
     스포츠토토 공식   78KB   JS 렌더링 필요 (소수배당 패턴 1개)
     **oddsportal     973KB  KBO 165회 · 소수배당 656패턴 · 정적 파싱 가능** ✅
   "JS 무거움"으로 최후순위였지만, 실제로는 Next.js **서버 스트리밍 페이로드**
   에 배당이 그대로 들어 있어 브라우저 없이 읽힌다. 문서가 아니라 응답을 봐야
   안다.

파싱 대상 (실측 구조):
  ① `rows`: {"id":9812029,"home-name":"Doosan Bears","away-name":"LG Twins",
             "status-id":1,...}                      ← 경기 ↔ eventId
  ② 배당 맵: {"MLJkRZK8":{"event":9812021,"odds":[
             {"maxOdds":1.64,"avgOdds":1.54,"bettingTypeId":3,"resultId":1,
              "positionsWithProviders":{...북별...}}]}}
  둘 다 `self.__next_f.push([1,"..."])` 안의 **이스케이프된 JSON** 이다.

⚠️ **avgOdds 를 쓴다.** `maxOdds` 는 여러 북 중 가장 좋은 값이라 실제로 걸 수
   있는 가격보다 낙관적이다. 가치 게이트가 그걸 기준으로 삼으면 통과가 헐거워진다.
⚠️ 상대 서버를 두들기지 않는다 — 리그당 1요청, 60분 주기.
🔴 배당은 판정 입력에 흐르지 않는다. 적재처는 `odds_snapshots` 뿐이다.
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

PROVIDER = "oddsportal"

# ─────────────────── 크롤 예절 ───────────────────
# 🔴 [정찰 C1-이관 2026-09-04] UA·타임아웃·재시도·백오프를 **여기서 지웠다.**
#    네 개 다 `app/net/polite_client.py` + config 가 원본이고, 여기 있던 것은
#    사본이었다. 사본은 원본이 바뀔 때 따라가지 않는다 — 설계 규율 §사본 금지.
#    (종전 값: UA 하드코딩 · TIMEOUT 30.0 · MAX_ATTEMPTS 2 · BACKOFF_SEC 3.0
#     → 지금은 crawl_timeout_sec 20.0 · crawl_retries 3 · crawl_backoff_sec 1.5)
#: 같은 리그를 이 간격 안에 두 번 부르지 않는다. 30분 주기 + 발송 직전 1회를
#  허용하되, 폴링 틱이 겹쳐도 실제 요청은 이 간격으로 막힌다.
#  ⚠️ 이것은 **이 소스 고유의 예절**이라 polite_client 로 옮기지 않는다.
#: 같은 리그를 이 간격 안에 두 번 부르지 않는다. 30분 주기 + 발송 직전 1회를
#  허용하되, 폴링 틱이 겹쳐도 실제 요청은 이 간격으로 막힌다.
MIN_INTERVAL_SEC = 10 * 60
#: 마지막 요청 시각 (프로세스 내). redis 없이도 한 프로세스 안에서는 지켜진다.
_last_call: dict[str, float] = {}

LEAGUE_URL = {
    "kbo": "https://www.oddsportal.com/baseball/south-korea/kbo/",
    "npb": "https://www.oddsportal.com/baseball/japan/npb/",
}

#: 2-way 승패 마켓. 야구는 무승부가 없다.
BETTING_TYPE_H2H = 3

#: oddsportal 표기 → 우리 games 팀명.
TEAM_MAP = {
    # KBO
    "Doosan Bears": "Doosan Bears", "LG Twins": "LG Twins",
    "KT Wiz Suwon": "KT Wiz", "Hanwha Eagles": "Hanwha Eagles",
    "NC Dinos": "NC Dinos", "KIA Tigers": "Kia Tigers",
    "Kiwoom Heroes": "Kiwoom Heroes", "SSG Landers": "SSG Landers",
    "Samsung Lions": "Samsung Lions", "Lotte Giants": "Lotte Giants",
    # NPB — ⚠️ oddsportal 은 **줄임 표기**를 쓴다. 실측 2026-09-02 로그가
    #   미매핑을 그대로 뱉어(`Fukuoka S. Hawks` 등) 여기에 추가했다.
    #   미매핑은 조용히 버려지지 않고 경고로 뜬다 — 새 표기가 나오면 드러난다.
    "Yomiuri Giants": "Yomiuri Giants", "Hanshin Tigers": "Hanshin Tigers",
    "Yokohama BayStars": "Yokohama DeNA BayStars",
    "Yokohama DeNA BayStars": "Yokohama DeNA BayStars",
    "Hiroshima Carp": "Hiroshima Toyo Carp",
    "Hiroshima Toyo Carp": "Hiroshima Toyo Carp",
    "Yakult Swallows": "Tokyo Yakult Swallows",
    "Tokyo Yakult Swallows": "Tokyo Yakult Swallows",
    "Chunichi Dragons": "Chunichi Dragons",
    "Fukuoka S. Hawks": "Fukuoka SoftBank Hawks",
    "Fukuoka SoftBank Hawks": "Fukuoka SoftBank Hawks",
    "Nippon Ham Fighters": "Hokkaido Nippon-Ham Fighters",
    "Hokkaido Nippon-Ham Fighters": "Hokkaido Nippon-Ham Fighters",
    "Chiba Lotte Marines": "Chiba Lotte Marines",
    "Rakuten Gold. Eagles": "Tohoku Rakuten Golden Eagles",
    "Tohoku Rakuten Golden Eagles": "Tohoku Rakuten Golden Eagles",
    "Seibu Lions": "Saitama Seibu Lions",
    "Saitama Seibu Lions": "Saitama Seibu Lions",
    "Orix Buffaloes": "Orix Buffaloes",
}


def _unescape(html: str) -> str:
    """스트리밍 페이로드의 `\\"` 를 실제 따옴표로. 통짜로 훑기 위한 최소 처리."""
    return html.replace('\\"', '"').replace("\\\\", "\\")


def parse_rows(html: str) -> dict[int, dict]:
    """eventId → {home, away, status}. 없는 칸은 만들지 않는다."""
    # ⚠️ `[^{}]` 로 범위를 막으면 안 된다 — `"superTemplate":{...}` 같은 중첩
    #    객체가 `"id"` 와 `"home-name"` 사이에 있어 매치가 통째로 실패한다
    #    (실측 2026-09-02: 그래서 rows 가 0건이었다). 거리로만 제한한다.
    flat = _unescape(html)
    out: dict[int, dict] = {}
    for m in re.finditer(
            r'"id":(\d{6,9}),.{0,400}?"home-name":"([^"]+)","away-name":"([^"]+)"',
            flat, re.S):
        eid, home, away = int(m.group(1)), m.group(2), m.group(3)
        out[eid] = {"home_raw": home, "away_raw": away,
                    "home": TEAM_MAP.get(home), "away": TEAM_MAP.get(away)}
    return out


def parse_odds(html: str) -> dict[int, dict]:
    """eventId → {home, away} 평균배당. h2h(2-way)만.

    🔴 **순서가 홈|원정이다.** `resultId` 로는 못 가른다 — 오늘 경기는 두
       항목이 모두 `resultId:0` 으로 온다(실측 2026-09-02). 대신 배열 순서가
       화면의 `cols:"1|2"` 와 같고, 1=홈·2=원정이 oddsportal 관례다.

       ⚠️ 관례를 **믿지 않고 검증했다.** 같은 날 MLB 슬레이트를 ESPN
          (독립 소스)과 대조해 **13/13 경기에서 첫 번째=홈**이 맞았고 값도
          소수점 둘째 자리까지 일치했다:
            Chicago White Sox|Houston Astros  oddsportal(1.72, 2.16)
                                              ESPN home 1.70 / away 2.17
          KBO·NPB 는 대조할 무료 소스가 없어 이 검증에 기댄다. 관례가 바뀌면
          MLB 대조가 먼저 깨지므로 그때 드러난다.
    """
    flat = _unescape(html)
    out: dict[int, dict] = {}
    for m in re.finditer(
            r'"[A-Za-z0-9]{6,10}":\{"event":(\d{6,9}),"odds":\[(\{.*?\})\],"cnt"',
            flat, re.S):
        eid, blob = int(m.group(1)), m.group(2)
        vals = re.findall(
            r'"avgOdds":([\d.]+),"bettingTypeId":%d,"scopeId":1' % BETTING_TYPE_H2H,
            blob)
        if len(vals) != 2:
            continue          # 2-way 가 아니면 손대지 않는다
        try:
            home, away = float(vals[0]), float(vals[1])
        except ValueError:
            continue
        if home > 1.0 and away > 1.0:
            out[eid] = {"home": round(home, 3), "away": round(away, 3)}
    return out


def to_rows(home: str, away: str, odds: dict) -> list[dict]:
    """우리 적재 계약. 한쪽만 있으면 그 한쪽만 — 역산하지 않는다."""
    out = []
    for side, team in (("home", home), ("away", away)):
        v = odds.get(side)
        if v and team:
            out.append({"book": "oddsportal-avg", "market": "h2h",
                        "side": team, "line": None, "odds": v})
    return out


async def fetch_league(sport: str, *, force: bool = False) -> dict[str, dict]:
    """리그 1회 요청 → {eventId: {home, away, rows[]}}. 실패하면 빈 dict."""
    import time

    from app.net.polite_client import PoliteClient

    url = LEAGUE_URL.get(sport)
    if not url:
        return {}
    if not force:
        last = _last_call.get(sport)
        if last is not None and (time.monotonic() - last) < MIN_INTERVAL_SEC:
            left = MIN_INTERVAL_SEC - (time.monotonic() - last)
            logger.info("[oddsportal] %s — %.0f초 전에 받았다. 요청 생략 "
                        "(최소 간격 %d분)", sport, MIN_INTERVAL_SEC - left,
                        MIN_INTERVAL_SEC // 60)
            return {}
    # ⚠️ **조건부 요청(ETag)을 쓰지 않는다.** 304 면 본문이 없어 빈 dict 을
    #    돌려주게 되고, 그러면 `odds_snapshots` 에 아무것도 안 쌓여 나이가
    #    늘어난다 — `W-ODDS-STALE` 이 "안 바뀌었다"를 "고장났다"로 읽는다.
    #    이 소스는 매번 본문을 받는다. 재시도·백오프·타임아웃은 클라이언트가 한다.
    html = None
    try:
        async with PoliteClient(PROVIDER) as c:
            r = await c.get(url, conditional=False)
            if r.status_code == 200:
                html = r.text
            else:
                # 401·403·429 는 클라이언트가 이미 "우회하지 않는다"고 남겼다.
                logger.warning("[oddsportal] %s 응답 %d — 이번 회차는 건너뛴다",
                               sport, r.status_code)
    except Exception as exc:
        logger.warning("[oddsportal] %s 조회 실패: %s", sport, exc)
    _last_call[sport] = time.monotonic()
    if html is None:
        return {}
    rows, odds = parse_rows(html), parse_odds(html)
    out: dict[str, dict] = {}
    unmapped: set[str] = set()
    for eid, g in rows.items():
        o = odds.get(eid)
        if not o:
            continue
        if not g["home"] or not g["away"]:
            unmapped.update(x for x in (g["home_raw"], g["away_raw"])
                            if x not in TEAM_MAP)
            continue
        r_ = to_rows(g["home"], g["away"], o)
        if r_:
            out[str(eid)] = {"home": g["home"], "away": g["away"], "rows": r_}
    if unmapped:
        logger.warning("[oddsportal] 팀명 미매핑 %s — TEAM_MAP 에 추가 필요",
                       ", ".join(sorted(unmapped)))
    logger.info("[oddsportal] %s — 경기 %d · 배당 %d · 확보 %d",
                sport.upper(), len(rows), len(odds), len(out))
    return out
