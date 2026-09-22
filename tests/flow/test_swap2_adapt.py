"""[SWAP-2] 수집이 **흐름의** 게이트·가설을 본다.

사용자 2026-09-22: "바꿔끼우기 진행해라" · 갈림길 **(가) 양 팀 다 찾는다**

🔴 CLAUDE.md 가 "순서가 끊겨 있다"고 적은 그 자리다:
```
g1766 두산@KT — 같은 경기, 같은 시각
  구경로 gate_of   사전값 0.638 (tier+form) · gap +0.44  → 동의    → 추출 생략
  흐름   n03_gate  사전값 0.5655 (team_elo) · gap −10.97 → 시장과대 → 증거 필요
```
위성은 "동의"라 추출을 생략했고, 흐름은 "시장과대"로 증거를 찾다가 못 찾았다.

🔴 **두 어휘가 띄어쓰기까지 다르다.** 그대로 이으면 `gate.select` 이
   `_G.OVER`("시장 과대")와 비교해 **전건 미일치**가 되고 대상이 **조용히 0**
   이 된다. 이 파일의 첫 계약이 그것을 막는다.
"""
from __future__ import annotations

import inspect

import pytest

from app.engine import gate as G
from app.flow import adapt as A
from app.flow import labels as L


# ── 라벨 번역 ───────────────────────────────────────────────────────

def test_띄어쓰기가_다른_라벨을_옮긴다():
    """🔴 이것이 이 단위의 핵심이다 — 안 옮기면 대상이 조용히 0이 된다."""
    assert L.OVER != G.OVER, "두 어휘가 같아졌다면 이 어댑터의 전제가 바뀐 것이다"
    assert A.gate_label({"gate": L.OVER}) == G.OVER
    assert A.gate_label({"gate": L.DOUBT}) == G.DOUBT
    assert A.gate_label({"gate": L.AGREE}) == G.AGREE
    assert A.gate_label({"gate": L.BOARD}) == G.BOARD


def test_문자열을_손으로_적지_않았다():
    """🔴 사본 금지 — 양쪽 상수를 import 해서 표를 만든다.

    ⚠️ **주석을 뗀다.** 꼬리 주석(`# "보드고정" → "보드 고정"`)이 금지 문자열을
       그대로 담고 있어 원문 grep 은 거짓으로 실패한다(D46, 이 저장소 9회).
    """
    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(A._label_map).splitlines())
    assert "from app.engine import gate" in src
    assert "from app.flow import labels" in src
    for banned in ('"시장 과대"', '"가치 의심"', '"보드 고정"'):
        assert banned not in src, f"라벨을 손으로 적었다: {banned}"


def test_대응_없는_라벨은_지어내지_않는다():
    """🔴 `사전값단독` 은 구경로에 짝이 없다 — None 이고, 그 경기는 종전대로
    빅매치 판정으로 간다."""
    assert A.gate_label({"gate": L.PRIOR_ONLY}) is None
    assert A.gate_label({"gate": "없는라벨"}) is None
    assert A.gate_label(None) is None
    assert A.gate_label("문자열") is None


def test_괴리를_숫자로_옮긴다():
    assert A.gate_gap_pp({"gap_pp": -10.97}) == -10.97
    assert A.gate_gap_pp({"gap_pp": None}) is None
    assert A.gate_gap_pp({"gap_pp": "x"}) is None
    assert A.gate_gap_pp({}) is None


# ── 가설 번역 ───────────────────────────────────────────────────────

_HYP = [{"id": "H_break", "text": "우리 픽(away)을 무너뜨릴 근거",
         "vars": [{"var": "lineup_out", "is_core": True},
                  {"var": "starter_recent3", "is_core": True},
                  {"var": "park_factor", "is_core": False}]}]


def test_양_팀_다_찾는다():
    """🔴 사용자 결정 (가). 흐름 변수에는 side 가 없다 — 한쪽만 보면 놓친다."""
    need = A.need_from_hyp(_HYP)
    keys = [f"{n['side']}.{n['field']}" for n in need]
    assert "home.out" in keys and "away.out" in keys
    assert "home.last3" in keys and "away.last3" in keys


def test_대응_없는_변수는_버리되_센다(caplog):
    """⚠️ 조용히 버리지 않는다 — `park_factor` 는 기사에서 못 뽑는 칸이다."""
    import logging

    with caplog.at_level(logging.INFO):
        need = A.need_from_hyp(_HYP)
    assert all(n["field"] != "park_factor" for n in need)
    assert "park_factor" in caplog.text


def test_같은_칸을_두_번_넣지_않는다():
    """⚠️ `starter_recent3` 와 `bullpen_3d` 는 같은 `last3` 를 본다 —
    중복되면 수집이 같은 것을 두 번 찾는다."""
    hyp = [{"id": "H", "text": "t",
            "vars": [{"var": "starter_recent3"}, {"var": "bullpen_3d"}]}]
    need = A.need_from_hyp(hyp)
    keys = [f"{n['side']}.{n['field']}" for n in need]
    assert len(keys) == len(set(keys)), keys
    assert sorted(keys) == ["away.last3", "home.last3"]


def test_번역한_키를_위성이_읽는다():
    """🔴 배선의 끝 — `satellite._need_of` 가 그대로 읽어야 한다."""
    import app.collectors.satellite as SAT

    row = A.to_row({"gate": L.DOUBT, "gap_pp": -10.9}, _HYP)
    keys = SAT._need_of({"game_id": 1, "hypothesis": row["hypothesis"]})
    assert keys is not None
    assert set(keys) >= {"home.out", "away.out", "home.last3", "away.last3"}


def test_가설이_없으면_None_이다():
    """⚠️ 빈 목록("찾을 것 없음")과 None("가설 없음")은 **다르다.**"""
    assert A.to_row({"gate": L.AGREE}, [])["hypothesis"] is None
    assert A.to_row({"gate": L.AGREE}, None)["hypothesis"] is None
    assert A.need_from_hyp([{"id": "H", "vars": [{"var": "park_factor"}]}]) == []


def test_순수_함수다():
    """🔴 DB·HTTP·LLM 0건 — `hypothesis.py` 와 같은 규약."""
    import ast

    tree = ast.parse(inspect.getsource(A))
    for fn in ("gate_label", "gate_gap_pp", "need_from_hyp", "to_row"):
        node = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == fn)
        calls = {getattr(c.func, "id", "") or getattr(c.func, "attr", "")
                 for c in ast.walk(node) if isinstance(c, ast.Call)}
        for banned in ("fetch", "execute", "complete_json", "ask_json", "post"):
            assert banned not in calls, f"{fn} 이 {banned} 를 부른다"


# ── 위성 배선 ───────────────────────────────────────────────────────

def _code_only(obj) -> str:
    """🔴 주석을 뗀다 — 원문 grep 은 내 주석에 걸린다(D46, 이 저장소 8회)."""
    return "\n".join(ln.split("#", 1)[0]
                     for ln in inspect.getsource(obj).splitlines())


def test_위성이_구경로_원장을_안_읽는다():
    """🔴 **이것이 단절의 원인이었다.**"""
    import app.collectors.satellite as SAT

    sql = SAT._DUE_SQL
    assert "pick_ledger" not in sql, "슬레이트 조회가 아직 구경로 원장을 조인한다"
    src = _code_only(SAT.run_satellite)
    assert "gate_of" not in src, "아직 구경로 게이트를 계산한다"
    assert "latest_for" in src, "흐름 산출을 안 읽는다"


def test_흐름을_여기서_돌리지_않는다():
    """🔴 읽기 전용이다 — 흐름은 자기 잡(`flow_shadow_15m`)이 돌린다."""
    src = _code_only(A.latest_for)
    for banned in ("run_slate", "run_today", "run_flow"):
        assert banned not in src, f"위성이 흐름을 돌린다: {banned}"


@pytest.mark.asyncio
async def test_못_읽으면_구경로로_안_돌아간다():
    """🔴 사용자 지시 — "옛 경로로 가서는 안 된다"."""
    class _Boom:
        async def fetch(self, *a, **k):
            raise RuntimeError("DB 없음")

    assert await A.latest_for(_Boom(), [1, 2]) == {}
    assert await A.latest_for(None, [1]) == {}
    assert await A.latest_for(_Boom(), []) == {}


@pytest.mark.asyncio
async def test_game_id_를_문자열로_넘긴다():
    """⚠️ `analysis_runs.game_id` 는 **TEXT** 다(`db/schema.sql:939`).
    숫자로 비교하면 한 건도 안 맞는다."""
    seen = {}

    class _P:
        async def fetch(self, sql, *args):
            seen["sql"], seen["args"] = sql, args
            return []

    await A.latest_for(_P(), [1769, 1770])
    assert seen["args"][0] == ["1769", "1770"], seen["args"]
    assert seen["args"][1] == ["n03_gate", "n04_hyp"]
    assert "::text[]" in seen["sql"]


@pytest.mark.asyncio
async def test_최신_행만_고른다():
    """⚠️ 흐름은 15분마다 돈다 — 옛 스냅샷을 읽으면 지난 가설로 수집한다."""
    assert "DISTINCT ON" in A._LATEST_SQL
    assert "a.id DESC" in A._LATEST_SQL


@pytest.mark.asyncio
async def test_스냅샷을_행으로_옮긴다():
    import json

    snap_gate = json.dumps({"n03_gate": {"gate": L.DOUBT, "gap_pp": -10.9}})
    snap_hyp = json.dumps({"n04_hyp": _HYP})

    class _P:
        async def fetch(self, sql, *args):
            return [{"game_id": "1769", "node": "n03_gate",
                     "snapshot_json": snap_gate},
                    {"game_id": "1769", "node": "n04_hyp",
                     "snapshot_json": snap_hyp}]

    out = await A.latest_for(_P(), [1769])
    assert 1769 in out
    assert out[1769]["gate_label"] == G.DOUBT
    assert out[1769]["gate_gap_pp"] == -10.9
    keys = [f"{n['side']}.{n['field']}"
            for n in out[1769]["hypothesis"]["need"]]
    assert "away.out" in keys
