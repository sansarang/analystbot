"""U13 계약 — 상수표·마감·채점.

🔴 이 파일의 핵심은 **값이 안 바뀌었다**는 것이다. U13 은 상수를 yaml 로
   옮기기만 했다. 하나라도 달라지면 U5~U12 판정이 전부 달라진다.
"""
import importlib
import logging
import pathlib

import pytest

from app.engine import rules as R


def test_rules_yaml이_로드된다():
    assert pathlib.Path("config/rules.yaml").exists()
    assert R.from_file() is True, "yaml 이 있는데 기본값으로 돌고 있다"
    assert R.load()


@pytest.mark.parametrize("mod,attr,path", [
    ("app.engine.adjust", "OUT_MULT", "adjust.out_mult"),
    ("app.engine.adjust", "OUT_CAP", "adjust.out_cap"),
    ("app.engine.adjust", "RETURN_MULT", "adjust.return_mult"),
    ("app.engine.adjust", "MIN_CONTRIB_PP", "adjust.min_contrib_pp"),
    ("app.engine.adjust", "RECENT_STARTS_N", "adjust.recent_starts_n"),
    ("app.engine.odds_move", "STEAM_MIN_BOOKS", "odds_move.steam_min_books"),
    ("app.engine.odds_move", "STEAM_MIN_PP", "odds_move.steam_min_pp"),
    ("app.engine.odds_move", "DISAGREE_SD_PP", "odds_move.disagree_sd_pp"),
    ("app.engine.odds_move", "LINE_PP_PER_HALF", "odds_move.line_pp_per_half"),
    ("app.engine.structure", "EDGE_MIN_PP", "structure.edge_min_pp"),
    ("app.engine.structure", "GRADE_HIGH_PP", "structure.grade_high_pp"),
    ("app.engine.hypothesis", "SUFFICIENT_DEFAULT",
     "hypothesis.sufficient_default"),
    ("app.engine.hypothesis", "SUFFICIENT_BIGMATCH",
     "hypothesis.sufficient_bigmatch"),
    ("app.engine.prob", "ADJ_SHRINK", "prob.adj_shrink"),
    ("app.engine.prob", "ADJ_SUM_CAP", "prob.adj_sum_cap"),
])
def test_모듈_상수는_yaml에서_온다(mod, attr, path):
    m = importlib.import_module(mod)
    assert getattr(m, attr) == R.get(path)


#: 🔴 U13 착수 시점(2026-09-15) 실측값. **이 표를 코드가 읽지 않는다** —
#   테스트만 본다. 값이 바뀌면 여기서 빨개지고, 그때 사용자가 결정한다.
_FROZEN = {
    "adjust.out_mult": 1.5, "adjust.out_cap": 6.0, "adjust.return_mult": 1.5,
    "adjust.min_contrib_pp": 2.0, "adjust.recent_starts_n": 10,
    "odds_move.steam_min_books": 3, "odds_move.steam_min_pp": 3.0,
    "odds_move.disagree_sd_pp": 2.0, "odds_move.line_pp_per_half": 4.0,
    "structure.edge_min_pp": 6.0, "structure.grade_high_pp": 8.0,
    "hypothesis.sufficient_default": 2, "hypothesis.sufficient_bigmatch": 3,
    "hypothesis.unknown_board_ratio": 0.5,
    "prob.adj_shrink": 0.5, "prob.adj_sum_cap": 6.0,
}


def test_값이_종전_상수와_같다():
    """반대 위험 — 옮기다 값이 바뀌면 판정이 통째로 달라진다."""
    bad = {k: (R.get(k), v) for k, v in _FROZEN.items() if R.get(k) != v}
    assert not bad, f"값이 바뀌었다: {bad}"


def test_구조_핸디_라인도_그대로():
    from app.engine import structure as ST
    assert ST.AH_LINES == (0.5, 1.0, 1.5)


def test_사례집_배점_합은_1():
    from app.engine import cases as CS
    assert round(sum(CS.WEIGHTS.values()), 6) == 1.0


def test_파일이_없으면_기본값이고_경고가_남는다(monkeypatch, caplog):
    """🔴 반대 위험 — CFG-1: 설정이 이미지에 안 올라가도 **조용히** 돌았다."""
    monkeypatch.setattr(R, "RULES_PATH", pathlib.Path("/없는/rules.yaml"))
    with caplog.at_level(logging.WARNING):
        R.load(force=True)
    assert R.from_file() is False
    assert any("rules" in r.message.lower() or "rules" in str(r.msg).lower()
               for r in caplog.records), "경고 없이 기본값으로 돌았다"
    assert R.get("adjust.out_mult") == 1.5
    R.load(force=True)          # 원복


def test_없는_키는_기본값이다():
    assert R.get("없는.키") is None
    assert R.get("없는.키", 7) == 7


# ───────────────────────── 리포트

def test_표본0이어도_리포트_골격이_나온다():
    from app.engine import report as RP
    h = RP.hygiene([])
    assert h["n"] == 0 and h["checkpoints"] == [50, 150, 300]
    # 🔴 표본이 없으면 None 이다. 0 으로 채우지 않는다.
    assert h["위생"]["가설_있음"] is None
    assert h["방향"]["적중률"] is None and h["방향"]["브라이어"] is None
    assert RP.by_axis([])["groups"] == {}
    assert RP.source_score([])["domains"] == {}
    assert RP.cancel_clv([])["판정"] == "표본 없음"


def test_위생_리포트는_50_150_300_구간():
    from app.engine import report as RP
    assert RP.hygiene([{} for _ in range(49)])["reached"] is None
    assert RP.hygiene([{} for _ in range(50)])["reached"] == 50
    assert RP.hygiene([{} for _ in range(299)])["reached"] == 150
    assert RP.hygiene([{} for _ in range(300)])["reached"] == 300


def test_축별_CLV는_main_axis로_묶는다():
    from app.engine import report as RP
    rows = [{"main_axis": "결장", "hit": 1, "p": 0.6, "clv": 2.0},
            {"main_axis": "결장", "hit": 0, "p": 0.6, "clv": -1.0},
            {"main_axis": "휴식", "hit": 1, "p": 0.55, "clv": 3.0}]
    out = RP.by_axis(rows)
    assert out["groups"]["결장"]["n"] == 2
    assert out["groups"]["결장"]["적중률"] == 0.5
    assert out["groups"]["휴식"]["평균_CLV"] == 3.0
    # 같은 함수로 flow_class 도 묶인다 — 축마다 함수를 늘리지 않는다
    assert RP.by_axis([{"flow_class": "steam", "hit": 1}],
                      key="flow_class")["groups"]["steam"]["n"] == 1


def test_채점_안된_행은_브라이어에서_빠진다():
    from app.engine import report as RP
    rows = [{"p": 0.6, "hit": 1}, {"p": 0.7, "hit": None}, {"p": None, "hit": 0}]
    assert RP.hygiene(rows)["방향"]["채점됨"] == 2
    assert RP.hygiene(rows)["방향"]["브라이어"] == pytest.approx((0.6 - 1) ** 2)


def test_source_score는_도메인별_결장_적중():
    from app.engine import report as RP
    rows = [{"source": "transfermarkt.com", "claimed": ["A", "B"],
             "actual": ["A"]},
            # 🔴 actual 이 없으면 **세지 않는다** — 라인업을 못 받은 경기다
            {"source": "transfermarkt.com", "claimed": ["C"], "actual": None}]
    out = RP.source_score(rows)
    d = out["domains"]["transfermarkt.com"]
    assert d["games"] == 1 and d["claimed"] == 2 and d["hit"] == 1
    assert d["정확도"] == 0.5


def test_취소건_가상_CLV():
    from app.engine import report as RP
    rows = [{"watch_state": "취소", "cancel_virtual_clv": 2.0},
            {"watch_state": "취소", "cancel_virtual_clv": 1.0},
            {"watch_state": "추천", "cancel_virtual_clv": 9.0}]
    out = RP.cancel_clv(rows)
    assert out["취소건"] == 2 and out["평균_가상CLV"] == 1.5
    assert out["판정"] == "취소가 손해였다"


# ───────────────────────── 사례집 outcome

def test_fill_outcome은_채점된_행만_본다():
    from app.engine import cases as CS
    out = CS.fill_outcome(
        [{"game_id": 1}, {"game_id": 2}, {"game_id": 3}, {"game_id": 9}],
        [{"game_id": 1, "hit": 1, "clv": 2.5},
         {"game_id": 2, "hit": None},              # 아직 결과 없음
         {"game_id": 3, "hit": 0, "void": True}])
    assert out[0]["outcome"] == CS.WON and out[0]["clv"] == 2.5
    assert "outcome" not in out[1], "채점 안 된 경기를 실패로 셌다"
    assert out[2]["outcome"] == CS.PUSH
    assert "outcome" not in out[3], "원장에 없는 경기를 지어냈다"


def test_스키마_칸_3개가_있다():
    src = pathlib.Path("db/schema.sql").read_text(encoding="utf-8")
    for col in ("clv_line_shift", "flow_class", "cancel_virtual_clv"):
        assert col in src
