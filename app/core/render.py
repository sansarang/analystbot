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
    "자료 한계 고백", "기준 XI", "결장", "폼", "경우의 수", "뒤집는 변수",
    "팀별 가설 + 무너지는 조건", "시나리오", "보드 대입", "결론", "방향 판정",
    "방아쇠")

#: 🔴 규격 번호 — 축구 완성 지시서 §5 가 **2b·3b** 를 새 블록으로 더했다.
#   ⚠️ 번호를 다시 매기지 않는다(사용자가 블록 번호로 말한다) — `2b`·`3b` 로 적는다.
NUMBERS: tuple[str, ...] = ("1", "2", "2b", "3", "3b", "4", "5", "6", "7", "8",
                            "9", "10")


def card_text(card: Card) -> str:
    """🔴 카드 전문. ⚠️ 블록이 **늘 전부 있다** — 비면 사유가 들어간다.

    🔴 축구 완성 지시서 §5 가 블록 **2b(결장)**·**3b(경우의 수)** 를 더했다.
    """
    out: list[str] = [_head(card)]
    bodies = (_b1(card), _b2(card), _b2b(card), _b3(card), _b3b(card),
              _b4(card), _b5(card), _b6(card), _b7(card), _b8(card),
              _b9(card), _b10(card))
    for num, title, body in zip(NUMBERS, TITLES, bodies, strict=True):
        out.append(f"\n**{num}. {title}**\n{body}")
    return "\n".join(out)


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
    """블록 3b 경우의 수 — **조별 리그에서만**(§3·§5).

    ⚠️ 순위표·잔여 경기가 없으면 **그 사실을 적는다**(#3) — 빈 블록은 거짓이다.
    """
    box = dict(card.facts.standings or {})
    rows = box.get("table") if isinstance(box.get("table"), list) else None
    if not rows:
        return ("- ⬜ 경우의 수를 못 센다 — 순위표·잔여 경기가 없다"
                f"(형식 `{card.facts.match_format}`)")
    out = ["| 팀 | 순위 | 승점 | 잔여 |", "|---|---|---|---|"]
    for r in rows[:8]:
        row = dict(r) if isinstance(r, dict) else {}
        out.append(f"| {row.get('name', '?')} | {row.get('idx', row.get('rank', '?'))}"
                   f" | {row.get('pts', '?')} | {row.get('played', '?')} |")
    out.append("⚠️ 동률 규칙을 모르면 **승점 → 득실 → 다득점**으로 센다(그 가정을 "
               "여기 적는다 · §3)")
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
        out.append(f"- 순위 — {_short(f.standings)}")
    if f.h2h:
        h = dict(f.h2h)
        got = h.get("summary")
        bits = []
        if isinstance(got, (list, tuple)) and len(got) == 3:
            bits.append(f"{got[0]}승 {got[1]}무 {got[2]}패")
        if h.get("count") is not None:
            bits.append(f"표본 {h['count']}경기")
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


def _b7(card: Card) -> str:
    if not card.evals:
        return "- ⬜ 대입한 줄이 없다"
    ids = [s.id for s in (card.hypo.scenarios if card.hypo else [])]
    head = "| 마켓 | " + " | ".join(ids) + " | 생존 | 상한 | 등급 |"
    bar = "|---" * (len(ids) + 4) + "|"
    rows = [head, bar]
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
