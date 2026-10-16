"""🔴🔴 계약 — **보드 수집 사다리**(의심 검증 통합본 v2 · 2026-10-14i §1).

| 조항 | 여기서 무엇을 본다 |
|---|---|
| §1-1 사다리 순서 | ① 캡처가 ②③ 을 **덮는다** · 줄마다 출처·시각·북메이커 |
| §1-2 한 줄 고르기 | 아시안 **쿼터는 메인으로 안 고른다** · 정수는 승·무·패 세 갈래 |
| §1-3 보드 없는 경기는 없다 | 전부 실패면 **경보**가 찬다(조용한 0 금지) |
| §1-1 ③ | 우리 대회마다 **③ 열쇠가 있거나 없는 까닭이 표에 적혀 있다** |

🔴 ⑥번이 핵심이다 — 열쇠 표가 **손으로 유지하는 목록**이면 대회를 늘릴 때마다
   조용히 빠진다(실측 2026-10-14: 칸이 다섯뿐이어서 챔피언십·J리그·에레디비시에·
   포르투갈·아르헨티나·브라질이 ③ 에서 통째로 빠졌다 — 보드 수집 실패로 보였다).
   그래서 계약은 **대회 목록에서 자라게** 짠다(CLAUDE.md #1).
"""
from __future__ import annotations

import pytest

from app.core import boardfeed as bf
from app.core import competition as cp
from app.core import odds as od

#: 🔴 ③ 가 **다루지 않는다고 실측으로 선언된** 대회(`scope_note` 와 같은 사실).
#   ⚠️ 여기 적는 것은 *"아직 안 넣었다"* 가 아니라 **"피드에 아예 없다"** 뿐이다.
NO_FEED = {
    "league:ACLE": "AFC — 피드 종목 목록에 아시아 클럽 대회가 없다(실측 10-14)",
    "league:ACL2": "AFC — 같다",
    "league:JLC": "J리그컵 — 피드에 일본 컵 종목이 없다(실측 10-14)",
    "national_friendly": "대표팀 친선 — 피드에 친선 종목이 없다(실측 10-06)",
    # 🔴🔴 **중미 1부 셋**(2026-10-16 등록) — 피드 종목 목록 **85개를 받아**
    #    `guatemal`·`hondur`·`costa`·`salvador`·`concacaf` 로 훑었고 **0건**이었다
    #    (걸린 것은 `soccer_uefa_nations_league` 뿐이다). 그래서 ③ 는 이 리그를
    #    못 받는다 — *"아직 안 넣었다"* 가 아니라 **피드에 없다**.
    "league:GUA1": "과테말라 1부 — 피드 종목 85개에 중미 리그가 없다(실측 10-16)",
    "league:HON1": "온두라스 1부 — 같다(실측 10-16)",
    "league:CRC1": "코스타리카 1부 — 같다(실측 10-16)",
}


def test_사다리는_캡처를_먼저_본다():
    """🔴 §1-1 — ① 이 들어오면 **아래를 덮는다**."""
    import inspect
    code = inspect.getsource(bf.of)
    said = [code.index("from_capture"), code.index("from_fixtures"),
            code.index("from_feed")]
    assert said == sorted(said), f"사다리 순서가 ①②③ 이 아니다: {said}"


def test_줄마다_출처와_시각과_북메이커가_붙는다():
    """🔴 §1-1 마지막 줄 — 출처 없는 줄은 어디서 왔는지 모른다."""
    for name in ("from_capture", "from_fixtures", "from_feed"):
        import inspect
        code = inspect.getsource(getattr(bf, name))
        assert "source=" in code, f"{name} 가 출처를 안 붙인다"
        assert ("at=" in code), f"{name} 가 수집 시각을 안 붙인다"


def test_쿼터_라인은_메인으로_고르지_않는다():
    """🔴 §1-2 — 국내 보드에 ±0.25·±0.75 가 **없다** → 표시만."""
    assert bf.domestic(0.5) and bf.domestic(-1.5) and bf.domestic(0.0)
    assert not bf.domestic(0.25)
    assert not bf.domestic(-0.75)
    rows = [bf.Row(market="handicap", side="home", point=-0.75, price=1.9,
                   book="a"),
            bf.Row(market="handicap", side="away", point=0.75, price=1.9,
                   book="a")]
    assert bf.main_line(rows, "handicap") == [], "쿼터를 메인으로 골랐다"


def test_정수_기준선은_승무패_세_갈래다():
    """🔴 §1-2 — 핸디 0·±1 은 **무**(푸시)가 있다."""
    board = bf.Board(rows=[
        bf.Row(market="handicap", side="home", point=-1.0, price=1.9)])
    got = board.names()
    assert any("무" in x for x in got), f"무 갈래가 없다: {got}"
    board2 = bf.Board(rows=[
        bf.Row(market="handicap", side="home", point=-1.5, price=1.9)])
    assert not any("무" in x for x in board2.names())


@pytest.mark.asyncio
async def test_전부_실패하면_경보가_찬다():
    """🔴🔴 §1-3 — **보드 없는 경기는 없다**. 조용한 0 금지(CLAUDE.md #3)."""
    got = await bf.of("없는팀 vs 없는팀2", net=None, market=None, fixtures=[])
    assert not got.rows
    assert got.alarm and "실패" in got.alarm, f"경보가 비었다: {got!r}"
    assert "실패" in bf.said_of(got), "카드 블록이 경보를 안 적는다"


def test_우리_대회마다_셋째칸_열쇠가_있거나_없는_까닭이_적혀_있다():
    """🔴🔴 §1-1 ③ — 표는 **대회 목록에서 자란다**(손 목록 금지).

    ⚠️ 대회를 늘렸는데 종목 열쇠를 안 적으면 그 대회의 ③ 는 영원히 0건이고,
       사다리는 그것을 *"보드 수집 실패"* 로만 보고한다. 🔴 그래서 빠진 대회는
       **여기서 빨개진다** — 넣든지, `NO_FEED` 에 **까닭을 적든지** 해야 한다.
    """
    feeds, _whys = od.ready_feeds()
    if not feeds:
        pytest.skip("피드 키가 없다 — 표만 있는 상태에서는 못 잰다")
    miss = []
    for key in sorted(cp.rows()):
        # 🔴🔴 **운영과 같은 길로 본다**(사용자 지시 2026-10-16) — 종전엔
        #    `sport_key_for(이름)` 으로 봤고, 그래서 코스타리카
        #    `Primera Division` 이 **스페인 라리가 열쇠**로 잡혀 *"열쇠가 있다"*
        #    고 셌다(실사고 2026-10-16). 🔴 이제 대회 줄의
        #    `sources.odds_sport_key` 를 읽는 `sport_key_of_comp` 하나를 본다.
        hit = any(od.sport_key_of_comp(f, key)[0] for f in feeds)
        if not hit and key not in NO_FEED:
            miss.append(f"{key}(`{said}`)")
    assert not miss, ("🔴 ③ 종목 열쇠가 없는 대회 — 넣거나 `NO_FEED` 에 까닭을 "
                      "적어라: " + " · ".join(miss))
    # 🔴 반대쪽도 본다 — **없다고 적었는데 실은 있는** 칸은 지워야 한다
    stale = []
    for key, why in NO_FEED.items():
        if key not in cp.rows():
            continue
        # 🔴 여기도 **운영과 같은 길**이다(위 머리말) — 이름으로 보면
        #    코스타리카가 라리가 열쇠를 받아 *"열쇠가 생겼다"* 로 거짓 빨개진다.
        if any(od.sport_key_of_comp(f, key)[0] for f in feeds):
            stale.append(f"{key} — `{why}`")
    assert not stale, "🔴 `NO_FEED` 가 낡았다(열쇠가 생겼다): " + " · ".join(stale)


def test_겹치는_낱말이_다른_대륙_열쇠를_받지_않는다():
    """🔴 실측 2026-10-14 — `AFC Champions League Elite` 가 `champions league`
    에 걸려 **UEFA 열쇠**를 받았다. 사유가 *"매칭 실패"* 로 적혀
    *"이 피드엔 AFC 가 아예 없다"* 는 사실을 가렸다."""
    feeds, _whys = od.ready_feeds()
    if not feeds:
        pytest.skip("피드 키가 없다")
    feed = feeds[0]
    got, why = od.sport_key_for(feed, "AFC Champions League Elite")
    assert not got, f"AFC 가 `{got}` 를 받았다"
    assert "afc" in why.lower(), why
    # 🔴 UEFA 는 그대로 받아야 한다(제외가 과하면 그것도 결함이다)
    assert od.sport_key_for(feed, "Champions League")[0] \
        == "soccer_uefa_champs_league"
