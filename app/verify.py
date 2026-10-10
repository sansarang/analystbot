"""§12-c 검증기 7종 — **검색기보다 먼저 존재한다.**

v3 §16-b 단계 1: *"검색기보다 먼저 존재, 각 검증기에 통과·거부 픽스처 한 쌍"*.
이것이 없으면 뒤의 모든 단계가 오염된다 — 지난주 일정을 오늘 것으로 읽고,
경기 후 기사로 경기 전 판정을 하고, 같은 보도자료 8건을 8개 근거로 센다.

🔴 **날짜를 못 읽는 자료는 통과가 아니라 거부다(fail-closed).**
   실사고 D25: 9/11 중지 공지를 오늘 것으로 오독했다. "모르면 통과"는 그
   재발 경로다. 일정·라인업 용도로는 쓰지 못하고 soft 로만 남긴다.

순수 함수다 — HTTP·DB·LLM 호출이 0건이다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

# ══════════════════════════════════════════════════════════════════
# 판정 결과
# ══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Verdict:
    """검증 한 건의 결과.

    `unknown=True` 는 "못 읽었다"다 — `ok=False` 와 함께 오면 **fail-closed**
    거부이고, 그것은 "틀렸다"와 구분해서 적어야 한다(§7-5e: 검색 0건은
    unknown 이지 refuted 가 아니다).
    """

    ok: bool
    reason: str
    unknown: bool = False
    hardness: str = "hard"      # 통과했을 때 이 자료의 등급


PASS = Verdict(True, "")


# ══════════════════════════════════════════════════════════════════
# ① 날짜 검증 — published_at 이 오늘 또는 어제인가
# ══════════════════════════════════════════════════════════════════

#: 한국·일본 포털이 쓰는 꼴. `2026.09.27. 오후 3:12` · `2026年9月27日 15:12`
_KO_DATE = re.compile(
    r"(20\d\d)[.\-/年]\s*(\d{1,2})[.\-/月]\s*(\d{1,2})\.?\s*日?"
    r"(?:\s*(오전|오후|AM|PM)?\s*(\d{1,2}):(\d{2}))?"
)
#: RFC 1123 에서 요일이 빠진 변형. `20 Sep 2026 09:00:00 +0900`
_RFC_NO_DOW = re.compile(
    r"(\d{1,2})\s+([A-Z][a-z]{2})\s+(20\d\d)\s+(\d{2}):(\d{2})(?::(\d{2}))?"
    r"\s*([+-]\d{4}|Z|GMT|UTC)?"
)
_MONTHS = {m: i for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}


#: RFC822 요일 약어. 🔴 `pubDate` 를 ISO 보다 **먼저** 알아보는 데만 쓴다.
_RFC822_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def parse_when(value, *, assume_tz: timezone | None = None) -> datetime | None:
    """문자열·datetime → tz 있는 datetime. 못 읽으면 `None`.

    🔴 `assume_tz` 를 반드시 넘겨라. naive 한국어 타임스탬프를 UTC 로 읽으면
       오늘 오후 기사가 **미래 발행**으로 보인다(실사고 2026-09-27).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(
            tzinfo=assume_tz or timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day,
                        tzinfo=assume_tz or timezone.utc)

    s = str(value).strip()
    if not s:
        return None

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **RSS 의 RFC822 꼴**(사용자 기술 지시 2026-10-03 · Bing 뉴스 RSS)
    # ══════════════════════════════════════════════════════════════════
    #
    #  `Fri, 02 Oct 2026 09:12:00 Z` — RSS 의 `pubDate` 가 이 꼴이다.
    #  🔴 ISO 로 못 읽혀 **발행 시각이 통째로 `None`** 이 됐다(실측 2026-10-03).
    #     그러면 §12-c-1 fail-closed 가 그 기사를 전부 떨어뜨린다 — 발행 시각이
    #     **오는데도** 못 쓰는 자리였다.
    #  ⚠️ 날짜 파싱은 **이 함수가 원본이다** — 호출부마다 따로 쓰면 갈린다.
    if "," in s[:5] or s[:3].lower() in _RFC822_DAYS:
        try:
            from email.utils import parsedate_to_datetime
            got = parsedate_to_datetime(s)
            if got is not None:
                return got if got.tzinfo else got.replace(
                    tzinfo=assume_tz or timezone.utc)
        except (TypeError, ValueError):
            pass

    # ISO 먼저 — 가장 흔하고 가장 믿을 수 있다
    iso = s.replace("Z", "+00:00")
    try:
        got = datetime.fromisoformat(iso)
        return got if got.tzinfo else got.replace(
            tzinfo=assume_tz or timezone.utc)
    except ValueError:
        pass

    if (m := _KO_DATE.search(s)):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh = int(m.group(5) or 0)
        mi = int(m.group(6) or 0)
        ampm = m.group(4)
        if ampm in ("오후", "PM") and hh < 12:
            hh += 12
        if ampm in ("오전", "AM") and hh == 12:
            hh = 0
        try:
            return datetime(y, mo, d, hh, mi,
                            tzinfo=assume_tz or timezone.utc)
        except ValueError:
            return None

    if (m := _RFC_NO_DOW.search(s)):
        mon = _MONTHS.get(m.group(2))
        if not mon:
            return None
        off = m.group(7)
        if off in (None, "GMT", "UTC", "Z"):
            tz = assume_tz or timezone.utc if off is None else timezone.utc
        else:
            sign = 1 if off[0] == "+" else -1
            tz = timezone(sign * timedelta(hours=int(off[1:3]),
                                           minutes=int(off[3:5])))
        try:
            return datetime(int(m.group(3)), mon, int(m.group(1)),
                            int(m.group(4)), int(m.group(5)),
                            int(m.group(6) or 0), tzinfo=tz)
        except ValueError:
            return None

    return None


def date_ok(published, now: datetime, *, allow_original_date: bool = False
            ) -> Verdict:
    """① 기사 발행이 오늘 또는 어제인가.

    🔴 **fail-closed** — 못 읽으면 거부다. 사용자 결정 2026-09-27:
       *"날짜를 못 읽는 자료는 통과가 아니라 거부(fail-closed). 일정·라인업
       용도로는 쓰지 못하고 soft 로만 남긴다."*

    `allow_original_date` 는 §12-c-1 의 예외다 — 순연·재편성 경기는 원래 날짜
    기사도 허용한다. **단 라인업 정보는 폐기한다**(호출부가 그것을 지킨다).
    """
    when = parse_when(published, assume_tz=now.tzinfo)
    if when is None:
        return Verdict(False, "발행 시각을 못 읽었다 — 일정·라인업 용도 불가",
                       unknown=True, hardness="soft")
    age = now - when
    if age < timedelta(hours=-2):
        return Verdict(False, f"발행이 미래다 ({when.isoformat()})")
    if age <= timedelta(days=2):
        return PASS
    if allow_original_date:
        return Verdict(True, "순연 경기 원래 날짜 기사 — 라인업 정보는 폐기",
                       hardness="soft")
    return Verdict(False, f"{age.days}일 지난 기사다")


# ══════════════════════════════════════════════════════════════════
# ② 경기 후 기사 배제
# ══════════════════════════════════════════════════════════════════

#: 🔴 원본은 여기 하나다. 읽는 쪽이 정규식을 다시 짜면 그것이 사본이다.
POST_GAME_MARKS = (
    "試合終了", "試合結果", "完투", "완봉", "끝내기",
    "승리", "패배", "역전승", "영봉승", "무승부로",
    "final score", "final:", "recap", "beat the", "defeated",
    "擊敗", "獲勝", "落敗", "終了",
)
#: 스코어 꼴. `3-5` · `3:5` · `3 - 5` — 라인업 번호와 섞이지 않게 공백 규약을 둔다
_SCORE = re.compile(r"(?<!\d)([0-9]{1,2})\s*[-:]\s*([0-9]{1,2})(?!\d)")


def not_post_game(title: str, body: str = "") -> Verdict:
    """② 경기 후 기사는 **사전 분석에 쓰지 않는다.** 채점에만 쓴다."""
    text = f"{title}\n{body}"
    low = text.lower()
    for mark in POST_GAME_MARKS:
        if mark.lower() in low:
            return Verdict(False, f"경기 후 기사다 (`{mark}`)")
    if _SCORE.search(title or ""):
        return Verdict(False, "제목에 스코어가 있다")
    return PASS


# ══════════════════════════════════════════════════════════════════
# ③ 시점 사실 — as_of 30분이면 stale (D26)
# ══════════════════════════════════════════════════════════════════

AS_OF_TTL = timedelta(minutes=30)


def as_of_fresh(as_of, now: datetime, ttl: timedelta = AS_OF_TTL) -> Verdict:
    """③ "오전 11:50 개장" 처럼 시점이 있는 사실은 30분 지나면 stale.

    ⚠️ as_of 가 **없는** 사실은 이 검증의 대상이 아니다 — 통과시킨다.
       (모든 사실에 시점이 있는 것은 아니다. 없는 것을 거부하면 순위·전적처럼
        하루 단위 사실까지 전부 떨어진다.)
    """
    if as_of in (None, ""):
        return PASS
    when = parse_when(as_of, assume_tz=now.tzinfo)
    if when is None:
        return Verdict(False, "as_of 를 못 읽었다", unknown=True,
                       hardness="soft")
    if now - when > ttl:
        return Verdict(False, f"stale — {int((now - when).total_seconds() // 60)}분 지났다")
    return PASS


# ══════════════════════════════════════════════════════════════════
# ④ 중복 제거 — 같은 보도자료 8건은 원문 1건이다
# ══════════════════════════════════════════════════════════════════

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w가-힣ぁ-ゟ゠-ヿ一-鿿]+")


def _shingles(text: str, n: int = 5) -> set[str]:
    words = _PUNCT.sub(" ", _WS.sub(" ", text or "")).split()
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def dedupe(articles: list[dict], threshold: float = 0.5
           ) -> tuple[list[dict], list[dict]]:
    """④ `(원문, 중복)` 로 가른다. `n_sources` 는 **서로 다른 원문 수**다.

    같은 발행사의 같은 URL 은 당연히 중복이고, 다른 매체라도 본문이 절반 이상
    겹치면 같은 보도자료다.
    """
    kept: list[dict] = []
    dups: list[dict] = []
    seen_urls: set[str] = set()
    fingerprints: list[set[str]] = []
    for art in articles:
        url = (art.get("url") or "").split("?")[0]
        if url and url in seen_urls:
            dups.append(art)
            continue
        sh = _shingles(art.get("body") or art.get("title") or "")
        hit = False
        for prev in fingerprints:
            if not sh or not prev:
                continue
            overlap = len(sh & prev) / min(len(sh), len(prev))
            if overlap >= threshold:
                hit = True
                break
        if hit:
            dups.append(art)
            continue
        if url:
            seen_urls.add(url)
        fingerprints.append(sh)
        kept.append(art)
    return kept, dups


# ══════════════════════════════════════════════════════════════════
# ⑤ 공식 우선 — 어느 층의 자료인가
# ══════════════════════════════════════════════════════════════════

#: 🔴 §12-c-5 의 4층. 숫자가 작을수록 세다.
TIER_OFFICIAL = 1     # 리그 공시·구단 공지·공식 라인업
TIER_PRIMARY = 2      # 현지 1차 매체 (닛칸·스포니치·NOWnews·연합)
TIER_PREVIEW = 3      # 프리뷰 사이트 — 선발·라인업 확인용만
TIER_FORECAST = 4     # 예측 사이트 — 🔴 판정 입력 금지

_TIER_HARDNESS = {TIER_OFFICIAL: "hard", TIER_PRIMARY: "likely",
                  TIER_PREVIEW: "soft", TIER_FORECAST: "soft"}


def admissible(tier: int, *, purpose: str = "judgement") -> Verdict:
    """⑤ 이 자료를 그 용도로 써도 되나.

    `purpose`: `judgement`(판정 입력) · `lineup`(선발·라인업 확인) · `context`.
    🔴 예측 사이트(4층)는 **판정 입력 금지**. 프리뷰(3층)는 라인업 확인만.
    """
    if tier >= TIER_FORECAST and purpose == "judgement":
        return Verdict(False, "예측 사이트는 판정 입력에 쓰지 않는다")
    if tier >= TIER_PREVIEW and purpose == "judgement":
        return Verdict(False, "프리뷰 사이트는 선발·라인업 확인용만")
    return Verdict(True, "", hardness=_TIER_HARDNESS.get(tier, "soft"))


def wins(a_tier: int, b_tier: int) -> int:
    """두 출처가 같은 것을 다르게 말할 때 누가 이기나. 낮은 층이 이긴다."""
    return a_tier if a_tier <= b_tier else b_tier


# ══════════════════════════════════════════════════════════════════
# ⑥ 인용 검증 — 따옴표 안 문장이 본문에 실재해야 hard
# ══════════════════════════════════════════════════════════════════

_QUOTE_TRIM = re.compile(r'^[\s"“”\'‘’「」『』]+|[\s"“”\'‘’「」『』]+$')


#: CJK 글자 범위 — 한자·히라가나·가타카나·한글. 🔴 약칭 규칙을 가르는 기준이다.
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")


def _has_cjk(s: str) -> bool:
    return bool(_CJK.search(s or ""))




def mentions_team(text: str, formal: str, local: str | None = None) -> bool:
    """이 글이 **그 팀을 말하나.** 정식명·현지 약칭 **둘 다** 본다.

    🔴 **한 곳이 원본이다.** `searchcells` 의 파서와 `cells` 의 열기 게이트가 같은
       판정을 써야 한다 — 둘이 갈리면 파서가 버린 것을 열기가 열고, 예산만 탄다.

    ⚠️ 실측: `福岡ソフトバンクホークス` 의 앞 두 자는 `福岡` 이고, 타순이 든 스니펫은
       그것을 안 썼다 — 약칭 `ソフトバンク` 를 봐야 맞는다. 그래서 정식명 앞 두 자도
       본다(정식명이 4자 이상일 때만 — 짧은 이름의 앞 두 자는 아무 데나 걸린다).

    🔴 영문 팀명은 **낱말로** 쪼개 본다. `Sacramento Republic` 이 통째로 안 나와도
       `sacramento-republic-fc-vs-las-vegas-lights-fc` 같은 **주소**에는 들어 있다 —
       실측 2026-10-01: 그 경기의 라인업 페이지가 정확히 그 꼴이었다.
    """
    formal = (formal or "").strip()
    if not formal:
        return False
    low = (text or "").lower()
    if formal in text or formal.lower() in low:
        return True
    if local and local.strip() and local.strip() in text:
        return True
    # 🔴 **앞 두 자 규칙은 CJK 전용이다.** 한자·가나는 두 자가 약칭을 이루지만
    #    (`埼玉西武ライオンズ` → `西武`), 라틴 문자 두 자는 아무 데나 걸린다.
    #    ⚠️ 실측 2026-10-01: `Las Vegas Lights` 의 앞 두 자 `La` 가
    #       `"Las Vegas weather forecast"` 에 걸려 **호텔·날씨 페이지가 통과했다.**
    if _has_cjk(formal) and len(formal) >= 4 and formal[:2] in text:
        return True
    # 🔴 라틴 문자 팀명은 **낱말 단위로** — 주소의 하이픈·슬래시를 넘기 위해
    words = [w.lower() for w in re.split(r"[^A-Za-z]+", formal) if len(w) >= 4]
    if not words:
        return False
    if all(w in low for w in words):
        return True
    # 🔴 **구단 공식 도메인은 약칭이다.** `sacrepublicfc.com` 에 `sacramento` 가
    #    통째로 없다 — 그러나 `sacr` 과 `republic` 이 있다. 가장 좋은 소스를
    #    약칭 때문에 버리면 안 된다(실측 2026-10-01: 그 도메인이 떨어졌다).
    #  ⚠️ 그래서 **낱말 둘 이상**을 요구한다. 하나면 도시 이름 하나로 호텔·공연
    #     페이지가 통과한다(`lasvegashotels` 가 `vegas` 로 걸린다).
    flat = re.sub(r"[^a-z]", "", low)
    hits = sum(1 for w in words if w in flat or w[:4] in flat)
    return hits >= min(2, len(words))


def quote_grounded(quote: str, body: str) -> Verdict:
    """⑥ 감독 발언은 본문에 그 문장이 있을 때만 `quote` 로 저장한다.

    🔴 LLM 추출기는 그럴듯한 인용을 **만들어낸다.** 본문 대조가 유일한 방어다.
    ⚠️ 공백·따옴표 표기는 매체마다 다르므로 정규화 후 비교한다.
    """
    q = _QUOTE_TRIM.sub("", quote or "")
    if not q:
        return Verdict(False, "인용이 비어 있다", hardness="soft")
    if not body:
        return Verdict(False, "본문이 없어 대조할 수 없다", unknown=True,
                       hardness="soft")
    norm = lambda s: _WS.sub("", _QUOTE_TRIM.sub("", s))   # noqa: E731
    if norm(q) in norm(body):
        return Verdict(True, "", hardness="hard")
    return Verdict(False, "본문에 없는 인용이다 — soft 로만", hardness="soft")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **한 글자 오타로 진짜 발견을 버리고 있었다** (실측 2026-10-02)
# ══════════════════════════════════════════════════════════════════
#
# 라이브에서 qwen3:8b 가 `ASK:emotion` 에 이렇게 답했다:
#
#     ロッテ・唐川侑己投手引退セレモニーを10月3日のソフトバン戦（ZOZOマリン…
#                                              ↑ `ソフトバンク` 의 `ク` 가 빠졌다
#
# 🔴 **그 사실은 진짜였다** — 사람이 손으로 쓴 분석의 변수 R7(다음 날 唐川 은퇴
#    등판 → 10/3 은 사실상 불펜 데이)이 바로 이것이다. 그런데 한 글자가 어긋나
#    `quote_grounded` 가 거부했고, 발견이 통째로 사라졌다.
#
# ⚠️ **검증을 느슨하게 하지 않는다.** 그 방향은 환각을 통과시킨다.
# 🔴 대신 **본문의 실제 구간으로 되돌린다**: 모델 인용과 본문이 공유하는 가장 긴
#    연속 조각을 찾아 **그 조각을 근거로 쓴다.** 저장되는 글자는 늘 본문에 실재하므로
#    §17-g-2 는 그대로 지켜지고, 모델의 오타는 버려진다.
# ⚠️ 층은 **한 칸 내린다**(`likely`) — 모델이 문장을 정확히 옮기지 못한 것은 사실이다.

#: 🔴 되돌릴 조각의 **최소 길이.** 이것이 진짜 방어선이다 — 일본어·한국어에서 스무
#   글자가 우연히 겹치는 일은 없다(겹쳤다면 본문에서 베낀 것이다).
#   ⚠️ 숫자는 실제 테스트로 고친다(사용자 지시 2026-10-02). 20 으로 시작한다.
REPAIR_MIN_CHARS = 20
#: 🔴 모델 인용의 **몇 할이 본문과 맞아야** 하나. 짧은 진짜 조각에 긴 환각을 얹는
#   것을 막는다. ⚠️ 위 실측이 30/68 ≈ 0.44 였다 — 0.4 로 시작한다.
REPAIR_MIN_RATIO = 0.4




#: 문장이 끝나는 글자. 🔴 일본어·한국어·영어를 함께 본다(매체마다 다르다).
_STOP = "。．.!！?？\n\r"


def _sentence_bounds(body: str, start: int, end: int) -> tuple[int, int]:
    """`body[start:end]` 를 품은 **한 문장**의 경계. 🔴 본문 안에서만 늘린다."""
    lo = start
    while lo > 0 and body[lo - 1] not in _STOP:
        lo -= 1
    hi = end + 1
    while hi < len(body) and body[hi] not in _STOP:
        hi += 1
    # 🔴 끝 구두점은 **포함한다** — 문장으로 읽히게
    if hi < len(body) and body[hi] in "。．.!！?？":
        hi += 1
    return lo, hi


# ══════════════════════════════════════════════════════════════════
# ⑦ 실측 예 — 슬레이트 날짜 대조
# ══════════════════════════════════════════════════════════════════


def slate_date_ok(page_dates: list, slate: date, *,
                  now: datetime | None = None) -> Verdict:
    """⑦ 일정 페이지가 **정말 오늘 것인가.**

    실측 2026-09-27: 다음스포츠 K리그 일정 페이지가 **지난주 4경기**를 오늘
    것으로 내놓았다(JS 렌더링 + 연도 없는 날짜 표기). 그 페이지는 여기서
    떨어져야 하고, 대체 소스(연합뉴스 순연 기사)로 간다.

    🔴 연도 없는 표기(`09.27 일`)는 **못 읽는 것으로 본다** — fail-closed.
    """
    from app import window as _w
    now = now or _w.now_utc().astimezone(KST)
    if not page_dates:
        return Verdict(False, "페이지에서 날짜를 못 찾았다", unknown=True,
                       hardness="soft")
    seen: list[date] = []
    for raw in page_dates:
        when = parse_when(raw, assume_tz=now.tzinfo)
        if when is None:
            continue
        seen.append(when.astimezone(now.tzinfo).date())
    if not seen:
        return Verdict(False, "연도 없는 날짜 표기 — 슬레이트 확정에 쓸 수 없다",
                       unknown=True, hardness="soft")
    if slate not in seen:
        return Verdict(False, f"페이지 날짜 {sorted(set(seen))} 에 슬레이트 "
                              f"{slate} 가 없다")
    return PASS


# ══════════════════════════════════════════════════════════════════
# 묶음 — 자료 하나를 7종에 통과시킨다
# ══════════════════════════════════════════════════════════════════


@dataclass
class Checked:
    """검증을 통과한 자료. `hardness` 는 **가장 약한 층**을 따른다."""

    ok: bool
    hardness: str
    reasons: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)


_ORDER = {"hard": 0, "likely": 1, "soft": 2}


def check_article(art: dict, now: datetime, *, purpose: str = "judgement",
                  allow_original_date: bool = False) -> Checked:
    """기사 한 건을 ①②③⑤⑥ 에 통과시킨다.

    ④(중복)는 목록 단위라 `dedupe` 로 따로, ⑦(슬레이트)은 일정 페이지 전용이다.
    🔴 **하나라도 거부면 거부다.** 통과하면 가장 약한 등급으로 내려간다.
    """
    checks = [
        ("date", date_ok(art.get("published_at"), now,
                         allow_original_date=allow_original_date)),
        ("post_game", not_post_game(art.get("title") or "",
                                    art.get("body") or "")),
        ("as_of", as_of_fresh(art.get("as_of"), now)),
        ("tier", admissible(int(art.get("tier") or TIER_PRIMARY),
                            purpose=purpose)),
    ]
    if art.get("quote"):
        checks.append(("quote", quote_grounded(art["quote"],
                                               art.get("body") or "")))

    out = Checked(ok=True, hardness="hard")
    for name, v in checks:
        if not v.ok:
            out.ok = False
            out.reasons.append(f"{name}: {v.reason}")
            if v.unknown:
                out.unknowns.append(name)
        if _ORDER[v.hardness] > _ORDER[out.hardness]:
            out.hardness = v.hardness
    return out


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 남녀·연령 표식 — **이름이 정체성이다** (라이브 2026-10-02)
# ══════════════════════════════════════════════════════════════════
#
# 실측: 아시안게임 **여자** 한국 vs 중국을 물었더니 검색이 **남자** 대표팀
# (손흥민·김민재) 경기 페이지를 열었고, 날짜도 같고 팀 이름도 `South Korea`·`China`
# 로 **글자까지 같아서** 어떤 가드도 막지 못했다.
#
# 🔴 **0건보다 나쁘다.** 0건은 "자료 부족"으로 멈추지만 틀린 자료는 카드를 만든다 —
#    §17-g-3 · M14 가 막으려는 사고가 바로 이것이다.
# 🔴 소스는 표식으로 가른다: fotmob 은 여자팀에 ` W`, 연령별에 `U21` 꼴을 붙인다.
#    **표식이 다르면 다른 팀이다.**

#: 🔴 표식 — 원본은 **소스의 표기 관행**이다. 추측으로 늘리지 않는다.
SQUAD_MARKS = ("w", "women", "여자", "u23", "u22", "u21", "u20", "u19", "u17")


def squad_marks(name: str) -> frozenset[str]:
    """이름이 든 **남녀·연령 표식**. 🔴 없으면 빈 집합(= 성인 남자/구단팀)."""
    one = f" {str(name or '').strip().lower()} ".replace("-", " ")
    got = {m for m in SQUAD_MARKS if f" {m} " in one}
    # ⚠️ `U21`·`U-21` 은 붙어 올 수도 있다
    import re as _re
    got |= {m.group(0).lower()
            for m in _re.finditer(r"[uU]-?\d{2}", str(name or ""))}
    return frozenset(m.replace("-", "").lower() for m in got)


def same_squad_kind(a: str, b: str) -> bool:
    """두 이름이 **같은 종류의 팀**인가(남녀·연령).

    🔴 `South Korea` ↔ `South Korea W` 는 **다르다**. 이름이 비슷하다고 같은 팀이
       아니다 — 그 혼동이 남자 대표팀 자료를 여자 경기에 붙였다.
    ⚠️ 둘 다 표식이 없으면 같다고 본다(성인 남자/구단팀이 기본 표기다).
    """
    return squad_marks(a) == squad_marks(b)
