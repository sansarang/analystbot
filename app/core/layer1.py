"""🔴🔴 **텔레그램 1겹 카드** — 사용자 지시 2026-10-09(3차).

> 1겹 카드의 **순서와 문체**를 바꾼다. **판정·확률 계산은 건드리지 않는다** —
> 보여 주는 방식만 바꾼다. 결론 한 줄 → 축구 말로 쓴 이유 → 확률·스코어 →
> 보드 판정. 읽는 사람이 **첫 세 줄**에서 결론과 이유를 얻게 한다.

🔴 **이 파일은 수를 만들지 않는다.** 받는 것은 다 센 `Card` 이고, 하는 일은
   ① 사실 목록(`facts_catalog`) ② 헤드라인 문구(`headline`) ③ 글 짜기(`text`)다.
   ⚠️ 확률·생존·등급을 여기서 고치면 *"보여 주는 방식만"* 이 거짓이 된다.

🔴 **헤드라인은 코드가 정한다**(§2 — LLM 아님). 그래서 같은 카드면 같은 문구다.
"""
from __future__ import annotations

import re

from app.core.schema import Card

#: 🔴 §5 — 1겹 전체·이유 문단 글자 상한
# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **900 → 1400** — 상성 엔진 지시서 §3 이 블록을 늘렸다(2026-10-10 여섯째)
# ══════════════════════════════════════════════════════════════════
#
#  §3 의 1겹 목록은 **열한 덩이**다: ⚽ · 📋 · 헤드라인 · ⚔️ 상성(축 넷 + 기여 +
#  주요 변수) · 📊 확률 · 🔎 검증 · 🧪 가설 · 🧑‍🏫 평 · 🔄 조건 · 🆕 · 🎯 보드.
#  🔴 실측 2026-10-10: 그 카드가 **967자**다(이유 문단을 바닥값 80자로 줄인 뒤에도).
#     900 을 지키려면 지시서가 요구한 블록을 **빼야** 하므로 상한을 올린다.
#  ⚠️ 텔레그램 한 메시지 상한은 4,096자다 — 1,400 은 그 안이다.
#  🔴 줄이는 순서는 그대로다: **이유 문단 → (그래도 넘치면) 상성 축 줄**.
CAP_ALL = 1400
CAP_REASON = 400

#: 🔴 §1 — 버튼 셋(순서 그대로). ⚠️ 글자를 바꾸면 사용자가 누르던 것이 달라진다
#  ⚠️ 넷째였던 `💹 시장 비교` 는 **걷혔다**(2026-10-19) — 비교할 시장이 없다.
BUTTONS: tuple[tuple[str, str], ...] = (
    ("📖 자세히", "deep"), ("🧩 시나리오", "scen"),
    ("🔄 재분석", "again"))

#: 🔴 §2 — 방향 문구의 문턱(승률 차 %p). ⚠️ 수를 바꾸면 문구가 달라진다
LEAD_STRONG = 0.15
LEAD_SLIGHT = 0.05

#: 🔴 §2·§4(k) — **단정어 금지**. ⚠️ 이것은 *우리 글*의 금지어다(자료가 아니다)
SURE_WORDS: tuple[str, ...] = (
    "확실", "반드시", "필승", "무조건", "틀림없", "당연히", "승리할 것이다",
    "이길 것이다", "승리한다", "완승", "낙승", "장담")


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x:.0%}"


def direction_words(card: Card) -> str:
    """🔴🔴 §2 **방향 문구** — 우리 열 두 팀 승률 차로 정한다(코드가 정한다).

    | 차 | 문구 |
    |---|---|
    | ≥15%p | `{팀} 우세` |
    | 5~15%p | `{팀} 근소 우세` |
    | <5%p | `반반` |

    ⚠️ *"~승"·"확실"·"필승"* 같은 **단정어는 쓰지 않는다**(§2 마지막 줄).
    🔴 우리 열이 **비면**(기준 없음 · 지시 2026-10-09 ③) 그 사실을 적는다 —
       없는 수로 방향을 말하지 않는다.
    """
    ours = card.our_prob
    if ours is None:
        return "방향 못 정함 — 기준이 없다"
    gap = abs(float(ours.home) - float(ours.away))
    who = card.match.home_name if ours.home >= ours.away else card.match.away_name
    if gap >= LEAD_STRONG:
        return f"{who} 우세"
    if gap >= LEAD_SLIGHT:
        return f"{who} 근소 우세"
    return "반반"


def bet_words(card: Card) -> str:
    """🔴🔴 §2 **걸지 여부 문구** — 등급·보드 상태가 정한다(코드가 정한다).

    | 상태 | 문구 |
    |---|---|
    | 시작한 경기 | `이미 시작 — 예측 아님` |
    | 등급 있음 | `{줄} {등급}` |
    | 등급 없음 | `이 경기는 걸지 않는다` |

    🔴 **순서가 뜻이다** — 시작한 경기가 먼저다(끝난 일에 등급을 적지 않는다).
    ⚠️ 종전에 있던 `보드 없음 → 보드를 주면 판정` 은 **걷혔다**(2026-10-19) —
       배당을 안 받으므로 *"보드를 달라"* 고 할 일이 없고, 보드 없는 경기의 결론은
       **규칙 (가)**(봇 확률만)가 낸다(`core/conclude`).
    """
    if card.started:
        return "이미 시작 — 예측 아님"
    named = graded(card)
    if named:
        # 🔴🔴 A-4 — **확정 XI 전 등급은 `잠정`** 이다(라인업 없는 경기의 등급은
        #    의미가 없다 · 사용자 원칙). 등급 확정은 확정 XI 뒤 재분석에서만.
        from app.core import lineups as _ln
        best = named[0]
        return f"{line_name(best)} {_ln.grade_word(xi_confirmed(card), best.grade)}"
    return "이 경기는 걸지 않는다"


#: 🔴 등급 **없음**을 뜻하는 글자들 — 표는 `schema.Grade` 가 든다(사본 금지)
NO_GRADE: tuple[str, ...] = ("없음", "보류", "자료부족")


#: 🔴🔴 **`XI.state` 는 영어다** — `Literal["confirmed","predicted","none"]`.
#
#  ⚠️⚠️ 실사고 2026-10-10: 이 파일과 `render.py` 가 그 칸을 **`"확정"`(한국어)**
#     과 비교했다. 그 비교는 **영원히 거짓**이므로
#       · 라인업 줄이 늘 `예상` 이었고
#       · 등급이 늘 `잠정` 이었고
#       · 새로 넣은 전략 단계가 **한 번도 돌 수 없었다**.
#     🔴 내가 넣은 계약(`tests/contracts/test_v6_4_strategy.py`)이 그것을 잡았다.
#  🔴 그래서 **옮기는 자리를 하나로** 둔다 — 아래 `XI_KO` 와 `xi_state` 다.
#     ⚠️ `render._XI_KO` 와 같은 표다(사본) — 거기서 이것을 쓰게 고쳤다.
XI_KO: dict[str, str] = {"confirmed": "확정", "predicted": "예상",
                         "none": "없음"}


def xi_state(card: Card) -> str:
    """🔴 그 카드의 **라인업 상태 한 글자**(`확정`·`예상`·`없음`).

    🔴 둘 다 확정일 때만 `확정` 이다(A-4) — 한쪽만 확정이면 `예상` 이다.
    ⚠️ 칸이 비면 `없음`.
    """
    kinds = {str(getattr(v, "state", "") or "")
             for v in (card.facts.xi or {}).values()} - {""}
    if not kinds:
        return "없음"
    if kinds == {"confirmed"}:
        return "확정"
    return XI_KO.get(next(iter(sorted(kinds))), "예상") if len(kinds) == 1 \
        else "예상"


def xi_confirmed(card: Card) -> bool:
    """🔴 A-4 — **확정 XI 인가**(둘 다 확정일 때만 참)."""
    return xi_state(card) == "확정"


def graded(card: Card) -> list:
    """🔴 **등급이 붙은 줄**만, 생존 높은 순. ⚠️ `없음`·`보류`·`자료부족` 은 뺀다."""
    said = [e for e in (card.evals or []) if str(e.grade) not in NO_GRADE]
    said.sort(key=lambda e: -float(e.survival or 0))
    return said


def line_name(ev) -> str:
    """🔴 마켓 줄의 사람 이름 — `BoardLine` 이 든 것을 그대로 쓴다(짓지 않는다)."""
    ln = getattr(ev, "line", None)
    for attr in ("text", "name", "raw"):
        got = str(getattr(ln, attr, "") or "")
        if got:
            return got
    bits = [str(getattr(ln, "market", "") or ""),
            str(getattr(ln, "side", "") or ""),
            ("" if getattr(ln, "point", None) is None
             else f"{getattr(ln, 'point'):g}")]
    return " ".join(x for x in bits if x) or "줄 미상"


def plain_line(ev, card: Card) -> str:
    """🔴🔴 **보드 줄을 사람 말로**(사용자 지시 2026-10-10 D-3).

    > 핸디 +1.5 는 *"{팀} +1.5 = 상대가 2골 차 이상으로 못 이긴다 nn%"*.
    > *"가장 두꺼운 줄"* 이 **방향과 반대 팀 이름**이면 그 뜻을 괄호로 풀어 쓴다.

    ⚠️ 실사고 2026-10-09(강원–부천): 방향은 **강원**인데 가장 두꺼운 줄이
       `handicap Bucheon FC 1995 0.955` 였다 — 한 줄만 읽으면 **반대로 보인다**.
    """
    ln = getattr(ev, "line", None)
    kind = str(getattr(ln, "market", "") or "")
    side = str(getattr(ln, "side", "") or "")
    point = getattr(ln, "point", None)
    sv = float(getattr(ev, "survival", 0) or 0)
    said = line_name(ev)
    if kind == "handicap" and point is not None:
        other = (card.match.away_name if side == card.match.home_name
                 else card.match.home_name)
        n = abs(float(point))
        if float(point) > 0:
            said = (f"{side} +{n:g} = **{other}가 {int(n) + 1}골 차 이상으로 "
                    f"못 이긴다** {sv:.0%}")
        else:
            said = (f"{side} −{n:g} = **{side}가 {int(n) + 1}골 차 이상으로 "
                    f"이긴다** {sv:.0%}")
    elif kind in ("total", "over", "under") and point is not None:
        said = f"{said} = **총 {point:g}골 {'넘는다' if 'over' in (side or kind) else '안 넘는다'}** {sv:.0%}"
    # 🔴 방향과 **반대 팀 이름**이면 그 사실을 괄호로 적는다
    want = dir_side(card)
    if want:
        who = (card.match.home_name if want == "home" else card.match.away_name)
        foe = (card.match.away_name if want == "home" else card.match.home_name)
        if foe and foe in said and who not in said:
            said += f" (⚠️ 방향은 **{who}** 다 — 이 줄은 {foe} 이름이 붙지만 "
            said += "그 팀이 **이긴다는 말이 아니다**)"
    return said


def _nm(card: Card, key: object) -> str:
    """🔴 팀 열쇠 → 보일 이름(열쇠를 글에 적지 않는다)."""
    if str(key) == str(card.match.home):
        return card.match.home_name
    if str(key) == str(card.match.away):
        return card.match.away_name
    return str(key)


def headline(card: Card) -> str:
    """🔴 §1 【헤드라인】 한 줄 — `{방향 문구} · {걸지 여부 문구}`."""
    return f"{direction_words(card)} · {bet_words(card)}"


def dir_side(card: Card) -> str:
    """🔴 방향이 **어느 쪽**인가 — `home`·`away`·`""`(반반·없음).

    ⚠️ 검열 (k) 가 *"마지막 문장이 같은 방향인가"* 를 이 값으로 센다.
    """
    ours = card.our_prob
    if ours is None:
        return ""
    gap = abs(float(ours.home) - float(ours.away))
    if gap < LEAD_SLIGHT:
        return ""
    return "home" if ours.home >= ours.away else "away"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **사실 목록** — §3 작성자 입력이고 §4 검열의 대조표다
# ══════════════════════════════════════════════════════════════════
#
#  🔴 **카드에서만** 뽑는다(§3 *"입력(카드에서만)"*) — 새로 받아 오지 않는다.
#  ⚠️ id 는 **글자로 고정**이다 — 작성자가 `fact_refs` 에 적고 검열이 그것을
#     대조한다. 바꾸면 그 두 곳이 같이 어긋난다.


def _xi_names(one) -> list[str]:
    """🔴 그 XI 의 **선발 이름**(사본 금지: `strategy._names` 와 같은 규칙)."""
    if one is None:
        return []
    return ([str(p.name) for p in (getattr(one, "lineup", None) or [])]
            or [str(x) for x in (getattr(one, "players", None) or [])])


def facts_catalog(card: Card) -> dict[str, dict]:
    """🔴 `{사실 id: {"kind": 종류, "text": 글}}`.

    `kind` 는 검열 (i) 의 **종류**다: `player`·`absence`·`rank`·`h2h`·`form`·
    `fatigue`·`dir`·`scen`.
    """
    out: dict[str, dict] = {}
    m = card.match
    f = card.facts

    # ① 라인업 — 포메이션과 **선수 이름**(선수 사실 (l) 의 대조표)
    for side, name in (("home", m.home_name), ("away", m.away_name)):
        key = m.home if side == "home" else m.away
        box = (f.xi or {}).get(key)
        names = [str(x) for x in (getattr(box, "players", None) or [])]
        if not names:
            continue
        out[f"XI:{side}"] = {
            "kind": "player",
            "text": (f"{name} {getattr(box, 'formation', '') or '포메이션 미상'}"
                     f"[{getattr(box, 'state', '') or '예상'}] "
                     + " · ".join(names))}
        for nm in names:
            out[f"P:{nm}"] = {"kind": "player", "text": f"{name} 선발 {nm}"}

    # ①-b 🔴🔴 **핵심 선수**(지시 2026-10-09(5차) ②) — 시즌 득점·도움 상위 2명
    #    ⚠️ 받아 두고 **안 쓰면 없는 코드**다(CLAUDE.md #2) — 작성자 입력이 그 자리다.
    #    🔴 실측 2026-10-09 J1: 가시마 `Léo` 10 · `Aleksandar Čavrić` 5 ·
    #       감바 `Issam Jebali` 3 · `Deniz Hümmet` 2.
    for key, rows_kp in ((f.standings or {}).get("key_players") or {}).items():
        who = _nm(card, key)
        for p_kp in (rows_kp or []):
            nm_kp = str(dict(p_kp).get("name") or "")
            if not nm_kp:
                continue
            out[f"KEY:{nm_kp}"] = {
                "kind": "player",
                "text": (f"{who} 핵심 선수 {nm_kp} — 시즌 "
                         f"{dict(p_kp).get('stat') or '기록'} "
                         f"{dict(p_kp).get('value')}"
                         + (f"({dict(p_kp).get('matches')}경기)"
                            if dict(p_kp).get("matches") else ""))}

    # ①-c 🔴 **경기당 총골**(§3 총골 기준 층) — 이 경기 기준이 어디서 왔나
    tot = dict((f.standings or {}).get("team_totals") or {})
    if tot:
        out["TOTAL"] = {
            "kind": "form",
            "text": ("경기당 총골 — "
                     + " · ".join(f"{_nm(card, k)} {v.get('total_per_game')}"
                                  f"({v.get('goals_for')}득 {v.get('goals_against')}실 "
                                  f"{v.get('played')}경기)"
                                  for k, v in tot.items())
                     + (f" → 이 경기 기준 "
                        f"{(f.standings or {}).get('match_total_baseline')}"
                        if (f.standings or {}).get("match_total_baseline")
                        else ""))}

    # ② 결장·징계 — 구조 사실과 검증 변수 둘 다
    for team, rows in (f.missing or {}).items():
        for row in (rows or []):
            nm = str(getattr(row, "name", "") or "")
            if not nm:
                continue
            out[f"ABS:{nm}"] = {
                "kind": "absence",
                "text": (f"{_nm(card, team)} {nm}"
                         f"({getattr(row, 'pos', '') or '포지션 미상'}) 결장 — "
                         f"{getattr(row, 'reason', '') or '사유 미상'}")}
    for v in (card.variables or []):
        if v.type in ("absence", "def_absence", "absence_att", "suspension"):
            out[v.id] = {"kind": "absence", "text": v.claim}
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 ⑤ **평소 XI 에서 빠진 선수**(사용자 지시 2026-10-11 ⑤) — `DROP:`
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 검열 카탈로그: 평소 XI 에서 빠진 선수를 **`DROP:id`** 로 넣는다(쇼난
    #  > 가세·도하나). **코드가 계산한 사람은 모델이 써도 위반이 아니다.**
    #
    #  ⚠️ 실사고 2026-10-11(쇼난): 코드가 고른 주장이 `Naoki Kase`·`Kazuki Dohana`
    #     를 말하는데 검열 (l) 이 *"XI·결장 명단·변수 대상에 없다"* 로 그 평을
    #     버렸다 — **코드가 계산한 사람**을 모델이 쓰면 위반이 되는 모순이었다.
    #  🔴 "빠진 선수" = **직전·과거 XI 에 있었는데 오늘 XI 에 없는 사람**이다.
    for side in ("home", "away"):
        key = str(getattr(card.match, side, "") or "")
        now = {str(x) for x in _xi_names((f.xi or {}).get(key))}
        past: set[str] = set()
        for one in [(f.last_xi or {}).get(key),
                    *list((f.past_xi or {}).get(key) or [])]:
            past |= {str(x) for x in _xi_names(one)}
        for nm in sorted(past - now):
            if nm:
                out[f"DROP:{nm}"] = {
                    "kind": "player",
                    "text": (f"{_nm(card, key)} 평소 XI 에 있었는데 오늘 XI 에 "
                             f"없다 — {nm}")}

    # ③ 순위·컷·동기
    look = dict(card.outlook or {})
    # 🔴 게이트가 닫혔으면(시즌 초) **상태를 사실로 주지 않는다**(지시 (5차) ①) —
    #    작성자가 그 글자를 쓰면 검열 (n) 이 잡는다. 애초에 안 주는 것이 맞다.
    if look and not look.get("gate_open", True):
        look = {}
    if look:
        cut = look.get("cut")
        for team, box in dict(look.get("states") or {}).items():
            # 🔴 **쪽은 `s2b` 가 적어 준다** — 이름을 이름과 견주어 홈/원정을
            #    추측하지 않는다(신원 계약 · `tests/test_identity_contract.py`).
            side = str(dict(box).get("side") or "")
            if side not in ("home", "away"):
                continue
            out[f"RANK:{side}"] = {
                "kind": "rank",
                "text": (f"{team} 상태 {box.get('state')} — {box.get('why')}"
                         + (f" · 분할 컷 {cut}위" if cut else ""))}
        reach = dict(look.get("reachable") or {})
        if reach:
            out["REACH"] = {
                "kind": "rank",
                "text": " · ".join(f"{t} 최대 {v}점" for t, v in reach.items())}

    # ④ 맞대결 — 전체와 **올 시즌** 둘(지시 2026-10-09 ①)
    h = dict(f.h2h or {})
    again = dict(h.get("recounted") or {})
    if again.get("n"):
        out["H2H"] = {
            "kind": "h2h",
            "text": (f"맞대결 {again['n']}경기 {again.get('basis')} "
                     f"{again['w']}승 {again['d']}무 {again['l']}패"
                     f"(상대 {again['l']}승)")}
    elif h.get("summary") and h.get("count"):
        w, d, lo = (int(x) for x in h["summary"])
        out["H2H"] = {"kind": "h2h",
                      "text": (f"맞대결 {h['count']}경기 {m.home_name} "
                               f"{w}승 {d}무 {lo}패(상대 {lo}승)")}
    season = list(h.get("season_matches") or [])
    if season:
        out["H2H:season"] = {
            "kind": "h2h",
            "text": ("올 시즌 맞대결 "
                     + " · ".join(f"{x.get('date')} {x.get('home')} "
                                  f"{x.get('score')} {x.get('away')}"
                                  for x in season))}

    # ⑤ 최근 폼 수치 · 일정 피로
    for key, raw in (f.recent or {}).items():
        box = dict(raw)
        side = "home" if str(key) == str(m.home) else "away"
        nm = m.home_name if side == "home" else m.away_name
        bits = [f"최근5 {box.get('form') or ''}".strip()]
        for lab, k in (("득점", "goals_avg"), ("보정", "trimmed_avg"),
                       ("실점", "conceded_avg")):
            if box.get(k) is not None:
                bits.append(f"{lab} {box[k]}")
        # 🔴 **수치가 없으면 싣지 않는다** — 이름만 든 사실은 글이 못 된다(#3:
        #    못 잰 칸은 블록 1 이 이름으로 적는다 · 여기서 빈 글을 만들지 않는다)
        if any(c.isdigit() for c in " ".join(bits)):
            out[f"FORM:{side}"] = {"kind": "form",
                                   "text": f"{nm} " + " · ".join(x for x in bits if x)}
        if box.get("rest_days") is not None:
            out[f"REST:{side}"] = {"kind": "fatigue",
                                   "text": f"{nm} 휴식 {box['rest_days']}일"}

    # ⑥ 방향·확률(우리 열) — 마지막 문장이 이것과 같은 방향이어야 한다
    ours = card.our_prob
    if ours is not None:
        out["DIR"] = {
            "kind": "dir",
            "text": (f"우리 열 {m.home_name} {_pct(ours.home)} · 무 "
                     f"{_pct(ours.draw)} · {m.away_name} {_pct(ours.away)} → "
                     f"{direction_words(card)}")}

    # ⑦ 무게 상위 시나리오 셋의 전개 문장
    rows = sorted(list(getattr(card.hypo, "scenarios", None) or []),
                  key=lambda s: -float(s.strength or 0.0))[:3]
    for s in rows:
        out[f"SCEN:{s.id}"] = {
            "kind": "scen",
            "text": (f"{s.id} "
                     + " · ".join(f"{h2}-{a2}" for h2, a2 in (s.outcomes or []))
                     + f" 무게 {s.strength} — {s.mechanism}")}

    # ⑧ 근거 가능 변수 — 작성자가 숫자를 끌어다 쓸 자리
    for v in (card.variables or []):
        if v.usable_as_basis and v.id not in out:
            out[v.id] = {"kind": "form" if v.type == "recent_pattern" else "other",
                         "text": v.claim}
    return out



def reason_text(card: Card) -> str:
    """🔴 §1 【이유】 문단 — 문장들을 한 문단으로. ⚠️ **400자 상한**(§5)."""
    said = card.reason
    if said is None or not said.sentences:
        return template_reason(card)
    # 🔴🔴 **나열은 1겹에 못 나간다**(사용자 지시 2026-10-09(6차) ④)
    #    > 이어 붙인 나열(`·` 구분 3개 이상, 말줄임표)이 1겹에 나가면 계약 실패로.
    #    ⚠️ 그래서 **나가기 전에** 거른다 — 계약은 그것이 지켜지는지 본다.
    from app.core.stages.s8_comment import listy
    flat = [x for x in said.sentences if listy(str(x.text or ""))]
    if flat and len(flat) == len(said.sentences):
        return template_reason(card)
    if flat:
        rows = [(str(x.text).strip(),
                 {str((facts_catalog(card).get(str(f)) or {}).get("kind") or "")
                  for f in (x.fact_refs or [])} & set(SPECIFIC_KINDS))
                for x in said.sentences if not listy(str(x.text or ""))]
        return join_cap(rows, CAP_REASON)
    box = facts_catalog(card)
    rows = [(str(x.text).strip(),
             {str((box.get(str(f)) or {}).get("kind") or "")
              for f in (x.fact_refs or [])} & set(SPECIFIC_KINDS))
            for x in said.sentences if str(x.text).strip()]
    return join_cap(rows, CAP_REASON)


#: 🔴 §4(i) 가 세는 **고유 사실의 종류** — 줄일 때도 이 종류를 지킨다
SPECIFIC_KINDS: tuple[str, ...] = ("player", "absence", "rank", "h2h", "form")


def join_cap(rows: list[tuple[str, set[str]]], cap: int) -> str:
    """🔴🔴 문장들을 상한 안에 담는다 — **종류가 겹치는 문장부터** 버린다.

    `rows` 는 `(문장, 그 문장이 든 사실 종류)` 다.

    ══════════════════════════════════════════════════════════════════
    🔴 **무엇을 지키나** — ① 첫 문장 ② 마지막 문장 ③ **사실 종류의 다양성**
    ══════════════════════════════════════════════════════════════════

    ⚠️ 실사고 2026-10-09(둘): ① 꼬리를 자르니 **방향을 맺는 마지막 문장**이 잘렸다
       (§3 이 못 박은 자리 · 검열 (k) 가 본다). ② 그래서 가운데를 버리게 고치니
       이번엔 **맞대결 문장**이 날아갔다 — §6 이 대전–전북에서 요구한 셋 중 하나다.
    🔴 그래서 버릴 문장을 **종류로** 고른다: 그 문장을 빼도 **남은 문장들이 같은
       종류를 들고 있는** 문장부터 버린다. ⚠️ 버렸다는 사실은 글자로 남긴다(#3).
    """
    rows = [(t, k) for t, k in rows if t]
    if not rows:
        return ""
    if len(" ".join(t for t, _ in rows)) <= cap:
        return " ".join(t for t, _ in rows)
    keep = list(rows)
    dropped = 0
    while len(keep) > 2 and len(" ".join(t for t, _ in keep)) > cap:
        # 🔴 가운데 후보들 중 **빼도 종류가 안 줄어드는** 문장을 고른다
        mid = list(range(1, len(keep) - 1))
        best, best_loss = None, None
        for i in mid:
            others: set[str] = set()
            for j, (_t, k) in enumerate(keep):
                if j != i:
                    others |= k
            loss = len(keep[i][1] - others)      # 이 문장만 가진 종류 수
            if best_loss is None or loss < best_loss:
                best, best_loss = i, loss
        keep.pop(best if best is not None else len(keep) // 2)
        dropped += 1
    said = " ".join(t for t, _ in keep)
    if dropped:
        said += f" (문장 {dropped}개는 길어서 `📖 자세히` 로 넘겼다)"
    if len(said) <= cap:
        return said
    # ⚠️ 두 문장만 남아도 넘치면 **첫 문장만** 자른다(마지막은 그대로 둔다)
    tail = keep[-1][0]
    room = cap - len(tail) - 1
    if room > 40:
        return _cap(keep[0][0], room) + " " + tail
    return _cap(tail, cap)


def template_reason(card: Card) -> str:
    """🔴🔴 **코드 템플릿 문단**(§4 마지막 줄) — 검열이 두 번 어긋났을 때.

    > 실패하면 코드 템플릿 문단(**핵심 사실 셋을 고정 틀에 넣은** 문장).

    🔴 지어내지 않는다 — 사실 목록에서 **종류가 다른 셋**을 골라 이어 붙인다.
    """
    box = facts_catalog(card)
    want = ("absence", "rank", "h2h", "form", "player")
    picked: list[str] = []
    seen: set[str] = set()
    for kind in want:
        for _id, row in box.items():
            if row["kind"] == kind and kind not in seen:
                picked.append(str(row["text"]))
                seen.add(kind)
                break
        if len(picked) >= 3:
            break
    if not picked:
        return ("이 경기의 고유 사실을 하나도 못 받았다 — 이유 문단을 쓰지 않는다"
                "(블록 1 의 사유를 보라).")
    return _cap(" ".join(template_lines(card)[0]), CAP_REASON)


def plain(said: str) -> str:
    """🔴 사실 글에서 **마크다운·군더더기를 뺀다** — 템플릿 문장에 쓸 꼴.

    ⚠️ 사실 글은 카드 블록용으로 `**굵게**` 와 `·` 를 쓴다 — 문단에 그대로 넣으면
       글이 아니라 표처럼 읽힌다.
    """
    out = " ".join(str(said or "").replace("**", "").split())
    return out.rstrip(" ·,.")


def template_lines(card: Card) -> tuple[list[str], list[list[str]]]:
    """🔴🔴 **코드 템플릿 — 세 문장**(§4 마지막 줄 *"핵심 사실 셋을 고정 틀에"*).

    `(문장들, 문장별 fact_refs)`.

    🔴 **세 문장**이어야 한다 — 종전 템플릿은 한 문장이라 검열 (i)(문장 3~5개)를
       **스스로 어겼다**(실측 2026-10-09: 템플릿이 다시 위반으로 잡혔다).
    ⚠️ 종류가 다른 사실을 고른다 — 그것이 (i) 구체성이 세는 것이다.
    """
    box = facts_catalog(card)
    want = ("absence", "rank", "h2h", "form", "player", "fatigue")
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for kind in want:
        for fid, row in box.items():
            if row["kind"] != kind or kind in seen:
                continue
            text = plain(row["text"])
            # ⚠️ **속 빈 사실은 뺀다** — 팀 이름만 남은 글은 문장이 안 된다
            #    (실측: 폼을 못 받은 경기의 `FORM:home` 이 *"South Korea 최근5"*)
            body = text
            for nm in (card.match.home_name, card.match.away_name):
                body = body.replace(nm, "")
            if len(body.strip(" ·-—")) < 8:
                continue
            rows.append((fid, text))
            seen.add(kind)
            break
        if len(rows) >= 3:
            break
    # 🔴 **틀은 사실 글 + 마침표**다 — ` 다.` 를 붙이면 *"최근5 다."* 처럼
    #    조각으로 읽힌다(실측 2026-10-09 한국–우즈벡 템플릿).
    said = [(text if text.endswith((".", "!", "?")) else text + ".")
            for _fid, text in rows]
    refs = [[fid] for fid, _text in rows]
    # 🔴 **마지막 문장은 방향으로 맺는다**(§3 마지막 줄 · 검열 (k))
    tail = direction_words(card)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **마지막 문장은 상성으로 맺는다**(상성 엔진 지시서 P1·§3)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전에는 `반반` 일 때 *"세 열이 갈라지지 않아 어느 쪽도 확신할 근거가
    #     없다"* 를 적었다 — **세 열이 출발점이던 시절의 말**이고, 검열 (j) 가
    #     *"범용 문장"* 으로 잡는다(실측 2026-10-10).
    #  🔴 지금 확률의 출처는 **상성**이다 → 그 판정(우위 팀·강도)과 **가장 큰 축**
    #     을 적고, 근거는 그 축의 변수 id 로 든다(없으면 방향만).
    said_edge, edge_refs = _edge_tail(card, tail)
    said.append(said_edge)
    refs.append(edge_refs if edge_refs else (["DIR"] if "DIR" in box else []))
    return said, refs


def _edge_tail(card: Card, tail: str) -> tuple[str, list]:
    """🔴 템플릿의 마지막 문장 — **상성 판정 + 가장 큰 축 + 그 축의 변수**."""
    box = dict(getattr(card, "matchup", None) or {})
    mr = box.get("report")
    share = dict(box.get("share") or {})
    refs = dict(box.get("share_refs") or {})
    if mr is None or not share:
        return (f"우리 열은 {tail} 로 잡힌다.", [])
    top = max(share, key=lambda k: abs(float(share[k] or 0.0)))
    who = str(dict(getattr(mr, "verdict", None) or {}).get("edge") or "")
    name = {"home": card.match.home_name,
            "away": card.match.away_name}.get(who, "")
    said = (f"상성은 {name} {dict(mr.verdict).get('strength')}"
            if name else "상성은 **가리지 못했다**")
    got = [str(x) for x in (refs.get(top) or [])][:2]
    return (f"{said} — 가장 큰 축은 {top}"
            f"({float(share[top]):+.1f}%p)이고 우리 열은 {tail} 로 잡힌다.",
            got)


def _cap(said: str, n: int) -> str:
    """🔴 **낱말 경계에서** 자른다. ⚠️ 자른 사실을 글자로 남긴다(#3)."""
    text = " ".join(str(said or "").split())
    if len(text) <= n:
        return text
    head = text[:n - 1]
    if " " in head[n // 2:]:
        head = head[:head.rfind(" ")]
    return head.rstrip(" ,·") + "…"


def text(card: Card, *, buttons: bool = True) -> str:
    """🔴🔴 **1겹 카드 전문**(§1 순서 그대로). ⚠️ 900자 상한(§5).

    > 넘으면 **이유 문단을 줄이고** 나머지는 버튼 뒤로.
    """
    m = card.match
    out: list[str] = []
    out.append(f"⚽ {m.home_name} vs {m.away_name} · {m.competition_short} · "
               f"{_when(card)}")
    out.append(f"📋 라인업 {_xi(card)} — {_again(card)}")
    # 🔴🔴 **경고는 1겹에도 올라온다**(지시 2026-10-09(4차) §2·§3) — 1겹이 기본
    #    카드이므로 여기 없으면 사람이 그 사실을 **못 본다**.
    #    ⚠️ 자리는 **머리 두 줄 뒤**다 — 그 두 줄은 *무슨 경기인가*이고 §1 의 순서가
    #       그것을 먼저 둔다(경고가 끼면 그 순서가 깨진다).
    from app.core.render import warn_lines
    out += list(warn_lines(card))
    out.append("")
    out.append(f"【헤드라인】 {headline(card)}")
    out.append(f"【이유】 {reason_text(card)}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **§3 카드 순서**(상성 엔진 지시서 2026-10-10 여섯째)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚔️ 상성 → 📊 확률(상성) → 🔎 검증 → 🧪 가설 → 🧑‍🏫 평 → 🔄 조건 → 🆕 → 🎯 보드
    #
    #  🔴 **상성이 확률보다 앞**이다 — 확률의 **출처**가 상성이기 때문이다(P1).
    #     ⚠️ 종전에는 확률이 먼저였다(세 열이 출발점이던 시절의 자리).
    said_edge = edge_block(card)
    if said_edge:
        out.append(said_edge)
    # 🔴🔴 **⑯ 1겹 — 상성 줄 아래 `🎯 우선순위`**(수정 지시서 2026-10-12)
    said_pri = str(dict(getattr(card, "matchup", None) or {})
                   .get("axis0_said") or "")
    if said_pri:
        out.append(said_pri)
    out.append(_probs(card))
    # 🔴🔴 **⑯ 1겹 — 확률 줄 아래 `📜 스크립트`**(상태 배율 · 지시서 [2b])
    said_script = str(dict(getattr(card, "matchup", None) or {})
                      .get("state_said") or "")
    if said_script:
        out.append(f"📜 스크립트 — {said_script[:160]}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 §4 — **확정 XI 일 때만** 전략·확률 변화 블록
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 자리는 **확률 줄 바로 뒤**다 — `잠정 → 최종` 이 그 확률을 설명하는 줄이라
    #     떨어져 있으면 읽는 사람이 둘을 잇지 못한다.
    #  ⚠️ **빈 글자는 넣지 않는다** — 넣으면 빈 줄이 생기고 §1 순서 계약이
    #     그것을 센다(실측 2026-10-10: `('📊','🎯','📊',' ')` 로 빨개졌다).
    # 🔴 전략·확률 변화 블록은 **확률 줄 뒤**다(확정 XI 일 때만)
    for said_block in (plan_block(card), move_block(card)):
        if said_block:
            out.append(said_block)
    out.append(f"🎯 예상 {_scores(card)}")
    # 🔴🔴 **⑯ 1겹 — 결론 줄에 반증 요약**(지시서 [3d])
    said_brk = list(getattr(card, "breaks", None) or [])
    if said_brk or str(getattr(card, "stance", "") or ""):
        n_b = sum(1 for c in said_brk
                  if str(getattr(c, "state", "")) == "확인-무너짐")
        n_u = sum(1 for c in said_brk
                  if str(getattr(c, "state", "")) == "미확인")
        hit = [str(getattr(c, "id", "")) for c in said_brk
               if str(getattr(c, "state", "")) == "미확인"][:2]
        out.append(f"🧪 반증 {len(said_brk)}조건: 무너짐 {n_b} · 미확인 {n_u} → "
                   f"{getattr(card, 'stance', '') or '판정 없음'}"
                   + (f"(방아쇠: {', '.join(hit)})" if hit else ""))
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **🔎 검증**(상성 엔진 지시서 §3 카드) — 상성 밖 정보는 여기 선다
    # ══════════════════════════════════════════════════════════════════
    said_ver = verify_block(card)
    if said_ver:
        out.append(said_ver)
    # 🔴🔴 **🧪 가설 검증** — 카드 순서: ⚔️ 상성 → 📊 확률 → 🔎 검증 → 🧪 가설
    said_chk = check_block(card)
    if said_chk:
        out.append(said_chk)
    # ⚠️ **최종 평 블록은 걷었다**(§1 처분 ㉔ · LLM 서술 삭제) — 그 자리에
    #    남는 것은 **뒤집히는 길 한 줄**이다(코드가 짓는다).
    out.append(f"⚠️ 뒤집히는 길: {_flip(card)}")
    # 🔴🔴 §3-4 — **🆕 새 사실(72시간)** 은 1겹에도 올라온다
    #
    #  > 새 뉴스(72시간)는 **판단에 반드시 들어간다**(지시서 원칙 ③).
    #
    #  🔴 1겹이 **기본 카드**다 — 여기 없으면 사람이 그 사실을 못 본다.
    #  ⚠️ 0건일 때도 적는다(그 사실이 §3-4 가 요구한 보고다). 🔴 다만 1겹은
    #     900자 상한이라 **항목 둘까지**만 보이고 나머지는 긴 카드가 든다.
    out.append(_new_facts(card))
    # 🔴 §3 — **보드 판정이 맨 끝**이다(새 사실 뒤)
    out.append(f"🎯 보드 판정: {_board(card)}")
    if buttons:
        out.append(" ".join(f"[{lab}]" for lab, _ in BUTTONS))
    said = "\n".join(x for x in out if x is not None)
    if len(said) <= CAP_ALL:
        return said
    # 🔴 **이유 문단을 줄인다** — 나머지 줄은 버튼 뒤의 깊은 카드가 든다(§5)
    over = len(said) - CAP_ALL
    short = _cap(reason_text(card), max(80, CAP_REASON - over - 1))
    # 🔴 **자리 번호로 찾지 않는다** — 블록을 더하면 그 번호가 밀린다
    #    (⚠️ 실사고가 될 자리였다: §4 블록 둘을 넣자 `out[4]` 가 확률 줄이 됐다)
    for i, line in enumerate(out):
        if str(line or "").startswith("【이유】"):
            out[i] = f"【이유】 {short}"
            break
    return "\n".join(x for x in out if x is not None)


def _when(card: Card) -> str:
    """🔴 `MM/DD(요일) HH:MM` — KST 로 적는다(절대규칙 2: 표시만 KST)."""
    from app import timefmt
    got = card.match.kickoff_utc
    if got is None:
        return "시각 미상"
    kst = timefmt.kst(got)
    days = "월화수목금토일"
    return f"{kst:%m/%d}({days[kst.weekday()]}) {kst:%H:%M}"


def _xi(card: Card) -> str:
    """🔴 `확정|예상` — 둘 중 하나다. ⚠️ 못 받으면 그 사실을 적는다."""
    # 🔴 판정은 `xi_state` 하나다(사본 금지) — 그 함수가 영어 칸을 옮긴다
    return xi_state(card)


def _again(card: Card) -> str:
    """🔴 재분석 시각 — 확정 XI 가 나오는 T-60분(`triggers.XI_MINS` 하나가 든다)."""
    from app import timefmt, triggers
    got = card.match.kickoff_utc
    if got is None:
        return "재분석 시각 미상"
    if "확정" == _xi(card):
        return "확정 XI 반영됨"
    kst = timefmt.kst(got)
    from datetime import timedelta
    at = kst - timedelta(minutes=int(triggers.XI_MINS))
    return f"{at:%H:%M} 이후 `/재분석`"


def _probs_tag(card: Card) -> str:
    """🔴 C10 — 확률 줄 꼬리: **출처(상성)**와 임시 표시."""
    box = dict(getattr(card, "matchup", None) or {})
    got = box.get("prob")
    if got is None:
        return ""
    from app.core import matchup as _mu
    return ("(상성)" + (f" {_mu.PROVISIONAL}" if getattr(got, "provisional",
                                                         False) else ""))


def _probs(card: Card) -> str:
    """🔴 §1 `📊` 줄 — **우리 열**이다.

    ⚠️ 종전에는 시장 열이 있으면 **괄호로** 함께 적었다 — 🔴 시장은 걷혔다
       (2026-10-19)이므로 괄호도 없다.
    """
    m = card.match
    ours = card.our_prob
    if ours is None:
        return "📊 우리 열이 비었다 — 기준이 없다(시나리오 비율을 쓰지 않는다)"

    def _m(key: str) -> str:
        return ""

    # 🔴🔴 §3 카드 — 확률 줄에 **출처(상성)** 와 `🔴 임시` 를 적는다(C10)
    said = _probs_tag(card)
    over = dict(dict(getattr(card, "matchup", None) or {})
                .get("sim") or {}).get("over") or {}
    tail = ("  오버 " + "/".join(f"{float(over[str(x)]):.0%}"
                                 for x in OVER_LINES if str(x) in over)
            if over else "")
    return (f"📊 {said} {m.home_name} {_pct(ours.home)}{_m('home')} · "
            f"무 {_pct(ours.draw)}{_m('draw')} · "
            f"{m.away_name} {_pct(ours.away)}{_m('away')}{tail}")


def _scores(card: Card) -> str:
    """🔴🔴 **무게 상위 3개를 그대로**(사용자 지시 2026-10-09(6차) ①).

    > 재가중된 스코어 무게 **상위 3개를 그대로** 쓴다. 방향 판정과 어긋나는
    > 스코어만 있으면 **그 사실을 표시**. `0-0` 이 들어가면 **근거 변수 id** 를
    > 옆에 적는다.

    ⚠️ 실사고 2026-10-09(강원–부천): 무게 1위 `1-2`(away 1.3525)가 빠지고
       `3-0 · 2-0 · 0-0` 이 나갔다 — 작성자가 골랐기 때문이다. 🔴 코드가 고른다.
    """
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **예상 스코어도 시뮬 분포에서**(지적 ④ — 확률은 한 곳이다)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-10(재현): 최종 확률은 홈 46% 인데 예상 스코어가
    #     `3-3 · 1-2 · 1-1` 로 나와 카드가 **"방향과 어긋난다"** 고 스스로
    #     적었다 — 스코어는 **재가중 시나리오 무게**에서, 확률은 **시뮬**에서
    #     왔기 때문이다(두 생성기).
    #  🔴 시뮬이 스코어 분포를 들고 있으므로 **그 상위 셋**을 쓴다. 그러면 확률·
    #     오버·스코어가 **같은 분포**에서 나온다. ⚠️ 시뮬이 못 돌면 재가중
    #     무게를 쓰고 그 사실을 적는다(#3).
    sim_sc = dict(dict(dict(getattr(card, "matchup", None) or {})
                       .get("sim") or {}).get("scores") or {})
    if sim_sc:
        top = sorted(sim_sc.items(), key=lambda kv: -float(kv[1]))[:3]
        said = " · ".join(f"{int(k[0])}-{int(k[1])}" for k, _v in top)
        return f"{said} (시뮬 분포)"
    rows = top_scores(card.hypo, 3)
    if not rows:
        return "못 골랐다 — 시나리오가 없다"
    side = dir_side(card)
    bits: list[str] = []
    for spot, _w in rows:
        said = spot
        if spot == "0-0":
            # 🔴 `0-0` 은 **근거를 옆에 적는다**(지시 ① 마지막 줄)
            ids = score_drivers(card.hypo, spot)
            said += f"(근거 {', '.join(ids) if ids else '**없다**'})"
        bits.append(said)
    out = " · ".join(bits)
    # 🔴 방향과 **어긋나는 것만** 남았으면 그 사실을 적는다
    if side:
        agree = [s for s, _w in rows
                 if _side_of(*(int(x) for x in s.split("-"))) == side]
        if not agree:
            out += (f" ⚠️ **방향({side})과 어긋난다** — 무게가 반대쪽에 있다"
                    " · 🔴 재가중 무게다(시뮬이 못 돌았다)")
    return out


def _board(card: Card) -> str:
    """🔴 §1 `🎯 보드 판정` — 등급이 없으면 **이유 한 줄**."""
    named = graded(card)
    if named:
        from app.core import lineups as _ln
        ok = xi_confirmed(card)
        return (_ln.conclusion_prefix(ok)
                + " / ".join(f"{plain_line(e, card)} "
                             f"**{_ln.grade_word(ok, e.grade)}**"
                             for e in named[:3]))
    if card.started:
        return "걸 줄 없음 — 이미 시작한 경기다"
    return f"걸 줄 없음 — {_why_none(card)}"


def _why_none(card: Card) -> str:
    """🔴 등급이 **왜** 없나 — 생존 산출이 남긴 사유에서 한 줄."""
    for said in (card.conclusion, *(card.triggers or [])):
        low = str(said or "")
        for mark in ("자료 얇음", "총점 줄 등급 보류", "상한", "손익분기"):
            if mark in low:
                return _cap(low, 60)
    return "문턱을 넘은 줄이 없다"


def _flip(card: Card) -> str:
    """🔴 §1 `⚠️ 뒤집히는 길` — **죽는 시나리오 1~2개를 사람 말로**.

    🔴 방향과 **반대 결과**를 그리는 갈래가 그 길이다. ⚠️ 없으면 그 사실을 적는다
       (지어내지 않는다 · #3).
    """
    side = dir_side(card)
    rows = sorted(list(getattr(card.hypo, "scenarios", None) or []),
                  key=lambda s: -float(s.strength or 0.0))
    out: list[str] = []
    for s in rows:
        for h, a in (s.outcomes or []):
            got = _side_of(int(h), int(a))
            if side and got == side:
                continue
            if not side and got == "draw":
                continue
            out.append(f"{h}-{a} — {_cap(str(s.mechanism or ''), 70)}")
            break
        if len(out) >= 2:
            break
    if not out:
        return "반대 결과를 그린 갈래가 없다 — 세트가 한쪽으로만 쏠렸다"
    return " / ".join(out)


#: 🔴 1겹에 보일 새 사실 **항목 수**(§5 900자 상한) — 나머지는 긴 카드가 든다
NEW_SHOW = 2


def _new_facts(card: Card) -> str:
    """🔴 §3-4 — 1겹의 **🆕 새 사실** 줄. 0건이면 그 사실을 한 줄로 적는다.

    🔴 세는 규칙은 `render.new_facts` 하나다(사본 금지) — 여기서는 **줄이기만** 한다.
    """
    from app.core import render
    rows = render.new_facts(card)
    if not rows:
        return f"{render.NEW_HEAD} — 🔴 0건"
    said = " / ".join(f"{_cap(v.claim, 70)}[{v.id}]" for v in rows[:NEW_SHOW])
    more = f" (+{len(rows) - NEW_SHOW}건은 `📖 자세히`)" if len(rows) > NEW_SHOW \
        else ""
    return f"{render.NEW_HEAD} {said}{more}"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §4 **라인업 전략 · 확률 변화** — 사용자 지시 2026-10-10(둘째)
# ══════════════════════════════════════════════════════════════════
#
#  > 1겹에 새 블록(**확정 XI일 때만**):
#  > 🧠 라인업 전략 / {홈}: {전략} — {근거 한 줄} / {원정}: … / 양상: …
#  > 📊 확률 변화   잠정 → 최종 …

PLAN_HEAD = "🧠 **라인업 전략**"
MOVE_HEAD = "📊 **확률 변화** 잠정 → 최종"
#: 🔴 §4 — 오버 줄에 적는 총점 선들(앞 지시가 1.5/2.5/3.5 로 되돌렸다)
OVER_LINES: tuple[float, ...] = (1.5, 2.5, 3.5)


def plan_block(card: Card) -> str:
    """🔴🔴 §4 — `🧠 라인업 전략` 블록. **확정 XI 가 아니면 빈 글자**(§1).

    ⚠️ 빈 글자를 돌려주는 것은 *"조용한 0"* 이 아니다 — §1 이 *"예상 XI 로는 전략을
       추론하지 않는다"* 고 적었고, 그 사실은 📋 라인업 줄이 이미 말한다.
       🔴 다만 **판정을 버린 경우**(수치와 반대)는 그 사실을 적는다(#3).
    """
    plan = getattr(card, "strategy", None)
    said = str(getattr(plan, "audit", "") or "")
    if plan is None or said in ("", "안 돌았다"):
        return ""
    if said == "확정 XI 전":
        return ""
    if said == "버렸다":
        bad = list(getattr(plan, "violations", None) or [])
        return (f"{PLAN_HEAD} — 🔴 **판정을 버렸다**(수치와 반대다 · §2-2): "
                + " / ".join(bad[:2]))
    m = card.match
    out = [PLAN_HEAD]
    for side, name in (("home", m.home_name), ("away", m.away_name)):
        one = _line_of(plan, side)
        if one is None:
            out.append(f" {name}: ⬜ 판정 없음")
            continue
        # 🔴 `squad_turnover` 는 **사람 말로** 적는다(코드 값은 열거값 그대로)
        from app.core import turnover as _turn
        out.append(f" {name}: **{_turn.verdict_ko(one.strategy)}** — "
                   f"{_cap(str(one.why or ''), 90)}")
    if getattr(plan, "shape", ""):
        out.append(f" 양상: {plan.shape}")
    # 🔴🔴 **선수단 교체 — 기준 약함**(지적 ③) — 1겹에도 올린다. 이 표시가 없으면
    #    사람이 *"김천 우세"* 를 **온전한 기준**으로 읽는다.
    said_w = str(dict(dict(getattr(card, "matchup", None) or {})
                      .get("sim") or {}).get("weak") or "")
    if said_w:
        out.append(f" {_cap(said_w.lstrip(' ·'), 150)}")
    return "\n".join(out)


def _line_of(plan, side: str):
    for one in (getattr(plan, "lines", None) or []):
        if str(getattr(one, "side", "")) == side:
            return one
    return None


def move_block(card: Card) -> str:
    """🔴🔴 §4 — `📊 확률 변화 잠정 → 최종`. 둘이 같으면 **그 사실을 적는다**.

    🔴 오버 줄은 **총골 분포**에서 온다(`shape`) — 없으면 그 칸만 빠진다.
    """
    # 🔴🔴 §4 — 이 블록은 **확정 XI 일 때만** 나간다(전략 블록과 한 묶음이다).
    #    ⚠️ 그렇지 않으면 전략이 없는 카드에도 `잠정 → 최종` 이 찍히고, 그 둘은
    #       늘 같은 수다(읽는 사람에게 거짓 신호다 · 2026-10-10 에 잡았다).
    if str(getattr(getattr(card, "strategy", None), "audit", "") or "") != "통과":
        return ""
    old, new = getattr(card, "prob_before", None), card.our_prob
    if old is None or new is None:
        return ""
    m = card.match
    same = (round(old.home, 4), round(old.draw, 4), round(old.away, 4)) == \
        (round(new.home, 4), round(new.draw, 4), round(new.away, 4))
    out = [MOVE_HEAD + ("  ⬜ **바뀐 것 없다**(전략이 확률을 못 움직였다)"
                        if same else "")]
    out.append(f" {m.home_name} 승 {old.home:.0%} → **{new.home:.0%}** · "
               f"무 {old.draw:.0%} → **{new.draw:.0%}** · "
               f"{m.away_name} 승 {old.away:.0%} → **{new.away:.0%}**")
    said = _over_line(card)
    if said:
        out.append(f" {said}")
    return "\n".join(out)


def _over_line(card: Card) -> str:
    """🔴 §4 — `오버 1.5 / 2.5 / 3.5 nn→nn` 줄. 분포가 없으면 빈 글자.

    ⚠️ **잠정 쪽 오버를 따로 세지 않는다** — 총골 분포는 재가중된 시나리오에서
       나오고, 그 재가중은 최종 확률로 한 번만 돈다. 🔴 그래서 지금 적을 수 있는
       것은 **최종 오버**뿐이고, 그 사실을 글자로 말한다(#3 조용히 넘기지 않는다).
    """
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **오버도 시뮬에서 나온다 — 확률은 한 곳이다**(지적 ④)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-10(재현): 같은 카드에서 `시뮬: 오버 1.5 **72%**` 인데
    #     `📊 확률 변화`의 오버는 **62%** 였다(재가중 분포). 🔴 사용자 지시 ④ 가
    #     *"최종 확률 = 시뮬레이션(묶인 분포) 결과"* 라고 정했으므로 **오버도
    #     그 분포**다. 그래서 `questions/2026-10-10_over_lines_two_generators.md`
    #     의 갈림길은 **A(시뮬이 이긴다)** 로 닫혔다.
    #  ⚠️ 시뮬이 못 돌면 재가중 분포를 쓰고 **그 사실을 적는다**(#3).
    sim = dict(dict(getattr(card, "matchup", None) or {}).get("sim") or {})
    over = dict(sim.get("over") or {})
    where = "시뮬 분포"
    if not over:
        over = dict(dict(getattr(card, "shape", None) or {}).get("over") or {})
        where = "🔴 시뮬이 못 돌아 **재가중 분포**"
    if not over:
        return ""
    said = " · ".join(f"{x} {float(over.get(str(x), 0.0)):.0%}"
                      for x in OVER_LINES if str(x) in over)
    return f"오버 {said} ({where})" if said else ""


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 §5 **⚔️ 상성 블록** — 사용자 지시 2026-10-10(셋째)
# ══════════════════════════════════════════════════════════════════
#
#  > ⚔️ 상성 — {팀}이 {상대}를 이길 수 있나
#  >  폼: {보정 폼 백분위 두 팀 한 줄}
#  >  전술: {무기→약점 한 줄, 꺼진 무기·후반 무기 포함}
#  >  골 내용: {예: "부천 실점 9 중 6골 후반 · 강원 득점 후반 58% → 후반 강원 우위"}
#  >  → 상성 우위: {팀} · 승률 잠정 nn% → 최종 nn% (폼 +x · 전술 +y · 골 내용 +z %p)

EDGE_HEAD = "⚔️ **상성**"


def edge_block(card: Card) -> str:
    """🔴🔴 §3 카드 — **상성 블록**(상성 엔진 지시서 2026-10-10 여섯째).

    > ⚔️ 상성 — {우위 팀} {강도}
    >   축0 전력 · 축1 폼 · 축2 전술(꺼진 무기·후반 무기) · 축3 골 내용(분모)
    >   기여: 축0 x · 축1 y · 축2 z · 축3 w %p — 주요 변수: {축별 상위 변수}

    🔴 `MatchupReport` 가 있으면 **그것으로** 적는다(S2 산출이 원본이다).
       ⚠️ 없으면 옛 세 축 글(아래 `_edge_old`)로 떨어지고 그 사실이 보인다.
    """
    box = dict(getattr(card, "matchup", None) or {})
    mr = box.get("report")
    if mr is None:
        return _edge_old(card)
    m = card.match
    verdict = dict(getattr(mr, "verdict", None) or {})
    who = {"home": m.home_name, "away": m.away_name}.get(
        str(verdict.get("edge") or ""), "")
    out = [f"{EDGE_HEAD} — "
           + (f"**{who}** {verdict.get('strength')}" if who
              else f"⬜ **가리지 못했다**({verdict.get('strength')})")]
    names = {"axis0": "축0 전력", "axis1": "축1 폼", "axis2": "축2 전술",
             "axis3": "축3 골 내용"}
    # 🔴 1겹은 **900자 상한**(§5)이다 — 축 줄을 짧게 적고 전문은 긴 카드가 든다
    for key, label in names.items():
        one = mr.axis(key)
        if one.gap is None:
            out.append(f" {label}: ⬜ {_cap(one.why, 34)}")
            continue
        out.append(f" {label}: {one.gap:+.2f}({one.strength}) · "
                   f"{_cap(one.why, 44)}")
    share = dict(box.get("share") or {})
    refs = dict(box.get("share_refs") or {})
    if share:
        out.append(" 기여(리그 평균 대비): "
                   + " · ".join(f"{k} {float(v):+.1f}%p"
                                for k, v in share.items()))
        said = [f"{k.replace('axis', '축')} {','.join(list(v)[:2])}"
                for k, v in refs.items() if v]
        if said:
            out.append(" 주요 변수 " + _cap(" · ".join(said), 80))
    offs = dict(getattr(mr, "off_weapons", None) or {})
    late = dict(getattr(mr, "late_weapons", None) or {})
    if any(offs.values()) or any(late.values()):
        out.append(" 꺼진 무기 "
                   + _cap(" · ".join(f"{k} {len(list(v or []))}"
                                     for k, v in offs.items()), 40)
                   + " · 후반 무기 "
                   + _cap(" · ".join(f"{k} {len(list(v or []))}"
                                     for k, v in late.items()), 40))
    return "\n".join(out)


def _edge_old(card: Card) -> str:
    """🔴🔴 §5 — 상성 블록. **세 축을 못 모았으면 빈 글자**(사유는 긴 카드가 적는다).

    🔴 수는 `s2e_matchup` 이 센 것을 그대로 적는다 — 여기서 다시 세지 않는다.
    """
    box = dict(getattr(card, "matchup", None) or {})
    if not box.get("profile"):
        return ""
    m = card.match
    out = [f"{EDGE_HEAD} — {m.home_name}이 {m.away_name}를 이길 수 있나"]
    said = _form_line(box, card)
    if said:
        out.append(f" 폼: {said}")
    out.append(f" 전술: {_tactic_line(box)}")
    said_g = _goal_line(box, card)
    if said_g:
        out.append(f" 골 내용: {said_g}")
    said_s = _sim_line(box)
    if said_s:
        out.append(f" 시뮬: {said_s}")
    out.append(f" → {_edge_line(box, card)}")
    return "\n".join(out)


def _form_line(box: dict, card: Card) -> str:
    """🔴 §5 — **보정 폼 백분위 두 팀 한 줄**. 백분위가 없으면 지수만 적는다."""
    rows = dict(box.get("form") or {})
    if not rows:
        return ""
    said = []
    for side, name in (("home", card.match.home_name),
                       ("away", card.match.away_name)):
        one = rows.get(side)
        if one is None:
            continue
        idx = one.index()
        pct = one.pct_att
        said.append(f"{name} {idx:+.2f}" if idx is not None else f"{name} 미상"
                    + (f"({pct:.0%})" if pct is not None else ""))
    return " · ".join(said) + "(보정 득실차/경기 · 상대 Elo 보정)"


def _tactic_line(box: dict) -> str:
    """🔴🔴 §5 — 전술 줄: **무기→약점 · 꺼진 무기 · 후반 무기**.

    > 전술: {무기→약점 한 줄, **꺼진 무기·후반 무기 포함**}

    ⚠️ 축2 가 안 돌면 **그 사실을 적는다**(#3 조용한 0 금지).
    """
    rows = [f for f in (box.get("fired2") or []) if not f.watch_only]
    if not rows:
        rows = list(box.get("fired2") or [])
    if not rows:
        return str(box.get("axis2_why") or "") or "⬜ 축2 자료 없음"
    said = " / ".join(f"[{f.rule}] {f.side} {f.text}" for f in rows[:3])
    off = {k: v for k, v in dict(box.get("off") or {}).items() if v}
    late = {k: v for k, v in dict(box.get("late") or {}).items() if v}
    if off:
        said += f" · 🔴 꺼진 무기 {off}"
    if late:
        said += f" · ⏱ 후반 무기 {late}"
    return said


def _goal_line(box: dict, card: Card) -> str:
    """🔴 §5 — **골 내용 한 줄**(사용자 예시 꼴). 발동 규칙을 사람 말로."""
    rows = [f for f in (box.get("fired") or []) if not f.watch_only]
    if not rows:
        rows = list(box.get("fired") or [])
        if not rows:
            return ""
    m = card.match
    said = []
    for f in rows[:3]:
        who = m.home_name if f.side == "home" else m.away_name
        said.append(f"{who} [{f.rule}] {f.text}"
                    + (f" ({_watch()})" if f.watch_only else ""))
    return " / ".join(said)


def _watch() -> str:
    from app.core import goals as _g
    return _g.WATCH_ONLY


def _edge_line(box: dict, card: Card) -> str:
    """🔴🔴 §5 — `상성 우위: {팀} · 승률 잠정 nn% → 최종 nn% (기여 분해)`.

    🔴 기여 분해는 `matchup["share"]` 가 든다(`compare` 가 센다) — 없으면 그
       사실을 적는다. ⚠️ 합이 잠정→최종 변화와 **같아야** 한다(§7 계약).
    """
    m = card.match
    old, new = getattr(card, "prob_before", None), card.our_prob
    who = _edge_team(box, card)
    head = (f"상성 우위: **{who}**" if who
            else ("상성 우위: ⬜ **안 쓴다**(⑤ — 축이 갈렸거나 최종 확률과 "
                  f"어긋난다) · 표 {edge_votes(box)}"))
    if old is None or new is None:
        return head + " · 승률 비교는 **잠정 열이 없어** 못 적는다"
    said = (f" · {m.home_name} 승 잠정 {old.home:.0%} → 최종 "
            f"**{new.home:.0%}**")
    share = dict(box.get("share") or {})
    if share:
        said += (" (" + " · ".join(f"{k} {float(v):+.1f}%p"
                                   for k, v in share.items()) + ")")
    else:
        said += " (기여 분해 — 🔴 적합 전이라 못 쪼갠다)"
    return head + said


def _edge_team(box: dict, card: Card) -> str:
    """🔴🔴 §5 — **상성 우위 팀**은 *세 축을 합친 결과*다(사용자 지시 2026-10-10 ⑤).

    > 세 축을 합친 결과로만 "상성 우위"를 정한다(**규칙 하나·두 개로 정하지
    > 않는다**). **최종 확률 방향과 다르면 쓰지 않는다.**

    ⚠️ 실사고 2026-10-10(김천–안양): 축3 규칙 **둘**(T10·T11)만 세서 *"상성 우위
       안양"* 이라고 적었다 — 그런데 축1 폼은 김천이 **1.1 이나 좋았고**(−0.17 대
       −1.30) 최종 확률도 김천이 높았다(38% 대 34%). 카드 한 장이 **서로 반대되는
       두 말**을 했다(사용자가 잡았다).
    🔴 이제 셋을 더한다: **축1 폼 차 · 축2 발동 · 축3 발동**. 그리고 방향이 최종
       확률과 **어긋나면 빈 글자**를 돌려준다(그 사실은 `_edge_line` 이 적는다).
    """
    side = edge_side(box, card)
    if not side:
        return ""
    return card.match.home_name if side == "home" else card.match.away_name


#: 🔴 ⑤ — 축1 이 **의견을 내는** 최소 폼 차(경기당 득실차). 이보다 작으면 **기권**이다
FORM_MIN = 0.1


def edge_votes(box: dict) -> dict:
    """🔴🔴 ⑤ — **축마다 한 표**. `{"축1": "home"|"away"|"", …}`.

    🔴 **무게를 매기지 않는다** — 축을 견주는 계수는 적합한 적이 없고, 지어낸
       계수로 *"폼 1.1 이 규칙 둘보다 크다"* 를 정하면 그것이 곧 환각이다.
       그래서 **표를 세고**, 갈리면 **안 쓴다**(아래 `edge_side`).
    ⚠️ 의견이 없는 축은 **빈 글자**(기권)다 — 0 을 홈/원정 어느 쪽으로도 보내지
       않는다(#3 조용한 0 금지).
    """
    out = {"축1": "", "축2": "", "축3": ""}
    form = dict(box.get("form") or {})
    h = form.get("home").index() if form.get("home") else None
    a = form.get("away").index() if form.get("away") else None
    if h is not None and a is not None and abs(float(h) - float(a)) >= FORM_MIN:
        out["축1"] = "home" if float(h) > float(a) else "away"
    for name, rows in (("축2", box.get("fired2") or []),
                       ("축3", box.get("fired") or [])):
        tally = {"home": 0, "away": 0}
        for f in rows:
            if f.watch_only:        # 🔴 관찰만은 확률을 안 움직인다 → 안 센다
                continue
            tally[str(f.side)] = tally.get(str(f.side), 0) + 1
        if tally["home"] != tally["away"]:
            out[name] = "home" if tally["home"] > tally["away"] else "away"
    return out


def edge_side(box: dict, card: Card) -> str:
    """🔴🔴 ⑤ — **세 축이 한 쪽을 가리킬 때만** 그 쪽이다. 아니면 빈 글자.

    > 세 축을 합친 결과로만 "상성 우위"를 정한다(**규칙 하나·두 개로 정하지
    > 않는다**). **최종 확률 방향과 다르면 쓰지 않는다.**

    ⚠️ 실사고 2026-10-10(김천–안양): 축3 규칙 둘이 *"안양"* 을 말했고 축1 폼은
       김천을 **1.13** 앞세웠다 — 그런데 카드는 *"상성 우위 안양"* 만 적었다.
    🔴 지금은 **축이 갈리면 안 쓴다**(둘 다 맞을 수는 없다). 그리고 최종 확률이
       더 높게 본 팀의 **반대쪽**은 어떤 경우에도 안 쓴다 — `반반` 일 때도 그렇다
       (⚠️ 그 구멍으로 김천–안양이 빠져나갔다: 38% 대 34% 는 `반반` 이다).
    """
    votes = [v for v in edge_votes(box).values() if v]
    if not votes or len(set(votes)) != 1:
        return ""
    side = votes[0]
    ours = card.our_prob
    if ours is not None:
        mine = float(ours.home if side == "home" else ours.away)
        other = float(ours.away if side == "home" else ours.home)
        if mine < other:
            return ""
    return side


def _sim_line(box: dict) -> str:
    """🔴🔴 §4 — **분 단위 시뮬레이션** 한 줄. 안 돌았으면 그 사유를 적는다.

    > 90분을 분 단위로 시뮬레이션 … 승무패, 오버 1.5/2.5/3.5, **"선제골 팀이
    > 이길 확률"** 까지.
    """
    said = dict(box.get("sim") or {})
    if not said:
        return ""
    if said.get("home") is None:
        return str(said.get("why") or "")[:110]
    over = dict(said.get("over") or {})
    got = (f"승무패 {float(said['home']):.0%}/{float(said['draw']):.0%}/"
           f"{float(said['away']):.0%}")
    if over:
        got += " · 오버 " + " · ".join(
            f"{x} {float(over.get(x, 0)):.0%}" for x in ("1.5", "2.5", "3.5"))
    if said.get("first_wins") is not None:
        got += f" · 선제골 팀 승 {float(said['first_wins']):.0%}"
    return got


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **최종 평 블록** — 사용자 지시 2026-10-10(넷째) §4
# ══════════════════════════════════════════════════════════════════
#
#  > 🧑‍🏫 최종 평 — {verdict}
#  >  {one_line}
#  >  · {key_point 1: 주장 — 메커니즘}
#  >  · {key_point 2}
#  >  · {key_point 3}
#  >  📈 흐름: {전반} / {후반}   ⏱ 승부처: {decisive_moment}
#  >  🔄 뒤집히는 조건: {flip_condition}
#
#  🔴 **빈 글자면 블록을 안 낸다** — 1겹의 줄 순서 계약이 빈 줄을 센다.
#  🔴 주장은 **셋까지**다(1겹 상한) — 나머지는 긴 카드가 든다(§4 둘째 덩이).

SAY_HEAD = "🧑‍🏫 **최종 평**"
#: 🔴 1겹에 올리는 주장 수 — 지시서 §4 가 보인 모양(점 셋)
SAY_POINTS = 3
#: 🔴🔴 1겹 한 줄 상한 — ⚠️ 실측 2026-10-10(강원–부천): 메커니즘이 한 줄에 **250자**
#  였다. 셋이면 그것만 750자이고 1겹 상한(`CAP_ALL` 900)을 혼자 다 먹는다.
#  🔴 **긴 카드가 전문을 든다**(`render.say_long`) — 1겹은 자른 글이고, `_cap` 이
#     자른 사실을 `…` 로 남긴다(#3 조용히 줄이지 않는다).
SAY_CAP_LINE = 120
SAY_CAP_ONE = 140


def _unlabel(said: object, label: str) -> str:
    """🔴 글 앞에 모델이 **스스로 붙인 딱지**를 뗀다(`뒤집히는 조건: …`).

    ⚠️ 글자를 고치는 것이 아니다 — **중복된 딱지만** 떼고 나머지는 그대로다.
    """
    got = str(said or "").strip()
    for head in (f"{label}:", f"{label} —", f"{label} -", f"{label}은",
                 f"{label}는"):
        if got.startswith(head):
            return got[len(head):].strip(" :—-")
    return got


CHECK_HEAD = "🧪 **가설 검증**"
#: 🔴 1겹에 올리는 줄 수(지시서가 적은 상위 3개)
CHECK_LINES = 3


def check_block(card: Card) -> str:
    """🔴 §카드 — 지지·반박 수와 상위 세 줄. ⚠️ 검증을 안 했으면 **빈 글자**."""
    box = dict(getattr(card, "check", None) or {})
    rows = list(box.get("rows") or [])
    if not rows:
        return ""
    from app.core import signals as _sg
    counts = dict(box.get("counts") or {})
    head = (f"{CHECK_HEAD} — 지지 {int(counts.get(_sg.OK, 0))} · 반박 "
            f"{int(counts.get(_sg.NO, 0))} · 판단 불가 "
            f"{int(counts.get(_sg.NA, 0))}")
    if str(box.get("stale") or ""):
        head += f"  {_cap(str(box['stale']), 90)}"
    # 🔴 **못 센 칸**은 카드가 적는다(#3) — ⚠️ 모델에 가는 글에는 안 섞는다
    for one in list(box.get("gaps") or [])[:1]:
        head += f" · {_cap(str(one), 60)}"
    out = [head]
    # 🔴 **지지 → 반박** 순으로 올린다(평이 쓰는 것이 먼저다)
    want = [r for r in rows if dict(r).get("verdict") == _sg.OK]
    want += [r for r in rows if dict(r).get("verdict") == _sg.NO]
    for one in want[:CHECK_LINES]:
        said = dict(one)
        mark = "✅" if said.get("verdict") == _sg.OK else "❌"
        out.append(f" {mark} {_cap(str(said.get('text') or ''), 70)}"
                   f" — {_cap(str(said.get('signal') or ''), 40)}"
                   f" · 시뮬 {said.get('value')}"
                   + (f" · {said.get('cause')}" if said.get("cause") else ""))
    return "\n".join(out)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **🔎 검증 블록** — 상성 엔진 지시서(2026-10-10 여섯째) §3 카드
# ══════════════════════════════════════════════════════════════════
#
#  > 🔎 검증 — 같은 방향 n · 반대 n — 반대: {출처 — 원인} · 등급 영향
#
#  🔴 **확률을 안 바꾼다**(S5) — 등급만 움직이고 그 사실을 적는다.

VERIFY_HEAD = "🔎 **검증**"


def verify_block(card: Card) -> str:
    """🔴 §3 — 검증 요약 한 줄 + 반대 출처(둘까지) + 등급 영향."""
    box = dict(getattr(card, "check", None) or {})
    if "sources" not in box:
        return ""                      # 🔴 S5 를 안 돌렸다(그 사실은 긴 카드가 적는다)
    rows = list(box.get("sources") or [])
    if not rows:
        # 🔴🔴 **0건이면 왜 0건인지 적는다** — ⚠️ 실측 2026-10-10: `같은 방향 0 ·
        #    반대 0` 만 찍혀 *"검증했는데 아무 말이 없었다"* 로 읽혔다. 실은
        #    **출처가 하나도 없었다**(① 기준이 없고 ② 배치 변수도 없었다).
        from app.core import routing
        got = getattr(card, "varset", None)
        n = sum(len(got.of(x)) for x in routing.VERIFY) if got else 0
        return (f"{VERIFY_HEAD} — ⬜ **출처 0건** · ② 검증 자리 변수 {n}개 · "
                "① 기준 확률 "
                + ("있다" if getattr(card.base_prob, "probs", None) is not None
                   else "**없다**"))
    same = [r for r in rows if dict(r).get("dir") == "같음"]
    against = [r for r in rows if dict(r).get("dir") == "반대"]
    out = [f"{VERIFY_HEAD} — 같은 방향 {len(same)} · 반대 {len(against)}"]
    for one in against[:2]:
        said = dict(one)
        out.append(f" ✖ {said.get('src')} {said.get('name')} — "
                   f"{said.get('cause') or '원인 미분류'} · 크기 "
                   f"{said.get('size')} · {_cap(str(said.get('why') or ''), 60)}")
    grade = dict(box.get("grade") or {})
    if grade.get("why"):
        out.append(" 등급 영향: " + _cap(" / ".join(grade["why"]), 120))
    else:
        out.append(" 등급 영향: ⬜ 없다")
    return "\n".join(out)


# 🔴 **`player_pool` 을 지웠다** — 오늘 되살렸는데 **부르던 곳이 옛 글
#    경로**(`stages/s9_audit` 검열 (j))였다. 그 모듈을 걷자 다시 고아가 됐다
#    (사용자 지시 2026-10-17 *"옛 코드는 더이상 필요하지 않다"* · #2).


#: 🔴 라틴 문자 이름 모양 — 옛 `s9_audit` 에서 함께 옮겼다(사본이 아니다)
_LATIN_NAME = re.compile(r"\b[A-Z][a-z]+(?:[ -][A-Z][a-z]+)+\b")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **옛 `s9_audit` 에서 옮겨 온 코드 도움함수들**(§1 처분 · 2026-10-12)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ `s9_audit` 은 **최종 평 LLM 검열** 모듈이었고 그 평이 지워졌다.
#  🔴 그런데 아래 셋은 **코드 계산**이고 1겹이 쓴다 — 함께 지우면 1겹의
#     점수 줄이 사라진다. 그래서 **쓰는 곳으로 옮겼다**(사본이 아니다).

def _nums(said: str) -> list[str]:
    """🔴 글에서 **숫자**를 뽑는다(§4-1 (f)) — 골·경기 수·%·날짜."""
    return re.findall(r"\d+(?:[.,]\d+)?", str(said or ""))




def top_scores(hypo: object | None, n: int = 3) -> list[tuple[str, float]]:
    """🔴🔴 **무게 상위 스코어 n개**(사용자 지시 2026-10-09(6차) ①) — 순서 그대로.

    > 예상 스코어: **재가중된 스코어 무게 상위 3개를 그대로 쓴다**(지금은 무게 1위
    > 갈래를 빼고 고른다).

    ⚠️ 실사고 2026-10-09(강원–부천): 무게 1위가 `C 1-2·0-1`(away 1.3525)인데 예상
       스코어가 `3-0 · 2-0 · 0-0` 이었다 — **1위 갈래가 빠졌다**(작성자가 골랐다).
    🔴 그래서 **코드가 고른다** — 작성자는 그 목록을 받아서 글만 쓴다.
    """
    box: dict[str, float] = {}
    for sc in (hypo.scenarios if hypo else []):
        pairs = list(sc.outcomes or [])
        if not pairs:
            continue
        share = float(sc.strength or 0.0) / len(pairs)
        for h, a in pairs:
            key = f"{h}-{a}"
            box[key] = box.get(key, 0.0) + share
    return sorted(box.items(), key=lambda kv: (-kv[1], kv[0]))[:max(0, int(n))]



def score_drivers(hypo: object | None, spot: str) -> list[str]:
    """🔴 그 스코어를 그린 갈래들의 **근거 변수 id**(지시 ① 마지막 줄).

    > `0-0` 이 들어가면 **근거 변수 id 를 옆에 적는다**.
    """
    out: list[str] = []
    for sc in (hypo.scenarios if hypo else []):
        if spot not in {f"{h}-{a}" for h, a in (sc.outcomes or [])}:
            continue
        # 🔴 칸 이름은 `driver_vars` 다(`drivers` 가 아니다 — 추측하면 조용히 빈다)
        for vid in (getattr(sc, "driver_vars", None) or []):
            if str(vid) not in out:
                out.append(str(vid))
    return out



def _top_spots(hypo: object | None, n: int) -> set[str]:
    """🔴 **스코어 무게 상위 n개** — 갈래 무게를 스코어 수로 나눠 센다."""
    box: dict[str, float] = {}
    for sc in (hypo.scenarios if hypo else []):
        pairs = list(sc.outcomes or [])
        if not pairs:
            continue
        share = float(sc.strength or 0.0) / len(pairs)
        for h, a in pairs:
            key = f"{h}-{a}"
            box[key] = box.get(key, 0.0) + share
    return {k for k, _v in sorted(box.items(), key=lambda kv: -kv[1])[:n]}






def _names_in(said: str) -> list[str]:
    """🔴 문장에서 **선수 이름일 수 있는 조각**을 뽑는다.

    ⚠️ 한글 이름은 조사가 붙어(`안톤이`) 글자만으로는 못 가른다 — 🔴 그래서
       라틴 문자 이름만 뽑고, 한글은 (l) 대신 (j)·(i) 가 사실 id 로 센다.
       그 한계를 여기 적어 둔다(#3 · 지어내지 않는다).
    """
    return [m.group(0).strip() for m in _LATIN_NAME.finditer(str(said or ""))]


def _side_of(home: int, away: int) -> str:
    """🔴 스코어 → 결과. ⚠️ 판정은 `rules.direction_of` **하나**다(사본 금지).

    ⚠️ **옮겨 왔다** — 옛 `app/core/reweight.py`(⑳ 시나리오 재가중)에 있던 함수다.
       그 모듈은 §1 처분으로 지워졌지만 이 **스코어 → 쪽** 변환은 1겹이 쓴다.
    """
    from app import rules
    return str(rules.direction_of([f"{home}-{away}"]) or "")
