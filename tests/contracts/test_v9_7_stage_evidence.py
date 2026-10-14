"""🔴🔴 **단계마다 자기 산출물** — 사용자 지시 2026-10-11(둘 다 해라).

> `s4_extract` 가 자기 줄을 찍게 한다 — 문서 n건 → 후보 m개(0이면 그 사실과 까닭).
> 점검표가 **단계마다 자기 산출물**을 보게 한다 … 같은 증거 한 줄을 두 단계에
> 쓰지 못하게 막는다(계약으로).

⚠️ 실사고 2026-10-11(가와사키 확정 XI 점검표): 6번(추출)과 7번(검증)이 **같은
   증거 한 줄**(`**4. 뒤집는 변수**`)을 썼다. 그 블록은 `s5_verify` 의 산출이므로
   6번의 ✅ 는 **근거 없는 ✅** 였다 — `s4_extract` 는 로그 줄이 0개이고 기사 변수도
   0개여서, *건너뛴 것·후보 0개인 것·터진 것*을 가를 수 없었다.
"""
from __future__ import annotations

import ast
import inspect
import re


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
# ① 추출이 **자기 줄**을 찍는다
# ══════════════════════════════════════════════════════════════════

def test_extract_logs_its_own_line() -> None:
    """🔴 `s4_extract` 가 `문서 n건 → 후보 m개` 를 찍는다(0이면 까닭까지)."""
    from app.core.stages import s4_extract
    src = _src(s4_extract.run)
    assert "logger.info" in src, "자기 줄을 한 번도 안 찍는다"
    assert "후보" in src and "문서" in src
    #: 🔴 0개면 **까닭**을 적는다(건너뜀·후보 0·터짐을 가른다)
    assert "_why_zero" in src, "0개의 까닭을 안 가린다"


def test_extract_names_why_it_is_zero() -> None:
    """🔴 #3 — 후보 0개의 **세 까닭**을 가려 적는다."""
    from app.core.stages import s4_extract
    assert s4_extract._why_zero(docs=0, asked=0) .startswith("⬜")
    said = s4_extract._why_zero(docs=5, asked=5)
    assert "0개" in said and "문서 5건" in said
    #: 🔴 문서는 있는데 **묻지도 못했으면** 그 사실이 다르다
    other = s4_extract._why_zero(docs=5, asked=0)
    assert other != said and "못 물었다" in other


# ══════════════════════════════════════════════════════════════════
# ② 점검표 — 같은 증거를 두 단계가 못 쓴다
# ══════════════════════════════════════════════════════════════════

def test_report_stages_have_distinct_patterns() -> None:
    """🔴🔴 점검표의 **증거 무늬가 단계마다 달라야** 한다."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "pipeline_report", "tools/pipeline_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # 🔴🔴 **지운 단계는 표식이 빈 글자**다(지시 2026-10-14 점검) — 주인도 산출도
    #    없는 자리라 `🗑 해당 없음` 으로만 찍힌다. ⚠️ 빈 글자 둘을 *"같은 증거를
    #    쓴다"* 로 세면 거짓 위반이 난다.
    pats = [row[3] for row in mod.STAGES if str(row[3] or "")]
    dupes = {p for p in pats if pats.count(p) > 1}
    assert not dupes, f"🔴 두 단계가 같은 증거를 쓴다: {dupes}"
    # 🔴 반쪽을 막는다 — 지운 단계는 주인·표식을 **둘 다** 비우고, 사는 단계는
    #    **둘 다** 채운다(한쪽만 비면 표가 거짓이 된다).
    half = [row[0] for row in mod.STAGES
            if bool(str(row[2] or "")) != bool(str(row[3] or ""))]
    assert not half, (
        f"🔴 주인과 표식 중 하나만 비었다: {half}")


def test_extract_stage_reads_its_own_output() -> None:
    """🔴 6번(추출)은 **자기 산출물**(후보 수·자기 로그)을 본다."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "pipeline_report", "tools/pipeline_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    row = [r for r in mod.STAGES if r[0] == "S1 추출"]
    assert row, "추출 단계가 표에 없다"
    pat = row[0][3]
    #: 🔴 카드 블록(`4. 뒤집는 변수`)이 아니라 **추출 자기 줄**을 본다
    assert "뒤집는 변수" not in pat, pat
    assert re.search(pat, "[s4] 추출 — 문서 7건 → 후보 0개"), pat
