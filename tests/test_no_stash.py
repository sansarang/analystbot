"""🔴🔴 **`git stash` 를 쓸 수 없게 한다** — 규율 9를 구조로 박는다.

══════════════════════════════════════════════════════════════════
🔴 왜 — 같은 실수를 **두 번** 했다
══════════════════════════════════════════════════════════════════

⚠️ 2026-10-04: `git stash --keep-index` 가 작업을 치워 복구 커맨드를 썼다.
   → CLAUDE.md 규율 9 가 `git stash` 를 **금지**했다.
⚠️ 2026-10-05: 그 규율을 적어 둔 뒤에도 **또 썼다**(`git stash push -q -m tmp`).
   미커밋 작업 둘(`app/openworld.py`·계약)이 치워졌고 `stash pop` 으로 되돌렸다.

🔴 사용자 지시 2026-10-04: *"같은 함정에 두 번 빠졌으면 **규율 한 줄로는 세
   번째를 못 막는다.** 두 가지를 코드로 박아라."* — 그 지시를 이 자리에도 쓴다.

🔴 **막을 수 없다 — 그래서 탐지한다**(실측 2026-10-05)

⚠️ 먼저 `git config alias.stash` 로 덮으려 했다. 🔴 **안 된다**: git 은 **내장
   명령을 별칭으로 덮지 않는다.** 실측했다:

```
git config --local alias.stash '!echo 금지; exit 2'
git stash push -q -m 확인용 -- probe_x.txt
  → exit=0 · stash@{0} 생김 · 파일이 **치워졌다**   🔴 별칭이 안 먹었다
```

🔴 그래서 **쓰는 것을 막는 대신 쓴 것을 잡는다** — 스위트가 돌 때마다
   *"치워 둔 작업이 있나"* 를 본다. ⚠️ 커밋 전에 스위트를 돌리는 규율(#6)과
   합쳐지면, **치워 둔 채로 커밋하는 일**은 막힌다.
⚠️ 이것은 예방이 아니라 **탐지**다 — 그 한계를 숨기지 않는다.
"""
from __future__ import annotations

import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    got = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                         text=True, check=False)
    return (got.stdout or "").strip()


def test_stash_를_별칭으로는_못_막는다():
    """🔴 **실측을 계약으로** — 별칭을 믿지 않게 못 박는다.

    ⚠️ 내가 `alias.stash` 를 걸고 *"막혔다"* 고 적을 뻔했다. 🔴 git 은 내장
       명령을 별칭으로 **덮지 않는다** — 그 사실을 여기 남긴다.
    """
    said = _git("config", "--local", "--get", "alias.stash")
    assert not said, (
        f"🔴 `alias.stash` 가 걸려 있다 — **그것은 막지 못한다**(실측 "
        f"2026-10-05: 별칭이 걸린 채로 `git stash push` 가 그냥 돌았다). "
        f"쓸모 없는 별칭은 *막혔다는 착각*을 준다: {said}")


def test_stash_가_비어_있다():
    """🔴 **치워 둔 작업이 없어야** 한다 — 있으면 누군가 썼고 안 되돌렸다."""
    got = _git("stash", "list")
    # ⚠️ 별칭이 걸리면 `stash list` 도 거부된다 — 그때는 **저장소 파일**을 본다
    if "금지" in got:
        p = ROOT / ".git" / "refs" / "stash"
        assert not p.exists(), (
            f"🔴 **치워 둔 작업이 남아 있다**({p}) — 되돌려라(`git stash pop`)")
        return
    assert not got, f"🔴 **치워 둔 작업이 남아 있다**:\n{got}"


def test_규율_9가_파일에_있다():
    """🔴 구조로 막아도 **까닭은 글로** 남는다(다음 세션이 읽는다)."""
    said = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "git stash` 는 쓰지 않는다" in said or "git stash" in said, "규율 9"
