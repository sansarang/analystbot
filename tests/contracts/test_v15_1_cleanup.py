"""🔴🔴 **§1 불필요 요소 정리** — 지시서 2026-10-12(셋째) §1.

> 계약 **X1**: 삭제·축소된 단계가 **확률·등급 경로에 남아 있으면 실패**.
> 계약 **X2**: LLM 호출은 **`s4_extract`(사실 추출)·필요 시 라인업 캡처 판독**만.

🔴 처분표(그 지시서 §1)와 **이 계약이 한 짝**이다 — 지운 것이 되살아나면 빨개진다.
⚠️ 이 파일은 **처분이 끝난 뒤** 초록이 된다(먼저 빨갛게 쓴다).
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: 🔴🔴 **지워질 모듈** — 처분표의 "삭제" 줄
GONE: tuple[str, ...] = (
    "app/core/priority.py",          # ⑨ 우선순위 지수 → absence_loss 가 대체
    "app/core/reweight.py",          # ⑳ 시나리오 재가중 → 생존은 격자에서
    "app/core/stages/s6_hypo.py",    # ⑭⑮ 가설·무너뜨릴 조건(LLM)
    "app/core/stages/s5b_falsify.py",  # ⑱ 반증 딥서치 → 2절 오늘 사실 질의로
)

#: 🔴 LLM 을 불러도 되는 자리 — **사실 추출**과 캡처 판독, 그리고 **질의 글자**
#
#  🔴🔴 **충돌을 적어 둔다**(2026-10-12 셋째): X2 는 *"LLM 호출은 s4_extract(사실
#     추출)·필요 시 라인업 캡처 판독만"* 이라고 적었다. 그런데 **경기 찾기**
#     (`findwriter`·`s1_resolve`)와 **질의 작성**(`querywriter`·`queries`·
#     `querygate`·`s3_docs`)도 LLM 을 부른다.
#  🔴 **해석**: 그 둘이 내는 것은 **검색에 넣을 글자**이고, 사실은 여전히
#     `s4_extract` 가 뽑는다 — §0 의 금지(*"판단·예측·서술로 확률·등급을 움직이지
#     않는다"*)에 닿지 않는다. ⚠️ 그리고 사용자가 앞서 **경기 찾기를 제대로
#     하라**고 못 박았다(2026-10-12: *"경기 찾기부터 제대로 되어야 한다"*) —
#     그 길의 이름 후보 LLM 을 지우면 그 지시를 깬다.
#  🔴 그래서 **판정·서술 LLM 은 전부 지우고**(⑩⑭㉔ 처분 완료), 질의 글자만 남겼다.
#     그 사실을 여기 적어 둔다(조용히 예외를 만들지 않는다).
# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **처분이 **되돌려졌다** — 사용자 지시 2026-10-14
# ══════════════════════════════════════════════════════════════════
#
#  > 예전에 있던 포메이션 전략 재개 · llm 호출추가 · **전술예상도 해야 한다** ·
#  > **전술 전문가다 … 자료로만 … 지어내지 않는다**
#
#  🔴 지시서 2026-10-12(셋째) §1 이 ㉔(최종 평·전술 예측)을 지웠다. **직접 지시가
#     그것을 덮는다**(CLAUDE.md 첫 줄: *"지시문이 이 파일과 충돌하면 지시문이
#     이긴다"* · 그리고 사용자 지시는 문서보다 위다).
#  🔴 그래서 `s9_say`(전술 예측·최종 평)과 `s9_audit`(검열)을 **되살렸다**.
#  ⚠️ 지운 까닭은 하나였다 — 광주 재현에서 평이 근거에 없는 **4-3** 을 적었다.
#     검열 (r)(수치 대조)은 그것을 **못 잡았다**(`4`·`3` 낱개로 쪼개진다).
#     🔴 되살리며 검열 **(w) 스코어 꼴**을 더했다(`s9_say._SCORE`) — 묶음 글에
#     그 **글자**가 없으면 위반이다. 계약은 아래 `test_w_score_check` 가 센다.
#  🔴🔴 **확률·등급에는 못 닿는다**(사용자 결정 2026-10-14: *"안 된다 — 쓰기만
#     한다"*) — `pipeline.with_say` 는 글 칸만 `model_copy` 하고, 절대 규칙
#     (`direction`·`weight`·`strength`·`survival`·`verdict`)은 그대로 산다.
LLM_OK: tuple[str, ...] = (
    "app/core/stages/s4_extract.py",   # ⑥ 기사 → 결장·복귀·라인업 **사실**
    # 🔴 되살린 둘(지시 2026-10-14) — 전술 전문가 예측 · 그 검열
    "app/core/stages/s9_say.py",
    "app/core/stages/s9_audit.py",
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **회상** — 사용자 지시 2026-10-14
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 3번(감독 이름)·4번(감독 부임후 성적)·5번(팀내 불화)은 딥서치에서 못
    #  > 찾으면 **llm 이 찾게 한다** … llm 을 **전략예측 및 서치**로 쓰는 거다.
    #
    #  🔴🔴 이것은 **새 종류**다 — 지금까지 LLM 은 글자(질의·이름)와 **문서에서
    #     뽑은 사실**만 냈다. 이 파일은 **문서 없이 모델 기억**을 받는다.
    #  🔴 그래서 계약을 따로 뒀다(`test_v29_2_recall.py` 8개): 원천이 박히고,
    #     확률 경로가 그것을 **못 읽고**, 딥서치가 찾은 칸을 **안 덮고**,
    #     *"모른다"* 가 실패가 아니다.
    "app/core/stages/s4b_recall.py",
    "app/core/ocr.py",                 # 라인업 캡처 판독
    "app/core/llm.py",                 # 통로 자체
    "app/core/rank.py",                # 재정렬(검색 순서 · 사실 추출의 입력)
    "app/core/rerank.py",
    # ── 🔴 **질의 글자**(사실이 아니다 · 위 해석)
    "app/core/findwriter.py",
    "app/core/querywriter.py",
    "app/core/stages/s1_resolve.py",
    "app/core/stages/s3_docs.py",
    "app/queries.py",
    "app/querygate.py",
)

#: 🔴 LLM 을 부르는 글자(D46 으로 코드만 본다)
LLM_WORDS = ("core.llm", "llm.ask", "llm.json", "_llm.")


def _code(rel: str) -> str:
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_x1_deleted_modules_are_gone() -> None:
    """🔴🔴 **X1** — 처분표의 "삭제" 모듈은 **파일이 없다**."""
    left = [rel for rel in GONE if (ROOT / rel).is_file()]
    assert not left, f"🔴 아직 남아 있다: {left}"


def test_x1_no_one_imports_them() -> None:
    """🔴 **X1** — `app/` 어디서도 그것을 들여오지 않는다(확률·등급 경로 포함)."""
    bad: list[str] = []
    names = [Path(rel).stem for rel in GONE]
    for p in sorted((ROOT / "app").rglob("*.py")):
        said = _code(p.relative_to(ROOT).as_posix())
        for name in names:
            if f"import {name}" in said or f"{name}." in said:
                bad.append(f"{p.relative_to(ROOT)} → {name}")
    assert not bad, f"🔴 지운 단계를 부른다: {bad}"


def test_x2_llm_is_called_only_for_facts() -> None:
    """🔴🔴 **X2** — LLM 을 부르는 파일은 **사실 추출·캡처 판독**뿐이다."""
    bad: list[str] = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        rel = p.relative_to(ROOT).as_posix()
        if rel in LLM_OK:
            continue
        said = _code(rel)
        if any(w in said for w in LLM_WORDS):
            bad.append(rel)
    assert not bad, f"🔴 LLM 을 부르는 자리가 남았다(X2): {bad}"


def test_card_has_no_llm_prose_blocks() -> None:
    """🔴 ㉔ — **최종 평 긴 블록**은 여전히 없다. ⚠️ 전술 예측은 **되살렸다**.

    🔴🔴 지시 2026-10-14 — *"전술예상도 해야 한다 … 전술 전문가다 … 자료로만 …
       지어내지 않는다"*. 그래서 `tactic_long`(🎓 전술 전문가 예측)은 **있어야**
       한다. ⚠️ 종전 이 계약은 그 이름을 금지했다 — 직접 지시가 덮었다.
    🔴 대신 **되살리지 않은 것**을 못 박는다: `say_long`(최종 평 긴 블록)·
       `verdict_long`. 그 둘은 카드 서술을 LLM 한 편으로 덮는 블록이었다.
    """
    said = _code("app/core/render.py")
    for bad in ("say_long", "verdict_long"):
        assert bad not in said, (
            f"🔴 `{bad}` 는 되살리지 않았다 — 카드 서술을 LLM 한 편으로 덮는다")
    assert "tactic_long" in said, (
        "🔴 전술 전문가 예측 블록이 없다(지시 2026-10-14) — 되살려야 한다")


def test_w_score_check_exists() -> None:
    """🔴🔴 **(w) 스코어 꼴** — 되살린 까닭의 핵심. 이게 없으면 되살리면 안 된다.

    지운 사고 그대로다(커밋 `a7448733`): 평이 근거에 없는 `4-3` 을 적었고 검열
    (r) 은 낱개 숫자로 쪼개 통과시켰다. 🔴 꼴 그대로 대조하는 검사가 **있어야**
    한다.
    """
    said = (ROOT / "app/core/stages/s9_say.py").read_text(encoding="utf-8")
    assert "_SCORE" in said, (
        "(w) 🔴🔴 스코어 꼴 검사가 없다 — `4-3` 을 지어내도 안 걸린다"
        "(이 단계를 지운 그 사고다)")
    assert "_scores_of" in said and "_scores_in" in said, (
        "(w) 🔴 묶음의 스코어와 문장의 스코어를 둘 다 뽑아야 대조가 된다")
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages import s9_say
    assert s9_say._scores_in("전반에 4-3 으로 앞선다") == ["4-3"], (
        "(w) 🔴 스코어를 못 뽑는다")
    assert s9_say._scores_in("최근 5경기 득점 2.4골") == [], (
        "(w) 🔴 무해한 소수를 스코어로 잡는다 — 거짓 위반이 난다")


def test_say_does_not_touch_probability() -> None:
    """🔴🔴 사용자 결정 2026-10-14 — LLM 전술 단계는 **쓰기만** 한다.

    `pipeline.with_say` 가 덮는 칸이 **글 칸뿐**인지 센다. 확률·등급 칸을 덮으면
    절대 규칙(LLM 출력이 `direction`·`weight`·`strength`·`survival`·`verdict` 에
    닿으면 실패)을 깬다.
    """
    import ast as _ast
    said = (ROOT / "app/core/pipeline.py").read_text(encoding="utf-8")
    i = said.index("def with_say(")
    body = said[i:]
    tree = _ast.parse(_ast.unparse(_ast.parse(body).body[0]))
    keys: set[str] = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call) and isinstance(node.func, _ast.Attribute) \
                and node.func.attr == "model_copy":
            for kw in node.keywords:
                if kw.arg == "update" and isinstance(kw.value, _ast.Dict):
                    for k in kw.value.keys:
                        if isinstance(k, _ast.Constant):
                            keys.add(str(k.value))
    assert keys, "🔴 `with_say` 가 `model_copy(update=…)` 를 안 쓴다"
    banned = {"our_prob", "adj_prob", "market", "judgement", "grade",
              "survival", "verdict", "matchup", "sim", "prob"}
    bad = keys & banned
    assert not bad, (
        f"🔴🔴 `with_say` 가 확률·판정 칸을 덮는다: {sorted(bad)} — LLM 전술 단계는 "
        "**쓰기만** 한다(사용자 결정 2026-10-14)")
