"""🔴🔴 **받은 자료에서 만든 변수** — 사용자 지시 2026-10-18.

> 선수 능력치, 갈래, **우리가 받은자료에서 변수 추가할것** ·
> **가나다 전부 변수에 닿게**

세는 것:
  DV1 손값이 **설정 표**에 있다(코드에 박지 않았다)
  DV2 가 — 선발 평균 백분위 차가 문턱을 넘으면 **변수**가 선다(A1)
  DV3 가 — 문턱 아래·인원 부족이면 **안 선다**(사유만)
  DV4 나 — 갈래를 **코드가 세운다**(LLM 주장 0 · B1·B2)
  DV5 다 — 선수 가치·상태 배율·포메이션 변화·득실 몰림이 변수가 된다
  DV6 **확률에 닿는다** — 다섯 유형이 배치표의 **축** 자리에 있고 λ 보정표가 센다
  DV7 운영·러너에 **배선**됐다
  DV8 LLM 을 **부르지 않는다**
"""
from __future__ import annotations

import pathlib

import pytest

from app.core import datavars as dv

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: 🔴 새 유형 다섯 — 선언·배치·λ 를 전부 센다(이름을 손으로 또 적지 않게 한 곳)
KINDS = ("squad_ability", "absence_quality", "branch_numbers",
         "squad_value", "state_rate")


class _R:
    id = "m1"
    home, away = "team:000001", "team:000002"
    home_name, away_name = "홈팀", "원정팀"
    competition = "Major League Soccer"


class _XI:
    def __init__(self, players=(), formation="4-4-2") -> None:
        self.players = list(players)
        self.formation = formation
        self.lineup: list = []
        self.bench: list = []
        self.source_url = ""


class _F:
    """🔴 대역은 **운영이 만드는 모양**이다(규율 #5)."""

    def __init__(self, **kw) -> None:
        self.standings: dict = {}
        self.recent: dict = {}
        self.xi: dict = {}
        self.missing: dict = {}
        self.coach: dict = {}
        self.last_xi: dict = {}
        self.past_xi: dict = {}
        self.schedule: dict = {}
        self.player_pos: dict = {}
        self.player_value: dict = {}
        self.player_stats: dict = {}
        self.squad: dict = {}
        self.state_rates: dict = {}
        self.venue: dict = {}
        for k, v in kw.items():
            setattr(self, k, v)


def _state():
    from app.core.state import RunState
    return RunState()


# ══════════════════════════════════════════════════════════════════
# DV1 손값은 설정 표에
# ══════════════════════════════════════════════════════════════════
def test_dv1_손값이_설정_표에_있다() -> None:
    import yaml
    box = yaml.safe_load((ROOT / dv.CONF).read_text(encoding="utf-8"))
    assert set(box) >= {"ability", "branches", "facts"}, box
    for key in ("squad_gap", "squad_min", "absence_gap", "tilt_gap",
                "tilt_lead"):
        assert key in box["ability"], key
    for key in ("value_ratio", "value_min", "state_gap", "form_changes",
                "blowout_ga", "blowout_lead"):
        assert key in box["facts"], key
    # 🔴 **코드에 손값을 박지 않았다** — 숫자가 글자로 들어 있지 않다
    src = (ROOT / "app/core/datavars.py").read_text(encoding="utf-8")
    body = "\n".join(x for x in src.splitlines()
                     if not x.lstrip().startswith("#"))
    for said in ("0.05", "1.30", "0.08"):
        assert said not in body, f"🔴 손값 `{said}` 가 코드에 박혔다"


# ══════════════════════════════════════════════════════════════════
# DV2·DV3 가 — 선발 평균 백분위(A1)
# ══════════════════════════════════════════════════════════════════
def _squad(n: int, pct: float) -> tuple[_F, dict]:
    """🔴 선발 `n` 명이 모두 백분위 `pct` 인 팀 둘(홈만 `pct`, 원정은 0.3)."""
    names_h = [f"H{i}" for i in range(n)]
    names_a = [f"A{i}" for i in range(n)]
    facts = _F(xi={"team:000001": _XI(names_h), "team:000002": _XI(names_a)},
               player_pos={**{x: "MF" for x in names_h},
                           **{x: "MF" for x in names_a}})
    box: dict = {}
    for i, nm in enumerate(names_h):
        box[str(1000 + i)] = {"traits": {"touches": pct,
                                         "defensive_actions": pct,
                                         "chances_created": pct,
                                         "aerials_won": pct,
                                         "goals": pct, "shot_attempts": pct}}
    for i, nm in enumerate(names_a):
        box[str(2000 + i)] = {"traits": {"touches": 0.3,
                                         "defensive_actions": 0.3,
                                         "chances_created": 0.3,
                                         "aerials_won": 0.3,
                                         "goals": 0.3, "shot_attempts": 0.3}}
    return facts, box


def test_dv2_선발_평균_백분위가_변수가_된다(monkeypatch) -> None:
    """🔴 A1 — 차가 문턱을 넘으면 **그쪽 유리**한 변수 하나."""
    facts, box = _squad(9, 0.80)

    def fake(facts_, ref_, side, box_, rule):
        return (0.80, 9, "대역") if side == "home" else (0.30, 9, "대역")

    from app.core import ability as _ab
    monkeypatch.setattr(_ab, "side_pct", fake)
    got = dv.from_ability(_R(), facts, box, state=_state())
    one = next((x for x in got if x.id == "AB1"), None)
    assert one is not None, [x.id for x in got]
    assert one.type == "squad_ability" and one.favors == "home", one
    assert "0.80" in one.claim and "0.30" in one.claim, one.claim
    # 🔴 벤치를 못 받는다는 사실이 글에 남는다(#3)
    assert "벤치" in one.claim, one.claim


def test_dv3_문턱_아래면_안_선다(monkeypatch) -> None:
    facts, box = _squad(9, 0.32)
    from app.core import ability as _ab
    monkeypatch.setattr(_ab, "side_pct",
                        lambda f, r, side, b, rule:
                        (0.32, 9, "대역") if side == "home"
                        else (0.30, 9, "대역"))
    st = _state()
    got = dv.from_ability(_R(), facts, box, state=st)
    assert not [x for x in got if x.id == "AB1"], got
    said = " ".join(st.notes)
    assert "안 센다" in said, said


def test_dv3b_인원이_적으면_안_선다(monkeypatch) -> None:
    facts, box = _squad(3, 0.90)
    from app.core import ability as _ab
    monkeypatch.setattr(_ab, "side_pct",
                        lambda f, r, side, b, rule:
                        (0.90, 3, "대역") if side == "home"
                        else (0.30, 3, "대역"))
    st = _state()
    got = dv.from_ability(_R(), facts, box, state=st)
    assert not [x for x in got if x.id == "AB1"], got
    assert any("미만" in x for x in st.notes), st.notes


# ══════════════════════════════════════════════════════════════════
# DV4 나 — 갈래를 **코드가** 세운다
# ══════════════════════════════════════════════════════════════════
def test_dv4_갈래를_코드가_세운다(monkeypatch) -> None:
    """🔴 LLM 주장 0 — 표의 갈래를 돌며 능력치로 가린다."""
    from app.core import ability as _ab
    facts, box = _squad(9, 0.8)
    said = {}

    def fake(kind, facts_, ref_, box_):
        said[kind] = True
        # 🔴 셋은 홈, 하나는 원정, 나머지는 **안 가려진다**
        order = sorted(dict(_ab.branch_table()))
        i = order.index(kind)
        return ((">", f"대역 {kind}") if i < 3 else
                ("<", f"대역 {kind}") if i == 3 else ("", f"대역 {kind}"))

    monkeypatch.setattr(_ab, "judge_branch", fake)
    got = dv.from_branches(_R(), facts, box, state=_state())
    # 🔴 갈래 이름을 **표에서** 받았다(사본 금지)
    assert said and set(said) <= set(dict(_ab.branch_table())), said
    kinds = [x.type for x in got]
    assert kinds and set(kinds) == {"branch_numbers"}, kinds
    # B1 네 개(가려진 것) + B2 묶음 하나
    assert len([x for x in got if x.id.startswith("BR-")]) == 4, got
    one = next((x for x in got if x.id == "BR0"), None)
    assert one is not None and one.favors == "home", got
    assert "갈래 묶음" in one.claim, one.claim


def test_dv4b_안_가려지면_변수가_없다(monkeypatch) -> None:
    from app.core import ability as _ab
    facts, box = _squad(9, 0.8)
    monkeypatch.setattr(_ab, "judge_branch",
                        lambda *a, **k: ("", "대역 — 차가 0.1 미만이다"))
    st = _state()
    got = dv.from_branches(_R(), facts, box, state=st)
    assert got == [], got
    assert any("안 가려졌다" in x for x in st.notes), st.notes


# ══════════════════════════════════════════════════════════════════
# DV5 다 — 받고 있던 자료 넷
# ══════════════════════════════════════════════════════════════════
def test_dv5_선수_가치가_변수가_된다() -> None:
    names_h = [f"H{i}" for i in range(8)]
    names_a = [f"A{i}" for i in range(8)]
    facts = _F(xi={"team:000001": _XI(names_h), "team:000002": _XI(names_a)},
               player_value={**{x: 10.0 for x in names_h},
                             **{x: 1.0 for x in names_a}})
    got = dv.from_facts(_R(), facts, state=_state())
    one = next((x for x in got if x.id == "DV3"), None)
    assert one is not None and one.type == "squad_value", [x.id for x in got]
    assert one.favors == "home" and "배" in one.claim, one.claim


def test_dv5b_상태_배율이_변수가_된다() -> None:
    facts = _F(state_rates={"home": {"뒤짐": {"득": 1.10}},
                            "away": {"뒤짐": {"득": 0.85}}})
    got = dv.from_facts(_R(), facts, state=_state())
    one = next((x for x in got if x.id == "DV4"), None)
    assert one is not None and one.type == "state_rate", [x.id for x in got]
    assert one.favors == "home" and "되돌리는" in one.claim, one.claim


def test_dv5c_포메이션_변화가_변수가_된다() -> None:
    rows = [_XI(formation=f) for f in ("4-4-2", "3-5-2", "4-3-3", "5-4-1")]
    facts = _F(past_xi={"team:000001": rows,
                        "team:000002": [_XI(formation="4-4-2") for _ in range(4)]})
    got = dv.from_facts(_R(), facts, state=_state())
    one = next((x for x in got if x.id == "DV6-home"), None)
    assert one is not None, [x.id for x in got]
    # 🔴 **흔든 팀의 상대**가 유리하다
    assert one.favors == "away" and one.type == "lineup_intent", one
    assert "바뀌었다" in one.claim, one.claim


def test_dv5d_득실_몰림이_변수가_된다() -> None:
    facts = _F(recent={
        "team:000001": {"sequence": [{"ga": 4, "date": "2026-10-15",
                                 "score": "0-4"},
                                {"ga": 1, "date": "2026-10-11"}]},
        "team:000002": {"sequence": [{"ga": 1, "date": "2026-10-15"}]}})
    got = dv.from_facts(_R(), facts, state=_state())
    one = next((x for x in got if x.id == "DV7"), None)
    assert one is not None and one.type == "recent_pattern", [x.id for x in got]
    assert one.favors == "away" and "몰린다" in one.claim, one.claim


def test_dv5e_감독은_사유만_남긴다() -> None:
    """🔴 C5 — 자료가 **이름뿐**이라 변수를 만들지 않는다(#3 사유로 남긴다)."""
    st = _state()
    dv.from_facts(_R(), _F(coach={"team:000001": object()}), state=st)
    assert any("감독" in x and "변수를 안 만든다" in x for x in st.notes), st.notes


# ══════════════════════════════════════════════════════════════════
# DV6 **확률에 닿는다**
# ══════════════════════════════════════════════════════════════════
def test_dv6_다섯_유형이_확률에_닿는다() -> None:
    """🔴🔴 사용자 지시 2026-10-18: *"가나다 전부 **변수에 닿게**"*.

    🔴 `flat_prob` 은 자리가 `AXES`·`CONST` 인 변수만 센다(`probmodel`).
       그래서 배치표의 자리와 λ 보정표를 **둘 다** 센다.
    """
    import yaml

    from app.core import routing as rt
    box = yaml.safe_load((ROOT / "config/variable_routing.yaml")
                         .read_text(encoding="utf-8"))
    types = dict(box.get("types") or {})
    ax = {*rt.AXES, rt.CONST}
    for kind in KINDS:
        row = dict(types.get(kind) or {})
        said = {str(x) for x in (row.get("places") or [])}
        assert said & ax, f"🔴 `{kind}` 가 확률에 안 닿는다 — 자리 {said}"
    fav = (((box.get("lambda_rules") or {}).get("by_var") or {})
           .get("favors") or {})
    said_t = {str(x) for x in (fav.get("types") or [])}
    for kind in KINDS:
        assert kind in said_t, f"🔴 λ 보정표가 `{kind}` 를 안 센다"
    # 🔴 유형 선언도 있어야 한다(없으면 축구 enum 밖이다 — 실사고 2026-10-17)
    decl = yaml.safe_load((ROOT / "config/variable_types.yaml")
                          .read_text(encoding="utf-8"))
    rows = dict(decl.get("types") or {})
    for kind in KINDS:
        assert kind in rows, f"🔴 `{kind}` 유형 선언이 없다"
        assert "soccer" in (rows[kind].get("sports") or []), kind
    # 🔴 DB 검사에도 있어야 한다(안 넣으면 저장이 터진다)
    said_sql = (ROOT / "db/schema.sql").read_text(encoding="utf-8")
    for kind in KINDS:
        assert f"'{kind}'" in said_sql, f"🔴 `{kind}` 가 DB 유형 검사에 없다"


def test_dv6b_실제로_확률을_민다() -> None:
    """🔴 글자 검사로 끝내지 않는다 — `flat_prob` 에 넣어 **움직이는지** 본다."""
    from app.core import probmodel as pm
    from app.core.routing import place
    rows = [dv._var("AB1", "squad_ability", _R(), "home", "대역 — 홈이 높다")]
    varset = place(rows)
    got, why = pm.flat_prob(varset, ref=_R())
    assert got["home"] > got["away"], (got, why)
    assert "AB1" in why, why


# ══════════════════════════════════════════════════════════════════
# DV7·DV8 배선 · LLM 금지
# ══════════════════════════════════════════════════════════════════
def test_dv7_운영에_배선됐다() -> None:
    said = (ROOT / "app/core/pipeline.py").read_text(encoding="utf-8")
    assert "datavars as _dvar" in said, "🔴 운영이 안 부른다"
    assert "_dvar.run(ref, facts, said_sq" in said, "🔴 능력치를 안 넘긴다"
    # 🔴 **배치를 다시 세우기 전**이어야 새 변수가 확률 자리에 들어간다
    i = said.index("_dvar.run(")
    j = said.index("⑤-b4 변수 배치 다시")
    assert i < j, "🔴 배치 뒤에서 만들면 확률에 안 닿는다"
    # 🔴 C1 순위 동기도 같은 자리에서 배선됐다(지시 2026-10-18 *"다"*)
    assert "s4c_leagueread as _lr" in said, "🔴 C1 순위 동기가 미배선이다"
    assert "_lr.variable(ref, got_lr)" in said, "🔴 C1 변수를 안 만든다"


def test_dv8_llm_을_부르지_않는다() -> None:
    """🔴 사용자 지시 2026-10-18 — *"llm 은 **서치용**으로 사용한다"*."""
    said = (ROOT / "app/core/datavars.py").read_text(encoding="utf-8")
    body = "\n".join(x for x in said.splitlines()
                     if not x.lstrip().startswith("#"))
    for bad in ("llm.ask", "llm_ask", "purpose="):
        assert bad not in body, f"🔴 `{bad}` 를 부른다(서치용만 허용)"


def test_dv9_터져도_카드는_나온다(monkeypatch) -> None:
    """🔴 §5 — 한 집안이 터져도 **빈 목록 + 사유**다."""
    monkeypatch.setattr(dv, "from_ability",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    st = _state()
    got, why = dv.run(_R(), _F(), {}, state=st)
    assert isinstance(got, list) and "가 능력치 🔴 터졌다" in why, why
    assert any("터졌다" in x for x in st.notes), st.notes


@pytest.mark.parametrize("kind", KINDS)
def test_dv10_유형마다_설명이_있다(kind: str) -> None:
    """🔴 카탈로그가 그 유형을 설명해야 한다(사람이 카드에서 읽는다)."""
    from app import classify
    said = dict(getattr(classify, "NOT_CLASSIFIED", None) or {})
    assert kind in said, f"🔴 `{kind}` 설명이 없다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **5경기 실제 실력 · 흐름(폼)** — 사용자 지시 2026-10-18
# ══════════════════════════════════════════════════════════════════
#
#  > 5경기를 통하여 **두팀의 실제 실력**을 가늠하기 위함이다
#  > 5경기에서 더 확인해야 할거는 **흐름**이다 .. **상세하게**
def _tab(n: int = 15) -> dict:
    """🔴 순위표 대역 — `rank` 1..n · 이름 `T1`..`Tn`(운영이 주는 꼴)."""
    return {"group": {"group": "Western",
                      "rows": [{"rank": i, "name": f"T{i}", "played": 29,
                                "points": 60 - i, "zone": ""}
                               for i in range(1, n + 1)]}}


def _game(date: str, side: str, opp: str, gf: int, ga: int) -> dict:
    return {"date": date, "side": side, "opponent": opp,
            "goals_for": gf, "goals_against": ga,
            "result": "W" if gf > ga else "L" if gf < ga else "D",
            "score": f"{gf}-{ga}"}


def test_st1_상대_수준을_센다() -> None:
    """🔴 홈은 **상위권**(1~4위)과, 원정은 **하위권**(12~15위)과 붙었다."""
    facts = _F(standings=_tab(), recent={
        "team:000001": {"sequence": [_game("10-15", "home", f"T{i}", 1, 1)
                                     for i in (1, 2, 3, 4)]},
        "team:000002": {"sequence": [_game("10-15", "away", f"T{i}", 1, 1)
                                     for i in (12, 13, 14, 15)]}})
    st = _state()
    got = dv.from_strength(_R(), facts, state=st)
    one = next((x for x in got if x.id == "ST1"), None)
    assert one is not None, [x.id for x in got]
    # 🔴 **센 일정을 치른 쪽**(순위가 작다)이 유리하다
    assert one.favors == "home", one.claim
    assert "더 센 일정" in one.claim and "오늘 순위" in one.claim, one.claim


def test_st3_상위권_상대_전적을_센다() -> None:
    """🔴 홈은 상위권 상대로 2승, 원정은 상위권 상대로 2패."""
    facts = _F(standings=_tab(), recent={
        "team:000001": {"sequence": [_game("10-15", "home", "T1", 2, 0),
                                     _game("10-11", "home", "T2", 1, 0),
                                     _game("10-01", "home", "T14", 0, 3)]},
        "team:000002": {"sequence": [_game("10-15", "away", "T1", 0, 2),
                                     _game("10-11", "away", "T2", 0, 1),
                                     _game("10-01", "away", "T14", 3, 0)]}})
    got = dv.from_strength(_R(), facts, state=_state())
    one = next((x for x in got if x.id == "ST3"), None)
    assert one is not None, [x.id for x in got]
    assert one.favors == "home" and "상위권 상대에 강하다" in one.claim, one


def test_st_순위표가_없으면_안_선다() -> None:
    st = _state()
    got = dv.from_strength(_R(), _F(recent={"team:000001": {"sequence": []}}),
                           state=st)
    assert got == [], got
    assert any("순위표가 없다" in x for x in st.notes), st.notes


def test_fl1_추세는_순서로_본다() -> None:
    """🔴🔴 평균이 **같은데** 순서가 다른 두 팀 — 추세가 갈라야 한다.

    홈: 앞 `-2,-2` → 최신 `+2,+2`(오른다) · 원정: 앞 `+2,+2` → 최신 `-2,-2`.
    ⚠️ 두 팀 **평균 득실은 0 으로 같다** — `S01` 은 이 둘을 못 가린다.
    """
    facts = _F(recent={
        "team:000001": {"sequence": [_game("10-15", "home", "T1", 3, 1),
                                     _game("10-11", "home", "T2", 3, 1),
                                     _game("10-05", "home", "T3", 1, 3),
                                     _game("10-01", "home", "T4", 1, 3)]},
        "team:000002": {"sequence": [_game("10-15", "away", "T1", 1, 3),
                                     _game("10-11", "away", "T2", 1, 3),
                                     _game("10-05", "away", "T3", 3, 1),
                                     _game("10-01", "away", "T4", 3, 1)]}})
    got = dv.from_flow(_R(), facts, state=_state())
    one = next((x for x in got if x.id == "FL1"), None)
    assert one is not None, [x.id for x in got]
    assert one.favors == "home" and one.goals == "up", one
    assert "흐름이 오른다" in one.claim and "순서" in one.claim, one.claim


def test_fl2_최신에_무게를_준다() -> None:
    facts = _F(recent={
        "team:000001": {"sequence": [_game("10-15", "home", "T1", 4, 0),
                                     _game("10-11", "home", "T2", 0, 1),
                                     _game("10-05", "home", "T3", 0, 1)]},
        "team:000002": {"sequence": [_game("10-15", "away", "T1", 0, 4),
                                     _game("10-11", "away", "T2", 1, 0),
                                     _game("10-05", "away", "T3", 1, 0)]}})
    got = dv.from_flow(_R(), facts, state=_state())
    one = next((x for x in got if x.id == "FL2"), None)
    assert one is not None and one.favors == "home", [x.id for x in got]
    assert "최신 쪽 폼" in one.claim, one.claim


def test_fl3_홈원정을_쪼개지_않는다() -> None:
    """🔴🔴 **과거는 홈원정 구분하지 마라** — 사용자 지시 2026-10-18.

    ⚠️ 종전 `FL3` 은 오늘 홈팀을 **과거 홈 경기**로만 봤다. 🔴 그 쪼갬을
       지웠다 — 쪼개면 표본이 다섯에서 둘·셋으로 줄어 평균이 몇 경기에
       휘둘린다.
    🔴 그래서 센다: **`FL3` 변수가 나오지 않는다** · 그 손값도 표에 없다.
    """
    import yaml
    facts = _F(recent={
        "team:000001": {"sequence": [_game("10-15", "home", "T1", 3, 0),
                                     _game("10-11", "home", "T2", 2, 0),
                                     _game("10-05", "away", "T3", 0, 5)]},
        "team:000002": {"sequence": [_game("10-15", "away", "T1", 0, 2),
                                     _game("10-11", "away", "T2", 0, 1),
                                     _game("10-05", "home", "T3", 5, 0)]}})
    got = dv.from_flow(_R(), facts, state=_state())
    assert not [x for x in got if x.id == "FL3"], [x.id for x in got]
    box = yaml.safe_load((ROOT / dv.CONF).read_text(encoding="utf-8"))
    flow = dict(box.get("flow") or {})
    for gone in ("side_min", "side_gap"):
        assert gone not in flow, f"🔴 손값 `{gone}` 가 아직 표에 있다"
    src = (ROOT / "app/core/datavars.py").read_text(encoding="utf-8")
    assert "def _side_form(" not in src, "🔴 그 함수가 아직 있다"


def test_fl4_흔들림은_폭이_작은_쪽이다() -> None:
    facts = _F(recent={
        "team:000001": {"sequence": [_game("10-15", "home", "T1", 1, 0),
                                     _game("10-11", "home", "T2", 1, 1),
                                     _game("10-05", "home", "T3", 0, 1)]},
        "team:000002": {"sequence": [_game("10-15", "away", "T1", 5, 0),
                                     _game("10-11", "away", "T2", 0, 5),
                                     _game("10-05", "away", "T3", 1, 1)]}})
    got = dv.from_flow(_R(), facts, state=_state())
    one = next((x for x in got if x.id == "FL4"), None)
    assert one is not None, [x.id for x in got]
    # 🔴 **덜 흔들리는 쪽**이 유리하다
    assert one.favors == "home" and "덜 흔들린다" in one.claim, one


def test_fl_흐름도_확률에_닿는다() -> None:
    """🔴 `flat_prob` 에 넣어 **움직이는지** 본다(글자 검사로 끝내지 않는다)."""
    from app.core import probmodel as pm
    from app.core.routing import place
    rows = [dv._var("FL1", "recent_pattern", _R(), "home", "대역", goals="up"),
            dv._var("ST3", "squad_ability", _R(), "home", "대역")]
    got, why = pm.flat_prob(place(rows), ref=_R())
    assert got["home"] > got["away"], (got, why)
    assert "FL1" in why and "ST3" in why, why


def test_dv_run_이_다섯_집안을_돈다() -> None:
    """🔴 `run` 이 가·나·다·실력·흐름을 **다** 돈다(하나라도 빠지면 빨개진다)."""
    st = _state()
    _got, why = dv.run(_R(), _F(), {}, state=st)
    for said in ("가 능력치", "나 갈래", "다 사실", "실력", "흐름"):
        assert said in why, (said, why)


def test_goals_부호는_주어_기준이다() -> None:
    """🔴🔴 **실사고 2026-10-18** — `side=="away"` 일 때 반대쪽을 밀었다.

    `flat_prob` 은 `goals` 를 **주어 팀 기준**으로 읽는다
    (`want = side if goals=="up" else 반대편`). 🔴 `_var` 의 주어는 **유리한
    팀**이므로 `goals` 는 **늘 `up`** 이어야 한다.
    ⚠️ 종전엔 `("up" if side=="home" else "down")` 를 넘겨, 원정이 유리한
       흐름 변수가 **홈을 밀었다**(캔자스 5차 로그: `[FL1] home ×1.05(goals
       down)` — 글은 홈 흐름이 오른다였는데 부호가 어긋났다).
    """
    from app.core import probmodel as pm
    from app.core.routing import place
    for side, other in (("home", "away"), ("away", "home")):
        one = dv._var("FL1", "recent_pattern", _R(), side, "대역", goals="up")
        assert one.goals == "up", one
        got, why = pm.flat_prob(place([one]), ref=_R())
        assert got[side] > got[other], (side, got, why)
    # 🔴 코드에 그 꼴이 다시 생기면 빨개진다
    src = (ROOT / "app/core/datavars.py").read_text(encoding="utf-8")
    assert 'if side == "home" else "down"' not in src, "🔴 그 버그가 돌아왔다"
