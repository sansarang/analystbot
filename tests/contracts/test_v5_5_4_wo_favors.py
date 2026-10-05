"""🔴🔴 **subject 와 favors 를 가른다** — 사용자 지시 2026-10-05 (카드 불합격).

> **1. 변수 칸 분리**: `subject`(누구에 **관한** 사실, team 열쇠)와
> `favors`(누구에게 **유리**, home/away/both/goals_up/goals_down)를 **별도 칸**
> 으로. `favors` 는 **코드가 catalog 방향 규칙으로 계산**한다:
>   - `absence`: favors = **상대** (def면 상대 득점↑, att면 자팀 득점↓)
>   - `stakes`: 이미 확정·탈락 확정 팀 → favors = **상대**(동기 비대칭).
>     결과가 필요한 팀 쪽이 근거.
>   - `coach_conflict`·`event_match`·`squad_rotation`: **both**
>   - 그 외 유형도 catalog 에 favors 규칙을 전부 적고, **규칙 없는 유형은 both**
>
> 계약: **"자팀 결장이 자팀 근거로 들어가면 실패"**, **"확정 팀의 stakes 가 그
> 팀 근거면 실패"**
>
> **5.** 양방향 복제는 **both 유형에만**. 같은 URL **두 매체 이상**이면
> hardness 올림(**R4 가 hard 여야 한다**).

══════════════════════════════════════════════════════════════════
🔴 왜 — 카드가 거꾸로 읽혔다(실측 2026-10-05 pn7)
══════════════════════════════════════════════════════════════════

```
R4 [absence·**home**]  호날두가 **포르투갈** 에서 이탈      → 포르투갈 **근거**
R8 [stakes·**home**]   포르투갈이 **8강 확정**              → 포르투갈 **근거**
```

⚠️ 둘 다 **거꾸로**다. 🔴 포르투갈의 주전 이탈은 포르투갈에 **불리**하고,
   8강을 이미 확정한 팀은 **동기가 낮다**(결과가 필요한 쪽은 노르웨이다).
🔴 까닭: `direction_hint` 는 *"누구에 관한 사실인가"* 를 말했고 코드가 그것을
   **방향으로** 읽었다 — **두 질문을 한 칸에** 담았다.
"""
from __future__ import annotations

import datetime as dt

import pytest

UTC = dt.timezone.utc
HOME, AWAY = "team:000191", "team:000174"       # Portugal · Norway


def _game():
    from app import classify
    return classify.Game(home="Portugal", away="Norway", sport="soccer",
                         league="UEFA Nations League",
                         home_id=HOME, away_id=AWAY)


def _var(**kw):
    from app.agentschema import AgentVar
    base = {"id": "v1", "type": "absence", "team": HOME,
            "claim": "호날두가 이탈했다", "quote": "Ronaldo left the squad",
            "url": "https://a/1",
            "published_at": dt.datetime(2026, 10, 4, 6, tzinfo=UTC),
            "direction_hint": "home", "lang": "en"}
    base.update(kw)
    return AgentVar(**base)


# ══════════════════════════════════════════════════════════════════
# ① 칸이 **둘**이다
# ══════════════════════════════════════════════════════════════════

def test_favors_칸이_둘로_갈렸다():
    """🔴 `subject`(누구에 관한)와 `favors`(누구에게 유리)는 **다른 질문**이다."""
    import dataclasses

    from app.agentschema import AgentVar
    names = {f.name for f in dataclasses.fields(AgentVar)}
    assert "subject" in names, (
        "🔴 `subject` 칸이 없다 — *누구에 관한 사실인가* 를 담을 자리")
    from app import classify
    c = classify.from_agent_var(_var(), _game())
    assert hasattr(c, "favors"), (
        "🔴 `Classified.favors` 가 없다 — *누구에게 유리한가* 를 담을 자리")


def test_favors_규칙이_설정에_있다():
    """🔴 *"catalog 에 favors 규칙을 **전부** 적고"* — 코드에 박지 않는다."""
    from app import rules
    box = rules.variable_types()
    missing = [t for t, v in box.items() if not (v or {}).get("favors")]
    assert not missing, (
        f"🔴 `favors` 규칙이 없는 유형 {len(missing)}종: {missing} — "
        f"지시 2026-10-05 은 **전부** 적으라고 했다")
    # 🔴 값은 정해진 것 중 하나다
    ok = {"opponent", "subject", "both", "goals_up", "goals_down", "none"}
    bad = {t: v["favors"] for t, v in box.items() if v["favors"] not in ok}
    assert not bad, f"🔴 모르는 `favors` 값: {bad} (허용 {sorted(ok)})"


# ══════════════════════════════════════════════════════════════════
# ② 사용자가 **이름을 댄 두 계약**
# ══════════════════════════════════════════════════════════════════

def test_favors_자팀_결장이_자팀_근거로_들어가면_실패():
    """🔴🔴 **지시서가 이름 댄 계약** — R4 가 그 자리였다."""
    from app import classify
    c = classify.from_agent_var(_var(type="absence", team=HOME), _game())
    assert c.direction != "home", (
        f"🔴 **포르투갈의 결장이 포르투갈 근거**로 들어갔다(direction="
        f"{c.direction!r}) — 주전 이탈은 그 팀에 **불리**하다")
    assert c.direction in ("away", "both"), c.direction
    # ✅ 반대쪽도 같다
    c2 = classify.from_agent_var(_var(type="absence", team=AWAY), _game())
    assert c2.direction != "away", c2.direction


def test_favors_확정_팀의_stakes_가_그_팀_근거면_실패():
    """🔴🔴 **지시서가 이름 댄 계약** — R8 이 그 자리였다.

    > `stakes`: 이미 확정·탈락 확정 팀 → favors = **상대**(동기 비대칭).
    > **결과가 필요한 팀 쪽이 근거.**
    """
    from app import classify
    c = classify.from_agent_var(
        _var(type="stakes", team=HOME,
             claim="Portugal secured first place in the quarter-finals",
             quote="Portugal has secured a spot in the quarterfinals"), _game())
    assert c.direction != "home", (
        f"🔴 **8강을 확정한 팀의 stakes 가 그 팀 근거**로 들어갔다"
        f"(direction={c.direction!r}) — 동기는 **결과가 필요한 쪽**이 높다")


def test_favors_아직_안_걸린_stakes_는_그_팀_쪽이다():
    """⚠️ 반대쪽도 본다 — **확정이 아니면** 걸린 팀 쪽이 근거다(종전 규칙)."""
    from app import classify
    c = classify.from_agent_var(
        _var(type="stakes", team=HOME,
             claim="Portugal must win to reach the quarter-finals",
             quote="Portugal need a win to qualify"), _game())
    assert c.direction == "home", c.direction


@pytest.mark.parametrize("kind", ["coach_conflict", "event_match",
                                  "squad_rotation"])
def test_favors_셋은_both_다(kind):
    """🔴 *"`coach_conflict`·`event_match`·`squad_rotation`: **both**"*."""
    from app import rules
    assert (rules.variable_types().get(kind) or {}).get("favors") == "both", \
        kind


def test_favors_규칙_없는_유형은_both():
    """🔴 *"규칙 없는 유형은 both"* — 조용히 한쪽으로 밀지 않는다."""
    from app import classify
    got = classify.favors_of("아예_없는_유형", subject=HOME, game=_game(),
                             text="")
    assert got == "both", got


# ══════════════════════════════════════════════════════════════════
# ⑤ 양방향 복제는 **both 유형에만** · 두 매체면 hardness 올림
# ══════════════════════════════════════════════════════════════════

def test_favors_양방향_복제는_both_유형에만():
    """🔴 실측 pn7: `squad_rotation`(both)은 둘로 나뉘었는데 **`absence` 도**
    나뉠 수 있었다 — 그러면 결장이 양쪽 근거가 된다."""
    from app import classify
    rows = classify.from_agent_vars([_var(type="absence", team=HOME)], _game())
    assert len(rows) == 1, (
        f"🔴 `absence` 가 **양방향으로 복제**됐다({len(rows)}개) — 결장은 한쪽에 "
        f"유리하다(both 가 아니다)")
    both = classify.from_agent_vars(
        [_var(id="v2", type="coach_conflict", team=HOME)], _game())
    assert len(both) == 2, (
        f"🔴 `coach_conflict`(both)가 **한 항목**이다({len(both)}개)")


def test_favors_두_매체면_hardness_가_오른다():
    """🔴 *"같은 URL 두 매체 이상이면 hardness 올림(**R4 가 hard 여야 한다**)"*.

    ⚠️ R4(호날두 이탈)는 **여러 매체**가 같은 말을 했다 — 그런데 `soft` 였다.
    🔴 두 매체가 같은 사실을 말하면 그것은 **단단한 사실**이다(§5-7 독립 출처).
    """
    from app import classify
    rows = classify.from_agent_vars([
        _var(id="v1", type="absence", team=HOME, url="https://a/1"),
        _var(id="v2", type="absence", team=HOME, url="https://b/2")], _game())
    hard = [r for r in rows if r.hardness == "hard"]
    assert hard, (
        f"🔴 **두 매체**가 같은 결장을 말했는데 전부 `soft` 다 — hardness 가 "
        f"올라야 한다: {[(r.type, r.hardness) for r in rows]}")
