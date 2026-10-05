"""🔴🔴 **묵은 바이트코드를 구조로 막는다** — 사용자 지시 2026-10-04.

> 같은 함정에 두 번 빠졌으면 **규율 한 줄로는 세 번째를 못 막는다.** 두 가지를
> 코드로 박아라.
> ① 테스트·돌연변이 실행기에 `PYTHONDONTWRITEBYTECODE=1` 을 고정하고, 스위트
>    시작 전에 `__pycache__` 를 지운다.
> ② 돌연변이 복원을 `cp` 가 아니라 `git checkout -- <file>` 로 한다.
>    복원 뒤 `git diff --quiet` 가 아니면 실패.

⚠️ **두 번 다쳤다**:
   2026-10-02 `effect_of("느낌")` 가 되돌린 뒤에도 `제거` 를 냈다.
   2026-10-04 되돌린 돌연변이가 빨간 채였고 **전역 오염으로 오진**했다 —
              디렉터리 이분·`label_of` 계측·`is_code` 확인까지 네 번 헛짚었다.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_pyc_스위트가_바이트코드를_안_쓴다():
    """🔴 ① — **이 프로세스**와 **자식 프로세스** 둘 다."""
    assert sys.dont_write_bytecode is True, (
        "🔴 이 프로세스가 `.pyc` 를 쓴다 — `conftest._drop_bytecode()` 가 "
        "안 불렸다")
    assert os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", (
        "🔴 **자식 프로세스**가 `.pyc` 를 쓴다 — 계약 몇 개가 `subprocess` 로 "
        "pytest 를 부른다(그 자식이 묵은 바이트코드를 남긴다)")


def test_pyc_스위트_시작_전에_치운다():
    """🔴 ① — 지우는 **자리가 있고** 실제로 지운 뒤여야 한다.

    ⚠️ `conftest.pytest_configure` 가 이미 돌았다 — 그러니 **지금 없어야** 한다.
    """
    from tests.conftest import _drop_bytecode
    left = [str(d) for d in ROOT.rglob("__pycache__")
            if not str(d).startswith(str(ROOT / ".venv"))]
    assert not left, (
        f"🔴 `__pycache__` 가 **남아 있다**({len(left)}개): {left[:4]} — "
        f"스위트 시작 전에 지워야 한다")
    # 🔴 그리고 그 함수가 **실제로 지우는가** — 하나 만들어 보고 센다
    #  ⚠️ **`finally` 로 반드시 치운다.** 실측 2026-10-04: 첫 판이 여기서
    #     터져 탐침 디렉터리가 남았고, **다음 판의 첫 단정**(`left` 가 비었나)이
    #     그것 때문에 깨졌다 — 시험이 **스스로를 오염시켰다.**
    made = ROOT / "tests" / "__pycache__"
    try:
        made.mkdir(exist_ok=True)
        (made / "x.pyc").write_bytes(b"x")
        got = _drop_bytecode()
        assert not made.exists(), "🔴 `_drop_bytecode()` 가 안 지웠다"
        assert any("__pycache__" in x for x in got), got
    finally:
        shutil.rmtree(made, ignore_errors=True)


def test_pyc_돌연변이_실행기가_git_으로_복원한다():
    """🔴🔴 ② — `cp` 가 아니라 `git checkout`, 그리고 **복원을 확인**한다."""
    from tests._helpers import strip_sh
    sh = (ROOT / "tools" / "mutate.sh")
    assert sh.exists(), "🔴 돌연변이 실행기가 없다(`tools/mutate.sh`)"
    # 🔴🔴 **주석을 걷고 본다**(D46) — ⚠️ 이 계약의 첫 판이 **내 설명 주석**에
    #    걸려 빨개졌다(*"종전엔 `cp` 였다"* 를 *"`cp` 를 부른다"* 로 읽었다).
    body = strip_sh(sh.read_text(encoding="utf-8"))
    # 🔴 복원이 `git checkout` 이어야 한다
    assert "git checkout -- " in body, (
        "🔴 복원이 `git checkout` 이 아니다 — `cp` 는 묵은 `.pyc` 와 미커밋 "
        "변경을 함께 샌다")
    # 🔴 복원 **뒤** 깨끗한지 본다
    after = body.split("git checkout -- ", 1)[1]
    assert "git diff --quiet" in after, (
        "🔴 복원 뒤 `git diff --quiet` 로 **확인하지 않는다**")
    # 🔴 치환이 **먹었나**도 본다(규율 8)
    assert body.count("git diff --quiet") >= 3, (
        "🔴 ① 미커밋 변경 거부 ② 치환이 먹었나 ③ 복원 확인 — 셋 다 있어야 한다")
    # 🔴 **통과하는 돌연변이를 실패로** 다룬다(§9-5)
    assert "failed" in body and "§9-5" in body, (
        "🔴 통과한 돌연변이를 **실패로** 다루지 않는다 — §9-5 는 그것을 "
        "*계약이 없다*는 뜻으로 읽는다")
    # ⚠️ `cp` 로 되돌리는 줄이 **남아 있지 않아야** 한다(주석은 뺐다)
    assert "cp " not in body, (
        f"🔴 `cp` 로 되돌리는 줄이 남아 있다: "
        f"{[x for x in body.splitlines() if 'cp ' in x]}")


def test_pyc_실행기가_미커밋_변경을_거부한다():
    """🔴 `git checkout` 은 작업을 **지운다** — 그래서 먼저 거부해야 한다.

    ⚠️ 규율 9 가 `git stash` 를 금지했다(2026-10-04 에 작업을 치웠다).
       🔴 여기서도 치우지 않는다 — **거부하고 사람에게 돌려준다.**
    """
    from tests._helpers import strip_sh
    body = strip_sh((ROOT / "tools" / "mutate.sh").read_text(encoding="utf-8"))
    head = body.split("perl", 1)[0]
    assert "git diff --quiet" in head and "exit 2" in head, (
        "🔴 돌연변이를 **넣기 전에** 미커밋 변경을 거부하지 않는다")
    assert "git stash" not in body, "🔴 `git stash` 는 금지다(규율 9)"
