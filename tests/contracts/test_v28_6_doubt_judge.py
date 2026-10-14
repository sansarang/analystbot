"""🔴🔴 계약 — **§4 판정(확신 · 보류 · 역배)**(의심 검증 v2 · 2026-10-14i §4·§7).

| 조항 | 여기서 무엇을 본다 |
|---|---|
| §4 확신 | 의심 후 ≥ 문턱 **그리고** 구간 하한도 문턱 근처 |
| §4 역배 | **반대쪽** 구간 하한 > 50% **그리고** 시즌 교차 |
| §4 보류 | 칸 없음·칸 보류·문턱 없음·1단 보류는 **전부 보류** |
| §4 자 | 🔴 문턱은 **의심 후 확률 자**다 — 봇 원확률 자와 섞지 않는다 |
| §7 | 칠 표는 **확신·역배만** 받고 역배는 **표시만**(다리 금지) |
| DB4 | 🔴 확률 경로가 이 모듈을 부르지 않는다 |
"""
from __future__ import annotations

from app.core import doubt as db
from app.core import picks as pk

#: 🔴 그 칸 꼴 — `tools/fit_doubt.say_cell` 이 적는 그대로다
def _cell(p: float, lo: float, hi: float, *, n: int = 300,
          p_lo: float = 0.40, p_hi: float = 1.01, hold: bool = False,
          cross: object = True) -> dict:
    return {"구간": f"{p_lo:.0%}~{p_hi:.0%}", "p_lo": p_lo, "p_hi": p_hi,
            "n": n, "봇평균": 0.5, "실측": p, "lo": lo, "hi": hi,
            "반대쪽실측": 1 - p, "실보드": n, "근사": 0,
            "시즌교차": cross, "보류": hold}


def _box(cell: dict, kind: str = db.WIN, bucket: str = "0") -> dict:
    return {kind: {bucket: [cell]}}


def test_판정_글자는_셋뿐이다():
    assert (db.SURE, db.HOLD, db.FADE) == ("확신", "보류", "역배")
    assert db.bucket_of(0) == "0" and db.bucket_of(1) == "1"
    assert db.bucket_of(2) == "2+" and db.bucket_of(9) == "2+"


def test_줄_이름을_줄_종류로_가른다():
    assert db.kind_of("핸디 home-0.5") == db.AH
    assert db.kind_of("오버 2.5") == db.OU and db.kind_of("언더 2.5") == db.OU
    for one in ("홈 승", "원정 승", "무"):
        assert db.kind_of(one) == db.WIN
    assert db.kind_of("") == ""


def test_문턱은_의심_후_자에_있다():
    """🔴🔴 §4 — 봇 원확률 자(0.88)와 **섞으면 아무것도 안 나온다**.

    ⚠️ 실측 2026-10-14: 보정표에서 가장 높은 칸이 **67.1%**(승무패 50%+)다.
       원확률 문턱을 그대로 쓰면 *"문턱이 높아 보류"* 가 아니라 **기계가 멈춘
       것**이 된다.
    """
    cut = float(dict(db.table().get("cuts") or {}).get("확신") or 0.0)
    assert 0.5 <= cut <= 0.7, f"확신 문턱 {cut} 이 의심 후 자를 벗어난다"
    assert cut < pk.CUT_SINGLE, "두 자가 섞였다"


def test_확신은_하한도_문턱_근처여야_한다():
    cut = float(dict(db.table().get("cuts") or {}).get("확신"))
    slack = float(dict(db.table().get("cuts") or {}).get("확신_하한_여유"))
    # 🔴 실측도 문턱 위 · 하한도 여유 안 → 확신
    ok = db.judge({"홈 승": 0.52}, box=_box(_cell(cut + 0.05, cut, cut + 0.1)))
    assert ok.rows[0].verdict == db.SURE, ok.why
    # 🔴 실측은 넘는데 **하한이 멀다** → 보류
    bad = db.judge({"홈 승": 0.52},
                   box=_box(_cell(cut + 0.05, cut - slack - 0.05, cut + 0.2)))
    assert bad.rows[0].verdict == db.HOLD, bad.why
    assert "하한" in bad.rows[0].why


def test_역배는_반대쪽_하한과_시즌교차를_다_넘어야_한다():
    # 🔴 반대쪽 하한 = 1 − 상한 → 상한 0.45 면 반대쪽 하한 0.55 > 50%
    got = db.judge({"홈 승": 0.52},
                   box=_box(_cell(0.38, 0.30, 0.45, cross=True)))
    assert got.rows[0].verdict == db.FADE, got.why
    # 🔴 **시즌 교차가 없으면 역배를 안 낸다**(추측 금지)
    for cross in (None, False):
        said = db.judge({"홈 승": 0.52},
                        box=_box(_cell(0.38, 0.30, 0.45, cross=cross)))
        assert said.rows[0].verdict == db.HOLD, said.why
        assert "시즌 교차" in said.rows[0].why


def test_보류_네_갈래():
    cut = float(dict(db.table().get("cuts") or {}).get("확신"))
    # ① 1단 기계 보류 → 전부 보류
    a = db.judge({"홈 승": 0.52}, machine_hold=True,
                 box=_box(_cell(cut + 0.1, cut + 0.05, cut + 0.2)))
    assert a.rows[0].verdict == db.HOLD and "기계 보류" in a.rows[0].why
    assert a.picks() == []
    # ② 칸이 없다
    b = db.judge({"홈 승": 0.52}, box=_box(_cell(0.9, 0.8, 0.95, p_lo=0.90)))
    assert b.rows[0].verdict == db.HOLD and "없다" in b.rows[0].why
    # ③ 칸이 보류다
    c = db.judge({"홈 승": 0.52},
                 box=_box(_cell(cut + 0.1, cut + 0.05, cut + 0.2, n=50,
                                hold=True)))
    assert c.rows[0].verdict == db.HOLD and "보류" in c.rows[0].why
    # ④ 보정표가 아예 없다
    d = db.judge({"홈 승": 0.52}, box={})
    assert d.rows[0].verdict == db.HOLD and "보정표" in d.rows[0].why


def test_칠_표는_확신_역배만_받고_역배는_표시만이다():
    """🔴🔴 §4·§7 — 역배는 **다리로 쓰지 않는다**."""
    rows = [{"match": "A vs B", "league": "L", "kickoff": "1",
             "board_lines": ["홈 승", "오버 2.5"],
             "lines": {"홈 승": 0.52, "오버 2.5": 0.55},
             "doubt_picks": {"홈 승": {"판정": db.SURE, "의심후": 0.671,
                                     "칸": "50%~100%"}}},
            {"match": "C vs D", "league": "L", "kickoff": "2",
             "board_lines": ["무"], "lines": {"무": 0.30},
             "doubt_picks": {"무": {"판정": db.FADE, "의심후": 0.62,
                                   "칸": "x"}}}]
    out = pk.of(rows)
    # 🔴 보류였던 `오버 2.5` 는 **후보가 아니다**(확률이 더 높아도)
    assert {x.line for x in out.singles} == {"홈 승", "무"}, out.singles
    # 🔴 역배는 다리에 **안 들어간다**
    assert all(x.verdict != db.FADE for got in out.parlays for x in got)
    said = pk.said_of(out)
    assert "역배 단폴(표시만)" in said, said
    assert "2단 판정을 쓴 경기 2개" in said, said


def test_2단_칸이_비면_옛_길로_간다():
    """🔴 §4 — 판정을 못 했다고 표를 **비우지 않는다**(문턱만 쓴다)."""
    high = max(pk.CUT_SINGLE, pk.CUT_LEG) + 0.02
    rows = [{"match": "A vs B", "league": "L", "kickoff": "1",
             "board_lines": ["홈 승"], "lines": {"홈 승": high}}]
    out = pk.of(rows)
    assert len(out.singles) == 1 and out.singles[0].after is None
    assert "2단 판정 칸이 비었다" in out.why, out.why


def test_확률_경로가_이_모듈을_안_부른다():
    """🔴 DB4 — 2단은 **글자와 판정**만 만든다(확률 불변)."""
    import ast
    import inspect
    from app.core import goals, probfloor, probmodel, sim
    for mod in (probmodel, probfloor, goals, sim):
        code = ast.unparse(ast.parse(inspect.getsource(mod)))
        assert "core.doubt" not in code and "import doubt" not in code, (
            f"{mod.__name__} 가 2단 판정을 부른다 — 확률 경로다")


def test_줄_이름을_세는_곳은_하나다():
    """🔴 사본 금지 — 보드 줄 이름과 **같은 꼴**이어야 맞물린다."""
    import ast
    import inspect
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    import slate_queue as sq
    code = ast.unparse(ast.parse(inspect.getsource(sq.pick_row)))
    assert "lines_of" in code and "grid_of" in code, code[:400]
    # 🔴 그 함수가 **정말** 보드 꼴 이름을 낸다
    got = pk.lines_of(pk.grid_of({"sim": {"scores": {"1-0": 0.5, "0-0": 0.5}}}))
    assert "홈 승" in got and "무" in got and "원정 승" in got
    assert any(k.startswith("핸디 ") for k in got)
    assert any(k.startswith("오버 ") for k in got)
