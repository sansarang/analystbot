"""ANL-1 — 분석 LLM 3단 구조 (Part 3 / Phase 4.5).

페이블의 분석은 **추출·계산·추론·서술** 네 일이 섞인 것이다. 지금 봇은
추출(위성)·계산(코드)·서술(Gemini)만 있고 **추론 자리가 없다.**

🔴 **LLM 은 숫자를 만들지 않는다**(실측 AUC 0.5151). 사실 두 개를 시장 가격과
   대조하는 **판단 구조**만 낸다. 확률·배당·% 가 출력에 있으면 반려한다.
🔴 ② 출력은 `p_code`·확신·pick 을 **바꾸지 않는다.** 구조 후보는 Phase 5-2
   규칙에 제출될 뿐이고 채택(+6%p)은 코드가 한다.
"""
import pytest

from app.engine import analyze as A


def _blk(**kw):
    base = {
        "league": "세리에A", "home": "US Lecce", "away": "AC Monza",
        "kickoff_kst": "2026-09-13 21:30",
        "p_prior": (0.46, 0.27, 0.27), "p_market": (0.60, 0.20, 0.20),
        "gap_pp": -14.0, "gate": "시장 과대",
        "adj_pp": {"주전결장": -4.0}, "p_code": 0.56,
        "derived": [{"시장": "Monza +1.5", "확률": 0.63}],
        "home_facts": {"out": ["Proper", "Linday"], "last3": ["L 2-3", "D 2-2"],
                       "xi_status": "predicted"},
        "away_facts": {"out": [], "last3": ["L 0-2"], "midweek": "UCL 원정 목요일"},
        "regulars": {"Proper": 9, "Linday": 9},
        "notes": "감독 '역습 경계'", "missing": ["Smans 첫 선발 여부"],
    }
    base.update(kw)
    return base


# ── 입력 블록 (4.5-2)

def test_배당_원값이_들어가지_않는다():
    """🔴 지시문 공통 원칙 3 — 배당 숫자는 프롬프트에 넣지 않는다."""
    t = A.build_input(_blk())
    for bad in ("1.53", "2.10", "배당", "odds"):
        assert bad not in t, bad


def test_확률은_퍼센트포인트_가공값으로만_들어간다():
    t = A.build_input(_blk())
    assert "46/27/27" in t and "60/20/20" in t
    assert "-14" in t and "시장 과대" in t


def test_전적과_시즌누적은_안_들어간다():
    t = A.build_input(_blk(전적="5승 3패", season="타율 .280"))
    assert "5승" not in t and ".280" not in t


def test_주전_판정이_들어간다():
    t = A.build_input(_blk())
    assert "Proper" in t and "9" in t


def test_결측은_missing으로_명시된다():
    t = A.build_input(_blk())
    assert "Smans" in t and "missing" in t.lower() or "미확인" in t


# ── 출력 스키마 (4.5-3)

_OK = {
    "결정축": "중원 결장",
    "결정축_근거": "Proper·Linday 최근 10경기 9회 선발 미드필더 2명 동시 결장",
    "결정축_방향": "홈 하향",
    "반대축": "Monza 5경기 무승",
    "시장_판단": "과대",
    "시장_판단_이유": "결장 4명 팀에 60%는 브랜드 가격",
    "구조_후보": [{"시장": "Monza +1.5", "근거": "중원 없이 2골 차 어렵다"}],
    "불확실": ["Smans 첫 선발 여부"],
    "근거_수": 2,
}


def test_스키마_칸이_지시문_그대로다():
    assert set(A.SCHEMA) == set(_OK)


def test_정상_출력은_통과한다():
    ok, why = A.l1(_OK, _blk())
    assert ok is True, why


def test_사실_칸에_숫자가_있으면_반려한다():
    """🔴 LLM 은 숫자를 만들지 않는다. 사실 칸은 예외가 없다."""
    for bad in ({"결정축_근거": "홈 승률은 62%다"},
                {"반대축": "배당 1.53 이 말해준다"},
                {"결정축": "0.56 의 근거"}):
        ok, why = A.l1({**_OK, **bad}, _blk())
        assert ok is False, bad
        assert "숫자" in why or "배당" in why


def test_시장_판단_이유는_입력에_있는_숫자만_인용한다():
    """⚠️ 지시문 규칙("% 출력 금지")과 예시("60%는 브랜드 가격")가 모순이라
       **목적으로 갈랐다.** 금지의 목적은 LLM 이 숫자를 **만드는** 것이고,
       주어진 값을 인용하는 것은 다른 일이다."""
    ok, _ = A.l1({**_OK, "시장_판단_이유": "결장 팀에 60%는 브랜드 가격"}, _blk())
    assert ok is True                      # 60 은 입력 블록(60/20/20)에 있다
    ok, why = A.l1({**_OK, "시장_판단_이유": "우리 계산은 71%다"}, _blk())
    assert ok is False and "입력에 없는 숫자" in why
    ok, why = A.l1({**_OK, "시장_판단_이유": "배당이 말해준다"}, _blk())
    assert ok is False and "배당" in why


def test_입력에_없는_사실을_들면_반려한다():
    ok, why = A.l1({**_OK, "결정축_근거": "Ronaldo 가 결장이다"}, _blk())
    assert ok is False and "근거" in why


def test_파생_디빅에_없는_시장을_제안하면_반려한다():
    bad = {**_OK, "구조_후보": [{"시장": "오버 3.5", "근거": "x"}]}
    ok, why = A.l1(bad, _blk())
    assert ok is False and "구조" in why


def test_구조_후보가_비어도_된다():
    ok, _ = A.l1({**_OK, "구조_후보": []}, _blk())
    assert ok is True


def test_방향_라벨은_셋뿐이다():
    for v in ("홈 하향", "홈 상향", "판단불가"):
        assert A.l1({**_OK, "결정축_방향": v}, _blk())[0] is True
    assert A.l1({**_OK, "결정축_방향": "원정 유리"}, _blk())[0] is False


def test_시장_판단_라벨은_셋뿐이다():
    for v in ("과대", "적정", "과소"):
        assert A.l1({**_OK, "시장_판단": v}, _blk())[0] is True
    assert A.l1({**_OK, "시장_판단": "모름"}, _blk())[0] is False


# ── 사이드 스왑 (4.5-4)

def test_방향이_갈리면_판단불가로_강제한다():
    a = {**_OK, "결정축_방향": "홈 하향"}
    b = {**_OK, "결정축_방향": "홈 상향"}
    out = A.swap(a, b)
    assert out["결정축_방향"] == "판단불가"
    assert out["swap_agree"] is False


def test_일치하면_첫_출력을_쓴다():
    a = {**_OK, "결정축": "중원 결장"}
    b = {**_OK, "결정축": "일정"}
    out = A.swap(a, b)
    assert out["결정축"] == "중원 결장" and out["swap_agree"] is True


def test_한쪽이_없으면_스왑_불일치다():
    out = A.swap(_OK, None)
    assert out["swap_agree"] is False and out["결정축_방향"] == "판단불가"


def test_둘_다_없으면_None이다():
    assert A.swap(None, None) is None


# ── 게이트 대조

def test_코드_게이트와_다르면_기록한다():
    assert A.gate_vs_llm("시장 과대", "과대") == "same"
    assert A.gate_vs_llm("시장 과대", "적정") == "diff"
    assert A.gate_vs_llm("가치 의심", "과소") == "same"
    assert A.gate_vs_llm(None, "과대") is None


# ── 모델 사슬 (4.5-0)

def test_사슬이_실측대로_groq_우선이다():
    """🔴 지시문 1순위(gemini-pro 무료)·2순위(nvidia)가 **둘 다 불가**로
       측정됐다(2026-09-13):
         gemini  429 "prepayment credits are depleted" — 유료 계정, 잔액 0
         nvidia  404(계정 미할당) 또는 45초 타임아웃
       그래서 실측대로 groq 1순위 · openrouter 2순위다."""
    assert A.MODEL_CHAIN[0][0] == "groq"
    assert A.MODEL_CHAIN[1][0] == "openrouter"


def test_유료_모델이_사슬에_없다():
    """지시문 4.5-9: 유료는 어느 단계에도 없다."""
    for prov, _ in A.MODEL_CHAIN:
        assert prov not in ("anthropic", "perplexity", "xai", "deepseek"), prov


def test_호출_상한이_있다():
    assert A.DAILY_CAP == 32


# ── 원장·프롬프트

def test_원장에_칸이_있다():
    s = open("db/schema.sql", encoding="utf-8").read()
    for col in ("main_axis", "counter_axis", "market_view", "swap_agree",
                "structure_candidates", "analyze_model", "gate_vs_llm",
                "analyze_failed"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in s, col


def test_프롬프트_파일이_있고_규칙_일곱을_담는다():
    from pathlib import Path

    for name in ("analyze_soccer.md", "analyze_baseball.md"):
        t = Path("prompts") / name
        assert t.exists(), name
        s = t.read_text(encoding="utf-8")
        assert "확률" in s and "JSON" in s
        for n in "1234567":
            assert f"{n}." in s, (name, n)
