"""🔴🔴 **단계 3+5 통합 계약** — 지시 2026-10-14 *"3,5 통합"*.

칸 4(국내 기사)가 **매달린 포인터**로 돌아가지 못하게 막는다. 실측 2026-10-14:
슬레이트 10장 **전부**가 `⏸ 변수 단계에서 센다` 로 찍혔다 — `s2_facts`(단계 3)가
딥서치(단계 5)보다 먼저 돌기 때문이다.

지키는 것:
  AM1 세는 곳이 **하나**다 — `core/absence.recount`
  AM2 **s5 뒤**에 부른다 — 변수가 생긴 다음이어야 기사 수가 존재한다
  AM3 칸 1~3 은 **안 건드린다**(구조 사실은 s2 가 센 그대로)
  AM4 규칙 변수(`from_rule`)는 **기사가 아니다** — 세지 않는다
  AM5 0 건이면 **까닭을 이름으로** 적는다(#3 조용한 0 금지)
  AM6 사다리가 비면 `facts` 를 그대로 둔다(없는 칸을 만들지 않는다)
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _code(rel: str) -> str:
    """🔴 D46 — 독스트링·주석을 뺀 **코드만**."""
    said = _src(rel)
    tree = ast.parse(said)
    drop: set[int] = set()
    for node in ast.walk(tree):
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


class _V:
    """🔴 Variable 의 **최소 모양** — 계약이 보는 칸만 든다."""

    def __init__(self, *, type="absence", subject="A", from_rule=None,
                 grade="", n_sources=0):
        self.type = type
        self.subject = subject
        self.from_rule = from_rule
        self.grade = grade
        self.n_sources = n_sources


def test_am1_one_counter() -> None:
    """AM1 — 파이프라인이 직접 세지 않는다."""
    code = _code("app/core/pipeline.py")
    i = code.find("def _absence_merge")
    j = code.find("\ndef ", i + 10)
    body = code[i:j] if i >= 0 else ""
    assert body, "AM1 🔴 `_absence_merge` 가 없다"
    assert "recount(" in body, (
        "AM1 🔴 `_absence_merge` 가 `absence.recount` 를 안 쓴다 — 세는 규칙이 "
        "둘이 되면 한쪽만 고쳐진다(사본 금지)")
    assert "국내 기사" not in body, (
        "AM1 🔴 칸 이름을 파이프라인이 들었다 — 이름은 `core/absence` 하나다")


def test_am2_after_s5() -> None:
    """AM2 — `s5_verify.run` **뒤**에 부른다(그 전이면 기사 수가 0 뿐이다)."""
    code = _code("app/core/pipeline.py")
    i = code.find("s5_verify.run")
    j = code.find("_absence_merge(")
    assert i >= 0, "AM2 🔴 `s5_verify.run` 을 못 찾았다"
    assert j >= 0, "AM2 🔴 `_absence_merge` 호출이 없다"
    assert i < j, (
        "AM2 🔴🔴 `_absence_merge` 가 `s5_verify` **앞**에 있다 — 그러면 기사 "
        "변수가 아직 없어 칸 4 가 영원히 0 이다(고치려던 그 병이다)")


def test_am3_keeps_first_three() -> None:
    """AM3 — 칸 1~3 은 그대로. 돌려서 센다."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core import absence

    rungs = [{"rung": "fotmob", "got": 2, "why": "경기 페이지"},
             {"rung": "명단 대조", "got": 0, "why": "⬜ 건너뛰었다"},
             {"rung": "연맹 징계", "got": 1, "why": "공시"},
             {"rung": "국내 기사", "got": 0, "why": "⏸ 변수 단계에서 센다"}]
    got, why = absence.recount(rungs, [_V(grade="A", n_sources=3)], keys=["A"])
    assert [x["got"] for x in got[:3]] == [2, 0, 1], (
        f"AM3 🔴 칸 1~3 이 바뀌었다 — {[x['got'] for x in got[:3]]}")
    assert got[3]["got"] == 1, f"AM3 🔴 칸 4 를 안 셌다 — {got[3]}"
    assert "A" in why or "등급" in why, why


def test_am4_rule_vars_not_articles() -> None:
    """AM4 — `from_rule` 변수는 기사가 아니다."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core import absence

    box = absence.articles_of([_V(from_rule="IR02"), _V(from_rule="IR02")],
                              keys=["A"])
    assert box["n"] == 0, (
        f"AM4 🔴🔴 규칙으로 지은 변수를 기사로 셌다({box['n']}건) — 칸 1~3 을 "
        "두 번 세는 셈이다")
    assert "규칙" in box["why"], box["why"]


def test_am5_zero_is_named() -> None:
    """AM5 — 0 건이면 까닭이 남는다."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core import absence

    box = absence.articles_of([], keys=["A"])
    assert box["n"] == 0
    assert "0건" in box["why"] and len(box["why"]) > 20, (
        f"AM5 🔴 0 건의 까닭이 없다 — {box['why']!r}")
    assert "⏸" not in box["why"], (
        "AM5 🔴 아직 `⏸ 변수 단계에서 센다` 를 적는다 — 그 단계가 **지금**이다")


def test_am6_empty_ladder_untouched() -> None:
    """AM6 — 사다리가 비면 아무것도 만들지 않는다."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core import absence

    got, why = absence.recount([], [_V()], keys=["A"])
    assert got == [], f"AM6 🔴 빈 사다리에 칸을 지어냈다 — {got}"
    assert "안 돌렸다" in why, why


def test_am7_media_threshold_is_named() -> None:
    """AM7 — 지시서의 *"2매체"* 문턱을 못 넘으면 그렇게 적는다."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core import absence

    box = absence.articles_of([_V(grade="B", n_sources=1)], keys=["A"])
    assert "미달" in box["why"], (
        f"AM7 🔴 매체 {absence.MEDIA_MIN} 미달을 안 적는다 — {box['why']}")
