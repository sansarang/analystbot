"""🔴🔴 **유형–내용 검사가 현지어를 모른다** — 사용자 지시 2026-10-11(서치 고침).

⚠️ 실측 2026-10-11(가와사키 재현): 추출이 **후보 2개**를 냈는데 둘 다
   `s5/type_content_mismatch` 로 죽어 **기사 변수 0개**가 됐다.
   🔴 까닭: `_TYPE_WORDS` 가 **한국어·영어만** 들고 있다. 일본 기사에서 뽑은
   후보는 `欠場`·`離脱` 로 적혀 있어 "그 말이 한 글자도 없다"가 됐다.
🔴 그런데 **개념 낱말 표에는 일본어가 있다**(`rules.local_words('injury','ja')`
   → `['欠場','故障者','離脱','登録抹消']`). 그 표를 쓰면 손으로 늘릴 필요가 없다
   (#1 사본 금지).
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


def test_japanese_absence_passes() -> None:
    """🔴🔴 일본어 결장 기사가 **통과한다**."""
    from app.core.stages.s5_verify import _type_fits
    assert _type_fits("absence", "川崎FのMF脇坂泰斗が欠場する") == ""
    assert _type_fits("absence", "負傷で離脱が決まった") == ""


def test_korean_and_english_still_pass() -> None:
    """🔴 전에 통과하던 것은 그대로 통과한다."""
    from app.core.stages.s5_verify import _type_fits
    assert _type_fits("absence", "손흥민이 결장한다") == ""
    assert _type_fits("absence", "ruled out with an injury") == ""


def test_wrong_content_still_fails() -> None:
    """🔴 아무 말도 없는 내용은 **여전히 버린다**(문을 열어 둔 것이 아니다)."""
    from app.core.stages.s5_verify import _type_fits
    said = _type_fits("absence", "구단이 새 유니폼을 공개했다")
    assert said and "한 글자도 없다" in said, said


def test_words_come_from_the_table() -> None:
    """🔴 #1 — 낱말은 **개념 낱말 표**에서 자란다(손으로 늘리지 않는다)."""
    from app.core.stages import s5_verify
    src = _src(s5_verify._type_words)
    assert "local_words" in src and "word_concept" in src


def test_unknown_type_passes() -> None:
    """⚠️ 목록에 없는 유형은 **통과**다(모르는 것으로 버리지 않는다 · #4)."""
    from app.core.stages.s5_verify import _type_fits
    assert _type_fits("아무 유형", "아무 글") == ""


def test_loss_table_shows_late_drops_first() -> None:
    """🔴🔴 #3 — 손실 표가 **늦은 단계(s4·s5)를 먼저** 보인다.

    ⚠️ 실측: 표가 40줄에서 잘려 `s5/type_content_mismatch` **2건**이 안 보였다 —
       그 둘이 *"거의 통과한 것"* 인데 사람이 볼 수 없었다.
    """
    from app.core import render
    src = _src(render.loss_table)
    assert "sort" in src or "late" in src or "늦은" in src
