"""🔴🔴 **v5 §3 에이전트 루프** — 도구 셋 · 출력 스키마 · 중단 조건. [#10 #14 #15]

§3 원문:

> 에이전트는 경기 하나를 받아 **변수 → 가설 → 시나리오 초안**까지 JSON 으로
> 돌려준다. 그 뒤는 **전부 코드**다.
> §3-2 **도구 3개** — 전부 코드 구현, 에이전트는 **호출만** 한다:
>   `search(query, lang)` · `fetch(url)` · `done(output)`
> §3-7 중단 조건: §2 예산 상한 · 도구 호출 상한 · `done` 스키마 2회 실패 ·
>   90초×3 타임아웃. 어느 경우든 **그때까지의 변수로 §5 로 넘기고** 사유를 적는다.
>   에이전트가 변수 0개를 돌려주면 그 경기는 자료 부족이며 깔때기에 `agent_zero`.

🔴 §1 의 한 줄: *"에이전트는 **제안만** 한다 … **검증층을 통과한 변수만 변수**이고,
   판정층이 계산한 등급만 등급이다."*
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

KICK = datetime(2026, 10, 4, 20, 0, tzinfo=timezone.utc)


def _input():
    from app.agentloop import AgentInput
    return AgentInput(
        match_key="statsapi:849825", home="team:000338", away="team:000325",
        home_names=("Milwaukee Brewers", "밀워키 브루어스"),
        away_names=("San Diego Padres",), competition="MLB", sport="baseball",
        kickoff_utc=KICK, venue="American Family Field",
        langs=("en",), board=(), structured_facts=(), checklist=("absence_def",),
        gaps=("coach",))


# ══════════════════════════════════════════════════════════════════
# §3-1 입력
# ══════════════════════════════════════════════════════════════════


def test_v5_3_1_입력이_문서가_이름_댄_칸을_든다():
    """🔴 §3-1 — `match`·`structured_facts`·`board`·`langs`·`checklist`·`gaps`."""
    import dataclasses

    from app.agentloop import AgentInput
    names = {f.name for f in dataclasses.fields(AgentInput)}
    for k in ("match_key", "home", "away", "competition", "sport",
              "kickoff_utc", "venue", "langs", "board", "structured_facts",
              "checklist", "gaps"):
        assert k in names, (k, sorted(names))


def test_v5_3_1_에이전트는_열쇠로_받는다():
    """🔴 §8-1 — 팀은 **열쇠**다. ⚠️ 이름은 **곁들이는 라벨**이다."""
    from app.agentloop import AgentInput
    with pytest.raises(ValueError, match="열쇠"):
        AgentInput(match_key="x:1", home="Milwaukee Brewers", away="team:1",
                   kickoff_utc=KICK)


def test_v5_3_1_naive_킥오프를_안_받는다():
    from app.agentloop import AgentInput
    with pytest.raises(ValueError, match="시간대"):
        AgentInput(match_key="x:1", home="team:1", away="team:2",
                   kickoff_utc=datetime(2026, 10, 4, 20, 0))


# ══════════════════════════════════════════════════════════════════
# §3-2 도구 셋
# ══════════════════════════════════════════════════════════════════


def test_v5_3_2_도구가_셋이고_이름이_문서대로다():
    from app.agentloop import TOOL_NAMES, tool_specs
    assert list(TOOL_NAMES) == ["search", "fetch", "done"], TOOL_NAMES
    specs = tool_specs()
    assert len(specs) == 3
    for s in specs:
        assert s["type"] == "function"
        fn = s["function"]
        assert fn["name"] in TOOL_NAMES
        assert fn.get("description"), fn["name"]
        assert fn["parameters"]["type"] == "object"


def test_v5_3_2_search는_문지기를_지난다():
    """🔴 §3-2 — *"금지 패턴(이름 하나짜리)이면 **거부하고 사유 반환**."*"""
    from app.agentloop import Tools
    from app.reasons import Reason
    t = Tools(_input())
    got = t.search("Scotland", "en")
    assert got["ok"] is False
    assert got["reason"] == Reason.QUERY_TOO_BARE.value, got


def test_v5_3_2_fetch는_검색_결과에_있던_URL만_받는다():
    """🔴 §4-4 — *"에이전트가 검색 결과에 없던 URL 을 부르면 **거부**."*"""
    from app.agentloop import Tools
    t = Tools(_input())
    got = t.fetch("https://처음보는곳.example/x")
    assert got["ok"] is False and "검색 결과" in got["why"], got


def test_v5_3_2_도구_호출_상한을_센다():
    """🔴 §2 — search 24 · fetch 16. ⚠️ 넘으면 `budget_cut`."""
    from app.agentloop import Tools
    from app.reasons import Reason
    t = Tools(_input())
    t.budget.tool_calls["search"] = 24
    got = t.search("Milwaukee Brewers San Diego Padres lineup", "en")
    assert got["ok"] is False and got["reason"] == Reason.BUDGET_CUT.value, got


# ══════════════════════════════════════════════════════════════════
# §3-6 출력 스키마
# ══════════════════════════════════════════════════════════════════


def test_v5_3_6_스키마가_강제된다():
    """🔴 §2 — *"출력은 **구조화 출력(JSON 스키마)**으로 강제한다(§3-6)."*"""
    from app.agentloop import output_schema
    sch = output_schema()
    assert sch["name"] and sch["strict"] is True
    props = sch["schema"]["properties"]
    for k in ("variables", "hypotheses", "scenarios", "gaps", "notes"):
        assert k in props, (k, sorted(props))
    # 🔴 변수 하나의 칸이 §3-6 그대로인가
    v = props["variables"]["items"]["properties"]
    for k in ("id", "type", "team", "direction_hint", "claim", "quote",
              "url", "published_at", "lang", "conflict", "reverified"):
        assert k in v, (k, sorted(v))


def test_v5_3_6_등급_어휘를_금지한다():
    """🔴 §3-3 10항 — *"**등급·확률·배당·승자 단어를 쓰지 않는다.** 그것은 네
    일이 아니다."* ⚠️ 프롬프트가 그것을 말해야 한다."""
    from app.agentloop import system_prompt
    got = system_prompt()
    for must in ("등급", "확률", "배당", "승자"):
        assert must in got, must
    assert "인용" in got and "25" in got


# ══════════════════════════════════════════════════════════════════
# §3-7 중단 조건
# ══════════════════════════════════════════════════════════════════


def test_v5_3_7_변수_0개면_agent_zero():
    """🔴 §3-7 — *"변수 0개를 돌려주면 그 경기는 자료 부족이며 `agent_zero`."*"""
    from app.agentloop import finish
    from app.funnel import Funnel
    from app.reasons import Reason
    fun = Funnel()
    got, why = finish([], funnel=fun)
    assert got == [] and Reason.AGENT_ZERO.value in why, why
    assert (fun.drops.get("agent_vars") or {}).get(Reason.AGENT_ZERO) == 1


def test_v5_3_7_중단해도_모은_변수로_넘긴다():
    """🔴 §3-7 — *"어느 경우든 **그때까지의 변수로 §5 로 넘기고** 사유를 적는다."*"""
    from app.agentloop import stop_note
    from app.reasons import Reason
    got = stop_note(Reason.BUDGET_CUT, kept=3)
    assert "3개" in got and Reason.BUDGET_CUT.value in got, got
    assert "§5" in got


def test_v5_3_7_스키마_두_번_실패하면_멈춘다():
    from app.agentloop import SCHEMA_RETRIES
    assert SCHEMA_RETRIES == 2, SCHEMA_RETRIES


# ══════════════════════════════════════════════════════════════════
# 🔴 §1 — 에이전트 출력은 **그대로 카드로 가지 않는다**
# ══════════════════════════════════════════════════════════════════


def test_v5_3_출력이_검증층을_지나야_변수가_된다():
    """🔴🔴 §1 의 한 줄 — *"검증층을 통과한 변수만 변수."*

    구조 계약: `agentloop` 가 `verifylayer` 를 **부른다.**
    """
    import ast
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[2] / "app"
           / "agentloop.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    called = {ast.unparse(n.func) for n in ast.walk(tree)
              if isinstance(n, ast.Call)}
    assert any("verify_all" in c for c in called), (
        "🔴 `agentloop` 가 **검증층을 안 부른다**(§1·§5) — 에이전트 출력이 그대로 "
        "변수가 된다")


def test_v5_3_solar를_부른다():
    """🔴 §2 — 통로는 `app/solar.chat` 하나다."""
    import ast
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[2] / "app"
           / "agentloop.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    called = {ast.unparse(n.func) for n in ast.walk(tree)
              if isinstance(n, ast.Call)}
    assert any("solar.chat" in c for c in called), called
