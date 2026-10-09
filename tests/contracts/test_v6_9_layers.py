"""🔴🔴 **네 층 확률 + 시장 비교 계약** — 지시서 2026-10-06(재작성) §9.

> 번호는 기존 계약 번호 다음부터. **전부 행동 검사.** 테스트는 고정물·카세트만 —
> 실피드·실데이터·실모델 금지.

⚠️ 여기 있는 검사는 **돌연변이로 확인했다** — 지시서 §9 가 돌연변이를 짝으로 적었다.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

from app.core import devig, odds
from app.core.schema import MarketQuote

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "app"


def _code(*paths: str) -> str:
    from tests._helpers import strip_docs
    out = []
    for rel in paths:
        for p in (ROOT / rel).rglob("*.py"):
            out.append(strip_docs(p.read_text(encoding="utf-8")))
    return "\n".join(out)


# ══════════════════════════════════════════════════════════════════
# §2-5 디빅
# ══════════════════════════════════════════════════════════════════


def test_디빅_비례가_지시서의_수를_낸다():
    """🔴 §9 — `1.66/3.79/4.55 → 55.5/24.3/20.2%`(±0.1), 합 1.0.

    돌연변이: **역수 합으로 안 나누기** → 합이 1.086 이 되어 빨개진다.
    """
    probs, vig = devig.proportional([1.66, 3.79, 4.55])
    assert [round(p * 100, 1) for p in probs] == [55.5, 24.3, 20.2]
    assert abs(sum(probs) - 1.0) < 1e-9
    assert round(vig * 100, 2) == 8.60      # 업체 몫 = 역수 합 − 1


def test_같은_마켓_배당이_하나라도_빠지면_시장_확률이_없다():
    """🔴 §2-5 — 승무패는 **셋 다** 있어야 한다. 돌연변이: 빠진 칸을 0 으로."""
    two = [MarketQuote(market="win", side=s, price=p, bookmaker="pinnacle")
           for s, p in (("home", 1.66), ("draw", 3.79))]
    probs, _, _, bad = odds.probs_of(two, basis=["pinnacle"])
    assert not probs, probs
    assert bad and "§2-5" in bad[0], bad


def test_업체가_여럿이면_디빅한_확률의_중앙값이다():
    """🔴 §2-4 — 피나클이 없으면 **업체별 디빅 후 중앙값**. 돌연변이: 단순 평균.

    세 업체의 홈 확률이 0.50·0.55·0.70 이면 중앙값은 **0.55 쪽**이고 평균(0.583)과
    다르다 — 그 차이가 이 검사를 살린다.
    """
    rows = []
    for book, prices in (("a", (2.00, 4.00, 4.00)), ("b", (1.80, 4.00, 4.60)),
                         ("c", (1.40, 5.00, 7.00))):
        rows += [MarketQuote(market="win", side=s, price=p, bookmaker=book)
                 for s, p in zip(("home", "draw", "away"), prices, strict=True)]
    names, label = odds.pick_basis(rows)
    assert "중앙값" in label, label
    probs, _, _, _ = odds.probs_of(rows, basis=names)
    got = probs[odds.key_of("win", "home")]
    # 🔴 업체별 디빅 후 홈 확률은 0.5000 · 0.5431 · 0.6757 → **중앙값 0.5431**
    each = [devig.proportional(list(p))[0][0]
            for p in ((2.00, 4.00, 4.00), (1.80, 4.00, 4.60), (1.40, 5.00, 7.00))]
    assert abs(got - sorted(each)[1]) < 0.002, (got, each)
    assert abs(got - sum(each) / 3) > 0.02, "중앙값이 아니라 평균을 썼다"
    # ⚠️ 디빅 **전** 평균(배당 평균 1.733 → 0.577)과도 달라야 한다
    assert abs(got - devig.proportional([1.7333, 4.3333, 5.2])[0][0]) > 0.02


def test_피나클이_있으면_피나클이_기준이다():
    """🔴 §2-4 — 돌연변이: 다른 업체와 섞어 중앙값."""
    rows = [MarketQuote(market="win", side=s, price=p, bookmaker=b)
            for b, prices in (("pinnacle", (1.66, 3.79, 4.55)),
                              ("other", (1.20, 6.00, 9.00)))
            for s, p in zip(("home", "draw", "away"), prices, strict=True)]
    names, label = odds.pick_basis(rows)
    assert names == ["pinnacle"] and "pinnacle" in label
    probs, _, _, _ = odds.probs_of(rows, basis=names)
    assert round(probs[odds.key_of("win", "home")] * 100, 1) == 55.5


def test_더블찬스는_승무패에서_유도한다():
    """🔴 §2-5 마지막 — 따로 받지 않는다."""
    rows = [MarketQuote(market="win", side=s, price=p, bookmaker="pinnacle")
            for s, p in (("home", 1.66), ("draw", 3.79), ("away", 4.55))]
    probs, _, _, _ = odds.probs_of(rows, basis=["pinnacle"])
    h, d, a = (probs[odds.key_of("win", s)] for s in ("home", "draw", "away"))
    assert abs(probs["unbeaten:home"] - (h + d)) < 1e-6
    assert abs(probs["unbeaten:away"] - (a + d)) < 1e-6


def probs_home(rows: list[MarketQuote]) -> float:
    """🔴 비례 방식 홈 확률 — Shin 과 **다른 수**인지 보려고 쓴다."""
    probs, _, _, _ = odds.probs_of(rows, basis=["pinnacle"])
    return probs[odds.key_of("win", "home")]


def test_승무패에는_Shin_도_함께_나온다():
    """🔴 §2-5 — 3-way 는 Shin 방식도 계산해 **괄호로** 보인다."""
    rows = [MarketQuote(market="win", side=s, price=p, bookmaker="pinnacle")
            for s, p in (("home", 1.66), ("draw", 3.79), ("away", 4.55))]
    _, shin, _, _ = odds.probs_of(rows, basis=["pinnacle"])
    # ⚠️ 표에 담을 때 소수 여섯 자리로 **둥근다** — 합 오차는 그 자리까지만 본다
    assert shin and abs(sum(shin.values()) - 1.0) < 2e-6
    # 🔴 Shin 은 비례와 **다른 수**다(실측: 홈 0.5688 vs 비례 0.5547)
    assert round(shin[odds.key_of("win", "home")], 4) == 0.5688
    assert shin[odds.key_of("win", "home")] > probs_home(rows)


# ══════════════════════════════════════════════════════════════════
# §2-2·§2-3 예산과 매칭
# ══════════════════════════════════════════════════════════════════


def test_경기_매칭은_후보가_하나일_때만():
    """🔴 §2-3 — 킥오프 ±8h + 두 팀 열쇠 일치. 돌연변이: **첫 후보 자동 선택**."""
    import importlib
    from datetime import timedelta
    t = importlib.import_module("tests.e2e.test_v6_replay")
    ref = t._ref()
    ev = {"id": "1", "commence_time": ref.kickoff_utc.isoformat(),
          "home_team": ref.home_name, "away_team": ref.away_name}
    got, why = odds.match_event(ref, [ev])
    assert got is ev, why
    # 🔴 같은 창에 **둘** → 고르지 않는다
    got2, why2 = odds.match_event(ref, [ev, dict(ev, id="2")])
    assert got2 is None and "하나로 못 좁혔다" in why2, why2
    # 🔴 창 밖(±8h 초과) → 0건
    far = dict(ev, commence_time=(ref.kickoff_utc + timedelta(hours=9)).isoformat())
    got3, why3 = odds.match_event(ref, [far])
    assert got3 is None and "후보 0건" in why3, why3


def test_월_한도를_넘으면_호출이_0이다():
    """🔴 §2-2 — 100% 면 중단, 80% 면 경고. 돌연변이: 한도 검사 제거."""
    ok, why = odds.budget_left(500, 500)
    assert not ok and "중단" in why
    ok2, why2 = odds.budget_left(450, 500)
    assert ok2 and "가깝다" in why2
    ok3, why3 = odds.budget_left(10, 500)
    assert ok3 and "10/500" in why3


def test_요청_예산이_분석_2회_재분석_1회다():
    """🔴 §2-2 — 표가 그 수를 든다(코드에 박지 않는다)."""
    from app import rules
    box = rules.odds_budget()
    assert int(box["per_analyze"]) == 2 and int(box["per_reanalyze"]) == 1
    assert int(box["events_cache_hours"]) == 6


def test_카드_등록이_필요한_피드는_쓰지_않는다():
    """🔴 §2-1 — `card_required: true` 면 **키가 있어도** 빠진다."""
    import app.core.odds as mod
    from app import rules
    real = rules.odds_feeds
    rules.odds_feeds = lambda **_: [            # type: ignore[assignment]
        {"name": "needs_card", "card_required": True, "needs_key": False}]
    try:
        got, whys = mod.ready_feeds()
    finally:
        rules.odds_feeds = real                 # type: ignore[assignment]
    assert not got and any("카드 등록" in w for w in whys), whys


# ══════════════════════════════════════════════════════════════════
# §3 ① 기준 확률
# ══════════════════════════════════════════════════════════════════


def test_Elo_We_가_지시서_수와_같다():
    """🔴 §9 — `dr=0 → 0.5` · `dr=+400 → 0.909`. 돌연변이: **부호 뒤집기**."""
    from app.core import base
    assert base.we(0) == pytest.approx(0.5, abs=1e-9)
    assert base.we(400) == pytest.approx(0.909, abs=0.001)
    assert base.we(-400) == pytest.approx(0.091, abs=0.001)


def test_순서형_로짓_계수는_config_에서만_온다():
    """🔴 §3-2 — **실행 중 적합 금지**. 돌연변이: `app/` 에서 fit 호출.

    🔴 AST 로 본다 — `app/**` 어디에도 적합 함수 호출이 없어야 한다.
    """
    banned = {"minimize", "curve_fit", "OrderedModel", "LogisticRegression",
              "least_squares"}
    bad: list[str] = []
    for p in APP.rglob("*.py"):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "id", None) or getattr(fn, "attr", None)
                if name in banned:
                    bad.append(f"{p.relative_to(ROOT)}:{node.lineno} {name}")
            if isinstance(node, ast.Attribute) and node.attr == "fit":
                bad.append(f"{p.relative_to(ROOT)}:{node.lineno} .fit")
    assert not bad, bad


def test_다른_대회_유형_계수를_빌려_쓰지_않는다():
    """🔴 §3 — 없는 유형을 물으면 **확률이 없다**(다른 유형 값이 아니다)."""
    from app.core import base
    got, why = base.triple_of("league:K리그1", 100.0)
    assert got is None and "계수가 없다" in why, why
    said, _ = base.triple_of("national_friendly", 100.0)
    assert said is not None and said.home > said.away


def test_중립_경기에는_기준_확률을_내지_않는다():
    """🔴 적합 자료가 **홈 개최뿐**이다(중립 줄은 결과순) — 그래서 중립은 "기준 없음"."""
    from app.core import base
    got = base.base_prob(kind="national_friendly", home_elo=1722, away_elo=1653,
                         neutral=True, source="x", data_date="2026-10-06")
    assert got.probs is None and "중립" in got.why
    assert got.we is not None            # ⚠️ We 는 그래도 보인다(§3-3)


# ══════════════════════════════════════════════════════════════════
# §0·§11 금지 — AST
# ══════════════════════════════════════════════════════════════════


def test_기대값_금액_계산이_app_에_없다():
    """🔴 §0 금지 — EV·손익분기·켈리·스테이크·금액. 돌연변이: `ev` 함수 추가."""
    code = _code("app")
    for word in ("expected_value", "def ev(", "kelly", "break_even",
                 "breakeven", "stake_size", "payout"):
        assert word not in code, word


def test_로컬_OCR_만_쓴다():
    """🔴 §11 금지 — 외부 OCR API 호출 0건. 돌연변이: 외부 OCR 호출 추가."""
    code = _code("app")
    for word in ("vision.googleapis", "api.ocr.space", "azure.com/vision",
                 "textract", "clova"):
        assert word not in code, word
    from app.core import ocr
    assert ocr.BINARY == "tesseract"


def test_시장_확률이_등급_계산에_직접_안_들어간다():
    """🔴 §7 금지 — `survive`·`s7` 가 `MarketProb.probs` 를 읽지 않는다.

    ⚠️ 시장은 **등급을 내리기만** 한다(§7). 그 일은 전용 함수가 하고, 생존율 계산은
       시장을 모른다 — 그래야 *"시장과 다르다는 이유로 우리 수를 고치기"* 가 불가능하다.
    """
    from tests._helpers import strip_docs
    for rel in ("app/survive.py", "app/core/stages/s6_hypo.py"):
        p = ROOT / rel
        if not p.is_file():
            continue
        said = strip_docs(p.read_text(encoding="utf-8"))
        assert "MarketProb" not in said, rel
        assert "market_prob" not in said, rel


# ══════════════════════════════════════════════════════════════════
# §4 ② 라인업 보정 · §5 중복 금지 · §7 등급 내림
# ══════════════════════════════════════════════════════════════════


def test_평소_XI_표본이_3경기_미만이면_건너뛴다():
    """🔴 §4-1 — 표본 검사. 돌연변이: **표본 검사 제거** → 1경기로 보정해 버린다."""
    from app.core import base
    from app.core.schema import Facts, Player, XI
    from app.core.stages import s2b_base
    from app.core.state import RunState
    import importlib
    ref = importlib.import_module("tests.e2e.test_v6_replay")._ref()
    xi = XI(team=ref.home, state="confirmed",
            lineup=[Player(name=f"P{i}") for i in range(11)])
    facts = Facts(xi={str(ref.home): xi}, last_xi={str(ref.home): xi},
                  player_value={f"P{i}": 1_000_000.0 for i in range(11)})
    assert base.MIN_USUAL_SAMPLE == 3
    assert s2b_base.usual_sample(facts) == 1
    got = s2b_base._adjust(ref, facts, __import__(
        "app.core.schema", fromlist=["BaseProb"]).BaseProb(), state=RunState())
    assert got.probs is None and "표본" in got.why, got.why
    assert not got.measured


def test_2가_계산되면_결장_계열_무게가_0이다():
    """🔴 §5 중복 금지 — ② 가 셌으면 결장 변수 무게 0. 돌연변이: **무게표 그대로**."""
    from app.core import compare
    from app.core.schema import Variable
    rows = [
        Variable(id="R1", type="def_absence", subject="team:000129",
                 favors="away", goals="up", target="X", hardness="hard",
                 weight=3.0, claim="c", quote="q"),
        Variable(id="R2", type="h2h_pattern", subject="team:000129",
                 favors="home", goals="none", target="h2h", hardness="soft",
                 weight=1.0, claim="c", quote="q")]
    got, notes = compare.weight_rules(rows, measured=True)
    assert got["R1"] == 0.0, got
    assert got["R2"] == 0.5, got
    assert any("②" in n for n in notes), notes
    # ⚠️ ② 가 없으면 **사람 무게표를 그대로** 쓴다(§4 마지막 줄)
    none, _ = compare.weight_rules(rows, measured=False)
    assert "R1" not in none and none["R2"] == 0.5, none


def test_시장은_등급을_못_바꾼다():
    """🔴🔴 **원칙 수정**(사용자 지시 2026-10-06(8차) ①) — 시장 열은 등급·확률을
    **어떤 경우에도** 바꾸지 않는다. 남은 규칙은 *"우리만 반대(기준과 다름)"* 뿐이다.

    돌연변이: `시장이 다르다` 에 한 단계 내림을 되살리기 / 세 열 일치에 올림 주기.
    """
    from app.core import compare
    for verdict in ("기준과 맞는다", "우리만 반대", "시장이 다르다", "시장만 튄다",
                    "우리만 튄다", "기준 없음", "시장 없음", "세 열 불일치"):
        step, why = compare.grade_step(verdict, found_new=False)
        assert step >= 0, (verdict, step, why)
    assert compare.grade_step("기준과 맞는다", found_new=False)[0] == 0
    # 🔴 **기준**과 반대면 등급 없음(기준은 우리 데이터다)
    assert compare.grade_step("우리만 반대", found_new=False)[0] >= 3
    # 🔴 시장이 반대·치우쳐도 **0칸**이다
    for v in ("시장이 다르다", "시장만 튄다", "세 열 불일치"):
        step, why = compare.grade_step(v, found_new=False)
        assert step == 0, (v, step)
        assert "바꾸지 않는다" in why, why


def test_등급_내림이_사다리_아래로만_간다():
    """🔴 §7 — `_lower` 가 **아래로만** 옮긴다(실제 판정 묶음으로 센다)."""
    from app.core import pipeline
    from app.core.schema import BoardLine, Judgement, MarketEval
    from app.core.state import RunState
    evals = [MarketEval(line=BoardLine(market="win", side="home"),
                        marks={}, survival=0.9, cap=1.0, grade="낸다")]
    said = Judgement(evals=evals, direction="d", conclusion="c")
    # 🔴 시장이 달라도 **그대로**다(8차 ①)
    got = pipeline._lower(said, {"compare": "시장이 다르다"}, state=RunState())
    assert got.evals[0].grade == "낸다", got.evals[0].grade
    none = pipeline._lower(said, {"compare": "우리만 반대"}, state=RunState())
    assert none.evals[0].grade == "없음"
    keep = pipeline._lower(said, {"compare": "기준과 맞는다"}, state=RunState())
    assert keep.evals[0].grade == "낸다"


def test_시나리오_비율은_무게로_세고_섞인_스코어를_나눈다():
    """🔴 §5 — 새 수식을 만들지 않는다. 돌연변이: 단순 개수 비율.

    ⚠️ **`our_prob` 이 아니라 `_from_scenarios` 를 부른다** — 사용자 지시
       2026-10-09 ③ 이 *"기준이 없을 때 시나리오 비율을 그대로 우리 열로 쓰지
       않는다"* 로 바꿨기 때문이다. 🔴 비율을 **세는 규칙**은 그대로 지킨다(참고로
       카드 사유에 적히고, 돌연변이가 들어오면 그 수가 조용히 틀린다).
    """
    from app.core import compare
    from app.core.schema import HypoSet, Scenario
    rows = [Scenario(id="A", outcomes=[(2, 0)], mechanism="m", strength=0.8),
            Scenario(id="B", outcomes=[(1, 1)], mechanism="m", strength=0.4),
            Scenario(id="C", outcomes=[(0, 1)], mechanism="m", strength=0.4)]
    got, why = compare._from_scenarios(HypoSet(scenarios=rows))
    assert got is not None
    assert round(got.home, 3) == 0.5 and round(got.draw, 3) == 0.25
    assert "무게" in why
    # 🔴🔴 **섞인 스코어는 나눠 센다**(2026-10-06(5차) ① 실측) — 종전에는 그 무게가
    #    통째로 사라져 무승부가 0% 로 나왔다. `2-2`·`2-3` 은 무/원정 반반이다.
    mixed = [Scenario(id="A", outcomes=[(2, 2), (2, 3)], mechanism="m",
                      strength=0.8)]
    said, why2 = compare._from_scenarios(HypoSet(scenarios=mixed))
    assert said is not None, why2
    assert round(said.draw, 3) == 0.5 and round(said.away, 3) == 0.5, said
    # ⚠️ 스코어가 아예 없으면 **그때는** 못 센다
    empty = [Scenario(id="A", outcomes=[], mechanism="m", strength=0.8)]
    none, why3 = compare._from_scenarios(HypoSet(scenarios=empty))
    assert none is None and "무게가 0" in why3, why3


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **사용자 지시 2026-10-06(5차)** — ① 무승부 필수 · ② 다섯 경기 · ③ 리그 Elo
# ══════════════════════════════════════════════════════════════════


def test_축구_시나리오에_무승부_갈래가_보강된다():
    """🔴 ① — 무승부 갈래가 **하나도 없으면** 코드가 넣는다. 돌연변이: 보강 제거.

    🔴 근거 변수가 있으면 **그 무게**를 쓴다(없으면 바닥값 = `[보강]` 기본값).
    """
    from app.core.schema import Facts, Scenario, Variable
    from app.core.stages import s6_hypo
    from app.core.state import RunState
    import importlib
    ref = importlib.import_module("tests.e2e.test_v6_replay")._ref()
    scen = [Scenario(id="A", outcomes=[(2, 0)], mechanism="m", strength=1.0),
            Scenario(id="B", outcomes=[(0, 1)], mechanism="m", strength=1.0)]
    mine = Variable(id="S04", type="match_type", subject=ref.home, favors="both",
                    goals="none", target="match_type", hardness="soft",
                    weight=0.4, claim="친선", quote="친선", from_rule="S04")
    got = s6_hypo._soccer_forms(ref, Facts(match_format="friendly"), scen,
                                [mine], state=RunState())
    draws = [s for s in got if any(h == a for h, a in s.outcomes)]
    assert draws, "🔴 무승부 갈래가 안 들어왔다"
    said = draws[0]
    assert said.added_by == "code" and "무승부" in said.mechanism
    # 🔴 근거 변수를 driver 로 들어야 `_strength` 가 그 무게를 센다
    assert said.driver_vars == ["S04"], said.driver_vars
    # ⚠️ 이미 무승부가 있으면 **더하지 않는다**
    again = s6_hypo._soccer_forms(
        ref, Facts(match_format="friendly"),
        [*scen, Scenario(id="C", outcomes=[(1, 1)], mechanism="m", strength=1.0)],
        [mine], state=RunState())
    assert len([s for s in again if any(h == a for h, a in s.outcomes)]) == 1


def test_직전_경기를_다섯까지_따라간다():
    """🔴 ② — 링크 상한 5 · 경기당 fetch 상한 5. 돌연변이: 상한 제거/1 로 되돌리기."""
    from app.collect import fotmob
    from app.core.stages import s2_facts
    assert fotmob.PREV_MATCHES == 5
    assert s2_facts.FOLLOW_CAP == 5
    # 🔴 **하루 캐시**다 — 자리 이름에 날짜가 들어간다
    assert s2_facts.FOLLOW_DIR.name == "follow"


def test_평소_XI_는_선발_빈도_상위_열한명이다():
    """🔴 §4-1 — 빈도 순. 돌연변이: 직전 한 경기만 쓰기 → 11명을 못 고른다."""
    from app.core.schema import XI, Player
    from app.core.stages.s2b_base import ranked, usual_xi
    def _xi(names):
        return XI(team="team:000129", state="none",
                  lineup=[Player(name=n) for n in names])
    rows = [_xi([f"P{i}" for i in range(11)]),
            _xi([f"P{i}" for i in range(1, 12)]),
            _xi([f"P{i}" for i in range(1, 12)])]
    got, how = usual_xi(rows)
    assert len(got) == 11 and "3경기" in how, (got, how)
    # 🔴 세 경기 중 세 번 나온 P1~P10 이 **한 번 나온 P0 보다 앞**이다
    assert "P0" not in got and "P11" in got, got
    # 🔴 `ranked` 는 **전원**을 순위로 든다 — 결장자를 빼고 채울 재료다
    assert len(ranked(rows)) == 12


def test_리그_Elo_는_우리가_계산하고_clubelo_는_dead_다():
    """🔴 ③ — football-data 결과로 **우리가** 굴린다. 돌연변이: clubelo 를 다시 켜기."""
    from app import rules
    from app.collect import leagueelo
    said = rules.rating_source("clubelo")
    assert said and said.get("allowed") is False, said
    box = leagueelo.table()
    assert float(box["k"]) == 20.0 and float(box["start"]) == 1500.0
    assert "PL" in [str(c) for c in box["competitions"]]
    # 🔴 Elo 는 **시간 순**으로 굴린다 — 경기 전 등급이 적합 입력이다
    matches = [{"utcDate": "2026-01-01T12:00:00Z", "homeTeam": {"name": "A"},
                "awayTeam": {"name": "B"},
                "score": {"fullTime": {"home": 1, "away": 0}}},
               {"utcDate": "2026-01-08T12:00:00Z", "homeTeam": {"name": "B"},
                "awayTeam": {"name": "A"},
                "score": {"fullTime": {"home": 0, "away": 0}}}]
    rate, rows = leagueelo.compute(matches, k=20.0, start=1500.0)
    assert rate["A"] > 1500.0 > rate["B"], rate
    assert rows[0]["home_elo"] == 1500.0, rows[0]
    # 🔴 두 번째 줄의 **경기 전** 등급이 첫 경기 결과를 담고 있다(누설 없음)
    assert rows[1]["home_elo"] < 1500.0 < rows[1]["away_elo"], rows[1]


def test_리그_경기의_계수도_같은_대회_유형만_쓴다():
    """🔴 ③ — `league:PL` 계수는 **PL 경기에만**. 돌연변이: 리그 하나로 뭉치기."""
    from app.core import base
    # 🔴 판정점은 `competition.key_of` **하나**다(지시 2026-10-09(4차) §1) —
    #    `s5_verify.league_code` 는 그 겉옷이라 지웠다.
    from app.core.competition import key_of, short_key
    assert short_key(key_of(competition="Premier League")[0]) == "PL"
    got, why = base.triple_of("league:PL", 100.0)
    assert got is not None, why
    assert "league:PL" in why
    none, why2 = base.triple_of("league:K리그1", 100.0)
    assert none is None and "계수가 없다" in why2, why2


def test_피드_종목_열쇠는_표에서_온다():
    """🔴 ④ — 대회명 → 피드 열쇠. 돌연변이: 모르는 대회에 아무 열쇠나 붙이기.

    ⚠️ 실측 2026-10-06: 이 피드에 **대표팀 친선·CONCACAF·AFC 가 없다**.
    """
    import importlib
    from app import rules
    from app.core import odds
    feed = [f for f in rules.odds_feeds() if f["name"] == "the_odds_api"][0]
    ref = importlib.import_module("tests.e2e.test_v6_replay")._ref()
    got, why = odds.sport_key_of(feed, ref)       # Friendlies
    assert got == "" and "친선" in why, (got, why)
    said, _ = odds.sport_key_of(feed, ref.model_copy(
        update={"competition": "Premier League"}))
    assert said == "soccer_epl"
    # 🔴 표가 측정값을 든다 — 친선·CONCACAF·AFC 는 `null` 이다
    scope = dict(feed.get("scope") or {})
    assert scope["national_friendly"] is None and scope["concacaf"] is None
    assert scope["epl"] == "soccer_epl"


def test_크레딧이_든_요청만_센다():
    """🔴 §2-2 — `/events` 는 0 크레딧이다(실측). 돌연변이: 늘 1 로 세기."""
    from app.core import odds
    assert odds._last_cost({"x-requests-last": "0"}) == 0
    assert odds._last_cost({"x-requests-last": "1"}) == 1
    # 🔴 모르면 **1 로 본다** — 0 으로 보면 한도를 조용히 넘는다
    assert odds._last_cost({}) == 1
    said = odds._quota({"x-requests-remaining": "499", "x-requests-used": "1"})
    assert said == {"remaining": 499, "used": 1, "limit_said": 500}, said


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **사용자 지시 2026-10-06(6차)** — ① 기준에서 출발 · ③ 포지션 짝
# ══════════════════════════════════════════════════════════════════


def _vars(*specs):
    from app.core.schema import Variable
    out = []
    for i, (kind, favors, weight) in enumerate(specs):
        out.append(Variable(id=f"V{i}", type=kind, subject="team:000129",
                            favors=favors, goals="none", target="t",
                            hardness="soft", weight=weight, claim="c",
                            quote="q"))
    return out


def test_우리_확률이_기준에서_출발한다():
    """🔴 ① — `OurProb` 는 ①②의 확률에서 **로그 오즈로** 움직인다.

    돌연변이: 출발점을 무시하고 시나리오 비율로 돌아가기 → 기준과 멀어져 빨개진다.
    """
    from app.core import compare
    from app.core.schema import ProbTriple
    start = ProbTriple(home=0.54, draw=0.29, away=0.17)
    got, why = compare.our_prob(None, start=start, variables=[], adjusted=False)
    assert got is not None and "기준" in why
    # 🔴 움직일 변수가 없으면 **기준 그대로**다
    assert abs(got.home - 0.54) < 0.005 and abs(got.away - 0.17) < 0.005, got
    # 🔴 `stakes`(홈 유리 · 무게 2.0)가 홈을 **올린다**
    said, why2 = compare.our_prob(None, start=start,
                                  variables=_vars(("stakes", "home", 2.0)),
                                  adjusted=False)
    assert said is not None and said.home > got.home, (said, why2)


def test_이동에_쓰는_유형이_열뿐이다():
    """🔴 ① — 목록 밖 유형은 **안 움직인다**. 돌연변이: 목록을 늘리기.

    ⚠️ 7차 §4 가 `lineup_intent` **하나를 더했다**(6차에서 빠져 있었다).
    """
    from app.core import compare
    box = compare.move_rules()
    assert sorted(box["movers"]) == sorted([
        "stakes", "coach_intent", "coach_conflict", "match_type", "fatigue",
        "match_format", "individual_title", "streak_psych", "venue_weather",
        "lineup_intent"])
    assert float(box["k"]) == 0.15 and float(box["cap_logodds"]) == 0.5
    # 🔴 ① 이 머금은 유형은 **빠진다**
    for kind in ("strength_gap", "recent_pattern", "home_field", "h2h_pattern"):
        assert kind in box["skip"], kind


def test_기준이_머금은_유형은_우리_열을_안_움직인다():
    """🔴 ① — `recent_pattern`·`home_field`·`h2h` 는 이동 0.

    🔴 결장 계열은 **② 가 움직였을 때만** 0 이다(지시 2026-10-09 ③ — ② 가 못 쓰면
       ③ 이 센다). ⚠️ 그 둘이 **동시에** 세면 이중 계산이다.
    """
    from app.core import compare
    from app.core.schema import ProbTriple
    start = ProbTriple(home=0.5, draw=0.3, away=0.2)
    rows = _vars(("recent_pattern", "home", 3.0), ("home_field", "home", 3.0),
                 ("h2h_pattern", "home", 3.0))
    got, why = compare.our_prob(None, start=start, variables=rows,
                                adjusted=False)
    assert got is not None and abs(got.home - 0.5) < 0.005, (got, why)
    # 🔴 ② 가 움직였으면 결장 계열도 빠진다(두 번 세지 않는다)
    absent = _vars(("def_absence", "away", 3.0))
    with_adj, _ = compare.our_prob(None, start=start, variables=absent,
                                   adjusted=True)
    assert with_adj is not None and abs(with_adj.away - 0.2) < 0.005, with_adj
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **②가 못 쓰면 ③이 센다**(사용자 지시 2026-10-09 ③)
    # ══════════════════════════════════════════════════════════════════
    #
    # > 라인업 보정 환산 계수가 없는 리그에서는 결장 계열 변수를 ③ 무게표로
    # > 센다(②에 넘겼는데 ②가 **못 쓰면 0 이 되는 구멍**).
    #
    # ⚠️ 종전 계약은 *"② 가 없으면 그 변수는 움직이지도 않는다"* 였다 — 그것이
    #    바로 구멍이었다(실측 2026-10-09 대전–전북: 결장 둘이 어디서도 안 세졌다).
    # 🔴 **둘이 동시에 세지는 않는다** — 위 `adjusted=True` 줄이 그것을 지킨다.
    moved, why2 = compare.our_prob(None, start=start, variables=absent,
                                   adjusted=False)
    assert moved is not None, why2
    assert moved.away > 0.2 + 0.005, (moved, why2)
    assert "def_absence" in why2 or "IR" in why2, why2


def test_한_결과_이동이_로그오즈_0_5_를_넘지_않는다():
    """🔴 ① — 상한. 돌연변이: 상한 제거 → 큰 무게가 확률을 뒤집는다."""
    from app.core import compare
    from app.core.schema import ProbTriple
    start = ProbTriple(home=0.5, draw=0.3, away=0.2)
    many = _vars(*[("stakes", "home", 3.0)] * 8)      # 합 3.6 로그 오즈
    got, why = compare.our_prob(None, start=start, variables=many,
                                adjusted=False)
    assert got is not None and "상한" in why, why
    # 🔴 0.5 로그 오즈면 홈은 0.5 → 0.62 쯤이다(뒤집히지 않는다)
    assert 0.55 < got.home < 0.68, got


def test_기준이_없으면_우리_열을_비우고_그_말을_적는다():
    """🔴🔴 **사용자 지시 2026-10-09 ③** — 돌연변이: 시나리오 비율을 우리 열로 쓴다.

    > 기준이 없을 때 **시나리오 비율을 그대로 우리 열로 쓰지 않는다**
    > (앞 지시 5번 그대로).

    🔴 왜 계약으로 박나 — 실측 2026-10-08(마리노스–교토산업대): 변수가 `S03`
       **하나**(그마저 수치 없음)인데 우리 열이 40/29/31 로 찍혀 **대학팀 원정승
       31%** 가 나왔다. 그 수는 분석이 아니라 **갈래를 센 수**다.
    ⚠️ 그래도 비율은 **버리지 않는다** — 사유에 참고로 남는다(#3 조용한 0 금지).
    """
    from app.core import compare
    from app.core.schema import HypoSet, Scenario
    rows = [Scenario(id="A", outcomes=[(2, 0)], mechanism="m", strength=1.0),
            Scenario(id="B", outcomes=[(1, 1)], mechanism="m", strength=1.0)]
    got, why = compare.our_prob(HypoSet(scenarios=rows), start=None)
    assert got is None, f"기준이 없는데 우리 열에 수가 찍혔다: {got}"
    assert "우리 열을 비운다" in why, why
    # 🔴 참고 수는 **남아 있어야** 한다 — 그 수를 없애면 자료가 사라진다
    assert "참고로 시나리오 비율" in why and "50%" in why, why


def test_기여표는_같은_포지션끼리_짝짓는다():
    """🔴 ③ — 다른 포지션은 **구조 변경**이다. 돌연변이: 순서대로 짝짓기."""
    from app.core.stages.s2b_base import _deltas
    values = {"DF1": 20e6, "DF2": 5e6, "FW1": 10e6}
    pos = {"DF1": "DF", "DF2": "DF", "FW1": "FW"}
    # ① 같은 포지션 교체 — 짝이 맺힌다
    got = _deltas({"team:000129": ["DF1", "FW1"]}, {"team:000129": ["DF2", "FW1"]}, values,
                  pos=pos)[2]
    said = [d for d in got if d.out_name == "DF1"][0]
    assert said.in_name == "DF2" and said.pos == "DF" and not said.structural
    assert said.delta_s < 0, said
    # ② 다른 포지션뿐 — **구조 변경**
    other = _deltas({"team:000129": ["DF1", "FW1"]}, {"team:000129": ["FW1", "MFX"]},
                    {**values, "MFX": 8e6}, pos={**pos, "MFX": "MF"})[2]
    assert all(d.structural for d in other), other
    assert {d.pos for d in other} == {"DF", "MF"}, other
    # ③ 포지션을 모르면 짝을 **안 맺는다**
    unknown = _deltas({"team:000129": ["DF1"]}, {"team:000129": ["DF2"]}, values, pos={})[2]
    assert unknown and unknown[0].structural, unknown


def test_라인업_보정이_확률을_움직이고_신뢰도를_함께_적는다():
    """🔴 ② 배선(6차 ②) — `ds_to_dr` 가 있으면 확률이 **움직인다**. 돌연변이: 계수 무시.

    🔴 카드에 **R²·표본**이 함께 나와야 한다(계수 신뢰도를 숨기지 않는다).
    """
    from app import rules
    from app.core import base
    from app.core.schema import BaseProb, ProbTriple
    box = rules.base_model("national_friendly")
    assert box.get("ds_to_dr"), "🔴 환산 계수가 config 에 없다"
    fit = dict(box.get("ds_fit") or {})
    assert fit.get("n") and fit.get("r2"), fit
    start = BaseProb(probs=ProbTriple(home=0.54, draw=0.29, away=0.17),
                     home_elo=1722.0, away_elo=1653.0, dr=69.0,
                     comp_kind="national_friendly")
    got = base.adjust(start, kind="national_friendly",
                      delta_s={"team:000129": -1.07}, strength_pct={},
                      deltas=[], home="team:000129", away="team:000245",
                      estimated=0, why="②")
    assert got.moved and got.probs is not None
    # 🔴 홈이 약해졌으니 홈 승이 **내려간다**
    assert got.probs.home < 0.54, got.probs
    assert "%p" in got.why and "R²" in got.why, got.why
    # ⚠️ 계수가 없는 유형은 **안 움직인다**(리그는 아직 가치 적합이 없다)
    none = base.adjust(start.model_copy(update={"comp_kind": "league:PL"}),
                       kind="league:PL", delta_s={"team:000129": -1.07},
                       strength_pct={}, deltas=[], home="team:000129",
                       away="team:000245", estimated=0, why="②")
    assert not none.moved and "환산 계수가 없다" in none.why


def test_k_는_임시값이라고_표에_적혀_있다():
    """🔴 6차 ④ — `k` 를 바꾸지 않는다 · 표에 *"임시값"* 이 적혀 있다."""
    import pathlib
    from app.core import compare
    assert float(compare.move_rules()["k"]) == 0.15
    said = pathlib.Path("config/interpret_rules.yaml").read_text(encoding="utf-8")
    i = said.index("our_prob:")
    assert "임시값" in said[i:i + 900], "🔴 `k` 가 임시값이라는 말이 표에 없다"


def test_셋째층_이동량이_구조로_남는다():
    """🔴 6차 ③ — 카드가 **글자를 다시 파싱하지 않는다**(`Card.moves`)."""
    from app.core import compare
    from app.core.schema import Card, ProbTriple
    assert "moves" in Card.model_fields
    start = ProbTriple(home=0.5, draw=0.3, away=0.2)
    compare.our_prob(None, start=start, variables=_vars(("stakes", "home", 2.0)),
                     adjusted=False)
    assert compare.MOVES and compare.MOVES[0]["type"] == "stakes"
    assert compare.MOVES[0]["logodds"] == 0.3, compare.MOVES
    # 🔴 다음 호출이 **앞의 기록을 지운다**(묵은 이동량이 카드에 남으면 거짓이다)
    compare.our_prob(None, start=start, variables=[], adjusted=False)
    assert compare.MOVES == []


def test_선수별_pp_는_상쇄되는_큰_항목에_안_적는다():
    """🔴 6차 ② — 쪼갠 `%p` 는 **이동을 만든 식과 같은 식**으로 나눈다.

    ⚠️ 몫이 1 을 크게 넘는 줄(서로 상쇄되는 큰 항목)에는 `%p` 를 **안 적는다** —
       실측 2026-10-06: 김민재(−17.16)와 황희찬(+16.09)의 몫이 ±16 이었고 그것을
       `−19%p`·`+18%p` 로 적으면 거짓으로 읽힌다.
    """
    from app.core import base
    from app.core.schema import LineupDelta
    rows = [LineupDelta(team="team:000129", out_name="A", in_name="B",
                        delta_s=-0.5),
            LineupDelta(team="team:000245", out_name="C", in_name="D",
                        delta_s=-0.5)]
    got = base._share(rows, -1.0, home="team:000129", away="team:000245",
                      delta_s={"team:000129": -0.5, "team:000245": -0.5})
    # 🔴 홈 −0.5, 원정 −0.5 → 분모 0 … 이동이 없으니 **아무 줄에도 안 적는다**
    assert all(d.delta_home_pct is None for d in got), got
    # 🔴 홈만 약해진 경우 — 그 줄에 `%p` 가 붙고 **부호가 이동과 같다**
    one = base._share([rows[0]], -1.2, home="team:000129",
                      away="team:000245", delta_s={"team:000129": -0.5})
    assert one[0].delta_home_pct == -1.2, one[0]
    # 🔴 상쇄되는 큰 항목(몫 16배)은 **비워 둔다**
    big = [LineupDelta(team="team:000129", out_name="K", delta_s=-17.16,
                       structural=True),
           LineupDelta(team="team:000129", in_name="H", delta_s=16.09,
                       structural=True)]
    said = base._share(big, -1.2, home="team:000129", away="team:000245",
                       delta_s={"team:000129": -1.07})
    assert all(d.delta_home_pct is None for d in said), said


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **사용자 지시 2026-10-06(7차)** — 순위표·경우의 수·상태별 이동·IR11
# ══════════════════════════════════════════════════════════════════


def _group_fixture() -> dict:
    """🔴 실측 표(네이션스리그 C 3조 · 2026-10-06) — 지어낸 수가 아니다."""
    return {
        "group": "Grp. 3",
        "zones": {"Promotion": 1, "Promotion qualification": 2},
        "rows": [
            {"rank": 1, "name": "Slovakia", "played": 3, "wins": 2, "draws": 1,
             "losses": 0, "goals_for": 5, "goals_against": 2, "goal_diff": 3,
             "points": 7, "zone": "Promotion"},
            {"rank": 2, "name": "Moldova", "played": 3, "wins": 1, "draws": 1,
             "losses": 1, "goals_for": 3, "goals_against": 4, "goal_diff": -1,
             "points": 4, "zone": "Promotion qualification"},
            {"rank": 3, "name": "Faroe Islands", "played": 3, "wins": 0,
             "draws": 3, "losses": 0, "goals_for": 3, "goals_against": 3,
             "goal_diff": 0, "points": 3, "zone": ""},
            {"rank": 4, "name": "Kazakhstan", "played": 3, "wins": 0, "draws": 1,
             "losses": 2, "goals_for": 3, "goals_against": 5, "goal_diff": -2,
             "points": 1, "zone": ""}],
        "fixtures": [], "remaining": 6}


def test_경우의_수가_결과_아홉_칸을_센다():
    """🔴 §2 — 이 경기 3 × 다른 경기 3. 돌연변이: 다른 경기를 무시(3칸만)."""
    from app import rules
    from app.core import standing as st
    order, _, ok, _ = rules.tiebreak("UEFA Nations League C Grp. 3")
    assert ok, "🔴 네이션스리그 동률 규칙이 확인 표시가 아니다"
    assert order[:2] == ["points", "h2h_points"], order
    cells = st.grid(_group_fixture(), home="Kazakhstan", away="Faroe Islands",
                    order=order, others=[("Moldova", "Slovakia")])
    assert len(cells) == 9, len(cells)
    # 🔴 실측과 같은 수 — 카자흐가 이기고 몰도바가 지면 **2위(승격 PO)**
    # 🔴 둘째 칸은 **그 경기의 말**이다(지시 2026-10-09 ①) — 이름이 실려 와야 한다
    def _pick(ours: str, them: str) -> dict:
        return next(c for c in cells if c["ours"] == ours
                    and c["others"][0]["result"] == them)

    assert cells[0]["others"][0]["home"] == "Moldova", cells[0]["others"]
    assert cells[0]["others"][0]["away"] == "Slovakia", cells[0]["others"]
    got = _pick("home", "away")
    assert got["ranks"]["Kazakhstan"] == 2
    assert got["zones"]["Kazakhstan"] == "Promotion qualification"
    # 🔴 비기면 4위다(구역 없음)
    draw = _pick("draw", "home")
    assert draw["ranks"]["Kazakhstan"] == 4 and draw["zones"]["Kazakhstan"] == ""


def test_상태가_다섯_글자_중_하나다():
    """🔴 §2 — `must_win`·`draw_enough`·`margin_needed`·`nothing`·`unknown`.

    실측: 카자흐 **must_win** · 페로 **draw_enough**(사용자가 예상한 그 둘).
    돌연변이: 구역만 보고 순위를 무시 → 3·4위가 같아 보여 `nothing` 이 된다.
    """
    from app import rules
    from app.core import standing as st
    order, _, _, _ = rules.tiebreak("UEFA Nations League")
    box = _group_fixture()
    cells = st.grid(box, home="Kazakhstan", away="Faroe Islands", order=order,
                    others=[("Moldova", "Slovakia")])
    kz, why1 = st.state_of(cells, "Kazakhstan", is_home=True,
                           zones=box["zones"])
    fo, why2 = st.state_of(cells, "Faroe Islands", is_home=False,
                           zones=box["zones"])
    assert kz == "must_win", (kz, why1)
    assert fo == "draw_enough", (fo, why2)
    assert kz in st.STATES and fo in st.STATES
    # 🔴 순위표가 없으면 **unknown** — 지어내지 않는다(금지 조항)
    none, why3 = st.state_of([], "Kazakhstan", is_home=True, zones={})
    assert none == "unknown" and "순위표" in why3
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **구역이 하나도 없는 조에서도 순위로 센다**
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 2026/27 네이션스리그 **League C 는 강등이 없다** — 3·4위에 구역 표시가
    #     아예 없다. 🔴 구역만 보면 둘이 같아 보여 `must_win` 을 놓친다(실측).
    #     그 함정을 이 검사가 잡는다(돌연변이: 순위를 무시하고 구역만 보기).
    flat = {**box, "zones": {}}
    said = st.grid(flat, home="Kazakhstan", away="Faroe Islands", order=order)
    kz2, why4 = st.state_of(said, "Kazakhstan", is_home=True, zones={})
    assert kz2 == "must_win", (kz2, why4)
    assert "위" in why4, why4


def test_상태별_이동이_표에서_온다():
    """🔴 §4 — `draw_enough` → 무승부 +k(5백이면 ×2) · `must_win` → **이동 없음**.

    돌연변이: `must_win` 에 1X2 이동을 주기 / `nothing` 에 상대 +k 를 주기.
    """
    from app.core import compare
    from app.core.schema import ProbTriple, Variable
    box = compare.move_rules()["outlook_moves"]
    assert box["must_win"]["side"] is None and box["must_win"]["goals"] == "up"
    assert box["nothing"]["side"] is None
    assert box["draw_enough"]["side"] == "draw"
    assert int(box["draw_enough"]["with_low_block"]) == 2
    assert box["margin_needed"]["require_counter"] is True
    start = ProbTriple(home=0.48, draw=0.33, away=0.19)
    look = {"states": {"Faroe": {"state": "draw_enough"},
                       "Kazakh": {"state": "must_win"}}}
    got, why = compare.our_prob(None, start=start, variables=[], outlook=look)
    assert got is not None and got.draw > 0.33, (got, why)
    # 🔴 `must_win` 은 1X2 를 **안 움직인다**
    only = {"states": {"Kazakh": {"state": "must_win"}}}
    said, _ = compare.our_prob(None, start=start, variables=[], outlook=only)
    assert said is not None and abs(said.draw - 0.33) < 0.005, said
    # 🔴 5백(IR01)이 함께 걸리면 **두 번**이다
    five = [Variable(id="IR01-away", type="lineup_intent",
                     subject="team:000080", favors="away", goals="down",
                     target="formation", hardness="soft", weight=0.7,
                     claim="Faroe 5백으로 내려선다", quote="five at the back",
                     from_rule="IR01-away")]
    twice, why2 = compare.our_prob(None, start=start, variables=five,
                                   outlook={"states": {"Faroe": {"state": "draw_enough"}}})
    assert twice is not None
    assert any(m["id"] == "경우의수:Faroe" and m["logodds"] == 0.3
               for m in compare.MOVES), compare.MOVES


def test_IR11_문턱이_4일과_시차3시간_거리3000km_다():
    """🔴 §6 — 둘 다 필요하다(4일 이내 **그리고** 시차·거리). 돌연변이: 문턱 완화."""
    from app.core.stages import s5_verify as s5
    assert s5.FATIGUE_DAYS == 4 and s5.FATIGUE_TZ_HOURS == 3
    assert s5.FATIGUE_KM == 3000
    # 🔴 실측(페로): 토르스하운 → 아스타나 — 시차·거리가 문턱을 넘는다
    tz, km, why = s5._travel({"last_lat": 62.01, "last_lon": -6.77,
                              "lat": 51.13, "lon": 71.43}, None, "x")
    assert km is not None and km > 3000, (km, why)
    assert tz is not None and abs(tz) > 3, (tz, why)
    # ⚠️ 좌표가 없으면 **안 돈다**(지어내지 않는다)
    none = s5._travel({}, None, "x")
    assert none[0] is None and "좌표" in none[2]


def test_대회_규정은_확인한_것만_확인_표시다():
    """🔴 §1 — `verified` 는 **공식 문서를 읽은 것만**. 돌연변이: 전부 true 로."""
    from app import rules
    order, zones, ok, src = rules.tiebreak("UEFA Nations League")
    assert ok and src.startswith("https://documents.uefa.com"), src
    assert "Promotion" in zones
    # 🔴 CONCACAF 는 **확인 전**이다 — 가정이고 카드가 그 사실을 적는다
    _, _, ok2, why2 = rules.tiebreak("CONCACAF Nations League")
    assert ok2 is False and "확인" in why2, why2


def test_동기_낱말에_이겨야_비겨도_골차가_있다():
    """🔴 §3 — 그 문장을 `stakes_vague` 로 **버리지 않는다**. 돌연변이: 목록 축소."""
    from app.core.stages.s5_verify import stakes_ok
    for said in ("이기지 못하면 강등이 확정된다", "비겨도 조 2위를 지킨다",
                 "2골 차로 이겨야 순위가 올라간다",
                 "Kazakhstan must win to keep hopes alive",
                 "a draw is enough for the Faroe Islands"):
        ok, why = stakes_ok(said)
        assert ok, (said, why)
    # ⚠️ 일정 안내는 그대로 **버린다**
    bad, why = stakes_ok("경기는 화요일 저녁에 열린다")
    assert not bad, why


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **시장은 참고용이다**(사용자 지시 2026-10-06(8차) ④) — AST 로 잠근다
# ══════════════════════════════════════════════════════════════════


def test_시장_확률이_우리확률_등급_함수의_입력이_아니다():
    """🔴🔴 ④ — `MarketProb`·시장 확률이 `our_prob`·등급 계산 함수의 **입력으로 들어가면
    실패**다. 돌연변이: `our_prob(..., market=…)` 를 더하거나 `_lower` 에 시장을 넘기기.

    🔴 세는 방법: **서명(signature)** 과 **본문**을 둘 다 AST 로 본다.
      ① 금지 함수의 인자 이름에 `market`·`mkt`·`odds`·`price` 가 없다
      ② 그 함수 본문에서 `MarketProb`·`market.probs`·`_market_triple` 을 안 읽는다
    ⚠️ 글자 검사가 아니라 **AST** 다(주석에 그 말이 있는 것은 괜찮다 · D46).
    """
    import ast as _ast

    banned_args = ("market", "mkt", "odds", "price", "vig", "book")
    targets = {
        "app/core/compare.py": ("our_prob", "_apply", "_from_scenarios",
                                "grade_step", "weight_rules", "tilt_reasons"),
        "app/core/pipeline.py": ("_lower",),
        "app/core/stages/s7_judge.py": ("_grade", "_enough", "_cap",
                                        "_same_direction_cap"),
        "app/survive.py": ("verdict_word",),
    }
    bad: list[str] = []
    for rel, names in targets.items():
        p = ROOT / rel
        if not p.is_file():
            continue
        tree = _ast.parse(p.read_text(encoding="utf-8"))
        for node in _ast.walk(tree):
            if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                continue
            if node.name not in names:
                continue
            args = [a.arg for a in (node.args.args + node.args.kwonlyargs)]
            for a in args:
                if any(w in a.lower() for w in banned_args):
                    bad.append(f"{rel}:{node.name} 인자 `{a}`")
            # ② 본문에서 시장 확률을 읽나
            for sub in _ast.walk(node):
                if isinstance(sub, _ast.Name) and sub.id in ("MarketProb",
                                                             "_market_triple"):
                    bad.append(f"{rel}:{node.name} 본문이 `{sub.id}` 를 쓴다")
                if isinstance(sub, _ast.Attribute) and sub.attr == "probs" \
                        and isinstance(sub.value, _ast.Name) \
                        and sub.value.id in ("market", "mkt", "user_market"):
                    bad.append(f"{rel}:{node.name} 본문이 `{sub.value.id}.probs`")
    assert not bad, "🔴 시장이 판정 경로로 들어왔다: " + " · ".join(bad)


def test_시장_확률은_설명_함수만_읽는다():
    """🔴 ④ 반대 방향 — 시장을 읽는 곳은 **설명·표시 함수**뿐이어야 한다.

    🔴 `_market_triple` 을 부르는 곳을 AST 로 센다: `verdict_of`(판정 **글자**만 만든다)
       · `market_reasons`(이유 후보) · `direction_line`(세 열을 **적는다**) · `moved`.
    ⚠️ 그 넷 밖에서 부르면 시장이 수에 닿을 길이 생긴 것이다.
    """
    import ast as _ast

    allow = {"verdict_of", "market_reasons", "direction_line", "moved",
             "_market_triple"}
    tree = _ast.parse((ROOT / "app/core/compare.py").read_text(encoding="utf-8"))
    for node in _ast.walk(tree):
        if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            continue
        for sub in _ast.walk(node):
            if isinstance(sub, _ast.Call) and isinstance(sub.func, _ast.Name) \
                    and sub.func.id == "_market_triple":
                assert node.name in allow, (
                    f"🔴 `{node.name}` 이 시장 확률을 읽는다 — 설명 함수만 읽어야 한다")


def test_역습_갈래가_필수형으로_들어온다():
    """🔴 ③ — `must_win`·`margin_needed` 팀의 **상대 역습 갈래**가 생기고 driver·전개
    문장이 맞는지 본다. ⚠️ 검수 기준은 **시장 거리와 무관**하다(8차 ③).
    """
    from app.core.schema import Facts, Scenario, Variable
    from app.core.stages import s6_hypo
    from app.core.state import RunState
    import importlib
    ref = importlib.import_module("tests.e2e.test_v6_replay")._ref()
    box = {"무승부": {"scores": ["1-1"]},
           "역습": {"when_states": ["must_win", "margin_needed"],
                   "scores_home_pusher": ["1-2", "0-1"],
                   "scores_away_pusher": ["2-1", "1-0"],
                   "mechanism": "{pusher} 가 {why} 라서 라인을 올리고 {other} 가 역습"}}
    facts = Facts(standings={"outlook_states": {
        ref.home_name: {"state": "margin_needed", "margin": 2, "why": "x"}}})
    mine = Variable(id="R9", type="stakes", subject=ref.home, favors="home",
                    goals="none", target="승격", hardness="hard", weight=2.0,
                    claim="2골 차로 이겨야 한다", quote="q")
    # 🔴 홈이 밀어붙이는데 **원정이 이기는 갈래가 없다** → 역습형이 들어와야 한다
    scen = [Scenario(id="A", outcomes=[(2, 0)], mechanism="m", strength=1.0),
            Scenario(id="B", outcomes=[(1, 1)], mechanism="m", strength=1.0)]
    got = s6_hypo._counter(ref, facts, scen, [mine], box, state=RunState())
    new = [s for s in got if s.type == "counter"]
    assert new, "🔴 역습 갈래가 안 생겼다"
    said = new[0]
    assert said.added_by == "code" and "역습" in said.mechanism
    # 🔴 **전개 문장**이 두 팀 이름과 까닭을 담는다
    assert ref.home_name in said.mechanism and ref.away_name in said.mechanism
    assert "2골" in said.mechanism, said.mechanism
    # 🔴 **driver** 는 그 상태를 만든 동기 변수다
    assert said.driver_vars == ["R9"], said.driver_vars
    # 🔴 원정이 이기는 갈래가 **이미 있으면** 더하지 않는다
    again = s6_hypo._counter(ref, facts,
                            [*scen, Scenario(id="C", outcomes=[(0, 2)],
                                             mechanism="m", strength=1.0)],
                            [mine], box, state=RunState())
    assert not [s for s in again if s.type == "counter"]
    # ⚠️ 상태가 없으면 **안 만든다**(지어내지 않는다)
    none = s6_hypo._counter(ref, Facts(), scen, [mine], box, state=RunState())
    assert not [s for s in none if s.type == "counter"]
    # 🔴🔴 **배선까지 센다** — `_soccer_forms` 가 `_counter` 를 부르는지 AST 로 본다.
    #    ⚠️ 함수만 검사하면 그 호출을 지워도 초록이다(실측 2026-10-06 돌연변이 ③).
    import ast as _ast
    tree = _ast.parse((ROOT / "app/core/stages/s6_hypo.py")
                      .read_text(encoding="utf-8"))
    fn = next(n for n in _ast.walk(tree)
              if isinstance(n, _ast.FunctionDef) and n.name == "_soccer_forms")
    calls = {c.func.id for c in _ast.walk(fn)
             if isinstance(c, _ast.Call) and isinstance(c.func, _ast.Name)}
    assert "_counter" in calls, "🔴 `_soccer_forms` 가 역습형을 안 부른다(배선 끊김)"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **사용자 지시 2026-10-06(9차)** — 합계 상한 · 감독 묶음 · 근거 불가 · 없음 보고
# ══════════════════════════════════════════════════════════════════


def test_이동은_경기당_합계_상한을_넘지_못한다():
    """🔴 ① — **경기당 합계** ±0.5 로그 오즈. 돌연변이: 결과마다만 자르기.

    ⚠️ 실측 카자흐–페로: 무 0.300 + 홈 0.165 + 원정 0.105 = **0.570** 이 통과했다.
    🔴 지금은 합을 보고 **비율대로 줄인다** — `MOVES` 도 같은 비율로 적는다(카드의
       이동량 합이 실제와 같아야 한다).
    """
    from app.core import compare
    from app.core.schema import ProbTriple
    start = ProbTriple(home=0.48, draw=0.33, away=0.19)
    many = _vars(("coach_intent", "both", 0.7), ("fatigue", "home", 0.7),
                 ("lineup_intent", "away", 0.7), ("stakes", "home", 0.7))
    got, why = compare.our_prob(None, start=start, variables=many,
                                outlook={"states": {"X": {"state": "draw_enough"}}})
    assert got is not None and "상한" in why, why
    said = sum(abs(float(m["logodds"])) for m in compare.MOVES)
    assert said <= float(compare.move_rules()["cap_logodds"]) + 1e-9, said
    # 🔴 상한 안이면 **줄이지 않는다**
    few = _vars(("stakes", "home", 0.7))
    compare.our_prob(None, start=start, variables=few, outlook=None)
    assert abs(sum(abs(float(m["logodds"])) for m in compare.MOVES) - 0.105) < 1e-9


def test_감독_로테이션은_같은_주제면_하나다():
    """🔴 ② — `coach_intent`·`coach_conflict`·`squad_rotation` 이 같은 팀 + 같은 주제면
    **한 변수**다(출처 수만 올라간다). 돌연변이: 유형별로 따로 두기.
    """
    from app.core.stages.s5_verify import COACH_KINDS, coach_topic, merge_key
    assert set(COACH_KINDS) == {"coach_intent", "coach_conflict", "squad_rotation"}
    assert coach_topic("Karpin is expected to rotate his squad") == "rotation"
    assert coach_topic("선발 명단을 다시 바꾼다") == "rotation"
    assert coach_topic("5백으로 내려선다") == "tactic"
    assert coach_topic("Ajasa 를 선발로 기용한다") == "selection"
    a = merge_key("team:000132", "coach_intent", "Karpin",
                  claim="Karpin is expected to rotate his squad")
    b = merge_key("team:000132", "squad_rotation", "starting XI",
                  claim="Russia are expected to make changes to his starting XI")
    c = merge_key("team:000132", "coach_conflict", "tactics",
                  claim="전술 준비가 문제다")
    assert a == b, (a, b)          # 🔴 같은 주제 → 한 열쇠
    assert a != c, (a, c)          # ⚠️ 다른 주제는 따로다
    # 🔴 주제를 못 가리면 **대상 글자**로 간다(지어내지 않는다)
    d = merge_key("team:1", "coach_intent", "Mier", claim="알 수 없는 말")
    assert d[2] == "mier", d


def test_근거_불가_변수는_확률을_못_움직인다():
    """🔴 ③ 점검표 — `usable_as_basis=False` 는 ③ 이동에서 빠진다.

    ⚠️ 실측: `R2`(출처 1곳 · 근거 불가)가 +0.060 을 받았다. 돌연변이: 검사 제거.
    """
    from app.core import compare
    from app.core.schema import ProbTriple, Variable
    start = ProbTriple(home=0.5, draw=0.3, away=0.2)
    weak = [Variable(id="R2", type="fatigue", subject="team:000132",
                     favors="home", goals="none", target="result",
                     hardness="soft", weight=0.7, claim="c", quote="q",
                     usable_as_basis=False)]
    got, why = compare.our_prob(None, start=start, variables=weak, outlook=None)
    assert got is not None and abs(got.home - 0.5) < 0.005, (got, why)
    assert not compare.MOVES, compare.MOVES
    # 🔴 근거 가능하면 움직인다
    ok = [weak[0].model_copy(update={"usable_as_basis": True})]
    said, _ = compare.our_prob(None, start=start, variables=ok, outlook=None)
    assert said is not None and said.home > 0.5


def test_정보가_없다는_변수로_만들지_않는다():
    """🔴 ③ 점검표 — *"확인된 부상 정보는 없다"* 는 사실이 아니다. 돌연변이: 검사 제거."""
    from app.core.stages.s5_verify import has_info
    for said in ("이 경기 전에 홈 팀의 확인된 부상 또는 출전 정지 정보는 없다",
                 "No confirmed injuries have been reported",
                 "결장 명단은 아직 발표되지 않았다"):
        ok, why = has_info(said)
        assert not ok and "없음의 보고" in why, (said, why)
    # ⚠️ **사실**은 통과한다(없다는 말이 들어 있어도 선수를 가리키면 사실이다)
    for said in ("김민재가 부상으로 결장한다", "Ndidi 가 이 경기에서 이탈했다"):
        ok, _ = has_info(said)
        assert ok, said
    # 🔴🔴 **배선까지 센다** — `_one`(검증 한 줄)이 `has_info` 를 부르는지 AST 로 본다.
    #    ⚠️ 함수만 검사하면 그 호출을 지워도 초록이다(같은 병을 8차에서 겪었다).
    import ast as _ast
    tree = _ast.parse((ROOT / "app/core/stages/s5_verify.py")
                      .read_text(encoding="utf-8"))
    fn = next(n for n in _ast.walk(tree)
              if isinstance(n, _ast.FunctionDef) and n.name == "_one")
    calls = {c.func.id for c in _ast.walk(fn)
             if isinstance(c, _ast.Call) and isinstance(c.func, _ast.Name)}
    assert "has_info" in calls, "🔴 `_one` 이 `has_info` 를 안 부른다(배선 끊김)"


def test_오백은_무승부_쪽이고_두_번_세지_않는다():
    """🔴 9차 ③ 점검표 — `lineup_intent`(5백): **무승부 쪽만** · away 이동 **없음** ·
    `draw_enough` ×2 로 이미 셌으면 **이동 0**(이중 계산 없음).

    돌연변이: 5백을 `favors`(away) 쪽으로 움직이기 / ×2 와 변수 이동을 둘 다 주기.
    """
    import importlib
    from app.core import compare
    from app.core.schema import ProbTriple, Variable
    ref = importlib.import_module("tests.e2e.test_v6_replay")._ref()
    start = ProbTriple(home=0.48, draw=0.33, away=0.19)
    five = Variable(id="IR01-away", type="lineup_intent", subject=ref.away,
                    favors="away", goals="down", target="formation",
                    hardness="soft", weight=0.7, claim="5백으로 내려앉는다",
                    quote="q", from_rule="IR01-away")
    # ① 경우의 수가 없을 때 — **무승부 쪽**으로만 움직인다(away 아님)
    compare.our_prob(None, start=start, variables=[five], ref=ref, outlook=None)
    assert [(m["id"], m["side"]) for m in compare.MOVES] == \
           [("IR01-away", "draw")], compare.MOVES
    # ② `draw_enough` ×2 가 돌면 그 변수는 **이동 0**(같은 사실이다)
    look = {"states": {ref.away_name: {"state": "draw_enough"}}}
    compare.our_prob(None, start=start, variables=[five], ref=ref, outlook=look)
    ids = [m["id"] for m in compare.MOVES]
    assert ids == [f"경우의수:{ref.away_name}"], ids
    assert compare.MOVES[0]["logodds"] == 0.3, compare.MOVES
    # 🔴 5백 판정은 **열쇠**로 센다 — claim 글자에 팀 이름이 없어도 ×2 가 돈다
    assert compare._low_block(ref.away_name, [five], ref=ref)
    assert not compare._low_block(ref.home_name, [five], ref=ref)


def test_이름표가_모르면_임시_열쇠를_발급한다():
    """🔴🔴 **오픈월드 열쇠 발급**(실사고 2026-10-07) — 미등록 리그 팀도 열쇠를 받는다.

    ⚠️ MLS(시카고–밴쿠버): 봇이 경기 페이지를 쥐고도 `key_of` 가 빈 열쇠를 줘서
       `adapt.ref_of` 가 그 경기를 **거부했다**. 카드는 *"팀 열쇠 임시 발급"* 이라고
       적고 있었지만 **그 발급 코드가 없었다**.
    🔴 발급 번호는 `name:<정규화>` 꼴로 `var/team_keys.json` 에 못 박힌다 — 다음
       실행이 같은 번호를 써야 한다(번호가 돌면 쌓인 카드가 다른 팀 것이 된다).
    돌연변이: `ref_from_row` 를 `key_of` 로 되돌리기.
    """
    import ast as _ast
    from app import teamref
    # ① 발급 — 이름표가 모르는 이름이 **열쇠 꼴**을 받는다
    #    ⚠️ 이 검사는 **못 박은 번호가 남아 있으면** 두 번째 실행부터 `key_of` 가
    #       먼저 찾는다(그것이 설계다 · 번호가 돌지 않게). 🔴 그래서 **매번 다른
    #       이름**으로 센다 — 같은 이름으로 세면 어제 실행이 이 검사를 바꾼다.
    import uuid
    name = f"Zzz {uuid.uuid4().hex[:8]} United"
    got, why = teamref.key_or_issue(name, sport="soccer", league="Test League")
    assert re.fullmatch(r"team:\d{6}", got), (got, why)
    assert "임시 열쇠" in why, why
    # ② **같은 이름은 같은 열쇠**다(두 번 물어도 번호가 안 바뀐다)
    again, _ = teamref.key_or_issue(name, sport="soccer", league="Test League")
    assert again == got
    # ③ 그 뒤에는 `key_of` 도 안다(이름이 이름표에 붙었다)
    said, _ = teamref.key_of(name)
    assert said == got
    # ④ ⚠️ 빈 이름에는 **발급하지 않는다**
    none, why4 = teamref.key_or_issue("  ")
    assert none == "" and "이름이 비었다" in why4
    # ⑤ 🔴 **배선** — `ref_from_row` 가 `key_or_issue` 를 부른다
    tree = _ast.parse((ROOT / "app/matchref.py").read_text(encoding="utf-8"))
    fn = next(n for n in _ast.walk(tree)
              if isinstance(n, _ast.FunctionDef) and n.name == "ref_from_row")
    calls = {c.func.attr for c in _ast.walk(fn)
             if isinstance(c, _ast.Call) and isinstance(c.func, _ast.Attribute)}
    assert "key_or_issue" in calls, "🔴 `ref_from_row` 가 발급을 안 부른다(배선 끊김)"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **사용자 지시 2026-10-07** — IR11 OR · 저득점 조건 · 맞대결 집계 검사
# ══════════════════════════════════════════════════════════════════


def test_IR11_은_8일_3경기로도_발동한다():
    """🔴 ① — 조건이 **OR** 다. 돌연변이: 두 번째 조건 지우기(내가 지웠던 그것).

    실측(미국 · 킥오프 10-07): 09-26·09-30·10-04 → 8일 안에 **이번이 3번째**.
    """
    from app.core.schema import Facts
    from app.core.stages import s5_verify as s5
    import importlib
    ref = importlib.import_module("tests.e2e.test_v6_replay")._ref()
    assert s5.FATIGUE_WINDOW_DAYS == 8 and s5.FATIGUE_WINDOW_GAMES == 3
    day = ref.kickoff_utc.date()
    from datetime import timedelta
    seq = [{"date": str(day - timedelta(days=3))},
           {"date": str(day - timedelta(days=7))},
           {"date": str(day - timedelta(days=40))}]
    got = s5._three_in_window(ref, Facts(recent={str(ref.home): {"sequence": seq}}))
    assert str(ref.home) in got and "3번째" in got[str(ref.home)], got
    # ⚠️ 창 안에 한 경기뿐이면 **안 돈다**(이번이 2번째다)
    few = [{"date": str(day - timedelta(days=3))}]
    assert not s5._three_in_window(ref, Facts(recent={str(ref.home):
                                                      {"sequence": few}}))
    # 🔴 날짜를 못 읽은 줄은 **세지 않는다**
    bad = [{"date": ""}, {"date": "모름"}, {"date": str(day - timedelta(days=2))}]
    assert not s5._three_in_window(ref, Facts(recent={str(ref.home):
                                                      {"sequence": bad}}))
    # 🔴🔴 **배선** — `_ir_fatigue`(IR11)가 그 조건을 부른다
    fn = next(n for n in ast.walk(ast.parse(
        (ROOT / "app/core/stages/s5_verify.py").read_text(encoding="utf-8")))
        if isinstance(n, ast.FunctionDef) and n.name == "_ir_fatigue")
    calls = {c.func.id for c in ast.walk(fn)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert "_three_in_window" in calls, "🔴 IR11 이 8일 3경기 조건을 안 부른다"


def test_저득점_필수형이_무실점_연속과_공격수_결장으로도_걸린다():
    """🔴 ② — 무실점 2연속 **또는** 상대 공격 자원 결장. 돌연변이: 조건 지우기."""
    from app.core.schema import Facts, Variable
    from app.core.stages import s6_hypo
    import importlib
    ref = importlib.import_module("tests.e2e.test_v6_replay")._ref()
    row = {"when_clean_sheet": 2, "when_striker_absent": True}
    # ① 무실점 2연속 — ⚠️ 돌려주는 것은 `(사유들, 변수 id들)` 이다(지시 1)
    said, ids = s6_hypo._low_score_why(
        ref, Facts(recent={str(ref.away): {"streak_clean_sheet": 2}}), [], row)
    assert said and "무실점 2경기" in said[0], said
    # ⚠️ 1경기면 안 걸린다
    assert not s6_hypo._low_score_why(
        ref, Facts(recent={str(ref.away): {"streak_clean_sheet": 1}}), [],
        row)[0]
    # ② 공격 자원 결장(`absence_att` 또는 포지션 FW)
    att = Variable(id="R9", type="absence_att", subject=ref.away, favors="home",
                   goals="down", target="Striker", hardness="hard", weight=3.0,
                   claim="c", quote="q")
    got, ids2 = s6_hypo._low_score_why(ref, Facts(), [att], row)
    assert got and "공격 자원 결장" in got[0], got
    # 🔴 *"최근 득점자"* 는 **확인 못 했다**고 적는다(지어내지 않는다)
    assert "확인 못 했다" in got[0], got[0]
    # 🔴 그 변수를 **driver 로 넘긴다**(지시 1 — 무게가 바닥값이 되지 않게)
    assert ids2 == ["R9"], ids2
    # ⚠️ 수비 결장은 안 걸린다(포지션이 DF 다)
    df = att.model_copy(update={"type": "def_absence", "target": "CB"})
    assert not s6_hypo._low_score_why(
        ref, Facts(player_pos={"CB": "DF"}), [df], row)[0]
    # 🔴🔴 **배선** — `_soccer_forms` 가 그 까닭 함수를 부른다
    fn = next(n for n in ast.walk(ast.parse(
        (ROOT / "app/core/stages/s6_hypo.py").read_text(encoding="utf-8")))
        if isinstance(n, ast.FunctionDef) and n.name == "_soccer_forms")
    calls = {c.func.id for c in ast.walk(fn)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert "_low_score_why" in calls, "🔴 저득점 필수형이 새 조건을 안 부른다"
    # 🔴 표에도 그 조건이 적혀 있다(코드에 수를 박지 않는다)
    import yaml
    box = yaml.safe_load((ROOT / "config/scenario_required.yaml")
                         .read_text(encoding="utf-8"))["soccer_forms"]["저득점"]
    assert int(box["when_clean_sheet"]) == 2 and box["when_striker_absent"]


def test_맞대결_집계가_안_맞으면_그_숫자를_안_쓴다():
    """🔴 ③ — 승+무+패 ≠ 표본이면 변수를 안 만들고 **블록 1**에 적는다.

    실측 2026-10-07(미국–캐나다): `count=10`(창) · `summary=[5,4,4]`(전체 13) —
    두 창이 한 줄에 섞여 있었다. 돌연변이: 검사 제거.
    """
    from app.core.schema import Facts
    from app.core.stages import s5_verify as s5
    from app.core.state import RunState
    import importlib
    ref = importlib.import_module("tests.e2e.test_v6_replay")._ref()
    row = {"id": "S02", "type": "h2h_pattern"}
    st = RunState()
    bad = Facts(h2h={"count": 10, "summary": [5, 4, 4], "all_games": 13})
    got = s5._ir_h2h("S02", row, ref, bad, state=st)
    assert got == [], got
    said = [d for d in st.drops if d.reason.value == "conflict"]
    assert said and "맞대결 집계 불일치" in said[0].detail, st.drops
    # 🔴 합이 맞으면 **그대로 쓴다**
    ok = Facts(h2h={"count": 9, "summary": [6, 3, 0], "window_avg_goals": 3.0})
    said2 = s5._ir_h2h("S02", row, ref, ok, state=RunState())
    assert said2 and said2[0].type == "h2h_pattern"
    # 🔴🔴 **카드도 그 수를 안 적는다** — 보이는 것도 **쓰는 것**이다
    #    ⚠️ 실측 2026-10-07: s5 는 변수를 안 만들었는데 **블록 3 이 계속 찍고**
    #       있었다(*"5승 4무 4패 · 표본 10경기"*).
    from app.core import render
    from app.core.schema import Card
    bad_card = Card(match=ref, facts=bad)
    said3 = render._b3(bad_card)
    assert "5승 4무 4패" not in said3, said3
    assert "집계 불일치" in said3, said3
    good = render._b3(Card(match=ref, facts=ok))
    assert "6승 3무 0패" in good, good


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **등급은 걸 수 있는 줄에만**(사용자 지시 2026-10-07 ①②③)
# ══════════════════════════════════════════════════════════════════


def _judge(board, source: str):
    from app.core.schema import Facts, HypoSet, Scenario
    from app.core.stages import s7_judge
    from app.core.state import RunState
    from datetime import timedelta
    import importlib
    t = importlib.import_module("tests.e2e.test_v6_replay")
    ref = t._ref()
    from app.core.schema import Variable
    rows = [Variable(id=f"V{i}", type="recent_pattern", subject=ref.home,
                     favors=("home" if i % 2 else "away"), goals="none",
                     target="recent", hardness="hard", weight=2.0, claim="c",
                     quote="q") for i in range(4)]
    scen = [Scenario(id="A", outcomes=[(2, 0)], mechanism="m", strength=1.0,
                     driver_vars=["V0"]),
            Scenario(id="B", outcomes=[(1, 1)], mechanism="m", strength=1.0,
                     driver_vars=["V1"]),
            Scenario(id="C", outcomes=[(0, 2)], mechanism="m", strength=1.0,
                     driver_vars=["V2"])]
    return s7_judge.run(ref, Facts(), rows, HypoSet(scenarios=scen),
                        state=RunState(), board=board, board_source=source,
                        now=ref.kickoff_utc - timedelta(hours=2))


def test_보드가_없으면_등급이_전부_보류다():
    """🔴 ② — 기준선에 **등급을 붙이면 계약 실패**다. 돌연변이: 보류 덮기 제거."""
    said = _judge(None, "")
    assert said.board_source == "none", said.board_source
    assert said.evals, "기준선 표는 **참고로** 나와야 한다"
    assert {e.grade for e in said.evals} == {"보류"}, \
        sorted({e.grade for e in said.evals})
    for e in said.evals:
        assert "보드 없음" in e.why, e.why
    # 🔴 결론은 *"보드를 주면 판정"* 으로 끝난다
    assert "보드를 주면 판정" in said.conclusion, said.conclusion
    # ⚠️ 생존·상한은 **그대로 보인다**(참고표로 쓸 수 있게)
    assert any(e.survival > 0 for e in said.evals)


def test_보드가_있으면_그_줄만_등급을_받는다():
    """🔴 ① — 사용자 보드가 **첫 출처**다. 돌연변이: 기준선과 섞기."""
    from app.core import board as _b
    got, _, _ = _b.parse("보드: 승무패 2.0 3.2 3.5 / 언더오버 3.5 1.90")
    said = _judge(got, "user_board")
    assert said.board_source == "user_board"
    kinds = {(e.line.market, e.line.side, e.line.point) for e in said.evals}
    assert ("total", "over", 3.5) in kinds and ("total", "under", 3.5) in kinds
    # 🔴 보드에 없는 기준선(총점 2.5·핸디)은 **표에 없다**
    assert not [e for e in said.evals
                if e.line.market == "total" and e.line.point != 3.5]
    assert "보류" not in {e.grade for e in said.evals}


def test_피드_메인_라인만_평가한다():
    """🔴 ① — 피드 기준선은 **그대로** 쓰고 **메인 라인 하나**만 센다.

    ⚠️ 실측 2026-10-07(MLS): 업체마다 달라 핸디 0.25·0.5·1.0·1.5 가 한꺼번에 왔고
       같은 마켓이 네 줄로 서서 등급이 네 번 나왔다.
    돌연변이: 모든 기준선을 평가 줄로 넣기.
    """
    from app.core import odds
    from app.core.schema import MarketProb, MarketQuote
    q = []
    for book in ("a", "b", "c"):
        q.append(MarketQuote(market="total", side="over", point=3.5, price=1.9,
                             bookmaker=book))
        q.append(MarketQuote(market="total", side="under", point=3.5, price=1.9,
                             bookmaker=book))
    q.append(MarketQuote(market="total", side="over", point=2.5, price=1.5,
                         bookmaker="d"))
    probs = MarketProb(quotes=q)
    assert odds.main_points(probs)["total"] == 3.5
    lines = odds.lines_from(probs)
    said = {(x.market, x.point) for x in lines}
    assert ("total", 3.5) in said and ("total", 2.5) not in said, said
    # 🔴 **우리가 수를 고르지 않는다** — 업체 수를 센 것뿐이다(2.5 가 다수면 2.5 다)
    more = MarketProb(quotes=q + [
        MarketQuote(market="total", side="over", point=2.5, price=1.5,
                    bookmaker=b) for b in ("e", "f", "g", "h")])
    assert odds.main_points(more)["total"] == 2.5


def test_등급_글자에_보류가_있다():
    """🔴 ② — `없음`(문턱 미달)과 `보류`(걸 줄 없음)는 **다른 말**이다."""
    from app.core.schema import Grade
    import typing
    assert "보류" in typing.get_args(Grade)
    assert "없음" in typing.get_args(Grade)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **사용자 지시 2026-10-07(종합 논평)** ① — 보강 갈래의 무게
# ══════════════════════════════════════════════════════════════════


def test_근거_있는_보강_갈래는_바닥값_무게를_받지_않는다():
    """🔴 ① — 발동 조건에 **쓴 변수**가 driver 로 달리고, 무게는 일반 규칙이다.

    실측 2026-10-07(미국–캐나다): 저득점 갈래 `G` 가 무실점 2연속·공격수 결장을
    근거로 생겼는데 `driver_vars=[]` → `strength` 가 **바닥값 0.1** 이었다.
    그래서 언더 3.5 생존이 0.5963 으로 눌렸다(고친 뒤 0.6393).

    ⚠️ `run` 을 부르지 않는다 — 그 길은 **DeepSeek 을 부른다**(계약은 실 API 를
       쓰지 않는다 · 사용자 지시 2026-10-05). 보강 단계와 무게 함수를 직접 본다.
    돌연변이: `_add` 의 `driver_vars=said[:4]` 를 `[]` 로 되돌리면 빨개진다.
    """
    import importlib
    from app.core.schema import Facts, Variable
    from app.core.stages import s6_hypo
    from app.core.state import RunState
    from app.survive import WEIGHT_FLOOR
    ref = importlib.import_module("tests.e2e.test_v6_replay")._ref()
    att = Variable(id="R9", type="absence_att", subject=ref.away,
                   favors="home", goals="down", target="Striker",
                   hardness="hard", weight=3.0, claim="c", quote="q")
    facts = Facts(recent={str(ref.away): {"streak_clean_sheet": 2}})
    got = s6_hypo._soccer_forms(ref, facts, [], [att], state=RunState())
    low = [s for s in got if "저득점" in s.mechanism]
    assert low, "🔴 저득점 보강 갈래가 안 생겼다(앞 조건 계약을 먼저 봐라)"
    one = low[0]
    assert one.driver_vars, "🔴 조건에 쓴 변수를 driver 로 안 달았다"
    assert set(one.driver_vars) <= {"R9", "recent_pattern"}, one.driver_vars
    # 🔴 무게 = 유형별 최댓값 합 → 바닥값(0.1)이 아니다
    said = s6_hypo._strength(one, [att])
    assert said > float(WEIGHT_FLOOR), f"🔴 근거가 있는데 바닥값이다: {said}"
    # 🔴 설명도 그 driver 로 쓴다 — *"근거 변수 없음"* 이 아니다
    assert "근거 변수 없음" not in one.mechanism, one.mechanism
    # ⚠️ 반대로 **근거가 하나도 없으면** 바닥값이고 그렇게 적는다
    bare = s6_hypo._mech("저득점", [(0, 0)], "왜", [], [])
    assert "근거 변수 없음" in bare and "바닥값" in bare, bare
    src = (ROOT / "app/core/stages/s6_hypo.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    # 🔴🔴 **배선 ①** — 네 보강 갈래가 전부 `drivers=` 를 넘긴다
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
              and n.name == "_soccer_forms")
    adds = [c for c in ast.walk(fn) if isinstance(c, ast.Call)
            and isinstance(c.func, ast.Name) and c.func.id == "_add"]
    assert len(adds) >= 4, f"보강 갈래가 {len(adds)}개뿐이다"
    for c in adds:
        assert any(k.arg == "drivers" for k in c.keywords), (
            f"🔴 `drivers=` 없이 보강한다 — 줄 {c.lineno}")
    # 🔴🔴 **배선 ②** — `run` 이 그 무게 함수를 모든 갈래에 먹인다
    runner = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                  and n.name == "run")
    used = {c.func.id for c in ast.walk(runner)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert "_strength" in used, "🔴 `run` 이 무게를 다시 세지 않는다"


def test_논평_본문에_변수_번호가_남지_않는다():
    """🔴 ④ — `text` 에 번호가 섞여도 **카드에는 사람 말만** 남는다.

    실측 2026-10-07(카자흐–페로): DeepSeek 이 *"…운영(var_ids: IR01-away)이라…"*
    를 적어 그 글자가 카드에 그대로 나왔다. 돌연변이: `plain` 의 괄호 지움 제거.
    """
    from app.core.schema import CommentLine, Commentary
    from app.core.stages import s8_comment
    got = Commentary(
        title="저득점", flow="흐름", score_range=["1-0"], lean="",
        reasons=[CommentLine(text="내려앉는 운영(var_ids: IR01-away)이라 좁다",
                             var_ids=["IR01-away"]),
                 CommentLine(text="과부하(var_ids: IR11-home, IR11-away)라 얇다",
                             var_ids=["IR11-home", "IR11-away"]),
                 CommentLine(text="주포 결장(R1) 이 겹친다", var_ids=["R1"])])
    said = s8_comment.plain(got)
    for bad in ("var_ids", "IR01-away", "IR11-home", "(R1)"):
        assert bad not in said, (bad, said)
    assert "내려앉는 운영이라 좁다" in said, said
    # 🔴🔴 **배선** — 카드 렌더러가 그 함수를 쓴다(원문을 그대로 찍지 않는다)
    fn = next(n for n in ast.walk(ast.parse(
        (ROOT / "app/core/render.py").read_text(encoding="utf-8")))
        if isinstance(n, ast.FunctionDef) and n.name == "_comment")
    calls = {c.func.id for c in ast.walk(fn)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert "plain" in calls, "🔴 카드가 논평 원문을 그대로 찍는다"


def test_논평이_LLM_에_사전을_넘기지_않는다():
    """🔴 §9(경계에 dict 금지) — **두 호출 경로 다** `llm.Message` 다.

    ⚠️ 실사고 2026-10-07: 1차는 `Message` 였는데 **재요청 경로**만 사전이어서
    `'dict' object has no attribute 'model_dump'` 로 터졌다(온두라스–자메이카
    재생이 거기서 멈췄다). 돌연변이: 그 자리를 다시 사전으로.
    """
    src = (ROOT / "app/core/stages/s8_comment.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {k.value for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        assert "role" not in keys, (
            f"🔴 사전을 LLM 에 넘긴다 — 줄 {node.lineno}(`llm.Message` 로 싸라)")
    # 🔴 쓰는 자리가 **둘 다** 있다(1차 · 재요청)
    said = sum(1 for n in ast.walk(tree)
               if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Attribute)
               and n.func.attr == "Message")
    assert said >= 3, f"`llm.Message` 호출이 {said}개뿐이다(계통 2곳 + 재요청)"


def test_보드가_없으면_논평도_줄을_가리키지_않는다():
    """🔴 ③ — 등급이 전부 `보류`(보드 없음)면 `lean` 은 **빈 문자열**이다.

    실측 2026-10-07(온두라스–자메이카): 보드가 없어 17줄이 전부 `보류` 인데 논평이
    `handicap Honduras -0.5` 를 기울기로 가리켰다 — **걸 수 없는 줄**이다.
    돌연변이: `check` 의 그 검사 제거.
    """
    from app.core.schema import (BoardLine, Commentary, Judgement,
                                 MarketEval)
    from app.core.stages import s8_comment
    line = BoardLine(market="handicap", side="home", point=-0.5)
    held = Judgement(evals=[MarketEval(line=line, marks={}, survival=0.45,
                                 cap=0.85, grade="보류", why="보드 없음")])
    got = Commentary(title="접전", flow="흐름", score_range=[],
                     reasons=[], lean="handicap home -0.5")
    ok, bad = s8_comment.check(got, shape={"shape": "접전"}, basis=[], scen=[],
                               said=held)
    assert not ok and any("보류" in x for x in bad), bad
    # ⚠️ 빈 문자열이면 통과한다
    ok2, bad2 = s8_comment.check(got.model_copy(update={"lean": ""}),
                                 shape={"shape": "접전"}, basis=[], scen=[],
                                 said=held)
    assert ok2, bad2
    # 🔴 반대로 **사용자 보드**가 있으면 그 줄을 가리켜도 된다
    real = Judgement(evals=[MarketEval(line=line, marks={}, survival=0.45, cap=0.85,
                                 grade="없음", why="")])
    ok3, bad3 = s8_comment.check(got, shape={"shape": "접전"}, basis=[],
                                 scen=[], said=real)
    assert ok3, bad3


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **결장 변수의 팀 귀속**(사용자 지시 2026-10-07 · §결장-귀속-5)
# ══════════════════════════════════════════════════════════════════


def _facts_two_squads(home_names, away_names):
    """🔴 두 팀 **소집 명단**만 든 `Facts` — 명단 대조의 재료다."""
    from app.core.schema import Facts
    return Facts(squad={"team:000164": list(home_names),
                        "team:000047": list(away_names)})


def _ref_mx_cl():
    """🔴 멕시코–칠레 — 라이브 s1 이 적은 값 그대로(실측 2026-10-07)."""
    from datetime import datetime, timezone
    from app.core.schema import MatchRef
    return MatchRef(id="fotmob:6368654", sport="soccer",
                    competition="Friendlies", competition_short="Friendlies",
                    home="team:000164", away="team:000047",
                    home_name="Mexico", away_name="Chile",
                    kickoff_utc=datetime(2026, 10, 7, 2, 30,
                                         tzinfo=timezone.utc),
                    langs=["es", "en"])


def test_결장_선수의_팀을_명단으로_고친다():
    """🔴🔴 §결장-귀속-2 — 모델이 **상대 팀**을 적었으면 명단이 고친다.

    실측 2026-10-07(mx_cl_1): *"Teenage midfielder Gilberto Mora will miss
    **Mexico's** friendly against **Chile**"* 에서 s4 가 `subject=team:000047`
    (칠레)를 냈다 → `favors=home`·득점↑ 로 뒤집혔고 시나리오 B·E 가 *"상대 결장"*
    으로 읽었다. 돌연변이: `_one` 의 명단 대조 호출을 지우면 빨개진다.
    """
    from app.core.stages import s5_verify as V
    ref = _ref_mx_cl()
    facts = _facts_two_squads(["Gilberto Mora", "Santiago Giménez"],
                              ["Ben Brereton", "Marcelo Morales"])
    got, how, why = V.team_of_player("Gilberto Mora", ref, facts)
    assert (got, how) == (ref.home, "roster"), (got, how, why)
    # 🔴 `Mora` 가 `Morales` 에 **글자로** 들어 있다 — 그래도 칠레로 가지 않는다
    assert not V.in_squad("Gilberto Mora", ref.away, facts)
    # 🔴 **방향** — 결장은 상대 쪽이다: 멕시코 결장 → `away`(칠레 쪽)
    assert V.favors_of("def_absence", ref.home, "결장", ref) == "away"
    assert V.favors_of("def_absence", ref.away, "결장", ref) == "home"


def test_이름_꼴이_달라도_같은_선수로_본다():
    """🔴 §결장-귀속-2 — 정규화(합자·악센트)+**성/이름 순서 무관**·머리글자.

    ⚠️ 글자 포함으로 묶지 않는다 — `Mora` ⊄ `Morales` 여야 한다(실측에서 그 하나가
    멕시코 선수를 칠레 명단에 넣었다).
    """
    from app.core.stages.s5_verify import same_person
    same = [("Gilberto Mora", "Gilberto Mora Ortega"),
            ("Gilberto Mora", "Mora, Gilberto"),
            ("G. Mora", "Gilberto Mora"),
            ("Mora", "Gilberto Mora"),
            ("Kim Minjae", "Kim Min-jae"),
            ("Heung-Min Son", "Son Heung-min"),
            ("Ødegaard", "Odegaard")]
    for a, b in same:
        assert same_person(a, b), (a, b)
    other = [("Mora", "Marcelo Morales"), ("Gilberto Mora", "Marcelo Morales"),
             ("Cyle Larin", "Cyle Lewis"), ("G. Mora", "Gonzalo Montiel")]
    for a, b in other:
        assert not same_person(a, b), (a, b)


def test_같은_문장에_상대팀이_있어도_소속_팀으로_귀속된다():
    """🔴🔴 §결장-귀속-5 — 고정물 셋(Mora · 김민재 · Larin).

    세 기사 다 **같은 문장에 두 팀 이름**이 있다 — 그래서 문장만 보면 못 가린다.
    🔴 명단이 가린다. ⚠️ 모델이 어느 쪽을 적었든 결과는 **소속 팀**이다.
    """
    from app.core.schema import Facts, MatchRef
    from app.core.stages import s5_verify as V
    from datetime import datetime, timezone
    rows = [
        # (경기, 선수, 소속, 홈 명단, 원정 명단)
        (_ref_mx_cl(), "Gilberto Mora", "team:000164",
         ["Gilberto Mora"], ["Marcelo Morales"]),
        (MatchRef(id="fotmob:6368651", sport="soccer", competition="Friendlies",
                  competition_short="Friendlies", home="team:000129",
                  away="team:000245", home_name="South Korea",
                  away_name="Uzbekistan",
                  kickoff_utc=datetime(2026, 10, 6, 11, tzinfo=timezone.utc)),
         "Kim Min-jae", "team:000129", ["Kim Min-jae"], ["Eldor Shomurodov"]),
        (MatchRef(id="fotmob:5991876", sport="soccer",
                  competition="Friendlies", competition_short="Friendlies",
                  home="team:000243", away="team:000039", home_name="USA",
                  away_name="Canada",
                  kickoff_utc=datetime(2026, 10, 7, 0, tzinfo=timezone.utc)),
         "Cyle Larin", "team:000039", ["Christian Pulisic"], ["Cyle Larin"]),
    ]
    for ref, who, mine, home_sq, away_sq in rows:
        facts = Facts(squad={ref.home: home_sq, ref.away: away_sq})
        got, how, _why = V.team_of_player(who, ref, facts)
        assert (got, how) == (mine, "roster"), (who, got, how)


def test_명단에도_문장에도_없으면_근거로_쓰지_않는다():
    """🔴 §결장-귀속-2 — `team_unresolved`·`team_ambiguous` 는 **근거 불가**다."""
    from app.core.schema import Doc, Facts
    from app.core.stages import s5_verify as V
    ref = _ref_mx_cl()
    # ① 두 팀 다 없다 + 기사 문장에도 팀이 없다 → 모른다
    bare = Doc(id="D1", url="https://x.test/1", subtask="A-home",
               domain="x.test", lang="en",
               title="Injury update", body="Someone got hurt in training.",
               tier="national")
    got, how, why = V.team_of_player("John Doe", ref, Facts(), bare)
    assert got == "" and how == "unknown", (got, how, why)
    # ② 문장에 **한 팀만** 나오면 그 팀이다
    one = bare.model_copy(update={
        "body": "John Doe trained alone. Mexico will be without him tonight."})
    got2, how2, _ = V.team_of_player("John Doe", ref, Facts(), one)
    assert (got2, how2) == (ref.home, "text"), (got2, how2)
    # ③ 두 팀 명단에 다 있으면 동명이인이다
    both = Facts(squad={ref.home: ["John Doe"], ref.away: ["John Doe"]})
    got3, how3, _ = V.team_of_player("John Doe", ref, both, bare)
    assert got3 == "" and how3 == "ambiguous", (got3, how3)


def test_s2b_2차는_명단_대조를_지난_결장만_넣는다():
    """🔴 §결장-귀속-3 — 대조를 통과하지 못한 결장은 ② 에 넣지 않는다.

    돌연변이: `s2b_base.again` 의 `in_squad` 검사를 지우면 빨개진다.
    """
    fn = next(n for n in ast.walk(ast.parse(
        (ROOT / "app/core/stages/s2b_base.py").read_text(encoding="utf-8")))
        if isinstance(n, ast.FunctionDef) and n.name == "again")
    calls = {c.func.id for c in ast.walk(fn)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert "in_squad" in calls, "🔴 ②(2차)가 명단 대조 없이 결장을 넣는다"


#: 🔴 mx_cl_1 의 **그 문장 그대로**(실측 2026-10-07 · 신화통신 영문)
MORA_LINE = ("Teenage midfielder Gilberto Mora will miss Mexico's friendly "
             "against Chile due to injury, the Mexican Football Federation "
             "(FMF) said on Monday.")


def _doc_mora():
    """🔴 그 기사 한 건 — s5 의 앞 검사(인용·발행일·신원·경기 연결)를 지나게."""
    from datetime import datetime, timezone
    from app.core.schema import Doc
    return Doc(id="A-home-D1", url="https://english.news.cn/20261006/mora",
               domain="english.news.cn", lang="en", subtask="A-home",
               title="Mexico midfielder Mora out of Chile friendly",
               body=(MORA_LINE + " The football friendly against Chile is set "
                     "for Tuesday at Allianz Field. Mora has been a regular "
                     "for Mexico this year."),
               tier="national",
               published_at=datetime(2026, 10, 6, 12, tzinfo=timezone.utc))


def test_s5_가_그_기사의_귀속을_고치고_카드에_적는다():
    """🔴🔴 §결장-귀속-5 고정물 — mx_cl_1 의 Mora 기사 → subject=멕시코.

    모델이 적은 `subject` 는 **칠레**다(실측 s4 출력). s5 가 명단으로 고치고
    `favors` 를 **칠레 쪽**(`away`)으로 다시 센다.
    🔴 돌연변이: `_one` 의 명단 대조(`team_of_player` 호출)를 끄면 빨개진다.
    """
    from app.core.schema import Facts, VarCandidate
    from app.core.state import RunState
    from app.core.stages import s5_verify as V
    ref, doc = _ref_mx_cl(), _doc_mora()
    facts = Facts(squad={ref.home: ["Gilberto Mora", "Santiago Giménez"],
                         ref.away: ["Ben Brereton", "Marcelo Morales"]})
    cand = VarCandidate(subtask="A-home", type="def_absence",
                        subject=ref.away,          # 🔴 **모델이 적은 그대로**(칠레)
                        claim=MORA_LINE, target="Gilberto Mora",
                        match_link="Chile", quote=MORA_LINE, doc_id=doc.id)
    st = RunState(match_key=ref.id)
    got = [v for v in V.run(ref, facts, [doc], [cand], state=st)
           if v.target == "Gilberto Mora"]
    assert got, f"변수가 안 섰다 — 버린 사유 {[d.reason.value for d in st.drops]}"
    one = got[0]
    assert one.subject == ref.home, f"🔴 귀속을 안 고쳤다: {one.subject}"
    assert one.favors == "away", f"🔴 방향을 다시 안 셌다: {one.favors}"
    # 🔴 **카드에 적는다** — 조용히 고치지 않는다(블록 1)
    said = [d for d in st.drops if d.reason.value == "team_reattached"]
    assert said, [d.reason.value for d in st.drops]
    assert "결장 귀속 정정: Gilberto Mora Chile→Mexico" in said[0].detail
    from app.core import render
    from app.core.schema import Card, Funnel
    card = Card(match=ref, facts=facts, variables=got, drops=list(st.drops),
                funnel=Funnel())
    assert "결장 귀속 정정: Gilberto Mora Chile→Mexico" in render.card_text(card)
    # 🔴🔴 **배선** — `_one` 이 그 대조 함수를 부른다
    fn = next(n for n in ast.walk(ast.parse(
        (ROOT / "app/core/stages/s5_verify.py").read_text(encoding="utf-8")))
        if isinstance(n, ast.FunctionDef) and n.name == "_one")
    calls = {c.func.id for c in ast.walk(fn)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
    assert "team_of_player" in calls, "🔴 s5 가 명단 대조를 부르지 않는다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **시나리오 재가중**(사용자 지시 2026-10-07 재가중 ①②)
# ══════════════════════════════════════════════════════════════════


def _hypo(rows):
    """🔴 `(id, type, [(h,a)…], 무게)` 목록 → `HypoSet`."""
    from app.core.schema import HypoSet, Scenario
    return HypoSet(scenarios=[
        Scenario(id=i, type=t, outcomes=list(sc), strength=w,
                 driver_vars=["X1"], added_by="deepseek",
                 mechanism="그래서 그렇게 된다")
        for i, t, sc, w in rows])


def _side_sums(hypo):
    """🔴 결과별 무게 합 — 스코어 단위로 쪼개 센다(`our_prob` 와 같은 규칙)."""
    from app.core.reweight import side_of
    box = {"home": 0.0, "draw": 0.0, "away": 0.0}
    for sc in hypo.scenarios:
        for h, a in sc.outcomes:
            box[side_of(h, a)] += float(sc.strength) / len(sc.outcomes)
    return box


def test_시나리오_무게가_우리_열에_묶인다():
    """🔴🔴 ① — 결과별 합 = OurProb. 같은 결과 안의 비율은 **그대로**.

    실측 2026-10-07(멕시코–칠레): 우리 열 홈 73% 인데 시나리오 무게는 원정·개방
    쪽에 몰려(C 2.4 · A 2.1) 양상·논평·예상 스코어가 **원정 승**을 그렸고
    핸디 Mexico −1.5 생존이 0.1935 였다. 돌연변이: 재가중 호출 제거.
    """
    from app.core import reweight
    from app.core.schema import ProbTriple
    from app.core.state import RunState
    ref = _ref_mx_cl()
    hypo = _hypo([("A", "home_win", [(2, 0)], 1.0),
                  ("B", "home_win", [(2, 1)], 3.0),
                  ("C", "away_win", [(1, 2)], 4.0),
                  ("D", "draw", [(1, 1)], 2.0)])
    ours = ProbTriple(home=0.70, draw=0.20, away=0.10)
    got = reweight.of(hypo, ours, ref=ref, state=RunState())
    box = _side_sums(got)
    tot = sum(box.values())
    for key in ("home", "draw", "away"):
        assert abs(box[key] / tot - getattr(ours, key)) < 1e-6, (key, box, tot)
    # 🔴 **총량은 그대로**(10.0) — 생존은 비율이지만 표가 읽을 수 있어야 한다
    assert abs(tot - 10.0) < 1e-6, tot
    # 🔴 같은 결과 안의 비율은 **그대로** — A:B 가 1:3 이었다
    kept = {s.id: s.strength for s in got.scenarios}
    assert abs(kept["B"] / kept["A"] - 3.0) < 1e-6, kept


def test_갈래가_없는_결과는_보강으로_덮는다():
    """🔴 ① — 우리 열이 확률을 주는데 그 결과 갈래가 없으면 **필수형 스코어로** 넣는다."""
    from app.core import reweight
    from app.core.schema import ProbTriple
    from app.core.state import RunState
    ref = _ref_mx_cl()
    # ⚠️ 무승부 갈래가 **하나도 없다**
    hypo = _hypo([("A", "home_win", [(2, 0)], 2.0),
                  ("B", "away_win", [(0, 1)], 2.0)])
    ours = ProbTriple(home=0.50, draw=0.30, away=0.20)
    got = reweight.of(hypo, ours, ref=ref, state=RunState())
    draws = [s for s in got.scenarios if s.type == "draw"]
    assert draws, "🔴 무승부 결과를 덮지 않았다"
    # 🔴 스코어는 **기존 필수형 표**의 것이다(지어내지 않는다)
    import yaml
    box = yaml.safe_load((ROOT / "config/scenario_required.yaml")
                         .read_text(encoding="utf-8"))["soccer_forms"]
    want = {tuple(int(x) for x in str(s).split("-"))
            for s in box["무승부"]["scores"]}
    assert set(draws[0].outcomes) <= want, (draws[0].outcomes, want)
    assert "근거" in draws[0].mechanism and draws[0].driver_vars == []
    box2 = _side_sums(got)
    tot = sum(box2.values())
    assert abs(box2["draw"] / tot - 0.30) < 1e-6, box2
    # 🔴🔴 **배선** — 파이프라인이 s7 **앞에서** 재가중한다(두 입구 다)
    src = (ROOT / "app/core/pipeline.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for name in ("analyze", "reanalyze"):
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == name)
        order = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)
                 and n.func.attr in ("of", "run")
                 and isinstance(n.func.value, ast.Name)
                 and n.func.value.id in ("_reweight", "s7_judge")]
        calls = [(n.lineno, n.func.value.id) for n in ast.walk(fn)
                 if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)
                 and ((n.func.value.id if isinstance(n.func.value, ast.Name)
                       else "") in ("_reweight", "s7_judge"))]
        got_rw = [ln for ln, who in calls if who == "_reweight"]
        got_s7 = [ln for ln, who in calls if who == "s7_judge"]
        assert got_rw and got_s7, (name, calls)
        assert min(got_rw) < min(got_s7), (
            f"🔴 {name}: 재가중이 s7 **뒤**에 있다(생존이 옛 무게로 선다)")
        assert order  # 🔴 두 호출이 같은 함수 안에 있다


def test_논평_승자가_방향과_어긋나면_잡는다():
    """🔴 ② — 예상 흐름·스코어의 승자 = 방향 판정 팀. 돌연변이: 그 검사 제거.

    실측 2026-10-07(멕시코–칠레): 방향 **Mexico** 인데 흐름이 *"원정팀 Chile가 한
    골 차 승부로 가져간다"* 였고 예상 스코어가 `1-2 · 0-1 · 2-1` 이었다.
    """
    from app.core.schema import Commentary, Judgement
    from app.core.stages import s8_comment
    ref = _ref_mx_cl()
    said = Judgement(direction="방향: **Mexico** (세 열 중 2열이 앞세운다)")
    bad = Commentary(
        title="접전", score_range=["1-2", "0-1", "2-1"],
        flow=("전반에는 홈팀 Mexico가 공을 쥐지만, 후반에 원정팀 Chile가 한 골 차 "
              "승부로 가져간다."), lean="", reasons=[])
    # ⚠️ 스코어 목록 검사와 섞이지 않게 — 네 스코어를 **다 가진** 갈래를 준다
    scen = _hypo([("A", "home_win", [(2, 1)], 1.0),
                  ("B", "away_win", [(1, 2), (0, 1)], 1.0),
                  ("C", "draw", [(1, 1)], 1.0)]).scenarios
    ok, why = s8_comment.check(bad, shape={"shape": "접전"}, basis=[],
                               scen=scen, said=said, ref=ref)
    assert not ok
    assert any("예상 흐름" in x for x in why), why
    assert sum(1 for x in why if "예상 스코어" in x) == 2, why   # 1-2 · 0-1
    # 🔴 방향과 같은 쪽이면 통과한다(무승부는 막지 않는다)
    fine = bad.model_copy(update={
        "score_range": ["2-1", "1-1"],
        "flow": "Mexico가 전반에 앞서고 Chile가 따라붙지만 Mexico가 리드를 지킨다."})
    ok2, why2 = s8_comment.check(fine, shape={"shape": "접전"}, basis=[],
                                 scen=scen, said=said, ref=ref)
    assert ok2, why2
    # ⚠️ 방향이 **반반**이면 제한이 없다
    half = Judgement(direction="방향: **반반** — 앞세운 열이 없다")
    ok3, _ = s8_comment.check(bad, shape={"shape": "접전"}, basis=[],
                              scen=scen, said=half, ref=ref)
    assert ok3
    # 🔴 낱말표는 config 에 있다(코드에 박지 않는다)
    import yaml
    said_words = yaml.safe_load((ROOT / "config/interpret_rules.yaml")
                                .read_text(encoding="utf-8"))
    assert said_words.get("commentary_win_words"), "표가 없다"


def test_s6_입력을_여섯개_80자로_줄였다():
    """🔴 ④ — 상한을 올리지 않고 **입력**을 줄인다(한국–우즈벡 `llm_truncated`)."""
    from app.core.stages import s6_hypo
    assert s6_hypo.BASIS_CAP == 6 and s6_hypo.CLAIM_CUT == 80
    # 🔴 맥락 변수는 **이름만** — `claim` 을 안 보낸다
    fn = next(n for n in ast.walk(ast.parse(
        (ROOT / "app/core/stages/s6_hypo.py").read_text(encoding="utf-8")))
        if isinstance(n, ast.FunctionDef) and n.name == "bare")
    # 🔴 D46 — **독스트링을 뺀 코드만** 본다(설명이 금지어를 말하는 것과 코드가
    #    그것을 부르는 것은 다르다)
    body = [n for n in fn.body
            if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                    and isinstance(n.value.value, str))]
    said = " ".join(ast.dump(n) for n in body)
    assert "claim" not in said, "🔴 맥락 변수에 claim 을 싣는다"
    # ⚠️ LLM 상한은 **그대로다**(§9: 상한을 올려 잘림을 고치지 않는다)
    import yaml
    box = yaml.safe_load((ROOT / "config/llm.yaml").read_text(encoding="utf-8"))
    assert int(box["v6"]["purposes"]["hypo"]["max_tokens"]) <= 8000


def test_결과가_섞인_갈래는_결과별로_쪼갠다():
    """🔴🔴 ① *"각 시나리오 스코어를 결과로 나누고"* — 쪼개야 **합이 맞는다**.

    ⚠️ 실측 2026-10-07: 재가중을 했는데도 결과별 합이 홈 64%(우리 열 73%)였다 —
    `2-2 · 2-3` 처럼 한 갈래가 두 결과를 들면 **갈래 단위 무게 하나**로는 맞출 수가
    없다(하류는 갈래 단위로 센다). 돌연변이: 쪼개기 제거 → 합이 어긋난다.
    """
    from app.core import reweight
    from app.core.schema import ProbTriple
    from app.core.state import RunState
    ref = _ref_mx_cl()
    hypo = _hypo([("A", "open", [(2, 2), (2, 3)], 4.0),      # 무 + 원정
                  ("B", "home_win", [(2, 1)], 2.0),
                  ("C", "open", [(1, 0), (1, 1)], 2.0)])     # 홈 + 무
    ours = ProbTriple(home=0.60, draw=0.25, away=0.15)
    got = reweight.of(hypo, ours, ref=ref, state=RunState())
    # 🔴 쪼갠 갈래는 **결과가 하나**다
    for sc in got.scenarios:
        sides = {reweight.side_of(h, a) for h, a in sc.outcomes}
        assert len(sides) == 1, (sc.id, sc.outcomes)
    # 🔴 **갈래 단위로 세도** 결과별 합이 우리 열과 같다(하류가 그렇게 센다)
    box = {"home": 0.0, "draw": 0.0, "away": 0.0}
    for sc in got.scenarios:
        box[reweight.side_of(*sc.outcomes[0])] += float(sc.strength)
    tot = sum(box.values())
    for key in ("home", "draw", "away"):
        assert abs(box[key] / tot - getattr(ours, key)) < 1e-3, (key, box, tot)
    # 🔴 무거운 쪽이 **본래 이름**을 지킨다(반증 줄이 그 이름을 가리킨다)
    ids = {s.id for s in got.scenarios}
    assert {"A", "B", "C"} <= ids and "A2" in ids, ids
    # 🔴 이야기는 그대로다 — driver 와 mechanism 을 물려받는다
    same = [s for s in got.scenarios if s.id.startswith("A")]
    assert all(s.driver_vars == ["X1"] for s in same), same
    assert all("그래서 그렇게 된다" in s.mechanism for s in same)


def test_쪼개기는_스코어를_바꾸지_않는다():
    """🔴🔴 지시 1(2026-10-07 총평 검열) — **뒤집기·좌우 반전·새 스코어 금지**.

    ⚠️ 쪼개기는 스코어를 **결과로 나누기만** 한다. 보강(결과 덮기)만 새 스코어를
       넣을 수 있고 그것은 `added_by="code"` 로 표시된다.
    돌연변이: 쪼개면서 스코어를 뒤집으면(`(a, h)`) 빨개진다.
    """
    from app.core import reweight
    from app.core.schema import ProbTriple
    from app.core.state import RunState
    ref = _ref_mx_cl()
    hypo = _hypo([("A", "open", [(3, 2), (2, 2)], 1.7),
                  ("B", "away_win", [(1, 3), (2, 3)], 2.4),
                  ("C", "open", [(1, 0), (0, 1)], 1.4),
                  ("D", "home_win", [(2, 0), (2, 1)], 1.4)])
    before = {(h, a) for s in hypo.scenarios for h, a in s.outcomes}
    ours = ProbTriple(home=0.73, draw=0.19, away=0.08)
    got = reweight.of(hypo, ours, ref=ref, state=RunState())
    # 🔴 보강으로 **더해진** 갈래만 새 스코어를 가질 수 있다
    kept = {(h, a) for s in got.scenarios for h, a in s.outcomes
            if "결과 덮기" not in s.mechanism}
    assert kept == before, (f"🔴 스코어가 바뀌었다 — 생긴 것 {sorted(kept - before)} "
                            f"· 사라진 것 {sorted(before - kept)}")


def test_쪼갠_조각의_무게_합이_원래_무게다():
    """🔴 지시 2 — 스코어 무게 = 갈래 무게 ÷ 스코어 수. 조각이 전체를 **들고 가지 않는다**.

    ⚠️ 비례 조정 **전**의 합이다 — 조정은 결과별로 따로 곱한다(그 뒤 합은 달라진다).
    """
    from app.core import reweight
    from app.core.schema import ProbTriple
    from app.core.state import RunState
    ref = _ref_mx_cl()
    hypo = _hypo([("A", "open", [(3, 2), (2, 2)], 1.7),
                  ("B", "home_win", [(2, 0), (2, 1)], 1.4)])
    # 🔴 **비례 조정이 1 이 되는 우리 열**을 준다 — 그러면 조정 전 무게가 그대로다
    #    (A 가 홈 0.85·무 0.85 · B 가 홈 1.4 → 홈 2.25 · 무 0.85 · 합 3.1)
    ours = ProbTriple(home=2.25 / 3.1, draw=0.85 / 3.1, away=0.0)
    got = reweight.of(hypo, ours, ref=ref, state=RunState())
    by_src: dict[str, float] = {}
    for sc in got.scenarios:
        if "결과 덮기" in sc.mechanism:
            continue
        by_src[sc.id[0]] = by_src.get(sc.id[0], 0.0) + float(sc.strength)
    assert abs(by_src["A"] - 1.7) < 1e-3, by_src
    assert abs(by_src["B"] - 1.4) < 1e-3, by_src


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **총평 검열**(사용자 지시 2026-10-07 §4·§5)
# ══════════════════════════════════════════════════════════════════


def _audit_box():
    """🔴 검열 고정물 — 멕시코–칠레의 **실측 사실**(두 팀 보정 득점 0.667)."""
    from app.core.schema import Facts, HypoSet, Judgement, Scenario, Variable
    ref = _ref_mx_cl()
    facts = Facts(recent={
        ref.home: {"matches": 5, "last5": ["W", "L", "D", "D", "L"],
                   "recent_scored_avg": 1.2, "recent_trimmed_avg": 0.667,
                   "sequence": [{"goals_for": 0, "goals_against": 3},
                                {"goals_for": 1, "goals_against": 1}]},
        ref.away: {"matches": 5, "last5": ["L", "L", "W", "L", "L"],
                   "recent_scored_avg": 1.2, "recent_trimmed_avg": 0.667,
                   "sequence": [{"goals_for": 2, "goals_against": 4}]}})
    down = Variable(id="S01-home", type="recent_pattern", subject=ref.home,
                    favors="home", goals="down", goals_against="none",
                    target="recent", hardness="soft", weight=0.7,
                    claim="최근 5경기 W L D D L · 득점 평균 1.2(보정 0.667)",
                    quote="x", from_rule="S01")
    up = Variable(id="S02", type="h2h_pattern", subject=ref.away, favors="away",
                  goals="up", target="h2h", hardness="hard", weight=1.0,
                  claim="맞대결 10경기 3승 3무 4패 · 평균 3.0골", quote="y",
                  from_rule="S02")
    hypo = HypoSet(scenarios=[
        Scenario(id="A", outcomes=[(3, 2)], type="home_win", strength=1.85,
                 driver_vars=["S01-home"], mechanism="주고받는다"),
        Scenario(id="D", outcomes=[(2, 0)], type="home_win", strength=3.05,
                 driver_vars=["S01-home"], mechanism="닫는다"),
        Scenario(id="C", outcomes=[(1, 0)], type="home_win", strength=1.52,
                 driver_vars=["S01-home"], mechanism="한 골")])
    said = Judgement(direction="방향: **Mexico** (세 열 중 2열이 앞세운다)")
    return ref, facts, [down, up], hypo, said


def _comment(**kw):
    from app.core.schema import CommentLine, Commentary
    box = {"title": "접전 — Mexico 쪽에 무게", "flow": "Mexico가 한 골 차로 지킨다",
           "score_range": ["2-0"],
           "reasons": [CommentLine(text="홈팀 득점이 눌려 있다",
                                   var_ids=["S01-home"])],
           "lean": ""}
    box.update(kw)
    return Commentary(**box)


def test_검열_코드검사_여덟칸이_각각_잡는다():
    """🔴🔴 §4-1 (a)~(h) — 위반 고정물 1건·통과 고정물 1건씩.

    🔴 고정물: **지금 멕시코–칠레 논평**(난타전 · 3-2 · S01 을 다득점 근거로) →
       **(d)(e)(g)** 로 잡혀야 한다(지시 §5 원문).
    """
    from app.core.schema import CommentLine
    from app.core.stages import s9_audit
    ref, facts, variables, hypo, said = _audit_box()
    shape = {"shape": "접전", "low": 0.5, "high": 0.2, "one_sided": 0.2,
             "close": 0.8, "top_scores": [["2-0", 3.05]]}

    def run(got, **kw):
        box = {"ref": ref, "facts": facts, "variables": variables,
               "hypo": hypo, "shape": shape, "said": said}
        box.update(kw)
        return s9_audit.code_check(got, **box)

    # ✅ 통과 고정물
    assert run(_comment()) == [], run(_comment())
    # (a) 근거 — 맥락·없는 번호
    bad = run(_comment(reasons=[CommentLine(text="x", var_ids=["R9"])]))
    assert any("근거 불가/없는 변수" in x for x in bad), bad
    # (b) 승자 — 방향(Mexico)과 반대인 스코어
    assert any("예상 스코어" in x for x in run(_comment(score_range=["0-2"])))
    # (c) 양상 — 제목이 shape 를 말하지 않는다
    assert any("title" in x for x in run(_comment(title="난타전 — 골 잔치")))
    # (d) 양상 근거 — 난타전인데 득점 방향 다수결이 `down`
    #     ⚠️ S01-home(down·0.7) + S02(up·**soft 로 센다** 0.7) → 비겼다 → 안 잡힌다.
    #        🔴 그래서 폼 변수 **둘**(양 팀)로 센다 — 실측과 같은 꼴이다.
    two = [*variables, variables[0].model_copy(update={"id": "S01-away"})]
    hot = {**shape, "shape": "난타전"}
    got_d = run(_comment(title="난타전 — 골이 오간다"), variables=two, shape=hot)
    assert any(x.startswith("(d)") for x in got_d), got_d
    # (e) 인용 방향 — `goals=down` 변수로 다득점을 말한다
    bad_e = run(_comment(reasons=[CommentLine(text="서로를 열어두고 주고받는다",
                                              var_ids=["S01-home"])]))
    assert any(x.startswith("(e)") for x in bad_e), bad_e
    # (f) 숫자 — 카드에 없는 수
    bad_f = run(_comment(reasons=[CommentLine(text="최근 47경기 흐름이다",
                                              var_ids=["S01-home"])]))
    assert any(x.startswith("(f)") for x in bad_f), bad_f
    # (g) 예상 스코어 — 무게 상위 5개 밖
    bad_g = run(_comment(score_range=["5-4"]))
    assert any(x.startswith("(g)") for x in bad_g), bad_g
    # (h) 금지어
    bad_h = run(_comment(flow="기대값이 좋아 보인다"))
    assert any("금지어" in x for x in bad_h), bad_h


def test_지금_멕시코_칠레_논평이_검열에_걸린다():
    """🔴🔴 §5 고정물 — *"난타전·3-2·S01 을 다득점 근거로"* → (d)(e)(g) 위반."""
    from app.core.schema import CommentLine
    from app.core.stages import s9_audit
    ref, facts, variables, hypo, said = _audit_box()
    two = [*variables, variables[0].model_copy(update={"id": "S01-away"})]
    shape = {"shape": "난타전", "low": 0.36, "high": 0.45, "one_sided": 0.23,
             "close": 0.77, "top_scores": [["2-0", 3.05]]}
    got = _comment(
        title="난타전 — 골이 주고받아지는 양상",
        score_range=["3-2", "2-2", "2-1"],
        flow="전반부터 양팀이 주고받으며 골이 오가고 홈팀이 리드를 지킨다",
        reasons=[CommentLine(text="양팀은 서로를 열어두고 부딪혀 왔다",
                             var_ids=["S01-home"])])
    bad = s9_audit.code_check(got, ref=ref, facts=facts, variables=two,
                              hypo=hypo, shape=shape, said=said)
    kinds = {x[:3] for x in bad}
    assert "(d)" in kinds, bad
    assert "(e)" in kinds, bad
    assert "(g)" in kinds, bad


def test_검열자는_작성자와_다른_모델이다():
    """🔴🔴 §4-2 — *"작성자와 검열자를 같은 모델로 두지 않는다"*. 돌연변이: 같게."""
    from app.core.stages import s9_audit
    assert s9_audit.AUDITOR != s9_audit.WRITER, (s9_audit.AUDITOR,
                                                 s9_audit.WRITER)
    # 🔴 코드가 **실제로** 그 둘을 쓴다 — 글자만 다른 상수가 아니다
    audit_src = (ROOT / "app/core/stages/s9_audit.py").read_text(encoding="utf-8")
    write_src = (ROOT / "app/core/stages/s8_comment.py").read_text(
        encoding="utf-8")
    assert "provider=AUDITOR" in audit_src, "🔴 검열이 그 상수를 안 쓴다"
    assert f'provider="{s9_audit.WRITER}"' in write_src, "🔴 작성자가 다른 모델이다"
    # 🔴 검열 호출 상한 — 출력 600 토큰(§4-4)
    import yaml
    box = yaml.safe_load((ROOT / "config/llm.yaml").read_text(encoding="utf-8"))
    assert int(box["v6"]["purposes"]["audit"]["max_tokens"]) == 600


def test_검열이_파이프라인에_이어져_있다():
    """🔴 §4 — 논평 **바로 뒤·렌더 전**이다. 돌연변이: 검열 단계 건너뛰기 → 빨강."""
    src = (ROOT / "app/core/pipeline.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for name in ("analyze", "reanalyze"):
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == name)
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)
                 and isinstance(n.func.value, ast.Name)]
        who = {f"{c.func.value.id}.{c.func.attr}" for c in calls}
        assert "s9_audit.run" in who, f"🔴 {name} 가 검열을 안 부른다: {sorted(who)}"
        # 🔴 **작성자를 직접 부르지 않는다** — 검열을 지나지 않는 길이 생긴다
        assert "s8_comment.run" not in who, (
            f"🔴 {name} 가 작성자를 직접 부른다(검열을 건너뛴다)")
    # 🔴 카드에 검열 결과 칸이 있다(§4-3: 과정은 `/디버그` 만)
    from app.core.schema import Card
    assert "comment_audit" in Card.model_fields
    assert "comment_violations" in Card.model_fields


def test_폼_변수에_득점_방향이_붙는다():
    """🔴 §3 — 기준(실측)의 팀당 몫과 ±0.2 로 `goals`·`goals_against`.

    돌연변이: 그 계산을 끄면(`none` 고정) 빨개진다.
    """
    from app import rules
    from app.core.stages.s5_verify import _form_goal_dirs, GOAL_GAP
    assert GOAL_GAP == 0.2
    share = rules.goal_share("national_friendly")
    assert share and 1.0 < share < 1.6, share      # 🔴 실측값(2.5324 ÷ 2)
    box = {"sequence": [{"goals_for": 0, "goals_against": 3},
                        {"goals_for": 1, "goals_against": 1}]}
    got, ga, why = _form_goal_dirs(box, 0.667, "national_friendly")
    assert got == "down", (got, why)               # 0.667 ≤ 1.266 − 0.2
    assert ga == "up", (ga, why)                   # 실점 평균 2.0 ≥ 1.266 + 0.2
    assert "기준 팀당" in why
    # ⚠️ 기준이 없는 종목은 **매기지 않는다**
    assert _form_goal_dirs(box, 0.667, "baseball") == ("none", "none", "")
    # 🔴 표는 실측 도구가 쓴다 — 측정일·표본이 함께 있다
    import yaml
    said = yaml.safe_load((ROOT / "config/goal_baselines.yaml")
                          .read_text(encoding="utf-8"))
    assert said.get("measured_at")
    for kind in ("national_friendly", "national_official", "league"):
        row = said["kinds"][kind]
        assert int(row["n"]) > 1000 and 1.5 < float(row["goals_per_match"]) < 4


def test_득점_방향이_반대인_driver_를_뺀다():
    """🔴 §3 마지막 — 3골 이상 갈래의 `goals=down` driver 를 뺀다(다 빠지면 바닥값)."""
    from app.core.schema import Scenario
    from app.core.stages import s6_hypo
    from app.core.state import RunState
    from app.survive import WEIGHT_FLOOR
    _ref, _facts, variables, _hypo, _said = _audit_box()
    down = variables[0]                      # S01-home · goals=down
    hot = Scenario(id="A", outcomes=[(3, 2)], type="home_win",
                   driver_vars=["S01-home"], mechanism="주고받는다")
    cold = Scenario(id="B", outcomes=[(1, 0)], type="home_win",
                   driver_vars=["S01-home"], mechanism="한 골")
    got = s6_hypo._goal_fit([hot, cold], [down], state=RunState())
    assert got[0].driver_vars == [], "🔴 3골 갈래에서 `down` driver 를 안 뺐다"
    assert got[1].driver_vars == ["S01-home"], "🔴 2골 갈래는 그대로여야 한다"
    assert s6_hypo._strength(got[0], [down]) == float(WEIGHT_FLOOR)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **사용자 지시 2026-10-09** — 대전–전북에서 나온 셋
# ══════════════════════════════════════════════════════════════════


def test_맞대결_집계가_안_맞으면_목록에서_다시_센다():
    """🔴 ① — 돌연변이: 불일치면 버린다(종전 동작).

    > 맞대결 집계 불일치일 때 **버리지 말고**, 경기 페이지의 맞대결 경기 목록
    > (날짜·스코어)을 **직접 세어 다시 만든다.**

    실측 2026-10-09(대전–전북): fotmob `summary` 는 전체 25경기의 `[3, 9, 13]`
    인데 `count` 는 창 10경기였다 — 종전 코드는 변수를 통째로 버렸다.
    """
    from app import league
    rows = [
        {"date": "2026-07-21", "home": "Jeonbuk", "away": "Daejeon",
         "home_score": 0, "away_score": 0},
        {"date": "2026-03-21", "home": "Daejeon", "away": "Jeonbuk",
         "home_score": 0, "away_score": 1},
        {"date": "2025-11-08", "home": "Jeonbuk", "away": "Daejeon",
         "home_score": 3, "away_score": 1},
        {"date": "2024-10-19", "home": "Jeonbuk", "away": "Daejeon",
         "home_score": 0, "away_score": 2},
    ]
    assert league.h2h_tally(rows, "Daejeon") == (1, 1, 2)
    # 🔴 **반대쪽 기준도 뒤집혀야** 한다 — 한쪽으로 박아 두면 홈/원정이 바뀔 때 거짓
    assert league.h2h_tally(rows, "Jeonbuk") == (2, 1, 1)
    # ⚠️ 스코어가 없으면 **센 척하지 않는다**
    assert league.h2h_tally([{"date": "2026-01-01", "home": "A", "away": "B"}],
                            "A") is None
    # 🔴 s5 가 그 길로 가나 — 버리는 코드가 남아 있으면 이 글자가 없다
    import pathlib
    src = pathlib.Path("app/core/stages/s5_verify.py").read_text(encoding="utf-8")
    assert "league.h2h_tally(" in src, "s5 가 다시 세지 않는다"
    assert 'facts.h2h["recounted"]' in src, "다시 센 수를 카드에 안 넘긴다"


def test_올_시즌_맞대결을_따로_센다():
    """🔴 ① 둘째 줄 — 돌연변이: 창 안에서만 고른다 · 시즌 경계를 코드에 박는다."""
    from app import league
    rows = [
        {"date": "2026-07-21", "home": "Jeonbuk", "away": "Daejeon",
         "home_score": 0, "away_score": 0, "score": "0-0"},
        {"date": "2026-03-21", "home": "Daejeon", "away": "Jeonbuk",
         "home_score": 0, "away_score": 1, "score": "0-1"},
        {"date": "2025-11-08", "home": "Jeonbuk", "away": "Daejeon",
         "home_score": 3, "away_score": 1, "score": "3-1"},
    ]
    got, year = league.h2h_season(rows, when="2026-10-09", comp="KL1")
    assert year == 2026 and len(got) == 2, (year, got)
    # 🔴 **오래된 것부터** — 사용자가 적은 순서(0-1 · 0-0)와 같아야 한다
    assert [m["score"] for m in got] == ["0-1", "0-0"], got
    # 🔴 시즌 경계는 **표**가 든다 — 유럽은 8월 시작이라 2026-03 은 **지난 시즌**이다
    assert league.season_cut_month("KL1") == 1
    assert league.season_cut_month("PL") == 8
    # 🔴 8월 경계에서는 2026-07·2026-03 이 **지난 시즌**이다 — 역년과 갈린다
    euro, yr = league.h2h_season(rows, when="2026-10-09", comp="PL")
    assert yr == 2026 and euro == [], (yr, euro)
    past, yr2 = league.h2h_season(rows, when="2026-03-01", comp="PL")
    assert yr2 == 2025 and [m["score"] for m in past] == ["3-1", "0-1", "0-0"], past


def test_조가_하나인_리그도_순위표를_읽는다():
    """🔴 ② — 돌연변이: `data.tables` 만 본다(종전 동작 · K리그1 이 매번 빠졌다).

    실측 2026-10-09: K리그1 표 페이지는 `table[0].data` **자체**가 표이고
    `data.tables` 는 `None` 이다. 종전 `_tables` 는 **0** 을 돌려줬다.
    """
    from app.collect import fotmob
    one = {"props": {"pageProps": {"table": [{"data": {
        "leagueName": "K League 1",
        "legend": [{"title": "Championship playoff",
                    "indices": [0, 1, 2, 3, 4, 5]}],
        "table": {"all": [
            {"name": "Daejeon Hana Citizen", "idx": 6, "played": 30,
             "wins": 10, "draws": 10, "losses": 10, "pts": 40,
             "scoresStr": "46-37", "goalConDiff": 9},
            {"name": "Jeonbuk Hyundai Motors FC", "idx": 4, "played": 30,
             "wins": 11, "draws": 11, "losses": 8, "pts": 44,
             "scoresStr": "38-28", "goalConDiff": 10}]}}}]}}}
    assert len(fotmob._tables(one)) == 1, "조가 하나인 표를 못 읽는다"
    got = fotmob.group_table(one, ["Daejeon Hana Citizen",
                                   "Jeonbuk Hyundai Motors FC"])
    assert got.get("group") == "K League 1", got
    assert len(got.get("rows") or []) == 2, got
    # 🔴 **파이널A 컷**이 글자 그대로 와야 한다(우리가 뜻을 지어내지 않는다)
    assert got["zones"].get("Championship playoff") == 6, got["zones"]
    # ⚠️ 여러 조 꼴도 **그대로** 읽혀야 한다(고치면서 깨면 네이션스리그가 죽는다)
    many = {"props": {"pageProps": {"table": [{"data": {"tables": [
        {"leagueName": "Grp. 3", "table": {"all": [
            {"name": "A", "idx": 1, "pts": 3}]}}]}}]}}}
    assert len(fotmob._tables(many)) == 1, "여러 조 꼴이 깨졌다"


def test_football_data_없는_리그는_fotmob_결과로_Elo_를_굴린다():
    """🔴 ③ — 돌연변이: K리그1·J1 을 football-data 로만 찾는다(404 라 기준이 없다).

    🔴 리그 번호는 **받아서 확인한 값**이다 — 추측하면 다른 리그가 온다(실사고
       2026-10-09: J1 을 `9134` 로 적었는데 그 번호는 **NWSL** 이었다).
    """
    from app.collect import leagueelo
    box = leagueelo.fotmob_table()
    comps = dict(box.get("competitions") or {})
    assert {"KL1", "J1"} <= set(comps), comps
    assert int(comps["KL1"]["id"]) == 9080 and comps["KL1"]["slug"] == "k-league-1"
    assert int(comps["J1"]["id"]) == 223 and comps["J1"]["slug"] == "j-league"
    # 🔴 `refresh` 가 그 통로를 **부르나** — 안 이으면 없는 코드다(CLAUDE.md #2)
    import pathlib
    src = pathlib.Path("app/collect/leagueelo.py").read_text(encoding="utf-8")
    assert "fetch_fotmob(net, comp" in src, "refresh 가 fotmob 통로를 안 부른다"
    # 🔴 **꼴을 맞춰** 돌려줘야 `_rows`·`compute` 가 분기 없이 읽는다(#1 사본 금지)
    said = leagueelo._fotmob_matches({"props": {"pageProps": {"fixtures": {
        "allMatches": [
            {"id": "1", "home": {"name": "A"}, "away": {"name": "B"},
             "status": {"finished": True, "scoreStr": "2 - 1",
                        "utcTime": "2026-03-01T05:00:00Z"}},
            {"id": "2", "home": {"name": "C"}, "away": {"name": "D"},
             "status": {"finished": False, "utcTime": "2026-10-09T05:00:00Z"}},
        ]}}}})
    assert len(said) == 1 and said[0]["score"]["fullTime"] == {"home": 2, "away": 1}
    assert leagueelo._rows(said), "football-data 꼴로 안 맞춰 `_rows` 가 못 읽는다"


def test_fotmob_로_받은_리그에_계수가_있고_출처를_속이지_않는다():
    """🔴 ③ — 계수가 없으면 Elo 가 있어도 기준이 안 선다. 돌연변이: 출처 글자 박기."""
    from app.core import base
    for kind in ("league:KL1", "league:J1"):
        got, why = base.triple_of(kind, 0.0)
        assert got is not None, f"{kind} 계수가 없다 — `--league` 적합을 돌려라"
        assert abs(got.home + got.draw + got.away - 1.0) < 1e-6, got
    import pathlib
    import yaml
    box = yaml.safe_load(
        pathlib.Path("config/base_model.yaml").read_text(encoding="utf-8"))
    for kind in ("league:KL1", "league:J1"):
        m = (box.get("models") or {})[kind]
        # 🔴 **통로를 속이지 않는다** — fotmob 으로 받았으면 그렇게 적힌다
        assert str(m.get("source", "")).startswith("fotmob "), m.get("source")
        # ⚠️ 모형이 자료보다 못하면 **쓸 수 없다**(yaml 머리글)
        assert float(m["logloss"]) < float(m["logloss_base"]), m
    # 🔴 s2b 도 출처를 **파일에서 읽어야** 한다(박아 두면 거짓이 찍힌다)
    src = pathlib.Path("app/core/stages/s2b_base.py").read_text(encoding="utf-8")
    assert 'f"football-data {comp} 자체 Elo"' not in src, "출처가 박혀 있다"
    assert '.get("via")' in src, "통로를 등급 파일에서 안 읽는다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **사용자 지시 2026-10-09(2차)** — 대전–전북 카드에서 나온 넷
# ══════════════════════════════════════════════════════════════════


def _kl1_table() -> dict:
    """🔴 실측 2026-10-09 K리그1 표(31라운드 전) — 승점·일정 그대로."""
    names = [("FC Seoul", 62), ("Ulsan HD FC", 47), ("Jeju SK", 46),
             ("Jeonbuk Hyundai Motors FC", 44), ("Gangwon FC", 43),
             ("Daejeon Hana Citizen", 40), ("Pohang Steelers", 40),
             ("Incheon United", 39), ("FC Anyang", 38),
             ("Gimcheon Sangmu", 33), ("Bucheon FC 1995", 32),
             ("Gwangju FC", 15)]
    rows = [{"rank": i, "name": n, "points": p, "played": 30,
             "wins": 0, "draws": 0, "losses": 0,
             "goals_for": 0, "goals_against": 0, "goal_diff": 0,
             "zone": ("Championship playoff" if i <= 6
                      else "Relegation qualification")}
            for i, (n, p) in enumerate(names, start=1)]
    fx = [{"round": "31", "home": "Daejeon Hana Citizen",
           "away": "Jeonbuk Hyundai Motors FC", "finished": False},
          {"round": "31", "home": "Incheon United",
           "away": "Pohang Steelers", "finished": False},
          {"round": "31", "home": "Gangwon FC",
           "away": "Bucheon FC 1995", "finished": False},
          {"round": "31", "home": "FC Seoul", "away": "Jeju SK",
           "finished": False},
          {"round": "31", "home": "Gimcheon Sangmu", "away": "FC Anyang",
           "finished": False},
          {"round": "31", "home": "Gwangju FC", "away": "Ulsan HD FC",
           "finished": False}]
    return {"group": "K League 1", "rows": rows, "fixtures": fx,
            "zones": {"Championship playoff": 6,
                      "Relegation qualification": 12}}


def test_다른_경기_칸은_그_경기_팀_이름으로_적는다():
    """🔴 ① — 돌연변이: 둘째 칸을 우리 팀 이름으로 푼다(종전 동작).

    실사고 2026-10-09: 카드가 *"대전 승 | 대전 승"* 으로 찍었다 — 둘째 칸은
    **인천–포항**의 말이어야 한다.
    """
    from app import rules
    from app.core import standing as st
    box = _kl1_table()
    order, _, _, _ = rules.tiebreak("K-League 1")
    cells = st.grid(box, home="Daejeon Hana Citizen",
                    away="Jeonbuk Hyundai Motors FC", order=order,
                    others=[("Incheon United", "Pohang Steelers")])
    assert len(cells) == 9, len(cells)
    one = cells[0]["others"][0]
    assert one["home"] == "Incheon United" and one["away"] == "Pohang Steelers"
    # 🔴 우리 팀 이름이 **둘째 칸에 섞이면** 안 된다
    assert "Daejeon" not in one["home"] and "Daejeon" not in one["away"]


def test_순위에_닿는_경기를_승점차로_고르고_뺀_것을_적는다():
    """🔴 ① — 돌연변이: 첫 경기 하나만 쓴다 · 뺀 경기를 말없이 버린다.

    🔴 사용자가 지목한 둘(인천–포항·강원–부천)이 **승점 차가 가장 작은 둘**이다:
       포항 40(차 0) · 강원 43(차 1) · 제주 46·안양 38(차 2) · 울산 47(차 3).
    """
    from app.core import standing as st
    box = _kl1_table()
    keep, drop = st.touching(box, home="Daejeon Hana Citizen",
                             away="Jeonbuk Hyundai Motors FC",
                             round_no="31", cap=2)
    got = {f"{r['home']}–{r['away']}" for r in keep}
    assert got == {"Incheon United–Pohang Steelers",
                   "Gangwon FC–Bucheon FC 1995"}, got
    assert [r["gap"] for r in keep] == [0, 1], keep
    # 🔴 **뺀 것을 돌려줘야** 카드가 이름으로 적을 수 있다(#3 조용한 0 금지)
    assert len(drop) == 3, drop
    assert all(r.get("gap") is not None for r in drop), drop
    # ⚠️ 우리 경기는 다른 경기에 **섞이지 않는다**
    assert not any("Daejeon" in f"{r['home']}{r['away']}" for r in keep + drop)


def test_분할_리그는_컷_안밖으로_상태를_센다():
    """🔴 ① — 돌연변이: 순위 쌍으로 센다(종전 동작 · 거짓 `must_win`).

    실측 2026-10-09: 대전은 어떤 결과든 5·6위로 **컷 안이 안 바뀌는데** 순위
    쌍으로 세면 `5위 ≠ 6위` 라 `must_win` 이 찍혔다.
    """
    from app import rules
    from app.core import standing as st
    split = rules.split_rule("K-League 1")
    assert split, "competition_rules 에 K리그1 분할 규칙이 없다"
    box = _kl1_table()
    cut = st.cut_rank(box["zones"],
                      titles=[str(x) for x in split["cut_zones"]])
    assert cut == 6, cut
    assert int(split["cut_rank_fallback"]) == 6, split
    order, _, _, _ = rules.tiebreak("K-League 1")
    cells = st.grid(box, home="Daejeon Hana Citizen",
                    away="Jeonbuk Hyundai Motors FC", order=order,
                    others=[("Incheon United", "Pohang Steelers"),
                            ("Gangwon FC", "Bucheon FC 1995")])
    assert len(cells) == 27, len(cells)
    # 🔴 전북은 44점으로 **어떤 결과든 컷 안**이다
    jb, why = st.state_of(cells, "Jeonbuk Hyundai Motors FC", is_home=False,
                          zones=box["zones"], cut=cut)
    assert jb == "nothing" and "컷" in why, (jb, why)
    # 🔴 사유 글이 **순위가 아니라 컷**을 말해야 한다
    dj, why2 = st.state_of(cells, "Daejeon Hana Citizen", is_home=True,
                           zones=box["zones"], cut=cut)
    assert "컷" in why2 and "위" not in why2.replace("컷", ""), why2
    assert dj in st.STATES


def test_확정_여부를_도달_가능_최대_승점으로_센다():
    """🔴 ① 마지막 줄 — 돌연변이: 현재 승점으로만 센다."""
    from app.core import standing as st
    box = _kl1_table()
    # 🔴 대전 40점 + 남은 2라운드(이 경기 뺀) × 3 = 46
    assert st.reachable(box, team="Daejeon Hana Citizen", rounds_left=2) == 46
    assert st.reachable(box, team="Jeonbuk Hyundai Motors FC",
                        rounds_left=2) == 50
    # ⚠️ 모르는 팀은 **0** 이다(지어내지 않는다)
    assert st.reachable(box, team="없는팀", rounds_left=2) == 0


def test_올시즌_맞대결이_저득점이면_필수형이_걸린다():
    """🔴 ② — 돌연변이: 올 시즌 맞대결을 안 본다(종전 동작).

    실측 2026-10-09: 올 시즌 `0-1`·`0-0` = 2경기 **총 1골**(경기당 0.5)인데
    저득점 갈래가 **하나도 없었다**(창 10경기 평균 2.1골이 덮었다).
    """
    import yaml
    import pathlib
    box = yaml.safe_load(
        pathlib.Path("config/scenario_required.yaml").read_text(encoding="utf-8"))
    row = dict((box.get("soccer_forms") or {}).get("저득점") or {})
    assert int(row["when_season_h2h_games"]) == 2, row
    assert float(row["when_season_h2h_goals_per_game"]) == 1.0, row
    assert "0-0" in row["scores"] and "1-0" in row["scores"], row
    # 🔴 코드가 그 칸을 **읽나** — 안 이으면 없는 규칙이다(CLAUDE.md #2)
    src = pathlib.Path("app/core/stages/s6_hypo.py").read_text(encoding="utf-8")
    assert "when_season_h2h_games" in src, "s6 가 그 조건을 안 읽는다"
    assert 'get("season_matches")' in src, "s6 가 올 시즌 맞대결을 안 본다"


def test_총점_줄은_등급_보류다():
    """🔴 ② 둘째 줄 — 돌연변이: 총점에 등급을 준다.

    > 결과 대조 지시 1번(총골 기준 층)을 이어서 진행 — **그 전까지 총점 줄은
    > 등급 보류 유지.**

    ⚠️ 그 지시 문서는 저장소에 **없다** — 실행 가능한 절만 넣었다(v4 §11-1).
    """
    import pathlib
    src = pathlib.Path("app/survive.py").read_text(encoding="utf-8")
    assert "총점 줄 등급 보류" in src, "총점 보류가 코드에 없다"
    # 🔴 **글자가 아니라 마켓 객체**로 센다(표기가 바뀌면 조용히 빠진다)
    assert 'getattr(mkt, "market_type", "") == "total"' in src, src[:0]


def test_맞대결은_한_번만_팀_이름을_붙여_적는다():
    """🔴 ④ — 돌연변이: 기준 없이 숫자만 적는다(한 카드에 두 숫자가 보였다)."""
    import pathlib
    s5 = pathlib.Path("app/core/stages/s5_verify.py").read_text(encoding="utf-8")
    assert 'f"맞대결 {n}경기 {ref.home_name} {w}승 {d}무 {lose}패"' in s5, \
        "s5 의 맞대결 claim 에 팀 이름이 없다"
    assert '(상대 {lose}승)' in s5, "상대 승수를 괄호에 안 적는다"
    rd = pathlib.Path("app/core/render.py").read_text(encoding="utf-8")
    assert "(상대 {again['l']}승)" in rd or "상대 {again['l']}승" in rd, \
        "카드가 상대 승수를 안 적는다"


def test_총평_검열이_맞대결_해석_방향을_잡는다():
    """🔴🔴 ④ 둘째 줄 — 돌연변이: 검사를 빼면 *"격차가 좁다"* 가 통과한다.

    > 한쪽 승이 다른 쪽의 **2배 이상**이면 "대등·좁다" 류 표현은 **위반**.

    실측 2026-10-09: 대전 **1승 4무 5패**(상대 5배)인데 총평이 *"좀처럼 크게
    벌어지지 않아 양 팀 간 격차가 좁게 유지돼 왔다"* 고 적었다.
    """
    from datetime import datetime, timezone

    from app.core.schema import CommentLine, Commentary, Facts, MatchRef
    from app.core.stages.s9_audit import h2h_direction_check
    ref = MatchRef(id="x", sport="soccer", competition="K-League 1",
                   competition_short="K-League 1",
                   kickoff_utc=datetime(2026, 10, 9, 5, 0, tzinfo=timezone.utc),
                   home="team:000316", away="team:000582",
                   home_name="Daejeon Hana Citizen",
                   away_name="Jeonbuk Hyundai Motors FC")
    facts = Facts(h2h={"recounted": {"w": 1, "d": 4, "l": 5, "n": 10,
                                     "basis": "Daejeon Hana Citizen"}})
    bad_text = "맞대결에서 좀처럼 크게 벌어지지 않아 양 팀 간 격차가 좁게 유지돼 왔다"
    got = Commentary(title="접전",
                     reasons=[CommentLine(text=bad_text, var_ids=[])],
                     flow="", score_range=[])
    bad = h2h_direction_check(got, ref=ref, facts=facts)
    # 🔴 번호가 **(m)** 이다 — 2026-10-09(3차) §4 가 (i)~(l) 을 가져갔다
    assert bad and "(m)" in bad[0], bad
    assert "기울었다" in bad[0], bad
    # 🔴 **기울지 않았으면 안 잡는다**(없는 위반을 만들지 않는다)
    even = Facts(h2h={"recounted": {"w": 4, "d": 2, "l": 4, "n": 10,
                                    "basis": "Daejeon Hana Citizen"}})
    assert h2h_direction_check(got, ref=ref, facts=even) == []
    # ⚠️ 전적을 못 세면 **검사하지 않는다**
    assert h2h_direction_check(got, ref=ref, facts=Facts()) == []
    # 🔴 코드 검사 묶음이 이것을 **부르나**(안 이으면 없는 검사다)
    import pathlib
    src = pathlib.Path("app/core/stages/s9_audit.py").read_text(encoding="utf-8")
    assert "bad += h2h_direction_check(" in src, "code_check 가 안 부른다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **대회 식별 한 곳** — 사용자 지시 2026-10-09(4차) §1·§2·§3·§4
# ══════════════════════════════════════════════════════════════════


def test_여러_출처_표기가_같은_키로_모인다():
    """🔴🔴 §4 — `jpn.1`·`kor.1`·이름·코드·fotmob id → **같은 키**.

    🔴 돌연변이: `competitions.yaml` 에서 `espn_slugs` 를 지우면 `jpn.1` 이
       키를 잃고 — 그것이 실사고 2026-10-09(가시마–감바)의 모습이다.
    """
    from app.core.competition import key_of
    want = {
        "league:J1": ["jpn.1", "J1 League", "J. League", "j리그1"],
        "league:KL1": ["kor.1", "K League 1", "K-League 1", "k리그1"],
        "league:PPL": ["por.1", "Liga Portugal", "Primeira Liga"],
        "league:PL": ["eng.1", "Premier League"],
        "league:BSA": ["bra.1", "Campeonato Brasileiro Série A"],
    }
    for key, says in want.items():
        for said in says:
            got, why = key_of(competition=said)
            assert got == key, (said, got, key, why)
    # 🔴 fotmob 리그 id 와 football-data 코드도 **같은 키**를 가리킨다
    assert key_of(league_id=223)[0] == "league:J1"
    assert key_of(league_id=9080)[0] == "league:KL1"
    assert key_of(code="PPL")[0] == "league:PPL"
    # 🔴 **이탈리아 세리에A 와 브라질이 갈린다**(표기가 겹친다)
    assert key_of(league_id=55)[0] == "league:SA"
    assert key_of(league_id=268)[0] == "league:BSA"
    # ⚠️ 슬러그는 **전체 일치**다 — `jpn.10` 을 `jpn.1` 로 읽지 않는다
    assert key_of(competition="jpn.10")[0] == "", key_of(competition="jpn.10")


def test_모르는_표기면_키가_없고_사유에_받은_글자가_있다():
    """🔴 §2 — 돌연변이: 모르는 표기를 `league:{받은 글자}` 로 **그냥 쓴다**.

    🔴 그 돌연변이가 바로 종전 동작이다 — `league:jpn.1` 이 만들어져 기준·홈
       이점·리그 평균이 **조용히** 비었다.
    """
    from app.core.competition import UNKNOWN_HEAD, key_of
    got, why = key_of(competition="zzz.9")
    assert got == "", got
    assert UNKNOWN_HEAD in why and "zzz.9" in why, why
    # ⚠️ 빈 입력도 **키가 없다**(없는 것을 키로 만들지 않는다)
    assert key_of()[0] == ""


def test_확인_못_한_표기는_알아보되_그_사실을_적는다():
    """🔴 §1 — `kor.1` 은 ESPN 세 경로가 503 이라 **확인 못 했다**.

    🔴 그래도 **알아본다**(지시가 *"kor.1 포함"*). ⚠️ 사유에 그 사실이 남아야
       사람이 확인된 표기와 **구분**할 수 있다.
    """
    from app.core.competition import key_of
    got, why = key_of(competition="kor.1")
    assert got == "league:KL1", (got, why)
    assert "확인 못 한 표기" in why, why
    # 🔴 확인된 표기에는 그 말이 **없다**
    assert "확인 못 한 표기" not in key_of(competition="jpn.1")[1]


def test_판정점이_하나다():
    """🔴🔴 §1 — 돌연변이: 두 번째 판정점을 되살린다.

    🔴 종전에는 `s5_verify.league_code` 가 `league_elo.yaml` 이름표를 **따로**
       읽었다 — 한 곳만 고치면 다른 곳이 조용히 틀린다.
    """
    import pathlib
    src = pathlib.Path("app/core/stages/s5_verify.py").read_text(encoding="utf-8")
    assert "def league_code" not in src, "두 번째 판정점이 되살아났다"
    assert "competition as _comp" in src and "_comp.kind_of(" in src, src[:0]
    # 🔴 `comp_kind` 는 **그 함수만** 부른다(이름표를 다시 읽지 않는다)
    assert "league_elo.yaml" not in src.split("def comp_kind")[1][:1200]


def test_대회_미식별이면_등급이_전부_보류다():
    """🔴🔴 §2 — 돌연변이: 미식별인데 등급을 준다."""
    import pathlib
    src = pathlib.Path("app/core/stages/s7_judge.py").read_text(encoding="utf-8")
    assert "대회 미식별 — 등급 전부 보류" in src, "s7 이 보류시키지 않는다"
    # 🔴 `enough=False` 로 **같은 길**을 탄다(대입·방향은 그대로 낸다)
    said = src.split("대회를 알아보지 못했다")[0][-700:]
    assert "enough = False" in said, said[-200:]
    # 🔴 운영자 알림이 **이어져** 있다
    assert "_tell_operator(ref)" in src
    from app import auditlog
    assert hasattr(auditlog, "unknown_competition")
    assert hasattr(auditlog, "unknown_competitions")


def test_빈_카드를_감지해_머리에_찍는다():
    """🔴🔴 §3 — 돌연변이: 조용히 내보낸다(가시마–감바가 그랬다).

    > 변수 2개 이하 + 기준 없음 + 폼·XI·순위 중 둘 이상 없음.
    """
    from app.core import render
    from app.core.schema import BaseProb, Card, Facts, MatchRef
    from datetime import datetime, timezone
    ref = MatchRef(id="x", sport="soccer", competition="zzz.9",
                   competition_short="zzz.9",
                   kickoff_utc=datetime(2026, 10, 9, 10, tzinfo=timezone.utc),
                   home="team:000316", away="team:000582",
                   home_name="A", away_name="B")
    thin = Card(match=ref, facts=Facts(), variables=[],
                base_prob=BaseProb(why="기준 없음"))
    said, why = render.thin_card(thin)
    assert said and "변수 0개" in why, (said, why)
    lines = render.warn_lines(thin)
    assert any("자료 부족 카드 — 판단에 쓰지 말 것" in x for x in lines), lines
    assert any("대회를 알아보지 못했다" in x for x in lines), lines
    # 🔴 **카드 머리와 블록 1 둘 다**에 들어간다
    body = render.card_text(thin)
    assert body.count("자료 부족 카드") >= 2, body.count("자료 부족 카드")
    assert body.count("대회를 알아보지 못했다") >= 2
    # ⚠️ 변수가 셋이면 **얇지 않다**(흔한 일을 경고로 만들지 않는다)
    from app.core.schema import Variable
    v = Variable(id="S03", type="home_field", subject="team:000316",
                 favors="home", goals="none", target="home_field",
                 hardness="soft", weight=1.0, claim="홈", quote="홈",
                 doc_ids=[], from_rule="S03")
    fat = thin.model_copy(update={"variables": [v, v, v]})
    assert render.thin_card(fat)[0] is False


def test_같은_경기가_다른_출처로_와도_하나로_묶인다():
    """🔴🔴 §1 — 돌연변이: 경기 id 로만 묶는다(출처가 다르면 id 가 다르다).

    실사고 2026-10-09(가시마–감바): fotmob `J. League` · ESPN `jpn.1` 로 **같은
    경기**가 둘 왔고 `ambiguous` 로 멈췄다 — 카드가 아예 안 나왔다.
    """
    from app.findgame import _same_match
    a = {"home": "Kashima Antlers", "away": "Gamba Osaka",
         "league": "J. League", "starts_utc": "2026-10-09T10:00:00+00:00"}
    b = {"home": "Kashima Antlers", "away": "Gamba Osaka",
         "league": "jpn.1", "starts_utc": "2026-10-09T10:00:00+00:00"}
    assert _same_match([a], b) is a, "같은 경기를 못 묶는다"
    # 🔴 홈·원정이 **뒤집혀도** 같은 경기다(출처가 순서를 바꿔 준다)
    flip = {**b, "home": "Gamba Osaka", "away": "Kashima Antlers"}
    assert _same_match([a], flip) is a
    # ⚠️ **다른 경기는 묶지 않는다** — 시각이 다르면 다른 경기다
    later = {**b, "starts_utc": "2026-10-17T06:00:00+00:00"}
    assert _same_match([a], later) is None
    other = {**b, "away": "V-Varen Nagasaki"}
    assert _same_match([a], other) is None
    # ⚠️ 시각을 못 재면 **묶지 않는다**(모르는 것을 같다고 하지 않는다 · #3)
    blind = {k: v for k, v in b.items() if k != "starts_utc"}
    assert _same_match([a], blind) is None


def test_DB_에_같은_경기가_두_줄이면_하나를_고른다():
    """🔴🔴 §1 — 돌연변이: `pick_one` 을 빼면 `ambiguous` 로 카드가 안 나온다.

    실사고 2026-10-09(가시마–감바): `games` 표에 `fotmob:5803602`(J. League) ·
    `espn:401877610`(jpn.1)이 **같은 경기**로 있었다(유일 제약 `(sport, ext_id)`
    가 출처 차이를 못 막는다).
    """
    from app.core.competition import pick_one, source_rank
    rows = [
        {"ext_id": "espn:401877610", "league": "jpn.1",
         "home": "Kashima Antlers", "away": "Gamba Osaka",
         "starts_utc": "2026-10-09 10:00:00+00:00"},
        {"ext_id": "fotmob:5803602", "league": "J. League",
         "home": "Kashima Antlers", "away": "Gamba Osaka",
         "starts_utc": "2026-10-09 10:00:00+00:00"},
    ]
    kept, notes = pick_one(rows)
    assert len(kept) == 1, kept
    # 🔴 **출처 우선순위**가 고른다 — 표가 `fotmob` 을 먼저로 적었다
    assert kept[0]["ext_id"] == "fotmob:5803602", kept
    assert notes and "같은 경기를 묶었다" in notes[0], notes
    assert source_rank("fotmob:1") < source_rank("espn:1")
    # ⚠️ **다른 경기는 묶지 않는다**(§17-g-3 을 어기지 않는다)
    two = [rows[0], {**rows[1], "starts_utc": "2026-10-17 06:00:00+00:00"}]
    assert len(pick_one(two)[0]) == 2
    # 🔴 **대회를 알아보는 줄이 먼저다** — 순위보다 그것이 앞선다
    mixed = [{"ext_id": "fotmob:1", "league": "zzz.9",
              "home": "A", "away": "B", "starts_utc": "2026-10-09 10:00:00+00:00"},
             {"ext_id": "espn:2", "league": "jpn.1",
              "home": "A", "away": "B", "starts_utc": "2026-10-09 10:00:00+00:00"}]
    assert pick_one(mixed)[0][0]["ext_id"] == "espn:2", pick_one(mixed)[0]
    # 🔴 `resolve` 가 그것을 **부르나**(안 이으면 없는 코드다 · CLAUDE.md #2)
    import pathlib
    src = pathlib.Path("app/resolve.py").read_text(encoding="utf-8")
    assert "_comp.pick_one(list(found.games))" in src


def test_구역은_구간_전체로_센다():
    """🔴🔴 돌연변이: 마지막 순위만으로 센다(종전 동작 — 6위가 `Relegation` 이었다).

    실측 2026-10-09 J1 legend: `AFC Champions League Elite indices [0,1]`(1~2위) ·
    `Relegation indices [17,18,19]`(18~20위). 🔴 `cut_lines` 는 구간의 **마지막
    순위만** 들어서 `rank <= 20` 인 모든 순위가 강등으로 찍혔다 — 경우의 수 표
    27줄이 그 거짓을 반복했다.
    """
    from app.collect.fotmob import cut_lines, zone_bands
    from app.core.standing import zone_of
    tb = {"legend": [
        {"title": "AFC Champions League Elite", "indices": [0, 1]},
        {"title": "Relegation", "indices": [17, 18, 19]}]}
    bands = zone_bands(tb)
    assert bands == {"AFC Champions League Elite": [1, 2],
                     "Relegation": [18, 20]}, bands
    # 🔴 `cut_lines` 는 **그대로 둔다**(`stakes` 가 경계 순위로 쓴다)
    assert cut_lines(tb) == {"AFC Champions League Elite": 2, "Relegation": 20}
    zones = cut_lines(tb)
    # 🔴 구간으로 세면 6·8·17위는 **구역이 없다**
    for rank in (3, 6, 8, 17):
        assert zone_of(rank, zones, bands) == "", rank
        # ⚠️ 종전 방식은 그 순위를 강등으로 말했다 — 돌연변이의 모습이다
        assert zone_of(rank, zones) == "Relegation", rank
    assert zone_of(1, zones, bands) == "AFC Champions League Elite"
    assert zone_of(18, zones, bands) == "Relegation"
    assert zone_of(20, zones, bands) == "Relegation"
    # 🔴 `grid` 가 **구간을 쓰나** — 안 쓰면 표가 다시 거짓이 된다
    import pathlib
    src = pathlib.Path("app/core/standing.py").read_text(encoding="utf-8")
    assert 'standings.get("zone_bands")' in src
    assert "zone_of(int(r.get(\"rank\") or 0),\n" in src or \
        "zones, bands)" in src, src[:0]
    fm = pathlib.Path("app/collect/fotmob.py").read_text(encoding="utf-8")
    assert '"zone_bands": zone_bands(tb)' in fm, "group_table 이 구간을 안 싣는다"


def test_블록3_은_허용_목록으로만_순위를_적는다():
    """🔴🔴 돌연변이: 거부 목록으로 되돌린다 — 새 칸이 생기면 또 샌다.

    실측: 2026-10-07 MLS 85,682자 → `group` 을 뺐다. 2026-10-09 가시마–감바
    3,983자 → 팀별 줄이 그 목록에 없었다. 🔴 그래서 **허용 목록**이다.
    """
    from app.core import render
    from app.core.schema import BaseProb, Card, Facts, MatchRef
    from datetime import datetime, timezone
    ref = MatchRef(id="x", sport="soccer", competition="J. League",
                   competition_short="J. League",
                   kickoff_utc=datetime(2026, 10, 9, 10, tzinfo=timezone.utc),
                   home="team:000316", away="team:000582",
                   home_name="A", away_name="B")
    # 🔴 **모르는 칸은 안 나간다** — 팀별 줄이 통째로 들어와도
    noisy = {"team": "B", "table": "J. League", "rank": 16, "played": 8,
             "wins": 1, "draws": 3, "losses": 4, "points": 6,
             "goals_for": 8, "goals_against": 14}
    card = Card(match=ref, facts=Facts(standings=noisy),
                base_prob=BaseProb(why="x"))
    said = render._standings_line(card)
    assert said == "", said
    assert "'rank'" not in render.card_text(card), "dict 원문이 카드에 나갔다"
    # 🔴 **홈 이점은 나간다**(블록 3 이 적을 칸이다)
    ha = Card(match=ref, base_prob=BaseProb(why="x"),
              facts=Facts(standings={"home_advantage": {
                  "win_pct_delta": -6.1, "home_games": 180,
                  "away_games": 180}}))
    got = render._standings_line(ha)
    assert "홈 이점(쪼갠 표)" in got and "-6.1%p" in got, got
    # ⚠️ 조 순위표만 있으면 **어디 있는지** 가리킨다(조용히 빠지지 않는다)
    grp = Card(match=ref, base_prob=BaseProb(why="x"),
               facts=Facts(standings={"group": {"rows": [{"name": "A"}]}}))
    assert "블록 3b" in render._standings_line(grp)


def test_남은_경기_줄이_조_전체와_팀별을_가른다():
    """🔴 돌연변이: 조 전체 수만 적는다 — *"남은 경기 300개"* 로 읽힌다."""
    import pathlib
    src = pathlib.Path("app/core/render.py").read_text(encoding="utf-8")
    assert "조 전체 남은 경기" in src, "조 전체임을 안 밝힌다"
    assert "이 두 팀 남은 라운드" in src, "팀별 라운드를 안 적는다"
