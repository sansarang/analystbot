"""[v1.4 STEP 1] 스켈레톤 계약 — **다섯 경로의 호출 목록이 정확히 일치한다.**

🔴 지시문 규율 9: **멈춤은 실패가 아니다.** ③ 보드 고정 · ⑥ 반박됨 ·
   ⑥ 모름과반 · ⑪ 값 없음은 정상 종료이고, 그 경로에서 **카드가 만들어지면
   버그다.** 이 파일이 그것을 잡는다.

🔴 지시문 규율 7: **노드는 서로 부르지 않는다.** 분기는 `run.py` 한 곳이다.
   노드 안에서 다른 노드를 import 하면 배선 오류 — 아래 계약이 전수로 막는다.

⚠️ 지금 노드는 전부 패스스루다. 이 테스트는 **배선**을 잰다 — 계산이 아니다.
"""
from __future__ import annotations

import pathlib

import pytest

from app.flow import run as RUN
from app.flow.state import NODE_KEYS, State

NODES_DIR = pathlib.Path(RUN.__file__).resolve().parent / "nodes"


class _Ctx:
    """스냅샷을 건너뛴다 — `pool` 이 None 이면 `run.py` 가 DB 를 안 부른다."""

    pool = None


def _game():
    return {"game_id": "kbo_20260918_HH_SS", "sport": "baseball",
            "league": "KBO", "home": "한화", "away": "삼성",
            "starts_at": "2026-09-18T09:30:00Z"}


def _stub(monkeypatch, **outs):
    """노드를 **자기 키만 채우는** 스텁으로 갈아끼운다.

    🔴 배선이 그 키를 읽는지 보는 것이 목적이다 — 계산을 흉내내지 않는다.
    """
    for name, payload in outs.items():
        mod = getattr(RUN, name)

        def _mk(key, value):
            def _run(state, ctx):
                setattr(state, key, value)
                return state
            return _run

        monkeypatch.setattr(mod, "run", _mk(mod.NODE, payload))


async def _go(monkeypatch, **outs):
    _stub(monkeypatch, **outs)
    return await RUN.run_game(_game(), _Ctx())


# ── 다섯 경로

@pytest.mark.asyncio
async def test_정상경로는_13노드를_전부_지난다(monkeypatch):
    s = await _go(monkeypatch,
                  n03_gate={"stop": False, "gate": "동의"},
                  n06_verdict={"verdict": "확인됨"},
                  n10_rejudge={"triggered": False},
                  n11_value={"pick_type": "승패"},
                  n12_text={"sentences": ["1", "2", "3", "4"]})
    assert s.trace == list(NODE_KEYS), s.trace
    assert s.stop_reason is None


@pytest.mark.asyncio
async def test_보드고정은_수집을_하지_않는다(monkeypatch):
    """🔴 ③ stop → ④ 가설·⑤ 수집부터 **한 번도** 안 돈다."""
    s = await _go(monkeypatch, n03_gate={"stop": True, "gate": "보드고정"})
    assert s.trace == ["n01_prior", "n02_market", "n03_gate"], s.trace
    assert s.stop_reason == "n03_freeze"
    for banned in ("n04_hyp", "n05_evidence", "n12_text", "n13_send"):
        assert banned not in s.trace


@pytest.mark.asyncio
async def test_반박됨은_조정부터_안_돈다(monkeypatch):
    s = await _go(monkeypatch,
                  n03_gate={"stop": False},
                  n06_verdict={"verdict": "반박됨"})
    assert s.trace == ["n01_prior", "n02_market", "n03_gate", "n04_hyp",
                       "n05_evidence", "n06_verdict"], s.trace
    assert s.stop_reason == "n06_refuted"
    assert "n07_adjust" not in s.trace


@pytest.mark.asyncio
async def test_모름과반도_같은_자리에서_멈춘다(monkeypatch):
    s = await _go(monkeypatch,
                  n03_gate={"stop": False},
                  n06_verdict={"verdict": "모름과반"})
    assert s.trace[-1] == "n06_verdict"
    assert s.stop_reason == "n06_unknown"
    assert "n07_adjust" not in s.trace


@pytest.mark.asyncio
async def test_값없음은_서술을_만들지_않는다(monkeypatch):
    """🔴 ⑪ 보드 → ⑫ 서술·⑬ 발송이 **호출되지 않는다.**"""
    s = await _go(monkeypatch,
                  n03_gate={"stop": False},
                  n06_verdict={"verdict": "확인됨"},
                  n10_rejudge={"triggered": False},
                  n11_value={"pick_type": "보드"})
    assert s.trace[-1] == "n11_value"
    assert s.stop_reason == "n11_no_value"
    assert "n12_text" not in s.trace and "n13_send" not in s.trace


# ── ⑩ 재판정: ⑤~⑨ 를 **1회만** 다시 돈다

@pytest.mark.asyncio
async def test_재판정_트리거는_5에서_9만_다시_돈다(monkeypatch):
    s = await _go(monkeypatch,
                  n03_gate={"stop": False},
                  n06_verdict={"verdict": "확인됨"},
                  n10_rejudge={"triggered": True, "trigger": "starter_changed"},
                  n11_value={"pick_type": "승패"},
                  n12_text={"sentences": ["1", "2", "3", "4"]})
    reruns = [t for t in s.trace if t.endswith(":rerun")]
    assert reruns == ["n05_evidence:rerun", "n06_verdict:rerun",
                      "n07_adjust:rerun", "n08_pcode:rerun",
                      "n09_conf:rerun"], reruns
    # 🔴 ①~④ 와 ⑪~⑬ 은 재실행 대상이 아니다.
    for banned in ("n01_prior:rerun", "n04_hyp:rerun", "n11_value:rerun"):
        assert banned not in s.trace


@pytest.mark.asyncio
async def test_서술이_지어내면_카드를_만들지_않는다(monkeypatch):
    s = await _go(monkeypatch,
                  n03_gate={"stop": False},
                  n06_verdict={"verdict": "확인됨"},
                  n10_rejudge={"triggered": False},
                  n11_value={"pick_type": "승패"},
                  n12_text={"hallucination": True})
    assert s.stop_reason == "n12_hallucination"
    assert "n13_send" not in s.trace


# ── 배선 규율 (지시문 규율 7·8)

def test_노드는_서로_부르지_않는다():
    """🔴 노드 파일 안에서 다른 노드를 import 하면 배선 오류다."""
    bad = []
    for f in sorted(NODES_DIR.glob("n*.py")):
        src = f.read_text(encoding="utf-8")
        code = "\n".join(ln for ln in src.splitlines()
                         if ln.strip() and not ln.strip().startswith("#"))
        body = code.split('"""', 2)[-1]          # 머리말(설명)은 제외
        for other in NODE_KEYS:
            if other != f.stem and other in body:
                bad.append(f"{f.name} → {other}")
    assert bad == [], bad


def test_노드마다_run이_하나씩_있다():
    files = sorted(p.stem for p in NODES_DIR.glob("n*.py"))
    assert files == list(NODE_KEYS), files
    for f in NODES_DIR.glob("n*.py"):
        mod = __import__(f"app.flow.nodes.{f.stem}", fromlist=["run"])
        assert callable(mod.run), f.stem
        assert mod.NODE == f.stem, (mod.NODE, f.stem)


def test_분기는_run_py_에만_있다():
    """🔴 멈춤 사유 문자열이 노드 파일에 있으면 분기가 샌 것이다."""
    from app.flow.state import STOP_REASONS

    bad = []
    for f in sorted(NODES_DIR.glob("n*.py")):
        body = f.read_text(encoding="utf-8").split('"""', 2)[-1]
        for reason in STOP_REASONS:
            if reason in body:
                bad.append(f"{f.name} → {reason}")
    assert bad == [], bad


def test_상수를_손으로_안_적었다():
    """🔴 사본 금지 — 문턱은 `config/rules.yaml` 의 `flow:` 가 원본이다."""
    from app.flow import rules as R

    assert R.get("gate_pp.agree") == 4.0
    assert R.get("gate_pp.freeze") == 12.0
    assert R.get("edge_min_pp") == 2.0
    assert R.get("total_adjust_cap_pp") == 6.0
    assert R.get("unknown_ratio_board") == 0.5
    # 로더가 숫자를 스스로 갖고 있지 않아야 한다
    body = pathlib.Path(R.__file__).read_text(encoding="utf-8").split('"""', 2)[-1]
    for literal in ("4.0", "12.0", "2.0", "6.0", "0.5", "0.26"):
        assert literal not in body, f"로더에 숫자를 적었다: {literal}"


def test_핵심변수는_rules가_원본이다():
    from app.flow import rules as R

    assert R.core_vars("baseball") == ("starter_recent3", "bullpen_3d",
                                       "lineup_out")
    assert R.core_vars("soccer") == ("xi_confirmed",)


def test_상태는_하나뿐이다():
    """🔴 지시문 규율 8 — 노드 간 전달용 전역·임시 파일이 없다."""
    body = pathlib.Path(RUN.__file__).read_text(encoding="utf-8").split('"""', 2)[-1]
    for banned in ("global ", "open(", "tempfile"):
        assert banned not in body, f"run.py 에 {banned} 가 있다"


def test_analysis_runs_테이블이_스키마에_있다():
    schema = pathlib.Path("db/schema.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS analysis_runs" in schema
    for col in ("run_id", "game_id", "node", "snapshot_json", "created_at_utc"):
        assert col in schema, col


def test_상태_왕복():
    s = State.new(_game())
    back = State.from_json(s.to_json())
    assert back.game_id == s.game_id and back.sport == s.sport
    assert back.stop_reason is None
