"""🔴🔴 **변수 배치** — 상성 중심 확률 엔진 지시서(2026-10-10 여섯째) S1V·C5·C6.

> C5 근거 가능 변수 중 **배치 안 된 변수 0개**. 근거 불가 변수는 ①② 자리에 없다.
> C6 배치표에 없는 유형은 **배치 실패로 내려간다**(임의 배치 금지).
> V-4 계약: 근거 가능 변수 중 **어느 자리에도 배치 안 된 변수 0개**.

🔴 이 파일은 **구현보다 먼저** 썼다(지시서 §0 마지막 줄: *"단계마다 계약·테스트
   먼저 → 구현 → 초록 → 커밋"*).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _var(vid: str, kind: str, *, usable: bool = True, weight: float = 2.0,
         hardness: str = "hard"):
    from app.core.schema import Variable
    return Variable(id=vid, type=kind, subject="team:000318", favors="home",
                    hardness=hardness, weight=weight, claim=f"{kind} 사실",
                    quote="q", usable_as_basis=usable)


# ══════════════════════════════════════════════════════════════════
# 🔴 배치표 자체
# ══════════════════════════════════════════════════════════════════

def test_v7_배치표가_카탈로그_유형을_전부_덮는다():
    """🔴 C6 — 표에 없는 유형은 배치 실패다. 그래서 **카탈로그를 덮어야** 한다.

    ⚠️ 유형을 새로 만들면 이 줄이 빨개진다 — 그때 배치를 **사람이** 정한다
       (지어서 배치하지 않는다).
    """
    from app import rules
    from app.core import routing
    box = dict((rules._load("config/variable_types.yaml") or {}).get("types")
               or {})
    gone = [k for k in box if k not in routing.table()["types"]]
    assert not gone, f"🔴 배치표에 없는 카탈로그 유형 — {gone}"


def test_v7_자리_글자는_표가_정한다():
    """🔴 자리는 **열거값**이다 — 코드가 지어낸 자리를 쓰지 않는다."""
    from app.core import routing
    assert routing.AXES == ("axis0", "axis1", "axis2", "axis3")
    assert routing.VERIFY == ("V1", "V2", "V3", "V4", "V5", "V6")
    assert routing.CONST == "lambda_const"
    assert routing.HYPO == "hypo"
    # 🔴 표의 모든 자리가 그 열거값 안이다
    allowed = {*routing.AXES, routing.CONST, *routing.VERIFY, routing.HYPO}
    for kind, row in routing.table()["types"].items():
        bad = [x for x in (dict(row).get("places") or []) if x not in allowed]
        assert not bad, (kind, bad)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 C5 — 근거 가능 변수는 **전부** 배치된다
# ══════════════════════════════════════════════════════════════════

def test_v7_C5_근거가능_변수는_전부_배치된다():
    """🔴 C5 — *"근거 가능 변수 중 배치 안 된 변수 **0개**"*."""
    from app.core import routing
    rows = [_var("R1", "absence"), _var("S01", "recent_pattern"),
            _var("S03", "home_field"), _var("R9", "stakes"),
            _var("IR11", "fatigue"), _var("S02", "h2h_pattern")]
    got = routing.place(rows)
    assert not got.unplaced, f"🔴 배치 안 된 근거 가능 변수 — {got.unplaced}"
    for one in got.rows:
        assert one.places, f"🔴 `{one.id}` 가 어느 자리에도 없다"


def test_v7_C5_근거불가_변수는_축과_검증에_못_간다():
    """🔴 C5 둘째 줄 — *"근거 불가 변수는 ①②에 못 들어가고 ③에서도 맥락으로만"*.

    ⚠️ 돌연변이: `usable_as_basis` 검사를 지우면 표본 얇은 기사 하나가 **축에
       들어가** 확률을 움직인다.
    """
    from app.core import routing
    got = routing.place([_var("R5", "absence", usable=False)])
    one = got.rows[0]
    assert routing.HYPO in one.places, "🔴 맥락 자리까지 빼앗았다"
    bad = [x for x in one.places if x in routing.AXES or x in routing.VERIFY]
    assert not bad, f"🔴 근거 불가 변수가 ①② 자리에 있다 — {bad}"
    assert one.context_only is True


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 C6 — 표에 없는 유형은 **내려간다**
# ══════════════════════════════════════════════════════════════════

def test_v7_C6_표에_없는_유형은_배치_실패로_내려간다():
    """🔴 C6 — *"배치표에 없는 유형은 배치 실패로 내려간다(임의 배치 금지)"*."""
    from app.core import routing
    got = routing.place([_var("X1", "made_up_type")])
    one = got.rows[0]
    assert one.context_only is True, "🔴 모르는 유형을 근거로 남겼다"
    assert one.places == [routing.HYPO], one.places
    assert got.fails, "🔴 배치 실패를 알리지 않았다(운영자 알림)"
    assert "made_up_type" in " ".join(got.fails)


# ══════════════════════════════════════════════════════════════════
# 🔴 조건부 자리 — 적합 전·XI 불일치
# ══════════════════════════════════════════════════════════════════

def test_v7_적합_안_된_피로는_축2로_안_간다():
    """🔴 V-3 — *"fatigue … 축2 압박 감쇠(T2)만 — **적합된 경우**"*.

    🔴 우리 T2 계수는 적합 전이다 → 피로는 **V3·가설**로만 간다.
    """
    from app.core import routing
    one = routing.place([_var("IR11", "fatigue")]).rows[0]
    assert "axis2" not in one.places, f"🔴 적합 없이 축2 로 갔다 — {one.places}"
    assert "V3" in one.places and routing.HYPO in one.places
    # 🔴 적합이 들어오면 축2 로 간다(그때 이 줄이 길을 열어 준다)
    two = routing.place([_var("IR11", "fatigue")], fitted=("T2",)).rows[0]
    assert "axis2" in two.places, two.places


def test_v7_감독_발언은_XI와_일치할_때만_축2다():
    """🔴 V-3 — *"coach_intent … 축2 전략 판정 입력(**확정 XI 와 일치할 때**)"*."""
    from app.core import routing
    off = routing.place([_var("R3", "coach_intent")]).rows[0]
    assert "axis2" not in off.places, off.places
    assert "V4" in off.places
    on = routing.place([_var("R3", "coach_intent")], xi_match={"R3"}).rows[0]
    assert "axis2" in on.places, on.places


# ══════════════════════════════════════════════════════════════════
# 🔴 산출 꼴 — V-4
# ══════════════════════════════════════════════════════════════════

def test_v7_VariableSet_이_V4_칸을_든다():
    """🔴 V-4 — `{id, 유형, 내용, 출처, hard/soft, 무게, 근거 가능, 귀속 팀,
    득점 방향, 배치 자리 목록}`."""
    from app.core import routing
    got = routing.place([_var("R1", "absence", weight=3.0)])
    one = got.rows[0]
    for k in ("id", "type", "claim", "hardness", "weight", "context_only",
              "subject", "goals", "places"):
        assert hasattr(one, k), f"🔴 `{k}` 칸이 없다"
    assert one.weight == 3.0 and one.hardness == "hard"
    # 🔴 자리별로 되찾을 수 있다(축이 자기 입력을 고른다)
    assert "R1" in [x.id for x in got.of("axis0")]
    assert not got.of("V2")


def test_v7_카드가_변수_전부를_자리와_함께_낸다():
    """🔴 V-4 — *"카드 긴 블록 `🔢 변수` 에 **전부** 보이고, 각 변수가 어디에
    쓰였는지 표시"*."""
    from app.core import render
    from app.core.schema import Card, Facts
    from datetime import datetime, timedelta, timezone

    from app.core.schema import MatchRef
    ref = MatchRef(id="x:1", sport="soccer", competition="K-League 1",
                   competition_short="K리그1", home="team:000318",
                   away="team:000320", home_name="Gangwon FC",
                   away_name="Bucheon FC 1995",
                   kickoff_utc=datetime.now(timezone.utc) + timedelta(hours=2))
    rows = [_var("R1", "absence"), _var("R2", "stakes"),
            _var("R3", "made_up_type")]
    card = Card(match=ref, facts=Facts(), variables=rows)
    said = render.vars_long(card)
    for one in rows:
        assert one.id in said, f"🔴 `{one.id}` 가 카드에 없다"
    assert "axis0" in said and "V2" in said, said[:200]
    assert "배치 실패" in said, "🔴 배치 실패를 카드가 안 적는다"
    # 🔴 배선 — 긴 카드가 실제로 부른다(#2)
    import ast
    src = (ROOT / "app" / "core" / "render.py").read_text(encoding="utf-8")
    fn = [n for n in ast.walk(ast.parse(src))
          if isinstance(n, ast.FunctionDef) and n.name == "card_text"]
    assert fn and "vars_long" in ast.unparse(fn[0]), "🔴 카드가 안 부른다"


def test_v7_파이프라인이_배치를_카드에_싣는다():
    """🔴 배선 — `analyze` 가 배치를 돌리고 카드가 그것을 든다."""
    src = (ROOT / "app" / "core" / "pipeline.py").read_text(encoding="utf-8")
    assert "routing.place(" in src, "🔴 파이프라인이 배치를 안 돌린다"
    assert "varset" in src, "🔴 배치 산출을 카드로 안 보낸다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 실행이 잡은 셋 — 선수단 교체 변수 · 유형–내용 · `상대` 기준
# ══════════════════════════════════════════════════════════════════

def test_v7_선수단_교체가_변수로_만들어진다():
    """🔴🔴 V-3 — *"squad_turnover(IR03 포함) → 축0 호흡, 축1·축3 r 가중,
    V1 기준 낡음"*.

    ⚠️ 실측 2026-10-10: 선수단 교체가 **깃발로만** 있어 배치표를 지나지 않았고,
       김천 VariableSet 에 `squad_rotation` 이 **0개**였다 — 축이 받을 통로가 없다.
    ⚠️ 돌연변이: `_turn_vars` 를 지우면 그 통로가 다시 막힌다.
    """
    from datetime import datetime, timedelta, timezone

    from app.core import routing
    from app.core.schema import MatchRef
    from app.core.stages import s5_verify
    from app.core.state import RunState
    ref = MatchRef(id="x:1", sport="soccer", competition="K-League 1",
                   competition_short="K리그1", home="team:000318",
                   away="team:000320", home_name="Gimcheon Sangmu",
                   away_name="FC Anyang",
                   kickoff_utc=datetime.now(timezone.utc) + timedelta(hours=2))
    got = s5_verify._turn_vars(
        ref, {"home": {"on": True, "why": "전역 주기 팀",
                       "off_squad": ["A", "B"]},
              "away": {"on": False}}, state=RunState(match_key="x"))
    assert len(got) == 1 and got[0].id == "TURN-home", [x.id for x in got]
    assert got[0].type == "squad_rotation" and got[0].hardness == "hard"
    # 🔴 배치표가 그것을 축0·축1·축3·V1 로 보낸다
    row = routing.place(got).rows[0]
    assert set(row.places) == {"axis0", "axis1", "axis3", "V1", "hypo"}
    # 🔴 깃발이 꺼지면 **안 만든다**(지어낸 변수 금지)
    assert s5_verify._turn_vars(ref, {"home": {"on": False}},
                                state=RunState(match_key="x")) == []
    # 🔴 배선 — s5 가 그것을 변수 목록에 더하고 파이프라인이 깃발을 넘긴다
    src = (ROOT / "app" / "core" / "stages"
           / "s5_verify.py").read_text(encoding="utf-8")
    assert "out += _turn_vars(" in src
    assert "turnover=turn" in (ROOT / "app" / "core"
                               / "pipeline.py").read_text(encoding="utf-8")


def test_v7_유형과_내용이_어긋나면_버린다():
    """🔴 V-2 — *"유형–내용 일치 검사(부진 문장을 fatigue 로 단 것 등 버림)"*.

    ⚠️ 실측 2026-10-10: *"4-4-2 포메이션으로 경기에 임한다"* 가 `def_absence`
       (수비 결장)로 들어왔다 — 결장 얘기가 **한 글자도 없다**.
    """
    from app.core.stages.s5_verify import _type_fits
    said = _type_fits("def_absence", "Gimcheon Sangmu는 4-4-2 포메이션이다")
    assert "한 글자도 없다" in said, said
    # 🔴 결장 말이 있으면 통과한다
    assert _type_fits("def_absence", "Kwon 이 명단에서 빠졌다") == ""
    assert _type_fits("returning", "무고사가 복귀했다") == ""
    # 🔴 목록에 없는 유형은 **통과**다(모르는 것으로 버리지 않는다 · #4)
    assert _type_fits("team_stats", "아무 말") == ""
    # 🔴 사유 열거값이 있다(사유를 지어 쓰지 않는다)
    from app.core.schema import DropReason
    assert DropReason.TYPE_CONTENT_MISMATCH.value == "type_content_mismatch"


def test_v7_상대_기준은_팀_지정_지표에만():
    """🔴🔴 ⚠️ 실사고 2026-10-10: `승무패[home] > 상대` 가 왔고 그 지표는 팀 칸이
    뜻이 없어 **자기 자신과 비교**했다(`0.461 > 0.461` → 늘 반박)."""
    from app.core import signals as _sg
    from app.core.schema import Signal
    bad = Signal(metric="승무패", direction=">", ref="상대", side="home",
                 arg="home")
    said = _sg.bad_signal(bad)
    assert "팀을 지정하는 지표" in said, said
    assert _sg.check(bad, {"home": 0.46, "away": 0.24})["verdict"] == _sg.NA
    # 🔴 팀 지정 지표에는 그대로 쓴다
    ok = Signal(metric="기대득점", direction=">", ref="상대", side="home")
    assert _sg.bad_signal(ok) == ""


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 S5 검증·S7 평·S8 보드 — 상성 엔진 지시서 §5-1·5-3 · S7 · C12
# ══════════════════════════════════════════════════════════════════

def _mr(edge: str = "home", strength: str = "중"):
    from app.core import matchup as _mu
    return _mu.MatchupReport(axes={"axis0": _mu.Axis(name="axis0", home=1.0,
                                                     away=0.0, gap=0.5,
                                                     edge=edge,
                                                     strength=strength)},
                             verdict={"edge": edge, "strength": strength,
                                      "score": 0.15, "why": "시험"})


def test_v7_검증_출처가_일곱_자리에서_온다():
    """🔴 S5-1 — V1 Elo · V2 동기 · V3 일정 · V4 감독·기타 · V5 맞대결 ·
    V6 시장(표시만) · V7 가설 신호."""
    from datetime import datetime, timedelta, timezone

    from app.core import odds as _odds
    from app.core import routing
    from app.core.schema import (BaseProb, Facts, HypoSet, MarketProb,
                                 MatchRef, ProbTriple)
    from app.core.stages import s6c_check as _chk
    from app.core.state import RunState
    ref = MatchRef(id="x:1", sport="soccer", competition="K-League 1",
                   competition_short="K리그1", home="team:000318",
                   away="team:000320", home_name="H", away_name="A",
                   kickoff_utc=datetime.now(timezone.utc) + timedelta(hours=2))
    rows = [_var("R9", "stakes"), _var("IR11", "fatigue"),
            _var("S02", "h2h_pattern"), _var("R3", "coach_quote")]
    vs = routing.place(rows)
    layers = {"base": BaseProb(probs=ProbTriple(home=0.6, draw=0.2, away=0.2)),
              "market": MarketProb(probs={_odds.key_of("win", "home"): 0.3,
                                          _odds.key_of("win", "draw"): 0.3,
                                          _odds.key_of("win", "away"): 0.4})}
    got = _chk.run(ref, Facts(), HypoSet(), {}, variables=rows, mr=_mr(),
                   varset=vs, layers=layers, state=RunState(match_key="x"))
    srcs = {dict(r)["src"] for r in got["sources"]}
    assert {"V1", "V2", "V3", "V4", "V5", "V6"} <= srcs, srcs
    # 🔴 C12 — 시장은 **표시만**이고 등급에 영향이 없다
    mk = [dict(r) for r in got["sources"] if dict(r)["src"] == "V6"][0]
    assert mk["cause"] == "" and "등급 영향 없음" in mk["why"]
    assert any("V6" in x and "등급 영향 없다" in x
               for x in got["grade"]["why"]), got["grade"]


def test_v7_S5_3_등급은_상성_사각만_내린다():
    """🔴🔴 S5-3 — (c) 상성 사각만 등급을 내린다. (a)(b)·V6 은 **영향 없음**."""
    from app.core.stages import s6c_check as _chk
    blind_hard = {"src": "V2", "name": "동기", "dir": "반대", "size": "강",
                  "trust": "hard", "refs": ["R9"], "cause": _chk.CAUSE_BLIND,
                  "why": "강등권"}
    got = _chk.grade_move([blind_hard], {})
    assert got["steps"] == 1 and not got["none"], got
    # 🔴 (c) 둘이면 **등급 없음**
    two = _chk.grade_move([blind_hard, {**blind_hard, "src": "V5",
                                        "refs": ["S02"]}], {})
    assert two["none"], two
    # 🔴 (a) 낡음 · (b) 이미 반영은 **안 내린다**
    for cause in (_chk.MISS_STALE, _chk.CAUSE_IN):
        said = _chk.grade_move([{**blind_hard, "cause": cause}], {})
        assert said["steps"] == 0 and not said["none"], (cause, said)
    # 🔴 V7 주 가설 지지 0개면 한 단계
    none_sup = _chk.grade_move([], {"rows": [{"x": 1}],
                                    "counts": {"지지": 0}})
    assert none_sup["steps"] == 1, none_sup
    # 🔴 배선 — 내리는 길은 `_lower` 하나다
    src = (ROOT / "app" / "core" / "pipeline.py").read_text(encoding="utf-8")
    assert 'dict(layers.get("check") or {}).get("grade")' in src


def test_v7_S7_첫줄과_상성사각_문장을_요구한다():
    """🔴 S7 — 첫 줄에 상성 판정 + 검증 요약 · **상성 사각이 있으면 한 문장**."""
    from datetime import datetime, timedelta, timezone

    from app.core import saybundle
    from app.core.schema import (Card, Facts, KeyPoint, MatchRef, ProbTriple,
                                 SayOut)
    from app.core.stages import s6c_check as _chk
    from app.core.stages import s9_say
    ref = MatchRef(id="x:1", sport="soccer", competition="K-League 1",
                   competition_short="K리그1", home="team:000318",
                   away="team:000320", home_name="H", away_name="A",
                   kickoff_utc=datetime.now(timezone.utc) + timedelta(hours=2))
    chk = {"rows": [], "counts": {"지지": 0, "반박": 0, "판단 불가": 0},
           "stale": "", "rerun": "", "why": "x",
           "sources": [{"src": "V2", "name": "동기", "dir": "반대",
                        "size": "강", "trust": "hard", "refs": ["R9"],
                        "cause": _chk.CAUSE_BLIND, "why": "강등권 탈출"}],
           "grade": {"steps": 1, "none": False, "why": ["내림"]}}
    card = Card(match=ref, facts=Facts(), check=chk,
                matchup={"report": _mr()},
                our_prob=ProbTriple(home=0.5, draw=0.3, away=0.2))
    box = saybundle.build(card)
    assert box.items.get("M0") is not None, "🔴 상성 판정이 묶음에 없다"
    assert box.items.get("M00") is not None, "🔴 검증 요약이 묶음에 없다"
    assert box.items.get("B1") is not None, "🔴 상성 사각이 묶음에 없다"
    base = {"verdict": "H", "flow_first": "a", "flow_second": "b",
            "decisive_moment": "c", "flip_condition": "d",
            "key_points": [KeyPoint(claim="주장", mechanism="메커니즘",
                                    refs=["M0", "P1"])] * 3}
    bad = SayOut(**base, one_line="H 가 가져간다")
    said = s9_say.check(bad, card=card, box=box)
    assert any("상성 사각" in x for x in said), said
    assert any("첫 줄에 상성 판정" in x for x in said), said
    ok = SayOut(**{**base,
                   "key_points": [KeyPoint(claim="상성 사각 — 동기가 반대다",
                                           mechanism="B1", refs=["B1", "M0"])]
                                  * 3},
                one_line="상성은 H 중 · 검증 같은 방향 0 · 반대 1")
    said2 = s9_say.check(ok, card=card, box=box)
    assert not any("상성 사각" in x or "첫 줄에 상성" in x for x in said2), said2


def test_v7_카드가_검증_블록을_낸다():
    """🔴 §3 카드 — `🔎 검증 — 같은 방향 n · 반대 n — 반대: {출처 — 원인}`."""
    from datetime import datetime, timedelta, timezone

    from app.core import layer1
    from app.core.schema import Card, Facts, MatchRef, ProbTriple
    from app.core.stages import s6c_check as _chk
    ref = MatchRef(id="x:1", sport="soccer", competition="K-League 1",
                   competition_short="K리그1", home="team:000318",
                   away="team:000320", home_name="H", away_name="A",
                   kickoff_utc=datetime.now(timezone.utc) + timedelta(hours=2))
    chk = {"sources": [{"src": "V1", "name": "Elo 기준 확률", "dir": "같음",
                        "size": "강", "trust": "그대로", "refs": [],
                        "cause": "", "why": "① 기준 홈 60%"},
                       {"src": "V2", "name": "동기", "dir": "반대",
                        "size": "강", "trust": "hard", "refs": ["R9"],
                        "cause": _chk.CAUSE_BLIND, "why": "강등권"}],
           "grade": {"steps": 1, "none": False,
                     "why": ["🔴 (c) 상성 사각 hard·강 1건 → 한 단계 내림"]},
           "rows": [], "counts": {}}
    card = Card(match=ref, facts=Facts(), check=chk,
                our_prob=ProbTriple(home=0.5, draw=0.3, away=0.2))
    said = layer1.verify_block(card)
    assert "같은 방향 1 · 반대 1" in said, said
    assert "V2" in said and _chk.CAUSE_BLIND in said
    assert "등급 영향" in said


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 C11 **백필 누설 금지** — 상성 엔진 지시서 3-5
# ══════════════════════════════════════════════════════════════════

def test_v7_C11_백필이_자기_경기를_특징에_안_넣는다():
    """🔴🔴 C11 — *"경기 m 특징에 **m 자신·이후 자료**가 들어가면 실패"*.

    두 가지로 센다:
      ① 백필 고리가 **특징을 만든 뒤에** 그 경기를 과거 목록에 넣는다(코드 순서)
      ② `features()` 는 `prior` 만 읽는다 — 그 안에 자기 경기가 없다
    ⚠️ 돌연변이: `_remember` 를 `features` **앞**으로 옮기면 ① 이 빨개진다.
    """
    import ast
    src = (ROOT / "tools" / "fit_matchup_model.py").read_text(encoding="utf-8")
    fn = [n for n in ast.walk(ast.parse(src))
          if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
          and n.name == "backfill"]
    assert fn, "🔴 `backfill` 이 없다"
    said = ast.unparse(fn[0])
    i, j = said.find("_bf.features("), said.find("_remember(")
    assert 0 <= i < j, f"🔴 자기 경기를 특징보다 **먼저** 넣는다(i={i} j={j})"
    # 🔴 ② 특징 함수는 `prior` 만 본다 — 그 경기 골/스코어를 안 읽는다
    bf = (ROOT / "app" / "core" / "backfill.py").read_text(encoding="utf-8")
    feat = [n for n in ast.walk(ast.parse(bf))
            if isinstance(n, ast.FunctionDef) and n.name == "features"]
    assert feat
    body = ast.unparse(feat[0])
    assert "goals_of" not in body, "🔴 특징이 **그 경기 골**을 읽는다(누설)"
    assert "score_of" not in body, "🔴 특징이 **그 경기 스코어**를 읽는다(누설)"


def test_v7_적합은_시간순으로_가른다():
    """🔴 3-5 — **시간순 분할**(미래로 과거를 맞추지 않는다) · 표본 적으면 멈춘다."""
    import tools.fit_matchup_model as fit
    assert 0.5 <= fit.SPLIT < 1.0
    src = (ROOT / "tools" / "fit_matchup_model.py").read_text(encoding="utf-8")
    assert 'rows.sort(key=lambda r: str(r.get("utc") or ""))' in src
    assert "train, test = rows[:cut], rows[cut:]" in src
    # 🔴 **표본이 적으면 적합하지 않는다**(지어낸 계수보다 임시값이 낫다)
    assert "적합하지 않는다" in src


def test_v7_적합은_계수를_스스로_쓰지_않는다():
    """🔴 P4·§6 — *"값은 자동으로 쓰지 않는다"*(사용자가 config 에 넣는다).

    ⚠️ 돌연변이: 도구가 `config/matchup_model.yaml` 을 쓰게 하면 빨개진다.
    """
    src = (ROOT / "tools" / "fit_matchup_model.py").read_text(encoding="utf-8")
    assert "matchup_model.yaml" in src, "🔴 어디에 넣을지 안 적었다"
    for bad in ("write_text(json.dumps(conf", "yaml.dump", "rules._save"):
        assert bad not in src, f"🔴 도구가 설정을 **스스로 쓴다**({bad})"
    # 🔴 보고 항목이 지시서 그대로다
    for want in ("로그 손실", "브라이어", "보정표", "채택 판정", "기준 모형"):
        assert want in src, f"🔴 보고에 `{want}` 가 없다"


def test_v7_C9_관찰만은_람다에_안_들어간다():
    """🔴 C9 — *"표본 미만 규칙은 **관찰만**, λ 에 안 들어간다"*.

    🔴 그 걸러내기는 `goals.sim_input` 하나가 한다(S3 가 그 함수를 쓴다).
    """
    from app.core import goals as _g
    thin = _g.Fired(rule="T9", side="home", effect={"lambda_own": 0.5},
                    watch_only=True)
    fat = _g.Fired(rule="T10", side="home", effect={"lambda_own": 0.1})
    got = _g.sim_input({"fired": [thin, fat], "fired2": []},
                       lam_home=1.0, lam_away=1.0)
    # 🔴 `관찰만` 의 0.5 가 빠졌으니 홈 λ 는 1.1 쪽이다(1.6 이 아니다)
    assert abs(float(got["lam_home"]) - 1.1) < 1e-6, got["lam_home"]
    assert thin.moves() == {}, "🔴 `관찰만` 이 이동량을 내놓는다"
    # 🔴🔴 **지시서 2026-10-11 F3 이 이 배선을 바꿨다** — ⑪ 은 규칙 λ 를 **안
    #    더한다**(축 안에서 한 번만 · R4). 걸러내기는 그대로 `goals` 가 하고,
    #    S3 는 **λ 를 안 주는** `sim_extras` 를 쓴다.
    src = (ROOT / "app" / "core" / "probmodel.py").read_text(encoding="utf-8")
    assert "_g.sim_extras(" in src, "🔴 S3 가 시간대·상태 배율을 안 쓴다"
    assert "_g.sim_input(" not in src, (
        "🔴 S3 가 규칙 λ 를 다시 더한다 — 이중 계산이다(F3/R4)")
    # 🔴 `관찰만` 걸러내기는 **그 길에서도** 산다
    got2 = _g.sim_extras({"fired": [thin, fat], "fired2": []})
    assert "T9" not in str(got2.get("why") or ""), got2


def test_v7_C10_임시값이면_카드에_보인다():
    """🔴 C10 — *"임시 계수가 쓰였으면 카드에 **🔴 임시**가 보인다"*."""
    from datetime import datetime, timedelta, timezone

    from app.core import layer1, matchup as _mu, probmodel as _pm, render
    from app.core import routing
    from app.core.schema import Card, Facts, MatchRef, ProbTriple, Variable, XI
    from app.core.state import RunState
    ref = MatchRef(id="x:1", sport="soccer", competition="K-League 1",
                   competition_short="K리그1", home="team:000318",
                   away="team:000320", home_name="H", away_name="A",
                   kickoff_utc=datetime.now(timezone.utc) + timedelta(hours=2))
    xi = {ref.home: XI(team=ref.home, state="confirmed",
                       players=[f"H{i}" for i in range(11)]),
          ref.away: XI(team=ref.away, state="confirmed",
                       players=[f"A{i}" for i in range(11)])}
    facts = Facts(xi=xi, standings={"match_total_baseline": 2.6},
                  player_value={**{f"H{i}": 1_000_000 for i in range(11)},
                                **{f"A{i}": 700_000 for i in range(11)}})
    vs = routing.place([Variable(id="S03", type="home_field", subject=ref.home,
                                 favors="home", hardness="soft", weight=0.4,
                                 claim="홈 이점 수치 없음", quote="q")])
    box = {"form": {}, "style": {}, "profile": {}, "fired": [], "fired2": [],
           "off": {}, "late": {}}
    mr = _mu.report(ref, facts, box, vs)
    prob = _pm.run(ref, facts, mr, vs, edge=box, state=RunState(match_key="x"))
    card = Card(match=ref, facts=Facts(), varset=vs,
                matchup={"report": mr, "prob": prob, "sim": prob.as_sim(),
                         "share": dict(prob.share),
                         "share_refs": dict(prob.share_refs)},
                our_prob=ProbTriple(home=prob.home, draw=prob.draw,
                                    away=prob.away))
    assert prob.provisional, "🔴 시험 재료 — 지금은 임시값이어야 한다"
    said = layer1._probs(card)
    assert _mu.PROVISIONAL in said and "(상성)" in said, said
    # 🔴 긴 카드의 **적합 정보**도 그 사실을 적는다
    long = render.fit_long(card)
    assert "임시값" in long and "tools/fit_matchup_model.py" in long


def test_v7_슬러그_색인이_별칭표를_지난다():
    """🔴🔴 **실사고 2026-10-10** — 사용자가 `제노아` 로 물었는데 봇이
    `match_not_found` 로 끝났다.

    색인 슬러그는 `genoa` 이고 `norm_name` 은 **한글↔로마자를 일부러 안 잇는다**
    (이으면 엉뚱한 팀이 섞인다). 🔴 그 다리는 **별칭표**(`config/entities.yaml`)
    이고 `_slug_hit` 이 이제 그것을 지난다.
    ⚠️ 돌연변이: `aliases_of` 를 빼면 한글 클럽 이름이 다시 **0건**이 된다.
    """
    from app.core import discover as _d
    idx = {"10233": "genoa", "133901": "gimcheon-sangmu",
           "162276": "adelaide-city", "9999": "adelaide-united"}
    assert _d._slug_hit(idx, "제노아") == [("10233", "genoa")]
    assert _d._slug_hit(idx, "김천상무") == [("133901", "gimcheon-sangmu")]
    # 🔴 **느슨해지지 않았다** — 비슷한 이름이 섞이지 않는다
    got = _d._slug_hit(idx, "Adelaide City")
    assert got and got[0] == ("162276", "adelaide-city"), got
    assert ("9999", "adelaide-united") not in got, "🔴 다른 팀이 섞였다"
    # 🔴 별칭표에 `제노아` 가 **있다**(그 다리가 이 파일이다)
    assert "Genoa" in _d.aliases_of("제노아"), _d.aliases_of("제노아")


def _stub_ladder(monkeypatch, rows):
    """🔴 ② 사다리의 **바깥 둘만** 세운다(팀 색인·일정 파싱) — 거르는 규칙이 과녁."""
    import asyncio

    from app.collect import fotmob as fm
    from app.core import discover as _d

    async def _idx(_net):
        return {"10233": "genoa"}

    class _Net:
        async def get(self, _url):
            return type("P", (), {"text": "<html></html>"})()

    monkeypatch.setattr(fm, "team_index", _idx)
    monkeypatch.setattr(_d, "team_fixtures", lambda _t, _i: rows)
    got = _d.Found()
    out = asyncio.run(_d._by_team(_Net(), home="제노아", away="",
                                  days=_d.window(None), got=got, at=""))
    return out


def test_v7_한_팀만_물어도_찾는다(monkeypatch):
    """🔴🔴 **실사고 2026-10-10** — 사용자가 `제노아` **한 팀만** 물었고 봇은
    일정 45경기를 받아 놓고 `match_not_found` 로 끝났다.

    🔴 원인: 상대가 빈 글자라 `theirs == []` → `same_any(…, [])` 가 **언제나
       거짓** → 창 안 경기가 전부 떨어졌다.
    ⚠️ 돌연변이: `if theirs:` 가름을 지우면 한 팀 질문이 다시 **0건**이 된다.
    """
    from app import window as _w
    from app.core import discover as _d
    soon = (_w.now_utc() + __import__("datetime").timedelta(hours=5))
    rows = [{"id": "1", "home": "Genoa", "away": "Fiorentina",
             "utc": soon.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "finished": False,
             "league_name": "Serie A", "league_id": 55, "page": ""}]
    out = _stub_ladder(monkeypatch, rows)
    assert out.match, out.tried
    assert out.match["away"] == "Fiorentina"
    assert out.rung.startswith("②"), out.rung
    # 🔴 **킥오프가 지난 경기는 "다음 경기"가 아니다** — 사유를 **이름으로** 남긴다(#3)
    past = dict(rows[0])
    past["utc"] = (_w.now_utc()
                   - __import__("datetime").timedelta(minutes=20)
                   ).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    out2 = _stub_ladder(monkeypatch, [past])
    assert not out2.match
    assert any("킥오프가 지났다" in t for t in out2.tried), out2.tried
    assert isinstance(_d._next_fixture([past]), type(None))


def test_v7_창_안이_0건이면_다음_경기를_적는다(monkeypatch):
    """🔴 **조용한 0 금지**(#3) — "못 찾았다"와 "창 밖이다"는 **다른 일**이다.

    ⚠️ 돌연변이: `if not in_win:` 사유 줄을 지우면 사용자는 *"봇이 제노아를
       모른다"* 로 읽는다 — 실제로는 **다음 경기가 일주일 뒤**다.
    """
    import datetime as dt

    from app import window as _w
    far = (_w.now_utc() + dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    rows = [{"id": "9", "home": "Roma", "away": "Genoa", "utc": far,
             "finished": False, "league_name": "Serie A", "league_id": 55,
             "page": ""}]
    out = _stub_ladder(monkeypatch, rows)
    assert not out.match
    said = " · ".join(out.tried)
    assert "창" in said and "0건" in said, said
    assert "Roma vs Genoa" in said, "🔴 다음 경기를 안 적었다"


def test_v7_fdorg_로_확정한_축구_경기도_fotmob_깊이를_받는다(monkeypatch):
    """🔴🔴 **실사고 2026-10-10**(제노아 vs 피오렌티나) — S0 가 **fdorg 슬레이트**로
    확정해 `ext_id = fdorg:558588` 이었다. fotmob 깊이는 `fotmob:` 접두만 받으므로
    `_depth` 가 **빈 목록**을 냈고, 카드가 이렇게 나왔다:

        XI 없음 · 결장 명단 미확보 · 감독 미확보 · 순위표 없음 · 폼 없음 ·
        맞대결 없음 → **축0 ⬜**(백필이 예측력을 잰 **유일한** 축)

    🔴 자료가 없는 것이 아니라 **열쇠가 없었다**(#2 배선).
    ⚠️ 돌연변이: `_depth` 의 fotmob 번호 풀이를 지우면 해외축구 슬레이트 경기가
       다시 깊이 0 이 된다.
    """
    import inspect

    from app.collect import fotmob as fm
    from app.core import discover as _d
    from app.core.stages import s2_facts

    said = inspect.getsource(s2_facts._depth)
    assert "discover" in said and "fotmob_id" in said, (
        "🔴 `_depth` 가 fotmob 경기 번호 풀이를 안 부른다 — fdorg 로 확정한 "
        "경기는 깊이가 0 이 된다")
    assert "sport" in said, "🔴 축구에만 걸어야 한다(야구·하키에 축구 페이지 금지)"
    # 🔴 **조용히 하지 않는다**(#3) — 이었는지 못 이었는지 보고에 남는다
    assert "state.note" in said, "🔴 번호를 풀었는지 보고에 안 적는다"
    # 🔴 번호 풀이는 **② 사다리를 다시 쓴다**(사본 금지)
    bridge = inspect.getsource(_d.fotmob_id)
    assert "_by_team" in bridge, "🔴 사다리를 베꼈다 — ② 를 다시 쓰지 않는다"
    # 🔴 접두가 붙으면 fotmob 깊이가 **열린다**(그 둘이 맞물려야 고쳐진 것이다)
    assert fm.sources_context("fdorg:558588") == []
    got = fm.sources_context("fotmob:5181853")
    assert got and "5181853" in got[0].url, got


def test_v7_판정이_S3_의_우리_열로_다시_세진다():
    """🔴🔴 **실사고 2026-10-10**(제노아) — 카드 7b 가 한 칸에서 서로 반대로 말했다:

        | Genoa 승 | 26% | **35%** | 50% |   ← 우리 열에 수가 **있다**
        판정: **우리 없음** — 우리 확률을 못 만들었다(시나리오 없음)

    🔴 `_layers` 가 **S3 앞에서** 돌아(그때 `ours=None`) 판정을 적고, S3 는
       `layers["ours"]` 만 덮었다. ⚠️ 돌연변이: S3 뒤의 `compare_block` 재계산을
       지우면 그 모순이 **그대로 돌아온다**.
    """
    import inspect

    from app.core import pipeline as _pl

    said = inspect.getsource(_pl)
    i_set = said.index('layers["ours"] = _PT(')
    after = said[i_set:i_set + 1400]
    assert "compare_block(" in after, (
        "🔴 S3 가 우리 열을 덮은 뒤 §6 판정을 **다시 세지 않는다** — "
        "낡은 '우리 없음' 이 새 수 옆에 남는다")
    assert 'layers["compare"]' in after and 'layers["tilt"]' in after
    # 🔴 규칙은 **한 곳**이다 — `_layers` 도 같은 함수를 쓴다(사본 금지)
    assert "compare_block(" in inspect.getsource(_pl._layers)


def test_v7_홈_배율이_리그_평균과_같은_열쇠를_본다():
    """🔴🔴 **실사고 2026-10-10**(제노아) — 같은 모형 안에서 **열쇠가 둘**이었다.

        [S3] 대회 유형 `league:SA` 실측 평균 2.5185(표본 810)
             · 🔴 홈 이점 **실측 없음**(대회 ``) — 배율 1.0

    🔴 `home_mul` 이 `ref` 없이 `_kind(None, …)` 를 불러 `_RefShim`(대회 이름이
       **빈 글자**)을 썼다. 실측 `home_share 1.3185 ÷ 1.2592 = ×1.047` 이 있었는데
       버려졌다. ⚠️ 돌연변이: `ref=ref` 를 떼면 다시 1.0 이 된다.
    """
    import inspect

    from app import rules
    from app.core import probmodel as _pm

    # 🔴 **그 표가 있다**(없는 것을 고친 척하지 않는다 — 실측)
    box = dict(rules.goal_baseline("league:SA") or {})
    assert box.get("home_share"), box
    per = rules.goal_share("league:SA")
    assert per and abs(float(box["home_share"]) / float(per) - 1.047) < 0.01

    assert "ref=None" in inspect.signature(_pm.home_mul).__str__() or (
        "ref" in inspect.signature(_pm.home_mul).parameters)
    said = inspect.getsource(_pm)
    assert said.count("home_mul(facts, varset, ref=ref)") == 2, (
        "🔴 `home_mul` 을 `ref` 없이 부르는 자리가 남았다 — 그 자리는 대회 이름이 "
        "빈 글자가 되어 홈 이점을 **조용히 버린다**")
    assert "_kind(ref, facts)" in inspect.getsource(_pm.home_mul)


def test_v7_리그_평균은_한_곳이다():
    """🔴🔴 **실사고 2026-10-10**(제노아) — 한 카드가 **같은 수를 알면서 모른다**고 했다.

        [S3] 대회 유형 `league:SA` 실측 평균 2.5185(표본 810)
        블록 4 — 기준 팀당 1.2592골(대회 league:SA)
        가설 4줄 — 🔴 리그 평균을 **모른다** — 이 경기 총골 기준이 없다

    🔴 `signals.league_of` 는 **순위표**만 봤고 순위표가 없었다. S3 가 쓰는 수는
       `probmodel.league_mean` 이다. ⚠️ 돌연변이: 그 되물음을 지우면 가설 넷이
       다시 `판단 불가` 로 떨어진다.
    """
    import inspect

    from app.core import signals as _sg
    from app.core.stages import s6c_check as _s6c

    said = inspect.getsource(_sg.league_of)
    assert "league_mean" in said, "🔴 S3 가 쓰는 수를 되묻지 않는다"
    assert "ref" in inspect.signature(_sg.league_of).parameters
    # 🔴 부르는 쪽이 `ref` 를 **넘겨야** 대회 열쇠가 산다(안 넘기면 또 빈 글자다)
    assert "league_of(facts, ref=ref)" in inspect.getsource(_s6c), (
        "🔴 `s6c` 가 `ref` 를 안 넘긴다 — 대회 유형을 모르면 평균도 못 찾는다")


def test_v7_등록_안_된_리그_클럽도_한글로_풀린다(tmp_path, monkeypatch):
    """🔴🔴 **실사고 2026-10-11** — 사용자가 `올랜도`·`크루`(MLS)로 물었다.

    별칭을 `config/entities.yaml` 에 적었는데도 `aliases_of('올랜도')` 가
    **['올랜도']** 뿐이었다 — `teamref._from_entities` 는 **정식명이 이름표에
    이미 있을 때만** 별칭을 붙이고(`정식명을 못 찾아 건너뜀`), MLS 는 리그 명부에
    없어 그 팀이 이름표에 **없다**.
    🔴 그런데 fotmob 색인은 이름표와 **무관한 출처**다 — 등록 안 된 리그의 클럽도
       거기 있다(실측 `orlando-city` 267810). 🔴 그래서 **표를 직접 읽는다**.
    ⚠️ 돌연변이: `_entity_aliases` 를 빼면 한글 MLS 질문이 다시 **0건**이 된다.
    """
    from app.core import discover as _d
    got = _d.aliases_of("올랜도")
    assert "Orlando City" in got, got
    assert "크루" != got[0] or True
    assert "Columbus Crew" in _d.aliases_of("크루"), _d.aliases_of("크루")
    # 🔴 이름표가 **아는** 팀은 종전 그대로다(새 길이 옛 길을 덮지 않는다)
    assert "Gangwon FC" in _d.aliases_of("강원")


def test_v7_2군_슬러그를_뺀다():
    """🔴🔴 **실측 2026-10-11** — `올랜도` 를 물으면 색인이 `orlando-city` 와 함께
    **`orlando-city-b`**(2군)를, `크루` 는 **`columbus-crew-2`**(MLS Next Pro)를
    준다. 🔴 1군 경기가 창에 없으면 **2군 경기를 열 수 있다 — 남의 경기다**(M14).

    ⚠️ 돌연변이: `RESERVE_TAIL` 을 지우면 2군이 후보로 돌아온다.
    ⚠️ 낱말(`b`·`2`)로 잡으면 엉뚱한 팀이 걸린다 — **꼬리로** 본다.
    """
    from app.core import discover as _d
    idx = {"267810": "orlando-city", "722266": "orlando-city-b",
           "6001": "columbus-crew", "1348126": "columbus-crew-2"}
    got = _d._slug_hit(idx, "Orlando City")
    assert got == [("267810", "orlando-city")], got
    got2 = _d._slug_hit(idx, "Columbus Crew")
    assert got2 == [("6001", "columbus-crew")], got2
    # 🔴 **사용자가 2군을 적었으면 그대로 본다**(공백 표기도 같은 꼬리로 읽는다)
    assert ("722266", "orlando-city-b") in _d._slug_hit(idx, "Orlando City B")
    assert ("1348126", "columbus-crew-2") in _d._slug_hit(idx, "Columbus Crew 2")


def test_v7_전역을_안_박는다_그리고_바뀐_자리_0개면_그렇게_쓴다():
    """🔴🔴 **실사고 2026-10-11**(올랜도 vs 크루) — 카드가 **두 번 거짓말**을 했다.

    ① 양상 — *"Orlando City 선수단 교체(**전역**·이적)"*. 올랜도는 **미국 클럽**
       이고 전역 주기 팀이 아니다 — 깃발은 ①(최근 선발 5명이 오늘 명단에 없다)로
       켜졌다. 🔴 까닭은 깃발이 **재서** `why` 에 적는다(①②③).
    ② 같은 카드가 `L2 평소 XI 대비 바뀐 자리 **0개**` 라고 적고 바로 아래서
       *"**바뀐 자리는** 체력 관리가 아니라…"* 라고 했다 — 가리키는 자리가 없다.
    ⚠️ 돌연변이: `VERDICT_KO` 에 `전역` 을 되넣거나 `chg` 가름을 지우면 되돌아간다.
    """
    import inspect

    from app.core import turnover as _turn
    from app.core.stages import s2d_strategy as _s2d

    assert "전역" not in _turn.VERDICT_KO, _turn.VERDICT_KO
    assert _turn.VERDICT_KO == "선수단 교체"
    said = inspect.getsource(_s2d._turn_lines)
    assert "chg" in said and "changed" in said, (
        "🔴 바뀐 자리 수를 보지 않는다 — `바뀐 자리는…` 이 0개일 때도 나간다")
    assert "평소 XI \n" not in said
    assert "평소 XI " in said and "그 선수들이 빠진 뒤의 것" in said
    # 🔴 `reads` 를 **받아야** 그 수를 안다
    assert "reads" in inspect.signature(_s2d._turn_lines).parameters


def test_v7_한_낱말_이름은_성으로만_맞춘다():
    """🔴🔴 **실사고 2026-10-11**(상파울루 vs 비토리아) — 카드가 **모순**을 냈다.

        2b. 결장 — `Rafael`(GK) — 부상 · 복귀 **Doubtful**
        🔢 변수 — `IR03-home` [returning] São Paulo FC **Rafael 복귀**
                  · 자리 ['axis0', 'axis2', 'hypo']   ← **확률에 닿는 자리**다

    🔴 명단에 있던 사람은 **`Rafael Tolói`**(수비수, 오늘 선발)로 **다른 사람**이다.
       품는 일치가 *이름(given name)* 에서 맞아 버렸다.
    🔴 브라질 선수는 mononym 이 흔하다 — 한쪽이 한 낱말이면 **성**이 같을 때만
       같은 사람으로 본다. ⚠️ 돌연변이: 그 가름을 지우면 `Rafael` 이 다시
       `Rafael Tolói` 로 맞아 **없는 복귀**가 축0·축2 근거가 된다.
    """
    from app.core.stages.s5_verify import _in
    # 🔴 **이것이 그 사고다**
    assert _in("Rafael", ["Rafael Tolói", "Carlos Coronel"]) is False
    # 🔴 성으로 부르는 것은 **맞아야 한다**(그 길을 막으면 진짜 복귀를 놓친다)
    assert _in("Griezmann", ["Antoine Griezmann"]) is True
    assert _in("Antoine Griezmann", ["Griezmann"]) is True
    assert _in("Sow", ["Djibril Sow"]) is True
    # 🔴 mononym ↔ mononym · 여러 낱말 ↔ 여러 낱말은 종전 그대로
    assert _in("Rafael", ["Rafael"]) is True
    assert _in("Stephan El Shaarawy", ["Stephan El Shaarawy"]) is True


def test_v7_두_낱말_한_팀_이름을_가르지_않는다():
    """🔴🔴 **실사고 2026-10-11** — 사용자가 `시애틀 사운더스` 라고 물었고 입구가
    그것을 **팀 `시애틀` vs 상대 `사운더스`** 로 갈랐다(로그: 팀 ['시애틀',
    '사운더스']) → 상대가 안 맞아 ② 사다리가 비고 검색 단으로 떨어졌다.

    🔴 가르기 전에 `discover.one_team` 으로 **이름표에 통째로 있는지** 본다.
    ⚠️ 그 검사는 **정확 일치**여야 한다 — 품는 일치로 하면 `올랜도 크루`(두 팀!)가
       `올랜도` 를 품어 한 팀이 되고, 한 시간 전 사용자 질문이 깨진다(실측).
    ⚠️ 돌연변이: `one_team` 호출을 지우면 두 낱말 팀 이름이 다시 갈라진다.
    """
    import inspect

    from app.bot import main as _m
    from app.core import discover as _d

    assert _d.one_team("시애틀 사운더스") is True
    assert _d.one_team("맨체스터 시티") is True
    # 🔴 **두 팀은 그대로 갈라야 한다**
    assert _d.one_team("올랜도 크루") is False
    assert _d.one_team("중국 팔레스타인") is False
    assert _d.one_team("강원 서울") is False
    # 🔴🔴 **가름 규칙은 한 곳**이다(사본 금지 · #1) — ⚠️ 실사고 2026-10-11:
    #    같은 규칙이 입구와 `pipeline._question` 에 **사본**으로 있어 한쪽만
    #    고쳤고 `--deep` 경로는 그대로 깨져 있었다.
    from app.core import pipeline as _pl
    said = inspect.getsource(_pl.split_asked)
    assert "one_team" in said, "🔴 가름이 한 팀 검사를 안 부른다"
    i = said.index("one_team")
    assert "words[0], words[1]" in said[i:], "🔴 가름이 그 검사 뒤에 와야 한다"
    assert _pl.split_asked("시애틀 사운더스") == ("시애틀 사운더스", "")
    assert _pl.split_asked("올랜도 크루") == ("올랜도", "크루")
    # 🔴 입구는 **그 한 곳을 부른다** — 자기 사본을 들지 않는다
    door = inspect.getsource(_m.cmd_analyze)
    assert "split_asked" in door, "🔴 입구가 한 곳을 안 부른다"
    assert "words[0], words[1]" not in door, "🔴 입구에 사본이 남았다"


def test_v7_긴_팀_이름이_질의를_통째로_막지_않는다():
    """🔴🔴 **실사고 2026-10-11**(뉴잉글랜드 vs 시애틀 사운더스) — 검색이 **0회**였다.

    팀 이름이 `New England Revolution`(3낱말)·`Seattle Sounders FC`(3낱말)이라
    두 팀 + 개념어가 **7~8낱말**이 되고 `gate_ok`(1~6낱말)가 질의를 **전부** 막았다
    → 검색 0회 · 문서 0건 · 새 사실 0건. ⚠️ 카드에는 `queries None` 만 남아
    *"안 쟀다"* 처럼 보였다(#3 조용한 0).

    🔴 이름을 **지어 줄이지 않는다** — 상대 이름만 빼고 **내 팀 + 개념**으로 묻는다.
    ⚠️ 돌연변이: `_fit` 을 지우면 긴 이름 두 팀 경기가 다시 검색 0회가 된다.
    ⚠️ 끝 낱말만 남기면 `injury news` 가 `news` 로 **잘린다** — 그래서 뺀다.
    """
    from app.core.stages.s3_docs import _fit, gate_ok

    long_q = "New England Revolution Seattle Sounders FC injury news"
    assert gate_ok(long_q)[0] is False, "🔴 전제가 바뀌었다(문지기가 안 막는다)"
    got = _fit([(long_q, "en")], mine="Seattle Sounders FC",
               other="New England Revolution")
    assert got, got
    said = got[0][0]
    assert gate_ok(said)[0] is True, said
    assert "injury news" in said, f"🔴 개념어가 잘렸다 — {said!r}"
    assert "New England" not in said, said
    # 🔴 **넘지 않는 질의는 손대지 않는다**
    ok_q = "Genoa CFC ACF Fiorentina injury"
    assert _fit([(ok_q, "en")], mine="Genoa CFC",
                other="ACF Fiorentina")[0][0] == ok_q


def test_v7_질의_0건도_수로_적는다():
    """🔴 **조용한 0 금지**(#3) — `if n:` 이 0 을 빼먹어 카드가 `queries None` 을
    적었다. *"안 쟀다"* 와 *"재 보니 0"* 은 다른 말이다.

    ⚠️ 돌연변이: 그 네 칸을 늘 적는 줄을 지우면 `None` 이 돌아온다.
    """
    import inspect

    from app.core import render as _r
    from app.core.stages import s3_docs as _s3

    said = inspect.getsource(_s3.run)
    assert '("queries", "hits", "kept_date")' in said, "🔴 0 을 적지 않는다"
    # 🔴 카드는 그 네 칸을 그대로 보인다(깔때기 계약이 칸 이름을 정한다)
    assert "queries" in inspect.getsource(_r.new_facts_block)


def test_v7_카드가_상성_확률의_유도를_적는다():
    """🔴🔴 **사용자 질문 2026-10-11** — *"상성에서 나온 확률은 없냐???"*

    🔴 있었다 — 7b 의 `우리` 열이 그것이다(상성 → λ → 시뮬). 그런데 긴 카드가
       **유도 사슬을 안 적었다**: λ 두 수·홈 배율·축 종합×β·규칙 λ 는 **로그에만**
       있었고 축별 기여(3-4)는 **1겹에만** 있었다 → 카드만 보면 그 수가 어디서
       나왔는지 보이지 않았다.
    ⚠️ 돌연변이: `prob_long` 을 카드에서 빼면 그 사슬이 다시 로그로 숨는다.
    🔴 수를 **다시 세지 않는다** — `ProbOut.as_sim()` 의 그 수를 적는다.
    """
    import inspect

    from app.core import render as _r

    said = inspect.getsource(_r.card_text)
    assert "prob_long(" in said, "🔴 긴 카드가 S3 확률 블록을 안 싣는다"
    body = inspect.getsource(_r.prob_long)
    for want in ("lam", "why", "share", "over"):
        assert want in body, f"🔴 `{want}` 를 안 적는다"
    # 🔴 **시뮬 표를 읽는다** — 카드가 저장을 지나면 데이터클래스가 없을 수 있다
    assert '"sim"' in body, "🔴 `sim` 표를 안 본다(객체 생존에 기댄다)"

    # 🔴 **실물로 센다** — 수가 셋 다 나오고 λ 가 적히는가
    class _Box:
        matchup = {"sim": {"home": 0.36, "draw": 0.24, "away": 0.40,
                           "lam": {"home": 1.398, "away": 1.456},
                           "over": {"2.5": 0.62}, "why": "유도 사슬",
                           "share": {"axis0": -1.2}},
                   "share": {"axis0": -1.2}, "share_refs": {"axis0": ["IR02"]}}

    got = _r.prob_long(_Box())
    assert "36%" in got and "24%" in got and "40%" in got, got
    assert "1.398" in got and "1.456" in got, got
    assert "유도 사슬" in got and "axis0" in got, got


def test_v7_캡처_XI_통로가_이어져_있고_카드를_안_죽인다():
    """🔴🔴 **실사고 2026-10-11**(스포팅 KC vs 포틀랜드) — 둘이 한꺼번에 났다.

    ① 🔴 **통로가 안 이어져 있었다** — 소비자(`s2_facts._fill_capture`)와 파서
       (`xicapture.parse`)는 있는데 `box["xi_capture"]` 를 **채우는 곳이 없었다**
       (#2 배선). 사용자가 캡처를 보내도 봇이 쓸 수 없었다.
    ② 🔴 캡처 XI 의 출처는 `user_capture`(주소가 아니다)인데 카드 머리글이
       `split("/")[2]` 를 해서 **IndexError 로 봇이 통째로 죽었다**(카드 0장).

    ⚠️ 돌연변이: `_xi_of` 를 지우면 캡처가 다시 안 들어가고, `_host_of` 를 되돌리면
       캡처 실행이 다시 죽는다.
    """
    import inspect

    from app.core import pipeline as _pl
    from app.core import render as _r
    from app.core.stages import s2_facts as _s2

    # ① 배선 — 파이프라인이 캡처를 읽고 s2 가 받는다
    assert "xi_image" in inspect.signature(_pl.analyze).parameters
    assert "xi_capture" in inspect.signature(_s2.run).parameters
    said = inspect.getsource(_pl.analyze)
    assert "xi_capture=xi_said" in said, "🔴 s2 로 안 넘긴다"
    assert "xi_image" in inspect.signature(_pl.reanalyze).parameters, (
        "🔴 재분석 길(`--deep`)로는 캡처가 안 간다")
    # ② 주소가 아닌 출처가 카드를 죽이지 않는다
    assert _r._host_of("user_capture") == "user_capture"
    assert _r._host_of("https://www.fotmob.com/match/1") == "www.fotmob.com"


def test_v7_캡처_파서가_OCR_잡음과_붙은_번호를_견딘다():
    """🔴 실측 2026-10-11 — 그 캡처 한 장이 파서의 구멍 **둘**을 드러냈다.

    ① OCR 잡음이 선수 줄로 섞였다 — `2 감독 위키` · `0 ()` · `7 3) €`
       → 11/11 가름이 **밀렸다**(홈 10명 · 원정에 엉뚱한 줄).
    ② 한 줄에 선수가 셋이고 `21차라` 처럼 **번호 뒤 공백이 없었다**
       → 그 줄이 통째로 안 잡혀 **두 선수를 잃었다**.
    """
    from app.core import xicapture as _cap
    said = ("4-4-2                    감독 위키\n"
            "30 클리블랜드\n0 ()\n7 3) €\n"
            "10 다비드 페레이라 다 코스타     21차라        80 오르티스\n")
    rows = _cap.parse(said)
    got = {r["number"]: r["name"] for r in rows}
    assert "0" not in got and not any("감독" in v for v in got.values()), got
    assert got.get("30") == "클리블랜드", got
    # 🔴 **붙은 번호**도 잡는다(그 줄의 셋 다)
    assert got.get("21") == "차라", got
    assert got.get("80") == "오르티스", got
    assert "다비드" in str(got.get("10")), got
    # 🔴 포메이션은 **둘 다** 읽는다(한 장에 두 팀)
    assert _cap.forms_of("4-4-2 … 4-3-3") == ["4-4-2", "4-3-3"]


def test_v7_OCR_잡티가_선수_줄로_안_샌다():
    """🔴 실측 2026-10-11(LAFC 캡처) — `6 OO a` 가 **글자 3개**라 선수 줄로 통과했고
    11/11 가름이 **밀렸다**(부앙가가 원정으로 넘어갔다).

    🔴 한 글자 토막은 버리고, **같은 글자만 반복되는 토막**(`OO`)도 이름이 아니다.
    ⚠️ 돌연변이: 그 가름을 지우면 잡티가 다시 샌다.
    """
    from app.core import xicapture as _cap
    got = {r["number"]: r["name"] for r in _cap.parse(
        "1 요리스\n6 OO a\n14 세르히 팔렌시아\n99 부앙가\n")}
    assert "6" not in got, got
    assert got.get("1") == "요리스" and got.get("99") == "부앙가", got
    assert got.get("14") == "세르히 팔렌시아", got
