"""[PPLX-OFF] **퍼플렉시티를 검색에 쓰지 않는다** (사용자 지시 2026-09-22).

사용자 지시 원문: "퍼플릭스는 서치에 사용하지 않는다"

🔴 실측 2026-09-22 · 운영:
```
DISABLED_PROVIDERS       'anthropic,perplexity,xai,nvidia'
is_disabled(perplexity)  True
DEEPSEARCH_PPLX_ENABLED  '0'
research_calls:2026-09-22 → None        (오늘 0콜 · 상한 60)
research_crosscheck 09-15·09-18·09-21 → checked 0
```
행위로는 이미 꺼져 있다. **문제는 목이 막혀 있지 않다는 것이다.**

🔴 **내가 처음 세운 전제는 틀렸다.** "`PerplexityClient.chat` 이 `self.mock` 만
   보므로 목이 안 막혀 있다"고 적었는데, 한 단계 아래에 이미 막혀 있다:

```
PerplexityClient.chat → BaseAPIClient._post → _request
  → api_guard.raise_if_unusable(name)
      if is_disabled(name): raise ProviderDisabledError   ← 여기
```
   `_send`(실제 HTTP) 앞에서 예외가 난다. **요청은 나가지 않는다.**
   그래서 **코드를 한 줄도 고치지 않았다** — 게이트를 더 놓으면 두 벌이 된다.

   막는 곳은 지금 셋이고 층이 다르다:
     · `api_guard.raise_if_unusable`  — **목**(모든 BaseAPIClient 경로)
     · `ask_json`                     — httpx 직호출이라 목을 안 지난다
     · `deep.py:593`·`494`            — 호출 전 조기 반환(콜 수·캐시 때문)

⚠️ 스위치를 새로 만들지 않는다 — 원본은 `DISABLED_PROVIDERS` 하나다.
   `config/rules.yaml` 에 두 번째 스위치를 두면 두 벌이 되고, 두 벌은
   어긋난다(사본 금지).

이 파일이 하는 일은 **그 사실을 잠그는 것**이다. 지시가 말로만 있으면
다음 세션이 `DISABLED_PROVIDERS` 를 지우거나 게이트를 우회하는 경로를 만든다.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def off(monkeypatch):
    """퍼플렉시티를 끈 설정. 🔴 **원본 스위치**를 쓴다."""
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DISABLED_PROVIDERS", "perplexity")
    monkeypatch.setenv("PPLX_API_KEY", "pplx-test-key-not-real")
    monkeypatch.setenv("FORCE_MOCK", "0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def on(monkeypatch):
    """⚠️ 반대 위험 — 켜면 나가야 한다. 끄기만 하는 수정이 아니다."""
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DISABLED_PROVIDERS", "")
    monkeypatch.setenv("PPLX_API_KEY", "pplx-test-key-not-real")
    monkeypatch.setenv("FORCE_MOCK", "0")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def sent(monkeypatch):
    """나간 HTTP 요청을 전부 기록한다. 🔴 **요청 0** 이 계약이다."""
    log: list[str] = []

    class _Resp:
        status_code = 200
        text = "{}"

        def json(self):
            return {"choices": [{"message": {"content": "{}"}}]}

        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, *a, **k):
            log.append(str(url))
            return _Resp()

        async def get(self, url, *a, **k):
            log.append(str(url))
            return _Resp()

        async def request(self, method, url, *a, **k):
            # 🔴 `BaseAPIClient._send` 는 `.request()` 를 쓴다 — 여기를 빠뜨리면
            #    가짜가 안 잡히고 계약이 **거짓 통과**한다(첫 판에서 겪었다).
            log.append(str(url))
            return _Resp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    return log


def test_기본값이_퍼플렉시티를_끈다():
    """🔴 환경변수를 안 줘도 꺼져 있어야 한다 — 키만 꽂으면 도는 일이 없게.

    ⚠️ **코드의 기본값**을 본다. `Settings()` 를 그냥 만들면 `.env` 가 얹혀서
       개발자 로컬 파일을 재게 된다(첫 판에서 그렇게 실패했다).
    """
    from app.config import Settings

    default = Settings.model_fields["disabled_providers"].default
    assert "perplexity" in str(default).lower(), (
        f"코드 기본값이 퍼플렉시티를 안 끈다: {default!r}")


@pytest.mark.asyncio
async def test_ask_json_은_요청을_안_보낸다(off, sent):
    """이미 막혀 있다 — 잠근다."""
    from app.research.perplexity import ask_json

    assert await ask_json("아무 프롬프트") is None
    assert not sent, f"꺼져 있는데 요청이 나갔다: {sent}"


@pytest.mark.asyncio
async def test_클라이언트_목이_막힌다(off, sent):
    """🔴 목은 `api_guard.raise_if_unusable` 다 — `_send` 앞에서 막는다.

    ⚠️ 예외 이름을 **여기서 정하지 않는다.** `api_guard` 가 올리는 것을
       그대로 기대한다 — 이름을 베끼면 원본이 바뀔 때 계약이 안 따라간다.
    """
    from app.collectors.base import ProviderDisabledError
    from app.research.perplexity import PerplexityClient

    c = PerplexityClient()
    with pytest.raises(ProviderDisabledError):
        await c.chat("아무 프롬프트")
    assert not sent, f"꺼져 있는데 유료 요청이 나갔다: {sent}"


def test_목이_api_guard_한_곳이다():
    """🔴 게이트를 `chat` 에 또 놓지 않았다 — 두 벌이 되면 어긋난다.

    `api_guard.raise_if_unusable` 가 `is_disabled` 를 보는 **유일한 목**이고,
    `BaseAPIClient._request` 가 모든 요청 앞에서 그것을 부른다.
    """
    import inspect

    from app.api_guard import raise_if_unusable
    from app.collectors.base import BaseAPIClient

    assert "is_disabled" in inspect.getsource(raise_if_unusable)
    assert "raise_if_unusable" in inspect.getsource(BaseAPIClient._request), (
        "요청 경로가 목을 안 지난다")


@pytest.mark.asyncio
async def test_호출부_게이트가_없어도_안_나간다(off, sent):
    """🔴 이 단위의 요점 — **목에서 막는다.**

    `deep_research_game` 은 공개 함수이고 클라이언트를 자기가 만든다.
    호출부가 게이트를 잊어도 요청은 나가지 않아야 한다.
    """
    from app.research.deep import deep_research_game

    jg = {"home": "San Francisco Giants", "away": "Minnesota Twins",
          "starts_at": "2026-09-22T01:45:00+00:00", "league": "MLB"}
    try:
        await deep_research_game(jg, "mlb")
    except Exception:
        pass          # 막혀서 예외가 나는 것은 정상 — 요청이 0인지가 계약이다
    assert not sent, f"호출부 게이트 없이 요청이 나갔다: {sent}"


@pytest.mark.asyncio
async def test_켜면_나간다(on, sent):
    """⚠️ **반대 위험.** 막기만 하는 수정이면 정식 승인 후 되돌릴 수 없다."""
    from app.research.perplexity import PerplexityClient

    c = PerplexityClient()
    try:
        await c.chat("아무 프롬프트")
    except Exception:
        pass
    assert sent, "켰는데도 요청이 안 나갔다 — 되돌릴 길이 막혔다"


def test_스위치를_두_벌로_만들지_않았다():
    """🔴 원본은 `DISABLED_PROVIDERS` 하나다(사본 금지)."""
    from app.engine import rules as R

    assert (R.get("sources.perplexity") is None), (
        "config/rules.yaml 에 두 번째 스위치가 생겼다 — "
        "DISABLED_PROVIDERS 와 어긋나면 어느 쪽이 참인지 알 수 없다")
