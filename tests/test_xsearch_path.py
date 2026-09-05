"""[AI 뉴스층 2026-09-06] x_search — 경로 테스트.

🔴 ENGINEERING §2 규율: "신규 기능은 기능 테스트가 아니라 **경로 테스트**로
   완결한다. 모든 진입 지점에서 발동을 시뮬로 증명하기 전까지 '배선됨'이라
   말하지 않는다." 이 파일이 그 증명이다.

🔴 **RSS 0건이 판별에 도달해야 한다.** 재료가 아예 없는 경기가 바로 AI 층이
   필요한 경우인데, `if rss_count:` 같은 판별을 쓰면 0건이 통째로 빠진다.
🔴 **요약문을 저장하지 않는다.** AI 가 쓴 문장이 판정 재료가 되면 제2의
   환각 경로다. 헤드라인·URL·시각·계정만 남긴다.
🔴 **URL 이 실재해야 자료2 후보다.** 지어낸 링크는 fetch 에서 걸러진다.
"""
import pytest

from app.collectors import xsearch as xs


class _Redis:
    def __init__(self):
        self.kv = {}

    async def set(self, k, v, ex=None, nx=False):
        if nx and k in self.kv:
            return None
        self.kv[k] = v
        return True

    async def incr(self, k):
        self.kv[k] = int(self.kv.get(k, 0)) + 1
        return self.kv[k]

    async def expire(self, k, ex):
        return True


# ─────────────────── 발동 판별 ───────────────────

class _LegacyCfg:
    """상황 상시를 끈 설정 — **종전 조건**(라인업 정찰)만 본다.

    🔴 [2026-09-06] 기본값은 이제 `scout_xsearch_situation=True` 라 전 경기가
       발동한다(사용자 지시: 경기가 아니라 변수를 서치한다). 종전 두 조건은
       사라진 게 아니라 **상시가 꺼졌을 때의 폴백**이므로 여기서 계속 잠근다.
    """

    scout_xsearch_situation = False
    scout_xsearch_rss_floor = 5
    scout_xsearch_lineup_min = 90.0


@pytest.mark.parametrize("rss,lineup,mins,fire", [
    (0,  "confirmed", 300, True),    # 🔴 0건도 발동한다
    (4,  "confirmed", 300, True),    # RSS < 5
    (5,  "confirmed", 300, False),
    (20, "predicted", 60,  True),    # T-90 안 · 미확정
    (20, "confirmed", 60,  False),   # 확정이면 안 한다
    (20, "predicted", 300, False),   # 아직 T-90 밖
    (20, None,        None, False),  # 시각 미상 — 모르면 발동하지 않는다
])
def test_fire_conditions_when_situation_switch_is_off(rss, lineup, mins, fire):
    got, why = xs.should_fire(rss, lineup, mins, _LegacyCfg())
    assert got is fire, why


def test_zero_rss_reaches_the_check():
    """🔴 지난 시뮬 결함① 교훈 — 0건 경로가 판별에 도달하는지."""
    fire, why = xs.should_fire(0, "confirmed", 300, _LegacyCfg())
    assert fire is True and "0건" in why


def test_situation_mode_fires_for_every_game():
    """기본값에서는 종목·라인업과 무관하게 발동한다 (경기당 1콜·캡 내)."""
    from app.config import get_settings

    s = get_settings()
    assert s.scout_xsearch_situation is True
    for args in ((23, "confirmed", -16), (24, "none", 519), (5, "confirmed", 300)):
        fire, why = xs.should_fire(*args, s)
        assert fire is True and "상황" in why, (args, why)


# ─────────────────── 상한 ───────────────────

@pytest.mark.asyncio
async def test_once_per_game():
    r = _Redis()
    assert await xs._once_ok(r, "kbo", 1, "2026-09-06") is True
    assert await xs._once_ok(r, "kbo", 1, "2026-09-06") is False   # 재틱 스킵
    assert await xs._once_ok(r, "kbo", 2, "2026-09-06") is True    # 다른 경기는 통과


@pytest.mark.asyncio
async def test_daily_cap_boundary(monkeypatch):
    """캡 12 — 12번째 허용, 13번째 차단."""
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("SCOUT_XSEARCH_DAILY_CAP", "12")
    s = get_settings()
    r = _Redis()
    r.kv["xsearch:calls:2026-09-06"] = 11        # 카운터 11 세팅
    try:
        assert await xs._cap_ok(r, "2026-09-06", s) is True    # 12번째
        assert await xs._cap_ok(r, "2026-09-06", s) is False   # 13번째 차단
    finally:
        get_settings.cache_clear()


# ─────────────────── 환각 방어 ───────────────────

def test_items_without_url_or_time_are_dropped():
    txt = """[
      {"headline":"선발 변경","url":"https://x.com/a/1","at":"2026-09-06T10:00","account":"@a"},
      {"headline":"URL 없음","at":"2026-09-06T10:00"},
      {"headline":"시각 없음","url":"https://x.com/a/2"},
      {"headline":"","url":"https://x.com/a/3","at":"2026-09-06T10:00"}
    ]"""
    got = xs.parse_items(txt)
    assert len(got) == 1
    assert got[0]["url"] == "https://x.com/a/1"
    assert got[0]["source"] == "xsearch"
    assert got[0]["account"] == "@a"


def test_no_summary_field_is_kept():
    """🔴 AI 요약문은 저장하지 않는다."""
    txt = ('[{"headline":"h","url":"https://x.com/a/1","at":"2026-09-06T10:00",'
           '"summary":"모델이 쓴 요약","analysis":"모델 해석"}]')
    got = xs.parse_items(txt)[0]
    assert "summary" not in got and "analysis" not in got
    assert set(got) == {"title", "url", "at", "account", "source"}


def test_malformed_response_yields_nothing():
    assert xs.parse_items("찾은 것이 없습니다") == []
    assert xs.parse_items("") == []
    assert xs.parse_items("[") == []


@pytest.mark.asyncio
async def test_dead_urls_are_discarded_and_counted(monkeypatch):
    class _R:
        def __init__(self, code): self.status_code = code

    class _C:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, u):
            if "dead" in u:
                return _R(404)
            if "boom" in u:
                raise RuntimeError("net")
            return _R(200)

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _C)
    items = [{"url": "https://x.com/ok"}, {"url": "https://x.com/dead"},
             {"url": "https://x.com/boom"}]
    kept, stat = await xs.verify_urls(items)
    assert len(kept) == 1 and stat == {"ok": 1, "no_url": 0, "dead": 2}


# ─────────────────── 배선 (경로) ───────────────────

def test_pipeline_always_logs_the_check():
    """🔴 발동/미발동 어느 쪽이든 판별 로그가 남아야 경로가 돌았음을 안다."""
    from pathlib import Path

    src = Path("app/pipeline.py").read_text(encoding="utf-8")
    assert "_maybe_xsearch" in src
    assert '"[scout] xsearch 판별 game=%s 발동=%s' in src
    # 판별 로그가 **enabled 검사보다 앞**이어야 한다
    i_log = src.index("[scout] xsearch 판별")
    i_gate = src.index("if not fire or not s.scout_xsearch_enabled:")
    assert i_log < i_gate, "꺼져 있으면 판별 로그도 안 남는다"


def test_no_new_table():
    """적재는 기존 뉴스 키 경로 — 새 테이블을 만들지 않는다."""
    from pathlib import Path

    assert "xsearch" not in Path("db/schema.sql").read_text(encoding="utf-8")
    src = Path("app/collectors/xsearch.py").read_text(encoding="utf-8")
    assert "CREATE TABLE" not in src and "INSERT INTO" not in src


def test_judgement_path_is_isolated():
    """🔴 기존 grok 산문 경로와 섞이지 않는다."""
    import inspect

    src = inspect.getsource(xs)
    for banned in ("live_briefing", "sentiment", "counter_briefing", "delta_check"):
        assert banned not in src, banned
    assert "_search_call" in src        # 저수준 호출만 재사용한다
