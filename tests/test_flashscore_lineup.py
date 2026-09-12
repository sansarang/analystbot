"""SOC-8 — Flashscore 라인업(층1). 킥오프 1시간 전에 전 경기 제공.

실측 2026-09-12 23:30 (운영): 당일 피드 3166경기 · 우리 31경기 매칭 31/31 ·
킥오프 1시간 안 13경기에서 포메이션·선발 수신, 먼 경기는 0명.

🔴 첫 시도에서 `NU÷` 슬러그만 긁어 "남의 팀 선수가 섞였다"고 잘못 보고했다.
   그 목록은 **알파벳순**이었다(블록과 무관하게 긁은 탓). 한 블록이 한 선수다.
"""
from app.collectors import flashscore as FS

_FIX = ("SA÷1~AA÷YRWOt1od¬AD÷1757700000¬WU÷liverpool¬WV÷fulham¬AE÷Ливерпуль¬"
        "AF÷Фулхэм¬~AA÷G8yViRgc¬AD÷1757700000¬WU÷chelsea¬WV÷hull-city¬")

_LU = (
    "LA÷Расстановка¬LB÷Стартовые составы¬LC÷1¬"
    "~LD÷1-4-2-3-1¬LH÷0¬LP÷a1¬LI÷Alisson¬LJ÷1¬NU÷/player/alisson/a1/¬"
    "~LH÷1¬LP÷a2¬LI÷Van Dijk V.¬LJ÷4¬NU÷/player/van-dijk-virgil/a2/¬"
    "¬LC÷2¬"
    "~LD÷1-5-4-1¬LH÷0¬LP÷b1¬LI÷Leno B.¬LJ÷17¬NU÷/player/leno-bernd/b1/¬"
    "~LH÷1¬LP÷b2¬LI÷Bassey C.¬LJ÷3¬NU÷/player/bassey-calvin/b2/¬"
    "¬LB÷Замены¬LC÷1¬"
    "~LH÷0¬LP÷c1¬LI÷Gakpo C.¬LJ÷18¬NU÷/player/gakpo-cody/c1/¬"
    "¬LC÷2¬"
    "~LH÷0¬LP÷d1¬LI÷King J.¬LJ÷9¬NU÷/player/king-joshua/d1/¬")


def test_경기_목록을_읽는다():
    fx = FS.parse_fixtures(_FIX)
    assert [f["id"] for f in fx] == ["YRWOt1od", "G8yViRgc"], fx
    assert fx[0]["home"] == "liverpool" and fx[0]["away"] == "fulham"
    assert fx[0]["ts"] == 1757700000


def test_홈과_원정을_LC로만_가른다():
    """🔴 이름으로 소속을 추측하지 않는다 — 2026 이적을 우리는 모른다."""
    lu = FS.parse_lineup(_LU)
    assert [p["이름"] for p in lu["홈"]["선발"]] == ["Alisson", "Van Dijk V."]
    assert [p["이름"] for p in lu["원정"]["선발"]] == ["Leno B.", "Bassey C."]


def test_이름과_등번호가_같은_블록에서_짝지어진다():
    """🔴 실측된 내 실수 — 키별로 따로 긁으면 순서가 어긋난다."""
    lu = FS.parse_lineup(_LU)
    assert lu["홈"]["선발"][0] == {"이름": "Alisson", "번호": "1"}
    assert lu["원정"]["선발"][1] == {"이름": "Bassey C.", "번호": "3"}


def test_포메이션을_팀별로_읽는다():
    lu = FS.parse_lineup(_LU)
    assert lu["홈"]["포메이션"] == "1-4-2-3-1"
    assert lu["원정"]["포메이션"] == "1-5-4-1"


def test_선발과_교체를_섞지_않는다():
    lu = FS.parse_lineup(_LU)
    assert [p["이름"] for p in lu["홈"]["교체"]] == ["Gakpo C."]
    assert [p["이름"] for p in lu["원정"]["교체"]] == ["King J."]
    assert "Gakpo C." not in [p["이름"] for p in lu["홈"]["선발"]]


def test_킥오프_전이면_빈손이다():
    """⚠️ 1시간 전에야 나온다. 빈 응답에 단정하지 않는다."""
    lu = FS.parse_lineup("")
    assert lu["홈"]["선발"] == [] and lu["원정"]["선발"] == []


def test_경기_매칭은_양팀과_시각_3중이다():
    """🔴 한쪽만 맞으면 버린다 — 남의 경기 라인업은 빈손보다 나쁘다."""
    fx = FS.parse_fixtures(_FIX)
    ts = 1757700000
    assert FS.find_fixture(fx, {"liverpool"}, {"fulham"}, ts) == "YRWOt1od"
    # 원정이 다르다 → 버린다
    assert FS.find_fixture(fx, {"liverpool"}, {"everton"}, ts) is None
    # 시각이 멀다 → 버린다
    assert FS.find_fixture(fx, {"liverpool"}, {"fulham"}, ts + 99999) is None


def test_섹션명_문자열에_기대지_않는다():
    """응답이 러시아어로 온다 — 섹션은 **순서**로 가른다."""
    import inspect

    src = inspect.getsource(FS.parse_lineup)
    for word in ("Стартовые", "Замены", "Тренеры"):
        assert word not in src, word


def test_위성이_라인업을_배선했다():
    """🔴 모듈만 만들고 안 부르면 운영에서는 아무것도 안 바뀐다."""
    import inspect

    from app.collectors import satellite_soccer as SOC

    assert "_fs_lineups" in inspect.getsource(SOC.gather_soccer)
    src = inspect.getsource(SOC._fs_lineups)
    assert "find_fixture" in src          # 3중 매칭을 거친다
    assert "tor_search" not in src and "_tor_supplement" not in src  # 층1 은 직접 HTTP
