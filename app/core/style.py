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
    """🔴 한 경기의 축 값 — `num 합 ÷ per`. 못 세면 `None`.

    🔴🔴 **상대 쪽 수도 쓴다**(사용자 결정 2026-10-12 ② 대리 지표):
       `per_side: opponent` · `num_side: opponent` 면 그 칸을 **상대 열**에서 읽는다.
    ⚠️ 왜 필요한가 — PPDA 는 *"상대 패스 몇 개마다 한 번 끊나"* 다. 분모가 **우리**
       패스면 그것은 압박이 아니라 *"우리가 공을 덜 돌렸다"* 를 센다(실측
       2026-10-12: 니스 press 가 패스 많은 경기에서 **내려갔다**).
    🔴 `low_block` 도 같은 꼴이다 — **상대가 어디서 쐈나**가 깊이의 증거다.
    """
    them = 1 - i
    per_key = str(spec.get("per") or "")
    per_i = them if str(spec.get("per_side") or "") == "opponent" else i
    per = dict((st.get(per_key) or ({}, {}))[per_i]).get("n") \
        if per_key in st else None
    if not per:
        return None
    num_i = them if str(spec.get("num_side") or "") == "opponent" else i
    tot = 0.0
    hit = False
    for key, w in dict(spec.get("num") or {}).items():
        if str(key) not in st:
            continue
        said = dict(st[str(key)][num_i]).get("n")
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
# ══════════════════════════════════════════════════════════════════════
# 🔴🔴 **상성·시뮬과 함께 지웠다** — 사용자 지시 2026-10-17
# ══════════════════════════════════════════════════════════════════════
#
#  > 상성이 왜 들어가 있냐?? · **상성 삭제해라** · **시뮬도 삭제해라**
#
#  🔴 아래 함수들은 **상성 축(축0~축3)이 쓰던 부품**이다 — 스타일 6축·무기 표·
#     백분위·창 검사·공격 기여·중심화. 상성 단계를 지우자 **부르는 곳이 0**
#     이 됐다(`tests/test_wiring.py` 가 고아로 잡았다 · #2).



#: 🔴 빠진 선수의 공격 기여가 팀의 이만큼이면 **공격 축 셋**이 꺼진다
OFF_BIG, OFF_SMALL = 0.30, 0.15


def _same_player(name: str, pool: set[str]) -> bool:
    """🔴 ③ — 그 이름이 **평소 XI 안에 있나**.

    ⚠️ 이름 표기가 두 통로에서 갈린다(`Müller` vs `Thomas Müller`). 🔴 그래서
       **성(마지막 토큰)**으로도 맞춘다 — 단, 토큰이 하나뿐인 이름은 **성으로만**
       맞춘다(`Rafael` 이 `Rafael Tolói` 를 잡던 실사고 2026-10-11 과 같은 규칙).
    """
    want = str(name or "").strip().lower()
    if not want:
        return False
    tail = want.split()[-1]
    for one in pool:
        got = str(one or "").strip().lower()
        if not got:
            continue
        if got == want or got.split()[-1] == tail:
            return True
    return False


def _att_share(read, gone: list[str]) -> float:
    """🔴 빠진 선수들이 쥔 **팀 공격 기여(득점+도움) 비중**(0~1).

    🔴 표는 `strategy._att_table` 하나다(사본 금지). ⚠️ 표가 비면 **0** 이 아니라
       그 사실이 비중 0 으로 남고, 호출부가 *"꺼진 무기 없음"* 을 적는다 — 없는
       약화를 지어내지 않는다(#4).
    """
    box = dict(getattr(read, "att_table", None) or {})
    if not box:
        return 0.0
    total = sum(float(v) for v in box.values())
    if total <= 0:
        return 0.0
    # 🔴🔴 **식별자는 둘 꼴이다**(§3 · 2026-10-13) — 신원표를 지난 **선수 id**
    #    이거나, 못 지났으면 `name:<이름>` 이다. 표의 열쇠도 둘 꼴이다(경기별
    #    xG+xA 표는 **id**, 시즌 누계 퇴로는 **이름**). 🔴 그래서 **양쪽을 다**
    #    본다 — 전에는 id 만 넣고 이름 표를 뒤져 **늘 0** 이었다.
    mine = 0.0
    for nm in (gone or []):
        said = str(nm or "")
        if said in box:
            mine += float(box.get(said) or 0.0)
            continue
        want = said[5:] if said.startswith("name:") else said
        if want in box:
            mine += float(box.get(want) or 0.0)
    return max(0.0, min(1.0, mine / total))


#: 🔴 전략 판정이 6축을 어느 쪽으로 미는가 — **임시값**(적합 전)
#  ⚠️ 수를 지어내지 않는다: 방향만 적고 크기는 한 칸(`STRATEGY_STEP`)이다.
STRATEGY_STEP = 0.15
STRATEGY_MOVE: dict[str, dict[str, float]] = {
    "수비 위주": {"low_block": +1, "press": -1, "forward": -1},
    "공격 위주": {"forward": +1, "box_entry": +1, "low_block": -1},
    "로테이션·체력 관리": {"press": -1},
    "squad_turnover": {"press": -1, "forward": -1},
}
