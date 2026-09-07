"""판정 JSON 회수 — 후행 쉼표로 경기가 통째로 날아가지 않게.

🔴 [P0 실사고 2026-09-07] opus 가 후행 쉼표를 종종 만든다.
   `_loads_dict` 는 엄격 파서라 거부하고, `judge_matchup` 은 2회 재시도 후
   포기해 **판정이 `{}` 가 된다** — 그 경기는 카드가 안 나간다.

   실측:
     · KBO game=1721 최종 판정 2회 실패
       (`stop=end_turn` · 응답 2544자/2383자 · 절단 아님)
     · 같은 날 MLB 다저스 판정 원문도 `"판단": "...",\n  },` 로 같은 결함
       (당일 opus 호출 3회 중 1회 발생)

⚠️ **문법만 회수한다.** 값·키를 우리가 주무르면 그건 파싱이 아니라 창작이다.
"""

import json

import pytest

from app.engine.team_form import parse_json_object


def test_후행_쉼표가_있어도_회수한다():
    """🔴 이 파일이 존재하는 이유."""
    raw = '{"a": 1, "b": {"c": 2,}, }'
    got = parse_json_object(raw)
    assert got == {"a": 1, "b": {"c": 2}}


def test_배열의_후행_쉼표도_회수한다():
    got = parse_json_object('{"근거": ["x", "y",], "p_home": 0.56,}')
    assert got == {"근거": ["x", "y"], "p_home": 0.56}


def test_실측_형태_그대로_회수한다():
    """다저스 판정 원문에서 실제로 난 모양."""
    raw = ('{\n  "결론": {\n    "승자": "LAD",\n'
           '    "판단": "…배율(홈 0.81 대 원정 0.54)에서…",\n  },\n'
           '  "p_home": 0.56\n}')
    got = parse_json_object(raw)
    assert got["p_home"] == 0.56
    assert got["결론"]["승자"] == "LAD"


def test_값_안의_쉼표는_건드리지_않는다():
    """⚠️ 반대 위험 — 문자열 안의 `,` 를 지우면 내용이 바뀐다."""
    raw = '{"판단": "홈 0.81, 원정 0.54, 격차 34.4", "p": 1,}'
    got = parse_json_object(raw)
    assert got["판단"] == "홈 0.81, 원정 0.54, 격차 34.4"


def test_정상_JSON_은_그대로_통과한다():
    raw = json.dumps({"p_home": 0.56, "우세": "home"}, ensure_ascii=False)
    assert parse_json_object(raw) == {"p_home": 0.56, "우세": "home"}


def test_코드펜스와_후행쉼표가_같이_와도_회수한다():
    assert parse_json_object('```json\n{"a": 1,}\n```') == {"a": 1}


def test_산문이_앞뒤에_붙어도_회수한다():
    got = parse_json_object('생각해보면 다음과 같다.\n{"a": 1,}\n이상입니다.')
    assert got == {"a": 1}


@pytest.mark.parametrize("raw", [
    "", None, "판정을 못 하겠습니다", "{", '{"a": ',
])
def test_회수할_수_없으면_None_이다(raw):
    """⚠️ 잘린 JSON 을 지어내 채우지 않는다."""
    assert parse_json_object(raw) is None


def test_객체가_아니면_None_이다():
    assert parse_json_object('[1, 2, 3]') is None


def test_내용을_고치지_않는다():
    """문법 회수만 한다 — 없는 키를 만들거나 값을 바꾸지 않는다."""
    src = open("app/engine/team_form.py", encoding="utf-8").read()
    i = src.index("def _loads_dict")
    seg = src[i:src.index("\ndef parse_json_object")]
    for banned in ("setdefault", "or 0.5", '"p_home"'):
        assert banned not in seg, f"파서가 내용을 만든다: {banned}"


# ═══════════════ 변수 방향 표기 — 영문도 읽는다

import pytest as _pytest


@_pytest.mark.parametrize("side_txt,expect", [
    ("홈", "home"), ("원정", "away"),
    ("home", "home"), ("away", "away"),
    ("Home", "home"), ("AWAY", "away"),
])
def test_방향_표기가_영문이어도_읽는다(side_txt, expect):
    """🔴 실측 2026-09-07 grok 판정: "발생 시 **home** 방향 약 2%p · …"
    종전 정규식은 `홈|원정` 만 받아 `parsed=None` 이 됐고, 그러면 그 변수는
    예산 검사·자료14 루프·원장에서 통째로 빠진다. opus 는 한국어를 써서
    이 결함이 안 보였다 — 대체 모델을 쓰는 순간 정량화가 무력화된다."""
    from app.engine.variable_parse import parse_variable

    line = (f"연전 피로 — 발생 시 {side_txt} 방향 약 2%p · 발생 확률 40% · "
            f"현재 p에 1%p 기반영 · 근거 자료10 연전")
    got = parse_variable(line)
    assert got and got["side"] == expect
    assert got["n"] == 2.0 and got["m"] == 1.0 and got["q"] == 40.0
    assert got["risk"] == "연전 피로"


def test_모르는_방향_표기는_버린다():
    """⚠️ 관대함이 창작이 되면 안 된다 — 모르는 값을 홈으로 찍지 않는다."""
    from app.engine.variable_parse import parse_variable

    assert parse_variable("x — 발생 시 중립 방향 약 2%p · 현재 p에 1%p "
                          "기반영 · 근거 자료10") is None


def test_프롬프트가_한국어_표기를_못박는다():
    """쓰는 쪽은 좁게, 읽는 쪽만 관대하게."""
    from app.engine.prompts import MATCHUP

    assert "`홈` 또는 `원정` 한국어로 쓴다" in MATCHUP
    assert "`home`·`away` 로 쓰지 마라" in MATCHUP
