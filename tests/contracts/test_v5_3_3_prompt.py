"""🔴🔴 **v5 §3-3·§3-4 — 프롬프트와 카탈로그.**

§9-3 이 *"`tests/contracts/` 에 **하나씩 파일로**"* 를 요구한다 —
처음에 남은 조항을 `test_v5_rest.py` 한 파일에 몰아 넣었고 그 계약이
🔴 *"조항 번호가 이름에 없는 계약 파일"* 로 빨개졌다. **맞았다**:
번호가 파일 이름에 없으면 그 조항을 찾을 수 없다.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]




def test_v5_3_3_프롬프트가_고정_문자열이다():
    """🔴 *"(시스템, **고정**)"* — 경기마다 바뀌면 **캐시 단가**를 못 받는다.

    ⚠️ §2 가 `cached_input` 단가를 적었다(0.06 vs 0.30) — 다섯 배다.
    """
    from app import agentloop
    a = agentloop.system_prompt()
    b = agentloop.system_prompt()
    assert a == b and a
    # 🔴 **경기 정보가 섞여 있지 않다** — 섞이면 고정이 아니다
    for leak in ("Milwaukee", "statsapi:", "2026-"):
        assert leak not in a, f"🔴 프롬프트에 경기별 글자가 있다: {leak}"


def test_v5_3_3_열_단계가_전부_들어_있다():
    """🔴 §3-3 이 **번호로** 적은 열 단계. ⚠️ 문서에서 세어 대조한다(사본 금지)."""
    import re

    from app import agentloop
    text = (ROOT / "docs" / "fable" / "inbox"
            / "2026-10-04_v5_solar.md").read_text(encoding="utf-8")
    i = text.index("3-3 프롬프트  요지")
    # 🔴 **그 뒤에서** 찾는다 — `index` 는 앞쪽(쪽 머리글·요약)을 먼저 잡는다
    #    ⚠️ 처음에 그냥 `index` 를 썼더니 잘린 글이 **빈 문자열**이었다.
    seg = text[i:text.index("3-4 변수  카탈로그", i)]
    # ⚠️ PDF 추출 글은 줄 앞에 공백이 섞인다 — 허용한다(쪽 머리글 때문이다)
    nums = sorted({int(m) for m in re.findall(r"^\s*(\d{1,2})\. ", seg, re.M)})
    assert nums == list(range(1, 11)), nums
    said = agentloop.system_prompt()
    # 🔴 프롬프트가 그 **개수만큼** 번호를 들고 있어야 한다
    got = sorted({int(m) for m in re.findall(r"^\s*(\d{1,2})\. ", said, re.M)})
    assert len(got) >= len(nums), (
        f"🔴 §3-3 은 {len(nums)}단계인데 프롬프트에 {len(got)}개뿐이다: {got}")


def test_v5_3_3_등급_어휘를_금지한다():
    """🔴 §3-3 ⑩ *"등급·확률·배당·승자 단어를 쓰지 않는다. 그것은 네 일이 아니다."*"""
    from app import agentloop
    said = agentloop.system_prompt()
    for word in ("등급", "확률", "배당", "승자"):
        assert word in said, (
            f"🔴 프롬프트가 금지어 `{word}` 를 **금지한다고 적지 않았다**")


# ══════════════════════════════════════════════════════════════════
# §3-4 변수 카탈로그
# ══════════════════════════════════════════════════════════════════


def test_v5_3_4_카탈로그가_선언에서_온다():
    """🔴 *"유형마다 search 템플릿 2~3개와 작동 방향 규칙이 … 에 있다."*

    ⚠️ 지시문은 `config/catalog.yaml` 이라 적었다 — 우리 선언은
       `config/variable_types.yaml` 이다(v4 §4 유형표). 🔴 **한 곳**이면 된다.
    """
    from app import rules
    types = rules.variable_types()
    assert len(types) >= 15, len(types)
    # 🔴 검색 템플릿이 있는 유형은 **2개 이상**을 든다(§3-4)
    few = {k: len(v.get("search") or [])
           for k, v in types.items()
           if v.get("search") and len(v.get("search") or []) < 2}
    assert not few, f"🔴 템플릿이 하나뿐인 유형: {few}"


def test_v5_3_4_방향은_코드가_재계산한다():
    """🔴 *"코드는 §5-4 에서 방향을 **재계산**한다"* — 에이전트 값을 그대로 안 쓴다."""
    from app import agentschema
    import dataclasses
    names = {f.name for f in dataclasses.fields(agentschema.AgentVar)}
    # 🔴 에이전트가 주는 것은 **힌트**다(`direction` 이 아니다)
    assert "direction_hint" in names and "direction" not in names, names


# ══════════════════════════════════════════════════════════════════
# §4-4 받기 전에 거른다 · §4-5 크기·시간 상한 · §4-6 깊이 소스 예산
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
