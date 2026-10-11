"""🔴🔴 **축3 — 골 내용 상성**. 사용자 지시 2026-10-10(셋째) §3.

> 골 하나하나를 기록한다(§3-1) → **팀 골 프로필**(§3-2) → **상대성 매칭
> 규칙 T9~T13**(§3-3) → 표본 처리(§3-4).

🔴 이 파일은 **수를 센다** — 규칙의 방향·크기는 `config/tactical_rules.yaml` 이
   들고(사본 금지), 수집은 `app/collect/fotmob.goals_of` 가 한다.
🔴 **표본이 모자라면 확률을 안 움직인다** — `관찰만` 으로 표시하고 그 사실을
   사유에 적는다(§3-4 · #3 조용한 0 금지).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

CONF = "config/tactical_rules.yaml"
#: 🔴 카드가 붙이는 표시 — 적합 못 한 계수를 쓸 때(금지: 표시 없이 사용)
PROVISIONAL = "🔴 **임시값**(적합 전)"
#: 🔴 표본이 모자랄 때의 표시(§3-4)
WATCH_ONLY = "관찰만"


def table() -> dict:
    """🔴 `config/tactical_rules.yaml` — 유형 어휘·문턱·규칙이 거기 있다."""
    from app import rules
    return dict(rules._load(CONF) or {})


def kind_of(goal: dict) -> str:
    """🔴🔴 §3-1 — 골 하나의 **유형**. 못 가리면 `"미상"`.

    돌려주는 것: `own_goal` · `penalty` · `setpiece` · `counter` · `open` · `미상`

    🔴 어휘는 표가 든다(실측 2026-10-10 · 43골). ⚠️ **`situation` 이 없는 골이
       42%** 다 — 그때는 `desc`(`Penalty`·`Own goal`)만 보고 나머지는 `미상` 이다.
       🔴 `미상` 을 `open`(필드골)으로 밀어 넣지 않는다 — 그러면 세트피스 비중이
          조용히 내려간다.
    """
    box = dict(table().get("kinds") or {})
    said = dict(goal or {})
    if said.get("own_goal"):
        return "own_goal"
    sit = str(said.get("situation") or "")
    desc = str(said.get("desc") or "").lower()
    if sit in [str(x) for x in (box.get("penalty") or [])] or "penalty" in desc:
        return "penalty"
    if "own goal" in desc:
        return "own_goal"
    for key in ("setpiece", "counter", "open"):
        if sit and sit in [str(x) for x in (box.get(key) or [])]:
            return key
    return "미상"


def is_header(goal: dict) -> bool:
    """🔴 §3-2 — 헤더 골인가(표기가 있을 때만 참)."""
    want = {str(x) for x in (dict(table().get("kinds") or {})
                             .get("header_shot") or [])}
    return str(dict(goal or {}).get("shot_type") or "") in want


def is_lucky(goal: dict) -> tuple[bool, str]:
    """🔴🔴 §3-1 — **운 섞인 골인가**. `(그렇다, 왜)`.

    > 자책골·PK·**낮은 xG 슈팅(예: 0.05 미만)** 득점은 운 요소로 표시.

    ⚠️ xG 가 **없는 골은 운이라고 하지 않는다** — 모르는 것을 그렇다고 세면
       하위 리그 팀의 공격이 통째로 할인된다(#4 추측 금지).
    """
    box = dict(table().get("luck") or {})
    kind = kind_of(goal)
    if kind in [str(x) for x in (box.get("kinds") or [])]:
        return True, f"{kind}"
    got = dict(goal or {}).get("xg")
    low = float(box.get("low_xg") or 0.05)
    if got is not None and float(got) < low:
        return True, f"xG {float(got):.3f} < {low}"
    return False, ""


def state_of(goal: dict) -> str:
    """🔴 §3-1 — 그 골 **직전**의 경기 상태(득점 팀 기준). 못 세면 `"미상"`.

    돌려주는 것: `앞섬` · `동점` · `뒤짐`
    """
    said = dict(goal or {})
    before = said.get("before")
    if not before or len(tuple(before)) != 2:
        return "미상"
    h, a = (int(x) for x in before)
    mine, theirs = (h, a) if said.get("home") else (a, h)
    return "앞섬" if mine > theirs else ("동점" if mine == theirs else "뒤짐")


def bucket_of(goal: dict) -> str:
    """🔴 §3-2 — 그 골의 **시간대**(`0-30`·`31-60`·`61-90+`). 못 세면 `"미상"`."""
    said = int(dict(goal or {}).get("minute") or 0)
    for row in (table().get("buckets") or []):
        box = dict(row)
        if int(box.get("from") or 0) <= said <= int(box.get("to") or 0):
            return str(box.get("key"))
    return "미상"


@dataclass
class Side:
    """🔴 한 팀의 **득점 쪽 또는 실점 쪽** 프로필(§3-2). ⚠️ 표본 수를 늘 든다."""

    n: int = 0
    by_kind: dict = field(default_factory=dict)
    by_bucket: dict = field(default_factory=dict)
    by_state: dict = field(default_factory=dict)
    header: int = 0
    lucky: int = 0
    xg_sum: float = 0.0
    xg_n: int = 0

    def share(self, box: dict, key: str) -> float | None:
        """🔴 비중 — ⚠️ 표본이 0 이면 **`None`**(0% 가 아니다)."""
        return (float(box.get(key, 0)) / self.n) if self.n else None

    def kind_share(self, key: str) -> float | None:
        return self.share(self.by_kind, key)

    def bucket_share(self, key: str) -> float | None:
        return self.share(self.by_bucket, key)


@dataclass
class Profile:
    """🔴🔴 §3-2 — 그 팀의 **골 프로필**(득점·실점 양쪽) + 경기 흐름."""

    team: str = ""
    matches: int = 0
    scored: Side = field(default_factory=Side)
    conceded: Side = field(default_factory=Side)
    #: 🔴 §3-2 — 선제골 낸 경기의 결과 `{지킴, 무, 역전패}`
    led_first: dict = field(default_factory=dict)
    #: 🔴 §3-2 — 선실점 한 경기의 결과 `{역전승, 무, 패}`
    trailed_first: dict = field(default_factory=dict)
    why: str = ""

    def hold_rate(self) -> float | None:
        """🔴 **리드 유지력** — 선제골 경기 중 이긴 비율. 표본 0 이면 `None`."""
        n = sum(int(v) for v in self.led_first.values())
        return (float(self.led_first.get("지킴", 0)) / n) if n else None

    def comeback_rate(self) -> float | None:
        """🔴 **추격력** — 선실점 경기 중 **지지 않은** 비율. 표본 0 이면 `None`."""
        n = sum(int(v) for v in self.trailed_first.values())
        if not n:
            return None
        got = int(self.trailed_first.get("역전승", 0)) \
            + int(self.trailed_first.get("무", 0))
        return float(got) / n


def profile_of(team_name: str, rows: list[dict]) -> Profile:
    """🔴🔴 §3-2 — **경기별 골 목록 → 팀 골 프로필**.

    `rows` 한 줄 꼴: `{"mine_home": True/False, "goals": [골…]}` —
    `goals` 는 `fotmob.goals_of` 가 돌려준 그 목록이다.

    🔴🔴 **우리 팀이 홈인지는 받는 쪽이 정해 온다**(`mine_home`) — 여기서 이름을
       비교하지 않는다. ⚠️ 신원 계약(3단계)이 *"이름끼리 비교 금지"* 다: 처음에
       여기서 이름을 맞췄다가 그 계약이 빨개졌다(2026-10-10). 🔴 가리는 자리는
       `s2e_matchup` 하나다(그쪽은 팀 **열쇠**를 들고 있다).
    ⚠️ `mine_home` 이 없는 줄은 **건너뛰고 사유에 적는다**(#3).
    """
    got = Profile(team=str(team_name or ""))
    skipped = 0
    for row in (rows or []):
        box = dict(row)
        if box.get("mine_home") is None:
            skipped += 1
            continue
        got.matches += 1
        _one_match(got, list(box.get("goals") or []),
                   mine_home=bool(box.get("mine_home")))
    got.why = (f"경기 {got.matches}건 · 득점 {got.scored.n} · 실점 "
               f"{got.conceded.n}"
               + (f" · ⚠️ 홈/원정을 못 가린 경기 {skipped}건은 건너뛰었다"
                  if skipped else ""))
    return got


def table_of(rows: list[dict]) -> list[dict]:
    """🔴🔴 §3-1 — **골 하나하나의 표**. 긴 카드(§5)가 그대로 적는다.

    한 줄 꼴: `{opp, home, minute, kind, state, bucket, xg, mine, lucky,
    header}` — `mine` 이 참이면 **우리 득점**, 거짓이면 **실점**이다.

    🔴 유형·상태·시간대·운 판정은 **위 함수들 하나씩**이 든다(사본 금지) —
       `profile_of` 가 세는 것과 **같은 함수**라 표와 비중이 어긋나지 않는다.
    ⚠️ `mine_home` 이 없는 줄은 `profile_of` 와 **같이** 건너뛴다.
    """
    out: list[dict] = []
    for row in (rows or []):
        box = dict(row)
        if box.get("mine_home") is None:
            continue
        mine_home = bool(box.get("mine_home"))
        opp = str((box.get("away_name") if mine_home
                   else box.get("home_name")) or "")
        for g in list(box.get("goals") or []):
            mine = bool(g.get("home")) == mine_home
            # 🔴 자책골은 **들어간 쪽**의 실점이다(`_one_match` 와 같은 규칙)
            if g.get("own_goal"):
                mine = not mine
            out.append({
                "opp": opp, "home": mine_home,
                "minute": int(g.get("minute") or 0),
                "kind": kind_of(g), "state": state_of(g),
                "bucket": bucket_of(g),
                "xg": (None if g.get("xg") is None else float(g["xg"])),
                "mine": mine, "lucky": is_lucky(g)[0],
                "header": is_header(g)})
    return out


def _one_match(got: Profile, goals: list[dict], *, mine_home: bool) -> None:
    """🔴 한 경기의 골들을 프로필에 더한다 + 경기 흐름(선제골·선실점)을 센다."""
    first = None
    for g in goals:
        mine = bool(g.get("home")) == mine_home
        # 🔴 **자책골은 상대 득점으로 센다** — 넣은 쪽이 아니라 **들어간 쪽**이다
        if g.get("own_goal"):
            mine = not mine
        side = got.scored if mine else got.conceded
        _add(side, g)
        if first is None:
            first = mine
    if first is None or not goals:
        return
    # 🔴 §3-2 경기 흐름 — 마지막 스코어로 결과를 센다
    last = goals[-1].get("after")
    if not last or len(tuple(last)) != 2:
        return
    h, a = (int(x) for x in last)
    mine_g, theirs = (h, a) if mine_home else (a, h)
    out = "지킴" if mine_g > theirs else ("무" if mine_g == theirs else "역전패")
    if first:
        got.led_first[out] = got.led_first.get(out, 0) + 1
    else:
        said = ("역전승" if mine_g > theirs
                else ("무" if mine_g == theirs else "패"))
        got.trailed_first[said] = got.trailed_first.get(said, 0) + 1


def _add(side: Side, g: dict) -> None:
    side.n += 1
    side.by_kind[kind_of(g)] = side.by_kind.get(kind_of(g), 0) + 1
    side.by_bucket[bucket_of(g)] = side.by_bucket.get(bucket_of(g), 0) + 1
    side.by_state[state_of(g)] = side.by_state.get(state_of(g), 0) + 1
    if is_header(g):
        side.header += 1
    if is_lucky(g)[0]:
        side.lucky += 1
    if g.get("xg") is not None:
        side.xg_sum += float(g["xg"])
        side.xg_n += 1


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §3-3 **상대성 매칭 규칙 T9~T13** — 표가 방향·크기를 든다
# ══════════════════════════════════════════════════════════════════

@dataclass
class Fired:
    """🔴 발동한 규칙 하나 — **왜·얼마나·표본**을 함께 든다."""

    rule: str = ""
    side: str = ""          # 🔴 어느 팀의 무기인가(`home`·`away`)
    text: str = ""
    effect: dict = field(default_factory=dict)
    #: 🔴 §3-4 — 표본이 모자라면 `관찰만` 이고 **확률을 안 움직인다**
    watch_only: bool = False
    why: str = ""

    def moves(self) -> dict:
        """🔴 확률을 움직일 몫 — `관찰만` 이면 **빈 표**다."""
        return {} if self.watch_only else dict(self.effect)


def fire(home: Profile, away: Profile, *, rest: dict | None = None,
         ) -> list[Fired]:
    """🔴🔴 §3-3 — 두 프로필을 맞춰 **T9~T13 을 발동**한다.

    `rest` 는 일정 피로 재료다(`{"home": 휴식일, "away": 휴식일}`) — T10 이 쓴다.

    🔴 **표가 없으면 아무것도 발동하지 않는다**(`fit` 칸이 없는 규칙은 안 쓴다).
    🔴 §3-4 — 그 유형 골이 `min_goals` 미만이면 `watch_only` 다(확률 미반영).
    ⚠️ 비중을 **리그 평균과 비교**해야 더 정확하지만 리그 전체 골 타임라인을 받는
       통로가 없다(실측 2026-10-10). 🔴 그래서 지금은 **두 팀 사이의 비교**로
       발동하고, 그 한계를 사유에 적는다(지어내 메우지 않는다).
    """
    box = table()
    rows = dict(box.get("rules") or {})
    min_n = int(dict(box.get("sample") or {}).get("min_goals") or 5)
    out: list[Fired] = []
    for side, mine, theirs in (("home", home, away), ("away", away, home)):
        out += _t9(rows, side, mine, theirs, min_n)
        out += _t10(rows, side, mine, theirs, min_n, rest or {})
        out += _t11(rows, side, mine, theirs, min_n)
        out += _t12(rows, side, mine, min_n)
        out += _t13(rows, side, mine, theirs, min_n)
    return out


def _fit_of(rows: dict, key: str) -> tuple[dict, str] | None:
    """🔴 그 규칙의 `(이동량, 사유)` — `fit` 칸이 없으면 `None`(안 쓴다)."""
    box = dict(rows.get(key) or {})
    fit = dict(box.get("fit") or {})
    if "provisional" not in fit:
        return None
    said = (f"{PROVISIONAL} — {fit.get('why')}" if fit.get("provisional")
            else f"적합 표본 {fit.get('n')}경기")
    return dict(box.get("effect") or {}), said


def _t9(rows: dict, side: str, mine: Profile, theirs: Profile,
        min_n: int) -> list[Fired]:
    """🔴 T9 — 세트피스 득점 의존 ↔ 상대 세트피스 실점 비중 높음 → 그 팀 λ↑."""
    got = _fit_of(rows, "T9")
    if got is None:
        return []
    eff, why = got
    a = mine.scored.kind_share("setpiece")
    b = theirs.conceded.kind_share("setpiece")
    if a is None or b is None:
        return []
    # 🔴 **둘 다 그 경로가 두드러질 때만** — 한쪽만이면 상성이 아니다
    if not (a >= 0.25 and b >= 0.25):
        return []
    thin = (mine.scored.by_kind.get("setpiece", 0) < min_n
            or theirs.conceded.by_kind.get("setpiece", 0) < min_n)
    return [Fired(rule="T9", side=side, effect=eff, watch_only=thin,
                  text=(f"세트피스 — 내 득점 {a:.0%}"
                        f"({mine.scored.by_kind.get('setpiece', 0)}/"
                        f"{mine.scored.n}) ↔ 상대 실점 {b:.0%}"
                        f"({theirs.conceded.by_kind.get('setpiece', 0)}/"
                        f"{theirs.conceded.n})"),
                  why=why + (f" · {WATCH_ONLY}(표본 {min_n}골 미만)" if thin
                             else ""))]


def _t10(rows: dict, side: str, mine: Profile, theirs: Profile, min_n: int,
         rest: dict) -> list[Fired]:
    """🔴 T10 — 후반 득점 비중 높음 ↔ 상대 후반 실점 많음 **또는** 상대 피로."""
    got = _fit_of(rows, "T10")
    if got is None:
        return []
    eff, why = got
    a = mine.scored.bucket_share("61-90+")
    b = theirs.conceded.bucket_share("61-90+")
    tired = _tired(rest, "away" if side == "home" else "home")
    if a is None or a < 0.40:
        return []
    if not ((b is not None and b >= 0.40) or tired):
        return []
    thin = mine.scored.by_bucket.get("61-90+", 0) < min_n
    said = (f"후반(61분+) — 내 득점 {a:.0%}"
            f"({mine.scored.by_bucket.get('61-90+', 0)}/{mine.scored.n})")
    said += (f" ↔ 상대 후반 실점 {b:.0%}"
             f"({theirs.conceded.by_bucket.get('61-90+', 0)}/"
             f"{theirs.conceded.n})" if b is not None and b >= 0.40 else "")
    said += f" · 상대 {tired}" if tired else ""
    return [Fired(rule="T10", side=side, effect=eff, watch_only=thin,
                  text=said,
                  why=why + (f" · {WATCH_ONLY}(표본 {min_n}골 미만)" if thin
                             else ""))]


def _tired(rest: dict, who: str) -> str:
    """🔴 T10 — 상대가 **일정 피로**인가(이틀 휴식 등). 아니면 빈 글자."""
    got = dict(rest or {}).get(who)
    try:
        days = int(got)
    except (TypeError, ValueError):
        return ""
    return f"휴식 {days}일" if days <= 3 else ""


def _t11(rows: dict, side: str, mine: Profile, theirs: Profile,
         min_n: int) -> list[Fired]:
    """🔴 T11 — 리드 유지력 낮음 ↔ 상대 추격력 높음 → 무승부·역전↑."""
    got = _fit_of(rows, "T11")
    if got is None:
        return []
    eff, why = got
    hold = mine.hold_rate()
    comeback = theirs.comeback_rate()
    if hold is None or comeback is None:
        return []
    if not (hold <= 0.60 and comeback >= 0.40):
        return []
    n_led = sum(int(v) for v in mine.led_first.values())
    n_tr = sum(int(v) for v in theirs.trailed_first.values())
    thin = n_led < 3        # 🔴 흐름 표본은 **경기 수**다(골 수가 아니다)
    # 🔴🔴 **분모를 함께 쓴다**(사용자 지시 2026-10-10 ⑤) — *"'90%(9/10)'처럼
    #    분모를 함께"*. ⚠️ `20%` 만 적으면 1/5 인지 2/10 인지 알 수 없다.
    return [Fired(rule="T11", side=side, effect=eff, watch_only=thin,
                  text=(f"리드 유지력 {hold:.0%}"
                        f"({int(mine.led_first.get('지킴', 0))}/{n_led}"
                        f" · {mine.led_first}) ↔ 상대 추격력 {comeback:.0%}"
                        f"({int(theirs.trailed_first.get('역전승', 0))
                            + int(theirs.trailed_first.get('무', 0))}/{n_tr}"
                        f" · {theirs.trailed_first})"),
                  why=why + (f" · {WATCH_ONLY}(선제골 경기 {n_led}건 < 3)"
                             if thin else ""))]


def _t12(rows: dict, side: str, mine: Profile, min_n: int) -> list[Fired]:
    """🔴 T12 — **운 요소 골 비중**이 크면 공격 폼 할인 / 실점 쪽이면 수비 보정."""
    got = _fit_of(rows, "T12")
    if got is None:
        return []
    eff, why = got
    out: list[Fired] = []
    a = mine.scored.n and (mine.scored.lucky / mine.scored.n)
    if a and a >= 0.30:
        out.append(Fired(
            rule="T12", side=side,
            effect={"form_attack_discount": float(eff.get(
                "form_attack_discount") or 0.0)},
            watch_only=(mine.scored.n < min_n),
            text=(f"운 요소 득점 {a:.0%}({mine.scored.lucky}/{mine.scored.n}) "
                  f"— 공격 폼을 할인한다"),
            why=why))
    b = mine.conceded.n and (mine.conceded.lucky / mine.conceded.n)
    if b and b >= 0.30:
        out.append(Fired(
            rule="T12", side=side,
            effect={"form_defense_credit": float(eff.get(
                "form_defense_credit") or 0.0)},
            watch_only=(mine.conceded.n < min_n),
            text=(f"운 요소 실점 {b:.0%}({mine.conceded.lucky}/"
                  f"{mine.conceded.n}) — 수비를 실제보다 나쁘게 봤을 수 있다"),
            why=why))
    return out


def _t13(rows: dict, side: str, mine: Profile, theirs: Profile,
         min_n: int) -> list[Fired]:
    """🔴 T13 — 헤더 의존 ↔ 상대 공중볼 약점. **자료가 없으면 안 돈다**.

    > (자료 있는 리그만)

    🔴 `needs: [aerial_duel_win_pct]` — 그 칸을 받는 통로가 **없다**(실측
       2026-10-10). ⚠️ 그래서 이 규칙은 **발동하지 않고**, 헤더 비중만 사실로
       남긴다(카드가 그 사실을 적는다 · #3).
    """
    box = dict(rows.get("T13") or {})
    need = [str(x) for x in (box.get("needs") or [])]
    if need:
        return []
    got = _fit_of(rows, "T13")
    if got is None:
        return []
    eff, why = got
    a = mine.scored.n and (mine.scored.header / mine.scored.n)
    if not a or a < 0.25:
        return []
    return [Fired(rule="T13", side=side, effect=eff,
                  watch_only=(mine.scored.header < min_n),
                  text=f"헤더 득점 {a:.0%}({mine.scored.header}/{mine.scored.n})",
                  why=why)]


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §4 **세 축 → 시뮬레이션 입력** · 기여 분해
# ══════════════════════════════════════════════════════════════════

def sim_extras(box: dict, *, axis2: bool = True, axis3: bool = True) -> dict:
    """🔴🔴 **F3** — 시뮬에 줄 것 중 **λ 를 안 미는 것만**: 시간대·상태 배율.

    > 규칙 효과는 **축 안에서 한 번만**. ⑪ 에서 "규칙 λ 를 따로 더하는" 항 삭제.
    > 시간대·경기 상태 배율(축3)은 **시뮬 안에서만**.  — 지시서 2026-10-11 F3

    🔴 그래서 `sim_input` 과 달리 **`lam_*` 을 안 돌려준다** — 규칙이 λ 를 두 번
       미는 길을 아예 끊는다(계약 R4).
    ⚠️ `sim_input` 은 남겨 둔다 — 적합 도구·계약이 규칙 λ 를 따로 재는 데 쓴다.
    """
    got = sim_input(box, lam_home=1.0, lam_away=1.0, axis2=axis2, axis3=axis3)
    return {"late_home": got["late_home"], "late_away": got["late_away"],
            "lead_mul": got["lead_mul"],
            # 🔴 규칙이 **무엇을 했는지**는 그대로 적는다(축이 이미 셌다는 뜻)
            "why": str(got.get("why") or "")}


def sim_input(box: dict, *, lam_home: float, lam_away: float,
              axis2: bool = True, axis3: bool = True) -> dict:
    """🔴🔴 §4 — 상성 묶음(`s2e_matchup` 산출) → **시뮬레이션 인자**.

    돌려주는 것: `{lam_home, lam_away, late_home, late_away, lead_mul, why}`

    🔴 **발동한 규칙만** 쓴다(`관찰만` 은 빼므로 확률이 안 움직인다 · §3-4).
    🔴 λ 상한(±15%)을 지킨다 — 표가 그 수를 든다.
    ⚠️ 상태 배율(`lead_mul`)은 **T11 이 걸렸을 때만** 넣는다. 그 규칙이 바로
       *"리드 유지력 낮음 ↔ 상대 추격력 높음"* 이고, 지시서 §4 가 말한
       *"앞서는 팀·뒤지는 팀의 득점률 변화"* 가 그것이다.
    ⚠️ 배율의 크기(0.85·1.2)는 **임시값**이다 — 적합 전이고 카드가 그것을 적는다.
    """
    _cap_lo, cap_pct = _caps()
    # 🔴🔴 **축2(T1~T6)와 축3(T9~T13)을 함께** 센다 — 상한은 하나다(±15%)
    # 🔴🔴 **축을 하나씩 끌 수 있다**(사용자 지시 2026-10-10 ④ — 기여 분해).
    #    ⚠️ `axis3` 는 T9~T13(골 내용), `axis2` 는 T1~T6(스타일)이다.
    fired = [f for f in [*((box.get("fired") or []) if axis3 else []),
                         *((box.get("fired2") or []) if axis2 else [])]
             if not f.watch_only]
    lam = {"home": float(lam_home), "away": float(lam_away)}
    late = {"home": 0.0, "away": 0.0}
    pct = {"home": 0.0, "away": 0.0}
    said: list[str] = []
    for f in fired:
        eff = dict(f.moves())
        side = str(f.side)
        if eff.get("lambda_own"):
            pct[side] += float(eff["lambda_own"]) * 100.0
            said.append(f"[{f.rule}] {side} λ {float(eff['lambda_own']):+.0%}")
        if eff.get("lambda_opp"):
            # 🔴 T6 처럼 **상대 λ 를 깎는** 규칙이 있다
            other = "away" if side == "home" else "home"
            pct[other] += float(eff["lambda_opp"]) * 100.0
            said.append(f"[{f.rule}] {other} λ "
                        f"{float(eff['lambda_opp']):+.0%}(상대 몫)")
        if eff.get("lambda_own_late"):
            late[side] += float(eff["lambda_own_late"])
            said.append(f"[{f.rule}] {side} 후반 λ "
                        f"{float(eff['lambda_own_late']):+.0%}")
    out_lam = {}
    for side in ("home", "away"):
        cut = max(-cap_pct, min(cap_pct, pct[side]))
        out_lam[side] = round(lam[side] * (1.0 + cut / 100.0), 4)
        if abs(pct[side]) > cap_pct:
            said.append(f"🔴 {side} λ 이동이 상한 ±{cap_pct:.0f}% 로 잘렸다")
    lead_mul = None
    if any(f.rule == "T11" for f in fired):
        # 🔴 §4 — 상태 배율. ⚠️ 크기는 **임시값**이다
        lead_mul = {"leading": 0.85, "trailing": 1.20}
        said.append(f"[T11] 상태 배율 앞섬 ×0.85 · 뒤짐 ×1.20 ({PROVISIONAL})")
    return {"lam_home": out_lam["home"], "lam_away": out_lam["away"],
            "late_home": late["home"], "late_away": late["away"],
            "lead_mul": lead_mul,
            "why": " · ".join(said) or "발동한 규칙이 없다 — λ 를 안 움직인다"}


def _caps() -> tuple[float, float]:
    """🔴 상한 — `strategy.caps` 하나가 든다(사본 금지 · 같은 ±0.5 · ±15%)."""
    from app.core import strategy
    return strategy.caps()

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **기여 분해는 이제 **S3**(`probmodel._share`)가 한다** — ④(2026-10-10)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 여기 있던 `share_of` 를 **지웠다**. 그 함수는 축마다 따로 센 확률을 받아
#     **잔차를 마지막 칸에 몰아** 합을 맞췄다 — 겹치는 효과를 눈가림한 것이다.
#  🔴 지금은 단계를 쌓아서 잰다(`잠정 → +폼 → +전략 → +축2 → +축3`). 차를 이어
#     붙이면 합이 **정확히** 잠정→최종 변화다 — 잔차가 아예 없다.
