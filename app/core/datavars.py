"""🔴🔴 **받은 자료에서 변수를 만든다** — 사용자 지시 2026-10-18.

> 선수 능력치, 갈래, **우리가 받은자료에서 변수 추가할것**
> **가나다 전부 변수에 닿게**

## 🔴 왜 생겼나 — 실측 2026-10-18(캔자스 재분석)
변수 **11개 중 3개**만 확률을 밀었다. 가장 센 사실들이 전부 버려졌다:
```
S02       맞대결 10경기 6승          → 자리 V5·hypo
S03       홈 이점 +16.8%p            → 맥락 전용으로 내려갔다
IR13-away 원정 이동 1,464km          → 자리 V3·hypo
선발 22명 능력치                      → 갈래 판정에만 쓰이고 변수가 아니다
순위 8칸 · 구장·날씨 · 선수 가치       → 변수 0개
```
🔴 그래서 **이미 들어오는 자료로 변수를 만든다**(새 통신 0 · LLM 0).

## 🔴 잠금 넷
  ① 손값은 **`config/datavars.yaml` 하나**다 — 코드에 박지 않는다(#1).
  ② 갈래 이름·지표는 **`config/ability.yaml` 이 든다** — 여기서 다시 적지
     않는다(사본 금지). `ability.branch_table()` 로 받는다.
  ③ 능력치 수는 `core/ability` 에서 **멈춘다** — 이 파일은 그 함수를 부르고
     **부등호와 글자**만 만든다(절대규칙 5 의 결).
  ④ **못 쟀으면 변수를 만들지 않는다** — 사유를 이름으로 남긴다(#3).

⚠️ `LLM` 을 부르지 않는다 — 사용자 지시 2026-10-18(*"llm 은 서치용"*).
"""
from __future__ import annotations

import logging

from app.core.schema import Facts, MatchRef, Variable
from app.core.state import RunState

logger = logging.getLogger(__name__)

#: 🔴 ① 손값이 사는 곳(사람이 고친다 · §13-7)
CONF = "config/datavars.yaml"

#: 🔴 못 쟨 칸 글자 — 카드·사유가 같은 글자를 쓴다
NONE_MARK = "⬜"


def _load() -> dict:
    from app import rules
    return dict(rules._load(CONF) or {})


def _box(name: str) -> dict:
    return dict(_load().get(name) or {})


def _num(box: dict, key: str) -> float | None:
    """🔴 손값 하나 — **표에 없으면 `None`** 이다(코드에 기본값을 두지 않는다).

    ⚠️ 계약 DV1 이 *"손값이 코드에 박혔나"* 를 글자로 센다 — 기본값도 손값이다.
    """
    try:
        return float(box.get(key))
    except (TypeError, ValueError):
        return None


def _name(ref: MatchRef, key: str) -> str:
    for side in ("home", "away"):
        if str(getattr(ref, side, "") or "") == str(key):
            return str(getattr(ref, f"{side}_name", "") or key)
    return str(key)


def _key(ref: MatchRef, side: str) -> str:
    return str(getattr(ref, side, "") or "")


def _var(rid: str, kind: str, ref: MatchRef, side: str, claim: str, *,
         goals: str = "none") -> Variable:
    """🔴 변수 하나 — **주어는 `side` 팀**이고 `favors` 가 그 쪽이다.

    ⚠️ 무게는 `s5_verify` 의 그 수와 같게 `0.7`(soft)이다 — 새 수를 짓지
       않는다. 크기(±5%)는 λ 보정표가 든다.
    """
    key = _key(ref, side)
    return Variable(
        id=rid, type=kind, subject=key,
        favors=(side if side in ("home", "away") else "both"),  # type: ignore[arg-type]
        goals=(goals if goals in ("up", "down", "none") else "none"),  # type: ignore[arg-type]
        target=f"{kind}:{rid}", hardness="soft", weight=0.7,
        claim=claim, quote=claim, doc_ids=[], from_rule=rid)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 가. **선수 능력치** — A1 선발 합 · A2 결장 자리 · A3 자리별 쏠림
# ══════════════════════════════════════════════════════════════════
#
#  재료 — `ability.squad_of`(선발 백분위) · `ability.side_pct`(자리 묶음) ·
#         `facts.missing`(결장) · `facts.last_xi`(직전 선발)
#  ⚠️ **벤치는 못 받는다** — `XI.bench` 가 이름 글자뿐이라 선수 번호가 없다.
#     그 사실을 사유에 적는다(지어내지 않는다).


def _all_pct(facts, ref, side: str, box: dict) -> tuple[float | None, int, str]:
    """🔴 그 팀 **선발 전체**의 평균 백분위. `(값, 인원, 사유)`.

    🔴 자리를 안 가린다 — `ability.side_pct` 를 **빈 규칙**으로 부른다(그
       함수가 `pos`/`flank` 빈 목록을 *"안 가린다"* 로 읽는다 · 사본 금지).
    """
    from app.core import ability as _ab
    rule = {"pos": [], "flank": [],
            "traits": sorted({t for r in dict(_ab.branch_table()).values()
                              for t in (r.get("traits") or [])})}
    return _ab.side_pct(facts, ref, side, box, rule)


def from_ability(ref: MatchRef, facts: Facts, box: dict, *,
                 state: RunState) -> list[Variable]:
    """🔴🔴 **가** — 능력치에서 변수 셋(A1·A2·A3). `[Variable]`."""
    from app.core import ability as _ab
    out: list[Variable] = []
    cf = _box("ability")
    if not box:
        state.note(f"가 능력치 변수 — {NONE_MARK} 능력치를 한 명도 못 받았다")
        return out
    # ── A1 선발 평균 백분위
    h, nh, why_h = _all_pct(facts, ref, "home", box)
    a, na, why_a = _all_pct(facts, ref, "away", box)
    low, gap = _num(cf, "squad_min"), _num(cf, "squad_gap")
    if low is None or gap is None:
        state.note(f"가 A1 — {NONE_MARK} 문턱 표가 없다(`{CONF}`)")
    elif h is None or a is None:
        state.note(f"가 A1 — {NONE_MARK} 못 쟀다(홈 {why_h} · 원정 {why_a})")
    elif nh < low or na < low:
        state.note(f"가 A1 — 홈 {nh}명 ↔ 원정 {na}명 · 한쪽이 {low}명 미만이라 "
                   "평균이 몇 사람에 휘둘린다(안 센다)")
    elif abs(h - a) < gap:
        state.note(f"가 A1 — 홈 {h:.3f} ↔ 원정 {a:.3f} · 차 {abs(h - a):.3f} "
                   f"< 문턱 {gap:g}(안 센다)")
    else:
        side = "home" if h > a else "away"
        out.append(_var("AB1", "squad_ability", ref, side,
                        f"{_name(ref, _key(ref, side))} 선발 능력치 평균이 높다 "
                        f"— 홈 **{h:.2f}**({nh}명) ↔ 원정 **{a:.2f}**({na}명) · "
                        f"차 {abs(h - a):.2f}(문턱 {gap:g}) · ⚠️ 벤치는 번호가 "
                        "없어 못 받았다"))
        state.note(f"가 A1 **발동** — {side} · 홈 {h:.3f} ↔ 원정 {a:.3f}")
    # ── A2 결장 자리의 능력치 손실
    out += _absence_quality(ref, facts, box, state=state)
    # ── A3 자리별 쏠림
    tilt_gap, lead = _num(cf, "tilt_gap"), _num(cf, "tilt_lead")
    if tilt_gap is None or lead is None:
        state.note(f"가 A3 — {NONE_MARK} 문턱 표가 없다(`{CONF}`)")
        return out
    won: dict[str, list[str]] = {"home": [], "away": []}
    for kind, rule in dict(_ab.branch_table()).items():
        hh, n1, _w1 = _ab.side_pct(facts, ref, "home", box, rule)
        aa, n2, _w2 = _ab.side_pct(facts, ref, "away", box, rule)
        if hh is None or aa is None or n1 < _ab.branch_min() \
                or n2 < _ab.branch_min() or abs(hh - aa) < tilt_gap:
            continue
        won["home" if hh > aa else "away"].append(str(kind))
    n_h, n_a = len(won["home"]), len(won["away"])
    if abs(n_h - n_a) < lead:
        state.note(f"가 A3 — 쏠린 자리 홈 {n_h}곳 ↔ 원정 {n_a}곳 · 차가 "
                   f"{lead} 미만이다(안 센다)")
    else:
        side = "home" if n_h > n_a else "away"
        said = " · ".join(won[side]) or "?"
        out.append(_var("AB3", "squad_ability", ref, side,
                        f"{_name(ref, _key(ref, side))} 자리별 능력치 쏠림 — "
                        f"{len(won[side])}곳에서 앞선다(홈 {n_h} ↔ 원정 {n_a} · "
                        f"문턱 차 {tilt_gap:g}) · 앞선 자리 {said}"))
        state.note(f"가 A3 **발동** — {side} · 홈 {n_h}곳 ↔ 원정 {n_a}곳")
    return out


def _absence_quality(ref: MatchRef, facts: Facts, box: dict, *,
                     state: RunState) -> list[Variable]:
    """🔴 **A2** — 빠진 선수 백분위 ↔ 오늘 선발 평균의 차. `[Variable]`.

    🔴 *"몇 명 빠졌다"*(`IR02`)와 다르다 — **누가** 빠졌나를 센다.
    ⚠️ 빠진 선수의 백분위가 없으면(선수 페이지를 못 받았다) **안 센다**.
    """
    from app.core import ability as _ab
    cf = _box("ability")
    gap = _num(cf, "absence_gap")
    out: list[Variable] = []
    if gap is None:
        state.note(f"가 A2 — {NONE_MARK} 문턱 표가 없다(`{CONF}`)")
        return out
    said_book = dict(_ab.pid_book(facts, ref) or {})
    for side in ("home", "away"):
        key = _key(ref, side)
        gone = [str(getattr(m, "name", "") or "")
                for m in list(dict(facts.missing or {}).get(key) or [])]
        gone = [x for x in gone if x]
        if not gone:
            state.note(f"가 A2 `{side}` — 결장 0명(안 센다)")
            continue
        mine, _why = _ab.squad_of(facts, ref, side)
        traits = sorted({t for r in dict(_ab.branch_table()).values()
                         for t in (r.get("traits") or [])})
        now = [v for v in (_ab._pct_of(p, traits) for p in mine)
               if v is not None]
        if not now:
            state.note(f"가 A2 `{side}` — {NONE_MARK} 오늘 선발 백분위가 없다")
            continue
        base = sum(now) / len(now)
        hits: list[tuple[str, float]] = []
        for nm in gone:
            pid = said_book.get(nm)
            one = dict(box.get(str(pid)) or {}) if pid else {}
            val = _ab._pct_of(one, traits) if one else None
            if val is not None:
                hits.append((nm, float(val)))
        if not hits:
            state.note(f"가 A2 `{side}` — {NONE_MARK} 빠진 {len(gone)}명의 "
                       "백분위를 못 받았다(선수 페이지를 안 열었다)")
            continue
        top = max(hits, key=lambda x: x[1])
        if top[1] - base < gap:
            state.note(f"가 A2 `{side}` — 빠진 최고 {top[0]} {top[1]:.3f} ↔ "
                       f"오늘 선발 평균 {base:.3f} · 차가 {gap:g} 미만(안 센다)")
            continue
        other = "away" if side == "home" else "home"
        out.append(_var(f"AB2-{side}", "absence_quality", ref, other,
                        f"{_name(ref, key)} 결장 **품질 손실** — 빠진 "
                        f"{top[0]} 백분위 **{top[1]:.2f}** 가 오늘 선발 평균 "
                        f"{base:.2f} 보다 {top[1] - base:.2f} 높다"
                        f"(문턱 {gap:g} · 결장 {len(gone)}명 중 백분위를 받은 "
                        f"{len(hits)}명)"))
        state.note(f"가 A2 `{side}` **발동** — {top[0]} {top[1]:.3f}")
    return out


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 나. **갈래** — B1 코드가 세운 갈래 · B2 가린 갈래 수
# ══════════════════════════════════════════════════════════════════
#
#  🔴 **LLM 주장이 없어도 돈다** — 종전 `branchjudge` 1단은 ⑤-b2 가 낸 주장
#     (`SL*`)이 있어야 돌았다. 그 LLM 을 지웠으므로(지시 2026-10-18) 갈래를
#     **코드가 세운다**: 표의 갈래마다 `ability.judge_branch` 로 가린다.
#  ⚠️ 가려지지 않은 갈래는 **변수를 만들지 않는다**(사유만 남긴다).


def from_branches(ref: MatchRef, facts: Facts, box: dict, *,
                  state: RunState) -> list[Variable]:
    """🔴🔴 **나** — 갈래에서 변수(B1 갈래별 · B2 묶음). `[Variable]`."""
    from app.core import ability as _ab
    out: list[Variable] = []
    if not box:
        state.note(f"나 갈래 변수 — {NONE_MARK} 능력치가 없다")
        return out
    cf = _box("branches")
    want = [str(x) for x in (cf.get("use") or [])]
    table = dict(_ab.branch_table())
    kinds = [k for k in table if not want or str(k) in want]
    won = {"home": 0, "away": 0}
    for kind in kinds:
        cmp_, why = _ab.judge_branch(str(kind), facts, ref, box)
        if cmp_ not in (">", "<"):
            state.note(f"나 B1 `{kind}` — {NONE_MARK} 안 가려졌다 · {why[:110]}")
            continue
        side = "home" if cmp_ == ">" else "away"
        won[side] += 1
        out.append(_var(f"BR-{len(out) + 1}", "branch_numbers", ref, side,
                        f"갈래 `{kind}` — {_name(ref, _key(ref, side))} 쪽이 "
                        f"낫다(`{cmp_}`) · {why[:160]}"))
        state.note(f"나 B1 `{kind}` **발동** — {side} `{cmp_}`")
    lead = _num(cf, "count_lead")
    if lead is None:
        state.note(f"나 B2 — {NONE_MARK} 문턱 표가 없다(`{CONF}`)")
        return out
    if abs(won["home"] - won["away"]) < lead:
        state.note(f"나 B2 — 가린 갈래 홈 {won['home']} ↔ 원정 {won['away']} · "
                   f"차가 {lead} 미만이다(안 센다)")
        return out
    side = "home" if won["home"] > won["away"] else "away"
    out.append(_var("BR0", "branch_numbers", ref, side,
                    f"{_name(ref, _key(ref, side))} 가 **갈래 묶음**에서 앞선다 "
                    f"— 가려진 갈래 홈 {won['home']}개 ↔ 원정 {won['away']}개"
                    f"(문턱 차 {lead} · 전체 {len(kinds)}갈래)"))
    state.note(f"나 B2 **발동** — {side} · 홈 {won['home']} ↔ 원정 {won['away']}")
    return out


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 다. **받고 있는데 변수가 안 서던 자료** — C3·C4·C6·C7
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ C1(순위 동기)은 `s4c_leagueread` 가 이미 만든다 — **배선**이 할 일이다.
#  ⚠️ C2(구장·날씨)는 `s5_verify` 의 `IR15` 가 만든다.
#  ⚠️ C5(감독)는 **자료가 이름뿐**이라 못 만든다 — 사유로 남긴다(지어내지
#     않는다 · 교체 여부는 기사에만 있다).


def from_facts(ref: MatchRef, facts: Facts, *,
               state: RunState) -> list[Variable]:
    """🔴🔴 **다** — 받은 사실에서 변수(C3·C4·C6·C7). `[Variable]`."""
    out: list[Variable] = []
    cf = _box("facts")
    out += _squad_value(ref, facts, cf, state=state)
    out += _state_rate(ref, facts, cf, state=state)
    out += _formation_change(ref, facts, cf, state=state)
    out += _goal_spread(ref, facts, cf, state=state)
    # 🔴 C5 — 자료가 **이름뿐**이다(#3 조용한 0 금지)
    said_c = dict(facts.coach or {})
    state.note(f"다 C5 감독 — {NONE_MARK} 변수를 안 만든다(받은 것은 이름 "
               f"{len(said_c)}곳뿐 · 교체·발언은 기사에만 있다)")
    return out


def _squad_value(ref: MatchRef, facts: Facts, cf: dict, *,
                 state: RunState) -> list[Variable]:
    """🔴 **C3** — 두 팀 **선발 가치 합**의 비. `[Variable]`."""
    book = {str(k): float(v) for k, v in dict(facts.player_value or {}).items()
            if v}
    if not book:
        state.note(f"다 C3 선수 가치 — {NONE_MARK} 받은 가치가 없다")
        return []
    low, want = _num(cf, "value_min"), _num(cf, "value_ratio")
    if low is None or want is None:
        state.note(f"다 C3 — {NONE_MARK} 문턱 표가 없다(`{CONF}`)")
        return []
    got: dict[str, tuple[float, int]] = {}
    for side in ("home", "away"):
        xi = dict(facts.xi or {}).get(_key(ref, side))
        names = [str(x) for x in (getattr(xi, "players", None) or [])]
        vals = [book[n] for n in names if n in book]
        got[side] = (sum(vals), len(vals))
    (vh, nh), (va, na) = got["home"], got["away"]
    if nh < low or na < low:
        state.note(f"다 C3 — 가치를 가진 선발 홈 {nh}명 ↔ 원정 {na}명 · "
                   f"한쪽이 {low}명 미만이다(안 센다)")
        return []
    if not vh or not va:
        state.note(f"다 C3 — {NONE_MARK} 한쪽 합이 0 이다(홈 {vh:g} ↔ 원정 {va:g})")
        return []
    ratio = (vh / va) if vh >= va else (va / vh)
    if ratio < want:
        state.note(f"다 C3 — 가치 합 홈 {vh:,.1f} ↔ 원정 {va:,.1f} · 비 "
                   f"{ratio:.2f} < 문턱 {want:g}(안 센다)")
        return []
    side = "home" if vh > va else "away"
    state.note(f"다 C3 **발동** — {side} · 비 {ratio:.2f}")
    return [_var("DV3", "squad_value", ref, side,
                 f"{_name(ref, _key(ref, side))} 선발 **가치 합**이 크다 — "
                 f"홈 {vh:,.1f} ↔ 원정 {va:,.1f}(비 **{ratio:.2f}배** · "
                 f"문턱 {want:g} · 가치를 가진 선발 홈 {nh}명 ↔ 원정 {na}명)")]


def _state_rate(ref: MatchRef, facts: Facts, cf: dict, *,
                state: RunState) -> list[Variable]:
    """🔴 **C4** — 지고 있을 때 **되돌리는 힘**(`뒤짐` 칸 득점 배율). `[Variable]`."""
    box = dict(facts.state_rates or {})
    if not box:
        state.note(f"다 C4 상태 배율 — {NONE_MARK} 표가 없다(리그 표가 비었다)")
        return []
    want = _num(cf, "state_gap")
    if want is None:
        state.note(f"다 C4 — {NONE_MARK} 문턱 표가 없다(`{CONF}`)")
        return []
    got: dict[str, float | None] = {}
    for side in ("home", "away"):
        one = dict(box.get(side) or box.get(_key(ref, side)) or {})
        row = dict(one.get("뒤짐") or one.get("behind") or {})
        try:
            got[side] = float(row.get("득") if "득" in row else row.get("gf"))
        except (TypeError, ValueError):
            got[side] = None
    h, a = got.get("home"), got.get("away")
    if h is None or a is None:
        state.note(f"다 C4 — {NONE_MARK} `뒤짐` 칸을 못 읽었다(홈 {h} · 원정 {a})")
        return []
    if abs(h - a) < want:
        state.note(f"다 C4 — 뒤짐 득점 배율 홈 {h:g} ↔ 원정 {a:g} · 차가 "
                   f"{want:g} 미만이다(안 센다)")
        return []
    side = "home" if h > a else "away"
    state.note(f"다 C4 **발동** — {side} · 홈 {h:g} ↔ 원정 {a:g}")
    return [_var("DV4", "state_rate", ref, side,
                 f"{_name(ref, _key(ref, side))} 는 **지고 있을 때** 되돌리는 "
                 f"힘이 크다 — 뒤짐 상태 득점 배율 홈 ×{h:g} ↔ 원정 ×{a:g}"
                 f"(문턱 차 {want:g})")]


def _formation_change(ref: MatchRef, facts: Facts, cf: dict, *,
                      state: RunState) -> list[Variable]:
    """🔴 **C6** — 직전 다섯 경기에서 포메이션이 몇 번 **바뀌었나**. `[Variable]`."""
    want = _num(cf, "form_changes")
    if want is None:
        state.note(f"다 C6 — {NONE_MARK} 문턱 표가 없다(`{CONF}`)")
        return []
    got: dict[str, tuple[int, list[str]]] = {}
    for side in ("home", "away"):
        rows = list(dict(facts.past_xi or {}).get(_key(ref, side)) or [])
        said = [str(getattr(x, "formation", "") or "") for x in rows]
        said = [x for x in said if x]
        n = sum(1 for i in range(1, len(said)) if said[i] != said[i - 1])
        got[side] = (n, said)
    (nh, sh), (na, sa) = got["home"], got["away"]
    if not sh or not sa:
        state.note(f"다 C6 — {NONE_MARK} 직전 포메이션이 없다"
                   f"(홈 {len(sh)}경기 · 원정 {len(sa)}경기)")
        return []
    out: list[Variable] = []
    for side, (n, said) in (("home", got["home"]), ("away", got["away"])):
        if n < want:
            state.note(f"다 C6 `{side}` — 포메이션 변화 {n}번 < 문턱 {want}"
                       f"(안 센다 · {' → '.join(said)})")
            continue
        other = "away" if side == "home" else "home"
        out.append(_var(f"DV6-{side}", "lineup_intent", ref, other,
                        f"{_name(ref, _key(ref, side))} 포메이션이 직전 "
                        f"{len(said)}경기에서 **{n}번 바뀌었다** — "
                        f"{' → '.join(said)}(문턱 {want} · 자리를 못 굳혔다)"))
        state.note(f"다 C6 `{side}` **발동** — 변화 {n}번")
    return out


def _goal_spread(ref: MatchRef, facts: Facts, cf: dict, *,
                 state: RunState) -> list[Variable]:
    """🔴 **C7** — 실점이 **한 경기에 몰렸나**(`S01` 은 평균만 쓴다). `[Variable]`."""
    want, lead = _num(cf, "blowout_ga"), _num(cf, "blowout_lead")
    if want is None or lead is None:
        state.note(f"다 C7 — {NONE_MARK} 문턱 표가 없다(`{CONF}`)")
        return []
    got: dict[str, tuple[int, list[str]]] = {}
    for side in ("home", "away"):
        box = dict(dict(facts.recent or {}).get(_key(ref, side)) or {})
        rows = list(box.get("sequence") or [])
        hits: list[str] = []
        for one in rows:
            row = dict(one or {})
            try:
                ga = int(row.get("ga"))
            except (TypeError, ValueError):
                continue
            if ga >= want:
                hits.append(f"{row.get('date') or '?'} {row.get('score') or ''}"
                            .strip())
        got[side] = (len(hits), hits)
    nh, na = got["home"][0], got["away"][0]
    if abs(nh - na) < lead:
        state.note(f"다 C7 — 몰린 경기 홈 {nh}번 ↔ 원정 {na}번 · 차가 "
                   f"{lead} 미만이다(안 센다 · 문턱 실점 {want})")
        return []
    side = "home" if nh > na else "away"
    other = "away" if side == "home" else "home"
    said = " · ".join(got[side][1][:3]) or "?"
    state.note(f"다 C7 **발동** — {side} 몰림 {max(nh, na)}번")
    return [_var("DV7", "recent_pattern", ref, other,
                 f"{_name(ref, _key(ref, side))} 는 **한 경기에 실점이 몰린다** "
                 f"— 직전 5경기에서 {max(nh, na)}번(실점 {want}+ · 홈 {nh} ↔ "
                 f"원정 {na}) · {said}")]


def run(ref: MatchRef, facts: Facts, box: dict, *,
        state: RunState) -> tuple[list[Variable], str]:
    """🔴🔴 **가·나·다 전부** — `(변수 목록, 사유)`.

    🔴 부르는 곳은 운영(`pipeline`)과 러너다. ⚠️ 터져도 **빈 목록 + 사유**다
       (카드는 항상 나온다 · §5).
    """
    out: list[Variable] = []
    said: list[str] = []
    for nm, fn in (("가 능력치", lambda: from_ability(ref, facts, box,
                                                     state=state)),
                   ("나 갈래", lambda: from_branches(ref, facts, box,
                                                    state=state)),
                   ("다 사실", lambda: from_facts(ref, facts, state=state)),
                   # 🔴🔴 **5경기 실제 실력**(사용자 지시 2026-10-18) —
                   #    상대 수준·가중 폼·상위권 전적
                   ("실력", lambda: from_strength(ref, facts, state=state)),
                   # 🔴🔴 **흐름(폼)**(사용자 지시 2026-10-18) — 추세·최신
                   #    가중·홈원정 쪼갬·흔들림
                   ("흐름", lambda: from_flow(ref, facts, state=state))):
        try:
            got = list(fn())
        except Exception as exc:                            # noqa: BLE001
            state.note(f"{nm} — 🔴 터졌다 {exc!r:.160}")
            said.append(f"{nm} 🔴 터졌다")
            continue
        out += got
        said.append(f"{nm} {len(got)}개")
    return out, ("받은 자료 변수 — " + " · ".join(said)
                 + f" → 모두 **{len(out)}개**")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **5경기로 실제 실력을 잰다** — 사용자 지시 2026-10-18
# ══════════════════════════════════════════════════════════════════
#
#  > 5경기를 통하여 **두팀의 실제 실력**을 가늠하기 위함이다 .. 이거는
#  > **과거 데이타**고 이 데이타를 가지고 **오늘 경기를 예측**하는거다
#
#  🔴 종전 폼 변수(`S01`·`IR12`·`DV7`)는 **상대를 안 본다** — 꼴찌 상대 2골과
#     1위 상대 2골이 같은 한 경기다. 그러면 *"실제 실력"* 이 아니라 **일정 운**
#     이 섞인다.
#  🔴 재료는 둘 다 **이미 있다**(새 통신 0):
#       경기 줄  `facts.recent[팀]["sequence"]` — 날짜·상대 이름·득실·결과
#       순위표   `facts.standings["group"]["rows"]` — 전 팀의 순위·승점·경기수
#  ⚠️ 순위는 **오늘 표**다 — 그날 순위는 자료가 없다. 그 사실을 변수 글에
#     글자로 적는다(#3 · 지어내지 않는다).


def _table_rows(facts) -> list[dict]:
    """🔴 순위표 줄 전부 — `[{rank,name,played,points,…}]`. 없으면 빈 목록."""
    box = dict(dict(getattr(facts, "standings", None) or {}).get("group") or {})
    return [dict(x) for x in (box.get("rows") or []) if isinstance(x, dict)]


def _rank_of(name: str, rows: list[dict]) -> int | None:
    """🔴 상대 이름 → **오늘 순위**. 이름 맞추기는 `core/teamname.pick` 하나다.

    ⚠️ 표에 없으면 `None` 이다(지어내지 않는다 · 부르는 쪽이 센다).
    """
    from app.core import teamname as _tn
    keys = [str(r.get("name") or "") for r in rows]
    got, _why = _tn.pick(str(name or ""), keys)
    if not got:
        return None
    for r in rows:
        if str(r.get("name") or "") == got:
            try:
                return int(r.get("rank"))
            except (TypeError, ValueError):
                return None
    return None


def _games(facts, ref: MatchRef, side: str) -> list[dict]:
    box = dict(dict(getattr(facts, "recent", None) or {})
               .get(_key(ref, side)) or {})
    return [dict(x) for x in (box.get("sequence") or []) if isinstance(x, dict)]


def _pts(row: dict) -> int:
    """🔴 그 경기에서 딴 승점 — 승 3 · 무 1 · 패 0(새 수가 아니다 · 축구 규칙)."""
    said = str(row.get("result") or "")
    return 3 if said == "W" else 1 if said == "D" else 0


def _faced(facts, ref: MatchRef, side: str,
           rows: list[dict]) -> tuple[list[dict], int, int]:
    """🔴 그 팀 5경기에 **상대 순위를 붙인다**. `(줄, 찾은 수, 못 찾은 수)`."""
    out, miss = [], 0
    for one in _games(facts, ref, side):
        rk = _rank_of(str(one.get("opponent") or ""), rows)
        if rk is None:
            miss += 1
            continue
        out.append({**one, "opp_rank": rk})
    return out, len(out), miss


def from_strength(ref: MatchRef, facts: Facts, *,
                  state: RunState) -> list[Variable]:
    """🔴🔴 **5경기 실제 실력** — 상대 수준·가중 폼·상위권 전적. `[Variable]`."""
    cf = _box("strength")
    rows = _table_rows(facts)
    out: list[Variable] = []
    if not rows:
        state.note(f"실력 — {NONE_MARK} 순위표가 없다(상대 수준을 못 잰다)")
        return out
    n_tab = len(rows)
    got: dict[str, list[dict]] = {}
    for side in ("home", "away"):
        said, n, miss = _faced(facts, ref, side, rows)
        got[side] = said
        state.note(f"실력 `{side}` — 5경기 중 상대 순위를 찾은 것 {n}개 · "
                   f"못 찾은 것 {miss}개(순위표 {n_tab}팀 · **오늘 순위**다)")
    out += _opp_level(ref, cf, got, state=state, n_tab=n_tab)
    out += _weighted_form(ref, cf, got, state=state, n_tab=n_tab)
    out += _vs_top(ref, cf, got, state=state, n_tab=n_tab)
    return out


def _opp_level(ref: MatchRef, cf: dict, got: dict, *, state: RunState,
               n_tab: int) -> list[Variable]:
    """🔴 **상대 평균 순위** — 누가 더 센 일정을 치렀나(작을수록 센 상대)."""
    gap, low = _num(cf, "rank_gap"), _num(cf, "rank_min")
    if gap is None or low is None:
        state.note(f"실력 상대수준 — {NONE_MARK} 문턱 표가 없다(`{CONF}`)")
        return []
    avg: dict[str, float] = {}
    for side in ("home", "away"):
        rowz = got.get(side) or []
        if len(rowz) < low:
            state.note(f"실력 상대수준 `{side}` — 찾은 상대 {len(rowz)}개 < "
                       f"{low:g}(안 센다)")
            return []
        avg[side] = sum(float(r["opp_rank"]) for r in rowz) / len(rowz)
    h, a = avg["home"], avg["away"]
    if abs(h - a) < gap:
        state.note(f"실력 상대수준 — 상대 평균 순위 홈 {h:.1f}위 ↔ 원정 "
                   f"{a:.1f}위 · 차 {abs(h - a):.1f} < {gap:g}(안 센다)")
        return []
    # 🔴 **순위가 작을수록 센 상대**다 — 센 일정을 치른 쪽이 유리하다
    side = "home" if h < a else "away"
    state.note(f"실력 상대수준 **발동** — {side} · 홈 {h:.1f} ↔ 원정 {a:.1f}")
    return [_var("ST1", "squad_ability", ref, side,
                 f"{_name(ref, _key(ref, side))} 는 **더 센 일정**을 치렀다 — "
                 f"5경기 상대 평균 순위 홈 **{h:.1f}위** ↔ 원정 **{a:.1f}위**"
                 f"(순위표 {n_tab}팀 · 차 {abs(h - a):.1f} · 문턱 {gap:g}) · "
                 "⚠️ **오늘 순위** 기준이다(그날 순위는 자료가 없다)")]


def _weighted_form(ref: MatchRef, cf: dict, got: dict, *, state: RunState,
                   n_tab: int) -> list[Variable]:
    """🔴 **가중 폼** — 득실 차를 **상대 순위로 가중**한다.

    🔴 가중은 `1 + (표 중앙 − 상대 순위) / 표 크기` 다 — 상위권 상대 결과에
       무게가 더 가고 하위권 상대 결과는 깎인다. ⚠️ 새 수를 짓지 않았다:
       **표 크기와 순위**만 쓴다(계수를 손으로 넣지 않는다).
    """
    want = _num(cf, "weighted_gap")
    low = _num(cf, "rank_min")
    if want is None or low is None:
        state.note(f"실력 가중폼 — {NONE_MARK} 문턱 표가 없다(`{CONF}`)")
        return []
    mid = (n_tab + 1) / 2.0
    val: dict[str, float] = {}
    for side in ("home", "away"):
        rowz = got.get(side) or []
        if len(rowz) < low:
            state.note(f"실력 가중폼 `{side}` — 찾은 상대 {len(rowz)}개 < "
                       f"{low:g}(안 센다)")
            return []
        tot = 0.0
        for r in rowz:
            try:
                gf = float(r.get("goals_for") or 0)
                ga = float(r.get("goals_against") or 0)
            except (TypeError, ValueError):
                continue
            w = 1.0 + (mid - float(r["opp_rank"])) / float(n_tab)
            tot += (gf - ga) * w
        val[side] = tot / len(rowz)
    h, a = val["home"], val["away"]
    if abs(h - a) < want:
        state.note(f"실력 가중폼 — 가중 득실 홈 {h:+.2f} ↔ 원정 {a:+.2f} · "
                   f"차 {abs(h - a):.2f} < {want:g}(안 센다)")
        return []
    side = "home" if h > a else "away"
    state.note(f"실력 가중폼 **발동** — {side} · 홈 {h:+.2f} ↔ 원정 {a:+.2f}")
    return [_var("ST2", "recent_pattern", ref, side,
                 f"{_name(ref, _key(ref, side))} 의 **가중 득실**이 높다 — "
                 f"상대 순위로 가중한 경기당 득실 홈 **{h:+.2f}** ↔ 원정 "
                 f"**{a:+.2f}**(문턱 차 {want:g} · 가중은 표 {n_tab}팀의 "
                 f"중앙 {mid:.1f}위 기준) · ⚠️ **오늘 순위** 기준이다",
                 goals=("up" if side == "home" else "down"))]


def _vs_top(ref: MatchRef, cf: dict, got: dict, *, state: RunState,
            n_tab: int) -> list[Variable]:
    """🔴 **상위권 상대 전적** — 센 팀을 상대로 무엇을 했나(경기당 승점)."""
    share = _num(cf, "top_share")
    want = _num(cf, "top_pts_gap")
    low = _num(cf, "top_min")
    if share is None or want is None or low is None:
        state.note(f"실력 상위권 — {NONE_MARK} 문턱 표가 없다(`{CONF}`)")
        return []
    cut = max(1, int(round(n_tab * share)))
    val: dict[str, tuple[float, int]] = {}
    for side in ("home", "away"):
        rowz = [r for r in (got.get(side) or []) if int(r["opp_rank"]) <= cut]
        if len(rowz) < low:
            state.note(f"실력 상위권 `{side}` — 상위 {cut}위 안 상대가 "
                       f"{len(rowz)}경기 < {low:g}(안 센다)")
            return []
        val[side] = (sum(_pts(r) for r in rowz) / len(rowz), len(rowz))
    (h, nh), (a, na) = val["home"], val["away"]
    if abs(h - a) < want:
        state.note(f"실력 상위권 — 상위권 상대 경기당 승점 홈 {h:.2f}({nh}경기) "
                   f"↔ 원정 {a:.2f}({na}경기) · 차 {abs(h - a):.2f} < "
                   f"{want:g}(안 센다)")
        return []
    side = "home" if h > a else "away"
    state.note(f"실력 상위권 **발동** — {side} · 홈 {h:.2f} ↔ 원정 {a:.2f}")
    return [_var("ST3", "squad_ability", ref, side,
                 f"{_name(ref, _key(ref, side))} 는 **상위권 상대에 강하다** — "
                 f"상위 {cut}위 안 상대 경기당 승점 홈 **{h:.2f}**({nh}경기) ↔ "
                 f"원정 **{a:.2f}**({na}경기) · 문턱 차 {want:g}(상위 "
                 f"{share:g} = {n_tab}팀 중 {cut}위까지) · ⚠️ **오늘 순위** 기준")]


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **5경기의 흐름(폼)** — 사용자 지시 2026-10-18
# ══════════════════════════════════════════════════════════════════
#
#  > 5경기에서 더 확인해야 할거는 **흐름**이다 .. **폼**이라는 말이다 ..
#  > **상세하게** .. 그냥 5경기 실득점만 확인하는게 아니다
#
#  🔴 `S01` 은 **평균 하나**다 — 순서를 버린다(`0-4` 뒤 3승과 3승 뒤 `0-4` 가
#     같은 수가 된다). 그래서 여기서는 **순서로** 본다:
#       F1 추세(앞 토막 ↔ 최신 토막) · F2 최신 가중 · F3 홈·원정 쪼갠 폼 ·
#       F4 흔들림(경기별 득실 차의 폭)
#  ⚠️ **연승은 표현하지 않는다**(사용자 지시 2026-10-17) — 승을 묶어 세지 않고
#     **경기마다** 본다.
#  🔴 재료는 `facts.recent[팀]["sequence"]` 하나다(최신이 앞 · 새 통신 0).


def _gd(row: dict) -> float | None:
    """🔴 그 경기 **득실 차**(득점 − 실점). 못 읽으면 `None`."""
    try:
        return float(row.get("goals_for") or 0) - float(row.get("goals_against")
                                                        or 0)
    except (TypeError, ValueError):
        return None


def _seq(facts, ref: MatchRef, side: str) -> list[dict]:
    """🔴 그 팀 경기 줄 — **최신이 앞**이다(`s2_facts` 가 그렇게 싣는다)."""
    return _games(facts, ref, side)


def from_flow(ref: MatchRef, facts: Facts, *,
              state: RunState) -> list[Variable]:
    """🔴🔴 **흐름(폼)** — F1 추세 · F2 최신 가중 · F3 홈원정 · F4 흔들림."""
    cf = _box("flow")
    out: list[Variable] = []
    box = {s: _seq(facts, ref, s) for s in ("home", "away")}
    if not box["home"] or not box["away"]:
        state.note(f"흐름 — {NONE_MARK} 경기 줄이 없다"
                   f"(홈 {len(box['home'])} · 원정 {len(box['away'])})")
        return out
    out += _trend(ref, cf, box, state=state)
    out += _decay_form(ref, cf, box, state=state)
    out += _side_form(ref, cf, box, state=state)
    out += _swing(ref, cf, box, state=state)
    return out


def _trend(ref: MatchRef, cf: dict, box: dict, *,
           state: RunState) -> list[Variable]:
    """🔴 **F1 추세** — 최신 토막이 앞 토막보다 좋아졌나(경기당 득실)."""
    n_late, want = _num(cf, "late_games"), _num(cf, "trend_gap")
    if n_late is None or want is None:
        state.note(f"흐름 F1 — {NONE_MARK} 문턱 표가 없다(`{CONF}`)")
        return []
    got: dict[str, float] = {}
    said_t: dict[str, str] = {}
    for side in ("home", "away"):
        rows = box[side]
        late = [v for v in (_gd(r) for r in rows[:int(n_late)]) if v is not None]
        early = [v for v in (_gd(r) for r in rows[int(n_late):])
                 if v is not None]
        if not late or not early:
            state.note(f"흐름 F1 `{side}` — 토막이 비었다(최신 {len(late)} · "
                       f"앞 {len(early)}) · 안 센다")
            return []
        a, b = sum(late) / len(late), sum(early) / len(early)
        got[side] = a - b
        said_t[side] = (f"최신 {len(late)}경기 {a:+.2f} ↔ 앞 {len(early)}경기 "
                        f"{b:+.2f}")
    h, a = got["home"], got["away"]
    if abs(h - a) < want:
        state.note(f"흐름 F1 — 추세 홈 {h:+.2f} ↔ 원정 {a:+.2f} · 차 "
                   f"{abs(h - a):.2f} < {want:g}(안 센다)")
        return []
    side = "home" if h > a else "away"
    state.note(f"흐름 F1 **발동** — {side} · 홈 {h:+.2f} ↔ 원정 {a:+.2f}")
    return [_var("FL1", "recent_pattern", ref, side,
                 f"{_name(ref, _key(ref, side))} 의 **흐름이 오른다** — 경기당 "
                 f"득실 추세 홈 **{h:+.2f}** ↔ 원정 **{a:+.2f}**"
                 f"(홈 {said_t['home']} · 원정 {said_t['away']} · 문턱 차 "
                 f"{want:g}) · ⚠️ 평균이 아니라 **순서**로 본 수다",
                 goals=("up" if side == "home" else "down"))]


def _decay_form(ref: MatchRef, cf: dict, box: dict, *,
                state: RunState) -> list[Variable]:
    """🔴 **F2 최신 가중** — 최신 경기에 무게를 더 준 득실(뒤로 갈수록 깎는다)."""
    dec, want = _num(cf, "decay"), _num(cf, "decay_gap")
    if dec is None or want is None:
        state.note(f"흐름 F2 — {NONE_MARK} 문턱 표가 없다(`{CONF}`)")
        return []
    got: dict[str, float] = {}
    for side in ("home", "away"):
        num = den = 0.0
        for i, row in enumerate(box[side]):
            val = _gd(row)
            if val is None:
                continue
            w = dec ** i
            num += val * w
            den += w
        if den <= 0:
            state.note(f"흐름 F2 `{side}` — {NONE_MARK} 득실을 못 읽었다")
            return []
        got[side] = num / den
    h, a = got["home"], got["away"]
    if abs(h - a) < want:
        state.note(f"흐름 F2 — 가중 득실 홈 {h:+.2f} ↔ 원정 {a:+.2f} · 차 "
                   f"{abs(h - a):.2f} < {want:g}(안 센다)")
        return []
    side = "home" if h > a else "away"
    state.note(f"흐름 F2 **발동** — {side} · 홈 {h:+.2f} ↔ 원정 {a:+.2f}")
    return [_var("FL2", "recent_pattern", ref, side,
                 f"{_name(ref, _key(ref, side))} 의 **최신 쪽 폼이 낫다** — "
                 f"최신에 무게를 둔 경기당 득실 홈 **{h:+.2f}** ↔ 원정 "
                 f"**{a:+.2f}**(뒤로 갈수록 ×{dec:g} · 문턱 차 {want:g})",
                 goals=("up" if side == "home" else "down"))]


def _side_form(ref: MatchRef, cf: dict, box: dict, *,
               state: RunState) -> list[Variable]:
    """🔴 **F3 홈·원정 쪼갠 폼** — 오늘 홈팀은 과거 **홈** 경기, 원정팀은 **원정**.

    🔴 까닭 — 오늘 홈팀에게 과거 원정 경기 성적은 다른 조건의 기록이다.
    ⚠️ 경기 줄의 `side` 칸을 쓴다(그 칸이 없으면 안 돈다 · #3).
    """
    low, want = _num(cf, "side_min"), _num(cf, "side_gap")
    if low is None or want is None:
        state.note(f"흐름 F3 — {NONE_MARK} 문턱 표가 없다(`{CONF}`)")
        return []
    got: dict[str, tuple[float, int]] = {}
    for side in ("home", "away"):
        rows = [r for r in box[side] if str(r.get("side") or "") == side]
        vals = [v for v in (_gd(r) for r in rows) if v is not None]
        if len(vals) < low:
            state.note(f"흐름 F3 `{side}` — 같은 쪽 경기가 {len(vals)}개 < "
                       f"{low:g}(안 센다)")
            return []
        got[side] = (sum(vals) / len(vals), len(vals))
    (h, nh), (a, na) = got["home"], got["away"]
    if abs(h - a) < want:
        state.note(f"흐름 F3 — 쪼갠 폼 홈 {h:+.2f}({nh}경기) ↔ 원정 "
                   f"{a:+.2f}({na}경기) · 차 {abs(h - a):.2f} < {want:g}"
                   "(안 센다)")
        return []
    side = "home" if h > a else "away"
    state.note(f"흐름 F3 **발동** — {side} · 홈 {h:+.2f} ↔ 원정 {a:+.2f}")
    return [_var("FL3", "recent_pattern", ref, side,
                 f"{_name(ref, _key(ref, side))} 는 **같은 자리(홈/원정)에서** "
                 f"더 낫다 — 홈팀의 과거 홈 {nh}경기 **{h:+.2f}** ↔ 원정팀의 "
                 f"과거 원정 {na}경기 **{a:+.2f}**(경기당 득실 · 문턱 차 "
                 f"{want:g})",
                 goals=("up" if side == "home" else "down"))]


def _swing(ref: MatchRef, cf: dict, box: dict, *,
           state: RunState) -> list[Variable]:
    """🔴 **F4 흔들림** — 경기별 득실 차의 **폭**(최대 − 최소).

    🔴 뜻 — 폭이 큰 팀은 같은 평균이어도 **읽기 어렵다**(오늘도 어느 쪽으로든
       크게 갈 수 있다). ⚠️ 방향은 **폭이 작은 쪽**이다(덜 흔들린다).
    """
    want = _num(cf, "swing_gap")
    if want is None:
        state.note(f"흐름 F4 — {NONE_MARK} 문턱 표가 없다(`{CONF}`)")
        return []
    got: dict[str, tuple[float, list[float]]] = {}
    for side in ("home", "away"):
        vals = [v for v in (_gd(r) for r in box[side]) if v is not None]
        if len(vals) < 2:
            state.note(f"흐름 F4 `{side}` — 경기 {len(vals)}개로는 폭을 못 잰다")
            return []
        got[side] = (max(vals) - min(vals), vals)
    h, a = got["home"][0], got["away"][0]
    if abs(h - a) < want:
        state.note(f"흐름 F4 — 흔들림 폭 홈 {h:g} ↔ 원정 {a:g} · 차 "
                   f"{abs(h - a):g} < {want:g}(안 센다)")
        return []
    side = "home" if h < a else "away"
    other = "away" if side == "home" else "home"
    state.note(f"흐름 F4 **발동** — {side}(덜 흔들린다) · 홈 {h:g} ↔ 원정 {a:g}")
    return [_var("FL4", "recent_pattern", ref, side,
                 f"{_name(ref, _key(ref, side))} 는 **덜 흔들린다** — 경기별 "
                 f"득실 차의 폭 홈 **{h:g}** ↔ 원정 **{a:g}**(문턱 차 {want:g}"
                 f" · 큰 쪽 {_name(ref, _key(ref, other))} 은 오늘도 어느 "
                 "쪽으로든 크게 갈 수 있다)")]
