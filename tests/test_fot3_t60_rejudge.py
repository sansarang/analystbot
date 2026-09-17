"""FOT-3 계약 — T-60 **확정 XI 가 판정으로 돌아간다** (PART A 표 S10).

🔴 `_lineup_recheck` 는 `fotmob.diff_xi` 로 차이를 만들어 **game_trace 에 적고
   끝났다.** 확정 라인업이 예상과 달라도 p_code 도 등급도 그대로였다.
⚠️ PA-27 은 **딥서치 경로**를 이었다. 여기는 **공식 XI 경로**이고,
   docs/FORKS.md F-2 의 권한표에서 `주전결장` 을 **대체할 수 있는 유일한
   출처**다 — 정작 그쪽이 안 이어져 있었다.
🔴 이 경로는 딥서치와 달리 **선수 시장가치가 있다**(fotmob.parse_lineup).
"""
import inspect
import json

import pytest

from app import scheduler as S
from app.engine import pick_ledger as PL
from app.engine import rejudge as RJ


def _got(diff=None, *, lineup="confirmed", home_total=1100, away_total=550):
    return {
        "lineup_type": lineup,
        "home": {"total_market_value": home_total,
                 "starters": [{"id": i, "name": f"H{i}", "market_value": 100}
                              for i in range(1, 12)]},
        "away": {"total_market_value": away_total,
                 "starters": [{"id": 100 + i, "name": f"A{i}",
                               "market_value": 50} for i in range(1, 12)]},
        **({"diff": diff} if diff else {}),
    }


OUT2 = {"home": {"bench_notable": ["H1", "H2"], "surprise_in": []}}


_DEFAULT_ROW = {"p_code": 0.62, "adj_pp": {"주전결장": -1.5, "짧은휴식": -2.0},
                "confidence": "중"}
_KEEP = object()          # ⚠️ None 이 "기본값"으로 덮이면 계약이 헛돈다


class _Pool:
    def __init__(self, row=_KEEP):
        self.row = dict(_DEFAULT_ROW) if row is _KEEP else row
        self.saved = []

    async def fetchrow(self, sql, *a):
        return self.row

    async def execute(self, sql, *a):
        self.saved.append(a)


# ── 🔴 팀별 총가치 환산

def test_원정_가치가_팀_총액_차이만큼_환산된다():
    """🔴 `importance` 분모는 **자기 팀** 총가치인데 `reweigh` 는 하나만 받는다.
    안 환산하면 총액이 절반인 팀의 선수가 절반으로 세어진다."""
    box, ref = S._xi_players(_got())
    assert ref == 1100.0
    assert box["H1"]["market_value"] == 100.0
    assert box["A1"]["market_value"] == 100.0        # 50 × (1100/550)


def test_총가치가_없으면_환산하지_않는다():
    """🔴 없는 값을 지어내지 않는다."""
    box, ref = S._xi_players(_got(home_total=None, away_total=None))
    assert ref is None
    assert box["A1"]["market_value"] == 50


def test_이름이_없는_선수는_건너뛴다():
    g = _got()
    g["home"]["starters"].append({"id": 999, "market_value": 1})
    assert None not in S._xi_players(g)[0]


# ── 재판정

@pytest.mark.asyncio
async def test_확정_XI가_원장에_되먹임된다():
    pool = _Pool()
    assert await S._rejudge_from_xi(pool, 1, _got(OUT2)) is True
    (gid, adj, p, grade, by) = pool.saved[-1]
    assert gid == 1
    assert "라인업결장:home" in json.loads(adj)
    assert p is not None and grade is not None


@pytest.mark.asyncio
async def test_출처가_official_xi다():
    """🔴 딥서치 행과 갈려야 나중에 어느 쪽이 맞았는지 잰다."""
    pool = _Pool()
    await S._rejudge_from_xi(pool, 1, _got(OUT2))
    assert pool.saved[-1][4] == RJ.SRC_OFFICIAL == "official_xi"


@pytest.mark.asyncio
async def test_공식_XI는_주전결장을_대체한다():
    """🔴 이 경로만 대체 권한이 있다(FORKS F-2)."""
    pool = _Pool()
    await S._rejudge_from_xi(pool, 1, _got(OUT2))
    adj = json.loads(pool.saved[-1][1])
    assert "주전결장" not in adj
    assert adj["짧은휴식"] == -2.0          # 무관한 축은 보존


@pytest.mark.asyncio
async def test_되짚기가_원본_adj를_쓴다():
    """🔴 PA-27-c — 대체된 축을 두 번 빼면 안 된다. 실측 0.6125."""
    pool = _Pool()
    await S._rejudge_from_xi(pool, 1, _got(OUT2))
    assert pool.saved[-1][2] == pytest.approx(0.6125, abs=1e-6)


# ── 🔴 반대 위험

@pytest.mark.asyncio
async def test_diff가_없으면_아무것도_안_한다():
    pool = _Pool()
    assert await S._rejudge_from_xi(pool, 1, _got()) is False
    assert not pool.saved


@pytest.mark.asyncio
async def test_원장_판정이_없으면_안_쓴다():
    """🔴 판정 전이면 되짚을 p_code 가 없다."""
    for row in (None, {"p_code": None, "adj_pp": {}, "confidence": None}):
        pool = _Pool(row=row)
        assert await S._rejudge_from_xi(pool, 1, _got(OUT2)) is False
        assert not pool.saved


@pytest.mark.asyncio
async def test_변화가_없으면_안_쓴다():
    """🔴 안 바뀐 것을 쓰면 '그대로'와 '재판정 안 함'이 같아진다."""
    pool = _Pool()
    empty = {"home": {"bench_notable": [], "surprise_in": []}}
    assert await S._rejudge_from_xi(pool, 1, _got(empty)) is False
    assert not pool.saved


def test_실패해도_트리거를_안_막는다():
    """🔴 곁가지가 본선을 멈추지 않는다 — CLV·이동과 같은 규약."""
    src = inspect.getsource(S._lineup_recheck)
    after = src.split("_rejudge_from_xi", 1)[1]
    assert "except Exception" in after.split("finally:", 1)[0]


# ── 사본 금지 · 저장 전용

def test_저장_SQL이_한_곳에서만_쓰인다():
    """🔴 경로가 둘이라 각자 SQL 을 들면 곧 사본이 된다.

    ⚠️ 글자 수를 세지 않는다 — 머리말에 "이 SQL 을 쓰는 곳은 하나뿐"이라고
       적은 문장까지 세어져 처음에 3 이 나왔다(PA-27-a·PA-28·RPT-1 에 이어
       **네 번째** 같은 함정이다). **어느 함수가 쓰는가**를 본다.
    """
    users = [n for n, fn in vars(PL).items()
             if callable(fn) and getattr(fn, "__module__", "") == PL.__name__
             and "_REJUDGE_SAVE" in (inspect.getsource(fn)
                                     if inspect.isfunction(fn) else "")]
    assert users == ["record_rejudge"], users
    assert "_REJUDGE_SAVE" not in inspect.getsource(
        PL.record_confirm_and_analysis)


def test_원래_칸을_안_덮는다():
    setc = PL._REJUDGE_SAVE.split("SET", 1)[1].split("WHERE", 1)[0]
    for bad in ("p_code =", "confidence =", "adj_pp ="):
        assert bad not in setc, bad


def test_발송을_켜지_않는다():
    src = inspect.getsource(S._rejudge_from_xi) + inspect.getsource(S._xi_players)
    for bad in ("send", "dispatch", "telegram"):
        assert bad not in src.lower(), bad


def test_야구_경로를_안_건드린다():
    """🔴 축구 XI diff 와 야구 선발 교체는 다른 것이다(rejudge 머리말)."""
    src = inspect.getsource(S._rejudge_from_xi)
    assert 'sport="soccer"' in src
    assert "starter_changed" not in src


@pytest.mark.asyncio
async def test_가치를_안다는_사실이_남는다():
    """🔴 F-3 — 딥서치는 0/n 인데 여기는 n/n 이어야 한다."""
    pool = _Pool()
    await S._rejudge_from_xi(pool, 1, _got(OUT2))
    rj = RJ.reweigh(adj={}, p_code=0.62, diff=OUT2,
                    players=S._xi_players(_got())[0],
                    team_total_value=1100.0, grade="중",
                    source=RJ.SRC_OFFICIAL)
    assert rj["value_coverage"] == {"known": 2, "total": 2}
