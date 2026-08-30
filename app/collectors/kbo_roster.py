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

_TAG = re.compile(r"<[^>]+>")
_NAME = re.compile(r"([^()0-9]+)\((\d+)\)")


def _cells(row: str) -> list[str]:
    return [_TAG.sub("", x).replace("&nbsp;", " ").strip()
            for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]


def parse_registered(html: str) -> dict[str, set[str]]:
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
            if col not in BATTER_COLUMNS or i >= len(cells):
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
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout,
                                     follow_redirects=True) as c:
            r = await c.get(BASE + REGISTER_ALL, headers=HEADERS)
        r.raise_for_status()
        return parse_registered(r.text)


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
    logger.info("[kbo_roster] %s — %d팀 등록 명단", date, len(table))
    return {"teams": len(table)}


async def load(redis, date: str) -> dict[str, set[str]]:
    import json

    raw = await redis.get(_key(date))
    return {k: set(v) for k, v in json.loads(raw).items()} if raw else {}


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
