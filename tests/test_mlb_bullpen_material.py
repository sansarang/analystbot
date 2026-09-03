"""[v1.3 B-1 집행] MLB 자료9(불펜)가 세 리그 대칭으로 실제 조립되는가.

🔴 설계는 "자료9 세 리그 대칭"인데, 2026-09-03 아침 MLB 카드가 두 장 연속
   "불펜 자료(자료9)가 없어 선발 조기 강판 시 불펜 싸움 변수를 반영하지
   못함"이라고 적었다. 조사 결과 **코드는 정상이고 판정이 코드보다
   74분 빨랐다** — 수집기(`5cd2ba8`, 09-03 08:59 KST)가 태어나기 전에
   그날 슬레이트 판정이 끝나 있었다.

   버그가 아니었다는 것이 "다음에도 괜찮다"는 뜻은 아니다. 이 경로가
   조용히 끊기면 카드가 또 같은 말을 하고, 우리는 또 로그를 뒤진다.
   끊기는 지점 셋을 각각 잠근다.

⚠️ 라이브 호출은 하지 않는다 — statsapi 응답 모양만 그대로 흉내낸다.
"""
import pytest

from app.collectors import mlb_team_pitching as MTP
from app.engine.matchup import bullpen_payload

#: statsapi `/teams/stats?group=pitching` 실응답 발췌 (2026-09-03 실측 형태).
FAKE = {"stats": [{"splits": [
    {"team": {"name": "Los Angeles Dodgers"},
     "stat": {"era": "3.68", "whip": "1.16",
              "strikeoutsPer9Inn": "9.28", "walksPer9Inn": "3.15"}},
    {"team": {"name": "St. Louis Cardinals"},
     "stat": {"era": "4.24", "whip": "1.34",
              "strikeoutsPer9Inn": "7.93", "walksPer9Inn": "3.41"}},
]}]}


@pytest.fixture(autouse=True)
def _no_cache():
    MTP._mem.clear()
    yield
    MTP._mem.clear()


def _unmock(monkeypatch):
    """`FORCE_MOCK` 만 내린다. 밖으로 나가는 호출은 호출부가 따로 막는다."""
    import app.config as CFG

    real = CFG.get_settings()

    class _S:
        force_mock = False

        def __getattr__(self, k):
            return getattr(real, k)

    monkeypatch.setattr(CFG, "get_settings", lambda: _S())


class _Client:
    def __init__(self, *a, **k):
        pass

    async def get(self, path, params):
        assert path == "/teams/stats"
        assert params["group"] == "pitching"
        return FAKE


@pytest.fixture
def _stub(monkeypatch):
    """statsapi 를 가짜로 갈고, `FORCE_MOCK` 만 이 테스트에서 내린다.

    ⚠️ conftest 가 `FORCE_MOCK=true` 를 걸어 두면 `fetch()` 가 첫 줄에서
       빈 dict 를 돌려주고 끝난다 — 조립 경로를 한 줄도 못 밟는다.
       **밖으로 나가는 호출은 `_Client` 가 막고**, 목 플래그만 내린다.
    """
    import app.collectors.starter_season as SS
    import app.config as CFG

    monkeypatch.setattr(SS, "StatsAPIClient", _Client)
    _unmock(monkeypatch)


@pytest.mark.asyncio
async def test_mlb_bullpen_reaches_material_9(_stub):
    """🔴 이 테스트가 이 파일의 목적이다 — 조립 결과에 자료9가 있는가."""
    jg = {"sport": "mlb", "game_id": 1,
          "home": "Los Angeles Dodgers", "away": "St. Louis Cardinals"}
    assert await MTP.attach(jg, season=2026) == 2
    pay = bullpen_payload(jg)
    assert set(pay) == {"home", "away"}, "자료9 가 비었다 — MLB 만 칸이 빈다"
    assert pay["home"]["era"] == 3.68 and pay["away"]["era"] == 4.24


@pytest.mark.asyncio
async def test_team_names_match_the_games_table_form(_stub):
    """수집 팀명이 `games` 의 팀명과 **같은 표기**여야 붙는다.

    이름이 한 글자만 달라도 조용히 안 붙는다 — 실패가 아니라 빈 칸으로
    나타나서 알아채기 어렵다. 실측 2026-09-03: statsapi 30팀과 `games`
    30팀이 완전 일치했고, 붙지 않던 원인은 이름이 아니었다.
    """
    table = await MTP.fetch(2026)
    jg = {"sport": "mlb", "game_id": 1,
          "home": "Los Angeles Dodgers", "away": "St. Louis Cardinals"}
    for side in ("home", "away"):
        assert jg[side] in table, f"{jg[side]} 가 수집 표에 없다"


@pytest.mark.asyncio
async def test_other_sports_are_untouched(_stub):
    """KBO·NPB 는 자기 수집기가 채운다 — 이 수집기가 끼어들지 않는다."""
    jg = {"sport": "kbo", "game_id": 2, "home": "LG", "away": "KIA"}
    assert await MTP.attach(jg, season=2026) == 0
    assert bullpen_payload(jg) == {}


@pytest.mark.asyncio
async def test_existing_bullpen_is_not_overwritten(_stub):
    """이미 다른 소스가 채웠으면 덮지 않는다 — `setdefault` 계약."""
    jg = {"sport": "mlb", "game_id": 3,
          "home": "Los Angeles Dodgers", "away": "St. Louis Cardinals",
          "research": {"home_bullpen": {"era": 1.11, "roster": ["기존"]}}}
    await MTP.attach(jg, season=2026)
    assert jg["research"]["home_bullpen"]["era"] == 1.11
    assert jg["research"]["home_bullpen"]["roster"] == ["기존"]
    assert jg["research"]["away_bullpen"]["era"] == 4.24


@pytest.mark.asyncio
async def test_collection_failure_does_not_block_judgement(monkeypatch):
    """수집이 죽어도 판정은 간다 — 자료9 는 있으면 좋은 것이지 관문이 아니다."""
    class Dead:
        def __init__(self, *a, **k):
            pass

        async def get(self, *a, **k):
            raise RuntimeError("statsapi down")

    import app.collectors.starter_season as SS

    monkeypatch.setattr(SS, "StatsAPIClient", Dead)
    _unmock(monkeypatch)          # 목 모드면 Dead 를 부르지도 않는다
    jg = {"sport": "mlb", "game_id": 4,
          "home": "Los Angeles Dodgers", "away": "St. Louis Cardinals"}
    assert await MTP.attach(jg, season=2026) == 0     # 예외가 새지 않는다
    assert bullpen_payload(jg) == {}


def test_call_site_is_on_the_shared_baseball_path():
    """호출부가 **세 리그 공용** 경로에 있어야 한다.

    감시 3층은 아시아 사이클에만 붙어 있다가 MLB 를 통째로 빠뜨렸다
    (2026-09-03). 같은 실수를 재료 쪽에서 반복하지 않는다.
    """
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    seg = src[src.index("async def _run_baseball_matchups"):]
    seg = seg[:seg.index("\nasync def ", 1)] if "\nasync def " in seg[1:] else seg
    assert "mlb_team_pitching" in seg, \
        "자료9 수집이 야구 공용 경로 밖에 있다 — MLB 가 조용히 빠질 수 있다"


def test_mlb_freeze_counter_starts_after_the_bullpen_deploy():
    """[동결 기준] MLB N/50 은 **자료9 주입 개시 이후** 슬레이트부터 센다.

    자료9 가 붙기 전 판정과 붙은 뒤 판정은 재료가 다르다. 같은 표본에
    넣으면 50건을 채워도 무엇의 성적인지 알 수 없다.
    KBO·NPB 는 영향이 없다 — 두 리그는 이미 자료9 를 갖고 있었다.
    """
    from app.engine.daily_summary import freeze_start

    # ⚠️ [C3 2026-09-04] 자료10·변수 명세 개정으로 **3리그 모두** 표본을 다시
    #    센다(§5). MLB 만 따로 두던 기준은 그 안에 흡수됐다 — 09-03 기준이
    #    남아 있으면 자료10 없이 내린 판정이 같은 표본에 섞인다.
    assert freeze_start("mlb") == freeze_start("kbo") == freeze_start("npb")
    assert freeze_start("mlb") == "2026-09-04"
