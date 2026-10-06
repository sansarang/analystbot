"""🔴🔴 **§2 — 하위 과제 분할·예산·병렬**(지시서 2026-10-05 딥서치 재구축).

> 경기 하나 = **하위 과제 8개**(유형군 4 × 홈/원정). `subtasks.py` 가 이 표를
> **데이터로** 갖고, 경기 입력에서 하위 과제 목록을 만든다.
> `recent_pattern`·`h2h` 는 구조 사실(어댑터)에서 오므로 **넣지 않는다.**

| 하위 | 유형군 | 카탈로그 유형 | 씨앗 질의(영어 1차) | 2차 언어 |
|---|---|---|---|---|
| A-홈/A-원정 | 결장·선발 | `absence_def`·`absence_att`·`pitcher_state` | `{팀} {상대} injury news` (야구: `{팀} starting pitcher news`) | 팀 현지어 |
| B-홈/B-원정 | 로테이션·감독 | `lineup_rotation`·`coach_intent`·`coach_conflict`·`coach_change` | `{팀} lineup rotation` → 감독명 확보 시 `{감독} press conference` | 〃 |
| C-홈/C-원정 | 동기·순위·흐름 | `stakes`·`individual_title`·`regression`·`team_stats` | `{팀} {대회} standings stakes` | 〃 |
| D-홈/D-원정 | 일정·경기외 | `travel_schedule`·`venue_weather`·`event_match`·`match_type`·`national_duty_return` | `{팀} schedule travel {대회}` | 〃 |

예산(합계는 기존 상한 그대로): 하위 1개 `search 3`·`fetch 2`·출력 `4,000`·턴 `8` ·
8개 합 `24`/`16`/`32,000` · 2차 예비(리드) 미사용분 + 출력 `8,000`.
"""
from __future__ import annotations

import ast
import inspect


def _ref():
    """🔴 경기 입력 대역 — 실제 경로가 주는 모양만 든다."""
    import datetime as dt
    return {
        "home": "France", "away": "Belgium",
        "home_key": "team:000081", "away_key": "team:000021",
        "sport": "soccer", "league": "UEFA Nations League A Grp. 1",
        "langs": ("en", "fr"),
        "kickoff_utc": dt.datetime(2026, 10, 5, 18, 45,
                                   tzinfo=dt.timezone.utc),
        "venue": "Stade de France",
    }


# ══════════════════════════════════════════════════════════════════
# 분할 — 유형군 4 × 홈/원정 = 8
# ══════════════════════════════════════════════════════════════════
def test_r2_하위가_여덟이다():
    from app.research import subtasks
    got = subtasks.split(_ref())
    assert len(got) == 8, f"🔴 하위가 {len(got)}개다(8이어야 한다): " \
                          f"{[s.name for s in got]}"
    names = [s.name for s in got]
    assert names == ["A-홈", "A-원정", "B-홈", "B-원정",
                     "C-홈", "C-원정", "D-홈", "D-원정"], names


def test_r2_유형군이_표에서_온다():
    """🔴 유형 이름을 **코드에 적지 않는다** — 표가 데이터다(#1 사본 금지)."""
    from app.research import subtasks
    assert hasattr(subtasks, "GROUPS"), "🔴 `GROUPS` 표가 없다"
    keys = [g["key"] for g in subtasks.GROUPS]
    assert keys == ["A", "B", "C", "D"], keys
    kinds = {k for g in subtasks.GROUPS for k in g["kinds"]}
    # 🔴 지시서 표가 이름을 **그대로 줬다** — 지어낸 것이 아니다
    for want in ("absence_def", "absence_att", "pitcher_state",
                 "lineup_rotation", "coach_intent", "coach_conflict",
                 "coach_change", "stakes", "individual_title", "regression",
                 "team_stats", "travel_schedule", "venue_weather",
                 "event_match", "match_type", "national_duty_return"):
        assert want in kinds, f"🔴 표에 `{want}` 가 없다"
    # 🔴 **구조 사실에서 오는 것은 하위에 안 넣는다**(지시서 §2)
    for never in ("recent_pattern", "h2h_pattern"):
        assert never not in kinds, (
            f"🔴 `{never}` 는 어댑터 구조 사실이다 — 하위 과제에 넣지 않는다")


def test_r2_씨앗_질의가_세_낱말에서_여섯_낱말이다():
    """🔴 §4: *"1차(씨앗) … **3~6단어**"* — 긴 질의가 결과를 죽였다."""
    from app.research import subtasks
    for s in subtasks.split(_ref()):
        n = len(s.seed.split())
        assert 3 <= n <= 6, f"🔴 `{s.name}` 씨앗이 {n}낱말이다: {s.seed!r}"


def test_r2_야구는_선발_투수_씨앗을_쓴다():
    """🔴 표가 *"(야구: `{팀} starting pitcher news`)"* 라고 적었다."""
    from app.research import subtasks
    ref = dict(_ref(), sport="baseball", home="Chiba Lotte Marines",
               away="Seibu Lions", league="NPB")
    a = [s for s in subtasks.split(ref) if s.name.startswith("A-")]
    assert a and all("pitcher" in s.seed for s in a), [s.seed for s in a]


def test_r2_하위마다_팀과_자리가_있다():
    """🔴 `{팀}` 은 별칭표의 **영어 짧은 표기**(열쇠 아님) — 출력 `team` 칸은 열쇠."""
    from app.research import subtasks
    got = subtasks.split(_ref())
    for s in got:
        assert s.side in ("home", "away"), s.side
        assert s.team and not s.team.startswith("team:"), (
            f"🔴 질의용 팀이 **열쇠**다({s.team!r}) — 질의는 글자다")
        assert s.team_key.startswith("team:"), (
            f"🔴 `team_key` 가 열쇠가 아니다({s.team_key!r}) — M48")


# ══════════════════════════════════════════════════════════════════
# M59 — 하위 예산은 **독립 객체**
# ══════════════════════════════════════════════════════════════════
def test_M59_하위_예산이_독립이다():
    """🔴 한 하위의 소진이 다른 하위의 `can_call` 을 바꾸지 않는다.

    ⚠️ 실측 2026-10-04: 한 팀 에이전트가 예산을 다 써서 **다른 쪽이 0개**였다.
    """
    from app.research import subtasks
    got = subtasks.split(_ref())
    first, second = got[0], got[1]
    assert first.budget is not second.budget, (
        "🔴 하위 둘이 **같은 예산 객체**를 본다 — 공유 카운터 금지(M59)")
    first.budget.spend_out(first.budget.out_cap)
    assert not first.budget.can_call(), "🔴 다 썼는데 아직 부를 수 있다"
    assert second.budget.can_call(), (
        "🔴 한 하위가 다 쓰자 **다른 하위도 막혔다** — 그것이 M59 가 막는 것이다")


def test_M59_예산_수가_표와_맞는다():
    """🔴 수는 **표가 든다** — 계약은 *표와 코드가 같은가*만 센다(#1 사본 금지).

    ⚠️ 종전엔 `4000`·`32000` 을 박아 뒀다. 🔴 사용자가 2026-10-06 ③ 에서
       하위 **8,000** 으로 올리자 이 계약이 빨개졌다 — 그 빨강은 결함이 아니라
       **사본이 늦은 것**이었다.
    """
    from app import rules
    from app.research import subtasks
    want = rules.llm_budget()["per_subtask"]
    tot = rules.llm_budget()["per_match"]
    got = subtasks.split(_ref())
    for s in got:
        assert s.budget.search_cap == int(want["search"]), s.budget.search_cap
        assert s.budget.fetch_cap == int(want["fetch"]), s.budget.fetch_cap
        assert s.budget.out_cap == int(want["output_tokens"]), s.budget.out_cap
        assert s.budget.turns == int(want["turns"]), s.budget.turns
    # 🔴 **합계가 경기 상한과 맞는가**(지시서 §2: "분할이 상한을 늘리지 않는다")
    calls = tot["tool_calls"]
    assert sum(s.budget.search_cap for s in got) == int(calls["search"])
    assert sum(s.budget.fetch_cap for s in got) == int(calls["fetch"])
    # 🔴🔴 **하위 합계 + 2차 예비 = 경기 상한** — 지시서 §1 표가 그 셋을 줬다.
    #    ⚠️ 종전 이 줄은 *"하위 합계 == 경기 상한"* 이었다. 🔴 지시서
    #       2026-10-06 §1 이 하위 4,000(×8 = 32,000)과 2차 예비 8,000 으로
    #       되돌렸다 — 둘을 더해 40,000 이다.
    want_sum = int(want["output_tokens"]) * len(got)
    spare = int(want.get("second_output_tokens") or 0)
    assert want_sum + spare == int(tot["output_tokens"]), (
        f"🔴 하위 합계({want_sum}) + 2차 예비({spare}) 가 경기 상한"
        f"({tot['output_tokens']}) 과 안 맞는다 — 지시서 §1 표를 본다")
    assert sum(s.budget.out_cap for s in got) == want_sum


def test_M59_예산_수를_코드에_안_박았다():
    """🔴 수는 `config/llm.yaml` 이 든다 — 지시서 §2: *"전부 설정에 상수로"*."""
    from app.research import subtasks
    src = inspect.getsource(subtasks)
    tree = ast.parse(src)
    # ⚠️ **예산 수**만 센다 — `COMP_WORDS_IN_SEED = 2` 처럼 예산이 아닌 수는
    #    여기 있어도 된다(그것은 §4 낱말 규칙이고 설정 칸이 아니다).
    #    🔴 그래서 **예산 함수 안**만 본다.
    fn = [n for n in ast.walk(tree)
          if isinstance(n, ast.FunctionDef) and n.name == "_budget"]
    assert fn, "🔴 `_budget` 을 못 찾았다"
    nums = {n.value for n in ast.walk(fn[0])
            if isinstance(n, ast.Constant) and isinstance(n.value, int)
            and n.value in (3, 2, 8000, 8, 24, 16, 64000)}
    assert not nums, (
        f"🔴 예산 수를 코드에 박았다{sorted(nums)} — 설정에서 읽어라")
    # 🔴 그리고 `_budget` 이 **설정을 읽는다**(#2 배선)
    called = {n.func.attr for n in ast.walk(fn[0])
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "budget_cfg" in called, (
        f"🔴 `_budget` 이 설정을 안 읽는다(부르는 것: {sorted(called)})")


# ══════════════════════════════════════════════════════════════════
# M63 — **병렬 격리**: 하위 1개가 터져도 나머지 7개가 병합에 들어간다
# ══════════════════════════════════════════════════════════════════
#
#  > `asyncio.gather(*subtasks, return_exceptions=True)` — 하위 하나의
#  > 예외·타임아웃·`budget_cut` 이 **다른 하위를 멈추지 않는다**(M63).
#  > 실패 하위는 장부에 `searched`(빈손) 또는 **사유 코드**로 남긴다.
def test_M63_하위_하나가_터져도_나머지가_산다():
    import asyncio

    from app.research import lead

    async def ok(i):
        return {"variables": [{"id": f"v{i}"}]}

    async def boom(_i):
        raise RuntimeError("일부러 터뜨린다")

    async def main():
        jobs = [ok(i) if i != 3 else boom(i) for i in range(8)]
        return await lead.run_all(jobs)

    got, bad = asyncio.run(main())
    assert len(got) == 7, f"🔴 산 하위가 {len(got)}개다(7이어야 한다)"
    assert len(bad) == 1 and "터뜨린다" in str(bad[0]), bad
    # 🔴 **사유로 남긴다**(#3) — 조용히 사라지지 않는다
    assert bad[0] is not None


def test_M63_gather_가_예외를_삼키게_설정됐다():
    """🔴 **배선**(#2) — `return_exceptions=True` 가 걸려 있다."""
    import ast
    import inspect

    from app.research import lead
    tree = ast.parse(inspect.getsource(lead))
    hit = []
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "gather"):
            hit += [k.arg for k in n.keywords]
    assert "return_exceptions" in hit, (
        "🔴 `gather(return_exceptions=True)` 가 없다 — 하위 하나가 터지면 "
        "나머지 일곱이 함께 죽는다(M63)")


# ══════════════════════════════════════════════════════════════════
# M66 — **동시성 가드**: SearXNG ≤3 · fetch ≤4 · Solar ≤4
# ══════════════════════════════════════════════════════════════════
def test_M66_동시성_상수가_설정에서_온다():
    from app.research import lead
    box = lead.limits()
    assert box["searx"] == 3 and box["fetch"] == 4, box
    assert box["solar"] == 4 and box["solar_after_429"] == 2, box
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(lead.limits))
    nums = {n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, int)}
    assert not (nums & {3, 4, 2}), (
        f"🔴 동시성 수를 코드에 박았다{sorted(nums)} — 설정에서 읽어라")


def test_M66_세마포어가_실제로_동시_호출을_묶는다():
    """🔴 **돌려서** 본다 — 여덟이 한꺼번에 들어가도 셋만 동시에 돈다."""
    import asyncio

    from app.research import lead
    peak = {"now": 0, "max": 0}

    async def job():
        async with lead.gate("searx"):
            peak["now"] += 1
            peak["max"] = max(peak["max"], peak["now"])
            await asyncio.sleep(0.02)
            peak["now"] -= 1

    async def main():
        await asyncio.gather(*[job() for _ in range(8)])

    asyncio.run(main())
    assert peak["max"] <= 3, (
        f"🔴 SearXNG 동시 호출이 {peak['max']}개였다 — 상한 3(M66)")
    assert peak["max"] >= 2, (
        f"🔴 동시성이 {peak['max']}개다 — 병렬이 아니라 직렬이다")


def test_r2_운영_경기_dict_에서_열쇠를_읽는다():
    """🔴 **실측으로 고쳤다** — 운영 `game` dict 는 `home_id`/`away_id` 다.

    ⚠️ 실사고 2026-10-05: `split` 이 `home_key`/`away_key` 만 봐서 `team_key`
       가 **빈 문자열**이었다. 장부가 `A/` 처럼 **열쇠 없는 칸**을 적었고,
       그러면 `found` 가 어느 팀 것인지 알 수 없다(M48).
    🔴 두 이름을 **다 받는다** — 호출부가 둘을 쓴다.
    """
    from app.research import subtasks
    ops = {"home": "Portugal", "away": "Norway",
           "home_id": "team:000191", "away_id": "team:000174",
           "sport": "soccer", "league": "UEFA Nations League A Grp. 4",
           "langs": ("pt", "en")}
    for t in subtasks.split(ops):
        assert t.team_key.startswith("team:"), (
            f"🔴 `{t.name}` 의 `team_key` 가 비었다({t.team_key!r}) — 운영 "
            f"dict 는 `home_id`/`away_id` 를 쓴다")
        assert t.opp_key.startswith("team:"), t.opp_key


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **하위 상한이 실제로 걸린다** — 실측 2026-10-05 (인도네시아–태국)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실사고: 하위 예산을 만들어 뒀는데 **아무도 안 썼다.**
#
#    ```
#    fetch 98회(상한 16) · 에이전트 턴 257회 · 경기당 벽시계 11분(상한 6분)
#    하위 표: | A-홈 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |   ← 전부 0
#    ```
#
#  🔴 에이전트는 `MatchBudget`(경기 합계 24/16)을 보고 `Subtask.budget`
#     (3/2)은 **센 적이 없다**. M59 계약은 *"독립 객체"* 만 봤고 **집행**을
#     안 봤다 — 그것이 내 계약의 구멍이었다.
def _tools(sub=None):
    import datetime as dt

    from app import agentloop, solar
    inp = agentloop.AgentInput(
        match_key="fotmob:1", home="team:000108", away="team:000111",
        kickoff_utc=dt.datetime(2026, 10, 5, 13, 0, tzinfo=dt.timezone.utc),
        home_names=("Indonesia",), away_names=("Thailand",),
        competition="FIFA ASEAN Cup Premier Division", sport="soccer",
        subtask=sub)
    # 🔴 **실제 배선과 같게** 넘긴다 — `analyze` 가 `subtask=` 를 준다
    return agentloop.Tools(inp, budget=solar.MatchBudget(
        side=True, subtask=sub,
        subtask_out=(sub.budget.out_cap if sub is not None else 0)))


def test_M59_하위_도구_상한이_실제로_걸린다():
    from app.research import subtasks
    sub = subtasks.split({"home": "Indonesia", "away": "Thailand",
                          "home_id": "team:000108", "away_id": "team:000111",
                          "sport": "soccer", "league": "FIFA ASEAN Cup",
                          "langs": ("en", "id")})[0]
    tools = _tools(sub)
    # 🔴 `search` 는 **3번**이다(하위 상한) — 경기 합계 24 가 아니다
    for i in range(sub.budget.search_cap):
        ok, why = tools.budget.can_tool("search")
        assert ok, f"🔴 {i + 1}번째 search 가 막혔다: {why}"
        tools.budget.took_tool("search")
    ok, why = tools.budget.can_tool("search")
    assert not ok, (
        f"🔴 하위 상한 {sub.budget.search_cap}회를 넘겼는데 안 막는다 — "
        f"실측 2026-10-05: fetch 가 98회였다(상한 16)")
    assert str(sub.budget.search_cap) in why, why


def test_M59_하위_fetch_상한도_걸린다():
    from app.research import subtasks
    sub = subtasks.split({"home": "Indonesia", "away": "Thailand",
                          "home_id": "team:000108", "away_id": "team:000111",
                          "sport": "soccer", "league": "FIFA ASEAN Cup",
                          "langs": ("en",)})[0]
    tools = _tools(sub)
    for _ in range(sub.budget.fetch_cap):
        assert tools.budget.can_tool("fetch")[0]
        tools.budget.took_tool("fetch")
    assert not tools.budget.can_tool("fetch")[0], (
        f"🔴 하위 fetch 상한 {sub.budget.fetch_cap} 을 안 막는다")


def test_M59_쓴_것이_하위_객체에_기록된다():
    """🔴 하위 표가 **0 이 아니어야** 한다 — 안 적으면 보고가 거짓이다(#3)."""
    from app.research import subtasks
    sub = subtasks.split({"home": "Indonesia", "away": "Thailand",
                          "home_id": "team:000108", "away_id": "team:000111",
                          "sport": "soccer", "league": "FIFA ASEAN Cup",
                          "langs": ("en",)})[0]
    tools = _tools(sub)
    tools.budget.took_tool("search")
    tools.budget.took_tool("fetch")
    assert sub.budget.search_used == 1, (
        f"🔴 `Subtask.budget.search_used` 가 {sub.budget.search_used} 다 — "
        f"하위 표가 영원히 0 이다(실측 2026-10-05)")
    assert sub.budget.fetch_used == 1, sub.budget.fetch_used


def test_M59_턴_상한도_하위_것이다():
    """🔴 §2 표: *"턴 8 — 하위당 6(2차)"*. ⚠️ 턴 257회가 11분을 만들었다."""
    from app import agentloop
    import ast
    import inspect
    import textwrap
    src = textwrap.dedent(inspect.getsource(agentloop.run))
    tree = ast.parse(src)
    # 🔴 `limit` 가 **하위 것**을 보는지 — `max_turns()` 만 보면 안 된다
    said = ast.dump(tree)
    assert "subtask" in said and "turns" in said, (
        "🔴 턴 상한이 하위 예산(`subtask.budget.turns`)을 **안 본다** — "
        "하위 8개가 각각 전체 턴 상한을 쓴다(실측: 턴 257회 · 11분)")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **예산에 막힌 하위는 2차 보충 대상** — 사용자 지시 2026-10-06 ③
# ══════════════════════════════════════════════════════════════════
#
# > 한 팀 하위 4개 중 **하나라도 `budget_cut`** 이면 2차 보충 대상.
#
# ⚠️ 실측 2026-10-06(북아일랜드–조지아): 조지아 쪽 하위가 `6744/4000` 으로
#    막혀 판정층 변수 **0개**였다. 🔴 그런데 2차 대상 판정은 상태(`searched`)만
#    보고 **왜** 비었는지는 보지 않았다.


def test_wo3_예산에_막히면_그_사실이_남는다():
    """🔴 `can_call` 이 거부를 **기록**해야 한다 — 돌려주기만 하면 사라진다(#3)."""
    from app import solar
    b = solar.MatchBudget(subtask_out=8_000)
    assert b.cut_why == "", b.cut_why
    b.output_tokens = 8_000
    ok, why = b.can_call()
    assert ok is False and why, why
    assert b.cut_why == why, (
        "🔴 막힌 사실이 **남지 않는다** — 2차 보충이 그것을 고를 수 없다")
    # 🔴 **어느 벽인지 이름으로** 적는다(종전엔 하위 상한에 막혀도 "경기당"이었다)
    assert "하위" in why, (
        f"🔴 하위 상한에 막혔는데 그 이름이 없다 — 고칠 곳을 가린다: {why}")
    # 🔴 첫 사유를 **덮지 않는다** — 그것이 원인이다
    b.input_tokens = 10 ** 9
    b.can_call()
    assert b.cut_why == why, b.cut_why


def test_wo3_막힌_하위가_2차_대상이다():
    """🔴🔴 상태가 `searched`(= 변수를 냈다)여도 **막혔으면** 2차를 돈다."""
    from app.research import lead as _lead
    from app import ledgerbook as _lb
    assert "budget_cut" in _lead.SECOND_STATES, _lead.SECOND_STATES
    book = _lb.Book()
    # ── 하위 A: 변수를 냈고 **막혔다** → 2차 대상
    # ── 하위 B: 변수를 냈고 막히지 않았다 → 2차 **아님**
    _lead.write_book(book, [
        {"group": "A", "team_key": "team:1", "searched": 3,
         "variables": [object()], "verified": 1,
         "budget_cut": "budget_cut: 하위 출력(추론 포함) 6744/4000 토큰"},
        {"group": "B", "team_key": "team:1", "searched": 3,
         "variables": [object()], "verified": 1, "budget_cut": ""},
    ])
    assert book.state("A", "team:1") == "budget_cut", book.cells
    assert book.state("B", "team:1") == "found", book.cells
    again = _lead.second_round(book, ["A", "B"], ["team:1"])
    assert ("A", "team:1") in again, again
    assert ("B", "team:1") not in again, (
        "🔴 막히지 않고 찾은 칸을 2차로 또 돈다 — 예산을 버린다")
    # 🔴 **사유가 남는다**(#3) — 왜 2차 대상인지
    said = (getattr(book, "whys", {}) or {}).get(("A", "team:1")) or ""
    assert "예산" in said, said


def test_wo3_장부를_2차_판정_전에_쓴다():
    """🔴🔴 **순서가 뜻이다** — 실측 2026-10-06.

    ⚠️ 종전 `analyze` 는 `second_round`(장부 읽기) **뒤에** 1차 결과를 썼다.
       🔴 그래서 2차 판정이 **빈 장부**를 보고 늘 네 칸 전부를 골랐고,
       `found` 배선(§3-2)이 2차에 아무 영향도 못 줬다
       (로그: `2차 보충 4칸 — A/… · B/… · C/… · D/…` — 한 팀 전부).
    """
    import inspect

    from app import analyze
    from tests._helpers import strip_docs
    src = strip_docs(inspect.getsource(analyze.gather))
    at_write = src.find("write_book")
    at_second = src.find("second_round")
    assert at_write > 0 and at_second > 0, (at_write, at_second)
    assert at_write < at_second, (
        "🔴 `second_round` 가 **1차 장부를 쓰기 전에** 돈다 — 빈 장부를 보고 "
        "네 칸 전부를 2차로 돌린다(실측 2026-10-06)")


def test_wo_하위_표의_출력_토큰이_0이_아니다():
    """🔴🔴 **보고가 거짓이던 자리** — 실측 2026-10-06.

    사용자 지시 2026-10-06 은 *"하위별 표(**출력 토큰**·budget_cut 여부)"* 를
    요구했다. 🔴 그런데 여덟 하위 **전부 0** 이었다 — `SubBudget.spend_out` 이
    **아무 데서도 안 불리는 죽은 코드**였다(#2 배선).

    ⚠️ `took_tool` 은 하위 객체에 적는다(그래서 `search`·`fetch` 칸은 맞았다).
       🔴 토큰만 빠져 있었고, 표는 그 빈칸을 **0 으로** 보여 줬다(#3).
    """
    from app import solar
    from app.research import subtasks
    one = subtasks.split(_ref())[0]
    bud = solar.MatchBudget(subtask=one, subtask_out=one.budget.out_cap)
    assert one.budget.out_used == 0
    bud.took({"prompt_tokens": 100, "completion_tokens": 1234})
    assert one.budget.out_used == 1234, (
        f"🔴 하위 출력 토큰이 **안 쌓인다**({one.budget.out_used}) — 보고의 "
        f"토큰 칸이 영원히 0 이다")
    # 🔴 두 번 부르면 **더해진다**(덮지 않는다)
    bud.took({"prompt_tokens": 1, "completion_tokens": 6})
    assert one.budget.out_used == 1240, one.budget.out_used
    # 🔴 도구 칸도 같은 길로 쌓인다(이쪽은 전부터 됐다 — 반대 증거)
    bud.took_tool("search")
    assert one.budget.search_used == 1, one.budget.search_used
