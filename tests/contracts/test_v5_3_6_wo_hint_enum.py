"""🔴🔴 **`direction_hint` 목록을 모델에게 말한다** — 실측 2026-10-05.

══════════════════════════════════════════════════════════════════
🔴 열 줄이 **전부** 버려졌다
══════════════════════════════════════════════════════════════════

```
[agent] 턴 14 · done({'variables': [ … ]}) → ok 끝낸다
[agent] 🔴 `done` 인자 칸=[…] · 변수 **10줄**
                               ↓
parse_args → 후보 **0개** · ⚠️ 꼴이 틀린 것 1개:
  "v1: 🔴 모르는 `direction_hint` 다: 'positive for Portugal attacking
   fluidity' — §3-6 이 이름 댄 것은 ['home','away','both','goals_up',
   'goals_down','opp_goals_up','opp_goals_down', …]"
```

🔴 모델이 그 칸에 **자유 문장**을 썼다. ⚠️ 그럴 수밖에 없었다 — **프롬프트도
   스키마도 그 목록을 한 번도 말하지 않았다**(실측: 둘 다 `goals_up` 없음).

🔴 §1-1 의 `12→0`, 카탈로그의 `겹침 0개` 와 **같은 꼴**이다: 코드가 **아는
   것을 모델에게 안 알려 주고** 그 답을 버린다.
"""
from __future__ import annotations

import json


def _hints() -> tuple[str, ...]:
    """🔴 허용 목록은 **한 곳**이다(사본 금지)."""
    from app.agentschema import DIRECTION_HINTS
    return tuple(DIRECTION_HINTS)


def test_hint_목록이_한_곳에_있다():
    """🔴 `_vars_from` 이 쓰는 목록과 **같은 것**이어야 한다."""
    got = _hints()
    assert len(got) >= 7, got
    for want in ("home", "away", "both", "goals_up", "goals_down"):
        assert want in got, (want, got)


def test_hint_목록이_프롬프트에_있다():
    """🔴🔴 **모델이 그 글자를 알아야** 쓴다 — 안 말하면 자유 문장을 쓴다."""
    from app import agentloop
    said = agentloop.system_prompt()
    missing = [h for h in _hints() if h not in said]
    assert not missing, (
        f"🔴 `direction_hint` 허용값 {missing} 을 프롬프트가 **안 말한다** — "
        f"모델이 자유 문장을 쓰고 그 변수는 **전부 버려진다**(실측 10줄 → 0개)")


def test_hint_목록이_스키마에_enum_으로_있다():
    """🔴 프롬프트만으로는 모자라다 — **스키마가 강제**해야 한다(§3-6).

    ⚠️ `done` 의 파라미터가 스키마다 — 그 안에 `enum` 이 있으면 모델이 그
       글자만 쓴다.
    """
    from app import agentloop
    d = json.dumps(agentloop.output_schema(), ensure_ascii=False)
    for h in _hints():
        assert f'"{h}"' in d, (
            f"🔴 스키마가 `{h}` 를 **enum 으로 안 든다** — 모델을 막을 수가 없다")


def test_hint_목록을_코드에_두_번_적지_않는다():
    """🔴 사본 금지 — `agentschema` 하나가 원본이다."""
    import inspect

    from app import agentloop
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(agentloop))
    # ⚠️ 목록을 **글자로 늘어놓은 자리**가 없어야 한다
    assert '"goals_up", "goals_down"' not in body, (
        "🔴 허용 목록을 `agentloop` 에 **베꼈다** — `agentschema` 를 읽어라")


def test_hint_모르는_값이_오면_사유가_남는다():
    """🔴 그래도 **막는 것은 유지**한다 — 조용히 고치지 않는다(#3).

    ⚠️ 모델이 그래도 틀린 값을 내면 **버리고 사유를 적는다** — 추측으로
       `home` 으로 바꾸면 그 방향이 거짓이 된다(§5-4 가 코드로 정하는 까닭).
    """
    import datetime as dt

    from app import agentloop
    UTC = dt.timezone.utc
    inp = agentloop.AgentInput(
        match_key="f:1", home="team:1", away="team:2",
        home_names=("A",), away_names=("B",), competition="C",
        sport="soccer", kickoff_utc=dt.datetime(2026, 10, 4, tzinfo=UTC),
        venue="V", langs=("en",))
    box = {"variables": [{"id": "v1", "type": "absence", "team": "team:1",
                          "direction_hint": "아무 말", "claim": "x",
                          "quote": "y"}]}
    got, why = agentloop.parse_args(box, inp=inp)
    assert got == [], got
    assert "direction_hint" in why, why
