"""배선 계약 — **질문 한 줄 → 카드 한 장** (사용자 지시 2026-10-02 *"배선해라"*).

🔴 이 파일이 검사하는 것은 **이어졌는가**다. 블록 하나하나의 규칙은 각 블록의 계약이
   본다(`test_classify`·`test_scenarios`·`test_survive`·`test_triggers`).
"""
from __future__ import annotations

import ast
import importlib.util
import inspect
import re
from pathlib import Path

import pytest

from app import scenarios, survive
from app.bot import main as B
from app.types import Market

ROOT = Path(__file__).resolve().parents[2]




def _board(game):
    return [Market(market_type="total", team="over", line=2.5),
            Market(market_type="total", team="under", line=2.5),
            Market(market_type="handicap", team=game.home, line=-0.5),
            Market(market_type="home"), Market(market_type="draw"),
            Market(market_type="away")]


# ══════════════════════════════════════════════════════════════════
# 사슬이 끝까지 돈다
# ══════════════════════════════════════════════════════════════════










def test_세포_없는_유형_목록이_코드와_같다():
    """🔴 **배선이 찾은 결함이다.** yaml 의 `implemented` 가 전부 `false` 로 낡아
    있어서 `rules.unimplemented_types()` 가 **열네 개를 다 미구현으로** 냈다.

    그 목록이 카드 블록 1 에 그대로 올라가면 *"recent_pattern 은 세포가 없다"* 는
    **거짓**을 적는다. 🔴 코드가 원본이고 yaml 은 선언이다 — 둘을 대조한다.
    """
    from app import classify, rules
    assert rules.unimplemented_types() == sorted(classify.NOT_CLASSIFIED)
    # 🔴 구현한 것이 미구현 목록에 섞여 있지 않나
    assert not (set(classify.DIRECTION_OF) & set(rules.unimplemented_types()))






# ══════════════════════════════════════════════════════════════════
# DB 적재 — 🔴 표와 코드가 **같은 어휘**를 쓰나
# ══════════════════════════════════════════════════════════════════


def _columns(table: str) -> set[str]:
    """`db/schema.sql` 에서 그 표의 칸 이름. 🔴 **스키마가 원본이다**."""
    sql = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    m = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);",
                  sql, re.S)
    assert m, table
    out = set()
    # 🔴 **마이그레이션으로 더한 칸도 센다** — `ALTER TABLE … ADD COLUMN`.
    #    ⚠️ CREATE 블록만 보면 `dateless_reason`(#7 마이그레이션)을 놓친다.
    for m2 in re.finditer(
            rf"ALTER TABLE {table} ADD COLUMN(?: IF NOT EXISTS)? (\w+)", sql):
        out.add(m2.group(1))
    for ln in m.group(1).splitlines():
        ln = ln.strip()
        if not ln or ln.startswith(("--", "CONSTRAINT", "UNIQUE", "PRIMARY",
                                    "FOREIGN", "CHECK")):
            continue
        out.add(ln.split()[0])
    return out










# ══════════════════════════════════════════════════════════════════
# 봇까지 이어졌나
# ══════════════════════════════════════════════════════════════════


















def test_미배선_목록은_선언_창_셋뿐이다():
    """🔴🔴 **두 지시를 함께 지킨다** — 2026-10-02 · 2026-10-06 ⑧.

    > 배선 안 된 거도 마무리 지어라 … **사유만 남기고 나중에 하지 않으면 안 하는
    > 이보다 못하다** (2026-10-02)

    > 삭제: 스케줄러·채점·슬레이트 코드 삭제 → `analyze.py` 삭제 … (2026-10-06 ⑧)

    🔴 ⑧ 에서 고아를 **적는 대신 지웠다**(공개 함수 40여 개). ⚠️ 남을 수 있는 것은
       **계약이 읽는 선언 창**뿐이고, 그 수가 **늘면 빨개진다** — 그래야 목록이
       다시 자라지 않는다(2026-10-02 가 막으려던 것).
    """
    import re as _re

    src = (ROOT / "tests" / "test_wiring.py").read_text(encoding="utf-8")
    m = _re.search(r"NOT_WIRED: set\[str\] = \{(.*?)\}", src, _re.S)
    assert m, "🔴 `NOT_WIRED` 선언을 못 찾았다(배선 계약이 사라졌나)"
    names = _re.findall(r'"([^"]+)"', m.group(1))
    #: 🔴 2026-10-06 실측 — ⚠️ 줄이면 내려 적는다(늘리려면 까닭을 먼저 적는다)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **다섯이 늘었다 — 까닭을 먼저 적는다** (사용자 지시 2026-10-18)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > llm 은 **서치용**으로 사용한다 .. **llm 전략분석만 지워라** ..
    #  > **자료는 놔둬라** · **능력치 갈래모듈, 직전5경기 등은 변수에
    #  > 사용될거다**
    #
    #  🔴 ⑤-b2(LLM 전략분석)를 지우자 그것이 부르던 **재료 함수 넷**과 **갈래
    #     판정**이 부르는 곳을 잃었다. 🔴 사용자가 *"지우지 마라 · 변수에
    #     사용될거다"* 라고 못 박았으므로 **지울 수 없다** — 그래서 적는다.
    #  ⚠️ 다음 순서는 **코드가 그 재료로 변수를 만드는 것**이고, 이으면 이
    #     다섯을 `NOT_WIRED` 에서 빼고 여기서도 지운다(목록이 거짓이 되지 않게).
    ALLOW = {"app.rules.added_types", "app.rules.unimplemented_types",
             "app.window.set_clock",
             "app.core.strategy_llm.recent_of",
             "app.core.strategy_llm.news_of",
             "app.core.strategy_llm.rest_of",
             "app.core.strategy_llm.past_of",
             "app.core.branchjudge.run"}
    assert set(names) <= ALLOW, (
        f"🔴 미배선 목록이 **자랐다**: {sorted(set(names) - ALLOW)} — 적는 대신 "
        f"**잇거나 지워라**(지시 2026-10-02)")




