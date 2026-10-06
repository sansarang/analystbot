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
# §1-4 예산 — **쪽 상한 < 경기 합계** (수는 표가 든다)
# ══════════════════════════════════════════════════════════════════
#
# ⚠️ 종전 이 계약들은 `25_000`·`40_000` 을 **손으로 박아** 뒀다. 🔴 사용자가
#    상한을 올리자(2026-10-06 ③: 하위 8,000 · 경기당 64,000) 여섯 계약이
#    한꺼번에 빨개졌다 — 사본의 병이다(#1).
# 🔴 그래서 **수를 읽고 관계를 센다**: 쪽 몫은 합계보다 작아야 하고, 쪽 둘을
#    더하면 합계를 넘어야 한다(그래야 "쉬는 쪽의 몫을 쓴다"가 성립한다).

def _caps() -> dict:
    from app import rules
    return rules.llm_budget()["per_match"]


def test_wo1_4_쪽_상한이_선언돼_있다():
    """🔴 선언이 **설정에** 있어야 한다(코드에 박지 않는다)."""
    got = _caps()
    tot, side = int(got["output_tokens"]), int(got["per_side_output_tokens"])
    assert tot > 0 and side > 0, got
    # 🔴 쪽은 합계보다 **작다** — 같거나 크면 합계가 벽이 아니다
    assert side < tot, (side, tot)
    # 🔴 쪽 둘을 더하면 합계를 **넘는다** — 쉬는 쪽의 몫을 쓸 여유가 그것이다
    assert side * 2 > tot, (
        f"🔴 쪽 {side} × 2 ≤ 합계 {tot} — 한 쪽이 쉬어도 그 몫을 못 쓴다"
        f"(지시서 §1-4 가 막으려는 바로 그 일이다)")


def test_wo1_4_쪽_몫을_코드가_쓴다():
    """🔴 `MatchBudget` 이 그 수를 **쓴다** — 선언만 있으면 없는 것이다(#2)."""
    from app import solar
    side = solar.MatchBudget(side=True)
    assert side.max_out == int(_caps()["per_side_output_tokens"]), side.max_out


def test_wo1_4_합계가_벽이다():
    """🔴🔴 *"합계 초과 금지"* — 두 쪽이 **같은 지갑**을 함께 본다.

    ⚠️ 쪽 × 2 > 합계다. 🔴 한 쪽이 제 몫을 다 쓰면 다른 쪽에는 **합계 − 쪽**만
       남아야 한다 — 그러려면 둘이 **경기 합계**를 공유해야 한다.
    """
    from app import solar
    cap = _caps()
    tot, per = int(cap["output_tokens"]), int(cap["per_side_output_tokens"])
    pot = solar.MatchPot()
    a = solar.MatchBudget(side=True, pot=pot)
    b = solar.MatchBudget(side=True, pot=pot)
    # 🔴 a 가 자기 몫을 다 쓴다
    a.output_tokens = per
    pot.output_tokens = per
    assert a.can_call()[0] is False, "🔴 자기 몫을 넘겼는데 계속 쓴다"
    # ✅ b 는 **아직 쓸 수 있다**(합계에서 `tot - per` 가 남았다)
    ok_b, why_b = b.can_call()
    assert ok_b is True, (
        f"🔴 다른 쪽이 막혔다 — {tot - per} 가 남아 있다: {why_b}")
    # 🔴 그런데 b 가 그 나머지를 쓰면 **합계**에서 멈춘다
    b.output_tokens = tot - per
    pot.output_tokens = tot
    ok2, why2 = b.can_call()
    assert ok2 is False and "합계" in why2, (
        f"🔴 **합계 {tot} 를 넘겼는데 계속 쓴다** — 지시서 §1-4: {why2}")




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
