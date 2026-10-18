# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **F7(2026-10-11) — 옛 논평 체계 계약을 걷었다**
# ══════════════════════════════════════════════════════════════════
#
#  걷은 것: `test_논평_본문에_변수_번호가_남지_않는다` · `test_보드가_없으면_논평도_줄을_가리키지_않는다` · `test_논평_승자가_방향과_어긋나면_잡는다` · `test_검열_코드검사_여덟칸이_각각_잡는다` · `test_지금_멕시코_칠레_논평이_검열에_걸린다` · `test_검열이_파이프라인에_이어져_있다` · `test_핵심선수와_총골이_작성자_입력과_카드에_이어진다` · `test_총평_템플릿이_나열이_아니라_문장이다`
#
#  🔴 F7 이 글을 **한 편**으로 합쳤다 — 지금 글은 `s9_say` 하나가 쓰고(작성 1회),
#     검열은 그 안의 `check`(코드 · (q)~(v))가 한다. 새 계약은
#     `tests/contracts/test_v8_f7_one_say.py` 가 든다(**R9**).
#  ⚠️ 조용히 지우지 않는다 — 어떤 보장이 어디로 갔는지 여기 적어 둔다.

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


def test_Elo_We_가_지시서_수와_같다() -> None:
    """🔴🔴 **Elo 를 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*.

    ⚠️ 이 시험(test_Elo_We_가_지시서_수와_같다)이 지키던 것은 **기준 확률(Elo → 승·무·패)** 경로다.
    🔴 **확률은 이미 그 수를 안 보고 있었다** — 승무패는 `flat_prob`
       (1/3 균등 + 변수)이 내고 `probmodel.run` 은 `floor` 를 안 읽는다.
       쓰이던 곳은 카드의 **기준 열**과 **방향 판정**뿐이었고 둘 다 표시인데,
       `eloratings.net/World.tsv` 를 **매 실행** 받고 있었다.
    🔴 그래서 지웠고, 이 시험은 *"되살아나지 않는다"* 를 지킨다.
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    #  ① Elo 모듈 넷이 **없다**
    for rel in ("app/collect/elo.py", "app/collect/leagueelo.py",
                "app/core/domesticelo.py"):
        assert not (root / rel).exists(), f"🔴 `{rel}`(Elo)가 되살아났다"
    #  ② 기준 확률 함수가 **없다**
    from app.core import base as _b
    for one in ("we", "triple_of", "triple_from", "base_prob"):
        assert not hasattr(_b, one), f"🔴 `core.base.{one}`(Elo)가 되살아났다"
    from app.core.stages import s2b_base as _s2b
    for one in ("_base", "continental_elo", "league_level"):
        assert not hasattr(_s2b, one), f"🔴 `s2b_base.{one}`(Elo)가 되살아났다"
    #  ③ ② 는 **남아 있다** — 오늘 XI 가 평소보다 약/강한가는 Elo 를 안 쓴다
    for one in ("strength_of", "fill_values", "adjust"):
        assert hasattr(_b, one), f"🔴 `core.base.{one}`(선수 전력)이 같이 지워졌다"
    #  ④ 기준은 **늘 비어 있고 사유가 붙는다**(#3 조용한 0 금지)
    said = (root / "app/core/stages/s2b_base.py").read_text(encoding="utf-8")
    assert "BaseProb(probs=None" in said, "🔴 기준을 빈 값으로 안 낸다"
    assert "기준(Elo)은 지웠다" in said, "🔴 그 사실을 사유에 안 적는다"


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


def test_다른_대회_유형_계수를_빌려_쓰지_않는다() -> None:
    """🔴🔴 **Elo 를 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*.

    ⚠️ 이 시험(test_다른_대회_유형_계수를_빌려_쓰지_않는다)이 지키던 것은 **기준 확률(Elo → 승·무·패)** 경로다.
    🔴 **확률은 이미 그 수를 안 보고 있었다** — 승무패는 `flat_prob`
       (1/3 균등 + 변수)이 내고 `probmodel.run` 은 `floor` 를 안 읽는다.
       쓰이던 곳은 카드의 **기준 열**과 **방향 판정**뿐이었고 둘 다 표시인데,
       `eloratings.net/World.tsv` 를 **매 실행** 받고 있었다.
    🔴 그래서 지웠고, 이 시험은 *"되살아나지 않는다"* 를 지킨다.
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    #  ① Elo 모듈 넷이 **없다**
    for rel in ("app/collect/elo.py", "app/collect/leagueelo.py",
                "app/core/domesticelo.py"):
        assert not (root / rel).exists(), f"🔴 `{rel}`(Elo)가 되살아났다"
    #  ② 기준 확률 함수가 **없다**
    from app.core import base as _b
    for one in ("we", "triple_of", "triple_from", "base_prob"):
        assert not hasattr(_b, one), f"🔴 `core.base.{one}`(Elo)가 되살아났다"
    from app.core.stages import s2b_base as _s2b
    for one in ("_base", "continental_elo", "league_level"):
        assert not hasattr(_s2b, one), f"🔴 `s2b_base.{one}`(Elo)가 되살아났다"
    #  ③ ② 는 **남아 있다** — 오늘 XI 가 평소보다 약/강한가는 Elo 를 안 쓴다
    for one in ("strength_of", "fill_values", "adjust"):
        assert hasattr(_b, one), f"🔴 `core.base.{one}`(선수 전력)이 같이 지워졌다"
    #  ④ 기준은 **늘 비어 있고 사유가 붙는다**(#3 조용한 0 금지)
    said = (root / "app/core/stages/s2b_base.py").read_text(encoding="utf-8")
    assert "BaseProb(probs=None" in said, "🔴 기준을 빈 값으로 안 낸다"
    assert "기준(Elo)은 지웠다" in said, "🔴 그 사실을 사유에 안 적는다"


def test_중립_경기에는_기준_확률을_내지_않는다() -> None:
    """🔴🔴 **Elo 를 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*.

    ⚠️ 이 시험(test_중립_경기에는_기준_확률을_내지_않는다)이 지키던 것은 **기준 확률(Elo → 승·무·패)** 경로다.
    🔴 **확률은 이미 그 수를 안 보고 있었다** — 승무패는 `flat_prob`
       (1/3 균등 + 변수)이 내고 `probmodel.run` 은 `floor` 를 안 읽는다.
       쓰이던 곳은 카드의 **기준 열**과 **방향 판정**뿐이었고 둘 다 표시인데,
       `eloratings.net/World.tsv` 를 **매 실행** 받고 있었다.
    🔴 그래서 지웠고, 이 시험은 *"되살아나지 않는다"* 를 지킨다.
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    #  ① Elo 모듈 넷이 **없다**
    for rel in ("app/collect/elo.py", "app/collect/leagueelo.py",
                "app/core/domesticelo.py"):
        assert not (root / rel).exists(), f"🔴 `{rel}`(Elo)가 되살아났다"
    #  ② 기준 확률 함수가 **없다**
    from app.core import base as _b
    for one in ("we", "triple_of", "triple_from", "base_prob"):
        assert not hasattr(_b, one), f"🔴 `core.base.{one}`(Elo)가 되살아났다"
    from app.core.stages import s2b_base as _s2b
    for one in ("_base", "continental_elo", "league_level"):
        assert not hasattr(_s2b, one), f"🔴 `s2b_base.{one}`(Elo)가 되살아났다"
    #  ③ ② 는 **남아 있다** — 오늘 XI 가 평소보다 약/강한가는 Elo 를 안 쓴다
    for one in ("strength_of", "fill_values", "adjust"):
        assert hasattr(_b, one), f"🔴 `core.base.{one}`(선수 전력)이 같이 지워졌다"
    #  ④ 기준은 **늘 비어 있고 사유가 붙는다**(#3 조용한 0 금지)
    said = (root / "app/core/stages/s2b_base.py").read_text(encoding="utf-8")
    assert "BaseProb(probs=None" in said, "🔴 기준을 빈 값으로 안 낸다"
    assert "기준(Elo)은 지웠다" in said, "🔴 그 사실을 사유에 안 적는다"


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


# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_시장_확률이_등급_계산에_직접_안_들어간다`

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
    """🔴🔴 **원칙 수정**(2026-10-06(8차) ①) + **F4**(2026-10-11) — 시장 열은
    등급·확률을 **어떤 경우에도** 바꾸지 않는다.

    🔴 F4 가 세 열 규칙(`compare.grade_step`)을 **통째로 지웠다** — 표의 절반이
       시장이었기 때문이다. 등급을 내리는 자리는 ⑫ 검증 하나다.
    돌연변이: `grade_step` 을 되살려 파이프라인에 잇기.
    """
    import inspect

    from app.core import compare, pipeline
    assert not hasattr(compare, "grade_step"), (
        "🔴 세 열 등급 규칙이 돌아왔다 — 시장이 등급에 닿는 길이다(F4)")
    # 🔴 **D46** — 독스트링·주석은 뺀다(문서가 그 이름을 *설명하는* 것과 코드가
    #    그것을 *부르는* 것은 다르다 · CLAUDE.md 7). AST 로 **호출**만 센다.
    tree = ast.parse(inspect.getsource(pipeline))
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    called |= {n.func.id for n in ast.walk(tree)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "grade_step" not in called, "🔴 파이프라인이 그 규칙을 부른다"


def test_등급_내림이_사다리_아래로만_간다():
    """🔴 F4 — `_grade_by_check` 가 **아래로만** 옮긴다(⑫ 검증이 입력이다)."""
    from app.core import pipeline
    from app.core.schema import BoardLine, Judgement, MarketEval
    from app.core.state import RunState
    evals = [MarketEval(line=BoardLine(market="win", side="home"),
                        marks={}, survival=0.9, cap=1.0, grade="낸다")]
    said = Judgement(evals=evals, direction="d", conclusion="c")
    # 🔴 **시장이 달라도 그대로**다 — 시장은 이제 등급 경로에 아예 없다
    got = pipeline._grade_by_check(said, {"compare": "시장이 다르다"},
                                   state=RunState())
    assert got.evals[0].grade == "낸다", got.evals[0].grade
    # 🔴 ⑫ 검증이 `없음` 이라고 하면 **없음**까지 내려간다
    none = pipeline._grade_by_check(
        said, {"check": {"grade": {"none": True, "why": ["(c) 반대 2건"]}}},
        state=RunState())
    assert none.evals[0].grade == "없음"
    # 🔴 한 칸 내림
    one = pipeline._grade_by_check(
        said, {"check": {"grade": {"steps": 1, "why": ["(c) hard·강 1건"]}}},
        state=RunState())
    assert one.evals[0].grade == "소액"
    # 🔴 조정이 없으면 **그대로**(올리는 길은 없다)
    keep = pipeline._grade_by_check(said, {"check": {"grade": {}}},
                                    state=RunState())
    assert keep.evals[0].grade == "낸다"


# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_시나리오_비율은_무게로_세고_섞인_스코어를_나눈다`

# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_축구_시나리오에_무승부_갈래가_보강된다`

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


def test_리그_Elo_는_우리가_계산하고_clubelo_는_dead_다() -> None:
    """🔴🔴 **Elo 를 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*.

    ⚠️ 이 시험(test_리그_Elo_는_우리가_계산하고_clubelo_는_dead_다)이 지키던 것은 **기준 확률(Elo → 승·무·패)** 경로다.
    🔴 **확률은 이미 그 수를 안 보고 있었다** — 승무패는 `flat_prob`
       (1/3 균등 + 변수)이 내고 `probmodel.run` 은 `floor` 를 안 읽는다.
       쓰이던 곳은 카드의 **기준 열**과 **방향 판정**뿐이었고 둘 다 표시인데,
       `eloratings.net/World.tsv` 를 **매 실행** 받고 있었다.
    🔴 그래서 지웠고, 이 시험은 *"되살아나지 않는다"* 를 지킨다.
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    #  ① Elo 모듈 넷이 **없다**
    for rel in ("app/collect/elo.py", "app/collect/leagueelo.py",
                "app/core/domesticelo.py"):
        assert not (root / rel).exists(), f"🔴 `{rel}`(Elo)가 되살아났다"
    #  ② 기준 확률 함수가 **없다**
    from app.core import base as _b
    for one in ("we", "triple_of", "triple_from", "base_prob"):
        assert not hasattr(_b, one), f"🔴 `core.base.{one}`(Elo)가 되살아났다"
    from app.core.stages import s2b_base as _s2b
    for one in ("_base", "continental_elo", "league_level"):
        assert not hasattr(_s2b, one), f"🔴 `s2b_base.{one}`(Elo)가 되살아났다"
    #  ③ ② 는 **남아 있다** — 오늘 XI 가 평소보다 약/강한가는 Elo 를 안 쓴다
    for one in ("strength_of", "fill_values", "adjust"):
        assert hasattr(_b, one), f"🔴 `core.base.{one}`(선수 전력)이 같이 지워졌다"
    #  ④ 기준은 **늘 비어 있고 사유가 붙는다**(#3 조용한 0 금지)
    said = (root / "app/core/stages/s2b_base.py").read_text(encoding="utf-8")
    assert "BaseProb(probs=None" in said, "🔴 기준을 빈 값으로 안 낸다"
    assert "기준(Elo)은 지웠다" in said, "🔴 그 사실을 사유에 안 적는다"


def test_리그_경기의_계수도_같은_대회_유형만_쓴다() -> None:
    """🔴🔴 **Elo 를 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*.

    ⚠️ 이 시험(test_리그_경기의_계수도_같은_대회_유형만_쓴다)이 지키던 것은 **기준 확률(Elo → 승·무·패)** 경로다.
    🔴 **확률은 이미 그 수를 안 보고 있었다** — 승무패는 `flat_prob`
       (1/3 균등 + 변수)이 내고 `probmodel.run` 은 `floor` 를 안 읽는다.
       쓰이던 곳은 카드의 **기준 열**과 **방향 판정**뿐이었고 둘 다 표시인데,
       `eloratings.net/World.tsv` 를 **매 실행** 받고 있었다.
    🔴 그래서 지웠고, 이 시험은 *"되살아나지 않는다"* 를 지킨다.
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    #  ① Elo 모듈 넷이 **없다**
    for rel in ("app/collect/elo.py", "app/collect/leagueelo.py",
                "app/core/domesticelo.py"):
        assert not (root / rel).exists(), f"🔴 `{rel}`(Elo)가 되살아났다"
    #  ② 기준 확률 함수가 **없다**
    from app.core import base as _b
    for one in ("we", "triple_of", "triple_from", "base_prob"):
        assert not hasattr(_b, one), f"🔴 `core.base.{one}`(Elo)가 되살아났다"
    from app.core.stages import s2b_base as _s2b
    for one in ("_base", "continental_elo", "league_level"):
        assert not hasattr(_s2b, one), f"🔴 `s2b_base.{one}`(Elo)가 되살아났다"
    #  ③ ② 는 **남아 있다** — 오늘 XI 가 평소보다 약/강한가는 Elo 를 안 쓴다
    for one in ("strength_of", "fill_values", "adjust"):
        assert hasattr(_b, one), f"🔴 `core.base.{one}`(선수 전력)이 같이 지워졌다"
    #  ④ 기준은 **늘 비어 있고 사유가 붙는다**(#3 조용한 0 금지)
    said = (root / "app/core/stages/s2b_base.py").read_text(encoding="utf-8")
    assert "BaseProb(probs=None" in said, "🔴 기준을 빈 값으로 안 낸다"
    assert "기준(Elo)은 지웠다" in said, "🔴 그 사실을 사유에 안 적는다"


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


def test_라인업_보정이_확률을_움직이고_신뢰도를_함께_적는다() -> None:
    """🔴🔴 **Elo 를 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*.

    ⚠️ 이 시험(test_라인업_보정이_확률을_움직이고_신뢰도를_함께_적는다)이 지키던 것은 **기준 확률(Elo → 승·무·패)** 경로다.
    🔴 **확률은 이미 그 수를 안 보고 있었다** — 승무패는 `flat_prob`
       (1/3 균등 + 변수)이 내고 `probmodel.run` 은 `floor` 를 안 읽는다.
       쓰이던 곳은 카드의 **기준 열**과 **방향 판정**뿐이었고 둘 다 표시인데,
       `eloratings.net/World.tsv` 를 **매 실행** 받고 있었다.
    🔴 그래서 지웠고, 이 시험은 *"되살아나지 않는다"* 를 지킨다.
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    #  ① Elo 모듈 넷이 **없다**
    for rel in ("app/collect/elo.py", "app/collect/leagueelo.py",
                "app/core/domesticelo.py"):
        assert not (root / rel).exists(), f"🔴 `{rel}`(Elo)가 되살아났다"
    #  ② 기준 확률 함수가 **없다**
    from app.core import base as _b
    for one in ("we", "triple_of", "triple_from", "base_prob"):
        assert not hasattr(_b, one), f"🔴 `core.base.{one}`(Elo)가 되살아났다"
    from app.core.stages import s2b_base as _s2b
    for one in ("_base", "continental_elo", "league_level"):
        assert not hasattr(_s2b, one), f"🔴 `s2b_base.{one}`(Elo)가 되살아났다"
    #  ③ ② 는 **남아 있다** — 오늘 XI 가 평소보다 약/강한가는 Elo 를 안 쓴다
    for one in ("strength_of", "fill_values", "adjust"):
        assert hasattr(_b, one), f"🔴 `core.base.{one}`(선수 전력)이 같이 지워졌다"
    #  ④ 기준은 **늘 비어 있고 사유가 붙는다**(#3 조용한 0 금지)
    said = (root / "app/core/stages/s2b_base.py").read_text(encoding="utf-8")
    assert "BaseProb(probs=None" in said, "🔴 기준을 빈 값으로 안 낸다"
    assert "기준(Elo)은 지웠다" in said, "🔴 그 사실을 사유에 안 적는다"


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
                                "weight_rules", "tilt_reasons"),
        # 🔴 F4 — `_lower`(세 열) 가 `_grade_by_check`(⑫ 검증)로 바뀌었다
        "app/core/pipeline.py": ("_grade_by_check",),
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


# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_역습_갈래가_필수형으로_들어온다`

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


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **M25 — 피로도가 상쇄하면 부등호를 세운다**(사용자 결정 2026-10-18)
# ══════════════════════════════════════════════════════════════════


def _fatigue_facts(ref, *, home_days: list[int], away_days: list[int]):
    """🔴 8일 창 안 직전 경기 날짜만 든 `Facts` — 사다리 ① 을 먹인다."""
    from datetime import timedelta

    from app.core.schema import Facts
    day = ref.kickoff_utc.date()

    def seq(days):
        return {"sequence": [{"date": str(day - timedelta(days=d))}
                             for d in days]}
    return Facts(recent={str(ref.home): seq(home_days),
                         str(ref.away): seq(away_days)})


def test_IR11_두_팀_다_걸리면_부등호로_한_변수만_낸다():
    """🔴🔴 M25 — *"피로도가 상쇄하면 **부등호 표시** .. 같다고 해라 ..
    피로도가 **더 큰쪽이 더 안좋은거다**"*(사용자 결정 2026-10-18).

    ⚠️ 종전: 두 팀 다 발동하면 변수 **둘**이 서로 반대쪽을 밀어 `flat_prob` 의
       순 쏠림이 **0** 이 됐다(MLS 는 일정이 빽빽해 거의 늘 그랬다).
    🔴 돌연변이: 사다리를 지우면 다시 변수 둘이 나와 상쇄한다.
    """
    import importlib

    from app.core.stages import s5_verify as s5
    from app.core.state import RunState
    ref = importlib.import_module("tests.e2e.test_v6_replay")._ref()
    row = {"favors": "opponent", "goals": "none"}
    # ① 둘 다 8일 3경기 — **경기 수가 같으니** 사다리 ②(쉰 날)로 갈린다
    facts = _fatigue_facts(ref, home_days=[3, 7], away_days=[2, 6])
    got = s5._ir_fatigue("IR11", "fatigue", row, ref, facts,
                         state=RunState(match_key="x"))
    assert len(got) == 1, f"🔴 두 팀 다 걸렸는데 변수가 {len(got)}개다 — 상쇄한다"
    one = got[0]
    # 🔴 쉰 날이 **적은** 원정이 더 피로하다 → 표의 `opponent` 가 홈을 민다
    assert one.subject == ref.away, (one.subject, one.claim)
    assert one.favors == "home", (one.favors, one.claim)
    assert ">" in one.claim and "쉰 날" in one.claim, one.claim
    assert one.usable_as_basis, one.claim
    # ② 경기 수가 **다르면** 사다리 ① 이 먼저 정한다(많은 쪽이 더 피로)
    more = s5._ir_fatigue("IR11", "fatigue", row, ref,
                          _fatigue_facts(ref, home_days=[2, 4, 6],
                                         away_days=[2, 6]),
                          state=RunState(match_key="x"))
    assert len(more) == 1 and more[0].subject == ref.home, more
    assert more[0].favors == "away" and "8일 안 경기 수" in more[0].claim, more
    # ③ 전부 같으면 **"같다"** — 확률에 안 넣는다(맥락 전용)
    same = s5._ir_fatigue("IR11", "fatigue", row, ref,
                          _fatigue_facts(ref, home_days=[2, 6],
                                         away_days=[2, 6]),
                          state=RunState(match_key="x"))
    assert len(same) == 1, same
    assert same[0].usable_as_basis is False, same[0].claim
    assert "같다" in same[0].claim, same[0].claim
    # 🔴 한쪽만 걸리면 **종전 그대로**(부등호를 세우지 않는다)
    one_side = s5._ir_fatigue("IR11", "fatigue", row, ref,
                              _fatigue_facts(ref, home_days=[2, 6],
                                             away_days=[2]),
                              state=RunState(match_key="x"))
    assert len(one_side) == 1 and one_side[0].subject == ref.home, one_side
    assert "일정 과부하" in one_side[0].claim, one_side[0].claim


def test_피로도_사다리는_잰_값끼리만_비교한다():
    """🔴 M25 — 못 잰 자는 **건너뛰고 사유에 적는다**(#3) · 합산 점수는 없다(#4).

    ⚠️ 돌연변이: `None` 을 0 으로 때우면 *"8일 안 경기 0번"* 이 사실처럼 선다.
    """
    from app.core.stages import s5_verify as s5
    # ① 한쪽을 못 쟀으면 그 자는 못 가린다 → 다음 자로 내려간다
    side, why = s5._fatigue_more({"games": None, "days": 2, "km": None},
                                 {"games": 3, "days": 4, "km": None})
    assert side == "home" and "쉰 날" in why, (side, why)
    assert "⬜" in why, why
    # ② 잴 자가 하나도 없으면 **빈 글자**(부르는 쪽이 "같다" 로 적는다)
    none, why2 = s5._fatigue_more({"games": None, "days": None, "km": None},
                                  {"games": None, "days": None, "km": None})
    assert none == "" and "⬜" in why2, (none, why2)
    # ③ 사다리는 **셋**이고 방향이 못 박혀 있다(경기 수·이동은 큰 쪽 · 쉰 날은 적은 쪽)
    assert [(k, d) for k, d, _l, _u in s5.FATIGUE_LADDER] == [
        ("games", "more"), ("days", "less"), ("km", "more")], s5.FATIGUE_LADDER



# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_저득점_필수형이_무실점_연속과_공격수_결장으로도_걸린다`

# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_맞대결_집계가_안_맞으면_그_숫자를_안_쓴다`

# ⚠️ **걷은 시험** — §1 처분(2026-10-12 셋째)으로 그 입구가 바뀌었다
#    (`our_board(drafts=)` → `fav=/dog=` · `s7_judge.run(hypo)` → 격자).
#    걷은 시험: `test_보드가_없으면_등급이_전부_보류다`

# ⚠️ **걷은 시험** — §1 처분(2026-10-12 셋째)으로 그 입구가 바뀌었다
#    (`our_board(drafts=)` → `fav=/dog=` · `s7_judge.run(hypo)` → 격자).
#    걷은 시험: `test_보드가_있으면_그_줄만_등급을_받는다`

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


# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_근거_있는_보강_갈래는_바닥값_무게를_받지_않는다`

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


# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_s5_가_그_기사의_귀속을_고치고_카드에_적는다`

# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_시나리오_무게가_우리_열에_묶인다`

# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_갈래가_없는_결과는_보강으로_덮는다`

# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_s6_입력을_여섯개_80자로_줄였다`

# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_결과가_섞인_갈래는_결과별로_쪼갠다`

# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_쪼개기는_스코어를_바꾸지_않는다`

# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_쪼갠_조각의_무게_합이_원래_무게다`

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


# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_득점_방향이_반대인_driver_를_뺀다`

def test_맞대결_규칙은_지웠다() -> None:
    """🔴🔴 **S02 삭제** — 사용자 지시 2026-10-18.

    > os02을 삭제해라 .. **5경기 패턴 분석해라**

    ⚠️ 종전 어림은 *"`s5` 가 맞대결 집계를 **목록에서 다시 센다**"*
       (`league.h2h_tally`)였다 — 집계와 목록이 어긋난 실사고를 막던 자리다.
    🔴 그 규칙(`S02` · `h2h_pattern`)과 집계 함수를 **지웠다**. 맞대결은 두 팀의
       **역대 전적**이고 사용자가 보려는 것은 **지난 5경기 패턴**이다.
    🔴 그래서 센다: 규칙 표에 `S02` 가 없고, `s5` 가 그 유형을 안 만든다.
    ⚠️ 맥락 **자료**(`facts.h2h`)는 그대로 받는다 — 되살리려면 규칙만 넣으면 된다.
    """
    import inspect

    from app.core.stages import s5_verify as s5
    rids = {str(r.get("id")) for r in s5.interpret_rules()}
    assert "S02" not in rids, sorted(rids)
    kinds = {str(r.get("type")) for r in s5.interpret_rules()}
    assert "h2h_pattern" not in kinds, sorted(kinds)
    src = inspect.getsource(s5)
    assert "_ir_h2h(" not in src, "🔴 그 함수가 아직 있다"
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


def test_football_data_없는_리그는_fotmob_결과로_Elo_를_굴린다() -> None:
    """🔴🔴 **Elo 를 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*.

    ⚠️ 이 시험(test_football_data_없는_리그는_fotmob_결과로_Elo_를_굴린다)이 지키던 것은 **기준 확률(Elo → 승·무·패)** 경로다.
    🔴 **확률은 이미 그 수를 안 보고 있었다** — 승무패는 `flat_prob`
       (1/3 균등 + 변수)이 내고 `probmodel.run` 은 `floor` 를 안 읽는다.
       쓰이던 곳은 카드의 **기준 열**과 **방향 판정**뿐이었고 둘 다 표시인데,
       `eloratings.net/World.tsv` 를 **매 실행** 받고 있었다.
    🔴 그래서 지웠고, 이 시험은 *"되살아나지 않는다"* 를 지킨다.
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    #  ① Elo 모듈 넷이 **없다**
    for rel in ("app/collect/elo.py", "app/collect/leagueelo.py",
                "app/core/domesticelo.py"):
        assert not (root / rel).exists(), f"🔴 `{rel}`(Elo)가 되살아났다"
    #  ② 기준 확률 함수가 **없다**
    from app.core import base as _b
    for one in ("we", "triple_of", "triple_from", "base_prob"):
        assert not hasattr(_b, one), f"🔴 `core.base.{one}`(Elo)가 되살아났다"
    from app.core.stages import s2b_base as _s2b
    for one in ("_base", "continental_elo", "league_level"):
        assert not hasattr(_s2b, one), f"🔴 `s2b_base.{one}`(Elo)가 되살아났다"
    #  ③ ② 는 **남아 있다** — 오늘 XI 가 평소보다 약/강한가는 Elo 를 안 쓴다
    for one in ("strength_of", "fill_values", "adjust"):
        assert hasattr(_b, one), f"🔴 `core.base.{one}`(선수 전력)이 같이 지워졌다"
    #  ④ 기준은 **늘 비어 있고 사유가 붙는다**(#3 조용한 0 금지)
    said = (root / "app/core/stages/s2b_base.py").read_text(encoding="utf-8")
    assert "BaseProb(probs=None" in said, "🔴 기준을 빈 값으로 안 낸다"
    assert "기준(Elo)은 지웠다" in said, "🔴 그 사실을 사유에 안 적는다"


def test_fotmob_로_받은_리그에_계수가_있고_출처를_속이지_않는다() -> None:
    """🔴🔴 **Elo 를 지웠다** — 사용자 지시 2026-10-17 *"elo 지워라"*.

    ⚠️ 이 시험(test_fotmob_로_받은_리그에_계수가_있고_출처를_속이지_않는다)이 지키던 것은 **기준 확률(Elo → 승·무·패)** 경로다.
    🔴 **확률은 이미 그 수를 안 보고 있었다** — 승무패는 `flat_prob`
       (1/3 균등 + 변수)이 내고 `probmodel.run` 은 `floor` 를 안 읽는다.
       쓰이던 곳은 카드의 **기준 열**과 **방향 판정**뿐이었고 둘 다 표시인데,
       `eloratings.net/World.tsv` 를 **매 실행** 받고 있었다.
    🔴 그래서 지웠고, 이 시험은 *"되살아나지 않는다"* 를 지킨다.
    """
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]

    #  ① Elo 모듈 넷이 **없다**
    for rel in ("app/collect/elo.py", "app/collect/leagueelo.py",
                "app/core/domesticelo.py"):
        assert not (root / rel).exists(), f"🔴 `{rel}`(Elo)가 되살아났다"
    #  ② 기준 확률 함수가 **없다**
    from app.core import base as _b
    for one in ("we", "triple_of", "triple_from", "base_prob"):
        assert not hasattr(_b, one), f"🔴 `core.base.{one}`(Elo)가 되살아났다"
    from app.core.stages import s2b_base as _s2b
    for one in ("_base", "continental_elo", "league_level"):
        assert not hasattr(_s2b, one), f"🔴 `s2b_base.{one}`(Elo)가 되살아났다"
    #  ③ ② 는 **남아 있다** — 오늘 XI 가 평소보다 약/강한가는 Elo 를 안 쓴다
    for one in ("strength_of", "fill_values", "adjust"):
        assert hasattr(_b, one), f"🔴 `core.base.{one}`(선수 전력)이 같이 지워졌다"
    #  ④ 기준은 **늘 비어 있고 사유가 붙는다**(#3 조용한 0 금지)
    said = (root / "app/core/stages/s2b_base.py").read_text(encoding="utf-8")
    assert "BaseProb(probs=None" in said, "🔴 기준을 빈 값으로 안 낸다"
    assert "기준(Elo)은 지웠다" in said, "🔴 그 사실을 사유에 안 적는다"


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


# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_올시즌_맞대결이_저득점이면_필수형이_걸린다`

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


# ⚠️ **걷은 시험** — `s9_audit`(최종 평 LLM **검열**)이 지시서
#    2026-10-12(셋째) §1 처분으로 지워졌다(그 평이 코드 템플릿이 되었다).
#    🔴 코드 계산이던 `top_scores`·`score_drivers`·`_names_in` 은 쓰는 곳
#    (`app/core/layer1.py`)으로 **옮겼다** — 사본이 아니다.
#    걷은 시험: `test_맞대결은_한_번만_팀_이름을_붙여_적는다`

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


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **사용자 지시 2026-10-09(5차)** — 경우의 수 게이트 · 폼 보완 · 총골 기준
# ══════════════════════════════════════════════════════════════════


# ⚠️ **걷은 시험** — `s9_audit`(최종 평 LLM **검열**)이 지시서
#    2026-10-12(셋째) §1 처분으로 지워졌다(그 평이 코드 템플릿이 되었다).
#    🔴 코드 계산이던 `top_scores`·`score_drivers`·`_names_in` 은 쓰는 곳
#    (`app/core/layer1.py`)으로 **옮겼다** — 사본이 아니다.
#    걷은 시험: `test_경우의_수는_시즌_막판에만_판정한다`

def test_경기당_총골을_리그_표에서_센다():
    """🔴🔴 §2·§3 — 돌연변이: 리그 평균으로 때운다.

    🔴 실측 2026-10-09 J1 로 사용자 수와 대조했다: 가시마 17득 16실 8경기 →
       **4.125**(사용자 4.1) · 감바 8득 14실 8경기 → **2.75**(사용자 2.75).
    """
    from app.collect.fotmob import team_ids, team_totals
    tj = {"props": {"pageProps": {"table": [{"data": {
        "leagueName": "J. League",
        "table": {"all": [
            {"name": "Kashima Antlers", "id": 4397, "idx": 8, "played": 8,
             "scoresStr": "17-16", "pts": 13},
            {"name": "Gamba Osaka", "id": 6582, "idx": 16, "played": 8,
             "scoresStr": "8-14", "pts": 6}]}}}]}}}
    tot = team_totals(tj)
    assert tot["Kashima Antlers"]["total_per_game"] == 4.125, tot
    assert tot["Gamba Osaka"]["total_per_game"] == 2.75, tot
    assert team_ids(tj) == {"Kashima Antlers": 4397, "Gamba Osaka": 6582}
    # ⚠️ 경기 수가 0 이면 **안 싣는다**(0 으로 나누지 않는다)
    zero = {"props": {"pageProps": {"table": [{"data": {"table": {"all": [
        {"name": "A", "id": 1, "played": 0, "scoresStr": "0-0"}]}}}]}}}
    assert team_totals(zero) == {}


def test_참고_총점_줄은_관례_줄이다():
    """🔴🔴 §3(6차) — 돌연변이: 경기 총골로 줄을 만든다(걸 수 없는 줄이 나온다).

    > 참고 줄은 **1.5/2.5/3.5 로 되돌린다**(1.2·2.2·3.2 는 실제로 걸 수 없는
    > 줄이다). 기준 총골(2.25)은 **블록 3 에 숫자로만** 적고, 줄 판정은 실제
    > 보드·피드 줄에만.

    ⚠️ 실사고 2026-10-09(강원–부천): 기준 2.25 가 `over 1.2 / 2.2 / 3.2` 를
       만들었다 — 북에 없는 줄이다.
    """
    import pathlib
    from app import rules
    assert rules.common_total_lines("soccer") == [1.5, 2.5, 3.5]
    src = pathlib.Path("app/survive.py").read_text(encoding="utf-8")
    # 🔴 **줄을 만들 때 그 수를 쓰지 않는다** — 주석 말고 코드에 없어야 한다
    code = "\n".join(ln for ln in src.splitlines()
                      if not ln.strip().startswith("#"))
    assert 'get("match_total_baseline")' not in code, \
        "경기 총골로 다시 줄을 만든다"
    # 🔴 **사실은 그대로 남는다** — 블록 3 이 숫자로 적는다
    rd = pathlib.Path("app/core/render.py").read_text(encoding="utf-8")
    assert "경기당 총골" in rd and "이 경기 기준" in rd, "블록 3 이 안 적는다"


def test_블록3_의_셋이_빠지면_머리표가_붙는다():
    """🔴 §2 마지막 줄 — 돌연변이: 조용히 내보낸다(가시마–감바가 그랬다)."""
    from app.core import render
    from app.core.schema import BaseProb, Card, Facts, MatchRef
    from datetime import datetime, timezone
    ref = MatchRef(id="x", sport="soccer", competition="J. League",
                   competition_short="J. League",
                   kickoff_utc=datetime(2026, 10, 9, 10, tzinfo=timezone.utc),
                   home="team:000316", away="team:000582",
                   home_name="A", away_name="B")
    empty = Card(match=ref, facts=Facts(), base_prob=BaseProb(why="x"))
    assert render.block3_gaps(empty) == ["폼(최근 5경기)", "경기당 총골", "핵심 선수"]
    # 🔴 셋을 다 받으면 머리표가 **없다**
    full = Card(match=ref, base_prob=BaseProb(why="x"), facts=Facts(
        recent={"team:000316": {"last5": ["W"]}},
        standings={"team_totals": {"team:000316": {"total_per_game": 4.1}},
                   "key_players": {"team:000316": [{"name": "Léo"}]}}))
    assert render.block3_gaps(full) == []
    assert any("블록 3 에" in x for x in render.warn_lines(empty)), \
        render.warn_lines(empty)



# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_폼_보완_꼴이_경기_페이지와_같은_칸을_쓴다`

# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_1겹_예상_스코어_줄이_근거와_어긋남을_적는다`

# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_반등_주장은_해석_규칙을_요구한다`

# ⚠️ **걷은 시험** — §1 처분(2026-10-12 셋째)으로 그 입구가 바뀌었다
#    (`our_board(drafts=)` → `fav=/dog=` · `s7_judge.run(hypo)` → 격자).
#    걷은 시험: `test_v7_C7_변수가_로그오즈를_직접_못_민다`


# ⚠️ **되살린 도움 함수**(걷은 블록에 묶여 사라졌다)
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


def _facts_two_squads(home_names, away_names):
    """🔴 두 팀 **소집 명단**만 든 `Facts` — 명단 대조의 재료다."""
    from app.core.schema import Facts
    return Facts(squad={"team:000164": list(home_names),
                        "team:000047": list(away_names)})
