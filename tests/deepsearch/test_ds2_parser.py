"""[DS-2P] 변화 감지에 **파서를 붙인다.** 첫 파서 = NPB 스코어보드 띠.

🔴 **지연이 실제로 문제였다 — 실측 2026-09-21:**
     마린스 vs 세이부    시작 18:00 · 공지 **08:30** · DB 반영 **14:00**  → 5h30m 늦음
     라쿠텐 vs 소프트뱅크 시작 13:00 · 중지 **12:40** · DB 반영 **14:00**  → 시작을 지나서 알았다
   다섯 행이 **전부 `updated_at` 14:00** 이다 — 배치 잡이라 사건이 아니라
   시각에 맞춰 돈다. `watch_10m` 이면 08:40 경에 잡았을 것이다.

🔴 **키워드로 짜면 안 된다 — 측정이 그걸 막았다.**
   구단 공지 페이지의 `中止` 는 **메뉴 문구**다:
     라쿠텐  `中止` 9회 → 전부 「地方主催試合中止時の払い戻し」(환불 안내)
     마린스  `中止` 0회 → 오늘 중지가 그 페이지에 아예 없다
   진짜는 **npb.jp 의 스코어보드 띠**에 구조로 들어 있다.

🔴 **`logo_left` 가 홈이다 — 우리 DB 와 4/4 대조해 확인했다.**
   추측하지 않았다.
"""
from __future__ import annotations

import pathlib
from datetime import datetime, timedelta, timezone

import pytest

KST = timezone(timedelta(hours=9))
_FIX = (pathlib.Path(__file__).resolve().parents[1]
        / "fixtures" / "deepsearch" / "npb_scoreboard.html")
AS_OF = datetime(2026, 9, 21, 17, 30, tzinfo=KST)


def _html():
    return _FIX.read_text(encoding="utf-8")


def test_픽스처가_실물이다():
    h = _html()
    assert h.count('class="score_box"') == 5
    assert h.count("中止") == 2
    assert "/scores/2026/0921/e-h-23/" in h


def test_다섯_경기를_구조로_읽는다():
    from app.deepsearch.parsers import parse_npb_scoreboard

    facts = parse_npb_scoreboard(_html(), as_of=AS_OF,
                                 url="https://npb.jp/announcement/roster/")
    assert len(facts) == 5
    for f in facts:
        assert f["event_date"] == "2026-09-21", f
        assert f["as_of"] == AS_OF
        assert f["home"] and f["away"] and f["home"] != f["away"]


def test_중지_두_경기를_잡는다():
    from app.deepsearch.parsers import parse_npb_scoreboard

    facts = parse_npb_scoreboard(_html(), as_of=AS_OF, url="x")
    off = [f for f in facts if f["status"] == "cancelled"]
    assert len(off) == 2, [f["status"] for f in facts]
    homes = sorted(f["home"] for f in off)
    assert homes == ["千葉ロッテマリーンズ", "東北楽天ゴールデンイーグルス"], homes


def test_홈은_logo_left_다():
    """🔴 우리 DB 와 4/4 대조해 확인한 사실이다 — 추측이 아니다.
    `楽天(left)/ソフトバンク(right)` · DB: SoftBank @ Rakuten."""
    from app.deepsearch.parsers import parse_npb_scoreboard

    facts = parse_npb_scoreboard(_html(), as_of=AS_OF, url="x")
    by = {f["home"]: f["away"] for f in facts}
    assert by["東北楽天ゴールデンイーグルス"] == "福岡ソフトバンクホークス"
    assert by["千葉ロッテマリーンズ"] == "埼玉西武ライオンズ"
    assert by["北海道日本ハムファイターズ"] == "オリックス・バファローズ"


def test_경기장과_점수를_함께_싣는다():
    from app.deepsearch.parsers import parse_npb_scoreboard

    facts = parse_npb_scoreboard(_html(), as_of=AS_OF, url="x")
    f = [x for x in facts if x["home"] == "東北楽天ゴールデンイーグルス"][0]
    assert f["venue"] == "楽天モバイル"
    # 🔴 중지 경기의 `*-*` 를 점수로 읽으면 안 된다
    assert f["home_score"] is None and f["away_score"] is None
    done = [x for x in facts if x["status"] == "final"][0]
    assert isinstance(done["home_score"], int)


def test_상태_사실은_as_of_를_갖는다():
    """🔴 09-21 에 내가 저지른 오독을 막는 자리다 — 시각 없는 상태는 소문이다."""
    from app.deepsearch.parsers import parse_npb_scoreboard
    from app.deepsearch.watch import StatusFact

    f = parse_npb_scoreboard(_html(), as_of=AS_OF, url="x")[0]
    sf = StatusFact(value=f["status"], as_of=f["as_of"])
    assert sf.as_of == AS_OF
    assert not sf.is_stale(now=AS_OF + timedelta(minutes=29))
    assert sf.is_stale(now=AS_OF + timedelta(minutes=31))


def test_팀명을_손으로_적지_않았다():
    """🔴 파서는 `alt` 속성에서 읽는다 — 팀 표를 만들지 않는다."""
    import inspect

    from app.deepsearch import parsers

    body = inspect.getsource(parsers.parse_npb_scoreboard).split('"""')[-1]
    for lit in ("楽天", "ロッテ", "阪神", "中日"):
        assert lit not in body, f"팀명 {lit} 을 코드에 적었다"


def test_모양이_이상하면_빈_목록이다():
    from app.deepsearch.parsers import parse_npb_scoreboard

    assert parse_npb_scoreboard("", as_of=AS_OF, url="x") == []
    assert parse_npb_scoreboard("<html><body>없다</body></html>",
                                as_of=AS_OF, url="x") == []


@pytest.mark.asyncio
async def test_감시가_파서를_부른다():
    """🔴 **만들어 놓고 안 이으면 없는 것과 같다.**"""
    import inspect

    from app.deepsearch import watch

    src = inspect.getsource(watch.run_watch)
    assert "parser_for" in src or "parsers" in src
    assert callable(watch.parser_for)
    fn = watch.parser_for({"url": "https://npb.jp/announcement/roster/"})
    assert fn is not None
    assert watch.parser_for({"url": "https://example.com/x"}) is None
