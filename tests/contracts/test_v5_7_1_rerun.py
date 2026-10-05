"""🔴🔴 **v5 §7-1 — T-60 재실행.** 확정 XI 를 가져오고 §5~§6 을 다시 돈다.

지시문 §7-1 원문:

> 킥오프 **60분 전(야구는 70분 전)** 코드가 확정 XI 를 가져온다. 순서:
> **어댑터**(statsapi probable/lineup, fotmob HTML 경기 페이지) → **공식 사이트
> 직독** → **에이전트 search**(검색어에 starting XI / 스타멘 / 선발 라인업 +
> 날짜 강제). 가져오면 `lineup_state` 를 `confirmed` 로 올리고 §5~§6 을 재실행,
> **카드 1회 갱신**(R10). 못 가져오면 카드에 **XI 미확정 — 발표 전/미검증**을
> 적고 **상한 0.85 를 강제**한다. **낡은 XI 를 기준 XI 로 쓰면 계약 실패**
> (크로아티아 카드: 트래퍼드 선발).

══════════════════════════════════════════════════════════════════
🔴 왜 — 카드는 **킥오프 전에 한 번 더** 맞을 기회가 있다
══════════════════════════════════════════════════════════════════

⚠️ 확정 XI 는 보통 킥오프 1시간 전에 나온다. 그때까지의 카드는 **예상 XI** 로
   세운 것이고 상한 0.85 다(§6-5). 🔴 확정을 받으면 상한이 풀리고, 그 한 번의
   갱신이 **등급을 바꾼다.**

🔴 **§10-4 M35** — 낡은 XI 로 상한(10-04) — T-60 확정 XI 실패 시 상한 0.85 강제
   ⚠️ 이 계약이 그 줄을 집행한다(`tests/test_contract_coverage.py` 가 번호로 대조한다).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 10, 4, 9, 0, tzinfo=timezone.utc)


def test_v5_7_1_창이_종목마다_yaml_에_있다():
    """🔴 *"60분 전(야구는 70분 전)"* — 두 수를 코드에 박지 않는다."""
    from app import rerun
    assert rerun.window_min("soccer") == 60
    assert rerun.window_min("baseball") == 70
    # ⚠️ 모르는 종목은 **기본값**이고, 그 사실이 글자로 남는다
    assert rerun.window_min("hockey") in (60, 70)
    from app import rules
    cfg = rules.rerun_window()
    assert str(cfg.get("basis") or "").strip(), "🔴 근거가 없다(§5-6)"


@pytest.mark.parametrize(("sport", "mins", "due"), [
    ("soccer", 59, True),     # 창 안이다
    ("soccer", 61, False),    # 아직 멀다
    ("baseball", 69, True),   # 🔴 야구는 70분
    ("baseball", 71, False),
    ("soccer", 0, False),     # 🔴 이미 시작했다 — 재실행은 경기 전만
    ("soccer", -5, False),
])
def test_v5_7_1_때가_됐나(sport, mins, due):
    from app import rerun
    kick = NOW + timedelta(minutes=mins)
    assert rerun.due(kick, now=NOW, sport=sport) is due


def test_v5_7_1_순서가_지시문_그대로다():
    """🔴 *"어댑터 → 공식 사이트 직독 → 에이전트 search"* — 그 순서다.

    ⚠️ 순서가 뜻이다 — 어댑터가 1층(공식 API)이고 에이전트 검색이 가장 약하다
       (§4-3 도메인 등급). 🔴 뒤집으면 약한 자료가 확정 XI 로 선다.
    """
    from app import rerun
    assert rerun.ORDER == ("adapter", "official", "agent")


def test_v5_7_1_못_가져오면_상한_0_85_를_강제한다():
    """🔴🔴 *"못 가져오면 … **상한 0.85 를 강제**한다."*

    ⚠️ §6-5 의 `없음`(0.8)보다 **느슨하다** — 예상 XI 는 있고 확정만 못 받은
       상태다. 🔴 그 수를 코드에 박지 않는다(yaml).
    """
    from app import rerun
    got = rerun.without_xi()
    assert got.cap == 0.85
    assert got.state_word == "미확정"
    # 🔴 *"발표 전"* 과 *"미검증"* 을 **둘 다** 적는다(§6-5 와 같은 가름)
    assert "발표 전" in got.line() and "미검증" in got.line(), got.line()


def test_v5_7_1_낡은_XI_는_기준_XI_가_아니다_M35():
    """🔴🔴 *"낡은 XI 를 기준 XI 로 쓰면 **계약 실패**"*(크로아티아 카드).

    ⚠️ 실사고: 카드가 **트래퍼드 선발**을 적었다 — 그것은 **지난 경기**의 XI 였다.
    🔴 XI 에 적힌 경기 날짜가 **이 경기**가 아니면 받지 않는다.
    """
    from app import rerun
    kick = NOW + timedelta(minutes=30)
    fresh = {"players": ["A"] * 11, "match_date": kick.date().isoformat()}
    old = {"players": ["A"] * 11, "match_date": "2026-09-20"}
    assert rerun.fresh_xi(fresh, kickoff=kick)[0] is True
    ok, why = rerun.fresh_xi(old, kickoff=kick)
    assert ok is False
    assert "낡" in why and "2026-09-20" in why, why
    # 🔴 **날짜가 없으면 받지 않는다**(fail-closed) — 낡은지 알 수 없다
    ok2, why2 = rerun.fresh_xi({"players": ["A"]}, kickoff=kick)
    assert ok2 is False
    assert "모른다" in why2 or "없다" in why2, why2


def test_v5_7_1_확정을_받으면_상한이_풀린다_M24():
    """🔴 `lineup_state` 를 `confirmed` 로 올린다 → §6-5 의 `양쪽확정`."""
    from app import rerun
    got = rerun.with_xi(both=True, verified=True)
    assert got.state == "양쪽확정"
    assert got.cap is None          # 🔴 상한이 없는 것과 같다
    # ⚠️ 한쪽만 받으면 `한쪽확정` 이고 상한 0.9 다(§6-5)
    one = rerun.with_xi(both=False, verified=True)
    assert one.state == "한쪽확정" and one.cap == 0.9
    # 🔴 **미검증**이면 한 단계 아래다(§6-5)
    un = rerun.with_xi(both=True, verified=False)
    assert un.state.endswith("미검증") and un.cap == 0.9


def test_v5_7_1_카드는_한_번만_갱신한다_R10():
    """🔴 *"카드 **1회** 갱신(R10)"* — 두 번째는 거절한다.

    ⚠️ 두 번 갱신하면 *"예측을 언제 했나"* 가 흐려지고 채점이 거짓이 된다.
    """
    from app import rerun
    assert rerun.may_update(done_at=None)[0] is True
    ok, why = rerun.may_update(done_at=NOW)
    assert ok is False
    assert "1회" in why or "이미" in why, why


def test_v5_7_1_M2_가_여기서_물린다():
    """🔴🔴 *"재실행에서 시나리오 수가 줄면 실패"*(M2) — **그 자리가 여기다.**

    ⚠️ `trigcond.rerun_ok` 를 만들어 두고 부르는 곳이 없었다(`NOT_WIRED`).
       🔴 §7-1 이 그 호출자다.
    """
    import ast
    import inspect
    import textwrap

    from app import rerun
    src = textwrap.dedent(inspect.getsource(rerun))
    calls = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") == "rerun_ok"]
    assert calls, (
        "🔴 M2 를 `rerun` 이 **안 부른다** — 시나리오가 줄어도 아무 일이 "
        "안 일어난다(§7-2 M2)")
    # 🔴 실물로 — 줄면 실패다
    got = rerun.check_scenarios(before=4, after=3)
    assert got[0] is False and "M2" in got[1]


def test_v5_7_1_배선_스케줄러가_돈다():
    """🔴🔴 **안 이어진 재실행은 없는 재실행이다**(CLAUDE.md #2)."""
    import ast
    import inspect
    import textwrap

    from app import scheduler
    src = textwrap.dedent(inspect.getsource(scheduler.main))
    tree = ast.parse(src)
    # 🔴 `rerun_once(pool)` 은 **이름 호출**이다(`ast.Name`) — 속성이 아니다.
    #    ⚠️ 처음에 `ast.Attribute` 만 봤고 그래서 못 찾았다.
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and getattr(n.func, "id", "") == "rerun_once"]
    assert calls, (
        "🔴 §7-1 재실행이 스케줄러 주기에 **없다** — 확정 XI 를 영원히 안 받고 "
        "모든 카드가 상한 0.85 에 머문다")
    # 🔴 **주기로** 돌아야 한다 — 한 번 부르는 것으로는 창을 놓친다
    loops = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_loop"
             and n.args and getattr(n.args[0], "value", "") == "rerun"]
    assert loops, "🔴 `_loop(\"rerun\", …)` 이 없다 — 한 번만 돌면 창을 놓친다"
    # ⚠️ 간격이 **창보다 촘촘해야** 한다(안 그러면 창을 건너뛴다)
    from app import rerun, scheduler as sch
    assert sch.RERUN_INTERVAL_SEC <= rerun.window_min("soccer") * 60, (
        f"🔴 재실행 주기 {sch.RERUN_INTERVAL_SEC}초가 창 "
        f"{rerun.window_min('soccer')}분보다 넓다 — **창을 건너뛴다**")


def test_v5_7_1_표시_칸이_스키마에_있다():
    """🔴 *"1회 갱신"* 을 **어디에 적나** — 기억이 없으면 두 번 갱신한다."""
    import pathlib
    sql = pathlib.Path("db/schema.sql").read_text()
    assert "rerun_at" in sql, (
        "🔴 재실행 표시 칸이 스키마에 없다 — 프로세스가 죽으면 *'이미 갱신했다'* "
        "를 잊고 카드를 또 바꾼다(R10 위반)")
