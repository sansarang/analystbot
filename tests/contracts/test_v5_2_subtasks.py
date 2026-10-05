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
    from app.research import subtasks
    got = subtasks.split(_ref())
    for s in got:
        assert s.budget.search_cap == 3, s.budget.search_cap
        assert s.budget.fetch_cap == 2, s.budget.fetch_cap
        assert s.budget.out_cap == 4000, s.budget.out_cap
        assert s.budget.turns == 8, s.budget.turns
    # 🔴 **합계가 기존 상한 그대로**여야 한다(지시서 §2)
    assert sum(s.budget.search_cap for s in got) == 24
    assert sum(s.budget.fetch_cap for s in got) == 16
    assert sum(s.budget.out_cap for s in got) == 32000


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
            and n.value in (3, 2, 4000, 8, 24, 16, 32000)}
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
