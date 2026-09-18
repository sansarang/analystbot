"""PA-6 계약 — 티어 미기입이어도 U5~U12 자리가 열린다.

🔴 실측 2026-09-16 ACLE 2경기: v3 판정 2/2 · 위성 15건 · 딥서치 성공인데
   가설·확인·가감·흐름·구조·결정축이 전부 비었다. `record_prior` 가 티어
   미기입에서 `return None` 했고, 그 뒤 줄과 호출부가 통째로 건너뛰어졌다.
"""
import pytest

from app.engine import gate as G
from app.engine import pick_ledger as PL
from app.engine import prior as P

GAME = {"sport": "soccer", "league": "ACL엘리트",
        "home": "Jeonbuk Hyundai Motors FC", "away": "Kashiwa Reysol"}


class _Conn:
    def __init__(self, game=None):
        self.saved = []
        self.game = game or GAME

    async def fetchrow(self, sql, *a):
        return dict(self.game) if "FROM games" in sql else None

    async def fetch(self, sql, *a):
        return []

    async def fetchval(self, sql, *a):
        return None

    async def execute(self, sql, *a):
        self.saved.append((sql, a))


@pytest.fixture
def no_tiers(monkeypatch):
    """티어 표는 있는데 **이 두 팀이 없다** — 운영의 ACL 상황."""
    monkeypatch.setattr(P, "load_tiers", lambda key: {"Some Other Club": 3})


@pytest.mark.asyncio
async def test_티어_미기입이면_보드고정을_돌려준다(no_tiers):
    conn = _Conn()
    out = await PL.record_prior(conn, game_id=1)
    assert out is not None, "None 이면 호출부의 U5~U12 가 건너뛰어진다"
    assert out["label"] == G.BOARD


@pytest.mark.asyncio
async def test_사전값은_여전히_NULL이다(no_tiers):
    """🔴 반대 위험 — 중앙값으로 메우면 U3 을 되돌리는 것이다."""
    out = await PL.record_prior(_Conn(), game_id=1)
    assert out["p_prior"] is None
    assert out["prior_src"] == "none"
    assert out["gap_pp"] is None and out["side"] is None


@pytest.mark.asyncio
async def test_사전값_행은_종전대로_기록된다(no_tiers):
    conn = _Conn()
    await PL.record_prior(conn, game_id=1)
    txt = " ".join(s for s, _ in conn.saved)
    assert "p_prior" in txt or "prior_src" in txt
    args = [a for _, a in conn.saved]
    assert any("티어 미기입" in str(x) for row in args for x in row)


@pytest.mark.asyncio
async def test_보드고정_가설이_저장된다(no_tiers):
    conn = _Conn()
    await PL.record_prior(conn, game_id=1)
    assert any("hypothesis" in s for s, _ in conn.saved), \
        "'찾을 것이 없다'는 가설도 기록해야 한다 — 조용한 NULL 보다 낫다"


def test_보드고정_가설은_비어_있다():
    """`hypothesis.build` 가 정한 것 — 없는 것을 찾지 않는다."""
    from app.engine import hypothesis as HY

    h = HY.build(G.BOARD, sport="soccer", side=None, bigmatch=False,
                 gap_pp=None)
    assert h.need == () and h.direction is None
    assert "찾을 것이 없다" in h.reason


@pytest.mark.asyncio
async def test_보드고정은_analyze를_부르지_않는다(monkeypatch):
    """🔴 반대 위험 — 보드까지 분석하면 무료 한도가 즉시 터진다."""
    from app.engine import analyze as AN

    calls = []

    async def _spy(*a, **k):
        calls.append(k.get("gate_label"))
        return {"ledger": None}

    monkeypatch.setattr(AN, "run", _spy)

    class _C(_Conn):
        async def fetchrow(self, sql, *a):
            if "FROM games" in sql:
                return {"id": 1, "sport": "soccer", "league": "ACL엘리트",
                        "home": "A", "away": "B", "starts_at": None}
            return {"hypothesis": {}, "p_code": 0.5, "adj_pp": {}, "p_prior": 0.5,
                    "odds": None, "model_probs": None,
                    "p_market": 0.5, "predicted_side": "home",
                    "confidence": "하"}

    out = await PL.record_confirm_and_analysis(
        _C(), game_id=1, gate={"label": G.BOARD, "gap_pp": None})
    # 🔴 [CNF-1 2026-09-18] 단언을 **좁혔다.** 보드 고정도 S6 채점까지는
    #    지나간다(공짜). 이 테스트가 지키는 것은 **analyze 가 안 불린다**이고,
    #    그건 그대로다 — `out is None` 은 그 규칙의 대리 측정이었을 뿐이다.
    assert calls == [], "보드 고정에서 분석이 호출됐다 — 무료 한도가 터진다"
    assert "analyze" not in (out or {}), out


@pytest.mark.asyncio
async def test_리그표가_없으면_종전대로_None(monkeypatch):
    """🔴 반대 위험 — '이 리그를 아예 모른다'는 다른 경우다. 범위를 넓히지 않는다."""
    monkeypatch.setattr(P, "load_tiers", lambda key: {})
    assert await PL.record_prior(_Conn(), game_id=1) is None


@pytest.mark.asyncio
async def test_티어가_있으면_동작이_안_바뀐다(monkeypatch):
    """🔴 반대 위험 — 야구 회귀. 티어가 있으면 보드 고정으로 빠지면 안 된다."""
    monkeypatch.setattr(P, "load_tiers",
                        lambda key: {"Jeonbuk Hyundai Motors FC": 1,
                                     "Kashiwa Reysol": 2})
    out = await PL.record_prior(_Conn(), game_id=1)
    # 배당이 없어 None 일 수는 있지만, **보드 고정 조기 반환은 아니어야** 한다
    if out is not None:
        assert out["prior_src"] != "none"
