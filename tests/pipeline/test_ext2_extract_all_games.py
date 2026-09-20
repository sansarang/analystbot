"""[EXT-2 / STEP 1-g] 추출이 **게이트 라벨로 갈렸다.**

🔴 실측 2026-09-20: KBO 5경기가 기사를 6~14건씩 모아 놓고도 `out` 이 채워진
   것은 **한 경기뿐**이었다. 두산@KT 는 기사 12건을 쥐고도 여섯 변수 전건 미상.

     [gate]  g1766 — 사전값 0.638(tier+form) · 시장 0.634 · gap +0.44 → 동의
     [scout] Doosan Bears@KT Wiz — 게이트 동의 · 빅매치 아님 · LLM 추출 생략
     [flow:n03] g1766 — 사전값 0.5655(team_elo) · 시장 0.6752 · gap −10.97 → 시장과대

   **게이트가 둘**이고(구경로 tier+form vs 흐름 team_elo) 위성은 구경로를
   본다. 흐름의 가설이 수집에 닿지 못한다(CLAUDE.md "가설이 수집을 지휘한다").

🔴 결정(two_gates_0920 → 답 B): 추출 대상 = **기사가 1건 이상 모인 전 경기.**
   게이트 라벨·빅매치로 가르지 않는다. 경기당 기사 상한은 **depth** 로.
"""
from __future__ import annotations

import inspect
import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_추출이_게이트로_갈리지_않는다():
    """🔴 f0920_doosan_kt — 게이트 동의·빅매치 아님이어도 추출한다."""
    from app.collectors import satellite as SAT

    src = "\n".join(ln for ln in inspect.getsource(SAT.extract_game_facts).splitlines()
                    if ln.strip() and not ln.strip().startswith("#"))
    assert "gate_target or tag.big" not in src, "추출이 아직 게이트로 갈린다"
    assert "LLM 추출 생략" not in src, "게이트 기반 생략이 남아 있다"


def test_depth_조회_함수가_있고_기본은_normal():
    from app.collectors import satellite as SAT

    assert hasattr(SAT, "get_depth"), "depth 조회 함수가 없다"


@pytest.mark.asyncio
async def test_f_depth_fallback_depth가_없으면_normal():
    """🔴 흐름 state 에 depth 가 없으면 `flow.depth_fallback` 을 쓴다."""
    from app.collectors import satellite as SAT

    got = await SAT.get_depth(None, game_id=999999)
    assert got == "normal", got


def test_depth_상한이_rules에_있다():
    """🔴 숫자를 코드에 박지 않는다."""
    d = yaml.safe_load((ROOT / "config" / "rules.yaml").read_text(encoding="utf-8"))
    flow = d.get("flow") or {}
    assert flow.get("depth_fallback") == "normal", flow.get("depth_fallback")
    caps = flow.get("depth_articles") or {}
    assert caps.get("shallow") == 0 and caps.get("normal") == 2 and caps.get("deep") == 5, caps


def test_키워드_사전이_있다():
    """🔴 키워드를 코드에 박지 않는다 — v2 STEP 7-4 가 쓸 그 파일이다."""
    f = ROOT / "config" / "evidence_lexicon.yaml"
    assert f.exists(), "config/evidence_lexicon.yaml 이 없다"
    d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    lex = d.get("lexicon") or {}
    for lang in ("ko", "ja", "en"):
        assert lex.get(lang), f"{lang} 키워드가 비었다"
    assert "라인업" in lex["ko"] and "말소" in lex["ko"], lex["ko"][:8]
    assert "スタメン" in lex["ja"] and "抹消" in lex["ja"], lex["ja"][:8]


def test_league_labels_nonempty():
    """🔴 [1-g 5)] 야구 리그 키가 비면 소스 tier 가 전부 미상이 된다."""
    from app.leagues import league_labels

    L = league_labels()
    for lg in ("KBO", "NPB", "MLB", "EPL", "라리가", "세리에A", "분데스리가", "J1 리그"):
        assert L.get(lg), f"{lg} 의 league_key 가 비었다: {L.get(lg)!r}"


def test_search_targets_move_to_flow_select():
    """🔴 [잠금] STEP 6 이 오면 위성은 `gate_of` 를 그만 불러야 한다.

    ⚠️ 지금은 `app/flow/select.py` 가 없으므로 통과한다. STEP 6 이 그 파일을
       만드는 순간 이 테스트가 **교체를 잊지 못하게** 실패한다.
    """
    from app.collectors import satellite as SAT

    if not (ROOT / "app" / "flow" / "select.py").exists():
        return
    src = "\n".join(ln for ln in inspect.getsource(SAT).splitlines()
                    if ln.strip() and not ln.strip().startswith("#"))
    assert "gate_of" not in src, \
        "flow/select.py 가 생겼는데 위성이 아직 구경로 gate_of 를 부른다 (STEP 6 교체 누락)"
