"""🔴🔴 **LLM 회상 계약** — 사용자 지시 2026-10-14.

> 3번(감독 이름)·4번(감독 부임후 성적)·5번(팀내 불화)은 딥서치에서 못 찾으면
> **llm 이 찾게 한다** … 그래서 llm 을 **전략예측 및 서치**로 쓰는 거다.

🔴 이것은 **문서 없이 모델 기억**을 받는 유일한 자리다. 그래서 가장 조여 둔다.

지키는 것:
  RC1 원천이 **박힌다** — `🔴 LLM 기억` 글자를 들고 다닌다
  RC2 **확률·등급에 못 닿는다** — 확률 경로가 이 모듈을 부르지 않는다
  RC3 **딥서치가 찾은 칸을 안 덮는다**(문서 있는 사실이 늘 세다)
  RC4 *"모른다"*(빈 글자)는 **실패가 아니다** — 지어내게 몰지 않는다
  RC5 빈 칸 판정은 **한 곳**이다(`need`)
  RC6 **s5 뒤**에 부른다(그 전이면 "못 찾았다"를 말할 수 없다)
  RC7 설정에 `recall` purpose 가 있고 **온도 0** 이다(재현)
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


def test_rc1_source_is_stamped() -> None:
    """RC1 — 원천 글자가 있고, 회상이 그것을 박는다."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages import s4b_recall as rc
    assert "LLM" in rc.SRC, f"RC1 🔴 원천 글자가 LLM 을 안 말한다 — {rc.SRC!r}"
    code = _code("app/core/stages/s4b_recall.py")
    assert "source=" in code and "SRC" in code, (
        "RC1 🔴 회상이 `source` 칸에 원천을 안 박는다 — 카드가 검증 여부를 "
        "구별할 수 없다")


def test_rc2_not_in_probability_path() -> None:
    """RC2 🔴🔴 — 확률을 만드는 모듈이 회상을 **부르지 않는다**."""
    bad = []
    for rel in ("app/core/probmodel.py", "app/core/sim.py",
                "app/core/matchup.py", "app/core/probfloor.py",
                "app/core/survive.py", "app/core/picks.py",
                "app/core/stages/s7_judge.py", "app/core/stages/s2e_matchup.py"):
        path = ROOT / rel
        if not path.is_file():
            continue
        if "s4b_recall" in _code(rel):
            bad.append(rel)
    assert not bad, (
        f"RC2 🔴🔴 확률 경로가 **LLM 기억**을 읽는다: {bad} — 사용자 결정 "
        "2026-10-14(*\"안 된다 — 쓰기만 한다\"*)을 깬다")


def test_rc2b_source_word_not_in_probability() -> None:
    """RC2b — 원천 글자 자체가 확률 코드에 나타나서도 안 된다(분기 금지)."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages import s4b_recall as rc
    bad = []
    for rel in ("app/core/probmodel.py", "app/core/sim.py",
                "app/core/matchup.py", "app/core/picks.py"):
        path = ROOT / rel
        if path.is_file() and rc.SRC in _code(rel):
            bad.append(rel)
    assert not bad, f"RC2b 🔴 확률 코드가 원천 글자로 분기한다: {bad}"


def test_rc3_does_not_overwrite_search() -> None:
    """RC3 — 딥서치가 받은 이름을 회상이 **덮지 않는다**. 돌려서 센다."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.schema import Coach
    from app.core.stages import s4b_recall as rc

    code = _code("app/core/stages/s4b_recall.py")
    assert "keep or name" in code, (
        "RC3 🔴 받은 이름(`keep`)을 먼저 쓰는 줄이 없다 — LLM 이 덮을 수 있다")
    # `need` 가 이미 찬 칸을 **안 고른다**
    class _F:
        coach = {"A": Coach(name="있다", record="1-0-0", source="경기 페이지")}
    assert rc.need(_F(), keys=["A"]) == {}, (
        "RC3 🔴 이름·성적이 다 있는 팀을 '빈 칸'으로 골랐다 — LLM 을 헛부른다")


def test_rc4_blank_is_not_failure() -> None:
    """RC4 — 프롬프트가 *"모르면 빈 글자"* 를 분명히 허락한다."""
    said = _src("app/core/stages/s4b_recall.py")
    for word in ("모르는 칸은 빈 글자", "추측해서 채우지 마라", "만들지 마라"):
        assert word in said, (
            f"RC4 🔴 프롬프트에 `{word}` 가 없다 — 모델을 지어내게 몬다")
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages import s4b_recall as rc
    assert rc._CoachOut().name == "", "RC4 🔴 빈 글자가 기본값이 아니다"


def test_rc5_one_judge() -> None:
    """RC5 — '못 찾았다' 판정은 `need` 하나다."""
    pipe = _code("app/core/pipeline.py")
    i = pipe.find("def _recall_fill")
    j = pipe.find("\ndef ", i + 10)
    body = pipe[i:j] if i >= 0 else ""
    assert body, "RC5 🔴 `_recall_fill` 이 없다"
    assert "_rc.run(" in body, "RC5 🔴 회상 모듈을 안 부른다"
    for bad in ('getattr(one, "name"', "coach.get("):
        assert bad not in body, (
            f"RC5 🔴 파이프라인이 빈 칸을 **직접** 센다(`{bad}`) — 판정은 "
            "`s4b_recall.need` 하나다(사본 금지)")


def test_rc6_after_s5() -> None:
    """RC6 — `s5_verify.run` 뒤에 부른다."""
    pipe = _code("app/core/pipeline.py")
    i = pipe.find("s5_verify.run")
    j = pipe.find("_recall_fill(")
    assert i >= 0 and j >= 0, "RC6 🔴 두 자리를 못 찾았다"
    assert i < j, (
        "RC6 🔴🔴 회상이 `s5_verify` **앞**에 있다 — 딥서치가 아직 안 끝났는데 "
        "*'못 찾았다'* 고 말하는 셈이다")


def test_rc7_purpose_is_configured() -> None:
    """RC7 — 설정에 `recall` 이 있고 온도 0 이다."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core import llm
    box = llm.purpose_cfg("recall")
    assert box, "RC7 🔴 `config/llm.yaml` 에 `recall` purpose 가 없다"
    assert box.get("temperature") == 0, (
        f"RC7 🔴 온도가 0 이 아니다({box.get('temperature')}) — 같은 경기에 "
        "다른 회상이 나오면 재현이 뜻을 잃는다")
