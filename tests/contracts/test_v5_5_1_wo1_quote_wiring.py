"""🔴🔴 **지시서 §1-1 — 에이전트가 연 본문이 검증층에 닿는다** + 인용 양방향.

작업 지시서(오픈월드) §1-1:

> 포르투갈 후보 12개 → 검증 0개의 **사유 진단** — 12개 각각에 대해 사유 코드,
> 에이전트가 낸 `quote`, 그 URL 에서 받아 둔 본문의 해당 부근 200자를 나란히
> 보고한다. 인용 검증(§5-1)이 **정규화 차이**(따옴표·공백·NBSP·대소문자·발음
> 기호)로 진짜 인용을 떨어뜨리는지, 에이전트가 **실제로 지어냈는지**를 가른다.
> … 계약에 **"진짜 인용 10건은 통과, 지어낸 인용 10건은 폐기"** 양방향 고정물을 둔다.

══════════════════════════════════════════════════════════════════
🔴 진단 결과 — **정규화도 지어냄도 아니다. 배선이 끊겼다.**
══════════════════════════════════════════════════════════════════

실측 2026-10-04(`pn2.log`) — 열두 건이 **전부 같은 사유**였다:

```
verified_vars 탈락: quote_not_found 12
[verify] 폐기 V8  — 🔴 그 URL 의 **본문을 받아 두지 않았다** — 대조할 수 없다
                     (fail-closed): https://www.si.com/soccer/norway-vs-portugal…
[verify] 폐기 V12 — 🔴 같은 것: https://www.si.com/soccer/portugal-vs-norway…
```

🔴 **인용을 본문과 비교조차 못 했다.** 까닭:

```
app/analyze.py:153
    ctx = verifylayer.Context(…, bodies=dict(getattr(seen, "bodies", {}) or {}))
                                             ↑ 세포가 받아 둔 것만

app/agentloop.py  Tools._open()
    self.bodies[url] = body      ← 에이전트가 직접 연 본문은 **여기** 있다
```

⚠️ 결정 ③(세포는 장부)으로 `seen.bodies` 가 **비었다**. 에이전트가 제 손으로
   연 본문은 `Tools.bodies` 에 쌓이는데 **아무도 검증층에 넘기지 않았다.**
🔴 이 저장소가 반복해 다친 자리다(#2) — *"만든 것은 부르는 곳이 있어야 한다."*
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib

import pytest

UTC = dt.timezone.utc
FIX = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "openworld"


def _ctx(bodies=None, roster=()):
    from app import verifylayer
    return verifylayer.Context(
        home="team:000191", away="team:000174",
        home_names=["Portugal"], away_names=["Norway"],
        competition="UEFA Nations League", roster=list(roster),
        kickoff=dt.datetime(2026, 10, 4, 18, 45, tzinfo=UTC),
        bodies=dict(bodies or {}))


# ══════════════════════════════════════════════════════════════════
# ① 배선 — 에이전트가 연 본문이 검증층에 **닿나**
# ══════════════════════════════════════════════════════════════════

def test_wo1_1_에이전트가_연_본문이_검증층에_닿는다():
    """🔴🔴 **그 열두 건이 떨어진 바로 그 자리**다(#2 배선).

    ⚠️ `Tools.bodies` 에 있는 본문이 `verify_all` 이 보는 `ctx.bodies` 로
       들어가지 않으면, 에이전트가 제 손으로 연 기사의 인용은 **구조적으로
       전부** `quote_not_found` 가 된다.
    """
    import inspect

    from app import agentloop
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(agentloop.run))
    assert "bodies" in body, (
        "🔴 `agentloop.run` 이 **에이전트가 연 본문을 검증층에 안 넘긴다** — "
        "인용 대조가 구조적으로 전부 실패한다(실측 12/12)")


def test_wo1_1_실제로_합쳐지나():
    """🔴 글자가 아니라 **동작**으로 본다(§9-5 가 글자 검사를 무효로 본다)."""
    from app import agentloop

    inp = agentloop.AgentInput(
        match_key="fotmob:1", home="team:000191", away="team:000174",
        home_names=("Portugal",), away_names=("Norway",),
        competition="UEFA Nations League", sport="soccer",
        kickoff_utc=dt.datetime(2026, 10, 4, 18, 45, tzinfo=UTC),
        venue="Estádio da Luz", langs=("en",))
    tools = agentloop.Tools(inp=inp)
    tools.bodies["https://x/a"] = "Portugal will be without João Félix."
    ctx = _ctx()
    # 🔴 **합치는 함수가 있어야** 한다 — 그리고 ctx 가 그것을 들어야 한다
    assert hasattr(agentloop, "merge_bodies"), (
        "🔴 `agentloop.merge_bodies` 가 없다 — 에이전트가 연 본문을 검증층에 "
        "합치는 자리가 없다")
    agentloop.merge_bodies(ctx, tools)
    assert ctx.bodies.get("https://x/a"), ctx.bodies


# ══════════════════════════════════════════════════════════════════
# ② 인용 양방향 고정물 — 진짜 10건 통과 · 지어낸 10건 폐기
# ══════════════════════════════════════════════════════════════════

def _cases() -> dict:
    """🔴 **실측 저장**이다(§5: 라이브 웹에 기대는 테스트는 계약이 아니다)."""
    p = FIX / "quote_cases.json"
    assert p.exists(), (
        f"🔴 고정물이 없다: {p} — §1-1 이 **양방향 10+10** 을 요구한다")
    return json.loads(p.read_text(encoding="utf-8"))


def test_wo1_1_고정물이_열_건씩_있다():
    """🔴 *"진짜 인용 10건은 통과, 지어낸 인용 10건은 폐기"*."""
    box = _cases()
    assert len(box["real"]) >= 10, len(box["real"])
    assert len(box["fake"]) >= 10, len(box["fake"])


@pytest.mark.parametrize("i", range(10))
def test_wo1_1_진짜_인용은_통과한다(i):
    """🔴🔴 **정규화 차이로 진짜를 떨어뜨리지 않는다.**

    ⚠️ 고정물 열 건은 전부 *"본문에 있는 말"* 인데 **글자 모양이 다르다**:
       곧은 따옴표↔굽은 따옴표 · NBSP · 전각 · 대소문자 · 발음 기호 · 줄바꿈.
    """
    from app.verifylayer import quote_ok
    case = _cases()["real"][i]
    ok, why = quote_ok(case["quote"], case["body"])
    assert ok is True, f"🔴 **진짜 인용을 떨어뜨렸다**({case['why']}): {why}"


@pytest.mark.parametrize("i", range(10))
def test_wo1_1_지어낸_인용은_폐기한다(i):
    """🔴 반대쪽도 막는다 — 정규화를 넓히다 **지어낸 것까지** 통과시키면 안 된다."""
    from app.verifylayer import quote_ok
    case = _cases()["fake"][i]
    ok, why = quote_ok(case["quote"], case["body"])
    assert ok is False, f"🔴 **지어낸 인용이 통과했다**({case['why']}): {why}"


def test_wo1_1_본문이_없으면_사유가_다르다():
    """🔴 §8-6 — *"본문을 못 받았다"* 와 *"인용이 본문에 없다"* 는 **다른 사유**다.

    ⚠️ 실측 12건이 `quote_not_found` 로 묶여서 **고칠 곳을 가렸다**. 🔴 본문이
       없는 것은 **수집/배선** 문제이고, 인용이 없는 것은 **에이전트** 문제다.
    """
    from app import reasons
    assert hasattr(reasons.Reason, "BODY_MISSING"), (
        "🔴 `Reason.BODY_MISSING` 이 없다 — 본문 부재를 `quote_not_found` 로 "
        "적으면 거짓 사유다(§8-6)")
    got = reasons.Reason.BODY_MISSING
    assert got.fix_where in ("수집", "읽기"), got.fix_where


def test_wo1_1_W03_본문_부재는_enum_으로_갈린다():
    """🔴🔴 **W03 이 통과했다** — 이 파일에 그 계약이 없었다.

    ⚠️ `BODY_MISSING` 을 **만들고** `Reason.QUOTE_NOT_FOUND` 로 되돌려도
       이 파일은 초록이었다(다른 파일이 잡았지만 여기 돌연변이를 돌렸다).
    🔴 §9-5 가 무효로 보는 꼴이다 — **그 자리에서** 잰다.
    """
    from app.reasons import Reason
    from app.verifylayer import verify_one

    class _V:
        type = "absence"
        team = "team:000191"
        direction = "home"
        hardness = "hard"
        quote = "Portugal will be without João Félix."
        url = "https://x/a"
        source = "https://x/a"
        published_at = dt.datetime(2026, 10, 4, 6, 0, tzinfo=UTC)

    # 🔴 본문이 **없다** → `BODY_MISSING`(고칠 곳 **수집**)
    ok, reason, why = verify_one(_V(), _ctx(bodies={}))
    assert ok is False
    assert reason is Reason.BODY_MISSING, (
        f"🔴 본문 부재를 `{reason}` 로 적었다 — 고칠 곳이 **에이전트**로 "
        f"읽힌다(§8-6 거짓 사유). 실측 12/12 가 그렇게 가려졌다: {why}")
    assert reason.fix_where == "수집", reason.fix_where


def test_wo1_1_W02_합자도_벗긴다():
    """🔴🔴 **W02 가 통과했다** — 고정물에 발음 기호가 **실제로 없었다**.

    ⚠️ 내가 `.replace("Odegaard","Ødegaard")` 를 썼는데 그 문장에 `Odegaard` 가
       없어서 **아무것도 안 바뀐 인용**이 고정물로 들어갔다(실측으로 고쳤다).
    🔴 그리고 `Ø` 는 NFD 로 **분해되지 않는다** — 합자·획 글자는 표가 필요하다.
    """
    from app.verifylayer import _norm
    assert _norm("Ødegaard") == _norm("Odegaard")
    assert _norm("Møller") == _norm("Moller")
    # 🔴 NFD 로 **되는** 것도 여전히 돼야 한다
    assert _norm("Håland") == _norm("Haland")
    assert _norm("Vítinha") == _norm("Vitinha")
    # ⚠️ 한글·가나·한자는 **건드리지 않는다**
    assert _norm("広島東洋カープ") == "広島東洋カープ"
    assert _norm("한화 이글스") == "한화 이글스"
