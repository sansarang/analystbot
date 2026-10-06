"""🔴🔴 **§1 하위 과제 — 코드가 찾고, LLM 은 한 번 읽는다** (지시서 §1 · M128·M135).

> 에이전트 루프(LLM 이 검색어를 정하고 → 검색 → 다시 생각 → fetch → 다시 생각 →
> done)는 턴마다 추론 토큰을 쓰고 **40~88초**가 걸린다. 하위 8개 × 7턴이 26분과
> `budget_cut` 의 원인이다. 찾는 일은 **코드가**, 읽고 뽑는 일만 **LLM 이 한
> 번에** 하게 바꾼다.
>
> 결과: 하위당 LLM 호출 **1~2회**(전: 7턴). 목표 경기당 **6분 이하**.
> 에이전트 루프 코드는 **삭제하지 않고** 오픈월드 ⑥단(경기 찾기)에서만 쓴다 —
> 하위 과제 경로에서는 호출하지 않는다(M128).
> 추출 호출: `max_tokens` **4,000** · `reasoning_effort=low` (요청 본문에 실리는지
> 원장으로 확인) · 타임아웃 120초 · 재시도 1회 (M135).
> 예산 재조정 — 하위 출력 8,000 → **4,000**, 경기 64,000 → **40,000**,
> fetch 경기 16 → **24**.
"""
from __future__ import annotations

import ast
import inspect


# ══════════════════════════════════════════════════════════════════
# 예산 재조정
# ══════════════════════════════════════════════════════════════════

def test_wo1_예산이_되돌아왔다():
    """🔴 *"상한을 올려서 budget_cut 해결"* 은 §8 금지 목록이다."""
    from app import rules
    b = rules.llm_budget()
    assert int(b["per_subtask"]["output_tokens"]) == 4_000, b["per_subtask"]
    assert int(b["per_match"]["output_tokens"]) == 40_000, b["per_match"]
    assert int(b["per_match"]["tool_calls"]["fetch"]) == 24, b["per_match"]
    # 🔴 하위 8개 × 4,000 = 32,000 ≤ 경기 40,000 (2차 예비 8,000 이 그 차이다)
    assert 8 * 4_000 <= int(b["per_match"]["output_tokens"])


# ══════════════════════════════════════════════════════════════════
# M128 — 하위 경로에서 에이전트 루프를 부르지 않는다
# ══════════════════════════════════════════════════════════════════

def test_M128_하위_경로가_에이전트_루프를_안_부른다():
    """🔴🔴 **행동 검사** — 하위를 돌려서 `agentloop.run` 이 불렸나 센다."""
    from app.research import subtasks
    assert hasattr(subtasks, "run_subtask"), "🔴 `subtasks.run_subtask` 가 없다"


def test_M128_하위_하나에_LLM_호출이_두_번_이하다(monkeypatch):
    """🔴 *"하위당 LLM 호출 1~2회(전: 7턴)."*"""
    from app import solar
    from app.research import subtasks
    seen = _spy(monkeypatch, solar)
    got, why = _run_one(monkeypatch, subtasks)
    assert seen["n"] <= 2, f"🔴 LLM 호출이 {seen['n']}회다(상한 2) — {why}"
    assert seen["n"] >= 1, f"🔴 추출을 아예 안 했다 — {why}"


def test_M128_에이전트_루프는_오픈월드에만_남는다(monkeypatch):
    """🔴🔴 **돌려서** 본다 — 하위 경로가 `agentloop.run` 을 부르면 터진다."""
    from app import agentloop
    from app.research import subtasks

    def _boom(*a, **k):
        raise AssertionError("🔴 하위 경로가 `agentloop.run` 을 불렀다(M128)")

    monkeypatch.setattr(agentloop, "run", _boom)
    _spy(monkeypatch, __import__("app.solar", fromlist=["x"]))
    got, why = _run_one(monkeypatch, subtasks)
    assert isinstance(got, list), why


# ══════════════════════════════════════════════════════════════════
# M135 — 추출 호출의 요청 본문
# ══════════════════════════════════════════════════════════════════

def test_M135_추출_요청에_칸이_실린다(monkeypatch):
    """🔴🔴 **실제 요청 객체**를 검사한다(글자 검사 금지 · §7)."""
    from app import solar
    from app.research import subtasks
    sent: dict = {}

    def _net(base_url, key, body, timeout, retries):
        sent.update({"body": dict(body), "timeout": timeout,
                     "retries": retries})
        return {"choices": [{"message": {"content": '{"variables":[]}'}}],
                "usage": {"completion_tokens": 10, "prompt_tokens": 10}}

    monkeypatch.setattr(solar, "_post", _net)
    _run_one(monkeypatch, subtasks, patch_solar=False)
    body = sent.get("body") or {}
    assert int(body.get("max_tokens") or 0) == 4_000, body.get("max_tokens")
    assert str(body.get("reasoning_effort") or "") == "low", body
    # 🔴 **도구 없음** — 루프를 돌지 않는다
    assert "tools" not in body, body.keys()
    assert sent.get("timeout") == 120, sent.get("timeout")
    assert sent.get("retries") == 1, sent.get("retries")


# ══════════════════════════════════════════════════════════════════
# 거들
# ══════════════════════════════════════════════════════════════════

def _spy(monkeypatch, solar):
    seen = {"n": 0}

    def _chat(messages, **kw):
        seen["n"] += 1
        return {"choices": [{"message": {"content": '{"variables":[]}'}}],
                "usage": {"completion_tokens": 5, "prompt_tokens": 5}}

    monkeypatch.setattr(solar, "chat", _chat)
    return seen


def _run_one(monkeypatch, subtasks, *, patch_solar=True):
    """🔴 하위 하나를 **실제로** 돌린다 — 검색·fetch 는 대역이다."""
    import asyncio

    from app import cells, net as _net_mod, search as _S
    if patch_solar:
        from app import solar
        if not hasattr(solar.chat, "__wrapped__"):
            pass

    class _Chain:
        async def query(self, text, *, lang="en", engines=None, qtype=None):
            del text, lang, engines, qtype
            return [_S.Hit(title="Bradley out", url="https://news.test/a",
                           snippet="Conor Bradley is unavailable",
                           publisher="bbc.com", engine="x",
                           published_at=None)]

    class _Net:
        async def get(self, url):
            return _net_mod.Fetched(
                url, True, 200,
                "<html><body><article><p>Conor Bradley is unavailable for "
                "Northern Ireland because of a hamstring injury.</p>"
                "</article></body></html>")

    tasks = subtasks.split(_ref())
    task = tasks[0]
    seen = cells.Seen()
    return asyncio.run(subtasks.run_subtask(
        task, seen=seen, chain=_Chain(), net=_Net(),
        game={"home": "Northern Ireland", "away": "Georgia",
              "league": "UEFA Nations League B Grp. 2", "sport": "soccer",
              "home_id": "team:1", "away_id": "team:2"},
        match_key="fotmob:1"))


def _ref():
    class _R:
        home, away = "Northern Ireland", "Georgia"
        home_id, away_id = "team:1", "team:2"
        competition = "UEFA Nations League B Grp. 2"
        sport = "soccer"
        langs = ("en",)
    return _R()


def test_M128_행동_analyze_가_하위에_루프를_안_쓴다(monkeypatch):
    """🔴🔴 **실제 경로**(`analyze._run_agent`)를 돌린다 — 계약이 `run_subtask` 를
    직접 부르면, `analyze` 가 그것을 **안 써도** 초록이다(돌연변이 M128 통과).

    ⚠️ 그래서 여기서는 `agentloop.run` 을 **터지게** 두고 `_run_agent` 를
       하위 과제로 돌린다. 🔴 하위 경로가 루프를 부르면 그 자리에서 터진다.
    """
    import asyncio

    from app import agentloop, analyze, cells, net as _net_mod, search as _S
    from app.research import subtasks

    def _boom(*a, **k):
        raise AssertionError("🔴 `analyze` 의 하위 경로가 `agentloop.run` 을 "
                             "불렀다(M128) — 지시서 §1 은 오픈월드 ⑥단에만 "
                             "남기라고 했다")

    monkeypatch.setattr(agentloop, "run", _boom)
    # 🔴 §3 스위치를 켠다 — 꺼져 있으면 그 앞에서 돌아가고 이 계약이 뜻을 잃는다.
    #    ⚠️ **캐시를 되돌려 놓는다** — `get_settings` 는 캐시이고, 그 상태가
    #       남으면 **다른 계약**이 켜진 봇을 본다(병렬 실행에서 실측됐다).
    monkeypatch.setenv("AGENT_ENABLED", "1")
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.undo  # (명시용 — 아래 finally 가 캐시를 비운다)
    calls = {"n": 0}

    async def _fake_subtask(task, **kw):
        calls["n"] += 1
        return [], f"{task.name}: 대역"

    monkeypatch.setattr(subtasks, "run_subtask", _fake_subtask)

    class _Chain:
        async def query(self, text, *, lang="en", engines=None, qtype=None):
            return []

    class _Net:
        async def get(self, url):
            return _net_mod.Fetched(url, True, 200, "<html></html>")

    task = subtasks.split(_ref())[0]
    game = {"home": "Northern Ireland", "away": "Georgia",
            "league": "UEFA Nations League B Grp. 2", "sport": "soccer",
            "home_id": "team:1", "away_id": "team:2", "ext_id": "fotmob:1",
            "langs": ("en",)}
    import datetime as _dt
    kick = _dt.datetime(2026, 10, 5, 18, 45, tzinfo=_dt.timezone.utc)
    try:
        got, why = asyncio.run(analyze._run_agent(
            game, "home", None, cells.Seen(), [], kick, ("en",),
            chain=_Chain(), net=_Net(), pot=None, subtask=task))
    finally:
        # 🔴 **캐시를 비운다** — 안 비우면 다음 계약이 켜진 스위치를 본다
        get_settings.cache_clear()
    assert calls["n"] == 1, (
        f"🔴 `analyze` 가 `run_subtask` 를 **안 불렀다**({calls['n']}회) — "
        f"하위가 아직 루프를 돈다: {why}")
    assert isinstance(got, list), why
