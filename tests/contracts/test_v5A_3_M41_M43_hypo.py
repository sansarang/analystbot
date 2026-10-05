"""🔴🔴 **v5-A §3 단계 3 — 가설·시나리오.** M41(사실 금지) · M43(등급 금지).

v5-A §3 코드 처리 원문:

> · `driver_vars` 의 ID 가 입력 `variables` 에 없으면 그 시나리오 폐기
>   (`unknown_var`).
> · `mechanism` 에 **입력에 없는 고유명사**(선수·팀·사건)가 나오면 폐기
>   (`new_fact`). 고유명사 목록은 입력 변수·사실·XI 에서 **코드가 뽑는다**.
> · `outcomes` 가 비거나 종목 범위 밖(**축구 0~9, 야구 0~25**)이면 폐기.
> · 남은 시나리오에 v5 §6-2 자동 보강을 그대로 돌린다 — DeepSeek 가 필수형을
>   빠뜨렸으면 코드가 템플릿으로 추가하고 `added_by:code`. 추가가 생기면
>   원장에 `deepseek_missed_required` 로 센다.
> · `strength` 는 v5 §6-1 대로 `driver_vars` 의 **hardness 합**. `weak:true` 는
>   strength 를 **바꾸지 않는다**(표시만).

| 번호 | 계약 | 돌연변이 |
|---|---|---|
| **M41** | `driver_vars` 는 검증 변수 ID 만 · `mechanism` 에 입력 밖 고유명사 금지 | 두 검사 제거 |
| **M43** | DeepSeek 출력의 **등급·확률·승자 단어**는 판정 입력에 닿지 않는다 | `confidence` 를 strength 에 더하기 |
"""
from __future__ import annotations

import pytest


def _vars():
    return [
        {"id": "R1", "type": "absence", "team": "team:000151",
         "direction": "away", "hardness": 2, "claim": "에를리치 결장"},
        {"id": "R2", "type": "recent_pattern", "team": "team:000266",
         "direction": "away", "hardness": 1, "claim": "최근 4경기 무패"},
    ]


def _inp(**kw):
    from app import hypo
    base = {
        "home": "team:000151", "away": "team:000266", "sport": "soccer",
        "competition": "UEFA Nations League A3",
        "variables": _vars(),
        "facts": {"xi": {"team:000151": ["에를리치", "크라마리치"]}},
        "board": [{"market": "1x2"}, {"market": "total", "point": 2.5}],
        "required_types": ["fav_concedes"],
    }
    base.update(kw)
    return hypo.HypoInput(**base)


def _sc(**kw):
    base = {"id": "A", "driver_vars": ["R1"], "mechanism": "결장이 수비를 흔든다",
            "outcomes": [[1, 2]], "type": "normal", "weak": False}
    base.update(kw)
    return base


def test_v5A_3_입력을_코드가_만든다():
    """🔴 `HypoInput` — *"코드가 만든다"*(v5-A §3). ⚠️ 모델이 짓지 않는다."""
    from app import hypo
    got = _inp()
    box = hypo.to_payload(got)
    # 🔴 **보내지 않는 것**(v5-A §2): 기사 원문·URL·사용자 정보·배당
    flat = str(box)
    for bad in ("http", "odds", "배당", "source_url"):
        assert bad not in flat, (bad, flat[:200])
    # 🔴 `required_types` 는 **코드가 선계산**해서 넘긴다
    assert box["required_types"] == ["fav_concedes"]


def test_v5A_3_모르는_변수_ID_면_폐기_M41():
    """🔴 *"`driver_vars` 의 ID 가 입력에 없으면 폐기(`unknown_var`)"*."""
    from app import hypo
    from app.reasons import Reason
    kept, drops = hypo.check_scenarios([_sc(driver_vars=["R9"])], _inp())
    assert kept == []
    assert drops[0][1] is Reason.UNKNOWN_VAR, drops
    # ⚠️ 아는 ID 면 **남는다**(반대 증거)
    kept2, _ = hypo.check_scenarios([_sc()], _inp())
    assert len(kept2) == 1


def test_v5A_3_입력_밖_고유명사면_폐기_M41():
    """🔴🔴 *"`mechanism` 에 입력에 없는 고유명사가 나오면 폐기(`new_fact`)"*.

    ⚠️ 고유명사 목록은 **입력 변수·사실·XI 에서 코드가 뽑는다** — 모델에게
       묻지 않는다. 🔴 그래야 *"모델이 지어낸 이름"* 을 가릴 수 있다.
    """
    from app import hypo
    from app.reasons import Reason
    # 🔴 **라틴 이름**은 잡는다
    kept, drops = hypo.check_scenarios(
        [_sc(mechanism="Modric controls the midfield")], _inp())
    assert kept == [], kept
    assert drops[0][1] is Reason.NEW_FACT, drops
    # ⚠️ **입력에 있는** 이름이면 쓴다(`에를리치` 는 XI 에 있다)
    kept2, _ = hypo.check_scenarios(
        [_sc(mechanism="에를리치 결장이 수비를 흔든다")], _inp())
    assert len(kept2) == 1, kept2
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **한글·가나 이름은 이 검사가 못 잡는다** — 그 사실을 적는다
    # ══════════════════════════════════════════════════════════════════
    #
    #  세 판을 거쳐 결정했다(머리글 참조): 사전·어미로는 끝이 없고, 그 길은
    #  **정상 시나리오를 폐기**한다 — M41 이 막으려던 것과 **반대** 결과다.
    #  🔴 그래서 **라틴 머리글자만** 본다. ⚠️ 한글 글은 **지난다** — 그 사실이
    #     `name_check` 칸에 남는다(조용히 통과시키지 않는다 · #3).
    #  ⬛ 한글 이름을 가르는 자는 `questions/` 에 적었다 — 사용자가 정한다.
    thru, _ = hypo.check_scenarios(
        [_sc(mechanism="모드리치가 중원을 잡는다")], _inp())
    assert len(thru) == 1, thru
    assert thru[0]["name_check"] == "latin_only", thru[0]


def test_v5A_3_고유명사를_코드가_뽑는다_M41():
    """🔴 그 목록이 **입력에서 자란다**(손으로 적지 않는다)."""
    from app import hypo
    got = hypo.proper_nouns(_inp())
    assert "에를리치" in got and "크라마리치" in got, got
    # ⚠️ 변수 `claim` 의 이름도 들어간다
    assert any("에를리치" in x for x in got)


@pytest.mark.parametrize(("sport", "score", "ok"), [
    ("soccer", [9, 0], True),
    ("soccer", [10, 0], False),     # 🔴 축구 0~9
    ("baseball", [25, 0], True),
    ("baseball", [26, 0], False),   # 🔴 야구 0~25
    ("soccer", [-1, 0], False),
])
def test_v5A_3_스코어_범위를_본다(sport, score, ok):
    """🔴 *"`outcomes` 가 비거나 종목 범위 밖이면 폐기"*(축구 0~9 · 야구 0~25)."""
    from app import hypo
    kept, drops = hypo.check_scenarios(
        [_sc(outcomes=[score])], _inp(sport=sport))
    assert bool(kept) is ok, (kept, drops)


def test_v5A_3_빈_outcomes_는_폐기():
    from app import hypo
    kept, drops = hypo.check_scenarios([_sc(outcomes=[])], _inp())
    assert kept == [] and drops, drops


def test_v5A_3_strength_는_hardness_합이다():
    """🔴 §6-1 — *"`strength` 는 `driver_vars` 의 **hardness 합**"*.

    ⚠️ `weak:true` 는 strength 를 **바꾸지 않는다**(표시만이다).
    """
    from app import hypo
    kept, _ = hypo.check_scenarios(
        [_sc(driver_vars=["R1", "R2"])], _inp())
    assert kept[0]["strength"] == 3, kept[0]      # 2 + 1
    weak, _ = hypo.check_scenarios(
        [_sc(driver_vars=["R1", "R2"], weak=True)], _inp())
    assert weak[0]["strength"] == 3, weak[0]
    assert weak[0]["weak"] is True


def test_v5A_3_등급_확률_승자_단어가_닿지_않는다_M43():
    """🔴🔴 **M43** — *"DeepSeek 출력의 등급·확률·승자 단어는 판정 입력에 닿지
    않는다"*(돌연변이: `confidence` 칸을 strength 에 더하기).

    ⚠️ 모델이 `confidence: 0.9`·`verdict: "name"` 을 적어도 **버린다.** 🔴 그
       수가 strength 에 섞이면 등급이 **모델 말**이 된다(절대규칙 5).
    """
    from app import hypo
    rows = [_sc(driver_vars=["R1"], confidence=0.9, verdict="name",
                probability=0.77, winner="Croatia")]
    kept, _ = hypo.check_scenarios(rows, _inp())
    assert len(kept) == 1
    got = kept[0]
    # 🔴 그 칸들이 **살아남지 않는다**
    for bad in ("confidence", "verdict", "probability", "winner"):
        assert bad not in got, (bad, sorted(got))
    # 🔴 strength 는 **hardness 합 그대로**(0.9 가 안 섞인다)
    assert got["strength"] == 2, got


def test_v5A_3_버린_칸을_사유로_남긴다_M43():
    """🔴 조용히 버리지 않는다 — **무엇을 버렸나**를 적는다(#3)."""
    from app import hypo
    kept, drops = hypo.check_scenarios(
        [_sc(confidence=0.9)], _inp())
    assert kept, drops
    assert "confidence" in str(kept[0].get("dropped_fields") or []), kept[0]


def test_v5A_3_필수형_누락을_센다():
    """🔴 *"DeepSeek 가 필수형을 빠뜨렸으면 … `deepseek_missed_required` 로
    센다"*(§6 측정의 **필수형 누락률**이다)."""
    from app import hypo
    from app.reasons import Reason
    got = hypo.missed_required([_sc(type="normal")], _inp())
    assert got == ["fav_concedes"], got
    assert hypo.MISSED_REASON is Reason.DEEPSEEK_MISSED_REQUIRED
    # ⚠️ 썼으면 **0 건**이다
    assert hypo.missed_required([_sc(type="fav_concedes")], _inp()) == []


def test_v5A_3_꺼져_있으면_안_부른다():
    """🔴 `enabled: false` — 단계 3 은 **돌지 않고 사유만** 남긴다."""
    # ══════════════════════════════════════════════════════════════
    # 🔴 **끄고 잰다** — 켜진 상태가 기본이 됐다(지시 2026-10-05)
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 이 계약은 `enabled: false` 를 **전제**했다. 🔴 사용자가 켜라고 해서
    #     그 전제가 깨졌다 — 그런데 **묻는 것은 그대로다**: *"꺼져 있으면 안
    #     부른다."* 그래서 **끄고** 잰다.
    #  🔴 끄는 자리는 한 곳이다(`rules.deepseek_cfg`) — 설정 파일을 건드리지
    #     않는다(시험이 저장소 상태를 바꾸면 그 다음 시험이 거짓이 된다).
    from app import hypo, rules
    from app.reasons import Reason
    old = rules.deepseek_cfg
    try:
        rules.deepseek_cfg = lambda: dict(old(), enabled=False)
        got = hypo.run(_inp())
    finally:
        rules.deepseek_cfg = old
    assert got.scenarios == []
    assert got.reason is Reason.DEEPSEEK_UNAVAILABLE
    assert "enabled" in got.why or "꺼" in got.why, got.why


def test_v5A_3_평범한_낱말을_고유명사로_보지_않는다_M41():
    """🔴🔴 **첫 판이 한글 전부를 고유명사로 봤다**(실측 2026-10-04).

    내 정규식이 `[가-힣]{2,}` 였다 — 그러면 `결장이`·`수비를`·`흔든다` 가
    **전부 고유명사**다. 🔴 그래서 **정상 시나리오가 `new_fact` 로 폐기**됐다.

    ⚠️ 한글·가나·한자에는 **대문자가 없다** — 라틴처럼 머리글자로 가릴 수 없다.
    🔴 그래서 **이름 목록으로 가린다**: 입력에서 뽑은 이름 집합에 **없고**
       그 글자가 **다른 이름의 조각도 아닐 때만** 새 이름으로 본다.
       ⚠️ 그것이 M41 의 뜻이다 — *"선수·팀·사건"* 이름이지 **조사 붙은 보통
       낱말**이 아니다.
    """
    from app import hypo
    inp = _inp()
    # 🔴 보통 낱말만 있는 메커니즘은 **통과**해야 한다
    kept, drops = hypo.check_scenarios(
        [_sc(mechanism="결장이 수비를 흔들어 실점이 늘어난다")], inp)
    assert len(kept) == 1, drops
    assert kept[0]["name_check"] == "latin_only", kept[0]
    # 🔴 **라틴 이름**은 잡는다
    bad2, _ = hypo.check_scenarios(
        [_sc(mechanism="Modric controls the midfield")], inp)
    assert bad2 == [], bad2
    # ⚠️ 문장 머리 대문자는 **이름이 아니다**(기능어 목록이 걷는다)
    ok3, d3 = hypo.check_scenarios(
        [_sc(mechanism="The absence weakens the defence")], inp)
    assert len(ok3) == 1, d3


def test_v5A_3_이름_사전이_어디서_오나_M41():
    """🔴 그 이름 사전은 **시스템이 이미 아는 것**이다(사본 금지).

    ⚠️ 손으로 이름 목록을 적으면 그것이 한 발 늦는다. 🔴 `teamref`(모든 언어의
       팀 이름)와 입력의 XI·명단이 그 사전이다.
    """
    from app import hypo
    got = hypo.known_names(_inp())
    assert "에를리치" in got and "크라마리치" in got, sorted(got)[:10]
