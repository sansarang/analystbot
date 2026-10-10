"""🔴🔴 **최종 평** — 사용자 지시 2026-10-10(넷째).

> 금지: **사실 묶음 밖의 사실·숫자** / **평으로 확률 바꾸기** / **근거 없는 감성어** /
> 시장을 근거로 쓰기 / EV·금액.
> §3 검열 (q) 근거 · (r) 수치 · (s) 측면 · (t) 골 경로 · (u) 방향 · (v) 운 요소.

🔴 이 계약이 막는 것: 평이 **없는 것을 말하는 것**과 **확률과 다른 말을 하는 것**.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _ref():
    from app.core.schema import MatchRef
    return MatchRef(id="x:1", sport="soccer", competition="K-League 1",
                    competition_short="K리그1", home="team:000318",
                    away="team:000320", home_name="Gangwon FC",
                    away_name="Bucheon FC 1995",
                    kickoff_utc=datetime.now(timezone.utc) + timedelta(hours=2))


def _player(name, spot, flank, *, num=2, age=27, rating=6.8):
    from app.core.schema import Player
    return Player(name=name, pos=("DF" if spot in ("CB", "LB", "RB")
                                  else "GK" if spot == "GK" else "FW"),
                  number=num, spot=spot, flank=flank, age=age, rating=rating)


def _card(*, prob=(0.52, 0.26, 0.22)):
    """🔴 사실 묶음이 **다 찬** 카드 하나(라인업·골 내용·전략·확률)."""
    from app.core import goals as _g
    from app.core.schema import Card, Facts, ProbTriple, XI
    ref = _ref()
    home_now = [_player("Dae-Won Kim", "RW", "오른"),
                _player("Moon-Ki Hwang", "LB", "왼"),
                _player("Min-Ha Shin", "CB", "중앙")]
    home_usual = [_player("Old Right", "RW", "오른"),
                  _player("Old Left", "LB", "왼"),
                  _player("Min-Ha Shin", "CB", "중앙")]
    xi = {ref.home: XI(team=ref.home, state="confirmed", formation="4-4-2",
                       players=[p.name for p in home_now], lineup=home_now),
          ref.away: XI(team=ref.away, state="confirmed", formation="3-5-2",
                       players=["Ye-Geon Seong"],
                       lineup=[_player("Ye-Geon Seong", "ST", "중앙")])}
    past = {ref.home: [XI(team=ref.home, state="confirmed", formation="4-4-2",
                          players=[p.name for p in home_usual],
                          lineup=home_usual) for _ in range(5)]}
    stats = {"Dae-Won Kim": {"goals": 16, "assists": 4, "rating": 7.4,
                             "age": 28, "group": "attackers"},
             "Old Right": {"goals": 1, "assists": 0, "rating": 6.1,
                           "age": 22, "group": "attackers"},
             "Moon-Ki Hwang": {"goals": 0, "assists": 1, "rating": 6.9,
                               "age": 30, "group": "defenders"},
             "Old Left": {"goals": 0, "assists": 0, "rating": 6.2,
                          "age": 20, "group": "defenders"},
             "Min-Ha Shin": {"goals": 0, "assists": 0, "rating": 6.7,
                             "age": 29, "group": "defenders"},
             "Ye-Geon Seong": {"goals": 7, "assists": 2, "rating": 7.0,
                               "age": 26, "group": "attackers"}}
    rows = [{"home_name": "A", "away_name": "B", "mine_home": True,
             "goals": [{"minute": 12, "home": True, "before": (0, 0),
                        "after": (1, 0), "situation": "FromCorner",
                        "xg": 0.09},
                       {"minute": 77, "home": False, "before": (1, 0),
                        "after": (1, 1), "desc": "Penalty", "xg": 0.76}]}]
    prof = {"home": _g.profile_of("Gangwon FC", rows),
            "away": _g.profile_of("Bucheon FC 1995", rows)}
    matchup = {"profile": prof, "table": {"home": _g.table_of(rows),
                                          "away": _g.table_of(rows)},
               "fired": _g.fire(prof["home"], prof["away"], rest={}),
               "fired2": [], "share": {"전술": -1.2},
               "rest": {"home": 6, "away": 3}}
    return Card(match=ref,
                facts=Facts(xi=xi, past_xi=past, player_stats=stats),
                matchup=matchup,
                our_prob=ProbTriple(home=prob[0], draw=prob[1], away=prob[2]),
                prob_before=ProbTriple(home=0.55, draw=0.25, away=0.20))


def _say(**kw):
    from app.core.schema import KeyPoint, SayOut
    box = {"verdict": "Gangwon FC", "one_line": "강원이 가져간다",
           "key_points": [KeyPoint(claim=f"주장 {i}", mechanism="메커니즘",
                                   refs=["X1", "X2"]) for i in range(3)],
           "flow_first": "전반 탐색", "flow_second": "후반 강원 우세",
           "decisive_moment": "60분 이후", "flip_condition": "선제 실점"}
    box.update(kw)
    return SayOut(**box)


# ══════════════════════════════════════════════════════════════════
# 🔴 §1 — 사실 묶음
# ══════════════════════════════════════════════════════════════════

def test_v6_사실묶음이_일곱_칸을_id로_낸다():
    """🔴 §1 — 1-1~1-7 이 **id 로** 들어온다. ⚠️ 없는 칸은 `없음` 으로."""
    from app.core import saybundle
    box = saybundle.build(_card())
    for which, what in (("X", "1-1 라인업 변화"), ("G", "1-3 골 내용"),
                        ("P", "1-7 확률")):
        assert box.of(which), f"🔴 {what} 칸이 비었다"
    said = "\n".join(box.empty)
    # 🔴 **받는 통로가 없는 지표**는 `없음` 으로 이름이 남는다(#3)
    assert "태클" in said and "없음" in said, "🔴 못 받는 지표를 조용히 뺐다"
    # 🔴 측면 판정은 **코드가** 한 것이다 — `약화`·`강화`·`비슷` 중 하나가 있다
    swaps = [x.text for x in box.of("X") if x.kind == "swap"]
    assert swaps, "🔴 자리별 교체 항목이 없다"
    assert any(("약화" in t or "강화" in t or "비슷" in t or "판정 못 함" in t)
               for t in swaps), f"🔴 측면 판정이 없다 — {swaps}"


def test_v6_측면_비중은_근사_표시를_달고_나온다():
    """🔴🔴 §1-2 — 방향 칸이 없으니 **근사**다. 그 표시가 항목에 박혀 있어야 한다.

    ⚠️ 실측 2026-10-10: fotmob 경기 통계 37칸에 **방향(왼/오른) 칸이 없다**.
       🔴 그래서 §1-2 둘째 줄대로 오늘 XI 측면 기여로 근사하고 `approx=True` 다.
    """
    from app.core import saybundle
    box = saybundle.build(_card())
    rows = [x for x in box.of("F") if x.kind == "flank_share"]
    assert rows, "🔴 측면 비중 항목이 아예 없다"
    for one in rows:
        assert one.approx, f"🔴 근사인데 표시가 없다 — {one.text}"
        assert saybundle.APPROX in one.text, f"🔴 글에 `근사` 가 없다 — {one.text}"
    assert any("실점 방향" in x for x in box.empty), (
        "🔴 실점 방향이 **없다**는 사실을 안 적었다(#3)")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §3 — 검열 (q)~(v)
# ══════════════════════════════════════════════════════════════════

def test_v6_q_근거가_둘_미만이거나_없는_id면_버린다():
    """🔴 (q) — 근거 id **2개 이상**이고 **전부 묶음에 있는 id**."""
    from app.core import saybundle
    from app.core.schema import KeyPoint
    from app.core.stages import s9_say
    card = _card()
    box = saybundle.build(card)
    one = KeyPoint(claim="주장", mechanism="메커니즘", refs=["X1"])
    bad = s9_say.check(_say(key_points=[one] * 3), card=card, box=box)
    assert any("(q)" in x and "2개 이상" in x for x in bad), bad
    two = KeyPoint(claim="주장", mechanism="메커니즘", refs=["X1", "Z99"])
    bad2 = s9_say.check(_say(key_points=[two] * 3), card=card, box=box)
    assert any("없는 근거 id" in x for x in bad2), bad2


def test_v6_r_없는_수치와_없는_이름을_잡는다():
    """🔴 (r) — 문장 속 **숫자·선수 이름**이 근거 항목과 글자 그대로 맞는다."""
    from app.core import saybundle
    from app.core.schema import KeyPoint
    from app.core.stages import s9_say
    card = _card()
    box = saybundle.build(card)
    num = KeyPoint(claim="강원은 점유율 777 을 가져간다", mechanism="없는 수다",
                   refs=["X1", "X2"])
    bad = s9_say.check(_say(key_points=[num] * 3), card=card, box=box)
    assert any("없는 수치" in x for x in bad), bad
    nm = KeyPoint(claim="Lionel Messi 가 선발이다", mechanism="없는 이름이다",
                  refs=["X1", "X2"])
    bad2 = s9_say.check(_say(key_points=[nm] * 3), card=card, box=box)
    assert any("없는 선수 이름" in x for x in bad2), bad2


def test_v6_s_측면_주장은_측면_근거와_근사_표시를_요구한다():
    """🔴🔴 (s) — *"왼쪽이 약하다"* 류는 1-1·1-2 id 가 있어야 하고, **근사면
    `근사` 라고 써야** 한다.

    ⚠️ §5 마지막 줄이 이것을 실패 조건으로 적었다 — *"측면 지표가 없는 리그에서
       '왼쪽/오른쪽' 주장이 나오지 않는지(근사 표시 없이 나오면 실패)"*.
    """
    from app.core import saybundle
    from app.core.schema import KeyPoint
    from app.core.stages import s9_say
    card = _card()
    box = saybundle.build(card)
    # ① 측면 말을 하면서 `X*`·`F*` 근거가 없다 → 위반
    one = KeyPoint(claim="부천 왼쪽이 약하다", mechanism="그냥 그렇다",
                   refs=["G1", "P1"])
    bad = s9_say.check(_say(key_points=[one] * 3), card=card, box=box)
    assert any("(s)" in x and "근거가 없다" in x for x in bad), bad
    # ② 근사 지표(`F*`)를 근거로 쓰면서 글에 `근사` 가 없다 → 위반
    fid = [x.id for x in box.of("F") if x.approx]
    assert fid, "🔴 시험 재료 — 근사 항목이 없다"
    two = KeyPoint(claim="강원은 오른쪽으로 공격한다", mechanism="측면 비중이 높다",
                   refs=[fid[0], "X1"])
    bad2 = s9_say.check(_say(key_points=[two] * 3), card=card, box=box)
    assert any(saybundle.APPROX in x for x in bad2), bad2
    # ③ `근사` 라고 쓰면 통과한다
    three = KeyPoint(claim="강원은 오른쪽으로 공격한다(근사 지표)",
                     mechanism="측면 비중 근사", refs=[fid[0], "X1"])
    ok = s9_say.check(_say(key_points=[three] * 3), card=card, box=box)
    assert not any("(s)" in x for x in ok), ok


def test_v6_t_골경로_주장은_G_근거를_요구한다():
    """🔴 (t) — *"필드골이 없다"* 류는 **1-3 사실 id 필수**."""
    from app.core import saybundle
    from app.core.schema import KeyPoint
    from app.core.stages import s9_say
    card = _card()
    box = saybundle.build(card)
    one = KeyPoint(claim="부천은 필드골이 없다", mechanism="세트피스뿐이다",
                   refs=["X1", "X2"])
    bad = s9_say.check(_say(key_points=[one] * 3), card=card, box=box)
    assert any("(t)" in x for x in bad), bad
    gid = [x.id for x in box.of("G")]
    assert gid, "🔴 시험 재료 — 골 내용 항목이 없다"
    two = KeyPoint(claim="부천은 필드골이 없다", mechanism="세트피스뿐이다",
                   refs=[gid[0], "X1"])
    ok = s9_say.check(_say(key_points=[two] * 3), card=card, box=box)
    assert not any("(t)" in x for x in ok), ok


def test_v6_u_평이_확률_방향과_다르면_버린다():
    """🔴🔴 (u) — `verdict`·`one_line`·`flow` 가 **최종 확률 방향**과 같다.

    ⚠️ 반반이면 **한쪽 승리를 단정하지 않는다**.
    """
    from app.core import saybundle
    from app.core.stages import s9_say
    card = _card()                                    # 홈 52% · 원정 22%
    box = saybundle.build(card)
    assert saybundle.direction_of(card) == "Gangwon FC"
    bad = s9_say.check(_say(verdict="Bucheon FC 1995"), card=card, box=box)
    assert any("(u)" in x for x in bad), bad
    bad2 = s9_say.check(_say(one_line="부천이 이긴다 — Bucheon FC 1995 승리"),
                        card=card, box=box)
    assert any("(u)" in x for x in bad2), bad2
    # 🔴 반반 카드 — 한쪽 승리를 단정하면 위반
    even = _card(prob=(0.36, 0.30, 0.34))
    box2 = saybundle.build(even)
    assert saybundle.direction_of(even) == "반반"
    bad3 = s9_say.check(_say(verdict="Gangwon FC"), card=even, box=box2)
    assert any("(u)" in x for x in bad3), bad3
    ok = s9_say.check(_say(verdict="반반", one_line="반반이다",
                          flow_second="후반도 팽팽하다"), card=even, box=box2)
    assert not any("(u)" in x for x in ok), ok


def test_v6_v_운요소_득점을_득점력의_근거로_못_쓴다():
    """🔴 (v) — 자책골·PK 로 만든 득점을 **"득점력"의 근거**로 쓰지 않는다."""
    from app.core import saybundle
    from app.core.schema import KeyPoint
    from app.core.stages import s9_say
    card = _card()
    box = saybundle.build(card)
    gid = [x.id for x in box.of("G")][0]
    one = KeyPoint(claim="부천 득점력이 좋다", mechanism="PK 로 꾸준히 넣었다",
                   refs=[gid, "X1"])
    bad = s9_say.check(_say(key_points=[one] * 3), card=card, box=box)
    assert any("(v)" in x for x in bad), bad
    # 🔴🔴 **거짓 위반을 막는다** — 실측 2026-10-10(강원–부천): 한 주장 안에서
    #    앞 문장은 *"강원 득점은 세트피스"*, 뒤 문장은 *"부천 실점에 PK 비중"*
    #    이었는데 (v) 가 글 전체를 한 덩이로 봐 **좋은 평을 템플릿으로 떨어뜨렸다**.
    #    ⚠️ 돌연변이: (v) 를 다시 글 전체로 돌리면 이 줄이 빨개진다.
    far = KeyPoint(
        claim="강원은 세트피스에서 골이 난다",
        mechanism=("강원 득점 유형은 세트피스가 가장 많다. 부천은 실점에서 "
                   "PK 비중이 높다. 그래서 공격력 차이가 아니라 경로 차이다"),
        refs=[gid, "X1"])
    ok = s9_say.check(_say(key_points=[far] * 3), card=card, box=box)
    assert not any("(v)" in x for x in ok), ok


def test_v6_근거없는_감성어를_잡는다():
    """🔴 §2 프롬프트 원칙 · 금지 조항 — `기세`·`정신력` 은 쓰지 않는다."""
    from app.core import saybundle
    from app.core.schema import KeyPoint
    from app.core.stages import s9_say
    card = _card()
    box = saybundle.build(card)
    one = KeyPoint(claim="강원이 기세를 탄다", mechanism="정신력이 좋다",
                   refs=["X1", "X2"])
    bad = s9_say.check(_say(key_points=[one] * 3), card=card, box=box)
    assert any("감성어" in x for x in bad), bad


def test_v6_주장수와_빈칸을_센다():
    """🔴 §2 — `key_points` 는 **3~5개**이고 일곱 칸이 다 차야 한다."""
    from app.core import saybundle
    from app.core.schema import KeyPoint
    from app.core.stages import s9_say
    card = _card()
    box = saybundle.build(card)
    two = [KeyPoint(claim="a", mechanism="b", refs=["X1", "X2"])] * 2
    bad = s9_say.check(_say(key_points=two), card=card, box=box)
    assert any("주장 수" in x for x in bad), bad
    bad2 = s9_say.check(_say(decisive_moment=""), card=card, box=box)
    assert any("빈 칸" in x for x in bad2), bad2


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §3 마지막 줄 — **템플릿 평**
# ══════════════════════════════════════════════════════════════════

def test_v6_두번_위반이면_코드_템플릿_평이_나온다():
    """🔴 §3 — *"또 위반이면 **코드 템플릿 평**(사실 묶음 상위 근거 셋 + 확률 방향)"*.

    ⚠️ 돌연변이: 템플릿을 지우고 빈 평을 내면 — 1겹에 블록이 **사라져** 사람이
       *"평이 없다"* 와 *"평을 버렸다"* 를 구분할 수 없다(#3).
    """
    from app.core import saybundle
    from app.core.stages import s9_say
    card = _card()
    box = saybundle.build(card)
    got = s9_say.template(card, box, why="검열 두 번 위반")
    assert got.audit == "템플릿"
    assert got.verdict == saybundle.direction_of(card)
    assert len(got.key_points) == 3, got.key_points
    assert all(kp.refs for kp in got.key_points), "🔴 템플릿도 근거 id 를 든다"
    assert got.used, "🔴 템플릿이 원 사실을 안 들었다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §4 — 카드
# ══════════════════════════════════════════════════════════════════

def test_v6_1겹_최종평이_보드_판정_바로_위다():
    """🔴🔴 §4 — *"1겹 맨 끝, **보드 판정 위에**"*.

    ⚠️ 돌연변이: 블록을 보드 판정 **아래**로 옮기면 빨개진다(지시서가 자리를
       글자로 정했다).
    """
    from app.core import layer1
    card = _card().model_copy(update={"say": _say(audit="통과")})
    said = layer1.text(card)
    assert layer1.SAY_HEAD.replace("**", "") in said.replace("**", "")
    i = said.find("🧑‍🏫")
    j = said.find("🎯 보드 판정")
    assert 0 <= i < j, f"🔴 최종 평이 보드 판정 위가 아니다(i={i} j={j})"
    # 🔴 §4 가 보인 모양 — 한 줄 요약 · 점 셋 · 흐름 · 승부처 · 뒤집히는 조건
    for want in ("📈 흐름:", "⏱ 승부처:", "🔄 뒤집히는 조건:"):
        assert want in said, f"🔴 `{want}` 줄이 없다"
    assert said.count("\n · ") >= 3, "🔴 주장 세 줄이 안 나왔다"


def test_v6_긴카드가_근거id와_원사실과_검열결과를_낸다():
    """🔴 §4 — *"긴 카드: key_point마다 **근거 id와 원 사실**, **검열 결과**"*."""
    from app.core import render, saybundle
    card = _card()
    box = saybundle.build(card)
    gid = [x.id for x in box.of("G")][0]
    from app.core.schema import KeyPoint
    say = _say(audit="통과",
               key_points=[KeyPoint(claim=f"주장 {i}", mechanism="메커니즘",
                                    refs=[gid, "X1"]) for i in range(3)],
               used={gid: box.items[gid].text,
                     "X1": box.items["X1"].text})
    said = render.say_long(card.model_copy(update={"say": say}))
    assert "판정 `통과`" in said
    assert f"`{gid}`" in said and box.items[gid].text[:20] in said, (
        "🔴 근거 id 의 **원 사실**이 긴 카드에 없다")
    assert "검열 결과" in said and "위반 0건" in said
    # 🔴 배선 — 긴 카드가 실제로 부른다(#2)
    import ast
    src = (ROOT / "app" / "core" / "render.py").read_text(encoding="utf-8")
    fn = [n for n in ast.walk(ast.parse(src))
          if isinstance(n, ast.FunctionDef) and n.name == "card_text"]
    assert fn and "say_long" in ast.unparse(fn[0]), (
        "🔴 긴 카드가 최종 평 블록을 안 부른다")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 금지 — **평으로 확률 바꾸기**
# ══════════════════════════════════════════════════════════════════

def test_v6_평은_확률을_못_바꾼다():
    """🔴🔴 금지 조항 — *"평으로 확률 바꾸기"*.

    두 가지로 막는다:
      ① `SayOut` 에 **확률 칸이 없다**(모델이 적을 자리가 없다)
      ② `with_say` 가 `our_prob`·`shape`·`hypo` 를 **안 건드린다**
    """
    import ast

    from app.core.schema import SayOut
    bad = [k for k in SayOut.model_fields
           if k in ("our_prob", "prob", "home", "draw", "away", "weight",
                    "direction", "survival", "strength", "verdict_prob")]
    assert not bad, f"🔴 `SayOut` 에 확률 칸이 있다 — {bad}"
    src = (ROOT / "app" / "core" / "pipeline.py").read_text(encoding="utf-8")
    fn = [n for n in ast.walk(ast.parse(src))
          if isinstance(n, ast.FunctionDef) and n.name == "with_say"]
    assert fn, "🔴 `with_say` 가 없다"
    said = ast.unparse(fn[0])
    for word in ("our_prob", "shape", "hypo", "variables"):
        assert word not in said, f"🔴 `with_say` 가 `{word}` 를 건드린다"
    assert '"say"' in said or "'say'" in said


def test_v6_최종평이_파이프라인_마지막이다():
    """🔴 §목적 — *"카드의 **마지막 단계**"*. ⚠️ 전술 예측보다 뒤다."""
    import ast
    src = (ROOT / "app" / "core" / "pipeline.py").read_text(encoding="utf-8")
    fn = [n for n in ast.walk(ast.parse(src))
          if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
          and n.name == "analyze"]
    assert fn, "🔴 `pipeline.analyze` 가 없다"
    said = ast.unparse(fn[0])
    i, j = said.find("with_tactic("), said.find("with_say(")
    assert 0 <= i < j, f"🔴 최종 평이 전술 예측보다 앞이다(i={i} j={j})"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §1-1 — **측면 눈금은 실측으로 맞췄다**
# ══════════════════════════════════════════════════════════════════

def test_v6_측면_눈금이_실측과_같다():
    """🔴🔴 실측 2026-10-10 — 선수 페이지의 `primaryPosition` 과 대조한 눈금.

    | `horizontalLayout.y` | 선수 페이지가 말한 자리 |
    |---|---|
    | 0.875 | **Right Back** |
    | 0.125 | **Left Back** |

    ⚠️ 돌연변이: 좌우를 뒤집으면(또는 `y` 대신 `x` 를 보면) 빨개진다 — 그 실수는
       카드에 *"왼쪽이 약하다"* 를 **반대로** 적는다.
    """
    from app.collect import fotmob as fm
    right = {"usualPlayingPositionId": 1,
             "horizontalLayout": {"x": 0.357, "y": 0.875}}
    left = {"usualPlayingPositionId": 1,
            "horizontalLayout": {"x": 0.357, "y": 0.125}}
    mid = {"usualPlayingPositionId": 1,
           "horizontalLayout": {"x": 0.357, "y": 0.625}}
    assert fm.flank_of(right) == "오른" and fm.spot_of(right) == "RB"
    assert fm.flank_of(left) == "왼" and fm.spot_of(left) == "LB"
    assert fm.flank_of(mid) == "중앙" and fm.spot_of(mid) == "CB"
    # 🔴 좌표가 없으면 **빈 글자**다(가운데로 때우지 않는다 · #3)
    assert fm.flank_of({"usualPlayingPositionId": 1}) == ""
    assert fm.spot_of({"usualPlayingPositionId": 0}) == "GK"
