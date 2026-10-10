"""🔴🔴 **확정 라인업에서 전략을 읽는다** — 사용자 지시 2026-10-10(둘째) §2.

> 라인업이 확정되면 *"감독이 오늘 무엇을 하려는가(전략)"* 를 분석하고, 그 결과로
> 승무패·언더오버 확률을 다시 계산한다. 라인업 전 확률은 **잠정**, 확정 라인업
> 반영 확률이 **최종**이다.

이 파일이 하는 것은 **§2-1(코드 사실)** 과 **§2-3(맞대결 양상)** 이다.
⚠️ §2-2(전략 판정)는 LLM 한 번이고 `app/core/stages/s2d_strategy.py` 가 든다 —
   그 판정이 **이 파일의 수치와 반대면 버린다**(같은 §2-2 의 코드 검사).

🔴 **예상 XI 로는 전략을 추론하지 않는다**(§1) — `facts.xi` 가 `확정` 일 때만
   사실을 만든다. ⚠️ 예상 XI 는 우리가 **빈도로 지은 것**이므로 그것으로 전략을
   읽으면 *"평소 그대로"* 가 늘 나온다(동어반복이다).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: 🔴🔴 §2-2 — 전략 **여섯 가지**(지시서가 이름을 그대로 줬다). 늘리지 않는다.
KINDS: tuple[str, ...] = ("공격 위주", "수비 위주", "역습",
                          "로테이션·체력 관리", "실험", "평소 그대로")
#: 🔴 §2-1 — 포지션 **세부 분류**(지시서가 준 여덟 칸)
SLOTS: tuple[str, ...] = ("GK", "CB", "FB/WB", "DM", "CM", "AM", "W", "ST")
#: 🔴 §2-4(앞 지시 §6) — 시즌 선발 비율이 이보다 낮으면 벤치는 **평소 운용**이다
#  ⚠️ 수는 `s5_verify.STARTER_SHARE` 하나다(사본 금지) — 거기서 읽는다.


def starter_share() -> float:
    """🔴 선발 비율 문턱 — 앞 지시 §6 이 정한 30%(원본은 `s5_verify`)."""
    from app.core.stages.s5_verify import STARTER_SHARE
    return float(STARTER_SHARE)


@dataclass
class Fact:
    """🔴 §2-1 사실 하나 — **id 로 가리킨다**(§2-2 의 근거 id 가 이것이다)."""

    id: str
    kind: str
    text: str
    #: 🔴 수치 사실이면 그 수(없으면 `None`) — 코드 검사가 이것을 본다
    value: float | None = None


@dataclass
class TeamRead:
    """🔴 한 팀의 §2-1 묶음. ⚠️ 못 잰 칸은 **`None`** 이다(0 이 아니다)."""

    team: str = ""
    confirmed: bool = False
    formation_now: str = ""
    formation_usual: str = ""
    back_now: int | None = None
    back_usual: int | None = None
    st_now: int | None = None
    st_usual: int | None = None
    changed: int | None = None
    #: 🔴 §2-1 — 자리별 교체(`{슬롯: (나간 이름들, 들어온 이름들)}`)
    swaps: dict = field(default_factory=dict)
    #: 🔴 §2-1 — 공격·수비 기여 변화율(%) · 못 재면 `None`
    da: float | None = None
    dd: float | None = None
    #: 🔴 핵심 선수 상태 — `{이름: "선발"|"벤치"|"명단 제외"}`
    key_state: dict = field(default_factory=dict)
    #: 🔴 교체 주력(선발 비율 30% 미만)의 벤치 — **약화로 읽지 않는다**
    bench_regulars: list = field(default_factory=list)
    #: 🔴 복귀 선수가 선발인가 — `{이름: True/False}`
    returning: dict = field(default_factory=dict)
    facts: list = field(default_factory=list)
    why: str = ""

    def ids(self) -> list[str]:
        return [f.id for f in self.facts]


def back_line(formation: object) -> int | None:
    """🔴 포메이션 글자의 **수비 수**(`4-4-2`→4 · `3-4-3`→3). 못 읽으면 `None`."""
    said = str(formation or "").strip()
    head = said.split("-")[0] if "-" in said else ""
    return int(head) if head.isdigit() and 2 <= int(head) <= 6 else None


def front_line(formation: object) -> int | None:
    """🔴 포메이션 글자의 **최전방 수**(`4-4-2`→2 · `3-4-3`→3). 못 읽으면 `None`."""
    parts = [x for x in str(formation or "").split("-") if x.strip().isdigit()]
    return int(parts[-1]) if len(parts) >= 2 else None


def slot_of(pos: object) -> str:
    """🔴 §2-1 — 포지션 글자 → **여덟 칸** 중 하나. 못 읽으면 빈 글자.

    ⚠️ 출처가 주는 글자가 제각각이다(`DF`·`CB`·`LB`·`DC`·`AMR` …) — 🔴 **글자를
       지어내 늘리지 않고** 실측으로 본 꼴만 적는다(fotmob `usualPlayingPositionId`
       기반 약칭).
    """
    said = str(pos or "").strip().upper().replace(" ", "")
    if not said:
        return ""
    if said.startswith("G"):
        return "GK"
    if said in ("LB", "RB", "LWB", "RWB", "WB", "DL", "DR"):
        return "FB/WB"
    if said in ("CB", "DC", "SW") or said == "DF":
        return "CB"
    if said in ("DM", "CDM", "DMC", "MD"):
        return "DM"
    if said in ("AM", "CAM", "AMC", "MA"):
        return "AM"
    if said in ("LW", "RW", "LM", "RM", "AML", "AMR", "W", "ML", "MR"):
        return "W"
    if said in ("ST", "CF", "FW", "F", "SS"):
        return "ST"
    if said.startswith("M") or said in ("CM", "MC"):
        return "CM"
    if said.startswith("F") or said.startswith("A"):
        return "ST"
    if said.startswith("D"):
        return "CB"
    return ""


def read(ref, facts, *, side: str) -> TeamRead:
    """🔴🔴 §2-1 — 그 팀의 **오늘 명단 vs 평소 XI** 사실을 코드로 센다.

    🔴 **확정 XI 가 아니면 사실을 만들지 않는다**(§1) — `confirmed=False` 로
       돌려주고 사유를 적는다. ⚠️ 그 상태로 §2-2 를 부르면 계약이 빨개진다.
    """
    from app.core.stages import s2b_base as _b
    key = str(getattr(ref, side) if side in ("home", "away") else side)
    name = str(getattr(ref, f"{side}_name", "") or "")
    got = TeamRead(team=key)
    xi = (facts.xi or {}).get(key)
    # 🔴 `XI.state` 는 **영어**다(`confirmed`) — 옮기는 자리는 `layer1.XI_KO`
    #    하나다. ⚠️ 여기서 한국어와 비교했다가 **영원히 거짓**이었다(2026-10-10).
    if xi is None or str(getattr(xi, "state", "") or "") != "confirmed":
        from app.core import layer1 as _l1
        said = str(getattr(xi, "state", "") or "") if xi else ""
        got.why = ("🔴 **확정 XI 전 — 전략 분석 없음**(§1) · 지금 XI 는 "
                   f"`{_l1.XI_KO.get(said, said or '없음')}`")
        return got
    got.confirmed = True
    rows = list((facts.past_xi or {}).get(key) or [])
    usual, how = _b.usual_xi(rows) if rows else ([], "과거 선발이 없다")
    now = _names(xi)
    got.formation_now = str(getattr(xi, "formation", "") or "")
    got.formation_usual = _usual_formation(rows)
    got.back_now = back_line(got.formation_now)
    got.back_usual = back_line(got.formation_usual)
    got.st_now = front_line(got.formation_now)
    got.st_usual = front_line(got.formation_usual)
    pos = dict(facts.player_pos or {})
    got.swaps = _swaps(now, usual, pos)
    got.changed = len([x for x in now if x not in usual]) if usual else None
    got.da, got.dd = _contrib(now, usual, facts)
    got.key_state = _key_state(facts, key, xi)
    got.bench_regulars = _bench_regulars(facts, key, xi)
    got.returning = _returning(facts, key, xi)
    got.facts = _facts_of(got, name=name, how=how)
    got.why = f"평소 XI — {how}"
    return got


def _names(xi) -> list[str]:
    return ([str(p.name) for p in (getattr(xi, "lineup", None) or [])]
            or [str(x) for x in (getattr(xi, "players", None) or [])])


def _usual_formation(rows: list) -> str:
    """🔴 평소 포메이션 — 과거 경기에서 **가장 많이 쓴 것**. 없으면 빈 글자."""
    tally: dict[str, int] = {}
    for xi in rows:
        said = str(getattr(xi, "formation", "") or "").strip()
        if said:
            tally[said] = tally.get(said, 0) + 1
    return max(tally, key=lambda k: (tally[k], k)) if tally else ""


def _swaps(now: list[str], usual: list[str], pos: dict) -> dict:
    """🔴 §2-1 — **자리별 교체**. `{슬롯: {"out": [...], "in": [...]}}`."""
    out: dict[str, dict] = {}
    for nm in usual:
        if nm in now:
            continue
        slot = slot_of(pos.get(nm)) or "?"
        out.setdefault(slot, {"out": [], "in": []})["out"].append(nm)
    for nm in now:
        if nm in usual:
            continue
        slot = slot_of(pos.get(nm)) or "?"
        out.setdefault(slot, {"out": [], "in": []})["in"].append(nm)
    return out


def _contrib(now: list[str], usual: list[str], facts) -> tuple:
    """🔴🔴 §2-1 — **공격·수비 기여 합의 변화율**(ΔA·ΔD). 못 재면 `(None, None)`.

    ⚠️ 지시서는 *"시즌 90분당 득점·도움·슈팅 / 태클·가로채기·클리어"* 를 재료로
       적었다. 🔴 지금 우리가 **실제로 들고 있는 것**은 두 가지다:
         · `facts.standings["key_players"]` — 득점+도움(리그 순위 페이지)
         · `facts.player_value` — 선수 가치(경기 페이지)
       태클·가로채기·클리어는 **아직 받는 통로가 없다**(실측 2026-10-10).
    🔴 그래서 지금은:
         ΔA = 공격 기여(득점+도움) 합의 변화율 — 자료가 **있는 선수만** 센다
         ΔD = 수비 자리(GK·CB·FB/WB·DM) **가치 합**의 변화율
       그리고 이 사실을 카드가 그대로 적는다(#3 조용히 메우지 않는다).
    ⚠️ **없는 수를 0 으로 놓지 않는다** — 둘 다 못 재면 `None` 이고 §2-2 의 코드
       검사는 그 칸을 **안 센다**.
    """
    from app.core import base as _bs
    att = _att_table(facts)
    val = dict(facts.player_value or {})
    pos = dict(facts.player_pos or {})
    if not usual:
        return None, None
    da = None
    if att:
        a_now = sum(float(att.get(nm, 0.0)) for nm in now)
        a_old = sum(float(att.get(nm, 0.0)) for nm in usual)
        if a_old > 0:
            da = _bs.pct_change(a_now, a_old)
    dd = None
    if val:
        back = {"GK", "CB", "FB/WB", "DM"}
        d_now = sum(float(val.get(nm, 0.0)) for nm in now
                    if slot_of(pos.get(nm)) in back)
        d_old = sum(float(val.get(nm, 0.0)) for nm in usual
                    if slot_of(pos.get(nm)) in back)
        if d_old > 0:
            dd = _bs.pct_change(d_now, d_old)
    return da, dd


def _att_table(facts) -> dict:
    """🔴 선수 → **공격 기여**(시즌 득점+도움). 없으면 빈 표.

    🔴 출처는 `facts.standings["key_players"]` 다 — `s2_facts` 가 리그 득점 순위
       페이지에서 받아 둔 것이다(새 통로를 붙이지 않는다).
    ⚠️ 그 표는 **팀마다 상위 2명**뿐이다 — 그래서 ΔA 는 *"핵심 선수가 빠졌나"* 를
       보는 수이고, 명단 전체의 공격력이 아니다. 🔴 그 한계를 카드가 적는다.
    """
    out: dict[str, float] = {}
    box = dict((facts.standings or {}).get("key_players") or {})
    for rows in box.values():
        for one in (rows or []):
            got = dict(one)
            nm = str(got.get("name") or "")
            try:
                out[nm] = float(got.get("value") or 0.0)
            except (TypeError, ValueError):
                continue
    return out


def _key_state(facts, key: str, xi) -> dict:
    """🔴 §2-1 — **핵심 선수**가 선발인가·벤치인가·명단에 없나."""
    rows = dict((facts.standings or {}).get("key_players") or {}).get(key) or []
    now = set(_names(xi))
    bench = {str(x) for x in (getattr(xi, "bench", None) or [])}
    out: dict[str, str] = {}
    for one in rows:
        nm = str(dict(one).get("name") or "")
        if not nm:
            continue
        out[nm] = "선발" if nm in now else ("벤치" if nm in bench else "명단 제외")
    return out


def _bench_regulars(facts, key: str, xi) -> list:
    """🔴🔴 §2-4 — **교체 전문 선수의 벤치는 약화가 아니다**(가시와 세가와).

    > 시즌 선발 비율 **30% 미만** 선수의 벤치는 *"평소 운용"*.

    🔴 비율은 `facts.past_xi` 로 센다(최근 5경기) — ⚠️ 시즌 전체가 아니므로 그
       표본 수를 함께 돌려준다.
    """
    rows = list((facts.past_xi or {}).get(key) or [])
    if not rows:
        return []
    bench = {str(x) for x in (getattr(xi, "bench", None) or [])}
    n = len(rows)
    out = []
    for nm in sorted(bench):
        starts = sum(1 for one in rows if nm in _names(one))
        if n and (starts / n) < starter_share():
            out.append({"name": nm, "starts": starts, "of": n,
                        "share": round(starts / n, 3)})
    return out


def _returning(facts, key: str, xi) -> dict:
    """🔴 §2-1 — **복귀 선수**가 선발인가(새 사실 72시간과 잇는다).

    🔴 복귀 사실은 `variables` 가 아니라 **`facts.missing` 의 반대**로 센다:
       직전 경기에 결장이었는데 오늘 명단에 있으면 복귀다.
    ⚠️ 그 통로가 비면 빈 표다 — 지어내지 않는다.
    """
    gone = {str(getattr(m, "player", "") or "")
            for m in ((facts.missing or {}).get(key) or [])}
    last = (facts.last_xi or {}).get(key)
    was = set(_names(last)) if last is not None else set()
    now = set(_names(xi))
    out: dict[str, bool] = {}
    for nm in sorted(now - was):
        if nm in gone:
            out[nm] = True
    return out


def _facts_of(got: TeamRead, *, name: str, how: str) -> list:
    """🔴🔴 §2-1 → **사실 목록**(id 로 가리킨다 · §2-2 의 근거가 이것이다)."""
    out: list[Fact] = []

    def add(kind: str, text: str, value: float | None = None) -> None:
        out.append(Fact(id=f"L{len(out) + 1}", kind=kind, text=text,
                        value=value))

    if got.formation_now and got.formation_usual \
            and got.formation_now != got.formation_usual:
        add("formation", f"{name} 포메이션 {got.formation_usual}→"
                         f"{got.formation_now}",
            float((got.back_now or 0) - (got.back_usual or 0)))
    elif got.formation_now:
        add("formation", f"{name} 포메이션 {got.formation_now}(평소와 같다)", 0.0)
    if got.back_now is not None and got.back_usual is not None \
            and got.back_now != got.back_usual:
        add("backline", f"{name} 수비 {got.back_usual}백→{got.back_now}백",
            float(got.back_now - got.back_usual))
    if got.st_now is not None and got.st_usual is not None \
            and got.st_now != got.st_usual:
        add("front", f"{name} 최전방 {got.st_usual}명→{got.st_now}명",
            float(got.st_now - got.st_usual))
    if got.changed is not None:
        add("rotation", f"{name} 평소 XI 대비 바뀐 자리 {got.changed}개",
            float(got.changed))
    if got.da is not None:
        add("delta_att", f"{name} 공격 기여 {got.da:+.0f}%(핵심 선수 기준)",
            float(got.da))
    if got.dd is not None:
        add("delta_def", f"{name} 수비 자리 가치 {got.dd:+.0f}%", float(got.dd))
    for nm, said in sorted(got.key_state.items()):
        add("key_player", f"{name} 핵심 선수 {nm} — {said}")
    for one in got.bench_regulars:
        box = dict(one)
        add("bench_regular",
            f"{name} {box['name']} 벤치 — **평소 운용**"
            f"(최근 {box['of']}경기 중 선발 {box['starts']}회 · "
            f"{box['share']:.0%} < {starter_share():.0%})")
    for nm in sorted(got.returning):
        add("returning", f"{name} {nm} 복귀 — 오늘 명단에 있다")
    for slot, box in sorted(got.swaps.items()):
        said = dict(box)
        if said.get("out") or said.get("in"):
            add("swap", f"{name} {slot} 자리 — 빠짐 {said.get('out') or []} · "
                        f"들어옴 {said.get('in') or []}")
    return out


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §2-3 **맞대결 양상** — 두 전략의 조합(코드가 정한다)
# ══════════════════════════════════════════════════════════════════

def shape_of(home: str, away: str, *, home_name: str = "홈",
             away_name: str = "원정") -> str:
    """🔴 §2-3 — 두 팀 전략 조합으로 **경기 양상** 한 줄. 못 정하면 빈 글자.

    > 공격 vs 잠그기 / 둘 다 잠그기 / 둘 다 공격 / 한쪽 로테이션.
    """
    a, b = str(home or ""), str(away or "")
    if not (a and b):
        return ""
    lock, att = "수비 위주", "공격 위주"
    rot = "로테이션·체력 관리"
    if a == lock and b == lock:
        return "둘 다 잠그기"
    if a == att and b == att:
        return "둘 다 공격"
    if a == att and b == lock:
        return f"{home_name} 공격 vs {away_name} 잠그기"
    if a == lock and b == att:
        return f"{away_name} 공격 vs {home_name} 잠그기"
    if rot in (a, b):
        who = home_name if a == rot else away_name
        return f"{who} 로테이션"
    return f"{a} vs {b}"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §3-2 **전략 → 확률 이동량** — 표가 원본이다
# ══════════════════════════════════════════════════════════════════

CONF = "config/strategy_effects.yaml"
#: 🔴 카드가 붙이는 표시 — 적합 못 한 계수를 쓸 때(§3-2 마지막 줄)
PROVISIONAL = "🔴 **임시값**(적합 전)"


def effects() -> dict:
    """🔴 `config/strategy_effects.yaml` — 방향은 지시서, 크기는 표가 든다."""
    from app import rules
    return dict(rules._load(CONF) or {})


def caps() -> tuple[float, float]:
    """🔴 §3-2 — `(로그 오즈 상한, λ 배율 상한%)`. 표가 없으면 지시서의 수."""
    box = dict(effects().get("caps") or {})
    return float(box.get("logodds") or 0.5), float(box.get("lambda_pct") or 15.0)


def move_of(said: str) -> tuple[dict, str]:
    """🔴🔴 §3-2 — 그 전략의 **이동량**. `(이동 표, 사유)`.

    못 찾으면 `({}, 사유)` 이고 **확률을 움직이지 않는다**(§3-2 금지: *"적합 없는
    계수를 표시 없이 사용"* — 우리는 **표시하거나 안 쓴다**).
    """
    box = dict(effects().get("effects") or {}).get(str(said or ""))
    if not box:
        return {}, f"🔴 `{said}` 의 이동량이 표에 없다 — 확률을 안 움직인다"
    fit = dict(box.get("fit") or {})
    if "provisional" not in fit:
        # 🔴 `fit` 칸이 없으면 **쓰지 않는다** — 적합 상태를 모르는 계수다
        return {}, f"🔴 `{said}` 에 `fit` 칸이 없다 — 확률을 안 움직인다"
    said_why = (f"{PROVISIONAL} — {fit.get('why')}" if fit.get("provisional")
                else f"적합 표본 {fit.get('n')}경기")
    return {k: float(v) for k, v in box.items() if k != "fit"}, said_why


def lambda_from_contrib(da: float | None, dd: float | None
                        ) -> tuple[float, float, str]:
    """🔴 §3-2 — `(그 팀 λ 배율, 상대 λ 배율, 사유)`. 못 재면 `(0, 0, 사유)`.

    > ΔA·ΔD와 2-3 조합으로 두 팀 λ를 움직인다.
    """
    box = dict(effects().get("contrib") or {})
    fit = dict(box.get("fit") or {})
    if "provisional" not in fit:
        return 0.0, 0.0, "🔴 `contrib.fit` 칸이 없다 — λ 를 안 움직인다"
    a = float(box.get("da_to_lambda_own") or 0.0)
    d = float(box.get("dd_to_lambda_opp") or 0.0)
    own = (float(da) / 100.0) * a if da is not None else 0.0
    opp = (float(dd) / 100.0) * d if dd is not None else 0.0
    said = []
    if da is not None:
        said.append(f"ΔA {da:+.0f}% × {a} → 자기 λ {own:+.1%}")
    if dd is not None:
        said.append(f"ΔD {dd:+.0f}% × {d} → 상대 λ {opp:+.1%}")
    why = (" · ".join(said) or "ΔA·ΔD 를 둘 다 못 쟀다")
    if fit.get("provisional"):
        why += f" · {PROVISIONAL}"
    return own, opp, why


def total_shift(plan: object, facts: object) -> tuple[float | None, str]:
    """🔴🔴 §3-2 — **전략·ΔA·ΔD → 이 경기 총골 기준의 λ 이동**. `(새 기준, 사유)`.

    > 총골: **ΔA·ΔD와 2-3 조합으로 두 팀 λ를 움직인다**(총골 모델 지시서의 λ 배율).
    > 경기당 총 이동 상한은 … **λ ±15%**.

    🔴 기준은 `facts.standings["match_total_baseline"]`(두 팀 경기당 총골의 평균)
       하나다 — 새 기준선을 만들지 않는다.
    ⚠️ **상한을 지킨다**(`caps.lambda_pct`) — 전략 둘과 ΔA·ΔD 가 겹쳐도 그 안이다.
    🔴 기준이 없으면 `(None, 사유)` 이고 **아무것도 바꾸지 않는다**.
    """
    box = dict(getattr(facts, "standings", None) or {})
    base = box.get("match_total_baseline")
    if base is None:
        return None, "🔴 이 경기 총골 기준이 없다 — λ 를 안 움직인다"
    if str(getattr(plan, "audit", "") or "") != "통과":
        return float(base), ("전략 판정이 없다(또는 버렸다) — λ 를 안 움직인다")
    _cap_lo, cap_pct = caps()
    said: list[str] = []
    pct = 0.0
    for line in (getattr(plan, "lines", None) or []):
        one, why = move_of(str(getattr(line, "strategy", "")))
        if not one:
            continue
        # 🔴 두 팀 λ 가 **합쳐 총골**이다 — 자기 λ 와 상대 λ 를 둘 다 더한다
        step = float(one.get("lambda_own") or 0.0) \
            + float(one.get("lambda_opp") or 0.0)
        if step:
            pct += step * 50.0        # ⚠️ 두 팀 몫이므로 절반씩 센다(%)
            said.append(f"{getattr(line, 'side', '?')} `"
                        f"{getattr(line, 'strategy', '')}` λ {step:+.0%} · {why}")
    return _apply(base, pct, said, cap_pct)


def _apply(base: float, pct: float, said: list[str], cap_pct: float
           ) -> tuple[float, str]:
    """🔴 상한을 걸고 기준을 움직인다 — 잘렸으면 그 사실을 사유에 적는다."""
    cut = max(-cap_pct, min(cap_pct, pct))
    out = round(float(base) * (1.0 + cut / 100.0), 3)
    why = (f"총골 기준 {base} → **{out}**({cut:+.1f}%)"
           + (f" · 🔴 상한 ±{cap_pct:.0f}% 로 **잘렸다**(원래 {pct:+.1f}%)"
              if abs(pct) > cap_pct else "")
           + (" · " + " / ".join(said) if said else " · 움직일 것이 없다"))
    return out, why


def contrib_shift(read_home: object, read_away: object) -> tuple[float, str]:
    """🔴 §3-2 — **ΔA·ΔD 가 더하는 총골 몫(%)**. `(퍼센트, 사유)`.

    🔴 계수는 `contrib` 표가 들고, 그 표가 `provisional` 이면 사유에 **임시값**이
       적힌다(`lambda_from_contrib` 하나가 그 계산을 한다 · 사본 금지).
    """
    out, said = 0.0, []
    for one, other in ((read_home, read_away), (read_away, read_home)):
        own, opp, why = lambda_from_contrib(getattr(one, "da", None),
                                            getattr(one, "dd", None))
        if own or opp:
            out += (own + opp) * 50.0
            said.append(why)
    return out, (" / ".join(said) or "ΔA·ΔD 를 못 쟀다")
