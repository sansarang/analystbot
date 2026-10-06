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
    "자료 한계 고백", "기준 XI", "폼", "뒤집는 변수", "팀별 가설 + 무너지는 조건",
    "시나리오", "보드 대입", "결론", "방향 판정", "방아쇠")


def card_text(card: Card) -> str:
    """🔴 카드 전문. ⚠️ 블록 **열 개가 늘 있다** — 비면 사유가 들어간다."""
    out: list[str] = [_head(card)]
    for i, body in enumerate((
            _b1(card), _b2(card), _b3(card), _b4(card), _b5(card), _b6(card),
            _b7(card), _b8(card), _b9(card), _b10(card)), 1):
        out.append(f"\n**{i}. {TITLES[i - 1]}**\n{body}")
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
    if not card.facts.xi:
        out.append("⚠️ **확정 XI 를 못 잡았다** — 상한이 그만큼 내려간다")
    if not card.facts.standings:
        out.append("⚠️ 순위표가 없다(친선·네이션스리그는 애초에 없다)")
    return "\n".join(f"- {x}" for x in out)


def _b2(card: Card) -> str:
    if not card.facts.xi:
        return "- ⬜ 없다 — 어느 쪽 XI 도 못 받았다(사유는 블록 1)"
    out = []
    for key, xi in card.facts.xi.items():
        who = (card.match.home_name if key == card.match.home
               else card.match.away_name)
        out.append(f"- **{who}** {xi.state} · {xi.formation or '포메이션 미상'} · "
                   f"{', '.join(xi.players[:11]) or '명단 없음'}")
    return "\n".join(out)


def _b3(card: Card) -> str:
    f = card.facts
    if not (f.recent or f.standings or f.h2h):
        return "- ⬜ 없다 — 구조 자료를 못 받았다(사유는 블록 1)"
    out = []
    for key, row in f.recent.items():
        who = (card.match.home_name if key == card.match.home
               else card.match.away_name if key == card.match.away else key)
        out.append(f"- **{who}** {row}")
    if f.standings:
        out.append(f"- 순위: {f.standings}")
    if f.h2h:
        out.append(f"- 맞대결: {f.h2h}")
    return "\n".join(out)


def _b4(card: Card) -> str:
    if not card.variables:
        return ("- ⬜ 변수 0개 — 🔴 **\"자료가 안 왔다\"와 \"왔는데 못 뽑았다\"는 "
                "다르다**(블록 1 의 사유를 본다)")
    return "\n".join(_var_line(v) for v in card.variables)


def _var_line(v: Variable) -> str:
    tail = "" if v.usable_as_basis else " · ⚠️ **근거로는 못 쓴다**(맥락 전용)"
    rule = f" · {v.from_rule}" if v.from_rule else ""
    return (f"- `{v.id}` [{v.type}] {v.claim} — 방향 **{v.favors}** · "
            f"{v.hardness}({v.weight}) · 출처 {', '.join(v.doc_ids)}{rule}{tail}")


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
        out.append(f"- **{s.id}** ({scores}) [{s.type} · {s.added_by} · "
                   f"strength {s.strength}] {s.mechanism} "
                   f"← {', '.join(s.driver_vars) or '근거 없음(코드 보강)'}")
    return "\n".join(out)


def _b7(card: Card) -> str:
    if not card.evals:
        return "- ⬜ 대입한 줄이 없다"
    ids = [s.id for s in (card.hypo.scenarios if card.hypo else [])]
    head = "| 마켓 | " + " | ".join(ids) + " | 생존 | 상한 | 등급 |"
    bar = "|---" * (len(ids) + 4) + "|"
    rows = [head, bar]
    for e in card.evals:
        point = f" {e.line.point}" if e.line.point is not None else ""
        cells = " | ".join(e.marks.get(i, "?") for i in ids)
        rows.append(f"| {e.line.market} {e.line.side}{point} | {cells} | "
                    f"{e.survival} | {e.cap} | {e.grade} |")
    return "\n".join(rows)


def _b8(card: Card) -> str:
    return card.conclusion or "- ⬜ 결론을 못 적었다"


def _b9(card: Card) -> str:
    # 🔴 **매 경기 한 줄** — "방향 없음" 은 쓰지 않는다(지시서 §2-2)
    return card.direction or "- 🔴 방향 줄이 비었다 — 이것은 결함이다(§2-2)"


def _b10(card: Card) -> str:
    if not card.triggers:
        return "- ⬜ 방아쇠가 없다 — 조건 표에 걸린 변수 유형이 없었다"
    return "\n".join(f"- {x}" for x in card.triggers)
