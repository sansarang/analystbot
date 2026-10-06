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

import pytest


@pytest.mark.slow
def test_t3_research_는_pyright_에러_0이다():
    """🔴 `app/research/*` 는 **strict** 이고 에러 0 이어야 한다.

    ⚠️ **`slow` 다**(사용자 지시 2026-10-05 4번): *"pyright 는 pytest 밖으로 —
       별도 명령(`make typecheck`)으로, 커밋 전 한 번만."* 🔴 pyright 가
       매번 10초를 먹어 스위트를 늦췄다. `make typecheck` 가 원본이고 이
       계약은 **마감 직전 한 번** 돈다.
    """
    got = subprocess.run(["uv", "run", "pyright", "--outputjson"],
                         capture_output=True, text=True, check=False)
    box = json.loads(got.stdout or "{}")
    bad = [d for d in box.get("generalDiagnostics", [])
           if d.get("severity") == "error" and "/research/" in d.get("file", "")]
    said = [f"{d['file'].split('analystbot/')[-1]}:"
            f"{d['range']['start']['line'] + 1} {d['message'][:90]}"
            for d in bad]
    assert not bad, "🔴 `app/research/` pyright 에러:\n  " + "\n  ".join(said)






def test_t3_기존_에러를_questions_에_적었다():
    """🔴 *"기존 코드 basic 에러는 **목록만** 뽑아 `questions/` 에 적고"*."""
    import pathlib
    box = pathlib.Path("docs/fable/questions")
    hits = [f for f in box.glob("*.md")
            if "pyright" in f.read_text(encoding="utf-8").lower()]
    assert hits, (
        "🔴 `questions/` 에 pyright 에러 목록이 없다 — 범위 밖 결함은 적어 "
        "두고 현재 단계를 계속한다(v4 §13)")
