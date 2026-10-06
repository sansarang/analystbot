"""🔴🔴 **네 층 확률 + 시장 비교 계약** — 지시서 2026-10-06(재작성) §9.

> 번호는 기존 계약 번호 다음부터. **전부 행동 검사.** 테스트는 고정물·카세트만 —
> 실피드·실데이터·실모델 금지.

⚠️ 여기 있는 검사는 **돌연변이로 확인했다** — 지시서 §9 가 돌연변이를 짝으로 적었다.
"""
from __future__ import annotations

import ast
import pathlib

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


def test_세_열_규칙은_등급을_올리지_못한다():
    """🔴 §7 금지 — 돌연변이: **세 열 일치면 한 단계 올리기** → 음수가 나와 빨개진다."""
    from app.core import compare
    for verdict in ("세 열 일치", "우리만 반대", "시장만 반대", "세 열 불일치",
                    "우리만 튄다", "시장만 튄다", "기준 없음", "시장 없음"):
        step, why = compare.grade_step(verdict, found_new=False)
        assert step >= 0, (verdict, step, why)
    assert compare.grade_step("세 열 일치", found_new=False)[0] == 0
    assert compare.grade_step("우리만 반대", found_new=False)[0] >= 3
    assert compare.grade_step("시장만 반대", found_new=False)[0] == 1
    # 🔴 새 사실을 찾았으면 **내리지 않는다**(재판정 결과를 쓴다)
    assert compare.grade_step("시장만 반대", found_new=True)[0] == 0


def test_등급_내림이_사다리_아래로만_간다():
    """🔴 §7 — `_lower` 가 **아래로만** 옮긴다(실제 판정 묶음으로 센다)."""
    from app.core import pipeline
    from app.core.schema import BoardLine, Judgement, MarketEval
    from app.core.state import RunState
    evals = [MarketEval(line=BoardLine(market="win", side="home"),
                        marks={}, survival=0.9, cap=1.0, grade="낸다")]
    said = Judgement(evals=evals, direction="d", conclusion="c")
    got = pipeline._lower(said, {"compare": "시장만 반대"}, state=RunState())
    assert got.evals[0].grade == "소액", got.evals[0].grade
    none = pipeline._lower(said, {"compare": "우리만 반대"}, state=RunState())
    assert none.evals[0].grade == "없음"
    keep = pipeline._lower(said, {"compare": "세 열 일치"}, state=RunState())
    assert keep.evals[0].grade == "낸다"


def test_우리_확률은_시나리오_무게_비율이다():
    """🔴 §5 — 새 수식을 만들지 않는다. 돌연변이: 단순 개수 비율."""
    from app.core import compare
    from app.core.schema import HypoSet, Scenario
    rows = [Scenario(id="A", outcomes=[(2, 0)], mechanism="m", strength=0.8),
            Scenario(id="B", outcomes=[(1, 1)], mechanism="m", strength=0.4),
            Scenario(id="C", outcomes=[(0, 1)], mechanism="m", strength=0.4)]
    got, why = compare.our_prob(HypoSet(scenarios=rows))
    assert got is not None
    assert round(got.home, 3) == 0.5 and round(got.draw, 3) == 0.25
    assert "무게" in why
    # 🔴🔴 **섞인 스코어는 나눠 센다**(2026-10-06(5차) ① 실측) — 종전에는 그 무게가
    #    통째로 사라져 무승부가 0% 로 나왔다. `2-2`·`2-3` 은 무/원정 반반이다.
    mixed = [Scenario(id="A", outcomes=[(2, 2), (2, 3)], mechanism="m",
                      strength=0.8)]
    said, why2 = compare.our_prob(HypoSet(scenarios=mixed))
    assert said is not None, why2
    assert round(said.draw, 3) == 0.5 and round(said.away, 3) == 0.5, said
    # ⚠️ 스코어가 아예 없으면 **그때는** 못 센다
    empty = [Scenario(id="A", outcomes=[], mechanism="m", strength=0.8)]
    none, why3 = compare.our_prob(HypoSet(scenarios=empty))
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
    from app.core.stages.s5_verify import league_code
    assert league_code("Premier League") == "PL"
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
