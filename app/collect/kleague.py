"""K리그 어댑터 — §19-g-1 이 요구하는 **일정 날짜 검증**의 자리.

§19-g-1 실측(2026-09-27): *"다음스포츠 K리그 일정(지난주) → 검증기 거부 → 연합
순연 기사에서 '강원-인천 1경기' 도출."*

🔴 **URL 을 지어내지 않는다**(§11-3). 다음스포츠·연합의 일정 페이지 주소를 손으로
   박으면 그것이 틀렸을 때 조용히 0건이 된다. 그래서 이 어댑터는 **검색으로 지형을
   보고**(§19-b-1) 찾은 페이지를 `verify.slate_date_ok` 에 통과시킨다.

🔴 **연도 없는 날짜 표기는 못 읽는 것으로 본다**(fail-closed · §12-c-7). 그것이
   09-27 에 지난주 4경기를 오늘 것으로 읽게 만든 함정이다(M13).

⚠️ 이 어댑터는 `games` 표에 **직접 적지 않는다** — 경기 수·상대만 사실로 낸다.
   K리그 `ext_id` 규약이 없어서, 지금 적으면 중복 행이 쌓인다. 그 규약은 단계 4
   에서 소스 지도를 확정할 때 정한다(범위 밖 — §13-1).
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone

from app import cassette, verify
from app.blackboard import Fact
from app.cells import Question, Source

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))
LEAGUE = "K리그1"
#: 🔴 이 어댑터가 맡는 종목. **상수로 밝힌다** — 행 안에만 적으면 "표에 어떤
#  종목이 있나"를 밖에서 못 읽는다(사용자 지시 2026-10-01: 다섯 종목을 쌓는다).
SPORT = "soccer"

#: 🔴 일정 페이지에서 **날짜처럼 보이는 것 전부**를 뽑는다. `verify.slate_date_ok`
#  가 그중 연도 있는 것만 읽고, 하나도 못 읽으면 **거부**한다(fail-closed).
#  ⚠️ 연도 없는 `09.27 일` 도 뽑아 넘긴다 — 뽑지 않으면 "날짜를 못 찾았다"가 되어
#     거부 사유가 뭉개진다. 두 사유를 구분해 적는 것이 §12-c-7 의 요지다.
_DATE_ANY = re.compile(
    r"(20\d\d[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}"     # 2026.09.27
    r"|\d{1,2}[.\-/월]\s*\d{1,2}\s*[일)]?)"            # 09.27 · 9월 27일
)
#: `강원-인천` · `강원 vs 인천` — 순연 기사가 경기를 이렇게 적는다(실측 09-27).
_PAIR = re.compile(r"([가-힣]{2,6})\s*(?:[-–vsVS]|대)\s*([가-힣]{2,6})")

#: §12-c-1 예외 — 순연·재편성 기사는 **원래 날짜 기사도** 허용한다.
#  🔴 단 라인업 정보는 폐기한다(`date_ok` 의 `allow_original_date` 규약).
POSTPONE_MARKS = ("순연", "연기", "취소", "재편성", "우천")


def page_dates(text: str) -> list[str]:
    """일정 페이지의 날짜 표기 전부. 🔴 **거르지 않는다** — 판단은 검증기가 한다."""
    return [m.group(1).strip() for m in _DATE_ANY.finditer(text or "")][:60]


def parse_schedule_page(got, q: Question) -> list[Fact]:
    """일정 페이지 → 경기 목록. 🔴 **날짜가 오늘이 아니면 사실 0건이다.**

    ⚠️ 실사고 M13: 다음스포츠가 JS 로 그린 **지난주** 일정을 오늘 것으로 읽었다.
       `slate_date_ok` 가 그것을 거부하고, 세포는 다음 소스로 간다(§19-b-4).
    """
    if not getattr(got, "ok", False):
        return []
    text = _strip(got.text)
    # 🔴 재현 시각은 카세트가 정한다(§19-g) — `off` 면 진짜 지금이다
    day = q.deadline.date() if q.deadline else cassette.reference_now().date()
    v = verify.slate_date_ok(page_dates(text), day)
    if not v.ok:
        # 🔴 사유를 로그에 남긴다 — "왜 대체 소스로 갔나"가 남아야 한다
        logger.info("[kleague] 일정 페이지 거부 — %s (%s)", v.reason,
                    getattr(got, "url", ""))
        return []
    pairs = _pairs(text)
    if not pairs:
        return []
    return [Fact(question_id=q.id, value=pairs, hardness="likely",
                 source=getattr(got, "url", ""), published_at=None,
                 tier=verify.TIER_PRIMARY, extracted_by="rule:PAIR", step=0)]


def parse_postponed(hits, q: Question) -> list[Fact]:
    """§19-g-1 대체 경로 — **연합 순연 기사**에서 오늘 경기를 도출한다.

    *"연합 순연 기사에서 '강원-인천 1경기' 도출"*(09-27 실측). 순연 기사는
    §12-c-1 예외로 **원래 날짜 기사도** 통과하지만, 여기서 얻는 것은 "오늘 몇
    경기가 남았나"이고 라인업이 아니다 — 그래서 그 예외가 안전하다.
    """
    out: list[Fact] = []
    for h in hits or []:
        text = f"{getattr(h, 'title', '')} {getattr(h, 'snippet', '')}"
        if not any(m in text for m in POSTPONE_MARKS):
            continue
        pairs = _pairs(text)
        if not pairs:
            continue
        out.append(Fact(
            question_id=q.id, value=pairs,
            # 🔴 스니펫 근거다 — soft(§19-b-3). 본문을 열지 않았다
            hardness="soft", source=getattr(h, "url", "") or "",
            publisher=getattr(h, "publisher", "") or "",
            published_at=getattr(h, "published_at", None),
            tier=verify.TIER_PRIMARY, extracted_by="rule:POSTPONE", step=0))
    return out


def _pairs(text: str) -> list[dict]:
    """`강원-인천` → `[{"a": "강원", "b": "인천"}]`. 🔴 중복은 한 번만.

    ⚠️ **홈-원정 순서를 여기서 정하지 않는다.** 기사 표기가 매체마다 다르고
       (`원정-홈`으로 쓰는 곳이 있다), 뒤집으면 핸디 마켓이 통째로 반대가 된다.
       그래서 `home`/`away` 가 아니라 `a`/`b` 로 남긴다 — 순서 확정은 단계 4 에서
       공식 소스와 대조해 정한다(§13-1 범위 밖).
    """
    seen: set[tuple[str, str]] = set()
    out = []
    for a, b in _PAIR.findall(text):
        if a == b or (a, b) in seen:
            continue
        seen.add((a, b))
        out.append({"a": a, "b": b})
    return out[:12]


_TAG = re.compile(r"<[^>]+>")


def _strip(html: str) -> str:
    return " ".join(_TAG.sub(" ", html or "").split())


# ══════════════════════════════════════════════════════════════════
# 세포
# ══════════════════════════════════════════════════════════════════


def sources_slate(day: date) -> list[Source]:
    """K리그 슬레이트 소스. 🔴 **검색이 일정 페이지를 찾고, 검증기가 판정한다.**

    §19-b-1(넓게 던진다) → §19-b-3(검증기) → §19-b-4(막히면 대체: 순연 기사).
    ⚠️ 앞 소스들은 페이지를 **열어** `slate_date_ok` 를 걸고(`body_only`), 마지막
       소스는 순연 기사 스니펫이다 — 이 순서가 곧 §19-g-1 의 경로다.

    🔴 다른 어댑터(`mlb`·`npb`)와 **같은 규약**이다 — `ingest._slate` 가 이 함수를
       부른다. 규약이 다르면 한쪽에 분기가 생기고, 분기는 리그가 늘 때마다 자란다.
    """
    md = f"{day.month}월 {day.day}일"
    srcs = [
        Source("검색:K리그 일정", "search", query=f"K리그 일정 {md}", lang="ko",
               tier=verify.TIER_PRIMARY, parse_body=parse_schedule_page,
               # 🔴 스니펫은 URL 고르는 데만 — 날짜는 **페이지**에 있다
               body_only=True),
        Source("검색:K리그 경기", "search", query=f"K리그 경기 {md}", lang="ko",
               tier=verify.TIER_PRIMARY, parse_body=parse_schedule_page,
               body_only=True),
        # §19-b-4 대체 — 앞이 전부 거부되면 순연 기사에서 도출한다
        Source("연합 순연 기사", "search", query=f"K리그 순연 {md}", lang="ko",
               tier=verify.TIER_PRIMARY, parse=parse_postponed, verify=True),
    ]
    return srcs
