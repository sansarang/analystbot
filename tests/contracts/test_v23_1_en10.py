"""🔴🔴 **1번 — 누설 제거(EN10) · 후보 E5**(지시 2026-10-13 밤 다섯째 · 실행 전 커밋).

> 2,582경기 전부 Elo 바닥을 **시즌 교차 판**으로 다시 만들고(**운영 판 사용
> 0건 — 계약 EN10**) 격자 재생성 → 같은 규칙 v2+(d) 재판정.
> 판정 전 추가 후보 등록: **E5 = 시즌 초는 E0, 그 뒤는 E1**. 단순함 순서는 E1 다음.

🔴 **왜 EN10 인가** — 앞 판정(2,582경기 · E1 채택)에서 **1,380경기의 바닥이
   `base_model.yaml`(운영 판)** 이었다. 그 판은 **전 표본 적합**이라 평가 시즌이
   섞인다 → `G_Elo`·`G_M3` 가 **낙관적**이고 E1 은 M3 를 절반 쓴다.
🔴 **퇴로를 바꾼다** — 리그의 다른 시즌 표본이 모자라면 **운영 판이 아니라**
   그 폴드의 **여러 리그 묶음 적합**(평가 시즌을 뺀 전부)을 쓴다. 그래야
   *"평가 시즌을 한 번도 안 본 계수"* 가 된다.
⚠️ **단순함 순서** — E0 > E1 > **E5** > E2 > E4 > E3(지시: E5 는 E1 다음).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))


def test_e5_is_registered_before_the_run() -> None:
    """🔴 **E5** 가 후보 목록에 있고 **E1 다음**이다(단순함 순서)."""
    import fit_ensemble as fe
    names = [n for n, _k in fe.PLATES] if hasattr(fe, "PLATES") else fe.NAMES
    assert "E5" in names, names
    assert names.index("E5") == names.index("E1") + 1, names


def test_e5_switches_at_eight_games() -> None:
    """🔴 **시즌 초는 E0**(이번 시즌 8경기 이하) · **그 뒤는 E1**."""
    import fit_ensemble as fe
    assert fe.EARLY_GAMES == 8
    w_early = fe.w_of("E5", n_before=3, w2={"M1": 0.55, "M3": 0.45})
    w_late = fe.w_of("E5", n_before=20, w2={"M1": 0.55, "M3": 0.45})
    assert w_early == {"M1": 1.0}, w_early
    assert w_late == {"M1": 0.5, "M3": 0.5}, w_late


def test_en10_no_operational_plate_in_the_grids() -> None:
    """🔴🔴 **EN10** — 격자 만들기가 **운영 판(`base_model.yaml`)을 안 쓴다**.

    🔴 `probfloor.floor_of` 는 그 판을 읽는 문이다 → 격자 도구에 그 이름이
       **없어야** 한다. ⚠️ 퇴로는 **묶음 교차 적합**이다(평가 시즌을 뺀 전부).
    """
    import ast
    tree = ast.parse((ROOT / "tools/build_grids.py").read_text(
        encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    code = ast.unparse(tree)
    assert "floor_of" not in code, "🔴 운영 판을 읽는다(EN10)"
    assert "pooled" in code or "묶음" in code


def test_en10_index_records_the_fit_source() -> None:
    """🔴 색인이 **바닥 계수의 출처**를 경기마다 적는다(운영 판이면 0건이어야 한다)."""
    import json
    path = ROOT / "var/judge/grids_index.json"
    if not path.exists():
        return
    box = json.loads(path.read_text(encoding="utf-8"))
    rows = list(box.get("rows") or [])
    if not rows or "floor_fit" not in rows[0]:
        return            # ⬜ 아직 다시 안 만들었다(그 사실은 보고가 적는다)
    bad = [r for r in rows if str(r.get("floor_fit")) == "운영 판"]
    assert not bad, f"🔴 운영 판으로 만든 격자 {len(bad)}건(EN10)"
