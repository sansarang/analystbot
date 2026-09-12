"""ORD-18 — web_search 를 기본에서 뺀다.

사용자 지시 2026-09-12: "web_search가 돈을 먹고 일도 안 한다…이거부터 해결해라"

🔴 실측 2026-09-12 (운영, 질문 4종 × 2변형):
     web+x(현행)  합계 $1.3524 · 답 4/4   입력 13,153~27,584 토큰
     x만          합계 $0.6164 · 답 3/4   입력  3,702~ 6,923 토큰   ← 54% 싸다
   그리고 **둘 다 주면 모델이 비싼 쪽을 고른다** — 4건 중 3건에서
   web_search 2~3회 · x_search **0회**. 우리가 원한 X 게시물을 아예 안 찾았다.
     선수 상태  web+x $0.3386 (x=0 w=3)  vs  x만 $0.1643 (x=2)
     불펜       web+x $0.4734 (x=0 w=3)  vs  x만 $0.1786 (x=2)
"""

import inspect

import pytest

from app.research import grok as GK
from app.research.grok import GrokClient


def _client():
    return GrokClient.__new__(GrokClient)


# ═══════════════ ① 기본은 x 전용

def test_기본은_x_전용이다():
    assert _client()._tools(False) == [{"type": "x_search"}]


def test_웹은_옵트인으로_남긴다():
    """🔴 지우지 않는다 — 같은 실측에서 X 속보 질문 하나는 웹이 답을 찾았다
    (3/4 vs 4/4). 웹이 꼭 필요한 경로는 web=True 로 켠다."""
    assert _client()._tools(True) == [{"type": "web_search"},
                                      {"type": "x_search"}]


def test_도구_목록을_한_곳에만_둔다():
    """🔴 이름을 여기저기 적으면 그것이 사본이다."""
    src = inspect.getsource(GK)
    assert src.count('{"type": "x_search"}') == 2      # X_ONLY · WEB_AND_X
    assert src.count('{"type": "web_search"}') == 1


@pytest.mark.parametrize("fn", ["_search_call", "search_with_citations"])
def test_두_호출_경로_모두_web_인자를_받는다(fn):
    sig = inspect.signature(getattr(GrokClient, fn))
    assert "web" in sig.parameters
    assert sig.parameters["web"].default is False


@pytest.mark.parametrize("fn", ["_search_call", "search_with_citations"])
def test_하드코딩된_도구가_남아_있지_않다(fn):
    src = inspect.getsource(getattr(GrokClient, fn))
    assert '"web_search"' not in src
    assert "self._tools(web)" in src


# ═══════════════ ② 실제 요청 본문이 바뀌는가

@pytest.mark.asyncio
async def test_기본_호출에_web_search_가_안_실린다(monkeypatch):
    sent = {}

    async def _post(self, path, *, headers=None, json_body=None, **k):
        sent.update(json_body or {})
        return {"output": [], "usage": {}}

    monkeypatch.setattr(GrokClient, "_post", _post)
    c = _client()
    c.api_key, c.model = "k", "m"
    await c._search_call("q")
    assert sent["tools"] == [{"type": "x_search"}]


@pytest.mark.asyncio
async def test_web_True_면_둘_다_실린다(monkeypatch):
    sent = {}

    async def _post(self, path, *, headers=None, json_body=None, **k):
        sent.update(json_body or {})
        return {"output": [], "usage": {}}

    monkeypatch.setattr(GrokClient, "_post", _post)
    c = _client()
    c.api_key, c.model = "k", "m"
    await c._search_call("q", web=True)
    assert {t["type"] for t in sent["tools"]} == {"web_search", "x_search"}


# ═══════════════ ③ 비용을 로그에 남긴다

def test_도구와_비용을_로그에_남긴다(caplog):
    """🔴 이것이 없어서 호출당 $0.40 이 오래 숨어 있었다."""
    with caplog.at_level("INFO"):
        GK._log_usage({"usage": {
            "input_tokens": 5500, "output_tokens": 999,
            "cost_in_usd_ticks": 163000000,
            "server_side_tool_usage_details": {"x_search_calls": 2,
                                               "web_search_calls": 0}}}, "x")
    assert "도구=x" in caplog.text
    assert "$0.1630" in caplog.text


def test_단가를_우리가_곱하지_않는다():
    """🔴 `cost_in_usd_ticks` 는 xAI 가 주는 값이다 — 단가표를 우리가 들고
    있으면 그것이 사본이고, 요금이 바뀔 때 따라가지 않는다."""
    src = inspect.getsource(GK._log_usage)
    assert "cost_in_usd_ticks" in src
    for banned in ("3.0", "15.0", "per_million", "PRICE"):
        assert banned not in src, banned


def test_usage_가_없으면_조용히_넘어간다():
    GK._log_usage({}, "x")
    GK._log_usage({"usage": {}}, "x")


@pytest.mark.asyncio
async def test_호출이_usage_를_찍는다(monkeypatch, caplog):
    async def _post(self, path, *, headers=None, json_body=None, **k):
        return {"output": [], "usage": {"input_tokens": 10, "output_tokens": 2,
                                        "cost_in_usd_ticks": 1000000}}

    monkeypatch.setattr(GrokClient, "_post", _post)
    c = _client()
    c.api_key, c.model = "k", "m"
    with caplog.at_level("INFO"):
        await c._search_call("q")
    assert "[grok] 도구=x" in caplog.text


# ═══════════════ ORD-19 — 퍼플렉시티 기본을 sonar 로

def test_퍼플렉시티_기본이_sonar_다():
    """🔴 실측 2026-09-12 (조사 질문 4종 × 2회):
         sonar $0.00511 · sonar-pro $0.00724 — 42% 비싸다.
       답 품질 차이는 찾지 못했다(8/8 둘 다 실질적으로 답했다).
       비용의 대부분은 토큰이 아니라 요청료다(sonar $0.005 · pro $0.006).
    ⚠️ 절감액은 작다 — 월 약 $1.7. 큰 절감은 경기당 1콜 캡이다."""
    from app.config import Settings

    assert Settings.model_fields["pplx_model"].default == "sonar"


def test_되돌릴_길이_있다():
    """🔴 표본 8건이고 내 정답 검사기가 오분류했다 — 환경변수로 즉시 복귀."""
    from app.config import Settings

    f = Settings.model_fields["pplx_model"]
    names = getattr(f.validation_alias, "choices", None) or []
    src = open("app/config.py", encoding="utf-8").read()
    assert "PPLX_MODEL=sonar-pro" in src, "되돌리는 법이 적혀 있어야 한다"


def test_모델명을_호출부에_적지_않았다():
    """원본은 `config.pplx_model` 한 곳이다."""
    import inspect

    from app.research import perplexity as P

    src = inspect.getsource(P.ask_json)
    assert "s.pplx_model" in src
    assert "sonar-pro" not in src
