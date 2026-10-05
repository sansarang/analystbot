"""🔴🔴 **v5 §3-2·§3-7 — 도구 루프.** 에이전트가 **도구를 돌고** 끝낸다.

§3-2 원문(도구 셋)과 §3-7 원문(중단 조건):

> 도구: `search(query, lang)` · `fetch(url)` · `done(output)`.
> `tools` 와 `schema` 를 **함께 주지 않는다** — 도구를 쓰는 턴은 도구 호출로
> 끝나고, **마지막 `done` 턴에서만 스키마를 강제한다.**
> 중단: 변수 0개 → `agent_zero` / `done` 스키마 **2회 실패** / 예산 소진.
> 그때까지의 변수로 §5 로 넘기고 **사유를 적는다.**

══════════════════════════════════════════════════════════════════
🔴 왜 루프가 없으면 에이전트가 **거짓말을 한다**
══════════════════════════════════════════════════════════════════

⚠️ 종전 `run()` 은 `solar.chat(msgs, schema=…)` 를 **한 번** 불렀다 — `tools`
   를 **안 넘겼다.** 프롬프트는 *"도구로만 일한다"* 라고 적었는데 도구가 없다.
🔴 그러면 모델은 **기억으로** 변수를 짓고 인용을 **지어낸다**. §5-1 이 그것을
   전부 폐기하므로 수는 안 틀리지만 — **토큰만 쓰고 0건**이 된다.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

KICK = datetime.now(timezone.utc) + timedelta(hours=2)
BODY = ("Milwaukee Brewers manager Pat Murphy said Logan Henderson will start "
        "on Saturday against the San Diego Padres.")
URL = "https://www.mlb.com/brewers/news/rotation"


def _inp():
    from app import agentloop
    return agentloop.AgentInput(
        match_key="statsapi:849825", home="team:000338", away="team:000325",
        home_names=("Milwaukee Brewers",), away_names=("San Diego Padres",),
        competition="MLB", sport="baseball", kickoff_utc=KICK,
        venue="American Family Field", langs=("en",))


def _ctx():
    from app import verifylayer
    return verifylayer.Context(
        home="team:000338", away="team:000325",
        home_names=["Milwaukee Brewers"], away_names=["San Diego Padres"],
        competition="MLB", roster=["Logan Henderson", "Pat Murphy"],
        kickoff=KICK, bodies={URL: BODY})


def _seen():
    from app.cells import Seen
    s = Seen()
    s.add_hit(URL, title="Brewers rotation", snippet="Henderson will start",
              query="Milwaukee Brewers San Diego Padres MLB baseball")
    s.add_body(URL, BODY)
    return s


def _tool_turn(name: str, args: dict, *, cid: str = "c1") -> dict:
    """🔴 Solar 가 도구를 부르는 턴의 모양(OpenAI 호환)."""
    return {"choices": [{"message": {
        "role": "assistant", "content": None,
        "tool_calls": [{"id": cid, "type": "function", "function": {
            "name": name, "arguments": json.dumps(args, ensure_ascii=False)}}],
    }}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


def _text_turn(text: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


_OUT = json.dumps({
    "variables": [{
        "id": "A1", "type": "pitcher_state", "team": "team:000338",
        "claim": "선발이 확정됐다", "quote": "Logan Henderson will start",
        "url": URL, "published_at": (KICK - timedelta(hours=20)).isoformat(),
        "direction_hint": "home", "lang": "en", "conflict": False,
        "reverified": True}],
    "hypotheses": [], "scenarios": [], "gaps": [], "notes": [],
}, ensure_ascii=False)


class _Net:
    """🔴 Solar 대역 — **턴을 차례로** 돌려준다. 보낸 몸통을 전부 적는다."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.sent: list[dict] = []

    def __call__(self, url, key, body, timeout, retries):
        self.sent.append(body)
        return self.turns.pop(0) if self.turns else _text_turn("{}")


def test_v5_3_2_도구를_실제로_넘긴다():
    """🔴🔴 **첫 턴에 `tools` 가 실려야 한다** — 안 실리면 도구가 없다.

    ⚠️ 종전 `run()` 은 `schema` 만 넘겼다. 🔴 프롬프트가 *"도구로만 일한다"* 라고
       적었는데 도구가 없으면 모델이 **기억으로** 짓는다.
    """
    from app import agentloop
    net = _Net([_tool_turn("done", {"output": _OUT}), _text_turn(_OUT)])
    agentloop.run(_inp(), _ctx(), seen=_seen(), net=net)
    assert net.sent, "🔴 Solar 를 한 번도 안 불렀다"
    first = net.sent[0]
    names = [f["function"]["name"] for f in (first.get("tools") or [])]
    assert names == list(agentloop.TOOL_NAMES), (
        f"🔴 첫 턴에 도구를 안 넘겼다: {names}")
    # 🔴 §3-2 — **도구와 스키마를 함께 주지 않는다**
    assert "response_format" not in first, first.keys()


def test_v5_3_2_마지막_턴에만_스키마를_강제한다():
    """🔴 *"마지막 `done` 턴에서만 스키마를 강제한다"*(§3-2)."""
    from app import agentloop
    net = _Net([_tool_turn("done", {"output": "{}"}), _text_turn(_OUT)])
    agentloop.run(_inp(), _ctx(), seen=_seen(), net=net)
    assert len(net.sent) >= 2, len(net.sent)
    last = net.sent[-1]
    assert "response_format" in last, last.keys()
    assert "tools" not in last, "🔴 마지막 턴에 도구를 또 넘겼다"


def test_v5_3_2_search_결과를_에이전트에게_돌려준다():
    """🔴 도구 결과가 **대화에 들어가야** 한다 — 안 들어가면 못 읽는다."""
    from app import agentloop
    net = _Net([
        _tool_turn("search", {"query": "Milwaukee Brewers San Diego Padres "
                                       "MLB baseball", "lang": "en"}),
        _tool_turn("fetch", {"url": URL}, cid="c2"),
        _tool_turn("done", {"output": _OUT}, cid="c3"),
        _text_turn(_OUT)])
    got, why = agentloop.run(_inp(), _ctx(), seen=_seen(), net=net)
    # 🔴 두 번째 턴의 대화에 **도구 결과**가 들어 있다
    msgs = net.sent[1]["messages"]
    tool_msgs = [m for m in msgs if m.get("role") == "tool"]
    assert tool_msgs, [m.get("role") for m in msgs]
    assert URL in str(tool_msgs[0].get("content")), tool_msgs[0]
    # 🔴 `fetch` 결과에 **본문**이 들어 있다
    msgs2 = net.sent[2]["messages"]
    bodies = [m for m in msgs2 if m.get("role") == "tool"
              and "Henderson" in str(m.get("content"))]
    assert bodies, [str(m.get("content"))[:60] for m in msgs2
                    if m.get("role") == "tool"]
    # ✅ 그리고 **검증층을 지난 변수**가 나온다
    assert len(got) == 1, (got, why)


def test_v5_3_7_턴_상한이_있다():
    """🔴 §3-7 — 끝없이 돌지 않는다. ⚠️ 상한은 **yaml**(§2 도구 호출 상한)이다.

    🔴 모델이 `done` 을 안 부르면 예산이 터질 때까지 돈다 — 그 전에 멈춘다.
    """
    from app import agentloop
    # 🔴 `search` 만 무한히 부르는 모델
    net = _Net([_tool_turn("search", {"query": "Milwaukee Brewers San Diego "
                                               "Padres MLB baseball", "lang": "en"},
                           cid=f"c{i}") for i in range(200)])
    got, why = agentloop.run(_inp(), _ctx(), seen=_seen(), net=net)
    assert len(net.sent) <= agentloop.MAX_TURNS + 1, len(net.sent)
    assert got == []
    assert "턴" in why or "상한" in why or "중단" in why, why


def test_v5_3_7_추출_두_번_실패하면_멈춘다():
    """🔴 §3-7 — *"`done` 스키마 2회 실패"*. ⚠️ 그때까지의 변수로 §5 로 넘긴다.

    🔴 **사유 이름이 바뀌었다**(작업 지시서 §1 M47): `schema_fail` → **
       `done_parse_fail`**. ⚠️ 모델은 스키마를 **지켰고** 우리가 **못 꺼낸**
       경우가 실제로 있었다 — 그 둘을 한 사유로 적으면 고칠 곳이 섞인다.
    """
    from app import agentloop
    net = _Net([_tool_turn("done", {"output": "쓰레기"}),
                _text_turn("쓰레기도 아니다"),
                _text_turn("여전히 아니다"),
                _text_turn("세 번째")])
    got, why = agentloop.run(_inp(), _ctx(), seen=_seen(), net=net)
    assert got == []
    assert "done_parse_fail" in why, why


def test_v5_3_7_예산이_끊기면_사유를_남긴다():
    """🔴 §3-7 — 예산 소진. ⚠️ **그때까지의 변수**로 넘긴다(버리지 않는다)."""
    from app import agentloop, solar
    b = solar.MatchBudget()
    # 🔴 도구 상한을 **다 쓴 상태**로 만든다
    for _ in range(100):
        if not b.can_tool("search")[0]:
            break
        b.took_tool("search")
    net = _Net([_tool_turn("search", {"query": "Milwaukee Brewers San Diego "
                                               "Padres MLB baseball",
                                      "lang": "en"}),
                _tool_turn("done", {"output": _OUT}, cid="c2"),
                _text_turn(_OUT)])
    got, why = agentloop.run(_inp(), _ctx(), seen=_seen(), net=net, budget=b)
    # 🔴 예산이 끊겼어도 **`done` 은 돈다**(그때까지의 변수로 넘긴다)
    assert len(got) == 1, (got, why)
    msgs = net.sent[1]["messages"]
    tool_msgs = [m for m in msgs if m.get("role") == "tool"]
    # ⚠️ 사유는 **enum 값**으로 온다(`budget_cut`) — 한국어 글자가 아니다.
    #    🔴 §8-6: 사유는 사람이 쓴 문장이 아니라 **실패한 조건이 돌려준 코드**다.
    from app.reasons import Reason
    assert any(Reason.BUDGET_CUT.value in str(m.get("content"))
               for m in tool_msgs), tool_msgs


def test_v5_3_7_모델이_그냥_글을_내면_멈춘다():
    """⚠️ 도구도 안 부르고 글만 내면 **끝낸 것**이다 — 그 글로 스키마를 받는다."""
    from app import agentloop
    net = _Net([_text_turn("다 찾았다"), _text_turn(_OUT)])
    got, why = agentloop.run(_inp(), _ctx(), seen=_seen(), net=net)
    assert len(got) == 1, (got, why)


def test_v5_3_7_배선_카드가_에이전트를_부른다():
    """🔴🔴 **게이트 2** — `analyze` 가 `agentloop.run` 을 실제로 부른다(#2)."""
    import ast
    import inspect
    import textwrap

    from app import analyze
    src = textwrap.dedent(inspect.getsource(analyze))
    tree = ast.parse(src)
    # ══════════════════════════════════════════════════════════════════
    # 🔴 **`to_thread` 로 부른다** — 그래서 호출이 **인자**로 들어 있다
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `solar.chat` 은 **동기**다. 그대로 `await` 없이 부르면 그 몇 분 동안
    #     이벤트 루프가 멈추고 다른 세포가 아무것도 못 한다.
    #  🔴 `asyncio.to_thread(agentloop.run, …)` 는 `agentloop.run` 을
    #     **부르지 않고 넘긴다** — 그래서 `ast.Call` 이 아니라 `ast.Attribute` 다.
    refs = [n for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and n.attr == "run"
            and getattr(n.value, "id", "") == "agentloop"]
    assert refs, (
        "🔴 §3 에이전트를 만들어 두고 `analyze` 가 **안 부른다** — 게이트 2 가 "
        "안 켜졌다(CLAUDE.md #2)")
    # 🔴 그리고 **스레드로** 넘겨야 한다(루프를 멈추지 않게)
    assert "to_thread" in src, (
        "🔴 `solar.chat` 은 동기다 — `to_thread` 없이 부르면 이벤트 루프가 "
        "몇 분 멈춘다(다른 세포가 아무것도 못 한다)")


def test_v5_3_7_스위치가_있고_꺼짐이_기본이_아니다():
    """🔴 게이트 2 는 **사용자가 켠다** — 그 스위치가 설정에 있어야 한다.

    ⚠️ 비용이 발생하므로 코드가 혼자 켜지 않는다. 🔴 지금은 사용자 지시
       2026-10-04(*"게이트2 켜라"*)로 **켜져 있다**.
    """
    from app.config import get_settings
    s = get_settings()
    assert hasattr(s, "agent_enabled"), (
        "🔴 §3 에이전트 스위치가 설정에 없다 — 비용을 코드가 혼자 켠다")
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **`.env` 파일을 본다 — 프로세스 환경이 아니다**(2026-10-04)
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전엔 `s.agent_enabled is True` 였다. 🔴 그런데 스위트가 이 기계의
    #     `.env` 를 그대로 읽고 있었고(= 계약 결과가 기계 설정에 달렸다),
    #     결정 ③을 넣자 세포 검색 경로를 시험하는 **39건이 빨개졌다.**
    #  🔴 그래서 conftest 가 그 스위치를 **뽑는다**(`_unplug_env`). 묻는 것은
    #     여전히 같다 — *"사용자가 켰나"* — 그래서 **파일**을 본다.
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]
    said = (root / ".env").read_text(encoding="utf-8") \
        if (root / ".env").exists() else ""
    on = [ln for ln in said.splitlines()
          if ln.strip().startswith("AGENT_ENABLED=")
          and ln.split("=", 1)[1].strip().lower() in ("1", "true", "yes")]
    assert on, (
        "🔴 사용자가 게이트 2 를 켜라고 했다(2026-10-04) — `.env` 의 "
        "`AGENT_ENABLED` 가 꺼져 있다")


@pytest.mark.parametrize("name", ["search", "fetch", "done"])
def test_v5_3_2_모르는_도구는_사유를_돌려준다(name):
    """⚠️ 선언한 셋만 돈다. 🔴 모르는 이름은 **사유**이고 크래시가 아니다."""
    from app import agentloop
    tools = agentloop.Tools(inp=_inp(), seen=_seen())
    assert hasattr(tools, name) or name == "done"
    got = agentloop.call_tool(tools, "없는도구", {})
    assert got["ok"] is False and "모르는 도구" in got["why"], got


def test_v5_3_1_입구가_팀_열쇠를_넘긴다():
    """🔴🔴 **실측 2026-10-04 — 에이전트가 입구에서 막혔다.**

    게이트 2 를 켜고 돌린 첫 판:

    ```
    · 세포 에이전트:Milwaukee Brewers: 🔴 §3 에이전트 입력을 못 만들었다(§3-1):
      🔴 `home` 은 **열쇠**여야 한다(§8-1): ''
    ```

    🔴 `gather` 로 가는 `game` 에 **`home_id`·`away_id` 가 안 실려 있었다** —
       `answer` 는 `ref.home_id` 를 알고 있었는데 그 칸을 안 넘겼다.
    ⚠️ §3-1 이 열쇠를 요구하는 것은 **맞다**(1~3단계가 고친 병이 입구에서
       되살아나지 않게). 🔴 고칠 곳은 **넘기는 쪽**이다.

    ⚠️ 그리고 이 계약은 **`answer` 의 호출 모양**을 본다 — 그 자리가 입구다.
    """
    import ast
    import inspect
    import textwrap

    from app import analyze
    src = textwrap.dedent(inspect.getsource(analyze.answer))
    tree = ast.parse(src)
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "id", "") != "gather":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Dict):
                keys |= {k.value for k in arg.keys
                         if isinstance(k, ast.Constant)}
    assert keys, "🔴 `answer` 가 `gather` 를 사전으로 안 부른다"
    for need in ("home_id", "away_id"):
        assert need in keys, (
            f"🔴 §3-1 — `gather` 로 가는 `game` 에 `{need}` 가 없다. "
            f"에이전트가 **입구에서 막힌다**(실측 2026-10-04). 있는 칸: "
            f"{sorted(keys)}")


def test_v5_3_1_열쇠가_없으면_사유가_그_자리를_가리킨다():
    """🔴 §8-6 — 사유가 **고칠 곳**을 말해야 한다(이 결함을 그 사유가 찾았다)."""
    from app import agentloop
    import pytest as _pt
    with _pt.raises(ValueError) as got:
        agentloop.AgentInput(
            match_key="statsapi:1", home="", away="team:2",
            home_names=("a",), away_names=("b",), competition="MLB",
            sport="baseball", kickoff_utc=KICK, venue="", langs=("en",))
    said = str(got.value)
    assert "열쇠" in said and "home" in said, said


def test_v5_3_2_done_이_스키마를_인자로_받는다():
    """🔴🔴 **실측 2026-10-04 — 모델이 `done` 을 **한 번도** 안 불렀다.**

    에이전트만 돌려 보니(48턴):

    ```
    턴 1~17  search·fetch 를 잘 돈다(등급도 붙는다)
    턴 18    🔴 **도구 없이 글을 냈다** → 스키마 2회 실패 → 변수 0개
    ```

    🔴 까닭: `done` 의 인자가 **`{"output": "문자열"}`** 이었다. 모델은 그 문자열
       에 **무엇을 넣어야 하는지 모른다** — 스키마는 *다음* 턴에서야 보여 주는데
       그 턴이 오지 않는다(닭과 알이다).
    ✅ 고침: **`done` 의 인자를 스키마 그 자체로** 만든다. §3-2 의 *"마지막
       `done` 턴에서만 스키마를 강제한다"* 와 어긋나지 않는다 — 그 턴의 **인자**가
       스키마다.
    """
    from app import agentloop
    spec = next(t for t in agentloop.tool_specs()
                if t["function"]["name"] == "done")
    props = spec["function"]["parameters"]["properties"]
    # 🔴 **문자열 한 칸이 아니다** — §3-6 의 칸들이다
    assert "output" not in props, (
        "🔴 `done` 이 아직 문자열 한 칸을 받는다 — 모델이 무엇을 넣을지 모른다")
    assert "variables" in props, sorted(props)
    var = props["variables"]["items"]["properties"]
    for need in ("type", "team", "quote", "url", "published_at"):
        assert need in var, (need, sorted(var))


def test_v5_3_2_done_인자를_그대로_읽는다():
    """🔴 `done` 이 **사전**을 주면 그것을 그대로 쓴다(JSON 글자로 안 돌린다)."""
    from app import agentloop
    args = {"variables": [{
        "id": "A1", "type": "pitcher_state", "team": "team:000338",
        "claim": "c", "quote": "Logan Henderson will start", "url": URL,
        "published_at": (KICK - timedelta(hours=20)).isoformat(),
        "direction_hint": "home", "lang": "en"}]}
    got, why = agentloop.parse_args(args)
    assert len(got) == 1, (got, why)
    assert got[0].type == "pitcher_state"
    # ⚠️ 빈 사전은 **후보 0개**다(크래시 아니다)
    assert agentloop.parse_args({})[0] == []


def test_v5_3_2_프롬프트가_끝내는_법을_말한다():
    """🔴 모델이 **`done` 을 불러야 끝난다**는 것을 알아야 한다.

    ⚠️ §3-3 의 열 단계는 *무엇을 조사하나*이고 *어떻게 끝내나*는 **§3-2 규약**
       이다. 🔴 그것을 안 적으면 모델이 산문으로 끝낸다(실측 2026-10-04).
    """
    from app import agentloop
    said = agentloop.system_prompt()
    assert "done" in said, "🔴 프롬프트가 `done` 을 말하지 않는다"
    assert "끝" in said or "마치" in said, said[-300:]


def test_v5_3_2_산문_속_JSON_을_꺼낸다():
    """🔴🔴 **실측 2026-10-04 — 모델이 산문에 JSON 을 섞어 냈다.**

    로그가 그 모양을 보여 줬다:

    ```
    Stubs (공식 등급, hardness 2) returning probable pitchers … 변수·가설·
    시나리오를 구성한다.

    확보한 사실(스텁 본문 인용 가능):
    - Brewers probable starter: Michael King (home)

    ```json
    done({
      "variables": [ … ]
    ```
    ```

    🔴 `json.loads(전체)` 는 당연히 터진다(`Expecting ',' delimiter`). ⚠️ 그것을
       *"모델이 스키마를 못 지켰다"* 로 적으면 **거짓 사유**다 — 모델은 **지켰고**
       우리가 **못 꺼냈다**(§8-6 이 막는 거짓 사유다).
    🔴 꺼내는 것은 **해킹이 아니다**: 울타리(```json)와 `done(` 은 **모델이 흔히
       쓰는 꼴**이고, 그 안은 그냥 JSON 이다.
    """
    from app import agentloop
    body = ('{"variables": [{"id": "A1", "type": "pitcher_state", '
            '"team": "team:000338", "claim": "c", '
            '"quote": "Logan Henderson will start", "url": "%s", '
            '"published_at": "%s", "direction_hint": "home", "lang": "en"}]}'
            % (URL, (KICK - timedelta(hours=20)).isoformat()))
    for wrap in (
            body,
            f"설명 한 줄\n\n```json\n{body}\n```\n끝났다",
            f"```json\ndone({body})\n```",
            f"앞말 done({body}) 뒷말",
            f"```\n{body}\n```"):
        got, why = agentloop.parse_output(wrap)
        assert len(got) == 1, (wrap[:60], got, why)
    # 🔴 **JSON 이 아예 없으면** 그렇게 말한다(지어내지 않는다)
    none_, why2 = agentloop.parse_output("그냥 산문이다")
    assert none_ == [] and "JSON" in why2, why2


def test_v5_3_2_꺼내기가_거짓_사유를_없앤다():
    """🔴 §8-6 — *"모델이 스키마를 못 지켰다"* 와 *"우리가 못 꺼냈다"* 는 다르다."""
    from app import agentloop
    got, why = agentloop.parse_output("```json\n{\"variables\": []}\n```")
    # ⚠️ 변수 0개는 **꺼내기 실패가 아니다** — `agent_zero` 다
    assert got == []
    assert "JSON 이 아니다" not in why, why


def test_v5_3_6_팀_이름은_폐기한다_M48():
    """🔴🔴 **실측 2026-10-04 — 모델이 `team` 을 이름으로 썼다.**

    `done` 을 드디어 불렀는데(턴 16) 변수가 **전부 떨어졌다**:

    ```
    "team": "Milwaukee Brewers"      🔴 `AgentVar` 는 `team:000338` 을 요구한다
    ```

    ⚠️ 입력에 열쇠를 줬는데도 모델은 **이름**을 쓴다 — 자연스러운 일이다.
    🔴 §8-1 은 *"이름→ID 해석은 `resolve()` **한 곳에서만**"* 이라고 했다. 그
       한 곳이 여기다(에이전트 출력의 입구) — 그래서 **옮긴다**(거부하지 않는다).
    ⚠️ 어느 팀도 아니면 **그대로 둔다** — §5-4 다리가 `side_mismatch` 로 적는다.
    """
    from app import agentloop
    inp = _inp()
    args = {"variables": [
        {"id": "v1", "type": "pitcher_state", "team": "Milwaukee Brewers",
         "claim": "c", "quote": "Logan Henderson will start", "url": URL,
         "published_at": (KICK - timedelta(hours=20)).isoformat(),
         "direction_hint": "home", "lang": "en"},
        {"id": "v2", "type": "recent_pattern", "team": "Padres",
         "claim": "c", "quote": "Logan Henderson will start", "url": URL,
         "published_at": (KICK - timedelta(hours=20)).isoformat(),
         "direction_hint": "away", "lang": "en"}]}
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **작업 지시서 §1 M48 이 이 계약을 뒤집었다**(2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 나는 이름을 **열쇠로 옮겼다**. 🔴 지시서는 *"이름이면 그 항목 **폐기**
    #     `name_not_key`"* 다(돌연변이도 *"이름 수용하게 바꾸기"*).
    #  🔴 왜 폐기가 맞나: 옮기면 모델의 그 버릇이 **숨는다.** 폐기하면 수가
    #     쌓이고 프롬프트를 고칠 근거가 된다.
    got, why = agentloop.parse_args(args, inp=inp)
    assert got == [], (got, why)
    assert "name_not_key" in why, why
    # ⚠️ **열쇠면** 받는다(반대 증거)
    args2 = {"variables": [dict(args["variables"][0], team=inp.home)]}
    got2, _ = agentloop.parse_args(args2, inp=inp)
    assert got2[0].team == inp.home


def test_v5_3_6_모르는_팀은_그대로_두고_사유가_남는다():
    """🔴 어느 팀도 아니면 **지어내지 않는다** — 다리가 `side_mismatch` 로 적는다."""
    from app import agentloop
    inp = _inp()
    args = {"variables": [
        {"id": "v1", "type": "pitcher_state", "team": "New York Yankees",
         "claim": "c", "quote": "Logan Henderson will start", "url": URL,
         "published_at": (KICK - timedelta(hours=20)).isoformat(),
         "direction_hint": "home", "lang": "en"}]}
    got, why = agentloop.parse_args(args, inp=inp)
    # ⚠️ 꼴이 틀려 **떨어진다**(열쇠가 아니다) — 그 사실이 사유에 남는다
    assert got == [] and "꼴이 틀린" in why, (got, why)


def test_v5_3_6_떨어진_줄_수를_사유가_말한다():
    """🔴 §3 — **조용한 0 금지.** 몇 줄이 왜 떨어졌는지 말해야 한다.

    ⚠️ 실측 2026-10-04: 사유가 *"후보 0개"* 였고 **열한 줄이 `team` 꼴 때문에
       떨어진 것**을 말하지 않았다 — 그래서 내가 한참 헤맸다.
    """
    from app import agentloop
    args = {"variables": [
        {"id": f"v{i}", "type": "pitcher_state", "team": "엉뚱한팀",
         "claim": "c", "quote": "q", "url": URL,
         "published_at": (KICK - timedelta(hours=20)).isoformat(),
         "direction_hint": "home", "lang": "en"} for i in range(3)]}
    got, why = agentloop.parse_args(args, inp=_inp())
    assert got == []
    assert "3개" in why, why


def test_v5_3_3_프롬프트가_열쇠를_요구한다():
    """🔴 모델에게 **열쇠를 쓰라**고 적어야 한다(그래도 이름을 쓰면 옮긴다)."""
    from app import agentloop
    said = agentloop.system_prompt()
    assert "team:" in said, said[-400:]


def test_v5_3_2_fetch_가_본문을_좁혀_준다():
    """🔴🔴 **실측 2026-10-04 — 경기당 입력 예산이 터졌다.**

    ```
    budget_cut: 경기당 입력 161475/150000 토큰 · `done`(턴 16)
    ```

    ⚠️ 턴마다 받은 본문이 **통째로** 대화에 쌓인다 — 16턴이면 150k 를 넘는다.
    🔴 고침은 §readtext 가 이미 아는 것이다: *"팀·선수 이름이 나오는 문단만
       BM25 로 골라 넘긴다. **입력이 짧아야 8B 모델도 정확하다.**"* 그 말은
       Solar 에게도 맞고 **예산에도** 맞는다.
    ⚠️ **자른 것을 숨기지 않는다** — 몇 자에서 몇 자로 줄였는지 적는다(#3).
    """
    from app import agentloop
    from app.cells import Seen
    long = ("Milwaukee Brewers manager Pat Murphy said Logan Henderson will "
            "start on Saturday. ") + ("광고와 메뉴가 길게 이어진다. " * 400)
    seen = Seen()
    seen.add_hit(URL, title="t", snippet="s", query="q")
    seen.add_body(URL, long)
    tools = agentloop.Tools(inp=_inp(), seen=seen)
    tools.search("Milwaukee Brewers San Diego Padres MLB baseball")
    got = tools.fetch(URL)
    assert got["ok"] is True, got
    body = str(got["body"])
    assert len(body) < len(long), (len(body), len(long))
    # 🔴 **중요한 문장은 남아야** 한다(좁히는 것이 버리는 것이 아니다)
    assert "Henderson" in body, body[:200]
    # 🔴 **줄인 사실을 적는다**(#3 조용한 0 금지)
    assert "자" in str(got["why"]) and str(len(long)) in str(got["why"]), got["why"]
    # ⚠️ 짧은 본문은 **그대로** 준다
    seen.add_body("https://a/short", "Henderson will start on Saturday.")
    seen.add_hit("https://a/short", title="t", snippet="s", query="q")
    tools.search("Milwaukee Brewers San Diego Padres baseball MLB preview")
    got2 = tools.fetch("https://a/short")
    assert got2["body"] == "Henderson will start on Saturday."


def test_v5_3_2_상한이_yaml_에_있다():
    """🔴 좁히는 길이를 코드에 박지 않는다. ⚠️ §4-5 가 상한을 적었다."""
    from app import agentloop, cells
    assert agentloop.AGENT_BODY_CHARS <= cells.EXTRACT_MAX_CHARS
    assert agentloop.AGENT_BODY_CHARS >= 1_000
