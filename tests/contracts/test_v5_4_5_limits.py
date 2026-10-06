"""🔴🔴 **v5 §4-4·§4-5·§4-6 — 받기 전 거르기·상한·깊이 예산.**

§9-3 이 *"`tests/contracts/` 에 **하나씩 파일로**"* 를 요구한다 —
처음에 남은 조항을 `test_v5_rest.py` 한 파일에 몰아 넣었고 그 계약이
🔴 *"조항 번호가 이름에 없는 계약 파일"* 로 빨개졌다. **맞았다**:
번호가 파일 이름에 없으면 그 조항을 찾을 수 없다.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]




def test_v5_4_4_검색_결과에_없던_URL은_거부한다():
    """🔴 *"에이전트가 검색 결과에 없던 URL 을 부르면 **거부**."*"""
    from app import agentloop
    from app.cells import Seen
    tools = agentloop.Tools(inp=_inp(), seen=Seen())
    got = tools.fetch("https://evil.example/x")
    assert got["ok"] is False and "검색 결과에 없던" in got["why"]


@pytest.mark.parametrize(("kind", "want"), [("본문", 50_000), ("위키", 25_000)])
def test_v5_4_5_크기_상한이_선언돼_있다(kind, want):
    """🔴 *"본문 50,000자 초과 → 앞 50,000자만. 위키·순위표는 25,000자."*"""
    from app import cells, domains
    if kind == "본문":
        assert cells.EXTRACT_MAX_CHARS == want
    else:
        # ⚠️ `max_chars` 는 **등급**을 받는다(URL 이 아니다) — 등급은 `tier_of` 다
        tier = domains.tier_of("https://en.wikipedia.org/wiki/X")
        assert tier == "wiki", tier
        assert domains.max_chars(tier) == want


def test_v5_4_5_경기당_fetch_상한이_스물넷이다():
    """🔴 수는 `config/llm.yaml` 이 든다 — 계약은 **표와 코드가 같은가**만 센다.

    ⚠️ 종전 이름은 *"열여섯이다"* 였고 `16` 을 박아 뒀다. 🔴 지시서 2026-10-06
       §1-3 이 **24** 로 올렸다(하위당 상위 3건 × 하위 8). 수를 계약에 박으면
       표가 바뀔 때마다 빨개진다(#1 사본 금지).
    """
    from app import rules, solar
    want = int((rules.llm_budget()["per_match"]["tool_calls"] or {})["fetch"])
    assert want == 24, want          # 🔴 지시서가 준 수다(§1-3)
    b = solar.MatchBudget()
    b.tool_calls["fetch"] = want
    ok, why = b.can_tool("fetch")
    assert ok is False and "fetch" in why, (ok, why)
    b.tool_calls["fetch"] = want - 1
    assert b.can_tool("fetch")[0] is True


def test_v5_4_6_깊이_소스가_follow_max를_선언한다():
    """🔴🔴 *"소스마다 `follow_max` 를 선언하고 … **선언 없는 소스는 계약 실패**."*

    ⚠️ 그 선언이 없으면 깊이 세포의 열기 예산이 **모자라** 따라가기가 조용히
       끊긴다(실측 2026-10-04: `MLB 예고 선발:예산소진`).
    """
    from app.collect import ingest
    bad = []
    for src_name, mod in sorted(ingest.SOURCE_ADAPTERS.items(),
                                key=lambda kv: kv[1].__name__):
        fn = getattr(mod, "sources_context", None)
        if not callable(fn):
            continue
        from app import matchkey
        for key in (matchkey.make(src_name, "849825"),
                    matchkey.make(src_name, "20261004-f-m")):
            for src in (fn(key) or []):
                # 🔴 **따라가는 소스만** 선언을 요구한다(안 따라가면 필요 없다)
                if getattr(src, "follow", None) and not getattr(
                        src, "follow_max", 0):
                    bad.append(f"{mod.__name__}:{src.name}")
    assert not bad, (
        f"🔴 §4-6 — `follow_max` 선언이 없는 깊이 소스: {sorted(set(bad))}")


# ══════════════════════════════════════════════════════════════════
# §6-1 strength = 변수 weight 합 · §6-7 거짓 1.0
# ══════════════════════════════════════════════════════════════════


# ── 대역 ──────────────────────────────────────────────────────────


def _inp():
    from datetime import datetime, timedelta, timezone

    from app import agentloop
    return agentloop.AgentInput(
        match_key="statsapi:849825", home="team:000338", away="team:000325",
        home_names=("Milwaukee Brewers",), away_names=("San Diego Padres",),
        competition="MLB", sport="baseball",
        kickoff_utc=datetime.now(timezone.utc) + timedelta(hours=2),
        venue="", langs=("en",))


def _draft(sid: str, strength: float):
    from app import scenarios
    return scenarios.Draft(id=sid, scores=["2-1"], strength=strength,
                           template_id="t", why="w", variables=["V1"],
                           added_by="template")


def _naive_var(when):
    from app import agentschema
    return agentschema.AgentVar(
        id="A1", type="pitcher_state", team="team:000338",
        direction_hint="home", claim="c", quote="Henderson will start",
        url="https://www.mlb.com/x", published_at=when, lang="en")


def _naive_ctx():
    from datetime import datetime, timedelta, timezone

    from app import verifylayer
    return verifylayer.Context(
        home="team:000338", away="team:000325",
        home_names=["Milwaukee Brewers"], away_names=["San Diego Padres"],
        competition="MLB", roster=["Logan Henderson"],
        kickoff=datetime.now(timezone.utc) + timedelta(hours=2),
        bodies={"https://www.mlb.com/x": "Henderson will start on Saturday"})
