"""🔴🔴 **v5-A §2 — DeepSeek 호출 사양.** 단가는 **공식 문서**에서 왔다.

부록 v5-A §2 원문:

> 모델 — 추론 모드가 있는 모델을 쓴다. … Claude Code 가 **공식 api-docs·
> pricing 페이지를 직접 읽어** `config/llm.yaml` 의 `deepseek:` 칸에 모델
> ID·입력/캐시/출력 단가·확인 날짜를 적는다. **매체 수치는 쓰지 않는다.**
> 시작은 저가 모델(Flash 계열, 추론 켬).
> 키·결제 — 키는 로컬 `.env` 의 `DEEPSEEK_API_KEY`, **이름만** `.env.example`.
> 웹 차단 — DeepSeek 호출에는 **도구를 하나도 넘기지 않는다**(M42).
> 예산 — 경기당 입력 30,000 · 출력 15,000. 하루·월은 **Solar 와 합산**.

🔴 **읽은 곳**: `https://api-docs.deepseek.com/quick_start/pricing`
   (2026-10-04 · 봇이 직접 받아 글자를 뽑았다)
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]















def test_v5A_2_키는_로컬_env_에만_있다():
    """🔴 *"키는 로컬 `.env`, **이름만** `.env.example`"*."""
    ex = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=" in ex
    # 🔴🔴 **값이 있으면 안 된다**(예시에 키가 새면 그것이 유출이다)
    for line in ex.splitlines():
        if line.startswith("DEEPSEEK_API_KEY"):
            assert line.strip() == "DEEPSEEK_API_KEY=", line
    # ⚠️ `.env` 키 ⊆ `.env.example` 계약은 기존 것이 지킨다
    env = ROOT / ".env"
    if env.exists():
        assert "DEEPSEEK_API_KEY" in env.read_text(encoding="utf-8")
