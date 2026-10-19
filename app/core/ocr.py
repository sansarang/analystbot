"""🔴🔴 **캡처 이미지 → 글** — **로컬에서만 돈다.**

🔴 쓰는 곳은 **XI 캡처 하나다**(`pipeline._xi_of` → `xicapture.parse`) — 확정
   라인업을 사용자가 캡처로 줄 때 그 글자를 뽑는다.

🔴🔴 **배당 보드 캡처는 걷혔다 — 사용자 지시 2026-10-19**
> 시장배당은 **아예 쓰지도 않는다.**

⚠️ 종전에는 `board_of` 가 캡처를 **보드 파서**(`core/board.parse`)에 넘겨 배당을
   읽었다(네 층 지시서 §2-6). 🔴 그 함수와 그 길을 지웠다 — 남은 것은 글자를
   뽑는 일(`read`)뿐이고 그것은 라인업이 쓴다.

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
