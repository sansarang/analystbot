"""PA-14 계약 — `book_gap`(D1)을 원장에 잇는다. **저장 전용.**

🔴 `book_gap` 은 만들어져 있는데 운영 호출이 0건이었다 — analyze·gate.select·
   U9 흐름·U10 구조에 이어 다섯 번째다.
⚠️ 지시문 "하지 말 것": *피나클 값이 없다고 사설 평균으로 대체하기 —
   NULL 로 두고 게이트는 사전값 기준으로 폴백.*
"""
import pathlib

import pytest

from app.engine import book_gap as BG
from app.engine import pick_ledger as PL


class _Conn:
    def __init__(self, rows):
        self.rows = rows
        self.saved = []

    async def fetch(self, sql, *a):
        return self.rows

    async def execute(self, sql, *a):
        self.saved.append((sql, a))


def _row(book, side, odds):
    return {"book": book, "side": side, "odds": odds}


BOTH = [_row(BG.SOFT_BOOK, "home", 1.50), _row(BG.SOFT_BOOK, "away", 2.80),
        _row(BG.SHARP_BOOK, "home", 1.65), _row(BG.SHARP_BOOK, "away", 2.40)]


@pytest.mark.asyncio
async def test_pinnacle_gap이_원장에_남는다():
    conn = _Conn(BOTH)
    got = await PL.record_book_gap(conn, game_id=1)
    assert got and got["gap_pp"] == pytest.approx(5.86, abs=0.01)
    assert conn.saved, "저장 SQL 이 안 나갔다"
    sql, args = conn.saved[-1]
    assert "pinnacle_gap" in sql
    assert args[1] == pytest.approx(5.86, abs=0.01)
    assert "후함" in args[2]


@pytest.mark.asyncio
@pytest.mark.parametrize("rows", [
    [_row(BG.SOFT_BOOK, "home", 1.50), _row(BG.SOFT_BOOK, "away", 2.80)],  # 샤프 없음
    [_row(BG.SHARP_BOOK, "home", 1.65), _row(BG.SHARP_BOOK, "away", 2.40)],  # 사설 없음
    [],
])
async def test_한쪽_북이_없으면_NULL이다(rows):
    """🔴 반대 위험 — 사설 평균으로 대체하면 D1 이 거짓말이 된다."""
    conn = _Conn(rows)
    assert await PL.record_book_gap(conn, game_id=1) is None
    assert not conn.saved, "값이 없는데 저장했다"


@pytest.mark.asyncio
async def test_강팀_쪽을_기준으로_잰다():
    """원정이 강팀이면 원정 쪽으로 잰다."""
    rows = [_row(BG.SOFT_BOOK, "home", 2.80), _row(BG.SOFT_BOOK, "away", 1.50),
            _row(BG.SHARP_BOOK, "home", 2.40), _row(BG.SHARP_BOOK, "away", 1.65)]
    got = await PL.record_book_gap(_Conn(rows), game_id=1)
    assert got["side"] == "away"


@pytest.mark.asyncio
async def test_실패해도_예외가_밖으로_안_나간다():
    """저장 전용이다 — 측정 장치가 판정을 죽이면 안 된다."""
    class _Boom(_Conn):
        async def fetch(self, sql, *a):
            raise RuntimeError("DB 없음")

    with pytest.raises(RuntimeError):
        await PL.record_book_gap(_Boom([]), game_id=1)
    # 🔴 호출부가 감싼다 — 그 자리가 실제로 try 로 덮여 있는지 본다
    src = pathlib.Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    blk = src.split("record_book_gap(conn")[1][:300]
    assert "except Exception" in blk


def test_판정을_건드리지_않는다():
    """🔴 반대 위험 — 기준선 교체(p_market → p_sharp)는 **다음 단위**다."""
    src = pathlib.Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    fn = src.split("async def record_book_gap")[1].split("\nasync def ")[0]
    for banned in ("p_code", "predicted_side", "confidence", "p_prior",
                   "gate_label", "p_market"):
        assert banned not in fn, f"저장 전용인데 {banned} 를 건드린다"


def test_북이름과_문턱을_손으로_안_적었다():
    """🔴 사본 금지 — `book_gap` 상수가 원본이다."""
    src = pathlib.Path("app/engine/pick_ledger.py").read_text(encoding="utf-8")
    fn = src[src.index("async def record_book_gap"):]
    assert '"sharp_proxy"' not in fn and '"soft_proxy"' not in fn
    assert "BG.SHARP_BOOK" in fn and "BG.SOFT_BOOK" in fn
    assert "3.0" not in fn, "문턱을 손으로 적었다"


def test_칸이_스키마에_있다():
    src = pathlib.Path("db/schema.sql").read_text(encoding="utf-8")
    assert "pinnacle_gap" in src and "pinnacle_gap_label" in src
