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

import re
import unicodedata
from typing import Any

from app.core.schema import (Doc, DropReason, Facts, Favors, MatchRef,
                             VarCandidate, Variable)
from app.core.state import RunState

#: 🔴 같은 주장으로 볼 유사도 — 수는 `SIM_SAME` 하나가 든다(#1).
def _sim_same() -> float:
    return float(SIM_SAME)


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
    """🔴🔴 **승패 방향은 카탈로그 규칙이 정한다** — `classify.favors_of` 가 원본이다.

    ⚠️ 규칙표(`variable_types.yaml` 의 `favors`)를 여기 베끼지 않는다(#1) —
       `stakes` 의 확정 뒤집기까지 그 함수 안에 있다.
    🔴 돌려주는 것은 `home`·`away`·`both` 뿐이다(사용자 지시 2026-10-06 ④) —
       득점 방향은 `goals_of` 가 따로 낸다. ⚠️ 표가 `none` 이라 적은 유형
       (`national_duty_return`)은 **어느 쪽도 아니다** → `both` 로 둔다(한쪽으로
       밀지 않는다). 그 유형은 `_enough` 의 방향 셈에 들어가지 않는다(home/away 만 센다).
    """
    from app import classify
    got = str(classify.favors_of(kind, subject=subject, game=game_of(ref),
                                 text=claim) or "")
    return got if got in ("home", "away", "both") else "both"


def goals_of(kind: str) -> str:
    """🔴 **득점 방향** — 표의 `goals` 칸이 원본이다(사용자 지시 2026-10-06 ④).

    ⚠️ 종전엔 이 값이 `favors` 칸에 `goals_up` 으로 들어 있어, 수비 결장 변수가
       *"어느 팀 쪽인가"* 를 말하지 못했다(그래서 방향 1종으로 등급이 거둬졌다).
    """
    from app import rules
    said = str((rules.variable_types().get(str(kind)) or {}).get("goals")
               or "none")
    return said if said in ("up", "down", "none") else "none"


def run(ref: MatchRef, facts: Facts, docs: list[Doc],
        cands: list[VarCandidate], *, state: RunState) -> list[Variable]:
    """🔴 후보를 검증해 변수로. ⚠️ 버린 것은 **사유와 함께** 남는다(#3)."""
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
        n_src, _groups = independent_sources(
            [(d.url, d.body[:2000]) for d in mine])
        tier = min((d.tier for d in mine),
                   key=lambda t: _TIER_ORDER.index(t)
                   if t in _TIER_ORDER else 9, default="aggregator")
        level = int(hardness_for(str(tier), sources=n_src))
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **출처 2곳 이상이면 `hard`** — 사용자 지시 2026-10-06 ①
        # ══════════════════════════════════════════════════════════════
        #
        #  > 같은 subject + 같은 type + 같은 핵심 대상이면 하나의 Variable 로 합치고
        #  > `doc_ids` 를 모은다(**출처 2곳 이상이면 `hard`**).
        #
        #  ⚠️ §5-5 표는 `national` **2매체**만 2 로 올렸다 — 그래서 실측 2026-10-06 의
        #     R1(세 매체가 말한 김민재 결장)이 `local` 등급 때문에 `soft(0.7)` 였다.
        #  🔴 사용자 규칙이 그보다 **위**다(CLAUDE.md): 독립 출처가 둘이면 `hard`.
        if n_src >= 2:
            level = max(level, 2)
        name = _LEVEL_NAME.get(level, "soft")
        from app.types import WEIGHT_OF
        out.append(Variable(
            id=f"R{i}", type=row["type"], subject=row["subject"],
            favors=row["favors"], goals=row.get("goals", "none"),
            target=str(row.get("target") or ""),
            hardness=("hard" if level == 2 else "soft"),
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
    from app import verify
    what = f"s5/{c.subtask}/{c.type}/{n}"
    doc = by_id.get(c.doc_id)
    if doc is None:
        # ⚠️ 스키마 enum 이 막으므로 **여기 오면 재생본이 어긋난 것**이다
        state.drop(what, DropReason.UNKNOWN_VAR,
                   f"`{c.doc_id}` 는 그 하위에 넘긴 문서가 아니다")
        return None
    quote = _unhead(c.quote)
    if quote != c.quote:
        # 🔴 **우리가 붙인 표지는 우리가 떼어 낸다**(#3: 그 사실을 적는다)
        state.note(f"s5 {what} 인용에서 **머리표를 떼어 냈다** — 모델이 붙인 "
                   f"`{c.quote[:28]}…` 는 우리가 넣은 표지다")
    ok, why = quote_ok(quote, doc.body)
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
            "goals": goals_of(c.type), "target": str(c.target or ""),
            "claim": c.claim, "quote": quote, "doc_ids": [doc.id]}


_FAVORS = set(Favors.__args__)                        # type: ignore[attr-defined]

#: 🔴 **우리가 붙인 문단 머리표** — `[A-home-D1-P2] (도메인, 2026-10-05) 본문…`
#  ⚠️ 실측 2026-10-06: 후보 16개 중 11개가 이 표지를 `quote` 에 넣어 전부
#     `quote_not_found` 가 됐다(변수 14 → 5). 🔴 **기사 탓이 아니라 우리 표지 탓**
#     이므로 떼어 내고 대조한다 — 그 대신 **모델에게도 넣지 말라고 적는다**(s4).
#  🔴 떼어 내는 것은 **이 꼴 하나**다(앞머리에서만) — 본문을 고치지 않는다.
_HEAD = re.compile(r"^\s*\[[A-Za-z]-[a-z]+-D\d+-P\d+\]\s*(\([^)]*\))?\s*")


def _unhead(said: str) -> str:
    """🔴 인용 **앞머리의 머리표만** 떼어 낸다. ⚠️ 가운데 글자는 건드리지 않는다."""
    return _HEAD.sub("", str(said or "")).strip()


def _mentions(subject: str, doc: Doc, ref: MatchRef) -> bool:
    """🔴 그 문서가 **그 팀**을 말하나 — 열쇠에서 이름을 꺼내 본다(§8-1).

    ⚠️ 이름을 인자로 받지 않는다 — 받으면 또 하나의 해석 지점이 된다.
    """
    from app.core.stages.s3_docs import names_of
    home, away = names_of(ref)
    names = home if subject == ref.home else away
    said = f"{doc.title} {doc.body}".lower()
    return any(len(str(x)) >= 3 and str(x).lower() in said for x in names)


def merge_key(subject: str, kind: str, target: str) -> tuple[str, str, str]:
    """🔴🔴 **사실 하나의 열쇠** — `(주체, 유형, 핵심 대상)`(사용자 지시 2026-10-06 ①).

    > 같은 subject + 같은 type + 같은 핵심 대상(선수명·사건)이면 하나의 Variable 로
    > 합치고 `doc_ids` 를 모은다 … **문장 유사도(MinHash)가 아니라** "누가·무엇" 열쇠로.

    🔴 대상 글자는 **정규화**해서 비교한다 — `Kim Min-jae`·`김민재`·`KIM MIN-JAE` 가
       갈리면 열쇠가 쪼개진다. ⚠️ 정규화는 이 파일의 `norm` 하나다(사본 금지 · 옛 `verifylayer._norm`).
    """
    return (str(subject), str(kind), norm(str(target)))


def _merge(rows: list[dict], *, state: RunState) -> list[dict]:
    """🔴 **사실 단위로 묶는다** — 같은 열쇠면 한 변수이고 `doc_ids` 가 쌓인다.

    ⚠️ 실측 2026-10-06: 김민재 결장이라는 **한 사실**이 변수 11개로 셌다(문장이
       저마다 달라 MinHash 가 못 묶었다). 🔴 열쇠로 묶으면 그 11개가 하나다.
    🔴 묶는 것은 **버리는 것이 아니다** — 출처가 늘면 `independent_sources` 가 그것을
       세고 등급이 `hard` 로 오른다(매체 2곳 이상).
    ⚠️ `target` 이 **비어 있으면 묶지 않는다** — 빈 열쇠로 묶으면 서로 다른 사실이
       한 변수가 된다(그쪽이 더 나쁘다). 그 사실을 사유로 남긴다.
    """
    out: list[dict] = []
    seen: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        target = str(row.get("target") or "")
        if not target.strip():
            state.note(f"s5 `{row['type']}` 변수에 **대상이 비었다** — 묶지 않는다"
                       f"(모델이 `target` 을 안 적었다)")
            out.append(row)
            continue
        key = merge_key(row["subject"], row["type"], target)
        keep = seen.get(key)
        if keep is None:
            seen[key] = row
            out.append(row)
            continue
        for d in row["doc_ids"]:
            if d not in keep["doc_ids"]:
                keep["doc_ids"].append(d)
        state.drop(f"s5/{row['type']}/{target[:24]}", DropReason.DUPLICATE,
                   f"같은 사실로 묶었다(열쇠 {key[1]}·{key[2][:20]}) → 출처 "
                   f"{len(keep['doc_ids'])}곳")
    return out


def interpret_rules() -> list[dict]:
    """🔴 해석 규칙 표 — `config/interpret_rules.yaml` 하나가 원본이다(사본 금지)."""
    from app import rules
    box = rules._load("config/interpret_rules.yaml")
    return [dict(r) for r in (box.get("rules") or [])]


def _sample_weight(n: int) -> tuple[str, float]:
    """🔴 표본 수 → `(hardness, weight)`. 수는 `league.h2h_weight` 하나가 든다.

    ⚠️ 여기서 사다리를 다시 적지 않는다(#1) — 그 함수가 §4 `sample_weight` 의
       원본이고, 실측 근거(3경기 창이 거짓을 말한 사고)가 그 독스트링에 있다.
    """
    from app import league
    from app.types import WEIGHT_OF
    w = float(league.h2h_weight(int(n)))
    name = {1.0: "hard", 0.7: "likely", 0.4: "soft"}.get(w, "soft")
    return name, float(WEIGHT_OF[name])


def _from_facts(ref: MatchRef, facts: Facts, *, state: RunState
                ) -> list[Variable]:
    """🔴🔴 **해석 규칙이 `Facts` 에서 변수를 더한다**(§5 s5 · 사용자 지시 ⑥).

    ══════════════════════════════════════════════════════════════════
    ⚠️ **접목 문서 §2 표가 이 기계에 없다**(실측 2026-10-06)
    ══════════════════════════════════════════════════════════════════

    `~/Downloads` 와 `docs/` 를 다 봤고 `IR01`~`IR12` 는 v6 지시서 본문·주석에만
    있다. 🔴 그래서 `config/interpret_rules.yaml` 은 **이 저장소에 이미 있는 규칙만**
    담았고(그 파일 머리에 적었다), 이 함수는 **그 파일을 읽을 뿐**이다 — 표를 받으면
    파일만 덮으면 된다(코드는 그대로).

    🔴 못 돈 규칙은 **이름으로** 남긴다(#3) — *"규칙이 있는데 안 걸린다"* 를 숨기지
       않는다.
    """
    out: list[Variable] = []
    for row in interpret_rules():
        rid, kind = str(row.get("id") or ""), str(row.get("type") or "")
        if row.get("off"):
            state.note(f"s5 {rid}({kind}) **끈 규칙** — {row['off']}")
            continue
        if kind == "recent_pattern":
            out += _ir_recent(rid, row, ref, facts, state=state)
        elif kind == "h2h_pattern":
            out += _ir_h2h(rid, row, ref, facts, state=state)
        elif kind == "home_field":
            out += _ir_home(rid, row, ref, facts, state=state)
        else:
            state.note(f"s5 {rid}({kind}) — **그 유형을 읽는 코드가 없다**"
                       f"(규칙이 표에만 있다 · #2 배선)")
    state.note(f"s5 해석 규칙 {len(interpret_rules())}줄 → 사실 변수 {len(out)}개")
    return out


def _min_games(row: dict, default: int = 0) -> int:
    """🔴 문턱은 **이름으로** 적혀 있다(`recent_min_games` 등) — 표에서 읽는다."""
    from app import thresholds
    said = str(row.get("min_games") or "")
    if not said:
        return int(default)
    try:
        return int(thresholds.value(said))           # type: ignore[arg-type]
    except (ValueError, TypeError):
        return int(default)


def _ir_recent(rid: str, row: dict, ref: MatchRef, facts: Facts, *,
               state: RunState) -> list[Variable]:
    """IR01 — 최근 폼. 🔴 **양 팀 다** 만든다(한쪽만 만들면 방향이 한 종류다)."""
    low = _min_games(row, 3)
    out: list[Variable] = []
    for key in (ref.home, ref.away):
        box = facts.recent.get(key)
        box = dict(box) if isinstance(box, dict) else {}
        n = int(box.get("matches") or len(box.get("last5") or []) or 0)
        if not n:
            state.note(f"s5 {rid} — `{key}` 폼 자료가 없다(변수 안 만든다)")
            continue
        hard, weight = _sample_weight(n)
        last5 = " ".join(str(x) for x in (box.get("last5") or [])) or "?"
        avg, trim = box.get("recent_scored_avg"), box.get("recent_trimmed_avg")
        claim = (f"최근 {n}경기 {last5} · 득점 평균 "
                 f"{avg if avg is not None else '못 쟀다'}"
                 + (f"(보정 {trim})" if trim is not None else ""))
        out.append(Variable(
            id=f"{rid}-{'home' if key == ref.home else 'away'}",
            type="recent_pattern", subject=key,
            favors=favors_of("recent_pattern", key, claim, ref),  # type: ignore[arg-type]
            goals=goals_of("recent_pattern"),                     # type: ignore[arg-type]
            target="recent", hardness=("hard" if hard == "hard" else "soft"),
            weight=weight, claim=claim,
            # 🔴 인용은 **어댑터 수치 그대로**다 — 기사가 아니라 구조 자료다
            quote=claim, doc_ids=[], from_rule=rid,
            # ⚠️ 표본이 문턱 미만이면 **근거로 쓰지 않는다**(§7 R7)
            usable_as_basis=(n >= low)))
        if n < low:
            state.note(f"s5 {rid} `{key}` 표본 {n}경기 < {low} — 맥락 전용")
    return out


def _ir_h2h(rid: str, row: dict, ref: MatchRef, facts: Facts, *,
            state: RunState) -> list[Variable]:
    """IR02 — 맞대결. 🔴 **기록이 가리키는 쪽**이 주체다(동률이면 만들지 않는다)."""
    box = dict(facts.h2h or {})
    got = box.get("summary")
    n = int(box.get("count") or 0)
    if not (isinstance(got, (list, tuple)) and len(got) == 3 and n):
        state.note(f"s5 {rid} — 맞대결 요약이 없다(변수 안 만든다)")
        return []
    w, d, lose = (int(x) for x in got)
    if w == lose:
        state.note(f"s5 {rid} — 맞대결이 {w}승 {d}무 {lose}패로 **동률**이다 "
                   f"(어느 쪽도 아니다 · 변수 안 만든다)")
        return []
    key = ref.home if w > lose else ref.away
    hard, weight = _sample_weight(n)
    claim = (f"맞대결 {n}경기 {w}승 {d}무 {lose}패"
             + (f" · 평균 {box['window_avg_goals']}골"
                if box.get("window_avg_goals") is not None else ""))
    return [Variable(
        id=f"{rid}", type="h2h_pattern", subject=key,
        favors=favors_of("h2h_pattern", key, claim, ref),   # type: ignore[arg-type]
        goals=goals_of("h2h_pattern"),                      # type: ignore[arg-type]
        target="h2h", hardness=("hard" if hard == "hard" else "soft"),
        weight=weight, claim=claim, quote=claim, doc_ids=[], from_rule=rid,
        # 🔴 표본 무게가 1.0 미만이면 **근거로 쓰지 않는다**(실측: 3경기 창이 거짓을
        #    말했고 그 수로 언더에 0.9 를 걸어 낙첨했다 — `league.h2h_weight` 독스트링)
        usable_as_basis=(hard == "hard"))]


def _ir_home(rid: str, row: dict, ref: MatchRef, facts: Facts, *,
             state: RunState) -> list[Variable]:
    """IR03 — 홈 이점. ⚠️ **중립 구장이면 만들지 않는다**(거짓 변수가 된다)."""
    from app import rules
    neutral, why = rules.neutral_venue(ref.competition)
    if neutral:
        state.note(f"s5 {rid} — 중립 구장이다({why}) · 변수 안 만든다")
        return []
    claim = f"{ref.home_name} 홈 경기 — 홈 이점"
    return [Variable(
        id=f"{rid}", type="home_field", subject=ref.home,
        favors=favors_of("home_field", ref.home, claim, ref),  # type: ignore[arg-type]
        goals=goals_of("home_field"),                         # type: ignore[arg-type]
        target="home_field", hardness="soft",
        weight=_sample_weight(1)[1], claim=claim, quote=claim, doc_ids=[],
        from_rule=rid,
        # ⚠️ 장소별 표본을 **안 쟀다** — 그래서 근거로는 쓰지 않는다(맥락 전용)
        usable_as_basis=False)]

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **`app/verifylayer.py` 에서 옮겨 왔다** — 사용자 지시 2026-10-06 ⑧
# ══════════════════════════════════════════════════════════════════
#
# > `verifylayer` 내용을 s5 로 옮기고 삭제.
#
# 🔴 옮긴 것은 **검증의 알맹이**다: 인용 정규화(NFKC·합자·따옴표·발음기호),
#    인용 대조, 자카드 유사도, 독립 출처 세기, 등급→무게. ⚠️ 그 함수들의 **실측
#    근거 주석을 그대로** 가져왔다(근거를 잃으면 수를 다시 지어내게 된다).
# ⚠️ 옛 파일의 `Context`·`verify_one`·`verify_all`(옛 dict 경로)은 **안 가져왔다** —
#    v6 는 `_one`·`run` 이 그 일을 `Doc`·`VarCandidate` 타입으로 한다.
#: 🔴 §5-3 — 기사는 **킥오프 7일 전 ~ 킥오프** 사이다.
DATE_WINDOW_DAYS = 7


#: 🔴 §5-7 — *"MinHash 유사도 **0.8 이상**을 한 묶음."*
SIM_SAME = 0.8


#: 🔴🔴 **NFD 로 안 벗겨지는 글자들** — 실측 2026-10-05.
#
#  ⚠️ `teamref._plain` 은 NFD 로 분해해 결합 문자를 버린다. 🔴 그런데 **합자·
#     획이 그어진 글자**는 애초에 분해되지 않는다:
#
#       Ø ø Æ æ ß đ ł Ð þ Þ   → NFD 가 **그대로** 돌려준다(실측)
#       Å å                   → ✅ 분해된다(A + 고리)
#
#  🔴 그래서 매체가 `Odegaard`(ASCII)로 쓰고 인용이 `Ødegaard` 로 오면 **대조가
#     실패한다** — 북유럽·아이슬란드·폴란드·독일 이름이 전부 이 꼴이다.
#  ⚠️ **음차가 아니다** — `Ø`→`O` 는 그 매체들이 ASCII 로 쓸 때 실제로 쓰는
#     글자다(실측: 같은 espn 기사가 `Odegaard`·`Moller` 로 썼다).
_LIGATURES = str.maketrans({
    "Ø": "O", "ø": "o", "Æ": "AE", "æ": "ae", "Œ": "OE", "œ": "oe",
    "ß": "ss", "Đ": "D", "đ": "d", "Ð": "D", "ð": "d",
    "Ł": "L", "ł": "l", "Þ": "TH", "þ": "th", "Ħ": "H", "ħ": "h",
    "Ŀ": "L", "ŀ": "l", "İ": "I", "ı": "i",
})


def norm(text: str) -> str:
    """🔴 §5-1 — *"공백·따옴표 정규화."* ⚠️ 한글을 분해하지 않는다(NFC).

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **넓혔다** — 지시서(오픈월드) §1-1 (2026-10-05)
    ══════════════════════════════════════════════════════════════════

    > 인용 검증(§5-1)이 **정규화 차이**(따옴표·공백·NBSP·대소문자·발음 기호)로
    > 진짜 인용을 떨어뜨리는지 … 정규화 문제면 정규화를 넓히고(NFKC·따옴표
    > 통일·공백 접기)

    ⚠️ 이미 하던 것: NFC · 따옴표 통일 · 공백 접기(`split()` 이 NBSP·전각 공백도
       나눈다) · 소문자.
    🔴 **더한 것: 발음 기호**(`Ødegaard` ↔ `Odegaard`). 매체가 북유럽·포르투갈
       이름을 **양쪽으로** 쓴다(실측: 같은 기사 안에서도 갈린다).
       ⚠️ 벗기는 자리는 `teamref._plain` **하나**다(사본 금지) — 한글·가나·한자는
          그대로 두고 라틴 발음부호만 벗긴다.
    🔴 대시·생략표도 통일한다 — `–`·`—` 와 `…` 는 매체마다 다르게 쓴다.
    """
    from app.teamref import _plain
    raw = unicodedata.normalize("NFC", str(text or ""))
    raw = re.sub(r"[“”„‟＂\"]", '"', raw)
    raw = re.sub(r"[‘’‚‛＇']", "'", raw)
    raw = re.sub(r"[–—―‒]", "-", raw)
    raw = raw.replace("…", "...")
    # 🔴 발음 기호를 벗긴다 — **라틴만**(한글·가나·한자는 `_plain` 이 지킨다)
    raw = raw.translate(_LIGATURES)
    raw = _plain(raw)
    return " ".join(raw.split()).lower()


def quote_ok(quote: str, body: str) -> tuple[bool, str]:
    """🔴🔴 **그 인용이 본문에 있나.** `(있다, 사유)` — §5-1.

    ⚠️ 이 판단이 **인라인으로** 숨어 있었다(지시서 §1-1 이 양방향 고정물을
       요구하는데 **부를 함수가 없었다**). 🔴 한 함수로 뽑는다 — 판정은 한 곳이다.

    🔴 **세 사유를 가른다**(§8-6: 거짓 사유 금지):
         인용이 없다        → `QUOTE_NOT_FOUND`(에이전트)
         본문을 못 받았다    → `BODY_MISSING`(수집/배선)  ⚠️ **다른 고칠 곳**이다
         본문에 없다        → `QUOTE_NOT_FOUND`(에이전트가 지어냈다)
    """
    q = norm(quote)
    if not q:
        return False, "🔴 인용이 **없다**(§5-1)"
    b = norm(body)
    if not b:
        return False, "🔴 **본문을 못 받았다** — 대조할 수 없다(fail-closed)"
    return (True, f"인용이 본문에 있다({len(q)}자)") if q.strip('"') in b else (
        False, f"🔴 인용이 **본문에 없다** — 지어낸 것이다(§5-1): `{q[:50]}`")


def hardness_for(tier: str, *, conflict: bool = False,
                 reverified: bool = True, sources: int = 1) -> int:
    """🔴 §5-5 — 등급 → 무게. ⚠️ 충돌·미재검증이 **내린다**.

    > hardness = 2(official 또는 **national 2매체 일치**) / 1(national·local
    > 단일, aggregator 2매체) / 0(배경·단일 aggregator).
    > §5-7: 충돌이면 두 변수 모두 보존하되 **hardness 0**.
    > §5-8·M31: `reverified:false` → **한 단계 내린다**.
    """
    from app import domains
    base = domains.hardness_of(tier)
    # 🔴 §5-5 — `national` 2매체 일치는 **2** 다
    if tier == "national" and sources >= 2:
        base = 2
    # ⚠️ 단일 `aggregator` 는 **0**(배경)이다 — 2매체면 1
    if tier == "aggregator" and sources < 2:
        base = 0
    if conflict:
        return 0                      # 🔴 §5-7
    if not reverified:
        base = max(base - 1, 0)       # 🔴 §5-8 · M31
    return base


def _shingles(text: str, k: int = 5) -> set[str]:
    t = norm(text)
    return {t[i:i + k] for i in range(max(len(t) - k + 1, 1))}


def similarity(a: str, b: str) -> float:
    """🔴 자카드 유사도. ⚠️ MinHash 의 추정 대상이 이것이다 — 건수가 적어서
    **정확히** 센다(해시 근사가 필요한 규모가 아니다)."""
    sa, sb = _shingles(a), _shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def independent_sources(rows: list[tuple[str, str]]) -> tuple[int, list[list[str]]]:
    """🔴 §5-7 — `(독립 출처 수, 묶음들)`. ⚠️ `rows` 는 `(url, 주장)`."""
    groups: list[list[str]] = []
    texts: list[str] = []
    for url, claim in rows:
        for i, seen in enumerate(texts):
            if similarity(claim, seen) >= SIM_SAME:
                groups[i].append(url)
                break
        else:
            groups.append([url])
            texts.append(claim)
    return len(groups), groups
