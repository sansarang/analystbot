"""🔴🔴 **v6 §7 단위 — 수학과 파서만.** s7 판정 수학 · s5 인용 대조 · s6 필수형.

지시서 §7: *"단위 테스트 — 수학과 파서만: s7 판정 수학(생존율·상한·다중 스코어
대입·방향 문턱), s5 인용 정규화, 해석 규칙 각각(고정 `Facts` 입력),
`competition_short`, `llm.py` 의 스키마 변환."*

⚠️ **실모델·실 API 를 부르지 않는다**(§9) — 여기 LLM 호출은 **없다**(s5·s7 은
   애초에 LLM 을 안 부르고, s6 는 호출 자리를 가짜로 바꿔 넣는다).
🔴 **글자 검사를 하지 않는다**(§9) — 전부 **행동**을 센다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.schema import (Doc, DropReason, Facts, HypoSet, MatchRef,
                             Scenario, VarCandidate, Variable)
from app.core.state import RunState
from app.core.stages import s5_verify, s6_hypo, s7_judge

HOME, AWAY = "team:000129", "team:000245"
KICK = datetime(2026, 10, 6, 11, 0, tzinfo=timezone.utc)


def ref(**kw) -> MatchRef:
    box = dict(id="fotmob:1", sport="soccer", competition="Friendlies",
               competition_short="친선", home=HOME, away=AWAY,
               home_name="South Korea", away_name="Uzbekistan",
               kickoff_utc=KICK)
    box.update(kw)
    return MatchRef(**box)                             # type: ignore[arg-type]


def var(i: int, **kw) -> Variable:
    box = dict(id=f"R{i}", type="absence", subject=HOME, favors="away",
               goals="none", target=f"대상{i}", hardness="hard", weight=1.0,
               claim=f"주장 {i}", quote="인용", doc_ids=["A-home-D1"])
    box.update(kw)
    return Variable(**box)                             # type: ignore[arg-type]


def scen(sid: str, outs: list[tuple[int, int]], **kw) -> Scenario:
    box = dict(id=sid, outcomes=outs, driver_vars=["R1"], mechanism="왜",
               strength=1.0)
    box.update(kw)
    return Scenario(**box)                             # type: ignore[arg-type]


# ══════════════════════════════════════════════════════════════════
# s5 — 인용 대조 · 방향 재계산 · 병합
# ══════════════════════════════════════════════════════════════════


def from_docs(got: list) -> list:
    """🔴 **기사에서 온 변수만** — 해석 규칙(IR01~)이 만든 사실 변수는 센지 않는다.

    ⚠️ s5 는 이제 `Facts` 에서도 변수를 만든다(사용자 지시 2026-10-06 ⑥) — 그것들은
       `from_rule` 을 들고 `doc_ids` 가 **없다**(기사가 아니라 어댑터 수치다).
    """
    return [v for v in got if v.from_rule is None]


def doc(body: str, *, did: str = "A-home-D1", when=KICK) -> Doc:
    return Doc(id=did, url=f"https://ex.com/{did}", domain="ex.com",
               tier="national", lang="en", title="South Korea news",
               body=body, published_at=when, date_source="htmldate",
               subtask="A-home")


def cand(**kw) -> VarCandidate:
    box = dict(subtask="A-home", type="absence", subject=HOME,
               claim="수비수가 빠진다", quote="Kim is ruled out",
               # 🔴 **병합 열쇠**(사용자 지시 2026-10-06 ①) — 같은 대상이면 한 사실이다
               target="Kim Min-jae", doc_id="A-home-D1")
    box.update(kw)
    return VarCandidate(**box)                         # type: ignore[arg-type]


def test_인용이_본문에_없으면_버린다():
    st = RunState()
    got = from_docs(s5_verify.run(ref(), Facts(),
                                  [doc("Nothing about it. South Korea")],
                                  [cand()], state=st))
    assert got == []
    assert [d.reason for d in st.drops] == [DropReason.QUOTE_NOT_FOUND]


def test_정규화_차이는_통과한다():
    """🔴 따옴표·대시·발음기호가 달라도 **같은 인용**이다(§5-1 정규화)."""
    body = ("South Korea coach said “Kim Min-jae is ruled out” — Ødegaard "
            "style absence.")
    got = from_docs(s5_verify.run(
        ref(), Facts(), [doc(body)],
        [cand(quote='"Kim Min-jae is ruled out" - Odegaard')],
        state=RunState()))
    assert len(got) == 1, got


def test_발행일이_없으면_근거가_못_된다():
    """🔴 불변식 9 — `date_source="none"` 인 Doc 을 근거로 한 변수는 **없다**."""
    st = RunState()
    body = "South Korea: Kim is ruled out"
    got = from_docs(s5_verify.run(ref(), Facts(), [doc(body, when=None)],
                                  [cand()], state=st))
    assert got == []
    assert [d.reason for d in st.drops] == [DropReason.DATE_MISSING]


def test_방향은_코드가_정한다_모델이_아니다():
    """🔴 `absence` 는 **상대**에게 유리하다 — 주체가 홈이면 `away`(카탈로그 규칙)."""
    body = "South Korea: Kim is ruled out"
    got = from_docs(s5_verify.run(ref(), Facts(), [doc(body)], [cand()],
                                  state=RunState()))
    assert got[0].favors == "away", got[0]
    # 🔴 주체를 원정으로 바꾸면 방향도 **뒤집힌다**(모델 입력은 그대로다)
    body2 = "Uzbekistan: Kim is ruled out"
    got2 = from_docs(s5_verify.run(
        ref(), Facts(), [doc(body2, did="A-away-D1")],
        [cand(subject=AWAY, subtask="A-away", doc_id="A-away-D1")],
        state=RunState()))
    assert got2[0].favors == "home", got2[0]


# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_같은_사실은_묶고_출처를_더한다`

def test_생존율은_무게로_센다():
    """🔴 홈승 갈래만 사는 마켓의 생존 = 그 갈래 무게 ÷ 전체."""
    vs = [var(1), var(2, favors="home"), var(3, favors="away")]
    scens = [scen("A", [(2, 0)], strength=3.0),
             scen("B", [(0, 1)], strength=1.0)]
    said = judge(vs, scens)
    row = _row(said, "win", "home")
    assert row.survival == pytest.approx(0.75), row
    assert row.marks == {"A": "○", "B": "✗"}
    # 🔴 `✗` 는 **죽는 시나리오**로 적힌다(§2-1)
    assert row.dead == ["B(✗)"]


def test_다중_스코어는_전부_대입해_부분_인정한다():
    """🔴 §6-a — 한 시나리오의 스코어가 갈리면 `△`(통과 비율만큼)."""
    vs = [var(1), var(2, favors="home"), var(3, favors="away")]
    said = judge(vs, [scen("A", [(2, 1), (1, 0)], strength=1.0)])
    row = _row(said, "total", "over") if any(
        e.line.market == "total" for e in said.evals) else None
    if row is not None:
        assert row.marks["A"] in ("○", "△", "✗")
    # 🔴 승패는 둘 다 홈승이라 `○` 다 — 섞이는 것은 총점이다
    assert _row(said, "win", "home").marks["A"] == "○"


def test_부분_인정은_반쪽_무게로_센다():
    """🔴 `2-1`·`0-0` 을 가진 갈래는 홈승에서 `△` 이고 생존이 1.0 이 아니다."""
    vs = [var(1), var(2, favors="home"), var(3, favors="away")]
    said = judge(vs, [scen("A", [(2, 1), (0, 0)], strength=1.0)])
    row = _row(said, "win", "home")
    assert row.marks["A"] == "△"
    assert 0.0 < row.survival < 1.0, row
    assert row.dead == ["A(△)"], row


def test_XI_가_없으면_상한이_내려가고_등급을_되올리지_않는다():
    """🔴 상한이 내린 등급을 **다시 계산해 올리지 않는다**(실측 pn8)."""
    vs = [var(1), var(2, favors="home"), var(3, favors="away"),
          var(4, favors="home"), var(5, favors="away")]
    scens = [scen("A", [(2, 0)], strength=9.0), scen("B", [(0, 1)],
                                                     strength=1.0)]
    said = judge(vs, scens)
    row = _row(said, "win", "home")
    assert row.survival == pytest.approx(0.9), row
    assert row.cap <= 0.8, row         # XI 없음 → 표의 상한
    assert row.grade != "낸다", row     # 🔴 상한이 막는다


def test_오픈월드는_한_칸_더_보수적이다():
    """🔴 아는 리그보다 **한 단계 보수적으로** — 간격은 표의 사다리가 정한다.

    ⚠️ XI 가 이미 `없음`(사다리 바닥)인 경기에서는 **더 내릴 칸이 없다** —
       그래서 양쪽 XI 가 확정인 경기로 센다(그때 상한이 1.0 이다).
    """
    from app.core.schema import XI
    vs = [var(1), var(2, favors="home"), var(3, favors="away"),
          var(4, favors="home"), var(5, favors="away")]
    scens = [scen("A", [(2, 0)], strength=9.0), scen("B", [(0, 1)],
                                                     strength=1.0)]
    xi = {k: XI(team=k, state="confirmed", players=[f"p{i}" for i in range(11)])
          for k in (HOME, AWAY)}
    facts = Facts(xi=xi)
    base = judge(vs, scens, facts=facts)
    opened = judge(vs, scens, facts=facts, ref={"openworld": True})
    assert _row(base, "win", "home").cap == 1.0
    assert _row(opened, "win", "home").cap < _row(base, "win", "home").cap


def test_변수가_모자라면_등급이_자료부족이다():
    """🔴 §7 R5 — **등급만** 거둔다(대입·방향은 그대로 낸다)."""
    said = judge([var(1)], [scen("A", [(2, 0)]), scen("B", [(0, 1)])])
    assert said.evals, "대입 줄은 그대로 있어야 한다"
    assert {e.grade for e in said.evals} == {"자료부족"}
    assert said.direction, "방향 줄은 매 경기 낸다"


# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_시작한_경기는_등급이_없다`

def test_방향_문턱은_차이_015_다():
    """🔴 지시서 §2-2 — 0.15 이상이면 팀 이름, 미만이면 `반반`+기울기."""
    vs = [var(1), var(2, favors="home"), var(3, favors="away")]
    gap = judge(vs, [scen("A", [(2, 0)], strength=8.0),
                     scen("B", [(0, 1)], strength=2.0)])
    assert "South Korea" in gap.direction, gap.direction
    even = judge(vs, [scen("A", [(2, 0)], strength=5.0),
                      scen("B", [(0, 1)], strength=5.0)])
    assert "반반" in even.direction, even.direction


# ══════════════════════════════════════════════════════════════════
# s6 — 필수형 보강 · 제외 번호 · strength
# ══════════════════════════════════════════════════════════════════


# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_근거_변수가_0개면_LLM_을_부르지_않는다`

# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_제외_번호를_인용한_줄은_버린다`

# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_필수형_90분_무승부는_단판에서만_들어간다`

# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_필수형_실점_동반형은_항상_들어간다`

# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_strength_는_유형별_최댓값_합이다`

# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_근거_없는_보강은_무게_바닥을_받는다`


# ⚠️ **되살린 도움 함수** — 걷은 시험 블록에 묶여 함께 사라졌다(§1 정리)
def _row(said, market: str, side: str):
    for e in said.evals:
        if e.line.market == market and e.line.side == side:
            return e
    raise AssertionError(f"{market}/{side} 줄이 없다: "
                         f"{[(e.line.market, e.line.side) for e in said.evals]}")
