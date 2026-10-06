"""🔴🔴 **v5 §3-2·§3-7 — 도구 루프.** 에이전트가 **도구를 돌고** 끝낸다.

§3-2 원문(도구 셋)과 §3-7 원문(중단 조건):

> 도구: `search(query, lang)` · `fetch(url)` · `done(output)`.
> `tools` 와 `schema` 를 **함께 주지 않는다** — 도구를 쓰는 턴은 도구 호출로
> 끝나고, **마지막 `done` 턴에서만 스키마를 강제한다.**
> 중단: 변수 0개 → `agent_zero` / `done` 스키마 **2회 실패** / 예산 소진.
> 그때까지의 변수로 §5 로 넘기고 **사유를 적는다.**

══════════════════════════════════════════════════════════════════
🔴 왜 루프가 없으면 에이전트가 **거짓말을 한다**
══════════════════════════════════════════════════════════════════

⚠️ 종전 `run()` 은 `solar.chat(msgs, schema=…)` 를 **한 번** 불렀다 — `tools`
   를 **안 넘겼다.** 프롬프트는 *"도구로만 일한다"* 라고 적었는데 도구가 없다.
🔴 그러면 모델은 **기억으로** 변수를 짓고 인용을 **지어낸다**. §5-1 이 그것을
   전부 폐기하므로 수는 안 틀리지만 — **토큰만 쓰고 0건**이 된다.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

KICK = datetime.now(timezone.utc) + timedelta(hours=2)
BODY = ("Milwaukee Brewers manager Pat Murphy said Logan Henderson will start "
        "on Saturday against the San Diego Padres.")
URL = "https://www.mlb.com/brewers/news/rotation"






def _seen():
    from app.cells import Seen
    s = Seen()
    s.add_hit(URL, title="Brewers rotation", snippet="Henderson will start",
              query="Milwaukee Brewers San Diego Padres MLB baseball")
    s.add_body(URL, BODY)
    return s


def _tool_turn(name: str, args: dict, *, cid: str = "c1") -> dict:
    """🔴 Solar 가 도구를 부르는 턴의 모양(OpenAI 호환)."""
    return {"choices": [{"message": {
        "role": "assistant", "content": None,
        "tool_calls": [{"id": cid, "type": "function", "function": {
            "name": name, "arguments": json.dumps(args, ensure_ascii=False)}}],
    }}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


def _text_turn(text: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


_OUT = json.dumps({
    "variables": [{
        "id": "A1", "type": "pitcher_state", "team": "team:000338",
        "claim": "선발이 확정됐다", "quote": "Logan Henderson will start",
        "url": URL, "published_at": (KICK - timedelta(hours=20)).isoformat(),
        "direction_hint": "home", "lang": "en", "conflict": False,
        "reverified": True}],
    "hypotheses": [], "scenarios": [], "gaps": [], "notes": [],
}, ensure_ascii=False)


class _Net:
    """🔴 Solar 대역 — **턴을 차례로** 돌려준다. 보낸 몸통을 전부 적는다."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.sent: list[dict] = []

    def __call__(self, url, key, body, timeout, retries):
        self.sent.append(body)
        return self.turns.pop(0) if self.turns else _text_turn("{}")


















def test_v5_3_7_스위치가_있고_꺼짐이_기본이_아니다():
    """🔴 게이트 2 는 **사용자가 켠다** — 그 스위치가 설정에 있어야 한다.

    ⚠️ 비용이 발생하므로 코드가 혼자 켜지 않는다. 🔴 지금은 사용자 지시
       2026-10-04(*"게이트2 켜라"*)로 **켜져 있다**.
    """
    from app.config import get_settings
    s = get_settings()
    assert hasattr(s, "agent_enabled"), (
        "🔴 §3 에이전트 스위치가 설정에 없다 — 비용을 코드가 혼자 켠다")
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **`.env` 파일을 본다 — 프로세스 환경이 아니다**(2026-10-04)
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전엔 `s.agent_enabled is True` 였다. 🔴 그런데 스위트가 이 기계의
    #     `.env` 를 그대로 읽고 있었고(= 계약 결과가 기계 설정에 달렸다),
    #     결정 ③을 넣자 세포 검색 경로를 시험하는 **39건이 빨개졌다.**
    #  🔴 그래서 conftest 가 그 스위치를 **뽑는다**(`_unplug_env`). 묻는 것은
    #     여전히 같다 — *"사용자가 켰나"* — 그래서 **파일**을 본다.
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parents[2]
    said = (root / ".env").read_text(encoding="utf-8") \
        if (root / ".env").exists() else ""
    on = [ln for ln in said.splitlines()
          if ln.strip().startswith("AGENT_ENABLED=")
          and ln.split("=", 1)[1].strip().lower() in ("1", "true", "yes")]
    assert on, (
        "🔴 사용자가 게이트 2 를 켜라고 했다(2026-10-04) — `.env` 의 "
        "`AGENT_ENABLED` 가 꺼져 있다")




























