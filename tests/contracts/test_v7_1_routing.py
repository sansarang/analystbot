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
