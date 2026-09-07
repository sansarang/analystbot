"""자료6(라인업 의도) 야구 배선 — 배선 지도가 잡은 구멍 (2026-09-07).

🔴 `_attach_lineup_intent` 는 `pipeline.py` 의 `if sport not in _BB_SKIP_OLD`
   안에 있어 **축구에서만** 불렸다. 그런데 야구 쪽에도:
     · 프롬프트 자리 `{{LINEUP_INTENT_JSON}}`  (prompts.py:67)
     · payload 함수 `intent_payload`           (matchup.py:260)
     · 렌더 인자 `LINEUP_INTENT_JSON=`         (matchup.py:563)
   가 다 있었다. 야구 판정은 그 자리에 **항상 빈 객체**를 받고 있었다.
   09-01 `ensure_analysis_cache` 호출처 0곳과 같은 유형이다.

⚠️ 붙이는 자리는 프리페치가 아니라 **확정 라인업 재판정 경로**다(사용자 결정):
   의도 해석은 확정 타순이 있어야 의미가 있고, 잠정 단계 해석은 비용·잡음만
   늘린다. 그래서 잠정 단계에서 비어 있는 것은 **정상**이다.
"""
from __future__ import annotations

import json
import pathlib

import pytest

SRC = pathlib.Path("app/pipeline.py").read_text(encoding="utf-8")


def _seg():
    i = SRC.index("async def _run_baseball_matchups")
    j = SRC.index("\nasync def ", i + 10)
    return SRC[i:j]


# ── 배선 ────────────────────────────────────────────────────────
def test_material6_is_wired_into_the_rejudge_loop():
    seg = _seg()
    assert "_attach_lineup_intent" in seg, "야구 재판정에 자료6 이 없다"


def test_material6_only_on_the_final_path():
    """잠정 단계에서는 부르지 않는다 — 비용·잡음."""
    seg = _seg()
    i = seg.index("await _attach_lineup_intent(")
    head = seg[max(0, i - 900):i]
    assert "if allow_final:" in head, "잠정 단계에서도 부른다"
    assert "lineup_is_confirmed" in head, "확정 타순 조건이 없다"


def test_confirmation_rule_is_not_copied():
    """확정 판별의 원본은 `matchup.lineup_is_confirmed` 하나다."""
    seg = _seg()
    i = seg.index("await _attach_lineup_intent(")
    head = seg[max(0, i - 900):i]
    assert "from app.engine.matchup import lineup_is_confirmed" in head
    assert "lineup_status" not in head.split("if allow_final:")[-1], \
        "확정 조건을 여기 베꼈다"


def test_failure_does_not_block_the_judgement():
    seg = _seg()
    i = seg.index("await _attach_lineup_intent(")
    tail = seg[i:i + 500]
    assert "except Exception" in tail
    assert "판정은 계속" in tail


def test_soccer_branch_is_untouched():
    """pipeline.py 의 축구 전용 분기는 그대로 둔다(지시)."""
    assert "if sport not in _BB_SKIP_OLD:" in SRC
    i = SRC.index("if sport not in _BB_SKIP_OLD:")
    assert "_attach_lineup_intent" in SRC[i:i + 300]


# ── 재료가 실제로 실리는가 ──────────────────────────────────────
def test_prompt_carries_real_data_when_intent_exists():
    from app.engine.matchup import intent_payload, render_matchup_prompt

    jg = {"sport": "kbo", "home": "H", "away": "A", "research": {},
          "lineup_intent": {"items": {"home": [
              {"change_type": "order", "symbol": "▲",
               "scoring_dir": "상승", "reason": "3번 타자 복귀"}]},
              "headline": {"home": "중심타선 복귀"}}}
    pay = intent_payload(jg)
    assert pay and "home" in pay
    out = render_matchup_prompt(jg, {"home": [{"runs": 3}], "away": [{"runs": 1}]},
                                {}, None)
    i = out.index("6. 라인업 의도")
    block = out[i:i + 400]
    assert "{}" != json.dumps(pay, ensure_ascii=False)
    assert "3번 타자 복귀" in block, "자료6 자리가 여전히 비어 있다"


def test_empty_intent_is_normal_before_confirmation():
    """🔴 잠정 단계에서 비어 있는 것은 **정상**이다 — 결함이 아니다."""
    from app.engine.matchup import intent_payload, render_matchup_prompt

    jg = {"sport": "kbo", "home": "H", "away": "A", "research": {}}
    assert intent_payload(jg) == {}
    out = render_matchup_prompt(jg, {"home": [{"runs": 3}], "away": [{"runs": 1}]},
                                {}, None)
    i = out.index("6. 라인업 의도")
    assert "{}" in out[i:i + 200]


# ── L1 대조 등록 여부 ───────────────────────────────────────────
def test_material6_has_no_measurable_numeric_field():
    """자료6 은 **해석**이다 — 구조상 수치 필드가 없다.

    `변경`·`부호`·`득점방향`·`사유`·`요약` 전부 문자열이고, 프롬프트도 이 칸을
    "사실이 아니라 해석"으로 명시해 받는다(prompts.py:67).
    L1(`fact_audit`)은 **수치 대조기**라 대조할 것이 없다 — 등록 대상이 아니다.
    ⚠️ 사유 문장 안에 숫자가 섞일 수는 있다("3번 타자 복귀"). 그것은 인용이
       아니라 서술이라 감사 대상이 아니다. 감사해야 할 것은 **수치 필드**이고,
       그런 필드가 생기면 이 테스트가 깨져 L1 등록을 검토하게 한다.
    """
    from app.engine.matchup import intent_payload

    pay = intent_payload({"lineup_intent": {"items": {"home": [
        {"change_type": "order", "symbol": "▲", "scoring_dir": "상승",
         "reason": "3번 타자 복귀"}]}, "headline": {"home": "x"}}})

    def numeric_fields(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                yield from numeric_fields(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                yield from numeric_fields(v, f"{path}[{i}]")
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            yield path, o

    found = list(numeric_fields(pay))
    assert not found, f"자료6 에 수치 필드가 생겼다 — L1 등록을 검토하라: {found}"


def test_material6_is_in_the_rebuild_list_not_cache():
    """재조립 목록 등재 — 재판정마다 다시 붙는다."""
    seg = _seg()
    for other in ("attach_starter_recent", "attach_material10", "_ctx"):
        assert other in seg
    assert "_attach_lineup_intent" in seg
