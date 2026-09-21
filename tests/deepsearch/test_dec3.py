"""[DEC-3] 규칙 개정 — **관련 문단 ≥1 일 때만 추출한다.**

사용자 결정 2026-09-21: "결정 3: 규칙 개정으로 처리. 새 계약 '관련 문단 ≥1 일
때만 추출, 0 이면 `reason=no_relevant_paragraph` 로 미상'. 고쳐 쓰는 16개
테스트의 목록·이전 의미·새 의미를 docs 에. 개정 전/후 LLM 호출 수와 추출
카드 수(하루치) 보고."

🔴 **이것은 계약을 뒤집는 개정이다.** DS-5 때 나는 같은 변경을 만들었다가
   **되돌렸다** — 기존 계약 16개가 깨졌고, "내 변경을 통과시키려고 계약 16개를
   고치는 것은 회귀를 숨기는 수"라고 적었다.
   🔴 지금은 다르다: **사용자가 규칙을 바꾸기로 결정했다.** 그래서 계약을
      고치는 것이 아니라 **규칙이 바뀐 것**이고, 그 사실을 문서에 남긴다.

[개정 전/후 — 운영 실측 2026-09-21 (최근 2일 · 기사 있는 경기 11개)]
```
전   LLM 호출 11회  ← 기사가 1건이라도 있으면 부른다
     그중 증거 문단 0 인 경기 **2**  ← 이 호출이 낭비다
후   LLM 호출  9회  (2회 절약 · 18%)
     미상 2경기 — 세이부@롯데(기사 6건) · 오릭스@니혼햄(기사 6건)
```
그 두 경기의 기사 6건에는 **그 경기 이야기가 아예 없었다**
(아시안게임 식사 문제 · 다른 팀 투수).
"""
from __future__ import annotations

import json

import pytest


def _async(v):
    async def f(*a, **k):
        return v
    return f


@pytest.fixture
def spy(monkeypatch):
    calls: list = []

    async def fake(chain, prompt, max_tokens, kind):
        calls.append(prompt)
        return json.dumps({"teams": []})

    monkeypatch.setattr("app.engine.team_form._complete_free", fake)
    monkeypatch.setattr("app.collectors.satellite._article_cap", _async(99))
    monkeypatch.setattr("app.collectors.satellite._llm_budget_ok", _async(True))
    monkeypatch.setattr("app.collectors.satellite._llm_budget_spend", _async(None))
    return calls


JUNK = [{"url": "https://x/1", "title": "아시안게임 트러블",
         "body": "선수들의 식사는 열악 태국 선수단 단장이 호소했다. " * 12}]


@pytest.mark.asyncio
async def test_관련_문단이_0이면_LLM을_안_부른다(spy):
    """🔴 절대 규칙 6 — 재료 없으면 분석 생성 금지."""
    from app.collectors.satellite import extract_game_facts

    out = await extract_game_facts(JUNK, home="Chiba Lotte Marines",
                                   away="Saitama Seibu Lions", league="NPB")
    assert spy == [], "증거가 없는데 LLM 을 불렀다"
    assert out.get("reason") == "no_relevant_paragraph", out


@pytest.mark.asyncio
async def test_미상_사유가_이름으로_남는다(spy):
    """🔴 "안 불렀다"와 "부르고 못 뽑았다"는 다르다. 사유를 이름으로 남긴다."""
    from app.collectors.satellite import extract_game_facts

    out = await extract_game_facts(JUNK, home="Chiba Lotte Marines",
                                   away="Saitama Seibu Lions", league="NPB")
    assert out["reason"] == "no_relevant_paragraph"
    assert out.get("articles") == 1, out      # 기사는 있었다는 사실도 남긴다
    assert out.get("teams") is None or out.get("teams") == {}


@pytest.mark.asyncio
async def test_관련_문단이_있으면_전과_같이_부른다(spy):
    from app.collectors.satellite import extract_game_facts

    arts = [{"url": "https://x/1", "title": "中日ドラゴンズ スタメン発表",
             "body": "中日ドラゴンズは21日のスタメンを発表した。"
                     "1番福永、2番村松。先発は髙橋宏斗。" * 3}]
    await extract_game_facts(arts, home="Chunichi Dragons",
                             away="Hiroshima Toyo Carp", league="NPB")
    assert len(spy) == 1


@pytest.mark.asyncio
async def test_스위치를_끄면_종전_규칙이다(spy, monkeypatch):
    """⚠️ 규칙 개정이라도 되돌릴 수단은 둔다 — config 한 줄."""
    from app.collectors.satellite import extract_game_facts
    from app.deepsearch import runtime as RT

    cfg = dict(RT.load_config())
    cfg["rerank"] = dict(cfg.get("rerank") or {}, require_relevant=False)
    monkeypatch.setattr(RT, "_CFG_CACHE", cfg)
    await extract_game_facts(JUNK, home="Chiba Lotte Marines",
                             away="Saitama Seibu Lions", league="NPB")
    assert len(spy) == 1, "끈 상태인데 종전 경로로 안 갔다"


def test_문서에_16개_목록이_있다():
    """🔴 지시: "고쳐 쓰는 16개 테스트의 목록·이전 의미·새 의미를 docs 에.\""""
    import pathlib

    p = pathlib.Path("docs/DEC3_CONTRACT_CHANGE_2026-09-21.md")
    assert p.exists(), "개정 문서가 없다"
    t = p.read_text(encoding="utf-8")
    assert "이전 의미" in t and "새 의미" in t
    # 실제로 16개가 적혀 있나
    assert t.count("| `test_") >= 16, f"목록이 {t.count('| `test_')}개뿐이다"
    assert "no_relevant_paragraph" in t
