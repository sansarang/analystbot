"""🔴🔴 **리그·컵 정보 분석** — 사용자 지시 2026-10-14.

> fotmob에 받아서 **llm이 그컵이나 리그정보 분석만** 해서 **변수에 넣는다** …
> 위의 테스트(웹 검색으로 순위 긷기)는 **오류를 많이 불러일으킨다**

## 🔴🔴 길이 바뀌었다 — 그 사실을 적어 둔다
```
❌ 접은 길   LLM 질의 → 웹 검색 → 순위표 페이지 → 추출
             실측 2026-10-14: 후보 91개 중 신원 46·날짜 40 탈락 · 열기 상한 3
             · 순위·일정은 **상시 페이지**라 7일 창에 늘 걸린다 → 문서 0건
✅ 쓰는 길   fotmob `group_table` 이 **구조화 자료**를 준다
             → LLM 은 그것을 **분석만** 한다(사실을 찾지 않는다)
             → 그 분석이 변수가 된다
```

## 🔴 LLM 이 하는 일과 **못 하는 일**
| 한다 | 못 한다 |
|---|---|
| 순위·승점·라운드·구역을 **읽고 뜻을 말한다** | 숫자를 **만든다** |
| 어느 팀이 더 급한가를 **판단한다** | 표에 없는 팀·수를 **들인다** |
| 한 줄로 **요약한다** | 확률·등급을 **건드린다** |

🔴 입력은 `group_table` 이 준 **그 표뿐**이다 — 모델 기억을 받지 않는다.
🔴 출력 칸은 **다섯**이고 전부 **표에서 확인되는 것**이다(계약 LR1 이 센다).
⚠️ 숫자는 **코드가 다시 센다** — 모델이 적은 수는 쓰지 않는다(계약 LR2).
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.core.schema import MatchRef
from app.core.state import RunState

logger = logging.getLogger(__name__)

#: 🔴 분석 한 줄 상한 — 길면 서술이 된다
SAY_MAX = 180

#: 🔴 모델이 고를 수 있는 **급함** — 열거로 잠근다(글자를 지어내지 못한다)
URGENCY: tuple[str, ...] = ("매우 급하다", "급하다", "보통", "여유", "모르겠다")


class LeagueRead(BaseModel):
    """🔴🔴 모델이 내는 것 — **판단 글자뿐**이다. 숫자 칸이 **없다**.

    ⚠️ 숫자 칸을 두면 모델이 표에 없는 수를 적는다 — 그 수가 변수의 근거가 되면
       검증할 수 없는 사실이 확률에 닿는다(§0 금지).
    """

    #: 🔴 어느 팀이 이 경기가 더 급한가 — 팀 이름(열거로 잠근다)
    urgent_team: str = Field(default="")
    #: 🔴 얼마나 급한가(열거)
    urgency: str = Field(default="모르겠다")
    #: 🔴 왜 그런가 — **표에서 확인되는 것만** 한 줄
    why: str = Field(default="")


def _table_of(facts) -> dict:
    """🔴 `facts.standings["group"]` — fotmob 이 준 그 표. 없으면 빈 표."""
    return dict(dict(getattr(facts, "standings", None) or {}).get("group") or {})


def _rows_for(box: dict, *, names: list[str]) -> dict:
    """🔴🔴 **그 두 팀 줄만** 골라 돌려준다. `{우리 이름: 그 줄}`.

    🔴 이름 맞추기는 `core/teamname.pick` 하나다(사본 금지) — `group_table` 이
       쓰는 그 함수다. ⚠️ 표의 이름은 `Feyenoord` 이고 우리 이름은
       `Feyenoord Rotterdam` 이다(실측 2026-10-14).
    """
    from app.core import teamname as _tn
    rows = [dict(x) for x in (dict(box or {}).get("rows") or [])]
    keys = [str(r.get("name") or "") for r in rows]
    out: dict[str, dict] = {}
    for one in [str(x) for x in (names or []) if str(x).strip()]:
        got, _why = _tn.pick(one, keys)
        if not got:
            continue
        for r in rows:
            if str(r.get("name") or "") == got:
                out[one] = r
                break
    return out


def _said_of(box: dict, mine: dict) -> str:
    """🔴🔴 **코드가 세는 글자** — 라운드·승점·순위·구역·남은 경기.

    🔴 이것이 카드에 적히는 **사실**이다(모델이 아니라 코드가 만든다 · 계약 LR2).
    ⚠️ 못 받은 칸은 ⬜ 로 남긴다(#3 조용한 0 금지).
    """
    if not mine:
        return "⬜ 두 팀 줄을 못 찾았다"
    rows = []
    n_left = dict(box or {}).get("remaining")
    for name, r in mine.items():
        played = r.get("played")
        rows.append(
            f"{name} — {r.get('rank') or '⬜'}위 · {played or '⬜'}경기 "
            f"**{r.get('points') if r.get('points') is not None else '⬜'}점**"
            f"({r.get('wins') or 0}승 {r.get('draws') or 0}무 "
            f"{r.get('losses') or 0}패) · 득실 {r.get('goals_for')}-"
            f"{r.get('goals_against')}"
            + (f" · 구역 {r.get('zone')}" if str(r.get("zone") or "") else ""))
    head = (f"`{dict(box or {}).get('group') or '⬜'}` · "
            + (f"남은 {n_left}경기" if n_left is not None else "남은 경기 ⬜"))
    return head + " · " + " / ".join(rows)


def ask(ref: MatchRef, facts, *, state: RunState) -> tuple[dict, str]:
    """🔴🔴 **LLM 이 그 표를 분석한다**. `({판단}, 사유)`.

    🔴 입력은 `group_table` 이 준 표**뿐**이다 — 검색도 기억도 안 쓴다.
    ⚠️ 표가 없으면 **안 묻는다**(없는 것을 분석하게 하지 않는다).
    ⚠️ 실패하면 **빈 표**다 — 코드가 센 글자(`said_of`)는 그대로 남는다.
    """
    from app.core import llm
    box = _table_of(facts)
    names = [str(getattr(ref, f"{s}_name", "") or "")
             or str(getattr(ref, s, "") or "") for s in ("home", "away")]
    mine = _rows_for(box, names=names)
    said = _said_of(box, mine)
    if not mine:
        state.note(f"s4c 리그 분석 — ⬜ 안 묻는다({said})")
        return {}, said
    msgs = [
        llm.Message(role="system", content=(
            "너는 순위표를 읽는 사람이다. 🔴 **아래 표에 있는 것만** 말한다 — "
            "표에 없는 팀·숫자·사건을 들이지 마라. 숫자를 **만들지 마라**. "
            "판단 한 줄만 낸다.")),
        llm.Message(role="user", content=(
            f"경기: {names[0]} (홈) vs {names[1]} (원정)\n"
            f"대회: {getattr(ref, 'competition', '')}\n\n"
            f"순위표(fotmob):\n{said}\n\n"
            "🔴 `urgent_team` — 위 두 팀 중 **이 경기가 더 급한 쪽**의 이름\n"
            f"🔴 `urgency` — {', '.join(URGENCY)} 중 하나\n"
            f"🔴 `why` — **표에서 확인되는 것만** {SAY_MAX}자 안에 한 줄\n"
            "   (순위·승점·남은 경기·구역을 근거로 든다)\n"
            "⚠️ 모르겠으면 `urgency` 를 `모르겠다` 로 두고 `why` 를 비운다.")),
    ]
    got = llm.ask(provider="deepseek", purpose="recall", messages=msgs,
                  out=LeagueRead, state=state,
                  enums={"urgent_team": names, "urgency": list(URGENCY)})
    if not isinstance(got, LeagueRead):
        why = f"🔴 LLM 분석 실패({getattr(got, 'reason', '?')}) — 코드 글자만 쓴다"
        state.note(f"s4c 리그 분석 — {why}")
        return {}, said + " · " + why
    team = str(got.urgent_team or "").strip()
    urg = str(got.urgency or "").strip()
    note = str(got.why or "").strip()[:SAY_MAX]
    if team not in set(names) or urg not in set(URGENCY):
        why = f"🔴 모델이 표 밖 값을 냈다(`{team}`·`{urg}`) — 버린다"
        state.note(f"s4c 리그 분석 — {why}")
        return {}, said + " · " + why
    out = {"urgent_team": team, "urgency": urg, "why": note, "rows": mine,
           "said": said}
    state.note(f"s4c 리그 분석 — **{team}** 이 더 급하다({urg}) · {note[:80]}")
    return out, said + f" · 🧠 **{team}** 이 더 급하다({urg}) — {note}"


#: 🔴 **변수 규칙 번호** — `config/interpret_rules.yaml` 의 IR14 다
RID = "IR14"


def variable(ref: MatchRef, got: dict) -> list:
    """🔴🔴 **분석 → 변수**(지시 2026-10-14: *"변수에 넣는다"*). `[Variable]`.

    🔴 유형은 `stakes`(동기)다 — 배치표가 그 자리를 안다.
    🔴 **주어는 급한 팀**이다 — λ 보정이 `subject` 로 쪽을 가린다.
       ⚠️ 그런데 뜻은 반대다: *급한 팀이 유리하다*. 그래서 `favors` 는
          `subject` 이고 λ 배율은 **상대**를 깎는다(설정이 그렇게 적는다).
    ⚠️ `모르겠다` 면 **변수를 만들지 않는다**(없는 판단을 사실로 바꾸지 않는다).
    🔴 `claim` 은 **코드가 센 글자 + 모델 한 줄**이다 — 숫자는 코드 것이다.
    """
    from app.core.schema import Variable
    urg = str(dict(got or {}).get("urgency") or "")
    team = str(dict(got or {}).get("urgent_team") or "")
    if not team or urg in ("", "모르겠다"):
        return []
    key = next((str(getattr(ref, s, "") or "") for s in ("home", "away")
                if str(getattr(ref, f"{s}_name", "") or "") == team
                or str(getattr(ref, s, "") or "") == team), "")
    if not key:
        return []
    rows = dict(dict(got or {}).get("rows") or {})
    one = dict(rows.get(team) or {})
    claim = (f"{team} 순위 동기 — {one.get('rank') or '⬜'}위 · "
             f"{one.get('played') or '⬜'}라운드 {one.get('points')}점"
             + (f" · 구역 {one.get('zone')}" if str(one.get("zone") or "") else "")
             + f" · **{urg}**"
             + (f" — {str(dict(got).get('why') or '')[:110]}"
                if str(dict(got).get("why") or "") else ""))
    side = "home" if key == str(getattr(ref, "home", "") or "") else "away"
    return [Variable(
        id=f"{RID}-{side}", type="stakes", subject=key,
        favors=side,                      # 🔴 급한 팀이 유리하다
        goals="none", target=f"stakes:{RID}", hardness="soft",
        weight=0.7, claim=claim, quote=claim, doc_ids=[],
        from_rule=RID, usable_as_basis=True)]
