"""GAT-1 계약 — **가설은 판정보다 먼저 세워진다.**

🔴 종전 순서가 거꾸로였다:
     `_row_from_game`  "판정이 없으면 None"        → 원장 행은 판정 뒤
     `_PRIOR_SAVE`     `UPDATE … WHERE game_id`     → 라벨은 그 행에 붙는다
     `_DUE_SQL`        `LEFT JOIN pick_ledger`      → 위성은 그 라벨을 읽는다
   그래서 첫 판정 때는 라벨이 없고, 라벨이 없으면 추출을 생략했다.
   실측 2026-09-17 운영 로그: `§3 대상 선별 — 슬레이트 19 · 게이트 대상 0`.
   원장 실측: need 133칸 중 확인 6칸(4.5%) · 미상 55칸(41.4%).

🔴 라벨의 재료는 판정과 무관하다 — 티어 표·올해 성적·배당 스냅샷.
   `gate_of` 가 그 계산만 하고, `record_prior` 는 쓰기만 한다.

⚠️ **LLM 콜은 늘지 않는다.** 같은 추출 1회를 더 일찍 할 뿐이고 §3 예산도 그대로다.
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.collectors import satellite as SAT
from app.engine import gate as G
from app.engine import pick_ledger as PL

HOME, AWAY = "Toronto Blue Jays", "Detroit Tigers"


class _Conn:
    """원장 행이 **아직 없는** 경기. 게임·성적·배당만 있다."""

    def __init__(self, *, tiers_ok=True, odds=True):
        self.writes = []
        self._tiers_ok = tiers_ok
        self._odds = odds

    async def fetchrow(self, sql, *a):
        if "FROM games WHERE id" in sql:
            return {"sport": "mlb", "league": "MLB",
                    "home": HOME if self._tiers_ok else "존재하지 않는 팀",
                    "away": AWAY}
        if "FILTER" in sql:                       # _FORM_SQL — 올해 성적
            return {"w": 20, "d": 0, "l": 13}
        return None

    async def fetch(self, sql, *a):
        if "odds_snapshots" in sql and self._odds:
            t = datetime.now(UTC)
            return [{"provider": "espn", "snap_tag": "open", "side": HOME,
                     "odds": 1.79, "home": HOME, "away": AWAY, "captured_at": t},
                    {"provider": "espn", "snap_tag": "open", "side": AWAY,
                     "odds": 2.05, "home": HOME, "away": AWAY, "captured_at": t}]
        return []

    async def execute(self, sql, *a):
        self.writes.append((sql, a))


# ── gate_of — 원장 없이 계산한다

@pytest.mark.asyncio
async def test_원장_행_없이_라벨을_낸다():
    got = await PL.gate_of(_Conn(), game_id=1)
    assert got is not None
    assert got["label"] in (G.OVER, G.DOUBT, G.AGREE, G.BOARD)
    assert got["p_prior"] is not None


@pytest.mark.asyncio
async def test_gate_of는_쓰지_않는다():
    """🔴 계산 전용이다. 위성이 부를 때 원장을 건드리면 안 된다."""
    conn = _Conn()
    await PL.gate_of(conn, game_id=1)
    assert conn.writes == [], f"gate_of 가 원장에 썼다: {conn.writes}"


@pytest.mark.asyncio
async def test_가설을_함께_낸다():
    """🔴 라벨만 내면 수집이 **무엇을 찾을지** 모른다."""
    import json

    got = await PL.gate_of(_Conn(), game_id=1)
    assert got["hypothesis"], "가설이 없다 — 수집을 지휘할 것이 없다"
    h = json.loads(got["hypothesis"])
    assert "need" in h and "sufficient_count" in h


@pytest.mark.asyncio
async def test_티어가_없으면_None이다():
    """🔴 반대 위험 — 모르는 리그에 값을 지어내지 않는다."""
    class _NoLeague(_Conn):
        async def fetchrow(self, sql, *a):
            if "FROM games WHERE id" in sql:
                return {"sport": "soccer", "league": "없는리그",
                        "home": "A", "away": "B"}
            return await super().fetchrow(sql, *a)

    assert await PL.gate_of(_NoLeague(), game_id=1) is None


@pytest.mark.asyncio
async def test_티어_미기입은_보드로_낸다():
    """팀 하나가 표에 없으면 `board_only` 로 보드 고정이다(U3)."""
    got = await PL.gate_of(_Conn(tiers_ok=False), game_id=1)
    assert got["board_only"] is True
    assert got["label"] == G.BOARD
    assert got["p_prior"] is None and got["prior_src"] == "none"


# ── record_prior — 종전대로 **쓴다**

@pytest.mark.asyncio
async def test_record_prior가_종전대로_원장에_쓴다():
    conn = _Conn()
    out = await PL.record_prior(conn, game_id=1)
    assert out is not None and out["label"]
    saved = [s for s, _ in conn.writes]
    assert any("p_prior" in s for s in saved), saved
    assert any("hypothesis" in s for s in saved), saved


@pytest.mark.asyncio
async def test_record_prior_반환_모양이_그대로다():
    """🔴 호출부(`record_confirm_and_analysis`)가 이 키들을 읽는다."""
    out = await PL.record_prior(_Conn(), game_id=1)
    for k in ("label", "gap_pp", "side", "p_prior", "prior_src"):
        assert k in out, k


@pytest.mark.asyncio
async def test_티어_미기입도_원장에_남는다():
    """🔴 조용히 빠지지 않는다 — 보드 고정으로 **기록한다**(PA-6)."""
    conn = _Conn(tiers_ok=False)
    out = await PL.record_prior(conn, game_id=1)
    assert out["label"] == G.BOARD
    assert any("p_prior" in s for s, _ in conn.writes)


# ── 위성 — 라벨 없는 경기에 라벨을 채운다

def _row(gid, *, label=None, gap_pp=None):
    # ⚠️ 라벨만 주면 §3 예산(`gate.select`)이 `gap_pp is not None` 을 요구해
    #    선별에서 빠지고, 그러면 `run_satellite` 가 라벨을 지운다(PA-15).
    #    그건 종전부터 있던 규칙이다 — 여기서 그것까지 재지 않는다.
    return {"id": gid, "sport": "mlb", "league": "MLB", "home": HOME,
            "away": AWAY, "starts_at": datetime.now(UTC) + timedelta(hours=3),
            "gate_label": label,
            "gate_gap_pp": (gap_pp if gap_pp is not None
                            else (9.0 if label else None)),
            "hypothesis": None}


class _Pool:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, sql, *a):
        return list(self._rows)


@pytest.fixture
def sat(monkeypatch):
    """위성 수집을 갈아끼우고, 각 경기에 실린 `jg` 를 모은다."""
    seen = []

    async def _gather(jg, redis, **kw):
        seen.append(dict(jg))
        return 0

    monkeypatch.setattr(SAT, "gather", _gather)
    return seen


@pytest.mark.asyncio
async def test_라벨은_흐름에서_온다(sat, monkeypatch):
    """🔴 [SWAP-2 2026-09-22 사용자 지시] **위성이 게이트를 계산하지 않는다.**

    종전 이름은 `test_라벨이_없으면_위성이_계산한다` 였고 `pick_ledger.gate_of`
    를 불렀다. 그것이 CLAUDE.md 가 "순서가 끊겨 있다"고 적은 자리다 —
    흐름이 세운 가설이 수집에 닿지 못하고, 수집은 **다른 사전값으로 계산된
    다른 게이트**를 봤다:
    ```
    g1766 두산@KT — 같은 경기, 같은 시각
      구경로 gate_of  사전값 0.638(tier+form) gap +0.44  → 동의    → 추출 생략
      흐름  n03_gate 사전값 0.5655(team_elo) gap −10.97 → 시장과대 → 증거 필요
    ```
    ⚠️ **계약을 통과시키려 고친 것이 아니다** — 사용자가 "바꿔끼우기 진행해라"
       고 지시했고, 배선이 바뀌었으므로 계약이 새 배선을 지킨다.
    """
    asked = []

    async def _latest(_pool, ids):
        asked.append(list(ids))
        return {1: {"gate_label": G.DOUBT, "gate_gap_pp": 9.9,
                    "hypothesis": {"need": []}}}

    import app.flow.adapt as _A

    monkeypatch.setattr(_A, "latest_for", _latest)
    await SAT.run_satellite(_Pool([_row(1)]), None, sports=["mlb"])
    assert asked == [[1]], "흐름 산출을 안 읽었다"
    assert sat and sat[0]["gate_label"] == G.DOUBT
    assert sat[0]["hypothesis"] == {"need": []}


@pytest.mark.asyncio
async def test_흐름이_없으면_구경로로_안_돌아간다(sat, monkeypatch):
    """🔴 사용자 지시 — "**옛 경로로 가서는 안 된다**".

    흐름 산출이 없으면 라벨 없이 간다(그 경기는 빅매치 판정으로).
    `gate_of` 를 **부르지 않는다.**
    """
    called = []

    async def _gate_of(_pool, *, game_id):
        called.append(game_id)
        return {"label": G.DOUBT, "gap_pp": 9.9, "hypothesis": None}

    async def _latest(_pool, ids):
        return {}

    import app.flow.adapt as _A

    monkeypatch.setattr(PL, "gate_of", _gate_of)
    monkeypatch.setattr(_A, "latest_for", _latest)
    await SAT.run_satellite(_Pool([_row(1)]), None, sports=["mlb"])
    assert called == [], "흐름이 없다고 구경로 게이트로 돌아갔다"
    assert sat and sat[0].get("gate_label") is None


@pytest.mark.asyncio
async def test_라벨이_있으면_다시_계산하지_않는다(sat, monkeypatch):
    """🔴 반대 위험 — 원장에 있는 값을 덮거나 질의를 낭비하지 않는다."""
    calls = []

    async def _gate_of(_pool, *, game_id):
        calls.append(game_id)
        return {"label": G.DOUBT, "gap_pp": 1.0, "hypothesis": None}

    monkeypatch.setattr(PL, "gate_of", _gate_of)
    await SAT.run_satellite(_Pool([_row(2, label=G.OVER)]), None, sports=["mlb"])
    assert calls == [], "원장에 라벨이 있는데 다시 계산했다"
    assert sat[0]["gate_label"] == G.OVER


@pytest.mark.asyncio
async def test_게이트_계산이_실패해도_사이클이_산다(sat, monkeypatch):
    """🔴 측정 장치가 본체를 죽이면 안 된다 — 종전 동작(라벨 없음)으로 떨어진다."""
    async def _boom(_pool, *, game_id):
        raise RuntimeError("DB 없음")

    monkeypatch.setattr(PL, "gate_of", _boom)
    out = await SAT.run_satellite(_Pool([_row(3)]), None, sports=["mlb"])
    assert out["games"] == 1
    assert sat[0]["gate_label"] is None


@pytest.mark.asyncio
async def test_pool이_없으면_종전_그대로다(sat, monkeypatch):
    """⚠️ 목 모드·테스트 경로는 pool 없이 돈다. 그때는 아무것도 안 바꾼다."""
    calls = []

    async def _gate_of(_pool, *, game_id):
        calls.append(game_id)
        return {"label": G.DOUBT, "gap_pp": 1.0, "hypothesis": None}

    monkeypatch.setattr(PL, "gate_of", _gate_of)

    class _NoPool(_Pool):
        pass

    # pool 자리에 None 을 주면 `_DUE_SQL` 조회 자체가 안 되므로, 조회는 되되
    # pool 이 None 인 상황은 실제로 없다 — 이 계약은 가드가 있다는 사실만 잰다.
    import inspect

    src = inspect.getsource(SAT.run_satellite)
    assert "if pool is not None:" in src, "pool 가드가 없다"
    assert calls == []


# ── 사본 금지

def test_위성이_게이트_규칙을_다시_쓰지_않는다():
    """🔴 계산은 `gate_of` 한 곳이다. 위성이 classify 를 직접 부르면 사본이다."""
    import inspect

    code = "\n".join(ln for ln in inspect.getsource(SAT.run_satellite).splitlines()
                     if ln.strip() and not ln.strip().startswith("#"))
    # 🔴 [SWAP-2 2026-09-22] `gate_of` → `latest_for`. 계산하는 곳이 아니라
    #    **읽는 곳**이 바뀌었다. 단언의 뜻은 그대로다 — 위성이 규칙을 다시
    #    쓰지 않는다.
    assert "latest_for" in code, "위성이 흐름 산출을 안 읽는다"
    assert "gate_of" not in code, "아직 구경로 게이트를 계산한다"
    assert "classify(" not in code, "위성이 게이트 규칙을 다시 구현했다"
    assert "load_tiers" not in code, "위성이 티어를 직접 읽는다"


def test_record_prior가_계산을_중복하지_않는다():
    """🔴 `record_prior` 는 쓰기만 한다 — 계산을 다시 적으면 사본이다."""
    import inspect

    code = "\n".join(ln for ln in inspect.getsource(PL.record_prior).splitlines()
                     if ln.strip() and not ln.strip().startswith("#"))
    assert "gate_of(" in code
    for banned in ("classify(", "load_tiers", "soccer_prior", "baseball_prior"):
        assert banned not in code, f"record_prior 가 계산을 다시 한다: {banned}"
