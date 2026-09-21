"""[A-2단계] KBO 1군 등록 명단 — 결장 판정의 절반. **LLM 0회.**

왜 딥서치를 대체하는가:
  결장 정보는 그동안 Perplexity 산문에서만 왔다. 그런데 KBO는 **말소로 결장을
  알린다** — 1군 등록 명단에서 빠지면 그 경기에 나올 수 없다. 이건 산문이 아니라
  공식 명단이고, 공개돼 있으며, 파싱하면 끝난다.

결장 판정은 두 조각이 필요하다:
  ① 누가 주전인가   → 최근 3경기 **타석 상위 9명** (app/collectors/kbo_usage)
  ② 누가 빠졌는가   → 오늘 1군 등록 명단에 없는 사람 (여기)
  ①∩②' = 주전인데 등록 명단에 없다 = **결장**

⚠️ 등록 명단은 "오늘 나올 수 있는 사람"이지 "오늘 나오는 사람"이 아니다.
   등록돼 있는데 라인업에 없는 것은 휴식일 수도, 대타 대기일 수도 있다 —
   그것까지 결장으로 부르면 매일 전 팀에 결장자가 쏟아진다.
   **말소된 주전만** 결장으로 본다.
"""

import logging
import re

logger = logging.getLogger(__name__)

BASE = "https://www.koreabaseball.com"
REGISTER_ALL = "/Player/RegisterAll.aspx"
CACHE_TTL = 6 * 3600      # 말소·등록은 경기 전 공시된다 — 하루 안에도 바뀐다

HEADERS = {"User-Agent": "Mozilla/5.0"}

# 표의 구단 표기는 "KT45명"처럼 인원이 붙는다. 숫자를 떼고 매핑한다.
TEAM_TO_ODDS = {
    "LG": "LG Twins", "두산": "Doosan Bears", "KT": "KT Wiz", "SSG": "SSG Landers",
    "NC": "NC Dinos", "키움": "Kiwoom Heroes", "한화": "Hanwha Eagles",
    "삼성": "Samsung Lions", "롯데": "Lotte Giants", "KIA": "Kia Tigers",
}

# 야수만 본다 — 결장 판정 대상은 타석 상위 9명이다.
BATTER_COLUMNS = ("포수", "내야수", "외야수")

#: 🔴 [ROS-1 2026-09-11] **델타용은 투수까지 본다.** 결장 판정(야수 9명)과
#   목적이 다르다 — 선발이 말소되면 그것이야말로 오늘 승부의 사건이다.
#   실측 2026-09-11: 갈림길 8/8·변수 15/17 이 투수였는데, 정작 투수 이탈을
#   알려 줄 공시 경로가 없었다.
ALL_COLUMNS = ("투수",) + BATTER_COLUMNS

#: 전 포지션 스냅샷. **결장 판정용 키와 섞지 않는다** — 소비자도 수명도 다르다.
FULL_KEY = "kbo_roster_full:{date}"
#: 어제와 비교하려면 하루를 넘겨 살아 있어야 한다. 5일이면 연휴도 덮는다.
FULL_TTL = 5 * 86400
#: 델타를 낼 때 거슬러 볼 최대 일수(휴식일·수집 실패를 건너뛴다).
LOOKBACK_DAYS = 5

_TAG = re.compile(r"<[^>]+>")
_NAME = re.compile(r"([^()0-9]+)\((\d+)\)")


def _cells(row: str) -> list[str]:
    return [_TAG.sub("", x).replace("&nbsp;", " ").strip()
            for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]


def parse_registered(html: str, columns=BATTER_COLUMNS) -> dict[str, set[str]]:
    """전체 등록 현황 HTML → {Odds 팀명: {등록 야수 이름}}.

    표는 헤더행과 데이터행이 번갈아 나온다. 헤더에서 열 위치를 읽어
    야수 열만 고른다 — 열 순서를 상수로 박으면 구조가 바뀔 때 조용히 어긋난다.
    """
    out: dict[str, set[str]] = {}
    header: list[str] = []
    for raw in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = _cells(raw)
        if not cells:
            continue
        if cells[0] == "구단":
            header = [re.sub(r"\(\d+\)", "", c).strip() for c in cells]
            continue
        if not header:
            continue
        team_raw = re.sub(r"\d+명$", "", cells[0]).strip()
        team = TEAM_TO_ODDS.get(team_raw)
        if not team:
            continue
        names: set[str] = set()
        for i, col in enumerate(header):
            if col not in columns or i >= len(cells):
                continue
            names |= {m.group(1).strip() for m in _NAME.finditer(cells[i])}
        if names:
            out[team] = names
    if not out:
        logger.error("[kbo_roster] 등록 명단 0팀 — 표 구조 변경 가능성")
    return out


class KBORosterClient:
    timeout = 20.0

    def __init__(self, mock: bool = False):
        self.mock = mock

    async def fetch(self) -> dict[str, set[str]]:
        return parse_registered(await self.fetch_html())

    async def fetch_html(self) -> str:
        """원문 HTML. **한 번만 받아 두 번 판다** — 요청을 늘리지 않는다."""
        # 🔴 [SRC-OFF 2026-09-21] robots 거부 소스는 **요청을 보내지 않는다.**
        #    판단은 `source_gate` 한 곳이 한다(사본 금지).
        from app.collectors.source_gate import require

        require("koreabaseball")

        import httpx

        async with httpx.AsyncClient(timeout=self.timeout,
                                     follow_redirects=True) as c:
            r = await c.get(BASE + REGISTER_ALL, headers=HEADERS)
        r.raise_for_status()
        return r.text


def absent_regulars(regulars: list[dict], registered: set[str]) -> list[dict]:
    """주전 중 **등록 명단에 없는 사람** = 결장.

    regulars 원소: {"name", "pa", "rank"} (kbo_usage.regulars 형식)

    ⚠️ 등록 명단을 못 받았으면 **빈 목록**을 돌려준다. 명단이 비었다고 전원을
       결장으로 만들면 그 경기 λ가 통째로 무너진다 — 수집 실패를 사실로
       바꾸는 최악의 유형이다.
    """
    if not registered:
        return []
    return [{**r, "reason": "1군 말소"} for r in regulars
            if r.get("name") and r["name"] not in registered]


def _key(date: str) -> str:
    return f"kbo_roster:{date}"


async def refresh(redis, date: str, client: KBORosterClient | None = None) -> dict:
    import json

    from app.collectors.base import freesource_mocked

    if freesource_mocked(client):        # [P5-1] 무인증 소스 — 목 모드
        return {"ok": False, "teams": 0, "mock": True}

    client = client or KBORosterClient()
    # [ROS-1] 원문을 한 번 받아 두 번 판다. 요청은 늘지 않는다.
    html = None
    try:
        html = await client.fetch_html()
        table = parse_registered(html)
    except AttributeError:               # 옛 목 클라이언트(테스트) 호환
        table = await client.fetch()
    if not table:
        from app.alerts import StageResult, stage_failed

        await stage_failed(StageResult(
            name="KBO 1군 등록", ok=0, total=1, cause="parse",
            detail="전체 등록 현황에서 0팀 파싱",
            impact="결장 판정이 통째로 빠집니다 (딥서치 산문에만 의존)"))
    await redis.set(_key(date),
                    json.dumps({k: sorted(v) for k, v in table.items()},
                               ensure_ascii=False), ex=CACHE_TTL)
    # [ROS-1] 전 포지션 스냅샷 — **델타의 재료**다. 어제와 비교하려면 하루를
    #   넘겨 살아 있어야 해서 수명이 다르다(기존 키는 6시간 그대로).
    full = 0
    if html is not None:
        table_all = parse_registered(html, ALL_COLUMNS)
        if table_all:
            await redis.set(FULL_KEY.format(date=date),
                            json.dumps({k: sorted(v) for k, v in table_all.items()},
                                       ensure_ascii=False), ex=FULL_TTL)
            full = len(table_all)
    logger.info("[kbo_roster] %s — %d팀 등록 명단 (전포지션 스냅샷 %d팀)",
                date, len(table), full)
    return {"teams": len(table), "full_teams": full}


async def load(redis, date: str) -> dict[str, set[str]]:
    import json

    raw = await redis.get(_key(date))
    return {k: set(v) for k, v in json.loads(raw).items()} if raw else {}


async def load_full(redis, date: str) -> dict[str, set[str]]:
    """전 포지션 스냅샷. 없으면 빈 dict."""
    import json

    raw = await redis.get(FULL_KEY.format(date=date))
    return {k: set(v) for k, v in json.loads(raw).items()} if raw else {}


def _shift(date: str, days: int) -> str:
    from datetime import date as _d
    from datetime import timedelta

    y, m, d = (int(x) for x in date.split("-"))
    return (_d(y, m, d) - timedelta(days=days)).isoformat()


async def roster_delta(redis, date: str) -> dict:
    """어제 대비 **말소·등록**. 공시를 '상태'가 아니라 '사건'으로 만든다.

    🔴 [ROS-1 2026-09-11] KBO 는 **말소로 결장을 알린다**(`kbo_roster` 머리말).
       그런데 우리는 '지금 명단에 없다'만 알았고 '오늘 빠졌다'를 몰랐다 —
       스냅샷 수명이 6시간이라 어제 것이 안 남았기 때문이다.
       MLB 는 `statsapi/transactions` 로 이미 사건을 받는다. 그 축을 KBO 에 맞춘다.

    반환: {"기준": 어제날짜|None, "사유": str|None,
           "팀": {팀명: {"말소": [...], "등록": [...]}}}

    ⚠️ 이전 스냅샷이 없으면 **빈 팀 dict + 사유**다. 빈 것을 "변화 없음"으로
       적지 않는다 — "모른다"와 "없다"는 다른 사실이다.
    """
    today = await load_full(redis, date)
    if not today:
        return {"기준": None, "사유": "오늘 전포지션 스냅샷 없음", "팀": {}}
    for back in range(1, LOOKBACK_DAYS + 1):
        prev_date = _shift(date, back)
        prev = await load_full(redis, prev_date)
        if prev:
            break
    else:
        return {"기준": None,
                "사유": f"직전 {LOOKBACK_DAYS}일 안에 비교할 스냅샷이 없음",
                "팀": {}}
    teams = {}
    for team, names in today.items():
        before = prev.get(team)
        if before is None:
            continue                      # 그 팀은 어제 자료가 없다 — 모른다
        out_ = sorted(before - names)
        in_ = sorted(names - before)
        if out_ or in_:
            teams[team] = {"말소": out_, "등록": in_}
    return {"기준": prev_date, "사유": None, "팀": teams}


def delta_articles(delta: dict, teams: list[str], now=None) -> list[dict]:
    """델타 → **위성 재료**(기사 dict). 사건이 있는 팀만 만든다.

    ⚠️ 기사 모양의 원본은 `satellite._article` 이다 — 여기서 키를 손으로
       늘리지 않는다.
    ⚠️ 변화가 0건이면 **기사도 0건**이다. 프롬프트를 "변화 없음"으로 채우지
       않는다 — 그건 정보가 아니라 잡음이다.
    """
    from app.collectors.satellite import _article

    base = delta.get("기준")
    out = []
    for team in teams:
        d = (delta.get("팀") or {}).get(team)
        if not d:
            continue
        bits = []
        if d.get("말소"):
            bits.append(f"1군 말소: {', '.join(d['말소'])}")
        if d.get("등록"):
            bits.append(f"1군 등록: {', '.join(d['등록'])}")
        if not bits:
            continue
        body = (f"KBO 공식 전체 등록 현황 기준, {base} 대비 {team} 의 "
                f"1군 엔트리 변동이다. " + " · ".join(bits) +
                ". 말소된 선수는 오늘 경기에 출전할 수 없다.")
        out.append(_article(
            title=f"[공시] {team} 1군 엔트리 변동 ({base} 대비) — "
                  + " · ".join(bits),
            url=BASE + REGISTER_ALL,
            source="KBO 공시(전체 등록 현황)",
            team=team, body=body, age_h=0.0))
    return out


def merge_into_research(research: dict, jg: dict, roster: dict) -> list[str]:
    """결장 목록을 research에 얹는다. 반환: 채운 필드 목록.

    ⚠️ 기존 `absences`(딥서치 산문)를 **덮지 않고 합친다.** 공시는 말소만 알고,
       딥서치는 부상·휴식 같은 다른 사유를 알 수 있다. 둘은 배타적이지 않다.
    """
    from app.research.crosscheck_sources import mark_collected

    if not roster:
        return []          # 명단을 못 받았으면 조사했다고 하지 않는다
    # 결장자가 0명이어도 **조사는 했다** — 그래야 딥서치를 다시 부르지 않는다.
    mark_collected(research, "absences")
    filled = []
    lines: list[str] = list(research.get("absences") or [])
    seen = {str(x) for x in lines}
    for side in ("home", "away"):
        team = jg.get(side)
        regulars = (research.get(f"{side}_usage") or {}).get("regulars") or []
        for a in absent_regulars(regulars, roster.get(team) or set()):
            line = (f"{team}의 {a['name']}(최근 3경기 타석 {a.get('pa', 0)}회, "
                    f"주전 {a.get('rank', '?')}번째) 1군 말소 — 출전 불가")
            if line not in seen:
                lines.append(line)
                seen.add(line)
    if lines != (research.get("absences") or []):
        research["absences"] = lines
        filled.append("absences")
    return filled
