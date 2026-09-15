"""U9 — 시장 흐름 완성. 4분류 → 5분류 · 북 불일치 · 라인 환산.

🔴 `steam`(3북 이상이 같은 방향으로 크게)을 `money` 와 구분 못 하면
   **한 북이 흔들린 것**과 **시장 전체가 밀린 것**이 같은 신호가 된다.
"""
from __future__ import annotations

import inspect
import pathlib

import pytest

from app.engine import odds_move as M

NEWS_HOME = {"direction": "home", "why": "주전 복귀"}


def test_다섯_분류다():
    labels = {M.NEWS, M.MONEY, M.CONTRA, M.NONE, M.STEAM}
    assert len(labels) == 5
    assert M.STEAM == "steam"


def test_기존_네_라벨_값이_그대로다():
    """🔴 반대 위험 — observer 가 "contra" 를 **문자열로** 비교한다."""
    assert (M.NEWS, M.MONEY, M.CONTRA, M.NONE) == ("news", "money", "contra", "none")
    src = pathlib.Path("app/engine/observer.py").read_text(encoding="utf-8")
    assert '"contra"' in src, "observer 가 문자열 비교를 쓴다(값 변경 금지)"


# ── steam

def test_steam은_3북_이상_같은_방향():
    assert (M.STEAM_MIN_BOOKS, M.STEAM_MIN_PP) == (3, 3.0)
    assert M.classify(move_pp=5.0, news=None, n_books=4).label == M.STEAM
    assert M.classify(move_pp=5.0, news=None, n_books=2).label == M.MONEY
    assert M.classify(move_pp=2.9, news=None, n_books=9).label == M.MONEY


def test_북_수를_모르면_money다():
    """🔴 반대 위험 — 없는 정보로 더 센 라벨을 붙이지 않는다."""
    assert M.classify(move_pp=9.0, news=None, n_books=None).label == M.MONEY


def test_steam이_뉴스와_같은_방향이면_steam():
    m = M.classify(move_pp=5.0, news=NEWS_HOME, n_books=4)
    assert m.label == M.STEAM and "같은 방향" in m.reason


def test_steam이_뉴스_반대면_contra():
    """🔴 순서 — 취소 신호가 우선이다. 뒤집으면 묻힌다."""
    m = M.classify(move_pp=-5.0, news=NEWS_HOME, n_books=4)
    assert m.label == M.CONTRA
    # 북 수를 몰랐다면 폭이 CONTRA_MIN 미만이라 money 였을 값이다
    assert M.classify(move_pp=-5.0, news=NEWS_HOME,
                      n_books=None).label in (M.MONEY, M.CONTRA)


def test_기존_경로가_그대로다():
    assert M.classify(move_pp=5.0, news=NEWS_HOME).label == M.NEWS
    assert M.classify(move_pp=0.5, news=NEWS_HOME).label == M.NONE
    assert M.classify(move_pp=-9.0, news=NEWS_HOME).label == M.CONTRA


# ── 북 불일치

def test_book_disagree는_SD_2pp():
    assert M.DISAGREE_SD_PP == 2.0
    tight = M.book_disagree([0.44, 0.45, 0.46])
    assert tight["disagree"] is False and tight["n"] == 3
    wide = M.book_disagree([0.40, 0.50])
    assert wide["disagree"] is True and wide["sd_pp"] == 5.0


def test_두_북_미만이면_판단하지_않는다():
    assert M.book_disagree([0.45]) is None
    assert M.book_disagree([]) is None and M.book_disagree(None) is None


def test_book_disagree는_확률을_안_바꾼다():
    src = inspect.getsource(M.book_disagree)
    assert "return" in src and "classify" not in src


# ── 라인 환산

@pytest.mark.parametrize("line,pp", [
    (0.5, 4.0), (1.0, 8.0), (0.25, 2.0), (-0.5, -4.0), (-0.25, -2.0), (0.0, 0.0),
])
def test_라인_환산(line, pp):
    assert M.line_to_pp(line) == pp


def test_라인이_없으면_None():
    assert M.line_to_pp(None) is None


def test_토탈에는_안_쓴다():
    """🔴 반대 위험 — 토탈(U/O)은 같은 계수가 아니다. 호출부가 시장을 가른다."""
    doc = inspect.getdoc(M.line_to_pp) or ""
    assert "핸디" in doc and "토탈" in doc


# ── adj_confirm

@pytest.mark.parametrize("label,confirm,stake,cancel", [
    (M.NEWS, 1, 1.0, False),
    (M.MONEY, 0, 0.5, False),
    (M.STEAM, 0, 0.5, False),
    (M.CONTRA, 0, 0.0, True),
])
def test_adj_confirm_네_경우(label, confirm, stake, cancel):
    got = M.adj_confirm(label, adj_pp=-3.0, move_pp=-5.0)
    assert got["confirm"] == confirm
    assert got["stake_mult"] == stake
    assert got["cancel"] is cancel


def test_news가_반대방향이면_확증_아니다():
    got = M.adj_confirm(M.NEWS, adj_pp=+3.0, move_pp=-5.0)
    assert got["confirm"] == 0 and got["stake_mult"] == 1.0


def test_contra는_취소다():
    assert M.cancels(M.CONTRA) is True
    assert M.cancels(M.STEAM) is False
    assert M.adj_confirm(M.CONTRA, adj_pp=None, move_pp=None)["cancel"] is True


def test_원장에_market_flow가_있다():
    src = pathlib.Path("db/schema.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS market_flow" in src
