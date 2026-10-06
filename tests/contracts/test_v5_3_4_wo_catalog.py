"""🔴🔴 **카탈로그를 에이전트에 잇는다** + **세포는 장부로 되살린다**.

사용자 지시 2026-10-05 (§1 둘째 조건 미달의 **진단 정정**):

> 세포 검색을 끄라고 한 건 맞지만, 그때 전제는 **카탈로그가 에이전트로 넘어간다**
> 는 것이었다. v5 §3-3 2번은 *"카탈로그 유형마다 적어도 한 번 찾는다"*, §3-4 는
> **카탈로그 전체를 에이전트 체크리스트로 준다.** 즉 이건 §3-3 gaps 우선
> 프롬프트로 풀 문제가 아니라, **카탈로그 체크리스트가 에이전트에 배선되지 않은
> 문제**다. 세포를 끄면서 그 질문들이 **아무에게도 안 넘어간** 것이다 — 이번
> 12→0과 **같은 꼴의 배선 끊김**이다.
>
> 1. 18개의 **유형 분포를 먼저 보고**한다.
> 2. **카탈로그를 에이전트에 잇는다** — 시스템 프롬프트에 v5 §3-4 카탈로그 **전
>    유형을 체크리스트**로 넣는다.
> 3. **세포를 장부로 되살린다** — 유형 × 팀 칸마다 `searched / found / empty /
>    not_tried` 를 기록하고, `done` 호출 시 **결장·로테이션·감독 발언·경기외** 네
>    유형이 `not_tried` 면 **`done` 을 거부**하고 *"이 유형을 아직 안 찾았다"* 를
>    돌려준다(**예산이 남아 있을 때만**). 이게 *"계획기는 버리고 장부는 남긴다"*
>    의 실제 모양이다.

══════════════════════════════════════════════════════════════════
🔴 실측 2026-10-05 — **겹치는 것이 0개였다**
══════════════════════════════════════════════════════════════════

```
에이전트가 낸 유형   form 10 · lineup 2 · context 2 · venue 1 ·
                    squad_offence 1 · head_to_head 1 · h2h 1
v5 §3-4 카탈로그    absence · coach_change · coach_conflict · def_absence ·
                    emotion · event_match · h2h_pattern · home_field ·
                    individual · lineup_intent · lineup_value · match_type ·
                    national_duty_return · pitcher_state · recent_pattern ·
                    squad_rotation · stakes · strength_gap ·
                    travel_schedule · venue_weather
겹침  🔴 **0개**
```

🔴 에이전트는 카탈로그를 **전혀 모른다** — 자기가 지은 이름을 쓴다. `checklist`
   칸은 **있었고**(`AgentInput.checklist`) `remind_line` 이 그것을 말할 준비까지
   돼 있었지만 **채우는 곳이 없었다.**
"""
from __future__ import annotations

import datetime as dt

import pytest

UTC = dt.timezone.utc

#: 🔴 사용자가 **이름을 댄 네 유형** — `done` 을 막는 기준이다.
FOUR = ("absence", "squad_rotation", "coach_conflict", "event_match")




# ══════════════════════════════════════════════════════════════════
# ② 카탈로그를 에이전트에 잇는다
# ══════════════════════════════════════════════════════════════════







def test_wo_cat_모르는_유형은_사유로_남는다():
    """🔴🔴 **카탈로그 밖 이름을 조용히 받지 않는다.**

    ⚠️ 실측: `form`·`context`·`squad_offence` 가 **전부 통과했다**. 🔴 그러면
       §4 유형표의 방향 규칙·hardness 규칙이 **하나도 안 걸린다** — 유형이
       뜻을 잃는다.
    """
    from app import reasons
    assert hasattr(reasons.Reason, "TYPE_OFF_CATALOG"), (
        "🔴 `Reason.TYPE_OFF_CATALOG` 가 없다 — 카탈로그 밖 유형을 **이름으로** "
        "남겨야 한다(#3)")


# ══════════════════════════════════════════════════════════════════
# ③ 세포를 **장부**로 되살린다
# ══════════════════════════════════════════════════════════════════

def test_wo_cat_장부가_네_상태를_든다():
    """🔴 *"유형 × 팀 칸마다 `searched / found / empty / not_tried`"*."""
    from app import ledgerbook
    # 🔴 **네 상태는 그대로 있어야** 한다 — `budget_cut` 이 2026-10-06 에
    #    더해졌다(사용자 지시 ③). ⚠️ 수를 박지 않고 **포함과 순서**를 센다.
    assert set(ledgerbook.STATES) >= {"not_tried", "searched", "empty",
                                      "found"}, ledgerbook.STATES
    # 🔴 사다리 순서가 뜻이다 — `mark` 가 앞으로만 간다
    idx = {s: i for i, s in enumerate(ledgerbook.STATES)}
    assert idx["not_tried"] < idx["searched"] < idx["empty"] < idx["found"], \
        ledgerbook.STATES
    # 🔴 막힌 칸은 **2차가 덮을 수 있어야** 한다(`found` 보다 아래다)
    assert idx.get("budget_cut", 0) < idx["found"], ledgerbook.STATES
    book = ledgerbook.Book()
    # 🔴 **처음은 전부 `not_tried`** — 0 이 아니라 *"안 해봤다"* 다(#3)
    assert book.state("absence", "team:1") == "not_tried"
    book.searched("absence", "team:1")
    assert book.state("absence", "team:1") == "searched"
    book.found("absence", "team:1")
    assert book.state("absence", "team:1") == "found"
    # ⚠️ 뒤로 **안 간다** — 찾은 것이 안 찾은 것이 되지 않는다
    book.searched("absence", "team:1")
    assert book.state("absence", "team:1") == "found"


def test_wo_cat_장부가_빈_것과_안_해본_것을_가른다():
    """🔴🔴 **조용한 0 금지**(#3) — *"찾았는데 없었다"* 와 *"안 찾았다"* 는 다르다."""
    from app import ledgerbook
    book = ledgerbook.Book()
    book.empty("coach_conflict", "team:2")
    assert book.state("coach_conflict", "team:2") == "empty"
    assert book.not_tried(FOUR, ["team:1", "team:2"]), "🔴 안 해본 칸을 못 센다"
    # ✅ 네 유형을 양 팀 다 해봤으면 비어야 한다
    for t in FOUR:
        for team in ("team:1", "team:2"):
            book.searched(t, team)
    assert book.not_tried(FOUR, ["team:1", "team:2"]) == []






@pytest.mark.parametrize("t", FOUR)
def test_wo_cat_네_유형이_카탈로그에_있다(t):
    """🔴 내가 고른 이름이 아니라 **카탈로그의 이름**인지 확인한다."""
    from app import rules
    assert t in rules.variable_types(), (
        f"🔴 `{t}` 가 카탈로그에 없다 — 사용자가 댄 네 유형을 **카탈로그 "
        f"이름으로** 옮겼는지 확인하라")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **돌연변이가 뚫은 자리를 메운다** (2026-10-05)
# ══════════════════════════════════════════════════════════════════
#
#  C02 `checklist=tuple(...)` → `checklist=()`   ⚠️ **통과했다**(글자 검사였다)
#  C06 `self._book_search(query)` → `pass`       ⚠️ **통과했다**(글자 검사였다)
#
# 🔴 둘 다 *"소스에 그 낱말이 있나"* 만 봤다 — §9-5 가 무효로 보는 꼴이다.






# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **거부가 예산을 태웠다** — 실측 2026-10-05 (내가 넣은 결함)
# ══════════════════════════════════════════════════════════════════
#
#  ```
#  Norway:   budget_cut 출력 25,108/25,000 · 턴 15 → 변수 **0개**
#  Portugal: budget_cut 출력 25,891/25,000 · 턴 15 → 변수 **0개**
#  ```
#
#  🔴 `done` 을 거부하자 에이전트가 더 찾았고, 그 턴들이 **쪽 상한을 태워**
#     `budget_cut` 으로 끊겼다 — **`done` 을 부를 기회가 없었다.**
#  ⚠️ 지시서의 *"예산이 남아 있을 때만"* 을 내가 `can_call()`(= 아직 0 이
#     아니다)로만 읽었다. 🔴 **거부한 뒤에도 `done` 을 부를 만큼** 남아야 한다.





# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **`done` 을 받았으면 예산과 무관하다** — 실측 2026-10-05
# ══════════════════════════════════════════════════════════════════
#
#  ```
#  [agent] 턴 14 · done({'variables': [ … ]}) → ok 끝낸다
#  [agent] 🔴 `done` 인자 칸=[…] · 변수 **16줄**
#  · 세포 에이전트:Portugal: budget_cut 출력 31,833/25,000 → 판정층 변수 **0개**
#  ```
#
#  🔴 `done` 이 **왔고 변수 16줄을 줬는데** 판정층에 0개였다. 까닭: `done` 뒤의
#     **스키마 턴**이 `can_call()` 에서 터져(`SolarUnavailable`) 그 인자를
#     **버렸다**.
#  ⚠️ 그 턴은 **필요 없었다** — `done_args` 가 이미 스키마 그 자체다(§3-2).





# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **지운 계약 일곱 — 승계 번호**(딥서치 재구축 §1·§7 · 2026-10-05)
# ══════════════════════════════════════════════════════════════════
#
#  지운 것: `done_을_거부한다` · `예산이_없으면_done_을_막지_않는다` ·
#  `네_유형을_해봤으면_done_이_된다` · `done_거부가_실제_루프에서_돈다` ·
#  `거부는_예비분이_있을_때만` · `예비분이_실측에서_온다` ·
#  `여유가_많으면_여전히_막는다`
#
#  **승계 사유**: 커버리지 보장이 **거부에서 분할로 이동했다**(이 재구축 §2 —
#  경기 하나 = 하위 과제 8개, 유형군 4 × 홈/원정). 🔴 커버리지 계약은
#  **M59**(하위 예산 독립)와 **장부 `found` 배선 계약**이 승계한다.
#
#  ⚠️ 왜 지웠나 — 거부가 **예산을 태웠다**: 실측 2026-10-05 에서 `done` 거부가
#     에이전트를 더 찾게 만들어 출력 25k 를 소진하고 `budget_cut` 에 걸렸다.
#     그래서 `done` 이 **한 번도 불리지 못해 변수가 18→0** 이 됐다.
#  🔴 지시서 §1: *"분할 자체가 커버리지를 보장하므로 제거."*
#
#  ⚠️ **남긴 것 열하나**는 카탈로그 배선·장부 네 상태 계약이다 — 그것은
#     분할 뒤에도 그대로 필요하다(§3 이 장부를 쓴다).
