"""🔴🔴 **v6 §7 정적 검사 — 빌드 실패 조건.** 글자 검사가 아니라 **AST** 다(D46).

지시서 §7:

> - `pyright strict`: `app/core/` 전체 에러 0
> - `app/` 어디서든 LLM SDK·HTTP 직접 호출이 `llm.py` 밖에 있으면 실패(AST)
> - `app/core/` 의 단계 함수 서명에 `dict`·`Any`·`tuple` 반환이 있으면 실패
> - 문지기 함수가 둘 이상 정의돼 있으면 실패

⚠️ **옛 경로는 아직 둘이다**(`querygate.gate`·`llm.query_ok` · `solar`·`deepseek` 의
   직접 호출) — §9 가 4단계 전까지 옛 경로 수정을 금지하므로 그 둘은 **§8 5단계**가
   지운다. 🔴 그래서 지금 검사 범위는 **`app/core/`** 이고, 그 사실을 아래 적는다
   (범위를 조용히 좁히면 계약이 뜻을 잃는다).
"""
from __future__ import annotations

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CORE = ROOT / "app" / "core"


def _tree(p: pathlib.Path) -> ast.Module:
    return ast.parse(p.read_text(encoding="utf-8"))


def _funcs(p: pathlib.Path):
    for node in ast.walk(_tree(p)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def test_v6_단계_함수는_dict_any_tuple_을_돌려주지_않는다():
    """🔴 단계 경계는 **한 타입**이다(§3) — 받는 쪽이 꼴을 외우면 그것이 결함 ①이다."""
    bad: list[str] = []
    for p in sorted((CORE / "stages").glob("s?_*.py")):
        for fn in _funcs(p):
            if fn.name != "run":
                continue
            said = ast.unparse(fn.returns) if fn.returns else ""
            if not said:
                bad.append(f"{p.name}:{fn.name} — 반환 주석이 **없다**")
                continue
            for word in ("dict", "Any", "tuple"):
                if word in said:
                    bad.append(f"{p.name}:{fn.name} → {said}")
    assert not bad, ("🔴 단계 함수가 느슨한 꼴을 돌려준다(§7 정적 검사):\n  "
                     + "\n  ".join(bad))


def test_v6_단계_마다_run_이_하나다():
    """🔴 단계는 **함수 하나**다(§5) — 입구가 둘이면 어느 것이 단계인지 모른다."""
    for p in sorted((CORE / "stages").glob("s?_*.py")):
        got = [fn.name for fn in _funcs(p) if fn.name == "run"]
        assert len(got) == 1, (p.name, got)


def test_v6_core_는_망에_직접_나가지_않는다():
    """🔴 `app/core/` 에서 망에 나가는 자리는 **`llm.py` 의 `_http` 하나**다(§4).

    ⚠️ 검사는 **이름이 아니라 호출**을 본다 — `urllib.request.urlopen`·`httpx`·
       `requests`·`openai` 를 부르는 곳을 AST 로 찾는다.
    """
    hits: list[str] = []
    for p in sorted(CORE.rglob("*.py")):
        for node in ast.walk(_tree(p)):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = ([a.name for a in node.names]
                         if isinstance(node, ast.Import)
                         else [str(node.module or "")])
                for name in names:
                    head = str(name).split(".")[0]
                    if head in ("httpx", "requests", "openai", "aiohttp"):
                        hits.append(f"{p.relative_to(ROOT)}: import {name}")
            if isinstance(node, ast.Call):
                said = ast.unparse(node.func)
                if said.endswith("urlopen") and p.name != "llm.py":
                    hits.append(f"{p.relative_to(ROOT)}: {said}")
    assert not hits, ("🔴 `app/core/` 가 `llm.py` 밖에서 망에 나간다(§7):\n  "
                     + "\n  ".join(hits))


def test_v6_문지기는_core_에_하나다():
    """🔴 문지기·사다리·상한의 **두 번째 정의 금지**(§9).

    ⚠️ 옛 경로에는 아직 둘이다(`querygate.gate`·`llm.query_ok`) — §8 5단계가 하나로
       줄인다. 🔴 그때 이 계약의 범위를 `app/` 전체로 넓힌다(그 사실을 적어 둔다).
    """
    hits = [f"{p.relative_to(ROOT)}:{fn.name}"
            for p in sorted(CORE.rglob("*.py")) for fn in _funcs(p)
            if fn.name in ("gate_ok", "query_ok", "gate")]
    assert hits == ["app/core/stages/s3_docs.py:gate_ok"], hits


def test_v6_llm_출력_모델에_코드가_정할_칸이_없다():
    """🔴🔴 §3 — `favors`·`weight`·`strength`·`grade` 는 **코드가** 정한다.

    ⚠️ 모델이 그 칸을 채울 **길 자체**가 없어야 한다(실측: `direction_hint` 가
       거꾸로였다). 🔴 그래서 LLM 출력 모델의 **필드 이름**을 센다.
    """
    from app.core import schema
    banned = {"favors", "weight", "strength", "grade", "direction",
              "direction_hint", "survival", "verdict"}
    out: list[str] = []
    for name in ("VarCandidate", "VarCandidates", "HypoOut", "ScenarioOut",
                 "Hypothesis", "HypoLine", "RedTeamOut", "RedTeamLine",
                 "SpellOut"):
        model = getattr(schema, name)
        for field in model.model_fields:
            if field in banned:
                out.append(f"{name}.{field}")
    assert not out, ("🔴 LLM 출력 모델에 코드가 정할 칸이 있다(§3·§9): "
                     + ", ".join(out))


@pytest.mark.parametrize("name", ["Question", "MatchRef", "Facts", "Doc",
                                  "Variable", "Scenario", "Card",
                                  "Judgement", "MarketEval"])
def test_v6_경계_타입은_얼려_있고_모르는_칸을_거부한다(name: str):
    """🔴 §3 — `frozen=True` · `extra="forbid"`. ⚠️ 하나라도 풀리면 그 자리가 샌다."""
    from app.core import schema
    cfg = getattr(schema, name).model_config
    assert cfg.get("frozen") is True, name
    assert cfg.get("extra") == "forbid", name
