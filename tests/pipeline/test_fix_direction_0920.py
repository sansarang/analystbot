"""[FIX-DIR 2026-09-20] 증거에 **방향**을 싣고, ⑦·⑨·⑪·⑬이 그것을 읽는다.

🔴 오늘 실측: 상대 선발이 6.0이닝 1자책(잘 던짐)인 경기와 4.0이닝 5자책(무너짐)인
   경기에 ⑦이 똑같이 `pp=3.0 sign=1.0 strength=1.0` 을 줬다. 부호가 내용을 안 봤다.
🔴 문턱은 `config/rules.yaml` 의 `flow.direction.*` 에만 둔다 — **미검증 사전값**이고
   채점 30건 뒤 데이터로만 고친다.
"""
from __future__ import annotations

import pytest


# ── FIX-1 선발 방향

def test_f0920_stl_잘_던진_상대_선발은_유리가_아니다():
    """픽스처 f0920_stl — 6.0이닝1자책 · 6.7이닝2자책 · 5.0이닝4자책."""
    from app.flow.direction import starter_direction

    rows = [{"innings": 6.0, "er": 1}, {"innings": 6.7, "er": 2}, {"innings": 5.0, "er": 4}]
    d = starter_direction(rows, league_era=4.20, team="home")
    assert d["home"] <= 0, d          # 상대(home) 악재가 아니다
    assert d["dev"] < 0, d


def test_f0920_laa_표본_부족은_0_에_짧은_등판_플래그():
    """픽스처 f0920_laa — 4.0이닝4자책 · 4.0이닝2자책 (이닝합 8 < 9)."""
    from app.flow.direction import starter_direction

    rows = [{"innings": 4.0, "er": 4}, {"innings": 4.0, "er": 2}]
    d = starter_direction(rows, league_era=4.20, team="away")
    assert d["away"] == 0, d
    assert "표본" in d["basis"], d
    assert "짧은 등판" in d["basis"], d


def test_한화_선발_ERA_6_10_은_상대에게_유리하다():
    """🔴 기존 픽스처가 그대로 통과해야 한다."""
    from app.flow.direction import starter_direction

    rows = [{"innings": 4.33, "er": 3}, {"innings": 4.33, "er": 3}, {"innings": 4.34, "er": 3}]
    d = starter_direction(rows, league_era=4.20, team="home")
    assert d["home"] == -1, d         # 그 선발을 내는 팀(home)의 악재
    assert d["dev"] > 0, d


def test_이닝이_0이면_방향이_없다():
    from app.flow.direction import starter_direction

    assert starter_direction([], league_era=4.20, team="home")["home"] == 0
    assert starter_direction([{"innings": 0, "er": 0}], league_era=4.20,
                             team="home")["home"] == 0


# ── FIX-1 불펜·라인업 방향

def test_불펜_과소모는_그_팀_악재():
    from app.flow.direction import bullpen_direction

    heavy = [{"pitcher": "A", "innings": 4.0, "d": "09-19"},
             {"pitcher": "B", "innings": 4.0, "d": "09-19"},
             {"pitcher": "C", "innings": 4.5, "d": "09-18"}]
    assert bullpen_direction(heavy, team="home")["home"] == -1
    light = [{"pitcher": "A", "innings": 1.0, "d": "09-19"}]
    assert bullpen_direction(light, team="home")["home"] == 0


def test_2연투_3명이면_악재():
    from app.flow.direction import bullpen_direction

    rows = [{"pitcher": p, "innings": 1.0, "d": d}
            for p in ("A", "B", "C") for d in ("09-19", "09-18")]
    assert bullpen_direction(rows, team="away")["away"] == -1


def test_확정_타순이_없으면_방향_0():
    from app.flow.direction import lineup_direction

    d = lineup_direction(excluded=3, confirmed=False, team="home")
    assert d["home"] == 0 and "미확정" in d["basis"]


def test_평소_주전_2명_이상_빠지면_악재():
    from app.flow.direction import lineup_direction

    assert lineup_direction(excluded=2, confirmed=True, team="home")["home"] == -1
    assert lineup_direction(excluded=1, confirmed=True, team="home")["home"] == 0


# ── FIX-1/2 n07 부호·강도

def test_부호는_양쪽_방향의_합이다():
    from app.flow.nodes.n07_adjust import _direction_of

    # 상대(home) 악재 → 우리(away) 픽에 유리
    assert _direction_of({"home": -1, "away": 0}, "away") == +1.0
    # 우리 쪽 악재 → 불리
    assert _direction_of({"home": 0, "away": -1}, "away") == -1.0
    # 상쇄
    assert _direction_of({"home": -1, "away": -1}, "away") == 0.0
    # 🔴 모르면 0 이다 (종전 −1 폐기)
    assert _direction_of({}, "away") == 0.0
    assert _direction_of(None, "away") == 0.0


def test_strength_는_편차_크기다():
    from app.flow.nodes.n07_adjust import _strength_of

    assert _strength_of(0.5, dev_full=0.5) == 1.0
    assert _strength_of(0.25, dev_full=0.5) == 0.5
    assert _strength_of(-0.25, dev_full=0.5) == 0.5
    assert _strength_of(None, dev_full=0.5) == 0.0


def test_숫자_정규식이_사라졌다():
    import inspect

    from app.flow.nodes import n07_adjust as N

    src = "\n".join(l.split("#")[0] for l in inspect.getsource(N).splitlines())
    assert "_NUM" not in src, "강도를 아직 정규식으로 정한다"


# ── FIX-4 구조 픽 — 이름 붙은 픽스처 두 개
#    ⚠️ 가드 다섯이 *각각* 막는지는 `test_nodes.py::test_구조픽_가드_넷이_각각_막는다`
#       가 잰다. 여기서는 지시문이 이름과 숫자를 지정한 두 경기만 재현한다.

def _struct_state(**kw):
    from app.flow.state import State

    st = State.new({"game_id": "g", "sport": "baseball", "league": "MLB",
                    "home": "COL", "away": "SEA"})
    st.pick_side = "away"
    st.n03_gate = {"gate": "가치의심"}
    st.n04_hyp = [{"id": "H_deriv", "market": "total", "vars": []}]
    st.n05_evidence = [
        {"var": "starter_recent3", "direction": {"home": -1, "away": 0, "dev": 0.4}},
        {"var": "bullpen_3d", "direction": {"home": -1, "away": 0, "dev": 0.3}},
    ]
    st.n02_market = {"odds": {"away": 1.95},
                     "derivatives": {"total": {"line": 11.5, "over": 1.90, "under": 1.95,
                                               "open": {"over": 1.95, "under": 1.90}}}}
    st.n08_pcode = {"p_code_pick": 0.52, "ours_markets": {"total_over": {11.5: 0.62}}}
    st.n09_conf = {"grade": "B"}
    for k, v in kw.items():
        setattr(st, k, v)
    return st


@pytest.mark.asyncio
async def test_f0920_col_람다가_잘린_경기는_구조_후보가_0():
    """픽스처 f0920_col — λ 가 `lam_max` 6.20 에 잘렸다(원값 7.05).

    🔴 잘린 λ 로 만든 파생 확률은 **모델의 값이 아니라 상한의 값**이다.
    """
    from app.flow.nodes import n11_value
    from app.flow.ctx import Ctx

    st = _struct_state(n08_pcode={"p_code_pick": 0.52,
                                  "ours_markets": {"total_over": {11.5: 0.62}},
                                  "model_probs": {"clipped": {"home": 7.05}}})
    v = (await n11_value.run(st, Ctx())).n11_value
    assert v["pick_type"] == "보드", v
    assert "절사" in v["reject_reason"] and "7.05" in v["reject_reason"], v
    assert v["structure"] is None, v


@pytest.mark.asyncio
async def test_f0920_edge_구조_edge_14_4pp_는_오류의심_보드():
    """픽스처 f0920_edge — edge 14.4%p. 🔴 큰 edge 는 강한 픽이 아니라 **신호**다."""
    from app.flow.nodes import n11_value
    from app.flow.ctx import Ctx
    from app.flow.odds_math import required_prob

    # 배당 1.90 → 요구확률. 여기에 +14.4%p 가 되도록 우리 확률을 맞춘다.
    p = round(required_prob(1.90) + 0.144, 4)
    st = _struct_state(n08_pcode={"p_code_pick": 0.52,
                                  "ours_markets": {"total_over": {11.5: p}}})
    v = (await n11_value.run(st, Ctx())).n11_value
    assert v["pick_type"] == "보드", v
    assert "오류의심" in v["reject_reason"] and "14.4" in v["reject_reason"], v


@pytest.mark.asyncio
async def test_f0920_laa_언더_픽은_오버_증거로_철회된다():
    """픽스처 f0920_laa 후반 — 총점 **언더** 후보인데 증거는 오버를 가리킨다.

    🔴 라인을 옮기지 않는다(언더를 오버로 바꾸지 않는다). **철회**다.
    """
    from app.flow.nodes import n11_value
    from app.flow.ctx import Ctx

    st = _struct_state()
    # 언더만 우리 확률이 있다 — 오버 쪽 후보는 아예 없다.
    st.n08_pcode = {"p_code_pick": 0.52, "ours_markets": {"total_under": {11.5: 0.62}}}
    v = (await n11_value.run(st, Ctx())).n11_value
    assert v["pick_type"] == "보드", v
    assert "방향(over)" in v["reject_reason"], v


@pytest.mark.asyncio
async def test_승패도_불리한_방향_증거면_보드로_내린다():
    """FIX-4f — ⑪이 승패 픽에도 같은 철회 규칙을 건다."""
    from app.flow.nodes import n11_value
    from app.flow.ctx import Ctx

    st = _struct_state()
    st.n03_gate = {"gate": "동의"}
    st.n08_pcode = {"p_code_pick": 0.62}
    # away 픽인데 away 가 악재 · home 이 호재 → 합 −2
    st.n05_evidence = [
        {"var": "starter_recent3", "direction": {"home": 0, "away": -1, "dev": 0.4}},
        {"var": "bullpen_3d", "direction": {"home": 0, "away": -1, "dev": 0.3}},
    ]
    v = (await n11_value.run(st, Ctx())).n11_value
    assert v["pick_type"] == "보드" and "-2" in v["reject_reason"], v


@pytest.mark.asyncio
async def test_타순_제외도_방향을_싣는다():
    """🔴 [FIX-1] `lineup_out` 만 옛 `sides` 경로로 돌고 있었다(실측 로그:
    `lineup_out 조정 없음 — dev=0.5 · 옛 sides 에서 옮김`).

    제외 수는 `absences.classify == BASIS_LINEUP` 로 센다 — IL 길이가 아니다.
    """
    from app.flow.ctx import Ctx
    from app.flow.nodes import n05_evidence
    from app.flow.state import State

    st = State.new({"game_id": "g", "sport": "baseball", "league": "MLB",
                    "home": "한화", "away": "삼성"})
    st.pick_side = "away"
    st.n03_gate = {"gate": "동의"}
    st.n04_hyp = [{"id": "H_x", "vars": [{"var": "lineup_out"}]}]
    # 한화 쪽 평소 주전 둘이 **오늘 라인업에서 빠짐** · 삼성은 IL 하나뿐
    # ⚠️ [HYC-1 2026-09-20] 상자 모양을 실제 위성 산출물과 같게 둔다 —
    #    `gathered_at`·`sources_fed` 가 없으면 ⑤가 카드를 쓰지 않는다.
    ctx = Ctx(inject={
        "extract": {"gathered_at": "2026-09-20T08:47:35+00:00",
                    "teams": {"home": {"out": ["한화 A 오늘 라인업에서 빠짐",
                                               "한화 B 오늘 라인업에서 빠짐"],
                                       "sources_fed": ["https://n.example/a"]},
                              "away": {"out": ["삼성 C Injured 10-Day"],
                                       "sources_fed": ["https://n.example/a"]}}},
        "absences": [],
    })
    st = await n05_evidence.run(st, ctx)
    row = next(e for e in st.n05_evidence if e["var"] == "lineup_out")
    d = row.get("direction") or {}
    assert d.get("home") == -1, d          # 한화 악재
    assert d.get("away") == 0, d           # IL 만으로는 방향 없음
    assert "평소 주전 2명" in str(d.get("basis")), d
