"""[VAL-1] ⑪이 **북의 라인에서 확률을 안 낸다** — 그래서 후보가 0이었다.

사용자 2026-09-23: "11번 풀어라"

🔴 실측 (운영, 오늘 MLB 8경기):
```
경기                     북 라인      모델이 낸 라인        일치
St.Louis@Pittsburgh        7.0   [9.5, 10.5, 11.5]      X
Milwaukee@Philadelphia     7.0   [8.5,  9.5, 10.5]      X
Washington@Detroit         8.5   [6.5,  7.5,  8.5]      O
Cleveland@Boston           6.0   [5.5,  6.5,  7.5]      X
Chicago WS@Kansas City     8.0   [9.5, 10.5, 11.5]      X
→ 라인 일치 3/8
```
⑪의 `_structure_candidates` 는 **북 라인의 우리 확률**을 찾는다:
```python
line   = book.get("line")            # 북이 건 라인
p_ours = ours.get(f"{name}_{side}").get(line)
if p_ours is None: continue          # 없으면 후보에서 빠진다
```
없으면 `지정 마켓 total 후보 0` 이다 — 실측 분포에서 **8건**이 그 사유였다.

🔴 `mlb_market_probs` 에는 `lines` 인자가 **이미 있다.** 안 넘겨서 λ 기준
   기본 3개만 냈을 뿐이다:
```python
for line in (lines or {}).get("totals", []) or _default_total_lines(lam_home + lam_away):
```

⚠️ **배당(가격)을 확률에 넣는 것이 아니다.** 넘기는 것은 "어느 **라인**에서
   평가할지"(숫자)뿐이고, 확률은 그대로 λ 포아송에서 나온다. `p_code`(승패)는
   한 줄도 바뀌지 않는다 — 계약이 그것을 잠근다.
"""
from __future__ import annotations

import inspect

import pytest

from app.flow import bridge as B

ODDS = [
    {"market": "totals", "side": "Over", "line": 7.0, "odds": 1.9},
    {"market": "totals", "side": "Under", "line": 7.0, "odds": 1.9},
    {"market": "spreads", "side": "Home -1.5", "line": 1.5, "odds": 2.4},
    {"market": "team_totals", "side": "Home Over", "line": 4.5, "odds": 1.95},
]


def test_라인추출기가_있다():
    assert hasattr(B, "book_lines")


def test_북_라인을_모은다():
    got = B.book_lines(ODDS, home="H", away="A")
    assert got["totals"] == [7.0], got
    assert 1.5 in got["spreads"], got
    assert 4.5 in got["team_totals"], got


def test_라인이_없으면_빈_dict():
    """🔴 빈 값을 넘기면 `mlb_market_probs` 가 기본 라인으로 돌아간다 —
    지어내지 않고 종전과 같아진다."""
    assert B.book_lines([], home="H", away="A") == {}


def test_규칙을_새로_짓지_않았다():
    """🔴 라인 추출은 `n02_market._derivatives` 가 원본이다(사본 금지)."""
    src = inspect.getsource(B.book_lines)
    assert "_derivatives" in src


def test_model_probs_가_라인을_받는다():
    """🔴 배선의 끝 — 안 넘기면 북 라인의 확률이 영영 안 생긴다."""
    sig = inspect.signature(B.model_probs_from_cache)
    assert "lines" in sig.parameters
    # 사슬대로 본다: run_slate → lines_by_game → book_lines
    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(B.run_slate).splitlines())
    assert "lines_by_game(" in src, "슬레이트가 라인을 안 모은다"
    assert "lines=" in src, "model_probs_from_cache 에 라인을 안 넘긴다"
    assert "book_lines(" in inspect.getsource(B.lines_by_game)


def test_북_라인의_확률이_생긴다():
    """🔴 이 단위의 전부 — 7.0 은 기본 라인 집합에 **없는** 값이다."""
    from app.engine.scoring import mlb_market_probs

    mp = mlb_market_probs(4.2, 3.9, lines={"totals": [7.0]})
    assert 7.0 in mp["totals"], sorted(mp["totals"])
    assert 0.0 < mp["totals"][7.0]["Over"] < 1.0


def test_승패_확률은_안_바뀐다():
    """🔴 **배당을 확률에 넣는 것이 아니다.** 라인은 "어디서 평가할지"일 뿐
    이고 `h2h` 는 λ 에서만 나온다 — 라인을 줘도 그대로여야 한다."""
    from app.engine.scoring import mlb_market_probs

    a = mlb_market_probs(4.2, 3.9)
    b = mlb_market_probs(4.2, 3.9, lines={"totals": [7.0], "spreads": [2.5]})
    assert a["h2h"] == b["h2h"]
    assert a["lambda"] == b["lambda"]


@pytest.mark.asyncio
async def test_한_경기가_실패해도_나머지가_산다():
    class _Boom:
        async def fetch(self, *a, **k):
            raise RuntimeError("DB")

    got = await B.lines_by_game(_Boom(), [1, 2])
    assert got == {}


@pytest.mark.asyncio
async def test_경기별로_한_번에_읽는다():
    """⚠️ 경기마다 질의하면 슬레이트에서 N배가 된다."""
    seen = []

    class _P:
        async def fetch(self, sql, *a):
            seen.append((sql, a))
            return [{"game_id": 1, "market": "totals", "side": "Over",
                     "line": 7.0, "odds": 1.9}]

    out = await B.lines_by_game(_P(), [1, 2, 3])
    assert len(seen) == 1, f"질의가 {len(seen)}번 나갔다"
    assert out.get(1, {}).get("totals") == [7.0], out
