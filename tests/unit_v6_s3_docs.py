"""🔴🔴 **v6 §7 단위 — s3 문서 수집의 규칙들.**

지시서 §5 s3 가 요구한 것을 **돌려서** 센다(글자 검사 금지 · §9).

⚠️ 실사고 2026-10-06 이 전부 이 단계에 있었다:
   · 유형 이름(`absence_def`)을 질의에 넣어 *"Overdrive 라디오 프로그램"* 문단
   · 상위 3건이 전부 못 열리면 **문서 0건**(실패를 대체하지 않았다)
   · 본문과 날짜를 따로 저장해 `date_missing` 20건
   · 어깻점(`O'Neill`)이 문지기에 걸려 그 유형이 구조적으로 0건
"""
from __future__ import annotations

import asyncio
import datetime as dt

from app.core.schema import Facts, MatchRef
from app.core.stages import s3_docs as S3
from app.core.state import RunState

UTC = dt.timezone.utc


def _ref(**kw) -> MatchRef:
    box = dict(id="fotmob:1", sport="soccer",
               competition="CONCACAF Nations League A Grp. 2",
               competition_short="CONCACAF Nations League",
               home="team:000103", away="team:000119",
               home_name="Honduras", away_name="Jamaica",
               kickoff_utc=dt.datetime(2026, 10, 7, 2, tzinfo=UTC),
               langs=["en", "es"])
    box.update(kw)
    return MatchRef(**box)


class _Sub:
    """🔴 하위 과제 그림자 — `subtasks.Budget` 과 같은 칸만 쓴다."""

    def __init__(self, kinds, *, name="A-홈", key="team:000103"):
        self.name, self.kinds, self.team_key = name, tuple(kinds), key
        self.budget = _Bud()


class _Bud:
    def __init__(self):
        self.search_cap = self.fetch_cap = 3
        self.search_used = self.fetch_used = 0

    def may_search(self):
        return self.search_used < self.search_cap

    def may_fetch(self):
        return self.fetch_used < self.fetch_cap


class _Hit:
    def __init__(self, url, title="t", snippet="s"):
        self.url, self.title, self.snippet = url, title, snippet
        self.published_at = None
        self.lang = "en"


class _Chain:
    def __init__(self, hits):
        self.hits, self.asked = hits, []

    async def query(self, text, *, lang="en", engines=None, qtype=None):
        self.asked.append((text, lang))
        return list(self.hits)


class _Net:
    """🔴 `ok=False` 를 섞어 **실패 대체**를 센다."""

    HTML = ("<html><body><article><p>Conor Bradley is unavailable for "
            "Honduras because of a hamstring injury picked up last week in "
            "training with the national team squad.</p></article></body></html>")

    def __init__(self, bad: set[str] | None = None, when: str = "2026-10-05"):
        self.bad, self.when, self.got = bad or set(), when, []

    async def get(self, url):
        from app.net import Fetched
        self.got.append(url)
        if url in self.bad:
            return Fetched(url, False, 403, "")
        meta = (f'<meta property="article:published_time" '
                f'content="{self.when}T09:00:00+00:00">')
        return Fetched(url, True, 200,
                       f"<html><head>{meta}</head>{self.HTML}</html>")


# ══════════════════════════════════════════════════════════════════
# ① 질의 — 개념 낱말이고, 유형 이름이 아니다
# ══════════════════════════════════════════════════════════════════

def test_질의에_유형_이름이_안_들어간다():
    got = S3.queries_for(_Sub(["absence_def", "absence_att"]), _ref())
    assert got, got
    joined = " ".join(q for q, _l in got)
    for bad in ("absence_def", "absence_att", "def_absence"):
        assert bad not in joined, (
            f"🔴 **유형 이름**이 질의에 들어갔다({bad}) — 기사에 없는 글자다"
            f"(실측 2026-10-06: 그래서 라디오 프로그램 문단을 받았다): {joined}")
    # 🔴 팀·상대가 들어간다
    assert "Honduras" in joined and "Jamaica" in joined, joined


def test_질의가_문지기를_지난다():
    for sub in (_Sub(["absence_def"]), _Sub(["coach_conflict"]),
                _Sub(["event_match"]), _Sub(["venue_weather"])):
        for q, _lang in S3.queries_for(sub, _ref()):
            ok, why = S3.gate_ok(q)
            assert ok, f"🔴 우리가 만든 질의가 문지기에 걸린다: {q!r} — {why}"


def test_어깻점이_값에서_제거된다():
    """🔴 `O'Neill` 이 문지기(`["'()]`)에 걸려 그 유형이 0건이었다(실측)."""
    ref = _ref(home_name="O'Neill United", away_name="Georgia")
    for q, _l in S3.queries_for(_Sub(["coach_conflict"], key="team:000103"), ref):
        assert "'" not in q, q
        assert S3.gate_ok(q)[0], q


def test_문지기가_하나다():
    """🔴 §9 — 두 번째 정의를 만들지 않는다. `gate_ok` 가 그 하나다."""
    import inspect
    src = inspect.getsource(S3)
    assert src.count("def gate_ok") == 1
    # 🔴 **돌려서** 본다: 긴 질의·연도·연산자를 막는다
    assert not S3.gate_ok("a b c d e f g h")[0]
    assert not S3.gate_ok("Honduras 2026 lineup")[0]
    assert not S3.gate_ok('site:x.com Honduras')[0]
    assert S3.gate_ok("Honduras Jamaica injury")[0]


# ══════════════════════════════════════════════════════════════════
# ③ fetch — 실패 대체 · 상위 N건 · stale · 캐시
# ══════════════════════════════════════════════════════════════════

def _run_one(chain, net, *, ref=None, cache=None, sub=None):
    st = RunState(match_key="fotmob:1")
    sub = sub or _Sub(["absence_def"])
    got = asyncio.run(S3._one(sub, ref or _ref(), state=st, chain=chain,
                              net=net, cache=cache if cache is not None else {}))
    return got, st, sub


def test_열기_실패는_다음_후보로_간다():
    """🔴🔴 실측 2026-10-06: 상위 3건이 **전부** 못 열려 문서 0건이었다 —
    그때 코드가 `kept[:3]` 만 돌아서 네 번째 후보를 **쳐다보지 않았다**.

    ══════════════════════════════════════════════════════════════════
    🔴 그런데 **예산은 호출 수**다 — 실패가 그 몫을 먹는다
    ══════════════════════════════════════════════════════════════════

    `fetch_cap` 은 **3회 호출**이고(경기 합계 24 = 3 × 하위 8), `fetch_top` 은
    **3건 문서**다. 둘이 같은 수라서 **403 하나가 문서 하나를 깎는다.**
    ⚠️ 상한을 올려 메우는 것은 §9 금지다 — 🔴 여기서 세는 것은 *"다음 후보로
       **간다**"*(앞에서 멈추지 않는다)와 *"깎인 사실이 사유로 남는다"* 다.
       상한을 어떻게 할지는 §8 3단계 실측으로 사용자가 정한다.
    """
    urls = [f"https://bbc.com/{i}" for i in range(6)]
    chain = _Chain([_Hit(u) for u in urls])
    net = _Net(bad={urls[0], urls[1]})       # 🔴 앞 둘이 막힌다
    docs, st, sub = _run_one(chain, net)
    # 🔴 ① **앞에서 멈추지 않았다** — 세 번째 후보를 받았다
    assert docs, f"🔴 앞 둘이 막히자 멈췄다 — 네 번째를 안 봤다: {st.drops}"
    assert {d.url for d in docs} <= set(urls[2:]), [d.url for d in docs]
    # 🔴 ② 실패한 둘을 **시도했다**(그래서 예산을 썼다) — 그 사실이 수로 남는다
    assert urls[0] in net.got and urls[1] in net.got, net.got
    assert sub.budget.fetch_used == sub.budget.fetch_cap, sub.budget.fetch_used
    # 🔴 ③ **버린 까닭이 남는다**(#3) — 조용히 줄지 않는다
    bad = [d for d in st.drops if d.reason.value == "body_missing"]
    assert len(bad) == 2, st.drops
    assert all("403" in d.detail or "열기 실패" in d.detail for d in bad), bad


def test_전부_막히면_문서_0건이고_까닭이_전부_남는다():
    """🔴 그 경우에도 **예외가 아니다** — 빈 목록 + 사유다(§5)."""
    urls = [f"https://bbc.com/{i}" for i in range(4)]
    docs, st, _sub = _run_one(_Chain([_Hit(u) for u in urls]),
                              _Net(bad=set(urls)))
    assert docs == []
    assert len([d for d in st.drops if d.reason.value == "body_missing"]) == 3


def test_상위_세건까지만_받는다():
    chain = _Chain([_Hit(f"https://bbc.com/{i}") for i in range(9)])
    docs, _st, _sub = _run_one(chain, _Net())
    assert len(docs) == 3, len(docs)
    assert [d.id for d in docs] == ["D1", "D2", "D3"], [d.id for d in docs]


def test_킥오프_7일_밖이면_Doc_을_안_만든다():
    """🔴 사유는 `stale` 이다 — 조용히 사라지지 않는다."""
    chain = _Chain([_Hit("https://bbc.com/old")])
    docs, st, _sub = _run_one(chain, _Net(when="2026-09-01"))
    assert docs == [], [d.url for d in docs]
    assert any(d.reason.value == "stale" for d in st.drops), st.drops


def test_본문과_날짜가_한_몸이다():
    chain = _Chain([_Hit("https://bbc.com/a")])
    docs, _st, _sub = _run_one(chain, _Net())
    d = docs[0]
    assert d.body.strip() and d.published_at is not None
    assert d.date_source == "htmldate", d.date_source
    # 🔴 날짜가 없으면 출처도 `none` — 둘이 어긋나지 않는다
    docs2, _s2, _b2 = _run_one(_Chain([_Hit("https://bbc.com/b")]),
                               _Net(when=""))
    if docs2:
        assert docs2[0].published_at is None
        assert docs2[0].date_source == "none", docs2[0].date_source


def test_같은_URL_은_경기_단위로_한_번만_받는다():
    """🔴 §5 s3-4 — 캐시는 `Doc` **통째로** 저장한다(본문만 저장하는 경로 없음)."""
    cache: dict = {}
    url = "https://bbc.com/same"
    net = _Net()
    _d1, _s1, _b1 = _run_one(_Chain([_Hit(url)]), net, cache=cache)
    n_first = len(net.got)
    _d2, _s2, _b2 = _run_one(_Chain([_Hit(url)]), net, cache=cache,
                             sub=_Sub(["absence_def"], name="B-홈"))
    assert len(net.got) == n_first, (
        f"🔴 같은 URL 을 두 번 받았다: {net.got}")
    assert url in cache and cache[url].body.strip()


def test_하위_이름이_열거값으로_바뀐다():
    for name, want in (("A-홈", "A-home"), ("D-원정", "D-away")):
        assert S3._sid(_Sub([], name=name)) == want


def test_같은_URL_이_목록에_두_번_안_들어간다():
    """🔴🔴 §8 2단계 합격 조건 — *"같은 URL 중복 0"*(실측 2026-10-06: 2건이었다).

    🔴 둘째 하위는 **건너뛰고 다음 후보로** 간다 — 그 URL 내용은 이미 있고,
       다른 문서를 받는 쪽이 덮는 범위가 넓다.
    """
    cache: dict = {}
    same, other = "https://bbc.com/same", "https://bbc.com/other"
    net = _Net()
    d1, _s1, _b1 = _run_one(_Chain([_Hit(same), _Hit(other)]), net, cache=cache)
    assert {d.url for d in d1} == {same, other}, [d.url for d in d1]
    d2, st2, _b2 = _run_one(_Chain([_Hit(same), _Hit("https://bbc.com/new")]),
                            net, cache=cache,
                            sub=_Sub(["absence_def"], name="B-홈"))
    urls2 = [d.url for d in d2]
    assert same not in urls2, f"🔴 같은 URL 이 둘째 하위에도 들어갔다: {urls2}"
    assert "https://bbc.com/new" in urls2, urls2
    # 🔴 **그 사실이 사유로 남는다**(#3)
    assert any("이미 들고 있다" in n for n in st2.notes), st2.notes
