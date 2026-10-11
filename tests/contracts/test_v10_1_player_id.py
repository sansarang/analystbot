"""🔴🔴 **라인업 신원 통일** — 사용자 지시 2026-10-11(상성은 라인업 위에 선다).

> 지금은 같은 선수가 **선발이면서 결장·교체·무기 꺼짐**으로 들어간다
> (가와사키: 브로더센·와키자카·나가이·이즈미).
> 1. 선수 신원표: 선수 id 하나에 별칭 여럿(영문·한글·일본어/현지어·등번호·이전 번호).
>    출처: fotmob 명부 + 최근 경기 라인업 + names_ko.yaml.
>    모든 라인업 출처는 이 표로 id 를 푼다. **비교·집계는 id 로만** — 이름 문자열 비교 금지.
> 2. 캡처 풀기: 번호 → 실패 시 이름 별칭(한글·현지어·로마자 유사도) → 실패 시 그 팀
>    최근 경기 출전자 중 번호·이름 근접 후보. 캡처의 포지션(GK 등)도 읽어 넣는다.
>    끝까지 못 풀면 **운영자 알림 + 카드에 🔴**.
"""
from __future__ import annotations

import ast
import inspect


def _src(fn) -> str:
    tree = ast.parse(inspect.getsource(fn))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Module)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def _rows():
    """🔴 세 출처가 같은 선수를 **다른 꼴로** 준 모양(실측의 축소판)."""
    return [
        # fotmob 명부(경기 페이지 라인업) — id·번호·포지션이 있다
        {"name": "Svend Brodersen", "number": 49, "pos": "GK",
         "player_id": "111", "source": "fotmob"},
        {"name": "Yasuto Wakizaka", "number": 14, "pos": "CM",
         "player_id": "222", "source": "fotmob"},
        # 최근 경기 라인업 — 번호가 없고 이름만
        {"name": "Yasuto Wakizaka", "source": "past"},
        # 같은 선수의 **이전 번호**
        {"name": "Svend Brodersen", "number": 1, "player_id": "111",
         "source": "past"},
    ]


def test_table_merges_by_player_id() -> None:
    """🔴 ① — 같은 `player_id` 는 **한 id** 로 모이고 별칭·번호가 쌓인다."""
    from app.core import playerid
    box = playerid.build(rows=_rows())
    assert len(box) == 2, list(box)
    one = [w for w in box.values() if "Svend Brodersen" in w.names][0]
    assert one.numbers == {49, 1}, one.numbers
    assert one.pos == "GK"
    assert {"fotmob", "past"} <= one.sources


def test_table_adds_korean_aliases() -> None:
    """🔴 ① — `names_ko.yaml` 의 한글 표기가 그 id 의 별칭이 된다."""
    from app.core import playerid
    box = playerid.build(rows=_rows(),
                         ko={"Svend Brodersen": ["브로더센"],
                             "Yasuto Wakizaka": ["와키자카"]})
    one = [w for w in box.values() if 49 in w.numbers][0]
    assert "브로더센" in one.names


def test_resolve_by_number_first() -> None:
    """🔴 ② 사다리 1칸 — **번호**가 가장 먼저다(언어가 없다)."""
    from app.core import playerid
    box = playerid.build(rows=_rows())
    got, why = playerid.resolve(box, said="아무 글자", number=49)
    assert got and 49 in box[got].numbers, (got, why)
    assert "번호" in why


def test_resolve_by_korean_alias() -> None:
    """🔴 ② 사다리 2칸 — 번호가 안 맞으면 **이름 별칭**(한글)."""
    from app.core import playerid
    box = playerid.build(rows=_rows(), ko={"Svend Brodersen": ["브로더센"]})
    got, why = playerid.resolve(box, said="브로더센", number=None)
    assert got and 49 in box[got].numbers, (got, why)
    assert "별칭" in why or "이름" in why


def test_resolve_by_romaji_similarity() -> None:
    """🔴 ② 사다리 2칸 — **로마자 유사도**(표기 흔들림)도 본다."""
    from app.core import playerid
    box = playerid.build(rows=_rows())
    got, why = playerid.resolve(box, said="Wakisaka", number=None)
    assert got and 14 in box[got].numbers, (got, why)
    assert "유사" in why


def test_resolve_refuses_when_unsure() -> None:
    """🔴🔴 ② — 끝까지 못 풀면 **빈 id + 사유**다(지어내지 않는다 · #4)."""
    from app.core import playerid
    box = playerid.build(rows=_rows())
    got, why = playerid.resolve(box, said="Cristiano Ronaldo", number=99)
    assert got == "", (got, why)
    assert "못 풀었다" in why


def test_compare_is_by_id_not_string() -> None:
    """🔴🔴 ① — **이름 문자열 비교 금지**. 같은 선수는 어느 꼴로 와도 같은 id."""
    from app.core import playerid
    box = playerid.build(rows=_rows(), ko={"Yasuto Wakizaka": ["와키자카"]})
    a, _ = playerid.resolve(box, said="와키자카")
    b, _ = playerid.resolve(box, said="Yasuto Wakizaka")
    c, _ = playerid.resolve(box, said="", number=14)
    assert a and a == b == c, (a, b, c)


def test_capture_rows_carry_position() -> None:
    """🔴 ② — 캡처의 **포지션**(GK 등)도 읽는다."""
    from app.core import xicapture
    rows = xicapture.parse("1 GK 조현우\n5 DF 정승현\n10 FW 이동경")
    assert rows, rows
    assert any(str(r.get("pos") or "").upper() == "GK" for r in rows), rows


# ══════════════════════════════════════════════════════════════════
# ③ 멈춤 조건 — 상성 S2 **진입 전 검문**
# ══════════════════════════════════════════════════════════════════
#
#  > (a) 양 팀 각 11명 전원 id 확정 (b) GK 정확히 1명
#  > (c) 오늘 XI 의 id 가 결장·명단 제외·교체 "없는 선수"·꺼진 무기 목록에 **하나도
#  >     없다**. 어기면 상성·확률을 내지 않고 "라인업 신원 미확정 — 누구" 카드.
#  >     **숫자를 낸 채 🔴만 다는 것 금지.**

def test_gate_needs_eleven_ids() -> None:
    """🔴 (a) — 11명 전원 id 가 서야 통과한다."""
    from app.core import lineupgate
    got = lineupgate.check(ids={"home": ["a"] * 11, "away": ["b"] * 10},
                           pos={"home": ["GK"], "away": ["GK"]},
                           clash={})
    assert not got.ok and "away" in got.why, got.why
    assert "11" in got.why


def test_gate_needs_exactly_one_gk() -> None:
    """🔴 (b) — GK 가 **정확히 1명**이어야 한다."""
    from app.core import lineupgate
    two = lineupgate.check(ids={"home": ["a"] * 11, "away": ["b"] * 11},
                           pos={"home": ["GK", "GK"], "away": ["GK"]},
                           clash={})
    assert not two.ok and "GK" in two.why, two.why
    none = lineupgate.check(ids={"home": ["a"] * 11, "away": ["b"] * 11},
                            pos={"home": [], "away": ["GK"]}, clash={})
    assert not none.ok and "GK" in none.why


def test_gate_catches_the_same_player_twice() -> None:
    """🔴🔴 (c) — 선발인 선수가 결장·꺼진 무기 목록에 있으면 **멈춘다**."""
    from app.core import lineupgate
    got = lineupgate.check(
        ids={"home": ["fm:111"] * 11, "away": ["fm:222"] * 11},
        pos={"home": ["GK"], "away": ["GK"]},
        clash={"home": {"fm:111": ["결장", "꺼진 무기"]}})
    assert not got.ok
    assert "fm:111" in got.why and "결장" in got.why, got.why
    assert got.names == ["fm:111"] or "fm:111" in got.names


def test_gate_passes_clean() -> None:
    """🔴 셋 다 맞으면 통과다(검문이 전부를 막지 않는다)."""
    from app.core import lineupgate
    got = lineupgate.check(
        ids={"home": [f"h{i}" for i in range(11)],
             "away": [f"a{i}" for i in range(11)]},
        pos={"home": ["GK"], "away": ["GK"]}, clash={})
    assert got.ok and not got.why


def test_pipeline_stops_before_matchup() -> None:
    """🔴🔴 ③ — 어기면 **상성·확률을 내지 않는다**(숫자 + 🔴 금지)."""
    from app.core import pipeline
    src = _src(pipeline.analyze) if hasattr(pipeline, "analyze") else ""
    assert "lineupgate" in src, "검문을 안 부른다"
    i = src.index("lineupgate")
    j = src.find("s2e_matchup")
    assert j == -1 or i < j, "검문이 상성 **뒤**에 있다"
    assert "라인업 신원 미확정" in src
