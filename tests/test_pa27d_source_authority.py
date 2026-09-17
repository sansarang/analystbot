"""PA-27-d 계약 — **대체는 완전한 출처만 한다** (docs/FORKS.md F-2 · F-3).

🔴 딥서치 자료(2026-09-17)가 가리키는 바:
     Most Trusted Source Wins   공식 팀시트 > 기사    → 주전결장이 이긴다
     Most Complete Wins         전체 집계 > 부분 명단  → 주전결장이 이긴다
     Profisee: "완전성 규칙은 오류 위험이 높다" · "**속성 단위로** 규칙을 짜라"

  공식 XI    완전 + 신뢰  → 대체할 수 있다
  기사 명단  부분        → **빈자리만 채운다. 남의 자리를 못 뺏는다**

🔴 F-3 — 값을 모르면 1.0(평균 주전)을 쓰는 것 자체는 자료가 지지한다(미측정
   프로는 대체선수가 아니라 리그 평균으로 본다). 그러나 panna #242 처럼
   **채워 넣은 값과 진짜 평균을 구별 못 하면** 나중에 표를 못 읽는다.
   그래서 계산은 안 바꾸고 **몇 명의 가치를 알았는지만** 남긴다.
"""
import pytest

from app.engine import rejudge as RJ

PLAYERS = {"A": {"market_value": 100}, "B": {"market_value": 100}}
TT = 1100
OUT2 = {"home": {"bench_notable": ["A", "B"], "surprise_in": []}}


def _run(**kw):
    kw.setdefault("adj", {"주전결장": -1.5})
    kw.setdefault("p_code", 0.55)
    kw.setdefault("diff", OUT2)
    kw.setdefault("players", PLAYERS)
    kw.setdefault("team_total_value", TT)
    kw.setdefault("grade", "중")
    return RJ.reweigh(**kw)


# ── 부분 출처(기사)

def test_기사는_주전결장을_못_뺏는다():
    g = _run(source=RJ.SRC_NEWS)
    assert g["adj_after"] == {"주전결장": -1.5}
    assert g.get("replaced_axis") is None


def test_기사는_주전결장_위에_얹지도_않는다():
    """🔴 얹으면 PA-27-b 가 고친 **이중 계산**이 되살아난다."""
    g = _run(source=RJ.SRC_NEWS)
    assert not any(k.startswith(RJ.KEY_OUT) for k in g["adj_after"])


def test_물러나면_확률이_안_움직인다():
    g = _run(source=RJ.SRC_NEWS)
    assert g["changed"] is False
    assert g["p_code_after"] == 0.55


def test_물러난_이유가_남는다():
    """🔴 "조용한 0"은 결함이다 — 왜 안 썼는지 말해야 한다."""
    g = _run(source=RJ.SRC_NEWS)
    assert g["yielded_to"] == RJ.KEY_BASE_OUT
    assert RJ.KEY_BASE_OUT in g["why"]
    assert any(k.startswith(RJ.KEY_OUT)
               for k in (g.get("adj_dropped_after") or {}))


def test_빈자리는_채운다():
    """🔴 반대 위험 — 물러나는 것은 **더 좋은 자료가 있을 때뿐**이다.
    축구 판정은 T-3h 라 주전결장이 없다 — 거기서는 기사가 유일한 신호다."""
    g = _run(source=RJ.SRC_NEWS, adj={})
    assert g["adj_after"] == {"라인업결장:home": -3.0}
    assert g["changed"] is True
    assert g["p_code_after"] < 0.55


def test_결장과_무관한_축은_그대로_간다():
    """🔴 반대 위험 — 물러나는 것은 **결장 축 하나**다."""
    g = _run(source=RJ.SRC_NEWS, adj={"주전결장": -1.5, "짧은휴식": -2.0})
    assert g["adj_after"]["짧은휴식"] == -2.0


def test_복귀는_물러나지_않는다():
    """🔴 대체 다툼은 결장끼리다. 복귀는 주전결장과 겹치지 않는다."""
    g = _run(source=RJ.SRC_NEWS,
             diff={"home": {"bench_notable": [], "surprise_in": ["A", "B"]}})
    assert any(k.startswith(RJ.KEY_IN) for k in g["adj_after"])
    assert g["adj_after"]["주전결장"] == -1.5


# ── 🔴 반대 위험 — 공식 XI 는 종전대로 대체한다 (F-1)

def test_공식_XI는_여전히_대체한다():
    g = _run(source=RJ.SRC_OFFICIAL)
    assert g["replaced_axis"] == RJ.KEY_BASE_OUT
    assert "주전결장" not in g["adj_after"]


def test_기본값이_공식_XI다():
    """🔴 부분 출처를 쓰는 쪽이 **그 사실을 밝히게** 한다."""
    assert _run()["replaced_axis"] == RJ.KEY_BASE_OUT


def test_대체_권한_목록이_공식_XI뿐이다():
    assert RJ.CAN_REPLACE == (RJ.SRC_OFFICIAL,)
    assert RJ.SRC_NEWS not in RJ.CAN_REPLACE


# ── F-3 · 가치 커버리지

def test_가치를_몇_명_알았는지_남는다():
    g = _run(source=RJ.SRC_NEWS, adj={})
    assert g["value_coverage"] == {"known": 2, "total": 2}


def test_모르면_모른다고_남는다():
    g = RJ.reweigh(adj={}, p_code=0.55, diff=OUT2, players={},
                   team_total_value=None, grade="중", source=RJ.SRC_NEWS)
    assert g["value_coverage"] == {"known": 0, "total": 2}
    assert "0/2" in g["why"]


def test_커버리지가_계산을_안_바꾼다():
    """🔴 F-3 은 **기록만** 한다 — 값을 모른다고 벌점을 주지 않는다.
    자료: 미측정 프로는 대체선수가 아니라 **리그 평균**으로 본다."""
    known = RJ.reweigh(adj={}, p_code=0.55, diff=OUT2, players=PLAYERS,
                       team_total_value=2 * 100 * 11 / 2, grade="중")
    unknown = RJ.reweigh(adj={}, p_code=0.55, diff=OUT2, players={},
                         team_total_value=None, grade="중")
    assert unknown["adj_after"]["라인업결장:home"] == pytest.approx(-3.0)
    assert known["value_coverage"]["known"] == 2
    assert unknown["value_coverage"]["known"] == 0


def test_변화_인원_0에도_커버리지가_있다():
    g = RJ.reweigh(adj={}, p_code=0.55, diff={"home": {}}, players={},
                   grade="중")
    assert g["value_coverage"] == {"known": 0, "total": 0}


# ── 사본 금지

def test_원장이_출처_이름을_다시_적지_않았다():
    """🔴 `rejudge` 가 원본이다 — 이름만 베끼면 권한 없는 사본이 된다."""
    import inspect

    from app.engine import pick_ledger as PL

    assert not hasattr(PL, "REGRADE_DEEPSEARCH")
    blk = inspect.getsource(PL.record_confirm_and_analysis)
    assert "RJ.SRC_NEWS" in blk
    assert '"deepsearch"' not in blk
