"""🔴🔴 **지시서 §1-3·§1-4·§1-5** — 게이트2 조건·예산 분할·재실행 규율.

작업 지시서(오픈월드):

> **§1-3 게이트2 조건 재정의** — 5경기 중 4경기에서 `verified_vars ≥ 6` 이면서
> **그중 에이전트 출처 ≥ 3**. 구조 자료만으로 채운 6개는 **통과가 아니다.**
> `tools/gate2_report.py` 에 **출처 열(agent/structured)** 을 추가한다.
>
> **§1-4 예산 분할** — 경기당 출력 **40k 유지**, **팀별 상한 25k**, 합계 40k
> 초과 금지. 한 팀이 예산을 다 써서 다른 팀이 0개가 되는 일을 막는다.
> 추론 강도가 low 인지 **원장에 기록해** 확인한다.
>
> **§1-5 노르웨이 쪽 재실행** — DNS 장애로 오염된 결과라 다시 돌린다. **장애로
> 끊긴 실행은 재실행 대상이고, 정상 종료된 실행은 재실행하지 않는다**는 구분을
> CLAUDE.md 규율에 한 줄로 적는다.

⚠️ `25k × 2 = 50k > 40k` 다 — **일부러 그렇다.** 한 팀이 25k 를 다 쓰면 다른
   팀에 15k 가 남고, 둘이 균등히 쓰면 각 20k 다. 🔴 **합계 40k 가 벽**이다.
"""
from __future__ import annotations


# ══════════════════════════════════════════════════════════════════
# §1-4 예산 — 팀별 25k · 합계 40k
# ══════════════════════════════════════════════════════════════════

def test_wo1_4_팀별_상한이_25k_다():
    """🔴 선언이 **설정에** 있어야 한다(코드에 박지 않는다)."""
    from app import rules
    got = rules.llm_budget()["per_match"]
    assert int(got["output_tokens"]) == 40_000, got
    assert int(got["per_side_output_tokens"]) == 25_000, (
        "🔴 팀별 출력 상한 25k 가 설정에 없다(지시서 §1-4)")


def test_wo1_4_팀별_몫이_25k_다():
    """🔴 `MatchBudget` 이 그 수를 **쓴다** — 선언만 있으면 없는 것이다(#2)."""
    from app import solar
    side = solar.MatchBudget(side=True)
    assert side.max_out == 25_000, side.max_out


def test_wo1_4_합계_40k_가_벽이다():
    """🔴🔴 *"합계 40k 초과 금지"* — 두 쪽이 **같은 지갑**을 함께 본다.

    ⚠️ `25k × 2 = 50k` 다. 🔴 한 쪽이 25k 를 다 쓰면 다른 쪽은 **15k** 만
       남아야 한다 — 그러려면 둘이 **경기 합계**를 공유해야 한다.
    """
    from app import solar
    pot = solar.MatchPot()
    a = solar.MatchBudget(side=True, pot=pot)
    b = solar.MatchBudget(side=True, pot=pot)
    # 🔴 a 가 자기 몫(25k)을 다 쓴다
    a.output_tokens = 25_000
    pot.output_tokens = 25_000
    assert a.can_call()[0] is False, "🔴 자기 몫을 넘겼는데 계속 쓴다"
    # ✅ b 는 **아직 쓸 수 있다**(합계 40k 중 15k 남았다)
    ok_b, why_b = b.can_call()
    assert ok_b is True, f"🔴 다른 쪽이 막혔다 — 15k 가 남아 있다: {why_b}"
    # 🔴 그런데 b 가 15k 를 쓰면 **합계 40k** 에서 멈춘다
    b.output_tokens = 15_000
    pot.output_tokens = 40_000
    ok2, why2 = b.can_call()
    assert ok2 is False and "합계" in why2, (
        f"🔴 **합계 40k 를 넘겼는데 계속 쓴다** — 지시서 §1-4: {why2}")


def test_wo1_4_에이전트가_쪽_예산을_받는다():
    """🔴 **배선**(#2) — `_run_agent` 가 쪽 예산과 **같은 지갑**을 넘겨야 한다."""
    import inspect

    from app import analyze
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(analyze.gather))
    assert "MatchPot" in body, (
        "🔴 경기 **합계 지갑**(`MatchPot`)을 만들지 않는다 — 두 쪽이 각자 25k 를 "
        "다 쓰면 합계 50k 가 된다(지시서 §1-4 위반)")


def test_wo1_4_추론_강도를_원장에_적는다():
    """🔴 *"추론 강도가 low 인지 **원장에 기록해** 확인한다"* — §1-4."""
    from app import solar
    # ⚠️ `LEDGER_REQUIRED` 에 넣으면 **모든 공급자**에 걸린다 — DeepSeek 는
    #    추론 강도 손잡이가 없어 그 줄이 터진다(실측: 5건이 빨개졌다).
    #    🔴 그래서 **Solar 에만** 요구한다.
    assert "reasoning_effort" in solar.LEDGER_REQUIRED_SOLAR, (
        f"🔴 원장이 추론 강도를 **안 적는다** — 확인할 수가 없다: "
        f"{solar.LEDGER_REQUIRED_SOLAR}")
    # 🔴 그리고 **실제로 적히나** — `chat` 이 그 칸을 넣는지 본다
    import inspect

    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(solar))
    assert '"reasoning_effort": str(body.get("reasoning_effort")' in body, (
        "🔴 원장 줄에 그 칸을 **안 넣는다**(#2 배선)")


# ══════════════════════════════════════════════════════════════════
# §1-3 게이트2 조건 — 에이전트 출처 ≥ 3
# ══════════════════════════════════════════════════════════════════

def test_wo1_3_게이트2_조건이_재정의됐다():
    """🔴 *"`verified_vars ≥ 6` 이면서 **그중 에이전트 출처 ≥ 3**"*."""
    from tools import gate2_report
    assert gate2_report.NEED_VERIFIED == 6
    assert gate2_report.NEED_AGENT == 3, (
        "🔴 에이전트 출처 최소 수가 없다 — *'구조 자료만으로 채운 6개는 통과가 "
        "아니다'*(지시서 §1-3)")


def test_wo1_3_보고에_출처_열이_있다():
    """🔴 *"`tools/gate2_report.py` 에 **출처 열(agent/structured)** 을 추가"*."""
    from tools import gate2_report
    assert hasattr(gate2_report, "sources_of"), (
        "🔴 출처를 가르는 자리가 없다 — `gate2_report.sources_of`")
    # 🔴 실측 로그 한 줄로 잰다(에이전트가 낸 변수 수가 거기 적혀 있다)
    line = ("· 세포 에이전트:San Diego Padres: §3 에이전트 — `done`(턴 13) · "
            "후보 10개 → **검증 통과 6개** · 도구 36회")
    got = gate2_report.sources_of([line])
    assert got["agent"] == 6, got


def test_wo1_3_합격_판정이_두_조건을_같이_본다():
    """🔴🔴 **구조 자료만으로 채운 6개는 통과가 아니다.**"""
    from tools import gate2_report
    assert gate2_report.passes({"verified": 8, "agent": 0}) is False, (
        "🔴 에이전트 출처 0 인데 통과시켰다")
    assert gate2_report.passes({"verified": 6, "agent": 3}) is True
    assert gate2_report.passes({"verified": 5, "agent": 5}) is False


# ══════════════════════════════════════════════════════════════════
# §1-5 재실행 규율
# ══════════════════════════════════════════════════════════════════

def test_wo1_5_재실행_규율이_CLAUDE_md_에_있다():
    """🔴 *"장애로 끊긴 실행은 재실행 대상, 정상 종료는 재실행하지 않는다"*.

    ⚠️ 규율은 **파일에** 있어야 한다 — 대화로만 아는 지시는 다음 세션이 모른다
       (CLAUDE.md 머리글의 실사고).
    """
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    said = (root / "CLAUDE.md").read_text(encoding="utf-8")
    assert "장애로 끊긴 실행" in said, (
        "🔴 재실행 규율이 CLAUDE.md 에 없다(지시서 §1-5)")
    assert "정상 종료" in said, said[-200:]
