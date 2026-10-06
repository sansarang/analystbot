"""🔴🔴 **보드 캡처 → 글** — 네 층 지시서 §2-6. **로컬에서만 돈다.**

> 사용자가 캡처 이미지를 보내면 **로컬 OCR**(무료 오픈소스, 한국어 지원 — 예:
> PaddleOCR·Tesseract kor)로 텍스트를 뽑아 같은 파서로. **로컬에서만 돌고 외부
> API 를 부르지 않는다.** 인식 결과를 카드에 **원문 그대로** 보여 주고, 못 읽은
> 줄은 *"못 읽음"*.

🔴 **이 기계에 있는 것으로 한다** — 실측 2026-10-06:
   `/opt/homebrew/bin/tesseract` · 언어 `eng`·`kor` 둘 다 설치돼 있다.
   ⚠️ 파이썬 래퍼(`pytesseract`)는 **없다** — 그래서 **실행 파일을 직접** 부른다
      (새 의존성을 끌어오지 않는다).
🔴 **외부 OCR API 는 부르지 않는다**(§11 금지 · 계약이 AST 로 잠근다).
"""
from __future__ import annotations

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)

#: 🔴 실행 파일 이름. ⚠️ 경로를 박지 않는다 — `PATH` 에서 찾는다
BINARY = "tesseract"
#: 🔴 한국어 + 영어. 실측: 이 기계의 tessdata 에 둘 다 있다
LANGS = "kor+eng"
TIMEOUT_SEC = 30


def available() -> tuple[bool, str]:
    """🔴 로컬 OCR 이 있나. `(있다, 사유)` — ⚠️ 없으면 **사유를 카드에 적는다**."""
    got = shutil.which(BINARY)
    if not got:
        return False, f"로컬 OCR 이 없다(`{BINARY}` 를 PATH 에서 못 찾았다)"
    return True, got


def read(path: str) -> tuple[str, str]:
    """🔴 이미지 → 글. `(글, 사유)`. ⚠️ 못 읽으면 **빈 글과 사유**다(예외 안 던진다).

    🔴 `--psm 6`(한 덩어리 글) 로 읽는다 — 보드 캡처는 표 모양이라 줄이 섞이면
       파서가 마켓을 못 찾는다.
    """
    ok, why = available()
    if not ok:
        return "", why
    cmd = [BINARY, path, "stdout", "-l", LANGS, "--psm", "6"]
    try:
        got = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=TIMEOUT_SEC, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return "", f"로컬 OCR 실행 실패 — {exc}"
    text = (got.stdout or "").strip()
    if not text:
        return "", (f"OCR 이 글을 못 뽑았다(exit {got.returncode}) — "
                    f"{(got.stderr or '').strip()[:80]}")
    logger.info("[ocr] %d자 ← %s", len(text), path)
    return text, f"로컬 OCR(tesseract {LANGS})"


def board_of(path: str):
    """🔴 캡처 → `(Board, 추가 줄, 못 읽은 줄, 원문)`. **원문을 함께 돌려준다**(§2-6).

    ⚠️ 원문을 안 돌려주면 카드가 *"인식 결과를 원문 그대로 보여 준다"* 를 못 지킨다.
    """
    from app.core import board as _board
    text, why = read(path)
    if not text:
        return None, [], [why], ""
    got, extra, bad = _board.parse(text)
    return got, extra, bad, text
