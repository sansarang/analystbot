"""🔴🔴 **거짓 1.0 계약** — 사용자 수정 ⑤ (2026-10-04).

> 변수가 **5개 미만**인 경기에서 어떤 마켓이든 **생존 1.0** 이 나오면 카드를 내지
> 말고 *"시나리오 세트 불완전"* 으로 실패. 그리고 양 팀 폼 변수에 *"연속 득점"* 이
> 있으면 **대량득점·난타전 시나리오가 없을 때** 실패 — 이건 **R3 계약이 안 물리고
> 있다**는 뜻이니 **돌연변이로 확인**.

══════════════════════════════════════════════════════════════════
🔴 왜 — 실측 2026-10-04 (북마케도니아 vs 스코틀랜드)
══════════════════════════════════════════════════════════════════

변수 **3개**(h2h 1 · 폼 2). 시나리오 A~E 의 스코어가 전부 **3골 이하**였다:

    A 2-1·1-0   B 0-1·1-2   C 0-0·1-1   D 2-0   E 0-2

→ `오버 3.5` 생존 **0.0** · `언더 3.5` 생존 **1.0 (small)** · 결론이 그것 하나.

🔴 그 1.0 은 *"죽는 시나리오가 0건"* 이 아니라 **4골 이상을 아무도 안 그렸다**는
   뜻이다. 사용자 진단: *"크로아티아 카드 때와 **같은 거짓 1.0** 이다."*

⚠️ 이 계약은 **생존 수를 고치지 않는다** — 거두는 것은 **등급**(`verdict`)이다.
   사람이 그 수를 봐야 왜 막혔는지 안다.
"""
from __future__ import annotations

import ast
import pathlib

from app import classify, survive
from app.scenarios import Draft
from app.types import NAME_AT

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _game():
    return classify.Game(home="North Macedonia", away="Scotland",
                         sport="soccer", league="UEFA Nations League B Grp. 1",
                         home_id="team:000151", away_id="team:000266")


def _thin_drafts():
    """🔴 실측의 그 세트다 — **최대 3골.** 4골 이상이 한 줄도 없다."""
    return [Draft(id="A", scores=["2-1", "1-0"], strength=1.0,
                  template_id="soccer_home_normal", why="테스트"),
            Draft(id="B", scores=["0-1", "1-2"], strength=1.4,
                  template_id="soccer_away_normal", why="테스트"),
            Draft(id="C", scores=["0-0", "1-1"], strength=0.4,
                  template_id="soccer_lock", why="테스트"),
            Draft(id="D", scores=["2-0"], strength=0.3,
                  template_id="5c-5", why="테스트"),
            Draft(id="E", scores=["0-2"], strength=0.3,
                  template_id="5c-5", why="테스트")]


def _var(why: str = "", direction: str = "home"):
    return classify.Classified(
        text="테스트 변수", source_url="https://example.com/x",
        hardness="hard", type="recent_pattern", direction=direction, why=why)


# ══════════════════════════════════════════════════════════════════
# ① 변수 5개 미만 + 생존 1.0 → **등급을 거둔다**
# ══════════════════════════════════════════════════════════════════


# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_변수_셋에_생존_1점0이면_등급을_거둔다`

# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_변수_다섯이면_막지_않는다`

# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_변수를_안_주면_막지_않는다`

# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_연속_득점인데_난타전_시나리오가_없으면_거둔다`

# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_난타전이_그려져_있으면_막지_않는다`

def test_두_가드가_run_안에서_불린다():
    """🔴 함수만 있고 안 부르면 없는 코드보다 나쁘다(CLAUDE.md #2 배선)."""
    src = (ROOT / "app" / "survive.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    run = next(n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "run")
    called = {ast.unparse(n.func) for n in ast.walk(run)
              if isinstance(n, ast.Call)}
    for name in ("_thin_set_guard", "_scoring_streak_guard"):
        assert name in called, f"🔴 `{name}` 을 `run()` 이 부르지 않는다"
