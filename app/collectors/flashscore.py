"""[SOC-8] Flashscore 라인업 — 축구 층1. 킥오프 **1시간 전**에 전 경기 제공.

사용자 지시 2026-09-12: "라인업은 굳이 딥서치 안해도 된다 .. 공식 url 에서
한시간 전에 모두 제공한다" → "flashscore 써라"

실측 2026-09-12 23:30 (운영):
    당일 축구 피드 3166경기 · 우리 31경기 매칭 31/31 (실패 0)
    킥오프 1시간 안 13경기 = 포메이션·선발 수신 / 먼 경기 = 0명

피드 문법 — `¬` 로 필드, `~` 로 개체를 나눈다:
    LB÷섹션(선발/교체/감독)   LC÷1|2 (홈/원정)   LD÷포메이션
    LH÷순번  LI÷이름  LJ÷등번호  NU÷/player/<슬러그>/<id>/

🔴 **블록 단위로 읽는다.** 처음에 `NU÷` 만 정규식으로 긁었다가 알파벳순으로
   정렬된 목록을 보고 "남의 팀 선수가 섞였다"고 잘못 보고했다. 한 블록이 한
   선수다 — 이름·등번호는 같은 블록에서만 짝짓는다.
🔴 **선수 소속을 이름으로 추측하지 않는다.** 낯선 이름을 보고 "다른 팀"이라
   단정했는데 2026 이적을 우리는 모른다. 소속은 `LC÷` 가 정한다.
🔴 **섹션은 순서로 가른다.** 응답이 러시아어로 오므로 섹션명 문자열에 기대지
   않는다 — 첫 그룹이 선발, 그다음이 교체다.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

FEED = "https://global.flashscore.ninja/2/x/feed"
#: 피드가 요구하는 서명 헤더. 없으면 빈 응답이다.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Referer": "https://www.flashscore.com/",
    "x-fsign": "SW9D1eZo",
}
#: 축구(1) · 당일(0)/익일(1) · 타임존 3
DAY_FEED = "f_1_{day}_3_en_1"
LINEUP_FEED = "df_li_1_{mid}"

_F = re.compile(r"([A-Z]{2,4})÷([^¬~|]*)")


def _fields(block: str) -> dict:
    """한 블록의 키/값. 같은 키가 여러 번이면 **첫 값**."""
    out: dict[str, str] = {}
    for k, v in _F.findall(block):
        out.setdefault(k, v.strip())
    return out


def parse_fixtures(text: str) -> list[dict]:
    """당일 피드 → [{id, home, away, ts}]. home/away 는 라틴 슬러그다."""
    out = []
    for blk in (text or "").split("~AA÷")[1:]:
        mid = blk[:8]
        f = _fields(blk)
        home, away = f.get("WU"), f.get("WV")
        if not (mid and home and away):
            continue
        try:
            ts = int(f.get("AD") or 0)
        except ValueError:
            ts = 0
        out.append({"id": mid, "home": home, "away": away, "ts": ts})
    return out


def parse_lineup(text: str) -> dict:
    """라인업 피드 → {"홈": {...}, "원정": {...}}.

    각 팀은 `{"포메이션": str, "선발": [{"이름","번호"}], "교체": [...]}`.
    ⚠️ 구분자가 블록 경계와 어긋날 수 있어 **선형 주사**로 읽는다.
    """
    teams: dict[str, dict] = {"홈": {"포메이션": "", "선발": [], "교체": []},
                              "원정": {"포메이션": "", "선발": [], "교체": []}}
    side: str | None = None
    grp = {"홈": -1, "원정": -1}
    cur: dict | None = None

    def _flush():
        nonlocal cur
        if cur and side is not None:
            slot = {0: "선발", 1: "교체"}.get(grp[side])
            if slot and cur.get("이름"):
                teams[side][slot].append(cur)
        cur = None

    for k, v in _F.findall(text or ""):
        v = v.strip()
        if k == "LC":
            _flush()
            side = "홈" if v == "1" else "원정"
            grp[side] += 1
        elif side is None:
            continue
        elif k == "LD":
            if not teams[side]["포메이션"]:
                teams[side]["포메이션"] = v
        elif k == "LP":
            _flush()
            cur = {"이름": "", "번호": ""}
        elif k == "LI" and cur is not None:
            cur["이름"] = v
        elif k == "LJ" and cur is not None:
            cur["번호"] = v
    _flush()
    return teams


def match_key(slug: str) -> set[str]:
    """슬러그 → 대조 토큰. `hull-city` → {hull, city}."""
    return {t for t in (slug or "").split("-") if len(t) > 2}


def find_fixture(fixtures: list[dict], home_toks: set[str],
                 away_toks: set[str], ts: int, *,
                 window: int = 3600) -> str | None:
    """🔴 **양 팀 + 시각 3중 조건.** 하나라도 어긋나거나 후보가 둘 이상이면
    버린다 — 남의 경기 라인업을 붙이는 것은 빈손보다 나쁘다(SAT-S4 전례)."""
    hit = [f for f in fixtures
           if (match_key(f["home"]) & home_toks)
           and (match_key(f["away"]) & away_toks)
           and abs(f["ts"] - ts) < window]
    return hit[0]["id"] if len(hit) == 1 else None


#: 당일 피드 캐시 — 슬레이트당 한 번만 받는다.
_FS_CACHE: dict[str, tuple[str, list[dict]]] = {}


def cache_clear() -> None:
    _FS_CACHE.clear()


async def _get(path: str) -> str:
    import httpx

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True,
                                 headers=HEADERS) as c:
        r = await c.get(f"{FEED}/{path}")
        r.raise_for_status()
        return r.text


async def fixtures_for(today: str) -> list[dict]:
    hit = _FS_CACHE.get("all")
    if hit and hit[0] == today:
        return hit[1]
    out: list[dict] = []
    for day in ("0", "1"):
        try:
            out += parse_fixtures(await _get(DAY_FEED.format(day=day)))
        except Exception as exc:
            logger.warning("[flashscore] 일정 피드 실패 day=%s: %s", day, exc)
    _FS_CACHE.clear()
    _FS_CACHE["all"] = (today, out)
    return out


async def lineup_for(mid: str) -> dict:
    return parse_lineup(await _get(LINEUP_FEED.format(mid=mid)))
