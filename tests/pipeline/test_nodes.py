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
async def test_시장이_없으면_보드고정이고_멈춘다():
    st = _s(pick_side="home", n01_prior={"p_home": 0.6},
            n02_market={"market_missing": True, "p": None})
    g = (await n03_gate.run(st, Ctx())).n03_gate
    assert g["gate"] == BOARD and g["stop"] is True


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
    ctx = Ctx(inject={"extract": {"home": {"out": ["기사선수"]}, "away": {"out": []}},
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

async def _verdict(per_evidence):
    st = _s(pick_side="away", n03_gate={"gate": AGREE})
    st = await n04_hyp.run(st, Ctx())
    st.n05_evidence = [{"var": k, "value": v, "raw_excerpt": "x"}
                       for k, v in per_evidence.items()]
    return (await n06_verdict.run(st, Ctx())).n06_verdict


@pytest.mark.asyncio
async def test_핵심_반증_하나면_반박됨():
    v = await _verdict({"starter_recent3": [], "bullpen_3d": ["a"],
                        "lineup_out": ["b"]})
    assert v["verdict"] == V_REFUTED
    assert v["core_refuted"] == ["starter_recent3"]


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
    st = _s(n06_verdict={"per_var": {"lineup_out": "confirmed"}},
            n05_evidence=[{"var": "lineup_out", "raw_excerpt": "결장자 있음"}])
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
    base = {"per_var": {"starter_recent3": "confirmed", "bullpen_3d": "confirmed"}}
    a = await n09_conf.run(_s(n06_verdict=base, n08_pcode={"sum_adj_pp": -3.5}), Ctx())
    assert a.n09_conf["grade"] == GRADE_A
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
            n08_pcode={"p_code_pick": 0.707}, n09_conf={"grade": GRADE_B},
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

    st2 = _s(pick_side="away", n03_gate={"gate": AGREE},
             n02_market={"odds": {"away": 1.35},
                         "derivatives": {"total": {"line": 9.5, "over": 1.90}}},
             n08_pcode={"p_code_pick": 0.687, "ours_markets": ours})
    v = (await n11_value.run(st2, Ctx())).n11_value
    # 요구확률 1/1.90 = 0.5263 · 우리 0.62 → edge ≈ +9.4%p
    assert v["pick_type"] == "구조", v
    assert v["structure"]["market"] == "total_over"
    assert v["structure"]["edge_pp"] > 2.0


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
