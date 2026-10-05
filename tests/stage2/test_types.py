"""단계 2 계약 — `app/types.py` 가 v4 §1 용어·§3 스키마를 집행하나.

🔴 **§9 단계 2 게이트가 이름을 댄 둘이 C1·C2 다**:
   *"계약: direction 없는 변수 저장 실패 · 배당 숫자 필드 존재 시 실패."*

⚠️ 이 디렉터리는 `stage_gate` 가 잠근다 — 단계 1 승인 서명이 없으면 수집되지 않는다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app import types as T

KST = timezone(timedelta(hours=9))
GAME = datetime(2026, 9, 29, 18, 30, tzinfo=KST)
BEFORE = datetime(2026, 9, 28, 12, 0, tzinfo=KST)


def _var(**kw):
    """정상 변수 하나. 🔴 **운영이 만드는 모양**으로 세운다."""
    base = dict(id="v1", type="stakes", direction="home", hardness="hard",
                weight=1.0, text="세이부 2위=CS 홈", source_url="https://a/1",
                published_at=BEFORE)
    return T.Variable(**{**base, **kw})


# ══════════════════════════════════════════════════════════════════
# C1 · C2 — §9 단계 2 게이트가 이름을 댄 계약
# ══════════════════════════════════════════════════════════════════

def test_C1_direction_없는_변수는_저장되지_않는다():
    """🔴 §9 게이트 · §1 — *"방향이 없는 사실은 배경이지 변수가 아니다."*"""
    with pytest.raises(ValidationError):
        _var(direction=None)
    with pytest.raises(ValidationError):
        T.Variable(id="v1", type="stakes", hardness="hard", weight=1.0,
                   text="x", source_url="https://a", published_at=BEFORE)
    # 🔴 값 집합 밖도 거부한다 — 자유 문자열이면 v3 의 `stance` 병이 돌아온다
    with pytest.raises(ValidationError):
        _var(direction="홈승")


def test_C2_배당_숫자_필드는_존재할_수_없다():
    """🔴 §9 게이트 · §0 · §11-9 — 가격이 판정 경로에 닿지 않는다.

    ⚠️ **금칙 이름 목록을 손으로 유지하지 않는다.** 모든 모델이 `extra="forbid"`
       이므로 **스키마에 없는 칸이면 무엇이든** 터진다 — 목록보다 넓다.
    """
    for bad in ({"odds": 1.85}, {"price": 2.1}, {"decimal_odds": 1.9},
                {"배당": 1.85}, {"payout": 3.0}, {"무엇이든": 1}):
        with pytest.raises(ValidationError):
            T.Market(market_type="home", **bad)
        with pytest.raises(ValidationError):
            T.Slate(game_id=1, league="KBO", home="H", away="A",
                    kst_time=GAME, **bad)


def test_C2b_일곱_종_전부가_모르는_칸을_거부한다():
    """🔴 **7종 전부**에서 그러해야 한다 — 하나라도 열려 있으면 그 문으로 들어온다.

    ⚠️ 목록은 `STEP_PAYLOADS` 에서 **자란다**(손으로 세지 않는다). [§9 게이트 · §0 · §11-9]
    """
    assert len(T.STEP_PAYLOADS) == 7, "STEP 산출은 §3 의 7종이다"
    # 🔴 **최상위 7종만 보면 부족하다**(리뷰 M5) — 중첩 모델(`Market`·`Variable`·
    #    `Scenario`·`MarketSurvival`…)이 `_Strict` 를 빠뜨리면 그 문으로 들어온다.
    #    목록을 손으로 세지 않고 `__subclasses__()` 로 **자라게** 한다.
    seen, stack = set(), [T._Strict]
    while stack:
        for sub in stack.pop().__subclasses__():
            if sub in seen:
                continue
            seen.add(sub)
            stack.append(sub)
    assert len(seen) >= 12, f"모델이 {len(seen)}개뿐이다 — 탐색이 덜 됐나"
    for model in (*T.STEP_PAYLOADS.values(), *seen):
        assert model.model_config.get("extra") == "forbid", \
            f"{model.__name__} 이 모르는 칸을 받는다 — 배당이 들어올 문이다"


# ══════════════════════════════════════════════════════════════════
# C3~C5 — §3 STEP 1~3 variables.json
# ══════════════════════════════════════════════════════════════════

def test_C3_출처_없는_변수는_저장되지_않는다():
    """§3 — *"source_url 없는 변수 저장 실패."*"""
    with pytest.raises(ValidationError):
        _var(source_url="")
    with pytest.raises(ValidationError):
        _var(source_url="   ")


def test_C4_경기_후_기사는_저장되지_않는다():
    """🔴 §3 — *"published_at 이 경기 이후면 저장 실패"*(v3 §12-c 그대로).

    ⚠️ 판별을 베끼지 않고 `verify.parse_when` 을 부른다. 그래서 이 계약은
       **그 함수가 죽으면 함께 빨개진다** — 사본이면 그러지 않는다.
    """
    after = GAME + timedelta(hours=2)
    with pytest.raises(ValidationError, match="경기 후"):
        T.Variables(game_id=1, kst_time=GAME,
                    variables=[_var(published_at=after)])
    # 경기 전은 통과한다
    T.Variables(game_id=1, kst_time=GAME, variables=[_var()])
    # 🔴 배경 항목도 같은 검사를 받는다 — 거기로 우회할 수 없다
    with pytest.raises(ValidationError, match="경기 후"):
        T.Variables(game_id=1, kst_time=GAME, background=[
            T.Background(id="b1", text="x", source_url="https://a",
                         published_at=after)])


def test_C5_weight_는_hardness_가_정한다():
    """🔴 §4 · §14-5 — LLM 이 `weight` 를 쓸 수 없다.

    *"hard(공식 발표·확정 명단·공시) 1.0, likely(감독 인용·전담 매체) 0.7,
    soft(스니펫·예측 사이트) 0.4."*
    """
    assert T.WEIGHT_OF == {"hard": 1.0, "likely": 0.7, "soft": 0.4}
    for hardness, weight in T.WEIGHT_OF.items():
        _var(hardness=hardness, weight=weight)          # 맞으면 통과
        with pytest.raises(ValidationError, match="weight"):
            _var(hardness=hardness, weight=weight + 0.1)  # 어긋나면 실패


# ══════════════════════════════════════════════════════════════════
# C6 — §3 STEP 2 premise_check.json
# ══════════════════════════════════════════════════════════════════

def test_C6_전제마다_재검증_항목이_하나씩_있어야_한다():
    """🔴 §3 — *"0건이면 STEP 5 진입 불가."*

    ⚠️ `covers()` 는 **빠진 전제의 이름**을 돌려준다 — 개수만 세면 어느 것이
       빠졌는지 사라진다(조용한 0 금지).
    """
    v = T.Variables(game_id=1, kst_time=GAME, variables=[
        _var(id="p1", type="match_type", is_premise=True),
        _var(id="p2", type="lineup_intent", is_premise=True),
        _var(id="v9", type="stakes"),
    ])
    assert T.PremiseCheck(game_id=1).covers(v) == ["p1", "p2"]
    done = T.PremiseCheck(game_id=1, items=[
        T.PremiseCheckItem(premise_id="p1", result="kept"),
        T.PremiseCheckItem(premise_id="p2", result="replaced",
                           replacement_variable_id="v9"),
    ])
    assert done.covers(v) == []


def test_C6b_replaced_와_대체_변수는_함께_간다():
    """§3 STEP 2 — `kept` 면 대체 변수가 없고, `replaced` 면 있어야 한다. [§3]"""
    with pytest.raises(ValidationError, match="대체 변수가 없다"):
        T.PremiseCheckItem(premise_id="p1", result="replaced")
    with pytest.raises(ValidationError, match="대체 변수가 있다"):
        T.PremiseCheckItem(premise_id="p1", result="kept",
                           replacement_variable_id="v9")


# ══════════════════════════════════════════════════════════════════
# C7 — §3 STEP 4 sufficiency.json
# ══════════════════════════════════════════════════════════════════

def test_C7_자료_부족은_수가_정한다():
    """🔴 §1 — *"방향 있는 변수가 3개 미만이거나 반대 방향 변수가 0개."*

    `verdict` 를 사람이나 LLM 이 고를 수 없다.
    """
    assert T.MIN_DIRECTIONAL == 3
    T.Sufficiency(game_id=1, n_directional=5, n_opposite=2, verdict="pass")
    T.Sufficiency(game_id=1, n_directional=2, n_opposite=1,
                  verdict="insufficient", reason="방향 변수 2개")
    T.Sufficiency(game_id=1, n_directional=9, n_opposite=0,
                  verdict="insufficient", reason="반대 방향 0개")
    # 🔴 수와 어긋난 verdict 는 저장되지 않는다
    with pytest.raises(ValidationError, match="insufficient"):
        T.Sufficiency(game_id=1, n_directional=2, n_opposite=1, verdict="pass")
    with pytest.raises(ValidationError, match="insufficient"):
        T.Sufficiency(game_id=1, n_directional=9, n_opposite=0, verdict="pass")
    with pytest.raises(ValidationError, match="pass"):
        T.Sufficiency(game_id=1, n_directional=5, n_opposite=2,
                      verdict="insufficient", reason="x")
    # 🔴 조용한 0 금지 — 부족하다면 왜인지 적어야 한다
    with pytest.raises(ValidationError, match="reason"):
        T.Sufficiency(game_id=1, n_directional=1, n_opposite=0,
                      verdict="insufficient")


# ══════════════════════════════════════════════════════════════════
# C8 — §3 STEP 5 scenarios.json
# ══════════════════════════════════════════════════════════════════

def _sc(**kw):
    base = dict(id="A", variables=["v1"], scores=["2-1", "1-0"], strength=1.0,
                template_id="soccer_home_normal")
    return T.Scenario(**{**base, **kw})


def test_C8_시나리오는_스코어가_있어야_하고_둘_이상이어야_한다():
    """🔴 §1 · §3 — 스코어가 없으면 총점·핸디 생존을 셀 수 없다."""
    with pytest.raises(ValidationError, match="scores"):
        _sc(scores=[])
    with pytest.raises(ValidationError, match="2 미만"):
        T.Scenarios(game_id=1, scenarios=[_sc()])
    with pytest.raises(ValidationError, match="2 미만"):
        T.Scenarios(game_id=1)
    # ⚠️ 방향이 갈려야 한다 — `_sc()` 기본값은 홈 승이라 둘 다 쓰면 C8b 에 걸린다
    T.Scenarios(game_id=1, scenarios=[_sc(id="A"),
                                      _sc(id="B", scores=["0-1"])])
    # 🔴 id 가 겹치면 생존 계산이 같은 묶음을 두 번 센다
    with pytest.raises(ValidationError, match="겹친다"):
        T.Scenarios(game_id=1, scenarios=[_sc(id="A"),
                                          _sc(id="A", scores=["0-1"])])
    # 🔴 **A~H 밖은 없다**(§1 · 결정 ① 2026-10-04 로 다섯 → 여덟)
    #    ⚠️ 종전엔 `"F"` 로 쟀다 — 이제 `F` 는 **있는 글자**다.
    #    🔴 경계를 **손으로 적지 않는다**: 선언된 마지막 글자 **다음**으로 잰다.
    import typing
    letters = [str(x) for x in typing.get_args(T.ScenarioId)]
    beyond = chr(ord(letters[-1]) + 1)
    assert beyond not in letters, letters
    with pytest.raises(ValidationError):
        _sc(id=beyond)


# ══════════════════════════════════════════════════════════════════
# C9 · C10 — §3 STEP 6 survival.json
# ══════════════════════════════════════════════════════════════════

def test_C9_이름은_생존이_정한다():
    """🔴 §6 · §12 — *"survival 1.0 만 낸다, 0.8 이상은 소액."*

    §12 가 금지한 실수가 이것이다(아르메니아 +0.5 — 생존이 1.0 이 아닌데
    이름을 적었다).
    """
    assert (T.NAME_AT, T.SMALL_AT) == (1.0, 0.8)
    T.MarketSurvival(market_type="home", survival=1.0, verdict="name")
    T.MarketSurvival(market_type="home", survival=0.85, verdict="small")
    T.MarketSurvival(market_type="home", survival=0.3, verdict="none")
    with pytest.raises(ValidationError, match="name"):
        T.MarketSurvival(market_type="home", survival=0.99, verdict="name")
    with pytest.raises(ValidationError, match="small"):
        T.MarketSurvival(market_type="home", survival=0.79, verdict="small")
    # 생존은 0~1 이다
    with pytest.raises(ValidationError):
        T.MarketSurvival(market_type="home", survival=1.4, verdict="name")


def test_C10_보드에_없는_마켓에는_이름을_적지_않는다():
    """🔴 §3 — *"보드에 없는 market_type 이 verdict name/small 이면 실패."*

    ⚠️ **보드가 비면 검사하지 않는다**(§6-c 예외) — 사용자가 보드를 주지 않은
       경기다. "보드가 없다"와 "마켓이 보드 밖이다"는 다르다.
    """
    # 🔴 총점은 `team` 칸에 over/under 가 온다(§1 · 사용자 지시 2026-10-02 ⑪)
    board = [T.Market(market_type="total", team="under", line=3.5),
             T.Market(market_type="home")]
    sv = T.Survival(game_id=1, markets=[
        T.MarketSurvival(market_type="home", survival=1.0, verdict="name"),
        T.MarketSurvival(market_type="away_dc", survival=1.0, verdict="name"),
    ])
    assert sv.off_board(board) == ["away_dc/None/None"]
    assert sv.off_board([]) == [], "보드 없는 경기는 §6-c 예외다"
    # 이름을 안 적은 마켓은 보드 밖이어도 괜찮다
    ok = T.Survival(game_id=1, markets=[
        T.MarketSurvival(market_type="away_dc", survival=0.3, verdict="none")])
    assert ok.off_board(board) == []


def test_C10b_핸디와_총점은_기준선이_있어야_한다():
    """§1 — 기준선이 없으면 생존을 셀 수 없다.

    🔴 **총점은 over/under 도 있어야 한다**(§1 *"total(over/under, 기준선)"*).
       ⚠️ 비면 §6-a 대입이 오버인지 언더인지 모른 채 돌고, 생존이 **조용히** 한쪽으로
          계산된다 — 그것이 가장 찾기 어려운 틀림이다.
    """
    with pytest.raises(ValidationError, match="line"):
        T.Market(market_type="total", team="under")
    with pytest.raises(ValidationError, match="over"):
        T.Market(market_type="total", line=2.5)
    with pytest.raises(ValidationError, match="over"):
        T.Market(market_type="total", line=2.5, team="두산")
    for side in T.TOTAL_SIDES:
        T.Market(market_type="total", team=side, line=2.5)
    with pytest.raises(ValidationError, match="line"):
        T.Market(market_type="handicap", team="두산")
    with pytest.raises(ValidationError, match="team"):
        T.Market(market_type="handicap", line=1.5)
    T.Market(market_type="handicap", team="두산", line=-1.5)
    T.Market(market_type="home")          # 승패는 기준선이 없다


# ══════════════════════════════════════════════════════════════════
# C11 — §3 STEP 8 ledger 불변
# ══════════════════════════════════════════════════════════════════

def test_C11_원장은_불변이다():
    """🔴 §3 — *"결과 후 survival.json 수정 금지(불변)."*

    원장은 판정을 덮어쓰지 않고 **따로** 쌓인다. 그래서 원장 자체가 얼어 있다.
    """
    led = T.Ledger(game_id=1, realized_scenario_id="A")
    with pytest.raises(ValidationError):
        led.game_id = 2
    assert T.Ledger.model_config.get("frozen") is True


def test_LLM_이_쓰면_안_되는_칸이_규칙으로_닫혔다():
    """🔴 §3 마지막 · §14-5 — `direction`·`weight`·`strength`·`survival`·`verdict`.

    ⚠️ 이 계약은 **"LLM 이 그 이름을 안 쓴다"가 아니라 "그 칸에 아무 값이나 넣을
       수 없다"** 를 본다. 문자열 검사는 우회되지만 규칙은 우회되지 않는다
       (단계 1 의 `test_LLM이_판정_필드를_쓰지_않는다` 가 그 약한 판이었다).
    """
    # weight — hardness 가 정한다
    with pytest.raises(ValidationError):
        _var(hardness="soft", weight=1.0)
    # verdict — survival 이 정한다
    with pytest.raises(ValidationError):
        T.MarketSurvival(market_type="home", survival=0.5, verdict="name")
    # direction — 값 집합 밖은 없다
    with pytest.raises(ValidationError):
        _var(direction="아무거나")
    # survival — 0~1 밖은 없다
    with pytest.raises(ValidationError):
        T.MarketSurvival(market_type="home", survival=-0.1, verdict="none")
    # strength — 음수는 없다
    with pytest.raises(ValidationError):
        _sc(strength=-1.0)


def test_C8b_모든_시나리오가_한_방향이면_실패한다():
    """🔴 §3 STEP 5 — *"반대 방향 시나리오 최소 1개."* §5-c-6 이 같은 규칙이다.

    ⚠️ 리뷰 M8 이 *"이 계약이 타입에서 집행되지 않는다"* 고 지적했다 —
       `rules.all_one_direction()` 은 있었는데 `Scenarios` 검증기에 안 붙었다.
       🔴 **모든 시나리오가 한 방향이면 그것은 예측이지 예측불허가 아니다.**
       v4 §0 이 막으려는 바로 그것이다. [§3 · §5-c]
    """
    home_only = [_sc(id="A", scores=["2-1"]), _sc(id="B", scores=["1-0", "3-0"])]
    with pytest.raises(ValidationError, match="반대 방향"):
        T.Scenarios(game_id=1, scenarios=home_only)
    # 반대가 하나 있으면 통과한다
    T.Scenarios(game_id=1, scenarios=[_sc(id="A", scores=["2-1"]),
                                      _sc(id="B", scores=["0-1"])])
    T.Scenarios(game_id=1, scenarios=[_sc(id="A", scores=["2-1"]),
                                      _sc(id="C", scores=["0-0"])])
    # 🔴 난타전이 끼면 "전부 한 방향"이 아니다 — 이미 반대 결과를 품는다
    T.Scenarios(game_id=1, scenarios=[_sc(id="A", scores=["2-1"]),
                                      _sc(id="D", scores=["2-2", "2-3"])])


# ══════════════════════════════════════════════════════════════════
# 🔴 발행 시각 없는 자료 — 사용자 결정 2026-10-02 (안 A)
# ══════════════════════════════════════════════════════════════════
#
# 순위표에는 발행 시각이 **없다**(fotmob 표·`standings/now` 둘 다). 그런데 §4
# `stakes`·`home_field` 가 거기서 나온다 — `published_at` 을 필수로 두면 그 두
# 유형이 §3 구조에 **영영 못 들어간다**(실측 2026-10-02, `app/classify.py` 를
# 지으며 드러났다). 그래서 `None` 을 허용했다.
#
# 🔴 **그냥 열면 구멍이다** — 이 칸은 §12-c-2(경기 후 기사 배제)가 쓰는 칸이다.
#    조건 둘로 막는다: 사유 필수 · soft 필수(§12-c-1).


def _dateless_kwargs(**over):
    got = dict(id="V1", type="home_field", direction="home", hardness="soft",
               weight=0.4, text="리그 홈 승률 +16.6%p", source_url="https://x.test/t",
               published_at=None, dateless_reason="순위표에 발행 시각이 없다")
    got.update(over)
    return got


def test_날짜가_없으면_사유를_적어야_한다():
    """★ 🔴 조용히 비울 수 없다 — 비우면 §12-c-2 가 비껴간다. [§3 · §12-c]"""
    T.Variable(**_dateless_kwargs())                      # 사유가 있으면 통과
    with pytest.raises(ValidationError, match="dateless_reason"):
        T.Variable(**_dateless_kwargs(dateless_reason=""))
    with pytest.raises(ValidationError, match="dateless_reason"):
        T.Variable(**_dateless_kwargs(dateless_reason="   "))


def test_날짜가_없으면_soft_여야_한다():
    """★ 🔴 §12-c-1 — *"날짜를 못 읽는 자료는 soft 로만 남긴다."*

    ⚠️ 이것이 구멍을 막는 자리다. 날짜 없는 **기사**가 `hard` 로 들어오면
       §12-c-2 검사를 건너뛴 채 **무게 1.0** 을 갖는다. [§3 · §12-c]
    """
    for bad in ("hard", "likely"):
        with pytest.raises(ValidationError, match="soft"):
            T.Variable(**_dateless_kwargs(
                hardness=bad, weight=T.WEIGHT_OF[bad]))


def test_날짜가_있으면_사유를_적지_않는다():
    """🔴 둘 중 하나다 — 둘 다 있으면 어느 쪽이 참인지 모른다. [§3]"""
    when = datetime(2026, 10, 1, 9, 0, tzinfo=timezone(timedelta(hours=9)))
    T.Variable(**_dateless_kwargs(published_at=when, dateless_reason=""))
    with pytest.raises(ValidationError, match="dateless_reason"):
        T.Variable(**_dateless_kwargs(published_at=when,
                                      dateless_reason="왜 적었나"))


def test_날짜_없는_항목이_이름으로_남는다():
    """★ 🔴 **조용히 건너뛰지 않는다.** 건너뛴 것이 안 보이면 *"검사를 다 했다"* 로
    읽힌다. `Variables.dateless` 가 그 목록이다. [§3 · #3]
    """
    KST = timezone(timedelta(hours=9))
    kick = datetime(2026, 10, 1, 11, 0, tzinfo=KST)
    v_ok = T.Variable(**_dateless_kwargs(
        id="V2", type="recent_pattern", hardness="hard", weight=1.0,
        published_at=datetime(2026, 9, 30, 9, 0, tzinfo=KST),
        dateless_reason=""))
    got = T.Variables(game_id=1, kst_time=kick,
                      variables=[T.Variable(**_dateless_kwargs()), v_ok])
    assert len(got.dateless) == 1
    assert got.dateless[0].startswith("V1:")
    assert "순위표" in got.dateless[0]


def test_날짜_있는_항목은_여전히_경기_후_검사를_받는다():
    """🔴 안 A 가 **열어 준 것은 날짜 없는 자료뿐**이다. 날짜가 있으면 그대로 막힌다.

    ⚠️ 이 계약이 없으면 "None 허용"이 검사를 통째로 무력하게 만들었는지 알 수 없다.
    [§3 · §12-c]
    """
    KST = timezone(timedelta(hours=9))
    kick = datetime(2026, 10, 1, 11, 0, tzinfo=KST)
    after = T.Variable(**_dateless_kwargs(
        id="V3", hardness="hard", weight=1.0,
        published_at=kick + timedelta(hours=2), dateless_reason=""))
    with pytest.raises(ValidationError, match="경기 후"):
        T.Variables(game_id=1, kst_time=kick, variables=[after])
