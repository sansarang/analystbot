"""🔴🔴 **축2 — 전술 상성(스타일 프로필 6축)**. 사용자 지시 2026-10-10(셋째) §2.

> 스타일 프로필(6축) + 오늘 XI 변화로 **"A의 무기 → B의 약점"**, **"B의 무기 →
> A의 약점"** 두 방향을 각각 판정(규칙 T1~T8).
> 오늘 XI 에서 **무기를 쥔 선수가 빠졌거나 벤치면 그 무기는 꺼진 것**으로 본다.
> 교체 전문 선수(시즌 선발 비율 30% 미만·득점 기여 상위)는 **"후반 무기"** 로
> 따로 표시.

🔴 재료는 **경기 페이지 통계**다(`fotmob.stats_of` · robots 허용 HTML).
🔴 축 정의·규칙·문턱은 `config/tactical_rules.yaml` 이 든다(사본 금지).
⚠️ **지시서가 T1~T8 의 내용을 주지 않았다** — T9~T13 은 글자로 줬다. 그래서
   §2 가 말한 꼴로 **6축을 짝지은 대칭 규칙 여섯**(T1~T6)만 두고 T7·T8 은
   비워 뒀다(지어내지 않는다 · 그 사실이 표에 적혀 있다).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

PROVISIONAL = "🔴 **임시값**(적합 전)"


def _conf() -> dict:
    from app.core import goals
    return dict(goals.table().get("style") or {})


def axes() -> dict:
    """🔴 6축 정의 — 표가 원본이다."""
    return dict(_conf().get("axes") or {})


@dataclass
class Style:
    """🔴 한 팀의 **스타일 프로필**. ⚠️ 못 잰 축은 **없다**(0 이 아니다)."""

    team: str = ""
    n: int = 0
    axis: dict = field(default_factory=dict)
    aerial: float | None = None
    why: str = ""


def profile_of(team: str, rows: list[dict]) -> Style:
    """🔴🔴 §2 — **경기별 통계 → 6축 프로필**.

    `rows` 한 줄: `{"mine_home": bool, "stats": {key: (홈, 원정)}}` —
    `stats` 는 `fotmob.stats_of` 가 돌려준 표다.

    🔴 축은 `표의 num ÷ per` 의 **경기 평균**이다. ⚠️ 분모가 0·없으면 그 경기는
       그 축에서 **빠진다**(0 으로 세면 축이 조용히 내려간다).
    🔴 홈/원정 가림은 **받는 쪽이 정해 온다**(`mine_home`) — 신원 계약(3단계)이
       아래 단계의 이름 비교를 금지한다.
    """
    box = axes()
    got = Style(team=str(team or ""))
    acc: dict[str, list[float]] = {k: [] for k in box}
    aer: list[float] = []
    key_aer = str(_conf().get("aerial_key") or "")
    for row in (rows or []):
        one = dict(row)
        if one.get("mine_home") is None:
            continue
        i = 0 if one["mine_home"] else 1
        st = dict(one.get("stats") or {})
        if not st:
            continue
        got.n += 1
        for name, spec in box.items():
            said = _ratio(st, dict(spec), i)
            if said is not None:
                acc[name].append(said)
        if key_aer in st:
            pct = dict(st[key_aer][i]).get("pct")
            if pct is not None:
                aer.append(float(pct) / 100.0)
    got.axis = {k: round(sum(v) / len(v), 4) for k, v in acc.items() if v}
    got.aerial = round(sum(aer) / len(aer), 4) if aer else None
    miss = [k for k in box if k not in got.axis]
    got.why = (f"경기 {got.n}건 · 축 {len(got.axis)}/{len(box)}"
               + (f" · ⚠️ 못 잰 축 {miss}" if miss else "")
               + (f" · 공중볼 {got.aerial:.0%}" if got.aerial is not None
                  else " · ⚠️ 공중볼 자료 없음(T2·T5·T13 안 돈다)"))
    return got


def _ratio(st: dict, spec: dict, i: int) -> float | None:
    """🔴 한 경기의 축 값 — `num 합 ÷ per`. 못 세면 `None`."""
    per_key = str(spec.get("per") or "")
    per = dict((st.get(per_key) or ({}, {}))[i]).get("n") if per_key in st \
        else None
    if not per:
        return None
    tot = 0.0
    hit = False
    for key, w in dict(spec.get("num") or {}).items():
        if str(key) not in st:
            continue
        said = dict(st[str(key)][i]).get("n")
        if said is None:
            continue
        tot += float(said) * float(w)
        hit = True
    return round(tot / float(per), 5) if hit else None


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §2 **T1~T6 발동** — "내 무기 → 상대 약점" 두 방향
# ══════════════════════════════════════════════════════════════════

@dataclass
class Fired:
    """🔴 발동한 축2 규칙 하나. ⚠️ 꺼진 무기는 `off` 에 적는다."""

    rule: str = ""
    side: str = ""
    text: str = ""
    effect: dict = field(default_factory=dict)
    watch_only: bool = False
    why: str = ""

    def moves(self) -> dict:
        return {} if self.watch_only else dict(self.effect)


def fire(home: Style, away: Style, *, off: dict | None = None) -> list[Fired]:
    """🔴🔴 §2 — 두 프로필을 맞춰 **T1~T6** 을 발동한다.

    `off` 는 **꺼진 무기**다(`{"home": ["direct", …]}`) — 오늘 XI 에서 그 무기를
    쥔 선수가 빠졌으면 그 축의 규칙은 **발동하지 않는다**(§2 둘째 줄).

    🔴 문턱·크기는 표가 든다. ⚠️ 전부 **임시값**이고 사유에 그렇게 적힌다.
    """
    from app.core import goals
    box = goals.table()
    rows = dict(box.get("matchups") or {})
    fit = dict(box.get("matchup_fit") or {})
    if "provisional" not in fit:
        return []           # 🔴 `fit` 칸이 없으면 **쓰지 않는다**
    why0 = (f"{PROVISIONAL} — {fit.get('why')}" if fit.get("provisional")
            else f"적합 표본 {fit.get('n')}경기")
    gap = float(box.get("matchup_gap") or 0.25)
    dead = dict(off or {})
    out: list[Fired] = []
    for side, mine, theirs in (("home", home, away), ("away", away, home)):
        for name, spec in rows.items():
            one = dict(spec)
            a = _axis_of(mine, str(one.get("mine")))
            b = _axis_of(theirs, str(one.get("theirs")))
            if a is None or b is None:
                continue
            if str(one.get("mine")) in [str(x) for x in
                                        (dead.get(side) or [])]:
                continue    # 🔴 §2 — **꺼진 무기는 발동하지 않는다**
            # 🔴 내 축이 상대 짝 축보다 `gap` 이상 높아야 한다
            if b <= 0 or (a - b) / max(b, 1e-6) < gap:
                continue
            out.append(Fired(
                rule=str(name), side=side,
                effect=dict(one.get("effect") or {}),
                watch_only=(mine.n < 3 or theirs.n < 3),
                text=(f"{one.get('mine')} {a:.3f} ↔ 상대 "
                      f"{one.get('theirs')} {b:.3f}"),
                why=f"{one.get('why')} · {why0}"))
    return out


def _axis_of(one: Style, name: str) -> float | None:
    """🔴 그 축 값 — `aerial` 은 따로 들고 있다. 없으면 `None`."""
    if name == "aerial":
        return one.aerial
    got = dict(one.axis or {}).get(name)
    return float(got) if got is not None else None


def off_weapons(read, prof) -> list[str]:
    """🔴🔴 §2 둘째 줄 — **오늘 XI 에서 꺼진 무기**.

    > 오늘 XI 에서 무기를 쥔 선수가 빠졌거나 벤치면 그 무기는 **꺼진 것**으로 본다.

    🔴 지금 셀 수 있는 것은 **핵심 선수(득점+도움 상위)가 명단에서 빠졌나**다 —
       `strategy.read` 가 그 상태를 이미 들고 있다(`key_state`).
    ⚠️ *"어느 선수가 어느 축의 무기인가"* 를 가리는 자료(선수별 크로스·공중볼)는
       받는 통로가 없다. 🔴 그래서 **핵심 선수가 빠지면 공격 쪽 축 셋**
       (`forward`·`box_entry`·`direct`)을 끈다 — 그 범위를 여기 적어 둔다.
    """
    said = dict(getattr(read, "key_state", None) or {})
    gone = [nm for nm, st in said.items() if st in ("명단 제외", "벤치")]
    return ["forward", "box_entry", "direct"] if gone else []


def off_from_vars(varset, side: str) -> tuple[list[str], list[str]]:
    """🔴🔴 **F2** — 배치된 변수에서 **꺼진 무기 · 켜진 무기**.

    > 결장·징계 변수 → 그 선수가 쥔 무기 **꺼짐**, 복귀 변수 → **켜짐**.
    >   — 지시서 2026-10-11 F2

    🔴 유형으로 가린다(`absence`·`def_absence`·`absence_att`·`suspension` → 꺼짐,
       `returning`·`national_duty_return` → 켜짐). ⚠️ *"어느 선수가 어느 축의
       무기인가"* 를 가리는 자료는 **없다**(선수별 크로스·공중볼 통로가 없다) —
       그래서 `off_weapons` 와 **같은 범위**를 쓴다(공격 축 셋). 범위를 여기 적어
       둔다(#4 — 모르는 것을 아는 척하지 않는다).
    """
    OFF = {"absence", "def_absence", "absence_att", "suspension"}
    ON = {"returning", "national_duty_return"}
    gone, back = [], []
    for row in (varset.of("axis2") if varset is not None else []):
        kind = str(getattr(row, "type", "") or "")
        rid = str(getattr(row, "id", "") or "")
        # 🔴 **어느 팀 것인가는 id 의 꼬리로만 본다**(`IR02-home`) — ⚠️ `VarRow` 에
        #    `side` 칸이 없고, `favors`(누구에게 유리한가)로 뒤집어 재면 그것은
        #    **추측**이다(#4). 꼬리가 없으면 **어느 쪽에도 안 붙인다**.
        if not rid.endswith(f"-{side}"):
            continue
        if kind in OFF:
            gone.append(rid)
        elif kind in ON:
            back.append(rid)
    axes = ["forward", "box_entry", "direct"]
    return (axes if gone and not back else []), (axes if back else [])


#: 🔴 전략 판정이 6축을 어느 쪽으로 미는가 — **임시값**(적합 전)
#  ⚠️ 수를 지어내지 않는다: 방향만 적고 크기는 한 칸(`STRATEGY_STEP`)이다.
STRATEGY_STEP = 0.15
STRATEGY_MOVE: dict[str, dict[str, float]] = {
    "수비 위주": {"low_block": +1, "press": -1, "forward": -1},
    "공격 위주": {"forward": +1, "box_entry": +1, "low_block": -1},
    "로테이션·체력 관리": {"press": -1},
    "squad_turnover": {"press": -1, "forward": -1},
}


def adjust(prof: Style, verdict: str) -> Style:
    """🔴🔴 **F2** — 전략 판정으로 **스타일 6축을 조정**한다.

    > 전략(수비 위주·3백 전환 등) → 스타일 6축 조정.  — 지시서 2026-10-11 F2

    🔴 방향만 표에 적고 크기는 **한 칸**(`STRATEGY_STEP`)이다 — 🔴 **임시값**이고
       사유에 그렇게 남는다. ⚠️ 표에 없는 판정이면 **안 건드린다**.
    """
    move = STRATEGY_MOVE.get(str(verdict or ""), {})
    if not move or not prof.axis:
        return prof
    axis = dict(prof.axis)
    said = []
    for key, way in move.items():
        if axis.get(key) is None:
            continue
        axis[key] = float(axis[key]) + way * STRATEGY_STEP
        said.append(f"{key} {way * STRATEGY_STEP:+.2f}")
    if not said:
        return prof
    return Style(team=prof.team, n=prof.n, axis=axis, aerial=prof.aerial,
                 why=(prof.why + f" · 전략 `{verdict}` 조정 {' · '.join(said)}"
                      f"(🔴 임시값)"))


def late_weapons(read) -> list[str]:
    """🔴 §2 마지막 줄 — **후반 무기**(교체 전문 선수 중 득점 기여 상위).

    > 교체 전문 선수(시즌 선발 비율 30% 미만·득점 기여 상위)는 *"후반 무기"* 로
    > 따로 표시.

    🔴 선발 비율은 `strategy.read` 가 이미 셌다(`bench_regulars`).
    ⚠️ *"득점 기여 상위"* 는 `key_state` 에 그 이름이 있는지로 본다(핵심 선수 표가
       득점+도움 상위다).
    """
    rows = [dict(x) for x in (getattr(read, "bench_regulars", None) or [])]
    key = set(dict(getattr(read, "key_state", None) or {}))
    return [x["name"] for x in rows if x.get("name") in key]
