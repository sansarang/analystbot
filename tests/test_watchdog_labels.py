"""WD-1 — 워치독 **코드 목록이 네 곳에 있었고 넷이 전부 달랐다.**

🔴 실측 2026-09-08: 코드에서 실제 발생 16종 · `alerts.WATCHDOG_CODES` 14종 ·
   `watchdog.py` 독스트링 9종 · CLAUDE.md 9종.
   라벨이 없는 `W-SOURCE-DRIFT`(파서가 조용히 0을 반환 — 소스 구조 변경)와
   `W-LLM-PAID`(유료 판정이 캡에 닿았다 — 비용 경보)는 텔레그램에
   **`🚨 W-SOURCE-DRIFT · 점검 필요`** 로 나갔다. 둘 다 중요한 경보다.

아이러니: `watchdog.py` 자신이 "사본을 두지 않는다"를 세 번 못박는다. 숫자는
전부 원본을 참조하는데 **코드 목록만 손으로 적혀 있었다.**

원본은 `alerts.WATCHDOG_CODES` 하나다. 이 테스트가 그것을 강제한다.
"""
import re
from pathlib import Path

from app.alerts import WATCHDOG_CODES

REPO = Path(__file__).resolve().parents[1]
CODE_RE = re.compile(r'"(W-[A-Z][A-Z-]+)"')


def _emitted() -> set[str]:
    """`app/` 에서 실제로 발생시키는 코드 — 라벨 사전 자신은 뺀다."""
    found: set[str] = set()
    for path in (REPO / "app").rglob("*.py"):
        if path.name == "alerts.py":
            continue
        found |= set(CODE_RE.findall(path.read_text(encoding="utf-8")))
    return found


def test_발생하는_모든_코드에_라벨이_있다():
    missing = sorted(_emitted() - set(WATCHDOG_CODES))
    assert not missing, (
        f"라벨 없는 코드 — 텔레그램에 '점검 필요'로 나간다: {missing}")


def test_아무도_안_쓰는_라벨이_없다():
    """반대 방향 — 죽은 라벨은 목록을 못 믿게 만든다."""
    stale = sorted(set(WATCHDOG_CODES) - _emitted())
    assert not stale, f"발생하지 않는 코드의 라벨: {stale}"


def test_손으로_적은_목록이_남아_있지_않다():
    """사본 금지 — 목록은 `WATCHDOG_CODES` 하나여야 한다.

    ⚠️ `watchdog.py` 본문에는 코드가 **당연히** 있다(거기서 발생시킨다).
       사본이 되는 자리는 **모듈 독스트링**이다 — 거기 적힌 목록은 원본이
       바뀌어도 따라가지 않는다. 그래서 독스트링만 본다.
       (이 구분을 처음에 못 해서 ④ 재현 불가가 한 번 실패했다.)
    """
    import ast

    doc = ast.get_docstring(ast.parse(
        (REPO / "app" / "watchdog.py").read_text(encoding="utf-8"))) or ""
    codes = set(re.findall(r"W-[A-Z][A-Z-]+", doc))
    assert len(codes) <= 1, (
        f"watchdog.py 독스트링이 코드 목록을 손으로 적고 있다({sorted(codes)}) — "
        "원본(alerts.WATCHDOG_CODES)을 가리켜라")

    md = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    md_codes = set(re.findall(r"W-[A-Z][A-Z-]+", md))
    assert len(md_codes) <= 1, (
        f"CLAUDE.md 가 코드 목록을 손으로 적고 있다({sorted(md_codes)})")
