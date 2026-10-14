"""🔴🔴 계약 — **2단 의심 시험 + 조건부 보정표**(의심 검증 v2 §3-2·3-3).

| 조항 | 여기서 무엇을 본다 |
|---|---|
| §3-2 (가)(나)(다) | 읽기 글자가 **세 갈래**이고 유효는 (가)뿐이다 |
| §3-2 체급 통제 | 🔴 전체만 유효한 것은 **올리지 않는다**(A2 가 그렇게 떨어졌다) |
| §3-3 칸 | 칸 <100 → 이웃 합침 → 그래도 <100 → **보류** |
| §3-3 집계 | **실보드와 근사를 섞어 적지 않는다**(칸마다 나눠 센다) |
| C11 누설 | 깃발 재료가 **그 경기 앞**의 것뿐인가 |
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import fit_doubt as fd                           # noqa: E402


def test_구간은_지시의_그_목록이다():
    """🔴 §3-3 — 40-45·45-50·50-55·55-60·60-70·70-80·80+."""
    got = [(round(a, 2), round(b, 2)) for a, b in fd.BANDS]
    assert got == [(0.40, 0.45), (0.45, 0.50), (0.50, 0.55), (0.55, 0.60),
                   (0.60, 0.70), (0.70, 0.80), (0.80, 1.01)], got
    assert fd.CELL_MIN == 100
    assert fd.KINDS == ("승무패 방향", "보드 핸디", "보드 언오버")
    # 🔴 구간은 **이어진다** — 틈이 있으면 그 확률의 줄이 조용히 사라진다
    for (a, b), (c, _d) in zip(fd.BANDS, fd.BANDS[1:]):
        assert b == c, f"{b} 와 {c} 사이에 틈이 있다"
    assert fd.band_of(0.39) is None and fd.band_of(0.40) == (0.40, 0.45)
    assert fd.band_of(0.999) == (0.80, 1.01)


def test_윌슨_구간은_범위를_안_벗어난다():
    """🔴 §3-3 — 칸이 작거나 비율이 0·1 에 붙어도 [0, 1] 안이다."""
    for hits, n in ((0, 5), (5, 5), (1, 3), (50, 100), (99, 100)):
        p, lo, hi = fd.wilson(hits, n)
        assert 0.0 <= lo <= p <= hi <= 1.0, (hits, n, p, lo, hi)
    import math
    assert math.isnan(fd.wilson(0, 0)[0])


def test_작은_칸은_합치고_그래도_작으면_보류다():
    """🔴🔴 §3-3 — 합치는 규칙이 **칸을 조용히 버리지 않는다**."""
    kind = "승무패 방향"
    # 🔴 구간마다 30줄 — 셋을 합쳐야 100 을 넘는다
    box = {(kind, band, "0"): [{"p": band[0], "hit": 1, "real": True}] * 30
           for band in fd.BANDS}
    got = fd.merged(box, kind, "0")
    assert got, "합친 칸이 하나도 없다"
    n_all = sum(len(x["rows"]) for x in got)
    assert n_all == 30 * len(fd.BANDS), f"줄이 사라졌다: {n_all}"
    # 🔴 마지막 칸을 뺀 나머지는 전부 문턱을 넘는다
    for one in got[:-1]:
        assert len(one["rows"]) >= fd.CELL_MIN
    # 🔴 전부 모자라면 **보류** 꼬리표가 붙는다
    thin = {(kind, fd.BANDS[0], "0"): [{"p": 0.42, "hit": 1, "real": True}] * 7}
    cell = fd.say_cell(fd.merged(thin, kind, "0")[0])
    assert cell["보류"] is True and cell["n"] == 7


def test_실보드와_근사를_섞어_적지_않는다():
    """🔴 §1-4 — 판정표는 실보드 표본과 **따로** 집계한다."""
    rows = ([{"p": 0.5, "hit": 1, "real": True}] * 3
            + [{"p": 0.5, "hit": 0, "real": False}] * 2)
    cell = fd.say_cell({"bands": [fd.BANDS[2]], "rows": rows})
    assert cell["실보드"] == 3 and cell["근사"] == 2
    assert cell["실보드"] + cell["근사"] == cell["n"]


def test_읽기는_세_갈래이고_유효는_가뿐이다():
    """🔴🔴 §3-2 — 🔴 **전체만 유효한 것은 올리지 않는다**.

    ⚠️ 실측 2026-10-14: A2(승격·강등 착시)가 전체 −15.9%p [−31.7, **−0.1**] 로
       턱걸이로 넘었는데 체급을 통제하면 −2.2%p [−23.4, +19.1] 로 사라졌다
       (걸린 경기 41건뿐). 체급이 섞인 차이는 그 변수가 아니라 **체급**일 수 있다.
    """
    import ast
    import inspect
    code = ast.unparse(ast.parse(inspect.getsource(fd.test_vars)))
    assert "체급유효" in code, "체급 통제 조건이 없다"
    assert 'said["유효"] = bool(said.get(\'전체유효\') and said.get(\'체급유효\'))' \
        in code or "전체유효') and said.get('체급유효'" in code, code[-600:]


def test_푸시는_버린다():
    """🔴 §3-3 — 정수 핸디의 무·총점 적중은 **맞음도 틀림도 아니다**."""
    r = {"hg": 1, "ag": 1, "ours": [0.4, 0.3, 0.3], "hit": 1,
         "lam": [1.3, 1.1], "season": "x", "league": "league:ELC"}
    # 🔴 핸디 0 · 총점 2 → 둘 다 푸시다 → 승무패 줄만 남는다
    got = fd.line_rows(r, {"kind": "실보드", "ah": {"point": 0.0},
                           "ou": {"point": 2.0}})
    assert [x["kind"] for x in got] == ["승무패 방향"], got
    # 🔴 반 단위면 푸시가 없다 → 줄 셋
    got2 = fd.line_rows(r, {"kind": "실보드", "ah": {"point": -0.5},
                            "ou": {"point": 2.5}})
    assert {x["kind"] for x in got2} == set(fd.KINDS), got2


def test_누설_금지():
    """🔴 C11 — 깃발은 **그 경기 앞**의 자료로만 선다."""
    import ast
    import inspect
    src = inspect.getsource(fd.flags_of)
    code = ast.unparse(ast.parse(src))
    # 🔴 지난 목록 갱신이 **깃발을 세운 뒤**에 온다(그 줄이 마지막 블록이다)
    assert code.index("out.append(got)") < code.index("prior.setdefault"), (
        "지난 목록을 깃발 앞에서 갱신한다 — 그 경기가 자기 재료에 들어간다")
    # 🔴 그 경기의 결과(`hg`·`ag`)를 깃발 재료로 쓰지 않는다 — C2 는 **앞선 홈
    #    경기들**의 득실이고, 그 줄은 `prior` 에서 온다
    assert "prior.get((lg, host))" in code


def test_만든_판이_규격을_지킨다():
    import yaml
    box = sorted((ROOT / "data/doubt_cal").glob("*.yaml"))
    if not box:
        pytest.skip("아직 보정표를 안 만들었다 — `tools/fit_doubt.py`")
    assert len(box) == len(fd.KINDS), [p.name for p in box]
    for path in box:
        got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        meta = dict(got.get("meta") or {})
        assert str(meta.get("줄종류")) in fd.KINDS, meta
        assert int(meta.get("칸_최소") or 0) == fd.CELL_MIN
        # 🔴 유효 의심 목록이 **등록표와 같다**(사본 금지)
        reg = yaml.safe_load(
            (ROOT / "config/doubt_vars.yaml").read_text(encoding="utf-8"))
        assert list(meta.get("유효_의심") or []) == \
            list(dict(reg.get("의심") or {}).get("유효") or [])
        for bucket, rows in dict(got.get("칸") or {}).items():
            assert bucket in ("0", "1", "2+"), bucket
            for one in list(rows or []):
                assert 0.0 <= float(one["실측"]) <= 1.0
                assert float(one["lo"]) <= float(one["실측"]) \
                    <= float(one["hi"])
                assert int(one["실보드"]) + int(one["근사"]) == int(one["n"])
