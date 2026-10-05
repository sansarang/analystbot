"""§7 방아쇠 계약 — **수동 12단계 ⑫** (사용자 지시 2026-10-02).

🔴 **방아쇠의 상한은 지어낸 숫자가 아니다** — 변수를 빼고 §5·§6 을 다시 돌린 값이다.
   그것이 이 파일이 검사하는 전부다. 숫자를 여기 적지 않는다.
⚠️ 단계 8 자리이나 `tests/stage8/` 은 서명이 없어 수집되지 않는다 — 돌아가는 자리에 둔다.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app import cells, classify, league, rules, scenarios, triggers
from app.types import Market

ROOT = Path(__file__).resolve().parents[2]
HOME, AWAY = "Sacramento Republic FC", "Las Vegas Lights FC"


class _G:
    def __init__(self, sport="soccer", league="USL Championship"):
        self.home, self.away, self.sport = HOME, AWAY, sport
        # 🔴 §5-a C 가 **리그 규정**(무승부 가능 여부)을 읽는다 — 대역도 들고 있어야 한다
        self.league = league


def _v(text, vtype, direction, hardness="hard"):
    """변수 하나. 🔴 `classify.Classified` 를 그대로 쓴다(대역이 아니다)."""
    return classify.Classified(text=text, source_url="https://x/1",
                               hardness=hardness, type=vtype,
                               direction=direction, why="시험",
                               dateless_reason="시험 자료", team=None)


def _golden():
    spec = importlib.util.spec_from_file_location(
        "t_sc2", ROOT / "tests/stage4/test_scenarios.py")
    t = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(t)
    facts, st = t._collect()
    if st is None:
        pytest.skip("순위표 카세트가 없다")
    game = t._game()
    items = classify.classify_facts(facts, game)
    hr = scenarios._venue_row(st, "home", game.home)
    ar = scenarios._venue_row(st, "away", game.away)
    exp = league.expected_goals(hr, ar, st["venue_averages"])
    probs = league.score_probabilities(exp["home"], exp["away"])
    return items, game, st, probs


# ══════════════════════════════════════════════════════════════════
# "언제 보나" — 🔴 yaml → cells.WAKE 에서 나온다
# ══════════════════════════════════════════════════════════════════


def test_모든_유형에_뒤집는_세포가_적혀_있다():
    """🔴 §9 단계 5 완료 조건 — *"§4 유형표 전 항목에 **세포 질문 매핑**"*.

    ⚠️ 어휘는 `cells.Q_TYPES` 다 — yaml 에서 새 이름을 만들면 여기서 빨개진다.
    """
    types = rules.variable_types()
    miss = [k for k, v in types.items() if not v.get("watch")]
    assert not miss, f"`watch` 가 없는 유형 {miss}"
    bad = [(k, v["watch"]) for k, v in types.items()
           if v["watch"] not in cells.Q_TYPES]
    assert not bad, f"`cells.Q_TYPES` 에 없는 이름 {bad}"


def test_언제_보나를_세포_시각에서_계산한다():
    """🔴 시각을 방아쇠에 적지 않는다 — `cells.WAKE` 가 원본이다(사본 금지)."""
    got = triggers.when_of("individual")
    q = rules.variable_types()["individual"]["watch"]
    mins = cells.WAKE[q][0]
    assert str(mins) in got and q in got, (got, q, mins)
    # 🔴 창이 없는 질문(아침 1회)은 분을 **지어내지 않는다**
    assert "하루 1회" in triggers.when_of("stakes")
    # 🔴 모르는 유형은 **모른다고** 적는다
    assert "모른다" in triggers.when_of("없는유형")


# ══════════════════════════════════════════════════════════════════
# 상한 — 🔴 반사실 재계산이다
# ══════════════════════════════════════════════════════════════════


def test_변수를_빼면_상한이_실제로_내려간다():
    """🔴 이것이 ⑫ 의 전부다 — *"무엇이 보이면 → 무엇이 바뀌고 → **상한 얼마**"*.

    상한은 그 변수를 뺀 뒤 §6 이 **실제로 내는 수**다. 지어낸 숫자가 아니다.
    ⚠️ 무게를 §5-d(strength)로 두어야 변수가 생존에 닿는다 — 격자를 주지 않는다.
    """
    items = [_v("홈 1", "stakes", "home"), _v("홈 2", "recent_pattern", "home"),
             _v("홈 3", "home_field", "home"), _v("원정 1", "absence", "away"),
             _v("원정 2", "travel_schedule", "away")]
    game = _G()
    board = [Market(market_type="home")]
    res = triggers.run(items, game, board=board)
    assert res.triggers, res.notes
    moved = [t for t in res.triggers if t.caps]
    assert moved, f"상한이 움직인 방아쇠가 없다 — {res.notes}"
    c = moved[0].caps[0]
    assert c.before != c.after
    # 🔴 **등급이 안 바뀌어도 움직인 것은 움직인 것이다.** 전 판은 등급만 봐서
    #    `그대로` 를 냈고 그러면 "0.56 → 0.68" 이 사라졌다.
    assert c.direction in triggers.Cap.MOVES and c.direction != "그대로", c
    assert "생존" in c.line() and str(c.after) in c.line()


def test_빠지면_자료부족이_되는_변수는_전부_철회다():
    """🔴 §7 R5 — 변수 3개·방향 2종을 못 채우면 **시나리오를 만들지 않는다.**

    그러면 이름을 적던 마켓이 **전부 철회**된다. 그것이 가장 센 방아쇠다.
    """
    items = [_v("홈 1", "stakes", "home"), _v("홈 2", "recent_pattern", "home"),
             _v("원정 1", "absence", "away")]
    res = triggers.run(items, _G(), board=[Market(market_type="home_dc")])
    hard = [t for t in res.triggers if t.insufficient]
    assert hard, f"자료 부족 방아쇠가 없다 — {res.notes}"
    # 🔴 철회된 마켓은 등급이 `none` 이다
    for t in hard:
        for c in t.caps:
            assert c.verdict_after == "none" and c.withdrawn


def test_등급이_내려가는_방아쇠가_먼저_온다():
    """🔴 정렬 — **돈을 잃는 자리가 먼저다.** 근거만 흔드는 것은 뒤다."""
    items = [_v("홈 1", "stakes", "home"), _v("홈 2", "recent_pattern", "home"),
             _v("홈 3", "home_field", "home"), _v("원정 1", "absence", "away"),
             _v("원정 2", "travel_schedule", "away"),
             _v("원정 3", "h2h_pattern", "away")]
    res = triggers.run(items, _G(), board=[Market(market_type="home")], limit=9)
    keys = [t.impact for t in res.triggers]
    assert keys == sorted(keys, reverse=True), keys


def test_상한에_걸려_잘린_방아쇠를_이름으로_남긴다():
    """🔴 조용한 0 금지 — `①~④` 만 적으면 나머지가 **사라진 것처럼** 보인다."""
    items, game, st, probs = _golden()
    res = triggers.run(items, game, standings=st, probs=probs, limit=2)
    assert len(res.triggers) <= 2
    assert res.dropped, "잘린 것을 이름으로 안 남겼다"
    assert any("만 적었다" in n for n in res.notes), res.notes
    # 🔴 번호는 `①②③…` 이다(사용자 판의 꼴)
    assert [t.id for t in res.triggers][:2] == ["①", "②"][:len(res.triggers)]


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 이 계약이 가장 중요하다 — **변수가 생존에 닿지 않는다**
# ══════════════════════════════════════════════════════════════════


def test_변수가_등급을_움직인다():
    """🔴🔴 **뒤집힌 계약** — 사용자 결정 2026-10-04 (②).

    ══════════════════════════════════════════════════════════════════
    🔴 종전 계약 이름 — `test_확률_무게에서는_변수가_등급을_못_바꾼다`
    ══════════════════════════════════════════════════════════════════

    그 고정물은 **구조 문제를 못 박아 둔 것**이었다: 무게가 확률(포아송 격자)이면
    그 격자는 **순위표**에서 나와 변수와 무관하고, 그래서 변수를 빼도 생존이 한
    치도 안 움직였다. ⚠️ v4 §0 은 그 반대를 전제한다 — *"변수 개수·정확도 =
    시나리오 품질"*.

    🔴 **그 병을 2026-10-04 에 고쳤다**(사용자 결정 ②):

    > v4 §5-a 는 **시나리오 strength = 변수 weight 합**이라고 적혀 있다. 포아송
    > 격자는 **v4 에 없는 봇의 추가물**이고 … 변수 → strength, **이게 생존율을
    > 정한다** … 이렇게 하면 §0 의 "변수 개수·정확도 = 시나리오 품질" 이 코드에서
    > 참이 된다. **지금은 변수가 장식이다.**

    ⚠️ 그래서 이 시험은 **반대를 잠근다**: 변수가 빠지면 **등급이 움직인다.**
       🔴 격자를 줘도 마찬가지다 — 격자는 더 이상 생존의 무게가 아니다.
    """
    items, game, st, probs = _golden()
    res = triggers.run(items, game, standings=st, probs=probs)
    assert res.triggers, res.notes
    # 🔴 근거(§5-d)도 움직인다
    assert all(t.moved_strength for t in res.triggers), res.triggers
    # 🔴🔴 **그리고 등급도 움직인다** — 격자를 줬는데도 그렇다
    assert any(t.caps for t in res.triggers), [
        (t.label, t.moved_strength, t.caps) for t in res.triggers]
    assert not any(t.grade_unchanged for t in res.triggers
                   if t.caps), res.triggers
    # 🔴 **그 병의 사유 문장이 더는 안 나온다**
    assert not any("등급은 하나도 안 바꾼다" in n for n in res.notes), res.notes
    # 🔴 격자를 **안 줘도** 같다 — 되돌림 자리가 하나다
    bare = {k: v for k, v in st.items()
            if k not in ("venue_averages", "venue_rows")}
    alt = triggers.run(items, game, standings=bare)
    assert any(t.caps for t in alt.triggers), alt.notes


def test_등급이_안_움직이는_방아쇠도_근거는_적는다():
    """🔴 등급이 안 움직이는 줄이 **있을 수는 있다**(그 변수가 죽어도 마켓이 산다).

    ⚠️ 그때도 **근거는 움직인다** — 안 적으면 변수가 한 일이 아무 데도 안 남는다
       (#3 조용한 0 금지).
    """
    items, game, st, probs = _golden()
    res = triggers.run(items, game, standings=st, probs=probs)
    assert all(t.moved_strength for t in res.triggers), res.triggers
    txt = triggers.render(res)
    assert "근거(§5-d)" in txt, txt


# ══════════════════════════════════════════════════════════════════
# 출력
# ══════════════════════════════════════════════════════════════════


def test_방아쇠_블록이_세_칸을_다_낸다():
    """사용자 판의 꼴 — *"무엇이 보이면 → 무엇이 바뀌고 → 상한 얼마"*."""
    items, game, st, probs = _golden()
    txt = triggers.render(triggers.run(items, game, standings=st, probs=probs))
    assert txt.startswith("방아쇠")
    assert "거짓으로 드러나면" in txt          # 무엇이 보이면
    assert "언제:" in txt                      # 언제
    assert "R1" in txt or "R2" in txt          # 변수 번호
    # 🔴 §7 R8 — 가격이 들어올 칸이 없다
    bad = {"price", "odds", "decimal", "배당"}
    assert not (bad & set(Market.model_fields))
    assert "배당" not in txt


def test_변수가_없으면_방아쇠를_지어내지_않는다():
    """🔴 빈 결과를 **사유와 함께** 낸다."""
    res = triggers.run([], _G())
    assert not res.triggers
    assert any("변수가 없다" in n for n in res.notes), res.notes
    assert "없다" in triggers.render(res)
