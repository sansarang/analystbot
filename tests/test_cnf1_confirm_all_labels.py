"""CNF-1 계약 — **채점(S6)은 모든 게이트 라벨에서 돈다. 분석(S11)만 문이 있다.**

🔴 실측 2026-09-18 (운영 원장 · 최근 5일):
     가치 의심   가설 10 · 채점 10 · 미채점  0
     시장 과대   가설 10 · 채점 10 · 미채점  0
     동의        가설 18 · 채점  0 · **미채점 18**   ← 전건
   `OVER|DOUBT` 중 미채점은 0건이었다 — 원인이 하나라는 증거다.

🔴 지점: `record_confirm_and_analysis` **맨 위**의
     `if label not in (G.OVER, G.DOUBT): return None`
   이 문은 **비용**을 막으려고 놓였는데(같은 파일: "LLM 비용은 안 는다"),
   이 함수는 둘을 한다 — S6 는 **순수 함수·0원**, S11 만 LLM 이다.
   문이 위에 있어 공짜인 채점까지 막혔다.

⚠️ **반대 위험을 함께 잰다** — 문을 내렸다고 분석이 새 라벨로 새면 그게 더 큰
   결함이다(토큰이 사용자 돈이다). `동의`·`보드 고정`에서 `analyze.run` 호출이
   **0 이어야** 한다.
"""
import json

import pytest

from app.engine import gate as G
from app.engine import hypothesis as HY
from app.engine import pick_ledger as PL


class _Conn:
    """원장 대역. 실행된 SQL 을 모아 무엇이 저장됐는지 센다."""

    def __init__(self, hyp):
        self.row = {"hypothesis": hyp, "p_code": 0.55, "adj_pp": {},
                    "p_market": 0.54, "p_prior": 0.55, "odds": None,
                    "model_probs": None, "predicted_side": "home",
                    "confidence": "중"}
        self.saved = []

    async def fetchrow(self, sql, *a):
        if "FROM games" in sql:
            return {"id": 1, "sport": "mlb", "league": "MLB",
                    "home": "H", "away": "A", "starts_at": None,
                    "home_pitcher": None, "away_pitcher": None}
        return self.row

    async def fetchval(self, sql, *a):
        return None

    async def fetch(self, sql, *a):
        return []

    async def execute(self, sql, *a):
        self.saved.append((sql, a))

    def confirm_saves(self):
        """채점 저장만. 🔴 SQL 본문으로 센다 — 주석이 아니라 실행된 것이다."""
        return [a for s, a in self.saved if "unknown_axes" in s]


@pytest.fixture
def harness(monkeypatch):
    """위성 추출을 갈아끼우고 분석 호출을 **센다**."""
    calls = []

    async def _read(_redis, _sport, _gid):
        # need 가 가리키는 칸을 실제로 채워서 돌려준다.
        return {"gathered_at": "x",
                "teams": {"home": {"last3": "WWL", "out": []},
                          "away": {"last3": "LLW", "out": []}}}

    async def _run(*a, **k):
        calls.append(k.get("gate_label"))
        return {"ledger": None, "skipped": "테스트"}

    from app.collectors import satellite as SAT
    from app.engine import analyze as AN

    monkeypatch.setattr(SAT, "read_extract", _read)
    monkeypatch.setattr(AN, "run", _run)
    return calls


async def _run(label, *, side="home"):
    h = HY.build(label, sport="mlb", side=side, gap_pp=-9.0)
    conn = _Conn(json.dumps(h.as_dict(), ensure_ascii=False))
    await PL.record_confirm_and_analysis(
        conn, game_id=1, gate={"label": label, "gap_pp": -9.0}, redis=object())
    return conn, h


# ── 채점은 모든 라벨에서 돈다

@pytest.mark.asyncio
@pytest.mark.parametrize("label", [G.AGREE, G.OVER, G.DOUBT, G.BOARD])
async def test_채점이_모든_라벨에서_저장된다(harness, label):
    conn, _ = await _run(label)
    assert conn.confirm_saves(), (
        f"{label} 에서 채점이 저장되지 않았다 — 찾으라 해놓고 세지 않는다")


@pytest.mark.asyncio
async def test_동의도_need를_세운다(harness):
    """🔴 전제 — `동의` 가설은 파생용 `last3` 두 칸을 만든다."""
    _, h = await _run(G.AGREE)
    assert len(h.need) == 2
    assert {n.field for n in h.need} == {"last3"}


@pytest.mark.asyncio
async def test_동의_채점이_실제_값을_읽는다(harness):
    """빈 저장이 아니라 수집물이 반영돼야 한다 — `last3` 는 확인으로 잡힌다."""
    conn, _ = await _run(G.AGREE)
    confirmed = json.loads(conn.confirm_saves()[-1][1])
    assert confirmed, "채점은 돌았는데 확인이 0칸이다 — 수집물을 안 읽었다"
    assert all(k.endswith(".last3") for k in confirmed), confirmed


# ── 🔴 반대 위험: 분석은 새지 않는다 (토큰이 사용자 돈이다)

@pytest.mark.asyncio
@pytest.mark.parametrize("label", [G.AGREE, G.BOARD])
async def test_분석은_동의_보드에서_호출되지_않는다(harness, label):
    await _run(label)
    assert harness == [], (
        f"{label} 에서 분석 LLM 이 호출됐다 — 비용 문이 사라졌다")


@pytest.mark.asyncio
@pytest.mark.parametrize("label", [G.OVER, G.DOUBT])
async def test_분석은_종전대로_호출된다(harness, label):
    await _run(label)
    assert harness == [label], f"{label} 에서 분석이 사라졌다 — 종전 동작을 깼다"


# ── 보드 고정은 need 가 비어도 터지지 않는다

@pytest.mark.asyncio
async def test_보드고정은_need가_비어도_안전하다(harness):
    conn, h = await _run(G.BOARD)
    assert h.need == ()
    assert json.loads(conn.confirm_saves()[-1][1]) == []


# ── 사본 금지

def test_라벨을_손으로_안_적었다():
    """🔴 `동의`·`시장 과대` 문자열을 테스트에 적지 않는다 — `gate` 가 원본이다."""
    import inspect
    import pathlib

    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.strip().startswith("#"))
    body = code.split('"""', 2)[-1]        # 머리말(설명)은 제외한다
    for literal in (f'"{G.OVER}"', f'"{G.AGREE}"', f'"{G.DOUBT}"'):
        assert literal not in body, f"라벨 문자열을 손으로 적었다: {literal}"
    # 문이 S11 앞에 **있다**는 것도 코드 줄로 확인한다(주석 아님).
    fn = [ln for ln in inspect.getsource(PL.record_confirm_and_analysis)
          .splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert sum("G.OVER, G.DOUBT" in ln for ln in fn) == 1, (
        "비용 문이 없거나 둘이다 — 하나여야 한다")
