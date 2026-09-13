"""ODP-1 — oddsportal 에서 축구 1X2 배당을 긁는다 (Phase 1 별도 승인 "나"→"A").

🔴 **실측이 선택지를 바꿨다.** 리그 목록 페이지에는 파생 시장이 없다
   (`handicapValue` 0건, `bettingTypeId` 가 야구 `{3}` · 축구 `{1}` 하나씩).
   대신 **축구 1X2 가 이미 그 페이지에 있었고 우리가 안 긁고 있었다** —
   최근 14일 축구 69경기 중 배당 보유 0건, 원인은 `LEAGUE_URL` 에 축구가
   없어서였다. Phase 1 ①(시장 디빅)이 축구에서 아예 안 서는 상태였다.

⚠️ 팀명은 **퍼지 금지**다(AC밀란 오매칭 전례). 결정적 정규화 + 명시 별칭표만
   쓴다. 그리고 정규화가 팀을 구분하는 토큰을 지우면 안 된다 — 실측에서
   `united`·`city`·`real`·`atletico` 를 지웠더니 **맨시티=맨유, 레알=AtM** 이
   같은 키가 됐다.
"""
import pytest

from app.collectors import oddsportal as OP


# ── 리그 표

def test_축구_7리그가_전부_있다():
    """🔴 목록을 손으로 적지 않는다 — `leagues.LEAGUES` 가 원본이다."""
    from app.leagues import LEAGUES

    assert set(OP.SOCCER_URL) == set(LEAGUES), (set(OP.SOCCER_URL) ^ set(LEAGUES))


def test_야구_리그는_그대로다():
    assert set(OP.LEAGUE_URL) == {"kbo", "npb"}


# ── 정규화: 팀을 구분하는 토큰을 지우지 않는다

@pytest.mark.parametrize("a,b", [
    ("Manchester City FC", "Manchester United FC"),
    ("Real Madrid CF", "Club Atlético de Madrid"),
    ("AC Milan", "FC Internazionale Milano"),
    ("Jeonbuk Hyundai Motors", "Ulsan Hyundai FC"),
])
def test_다른_팀은_다른_키다(a, b):
    """🔴 실측에서 실제로 충돌했던 짝들이다."""
    assert OP.norm(a) != OP.norm(b), (a, b, OP.norm(a))


@pytest.mark.parametrize("a,b", [
    ("Bournemouth", "AFC Bournemouth"),
    ("Aston Villa", "Aston Villa FC"),
    ("Manchester City", "Manchester City FC"),
    ("FC Koln", "1. FC Köln"),
    ("Sonderjyske", "SonderjyskE"),
])
def test_같은_팀의_두_표기는_같은_키다(a, b):
    assert OP.norm(a) == OP.norm(b), (a, b, OP.norm(a), OP.norm(b))


# ── 별칭표

def test_별칭은_우리_DB_표기를_가리킨다():
    """별칭 값이 다시 별칭 키가 되면 순환이다. 값은 최종 표기여야 한다."""
    for op_name, ours in OP.SOCCER_ALIAS.items():
        assert ours not in OP.SOCCER_ALIAS, f"{op_name} → {ours} 가 또 별칭이다"
        assert op_name != ours, op_name


def test_실측에서_막혔던_팀이_전부_별칭에_있다():
    need = ["Brighton", "Coventry", "Hull", "Ipswich", "Manchester Utd",
            "Newcastle", "Nottingham", "Tottenham",
            "Alaves", "Ath Bilbao", "Atl. Madrid", "Betis", "Dep. A Coruna",
            "Espanyol", "Racing Santander", "Rayo Vallecano",
            "Fiorentina", "Inter",
            "B. Monchengladbach", "Bayern Munich", "Dortmund", "Hoffenheim",
            "Mainz", "Stuttgart",
            "Aarhus", "Odense",
            "Daejeon", "Incheon", "Jeju SK", "Jeonbuk", "Pohang", "Ulsan HD"]
    missing = [n for n in need if n not in OP.SOCCER_ALIAS]
    assert not missing, missing


def test_별칭을_거치면_우리_이름과_키가_같다():
    pairs = [("Brighton", "Brighton & Hove Albion FC"),
             ("Atl. Madrid", "Club Atlético de Madrid"),
             ("Inter", "FC Internazionale Milano"),
             ("Bayern Munich", "FC Bayern München"),
             ("Ulsan HD", "Ulsan Hyundai FC")]
    for op_name, ours in pairs:
        assert OP.team_key(op_name) == OP.norm(ours), (op_name, ours)


# ── 3-way 파싱

_SOCCER_BLOB = (
    '"aaaaaa1":{"event":1234567,"odds":['
    '{"avgOdds":2.10,"bettingTypeId":1,"scopeId":2,"outcomeId":"x"},'
    '{"avgOdds":3.40,"bettingTypeId":1,"scopeId":2,"outcomeId":"y"},'
    '{"avgOdds":3.60,"bettingTypeId":1,"scopeId":2,"outcomeId":"z"}'
    '],"cnt":3}'
)


def test_축구는_홈_무_원정_셋을_읽는다():
    out = OP.parse_odds(_SOCCER_BLOB, three_way=True)
    assert out[1234567] == {"home": 2.1, "draw": 3.4, "away": 3.6}


def test_야구_파서는_3way_블록을_버린다():
    """⚠️ 기본값은 종전 그대로 2-way 다 — 야구 경로가 안 바뀌어야 한다."""
    assert OP.parse_odds(_SOCCER_BLOB) == {}


def test_행에_무승부가_실린다():
    rows = OP.to_rows("H", "A", {"home": 2.1, "draw": 3.4, "away": 3.6})
    sides = {r["side"]: r["odds"] for r in rows}
    assert sides == {"H": 2.1, "Draw": 3.4, "A": 3.6}
    assert all(r["market"] == "h2h" for r in rows)


def test_무승부가_없으면_안_만든다():
    """🔴 야구에 무승부 칸을 만들면 디빅이 3-way 로 잘못 돈다."""
    rows = OP.to_rows("H", "A", {"home": 1.8, "away": 2.0})
    assert {r["side"] for r in rows} == {"H", "A"}


# ── 배선

def test_레지스트리가_축구를_담당한다():
    from app.registry import provider

    assert "soccer" in provider("oddsportal").sports


def test_수집_함수가_있고_스케줄러가_부른다():
    import inspect

    from app.collectors import odds_free
    from app import scheduler

    assert hasattr(odds_free, "collect_soccer")
    assert "collect_soccer" in inspect.getsource(scheduler)
