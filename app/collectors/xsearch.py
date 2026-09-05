"""[정찰 AI 뉴스층] Grok x_search — X 속보를 **항목으로** 받는다.

🔴 **판정 경로와 격리한다.** `research/grok.py` 의 기존 함수들은 산문 요약을
   돌려주고 그것이 판정에 넘어간다. 여기는 다르다 — 헤드라인·URL·게시시각·
   계정만 받고, **요약문은 저장하지 않는다.** AI 가 쓴 문장을 판정 재료로
   넣으면 그것이 제2의 환각 경로가 된다.

🔴 **URL 이 실재해야 자료2 후보가 된다.** 모델이 지어낸 링크는 fetch 에서
   걸러진다. URL 없는 항목·fetch 실패 항목은 폐기하고 그 수를 센다.

🔴 **계정명을 보존한다.** X 포스트는 루머가 섞인다. 판정 모델이 출처 신뢰도를
   스스로 볼 수 있어야 한다 — 우리가 대신 판단해 버리지 않는다.

상한 (config 가 원본):
  · 경기당 1콜  — `(game_id, date)` Redis 키로 dedupe
  · 일일 N콜    — `scout_xsearch_daily_cap`
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

SOURCE = "xsearch"

#: 발동 판별에 쓰는 RSS 하한. config 가 원본 — 여기 숫자를 적지 않는다.
_ONCE_KEY = "xsearch:done:{sport}:{game_id}:{date}"
_CAP_KEY = "xsearch:calls:{date}"
_TTL = 26 * 3600

PROMPT = """오늘({date}) {league} 경기 "{away} @ {home}" 에 대한 X(트위터) 속보를 찾아라.

찾을 것: 선발 변경 · 결장/부상 · 라인업 발표 · 구단 공지.
또한 **팀의 공기**: {situation}.
  — 구단 공식 계정·비트기자의 현장 속보가 여기 먼저 뜬다.
찾지 말 것: 응원·예상·중계 안내·과거 경기 회고.

**JSON 배열만 출력한다. 다른 말 금지.** 최대 8건.
[{{"headline":"게시물 요지 한 줄","url":"게시물 URL","at":"YYYY-MM-DDTHH:MM","account":"@계정"}}]

규칙:
- `url` 은 **실제 게시물 주소**여야 한다. 없으면 그 항목을 빼라. 지어내지 마라.
- `at` 은 게시 시각이다. 모르면 그 항목을 빼라.
- 오늘 또는 어제 게시물만. 그보다 오래된 것은 빼라.
- 찾은 것이 없으면 빈 배열 `[]` 을 출력하라."""


def _cfg():
    from app.config import get_settings

    return get_settings()


def should_fire(rss_count: int, lineup_status: str | None,
                minutes_to_start: float | None, settings=None) -> tuple[bool, str]:
    """발동하는가. 반환 (발동, 사유).

    조건: (T-N 라인업 미확정) OR (RSS < 하한)
    🔴 **RSS 0건도 조건에 포함된다.** "재료가 아예 없는 경기"야말로 AI 층이
       필요한 경우인데, `if rss_count:` 같은 판별을 쓰면 0건이 통째로
       빠진다 — 조용한 0 의 전형이다.
    """
    s = settings or _cfg()
    lo = int(s.scout_xsearch_rss_floor)
    if rss_count < lo:
        return True, f"RSS {rss_count}건 < {lo}"
    tn = float(s.scout_xsearch_lineup_min)
    if (minutes_to_start is not None and minutes_to_start <= tn
            and (lineup_status or "none") != "confirmed"):
        return True, f"T-{minutes_to_start:.0f}분 라인업 {lineup_status or 'none'}"
    return False, f"RSS {rss_count}건 · 라인업 {lineup_status or 'none'}"


async def _once_ok(redis, sport: str, game_id, date: str) -> bool:
    """경기당 1콜. 이미 돌았으면 False 이고 그 사실을 로그에 남긴다."""
    if redis is None:
        return True
    key = _ONCE_KEY.format(sport=sport, game_id=game_id, date=date)
    try:
        first = await redis.set(key, "1", ex=_TTL, nx=True)
    except Exception as exc:
        logger.debug("[xsearch] dedupe 키 실패: %s", exc)
        return True
    if not first:
        logger.info("[xsearch] 경기당 1콜 — 이미 호출됨, 생략 game=%s", game_id)
    return bool(first)


async def _cap_ok(redis, date: str, settings=None) -> bool:
    """일일 캡. 초과면 False 이고 **소리 낸다**."""
    s = settings or _cfg()
    cap = int(s.scout_xsearch_daily_cap)
    if redis is None:
        return True
    try:
        n = await redis.incr(_CAP_KEY.format(date=date))
        await redis.expire(_CAP_KEY.format(date=date), _TTL)
    except Exception as exc:
        logger.debug("[xsearch] 캡 카운터 실패: %s", exc)
        return True
    if int(n) > cap:
        logger.warning("[xsearch] 🔴 일일 캡 %d콜 도달 — 이후 호출 차단 (%d번째)",
                       cap, int(n))
        return False
    logger.info("[xsearch] 일일 사용 %d/%d", int(n), cap)
    return True


def parse_items(text: str) -> list[dict]:
    """모델 응답 → 항목 목록. **요약문은 담지 않는다.**"""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    i, j = raw.find("["), raw.rfind("]")
    if i < 0 or j <= i:
        return []
    try:
        arr = json.loads(raw[i:j + 1])
    except ValueError:
        return []
    out = []
    for x in arr if isinstance(arr, list) else []:
        if not isinstance(x, dict):
            continue
        url, at = str(x.get("url") or "").strip(), str(x.get("at") or "").strip()
        head = str(x.get("headline") or "").strip()
        if not url.startswith("http") or not at or not head:
            continue          # URL·시각·헤드라인이 없으면 검증할 수 없다
        out.append({"title": head, "url": url, "at": at,
                    "account": str(x.get("account") or "").strip(),
                    "source": SOURCE})
    return out


async def verify_urls(items: list[dict]) -> tuple[list[dict], dict]:
    """URL 실재 검증. 반환 (통과분, {ok, no_url, dead})."""
    import httpx

    stat = {"ok": 0, "no_url": 0, "dead": 0}
    out = []
    async with httpx.AsyncClient(timeout=float(_cfg().crawl_timeout_sec),
                                 follow_redirects=True) as c:
        for it in items:
            u = it.get("url")
            if not u:
                stat["no_url"] += 1
                continue
            try:
                r = await c.get(u)
            except Exception as exc:
                stat["dead"] += 1
                logger.info("[xsearch] URL 폐기(조회 실패) %s: %s", u[:60], exc)
                continue
            if r.status_code != 200:
                stat["dead"] += 1
                logger.info("[xsearch] URL 폐기(%d) %s", r.status_code, u[:60])
                continue
            stat["ok"] += 1
            out.append(it)
    if stat["no_url"] or stat["dead"]:
        logger.warning("[xsearch] 환각 방어 — 폐기 %d건 (URL없음 %d · 죽은링크 %d)",
                       stat["no_url"] + stat["dead"], stat["no_url"], stat["dead"])
    return out, stat


async def fetch_for_game(jg: dict, date: str, redis=None,
                         settings=None) -> list[dict]:
    """이 경기의 X 속보 항목. 상한·검증을 통과한 것만. 실패하면 빈 목록.

    ⚠️ **실패가 수집을 막지 않는다** — RSS 만으로 진행하고 로그 1줄을 남긴다.
    """
    s = settings or _cfg()
    sport, gid = (jg.get("sport") or "").lower(), jg.get("game_id")
    if not await _once_ok(redis, sport, gid, date):
        return []
    if not await _cap_ok(redis, date, s):
        return []
    from app.research.grok import GrokClient

    # [상황 변수 2026-09-06] 상황 축을 쿼리에 함께 싣는다. **캡은 그대로다**
    #   (경기당 1회·일 12콜) — 늘어난 것은 프롬프트 한 줄뿐이다.
    #   종목별 키워드는 registry 가 원본이다.
    from app.registry import situation_axes as _axes

    _terms = [w[0] for w in _axes(sport).values() if w][:8]
    prompt = PROMPT.format(date=date, league=sport.upper(),
                           away=jg.get("away"), home=jg.get("home"),
                           situation=" · ".join(_terms) or "구단 주변 상황")
    #  ⚠️ `GrokClient.__init__(mock=None)` 만 받는다 — settings 를 넘기면
    #     TypeError 다(시뮬 실측 2026-09-06). 설정은 생성자가 스스로 읽는다.
    try:
        text = await GrokClient()._search_call(prompt)
    except Exception as exc:
        logger.warning("[xsearch] 호출 실패 game=%s — RSS 만으로 진행: %s", gid, exc)
        return []
    items = parse_items(text)
    logger.info("[xsearch] game=%s 응답 %d항목", gid, len(items))
    kept, stat = await verify_urls(items)
    logger.info("[xsearch] game=%s 적재 %d건 (검증 %s)", gid, len(kept), stat)
    return kept
