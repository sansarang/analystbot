"""🔴🔴 **LLM 표적 검색 계약** — 사용자 지시 2026-10-14.

> 3번·4번·5번은 딥서치에서 못 찾으면 **llm 이 찾게 한다** … llm 을 **전략예측
> 및 서치**로 쓰는 거다 · 🔴 *"llm 회상하는게 아니라 **서치**하는거라고"* ·
> *"llm이 검색할 대상은 **변수에 관련된 내용**이다 … **x search 가 약해서**"*

## 🔴 막는 것이 무엇인가
처음 만든 판은 모델 **기억**을 사실로 받았다(`s4b_recall`) — 사용자가 바로잡았다.
🔴 그래서 이 계약의 중심은 하나다: **LLM 은 질의만 낸다. 사실은 문서에서 온다.**

  GS1 LLM 출력 스키마에 **사실 칸이 없다**(질의 글자뿐)
  GS2 프롬프트가 *"사실을 말하지 않는다"* 를 못 박는다
  GS3 받은 질의는 **걸러서** 쓴다(팀 표기 · `llm.query_ok`)
  GS4 던지는 통로는 **기존 사슬**이다(새 엔진 금지)
  GS5 별칭은 **이름**에서 뽑는다(열쇠 `team:000455` 가 아니다)
  GS6 빈 칸 판정은 **한 곳**(`need`) · 얇은 묶음은 **설정**에서 읽는다
  GS7 확률 경로가 이 모듈을 **안 부른다**
  GS8 **s5 뒤**에 부른다
  GS9 공급자 **둘을 순서대로** 시도한다(한쪽이 0개를 내도 멈추지 않는다)
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD = "app/core/stages/s4b_gapsearch.py"


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _code(rel: str) -> str:
    """🔴 D46 — 독스트링·주석을 뺀 **코드만**."""
    said = _src(rel)
    drop: set[int] = set()
    for node in ast.walk(ast.parse(said)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = list(getattr(node, "body", []) or [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                one = body[0]
                for ln in range(one.lineno, (one.end_lineno or one.lineno) + 1):
                    drop.add(ln)
    return "\n".join(x for i, x in enumerate(said.splitlines(), 1)
                     if i not in drop and not x.strip().startswith("#"))


def test_gs1_output_has_no_fact_fields() -> None:
    """GS1 🔴🔴 — 스키마에 **질의 말고 아무것도** 없다."""
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages.s4b_gapsearch import GapQueries
    got = set(GapQueries.model_fields)
    assert got == {"queries", "langs"}, (
        f"GS1 🔴🔴 LLM 출력 칸이 {sorted(got)} 다 — `queries`·`langs` 둘만 "
        "허용한다. 칸을 더하는 순간 모델 **기억**이 사실로 들어온다(사용자가 "
        "바로잡은 그 지점이다)")
    # 🔴 `langs` 는 **열거로 잠겨** 있어야 한다 — 아무 글자나 들어오면 그 칸이
    #    사실을 나르는 통로가 된다.
    code = _code(MOD)
    assert 'enums={"langs": list(LANGS)}' in code, (
        "GS1 🔴🔴 `langs` 를 `enums` 로 안 잠갔다 — 모델이 그 칸에 아무 글자나 "
        "넣을 수 있다(언어 코드만 받아야 한다)")


def test_gs2_prompt_forbids_facts() -> None:
    """GS2 — 프롬프트가 *"사실을 말하지 않는다"* 를 적는다."""
    said = _src(MOD)
    for word in ("사실을 말하지 않는다", "아는 척하지 말고", "검색어만"):
        assert word in said, f"GS2 🔴 프롬프트에 `{word}` 가 없다"
    assert "답으로" in said, (
        "GS2 🔴 *'숫자·이름·상태를 답으로 쓰지 마라'* 가 없다")


def test_gs3_queries_are_filtered() -> None:
    """GS3 — 팀 표기·글자 규칙으로 거른다. 규칙은 **기존 것**을 부른다."""
    code = _code(MOD)
    assert "querywriter.keep(" in code, (
        "GS3 🔴 팀 표기 검사를 `querywriter.keep` 으로 안 한다(사본 금지)")
    assert "query_ok(" in code, (
        "GS3 🔴 글자 규칙(`app.llm.query_ok`)을 안 거친다 — 연산자·연도가 "
        "들어간 질의가 사슬로 간다")


def test_gs4_no_new_engine() -> None:
    """GS4 — 이 모듈이 **스스로 망에 나가지 않는다**(사슬이 던진다)."""
    code = _code(MOD)
    for bad in ("urlopen", "httpx", "requests", "aiohttp", "net.get("):
        assert bad not in code, (
            f"GS4 🔴 `{bad}` — 새 fetch 경로를 만들었다. 질의는 **기존 사슬**이 "
            "던진다(`SearchChain.query`)")


def test_gs5_aliases_from_names_not_keys() -> None:
    """GS5 🔴🔴 — 실사고 2026-10-14: 열쇠로 별칭을 뽑아 질의 **6개가 전부** 버려졌다."""
    code = _code(MOD)
    i = code.find("def ask(")
    body = code[i:]
    assert 'aliases_of(one)' in body, (
        "GS5 🔴 별칭을 이름(`one`)에서 안 뽑는다")
    assert 'aliases_of(str(getattr(ref, s' not in body, (
        "GS5 🔴🔴 별칭을 `ref.home`(=`team:000455` 내부 열쇠)에서 뽑는다 — "
        "별칭이 쓰레기가 되고 모든 질의가 `팀 표기 없음`으로 버려진다")
    # 🔴 돌려서 센다 — 이름 낱말이 표기에 들어가야 사람 꼴 질의가 산다
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core import querywriter
    kept, bad = querywriter.keep(["Como injury news"], aliases=["Como 1907", "Como"])
    assert kept, f"GS5 🔴 `Como` 표기로도 질의가 안 산다(버림 {bad})"


def test_gs6_one_judge_and_config() -> None:
    """GS6 — 빈 칸은 `need` 하나, 얇은 묶음은 **설정**에서 읽는다."""
    code = _code(MOD)
    assert "def need(" in code and "def thin_kinds(" in code, (
        "GS6 🔴 판정 함수 둘이 없다")
    i = code.find("def thin_kinds(")
    body = code[i:code.find("\ndef ", i + 10) if "\ndef " in code[i + 10:] else len(code)]
    assert "_sub.groups()" in body, (
        "GS6 🔴 묶음 목록을 **설정**(`research.subtasks.groups`)에서 안 읽는다 — "
        "코드에 베끼면 표를 고칠 때 한쪽만 바뀐다")
    assert "from_rule" in body, (
        "GS6 🔴 규칙으로 지은 변수를 **검색이 찾은 것**으로 센다 — 얇은 자리를 "
        "못 찾는다")


def test_gs7_not_in_probability_path() -> None:
    """GS7 — 확률을 만드는 모듈이 이것을 안 부른다."""
    bad = []
    for rel in ("app/core/probmodel.py", "app/core/sim.py",
                "app/core/matchup.py", "app/core/probfloor.py",
                "app/core/survive.py", "app/core/picks.py",
                "app/core/stages/s7_judge.py", "app/core/stages/s2e_matchup.py"):
        if (ROOT / rel).is_file() and "s4b_gapsearch" in _code(rel):
            bad.append(rel)
    assert not bad, f"GS7 🔴 확률 경로가 표적 검색을 읽는다: {bad}"


def test_gs8_after_s5() -> None:
    """GS8 — `s5_verify` 뒤에 부른다(그 전이면 '못 찾았다'를 말할 수 없다)."""
    for rel in ("app/core/pipeline.py", "tools/run_collect.py"):
        if not (ROOT / rel).is_file():
            continue
        code = _code(rel)
        i = code.find("s5_verify")
        j = max(code.find("s4b_gapsearch.ask"), code.find("_gapsearch.ask"))
        if i < 0 or j < 0:
            continue
        assert i < j, (
            f"GS8 🔴🔴 {rel} 에서 표적 검색이 `s5_verify` **앞**에 있다")


def test_gs9_both_providers() -> None:
    """GS9 — 공급자 둘(지시 2026-10-14: *"deepseek, solar pro 둘다 api가 있다"*).

    ⚠️ 실측 2026-10-14(페예노르트–코모): `deepseek` 가 질의를 **0개** 냈다.
       🔴 한 공급자에 매달면 그 단계가 통째로 죽는다.
    """
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core import llm
    from app.core.stages import s4b_gapsearch as g
    assert len(g.PROVIDERS) >= 2, (
        f"GS9 🔴 공급자가 {g.PROVIDERS} 하나뿐이다")
    ok = set(getattr(llm.Provider, "__args__", ()))
    bad = [p for p in g.PROVIDERS if ok and p not in ok]
    assert not bad, f"GS9 🔴 설정에 없는 공급자다: {bad} (쓸 수 있는 것 {sorted(ok)})"
    code = _code(MOD)
    assert "for pv in PROVIDERS" in code, (
        "GS9 🔴 공급자를 **순서대로** 돌지 않는다")
    assert "if rows:\n            break" in code, (
        "GS9 🔴 앞 공급자가 질의를 냈을 때 멈추지 않는다 — 둘 다 불러 돈을 "
        "두 번 쓴다")


def test_gs10_local_language_first() -> None:
    """GS10 — *"검색은 현지어 영어등 순으로 해라"*(지시 2026-10-14)."""
    said = _src(MOD)
    assert "현지어를 먼저" in said, (
        "GS10 🔴 프롬프트가 현지어 우선을 안 적는다")
    import sys
    sys.path.insert(0, str(ROOT))
    from app.core.stages import s4b_gapsearch as g
    assert g.LANGS[-1] == "en", (
        f"GS10 🔴 언어 열거의 **끝**이 `en` 이어야 한다(현지어가 앞) — {g.LANGS}")
    assert g.langs_of() == ["en"] or g.langs_of(), "GS10 🔴 기본 언어가 없다"
