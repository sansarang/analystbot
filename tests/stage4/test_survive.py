"""§6 생존 계산 계약 — **수동 12단계 ⑪** (사용자 지시 2026-10-02 *"11부터 가라"*).

🔴 **문턱·기준선·기호를 여기 적지 않는다.** `app/types.py`(NAME_AT·SMALL_AT)와
   `config/scenario_rules.yaml` 이 원본이고 계약은 **읽어서 대조**한다.
⚠️ 단계 7 자리이나 `tests/stage7/` 은 서명이 없어 수집되지 않는다 — 돌아가는 자리에 둔다.
"""
from __future__ import annotations

import pathlib

import glob
import importlib.util
import json
from pathlib import Path

import pytest

from app import classify, league, rules, scenarios, survive
from app.types import (BTTS_SIDES, NAME_AT, SMALL_AT, TOTAL_SIDES, Market,
                       MarketSurvival,
                       Scenario)

ROOT = Path(__file__).resolve().parents[2]
HOME, AWAY = "Sacramento Republic FC", "Las Vegas Lights FC"


class _G:
    """경기 — `classify.Game` 의 최소 대역."""

    def __init__(self, sport="soccer", league="USL Championship"):
        self.home, self.away, self.sport = HOME, AWAY, sport
        # 🔴 §5-a C 가 **리그 규정**(무승부 가능 여부)을 읽는다 — 대역도 들고 있어야 한다
        self.league = league


class _D:
    """시나리오 초안 대역. 🔴 무게 둘을 **따로** 들고 있어야 한다."""

    def __init__(self, sid, scores, strength=1.0, probability=None):
        self.id, self.scores = sid, scores
        self.strength, self.probability = strength, probability




# ══════════════════════════════════════════════════════════════════
# §6-a 대입 — ○ / △ / ✗
# ══════════════════════════════════════════════════════════════════


def test_집합이_전부_통과면_동그라미_섞이면_삼각():
    """🔴 §6-a — *"전부 통과면 ○, 전부 실패면 ✗, 섞이면 △(통과 비율만큼)"*."""
    m = Market(market_type="home")
    assert survive.apply(m, ["2-1", "1-0"], home=HOME, away=AWAY)[0] == survive.PASS
    assert survive.apply(m, ["0-1", "1-2"], home=HOME, away=AWAY)[0] == survive.FAIL
    sym, ratio, _ = survive.apply(m, ["2-1", "0-1"], home=HOME, away=AWAY)
    assert (sym, ratio) == (survive.PART, 0.5)


def test_무패는_승_더하기_무승부다():
    """§6-a — *"무패(dc)는 승+무"*."""
    assert survive.passes(Market(market_type="home_dc"), "1-1")
    assert survive.passes(Market(market_type="home_dc"), "2-1")
    assert not survive.passes(Market(market_type="home_dc"), "0-1")


def test_핸디는_더하는_꼴로_센다():
    """🔴 **내가 전에 틀린 자리다.** `a - h < 2` 로 적었더니 `+1.5` 가 `2-0` 을 통과시켰다.

    기준선은 그 팀 점수에 **더하는** 값이다: `(내 점수 + line) > 상대 점수`.
    """
    plus = Market(market_type="handicap", team=AWAY, line=1.5)
    assert survive.passes(plus, "1-0", home=HOME, away=AWAY) is True   # 1골 차 패
    assert survive.passes(plus, "2-0", home=HOME, away=AWAY) is False  # 2골 차 패
    minus = Market(market_type="handicap", team=HOME, line=-1.5)
    assert survive.passes(minus, "2-0", home=HOME, away=AWAY) is True
    assert survive.passes(minus, "1-0", home=HOME, away=AWAY) is False
    # 🔴 ±0.5 는 승/무패와 같다(§6-a)
    half = Market(market_type="handicap", team=HOME, line=-0.5)
    for sc in ("1-0", "2-1", "1-1", "0-1"):
        assert survive.passes(half, sc, home=HOME, away=AWAY) == \
            survive.passes(Market(market_type="home"), sc)
    # 🔴 **어느 팀인지 모르면 `None`** — 0 으로 때우지 않는다
    assert survive.passes(Market(market_type="handicap", team="없는팀", line=1.5),
                          "1-0", home=HOME, away=AWAY) is None


def test_총점은_방향이_있어야_하고_밀어내기는_실패다():
    """🔴 §1 *"total(over/under, 기준선)"*. 방향이 없으면 **스키마가 막는다**."""
    for side in TOTAL_SIDES:
        Market(market_type="total", team=side, line=2.5)
    over = Market(market_type="total", team="over", line=2.5)
    under = Market(market_type="total", team="under", line=2.5)
    assert survive.passes(over, "2-1") is True and survive.passes(over, "1-0") is False
    assert survive.passes(under, "1-0") is True and survive.passes(under, "2-1") is False
    # ⚠️ 정수 기준선의 밀어내기는 **이기는 것이 아니다** → ✗
    push = Market(market_type="total", team="over", line=3.0)
    assert survive.passes(push, "2-1") is False


def test_야구_동점은_승패_마켓에서_보수적으로_실패다():
    """§6-a — *"연장 규정 있는 리그의 n-n 은 승패 마켓에서 ✗(북 규정 미확인 시)"*."""
    for mt in survive.WIN_MARKETS:
        assert survive.passes(Market(market_type=mt), "3-3",
                              sport="baseball") is False
    # 🔴 축구는 그대로 — 무승부가 있는 종목이다
    assert survive.passes(Market(market_type="draw"), "3-3", sport="soccer") is True


def test_못_읽은_스코어는_분모에서_뺀다():
    """🔴 **못 읽은 것과 틀린 것은 다르다.** `False` 로 세면 생존이 거짓으로 내려간다."""
    m = Market(market_type="home")
    assert survive.passes(m, "엉망") is None
    sym, ratio, bad = survive.apply(m, ["2-1", "엉망"], home=HOME, away=AWAY)
    assert (sym, ratio, bad) == (survive.PASS, 1.0, 1)
    # 통째로 못 읽으면 기호가 `?` 다 — △ 0.0 으로 **보이지 않게** 한다
    assert survive.apply(m, ["엉망"], home=HOME, away=AWAY)[0] == "?"


# ══════════════════════════════════════════════════════════════════
# §6-b 등급 — 🔴 수가 정한다
# ══════════════════════════════════════════════════════════════════


def test_등급은_수가_정한다():
    """🔴 §6-b — 고르는 사람도 LLM 도 없다. 문턱은 `types` 가 원본이다."""
    assert survive._verdict(NAME_AT) == "name"
    assert survive._verdict(SMALL_AT) == "small"
    assert survive._verdict(round(SMALL_AT - 0.01, 4)) == "none"
    assert survive._verdict(NAME_AT - 0.0001) == "small"
    # 🔴 스키마가 어긋난 짝을 거부한다(두 겹)
    with pytest.raises(ValueError):
        MarketSurvival(market_type="home", survival=0.5, verdict="name")


def test_생존을_확률_대신_변수_합으로_센다():
    """🔴🔴 **뒤집힌 계약** — 사용자 결정 2026-10-04 (②).

    ══════════════════════════════════════════════════════════════════
    🔴 종전 계약 — *"무게는 확률이 1순위다"*
    ══════════════════════════════════════════════════════════════════

    봇이 스스로 카드에 적은 줄:

    > 🔴🔴 변수 3개가 **근거는 바꾸는데 등급은 하나도 안 바꾼다** — 무게가 확률
    > (포아송 격자)이고 그 격자는 **순위표에서 나와 변수와 무관**하기 때문이다.
    > v4 §0 은 '변수 개수·정확도 = 시나리오 품질' 을 전제하는데 지금 구조에서는
    > 변수가 생존에 닿지 않는다 — 사용자 결정이 필요하다

    사용자 답:

    > 그 지적이 맞고, 이건 **결정이 아니라 v4대로 돌리는 문제**다. v4 §5-a 는
    > **시나리오 strength = 변수 weight 합**이라고 적혀 있다. 포아송 격자는
    > **v4 에 없는 봇의 추가물**이다 … 변수 → strength, **이게 생존율을 정한다.**
    > 격자 → 시나리오 안의 **스코어 집합을 고르는 도구로만.**
    > **지금은 변수가 장식이다.**

    🔴 격자는 **지우지 않았다** — `p_market`(실제로 맞을 확률)·스코어 고르기·
       커버리지 경고로 계속 쓴다. 생존의 분자·분모만 아니다.
    """
    ds = [_D("A", ["2-1"], 9.0, 0.2), _D("B", ["0-1"], 1.0, 0.8)]
    w, mode = survive.weights(ds)
    # 🔴 확률을 **줬는데도** 변수 합으로 센다
    assert mode.startswith("strength"), mode
    assert "§5-a" in mode, mode
    assert w == {"A": 9.0, "B": 1.0}, w
    r = survive.run(ds, _G(), board=[Market(market_type="home")])
    # 🔴 확률로 셌으면 0.2 다. 변수 합으로 세면 **0.9** 다
    assert r.rows[0]["survival"] == 0.9, r.rows[0]
    # 🔴 확률을 **아예 안 줘도** 같다 — 되돌림 자리가 하나다
    ds[1].probability = None
    w2, mode2 = survive.weights(ds)
    assert mode2 == mode and w2 == w, (mode2, w2)
    # ⚠️ 선언이 그 사실을 적어 두나 — **되돌린 것을 숨기지 않는다**
    cfg = rules.scenario_weight()
    assert "변수 weight 합" in cfg["weight"], cfg
    assert "자료 부족" in cfg["fallback"], cfg
    assert cfg.get("was_until_2026_10_04"), cfg
    assert cfg.get("grid_role"), cfg


# ══════════════════════════════════════════════════════════════════
# §6-c 보드
# ══════════════════════════════════════════════════════════════════


def test_보드가_있으면_보드_줄만_센다():
    """🔴 §6-c-1 · §7 R2 — 09-29 태국–베트남에서 보드에 없는 언더 4.5 를 적었다."""
    ds = [_D("A", ["2-1"], 1.0, 0.5), _D("B", ["0-1"], 1.0, 0.5)]
    board = [Market(market_type="home")]
    r = survive.run(ds, _G(), board=board)
    assert [x["market"].market_type for x in r.rows] == ["home"]
    assert r.to_survival(1).off_board(board) == []


# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_보드가_없으면_우리_기준선이고_그렇게_적는다`

def test_총점은_기준선별_생존을_함께_낸다():
    """§6-f — *"언더 X.5 (기준선 Y.5면 △, Z.5면 ✗)"* — 다른 북을 봐도 대입하게."""
    ds = [_D("A", ["2-1"], 1.0, 0.5), _D("B", ["1-0"], 1.0, 0.5)]
    r = survive.run(ds, _G(),
                    board=[Market(market_type="total", team="under", line=2.5)])
    assert r.by_line, r.notes
    lines = [x["line"] for x in r.by_line[0]["lines"]]
    assert 2.5 in lines and len(lines) >= 2
    # 🔴 기준선이 올라가면 언더 생존은 **줄지 않는다**(단조)
    svs = [x["survival"] for x in sorted(r.by_line[0]["lines"],
                                         key=lambda x: x["line"])]
    assert svs == sorted(svs), svs


def test_배당은_들어올_칸이_없다():
    """🔴 §6-c-5 · §7 R8 — 보드는 *"마켓 종류 + 기준선"* 만 읽는다."""
    bad = {"price", "odds", "decimal", "배당"}
    assert not (bad & set(Market.model_fields)), Market.model_fields
    assert not (bad & set(MarketSurvival.model_fields))
    # 🔴 이름에도 가격이 없다 — 카드가 이 이름을 그대로 쓴다
    name = survive.name_of(Market(market_type="total", team="over", line=2.5))
    assert "2.5" in name and "오버" in name


# ══════════════════════════════════════════════════════════════════
# §7 R6 — 깨질 자리가 없는 1.0 은 1.0 이 아니다
# ══════════════════════════════════════════════════════════════════


def test_R6_2골차_시나리오가_없으면_등급을_안_매긴다():
    """🔴 §7 R6 — *"+1.5 마켓 계산 시 0-2 스코어 시나리오 없으면 실패"*.

    09-29 돗토리·후쿠시마가 그것을 빠뜨렸다가 1.0 → 0.85 로 내려갔다.
    ⚠️ **사용자 지시 ⑪ 이 이 결함을 반대 방향에서 또 찾았다** — `2-0` 만 만들고
       `0-2` 를 안 만들어서 홈 +1.5 가 깨질 자리 없이 1.0 을 받고 있었다.
    """
    ds = [_D("A", ["2-1"], 1.0, 0.5), _D("B", ["1-0"], 1.0, 0.5)]
    m = Market(market_type="handicap", team=HOME, line=1.5)
    r = survive.run(ds, _G(), board=[m])
    assert r.rows[0]["survival"] == 1.0
    assert r.rows[0]["verdict"] == "none", "깨질 자리가 없는데 이름을 적었다"
    assert any("R6" in n for n in r.notes), r.notes
    # 🔴 0-2 를 넣으면 등급이 선다
    ds.append(_D("C", ["0-2"], 0.3, 0.1))
    r2 = survive.run(ds, _G(), board=[m])
    assert r2.rows[0]["verdict"] in ("name", "small"), r2.notes


def test_5c_5_가_방향마다_따로_본다():
    """🔴 전 판은 *"2골 차 스코어가 하나라도 있으면 건너뛴다"* 였다.

    그러면 `3-0` 이 있을 때 `0-2` 를 **영영 안 만든다** → 홈 +1.5 가 깨질 자리 없이
    생존 1.0 을 받는다. 방향마다 본다.
    """
    cfg = rules.cross_rule("5c-5")
    sides = cfg["two_goal_scores"]
    assert set(sides) == {"home", "away"}, sides
    assert scenarios._wins_by(sides["home"][0], "home", 2)
    assert scenarios._wins_by(sides["away"][0], "away", 2)
    assert not scenarios._wins_by(sides["home"][0], "away", 2)
    # 🔴 `3-0` 은 홈 2골 차 승이지 **원정** 2골 차 승이 아니다
    assert scenarios._wins_by("3-0", "home", 2)
    assert not scenarios._wins_by("3-0", "away", 2)


# ══════════════════════════════════════════════════════════════════
# 🔴 두 수를 나란히 — survival 과 격자 전체 확률
# ══════════════════════════════════════════════════════════════════


def test_격자_전체_확률을_함께_낸다():
    """🔴 `survival` 은 *"내가 세운 이야기들 중"*, `p_market` 은 *"실제로"* 다.

    ⚠️ 내가 전 판에 *"안 덮인 결과는 살지 않는다고 보자"* 고 말했다 — **틀렸다.**
       `3-0` 은 어느 시나리오에도 없지만 총점 2.5 오버인지는 **정확히 안다.**
    """
    probs = league.score_probabilities(1.9, 0.9)
    ds = [_D("A", ["2-1"], 1.0, 0.5), _D("B", ["1-0"], 1.0, 0.5)]
    r = survive.run(ds, _G(),
                    board=[Market(market_type="total", team="over", line=2.5)],
                    probs=probs)
    p = r.rows[0]["p_market"]
    assert p is not None and 0.0 < p < 1.0
    # 🔴 격자가 없으면 **`None`** — 0 으로 때우지 않는다
    r2 = survive.run(ds, _G(), board=[Market(market_type="home")])
    assert r2.rows[0]["p_market"] is None






def test_손익분기_아래면_이름을_적지_않는다():
    """🔴 §0 — *"전부 살아남는 마켓만 낸다"*. 맞을 확률보다 틀릴 확률이 큰 자리에
    이름을 적는 것은 그 문장과 정면으로 어긋난다.

    ⚠️ `0.5` 는 **지어낸 값이 아니다** — 두 쪽 마켓의 손익분기점이다.
    실측(정답지): `Las Vegas +1.5` survival 0.8503(소액) ↔ 격자 확률 0.6146 →
    veto 가 **안 걸린다**(0.6146 > 0.5). 걸리는 자리는 그보다 낮은 쪽이다.
    """
    assert survive.BREAK_EVEN == 0.5
    # ⚠️ ②(2026-10-04) 뒤 생존은 **변수 합**으로 센다 — 무게를 `strength` 로 준다
    #    (종전엔 `probability` 0.9/0.1 로 줬다). 이 시험의 요점은 **손익분기 veto** 다.
    ds = [_D("A", ["2-1"], 0.9, 0.9), _D("B", ["0-1"], 0.1, 0.1)]
    probs = league.score_probabilities(0.4, 2.4)   # 🔴 원정이 훨씬 세다
    m = Market(market_type="home")
    r = survive.run(ds, _G(), board=[m], probs=probs)
    row = r.rows[0]
    assert row["survival"] >= SMALL_AT, row
    assert row["p_market"] < survive.BREAK_EVEN, row
    assert row["verdict"] == "none", "손익분기 아래인데 이름을 적었다"
    assert any("손익분기 veto" in n for n in r.notes), r.notes
    # 🔴 격자가 없으면 veto 를 **물을 수 없다** — 그때는 걸지 않는다
    r2 = survive.run(ds, _G(), board=[m])
    assert r2.rows[0]["verdict"] != "none"




# ══════════════════════════════════════════════════════════════════
# §3 스키마까지 선다
# ══════════════════════════════════════════════════════════════════




def test_시나리오가_없으면_생존을_세지_않는다():
    """🔴 §7 R5 — 자료 부족이면 셀 것이 없다. **0 을 내지 않는다.**"""
    r = survive.run([], _G())
    assert not r.markets and not r.rows
    assert any("자료 부족" in n for n in r.notes), r.notes


# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_5c_5_는_3_0_이_있어도_0_2_를_만든다`

def test_통과_비율을_개수가_아니라_확률로_센다():
    """🔴🔴 **돌연변이가 통과해서 더한 계약이다.**

    §6-a 원문은 *"통과 비율만큼 strength 를 부분 인정"* 이다. 전 판은 그 비율을
    **스코어 개수**로 셌다 — `2-1` 과 `1-0` 을 똑같이 반반으로 봤다.
    🔴 그 둘은 똑같이 그럴듯하지 않다. 격자는 이미 있었고 **안 쓰고 있었다.**
    """
    probs = league.score_probabilities(1.9, 0.9)
    over = Market(market_type="total", team="over", line=2.5)
    # `2-1`(3골·통과) + `1-0`(1골·실패) — 개수로는 정확히 0.5 다
    sym, ratio, _ = survive.apply(over, ["2-1", "1-0"], home=HOME, away=AWAY,
                                  probs=probs)
    assert sym == survive.PART
    assert ratio != 0.5, "개수로 셌다 — 두 스코어의 확률이 다른데 반반이다"
    grid = probs["scores"]
    want = round(grid["2-1"] / (grid["2-1"] + grid["1-0"]), 4)
    assert abs(ratio - want) < 1e-4, (ratio, want)
    # 🔴 격자가 없으면 **개수로 돌아간다**(그 사실이 기록에 남는다)
    assert survive.apply(over, ["2-1", "1-0"], home=HOME, away=AWAY)[1] == 0.5
    # 🔴 **기호는 개수로 정한다** — 확률 가중이 ○/✗ 를 흐리면 안 된다
    assert survive.apply(over, ["2-1", "3-1"], home=HOME, away=AWAY,
                         probs=probs)[0] == survive.PASS
    assert survive.apply(over, ["1-0", "0-0"], home=HOME, away=AWAY,
                         probs=probs)[0] == survive.FAIL


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 채점 — **실제 결과가 기준이다** (사용자 지시 2026-10-02)
# ══════════════════════════════════════════════════════════════════
#
# > 정답지는 없다... 정답은 없는거다... 명심해라... 정답지는 지운다...
# > 데이타가 쌓이고 그럼 그거가지고 분석을 하고... 스포츠는 정답이 없는거다...


class _MS:
    def __init__(self, mt, verdict, survival=1.0, team=None, line=None):
        self.market_type, self.verdict = mt, verdict
        self.survival, self.team, self.line = survival, team, line


def test_실제_결과로_채점한다():
    """🔴 묻는 것은 하나다 — **이름을 적은 마켓이 맞았나.**

    ⚠️ *"페이블의 분석과 같은가"* 는 묻지 않는다. 그 기준은 지웠다.
    """
    ds = [_D("A", ["2-1"], 1.0, 0.4), _D("D", ["3-2"], 0.4, 0.1)]
    mk = [_MS("home", "name"), _MS("away", "none"),
          _MS("total", "small", 0.85, team="over", line=2.5)]
    got = survive.grade(mk, ds, 3, 2, game=_G())
    assert got["result"] == "3-2"
    # 🔴 실제 스코어를 담은 시나리오를 찾는다
    assert got["realized"] == "D", got
    # 🔴 이름 적은 둘(홈 승·오버 2.5) 다 맞았다
    assert got["named"] == 2 and got["hit"] == 2, got
    rows = {v["market"]: v["hit"] for v in got["verdicts"]}
    assert rows["홈 승"] is True and rows["원정 승"] is False
    assert rows["오버 2.5"] is True


def test_어느_시나리오에도_없던_결과를_기록한다():
    """🔴🔴 **이 줄이 가장 값지다** — 우리가 그 결과를 아예 그리지 않았다는 기록이다.

    ⚠️ 실측 2026-10-02: 축구 카드의 덮이지 않은 확률이 0.33~0.39 였다. 그 구간이
       실제로 나면 **맞고 틀린 문제가 아니라 안 그린 문제**다 — 그 둘을 섞지 않는다.
    """
    ds = [_D("A", ["2-1"], 1.0, 0.5), _D("B", ["0-1"], 1.0, 0.5)]
    got = survive.grade([_MS("home", "name")], ds, 4, 0, game=_G())
    assert got["realized"] is None
    assert any("어느 시나리오에도 없었다" in n for n in got["notes"]), got["notes"]
    # 🔴 그래도 마켓 채점은 된다 — 4-0 은 홈 승이다
    assert got["hit"] == 1


def test_그때_그_결과에_얼마를_줬는지_남긴다():
    """🔴 교정(calibration)의 재료다 — 쌓이면 *"0.1 이라고 한 것이 몇 번 났나"* 를 센다.

    ⚠️ 그것이 λ 보정 계수를 **측정**하는 길이다(발표된 계수는 없다).
    """
    probs = league.score_probabilities(1.9, 0.9)
    ds = [_D("A", ["2-1"], 1.0, 0.5)]
    got = survive.grade([_MS("home", "name")], ds, 2, 1, game=_G(), probs=probs)
    assert got["result_probability"] == probs["scores"]["2-1"]
    # 🔴 격자가 없으면 그 칸이 **없다** — 0 으로 때우지 않는다
    assert "result_probability" not in survive.grade(
        [_MS("home", "name")], ds, 2, 1, game=_G())






def test_격자를_람다로_되살릴_수_있다():
    """🔴 격자 64칸을 저장하지 않는 대신 `λ` 두 수를 적는다 — 그것으로 **같은** 격자가
    나와야 한다. 안 나오면 쌓인 확률이 그때의 확률이 아니다."""
    g1 = league.score_probabilities(2.14, 1.079)
    assert g1 and g1["lam"] == {"home": 2.14, "away": 1.079}
    g2 = league.score_probabilities(g1["lam"]["home"], g1["lam"]["away"])
    assert g2["scores"] == g1["scores"], "λ 로 되살린 격자가 다르다"


