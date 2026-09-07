"""테스트 공용 픽스처: 격리된 analystbot_test DB 생성 후 스키마 적용."""

import os

# 테스트는 외부 API를 절대 치지 않는다 — config를 읽기 전에 강제 목 모드 고정.
os.environ.setdefault("FORCE_MOCK", "true")
# 운영 기본값은 grok,perplexity disabled. 테스트는 기존 경로(목 리서치)를 유지한다.
os.environ.setdefault("DISABLED_PROVIDERS", "")
# 🔴 [v1.4 2026-09-07] 시장 동의 게이트를 **테스트 기본에서는 끈다.**
#   이 스위치가 켜져 있으면 시장값이 없는 픽스처가 전부 `market_missing` 으로
#   탈락해, 확률·라인업·표본 게이트를 검사하던 테스트 15건이 시장 부재에
#   뭉개진다 — 무엇이 깨졌는지 알 수 없게 된다.
#   ⚠️ 스위치 자체는 `tests/test_market_agree_gate.py` 가 **켜고** 검사하고,
#      운영 기본값이 True 인 것은 같은 파일이 따로 잠근다. 여기서 끈다고
#      제품 기본값이 바뀌지 않는다.
os.environ.setdefault("MARKET_AGREE_REQUIRED", "false")

import asyncpg
import pytest
import redis.asyncio as aioredis

from app.db import apply_schema

# ------------------------------------------------- 외부 HTTP 전면 차단 (P5-2)
#
# 위 `FORCE_MOCK=true` 는 **API 키가 있는 소스만** 목으로 돌린다.
# `config.py` 의 목 판정이 전부 `force_mock or not <API키>` 형태이기 때문이다.
# 무인증 소스(Statcast·네이버·Yahoo재팬·KBO 기록실·open-meteo·statsapi)는
# 걸 고리가 없어 **테스트에서 실제 트래픽이 나갔다.**
#
#   실측 2026-08-30: test_quota / test_pipeline_bot / test_data_provenance 가
#   run_pipeline(sport="mlb") 에서 baseballsavant.mlb.com 으로 30일치 투구
#   원본을 받느라 2분 넘게 멈춰 있었다. 세 파일은 사실상 실행 불가였고,
#   그 안의 회귀 방어는 한 번도 돌지 않았다.
#
# ⚠️ 이 파일 위쪽 `_no_outbound_telegram` 독스트링은 "httpx 전역 교체는 쓰지
#    않는다"고 적어 두었다. **그 결정을 여기서 뒤집는다.** 이유가 다르다 —
#    그때는 클라이언트를 통째로 가짜로 갈아끼워 스로틀·재시도 로직 테스트까지
#    깨졌다. 여기서는 `send` 만 가로채고 **localhost 는 통과**시키므로 로컬
#    Redis·Postgres 와 HTTP 동작 자체를 검사하는 테스트는 영향이 없다.
#    그리고 밖으로 나가는 호출은 **깨져야 한다** — 그게 목이 필요한 지점의
#    지도를 그리는 유일한 방법이다.
#
# 실운영 영향 없음: conftest.py 는 pytest 가 수집할 때만 로드된다.
# `app/` 어디에서도 import 하지 않는다(`grep -rn "conftest" app/` → 0건).

_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"}
_CURRENT_TEST = {"id": "<수집 단계>"}
BLOCKED_CALLS: list[tuple[str, str]] = []


class OutboundHTTPBlocked(RuntimeError):
    """테스트가 외부로 HTTP를 냈다 — 목이 필요한 지점이다."""


def _guard(kind: str, url: str) -> None:
    from urllib.parse import urlsplit

    host = (urlsplit(url).hostname or "").lower()
    if host in _ALLOWED_HOSTS:
        return
    BLOCKED_CALLS.append((_CURRENT_TEST["id"], url))
    raise OutboundHTTPBlocked(
        f"\n  테스트가 외부 HTTP를 냈다 — 목으로 대체해야 한다."
        f"\n    테스트: {_CURRENT_TEST['id']}"
        f"\n    경로  : {kind}"
        f"\n    URL   : {url[:200]}"
        f"\n  (허용: {sorted(_ALLOWED_HOSTS)} — 로컬 Redis·Postgres용)"
    )


def _install_http_block() -> None:
    for mod_name in ("httpx", "httpx2"):
        try:
            hx = __import__(mod_name)
        except ImportError:
            continue
        _a, _s = hx.AsyncClient.send, hx.Client.send

        async def a_send(self, request, *a, __o=_a, **kw):
            _guard("httpx-async", str(request.url))
            return await __o(self, request, *a, **kw)

        def s_send(self, request, *a, __o=_s, **kw):
            _guard("httpx-sync", str(request.url))
            return __o(self, request, *a, **kw)

        hx.AsyncClient.send, hx.Client.send = a_send, s_send

    try:
        import requests.adapters as ra
    except ImportError:
        pass
    else:
        _r = ra.HTTPAdapter.send

        def r_send(self, request, *a, **kw):
            _guard("requests", str(request.url))
            return _r(self, request, *a, **kw)

        ra.HTTPAdapter.send = r_send

    import urllib.request as ur

    _u = ur.urlopen

    def u_open(url, *a, **kw):
        _guard("urllib", str(getattr(url, "full_url", url)))
        return _u(url, *a, **kw)

    ur.urlopen = u_open


_install_http_block()


def pytest_runtest_setup(item):
    _CURRENT_TEST["id"] = item.nodeid


def pytest_terminal_summary(terminalreporter, *_a, **_kw):
    if not BLOCKED_CALLS:
        return
    tr = terminalreporter
    tr.write_sep("=", "외부 HTTP 차단 — 목이 필요한 지점", red=True)
    seen: dict[str, set] = {}
    for nodeid, url in BLOCKED_CALLS:
        from urllib.parse import urlsplit
        seen.setdefault(nodeid, set()).add(urlsplit(url).netloc)
    for nodeid, hosts in sorted(seen.items()):
        tr.write_line(f"  {nodeid}\n      → {', '.join(sorted(hosts))}")

ADMIN_DSN = "postgresql://analyst:analyst@localhost:5432/postgres"
TEST_DB = "analystbot_test"
TEST_DSN = f"postgresql://analyst:analyst@localhost:5432/{TEST_DB}"


@pytest.fixture
async def db_pool():
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
    await admin.execute(f"CREATE DATABASE {TEST_DB}")
    await admin.close()

    pool = await asyncpg.create_pool(TEST_DSN)
    async with pool.acquire() as conn:
        await apply_schema(conn)
    yield pool
    await pool.close()


# ------------------------------------------------- 전역 풀이 테스트 경계를 넘지 않게

@pytest.fixture(autouse=True)
async def _reset_global_pool():
    """`app.db._pool`(모듈 전역)을 테스트마다 폐기한다.

    🔴 이게 없으면 **행(hang)이다. 실패가 아니라 영원히 안 끝난다.**
       pytest-asyncio는 테스트마다 새 이벤트 루프를 만드는데, `get_pool()`이
       만든 asyncpg 풀은 만들어진 루프에 묶인 채 전역에 남는다. 다음 테스트가
       새 루프에서 그 풀을 다시 잡으면 await가 영원히 깨어나지 않는다.

       절제 실험(2026-08-30):
         test_pipeline_falls_back_to_mock_judge_on_quota 단독      → 2.22초 종료
         test_bot_replies_friendly_message_on_quota 를 앞에 두면   → 행
         같은 조합 + 전역 풀 폐기                                   → 2.59초 종료
       앞 테스트가 `answer_query`→`get_pool()`로 풀을 만들고, 뒤 테스트가
       `pipeline.py`·`collectors/mlb.py`의 `get_pool()` 경유로 그걸 다시 잡았다.
       faulthandler 스택은 루프가 select()에 잠긴 모습, lsof는 외부 소켓 0개
       (postgres만) — 네트워크 대기가 아니라 죽은 루프 대기였다.

       이 행은 P5-2(외부 HTTP 차단)와 무관하다. HEAD의 conftest로 되돌려도
       같은 조합이 그대로 행이었다.

    teardown은 그 테스트의 루프 안에서 돌므로 여기서는 정상적으로 close 할 수
    있다. close가 실패해도 참조만은 반드시 끊는다 — 끊지 않으면 다음 테스트가
    같은 덫에 걸린다.

    ⚠️ 조사 후보(지금 고치지 않는다): **실운영에서도 이벤트 루프가 재생성되는
       경로가 있다면 같은 행이 가능하다.** 봇·스케줄러는 루프 하나로 도는 것을
       전제하지만, 재시작·재연결 로직이 `asyncio.run()`을 두 번 부르는 곳이
       있는지 확인되지 않았다. → docs/AUDIT_OPEN_ITEMS.md
    """
    yield
    import app.db as db

    if db._pool is None:
        return
    try:
        await db.close_pool()
    except Exception:
        db._pool = None
        db._schema_applied = False


@pytest.fixture
async def redis_client():
    r = aioredis.from_url("redis://localhost:6379/15", decode_responses=True)
    await r.flushdb()
    yield r
    await r.flushdb()
    await r.aclose()


# ---------------------------------------------------------------- 외부 발신 차단

@pytest.fixture(autouse=True)
def _no_outbound_telegram(monkeypatch, request):
    """테스트는 절대 실제 텔레그램으로 발송하지 않는다.

    실사고(2026-08-25): [7] 단계 실패 알림을 붙인 뒤 `pytest`를 돌릴 때마다
    build_analysis가 테스트 픽스처로 실패 알림을 만들어 **관리자 채팅으로
    실제 발송**했다. "λ 0/5"·"리서치 13/15" 같은 실슬레이트에 없는 숫자가
    1~2분 간격으로 쏟아진 원인이 이것이다. 억제 로직 문제가 아니라
    테스트가 외부로 나간 문제였다.

    가드는 send_telegram을 **차단 스텁**으로 갈아끼운다. 스텁은 예외를 던지지 않고
    False를 반환하며 발송 시도를 기록한다 — 예외로 만들면 "토큰이 없으면 조용히
    False" 같은 정상 경로 테스트가 깨진다. 자체적으로 send_telegram을 대체하는
    테스트(test_alerts·test_quota)는 이 스텁을 덮어쓰므로 영향을 받지 않는다.

    httpx.AsyncClient를 갈아끼우는 방식은 쓰지 않는다 — 모듈 전역이라
    스로틀·수집기 테스트까지 함께 깨진다.
    """
    blocked: list[str] = []

    async def _blocked(text: str, **_kwargs) -> bool:
        blocked.append(text)
        return False

    import app.alerts as alerts_mod
    import app.notify as notify_mod

    # 발송 지점은 **하나**다 — alerts는 notify 모듈 속성으로 부른다.
    #   (종전에는 alerts가 함수를 자기 이름공간에 묶어 두 곳을 다 막아야 했고,
    #    한쪽만 막으면 조용히 새어 나갔다.)
    monkeypatch.setattr(notify_mod, "send_telegram", _blocked)
    assert not hasattr(alerts_mod, "send_telegram"), \
        "alerts가 send_telegram을 다시 자기 이름공간에 묶었다 — 발송 지점이 갈라진다"

    # 억제 상태도 격리한다. 안 하면 테스트가 **운영 Redis의 알림 예산**
    # (alert:budget, 10분 12건)을 갉아먹어 실제 장애 알림이 막힌다.
    # 실측(2026-08-25): 테스트를 돌린 뒤 KBO 파싱 실패 알림이 예산 초과로 억제됐다.
    class _MemRedis:
        def __init__(self):
            self.store: dict = {}

        async def set(self, k, v, nx=False, ex=None):
            if nx and k in self.store:
                return None
            self.store[k] = v
            return True

        async def get(self, k):
            return self.store.get(k)

        async def incr(self, k):
            self.store[k] = int(self.store.get(k, 0)) + 1
            return self.store[k]

        async def expire(self, k, sec):
            return True

        async def delete(self, *ks):
            for k in ks:
                self.store.pop(k, None)

        async def keys(self, pattern):
            return list(self.store)

        async def aclose(self):
            pass

    _mem = _MemRedis()

    async def _fake_redis():
        return _mem

    monkeypatch.setattr(alerts_mod, "_redis", _fake_redis)
    yield
    if blocked:
        # 새 코드가 알림 경로를 늘렸다는 신호 — 조용히 넘기지 않는다
        print(f"\n[conftest] 테스트 중 텔레그램 발송 {len(blocked)}건 차단됨 "
              f"(첫 건: {blocked[0][:80]!r})")


@pytest.fixture(autouse=True)
def _no_outbound_collectors(monkeypatch):
    """테스트는 외부 수집 API(Open-Meteo·statsapi 라인업)를 호출하지 않는다.

    실사고(2026-08-25): 파이프라인에 날씨·결장 수집을 붙이자 `pytest`가
    16초 → 107초가 됐다. build_analysis가 테스트에서도 실제 HTTP를 때린 것이다.
    테스트는 hermetic해야 한다 — 필요하면 각 테스트가 직접 되돌려 쓴다.
    """
    async def _empty(*a, **kw):
        return {}

    import app.collectors.absences as absences_mod
    import app.collectors.weather as weather_mod

    monkeypatch.setattr(weather_mod, "fetch_for_games", _empty)
    monkeypatch.setattr(absences_mod, "fetch_for_games", _empty)


@pytest.fixture(autouse=True)
def _api_guard_isolated():
    """회로 차단 상태를 테스트끼리 섞지 않고, 운영 Redis에도 쓰지 않는다."""
    from app import api_guard

    api_guard.reset()
    api_guard.set_network_redis(False)
    api_guard.set_redis(None)
    yield
    api_guard.reset()
    api_guard.set_redis(None)
    api_guard.set_network_redis(False)
