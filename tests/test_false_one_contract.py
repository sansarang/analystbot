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


def test_변수_셋에_생존_1점0이면_등급을_거둔다():
    """🔴 실측의 그 자리다 — `언더 3.5` 가 1.0(small) 로 발표됐다."""
    res = survive.run(_thin_drafts(), _game(), variables=[_var() for _ in range(3)])
    ones = [m for m in res.markets if float(m.survival or 0) >= NAME_AT]
    assert ones, "이 세트는 1.0 마켓을 낸다 — 대역이 틀렸다"
    # 🔴 생존 수는 **그대로** 보여 준다
    assert any(float(m.survival) >= NAME_AT for m in ones)
    # 🔴 등급은 **전부 거뒀다**
    assert all(m.verdict == "none" for m in ones), [
        (m.market_type, m.survival, m.verdict) for m in ones]
    assert any("시나리오 세트 불완전" in n for n in res.notes), res.notes


def test_변수_다섯이면_막지_않는다():
    """⚠️ 문턱을 넘으면 **그대로 발표한다** — 가드가 늘 거두면 봇이 벙어리가 된다."""
    res = survive.run(_thin_drafts(), _game(), variables=[_var() for _ in range(5)])
    ones = [m for m in res.markets if float(m.survival or 0) >= NAME_AT]
    assert ones
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **이 세트의 1.0 은 총점 줄뿐이다** — 지시 2026-10-09 ② 로 보류다
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 그래서 *"등급이 하나는 살아남는다"* 로는 더 못 검사한다. 🔴 이 계약이
    #     지키려던 것은 **얇은 세트 가드가 문턱을 넘으면 안 돈다**는 것이므로
    #     그 말을 **직접** 검사한다(가드 글이 없어야 한다).
    assert not any("시나리오 세트 불완전" in n for n in res.notes), res.notes
    # 🔴 거둔 사유가 **총점 보류**임을 못 박는다 — 다른 가드가 몰래 거두면 빨개진다
    held = [m for m in ones if m.verdict == "none"]
    if held:
        assert all(m.market_type == "total" for m in held), [
            (m.market_type, m.survival) for m in held]
        assert any("총점 줄 등급 보류" in n for n in res.notes), res.notes


def test_변수를_안_주면_막지_않는다():
    """🔴 **모르는 것과 0 은 다르다** — 안 넘겨 주면 가드가 안 돈다."""
    res = survive.run(_thin_drafts(), _game())
    assert not any("시나리오 세트 불완전" in n for n in res.notes), res.notes


# ══════════════════════════════════════════════════════════════════
# ② 연속 득점 + 난타전 없음 → **등급을 거둔다**
# ══════════════════════════════════════════════════════════════════


def test_연속_득점인데_난타전_시나리오가_없으면_거둔다():
    """🔴 *"R3 계약이 안 물리고 있다"* 를 기계가 말하게 한다."""
    whys = [_var(why="§4 recent_pattern '패턴 방향' — Paraguay 최근 5경기 "
                      "3승 1패 · 원정 연속 득점 8경기")
            for _ in range(6)]        # 🔴 5개 **이상** — ①이 아니라 ②가 잡아야 한다
    res = survive.run(_thin_drafts(), _game(), variables=whys)
    ones = [m for m in res.markets if float(m.survival or 0) >= NAME_AT]
    assert ones
    assert all(m.verdict == "none" for m in ones), [
        (m.market_type, m.survival, m.verdict) for m in ones]
    joined = " ".join(res.notes)
    assert "연속 득점" in joined and "난타전 없음" in joined, res.notes


def test_난타전이_그려져_있으면_막지_않는다():
    """⚠️ 4골 이상 시나리오가 **있으면** 그 1.0 은 거짓이 아니다.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **이 시험의 첫 판이 돌연변이를 통과시켰다**(2026-10-04)
    ══════════════════════════════════════════════════════════════════

    첫 판은 얇은 세트의 `A` 에 `3-2` 를 **얹었다.** 그러자 `언더 3.5` 가 죽어
    **1.0 마켓이 하나도 안 남았고**, 가드는 `if not ones: return` 에서 돌아갔다.
    🔴 그래서 `if big >= 4: return`(난타전 확인)을 **지워도 초록이었다** — 시험이
       닿지도 않는 줄을 지킨 셈이다. 이 저장소에서 같은 병이 **네 번째**다.

    🔴 그래서 지금은 **1.0 이 남는 세트**로 짠다: 전부 4골 이상이라 `오버 3.5` 가
       1.0 이고, 동시에 난타전(5골)이 **그려져 있다.** 그 1.0 은 거짓이 아니다.
    ⚠️ `ones` 가 비지 않는 것을 **먼저 단언한다** — 비면 이 시험은 아무것도 안 본다.
    """
    drafts = [Draft(id="A", scores=["3-2"], strength=1.0,
                    template_id="soccer_home_blowout", why="난타전"),
              Draft(id="B", scores=["2-3"], strength=1.0,
                    template_id="soccer_away_blowout", why="난타전"),
              Draft(id="C", scores=["2-2"], strength=0.4,
                    template_id="soccer_lock", why="테스트"),
              Draft(id="D", scores=["4-0"], strength=0.3,
                    template_id="5c-5", why="테스트"),
              Draft(id="E", scores=["0-4"], strength=0.3,
                    template_id="5c-5", why="테스트")]
    whys = [_var(why="원정 연속 득점 8경기") for _ in range(6)]
    res = survive.run(drafts, _game(), variables=whys)
    ones = [m for m in res.markets if float(m.survival or 0) >= NAME_AT]
    # 🔴 **가드가 난타전 검사까지 닿는다**는 것을 먼저 확인한다
    assert ones, ("🔴 이 세트는 1.0 마켓을 내야 한다 — 안 내면 가드가 "
                  "`if not ones` 에서 돌아가고 이 시험은 아무것도 안 본다")
    joined = " ".join(res.notes)
    assert "난타전 없음" not in joined, res.notes
    # ══════════════════════════════════════════════════════════════════
    # 🔴 **등급은 `_pick_one` 이 정한다 — 이 가드가 아니다**(2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 첫 판은 *"1.0 짜리 줄에 등급이 남아 있다"* 를 봤다. 그런데 ②(무게 =
    #     변수 합) 뒤로는 등급이 서는 줄이 여럿이고, §6 `_pick_one` 이 선언
    #     순서(`win → btts → total → handicap`)대로 **하나만** 남긴다 — 실측에서
    #     `btts 예`(0.8)가 `오버 2.5·3.5`(1.0)를 이겼다.
    #  🔴 그것은 이 가드가 한 일이 **아니다.** 이 시험이 지킬 것은 *"가드가 안
    #     걸렸다"* 하나고, 그것은 위 사유 검사가 본다. ⚠️ 등급까지 묶어 보면
    #     `_pick_one` 의 선언을 바꾸는 것만으로 이 시험이 빨개진다(거짓 경고).
    #  🔴 대신 **세트가 통째로 거둬지지는 않았다**를 본다 — 그것이 가드의 반대다.
    assert any(str(m.verdict) != "none" for m in res.markets), [
        (m.market_type, m.survival, m.verdict) for m in res.markets]


# ══════════════════════════════════════════════════════════════════
# 🔴 구조 계약 — 가드가 **배선돼 있나**
# ══════════════════════════════════════════════════════════════════




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
