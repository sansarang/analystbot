"""[SCT-2] 딥서치 설정 — 현지어 검색어 · 소스 등급 · 추출 스키마.

지시문 Phase 4. **세 가지만, 현지어로, 화이트리스트에서.**

🔴 위성(층1)의 `_SOCCER_TERMS = ""` 를 대체하지 않는다 — 그건 다음 뉴스검색
   채널이고 검색어를 붙이면 엉뚱한 기사가 온다(실측 2026-09-12).
⚠️ 순수 함수 모듈이다. 검색·fetch 는 기존 통로가 한다.
"""
from __future__ import annotations

import functools
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_DIR = Path("config")

#: 경기당 상한. 지시문 4-1·4-2 그대로 — **여기 한 곳에만 적는다.**
PER_TEAM_QUERIES = 1        # 팀당 1질의 → 경기당 2
PER_GAME_FETCH = 3          # 등급 순 상위 3개만 본문을 받는다

#: 등급. 낮을수록 먼저 본다. 0 은 차단, 9 는 미상(목록에 없는 도메인).
RANK_BLOCKED, RANK_UNKNOWN = 0, 9

#: 추출 스키마 — 이 칸 **외에는 버린다**(지시문 4-3).
#  `list` 는 문자열 목록, `str` 은 한 줄.
EXTRACT_SCHEMA = {
    "team": str, "out": list, "doubt": list, "predicted_xi": list,
    "last3": list, "notes": str, "source": str, "fetched_at": str,
}


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


SEARCH_TERMS: dict[str, list[str]] = dict(
    (_load("search_terms.yaml").get("terms") or {}))

SOURCES: dict[str, list[str]] = {
    k: list(_load("sources.yaml").get(k) or [])
    for k in ("tier1_official", "tier2_local", "tier3_aggregator", "blocked")
}


def queries(league: str, team: str) -> list[str]:
    """리그·팀 → 질의 목록(팀당 `PER_TEAM_QUERIES` 개)."""
    terms = SEARCH_TERMS.get(league) or []
    return [t.replace("{team}", str(team or "")).strip() for t in terms]


@functools.lru_cache(maxsize=64)
def tor_safe(league: str) -> bool:
    """이 리그 질의를 토르로 보내도 되는가.

    🔴 한국어는 거부된다(`tor_search.is_tor_safe_query` 가 원본). 그 리그는
       다음·그라운딩으로 가야 하고, 호출부가 그것을 알아야 **조용히 0건을
       받지 않는다.**
    """
    from app.collectors.tor_search import is_tor_safe_query

    qs = queries(league, "X")
    return bool(qs) and all(is_tor_safe_query(q) for q in qs)


def _domain(url: str) -> str:
    s = str(url or "").split("://", 1)[-1].split("/", 1)[0].lower()
    return s[4:] if s.startswith("www.") else s


def rank(url: str) -> int:
    """도메인 → 등급. 낮을수록 먼저 본다."""
    d = _domain(url)
    if any(d == b or d.endswith("." + b) for b in SOURCES["blocked"]):
        return RANK_BLOCKED
    for i, key in enumerate(("tier1_official", "tier2_local",
                             "tier3_aggregator"), start=1):
        if any(d == x or d.endswith("." + x) for x in SOURCES[key]):
            return i
    return RANK_UNKNOWN


def pick_sources(urls: list[str]) -> list[str]:
    """등급 순 상위 `PER_GAME_FETCH` 개. 차단·미상은 제외한다."""
    ok = [(rank(u), i, u) for i, u in enumerate(urls or [])]
    ok = [t for t in ok if RANK_BLOCKED < t[0] < RANK_UNKNOWN]
    ok.sort(key=lambda t: (t[0], t[1]))
    return [u for _, _, u in ok[:PER_GAME_FETCH]]


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

    🔴 스키마 밖(전적·감독 코멘트·팬 반응)은 버린다 — `notes` 한 줄이 전부다.
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
        if kind is list:
            out[key] = _strs(v)
        else:
            out[key] = " ".join(str(v or "").split())
    out["team"] = team
    return out
