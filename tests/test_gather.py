"""ORD-10 (1단계) — 질문 없이 경기 것만 긁는다.

사용자 지시 2026-09-12: "갈림길 변수등을 서치로 지정하지 않고 경기에 대한
것만 서치해 온다...그후 ai에게 정보를 준다.ai가 거른다"

🔴 왜: 질문에 매인 수집이 셋으로 샜다(실측 2026-09-12).
     퍼플렉시티 경기당 최대 4콜 → 429 발생
     X 는 질답 강요로 같은 프롬프트 5회에 답 [0,0,1,0,1]
     질문 없는 속보 수집기가 놀고 있었다

⚠️ 이 단계는 잡음을 줄이지 않는다 — 거르는 일은 ②(2단계)다. 합격 기준은
   "적게 가져오기"가 아니라 "빠뜨리지 않고 출처·시각을 붙여 가져오기"다.
"""

import pytest

from app.engine import gather as G


def _jg():
    return {"game_id": 1737, "sport": "kbo", "league": "KBO",
            "home": "Doosan Bears", "away": "NC Dinos"}


def _patch(monkeypatch, **kw):
    for name, fn in kw.items():
        monkeypatch.setattr(G, name, fn)


async def _none(*a, **k):
    return []


# ═══════════════ ① 네 채널을 다 부른다

@pytest.mark.asyncio
async def test_무료_채널만_부른다(monkeypatch):
    seen = []

    def mk(tag):
        async def f(*a, **k):
            seen.append(tag)
            return [G._row(tag, src=tag)]
        return f

    # 🔴 [ORD-21] pplx·X 는 여기서 빠졌다 — 2차 검증관이 요청할 때만 쓴다.
    #    "퍼플릭스와 x seach는 안트로픽 api키가 요청을 할때만 켜는걸로 하자."
    #    실측 2026-09-12: x_search 호출당 $0.413. 위성·크롤러만으로도 갈림길이
    #    나왔다("문보경이 지명타자로 복귀해…").
    _patch(monkeypatch, _satellite=mk("satellite"),
           _preview=mk("pplx"), _lineup=mk("라인업"), _bullpen=mk("크롤러"))
    out = await G.collect(_jg(), None, "2026-09-12")
    assert sorted(seen) == ["satellite", "라인업", "크롤러"]
    assert "pplx" not in seen and "x" not in seen, "유료 검색은 안 부른다"
    assert out["출처"] == {"satellite": 1, "라인업": 1, "크롤러": 1}


@pytest.mark.asyncio
async def test_한_채널이_터져도_나머지가_산다(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("터졌다")

    _patch(monkeypatch, _satellite=boom, _preview=_none,
           _lineup=_none, _bullpen=lambda *a, **k: _ok())

    async def _ok():
        return [G._row("불펜", src="크롤러")]

    out = await G.collect(_jg(), None, "2026-09-12")
    assert out["출처"] == {"크롤러": 1}


@pytest.mark.asyncio
async def test_0건이면_0건이라고_돌려준다(monkeypatch):
    """🔴 빈손을 숨기면 ②가 아는 척 거른다."""
    _patch(monkeypatch, _satellite=_none, _preview=_none,
           _lineup=_none, _bullpen=_none)
    out = await G.collect(_jg(), None, "2026-09-12")
    assert out == {"자료": [], "출처": {}}


def test_채널별_건수를_로그에_남긴다():
    """🔴 ORD-8 에서 배운 것 — 중간 수치가 없으면 "왜 0건인가"를 다시 묻는다."""
    import inspect

    assert "수집 %d건 %s" in inspect.getsource(G.collect)


# ═══════════════ ② 행 모양은 기존 계약 그대로

def test_행_모양이_기존_자료와_같다():
    """🔴 새 계약을 만들지 않는다 — 카드·결론이 그대로 읽어야 한다."""
    r = G._row("x", src="pplx")
    for k in ("질문", "답", "소스", "소스유형", "시점", "계정", "url"):
        assert k in r, k
    assert r["질문"] == "", "질문 없는 수집이다"


# ═══════════════ ③ 질문을 만들지 않는다

def test_프리뷰는_질문_목록이_아니다():
    assert "질문 목록은 없다" in G.PREVIEW_ASK
    assert "{questions}" not in G.PREVIEW_ASK


def test_프리뷰가_성적을_금지한다():
    """🔴 ORD-5 실측: 조사요청 38문 중 28문(74%)이 성적 조회였다."""
    assert "성적을 가져오지 마라" in G.PREVIEW_ASK
    for banned in ("평균자책점", "팀 타율", "OPS", "게임로그", "통산 전적"):
        assert banned in G.PREVIEW_ASK, banned


def test_프리뷰가_변수_축을_준다():
    for axis in ("부상", "말소", "투구수 제한", "연투", "지붕 개폐", "라인업"):
        assert axis in G.PREVIEW_ASK, axis


def test_없으면_적게_가져오라고_한다():
    """🔴 채우려고 일반론을 쓰면 ②의 부담만 는다."""
    assert "없으면 없는 대로 적게 가져와라" in G.PREVIEW_ASK


# ═══════════════ ④ 이미 있는 것을 다시 만들지 않는다

def test_위성_상한을_새로_정하지_않는다():
    """원본은 `deepsearch.MAX_SAT`(ORD-3) 이다."""
    from app.engine.deepsearch import MAX_SAT

    assert G.MAX_SAT is MAX_SAT


def test_불펜_문장은_크롤러_모듈이_만든다():
    import inspect

    src = inspect.getsource(G._bullpen)
    assert "bullpen_usage" in src and "to_answer" in src
    assert "이닝" not in src, "문장을 여기서 다시 조립하면 사본이다"


@pytest.mark.asyncio
async def test_불펜은_질문을_기다리지_않는다(monkeypatch):
    """🔴 ORD-7 은 ①이 물었을 때만 답했다. 이제 질문이 없으므로 항상 붙인다."""
    import app.collectors.bullpen_usage as BU

    async def _recent(pool, sport, team, **k):
        return {"투수": [], "마지막적재": None}

    monkeypatch.setattr(BU, "recent", _recent)
    monkeypatch.setattr(BU, "to_answer", lambda t, d, **k: f"{t} 불펜")
    out = await G._bullpen(None, _jg())
    assert [r["답"] for r in out] == ["NC Dinos 불펜", "Doosan Bears 불펜"]


# ═══════════════ ⑤ 위성은 최신순 (ORD-3 규약)

@pytest.mark.asyncio
async def test_위성은_최신순으로_자른다(monkeypatch):
    import app.collectors.satellite as SAT

    old = [{"title": f"old{i}", "body": "", "url": "", "age_h": 500.0 + i}
           for i in range(G.MAX_SAT)]

    async def _rc(redis, sport, gid):
        return old + [{"title": "오늘 복귀", "body": "", "url": "", "age_h": 3.0}]

    monkeypatch.setattr(SAT, "read_cache", _rc)
    out = await G._satellite(_jg(), None)
    assert any(r["답"] == "오늘 복귀" for r in out)
    assert len(out) == G.MAX_SAT


@pytest.mark.asyncio
async def test_위성_제목과_본문을_두_번_싣지_않는다(monkeypatch):
    import app.collectors.satellite as SAT

    same = "Brewers activated RHP Abner Uribe from the 15-day IL."

    async def _rc(redis, sport, gid):
        return [{"title": same, "body": same, "url": "", "age_h": 3.0}]

    monkeypatch.setattr(SAT, "read_cache", _rc)
    out = await G._satellite(_jg(), None)
    assert out[0]["답"] == same


# ═══════════════ ⑥ 실측이 잡은 것 (2026-09-12 1단계 리허설)

# ═══════════════ ⑦ ORD-14 — 크롤러 라인업·선발도 수집이다

def _cf_patch(monkeypatch, snap=None, changes=None, lp=None, state="none"):
    import app.collectors.crawler_feed as CF
    import app.engine.matchup as MU

    async def _ls(redis, sport, date):
        return snap or {}

    async def _lc(redis, sport, date, limit=50):
        return changes or []

    monkeypatch.setattr(CF, "load_snapshot", _ls)
    monkeypatch.setattr(CF, "load_changes", _lc)
    monkeypatch.setattr(MU, "lineups_payload", lambda jg: lp or {})


@pytest.mark.asyncio
async def test_선발_예고를_수집에_싣는다(monkeypatch):
    """🔴 3단계 실측 2026-09-12: 네 경기 전부 `없는것` 이
    ['선발 최근 등판', '오늘 타순'] 이었고 확신이 4/4 `하` 로 깔렸다.
    그런데 그 둘은 우리가 이미 10분마다 긁고 있었다."""
    _cf_patch(monkeypatch, lp={"away": {"선발투수": "구창모"},
                               "home": {"선발투수": "잭로그"}})
    out = await G._lineup(_jg(), None, "2026-09-12")
    answers = [r["답"] for r in out]
    assert "원정 선발 예고 — 구창모" in answers
    assert "홈 선발 예고 — 잭로그" in answers
    assert {r["소스"] for r in out} == {"라인업"}


@pytest.mark.asyncio
async def test_타순을_순번과_함께_싣는다(monkeypatch):
    _cf_patch(monkeypatch, lp={"away": {"선발투수": "구창모",
                                        "타순": [{"순번": 1, "이름": "김주원"},
                                                {"순번": 2, "이름": "권희동"}]},
                               "home": {"선발투수": "잭로그"}})
    out = await G._lineup(_jg(), None, "2026-09-12")
    line = next(r["답"] for r in out if "오늘 타순 —" in r["답"])
    assert "1김주원" in line and "2권희동" in line


@pytest.mark.asyncio
async def test_타순_미확정도_사실로_적는다(monkeypatch):
    """🔴 잠정 카드가 왜 잠정인지를 ②가 알아야 한다. 조용히 빠뜨리면
    "타순을 모른다"는 것조차 모른다."""
    _cf_patch(monkeypatch, lp={"away": {}, "home": {}})
    out = await G._lineup(_jg(), None, "2026-09-12")
    assert any("타순 상태 — none (확정 전)" in r["답"] for r in out)


@pytest.mark.asyncio
async def test_타순이_확정이면_상태줄을_안_낸다(monkeypatch):
    _cf_patch(monkeypatch, lp={"away": {}, "home": {}})
    jg = _jg(); jg["lineup_status"] = "confirmed"
    out = await G._lineup(jg, None, "2026-09-12")
    assert not any("확정 전" in r["답"] for r in out)


@pytest.mark.asyncio
async def test_선발이_없으면_미정이라_쓴다(monkeypatch):
    """🔴 없는 것을 지어내지 않는다."""
    _cf_patch(monkeypatch, lp={"away": {}, "home": {}})
    out = await G._lineup(_jg(), None, "2026-09-12")
    assert any(r["답"] == "원정 선발 예고 — 미정" for r in out)


@pytest.mark.asyncio
async def test_언제_바뀌었는지를_싣는다(monkeypatch):
    """🔴 "18:05 에 4번 타자가 빠졌다"는 그 자체로 신호다 —
    스냅샷 하나만 보는 구조로는 영원히 못 본다(`lineup_timeline` 머리말)."""
    import app.collectors.crawler_feed as CF

    _cf_patch(monkeypatch, lp={"away": {}, "home": {}})
    monkeypatch.setattr(CF, "lineup_timeline", lambda ch, jg: {
        "lineup_announced_at": "17:05",
        "lineup_changes": ["18:05 홈 라인업 변경"],
        "starter_changes": ["16:40 원정 선발 A → B"]})
    out = await G._lineup(_jg(), None, "2026-09-12")
    answers = [r["답"] for r in out]
    assert "라인업 발표 시각 — 17:05" in answers
    assert "18:05 홈 라인업 변경" in answers
    assert "16:40 원정 선발 A → B" in answers


@pytest.mark.asyncio
async def test_크롤러가_죽어도_수집은_계속된다(monkeypatch):
    import app.collectors.crawler_feed as CF
    import app.engine.matchup as MU

    async def boom(*a, **k):
        raise RuntimeError("터졌다")

    monkeypatch.setattr(CF, "load_snapshot", boom)
    monkeypatch.setattr(CF, "load_changes", boom)
    monkeypatch.setattr(MU, "lineups_payload", lambda jg: {"away": {"선발투수": "A"}})
    out = await G._lineup(_jg(), None, "2026-09-12")
    assert any("선발 예고 — A" in r["답"] for r in out)


@pytest.mark.asyncio
async def test_수집이_라인업_채널을_부른다(monkeypatch):
    seen = []

    def mk(tag):
        async def f(*a, **k):
            seen.append(tag)
            return []
        return f

    _patch(monkeypatch, _satellite=mk("s"), _preview=mk("p"),
           _lineup=mk("라인업"), _bullpen=mk("b"))
    await G.collect(_jg(), None, "2026-09-12")
    assert "라인업" in seen


def test_외부_호출이_없다():
    """🔴 크롤러가 이미 긁어 둔 것을 읽을 뿐이다."""
    import inspect

    src = inspect.getsource(G._lineup)
    for banned in ("httpx", "fetch_for_game", "ask_json", "GrokClient"):
        assert banned not in src, banned


def test_조립을_다시_하지_않는다():
    """원본은 `crawler_feed` 와 `matchup.lineups_payload` 다."""
    import inspect

    src = inspect.getsource(G._lineup)
    assert "crawler_feed" in src and "lineups_payload" in src
    assert "snapshot_keys_for" not in src, "더블헤더 키 처리는 crawler_feed 것이다"


def test_카드가_출처를_밝힌다():
    from app.engine.form_card import _SRC_KR

    assert _SRC_KR["라인업"] == "크롤러·공시"


# ═══════════════ ⑧ ORD-16 — 크롤러 선발로 jg 를 메운다

@pytest.mark.asyncio
async def test_빈_선발을_크롤러로_메운다(monkeypatch):
    """🔴 실측 2026-09-12 13:14: 크롤러는 정상이었고(KBO 4·NPB 6경기, 선발
    이름 전부 있음) games 테이블만 NULL 이었다. `games.home_pitcher` 를 쓰는
    코드가 KBO·NPB 에 없다 — MLB 만 채운다."""
    import app.collectors.crawler_feed as CF

    async def _ls(redis, sport, date):
        return {"x": {}}

    monkeypatch.setattr(CF, "load_snapshot", _ls)
    monkeypatch.setattr(CF, "snapshot_for_game",
                        lambda snap, jg: {"home_pitcher": "후라도",
                                          "away_pitcher": "톨허스트"})
    jg = _jg()
    filled = await G.enrich(jg, None, "2026-09-12")
    assert jg["home_pitcher"] == "후라도" and jg["away_pitcher"] == "톨허스트"
    assert len(filled) == 2


@pytest.mark.asyncio
async def test_이미_있으면_덮지_않는다(monkeypatch):
    """🔴 MLB 는 statsapi 예고 선발이 이미 차 있다 — 덮으면 더 나빠질 수 있다."""
    import app.collectors.crawler_feed as CF

    async def _ls(redis, sport, date):
        return {"x": {}}

    monkeypatch.setattr(CF, "load_snapshot", _ls)
    monkeypatch.setattr(CF, "snapshot_for_game",
                        lambda snap, jg: {"home_pitcher": "크롤러값"})
    jg = _jg(); jg["home_pitcher"] = "Shota Imanaga"
    await G.enrich(jg, None, "2026-09-12")
    assert jg["home_pitcher"] == "Shota Imanaga"


@pytest.mark.asyncio
async def test_스냅샷이_터져도_수집은_계속된다(monkeypatch):
    import app.collectors.crawler_feed as CF

    async def boom(*a, **k):
        raise RuntimeError("터졌다")

    monkeypatch.setattr(CF, "load_snapshot", boom)
    jg = _jg()
    assert await G.enrich(jg, None, "2026-09-12") == []
    assert "home_pitcher" not in jg


@pytest.mark.asyncio
async def test_수집이_메우기를_먼저_한다(monkeypatch):
    """🔴 호출 순서가 계약이다 — 반대면 game_brief 가 '미정' 을 낸다."""
    order = []

    async def _e(jg, redis, date):
        order.append("enrich")
        return []

    async def _mk(*a, **k):
        order.append("channel")
        return []

    monkeypatch.setattr(G, "enrich", _e)
    _patch(monkeypatch, _satellite=_mk, _preview=_mk,
           _lineup=_mk, _bullpen=_mk)
    await G.collect(_jg(), None, "2026-09-12")
    assert order[0] == "enrich"


def test_game_brief_는_안_바꿨다():
    """🔴 선발 우선순위 규약의 원본은 `matchup._starter`(ORD-3) 다.
    이 수정은 그 함수를 바꾸지 않고 **입력을 채울 뿐이다.**"""
    import inspect

    from app.engine import matchup as MU

    src = inspect.getsource(MU._starter)
    assert "crawler" not in src and "gather" not in src


# ══════════ SRCH-1 — X 채널을 지웠다

def test_X_채널이_사라졌다():
    """🔴 사용자 지시 2026-09-12 "x seach 삭제". 실측: 호출당 $0.413 에
    본문 수율 0. 그 자리는 Anthropic 웹 검색이 받는다(경기당 $0.102)."""
    assert not hasattr(G, "_x_news")


@pytest.mark.asyncio
async def test_수집은_무료_채널만_부른다(monkeypatch):
    """🔴 **수집에서 유료 호출이 나가면 안 된다.** 요청받았을 때만 검색한다
    (사용자 지시 "안트로픽 api키가 요청을 할때만 켜는걸로 하자").
    ⚠️ 채널 이름을 손으로 적지 않는다 — `collect` 가 실제로 부른 것을 센다."""
    called = []

    def mk(tag):
        async def _f(*a, **k):
            called.append(tag)
            return []
        return _f

    _patch(monkeypatch, _satellite=mk("satellite"), _preview=mk("pplx"),
           _lineup=mk("라인업"), _bullpen=mk("크롤러"),
           enrich=mk("enrich"))
    await G.collect(_jg(), None, "2026-09-12")
    assert "pplx" not in called, "수집이 퍼플렉시티를 불렀다"
    assert set(called) == {"enrich", "satellite", "라인업", "크롤러"}, called
