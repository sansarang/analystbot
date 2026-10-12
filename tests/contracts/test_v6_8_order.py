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
      ③ 파이프라인에서 `claims()` 가 **S3**(`_pm.run`) **앞**에 있다
    """
    fn = _fn(CORE / "stages" / "s6_hypo.py", "claims")
    args = {a.arg for a in [*fn.args.args, *fn.args.kwonlyargs]}
    for bad in ("sim", "ours", "our_prob", "prob", "layers", "matchup",
                "edge", "base_p", "adj_p"):
        assert bad not in args, f"🔴 가설 단계가 `{bad}` 를 받는다"
    said = ast.unparse(fn)
    for bad in ("probmodel", "our_prob", "\"sim\"", "'sim'"):
        assert bad not in said, f"🔴 가설 단계가 `{bad}` 를 읽는다"
    # 🔴🔴 **순서가 바뀌었다**(상성 엔진 지시서 §1): S2 상성 → S3 확률 → S4 가설
    #    → S5 검증 → S6 시나리오. ⚠️ C3 이 금지하는 것은 *"가설이 S3 **출력을
    #    입력으로** 받는 것"* 이고, 그것은 위 ①② 가 센다(인자·본문).
    src = (CORE / "pipeline.py").read_text(encoding="utf-8")
    s2, claims = src.find("_mu.report("), src.find("s6_hypo.claims(")
    chk, scen = src.find("_s6c.run("), src.find("s6_hypo.scenarios(")
    assert 0 <= s2 < claims, f"🔴 가설이 상성(S2)보다 앞이다({s2} {claims})"
    assert claims < chk < scen, f"🔴 검증·시나리오 순서가 어긋났다({chk} {scen})"


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


def test_v6_시뮬_표가_검증이_읽는_네_칸을_든다():
    """🔴🔴 **실사고 2026-10-10** — `sim.Out` 에 칸을 더해 놓고 산출 표에 **안
    실어** 검증이 12줄 중 **8줄**을 `기대득점 칸이 없다` 로 버렸다.

    🔴 그 표는 이제 **S3**(`probmodel.ProbOut.as_sim`)이 낸다(§2: 옛 `final_sim`
       을 지웠다). ⚠️ 네 칸 중 하나라도 빠지면 이 줄이 빨개진다(조용한 0 · #3).
    """
    from app.core import matchup as _mu
    from app.core import probmodel as _pm
    from app.core import routing, signals as _sg
    from app.core.schema import Facts, Signal, Variable, XI
    from app.core.state import RunState
    ref = _ref()
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
    got = _pm.run(ref, facts, mr, vs, state=RunState(match_key="x")).as_sim()
    for key in ("xg", "no_goal", "by_bucket", "first_then_win"):
        assert got.get(key), f"🔴 S3 표에 `{key}` 가 없다 — 검증이 못 읽는다"
    want = [Signal(metric="기대득점", direction=">", ref="0.5", side="home"),
            Signal(metric="무득점확률", direction="<", ref="0.9", side="away"),
            Signal(metric="구간득점", direction=">", ref="0.0", side="home",
                   arg="61-90+"),
            Signal(metric="선제골후승리", direction=">", ref="0.1",
                   side="home"),
            Signal(metric="승무패", direction=">", ref="0.1", arg="draw"),
            Signal(metric="오버", direction=">", ref="0.1", arg="1.5")]
    league = _sg.league_of(facts)
    for sig in want:
        said = _sg.check(sig, got, league=league)
        assert said["verdict"] != _sg.NA, (sig.metric, said["why"])

def test_v6_단위가_다른_기준을_버린다():
    """🔴🔴 **실사고 2026-10-10** — 모델이 `무득점확률 > 리그평균` 을 냈고 검증이
    **0.20 > 1.26** 을 견주어 *"반박"* 이라 적었다.

    `리그평균` 은 **경기당 한 팀 기대 득점**(골 수)이고 `무득점확률` 은 **확률**이다
    — 단위가 다르면 그 비교는 **뜻이 없다**(지지도 반박도 아니다).
    ⚠️ 돌연변이: `LEAGUE_OK` 검사를 지우면 그 거짓 판정이 돌아온다.
    """
    from app.core import signals as _sg
    from app.core.schema import Signal
    assert set(_sg.LEAGUE_OK) == {"기대득점", "구간득점"}
    for metric, arg in (("무득점확률", ""), ("승무패", "home"),
                        ("오버", "2.5"), ("선제골후승리", "")):
        sig = Signal(metric=metric, direction=">", ref="리그평균",
                     side="home", arg=arg)
        said = _sg.bad_signal(sig)
        assert "단위가 다르다" in said, (metric, said)
        got = _sg.check(sig, {"home": 0.4, "no_goal": {"home": 0.2}},
                        league={"per_team": 1.25})
        assert got["verdict"] == _sg.NA, (metric, got)
    # 🔴 골 단위 지표에는 **그대로 쓴다**
    ok = Signal(metric="기대득점", direction=">", ref="리그평균*0.8",
                side="home")
    assert _sg.bad_signal(ok) == ""
    # 🔴 프롬프트가 그 규칙을 **말한다**
    from app.core.stages import s6_hypo
    assert "확률 지표" in s6_hypo.system_prompt()


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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **(b) 의 조건이 좁아졌다** — 사용자 지시 2026-10-11(둘 다 고쳐라)
    # ══════════════════════════════════════════════════════════════════
    #
    #  종전: 경기에 낡음 의심이 있으면 **모든** 반박이 (b) 였다.
    #  이제: 그 가설의 **근거 변수가 낡은 쪽의 결장·교체**일 때만 (b) 다.
    #  🔴 새 보장은 `tests/contracts/test_v9_3_say_and_hypo.py` 가 센다.
    #  ⚠️ 실측 2026-10-11(LAFC): 반박 6건이 **전부** (b) 로 찍혀 원인 분류가
    #     아무 말도 하지 않았다 — 폼 가설(`S01-home`)까지 "기준 낡음"이었다.
    gone_v = ok.model_copy(update={"id": "R9", "type": "absence",
                                   "subject": "team:000318"})
    row_gone = _s6c.Row(verdict="반박", var_ids=["R9"], why="기본")
    cause2, why2 = _s6c._cause(row_gone, variables=[gone_v], stale="🔴 낡음",
                               why="기본", stale_sides={"home"}, ref=_ref())
    assert cause2 == _s6c.STALE, (cause2, why2)
    # 🔴 폼 변수는 **(c)** 다 — 결장과 관계가 없다(그래도 낡음 의심은 적는다)
    cause2b, why2b = _s6c._cause(row, variables=[ok], stale="🔴 낡음",
                                 why="기본", stale_sides={"home", "away"})
    assert cause2b == _s6c.WRONG and "낡음" in why2b, (cause2b, why2b)
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
    assert "선수단 교체" in said, said
    # 🔴🔴 **못 센 칸은 글귀에 안 섞는다** — ⚠️ 실사고 2026-10-10: 그 군더더기를
    #    같은 문장에 붙였더니 최종 평이 *"선수단 교체는 **감독 교체 직후라** …"*
    #    로 두 사실을 하나로 붙여 **거짓을 만들었다**. 그래서 `gaps` 로 따로 든다.
    assert "감독 교체" not in said, "🔴 모델에 가는 글에 군더더기가 섞였다"
    assert "감독 교체" in _s6c.GAP_COACH
    from app.core.state import RunState
    from app.core.schema import HypoSet
    got = _s6c.run(ref, Facts(), HypoSet(), {}, state=RunState(match_key="x"),
                   turnover={"home": {"on": True}})
    assert _s6c.GAP_COACH in list(got.get("gaps") or []), got.get("gaps")
    miss = [Missing(name=f"P{i}", reason="injury") for i in range(3)]
    said2 = _s6c._stale(ref, Facts(missing={ref.home: miss}), None)
    assert "결장 3명" in said2, said2
    assert _s6c._stale(ref, Facts(), None) == "", "🔴 아무것도 없는데 낡다고 했다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 계약 ④ — 최종 평의 근거 ⊂ 지지된 가설·변수
# ══════════════════════════════════════════════════════════════════

# ⚠️ **걷은 시험** — `s9_say`(㉔ 최종 평 LLM)가 지시서 2026-10-12(셋째)
#    §1 처분으로 **지워졌다**. 없는 단계를 시험하면 계약이 거짓을 지킨다.
#    걷은 시험: `test_v6_최종평은_반박된_가설을_근거로_못_쓴다`

# ⚠️ **걷은 시험** — `s9_say`(㉔ 최종 평 LLM)가 지시서 2026-10-12(셋째)
#    §1 처분으로 **지워졌다**. 없는 단계를 시험하면 계약이 거짓을 지킨다.
#    걷은 시험: `test_v6_기준_낡음은_평_첫줄에_적는다`

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
    # 🔴🔴 **여섯째 지시서 §3 이 순서를 다시 정했다** — ⚔️ 상성이 📊 확률 **앞**이다
    #    (확률의 출처가 상성이기 때문이다 · P1). 보드 판정은 **맨 끝**이다.
    # ⚠️ **🧑‍🏫 최종 평 칸은 빠졌다** — ㉔ LLM 서술이 §1 처분으로 지워졌다
    #    (지시서 2026-10-12(셋째)). 🔴 남은 순서는 그대로 지킨다.
    spots = [said.find(x) for x in ("⚔️", "📊", "🧪", "🎯 보드 판정")]
    assert all(x >= 0 for x in spots), spots
    assert spots == sorted(spots), f"🔴 카드 순서가 어긋났다 — {spots}"
    # 🔴 긴 카드에 **표 전체**와 재실행 여부가 있다
    from app.core import render
    long = render.check_long(card)
    assert "재실행" in long and "지지" in long
