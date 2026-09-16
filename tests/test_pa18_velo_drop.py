"""PA-18 계약 — 구속 하락을 가감까지 잇는다 (지시문 D2 야구).

> 선발 최근 등판 평균 구속이 시즌 평균 대비 **−1.0mph 이상**이면
> `velo_drop` → 그 팀 **−2%p**(변수 대장 사전값).

🔴 종전에는 `statcast_velo` 가 `delta_mph` 를 정확히 내는데 SAT-8 이 그것을
   **문장으로 바꿔 기사로만** 넣고 숫자는 버렸다. 판정이 볼 길이 없었다.
🔴 통로는 **Redis**다(사용자 결정 2026-09-16) — 구속은 하루 지나면 무의미해
   TTL 로 사는 값이라 원장·스키마를 안 늘린다. 판정 경로에서 Savant 를
   치지 않는다(느리고 실패한다).
"""
import pathlib

import pytest

from app.collectors import satellite as SAT
from app.collectors import statcast_velo as SV
from app.collectors.lineups import STATUS_CONFIRMED
from app.engine import adjust as A
from app.engine import prob as P


class _Redis:
    def __init__(self, store=None):
        self.store = store or {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, **kw):
        self.store[k] = v
        return True


class _Pool:
    async def fetch(self, sql, *a):
        return []

    async def fetchval(self, sql, *a):
        return None


def _jg(redis=None):
    return {"game_id": 7, "sport": "mlb", "home": "Orix", "away": "SoftBank",
            "starts_at": "2026-09-17T09:00:00+00:00",
            "lineup_status": STATUS_CONFIRMED, "_redis": redis,
            "research": {"today_nine": {"home": ["X"], "away": ["Y"]}}}


def test_변수_대장에_있다():
    """D2: 야구 −2%p."""
    rule = P.ADJ_RULES["baseball"]["구속하락"]
    assert rule[0] == "velo_drop"
    assert rule[1] == -2.0 and rule[2] == -2.0


def test_문턱을_손으로_안_적었다():
    """🔴 사본 금지 — 1.0mph 는 statcast_velo 가 원본이다."""
    src = pathlib.Path("app/engine/adjust.py").read_text(encoding="utf-8")
    assert "VELO_DELTA_MIN as VELO_MIN" in src
    blk = src.split("구속 하락 (D2")[1].split("이동 연전")[0]
    assert "1.0" not in blk, "문턱을 손으로 적었다"


@pytest.mark.asyncio
async def test_판정_경로에서_HTTP를_안_켠다(monkeypatch):
    """🔴 반대 위험 — Savant 를 판정 중에 치면 느리고 실패한다."""
    called = []

    async def _boom(*a, **k):
        called.append(1)
        raise AssertionError("판정 경로에서 Savant 를 쳤다")

    monkeypatch.setattr(SV, "fetch_pitcher_statcast", _boom)
    monkeypatch.setattr(SV, "pitcher_trend", _boom)
    await A.attach(_jg(_Redis()), _Pool())
    assert not called


@pytest.mark.asyncio
@pytest.mark.parametrize("velo,want", [
    # 🔴 부호 규약은 `out_starters` 와 같다 — **홈 빼기 원정**이고, 규칙의
    #    계수가 음수(-2.0)라 양수면 홈에 불리가 된다.
    #    (처음에 기대값을 뒤집어 적었다가 틀렸다.)
    ({"Orix": -1.5, "SoftBank": 0.2}, 1),      # 홈만 떨어짐 → +1 × -2%p = 홈 불리
    ({"Orix": 0.1, "SoftBank": -1.3}, -1),     # 원정만 떨어짐 → 홈 유리
    ({"Orix": -1.5, "SoftBank": -1.2}, 0),     # 둘 다 → 상쇄
    ({"Orix": -0.5, "SoftBank": 0.0}, 0),      # 문턱 미달
    ({"Orix": 2.0, "SoftBank": 0.0}, 0),       # 오른 것은 신호가 아니다
])
async def test_홈기준_부호(velo, want):
    import json

    r = _Redis({SAT._velo_key("mlb", 7): json.dumps(velo)})
    jg = _jg(r)
    await A.attach(jg, _Pool())
    assert jg.get("velo_drop") == want


@pytest.mark.asyncio
async def test_값이_없으면_미계산이다():
    """🔴 반대 위험 — 모르는 것을 0 으로 채우면 '떨어지지 않았다'가 된다."""
    jg = _jg(_Redis())
    await A.attach(jg, _Pool())
    assert jg.get("velo_drop") is None
    assert "velo_drop" in (jg.get("adj_missing") or [])


@pytest.mark.asyncio
async def test_위성이_숫자를_남긴다():
    import json

    r = _Redis()
    await SAT._write_velo(r, {"game_id": 7, "sport": "mlb"}, {"Orix": -1.2})
    got = await SAT.read_velo(r, "mlb", 7)
    assert got == {"Orix": -1.2}
    assert json.loads(r.store[SAT._velo_key("mlb", 7)]) == {"Orix": -1.2}


def test_SAT8이_저장을_부른다():
    src = pathlib.Path("app/collectors/satellite.py").read_text(encoding="utf-8")
    # ⚠️ **정의부**를 본다 — 첫 등장은 호출부라 본문이 안 잡힌다.
    blk = src.split("async def _mlb_velocity_articles")[1][:2500]
    assert 'velo[team] = t.get("delta_mph")' in blk, "숫자를 여전히 버린다"
    assert "_write_velo(" in blk
