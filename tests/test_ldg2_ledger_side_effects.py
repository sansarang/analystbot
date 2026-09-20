"""[LDG-2 2026-09-20] 사람이 넣은 판정 행에 **저장 전용 기록이 안 붙었다.**

🔴 실측 2026-09-20 운영:
     원장 1,393행 중 odds_at_verdict 298 · odds_closing 107 · clv **97**
     오늘 58경기 중 원장 행 있음 **7** (전부 `ledger_add` 로 넣은 페이블 판정)
     그 7행의 market_flow·odds_open·gate_label 전부 NULL

`tools/ledger_add.py` 가 행만 넣고 `_record_side_effects` 를 부르지 않았다.
`grade_pending` 이 `odds_closing` 은 채우지만 `clv` 는 `odds_at_verdict` 가
있어야 계산되므로(`_CLV_SAVE["closing"]`), **CLV 가 영원히 NULL** 이었다.

⚠️ 머리말이 "채점·CLV 는 여기서 채우지 않는다"고 적은 것은 **채점**을 말한다.
   `odds_at_verdict` 는 채점이 아니라 **판정 시각의 배당**이고, 그 시각을 아는
   것은 이 도구뿐이다 — 나중에 결과 잡이 복원할 수 없다.
"""
from __future__ import annotations

import inspect


def test_ledger_add가_저장전용_기록을_부른다():
    """🔴 배선 — 넣고 끝내면 그 행은 영영 CLV 가 없다."""
    import tools.ledger_add as L

    src = inspect.getsource(L)
    assert "_record_side_effects" in src, "ledger_add 가 저장 전용 기록을 부르지 않는다"


def test_판정시각_배당은_넣은_시각으로_찍는다():
    """⚠️ 지금 배당이 아니라 **행이 들어온 시각**의 스냅샷이어야 한다."""
    import tools.ledger_add as L

    src = inspect.getsource(L._run)
    assert "clv_at" in src and "verdict" in src, src[-600:]


def test_승패가_아니면_CLV를_쓰지_않는다():
    """🔴 `record_clv` 는 고른 쪽을 모르면 아무것도 쓰지 않는다.

    총점·팀토탈 행은 `predicted_side` 가 None 이므로 여기서 걸러진다 —
    반대쪽 배당으로 채우면 CLV 가 통째로 무의미해진다.
    """
    from tools.ledger_add import build_row

    r = build_row(game_id=1, sport="mlb", league="MLB", date="2026-09-20",
                  judge_by="fable_chat", market="total", line=8.5,
                  side="under", odds=1.9, note=None)
    assert r["predicted_side"] is None

    r2 = build_row(game_id=1, sport="mlb", league="MLB", date="2026-09-20",
                   judge_by="fable_chat", market="ml", line=None,
                   side="home", odds=1.9, note=None)
    assert r2["predicted_side"] == "home"


def test_ledger_add는_LLM을_부르지_않는다():
    """🔴 사람이 손으로 돌리는 도구가 ⑫ 서술의 무료 한도를 태우면 안 된다.

    실측 2026-09-20: `_record_side_effects` 를 그대로 부르자 한 행에서
    gemini 402 + groq 429 로 **사슬 두 개를 소진**했다. U12 분석만 LLM 을
    쓰므로 그 자리만 끈다.
    """
    import inspect

    import tools.ledger_add as L
    from app.engine.pick_ledger import _record_side_effects

    assert "analysis=False" in inspect.getsource(L._run)
    sig = inspect.signature(_record_side_effects)
    assert sig.parameters["analysis"].default is True, "판정 경로 기본값이 바뀌면 안 된다"
