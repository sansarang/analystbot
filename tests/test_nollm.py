"""[NOLLM] **판정은 코드가, 서술은 템플릿이.**

사용자 2026-09-22: "판정은 원래 코드에서 낸다… **서술도 템플릿으로 바꿔라**"

🔴 왜 — LLM 판정 3곳의 결과는 `apply_code_verdict` 가 **전부 덮어쓴다**(P0-1):
```
verdict.decide(verdict.py:141)  → 승자  ┐
matchup 재질의(matchup.py:1543) → 승자  ├→ 카드에 붙었다가 코드 값으로 교체
dbref.recheck(dbref.py:172)     → 승자  ┘
```
세 번 묻고 세 번 버리면서, 그 실패로 경기가 통째로 탈락했다 —
실측 2026-09-22: LLM 사슬 소진 → KBO **0/8** · NPB **0/5** 판정 전멸.
"""
from __future__ import annotations

import ast
import inspect

import pytest

from app.engine import narrate as N


# ── 스위치 ──────────────────────────────────────────────────────────

def test_스위치가_설정에_있고_꺼져_있다():
    from app.engine import rules as R
    from app.engine.matchup import _llm_verdict_on

    assert R.get("judge.llm_verdict") is False
    assert _llm_verdict_on() is False


def test_설정을_못_읽으면_켜진_것으로_본다(monkeypatch):
    """⚠️ 스위치 고장이 판정 경로를 **조용히** 바꾸면 그게 더 나쁘다
    (`source_gate.enabled` 와 같은 규약)."""
    from app.engine import matchup as M

    monkeypatch.setattr("app.engine.rules.get",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert M._llm_verdict_on() is True


def test_스위치_원본이_한_곳이다():
    """🔴 사본 금지 — `dbref` 는 `matchup._llm_verdict_on` 을 부른다.

    ⚠️ **설정을 읽는지**를 본다. `judge.llm_verdict` 라는 **글자**는 로그
       라벨에도 나온다(`"생략(judge.llm_verdict=false)"`) — 원문을 grep 하면
       그 라벨에 걸려 거짓으로 실패한다. `rules.get` 호출 유무로 판별한다.
    """
    import ast

    from app.engine import dbref as D

    src = inspect.getsource(D.recheck)
    assert "_llm_verdict_on" in src, "스위치를 안 본다"

    import textwrap

    tree = ast.parse(textwrap.dedent(src))
    reads = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        fn = n.func
        name = getattr(fn, "id", "") or getattr(fn, "attr", "")
        if name != "get":
            continue
        for a in n.args:
            if isinstance(a, ast.Constant) and "judge." in str(a.value):
                reads.append(a.value)
    assert reads == [], f"dbref 가 설정을 직접 읽는다(두 벌): {reads}"


# ── 판정 경로 ───────────────────────────────────────────────────────

def _code_lines(obj) -> str:
    """🔴 주석을 뗀다 — 원문 grep 은 **내 주석**에 걸린다(D46, 이 저장소 7회)."""
    return "\n".join(ln.split("#", 1)[0]
                     for ln in inspect.getsource(obj).splitlines())


def test_꺼지면_LLM_에_승자를_안_묻는다():
    """🔴 이 단위의 핵심."""
    from app.engine import matchup as M

    src = _code_lines(M)
    i_gate = src.index("if not _llm_verdict_on():")
    i_call = src.index("v = await verdict.decide(", i_gate)
    seg = src[i_gate:i_call]
    assert "else:" in seg, "LLM 호출이 스위치 밖에 있다"
    assert '"승자": None' in seg, "승자를 지어낸다"


def test_승자를_비우고_코드에_맡긴다():
    """🔴 **지어내지 않는다.** 파이프라인이 뼈대를 붙인 뒤 코드가 채운다."""
    from app.engine import matchup as M

    src = _code_lines(M)
    seg = src[src.index("if not _llm_verdict_on():"):][:400]
    assert '"확신": None' in seg


def test_탈락_경로가_사라지지_않았다():
    """⚠️ 스위치를 켜면 종전대로 동작해야 한다 — 되돌릴 길을 막지 않는다."""
    from app.engine import matchup as M

    src = _code_lines(M)
    assert 'return await _drop("판정 실패")' in src


def test_dbref_는_DB_사실을_남긴다():
    """🔴 `있음`·`없음` 은 **DB 사실**이다 — LLM 이 아니다. 끄는 것은
    그 뒤의 재판정뿐이다."""
    from app.engine import dbref as D

    src = _code_lines(D.recheck)
    i_out = src.index('out = {"있음"')
    i_gate = src.index("if not _llm_verdict_on():")
    assert i_out < i_gate, "사실을 채우기 전에 빠져나간다"


# ── 템플릿 서술 ─────────────────────────────────────────────────────

def _jg(**kw):
    base = {"home": "Samsung Lions", "away": "NC Dinos",
            "home_kr": "삼성 라이온즈", "away_kr": "NC 다이노스",
            "winner": "Samsung Lions", "p_code": 0.6522, "adj_pp": "{}",
            "lineup_status": "", "order_v3": {}}
    base.update(kw)
    return base


def test_서술이_LLM_을_안_부른다():
    """🔴 순수 함수다 — `hypothesis.py` 와 같은 규약."""
    src = inspect.getsource(N)
    tree = ast.parse(src)
    called = {getattr(n.func, "id", "") or getattr(n.func, "attr", "")
              for n in ast.walk(tree) if isinstance(n, ast.Call)}
    for banned in ("complete_json", "ask_json", "fetch", "execute", "post"):
        assert banned not in called, f"서술이 {banned} 를 부른다"
    assert "httpx" not in src and "await " not in src


def test_시장이라고_적지_우리_판단이라고_안_적는다():
    """🔴 `p_code` 는 시장 뼈대다(실측: p_code == p_market 이 80%).
    "우리가 계산했다"로 읽히면 거짓이다."""
    line = N.market_line(_jg())
    assert line and "시장" in line
    assert "삼성 라이온즈" in line


def test_조정이_0이면_0이라고_적는다():
    """⚠️ 조용히 비우면 '분석했다'로 읽힌다."""
    v = N.adjust_line(_jg(adj_pp="{}"))
    assert v and "시장값 그대로" in v
    v2 = N.adjust_line(_jg(adj_pp='{"결장": -2.5}'))
    assert v2 and "결장" in v2 and "-2.5" in v2


def test_JSON_원문을_서술에_안_싣는다():
    """🔴 카드에 `{"home": {"팀": …` 이 그대로 찍히던 자리다(실측 card:kbo)."""
    jg = _jg(order_v3={"자료": [
        {"이름": "선발 최근 등판", "값": '{"home": {"팀": "Samsung"}}'},
        {"이름": "홈 선발 예고", "값": "페덱"}]})
    ev = N.evidence_lines(jg)
    assert ev == ["홈 선발 예고 — 페덱"], ev


def test_못_본_것을_적는다():
    """🔴 조용한 0 금지."""
    v = N.missing_line(_jg(order_v3={"없는것": ["파크팩터", "1군 등록"]}))
    assert v and "파크팩터" in v
    assert N.missing_line(_jg()) is None


def test_값이_없으면_그_줄을_뺀다():
    """🔴 절대 규칙 6 — 재료 없으면 분석 생성 금지."""
    assert N.market_line({"p_code": None}) is None
    assert N.market_line(_jg(winner=None)) is None
    # 승자도 확률도 없으면 서술은 조정·확신 줄만 남는다(빈 문자열은 아니다)
    s = N.story({"home": "A", "away": "B"})
    assert "시장은" not in s


def test_서술이_빈_카드를_만들지_않는다():
    """⚠️ 아무것도 없으면 **빈 문자열** — 빈 줄을 만들지 않는다."""
    s = N.story({})
    assert isinstance(s, str)
    assert not s.startswith("\n")


def test_matchup_이_템플릿을_쓴다():
    """🔴 배선 확인 — 서술이 비면 템플릿이 채운다."""
    from app.engine import matchup as M

    src = _code_lines(M)
    assert "from app.engine.narrate import story" in src
    i_story = src.index("_story = ")
    i_tmpl = src.index("narrate import story")
    assert i_story < i_tmpl, "템플릿이 LLM 서술보다 먼저 덮어쓴다"


# ── [SWAP-3T 2026-09-22] 흐름의 서술도 템플릿이다 ──────────────────────

def _flow_state(**kw):
    class S:
        game_id = "7"
        home = "Samsung Lions"
        away = "NC Dinos"
        pick_side = "home"
        n04_hyp = [{"text": "우리 픽(home)을 무너뜨릴 근거"}]
        n05_evidence = [{"var": "lineup_out", "value": "없음"}]
        # ⚠️ [VIS-1] 실제 ⑥이 쓰는 값으로 맞췄다 — 종전 대역은 "확인"/"모름"
        #    이라는 **없는 문자열**을 써서 서술이 그것을 읽지 못했다.
        n06_verdict = {"per_var": {"lineup_out": "confirmed",
                                   "bullpen_3d": "unknown"}}
        n07_adjust = []
        n08_pcode = {"p_code_pick": 0.6522}
        n09_conf = {"grade": "B"}
        n11_value = {}
        n12_text = None

    for k, v in kw.items():
        setattr(S, k, v)
    return S()


def test_흐름_서술이_LLM_을_안_부른다():
    """🔴 사용자 지시는 **흐름에도** 적용된다 — 구경로에만 붙여 두면
    경로를 갈아끼울 때 다시 LLM 서술로 돌아간다."""
    import asyncio

    from app.flow.nodes import n12_text as N

    s = asyncio.run(N.run(_flow_state(), None))
    assert s.n12_text["source"] == "template"
    assert s.n12_text["hallucination"] is False
    assert len(s.n12_text["sentences"]) >= 3


def test_흐름_서술이_지어낸_숫자를_못_만든다():
    """🔴 템플릿은 상태에 있는 값만 옮긴다 — 지어내기가 **구조적으로 불가능**하다."""
    from app.engine.narrate import story_flow

    lines = story_flow(_flow_state())
    joined = " ".join(lines)
    # 상태에 있는 숫자만 나온다(0.6522 → 밴드 말로 바뀐다)
    assert "Samsung Lions" in joined
    # 🔴 [VIS-1 2026-09-23] 글의 **형식**이 바뀌었다(사용자 지시 "알기 쉽게").
    #    이 시험의 뜻은 그대로다 — **상태에 있는 값만 나온다.**
    #    종전에는 "확인 1 · 모름 1" 로 셌고, 지금은 사람 이름으로 적는다.
    assert "결장" in joined, joined          # lineup_out 의 사람 이름
    assert "불펜 3일 소모" in joined, joined   # bullpen_3d — 아직 못 본 것
    assert "65.2%" in joined, "코드 확률이 사라졌다"


def test_흐름_서술이_미상을_숨기지_않는다():
    """🔴 채점 결과를 그대로 적는다 — 미상이 이 봇의 값어치다."""
    from app.engine.narrate import flow_verdict_line

    v = flow_verdict_line(_flow_state())
    # 🔴 [VIS-1] 뜻은 그대로다 — **미상을 숨기지 않는다.** 표현만 사람 말로
    #    바뀌었다(종전 `채점: confirmed 1 · unknown 1.`).
    assert v and "모름" in v, v
    assert "불펜 3일 소모" in v, v          # bullpen_3d 가 아직 모름
    assert "unknown" not in v and "confirmed" not in v, v


def test_흐름_조정이_0이면_0이라고_적는다():
    from app.engine.narrate import flow_adjust_line

    assert "시장값 그대로" in flow_adjust_line(_flow_state())
    s = _flow_state(n07_adjust=[{"var": "lineup_out", "pp": -1.5}])
    assert "-1.5" in flow_adjust_line(s)


def test_흐름_서술이_값_없으면_줄을_뺀다():
    """🔴 절대 규칙 6 — 재료 없으면 분석 생성 금지."""
    from app.engine.narrate import story_flow

    class _Empty:
        pass

    assert story_flow(_Empty()) == []


def test_흐름_서술도_같은_스위치를_본다():
    """🔴 사본 금지 — 판정과 서술이 같은 스위치로 갈린다."""
    import inspect

    from app.flow.nodes import n12_text as N

    src = inspect.getsource(N.run)
    assert "_llm_verdict_on" in src
    assert "judge.llm_verdict" not in src.replace("`judge.llm_verdict`", ""), \
        "n12_text 가 설정을 직접 읽는다(두 벌)"
