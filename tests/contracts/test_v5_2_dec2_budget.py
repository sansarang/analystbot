"""🔴🔴 **결정 ② — 예산 입력 300k·출력 40k · 팀별 반씩**.

사용자 결정 2026-10-04:

> 경기당 **입력 300k·출력 40k**로 올린다. **하루 $3·월 $40은 그대로.** MLB
> 실측이 경기당 $0.09이니 하루 30경기도 $3 안이다. 출력 20k를 넘은 건
> **Solar의 추론 토큰** 때문이고, 그건 **결함이 아니라 모델 특성**이다. 대신
> 두 가지를 같이 건다. **추론 강도가 low인지 확인**하고, **한 팀 에이전트가
> 예산을 다 써서 다른 팀이 0개가 되는 일이 없도록 팀별로 예산을 반씩 나눈다**
> (밀워키 0개·파드리스 6개 사례).

══════════════════════════════════════════════════════════════════
🔴 실측 2026-10-04 (게이트2 2판) — **두 경기가 같은 자리에서 다쳤다**
══════════════════════════════════════════════════════════════════

```
MLB  밀워키 budget_cut 출력 20,312/20,000 → 변수 **0개** · 파드리스 6개 → 합 11
KBO  한화   budget_cut 출력 20,682/20,000 → 변수 **0개** · 키움   2개 → 합 **2**
```
"""
from __future__ import annotations


def test_dec2_경기당_예산이_올랐다():
    """🔴 입력 300k · 출력은 **표가 든다**.

    ⚠️ 종전엔 `40_000` 을 박아 뒀다. 🔴 사용자가 2026-10-06 ③ 에서 경기당
       **64,000** 으로 올렸다 — 수를 계약에 박으면 올릴 때마다 빨개진다(#1).
    🔴 계약이 보는 것은 *"종전(20k)보다 올랐고, 하위 8개 × 하위 상한과 맞는다"* 다.
    """
    from app import rules
    b = rules.llm_budget()
    got, sub = b["per_match"], b["per_subtask"]
    assert int(got["input_tokens"]) == 300_000, got
    tot = int(got["output_tokens"])
    assert tot > 20_000, f"🔴 결정 ② 전(20k)으로 되돌아갔다: {tot}"
    # 🔴 **하위 8개 × 하위 상한 = 경기 합계** — 수가 서로 맞아야 한다
    assert tot == 8 * int(sub["output_tokens"]), (tot, sub["output_tokens"])


def test_dec2_돈_상한은_그대로다():
    """🔴 *"하루 \\$3·월 \\$40은 **그대로**"* — 돈은 사용자가 정한 것이다."""
    from app import rules
    got = rules.llm_budget()
    # ⚠️ 하루 상한은 **사용자가 바꾼다**(2026-10-05: $3 → $5) — 수를 박으면
    #    그 결정이 계약을 빨갛게 만든다. 🔴 월 상한과의 관계만 본다.
    assert 0 < float(got["per_day_usd"]) < float(got["per_month_usd"])
    assert float(got["per_month_usd"]) == 40.0


def test_dec2_추론_강도가_low_다():
    """🔴 ②의 조건 하나 — **확인**이다(올리는 것이 아니다).

    ⚠️ 출력이 20k 를 넘은 것은 **추론 토큰**이고 그것은 모델 특성이다 — 그래서
       강도가 `low` 인지 **확인하고** 예산을 올린다.
    """
    import pathlib

    import yaml
    root = pathlib.Path(__file__).resolve().parents[2]
    box = yaml.safe_load(
        (root / "config" / "llm.yaml").read_text(encoding="utf-8"))
    # ⚠️ 칸은 `model:` 아래다(처음 `solar:` 로 찾아 빗나갔다)
    said = str((box.get("model") or {}).get("reasoning_effort") or "")
    assert said == "low", f"🔴 추론 강도가 `{said}` 다 — ②는 `low` 를 요구한다"
    # 🔴 실측값이 **함께 적혀 있어야** 한다 — *"low 가 싸다"* 를 전제로 예산을
    #    짜면 안 된다는 사실이 그 수에 있다(low 219 · medium 178 · high 159).
    assert (box.get("model") or {}).get(
        "reasoning_effort_measured_2026_10_04"), (
        "🔴 추론 강도 실측값이 없다 — 손잡이가 비용을 단조롭게 줄이지 않는다")


def test_dec2_추론_강도가_실제로_호출에_실린다():
    """🔴🔴 **배선**(#2) — 설정에 적혀 있고 **안 보내면** 없는 것이다."""
    import inspect

    from app import solar
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(solar))
    assert "reasoning_effort" in body, (
        "🔴 `reasoning_effort` 를 설정에만 적고 **호출에 안 싣는다**(#2)")


def test_dec2_팀별로_반씩_나눈다():
    """🔴🔴 **한 팀이 다 쓰면 다른 팀이 0개가 되는 것**을 막는다.

    ⚠️ 실측: 밀워키가 출력 예산을 다 써 `budget_cut` 으로 **0개**를 냈고,
       파드리스가 6개를 냈다. KBO 는 한화 0개 · 키움 2개로 **합 2개**였다.
    """
    from app import solar
    full = solar.MatchBudget()
    half = solar.MatchBudget(share=0.5)
    assert half.max_in == full.max_in // 2, (half.max_in, full.max_in)
    assert half.max_out == full.max_out // 2, (half.max_out, full.max_out)


def test_dec2_한쪽이_다_써도_다른쪽_몫이_남는다():
    """🔴 **두 쪽이 각자 자기 몫**을 갖는다 — 합쳐 쓰지 않는다."""
    from app import solar
    a = solar.MatchBudget(share=0.5)
    b = solar.MatchBudget(share=0.5)
    # 🔴 a 가 자기 몫을 다 쓴다. ⚠️ 칸 이름은 `output_tokens` 다
    a.output_tokens = a.max_out + 1
    assert a.can_call()[0] is False, "🔴 자기 몫을 넘겼는데 계속 쓴다"
    # ✅ b 는 **멀쩡하다**
    assert b.can_call()[0] is True, (
        "🔴 한쪽이 다 쓰자 **다른 쪽도 막혔다** — 몫을 안 나눴다")


def test_dec2_에이전트가_쪽마다_몫을_받는다():
    """🔴🔴 **배선** — `MatchBudget(share=…)` 을 만들어도 **부르는 곳**이 없으면
    실행에서는 아무것도 안 바뀐다(이 저장소가 반복해 다친 자리 · #2).
    """
    import inspect

    from app import analyze
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(analyze._run_agent))
    # ══════════════════════════════════════════════════════════════
    # 🔴 **`share` → `side=True`** 로 바뀌었다 — 지시서 §1-4 (2026-10-05)
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 결정 ②는 *"팀별로 반씩"*(`share=0.5` = 20k 고정)이었다. 🔴 지시서가
    #     그것을 **팀별 25k + 합계 40k** 로 올렸다 — 상대가 쉬면 그 몫을 더 쓸
    #     수 있어야 한다(`share` 는 20k 에서 멈춰 그것을 막았다).
    #  🔴 묻는 것은 **그대로**다: *"한쪽이 다 써서 다른쪽이 0개가 되지 않나."*
    assert "side=True" in body, (
        "🔴 `_run_agent` 가 **쪽 예산**을 넘기지 않는다 — 설정만 바꾸면 "
        "실행에서는 그대로 한쪽이 다 쓴다(#2)")
    assert "pot=" in body, (
        "🔴 **경기 합계 지갑**을 넘기지 않는다 — 팀별 25k 뿐이면 합계가 50k 가 "
        "된다(지시서 §1-4)")
