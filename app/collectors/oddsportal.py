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

import asyncio
import json
import logging
import re
import time

logger = logging.getLogger(__name__)

PROVIDER = "oddsportal"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
TIMEOUT = 30.0

# ─────────────────── 크롤 예절 (상한을 코드에 박는다) ───────────────────
#: 재시도 **총 2회**(첫 시도 포함). 남의 서버는 우리 사정으로 두들길 대상이 아니다.
MAX_ATTEMPTS = 2
#: 재시도 백오프 초. 지수로 늘린다.
BACKOFF_SEC = 3.0
#: 같은 리그를 이 간격 안에 두 번 부르지 않는다. 30분 주기 + 발송 직전 1회를
#  허용하되, 폴링 틱이 겹쳐도 실제 요청은 이 간격으로 막힌다.
MIN_INTERVAL_SEC = 10 * 60
#: 마지막 요청 시각 (프로세스 내). redis 없이도 한 프로세스 안에서는 지켜진다.
_last_call: dict[str, float] = {}

LEAGUE_URL = {
    "kbo": "https://www.oddsportal.com/baseball/south-korea/kbo/",
    "npb": "https://www.oddsportal.com/baseball/japan/npb/",
}

#: 2-way 승패 마켓. 야구는 무승부가 없다. (scopeId 1)
BETTING_TYPE_H2H = 3
#: 🔴 [ODP-1 2026-09-13] 축구 1X2. 실측: 리그 페이지가 `bettingTypeId:1` ·
#   `scopeId:2` 로 세 값을 준다(EPL 90개=30경기×3, 라리가 87개).
#   ⚠️ 파생 시장(핸디·언더오버)은 **리그 페이지에 없다** — `handicapValue`
#      0건. 경기별 상세에만 있고 링크조차 HTML 에 안 실린다.
BETTING_TYPE_1X2 = 1
SCOPE_1X2 = 2

#: 축구 리그 URL. 🔴 **키는 `leagues.LEAGUES` 와 같아야 한다** — 목록을 손으로
#  적으면 그것이 사본이고, 리그가 늘 때 따라가지 않는다(계약이 전수 대조).
SOCCER_URL = {
    "epl":        "https://www.oddsportal.com/football/england/premier-league/",
    "la_liga":    "https://www.oddsportal.com/football/spain/laliga/",
    "serie_a":    "https://www.oddsportal.com/football/italy/serie-a/",
    "bundesliga": "https://www.oddsportal.com/football/germany/bundesliga/",
    "j1":         "https://www.oddsportal.com/football/japan/j1-league/",
    "denmark":    "https://www.oddsportal.com/football/denmark/superliga/",
    "kleague1":   "https://www.oddsportal.com/football/south-korea/k-league-1/",
    # 🔴 [ACL-1 2026-09-15] 실측으로 고른 URL 이다.
    #    /asia/afc-champions-league-elite/ → HTML 276,511자 · **경기행 0**
    #    /asia/afc-champions-league/       → HTML 645,657자 · 경기행 15 · 배당 16  ✅
    #    ⚠️ 이 페이지엔 `positionsWithProviders` 가 없다 — 북별 파싱 0경기.
    #       ACL 은 **평균 배당만** 된다(sharp/soft proxy 불가).
    "acl":        "https://www.oddsportal.com/football/asia/afc-champions-league/",
}

#: 🔴 정규화에서 **지우는 토큰**. 법인 형태 접미사와 창단 연도뿐이다.
#   실측 2026-09-13: `united`·`city`·`real`·`atletico` 까지 지웠더니
#   **맨시티=맨유 · 레알=AtM** 이 같은 키가 됐다. 팀을 구분하는 토큰은
#   절대 지우지 않는다 — 퍼지 매칭이 낸 사고(AC밀란→인테르)와 같은 구조다.
_DROP_TOKENS = {
    "fc", "afc", "cf", "cfc", "sc", "sv", "ac", "as", "ss", "ssc", "us",
    "rc", "rcd", "ca", "ud", "bc", "bk", "if", "calcio", "club", "de",
    "fussball", "fk", "balompie", "futbol",
    "1", "07", "04", "05", "1899", "1909", "1913", "1907", "1995",
}


def norm(name: str) -> str:
    """팀명 → 대조 키. **결정적이다 — 유사도를 쓰지 않는다.**"""
    import unicodedata

    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(t for t in s.split()
                    if t not in _DROP_TOKENS and not t.isdigit())


#: oddsportal 표기 → **우리 games 표기**. 정규화로 안 붙는 것만 적는다
#  (실측: 정규화만으로 66/122). 값은 최종 표기다 — 다시 별칭 키가 되면 순환이다.
SOCCER_ALIAS = {
    # 🔴 [ACL-1 2026-09-15] ACL 엘리트 — 오즈포털은 짧게 적고 FotMob 은 길게 적는다.
    #    값은 **FotMob 표기**다(경기를 FotMob 이 적재하므로 그쪽이 canonical).
    #    ⚠️ `Daejeon`·`Pohang` 은 **K리그1 에 이미 있다**(아래). 여기 다시 적으면
    #       같은 구단이 리그마다 다른 이름을 갖는다 — 적지 않는다.
    #       FotMob 쪽 긴 표기는 `fotmob.SLATE_CANONICAL` 이 맞춘다.
    "Kyoto": "Kyoto Sanga FC",
    "Cong An Ha Noi": "Công An Hà Nội",
    # EPL
    "Brighton": "Brighton & Hove Albion FC",
    "Coventry": "Coventry City FC",
    "Hull": "Hull City AFC",
    "Ipswich": "Ipswich Town FC",
    "Leeds": "Leeds United FC",
    "Manchester Utd": "Manchester United FC",
    "Newcastle": "Newcastle United FC",
    "Nottingham": "Nottingham Forest FC",
    "Tottenham": "Tottenham Hotspur FC",
    # 라리가
    "Alaves": "Deportivo Alavés",
    "Ath Bilbao": "Athletic Club",
    "Atl. Madrid": "Club Atlético de Madrid",
    "Betis": "Real Betis Balompié",
    "Dep. A Coruna": "RC Deportivo La Coruña",
    "Espanyol": "RCD Espanyol de Barcelona",
    "Racing Santander": "Real Racing Club de Santander",
    "Rayo Vallecano": "Rayo Vallecano de Madrid",
    # 세리에A
    "Fiorentina": "ACF Fiorentina",
    "Inter": "FC Internazionale Milano",
    # 분데스리가
    "B. Monchengladbach": "Borussia Mönchengladbach",
    "Bayern Munich": "FC Bayern München",
    "Dortmund": "Borussia Dortmund",
    "Hoffenheim": "TSG 1899 Hoffenheim",
    "Mainz": "1. FSV Mainz 05",
    "Stuttgart": "VfB Stuttgart",
    # 덴마크
    "Aarhus": "AGF Aarhus",
    "Odense": "OB Odense BK",
    # K리그1
    "Daejeon": "Daejeon Citizen",
    # ⚠️ 연고 이전(상주→김천)으로 같은 팀이라고 **판단**한 것이다. 측정이
    #    아니므로 첫 사이클에서 날짜·상대로 대조한다.
    "Gimcheon Sangmu": "Sangju Sangmu FC",
    "Incheon": "Incheon United",
    "Jeju SK": "Jeju United FC",
    "Jeonbuk": "Jeonbuk Hyundai Motors",
    "Pohang": "Pohang Steelers",
    "Ulsan HD": "Ulsan Hyundai FC",
    # J1 — 우리 DB 에 경기가 있는 팀만. 나머지 18팀은 **추측해서 만들지 않는다.**
    "Machida": "FC Machida Zelvia",
    "Urawa Reds": "Urawa Red Diamonds",
}


#: 🔴 [ACL-1] 국제 대회 표에서만 붙는 **국가 접미사**. `Gamba Osaka (Jpn)`.
#   ⚠️ 패턴을 좁게 잡는다 — **끝에 붙은 괄호 3글자**만. `Hull City AFC` 처럼
#      괄호 없는 이름이나 `1. FC Köln` 같은 것은 건드리지 않는다(계약이 잠근다).
_COUNTRY_SUFFIX = re.compile(r"\s*\([A-Za-z]{3}\)\s*$")


def strip_country(op_name: str) -> str:
    """`'Gamba Osaka (Jpn) '` → `'Gamba Osaka'`. 그 외는 공백만 다듬는다."""
    return _COUNTRY_SUFFIX.sub("", str(op_name or "")).strip()


def team_key(op_name: str) -> str:
    """oddsportal 표기 → 대조 키(국가 접미사 제거 → 별칭 → 정규화)."""
    base = strip_country(op_name)
    return norm(SOCCER_ALIAS.get(base, base))

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


def parse_odds(html: str, *, three_way: bool = False) -> dict[int, dict]:
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
    # 🔴 [ODP-1] `three_way` 기본값은 **False** — 야구 경로가 종전 그대로다.
    bt, scope, want = ((BETTING_TYPE_1X2, SCOPE_1X2, 3) if three_way
                       else (BETTING_TYPE_H2H, 1, 2))
    for m in re.finditer(
            r'"[A-Za-z0-9]{6,10}":\{"event":(\d{6,9}),"odds":\[(\{.*?\})\],"cnt"',
            flat, re.S):
        eid, blob = int(m.group(1)), m.group(2)
        vals = re.findall(
            r'"avgOdds":([\d.]+),"bettingTypeId":%d,"scopeId":%d' % (bt, scope),
            blob)
        if len(vals) != want:
            continue          # 칸 수가 다르면 손대지 않는다
        try:
            nums = [float(v) for v in vals]
        except ValueError:
            continue
        if any(v <= 1.0 for v in nums):
            continue
        # oddsportal 관례: 1X2 는 **홈|무|원정**, 2-way 는 홈|원정
        keys = ("home", "draw", "away") if three_way else ("home", "away")
        out[eid] = {k: round(v, 3) for k, v in zip(keys, nums)}
    return out


def _balanced(text: str, start: int) -> str:
    """`text[start]` 의 `{` 부터 짝이 맞는 `}` 까지. 못 찾으면 빈 문자열.

    🔴 JSON 조각을 정규식으로 자르면 중첩에서 잘린다(실측 2026-09-14:
       `positionsWithProviders` 가 첫 북에서 끊겼다).
    """
    if start < 0 or start >= len(text) or text[start] != "{":
        return ""
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return ""


#: [D1-4 사용자 지시] 이 환급률 미만이면 **샤프북이 없다**고 본다.
#  🔴 실측 2026-09-14: 오즈포털이 주는 북 넷의 환급률이 92.6~95.9% 였다.
#     피나클급(97~98%)이 하나도 없다 — `sharp_proxy` 는 "덜 넓은 마진의
#     소프트북"일 뿐이고, 그 사실을 값에 붙여 다녀야 해석이 안 뒤집힌다.
SHARP_MIN_PAYOUT = 96.0

#: [D1-1] `sharp_proxy` 를 세우는 최소 활성 북 수(사용자 지시).
#  🔴 표본이 적으면 "가장 높은 환급률"이 우연이다. 그때는 **만들지 않는다.**
SHARP_MIN_BOOKS = 3


def parse_books(blob: str, *, three_way: bool = False) -> dict[int, dict]:
    """[D1-1] eventId → 북별 배당 + `sharp_proxy`.

    반환 `{eid: {"books": {id: {home,draw,away}}, "payout": {id: %},
                 "sharp_id": id|None, "n": 활성 북 수}}`

    🔴 **피나클을 이름으로 특정할 수 없다**(북메이커 페이지에 id↔이름 표가
       없다 — 실측). 그래서 `sharp_id` 는 그 스냅샷에서 `highestPayout` 이
       가장 높은 id 다. **피나클이라 단정하지 않는다.**
    ⚠️ 결과 위치(0=홈·1=무·2=원정)는 `parse_odds` 와 **같은 관례**다.
    """
    keys = ("home", "draw", "away") if three_way else ("home", "away")
    out: dict[int, dict] = {}
    for m in re.finditer(
            r'"event":(\d{6,9}),"odds":\[(\{.*?\})\],"cnt"', blob or "", re.S):
        eid, body = int(m.group(1)), m.group(2)
        books: dict[int, dict] = {}
        payout: dict[int, float] = {}
        # 🔴 정규식으로 중첩 객체를 자르지 않는다 — `(.*?)\}\}` 는 첫 북에서
        #    잘린다(실측). **괄호 균형**으로 정확히 떼어낸다.
        for mk in re.finditer(r'"positionsWithProviders":', body):
            chunk = _balanced(body, body.find("{", mk.end()))
            for pos_m in re.finditer(r'"([012])":\{', chunk):
                pos = int(pos_m.group(1))
                if pos >= len(keys):
                    continue
                inner = _balanced(chunk, pos_m.end() - 1)
                # 🔴 [D1-2] **포지션마다 `odds` 모양이 다르다**(실측 2026-09-14):
                #    위치 0 은 배열 `[5.25]`, 위치 1·2 는 객체 `{"1":3.8}`.
                #    배열만 받던 정규식이 무·원정 칸을 통째로 비워 북별 파싱이
                #    0건이 됐다. 두 모양을 다 받는다.
                for bm in re.finditer(
                        r'"(\d{2,5})":\{"odds":(?:\[([\d.]+)\]'
                        r'|\{"\d+":([\d.]+)\})[^}]*?'
                        r'"highestPayout":([\d.]+)', inner):
                    bid = int(bm.group(1))
                    odd = float(bm.group(2) or bm.group(3))
                    pay = float(bm.group(4))
                    if odd <= 1.0:
                        continue
                    books.setdefault(bid, {})[keys[pos]] = round(odd, 3)
                    payout[bid] = pay
        # 칸이 다 찬 북만 센다 — 반쪽 배당으로 디빅하면 확률이 부푼다.
        full = {b: v for b, v in books.items() if len(v) == len(keys)}
        sharp = soft = None
        if len(full) >= SHARP_MIN_BOOKS:
            sharp = max(full, key=lambda b: (payout.get(b, 0.0), -b))
            # 🔴 [D1-3 사용자 지시] 마진이 가장 **넓은** 북이 사설 대용이다.
            soft = min(full, key=lambda b: (payout.get(b, 0.0), b))
            if soft == sharp:
                # 같은 북을 양쪽에 놓으면 gap 이 늘 0이다 — 둘 다 세우지 않는다.
                sharp = soft = None
        if full:
            top = max((payout.get(b, 0.0) for b in full), default=0.0)
            out[eid] = {"books": full, "payout": payout, "sharp_id": sharp,
                        "soft_id": soft, "n": len(full),
                        "top_payout": round(top, 1),
                        # 🔴 [D1-4] 값은 그대로 두고 **해석에 플래그를 붙인다.**
                        "sharp_absent": top < SHARP_MIN_PAYOUT}
    return out


def to_rows(home: str, away: str, odds: dict,
            books: dict | None = None) -> list[dict]:
    """우리 적재 계약. 한쪽만 있으면 그 한쪽만 — 역산하지 않는다.

    🔴 [D1-1] `books` 를 주면 **북별 줄**(`op-{id}`)과 `sharp_proxy` 를 더한다.
       평균 줄(`oddsportal-avg`)은 **그대로 남긴다**(사용자 지시 — 비교용).
       안 주면 종전과 똑같은 한 벌이다(야구 경로 무영향).
    """
    out = []
    # 🔴 [ODP-1] 무승부는 **`draw` 키가 있을 때만** 만든다. 야구에 무승부
    #    칸이 생기면 디빅이 3-way 로 잘못 돌아 승/패 확률이 부풀고
    #    전 경기 +EV 착시가 난다(`_market_probs` 실사고 이력).
    sides = (("home", home), ("draw", "Draw"), ("away", away))
    for side, team in sides:
        v = odds.get(side)
        if v and team:
            out.append({"book": "oddsportal-avg", "market": "h2h",
                        "side": team, "line": None, "odds": v})
    for bid, vals in ((books or {}).get("books") or {}).items():
        for side, team in sides:
            v = vals.get(side)
            if v and team:
                out.append({"book": f"op-{bid}", "market": "h2h",
                            "side": team, "line": None, "odds": v})
    for key, label in (("sharp_id", "sharp_proxy"), ("soft_id", "soft_proxy")):
        pid = (books or {}).get(key)
        if pid is None:
            continue
        for side, team in sides:
            v = ((books.get("books") or {}).get(pid) or {}).get(side)
            if v and team:
                out.append({"book": label, "market": "h2h",
                            "side": team, "line": None, "odds": v})
    return out


async def _get(url: str, tag: str) -> str | None:
    """한 번 요청. 실패하면 None. **간격 기록은 호출부가 이미 했다.**

    ⚠️ 요청 블록을 두 벌 적지 않기 위해 꺼냈다 — 야구·축구가 같은 것을 쓴다.
    """
    import httpx

    for attempt in range(MAX_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True,
                                         headers={"User-Agent": UA}) as c:
                r = await c.get(url)
                r.raise_for_status()
                logger.info("[oddsportal] %s 응답 %dB (시도 %d/%d)",
                            tag, len(r.content), attempt + 1, MAX_ATTEMPTS)
                _last_call[tag] = time.monotonic()
                return r.text
        except Exception as exc:
            logger.warning("[oddsportal] %s 조회 실패 (시도 %d/%d): %s",
                           tag, attempt + 1, MAX_ATTEMPTS, exc)
            if attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(BACKOFF_SEC * (attempt + 1))
    _last_call[tag] = time.monotonic()
    return None


def _throttled(tag: str) -> bool:
    last = _last_call.get(tag)
    if last is None or (time.monotonic() - last) >= MIN_INTERVAL_SEC:
        return False
    logger.info("[oddsportal] %s — %.0f초 전에 받았다. 요청 생략 (최소 간격 %d분)",
                tag, time.monotonic() - last, MIN_INTERVAL_SEC // 60)
    return True


async def fetch_soccer_league(league: str, *, force: bool = False) -> list[dict]:
    """[ODP-1] 축구 리그 1회 요청 → `[{home_raw, away_raw, key_home, key_away, rows}]`.

    🔴 팀명을 **여기서 우리 표기로 바꾸지 않는다.** 대조 키만 낸다 —
       실제 경기 행과 맞추는 것은 `odds_free.collect_soccer` 의 몫이고,
       그래야 같은 팀의 두 표기(`Aston Villa` / `Aston Villa FC`)가 둘 다 붙는다.
    """
    url = SOCCER_URL.get(league)
    if not url or (not force and _throttled(league)):
        return []
    html = await _get(url, league)
    if html is None:
        return []
    rows, odds = parse_rows(html), parse_odds(html, three_way=True)
    # 🔴 [D1-1] **같은 응답을 더 파싱할 뿐이다 — 요청은 늘지 않는다.**
    books = parse_books(_unescape(html), three_way=True)
    out: list[dict] = []
    n_sharp = 0
    for eid, g in rows.items():
        o = odds.get(eid)
        if not o:
            continue
        bk = books.get(eid)
        if bk and bk.get("sharp_id") is not None:
            n_sharp += 1
        r_ = to_rows(g["home_raw"], g["away_raw"], o, books=bk)
        if not r_:
            continue
        out.append({"event": str(eid),
                    "home_raw": g["home_raw"], "away_raw": g["away_raw"],
                    "key_home": team_key(g["home_raw"]),
                    "key_away": team_key(g["away_raw"]),
                    "rows": r_})
    logger.info("[oddsportal] %s — 경기 %d · 배당 %d · 확보 %d · "
                "북별 %d경기(샤프대용 %d · 최소 %d북)",
                league, len(rows), len(odds), len(out), len(books), n_sharp,
                SHARP_MIN_BOOKS)
    return out


async def fetch_league(sport: str, *, force: bool = False) -> dict[str, dict]:
    """리그 1회 요청 → {eventId: {home, away, rows[]}}. 실패하면 빈 dict."""


    url = LEAGUE_URL.get(sport)
    if not url:
        return {}
    if not force and _throttled(sport):
        return {}
    html = await _get(url, sport)
    if html is None:
        return {}
    rows, odds = parse_rows(html), parse_odds(html)
    # 🔴 [D1-1] 야구도 같은 응답에서 북별 값을 받는다(요청 증가 0).
    #    2-way 라 칸이 둘이고, 그 판정은 `parse_books` 의 `three_way` 가 한다.
    books = parse_books(_unescape(html))
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
        r_ = to_rows(g["home"], g["away"], o, books=books.get(eid))
        if r_:
            out[str(eid)] = {"home": g["home"], "away": g["away"], "rows": r_}
    if unmapped:
        logger.warning("[oddsportal] 팀명 미매핑 %s — TEAM_MAP 에 추가 필요",
                       ", ".join(sorted(unmapped)))
    logger.info("[oddsportal] %s — 경기 %d · 배당 %d · 확보 %d",
                sport.upper(), len(rows), len(odds), len(out))
    return out
