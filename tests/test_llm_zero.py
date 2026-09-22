"""[LLM0] **이 봇에서 LLM 을 0 으로 만든다.**

사용자 2026-09-22: "llm 완전히 0으로 만들어라..."

🔴 실측이 이 결정의 근거다 — LLM 은 **이미 거의 아무것도 못 채우고 있었다**
   (오늘 25경기·팀 행 40개):
```
out 10/40 · xi_status 11/40(전부 "predicted"=미상) · notes 15/40(판정 미사용)
doubt · last3 · midweek · published · llm_fetched_at   전부 0/40
```
그리고 살아 있는 자리는 **둘**이었다(하나는 세지도 않고 있었다):
```
satellite.extract_game_facts   58콜/일   api_calls:scout_extract 에 잡힘
team_form.analyze_team         26콜/일   아무 카운터에도 안 잡힘
```

🔴 **스위치는 하나다** — `api_guard.llm_enabled()`. 문마다 따로 끄면 한 문이
   열린 채 남고, 그게 "0 이라고 말했는데 아니었다"가 되는 자리다.

⚠️ 되돌릴 길을 막지 않는다 — `config/rules.yaml` 의 `llm.enabled: true`
   한 줄이면 전부 되돌아온다. 계약이 그것도 함께 잠근다.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from app import api_guard

ROOT = pathlib.Path(__file__).resolve().parents[1]


# ── 스위치 ──────────────────────────────────────────────────────────

def test_스위치가_한_곳이다():
    """🔴 원본은 `api_guard.llm_enabled` 하나다(사본 금지)."""
    assert hasattr(api_guard, "llm_enabled")
    assert api_guard.llm_enabled() is False, "운영 기본값이 꺼짐이 아니다"


def test_설정에서_읽는다_코드에_박지_않았다():
    """⚠️ `return False` 로 박으면 되돌릴 길이 사라진다.

    🔴 "켜면 켜진다"는 **아래 `test_켜면_다시_돈다` 가 실제로 호출해서** 잡는다.
       여기서는 원본이 어디인지만 잠근다 — 리터럴 유무 같은 대리검사는
       구현을 조금만 바꿔도 거짓으로 실패한다(처음 쓸 때 실제로 그랬다).
    """
    src = inspect.getsource(api_guard.llm_enabled)
    assert "llm.enabled" in src, "설정 키를 안 읽는다"
    assert "rules" in src, "원본이 config/rules.yaml 이 아니다"


def test_모르면_끈_것으로_본다(monkeypatch):
    """🔴 **실패는 닫히는 쪽이다.** 설정을 못 읽을 때 부르면, 끈 줄 알았는데
    조용히 나가는 상태가 된다 — 이 저장소가 가장 자주 당한 종류의 결함이다."""
    from app.engine import rules as R

    def _boom(*a, **k):
        raise RuntimeError("설정 못 읽음")

    monkeypatch.setattr(R, "get", _boom)
    assert api_guard.llm_enabled() is False


def test_켜면_다시_돈다(monkeypatch):
    """🔴 되돌릴 길을 막지 않는다 — 이것이 없으면 삭제와 같다."""
    from app.engine import rules as R

    monkeypatch.setattr(R, "get", lambda k, d=None: True if k == "llm.enabled" else d)
    assert api_guard.llm_enabled() is True


# ── 문 전수 ─────────────────────────────────────────────────────────

#: 🔴 **LLM 으로 나가는 문 전부.** `(모듈, 게이트가 있어야 하는 함수)`.
#   ⚠️ 이 목록은 손으로 적은 사본이 아니다 — 아래
#      `test_목록_밖에_LLM_문이_없다` 가 저장소를 훑어 대조한다.
DOORS = [
    ("app.llm.judge_route", "chain"),
    ("app.llm.openai_compat", "complete"),
    ("app.llm.gemini", "generate"),
    ("app.collectors.websearch", "ask"),
    ("app.collectors.grounding", "fetch_for_team"),
    ("app.collectors.grounding", "fetch_for_game"),
    ("app.engine.judge", "_create"),
    ("app.research.perplexity", "ask_json"),
]


def _code_of(mod_name: str, fn_name: str) -> str:
    """주석·독스트링을 뗀 본문. 🔴 원문 grep 은 내 주석에 걸린다(D46, 9회)."""
    import importlib

    mod = importlib.import_module(mod_name)
    obj = getattr(mod, fn_name, None)
    if obj is None:
        for _, cls in vars(mod).items():
            if isinstance(cls, type) and hasattr(cls, fn_name):
                obj = getattr(cls, fn_name)
                break
    assert obj is not None, f"{mod_name}.{fn_name} 이 없다"
    tree = ast.parse(inspect.getsource(obj).strip())
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not body or not isinstance(body, list):
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            body.pop(0)
    return ast.unparse(tree)


@pytest.mark.parametrize("mod,fn", DOORS)
def test_모든_문이_스위치를_본다(mod, fn):
    """🔴 한 문이라도 안 보면 '0' 은 거짓이 된다."""
    code = _code_of(mod, fn)
    assert "llm_enabled" in code, f"{mod}.{fn} 이 스위치를 안 본다"


def test_목록_밖에_LLM_문이_없다():
    """🔴 **사본이 되지 않게 저장소를 훑어 대조한다.**

    ⚠️ 새 문이 생기면 여기서 걸린다 — 그때 `DOORS` 에 넣고 게이트를 달아야
       한다. 목록만 고치고 게이트를 안 달면 위 계약이 잡는다.
    """
    marks = ("AsyncAnthropic(", "openai_compat", "generativelanguage",
             "api.groq.com", "api.x.ai", "openrouter.ai", "perplexity.ai")
    known = {m for m, _ in DOORS} | {
        "app.llm.provider", "app.llm.judge_route", "app.llm.token_budget",
        "app.engine.team_form", "app.engine.matchup", "app.engine.council",
        "app.engine.analyze", "app.engine.synthesis", "app.engine.soccer_trial",
        "app.engine.verdict", "app.engine.dbref", "app.collectors.satellite",
        "app.config", "app.notify", "app.research.grok",
        "app.flow.nodes.n12_text",
    }
    found = []
    for p in (ROOT / "app").rglob("*.py"):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        code = "\n".join(ln.split("#", 1)[0] for ln in txt.splitlines())
        if not any(m in code for m in marks):
            continue
        mod = ".".join(p.relative_to(ROOT).with_suffix("").parts)
        if mod not in known:
            found.append(mod)
    assert found == [], f"목록에 없는 LLM 문: {found}"


# ── 실제로 안 나가는가 ──────────────────────────────────────────────

def test_사슬이_비어_있다():
    """🔴 `chain()` 이 비면 team_form·matchup·council·satellite 가 전부 멈춘다.
    그 '재료 없이 간다' 경로는 **이미 설계돼 있고 로그가 남는다.**"""
    from app.llm import judge_route as JR

    for role in ("form", "matchup", "matchup_prelim", "verify"):
        assert JR.chain(role) == [], role


@pytest.mark.asyncio
async def test_송신이_거부된다():
    """⚠️ 예외가 아니라 **실패 dict** 다 — 호출부가 이미 그 모양을 다룬다."""
    from app.llm import openai_compat as OC

    out = await OC.complete("groq", "any-model", "hi")
    assert out["ok"] is False
    assert "llm_off" in str(out["error"])


@pytest.mark.asyncio
async def test_제미니_직호출도_막힌다():
    from app.llm import gemini as G

    assert await G.generate("hi") is None


@pytest.mark.asyncio
async def test_끈_것이_예외를_던지지_않는다():
    """🔴 **절대 규칙 3 과 같은 규약** — 끔이 크래시가 되면 안 된다.
    카드가 안 나가는 것과 파이프라인이 죽는 것은 다르다."""
    from app.collectors import websearch as W

    got = await W.ask({"home": "A", "away": "B"}, ["q"])
    assert got in (None, [], {}, ()) or hasattr(got, "__len__")
