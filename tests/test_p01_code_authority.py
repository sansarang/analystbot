"""P0-1 — 승자·확신은 코드가 정한다. LLM 값은 섀도로만 남는다.

🔴 어젯밤 7432 Parma@Como 실측이 이 파일의 이유다:
     [verdict] 승자 Parma Calcio 1913 · 확신 상
     [prob]    p_market=0.7712 p_code=0.72 확신=하
   같은 경기에 값이 둘이었고 카드로 가는 쪽은 LLM 이었다.
"""
from __future__ import annotations

import inspect

import pytest

from app.engine import prob as P
from app.engine.matchup import apply_code_verdict, apply_winner
from app.engine.verdict import LEVELS, level, shadow_level

COMO, PARMA = "Como 1907", "Parma Calcio 1913"


def _jg(**kw):
    """7432 실측값. 시장 디빅 코모 77.2 / 무 15.1 / 파르마 7.7."""
    jg = {"game_id": 7432, "sport": "soccer", "home": COMO, "away": PARMA,
          "market_probs": {COMO: 0.772, "Draw": 0.151, PARMA: 0.077},
          "p_code": 0.72, "code_confidence": "하"}
    jg.update(kw)
    return jg


def _llm_said(jg, 승자=PARMA, 확신="상"):
    """3단계(LLM) 판정이 먼저 실린 상태를 만든다 — 실제 순서 그대로."""
    assert apply_winner(jg, {"결과": "원정승" if 승자 == PARMA else "홈승",
                             "확신": 확신, "model": "groq/gpt-oss-120b"})
    return jg


# ── ① 코드가 이긴다

def test_verdict_code_authority():
    """LLM 이 '파르마 승·상' 을 돌려줘도 결과는 코모·하."""
    jg = _llm_said(_jg())
    assert jg["winner"] == PARMA, "전제: LLM 값이 먼저 실려 있다"
    assert jg["matchup"]["확신"] == "상"

    assert apply_code_verdict(jg) is True
    assert jg["winner"] == COMO
    assert jg["matchup"]["결과"] == "홈승"
    assert jg["matchup"]["확신"] == "하"


def test_llm_verdict_preserved():
    """결정 D — 덮어쓰기 전 LLM 값이 원장 칸으로 살아남는다."""
    jg = _llm_said(_jg())
    apply_code_verdict(jg)
    assert jg["llm_verdict"] == {"승자": PARMA, "확신": "상"}

    from app.engine.pick_ledger import _row_from_game
    row = _row_from_game(jg, {}, {})
    assert row["llm_winner"] == PARMA
    assert row["llm_level"] == "상"
    assert row["llm_winner"] != jg["winner"], "섀도가 자기 자신과 비교되고 있다"
    # 🔴 칸은 스키마에 있었는데 **쓰는 코드가 없었다**(실측 2026-09-15:
    #    ACL 4경기 전부 gate_vs_llm NULL). 원장 행에 실리는지 본다.
    assert row["gate_vs_llm"] == "diff", row["gate_vs_llm"]


def test_원장_INSERT에_gate_vs_llm이_있다():
    """🔴 row 에 담아도 INSERT 목록에 없으면 영원히 NULL 이다."""
    import inspect
    from app.engine import pick_ledger as PL

    src = inspect.getsource(PL)
    i = src.index("INSERT INTO pick_ledger")
    block = src[i:i + 1400]
    assert "gate_vs_llm" in block, "INSERT 칸 목록에 없다"
    assert 'row.get("gate_vs_llm")' in src, "인자로 안 넘긴다"


def test_코드가_두_번_불려도_llm_원값은_첫_것이다():
    jg = _llm_said(_jg())
    apply_code_verdict(jg)
    apply_code_verdict(jg)
    assert jg["llm_verdict"]["승자"] == PARMA


# ── ② 시장이 없으면 지어내지 않는다

def test_verdict_no_market():
    jg = _llm_said(_jg(p_code=None, code_confidence=None))
    assert apply_code_verdict(jg) is False
    assert jg["winner"] is None
    assert jg["matchup"]["승자"] is None
    assert jg["matchup"]["확신"] == LEVELS[-1] == "하"
    assert jg["board_only"] is True
    assert jg["llm_verdict"]["승자"] == PARMA, "보드로 내려도 섀도는 남는다"


def test_무승부_칸이_없으면_축구는_고르지_않는다():
    jg = _jg(market_probs={COMO: 0.772, PARMA: 0.077})
    assert P.code_pick(jg) is None


# ── ③ 3-way 는 무승부 질량을 뺀 뒤 최대값

@pytest.mark.parametrize("p_code,draw,expect", [
    (0.72, 0.151, "홈승"),     # 코모 72 · 무 15.1 · 파르마 12.9
    (0.20, 0.151, "원정승"),   # 홈 20 · 무 15.1 · 원정 64.9
    (0.30, 0.600, "무"),       # 홈 30 · 무 60 · 원정 10
])
def test_축구는_3way_최대값(p_code, draw, expect):
    jg = _jg(p_code=p_code,
             market_probs={COMO: 0.7, "Draw": draw, PARMA: 0.2})
    assert P.code_pick(jg) == {"결과": expect}


def test_야구는_반반을_기준으로_가른다():
    jg = {"sport": "mlb", "home": "H", "away": "A", "p_code": 0.5}
    assert P.code_pick(jg) == {"승자": "H"}
    jg["p_code"] = 0.4999
    assert P.code_pick(jg) == {"승자": "A"}


# ── ④ level() 은 기대값을 요구한다

def test_level_requires_expected():
    with pytest.raises(TypeError):        # 기본값이 없다 — 인자를 빼면 터진다
        level("상")
    with pytest.raises(ValueError):       # 명시적 None 도 막는다
        level("상", None)
    assert level("하", "하") == "하"
    assert level("상", "하") is None       # 다르면 반려
    assert shadow_level("상") == "상"      # 섀도는 정규화만
    assert shadow_level("없는라벨") == "하"


def test_expected_없는_level_호출이_남아있지_않다():
    """🔴 기본값을 지운 것이 이 결함의 본체다 — 되살아나면 여기서 잡는다."""
    import pathlib
    sig = inspect.signature(level)
    assert sig.parameters["expected"].default is inspect.Parameter.empty
    import re
    # 인자가 **하나뿐인** 실제 호출만 본다. 주석·독스트링의 `level()` 은 산문이다.
    call = re.compile(r"(?<![A-Za-z_`])level\(\s*[^\s(),][^(),]*\)")
    bad = []
    for f in pathlib.Path("app").rglob("*.py"):
        for i, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            s = ln.strip()
            if s.startswith("#") or s.startswith("*"):
                continue
            for m in call.finditer(ln):
                bad.append((f.name, i, m.group(0)))
    assert bad == [], f"expected 없이 level() 을 부른다: {bad}"


# ── ⑤ recheck 는 승자를 바꾸지 않는다

def test_recheck_no_winner_change():
    import app.engine.dbref as D
    src = inspect.getsource(D.recheck)
    assert 'out["승자"] = ' not in src, "recheck 가 승자를 다시 쓴다"
    assert "반대근거" in src, "다른 의견을 버리고 있다"


def test_recheck_는_등급도_못_바꾼다():
    import app.engine.dbref as D
    src = inspect.getsource(D.recheck)
    assert 'level(parsed.get("확신"), _exp) or _exp' in src


# ── ⑥ 카드는 덮어쓴 뒤 값만 읽는다

def test_card_reads_code_only():
    """렌더가 덮어쓰기보다 뒤에 있어야 한다 — 순서가 곧 계약이다."""
    from app import pipeline as PL

    for fn in (PL._run_baseball_matchups, PL._run_soccer_matchups):
        src = inspect.getsource(fn)
        i = src.index("_attach_market_spine")
        j = src.index("apply_code_verdict")
        assert i < j, f"{fn.__name__}: 뼈대보다 먼저 덮어쓴다 — p_code 가 없다"

    whole = inspect.getsource(PL)
    assert whole.index("apply_code_verdict") < whole.index("jg[\"card\"] = build_card"), \
        "카드 렌더가 덮어쓰기보다 앞에 있다"


def test_gate_vs_llm_이_덮어쓰기_안에서_붙는다():
    jg = _llm_said(_jg())                      # LLM=파르마 · 코드=코모
    apply_code_verdict(jg)
    assert jg["gate_vs_llm"] == "diff", "LLM 이 반대편을 골랐는데 same 이다"

    jg2 = _llm_said(_jg(), 승자=COMO)           # 둘 다 코모
    apply_code_verdict(jg2)
    assert jg2["gate_vs_llm"] == "same"


# ═══════════════ U0-b — 종목 분기. 8199 실수 재발 방지

def test_code_pick이_종목으로_갈린다():
    """🔴 실사고 2026-09-15: D-10 을 검증하며 **축구를 야구 규칙으로 쟀다.**
    8199 Kyoto@Daejeon 은 p_code=0.4473 이라 `>= 0.5` 로는 '원정'인데,
    3-way 최대값(홈 45.1 / 무 27.1 / 원정 27.9)은 **홈승**이다.
    분기가 `code_pick` 한 곳에만 있다는 것을 계약으로 잠근다.
    """
    soccer = {"sport": "soccer", "home": "Daejeon Citizen", "away": "Kyoto Sanga FC",
              "p_code": 0.4473,
              "market_probs": {"Daejeon Citizen": 0.451, "Draw": 0.271,
                               "Kyoto Sanga FC": 0.279}}
    assert P.code_pick(soccer) == {"결과": "홈승"}, "축구를 야구 규칙으로 쟀다"

    baseball = {"sport": "mlb", "home": "H", "away": "A", "p_code": 0.4473}
    assert P.code_pick(baseball) == {"승자": "A"}, "야구는 0.5 기준이다"

    # 같은 숫자인데 결과가 다르다 — 그게 분기의 증거다
    assert P.code_pick(soccer) != P.code_pick(baseball)


def test_종목_분기가_한_곳에만_있다():
    """🔴 사본 금지 — 다른 곳에서 승패 방향을 또 정하면 축구가 틀린다."""
    import pathlib
    import re

    #: "p_code 를 0.5 와 비교" 하는 줄. 있어도 되는 곳은 `prob.code_pick` 뿐이다.
    pat = re.compile(r"p_code[^\n]{0,24}>=\s*0\.5|>=\s*0\.5[^\n]{0,24}p_code"
                     r"|float\(p\)\s*>=\s*0\.5|p\)\s*>=\s*0\.5")
    hits = []
    for f in pathlib.Path("app").rglob("*.py"):
        for i, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if ln.strip().startswith("#") or pat.search(ln) is None:
                continue
            hits.append(f"{f}:{i}")
    assert all(h.startswith("app/engine/prob.py") for h in hits), hits
    assert len(hits) <= 1, f"분기가 여러 곳이다: {hits}"

    # 그리고 그 한 곳이 종목을 본다
    import inspect
    src = inspect.getsource(P.code_pick)
    assert 'sport' in src and 'soccer' in src
    assert "market_triple" in src, "축구 3-way 를 안 본다"
