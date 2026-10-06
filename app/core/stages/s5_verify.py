"""🔴🔴 **v6 s5 — 검증.** `list[VarCandidate] → list[Variable]`(§5).

지시서 §5 s5 — 기존 검증 규칙의 **내용을 새 함수로 옮겨 쓴다**:

> 인용이 해당 `Doc` 본문에 글자 그대로(NFKC·합자표·따옴표 정규화), 날짜
> (`Doc.published_at`), 신원, **방향 재계산**(`subject`+`type`→`favors`, catalog
> 규칙), 매체 2곳 이상이면 `hard`, MinHash 병합, 표본 부족은
> `usable_as_basis=False`. 해석 규칙(IR01~IR12)이 `Facts` 에서 변수를 더한다.

🔴 **방향은 코드가 정한다** — 모델 출력에 방향 칸이 아예 없다(§3). 그 자리가
   `side_mismatch` 의 입구였다(모델이 `away` 라 적어도 그 팀이 홈이면 홈이다).

══════════════════════════════════════════════════════════════════
⚠️ **해석 규칙 IR01~IR12 는 이 저장소에 표가 없다**
══════════════════════════════════════════════════════════════════

🔴 실측 2026-10-06: `IR01`~`IR12` 를 `app/`·`config/`·`docs/` 에서 **찾지 못했다**
   (이름이 나오는 곳은 v6 지시서 본문과 `schema.py` 주석뿐이다). 지시서는
   *"규칙 문서의 표 그대로"* 라고 가리키는데 **그 문서가 이 기계에 없다.**
⚠️ 그래서 **지어내지 않는다**(#4 추측 금지 · §9 *"이 문서에 없는 새 기능"* 금지) —
   `Facts` 에서 변수를 더하는 자리는 `_from_facts` 로 **비워 두고 사유를 남긴다.**
   🔴 표를 받으면 그 함수 하나만 채운다(배선은 이미 돼 있다).
"""
from __future__ import annotations

from typing import Any

from app.core.schema import (Doc, DropReason, Facts, Favors, MatchRef,
                             VarCandidate, Variable)
from app.core.state import RunState

#: 🔴 같은 주장으로 볼 유사도 — 수는 `verifylayer.SIM_SAME` 하나가 든다(#1).
def _sim_same() -> float:
    from app import verifylayer
    return float(verifylayer.SIM_SAME)


#: 🔴 등급 수(0·1·2) → 옛 이름. ⚠️ 무게는 `types.WEIGHT_OF` 가 원본이다.
_LEVEL_NAME = {2: "hard", 1: "likely", 0: "soft"}


def game_of(ref: MatchRef) -> Any:
    """🔴 방향 규칙이 보는 **경기 맥락** — `classify.Game` 그대로 쓴다(§6 부품).

    ⚠️ dict 를 넘기지 않는다(§9) — `Game` 은 dataclass 이고 `side_of` 가 **열쇠를
       먼저** 본다(이름으로 가리면 언어가 갈릴 때 방향이 뒤집힌다).
    """
    from app import classify
    return classify.Game(home=ref.home_name, away=ref.away_name,
                         sport=ref.sport, league=ref.competition,
                         home_id=ref.home, away_id=ref.away)


def favors_of(kind: str, subject: str, claim: str, ref: MatchRef) -> str:
    """🔴🔴 **방향은 카탈로그 규칙이 정한다** — `classify.favors_of` 가 원본이다.

    ⚠️ 규칙표(`variable_types.yaml` 의 `favors`)를 여기 베끼지 않는다(#1) —
       `stakes` 의 확정 뒤집기까지 그 함수 안에 있다.
    """
    from app import classify
    return str(classify.favors_of(kind, subject=subject, game=game_of(ref),
                                  text=claim) or "")


def run(ref: MatchRef, facts: Facts, docs: list[Doc],
        cands: list[VarCandidate], *, state: RunState) -> list[Variable]:
    """🔴 후보를 검증해 변수로. ⚠️ 버린 것은 **사유와 함께** 남는다(#3)."""
    from app import verifylayer
    by_id = {d.id: d for d in docs}
    rows: list[dict] = []
    for i, c in enumerate(cands):
        got = _one(c, ref, by_id, state=state, n=i)
        if got is not None:
            rows.append(got)
    merged = _merge(rows, state=state)
    out: list[Variable] = []
    for i, row in enumerate(merged, 1):
        mine = [by_id[d] for d in row["doc_ids"] if d in by_id]
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **독립 출처는 기사 본문으로 센다** — 실측 2026-10-06
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 처음엔 `(url, 주장)` 을 넘겼다 — 묶인 변수의 주장은 **한 글자**라
        #     `independent_sources` 가 늘 **1곳**을 돌려줬고, 그래서 두 매체가
        #     말한 것도 `hard` 가 되지 못했다(실측: 2곳인데 soft).
        #  🔴 그 함수가 세는 것은 *"서로 다른 글인가"* 다 — `복사된 보도자료
        #     여덟은 하나다`. 그러니 **기사 본문**을 넘겨야 뜻이 맞는다.
        n_src, _groups = verifylayer.independent_sources(
            [(d.url, d.body[:2000]) for d in mine])
        tier = min((d.tier for d in mine),
                   key=lambda t: _TIER_ORDER.index(t)
                   if t in _TIER_ORDER else 9, default="aggregator")
        level = int(verifylayer.hardness_for(str(tier), sources=n_src))
        name = _LEVEL_NAME.get(level, "soft")
        from app.types import WEIGHT_OF
        out.append(Variable(
            id=f"R{i}", type=row["type"], subject=row["subject"],
            favors=row["favors"], hardness=("hard" if level == 2 else "soft"),
            weight=float(WEIGHT_OF[name]), claim=row["claim"],
            quote=row["quote"], doc_ids=row["doc_ids"],
            # 🔴🔴 **근거로 쓸 수 있나** — 등급 0(단일 aggregator·충돌)은 못 쓴다.
            #    ⚠️ 옛 경로가 `hardness == "none"` 으로 가른 그 선이다
            #       (`analyze.split_basis`) — 뜻을 옮겨 적었다.
            usable_as_basis=(level >= 1)))
        if level < 1:
            state.note(f"s5 R{i} 는 **근거로 못 쓴다**(등급 {level} · 출처 "
                       f"{n_src}곳 · {tier}) — 맥락으로만 보낸다")
    out += _from_facts(ref, facts, state=state)
    state.set("variables", len(out))
    return out


#: 🔴 센 등급이 먼저다 — 한 주장을 여러 매체가 말하면 **가장 센 쪽**으로 센다
_TIER_ORDER = ("official", "national", "local", "aggregator", "tip", "dead")


def _one(c: VarCandidate, ref: MatchRef, by_id: dict[str, Doc], *,
         state: RunState, n: int) -> dict | None:
    """🔴 후보 하나 — 검사 순서는 **싼 것부터**다(문서 → 인용 → 날짜 → 신원 → 방향)."""
    from app import verify, verifylayer
    what = f"s5/{c.subtask}/{c.type}/{n}"
    doc = by_id.get(c.doc_id)
    if doc is None:
        # ⚠️ 스키마 enum 이 막으므로 **여기 오면 재생본이 어긋난 것**이다
        state.drop(what, DropReason.UNKNOWN_VAR,
                   f"`{c.doc_id}` 는 그 하위에 넘긴 문서가 아니다")
        return None
    ok, why = verifylayer.quote_ok(c.quote, doc.body)
    if not ok:
        state.drop(what, (DropReason.BODY_MISSING if "본문을 못" in why
                          else DropReason.QUOTE_NOT_FOUND), why[:110])
        return None
    if doc.published_at is None:
        # 🔴 불변식 9 — `date_source="none"` 인 Doc 을 근거로 한 변수는 **없다**
        state.drop(what, DropReason.DATE_MISSING,
                   f"{doc.id} 발행일이 없다({doc.url[:50]})")
        return None
    post = verify.not_post_game(doc.title, doc.body)
    if not getattr(post, "ok", True):
        state.drop(what, DropReason.POST_MATCH,
                   str(getattr(post, "why", ""))[:110])
        return None
    if not _mentions(c.subject, doc, ref):
        state.drop(what, DropReason.IDENTITY_MISMATCH,
                   f"{doc.id} 본문이 `{c.subject}` 를 말하지 않는다")
        return None
    fav = favors_of(c.type, c.subject, c.claim, ref)
    if fav not in _FAVORS:
        # 🔴 **방향 규칙이 없는 유형**이다 — 한쪽으로 밀지 않는다(지어내지 않는다)
        state.drop(what, DropReason.TYPE_OFF_CATALOG,
                   f"`{c.type}` 방향 규칙이 없다(받은 값 {fav!r})")
        return None
    return {"type": c.type, "subject": c.subject, "favors": fav,
            "claim": c.claim, "quote": c.quote, "doc_ids": [doc.id]}


_FAVORS = set(Favors.__args__)                        # type: ignore[attr-defined]


def _mentions(subject: str, doc: Doc, ref: MatchRef) -> bool:
    """🔴 그 문서가 **그 팀**을 말하나 — 열쇠에서 이름을 꺼내 본다(§8-1).

    ⚠️ 이름을 인자로 받지 않는다 — 받으면 또 하나의 해석 지점이 된다.
    """
    from app.core.stages.s3_docs import names_of
    home, away = names_of(ref)
    names = home if subject == ref.home else away
    said = f"{doc.title} {doc.body}".lower()
    return any(len(str(x)) >= 3 and str(x).lower() in said for x in names)


def _merge(rows: list[dict], *, state: RunState) -> list[dict]:
    """🔴 §5-7 — 같은 주장은 **하나로 묶고 출처를 더한다**(MinHash 병합).

    ⚠️ 버리는 것이 아니다 — `doc_ids` 가 늘어나면 `independent_sources` 가 그것을
       세고 등급이 올라간다(매체 2곳 이상이면 `hard`).
    """
    from app import verifylayer
    out: list[dict] = []
    for row in rows:
        for keep in out:
            if keep["type"] != row["type"] or keep["subject"] != row["subject"]:
                continue
            if verifylayer.similarity(keep["claim"], row["claim"]) < _sim_same():
                continue
            for d in row["doc_ids"]:
                if d not in keep["doc_ids"]:
                    keep["doc_ids"].append(d)
            state.drop(f"s5/{row['type']}/{row['subject']}",
                       DropReason.DUPLICATE,
                       f"같은 주장으로 묶었다 → 출처 {len(keep['doc_ids'])}곳")
            break
        else:
            out.append(row)
    return out


def _from_facts(ref: MatchRef, facts: Facts, *, state: RunState
                ) -> list[Variable]:
    """🔴🔴 **해석 규칙(IR01~IR12)이 `Facts` 에서 변수를 더하는 자리**(§5 s5).

    ⚠️ **그 표가 이 저장소에 없다**(위 모듈 설명의 실측) — 그래서 **빈 목록**이고
       그 사실을 사유로 남긴다. 🔴 지어내 채우면 방향 규칙·검색 템플릿까지 지어내야
       한다(#4). 표를 받으면 **이 함수 하나**를 채운다.
    """
    state.note("s5 해석 규칙(IR01~IR12) — 🔴 **표가 저장소에 없다**(실측 "
               "2026-10-06: `app/`·`config/`·`docs/` 에 `IR01` 이 없다) → "
               f"사실에서 더한 변수 0개 · 순위 {len(facts.standings)}칸 · "
               f"폼 {len(facts.recent)}팀 · 맞대결 {len(facts.h2h)}칸이 **쓰이지 "
               "않았다**")
    return []
