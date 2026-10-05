"""🔴 KBO 어댑터 — **상태값을 뜻 확인 없이 믿지 않는다**(CLAUDE.md #4).

실측 2026-10-03: 사용자가 *"오늘 기아와 LG 야구 경기"* 를 묻자 봇이 KBO 를 **아예
모른다**는 것이 드러났다 — `config.LEAGUES_AUTO` 에는 있고 `ingest.ADAPTERS` 에는
없었다. 소스를 고른 경위는 `app/collect/kbo.py` 머리글과
`docs/fable/questions/2026-10-03_kbo_source.md` 에 있다.
"""
from __future__ import annotations

import json
from datetime import timezone

from app.collect import kbo
from app.net import Fetched

#: 🔴 **실물 응답 모양**이다(실조회 2026-10-03 · `eventsnext.php?id=139820`).
_EV = {
    "idEvent": "2400431", "strEvent": "LG Twins vs Kia Tigers",
    "strHomeTeam": "LG Twins", "strAwayTeam": "Kia Tigers",
    "strLeague": "Korean KBO League", "strSport": "Baseball",
    "strVenue": "Jamsil Baseball Stadium", "strStatus": "NS",
    # 🔴 실측에서 **미래 경기 전부** 이 값이었다 — 순연 칸이 아니다
    "strPostponed": "yes",
    "strTimestamp": "2026-10-03T05:00:00",
    "dateEvent": "2026-10-03", "strTime": "05:00:00",
    # ⚠️ 이 둘은 실측에서 **어긋나 있었다** — 믿지 않는다
    "dateEventLocal": "2026-09-25", "strTimeLocal": "18:40:00",
    "intHomeScore": None, "intAwayScore": None,
}


def _got(events) -> Fetched:
    return Fetched("https://x", True, 200, json.dumps({"events": events}))


def test_미래_경기를_순연이라고_말하지_않는다():
    """🔴🔴 **이 저장소가 실제로 저지른 실수다**(2026-10-03).

    `strPostponed == "yes"` 를 순연으로 읽었더니 그날 KBO **네 경기가 전부**
    `postponed` 로 들어갔다. 열 건을 받아 보니:

    ```
    NS(미시작) 5건 → strPostponed: yes   (5/5)
    FT(종료)   5건 → strPostponed: no    (5/5)
    ```
    ⚠️ 즉 그 칸은 *"아직 안 끝났다"* 를 뜻하고 **순연과 무관**하다.
    🔴 상태값(200 OK·필드 이름)은 **의도한 뜻의 증거가 아니다**(CLAUDE.md #4).
    """
    row = kbo.slate_row(_EV)
    assert row is not None
    assert row["status"] == "scheduled", row
    # 🔴 코드가 그 칸을 **읽지도 않는다** — 읽으면 또 같은 실수를 한다
    src = (kbo.slate_row.__doc__ or "") + open(kbo.__file__, encoding="utf-8").read()
    import ast
    tree = ast.parse(open(kbo.__file__, encoding="utf-8").read())
    used = [n for n in ast.walk(tree) if isinstance(n, ast.Constant)
            and n.value == "strPostponed"]
    assert not used, "`strPostponed` 를 다시 읽고 있다 — 그 칸은 순연이 아니다"
    assert "strPostponed" in src, "왜 안 읽는지 주석으로 남아 있어야 한다"


def test_UTC_로_읽고_KST_로_보인다():
    """🔴 절대규칙 2 — **DB 는 UTC, 표시만 KST.**

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **이 계약이 거짓을 못 박고 있었다** (실측 2026-10-05 · 인계 ①-2)
    ══════════════════════════════════════════════════════════════════

    종전: `assert row["starts_kst"].hour == 14`.

    ⚠️ `games.starts_kst` 는 `TIMESTAMPTZ` 다 — **순간**만 담고 오프셋은
       **버린다.** 그래서 저 `14` 는 DB 에 닿는 순간 사라지고, 라이브 52행
       **전부** `starts_kst = starts_utc` 였다. 🔴 초록인데 틀린 계약이었다.
    🔴 그 믿음 때문에 질의 여섯 자리가 `starts_kst::date` 로 날짜를 뽑았고,
       그 캐스트는 **세션 시간대(UTC)** 로 돈다 — 52행 중 **16행**이 어긋났다.

    🔴 그래서 **참인 둘**만 센다:
      ① 저장하는 값은 `starts_utc` 와 **같은 순간**이다
      ② 사람에게 보이는 `14:00` 은 `timefmt` 가 만든다
    """
    from app import timefmt
    row = kbo.slate_row(_EV)
    assert row["starts_utc"].tzinfo is not None
    assert row["starts_utc"].astimezone(timezone.utc).hour == 5
    # ① **같은 순간**이다 — 그리고 그 사실이 저장될 꼴(UTC)로 들어간다
    assert row["starts_kst"] == row["starts_utc"], (
        row["starts_kst"], row["starts_utc"])
    assert row["starts_kst"].utcoffset() == timezone.utc.utcoffset(None), (
        f"🔴 `timestamptz` 에 넣는 값은 UTC 여야 한다 — `_kst` 라는 이름이 "
        f"거짓 믿음을 만든 자리다: {row['starts_kst']!r}")
    # ② 🔴 **14:00 은 표시에서 생긴다**(05:00Z = 14:00 KST)
    assert timefmt.kst(row["starts_kst"]).hour == 14
    assert timefmt.kst_label(row["starts_kst"]).endswith("14:00 KST"), (
        timefmt.kst_label(row["starts_kst"]))
    # 🔴 §2 — 현지 시각도 저장한다(KBO 의 현지는 KST 다). ⚠️ 같은 순간이다.
    assert row["starts_local"] == row["starts_utc"]


def test_시각을_모르면_행을_만들지_않는다():
    bad = dict(_EV); bad.pop("strTimestamp"); bad.pop("strTime")
    assert kbo.slate_row(bad) is None


def test_같은_경기를_두_번_적지_않는다():
    """🔴 팀마다 묻기 때문에 같은 경기가 **두 번** 온다 — 그것이 정상이다."""
    rows = kbo.parse_slate(_got([_EV, dict(_EV)]))
    assert len(rows) == 1, rows
    assert rows[0]["ext_id"].startswith("tsdb:")   # 🔴 v5 §8-1 — `출처:경기ID`


def test_열한_주소를_묻는다():
    """🔴 실측: 리그 질의 하나로는 **한 경기**만 왔다 → 10팀을 각각 묻는다.

    ⚠️ 그 비용을 숨기지 않는다. 그리고 세포가 **전부 모으게** 어댑터가 선언한다 —
       첫 성공에서 멈추면 그 열 질의가 뜻이 없다.
    """
    srcs = kbo.sources_slate(None)
    assert len(srcs) == 1 + len(kbo.TEAM_IDS) == 11, len(srcs)
    assert kbo.SLATE_COLLECT_ALL is True
    assert all(s.url and s.url.startswith(kbo.BASE) for s in srcs)
    # 🔴 **키가 없다** — 공개 테스트 키뿐이다(§11-7 유료 API 0건)
    assert "key=" not in kbo.BASE and "apikey" not in kbo.BASE.lower()


def test_금지된_호스트로_가지_않는다():
    """🔴🔴 절대규칙 3 — `koreabaseball.com` 은 robots 가 **전면 거부**다.

    ```
    # 본 사이트의 데이터를 사전 승인 없이 자동 수집·크롤링·복제하는 행위를 금지합니다.
    User-agent: * / Disallow: /
    ```
    ⚠️ 네이버·소파스코어도 같다(실측 2026-10-03). **코드에 그 주소가 없어야** 한다.
    """
    import ast
    tree = ast.parse(open(kbo.__file__, encoding="utf-8").read())
    code = "\n".join(
        ast.unparse(n) for n in tree.body
        if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)))
    for bad in ("koreabaseball.com", "sports.naver.com", "sofascore",
                "mykbostats", "daum.net"):
        assert bad not in code, f"robots 거부 호스트가 코드에 있다: {bad}"


def test_깊이가_없다는_것을_숨기지_않는다():
    """🔴 이 API 는 예고 선발·라인업·순위를 **안 준다**. 있는 척하지 않는다."""
    assert kbo.sources_context("tsdb-1") == []


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **배당 호스트는 판정 경로에 닿지 않는다** (절대규칙 6)
# ══════════════════════════════════════════════════════════════════


def test_배당_호스트를_열지_않는다():
    """🔴🔴 실측 2026-10-03(LG 트윈스 vs 기아 타이거즈)에서 **실제로 열었다**:

    ```
    GET https://888starz.bet/mn/line/baseball/1886142-kbo-south-korea/
        375538124-lg-twins-kia-tigers
    ```
    북메이커 경기 페이지다. CLAUDE.md 절대규칙 6: *"배당은 `research` 스키마에만.
    **판정 경로·카드 렌더러 접근 0건**."*

    ⚠️ `late_hosts`(뒤로 미룸)로는 못 막는다 — 예산이 남으면 **결국 연다.**
    ⚠️ 그 페이지가 본문을 안 줘서 이번엔 사고가 안 났을 뿐이다 — 상태값은 의도한
       것이 동작한다는 증거가 아니다(CLAUDE.md #4).
    """
    from app import rules
    assert rules.banned_host(
        "https://888starz.bet/mn/line/baseball/1886142-kbo/375538124-lg-twins")
    for u in ("https://m.bet365.com/x", "https://www.oddsportal.com/baseball/",
              "https://sportsbook.fanduel.com/y"):
        assert rules.banned_host(u), u
    # 🔴 **멀쩡한 곳은 막지 않는다**
    for u in ("https://www.lgtwins.com/a", "https://sports.donga.com/b",
              "https://tigers.co.kr/c"):
        assert not rules.banned_host(u), u


def test_여는_자리가_그_판정을_부른다():
    """🔴 CLAUDE.md #2 — 만든 것은 **부르는 곳**이 있어야 한다.

    ⚠️ `banned_host` 를 선언만 하고 `Cell` 이 안 부르면 그것은 없는 코드다.
    """
    import inspect

    from app import cells
    src = inspect.getsource(cells.Cell)
    assert "banned_host(" in src, "세포가 배당 호스트 판정을 부르지 않는다"
    # 🔴 **버리되 센다** — 왜 안 열었는지가 사유에 남아야 한다(#3)
    assert "안 열었다" in src


def test_KBO_팀을_한국어로_찾는다():
    """🔴🔴 영문 이름이 검색을 **통째로 엉뚱한 데로** 보냈다(실측 2026-10-03).

    ```
    www.kia.com (자동차) 12회 · www.lg.com·solutions.lg.com 12회
    en.wikipedia.org/wiki/LG_Electronics · nba.com · golf.com
    kare11.com "Gardenhire out as Twins manager"   ← 미네소타 트윈스
    ```
    🔴 한국어 별칭을 선언하면 ① 검색어가 한국어가 되고 ② 귀속 검사가 한국어
       기사를 인정하고 ③ 그 팀 매체를 먼저 연다.
    """
    from app import entities
    for team in kbo.TEAM_IDS:
        ko = entities.aliases_of(team, lang="ko")
        assert ko, f"{team} 의 한국어 별칭이 없다 — 영문으로 검색하게 된다"
        assert "ko" in entities.langs_of(team), team


def test_선언한_매체는_robots_거부_호스트가_아니다():
    """🔴 절대규칙 3 — `m.sports.naver.com` 은 `Disallow: /` 다(실측 2026-10-03).

    ⚠️ 매체 목록에 넣으면 **먼저 열라**는 뜻이 되고, 그 호스트는 열 수 없다.
    """
    from app import entities
    for team in kbo.TEAM_IDS:
        for host in entities.outlets_of(team):
            assert "naver.com" not in host, (team, host)
            assert "koreabaseball.com" not in host, (team, host)


def test_주_세포_질의도_한국어_이름을_쓴다():
    """🔴🔴 사다리(기술 1)만 한국어였고 **주 세포 질의는 영문**이었다(실측 2026-10-03).

    ```
    LG Twins 선발 라인업 10월 3일      ← 🔴 반쯤 한국어인 질의
    → www.kia.com(자동차) · solutions.lg.com · nba.com · golf.com
      kare11.com "Gardenhire out as Twins manager"  ← 미네소타 트윈스
    ```
    ⚠️ §13-b 표에 행이 없는 리그는 `native` 가 비고 **정식명(영문)** 으로 떨어진다.
    🔴 `entities.yaml` 이 그 표기를 **이미** 들고 있다 — 같은 접근자를 부른다
       (사본 금지). 표·호출부가 준 것이 **먼저**다(그쪽이 더 구체적이다).
    """
    from datetime import date

    from app import queries
    got = queries.variants(team="LG Twins", league="KBO",
                           day=date(2026, 10, 3), what="선발 라인업")
    ko = [v for v in got if v.lang == "ko" and v.axis != "§13-b"]
    assert ko, got
    assert any("LG 트윈스" in v.text for v in ko), [v.text for v in ko]
    # 🔴 영어 변형에는 **정식명**이 남는다(영어 매체는 그 이름을 쓴다)
    en = [v for v in got if v.lang == "en"]
    assert any("LG Twins" in v.text for v in en), [v.text for v in en]
    # ⚠️ 호출부가 현지 표기를 주면 **그것이 이긴다** — 선언보다 구체적이다
    given = queries.variants(team="LG Twins", league="KBO", local="엘지",
                             day=date(2026, 10, 3), what="선발 라인업")
    assert any(v.text.startswith("엘지 ") for v in given), [v.text for v in given]
