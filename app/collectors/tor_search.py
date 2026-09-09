"""[SAT-7] 토르 경유 검색 — 직접 소스가 놓친 것을 DDG 로 보강. **기본 꺼짐.**

🔴 **순수 보강이다.** 세 리그 모두 직접 경로로 재료를 얻는다(MLB statsapi/
   transactions · NPB 야후재팬 · KBO 다음). 토르는 AWS IP(AS16509 Amazon)로 막힌
   검색 애그리게이터를 출구노드로 되살려 **추가** 기사를 발굴할 뿐이다.

🔴 **실측 2026-09-09 (컨테이너에 임시 토르 설치→측정→제거):**
     토르 출구로  DuckDuckGo 200 · Bing 200   ← 되살아난다
     그러나       Google 429 · Cloudflare(Statiz·FanGraphs) 불가
     그리고       한국 사이트(다음·네이버)는 출구노드를 의심해 **오히려 깨진다**
   → 그래서 한국어 질의는 토르로 보내지 않는다(`is_tor_safe_query`).

⚠️ 실패는 전부 조용한 폴백이다 — 토르가 없거나 못 뜨거나 검색이 실패하면
   빈 리스트/False 를 돌려주고, 직접 경로 결과만 남는다(회귀 없음).
"""
from __future__ import annotations

import asyncio
import html as _html
import logging
import os
import re
import shutil
import subprocess

logger = logging.getLogger(__name__)

SOCKS = "socks5h://127.0.0.1:9050"
_TOR_DATADIR = "/tmp/satellite-tor"
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_tor_proc: subprocess.Popen | None = None
_tor_ready = False

#: 한국어 음절 블록. 하나라도 있으면 토르로 보내지 않는다.
_HANGUL = re.compile(r"[\uac00-\ud7a3]")
#: 🔴 [SAT-11 실측 2026-09-09] DDG lite 는 class 를 **홑따옴표**로 쓰고 href 가
#   class 보다 **앞**에 온다. 종전 패턴(겹따옴표·class 선행)은 200 OK 에 결과가
#   10건 있어도 0건으로 읽었다 — 토르가 살아 있는데 보강이 통째로 죽어 있었다.
#   속성 순서는 고정으로 보지 않는다 — `result-link` 앵커를 먼저 잡고 href 를
#   따로 뽑는다. DDG 가 순서를 또 바꿔도 안 깨진다.
_DDG_LINK = re.compile(
    r'<a[^>]*result-link[^>]*>.*?</a>', re.S)
_HREF = re.compile(r'href=["\'](https?://[^"\']+)["\']')


def is_tor_safe_query(query: str) -> bool:
    """이 질의를 토르로 보내도 되는가. **한국어는 거부**(한국 사이트가 깨진다)."""
    return not _HANGUL.search(query or "")


def _strip(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def parse_ddg_lite(html: str) -> list[dict]:
    """DDG lite HTML → [{url, title, snippet}]. duckduckgo 내부 링크(광고)는 버린다."""
    out: list[dict] = []
    for m in _DDG_LINK.finditer(html or ""):
        anchor = m.group(0)
        hm = _HREF.search(anchor)
        if hm is None:
            continue
        url = hm.group(1)
        raw = _strip(re.sub(r"^<a[^>]*>|</a>$", "", anchor))
        if "duckduckgo.com" in url or not raw:
            continue
        tail = (html or "")[m.end():m.end() + 3000]
        sm = re.search(r'class=["\']result-snippet["\'][^>]*>(.*?)</td>', tail, re.S)
        snip = _strip(sm.group(1)) if sm else ""
        out.append({"url": url, "title": _html.unescape(raw),
                    "snippet": _html.unescape(snip)[:220]})
    return out


async def ensure_tor(timeout: int = 60) -> bool:
    """토르 데몬을 (없으면) 띄우고 부팅을 기다린다. 성공 True.

    ⚠️ 바이너리가 없거나 부팅 실패면 **False** — 절대 예외를 던지지 않는다.
       한 번 뜨면 모듈 전역으로 재사용한다(15분 잡 사이 유지).
    """
    global _tor_proc, _tor_ready
    if _tor_ready and _tor_proc is not None and _tor_proc.poll() is None:
        return True
    if not shutil.which("tor"):
        logger.warning("[tor] tor 바이너리 없음 — 보강 검색 생략")
        return False
    try:
        if _tor_proc is None or _tor_proc.poll() is not None:
            os.makedirs(_TOR_DATADIR, exist_ok=True)
            _tor_proc = subprocess.Popen(
                ["tor", "--SocksPort", "9050", "--DataDirectory", _TOR_DATADIR,
                 "--Log", "notice stdout"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        logger.warning("[tor] 데몬 기동 실패 — 보강 생략: %s", exc)
        return False
    # 부팅 확인: 토르 자체 확인 API 로 폴백 없이 SOCKS 연결이 되는지 폴링
    import httpx

    deadline = timeout
    while deadline > 0:
        try:
            async with httpx.AsyncClient(proxy=SOCKS, timeout=10,
                                         headers={"User-Agent": _UA}) as c:
                r = await c.get("https://check.torproject.org/api/ip")
                if r.status_code == 200:
                    _tor_ready = True
                    logger.info("[tor] 부팅 완료 — 보강 검색 가용")
                    return True
        except Exception:
            pass
        await asyncio.sleep(3)
        deadline -= 3
    logger.warning("[tor] 부팅 대기 초과(%ds) — 보강 생략", timeout)
    return False


async def search(query: str, *, limit: int = 6, timeout: int = 60) -> list[dict]:
    """토르 경유 DDG lite 검색. [{url, title, snippet}]. 실패·미가용이면 빈 리스트.

    🔴 한국어 질의는 보내지 않는다. 토르 미가용도 빈 리스트다(직접 경로만 남는다).
    """
    if not query or not is_tor_safe_query(query):
        return []
    if not await ensure_tor(timeout=timeout):
        return []
    import httpx

    try:
        async with httpx.AsyncClient(proxy=SOCKS, timeout=30, follow_redirects=True,
                                     headers={"User-Agent": _UA}) as c:
            r = await c.post("https://lite.duckduckgo.com/lite/",
                             data={"q": query})
        if r.status_code != 200:
            logger.info("[tor] DDG %s — 보강 없음 (%s)", r.status_code, query[:40])
            return []
        return parse_ddg_lite(r.text)[:limit]
    except Exception as exc:
        logger.warning("[tor] DDG 검색 실패 %s: %s", query[:40], exc)
        return []
