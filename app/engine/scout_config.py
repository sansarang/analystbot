"""[SCT-3] 위성 검색 개편 — 현지어 2단계 · 선별 · 확장 스키마 (Part 2).

오늘 페이블이 실제로 정보를 가져온 방식을 이식한다:
**리그별 현지어 검색어 → 제목·날짜·신선도로 걸러 → 구단·지역 매체 우선 →
결장·XI·직전 3경기만 추출.**

🔴 층1 위성(다음 뉴스검색)의 `_SOCCER_TERMS = ""` 를 대체하지 않는다 —
   거기 검색어를 붙이면 맥도날드·프로야구 기사가 온다(실측 2026-09-12).
⚠️ 순수 함수 모듈이다. 검색·fetch 는 기존 통로가 한다.
"""
from __future__ import annotations

import functools
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_DIR = Path("config")

#: 예산(지시문 4-5). **여기 한 곳에만 적는다.**
PER_GAME_SEARCH = 3      # 경기당 검색 총 상한
PER_GAME_FETCH = 5       # 경기당 fetch 총 상한
FETCH_PER_STAGE = 3      # 한 단계에서 여는 상위 개수

#: 신선도 상한(시간). 지시문 4-3 ③.
MAX_AGE_H = {"pre": 48, "lineup": 3}

#: 등급. 낮을수록 먼저 본다. 9 는 미상(목록에 없는 도메인) — fetch 하지 않는다.
RANK_UNKNOWN = 9

#: 추출 스키마(지시문 4-4). 이 칸 **외에는 버린다**.
EXTRACT_SCHEMA = {
    "team": str, "out": list, "doubt": list, "xi_status": str, "xi": list,
    "bench_notable": list, "last3": list, "midweek": str, "notes": str,
    "source": str, "published": str, "fetched_at": str,
}

_XI_STATUS = ("predicted", "official")
_YEAR = re.compile(r"(19|20)\d{2}")


def _load(name: str) -> dict:
    import yaml

    p = CONFIG_DIR / name
    if not p.exists():
        logger.warning("[scout] 설정 없음: %s", p)
        return {}
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("[scout] 설정 읽기 실패 %s: %s", p, exc)
        return {}


_TERMS_DOC = _load("search_terms.yaml")
_SRC_DOC = _load("sources.yaml")

SEARCH_TERMS: dict[str, dict] = dict(_TERMS_DOC.get("terms") or {})
CONFIRM_WORDS: list[str] = [str(x).lower()
                            for x in (_TERMS_DOC.get("confirm_keywords") or [])]
TODAY_WORDS: list[str] = [str(x).lower()
                          for x in (_TERMS_DOC.get("today_words") or [])]

SOURCES: dict = {k: _SRC_DOC.get(k) or ({} if k.startswith("tier") else [])
                 for k in ("tier1_club_local", "tier2_aggregator", "tier3_wire",
                           "blocked", "blocked_fragments", "js_only")}


def queries(league: str, team: str, stage: str = "pre") -> list[str]:
    """리그·팀·단계 → 질의 목록."""
    terms = (SEARCH_TERMS.get(league) or {}).get(stage) or []
    return [t.replace("{team}", str(team or "")).strip() for t in terms]


@functools.lru_cache(maxsize=64)
def tor_safe(league: str) -> bool:
    """토르로 보내도 되는가. 🔴 한국어는 거부된다(`is_tor_safe_query` 가 원본)."""
    from app.collectors.tor_search import is_tor_safe_query

    qs = queries(league, "X", "pre") + queries(league, "X", "lineup")
    return bool(qs) and all(is_tor_safe_query(q) for q in qs)


def _domain(url: str) -> str:
    s = str(url or "").split("://", 1)[-1].split("/", 1)[0].lower()
    return s[4:] if s.startswith("www.") else s


def _in(domain: str, names) -> bool:
    return any(domain == n or domain.endswith("." + n) for n in (names or []))


def blocked(url: str) -> bool:
    """차단 도메인 또는 **조각**(bet·odds·tipster)."""
    d = _domain(url)
    if _in(d, SOURCES["blocked"]):
        return True
    return any(f in d for f in (SOURCES["blocked_fragments"] or []))


def js_only(url: str) -> bool:
    """열어도 표가 없다 — fetch 금지. 기존 피드로만 본다."""
    return _in(_domain(url), SOURCES["js_only"])


def rank(url: str, league: str) -> int:
    """도메인 → 등급(1·2·3). 목록에 없으면 `RANK_UNKNOWN`."""
    d = _domain(url)
    for i, key in enumerate(("tier1_club_local", "tier2_aggregator"), start=1):
        if _in(d, (SOURCES[key] or {}).get(league) or []):
            return i
    if _in(d, (SOURCES["tier3_wire"] or {}).get("common") or []):
        return 3
    return RANK_UNKNOWN


@dataclass(frozen=True)
class Screen:
    keep: bool
    reason: str


def _tokens(team: str) -> list[str]:
    """팀명에서 두 글자 이상인 조각만. 🔴 한 글자는 아무 데나 걸린다."""
    return [t for t in re.split(r"[^\w가-힣]+", str(team or "")) if len(t) >= 2]


def screen(hit: dict, *, team: str, kickoff, stage: str, now=None) -> Screen:
    """fetch 전 선별(지시문 4-3). 버리는 이유를 **이름으로** 남긴다."""
    url = hit.get("url") or ""
    if blocked(url):
        return Screen(False, "차단")
    if js_only(url):
        return Screen(False, "js_only")
    text = f"{hit.get('title') or ''} {hit.get('snippet') or ''}"
    low = text.lower()
    toks = _tokens(team)
    if toks and not any(t.lower() in low for t in toks):
        return Screen(False, "제목")
    # ② 날짜 문 — 경기 날짜(±1일) · "오늘" 말 · 다른 연도가 아닐 것
    ok_date = any(w in low for w in TODAY_WORDS)
    if not ok_date and kickoff is not None:
        for delta in (-1, 0, 1):
            d = (kickoff + timedelta(days=delta)).strftime("%Y-%m-%d")
            if d in text or d.replace("-", "/") in text:
                ok_date = True
                break
    if not ok_date:
        years = {m.group(0) for m in _YEAR.finditer(text)}
        this = str((kickoff or now or datetime.now(timezone.utc)).year)
        ok_date = bool(years) and this in years
    if not ok_date:
        return Screen(False, "날짜")
    # ③ 신선도 — ⚠️ 모르는 것과 오래된 것은 다르다. 모르면 버리지 않는다.
    pub = hit.get("published")
    if isinstance(pub, datetime):
        cur = now or datetime.now(timezone.utc)
        if (cur - pub) > timedelta(hours=MAX_AGE_H.get(stage, 48)):
            return Screen(False, "신선도")
    return Screen(True, "")


def _confirmed(title: str) -> bool:
    low = str(title or "").lower()
    return any(w in low for w in CONFIRM_WORDS)


def rank_and_pick(hits: list[dict], *, league: str, stage: str,
                  team: str | None = None, kickoff=None, now=None,
                  with_discard: bool = False):
    """선별 → 등급 정렬 → 상위 `FETCH_PER_STAGE` 개.

    🔴 `lineup` 단계에서 제목에 확정 키워드가 있으면 **tier 무관 최우선**
       (지시문 4-3 ④). `pre` 에서는 먹지 않는다 — 예상 기사에 "공식"이
       붙어 있을 리 없고, 붙어 있다면 지난 경기 것이다.
    """
    kept, discard = [], {}
    for i, h in enumerate(hits or []):
        if team is not None:
            s = screen(h, team=team, kickoff=kickoff, stage=stage, now=now)
            if not s.keep:
                discard[s.reason] = discard.get(s.reason, 0) + 1
                continue
        elif blocked(h.get("url") or "") or js_only(h.get("url") or ""):
            discard["차단"] = discard.get("차단", 0) + 1
            continue
        r = rank(h.get("url") or "", league)
        if r >= RANK_UNKNOWN:
            discard["미상"] = discard.get("미상", 0) + 1
            continue
        boost = 0 if (stage == "lineup" and _confirmed(h.get("title"))) else 1
        kept.append((boost, r, i, h))
    kept.sort(key=lambda t: (t[0], t[1], t[2]))
    out = [h for _, _, _, h in kept[:FETCH_PER_STAGE]]
    if discard:
        logger.info("[scout] %s %s — 폐기 %s", league, stage, discard)
    return (out, discard) if with_discard else out


def _strs(v) -> list[str]:
    out = []
    for x in (v if isinstance(v, (list, tuple)) else []):
        if x is None:
            continue
        s = str(x).strip()
        if s:
            out.append(s)
    return out


def validate(raw: dict) -> dict | None:
    """추출 결과 → 스키마 안의 것만. 팀이 없으면 **None**.

    🔴 전적·감독 코멘트·팬 반응·베팅 팁은 버린다 — `notes` 한 줄이 전부다.
    ⚠️ 빈 목록은 **사실이다**(결장 없음). 결손과 구분해서 읽어야 한다.
    """
    if not isinstance(raw, dict):
        return None
    team = str((raw or {}).get("team") or "").strip()
    if not team:
        logger.info("[scout] 팀이 없는 추출 — 버린다")
        return None
    out: dict = {}
    for key, kind in EXTRACT_SCHEMA.items():
        v = raw.get(key)
        out[key] = _strs(v) if kind is list else " ".join(str(v or "").split())
    out["team"] = team
    st = out.get("xi_status")
    out["xi_status"] = st if st in _XI_STATUS else None
    return out


def bench_notable(*, predicted, official, regulars) -> list[str]:
    """예상 XI 에 있고 공식 XI 에서 빠진 **주전**.

    🔴 코드가 채운다 — LLM 자기보고가 아니다(지시문 4-4). T-60 diff 의 핵심이다.
    """
    off = {str(x).strip() for x in (official or [])}
    reg = {str(x).strip() for x in (regulars or set())}
    return [str(p).strip() for p in (predicted or [])
            if str(p).strip() in reg and str(p).strip() not in off]


def merge(items: list[dict], *, league: str) -> dict | None:
    """여러 소스의 추출을 합친다. 충돌하면 **tier 높은 쪽** + `conflict=true`.

    지시문 4-6. ⚠️ 평균 내지 않는다 — 결장 명단은 평균이 없는 값이다.
    """
    rows = [r for r in (items or []) if r]
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: rank(str(r.get("source") or ""), league))
    best = dict(rows[0])
    conflict = any(
        _strs(r.get(k)) != _strs(best.get(k))
        for r in rows[1:] for k in ("out", "xi"))
    best["conflict"] = bool(conflict)
    return best
