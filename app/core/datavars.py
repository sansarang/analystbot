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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **인원 수가 다르면 평균을 견주지 않는다**(사용자 지시 2026-10-19)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 점수차가 많이 나는거는 실제로 우리 코드에 문제가 있다는거다
    #  > → **고쳐라**
    #
    #  ⚠️ 실측 2026-10-19 — 큰 점수차 네 판 중 **인원이 같은 셋은 다 맞췄고**
    #     유일하게 틀린 판이 인원이 **다른** 판이었다:
    #       우디네세 0-3   0.40(10명) ↔ 0.46(10명) → 원정 ✅
    #       브라이턴 5-0   0.62(10명) ↔ 0.52(10명) → 홈   ✅
    #       호펜하임 1-2   0.42(10명) ↔ 0.54(10명) → 원정 ✅
    #       🔴 르아브르 1-3 0.50(**8명**) ↔ 0.37(10명) → 홈 ✗(실제 원정 승)
    #  🔴 까닭 — 능력치를 못 받는 선수는 보통 **출전이 적은 선수**다. 그들을
    #     빼고 낸 평균은 **위로 치우친다**. 표본 수가 다른 두 평균을 그대로
    #     견주면 비교의 전제가 깨진다.
    #  🔴 새 손값을 만들지 않는다 — *"같지 않으면 안 센다"* 하나다.
    elif abs(nh - na) > _ab.count_slack():
        state.note(f"가 A1 — 홈 {nh}명 ↔ 원정 {na}명 · **인원 차 "
                   f"{abs(nh - na)}명**(허용 {_ab.count_slack()}명) → 안 센다")
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
        # 🔴🔴 **인원이 다르면 자리별 평균도 견주지 않는다**(2026-10-19 · A1 과 같은 까닭)
        #    ⚠️ 실측 — `AB3` 가 **9명 ↔ 6명**으로 견준 판이 있었다(호펜하임).
        if hh is None or aa is None or n1 < _ab.branch_min() \
                or n2 < _ab.branch_min() \
                or abs(n1 - n2) > _ab.count_slack() \
                or abs(hh - aa) < tilt_gap:
            if (hh is not None and aa is not None
                    and abs(n1 - n2) > _ab.count_slack()):
                state.note(f"가 A3 `{kind}` — 홈 {n1}명 ↔ 원정 {n2}명 · "
                           f"**인원 차 {abs(n1 - n2)}명**(허용 "
                           f"{_ab.count_slack()}명) → 그 자리는 안 센다")
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
    #: 🔴 집안 하나(2026-10-19 ㄱ) — 쪽별 **손실 크기**를 담는다
    loss: dict = {}
    if gap is None:
        state.note(f"가 A2 — {NONE_MARK} 문턱 표가 없다(`{CONF}`)")
        return out
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
        # 🔴 능력치 표(`box`)의 열쇠는 **선수 이름**이다(`ability.side_pct` 가
        #    `box.get(p["name"])` 로 읽는다 · 사본 금지).
        #    ⚠️ 실사고 2026-10-18: 행(`p`) 자체를 `_pct_of` 에 넘겨 **늘 빈
        #       값**이었다 — A1 은 0.55 를 쟀는데 A2 만 *"백분위가 없다"* 였다.
        now = [v for v in (_ab._pct_of(box.get(p["name"]) or {}, traits)
                           for p in mine) if v is not None]
        if not now:
            state.note(f"가 A2 `{side}` — {NONE_MARK} 오늘 선발 백분위가 없다")
            continue
        base = sum(now) / len(now)
        hits: list[tuple[str, float]] = []
        for nm in gone:
            # 🔴 같은 까닭 — **이름**으로 찾는다(`pid` 는 선수 페이지 열쇠일
            #    뿐이고 능력치 표의 열쇠가 아니다)
            one = dict(box.get(nm) or {})
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
        #: 🔴 집안 하나가 읽을 **잰 값** — 손실 크기(빠진 최고 − 오늘 평균)
        loss[side] = float(top[1] - base)
        state.note(f"가 A2 `{side}` **발동** — {top[0]} {top[1]:.3f}")
    return _ab2_one(out, loss, ref, gap, state=state)


def _ab2_one(out: list[Variable], loss: dict, ref: MatchRef, gap: float, *,
             state: RunState) -> list[Variable]:
    """🔴🔴 **결장 품질도 집안 하나 — 부등호로 센다**(사용자 지시 2026-10-19 ㄱ).

    ⚠️ 실측 2026-10-19 — `AB2` 가 **양 팀에 같이 걸려 서로 지웠다**:
       · 우디네세 0-3 레체 — `AB2-home` ↔ `AB2-away` 상쇄 · 우리 홈 1위(틀림)
       · 글라드바흐 1-2 호펜하임 — 같은 모양 · 우리 홈 1위(틀림)
       🔴 `AB2` 는 `FAMILY` 표에 **없어서** 집안 하나 규칙이 건드리지 않았다.
    🔴 그래서 **손실이 큰 쪽**만 확률에 닿는다(그 팀이 불리하므로 표의 방향대로
       상대를 민다). 두 손실 차가 문턱(`absence_gap`) 미만이면 **"같다"** 로
       적고 둘 다 맥락 전용이다.
    🔴 문턱은 **새 손값이 아니다** — A2 가 쓰는 그 `absence_gap` 을 그대로 쓴다.
    """
    if len(out) < 2 or len(loss) < 2:
        return out
    a, b = float(loss.get("home", 0.0)), float(loss.get("away", 0.0))
    said = f"손실 홈 {a:.2f} ↔ 원정 {b:.2f}"
    if abs(a - b) < float(gap):
        state.note(f"가 A2 — 집안 하나: **같다**({said} · 차 {abs(a - b):.2f} < "
                   f"{float(gap):g}) → 둘 다 맥락")
        return [one.model_copy(update={
            "usable_as_basis": False,
            "claim": f"{one.claim} · 🔴 **결장 품질 같다**({said}) — "
                     f"확률에 안 넣는다"}) for one in out]
    worse = "home" if a > b else "away"
    mark = ">" if a > b else "<"
    got: list[Variable] = []
    for one in out:
        mine = "home" if str(getattr(one, "id", "")).endswith("-home") else "away"
        if mine == worse:
            got.append(one.model_copy(update={
                "claim": f"{one.claim} · 🔴 **손실이 더 크다**({said} · "
                         f"{a:.2f} {mark} {b:.2f}) — 이 쪽이 집안 대표다"}))
        else:
            got.append(one.model_copy(update={
                "usable_as_basis": False,
                "claim": f"{one.claim} · 🔴 **집안 하나** — 상대 쪽 손실이 더 "
                         f"크다({said} · 확률에 안 넣는다)"}))
    state.note(f"가 A2 — 집안 하나: **{worse} 손실이 더 크다**({said})")
    return got


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
    # 🔴🔴 **인원 수가 다르면 합을 견주지 않는다**(2026-10-19 · A1 과 같은 까닭)
    #    ⚠️ 가치 **합**은 인원 수에 그대로 비례한다 — 한쪽이 두 명 적으면
    #       그 팀 합이 작아 보이고, 그것을 *"전력이 낮다"* 로 읽는다.
    from app.core import ability as _ability
    slack = _ability.count_slack()
    if abs(nh - na) > slack:
        state.note(f"다 C3 — 가치를 가진 선발 홈 {nh}명 ↔ 원정 {na}명 · "
                   f"**인원 차 {abs(nh - na)}명**(허용 {slack}명 · "
                   "합이 인원에 비례한다) → 안 센다")
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


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **한 집안에서 확률에 닿는 것은 하나** — 사용자 지시 2026-10-18
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측(휴스턴 vs 댈러스): 갈래가 `BR-1·2·3` + 묶음 `BR0` 로 **네 표**가
#     됐고, `ST1`↔`ST2`·`FL1`↔`FL2` 는 **서로 지워 0표**가 됐다.
#  🔴 집안마다 **가장 센 것 하나**만 남기고 나머지는 **맥락 전용**으로 내린다
#     (`usable_as_basis=False` → `routing.place` 가 `hypo` 로 내린다).
#  🔴 집안·세기는 **여기 표**가 든다 — 변수 id 접두로 가린다(사본 금지:
#     id 를 만드는 곳이 이 파일 하나다).

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **갈래는 묶음이 대표다** — 사용자 지시 2026-10-18(*"전부 고쳐라"*)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측(오스틴 vs 밴쿠버): 갈래 **넷이 전부 원정**(`중원·빌드업·압박·교체`
#     4:0)이었는데 집안 하나 규칙이 **먼저 나온 `BR-1`** 을 남겨 *"4:0 으로
#     압도"* 라는 **세기가 사라졌다**.
#  🔴 묶음(`BR0`)은 **가린 갈래 수의 차**가 문턱을 넘을 때만 선다(`count_lead`)
#     — 즉 그 변수 자체가 *"압도"* 를 뜻한다. 그래서 **묶음이 있으면 묶음이
#     대표**가 되고 갈래별은 전부 맥락으로 내려간다.
#  ⚠️ 묶음이 없으면(2:1 처럼 팽팽하면) 종전처럼 **먼저 나온 갈래 하나**가
#     대표다 — 그 경우는 압도가 아니므로 한 표가 맞다.

#: 🔴 집안마다 **대표로 고를 id**(없으면 먼저 나온 것) — 사본 금지: 여기 하나다
PREFER: dict[str, str] = {"갈래": "BR0"}

#: 🔴 집안 — `{집안 이름: (id 접두들)}`. ⚠️ 묶음 변수(`BR0`)는 **갈래 집안**이다
FAMILY: dict[str, tuple[str, ...]] = {
    "갈래": ("BR-", "BR0"),
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **선발 명단 하나에서 일곱 표가 나왔다** — 사용자 지시 2026-10-19
    # ══════════════════════════════════════════════════════════════
    #
    #  > 구조적 결함 있는지 전수 검사 해라 → **1번 고치고 재측정해봐라**
    #
    #  ⚠️ 전수 검사(2026-10-19): `facts.xi` **한 칸**에서 확률에 닿는 변수가
    #     **일곱**이었다 — `IR02`·`IR03`·`DV3`·`AB1`·`AB3`·`BR0`·`BR-n`.
    #     실측(브라이턴): 센 변수 넷 중 **셋**이 선발 명단에서 나왔다
    #     (`AB1`·`AB2`·`BR0`) — *"명단이 좋다"* 가 세 번 세어졌다.
    #  🔴 그 칸이 답하는 질문은 **셋**이다. 질문마다 표 하나로 묶는다:
    #       ① 누가 나왔나(선발 전력) — `AB1`·`AB3`·**`DV3`**(가치는 전력의 어림)
    #       ② 누가 빠졌나(결장)      — `AB2`·`IR02`(`one_fact_one_vote`)
    #       ③ 전술 비교(갈래)        — `BR0`·`BR-n`(묶음이 대표)
    #  ⚠️ 대표를 **어느 것으로** 할지는 아홉 판으로 정할 수 없다 — 지금은 각
    #     집안 함수가 담는 **순서**(AB1 → AB3 → DV3)를 쓰고, 그 순서가 옳은지는
    #     백필 측정으로 가린다(🔴 수를 짓지 않는다).
    #  🔴🔴 **되돌렸다**(사용자 지시 2026-10-19) — 묶음은 `AB1`·`AB3` 만이다.
    #     ⚠️ 실측 아홉 판 비교 — `DV3` 까지 묶으면 적중 **6 → 5**, 빗남 1 → 2
    #        였다(벨그라노·호펜하임이 동률로 내려갔다: `AB3`·`DV3` 가 같은 쪽을
    #        가리킨 판에서 한 표로 줄기 때문이다).
    #     🔴 그래도 **중복은 사실이다** — `facts.xi` 한 칸에서 확률에 닿는 변수가
    #        여섯이다(`IR02`·`IR03`·`DV3`·`AB1`·`AB3`·`BR*`). 어느 것을 대표로
    #        할지는 백필 2,582경기가 말해야 한다(표본 아홉으로는 못 가린다).
    "능력치": ("AB1", "AB3"),
    # 🔴 `AB2`(결장 품질)는 **쪽마다 하나씩** 나므로 크기를 견줘야 한다 —
    #    그 판정은 `_ab2_one` 이 하고(2026-10-19 ㄱ), 이 표는 집안 이름만 든다.
    #    ⚠️ 종전엔 이 표에 없어서 집안 하나 규칙이 **건드리지 않았다**.
    "결장 품질": ("AB2",),
    "전력차": ("TB1", "TB2"),
    "실력": ("ST1", "ST2", "ST3"),
    "흐름": ("FL1", "FL2", "FL4"),
}


def _family_of(rid: str) -> str:
    said = str(rid or "")
    for name, pres in FAMILY.items():
        if any(said.startswith(p) for p in pres):
            return name
    return ""


#: 🔴🔴 **같은 사실을 두 번 세지 않는다**(사용자 지시 2026-10-19 — 구조적 결함)
#
#  ⚠️ 실측 2026-10-19(우디네세 0-3 레체): 결장자 **한 명**(Ivan Ilić)이 확률에
#     **두 표**로 들어갔다 —
#       `IR02-away` *"직전 선발 Ilić 가 오늘 명단에 없다"*      → 홈 ×1.03
#       `AB2-away`  *"결장 품질 손실 — Ilić 0.58 > 평균 0.46"*  → 홈 ×1.03
#     그 둘이 홈을 2표로 밀어 홈 1위(36.5%)가 됐고 결과는 **0-3 원정 완승**이다.
#     (같은 사실이 `A5 전력 누수`·`A8 자리 교체`로도 적히지만 그 둘은 맥락이다.)
#  🔴 **대표는 `AB2`** 다 — 그것이 *"누가"* 빠졌나(능력치까지)를 센다.
#     `IR02`(몇 명)는 맥락으로 내린다. ⚠️ `AB2` 가 없으면 `IR02` 가 그대로 선다.
#  🔴 쪽마다 따로 본다 — 홈에 `AB2` 가 있고 원정에 없으면 원정 `IR02` 는 남는다.
SAME_FACT: tuple[tuple[str, str], ...] = (("AB2", "IR02"),)


def one_fact_one_vote(rows: list, *, state: RunState) -> list:
    """🔴🔴 **한 사실 한 표** — 대표가 있으면 겹치는 쪽을 맥락으로 내린다.

    `SAME_FACT` 의 `(대표 접두, 내릴 접두)` 를 **쪽별로** 본다(`-home`·`-away`).
    🔴 돌려주는 줄 수는 그대로다 — 내린 것은 `usable_as_basis=False` 로 남아
       ⑯ 이 읽는다(#3 조용한 0 금지).
    """
    # 🔴🔴 **대표가 확률에 닿는지까지 본다**(사용자 지시 2026-10-19 · 결함 2)
    #
    #  ⚠️ 실사고 2026-10-19(우디네세 0-3 레체): `AB2` 양쪽이 *"같다"* 로 맥락에
    #     내려갔는데도 이 자리가 *"대표가 있다"* 로 보고 `IR02-away` 를 내렸다 —
    #     아니, 더 나쁘게는 **대표가 없는 셈**이 되어 `IR02` 가 혼자 홈을 밀었다.
    #  🔴 대표가 **맥락이면 대표가 아니다** — 그때는 `IR02` 를 그대로 둔다.
    #     ⚠️ 그래도 같은 사실을 **두 표**로 세는 일은 없다: 대표가 맥락이면
    #        확률에 닿는 것은 `IR02` 하나뿐이다.
    said = {str(getattr(x, "id", "")): bool(getattr(x, "usable_as_basis", True))
            for x in (rows or [])}
    out = []
    for one in (rows or []):
        rid = str(getattr(one, "id", ""))
        hit = ""
        for lead, drop in SAME_FACT:
            if not rid.startswith(drop):
                continue
            tail = rid[len(drop):]            # 🔴 `-home`·`-away`(없으면 빈 글자)
            if said.get(f"{lead}{tail}"):     # 🔴 **확률에 닿는** 대표만
                hit = f"{lead}{tail}"
                break
        if not hit:
            out.append(one)
            continue
        out.append(one.model_copy(update={
            "usable_as_basis": False,
            "claim": f"{one.claim} · 🔴 **한 사실 한 표** — 같은 결장을 "
                     f"`{hit}` 가 품질까지 세므로 이 줄은 확률에 안 넣는다"}))
        state.note(f"한 사실 한 표 — `{rid}` 를 맥락으로 내렸다(대표 `{hit}`)")
    return out


def _one_per_family(rows: list[Variable], *,
                    state: RunState) -> list[Variable]:
    """🔴🔴 집안마다 **하나**만 확률에 닿게 한다. `[Variable]`(수는 그대로).

    🔴 고르는 기준은 **글에 적힌 차**가 아니라 **먼저 나온 것**이다 — 각
       집안의 함수가 **센 것부터** 담기 때문이다(갈래는 가려진 순서 · 실력은
       ST1→ST2→ST3 · 흐름은 FL1→FL2→FL4). ⚠️ 그 사실을 사유에 적는다.
    🔴 내린 변수는 **사라지지 않는다** — `usable_as_basis=False` 로 맥락 전용이
       되어 ⑯ 이 읽는다(#3).
    """
    if not bool(_load().get("one_per_family")):
        state.note("집안 하나 — ⬜ 끔(`one_per_family` 가 거짓이다)")
        return rows
    # 🔴 **대표를 먼저 고른다**(위 `PREFER`) — 갈래는 묶음이 압도를 뜻한다
    said_ids = {str(getattr(x, "id", "")) for x in rows}
    want: dict[str, str] = {}
    for fam, rid in PREFER.items():
        if rid in said_ids:
            want[fam] = rid
            state.note(f"집안 하나 — 집안 `{fam}` 의 대표는 `{rid}` 다"
                       "(묶음이 **압도**를 뜻한다)")
    seen: set[str] = set()
    out: list[Variable] = []
    for one in rows:
        fam = _family_of(getattr(one, "id", ""))
        rid = str(getattr(one, "id", ""))
        # 🔴 그 집안에 **대표가 정해져 있으면** 그것만 남긴다
        if fam and fam in want:
            if rid == want[fam]:
                out.append(one)
                continue
            out.append(one.model_copy(update={
                "usable_as_basis": False,
                "claim": f"{one.claim} · ⚠️ **맥락 전용으로 내렸다** — 집안 "
                         f"`{fam}` 의 대표는 `{want[fam]}`(묶음)다"}))
            state.note(f"집안 하나 — `{rid}` 를 맥락 전용으로 내렸다"
                       f"(집안 `{fam}` · 대표 `{want[fam]}`)")
            continue
        if not fam or fam not in seen:
            if fam:
                seen.add(fam)
            out.append(one)
            continue
        out.append(one.model_copy(update={
            "usable_as_basis": False,
            "claim": f"{one.claim} · ⚠️ **맥락 전용으로 내렸다** — 집안 "
                     f"`{fam}` 에서 이미 한 변수가 확률에 닿았다(한 사실이 "
                     "여러 표가 되지 않게)"}))
        state.note(f"집안 하나 — `{one.id}` 를 맥락 전용으로 내렸다(집안 `{fam}`)")
    return out


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
    out = _one_per_family(out, state=state)
    n_hit = sum(1 for x in out if getattr(x, "usable_as_basis", True))
    return out, ("받은 자료 변수 — " + " · ".join(said)
                 + f" → 모두 **{len(out)}개**"
                 + f"(확률에 닿는 것 {n_hit}개 · 맥락 전용 "
                   f"{len(out) - n_hit}개 — 집안마다 하나)")


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
    out += _table_gap(ref, cf, rows, state=state)
    out += _opp_level(ref, cf, got, state=state, n_tab=n_tab)
    out += _weighted_form(ref, cf, got, state=state, n_tab=n_tab)
    out += _vs_top(ref, cf, got, state=state, n_tab=n_tab)
    return out


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **순위표가 말하는 전력차** — 사용자 지시 2026-10-18
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측(오스틴 vs 밴쿠버): 밴쿠버 **1위 52점** ↔ 오스틴 **14위 31점** 인데
#     확률이 39.4 ↔ 30.6 이었다 — 그 **격차 자체를 세는 변수가 없었다**.
#  🔴 재료는 이미 있다 — 순위표 줄의 `points`·`played`·`wins/draws/losses`.
#     ⚠️ 경기 수가 다를 수 있어 **경기당**으로 고른다(승점/경기 · 득실/경기).
#  🔴 유형은 `strength_gap` 이다 — **선언·배치·λ 표에 다 있는데 쓰는 곳이
#     없었다**(CLAUDE.md #2 의 그 꼴).


def _row_for(ref: MatchRef, rows: list[dict], side: str) -> dict:
    """🔴 그 팀의 순위표 줄 — 이름 맞추기는 `core/teamname.pick` 하나다."""
    from app.core import teamname as _tn
    nm = str(getattr(ref, f"{side}_name", "") or _key(ref, side))
    keys = [str(r.get("name") or "") for r in rows]
    got, _why = _tn.pick(nm, keys)
    for r in rows:
        if got and str(r.get("name") or "") == got:
            return dict(r)
    return {}


def _ppg(row: dict) -> tuple[float | None, float | None, int]:
    """🔴 `(경기당 승점, 경기당 득실차, 경기 수)`. 못 읽으면 `None`."""
    try:
        n = int(row.get("played"))
    except (TypeError, ValueError):
        return None, None, 0
    if n <= 0:
        return None, None, 0
    try:
        pts = float(row.get("points"))
    except (TypeError, ValueError):
        return None, None, n
    gd = None
    for a_key, b_key in (("goals_for", "goals_against"), ("gf", "ga"),
                         ("scored", "conceded")):
        try:
            gd = (float(row[a_key]) - float(row[b_key])) / n
            break
        except (KeyError, TypeError, ValueError):
            continue
    return pts / n, gd, n


def _table_gap(ref: MatchRef, cf: dict, rows: list[dict], *,
               state: RunState) -> list[Variable]:
    """🔴🔴 **전력차** — 순위표의 경기당 승점·득실차. `[Variable]`."""
    want_p, want_g = _num(cf, "ppg_gap"), _num(cf, "gd_gap")
    if want_p is None or want_g is None:
        state.note(f"실력 전력차 — {NONE_MARK} 문턱 표가 없다(`{CONF}`)")
        return []
    box: dict[str, tuple] = {}
    for side in ("home", "away"):
        row = _row_for(ref, rows, side)
        if not row:
            state.note(f"실력 전력차 `{side}` — {NONE_MARK} 순위표에 그 팀 줄이 "
                       "없다(이름을 못 맞췄다)")
            return []
        box[side] = (*_ppg(row), row.get("rank"), row.get("points"))
    (ph, gh, nh, rh, tph), (pa, ga_, na, ra, tpa) = box["home"], box["away"]
    if ph is None or pa is None:
        state.note(f"실력 전력차 — {NONE_MARK} 승점·경기 수를 못 읽었다")
        return []
    out: list[Variable] = []
    if abs(ph - pa) >= want_p:
        side = "home" if ph > pa else "away"
        out.append(_var("TB1", "strength_gap", ref, side,
                        f"{_name(ref, _key(ref, side))} 가 **순위표에서 앞선다** "
                        f"— 경기당 승점 홈 **{ph:.2f}**({rh}위 · {tph}점/"
                        f"{nh}경기) ↔ 원정 **{pa:.2f}**({ra}위 · {tpa}점/"
                        f"{na}경기) · 차 {abs(ph - pa):.2f}(문턱 {want_p:g})"))
        state.note(f"실력 전력차 **발동** — {side} · 경기당 승점 {ph:.2f} ↔ {pa:.2f}")
    else:
        state.note(f"실력 전력차 — 경기당 승점 홈 {ph:.2f} ↔ 원정 {pa:.2f} · 차 "
                   f"{abs(ph - pa):.2f} < {want_p:g}(안 센다)")
    if gh is not None and ga_ is not None and abs(gh - ga_) >= want_g:
        side = "home" if gh > ga_ else "away"
        out.append(_var("TB2", "strength_gap", ref, side,
                        f"{_name(ref, _key(ref, side))} 가 **득실에서 앞선다** — "
                        f"경기당 득실차 홈 **{gh:+.2f}** ↔ 원정 **{ga_:+.2f}**"
                        f"(차 {abs(gh - ga_):.2f} · 문턱 {want_g:g})"))
        state.note(f"실력 득실차 **발동** — {side} · {gh:+.2f} ↔ {ga_:+.2f}")
    elif gh is None or ga_ is None:
        state.note(f"실력 득실차 — {NONE_MARK} 순위표에 득실 칸이 없다")
    else:
        state.note(f"실력 득실차 — 홈 {gh:+.2f} ↔ 원정 {ga_:+.2f} · 차 "
                   f"{abs(gh - ga_):.2f} < {want_g:g}(안 센다)")
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
                 # 🔴 **주어가 유리한 팀**이다 — `goals` 는 **그 주어 기준**으로
                 #    읽힌다(`flat_prob`: `want = side if goals=="up"`).
                 #    ⚠️ 실사고 2026-10-18: `side=="away"` 일 때
                 #       `down` 을 넘겨 **반대쪽을 밀었다**.
                 goals="up")]


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
#       F1 추세(앞 토막 ↔ 최신 토막) · F2 최신 가중 · F4 흔들림
#  ⚠️ **F3(홈·원정 쪼갬)은 지웠다** — 사용자 지시 2026-10-18
#     (*"과거는 홈원정 구분하지 마라"*).
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
    """🔴🔴 **흐름(폼)** — F1 추세 · F2 최신 가중 · F4 흔들림.

    ⚠️ **F3(홈·원정 쪼갬)은 지웠다**(사용자 지시 2026-10-18 — *"과거는
       홈원정 구분하지 마라"*).
    """
    cf = _box("flow")
    out: list[Variable] = []
    box = {s: _seq(facts, ref, s) for s in ("home", "away")}
    if not box["home"] or not box["away"]:
        state.note(f"흐름 — {NONE_MARK} 경기 줄이 없다"
                   f"(홈 {len(box['home'])} · 원정 {len(box['away'])})")
        return out
    out += _trend(ref, cf, box, state=state)
    out += _decay_form(ref, cf, box, state=state)
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
                 # 🔴 **주어가 유리한 팀**이다 — `goals` 는 **그 주어 기준**으로
                 #    읽힌다(`flat_prob`: `want = side if goals=="up"`).
                 #    ⚠️ 실사고 2026-10-18: `side=="away"` 일 때
                 #       `down` 을 넘겨 **반대쪽을 밀었다**.
                 goals="up")]


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
                 # 🔴 **주어가 유리한 팀**이다 — `goals` 는 **그 주어 기준**으로
                 #    읽힌다(`flat_prob`: `want = side if goals=="up"`).
                 #    ⚠️ 실사고 2026-10-18: `side=="away"` 일 때
                 #       `down` 을 넘겨 **반대쪽을 밀었다**.
                 goals="up")]


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **F3 홈·원정 쪼갠 폼은 지웠다** — 사용자 지시 2026-10-18
# ══════════════════════════════════════════════════════════════════
#
#  > **과거는 홈원정 구분하지 마라**
#
#  ⚠️ 종전 `FL3` 은 *"오늘 홈팀은 과거 홈 경기, 원정팀은 과거 원정 경기"* 로
#     쪼개 봤다. 🔴 그 쪼갬을 **안 한다** — 과거 5경기는 **자리를 가리지 않고**
#     본다(그래야 표본이 다섯 그대로 남는다 · 쪼개면 둘·셋으로 줄어 평균이
#     몇 경기에 휘둘렸다).
#  🔴 경기 줄의 `side` 칸은 그대로 있다(지우지 않았다) — 다른 변수가 쓸 수 있다.


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
