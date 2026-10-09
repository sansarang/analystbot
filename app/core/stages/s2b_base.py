"""🔴🔴 **s2b — ① 기준 확률 + ② 라인업 보정.** 네 층 지시서 §3·§4.

```
MatchRef + Facts → (BaseProb, AdjProb)
```

🔴 **LLM 을 부르지 않는다**(§1). 🔴 **실행 중 적합하지 않는다**(§3-2 · 계수는 config).
⚠️ 한 층이 못 돌아도 다른 층을 막지 않는다 — 못 만든 층은 `why` 를 들고 빈 채로 간다.
"""
from __future__ import annotations

import logging
from datetime import date

from app.core import base
#: 🔴 결장 계열 유형은 `compare` 가 든 **목록 하나**를 쓴다(사본 금지 · #1)
from app.core.compare import ABSENCE_TYPES
from app.core.schema import (XI, AdjProb, BaseProb, Facts, LineupDelta,
                             MatchRef)
from app.core.state import RunState

logger = logging.getLogger(__name__)

#: 🔴 등급표를 하루에 한 번만 받는다(§3 캐시) — `{날짜: 표}`
_CACHE: dict[str, dict[str, float]] = {}


async def run(ref: MatchRef, facts: Facts, *, state: RunState, net,
              when: date | None = None) -> tuple[BaseProb, AdjProb]:
    """🔴 ①② 를 만든다. ⚠️ 못 만든 사유는 **전부 `why` 에** 남는다(조용한 0 금지)."""
    got = await _base(ref, facts, state=state, net=net, when=when)
    said = _adjust(ref, facts, got, state=state)
    return got, said


def again(ref: MatchRef, facts: Facts, base_p: BaseProb,
          variables: list, *, state: RunState) -> AdjProb:
    """🔴🔴 **검증된 결장 변수까지 넣어 ② 를 다시 센다**(§4-2 세 번째 줄).

    > 오늘 XI — 확정 > 예상 > *"평소 XI − 결장 명단 − **검증된 결장 변수**"*
    > (이 경우 카드에 "추정 XI").

    ⚠️ s2b 는 s5 **앞**에서 돈다 — 그때는 기사에서 검증된 결장(`R1` 김민재 같은 것)을
       아직 모른다. 🔴 그래서 s5 뒤에 **한 번 더** 센다. 네트워크를 안 쓴다(공짜다).
    """
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **②에 넣기 전에 명단 대조를 지난다**(사용자 지시 2026-10-07 §3)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 검증된 결장 변수를 라인업 보정에 넣을 때 대조 결과(정정된 subject)만 쓴다.
    #  > 대조를 통과하지 못한 변수는 ②에 넣지 않는다.
    #
    #  ⚠️ 실측 2026-10-07(멕시코–칠레): **멕시코** 선수 `Gilberto Mora` 가 칠레에
    #     붙어 들어왔다 — 그러면 ②가 **없는 선수를 칠레에서 뺀다**.
    #  🔴 대조 함수는 `s5_verify.in_squad` **하나**다(사본 금지 · 같은 이름 비교).
    from app.core.stages.s5_verify import in_squad
    gone: dict[str, set[str]] = {}
    for v in variables:
        if v.type not in ABSENCE_TYPES or not v.target:
            continue
        if not in_squad(str(v.target), str(v.subject), facts):
            state.note(f"s2b ②(2차) — `{v.target}` 는 그 팀 명단에 없다 → "
                       f"**넣지 않는다**(귀속 미확인 · {v.id})")
            continue
        gone.setdefault(str(v.subject), set()).add(str(v.target))
    if not gone:
        state.note("s2b ②(2차) — 검증된 결장 변수가 없다 · 1차 그대로 둔다")
        return _adjust(ref, facts, base_p, state=state)
    said = ", ".join(f"{k}:{sorted(v)}" for k, v in gone.items())
    state.note(f"s2b ②(2차) — 검증된 결장 변수를 넣는다({said})")
    return _adjust(ref, facts, base_p, state=state, absent=gone)


async def _base(ref: MatchRef, facts: Facts, *, state: RunState, net,
                when: date | None) -> BaseProb:
    """🔴 ① — eloratings 등급 → 승·무·패. ⚠️ 축구가 아니면 **안 만든다**."""
    from app import rules
    from app.collect import elo
    from app.core.stages.s5_verify import comp_kind
    kind = comp_kind(ref, facts)
    if ref.sport != "soccer":
        return BaseProb(why=f"종목이 `{ref.sport}` 다 — ① 은 축구만(§0 범위)",
                        comp_kind=kind)
    neutral, why_n = rules.neutral_venue(ref.competition)
    day = (when or date.today()).isoformat()
    table = _CACHE.get(day)
    source = "eloratings.net"
    if table is None:
        table, why = await elo.ratings(net, when=when or date.today())
        if not table:
            state.note(f"s2b ① 등급표를 못 받았다 — {why}")
            return BaseProb(why=f"기준 없음 — {why}", comp_kind=kind,
                            source=source, data_date=day)
        _CACHE[day] = table
        state.note(f"s2b ① 등급표 {why}")
    home, away = _code_of(ref.home), _code_of(ref.away)
    home_elo = table.get(home) if home else None
    away_elo = table.get(away) if away else None
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **리그 경기는 우리가 계산한 자체 Elo**(사용자 승인 2026-10-06(5차) ③)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 clubelo 는 죽었다(실측) — football-data 과거 결과로 **우리가 굴린** 등급을
    #     쓴다(`app/collect/leagueelo.py` · 하루 1회 갱신 · `var/league_elo/`).
    #  ⚠️ 대표팀 코드(`iso:`)가 없는 경기는 애초에 eloratings 표에 없다 — 그래서
    #     이 길이 **유일한** 기준이다.
    if home_elo is None or away_elo is None:
        if kind.startswith("league:"):
            from app.collect import leagueelo
            comp = kind.split(":", 1)[1]
            # 🔴 **하루 1회 갱신**(승인 ③) — 그날 파일이 없으면 여기서 만든다.
            #    ⚠️ 그날 파일이 있으면 네트워크에 안 간다(`refresh` 가 그것을 본다).
            if not leagueelo.load(comp, when=when):
                await leagueelo.refresh(net, when=when, state=state)
            a, how_a = leagueelo.rating_of(ref.home_name, comps=[comp],
                                           when=when)
            b, how_b = leagueelo.rating_of(ref.away_name, comps=[comp],
                                           when=when)
            if a is not None and b is not None:
                home_elo, away_elo = a, b
                # 🔴 **통로를 지어내지 않는다**(사용자 지시 2026-10-09 ③) — 등급
                #    파일의 `via` 가 어디서 받았는지 말한다. ⚠️ 종전엔 이 줄이
                #    `football-data` 로 **박혀 있어** fotmob 으로 받은 K리그1·J1
                #    카드에 거짓 출처가 찍혔다(#4 추측 금지).
                via = str((leagueelo.load(comp, when=when) or {}).get("via")
                          or "football-data")
                source = f"{via} {comp} 자체 Elo"
                state.note(f"s2b ① 리그 Elo — {ref.home_name} {a:.0f} · "
                           f"{ref.away_name} {b:.0f}({how_a})")
            else:
                state.note(f"s2b ① 리그 Elo 를 못 찾았다 — {how_a} / {how_b}")
    got = base.base_prob(kind=kind, home_elo=home_elo, away_elo=away_elo,
                         neutral=bool(neutral), source=source, data_date=day)
    if got.probs is None:
        state.note(f"s2b ① 기준 없음 — {got.why}"
                   + (f"(중립 판정: {why_n})" if neutral else ""))
    else:
        state.note(f"s2b ① 홈 {got.home_elo:.0f} · 원정 {got.away_elo:.0f} · "
                   f"dr {got.dr:+.0f} → 홈 {got.probs.home:.3f} 무 "
                   f"{got.probs.draw:.3f} 원정 {got.probs.away:.3f} · {got.why}")
    return got


def _code_of(key: str) -> str:
    """🔴 팀 열쇠 → **ISO2 코드**. ⚠️ 이름표에 코드가 없으면 빈 글자(대표팀이 아니다).

    🔴 `_from_cldr` 이 대표팀 이름표에 `iso:KR` 을 붙여 뒀다 — 그것을 그대로 쓴다
       (나라 이름 표를 여기 베끼지 않는다 · #1).
    """
    from app import teamref
    box = teamref.registry().teams.get(str(key))
    if box is None:
        return ""
    for names in box.names.values():
        for nm in names:
            if teamref.is_code(nm) and nm.startswith("iso:"):
                return nm.split(":", 1)[1].upper()
    return ""


def usual_sample(facts: Facts) -> int:
    """🔴 §4-1 — 평소 XI 를 센 **경기 수**(팀마다 센 뒤 **가장 적은 쪽**).

    🔴 사용자 승인 2026-10-06(5차) ②로 직전 경기를 **최대 5개** 따라간다 — 그래서
       이 수가 3 이상이면 ② 가 돈다. ⚠️ 한 팀만 많아도 소용없다(비교가 안 된다).
    ⚠️ `past_xi` 가 비면 옛 꼴(`last_xi` 하나)로 센다 — 1 이다.
    """
    box = facts.past_xi or {}
    if box:
        return min(len([x for x in v if (x.lineup or x.players)])
                   for v in box.values()) if box else 0
    return 1 if any((v.lineup or v.players)
                    for v in (facts.last_xi or {}).values()) else 0


def ranked(rows: list[XI]) -> list[str]:
    """🔴 과거 경기들의 **선발 빈도 순 전체 명단**(동률은 최근 경기 순).

    🔴 `usual_xi` 는 이 목록의 앞 11명이고, **추정 XI** 는 결장자를 뺀 앞 11명이다 —
       그래야 빠진 자리에 **다음 선수가 들어간다**. ⚠️ 그 보충이 없으면 10명짜리
       라인업이 되고 `ΔS` 가 *"한 명이 사라졌다"* 로 읽혀 전력 하락이 과장된다
       (실측 2026-10-06: 김민재 한 명으로 `ΔS −3.78`(−10.4%)이 나왔다).
    """
    seen: dict[str, int] = {}
    order: dict[str, int] = {}
    for i, xi in enumerate(rows):
        for nm in ([p.name for p in (xi.lineup or [])] or list(xi.players or [])):
            seen[nm] = seen.get(nm, 0) + 1
            order.setdefault(nm, i)
    return sorted(seen, key=lambda nm: (-seen[nm], order.get(nm, 99), nm))


def usual_xi(rows: list[XI], *, size: int = 11) -> tuple[list[str], str]:
    """🔴🔴 §4-1 — 최근 N경기의 **선발 빈도 상위 11명**. `(이름들, 사유)`.

    ⚠️ 동률은 **최근 경기에 나온 순서**로 가른다 — 무작위로 고르면 회차마다 평소 XI
       가 흔들려 `ΔS` 가 거짓으로 움직인다.
    """
    said = ranked(rows)
    got = said[:size]
    return got, (f"{len(rows)}경기 선발 빈도 상위 {len(got)}명"
                 f"(명단 {len(said)}명)")


def _adjust(ref: MatchRef, facts: Facts, got: BaseProb, *,
            state: RunState,
            absent: dict[str, set[str]] | None = None) -> AdjProb:
    """🔴 ② — 오늘 XI 가 평소 XI 보다 얼마나 약/강한가(§4).

    ⚠️ **평소 XI 표본이 3경기 미만이면 건너뛴다**(§4-1 원문) — 1경기를 "평소"라고
       부르면 로테이션 한 번이 전력 급락으로 읽힌다. 🔴 지금은 거의 늘 건너뛴다.
    """
    from app.core.stages.s5_verify import comp_kind
    kind = comp_kind(ref, facts)
    values = dict(facts.player_value or {})
    sample = usual_sample(facts)
    if not values:
        why = "② 없음 — 선수 가치를 한 명도 못 받았다"
        state.note(f"s2b {why}")
        return AdjProb(why=why)
    if sample < base.MIN_USUAL_SAMPLE:
        why = (f"② 건너뜀 — 평소 XI 표본이 **{sample}경기**다(최소 "
               f"{base.MIN_USUAL_SAMPLE}경기 · §4-1) · 경기 페이지에서 직전 경기 "
               f"하나까지만 따라간다")
        state.note(f"s2b {why} · 선수 가치 {len(values)}명은 받았다")
        return AdjProb(why=why)
    # 🔴 §4-1 — 평소 XI 는 **선발 빈도 상위 11명**이다(직전 한 경기가 아니다)
    usual: dict[str, list[str]] = {}
    pool_of: dict[str, list[str]] = {}
    for key, rows in (facts.past_xi or {}).items():
        # ⚠️ 이름을 `got` 으로 쓰면 **인자 `got`(BaseProb)을 덮어쓴다** — 실측
        #    2026-10-06: `'list' object has no attribute 'probs'` 로 터졌다.
        names, how = usual_xi(list(rows))
        if names:
            usual[str(key)] = names
            pool_of[str(key)] = ranked(list(rows))
            state.note(f"s2b ② `{key}` 평소 XI — {how}")
    # 🔴 오늘 XI — 확정 > 예상 > **평소 XI − 결장**(§4-2 "추정 XI")
    today: dict[str, list[str]] = {}
    for key in usual:
        xi = (facts.xi or {}).get(key)
        mine = ([p.name for p in (xi.lineup or [])] or list(xi.players or [])) \
            if xi is not None else []
        if mine:
            today[key] = mine
            continue
        gone = {m.name for m in (facts.missing or {}).get(key, [])}
        # 🔴 **검증된 결장 변수**(§4-2) — 기사에서 온 결장도 오늘 XI 에서 뺀다
        gone |= set((absent or {}).get(key, set()))
        # 🔴 결장자를 빼고 **다음 선수로 11명을 채운다**(§4-2 "추정 XI")
        said = [nm for nm in pool_of.get(key, usual[key])
                if not _same_player(nm, gone)][:len(usual[key])]
        if gone and said:
            came = [nm for nm in said if nm not in usual[key]]
            today[key] = said
            state.note(f"s2b ② `{key}` **추정 XI** — 평소 XI 에서 결장 "
                       f"{len(gone)}명을 빼고({', '.join(sorted(gone))}) 다음 "
                       f"선수 {len(came)}명을 채웠다"
                       f"{'(' + ', '.join(came) + ')' if came else ''}")
    # 🔴 포지션 표는 `facts.player_pos` 다(③) — 어댑터가 경기 페이지에서 긁어 둔다
    ds, pct, deltas, est = _deltas(usual, today, values,
                                   pos=dict(facts.player_pos or {}))
    if est > base.MAX_ESTIMATED:
        why = (f"② 표시만 — 값 없는 선수를 {est}명 채웠다(>{base.MAX_ESTIMATED}) → "
               f"**판정에 쓰지 않는다**(§4-3)")
        state.note(f"s2b {why}")
        return AdjProb(why=why, deltas=deltas, delta_s=ds, strength_pct=pct,
                       estimated_players=est)
    return base.adjust(got, kind=kind, delta_s=ds, strength_pct=pct,
                       deltas=deltas, home=ref.home, away=ref.away,
                       estimated=est, why=f"② 평소 XI {sample}경기 · 가치 {len(values)}명")


def _deltas(usual: dict[str, list[str]], today: dict[str, list[str]],
            values: dict[str, float], *, pos: dict[str, str] | None = None
            ) -> tuple[dict[str, float], dict[str, float], list[LineupDelta], int]:
    """🔴 §4-4·§4-6 — `ΔS` 와 **선수별 기여표**. `(ΔS, 변화율, 기여, 채운 수)`.

    🔴 `S = Σ log(가치)` 이고 `ΔS = S(오늘) − S(평소)` 다(포지션 가중 없이 시작 · §4-4).
    ⚠️ 값 없는 선수는 **그 팀 평소 XI 가치의 하위 25%** 로 채우고 채운 수를 센다(§4-3).

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **짝은 같은 포지션끼리만**(사용자 지시 2026-10-06(6차) ③)
    ══════════════════════════════════════════════════════════════════

    > 기여표: 같은 포지션(GK/DF/MF/FW)끼리만 짝짓는다. 같은 포지션 교체가 없으면
    > **"구조 변경"** 으로 표시.

    ⚠️ 실측: 센터백(김민재)이 공격수(황희찬)와 짝지어져 *"−1.07"* 이 나왔다. 그 수는
       수비 손실이 아니라 **다른 자리의 가치 차**였다. 🔴 팀 `ΔS` 는 그대로 쓰고
       (전력 합의 변화는 포지션과 무관하다), **짝만** 포지션으로 묶는다.
    """
    box = dict(pos or {})
    ds: dict[str, float] = {}
    pct: dict[str, float] = {}
    out: list[LineupDelta] = []
    est = 0
    for team, usual_names in usual.items():
        now = today.get(team) or []
        if not now or not usual_names:
            continue
        pool = [v for nm, v in values.items() if nm in usual_names] or \
               list(values.values())
        a, est_a, _ = base.fill_values(list(usual_names), values, pool)
        b, est_b, _ = base.fill_values(list(now), values, pool)
        if not a or not b:
            continue
        s_usual, s_now = base.strength_of(a), base.strength_of(b)
        ds[team] = round(s_now - s_usual, 4)
        pct[team] = base.pct_change(s_now, s_usual)
        est += est_a + est_b
        floor = base.fill_values(["?"], {}, pool)[0]
        gone = [nm for nm in usual_names if nm not in now]
        came = [nm for nm in now if nm not in usual_names]
        out += _pairs(team, gone, came, values, box,
                      floor[0] if floor else 0.0)
    return ds, pct, out, est


def _pairs(team: str, gone: list[str], came: list[str],
           values: dict[str, float], pos: dict[str, str],
           floor: float) -> list[LineupDelta]:
    """🔴 빠진 선수 ↔ 들어온 선수를 **같은 포지션끼리** 짝짓는다(③).

    ⚠️ 포지션을 모르는 선수는 짝을 **못 맺는다** — 그것도 `structural` 이다(모르는
       것을 같은 자리로 가정하지 않는다).
    """
    out: list[LineupDelta] = []
    left = list(came)
    for nm in gone:
        mine = pos.get(nm, "")
        mate = ""
        for cand in left:
            if mine and pos.get(cand, "") == mine:
                mate = cand
                break
        if mate:
            left.remove(mate)
            v_out = values.get(nm) or floor
            v_in = values.get(mate) or floor
            out.append(LineupDelta(
                team=team, out_name=nm, in_name=mate, pos=mine,
                delta_s=round(base.strength_of([v_in])
                              - base.strength_of([v_out]), 4),
                estimated=nm not in values or mate not in values))
            continue
        # 🔴 같은 포지션 교체가 없다 — **구조 변경**이다(§③). 그 선수의 가치만 적는다
        out.append(LineupDelta(
            team=team, out_name=nm, in_name="", pos=mine, structural=True,
            delta_s=round(-base.strength_of([values.get(nm) or floor]), 4),
            estimated=nm not in values))
    for cand in left:
        # ⚠️ 짝 없이 **들어온** 선수도 구조 변경이다(어느 자리를 메웠는지 모른다)
        out.append(LineupDelta(
            team=team, out_name="", in_name=cand, pos=pos.get(cand, ""),
            structural=True,
            delta_s=round(base.strength_of([values.get(cand) or floor]), 4),
            estimated=cand not in values))
    return out


def _same_player(name: str, pool: set[str]) -> bool:
    """🔴 그 이름이 결장 목록에 있나 — **표기가 갈린다**(`Kim Min-jae`·`Min-Jae Kim`).

    ⚠️ 실측 2026-10-06: 기사는 `Kim Min-jae`, fotmob 은 `Min-Jae Kim` 이다. 글자
       그대로 비교하면 **같은 선수를 못 맞춘다** — 그래서 **낱말 집합**으로 센다.
    🔴 성·이름 순서만 다른 경우를 맞추는 것이고, 다른 선수를 같다고 하지 않는다
       (낱말이 **전부** 같아야 한다).
    """
    from app.core.stages.s5_verify import norm
    mine = {w for w in norm(name).replace("-", " ").split() if len(w) > 1}
    for said in pool:
        box = {w for w in norm(said).replace("-", " ").split() if len(w) > 1}
        if mine and box and mine == box:
            return True
    return False


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **경우의 수**(사용자 지시 2026-10-06(7차) §2) — 코드만, LLM 없음
# ══════════════════════════════════════════════════════════════════


def outlook(ref: MatchRef, facts: Facts, *, state: RunState) -> dict:
    """🔴 §2 — 결과 3 × 다른 경기 3 의 순위·구역과 **팀별 상태**.

    > 남은 경기가 있으면 *"이번 경기만 보면"* 과 *"최종 확정"* 둘을 **구분해** 적는다.

    🔴 순위표가 없으면 `{}` 이고 카드가 `unknown` 으로 적는다(지어내지 않는다).
    """
    from app import rules
    from app.core import standing as st
    box = dict((facts.standings or {}).get("group") or {})
    rows = list(box.get("rows") or [])
    if not rows:
        state.note("s2b §2 경우의 수 — 조 순위표가 없다 → `unknown`")
        return {}
    order, zone_doc, verified, src = rules.tiebreak(ref.competition)
    home, away = ref.home_name, ref.away_name
    # 🔴 **같은 라운드 다른 경기** — 우리 경기와 같은 라운드의, 우리가 안 뛰는 경기
    mine = {home.lower(), away.lower()}
    ours = next((f for f in (box.get("fixtures") or [])
                 if not f.get("finished")
                 and {str(f.get("home", "")).lower(),
                      str(f.get("away", "")).lower()} == mine), None)
    rnd = str((ours or {}).get("round") or "")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **순위에 닿는 경기는 전부 넣는다**(사용자 지시 2026-10-09 ①)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 고르는 규칙은 `standing.touching` 이 든다(승점 차가 가까운 순). ⚠️ 표가
    #     `3 × 3^k` 로 커지므로 `rules.OUTLOOK_MAX_OTHER` 가 수를 막고, **뺀 경기는
    #     이름으로** 카드에 남는다(#3 조용한 0 금지).
    other_rows, dropped = st.touching(box, home=home, away=away, round_no=rnd,
                                      cap=rules.OUTLOOK_MAX_OTHER)
    pairs = [(str(r["home"]), str(r["away"])) for r in other_rows]
    cells = st.grid(box, home=home, away=away, order=order, others=pairs)
    # 🔴🔴 **분할 컷** — 있으면 상태를 **컷 안/밖**으로 센다(지시 ① 셋째 줄)
    split = rules.split_rule(ref.competition)
    cut = 0
    if split:
        cut = st.cut_rank(dict(box.get("zones") or {}),
                          titles=[str(x) for x in (split.get("cut_zones") or [])]) \
            or int(split.get("cut_rank_fallback") or 0)
        state.note(f"s2b §2 분할 컷 **{cut}위** — {split.get('why')}")
    states: dict[str, dict] = {}
    for team, is_home in ((home, True), (away, False)):
        said, why = st.state_of(cells, team, is_home=is_home,
                                zones=dict(box.get("zones") or {}), cut=cut)
        margin, mwhy = st.margin_for(box, team=team, rival=away if is_home else home,
                                     order=order, home=home, away=away,
                                     zones=dict(box.get("zones") or {}))
        if margin:
            said, why = "margin_needed", f"{margin}골 차 필요 — {mwhy}"
        states[team] = {"state": said, "why": why, "margin": margin}
        state.note(f"s2b §2 `{team}` **{said}** — {why}")
    left = int(box.get("remaining") or 0)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **확정 여부는 도달 가능한 최대 승점으로**(지시 ① 마지막 줄)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 남은 라운드에서 **도달 가능한 최대 승점**으로 확정 여부를 따진다.
    #
    #  🔴 우리 두 팀의 남은 라운드 수를 센다(이 경기를 **뺀** 수). ⚠️ `remaining` 은
    #     조 전체 남은 경기 수라 팀별 라운드가 아니다 — 일정에서 팀별로 센다.
    fx = list(box.get("fixtures") or [])
    rounds = {t: sum(1 for f in fx
                     if not f.get("finished")
                     and t.lower() in (str(f.get("home", "")).lower(),
                                       str(f.get("away", "")).lower()))
              for t in (home, away)}
    reach = {t: st.reachable(box, team=t, rounds_left=max(0, n - 1))
             for t, n in rounds.items()}
    out = {"group": box.get("group"), "cells": cells, "states": states,
           "verified": verified, "source": src, "zones": dict(box.get("zones") or {}),
           "remaining": left,
           # 🔴 **우리 두 팀에게** 이 경기가 마지막인가(조 전체가 아니다)
           "final": all(n <= 1 for n in rounds.values()),
           "rounds_left": rounds, "reachable": reach,
           "cut": cut, "cut_why": str(split.get("why") or "") if split else "",
           "other": [f"{r['home']} vs {r['away']} ({str(r.get('kickoff_utc') or '')[:16]}Z)"
                     + (f" · 승점차 {r['gap']}" if r.get("gap") is not None else "")
                     for r in other_rows],
           # 🔴 **뺀 경기도 적는다** — 말없이 자르면 "전부 셌다"로 읽힌다
           "other_dropped": [f"{r['home']} vs {r['away']}"
                             + (f" (승점차 {r['gap']})" if r.get("gap") is not None
                                else "")
                             for r in dropped],
           "zone_meaning": zone_doc}
    # 🔴 s6 의 역습 필수형이 **상태**를 봐야 한다 — `Facts` 는 얼어 있어 고칠 수
    #    없으므로 `standings` 표(같은 dict)에 칸을 더해 넘긴다.
    #    ⚠️ 새 칸 이름은 `outlook_states` 다(기존 칸을 덮지 않는다).
    try:
        (facts.standings or {})["outlook_states"] = states
    except Exception:                                       # noqa: BLE001
        state.note("s2b §2 — 상태를 standings 에 못 실었다(s6 역습형이 안 돈다)")
    state.note(f"s2b §2 경우의 수 {len(cells)}칸 · 같은 라운드 다른 경기 "
               f"{len(other_rows)}개 · 남은 경기 {left} · 최종확정 {out['final']} · "
               f"동률규칙 {'확인' if verified else '**가정**'}")
    return out
