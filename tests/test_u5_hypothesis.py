"""U5 — 가설 H1. 검색 **전에** 무엇을 찾을지 정한다.

🔴 지금까지는 수집이 need 와 무관하게 전부 돌았다. 그래서 S6(확인 판정)이
   "무엇을 확인해야 하는가"를 몰랐고 S9(구조 픽)가 "무엇이 충족됐나"로 고를
   수 없었다. 지시문이 "페이블 순서의 핵심"이라고 적은 자리다.
"""
from __future__ import annotations

import inspect
import pathlib

import pytest

from app.engine import gate as G
from app.engine import hypothesis as H


def _b(label, **kw):
    kw.setdefault("sport", "soccer")
    kw.setdefault("side", "home")
    return H.build(label, **kw)


# ── 게이트 × 종목 여섯 조합

@pytest.mark.parametrize("sport", ["soccer", "mlb"])
@pytest.mark.parametrize("label", [G.OVER, G.DOUBT, G.AGREE])
def test_게이트x종목_여섯_조합의_need(label, sport):
    h = _b(label, sport=sport, gap_pp=10.0)
    assert h.need, f"{label}/{sport} 에 need 가 없다"
    assert all(n.field in H.FIELDS for n in h.need), [n.field for n in h.need]
    assert all(n.side in (H.HOME, H.AWAY) for n in h.need)
    assert all(n.why for n in h.need), "왜 찾는지가 비었다"


def test_시장과대는_반대편을_세운다():
    h = _b(G.OVER, side="home", gap_pp=-15.0)
    assert h.direction == H.AWAY, "시장이 홈을 높게 보는데 홈을 고른다"
    keys = H.need_keys(h)
    assert "away.out" in keys, "반대편 근거를 안 찾는다"
    assert "home.midweek" in keys, "시장이 높게 본 쪽 약점을 안 찾는다"


def test_가치의심은_우리쪽을_무너뜨린다():
    h = _b(G.DOUBT, side="home", gap_pp=12.0)
    assert h.direction == H.HOME
    keys = H.need_keys(h)
    assert "home.out" in keys and "home.midweek" in keys
    assert "away.out" in keys, "상대가 강할 근거를 안 본다"


def test_동의는_파생_need만():
    h = _b(G.AGREE, gap_pp=1.0)
    assert h.direction is None
    assert set(H.need_keys(h)) == {"home.last3", "away.last3"}
    assert "파생" in h.reason or "승패" in h.reason


def test_보드고정은_need가_없다():
    """🔴 반대 위험 — 없는 것을 찾지 않는다. 수집도 하지 않는다."""
    h = _b(G.BOARD, side=None)
    assert h.direction is None
    assert h.need == ()
    assert H.need_keys(h) == []


def test_무승부_방향이면_반대편이_없다():
    """경계 — draw 는 반대편이 없다. 지어내지 않는다."""
    h = _b(G.OVER, side=G.SIDES[1], gap_pp=-9.0)
    assert h.direction is None and h.need == ()


def test_빅매치는_sufficient_3():
    assert _b(G.DOUBT, gap_pp=9.0, bigmatch=False).sufficient_count == 2
    assert _b(G.DOUBT, gap_pp=9.0, bigmatch=True).sufficient_count == 3
    assert (H.SUFFICIENT_DEFAULT, H.SUFFICIENT_BIGMATCH) == (2, 3)


# ── 🔴 사본 금지 · 순수 함수

#: 🔴 지시문 3-2 의 추출 스키마 8칸. `hypothesis.FIELDS` 가 이것과 같아야
#   U7 이 need 와 수집 결과를 맞출 수 있다.
SCHEMA_8 = ("out", "doubt", "xi_status", "xi", "bench_notable",
            "last3", "midweek", "notes")


def test_need_이름이_추출_스키마_8칸과_같다():
    """🔴 두 이름표를 만들면 U7 이 영영 못 맞춘다."""
    assert tuple(H.FIELDS) == SCHEMA_8


def test_S5가_8칸을_전부_저장한다():
    """🔴 U5 때는 8칸 중 4칸(doubt·last3·midweek·notes)이 프롬프트에만 있고
    저장되지 않았다. **U6 가 닫았고 이 테스트가 먼저 알려줬다** —
    "언젠가 되겠지" 대신 지금 몇 칸인지를 계약이 들고 있었기 때문이다.
    이제는 8칸 전부를 요구한다.
    """
    from app.collectors.satellite import fill_schema

    box = fill_schema({"out": ["A"]})
    missing = [f for f in H.FIELDS if f not in box]
    assert missing == [], missing
    assert box["out"] == ["A"]
    # 🔴 없는 칸은 None 이지 빈 값이 아니다 — "모른다"와 "없다"는 다르다
    assert box["doubt"] is None and box["doubt"] != []


def test_게이트_라벨을_베껴적지_않는다():
    src = inspect.getsource(H)
    for lit in ('"동의"', '"시장 과대"', '"가치 의심"', '"보드 고정"'):
        assert lit not in src, f"게이트 라벨을 손으로 적었다: {lit}"
    assert "from app.engine import gate" in src


def test_순수함수다_DB를_안_부른다():
    """🔴 반대 위험 — gate.py 와 같은 규칙이다."""
    src = inspect.getsource(H)
    for bad in ("asyncpg", "httpx", "get_pool", "redis", "await "):
        assert bad not in src, f"{bad} 를 쓴다"


def test_as_dict가_원장_모양이다():
    h = _b(G.DOUBT, gap_pp=12.0)
    d = h.as_dict()
    assert set(d) == {"direction", "need", "sufficient_count", "reason"}
    assert all(set(n) == {"field", "side", "why"} for n in d["need"])
    import json
    json.dumps(d, ensure_ascii=False)          # 직렬화가 되어야 원장에 든다


def test_원장_칸이_있다():
    src = pathlib.Path("db/schema.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS hypothesis JSONB" in src


def test_배선돼_있다():
    """🔴 만들고 안 부르면 원장은 영원히 NULL 이다."""
    from app.engine import pick_ledger as PL

    src = inspect.getsource(PL.record_prior)
    assert "hypothesis as HY" in src and "HY.build(" in src
    assert "SET hypothesis" in src, "기록하지 않는다"
    assert "is_big_match" in src, "빅매치를 안 본다(문턱이 늘 2가 된다)"
