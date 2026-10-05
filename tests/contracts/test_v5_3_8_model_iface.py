"""🔴🔴 **v5 §3-8 모델 인터페이스 — M47~M52.** 10-04 게이트2 세션의 실측을 규칙으로.

작업 지시서 §1 원문:

> 10-04 세션에서 실측으로 알아낸 Solar 의 버릇은 **문서에 없던 지식**이다.
> v5 §3 에 **§3-8 모델 인터페이스**로 적고, 각 항목을 `tests/contracts/` 의
> 계약 **M47~M52** 로 만든다.

| 번호 | 규칙 |
|---|---|
| **M47** | `done` 은 **구조화 인자**로 선언하고, 산문 속 ```json `done({…})` 꼴도 루프가 **블록을 추출**해 수용한다. 추출 실패 2회면 중단 사유 `done_parse_fail` |
| **M48** | 에이전트 출력의 모든 `team` 칸은 **열쇠만**. 이름이면 그 항목 **폐기** `name_not_key` |
| **M49** | 예산은 **캐시/비캐시 입력을 분리 단가**로 센다. 원장 매 줄에 `in`·`cache`·`out` 토큰과 USD **필수** — `None` 이면 기록 실패 |
| **M50** | 에이전트가 만든 카드 줄은 **✅·이모지·기호로 시작하지 않는다** + 카드 파이프라인은 **접두 기호로 줄을 거르지 않는다** |
| **M51** | `AgentInput` 에 `home_id`·`away_id` **필수**. 없으면 에이전트 호출 **전에** 실패 |
| **M52** | 검색어 짐작의 날짜 인식은 **달+일·달+연도·ISO 전부** |

══════════════════════════════════════════════════════════════════
🔴🔴 **둘은 이 세션에서 내가 한 것을 뒤집는다**
══════════════════════════════════════════════════════════════════

**M48** — 나는 이름을 **열쇠로 옮겼다**(`_team_key`). 🔴 지시서는 *"이름이면 그
항목 **폐기**"* 다. 돌연변이도 *"이름 수용하게 바꾸기"* 다. → **옮기기를
걷는다.** ⚠️ 그러면 모델이 이름을 쓰면 변수가 0개가 되지만, 그 사실이
`name_not_key` 로 **보인다** — 옮기면 그 버릇이 숨는다.

**M50** — 나는 `state_shown` 이 **표시(🔴·⚠️·✅)로** 줄을 골랐다. 🔴 지시서는
*"카드 파이프라인은 **접두 기호로 줄을 거르지 않는다**"* 다. → **기호 판정을
걷는다.** ⚠️ 그리고 에이전트 줄이 `✅` 로 시작하지 않아야 한다(둘 다 계약).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

KICK = datetime.now(timezone.utc) + timedelta(hours=2)
URL = "https://www.mlb.com/brewers/news/rotation"


def _inp():
    from app import agentloop
    return agentloop.AgentInput(
        match_key="statsapi:849825", home="team:000338", away="team:000325",
        home_names=("Milwaukee Brewers", "Brewers"),
        away_names=("San Diego Padres", "Padres"), competition="MLB",
        sport="baseball", kickoff_utc=KICK, venue="", langs=("en",))


def _row(**kw):
    base = {"id": "v1", "type": "pitcher_state", "team": "team:000338",
            "claim": "c", "quote": "Logan Henderson will start", "url": URL,
            "published_at": (KICK - timedelta(hours=20)).isoformat(),
            "direction_hint": "home", "lang": "en"}
    base.update(kw)
    return base


# ══════════════════════════════════════════════════════════════════
# M47 — `done` 구조화 인자 + 블록 추출 + `done_parse_fail`
# ══════════════════════════════════════════════════════════════════


def test_v5_3_8_done_이_구조화_인자다_M47():
    """🔴 `done` 의 인자가 **스키마 그 자체**다(문자열 한 칸이 아니다)."""
    from app import agentloop
    spec = next(t for t in agentloop.tool_specs()
                if t["function"]["name"] == "done")
    props = spec["function"]["parameters"]["properties"]
    assert "output" not in props, sorted(props)
    assert "variables" in props, sorted(props)


@pytest.mark.parametrize("wrap", [
    "{body}",
    "설명 한 줄\n\n```json\n{body}\n```\n끝났다",
    "```json\ndone({body})\n```",
    "앞말 done({body}) 뒷말",
    "```\n{body}\n```",
    # ══════════════════════════════════════════════════════════════
    # 🔴 **울타리만이 풀 수 있는 경우** — 앞에 **미끼 중괄호**가 있다
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 첫 판에 돌연변이(*"블록 추출기 끄기"*)가 **통과했다** — 중괄호
    #     세기(③)가 메워 줬다. 🔴 그러면 울타리 추출기가 **일하는지 모른다.**
    #  🔴 앞에 `{설명}` 을 두면 중괄호 세기는 그것을 집어 실패하고, **울타리만**
    #     옳은 블록을 찾는다.
    "메모 {이 줄은 JSON 이 아니다}\n\n```json\n{body}\n```",
])
def test_v5_3_8_산문_속_블록을_추출한다_M47(wrap):
    """🔴 산문 속 ```json `done({…})` 꼴도 **수용한다**(지시서 §1 M47)."""
    import json

    from app import agentloop
    body = json.dumps({"variables": [_row()]}, ensure_ascii=False)
    got, why = agentloop.parse_output(wrap.replace("{body}", body))
    assert len(got) == 1, (got, why)


def test_v5_3_8_추출_두_번_실패면_done_parse_fail_M47():
    """🔴 *"추출 실패 **2회**면 그 경기 중단 사유 `done_parse_fail`"*.

    ⚠️ 그 사유가 enum 에 **있어야** 한다 — 없으면 카드가 짐작해서 적는다(§8-6).
    """
    from app.reasons import Reason
    assert hasattr(Reason, "DONE_PARSE_FAIL"), [r.name for r in Reason]
    r = Reason.DONE_PARSE_FAIL
    assert r.value == "done_parse_fail"
    # 🔴 **판정**(우리 코드가 못 읽은 것이다) · 다시 물어도 같다
    assert r.fix_where == "판정" and r.kind == "bug"
    from app.reasons import SAY
    assert "다시 물어도 같다" in SAY[r], SAY[r]
    assert agent_stop_uses(Reason.DONE_PARSE_FAIL)


def agent_stop_uses(reason) -> bool:
    """🔴 루프가 **그 사유로** 멈추나(배선 · #2)."""
    import inspect

    from app import agentloop
    return reason.name in inspect.getsource(agentloop)


# ══════════════════════════════════════════════════════════════════
# M48 — `team` 은 열쇠만. 이름이면 폐기
# ══════════════════════════════════════════════════════════════════


def test_v5_3_8_이름이면_폐기한다_M48():
    """🔴🔴 *"이름이면 그 항목 **폐기** `name_not_key`"*(지시서 §1 M48).

    ⚠️ 나는 이 세션에서 이름을 **열쇠로 옮겼다** — 지시서가 그것을 뒤집었다.
    🔴 왜 폐기가 맞나: 옮기면 모델의 그 버릇이 **숨는다.** 폐기하면
       `name_not_key` 가 수로 쌓이고 프롬프트를 고칠 근거가 된다.
    """
    from app import agentloop
    from app.reasons import Reason
    assert hasattr(Reason, "NAME_NOT_KEY"), [r.name for r in Reason]
    got, why = agentloop.parse_args(
        {"variables": [_row(team="Milwaukee Brewers"), _row()]}, inp=_inp())
    # 🔴 **열쇠인 것만** 남는다
    assert len(got) == 1, (got, why)
    assert got[0].team == "team:000338"
    assert "name_not_key" in why, why


def test_v5_3_8_옮기는_코드가_없다_M48():
    """🔴 **옮기기를 걷었다** — 그 함수가 남아 있으면 다음 사람이 되살린다.

    ⚠️ D46 — 독스트링·주석을 뺀 **코드만** 본다(위 설명이 그 이름을 적는다).
    """
    import pathlib

    from tests._helpers import strip_docs
    body = strip_docs(pathlib.Path("app/agentloop.py").read_text())
    assert "_team_key" not in body, (
        "🔴 이름→열쇠 옮기기가 코드에 남아 있다 — M48 은 **폐기**다")


# ══════════════════════════════════════════════════════════════════
# M49 — 캐시/비캐시 분리 + 원장 필수 칸
# ══════════════════════════════════════════════════════════════════


def test_v5_3_8_캐시를_분리해_센다_M49():
    """🔴 캐시 입력을 **제값으로 세지 않는다**(실측: 입력 179k 중 캐시 121k)."""
    from app import solar
    b = solar.MatchBudget()
    b.took({"prompt_tokens": 18_692, "completion_tokens": 1_791,
            "prompt_tokens_details": {"cached_tokens": 16_320}})
    assert b.input_tokens == 2_372
    assert b.cached_tokens == 16_320


def test_v5_3_8_원장_줄에_세_토큰과_USD_가_있다_M49():
    """🔴🔴 *"원장 매 줄에 `in`·`cache`·`out` 토큰과 USD **필수** — `None` 이면
    기록 실패"*(지시서 §1 M49).

    ⚠️ 실측 2026-10-04: 내가 원장을 읽으려 하니 `in`·`out` 이 **없었다**(칸
       이름이 `prompt_tokens` 였다). 🔴 그리고 `ledgerkind.cost_of` 는
       `cost_usd` 를 찾는데 원장은 `usd` 를 적었다 — **늘 0 이었다.**
    """
    import json
    import pathlib
    import tempfile

    from app import solar
    with tempfile.TemporaryDirectory() as d:
        p = solar.write_ledger(
            {"match": "statsapi:1", "usd": 0.0031,
             "in": 2_372, "cache": 16_320, "out": 1_791},
            root=pathlib.Path(d))
        row = json.loads(p.read_text(encoding="utf-8").strip())
    for need in ("in", "cache", "out", "usd"):
        assert row.get(need) is not None, (need, row)


def test_v5_3_8_None_이면_기록이_실패한다_M49():
    """🔴 *"`None` 이면 기록 실패"* — 조용히 빈 줄을 쌓지 않는다."""
    import pathlib
    import tempfile

    from app import solar
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(ValueError) as got:
            solar.write_ledger({"match": "x", "usd": None, "in": None,
                                "cache": None, "out": None},
                               root=pathlib.Path(d))
    assert "in" in str(got.value), got.value


def test_v5_3_8_비용_읽기가_원장_칸을_쓴다_M49():
    """🔴 `ledgerkind.cost_of` 가 **원장이 쓰는 칸**을 읽는다(사본 금지)."""
    from app import ledgerkind
    rows = [{"match": "g1", "usd": 0.01}, {"match": "g1", "usd": 0.02}]
    assert ledgerkind.cost_of("g1", rows) == 0.03
    assert ledgerkind.cost_of("없다", rows) is None


# ══════════════════════════════════════════════════════════════════
# M50 — 접두 기호로 거르지 않는다
# ══════════════════════════════════════════════════════════════════


def test_v5_3_8_접두_기호로_줄을_거르지_않는다_M50():
    """🔴🔴 *"카드 파이프라인은 **접두 기호로 줄을 거르지 않는다**"*(§1 M50).

    ⚠️ 나는 `state_shown` 이 **표시(🔴·⚠️·✅)로** 줄을 골랐다 — 지시서가 그것을
       뒤집었다. 🔴 까닭은 이 세션이 증명했다: 그 기준이 **두 번** 줄을 삼켰다
       (31줄 · 그리고 고친 뒤에도 에이전트 줄).
    """
    import inspect

    from app import analyze
    from tests._helpers import strip_docs
    src = strip_docs(inspect.getsource(analyze.state_shown))
    for mark in ("🔴", "⚠️", "✅"):
        assert mark not in src, (
            f"🔴 `state_shown` 이 아직 기호(`{mark}`)로 고른다 — M50 금지다")
    # 🔴 **글자가 있으면 나온다**(기호와 무관하게)
    for said in ("✅ 됐다", "🔴 안 됐다", "unknown", "그냥 글", "검색 3/3"):
        assert analyze.state_shown(said) is True, said
    assert analyze.state_shown("") is False
    assert analyze.state_shown("   ") is False


def test_v5_3_8_에이전트_줄이_기호로_시작하지_않는다_M50():
    """🔴 *"에이전트가 만든 카드 줄은 ✅·이모지·기호로 시작하지 않는다"*."""
    import inspect

    from app import analyze
    src = inspect.getsource(analyze._run_agent)
    import re
    # 🔴 `note = (...)` 의 첫 글자가 기호면 안 된다
    for m in re.finditer(r'note\s*=\s*\(?\s*f?"([^"]{0,4})', src):
        head = m.group(1)
        assert not head[:1] in ("✅", "🔴", "⚠️", "·", "—"), (
            f"🔴 에이전트 줄이 기호로 시작한다: {head!r} — M50 금지다")


# ══════════════════════════════════════════════════════════════════
# M51 — `home_id`·`away_id` 필수
# ══════════════════════════════════════════════════════════════════


def test_v5_3_8_입력에_두_열쇠가_필수다_M51():
    """🔴 *"없으면 에이전트 호출 **전에** 실패"*(§3-1)."""
    from app import agentloop
    for miss in ("home", "away"):
        kw = {"match_key": "statsapi:1", "home": "team:1", "away": "team:2",
              "home_names": ("a",), "away_names": ("b",),
              "competition": "MLB", "sport": "baseball",
              "kickoff_utc": KICK, "venue": "", "langs": ("en",)}
        kw[miss] = ""
        with pytest.raises(ValueError) as got:
            agentloop.AgentInput(**kw)
        assert "열쇠" in str(got.value), got.value


def test_v5_3_8_입구가_두_열쇠를_넘긴다_M51():
    """🔴 `gather` 로 가는 `game` 에 그 칸이 **실려야** 한다(실측이 잡은 결함)."""
    import ast
    import inspect
    import textwrap

    from app import analyze
    tree = ast.parse(textwrap.dedent(inspect.getsource(analyze.answer)))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "gather":
            for arg in node.args:
                if isinstance(arg, ast.Dict):
                    keys |= {k.value for k in arg.keys
                             if isinstance(k, ast.Constant)}
    assert {"home_id", "away_id"} <= keys, sorted(keys)


# ══════════════════════════════════════════════════════════════════
# M52 — 날짜 인식 세 꼴
# ══════════════════════════════════════════════════════════════════


#: ⚠️ **`WHEN_WORDS` 를 쓰지 않는다** — `preview`·`lineup` 이 들어가면 그 낱말이
#  `when` 을 메워 **날짜 정규식이 일하는지 모른다**(첫 판에 돌연변이가 통과했다).
@pytest.mark.parametrize("q", [
    "Brewers Padres Oct 4",
    "Brewers Padres October 2026",
    "Brewers Padres 2026-10-04",
    "ロッテ ソフトバンク 10月4日",
    "ロッテ ソフトバンク 2026年10月",
])
def test_v5_3_8_날짜_세_꼴을_다_센다_M52(q):
    """🔴 달+일 · 달+연도 · ISO **전부**(§1 M52)."""
    from app import querygate
    assert "when" in querygate.count_parts(q)[1], (q,
                                                   querygate.count_parts(q))


def test_v5_3_8_연도만은_날짜가_아니다_M52():
    """⚠️ **연도 하나**는 창을 안 좁힌다 — 날짜가 아니다."""
    from app import querygate
    assert "when" not in querygate.count_parts("Brewers Padres 2026")[1]


# ══════════════════════════════════════════════════════════════════
# §3-3 리마인드 — 계약은 아니지만 **있는지** 본다
# ══════════════════════════════════════════════════════════════════


def test_v5_3_3_여덟_턴마다_리마인드를_넣는다():
    """🔴 지시서 §1 추가 한 줄:

    > 매 **8턴마다** 시스템이 *"지금까지 모은 변수로 `done` 을 부를 수 있다.
    > 카탈로그에서 안 찾은 유형: …"* 를 **리마인드**로 넣는다. 48턴 배회의
    > 재발 방지이고, **턴 상한(32)은 그대로 둔다.**
    """
    from app import agentloop
    assert agentloop.REMIND_EVERY == 8
    said = agentloop.remind_line(["absence", "coach_conflict"])
    assert "done" in said and "absence" in said, said
    # 🔴 **턴 상한은 32** 다(지시서가 그 수를 적었다)
    assert agentloop.max_turns() == 32
