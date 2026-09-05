"""[9번 2026-09-04] 폼 파싱 실패의 원인 — 추론이 출력 예산을 먹었다.

🔴 계측이 답을 줬다 (2026-09-04 프리페치 로그, `[form] … 앞=%r`):
   · 1회차 `resp_chars=599` · 앞 `'{\\n  "team": "Samsung Lions", "타선": …'`
     → **잘린 JSON.** 예산이 모자랐다.
   · 2회차 `resp_chars=3881` · 앞 `"The user wants me to analyze Samsung Lions'"`
     → **영어 사고문.** JSON 은 아예 안 나왔다.

   직접 호출로 재현: Nemotron 3 Ultra 는 사고를 `reasoning_content` 로 따로
   주기도 하고 `content` 안에 쏟기도 한다(비결정적). 후자일 때 1500토큰이
   전부 사고로 소진된다 — 측정: reasoning 1814자 vs content 423자.

   같은 사고가 2026-08-27 에 있었다(2단 해석봇, 300 중 285를 사고가 소모).
   그때 결론이 "짧은 판정은 사고를 끈다" 였고, 여기가 같은 자리다.

⚠️ 판정(matchup)은 사고를 **켠 채로 둔다.** 거기선 사고가 품질이다.
⚠️ 세 제공자 모두 `reasoning_effort` 를 받는 것을 실호출로 확인했다
   (nvidia reasoning 222자→0자 · groq 200 · openrouter 200).
   추측으로 넣은 필드가 아니다.
"""
import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("reasoning,expected", [(False, "none"), (True, None)])
async def test_reasoning_flag_controls_the_body(monkeypatch, reasoning, expected):
    import app.llm.openai_compat as oc

    seen = {}

    class _Resp:
        status_code = 200
        headers: dict = {}

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": '{"ok":1}'}}],
                    "usage": {"completion_tokens": 5}}

    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            seen.update(json or {})
            return _Resp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    monkeypatch.setattr(oc, "_throttle", lambda *_a, **_k: _noop())
    monkeypatch.setenv("NVIDIA_API_KEY", "k")

    out = await oc.complete("nvidia", "m", "p", max_tokens=100,
                            reasoning=reasoning)
    assert out["ok"] is True
    assert seen.get("reasoning_effort") == expected


async def _noop():
    return None


@pytest.mark.asyncio
async def test_form_turns_reasoning_off_and_matchup_keeps_it(monkeypatch):
    """역할에 따라 갈린다 — 일괄로 끄지 않는다."""
    import app.engine.team_form as tf

    calls = []

    async def _fake(provider, model, prompt, *, max_tokens, reasoning=True, **kw):
        calls.append((provider, reasoning))
        return {"ok": True, "text": "{}", "elapsed": 0.1, "error": None,
                "usage": {}, "status": 200}

    import app.llm.openai_compat as oc
    monkeypatch.setattr(oc, "complete", _fake)

    await tf._complete_free([("nvidia", "m")], "p", 100, "form")
    await tf._complete_free([("nvidia", "m")], "p", 100, "matchup")
    assert calls == [("nvidia", False), ("nvidia", True)]


def test_the_measurement_is_recorded_where_the_code_is():
    """숫자를 지운 채 코드만 남기지 않는다 — 다음 사람이 되돌린다."""
    from pathlib import Path

    src = Path("app/llm/openai_compat.py").read_text(encoding="utf-8")
    assert "reasoning_effort" in src
    assert "599" in src and "3881" in src, "실측 근거가 코드에서 사라졌다"


# ─────────────────── reasoning_effort 값이 제공자마다 다르다 ───────────────────

def test_reasoning_downgrade_order_is_measured_not_guessed():
    """🔴 실측 2026-09-04 — 400 응답이 직접 알려준 값들이다.

    groq `openai/gpt-oss-120b`:
      "`reasoning_effort` must be one of `low`, `medium`, or `high`"
    groq `qwen/qwen3.8-27b` 와 nvidia 는 `none` 을 받는다.
    """
    from app.llm.openai_compat import _REASONING_OFF, _next_reasoning

    assert _REASONING_OFF[0] == "none", "가장 강한 값부터 시도한다"
    assert _next_reasoning("none") == "low"
    assert _next_reasoning("low") is None, "끝이면 필드를 뺀다"
    assert _next_reasoning(None) is None


@pytest.mark.asyncio
async def test_400_on_reasoning_effort_downgrades_instead_of_dropping_the_provider(
        monkeypatch):
    """한 모델이 이 필드를 모른다고 그 후보를 통째로 버리면 사슬이 무의미해진다."""
    import app.llm.openai_compat as oc

    bodies = []

    class _Resp:
        def __init__(self, code, text=""):
            self.status_code = code
            self.text = text
            self.headers: dict = {}

        def json(self):
            return {"choices": [{"message": {"content": '{"ok":1}'}}],
                    "usage": {"completion_tokens": 5}}

    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            bodies.append(dict(json or {}))
            if (json or {}).get("reasoning_effort") == "none":
                return _Resp(400, '{"error":{"message":"`reasoning_effort` must '
                                  'be one of `low`, `medium`, or `high`"}}')
            return _Resp(200)

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    monkeypatch.setattr(oc, "_throttle", lambda *_a, **_k: _noop())
    monkeypatch.setenv("GROQ_API_KEY", "k")

    out = await oc.complete("groq", "openai/gpt-oss-120b", "p",
                            max_tokens=100, reasoning=False)
    assert out["ok"] is True, "400 한 번에 후보를 버리면 안 된다"
    assert [b.get("reasoning_effort") for b in bodies] == ["none", "low"]
