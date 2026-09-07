"""MLB 폴링 창 — 시각을 코드에 박지 않는다.

🔴 실측 2026-09-07 (운영 DB, 최근 30일 MLB 337경기):
     01시 7 · 02시 40 · 03시 25 · 04시 9  = **81경기(24%)**
   이 경기들은 `mlb_pregame_5m` 의 `CronTrigger(hour="5-11")` 밖이라
   폴링이 아예 돌지 않았다. 발송 창은 T-180 에 열리고 보장선은 T-30 인데
   폴링이 자고 있었으므로, `CLAUDE.md` 발송 규율의 "첫 카드 보장선 T-30"이
   그 24% 에는 적용된 적이 없다.

   KBO·NPB 는 같은 결함(`hour="17,18"`)을 이미 고쳤다 — 이 파일은 MLB 가
   그 자리로 되돌아가지 않게 못박는다.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.engine.pregame_push import FIRST_CARD_GUARANTEE_MIN, SEND_OPEN_MIN
from app.scheduler import mlb_poll_window

SRC = open("app/scheduler.py", encoding="utf-8").read()


def _code_only(text: str) -> str:
    """주석 줄을 걷어낸 **실행되는 코드**만. 이력 설명이 검사에 걸리지 않게 한다.

    ⚠️ 이 파일의 검사는 소스 문자열을 본다. 주석에 옛 값을 적어 두는 것은
       사고 이력을 남기는 일이므로 막으면 안 된다 — 막을 것은 **코드**다.
    """
    out = []
    for line in text.splitlines():
        st = line.strip()
        if st.startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)


def _body(name: str) -> str:
    """그 함수의 독스트링·주석을 뺀 몸통."""
    i = SRC.index(f"async def {name}") if f"async def {name}" in SRC \
        else SRC.index(f"def {name}")
    seg = SRC[i:SRC.index("\nasync def ", i + 10)]
    if seg.count('"""') >= 2:                       # 독스트링 제거
        seg = seg[seg.index('"""', seg.index('"""') + 3) + 3:]
    return _code_only(seg)


class _Pool:
    def __init__(self, lo=None, hi=None, exc=None):
        self.row = None if lo is None else {"lo": lo, "hi": hi}
        self.exc, self.calls = exc, []

    async def fetchrow(self, sql, *a):
        self.calls.append((sql, a))
        if self.exc:
            raise self.exc
        return self.row


def _utc(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=UTC)


# 실측 사례: 2026-09-08 02:00 KST 시작 = 2026-09-07 17:00 UTC
FIRST = _utc(2026, 9, 7, 17, 0)
LAST = _utc(2026, 9, 8, 2, 0)


# ═══════════════ ① 새벽 경기가 창 안에 들어오는가

@pytest.mark.asyncio
async def test_새벽_2시_경기의_T30_에_창이_열려_있다():
    """🔴 이 파일이 존재하는 이유. 종전 크론(5-11 KST)은 여기서 자고 있었다."""
    t30 = FIRST - timedelta(minutes=FIRST_CARD_GUARANTEE_MIN)   # 01:30 KST
    open_, why = await mlb_poll_window(_Pool(FIRST, LAST), t30)
    assert open_, f"T-30 에 창이 닫혀 있다: {why}"


@pytest.mark.asyncio
async def test_발송_창이_열리는_T180_에도_창이_열려_있다():
    """폴링이 발송 창보다 먼저 돌아야 카드가 나간다."""
    t180 = FIRST - timedelta(minutes=SEND_OPEN_MIN["mlb"])
    open_, _ = await mlb_poll_window(_Pool(FIRST, LAST), t180)
    assert open_


@pytest.mark.asyncio
async def test_발송_창보다_먼저_열린다():
    """여유 20분 — `asia_poll_window` 와 같은 규약."""
    lead = SEND_OPEN_MIN["mlb"] + 20
    open_, _ = await mlb_poll_window(_Pool(FIRST, LAST),
                                     FIRST - timedelta(minutes=lead))
    assert open_


# ═══════════════ ② 필요 없을 때는 닫힌다 (5분마다 도는 값을 치른다)

@pytest.mark.asyncio
async def test_너무_이르면_닫힌다():
    too_early = FIRST - timedelta(minutes=SEND_OPEN_MIN["mlb"] + 21)
    open_, why = await mlb_poll_window(_Pool(FIRST, LAST), too_early)
    assert not open_ and "창 이전" in why


@pytest.mark.asyncio
async def test_막_경기가_시작하면_닫힌다():
    open_, why = await mlb_poll_window(_Pool(FIRST, LAST),
                                       LAST + timedelta(minutes=1))
    assert not open_ and "창 이후" in why


@pytest.mark.asyncio
async def test_예정_경기가_없으면_닫힌다():
    """⚠️ 요일·시각 분기를 넣지 않는다 — 경기가 없으면 자연히 닫힌다."""
    open_, why = await mlb_poll_window(_Pool(), _utc(2026, 9, 7, 12))
    assert not open_ and "없음" in why


@pytest.mark.asyncio
async def test_조회_실패는_닫힘이다():
    """모르는 것을 폴링의 근거로 쓰지 않는다."""
    open_, why = await mlb_poll_window(_Pool(exc=RuntimeError("db")), FIRST)
    assert not open_ and "실패" in why


@pytest.mark.asyncio
async def test_pool_이_없으면_닫힌다():
    open_, _ = await mlb_poll_window(None, FIRST)
    assert not open_


# ═══════════════ ③ 날짜 기준 — KST 로 자르면 새벽 경기가 또 빠진다

@pytest.mark.asyncio
async def test_슬레이트를_미국_동부_날짜로_고른다():
    """⚠️ `CLAUDE.md` 규칙 5. KST 날짜로 자르면 01~04시 KST 경기가
    전날 슬레이트로 밀려 창이 다시 닫힌다."""
    pool = _Pool(FIRST, LAST)
    await mlb_poll_window(pool, FIRST)
    sql, args = pool.calls[0]
    assert "America/New_York" in sql
    assert "Asia/Seoul" not in sql


def test_슬레이트_날짜_규칙을_다시_쓰지_않는다():
    """사본 금지 — `mlb_slate_date()` 가 원본이다."""
    assert "mlb_slate_date()" in _body("mlb_poll_window")


def test_발송창_상수를_베껴_적지_않는다():
    """새 상수를 만들지 않는다 — `SEND_OPEN_MIN` 이 원본이다."""
    body = _body("mlb_poll_window")
    assert 'SEND_OPEN_MIN["mlb"]' in body
    assert "180" not in body, "발송 창 값을 손으로 적었다"


# ═══════════════ ④ 배선 — 크론에 시각이 박혀 있으면 창은 무의미하다

def _registration(job_id: str) -> str:
    """그 잡의 **등록 줄**만. 독스트링·주석의 이력 설명에 걸리지 않는다.

    ⚠️ `_JOB_TRIGGERS` 는 스케줄러가 뜬 뒤에 채워지므로 임포트 시점에는
       비어 있다(실측). 그래서 트리거 객체가 아니라 등록부를 본다.
    """
    lines = SRC.splitlines()
    for i, line in enumerate(lines):
        if f'("{job_id}"' not in line or line.strip().startswith("#"):
            continue
        # 튜플이 닫힐 때까지만 읽는다 — 뒤따르는 주석을 삼키지 않는다.
        buf, depth = [], 0
        for cur in lines[i:]:
            body = cur.split("#", 1)[0] if cur.strip().startswith("#") else cur
            buf.append(body)
            depth += body.count("(") - body.count(")")
            if depth <= 0:
                break
        return "\n".join(buf)
    raise AssertionError(f"{job_id} 등록 줄을 찾지 못했다")


def test_크론에_시각이_박혀_있지_않다():
    """🔴 회귀 방지. 이 한 줄이 24% 를 결정했다.

    주석·독스트링의 이력 설명은 남겨도 되지만 **등록 줄**에 시각이 박히면
    안 된다. 그 한 줄이 01~04시 KST 81경기의 운명을 정한다.
    """
    reg = _registration("mlb_pregame_5m")
    assert "IntervalTrigger(minutes=5)" in reg
    assert "CronTrigger" not in reg, f"등록 줄에 크론이 남아 있다:\n{reg}"
    assert "hour=" not in reg, f"등록 줄에 시각이 박혀 있다:\n{reg}"


def test_아시아_폴링도_같은_규약이다():
    """KBO·NPB 가 먼저 고친 자리 — 함께 지킨다."""
    for job in ("asia_pregame_5m", "npb_pregame_2m"):
        reg = _registration(job)
        assert "IntervalTrigger" in reg and "hour=" not in reg


def test_폴링이_창_게이트를_실제로_부른다():
    """게이트를 만들고 안 부르면 없는 것과 같다."""
    body = _body("mlb_pregame_poll")
    assert "await mlb_poll_window(pool, now)" in body
    assert "await redis.aclose()" in body, "창이 닫혔을 때 연결을 놓아야 한다"


def test_워치독은_주기를_트리거에서_읽는다():
    """주기를 손으로 적으면 크론→인터벌 변경이 곧 오탐이 된다.
    `OPEN.md` 에 이미 그 부류의 오탐이 기록돼 있다."""
    w = open("app/watchdog.py", encoding="utf-8").read()
    i = w.index("def _next_expected")
    seg = _code_only(w[i:w.index("\ndef ", i + 10)])
    assert "_JOB_TRIGGERS" in seg and "get_next_fire_time" in seg
