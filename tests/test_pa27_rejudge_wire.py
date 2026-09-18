"""PA-27 계약 — 딥서치 결장 명단이 **판정으로 되돌아간다** (지시문 7단계).

🔴 지시문 7단계: "추출된 결장 명단을 5단계 원장의 결장 변수로 재계산(LLM 이
   문장으로 반영하는 게 아니라 **코드가 delta 를 다시 매김**). 재계산 후 gap
   재판정. 등급이 바뀌면 원장에 `regraded_by=deepsearch` 기록."

🔴 종전 실측: `rejudge.reweigh` 를 **부르는 코드가 app/ 전체에 0건**이었다.
   U11 을 만들어 놓고 안 이었다 — 딥서치가 결장자를 찾아내도 확률이 1%p 도
   안 움직였다.

⚠️ **저장 전용이다.** `p_code`·`confidence`·`adj_pp` 는 그대로 두고 `*_after`
   에만 남긴다. 카드·발송은 이 칸을 아직 안 읽는다.
"""
import inspect
import json
import pathlib

import pytest

from app.engine import gate as G
from app.engine import pick_ledger as PL

SRC = inspect.getsource(PL.record_confirm_and_analysis)


class _Conn:
    def __init__(self, *, adj=None, p_code=0.62, grade="중"):
        self.row = {"hypothesis": {}, "p_code": p_code, "adj_pp": adj or {},
                    "p_market": 0.55, "p_prior": 0.58, "odds": None,
                    "model_probs": None, "predicted_side": "home",
                    "confidence": grade}
        self.saved = []

    async def fetchrow(self, sql, *a):
        if "FROM games" in sql:
            return {"id": 1, "sport": "soccer", "league": "세리에A",
                    "home": "H", "away": "A", "starts_at": None}
        return self.row

    async def fetch(self, sql, *a):
        return []

    async def execute(self, sql, *a):
        self.saved.append((sql, a))

    def rejudge_saves(self):
        return [a for s, a in self.saved if "regraded_by" in s]


@pytest.fixture
def no_llm(monkeypatch):
    from app.engine import analyze as AN

    async def _skip(*a, **k):
        return {"ledger": None, "skipped": "테스트"}

    monkeypatch.setattr(AN, "run", _skip)


@pytest.fixture
def extract(monkeypatch):
    """위성 추출 캐시를 갈아끼운다. `{side: {"out": [이름…]}}` 만 준다."""
    box = {}

    async def _read(_redis, _sport, _gid):
        return {"gathered_at": "x", "teams": box.get("teams") or {}}

    from app.collectors import satellite as SAT

    monkeypatch.setattr(SAT, "read_extract", _read)
    return box


async def _run(conn, extract_box, teams):
    extract_box["teams"] = teams
    return await PL.record_confirm_and_analysis(
        conn, game_id=1, gate={"label": G.OVER, "gap_pp": -9.0},
        redis=object())


# ── 되먹임이 실제로 일어난다

@pytest.mark.asyncio
async def test_딥서치_결장이_원장에_되먹임된다(no_llm, extract):
    conn = _Conn()
    await _run(conn, extract, {"home": {"out": ["A", "B"]}})
    hits = conn.rejudge_saves()
    assert hits, "재판정 결과가 저장되지 않았다 — 만들고 안 이은 것과 같다"
    adj_after = json.loads(hits[-1][1])
    assert any(k.startswith("라인업결장") for k in adj_after), adj_after


@pytest.mark.asyncio
async def test_홈_결장이면_홈_확률이_내려간다(no_llm, extract):
    """🔴 결장을 확인했는데 확률이 올라가면 신호가 거꾸로다."""
    conn = _Conn(p_code=0.62)
    await _run(conn, extract, {"home": {"out": ["A", "B"]}})
    p_after = conn.rejudge_saves()[-1][2]
    assert p_after < 0.62


@pytest.mark.asyncio
async def test_원정_결장은_홈에_유리하다(no_llm, extract):
    conn = _Conn(p_code=0.62)
    await _run(conn, extract, {"away": {"out": ["A", "B"]}})
    assert conn.rejudge_saves()[-1][2] > 0.62


@pytest.mark.asyncio
async def test_출처가_deepsearch로_남는다(no_llm, extract):
    """🔴 T-60 라인업 diff 와 **같은 칸**을 쓴다 — 출처가 없으면 못 가른다."""
    conn = _Conn()
    await _run(conn, extract, {"home": {"out": ["A", "B"]}})
    from app.engine import rejudge as RJ

    assert conn.rejudge_saves()[-1][4] == RJ.SRC_NEWS == "deepsearch"


@pytest.mark.asyncio
async def test_등급도_함께_남는다(no_llm, extract):
    conn = _Conn(p_code=0.62, grade="중")
    await _run(conn, extract, {"home": {"out": ["A", "B", "C", "D"]}})
    assert conn.rejudge_saves()[-1][3] is not None


# ── 🔴 반대 위험 — 안 해야 할 때 안 한다

@pytest.mark.asyncio
async def test_결장자가_없으면_안_쓴다(no_llm, extract):
    """🔴 빈 값을 쓰면 '안 봤다'와 '없다'가 같아진다."""
    conn = _Conn()
    await _run(conn, extract, {"home": {"out": []}, "away": {}})
    assert not conn.rejudge_saves()


@pytest.mark.asyncio
async def test_추출이_통째로_없으면_안_쓴다(no_llm, extract):
    conn = _Conn()
    await _run(conn, extract, {})
    assert not conn.rejudge_saves()


@pytest.mark.asyncio
async def test_잡음_한_명은_안_쓴다(no_llm, extract):
    """한 명(1.5%p)은 U8 잡음 문턱(2.0) 아래 — `changed` 여도 저장 안 한다.

    ⚠️ `reweigh` 는 `changed=True` 로 돌려주지만 `adj_after` 는 그대로다.
       여기서는 **저장은 일어나도 축이 안 생기는지**를 잰다.
    """
    conn = _Conn()
    await _run(conn, extract, {"home": {"out": ["A"]}})
    hits = conn.rejudge_saves()
    if hits:
        assert not any(k.startswith("라인업결장")
                       for k in json.loads(hits[-1][1]))


@pytest.mark.asyncio
async def test_게이트_대상이_아니면_재판정하지_않는다(no_llm, extract):
    """🔴 [CNF-1 2026-09-18] 단언을 **좁혔다.** 종전에는 "아무것도 안 한다"였다.

    이제 `동의`·`보드 고정`도 **S6 확인 판정까지는** 지나간다(순수 함수·0원).
    막는 것은 그 아래 — 재판정과 분석이다. 이 테스트가 지키는 것은 그쪽이다.
    ⚠️ 종전 단언(`not conn.saved`)은 "재판정이 안 돈다"의 **대리 측정**이었다.
       대리가 깨졌다고 규칙이 바뀐 것은 아니다 — 규칙을 직접 잰다.
    """
    conn = _Conn()
    extract["teams"] = {"home": {"out": ["A", "B"]}}
    got = await PL.record_confirm_and_analysis(
        conn, game_id=1, gate={"label": G.AGREE}, redis=object())
    assert not conn.rejudge_saves(), "게이트 대상이 아닌데 재판정이 돌았다"
    assert "rejudge" not in (got or {}), got


@pytest.mark.asyncio
async def test_재판정이_실패해도_분석을_막지_않는다(monkeypatch, no_llm, extract):
    """🔴 CLV·이동과 같은 규약 — 곁가지가 본선을 멈추지 않는다."""
    from app.engine import rejudge as RJ

    def _boom(**k):
        raise RuntimeError("일부러")

    monkeypatch.setattr(RJ, "reweigh", _boom)
    conn = _Conn()
    got = await _run(conn, extract, {"home": {"out": ["A", "B"]}})
    assert got is not None


# ── 🔴 원래 값을 덮지 않는다

def test_원래_칸을_덮지_않는다():
    """🔴 `p_code`·`confidence`·`adj_pp` 를 갈아쓰면 '어떻게 바뀌었나'를 잃는다."""
    save = PL._REJUDGE_SAVE
    body = save.split("SET", 1)[1].split("WHERE", 1)[0]
    for bad in ("p_code =", "confidence =", "adj_pp ="):
        assert bad not in body, bad
    for good in ("adj_after", "p_code_after", "grade_after", "regraded_by"):
        assert good in body, good


def test_INSERT_자리표_수가_맞는다():
    """🔴 자리표가 모자라면 저장이 통째로 터진다(PA-23 에서 한 번 겪었다)."""
    import re

    n = max(int(x) for x in re.findall(r"\$(\d+)", PL._REJUDGE_SAVE))
    assert n == 5


def test_칸이_스키마에_있다():
    sql = pathlib.Path("db/schema.sql").read_text(encoding="utf-8")
    assert "regraded_by" in sql


def test_결장_칸_이름을_손으로_안_적었다():
    """🔴 사본 금지 — `out` 은 `EXTRACT_SCHEMA` 의 키다."""
    from app.engine.scout_config import EXTRACT_SCHEMA

    assert "out" in EXTRACT_SCHEMA
    assert "EXTRACT_SCHEMA" in SRC, "스키마를 안 보고 이름을 지어 썼다"


def test_발송을_켜지_않는다():
    """🔴 반대 위험 — 저장 전용이다. 카드 경로 전환은 별건이다."""
    blk = SRC.split("S7 재판정", 1)[1].split("S11 분석", 1)[0]
    for bad in ("send", "dispatch", "telegram"):
        assert bad not in blk.lower(), bad
