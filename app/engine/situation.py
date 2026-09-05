"""[상황 변수 2026-09-06] 팀의 공기 — 기사 제목에서 상황 축을 뽑는다.

🔴 **LLM 을 부르지 않는다.** 키워드 매칭이다 — 캡도 비용도 없고, 같은 입력에
   같은 답을 낸다. 상황 축은 "은퇴식이 있었나"처럼 **사실 확인**이지 해석이
   아니므로 모델이 필요 없다.

🔴 **종목 분기를 코드에 두지 않는다.** `registry.situation_axes(sport)` 만
   부른다. 새 종목은 registry 한 줄로 붙는다 — 여기는 손대지 않는다.

⚠️ **요약문을 만들지 않는다.** 제목·URL·출처만 남긴다. 요약하는 순간 그
   요약이 판정 재료가 된다(자료2 가 겪은 실패와 같은 모양).

⚠️ 출처가 공식·언론이 아니면 `[미확인]` 이고, 프롬프트 규칙이 그 항목의
   %p 를 0 으로 고정한다. 라벨만 붙이고 **버리지는 않는다** — 사용자는
   보되 확률은 오염되지 않는 것이 이 층의 설계다.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

#: 자료2 에 병기하는 라벨. 판정 프롬프트가 이 문자열로 규칙을 건다.
LABEL = "[상황]"
UNVERIFIED = "[미확인]"


#: 집계자 도메인 — 이건 **출처가 아니다.** Google News 링크는 리다이렉트라
#  그대로 쓰면 모든 기사가 `[미확인]` 이 된다(실측 2026-09-06).
_AGGREGATORS = ("news.google.com", "news.yahoo.co.jp", "news.naver.com")


def domain_of(url: str) -> str:
    """URL → 도메인. 못 읽으면 빈 문자열 — 빈 값은 `[미확인]` 으로 흐른다."""
    try:
        host = urlparse(url or "").netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def source_of(item: dict) -> str:
    """이 기사의 **실제 출처**. 집계자 링크에 속지 않는다.

    우선순위: `<source url>` 속성 → 기사 링크(집계자가 아니면) → 매체 이름.
    """
    su = domain_of(str((item or {}).get("source_url") or ""))
    if su and su not in _AGGREGATORS:
        return su
    d = domain_of(str((item or {}).get("url") or item.get("link") or ""))
    if d and d not in _AGGREGATORS:
        return d
    return str((item or {}).get("source") or "").strip()


def _norm(s: str) -> str:
    """대소문자·공백만 정규화. 원문을 바꾸지 않는다."""
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def match_types(text: str, axes: dict[str, tuple[str, ...]]) -> list[str]:
    """이 문장이 걸리는 상황 유형들. 없으면 빈 목록."""
    t = _norm(text)
    if not t:
        return []
    hit = []
    for kind, words in (axes or {}).items():
        if any(_norm(w) in t for w in words):
            hit.append(kind)
    return hit


def is_recap(title: str, sport: str) -> bool:
    """경기 **결과**를 말하는 기사인가.

    🔴 [2026-09-06 사용자 지시] **경기 후 기사는 의미가 없다.**
       "김성현 은퇴식이 있던 날, SSG 1점차 승리" 는 어제 끝난 경기의 상보다.
       그 은퇴식은 **어제 일**이지 오늘 일이 아니다 — 오늘 경기에 붙이면
       지나간 사건을 오늘의 공기로 오인한다.
    ⚠️ 예고·공지·논란(아직 일어나지 않았거나 계속되는 것)은 걸리면 안 된다.
    """
    import re as _re

    from app.registry import SCORE_PATTERN, recap_markers

    t = _norm(title)
    if not t:
        return False
    if _re.search(SCORE_PATTERN, t):          # 점수 표기 = 가장 강한 표지
        return True
    return any(_norm(w) in t for w in recap_markers(sport))


def published_before(item: dict, starts_at) -> bool:
    """이 기사가 **경기 시작 전**에 나왔는가. 시각을 모르면 통과시킨다.

    ⚠️ 모르는 것을 버리지 않는다 — RSS 가 pubDate 를 안 주는 매체가 있고,
       그걸 버리면 그 매체의 기사가 통째로 사라진다.
    """
    from datetime import datetime, timezone
    from email.utils import parsedate_to_datetime

    if starts_at is None:
        return True
    raw = (item or {}).get("published")
    if not raw:
        return True
    try:
        dt = parsedate_to_datetime(str(raw))
    except (TypeError, ValueError):
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    st = starts_at
    if isinstance(st, str):
        try:
            st = datetime.fromisoformat(st.replace("Z", "+00:00"))
        except ValueError:
            return True
    if getattr(st, "tzinfo", None) is None:
        st = st.replace(tzinfo=timezone.utc)
    return dt < st


def classify(items: list[dict], sport: str, *, starts_at=None) -> list[dict]:
    """기사 목록 → 상황 태그. 종목을 모르면 빈 목록(수집은 멈추지 않는다).

    `starts_at` 이 오면 **그 시각 이전 기사만** 본다.

    반환 항목: `{유형, 라벨, 제목, url, 출처, 확인}`
      · `확인`: "공식" | "미확인" — `registry.is_trusted_source` 가 판단한다.
    """
    from app.registry import is_trusted_source, situation_axes

    axes = situation_axes(sport)
    if not axes:
        return []
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    n_recap = n_late = 0
    for it in items or []:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or "")
        if is_recap(title, sport):
            n_recap += 1
            continue
        if not published_before(it, starts_at):
            n_late += 1
            continue
        url = str(it.get("url") or it.get("link") or "")
        dom = source_of(it)
        for kind in match_types(title, axes):
            # 같은 유형·같은 제목은 한 번만 — 같은 기사가 두 신호가 되면 안 된다.
            key = (kind, title[:60])
            if key in seen:
                continue
            seen.add(key)
            # ⚠️ **해결된 출처**로 판단한다. `url` 은 집계자 리다이렉트라
            #    그것을 보면 전건이 `[미확인]` 이 된다(실측 2026-09-06).
            trusted = is_trusted_source(dom) if dom else is_trusted_source(url)
            out.append({
                "유형": kind,
                "라벨": LABEL if trusted else f"{LABEL}{UNVERIFIED}",
                "제목": title[:160],
                "url": url,
                "출처": dom,
                "확인": "공식" if trusted else "미확인",
            })
    if n_recap or n_late:
        logger.info("[situation] %s 경기후 기사 %d건 · 시작 이후 %d건 제외",
                    sport, n_recap, n_late)
    return out


def by_side(research: dict, sport: str, *, starts_at=None) -> dict[str, list[dict]]:
    """`{side}_news` 를 읽어 진영별 상황 태그. 없으면 빈 dict."""
    out: dict[str, list[dict]] = {}
    for side in ("home", "away"):
        rows = (research or {}).get(f"{side}_news") or []
        tags = classify(rows, sport, starts_at=starts_at)
        if tags:
            out[side] = tags
    return out


def as_lines(tags: list[dict]) -> list[str]:
    """자료2 에 실을 한 줄 표기. 판정이 출처 신뢰도를 볼 수 있어야 한다."""
    lines = []
    for t in tags or []:
        src = t.get("출처") or "출처불명"
        lines.append(f"{t.get('라벨')} {t.get('유형')} — {t.get('제목')} ({src})")
    return lines


def attach(jg: dict) -> int:
    """경기에 상황 태그를 새긴다. 반환은 붙인 태그 수.

    ⚠️ **조용히 실패하지 않는다.** 종목을 모르거나 기사가 없으면 0 을
       돌려주고 로그를 한 줄 남긴다 — "안 붙었다"와 "볼 게 없었다"를
       구분할 수 있어야 한다.
    """
    sport = (jg.get("sport") or "").lower()
    research = jg.get("research") or {}
    tags = by_side(research, sport,
                   starts_at=jg.get("starts_at") or jg.get("starts_at_utc"))
    jg["situation_tags"] = tags
    n = sum(len(v) for v in tags.values())
    logger.info("[situation] %s game=%s 태그 %d건 (home=%d away=%d)",
                sport, jg.get("game_id"), n,
                len(tags.get("home") or []), len(tags.get("away") or []))
    return n
