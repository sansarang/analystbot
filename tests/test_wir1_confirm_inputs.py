"""WIR-1 계약 — **이미 가진 사실이 채점 입력으로 간다** (FORKS F-11 · F-13).

🔴 종전: 채점(`hypothesis.confirm`)이 **위성 기사 추출 상자만** 읽었다.
   실측 2026-09-18 운영 원장(최근 5일): `out` 확인 5/52(9.6%) · `last3` 0/26(0%).

🔴 그런데 둘 다 이미 우리 손에 있었다:
     결장   `absences.py` 가 statsapi(IL 명단 + 확정 라인업)로 산출 →
            `research["absences"]`. 실측 운영 캐시(analysis:mlb:2026-09-18):
            "Cincinnati Reds의 Hunter Greene(선발) Injured 60-Day로 결장"
     최근3  `games` 표 (`status='final'`)

⚠️ 딥서치 근거(docs/FORKS.md):
   F-13 공식 statsapi 가 뉴스 스크래핑보다 신뢰도가 높다. 충돌 시 공식이 이긴다(F-2).
   F-11 최근 3~5경기는 승패 예측력이 0 에 가깝다 → `last3` 는 파생(U/O) 재료로만.

⚠️ **LLM 콜 0 · 새 수집 0.** 이미 있는 값을 잇기만 한다.
"""
import json

import pytest

from app.collectors import absences as ABS
from app.engine import gate as G
from app.engine import hypothesis as HY
from app.engine import pick_ledger as PL

HOME, AWAY = "Cincinnati Reds", "Chicago Cubs"


class _Conn:
    def __init__(self, hyp, *, last3=True):
        self.row = {"hypothesis": hyp, "p_code": 0.55, "adj_pp": {},
                    "p_market": 0.54, "p_prior": 0.62, "odds": None,
                    "model_probs": None, "predicted_side": "home",
                    "confidence": "중"}
        self.saved = []
        self._last3 = last3

    async def fetchrow(self, sql, *a):
        if "FROM games" in sql:
            return {"id": 1, "sport": "mlb", "league": "MLB",
                    "home": HOME, "away": AWAY, "starts_at": None,
                    "home_pitcher": None, "away_pitcher": None}
        return self.row

    async def fetchval(self, sql, *a):
        return None

    async def fetch(self, sql, *a):
        if self._last3 and "ORDER BY starts_at DESC" in sql and "LIMIT 3" in sql:
            team = a[1]
            return [{"home": team, "away": "X", "home_score": 5,
                     "away_score": 3, "starts_at": None},
                    {"home": "X", "away": team, "home_score": 1,
                     "away_score": 4, "starts_at": None}]
        return []

    async def execute(self, sql, *a):
        self.saved.append((sql, a))

    def confirm(self):
        for s, a in self.saved:
            if "unknown_axes" in s:
                return {"confirmed": json.loads(a[1]),
                        "refuted": json.loads(a[2]),
                        "unknown": json.loads(a[3])}
        return None


@pytest.fixture
def harness(monkeypatch):
    """위성은 **빈손**이다(실측: out=[] 이 30건 중 25건). 분석은 안 부른다."""
    async def _read(_r, _s, _g):
        return {"gathered_at": "x",
                "teams": {"home": {"out": [], "doubt": [], "last3": []},
                          "away": {"out": [], "doubt": [], "last3": []}}}

    async def _skip(*a, **k):
        return {"ledger": None, "skipped": "테스트"}

    from app.collectors import satellite as SAT
    from app.engine import analyze as AN

    monkeypatch.setattr(SAT, "read_extract", _read)
    monkeypatch.setattr(AN, "run", _skip)


async def _run(conn, *, absences=None, label=G.DOUBT):
    h = HY.build(label, sport="mlb", side="home", gap_pp=9.0)
    conn.row["hypothesis"] = json.dumps(h.as_dict(), ensure_ascii=False)
    await PL.record_confirm_and_analysis(
        conn, game_id=1, gate={"label": label, "gap_pp": 9.0},
        redis=object(), absences=absences)
    return conn.confirm()


# ── F-13 공식 결장

@pytest.mark.asyncio
async def test_공식_결장이_확인으로_잡힌다(harness):
    """🔴 위성이 빈손이어도 공식 명단이 있으면 확인이다."""
    conn = _Conn(None)
    got = await _run(conn, absences=[
        f"{HOME}의 Hunter Greene(선발) Injured 60-Day로 결장",
        f"{AWAY}의 Someone Else(선수) Injured 10-Day로 결장"])
    assert "home.out" in got["confirmed"], got
    assert "away.out" in got["confirmed"], got


@pytest.mark.asyncio
async def test_결장이_없으면_종전대로다(harness):
    """🔴 반대 위험 — 없는 결장을 만들지 않는다."""
    got = await _run(_Conn(None), absences=None)
    assert "home.out" not in got["confirmed"]
    assert "home.out" in got["refuted"]


@pytest.mark.asyncio
async def test_기사_결장을_덮지_않고_합친다(harness, monkeypatch):
    """🔴 F-2 — 기사는 휴식·부진을 잡고 공식은 IL 을 잡는다. **합친다.**"""
    async def _read(_r, _s, _g):
        return {"gathered_at": "x",
                "teams": {"home": {"out": ["기사가 찾은 선수"], "doubt": [],
                                   "last3": []},
                          "away": {"out": [], "doubt": [], "last3": []}}}

    from app.collectors import satellite as SAT

    monkeypatch.setattr(SAT, "read_extract", _read)
    conn = _Conn(None)
    await _run(conn, absences=[f"{HOME}의 A(선수) Injured 10-Day로 결장"])
    # 합쳐진 목록은 `rejudge` 저장에서 보인다 — 둘 다 살아 있어야 한다.
    assert conn.confirm()["confirmed"], conn.confirm()


@pytest.mark.asyncio
async def test_팀을_손으로_가르지_않는다():
    """🔴 사본 금지 — 분리는 `performance._split_absences` 가 원본이다."""
    import inspect

    src = inspect.getsource(PL.record_confirm_and_analysis)
    code = "\n".join(ln for ln in src.splitlines()
                     if ln.strip() and not ln.strip().startswith("#"))
    assert "_split_absences" in code, "팀 분리를 직접 구현했다"
    assert "의 " not in code.split("_split_absences")[0][-400:], \
        "문장 형식을 손으로 파싱한다"


def test_결장_문장_형식이_원본과_묶여_있다():
    """🔴 `_describe` 형식이 바뀌면 분리가 조용히 깨진다 — 실제 출력으로 잰다."""
    from app.engine.performance import _split_absences

    line = ABS._describe(HOME, "Hunter Greene", None, "Injured 60-Day")
    h, a = _split_absences([line], {"home": HOME, "away": AWAY})
    assert h == [line] and a == [], (line, h, a)


# ── F-11 최근 3경기

@pytest.mark.asyncio
async def test_최근3경기를_DB에서_채운다(harness):
    conn = _Conn(None)
    got = await _run(conn)
    assert "home.last3" in got["confirmed"], got


@pytest.mark.asyncio
async def test_기사가_채웠으면_DB로_덮지_않는다(harness, monkeypatch):
    """⚠️ 기사 값이 있으면 그대로 둔다 — 출처를 뒤섞지 않는다."""
    async def _read(_r, _s, _g):
        return {"gathered_at": "x",
                "teams": {"home": {"out": [], "doubt": [], "last3": ["기사값"]},
                          "away": {"out": [], "doubt": [], "last3": []}}}

    from app.collectors import satellite as SAT

    monkeypatch.setattr(SAT, "read_extract", _read)
    got = await _run(_Conn(None), label=G.AGREE)
    assert "home.last3" in got["confirmed"], got


@pytest.mark.asyncio
async def test_DB에_경기가_없으면_만들지_않는다(harness):
    """🔴 반대 위험 — 시즌 초·신규 리그는 빈손이다. 지어내지 않는다."""
    got = await _run(_Conn(None, last3=False))
    assert "home.last3" not in got["confirmed"]


def test_last3_한_줄_형식():
    """`_last3_line` 은 점수 비교 한 줄이다 — 승/패/무."""
    f = PL._last3_line
    assert f({"home": "A", "away": "B", "home_score": 5, "away_score": 3,
              "starts_at": None}, "A").startswith("승")
    assert f({"home": "A", "away": "B", "home_score": 1, "away_score": 4,
              "starts_at": None}, "A").startswith("패")
    assert f({"home": "A", "away": "B", "home_score": 2, "away_score": 2,
              "starts_at": None}, "A").startswith("무")
    # 원정 기준도 같은 규칙이다
    assert f({"home": "A", "away": "B", "home_score": 1, "away_score": 4,
              "starts_at": None}, "B").startswith("승")


# ── 반대 위험: 비용·범위

@pytest.mark.asyncio
async def test_LLM을_부르지_않는다(harness, monkeypatch):
    """🔴 이 배선은 **콜 0** 이다. 한 건이라도 늘면 토큰이 새는 것이다."""
    calls = []

    async def _spy(*a, **k):
        calls.append(k.get("gate_label"))
        return {"ledger": None}

    from app.engine import analyze as AN

    monkeypatch.setattr(AN, "run", _spy)
    await _run(_Conn(None), absences=[f"{HOME}의 A(선수) Injured 10-Day로 결장"],
               label=G.AGREE)
    assert calls == [], "동의 라벨에서 분석이 호출됐다"


@pytest.mark.asyncio
async def test_보강이_실패해도_채점은_저장된다(harness, monkeypatch):
    """🔴 측정 장치가 본체를 죽이면 안 된다."""
    def _boom(*a, **k):
        raise RuntimeError("분리 실패")

    import app.engine.performance as PF

    monkeypatch.setattr(PF, "_split_absences", _boom)
    got = await _run(_Conn(None), absences=["형식이 이상한 문장"])
    assert got is not None, "보강 실패가 채점 저장을 막았다"
