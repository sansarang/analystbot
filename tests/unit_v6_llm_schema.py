"""🔴🔴 **v6 §7 단위 — `llm.py` 의 스키마 변환.**

지시서 §7: *"단위 테스트 — 수학과 파서만 … `llm.py` 의 스키마 변환
(`additionalProperties`·`required`·`null`)."*

§4 가 요구한 Upstage strict 규칙:

> 모든 object 에 `additionalProperties: false`, **모든 속성을 `required` 에
> 넣고**, 선택 칸은 타입에 `null` 을 더해 표현한다.

🔴 그리고 **경기마다 달라지는 enum 을 요청마다 스키마에 박는다** — 그것이
   *"이름 대신 열쇠"*·*"머리표 대신 도메인"* 을 **구조적으로** 막는 자리다.
"""
from __future__ import annotations

from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict

from app.core import llm
from app.core.schema import VarCandidate, VarCandidates


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def test_모든_object_가_strict_규칙을_지킨다():
    got = llm.strict_schema(VarCandidates)
    objs = [n for n in _walk(got)
            if isinstance(n.get("properties"), dict)]
    assert objs, got
    for n in objs:
        assert n.get("additionalProperties") is False, n
        # 🔴 **전부 required** — 선택 칸도 빠지지 않는다
        assert set(n["required"]) == set(n["properties"]), (
            sorted(set(n["properties"]) - set(n["required"])), n.get("title"))
        # ⚠️ `default` 는 strict 가 안 받는다
        for sub in n["properties"].values():
            assert "default" not in sub, sub


def test_참조를_펼친다():
    """🔴 `$ref`·`$defs` 가 남아 있으면 strict 가 거부할 수 있다."""
    got = llm.strict_schema(VarCandidates)
    assert "$defs" not in got, got.keys()
    assert not [n for n in _walk(got) if "$ref" in n], "🔴 `$ref` 가 남았다"
    # 🔴 펼친 결과에 **속 모델의 칸**이 실제로 보인다(빈 스키마가 아니다)
    names = {k for n in _walk(got) if isinstance(n.get("properties"), dict)
             for k in n["properties"]}
    assert {"subtask", "type", "subject", "claim", "quote", "doc_id"} <= names, \
        sorted(names)


def test_선택_칸은_null_을_더해_표현한다():
    """🔴 `required` 에서 빼지 않는다 — 타입에 `null` 을 더한다(§4)."""
    class _M(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)
        a: str
        b: int | None = None

    got = llm.strict_schema(_M)
    assert set(got["required"]) == {"a", "b"}, got["required"]
    b = got["properties"]["b"]
    said = str(b)
    assert "null" in said, b


def test_요청마다_enum_을_박는다():
    """🔴🔴 **이것이 ② 결함을 구조적으로 막는 자리다**(§4)."""
    keys = ["team:000103", "team:000119"]
    docs = ["D1", "D2"]
    kinds = ["absence", "def_absence"]
    got = llm.strict_schema(
        VarCandidates,
        enums={"subject": keys, "doc_id": docs, "type": kinds})
    props = next(n["properties"] for n in _walk(got)
                 if isinstance(n.get("properties"), dict)
                 and "subject" in n["properties"])
    assert props["subject"]["enum"] == keys, props["subject"]
    assert props["doc_id"]["enum"] == docs, props["doc_id"]
    assert props["type"]["enum"] == kinds, props["type"]
    # 🔴 열거값은 **문자열**이다(모델이 다른 꼴을 낼 수 없다)
    for name in ("subject", "doc_id", "type"):
        assert props[name]["type"] == "string", props[name]


def test_출력_모델에_코드가_정할_칸이_없다():
    """🔴 §9 금지 — `favors`·`weight`·`strength`·`grade` 를 모델이 못 채운다."""
    from app.core import schema as S
    banned = {"favors", "weight", "strength", "grade", "hardness"}
    for model in (S.VarCandidate, S.VarCandidates, S.HypoOut, S.ScenarioOut,
                  S.RedTeamOut, S.SpellOut):
        got = set(model.model_fields)
        assert not (got & banned), (model.__name__, got & banned)


def test_LLM_출력_모델에_방향_칸이_없다():
    """🔴 `direction_hint` 자유 문장이 결함 ②의 전형이었다 — 칸 자체를 없앴다."""
    assert "direction_hint" not in VarCandidate.model_fields
    assert "direction" not in VarCandidate.model_fields


def test_알_수_없는_용도는_터진다():
    with pytest.raises(KeyError, match="purposes"):
        llm.purpose_cfg("없는용도")
