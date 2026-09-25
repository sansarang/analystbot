"""[CC-3·4·5 2026-09-25] 명령·에이전트·MCP 설정이 **있고, 규율을 적고 있다.**

지시문 `cc_collab_0925`. 파일이 있는지만 보면 빈 껍데기도 통과한다 — 그래서
각 파일이 **자기 규율을 실제로 적고 있는지**까지 본다.

🔴 토큰·DB URL 이 파일에 적히면 FAIL. 이것이 이 파일에서 가장 중요한 계약이다.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CMD = ROOT / ".claude" / "commands"
AGENT = ROOT / ".claude" / "agents"
MCP = ROOT / ".mcp.json"

COMMANDS = ("fable-run", "fable-export", "fable-trace", "fable-status")
AGENTS = ("contract-reviewer", "export-builder")


@pytest.mark.parametrize("name", COMMANDS)
def test_명령이_있다(name):
    p = CMD / f"{name}.md"
    assert p.is_file(), f"/{name} 이 없다"
    text = p.read_text(encoding="utf-8")
    assert text.startswith("---"), f"{name}: frontmatter 가 없다"
    assert "description:" in text.split("---")[1], f"{name}: description 이 없다"


@pytest.mark.parametrize("name", AGENTS)
def test_에이전트가_있다(name):
    p = AGENT / f"{name}.md"
    assert p.is_file(), f"{name} 에이전트가 없다"
    fm = p.read_text(encoding="utf-8").split("---")[1]
    assert f"name: {name}" in fm, f"{name}: frontmatter 이름이 다르다"
    assert "tools:" in fm, f"{name}: 도구 목록이 없다"


def test_fable_run_이_갈림길_규율을_적었다():
    """🔴 이 문구가 빠지면 명령이 갈림길에서 스스로 고르게 된다."""
    text = (CMD / "fable-run.md").read_text(encoding="utf-8")
    for must in ("questions/", "완료 조건 원문", "contract-reviewer", "우회하지 않는다"):
        assert must in text, f"fable-run: `{must}` 가 없다"


def test_export_가_판정을_금지했다():
    for p in (CMD / "fable-export.md", AGENT / "export-builder.md"):
        text = p.read_text(encoding="utf-8")
        assert "판정" in text and "금지" in text, f"{p.name}: 판정 금지가 없다"
        assert "null" in text, f"{p.name}: 못 구한 칸 규약이 없다"


def test_reviewer_가_구현을_금지했다():
    text = (AGENT / "contract-reviewer.md").read_text(encoding="utf-8")
    assert "구현하지 않는다" in text
    assert "FAIL" in text and "PASS" in text
    # 점검 여섯 항목이 다 있는가
    for must in ("n02_market", "리터럴", "stop", "거짓 통과",
                 "decision_ledger", "robots"):
        assert must in text, f"contract-reviewer: 점검 `{must}` 가 없다"


# ── CC-5 MCP ───────────────────────────────────────────────────────

def test_mcp_설정이_있다():
    assert MCP.is_file(), ".mcp.json 이 없다"
    cfg = json.loads(MCP.read_text(encoding="utf-8"))
    servers = cfg.get("mcpServers") or {}
    assert "github" in servers and "postgres_ro" in servers, list(servers)


def test_mcp_에_비밀이_적혀_있지_않다():
    """🔴 [CC-5] 토큰·DB URL 은 **환경변수로만**. 값이 파일에 있으면 FAIL."""
    raw = MCP.read_text(encoding="utf-8")
    # 환경변수 치환(`${...}`)만 허용한다
    for pat, why in (
        (r"ghp_[A-Za-z0-9]{10,}", "GitHub 토큰"),
        (r"github_pat_[A-Za-z0-9_]{10,}", "GitHub 토큰"),
        (r"postgres(?:ql)?://[^$\s\"]*:[^@\s\"]+@", "자격증명이 든 DB URL"),
    ):
        assert not re.search(pat, raw), f".mcp.json 에 {why} 가 적혀 있다"
    assert "${GITHUB_TOKEN}" in raw or "${GITHUB_PERSONAL_ACCESS_TOKEN}" in raw
    assert "${DATABASE_URL_READONLY}" in raw


def test_mcp_에_쓰기_DB를_붙이지_않았다():
    """🔴 [CC-5] 쓰기 권한 DB 를 MCP 에 붙이지 않는다."""
    raw = MCP.read_text(encoding="utf-8")
    assert "DATABASE_URL}" not in raw, "운영(쓰기) DATABASE_URL 을 붙였다"
    assert "postgres_rw" not in raw


def test_드라이브_MCP를_붙이지_않았다():
    """🔴 [CC-5] 구글 드라이브는 Claude Code 에 붙이지 않는다(심볼릭 링크로 푼다)."""
    raw = MCP.read_text(encoding="utf-8").lower()
    for banned in ("gdrive", "google-drive", "googledrive", "drive.google"):
        assert banned not in raw, f".mcp.json 에 드라이브가 붙었다: {banned}"
