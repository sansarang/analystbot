"""[#82] 2단 해석봇 **배선** 테스트.

⚠️ 이 파일이 지키는 것은 기능이 아니라 **호출처**다.
   실사고 2026-08-27: 2단(`interpret_side`)은 구현·테스트가 다 돼 있었지만
   `app/` 안에 호출처가 **0개**였다. 임시 스크립트로만 돌았고 텔레그램에는
   5칸 ▲▼가 한 번도 나가지 않았다. "구현 완료"와 "배선 완료"는 다르다.
"""
import ast
import asyncio
import pathlib

import pytest

from app.engine.card import CELLS, card_summary_line, render_state_card

ROOT = pathlib.Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ 호출처 존재

def _calls_in_app(name: str) -> list[str]:
    """app/ 전체에서 그 이름을 **실제로 호출**하는 파일 목록."""
    hits = []
    for path in (ROOT / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            called = (f.id if isinstance(f, ast.Name)
                      else f.attr if isinstance(f, ast.Attribute) else None)
            if called == name and path.name != f"{name}.py":
                hits.append(str(path.relative_to(ROOT)))
    return sorted(set(hits))


@pytest.mark.parametrize("name", ["interpret_slate", "build_card",
                                  "render_state_card", "card_summary_line",
                                  "record_verdicts"])
def test_stage2_has_a_real_caller_in_app(name):
    """🔴 app/ 안에 호출처가 없으면 그 코드는 사용자에게 도달하지 않는다."""
    callers = [c for c in _calls_in_app(name)
               if not c.startswith("app/engine/interpreter.py:")]
    assert callers, (f"{name}() 호출처가 app/ 안에 없다 — 구현만 되고 "
                     f"배선되지 않았다. 임시 스크립트는 배선이 아니다.")


def test_build_analysis_calls_stage2_before_judging():
    """2단은 판정 **전에** 돌아야 한다 — 판정이 카드를 볼 수 있어야 한다."""
    src = (ROOT / "app/pipeline.py").read_text(encoding="utf-8")
    i_cells = src.index("await _attach_cell_verdicts(")
    i_judge = src.index('await progress(3, 4, "Claude 판정")')
    assert i_cells < i_judge, "2단이 판정 뒤에 있다"


# ------------------------------------------------------------------ 출력 표시

def _jg(cells=None, status="판정"):
    facts = {k: {"facts": [f"{k} 사실"], "source": "테스트", "metrics": {}}
             for k, _ in CELLS}
    return {"home": "Kia Tigers", "away": "Lotte Giants",
            "home_kr": "KIA", "away_kr": "롯데", "game_id": 1,
            "card": {"home": facts, "away": facts, "unknown_labels": []},
            "cells": cells or {"home": {}, "away": {}},
            "cells_status": status}


def test_card_shows_symbols_and_one_line_reasons():
    jg = _jg({"home": {"bullpen": {"symbol": "▲", "reason": "직전 3명 투입"}},
              "away": {"bullpen": {"symbol": "▼", "reason": "직전 9명 투입"}}})
    out = "\n".join(render_state_card(jg))
    assert "불펜 가용: 롯데 ▼ | KIA ▲" in out
    assert "· KIA 불펜 가용 ▲ — 직전 3명 투입" in out
    assert "· 롯데 불펜 가용 ▼ — 직전 9명 투입" in out


def test_unjudged_cells_show_a_dot_not_an_equals():
    """🔴 판정 못 한 칸을 '='로 채우면 판정한 것처럼 보인다."""
    out = "\n".join(render_state_card(_jg()))
    assert "=" not in out
    assert "·" in out


def test_total_llm_failure_is_stated_not_hidden():
    """오늘 한화 사례 — 3중 폴백 전멸 시 '판정 미수행'을 명시한다."""
    out = "\n".join(render_state_card(_jg(status="판정 미수행")))
    assert "판정 미수행" in out
    assert card_summary_line(_jg(status="판정 미수행")).endswith("(사실만 수집됨)")


def test_summary_counts_but_does_not_conclude():
    """요약은 칸을 셀 뿐 승자를 말하지 않는다 — 결론은 3단의 몫이다."""
    line = card_summary_line(_jg({
        "home": {"bullpen": {"symbol": "▲"}, "starter": {"symbol": "▲"}},
        "away": {"bullpen": {"symbol": "▼"}, "starter": {"symbol": "="}}}))
    assert "KIA 우세 2칸" in line
    for word in ("승", "이긴", "추천"):
        assert word not in line


def test_card_uses_no_angle_brackets():
    """HTML parse_mode로 나가므로 꺾쇠가 있으면 메시지가 깨진다."""
    out = "\n".join(render_state_card(_jg(
        {"home": {"bullpen": {"symbol": "▲", "reason": "x"}}, "away": {}})))
    assert "<" not in out and ">" not in out


# ------------------------------------------------------------------ 목 모드 안전

def test_stage2_never_hits_network_under_force_mock():
    """🔴 절대 규칙 3 — 강제 목 모드에서 2단이 외부를 치면 안 된다."""
    from app.config import Settings
    from app.engine.interpreter import interpret_side

    s = Settings(force_mock=True, interpreter_provider="groq", groq_api_key="x")
    card = _jg()["card"]["home"]
    asyncio.run(interpret_side(card, "KIA", settings=s, baselines={}))


def test_facts_survive_a_total_judge_failure():
    """🔴 판정이 실패해도 수집한 사실은 나가야 한다.

    실측 2026-08-27: LLM 4개 벤더가 전부 소진된 날, 크롤링으로 모은 사실이
    전부 있는데 화면에는 "판정 실패" 두 줄만 나갔다. 카드가 통째로 사라졌다.
    """
    from app.pipeline import DETAIL_SEP, _render_card

    g = _jg(status="판정 미수행")
    g.update({"status": "scheduled", "p_claude": None, "starts_at_kst": "18:30",
              "league": "KBO", "market_board": [], "research": {}})
    out = _render_card({"date": "2026-08-27", "sport": "kbo", "games": [g],
                        "picks": [], "recommended": []})
    easy, detail = out.split(DETAIL_SEP, 1)
    assert "판정 실패" in easy, "실패 사실을 위장하면 안 된다"
    assert "🃏" in easy, "수집한 사실이 사라졌다"
    assert "불펜 가용:" in detail, "5칸 카드가 상세에 없다"
