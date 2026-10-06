"""🔴🔴 **MPS 는 한 스레드가 소유한다** — 사용자 지시 2026-10-05.

> **락 추가로 땜질하지 않는다.**
>
> 1. **MPS 단일 스레드 소유**(PyTorch 이슈 #197805: MPS 는 2개 이상 스레드
>    동시 연산 시 SIGSEGV/SIGABRT)
>    · `rerank.py` 에 **모듈 전역** `ThreadPoolExecutor(max_workers=1,
>      thread_name_prefix="rerank")`.
>    · 모델 로드·추론은 **전부 이 실행기 안에서만.** 비동기 쪽은
>      `loop.run_in_executor(RERANK_EXEC, fn, ...)` 로만 부른다.
>    · `asyncio.to_thread` 로 재정렬을 부르는 곳을 **전부 제거.**
>    · 계약: 하위 8개 동시 호출 시 추론 스레드 이름이 전부 `rerank_0` 이고
>      **프로세스가 살아 있다**(실측 실행).
> 2. **시작 시 1회 로드 + 예열** — 지연 로드 함수 삭제. 로드 횟수 카운터.
>    로드 함수 첫 줄에 `__name__` 과 `id(sys.modules[__name__])` 를 로그.

⚠️ 실사고 2026-10-05(인도네시아–태국): 락을 넣었는데 로드가 **4→11회로
   늘고** 봇이 두 번 죽었다. 🔴 락은 **같은 스레드 풀을 보장하지 않는다** —
   MPS 는 소유 스레드가 하나여야 한다.
"""
from __future__ import annotations

import ast
import inspect

import pytest


def test_mps1_전용_실행기가_하나다():
    from app.research import rerank
    assert hasattr(rerank, "RERANK_EXEC"), (
        "🔴 `rerank.RERANK_EXEC`(전용 실행기)가 없다")
    ex = rerank.RERANK_EXEC
    assert ex._max_workers == 1, (
        f"🔴 작업자가 {ex._max_workers} 명이다 — MPS 는 **한 스레드**가 "
        f"소유해야 한다(PyTorch #197805)")
    assert ex._thread_name_prefix == "rerank", ex._thread_name_prefix






def test_mps1_to_thread_로_재정렬을_안_부른다():
    """🔴 *"`asyncio.to_thread` 로 재정렬을 부르는 곳을 전부 제거"*."""
    import pathlib
    bad: list[str] = []
    for f in sorted(pathlib.Path("app").rglob("*.py")):
        src = f.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "to_thread"):
                continue
            said = ast.dump(n)
            if "rerank" in said or "order" in said or "paragraphs" in said:
                bad.append(f"{f}:{n.lineno}")
    assert not bad, (
        f"🔴 `asyncio.to_thread` 로 재정렬을 부른다{bad} — MPS 소유가 깨진다")






def test_mps2_로드가_모듈_정체를_적는다():
    """🔴 *"로드 함수 첫 줄에 `__name__` 과 `id(sys.modules[__name__])` 로그"*.

    ⚠️ 두 이름이 나오면 **이중 import** 다 — 그것이 로드가 늘어난 원인일 수
       있다(측정으로 가린다).
    """
    from app.research import rerank
    src = inspect.getsource(rerank)
    assert "sys.modules[__name__]" in src, (
        "🔴 모듈 정체(`id(sys.modules[__name__])`)를 안 찍는다 — 이중 import "
        "를 가릴 수 없다")


def test_mps2_토크나이저_병렬을_끈다():
    """🔴 *"`TOKENIZERS_PARALLELISM=false` 를 봇 진입점에서 설정"*."""
    import pathlib
    said = pathlib.Path("app/bot/main.py").read_text(encoding="utf-8")
    assert "TOKENIZERS_PARALLELISM" in said, (
        "🔴 봇 진입점이 `TOKENIZERS_PARALLELISM` 을 안 끈다 — 토크나이저가 "
        "스레드를 띄워 MPS 소유를 흔든다")


def test_mps2_봇_진입점이_예열한다():
    """🔴 **배선**(#2) — 지연 로드를 지웠으니 **진입점이 올려야** 한다.

    ⚠️ 안 부르면 재정렬이 영원히 ③단이다(조용히 꺼진다).
    """
    import pathlib
    said = pathlib.Path("app/bot/main.py").read_text(encoding="utf-8")
    assert "warm(" in said, (
        "🔴 봇 진입점이 `rerank.warm()` 을 **안 부른다** — 지연 로드를 지웠으니 "
        "모델이 영원히 안 올라간다")
