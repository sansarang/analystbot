"""🔴🔴 **v6 렌더러 — `Card` 하나만 받는다**(§3 · §5 render).

블록 순서는 `docs/fable/output_spec.md` 의 **열 블록**이다(사용자가 두 번 보낸
출력에서 블록과 순서만 뽑은 규격). 🔴 그 표를 여기 베끼지 않는다 — 블록 제목만
쓰고, 무엇이 들어가는지는 규격이 든다.

⚠️ 실사고 2026-10-06: 옛 렌더러가 폐기 줄을 dict 로 알아 `AttributeError: 'tuple'
   object has no attribute 'get'` 로 **카드 전체를 잃었다**. 🔴 v6 는 받는 것이
   `Card` 한 타입이고 전부 `frozen` 이라 그 꼴 차이가 **존재하지 않는다**.
🔴 **카드는 항상 나온다** — 비어 있는 블록도 *왜 비었나*를 적는다(#3).
"""
from __future__ import annotations

from app.core.schema import Card, Variable

#: 🔴 블록 제목 — 규격의 열 블록. ⚠️ 번호를 건너뛰지 않는다(불변식 1).
TITLES: tuple[str, ...] = (
    "자료 한계 고백", "기준 XI", "결장", "폼", "기준 전력 (데이터)", "경우의 수",
    "뒤집는 변수", "팀별 가설 + 무너지는 조건", "시나리오", "확률 세 열",
    "보드 대입", "결론", "방향 판정", "방아쇠")

#: 🔴 규격 번호 — 축구 완성 지시서 §5 가 **2b·3b** 를 새 블록으로 더했다.
#   ⚠️ 번호를 다시 매기지 않는다(사용자가 블록 번호로 말한다) — `2b`·`3b` 로 적는다.
#   🔴 네 층 지시서 §8 이 **3c(기준 전력)**·**7b(확률 세 열)** 를 더했다 —
#      블록 순서는 그대로 두고 **두 블록만** 끼운다(그 문서가 그렇게 못 박았다).
NUMBERS: tuple[str, ...] = ("1", "2", "2b", "3", "3c", "3b", "4", "5", "6",
                            "7b", "7", "8", "9", "10")


def card_text(card: Card, *, debug: bool = False) -> str:
    """🔴 카드 전문. ⚠️ 블록이 **늘 전부 있다** — 비면 사유가 들어간다.

    🔴 축구 완성 지시서 §5 가 블록 **2b(결장)**·**3b(경우의 수)** 를 더했다.
    """
    out: list[str] = [_head(card)]
    bodies = (_b1(card), _b2(card), _b2b(card), _b3(card), _b3c(card),
              _b3b(card), _b4(card), _b5(card), _b6(card), _b7b(card),
              _b7(card), _b8(card), _b9(card), _b10(card))
    for num, title, body in zip(NUMBERS, TITLES, bodies, strict=True):
        out.append(f"\n**{num}. {title}**\n{body}")
        # 🔴 **결론 바로 아래**가 논평 자리다(지시 ④)
        if num == "8":
            out.append(_comment(card, debug=debug))
    return "\n".join(out)


def debug_text(card: Card) -> str:
    """🔴 긴 카드(`/디버그`) — 같은 블록에 **근거 번호·양상 비중**이 붙는다(지시 ④)."""
    return card_text(card, debug=True)


def _head(card: Card) -> str:
    from app import timefmt
    m = card.match
    # 🔴 표시만 KST 다(절대규칙 2) — 꼴은 `timefmt.kst_label` 하나가 든다(#1)
    head = (f"🏟 **{m.home_name} vs {m.away_name}** · {m.competition_short} · "
            f"{timefmt.kst_label(m.kickoff_utc)}")
    if m.openworld:
        # 🔴 **처음 보는 리그라는 것을 한눈에**(오픈월드 §4 표기)
        head += f"\n🌐 **오픈월드** — 리그: {m.competition} · 팀 열쇠 임시 발급"
    c = card.cost
    head += (f"\n💵 ${c.usd:.4f} · 호출 {c.calls}회 · 출력 {c.out_tokens} "
             f"(추론 {c.reasoning_tokens})")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **확정 XI 전 안내**(사용자 지시 2026-10-06(7차) §7)
    # ══════════════════════════════════════════════════════════════════
    #
    # > 킥오프 **90분 이내**인데 XI 가 `confirmed` 가 아니면 카드 머리에
    # > *"확정 XI 전 — HH:MM KST 이후 /재분석"*.
    #
    # ⚠️ 그 시각은 **킥오프 60분 전**이다(확정 XI 는 보통 그때 나온다 · 축구 §2).
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **피드에 없는 경기면 보드를 달라고 한다**(사용자 지시 2026-10-07 ③)
    # ══════════════════════════════════════════════════════════════════
    #
    # > 피드에 경기가 없을 때(대표팀 친선 등): 카드 머리에
    # > *"시장 피드에 없는 경기 — 보드 캡처를 보내 달라"* 한 줄.
    if not card.market.probs and not card.user_market.probs:
        head += ("\n📋 **시장 피드에 없는 경기 — 보드 캡처를 보내 달라**"
                 "(보드가 없으면 등급을 못 붙인다)")
    said_xi = {v.state for v in (card.facts.xi or {}).values()}
    if said_xi and "confirmed" not in said_xi:
        from datetime import timedelta
        when = m.kickoff_utc - timedelta(minutes=60)
        head += (f"\n⏳ **확정 XI 전** — {timefmt.kst_label(when)} 이후 `/재분석`"
                 f"(지금 XI 는 {'·'.join(sorted(said_xi))})")
    if card.changed:
        # 🔴 **재분석 — 바뀐 것**(축구 완성 지시서 §4-4): 카드 **맨 위**다
        head += "\n\n🔁 **재분석 — 바뀐 것**\n" + "\n".join(
            f"- {x}" for x in card.changed)
    return head


def _b1(card: Card) -> str:
    """블록 1 — 🔴 **이 블록이 비면 그것이 거짓이다.**"""
    out: list[str] = []
    if card.started:
        out.append("🔴 **이미 시작한 경기다 — 예측이 아니다**(등급을 내지 않는다)")
    by: dict[str, int] = {}
    for d in card.drops:
        by[d.reason.value] = by.get(d.reason.value, 0) + 1
    if by:
        out.append("버린 것: " + " · ".join(f"`{k}` {v}건"
                                        for k, v in sorted(by.items())))
    docs_n = card.funnel.counts.get("docs")
    out.append(f"문서 {docs_n if docs_n is not None else '못 쟀다'}건 · 변수 "
               f"{len(card.variables)}개 · 시나리오 "
               f"{len(card.hypo.scenarios) if card.hypo else 0}개")
    # 🔴🔴 **못 받은 칸을 칸별로**(축구 완성 지시서 §2 마지막 줄) — s2 가 센 것을 그대로
    #    ⚠️ 이 줄이 비면 *"다 받았다"* 는 거짓이 된다(#3 조용한 0 금지).
    if card.facts.gaps:
        out.append("못 받은 칸 — " + " · ".join(card.facts.gaps))
    elif not card.facts.xi:
        out.append("⚠️ **확정 XI 를 못 잡았다** — 상한이 그만큼 내려간다")
    # 🔴 충돌은 **채택/버림**을 한 줄로(§1-2)
    for d in card.drops:
        if d.reason.value == "conflict":
            out.append(f"🔴 {d.detail}")
    return "\n".join(f"- {x}" for x in out)


#: 🔴 상태 글자 — 사람이 읽는 꼴(§5 블록 2)
_XI_KO = {"confirmed": "확정", "predicted": "예상", "none": "없음"}


def _b2(card: Card) -> str:
    """블록 2 XI — `{팀} {포메이션} [확정|예상|없음] 감독 {이름}` + 선수 11명(§5)."""
    if not card.facts.xi:
        return "- ⬜ 없다 — 어느 쪽 XI 도 못 받았다(사유는 블록 1)"
    out: list[str] = []
    for key, xi in card.facts.xi.items():
        who = _who(card, key)
        coach = card.facts.coach.get(key)
        head = (f"- **{who}** {xi.formation or '포메이션 미상'} "
                f"[{_XI_KO.get(xi.state, xi.state)}]")
        if coach is not None:
            head += f" 감독 {coach.name}" + (" (임시)" if coach.interim else "")
        out.append(head)
        if xi.lineup:
            # 🔴 포지션 약자를 함께 적는다(§5) — 등번호가 있으면 그것도
            said = " · ".join(
                f"{p.name}({p.pos or '?'}" + (f",{p.number}" if p.number else "")
                + ")" for p in xi.lineup[:11])
            out.append(f"    {said}")
        elif xi.players:
            out.append(f"    {' · '.join(xi.players[:11])}")
        else:
            out.append("    ⬜ 선발 명단 없음")
        for said in xi.conflicts:
            # 🔴 결장 충돌로 뺀 선수는 **그 사실을 적는다**(§2·§5)
            out.append(f"    {said}")
    return "\n".join(out)


def _b2b(card: Card) -> str:
    """블록 2b 결장(새 블록 · §5) — `이름(포지션) — 사유 · 출처 도메인`."""
    if not card.facts.missing:
        return "- ⬜ **결장 명단 미확보**"
    ko = {"injury": "부상", "suspension": "징계", "doubtful": "출전 불확실",
          "international_duty": "대표팀 차출", "other": "사유 미상"}
    out: list[str] = []
    for key, rows in card.facts.missing.items():
        out.append(f"- **{_who(card, key)}**")
        for m in rows:
            dom = (m.source_url.split("/")[2] if m.source_url.count("/") >= 2
                   else "")
            tail = f" · 복귀 {m.returns}" if m.returns else ""
            mark = " ⚠️ 기사" if m.source == "article" else ""
            out.append(f"    {m.name}({m.pos or '?'}) — {ko.get(m.reason, m.reason)}"
                       f"{tail} · {dom}{mark}")
    return "\n".join(out)


def _b3b(card: Card) -> str:
    """🔴🔴 블록 3b **경우의 수** — 사용자 지시 2026-10-06(7차) §2.

    > 결과별 순위·구역, 그리고 **팀별 상태 한 줄**.
    > 예) *"카자흐스탄: must_win(지면 4위 확정적, 비겨도 4위) · 페로: draw_enough"*

    ⚠️ 순위표가 없으면 **그 사실을 적는다**(#3) — 빈 블록은 거짓이다.
    🔴 동률 규칙이 **확인 안 된 대회**면 그 가정을 여기 적는다(금지 조항).
    """
    look = dict(card.outlook or {})
    cells = list(look.get("cells") or [])
    if not cells:
        box = dict(card.facts.standings or {})
        rows = box.get("table") if isinstance(box.get("table"), list) else None
        if not rows:
            return ("- ⬜ 경우의 수를 못 센다 — **순위표가 없다**(`unknown`) · 형식 "
                    f"`{card.facts.match_format}`")
        out = ["| 팀 | 순위 | 승점 | 경기 |", "|---|---|---|---|"]
        for r in rows[:8]:
            row = dict(r) if isinstance(r, dict) else {}
            out.append(f"| {row.get('name', '?')} | "
                       f"{row.get('idx', row.get('rank', '?'))} | "
                       f"{row.get('pts', '?')} | {row.get('played', '?')} |")
        out.append("⚠️ 같은 조 전체 표를 못 받아 **결과별 순위**는 못 센다")
        return "\n".join(out)
    home, away = card.match.home_name, card.match.away_name
    out: list[str] = []
    group = look.get("group") or ""
    out.append(f"- 조 `{group}` · 남은 경기 {look.get('remaining', '?')}개 · "
               + ("**최종 확정 가능**" if look.get("final")
                  else "⚠️ **최종 확정 아니다**(남은 경기가 더 있다)"))
    if look.get("other"):
        out.append("- 같은 라운드 다른 경기: " + " · ".join(look["other"]))
    # ⚠️ 사유가 **여러 줄**로 올 수 있다(yaml 블록) — 한 줄로 눌러 담는다(표가 깨진다)
    src = " ".join(str(look.get("source") or "").split())[:150]
    if not look.get("verified"):
        out.append(f"- ⚠️ **동률 규칙 가정**(승점→득실→다득점) — {src}")
    else:
        out.append(f"- 동률 규칙 **확인됨** — {src}")
    # 🔴 결과별 순위·구역 표 — 같은 라운드 다른 경기가 있으면 열이 셋이다
    has_other = any(c.get("other") for c in cells)
    head = (f"| 이 경기 | 다른 경기 | {home} | {away} |" if has_other
            else f"| 이 경기 | {home} | {away} |")
    out += ["", head, "|---|---|---|---|" if has_other else "|---|---|---|"]
    word = {"home": f"{home} 승", "draw": "무승부", "away": f"{away} 승"}
    for c in cells:
        def _cell(team: str) -> str:
            z = str(c["zones"].get(team, ""))
            return f"{c['ranks'].get(team, '?')}위" + (f" ({z})" if z else "")
        if has_other:
            out.append(f"| {word.get(c['ours'], c['ours'])} | "
                       f"{word.get(str(c.get('other')), str(c.get('other')))} | "
                       f"{_cell(home)} | {_cell(away)} |")
        else:
            out.append(f"| {word.get(c['ours'], c['ours'])} | {_cell(home)} | "
                       f"{_cell(away)} |")
    # 🔴 팀별 상태 한 줄 — 이동 규칙이 **이 글자**를 본다
    said = dict(look.get("states") or {})
    for team in (home, away):
        box = dict(said.get(team) or {})
        if not box:
            continue
        out.append(f"- **{team}: {box.get('state')}** — {box.get('why')}"
                   + (f" · {box.get('margin')}골 차" if box.get("margin") else ""))
    if look.get("zone_meaning"):
        out.append("- 구역 뜻: " + " · ".join(
            f"`{k}` = {v}" for k, v in dict(look["zone_meaning"]).items()))
    if not look.get("final"):
        out.append("- ⚠️ 위 표는 **이번 경기만 보면** 이다 — 남은 경기가 "
                   f"{look.get('remaining')}개라 최종 순위는 그 뒤에 정해진다")
    return "\n".join(out)


def _who(card: Card, key: str) -> str:
    """🔴 열쇠 → **보일 이름**(열쇠는 사람이 못 읽는다)."""
    if key == card.match.home:
        return card.match.home_name
    if key == card.match.away:
        return card.match.away_name
    return key


def _b3(card: Card) -> str:
    """블록 3 폼 — 🔴 **사람이 읽는 꼴**(사용자 지시 2026-10-06 ⑦).

    > 블록 3 을 사람이 읽는 형태로(최근 5경기·평균·보정 평균·휴식).

    ⚠️ 실측 2026-10-06: 어댑터 dict 를 `str()` 로 찍어 `{'team': …, 'sequence': [{…}]}`
       가 카드에 그대로 나갔다 — 맞대결은 `matchUrl` 까지 실려 있었다.
    🔴 **없는 칸은 이름으로** 남긴다(#3) — 못 잰 것과 0 을 가른다.
    """
    f = card.facts
    if not (f.recent or f.standings or f.h2h):
        return "- ⬜ 없다 — 구조 자료를 못 받았다(사유는 블록 1)"
    out: list[str] = []
    for key, raw in f.recent.items():
        box = dict(raw) if isinstance(raw, dict) else {}
        who = (card.match.home_name if key == card.match.home
               else card.match.away_name if key == card.match.away else key)
        last5 = " ".join(str(x) for x in (box.get("last5") or [])) or "못 쟀다"
        got = box.get("recent_scored_avg")
        trim = box.get("recent_trimmed_avg")
        rest = box.get("rest_days")
        bits = [f"최근5 **{last5}**"]  # 🔴 §5: 아래에 경기별 한 줄을 적는다
        bits.append(f"득점 평균 {got}" if got is not None else "득점 평균 못 쟀다")
        if trim is not None and got is not None and float(trim) != float(got):
            # 🔴 **보정했으면 그 사실을 적는다** — 조용히 다른 수를 쓰지 않는다
            bits.append(f"보정 평균 **{trim}**")
        bits.append(f"휴식 {rest}일" if rest is not None else "휴식 못 쟀다")
        for name, label in (("streak_unbeaten", "무패"), ("streak_scored", "연속 득점"),
                            ("streak_winless", "무승")):
            if box.get(name):
                bits.append(f"{label} {box[name]}")
        out.append(f"- **{who}** — " + " · ".join(bits))
        seq = [x for x in (box.get("sequence") or []) if isinstance(x, dict)]
        for x in seq[:5]:
            # 🔴 §5 블록 3 — **경기별 한 줄**이다(한 줄에 몰아 적지 않는다)
            rank = x.get("opponent_rank")
            tail = f"({rank}위)" if rank else ""
            out.append(f"    {x.get('date')} "
                       f"{'홈' if x.get('side') == 'home' else '원정'} "
                       f"{x.get('opponent')}{tail} {x.get('score')}")
    if f.standings:
        # 🔴🔴 **조 순위표는 블록 3b 가 그린다** — 여기서 그 dict 를 찍지 않는다.
        #    ⚠️ 실측 2026-10-07(MLS): `standings["group"]` 이 들어오자 이 줄이
        #       **85,682자**를 쏟아 카드가 읽을 수 없게 됐다(`_short` 가 줄여도
        #       한 줄에 수백 자다). 🔴 블록 3 은 **쪼갠 표·홈 이점**만 적는다.
        said = {k: v for k, v in dict(f.standings).items()
                if k not in ("group", "outlook_states")}
        if said:
            out.append(f"- 순위 — {_short(said)}")
    if f.h2h:
        h = dict(f.h2h)
        got = h.get("summary")
        bits = []
        n = h.get("count")
        # 🔴🔴 **집계가 안 맞으면 그 수를 안 적는다**(사용자 지시 2026-10-07 ③).
        #    ⚠️ s5 는 변수를 안 만들고 블록 1에 적는데, **블록 3 은 그 수를 계속
        #       찍고 있었다**(실측 2026-10-07: *"5승 4무 4패 · 표본 10경기"*).
        #       🔴 보이는 것도 **쓰는 것**이다 — 사람이 그 수로 판단한다.
        ok3 = (isinstance(got, (list, tuple)) and len(got) == 3
               and (n is None or sum(int(x) for x in got) == int(n)))
        if ok3:
            bits.append(f"{got[0]}승 {got[1]}무 {got[2]}패")
        elif isinstance(got, (list, tuple)) and len(got) == 3:
            bits.append(f"⚠️ **전적 안 적는다**(집계 불일치 — 합 "
                        f"{sum(int(x) for x in got)} ≠ 표본 {n})")
        if n is not None:
            bits.append(f"표본 {n}경기")
        if h.get("window_avg_goals") is not None:
            bits.append(f"평균 {h['window_avg_goals']}골")
        if h.get("sample_weight") is not None:
            bits.append(f"표본 무게 {h['sample_weight']}")
        out.append("- 맞대결 — " + (" · ".join(bits) or "못 쟀다"))
    return "\n".join(out)


def _short(box: object, cap: int = 160) -> str:
    """🔴 긴 사전을 **줄여** 적는다 — ⚠️ 줄였다는 사실을 함께 적는다(#3)."""
    said = str(box)
    return said if len(said) <= cap else f"{said[:cap]}… (줄였다 {len(said)}자)"


def _b4(card: Card) -> str:
    """블록 4 변수 — 🔴 **근거 불가 변수는 맨 아래 따로 묶는다**(§5)."""
    if not card.variables:
        return ("- ⬜ 변수 0개 — 🔴 **\"자료가 안 왔다\"와 \"왔는데 못 뽑았다\"는 "
                "다르다**(블록 1 의 사유를 본다)")
    good = [v for v in card.variables if v.usable_as_basis]
    weak = [v for v in card.variables if not v.usable_as_basis]
    out = [_var_line(v) for v in good]
    if weak:
        out.append("")
        out.append("**(근거 불가)** — 맥락으로만 쓴다")
        out += [_var_line(v) for v in weak]
    return "\n".join(out)


def _var_line(v: Variable) -> str:
    """🔴 변수 한 줄 — **승패와 득점 방향을 둘 다** 적는다(사용자 지시 ④).

    ⚠️ 종전엔 `goals_up` 이 승패 칸에 있어 *"어느 팀 쪽인가"* 가 안 보였다.
    """
    rule = f" · [규칙 {v.from_rule}]" if v.from_rule else ""
    goals = {"up": "↑", "down": "↓"}.get(v.goals, "-")
    src = (f"출처 {len(v.doc_ids)}곳" if v.doc_ids else "출처 구조 사실")
    who = f" · 대상 `{v.target}`" if v.target else ""
    return (f"- `{v.id}` [{v.type}] {v.claim} — 승패 **{v.favors}** · "
            f"득점 {goals} · {v.hardness} · {src}{who}{rule}")


def _b5(card: Card) -> str:
    if card.hypo is None or not card.hypo.hypotheses:
        return "- ⬜ 가설이 없다 — DeepSeek 단계가 못 돌았거나 근거 변수가 0개다"
    out = []
    for h in card.hypo.hypotheses:
        who = (card.match.home_name if h.team == "home"
               else card.match.away_name)
        out.append(f"- **{who}**")
        for line in h.reasons:
            out.append(f"  - 이긴다면: {line.text} ({', '.join(line.var_ids)})")
        for line in h.breaks:
            out.append(f"  - 무너지는 조건: {line.text} "
                       f"({', '.join(line.var_ids)})")
    cited = [d for d in (card.hypo.drops or [])]
    for d in cited:
        out.append(f"  - 🔴 버린 줄: `{d.reason.value}` {d.detail}")
    return "\n".join(out)


def _b6(card: Card) -> str:
    if card.hypo is None or not card.hypo.scenarios:
        return "- ⬜ 시나리오가 없다 — 대입할 갈래가 없으면 생존은 뜻이 없다"
    out = []
    for s in card.hypo.scenarios:
        scores = " · ".join(f"{h}-{a}" for h, a in s.outcomes)
        mark = " [보강]" if s.added_by == "code" else ""
        out.append(f"- **{s.id}** ({scores}) {s.type} · 무게 {s.strength}{mark} — "
                   f"{s.mechanism} ← {', '.join(s.driver_vars) or '근거 없음'}")
    return "\n".join(out)


#: 🔴 보드 출처 → 사람이 읽는 말(사용자 지시 2026-10-07 ①)
_SRC_KO = {"user_board": "사용자 보드", "feed": "피드 메인 라인", "none": ""}


def _b7(card: Card) -> str:
    if not card.evals:
        return "- ⬜ 대입한 줄이 없다"
    ids = [s.id for s in (card.hypo.scenarios if card.hypo else [])]
    head = "| 마켓 | " + " | ".join(ids) + " | 생존 | 상한 | 등급 |"
    bar = "|---" * (len(ids) + 4) + "|"
    rows: list[str] = []
    # 🔴🔴 **출처를 적는다** — 보드가 없으면 *"참고 — 보드 없음"*(지시 ②)
    src = str(card.board_source or "none")
    if src == "none":
        rows.append("⏸ **참고 — 보드 없음**(기준선 목록이다 · 등급은 전부 `보류`)")
    else:
        rows.append(f"출처: **{_SRC_KO.get(src, src)}**")
    rows.append("")
    rows += [head, bar]
    extra = set(card.board_extra)
    tail: list[str] = []
    for e in card.evals:
        point = f" {e.line.point}" if e.line.point is not None else ""
        said = (f"{e.line.market} {e.line.side}"
                f"{(' ' + str(e.line.point)) if e.line.point is not None else ''}")
        cells = " | ".join(e.marks.get(i, "?") for i in ids)
        line = (f"| {e.line.market} {e.line.side}{point} | {cells} | "
                f"{e.survival} | {e.cap} | {e.grade} |")
        # 🔴 `추가:` 줄은 **아래 묶음**으로(§4 · 사용자 규칙)
        (tail if said in extra else rows).append(line)
    if tail:
        rows.append("")
        rows.append("**추가 옵션에 있으면**")
        rows += tail
    for said in card.board_bad:
        # 🔴 **못 읽은 줄은 그대로 보인다**(조용히 버리지 않는다 · §4)
        rows.append(f"- 🔴 보드 줄 못 읽음: {said}")
    return "\n".join(rows)


def _comment(card: Card, *, debug: bool = False) -> str:
    """🔴🔴 **종합 논평 블록**(사용자 지시 2026-10-07 ④) — 결론 줄 **바로 아래**.

    ```
    🧭 종합 논평 — {title}
    {reasons 를 한 문단으로 · 변수 번호·코드 없이 사람 말}
    📈 예상 흐름: {flow}
    🎯 예상 스코어: {score_range}
    ```

    🔴 1겹(텔레그램) 카드는 **번호를 지운다**. ⚠️ 긴 카드(`debug=True`)는 같은 블록에
       **근거 `var_ids`·양상 비중 숫자**를 붙인다.
    """
    from app.core.stages.s8_comment import plain
    said = card.commentary
    if said is None:
        box = dict(card.shape or {})
        return ("\n🧭 **종합 논평 — 없다**"
                + (f"(양상 {box.get('shape')} · {box.get('why')})" if box else
                   "(양상을 못 쟀다 — 시나리오가 없다)")
                + ("" if not card.comment_notes else
                   "\n    ⚠️ " + " · ".join(card.comment_notes[:3])))
    out = [f"\n🧭 **종합 논평 — {said.title}**"]
    body = plain(said)
    if body:
        out.append(body)
    if said.flow:
        out.append(f"📈 **예상 흐름**: {said.flow}")
    if said.score_range:
        out.append(f"🎯 **예상 스코어**: {' · '.join(said.score_range)}")
    if said.lean:
        # ⚠️ 등급이 없으면 *"추천"* 이 아니라 **기울기**다(코드가 그것을 검사했다)
        out.append(f"↗️ **기울기**: {said.lean}")
    if debug:
        box = dict(card.shape or {})
        out.append(f"    [양상] {box.get('shape')} — 2골 이하 "
                   f"{box.get('low', 0):.0%} · 4골 이상 {box.get('high', 0):.0%} · "
                   f"2골 차 이상 {box.get('one_sided', 0):.0%} · 한 골 안 "
                   f"{box.get('close', 0):.0%} · {box.get('why')}")
        for line in said.reasons:
            out.append(f"    [근거] {line.text} ← {', '.join(line.var_ids) or '없음'}")
        if card.comment_notes:
            out.append("    [검사] " + " · ".join(card.comment_notes))
    return "\n".join(out)


def _b8(card: Card) -> str:
    return card.conclusion or "- ⬜ 결론을 못 적었다"


def _b9(card: Card) -> str:
    # 🔴 **매 경기 한 줄** — "방향 없음" 은 쓰지 않는다(지시서 §2-2)
    return card.direction or "- 🔴 방향 줄이 비었다 — 이것은 결함이다(§2-2)"


def _b10(card: Card) -> str:
    """블록 10 방아쇠 — 🔴 **사람이 읽는 문장**이다(§5: 내부 표기 금지)."""
    if not card.triggers:
        return "- ⬜ 방아쇠가 없다 — 조건 표에 걸린 변수 유형이 없었다"
    return "\n".join(f"- {x}" for x in card.triggers)

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **블록 3c·7b** — 네 층 지시서 §8
# ══════════════════════════════════════════════════════════════════


def _b3c(card: Card) -> str:
    """🔴 3c 기준 전력 — ① Elo·② 라인업 보정. ⚠️ 없으면 **"없음 — 사유"** 다(§1)."""
    b, a = card.base_prob, card.adj_prob
    out: list[str] = []
    if b.probs is not None:
        out.append(f"- Elo: {card.match.home_name} **{b.home_elo:.0f}** · "
                   f"{card.match.away_name} **{b.away_elo:.0f}** · 차 {b.dr:+.0f} "
                   f"→ 승 {b.probs.home:.0%} · 무 {b.probs.draw:.0%} · "
                   f"패 {b.probs.away:.0%}")
        out.append(f"    출처 {b.source}({b.data_date}) · {b.why}")
    else:
        out.append(f"- ⬜ **기준 없음** — {b.why}")
        if b.we is not None:
            # 🔴 §3-3 — 무승부를 못 나누면 **We 만** 보인다(지어내지 않는다)
            out.append(f"    Elo 기대 득점률 `We` **{b.we:.3f}**"
                       f"(홈 {b.home_elo:.0f} · 원정 {b.away_elo:.0f})")
    if a.strength_pct:
        got = " · ".join(f"{k} {v:+.1f}%" for k, v in a.strength_pct.items())
        # 🔴🔴 **%p 와 계수 신뢰도를 함께**(사용자 지시 2026-10-06(6차) ②)
        #    꼴: `라인업 보정 −1.2%p (환산 R² 0.61 · 표본 33)`
        head = f"- 라인업 보정: 평소 대비 {got}"
        if a.moved and b.probs is not None and a.probs is not None:
            pp = (a.probs.home - b.probs.home) * 100.0
            fit = _ds_fit(b.comp_kind)
            head += (f" → 홈 승 **{pp:+.1f}%p**"
                     f"(환산 R² {fit.get('r2', '?')} · 표본 {fit.get('n', '?')})")
            head += (f"\n    보정 후 승 {a.probs.home:.0%} · 무 {a.probs.draw:.0%} · "
                     f"패 {a.probs.away:.0%}")
        else:
            head += " — ⚠️ 확률은 **안 움직였다**(환산 계수 없음)"
        out.append(head)
        for d in a.deltas[:6]:
            # 🔴 ③ — 같은 포지션끼리만 짝이다. 짝이 없으면 **구조 변경**이라고 적는다
            tag = f"[{d.pos}]" if d.pos else "[포지션 미상]"
            if d.structural:
                # ⚠️ 구조 변경 줄의 수는 **짝의 차이가 아니다** — 그 선수 혼자의
                #    로그 가치다. 그 말을 적지 않으면 팀 ΔS 와 섞여 읽힌다.
                said = (f"{d.out_name} 빠짐 {tag} — **구조 변경**(같은 포지션 교체 없음)"
                        if d.out_name else
                        f"{d.in_name} 들어옴 {tag} — **구조 변경**")
                out.append(f"    {said}: 그 선수 로그가치 {d.delta_s:+.2f}"
                           + (" (추정값)" if d.estimated else ""))
                continue
            else:
                said = f"{d.out_name} → {d.in_name} {tag}"
            out.append(f"    {said}: ΔS {d.delta_s:+.2f}"
                       + (f" → 홈 승 {d.delta_home_pct:+.1f}%p"
                          if d.delta_home_pct is not None else "")
                       + (" (추정값)" if d.estimated else ""))
    else:
        out.append(f"- ⬜ **라인업 보정 없음** — {a.why}")
    return "\n".join(out)


def _b7b(card: Card) -> str:
    """🔴 7b 확률 세 열 — 기준·우리·시장(+사용자 보드). **한 숫자로 합치지 않는다**.

    🔴 배당 원숫자는 시장·사용자 보드 열에 **괄호로** 보인다(§8 · 사용자 결정).
    🔴 기대값·금액은 **어디에도 없다**(§0 금지).
    """
    from app.core.odds import key_of
    mk, user = card.market, card.user_market
    head = f"시장 = {mk.basis or '없음'}"
    if mk.captured_at is not None:
        from app import timefmt
        head += f"(받은 때 {timefmt.kst_label(mk.captured_at)})"
    vig = (mk.vig or {}).get("win")
    if vig is not None:
        head += f" · 업체 몫 {vig:.1%}"
    if mk.used is not None:
        head += f" · 월 사용 {mk.used}/{mk.limit or '?'}"
    # 🔴 §2-6 — 사용자 보드가 **그대로 시장 열**인 경우(피드 없음)에는 열을 **겹쳐
    #    적지 않는다**. ⚠️ 겹쳐 적으면 같은 배당이 두 열에 보여 *"피드도 있다"* 로 읽힌다.
    same_col = bool(user.probs) and mk.basis == user.basis
    cols = ["| | 기준 | 우리 | 시장 |", "|---|---|---|---|"] if same_col else \
           ["| | 기준 | 우리 | 시장 | 사용자 보드 |", "|---|---|---|---|---|"]
    # 🔴🔴 **기준 열은 "②반영" 이다**(네 층 지시서 §6 첫 줄: *"기준(②반영)·우리·시장"*).
    #    ⚠️ ① 만 적으면 우리 열의 **출발점과 다른 수**가 기준 칸에 앉아, 이동량 줄이
    #       설명하지 못하는 차이가 생긴다(실측 2026-10-06: 54% vs 출발 52%).
    base_col = (card.adj_prob.probs if card.adj_prob.probs is not None
                else card.base_prob.probs)
    if card.adj_prob.moved:
        cols[0] = cols[0].replace("| 기준 |", "| 기준(②반영) |")
    rows = [f"- {head}", ""] + cols
    names = ((f"{card.match.home_name} 승", "home"), ("무", "draw"),
             (f"{card.match.away_name} 승", "away"))
    for label, key in names:
        cells = [label]
        cells.append(f"{getattr(base_col, key):.0%}"
                     if base_col is not None else "—")
        cells.append(f"{getattr(card.our_prob, key):.0%}"
                     if card.our_prob is not None else "—")
        for box in ((mk,) if same_col else (mk, user)):
            p = (box.probs or {}).get(key_of("win", key))
            price = _price_of(box, key)
            cells.append("—" if p is None else
                         (f"{p:.0%}" + (f" ({price:g})" if price else "")))
        rows.append("| " + " | ".join(cells) + " |")
    shin = mk.shin or {}
    if shin:
        said = " · ".join(
            f"{nm} {shin.get(key_of('win', k), 0):.0%}"
            for nm, k in (("홈", "home"), ("무", "draw"), ("원정", "away")))
        rows.append(f"- Shin 방식(괄호 비교용): {said}")
    # 🔴🔴 **③ 이 움직인 양**(사용자 지시 2026-10-06(6차) ③) — 없으면 그 사실을 적는다
    if card.moves:
        said = " · ".join(
            f"`{m.get('id')}`({m.get('type')}→{m.get('side')}) "
            f"{float(m.get('logodds') or 0):+.3f}" for m in card.moves[:6])
        tot = sum(abs(float(m.get("logodds") or 0)) for m in card.moves)
        rows.append(f"- ③ 이 움직인 양(로그 오즈 합 {tot:.3f}): {said}")
    else:
        rows.append("- ③ **이동 없음 — 우리 열 = 기준**"
                    + ("" if card.base_prob.probs is not None else
                       "(기준도 없어 시나리오 비율이다)"))
    if card.compare:
        rows.append(f"- 판정: **{card.compare}**")
    for line in card.compare_lines:
        if line:
            rows.append(f"    {line}")
    for line in card.tilt:
        rows.append(f"- → {line}")
    for line in card.market_why:
        rows.append(f"- → {line}")
    if card.ocr_text:
        rows.append("- 캡처 인식 원문(그대로):")
        rows += [f"    {x}" for x in card.ocr_text.splitlines() if x.strip()]
    if not mk.probs and not user.probs:
        rows.append(f"- ⬜ **시장 없음** — {mk.why or '피드·사용자 보드 모두 없다'}")
    return "\n".join(rows)


def _ds_fit(kind: str) -> dict:
    """🔴 `ΔS→dr` 계수의 **표본·R²** — 카드가 그 신뢰도를 숨기지 않는다(②)."""
    from app import rules
    return dict((rules.base_model(str(kind)) or {}).get("ds_fit") or {})


def _price_of(box, side: str) -> float | None:
    """🔴 그 쪽의 **원배당** — 괄호로 보이는 숫자다. ⚠️ 없으면 `None`."""
    for q in (box.quotes or []):
        if q.market == "win" and q.side == side:
            return q.price
    return None
