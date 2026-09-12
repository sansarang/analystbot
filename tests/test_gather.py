"""ORD-10 (1단계) — 질문 없이 경기 것만 긁는다.

사용자 지시 2026-09-12: "갈림길 변수등을 서치로 지정하지 않고 경기에 대한
것만 서치해 온다...그후 ai에게 정보를 준다.ai가 거른다"

🔴 왜: 질문에 매인 수집이 셋으로 샜다(실측 2026-09-12).
     퍼플렉시티 경기당 최대 4콜 → 429 발생
     X 는 질답 강요로 같은 프롬프트 5회에 답 [0,0,1,0,1]
     `xsearch.fetch_for_game`(질문 없는 속보 수집기)이 놀고 있었다

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
async def test_네_채널을_모두_부른다(monkeypatch):
    seen = []

    def mk(tag):
        async def f(*a, **k):
            seen.append(tag)
            return [G._row(tag, src=tag)]
        return f

    _patch(monkeypatch, _satellite=mk("satellite"), _x_news=mk("x"),
           _preview=mk("pplx"), _bullpen=mk("크롤러"))
    out = await G.collect(_jg(), None, "2026-09-12")
    assert sorted(seen) == ["pplx", "satellite", "x", "크롤러"]
    assert out["출처"] == {"satellite": 1, "x": 1, "pplx": 1, "크롤러": 1}


@pytest.mark.asyncio
async def test_한_채널이_터져도_나머지가_산다(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("터졌다")

    _patch(monkeypatch, _satellite=boom, _x_news=_none, _preview=_none,
           _bullpen=lambda *a, **k: _ok())

    async def _ok():
        return [G._row("불펜", src="크롤러")]

    out = await G.collect(_jg(), None, "2026-09-12")
    assert out["출처"] == {"크롤러": 1}


@pytest.mark.asyncio
async def test_0건이면_0건이라고_돌려준다(monkeypatch):
    """🔴 빈손을 숨기면 ②가 아는 척 거른다."""
    _patch(monkeypatch, _satellite=_none, _x_news=_none, _preview=_none,
           _bullpen=_none)
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

def test_X_는_기존_속보_수집기를_쓴다():
    """🔴 ORD-8 에서 질답 틀을 씌운 것이 잘못이었다. 프롬프트·URL 검증·캡의
    원본은 `collectors/xsearch` 다."""
    import inspect

    src = inspect.getsource(G._x_news)
    assert "fetch_for_game" in src
    assert "X_ASK" not in src and "질문" not in src.split('"""')[2]


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

@pytest.mark.asyncio
async def test_X_항목을_버리지_않는다(monkeypatch):
    """🔴 실측 2026-09-12: `xsearch` 가 NPB 4건·2건을 적재했는데 수집 출처에
    `x` 가 없었다. `parse_items` 가 `headline` 을 **`title` 로 바꿔** 돌려주는데
    내가 `headline` 으로 읽었다. 수집기는 성공했고 우리가 못 읽었다."""
    import app.collectors.xsearch as XS

    async def _f(jg, date, redis=None, settings=None):
        return [{"title": "선발 예고 잭로그", "url": "https://x.com/i/status/1",
                 "at": "2026-09-11T12:00", "account": "@doosanbears1982",
                 "source": "xsearch"}]

    monkeypatch.setattr(XS, "fetch_for_game", _f)
    out = await G._x_news(_jg(), "2026-09-12", None)
    assert len(out) == 1
    assert out[0]["답"] == "선발 예고 잭로그"
    assert out[0]["계정"] == "@doosanbears1982"
    assert out[0]["시점"] == "2026-09-11"


def test_X_키를_손으로_적지_않았는지_대조한다():
    """🔴 `parse_items` 가 실제로 내는 키와 맞는지 **그 함수로** 확인한다.
    이름을 손으로 옮겨 적으면 그것이 미래의 오탐이다(사본 금지)."""
    import inspect

    from app.collectors.xsearch import parse_items

    produced = parse_items(
        '[{"headline":"h","url":"https://x.com/1","at":"2026-09-11T12:00",'
        '"account":"@a"}]')
    assert produced, "파서가 항목을 내야 이 계약이 성립한다"
    keys = set(produced[0])
    src = inspect.getsource(G._x_news)
    for k in ("title", "url", "at", "account"):
        assert k in keys, f"parse_items 가 {k} 를 더 이상 내지 않는다"
        assert f'"{k}"' in src, f"_x_news 가 {k} 를 읽지 않는다"
    assert '"headline"' not in src, "parse_items 는 headline 을 내지 않는다"


class _Redis:
    def __init__(self, store=None):
        self.store = dict(store or {})
        self.sets = []

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, ex=None, nx=False):
        if nx and k in self.store:
            return False
        self.store[k] = v
        self.sets.append(k)
        return True


@pytest.mark.asyncio
async def test_X_는_캐시를_먼저_읽는다(monkeypatch):
    """🔴 실측 2026-09-12: `xsearch` 는 경기당 1콜인데 **결과를 저장하지
    않았다.** 스케줄러가 낮에 소진해 판정 시점 수집이 KBO·NPB 전부 X 0건이
    됐다. 먼저 쏜 쪽이 채우고 나머지는 읽는다 — 캡은 우회하지 않는다."""
    import json as _json

    import app.collectors.xsearch as XS

    fired = {"n": 0}

    async def _f(jg, date, redis=None, settings=None):
        fired["n"] += 1
        return []

    monkeypatch.setattr(XS, "fetch_for_game", _f)
    key = XS._ITEMS_KEY.format(sport="kbo", game_id=1737, date="2026-09-12")
    r = _Redis({key: _json.dumps([{"title": "선발 예고", "url": "u",
                                   "at": "2026-09-11T12:00", "account": "@a"}])})
    out = await G._x_news(_jg(), "2026-09-12", r)
    assert [x["답"] for x in out] == ["선발 예고"]
    assert fired["n"] == 0, "캐시가 있으면 다시 쏘지 않는다"


@pytest.mark.asyncio
async def test_캐시가_비면_쏜다(monkeypatch):
    import app.collectors.xsearch as XS

    async def _f(jg, date, redis=None, settings=None):
        return [{"title": "새 속보", "url": "u", "at": "2026-09-12T09:00",
                 "account": "@b"}]

    monkeypatch.setattr(XS, "fetch_for_game", _f)
    out = await G._x_news(_jg(), "2026-09-12", _Redis())
    assert [x["답"] for x in out] == ["새 속보"]


@pytest.mark.asyncio
async def test_쏜_결과를_저장한다():
    """다음 호출부가 읽을 수 있어야 한다."""
    import app.collectors.xsearch as XS

    r = _Redis()
    items = [{"title": "t", "url": "u", "at": "2026-09-12T09:00"}]
    await XS._store(r, "kbo", 1737, "2026-09-12", items)
    got = await XS.load_cache(r, "kbo", 1737, "2026-09-12")
    assert got == items


@pytest.mark.asyncio
async def test_빈_결과는_저장하지_않는다():
    """🔴 빈손을 캐시하면 나중에 진짜 결과가 와도 못 읽는다."""
    import app.collectors.xsearch as XS

    r = _Redis()
    await XS._store(r, "kbo", 1737, "2026-09-12", [])
    assert r.sets == []


@pytest.mark.asyncio
async def test_캐시가_깨져도_죽지_않는다():
    import app.collectors.xsearch as XS

    key = XS._ITEMS_KEY.format(sport="kbo", game_id=1, date="d")
    assert await XS.load_cache(_Redis({key: "{망가진"}), "kbo", 1, "d") == []


def test_1콜_캡을_우회하지_않는다():
    """🔴 우회하면 요금 방어가 사라진다."""
    import inspect

    src = inspect.getsource(G._x_news)
    assert "_once_ok" not in src and "_ONCE_KEY" not in src
    assert "fetch_for_game" in src
