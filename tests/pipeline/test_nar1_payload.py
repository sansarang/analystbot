"""[NAR-1] ⑫ 입력에 금지 항목이 들어가지 못하게 **기계가 막는다.**

🔴 지금은 `_payload` 가 우연히 깨끗하다. 계약이 없으면 다음 사람이 `odds` 를
   한 줄 넣어도 아무도 모른다 — 이 저장소가 반복해 겪은 종류의 사고다.
🔴 막는 것 셋(CLAUDE.md 대원칙 · 지시문 STEP 11):
     배당 숫자 · 시즌 누적 · 상대전적(BvP/H2H)
🔴 **승자·확률·확신은 코드 값이다.** LLM 은 설명만 한다 — 페이로드에 그 값이
   들어가되 LLM 이 바꿀 수 없다는 것이 이 노드의 전제다.
"""
from __future__ import annotations

import pytest

from app.flow.state import State


# ── [SWAP-3T 2026-09-22] 이 파일은 **LLM 서술 경로**를 시험한다 ────────────
#
# 🔴 사용자 지시로 서술이 **템플릿**이 됐다("서술도 템플릿으로 바꿔라").
#    `judge.llm_verdict` 가 꺼져 있으면 ⑫가 LLM 을 아예 안 부르므로
#    이 파일의 시험 대상 경로가 돌지 않는다.
# 🔴 **그 경로를 지우지 않았다** — 스위치 한 줄로 되돌릴 수 있어야 하고,
#    되돌렸을 때 종전대로 도는지는 **계약이 지켜야 한다.**
# ⚠️ 템플릿 동작은 `tests/test_nollm.py` 가 따로 잠근다.
import pytest as _pytest


@_pytest.fixture(autouse=True)
def _llm_verdict_on(monkeypatch):
    monkeypatch.setattr("app.engine.matchup._llm_verdict_on", lambda: True)


def _state():
    s = State(run_id="r", game_id="1", sport="baseball", league="MLB",
              home="H", away="A", kickoff_utc="2026-09-19T01:40:00Z")
    s.pick_side = "away"
    s.n02_market = {"p": {"home": 0.5, "away": 0.5},
                    "odds": {"home": 1.9, "away": 2.05},
                    "derivatives": {"total": {"line": 8.5, "over": 1.8}}}
    s.n05_evidence = [{"var": "lineup_out", "value": ["X 결장"],
                       "raw_excerpt": "X 결장", "source_url": "http://x"}]
    s.n07_adjust = [{"var": "lineup_out", "pp": 2.5}]
    s.n08_pcode = {"p_code_pick": 0.61}
    s.n09_conf = {"grade": "B"}
    s.n11_value = {"pick_type": "구조", "structure": {"market": "total_under"}}
    return s


def test_배당이_페이로드에_들어가지_않는다():
    """🔴 ②가 배당을 들고 있어도 ⑫에는 흘러가면 안 된다."""
    from app.flow.nodes.n12_text import _payload

    blob = str(_payload(_state()))
    for banned in ("odds", "1.9", "2.05", "derivatives"):
        assert banned not in blob, f"{banned} 가 서술 입력에 있다"


def test_금지_키가_없다():
    from app.flow.nodes.n12_text import _payload

    keys = set(_payload(_state()))
    for banned in ("odds", "season", "season_official", "h2h", "bvp",
                   "market", "p_market", "recent6"):
        assert banned not in keys, banned


def test_코드가_정한_값은_그대로_실린다():
    from app.flow.nodes.n12_text import _payload

    p = _payload(_state())
    assert p["p_code"] == 0.61
    assert p["confidence"] == "B"
    assert p["pick_side"] == "away"


@pytest.mark.asyncio
async def test_규격_미달이면_카드를_만들지_않는다():
    """🔴 두 번 시도해도 4문장이 아니면 `hallucination=True` 로 멈춘다."""
    from app.flow.ctx import Ctx
    from app.flow.nodes import n12_text as N

    s = await N.run(_state(), Ctx(inject={"narration": "한 문장뿐이다."}))
    assert s.n12_text["hallucination"] is True
    assert s.n12_text["sentences"] == []


@pytest.mark.asyncio
async def test_입력에_없는_숫자를_쓰면_반려한다():
    from app.flow.ctx import Ctx
    from app.flow.nodes import n12_text as N

    bad = ("원정을 고른다. 확률은 61% 다. 상대 선발은 방어율 3.72 다. 리스크가 있다.")
    s = await N.run(_state(), Ctx(inject={"narration": bad}))
    assert s.n12_text["hallucination"] is True, s.n12_text
