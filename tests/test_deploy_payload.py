"""CFG-1 — 코드가 읽는 디렉토리가 배포 이미지에 전부 들어가는가.

🔴 실측 2026-09-13: `config/` 가 `Dockerfile` COPY 에 없어 서버에서 검색어·
   소스·티어가 **전부 비어 있었다.** 모듈은 예외 없이 빈 값으로 동작하므로
   로그 한 줄(`[scout] 설정 없음`)이 유일한 신호였다.
⚠️ 로컬 테스트는 저장소 루트에서 돌아 항상 파일을 본다 — **로컬에서는
   영원히 재현되지 않는다.** 그래서 `Dockerfile` 자체를 본다.
"""
import re
from pathlib import Path


def _copied() -> set[str]:
    txt = Path("Dockerfile").read_text(encoding="utf-8")
    out = set()
    for m in re.finditer(r"^COPY\s+(?!--from)(.+?)\s+\./", txt, re.M):
        for token in m.group(1).split():
            out.add(token.rstrip("/").split("/")[0])
    return out


def test_코드가_읽는_디렉토리가_전부_복사된다():
    """🔴 목록을 손으로 적지 않는다 — 소스에서 읽는 경로를 전수로 찾는다."""
    pat = re.compile(r'Path\(\s*["\']([A-Za-z0-9_]+)(?:/[^"\']*)?["\']')
    need: dict[str, str] = {}
    for p in Path("app").rglob("*.py"):
        for m in pat.finditer(p.read_text(encoding="utf-8")):
            top = m.group(1)
            if Path(top).is_dir():
                need.setdefault(top, str(p))
    # 🔴 예외는 **이유가 Dockerfile 에 적혀 있을 때만** 인정한다.
    #    `data/` 는 .gitignore 에 있어 COPY 하면 빌드가 깨진다
    #    (실사고 2026-08-26: `"/data": not found`). 빈 디렉토리로 만든다.
    txt = Path("Dockerfile").read_text(encoding="utf-8")
    assert "RUN mkdir -p /app/data" in txt
    assert "이미지에 넣지 않는다" in txt, "제외 이유가 Dockerfile 에 없다"
    known_empty = {"data"}
    missing = {k: v for k, v in need.items()
               if k not in _copied() and k not in known_empty}
    assert not missing, (
        f"코드가 읽는 디렉토리가 이미지에 없다: {missing}. "
        "Dockerfile 에 COPY 를 더하거나, 그 경로를 쓰지 마라.")


def test_config_가_들어_있다():
    assert "config" in _copied()
