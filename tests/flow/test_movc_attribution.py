"""[MOV-C 3·4·5단계] 이동의 원인을 시각으로 맞춘다. **"이유 미상"은 없다.**

사용자 2026-09-23: **"이유 미상은 없다"** · "배당률 분석은 **초기부터**
분석이 이루어져야 한다" · "왜 이렇게 배당이 이동되었는지…초기 가설과 접목"

🔴 **`none` 을 만들지 않는다.** 대신 셋으로 가른다:
```
news        창 안에 관측된 변화·기사가 있다   → 근거를 적는다
money       관측은 있었는데 창 안에 없었다    → 자금 이동. 회피가 아닌 답
unobserved  관측 자체가 없었다               → 자금이라 부를 수 없다
```
⚠️ 셋째가 핵심이다. MOV-T7 커밋이 남긴 자백 — `"뉴스 근거 없음(딥서치
   **미실행** 또는 무소득)"` — 을 반복하지 않으려면 "안 찾아봤다"와
   "찾아봤는데 없다"를 **구분해야** 한다.

⚠️ 창 폭 30분은 **실측으로 정했다**(2026-09-22~23, 2%p 이상 이동):
   ±15분 33.3% · ±30분 46.7% · ±60분 46.7% → 넓혀도 더 안 잡힌다.
"""
from __future__ import annotations

import ast
import datetime as dt
import inspect

import pytest

from app.flow import attribution as A

T = dt.datetime(2026, 9, 23, 9, 0, tzinfo=dt.UTC)


def _p(mins, prob):
    return (T + dt.timedelta(minutes=mins), prob)


#: 09:00 50% → 09:40 44%  (−6%p)
_PTS = [_p(0, 0.50), _p(40, 0.44)]


def _chg(mins, field="lineup_home", to="도회-마키-츠츠고", frm=""):
    return {"at": (T + dt.timedelta(minutes=mins)).isoformat(),
            "game": "A@B", "field": field, "from": frm, "to": to, "kind": "changed"}


# ── 귀인 ────────────────────────────────────────────────────────────

def test_창_안의_변화를_원인으로_붙인다():
    bag = A.explain(_PTS, [_chg(20)])
    assert len(bag["moves"]) == 1
    m = bag["moves"][0]
    assert m["pp"] == -6.0 and m["kind"] == A.NEWS
    assert "lineup_home" in m["causes"][0]


def test_창_밖이면_자금이다():
    """🔴 관측은 있었는데 창 안에 없었다 — **자금**이다. 미상이 아니다."""
    bag = A.explain(_PTS, [_chg(400)])
    assert bag["moves"][0]["kind"] == A.MONEY
    assert bag["observed"] is True
    assert bag["unexplained_pp"] == 6.0


def test_관측이_없으면_자금이라_부르지_않는다():
    """🔴 **이 계약이 이 단위의 핵심이다.** 찾아보지도 않고 자금이라 하면
    `none` 에 이름만 바꾼 것이다(MOV-T7 이 남긴 자백)."""
    bag = A.explain(_PTS, [])
    assert bag["moves"][0]["kind"] == A.UNOBSERVED
    assert bag["observed"] is False
    assert A.MONEY != A.UNOBSERVED


def test_회_진행은_원인이_아니다():
    """⚠️ 실측: 크롤러 변화 154건 중 **83건이 status**(9회초 → 9회말)였다."""
    bag = A.explain(_PTS, [_chg(20, field="status", frm="3회초", to="3회말")])
    assert bag["moves"][0]["kind"] == A.UNOBSERVED, "중계를 원인으로 셌다"


def test_역행은_사건이_아니다():
    bag = A.explain(_PTS, [_chg(20, field="starter_status", frm="확정", to="미상")])
    assert bag["moves"][0]["kind"] == A.UNOBSERVED


def test_기사는_발행시각을_쓴다():
    """🔴 크롤 시각이 아니라 **기사 자체의 시각**이다. `news.go` 가 값에
    `<RFC3339>|<제목>` 으로 실어 보낸다 — 20분마다 긁으므로 크롤 시각을
    쓰면 최대 20분이 어긋난다."""
    pub = (T + dt.timedelta(minutes=20)).isoformat()
    c = {"at": (T + dt.timedelta(minutes=400)).isoformat(), "game": "A@B",
         "field": "abc123", "from": "", "to": f"{pub}|문동주 선발 제외", "kind": "added"}
    bag = A.explain(_PTS, [c])
    assert bag["moves"][0]["kind"] == A.NEWS, "크롤 시각을 썼다"
    assert "문동주" in bag["moves"][0]["causes"][0]


def test_문턱_미만은_이동으로_세지_않는다():
    assert A.explain([_p(0, 0.50), _p(40, 0.503)], [_chg(20)])["moves"] == []


def test_못_읽는_시각에_터지지_않는다():
    for bad in ("", "어제", None, 123):
        assert A.explain([(bad, 0.5), _p(40, 0.44)], [_chg(20)])["moves"] == []
    assert A.explain(None, None)["moves"] == []
    assert A.explain([], [{"at": "x"}])["observed"] is False


def test_요약은_없는_말을_만들지_않는다():
    assert A.summary({"moves": []}) == ""
    assert A.summary({}) == "" and A.summary(None) == ""
    assert "자금" in A.summary(A.explain(_PTS, [_chg(400)]))


def test_창과_목록이_config_에_있다():
    from app.flow import rules as R

    assert float(R.get("move.window_min")) == 30.0
    assert "status" in [str(x) for x in R.get("move.ignore_fields")]
    src = inspect.getsource(A)
    for banned in ('"status"', "'status'", '"확정→미상"'):
        assert banned not in src, f"이름을 손으로 적었다: {banned}"


def test_순수_함수다():
    """🔴 DB·HTTP·LLM 0건 — `hypothesis.py` 와 같은 규약."""
    tree = ast.parse(inspect.getsource(A))
    calls = {getattr(c.func, "id", "") or getattr(c.func, "attr", "")
             for c in ast.walk(tree) if isinstance(c, ast.Call)}
    for banned in ("fetch", "execute", "complete_json", "ask_json", "post", "get_pool"):
        assert banned not in calls, banned


# ── ② 배선 ─────────────────────────────────────────────────────────

class _Ctx:
    def __init__(self, changes=None, rows=None):
        self.inject = {"changes": changes or [], "odds_rows": rows or []}
        self.pool = None
        self.redis = None


class _S:
    game_id = "1"
    sport = "baseball"
    league = "KBO"
    home = "HOME"
    away = "AWAY"
    kickoff_utc = "2026-09-23T09:30:00+00:00"
    n01_prior = {"p_home": 0.55, "p_away": 0.45}
    n02_market = None


def _row(mins, side, odds):
    return {"market": "h2h", "side": side, "odds": odds, "line": None,
            "snap_tag": None, "provider": "p",
            "captured_at": T + dt.timedelta(minutes=mins)}


# 🔴 마진이 있는 호가여야 한다. 처음 쓴 `2.27/1.79` 는 합 0.9992 라
#    ODD-S 게이트가 **옳게** 버렸다 — 운영이 만들 수 없는 값이었다.
#    개장 1.95/1.95 = 홈 50.0% → 40분 뒤 2.20/1.72 = 홈 43.9%
_ROWS = [_row(0, "HOME", 1.95), _row(0, "AWAY", 1.95),
         _row(40, "HOME", 2.20), _row(40, "AWAY", 1.72)]


@pytest.mark.asyncio
async def test_2가_원인을_싣는다():
    from app.flow.nodes import n02_market as N2

    s = await N2.run(_S(), _Ctx(changes=[_chg(20)], rows=_ROWS))
    mv = s.n02_market["move"]
    assert mv["causes"]["moves"][0]["kind"] == A.NEWS


@pytest.mark.asyncio
async def test_개장가와_우리_사전값의_괴리를_낸다():
    """🔴 사용자: "배당률 분석은 **초기부터**". ③은 현재 시장과만 비교한다 —
    개장과도 비교해야 "처음부터 달랐나 / 움직여서 달라졌나"가 갈린다."""
    from app.flow.nodes import n02_market as N2

    s = await N2.run(_S(), _Ctx(rows=_ROWS))
    mv = s.n02_market["move"]
    assert mv["open_home"] == 0.5
    assert mv["open_gap_pp"] == -5.0      # 개장 50% − 사전값 55%


@pytest.mark.asyncio
async def test_사전값이_없으면_괴리를_지어내지_않는다():
    from app.flow.nodes import n02_market as N2

    s = _S()
    s.n01_prior = None
    out = await N2.run(s, _Ctx(rows=_ROWS))
    assert out.n02_market["move"]["open_gap_pp"] is None


@pytest.mark.asyncio
async def test_한_벌뿐이면_원인을_묻지_않는다():
    from app.flow.nodes import n02_market as N2

    s = await N2.run(_S(), _Ctx(rows=_ROWS[:2]))
    assert s.n02_market["move"]["causes"] is None


def test_2가_흐름_밖의_변화를_읽는다():
    """🔴 배선의 끝 — 흐름은 지금까지 `crawler_feed` 를 한 번도 안 읽었다."""
    from app.flow.nodes import n02_market as N2

    src = inspect.getsource(N2._changes)
    assert "load_changes" in src
    assert "news_" in src, "뉴스 변화를 안 읽는다"


# ── ④ 접목 ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_4가_이유를_적는다():
    from app.flow.nodes import n04_hyp as N4

    class _S4(_S):
        hyp_side = "home"
        pick_side = "home"
        n03_gate = {"gate": "동의"}
        n04_hyp = None
        n02_market = {
            "p": {"home": 0.44, "draw": None, "away": 0.56},
            "move": {"move_pp": -6.0, "open_home": 0.50, "now_home": 0.44,
                     "n_snaps": 2,
                     "causes": A.explain(_PTS, [_chg(20)])}}

    class _C:
        inject = {}
        pool = None

    s = _S4()
    s.league = "MLB"
    out = await N4.run(s, _C())
    why = out.n04_hyp[0]["why"]
    assert "이동" in why and "lineup_home" in why, why
    assert "미상" not in why, why


# ── 실데이터가 잡은 것 ──────────────────────────────────────────────

def test_쪽마다_시각이_어긋나도_한_벌로_묶는다():
    """🔴 **실데이터로 돌려 보고서야 알았다.** 적재가 쪽마다 따로 INSERT 해서
    같은 벌의 `captured_at` 이 마이크로초로 어긋난다:
    ```
    15:13:42.665749  home 1.95
    15:13:42.672699  away 1.95
    ```
    정확히 같은 값으로 묶으면 전 벌이 반쪽이 되어 **이동이 조용히 0** 이 된다
    (실측: 운영 9경기 전건 `n_snaps=0`). 단위 계약이 두 쪽에 **같은** 시각을
    주는 바람에 통과했었다 — 거짓 픽스처다.
    """
    import datetime as _dt

    from app.flow.nodes import n02_market as N2

    def r(sec_us, side, odds):
        return {"market": "h2h", "side": side, "odds": odds, "line": None,
                "captured_at": T + _dt.timedelta(seconds=sec_us)}

    rows = [r(0.665749, "HOME", 1.95), r(0.672699, "AWAY", 1.95),
            r(2400.11, "HOME", 2.20), r(2400.19, "AWAY", 1.72)]
    pts = N2._sets(rows, "HOME", "AWAY")
    assert len(pts) == 2, f"쪽마다 시각이 어긋나 반쪽이 됐다: {pts}"
    assert pts[0][1] == 0.5


def test_한_분에_두_벌이_오면_버린다():
    """🔴 **실데이터가 잡은 두 번째 결함.** 같은 분에 서로 반대인 두 벌이
    들어온다 — 둘 다 마진이 정상이고 `snap_tag` 도 같아 가릴 수 없다:
    ```
    g1774 15:13:42  한화 1.65 / 롯데 2.20   마진 1.061 (한화 우세)
          15:13:42  한화 2.10 / 롯데 1.74   마진 1.051 (롯데 우세)
    ```
    아무 쪽이나 고르면 다음 분에 반대 벌이 뽑혀 **±12%p 가짜 이동**이 생긴다.
    실측: 그렇게 뽑힌 g1774 는 "자금 7구간 · 설명 못한 폭 84%p" 였고,
    버리게 고치니 "근거 있음 1구간 · 설명 못한 폭 0%p" 가 됐다.
    ⚠️ 고르지 않고 **버린다.** 모르는 것을 골라 쓰면 곧 거짓 귀인이 되고,
       "이유 미상은 없다"가 거짓말이 된다.
    """
    import datetime as _dt

    from app.flow.nodes import n02_market as N2

    def r(sec, side, odds):
        return {"market": "h2h", "side": side, "odds": odds, "line": None,
                "captured_at": T + _dt.timedelta(seconds=sec)}

    rows = [r(0.63, "HOME", 1.65), r(0.64, "AWAY", 2.20),
            r(0.68, "HOME", 2.10), r(0.69, "AWAY", 1.74),
            r(2400.1, "HOME", 2.20), r(2400.2, "AWAY", 1.72)]
    pts = N2._sets(rows, "HOME", "AWAY")
    assert len(pts) == 1, f"모호한 분을 골라 썼다: {pts}"


def test_같은_값이_두_번_와도_모호가_아니다():
    """⚠️ 반대 위험 — 중복 INSERT 는 모호가 아니다. 버리면 정상 자료를
    잃는다."""
    import datetime as _dt

    from app.flow.nodes import n02_market as N2

    def r(sec, side, odds):
        return {"market": "h2h", "side": side, "odds": odds, "line": None,
                "captured_at": T + _dt.timedelta(seconds=sec)}

    rows = [r(0.1, "HOME", 1.95), r(0.2, "AWAY", 1.95),
            r(0.3, "HOME", 1.95), r(0.4, "AWAY", 1.95)]
    assert len(N2._sets(rows, "HOME", "AWAY")) == 1
