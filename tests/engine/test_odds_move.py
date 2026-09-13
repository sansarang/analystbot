"""MOV-1 — 배당 이동 분석 (Part 1 / Phase 1-B).

🔴 **라인 이동(`move_line_hcp`·`move_line_ou`)은 만들지 않았다.**
   지시문 허가 범위가 "핸디·U/O 라인이 크롤에 없으면 **멈추고 보고**"라고
   정했고, Phase 1 에서 이미 측정했다:
     oddsportal 리그 페이지  handicapValue 0건 (KBO·EPL·라리가 전수)
     theodds(유일한 파생 소스) 08-27 이후 정지 · 10개 북 동시
   원자료가 없는 칸을 만들면 그것은 **영원히 NULL 인 칸**이다.
   승패·언더오버 **확률** 이동은 h2h 만으로 되므로 그것만 만든다.
"""
import pytest

from app.engine import odds_move as M


# ── 이동량

def test_확률_이동은_퍼센트포인트다():
    assert M.move_pp(0.60, 0.58) == pytest.approx(2.0)
    assert M.move_pp(0.58, 0.60) == pytest.approx(-2.0)


def test_한쪽이_없으면_이동을_만들지_않는다():
    """🔴 없는 것을 0 으로 읽으면 '움직이지 않았다'가 된다 — 다른 말이다."""
    assert M.move_pp(None, 0.5) is None
    assert M.move_pp(0.5, None) is None


def test_이동_임계는_2퍼센트포인트다():
    assert M.MOVE_MIN_PP == 2.0
    assert M.moved(1.99) is False and M.moved(2.0) is True
    assert M.moved(-2.0) is True and M.moved(None) is False


# ── 원인 분류

def _news(direction="home"):
    """결장·XI diff 가 가리키는 방향."""
    return {"direction": direction, "why": "홈 주전 4명 결장"}


def test_뉴스_방향과_같으면_news다():
    r = M.classify(move_pp=-3.0, news=_news("away"))
    assert r.label == M.NEWS and "결장" in r.reason


def test_뉴스_없이_움직이면_money다():
    r = M.classify(move_pp=-3.0, news=None)
    assert r.label == M.MONEY
    assert "뉴스 근거 없음" in r.reason


def test_뉴스와_반대면_contra다():
    r = M.classify(move_pp=+4.0, news=_news("away"))
    assert r.label == M.CONTRA


def test_contra_임계는_3퍼센트포인트다():
    assert M.CONTRA_MIN_PP == 3.0
    assert M.classify(move_pp=+2.9, news=_news("away")).label == M.MONEY
    assert M.classify(move_pp=+3.0, news=_news("away")).label == M.CONTRA


def test_임계_미만은_none이다():
    assert M.classify(move_pp=1.5, news=_news("home")).label == M.NONE
    assert M.classify(move_pp=None, news=None).label == M.NONE


def test_딥서치가_없으면_news나_contra가_안_나온다():
    """지시문: 딥서치 없는 경기는 money/none 만 가능하다."""
    for pp in (-9.0, +9.0, 0.5):
        assert M.classify(move_pp=pp, news=None).label in (M.MONEY, M.NONE)


# ── 판정 연결 (1-B-4)

def test_news가_가감과_같은_방향이면_확증이다():
    assert M.confirm(M.NEWS, adj_pp=-3.0, move_pp=-4.0) == 1
    assert M.confirm(M.NEWS, adj_pp=-3.0, move_pp=+4.0) == 0


def test_money는_확증이_아니다():
    assert M.confirm(M.MONEY, adj_pp=-3.0, move_pp=-4.0) == 0


def test_contra면_취소다():
    assert M.cancels(M.CONTRA) is True
    for lb in (M.NEWS, M.MONEY, M.NONE):
        assert M.cancels(lb) is False


# ── 기준선

def test_기준선은_open이고_없으면_가장_이른_것이다():
    snaps = [{"snap_tag": "pre", "p_home": 0.55},
             {"snap_tag": "lineup", "p_home": 0.58}]
    assert M.baseline(snaps)["snap_tag"] == "pre"
    snaps.insert(0, {"snap_tag": "open", "p_home": 0.60})
    assert M.baseline(snaps)["snap_tag"] == "open"
    assert M.baseline([]) is None


# ── 격리

def test_소스를_섞어_계산하지_않는다():
    """🔴 지시문 1-B-1: 이동 계산은 **소스 안에서만**."""
    snaps = [{"snap_tag": "open", "provider": "a", "p_home": 0.60},
             {"snap_tag": "lineup", "provider": "b", "p_home": 0.50}]
    assert M.series(snaps, "b") == [snaps[1]]
    assert M.move_between(snaps, "lineup", "open", provider="b") is None


# ── 원장·스키마

def test_스냅샷에_태그_칸이_있다():
    s = open("db/schema.sql", encoding="utf-8").read()
    assert "ADD COLUMN IF NOT EXISTS snap_tag" in s


def test_원장_칸은_라인_없이_셋이다():
    """⚠️ `move_line_hcp`·`move_line_ou` 는 **만들지 않았다** — 원자료가 없다."""
    s = open("db/schema.sql", encoding="utf-8").read()
    for col in ("odds_open", "move_class", "move_reason"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in s, col
    # ⚠️ 주석에는 "왜 안 만들었는지"가 적혀 있다 — **컬럼 선언만** 본다.
    for col in ("move_line_hcp", "move_line_ou"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" not in s, col
