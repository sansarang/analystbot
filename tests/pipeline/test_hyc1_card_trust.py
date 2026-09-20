"""[HYC-1] 못 믿을 추출 카드를 `confirmed` 로 세고 있었다.

🔴 실측 2026-09-20 (운영 Redis 추출 상자 42쪽):
     conflict=true      17 / 42
     source 빈 칸       30 / 42
     fetched_at 빈 칸   42 / 42   ← **전건**
   그런데 ⑤는 이 셋을 하나도 보지 않고 `out` 값이 있으면 증거로 실었다.
   오늘 인천-대전에서 유일하게 확인된 `xi_confirmed` 가 바로 그런 카드다 —
   무고사·하창래가 **결장 목록과 선발 XI에 동시에** 있고(conflict=true),
   출처가 비어 어느 쪽이 맞는지 판정할 수 없었다.

🔴 **검증 근거는 코드가 쓴 것만 쓴다**(사용자 결정 2026-09-20).
     수집 시각 → 상자 최상위 `gathered_at` (위성이 코드로 쓴다)
     출처      → `sources_fed` (그 LLM 호출에 **실제로 넣은** 기사 URL 목록)
     구조 소스 → `out_src` 가 `llm` 이 아니면 그 소스명 + 조회 시각이 출처다
   LLM 이 채운 `source`·`fetched_at` 은 **검사에 쓰지 않는다.** 이름만
   `llm_source`·`llm_fetched_at` 으로 바꿔 남긴다(나중에 지어낸 출처 비율을
   재는 자료다).

⚠️ 반대 위험 — 규칙을 걸면 증거가 줄어든다. 그것이 정직한 방향이다:
   종전에는 **검증할 수 없는 값을 검증된 것처럼** 세고 있었다.
⚠️ 공식 결장(`_cache_absences`)은 상자가 아니라 판정 캐시에서 온다 —
   상자 카드가 못 믿을 것이어도 **공식 결장은 그대로 센다.**
"""
from __future__ import annotations

import inspect

import pytest

# ── 픽스처 (지시문 §5) ──────────────────────────────────────────────
#: 상자에 수집 시각이 없다 → 검증 불가
f_box_no_gathered_at = {
    "teams": {"home": {"team": "H", "out": ["가"], "out_src": "llm",
                       "sources_fed": ["https://n.example/a"]},
              "away": {"team": "A", "out": [], "out_src": "llm",
                       "sources_fed": ["https://n.example/a"]}},
}

#: LLM 카드인데 **코드가 아는 출처**가 없다 → 검증 불가
f_box_no_sources_fed = {
    "gathered_at": "2026-09-20T08:47:35+00:00",
    "teams": {"home": {"team": "H", "out": ["가"], "out_src": "llm"},
              "away": {"team": "A", "out": ["나"], "out_src": "llm",
                       "sources_fed": []}},
}

#: 구조 소스(FotMob)에서 온 카드 → 소스명 + 조회 시각이 출처다 → 통과
f_box_struct_source = {
    "gathered_at": "2026-09-20T08:47:35+00:00",
    "teams": {"home": {"team": "H", "out": ["Sung-wook Jo"],
                       "out_src": "fotmob", "conflict": False},
              "away": {"team": "A", "out": [], "out_src": "fotmob",
                       "conflict": False}},
}

#: LLM 이 `source` 를 채웠어도 `sources_fed` 가 없으면 미상이다
f_llm_source_ignored = {
    "gathered_at": "2026-09-20T08:47:35+00:00",
    "teams": {"home": {"team": "H", "out": ["가"], "out_src": "llm",
                       "llm_source": "http://v.daum.net/v/20260919164442056"},
              "away": {"team": "A", "out": ["나"], "out_src": "llm",
                       "llm_source": "https://sports.news/x"}},
}

#: 오늘 인천 상자 그대로 — conflict=true
f0920_incheon = {
    "gathered_at": "2026-09-20T08:47:35+00:00",
    "sources_fed": ["https://n.example/incheon"],
    "teams": {"home": {"team": "Incheon United",
                       "out": ["Stefan Mugosa", "Tae-heui Lee"],
                       "xi": ["Stefan Mugoša"], "xi_status": "lastStarting11",
                       "conflict": True, "out_src": "fotmob"},
              "away": {"team": "Daejeon Citizen",
                       "out": ["Masatoshi Ishida"], "conflict": True,
                       "out_src": "fotmob"}},
}


def _trust(box, side):
    from app.flow.nodes.n05_evidence import card_trust

    return card_trust(box, (box.get("teams") or {}).get(side) or {})


# ── ① 규칙 그 자체 ────────────────────────────────────────────────
def test_수집_시각이_없으면_미상이다():
    ok, why = _trust(f_box_no_gathered_at, "home")
    assert ok is False
    assert "수집" in why or "gathered_at" in why, why


def test_코드가_아는_출처가_없으면_미상이다():
    for side in ("home", "away"):          # 칸이 없는 경우 · 빈 목록인 경우
        ok, why = _trust(f_box_no_sources_fed, side)
        assert ok is False, side
        assert "출처" in why or "sources_fed" in why, why


def test_구조_소스_카드는_통과한다():
    """🔴 FotMob·부상표는 **코드가 조회한 것**이다 — 기사 URL 이 필요 없다."""
    ok, why = _trust(f_box_struct_source, "home")
    assert ok is True, why


def test_LLM_이_쓴_출처는_검사에_쓰지_않는다():
    """🔴 `llm_source` 가 그럴듯해도 그것은 **모델이 만든 문자열**이다."""
    for side in ("home", "away"):
        ok, why = _trust(f_llm_source_ignored, side)
        assert ok is False, f"{side}: LLM 출처로 통과시켰다 ({why})"


def test_충돌_카드는_미상이다():
    """오늘 인천 — 무고사가 결장 목록과 XI 에 동시에 있다."""
    ok, why = _trust(f0920_incheon, "home")
    assert ok is False
    assert "충돌" in why or "conflict" in why, why


# ── ② ⑤·⑥ 배선 ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_못_믿을_카드는_증거가_되지_않고_사유가_남는다():
    from app.flow.ctx import Ctx
    from app.flow.nodes import n05_evidence as N5
    from app.flow.nodes import n06_verdict as N6
    from app.flow.state import State

    st = State(run_id="r", game_id="11338", sport="soccer", league="K리그1",
               home="Incheon United", away="Daejeon Citizen",
               kickoff_utc="2026-09-20T10:00:00+00:00", pick_side="away")
    st.n04_hyp = [{"id": "H_break", "refuted_means": "강화",
                   "vars": [{"var": "xi_confirmed", "is_core": True}]}]
    ctx = Ctx()
    ctx.inject = {"extract": f0920_incheon, "absences": []}

    st = await N5.run(st, ctx)
    rows = [e for e in (st.n05_evidence or []) if e["var"] == "xi_confirmed"]
    assert rows, "왜 못 믿는지를 남기지 않았다 — 행 자체가 없다"
    assert rows[0].get("value") is None, "못 믿을 값을 증거로 실었다"
    assert rows[0].get("untrusted_reason"), "사유 칸이 비었다"

    st = await N6.run(st, ctx)
    assert st.n06_verdict["per_var"]["xi_confirmed"] == "unknown"


@pytest.mark.asyncio
async def test_공식_결장은_상자와_무관하게_센다():
    """⚠️ 반대 위험 — 상자를 막느라 **공식 결장까지** 버리면 안 된다."""
    from app.flow.ctx import Ctx
    from app.flow.nodes import n05_evidence as N5
    from app.flow.state import State

    st = State(run_id="r", game_id="1", sport="baseball", league="KBO",
               home="LG Twins", away="Hanwha Eagles",
               kickoff_utc="2026-09-20T09:00:00+00:00", pick_side="home")
    st.n04_hyp = [{"id": "H_break", "vars": [{"var": "lineup_out",
                                              "is_core": True}]}]
    ctx = Ctx()
    ctx.inject = {"extract": f_box_no_sources_fed,
                  "absences": ["LG Twins의 홍길동 결장 — 오늘 라인업에서 빠짐"]}
    st = await N5.run(st, ctx)
    got = [e for e in (st.n05_evidence or []) if e.get("value")]
    assert got, "공식 결장이 있는데 증거가 통째로 비었다"


# ── ③ 위성이 코드로 출처를 남기는가 ────────────────────────────────
def test_위성이_sources_fed_를_코드로_쓴다():
    from app.collectors import satellite as SAT

    src = "\n".join(ln for ln in inspect.getsource(SAT.extract_game_facts)
                    .splitlines() if not ln.strip().startswith("#"))
    assert "sources_fed" in src, "LLM 에 넣은 기사 URL 을 기록하지 않는다"


def test_LLM_출처는_이름을_바꿔_남긴다():
    from app.collectors import satellite as SAT

    src = "\n".join(ln for ln in inspect.getsource(SAT.extract_game_facts)
                    .splitlines() if not ln.strip().startswith("#"))
    assert "llm_source" in src, "LLM 이 쓴 source 를 그대로 두거나 버렸다"


def test_추출_스키마에_fetched_at_이_없다():
    """🔴 채우는 코드가 0건인 칸이었다 — 42/42 전건 빈 칸(실측)."""
    from app.collectors.satellite import _extract_prompt
    from app.engine.scout_config import EXTRACT_SCHEMA

    assert "fetched_at" not in EXTRACT_SCHEMA
    assert "fetched_at" not in _extract_prompt("H", "A", [("u", "본문")])
