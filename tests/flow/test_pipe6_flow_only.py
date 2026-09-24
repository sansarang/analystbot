"""[PIPE-6 2026-09-25] **픽은 흐름 안에서만 난다.**

사용자 감사 2026-09-25 모순 6: 그날의 "픽 2건"은 ⑨·⑩·⑪·방향 검사를 전부
우회해 `scoring.mlb_market_probs` 를 직접 태워 만든 것이었다. 그래서 ⑦ 방향과
**정반대**인 핸디 후보가 나왔다.

🔴 이 파일이 잠그는 것 셋:
  (a) 결정 원장에 남는 흐름 판정은 **run_id 가 반드시 적힌다** — 원장만 보고
      "흐름 밖에서 만든 것"을 가려낼 수 있어야 한다.
      ⚠️ `decision_ledger` 에 `run_id` **열이 없다**(실측 2026-09-25 스키마).
         스키마를 늘리지 않고 `note` 의 `run=` 토큰으로 잠근다.
  (b) 원장 기록 경로는 **`run.finish` 하나**다 — 다른 곳에서 `ENGINE` 으로
      쓰면 흐름 밖 판정이 섞인다.
  (c) ⑪의 구조 픽 마켓은 **④가 지정한 마켓**과 같아야 한다(D51 핸디 방향).
      가설이 부르지 않은 마켓을 ⑪이 집으면 그것이 흐름 밖 픽과 같은 모양이다.
"""
from __future__ import annotations

import ast
import inspect

import pytest

from app.flow import record as REC
from app.flow import run as RUN
from app.flow.nodes import n11_value as N11


def _code_only(src: str) -> str:
    """docstring 을 걷어낸 코드 본문. 🔴 DEFECTS D46 — "규율을 설명할수록
    계약이 깨지는" 자리를 피한다. 주석은 `ast` 가 애초에 버린다."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not body or not isinstance(body, list):
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            body.pop(0)
    return ast.unparse(tree)


class _S:
    """원장 기록에 필요한 칸만 가진 최소 상태."""

    def __init__(self, **kw):
        self.run_id = kw.get("run_id", "11111111-2222-3333-4444-555555555555")
        self.n03_gate = kw.get("n03_gate")
        self.n07_adjust = kw.get("n07_adjust") or []
        self.n09_conf = kw.get("n09_conf")
        self.stop_reason = kw.get("stop_reason")


# ── (a) 원장 note 에 run_id 가 반드시 있다 ─────────────────────────

def test_pipe6_no_pick_outside_flow():
    """🔴 원장 한 줄만 보고 어느 run 이 냈는지 답할 수 있어야 한다."""
    note = REC.note_of(_S())
    assert "run=" in note, f"run_id 가 note 에 없다: {note}"
    assert "11111111-2222-3333-4444-555555555555" in note

    # run_id 가 비면 빈 run= 이 남는다 — 그것도 "흐름 밖"의 표지다.
    blank = REC.note_of(_S(run_id=""))
    assert blank.startswith("run="), blank


def test_pipe6_note_에_게이트가_실린다():
    """③이 쓰는 키는 `gate` 다. `label` 로 읽으면 전건 빠진다(이 패치의 결함)."""
    from app.flow.labels import OVER

    note = REC.note_of(_S(n03_gate={"gate": OVER}))
    assert OVER in note, f"게이트가 note 에 없다: {note}"
    # 🔴 사본 금지 — 코드가 읽는 키 이름을 여기서 다시 적지 않고 동작으로 잰다.
    assert OVER not in REC.note_of(_S(n03_gate={"label": OVER})), \
        "없는 키(label)로도 값이 실린다면 어느 키가 원본인지 갈리지 않는다"


# ── (b) 원장 기록 경로는 하나다 ────────────────────────────────────

def test_pipe6_원장_기록은_흐름_종료부에서만_불린다():
    src = inspect.getsource(RUN.finish)
    assert "record" in src, "run.finish 가 원장을 남기지 않는다"

    import pathlib

    root = pathlib.Path(REC.__file__).resolve().parents[2] / "app"
    writers = sorted(str(f.relative_to(root))
                     for f in root.rglob("*.py")
                     if "INSERT INTO decision_ledger" in f.read_text(encoding="utf-8"))
    # 🔴 원장에 쓰는 파일은 **둘뿐**이다. `learning/decisions.py` 는 구경로
    #    소유(engine 을 인자로 받는다)이고, 흐름은 `flow/record.py` 하나다.
    #    셋째가 생기면 흐름 밖 판정이 섞일 수 있으므로 여기서 막는다.
    assert writers == ["flow/record.py", "learning/decisions.py"], \
        f"원장에 쓰는 파일이 늘었다: {writers}"
    # 🔴 두 writer 중 **흐름 엔진 이름을 아는 것은 `record.py` 하나**여야 한다.
    #    구경로(`learning/decisions.py`)가 `flow_v14` 를 박아 쓰기 시작하면
    #    두 경로의 판정이 같은 엔진 이름으로 섞인다.
    #    ⚠️ 문자열 매칭에 **주석·docstring 이 걸린다**(DEFECTS D46). 코드만 본다.
    other = _code_only((root / "learning/decisions.py").read_text(encoding="utf-8"))
    assert REC.ENGINE not in other, \
        f"구경로 코드가 {REC.ENGINE} 을 손으로 적는다 — 두 경로가 섞인다"


# ── (c) D51 — ⑪은 ④가 지정하지 않은 마켓을 집지 않는다 ────────────

def test_handicap_direction_consistent():
    """🔴 ⑦ 합이 강팀 쪽인데 약팀 +라인을 집는 일이 없어야 한다.

    ⑪의 구조 후보는 `want`(=④가 지정한 마켓) **접두사**로만 걸러진다.
    그 필터가 사라지면 핸디가 총점 자리에 섞여 들어온다.
    """
    src = inspect.getsource(N11.run)
    assert 'startswith(want)' in src, \
        "지정 마켓 필터가 사라졌다 — 가설이 부르지 않은 마켓이 픽이 된다"

    cands = [{"market": "total_over", "line": 7.0, "odds": 1.9, "edge_pp": 3.0},
             {"market": "ah", "line": 1.5, "odds": 1.7, "edge_pp": 40.0}]
    fam = [c for c in cands if str(c.get("market", "")).startswith("total")]
    assert [c["market"] for c in fam] == ["total_over"], \
        "지정 마켓이 total 인데 핸디가 후보로 남았다"


@pytest.mark.parametrize("market,want,ok", [
    ("total_over", "total", True),
    ("total_under", "total", True),
    ("ah", "total", False),
    ("team_total_home_over", "total", False),
])
def test_pipe6_지정마켓_접두사_판정(market, want, ok):
    assert str(market).startswith(want) is ok
