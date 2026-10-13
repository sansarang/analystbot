"""🔴🔴 **§6-3 본문 확보** — 지시서 2026-10-13 밤 셋째.

> 순서: **원문 → AMP 판 → 구단·리그 RSS → 원천 표에 적힌 대체 경로.**
> 실패 사유를 **칸별로** 기록(robots·4xx·5xx·빈 본문·자바스크립트 렌더 필요).
> 재시도·캐시·속도 제한(도메인당). 렌더 필요 원천은 원천 표에 표시하고 별도
> 처리 목록으로.
> 계약 **FT1**: 실패를 조용히 버리면 실패(**사유 0건 금지**).

🔴 **칸을 왜 넷으로 나누나** — 실측(2026-10-13 · 49장 깔때기): 본문 없음으로
   버린 문서가 가장 많았고, 그 중 상당수는 **원문이 자바스크립트 렌더**거나
   4xx 였다. 원문 하나로 끝내면 그 문서는 통째로 사라진다.
🔴 **AMP 는 추측해 붙이지 않는다** — 원문 HTML 의 `<link rel="amphtml">` 에
   적힌 주소만 쓴다(CLAUDE.md #4: 받아서 확인한 것만).
🔴 **RSS·대체 경로는 원천 표가 든다**(`config/sources/*.yaml` 의 `rss`·`alt`) —
   코드에 주소를 적지 않는다. 표에 없으면 그 칸은 **⬜ 통로 없음**이다.
"""
from __future__ import annotations

import logging
import re
import time
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

#: 🔴 칸 이름 — 이 순서로 내려간다(카드·보고가 이 글자를 적는다)
RUNGS: tuple[str, ...] = ("원문", "AMP", "RSS", "대체 경로")

#: 🔴 도메인당 **최소 간격**(초) — 표에 `min_interval` 이 있으면 그것이 이긴다
MIN_INTERVAL = 1.0

#: 🔴 한 칸에서 몇 번까지 다시 받나(5xx·시간초과만 · 4xx 는 **다시 안 받는다**)
RETRY = 1

#: 🔴 자바스크립트 렌더가 필요하다고 볼 꼴 — 본문이 비고 이 낱말만 있는 판
_JS = re.compile(r"(enable javascript|javascript is required|"
                 r"자바스크립트를 활성화|JavaScript를 사용)", re.I)

_AMP = re.compile(r"<link[^>]+rel=[\"']?amphtml[\"']?[^>]*>", re.I)
_HREF = re.compile(r"href=[\"']([^\"']+)[\"']", re.I)

#: 🔴 도메인마다 **마지막으로 받은 시각**(속도 제한 · 한 실행 안에서만 산다)
_LAST: dict[str, float] = {}


def host_of(url: str) -> str:
    try:
        return (urlparse(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""


def amp_of(html: str) -> str:
    """🔴 원문 HTML 의 `<link rel="amphtml">` 주소. 없으면 **빈 글자**."""
    got = _AMP.search(str(html or ""))
    if not got:
        return ""
    said = _HREF.search(got.group(0))
    return str(said.group(1)) if said else ""


def _rows_of(league: str, host: str) -> dict:
    """🔴 그 도메인의 표 줄(등급 어디에 있든 하나로). 없으면 빈 사전."""
    from app.core.search import sources as _sr
    for grade in _sr.ORDER:
        for one in _sr.rows_of(str(league or ""), grade):
            said = str(one.get("domain") or "").lower()
            if said and (host == said or host.endswith("." + said)):
                return dict(one)
    return {}


def rss_of(league: str, url: str) -> list[str]:
    """🔴 그 도메인의 **RSS 주소 목록**(원천 표가 든다 · 추측 금지)."""
    box = _rows_of(league, host_of(url))
    said = box.get("rss")
    rows = said if isinstance(said, list) else ([said] if said else [])
    return [str(x) for x in rows if str(x or "").startswith("http")]


def alt_of(league: str, url: str) -> list[str]:
    """🔴 표에 적힌 **대체 경로**(`alt`) — 주소 그대로이거나 `{경로}` 꼴."""
    box = _rows_of(league, host_of(url))
    said = box.get("alt")
    rows = said if isinstance(said, list) else ([said] if said else [])
    out: list[str] = []
    for one in rows:
        got = str(one or "")
        if got.startswith("http"):
            out.append(got)
        elif got:
            # 🔴 표가 **경로 조각**을 적었으면 원문 주소에 붙인다(표가 그 꼴을
            #    정한다 — 코드가 꼴을 발명하지 않는다)
            out.append(url.rstrip("/") + "/" + got.lstrip("/"))
    return out


def needs_render(html: str, body: str) -> bool:
    """🔴 **자바스크립트 렌더가 필요한가** — 본문이 비고 그 안내만 있는 판."""
    return (not str(body or "").strip()) and bool(_JS.search(str(html or "")))


async def _one(net, url: str, *, rung: str) -> tuple[object, str]:
    """🔴 한 주소를 받는다(속도 제한·재시도). `(응답|None, 사유)`."""
    host = host_of(url)
    gap = MIN_INTERVAL
    said_last = _LAST.get(host)
    if said_last is not None:
        left = gap - (time.monotonic() - said_last)
        if left > 0:
            import asyncio
            await asyncio.sleep(min(left, gap))
    _LAST[host] = time.monotonic()
    last = ""
    for i in range(RETRY + 1):
        try:
            got = await net.get(url)
        except Exception as exc:                            # noqa: BLE001
            last = f"{rung}: 열기 예외 {type(exc).__name__}"
            continue
        status = int(getattr(got, "status", 0) or 0)
        if getattr(got, "ok", False):
            return got, f"{rung}: 받았다(상태 {status or 200})"
        if 400 <= status < 500:
            # 🔴 4xx 는 **다시 받지 않는다**(같은 답이 온다 · 상한 낭비)
            return None, f"{rung}: **{status}**(다시 받지 않는다)"
        last = f"{rung}: 상태 {status or '?'}" + (" · 재시도" if i < RETRY
                                                 else " · 재시도도 실패")
    return None, (last or f"{rung}: 못 받았다")


async def body_of(net, url: str, *, league: str = "",
                  extract=None) -> tuple[str, object, list[dict]]:
    """🔴🔴 **칸을 차례로 내려가며 본문을 얻는다**. `(본문, 발행시각, 칸 기록)`.

    🔴 **FT1** — 칸 기록은 **절대 비지 않는다**. 칸마다
       `{"rung","url","ok","why"}` 를 적는다(조용한 실패 금지 · #3).
    ⚠️ `extract` 는 `readtext.extract` 를 받는다(사본 금지 — 본문 뽑는 자리는
       그 함수 하나다).
    """
    from app import readtext
    said_extract = extract or readtext.extract
    rows: list[dict] = []
    html0 = ""
    want: list[tuple[str, str]] = [("원문", str(url))]
    while want:
        rung, one = want.pop(0)
        got, why = await _one(net, one, rung=rung)
        if got is None:
            rows.append({"rung": rung, "url": one, "ok": False, "why": why})
        else:
            html = str(getattr(got, "text", "") or "")
            body, when = said_extract(html, url=one)
            if rung == "원문":
                html0 = html
            if str(body or "").strip():
                rows.append({"rung": rung, "url": one, "ok": True,
                             "why": f"{why} · 본문 {len(str(body))}자"})
                return str(body), when, rows
            said_js = needs_render(html, body)
            rows.append({"rung": rung, "url": one, "ok": False,
                         "why": (f"{why} · 🔴 **본문 0자** — "
                                 + ("**자바스크립트 렌더 필요**"
                                    if said_js else "빈 본문"))})
        # ── 🔴 다음 칸을 **그때** 만든다(원문 HTML 이 있어야 AMP 를 안다)
        if rung == "원문":
            said_amp = amp_of(html0)
            if said_amp:
                want.append(("AMP", said_amp))
            else:
                rows.append({"rung": "AMP", "url": "", "ok": False,
                             "why": "⬜ **AMP 없다** — 원문에 `rel=amphtml` 이 "
                                    "없다(주소를 추측하지 않는다)"})
            said_rss = rss_of(league, url)
            if said_rss:
                want += [("RSS", x) for x in said_rss[:2]]
            else:
                rows.append({"rung": "RSS", "url": "", "ok": False,
                             "why": (f"⬜ **RSS 통로 없음** — 원천 표"
                                     f"(`{league or '리그 미상'}`)에 `rss` 가 "
                                     f"없다")})
            said_alt = alt_of(league, url)
            if said_alt:
                want += [("대체 경로", x) for x in said_alt[:2]]
            else:
                rows.append({"rung": "대체 경로", "url": "", "ok": False,
                             "why": "⬜ **대체 경로 없음** — 원천 표에 `alt` 가 "
                                    "없다"})
    return "", None, rows


def why_of(rows: list[dict]) -> str:
    """🔴 **FT1** — 칸별 사유를 한 줄로(버릴 때 이 글자를 적는다)."""
    said = list(rows or [])
    if not said:
        # 🔴 여기 오면 계약이 빨개진다(사유 0건 금지) — 그래도 말은 한다
        return "🔴 **칸 기록이 없다**(FT1 위반)"
    return " · ".join(f"{r.get('rung')} {r.get('why')}" for r in said)
