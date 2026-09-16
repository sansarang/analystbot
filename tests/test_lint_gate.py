"""LINT-1 계약 — 린터가 버그 급만 막는다.

🔴 이 파일이 지키는 것 둘:
   (a) 중복 정의·없는 이름을 **잡는다** — 어제 스위트가 놓친 종류다.
   (b) 스타일로는 **안 막는다** — 스타일로 막으면 사람이 게이트를 통째로 끈다.
"""
import pathlib
import shutil
import subprocess
import tempfile

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
RUFF = REPO / ".venv/bin/ruff"
HOOK = REPO / ".claude/hooks/guard-bash.sh"

#: 게이트가 보는 규칙. 🔴 원본은 pyproject.toml 이다 — 이 표는 **대조용**이고,
#  값이 갈리면 아래 테스트가 빨개져서 사람이 결정한다(사본을 조용히 두지 않는다).
GATE_RULES = {"F811", "F821", "F822", "F823"}


def _ruff(args, cwd=None):
    return subprocess.run([str(RUFF), *args], capture_output=True, text=True,
                          cwd=str(cwd or REPO))


def _cfg() -> str:
    return (REPO / "pyproject.toml").read_text(encoding="utf-8")


def test_ruff가_설치돼_있다():
    assert RUFF.exists(), "ruff 가 없다 — 게이트가 조용히 통과한다"
    assert _ruff(["--version"]).returncode == 0


def test_게이트_규칙은_버그급만():
    """🔴 반대 위험 — 스타일을 넣으면 게이트가 꺼진다."""
    import re

    m = re.search(r'select\s*=\s*\[([^\]]*)\]', _cfg())
    assert m, "pyproject 에 [tool.ruff.lint] select 가 없다"
    got = set(re.findall(r'"([A-Z]+\d+)"', m.group(1)))
    assert got == GATE_RULES, f"게이트 규칙이 바뀌었다: {got}"


def test_F401은_게이트가_아니다():
    """착수 시점 97건이다. 게이트에 넣으면 그날 커밋이 전부 막힌다."""
    assert "F401" not in _cfg().split("[tool.ruff.lint]")[1].split("select")[1][:80]


@pytest.mark.parametrize("src,rule", [
    ('def f():\n    return 1\n\n\ndef f():\n    return 2\n', "F811"),
    ('def g():\n    return 없는이름\n', "F821"),
])
def test_버그급_위반을_잡는다(src, rule):
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "x.py"
        f.write_text(src, encoding="utf-8")
        r = _ruff(["check", "--select", rule, str(f)])
        assert r.returncode == 1 and rule in (r.stdout + r.stderr)


def test_현재_코드는_게이트_규칙을_통과한다():
    """게이트를 켜놓고 저장소가 빨간 상태면 아무도 커밋을 못 한다."""
    r = _ruff(["check", "app", "tools", "tests"])
    assert r.returncode == 0, r.stdout[:2000]


def test_훅에_규칙이름을_적지_않았다():
    """🔴 사본 금지 — 규칙은 pyproject 하나가 원본이다."""
    src = HOOK.read_text(encoding="utf-8")
    assert "ruff" in src, "훅에 린트 단계가 없다"
    body = src.split("LINT-1")[1]
    for rule in GATE_RULES:
        assert f'"{rule}"' not in body and f"'{rule}'" not in body, \
            f"훅이 규칙 {rule} 을 손으로 적고 있다"


def test_ruff가_없으면_막지_않는다():
    """🔴 반대 위험 — 없는 도구로 커밋을 막으면 저장소가 통째로 잠긴다."""
    src = HOOK.read_text(encoding="utf-8")
    assert '[ -x "$REPO/.venv/bin/ruff" ]' in src


def test_린트_가지가_스위트_뒤에_온다():
    """순서 계약 — 마커 검사가 먼저다. 뒤집으면 스위트를 안 돌려도 통과한다."""
    src = HOOK.read_text(encoding="utf-8")
    assert src.index("GREEN") < src.index("commit-lint")


def test_crawler는_제외다():
    """Go 모듈이다 — 파이썬 린터가 볼 것이 없다."""
    assert '"crawler"' in _cfg().split("[tool.ruff]")[1][:400]


def test_이미_있던_F821은_숨기지_않고_표시한다():
    """🔴 per-file-ignores 는 '없애기'가 아니라 '등록해 두기'다."""
    cfg = _cfg()
    assert "[tool.ruff.lint.per-file-ignores]" in cfg
    blk = cfg.split("[tool.ruff.lint.per-file-ignores]")[1]
    assert "app/research/deep.py" in blk and "LINT-1-b" in cfg
    # 그 파일들은 실제로 아직 위반이 있어야 한다 — 고쳤으면 무시도 지워야 한다
    r = _ruff(["check", "--select", "F821", "--ignore-noqa",
               "--no-respect-gitignore", "app/research/deep.py",
               "--isolated"])
    assert "F821" in (r.stdout + r.stderr), \
        "deep.py 가 고쳐졌다 — per-file-ignores 에서 지워라"


def test_shutil로_ruff를_찾을_수_있다():
    """CI·다른 셸에서도 같은 바이너리를 본다."""
    assert shutil.which("ruff", path=str(REPO / ".venv/bin")) is not None
