"""§7 방아쇠 — **수동 12단계의 ⑫** (마지막 블록).

사용자 지시 2026-10-02: *"가라"* (⑫) · *"최종 목표는 니가 수동으로 돌려던 거를
자동화 하는 거다"*.

## 🔴 방아쇠는 **지어내지 않는다 — 다시 계산한다**

사용자의 수동 판이 이렇게 생겼다:

```
① 메모 로드리게스 벤치        → B·C 강화, 오버 0.8
② 기준 XI 에서 3명 이상 교체   → R9 on, 오버 0.8
③ 라스베이거스 4-3-3 그대로   → R4 유지, 오버 그대로
④ 라스베이거스가 5백으로      → B 강화, 오버 **철회**
```

꼴은 *"**무엇이 보이면** → **무엇이 바뀌고** → **상한 얼마**"* 셋이다. 그리고 그
셋은 전부 **이미 있는 것에서 나온다**:

| 칸 | 어디서 오나 |
|---|---|
| 무엇이 보이면 | 변수 하나가 **거짓으로 드러나는 것** — 변수 목록이 원본 |
| 언제 보나 | §4 유형의 `watch` → `cells.WAKE` 의 깨는 시각 |
| 무엇이 바뀌고 | 그 변수를 **빼고 §5 를 다시 돌린 결과** — 어느 시나리오가 변하나 |
| **상한 얼마** | 그 상태로 **§6 을 다시 돌린 생존·등급** |

🔴 **그래서 상한에 지어낸 숫자가 없다.** *"오버 0.8"* 은 그 변수를 뺐을 때 §6 이
실제로 내는 수다. 반사실(counterfactual) 한 번이 방아쇠 한 줄이다.

⚠️ **배당이 아니다.** 상한은 `survival` 이고 §7 R8 이 금지한 가격 숫자가 아니다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from app import cells, rules, scenarios, survive, timefmt, trigcond

logger = logging.getLogger(__name__)

#: 사용자 출력이 `①~④` 다. 🔴 **잘린 것은 이름으로 남긴다**(조용한 0 금지).
LIMIT = 4

#: 등급이 내려가는 순서. 🔴 `none` 으로 떨어지는 것이 **철회**다.
_RANK = {"name": 2, "small": 1, "none": 0}




def when_of(vtype: str, kickoff=None) -> str:
    """그 유형이 **언제 뒤집히나**. 🔴 `variable_types.yaml` → `cells.WAKE` 에서 나온다.

    ⚠️ 시각(분)을 여기 적지 않는다 — 두 곳에 적으면 갈린다(사본 금지).

    ══════════════════════════════════════════════════════════════════
    🔴 **킥오프를 알면 시계 시각으로도 적는다**(분석 과정 10단계)
    ══════════════════════════════════════════════════════════════════

    > 10. 상한·상관 → 결론·방아쇠 — 같은 방향 3개까지, **확인 항목 첨부**
    > 방아쇠 **(KST 10:00 XI)**

    사용자 글은 *"KST 10:00 에 XI 를 봐라"* 로 **시계 시각**이 박혀 있다. 봇은
    `T-70분` 만 적었다 — ⚠️ 그것은 **언제 보라는 말이 아니다.** 받는 사람이 머리로
    킥오프에서 빼야 하고, 거기서 틀리면 확인 자체를 놓친다.
    🔴 킥오프를 모르면 상대 시각만 적는다 — 지어내지 않는다.
    """
    cfg = (rules.variable_types().get(vtype) or {})
    q = cfg.get("watch")
    if not q or q not in cells.Q_TYPES:
        return f"언제 뒤집히는지 모른다(§4 `{vtype}.watch` 가 없다)"
    mins = cells.WAKE[q][0]
    if mins is None:
        return f"`{q}` 세포가 다시 돌 때(하루 1회)"
    out = f"`{q}` 세포가 깨는 T-{mins}분"
    if kickoff is not None:
        # 🔴 변환은 `timefmt` 하나다(절대규칙 2) — 여기서 다시 하지 않는다
        out = (f"{timefmt.kst_label(kickoff - timedelta(minutes=int(mins)))}"
               f" ({out})")
    return out


@dataclass
class Cap:
    """마켓 하나의 상한 변화. 🔴 **전·후를 둘 다** 들고 있어야 감사가 된다."""

    market: str
    before: float
    after: float
    verdict_before: str
    verdict_after: str

    @property
    def withdrawn(self) -> bool:
        """🔴 **철회** — 이름을 적던 것이 이름 없음으로 내려간다."""
        return (_RANK[self.verdict_before] > 0
                and _RANK[self.verdict_after] == 0)

    #: 🔴 등급이 안 바뀌어도 **생존이 움직인 것은 움직인 것이다.** 전 판은 등급만
    #  봐서 `그대로` 를 냈고, 그러면 *"0.56 → 0.68 로 올랐다"* 가 사라졌다.
    MOVES = ("철회", "하향", "상향", "생존↓", "생존↑", "그대로")

    @property
    def direction(self) -> str:
        a, b = _RANK[self.verdict_before], _RANK[self.verdict_after]
        if b < a:
            return "철회" if b == 0 else "하향"
        if b > a:
            return "상향"
        if self.after < self.before:
            return "생존↓"
        if self.after > self.before:
            return "생존↑"
        return "그대로"

    def line(self) -> str:
        """사람이 읽는 한 줄. 🔴 **가격 숫자가 없다**(§7 R8)."""
        if self.direction == "그대로":
            return f"{self.market} 그대로(생존 {self.after})"
        return (f"{self.market} {self.direction} — 생존 {self.before} → "
                f"{self.after}({self.verdict_after})")


@dataclass
class Trigger:
    """방아쇠 한 줄."""

    id: str
    label: str
    watch: str
    when: str
    changed_scenarios: list[str] = field(default_factory=list)
    caps: list[Cap] = field(default_factory=list)
    insufficient: bool = False
    #: 🔴 `{시나리오: (전, 후)}` — **근거(§5-d strength) 변화.** 등급이 안 움직여도
    #  이것은 움직인다. 둘을 따로 보지 않으면 변수가 한 일이 안 보인다.
    moved_strength: dict = field(default_factory=dict)
    #: 🔴🔴 **§7-2 기계 조건** — T-60 재실행이 **평가하는 식**이다.
    #
    #  ⚠️ `watch`·`when` 은 **사람 글**이다. 재실행이 그 글을 보고 무엇을 참으로
    #     볼지 정할 수 없다 — 그러면 등급을 바꿀 수 없고, *"바꾸지 못했다"* 와
    #     *"조건이 안 걸렸다"* 가 한 글자가 된다(§8-6).
    #  🔴 **못 만들면 빈 문자열**이고 그 까닭이 `check_why` 에 남는다(#3).
    check: str = ""
    check_why: str = ""

    @property
    def grade_unchanged(self) -> bool:
        """🔴 근거는 변했는데 **등급은 안 변했다** — 확률 무게의 결과다."""
        return bool(self.moved_strength) and not self.caps

    @property
    def impact(self) -> tuple:
        """정렬 열쇠. 🔴 **등급이 내려가는 것이 먼저다** — 그것이 돈을 잃는 자리다."""
        drops = sum(1 for c in self.caps if c.withdrawn)
        down = sum(1 for c in self.caps if c.direction in ("철회", "하향"))
        move = round(sum(abs(c.after - c.before) for c in self.caps), 4)
        ev = round(sum(abs(b - a) for b, a in self.moved_strength.values()), 4)
        return (drops, down, move, ev)


@dataclass
class Result:
    triggers: list[Trigger] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    #: 🔴 상한에 걸려 **잘린** 방아쇠 — 이름으로 남긴다
    dropped: list[str] = field(default_factory=list)

    @property
    def checks(self) -> list[str]:
        """🔴 §7-2 — 이 카드가 들고 나가는 **기계 조건 전부**."""
        return [t.check for t in self.triggers if t.check]

    def resolution(self, xi: dict | None = None):
        """🔴🔴 **§7-2 M28** — 조건을 명단에 대고 평가한다.

        ⚠️ 명단이 없으면(`None`) **평가 불가**이고 베팅 등급이 아니다. 🔴 조건이
           **0 개**인 것도 실패다(§7-2: *"카드마다 1개 이상"*).
        """
        return trigcond.resolve(self.checks, xi)


def _grades(items: list, game, *, board, standings, probs):
    """§5 → §6 을 한 번 돌려 **마켓별 (생존, 등급)** · 시나리오 id · **근거 무게**.

    🔴 `strength` 도 함께 돌려준다 — 등급이 안 변해도 **근거는 변한다.** 그 둘을
       따로 보지 않으면 *"변수가 아무 일도 안 한다"* 를 못 본다(아래 `run` 의 경고).
    """
    sc = scenarios.generate(items, game, standings=standings, board=board)
    if sc.insufficient or not sc.drafts:
        return {}, [], {}, True
    sv = survive.run(sc.drafts, game, board=board, standings=standings,
                     probs=probs)
    got = {r["name"]: (r["survival"], r["verdict"]) for r in sv.rows}
    stren = {d.id: d.strength for d in sc.drafts}
    return got, [d.id for d in sc.drafts], stren, False




def _watch_text(v) -> str:
    """*"무엇이 보이면"* — 🔴 변수의 **그 문장**에서 나온다. 요약하지 않는다."""
    txt = " ".join(str(getattr(v, "text", "") or "").split())
    if len(txt) > 90:
        txt = txt[:87] + "…"
    side = {"home": "홈", "away": "원정", "draw": "무승부"}.get(
        getattr(v, "direction", ""), "")
    return f"{txt}  [{v.type}·{side}] 이 **거짓으로 드러나면**"


