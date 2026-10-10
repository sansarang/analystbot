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

from app.core.schema import Card

#: 🔴 §5 — 1겹 전체·이유 문단 글자 상한
CAP_ALL = 900
CAP_REASON = 400

#: 🔴 §1 — 버튼 넷(순서 그대로). ⚠️ 글자를 바꾸면 사용자가 누르던 것이 달라진다
BUTTONS: tuple[tuple[str, str], ...] = (
    ("📖 자세히", "deep"), ("🧩 시나리오", "scen"),
    ("💹 시장 비교", "market"), ("🔄 재분석", "again"))

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
    | 보드 없음 | `보드를 주면 판정` |

    🔴 **순서가 뜻이다** — 시작한 경기가 먼저다(끝난 일에 등급을 적지 않는다).
    """
    if card.started:
        return "이미 시작 — 예측 아님"
    named = graded(card)
    if named:
        best = named[0]
        return f"{line_name(best)} {best.grade}"
    if str(card.board_source or "none") == "none":
        return "보드를 주면 판정"
    return "이 경기는 걸지 않는다"


#: 🔴 등급 **없음**을 뜻하는 글자들 — 표는 `schema.Grade` 가 든다(사본 금지)
NO_GRADE: tuple[str, ...] = ("없음", "보류", "자료부족")


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


def player_pool(card: Card) -> set[str]:
    """🔴 §4(l) — **있는 선수**의 이름 모음(XI · 결장 명단 · 변수 대상).

    ⚠️ 이 모음에 없는 선수를 글에 적으면 **위반**이다(없는 선수 언급 금지).
    """
    out: set[str] = set()
    m = card.match
    for key in (m.home, m.away):
        box = (card.facts.xi or {}).get(key)
        out |= {str(x) for x in (getattr(box, "players", None) or [])}
        out |= {str(x) for x in (getattr(box, "bench", None) or [])}
        out |= {str(x) for x in ((card.facts.squad or {}).get(key) or [])}
    for rows in (card.facts.missing or {}).values():
        out |= {str(getattr(r, "name", "") or "") for r in (rows or [])}
    # 🔴 **핵심 선수도 "있는 선수"** 다 — 검열 (l) 이 그 이름을 막으면 안 된다
    for rows in ((card.facts.standings or {}).get("key_players") or {}).values():
        out |= {str(dict(r).get("name") or "") for r in (rows or [])}
    for v in (card.variables or []):
        if v.target:
            out.add(str(v.target))
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **변수 claim 에서 이름을 뽑는다**(실사고 2026-10-09)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 종전에는 claim 을 `·` 로 쪼개 **조각째** 담고 40자 상한을 뒀다.
        #     🔴 `"Daejeon Hana Citizen 직전 선발 Anton Krivotsyuk"` 은 **45자**라
        #        버려졌고, 그래서 검열 (l) 이 `Anton Krivotsyuk` 을 *"없는 선수"*
        #        로 잡았다 — **거짓 위반**이다.
        #  🔴 이제 이름 모양으로 **뽑는다**(`s9_audit._names_in` 과 같은 그물).
        from app.core.stages.s9_audit import _names_in
        out |= set(_names_in(str(v.claim or "")))
        # ⚠️ 한글 이름은 조사가 붙어 그물에 안 걸린다 — 조각도 **함께** 담는다
        for piece in str(v.claim or "").replace(",", " · ").split("·"):
            said = piece.strip()
            if 2 <= len(said) <= 80 and any(c.isalpha() for c in said):
                out.add(said)
    return {x for x in out if x}


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
    if tail == "반반":
        said.append("세 열이 갈라지지 않아 **어느 쪽도 확신할 근거가 없다**.")
    else:
        said.append(f"우리 열은 {tail} 로 잡힌다.")
    refs.append(["DIR"] if "DIR" in box else [])
    return said, refs


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
    out.append(_probs(card))
    out.append(f"🎯 예상 {_scores(card)}")
    out.append(f"🎯 보드 판정: {_board(card)}")
    out.append(f"⚠️ 뒤집히는 길: {_flip(card)}")
    if buttons:
        out.append(" ".join(f"[{lab}]" for lab, _ in BUTTONS))
    said = "\n".join(x for x in out if x is not None)
    if len(said) <= CAP_ALL:
        return said
    # 🔴 **이유 문단을 줄인다** — 나머지 줄은 버튼 뒤의 깊은 카드가 든다(§5)
    over = len(said) - CAP_ALL
    short = _cap(reason_text(card), max(80, CAP_REASON - over - 1))
    out[4] = f"【이유】 {short}"
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
    kinds = {str(getattr(v, "state", "") or "")
             for v in (card.facts.xi or {}).values()}
    kinds -= {""}
    if not kinds:
        return "없음"
    # 🔴 글자는 `XIState` 가 든다 — 둘 다 `확정` 일 때만 확정이다
    return "확정" if kinds == {"확정"} else "예상"


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


def _probs(card: Card) -> str:
    """🔴 §1 `📊` 줄 — **우리 열**이다. 시장 열이 있으면 **괄호로** 함께."""
    m = card.match
    ours = card.our_prob
    if ours is None:
        return "📊 우리 열이 비었다 — 기준이 없다(시나리오 비율을 쓰지 않는다)"
    box = dict(getattr(card.market, "probs", None) or {})

    def _m(key: str) -> str:
        from app.core import odds
        got = box.get(odds.key_of("win", key))
        return f" ({got:.0%})" if got is not None else ""

    return (f"📊 {m.home_name} {_pct(ours.home)}{_m('home')} · "
            f"무 {_pct(ours.draw)}{_m('draw')} · "
            f"{m.away_name} {_pct(ours.away)}{_m('away')}")


def _scores(card: Card) -> str:
    """🔴🔴 **무게 상위 3개를 그대로**(사용자 지시 2026-10-09(6차) ①).

    > 재가중된 스코어 무게 **상위 3개를 그대로** 쓴다. 방향 판정과 어긋나는
    > 스코어만 있으면 **그 사실을 표시**. `0-0` 이 들어가면 **근거 변수 id** 를
    > 옆에 적는다.

    ⚠️ 실사고 2026-10-09(강원–부천): 무게 1위 `1-2`(away 1.3525)가 빠지고
       `3-0 · 2-0 · 0-0` 이 나갔다 — 작성자가 골랐기 때문이다. 🔴 코드가 고른다.
    """
    from app.core import reweight
    from app.core.stages.s9_audit import score_drivers, top_scores
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
                 if reweight.side_of(*(int(x) for x in s.split("-"))) == side]
        if not agree:
            out += f" ⚠️ **방향({side})과 어긋난다** — 무게가 반대쪽에 있다"
    return out


def _board(card: Card) -> str:
    """🔴 §1 `🎯 보드 판정` — 등급이 없으면 **이유 한 줄**."""
    named = graded(card)
    if named:
        return " / ".join(f"{plain_line(e, card)} **{e.grade}**"
                          for e in named[:3])
    if str(card.board_source or "none") == "none":
        return "걸 줄 없음 — 보드가 없다(보드를 주면 판정한다)"
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
    from app.core import reweight
    out: list[str] = []
    for s in rows:
        for h, a in (s.outcomes or []):
            got = reweight.side_of(int(h), int(a))
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
