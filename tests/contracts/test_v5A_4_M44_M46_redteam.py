"""🔴🔴 **v5-A §4 단계 4 — 반증(레드팀).** M44(생존 상승 금지) · M46(필수형 우선).

v5-A §4 원문:

> 판정 직전에 **이 마켓을 죽이는 시나리오가 세트에 빠졌나**를 따로 묻는다.
> 페이블이 채팅에서 놓쳤던 질문이 이것이다(남아공 5-0: 언더를 죽이는 대량득점형
> 부재 / 크로아티아 봇: 언더 3.5 를 죽이는 난타전 부재 / 콜롬비아: 무패를
> 죽이는 파라과이 승 갈래를 h2h 로 눌러 무시).
>
> **언제 도나** — 단계 3 시나리오 세트로 코드가 1차 생존 계산을 한 뒤, **생존
> 0.8 이상인 마켓이 하나라도 있을 때만.** 등급 후보가 없으면 반증할 결론도 없으니
> **비용을 쓰지 않는다.**
>
> 코드 처리 — `proposal` 은 §3 과 **같은 검사**를 통과해야 세트에 들어간다.
> 통과하면 `added_by:redteam`. · **추가만 가능 — 삭제·약화 금지.** ·
> `impossible` 은 **그대로 받지 않는다** — 필수형 조건이 걸리는데 `impossible`
> 이라 했으면 무시하고 템플릿 시나리오를 넣는다(`redteam_overruled`). ·
> **반증 단계는 등급을 올리지 못한다** — 올라가면 **버그로 보고 카드 금지**(M44).
"""
from __future__ import annotations

import pytest


def _vars():
    return [{"id": "R1", "type": "absence", "team": "team:000151",
             "direction": "away", "hardness": 2, "claim": "에를리치 결장"},
            {"id": "R4", "type": "recent_pattern", "team": "team:000266",
             "direction": "away", "hardness": 1, "claim": "최근 4경기 무패"}]


def _inp(**kw):
    from app import hypo
    base = {"home": "team:000151", "away": "team:000266", "sport": "soccer",
            "competition": "UEFA NL A3", "variables": _vars(),
            "facts": {"xi": {"team:000151": ["에를리치"]}},
            "board": [{"market": "total", "point": 2.5}],
            "required_types": []}
    base.update(kw)
    return hypo.HypoInput(**base)


def _set():
    return [{"id": "A", "driver_vars": ["R1"], "mechanism": "결장이 흔든다",
             "outcomes": [[1, 0]], "type": "normal", "strength": 2}]


def test_v5A_4_생존_0_8_이상이_없으면_안_부른다():
    """🔴🔴 *"생존 0.8 이상인 마켓이 **하나라도 있을 때만**"*(v5-A §4).

    ⚠️ 등급 후보가 없으면 반증할 결론도 없다 — 🔴 **비용을 쓰지 않는다.**
    """
    from app import redteam
    from app.reasons import Reason
    got = redteam.run(_inp(), _set(), survivals=[("total_under_2.5", 0.7)])
    assert got.added == []
    assert got.reason is Reason.REDTEAM_SKIPPED
    assert "0.8" in got.why, got.why


def test_v5A_4_부를_조건이면_사유가_건너뜀이_아니다():
    """⚠️ 반대 증거 — 0.8 이상이 있으면 **건너뛰지 않는다**.

    ══════════════════════════════════════════════════════════════
    🔴 **켜졌다** — 지시 2026-10-05. 그래서 **두 쪽을 다** 본다.
    ══════════════════════════════════════════════════════════════

    ⚠️ 종전엔 `enabled: false` 라 `deepseek_unavailable` 이 답이었다.
    🔴 지금은 **실제로 돈다** — 그러면 묻는 것이 둘이다:
       ① 꺼 두면 `deepseek_unavailable`(건너뜀이 **아니다**)
       ② 켜 두면 **건너뜀이 아니고** 제안이 온다(또는 장애 사유가 온다)
    """
    from app import redteam, rules
    from app.reasons import Reason
    # ① **끄고** — 사유가 `deepseek_unavailable` 이어야 한다(건너뜀 아니다)
    old = rules.deepseek_cfg
    try:
        rules.deepseek_cfg = lambda: dict(old(), enabled=False)
        off = redteam.run(_inp(), _set(),
                          survivals=[("total_under_2.5", 0.85)])
    finally:
        rules.deepseek_cfg = old
    assert off.reason is Reason.DEEPSEEK_UNAVAILABLE, off.reason
    assert "enabled" in off.why or "꺼" in off.why, off.why
    # ② **켜고** — `redteam_skipped` 가 **아니어야** 한다
    got = redteam.run(_inp(), _set(), survivals=[("total_under_2.5", 0.85)])
    assert got.reason is not Reason.REDTEAM_SKIPPED, (got.reason, got.why)
    # 🔴 장애면 그 사유여도 된다 — **M45**(장애 시 Solar 경로로 끝까지)
    assert got.reason in (Reason.OK, Reason.DEEPSEEK_UNAVAILABLE,
                          Reason.REDTEAM_OVERRULED), (got.reason, got.why)


def test_v5A_4_제안은_같은_검사를_지난다():
    """🔴 *"`proposal` 은 §3 과 **같은 검사**를 통과해야 세트에 들어간다"*."""
    from app import redteam
    bad = {"market": "total_under_2.5", "kill_range": "sum>=3",
           "status": "proposed",
           "proposal": {"id": "RT1", "driver_vars": ["R9"],
                        "mechanism": "x", "outcomes": [[2, 2]]}}
    kept, drops = redteam.check_proposals([bad], _inp())
    assert kept == [] and drops, drops
    ok = {"market": "total_under_2.5", "kill_range": "sum>=3",
          "status": "proposed",
          "proposal": {"id": "RT1", "driver_vars": ["R1", "R4"],
                       "mechanism": "결장이 흔든다", "outcomes": [[2, 2]],
                       "weak": True}}
    kept2, _ = redteam.check_proposals([ok], _inp())
    assert len(kept2) == 1, kept2
    # 🔴 **`added_by:redteam`** 을 단다
    assert kept2[0]["added_by"] == "redteam", kept2[0]


def test_v5A_4_추가만_가능하다():
    """🔴🔴 *"**추가만 가능 — 삭제·약화 금지**"*(시나리오를 줄이면 거짓 1.0)."""
    from app import redteam
    before = _set()
    kept, _ = redteam.check_proposals(
        [{"market": "m", "status": "proposed",
          "proposal": {"id": "RT1", "driver_vars": ["R1"],
                       "mechanism": "결장이 흔든다", "outcomes": [[2, 2]]}}],
        _inp())
    after = redteam.merge(before, kept)
    assert len(after) == len(before) + 1
    # 🔴 **원래 것이 그대로** 있다(무게도 안 바뀐다)
    assert after[0] == before[0], (after[0], before[0])


def test_v5A_4_삭제_요청을_받지_않는다():
    """🔴 모델이 *"A 를 지워라"* 라고 해도 **안 지운다.**"""
    from app import redteam
    import inspect
    src = inspect.getsource(redteam)
    # 🔴 세트에서 **빼는 코드가 없다**(지우는 길을 만들지 않는다)
    for bad in (".remove(", "del scenarios", "pop("):
        assert bad not in src, f"🔴 반증이 시나리오를 지울 수 있다: {bad}"
    got = redteam.merge(_set(), [], drop=["A"])
    assert len(got) == 1, got


@pytest.mark.parametrize(("before", "after", "ok"), [
    (1.0, 0.83, True),     # 🔴 내려가는 것은 **정상**이다
    (0.85, 0.85, True),    # ⚠️ 같은 것도 정상(같은 갈래였다)
    (0.80, 0.90, False),   # 🔴🔴 **올라가면 버그다**
])
def test_v5A_4_생존율이_올라가면_카드_금지_M44(before, after, ok):
    """🔴🔴 **M44** — *"반증 단계는 등급을 올리지 못한다. 시나리오가 늘기만
    하므로 생존율은 같거나 내려간다. **올라가는 결과가 나오면 버그로 보고 카드
    금지**."*

    ⚠️ 왜 올라갈 수 없나: 시나리오가 늘면 **죽을 자리가 늘어난다.** 올라갔다면
       우리가 시나리오를 **지웠거나 무게를 바꾼** 것이다.
    """
    from app import redteam
    got, why = redteam.check_survival({"m": before}, {"m": after})
    assert got is ok, (got, why)
    if not ok:
        assert "M44" in why and "카드 금지" in why, why


def test_v5A_4_impossible_을_그대로_받지_않는다_M46():
    """🔴🔴 **M46** — *"필수형 조건이 걸리는데 `impossible` 이라 했으면 무시하고
    템플릿 시나리오를 넣는다(`redteam_overruled`)"*.

    ⚠️ 모델이 *"못 만든다"* 고 해도 **§6-2 필수형 조건**이 걸리면 코드가 넣는다.
    🔴 그 판단은 **코드 것**이다(v5-A §1: 판정은 코드 자리).
    """
    from app import redteam
    from app.reasons import Reason
    rows = [{"market": "total_under_2.5", "kill_range": "sum>=3",
             "status": "impossible", "reason": "변수가 없다"}]
    # 🔴 필수형(`fav_concedes`)이 **걸린다**
    got = redteam.overrule(rows, _inp(required_types=["fav_concedes"]))
    assert got.types == ["fav_concedes"], got
    assert got.reason is Reason.REDTEAM_OVERRULED
    # ⚠️ 필수형이 **안 걸리면** 그대로 받는다
    none_ = redteam.overrule(rows, _inp(required_types=[]))
    assert none_.types == [] and none_.reason is Reason.OK


def test_v5A_4_카드에_적는_줄이_있다():
    """🔴 v5-A §4 출력 예 — *"반증 단계가 시나리오 RT1 을 추가해 언더 2.5
    생존 1.0 → 0.83"* 처럼 적는다."""
    from app import redteam
    said = redteam.card_line("언더 2.5", "proposed", before=1.0, after=0.83,
                             by=["RT1"])
    assert "1.0" in said and "0.83" in said and "RT1" in said, said
    cov = redteam.card_line("오버 2.5", "covered", before=0.8, after=0.8,
                            by=["B"])
    assert "covered" in cov and "유지" in cov, cov


def test_v5A_4_예산을_넘으면_건너뛴다():
    """🔴 v5-A §2 — *"경기당 DeepSeek 입력 30,000 초과 → **단계 4 생략**,
    카드에 `redteam_skipped`"*."""
    from app import redteam
    from app.reasons import Reason
    got = redteam.run(_inp(), _set(), survivals=[("m", 0.9)],
                      spent_in=30_001)
    assert got.reason is Reason.REDTEAM_SKIPPED
    assert "30,000" in got.why or "30000" in got.why, got.why
