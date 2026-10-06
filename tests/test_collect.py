"""수집기 계약 — 🔴 **실물 픽스처로** 검사한다(§16-a-2).

픽스처는 `tests/fixtures/2026-09-27/` 의 **실제 페이지·실제 API 응답**이다.
합성 픽스처는 문자 그대로만 통과한다 — 단계 1 에서 그것 때문에 반려됐다.

수집 대상(실측 2026-09-27):
  MLB statsapi  일정 15경기 · 예고 선발 13/15 · 순위 30팀 · transactions
  npb.jp        일정 5경기 + 양 팀 予告先発 · 헤더 스코어 띠 · 등록 명단(背番号)
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import cells as C
from app.blackboard import (CONTRADICTED, FOUND, UNKNOWN, Blackboard, Fact,
                            reconcile)
from app.collect import mlb, npb
from app.net import Fetched, Net, Search, SearchUnavailable

FIX = Path(__file__).resolve().parent / "fixtures" / "2026-09-27"
KST = timezone(timedelta(hours=9))
DAY = date(2026, 9, 27)


def _fix(name: str) -> Fetched:
    return Fetched(f"file://{name}", True, 200,
                   (FIX / name).read_text(encoding="utf-8"))


# ══════════════════════════════════════════════════════════════════
# MLB — 키 0건 · 검색 0건
# ══════════════════════════════════════════════════════════════════



def test_mlb_토요일_야간이_KST_일요일_아침이다():
    """🔴 §2 · 절대 규칙 2 — MLB 토요일 야간은 **KST 로 일요일 아침**이다.

    ⚠️ 종전 이 계약은 `g["starts_kst"].utcoffset() == +9` 를 쟀다. 🔴 그 오프셋은
       `timestamptz` 에 들어가면 **사라진다**(실측 2026-10-05: 라이브 52행 전부
       `starts_kst = starts_utc`) — 초록인데 아무것도 지키지 않는 계약이었다.
    🔴 지켜야 하는 것은 **날짜가 넘어간다**는 사실이다. 그것은 표시 변환
       (`timefmt`)에서 생기고, 그래서 거기를 센다.
    """
    from app import timefmt
    g = mlb.parse_schedule(_fix("mlb_schedule.json"))[0]
    assert g["starts_utc"].tzinfo is not None
    # 🔴 **같은 순간**이다 — DB 칸이 순간만 담으므로 이것이 참인 전부다
    assert g["starts_kst"] == g["starts_utc"]
    # 🔴🔴 **그래서 날짜가 넘어가는가** — 이것이 §2 가 지키라는 사실이다
    utc, kst = g["starts_utc"].astimezone(timezone.utc), timefmt.kst(g["starts_kst"])
    assert kst.utcoffset() == timedelta(hours=9)
    # 🔴 17:05Z → **다음 날** 02:05 KST. ⚠️ 날짜가 넘어가는 그 한 칸이 §2 다.
    assert kst.date() == utc.date() + timedelta(days=1), (utc, kst)
    assert timefmt.kst_label(g["starts_kst"]) == "09-28 02:05 KST", (
        timefmt.kst_label(g["starts_kst"]))


def test_mlb_예고_선발이_없으면_None이다():
    """🔴 §0-5 — 지어내지 않는다. 실측 13/15 경기만 양쪽이 찼다."""
    games = mlb.parse_schedule(_fix("mlb_schedule.json"))
    both = [g for g in games if all(g["probable"].values())]
    none_ = [g for g in games if not all(g["probable"].values())]
    assert len(both) == 13, len(both)
    assert len(none_) == 2
    for g in none_:
        assert None in g["probable"].values()


def test_mlb_예고_선발에_외부_id가_붙는다():
    """1b — alias 로 이을 수 있어야 한다(이름만으로 매칭하지 않는다)."""
    g = next(g for g in mlb.parse_schedule(_fix("mlb_schedule.json"))
             if all(g["probable"].values()))
    p = g["probable"]["home"]
    assert p["source"] == "statsapi" and p["external_id"].isdigit()
    assert p["name"]


def test_mlb_순위가_동기_재료를_전부_준다():
    """🔴 §3 이 요구하는 칸 — clinched · eliminated · games_back · remaining."""
    facts = mlb.parse_standings(_fix("mlb_standings.json"))
    assert len(facts) == 30, len(facts)
    rows = [f.value for f in facts]
    assert all(r["team"] for r in rows)
    assert all(isinstance(r["remaining"], int) and r["remaining"] >= 0
               for r in rows)
    assert any(r["clinched"] for r in rows), "확정 팀이 0이다"
    assert any(r["eliminated"] for r in rows), "탈락 팀이 0이다"
    assert all(f.hardness == "hard" for f in facts)


# 🔴 v4 §8 폐기로 **동기 등급 계약 2건을 지웠다** — `motivation_tier` 가 없다.
#    다만 순위 **자료**는 v4 §4 유형표의 `standings` 변수 원천으로 남는다.
#    그래서 "확정과 탈락이 동시에 오지 않는가" 같은 **자료 무결성** 계약은 남긴다.


def test_확정_팀은_탈락이_아니다():
    """🔴 실측 2026-09-27 — 양키스가 "진출 확정 · 탈락"으로 동시에 찍혔다.

    `eliminationNumber` 는 **지구** 탈락이고 와일드카드가 따로다. 둘을 뭉개면
    §3 동기 등급이 모순된 입력을 받는다.
    """
    rows = [f.value for f in mlb.parse_standings(_fix("mlb_standings.json"))]
    both = [r for r in rows if r["clinched"] and r["eliminated"]]
    assert both == [], [r["team"] for r in both]
    yankees = next(r for r in rows if "Yankees" in r["team"])
    assert yankees["clinched"] and not yankees["eliminated"]
    assert "지구 탈락" in yankees["note"], yankees["note"]


def test_mlb_잔여가_음수가_되지_않는다():
    """⚠️ 우천 순연으로 162 를 못 채우는 팀이 있다."""
    rows = [f.value for f in mlb.parse_standings(_fix("mlb_standings.json"))]
    assert min(r["remaining"] for r in rows) >= 0




def test_mlb_복귀는_결장이_아니다():
    """`Recalled`·`Activated` 가 결장으로 들어오면 결장 수가 뒤집힌다."""
    raw = json.loads((FIX / "mlb_transactions.json").read_text())
    kinds = {t.get("typeDesc") for t in raw.get("transactions") or []}
    assert kinds, "픽스처에 거래가 0건이다"
    facts = mlb.parse_transactions(_fix("mlb_transactions.json"))
    names = {f.value["note"] for f in facts}
    assert not any("Activated" in n for n in names)


def test_mlb_상태_규약이_우리_것으로_번역된다():
    games = mlb.parse_schedule(_fix("mlb_schedule.json"))
    assert {g["status"] for g in games} <= {
        "scheduled", "inprogress", "final", "postponed", "delayed"}


def test_mlb_URL에_키가_없다():
    """🔴 §14-13 — 유료 키 0건. statsapi 는 키가 필요 없다."""
    for u in (mlb.schedule_url(DAY), mlb.standings_url(2026),
              mlb.transactions_url(DAY)):
        assert "key" not in u.lower() and "token" not in u.lower()
        assert u.startswith("https://statsapi.mlb.com/")


def _code(obj) -> str:
    """독스트링을 뺀 코드만. 🔴 문서가 숫자를 설명하는 것과 코드가 그것을 박는
    것은 다르다(D46)."""
    import ast
    import inspect
    import re as _re
    src = inspect.getsource(obj)
    lines = src.splitlines()
    tree = ast.parse(_re.sub(r"^\s+", "", src.split("\n")[0]) and
                     inspect.cleandoc("") or src) if False else None
    # 함수 첫 독스트링만 지운다 — 들여쓰기 파싱 없이 안전하게
    out, in_doc = [], False
    for ln in lines:
        t = ln.strip()
        if not in_doc and (t.startswith('"""') or t.startswith("r\"\"\"")):
            in_doc = not (t.count('"""') >= 2)
            continue
        if in_doc:
            if '"""' in t:
                in_doc = False
            continue
        out.append(_re.sub(r"#.*", "", ln))
    return "\n".join(out)


def test_mlb_리그_상수가_한_곳이다():
    """🔴 사본 금지 — 162 를 파서 안에 박지 않는다."""
    assert "162" not in _code(mlb.parse_standings)
    assert mlb.GAMES_IN_SEASON == 162


# ══════════════════════════════════════════════════════════════════
# NPB — 실물 HTML
# ══════════════════════════════════════════════════════════════════

def test_npb_일정_5경기를_읽는다():
    games = npb.parse_schedule(_fix("npb_schedule_09.html"), DAY)
    assert len(games) == 5, [g["home"] for g in games]
    assert all(g["league"] == "NPB" for g in games)


def test_npb_예고_선발이_양_팀_다_나온다():
    """실측 — 일정 표에 `先発：小笠原` 꼴로 양쪽이 있다."""
    games = npb.parse_schedule(_fix("npb_schedule_09.html"), DAY)
    assert all(g["probable"]["home"] and g["probable"]["away"]
               for g in games), [g["probable"] for g in games]
    names = {g["probable"]["home"]["name"] for g in games}
    assert "先発" not in "".join(names), "표지를 안 떼고 이름에 넣었다"
    assert "小笠原" in names


def test_npb_약칭을_정식명으로_바꾼다():
    games = npb.parse_schedule(_fix("npb_schedule_09.html"), DAY)
    teams = {g["home"] for g in games} | {g["away"] for g in games}
    assert "巨人" not in teams and "読売ジャイアンツ" in teams


def test_npb_현지와_KST를_둘_다_만든다():
    g = npb.parse_schedule(_fix("npb_schedule_09.html"), DAY)[0]
    assert g["starts_local"].utcoffset() == timedelta(hours=9)
    assert g["starts_kst"] == g["starts_local"].astimezone(KST)
    assert g["starts_utc"].tzinfo is timezone.utc or \
        g["starts_utc"].utcoffset() == timedelta(0)


def test_npb_다른_날짜는_섞이지_않는다():
    """🔴 §14-9 — 요청하지 않은 날짜를 슬레이트에 넣지 않는다.

    픽스처에는 9/28·9/30 행도 들어 있다 — 그것이 섞이면 이 계약이 잡는다.
    """
    got = _fix("npb_schedule_09.html")
    assert 'id="date0930"' in got.text, "픽스처에 대조군이 없다"
    for g in npb.parse_schedule(got, DAY):
        assert g["starts_local"].day == 27, g


def test_npb_예비일은_순연이다():
    """실측 9/30 DeNA-広島 `(予備日)`."""
    games = npb.parse_schedule(_fix("npb_schedule_09.html"), date(2026, 9, 30))
    hit = [g for g in games if g["status"] == "postponed"]
    assert hit and hit[0]["round_note"], games


def test_npb_라이브_상태를_읽는다():
    """헤더 스코어 띠 — 試合終了·N回表 를 우리 규약으로."""
    facts = npb.parse_live(_fix("npb_schedule_09.html"))
    assert len(facts) == 5, len(facts)
    states = {f.value["status"] for f in facts}
    assert states <= {"final", "inprogress", "postponed", "scheduled"}
    assert "final" in states and "inprogress" in states








def test_npb_전출만_결장이다():
    """🔴 전입(←)은 결장이 아니라 보강이다."""
    facts = npb.parse_movement(_fix("npb_registered_h.html"),
                              "福岡ソフトバンクホークス")
    assert facts, "전출 0건이면 이동표를 못 읽은 것이다"
    assert all(f.value["basis"] == "gone" for f in facts)
    names = {f.value["player_name"] for f in facts}
    assert "山本祐大" not in names, "전입을 결장으로 셌다"
    assert "井上朋也" in names, "전출을 놓쳤다"




def test_npb_일일_공시는_미확인으로_적혀_있다():
    """🔴 추측 금지 — URL 을 모르면 모른다고 적는다."""
    assert "미확인" in npb.KOJI_URL_UNKNOWN


# ══════════════════════════════════════════════════════════════════
# §19-c 블랙보드
# ══════════════════════════════════════════════════════════════════

def test_같은_값이면_찾은_것이다():
    bb = Blackboard()
    bb.write(Fact("starter:KT", "배제성", "likely"))
    bb.write(Fact("starter:KT", "배제성", "hard"))
    slot = bb.get("starter:KT")
    assert slot.state == FOUND and slot.value == "배제성"


def test_센_것이_이긴다():
    """🔴 모순 순서 ① hardness."""
    bb = Blackboard()
    bb.write(Fact("starter:KT", "A", "soft"))
    bb.write(Fact("starter:KT", "B", "hard"))
    assert bb.value("starter:KT") == "B"


def test_같은_강도면_최신이_이긴다():
    """🔴 모순 순서 ② published_at."""
    old = datetime(2026, 9, 26, tzinfo=KST)
    new = datetime(2026, 9, 27, tzinfo=KST)
    bb = Blackboard()
    bb.write(Fact("q", "old", "hard", published_at=old))
    bb.write(Fact("q", "new", "hard", published_at=new))
    assert bb.value("q") == "new"


def test_같은_강도_같은_시각이면_인용이_이긴다():
    """🔴 모순 순서 ③ 원문 인용 유무."""
    t = datetime(2026, 9, 27, tzinfo=KST)
    bb = Blackboard()
    bb.write(Fact("q", "무인용", "hard", published_at=t))
    bb.write(Fact("q", "인용", "hard", published_at=t, quote="감독 말"))
    assert bb.value("q") == "인용"


def test_못_정하면_모순으로_둔다():
    """🔴 억지로 하나로 만들지 않는다(§2갈래 규율과 같은 논리)."""
    t = datetime(2026, 9, 27, tzinfo=KST)
    state, reason = reconcile([Fact("q", "A", "hard", published_at=t),
                               Fact("q", "B", "hard", published_at=t)])
    assert state == CONTRADICTED and "다른 값" in reason


def test_unknown에_사유가_붙는다():
    """🔴 §19-b-6 — 검색 0건은 "없음"이 아니다."""
    bb = Blackboard()
    bb.unknown("starter:LG", "西スポ dead · 변형 2회")
    assert bb.get("starter:LG").state == UNKNOWN
    assert bb.unknowns() == [("starter:LG", "西スポ dead · 변형 2회")]


def test_찾은_뒤에는_unknown으로_내려가지_않는다():
    bb = Blackboard()
    bb.write(Fact("q", "값", "hard"))
    bb.unknown("q", "늦게 온 실패")
    assert bb.value("q") == "값"




def test_이미_있는_사실은_즉시_깨운다():
    bb = Blackboard()
    bb.write(Fact("q", 1, "hard"))
    got = []
    bb.subscribe("q", lambda s: got.append(s.value))
    assert got == [1]


def test_unknown도_닫힌_것이다():
    """🔴 §1 — 멈추지 않는다. 의존이 unknown 이어도 다음 세포가 돈다."""
    bb = Blackboard()
    bb.unknown("a", "사유")
    assert bb.ready(["a"]) is True


# ══════════════════════════════════════════════════════════════════
# §19-a/b 세포
# ══════════════════════════════════════════════════════════════════

class _FakeNet(Net):
    def __init__(self, table: dict[str, Fetched]):
        super().__init__()
        self.table = table
        self.asked: list[str] = []

    async def get(self, url, *, params=None, headers=None, **_k):
        # 🔴 **실제 `Net.get` 서명을 따라간다.** 대역이 좁으면 운영이 넓어질 때
        #    `TypeError` 로 터지고, 그 터짐이 "코드 결함"으로 읽힌다
        #    (실측 2026-10-01: 소스별 헤더를 붙이자 15건이 그렇게 빨개졌다).
        self.asked.append(url)
        return self.table.get(url, Fetched(url, False, 404, reason="HTTP 404"))


@pytest.mark.asyncio
async def test_첫_소스가_죽으면_다음으로_넘어간다():
    """🔴 §19-b-4 — 막히면 우회가 아니라 **대체**다. 이 전환이 자동이어야 한다."""
    bb = Blackboard()
    net = _FakeNet({"https://b/ok": Fetched("https://b/ok", True, 200, "x")})
    cell = C.Cell(
        question=C.Question(C.Q_LINEUP, "KT"),
        sources=[
            C.Source("죽은 소스", "url", url="https://a/dead", parse=lambda g, q: []),
            C.Source("산 소스", "url", url="https://b/ok",
                     parse=lambda g, q: [Fact("", "타순 9명", "hard")]),
        ])
    assert await cell.run(net, bb) == FOUND
    assert net.asked == ["https://a/dead", "https://b/ok"]
    assert bb.value("lineup:KT") == "타순 9명"


@pytest.mark.asyncio
async def test_전부_실패하면_unknown이고_사유에_소스가_적힌다():
    bb = Blackboard()
    cell = C.Cell(question=C.Question(C.Q_STARTER_RECENT, "카라스코"),
                  sources=[C.Source("A", "url", url="https://a/x",
                                    parse=lambda g, q: []),
                           C.Source("B", "url", url="https://b/x",
                                    parse=lambda g, q: [])])
    assert await cell.run(_FakeNet({}), bb) == UNKNOWN
    reason = bb.get("starter_recent:카라스코").reason
    assert "A" in reason and "B" in reason and "열기 2/" in reason


@pytest.mark.asyncio
async def test_예산을_넘기면_더_안_두드린다():
    """🔴 §12-d — 세포 하나가 슬레이트 예산을 먹지 않는다."""
    bb = Blackboard()
    net = _FakeNet({})
    cell = C.Cell(question=C.Question(C.Q_LINEUP, "x"),
                  sources=[C.Source(f"S{i}", "url", url=f"https://s{i}/",
                                    parse=lambda g, q: []) for i in range(6)],
                  budget=C.Budget(fetches=2))
    await cell.run(net, bb)
    assert len(net.asked) == 2, net.asked
    assert "예산소진" in bb.get("lineup:x").reason


@pytest.mark.asyncio
async def test_검색_수단이_없으면_그렇게_적는다():
    """🔴 없는 것을 있는 척하지 않는다 — 조용한 0 금지."""
    bb = Blackboard()
    cell = C.Cell(question=C.Question(C.Q_INTENT, "정경호"),
                  sources=[C.Source("검색", "search", query="정경호 인터뷰",
                                    parse=lambda h, q: [])])
    assert await cell.run(_FakeNet({}), bb, search=None) == UNKNOWN
    assert "검색 수단 미정" in bb.get("intent:정경호").reason


@pytest.mark.asyncio
async def test_검색_포트는_예외를_던진다():
    with pytest.raises(SearchUnavailable):
        await Search().query("x")
    assert Search.available is False


@pytest.mark.asyncio


@pytest.mark.asyncio
async def test_파서가_터져도_다음_소스로_간다():
    def _boom(got, q):
        raise ValueError("표 구조 변경")

    bb = Blackboard()
    net = _FakeNet({"https://a/x": Fetched("https://a/x", True, 200, "x"),
                    "https://b/x": Fetched("https://b/x", True, 200, "y")})
    cell = C.Cell(question=C.Question(C.Q_LINEUP, "x"),
                  sources=[C.Source("깨진 파서", "url", url="https://a/x",
                                    parse=_boom),
                           C.Source("정상", "url", url="https://b/x",
                                    parse=lambda g, q: [Fact("", 1, "hard")])])
    assert await cell.run(net, bb) == FOUND


@pytest.mark.asyncio
async def test_사실이_사실을_낳는다():
    """🔴 §19-c — 09-27 휴스턴: 선발 unknown → 반증 세포 → hit → 상향.

    블랙보드 구독으로 그 사슬이 실제로 이어지는지 본다.
    """
    bb = Blackboard()
    chain: list[str] = []
    bb.subscribe("counter:휴스턴 선발", lambda s: chain.append(str(s.value)))
    bb.unknown("starter_recent:휴스턴", "예고 미발표")
    assert bb.get("starter_recent:휴스턴").state == UNKNOWN
    cell = C.Cell(question=C.Question(C.Q_COUNTER, "휴스턴 선발"),
                  deps=["starter_recent:휴스턴"],
                  sources=[C.Source("RotoWire", "url", url="https://r/x",
                                    parse=lambda g, q: [
                                        Fact("", "웨스네스키 3.50", "likely")])])
    net = _FakeNet({"https://r/x": Fetched("https://r/x", True, 200, "x")})
    assert await cell.run(net, bb) == FOUND
    assert chain == ["웨스네스키 3.50"]


# ══════════════════════════════════════════════════════════════════
# §19-d 시간축
# ══════════════════════════════════════════════════════════════════

def test_라인업은_T70분부터_깨어난다():
    t = datetime(2026, 9, 27, 18, 30, tzinfo=KST)
    assert not C.awake(C.Q_LINEUP, t, t - timedelta(minutes=90))
    assert C.awake(C.Q_LINEUP, t, t - timedelta(minutes=70))
    assert C.awake(C.Q_LINEUP, t, t - timedelta(minutes=20))
    assert not C.awake(C.Q_LINEUP, t, t - timedelta(minutes=5))


def test_경기가_시작되면_세포가_끝난다():
    """🔴 §19-d — 채점 세포만 경기 후 깨어난다."""
    t = datetime(2026, 9, 27, 18, 30, tzinfo=KST)
    after = t + timedelta(minutes=1)
    for q in (C.Q_LINEUP, C.Q_ABSENCE, C.Q_STARTER_RECENT, C.Q_INTENT):
        assert not C.awake(q, t, after), q
    assert C.awake(C.Q_LIVE, t, after), "타 구장 라이브는 계속 본다"


def test_아침_세포는_언제나_깨어_있다():
    t = datetime(2026, 9, 27, 18, 30, tzinfo=KST)
    assert C.awake(C.Q_SLATE, t, t - timedelta(hours=11))
    assert C.awake(C.Q_STANDINGS, t, t - timedelta(hours=11))


def test_시간축_원본이_한_곳이다():
    """🔴 사본 금지 — 스케줄러가 이 표를 읽는다."""
    assert set(C.WAKE) == set(C.Q_TYPES)


# ══════════════════════════════════════════════════════════════════
# §19-e 소스 점수표
# ══════════════════════════════════════════════════════════════════

def test_적중률이_높은_소스가_먼저_온다():
    """실측 09-27: 西スポ hit · baseball-data miss."""
    s = C.SourceScores()
    srcs = [C.Source("baseball-data", "url"), C.Source("西スポ", "url")]
    for _ in range(3):
        s.record("baseball-data", C.Q_LINEUP, hit=False)
        s.record("西スポ", C.Q_LINEUP, hit=True, lag_minutes=55)
    order = s.reorder(srcs, C.Question(C.Q_LINEUP, "SB"))
    assert [x.name for x in order] == ["西スポ", "baseball-data"]


def test_모르는_소스는_순서를_안_바꾼다():
    """⚠️ 안정 정렬 — 점수가 없으면 §13 순서 그대로다."""
    s = C.SourceScores()
    srcs = [C.Source("A", "url"), C.Source("B", "url"), C.Source("C", "url")]
    got = s.reorder(srcs, C.Question(C.Q_LINEUP, "x"))
    assert [x.name for x in got] == ["A", "B", "C"]


def test_질문_타입별로_따로_센다():
    s = C.SourceScores()
    s.record("닛칸", C.Q_LINEUP, "NPB", hit=True)
    s.record("닛칸", C.Q_INTENT, "NPB", hit=False)
    assert s.table[("닛칸", C.Q_LINEUP, "NPB")].rate == 1.0
    assert s.table[("닛칸", C.Q_INTENT, "NPB")].rate == 0.0


def test_리그별로_따로_센다():
    """🔴 §19-e 는 `(source, question_type, league)` 셋이다 — `source_score`
    표의 유일키도 셋이다.

    ⚠️ 종전 열쇠는 둘이었다. 그러면 KBO 에서 잘 듣는 매체가 **NPB 순서를 밀어
       올린다** — 매체는 리그마다 다르게 듣는다(§13 소스 지도가 리그별인 이유).
    """
    s = C.SourceScores()
    s.record("스포츠나비", C.Q_LINEUP, "NPB", hit=False)
    s.record("스포츠나비", C.Q_LINEUP, "KBO", hit=True)
    assert s.table[("스포츠나비", C.Q_LINEUP, "NPB")].rate == 0.0
    assert s.table[("스포츠나비", C.Q_LINEUP, "KBO")].rate == 1.0


def test_지연을_못_재면_0이_아니라_None이다():
    """🔴 `source_score.lag_min` 주석: *"못 재면 NULL — 0 으로 때우지 않는다."*

    ⚠️ 종전 `lag` 는 `lag_total / hit` 였다. 마감(T)을 모르는 질문(아침 1회
       순위·슬레이트)은 지연을 **못 재는데도 0분**으로 나왔고, 0분은 "가장
       빠르다"는 뜻이라 `reorder` 가 그 소스를 맨 앞에 세웠다.
    """
    s = C.SourceScores()
    s.record("npb.jp", C.Q_STANDINGS, "NPB", hit=True)          # 마감 없음
    assert s.table[("npb.jp", C.Q_STANDINGS, "NPB")].lag is None
    assert "지연 못 쟀다" in "\n".join(s.report())

    s.record("西スポ", C.Q_LINEUP, "NPB", hit=True, lag_minutes=55)
    assert s.table[("西スポ", C.Q_LINEUP, "NPB")].lag == 55.0


def test_지연을_못_잰_소스를_앞세우지_않는다():
    """🔴 `None` 을 0 으로 읽으면 **한 번도 시간을 못 잰 소스가 1위**가 된다."""
    s = C.SourceScores()
    s.record("잰것", C.Q_LINEUP, "NPB", hit=True, lag_minutes=60)
    s.record("못잰것", C.Q_LINEUP, "NPB", hit=True)        # 적중률은 같다
    srcs = [C.Source("못잰것", "url"), C.Source("잰것", "url")]
    q = C.Question(C.Q_LINEUP, "x", league="NPB")
    assert [x.name for x in s.reorder(srcs, q)] == ["잰것", "못잰것"]


def test_마감이_없으면_지연을_못_잰다():
    """🔴 `lag_minutes` 는 마감(T) 기준이다 — 없으면 **None**, 0 이 아니다."""
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 9, 27, 17, 5, tzinfo=timezone.utc)
    assert C.lag_minutes(C.Question(C.Q_STANDINGS, "NPB")) is None
    q = C.Question(C.Q_LINEUP, "소프트뱅크",
                   deadline=now + timedelta(minutes=55))
    assert C.lag_minutes(q, now) == 55
    # ⚠️ tz 없는 마감으로 빼지 않는다 — KST 를 UTC 로 읽으면 9시간 어긋난다
    assert C.lag_minutes(C.Question(C.Q_LINEUP, "x",
                                    deadline=datetime(2026, 9, 27)), now) is None


def test_점수표는_데이터다():
    """🔴 §19-e — 사람 승인 없이 §13 문서를 바꾸지 않는다. 코드는 순서만 고친다."""
    import inspect
    src = inspect.getsource(C.SourceScores)
    assert "write_text" not in src and "open(" not in src


# ══════════════════════════════════════════════════════════════════
# §19-f 금지·경계
# ══════════════════════════════════════════════════════════════════

def test_UA가_위장하지_않는다():
    """🔴 실사고 D34 — 운영 수집 경로가 브라우저 UA 로 위장했다."""
    from app import net as N
    assert "AnalystBot" in N.UA
    for bad in ("Mozilla", "Chrome", "Safari", "Windows NT"):
        assert bad not in N.UA


def test_프록시_설정이_코드에_없다():
    """🔴 §14-12 — 우회 설계 금지."""
    import inspect
    import re as _re
    src = inspect.getsource(__import__("app.net", fromlist=["x"])).lower()
    # ⚠️ 낱말 경계로 본다 — `factory`·`@property` 안의 글자가 걸리면 거짓 적색이다
    for bad in ("proxies", "proxy", "socks", "tor", "user_agent_spoof"):
        assert not _re.search(rf"\b{bad}\b", src), bad


def test_세포가_판정하지_않는다():
    """🔴 §19-f — lean·확신·등급은 judge.py 다."""
    import inspect
    for mod in (C, __import__("app.blackboard", fromlist=["x"])):
        src = inspect.getsource(mod)
        for bad in ("lean", "confidence", "TIER_", "GO", "grade"):
            assert f"= {bad}" not in src, (mod.__name__, bad)


def test_수집기가_유료_사슬을_안_부른다():
    import inspect
    for mod in (mlb, npb, C, __import__("app.net", fromlist=["x"])):
        src = inspect.getsource(mod).lower()
        for bad in ("anthropic", "perplexity", "pplx", "apifootball",
                    "openrouter", "groq", "api_key", "odds"):
            assert bad not in src, (mod.__name__, bad)


@pytest.mark.asyncio
async def test_robots_거부는_기억하고_다시_안_두드린다():
    calls: list[str] = []

    class _N(Net):
        async def _load_robots(self, host):
            calls.append(host)
            import urllib.robotparser as rp
            p = rp.RobotFileParser()
            p.parse(["User-agent: *", "Disallow: /"])
            return p

    n = _N()
    assert (await n.allowed("https://x.com/a"))[0] is False
    assert (await n.allowed("https://x.com/b"))[0] is False
    assert calls == ["x.com"], "robots 를 두 번 읽었다"
    assert "x.com" in n.dead_hosts


@pytest.mark.asyncio
async def test_robots_자리에_HTML이_오면_제한_없음으로_본다():
    """실측 2026-09-27 — npb.jp 가 robots.txt 자리에 사이트 HTML 을 준다."""
    class _N(Net):
        async def _load_robots(self, host):
            return await Net._load_robots(self, host)

    import httpx

    class _R:
        status_code = 200
        text = "<!DOCTYPE html>\n<html lang='ja'><head>"

    n = Net()

    async def _fake_get(self, url, **kw):
        return _R()

    orig = httpx.AsyncClient.get
    httpx.AsyncClient.get = _fake_get
    try:
        assert await n._load_robots("npb.jp") is None
    finally:
        httpx.AsyncClient.get = orig


# ══════════════════════════════════════════════════════════════════
# 🔴 한 소스가 여러 주체를 낼 때 — 실사고 2026-09-27
# ══════════════════════════════════════════════════════════════════

def test_순위는_팀마다_다른_질문이다():
    """🔴 실사고 — 30팀을 한 질문에 묶어 **전부 모순으로** 판정됐다.

    계약이 값 하나짜리 대역이라 못 잡았고, 실물을 돌려서야 보였다.
    """
    facts = mlb.parse_standings(_fix("mlb_standings.json"))
    ids = {f.question_id for f in facts}
    assert len(ids) == 30, f"질문이 {len(ids)}개로 뭉쳤다"
    assert all(i.startswith("standings:MLB:") for i in ids)


def test_라이브도_경기마다_다른_질문이다():
    facts = npb.parse_live(_fix("npb_schedule_09.html"))
    assert len({f.question_id for f in facts}) == 5


@pytest.mark.asyncio
async def test_세포가_파서의_질문_id를_덮지_않는다():
    """🔴 덮어쓰면 한 소스의 여러 주체가 한 질문에 몰린다."""
    bb = Blackboard()
    net = _FakeNet({"https://x/": Fetched("https://x/", True, 200, "x")})
    cell = C.Cell(question=C.Question(C.Q_STANDINGS, "MLB"),
                  sources=[C.Source("S", "url", url="https://x/",
                                    parse=lambda g, q: [
                                        Fact("standings:MLB:A", 1, "hard"),
                                        Fact("standings:MLB:B", 2, "hard")])])
    await cell.run(net, bb)
    assert bb.value("standings:MLB:A") == 1
    assert bb.value("standings:MLB:B") == 2
    assert bb.contradictions() == []


@pytest.mark.asyncio
async def test_질문_id가_비면_세포가_채운다():
    """⚠️ 반대 위험 — 파서가 안 정했으면 세포가 채워야 한다."""
    bb = Blackboard()
    net = _FakeNet({"https://x/": Fetched("https://x/", True, 200, "x")})
    cell = C.Cell(question=C.Question(C.Q_LINEUP, "KT"),
                  sources=[C.Source("S", "url", url="https://x/",
                                    parse=lambda g, q: [Fact("", "9명", "hard")])])
    await cell.run(net, bb)
    assert bb.value("lineup:KT") == "9명"


@pytest.mark.asyncio


def test_모든_파서가_Fact를_낸다():
    """★ 배선 — 소스에 붙은 파서가 `Fact` 아닌 것을 내면 세포가 터진다."""
    got_sched = _fix("mlb_schedule.json")
    got_npb = _fix("npb_schedule_09.html")
    q = C.Question(C.Q_SLATE, "x")
    for srcs, got in ((mlb.sources_slate(DAY), got_sched),
                      (mlb.sources_standings(2026),
                       _fix("mlb_standings.json")),
                      (mlb.sources_transactions(DAY),
                       _fix("mlb_transactions.json")),
                      (npb.sources_slate(DAY), got_npb),
                      (npb.sources_live(DAY), got_npb)):
        for src in srcs:
            out = src.parse(got, q)
            assert isinstance(out, list), src.name
            assert all(isinstance(f, Fact) for f in out), src.name


# ══════════════════════════════════════════════════════════════════
# §19-b-3 검증기가 루프 안에 있다
# ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_기사_소스는_검증기를_통과해야_한다():
    """🔴 §19-b-3 — 날짜를 못 읽는 기사는 **거부**다(fail-closed)."""
    bb = Blackboard()
    net = _FakeNet({"https://n/x": Fetched("https://n/x", True, 200, "x")})
    cell = C.Cell(question=C.Question(C.Q_INTENT, "감독"),
                  sources=[C.Source("기사", "url", url="https://n/x", tier=2,
                                    verify=True,
                                    parse=lambda g, q: [
                                        Fact("", "총력전", "hard")])])
    assert await cell.run(net, bb) == UNKNOWN
    assert any("검증거부" in t for t in cell.tried), cell.tried
    assert "발행 시각" in bb.get("intent:감독").reason or \
        "검증거부" in bb.get("intent:감독").reason


@pytest.mark.asyncio
async def test_경기_후_기사는_거부된다():
    """🔴 §12-c-2 — **기사**가 경기 후 것이면 거부한다.

    ⚠️ 종전 판은 경기 후 문구를 사실의 **값**에 넣었다(`Fact("", "3-5 역전승")`).
       그것이 통과한 이유는 `_verified` 가 **값을 기사 제목인 양** 검증기에 넘겨서다 —
       즉 이 계약은 **결함을 잠그고 있었다**(실사고 2026-09-30, 단계 4 측정).
    🔴 §12-c-2 가 보는 것은 **기사**다. 그래서 `article_title` 에 넣는다.
    """
    from datetime import datetime as _dt
    bb = Blackboard()
    net = _FakeNet({"https://n/x": Fetched("https://n/x", True, 200, "x")})
    now = _dt.now(KST)
    cell = C.Cell(question=C.Question(C.Q_INTENT, "x"),
                  sources=[C.Source("기사", "url", url="https://n/x", tier=2,
                                    verify=True,
                                    parse=lambda g, q: [
                                        Fact("", "감독 인용", "hard",
                                             published_at=now,
                                             article_title="3-5 역전승")])])
    assert await cell.run(net, bb) == UNKNOWN
    assert any("post_game" in t for t in cell.tried), cell.tried


@pytest.mark.asyncio
async def test_사실의_값을_기사로_검사하지_않는다():
    """🔴 **실사고 2026-09-30.** 검증기에 **우리가 뽑은 값**을 넘기면 안 된다.

    감독 교체 사실 `{'since': '2026-09-26', …}` 의 `09-26` 이 **스코어 9-26** 으로
    읽혀 *"제목에 스코어가 있다"* → **경기 후 기사로 판정되어 거부**됐다.
    §9 필수 8건 ① 의 자료를 찾아 놓고 그렇게 떨어뜨렸다.

    🔴 더 나쁜 것: 그 말은 **§12-c-2 가 기사에 적용된 적이 없다**는 뜻이었다.
    """
    from datetime import datetime as _dt
    bb = Blackboard()
    net = _FakeNet({"https://n/y": Fetched("https://n/y", True, 200, "x")})
    now = _dt.now(KST)
    # 🔴 값에 날짜가 있고(스코어처럼 보인다) 기사는 멀쩡하다 → **통과해야 한다**
    value = {"coach": "Ramaz Svanadze", "since": "2026-09-26",
             "days_before_game": 2}
    cell = C.Cell(question=C.Question(C.Q_INTENT, "y"),
                  sources=[C.Source("기사", "url", url="https://n/y", tier=2,
                                    verify=True,
                                    parse=lambda g, q: [
                                        Fact("", value, "hard",
                                             published_at=now,
                                             article_title="조지아 감독 스바나제 부임")])])
    state = await cell.run(net, bb)
    assert state == FOUND, cell.tried
    assert not any("post_game" in t for t in cell.tried), cell.tried


@pytest.mark.asyncio
async def test_공식_소스는_검증기를_안_거친다():
    """🔴 §12-c-5 — 공식 API 는 발행 시각이 없다. 그것을 거부하면 아무것도 못 쓴다."""
    bb = Blackboard()
    net = _FakeNet({"https://o/x": Fetched("https://o/x", True, 200, "x")})
    cell = C.Cell(question=C.Question(C.Q_SLATE, "MLB"),
                  sources=[C.Source("공식", "url", url="https://o/x", tier=1,
                                    verify=False,
                                    parse=lambda g, q: [Fact("", [1], "hard")])])
    assert await cell.run(net, bb) == FOUND


@pytest.mark.asyncio
async def test_통과한_기사는_층에_맞게_약해진다():
    """🔴 프리뷰 사이트는 soft 다 — hard 로 들어오면 확신이 부풀어 오른다."""
    from datetime import datetime as _dt
    bb = Blackboard()
    net = _FakeNet({"https://p/x": Fetched("https://p/x", True, 200, "x")})
    cell = C.Cell(question=C.Question(C.Q_LINEUP, "x"),
                  sources=[C.Source("프리뷰", "url", url="https://p/x",
                                    tier=3, verify=True,
                                    parse=lambda g, q: [
                                        Fact("", "라인업", "hard",
                                             published_at=_dt.now(KST))])])
    st = await cell.run(net, bb)
    assert st == UNKNOWN, "프리뷰가 판정 입력으로 통과했다"
    assert any("tier" in t for t in cell.tried), cell.tried


def test_우리_소스가_층을_밝힌다():
    """★ 공식은 1층이어야 한다 — 층을 안 적으면 기본 2층이 되어 검증이 어긋난다."""
    for srcs in (mlb.sources_slate(DAY), mlb.sources_standings(2026),
                 mlb.sources_transactions(DAY), npb.sources_slate(DAY),
                 npb.sources_live(DAY)):
        for s in srcs:
            assert s.tier == 1, s.name
            assert s.verify is False, f"{s.name}: 공식인데 기사 검증을 건다"


@pytest.mark.asyncio
async def test_자료가_왔는데_못_뽑으면_그렇게_적는다():
    """🔴 실사고 2026-09-27 — 검색 31건을 받고 파서가 0건을 냈는데 사유가
    "시도 0건"이었다. **거짓이다.** 어느 쪽인지 모르면 파서를 고칠지 소스를
    바꿀지 판단할 수 없다.
    """
    bb = Blackboard()
    net = _FakeNet({"https://x/": Fetched("https://x/", True, 200, "본문")})
    cell = C.Cell(question=C.Question(C.Q_COUNTER, "x"),
                  sources=[C.Source("소스", "url", url="https://x/",
                                    parse=lambda g, q: [])])
    assert await cell.run(net, bb) == UNKNOWN
    assert any("사실 0건(파서)" in t for t in cell.tried), cell.tried
    assert "시도 0건" not in bb.get("counter:x").reason


@pytest.mark.asyncio
async def test_자료가_아예_안_오면_그렇게_적는다():
    """⚠️ 반대 — 소스가 죽은 것은 파서 문제가 아니다."""
    bb = Blackboard()
    cell = C.Cell(question=C.Question(C.Q_COUNTER, "y"),
                  sources=[C.Source("소스", "url", url="https://dead/",
                                    parse=lambda g, q: [])])
    await cell.run(_FakeNet({}), bb)
    assert any("HTTP 404" in t for t in cell.tried), cell.tried
    assert not any("파서" in t for t in cell.tried)
