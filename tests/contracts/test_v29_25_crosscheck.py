"""🔴🔴 **안전장치 세 층** — 사용자 지시 2026-10-16
*"봇이 fotmob 정보를 우리 변수에 제대로 넣고 있는지 · 잘못된 경기로 하고 있는지
확인하는 장치를 순서대로 전부 구현하고 테스트해라"*.

⚠️ 재현하는 실사고(2026-10-16 코스타리카 Saprissa vs Sporting):
   팀 일정의 슬러그 주소가 **다른 맞대결**을 줘 과거 5경기 중 4개가 남의
   경기였고(한 자리엔 **그 경기 자신**), 골 목록이 없어 득실이 **조용히 0** 이
   됐다 → 폼이 `L D D D D · 득점 0.0 · 실점 0.2` 라는 거짓 수가 되어 확률·평까지
   갔다. 같은 팀을 **다른 경로**(경기 페이지 `teamForm`)로 보면 1.6/2.0 이었다.

지키는 것:
  CC1 층2 — 두 경로가 어긋나면 **False** 와 사유(둘 다 있어야 비교한다)
  CC2 층3 — 득점 합 0 · 전부 같은 결과 · 표본 부족을 **이름으로** 잡는다
  CC3 층4 — 킥오프 뒤 경기·**그 경기 자신**이 폼에 있으면 잡는다
  CC4 배선 — `s2_facts` 가 세 층을 돌려 `flags` 를 단다
  CC5 배선 — `s5_verify` 는 `flags` 가 있으면 **맥락 전용**으로 내린다
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

from app.core import crosscheck as cc

ROOT = Path(__file__).resolve().parents[2]

#: 🔴 그날 **거짓으로 들어온** 폼(경로 B — 슬러그 주소가 데려온 남의 경기들)
FAKE = {"sequence": [
    {"date": "2026-10-11", "goals_for": 0, "goals_against": 1,
     "result": "L", "score": "0-1"},
    *[{"date": f"2026-09-{d}", "goals_for": 0, "goals_against": 0,
       "result": "D", "score": "0-0"} for d in (20, 17, 13, 10)]]}
#: 🔴 같은 팀의 **참값**(경로 A — 경기 페이지 teamForm)
REAL = {"sequence": [
    {"date": "2026-10-11", "goals_for": 0, "goals_against": 1,
     "result": "L", "score": "0-1"},
    {"date": "2026-09-20", "goals_for": 2, "goals_against": 0,
     "result": "W", "score": "2-0"},
    {"date": "2026-09-17", "goals_for": 2, "goals_against": 3,
     "result": "L", "score": "2-3"},
    {"date": "2026-09-13", "goals_for": 2, "goals_against": 4,
     "result": "L", "score": "2-4"},
    {"date": "2026-09-10", "goals_for": 2, "goals_against": 2,
     "result": "D", "score": "2-2"}]}


def _code(rel: str) -> str:
    """🔴 D46 — 독스트링·주석을 뺀 **코드만**."""
    said = (ROOT / rel).read_text(encoding="utf-8")
    drop: set[int] = set()
    for node in ast.walk(ast.parse(said)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = list(getattr(node, "body", []) or [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                one = body[0]
                for ln in range(one.lineno, (one.end_lineno or one.lineno) + 1):
                    drop.add(ln)
    return "\n".join(x for i, x in enumerate(said.splitlines(), 1)
                     if i not in drop and not x.strip().startswith("#"))


def test_cc1_층2_두_경로_대조() -> None:
    """CC1 🔴🔴 그날의 거짓 폼이 **참값과 대조되면 잡힌다**."""
    ok, why = cc.form_cross(FAKE, REAL)
    assert ok is False, why
    assert "득점" in why and "0.0" in why and "1.6" in why, why
    # 🔴 같은 것끼리는 통과한다(거짓 양성이 없다)
    ok2, why2 = cc.form_cross(REAL, REAL)
    assert ok2 is True, why2
    # 🔴 한쪽이 없으면 **실패가 아니라 못 쟀음**이다(#3)
    got, said = cc.form_cross(REAL, {})
    assert got is None and "대조 못 함" in said, said


def test_cc2_층3_말이_되는_값() -> None:
    """CC2 🔴 득점 합 0 · 전부 같은 결과 · 표본 부족."""
    said = cc.form_sane(FAKE)
    assert any("득점 합이 0" in x for x in said), said
    assert not cc.form_sane(REAL), cc.form_sane(REAL)
    # 🔴 전부 같은 결과
    allD = {"sequence": [{"goals_for": 1, "goals_against": 1, "result": "D",
                          "score": "1-1"}] * 5}
    assert any("전부" in x for x in cc.form_sane(allD))
    # 🔴 스코어 글자와 득실이 어긋나는 줄
    bad = {"sequence": [{"goals_for": 1, "goals_against": 0, "result": "W",
                         "score": "3-0"}] * 3}
    assert any("어긋난다" in x for x in cc.form_sane(bad))


def test_cc3_층4_누설() -> None:
    """CC3 🔴🔴 **그 경기 자신**과 킥오프 뒤 경기를 잡는다."""
    ko = datetime(2026, 10, 16, 2, 0, tzinfo=timezone.utc)
    games = [{"date": "2026-10-16", "opp": "Sporting FC"},
             {"date": "2026-10-20", "opp": "Cartaginés"},
             {"date": "2026-09-13", "opp": "Sporting FC"}]
    said = cc.leak_of(games, kickoff=ko, home="Deportivo Saprissa",
                      away="Sporting FC")
    assert any("그 경기 자신" in x for x in said), said
    assert any("킥오프 뒤" in x for x in said), said
    # 🔴 과거 경기만 있으면 조용하다
    assert not cc.leak_of([{"date": "2026-09-13", "opp": "Sporting FC"}],
                          kickoff=ko, home="A", away="B")


def test_cc4_s2_facts_가_세_층을_돌린다() -> None:
    """CC4 🔴 배선 — 안 이으면 없는 코드다(CLAUDE.md #2)."""
    said = _code("app/core/stages/s2_facts.py")
    for one in ("crosscheck", "leak_of(", "form_sane(", "form_cross("):
        assert one in said, f"CC4 🔴 `s2_facts` 가 `{one}` 를 안 쓴다"
    assert '"flags"' in said, "CC4 🔴 어긋남을 폼 칸에 안 남긴다"


def test_cc5_s5_가_빨간_폼을_내린다() -> None:
    """CC5 🔴🔴 안전장치가 걸린 폼은 **확률에 안 닿는다**."""
    said = _code("app/core/stages/s5_verify.py")
    assert 'box.get("flags")' in said, "CC5 🔴 `flags` 를 안 읽는다"
    assert "usable_as_basis=(n >= low and not said_flags)" in said, (
        "CC5 🔴 빨간 폼이 **근거로 남는다** — 맥락 전용으로 내려야 한다")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **폼 창은 리그 경기만** — 사용자 지시 2026-10-16
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실사고 2026-10-16(Sydney FC · A리그 개막 전): 폼 다섯 경기가 **호주컵 넷 +
#     친선 하나**로 찼고(리그 **0건**) 그 수로 `득점 평균 2.6` 이 섰다.

CUPMIX = [
    {"date": "2026-07-21", "league": "Australia Cup", "gf": 5, "ga": 1},
    {"date": "2026-07-29", "league": "Club Friendlies", "gf": 1, "ga": 1},
    {"date": "2026-09-01", "league": "A-League", "gf": 1, "ga": 2},
    {"date": "2026-09-08", "league": "AFC Champions League Two", "gf": 0, "ga": 0},
    {"date": "2026-09-15", "league": "A-League", "gf": 2, "ga": 0},
]


def test_cc6_폼_창은_리그만() -> None:
    """CC6 🔴 컵·친선·대륙 대회를 뺀다 — 판정은 `form.is_league_game` 하나다."""
    from app.core import form as _form

    keep, cut = _form.league_only(CUPMIX)
    assert [k["date"] for k in keep] == ["2026-09-01", "2026-09-15"], keep
    assert len(cut) == 3, cut
    assert _form.is_league_game("A-League") and _form.is_league_game("Serie A")
    for bad in ("Australia Cup", "Club Friendlies", "DFB-Pokal", "Copa del Rey",
                "UEFA Champions League", "Conference League", "친선"):
        assert not _form.is_league_game(bad), bad
    # ⬜ 대회를 모르면 **빼지 않는다**(있는 것을 지우지 않는다 · #3)
    assert _form.is_league_game("") and _form.is_league_game(None)


def test_cc7_뺀_것을_이름으로_남긴다() -> None:
    """CC7 🔴 창이 얇아진 까닭이 보여야 한다(조용한 0 금지)."""
    from app.core.stages.s2_facts import _recent_from_games

    box = _recent_from_games(CUPMIX, kickoff=None)
    assert box.get("cup_dropped"), box
    assert any("Australia Cup" in x for x in box["cup_dropped"])
    # 🔴 남은 두 경기만 센다
    assert len(box["sequence"]) == 2, box["sequence"]
