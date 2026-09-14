"""SCT-6 — 날짜를 **모르는** 결과를 버리지 않는다 (소스별 분리).

🔴 실측 2026-09-14: 지시문 4-3 ②를 그대로 걸었더니 DDG 보강이 6건 → 0건이
   됐다. RSS 는 pubDate 를 싣고 DDG 스니펫은 안 싣는다 — "모른다"를
   "지난 글"과 같게 처리한 것이 결함이었다.
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.engine import scout_config as SC

NOW = datetime(2026, 9, 14, 9, 0, tzinfo=UTC)
KICK = NOW + timedelta(hours=16)


def _hit(title="Napoli formazioni ufficiali", snippet="", url="https://calciolecce.it/a",
         **kw):
    return {"url": url, "title": title, "snippet": snippet, **kw}


def test_DDG_는_날짜가_없으면_undated_로_통과한다():
    s = SC.screen(_hit(), team="Napoli", kickoff=KICK, stage="lineup", now=NOW)
    assert s.keep is True and s.undated is True


def test_DDG_라도_지난_연도가_명시되면_버린다():
    s = SC.screen(_hit(title="Napoli 2021 preview", snippet="2021"),
                  team="Napoli", kickoff=KICK, stage="lineup", now=NOW)
    assert s.keep is False and s.reason == "날짜"


def test_RSS_는_종전_규칙_그대로다():
    """pubDate 를 아는 소스는 신선도를 그대로 건다."""
    old = _hit(published=NOW - timedelta(hours=100))
    assert SC.screen(old, team="Napoli", kickoff=KICK, stage="pre",
                     now=NOW).reason == "신선도"
    fresh = _hit(published=NOW - timedelta(hours=2))
    s = SC.screen(fresh, team="Napoli", kickoff=KICK, stage="pre", now=NOW)
    # 🔴 RSS 는 날짜를 아는 소스다 — undated 로 빠져나가지 않는다.
    assert s.keep is False and s.reason == "날짜"
    dated = _hit(snippet="oggi", published=NOW - timedelta(hours=2))
    assert SC.screen(dated, team="Napoli", kickoff=KICK, stage="pre",
                     now=NOW) == SC.Screen(True, "")


def test_undated_는_tier_를_한_단계_내린다():
    hits = [_hit(url="https://fantacalcio.it/b", snippet="oggi"),      # tier2 · 날짜 있음
            _hit(url="https://calciolecce.it/a")]                       # tier1 · 날짜 없음
    picked = SC.rank_and_pick(hits, league="serie_a", stage="pre",
                              team="Napoli", kickoff=KICK, now=NOW)
    # tier1(1) + undated(1) = 2 → tier2(2) 와 같은 등급, 원래 순서가 가른다.
    assert [h["url"] for h in picked] == ["https://fantacalcio.it/b",
                                          "https://calciolecce.it/a"]
    assert picked[1]["undated"] is True


def test_본문_재검사는_증거가_있을_때만_버린다():
    ok, why = SC.body_date_ok(
        '<meta property="article:published_time" content="2026-09-14T08:00:00Z">',
        kickoff=KICK, now=NOW)
    assert ok and not why
    bad, why2 = SC.body_date_ok("경기 리뷰 2023-05-01", kickoff=KICK, now=NOW)
    assert not bad and "경기일에서" in why2
    # 🔴 본문에도 날짜가 없으면 통과다 — 모르는 것을 오래된 것으로 바꾸지 않는다.
    assert SC.body_date_ok("날짜가 없는 본문", kickoff=KICK, now=NOW)[0] is True
    assert SC.body_date_ok("Preview 2021 season", kickoff=KICK, now=NOW)[0] is False
