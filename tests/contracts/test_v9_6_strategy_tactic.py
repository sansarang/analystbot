"""🔴🔴 **전략 판정·전술 예측** — 사용자 지시 2026-10-11(앞에서부터) ③·④.

> 3. 전략 판정: LLM 입력에 **포메이션 대신** 선발 선수별 시즌 공격 기여·평소 XI
>    대비 바뀐 자리를 준다. ④에 걸려 버리면 → **코드 판정**(바뀐 자리 수·ΔA·ΔD·
>    핵심 선발 여부)으로 대체해서 낸다. **빈칸 금지.**
> 4. 전술 예측: 근거 풀에 **MatchupReport id**(축 우위·발동 규칙·꺼진 무기·
>    시간대 득실)를 포함한다 — 기사가 0이어도 쓸 수 있어야 한다. 실패하면
>    "템플릿" 대신 **사유**(llm_truncated / 검열 코드 / 근거 0)를 카드에 적는다.
>    계약: MatchupReport가 있는 경기에서 전술 예측 근거가 []이면 **실패**.
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


# ══════════════════════════════════════════════════════════════════
# ③ 전략 — 코드 판정이 **빈칸을 메운다**
# ══════════════════════════════════════════════════════════════════

def _read(**kw):
    from app.core.strategy import TeamRead
    return TeamRead(team="T", confirmed=True, **kw)


def test_code_verdict_covers_every_case() -> None:
    """🔴 ③ — 네 재료(바뀐 자리·ΔA·ΔD·핵심 선발)로 **반드시 한 값**을 낸다."""
    from app.core import strategy
    from app.core.stages import s2d_strategy as s2d
    for read in (_read(changed=8, da=-30.0, dd=-10.0),
                 _read(changed=0, da=None, dd=None),
                 _read(changed=5, da=2.0, dd=1.0),
                 _read(changed=1, da=25.0, dd=0.0),
                 _read(changed=2, da=-20.0, dd=5.0)):
        got, why = s2d.code_verdict(read)
        assert got in strategy.KINDS, (got, why)
        assert str(why).strip(), "까닭이 비었다"


def test_code_verdict_reads_the_numbers() -> None:
    """🔴 ③ — ΔA 가 크게 내려가면 **수비 위주**, 올라가면 **공격 위주**."""
    from app.core.stages import s2d_strategy as s2d
    assert s2d.code_verdict(_read(changed=1, da=-25.0))[0] == "수비 위주"
    assert s2d.code_verdict(_read(changed=1, da=+25.0))[0] == "공격 위주"
    #: 🔴 자리가 많이 바뀌면 로테이션
    assert s2d.code_verdict(_read(changed=5, da=0.0))[0] == "로테이션·체력 관리"
    #: 🔴 아무 신호가 없으면 평소 그대로
    assert s2d.code_verdict(_read(changed=0))[0] == "평소 그대로"


def test_dropped_llm_verdict_is_replaced_not_blanked() -> None:
    """🔴🔴 ③ **빈칸 금지** — 버리면 코드 판정으로 **대체해서 낸다**."""
    from app.core.stages import s2d_strategy as s2d
    src = _src(s2d.run)
    assert "_code_lines" in src, "코드 판정 줄을 안 만든다"
    assert "코드 판정" in src, "판정 글자가 그 사실을 말하지 않는다"
    assert "code_verdict" in _src(s2d._code_lines)


def test_prompt_gives_players_not_formation() -> None:
    """🔴 ③ — 프롬프트가 **선발 선수별 공격 기여**와 바뀐 자리를 준다."""
    from app.core.stages import s2d_strategy as s2d
    src = _src(s2d._prompt)
    assert "기여" in src and "_att_lines" in src
    made = _src(s2d._att_lines)
    assert "att_table" in made and "changed" in made
    assert "바뀐 자리" in made


# ══════════════════════════════════════════════════════════════════
# ④ 전술 예측 — 상성 id 를 근거로 쓴다
# ══════════════════════════════════════════════════════════════════

#  ⚠️ F7(2026-10-11) 이후 **전술 예측은 따로 돌지 않는다** — 최종 평 한 편이
#     그 칸들을 먹인다(`s9_say` → `pipeline.with_say` → `card.tactic`). 그래서
#     계약도 그 길을 센다(없는 모듈 `s2f_tactic` 을 세지 않는다).

def test_tactic_pool_has_matchup_ids() -> None:
    """🔴🔴 ④ — 근거 풀에 **상성 id**(축·규칙·꺼진 무기·시간대)가 있다."""
    from app.core import saybundle
    made = inspect.getsource(saybundle)
    assert "matchup" in made, "상성 재료를 안 담는다"
    for word in ("axis", "fired", "off"):
        assert word in made, word
    #: 🔴 묶음에 상성 id 가 실제로 **들어간다**(id 머리글 `M`·`T`·`G`)
    assert '"M' in made or "'M" in made


def test_tactic_lines_carry_refs() -> None:
    """🔴🔴 ④ — 전술 줄이 **근거 id**를 들고 온다(기사가 0이어도 쓴다)."""
    from app.core import pipeline
    from app.core.schema import SayOut
    assert "tactic_refs" in SayOut.model_fields
    src = _src(pipeline.with_say)
    assert "tactic_refs" in src, "전술 줄에 근거를 안 붙인다"
    from app.core.stages import s9_say
    assert "tactic_refs" in _src(s9_say._prompt), "프롬프트가 안 요구한다"


def test_tactic_failure_says_why() -> None:
    """🔴 ④ — 실패하면 **사유**를 적는다(`템플릿` 한 글자로 끝내지 않는다)."""
    from app.core import render
    src = _src(render.tactic_long)
    assert "violations" in src
    #: 🔴 위반 줄을 **이른 반환보다 먼저** 붙인다(어떤 판정이든 까닭이 남는다)
    assert src.index("violations") < src.index("확정 XI 전"), src


def test_contract_empty_refs_with_matchup_is_a_failure() -> None:
    """🔴🔴 ④ 계약 — 상성이 있는데 전술 근거가 `[]` 면 **실패**."""
    from app.core import saybundle
    assert saybundle.refs_bad(refs=[], has_matchup=True)
    assert not saybundle.refs_bad(refs=["M1"], has_matchup=True)
    #: ⚠️ 상성이 없으면 그 계약은 **안 센다**(없는 자료를 요구하지 않는다)
    assert not saybundle.refs_bad(refs=[], has_matchup=False)


def test_pipeline_marks_the_empty_refs() -> None:
    """🔴 ④ — 그 실패가 **판정 글자**에 남는다."""
    from app.core import pipeline
    src = _src(pipeline.with_say)
    assert "refs_bad" in src and "근거 0" in src
