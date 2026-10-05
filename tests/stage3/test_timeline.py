"""단계 3 계약 — §19-d **시간축**과 §19-e **소스 점수표**(완료 조건 두 항목).

§19-d 원문: *"세포는 깨어나는 시각이 있다: 슬레이트·순위·대표팀 명단은 아침 1회,
선발·최근 창·결장은 T-6h, 감독 인용은 T-3h·T-1h, 확정 라인업은 T-70분부터 5분
간격, 라이브 스코어(타 구장)는 판정에 걸린 경기만 10분 간격. 경기 시작이면 그
경기의 모든 세포는 종료. 채점 세포만 경기 후 깨어난다."*
"""
from __future__ import annotations

import ast
import inspect
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests._helpers import strip_docs

from app import cells as C
from app.collect import ingest

ROOT = Path(__file__).resolve().parents[2]
SQL = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
UTC = timezone.utc


def _at(minutes_before: float) -> tuple[datetime, datetime]:
    starts = datetime(2026, 9, 27, 9, 0, tzinfo=UTC)
    return starts, starts - timedelta(minutes=minutes_before)


# ══════════════════════════════════════════════════════════════════
# §19-d 표 자체
# ══════════════════════════════════════════════════════════════════

def test_WAKE가_모든_질문_타입을_덮는다():
    """🔴 표에 없는 타입은 `awake()` 가 **언제나 깨어 있다**고 답한다.

    ⚠️ 그것은 조용한 결함이다 — 새 질문 타입을 만들면 예산을 무제한으로 쓰면서
       "시간축을 지키고 있다"고 보인다. 🔴 `Q_TYPES` 가 원본이므로 여기서
       이름을 손으로 세지 않는다.
    """
    missing = sorted(set(C.Q_TYPES) - set(C.WAKE))
    assert missing == [], f"§19-d 표에 없는 질문 타입: {missing}"


def test_경기가_시작되면_라이브만_남는다():
    """🔴 §19-d — *"경기 시작이면 그 경기의 모든 세포는 종료."*"""
    starts, _ = _at(0)
    after = starts + timedelta(minutes=1)
    for q in C.Q_TYPES:
        got = C.awake(q, starts, after)
        assert got is (q == C.Q_LIVE), f"{q} 가 경기 시작 후에 {got}"


def test_라인업은_T70부터_T10까지다():
    """§19-d — *"확정 라인업은 T-70분부터 5분 간격, T-10분까지."*"""
    starts, _ = _at(0)
    assert not C.awake(C.Q_LINEUP, starts, starts - timedelta(minutes=71))
    assert C.awake(C.Q_LINEUP, starts, starts - timedelta(minutes=70))
    assert C.awake(C.Q_LINEUP, starts, starts - timedelta(minutes=10))
    # T-10 을 지나면 닫힌다 — 그 뒤 라인업은 경기 중 정보다
    assert not C.awake(C.Q_LINEUP, starts, starts - timedelta(minutes=9))


def test_아침_1회_질문은_언제든_깬다():
    """슬레이트·순위는 T 와 무관하다 — 🔴 마감이 없으니 지연도 못 잰다."""
    starts, _ = _at(0)
    for q in (C.Q_SLATE, C.Q_STANDINGS):
        assert C.awake(q, starts, starts - timedelta(hours=20))
        assert C.awake(q, starts, starts - timedelta(minutes=1))


def test_선발과_결장은_T6h다():
    starts, _ = _at(0)
    for q in (C.Q_ABSENCE, C.Q_STARTER_RECENT, C.Q_COUNTER):
        assert not C.awake(q, starts, starts - timedelta(minutes=361))
        assert C.awake(q, starts, starts - timedelta(minutes=360))


# ══════════════════════════════════════════════════════════════════
# 🔴 표가 **집행되나** — 만든 표를 아무도 안 보면 없는 것과 같다
# ══════════════════════════════════════════════════════════════════

def test_수집이_시간축을_집행한다():
    """★ `awake()` 를 **부르는 자리**가 있어야 시간축이 존재한다.

    ⚠️ 문자열로 보면 안 된다 — `from app.cells import … awake` 라는 import 줄이
       소스에 있으므로 호출을 지워도 `"awake" in src` 는 참이다(이 저장소가 다섯
       번 만든 병). **부르는 자리**를 본다.
    """
    tree = ast.parse(inspect.getsource(ingest))
    called = {n.func.id if isinstance(n.func, ast.Name)
              else getattr(n.func, "attr", "")
              for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert "awake" in called, "수집이 `awake()` 를 **부르지** 않는다"


def test_안_깬_세포는_사유가_남는다():
    """🔴 조용한 0 금지 — *"자료가 없다"* 와 *"아직 시간이 아니다"* 는 다르다.

    ⚠️ 구분하지 않으면 다음 사람이 파서·소스를 고치려 하고, 고칠 것은 없다.
    """
    src = strip_docs(inspect.getsource(ingest._game_cells))
    assert "bb.unknown" in src, "안 깬 세포를 조용히 건너뛴다"
    assert "시간축" in inspect.getsource(ingest._game_cells)


def test_스케줄러가_라인업_주기보다_자주_돈다():
    """🔴 §19-d 는 라인업을 **5분 간격**으로 요구한다.

    ⚠️ 수집 주기가 그보다 길면 T-70~T-10(60분) 창에서 **몇 번밖에** 못 두드린다.
       그 사이 라인업이 바뀌면 못 잡는다.
    """
    from app import scheduler as S
    _, step, until = C.WAKE[C.Q_LINEUP]
    window_min = C.WAKE[C.Q_LINEUP][0] - (until or 0)
    tries = window_min / (S.COLLECT_INTERVAL_SEC / 60)
    assert tries >= 2, (
        f"라인업 창 {window_min}분 동안 수집이 {tries:.1f}번밖에 안 돈다 "
        f"(§19-d 는 {step}분 간격을 요구한다 — COLLECT_INTERVAL_SEC 를 줄여라)")


# ══════════════════════════════════════════════════════════════════
# §19-e 소스 점수표
# ══════════════════════════════════════════════════════════════════

def test_DB_제약이_세포_질문_타입과_같다():
    """🔴 **`source_score.question_type` 은 §19-a 세포 질문 타입이다.**

    ⚠️ 단계 2 가 여기에 **§4 변수 유형 13종**(`emotion`·`h2h_pattern`·`stakes` …)
       을 걸어 놨다. 그것은 `variables.type` 의 어휘이고, 질문의 어휘가 아니다 —
       겹치는 것은 `absence` 하나뿐이다. 실측 2026-09-30: 단계 3 이 점수표 적재를
       이으니 `question_type='lineup'` 이 바로 `CheckViolationError` 로 튕겼다.
       🔴 **표만 세우고 쓰는 코드가 없어 단계 2 에서는 아무도 몰랐다** — 계약도
       제약의 *존재*만 봤고 어휘가 맞는지는 안 봤다(CLAUDE.md §배선).

    🔴 그래서 이 계약은 **`Q_TYPES` 를 원본으로 삼아 SQL 을 대조한다.**
    """
    m = re.search(
        r"ADD CONSTRAINT source_score_qtype_ck CHECK \(\s*"
        r"question_type IN \(([^)]*)\)", SQL)
    assert m, "source_score_qtype_ck 가 없다"
    in_sql = set(re.findall(r"'([a-z0-9_]+)'", m.group(1)))
    want = set(C.Q_TYPES)
    assert in_sql == want, (f"DB 에 없는 질문 타입 {sorted(want - in_sql)} · "
                            f"§19-a 에 없는 값 {sorted(in_sql - want)}")


def test_점수표_열쇠가_리그를_포함한다():
    """🔴 §19-e 원문은 `(source, question_type, league)` **셋**이고 `source_score`
    유일키도 셋이다.

    ⚠️ 둘만 쓰면 KBO 에서 잘 듣는 매체가 NPB 순서를 밀어 올린다 — §13 소스 지도가
       리그별인 이유가 그것이다.
    """
    sc = C.SourceScores()
    sc.record("m", C.Q_LINEUP, "NPB", hit=True)
    key = next(iter(sc.table))
    assert len(key) == 3 and key[2] == "NPB", key
    m = re.search(r"UNIQUE \(source, question_type, league\)", SQL)
    assert m, "source_score 유일키가 셋이 아니다"


def test_지연은_못_재면_NULL로_간다():
    """🔴 `source_score.lag_min` 주석: *"못 재면 NULL — 0 으로 때우지 않는다."*"""
    sc = C.SourceScores()
    sc.record("아침소스", C.Q_STANDINGS, "NPB", hit=True)      # 마감 없음
    s = sc.table[("아침소스", C.Q_STANDINGS, "NPB")]
    assert s.lag is None, "못 잰 지연이 숫자로 나왔다"
    # 🔴 적재도 NULL 이어야 한다 — 코드가 0 을 만들어 넣으면 안 된다
    src = strip_docs(inspect.getsource(C.SourceScores.flush))
    assert "None if s.lag is None" in src, "적재가 NULL 을 안 쓴다"


def test_점수표가_DB에서_되살아난다():
    """🔴 §19-e — *"쌓이면 §13 소스 순서를 코드가 스스로 고친다."*

    ⚠️ 프로세스가 죽을 때마다 0 으로 돌아가면 **영영 쌓이지 않는다.**
    """
    src = inspect.getsource(ingest.collect)
    assert "scores.load(" in src, "수집이 점수표를 되살리지 않는다"
    assert "scores.flush(" in src, "수집이 점수표를 남기지 않는다"


def test_죽은_호스트는_사유_없이_죽지_않는다():
    """🔴 `source_state.reason` 이 NOT NULL 이고, 사유가 없으면 "왜 대체 소스로
    갔나"를 되짚을 수 없다(§19-b-6).
    """
    import pytest

    from app.net import Net
    net = Net()
    with pytest.raises(ValueError, match="사유 없이"):
        net.mark_dead("example.com", "")
    net.mark_dead("example.com", "robots 거부")
    assert net.dead_hosts["example.com"] == "robots 거부"


# ══════════════════════════════════════════════════════════════════
# §4 결장 원장 — 🔴 `line` 을 지어내지 않는다
# ══════════════════════════════════════════════════════════════════

def test_line을_모르면_원장에_넣지_않는다():
    """🔴 `absences.line` 은 NOT NULL 이고 **지어낼 수 없다.**

    §4 의 `line` 은 `starter|bullpen|lineup_core|defense|midfield` 다. MLB
    transactions 파서가 이미 못 박았다: *"투수인지 야수인지는 로스터가 말하고,
    그것이 없으면 `starter`/`lineup_core` 를 지어내게 된다."*

    지금 알 수 있는 것은 하나다 — **오늘 예고 선발이면 `starter`**. 그 밖은 모른다.
    ⚠️ 절제 2026-09-30: `_line_of` 가 늘 `"starter"` 를 내도록 바꿨더니 계약이
       **통과해 버렸다.** 그러면 예고되지 않은 결장자가 전부 선발로 기록되고,
       그것이 `pitcher_state` 판정을 오염시킨다(M18 과 같은 결의 오류).
    """
    import asyncio

    from app.collect import ingest

    class _Conn:
        def __init__(self, row):
            self.row = row
            self.asked = 0

        async def fetchrow(self, *a):
            self.asked += 1
            return self.row

    # 🔴 예고 선발 행이 없으면 **모른다**
    c = _Conn(None)
    got = asyncio.run(ingest._line_of(c, "NPB", "팀", "선수", None))
    assert got is None, f"line 을 지어냈다: {got!r}"
    assert c.asked == 1, "DB 를 보지도 않고 답했다"

    # 🔴 예고 선발이면 `starter`
    got = asyncio.run(ingest._line_of(_Conn({"?column?": 1}), "NPB", "팀",
                                      "선수", None))
    assert got == "starter", got


def test_line_미상_결장은_이름으로_남는다():
    """🔴 조용한 0 금지 — 원장에 못 넣은 결장을 **사유째로** 남긴다.

    ⚠️ 그냥 건너뛰면 "결장자가 없다"로 읽히고, 그것이 M11(명단 없이 완전체로
       씀)의 재발 경로다.
    """
    import inspect

    from app.collect import ingest
    src = inspect.getsource(ingest._absences)
    assert "line 을 모른다" in src, "line 미상을 조용히 건너뛴다"
    assert strip_docs(src).count("bb.unknown") >= 2, \
        "귀속 불명·line 미상 둘 다 남기지 않는다"


def test_되살린_dead_사유가_자라지_않는다():
    """🔴 **멱등이어야 한다.** `load_state` → `flush_state` 를 여러 번 돌려도
    `source_state.reason` 이 자라지 않아야 한다.

    ⚠️ 실측 2026-09-30: `load_state` 가 사이클마다 표시를 덧붙여 사유가
       `robots 거부 (오늘 기록됨) (오늘 기록됨)` 로 자랐다. 수집은 20분마다 돌므로
       하루 72번이면 그 칸을 읽을 수 없게 된다 — 사유는 **진단**이고, 읽을 수
       없는 진단은 없는 진단이다.

    🔴 **리뷰 B1(2026-09-30): 종전 판은 공회전이었다.** `mark_dead` 를 세 번 부르고
       표시가 하나인지 봤는데, `mark_dead` 는 **애초에 덧붙이지 않는다**(`setdefault`)
       — 즉 어떤 구현에서도 참인 단정이었고, `load_state` 를 **한 번도 안 불렀다.**
       그래서 이 계약은 이제 **`load_state` 를 목 pool 로 직접 돌린다.**
    """
    import asyncio

    from app.net import Net, _LOADED

    class _Pool:
        """`source_state` 한 행을 들고 있는 목. 🔴 `flush_state` 의 쓰기를 반영한다."""

        def __init__(self):
            self.reason = "robots 거부"

        async def fetch(self, *a):
            return [{"host": "x.example", "reason": self.reason,
                     "dead_since": None}]

        async def execute(self, sql, host, reason):
            self.reason = reason          # 다음 사이클이 이것을 되살린다
            return "INSERT 0 1"

    pool = _Pool()
    seen = []
    for _ in range(4):                    # 🔴 네 사이클 — 자라면 여기서 보인다
        net = Net()
        asyncio.run(net.load_state(pool))
        asyncio.run(net.flush_state(pool))
        seen.append(pool.reason)

    assert all(r.count(_LOADED) == 1 for r in seen), seen
    assert len(set(seen)) == 1, f"사유가 사이클마다 달라졌다: {seen}"
    # 🔴 원래 사유가 사라지지 않았다 — 표시만 붙는다
    assert "robots 거부" in seen[-1], seen[-1]


def test_load_state가_dead_표시를_실제로_붙인다():
    """🔴 **표시가 아예 안 붙으면** "지금 막은 것"과 "이미 막혀 있던 것"이 안 갈린다.

    ⚠️ 위 계약과 짝이다 — 위는 *"두 번 붙지 않는다"*, 여기는 *"한 번은 붙는다"*.
       하나만 두면 "아무것도 안 붙인다"가 통과한다.
    """
    import asyncio

    from app.net import Net, _LOADED

    class _Pool:
        async def fetch(self, *a):
            return [{"host": "y.example", "reason": "robots 거부",
                     "dead_since": None}]

    net = Net()
    asyncio.run(net.load_state(_Pool()))
    assert _LOADED in net.dead_hosts["y.example"], net.dead_hosts


# ══════════════════════════════════════════════════════════════════
# 🔴 조용한 0 — 답을 찾아도 **버린 것**은 남는다
# ══════════════════════════════════════════════════════════════════

def test_답을_찾아도_버린_것이_블랙보드에_남는다():
    """🔴 **리뷰 B3(2026-09-30)**: 이것이 안 닫혀 있었다.

    날짜 없어 옆으로 치운 사실의 사유가 `Cell.tried` 에만 적히고, `tried` 가
    블랙보드로 가는 길은 **unknown 경로뿐**이었다. 즉 답을 찾은 세포가 버린 것은
    DB·요약·로그 **어디에도 안 남았다** — 그런데 계약은 `cell.tried` **객체를
    직접** 봐서 초록이었다.

    그러면 운영에서 *"왜 라인업이 한 칸뿐인가"* 를 되짚을 수 없다
    (CLAUDE.md §조용한 0 금지).
    """
    import asyncio

    from app.blackboard import Blackboard, Fact
    from app.net import Net

    def _parse(payload, q):
        return [Fact(question_id=q.id, value={"x": 1}, hardness="hard")]

    cell = C.Cell(
        C.Question(C.Q_LINEUP, "NPB:팀:2026-09-27", team="팀", league="NPB"),
        [C.Source("1차", "url", url="https://ok.example/x", tier=1,
                  parse=_parse)],
        budget=C.Budget(searches=0, fetches=1))
    cell.tried.append("1차:발행 시각 없어 옆으로 치운 사실 3건")

    net = Net()

    async def _get(url, **k):
        from app.net import Fetched
        return Fetched(url, True, 200, "<html></html>")

    net.get = _get                                  # type: ignore[assignment]
    bb = Blackboard()
    state = asyncio.run(cell.run(net, bb, search=None, scores=None))
    assert state == "found", state

    # 🔴 **블랙보드에 남는다** — 객체를 들여다보지 않고도 보인다
    notes = dict(bb.notes())
    assert cell.question.id in notes, bb.notes()
    assert "치운 사실 3건" in notes[cell.question.id]
    # ⚠️ unknown 이 아니다 — 질문은 닫혔다
    assert bb.get(cell.question.id).state == "found"


def test_수집_요약이_버린_것을_낸다():
    """🔴 요약에 안 올라가면 사람이 못 본다(§조용한 0 금지)."""
    src = inspect.getsource(ingest.collect)
    assert 'out["notes"] = bb.notes()' in src, "수집 요약이 비고를 안 낸다"
    from app import scheduler as S
    assert "collect_notes" in inspect.getsource(S.run_once), \
        "스케줄러 보고가 비고를 안 낸다"


def test_직접_주소_소스도_가리킨_자료를_따라간다():
    """🔴🔴 **§19-c 가 직접 주소 소스에서 빠져 있었다** (실측 2026-10-02 라이브).

    검색 소스는 *"연 자료가 다른 자료를 가리키면 한 번 따라간다"* 를 하고 있었는데
    **직접 주소 소스는 안 했다.** 그런데 공식 API 깊이가 바로 그 꼴이다
    (`mlb.sources_context`·`nhl.sources_context`) — 즉 **야구·하키의 깊이가 통째로
    끊겨 있었다.**

    실측(NHL 디트로이트, 2026-10-02):
        고치기 전   박스스코어 1장 → 사실 8건 → 변수 **0건** → 자료 부족
        고친 뒤     일정·선수·순위까지 → 사실 **32건** → 변수 1건 · 폼 블록이 찼다
    ⚠️ `nhl.follow_links` 는 세 주소를 **내고 있었고 아무도 부르지 않았다.**
    🔴 축구(fotmob)는 한 페이지에 다 들어 있어서 이 구멍이 안 보였다 — 정답지 경기가
       축구였던 것이 결함을 가렸다.
    """
    import asyncio

    from app.blackboard import Blackboard, Fact
    from app.net import Fetched, Net

    def _parse(payload, q):
        return [Fact(question_id=f"{q.id}:head", value={"a": 1}, hardness="hard")]

    def _follow(got, q):
        return ["https://ok.example/deep"]

    def _parse_follow(got, q):
        return [Fact(question_id=f"{q.id}:form", value={"b": 2}, hardness="hard")]

    cell = C.Cell(
        C.Question(C.Q_LINEUP, "NHL:팀:2026-10-02", team="팀", league="NHL"),
        [C.Source("공식 API", "url", url="https://ok.example/box", tier=1,
                  parse=_parse, follow=_follow, parse_follow=_parse_follow)],
        budget=C.Budget(searches=0, fetches=4))

    seen: list[str] = []

    async def _get(url, **k):
        seen.append(url)
        return Fetched(url, True, 200, "{}")

    net = Net()
    net.get = _get                                  # type: ignore[assignment]
    bb = Blackboard()
    assert asyncio.run(cell.run(net, bb, search=None, scores=None)) == "found"

    # 🔴 **가리킨 주소를 실제로 열었나**
    assert "https://ok.example/deep" in seen, seen
    qids = {q for q in bb.slots}
    assert any(q.endswith(":form") for q in qids), sorted(qids)

    # 🔴 **한 번만이다** — 2단을 허용하면 링크를 타고 예산이 샌다
    assert seen.count("https://ok.example/deep") == 1, seen


def test_킥오프_뒤에_나온_자료는_세포가_거부한다():
    """🔴🔴 **게이트의 구멍이었다** (사용자 지시 2026-10-02 *"구현해라"*).

    `verify.check_article` 은 **"지금"만** 안다 — *우리 경기가 언제인지*는 모른다.
    그래서 *"킥오프 뒤에 나온 자료"* 를 못 걸렀고, 그 검사는 §3 스키마에만 있었다.
    그런데 **단계 4 측정은 사실을 직접 센다** → 구멍이 측정에 그대로 비쳤다:

        실측 2026-10-02: 봇이 낸 순위 **2위** ↔ 정답지 **4위** (값 다름 1건)
        = 경기(3-2 승) **뒤**의 순위표를 경기 전 사실로 썼다
        고친 뒤: 값 다름 **0건** · 재현율 29% → **14%**(정직한 수)

    ⚠️ `live_score` 는 예외다 — 그 세포는 **경기 중**을 보라고 있다.
    """
    import asyncio
    from datetime import datetime, timedelta, timezone

    from app.blackboard import Blackboard, Fact
    from app.net import Fetched, Net

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **시간에 썩는 고정물이었다** (실측 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  종전에는 킥오프를 `2026-10-01` 로 **박아** 뒀다. 이 시험의 둘째 경우는
    #  *"킥오프 2시간 전 기사는 통과한다"* 인데, 그 기사 발행이 `09-30 02:00` 으로
    #  고정되어 **신선도 창(2일)** 이 10-03 에 지나 버렸다 → `unknown`.
    #  🔴 그래서 **지금을 기준으로** 만든다 — 날짜를 박으면 시험이 달력에 따라
    #     빨개지고, 그러면 진짜 결함과 구분할 수 없다.
    #  ⚠️ `cassette.reference_now()` 가 세포의 "지금"이다 — 그것과 같은 시계를 쓴다.
    from app import cassette as _cs
    kick = _cs.reference_now() + timedelta(hours=1)

    def _make(qtype: str, when: datetime):
        def _parse(payload, q):
            return [Fact(question_id=q.id, value={"x": 1}, hardness="soft",
                         published_at=when, article_title="표",
                         source="https://ok.example/x")]
        cell = C.Cell(
            C.Question(qtype, "L:팀:2026-10-01", team="팀", league="L",
                       deadline=kick),
            [C.Source("표", "url", url="https://ok.example/x", tier=1,
                      parse=_parse, verify=True)],
            budget=C.Budget(searches=0, fetches=1))
        net = Net()

        async def _get(url, **k):
            return Fetched(url, True, 200, "{}")

        net.get = _get                              # type: ignore[assignment]
        bb = Blackboard()
        state = asyncio.run(cell.run(net, bb, search=None, scores=None))
        return state, cell, bb

    # 🔴 킥오프 **뒤** 자료 → 거부되고 사유가 남는다
    state, cell, _ = _make(C.Q_LINEUP, kick + timedelta(minutes=73))
    assert state != "found", state
    assert any("경기 후 자료" in t for t in cell.tried), cell.tried

    # 🔴 킥오프 **전** 자료 → 통과한다(날짜 검사를 느슨하게 만든 것이 아니다)
    state2, _, _ = _make(C.Q_LINEUP, kick - timedelta(hours=2))
    assert state2 == "found", state2

    # ⚠️ `live_score` 는 **경기 중**을 보라고 있다 — 막으면 그 세포가 죽는다
    state3, _, _ = _make(C.Q_LIVE, kick + timedelta(minutes=30))
    assert state3 == "found", state3
