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


def label_of(i: int) -> str:
    """변수 번호. 🔴 사용자 판의 `R1…Rn` 과 같은 꼴이다."""
    return f"R{i + 1}"


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


def run(items: list, game, *, board=None, standings: dict | None = None,
        probs: dict | None = None, limit: int = LIMIT, kickoff=None,
        stars: dict | None = None, shapes: dict | None = None) -> Result:
    """§7 방아쇠 — 변수마다 **빼고 다시 계산**해서 상한을 얻는다.

    🔴 `board` 는 `types.Market` 목록이다. 없으면 §6-c-3 우리 기준선으로 센다.
    ⚠️ 변수를 빼면 §7 R5(변수 3개·방향 2종)를 못 채울 수 있다 — 그러면 **자료
       부족**이고 그 방아쇠는 *"전부 철회"* 를 뜻한다. 그 사실을 그대로 적는다.
    🔴 `kickoff` 을 주면 *"언제 보나"* 를 **시계 시각**으로도 적는다(10단계).
    """
    res = Result()
    varis = [c for c in items if c.is_variable]
    if not varis:
        res.notes.append("변수가 없다 — 방아쇠를 만들 것이 없다(§7 R5)")
        return res

    base, base_ids, base_str, bad = _grades(items, game, board=board,
                                            standings=standings, probs=probs)
    if bad:
        res.notes.append("기준 상태가 자료 부족이다 — 상한을 비교할 바탕이 없다")
        return res

    made: list[Trigger] = []
    for i, v in enumerate(varis):
        # 🔴 **그 변수만 뺀다.** 같은 객체를 지우므로 다른 변수는 그대로다
        alt = [c for c in items if c is not v]
        got, ids, stren, short = _grades(alt, game, board=board,
                                         standings=standings, probs=probs)
        caps = []
        if short:
            # 🔴 자료 부족이면 **이름을 적던 모든 마켓이 철회**된다
            for name, (sv0, vd0) in base.items():
                if _RANK[vd0] > 0:
                    caps.append(Cap(name, sv0, 0.0, vd0, "none"))
        else:
            for name, (sv0, vd0) in base.items():
                sv1, vd1 = got.get(name, (0.0, "none"))
                if sv1 != sv0 or vd1 != vd0:
                    caps.append(Cap(name, sv0, sv1, vd0, vd1))
        # 🔴 **근거 변화도 센다** — 등급이 안 움직여도 strength 는 움직인다
        moved = {k: (base_str[k], stren.get(k, 0.0)) for k in base_str
                 if round(base_str[k], 4) != round(stren.get(k, 0.0), 4)}
        if not caps and not short and not moved:
            # ⚠️ 등급도 근거도 안 바뀌는 변수는 방아쇠가 아니다. **그래도 센다**
            continue
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **§7-2 — 기계 조건을 붙인다**
        # ══════════════════════════════════════════════════════════════
        #
        #  > 카드마다 명단에서 확인할 항목을 **1개 이상 기계 조건**으로 적는다.
        #
        #  🔴 빈 자리는 **이 경기 자료**가 채운다 — `stars`(팀 최다 득점자)와
        #     `shapes`(포메이션). ⚠️ 채울 값이 없으면 **만들지 않는다**
        #     (`player: in XI` 같은 평가 불가 글자를 조건이라 적지 않는다).
        team = str(getattr(v, "team", "") or "")
        chk, chk_why = trigcond.check_for(
            v.type, star=str((stars or {}).get(team) or ""),
            shape=str((shapes or {}).get(team) or ""))
        made.append(Trigger(
            id="", label=label_of(i),
            watch=_watch_text(v),
            when=when_of(v.type, kickoff),
            changed_scenarios=sorted(set(base_ids) ^ set(ids)),
            caps=caps, insufficient=short, moved_strength=moved,
            check=chk, check_why=chk_why))

    # 🔴 등급이 내려가는 것부터. 같으면 움직임이 큰 것부터
    made.sort(key=lambda t: t.impact, reverse=True)
    for n, t in enumerate(made[:limit]):
        t.id = "①②③④⑤⑥⑦⑧⑨⑩"[n] if n < 10 else str(n + 1)
    res.triggers = made[:limit]
    if len(made) > limit:
        res.dropped = [f"{t.label}({t.watch[:28]})" for t in made[limit:]]
        res.notes.append(
            f"🔴 방아쇠 {len(made)}개 중 {limit}개만 적었다 — 잘린 것: "
            f"{', '.join(res.dropped)}")
    # 🔴🔴 **이 경고가 이 파일에서 가장 중요한 줄이다.**
    #
    #  무게가 확률(포아송 격자)이면 그 격자는 **순위표**에서 나오고 변수와 무관하다.
    #  그러면 변수를 빼도 생존이 **한 치도** 안 움직인다 — 즉 §4 변수 수집(딥서치
    #  150건)이 **등급에 아무 영향이 없다.** v4 §0 은 그 반대를 전제한다:
    #  *"변수 개수·정확도 = 시나리오 품질"*.
    #  실측 2026-10-02(실측 경기(새크라멘토 vs 라스베이거스)): 변수 11개를 전부 빼 봐도 등급 변화 0건이었다.
    mute = [t.label for t in made if t.grade_unchanged]
    if mute and len(mute) == len(made):
        res.notes.append(
            f"🔴🔴 변수 {len(mute)}개가 **근거는 바꾸는데 등급은 하나도 안 바꾼다** — "
            f"무게가 확률(포아송 격자)이고 그 격자는 순위표에서 나와 변수와 무관하기 "
            f"때문이다. v4 §0 은 *'변수 개수·정확도 = 시나리오 품질'* 을 전제하는데 "
            f"지금 구조에서는 변수가 생존에 닿지 않는다 — 사용자 결정이 필요하다")
    flat = len(varis) - len(made)
    if flat:
        res.notes.append(
            f"변수 {flat}개는 빼도 어느 마켓의 등급·생존이 **안 변한다** — "
            f"방아쇠가 아니다(그 사실도 센다)")
    return res


def _watch_text(v) -> str:
    """*"무엇이 보이면"* — 🔴 변수의 **그 문장**에서 나온다. 요약하지 않는다."""
    txt = " ".join(str(getattr(v, "text", "") or "").split())
    if len(txt) > 90:
        txt = txt[:87] + "…"
    side = {"home": "홈", "away": "원정", "draw": "무승부"}.get(
        getattr(v, "direction", ""), "")
    return f"{txt}  [{v.type}·{side}] 이 **거짓으로 드러나면**"


def render(res: Result) -> str:
    """사람이 읽는 방아쇠 블록(사용자 출력 블록 10).

    🔴 **가격 숫자를 쓰지 않는다**(§7 R8). 상한은 `survival` 이다.
    """
    if not res.triggers:
        out = ["방아쇠 — 없다"]
        out += [f"  · {n}" for n in res.notes]
        return "\n".join(out)
    out = ["방아쇠"]
    for t in res.triggers:
        head = f"{t.id} {t.label} — {t.watch}"
        out.append(head)
        out.append(f"     언제: {t.when}")
        # 🔴 §7-2 — **기계 조건**. ⚠️ 못 만들었으면 그 까닭을 적는다(#3)
        out.append(f"     확인(기계): `{t.check}`" if t.check
                   else f"     ⚠️ 기계 조건 없음 — {t.check_why}")
        if t.insufficient:
            out.append("     🔴 빠지면 **자료 부족**이 된다(§7 R5) — 전부 철회")
        if t.changed_scenarios:
            out.append(f"     시나리오 변화: {', '.join(t.changed_scenarios)}")
        if t.moved_strength:
            bits = " · ".join(f"{k} {b}→{a}"
                              for k, (b, a) in sorted(t.moved_strength.items()))
            out.append(f"     근거(§5-d): {bits}")
        if t.grade_unchanged:
            out.append("     🔴 **등급은 안 바뀐다** — 무게가 확률이라 변수가 "
                       "생존에 닿지 않는다")
        for c in t.caps:
            out.append(f"     → {c.line()}")
    for n in res.notes:
        out.append(f"  · {n}")
    return "\n".join(out)
