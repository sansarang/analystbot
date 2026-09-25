"""[CC-1 2026-09-25] 보고서는 **다섯 절**을 갖는다.

지시문 `cc_collab_0925`:
```
REPORT 형식(고정): # <지시문> · 커밋 <해시들> · 배포 <시각|미배포>
  ## 완료 조건 원문 / ## 전/후 표 / ## pytest 마지막 20줄 /
  ## 고쳐 쓴 기존 테스트(목록·사유) / ## 남은 것
```

🔴 **왜 계약으로 잠그나.** 형식이 흔들리면 페이블이 매번 다른 모양을 읽게 되고,
   그러면 "무엇이 빠졌나"를 사람이 눈으로 찾아야 한다. 특히 `완료 조건 원문`
   절이 빠지면 "끝났다"의 기준이 사라진다 — 이 저장소가 반복해 다친 자리다.
⚠️ 절 이름을 이 파일에 손으로 적지 않는다 — `README.md` 가 원본이고 거기서
   읽는다(사본 금지).
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FABLE = ROOT / "docs" / "fable"
REPORTS = FABLE / "reports"
README = FABLE / "README.md"


def required_sections() -> list[str]:
    """🔴 원본은 `docs/fable/README.md` 의 형식 블록이다.

    코드 블록 안의 `## ` 줄을 순서대로 읽는다 — 목록을 여기 다시 적으면
    README 가 바뀔 때 따라가지 않는다.
    """
    text = README.read_text(encoding="utf-8")
    block = text.split("```markdown", 1)[1].split("```", 1)[0]
    return [ln.strip() for ln in block.splitlines() if ln.startswith("## ")]


def report_files() -> list[pathlib.Path]:
    """**지시문 보고서만.**

    CC-1 이 정한 이름은 `<지시문이름>_report.md` 다. 그 규칙을 그대로 쓴다:
      · `_last_commit.md` — 훅이 만든 초안 재료(보고서 아님)
      · `status_<날짜>.md` — `/fable-status` 산출물(지시문 보고서 아님)
    ⚠️ 이름으로 거르는 것이 아니라 **규약 이름에 맞는 것만** 본다 — 그래야
       새 종류의 산출물이 생겨도 이 계약이 헛돌지 않는다.
    """
    if not REPORTS.is_dir():
        return []
    return sorted(REPORTS.glob("*_report.md"))


def test_형식_원본을_읽을_수_있다():
    got = required_sections()
    assert len(got) == 5, got
    assert got[0].startswith("## 완료 조건"), got


def test_폴더_규약이_그대로_있다():
    """🔴 폴더가 없으면 지시문이 갈 곳이 없다."""
    for name in ("inbox", "done", "reports", "questions", "answers", "exports"):
        assert (FABLE / name).is_dir(), f"docs/fable/{name}/ 이 없다"


@pytest.mark.parametrize("path", report_files() or [None])
def test_보고서가_다섯_절을_갖는다(path):
    if path is None:
        pytest.skip("reports/ 에 보고서가 아직 없다")
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines and lines[0].startswith("# "), f"{path.name}: 제목 줄이 없다"
    # 🔴 머리글에 커밋과 배포 상태가 있어야 한다 — 없으면 "언제 무엇이
    #    반영됐나"를 보고서만으로 답할 수 없다.
    assert "커밋" in lines[0], f"{path.name}: 제목에 커밋이 없다 — {lines[0]}"
    assert "배포" in lines[0], f"{path.name}: 제목에 배포 상태가 없다 — {lines[0]}"
    for sec in required_sections():
        assert sec in text, f"{path.name}: `{sec}` 절이 없다"


@pytest.mark.parametrize("path", report_files() or [None])
def test_완료_조건_절이_비어_있지_않다(path):
    """⚠️ 절 제목만 있고 내용이 없으면 형식만 맞춘 것이다."""
    if path is None:
        pytest.skip("reports/ 에 보고서가 아직 없다")
    text = path.read_text(encoding="utf-8")
    body = text.split("## 완료 조건 원문", 1)[1].split("\n## ", 1)[0]
    assert len(body.strip()) >= 20, f"{path.name}: 완료 조건이 비었다"
