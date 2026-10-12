"""🔴🔴 **1번 감독 의도 = 경기 우선순위 지수** — 수정 지시서 2026-10-12.

> [1a] ③ 구조 사실. 팀별 **시즌 최강 XI 가치**(신원표 id 기준, 시즌 출전 시간
> 상위 11명을 포지션 틀에 맞춘 가치 합). 신원표가 서기 전엔 계산하지 않는다 —
> **빈칸·🔴**.
> [1b] ⑦ 전략 판정, 판정 함수 **앞**. 우선순위 지수 = 오늘 XI 가치 합 ÷ 최강 XI
> 가치 합(0~1+). 전략 판정 입력에 넣는다. **LLM 판정이 지수와 반대면 버리고 코드 판정.**
> [1c] ⑧ 축0 — 지수를 축0 값에 **또 곱하지 않는다**(이중 반영 금지). 축0 근거
> 줄과 **K5 반증 조건 입력**으로만 쓴다.
> [1d] ⑥ 배치. 감독 발언 → V4, 다음 경기 일정 → V3. **확률 경로 없음**(C1·C7).

🔴 P1 — 우선순위 지수를 축0 에 곱하면 실패.
🔴 P2 — V3·V4 가 λ·확률 경로에 나타나면 실패.
⚠️ **시즌 출전 시간은 어디에도 없다**(실측 2026-10-12: fotmob 선수단 페이지의
   `minutes_played` 는 **번역 사전 열쇠**였다). 🔴 그래서 최강 XI 는 **창 10경기
   선발 빈도 + 선수 가치**로 세우고 그 사실을 사유에 적는다(지어내지 않는다).
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════
# [1a] 최강 XI 가치 — 재료가 없으면 빈칸·🔴
# ══════════════════════════════════════════════════════════════════

def test_best_xi_needs_value_and_starts() -> None:
    from app.core import priority as pr
    got, why = pr.best_xi(starts={}, value={})
    assert got is None and "🔴" in why


def test_best_xi_sums_top_eleven() -> None:
    from app.core import priority as pr
    starts = {f"p{i}": (10 - i) for i in range(14)}
    value = {f"p{i}": 100.0 for i in range(14)}
    got, why = pr.best_xi(starts=starts, value=value)
    # 🔴 상위 11명만 센다
    assert got == 1100.0, (got, why)
    assert "11" in why


def test_best_xi_says_the_measurement_gap() -> None:
    """🔴 #3·#4 — *"시즌 출전 시간이 아니다"* 를 사유가 적는다.

    ⚠️ 11명이 **다 서야** 지수를 센다 — 그래서 시험도 11명을 준다
       (한 명만 주면 *"1/11 명만 값이 있다"* 가 맞는 사유다).
    """
    from app.core import priority as pr
    starts = {f"p{i}": (12 - i) for i in range(12)}
    value = {f"p{i}": 10.0 for i in range(12)}
    _got, why = pr.best_xi(starts=starts, value=value)
    assert "선발 빈도" in why


# ══════════════════════════════════════════════════════════════════
# [1b] 지수
# ══════════════════════════════════════════════════════════════════

def test_index_is_today_over_best() -> None:
    from app.core import priority as pr
    got, why = pr.index_of(today=800.0, best=1000.0)
    assert abs(got - 0.80) < 1e-9, (got, why)


def test_index_is_none_when_best_missing() -> None:
    from app.core import priority as pr
    got, why = pr.index_of(today=800.0, best=None)
    assert got is None and ("🔴" in why or "없다" in why)


def test_index_over_one_is_kept() -> None:
    """⚠️ 오늘 XI 가 평소보다 강하면 **1 을 넘는다**(0~1+ · 자르지 않는다)."""
    from app.core import priority as pr
    got, _why = pr.index_of(today=1200.0, best=1000.0)
    assert got > 1.0


def test_llm_verdict_loses_to_the_index() -> None:
    """🔴 [1b] — *"LLM 판정이 지수와 반대면 버리고 코드 판정"*."""
    from app.core import priority as pr
    # 🔴 지수가 낮은데(아꼈다) LLM 이 `평소 그대로` 라고 하면 **버린다**
    said, why = pr.verdict_check("평소 그대로", index=0.60)
    assert said != "평소 그대로" and "🔴" in why
    # ⚠️ 지수가 높은데 LLM 이 로테이션이라고 하면 그것도 버린다
    said2, why2 = pr.verdict_check("로테이션·체력 관리", index=0.98)
    assert said2 != "로테이션·체력 관리" and "🔴" in why2
    # ✅ 맞으면 그대로 둔다
    same, _ = pr.verdict_check("로테이션·체력 관리", index=0.60)
    assert same == "로테이션·체력 관리"


def test_verdict_check_needs_an_index() -> None:
    from app.core import priority as pr
    said, why = pr.verdict_check("평소 그대로", index=None)
    assert said == "평소 그대로" and ("없다" in why or "⬜" in why)


# ══════════════════════════════════════════════════════════════════
# [1c] P1 — 축0 에 곱하지 않는다
# ══════════════════════════════════════════════════════════════════

def test_p1_axis0_never_multiplies_the_index() -> None:
    from app.core import matchup
    said = ast.unparse(ast.parse(inspect.getsource(matchup.axis0).lstrip()))
    for bad in ("priority", "pri_index", "우선순위"):
        assert bad not in said, bad


def test_p1_axis0_gets_it_as_a_reason_only() -> None:
    """🔴 지수는 **근거 줄**로만 간다 — 그 자리가 코드에 있다."""
    said = _src("app/core/stages/s2e_matchup.py")
    assert "priority" in said, "🔴 ⑧ 이 지수를 재료로 안 받는다"
    assert "axis0_said" in said or "pri_said" in said


# ══════════════════════════════════════════════════════════════════
# [1d] P2 — V3·V4 는 확률 경로에 없다
# ══════════════════════════════════════════════════════════════════

def test_p2_v3_v4_not_in_lambda_path() -> None:
    said = _src("app/core/probmodel.py")
    for bad in ("V3", "V4", "coach_intent", "coach_quote"):
        assert bad not in said, bad


def test_p2_routing_sends_coach_to_v4_only() -> None:
    """🔴 배치표가 감독 발언을 **V4**(와 가설)로만 보낸다."""
    import yaml
    box = yaml.safe_load(
        (ROOT / "config/variable_routing.yaml").read_text(encoding="utf-8"))
    for kind in ("coach_intent", "coach_quote"):
        places = list(dict(box["types"][kind])["places"])
        assert "V4" in places
        for bad in ("axis0", "axis1", "axis3", "lambda_const"):
            assert bad not in places, (kind, places)


def test_1d_card_says_word_vs_action() -> None:
    """🔴 ⑫ 검증이 *"말·일정 ↔ 행동(지수)"* 일치를 적는다."""
    said = _src("app/core/stages/s6c_check.py")
    assert "우선순위" in said and "행동" in said


# ══════════════════════════════════════════════════════════════════
# 배선
# ══════════════════════════════════════════════════════════════════

def test_wired_before_the_strategy_verdict() -> None:
    """🔴 [1b] — ⑦ 전략 판정 **앞**에서 센다."""
    said = _src("app/core/pipeline.py")
    assert "priority" in said
    assert said.index("priority") < said.index("s2d_strategy.plan(") \
        if "s2d_strategy.plan(" in said else True


def test_k5_gets_the_index() -> None:
    """🔴 [1c] — 지수는 **K5 반증 조건**의 입력이다."""
    said = _src("app/core/pipeline.py")
    i = said.index("build_break_conditions")
    assert "priority" in said[i:i + 400], said[i:i + 200]


# ══════════════════════════════════════════════════════════════════
# ⑯ 1겹 — 세 줄이 제자리에 있다
# ══════════════════════════════════════════════════════════════════

def test_layer1_has_the_three_lines() -> None:
    """🔴 ⑯ — 상성 줄 아래 `🎯 우선순위` · 확률 줄 아래 `📜 스크립트` ·
    결론 줄에 `🧪 반증` 요약."""
    said = _src("app/core/layer1.py")
    i_edge = said.index("said_edge = edge_block(card)")
    i_pri = said.index("axis0_said")
    i_prob = said.index("out.append(_probs(card))")
    i_script = said.index("📜 스크립트")
    i_brk = said.index("🧪 반증")
    assert i_edge < i_pri < i_prob < i_script < i_brk, (
        i_edge, i_pri, i_prob, i_script, i_brk)


def test_verify_long_prints_word_vs_action() -> None:
    said = _src("app/core/render.py")
    assert "word_action" in said and "🗣" in said
