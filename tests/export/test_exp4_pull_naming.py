"""[EXP-4] 회수 파일 이름 — **서버 이름을 그대로 쓴다.**

🔴 종전 규칙은 "겹치면 `_r2`"였는데, 서버도 재실행 때 `_r2` 를 붙인다.
   두 `_r2` 의 뜻이 달라서(로컬=두 번째 회수 · 서버=두 번째 실행) 같은 이름이
   다른 내용을 가리켰다. 실측으로 잡았다 — 로컬 `_lineup_r2.md` 는 서버의
   `_lineup.md` 사본이었고, 서버의 진짜 `_lineup_r2.md` 와 내용이 달랐다.
🔴 이름이 같고 **내용도 같으면** 다시 받지 않는다. 같은 파일을 두 벌 두면
   어느 쪽이 최신인지 사람이 알 수 없다.
"""
from __future__ import annotations

import pathlib
import re

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "tools" / "pull_export.sh"


def _body() -> str:
    return "\n".join(l for l in SCRIPT.read_text(encoding="utf-8").splitlines()
                     if not l.strip().startswith("#"))


def test_로컬에서_r2_를_붙이지_않는다():
    body = _body()
    assert not re.search(r'_r\$\{?n\}?', body), \
        "로컬이 _r2 를 붙인다 — 서버의 _r2 와 뜻이 충돌한다"


def test_같은_내용이면_건너뛴다():
    body = _body()
    assert "cmp" in body or "shasum" in body or "md5" in body, \
        "내용 비교 없이 덮거나 늘린다"


def test_다르면_서버_시각을_붙인다():
    body = _body()
    assert "date -r" in body, "서버 파일의 수정 시각을 읽지 않는다"
    assert "__${ts}" in body, "그 시각을 이름에 붙이지 않는다"


def test_붙이는_시각은_KST_다():
    """🔴 이 저장소는 표기를 항상 KST 로 한다 — 파일명도 예외가 아니다."""
    assert "TZ=Asia/Seoul date -r" in _body()
