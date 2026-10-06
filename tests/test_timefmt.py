"""🔴🔴 절대규칙 2 — **표시는 KST 다**. 그 변환을 건너뛴 자리를 찾는다.

══════════════════════════════════════════════════════════════════
🔴 왜 이 계약이 생겼나 — **같은 결함을 두 번 냈다**
══════════════════════════════════════════════════════════════════

실측 2026-09-27 에 `run.kst_label` 을 만들어 고쳤는데, 그 뒤에 쓴 코드 둘이
같은 실수를 다시 했다. 실측 2026-10-03(엘살바도르 vs 자메이카):

```
findgame 로그   2026-10-03 11:00:00+09:00 KST     ← 맞다
카드 머리글      10-03 02:00 KST                  ← 🔴 9시간 틀렸다
```

🔴 **손으로 유지하는 목록을 두지 않는다**(CLAUDE.md #1) — 계약이 `app/` 을 훑어
   *"KST 라고 적는 형식화"* 를 **원본에서 자라게** 찾는다. 새 파일이 같은 실수를
   하면 그 파일을 적지 않아도 빨개진다.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import timefmt

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"

#: 🔴 변환이 사는 곳. 이 파일만 `astimezone` 을 직접 불러도 된다.
HOME = "timefmt.py"


def _sources() -> list[Path]:
    return sorted(p for p in APP.rglob("*.py") if p.name != "__pycache__")


def test_KST_라벨은_변환을_거친다():
    """🔴🔴 `app/` 안에서 **`KST` 라고 적는 모든 형식화**를 찾아 검사한다.

    두 꼴을 잡는다:
      ① `x.strftime(...)` 의 꼴 문자열에 `KST` 가 들어 있다
      ② `f"...{x.strftime(...)} KST..."` — 라벨이 **옆 글자**에 있다

    둘 다 **그 호출이 `astimezone` 을 거쳤거나** `timefmt.kst_label` 이어야 한다.
    ⚠️ ②가 실제로 다친 꼴이다 — 꼴 문자열에는 `KST` 가 없어서 ①만 보면 못 잡는다.
    """
    bad: list[str] = []
    for p in _sources():
        if p.name == HOME:
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # ② f-string 안에서 strftime 결과 옆에 KST 가 붙는 꼴
            if isinstance(node, ast.JoinedStr):
                flat = "".join(
                    v.value for v in node.values if isinstance(v, ast.Constant)
                    and isinstance(v.value, str))
                if "KST" not in flat:
                    continue
                for v in node.values:
                    if not isinstance(v, ast.FormattedValue):
                        continue
                    src = ast.unparse(v.value)
                    if ".strftime(" in src and "astimezone" not in src:
                        bad.append(f"{p.relative_to(ROOT)}:{node.lineno} — {src}")
            # ① 꼴 문자열 자체에 KST
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == "strftime":
                fmt = next((a.value for a in node.args
                            if isinstance(a, ast.Constant)
                            and isinstance(a.value, str)), "")
                if "KST" in fmt and "astimezone" not in ast.unparse(node.func.value):
                    bad.append(f"{p.relative_to(ROOT)}:{node.lineno} — "
                               f"{ast.unparse(node)}")
    assert not bad, (
        "🔴 KST 라고 적으면서 변환을 안 했다 — `timefmt.kst_label` 을 쓴다"
        f"(절대규칙 2):\n  " + "\n  ".join(bad))


def test_UTC를_KST라고_적으면_9시간_틀린다():
    """🔴 실측 그대로: `02:00+00` 은 **11:00 KST** 다."""
    utc = datetime(2026, 10, 3, 2, 0, tzinfo=timezone.utc)
    assert timefmt.kst_label(utc) == "10-03 11:00 KST"
    # ⚠️ 변환을 뺀 값(종전 결함)과 **다르다**는 것이 이 계약의 요점이다
    assert utc.strftime("%m-%d %H:%M") == "10-03 02:00"




def test_이미_KST인_값은_그대로다():
    kst = datetime(2026, 10, 3, 11, 0, tzinfo=timezone(timedelta(hours=9)))
    assert timefmt.kst_label(kst) == "10-03 11:00 KST"


