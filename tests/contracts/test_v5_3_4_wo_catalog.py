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


def _inp(**kw):
    from app import agentloop
    base = {"match_key": "fotmob:1", "home": "team:1", "away": "team:2",
            "home_names": ("Portugal",), "away_names": ("Norway",),
            "competition": "UEFA Nations League", "sport": "soccer",
            "kickoff_utc": dt.datetime(2026, 10, 4, 18, 45, tzinfo=UTC),
            "venue": "Estádio da Luz", "langs": ("en",)}
    base.update(kw)
    return agentloop.AgentInput(**base)


# ══════════════════════════════════════════════════════════════════
# ② 카탈로그를 에이전트에 잇는다
# ══════════════════════════════════════════════════════════════════

def test_wo_cat_시스템_프롬프트에_카탈로그_전_유형이_있다():
    """🔴🔴 *"시스템 프롬프트에 v5 §3-4 카탈로그 **전 유형**을 체크리스트로"*."""
    from app import agentloop, rules
    said = agentloop.system_prompt()
    missing = [t for t in rules.variable_types() if t not in said]
    assert not missing, (
        f"🔴 카탈로그 {len(missing)}종이 프롬프트에 **없다** — 에이전트가 "
        f"자기가 지은 이름을 쓴다(실측: 겹침 0개): {missing}")


def test_wo_cat_checklist_가_채워진다():
    """🔴 `AgentInput.checklist` 가 **비어 있었다** — 채우는 곳이 없었다(#2).

    ⚠️ `remind_line` 은 그것을 말할 준비가 돼 있었다 — **재료만 없었다.**
    """
    import inspect

    from app import analyze
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(analyze._run_agent))
    assert "checklist=" in body, (
        "🔴 `_run_agent` 가 `checklist` 를 **안 채운다** — 카탈로그가 "
        "에이전트에 안 닿는다(#2 배선)")


def test_wo_cat_카탈로그_이름을_코드에_안_적는다():
    """🔴 20종을 손으로 적지 않는다 — `variable_types.yaml` 이 원본이다."""
    import inspect

    from app import agentloop
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(agentloop.system_prompt))
    for name in ("absence", "squad_rotation", "venue_weather"):
        assert name not in body, (
            f"🔴 카탈로그 이름 `{name}` 을 **코드에 박았다** — 설정에서 "
            f"읽어라(사본 금지)")


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
    assert ledgerbook.STATES == ("not_tried", "searched", "empty", "found"), \
        ledgerbook.STATES
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


def test_wo_cat_C02_실제로_카탈로그가_에이전트에_닿는다():
    """🔴🔴 **C02** — `checklist` 를 비워도 빨개져야 한다.

    ⚠️ `_run_agent` 를 직접 돌릴 수는 없다(네트워크·DB). 🔴 그래서 그 함수가
       만드는 `AgentInput` 을 **같은 방법으로** 만들어 칸을 확인한다.
    """
    import ast
    import inspect

    from app import agentloop, analyze, rules
    src = inspect.getsource(analyze._run_agent)
    tree = ast.parse(src.lstrip())
    # 🔴 `AgentInput(...)` 호출의 `checklist=` 인자를 **찾아 평가한다**
    found = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = getattr(fn, "attr", None) or getattr(fn, "id", None)
        if name != "AgentInput":
            continue
        for kw in node.keywords:
            if kw.arg == "checklist":
                found = ast.unparse(kw.value)
    assert found, "🔴 `AgentInput(checklist=…)` 가 **없다**(#2 배선)"
    # 🔴 **빈 것이면 안 된다** — 그것이 §1 의 버그였다
    assert found not in ("()", "tuple()", "[]"), (
        f"🔴 `checklist` 를 **비워서** 넘긴다 — 에이전트가 카탈로그를 모른다"
        f"(실측 2026-10-05: 겹침 0개): {found}")
    # ✅ 그리고 그 글이 **카탈로그를 읽는다**
    assert "variable_types" in found, found
    # 🔴 마지막으로 **그 값이 전 유형을 담나** — 눈으로가 아니라 수로 본다
    got = tuple(sorted(rules.variable_types()))
    assert len(got) >= 20, len(got)
    assert set(agentloop._catalog()) == set(got)


def test_wo_cat_C06_검색이_장부에_실제로_적힌다():
    """🔴🔴 **C06** — `_book_search` 를 꺼도 빨개져야 한다.

    ⚠️ 종전 계약은 `done_ok` 만 시험했고 **장부를 손으로 채웠다** — 그래서
       *"검색이 장부에 적나"* 는 아무도 안 봤다.
    """
    from app import agentloop, ledgerbook
    book = ledgerbook.Book()
    tools = agentloop.Tools(inp=_inp(checklist=FOUR), book=book, seen=None)
    # 🔴 결장 질의를 던진다 — `absence` 칸이 `searched` 가 돼야 한다
    tools.search("Portugal Norway Nations League injury news October 4", "en")
    said = [k for (k, _), v in book.cells.items() if v != "not_tried"]
    assert said, (
        "🔴 검색을 던졌는데 **장부가 비었다** — `done` 막기가 뜻을 잃는다"
        "(안 해본 칸을 영영 못 지운다)")
    # ⚠️ 어느 유형이 적혔는지도 본다(결장 낱말이 들어간 질의였다)
    assert "absence" in said or "def_absence" in said, said


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


def test_wo_cat_done_인자가_있으면_스키마_턴을_안_부른다():
    """🔴🔴 **받은 것을 예산 때문에 버리지 않는다.**

    ⚠️ `done` 의 인자가 **곧 스키마**다(§3-2: *"`done` 의 파라미터를 스키마로
       둔다"*). 🔴 그것을 받은 뒤 다시 묻는 것은 돈만 쓰고, 예산이 끝나 있으면
       **받은 변수를 통째로 버린다**(실측: 16줄 → 0개).
    """
    import inspect

    from app import agentloop
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(agentloop.run))
    i = body.index("if done_args is not None:")
    seg = body[i:i + 1200]
    # 🔴 `cands` 가 찼으면 **재시도 루프에 안 들어가야** 한다
    assert "if cands" in seg, seg[:300]
    # 🔴 그리고 예산으로 터지는 자리가 **그 뒤**여야 한다
    assert seg.index("if cands") < seg.index("solar.chat"), (
        "🔴 `done` 인자를 읽기 **전에** 다시 묻는다 — 예산이 끝나면 받은 "
        "변수를 통째로 버린다(실측 2026-10-05: 16줄 → 0개)")


def test_wo_cat_예산이_끝나도_done_인자를_읽는다():
    """🔴🔴 **행동으로** 잰다 — 예산을 막아 두고 `done` 인자를 읽히게 한다."""
    from app import agentloop, solar

    bud = solar.MatchBudget(side=True)
    bud.blocked = "budget_cut: 시험 — 출력 31833/25000"
    inp = _inp(checklist=FOUR)
    args = {"variables": [{
        "id": "v1", "type": "absence", "team": str(inp.home),
        "direction_hint": "home", "claim": "호날두가 빠진다",
        "quote": "Ronaldo excluded", "url": "https://x/a",
        "published_at": "2026-10-04T06:00:00Z", "tier": "local"}],
        "hypotheses": [], "scenarios": [], "gaps": [], "notes": []}
    got, why = agentloop.parse_args(args, inp=inp)
    assert got, (
        f"🔴 예산이 끝났다고 **받은 `done` 인자를 못 읽는다**: {why}")

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
