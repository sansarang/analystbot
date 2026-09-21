"""[SOLAR-1] Upstage Solar 를 공급자로 잇는다 (사용자 지시 2026-09-21).

🔴 사용자 지시: *"일본, 한국은 solar 로 대체하고 테스트를 해봐라 ·
   그리고 해외도 가능한지 테스트를 해봐라 · 가능하지 않다면 해외는 gemini 로
   계속한다 · 문제는 무료 api 키들이 제 역할을 못해서 그런다"*

🔴 실측 2026-09-21 (키 실호출):
     GET /v1/models                 → 200 · `solar-pro4` 목록에 있다
     한국어 K리그 추출               → 1.5s · 귀속 정확(무고사·이태희→인천)
     일본어 J리그 추출               → 4.7s · 귀속 정확
     영어 EPL · 스페인어 · 이탈리아어 → 1.7~2.5s · 전부 귀속 정확
   ⚠️ 즉 **해외도 가능하다.** "가능하지 않다면 gemini" 조건은 발동하지 않는다.

⚠️ Solar 는 **유료**다. `FREE_PROVIDERS` 에 넣지 않는다 — 넣으면 기존 토큰
   상한이 이 경로를 그냥 통과시킨다. 유료 후보로 두면 `PAID_LLM_ALLOWED`
   와 상한이 그대로 걸린다.
"""
from __future__ import annotations

import pytest


def test_solar가_공급자로_등록됐다():
    from app.llm.provider import _KIND_TO_CLASS, OpenAICompatProvider

    assert _KIND_TO_CLASS.get("solar") is OpenAICompatProvider


def test_base_url은_실측한_주소다():
    """🔴 주소를 추측하지 않는다 — `/v1/models` 가 200 을 준 것을 확인했다."""
    from app.llm.provider import _DEFAULT_BASE

    assert _DEFAULT_BASE["solar"] == "https://api.upstage.ai/v1"


def test_기본_모델은_실측한_이름이다():
    """🔴 모델명을 추측하지 마라(이 파일의 다른 주석들과 같은 규율).
    `/v1/models` 응답에 `solar-pro4` 가 있었다."""
    from app.llm.provider import _PROVIDER_DEFAULT_MODEL

    assert _PROVIDER_DEFAULT_MODEL["solar"] == "solar-pro4"


def test_키가_설정에서_온다():
    from app.config import Settings

    assert "solar_api_key" in Settings.model_fields


def test_solar는_유료로_분류된다():
    """⚠️ 무료로 분류하면 토큰 상한이 이 경로를 그냥 통과시킨다."""
    from app.llm.judge_route import is_free, is_paid_provider

    assert is_paid_provider("solar") is True
    assert is_free("solar", "solar-pro4") is False


def test_사슬_문자열로_고를_수_있다():
    """`FORM_CHAIN="solar/solar-pro4,groq/…"` 형태."""
    from app.llm.provider import build_provider

    p = build_provider("solar", "solar-pro4")
    assert p.name == "solar"
    assert "upstage" in (p.base_url or "")


def test_키가_없으면_크래시하지_않는다():
    """절대 규칙 3 — 키 부재로 크래시하지 않는다."""
    from app.llm.provider import build_provider

    class _S:
        solar_api_key = None
        xai_api_key = None
        solar_base_url = None

    p = build_provider("solar", "solar-pro4", settings=_S())
    assert p is not None
