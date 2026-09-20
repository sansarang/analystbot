"""[v1.4 STEP 2~12] 노드별 계약 — 지시문의 기대값을 그대로 잠근다.

🔴 숫자는 **지시문 §3·§6 원문**이다. 여기서 새로 짓지 않았다.
⚠️ 모든 노드는 `ctx.inject` 로 바깥을 갈아끼운다 — 테스트가 네트워크·DB 를
   타지 않는다(CLAUDE.md: 계약이 인프라에 매이면 그건 계약이 아니다).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.flow.ctx import Ctx
from app.flow.labels import (AGREE, BOARD, DOUBT, GRADE_A, GRADE_B, GRADE_C,
                             OVER, PICK_BOARD, PICK_ML, V_OK, V_REFUTED,
                             V_UNKNOWN)
from app.flow.nodes import (n01_prior, n02_market, n03_gate, n04_hyp,
                            n05_evidence, n06_verdict, n07_adjust, n08_pcode,
                            n09_conf, n10_rejudge, n11_value, n12_text,
                            n13_send)
from app.flow.odds_math import devig_2way, devig_3way, margin, required_prob
from app.flow.state import State

KBO = {"game_id": "1", "sport": "baseball", "league": "KBO",
       "home": "한화", "away": "삼성", "starts_at": "2026-09-18T09:30:00Z"}
UEL = {"game_id": "2", "sport": "soccer", "league": "UEL",
       "home": "Crystal Palace", "away": "Lech Poznan",
       "starts_at": "2026-09-17T19:00:00Z"}


def _s(game=KBO, **kw):
    st = State.new(game)
    for k, v in kw.items():
        setattr(st, k, v)
    return st


# ── STEP 3 배당 수학 (지시문 기대값)

def test_devig_2way_지시문_기대값():
    _, p_away = devig_2way(2.97, 1.35)
    assert abs(p_away - 0.687) <= 0.002, p_away


def test_devig_3way_지시문_기대값():
    ph, pd, pa = devig_3way(1.32, 5.06, 7.29)
    assert abs(ph - 0.693) <= 0.003, ph
    assert abs(ph + pd + pa - 1.0) < 1e-9


def test_요구확률은_마진을_빼지_않는다():
    """🔴 `p_market`(devig)과 `required`(1/배당)는 다른 숫자다."""
    _, p_devig = devig_2way(2.97, 1.35)
    assert required_prob(1.35) > p_devig      # 마진만큼 크다
    assert margin(2.97, 1.35) > 0


# ── STEP 2 ① 사전값

@pytest.mark.asyncio
async def test_사전값_야구_2way():
    ctx = Ctx(inject={"elo": {"한화": 1450.0, "삼성": 1580.0}})
    s = await n01_prior.run(_s(), ctx)
    p = s.n01_prior
    assert p["p_draw"] is None
    assert abs(p["p_home"] + p["p_away"] - 1.0) < 1e-9
    assert p["p_away"] >= 0.6, p              # 지시문 STEP 2 테스트
    assert s.pick_side == "away"


@pytest.mark.asyncio
async def test_사전값_축구_3way_합이_1():
    ctx = Ctx(inject={"elo": {"Crystal Palace": 1600.0, "Lech Poznan": 1450.0}})
    s = await n01_prior.run(_s(UEL), ctx)
    p = s.n01_prior
    assert abs(p["p_home"] + p["p_draw"] + p["p_away"] - 1.0) < 1e-9
    assert p["p_draw"] > 0


@pytest.mark.asyncio
async def test_elo가_없으면_지어내지_않는다():
    """🔴 리그 평균으로 메우지 않는다 — 채운 팀과 안 채운 팀이 같아 보이면 안 된다."""
    s = await n01_prior.run(_s(), Ctx(inject={"elo": {}}))
    assert s.n01_prior["p_home"] is None
    assert s.n01_prior["missing"] == ["한화", "삼성"]
    assert s.pick_side is None


# ── STEP 3 ② 시장값

def _odds_rows():
    return [{"market": "h2h", "side": "한화", "line": None, "odds": 2.97},
            {"market": "h2h", "side": "삼성", "line": None, "odds": 1.35},
            {"market": "totals", "side": "Over", "line": 9.5, "odds": 1.78},
            {"market": "totals", "side": "Under", "line": 9.5, "odds": 1.90},
            {"market": "team_totals", "side": "삼성 Over", "line": 4.5,
             "odds": 1.43},
            {"market": "team_totals", "side": "삼성 Under", "line": 4.5,
             "odds": 2.58},
            {"market": "spreads", "side": "삼성", "line": -2.5, "odds": 1.84}]


@pytest.mark.asyncio
async def test_시장값_야구():
    s = await n02_market.run(_s(), Ctx(inject={"odds_rows": _odds_rows()}))
    m = s.n02_market
    assert abs(m["p"]["away"] - 0.687) <= 0.002
    assert m["p"]["draw"] is None
    assert m["market_missing"] is False
    # 🔴 요구확률은 따로 있다
    assert m["required"]["away"] > m["p"]["away"]
    assert m["derivatives"]["total"]["line"] == 9.5
    assert m["derivatives"]["team_total_away"]["over"] == 1.43


@pytest.mark.asyncio
async def test_배당이_없으면_시장없음():
    s = await n02_market.run(_s(), Ctx(inject={"odds_rows": []}))
    assert s.n02_market["market_missing"] is True
    assert s.n02_market["p"] is None


# ── STEP 4 ③ 게이트

async def _gate(gap_pp, side="away"):
    """사전값과 시장을 원하는 gap 이 나오게 맞춘다."""
    p_mkt = 0.60
    p_pri = round(p_mkt + gap_pp / 100.0, 4)
    st = _s(pick_side=side,
            n01_prior={f"p_{side}": p_pri},
            n02_market={"p": {side: p_mkt}, "market_missing": False})
    return (await n03_gate.run(st, Ctx())).n03_gate


@pytest.mark.asyncio
async def test_게이트_네갈래():
    assert (await _gate(+0.3))["gate"] == AGREE
    assert (await _gate(-9.3))["gate"] == OVER
    assert (await _gate(+4.4))["gate"] == DOUBT
    assert (await _gate(+13.0))["gate"] == BOARD


@pytest.mark.asyncio
async def test_시장이_없어도_사전값이_있으면_멈추지_않는다():
    """🔴 [F-17 2026-09-19 개정] 종전에는 시장이 없으면 보드 고정이었다.

    이제는 **사전값이 없을 때만** 보드다 — 시장이 아직 안 온 것은
    "찾을 것이 없다"가 아니라 "비교 대상이 아직 없다"이다.
    """
    from app.flow.labels import PRIOR_ONLY

    st = _s(pick_side="home", n01_prior={"p_home": 0.6},
            n02_market={"market_missing": True, "p": None})
    g = (await n03_gate.run(st, Ctx())).n03_gate
    assert g["gate"] == PRIOR_ONLY and g["stop"] is False


@pytest.mark.asyncio
async def test_gap은_픽_기준이다():
    """🔴 홈 기준으로 고정하면 픽이 원정일 때 분기가 뒤집힌다."""
    st = _s(pick_side="away",
            n01_prior={"p_home": 0.35, "p_away": 0.65},
            n02_market={"p": {"home": 0.45, "away": 0.55}, "market_missing": False})
    g = (await n03_gate.run(st, Ctx())).n03_gate
    assert g["gap_pp"] == 10.0 and g["gate"] == DOUBT


# ── STEP 5 ④ 가설

@pytest.mark.asyncio
async def test_가설은_게이트마다_다르다():
    for gate, hid in ((OVER, "H_fade"), (DOUBT, "H_break"), (AGREE, "H_deriv")):
        st = _s(pick_side="away", n03_gate={"gate": gate})
        h = (await n04_hyp.run(st, Ctx())).n04_hyp[0]
        assert h["id"] == hid, (gate, h)
        assert h["vars"], gate


@pytest.mark.asyncio
async def test_동의는_파생만_본다():
    st = _s(pick_side="away", n03_gate={"gate": AGREE})
    h = (await n04_hyp.run(st, Ctx())).n04_hyp[0]
    names = [v["var"] for v in h["vars"]]
    assert names == ["starter_recent3", "bullpen_3d", "lineup_out"], names


def test_가설은_LLM을_부르지_않는다():
    """🔴 CLAUDE.md — 가설은 코드가 세운다.

    ⚠️ **주석이 아니라 실행 줄만 본다.** 머리말에 "LLM 을 부르지 않는다"라고
       설명해 둔 것을 결함으로 세면 설명을 못 쓰게 된다(이 저장소의 반복 결함).
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(n04_hyp))
    for node in ast.walk(tree):           # 문서 문자열을 통째로 지운다
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    code = ast.unparse(tree).lower()
    for banned in ("llm", "complete_text", "gemini", "groq", "provider"):
        assert banned not in code, banned


# ── STEP 6 ⑤ 수집

@pytest.mark.asyncio
async def test_수집은_가설_목록_밖을_요청하지_않는다():
    st = _s(pick_side="away", n03_gate={"gate": AGREE})
    st = await n04_hyp.run(st, Ctx())
    ctx = Ctx(inject={"extract": {"home": {"out": ["A"]}, "away": {"out": []}},
                      "absences": []})
    st = await n05_evidence.run(st, ctx)
    wanted = {v["var"] for v in st.n04_hyp[0]["vars"]}
    assert all(e["var"] in wanted for e in st.n05_evidence), st.n05_evidence


@pytest.mark.asyncio
async def test_공식_결장을_합친다():
    """🔴 FORKS F-2 — 기사와 공식을 합치고, 충돌 시 공식이 이긴다."""
    st = _s(pick_side="away", n03_gate={"gate": AGREE})
    st = await n04_hyp.run(st, Ctx())
    # ⚠️ [HYC-1 2026-09-20] 기사 카드는 **코드가 아는 출처**가 있어야 센다 —
    #    상자 모양을 실제 위성 산출물과 같게 둔다(`gathered_at` + `sources_fed`).
    #    출처 없는 카드가 버려지는 것은 `test_hyc1_card_trust.py` 가 따로 잠근다.
    ctx = Ctx(inject={"extract": {
        "gathered_at": "2026-09-20T08:47:35+00:00",
        "teams": {"home": {"out": ["기사선수"],
                           "sources_fed": ["https://n.example/a"]},
                  "away": {"out": [], "sources_fed": ["https://n.example/a"]}}},
        "absences": ["한화의 공식선수(선발) Injured 10-Day로 결장"]})
    st = await n05_evidence.run(st, ctx)
    row = [e for e in st.n05_evidence if e["var"] == "lineup_out"]
    assert row and "기사선수" in row[0]["value"]
    assert any("공식선수" in v for v in row[0]["value"]), row


@pytest.mark.asyncio
async def test_원문이_없으면_폐기한다():
    st = _s(pick_side="away", n03_gate={"gate": AGREE})
    st = await n04_hyp.run(st, Ctx())
    st = await n05_evidence.run(st, Ctx(inject={"extract": {}, "absences": []}))
    assert st.n05_evidence == []


# ── STEP 7 ⑥ 채점

async def _verdict(per_evidence, gate=AGREE):
    st = _s(pick_side="away", n03_gate={"gate": gate})
    st = await n04_hyp.run(st, Ctx())
    st.n05_evidence = [{"var": k, "value": v, "raw_excerpt": "x"}
                       for k, v in per_evidence.items()]
    return (await n06_verdict.run(st, Ctx())).n06_verdict


@pytest.mark.asyncio
async def test_핵심_반증_하나면_반박됨():
    """🔴 [CNF-2 2026-09-20] 반증이 **철회를 뜻하는 가설에서만** 반박됨이다.

    종전에는 게이트와 무관하게 언제나 철회였다. 그러면 "우리 픽을 무너뜨릴
    근거를 못 찾았다"도 철회가 되어, 결장 0명인 건강한 라인업이 전부
    철회된다(근거 FORKS F-19).
    """
    from app.flow.labels import OVER

    # 시장과대 → H_fade "시장 반대편을 세울 근거" → 없으면 시장이 맞다
    v = await _verdict({"starter_recent3": [], "bullpen_3d": ["a"],
                        "lineup_out": ["b"]}, gate=OVER)
    assert v["verdict"] == V_REFUTED
    assert v["core_refuted"] == ["starter_recent3"]
    assert v["refuted_means"] == "철회"

    # 동의 → H_deriv 파생 재료 → 승패 판정을 건드리지 않는다
    v2 = await _verdict({"starter_recent3": [], "bullpen_3d": ["a"],
                         "lineup_out": ["b"]}, gate=AGREE)
    assert v2["core_refuted"] == ["starter_recent3"]
    assert v2["verdict"] != V_REFUTED
    assert v2["refuted_means"] == "중립"


@pytest.mark.asyncio
async def test_미상_과반이면_모름과반():
    v = await _verdict({"starter_recent3": ["a"]})     # 3개 중 2개 미상
    assert v["verdict"] == V_UNKNOWN
    assert v["unknown_ratio"] > 0.5


@pytest.mark.asyncio
async def test_전부_확인되면_확인됨():
    v = await _verdict({"starter_recent3": ["a"], "bullpen_3d": ["b"],
                        "lineup_out": ["c"]})
    assert v["verdict"] == V_OK
    assert v["unknown_ratio"] == 0.0


# ── STEP 8 ⑦⑧⑨

@pytest.mark.asyncio
async def test_조정은_표_안에서만_그리고_합계_클램프():
    st = _s(n06_verdict={"per_var": {"starter_recent3": "confirmed",
                                     "bullpen_3d": "confirmed",
                                     "lineup_out": "confirmed",
                                     "없는변수": "confirmed"}},
            n05_evidence=[{"var": v, "raw_excerpt": "ERA 6.10"}
                          for v in ("starter_recent3", "bullpen_3d", "lineup_out")])
    st = await n07_adjust.run(st, Ctx())
    names = {a["var"] for a in st.n07_adjust}
    assert "없는변수" not in names                     # 표 밖은 0
    total = sum(a["pp"] for a in st.n07_adjust)
    assert abs(total) <= 6.0 + 1e-9, total             # 합계 캡


@pytest.mark.asyncio
async def test_정성근거는_절반만_먹는다():
    """🔴 [FIXDIR 2026-09-20] 규칙이 **둘** 바뀌었다.

    ① 방향을 모르면 조정을 **만들지 않는다.** 종전에는 `_direction` 이
       "모르면 −1(보수적으로 불리)"을 냈는데, 그러면 자료가 없을수록 확률이
       내려간다 — 모름을 불리의 근거로 쓴 것이다. 아래 첫 단언이 그 폐기다.
    ② 강도는 편차 크기다(`|dev| / dev_full`). 정성 근거는 `sides` 로 쪽이
       지정됐을 때만 옛 규칙(0.5)이 호환 경로로 유지된다.
    """
    # ① 쪽 지정도 방향도 없으면 → 조정 0건
    st = _s(n06_verdict={"per_var": {"lineup_out": "confirmed"}},
            n05_evidence=[{"var": "lineup_out", "raw_excerpt": "결장자 있음"}])
    st = await n07_adjust.run(st, Ctx())
    assert st.n07_adjust == [], st.n07_adjust

    # ② 쪽이 지정된 정성 근거는 종전처럼 절반만 먹는다
    st = _s(pick_side="away",
            n06_verdict={"per_var": {"lineup_out": "confirmed"}},
            n05_evidence=[{"var": "lineup_out", "raw_excerpt": "결장자 있음",
                           "sides": {"home": 1}}])
    st = await n07_adjust.run(st, Ctx())
    assert st.n07_adjust[0]["strength"] == 0.5
    assert abs(st.n07_adjust[0]["pp"]) == 1.25         # 2.5 × 0.5


@pytest.mark.asyncio
async def test_pcode는_시장_뼈대에_조정을_얹는다():
    st = _s(pick_side="away",
            n02_market={"p": {"away": 0.687}},
            n07_adjust=[{"var": "x", "pp": 2.0}])
    st = await n08_pcode.run(st, Ctx())
    assert st.n08_pcode["p_code_pick"] == 0.707        # 지시문 STEP 8
    assert st.n08_pcode["sum_adj_pp"] == 2.0
    assert st.n08_pcode["model_w"] == 0.0


@pytest.mark.asyncio
async def test_확신_등급():
    # 🔴 [FIX-3 2026-09-20] A 의 |Σadj| 는 **방향이 판정된 조정**(n07_adjust)만
    #    센다. 종전에는 `n08.sum_adj_pp`(캡·축소가 걸린 뒤 값)를 봤다.
    base = {"per_var": {"starter_recent3": "confirmed", "bullpen_3d": "confirmed"}}
    a = await n09_conf.run(_s(n06_verdict=base, n08_pcode={"sum_adj_pp": -3.5},
                              n07_adjust=[{"var": "starter_recent3", "pp": -3.5}]), Ctx())
    assert a.n09_conf["grade"] == GRADE_A
    # 방향이 판정된 조정이 없으면 A 가 아니다 — 자료가 없는데 A 가 나오면 안 된다
    a2 = await n09_conf.run(_s(n06_verdict=base, n08_pcode={"sum_adj_pp": -3.5},
                               n07_adjust=[]), Ctx())
    assert a2.n09_conf["grade"] == GRADE_B, a2.n09_conf
    b = await n09_conf.run(_s(n06_verdict={"per_var": {"lineup_out": "confirmed"}},
                              n08_pcode={"sum_adj_pp": -1.0}), Ctx())
    assert b.n09_conf["grade"] == GRADE_B
    c = await n09_conf.run(_s(n06_verdict={"per_var": {"lineup_out": "unknown"}},
                              n08_pcode={"sum_adj_pp": 0.0}), Ctx())
    assert c.n09_conf["grade"] == GRADE_C


# ── STEP 9 ⑩ 재판정

def _ko(minutes_left):
    now = datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc)
    return now + timedelta(minutes=minutes_left), now


@pytest.mark.asyncio
async def test_창_안에서_선발변경이면_재판정():
    ko, now = _ko(60)
    st = _s(dict(KBO, starts_at=ko.isoformat()))
    ctx = Ctx(now_kst=now, inject={"rejudge_signals": {"starter_changed": True}})
    r = (await n10_rejudge.run(st, ctx)).n10_rejudge
    assert r["triggered"] is True and r["trigger"] == "starter_changed"


@pytest.mark.asyncio
async def test_창_밖이면_재판정하지_않는다():
    ko, now = _ko(200)
    st = _s(dict(KBO, starts_at=ko.isoformat()))
    ctx = Ctx(now_kst=now, inject={"rejudge_signals": {"starter_changed": True}})
    assert (await n10_rejudge.run(st, ctx)).n10_rejudge["triggered"] is False


@pytest.mark.asyncio
async def test_두번째_트리거는_무시한다():
    ko, now = _ko(60)
    st = _s(dict(KBO, starts_at=ko.isoformat()),
            n10_rejudge={"triggered": True, "trigger": "starter_changed"})
    ctx = Ctx(now_kst=now, inject={"rejudge_signals": {"lineup_confirmed": True}})
    r = (await n10_rejudge.run(st, ctx)).n10_rejudge
    assert r["second_ignored"] is True and r["trigger"] == "starter_changed"


# ── STEP 10 ⑪ 값 판정

@pytest.mark.asyncio
async def test_승패픽은_동의에서만_그리고_edge가_넘어야():
    st = _s(pick_side="away", n03_gate={"gate": AGREE},
            n02_market={"odds": {"away": 1.35}, "derivatives": {}},
            n08_pcode={"p_code_pick": 0.80})
    v = (await n11_value.run(st, Ctx())).n11_value
    assert v["pick_type"] == PICK_ML and v["ml_edge_pp"] > 2.0


@pytest.mark.asyncio
async def test_시장과대에서는_승패픽을_만들지_않는다():
    """🔴 v1.4 — 시장 동의 시에만 추천한다."""
    st = _s(pick_side="away", n03_gate={"gate": OVER},
            n02_market={"odds": {"away": 1.35}, "derivatives": {}},
            n08_pcode={"p_code_pick": 0.95})
    v = (await n11_value.run(st, Ctx())).n11_value
    assert v["pick_type"] == PICK_BOARD


@pytest.mark.asyncio
async def test_모델없는_파생은_후보가_아니다():
    """🔴 추측 확률로 픽을 만들지 않는다."""
    st = _s(pick_side="away", n03_gate={"gate": AGREE},
            n02_market={"odds": {"away": 1.35},
                        "derivatives": {"team_total_away": {"line": 4.5,
                                                            "over": 1.43}}},
            n08_pcode={"p_code_pick": 0.70})      # ours_markets 없음
    v = (await n11_value.run(st, Ctx())).n11_value
    assert v["pick_type"] == PICK_BOARD and v["n_candidates"] == 0


# ── STEP 11 ⑫ 서술

def _narr_state():
    return _s(pick_side="away",
              n05_evidence=[{"var": "lineup_out", "value": ["A"],
                             "source_url": "http://x"}],
              n07_adjust=[{"var": "lineup_out", "pp": -2.5}],
              n08_pcode={"p_code_pick": 0.707},
              n09_conf={"grade": GRADE_B},
              n11_value={"pick_type": PICK_ML})


@pytest.mark.asyncio
async def test_서술은_4문장이다():
    text = "삼성을 고른다. 결장이 확인됐다. 조정이 반영됐다. 다만 변수가 있다."
    st = await n12_text.run(_narr_state(), Ctx(inject={"narration": text}))
    assert st.n12_text["hallucination"] is False
    assert len(st.n12_text["sentences"]) == 4


@pytest.mark.asyncio
async def test_입력에_없는_숫자가_나오면_카드를_안_만든다():
    text = "삼성 승률 88%. 결장 3명. 불펜 12이닝. 리스크 있다."
    st = await n12_text.run(_narr_state(), Ctx(inject={"narration": text}))
    assert st.n12_text["hallucination"] is True
    assert st.n12_text["sentences"] == []


# ── STEP 12 ⑬ 발송

@pytest.mark.asyncio
async def test_보드면_보내지_않는다():
    st = _s(n11_value={"pick_type": PICK_BOARD},
            n12_text={"sentences": ["1", "2", "3", "4"]})
    assert (await n13_send.run(st, Ctx())).n13_send["sent"] is False


@pytest.mark.asyncio
async def test_한_번만_보낸다(monkeypatch):
    """⚠️ [2026-09-18] 섀도 가드가 생겨 `PIPELINE_V14_SEND` 를 켜야 한다.
    이 테스트가 재는 것은 **멱등성**이지 스위치가 아니다."""
    from app import config as C

    class _S:
        pipeline_v14_send = True

    monkeypatch.setattr(C, "get_settings", lambda: _S())
    sent = []
    st = _s(pick_side="away", n11_value={"pick_type": PICK_ML, "structure": None},
            n02_market={"odds": {"away": 1.35}},
            # ⚠️ [FIX-5 2026-09-20] 발송 조건에 등급이 생겼다(승패 = grade A).
            #    이 테스트가 재는 것은 **멱등성**이므로 등급만 A 로 올린다.
            n08_pcode={"p_code_pick": 0.707}, n09_conf={"grade": GRADE_A},
            n12_text={"sentences": ["1", "2", "3", "4"]},
            n05_evidence=[])
    ctx = Ctx(inject={"send": lambda t: sent.append(t) or True})
    st = await n13_send.run(st, ctx)
    assert st.n13_send["sent"] is True and len(sent) == 1
    # 같은 상태로 다시 부르면 — Redis 표시가 없으므로 호출부(run.py)가 막는다.
    # 여기서는 **카드가 두 번 만들어지지 않는다**는 것만 잰다.
    assert sent[0].count("픽") == 1


# ── [2026-09-18] ④ 파생 모델 배선 · 축구 2-way 정정

def test_파생확률은_scoring_모양을_이름만_옮긴다():
    """🔴 계산하지 않는다 — `scoring` 이 원본이고 여기서는 키만 맞춘다."""
    from app.flow.nodes.n08_pcode import _ours_markets

    mp = {"totals": {9.5: {"Over": 0.52, "Under": 0.48},
                     "8.5": {"Over": 0.64}},           # JSON 왕복 문자열 키
          "spreads": {1.5: {"home_minus": 0.38, "away_plus": 0.62}}}
    got = _ours_markets(mp)
    assert got["total_over"] == {9.5: 0.52, 8.5: 0.64}
    assert got["total_under"] == {9.5: 0.48}
    assert got["ah"] == {1.5: 0.38}
    assert _ours_markets(None) == {}                    # 없으면 빈 dict


@pytest.mark.asyncio
async def test_파생확률이_있으면_구조픽이_선다():
    """🔴 배선 전에는 후보가 언제나 0 이었다 — E2E 두 건이 그 상태였다."""
    st = _s(pick_side="away", n03_gate={"gate": AGREE},
            n02_market={"odds": {"away": 1.35},
                        "derivatives": {"total": {"line": 9.5, "over": 1.90}}},
            n07_adjust=[])
    st = await n08_pcode.run(
        _s(pick_side="away", n02_market={"p": {"away": 0.687}}, n07_adjust=[]),
        Ctx(inject={"model_probs": {"totals": {9.5: {"Over": 0.62}}}}))
    ours = st.n08_pcode["ours_markets"]
    assert ours["total_over"][9.5] == 0.62

    # 🔴 [FIX-4 2026-09-20] 구조 픽에 네 가지 조건이 더 붙었다. 의도(파생 확률이
    #    ⑪까지 흐른다)는 그대로 두고 그 입력을 채운다.
    #      a 가설이 마켓을 지정 · b 시장 동의(open 필요) · e 방향 증거 · d λ 절사 없음
    der = {"total": {"line": 9.5, "over": 1.90, "under": 1.95,
                     "open": {"over": 1.95, "under": 1.90}}}
    ev = [{"var": "starter_recent3", "direction": {"home": -1, "away": 0, "dev": 0.4}},
          {"var": "bullpen_3d", "direction": {"home": -1, "away": 0, "dev": 0.3}}]
    st2 = _s(pick_side="away", n03_gate={"gate": AGREE},
             n04_hyp=[{"id": "H_deriv", "market": "total", "vars": []}],
             n05_evidence=ev,
             n02_market={"odds": {"away": 1.35}, "derivatives": der},
             n08_pcode={"p_code_pick": 0.687, "ours_markets": ours},
             n09_conf={"grade": "B"})
    v = (await n11_value.run(st2, Ctx())).n11_value
    # 요구확률 1/1.90 = 0.5263 · 우리 0.62 → edge ≈ +9.4%p
    assert v["pick_type"] == "구조", v
    assert v["structure"]["market"] == "total_over"
    assert v["structure"]["edge_pp"] > 2.0
    assert v["struct_grade"] == "A", v          # 찬 2 · 반 0


@pytest.mark.asyncio
async def test_구조픽_가드_넷이_각각_막는다():
    """🔴 [FIX-4] 하나씩 빼면 각각 보드로 떨어져야 한다."""
    ours = {"total_over": {9.5: 0.62}}
    der = {"total": {"line": 9.5, "over": 1.90, "under": 1.95,
                     "open": {"over": 1.95, "under": 1.90}}}
    ev = [{"var": "starter_recent3", "direction": {"home": -1, "away": 0, "dev": 0.4}},
          {"var": "bullpen_3d", "direction": {"home": -1, "away": 0, "dev": 0.3}}]

    def base(**kw):
        d = dict(pick_side="away", n03_gate={"gate": AGREE},
                 n04_hyp=[{"id": "H_deriv", "market": "total", "vars": []}],
                 n05_evidence=ev,
                 n02_market={"odds": {"away": 1.35}, "derivatives": der},
                 n08_pcode={"p_code_pick": 0.687, "ours_markets": ours},
                 n09_conf={"grade": "B"})
        d.update(kw)
        return _s(**d)

    # a. 가설이 마켓을 지정하지 않음
    v = (await n11_value.run(base(n04_hyp=[{"id": "H_break", "vars": []}]), Ctx())).n11_value
    assert v["pick_type"] == "보드" and "지정하지" in v["reject_reason"], v

    # b. open 배당 없음 → fail closed
    der2 = {"total": {"line": 9.5, "over": 1.90, "under": 1.95}}
    v = (await n11_value.run(base(n02_market={"odds": {"away": 1.35},
                                              "derivatives": der2}), Ctx())).n11_value
    assert v["pick_type"] == "보드" and "시장 동의" in v["reject_reason"], v

    # d. λ 절사
    v = (await n11_value.run(base(n08_pcode={"p_code_pick": 0.687, "ours_markets": ours,
                                             "model_probs": {"clipped": {"home": 7.1}}}),
                             Ctx())).n11_value
    assert v["pick_type"] == "보드" and "절사" in v["reject_reason"], v

    # e. 방향 증거 없음
    v = (await n11_value.run(base(n05_evidence=[]), Ctx())).n11_value
    assert v["pick_type"] == "보드" and "방향" in v["reject_reason"], v

    # c. edge 상한 — 우리 확률을 올려 edge 를 12%p 이상으로
    v = (await n11_value.run(base(n08_pcode={"p_code_pick": 0.687,
                                             "ours_markets": {"total_over": {9.5: 0.70}}}),
                             Ctx())).n11_value
    assert v["pick_type"] == "보드" and "오류의심" in v["reject_reason"], v


def test_원정확률_규칙은_한_곳이다():
    """🔴 `1 - p_home` 은 축구에서 원정 확률이 아니다 — `prob.away_prob` 가 원본."""
    from app.engine.prob import away_prob

    assert away_prob({"sport": "kbo"}, 0.62) == 0.38
    # 무승부 질량을 모르면 **만들지 않는다**
    assert away_prob({"sport": "soccer"}, 0.62) is None
    assert away_prob({"sport": "soccer", "home": "A", "away": "B",
                      "market_probs": {"A": 0.62, "Draw": 0.24, "B": 0.14}},
                     0.62) == 0.14


def test_카드와_성능이_그_규칙을_쓴다():
    """🔴 세 자리가 각자 `1 - p` 를 적으면 그게 사본이다.

    실위험 지점(2026-09-18 전수 조사): `card.py` 한 줄 판정 · `performance.py`
    최종 줄과 `p_away` 칸. 셋 다 `prob.away_prob` 를 지나야 한다.
    """
    import inspect

    from app.engine import card as C
    from app.engine import performance as PF

    for mod in (C, PF):
        assert "away_prob" in inspect.getsource(mod), mod.__name__


# ── [2026-09-18 페이블 검토] ② doubt 제거 · ③ 선발 배선 · ⑥ n01 격리

def test_야구_need에_doubt가_없다():
    """🔴 실측 확인 0/30 — 구조화된 소스가 없다(FORKS F-15).

    ⚠️ **축구는 그대로다.** 그쪽은 개념도 소스도 있다 — 종목을 함께 지우면
       안 되는 것까지 지운다.
    """
    from app.engine import hypothesis as HY
    from app.flow import rules as R

    # flow(v1.4): 야구에서 뺐다. 축구 표에는 지시문 §1.2 부터 `doubt` 가 없다
    #   — 축구는 `xi_confirmed` 가 그 역할을 한다(확정 XI 대비 주전 결장).
    assert "doubt" not in R.vars_for("baseball")
    assert set(R.vars_for("soccer")) == {"xi_confirmed", "form_recent5",
                                         "rotation_risk", "travel", "motivation"}
    # 기존 경로: 야구만 뺐고 **축구는 그대로다** — 그쪽은 개념도 소스도 있다.
    assert HY._BASEBALL_OUT == ("out",)
    assert "doubt" in HY._SOCCER_OUT


def test_야구_핵심변수에_선발이_있다():
    """🔴 딥서치가 가장 강하게 지지한 축이다(FORKS F-16)."""
    from app.flow import rules as R

    assert "starter_recent3" in R.core_vars("baseball")


@pytest.mark.asyncio
async def test_선발_변경이_evidence로_들어온다():
    st = _s(pick_side="away", n03_gate={"gate": AGREE})
    st = await n04_hyp.run(st, Ctx())
    ctx = Ctx(inject={"starter_notes": ["홈 선발 변경: 문동주 → 박준영"],
                      "extract": {}, "absences": []})
    st = await n05_evidence.run(st, ctx)
    row = [e for e in st.n05_evidence if e["var"] == "starter_recent3"]
    assert row, st.n05_evidence
    assert row[0]["sides"] == {"home": 1}          # 홈 선발이 바뀌었다
    st = await n06_verdict.run(st, Ctx())
    assert st.n06_verdict["per_var"]["starter_recent3"] == "confirmed"


@pytest.mark.asyncio
async def test_상대_선발_변경은_우리에게_유리하다():
    """🔴 부호는 `sides` 가 정한다 — 한쪽으로 고정하면 근거와 반대로 움직인다."""
    st = _s(pick_side="away", n03_gate={"gate": AGREE})
    st = await n04_hyp.run(st, Ctx())
    ctx = Ctx(inject={"starter_notes": ["홈 선발 변경: 문동주 → 박준영"],
                      "extract": {}, "absences": []})
    st = await n05_evidence.run(st, ctx)
    st = await n06_verdict.run(st, Ctx())
    st = await n07_adjust.run(st, Ctx())
    adj = [a for a in st.n07_adjust if a["var"] == "starter_recent3"]
    assert adj and adj[0]["pp"] > 0, st.n07_adjust   # 픽(원정)에게 유리


def test_선발변경_문장_형식이_원본과_묶여_있다():
    """🔴 `starter_change_notes` 형식이 바뀌면 팀 분리가 조용히 깨진다.

    그 함수의 **실제 출력**으로 결합을 고정한다.
    """
    from app.flow.nodes.n05_evidence import _SIDE_KR
    from app.pipeline import starter_change_notes

    notes = starter_change_notes(
        {"home_pitcher": {"name": "박준영"}, "away_pitcher": {"name": "원태인"}},
        {"home": "문동주", "away": "원태인"})
    assert notes, notes
    assert any(n.startswith(ko) for n in notes for ko in _SIDE_KR), notes


def test_n01은_배당을_읽지_않는다():
    """🔴 [⑥ 페이블 검토] 사전값이 시장을 보면 그건 앵커링이다.

    CLAUDE.md "시장에 끌려가지 않는다" · FORKS F-17. 사전값이 배당을 보면
    "우리가 시장과 다르다"를 잴 수 없고, CLV 채점(F-4)의 전제가 무너진다.
    ⚠️ 주석이 아니라 **실행 줄**만 본다.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(n01_prior))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    code = ast.unparse(tree)
    for banned in ("n02_market", "odds", "market", "devig", "required_prob",
                   "odds_snapshots", "implied"):
        assert banned not in code.lower(), f"n01 이 시장을 읽는다: {banned}"


def test_n01은_자기_키만_쓴다():
    """🔴 지시문 규율 8 — 다른 노드 키를 고치면 배선 오류다."""
    import ast
    import inspect

    from app.flow.state import NODE_KEYS

    tree = ast.parse(inspect.getsource(n01_prior))
    writes = {t.attr for n in ast.walk(tree) if isinstance(n, ast.Assign)
              for t in n.targets if isinstance(t, ast.Attribute)}
    assert writes <= {"n01_prior", "pick_side"}, writes
    assert all(k not in writes for k in NODE_KEYS if k != "n01_prior")


# ── [2026-09-19] A 파생 주입 · B 시장 없이 가설 · C 불펜 배선

@pytest.mark.asyncio
async def test_시장이_없어도_가설이_선다():
    """🔴 [F-17] 데이터가 쌓여야 가설을 세우는 것이 아니다.

    사용자 지시: "시장에 끌려가지 않고 우리 쪽 판단을 먼저 적는 게 중요함".
    ⚠️ **사전값도 없으면** 그때는 보드 고정이다 — 찾을 것이 정말 없다.
    """
    from app.flow.labels import PRIOR_ONLY

    st = _s(pick_side="away",
            n01_prior={"p_away": 0.62, "p_home": 0.38},
            n02_market={"market_missing": True, "p": None})
    st = await n03_gate.run(st, Ctx())
    assert st.n03_gate["gate"] == PRIOR_ONLY
    assert st.n03_gate["stop"] is False, "시장이 없다고 멈추면 가설이 안 선다"

    st = await n04_hyp.run(st, Ctx())
    assert st.n04_hyp[0]["id"] == "H_break"
    assert st.n04_hyp[0]["vars"], "need 가 비었다"


@pytest.mark.asyncio
async def test_사전값도_없으면_보드고정이다():
    """🔴 반대 위험 — 없는 판단으로 조사를 시작하지 않는다."""
    st = _s(pick_side=None, n01_prior={"p_home": None, "p_away": None},
            n02_market={"market_missing": True, "p": None})
    st = await n03_gate.run(st, Ctx())
    assert st.n03_gate["gate"] == BOARD and st.n03_gate["stop"] is True


@pytest.mark.asyncio
async def test_시장이_오면_다시_분류된다():
    """🔴 시장은 가설을 **가능하게** 하는 것이 아니라 **검증**하는 것이다.
    방향이 뒤집히는 것은 결함이 아니라 검증이 작동한 것이다."""
    from app.flow.labels import PRIOR_ONLY

    st = _s(pick_side="away", n01_prior={"p_away": 0.62},
            n02_market={"market_missing": True, "p": None})
    assert (await n03_gate.run(st, Ctx())).n03_gate["gate"] == PRIOR_ONLY

    st.n02_market = {"market_missing": False, "p": {"away": 0.72}}
    g = (await n03_gate.run(st, Ctx())).n03_gate
    assert g["gate"] == OVER, g          # 시장이 더 높게 본다 → 방향이 뒤집힌다
    assert g["gap_pp"] == -10.0


@pytest.mark.asyncio
async def test_불펜_최근3일이_evidence로_들어온다():
    """🔴 핵심 변수인데 소스가 없어 언제나 `unknown` 이었다(실측 0건).
    `pitcher_appearances` 에 이미 있었다 — MLB 754행 · NPB 260행."""
    st = _s(pick_side="away", n03_gate={"gate": AGREE})
    st = await n04_hyp.run(st, Ctx())
    ctx = Ctx(inject={"bullpen": {"home": ["09-17 A 1.0이닝", "09-18 B 0.7이닝"],
                                  "away": ["09-18 C 2.0이닝"]},
                      "extract": {}, "absences": []})
    st = await n05_evidence.run(st, ctx)
    row = [e for e in st.n05_evidence if e["var"] == "bullpen_3d"]
    assert row, st.n05_evidence
    assert row[0]["sides"] == {"home": 2, "away": 1}
    assert row[0]["source"] == "db:pitcher_appearances"
    st = await n06_verdict.run(st, Ctx())
    assert st.n06_verdict["per_var"]["bullpen_3d"] == "confirmed"


def test_불펜은_선발을_세지_않는다():
    """🔴 불펜 소모를 재는 값이다 — 선발이 섞이면 숫자가 뒤집힌다."""
    from app.flow.nodes.n05_evidence import _BULLPEN_SQL

    assert "is_starter = false" in _BULLPEN_SQL
    assert "interval '3 days'" in _BULLPEN_SQL


def test_다리가_파생확률을_경기마다_주입한다():
    """🔴 `_ours_markets` 를 만들어 놓고 **넣는 배선을 안 했다** — 그래서
    구조 후보가 언제나 0 이었다. 슬레이트당 한 번 읽고 경기마다 갈아끼운다."""
    import inspect

    from app.flow import bridge as B

    # ⚠️ 문서 문자열을 통째로 지우면 **dict 키까지** 사라진다(`"model_probs"`).
    #    주석만 걷어내고 실행 줄을 본다.
    code = "\n".join(ln for ln in inspect.getsource(B).splitlines()
                     if ln.strip() and not ln.strip().startswith("#"))
    assert 'ctx.inject = {"model_probs"' in code, "경기마다 주입하지 않는다"
    # 🔴 경기마다 조회하면 질의가 N배다 — 슬레이트당 한 번이어야 한다.
    assert code.count("await pool.fetch(_MODEL_SQL") == 1
