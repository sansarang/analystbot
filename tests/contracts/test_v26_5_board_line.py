"""🔴🔴 **P5 보드 줄은 파이프라인이 센 글자 하나다**(DV1~DV3).

⚠️ 실사고 2026-10-14 00:45(알사드–알힐랄 예상 XI 판): 카드의 보드 줄이
   `render._board_line` 안에서 **공정 확률을 1/p 로 되뒤집어** 다시 셌다. 그래서
   ① 사용자가 준 **원 배당 5.00/4.40/1.53** 이 아니라 마진 제거된
   5.40432/4.75581/1.65373 이 *"원 배당"* 으로 찍혔고 ② 그 수로 마진을 다시 세서
   **0.0%**(실제 8.1%)가 됐고 ③ `gaps=[]` 를 손으로 박아 파이프라인은
   `접는다` 인데 카드는 **"조건부까지 허용"** 이라 적었다.

🔴 그래서 잠근다 — 수는 `core/divergence.said_of` **한 번만** 만들고
   (`pipeline._divergence_of`), 카드는 그 글자를 **들고 가 찍기만** 한다.
"""
from __future__ import annotations

import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_dv1_카드가_괴리_글자를_들고_간다() -> None:
    """DV1 — `Card.divergence` 칸이 있고 `card_of` 가 층에서 채운다."""
    from app.core.schema import Card
    assert "divergence" in Card.model_fields
    said = inspect.getsource(__import__("app.core.pipeline",
                                        fromlist=["x"]).card_of)
    assert 'divergence=str(box.get("divergence")' in said


def test_dv2_파이프라인이_그_칸을_채운다() -> None:
    """DV2 — `_divergence_of` 결과가 층(`layers`)으로 들어간다."""
    said = (ROOT / "app/core/pipeline.py").read_text(encoding="utf-8")
    i = said.index("said_div, said_fold = _divergence_of(")
    assert 'layers["divergence"] = said_div' in said[i:i + 400], said[i:i + 300]


def test_dv3_렌더러가_다시_세지_않는다() -> None:
    """DV3 — 글자가 있으면 렌더러는 **그대로 찍는다**(되뒤집기 전에 돌아간다).

    🔴 `1.0 / float(...)`(공정 확률 → 배당 되뒤집기)와 손으로 박은 `gaps=[]` 가
       **이 글자가 없을 때만** 닿아야 한다 — 그 둘보다 **먼저** `return` 이 온다.
    """
    said = inspect.getsource(__import__("app.core.render",
                                        fromlist=["x"])._board_line)
    i_ret = said.index('return f"- **보드(사용자 캡처 · 표시만)** — {said_pipe}"')
    assert i_ret < said.index("1.0 / float("), "되뒤집기가 먼저 온다"
    assert i_ret < said.index("gaps=[]"), "손으로 박은 ⬜ 목록이 먼저 온다"
