"""🔴🔴 **세포는 장부다** — 유형 × 팀 칸마다 무엇을 해봤나. 사용자 지시 2026-10-05.

> **세포를 장부로 되살린다.** 유형 × 팀 칸마다 `searched / found / empty /
> not_tried` 를 기록하고, `done` 호출 시 **결장·로테이션·감독 발언·경기외** 네
> 유형이 `not_tried` 면 **`done` 을 거부**하고 *"이 유형을 아직 안 찾았다"* 를
> 돌려준다(**예산이 남아 있을 때만**). 이게 내가 전에 말한 **"계획기는 버리고
> 장부는 남긴다"** 의 실제 모양이다. — 사용자 지시 2026-10-05

══════════════════════════════════════════════════════════════════
🔴 왜 — 결정 ③이 질문을 **아무에게도 안 넘겼다**(실측 2026-10-05)
══════════════════════════════════════════════════════════════════

결정 ③(세포는 검색하지 않는다)의 **전제**는 *"카탈로그가 에이전트로 넘어간다"*
였다. 🔴 그런데 넘어가지 않았다:

```
에이전트가 낸 유형   form 10 · lineup 2 · context 2 · venue 1 · …
v5 §3-4 카탈로그    absence · squad_rotation · coach_conflict · event_match · …
겹침  🔴 **0개**
```

⚠️ 에이전트는 카탈로그를 **전혀 몰랐다** — 자기가 지은 이름을 썼다. 그리고
   세포는 끊겨서 `def_absence`·`squad_rotation`·`coach_conflict`·`event_match`
   를 **아무도 묻지 않았다.** 🔴 §1-1 의 `12 → 0` 과 **같은 꼴의 배선 끊김**이다.

🔴 **장부의 일**은 둘이다:
   ① 유형 × 팀 칸마다 **무엇을 해봤나**를 기록한다(조용한 0 금지 · #3)
   ② `done` 을 **막는다** — 네 유형을 안 해봤고 **예산이 남았으면**

⚠️ 장부는 **계획하지 않는다** — 무엇을 먼저 찾을지 정하지 않는다(그것이 끊은
   *계획기*다). 🔴 *"안 해본 칸이 있다"* 고 말할 뿐이다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: 🔴 **네 상태.** ⚠️ 순서가 뜻이다 — 뒤로 가지 않는다(찾은 것이 안 찾은 것이
#   되지 않는다). `not_tried` → `searched` → `empty` → `found`.
#  🔴🔴 **`budget_cut` 을 더했다** — 사용자 지시 2026-10-06 ③:
#     > 한 팀 하위 4개 중 **하나라도 `budget_cut`** 이면 2차 보충 대상.
#
#  ⚠️ **사다리의 자리가 뜻이다** — `mark` 는 **앞으로만** 간다. `budget_cut` 을
#     `not_tried` 바로 위에 둔 까닭: 2차 보충이 돌아 뭔가 찾으면(`found`) 또는
#     돌았는데 비면(`empty`) 그 **더 나아간 사실이 덮어야** 한다. 🔴 `found`
#     아래에 두지 않으면 막혔던 칸이 영원히 막힌 것으로 남는다.
STATES: tuple[str, ...] = ("not_tried", "budget_cut", "searched", "empty",
                           "found")

#: 🔴 `done` 을 막는 **네 유형** — 사용자가 이름을 댔다(2026-10-05).
#
#  ⚠️ **카탈로그 이름**이다(내가 고른 것이 아니다): `absence`(결장) ·
#     `squad_rotation`(로테이션) · `coach_conflict`(감독 발언) ·
#     `event_match`(경기외).
#  🔴 이 넷이 *"뒤집는 변수"* 의 본체다 — 폼·순위·맞대결은 **배경**에 가깝고
#     그것만으로는 시나리오가 얇아진다(실측: 18개 중 10개가 `form`).
MUST_TRY: tuple[str, ...] = ("absence", "squad_rotation", "coach_conflict",
                             "event_match")


@dataclass
class Book:
    """🔴 유형 × 팀 칸의 장부. ⚠️ **칸을 지우지 않는다** — 쌓기만 한다.

    ⚠️ 칸의 둘째 쪽은 **팀 열쇠**다(`team:000191`) — 이름이 아니다(§8-1).
       🔴 그래서 인자 이름도 `key` 다: 이름을 받는 자리로 세어지면 그 계약이
       *"새 코드는 열쇠를 받아라"* 라고 말하는데, 이미 열쇠를 받고 있다.
    """

    cells: dict = field(default_factory=dict)

    def _rank(self, state: str) -> int:
        return STATES.index(state) if state in STATES else 0

    def mark(self, kind: str, key: str, state: str) -> str:
        """🔴 칸을 적는다. ⚠️ **뒤로 안 간다** — 더 나아간 상태만 덮는다."""
        if state not in STATES:
            return self.state(kind, key)
        cell = (str(kind), str(key))
        now = self.cells.get(cell, "not_tried")
        if self._rank(state) > self._rank(now):
            self.cells[cell] = state
        return self.cells.get(cell, now)

    def searched(self, kind: str, key: str) -> str:
        """🔴 **찾아봤다**(결과는 아직 모른다)."""
        return self.mark(kind, key, "searched")

    def empty(self, kind: str, key: str) -> str:
        """🔴 찾아봤고 **없었다.** ⚠️ `not_tried` 와 **다르다**(#3)."""
        return self.mark(kind, key, "empty")

    def found(self, kind: str, key: str) -> str:
        """✅ 찾았고 **있었다**."""
        return self.mark(kind, key, "found")

    def state(self, kind: str, key: str) -> str:
        return self.cells.get((str(kind), str(key)), "not_tried")

    def why(self, kind: str, key: str) -> str:
        """🔴 그 칸의 **사유** — 실패와 *"안 해봤다"* 를 가른다(#3).

        ⚠️ 딥서치 재구축 §3-2: *"하위가 실패(타임아웃·`llm_unavailable`)했으면
           `not_tried` + **사유**."* 🔴 사유 없는 `not_tried` 는 고칠 곳을
           말하지 않는다.
        """
        return str((getattr(self, "whys", None) or {}).get(
            (str(kind), str(key))) or "")

    def not_tried(self, kinds, keys) -> list[str]:
        """🔴 그 유형들 중 **한 팀이라도 안 해본** 것들.

        ⚠️ 인자 이름이 `keys` 다 — **열쇠**를 받는다(§8-1). 🔴 `team` 이라
           부르면 이름을 받는 자리로 세어지고, 그 계약이 옳다: 이름을 받으면
           그 함수가 또 하나의 해석 지점이 된다.
        """
        out = []
        for k in (kinds or ()):
            if any(self.state(k, x) == "not_tried" for x in (keys or ())):
                out.append(str(k))
        return out

    def line(self) -> str:
        """🔴 한 줄 요약 — **칸 수를 상태별로**(#3 조용한 0 금지)."""
        from collections import Counter
        got = Counter(self.cells.values())
        said = " · ".join(f"{s} {got.get(s, 0)}" for s in STATES[1:])
        return f"장부 {len(self.cells)}칸 — {said}"
