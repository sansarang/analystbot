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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_DIR = Path("config")

#: 예산(지시문 4-5). **여기 한 곳에만 적는다.**
PER_GAME_SEARCH = 3      # 경기당 검색 총 상한
PER_GAME_FETCH = 5       # 경기당 fetch 총 상한
FETCH_PER_STAGE = 3      # 한 단계에서 여는 상위 개수

#: 신선도 상한(시간). 지시문 4-3 ③.
MAX_AGE_H = {"pre": 48, "lineup": 3}

#: 등급. 낮을수록 먼저 본다. 9 는 미상(목록에 없는 도메인).
RANK_UNKNOWN = 9
#: 🔴 [SCT-9 2026-09-14 사용자 지시] **미상을 버리지 않는다 — tier 4 로 통과**
#   시킨다. 실측 2026-09-14: 오늘 프리뷰를 낸 이탈리아 매체 28건 중 24건이
#   목록에 없어 폐기됐다(eurosport·ilmessaggero·romatoday…). 상위 3건은 tier
#   순이라 등록 매체가 있으면 미상은 자연히 밀린다.
#   ⚠️ `blocked`·`js_only` 는 그대로 버린다 — 그쪽은 "모르는 곳"이 아니라
#      "열면 안 되는 곳"이다.
RANK_UNLISTED = 4

#: 추출 스키마(지시문 4-4). 이 칸 **외에는 버린다**.
#: 🔴 [HYC-1 2026-09-20] `fetched_at` 을 **뺐다.** 채우는 코드가 0건이었고
#   (LLM 에게 기사에서 뽑으라고 맡겼다), 기사 본문에 "우리가 언제 수집했는지"가
#   있을 리 없다 — 실측 운영 상자 42쪽 중 **42쪽이 빈 칸**이었다.
#   수집 시각의 원본은 상자 최상위 `gathered_at` 이다(위성이 코드로 쓴다).
#   ⚠️ `source` 는 남겨 둔다 — LLM 응답을 받되 **검사에 쓰지 않고**
#      `llm_source` 로 개명해 보관한다(지어낸 출처 비율을 재는 자료).
#      다음 커밋(HYC-1b)에서 `article_idx` 로 대체한다.
EXTRACT_SCHEMA = {
    "team": str, "out": list, "doubt": list, "xi_status": str, "xi": list,
    "bench_notable": list, "last3": list, "midweek": str, "notes": str,
    "source": str, "published": str,
}

#: 추출이 **아는** XI 상태값. 확정 여부와 다르다 — 아래를 보라.
_XI_STATUS = ("predicted", "official")

#: 🔴 [HYC-2 2026-09-23 사용자 지시 "hyc 전부 다 해라"] **확정으로 인정하는
#   값.** 계획서 `hyp_conditions_0920` §1-b 그대로다.
#
#   왜 필요한가 (계획서 실측): 유일하게 confirmed 로 센 `xi_confirmed` 가
#   믿을 수 없는 카드였다 — `conflict: true`(무고사·하창래가 결장 목록과 XI
#   에 동시 존재) · `source: ""` · **`xi_status: "lastStarting11"`**
#   (오늘 확정 XI 가 아니라 **지난 경기 선발**).
#
# 🔴 `predicted`·`lastStarting11`·`standard`·`None` 은 **전부 미상**이다.
#    CLAUDE.md 발송 규율 "예상을 확정으로 취급 금지"와 같은 규약.
# ⚠️ 여기가 원본이다 — 노드에 문자열을 적지 마라(사본 금지).
XI_CONFIRMED = ("official",)


def xi_is_confirmed(status) -> bool:
    """이 XI 를 **확정**으로 볼 수 있나. 모르면 False(낮은 쪽)."""
    return str(status or "") in XI_CONFIRMED
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


#: [SCT-8] 대진 질의가 이만큼 나오면 팀 질의는 생략한다(사용자 지시).
PAIR_HITS_ENOUGH = 10


def queries(league: str, team: str | None = None, stage: str = "pre", *,
            home: str | None = None, away: str | None = None) -> list[str]:
    """리그·단계 → 질의 목록. **채울 수 없는 자리표시자가 있으면 그 줄은 뺀다.**

    🔴 [SCT-8 2026-09-14 사용자 지시] 검색어가 두 벌이다:
       · 대진 질의 `{home} {away} …` — 오늘 경기 기사를 잡는다
       · 팀 질의  `{team} … 오늘` — 결장 뉴스를 잡는다
       실측(2026-09-14)이 이유다. `"{team} probabili formazioni infortunati"` 는
       구글이 **과거 전체**에서 매칭해 80건 중 48시간 안이 0건이었다
       (434h·3386h·5881h…). 같은 통로에 두 팀 이름을 넣으면 1.6~5.1h 가
       열 건 넘게 나온다.
    ⚠️ 빈 자리를 빈 문자열로 채우지 않는다 — 그러면 `" probabili formazioni"`
       같은 반쪽 질의가 나가고, 그게 다시 과거 전체를 긁는다.
    """
    out: list[str] = []
    for t in ((SEARCH_TERMS.get(league) or {}).get(stage) or []):
        q = str(t)
        need = {"{team}": team, "{home}": home, "{away}": away}
        if any(k in q and not v for k, v in need.items()):
            continue
        for k, v in need.items():
            if v:
                q = q.replace(k, str(v))
        q = q.strip()
        if q:
            out.append(q)
    return out


#: [ALI-1] 현지 표기 별칭. 🔴 한국어 별칭표(`SOCCER_ALIAS`)와 **용도가 다르다** —
#  저쪽은 한국어 매체 검색·카드 표시, 이쪽은 현지어 검색 질의다.
_ALIAS_DOC = _load("aliases_local.yaml")
LOCAL_ALIASES: dict[str, dict] = dict(_ALIAS_DOC.get("aliases") or {})


def local_name(league: str, team: str) -> str:
    """검색 질의에 쓸 **현지 표기**. 표에 없으면 원래 이름 그대로.

    🔴 실측 2026-09-14: `"Como 1907 infortunati oggi"` 는 0건, `"Como …"` 는
       기사가 나온다. 법인격(FC·AC·US)과 창단연도는 이름이 아니라 형식이다.
    ⚠️ 값은 목록이다 — **첫 번째**를 쓴다. 나머지는 사람이 고를 여지다.
    """
    vals = (LOCAL_ALIASES.get(league) or {}).get(team) or []
    return str(vals[0]) if vals else str(team or "")


LOCALES: dict[str, dict] = dict(_TERMS_DOC.get("locales") or {})


def locale(league: str) -> dict | None:
    """[SCT-7] 리그 → Google News RSS 로케일. 없으면 None(=RSS 안 쓴다).

    🔴 `ceid` 는 표에 적지 않는다 — `{gl}:{hl 앞 2자}` 규칙으로 만든다.
       두 곳에 적으면 한쪽만 고쳐진다.
    """
    loc = LOCALES.get(league) or {}
    hl, gl = str(loc.get("hl") or ""), str(loc.get("gl") or "")
    if not hl or not gl:
        return None
    return {"hl": hl, "gl": gl, "ceid": f"{gl}:{hl[:2]}"}


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


#: 🔴 [PA-21 2026-09-16] 같은 본문이 이 수 이상 반복되면 기사가 아니라
#   **사이트 안내문**이다. 2 로 둔다 — 서로 다른 두 기사가 글자까지 같은
#   본문을 갖는 일은 없다(요약 기사도 제목·수치가 다르다).
BOILER_MIN_REPEAT = 2

#: 비교에 쓰는 앞부분 길이. 본문 전체를 비교하면 광고 꼬리 하나로 갈린다.
BOILER_HEAD = 200


def drop_boilerplate(articles: list | None) -> list:
    """반복되는 사이트 안내문을 버린다. 🔴 **길이 검사가 못 잡는 것**이다.

    실측 2026-09-16 g8360: 캐시 기사 17건 중 15건이 v.daum.net 의 같은
    안내문 1,200자였다(§7 의 "본문 < 500자" 검사를 통과한다). LLM 이 뽑을
    사실이 없어 `out 0` 이 됐고, 그것이 S6 확인 0건의 원인이었다.

    ⚠️ **반대 위험**: 정상 기사를 죽이면 자료가 줄어든다. 그래서 (a) 앞
       200자만 비교하고 (b) **2건 이상 겹칠 때만** 버린다. 한 번만 나온
       본문은 아무리 짧아도 건드리지 않는다.
    """
    arts = list(articles or [])
    if len(arts) < BOILER_MIN_REPEAT:
        return arts
    seen: dict[str, int] = {}
    for a in arts:
        head = " ".join((a.get("body") or "").split())[:BOILER_HEAD]
        if head:
            seen[head] = seen.get(head, 0) + 1
    dup = {h for h, n in seen.items() if n >= BOILER_MIN_REPEAT}
    if not dup:
        return arts
    out = [a for a in arts
           if " ".join((a.get("body") or "").split())[:BOILER_HEAD] not in dup]
    logger.info("[scout] 반복 본문 폐기 %d건 (서로 다른 안내문 %d종) — 남은 %d건",
                len(arts) - len(out), len(dup), len(out))
    return out


#: 🔴 [U6 2026-09-15] tier0 — 구단 공식·담당 기자. tier1 보다 **앞선다**.
#   0 이 가장 좋은 등급이고 숫자가 클수록 나쁘다 — 기존 순서(1·2·3·4·9)를
#   그대로 잇는다. 계약이 0 < 1 < 2 < 3 < RANK_UNLISTED < RANK_UNKNOWN 을 본다.
RANK_PRIMARY = 0


def rank(url: str, league: str) -> int:
    """도메인 → 등급(0·1·2·3). 목록에 없으면 `RANK_UNKNOWN`."""
    d = _domain(url)
    if _in(d, (SOURCES.get("tier0_primary") or {}).get(league) or []):
        return RANK_PRIMARY
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
    #: 🔴 [SCT-6] 날짜를 **모르는** 결과. 버리지 않고 tier 를 한 단계 내려
    #  통과시킨 뒤, 본문을 열고 다시 본다(`body_date_ok`).
    #  "모른다"와 "오래됐다"는 다른 말이다.
    undated: bool = False


def _tokens(team: str) -> list[str]:
    """팀명에서 두 글자 이상인 조각만. 🔴 한 글자는 아무 데나 걸린다."""
    return [t for t in re.split(r"[^\w가-힣]+", str(team or "")) if len(t) >= 2]


def screen(hit: dict, *, team: str, kickoff, stage: str, now=None) -> Screen:
    """fetch 전 선별(지시문 4-3). 버리는 이유를 **이름으로** 남긴다."""
    # 🔴 [SCT-9] 차단·js_only 는 **매체 도메인**으로 본다. 구글 RSS 의 `link` 는
    #    news.google.com 이라 그것으로 보면 베팅 사이트도 통과한다
    #    (실측 2026-09-14: 미상을 tier 4 로 통과시키자 tipico.de 가 열렸다).
    url = hit.get("source_url") or hit.get("url") or ""
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
    #
    # 🔴 [SCT-6 2026-09-14 사용자 지시] **소스별로 가른다.**
    #    RSS 는 `pubDate` 를 싣는다 — 날짜를 알므로 종전 규칙 그대로다.
    #    DDG/토르는 스니펫에 날짜가 거의 없다. 그 경우를 폐기로 처리했더니
    #    **정상 기사까지 통째로 버려졌다**(실측 2026-09-14: 세리에A 3경기
    #    보강 6건 → 0건, 폐기 사유의 최다가 '날짜'). 이제 모르면 버리지 않고
    #    `undated` 로 통과시켜 tier 를 한 단계 내리고, 본문을 연 뒤 다시 본다.
    ok_date = any(w in low for w in TODAY_WORDS)
    if not ok_date and kickoff is not None:
        for delta in (-1, 0, 1):
            d = (kickoff + timedelta(days=delta)).strftime("%Y-%m-%d")
            if d in text or d.replace("-", "/") in text:
                ok_date = True
                break
    years = {m.group(0) for m in _YEAR.finditer(text)}
    this = str((kickoff or now or datetime.now(timezone.utc)).year)
    if not ok_date and years:
        # 연도가 **명시**돼 있는데 올해가 아니면 지난 시즌 글이다 — 버린다.
        ok_date = this in years
        if not ok_date:
            return Screen(False, "날짜")
    pub = hit.get("published")
    if isinstance(pub, datetime):
        # ③ 신선도 — pubDate 를 아는 소스(RSS)에만 건다.
        cur = now or datetime.now(timezone.utc)
        if (cur - pub) > timedelta(hours=MAX_AGE_H.get(stage, 48)):
            return Screen(False, "신선도")
        # 🔴 [SCT-7] **pubDate 가 곧 날짜 증거다.** 발행 시각을 정확히 알면서
        #    제목에 "오늘"이 없다고 버리는 것은 같은 사실을 두 번 재는 것이고,
        #    그 둘째 검사는 증거값이 없다(실측 2026-09-14: 1시간 전 발행된
        #    "Torino, formazioni ufficiali" 가 날짜 문에서 폐기됐다).
        #    날짜 문은 pubDate 가 **없을 때** 그 자리를 대신하려고 있던 것이다.
        #    ⚠️ 지난 연도가 제목에 **명시**된 글은 위에서 이미 걸러졌다.
        return Screen(True, "")
    # pubDate 가 없는 소스(DDG/토르) — 날짜 토큰이 있으면 통과, 없으면 undated.
    return Screen(True, "") if ok_date else Screen(True, "", True)


#: 본문 날짜 후보. `article:published_time` 이 1순위, 없으면 본문 첫 ISO 날짜.
_META_PUB = re.compile(
    r"""article:published_time["']?\s*(?:content=)?["']([0-9]{4}-[0-9]{2}-[0-9]{2})""",
    re.I)
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

#: 본문 날짜가 경기일에서 이만큼 벗어나면 지난 경기 글이다(지시문 후속 지시).
BODY_DATE_TOLERANCE_D = 2


def body_date_ok(body: str, *, kickoff, now=None) -> tuple[bool, str]:
    """[SCT-6] 날짜를 모르고 연 기사를 **본문으로** 다시 본다.

    🔴 **증거가 있을 때만 버린다.** 본문에도 날짜가 없으면 통과다 —
       "모른다"를 "오래됐다"로 바꾸지 않는다(그 혼동이 보강을 0건으로 만들었다).
    반환 `(통과, 사유)`.
    """
    text = str(body or "")
    if not text:
        return True, ""
    m = _META_PUB.search(text) or _ISO_DATE.search(text)
    if m:
        try:
            g = m.groups()
            d = (date.fromisoformat(g[0]) if len(g) == 1
                 else date(int(g[0]), int(g[1]), int(g[2])))
        except (TypeError, ValueError):
            d = None
        if d is not None and kickoff is not None:
            kd = kickoff.date() if hasattr(kickoff, "date") else kickoff
            gap = abs((d - kd).days)
            if gap > BODY_DATE_TOLERANCE_D:
                return False, f"본문 날짜 {d} — 경기일에서 {gap}일"
            return True, ""
    years = {mm.group(0) for mm in _YEAR.finditer(text)}
    this = str((kickoff or now or datetime.now(timezone.utc)).year)
    if years and this not in years:
        return False, f"본문에 지난 연도만 있다 {sorted(years)[:3]}"
    return True, ""


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
    kept, discard, unlisted = [], {}, []
    for i, h in enumerate(hits or []):
        if team is not None:
            sc = screen(h, team=team, kickoff=kickoff, stage=stage, now=now)
            if not sc.keep:
                discard[sc.reason] = discard.get(sc.reason, 0) + 1
                continue
            if sc.undated:
                # 🔴 호출부가 본문을 열고 다시 봐야 한다는 표시.
                h["undated"] = True
        elif blocked(h.get("source_url") or h.get("url") or "") \
                or js_only(h.get("source_url") or h.get("url") or ""):
            discard["차단"] = discard.get("차단", 0) + 1
            continue
        # 🔴 [SCT-7] 등급은 **매체 도메인**으로 본다. 구글 RSS 의 `link` 는
        #    news.google.com 리다이렉트라 그것으로 보면 전건이 '미상'이 된다
        #    (news_rss 가 같은 이유로 `<source url>` 을 따로 읽는다).
        r = rank(h.get("source_url") or h.get("url") or "", league)
        if r >= RANK_UNKNOWN:
            # 🔴 [SCT-9] 미상은 **버리지 않고** tier 4 로 내려 후보에 남긴다.
            #    나중에 tier 승격 후보로 보고하려고 표시를 남긴다.
            r = RANK_UNLISTED
            h["unlisted"] = True
            unlisted.append(_domain(h.get("source_url") or h.get("url") or ""))
        # 🔴 [SCT-6] 날짜를 모르는 결과는 **한 단계 내린다** — 버리지는 않는다.
        #    본문을 열고 다시 보는 것은 호출부(`body_date_ok`)의 몫이다.
        kept.append((0 if (stage == "lineup" and _confirmed(h.get("title"))) else 1,
                     r + (1 if h.get("undated") else 0), i, h))
    kept.sort(key=lambda t: (t[0], t[1], t[2]))
    out = [h for _, _, _, h in kept[:FETCH_PER_STAGE]]
    if discard:
        logger.info("[scout] %s %s — 폐기 %s", league, stage, discard)
    if unlisted:
        # 🔴 [SCT-9] 목록에 없는 도메인을 **매일 남긴다** — tier 승격 후보다.
        picked_unlisted = [_domain(h.get("source_url") or h.get("url") or "")
                           for h in out if h.get("unlisted")]
        logger.info("[scout] %s %s — 미상 %d건(후보 %s) · 그중 fetch %s",
                    league, stage, len(unlisted), sorted(set(unlisted))[:8],
                    picked_unlisted or "없음")
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
