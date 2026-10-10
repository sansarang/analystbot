"""🔴🔴 **순서 재편 계약** — 사용자 지시 2026-10-10(다섯째).

> ━━ 계약 ━━
> · 단계 순서: 단계 2(가설)는 단계 3(시뮬) 결과를 **입력으로 받지 않는다**
>   (가설이 결과를 보고 쓰이면 **실패**).
> · 가설마다 **예측 신호**가 있고, 신호 지표가 **허용 목록 안**.
> · **재실행 ≤ 1회**, 재실행 **사유 기록**.
> · 최종 평의 근거 id ⊂ **지지된 가설·변수**.
> · LLM 출력이 **확률을 바꾸지 않는다**.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "app" / "core"


def _tree(p: Path) -> ast.Module:
    return ast.parse(p.read_text(encoding="utf-8"))


def _fn(p: Path, name: str):
    got = [n for n in ast.walk(_tree(p))
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
           and n.name == name]
    assert got, f"🔴 `{p.name}` 에 `{name}` 이 없다"
    return got[0]


def _ref():
    from app.core.schema import MatchRef
    return MatchRef(id="x:1", sport="soccer", competition="K-League 1",
                    competition_short="K리그1", home="team:000318",
                    away="team:000320", home_name="Gangwon FC",
                    away_name="Bucheon FC 1995",
                    kickoff_utc=datetime.now(timezone.utc) + timedelta(hours=2))


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 계약 ① — 단계 2 는 시뮬 결과를 **안 받는다**
# ══════════════════════════════════════════════════════════════════

def test_v6_가설_단계가_시뮬_결과를_안_받는다():
    """🔴🔴 *"가설이 결과를 보고 쓰이면 **실패**"*.

    세 가지로 막는다:
      ① `claims()` 의 **인자에 시뮬·확률이 없다**
      ② 그 본문이 `sim`·`our_prob`·`matchup` 을 **읽지 않는다**
      ③ 파이프라인에서 `claims()` 가 `final_sim()` **앞**에 있다
    """
    fn = _fn(CORE / "stages" / "s6_hypo.py", "claims")
    args = {a.arg for a in [*fn.args.args, *fn.args.kwonlyargs]}
    for bad in ("sim", "ours", "our_prob", "prob", "layers", "matchup",
                "edge", "base_p", "adj_p"):
        assert bad not in args, f"🔴 가설 단계가 `{bad}` 를 받는다"
    said = ast.unparse(fn)
    for bad in ("final_sim", "our_prob", "\"sim\"", "'sim'"):
        assert bad not in said, f"🔴 가설 단계가 `{bad}` 를 읽는다"
    src = (CORE / "pipeline.py").read_text(encoding="utf-8")
    i, j = src.find("s6_hypo.claims("), src.find("final_sim(")
    assert 0 <= i < j, f"🔴 가설이 시뮬보다 뒤다(i={i} j={j})"
    # 🔴 시나리오는 **시뮬 뒤**다(§2-3·§4-4)
    k = src.find("s6_hypo.scenarios(")
    assert j < k, f"🔴 시나리오가 시뮬보다 앞이다(j={j} k={k})"
    # 🔴 검증도 시뮬 뒤다
    m = src.find("_s6c.run(")
    assert j < m, f"🔴 검증이 시뮬보다 앞이다"


def test_v6_가설_입력에_확률이_없다():
    """🔴 §계약 — `_payload` 가 보내는 것에 확률 칸이 **없다**."""
    said = ast.unparse(_fn(CORE / "stages" / "s6_hypo.py", "_payload"))
    for bad in ("our_prob", "base_prob", "probs", "ours", "sim"):
        assert bad not in said, f"🔴 가설 입력에 `{bad}` 가 있다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 계약 ② — 신호가 있고, 지표가 허용 목록 안
# ══════════════════════════════════════════════════════════════════

def test_v6_신호_지표는_허용_목록_안이다():
    """🔴 §2-2 — *"쓸 수 있는 지표 목록은 **코드가 준다** … 목록 밖 지표 금지."*"""
    from app.core import signals as _sg
    from app.core.schema import Signal
    assert set(_sg.METRICS) == {"기대득점", "무득점확률", "구간득점",
                                "선제골후승리", "승무패", "오버", "스코어"}
    # 🔴 프롬프트가 **표에서 자란다**(사본 금지)
    from app.core.stages import s6_hypo
    said = s6_hypo.system_prompt()
    for k in _sg.METRICS:
        assert f"`{k}`" in said, f"🔴 프롬프트에 `{k}` 가 없다"
    # 🔴 목록 밖은 **버려진다**
    assert _sg.bad_signal(Signal(metric="점유율", direction=">", ref="0.5",
                                 side="home")), "🔴 목록 밖 지표를 받았다"
    assert _sg.bad_signal(None), "🔴 신호 없는 줄을 통과시켰다"
    # 🔴 팀을 지정해야 하는 지표는 그것을 센다
    assert _sg.bad_signal(Signal(metric="기대득점", direction="<", ref="1.0"))
    # 🔴 인자가 필요한 지표도 센다
    assert _sg.bad_signal(Signal(metric="오버", direction=">", ref="0.5"))
    assert not _sg.bad_signal(Signal(metric="오버", direction=">", ref="0.5",
                                     arg="2.5"))


def test_v6_신호없는_줄은_판단_불가다():
    """🔴 §2-2·§4-1 — 신호가 없으면 **줄은 남고** 판정이 `판단 불가` 다.

    ⚠️ 줄을 지우면 *"가설이 없었다"* 와 *"검증 못 했다"* 가 섞인다(#3).
    """
    from app.core import signals as _sg
    from app.core.schema import HypoLine, Hypothesis
    from app.core.stages.s6_hypo import _clean_signals
    from app.core.state import RunState
    rows = [Hypothesis(team="home",
                       reasons=[HypoLine(text="신호 없다", var_ids=["V1"])])]
    drops: list = []
    got = _clean_signals(rows, drops=drops, state=RunState(match_key="x"))
    assert got[0].reasons[0].text == "신호 없다", "🔴 줄을 지웠다"
    assert got[0].reasons[0].signal is None
    assert drops, "🔴 버린 사유를 안 남겼다"
    said = _sg.check(None, {"home": 0.4})
    assert said["verdict"] == _sg.NA


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 계약 ③ — 재실행 ≤ 1회 · 사유 기록
# ══════════════════════════════════════════════════════════════════

def test_v6_재실행은_한_번이고_사유가_남는다():
    """🔴 §4-3 — *"재실행은 **최대 1회**"* · *"적합값이 없는 변수를 검증을 맞추려고
    임의로 넣지 않는다"*.

    🔴 지금은 계수가 전부 임시값이라 **0회**이고, 그 사유가 표에 남는다.
    """
    from app.core.stages import s6c_check as _s6c
    assert _s6c.MAX_RERUN == 1
    row = _s6c.Row(verdict="반박", cause=_s6c.MISS, var_ids=["V1"])
    said = _s6c._rerun_why([row], stale="")
    assert "재실행하지 않는다" in said and "적합" in said, said
    assert not _s6c.rerun_needed({"rerun": said}), "🔴 적합 없이 다시 돌았다"
    # 🔴 파이프라인은 그 깃발만 보고 **한 번** 돈다
    src = (CORE / "pipeline.py").read_text(encoding="utf-8")
    assert "rerun_needed(" in src, "🔴 재실행 판단을 안 본다"
    assert src.count("_s6c.run(") == 1, "🔴 검증을 여러 번 부른다"


def test_v6_반박_원인을_셋으로_가른다():
    """🔴 §4-2 — (a) 입력 누락 · (b) 기준 낡음 · (c) 가설 오류."""
    from app.core.stages import s6c_check as _s6c
    from app.core.schema import Variable
    row = _s6c.Row(verdict="반박", var_ids=["V1"], why="기본")
    ctx = Variable(id="V1", type="form", subject="team:000318", favors="home",
                   hardness="soft", weight=0.0, claim="c", quote="q",
                   usable_as_basis=False)
    cause, why = _s6c._cause(row, variables=[ctx], stale="", why="기본")
    assert cause == _s6c.MISS and "근거 불가" in why, (cause, why)
    ok = ctx.model_copy(update={"usable_as_basis": True, "weight": 2.0})
    cause2, why2 = _s6c._cause(row, variables=[ok], stale="🔴 낡음",
                               why="기본")
    assert cause2 == _s6c.STALE, (cause2, why2)
    cause3, _ = _s6c._cause(row, variables=[ok], stale="", why="기본")
    assert cause3 == _s6c.WRONG
    # 🔴 변수 목록을 모르면 (a) 라고 하지 않는다(#4)
    cause4, _ = _s6c._cause(row, variables=None, stale="", why="기본")
    assert cause4 == _s6c.WRONG


def test_v6_기준_낡음을_선수단교체와_결장으로_센다():
    """🔴 §4-2 (b) — *"한쪽이 `squad_turnover`·감독 교체 직후·**핵심 3명 이상
    결장**"*. ⚠️ 감독 교체 직후는 **못 센다**(취임일 자료가 없다)."""
    from app.core.schema import Facts, Missing
    from app.core.stages import s6c_check as _s6c
    ref = _ref()
    assert _s6c.ABSENT_STALE == 3
    said = _s6c._stale(ref, Facts(), {"home": {"on": True}})
    assert "선수단 교체" in said and "감독 교체" in said, said
    miss = [Missing(name=f"P{i}", reason="injury") for i in range(3)]
    said2 = _s6c._stale(ref, Facts(missing={ref.home: miss}), None)
    assert "결장 3명" in said2, said2
    assert _s6c._stale(ref, Facts(), None) == "", "🔴 아무것도 없는데 낡다고 했다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 계약 ④ — 최종 평의 근거 ⊂ 지지된 가설·변수
# ══════════════════════════════════════════════════════════════════

def test_v6_최종평은_반박된_가설을_근거로_못_쓴다():
    """🔴 §5 — *"지지된 가설과 그 근거만 쓴다. 반박된 가설은 '🔄 뒤집히는 조건'
    후보로만."*"""
    from app.core import saybundle
    from app.core.schema import Card, Facts, KeyPoint, ProbTriple, SayOut
    from app.core.stages import s9_say
    chk = {"rows": [
        {"side": "home", "kind": "reasons", "text": "지지된 것",
         "var_ids": ["V1"], "signal": "s", "value": 1.0, "want": 0.5,
         "verdict": "지지", "cause": "", "why": "w"},
        {"side": "away", "kind": "reasons", "text": "반박된 것",
         "var_ids": ["V2"], "signal": "s", "value": 0.1, "want": 0.5,
         "verdict": "반박", "cause": "가설 오류", "why": "w"}],
        "supported": [], "counts": {"지지": 1, "반박": 1, "판단 불가": 0},
        "stale": "", "rerun": "", "why": "x"}
    card = Card(match=_ref(), facts=Facts(), check=chk,
                our_prob=ProbTriple(home=0.5, draw=0.3, away=0.2))
    box = saybundle.build(card)
    assert box.items.get("H1") is not None, "🔴 지지된 가설이 묶음에 없다"
    assert box.items.get("R1") is not None, "🔴 반박된 가설이 묶음에 없다"
    # 🔴 판단 불가는 **묶음에 없다**
    assert not [k for k in box.items if str(k).startswith("U")]
    base = {"verdict": "Gangwon FC", "one_line": "강원이 가져간다",
            "flow_first": "a", "flow_second": "b", "decisive_moment": "c",
            "flip_condition": "d"}
    bad = SayOut(**base, key_points=[
        KeyPoint(claim="주장", mechanism="메커니즘", refs=["R1", "H1"])] * 3)
    said = s9_say.check(bad, card=card, box=box)
    assert any("반박된 가설을 근거로 썼다" in x for x in said), said
    ok = SayOut(**base, key_points=[
        KeyPoint(claim="주장", mechanism="메커니즘", refs=["H1", "P1"])] * 3)
    said2 = s9_say.check(ok, card=card, box=box)
    assert not any("반박된" in x for x in said2), said2


def test_v6_기준_낡음은_평_첫줄에_적는다():
    """🔴 §5 — *"기준 낡음 의심이 있으면 평 **첫 줄에** 그 사실을 적는다."*"""
    from app.core import saybundle
    from app.core.schema import Card, Facts, KeyPoint, ProbTriple, SayOut
    from app.core.stages import s9_say
    chk = {"rows": [{"side": "home", "kind": "reasons", "text": "t",
                     "var_ids": ["V1"], "signal": "s", "value": 1.0,
                     "want": 0.5, "verdict": "지지", "cause": "", "why": "w"}],
           "counts": {"지지": 1, "반박": 0, "판단 불가": 0},
           "stale": "🔴 **기준 낡음 의심** — 강원 선수단 교체", "rerun": "",
           "why": "x"}
    card = Card(match=_ref(), facts=Facts(), check=chk,
                our_prob=ProbTriple(home=0.5, draw=0.3, away=0.2))
    box = saybundle.build(card)
    assert box.items.get("H0") is not None, "🔴 기준 낡음을 묶음에 안 넣었다"
    base = {"verdict": "Gangwon FC", "flow_first": "a", "flow_second": "b",
            "decisive_moment": "c", "flip_condition": "d",
            "key_points": [KeyPoint(claim="주장", mechanism="메커니즘",
                                    refs=["H1", "P1"])] * 3}
    bad = SayOut(**base, one_line="강원이 가져간다")
    said = s9_say.check(bad, card=card, box=box)
    assert any("기준 낡음" in x for x in said), said
    ok = SayOut(**base, one_line="기준 낡음 의심 — 강원이 가져간다")
    assert not any("기준 낡음 의심인데" in x
                   for x in s9_say.check(ok, card=card, box=box))


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 계약 ⑤ — LLM 이 확률을 안 바꾼다 · 시나리오는 분포에서
# ══════════════════════════════════════════════════════════════════

def test_v6_검증단계가_LLM을_안_부르고_확률을_안_바꾼다():
    """🔴 §3·§4 — 검증은 **코드만**이고 확률을 만들지 않는다."""
    said = (CORE / "stages" / "s6c_check.py").read_text(encoding="utf-8")
    for bad in ("llm.ask", "our_prob =", "ProbTriple("):
        assert bad not in said, f"🔴 검증 단계가 `{bad}` 를 한다"
    sig = (CORE / "signals.py").read_text(encoding="utf-8")
    assert "llm" not in sig, "🔴 신호 대조가 LLM 을 부른다"


def test_v6_시나리오가_시뮬_분포에서_온다():
    """🔴 §4-4 — 승·무·패별 상위 1~2개 · 근거는 **지지된 가설의 변수만**."""
    from app.core.schema import Facts, HypoSet
    from app.core.stages import s6_hypo
    from app.core.state import RunState
    sim = {"scores": {(1, 0): 0.12, (2, 0): 0.08, (1, 1): 0.11, (0, 0): 0.06,
                      (0, 1): 0.09, (1, 2): 0.05}}
    sup = [{"side": "home", "kind": "reasons", "var_ids": ["V1", "V2"]},
           {"side": "away", "kind": "reasons", "var_ids": ["V9"]},
           {"side": "home", "kind": "breaks", "var_ids": ["V7"]}]
    got = s6_hypo._from_sim(sim, HypoSet(), sup, state=RunState(match_key="x"))
    assert s6_hypo.PER_OUTCOME == 2
    kinds = {("home" if h > a else "draw" if h == a else "away")
             for one in got for (h, a) in one.outcomes}
    assert kinds == {"home", "draw", "away"}, kinds
    home_one = [o for o in got if o.outcomes[0][0] > o.outcomes[0][1]][0]
    assert set(home_one.driver_vars) == {"V1", "V2"}, home_one.driver_vars
    away_one = [o for o in got if o.outcomes[0][0] < o.outcomes[0][1]][0]
    assert set(away_one.driver_vars) == {"V9"}
    draw_one = [o for o in got if o.outcomes[0][0] == o.outcomes[0][1]][0]
    assert set(draw_one.driver_vars) == {"V7"}, "🔴 무승부 근거는 `breaks` 다"
    # 🔴 분포가 없으면 **빈 목록**이고 사유가 남는다(#3)
    st = RunState(match_key="x")
    assert s6_hypo._from_sim({}, HypoSet(), sup, state=st) == []
    assert any("분포에서 못 만들었다" in x for x in st.notes)


def test_v6_카드_순서가_지시서대로다():
    """🔴 §카드 — 헤드라인 → 📊 확률 → ⚔️ 상성 → 🧪 검증 → 🧑‍🏫 평 → 보드."""
    from app.core import layer1
    from app.core.schema import Card, Facts, ProbTriple, SayOut, KeyPoint
    chk = {"rows": [{"side": "home", "kind": "reasons", "text": "지지된 것",
                     "var_ids": ["V1"], "signal": "home 기대득점 > 1.0",
                     "value": 1.4, "want": 1.0, "verdict": "지지",
                     "cause": "", "why": "w"}],
           "counts": {"지지": 1, "반박": 0, "판단 불가": 0}, "stale": "",
           "rerun": "", "why": "x"}
    say = SayOut(verdict="Gangwon FC", one_line="한 줄",
                 key_points=[KeyPoint(claim="주장", mechanism="메커니즘",
                                      refs=["H1"])] * 3,
                 flow_first="a", flow_second="b", decisive_moment="c",
                 flip_condition="d", audit="통과")
    card = Card(match=_ref(), facts=Facts(), check=chk, say=say,
                matchup={"profile": {"home": 1},
                         "sim": {"home": 0.5, "draw": 0.3, "away": 0.2}},
                our_prob=ProbTriple(home=0.5, draw=0.3, away=0.2))
    said = layer1.text(card)
    spots = [said.find(x) for x in ("📊", "⚔️", "🧪", "🧑‍🏫", "🎯 보드 판정")]
    assert all(x >= 0 for x in spots), spots
    assert spots == sorted(spots), f"🔴 카드 순서가 어긋났다 — {spots}"
    # 🔴 긴 카드에 **표 전체**와 재실행 여부가 있다
    from app.core import render
    long = render.check_long(card)
    assert "재실행" in long and "지지" in long
