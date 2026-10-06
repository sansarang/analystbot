"""🔴🔴 **§2 질의 생성 규칙** — 지시서 2026-10-06 §2 · M129.

원문 질의(실측 2026-10-06 카드):

```
§12-b 위반 'Georgia squad 2 UEFA Nations League B Grp. 2'
§12-b 위반 'Northern Ireland national team return Oct 5'
```

🔴 템플릿 변수에 **대회 전체명(조 포함)과 날짜**가 그대로 들어가 문지기에 걸렸다.
⚠️ **§12-b 문지기 자체는 바꾸지 않는다** — 문지기가 맞게 막았다. 고칠 곳은
   질의를 만드는 쪽이다.

> 대회 짧은 이름 — `competition_short(full)` 한 함수(정본 하나, 사본 금지):
> 조·라운드·리그 등급 꼬리 제거.
> 템플릿 변수 제한 — `{team}`·`{opp}`·`{comp}`·`{coach}`·`{player}`·`{word}` 뿐.
> **날짜·숫자·조 번호·라운드 변수는 템플릿에서 금지** — `time_range=week` 가
> 날짜를 대신한다.
> 사전 검사 — 봇 시작 시 모든 템플릿을 고정물 3경기로 렌더링해 §12-b 와 길이
> 규칙(3~10단어)을 통과하는지 확인. 하나라도 걸리면 **시작 실패.**
"""
from __future__ import annotations

import pytest


# ══════════════════════════════════════════════════════════════════
# ① 대회 짧은 이름 — 한 함수
# ══════════════════════════════════════════════════════════════════

CASES = [
    ("UEFA Nations League B Grp. 2", "Nations League"),
    ("CONCACAF Nations League A Grp. 2", "CONCACAF Nations League"),
    ("FIFA ASEAN Cup Premier Division", "FIFA ASEAN Cup"),
    ("Women's Asian Cup Grp. A", "Women's Asian Cup"),
    ("USL Championship", "USL Championship"),
    ("KBO 리그", "KBO"),
]


@pytest.mark.parametrize("full,want", CASES)
def test_wo2_대회_짧은_이름(full, want):
    from app import queries
    got = queries.competition_short(full)
    assert got == want, (full, got, want)


def test_wo2_꼬리가_실제로_빠진다():
    """🔴 조·라운드·시즌·리그 등급 표시가 남으면 §12-b 가 또 막는다."""
    from app import queries
    for full in ("X League Group A", "Y Cup Round of 16", "Z League Matchday 5",
                 "W League 2026-27", "V Nations League C Grp. 4"):
        got = queries.competition_short(full)
        low = got.lower()
        for bad in ("group", "grp", "round of", "matchday", "2026-27"):
            assert bad not in low, (full, got, bad)
        assert got.strip(), full


# ══════════════════════════════════════════════════════════════════
# ② 템플릿 변수 제한 — 날짜·숫자·라운드 금지
# ══════════════════════════════════════════════════════════════════

def test_wo2_템플릿_변수가_허용_목록_안이다():
    from app import queries, rules
    allowed = set(queries.TEMPLATE_SLOTS)
    assert allowed == {"team", "opp", "comp", "coach", "player", "word"}, allowed
    bad: list[str] = []
    for vtype in sorted(rules.variable_types()):
        for tpl, _lang in rules.type_templates_tagged(vtype):
            for slot in queries.slots_in(tpl):
                if slot not in allowed:
                    bad.append(f"{vtype}: {{{slot}}} in {tpl!r}")
    assert not bad, (
        "🔴 템플릿에 **금지된 변수**가 있다(날짜·숫자·조 번호는 "
        "`time_range=week` 가 대신한다):\n  " + "\n  ".join(bad))


# ══════════════════════════════════════════════════════════════════
# ③ M129 사전 검사 — 고정물 3경기로 렌더링해 문지기를 통과하나
# ══════════════════════════════════════════════════════════════════

def test_wo2_M129_모든_템플릿이_고정물_3경기를_통과한다():
    """🔴🔴 **돌려서** 본다 — 렌더링해 §12-b 문지기와 길이 규칙에 넣는다."""
    from app import queries
    bad = queries.template_precheck()
    assert bad == [], (
        "🔴 §12-b·길이 규칙에 걸리는 템플릿이 있다:\n  " + "\n  ".join(bad))


def test_wo2_M129_걸리면_봇_시작이_실패한다():
    """🔴 *"하나라도 걸리면 시작 실패(조용히 건너뛰지 않는다)."*"""
    from app import queries
    assert hasattr(queries, "assert_templates_ok")
    queries.assert_templates_ok()          # 🔴 지금은 통과해야 한다
    # 🔴 **거짓 하나를 넣으면 터진다** — 검사가 실제로 막는지 본다
    with pytest.raises(ValueError, match="템플릿"):
        # 🔴 9낱말짜리 — 실측에서 떨어진 그 꼴이다(`llm.query_ok` 상한 6)
        queries.assert_templates_ok(extra=[(
            "나쁜유형",
            "{team} squad 2 international break national team roster {comp}",
            "en")])


def test_wo2_M129_기동이_그_검사를_부른다():
    """🔴 #2 배선 — 검사만 만들고 **안 부르면** 없는 것이다."""
    import inspect

    from app import bot_boot
    src = inspect.getsource(bot_boot)
    assert "assert_templates_ok" in src, (
        "🔴 기동이 템플릿 사전 검사를 **안 부른다** — 걸리는 템플릿이 조용히 "
        "운영으로 간다(지시서 §2: 시작 실패)")


# ══════════════════════════════════════════════════════════════════
# ④ 그 두 질의가 **실제로** 사라졌나
# ══════════════════════════════════════════════════════════════════

def test_wo2_실측_위반_질의가_안_나온다():
    """🔴 카드 원문에 찍힌 그 두 꼴을 **같은 입력으로** 다시 만들어 본다."""
    from app import llm, queries, querygate
    out: list[str] = []
    for vtype in ("squad_rotation", "national_duty_return"):
        for v in queries.catalog_variants(
                vtype, team="Georgia", opponent="Northern Ireland",
                league="UEFA Nations League B Grp. 2", langs=("en", "ka")):
            said = str(v.text or "").strip()
            if said:
                out.append(said)
    assert out, "전제가 깨졌다 — 질의가 하나도 안 나왔다"
    for said in out:
        # 🔴🔴 **카탈로그를 실제로 거르는 문지기는 `llm.query_ok`** 다(1~6낱말).
        #    ⚠️ 나는 처음에 `querygate.gate`(10낱말)로 쟀고, 그래서 9낱말 질의가
        #       계약을 통과했다 — 문지기를 잘못 짚으면 계약이 거짓말을 한다.
        assert llm.query_ok(said), (
            f"🔴 §12-b(`llm.query_ok`) 에 걸리는 질의가 아직 나온다: {said!r} "
            f"(낱말 {len(said.split())}개 · 상한 6)")
        ok, _reason, why = querygate.gate(said, seed=True)
        assert ok, f"🔴 `querygate` 에 걸린다: {said!r} — {why}"
        # 🔴 대회 전체명·조 번호가 남아 있으면 안 된다
        assert "Grp." not in said, said
