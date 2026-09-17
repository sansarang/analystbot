"""RPT-1 계약 — 원장에서 표를 뽑는 도구. **얇은 어댑터다.**

🔴 `report.py` 다섯 함수는 전부 순수 함수라 **행을 넣어주는 쪽**이 필요했다.
   실측: `report` 를 import 하는 운영·도구 파일 **0건**(tests 뿐).
🔴 도구가 계산을 다시 하면 안 된다 — `tools/calibration.py` 의 규약:
   "도구와 운영이 다른 계산을 하면 **표를 믿을 수 없다**".
"""
import importlib.util
import inspect
import pathlib

import pytest

from app.engine import gate as G
from app.engine import report as RP

TOOL = pathlib.Path(__file__).resolve().parents[1] / "tools" / "report_vars.py"


def _load():
    spec = importlib.util.spec_from_file_location("report_vars", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


T = _load()
SRC = TOOL.read_text(encoding="utf-8")


def _rec(**kw):
    base = {"sport": "soccer", "predicted_side": "home", "favored": "home",
            "p_home": 0.62, "p_code": 0.62, "hit": True,
            "adj_pp": {"주전결장": -1.5}, "adj_evidence": None,
            "gate_label": None, "clv": 2.0}
    base.update(kw)
    return base


# ── 🔴 `p` 는 **고른 쪽** 확률이다

def test_홈픽은_p_home_그대로():
    assert T.to_rows([_rec()], board_label=G.BOARD)[0]["p"] == 0.62


def test_원정픽은_확률이_뒤집힌다():
    """🔴 `hit` 은 우리 픽 기준인데 `p_home` 은 홈 기준이다 —
    안 돌리면 **브라이어가 통째로 뒤집힌다.**"""
    got = T.to_rows([_rec(predicted_side="away")], board_label=G.BOARD)[0]
    assert got["p"] == pytest.approx(0.38)


def test_픽을_모르면_p가_None이다():
    got = T.to_rows([_rec(predicted_side=None, favored="박빙")],
                    board_label=G.BOARD)[0]
    assert got["p"] is None


def test_확률이_없으면_None이다():
    """🔴 0 으로 채우면 '확률 0%'와 '확률 없음'이 같아진다."""
    got = T.to_rows([_rec(p_home=None, p_code=None)], board_label=G.BOARD)[0]
    assert got["p"] is None


def test_p_home이_없으면_p_code로_간다():
    got = T.to_rows([_rec(p_home=None, p_code=0.7)], board_label=G.BOARD)[0]
    assert got["p"] == 0.7


# ── 값 옮기기

def test_JSONB가_문자열로_와도_읽는다():
    got = T.to_rows([_rec(adj_pp='{"주전결장": -1.5}')], board_label=G.BOARD)[0]
    assert got["adj_pp"] == {"주전결장": -1.5}


def test_못_읽는_JSONB는_None이다():
    got = T.to_rows([_rec(adj_pp="이건 JSON 이 아니다")], board_label=G.BOARD)[0]
    assert got["adj_pp"] is None


def test_hit이_없으면_None이다():
    assert T.to_rows([_rec(hit=None)], board_label=G.BOARD)[0]["hit"] is None


def test_보드_라벨을_손으로_안_적었다():
    """🔴 사본 금지 — `gate.BOARD` 가 원본이다."""
    assert "보드 고정" not in SRC
    on = T.to_rows([_rec(gate_label=G.BOARD)], board_label=G.BOARD)[0]
    off = T.to_rows([_rec(gate_label=G.AGREE)], board_label=G.BOARD)[0]
    assert on["board_only"] is True and off["board_only"] is None


def test_빈_원장에서도_안_터진다():
    assert T.to_rows([], board_label=G.BOARD) == []
    assert "표본 0건" in T.render(RP, [])


# ── 🔴 반대 위험

def test_계산을_직접_하지_않는다():
    """🔴 평균·브라이어·판정은 전부 `report.py` 가 한다."""
    body = "\n".join(ln for ln in SRC.splitlines()
                     if ln.strip() and not ln.strip().startswith("#"))
    for bad in ("def _brier", "def _mean", "statistics", "numpy"):
        assert bad not in body, bad


def test_원장에_쓰지_않는다():
    """🔴 읽기 전용이다.

    ⚠️ **주석·머리말이 아니라 실제 SQL 과 호출**을 본다. 처음에 소스 전체에서
       "INSERT" 를 찾게 했더니 *"INSERT·UPDATE 를 하지 않는다"* 라고 적은
       머리말이 걸렸다 — 설명을 못 쓰게 만드는 계약은 틀린 계약이다
       (PA-27-a · PA-28 에서도 같은 함정에 걸렸다).
    """
    assert T._SQL.strip().upper().startswith("SELECT")
    for bad in ("INSERT", "UPDATE", "DELETE", "DROP"):
        assert bad not in T._SQL.upper(), bad
    # 실행 호출은 fetch 뿐이다 — execute/executemany 는 쓰기 통로다.
    code = "\n".join(ln for ln in SRC.splitlines()
                      if ln.strip() and not ln.strip().startswith("#"))
    assert "pool.fetch(" in code
    assert ".execute(" not in code and ".executemany(" not in code


def test_report_다섯_중_넷을_부르고_하나는_사유를_말한다():
    """🔴 `source_score` 는 대조 자료가 원장에 없다 — 억지로 채우지 않는다."""
    for fn in ("hygiene", "by_variable", "by_axis", "cancel_clv"):
        assert f"RP.{fn}(" in SRC or f"rep.{fn}(" in SRC, fn
    assert "source_score" in SRC and "부르지 않았다" in SRC


def test_스케줄러에_걸지_않았다():
    """🔴 지시받은 것은 A(도구)뿐이다. 체크포인트 발송은 별건이다."""
    sched = (pathlib.Path(__file__).resolve().parents[1]
             / "app" / "scheduler.py").read_text(encoding="utf-8")
    assert "report_vars" not in sched


def test_render가_report값을_그대로_쓴다():
    rows = T.to_rows([_rec() for _ in range(3)], board_label=G.BOARD)
    txt = T.render(RP, rows)
    assert f"문턱 {RP.VAR_MIN_N}건" in txt
    assert "주전결장" in txt
    assert RP.THIN in txt          # 3건이면 표본 부족이다


def test_없는_값은_대시로_찍는다():
    """🔴 0 으로 찍으면 '0건'과 '0%'가 같아진다."""
    assert T._n(None) == "—"
    assert T._n(0.0) == "0.000"


def test_머리말이_로컬DB_함정을_적었다():
    doc = inspect.getdoc(T) or ""
    assert "railway ssh" in doc
