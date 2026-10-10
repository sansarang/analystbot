"""🔴🔴 **최종 평의 사실 묶음**. 사용자 지시 2026-10-10(넷째) §1.

> 사실 묶음 (코드가 만든다, **LLM 입력의 전부**)
> 각 항목에 **id** 를 붙인다. 없는 칸은 **"없음"** 으로 넣고 LLM에게 그 칸에
> 대해 **말하지 말라**고 한다.

🔴 이 파일은 **수를 세거나 받지 않는다** — 앞 단계들이 이미 센 것을 **id 로 묶는다**
   (사본 금지: 비중·백분위·발동 규칙은 `goals`·`style`·`strategy`·`matchup` 이 든다).
🔴 **없는 칸을 0 으로 메우지 않는다**(#3) — `없음` 항목을 만들고 그 사유를 적는다.
   그래서 검열 (r)·(s)·(t) 가 *"없는 것을 인용했다"* 를 잡을 수 있다.

id 앞글자 — 어느 칸에서 왔나:

| 앞글자 | §1 칸 |
|---|---|
| `X` | 1-1 라인업 변화(자리·측면) |
| `F` | 1-2 측면별 공격·수비 지표 |
| `G` | 1-3 골 내용(축3) |
| `S` | 1-4 전략·스타일·발동 규칙 |
| `M` | 1-5 동기·일정 |
| `N` | 1-6 결장·복귀·새 사실(72시간) |
| `P` | 1-7 확률 |

⚠️ 전략 사실(`L*`·`A*`)은 **그 id 를 그대로 둔다** — `s2d_strategy` 가 붙인 이름이고
   카드·검열이 이미 그 글자로 가리킨다(두 이름을 만들면 사본이 된다).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: 🔴 §1-1 — **받는 통로가 없는 지표**. 사실 묶음이 `없음` 으로 적는다(#3).
#  ⚠️ 실측 2026-10-10: 경기 페이지의 선수 칸은 `age·marketValue·
#     performance.seasonRating` 뿐이고, 선수단 페이지는 `goals·assists·
#     rating·age·height·injury` 뿐이다. 팀 **합계**로는 `duel_won`·`tackles`·
#     `interceptions`·`aerials_won`·`dribbles_succeeded`·`accurate_crosses` 가
#     있지만 **선수별로는 없다**.
NO_PLAYER_STATS = ("경합 승률", "태클", "가로채기", "공중볼", "드리블", "크로스",
                   "슈팅", "시즌 출장 시간")
#: 🔴 §1-2 — 측면 비중을 **근사**로 만들 때 붙이는 글자(검열 (s) 가 이 글자를 센다)
APPROX = "근사"
#: 🔴 측면 판정 — 들어온 쪽 기여가 빠진 쪽보다 이만큼 낮으면 `약화`(비율)
FLANK_DROP = 0.25


@dataclass
class Item:
    """🔴 사실 하나 — **id 로 가리킨다**(§2 의 근거 id 가 이것이다)."""

    id: str
    kind: str
    text: str
    value: float | None = None
    #: 🔴 §1-2 — 근사 지표인가(검열 (s): 근사면 글에 `근사` 라고 써야 한다)
    approx: bool = False
    #: 🔴 어느 팀 얘기인가(`home`·`away`·빈 글자)
    side: str = ""


@dataclass
class Bundle:
    """🔴 §1 묶음 전체. ⚠️ **빈 칸의 사유**도 함께 든다(#3)."""

    items: dict = field(default_factory=dict)
    #: 🔴 `없음` 으로 들어간 칸들 — 프롬프트가 *"이 칸은 말하지 마라"* 로 쓴다
    empty: list = field(default_factory=list)

    def ids(self) -> set:
        return set(self.items)

    def of(self, which: str) -> list:
        """🔴 그 앞글자의 항목들(순서 유지)."""
        return [v for k, v in self.items.items() if str(k).startswith(which)]


def build(card) -> Bundle:
    """🔴🔴 §1 — 카드에서 **사실 묶음**을 만든다. ⚠️ 새 통신·새 계산 0건."""
    got = Bundle()
    _lineup(card, got)          # 1-1
    _flanks(card, got)          # 1-2
    _goals(card, got)           # 1-3
    _strategy(card, got)        # 1-4
    _motive(card, got)          # 1-5
    _absence(card, got)         # 1-6
    _probs(card, got)           # 1-7
    _checked(card, got)         # 🔴 단계 5 — 지지/반박된 가설
    _s7(card, got)              # 🔴 S7 — 상성 판정·검증 요약·상성 사각
    _names_item(card, got)      # 🔴 팀 이름 표기(음역 금지)
    return got


def _put(got: Bundle, item: Item) -> None:
    got.items[item.id] = item


def _none(got: Bundle, what: str, why: str) -> None:
    """🔴 #3 — **없는 칸을 이름으로** 남긴다(LLM 은 이 칸을 말하지 않는다)."""
    got.empty.append(f"{what} — 없음({why})")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §1-1 — **라인업 변화(자리·측면 단위)**
# ══════════════════════════════════════════════════════════════════

def _rows_of(card, key: str) -> list:
    """🔴 그 팀 오늘 XI 의 `Player` 줄들(세부 자리·측면이 든 것)."""
    xi = (card.facts.xi or {}).get(key)
    return list(getattr(xi, "lineup", None) or [])


def _usual_of(card, key: str) -> tuple[list, str]:
    """🔴 평소 XI — `s2b.usual_xi` 하나가 센다(사본 금지)."""
    from app.core.stages import s2b_base as _b
    rows = list((card.facts.past_xi or {}).get(key) or [])
    if not rows:
        return [], "과거 선발이 없다"
    return _b.usual_xi(rows)


def _stat_of(card, name: str) -> dict:
    """🔴 그 선수의 시즌 기록 — 조회는 `strategy.stat_of` **한 곳**이다.

    ⚠️ 글자로 맞추면 안 된다 — 선수단 페이지는 `Park Man-Ho`, 라인업은
       `Man-Ho Park` 이다(실사고 2026-10-10: 겹치는 이름 **0명**).
    """
    from app.core import strategy as _st
    return _st.stat_of(card.facts, name)


def _who(card, name: str) -> str:
    """🔴 선수 한 명을 **수와 함께** 한 글자로. ⚠️ 없는 수는 적지 않는다."""
    box = _stat_of(card, name)
    bits = []
    if box.get("goals") is not None or box.get("assists") is not None:
        bits.append(f"시즌 {int(box.get('goals') or 0)}골 "
                    f"{int(box.get('assists') or 0)}도움")
    if box.get("rating") is not None:
        bits.append(f"레이팅 {float(box['rating']):.2f}")
    if box.get("age") is not None:
        bits.append(f"{int(box['age'])}세")
    return f"{name}" + (f"({' · '.join(bits)})" if bits else "(기록 없음)")


def _worth(card, name: str) -> float | None:
    """🔴 측면 판정의 재료 — **시즌 득점+도움**. ⚠️ 기록이 없으면 `None`."""
    box = _stat_of(card, name)
    if box.get("goals") is None and box.get("assists") is None:
        return None
    return float(int(box.get("goals") or 0) + int(box.get("assists") or 0))


def _spot_flank(card, rows: list, name: str) -> tuple[str, str]:
    """🔴 그 이름의 **세부 자리·측면**. 오늘 XI 에 없으면 과거 XI 에서 찾는다."""
    for p in rows:
        if str(p.name) == str(name):
            return str(p.spot or ""), str(p.flank or "")
    for key in ((card.facts.past_xi or {})):
        for xi in list((card.facts.past_xi or {}).get(key) or []):
            for p in (getattr(xi, "lineup", None) or []):
                if str(p.name) == str(name):
                    return str(p.spot or ""), str(p.flank or "")
    return "", ""


def _lineup(card, got: Bundle) -> None:
    """🔴🔴 §1-1 — 자리별 **빠짐 → 들어옴** + **측면 판정**(코드가 정한다)."""
    n = 0
    seen_stats = False
    for side in ("home", "away"):
        key = str(getattr(card.match, side))
        name = str(getattr(card.match, f"{side}_name", "") or "")
        rows = _rows_of(card, key)
        if not rows:
            _none(got, f"{name} 오늘 XI 자리 정보", "선발 명단을 못 받았다")
            continue
        usual, how = _usual_of(card, key)
        now = [str(p.name) for p in rows]
        n += 1
        said = " · ".join(f"{p.spot or '?'}{'' if not p.flank else f'({p.flank})'}"
                          f" {p.name}" for p in rows)
        _put(got, Item(id=f"X{n}", kind="xi", side=side,
                       text=(f"{name} 오늘 XI 자리 — {said}")))
        if any(_stat_of(card, x) for x in now):
            seen_stats = True
        if not usual:
            _none(got, f"{name} 평소 XI", how)
            continue
        out_names = [x for x in usual if x not in now]
        in_names = [x for x in now if x not in usual]
        n += 1
        _put(got, Item(id=f"X{n}", kind="rotation", side=side,
                       value=float(len(in_names)),
                       text=(f"{name} 평소 XI 대비 바뀐 자리 {len(in_names)}개"
                             f"(평소 XI 는 {how})")))
        # 🔴 **자리·측면 묶음으로** 모은다 — 같은 측면의 교체를 한 항목으로
        box: dict = {}
        for who, where in ((out_names, "out"), (in_names, "in")):
            for nm in who:
                spot, flank = _spot_flank(card, rows, nm)
                box.setdefault((spot or "?", flank or "?"),
                               {"out": [], "in": []})[where].append(nm)
        for (spot, flank), one in box.items():
            n += 1
            verdict, why = _flank_verdict(card, one)
            _put(got, Item(
                id=f"X{n}", kind="swap", side=side,
                text=(f"{name} {spot} 자리"
                      + (f"({flank}쪽)" if flank != "?" else "")
                      + " — 빠짐 "
                      + (", ".join(_who(card, x) for x in one["out"]) or "없음")
                      + " → 들어옴 "
                      + (", ".join(_who(card, x) for x in one["in"]) or "없음")
                      + f" · **{verdict}**{why}")))
    if n and not seen_stats:
        _none(got, "선수별 시즌 기록", "선수단 페이지를 못 받았다")
    # 🔴 §1-1 이 요구한 지표 중 **받는 통로가 없는 것**을 이름으로 적는다(#3)
    _none(got, "선수별 " + "·".join(NO_PLAYER_STATS),
          "출처가 선수별로 주지 않는다(팀 합계만 있다)")


def _flank_verdict(card, one: dict) -> tuple[str, str]:
    """🔴🔴 §1-1 셋째 줄 — **측면 판정은 코드가 한다**(LLM 이 아니다).

    `강화` · `약화` · `비슷` · `판정 못 함`. 뒤쪽 글자는 그 **근거**다.

    ⚠️ 기여를 못 잰 선수가 끼면 **판정 못 함**이다 — 0 으로 놓고 "약화"라고
       말하면 기록 없는 어린 선수가 늘 약화가 된다(#3·#4).
    """
    outs = [_worth(card, x) for x in one.get("out") or []]
    ins = [_worth(card, x) for x in one.get("in") or []]
    if not outs or not ins:
        return "자리 수 변화", ""
    if any(v is None for v in (*outs, *ins)):
        return "판정 못 함", "(기여를 못 잰 선수가 있다)"
    a, b = sum(float(x) for x in outs), sum(float(x) for x in ins)  # type: ignore[arg-type]
    if a <= 0 and b <= 0:
        return "비슷", "(양쪽 다 시즌 공격 기여 0)"
    if b < a * (1 - FLANK_DROP):
        return "약화", f"(기여 {a:.0f} → {b:.0f})"
    if b > a * (1 + FLANK_DROP):
        return "강화", f"(기여 {a:.0f} → {b:.0f})"
    return "비슷", f"(기여 {a:.0f} → {b:.0f})"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §1-2 — **측면별 공격·수비 지표**(있는 리그만)
# ══════════════════════════════════════════════════════════════════
#
#  🔴 실측 2026-10-10: fotmob 경기 통계 37칸에 **방향(왼/중앙/오른) 칸이 없다**
#     (`accurate_crosses`·`duel_won`·`aerials_won` 은 팀 합계이고 방향이 없다).
#  🔴 그래서 §1-2 둘째 줄을 그대로 한다 — *"없으면 오늘 XI 측면별 공격 선수의
#     기여 합으로 **근사**(근사 표시)"*. ⚠️ `approx=True` 가 그 표시이고, 검열
#     (s) 가 *"근사라고 안 썼다"* 를 잡는다.
#  🔴 **실점 방향은 근사하지 않는다** — 재료가 아예 없다(`없음`).

def _flanks(card, got: Bundle) -> None:
    """🔴 §1-2 — 측면 비중(근사) + **측면 맞대결**(코드가 짝짓는다)."""
    n = 0
    share: dict = {}
    for side in ("home", "away"):
        key = str(getattr(card.match, side))
        name = str(getattr(card.match, f"{side}_name", "") or "")
        rows = _rows_of(card, key)
        if not rows:
            continue
        tally = {"왼": 0.0, "중앙": 0.0, "오른": 0.0}
        seen = 0
        for p in rows:
            if str(p.spot or "") in ("GK", "CB", "LB", "RB", ""):
                continue            # 🔴 공격 기여를 보는 것이다(수비 자리는 뺀다)
            worth = _worth(card, str(p.name))
            if worth is None:
                continue
            seen += 1
            tally[str(p.flank or "중앙")] = tally.get(
                str(p.flank or "중앙"), 0.0) + float(worth)
        total = sum(tally.values())
        if not seen or total <= 0:
            _none(got, f"{name} 측면 공격 비중",
                  "오늘 XI 공격 자원의 시즌 기여가 0이거나 기록이 없다")
            continue
        share[side] = {k: v / total for k, v in tally.items()}
        n += 1
        _put(got, Item(
            id=f"F{n}", kind="flank_share", side=side, approx=True,
            text=(f"{name} 측면 공격 비중({APPROX} — 오늘 XI 공격 자원 "
                  f"{seen}명의 시즌 득점+도움 합) 왼 "
                  + " · ".join(f"{k} {v / total:.0%}" for k, v in tally.items()
                               ).replace("왼 왼", "왼"))))
    _none(got, "팀 실점 방향(어느 측면에서 허용했나)",
          "출처에 방향 칸이 없다(경기 통계 37칸을 실측했다)")
    # 🔴 §1-2 셋째 줄 — **측면 맞대결**: 내 왼쪽 공격 ↔ 상대 오른쪽 수비
    mirror = {"왼": "오른", "오른": "왼"}
    for side in ("home", "away"):
        other = "away" if side == "home" else "home"
        name = str(getattr(card.match, f"{side}_name", "") or "")
        them = str(getattr(card.match, f"{other}_name", "") or "")
        mine = dict(share.get(side) or {})
        for flank in ("왼", "오른"):
            if float(mine.get(flank, 0.0)) < 0.3:
                continue
            said = _defence_of(card, other, mirror[flank])
            if not said:
                continue
            n += 1
            _put(got, Item(
                id=f"F{n}", kind="flank_duel", side=side, approx=True,
                text=(f"측면 맞대결 — {name} {flank}쪽 공격({APPROX} 비중 "
                      f"{float(mine[flank]):.0%}) ↔ {them} "
                      f"{mirror[flank]}쪽 수비 {said}")))


def _defence_of(card, side: str, flank: str) -> str:
    """🔴 그 팀 그 측면 **수비 자리의 오늘 상태** — 바뀐 자리면 그 판정을 쓴다."""
    key = str(getattr(card.match, side))
    rows = _rows_of(card, key)
    for p in rows:
        if str(p.flank or "") == flank and str(p.spot or "") in ("LB", "RB"):
            box = _stat_of(card, str(p.name))
            said = (f"레이팅 {float(box['rating']):.2f}"
                    if box.get("rating") is not None else "기록 없음")
            return f"{p.spot} {p.name}({said})"
    return ""


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §1-3 — **골 내용**(축3). 🔴 코드가 문장을 만든다(LLM 이 세지 않는다)
# ══════════════════════════════════════════════════════════════════
#
#  > *"필드골 0 — 최근 5경기 득점이 전부 세트피스·PK"* 같은 문장은 **코드가 사실로
#  > 만든다**(LLM이 세지 않는다).

#: 🔴 유형 글자 — `render.KIND_KO` 하나가 든다(사본 금지)
def _kind_ko() -> dict:
    from app.core import render
    return dict(render.KIND_KO)


def _goals(card, got: Bundle) -> None:
    """🔴 §1-3 — 득점·실점 유형·시간대·선제골 후 결과·운 요소."""
    box = dict(getattr(card, "matchup", None) or {})
    prof = dict(box.get("profile") or {})
    if not prof:
        _none(got, "골 내용(축3)", str(box.get("why") or "상성을 못 셌다"))
        return
    ko = _kind_ko()
    n = 0
    for side in ("home", "away"):
        one = prof.get(side)
        name = str(getattr(card.match, f"{side}_name", "") or "")
        if one is None:
            continue
        for what, got_side in (("득점", one.scored), ("실점", one.conceded)):
            if not got_side.n:
                _none(got, f"{name} {what} 유형", "표본 0골")
                continue
            n += 1
            kinds = " · ".join(
                f"{ko.get(k, k)} {int(v)}건({int(v) / got_side.n:.0%})"
                for k, v in sorted(dict(got_side.by_kind).items(),
                                   key=lambda kv: -int(kv[1])))
            _put(got, Item(id=f"G{n}", kind="goal_kind", side=side,
                           value=float(got_side.n),
                           text=f"{name} {what} {got_side.n}골 유형 — {kinds}"))
            n += 1
            _put(got, Item(
                id=f"G{n}", kind="goal_time", side=side,
                text=(f"{name} {what} 시간대 — "
                      + " · ".join(f"{k} {int(v)}건"
                                   f"({int(v) / got_side.n:.0%})"
                                   for k, v in sorted(
                                       dict(got_side.by_bucket).items())))))
            # 🔴 **"필드골 0" 문장을 코드가 만든다**(§1-3 둘째 줄)
            if not int(dict(got_side.by_kind).get("open", 0)):
                n += 1
                _put(got, Item(
                    id=f"G{n}", kind="goal_path", side=side, value=0.0,
                    text=(f"{name} {what} {got_side.n}골 중 **필드골 0** — "
                          "전부 세트피스·PK·역습·미상이다")))
            if got_side.lucky:
                n += 1
                _put(got, Item(
                    id=f"G{n}", kind="luck", side=side,
                    value=float(got_side.lucky),
                    text=(f"{name} {what} {got_side.n}골 중 **운 요소**"
                          f"(자책골·PK·낮은 xG) {got_side.lucky}골"
                          f"({got_side.lucky / got_side.n:.0%}) — "
                          "득점력의 근거로 쓰지 않는다")))
        hold, back = one.hold_rate(), one.comeback_rate()
        n += 1
        _put(got, Item(
            id=f"G{n}", kind="flow", side=side,
            text=(f"{name} 선제골 후 결과 "
                  + (f"리드 유지력 {hold:.0%} {dict(one.led_first)}"
                     if hold is not None else "선제골 경기 0건")
                  + " · 선실점 후 "
                  + (f"추격력 {back:.0%} {dict(one.trailed_first)}"
                     if back is not None else "선실점 경기 0건"))))


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §1-4 — **전략·스타일·발동 규칙**
# ══════════════════════════════════════════════════════════════════

def _strategy(card, got: Bundle) -> None:
    """🔴 §1-4 — 전략 판정(+근거 id 그대로) · 스타일 백분위 · T1~T13."""
    plan = getattr(card, "strategy", None)
    box = dict(getattr(card, "matchup", None) or {})
    # 🔴 전략 사실은 **`s2d` 가 붙인 id**(`L*`·`A*`)를 그대로 쓴다
    for k, v in dict(getattr(plan, "facts", None) or {}).items():
        one = dict(v)
        _put(got, Item(id=str(k), kind=str(one.get("kind") or "strategy"),
                       text=str(one.get("text") or ""),
                       value=(float(one["value"])
                              if one.get("value") is not None else None)))
    n = 0
    for line in (getattr(plan, "lines", None) or []):
        n += 1
        _put(got, Item(
            id=f"S{n}", kind="strategy", side=str(getattr(line, "side", "")),
            text=(f"{getattr(line, 'side', '')} 전략 판정 "
                  f"**{getattr(line, 'strategy', '')}** — "
                  f"{getattr(line, 'why', '')} · 근거 "
                  f"{list(getattr(line, 'fact_refs', None) or [])}")))
    if plan is not None and str(getattr(plan, "shape", "") or ""):
        n += 1
        _put(got, Item(id=f"S{n}", kind="shape",
                       text=f"맞대결 양상 — {plan.shape}"))
    if not getattr(plan, "lines", None):
        _none(got, "전략 판정",
              str(getattr(plan, "audit", "") or "안 돌았다"))
    for side, one in dict(box.get("style") or {}).items():
        for axis, val in dict(getattr(one, "axis", None) or {}).items():
            n += 1
            _put(got, Item(id=f"S{n}", kind="style", side=side,
                           value=float(val),
                           text=(f"{side} 스타일 6축 `{axis}` {float(val):.3f}"
                                 f"(두 팀 사이 비교값)")))
    fired = [*(box.get("fired2") or []), *(box.get("fired") or [])]
    for f in fired:
        _put(got, Item(
            id=str(f.rule), kind="rule", side=str(f.side),
            text=(f"[{f.rule}] {f.side} {f.text}"
                  + (" (관찰만 — 확률 미반영)" if f.watch_only
                     else f" · 효과 {dict(f.moves())}"))))
    if not fired:
        _none(got, "발동 규칙 T1~T13", "문턱을 넘은 규칙이 없다")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §1-5 — **동기·일정**
# ══════════════════════════════════════════════════════════════════

def _motive(card, got: Bundle) -> None:
    """🔴 §1-5 — 순위·경우의 수 · 감독 발언 · 휴식일·직전 대회."""
    n = 0
    box = dict(getattr(card, "matchup", None) or {})
    std = dict(card.facts.standings or {})
    rows = dict(std.get("group") or {}).get("rows") or []
    for side in ("home", "away"):
        key = str(getattr(card.match, side))
        name = str(getattr(card.match, f"{side}_name", "") or "")
        got_row = [r for r in rows if str(dict(r).get("team") or "") == key]
        if got_row:
            r = dict(got_row[0])
            n += 1
            _put(got, Item(
                id=f"M{n}", kind="standing", side=side,
                text=(f"{name} 순위 {r.get('rank')}위 · 승점 {r.get('points')}"
                      f" · {r.get('played')}경기"
                      + (f" · 구역 `{r.get('zone')}`" if r.get("zone") else ""))))
        rest = dict(box.get("rest") or {}).get(side)
        if rest is not None:
            n += 1
            _put(got, Item(id=f"M{n}", kind="rest", side=side,
                           value=float(rest),
                           text=f"{name} 휴식 {int(rest)}일"))
        seq = list(dict(card.facts.recent or {}).get(key, {})
                   .get("sequence") or [])
        if seq:
            last = dict(seq[0])
            n += 1
            _put(got, Item(
                id=f"M{n}", kind="last_match", side=side,
                text=(f"{name} 직전 경기 {last.get('date')} "
                      f"{last.get('tournament')} {last.get('side')} "
                      f"{last.get('score')}")))
        coach = (card.facts.coach or {}).get(key)
        said = str(getattr(coach, "quote", "") or "") if coach else ""
        if said:
            n += 1
            _put(got, Item(id=f"M{n}", kind="coach", side=side,
                           text=f"{name} 감독 발언 — {said}"))
    if not rows:
        _none(got, "순위·경우의 수", "같은 조 순위표를 못 받았다")
    if not any(v.kind == "coach" for v in got.items.values()):
        _none(got, "감독 발언", "72시간 안의 발언 기사가 없다")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §1-6 — **결장·복귀·새 사실(72시간)**
# ══════════════════════════════════════════════════════════════════

def _absence(card, got: Bundle) -> None:
    """🔴 §1-6 — 결장 명단 · 복귀 · 새 사실. ⚠️ 0건도 **이름으로** 적는다."""
    from app.core import render
    n = 0
    for side in ("home", "away"):
        key = str(getattr(card.match, side))
        name = str(getattr(card.match, f"{side}_name", "") or "")
        rows = list((card.facts.missing or {}).get(key) or [])
        for m in rows:
            n += 1
            _put(got, Item(
                id=f"N{n}", kind="absence", side=side,
                text=(f"{name} 결장 {m.name}"
                      + (f"({m.pos})" if getattr(m, "pos", "") else "")
                      + f" — {getattr(m, 'reason', '')}")))
        if not rows:
            _none(got, f"{name} 결장 명단", "출처가 결장 명단을 안 줬다")
    # 🔴 복귀는 **전략 사실**이 이미 들고 있다(`kind: returning` · `L*`·`A*`) —
    #    여기서 새 id 를 발급하면 같은 사실이 두 이름을 갖는다(사본 금지).
    plan = getattr(card, "strategy", None)
    back = [str(k) for k, v in dict(getattr(plan, "facts", None) or {}).items()
            if str(dict(v).get("kind") or "") == "returning"]
    if not back:
        _none(got, "복귀 선수", "확정 XI 에서 복귀로 센 선수가 없다")
    rows = render.new_facts(card)
    for v in rows:
        n += 1
        _put(got, Item(id=f"N{n}", kind="new_fact",
                       text=f"새 사실(72시간) — {v.claim} [{v.id}]"))
    if not rows:
        _none(got, "새 사실(72시간)", "창 안에서 건진 기사 사실이 0건")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §1-7 — **확률**
# ══════════════════════════════════════════════════════════════════

def _s7(card, got: Bundle) -> None:
    """🔴🔴 S7 — 최종 평의 **첫 줄 재료**와 **상성 사각 문장**.

    > 첫 줄: 상성 판정(우위 팀·강도) + 검증 요약(같은 방향 n · 반대 n — 원인).
    > **상성 사각(c)이 있으면 반드시 한 문장.**
    """
    box = dict(getattr(card, "matchup", None) or {})
    mr = box.get("report")
    if mr is not None:
        verdict = dict(getattr(mr, "verdict", None) or {})
        who = {"home": card.match.home_name,
               "away": card.match.away_name}.get(str(verdict.get("edge") or ""),
                                                 "가리지 못함")
        _put(got, Item(id="M0", kind="matchup_verdict",
                       text=(f"상성 판정 — **{who}** {verdict.get('strength')}"
                             f" · {verdict.get('why')}")))
    chk = dict(getattr(card, "check", None) or {})
    rows = list(chk.get("sources") or [])
    if rows:
        same = [r for r in rows if dict(r).get("dir") == "같음"]
        against = [r for r in rows if dict(r).get("dir") == "반대"]
        _put(got, Item(id="M00", kind="verify_sum",
                       text=(f"검증 요약 — 같은 방향 {len(same)} · 반대 "
                             f"{len(against)}"
                             + (" · 반대 원인 "
                                + ", ".join(f"{dict(r)['src']}:{dict(r)['cause']}"
                                            for r in against[:3])
                                if against else ""))))
        # 🔴 **상성 사각(c)** — 있으면 평이 **반드시 한 문장** 적는다
        from app.core.stages import s6c_check as _chk
        blind = [r for r in against
                 if dict(r).get("cause") == _chk.CAUSE_BLIND]
        for i, one in enumerate(blind[:3], 1):
            said = dict(one)
            _put(got, Item(id=f"B{i}", kind="blind",
                           text=(f"**상성 사각** — {said.get('src')} "
                                 f"{said.get('name')}이 상성과 **반대**다 · "
                                 f"{said.get('why')}")))


def _names_item(card, got: Bundle) -> None:
    """🔴🔴 **팀 이름의 한국어 표기**를 사실로 넣는다.

    ⚠️ 실측 2026-10-10(재현): 평이 `FC Anyang` 을 **"애냥"** 이라고 적었다 —
       입력에 한국어 표기가 없어 모델이 **음역을 지어냈다**. 🔴 별칭표가 아는
       표기를 주고, 프롬프트가 *"그 글자를 그대로 쓰라"* 고 못 박는다.
    ⚠️ 별칭표에 한국어가 없으면 **그 사실을 적는다**(지어내지 않는다 · #3).
    """
    from app.core import discover as _d
    rows = []
    for side in ("home", "away"):
        name = str(getattr(card.match, f"{side}_name", "") or "")
        ko = [x for x in _d.aliases_of(name)
              if any("가" <= ch <= "힣" for ch in str(x))]
        rows.append(f"{name} = " + (" · ".join(sorted(set(ko))[:3]) if ko
                                    else "한국어 표기 없음"))
    _put(got, Item(id="P0", kind="team_names",
                   text=("팀 이름 표기(이 글자를 그대로 쓴다 · 음역을 지어내지 "
                         "않는다) — " + " / ".join(rows))))


def _checked(card, got: Bundle) -> None:
    """🔴🔴 **단계 5** — 검증을 통과한 가설만 평의 재료다(순서 재편 §5).

    > 최종 평은 **지지된 가설과 그 근거만** 쓴다. 반박된 가설은 "🔄 뒤집히는
    > 조건" 후보로만. **판단 불가 가설은 평에 쓰지 않는다.**
    > 기준 낡음 의심이 있으면 **평 첫 줄에** 그 사실을 적는다.

    🔴 id 앞글자는 `H`(지지)·`R`(반박 — 뒤집히는 조건 후보)다. ⚠️ `판단 불가` 는
       **묶음에 넣지 않는다** — 넣으면 모델이 그것을 근거로 쓴다.
    """
    from app.core import signals as _sg
    box = dict(getattr(card, "check", None) or {})
    rows = list(box.get("rows") or [])
    if not rows:
        _none(got, "가설 검증표", str(box.get("why") or "가설이 없다"))
        return
    n_ok = n_no = 0
    for one in rows:
        said = dict(one)
        if str(said.get("verdict")) == _sg.OK:
            n_ok += 1
            _put(got, Item(id=f"H{n_ok}", kind="supported",
                           side=str(said.get("side") or ""),
                           text=(f"**지지된 가설** — {said.get('text')} · 신호 "
                                 f"{said.get('signal')} · 시뮬 "
                                 f"{said.get('value')}(기준 {said.get('want')})"
                                 f" · 근거 변수 {said.get('var_ids')}")))
        elif str(said.get("verdict")) == _sg.NO:
            n_no += 1
            _put(got, Item(id=f"R{n_no}", kind="refuted",
                           side=str(said.get("side") or ""),
                           text=(f"**반박된 가설**(뒤집히는 조건 후보) — "
                                 f"{said.get('text')} · {said.get('why')}")))
    if not n_ok:
        _none(got, "지지된 가설", "하나도 없다 — 평은 수치만으로 쓴다")
    # 🔴 §5 — **기준 낡음**은 평 첫 줄에 적어야 한다(프롬프트가 그렇게 시킨다)
    if str(box.get("stale") or ""):
        _put(got, Item(id="H0", kind="stale", text=str(box["stale"])))
    if str(box.get("rerun") or ""):
        _put(got, Item(id="H00", kind="rerun",
                       text=f"재실행 — {box['rerun']}"))


def _probs(card, got: Bundle) -> None:
    """🔴 §1-7 — 최종 승무패·오버·잠정→최종·축별 기여·예상 스코어 상위 3."""
    from app.core import layer1
    m = card.match
    new = card.our_prob
    if new is None:
        _none(got, "최종 확률", "확률을 못 셌다")
        return
    _put(got, Item(
        id="P1", kind="prob",
        text=(f"최종 확률 — {m.home_name} 승 {new.home:.0%} · 무 "
              f"{new.draw:.0%} · {m.away_name} 승 {new.away:.0%}")))
    over = dict(dict(getattr(card, "shape", None) or {}).get("over") or {})
    if over:
        _put(got, Item(id="P2", kind="over",
                       text=("오버 " + " · ".join(
                           f"{k} {float(v):.0%}" for k, v in sorted(
                               over.items(), key=lambda kv: float(kv[0]))))))
    else:
        _none(got, "오버 1.5/2.5/3.5", "총골 분포가 없다")
    old = getattr(card, "prob_before", None)
    if old is not None:
        _put(got, Item(
            id="P3", kind="move",
            text=(f"잠정 → 최종 — {m.home_name} {old.home:.0%}→{new.home:.0%}"
                  f" · 무 {old.draw:.0%}→{new.draw:.0%} · "
                  f"{m.away_name} {old.away:.0%}→{new.away:.0%}")))
    share = dict(dict(getattr(card, "matchup", None) or {}).get("share") or {})
    if share:
        _put(got, Item(id="P4", kind="share",
                       text=("축별 기여 — " + " · ".join(
                           f"{k} {float(v):+.1f}%p" for k, v in share.items()))))
    else:
        _none(got, "축별 기여 분해", "적합 전이라 못 쪼갠다")
    said = layer1._scores(card)
    if said:
        _put(got, Item(id="P5", kind="scores",
                       text=f"예상 스코어 상위 3 — {said}"))
    # 🔴 방향은 **코드가 정한다** — 검열 (u) 가 이것과 대조한다
    _put(got, Item(id="P6", kind="direction",
                   text=f"확률 방향(코드 판정) — {direction_of(card)}"))


def direction_of(card) -> str:
    """🔴🔴 검열 (u) 의 기준 — **최종 확률의 방향**. 사본 금지: `layer1` 이 센다.

    돌려주는 것: 팀 이름 · `무승부 쪽` · `반반`.
    """
    from app.core import layer1
    new = card.our_prob
    if new is None:
        return "모른다"
    side = layer1.dir_side(card)
    if side == "home":
        return str(card.match.home_name or "")
    if side == "away":
        return str(card.match.away_name or "")
    # 🔴 무승부가 둘보다 높으면 `무승부 쪽`, 아니면 `반반`
    if new.draw >= max(new.home, new.away):
        return "무승부 쪽"
    return "반반"
