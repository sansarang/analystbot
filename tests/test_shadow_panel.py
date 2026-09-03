"""[감시 L2·L3] 검사역·독립 판정.

가장 중요한 것은 **오염 방지**다 — L3 프롬프트에 주심 판정이 들어가면
독립 판정이 아니라 추인이 된다.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

VERDICT = {"p_home": 0.66, "우세": "home", "확신도": "중",
           "근거": ["자료9: 불펜 ERA 5.39 vs 5.38", "자료1: 3득점-26실점"],
           "변수": ["표본 3경기"]}
MATERIALS = '9. 불펜: {"home": {"era": 5.39}, "away": {"era": 5.38}}'


# ─────────────── 오염 방지 (최중요) ───────────────

def test_independent_prompt_cannot_receive_the_main_verdict():
    """🔴 **시그니처로 막는다.** 플래그 분기가 아니라 인자가 아예 없다."""
    from app.engine.shadow_panel import build_independent_prompt

    params = list(inspect.signature(build_independent_prompt).parameters)
    assert params == ["materials"], f"주심 판정을 넘길 통로가 있다: {params}"


def test_independent_prompt_contains_no_verdict_string():
    """렌더 결과에도 주심 판정이 없어야 한다."""
    from app.engine.shadow_panel import build_independent_prompt

    out = build_independent_prompt(MATERIALS)
    # ⚠️ "근거"·"p_home" 은 **이 프롬프트 자신의 출력 계약** 문구라 누출이 아니다.
    #    주심 판정의 **값**이 새는지를 본다.
    import json as _json

    for leak in ("0.66", '"우세"', '"확신도"', _json.dumps(VERDICT["근거"],
                                                         ensure_ascii=False)):
        assert leak not in out, f"L3 프롬프트에 주심 흔적: {leak}"
    assert "p_home" in out          # 출력 계약은 있어야 한다
    assert MATERIALS in out         # 자료는 들어간다


def test_reviewer_and_independent_are_separate_functions():
    """같은 함수에 플래그로 분기하면 언젠가 그 분기가 잘못 탄다."""
    from pathlib import Path

    src = Path("app/engine/shadow_panel.py").read_text(encoding="utf-8")
    assert "def build_reviewer_prompt" in src
    assert "def build_independent_prompt" in src
    assert "if reviewer" not in src and "mode=" not in src


def test_reviewer_prompt_does_include_the_verdict():
    """검사역은 반대다 — 판정이 검사 **대상**이라 넣어야 한다."""
    from app.engine.shadow_panel import build_reviewer_prompt

    out = build_reviewer_prompt(VERDICT, MATERIALS)
    assert "0.66" in out and "검사역" in out
    assert "빈 배열" in out, "이의가 없으면 없다고 하게 해야 한다"


# ─────────────── 이의 유효성 (기계 대조 3케이스) ───────────────

@pytest.mark.parametrize("objection,expected", [
    ({"자료": "자료9", "설명": "불펜 ERA 9.99 로 적었으나 원문과 다르다"}, True),
    ({"자료": "자료9", "설명": "ERA 5.39 는 원문 그대로다"}, False),
    ({"자료": "자료9", "설명": "표본 대비 과신이다"}, None),
])
def test_objection_validity_three_cases(objection, expected):
    """대조 불가는 **None** — "틀렸다"가 아니라 "사람이 봐야 한다"다."""
    from app.engine.shadow_panel import _is_valid

    assert _is_valid(objection, MATERIALS) is expected


def test_objection_without_a_citation_is_unverifiable():
    from app.engine.shadow_panel import _is_valid

    assert _is_valid({"설명": "ERA 9.99"}, MATERIALS) is None


# ─────────────── 대상 선정 ───────────────

def test_targets_are_gate_passers_capped_by_config():
    """게이트 통과만, 상한은 config 에서 읽는다(사본 금지)."""
    from app.engine.pick_ledger import GATE_BOARD_ONLY, GATE_RECOMMENDED
    from app.engine.shadow_panel import pick_targets

    games = [{"game_id": i, "gate_result": GATE_RECOMMENDED,
              "matchup": {"p_home": 0.50 + i / 100}} for i in range(1, 9)]
    games.append({"game_id": 99, "gate_result": GATE_BOARD_ONLY,
                  "matchup": {"p_home": 0.90}})
    got = pick_targets(games)
    assert len(got) == 5, "슬레이트 상한"
    assert 99 not in [g["game_id"] for g in got], "보드만은 대상이 아니다"
    # 확신 높은 순 = 0.5 에서 먼 순
    assert got[0]["matchup"]["p_home"] == pytest.approx(0.58)


# ─────────────── 휴면·격리 ───────────────

def test_dormant_without_a_key(monkeypatch):
    """키가 없으면 전체 휴면 — 카드에 영향 0."""
    from app.config import Settings
    from app.engine.shadow_panel import run_panel

    monkeypatch.setattr("app.config.get_settings",
                        lambda: Settings(_env_file=None, gemini_api_key=""))
    res = asyncio.run(run_panel(None, None, [{"game_id": 1}]))
    assert res == {"targets": 0, "reviewed": 0, "shadowed": 0, "skipped": 0}


def test_panel_never_raises(monkeypatch):
    """P4 — 감시 실패가 발송을 막으면 안 된다."""
    from app.config import Settings
    from app.engine import shadow_panel as sp

    monkeypatch.setattr("app.config.get_settings",
                        lambda: Settings(_env_file=None, gemini_api_key="k"))

    def boom(*a, **k):
        raise RuntimeError("대상 선정 폭발")

    monkeypatch.setattr(sp, "pick_targets", boom)
    res = asyncio.run(sp.run_panel(None, None, []))
    assert res["targets"] == 0          # 예외가 밖으로 나오지 않는다


def test_shadow_uses_the_main_clip_function():
    """클립은 주심 함수를 import 해서 쓴다 — 사본 금지."""
    from pathlib import Path

    src = Path("app/engine/shadow_panel.py").read_text(encoding="utf-8")
    assert "from app.engine.matchup import clip_p_home" in src
    assert "0.32" not in src and "0.68" not in src


# ─────────────── Gemini 클라이언트 ───────────────

def test_retry_once_on_429_then_gives_up():
    """무료 티어를 두들기지 않는다 — 429 는 30초 후 **1회만**."""
    from pathlib import Path

    src = Path("app/llm/gemini.py").read_text(encoding="utf-8")
    assert "for attempt in (1, 2)" in src
    assert "RETRY_AFTER_429_SEC" in src
    from app.llm.gemini import RETRY_AFTER_429_SEC

    assert RETRY_AFTER_429_SEC >= 30


def test_min_interval_is_built_into_the_client():
    """호출부가 잊어도 지켜지도록 클라이언트에 내장한다."""
    from pathlib import Path

    src = Path("app/llm/gemini.py").read_text(encoding="utf-8")
    assert "async def _throttle" in src and "await _throttle()" in src
    from app.config import Settings

    assert Settings(_env_file=None).gemini_min_interval_sec >= 6


def test_lenient_parse_never_fixes_content():
    """파싱만 관대하게 — 내용을 우리가 원하는 모양으로 주무르지 않는다."""
    from app.llm.gemini import parse_json_lenient

    assert parse_json_lenient("```json\n[{\"a\":1}]\n```") == [{"a": 1}]
    assert parse_json_lenient("앞말 {\"p_home\": 0.5} 뒷말") == {"p_home": 0.5}
    assert parse_json_lenient("판정을 못 하겠습니다") is None   # 지어내지 않는다
    assert parse_json_lenient(None) is None


def test_no_sdk_dependency_added():
    """의존성을 늘리지 않는다 — REST 직접 호출."""
    from pathlib import Path

    src = Path("app/llm/gemini.py").read_text(encoding="utf-8")
    # ⚠️ **import 문만 본다.** 주석의 "google-genai 를 넣지 않는다"까지
    #    잡으면 그 다짐을 적을 수 없게 된다.
    import re as _re

    code = "\n".join(l for l in src.splitlines()
                     if not l.lstrip().startswith(("#", "\"\"\"", "⚠️", "🔴")))
    assert not _re.search(r"^\s*(import|from)\s+google", code, _re.M)
    assert "httpx" in src
    # pyproject 에도 SDK 가 없어야 한다
    pj = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "google-genai" not in pj and "google-generativeai" not in pj


def test_gemini_is_not_wired_into_judgement_or_deepsearch():
    """🔴 감시 전용이다. 판정·딥서치 경로에 연결하지 않는다."""
    from pathlib import Path

    for path in ("app/engine/matchup.py", "app/engine/deepsearch.py",
                 "app/engine/team_form.py", "app/llm/provider.py"):
        src = Path(path).read_text(encoding="utf-8")
        assert "gemini" not in src.lower() or "app.llm.gemini" not in src, path
