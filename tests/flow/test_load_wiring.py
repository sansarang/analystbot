"""[LOAD-1] 일정 부하·출전 부하를 ⑤에 **잇는다.** 주전/후보로 무게를 나눈다.

사용자 2026-09-23: "출전부하도 배선에 넣어라...그리고 이것은 **후배선수인지
메인선수인지 확인해서 숫자를 바꿔야 한다**"

🔴 **둘 다 "만들어 놓고 안 이은" 자리다:**
```
travel_backtoback  n05_evidence.py 에 이름이 **0번** 나온다 → 기본 경로로
                   떨어져 "수집 경로가 없다 — 미실행". 🔴 그런데 바로 옆
                   `_recent_match()` 가 축구 rotation_risk 에 쓰이고 있다
play_load          batter_appearances 19,025행(9월 mlb 279·npb 98·kbo 81)을
                   흐름이 **한 번도 안 읽는다**
```

⚠️ **축구는 못 한다** — `lineup_history.minutes` 가 전 리그 **0건**이고
   날짜가 08-22~08-29 8일치뿐이다(9월 0경기). 야구만 잇는다.

🔴 **주전 판정의 원본은 `lineup_diff.usual_from` 하나다**(사본 금지) —
   최근 10경기 중 절반 이상 나온 선수가 `regulars`, 최빈 타순이 `slots`.
   `flow/direction.py` 가 이미 그것을 쓴다.
"""
from __future__ import annotations

import datetime as dt
import inspect

import pytest

from app.flow import load as L

KICK = dt.datetime(2026, 9, 23, 9, 30, tzinfo=dt.UTC)


# ── 주전/후보 가중 ──────────────────────────────────────────────────

def test_주전과_후보의_무게가_다르다():
    """🔴 사용자 지시의 핵심 — "후배선수인지 메인선수인지 확인해서 숫자를 바꿔야"."""
    usual = {"slots": {"a": 2, "b": 9}, "regulars": {"a"}, "games": 10}
    w_main = L.player_weight("a", usual)
    w_sub = L.player_weight("b", usual)
    assert w_main > w_sub > 0, (w_main, w_sub)


def test_상위타순이_더_무겁다():
    usual = {"slots": {"a": 2, "b": 7}, "regulars": {"a", "b"}, "games": 10}
    assert L.player_weight("a", usual) > L.player_weight("b", usual)


def test_모르는_선수는_무게가_없다():
    """🔴 지어내지 않는다 — 평소 타순을 모르면 0 이다."""
    usual = {"slots": {"a": 2}, "regulars": {"a"}, "games": 10}
    assert L.player_weight("zzz", usual) == 0.0
    assert L.player_weight("a", {}) == 0.0
    assert L.player_weight("", usual) == 0.0


def test_주전_판정을_다시_짓지_않았다():
    """🔴 사본 금지 — `lineup_diff.usual_from` 이 원본이다."""
    src = inspect.getsource(L)
    assert "usual_from" in src, "원본을 안 쓴다"
    for banned in ("regulars =", "def usual_", "c * 2 >= n"):
        assert banned not in src, f"주전 판정을 다시 짰다: {banned}"


def test_가중치가_config_에_있다():
    from app.flow import rules as R

    assert float(R.get("load.weight_regular", 0)) > 0
    assert float(R.get("load.weight_sub", 0)) >= 0
    src = inspect.getsource(L.player_weight)
    assert "R.get(" in src, "가중치를 손으로 적었다"


# ── 출전 부하 ───────────────────────────────────────────────────────

def _app(days_ago, batter, slot):
    return {"batter": batter, "slot": slot,
            "starts_at": KICK - dt.timedelta(days=days_ago)}


def test_최근_연속출장이_부하다():
    """가중을 실은 출장 수가 부하다 — 후보가 많이 나온 것과 주전이 많이 나온
    것은 다르다."""
    usual = {"slots": {"a": 2, "b": 9}, "regulars": {"a"}, "games": 10}
    heavy = L.play_load([_app(i, "a", 2) for i in range(1, 6)], usual)
    light = L.play_load([_app(i, "b", 9) for i in range(1, 6)], usual)
    assert heavy["score"] > light["score"] > 0
    assert heavy["n"] == 5


def test_창_밖_출장은_안_센다():
    """⚠️ 기준 시각은 **킥오프**다. ⑤가 그것을 넘긴다 — 안 넘기면 마지막
    출장이 기준이 되어 창이 의미를 잃는다."""
    usual = {"slots": {"a": 2}, "regulars": {"a"}, "games": 10}
    assert L.play_load([_app(30, "a", 2)], usual, at=KICK)["n"] == 0
    assert L.play_load([_app(2, "a", 2)], usual, at=KICK)["n"] == 1


def test_자료가_없으면_None():
    """🔴 0 과 모름은 다르다 — ⑤가 `미실행` 으로 적을 수 있어야 한다."""
    assert L.play_load(None, {}) is None
    assert L.play_load([], {}) is None


# ── ⑤ 배선 ─────────────────────────────────────────────────────────

class _Ctx:
    inject: dict = {}
    pool = None
    redis = None

    def __init__(self, **kw):
        self.inject = dict(kw)


def _state(vars_):
    from app.flow.state import State

    s = State(run_id="r", game_id="1", sport="baseball", league="KBO",
              home="Doosan Bears", away="Kia Tigers",
              kickoff_utc=KICK.isoformat())
    s.hyp_side = s.pick_side = "home"
    s.n01_prior = {"p_home": 0.52, "p_away": 0.48}
    s.n02_market = {"p": {"home": 0.5, "draw": None, "away": 0.5}, "move": {}}
    s.n04_hyp = [{"id": "H", "vars": [{"var": v, "is_core": False} for v in vars_]}]
    return s


@pytest.mark.asyncio
async def test_5가_연전을_센다():
    """🔴 `_recent_match` 가 이미 있는데 야구가 안 불렀다."""
    from app.flow.nodes import n05_evidence as N5

    s = await N5.run(_state(["travel_backtoback"]),
                     _Ctx(recent_match={"home": ["09-22 vs LG"], "away": []}))
    row = next(e for e in s.n05_evidence if e["var"] == "travel_backtoback")
    assert row["status"] == "", row
    assert row["direction"]["home"] == -1, row


@pytest.mark.asyncio
async def test_연전_자료를_못_보면_미실행이다():
    from app.flow.nodes import n05_evidence as N5

    s = await N5.run(_state(["travel_backtoback"]), _Ctx())
    row = next(e for e in s.n05_evidence if e["var"] == "travel_backtoback")
    assert row["status"] == "미실행", row


@pytest.mark.asyncio
async def test_5가_출전부하를_싣는다():
    from app.flow.nodes import n05_evidence as N5

    usual = {"slots": {"a": 2}, "regulars": {"a"}, "games": 10}
    s = await N5.run(_state(["play_load"]),
                     _Ctx(play_load={"home": {"apps": [_app(i, "a", 2) for i in range(1, 6)],
                                              "usual": usual},
                                     "away": {"apps": [], "usual": usual}}))
    row = next(e for e in s.n05_evidence if e["var"] == "play_load")
    assert row["status"] == "", row
    assert row["direction"]["home"] == -1, row


@pytest.mark.asyncio
async def test_출전부하_자료가_없으면_미실행이다():
    from app.flow.nodes import n05_evidence as N5

    s = await N5.run(_state(["play_load"]), _Ctx())
    row = next(e for e in s.n05_evidence if e["var"] == "play_load")
    assert row["status"] == "미실행", row


def test_변수표에_둘_다_있다():
    """🔴 배선의 끝 — 변수표에 없으면 ④⑥⑦이 영영 안 집는다."""
    from app.flow import rules as R

    b = R.vars_for("baseball")
    assert "travel_backtoback" in b
    assert "play_load" in b, "출전부하 변수가 없다"
    assert b["play_load"]["core"] is False
    # ⚠️ 축구는 자료가 없어 넣지 않았다(lineup_history.minutes 전건 0)
    assert "play_load" not in R.vars_for("soccer")


def test_야구_연전_창이_따로_있다():
    """⚠️ 축구 96h 를 그대로 쓰지 않는다 — 야구는 매일 경기다."""
    from app.flow import rules as R

    h = float(R.get("load.b2b_window_h", 0))
    assert 0 < h <= 48, h


# ── 오늘 선발이냐 ───────────────────────────────────────────────────

def test_오늘_안_나오는_선수의_피로는_안_센다():
    """🔴 **사용자 지시 2026-09-23** — "그날 경기에 그 선수가 선발이냐도
    예측에 적용되어야 한다".

    많이 뛴 선수가 오늘 빠지면 그 피로는 이 경기에 들어오지 않는다.
    그건 `lineup_out` 이 보는 **다른 사실**이다(전력 약화).
    """
    usual = {"slots": {"a": 2, "b": 3}, "regulars": {"a", "b"}, "games": 10}
    apps = [_app(i, "a", 2) for i in range(1, 6)] + \
           [_app(i, "b", 3) for i in range(1, 6)]
    both = L.play_load(apps, usual, at=KICK)
    only_a = L.play_load(apps, usual, today=["a"], at=KICK)
    assert only_a["n"] == 5 and both["n"] == 10
    assert only_a["score"] < both["score"]
    assert only_a["scoped"] is True and both["scoped"] is False


def test_타순이_미확정이면_전부_센다():
    """⚠️ 확정 타순이 없을 때 **0 으로 만들지 않는다** — 덜 정확할 뿐이다.
    `scoped=False` 로 그 사실을 남긴다."""
    usual = {"slots": {"a": 2}, "regulars": {"a"}, "games": 10}
    got = L.play_load([_app(1, "a", 2)], usual, today=None, at=KICK)
    assert got["n"] == 1 and got["scoped"] is False
    got2 = L.play_load([_app(1, "a", 2)], usual, today=[], at=KICK)
    assert got2["scoped"] is False, "빈 명단을 '아무도 안 나온다'로 읽었다"


def test_표기가_흔들려도_같은_선수로_본다():
    """⚠️ `canon_name` 이 원본이다 — 여기서 정규화를 다시 짓지 않는다.

    🔴 실측: `canon_name` 은 **공백·하이픈은 지우지만 대소문자는 구분**한다.
    ```
    'Kim Min-Su'  → 'KimMinSu'
    'Kim  Min-Su' → 'KimMinSu'     ← 같다
    'kim min-su'  → 'kimminsu'     ← **다르다**
    ```
    ⚠️ `usual`·`apps` 는 `batter_appearances`, `today` 는 `lineups` 에서
       온다 — **표기 출처가 다르다.** 대소문자가 어긋나면 부하가 조용히 0 이
       된다. 여기서 소문자화를 더하면 `canon_name` 을 다시 짓는 것이므로
       하지 않고, **BT-9 백테스트가 그 어긋남을 실측**한다.
    """
    from app.engine.lineup_diff import canon_name

    assert canon_name("Kim Min-Su") == canon_name("Kim  Min-Su")
    usual = {"slots": {canon_name("Kim Min-Su"): 2},
             "regulars": {canon_name("Kim Min-Su")}, "games": 10}
    a = [{"batter": "Kim Min-Su", "slot": 2, "starts_at": KICK - dt.timedelta(days=1)}]
    assert L.play_load(a, usual, today=["Kim  Min-Su"], at=KICK)["n"] == 1


@pytest.mark.asyncio
async def test_5가_오늘_타순을_넘긴다():
    """🔴 배선의 끝 — ⑤가 오늘 타순을 안 넘기면 위 규칙이 죽는다."""
    from app.flow.nodes import n05_evidence as N5

    usual = {"slots": {"a": 2, "b": 3}, "regulars": {"a", "b"}, "games": 10}
    apps = [_app(i, "a", 2) for i in range(1, 6)] + \
           [_app(i, "b", 3) for i in range(1, 6)]
    s = await N5.run(_state(["play_load"]),
                     _Ctx(play_load={"home": {"apps": apps, "usual": usual},
                                     "away": {"apps": [], "usual": usual}},
                          today_order={"home": ["a"], "away": []}))
    row = next(e for e in s.n05_evidence if e["var"] == "play_load")
    assert "5경기" in row["raw_excerpt"], row      # 10 이 아니라 5
    assert "10경기" not in row["raw_excerpt"], row


def test_오늘_타순_읽기가_최신_한벌만_본다():
    """⚠️ 같은 경기에 예상/확정이 둘 다 있을 수 있다. `captured_at DESC` 의
    첫 행이 최신이다."""
    from app.flow.nodes import n05_evidence as N5

    rows = [{"side": "home", "batting_order": ["new1", "new2"]},
            {"side": "home", "batting_order": ["old1"]},
            {"side": "away", "batting_order": '["a1"]'}]
    got = N5._order_by_side(rows)
    assert got["home"] == ["new1", "new2"]
    assert got["away"] == ["a1"], "JSON 문자열을 못 읽는다"
    assert N5._order_by_side([]) == {}
    assert N5._order_by_side([{"side": "home", "batting_order": None}]) == {}
