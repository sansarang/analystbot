"""SRCH-3 — 검색 요청자를 **2단계 선별**로 옮긴다. 그리고 배선을 못 박는다.

사용자 지시 2026-09-12: "최종 판정 2단계는 삭제..1단계로 제미니 최종 판정으로
간다" · "퍼플릭스와 안트로픽" · "경기당 1회 질문 3개로 해라"

🔴 왜 이 단계가 필요한가. SRCH-1 이 2차 검증을 지웠는데, **검색을 요청하던
   것이 바로 그 2차 검증관**이었다. 그래서 지금 이 경로의 외부 검색은 0 이다.
   선별은 이미 `없는것` 을 돌려준다 — 요청자는 거기 있으면 된다.

🔴 **가장 큰 위험은 "만들었는데 안 불린다"이다.**
   SRCH-2 가 `websearch.ask` 를 만들어 두었지만 아무도 부르지 않는다.
   이 저장소는 같은 결함을 이미 겪었다(PGP-2: 존재하는 것과 불리는 것은
   다르다 · SCT-1: 정찰이 자료15로 들어가는지 배선을 따로 단언했다).
   그래서 여기 **호출 계약**이 있다.

⚠️ 반대 위험: 습관적으로 요청하면 경기당 $0.10 이 고정된다. 요청 0개면
   호출이 없어야 하고, 그것도 계약이다.
"""

import pytest

from app.engine import gather as G
from app.engine import matchup as MU
from app.engine import triage as TR


# ── [NOLLM 2026-09-22] 이 파일은 **LLM 판정 경로**를 시험한다 ──────────────
#
# 🔴 사용자 지시로 `judge.llm_verdict` 기본값이 **false** 가 됐다("판정은 원래
#    코드에서 낸다"). 그러면 이 파일의 시험 대상 경로가 아예 안 돈다.
# 🔴 **그 경로를 지우지 않았다** — 스위치 한 줄로 되돌릴 수 있어야 하고,
#    되돌렸을 때 종전대로 도는지는 **계약이 지켜야 한다.**
#    그래서 여기서는 스위치를 **켜고** 시험한다.
# ⚠️ 스위치가 꺼진 동작은 `tests/test_nollm.py` 가 따로 잠근다.
import pytest as _pytest


@_pytest.fixture(autouse=True)
def _llm_verdict_on(monkeypatch):
    monkeypatch.setattr("app.engine.matchup._llm_verdict_on", lambda: True)


@pytest.fixture(autouse=True)
def _no_pplx(monkeypatch):
    """🔴 테스트가 실망을 타지 않게 한다. 퍼플렉시티를 쓰는 계약은 자기가
    다시 패치한다 — 여기 기본은 '꺼짐'이다."""
    async def _off(jg, asks):
        return []

    monkeypatch.setattr("app.engine.deepsearch._ask_pplx", _off)


def _jg():
    return {"game_id": 1, "sport": "kbo", "league": "KBO",
            "home": "Samsung Lions", "away": "LG Twins"}


def _row(ans, src="anthropic", when="2026-09-12"):
    return {"질문": "", "답": ans, "소스": src, "소스유형": "뉴스",
            "시점": when, "계정": "", "url": ""}


# ═══════════════ ① 선별이 검색 질문을 낸다

def test_프롬프트가_검색요청을_묻는다():
    from app.engine.prompts import TRIAGE

    assert "검색요청" in TRIAGE
    assert "DB요청" in TRIAGE, "DB 요청과 **다른 칸**이어야 한다"


def test_프롬프트가_오늘_바뀐_것만_묻게_한다():
    """🔴 ORD-5 실측: 조사요청 38문 중 28문(74%)이 성적 조회였다.
    성적은 어느 날에나 같은 값이라 오늘을 설명하지 않는다."""
    from app.engine.prompts import TRIAGE

    i = TRIAGE.index("검색요청")
    body = TRIAGE[i - 900:i + 900]
    assert "성적" in body
    assert "부상" in body and "말소" in body


def test_프롬프트가_습관적_요청을_막는다():
    """🔴 요청은 유료다. 실측 2026-09-12: 경기당 $0.08~0.14."""
    from app.engine.prompts import TRIAGE

    assert "돈이 든다" in TRIAGE or "유료" in TRIAGE
    assert "빈 배열" in TRIAGE


def test_선별이_검색요청을_돌려준다(monkeypatch):
    _fake_triage(monkeypatch, {"채택": [1], "검색요청": ["구창모 등판 가능한가"]})
    out = _run_triage([_row("a")])
    assert out["검색요청"] == ["구창모 등판 가능한가"]


def test_검색요청도_세_개까지다(monkeypatch):
    """사용자 결정: "경기당 1회 질문 3개로 해라". **코드가 자른다.**"""
    _fake_triage(monkeypatch,
                 {"채택": [1], "검색요청": [f"q{i}" for i in range(9)]})
    out = _run_triage([_row("a")])
    assert len(out["검색요청"]) == TR.MAX_ASKS == 3


def test_빈_질문은_버린다(monkeypatch):
    _fake_triage(monkeypatch, {"채택": [1], "검색요청": ["", "  ", "진짜 질문"]})
    assert _run_triage([_row("a")])["검색요청"] == ["진짜 질문"]


def test_검색요청이_없으면_빈_목록이다(monkeypatch):
    _fake_triage(monkeypatch, {"채택": [1]})
    assert _run_triage([_row("a")])["검색요청"] == []


# ═══════════════ ② 검색 라운드 — 경기당 1회

@pytest.mark.asyncio
async def test_질문을_웹검색에_넘긴다(monkeypatch):
    seen = {}

    async def _ws(jg, qs, *, today=None, settings=None):
        seen["qs"] = list(qs)
        seen["today"] = today
        return [_row("문보경 5번 지명타자 복귀")]

    monkeypatch.setattr("app.collectors.websearch.ask", _ws)
    out = await G.search(_jg(), ["문보경 복귀?", "구자욱 결장?"], "2026-09-12")
    assert seen["qs"] == ["문보경 복귀?", "구자욱 결장?"]
    assert seen["today"] == "2026-09-12"
    assert out["자료"][0]["답"].startswith("문보경")
    assert out["출처"] == {"anthropic": 1}


@pytest.mark.asyncio
async def test_질문이_없으면_아무_채널도_안_부른다(monkeypatch):
    """🔴 유료다. 요청이 없으면 호출도 없어야 한다."""
    async def _boom(*a, **k):
        raise AssertionError("질문이 없는데 불렀다")

    monkeypatch.setattr("app.collectors.websearch.ask", _boom)
    out = await G.search(_jg(), [], "2026-09-12")
    assert out == {"자료": [], "출처": {}}


@pytest.mark.asyncio
async def test_한_채널이_터져도_나머지가_산다(monkeypatch):
    async def _boom(*a, **k):
        raise RuntimeError("터졌다")

    monkeypatch.setattr("app.collectors.websearch.ask", _boom)
    out = await G.search(_jg(), ["q"], "2026-09-12")
    assert out["자료"] == []


@pytest.mark.asyncio
async def test_0건이면_0건이라고_돌려준다(monkeypatch):
    async def _none(*a, **k):
        return []

    monkeypatch.setattr("app.collectors.websearch.ask", _none)
    out = await G.search(_jg(), ["q"], "2026-09-12")
    assert out["자료"] == [] and out["출처"] == {}


# ═══════════════ ③ 배선 — **실제로 불리는가**

def test_판정_문이_검색을_부른다():
    """🔴 이 저장소의 반복 결함: 만들어 놓고 안 불린다(PGP-2).
    `websearch.ask` 는 SRCH-2 가 만들었지만 어제까지 호출부가 0 이었다."""
    import inspect

    src = inspect.getsource(MU._judge_v3)
    assert "gather.search" in src or "search(" in src, src[:400]
    i = src.index("triage.run")
    j = src.index("verdict.decide")
    assert "search" in src[i:j], "검색이 선별과 판정 **사이**에 있어야 한다"


def test_검색을_쓰는_곳이_실제로_존재한다():
    """🔴 심볼이 있는 것과 경로가 이어진 것은 다르다."""
    import pathlib

    hits = [p for p in pathlib.Path("app").rglob("*.py")
            if "websearch" in p.read_text(encoding="utf-8")
            and p.name != "websearch.py"]
    assert hits, "app/ 안에서 websearch 를 부르는 곳이 하나도 없다"


@pytest.mark.asyncio
async def test_검색_결과가_판정_재료에_들어간다(monkeypatch):
    """🔴 검색해 놓고 판정이 못 보면 돈만 쓴 것이다."""
    seen = {}

    async def _decide(jg, brief, tri, **k):
        seen["채택"] = list(tri["채택"])
        return {"승자": "LG Twins", "확신": "중"}

    await _wire(monkeypatch, decide=_decide,
                triage={"채택": [_row("수집물")], "검색요청": ["q"],
                        "갈림길": [], "변수": [], "없는것": [], "DB요청": [],
                        "계측": {"수집": 1, "채택": 1, "기각": 0, "미분류": 0}},
                search={"자료": [_row("검색으로 찾은 사실")],
                        "출처": {"anthropic": 1}})
    answers = [r["답"] for r in seen["채택"]]
    assert "검색으로 찾은 사실" in answers, answers


@pytest.mark.asyncio
async def test_검색이_0건이어도_판정은_계속된다(monkeypatch):
    """🔴 검색 실패로 카드를 막지 않는다 — 재료가 줄 뿐이다."""
    jg = await _wire(monkeypatch,
                     triage={"채택": [_row("수집물")], "검색요청": ["q"],
                             "갈림길": [], "변수": [], "없는것": [], "DB요청": [],
                             "계측": {"수집": 1, "채택": 1, "기각": 0, "미분류": 0}},
                     search={"자료": [], "출처": {}})
    assert jg.get("winner") == "LG Twins"


@pytest.mark.asyncio
async def test_요청이_없으면_검색을_부르지_않는다(monkeypatch):
    """🔴 비용 게이트. 습관적으로 부르면 경기당 $0.10 이 고정된다."""
    called = {"n": 0}

    async def _search(*a, **k):
        called["n"] += 1
        return {"자료": [], "출처": {}}

    await _wire(monkeypatch, search=_search,
                triage={"채택": [_row("수집물")], "검색요청": [],
                        "갈림길": [], "변수": [], "없는것": [], "DB요청": [],
                        "계측": {"수집": 1, "채택": 1, "기각": 0, "미분류": 0}})
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_원장에_검색_계측이_남는다(monkeypatch):
    """🔴 조용한 0 금지. "검색을 안 했다"와 "했는데 0건"은 다르다."""
    jg = await _wire(monkeypatch,
                     triage={"채택": [_row("수집물")], "검색요청": ["q1", "q2"],
                             "갈림길": [], "변수": [], "없는것": [], "DB요청": [],
                             "계측": {"수집": 1, "채택": 1, "기각": 0, "미분류": 0}},
                     search={"자료": [_row("x")], "출처": {"anthropic": 1}})
    o = jg["order_v3"]
    assert o["검색요청"] == ["q1", "q2"]
    assert o["검색n"] == 1
    assert o["검색출처"] == {"anthropic": 1}


# ═══════════════ 보조

def _fake_triage(monkeypatch, payload):
    """`triage.run` 의 바깥(LLM·라우팅·목 스위치)만 가짜로 만든다.
    ⚠️ 파싱과 상한은 **진짜 코드**가 돌아야 계약이 의미가 있다."""
    import json
    import types

    import app.config as CFG

    _real = CFG.get_settings

    def _s():
        base = _real()
        d = {k: getattr(base, k) for k in
             ("deepsearch_max_tokens", "deepsearch_timeout_sec")}
        d["mock_judge"] = False
        return types.SimpleNamespace(**d)

    monkeypatch.setattr(CFG, "get_settings", _s)
    monkeypatch.setattr("app.llm.judge_route.chain",
                        lambda role: [("gemini", "gemini-3.7-flash")])

    async def _free(routes, prompt, mx, role):
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr("app.engine.team_form._complete_free", _free)


def _run_triage(rows):
    import asyncio

    out = asyncio.run(TR.run(_jg(), "brief", rows))
    assert out is not None, "선별이 None 을 돌려줬다 — 가짜 배선이 틀렸다"
    return out


async def _wire(monkeypatch, *, triage, search=None, decide=None):
    """`_judge_v3` 를 가짜 단계로 돌린다. 진짜 배선만 남긴다."""
    async def _collect(jg, redis, date, pool=None):
        return {"자료": [_row("수집물")], "출처": {"satellite": 1}}

    async def _tri(jg, brief, rows, **k):
        return {k2: (list(v) if isinstance(v, list) else v)
                for k2, v in triage.items()}

    async def _dec(jg, brief, tri, **k):
        return {"승자": "LG Twins", "확신": "중"}

    async def _ref(jg, tri, v, **k):
        return {"승자": v["승자"], "확신": v["확신"], "판정": "확인",
                "승자변경": False, "사유": "", "있음": [], "없음": [], "본것": []}

    async def _srch(jg, asks, date, **k):
        return search if isinstance(search, dict) else {"자료": [], "출처": {}}

    monkeypatch.setattr(G, "collect", _collect)
    monkeypatch.setattr(TR, "run", _tri)
    monkeypatch.setattr("app.engine.verdict.decide", decide or _dec)
    monkeypatch.setattr("app.engine.dbref.recheck", _ref)
    monkeypatch.setattr(G, "search", search if callable(search) else _srch)
    monkeypatch.setattr(MU, "game_brief", lambda jg: "brief")

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(MU, "persist_matchup_record", _noop)
    monkeypatch.setattr(MU, "release_final", _noop)
    jg = _jg()
    await MU._judge_v3(jg, None, "2026-09-12", final=False)
    return jg


# ═══════════════ SRCH-4 — 퍼플렉시티도 같은 문을 지난다

@pytest.mark.asyncio
async def test_퍼플렉시티도_검색_라운드에_있다(monkeypatch):
    """사용자 지시 2026-09-12: "퍼플릭스와 안트로픽"."""
    seen = {}

    async def _pplx(jg, asks):
        seen["asks"] = list(asks)
        return [_row("퍼플렉시티가 찾은 것", src="pplx")]

    async def _ws(*a, **k):
        return []

    monkeypatch.setattr("app.engine.deepsearch._ask_pplx", _pplx)
    monkeypatch.setattr("app.collectors.websearch.ask", _ws)
    out = await G.search(_jg(), ["q1"], "2026-09-12")
    assert seen["asks"] == ["q1"]
    assert out["출처"] == {"pplx": 1}


@pytest.mark.asyncio
async def test_퍼플렉시티_행도_날짜_게이트를_지난다(monkeypatch):
    """🔴 게이트 없이 붙이면 SRCH-2 가 막은 결함(5개월 전 기사)을 다시 연다."""
    async def _pplx(jg, asks):
        return [_row("오늘 일", src="pplx", when="2026-09-12"),
                _row("4월 부상", src="pplx", when="2026-04-14")]

    async def _ws(*a, **k):
        return []

    monkeypatch.setattr("app.engine.deepsearch._ask_pplx", _pplx)
    monkeypatch.setattr("app.collectors.websearch.ask", _ws)
    out = await G.search(_jg(), ["q"], "2026-09-12")
    assert [r["답"] for r in out["자료"]] == ["오늘 일"]


@pytest.mark.asyncio
async def test_두_채널이_병렬이고_한쪽이_죽어도_산다(monkeypatch):
    async def _pplx(jg, asks):
        raise RuntimeError("터졌다")

    async def _ws(*a, **k):
        return [_row("웹검색이 찾은 것")]

    monkeypatch.setattr("app.engine.deepsearch._ask_pplx", _pplx)
    monkeypatch.setattr("app.collectors.websearch.ask", _ws)
    out = await G.search(_jg(), ["q"], "2026-09-12")
    assert out["출처"] == {"anthropic": 1}
