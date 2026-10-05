"""§19-c 블랙보드 — **세포는 다른 세포를 직접 부르지 않는다.**

공용 사실 저장소(`evidence` 표)에 쓰고, 그것을 **구독**한다. 그래서 "사실이
사실을 낳는다": "휴스턴 선발 미정" unknown 이 **반증 세포**를 낳고, 그 세포가
RotoWire 기사로 그것을 채우면 뒤 단계가 그 사실로 다시 계산한다(09-27 실측).

⚠️ v3 는 이 자리를 *"lean 을 접는다로 만들고 …"* 로 서술했다. `lean`·확신·등급은
   **v4 §8 폐기 어휘**다 — 폐기된 개념으로 설명하면 다음 세션이 그것을 되살린다.

🔴 모순 처리 순서는 **hardness → published_at → 원문 인용 유무**, 못 정하면
   unknown. 억지로 하나로 만들지 않는다.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from app import verify as V

logger = logging.getLogger(__name__)

#: 🔴 원본은 여기 하나다. 낮을수록 세다(§12-c-5 4층과 같은 방향).
HARDNESS_RANK = {"hard": 0, "likely": 1, "soft": 2}

FOUND = "found"
UNKNOWN = "unknown"
CONTRADICTED = "contradicted"

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **독립 출처 세기** (사용자 기술 지시 2026-10-03 · 기술 6)
# ══════════════════════════════════════════════════════════════════
#
# > 같은 보도자료가 8개 매체에 복사되면 출처 **8개가 아니라 1개**다. 문장 유사도로
# > 묶은 뒤 센다. 두 출처가 서로 다르면 미상, 시간 순으로 더 새 상태가 명시돼
# > 있으면("의심" → "결장 확정") 새 쪽을 쓴다.
#
# ⚠️ 종전 중복 제거는 `(질문id, str(value)[:400])` **완전 일치**였다 — 표기만 달라도
#    별건이 되어 **같은 보도자료가 여러 출처로 세어졌다.**
# 🔴 그래서 **문장 조각(shingle) 유사도**로 묶는다. 외부 라이브러리를 들이지 않는다
#    (minhash 는 큰 집합용이고, 우리는 한 질문에 사실 몇 건이다 — 직접 센다).

#: 🔴 **같은 보도로 볼 유사도**. ⚠️ 사용자 예시 코드가 `threshold=0.8` 이다.
DUP_SIMILARITY = 0.8

#: 🔴 조각 길이(문자 n-그램). ⚠️ 한국어·일본어는 공백으로 안 갈린다 — 글자로 센다.
SHINGLE = 5

#: 🔴 **독립 출처가 몇 개면 확정인가**. ⚠️ 사용자 예시: `len(group) >= 2 or official`.
CONFIRM_AT = 2


@dataclass
class Fact:
    """한 질문에 대한 한 소스의 답. 🔴 `fetched_at` 은 코드가 찍는다(§12-e)."""

    question_id: str
    value: object
    hardness: str = "soft"
    source: str = ""
    publisher: str = ""
    published_at: datetime | None = None
    fetched_at: datetime | None = None
    quote: str | None = None
    extracted_by: str | None = None
    step: int = 0
    team: str | None = None
    player_id: int | None = None
    #: 🔴 **이 사실이 나온 기사의 제목·본문.** 검증기(§12-c)가 검사할 대상이다.
    #
    #  ⚠️ 실사고 2026-09-30(단계 4): `cells._verified` 가 **사실의 값**을 기사
    #     제목인 양 검증기에 넘겼다. 그래서 감독 교체 사실
    #     `{'since': '2026-09-26', …}` 의 `09-26` 이 **스코어 9-26** 으로 읽혀
    #     *"제목에 스코어가 있다"* → **경기 후 기사로 판정되어 거부**됐다.
    #  🔴 더 나쁜 것: 그 말은 **§12-c-2(경기 후 기사 배제)가 여태 기사에 적용된
    #     적이 없다**는 뜻이다 — 우리가 뽑은 값을 검사하고 있었다.
    article_title: str = ""
    article_body: str = ""
    #: 🔴 **이 사실은 "다른 경기"의 기록이다** — 기사가 아니다.
    #
    #  §12-c-1 신선도 검사(①)와 §12-c-2 경기 후 기사 배제(②)는 **기사**를 겨냥한
    #  규칙이다. *"어제 기사를 오늘 사실로 쓰지 마라"* 가 그 뜻이다.
    #  ⚠️ 그런데 **기준 XI** 는 과거 경기에서 일부러 가져온다. 사용자 글 첫 문장이
    #     그것이다 — *"잡힌 건 양 팀 직전 경기 선발 XI라 그걸 기준 XI로 놓고"*.
    #     그것에 신선도 검사를 걸면 **설계대로 만든 사실이 거부된다**
    #     (실측 2026-10-01: *"4일 지난 기사다"* 로 떨어졌다).
    #
    #  🔴 **구멍이 되지 않게 조건을 둔다**(계약이 집행한다):
    #     ① `value` 에 **어느 경기에서 왔는지**(`from_match`)가 있어야 한다
    #     ② `hardness` 는 **soft** 다 — 다른 경기의 선발은 오늘의 확정이 아니다
    #     ③ 사유가 `tried` 에 남는다 — 조용히 통과시키지 않는다
    from_past_match: bool = False
    #: §12-c-5 층. 🔴 **0 은 "모른다"** 다 — 1층(공식)과 섞이지 않게 0 을 쓴다.
    #  hardness 가 못 가르는 갈림을 이것이 가른다: 프리뷰(3층)와 예측(4층)은
    #  **둘 다 soft** 인데 프리뷰가 이긴다(§12-c-5).
    tier: int = 0

    @property
    def rank(self) -> int:
        return HARDNESS_RANK.get(self.hardness, 9)


def _shingles(s: str) -> frozenset:
    """글자 n-그램 집합. 🔴 공백·기호를 지우고 센다(매체마다 표기가 다르다)."""
    import re as _re
    flat = _re.sub(r"[\s\W_]+", "", str(s or "").lower())
    if len(flat) <= SHINGLE:
        return frozenset([flat]) if flat else frozenset()
    return frozenset(flat[i:i + SHINGLE]
                     for i in range(len(flat) - SHINGLE + 1))


def similar(a: str, b: str) -> float:
    """두 글의 **자카드 유사도**(0~1). 🔴 같은 보도자료를 묶는 데 쓴다."""
    x, y = _shingles(a), _shingles(b)
    if not x or not y:
        return 1.0 if x == y else 0.0
    return len(x & y) / len(x | y)


def independent_sources(facts: list) -> tuple[int, list[list]]:
    """🔴🔴 **독립 출처 수**와 그 묶음들(사용자 기술 지시 2026-10-03 · 기술 6).

    > 같은 보도자료가 8개 매체에 복사되면 출처 **8개가 아니라 1개**다.

    🔴 묶는 열쇠는 **인용·본문의 문장 유사도**다(주소가 아니다 — 같은 글이 주소만
       달라 오는 것이 바로 그 문제다).
    ⚠️ 글이 없으면 `value` 로 묶는다 — 그것이라도 같으면 같은 사실이다.
    """
    groups: list[list] = []
    for f in facts or []:
        text = str(getattr(f, "quote", "") or "") or \
            str(getattr(f, "article_title", "") or "") or str(f.value)[:300]
        for g in groups:
            head = str(getattr(g[0], "quote", "") or "") or \
                str(getattr(g[0], "article_title", "") or "") or \
                str(g[0].value)[:300]
            if similar(text, head) >= DUP_SIMILARITY:
                g.append(f)
                break
        else:
            groups.append([f])
    return len(groups), groups


def claim_state(facts: list) -> tuple[str, str]:
    """🔴 그 주장이 **확정인가 · 단독인가 · 엇갈리나**. `(상태, 사유)`.

    > 두 출처가 서로 다르면 **미상**, 시간 순으로 **더 새 상태가 명시돼 있으면**
    > ("의심" → "결장 확정") 새 쪽을 쓴다.

    ⚠️ **독립 출처로 센다** — 복사된 보도자료 여덟은 하나다.
    🔴 공식(1층)이 하나라도 있으면 **그것만으로 확정**이다(사용자 예시 그대로).
    """
    if not facts:
        return UNKNOWN, "사실 0건"
    n, groups = independent_sources(facts)
    official = any(int(getattr(f, "tier", 9) or 9) == 1 for f in facts)
    values = {_key(f.value) for f in facts}
    if len(values) > 1:
        # 🔴 **값이 엇갈린다** — 시간 순으로 더 새 쪽이 있나 본다
        dated = [f for f in facts if getattr(f, "published_at", None)]
        if len(dated) == len(facts) and len({f.published_at for f in dated}) > 1:
            newest = max(dated, key=lambda f: f.published_at)
            return FOUND, (f"출처 {n}곳이 엇갈렸고 **시간 순으로 더 새 쪽**을 쓴다 "
                           f"({newest.published_at:%m-%d %H:%M}Z)")
        return CONTRADICTED, f"독립 출처 {n}곳이 **서로 다른 값**을 말한다"
    if official:
        return FOUND, "공식(1층) 출처가 있다 — 단독이라도 확정이다"
    if n >= CONFIRM_AT:
        return FOUND, f"독립 출처 {n}곳이 같은 값을 말한다(묶음 전 {len(facts)}건)"
    return FOUND, (f"⚠️ **단독 출처**다(독립 {n}곳 · 묶음 전 {len(facts)}건) — "
                   f"확정이 아니다")


@dataclass
class Slot:
    """질문 하나의 상태. 여러 소스의 답이 여기 쌓인다."""

    question_id: str
    facts: list[Fact] = field(default_factory=list)
    state: str = UNKNOWN
    reason: str = ""            # 🔴 unknown 이면 **왜**를 적는다(§19-b-6)
    #: 🔴 **답을 찾았어도 남는 말.** `reason` 은 unknown 전용이라, 답을 찾은
    #  세포가 *"날짜 없어 사실 3건을 옆으로 치웠다"* 를 적을 자리가 없었다.
    #
    #  ⚠️ 실측 2026-09-30(리뷰 B3): 그 사유가 `Cell.tried` 에만 남고 블랙보드·DB·
    #     요약 어디에도 안 갔다 — 계약은 `cell.tried` **객체를 직접** 봐서 초록이었다.
    #     그러면 운영에서 "왜 라인업이 한 칸뿐인가"를 되짚을 수 없다.
    notes: list[str] = field(default_factory=list)

    #: 🔴 **독립 출처 수**(기술 6) — 복사된 보도자료 여덟은 하나다
    sources: int = 0
    #: 🔴 그 수를 어떻게 셌나 · 확정인가 단독인가 — 카드가 그대로 적는다
    source_note: str = ""

    @property
    def value(self):
        """정해진 값. `contradicted` 거나 비었으면 None."""
        return self.facts[0].value if self.state == FOUND and self.facts else None


class Blackboard:
    """슬레이트 하나가 쓰는 칠판. DB 적재는 `flush` 가 한다."""

    def __init__(self):
        self.slots: dict[str, Slot] = {}
        self._waiters: dict[str, list] = defaultdict(list)

    # ── 쓰기 ──────────────────────────────────────────────────────
    def write(self, fact: Fact) -> Slot:
        """사실 하나를 올리고, 그 질문을 기다린 세포를 깨운다(§19-b-7)."""
        slot = self.slots.setdefault(fact.question_id,
                                     Slot(fact.question_id))
        slot.facts.append(fact)
        slot.state, slot.reason = reconcile(slot.facts)
        # 🔴🔴 **독립 출처를 센다**(기술 6) — 같은 보도자료 여덟은 하나다.
        #    ⚠️ `reconcile` 은 **하나를 고르는** 일이고 이것은 **몇 곳이 말하나**다.
        #       둘은 다른 질문이라 둘 다 필요하다.
        slot.sources, _groups = independent_sources(slot.facts)
        _st, slot.source_note = claim_state(slot.facts)
        for cb in self._waiters.pop(fact.question_id, []):
            cb(slot)
        logger.info("[bb] %s ← %s (%s) → %s", fact.question_id,
                    _short(fact.value), fact.hardness, slot.state)
        return slot

    def note(self, question_id: str, text: str) -> Slot:
        """🔴 **답을 찾았어도 남길 말.** 조용한 0 금지(CLAUDE.md §5).

        `unknown()` 과 다르다 — 상태를 바꾸지 않는다. 질문은 닫혔지만 그 과정에서
        **버린 것·치운 것**이 있으면 여기 이름으로 남는다.
        """
        slot = self.slots.setdefault(question_id, Slot(question_id))
        if text and text not in slot.notes:
            slot.notes.append(text)
            logger.info("[bb] %s 비고 — %s", question_id, text)
        return slot

    def unknown(self, question_id: str, reason: str) -> Slot:
        """🔴 검색 0건은 "없음"이 아니라 unknown 이다(§7-5e). **사유를 붙인다.**"""
        slot = self.slots.setdefault(question_id, Slot(question_id))
        if slot.state != FOUND:
            slot.state = UNKNOWN
            slot.reason = reason
        logger.info("[bb] %s unknown — %s", question_id, reason)
        return slot

    # ── 읽기·구독 ─────────────────────────────────────────────────
    def get(self, question_id: str) -> Slot | None:
        return self.slots.get(question_id)

    def value(self, question_id: str, default=None):
        slot = self.slots.get(question_id)
        return slot.value if slot and slot.state == FOUND else default

    def ready(self, deps: list[str]) -> bool:
        """의존이 전부 닫혔나. unknown 도 **닫힌 것**이다 — 멈추지 않는다(§1)."""
        return all(q in self.slots for q in deps)

    def subscribe(self, question_id: str, cb) -> None:
        slot = self.slots.get(question_id)
        if slot and slot.state == FOUND:
            cb(slot)
            return
        self._waiters[question_id].append(cb)

    # ── 요약 ──────────────────────────────────────────────────────
    def unknowns(self) -> list[tuple[str, str]]:
        """🔴 못 잰 칸을 **이름과 사유로** 낸다(§5)."""
        return [(q, s.reason) for q, s in self.slots.items()
                if s.state != FOUND]

    def contradictions(self) -> list[str]:
        return [q for q, s in self.slots.items() if s.state == CONTRADICTED]

    def notes(self) -> list[tuple[str, str]]:
        """🔴 답을 찾은 질문이 남긴 말까지 **이름과 함께** 낸다.

        ⚠️ `unknowns()` 는 못 잰 칸만 낸다. 찾았지만 **일부를 버린** 칸은 여기서만
           보인다 — 둘 다 보고에 올라가야 "근거가 왜 이만큼인가"가 설명된다.
        """
        return [(q, t) for q, s in self.slots.items() for t in s.notes]

    async def flush(self, pool, game_id: int | None) -> int:
        """evidence 표에 적재한다. 🔴 `used_in`·`hardness` 를 그대로 남긴다."""
        n = 0
        for q, slot in self.slots.items():
            for f in slot.facts:
                await pool.execute(
                    "INSERT INTO evidence (game_id, claim, step, team, "
                    "player_id, value, source_url, publisher, published_at, "
                    "hardness, used_in, extracted_by) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)",
                    game_id, q, f.step, f.team, f.player_id, _short(f.value),
                    f.source, f.publisher, f.published_at, f.hardness,
                    _used_in(q), f.extracted_by)
                n += 1
        return n


def reconcile(facts: list[Fact]) -> tuple[str, str]:
    """§19-c 모순 처리. 반환은 `(state, reason)`.

    🔴 순서는 **hardness → published_at(최신) → 원문 인용 유무**다. 그래도 못
       정하면 `contradicted` 로 두고 억지로 하나로 만들지 않는다.
    ⚠️ 정렬은 안정적이어야 한다 — 같은 입력이 같은 답을 내야 채점이 성립한다.
    """
    if not facts:
        return UNKNOWN, "사실 0건"
    values = {_key(f.value) for f in facts}
    if len(values) == 1:
        facts.sort(key=_order)
        return FOUND, ""

    facts.sort(key=_order)
    best, second = facts[0], facts[1]
    if _order(best) < _order(second):
        return FOUND, ""
    # 🔴 hardness·시각·인용이 전부 같다. 마지막 갈림은 **§12-c-5 층**이다 —
    #    `verify.wins` 가 그 규칙의 원본이고, 여기서 부등호를 다시 쓰지 않는다.
    #    ⚠️ 프리뷰(3층)와 예측(4층)은 **둘 다 soft** 라 hardness 로는 안 갈린다.
    #       그런데 §12-c-5 는 예측 사이트를 판정 입력에서 아예 뺀다 — 그 차이가
    #       여기서 사라지면 예측값이 프리뷰값을 이길 수 있다.
    if best.tier and second.tier and best.tier != second.tier:
        win = V.wins(best.tier, second.tier)
        if win == best.tier:
            return FOUND, ""
        facts[0], facts[1] = second, best
        return FOUND, ""
    return CONTRADICTED, (
        f"같은 질문에 다른 값 — {_short(best.value)} vs {_short(second.value)} "
        f"(둘 다 {best.hardness}"
        + (f", {best.tier}층" if best.tier else ", 층 모름") + ")")


def _order(f: Fact):
    """센 것이 먼저. published_at 은 최신이 먼저, 인용 있는 쪽이 먼저."""
    return (f.rank,
            -(f.published_at.timestamp() if f.published_at else 0),
            0 if f.quote else 1)


def _key(v) -> str:
    if isinstance(v, (list, tuple)):
        return "|".join(sorted(str(x) for x in v))
    if isinstance(v, dict):
        return "|".join(f"{k}={v[k]}" for k in sorted(v))
    return str(v)


def _short(v) -> str:
    s = _key(v)
    return s if len(s) <= 400 else s[:397] + "…"


#: `evidence.used_in` 의 값 집합 — 🔴 **v4 §8 이 `lean` 을 폐기했다.**
#:
#: 종전 값 `lean`·`counter`·`trigger` 는 v3 의 판정 어휘였고, 그중 `lean` 이
#: §8 폐기 목록에 있다. 사용자 결정 2026-09-30: 다섯 값으로 교체하고 **원값은
#: `evidence.legacy_used_in` 에 보존**한다(#6). 마이그레이션은 `db/schema.sql`.
#:
#: ⚠️ DB 의 `evidence_used_in_ck` 제약이 이 집합을 강제한다 — 여기만 고치고
#:    스키마를 안 고치면 적재가 터진다. 그 대조는 계약이 한다.
USED_IN = ("variable", "premise_check", "opposite", "lineup_rerun", "grading")


def _used_in(question_id: str) -> str:
    """세포 질문 → 그 근거가 **어디에 쓰였나**(#6).

    🔴 `lean` 을 돌려주지 않는다 — v4 §8 폐기 어휘다. 기본값은 `variable` 이고,
       그것이 §1 의 *"변수"* 와 같은 뜻이다.
    """
    if question_id.startswith("counter:"):
        return "opposite"
    if question_id.startswith("premise:"):
        return "premise_check"
    if question_id.startswith("lineup:") or question_id.startswith("live:"):
        return "lineup_rerun"
    if question_id.startswith("grade:"):
        return "grading"
    return "variable"
