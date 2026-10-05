"""🔴🔴 **타입 경계** — 사용자 지시 2026-10-05 (3번).

> · `pyright` 를 **테스트 스위트의 계약 하나로** 돈다(에러 0 이어야 초록).
>   기존 코드 basic 에러는 **목록만 뽑아 `questions/` 에 적고**, `research/` 와
>   그것이 부르는 경계(`lead.merge` 입력·출력)만 **지금** 고친다.
> · `lead.merge` 입력 타입을 **하위 에이전트 출력 타입 하나로 고정**.
>   **`dict(v)` 금지** — 필요하면 그 타입의 메서드로.

⚠️ 왜 — 두 크래시가 모두 **꼴 불일치**였다:
   ① `done.variables` 가 **문자열**로 와서 `row.get` 이 터졌다(변수 15,455자 소실)
   ② `lead.merge` 가 **`Classified`** 를 받아 `dict(v)` 가 터졌다(봇 사망)
   🔴 둘 다 *"받는 쪽이 꼴을 믿었다"* 다 — 타입이 그것을 미리 잡는다.
"""
from __future__ import annotations

import ast
import inspect
import json
import subprocess


def test_t3_research_는_pyright_에러_0이다():
    """🔴 `app/research/*` 는 **strict** 이고 에러 0 이어야 한다."""
    got = subprocess.run(["uv", "run", "pyright", "--outputjson"],
                         capture_output=True, text=True, check=False)
    box = json.loads(got.stdout or "{}")
    bad = [d for d in box.get("generalDiagnostics", [])
           if d.get("severity") == "error" and "/research/" in d.get("file", "")]
    said = [f"{d['file'].split('analystbot/')[-1]}:"
            f"{d['range']['start']['line'] + 1} {d['message'][:90]}"
            for d in bad]
    assert not bad, "🔴 `app/research/` pyright 에러:\n  " + "\n  ".join(said)


def test_t3_merge_가_dict_로_바꾸지_않는다():
    """🔴 *"`dict(v)` 금지 — 필요하면 그 타입의 메서드로"*."""
    from app.research import lead
    tree = ast.parse(inspect.getsource(lead.merge))
    bad = [n for n in ast.walk(tree)
           if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
           and n.func.id == "dict" and n.args]
    assert not bad, (
        f"🔴 `merge` 가 `dict(…)` 로 꼴을 바꾼다({len(bad)}곳) — 원본 객체를 "
        f"잃는다(실사고 2026-10-05: 봇이 죽었다)")


def test_t3_merge_입력_타입이_하나다():
    """🔴 입력 타입을 **하위 에이전트 출력 타입 하나**로 고정했나."""
    from app.research import lead
    assert hasattr(lead, "SubtaskOut"), (
        "🔴 `lead.SubtaskOut`(하위 출력 타입)이 없다 — 입력이 `list` 면 "
        "무엇이 오는지 아무도 모른다")
    sig = inspect.signature(lead.merge)
    said = str(sig.parameters["parts"].annotation)
    assert "SubtaskOut" in said, (
        f"🔴 `merge(parts)` 의 타입이 `{said}` 다 — `SubtaskOut` 로 고정해라")


def test_t3_기존_에러를_questions_에_적었다():
    """🔴 *"기존 코드 basic 에러는 **목록만** 뽑아 `questions/` 에 적고"*."""
    import pathlib
    box = pathlib.Path("docs/fable/questions")
    hits = [f for f in box.glob("*.md")
            if "pyright" in f.read_text(encoding="utf-8").lower()]
    assert hits, (
        "🔴 `questions/` 에 pyright 에러 목록이 없다 — 범위 밖 결함은 적어 "
        "두고 현재 단계를 계속한다(v4 §13)")
