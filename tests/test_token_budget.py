"""BUD-1 — 유료 LLM 일일 토큰 상한의 계약.

🔴 왜 이 모듈이 생겼나. 2026-09-11 유료 전면 전환(gemini 주전 · xai 폴백) 뒤
   상한이 걸리는 경로가 `anthropic_daily_cap` 하나였다. 그 캡은 Anthropic 만
   보는데 운영은 gemini·xai 로 돈다 — **지출 경로에 상한도 카운터도 없었다.**
   뿌리는 `is_free()` 가 독스트링("확실하지 않으면 False")과 **반대로** 구현돼
   모르는 provider 를 전부 무료로 통과시킨 것이다.

🔴 이 파일은 **배선까지** 잠근다. 모듈이 존재하는 것과 호출되는 것은 다르다 —
   실사고 PGP-2: "죽으면 알리게" 수정이 5일 전에 배선이 끊긴 함수 안에 들어갔다.
"""

import pytest

from app.llm import token_budget as tb


class _Redis:
    """`get`/`incrby`/`expire` 만 쓰는 최소 목."""

    def __init__(self, start=0, boom=False):
        self.store: dict[str, int] = {}
        self.boom = boom
        self.start = start

    async def get(self, key):
        if self.boom:
            raise RuntimeError("redis down")
        return self.store.get(key, self.start)

    async def incrby(self, key, n):
        if self.boom:
            raise RuntimeError("redis down")
        self.store[key] = int(self.store.get(key, self.start)) + int(n)
        return self.store[key]

    async def expire(self, key, ttl):
        return True


@pytest.fixture
def cap(monkeypatch):
    """상한을 원하는 값으로. 원본은 config 이므로 그것을 갈아끼운다."""
    def _set(n):
        monkeypatch.setattr(tb, "cap_for", lambda provider: n)
    return _set


# ═══════════════ ① 무엇을 세는가 — 유료만

@pytest.mark.asyncio
async def test_무료_provider_는_세지_않는다():
    """상한의 목적은 지출이다. 무료 티어는 카운터를 더럽히지 않는다."""
    r = _Redis()
    n = await tb.note_usage(r, "groq", role="form", model="q",
                            input_tokens=1000, output_tokens=500)
    assert n == 0 and r.store == {}


@pytest.mark.asyncio
async def test_유료_provider_는_입출력을_합쳐_누적한다():
    r = _Redis()
    await tb.note_usage(r, "gemini", role="matchup", model="g",
                        input_tokens=4000, output_tokens=1500)
    await tb.note_usage(r, "gemini", role="form", model="g",
                        input_tokens=300, output_tokens=200)
    assert await tb.spent_today(r, "gemini") == 6000


@pytest.mark.asyncio
async def test_provider_별로_따로_센다():
    r = _Redis()
    await tb.note_usage(r, "gemini", role="matchup", model="g",
                        input_tokens=100, output_tokens=0)
    await tb.note_usage(r, "xai", role="matchup", model="k",
                        input_tokens=700, output_tokens=0)
    assert await tb.spent_today(r, "gemini") == 100
    assert await tb.spent_today(r, "xai") == 700


@pytest.mark.asyncio
async def test_usage_가_없으면_0으로_덮지_않는다(caplog):
    """🔴 0 으로 적으면 '안 썼다'와 '모른다'가 같아진다 — 상한이 헐거워진다."""
    import logging

    r = _Redis()
    with caplog.at_level(logging.WARNING):
        n = await tb.note_usage(r, "gemini", role="matchup", model="g",
                                input_tokens=None, output_tokens=None)
    assert n == 0 and r.store == {}, "모르는데 누적했다"
    assert "usage 없음" in caplog.text, "조용히 지나갔다"


# ═══════════════ ② 언제 막는가

@pytest.mark.asyncio
async def test_상한이_0이면_막지_않는다_관측만(cap):
    """🔴 실측 없이 숫자를 정하지 않는다. 0 인 동안은 세기만 한다."""
    cap(0)
    r = _Redis(start=10 ** 9)
    ok, why = await tb.allowed(r, "gemini")
    assert ok is True and why is None


@pytest.mark.asyncio
async def test_상한을_넘으면_막는다(cap):
    cap(1000)
    r = _Redis()
    await tb.note_usage(r, "gemini", role="matchup", model="g",
                        input_tokens=600, output_tokens=500)   # 1100
    ok, why = await tb.allowed(r, "gemini")
    assert ok is False
    assert "1,000" in why and "1,100" in why


@pytest.mark.asyncio
async def test_상한_안이면_통과한다(cap):
    cap(1000)
    r = _Redis()
    await tb.note_usage(r, "gemini", role="matchup", model="g",
                        input_tokens=400, output_tokens=100)
    assert (await tb.allowed(r, "gemini"))[0] is True


@pytest.mark.asyncio
async def test_무료_provider_는_상한과_무관하다(cap):
    cap(10)
    r = _Redis(start=10 ** 6)
    assert (await tb.allowed(r, "groq"))[0] is True


@pytest.mark.asyncio
async def test_redis_가_없으면_막지_않는다(cap):
    """모른다고 판정을 멈추면 카드가 안 나간다. 그쪽이 더 나쁘다."""
    cap(10)
    assert (await tb.allowed(None, "gemini"))[0] is True
    assert await tb.note_usage(None, "gemini", role="matchup", model="g",
                               input_tokens=99, output_tokens=99) == 0


@pytest.mark.asyncio
async def test_redis_가_고장이면_막지_않는다(cap):
    cap(10)
    assert (await tb.allowed(_Redis(boom=True), "gemini"))[0] is True


# ═══════════════ ③ 경보 — 잔량이 신호다

@pytest.mark.asyncio
async def test_80퍼센트를_넘으면_경보한다(cap, monkeypatch):
    """비율의 원본은 `judge_route.PAID_WARN_RATIO` 다 — 사본을 만들지 않는다."""
    cap(1000)
    sent = []

    async def _wd(code, detail, target=None):
        sent.append((code, detail, target))

    import app.alerts as alerts
    monkeypatch.setattr(alerts, "watchdog", _wd)

    r = _Redis()
    await tb.note_usage(r, "gemini", role="matchup", model="g",
                        input_tokens=700, output_tokens=0)     # 70% — 조용
    assert sent == []
    await tb.note_usage(r, "gemini", role="matchup", model="g",
                        input_tokens=200, output_tokens=0)     # 90% — 경보
    assert len(sent) == 1
    code, detail, target = sent[0]
    assert code == "W-LLM-PAID" and target == "gemini"
    assert "900" in detail


def test_경보_코드는_원본에_있는_것만_쓴다():
    """🔴 사본 금지 — 새 코드를 만들지 않았다. 라벨의 원본은 alerts 다."""
    from app.alerts import WATCHDOG_CODES

    assert "W-LLM-PAID" in WATCHDOG_CODES


def test_경보_비율은_판정캡과_같은_원본을_쓴다():
    from app.llm.judge_route import PAID_WARN_RATIO

    src = open("app/llm/token_budget.py", encoding="utf-8").read()
    assert "PAID_WARN_RATIO" in src and "0.8" not in src, "비율을 사본으로 적었다"
    assert 0 < PAID_WARN_RATIO < 1


# ═══════════════ ④ 배선 — 존재하는 것과 불리는 것은 다르다

@pytest.mark.asyncio
async def test_판정_사슬이_토큰을_실제로_누적한다(monkeypatch, cap):
    """🔴 실사고 PGP-2: 배선이 끊긴 함수 안에 수정이 들어갔다."""
    cap(0)
    import app.engine.team_form as tf
    import app.llm.openai_compat as oc

    r = _Redis()
    monkeypatch.setattr(tf, "_redis", lambda: _async(r))

    async def _fake(provider, model, prompt, **kw):
        return {"ok": True, "text": '{"p_home": 0.55}', "elapsed": 1.0,
                "error": None, "status": 200,
                "usage": {"prompt_tokens": 5000, "completion_tokens": 1200}}

    monkeypatch.setattr(oc, "complete", _fake)
    out = await tf._complete_free([("gemini", "gemini-3.7-flash")], "p",
                                  max_tokens=100, role="matchup")
    assert out == '{"p_home": 0.55}'
    assert await tb.spent_today(r, "gemini") == 6200, "카운터가 배선되지 않았다"


@pytest.mark.asyncio
async def test_상한을_넘긴_provider_는_호출_자체를_건너뛴다(monkeypatch, cap):
    """넘은 채로 계속 부르면 상한이 무의미하다."""
    cap(100)
    import app.engine.team_form as tf
    import app.llm.openai_compat as oc

    r = _Redis()
    r.store[tb.KEY.format(provider="gemini", date=tb._today())] = 999
    monkeypatch.setattr(tf, "_redis", lambda: _async(r))

    called = []

    async def _fake(provider, model, prompt, **kw):
        called.append(provider)
        return {"ok": True, "text": "{}", "elapsed": 1.0, "error": None,
                "status": 200, "usage": {}}

    monkeypatch.setattr(oc, "complete", _fake)
    out = await tf._complete_free([("gemini", "gemini-3.7-flash")], "p",
                                  max_tokens=100, role="matchup")
    assert called == [], "상한을 넘겼는데 불렀다"
    assert out is None


@pytest.mark.asyncio
async def test_상한을_넘긴_뒤에도_다음_후보로_넘어간다(monkeypatch, cap):
    """🔴 반대 위험: 가드가 카드를 통째로 막으면 안 된다.

    gemini 가 상한에 닿아도 xai 가 남아 있으면 그 경기는 판정을 받는다.
    """
    import app.engine.team_form as tf
    import app.llm.openai_compat as oc

    monkeypatch.setattr(tb, "cap_for",
                        lambda provider: 100 if provider == "gemini" else 0)
    r = _Redis()
    r.store[tb.KEY.format(provider="gemini", date=tb._today())] = 999
    monkeypatch.setattr(tf, "_redis", lambda: _async(r))

    called = []

    async def _fake(provider, model, prompt, **kw):
        called.append(provider)
        return {"ok": True, "text": '{"ok": 1}', "elapsed": 1.0, "error": None,
                "status": 200, "usage": {"prompt_tokens": 10,
                                         "completion_tokens": 5}}

    monkeypatch.setattr(oc, "complete", _fake)
    out = await tf._complete_free(
        [("gemini", "gemini-3.7-flash"), ("xai", "grok-4.3-latest")], "p",
        max_tokens=100, role="matchup")
    assert called == ["xai"], called
    assert out == '{"ok": 1}'


async def _async(v):
    return v


# ═══════════════ ⑤ 목 표시가 실제 판정 사슬을 본다 (A4 실측에서 나온 것)

def test_판정_주전_provider_의_목_표시가_존재한다(monkeypatch):
    """🔴 [BUD-1] 실측 2026-09-11: 키를 전부 빼도 gemini 는 표시되지 않았다.

    `mock_judge` 는 anthropic 키만, `mock_grok` 은 xai 키만 봤다. 2026-09-11
    전환으로 판정 주전은 gemini 인데 그 축이 표시에 아예 없었다.
    """
    from app.config import Settings

    s = Settings(GEMINI_API_KEY="", FORCE_MOCK=False)
    assert s.mock_gemini is True
    s2 = Settings(GEMINI_API_KEY="k", FORCE_MOCK=False)
    assert s2.mock_gemini is False


def test_기동_로그가_gemini_를_포함한다():
    """표시 목록의 원본은 `log_mock_status` 다 — 사본을 만들지 않고 소스를 본다."""
    src = open("app/config.py", encoding="utf-8").read()
    i = src.index("def log_mock_status")
    body = src[i:i + 400]
    assert '"gemini"' in body, "판정 주전이 기동 표시에서 빠져 있다"
