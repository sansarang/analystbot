"""[LGA-1 / STEP 1-i-1] 이미 오는 자료를 버리고 있었다.

🔴 실측 2026-09-20: football-data 무료 전역 `/matches` 가 매일 돌려주는 대회에
   **Ligue 1 과 Eredivisie 가 들어 있다.**

     2026-09-19 · 전체 53경기
        Championship 10 · Bundesliga 6 · **Ligue 1 6** · Premier League 6
        **Eredivisie 5** · Serie A 5 · Primera Division 5 …  (전부 종료)

   그런데 `football.py:123` 이 화이트리스트 밖이라며 **전건 버린다**.
   `LEAGUES` 에 두 리그가 아예 없기 때문이다(주석 `:124` "리그앙·브라질 등 제외").

🔴 그 주석의 출처는 `9528ba5`(2026-08-23) — 축구 7리그 커버리지를 **처음 연**
   커밋이고, 리그앙 제외에 별도 사유가 적혀 있지 않다. 정책이 아니라
   **그때의 범위**였다.

⚠️ `LEAGUES` 는 **칸 단위로** 기능이 갈린다(odds_key→배당 · fd_names→결과 ·
   tm_code→부상표 · elo→사전값 · aliases→라우터). 그래서 별도 기능 플래그가
   필요 없다 — **`fd_names` 만 채우고 나머지는 비워** 결과 적재만 켠다.
"""
from __future__ import annotations


def test_리그앙_에레디비시가_목록에_있다():
    from app.leagues import LEAGUES

    for key in ("ligue1", "eredivisie"):
        assert key in LEAGUES, f"{key} 가 LEAGUES 에 없다"


def test_결과_적재만_켜진다():
    """🔴 준비되지 않은 기능이 **따라 켜지면 안 된다.**

    `fd_names` 만 채운다. 배당(`odds_key`)·부상표(`tm_code`)·사전값(`elo`)·
    라우터(`aliases`)는 비워 둔다 — 자료가 없는데 목록에 보이면 사용자가
    부를 수 있고, 그때 "자료 없음"이 아니라 **빈 카드**가 나간다.
    """
    from app.leagues import LEAGUES

    for key in ("ligue1", "eredivisie"):
        cfg = LEAGUES[key]
        assert cfg.get("fd_names"), f"{key} 의 fd_names 가 비었다"
        for off in ("odds_key", "tm_code", "elo"):
            assert not cfg.get(off), f"{key} 의 {off} 가 켜져 있다 — 준비 안 됐다"
        assert not cfg.get("aliases"), f"{key} 가 라우터에 노출된다"


def test_fd_이름이_실제_응답과_같다():
    """🔴 실측한 이름 그대로여야 매칭된다 — 추측한 철자를 쓰지 않는다."""
    from app.leagues import LEAGUES

    assert "Ligue 1" in LEAGUES["ligue1"]["fd_names"]
    assert "Eredivisie" in LEAGUES["eredivisie"]["fd_names"]


def test_기존_리그_설정은_그대로다():
    """⚠️ 반대 위험 — 추가하다가 돌던 리그를 건드리면 안 된다."""
    from app.leagues import LEAGUES

    assert LEAGUES["epl"]["fd_names"] == ["Premier League"]
    assert LEAGUES["epl"]["odds_key"] == "soccer_epl"
    assert LEAGUES["la_liga"]["fd_names"] == ["Primera Division", "La Liga"]


def test_기능_플래그가_소비처를_가른다():
    """🔴 [LGA-1] 결과만 쌓는 리그가 배당·위성·라우터에 **따라 켜지면 안 된다.**

    실제로 계약 테스트 5건이 "모든 축구 리그가 위성/배당/라우터에 있다"를
    잠그고 있었고, 그 계약이 뜻한 것은 **전 기능이 준비된 리그**였다.
    그 뜻을 `features` 로 명시한다.
    """
    from app.leagues import features_of, leagues_with

    results = set(leagues_with("results"))
    for key in ("ligue1", "eredivisie"):
        assert key in results
        assert features_of(key) == ("results",), features_of(key)
        for other in ("odds", "satellite", "router", "judge"):
            assert key not in leagues_with(other), f"{key} 가 {other} 에 켜졌다"


def test_명시가_없으면_전부_켜진다():
    """⚠️ 반대 위험 — 플래그를 도입하며 기존 리그를 끄면 안 된다."""
    from app.leagues import FULL_FEATURES, features_of

    for key in ("epl", "la_liga", "serie_a", "bundesliga", "j1",
                "denmark", "kleague1", "acl"):
        assert features_of(key) == FULL_FEATURES, (key, features_of(key))
