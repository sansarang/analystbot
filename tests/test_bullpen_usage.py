"""ORD-7 — 긁어 둔 불펜 등판을 ②의 답으로 잇는다.

사용자 지시 2026-09-12: "2번으로 해라..크롤러로 직접 긁어라"

🔴 **새로 긁지 않았다.** 조사해 보니 `pitcher_appearances` 에 이미 있었다
   (실측 2026-09-12 운영: MLB 3,573행·투수 573 · KBO 2,327 · NPB 1,437).
   만든 것은 **읽는 길**이다. 새 수집기를 만들었으면 그것이 사본이다.

🔴 왜: 실측 2026-09-12 game=5633 "텍사스 불펜·마무리 가용"을 검색이 두 차례
   모두 못 찾았다. 공개 소스가 약한 축인데 우리는 원시 기록을 갖고 있었다.
"""

import datetime as dt

import pytest

from app.collectors import bullpen_usage as BU


class _Pool:
    def __init__(self, rows=None, last=None, boom=False):
        self.rows, self.last, self.boom = rows or [], last, boom
        self.seen = []

    async def fetch(self, sql, *a):
        self.seen.append((sql, a))
        if self.boom:
            raise RuntimeError("DB 터짐")
        return self.rows

    async def fetchval(self, sql, *a):
        if self.boom:
            raise RuntimeError("DB 터짐")
        return self.last


def _row(p, d, ip, b):
    return {"pitcher": p, "d": d, "innings": ip, "batters": b}


def _jg():
    return {"game_id": 1, "sport": "mlb", "league": "MLB",
            "home": "New York Yankees", "away": "New York Mets"}


# ═══════════════ ① 질문을 겨눴을 때만 답한다

@pytest.mark.parametrize("q", [
    "Texas Rangers bullpen usage and closer availability September 11 2026",
    "신시내티 레즈 불펜 최근 3일간 연투 현황",
    "Giants relief pitchers back-to-back appearances",
    "두산 필승조 가용 여부"])
def test_불펜_질문을_알아본다(q):
    assert BU.matches(q)


@pytest.mark.parametrize("q", [
    "George Kirby injury status pitch limit",
    "Chase Field roof open or closed",
    "Texas Rangers starting lineup injury scratches"])
def test_다른_질문에는_끼어들지_않는다(q):
    """🔴 묻지 않은 것을 밀어 넣으면 순서를 바꾼 의미가 없다."""
    assert not BU.matches(q)


@pytest.mark.asyncio
async def test_안_물었으면_답하지_않는다():
    pool = _Pool([_row("A", dt.date(2026, 9, 10), 1.0, 3)], dt.date(2026, 9, 10))
    assert await BU.answers(pool, _jg(), ["Kirby injury status"]) == []
    assert pool.seen == []          # 쿼리도 안 나간다


@pytest.mark.asyncio
async def test_물었으면_양팀을_답한다():
    pool = _Pool([_row("A", dt.date(2026, 9, 10), 1.0, 3)], dt.date(2026, 9, 10))
    out = await BU.answers(pool, _jg(), ["Yankees bullpen usage last 3 days"])
    assert len(out) == 2
    assert {r["소스"] for r in out} == {"크롤러"}
    assert all(r["질문"] == "Yankees bullpen usage last 3 days" for r in out)


# ═══════════════ ② 연투는 날짜 연속으로만 정의한다

@pytest.mark.asyncio
async def test_연속된_날이면_연투다():
    pool = _Pool([_row("A", dt.date(2026, 9, 9), 1.0, 4),
                  _row("A", dt.date(2026, 9, 10), 0.333, 1)], dt.date(2026, 9, 10))
    d = await BU.recent(pool, "mlb", "T")
    a = d["투수"][0]
    assert a["연투"] is True
    assert a["이닝"] == pytest.approx(1.33, abs=0.01) and a["타자"] == 5


@pytest.mark.asyncio
async def test_하루_건너뛰면_연투가_아니다():
    pool = _Pool([_row("A", dt.date(2026, 9, 8), 1.0, 3),
                  _row("A", dt.date(2026, 9, 10), 1.0, 3)], dt.date(2026, 9, 10))
    assert (await BU.recent(pool, "mlb", "T"))["투수"][0]["연투"] is False


@pytest.mark.asyncio
async def test_같은_날_두_번은_연투가_아니다():
    """중복 적재·더블헤더를 연투로 세면 거짓이다."""
    pool = _Pool([_row("A", dt.date(2026, 9, 10), 1.0, 3),
                  _row("A", dt.date(2026, 9, 10), 1.0, 3)], dt.date(2026, 9, 10))
    assert (await BU.recent(pool, "mlb", "T"))["투수"][0]["연투"] is False


@pytest.mark.asyncio
async def test_많이_던진_투수가_앞에_온다():
    pool = _Pool([_row("A", dt.date(2026, 9, 10), 1.0, 3),
                  _row("B", dt.date(2026, 9, 9), 1.0, 3),
                  _row("B", dt.date(2026, 9, 10), 1.0, 3)], dt.date(2026, 9, 10))
    assert [p["이름"] for p in (await BU.recent(pool, "mlb", "T"))["투수"]] == ["B", "A"]


# ═══════════════ ③ 모르는 것을 없다고 하지 않는다

def test_등판_없음과_기록_없음을_가른다():
    """🔴 안 가르면 "전원 가용"이라는 거짓이 카드로 나간다."""
    t = BU.to_answer("T", {"투수": [], "마지막적재": dt.date(2026, 9, 10)})
    assert "기록 없음" in t and "구분되지 않는다" in t
    assert BU.to_answer("T", {"투수": [], "마지막적재": None}) == ""


def test_투구수처럼_보이게_쓰지_않는다():
    """🔴 투구수는 수집되지 않는다 — 타자 수가 소모 대리값이다."""
    t = BU.to_answer("T", {"투수": [{"이름": "A", "날짜": [dt.date(2026, 9, 10)],
                                    "이닝": 1.0, "타자": 3, "연투": False}],
                           "마지막적재": dt.date(2026, 9, 10)})
    assert "3타자" in t and "소모 대리값" in t
    assert "투구수는 수집되지 않아" in t


def test_역할을_추정하지_않는다():
    """🔴 `kbo_usage` 가 못박은 규약 — 응답에 마무리·셋업 라벨이 없다."""
    src = open("app/collectors/bullpen_usage.py", encoding="utf-8").read()
    body = src.split('def to_answer')[1]
    for guess in ("마무리", "셋업", "필승조", "closer"):
        assert guess not in body, guess


@pytest.mark.asyncio
async def test_DB가_터져도_판정을_막지_않는다():
    out = await BU.recent(_Pool(boom=True), "mlb", "T")
    assert out == {"투수": [], "마지막적재": None}


@pytest.mark.asyncio
async def test_pool_이_없으면_조용히_빈손이다():
    assert await BU.answers(None, _jg(), ["bullpen usage"]) == []


# ═══════════════ ④ 배선 — 있는 것과 불리는 것은 다르다

@pytest.mark.asyncio
async def test_reinforce_가_우리_기록을_얹는다(monkeypatch):
    import app.engine.deepsearch as DS

    async def _none(*a, **k):
        return []

    monkeypatch.setattr(DS, "_free_articles", _none)
    monkeypatch.setattr(DS, "_ask_pplx", _none, raising=False)
    monkeypatch.setattr(DS, "_ask_grok", _none, raising=False)
    pool = _Pool([_row("A", dt.date(2026, 9, 10), 1.0, 3)], dt.date(2026, 9, 10))
    out = await DS.reinforce(_jg(), {"조사요청": ["Yankees bullpen usage"],
                                     "갈림길": [], "변수": []}, None, pool=pool)
    assert out["출처"].get("크롤러") == 2


def test_판정이_DB_연결을_넘긴다():
    import inspect

    from app.engine import matchup as MU

    assert "pool" in inspect.signature(MU.judge_matchup).parameters
    body = inspect.getsource(MU.judge_matchup)
    assert "_reinforce(jg, _pre, redis, pool=pool)" in body


def test_파이프라인이_DB_연결을_넘긴다():
    """🔴 존재하는 것과 전달되는 것은 다르다(PGP-2)."""
    src = open("app/pipeline.py", encoding="utf-8").read()
    i = src.index("judge_matchup(jg, redis, date")
    assert "pool=pool" in src[i:i + 160]


def test_카드가_출처를_밝힌다():
    from app.engine.form_card import _SRC_KR

    assert _SRC_KR["크롤러"] == "우리 기록"
