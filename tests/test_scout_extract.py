"""SCT-5·SCT-10·EXT-1 — 위성이 긁은 본문을 4-4 스키마로 추출한다.

🔴 실측 결함들이 이 파일을 만들었다:
   · 2026-09-14 추출 호출부가 0 이었다(SCT-5)
   · 목록 앞 3건만 읽어 tier1/2 현지 기사를 놓쳤다(SCT-10)
   · 팀별 3건 = **경기당 6콜** 이 groq 무료 한도를 태웠다
     (429 백오프 340~467초) → **경기당 1콜 + 창 + URL 해시 캐시**(EXT-1)

⚠️ 주력 채널(다음·야후)에는 tier 선별을 걸지 않는다 — 그 도메인은 표에 없다.
"""
import json

import pytest

from app.collectors import satellite as SAT
from app.engine import scout_config as SC

# 🔴 [BIG-2] 추출은 **빅매치에만** 돈다 — 더비 대진으로 잰다
#    (순위를 몰라도 더비면 빅매치다).
HOME, AWAY = "AC Milan", "FC Internazionale Milano"


def _art(team, url, body="본문"):
    return {"team": team, "url": url, "body": body}


def _fake(payload, calls=None):
    async def _f(routes, prompt, max_tokens, role):
        assert role == "form", "구조화 출력은 추론을 끄고 부른다"
        if calls is not None:
            calls.append(prompt)
        return json.dumps(payload, ensure_ascii=False)
    return _f


def _two_teams(home_out=("Casadei",), away_out=()):
    return {"teams": [
        {"team": HOME, "out": list(home_out), "xi_status": "predicted",
         "notes": "중원 결장", "전적": "버려야 한다"},
        {"team": AWAY, "out": list(away_out), "xi_status": "official"},
    ]}


@pytest.mark.asyncio
async def test_경기당_한_번만_묻는다(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr("app.engine.team_form._complete_free",
                        _fake(_two_teams(), calls))

    out = await SAT.extract_game_facts(
        [_art(HOME, "https://www.gazzetta.it/a"),
         _art(AWAY, "https://www.fantacalcio.it/b"),
         _art(HOME, "https://www.romatoday.it/c")],
        home=HOME, away=AWAY, league="serie_a")

    assert len(calls) == 1, "기사 3건·팀 2개라도 호출은 한 번이다"
    assert out["home"]["out"] == ["Casadei"] and out["away"]["xi_status"] == "official"
    assert "전적" not in out["home"], "스키마 밖은 버린다"


@pytest.mark.asyncio
async def test_기사_전문_대신_창만_넣는다(monkeypatch):
    calls: list[str] = []
    body = "머리말 " * 400 + " Casadei out injury " + " 꼬리말 " * 400
    monkeypatch.setattr("app.engine.team_form._complete_free",
                        _fake(_two_teams(), calls))

    await SAT.extract_game_facts([_art(HOME, "https://www.gazzetta.it/a", body)],
                                 home=HOME, away=AWAY, league="serie_a")

    sent = calls[0]
    assert "Casadei out injury" in sent, "단서 주변은 남긴다"
    assert len(sent) < len(body), "전문을 넣지 않는다"
    assert SAT.WINDOW_SPAN == 300


def test_단서가_없으면_머리만_준다():
    """🔴 빈손으로 부르면 "읽었는데 없다"와 "안 읽었다"가 같아진다."""
    w = SAT._windows("가" * 5000, ("Torino",))
    assert len(w) == SAT.WINDOW_SPAN * 2


@pytest.mark.asyncio
async def test_같은_URL_묶음이면_다시_묻지_않는다(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr("app.engine.team_form._complete_free",
                        _fake(_two_teams(), calls))

    class _R:
        def __init__(self):
            self.kv = {}

        async def get(self, k):
            return self.kv.get(k)

        async def set(self, k, v, ex=None):
            self.kv[k] = v

    r = _R()
    arts = [_art(HOME, "https://www.gazzetta.it/a")]
    first = await SAT.extract_game_facts(arts, home=HOME, away=AWAY,
                                         league="serie_a", redis=r)
    second = await SAT.extract_game_facts(arts, home=HOME, away=AWAY,
                                          league="serie_a", redis=r)

    assert len(calls) == 1, "두 번째는 캐시가 답한다"
    assert first == second
    assert list(r.kv)[0].startswith("scout:x:")


@pytest.mark.asyncio
async def test_등급_순으로_읽는다(monkeypatch):
    """🔴 수집 순서는 층1→다음→RSS 다. 앞에서 자르면 tier1/2 가 늘 잘린다."""
    calls: list[str] = []
    monkeypatch.setattr("app.engine.team_form._complete_free",
                        _fake(_two_teams(), calls))

    await SAT.extract_game_facts(
        [_art(HOME, "https://www.transfermarkt.com/x"),
         _art(HOME, "http://v.daum.net/v/1"),
         _art(HOME, "http://v.daum.net/v/2"),
         _art(HOME, "https://www.teleradiostereo.it/a"),
         _art(AWAY, "https://www.fantacalcio.it/b")],
        home=HOME, away=AWAY, league="serie_a")

    sent = calls[0]
    assert "teleradiostereo.it" in sent and "fantacalcio.it" in sent
    assert SC.FETCH_PER_STAGE == 3


@pytest.mark.asyncio
async def test_본문이_없으면_부르지_않는다(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr("app.engine.team_form._complete_free",
                        _fake(_two_teams(), calls))

    out = await SAT.extract_game_facts([_art(HOME, "https://x.it/a", body="")],
                                       home=HOME, away=AWAY, league="serie_a")

    assert out == {} and not calls


@pytest.mark.asyncio
async def test_추출은_기사와_다른_키에_남는다():
    class _R:
        def __init__(self):
            self.kv = {}

        async def set(self, k, v, ex=None):
            self.kv[k] = v

        async def get(self, k):
            return self.kv.get(k)

    r = _R()
    await SAT._write_extract(r, "soccer", 7432, {"home": {"team": "A"}})

    assert list(r.kv) == ["scout:soccer:7432"]
    assert SAT._cache_key("soccer", 7432) not in r.kv, "기사 캐시를 덮으면 안 된다"
    back = await SAT.read_extract(r, "soccer", 7432)
    assert back["teams"]["home"]["team"] == "A"
    assert await SAT.read_extract(r, "soccer", 9999) == {}


@pytest.mark.asyncio
async def test_야구도_모은_기사에서_추출한다(monkeypatch):
    """🔴 [PA-12 2026-09-16 사용자 지시 "위성수집으로 하면 되잖아"] 뒤집힌 계약.

    종전(SCT-5)은 `test_야구는_추출하지_않는다` 였다 — "4-4 스키마는 축구 칸이라
    야구에 억지로 채우면 거짓 재료가 된다."

    그 규칙의 대가가 실측으로 드러났다(2026-09-16): 야구가 기사 **35건을 모으고
    추출 0회** 였고, 원장 g8773 의 need 5개가 **전부 '미상'** 이었다. 가설을
    세우고 아무것도 확인하지 못한 채 판정하고 있었다.

    ⚠️ SCT-5 의 걱정은 여기서 사라진 것이 아니라 **다른 곳이 막고 있다** —
       추출 스키마에 타순·등판 칸이 아예 없어 LLM 이 만들 자리가 없다.
       `test_pa12_baseball_extract.py::test_추출_스키마에_타순_등판이_없다` 가
       그 방어선을 지킨다. 야구 가설이 요구하는 칸은 out·doubt·last3 셋뿐이고
       전부 공용 칸이다.
    """
    called = []

    async def _ex(*a, **k):
        called.append(1)
        return {"home": {"team": "x"}}

    async def _adapter(jg, client=None, now=None):
        return [{"team": "Mariners", "body": "b", "url": "u"}]

    monkeypatch.setattr(SAT, "extract_game_facts", _ex)
    monkeypatch.setitem(SAT._ADAPTERS, "mlb", _adapter)

    n = await SAT.gather({"sport": "mlb", "game_id": 1, "home": "Mariners",
                          "away": "A", "league": "MLB"}, None)

    assert n == 1 and called, "기사를 모으고도 추출을 안 했다"


# ── FOT-4: out·xi 는 JSON 정본, LLM 은 보조

def _fm(un_home=None, starters=None, lineup_type="predicted", diff=None):
    return {"lineup_type": lineup_type,
            "home": {"starters": starters or [], "unavailable": un_home},
            "away": {"starters": [], "unavailable": None},
            "diff": diff or {}}


@pytest.mark.asyncio
async def test_out_은_JSON_이_정본이고_LLM_과_다르면_충돌이다(monkeypatch):
    """🔴 사용자 지시: LLM 이 out 을 돌려줘도 JSON 과 다르면 JSON 채택 + conflict."""
    monkeypatch.setattr("app.engine.team_form._complete_free",
                        _fake({"teams": [
                            {"team": HOME, "out": ["지어낸 선수"],
                             "notes": "중원 결장", "midweek": "UCL 목요일"},
                            {"team": AWAY, "out": []}]}))
    jg = {"rank_home": 1, "rank_away": 2, "fotmob": _fm(un_home=[{"name": "Ché Adams"}],
                        starters=[{"id": 1, "name": "Perri"}])}

    out = await SAT.extract_game_facts([_art(HOME, "https://www.gazzetta.it/a")],
                                       home=HOME, away=AWAY, league="serie_a", jg=jg)

    h = out["home"]
    assert h["out"] == ["Ché Adams"] and h["out_src"] == "fotmob"
    assert h["conflict"] is True
    assert h["out_llm"] == ["지어낸 선수"], "LLM 값을 버리지 않는다(왜 달랐는지 남긴다)"
    assert h["xi"] == ["Perri"] and h["xi_status"] == "predicted"
    # 보조 칸은 LLM 것이 그대로 산다.
    assert h["notes"] == "중원 결장" and h["midweek"] == "UCL 목요일"


@pytest.mark.asyncio
async def test_JSON_이_없으면_종전대로_LLM_을_쓴다(monkeypatch):
    monkeypatch.setattr("app.engine.team_form._complete_free",
                        _fake({"teams": [{"team": HOME, "out": ["A"]},
                                         {"team": AWAY, "out": []}]}))

    out = await SAT.extract_game_facts([_art(HOME, "https://www.gazzetta.it/a")],
                                       home=HOME, away=AWAY, league="serie_a")

    assert out["home"]["out"] == ["A"] and out["home"]["out_src"] == "llm"


@pytest.mark.asyncio
async def test_bench_notable_은_코드가_채운다(monkeypatch):
    """🔴 LLM 자기보고가 아니라 예상→공식 diff 다(지시문 4-4)."""
    monkeypatch.setattr("app.engine.team_form._complete_free",
                        _fake({"teams": [{"team": HOME, "bench_notable": ["엉뚱한 값"]},
                                         {"team": AWAY}]}))
    jg = {"rank_home": 1, "rank_away": 2, "fotmob": _fm(lineup_type="confirmed",
                        diff={"home": {"bench_notable": ["Simeone"],
                                       "surprise_in": ["Ngonge"]}})}

    out = await SAT.extract_game_facts([_art(HOME, "https://www.gazzetta.it/a")],
                                       home=HOME, away=AWAY, league="serie_a", jg=jg)

    assert out["home"]["bench_notable"] == ["Simeone"]
    assert out["home"]["surprise_in"] == ["Ngonge"]
