"""단계 4 계약 — **인용을 어느 팀에 붙이나.** 🔴 거짓 사실을 막는다.

## 무엇이 실제로 일어났나 (실측 2026-10-01, USL 녹음)

`parse_intent` 는 **검색 결과의 어떤 인용이든** 받았다. 팀 확인이 없었다. 그래서
`koreadaily.com` 의 **영화 인터뷰**에서 이 문장을 뽑아 감독 발언으로 블랙보드에
올렸다:

```
자기 언어가 있는 영화에 손이 갈 것
영화는 세계공통어…이야기 힘 믿어
```

🔴 **사실 0건보다 나쁘다.** §0 절대 전제가 그 이유를 적었다 — *"전제 변수 하나가
틀리면 그 위의 결론이 전부 틀린다"*(09-29 르방컵에서 8개 결론을 철회했다).

⚠️ 같은 병을 라인업에서 한 번 고쳤다(M14: `阪神・ルーカス` 를 소프트뱅크 라인업으로
   저장). 그때 만든 것이 `_attribute`·`_names_hit` 인데 **인용 경로에는 안 걸려
   있었다.** 고친 자리가 다음 자리를 못 지켰다.

## 종목에 없는 질문

같은 녹음에서 축구 경기에 `starter_recent`(예고 선발)를 돌렸고, 검색어가
`Las Vegas Lights 선발 등판 1일` — **야구 용어**가 됐다. 어댑터가 이미 적어 뒀다:
*"축구에는 예고 선발이 없다"*(`fdorg`), *"하키에는 예고 선발(투수)이 없다"*(`nhl`).
"""
from __future__ import annotations

import inspect

from app import queries, searchcells, slate
from app.cells import Q_INTENT, Q_TYPES, Question
from app.search import Hit

#: 🔴 실측 그대로. 이 기사는 **팀 이름이 없다** — 그것이 유일한 판별점이다.
FILM = Hit(title="영화는 세계공통어…이야기 힘 믿어",
           url="https://www.koreadaily.com/article/20260926231959722",
           snippet='감독은 "자기 언어가 있는 영화에 손이 갈 것"이라고 말했다')

REAL = Hit(title="Las Vegas Lights head coach on rotation",
           url="https://example.test/lv-presser",
           snippet='Las Vegas Lights boss said "we will rotate three players"')


def _q() -> Question:
    return Question(Q_INTENT, "USL Championship:Las Vegas Lights:2026-10-01",
                    team="Las Vegas Lights", league="USL Championship")


def test_팀_언급이_없는_기사의_인용은_버린다():
    """★ 🔴 실측 회귀 — 영화 인터뷰가 감독 발언으로 들어왔다."""
    got = searchcells.parse_intent([FILM], _q())
    assert got == [], (
        f"팀 이름이 없는 기사에서 인용을 뽑았다: "
        f"{[str(f.value)[:40] for f in got]}")


def test_팀_언급이_있으면_인용을_받는다():
    """🔴 반대 위험 — 너무 조이면 **진짜 인용이 사라진다.**

    ⚠️ M14 를 고칠 때 배운 것이다: 귀속 불명이면 *버리지 않고* 팀 칸만 비운다.
       여기서는 팀이 명시됐으므로 받아야 한다.
    """
    got = searchcells.parse_intent([REAL], _q())
    assert len(got) == 1, [str(f.value) for f in got]
    assert "rotate" in str(got[0].value)
    assert got[0].hardness == "soft", "스니펫 근거는 soft 다(§12-b)"


def test_본문_경로에도_같은_검사가_걸려_있다():
    """🔴 스니펫만 막으면 **본문 경로로 들어온다** — 실측에서 그 경로였다."""
    src = inspect.getsource(searchcells.parse_intent_body)
    assert "_names_hit" in src, (
        "`parse_intent_body` 에 귀속 검사가 없다 — 스니펫만 막으면 새어 들어온다")


# ══════════════════════════════════════════════════════════════════
# 종목에 없는 질문
# ══════════════════════════════════════════════════════════════════


def test_종목표가_슬레이트_종목을_전부_덮는다():
    """🔴 **목록이 원본에서 자란다** — 종목은 `slate.SPORT_KO` 가 원본이다.

    종목이 늘면(사용자 지시로 다섯이 됐다) 이 계약이 "질문표도 따라가라"고 빨개진다.
    """
    missing = sorted(set(slate.SPORT_KO) - set(queries.SPORT_QUESTIONS))
    assert missing == [], f"질문표에 없는 종목: {missing}"


def test_질문_이름이_원본_어휘다():
    """★ 🔴 **내가 지어낸 이름이 세포를 조용히 없앴다** — 2026-10-01 실측.

    첫 판의 질문표에 `"coach_change"`·`"live"` 를 적었다. 둘 다 없는 이름이다 —
    감독 교체 세포는 `intent` 를 쓰고(`subject` 에 `:coach` 를 붙여 id 만 가른다),
    라이브는 `live_score` 다. 그래서 녹음이 **감독 교체 세포를 "축구에 없는
    질문"으로 건너뛰었다** — §4 `coach_change` 의 보기가 *"조지아 사뇰 사임"*
    (축구!)인데도.

    🔴 내가 "조용한 0"을 막으려고 넣은 가드가 조용한 0 을 **만들었다.**
       그래서 어휘를 `cells.Q_TYPES` 와 대조한다.
    """
    for sport, have in queries.SPORT_QUESTIONS.items():
        unknown = sorted(have - set(Q_TYPES))
        assert unknown == [], f"{sport}: `Q_TYPES` 에 없는 질문 이름 {unknown}"
    # 🔴 반대 위험 — 어느 종목에도 안 든 질문 타입은 **영영 안 돈다**
    covered = set().union(*queries.SPORT_QUESTIONS.values())
    orphan = sorted(set(Q_TYPES) - covered)
    assert orphan == [], f"어느 종목에도 열려 있지 않은 질문: {orphan}"


def test_녹음_도구가_쓰는_질문_타입이_원본_어휘다():
    """🔴 호출부가 지어낸 이름을 쓰면 가드가 그 세포를 **조용히** 건너뛴다."""
    from tools import record_question
    bad = [q for _n, q in record_question.CELLS if q not in Q_TYPES]
    assert bad == [], f"`Q_TYPES` 에 없는 질문 타입을 쓴다: {bad}"


def test_감독_교체는_모든_종목에_있다():
    """🔴 §4 `coach_change` 의 보기가 *"조지아 사뇰 사임"* — **축구**다.

    감독 교체 세포는 `intent` 질문을 쓰므로, 그것이 모든 종목에 열려 있어야 한다.
    """
    for sport in queries.SPORT_QUESTIONS:
        assert queries.asks(sport, "intent")[0] is True, sport


def test_모르는_질문_이름은_막지_않고_적어_둔다():
    """🔴 오타 하나가 세포를 없애지 않게 — 막지 않고 **이름으로** 남긴다."""
    ok, why = queries.asks("soccer", "coach_change")
    assert ok is True, "모르는 이름을 막았다 — 오타가 세포를 조용히 없앤다"
    assert "Q_TYPES" in why and "coach_change" in why


def test_예고_선발은_야구에만_있다():
    """어댑터가 적어 둔 사실을 기계로 집행한다."""
    assert queries.asks("baseball", "starter_recent")[0] is True
    for sport in ("soccer", "hockey", "basketball", "volleyball"):
        ok, why = queries.asks(sport, "starter_recent")
        assert ok is False, f"{sport} 에 예고 선발 질문이 열려 있다"
        assert why, f"{sport}: 묻지 않은 **사유**가 없다(조용한 0 금지)"


def test_모르는_종목은_막지_않고_적어_둔다():
    """🔴 표에 없는 종목을 조용히 전부 거부하면 **새 종목이 아무 질문도 못 한다.**"""
    ok, why = queries.asks("curling", "lineup")
    assert ok is True and "질문표에 없다" in why


def test_라인업과_의도는_모든_종목에_있다():
    for sport in queries.SPORT_QUESTIONS:
        for qtype in ("lineup", "intent"):
            assert queries.asks(sport, qtype)[0] is True, (sport, qtype)


# ══════════════════════════════════════════════════════════════════
# 🔴 주소에 적힌 발행 날짜 — 9개월 된 기사가 오늘 것으로 통과했다
# ══════════════════════════════════════════════════════════════════

#: 실측 그대로. 🔴 **9개월 지난 기사**가 오늘 경기의 "감독 의도" 사실이 됐다.
STALE_URL = ("https://www.lasvegaslightsfc.com/news/2025/01/09/"
             "las-vegas-lights-fc-announces-antonio-nocerino-as-head-coach/")


def test_주소_경로의_발행_날짜를_읽는다():
    """★ 🔴 실측 2026-10-01 — 날짜가 **주소에 적혀 있었는데** 안 읽었다.

    그 페이지에 메타 발행 시각이 없어서 `dateless_ok` 경로로 soft 로 들어왔다.
    매체가 경로에 박아 둔 날짜는 **발행자가 붙인 구조**다 — 본문에 인용된 과거
    날짜(M13 재발 경로)와 다르다.
    """
    from app.net import published_at_from_url
    got = published_at_from_url(STALE_URL)
    assert got is not None and (got.year, got.month, got.day) == (2025, 1, 9), got


def test_연도_하나는_발행_날짜가_아니다():
    """⚠️ 좁게 읽는다 — `/연/월/일/` 꼴만. 그러지 않으면 M13 이 되돌아온다."""
    from app.net import published_at_from_url
    for url in ("https://en.wikipedia.org/wiki/2026_Las_Vegas_Lights_FC_season",
                "https://x.test/tag/2026/", "https://x.test/2026-season"):
        assert published_at_from_url(url) is None, url


def test_메타가_있으면_메타가_이긴다():
    """🔴 주소 날짜는 **대체**다 — 페이지가 적은 것을 덮지 않는다."""
    from app.net import published_at_of
    got = published_at_of(
        '<meta property="article:published_time" content="2026-09-30T10:00:00Z">',
        "https://x.test/news/2020/01/01/a")
    assert got is not None and got.year == 2026, got


def test_본문이_없어도_주소는_본다():
    from app.net import published_at_of
    got = published_at_of("", "https://x.test/news/2026/09/30/a")
    assert got is not None and (got.month, got.day) == (9, 30), got


# ══════════════════════════════════════════════════════════════════
# 🔴 열기 게이트 — 팀을 말하지 않는 페이지는 열지 않는다
# ══════════════════════════════════════════════════════════════════

#: 실측 2026-10-01 그대로. 🔴 라인업 세포가 **열기 20건 중 9건을** 이런 데 태웠다.
JUNK = ["https://www.airbnb.ca/rooms/1758463873006774167",
        "https://www.airbnb.gy/rooms/1182125645369818850",
        "https://deadikace.com/concerts/",
        "https://parissi.app/en/poi/124950"]
#: 같은 세포가 **진짜 라인업 페이지**에도 닿았다 — 예산을 버린 뒤였다.
REAL_PAGES = [
    "https://www.sportsbencher.com/lineups/"
    "sacramento-republic-fc-vs-las-vegas-lights-fc",
    "https://www.fotmob.com/matches/"
    "sacramento-republic-fc-vs-las-vegas-lights-fc/d66zlwfw",
    "https://www.sacrepublicfc.com/schedule/",
]


def test_쓰레기_주소는_팀_언급_판정에서_떨어진다():
    from app.verify import mentions_team
    for u in JUNK:
        assert mentions_team(u, "Sacramento Republic") is False, u


def test_진짜_경기_페이지는_주소만으로도_통과한다():
    """🔴 주소에 팀명이 들어 있다 — 그래서 **주소도 본다.**

    ⚠️ `sacrepublicfc.com` 은 **약칭**이다(`sacramento` 가 통째로 없다). 구단 공식
       도메인이 가장 좋은 소스인데 약칭 때문에 떨어졌다 — 낱말 둘(`sacr`·`republic`)
       로 통과시킨다(실측 2026-10-01).
    """
    from app.verify import mentions_team
    for u in REAL_PAGES:
        assert mentions_team(u, "Sacramento Republic") is True, u
    assert mentions_team("https://www.lasvegaslightsfc.com/roster/",
                         "Las Vegas Lights") is True


def test_도시_이름_하나로는_통과하지_못한다():
    """🔴 낱말 하나만 요구하면 **도시 이름으로 호텔·공연 페이지가 통과한다.**"""
    from app.verify import mentions_team
    assert mentions_team("https://lasvegashotels.com/deals",
                         "Las Vegas Lights") is False
    assert mentions_team("Las Vegas weather forecast",
                         "Las Vegas Lights") is False


def test_일본팀_약칭도_통과한다():
    """⚠️ 기사는 약칭을 쓴다 — 이 판정이 좁아지면 NPB 가 통째로 막힌다."""
    from app.verify import mentions_team
    assert mentions_team("西武 スタメン 平良", "埼玉西武ライオンズ", "西武") is True
    assert mentions_team("阪神 スタメン", "埼玉西武ライオンズ", "西武") is False


def test_판정이_한_곳에서만_정의된다():
    """🔴 파서와 열기 게이트가 **같은 판정**을 써야 한다.

    둘이 갈리면 파서가 버릴 자료를 열기가 열고, **예산만 탄다.**
    """
    import inspect

    from app import cells, searchcells
    assert "mentions_team" in inspect.getsource(searchcells._names_hit), \
        "`searchcells` 가 판정을 따로 들고 있다 — `verify` 로 모으라"
    assert "mentions_team" in inspect.getsource(cells.Cell._open_hits), \
        "`cells` 의 열기 게이트가 판정을 안 쓴다"


def test_건너뛴_개수를_사유로_남긴다():
    """🔴 조용히 지우지 않는다 — 몇 건을 왜 안 열었는지 남는다."""
    import inspect

    from app import cells
    src = inspect.getsource(cells.Cell._open_hits)
    assert "팀 언급 없어 안 연 자료" in src


def test_앞_두_자_규칙은_CJK_전용이다():
    """★ 🔴 라틴 문자 두 자는 아무 데나 걸린다.

    실측 2026-10-01: `Las Vegas Lights` 의 앞 두 자 `La` 가
    `"Las Vegas weather forecast"` 에 걸려 **호텔·날씨 페이지가 통과했다.**
    그 규칙은 `埼玉西武ライオンズ` → `西武` 같은 **CJK 약칭**을 위해 있다.
    """
    from app.verify import mentions_team
    assert mentions_team("西武 スタメン 平良", "埼玉西武ライオンズ", "西武") is True
    assert mentions_team("두산 베어스 선발", "두산 베어스") is True
    # 🔴 라틴에서는 안 걸려야 한다
    assert mentions_team("Last minute deals", "Las Vegas Lights") is False
    assert mentions_team("Sacred Heart hospital", "Sacramento Republic") is False
