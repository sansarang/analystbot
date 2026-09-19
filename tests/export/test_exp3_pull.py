"""[EXP-3] 산출물 회수 도구 — **두 가지 회귀만** 잠근다.

🔴 네트워크를 타는 부분은 테스트하지 않는다(컨테이너가 필요하다).
   여기서 막는 것은 코드를 읽으면 알 수 있는 두 가지다:
   ① 받는 쪽 경로가 `for_fable.resolve_out_dir()` 의 로컬 기본값과 갈라지는 것
   ② 볼륨 경로를 손으로 박아 넣는 것(마운트가 바뀌면 사본이 된다)
"""
from __future__ import annotations

import os
import pathlib
import re

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "tools" / "pull_export.sh"


def _body() -> str:
    """주석을 뺀 본문. 🔴 설명문에 적힌 경로가 계약을 통과시키면 안 된다."""
    out = []
    for line in SCRIPT.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("#"):
            continue
        out.append(line.split("#", 1)[0] if " #" in line else line)
    return "\n".join(out)


def test_실행권한이_있다():
    assert SCRIPT.exists(), SCRIPT
    assert os.access(SCRIPT, os.X_OK), "실행 권한이 없다"


def test_받는_곳이_내보내기의_로컬_기본값과_같다(monkeypatch):
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    from app.export.for_fable import resolve_out_dir

    local = resolve_out_dir()
    assert local.parent.name == "Downloads", local
    assert f'"$HOME/{local.parent.name}/{local.name}"' in _body(), local


def test_볼륨_경로를_손으로_박지_않았다():
    body = _body()
    assert "RAILWAY_VOLUME_MOUNT_PATH" in body, "볼륨 경로를 컨테이너에 묻지 않는다"
    # 본문에 `/data` 가 문자열로 박혀 있으면 사본이다.
    assert not re.search(r"(?<![A-Za-z_])/data(?![A-Za-z_])", body), \
        "볼륨 경로가 본문에 박혀 있다 — 사본 금지"


def test_받을_것이_없으면_0으로_끝내지_않는다():
    body = _body()
    assert "exit 1" in body, "빈손인데 성공으로 끝나면 조용한 0 이다"


def test_덮어쓰지_않는다():
    assert "_r${n}" in _body(), "이름이 겹칠 때 번호를 올리지 않는다"
