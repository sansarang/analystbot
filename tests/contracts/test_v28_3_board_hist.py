"""🔴🔴 계약 — **백필 보드**(의심 검증 통합본 v2 · 2026-10-14i §1-4).

| 조항 | 여기서 무엇을 본다 |
|---|---|
| §1-4 원천 | `football_data_hist` 꼴이 맞나 · 코드가 **확인된 값**인가 |
| §1-4 근사 | 0.5 단위 **전부**에서 고르나 · **정수 줄(푸시)** 이 빠지지 않나 |
| §1-2 | 카드가 쓰는 기준선 표는 **그대로**인가(근사가 카드를 흔들면 안 된다) |
| CLAUDE.md #3 | 만든 판에 **경기 수만큼 줄**이 있나(조용히 줄지 않나) |
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from app.core import competition as cp          # noqa: E402
from app.core import probfloor as pf            # noqa: E402
import fit_board_hist as fh                     # noqa: E402

#: 🔴 확인된 코드만 쓴다 — `mmz4281` 폴더는 두 자리 둘(`2526`)이고 `Div` 는 짧다
KINDS = {"mmz4281": {"code"}, "extra": {"file", "league"}}


def test_시즌_폴더_꼴():
    assert fh.season_code("2025/2026") == "2526"
    assert fh.season_code("2026/2027") == "2627"
    # 🔴 한 해짜리 시즌(J리그 `2026`)은 mmz4281 폴더 꼴이 **없다** → 빈 글자
    assert fh.season_code("2026") == ""
    assert fh.season_code("") == ""


def test_날짜를_바꾸되_짐작하지_않는다():
    assert fh._day("08/08/2025") == "2025-08-08"
    assert fh._day("2/5/26") == "2026-05-02"
    assert fh._day("") == ""
    assert fh._day("쓰레기") == ""


def test_원천_선언의_꼴이_맞다():
    """🔴 §1-4 — 꼴이 틀리면 그 리그는 **조용히 근사로** 떨어진다."""
    n = 0
    for key in sorted(cp.rows()):
        got = (cp.row_of(key).get("sources") or {}).get("football_data_hist")
        if got is None:
            continue
        n += 1
        kind = str(dict(got).get("kind") or "")
        assert kind in KINDS, f"{key} — `kind: {kind}` 는 모르는 꼴이다"
        miss = KINDS[kind] - set(dict(got))
        assert not miss, f"{key} — `{kind}` 에 {sorted(miss)} 가 없다"
        if kind == "mmz4281":
            code = str(got["code"])
            assert 2 <= len(code) <= 3 and code.isalnum(), code
            # ⚠️ `football_data`(Elo 코드)와 **다른 값**이다 — 섞으면 404 다
            assert code != str((cp.row_of(key).get("sources") or {})
                               .get("football_data") or ""), (
                f"{key} — 백필 코드가 Elo 코드와 같다(섞였다)")
    assert n >= 10, f"선언된 원천이 {n}개뿐이다 — 리그를 늘리면 여기도 늘린다"


def test_근사는_정수_줄도_고른다():
    """🔴🔴 §1-4 — **푸시 때문에 정수 줄이 빠지면** 근사가 한쪽으로 쏠린다.

    ⚠️ 실측 2026-10-14: `f"{-0.0:+.1f}"` 가 `"-0.0"` 이라 격자 열쇠
       `away+0.0` 을 못 찾아 **핸디 0 줄이 통째로 빠졌다** — λ 가 같은 경기에서
       −0.5 가 뽑혀 양쪽이 0.362/0.638 로 벌어졌다.
    """
    got, why = fh.approx_lines([1.2, 1.2])
    assert got, why
    assert float(got["ah"]["point"]) == 0.0, why
    assert "무" in why, why          # 🔴 정수 줄은 무(푸시)를 적는다
    # 🔴 치우친 경기는 반 단위로 간다
    got2, why2 = fh.approx_lines([1.6, 1.1])
    assert float(got2["ah"]["point"]) == -0.5, why2
    # 🔴 배당은 **짓지 않는다**(#4)
    for side in ("home", "away"):
        assert got["ah"][side] is None
    assert got["win"] == [None, None, None]
    # 🔴 λ 가 없으면 **만들지 않는다**
    assert fh.approx_lines([])[0] == {}
    assert fh.approx_lines([0.0, 1.0])[0] == {}


def test_카드가_쓰는_기준선은_안_바뀐다():
    """🔴 §1-2 — 근사용 넓은 표가 **기본값을 건드리면** 카드 글이 바뀐다."""
    assert pf.AH_LINES == (-2.5, -1.5, -0.5, 0.5, 1.5, 2.5)
    assert pf.TOTAL_LINES == (0.5, 1.5, 2.5, 3.5, 4.5)
    grid = pf.score_grid(lam_home=1.5, lam_away=1.2)
    assert (sorted(pf.markets_of(grid)["ah"])
            == sorted(pf.markets_of(grid, ah_lines=pf.AH_LINES)["ah"]))
    # 🔴 넓은 표는 **정수를 품는다**(그것이 쓰는 까닭이다)
    wide = pf.markets_of(grid, ah_lines=pf.AH_LINES_FULL)["ah"]
    assert "home+0.0" in wide and "away+0.0" in wide


def test_만든_판에_경기_수만큼_줄이_있다():
    """🔴 CLAUDE.md #3 — 조용히 줄면 백필 표본이 소리 없이 작아진다."""
    import yaml
    box = sorted((ROOT / "data/board_hist").glob("*/*.yaml"))
    if not box:
        pytest.skip("아직 백필 보드를 안 만들었다 — `tools/fit_board_hist.py`")
    for path in box:
        got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        meta, lines = dict(got.get("meta") or {}), list(got.get("lines") or [])
        assert len(lines) == int(meta.get("rows") or -1), (
            f"{path.name} — 줄 {len(lines)} ≠ 경기 {meta.get('rows')}")
        tally = dict(meta.get("tally") or {})
        assert sum(int(v) for v in tally.values()) == len(lines), (
            f"{path.name} — 집계 {tally} 가 줄 수와 다르다")
        # 🔴 실보드/근사가 **줄마다 적혀** 있다(판정표가 따로 집계한다 · §1-4)
        for one in lines:
            assert str(one.get("kind") or "") in (
                "실보드", "실보드(승무패만)", "근사", "없음"), one.get("kind")
