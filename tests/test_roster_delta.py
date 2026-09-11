"""ROS-1 — KBO 공시를 '상태'가 아니라 **'사건'**으로 만든다.

🔴 왜. DSM-1 기준선(2026-09-11 운영 실측): 위성 재료 **76건 중 조사 인용 0건**.
   모인 것은 굿즈 기사·타팀 FA 전망이었다. 그런데 `kbo_roster` 머리말은 이미
   답을 적어 놨다 —
     "KBO는 **말소로 결장을 알린다** … 이건 산문이 아니라 공식 명단이고,
      공개돼 있으며, 파싱하면 끝난다."
   우리는 그 명단의 **지금 상태**만 알았고 **오늘 빠졌다**는 변화를 몰랐다.
   스냅샷 수명이 6시간이라 어제 것이 안 남았기 때문이다.

🔴 MLB 는 `statsapi/transactions` 로 이미 **사건**을 받는다(위성 25~62건).
   그 축을 KBO 에 맞추는 것이 이 수정이다.

⚠️ 결장 판정 경로(`load`·`absent_regulars`·`merge_into_research`)는 **불변**이다.
   그쪽은 야수 전용이 맞다 — 결장 대상이 타석 상위 9명이기 때문이다.
"""

import json

import pytest

from app.collectors import kbo_roster as KR


class _Redis:
    def __init__(self, store=None):
        self.store = dict(store or {})

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, val, ex=None):
        self.store[key] = val
        return True


def _snap(date, table):
    return {KR.FULL_KEY.format(date=date):
            json.dumps({k: sorted(v) for k, v in table.items()},
                       ensure_ascii=False)}


# ═══════════════ ① 델타 = 사건

@pytest.mark.asyncio
async def test_말소와_등록을_가른다():
    r = _Redis({**_snap("2026-09-10", {"Samsung Lions": {"가", "나", "다"}}),
                **_snap("2026-09-11", {"Samsung Lions": {"가", "라"}})})
    d = await KR.roster_delta(r, "2026-09-11")
    assert d["기준"] == "2026-09-10" and d["사유"] is None
    assert d["팀"]["Samsung Lions"] == {"말소": ["나", "다"], "등록": ["라"]}


@pytest.mark.asyncio
async def test_변화가_없으면_그_팀은_안_나온다():
    r = _Redis({**_snap("2026-09-10", {"A": {"가"}}),
                **_snap("2026-09-11", {"A": {"가"}})})
    assert (await KR.roster_delta(r, "2026-09-11"))["팀"] == {}


@pytest.mark.asyncio
async def test_어제가_없으면_며칠_거슬러_본다():
    """휴식일·수집 실패를 건너뛴다."""
    r = _Redis({**_snap("2026-09-08", {"A": {"가", "나"}}),
                **_snap("2026-09-11", {"A": {"가"}})})
    d = await KR.roster_delta(r, "2026-09-11")
    assert d["기준"] == "2026-09-08"
    assert d["팀"]["A"]["말소"] == ["나"]


# ═══════════════ ② 모르는 것을 "없다"고 하지 않는다

@pytest.mark.asyncio
async def test_비교할_스냅샷이_없으면_사유를_남긴다():
    """🔴 빈 목록을 '변화 없음'으로 적으면 '모른다'와 '없다'가 같아진다."""
    r = _Redis(_snap("2026-09-11", {"A": {"가"}}))
    d = await KR.roster_delta(r, "2026-09-11")
    assert d["팀"] == {} and d["기준"] is None
    assert "스냅샷이 없" in d["사유"]


@pytest.mark.asyncio
async def test_오늘_스냅샷이_없어도_사유를_남긴다():
    d = await KR.roster_delta(_Redis(), "2026-09-11")
    assert d["사유"] and d["팀"] == {}


@pytest.mark.asyncio
async def test_어제_없던_팀은_건너뛴다():
    """그 팀은 어제 자료가 없다 — 전원 등록으로 만들면 거짓 사건이 된다."""
    r = _Redis({**_snap("2026-09-10", {"A": {"가"}}),
                **_snap("2026-09-11", {"A": {"가"}, "B": {"나", "다"}})})
    assert "B" not in (await KR.roster_delta(r, "2026-09-11"))["팀"]


# ═══════════════ ③ 재료로 나간다

def test_사건이_있는_팀만_기사가_된다():
    delta = {"기준": "2026-09-10", "사유": None,
             "팀": {"Samsung Lions": {"말소": ["나"], "등록": []}}}
    arts = KR.delta_articles(delta, ["Samsung Lions", "Kiwoom Heroes"])
    assert len(arts) == 1
    a = arts[0]
    assert a["team"] == "Samsung Lions"
    assert "말소" in a["title"] and "나" in a["title"]
    assert "출전할 수 없다" in a["body"]


def test_소스가_공식임이_드러난다():
    """🔴 DS-14 뒤집기는 `공식|기록` 을 요구한다. 오늘 발견은 100% 뉴스였다."""
    delta = {"기준": "2026-09-10", "사유": None, "팀": {"A": {"말소": ["가"]}}}
    a = KR.delta_articles(delta, ["A"])[0]
    assert "공시" in a["source"] and a["source"].startswith("KBO")
    assert a["title"].startswith("[공시]")


def test_변화가_없으면_기사도_없다():
    """프롬프트를 '변화 없음'으로 채우지 않는다 — 정보가 아니라 잡음이다."""
    assert KR.delta_articles({"기준": "x", "팀": {}}, ["A"]) == []


def test_기사_모양이_주입_계약을_지킨다():
    """원본은 `satellite._article` 이다 — 키를 손으로 늘리지 않는다."""
    delta = {"기준": "2026-09-10", "사유": None, "팀": {"A": {"말소": ["가"]}}}
    a = KR.delta_articles(delta, ["A"])[0]
    for k in ("title", "url", "source", "team", "body"):
        assert k in a, k


# ═══════════════ ④ 투수까지 본다

def test_전포지션_파서에_투수가_있다():
    """🔴 실측 2026-09-11: 갈림길 8/8·변수 15/17 이 투수였는데,
    투수 이탈을 알려 줄 공시 경로가 없었다."""
    assert "투수" in KR.ALL_COLUMNS
    for c in KR.BATTER_COLUMNS:
        assert c in KR.ALL_COLUMNS


def test_기본_파서는_종전대로_야수만_본다():
    """결장 판정은 타석 상위 9명이 대상이다 — 그 경로를 바꾸지 않았다."""
    import inspect

    sig = inspect.signature(KR.parse_registered)
    assert sig.parameters["columns"].default == KR.BATTER_COLUMNS


def test_스냅샷은_하루를_넘겨_산다():
    assert KR.FULL_TTL > 24 * 3600
    assert KR.CACHE_TTL == 6 * 3600, "결장 판정용 키의 수명을 바꾸지 않았다"


# ═══════════════ ⑤ 위성 배선

@pytest.mark.asyncio
async def test_위성이_공시를_맨_앞에_붙인다(monkeypatch):
    """검색 기사보다 공식이 먼저다 — 주입 번호 1번이 공시여야 한다."""
    import app.collectors.satellite as SAT

    async def _fake_adapter(jg, client=None, now=None):
        return [{"title": "뉴스", "url": "u", "source": "다음뉴스",
                 "team": "A", "body": "b"}]

    monkeypatch.setitem(SAT._ADAPTERS, "kbo", _fake_adapter)

    async def _official(jg, redis):
        return [{"title": "[공시] A 1군 엔트리 변동", "url": "k",
                 "source": "KBO 공시(전체 등록 현황)", "team": "A", "body": "b"}]

    # ⚠️ `raising=False` — 수정 전 코드에는 `_kbo_official` 이 없다. 여기서
    #    AttributeError 로 죽으면 "심볼이 없다"로 실패하고, 정작 **결함 자체를
    #    겨눈 단언**(공시가 재료에 안 들어간다)에 닿지 못한다.
    monkeypatch.setattr(SAT, "_kbo_official", _official, raising=False)
    r = _Redis()
    n = await SAT.gather({"sport": "kbo", "game_id": 1, "home": "A", "away": "B"}, r)
    assert n == 2
    items = json.loads(r.store[SAT._cache_key("kbo", 1)])["items"]
    assert items[0]["title"].startswith("[공시]")


@pytest.mark.asyncio
async def test_공시_실패가_위성을_막지_않는다(monkeypatch):
    import app.collectors.satellite as SAT

    async def _boom(redis, date):
        raise RuntimeError("터졌다")

    monkeypatch.setattr(KR, "roster_delta", _boom)
    assert await SAT._kbo_official({"home": "A", "away": "B"}, _Redis()) == []
