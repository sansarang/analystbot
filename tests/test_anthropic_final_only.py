"""안트로픽은 **최종 판정에서만** 쓴다 — 2026-09-06 사용자 지시.

전수 검사에서 `team_form` 외에 다섯 곳이 Anthropic 을 직접 부르고 있었다.
그중 야구 슬레이트에 닿는 셋(딥서치·축구 시범·봇 의도 파싱)을 막았다.
이 파일은 **그 셋이 다시 열리면 운다.** 문서로 적으면 사본이 되고,
사본은 원본이 바뀔 때 따라가지 않는다.
"""
from __future__ import annotations

import asyncio
import inspect
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ── ② 딥서치 ────────────────────────────────────────────────────
def test_deepsearch_never_builds_an_anthropic_client():
    """RSS 0건 폴백(유료 web_search)이 되살아나면 여기서 잡힌다."""
    src = _src("app/engine/deepsearch.py")
    assert "anthropic.AsyncAnthropic" not in src
    assert "import anthropic" not in src
    assert "web_search_20260318" not in src


def test_deepsearch_routes_on_a_non_matchup_role():
    """`chain("matchup")` 을 물으면 최종 판정 설정이 딥서치까지 유료로 끈다."""
    from app.engine.deepsearch import DEEPSEARCH_ROLE
    from app.llm.judge_route import MATCHUP_ROLE

    assert DEEPSEARCH_ROLE != MATCHUP_ROLE
    src = _src("app/engine/deepsearch.py")
    assert '_chain("matchup")' not in src
    assert f"_chain({'DEEPSEARCH_ROLE'})" in src


def test_deepsearch_role_is_free_even_when_judge_provider_is_anthropic():
    """최종 판정이 Anthropic 이어도 딥서치 역할에는 anthropic 이 없다."""
    from app.llm import judge_route

    class _S:
        judge_provider = "anthropic"
        matchup_model = "claude-fable-5"
        paid_llm_allowed = True
        judge_chain = "gemini/gemini-3.7-flash"
        form_chain = "gemini/gemini-3.7-flash"

    from app.engine.deepsearch import DEEPSEARCH_ROLE

    orig = judge_route._cfg
    judge_route._cfg = lambda: _S()
    try:
        assert judge_route.chain(judge_route.MATCHUP_ROLE)[0][0] == "anthropic"
        assert all(p != "anthropic" for p, _ in judge_route.chain(DEEPSEARCH_ROLE))
    finally:
        judge_route._cfg = orig


def test_deepsearch_skips_when_rss_is_empty(monkeypatch):
    """기사가 0건이면 조사를 생략한다 — 유료 검색으로 넘어가지 않는다."""
    from app.engine import deepsearch as ds

    async def _none(jg, redis, **kw):
        # ⚠️ [DSM-1] `meta=` 를 받는다 — 딥서치가 출처(위성/RSS)를 세기 위해
        #    넘긴다. 목이 키워드를 안 받으면 여기서만 깨진다.
        return []

    def _boom(*a, **k):                      # 유료 예산을 건드리면 실패
        raise AssertionError("유료 검색 예산을 건드렸다")

    monkeypatch.setattr(ds, "_free_articles", _none)
    monkeypatch.setattr(ds, "_paid_budget_left", _boom)
    monkeypatch.setattr(ds, "_spend_paid", _boom)

    class _S:
        mock_judge = False
        deepsearch_max_searches = 3
        deepsearch_max_tokens = 1500
        deepsearch_timeout_sec = 60

    monkeypatch.setattr("app.config.get_settings", lambda: _S())
    jg = {"sport": "kbo", "home": "H", "away": "A", "matchup": {"p_home": 0.5}}
    data, used, src = asyncio.run(ds.investigate(jg, ["트리거"], redis=None))
    assert data is None and used == 0


# ── ③ 축구 시범 ─────────────────────────────────────────────────
def test_soccer_trial_is_off_by_default():
    from app.config import Settings

    assert Settings.model_fields["soccer_trial_enabled"].default is False


def test_soccer_trial_run_once_returns_without_collecting(monkeypatch):
    """꺼져 있으면 수집도 판정도 하지 않는다."""
    from app.engine import soccer_trial as st

    async def _boom(*a, **k):
        raise AssertionError("꺼져 있는데 수집했다")

    monkeypatch.setattr(st, "collect", _boom)
    out = asyncio.run(st.run_once(None, None, send=lambda *_: None))
    assert out == {"judged": 0, "resent": 0, "skipped": 0, "capped": 0}


def test_scheduler_job_checks_the_switch():
    src = _src("app/scheduler.py")
    body = src[src.index("async def soccer_trial_job"):]
    body = body[:body.index("\nasync def ", 1)]
    assert "soccer_trial_enabled" in body
    # 스위치 검사가 run_once 임포트보다 앞에 있어야 한다
    assert body.index("soccer_trial_enabled") < body.index("run_once")


# ── ④ 봇 의도 파싱 ──────────────────────────────────────────────
def test_bot_intent_parsing_never_calls_anthropic():
    src = _src("app/bot/main.py")
    assert "anthropic.AsyncAnthropic" not in src
    assert "import anthropic" not in src
    assert "_parse_intent_live" not in src


def test_parse_intent_is_rule_based():
    from app.bot.main import parse_intent, parse_intent_mock

    text = "오늘 야구 픽 간단히"
    assert asyncio.run(parse_intent(text)) == parse_intent_mock(text)


# ── ⑤ 축구 구 Judge ─────────────────────────────────────────────
def test_old_soccer_judge_is_off_by_default():
    """마지막 Anthropic 경로였다. 안트로픽은 야구 2차 최종 판정 전용이다."""
    from app.config import Settings

    assert Settings.model_fields["soccer_judge_enabled"].default is False


def test_old_soccer_judge_returns_empty_without_calling(monkeypatch):
    from app.engine.judge import Judge

    called = []

    async def boom(self, payload):
        called.append(1)
        raise AssertionError("꺼져 있는데 호출했다")

    monkeypatch.setattr(Judge, "_judge_once", boom)
    j = Judge(mock=False)
    monkeypatch.setattr(j.settings, "soccer_judge_enabled", False)
    out = asyncio.run(j.judge({"sport": "soccer",
                               "games": [{"game_id": 1, "home": "A", "away": "B"}]}))
    assert out == {"games": []} and not called


# ── 전수: 야구 경로에 남은 Anthropic 호출 지점 ──────────────────
#: 최종 판정 1곳 + 축구 전용 경로. 여기 없는 파일이 새로 뜨면 운다.
_ALLOWED = {
    "app/engine/team_form.py",     # 2차 최종 판정 — chain() 이 matchup 으로 잠근다
    "app/engine/judge.py",         # 구 Judge — 축구 전용 (야구는 else 분기)
    # ⚠️ 코드는 남아 있으나 `SOCCER_TRIAL_ENABLED` 기본 꺼짐으로 닫혀 있다.
    #    스위치를 켜기 전에 무료 사슬로 옮겨야 한다.
    "app/engine/soccer_trial.py",
    # 🔴 `app/llm/provider.py` 는 2026-09-06 에 목록에서 **빠졌다.**
    #    역할 체인(interpreter·judge_a·narrator·intent)의 Anthropic 경로를
    #    클래스째 지웠다 — 기본값만 바꾸면 env 한 줄로 다시 열린다.
}


def test_role_chain_cannot_reach_anthropic_at_all():
    """`*_PROVIDER=anthropic` 을 넣어도 거절돼야 한다 — 기본값이 아니라 부재로."""
    from app.config import Settings
    from app.llm.provider import LLMError, _KIND_TO_CLASS, provider_chain

    assert "anthropic" not in _KIND_TO_CLASS
    s = Settings(_env_file=None, force_mock=False,
                 judge_a_provider="anthropic", anthropic_api_key="k")
    with pytest.raises(LLMError, match="알 수 없는 provider"):
        provider_chain("judge_a", s)


def test_role_defaults_carry_no_anthropic():
    """env 가 하나도 없는 환경에서도 열리지 않는다."""
    from app.config import Settings

    s = Settings(_env_file=None)
    for role in ("interpreter", "judge_a", "judge_b", "narrator", "intent"):
        prov = (getattr(s, f"{role}_provider", "") or "")
        fb = (getattr(s, f"{role}_fallback", "") or "")
        assert "anthropic" not in f"{prov},{fb}", \
            f"{role} 기본값에 anthropic 이 남아 있다: {prov!r} / {fb!r}"
    # 해석봇에 claude 모델명을 박아두면 groq 으로 넘어간다.
    assert "claude" not in (s.interpreter_model or "").lower()


def test_no_new_anthropic_call_sites():
    hits = set()
    for f in ROOT.joinpath("app").rglob("*.py"):
        if re.search(r"anthropic\.AsyncAnthropic\(", f.read_text(encoding="utf-8")):
            hits.add(str(f.relative_to(ROOT)))
    assert hits == _ALLOWED, (
        f"Anthropic 직접 호출 지점이 바뀌었다. 추가 {hits - _ALLOWED} · "
        f"제거 {_ALLOWED - hits} — 최종 판정 외에 열렸는지 확인하라")
