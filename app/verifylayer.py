"""🔴🔴 **검증층** — v5 §5. 에이전트 출력을 변수로 승격하는 **관문**. [#10 #13]

> 에이전트가 돌려준 `variables[]` 는 **여섯 검사를 전부 통과해야** 변수가 된다.
> 하나라도 걸리면 그 항목은 **폐기**되고 사유가 깔때기에 남는다. 폐기는 **조용히
> 하지 않는다** — 카드 하단 `dropped:` 줄에 **개수와 사유**를 적는다.

══════════════════════════════════════════════════════════════════
🔴 왜 — **에이전트는 지어낼 수 있다**
══════════════════════════════════════════════════════════════════

실측 2026-10-04(§17-b L2): 모델이 위키 **역사 문서**에서 `Alex McLeish`(옛
스코틀랜드 감독)를 끌어와 *"로테이션 땜질"* 이라고 적었다. 🔴 인용 대조가
그것을 거부했다 — §5-1 이 그 검사를 **모든 변수**에 건다.

실측 2026-10-04: `Song was noncommittal about his **WBC** participation` 이 감독
발언 변수로 올라왔다 — 🔴 **이 경기와 무관하다**(§5-2 `off_match`).

⚠️ 검사 순서가 뜻이다 — **싼 것부터**: 출처 등급 → 인용 → 날짜 → 신원.
   🔴 본문 대조는 글자를 훑으므로 가장 비싸다.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.reasons import Reason
from app import verify

logger = logging.getLogger(__name__)

#: 🔴 §5-2 — 남녀·연령 표식. ⚠️ 하나라도 **한쪽에만** 있으면 다른 경기다.
AGE_SEX_MARKS: tuple[str, ...] = (
    "women", "women's", "ladies", "feminine", "femenil", "femenino",
    "u15", "u16", "u17", "u18", "u19", "u20", "u21", "u22", "u23",
    "u-15", "u-16", "u-17", "u-18", "u-19", "u-20", "u-21", "u-22", "u-23",
    "여자", "女子", "女足", "youth", "junior", "reserves", "b team",
)

#: 🔴 §5-3 — 기사는 **킥오프 7일 전 ~ 킥오프** 사이다.
DATE_WINDOW_DAYS = 7

#: 🔴 §5-7 — *"MinHash 유사도 **0.8 이상**을 한 묶음."*
SIM_SAME = 0.8

#: 🔴 §5-2 — *"명단 선수 **2명 이상**."*
ROSTER_MIN = 2

#: ⚠️ 그 경기와 **무관한 대회** 낱말. 🔴 본문이 그것만 말하면 `off_match`.
#   실측 2026-10-04: WBC 발언이 올라왔다.
OFF_MATCH_WORDS: tuple[str, ...] = (
    "world baseball classic", "wbc", "olympic", "올림픽", "아시안게임",
    "asian games", "친선", "friendly tournament",
)


#: 🔴🔴 **NFD 로 안 벗겨지는 글자들** — 실측 2026-10-05.
#
#  ⚠️ `teamref._plain` 은 NFD 로 분해해 결합 문자를 버린다. 🔴 그런데 **합자·
#     획이 그어진 글자**는 애초에 분해되지 않는다:
#
#       Ø ø Æ æ ß đ ł Ð þ Þ   → NFD 가 **그대로** 돌려준다(실측)
#       Å å                   → ✅ 분해된다(A + 고리)
#
#  🔴 그래서 매체가 `Odegaard`(ASCII)로 쓰고 인용이 `Ødegaard` 로 오면 **대조가
#     실패한다** — 북유럽·아이슬란드·폴란드·독일 이름이 전부 이 꼴이다.
#  ⚠️ **음차가 아니다** — `Ø`→`O` 는 그 매체들이 ASCII 로 쓸 때 실제로 쓰는
#     글자다(실측: 같은 espn 기사가 `Odegaard`·`Moller` 로 썼다).
_LIGATURES = str.maketrans({
    "Ø": "O", "ø": "o", "Æ": "AE", "æ": "ae", "Œ": "OE", "œ": "oe",
    "ß": "ss", "Đ": "D", "đ": "d", "Ð": "D", "ð": "d",
    "Ł": "L", "ł": "l", "Þ": "TH", "þ": "th", "Ħ": "H", "ħ": "h",
    "Ŀ": "L", "ŀ": "l", "İ": "I", "ı": "i",
})


def _norm(text: str) -> str:
    """🔴 §5-1 — *"공백·따옴표 정규화."* ⚠️ 한글을 분해하지 않는다(NFC).

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **넓혔다** — 지시서(오픈월드) §1-1 (2026-10-05)
    ══════════════════════════════════════════════════════════════════

    > 인용 검증(§5-1)이 **정규화 차이**(따옴표·공백·NBSP·대소문자·발음 기호)로
    > 진짜 인용을 떨어뜨리는지 … 정규화 문제면 정규화를 넓히고(NFKC·따옴표
    > 통일·공백 접기)

    ⚠️ 이미 하던 것: NFC · 따옴표 통일 · 공백 접기(`split()` 이 NBSP·전각 공백도
       나눈다) · 소문자.
    🔴 **더한 것: 발음 기호**(`Ødegaard` ↔ `Odegaard`). 매체가 북유럽·포르투갈
       이름을 **양쪽으로** 쓴다(실측: 같은 기사 안에서도 갈린다).
       ⚠️ 벗기는 자리는 `teamref._plain` **하나**다(사본 금지) — 한글·가나·한자는
          그대로 두고 라틴 발음부호만 벗긴다.
    🔴 대시·생략표도 통일한다 — `–`·`—` 와 `…` 는 매체마다 다르게 쓴다.
    """
    from app.teamref import _plain
    raw = unicodedata.normalize("NFC", str(text or ""))
    raw = re.sub(r"[“”„‟＂\"]", '"', raw)
    raw = re.sub(r"[‘’‚‛＇']", "'", raw)
    raw = re.sub(r"[–—―‒]", "-", raw)
    raw = raw.replace("…", "...")
    # 🔴 발음 기호를 벗긴다 — **라틴만**(한글·가나·한자는 `_plain` 이 지킨다)
    raw = raw.translate(_LIGATURES)
    raw = _plain(raw)
    return " ".join(raw.split()).lower()


def quote_ok(quote: str, body: str) -> tuple[bool, str]:
    """🔴🔴 **그 인용이 본문에 있나.** `(있다, 사유)` — §5-1.

    ⚠️ 이 판단이 **인라인으로** 숨어 있었다(지시서 §1-1 이 양방향 고정물을
       요구하는데 **부를 함수가 없었다**). 🔴 한 함수로 뽑는다 — 판정은 한 곳이다.

    🔴 **세 사유를 가른다**(§8-6: 거짓 사유 금지):
         인용이 없다        → `QUOTE_NOT_FOUND`(에이전트)
         본문을 못 받았다    → `BODY_MISSING`(수집/배선)  ⚠️ **다른 고칠 곳**이다
         본문에 없다        → `QUOTE_NOT_FOUND`(에이전트가 지어냈다)
    """
    q = _norm(quote)
    if not q:
        return False, "🔴 인용이 **없다**(§5-1)"
    b = _norm(body)
    if not b:
        return False, "🔴 **본문을 못 받았다** — 대조할 수 없다(fail-closed)"
    return (True, f"인용이 본문에 있다({len(q)}자)") if q.strip('"') in b else (
        False, f"🔴 인용이 **본문에 없다** — 지어낸 것이다(§5-1): `{q[:50]}`")


@dataclass
class Context:
    """🔴 검증에 필요한 **그 경기의 사실들**. 코드가 만든다."""

    home: str
    away: str
    home_names: tuple[str, ...] = ()
    away_names: tuple[str, ...] = ()
    competition: str = ""
    roster: tuple[str, ...] = ()
    kickoff: datetime | None = None
    #: 🔴 §5-1 — **fetch 로 받아 둔 본문**. ⚠️ 없으면 인용을 대조할 수 없다
    bodies: dict = field(default_factory=dict)
    #: 🔴🔴 **받아 둔 문서 저장소**(`cells.Seen`) — 지시서 §3: 날짜 조회가
    #   `doc_date(url)` 하나를 지난다. ⚠️ `None` 이면 변수에 붙은 값만 본다.
    seen: object = None


# ══════════════════════════════════════════════════════════════════
# §5-5 출처 등급 · 무게
# ══════════════════════════════════════════════════════════════════


def hardness_for(tier: str, *, conflict: bool = False,
                 reverified: bool = True, sources: int = 1) -> int:
    """🔴 §5-5 — 등급 → 무게. ⚠️ 충돌·미재검증이 **내린다**.

    > hardness = 2(official 또는 **national 2매체 일치**) / 1(national·local
    > 단일, aggregator 2매체) / 0(배경·단일 aggregator).
    > §5-7: 충돌이면 두 변수 모두 보존하되 **hardness 0**.
    > §5-8·M31: `reverified:false` → **한 단계 내린다**.
    """
    from app import domains
    base = domains.hardness_of(tier)
    # 🔴 §5-5 — `national` 2매체 일치는 **2** 다
    if tier == "national" and sources >= 2:
        base = 2
    # ⚠️ 단일 `aggregator` 는 **0**(배경)이다 — 2매체면 1
    if tier == "aggregator" and sources < 2:
        base = 0
    if conflict:
        return 0                      # 🔴 §5-7
    if not reverified:
        base = max(base - 1, 0)       # 🔴 §5-8 · M31
    return base


# ══════════════════════════════════════════════════════════════════
# §5-7 중복 — 독립 출처 세기
# ══════════════════════════════════════════════════════════════════


def _shingles(text: str, k: int = 5) -> set[str]:
    t = _norm(text)
    return {t[i:i + k] for i in range(max(len(t) - k + 1, 1))}


def similarity(a: str, b: str) -> float:
    """🔴 자카드 유사도. ⚠️ MinHash 의 추정 대상이 이것이다 — 건수가 적어서
    **정확히** 센다(해시 근사가 필요한 규모가 아니다)."""
    sa, sb = _shingles(a), _shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def independent_sources(rows: list[tuple[str, str]]) -> tuple[int, list[list[str]]]:
    """🔴 §5-7 — `(독립 출처 수, 묶음들)`. ⚠️ `rows` 는 `(url, 주장)`."""
    groups: list[list[str]] = []
    texts: list[str] = []
    for url, claim in rows:
        for i, seen in enumerate(texts):
            if similarity(claim, seen) >= SIM_SAME:
                groups[i].append(url)
                break
        else:
            groups.append([url])
            texts.append(claim)
    return len(groups), groups


# ══════════════════════════════════════════════════════════════════
# §5 — 여섯 검사
# ══════════════════════════════════════════════════════════════════


def verify_one(var, ctx: Context) -> tuple[bool, Reason, str]:
    """🔴🔴 그 변수 후보가 **변수가 되나**. `(통과, 사유 enum, 설명)`.

    ⚠️ 검사 순서는 **싼 것부터**다: 등급 → 인용 → 날짜 → 신원.
    """
    from app import domains
    url = str(getattr(var, "url", "") or "")

    # ── §4-3·§5-5 출처 등급 — 🔴 `tip` 은 변수가 못 된다
    tier = domains.tier_of(url)
    if tier in ("tip", "deny"):
        return False, Reason.TIP_SOURCE, (
            f"🔴 등급 `{tier}` — **변수 근거가 못 된다**(§4-3·§5-5): {url[:70]}")

    # ── §5-1 인용 검증
    raw_body = (ctx.bodies or {}).get(url) or ""
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **본문 부재는 다른 사유다** — 지시서 §1-1 (§8-6 거짓 사유 금지)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-04(포르투갈): **12건 전부** `quote_not_found` 였는데 그
    #     내용은 *"본문을 받아 두지 않았다"* 였다 — 인용을 **대조조차 못 했다.**
    #  🔴 한 사유로 묶어서 **고칠 곳을 가렸다**: 본문 부재는 **수집/배선**이고
    #     인용 부재는 **에이전트**다. 그 둘을 가른다.
    if not _norm(raw_body):
        return False, Reason.BODY_MISSING, (
            f"🔴 그 URL 의 **본문을 받아 두지 않았다** — 대조할 수 없다"
            f"(fail-closed · 고칠 곳은 **수집/배선**이다): {url[:70]}")
    ok_q, why_q = quote_ok(getattr(var, "quote", ""), raw_body)
    if not ok_q:
        return False, Reason.QUOTE_NOT_FOUND, why_q
    # 🔴 아래 §5-2 가 같은 본문을 쓴다 — **한 번만** 정규화한다(ruff 가 잡았다)
    body = _norm(raw_body)

    # ── §5-3 날짜
    # 🔴🔴 **저장소에서도 본다** — 지시서 2026-10-06 §3:
    #    *"검증층의 날짜 조회도 한 함수: `doc_date(url)`. 재사용이든 신규든 같은
    #    저장소에서 읽는다."*
    #  ⚠️ 변수에 붙은 값이 먼저다(모델·조립이 이미 정한 것) — 없을 때 저장소다.
    #  🔴 그래야 *"받아 두긴 했는데 변수에 안 붙은"* 경우가 `date_missing` 이
    #     되지 않는다(실측 2026-10-06: 그 때문에 20건이 죽었다).
    when = getattr(var, "published_at", None)
    if not isinstance(when, datetime):
        from app.cells import doc_date
        said = doc_date(getattr(ctx, "seen", None), url)
        if isinstance(said, datetime):
            when = said
    if not isinstance(when, datetime):
        return False, Reason.DATE_MISSING, "🔴 발행 시각이 **없다**(§5-3)"
    if when.tzinfo is None or when.tzinfo.utcoffset(when) is None:
        return False, Reason.DATE_MISSING, (
            f"🔴 **시간대 없는 발행 시각**이다(§8-7): {when!r}")
    if ctx.kickoff is not None:
        if when > ctx.kickoff:
            return False, Reason.POST_MATCH, (
                f"🔴 **킥오프 뒤** 기사다(§5-3) — 예측의 근거가 아니다")
        if when < ctx.kickoff - timedelta(days=DATE_WINDOW_DAYS):
            return False, Reason.DATE_MISSING, (
                f"🔴 킥오프 **{DATE_WINDOW_DAYS}일 전보다 오래된** 기사다(§5-3)")

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **§5-2 — 그 변수가 *이 경기 팀* 것인가**(M36 side_mismatch)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-04(게이트 3 주입 시험): `team: "team:999999"` 를 붙인
    #     변수가 **통과했다.** 🔴 검증층이 본문의 **이름**만 보고 변수가 적은
    #     **열쇠**는 안 봤다.
    #  🔴 그러면 남의 팀 변수가 이 경기 시나리오를 민다 — M36 이 막는 것이
    #     *"원정 기록을 홈 변수로"* 이고 이것은 그보다 더 넓은 구멍이다.
    #  ⚠️ 비교는 **열쇠**로 한다(이름이 아니다 · §8-1 ID 우선).
    said_team = str(getattr(var, "team", "") or "")
    if said_team and said_team not in (ctx.home, ctx.away):
        return False, Reason.SIDE_MISMATCH, (
            f"🔴 변수가 적은 팀 `{said_team}` 이 **이 경기 팀이 아니다**"
            f"(홈 `{ctx.home}` · 원정 `{ctx.away}`) — §5-2 · M36")

    # ── §5-2 신원 필터
    ours = [n for n in (ctx.home_names or ()) if _norm(n) and _norm(n) in body]
    theirs = [n for n in (ctx.away_names or ()) if _norm(n) and _norm(n) in body]
    if not (ours or theirs):
        return False, Reason.IDENTITY_MISMATCH, (
            "🔴 본문에 **두 팀 중 하나의 이름도 없다**(§5-2)")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **CJK 는 두 조건을 건다** — 사용자 결정 ⑧ (2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 한자·가나·로마자 표기를 **같은 팀 열쇠의 별칭**으로 묶어 대조하되,
    #  > **부분 문자열 일치는 2자 이상이고 명단 선수 1명 이상이 같이 나올 때만**
    #  > 인정한다. `広島`가 다른 단어 안에 섞여 통과하는 걸 막는 조건이다.
    #
    #  🔴 **여기가 그 자리다** — 명단(`ctx.roster`)이 있는 곳이다. ⚠️ 귀속을
    #     세포(`searchcells`)에서 하려 했으나 §13-2 가 막는다: *"라인업 세포가
    #     명단을 읽는다 — 그 비교는 STEP 2(단계 5)다."* 계약이 그것을 잡았다.
    #  ⚠️ **CJK 이름일 때만** 본다 — 라틴 이름은 낱말 단위 비교가 이미 그 일을
    #     한다(`mentions_team` 의 앞 두 자 규칙은 CJK 전용이다).
    side_names = [str(n) for n in (ours or theirs)]
    if side_names and any(verify._has_cjk(n) for n in side_names):
        all_names = [str(n) for n in
                     ((ctx.home_names or ()) if ours else (ctx.away_names or ()))]
        ok_cjk, why_cjk = verify.mentions_team_cjk(
            body, key=(ctx.home if ours else ctx.away),
            names=all_names, roster=list(ctx.roster or ()))
        if not ok_cjk:
            return False, Reason.IDENTITY_MISMATCH, (
                f"🔴 **CJK 귀속 조건 미달**(결정 ⑧ 2026-10-04) — {why_cjk}")
    # 🔴 남녀·연령 표식 — ⚠️ 본문에 있는데 **우리 경기에는 없으면** 다른 경기다
    marks = [m for m in AGE_SEX_MARKS if re.search(rf"\b{re.escape(m)}\b", body)]
    if marks:
        said = _norm(" ".join(list(ctx.home_names) + list(ctx.away_names)
                              + [ctx.competition]))
        if not any(m in said for m in marks):
            return False, Reason.IDENTITY_MISMATCH, (
                f"🔴 본문에 **{marks[:2]}** 표식이 있는데 우리 경기에는 없다 — "
                f"남녀·연령이 다른 경기다(§5-2)")
    hits = [p for p in (ctx.roster or ()) if _norm(p) and _norm(p) in body]
    comp = bool(_norm(ctx.competition) and _norm(ctx.competition) in body)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **`off_match` 를 먼저 본다**(§5-2 · 순서가 뜻이다)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 내 첫 판은 *"그 경기 것인지 못 가렸다"*(`identity_mismatch`)를 먼저
    #     봤다. 그러면 **다른 대회 이야기**가 그 사유로 적힌다 — §8-6 이 막는
    #     거짓 사유다(고칠 곳이 다르다: 수집 vs 검증).
    #  🔴 본문이 **다른 대회만** 말하면 그것은 `off_match` 다. 실측 2026-10-04:
    #     `Song was noncommittal about his **WBC** participation`.
    off = [w for w in OFF_MATCH_WORDS if w in body]
    if off and not comp and not theirs:
        return False, Reason.OFF_MATCH, (
            f"🔴 **다른 대회 이야기**다(§5-2): {off[:2]} — 이 경기의 대회명도 "
            f"상대명도 본문에 없다")
    # 🔴 명단 선수 2명 **또는** 대회명·상대명
    if not (len(hits) >= ROSTER_MIN or comp or theirs):
        return False, Reason.IDENTITY_MISMATCH, (
            f"🔴 그 경기 것인지 **못 가렸다**(§5-2) — 명단 선수 {len(hits)}명"
            f"(최소 {ROSTER_MIN}) · 대회명 없음 · 상대명 없음")
    return True, Reason.OK, f"등급 `{tier}` · 인용 대조 통과 · 신원 확인"


def verify_all(vars_: list, ctx: Context, *, funnel=None) -> list:
    """🔴 §5 — 통과한 것만 돌려준다. ⚠️ **폐기는 조용히 하지 않는다.**

    🔴 사유는 §8-6 enum 으로 깔때기에 **개수**로 쌓인다(§8-5).
    """
    out = []
    for v in (vars_ or []):
        ok, reason, why = verify_one(v, ctx)
        if ok:
            out.append(v)
            continue
        logger.info("[verify] 폐기 %s — %s", getattr(v, "id", "?"), why)
        if funnel is not None:
            funnel.drop(reason, "verified_vars")
    if funnel is not None:
        funnel.set("agent_vars", len(vars_ or []))
        funnel.set("verified_vars", len(out))
    return out
