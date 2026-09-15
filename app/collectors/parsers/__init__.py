"""[U6 2026-09-15] 결장표 **전용 파서**. 파서가 채우면 그 경기 LLM 콜은 0이다.

🔴 **파서가 실패하면 없는 것으로 치지 않는다.** `None` 을 돌려주고 호출부가
   종전대로 LLM 추출로 되돌아간다. 파서는 보조 경로이지 관문이 아니다.
🔴 도메인별이다 — `for_domain(url)` 이 고른다. 목록을 호출부에 베껴 적지 않는다.
⚠️ 각 파서는 **HTML 문자열만** 받는다. HTTP·DB 를 부르지 않는다(순수 함수).
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _text(html: str) -> str:
    return _WS.sub(" ", _TAG.sub(" ", html or "")).strip()


def _uniq(names) -> list[str]:
    out, seen = [], set()
    for n in names:
        n = _WS.sub(" ", str(n or "")).strip(" ,·-–")
        if n and len(n) > 2 and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out


# ── fantacalcio.it (세리에A) — 결장표가 `indisponibili` 블록에 있다
_FC = re.compile(
    r"(?:indisponibil\w*|squalificat\w*|infortunat\w*)(.{0,1200}?)(?:</(?:ul|div|table)>)",
    re.I | re.S)
_FC_NAME = re.compile(r'title="([^"]{3,40})"|>([A-ZÀ-Ý][\w\'’.\- ]{2,30})<')


def parse_fantacalcio(html: str) -> dict | None:
    m = _FC.search(html or "")
    if not m:
        return None
    names = [a or b for a, b in _FC_NAME.findall(m.group(1))]
    out = _uniq(names)
    return {"out": out, "source_parser": "fantacalcio"} if out else None


# ── ligainsider.de (분데스리가)
_LI = re.compile(r"(?:Ausf[äa]lle|verletzt|gesperrt)(.{0,1200}?)(?:</(?:ul|div|table)>)",
                 re.I | re.S)
_LI_NAME = re.compile(r'>([A-ZÄÖÜ][\wäöüß\'’.\- ]{2,30})<')


def parse_ligainsider(html: str) -> dict | None:
    m = _LI.search(html or "")
    if not m:
        return None
    out = _uniq(_LI_NAME.findall(m.group(1)))
    return {"out": out, "source_parser": "ligainsider"} if out else None


# ── sportsmole.co.uk (EPL·라리가) — "Team News" 문단
_SM = re.compile(r"(?:Team News|injur\w+|doubtful)(.{0,1500}?)(?:</p>|</div>)",
                 re.I | re.S)
_SM_NAME = re.compile(r"\b([A-Z][a-z]{2,15} [A-Z][a-zA-Z\'’\-]{2,20})\b")


def parse_sportsmole(html: str) -> dict | None:
    m = _SM.search(html or "")
    if not m:
        return None
    out = _uniq(_SM_NAME.findall(_text(m.group(1))))
    return {"out": out, "source_parser": "sportsmole"} if out else None


#: 도메인 → 파서. 🔴 **여기가 원본**이다. 호출부는 `for_domain` 만 쓴다.
PARSERS = {
    "fantacalcio.it": parse_fantacalcio,
    "ligainsider.de": parse_ligainsider,
    "sportsmole.co.uk": parse_sportsmole,
}


def for_domain(url: str):
    """그 도메인의 파서. 없으면 None."""
    u = str(url or "").lower()
    for dom, fn in PARSERS.items():
        if dom in u:
            return fn
    return None


def try_parse(url: str, html: str) -> dict | None:
    """파서가 있으면 돌린다. **실패는 None** — 호출부가 LLM 으로 되돌아간다."""
    fn = for_domain(url)
    if fn is None:
        return None
    try:
        got = fn(html)
    except Exception as exc:
        logger.warning("[parser] %s 실패 — LLM 으로 되돌아간다: %s",
                       str(url)[:60], exc)
        return None
    if got:
        logger.info("[parser] %s → out %d명 (LLM 콜 0)",
                    got.get("source_parser"), len(got.get("out") or []))
    return got
