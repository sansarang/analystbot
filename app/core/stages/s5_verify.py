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


#: 🔴🔴 **맞대결 기록 꼴** — 사용자 지시 2026-10-06(2차) ②
#
#  > 추출된 맞대결 기록은 **유형과 상관없이** `h2h_pattern` 으로 바꾸고, 같은 표본
#  > 규칙(근거 불가)을 적용한다.
#
#  ⚠️ 실측 2026-10-06 재녹화: *"역대 11승 4무 1패"* 가 `team_stats`(한 번은
#     `individual_title`)로 들어왔다 — 그러면 표본 규칙이 **안 걸린다**(맞대결 1경기
#     표본으로 언더에 0.9 를 걸어 낙첨한 적이 있다 · `league.h2h_weight` 독스트링).
_H2H_PATS = (
    re.compile(r"(\d+)\s*승\s*(\d+)\s*무\s*(\d+)\s*패"),
    re.compile(r"(\d+)\s+wins?[^.\d]{0,12}(\d+|one|two|three|four|five)\s+draws?"
               r"[^.\d]{0,14}(\d+|one|two|three|four|five)\s+(?:loss|losses|defeat)",
               re.I),
)
_WORD_N = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def h2h_record(said: str) -> tuple[int, int, int] | None:
    """🔴 그 글이 **맞대결 전적**을 말하나 — `(승, 무, 패)` 또는 `None`."""
    for pat in _H2H_PATS:
        m = pat.search(str(said or ""))
        if not m:
            continue
        got = []
        for raw in m.groups():
            x = str(raw).strip().lower()
            got.append(int(x) if x.isdigit() else _WORD_N.get(x, -1))
        if all(n >= 0 for n in got) and len(got) == 3:
            return (got[0], got[1], got[2])
    return None


#: 🔴 `stakes` 가 되려면 claim 에 **구체적 동기**가 있어야 한다(사용자 지시 ③)
#
#  > 진출·탈락·우승·기록·감독 거취·순위
# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **동기 낱말**(사용자 지시 2026-10-06(7차) §3 이 넓혔다)
# ══════════════════════════════════════════════════════════════════
#
# > 추출 스키마의 `stakes` 유형 설명에 *"강등·승격·탈락·진출, **이겨야 한다**,
# > **비겨도 된다**, **n골 차 필요**"* 를 구체 동기로 명시한다. 이런 문장은
# > `stakes_vague` 로 **버리지 않는다.**
#
# ⚠️ 종전 목록에는 *"이겨야 한다"·"비겨도 된다"* 가 없었다 — 그래서 경우의 수를
#    그대로 적은 기사 문장이 `stakes_vague` 로 떨어졌다.
_STAKE_WORDS = ("진출", "탈락", "우승", "기록", "거취", "순위", "승점", "플레이오프",
                "강등", "승격", "이겨야", "반드시 이", "비겨도", "무승부면",
                "골 차", "골차", "득점 차", "확정",
                "qualif", "eliminat", "title", "record", "standings",
                "relegat", "promot", "playoff", "play-off", "sack", "contract",
                "points", "must win", "must-win", "need a win", "draw is enough",
                "draw will do", "goal difference", "goals clear", "survive")


def has_info(claim: str) -> tuple[bool, str]:
    """🔴🔴 그 claim 이 **사실을 말하나** — *"정보가 없다"* 면 거짓이다(9차 ③).

    🔴 낱말표는 `config/variable_types.yaml` 의 `no_info_words` 다(사본 금지).
    ⚠️ *"부상이 없다"* 와 *"부상 정보가 없다"* 는 다르다 — 전자는 사실이고 후자는
       **못 알아낸 것**이다. 🔴 표의 낱말은 뒤쪽만 담는다.
    """
    from app import rules
    low = norm(claim)
    for w in (rules._load(rules.VARIABLE_TYPES).get("no_info_words") or []):
        if norm(str(w)) in low:
            return False, (f"🔴 *\"{w}\"* — **없음의 보고**는 사실이 아니다"
                           f"(방향을 붙일 근거가 없다) · {str(claim)[:60]}")
    return True, ""


def stakes_ok(claim: str) -> tuple[bool, str]:
    """🔴 그 claim 이 **동기**를 말하나. ⚠️ 일정 안내는 동기가 아니다."""
    low = norm(claim)
    hit = [w for w in _STAKE_WORDS if w in low]
    if hit:
        return True, f"동기 낱말 {hit[:3]}"
    return False, (f"🔴 구체적 동기가 없다(진출·탈락·우승·기록·감독 거취·순위) — "
                   f"{str(claim)[:60]}")


def run(ref: MatchRef, facts: Facts, docs: list[Doc],
        cands: list[VarCandidate], *, state: RunState,
        turnover: dict | None = None) -> list[Variable]:
    """🔴 후보를 검증해 변수로. ⚠️ 버린 것은 **사유와 함께** 남는다(#3).

    🔴🔴 `turnover` 가 켜진 팀은 **`squad_rotation` 변수**를 하나 만든다(상성 엔진
       지시서 V-3) — 그래야 축0·축1·축3 이 선수단 교체를 **입력으로** 받는다.
    """
    by_id = {d.id: d for d in docs}
    rows: list[dict] = []
    for i, c in enumerate(cands):
        got = _one(c, ref, by_id, state=state, n=i, facts=facts)
        if got is not None:
            rows.append(got)
    merged = _merge(rows, state=state, facts=facts)
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
        usable = level >= 1
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **맞대결은 표본 규칙을 지난다**(사용자 지시 2026-10-06(2차) ②)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 추출된 맞대결 기록은 유형과 상관없이 `h2h_pattern` 으로 바꾸고,
        #  > **같은 표본 규칙(근거 불가)** 을 적용한다.
        if row["type"] == "h2h_pattern":
            rec = h2h_record(row["claim"])
            n_games = sum(rec) if rec else 0
            hard_name, weight = _sample_weight(n_games)
            name, level = hard_name, (2 if hard_name == "hard" else 1)
            usable = hard_name == "hard"
            state.note(f"s5 맞대결 표본 {n_games}경기 → 무게 {weight} · "
                       f"근거 {'가능' if usable else '불가'}(표본 규칙)")
            # 🔴 **구조 사실과 숫자가 다르면 충돌**이다 — 공식이 이긴다
            got = _h2h_clash(rec, facts)
            if got:
                state.drop(f"s5/h2h/R{i}", DropReason.CONFLICT, got)
                continue
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **기사 결장 ↔ XI 대조**(사용자 지시 2026-10-06(3차) ⑤)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 검증된 `absence` 변수의 `target` 이 예상/확정 XI 에 있으면 **충돌로
        #  > 표시하고 그 변수를 soft 로 내린다.**
        #
        #  ⚠️ 거꾸로(예상 명단에 결장자가 있으면 그 선수를 빼는 것)는 s2 가 한다 —
        #     여기는 **기사가 결장이라 했는데 명단에 있는** 경우다. 🔴 어느 쪽도
        #     지우지 않는다: 둘 다 적고 **등급만 내린다**(무엇이 맞는지는 킥오프가 말한다).
        clash = ""
        if row["type"] in ABSENCE_KINDS and row.get("target"):
            clash = _xi_clash(str(row["target"]), row["subject"], facts)
        if clash:
            level = min(level, 1)
            name = _LEVEL_NAME.get(level, "soft")
            state.drop(f"s5/xi/{row['target'][:20]}", DropReason.CONFLICT,
                       clash)
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **구조 사실에 있는 결장은 hard·근거 가능**(사용자 지시 2026-10-11 ⑤)
        # ══════════════════════════════════════════════════════════════
        #
        #  > fotmob **결장 명단(구조 사실)** 에 있는 결장은 **기사 출처 수와
        #  > 상관없이 hard·근거 가능**.
        #
        #  ⚠️ 실사고 2026-10-11(LAFC): 뮐러 결장이 **fotmob 결장 명단에 있는데도**
        #     기사가 1곳이라 `soft · 🔴 근거 불가(맥락)` 로 내려갔다 — 구조 사실을
        #     기사 수로 깎은 것이다. 🔴 명단에 있으면 그것이 **더 센 근거**다.
        if row["type"] in ABSENCE_KINDS and row.get("target") \
                and _in_missing(str(row["target"]), row["subject"], facts):
            level, usable = 2, True
            state.note(f"s5 R{i} `{row['target']}` — **구조 결장 명단에 있다** → "
                       f"hard·근거 가능(기사 출처 수와 무관 · ⑤)")
        # 🔴 **팀 귀속을 못 가린 결장 변수는 근거로 못 쓴다**(지시 2 · 맥락만)
        if row.get("_basis_off"):
            usable = False
            state.note(f"s5 R{i} 결장 귀속 미확정 → **근거 불가**"
                       f"({str(row['_basis_off'])[:70]})")
        out.append(Variable(
            id=f"R{i}", type=row["type"], subject=row["subject"],
            favors=row["favors"], goals=row.get("goals", "none"),
            target=str(row.get("target") or ""),
            match_link=str(row.get("match_link") or ""),
            hardness=("hard" if level == 2 else "soft"),
            weight=float(WEIGHT_OF[name]), claim=row["claim"],
            quote=row["quote"], doc_ids=row["doc_ids"],
            # 🔴 §3-4 — **어느 하위가 나른 변수인가**(🆕 블록이 이것으로 고른다)
            subtask=str(row.get("subtask") or ""),
            # 🔴🔴 **근거로 쓸 수 있나** — 등급 0(단일 aggregator·충돌)은 못 쓴다.
            #    ⚠️ 옛 경로가 `hardness == "none"` 으로 가른 그 선이다
            #       (`analyze.split_basis`) — 뜻을 옮겨 적었다.
            usable_as_basis=usable))
        if level < 1:
            state.note(f"s5 R{i} 는 **근거로 못 쓴다**(등급 {level} · 출처 "
                       f"{n_src}곳 · {tier}) — 맥락으로만 보낸다")
    out += _from_facts(ref, facts, state=state)
    # 🔴🔴 V-3 — **선수단 교체 변수**(깃발을 변수로 만든다 · 아래 함수 주석 참고)
    out += _turn_vars(ref, turnover, state=state)
    state.set("variables", len(out))
    return out


def _turn_vars(ref: MatchRef, turnover: dict | None, *,
               state: RunState) -> list[Variable]:
    """🔴🔴 상성 엔진 V-3 — **선수단 교체 변수**(`squad_rotation`). 켜진 팀만.

    > squad_turnover(IR03 포함) │ 축0 호흡, 축1·축3 r 가중 │ V1 기준 낡음 │ 근거

    🔴 이 변수가 있어야 S2 가 그 셋을 할 수 있다 — ⚠️ 실측 2026-10-10: 선수단
       교체가 **깃발로만** 있어 배치표를 지나지 않았고, 김천 VariableSet 에
       `squad_rotation` 이 **0개**였다(축이 받을 통로가 없었다).
    ⚠️ 깃발이 꺼졌으면 **만들지 않는다**(지어낸 변수 금지).
    """
    out: list[Variable] = []
    for side, one in dict(turnover or {}).items():
        box = dict(one)
        if not box.get("on"):
            continue
        key = str(getattr(ref, side, "") or "")
        name = str(getattr(ref, f"{side}_name", "") or "")
        gone = [str(x) for x in (box.get("off_squad") or [])]
        out.append(Variable(
            id=f"TURN-{side}", type="squad_rotation", subject=key,
            favors=("away" if side == "home" else "home"),
            goals="none", target="squad_rotation:turnover", hardness="hard",
            weight=_sample_weight(5)[1],
            claim=(f"{name} 선수단 교체 — {box.get('why')}"
                   + (f" · 명부에 없는 과거 선발 {len(gone)}명" if gone else "")),
            quote=str(box.get("why") or ""), doc_ids=[],
            from_rule="IR03T", usable_as_basis=True))
        state.note(f"s5 선수단 교체 변수 — `TURN-{side}` ({name})")
    return out


#: 🔴 센 등급이 먼저다 — 한 주장을 여러 매체가 말하면 **가장 센 쪽**으로 센다
_TIER_ORDER = ("official", "national", "local", "aggregator", "tip", "dead")


#: 🔴🔴 V-2 — **유형이 반드시 담아야 하는 말**(그 말이 없으면 유형이 거짓이다).
#  ⚠️ 실측 2026-10-10: *"4-4-2 포메이션으로 경기에 임한다"* 가 `def_absence` 로
#     들어왔다 — 결장 얘기가 한 글자도 없다.
#  🔴 **여는 쪽으로 짠다** — 목록에 없는 유형은 검사하지 않는다(거짓 탈락이 더
#     나쁘다). 늘리는 것은 **실측으로** 한다.
_TYPE_WORDS: dict[str, tuple[str, ...]] = {
    "absence": ("결장", "빠진", "빠졌", "제외", "부상", "못 나", "못나", "없다",
                "아웃", "out", "miss", "injur", "doubt", "unavailab"),
    "def_absence": ("결장", "빠진", "빠졌", "제외", "부상", "없다", "out",
                    "miss", "injur", "suspend", "doubt"),
    "absence_att": ("결장", "빠진", "빠졌", "제외", "부상", "없다", "out",
                    "miss", "injur", "suspend", "doubt"),
    "suspension": ("정지", "징계", "경고", "퇴장", "누적", "suspend", "ban",
                   "red card"),
    "returning": ("복귀", "합류", "전역", "제대", "돌아", "return", "back",
                  "available"),
    "national_duty_return": ("복귀", "합류", "대표", "국가대표", "return",
                             "national"),
    "fatigue": ("휴식", "일정", "연전", "피로", "이동", "체력", "rest", "days",
                "fixture", "travel", "fatigu"),
    "travel_schedule": ("이동", "원정", "비행", "시차", "일정", "travel",
                        "trip", "away"),
}


#: 🔴 유형–내용 검사가 보는 **언어들**. ⚠️ 이름은 `search_words.yaml` 이 든다 —
#   여기서 낱말을 적지 않는다(#1 사본 금지).
_FIT_LANGS: tuple[str, ...] = ("ko", "en", "ja", "nl", "es", "pt", "de", "fr")


def _type_words(kind: str) -> tuple[str, ...]:
    """🔴🔴 그 유형이 내용에 있어야 하는 **낱말들** — 손 표 + **개념 낱말 표**.

    ⚠️ 실사고 2026-10-11(가와사키): 추출이 **후보 2개**를 냈는데 둘 다
       `type_content_mismatch` 로 죽어 기사 변수가 0개가 됐다. 🔴 까닭은
       `_TYPE_WORDS` 가 **한국어·영어만** 들고 있어서다 — 일본 기사의 `欠場`·
       `離脱` 이 "그 말이 한 글자도 없다"로 읽혔다.
    🔴 그런데 **개념 낱말 표에 현지어가 이미 있다**(`rules.local_words('injury',
       'ja')` → `['欠場','故障者','離脱','登録抹消']`). 그 표에서 자라게 한다 —
       손으로 늘리면 그 순간 사본이 된다(#1).
    """
    from app import rules
    from app.core import adapt as _ad
    got = list(_TYPE_WORDS.get(str(kind or "")) or ())
    # 🔴🔴 **손 표에 없는 유형은 그대로 통과**다 — ⚠️ 실사고 2026-10-11: 개념
    #    표에서 자라게 했더니 `team_stats` 처럼 **문이 없던 유형에 새 문**이
    #    생겼다(옛 계약이 잡았다). 그러면 수확이 **줄어든다** — 이 고침의 뜻은
    #    문을 **느슨하게** 하는 것이지 조이는 것이 아니다.
    if not got:
        return ()
    said = _ad.catalog_type(str(kind or "")) or str(kind or "")
    concept = rules.word_concept(said)
    if concept:
        for lang in _FIT_LANGS:
            for one in (rules.local_words(concept, lang) or []):
                # 🔴 질의용 낱말은 **구**일 수 있다(`injury news`) — 그 안의
                #    토막도 넣는다(내용에는 한 낱말로 나온다).
                for tok in str(one).split():
                    if len(tok) >= 2 and tok not in got:
                        got.append(tok)
    return tuple(got)


def _type_fits(kind: str, said: str) -> str:
    """🔴 V-2 — 유형이 그 내용과 **맞나**. 어긋나면 사유 글자, 맞으면 빈 글자.

    ⚠️ 목록에 없는 유형은 **통과**다(모르는 것으로 버리지 않는다 · #4).
    """
    want = _type_words(str(kind or ""))
    if not want:
        return ""
    low = str(said or "").lower()
    if any(w.lower() in low for w in want):
        return ""
    return (f"🔴 유형 `{kind}` 인데 그 말이 **한 글자도 없다** — "
            f"필요한 말 {list(want)[:5]}… · 내용 `{str(said)[:60]}`")


def _one(c: VarCandidate, ref: MatchRef, by_id: dict[str, Doc], *,
         state: RunState, n: int, facts: Facts) -> dict | None:
    """🔴 후보 하나 — 검사 순서는 **싼 것부터**다(문서 → 인용 → 날짜 → 신원 → 방향)."""
    from app import verify
    what = f"s5/{c.subtask}/{c.type}/{n}"
    doc = by_id.get(c.doc_id)
    if doc is None:
        # ⚠️ 스키마 enum 이 막으므로 **여기 오면 재생본이 어긋난 것**이다
        state.drop(what, DropReason.UNKNOWN_VAR,
                   f"`{c.doc_id}` 는 그 하위에 넘긴 문서가 아니다")
        return None
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **유형–내용 일치 검사**(상성 엔진 지시서 V-2)
    # ══════════════════════════════════════════════════════════════════
    said_bad = _type_fits(str(c.type), f"{c.claim} {c.quote}")
    if said_bad:
        state.drop(what, DropReason.TYPE_CONTENT_MISMATCH, said_bad)
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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **경기 후 기사인지는 날짜가 말한다 — 낱말이 아니다**
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고 2026-10-10: `verify.POST_GAME_MARKS` 에 맨 `승리`·`패배`·
    #     `역전승` 이 들어 있어 **한국어 미리보기 기사가 전부 떨어졌다**
    #     (*"무승 깨는 **대역전승**"* · *"서울전 2연승 도전"* 은 **지난 경기**
    #     얘기다). FC서울–제주 실행에서 `post_match` **7건**이 그것이고, 그래서
    #     🆕 새 사실이 0건이었다.
    #  🔴 우리는 **발행일과 킥오프를 둘 다 안다**(위에서 발행일 없는 Doc 은 이미
    #     버렸다). 발행이 킥오프보다 뒤면 경기 후 기사다 — 그것이 정확하다.
    #  ⚠️ 발행일이 **날짜만**(시각 00:00)이면 그 비교로는 못 가른다 — 그때만
    #     낱말 검사로 떨어진다(fail-closed).
    said_when = doc.published_at
    if said_when >= ref.kickoff_utc:
        state.drop(what, DropReason.POST_MATCH,
                   f"발행 {said_when:%Y-%m-%d %H:%M}Z 가 킥오프 "
                   f"{ref.kickoff_utc:%Y-%m-%d %H:%M}Z **뒤**다")
        return None
    date_only = (said_when.hour == 0 and said_when.minute == 0
                 and said_when.second == 0)
    if date_only:
        # 🔴🔴 **낱말만으로 버리지 않는다** — 두 팀 + 스코어 + 종료 낱말이 **한
        #    문장에** 있어야 한다(규칙은 `verify.ended_this_match` 하나다).
        #
        #  ⚠️ 실사고 2026-10-10: `verify.not_post_game` 은 맨 `승리`·`패배`·
        #     `역전승` 을 보고 버렸다 — 한국어 미리보기(*"무승 깨는 **대역전승**"*
        #     는 **지난 경기** 얘기다)가 FC서울–제주 실행에서 **38건** 떨어졌고
        #     그래서 🆕 새 사실이 0건이었다.
        from app.core.stages.s3_docs import names_of
        got, said = verify.ended_this_match(f"{doc.title}\n{doc.body}",
                                            names_of(ref))
        if got:
            state.drop(what, DropReason.POST_MATCH,
                       f"발행 시각이 **날짜뿐**이고 본문이 이 경기 결과를 "
                       f"말한다 — {said[:80]}")
            return None
    if not _mentions(c.subject, doc, ref):
        state.drop(what, DropReason.IDENTITY_MISMATCH,
                   f"{doc.id} 본문이 `{c.subject}` 를 말하지 않는다")
        return None
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **이 경기 이야기인가**(사용자 지시 2026-10-06(4차) ①-b)
    # ══════════════════════════════════════════════════════════════════
    ok_m, said_m = match_link_ok(c, doc, ref, facts)
    if not ok_m:
        state.drop(what, DropReason.OFF_MATCH, said_m[:120])
        return None
    # ══════════════════════════════════════════════════════════════════
    # 🔴 ② **맞대결 기록은 유형과 상관없이 `h2h_pattern`**(사용자 지시 ②)
    # ══════════════════════════════════════════════════════════════════
    kind, target = c.type, str(c.target or "")
    rec = h2h_record(c.claim)
    if rec is not None and kind != "h2h_pattern":
        state.note(f"s5 {what} `{kind}` → **h2h_pattern** 으로 바꿨다"
                   f"(맞대결 전적 {rec[0]}승 {rec[1]}무 {rec[2]}패)")
        kind, target = "h2h_pattern", "h2h"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **"정보가 없다"는 사실이 아니다**(사용자 지시 2026-10-06(9차) ③)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 카자흐–페로: *"확인된 부상 또는 출전 정지 정보는 **없다**"* 가
    #     `absence_att` 변수로 섰다(`R1`). 🔴 없음의 보고로는 방향·득점을 못 정한다.
    ok_i, said_i = has_info(c.claim)
    if not ok_i:
        state.drop(what, DropReason.NO_INFO, said_i[:120])
        return None
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **"선발 제외"는 주전에게만 결장이다**(사용자 결정 2026-10-10 §6)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 선발 제외를 결장으로 보지 않는다 — 그 선수의 시즌 **선발 비율이 30%
    #  > 미만**이면. (실례: **가시와 세가와**는 교체로 7골을 넣었다.)
    #
    #  🔴 교체로 나오는 선수가 선발에서 빠진 것은 **평소**다 — 그것을 결장으로
    #     읽으면 매 경기 그 팀에 불리한 변수가 하나 생긴다.
    if kind in ABSENCE_KINDS:
        ok_b, said_b = bench_regular(c.claim, target, facts)
        if ok_b:
            state.drop(what, DropReason.BENCH_REGULAR, said_b[:130])
            return None
    # ══════════════════════════════════════════════════════════════════
    # 🔴 ③ **`stakes` 는 구체적 동기가 있을 때만**(사용자 지시 ③)
    # ══════════════════════════════════════════════════════════════════
    if kind == "stakes":
        ok_s, said_s = stakes_ok(c.claim)
        if not ok_s:
            state.drop(what, DropReason.STAKES_VAGUE, said_s[:110])
            return None
    elif kind == "individual_title":
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **기록 도전은 수치가 있으면 통과**(사용자 지시 2026-10-06(3차) ③)
        # ══════════════════════════════════════════════════════════════
        #
        #  > `individual_title`(기록 도전)은 `stakes_vague` 검사에서 **제외** —
        #  > **구체적 수치가 있으면** 통과.
        #
        #  ⚠️ 실측: *"10월 홈 친선 일정"* 이 `individual_title` 로 들어와 `득점↑` 를
        #     받았다(일정 안내는 기록 도전이 아니다). 🔴 그래서 **수치**를 요구한다 —
        #     `58골`·`11승 4무 1패`·`기록 경신` 처럼 셀 수 있는 것이 있어야 한다.
        if not re.search(r"\d", str(c.claim)):
            state.drop(what, DropReason.STAKES_VAGUE,
                       f"🔴 기록 도전인데 **수치가 없다** — {str(c.claim)[:60]}")
            return None
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **결장 선수 → 팀 대조는 코드가 한다**(사용자 지시 2026-10-07)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-07(멕시코–칠레): **멕시코** 선수 `Gilberto Mora` 의 결장이
    #     s4 출력에서 `team:000047`(칠레)로 붙어 `favors=home`·`득점↑` 로 뒤집혔다.
    #     가설·시나리오 B·E 가 그것을 *"상대 결장"* 으로 읽었다.
    #  🔴 그래서 **방향을 세기 전에** 주체를 고친다 — `favors` 는 고친 주체로 센다.
    subject, basis_off = c.subject, ""
    if kind in ABSENCE_KINDS and target:
        got, how, why = team_of_player(target, ref, facts, doc)
        if got and got != c.subject:
            # 🔴 **정정한다 — 조용히 버리지 않는다**(카드 블록 1 에 적는다)
            subject = got
            state.drop(what, DropReason.TEAM_REATTACHED,
                       f"결장 귀속 정정: {target} "
                       f"{_who(c.subject, ref)}→{_who(got, ref)} ({why})")
        elif not got:
            basis_off = why
            state.drop(what, (DropReason.TEAM_AMBIGUOUS if how == "ambiguous"
                              else DropReason.TEAM_UNRESOLVED), why[:120])
        else:
            state.note(f"s5 {what} 결장 귀속 확인 — {why}(길 {how})")
    fav = favors_of(kind, subject, c.claim, ref)
    if fav not in _FAVORS:
        # 🔴 **방향 규칙이 없는 유형**이다 — 한쪽으로 밀지 않는다(지어내지 않는다)
        state.drop(what, DropReason.TYPE_OFF_CATALOG,
                   f"`{kind}` 방향 규칙이 없다(받은 값 {fav!r})")
        return None
    return {"type": kind, "subject": subject, "favors": fav,
            # 🔴 대조를 통과하지 못했으면 **근거로 쓰지 않는다**(맥락만 · 지시 2)
            "_basis_off": basis_off,
            "goals": goals_of(kind), "target": target,
            "match_link": str(c.match_link or ""),
            "claim": c.claim, "quote": quote, "doc_ids": [doc.id],
            # 🔴 §3-4 — **어느 하위가 나른 사실인가**(🆕 블록이 이것으로 고른다)
            "subtask": str(c.subtask or ""),
            # 🔴 유형이 바뀌면 방향을 다시 세야 한다 — 그 경기 맥락을 함께 든다
            "_ref": ref}


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


def _who(key: str, ref: MatchRef) -> str:
    """🔴 열쇠 → **사람이 읽는 팀 이름**(정정 줄에 쓴다). ⚠️ 모르면 열쇠 그대로."""
    if key == ref.home:
        return ref.home_name or key
    if key == ref.away:
        return ref.away_name or key
    return key


def _mentions(subject: str, doc: Doc, ref: MatchRef) -> bool:
    """🔴 그 문서가 **그 팀**을 말하나 — 열쇠에서 이름을 꺼내 본다(§8-1).

    ⚠️ 이름을 인자로 받지 않는다 — 받으면 또 하나의 해석 지점이 된다.
    """
    from app.core.stages.s3_docs import names_of
    home, away = names_of(ref)
    names = home if subject == ref.home else away
    said = f"{doc.title} {doc.body}".lower()
    return any(len(str(x)) >= 3 and str(x).lower() in said for x in names)


#: 🔴🔴 **결장 계열** — 유형을 **열쇠에서 뺀다**(사용자 지시 2026-10-06(2차) ①)
#
#  > 병합 열쇠에서 `type` 을 뺀다: 결장 계열(`absence_att`·`def_absence`·`fatigue`·
#  > `injury`)은 `subject`+`target` 만으로 묶는다.
#
#  ⚠️ 실측 2026-10-06 재녹화: 같은 김민재 결장이 `fatigue`·`absence_att`·`def_absence`
#     **세 변수**로 남았다(유형이 열쇠에 있어서). 🔴 한 사실은 한 변수다.
#  🔴 축구 완성 지시서 §1-1 이 **`suspension` 을 이름으로 더했다**(결장 계열 다섯).
ABSENCE_KINDS = ("absence", "absence_att", "def_absence", "fatigue", "injury",
                 "suspension")

#: 🔴🔴 **감독 계열도 묶는다**(사용자 지시 2026-10-06(3차) ⑥)
#
#  > 병합 열쇠를 결장 계열 **밖으로 확장**: `coach_conflict`·`coach_intent` 도
#  > `subject+target`(선수·포지션)로 묶는다.
#
#  ⚠️ 실측(콜롬비아–페루): `Kevin Mier` 하나를 두고 `coach_intent` 둘·
#     `coach_conflict` 하나가 따로 섰고, `Aldair Quintana`·`Álvaro Montero` 도
#     갈렸다. 🔴 한 선수의 **같은 이야기**다.
# 🔴🔴 **`squad_rotation` 까지 한 묶음**(사용자 지시 2026-10-06(9차) ②) — 같은 팀의
#    같은 주제(로테이션/선수 기용/전술 변경)면 **하나**다.
COACH_KINDS = ("coach_conflict", "coach_intent", "squad_rotation")


def coach_topic(claim: str, quote: str = "") -> str:
    """🔴 그 문장이 **어느 주제**인가 — `rotation`·`tactic`·`selection`. 모르면 `""`.

    🔴 낱말표는 `config/variable_types.yaml` 의 `coach_topics` 다(사본 금지).
    ⚠️ 못 가리면 빈 글자이고, 그때 열쇠는 **대상 글자**로 간다(종전과 같다).
    """
    from app import rules
    low = norm(f"{claim} {quote}")
    box = dict((rules._load(rules.VARIABLE_TYPES).get("coach_topics") or {}))
    for topic, said in box.items():
        for w in (dict(said).get("words") or []):
            if norm(str(w)) in low:
                return str(topic)
    return ""


def merge_key(subject: str, kind: str, target: str, *, claim: str = "",
              quote: str = "") -> tuple[str, str, str]:
    """🔴🔴 **사실 하나의 열쇠** — `(주체, 유형군, 핵심 대상)`.

    🔴 결장 계열은 **유형 자리에 `absence*` 한 글자**가 들어간다 — 그래서 모델이
       피로/수비 결장/공격 결장으로 갈라 적어도 **한 사실**로 묶인다.
    🔴 감독·로테이션 계열(`coach*`)은 **주제**가 대상 자리에 들어간다(9차 ②) — 실측
       2026-10-06: 로테이션 이야기 하나가 `coach_intent` **다섯 줄**로 서서 ③ 이동을
       다섯 번 받았다. ⚠️ 주제를 못 가리면 대상 글자로 간다.
    🔴 대상 글자는 **정규화**해서 비교한다 — `Kim Min-jae`·`김민재`·`KIM MIN-JAE` 가
       갈리면 열쇠가 쪼개진다(정규화는 이 파일의 `norm` 하나다).
    """
    said = str(kind)
    group = said
    spot = norm(str(target))
    if said in ABSENCE_KINDS:
        group = "absence*"
    elif said in COACH_KINDS:
        group = "coach*"
        topic = coach_topic(claim, quote)
        if topic:
            spot = f"주제:{topic}"
    return (str(subject), group, spot)


#: 🔴 포지션 낱말 → 결장 유형. ⚠️ **자료가 있을 때만** 쓴다(없으면 다수결로 간다).
#  🔴 실측 2026-10-06: fotmob 는 포지션을 **묶음 글자**로 준다(`GK`·`DF`·`MF`·`FW` —
#     `usualPlayingPositionId` 0/1/2/3 에서 왔다). ⚠️ `MF` 는 **어느 쪽도 아니다** —
#     미드필더 결장을 수비/공격 결장으로 적으면 방향이 거짓이 된다.
_DEF_WORDS = ("gk", "df", "수비", "센터백", "골키퍼", "키퍼", "포수", "유격수",
              "defender", "centre-back", "center-back", "goalkeeper", "keeper",
              "back", "cb")
_ATT_WORDS = ("fw", "공격", "윙어", "스트라이커", "포워드", "forward", "striker",
              "winger", "attacker")


def position_of(target: str, facts: Facts) -> str:
    """🔴 그 선수의 포지션 — **XI·명단·어댑터 사실에 있으면**(사용자 지시 ①).

    돌려주는 것은 `"def"`·`"att"`·`""`(모른다). ⚠️ 이름만 있는 명단에서는 **모른다**가
    정직한 답이다 — 포지션을 지어내면 그 변수의 방향이 거짓이 된다.
    """
    said = norm(target)
    if not said:
        return ""
    # 🔴 **경기 단위 포지션 표**가 원본이다(§2 `player_pos`) — s2 가 XI·결장에서 만든다
    for name, pos in (facts.player_pos or {}).items():
        if said not in norm(name) and norm(name) not in said:
            continue
        low = norm(pos)
        if any(low == w or low.startswith(w) for w in _DEF_WORDS):
            return "def"
        if any(low == w or low.startswith(w) for w in _ATT_WORDS):
            return "att"
        # ⚠️ `MF` 는 어느 쪽도 아니다 — 모른다고 답한다(지어내지 않는다)
        return ""
    return ""


def kind_after_merge(kinds: list[str], target: str, facts: Facts
                     ) -> tuple[str, str]:
    """🔴🔴 **묶인 결장 변수의 유형** — `(유형, 사유)`(사용자 지시 2026-10-06(2차) ①).

    > 묶인 변수의 유형은 **그 선수의 포지션**으로 정한다(XI·명단·어댑터 사실에
    > 있으면). 포지션을 모르면 모델이 단 유형 중 **다수결**, 동률이면
    > `def_absence`/`absence_att` 를 **버리고** `absence`.
    """
    got = [k for k in kinds if k]
    pos = position_of(target, facts)
    if pos == "def":
        return "def_absence", f"포지션 자료가 **수비**라고 말한다({target})"
    if pos == "att":
        return "absence_att", f"포지션 자료가 **공격**이라고 말한다({target})"
    tally: dict[str, int] = {}
    for k in got:
        tally[k] = tally.get(k, 0) + 1
    if tally:
        top = max(tally.values())
        best = sorted(k for k, n in tally.items() if n == top)
        if len(best) == 1:
            return best[0], (f"포지션 자료가 없다 → 다수결 {tally}")
        # 🔴 **동률이면 방향을 고르지 않는다** — 수비/공격 결장을 버리고 일반 결장으로
        return "absence", (f"포지션 자료가 없고 **동률**이다({tally}) → "
                           f"`def_absence`/`absence_att` 를 버리고 `absence`")
    return "absence", "유형이 없다 → `absence`"


def _merge(rows: list[dict], *, state: RunState,
           facts: Facts | None = None) -> list[dict]:
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
        # 🔴 9차 ② — 감독·로테이션은 **주제**로 묶는다(claim·quote 를 넘겨야 센다)
        key = merge_key(row["subject"], row["type"], target,
                        claim=str(row.get("claim") or ""),
                        quote=str(row.get("quote") or ""))
        keep = seen.get(key)
        if keep is None:
            row["kinds"] = [row["type"]]
            seen[key] = row
            out.append(row)
            continue
        for d in row["doc_ids"]:
            if d not in keep["doc_ids"]:
                keep["doc_ids"].append(d)
        # 🔴 **모델이 단 유형을 모아 둔다** — 묶인 뒤 포지션·다수결로 하나를 고른다
        keep.setdefault("kinds", [keep["type"]]).append(row["type"])
        # 🔴 귀속을 **가린 쪽이 이긴다** — 한 기사가 팀을 못 말했어도 다른 기사가
        #    말했으면 그 사실은 가려진 것이다(지시 2).
        if not row.get("_basis_off"):
            keep["_basis_off"] = ""
        # 🔴🔴 §3-3·§3-4 — **F(새 사실 72시간)가 함께 찾았으면 새 사실이다**
        #
        #  > 같은 사실 여러 기사 → 하나로 묶고 **출처 수만 올린다**.
        #
        #  ⚠️ 묶으면 **먼저 들어온 하위**가 남는다 — A~D 가 먼저면 그 변수는
        #     🆕 블록에서 사라진다. 🔴 F 가 같은 사실을 72시간 창에서 찾았다면
        #     그것은 **새로 나온 사실**이고, 사용자가 그것을 보라고 했다.
        if str(row.get("subtask") or "").startswith("F-") \
                and not str(keep.get("subtask") or "").startswith("F-"):
            keep["subtask"] = str(row["subtask"])
        state.drop(f"s5/{row['type']}/{target[:24]}", DropReason.DUPLICATE,
                   f"같은 사실로 묶었다(열쇠 {key[1]}·{key[2][:20]}) → 출처 "
                   f"{len(keep['doc_ids'])}곳")
    # ── 🔴 결장 계열의 **유형을 다시 정한다**(사용자 지시 2026-10-06(2차) ①)
    box = facts if facts is not None else Facts()
    for row in out:
        kinds = [str(k) for k in (row.get("kinds") or [row["type"]])]
        if any(k in COACH_KINDS for k in kinds) and len(set(kinds)) > 1:
            # 🔴 감독 계열은 **다수결**이다 — 포지션은 뜻이 없다(사람 결정이다)
            tally: dict[str, int] = {}
            for k in kinds:
                tally[k] = tally.get(k, 0) + 1
            best = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            state.note(f"s5 감독 계열 유형을 `{best}` 로 정했다 — 다수결 {tally}")
            row["type"] = best
            row["favors"] = _side_for(best, row, box)
            row["goals"] = goals_of(best)
            continue
        if not any(k in ABSENCE_KINDS for k in kinds):
            continue
        got, why = kind_after_merge(kinds, str(row.get("target") or ""), box)
        if got != row["type"] or len(set(kinds)) > 1:
            state.note(f"s5 결장 유형을 `{got}` 로 정했다 — {why} "
                       f"(모델이 적은 것: {sorted(set(kinds))})")
        row["type"] = got
        row["favors"] = _side_for(got, row, box)
        row["goals"] = goals_of(got)
    return out


def _side_for(kind: str, row: dict, facts: Facts) -> str:
    """🔴 유형이 바뀌면 **방향도 다시 센다** — 방향은 카탈로그가 정한다(§3)."""
    ref = row.get("_ref")
    if ref is None:
        return str(row.get("favors") or "both")
    return favors_of(kind, str(row["subject"]), str(row.get("claim") or ""), ref)


def interpret_rules() -> list[dict]:
    """🔴 해석 규칙 표 — `config/interpret_rules.yaml` 하나가 원본이다(사본 금지).

    🔴 두 묶음을 **이어서** 돌려준다(사용자 지시 2026-10-06(2차) ④):
       `rules`(S01~) 구조 사실 규칙 · `ir_table`(IR01~) 접목 지시서의 해석 규칙.
    ⚠️ `ir_table` 은 **지금 비어 있다** — 그 표가 이 기계에 오지 않았다(파일 머리에
       적었다). 표가 오면 이 함수가 **그대로 읽는다**(코드를 고칠 일이 없다).
    """
    from app import rules
    box = rules._load("config/interpret_rules.yaml")
    return [dict(r) for r in (box.get("rules") or [])] + \
           [dict(r) for r in (box.get("ir_table") or [])]


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
        # 🔴 열쇠는 `disabled` 다 — ⚠️ `off` 는 **YAML 이 불리언으로 읽는다**(실측)
        if row.get("disabled"):
            state.note(f"s5 {rid}({kind}) **끈 규칙** — {row['disabled']}")
            continue
        # 🔴 **종목으로 가른다**(축구 완성 지시서 §3: IR08~IR10 은 축구에서 끈다)
        sports = [str(x) for x in (row.get("sports") or [])]
        if sports and ref.sport not in sports:
            state.note(f"s5 {rid}({kind}) — `{ref.sport}` 규칙이 아니다({sports})")
            continue
        if kind == "recent_pattern":
            out += _ir_recent(rid, row, ref, facts, state=state)
        elif kind == "h2h_pattern":
            out += _ir_h2h(rid, row, ref, facts, state=state)
        elif kind == "home_field":
            out += _ir_home(rid, row, ref, facts, state=state)
        elif kind == "match_type" and rid.startswith("S"):
            out += _ir_match_type(rid, row, ref, facts, state=state)
        elif rid.startswith("IR"):
            out += _ir_soccer(rid, row, ref, facts, state=state)
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
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **폼 변수에 득점 방향을 단다**(사용자 지시 2026-10-07 §3)
        # ══════════════════════════════════════════════════════════════
        #
        #  > `recent_pattern`(S01)의 **보정 평균 득점**이 그 기준의 팀당 몫(평균
        #  > 득점÷2)보다 **0.2 이상 낮으면 `goals=down`**, 0.2 이상 높으면 `up`,
        #  > 그 사이면 `none`. **실점 평균도 같은 방식으로 따로** 단다.
        #
        #  ⚠️ 실측 2026-10-07(멕시코–칠레): 두 팀 보정 득점이 **0.667** 인데 폼
        #     변수의 `goals` 가 `none` 이어서 양상이 **난타전**으로 섰고, 논평이
        #     *"서로를 열어두고 주고받는다"* 를 그 변수로 근거 삼았다.
        kind = comp_kind(ref, facts)
        got_dir, got_against, why_dir = _form_goal_dirs(box, trim, kind)
        claim = (f"최근 {n}경기 {last5} · 득점 평균 "
                 f"{avg if avg is not None else '못 쟀다'}"
                 + (f"(보정 {trim})" if trim is not None else "")
                 + (f" · {why_dir}" if why_dir else ""))
        out.append(Variable(
            id=f"{rid}-{'home' if key == ref.home else 'away'}",
            type="recent_pattern", subject=key,
            favors=favors_of("recent_pattern", key, claim, ref),  # type: ignore[arg-type]
            goals=got_dir,                                        # type: ignore[arg-type]
            goals_against=got_against,                            # type: ignore[arg-type]
            target="recent", hardness=("hard" if hard == "hard" else "soft"),
            weight=weight, claim=claim,
            # 🔴 인용은 **어댑터 수치 그대로**다 — 기사가 아니라 구조 자료다
            quote=claim, doc_ids=[], from_rule=rid,
            # ⚠️ 표본이 문턱 미만이면 **근거로 쓰지 않는다**(§7 R7)
            usable_as_basis=(n >= low)))
        if n < low:
            state.note(f"s5 {rid} `{key}` 표본 {n}경기 < {low} — 맥락 전용")
    return out


#: 🔴 **기준에서 얼마나 떨어져야 방향을 매기나**(§3 원문: 0.2). ⚠️ 코드의 수는 이 한 곳
GOAL_GAP = 0.2


def _form_goal_dirs(box: dict, trim, kind: str) -> tuple[str, str, str]:
    """🔴🔴 폼의 **득점·실점 방향** — `(goals, goals_against, 사유 글)`.

    🔴 기준은 `config/goal_baselines.yaml` 의 그 대회 유형 **팀당 몫**이다(실측).
    ⚠️ 기준이 없거나 보정 평균을 못 쟀으면 **`none`** 이다(지어내지 않는다 · #4).
    """
    from app import rules
    share = rules.goal_share(kind)
    if share is None:
        return "none", "none", ""
    got = _side_of_avg(trim, share)
    # 🔴 실점은 **수열에서** 센다 — `goals_against` 가 경기마다 들어 있다
    seq = [g for g in (box.get("sequence") or []) if isinstance(g, dict)]
    vals = [float(g["goals_against"]) for g in seq
            if str(g.get("goals_against")).isdigit()]
    ga_avg = round(sum(vals) / len(vals), 3) if vals else None
    ga = _side_of_avg(ga_avg, share)
    why = (f"기준 팀당 {share}골(대회 {kind}) 대비 득점 "
           f"{_KO_DIR[got]}" + (f" · 실점 평균 {ga_avg}({_KO_DIR[ga]})"
                                if ga_avg is not None else ""))
    return got, ga, why


_KO_DIR = {"up": "많다", "down": "적다", "none": "보통"}


def _side_of_avg(avg, share: float) -> str:
    """🔴 그 평균이 기준 몫보다 **0.2 이상** 낮으면 `down` · 높으면 `up`."""
    try:
        got = float(avg)
    except (TypeError, ValueError):
        return "none"
    if got <= share - GOAL_GAP:
        return "down"
    if got >= share + GOAL_GAP:
        return "up"
    return "none"


def _ir_h2h(rid: str, row: dict, ref: MatchRef, facts: Facts, *,
            state: RunState) -> list[Variable]:
    """IR02 — 맞대결. 🔴 **기록이 가리키는 쪽**이 주체다(동률이면 만들지 않는다)."""
    from app import league
    box = dict(facts.h2h or {})
    got = box.get("summary")
    n = int(box.get("count") or 0)
    if not (isinstance(got, (list, tuple)) and len(got) == 3 and n):
        state.note(f"s5 {rid} — 맞대결 요약이 없다(변수 안 만든다)")
        return []
    w, d, lose = (int(x) for x in got)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **집계 검사**(사용자 지시 2026-10-07 ③) — 승+무+패 = 표본 수여야 한다
    # ══════════════════════════════════════════════════════════════════
    #
    # > 승+무+패 = 표본 수가 아니면 **그 숫자를 쓰지 말고** 블록 1에
    # > *"맞대결 집계 불일치"* 로 적는다.
    #
    # 🔴 원인(실측 2026-10-07 미국–캐나다): `count` 는 **창을 자른** 경기 수(10)인데
    #    `summary` 는 fotmob 의 **전체 전적**(5-4-4 = 13)이다 — 두 창이 한 줄에
    #    섞여 있었다. ⚠️ 그 수로 방향을 정하면 창 밖 경기가 방향을 정하는 것이다.
    if w + d + lose != n:
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **버리지 않는다 — 목록에서 다시 센다**(사용자 지시 2026-10-09 ①)
        # ══════════════════════════════════════════════════════════════
        #
        # > 맞대결 집계 불일치일 때 **버리지 말고**, 경기 페이지의 맞대결 경기
        # > 목록(날짜·스코어)을 **직접 세어 다시 만든다.**
        #
        # 🔴 왜 셀 수 있나 — `matches` 가 **창 안의 줄 전부**를 날짜·스코어와 함께
        #    들고 있다(`fotmob.parse_h2h`). 종전 코드는 그것을 보고도 버렸다.
        # ⚠️ 그래도 **못 세면** 버린다 — 스코어가 없는 자료(야구 일부)가 있다.
        said0 = (f"맞대결 집계 불일치 — 전적 {w}승 {d}무 {lose}패(합 "
                 f"{w + d + lose})인데 표본은 {n}경기다"
                 + (f" · 전체 {box['all_games']}경기" if box.get("all_games")
                    else ""))
        counted = league.h2h_tally(list(box.get("matches") or []), ref.home_name)
        if counted is None:
            said = said0 + " → 🔴 **그 숫자를 쓰지 않는다**(스코어가 없어 셀 수 없다)"
            state.drop(f"{rid}/h2h", DropReason.CONFLICT, said)
            state.note(f"s5 {rid} — {said}")
            return []
        w, d, lose = counted
        n = w + d + lose
        said = (said0 + f" → 🔴 **목록에서 다시 셌다**(창 {n}경기 · "
                f"{ref.home_name} 기준 {w}승 {d}무 {lose}패)")
        state.note(f"s5 {rid} — {said}")
        # 🔴 카드가 같은 수를 찍어야 한다 — 블록 3 이 `facts.h2h` 를 그대로 읽는다
        #    (실측 2026-10-07: s5 가 버렸는데 블록 3 은 옛 수를 계속 찍었다).
        try:
            facts.h2h["recounted"] = {"w": w, "d": d, "l": lose, "n": n,
                                      "basis": ref.home_name, "why": said0}
        except (TypeError, AttributeError):
            state.note(f"s5 {rid} — 다시 센 수를 facts 에 못 실었다(카드가 옛 수를 찍는다)")
    if w == lose:
        state.note(f"s5 {rid} — 맞대결이 {w}승 {d}무 {lose}패로 **동률**이다 "
                   f"(어느 쪽도 아니다 · 변수 안 만든다)")
        return []
    key = ref.home if w > lose else ref.away
    hard, weight = _sample_weight(n)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **맞대결은 한 번만, 팀 이름을 붙여 적는다**(사용자 지시 2026-10-09 ④)
    # ══════════════════════════════════════════════════════════════════
    #
    # > 맞대결은 **한 번만**, 항상 `{홈팀} n승 n무 n패(상대 n승)` 처럼 팀 이름을
    # > 붙여 적는다.
    #
    # 🔴 왜 — 실측 2026-10-09(대전–전북): 같은 전적을 카드가 **두 번** 적었고
    #    기준이 서로 뒤집혀 있었다(대전 쪽 *"1승 4무 5패"* · 전북 쪽 *"5승 4무
    #    1패"*). ⚠️ 수는 맞지만 한 카드에 두 숫자가 보이면 사람이 어느 쪽을
    #    믿을지 모른다. 🔴 그래서 **홈팀 기준 한 줄**로 못 박고 상대 승수를
    #    괄호에 적는다 — 읽는 쪽이 뒤집을 필요가 없다.
    claim = (f"맞대결 {n}경기 {ref.home_name} {w}승 {d}무 {lose}패"
             f"(상대 {lose}승)"
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
    """S03 — 홈 이점. ⚠️ **중립 구장이면 만들지 않는다**(거짓 변수가 된다).

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **표본이 없으면 버리지 않는다 — 기본값으로 soft**(사용자 지시 ①)
    ══════════════════════════════════════════════════════════════════

    > 홈 이점: 표본이 없으면 버리지 말고 **기본값(국가대표/리그 홈 승률)** 으로 soft
    > 변수. `home_field` 가 **근거 불가로 빠지면 E2E 실패.**

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **같은 대회 유형에서만 빌린다**(사용자 지시 2026-10-06(4차) ③)
    ══════════════════════════════════════════════════════════════════

    > 홈 이점 기본값: **같은 대회 유형의 표에서만** 가져온다(국가대표 친선 / 국가대표
    > 공식전 / 각 리그). 그 유형의 표가 없으면 **숫자 없이** *"홈 이점 — 수치 없음"*
    > soft 변수로 두고, 다른 대회 숫자를 **빌려 쓰지 않는다.** 카드에 기본값의
    > **출처 대회**를 적는다.

    🔴 표는 `config/interpret_rules.yaml` 의 `S03.defaults` 가 들고, 열쇠는
       `comp_kind()` 가 만든다(`national_friendly`·`national_official`·`league:…`).
    ⚠️ 실측 2026-10-06: 대표팀 친선 카드에 **MLS 숫자(+16.8%p)** 가 들어가 있었다 —
       리그 홈 이점을 대표팀에 빌린 것이고, 그래서 대표팀 칸은 **비워 뒀다**.
    🔴 그래도 변수는 **만든다**(①) — 수치가 없다는 것도 카드가 말해야 하는 사실이다.
    ⚠️ 쪼갠 표가 생기면 그 수가 기본값을 **덮는다**.
    """
    from app import rules
    neutral, why = rules.neutral_venue(ref.competition)
    if neutral:
        state.note(f"s5 {rid} — 중립 구장이다({why}) · 변수 안 만든다")
        return []
    box = dict(facts.standings or {})
    ha = dict(box.get("home_advantage") or {})
    got = ha.get("win_pct_delta")
    kind_of_comp = comp_kind(ref, facts)
    if got is not None:
        claim = (f"{ref.home_name} 홈 경기 — 홈 승률 +{got}%p"
                 f"({ha.get('home_games', '?')}경기 · 쪼갠 표 · {kind_of_comp})")
    else:
        # 🔴 **같은 대회 유형의 표에서만**(③) — 다른 대회 숫자를 빌리지 않는다
        table = dict(row.get("defaults") or {})
        mine = dict(table.get(kind_of_comp) or {})
        said = mine.get("win_pct_delta")
        if said is None:
            # 🔴🔴 **어느 표가 없는지 적는다** — ⚠️ 실사고 2026-10-10(제노아):
            #    이 줄이 *"대회 유형 `league:SA` 의 표가 없다"* 라고만 적었고,
            #    같은 카드의 λ 줄은 **득점 실측**(`home_share 1.3185`)을 쓰고 있었다.
            #    🔴 없는 것은 **홈 승률(`win_pct_delta`) 표**이고, 득점 쪽 실측은
            #    **있을 수 있다** — 그 둘을 가려 적지 않으면 카드가 서로 반대로 읽힌다.
            mine_goals = dict(rules.goal_baseline(kind_of_comp) or {})
            said_goal = mine_goals.get("home_share")
            extra = (f" · ⚠️ λ 홈 배율은 **득점 실측**을 쓴다"
                     f"(홈 팀 평균 {said_goal:g} · 표본 {mine_goals.get('n', '?')})"
                     if said_goal is not None else "")
            claim = (f"{ref.home_name} 홈 경기 — 홈 **승률** 수치 없음"
                     f"(대회 유형 `{kind_of_comp}` 의 승률 표가 없다 · 다른 대회 "
                     f"숫자를 빌리지 않는다){extra}")
            state.note(f"s5 {rid} — `{kind_of_comp}` **승률** 표가 없다 → "
                       f"수치 없이 soft 변수로 둔다(③){extra}")
        else:
            claim = (f"{ref.home_name} 홈 경기 — 홈 이점 **기본값** +{said}%p"
                     f"(출처 대회 `{kind_of_comp}` · {mine.get('basis', '근거 미상')})")
            state.note(f"s5 {rid} — `{kind_of_comp}` 기본값 +{said}%p 를 썼다")
    return [Variable(
        id=f"{rid}", type="home_field", subject=ref.home,
        favors=favors_of("home_field", ref.home, claim, ref),  # type: ignore[arg-type]
        goals=goals_of("home_field"),                         # type: ignore[arg-type]
        target="home_field", hardness="soft",
        weight=_sample_weight(3)[1], claim=claim, quote=claim, doc_ids=[],
        from_rule=rid,
        # 🔴 **근거로 쓴다**(사용자 지시 ①) — 기본값이라도 홈 이점은 **아는 사실**이다
        usable_as_basis=True)]

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

def _h2h_clash(rec: tuple[int, int, int] | None, facts: Facts) -> str:
    """🔴🔴 **구조 사실과 기사 맞대결이 다르면 충돌**(사용자 지시 2026-10-06(2차) ②).

    > 구조 사실의 h2h 와 숫자가 다르면 **충돌로 처리(공식 > 출처 수 > 등급)**,
    > 카드 블록 1 에 *"충돌: 채택/버림"* 한 줄.

    돌려주는 것은 **버릴 사유 글자**(버리지 않으면 빈 글자). 🔴 순서가 규칙이다:
    어댑터 사실은 **공식**이므로 기사 수치를 버린다 — 기사 쪽이 더 많은 매체가
    말했더라도(출처 수) 공식이 먼저다.
    """
    box = dict(facts.h2h or {})
    got = box.get("summary")
    if rec is None or not (isinstance(got, (list, tuple)) and len(got) == 3):
        return ""
    mine = tuple(int(x) for x in got)
    if mine == rec:
        return ""
    return (f"충돌: **채택 구조 사실**(공식 어댑터 {mine[0]}승 {mine[1]}무 "
            f"{mine[2]}패 · 표본 {box.get('count')}경기) / **버림 기사**"
            f"({rec[0]}승 {rec[1]}무 {rec[2]}패) — 공식 > 출처 수 > 등급")

def _ir_match_type(rid: str, row: dict, ref: MatchRef, facts: Facts, *,
                   state: RunState) -> list[Variable]:
    """S04 — **친선 경기면 코드가 변수 하나를 만든다**(사용자 지시 2026-10-06(2차) ③).

    > 친선 경기(`match_format=friendly`)는 코드가 `match_type` 변수 하나를 만든다:
    > *"친선 — 실험 라인업·교체 다수 가능"*, `favors both`, `goals none`, `soft`.

    ⚠️ 그 경기의 `stakes` 가 거의 전부 버려지는 까닭이 이것이다 — 친선에는 진출·탈락이
       없다. 🔴 그래서 **그 사실 자체**를 변수로 적는다(없는 동기를 지어내지 않는다).
    """
    if facts.match_format != "friendly":
        state.note(f"s5 {rid} — 형식이 `{facts.match_format}` 다(친선 아님) · "
                   f"변수 안 만든다")
        return []
    claim = str(row.get("claim") or "친선 — 실험 라인업·교체 다수 가능")
    return [Variable(
        id=f"{rid}", type="match_type", subject=ref.home,
        favors="both", goals="none", target="match_type", hardness="soft",
        weight=_sample_weight(1)[1], claim=claim, quote=claim, doc_ids=[],
        from_rule=rid,
        # 🔴 **근거로 쓴다** — 이것은 표본이 아니라 **형식**이다(확실히 안다)
        usable_as_basis=True)]

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **축구 해석 규칙 IR01~IR12** — 축구 완성 지시서 §3
# ══════════════════════════════════════════════════════════════════
#
# > 각 규칙은 **§2 의 사실 칸이 있을 때만** 돈다.
#
# 🔴 그래서 규칙마다 `needs` 를 보고, 없으면 **건너뛰고 사유를 남긴다**(#3) —
#    *"규칙이 있는데 안 걸린다"* 를 숨기지 않는다.


def _have(need: str, facts: Facts, ref: MatchRef) -> bool:
    """🔴 그 사실 칸이 **있나**. `recent.streak_unbeaten` 처럼 점으로 들어간다."""
    head, _, tail = str(need).partition(".")
    box = getattr(facts, head, None)
    if not box:
        return False
    if not tail:
        return True
    if head == "xi":
        return any(getattr(v, tail, None) for v in facts.xi.values())
    if isinstance(box, dict):
        for v in box.values():
            row = dict(v) if isinstance(v, dict) else {}
            if row.get(tail) is not None:
                return True
    return False


def _rid_for(rid: str, key: str, ref: MatchRef) -> str:
    """🔴 팀마다 만드는 규칙의 번호 — `IR04-home` 꼴. ⚠️ 같은 id 둘이면 가설이 어느
    쪽을 가리키는지 알 수 없다(불변식 5 가 번호로 센다)."""
    return f"{rid}-{'home' if key == ref.home else 'away'}"


def _ir_var(rid: str, kind: str, row: dict, key: str, claim: str, ref: MatchRef,
            *, usable: bool = True, goals: str = "") -> Variable:
    """🔴 규칙이 만든 변수 한 개 — 방향은 **표의 칸**이 정한다(§3)."""
    fav = str(row.get("favors") or "both")
    side = {"subject": ("home" if key == ref.home else "away"),
            "opponent": ("away" if key == ref.home else "home")}.get(fav, fav)
    got_goals = goals or str(row.get("goals") or "none")
    return Variable(
        id=rid, type=kind, subject=key,
        favors=(side if side in ("home", "away", "both") else "both"),  # type: ignore[arg-type]
        goals=(got_goals if got_goals in ("up", "down", "none") else "none"),  # type: ignore[arg-type]
        target=f"{kind}:{rid}", hardness="soft",
        weight=_sample_weight(5)[1], claim=claim, quote=claim, doc_ids=[],
        from_rule=rid, usable_as_basis=usable)


#: 🔴 5백 포메이션 — ⚠️ 글자로 센다(`5-3-2`·`5-4-1`·`3-5-2` 의 수비 5)
def _is_five_back(formation: object) -> bool:
    said = str(formation or "").strip()
    return said.startswith("5-") or said in ("3-5-2",)


def _ir_soccer(rid: str, row: dict, ref: MatchRef, facts: Facts, *,
               state: RunState) -> list[Variable]:
    """🔴🔴 축구 해석 규칙 한 줄 — **사실이 있으면 변수, 없으면 사유**(§3)."""
    kind = str(row.get("type") or "")
    needs = [str(x) for x in (row.get("needs") or [])]
    gone = [n for n in needs if not _have(n, facts, ref)]
    if gone:
        state.note(f"s5 {rid}({kind}) **건너뜀** — 사실 칸이 없다: {gone}")
        return []
    out: list[Variable] = []
    if rid == "IR01":                       # 5백
        for key, xi in facts.xi.items():
            if not _is_five_back(xi.formation):
                continue
            out.append(_ir_var(_rid_for(rid, key, ref), kind, row, key,
                               f"{_name(ref, key)} {xi.formation} — "
                               f"5백으로 내려앉는 운영", ref, goals="down"))
        if not out:
            state.note(f"s5 {rid} — 5백이 아니다"
                       f"({[v.formation for v in facts.xi.values()]})")
    elif rid in ("IR02", "IR03"):           # 주전 이탈 · 복귀
        out += _ir_rotation(rid, kind, row, ref, facts, state=state)
    elif rid == "IR04":                     # 이상치 보정 — **상대가 하위권일 때만**
        for key, raw in facts.recent.items():
            box = dict(raw) if isinstance(raw, dict) else {}
            avg, trim = box.get("recent_scored_avg"), box.get("recent_trimmed_avg")
            if avg is None or trim is None or float(avg) == float(trim):
                continue
            low, said = _outlier_weak(box, row, state=state)
            if not low:
                state.note(f"s5 {rid} `{key}` 건너뜀 — {said}")
                continue
            out.append(_ir_var(_rid_for(rid, key, ref), kind, row, key,
                               f"{_name(ref, key)} 득점 평균 {avg} → 보정 {trim}"
                               f"(이상치 한 경기를 뺐다 · {said})", ref))
    elif rid == "IR05":                     # 확정 비대칭(동기)
        out += _ir_stakes(rid, kind, row, ref, facts, state=state)
    elif rid == "IR06":                     # 로테이션 패배 할인
        state.note(f"s5 {rid} — 직전 경기 선발을 받아야 돈다(§2 `last_xi`)")
    elif rid == "IR07":                     # 단판·1차전
        from app import scenarios
        if facts.match_format in scenarios.draw_formats():
            out.append(_ir_var(rid, kind, row, ref.home,
                               f"형식 {facts.match_format} — 90분 무승부가 갈래다",
                               ref))
        else:
            state.note(f"s5 {rid} — 형식이 `{facts.match_format}` 다"
                       f"(단판·1차전 아님)")
    elif rid == "IR11":                     # 일정 피로 — 7차 §6 로 문턱이 바뀌었다
        out += _ir_fatigue(rid, kind, row, ref, facts, state=state)
    elif rid == "IR12":                     # 연승·연패
        for key, raw in facts.recent.items():
            box = dict(raw) if isinstance(raw, dict) else {}
            said = ""
            if int(box.get("streak_unbeaten") or 0) >= 3:
                said = f"무패 {box['streak_unbeaten']}경기"
            elif int(box.get("streak_winless") or 0) >= 3:
                said = f"무승 {box['streak_winless']}경기"
            if said:
                out.append(_ir_var(_rid_for(rid, key, ref), kind, row, key,
                                   f"{_name(ref, key)} {said}", ref))
        if not out:
            state.note(f"s5 {rid} — 3경기 이상 연속이 없다")
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **연패 = 간절함**(사용자 지시 2026-10-11) — **가설 근거로만**
        # ══════════════════════════════════════════════════════════════
        #
        #  > 연패한 팀일수록 승리에 더 간절하다도 **가설에 추가해라**.
        #
        #  🔴 유형은 `stakes` 다 — 배치표가 그 유형을 **`V2`·`hypo`** 로만 보낸다
        #     (확률에 닿지 않는다 · C7). ⚠️ 그래서 이 변수는 λ 를 **안 움직인다**.
        #  🔴 수는 `facts.recent[*]["streak_losing"]`(그 한 경기 목록에서 센 것)
        #     하나다 — 여기서 다시 세지 않는다(사본 금지).
        out += _ir_desperate(rid, row, ref, facts, state=state)
    return out


#: 🔴 **연패 간절함**의 문턱(경기 수). ⚠️ 문턱 아래면 변수를 만들지 않는다.
DESPERATE_MIN = 2


def _ir_desperate(rid: str, row: dict, ref: MatchRef, facts: Facts, *,
                  state: RunState) -> list[Variable]:
    """🔴🔴 **연패한 팀일수록 승리에 더 간절하다**(사용자 지시 2026-10-11).

    🔴 유형 `stakes` — 배치표가 **`V2`·`hypo`** 로만 보낸다(확률 금지 · C7).
    ⚠️ 이것은 **해석**이다(연패 → 간절함). 그래서 `hardness` 는 soft 이고
       근거 가능 여부는 배치표가 정한다 — 숫자(연패 수)는 사실이고 그 해석을
       가설이 쓴다.
    """
    out: list[Variable] = []
    for key, raw in (facts.recent or {}).items():
        box = dict(raw) if isinstance(raw, dict) else {}
        n = int(box.get("streak_losing") or 0)
        if n < DESPERATE_MIN:
            continue
        out.append(_ir_var(
            _rid_for(f"{rid}D", key, ref), "stakes", row, key,
            f"{_name(ref, key)} **{n}연패** — 승리에 더 간절하다"
            f"(연패가 길수록 간절함이 크다 · 해석이고 확률에 닿지 않는다)",
            ref))
    if not out:
        state.note(f"s5 {rid}D — {DESPERATE_MIN}연패 이상인 팀이 없다")
    return out


def _name(ref: MatchRef, key: str) -> str:
    """🔴 카드에 **보일 이름** — 열쇠는 사람이 못 읽는다(§8-1 의 표시 예외)."""
    return ref.home_name if key == ref.home else ref.away_name


def _ir_rotation(rid: str, kind: str, row: dict, ref: MatchRef, facts: Facts, *,
                 state: RunState) -> list[Variable]:
    """IR02·IR03 — **직전 선발 ↔ 오늘 명단**을 견준다(§2 `last_xi` 가 재료다).

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **오늘 XI 가 있을 때만 돈다**(사용자 지시 2026-10-06(4차) ②)
    ══════════════════════════════════════════════════════════════════

    > IR02: 오늘 XI 상태가 `confirmed` 또는 `predicted` 일 때만 돈다. `none` 이면
    > 건너뛰고 사유 *"오늘 XI 없음"*. 비교 대상도 XI 가 아니라 **소집 명단**으로
    > 바꿀 수 있으면 그쪽(**명단에 없음 = 결장, XI 에 없음 = 벤치**).

    ⚠️ 실측 2026-10-06: 라인업이 **없는** 경기에서 IR02 가 *"직전 선발 Song·Seol·Lee
       가 오늘 명단에 없다"* 를 냈다 — 오늘 명단 자체가 없었으니 **전원이 없다**고
       적은 것이고, 그것은 거짓이다.
    """
    out: list[Variable] = []
    for key, last in facts.last_xi.items():
        now = facts.xi.get(key)
        if now is None or now.state == "none":
            state.note(f"s5 {rid} `{key}` 건너뜀 — **오늘 XI 없음**"
                       f"(상태 {getattr(now, 'state', '없음')})")
            continue
        if not last.players:
            continue
        # 🔴 **명단이 있으면 명단으로** 센다 — 그러면 `결장`과 `벤치`가 갈린다
        pool = [str(x) for x in (facts.squad.get(key) or [])]
        where = "소집 명단" if pool else f"{now.state} XI"
        if not pool:
            pool = list(now.players)
        gone = [n for n in last.players if not _in(n, pool)]
        back = [m.name for m in facts.missing.get(key, [])
                if _in(m.name, pool)]
        if gone:
            state.note(f"s5 {rid} `{key}` — {where} 기준으로 센다"
                       f"({'명단에 없음 = 결장' if where == '소집 명단' else 'XI 에 없음 = 벤치일 수도 있다'})")
        if rid == "IR02" and gone:
            said = ("명단에 없다(결장)" if where == "소집 명단"
                    else f"{now.state} XI 에 없다(벤치일 수도 있다)")
            out.append(_ir_var(_rid_for(rid, key, ref), kind, row, key,
                               f"{_name(ref, key)} 직전 선발 "
                               f"{', '.join(gone[:3])} 가 오늘 {said}", ref))
        if rid == "IR03" and back:
            out.append(_ir_var(_rid_for(rid, key, ref), kind, row, key,
                               f"{_name(ref, key)} {', '.join(back[:3])} 복귀",
                               ref))
    if not out:
        state.note(f"s5 {rid} — 직전 선발과 오늘 명단을 견줄 자료가 없다")
    return out


def _ir_stakes(rid: str, kind: str, row: dict, ref: MatchRef, facts: Facts, *,
               state: RunState) -> list[Variable]:
    """IR05 — **동기 비대칭**. 🔴 순위표에서 **읽을 수 있는 것만** 적는다."""
    box = dict(facts.standings or {})
    rows = box.get("table") if isinstance(box.get("table"), list) else None
    if not rows:
        state.note(f"s5 {rid} — 순위표에 표(`table`)가 없다(동기를 못 센다)")
        return []
    out: list[Variable] = []
    for key in (ref.home, ref.away):
        name = _name(ref, key)
        mine = next((r for r in rows
                     if isinstance(r, dict)
                     and norm(str(r.get("name") or "")) == norm(name)), None)
        if not mine:
            continue
        rank, pts = mine.get("idx") or mine.get("rank"), mine.get("pts")
        if rank is None:
            continue
        out.append(_ir_var(_rid_for(rid, key, ref), kind, row, key,
                           f"{name} 순위 {rank}위"
                           + (f" · 승점 {pts}" if pts is not None else ""), ref))
    if not out:
        state.note(f"s5 {rid} — 순위표에서 두 팀을 못 찾았다")
    return out

def _outlier_weak(box: dict, row: dict, *, state: RunState) -> tuple[bool, str]:
    """🔴🔴 **그 이상치 경기 상대가 하위권인가**(사용자 지시 2026-10-06(3차) ②).

    > IR04 조건에 *"그 이상치 경기 상대가 하위권(랭킹·순위 하위 25%)"* 을 추가.
    > **상대 정보가 없으면 발동하지 않는다.**

    🔴 `(참/거짓, 사유)`. ⚠️ 상대 순위를 **모르면 거짓**이다 — 그것이 지시의 뜻이다
       (모르는 것을 하위권으로 보면 모든 이상치가 회귀가 된다).
    🔴 이상치 경기는 `trimmed_why` 가 말한다(*"3골 경기 하나를 뺐다"*) — 그 경기를
       `sequence` 에서 **득점이 가장 많은 한 경기**로 찾는다(그 함수가 그렇게 뺀다).
    """
    pct = float(row.get("bottom_pct") or 0)
    seq = [x for x in (box.get("sequence") or []) if isinstance(x, dict)]
    if not seq:
        return False, "최근 경기 목록이 없다(상대를 모른다)"
    best = max(seq, key=lambda x: int(x.get("goals_for") or 0))
    rank = best.get("opponent_rank")
    total = best.get("opponent_rank_total") or box.get("league_teams")
    who = str(best.get("opponent") or "?")
    if rank is None or not total:
        return False, (f"이상치 경기 상대 `{who}` 의 순위를 모른다 — "
                       f"발동하지 않는다(지시 ②)")
    cut = float(total) * (1 - pct / 100.0)
    if float(rank) >= cut:
        return True, f"이상치 상대 `{who}` {rank}/{total}위 — 하위 {pct:.0f}%"
    return False, (f"이상치 상대 `{who}` {rank}/{total}위 — 하위 {pct:.0f}% 가 아니다")

def _in_missing(name: str, key: object, facts) -> bool:
    """🔴 그 선수가 **구조 결장 명단**(fotmob `missing_of`)에 있나.

    🔴 이름 대조는 `s5_verify._in` 하나가 한다(사본 금지) — 한 낱말 이름은 성으로만
       맞춘다(실사고 2026-10-11 의 그 규칙).
    """
    rows = dict(getattr(facts, "missing", None) or {}).get(str(key)) or []
    pool = [str(getattr(m, "name", "") or "") for m in rows]
    return _in(str(name), pool)


def _xi_clash(target: str, subject: str, facts: Facts) -> str:
    """🔴 그 선수가 **XI 에 들어 있나** — 들어 있으면 충돌 사유 글자(아니면 빈 글자).

    ⚠️ 비교는 정규화해서 한다(`Kim Min-jae` ↔ `김민재` 는 못 맞춘다 — 그때는 빈 글자다).
    """
    xi = facts.xi.get(subject)
    if xi is None or xi.state == "none":
        return ""
    if not str(target or "").strip():
        return ""
    for name in [*xi.players, *[p.name for p in xi.lineup]]:
        # ⚠️ 이름 비교는 `same_person` **하나**다(#1) — 글자 포함으로 묶지 않는다
        if same_person(target, name):
            return (f"충돌: 기사가 **결장**이라 한 `{target}` 가 "
                    f"{xi.state} XI 에 **있다** → 그 변수를 soft 로 내린다"
                    f"(무엇이 맞는지는 킥오프가 말한다)")
    return ""

#: 🔴 **개인 상태 유형** — 그 선수가 소집 명단에 있으면 경기 연결로 **인정**한다(①-b 예외)
PERSONAL_KINDS = (*ABSENCE_KINDS, "individual_title", "returning",
                  "lineup_value")


def _squash(said: str) -> str:
    """🔴 글자만 남긴다 — `Kim Min-jae` → `kimminjae`(붙여 쓴 표기를 맞추려고)."""
    return re.sub(r"[^0-9a-z가-힣ぁ-んァ-ヶ一-龥]", "", said)


def _parts(said: str) -> list[str]:
    """🔴 이름을 **낱말로** 쪼갠다 — 공백·쉼표·점·하이픈·따옴표."""
    return [t for t in re.split(r"[\s,.\-'\u00b7]+", said) if t]


def same_person(a: str, b: str) -> bool:
    """🔴🔴 **두 이름이 같은 사람인가** — 비교는 **여기 한 곳**이다(사본 금지).

    ⚠️ 매체와 명단이 같은 선수를 다르게 적는다(실측): `Gilberto Mora Ortega` /
       `G. Mora` / `Mora, Gilberto` / `Ødegaard` ↔ `Odegaard`.
    🔴 `norm` 이 NFKC·합자·발음기호·대소문자를 이미 걷는다 — 여기서 더하는 것은
       **낱말 단위** 비교다:
         ① 글자 포함(한쪽이 다른 쪽을 품는다 — `Mora` ⊂ `Gilberto Mora`)
         ② 낱말 집합이 같다(**성·이름 순서 무관** — `Mora Gilberto` = `Gilberto Mora`)
         ③ 머리글자 + 성(`G. Mora` = `Gilberto Mora`)
    🔴 ③ 은 **성이 같고** 머리글자가 같을 때만이다 — 성만 같은 다른 선수를 묶지
       않는다. ⚠️ 그래도 동명이인은 남는다 — 그 경우는 `team_ambiguous` 로 센다.
    """
    x, y = norm(a), norm(b)
    if not x or not y:
        return False
    if x == y:
        return True
    # ⚠️ **글자 포함으로 묶지 않는다** — `Mora` 가 `Morales` 에 들어 있다(실측
    #    2026-10-07: 그래서 멕시코 선수가 칠레 선수와 같은 사람이 됐다).
    #    🔴 비교는 **낱말 단위**다.
    if _squash(x) == _squash(y):            # `Kim Minjae` = `Kim Min-jae`
        return True
    xs, ys = _parts(x), _parts(y)
    if not xs or not ys:
        return False
    if set(xs) == set(ys):                  # 성·이름 **순서 무관**
        return True
    short, long = (xs, ys) if len(xs) <= len(ys) else (ys, xs)
    if set(short) <= set(long):             # `Mora` ⊂ `Gilberto Mora`
        return True
    # ③ 머리글자 + 성 — 짧은 쪽이 `G Mora` 꼴일 때만
    if len(short) == 2 and len(short[0]) == 1 and short[-1] == long[-1]:
        return short[0] == long[0][:1]
    return False


def roster_of(key: str, facts: Facts) -> list[str]:
    """🔴 그 팀의 **이름 풀** — 예상/확정 XI·벤치·결장 명단·소집 명단·평소 XI.

    🔴 `s2` 가 받은 칸을 **전부** 본다(지시 2: 어느 칸에 있어도 그 팀 선수다).
    ⚠️ 직전 5경기 선발(`past_xi`)도 넣는다 — 소집 명단이 없는 대회가 있다.
    """
    pool: list[str] = list(facts.squad.get(key) or [])
    xi = facts.xi.get(key)
    if xi is not None:
        pool += [*xi.players, *xi.bench, *[p.name for p in xi.lineup]]
    pool += [m.name for m in (facts.missing.get(key) or [])]
    for old in (facts.past_xi.get(key) or []):
        pool += [*old.players, *old.bench, *[p.name for p in old.lineup]]
    return [x for x in pool if str(x).strip()]


def team_of_player(target: str, ref: MatchRef, facts: Facts,
                   doc: Doc | None = None) -> tuple[str, str, str]:
    """🔴🔴 **그 선수는 어느 팀인가 — 코드가 대조한다.** `(팀 열쇠, 길, 사유)`.

    🔴 열쇠가 `""` 면 **못 가렸다**는 뜻이고, `길` 이 `ambiguous`·`unknown` 중
       어느 쪽인지 말한다. ⚠️ **LLM 에게 다시 묻지 않는다**(사용자 지시 금지 ①).

    순서:
      ① 두 팀 **명단**에서 찾는다 → 한 팀에서만 나오면 그 팀이다.
      ② 두 팀 다 나오면 `ambiguous`(동명이인) — 방향을 정할 수 없다.
      ③ 둘 다 없으면 **기사 문장**을 본다: 선수 이름이 든 문장과 그 앞뒤 한 문장에
         팀 이름이 한쪽만 나오면 그 팀이다.
      ④ 그래도 모르면 `unknown`.
    """
    said = str(target or "").strip()
    if not said:
        return "", "unknown", "대상(선수 이름)이 비었다"
    hit = [k for k in (ref.home, ref.away)
           if any(same_person(said, n) for n in roster_of(k, facts))]
    if len(hit) == 1:
        return hit[0], "roster", f"`{said}` 를 그 팀 명단에서 찾았다"
    if len(hit) == 2:
        return "", "ambiguous", f"`{said}` 가 **두 팀 명단에** 다 있다(동명이인)"
    if doc is None:
        return "", "unknown", f"`{said}` 가 두 팀 명단에 없다(기사도 못 봤다)"
    got, why = _team_in_text(said, doc, ref)
    if got:
        return got, "text", why
    return "", "unknown", why


def _team_in_text(target: str, doc: Doc, ref: MatchRef) -> tuple[str, str]:
    """🔴 기사에서 그 선수 이름 **앞뒤 한 문장 안**에 팀 이름이 한쪽만 나오나."""
    from app.core.stages.s3_docs import names_of
    sents = [x for x in re.split(r"(?<=[.!?。])\s+|\n+",
                                 f"{doc.title}. {doc.body}") if x.strip()]
    low = norm(target)
    where = [i for i, x in enumerate(sents) if low and low in norm(x)]
    if not where:
        return "", f"`{target}` 가 본문에 없다 — 팀을 가릴 수 없다"
    home, away = names_of(ref)
    seen: set[str] = set()
    for i in where:
        window = " ".join(sents[max(0, i - 1):i + 2])
        said = norm(window)
        for key, names in ((ref.home, home), (ref.away, away)):
            if any(len(str(x)) >= 3 and norm(str(x)) in said for x in names):
                seen.add(key)
    if len(seen) == 1:
        got = seen.pop()
        return got, f"`{target}` 문장 앞뒤에 그 팀 이름만 나온다"
    if len(seen) == 2:
        return "", (f"`{target}` 문장에 **두 팀 이름이 다** 나온다 — 소속을 "
                    f"가릴 수 없다")
    return "", f"`{target}` 문장에 팀 이름이 없다"


def in_squad(target: str, subject: str, facts: Facts) -> bool:
    """🔴 그 선수가 **이번 소집 명단**에 있나(①-b 예외 · ② 가 같은 표를 쓴다).

    ⚠️ 이름 비교는 `same_person` 하나다 — 여기 다시 적지 않는다(#1).
    """
    return any(same_person(target, n) for n in roster_of(subject, facts))


def match_link_ok(c: VarCandidate, doc: Doc, ref: MatchRef,
                  facts: Facts) -> tuple[bool, str]:
    """🔴🔴 **이 경기와 이어지나**(사용자 지시 2026-10-06(4차) ①-b). `(통과, 사유)`.

    > 코드가 그 근거가 문단에 **실제로 있는지** 확인하고, 없으면 버린다(`off_match`).
    > 예외: 선수 개인 상태(부상·피로·기록 도전)는 그 선수가 **이번 소집 명단에 있으면**
    > 경기 연결로 인정.

    🔴 모델이 적은 `match_link` 를 **본문에 대고** 맞춰 본다(인용 검사와 같은 방법) —
       모델이 지어낸 근거는 통과하지 못한다.
    ⚠️ 그리고 그 근거가 **이 경기를 가리키는지** 센다: 상대팀 이름·경기장·킥오프 날짜
       중 하나와 겹쳐야 한다. 🔴 아무 글자나 따오는 것을 막는 자리다.
    """
    said = str(c.match_link or "").strip()
    body = norm(f"{doc.title} {doc.body}")
    # ── 예외: 개인 상태 + 소집 명단
    if c.type in PERSONAL_KINDS and in_squad(str(c.target or ""), c.subject,
                                             facts):
        return True, f"개인 상태 · `{c.target}` 가 소집 명단에 있다"
    if not said:
        return False, "🔴 `match_link` 가 비었다 — 이 경기와 이어지는 근거가 없다"
    if norm(said) not in body:
        return False, (f"🔴 `match_link` 가 본문에 없다(지어낸 근거다): "
                       f"{said[:50]!r}")
    # ── 그 근거가 **이 경기**를 가리키나
    low = norm(said)
    marks: list[str] = []
    from app.core.stages.s3_docs import names_of
    home, away = names_of(ref)
    for name in [*home, *away]:
        got = norm(name)
        if len(got) >= 3 and got in low:
            marks.append(str(name))
    if ref.venue and norm(ref.venue) in low:
        marks.append(ref.venue)
    for fmt in ("%Y-%m-%d", "%m-%d", "%d/%m", "%m/%d"):
        if ref.kickoff_utc.strftime(fmt).lower() in low:
            marks.append(ref.kickoff_utc.strftime(fmt))
    if not marks:
        return False, (f"🔴 `match_link` 가 이 경기를 가리키지 않는다"
                       f"(상대팀·경기장·날짜가 없다): {said[:50]!r}")
    return True, f"경기 연결 ✅ {marks[:2]}"

def _in(name: str, pool: list[str]) -> bool:
    """🔴 그 이름이 목록에 있나 — 정규화해서 본다(표기가 갈려도 같은 사람이다).

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **한 낱말 이름은 성으로만 맞춘다** — 실사고 2026-10-11(상파울루)
    ══════════════════════════════════════════════════════════════════

    카드가 `Rafael — 부상 · 복귀 Doubtful`(GK)이라고 적고, 동시에
    `IR03-home São Paulo FC **Rafael 복귀**` 를 **축0·축2 근거로** 썼다.
    🔴 명단에 있던 사람은 **`Rafael Tolói`**(수비수, 오늘 선발)였다 — **다른
       사람**이다. 품는 일치(`said in norm(x)`)가 *이름(given name)* 에서 맞아
       버렸다.
    🔴 그래서 한쪽이 **한 낱말**이면(브라질 선수는 mononym 이 흔하다) 상대의
       **마지막 낱말(성)** 과 같을 때만 같은 사람으로 본다 —
       `Griezmann` ↔ `Antoine Griezmann` 은 맞고, `Rafael` ↔ `Rafael Tolói` 는
       아니다. ⚠️ 두 이름이 **둘 다 여러 낱말**이면 종전처럼 품는 일치를 쓴다
       (표기 차이가 거기서 나온다 — `Stephan El Shaarawy`).
    """
    said = norm(name)
    if not said:
        return False
    for one in pool:
        if not one:
            continue
        got = norm(one)
        if not got or not (said in got or got in said):
            continue
        a, b = str(name).split(), str(one).split()
        if (len(a) == 1) != (len(b) == 1):
            # 🔴 한쪽만 한 낱말 — **성**이 같아야 한다
            lone = norm(a[0] if len(a) == 1 else b[0])
            many = b if len(a) == 1 else a
            if norm(many[-1]) != lone:
                continue
        return True
    return False

def comp_kind(ref: MatchRef, facts: Facts) -> str:
    """🔴🔴 **대회 유형**(사용자 지시 2026-10-06(4차) ③) — 홈 이점 표의 열쇠다.

    돌려주는 것: `national_friendly` · `national_official` · `league:<이름>`.

    🔴 대표팀인지는 **이름표가 안다** — 열쇠가 나라 대표팀인지 구단인지. ⚠️ 그것을
       못 가리면 대회명으로 떨어진다(친선이면 친선, 아니면 공식전).
    """
    said = str(ref.competition or "")
    friendly = facts.match_format == "friendly" or "friendl" in said.lower() \
        or "친선" in said
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **대회 판정은 한 곳이다**(사용자 지시 2026-10-09(4차) §1)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 `app/core/competition.py` 가 ESPN 슬러그·fotmob id·football-data 코드·
    #     사람 이름을 **하나의 키**로 바꾼다. ⚠️ 여기서 다시 판정하지 않는다 —
    #     두 곳이 판정하면 한 곳만 고쳐지고 다른 곳이 조용히 틀린다.
    #  🔴 **못 알아보면 빈 글자**다 — 호출부가 크게 실패한다(§2). 종전에는
    #     `league:jpn.1` 처럼 **받은 글자를 그대로 키로 썼고**, 그래서 기준·홈
    #     이점·리그 평균이 조용히 비었다(실사고 2026-10-09 가시마–감바).
    from app.core import competition as _comp
    #  🔴 **번호가 있으면 번호가 글자를 이긴다** — 대회 이름은 나라를 넘어
    #     겹친다(실사고 2026-10-10: `Super League` 가 스위스·인도네시아 둘이다).
    got, _why = _comp.kind_of(competition=said,
                              league_id=(str(facts.league_id or "") or None),
                              friendly=friendly, national=_is_national(ref))
    return got


def _is_national(ref: MatchRef) -> bool:
    """🔴 대표팀 경기인가 — **이름표에 나라 코드가 있나**(`iso:KR`·`fa:SCO`).

    ⚠️ 나라 이름 목록을 여기 적지 않는다(사본 금지 · #1). 🔴 `_from_cldr` 이
       대표팀 이름표에 `iso:KR` 을, `_from_nations` 이 `fa:SCO` 를 **이미 붙여
       뒀다** — 구단 이름표에는 그 코드가 없다. 그래서 코드의 유무가 답이다.
    ⚠️ 이름표를 못 읽으면 **대표팀이 아니라고 본다** — 그 쪽이 조용하다(리그
       열쇠로 떨어지고, 리그 표가 비어 있으면 `수치 없음` 이 된다).
    """
    from app import teamref
    try:
        reg = teamref.registry()
    except Exception:                                       # noqa: BLE001
        return False
    for key in (ref.home, ref.away):
        box = reg.teams.get(str(key))
        if box is None:
            continue
        for names in box.names.values():
            for nm in names:
                if teamref.is_code(nm) and nm.split(":", 1)[0] in ("iso", "fa"):
                    return True
    return False


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **IR11 일정 피로**(사용자 지시 2026-10-06(7차) §6 로 문턱이 바뀌었다)
# ══════════════════════════════════════════════════════════════════
#
# > *"직전 경기 후 **4일 이내** + (**시차 3시간 이상** 또는 **이동 3,000km 이상**)"*
# > 으로 바꾼다. 직전 경기 장소는 2단계에서 받은 직전 경기 페이지에서.
# > (페로: 10/2 토르스하운 → 10/6 아스타나, **시차 4시간**)
#
#: 🔴 문턱 — 표가 아니라 **지시서가 못 박은 수**다(여기 적고 주석으로 근거를 남긴다)
FATIGUE_DAYS = 4
FATIGUE_TZ_HOURS = 3
FATIGUE_KM = 3000


def _ir_fatigue(rid: str, kind: str, row: dict, ref: MatchRef, facts: Facts, *,
                state: RunState) -> list[Variable]:
    """🔴 §6 — 직전 경기 후 4일 이내 **그리고** (시차 3시간+ 또는 이동 3,000km+).

    🔴 재료: `facts.schedule[팀]["last_match"]`(날짜)와 `last_venue`·`last_country`.
    ⚠️ 하나라도 없으면 **안 돈다** — 사유를 이름으로 남긴다(#3 조용한 0 금지).
    """
    out: list[Variable] = []
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **조건은 OR 이다**(사용자 지시 2026-10-07 ①) — 내가 지운 것을 되살린다
    # ══════════════════════════════════════════════════════════════════
    #
    # > (직전 경기 후 4일 이내 + 시차 3시간 이상 **또는** 이동 3,000km 이상)
    # > **OR** (최근 8일 안에 이번이 **3번째** 경기).
    #
    # ⚠️ 7차 §6 에서 문턱을 고칠 때 내가 **두 번째 조건을 지웠다**(종전 조항은
    #    *"8일에 3경기"* 였다). 🔴 실측 2026-10-07 미국: 09-26·09-30·10-04 로
    #    8일 안에 두 경기를 치르고 이번이 **세 번째**인데 IR11 이 안 돌았다.
    for key, said in _three_in_window(ref, facts).items():
        out.append(_ir_var(_rid_for(rid, key, ref), kind, row, key,
                           f"{_name(ref, key)} 일정 과부하 — {said}", ref))
        state.note(f"s5 {rid} `{key}` **발동**(8일 3경기) — {said}")
    done = {v.subject for v in out}
    box = dict(facts.schedule or {})
    if not box:
        if not out:
            state.note(f"s5 {rid} — 일정 칸(`schedule`)이 비었다 · 안 돈다")
        return out
    for key, raw in box.items():
        if key in done:
            continue            # 🔴 이미 8일 3경기로 걸렸다 — 두 번 세지 않는다
        said = dict(raw) if isinstance(raw, dict) else {}
        days = _days_since(said.get("last_match"), ref.kickoff_utc)
        if days is None:
            state.note(f"s5 {rid} `{key}` — 직전 경기 날짜가 없다")
            continue
        if days > FATIGUE_DAYS:
            state.note(f"s5 {rid} `{key}` — 직전 경기 {days}일 전"
                       f"(문턱 {FATIGUE_DAYS}일) · 안 돈다")
            continue
        tz, km, why = _travel(said, ref, key)
        if tz is None and km is None:
            state.note(f"s5 {rid} `{key}` — 직전 경기 **장소를 모른다**({why})")
            continue
        hit = ((tz is not None and abs(tz) >= FATIGUE_TZ_HOURS)
               or (km is not None and km >= FATIGUE_KM))
        if not hit:
            state.note(f"s5 {rid} `{key}` — {days}일 쉬었고 이동 부담이 문턱 아래다"
                       f"({why})")
            continue
        out.append(_ir_var(_rid_for(rid, key, ref), kind, row, key,
                           f"{_name(ref, key)} 일정 피로 — 직전 경기 {days}일 전 · "
                           f"{why}", ref))
        state.note(f"s5 {rid} `{key}` **발동** — {days}일 · {why}")
    return out


def _days_since(said: object, kickoff) -> int | None:
    """🔴 직전 경기와 이 경기의 **날짜 차**(일). 못 읽으면 `None`."""
    from datetime import date, datetime
    raw = str(said or "").strip()[:10]
    if not raw:
        return None
    try:
        then = date.fromisoformat(raw)
    except ValueError:
        return None
    now = kickoff.date() if isinstance(kickoff, datetime) else kickoff
    return (now - then).days


def _travel(said: dict, ref: MatchRef, key: str) -> tuple[float | None,
                                                          float | None, str]:
    """🔴 직전 경기 장소 → **시차(시간)·거리(km)**. 못 구하면 `(None, None, 사유)`.

    🔴 좌표는 경기 페이지가 준다(`eventJSONLD.location.latitude/longitude` ·
       실측 2026-10-06). 시차는 두 좌표의 **시간대**로 센다(`timezonefinder` 가 없으면
       경도 15°=1시간으로 어림한다 — 그 어림을 사유에 적는다).
    ⚠️ 어림한 값을 **잰 값처럼** 적지 않는다.
    """
    import math

    lat1, lon1 = said.get("last_lat"), said.get("last_lon")
    lat2, lon2 = said.get("lat"), said.get("lon")
    if None in (lat1, lon1, lat2, lon2):
        return None, None, "직전 경기 좌표가 없다"
    lat1, lon1, lat2, lon2 = (float(lat1), float(lon1),  # type: ignore[arg-type]
                              float(lat2), float(lon2))  # type: ignore[arg-type]
    # 🔴 대권 거리(하버사인) — 지구 반지름 6371km
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    km = 2 * 6371 * math.asin(min(1.0, math.sqrt(a)))
    tz = (lon2 - lon1) / 15.0            # ⚠️ 경도 어림(시간대 표가 없다)
    return (round(tz, 1), round(km, 0),
            f"시차 약 {abs(tz):.1f}시간(경도 어림) · 이동 {km:,.0f}km")


#: 🔴 두 번째 조건의 창(일)과 경기 수 — 지시서 원문 *"최근 8일 안에 이번이 3번째"*
FATIGUE_WINDOW_DAYS = 8
FATIGUE_WINDOW_GAMES = 3


def _three_in_window(ref: MatchRef, facts: Facts) -> dict[str, str]:
    """🔴 **8일 안에 이번이 3번째 경기**인 팀들. `{열쇠: 사유}` — 아니면 빈 표.

    🔴 재료는 `facts.recent[팀]["sequence"]` 의 **날짜**다(폼 표가 이미 들고 있다).
    ⚠️ 날짜를 못 읽은 줄은 **세지 않는다**(0 으로 때우지 않는다 · #3).
    """
    from datetime import date

    out: dict[str, str] = {}
    when = ref.kickoff_utc.date()
    for key, raw in (facts.recent or {}).items():
        box = dict(raw) if isinstance(raw, dict) else {}
        days: list[int] = []
        for row in (box.get("sequence") or []):
            said = str(dict(row).get("date") or "")[:10]
            if not said:
                continue
            try:
                then = date.fromisoformat(said)
            except ValueError:
                continue
            gap = (when - then).days
            if 0 <= gap <= FATIGUE_WINDOW_DAYS:
                days.append(gap)
        # 🔴 **이번 경기를 포함해** 센다 — 앞선 경기가 (3-1)개면 이번이 3번째다
        if len(days) >= FATIGUE_WINDOW_GAMES - 1:
            out[str(key)] = (f"{FATIGUE_WINDOW_DAYS}일 안에 이번이 "
                             f"{len(days) + 1}번째 경기"
                             f"(직전 {sorted(days)}일 전)")
    return out


#: 🔴🔴 §6 — **선발 비율 문턱**(사용자가 적은 30%)
STARTER_SHARE = 0.30
#: 🔴 "선발에서 빠졌다"를 말하는 꼴 — ⚠️ `결장`·`부상`·`징계` 는 **여기 없다**
#   (그것들은 선발 비율과 무관하게 결장이다).
BENCH_SAID = (
    "선발 제외", "선발에서 제외", "선발 명단 제외", "라인업 제외", "엔트리 제외",
    "벤치", "교체 명단", "dropped to the bench", "benched", "left out of the",
    "not in the starting", "ベンチスタート", "先発外れ", "先発落ち", "suplente",
)


def bench_regular(claim: str, target: str, facts: Facts) -> tuple[bool, str]:
    """🔴🔴 §6 — **선발 비율이 낮은 선수의 "선발 제외"인가**. `(버리나, 왜)`.

    > 선발 제외를 결장으로 보지 않는다 — 그 선수의 시즌 **선발 비율이 30% 미만**
    > 이면(가시와 **세가와**는 교체로 7골을 넣었다).

    🔴 재는 자료는 `facts.past_xi` 다 — s2 가 받아 둔 **과거 경기 선발 명단**
       (최대 5경기 · `s2_facts.FOLLOW_CAP`). ⚠️ 시즌 전체가 아니다. 그래서
       **표본 수를 사유에 적는다**(#3 — 모른 척하지 않는다).
    ⚠️ 그 자료가 **없으면 버리지 않는다** — 못 잰 것과 낮은 것은 다른 일이다.
       🔴 그 사실은 사유에 남고, 변수는 그대로 선다(조용히 떨어뜨리지 않는다).
    🔴 **`결장`·`부상`·`징계` 는 이 검사를 안 탄다**(`BENCH_SAID` 에 없다) —
       그것들은 선발 비율과 무관하게 결장이다.
    """
    low = str(claim or "")
    if not any(w.lower() in low.lower() for w in BENCH_SAID):
        return False, ""
    who = str(target or "").strip()
    if not who:
        return False, ""
    rows = [x for box in (facts.past_xi or {}).values() for x in box]
    if not rows:
        return False, ""
    n = len(rows)
    # 🔴 **두 칸을 다 본다** — `XI` 는 선발을 `players`(이름)와 `lineup`(선수
    #    객체) 두 꼴로 들 수 있다(어댑터에 따라 다르다). 한 칸만 보면 **표본이
    #    0**이 되고, 0이면 이 검사가 아무도 안 거른다(조용한 0 · #3).
    starts = sum(1 for xi in rows if who in _xi_names(xi))
    share = starts / n if n else 0.0
    if share >= STARTER_SHARE:
        return False, ""
    return True, (f"`{who}` 는 최근 {n}경기 중 **{starts}경기만 선발**"
                  f"({share:.0%} < {STARTER_SHARE:.0%}) — 선발 제외가 **평소**다"
                  f"(§6 · 교체 주력은 결장이 아니다)")


def _xi_names(xi: Any) -> set[str]:
    """🔴 그 선발 명단의 **이름들** — `players`(이름)와 `lineup`(객체)을 합친다."""
    out = {str(x) for x in (getattr(xi, "players", None) or [])}
    out |= {str(getattr(p, "name", "")) for p in (getattr(xi, "lineup", None)
                                                  or [])}
    return {x for x in out if x}
