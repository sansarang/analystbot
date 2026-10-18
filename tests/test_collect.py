"""수집기 계약 — 🔴 **실물 픽스처로** 검사한다(§16-a-2).

픽스처는 `tests/fixtures/2026-09-27/` 의 **실제 페이지·실제 API 응답**이다.
합성 픽스처는 문자 그대로만 통과한다 — 단계 1 에서 그것 때문에 반려됐다.

수집 대상(실측 2026-09-27):
  MLB statsapi  일정 15경기 · 예고 선발 13/15 · 순위 30팀 · transactions
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import cells as C
from app.blackboard import (CONTRADICTED, FOUND, UNKNOWN, Blackboard, Fact,
                            reconcile)
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
