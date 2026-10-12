"""🔴🔴 **s6c — 가설 검증**. 순서 재편 지시서(2026-10-10 다섯째) 단계 4.

> 4-1 가설마다 예측 신호를 시뮬레이션 출력과 대조(코드): **지지 / 반박 /
>     판단 불가**(지표 없음·표본 부족).
> 4-2 반박된 가설은 **원인을 코드가 분류**한다 — (a) 입력 누락 · (b) 기준 낡음 ·
>     (c) 가설 오류.
> 4-3 **재실행은 최대 1회**: (a) 는 그 변수의 효과가 **적합돼 있는데 빠졌을 때만**
>     넣고 다시 돈다. (b) 는 기준 항 가중을 규칙대로 다시 계산해 한 번 더 돈다.
>     **적합값이 없는 변수를 검증을 맞추려고 임의로 넣지 않는다.**
> 4-5 산출: **가설 검증표** — 가설·신호·시뮬 값·판정·반박 원인.

🔴 이 단계는 **확률을 만들지 않는다** — 읽고 견주고, (4-3 에 해당할 때만) 시뮬을
   **같은 함수로** 한 번 더 돌린다.
🔴 LLM 을 **부르지 않는다**(전부 코드다).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.schema import Facts, HypoSet, MatchRef
from app.core.state import RunState

logger = logging.getLogger(__name__)

#: 🔴 §4-2 원인 글자
MISS, STALE, WRONG = "입력 누락", "기준 낡음", "가설 오류"
#: 🔴 §4-2 (b) — **핵심 몇 명 결장**이면 기준이 낡았다고 보나(지시서가 적은 3)
ABSENT_STALE = 3
#: 🔴 §4-2 (b) 의 **못 센 칸** — 카드가 적고, **모델에 가는 글에는 안 섞는다**
GAP_COACH = "⚠️ 감독 교체 직후는 **못 센다**(취임일 자료가 없다)"
#: 🔴 §4-3 — 재실행 상한
MAX_RERUN = 1


@dataclass
class Row:
    """🔴 검증표 한 줄(§4-5)."""

    side: str = ""
    kind: str = ""          # `reasons`·`breaks`
    text: str = ""
    var_ids: list = field(default_factory=list)
    signal: str = ""
    value: float | None = None
    want: float | None = None
    verdict: str = ""
    cause: str = ""
    why: str = ""

    def as_dict(self) -> dict:
        return {"side": self.side, "kind": self.kind, "text": self.text,
                "var_ids": list(self.var_ids), "signal": self.signal,
                "value": self.value, "want": self.want,
                "verdict": self.verdict, "cause": self.cause, "why": self.why}


#: 🔴🔴 S5-1 검증 출처 — 지시서가 적은 일곱(V7 은 가설 신호다)
SOURCES = {"V1": "Elo 기준 확률", "V2": "동기", "V3": "일정·피로",
           "V4": "감독 발언·기타", "V5": "맞대결", "V6": "시장(표시만)",
           "V7": "가설 신호"}
#: 🔴 S5-3 — 등급 조정 문턱(config 가 든다 · 적합 전 임시값)
CONF = "config/verify_rules.yaml"


def rules_table() -> dict:
    from app import rules
    return dict(rules._load(CONF) or {})


def sources(ref: MatchRef, facts: Facts, mr, varset, *, layers: dict | None,
            turnover: dict | None) -> list[dict]:
    """🔴🔴 S5-1 — **검증 출처 표**. 한 줄 꼴:

    ```
    {"src": "V2", "name": "동기", "dir": "같음"|"반대"|"중립",
     "size": "강"|"중"|"약", "trust": "…", "refs": [변수 id…],
     "cause": "낡음"|"이미 반영"|"상성 사각"|"", "why": "…"}
    ```

    🔴 **확률을 바꾸지 않는다**(S5 머리줄) — 방향을 견주고 등급만 움직인다.
    🔴 방향 비교의 기준은 **상성 결론**(`mr.verdict["edge"]`)이다.
    """
    from app.core import matchup as _mu
    box = dict(rules_table().get("size") or {})
    edge = str(dict(getattr(mr, "verdict", None) or {}).get("edge") or "")
    out: list[dict] = []
    # ── V1 Elo 기준 확률 — **기준 낡음**이면 신뢰도를 낮춘다
    base = (layers or {}).get("base")
    probs = getattr(base, "probs", None)
    stale = _stale(ref, facts, turnover)
    if probs is not None:
        side = ("home" if float(probs.home) > float(probs.away) else "away")
        gap = abs(float(probs.home) - float(probs.away))
        out.append({
            "src": "V1", "name": SOURCES["V1"],
            "dir": _dir(side, edge), "size": _size(gap, box),
            "trust": ("🔴 **기준 낡음**" if stale else "그대로"),
            "refs": [], "cause": (MISS_STALE if stale else ""),
            "why": (f"① 기준 홈 {float(probs.home):.0%} · 원정 "
                    f"{float(probs.away):.0%}" + (f" · {stale}" if stale
                                                  else ""))})
    # ── V2~V5 — **변수 배치표가 보낸 것**(②) 그대로
    for src in ("V2", "V3", "V4", "V5"):
        for one in (varset.of(src) if varset else []):
            side = ("home" if str(one.favors) == "home"
                    else "away" if str(one.favors) == "away" else "")
            said = _dir(side, edge) if side else "중립"
            axes = [x for x in one.places if x in _mu_axes()]
            out.append({
                "src": src, "name": SOURCES[src], "dir": said,
                "size": ("강" if one.hardness == "hard" and one.weight >= 2.0
                         else "중" if one.weight >= 1.0 else "약"),
                "trust": str(one.hardness), "refs": [one.id],
                "cause": ("" if said != "반대" else
                          (CAUSE_IN if axes else CAUSE_BLIND)),
                "why": f"`{one.id}` {one.claim[:60]}"})
    # ── V6 시장 — **표시만**(C12: 등급 영향 없음)
    # 🔴 V6 — `MarketProb.probs` 는 **배당 열쇠 사전**이다(ProbTriple 이 아니다)
    from app.core import odds as _odds
    mk = dict(getattr((layers or {}).get("market"), "probs", None) or {})
    h = mk.get(_odds.key_of("win", "home"))
    a = mk.get(_odds.key_of("win", "away"))
    if h is not None and a is not None:
        side = "home" if float(h) > float(a) else "away"
        out.append({"src": "V6", "name": SOURCES["V6"], "dir": _dir(side, edge),
                    "size": "—", "trust": "표시만", "refs": [], "cause": "",
                    "why": (f"시장 홈 {float(h):.0%} · 원정 {float(a):.0%}"
                            " — **등급 영향 없음**")})
    return out


def _mu_axes() -> tuple:
    from app.core import routing
    return routing.AXES


def _dir(side: str, edge: str) -> str:
    if not side or not edge:
        return "중립"
    return "같음" if side == edge else "반대"


def _size(gap: float, box: dict) -> str:
    strong = float(box.get("strong_gap") or 0.15)
    mid = float(box.get("mid_gap") or 0.05)
    return "강" if gap >= strong else "중" if gap >= mid else "약"


#: 🔴 S5-2 원인 글자
MISS_STALE, CAUSE_IN, CAUSE_BLIND = "낡음", "이미 반영", "상성 사각"


def grade_move(rows: list[dict], claims: dict) -> dict:
    """🔴🔴 S5-3 — **등급 조정**(확률은 그대로). 돌려주는 표:

    `{"steps": 내릴 단계 수, "none": 등급 없음인가, "why": […]}`

    > · (c) 중 **hard·크기 "강"** 반대 1개 이상 → 한 단계 내림
    > · (c) 반대 **2개 이상** → 등급 없음
    > · V7 주 가설 지지 **0개** → 한 단계 내림
    > · (a)(b)·V6 은 등급 영향 **없음**
    """
    blind = [r for r in rows if r.get("dir") == "반대"
             and r.get("cause") == CAUSE_BLIND]
    said: list[str] = []
    steps, none = 0, False
    hard_strong = [r for r in blind
                   if str(r.get("trust")) == "hard" and r.get("size") == "강"]
    if hard_strong:
        steps += 1
        said.append(f"🔴 (c) 상성 사각 hard·강 {len(hard_strong)}건 → 한 단계 "
                    f"내림 · {[r['refs'] for r in hard_strong][:3]}")
    if len(blind) >= 2:
        none = True
        said.append(f"🔴 (c) 상성 사각 반대 {len(blind)}건 → **등급 없음**")
    if dict(claims or {}).get("counts", {}).get("지지", 0) == 0 \
            and dict(claims or {}).get("rows"):
        steps += 1
        said.append("🔴 V7 주 가설 **지지 0개** → 한 단계 내림")
    skipped = [r["src"] for r in rows if r.get("dir") == "반대"
               and r.get("cause") in (MISS_STALE, CAUSE_IN)]
    if skipped:
        said.append(f"⬜ (a)(b) 반대 {sorted(set(skipped))} — 등급 영향 없다")
    if any(r.get("src") == "V6" for r in rows):
        said.append("⬜ V6 시장 — **등급 영향 없다**(C12)")
    return {"steps": steps, "none": none, "why": said}


def run(ref: MatchRef, facts: Facts, hypo: HypoSet, sim: dict, *,
        variables: list | None = None, turnover: dict | None = None,
        mr=None, varset=None, layers: dict | None = None,
        state: RunState) -> dict:
    """🔴🔴 §4 — 검증표를 만든다. 돌려주는 표:

    ```
    {"rows": [검증표 줄…], "supported": [지지된 줄…],
     "counts": {"지지": n, "반박": n, "판단 불가": n},
     "stale": "사유"|"", "rerun": "사유"|"", "why": "한 줄"}
    ```

    ⚠️ **재실행 판단만** 한다 — 실제 재실행은 파이프라인이 `rerun` 을 보고 한 번
       돈다(시뮬 함수는 한 곳이다 · 사본 금지).
    """
    from app.core import signals as _sg
    league = _sg.league_of(facts, ref=ref)
    rows: list[Row] = []
    for one in (hypo.hypotheses or []):
        side = str(getattr(one, "team", "") or "")
        for kind in ("reasons", "breaks"):
            for line in (getattr(one, kind, None) or []):
                rows.append(_one(line, side=side, kind=kind, sim=sim,
                                 league=league))
    stale = _stale(ref, facts, turnover)
    sides = _stale_sides(ref, facts, turnover)
    for r in rows:
        if r.verdict == _sg.NO:
            r.cause, r.why = _cause(r, variables=variables, stale=stale,
                                    why=r.why, stale_sides=sides, ref=ref)
    counts = {k: sum(1 for r in rows if r.verdict == k)
              for k in (_sg.OK, _sg.NO, _sg.NA)}
    rerun = _rerun_why(rows, stale=stale)
    said = (f"가설 {len(rows)}줄 — 지지 {counts[_sg.OK]} · 반박 {counts[_sg.NO]}"
            f" · 판단 불가 {counts[_sg.NA]}"
            + (f" · {stale}" if stale else ""))
    state.note(f"s6c 단계 4 — {said}"
               + (f" · 🔴 재실행 사유: {rerun}" if rerun else ""))
    logger.info("[s6c] %s · 재실행 %s", said, rerun or "없다")
    got = {"rows": [r.as_dict() for r in rows],
           "supported": [r.as_dict() for r in rows if r.verdict == _sg.OK],
           "counts": counts, "stale": stale, "rerun": rerun,
           # 🔴 **못 센 칸**은 따로 든다(카드가 적는다 · 모델 글에는 안 섞인다)
           "gaps": [GAP_COACH], "why": said}
    # ⚠️ **[1d] 말·일정 ↔ 행동 줄은 걷었다** — 그 줄의 수(우선순위 지수 ⑨)가
    #    지시서 2026-10-12(셋째) §1 으로 **지워졌다**. 🔴 지수가 없으면 *"아꼈다"*
    #    를 말할 근거가 없다(지어내지 않는다 · #4).
    # 🔴🔴 S5-1·S5-3 — **검증 출처 표**와 **등급 조정**(확률은 그대로)
    if mr is not None:
        got["sources"] = sources(ref, facts, mr, varset, layers=layers,
                                 turnover=turnover)
        got["grade"] = grade_move(got["sources"], got)
        same = len([r for r in got["sources"] if r["dir"] == "같음"])
        against = len([r for r in got["sources"] if r["dir"] == "반대"])
        got["why"] = (f"{said} · 검증 같은 방향 {same} · 반대 {against}"
                      + (f" · 등급 {got['grade']['why']}"
                         if got["grade"]["why"] else ""))
        state.note(f"S5 검증 — 같은 방향 {same} · 반대 {against} · "
                   + (" / ".join(got["grade"]["why"]) or "등급 조정 없다"))
    return got


def _one(line, *, side: str, kind: str, sim: dict, league: dict) -> Row:
    """🔴 §4-1 — 한 줄을 대조한다."""
    from app.core import signals as _sg
    got = _sg.check(getattr(line, "signal", None), sim, league=league)
    sig = getattr(line, "signal", None)
    return Row(side=side, kind=kind, text=str(getattr(line, "text", "") or ""),
               var_ids=[str(x) for x in (getattr(line, "var_ids", None) or [])],
               signal=(_sg._say(sig) if sig is not None else "없다"),
               value=got.get("value"), want=got.get("want"),
               verdict=str(got.get("verdict") or ""), why=str(got.get("why")
                                                              or ""))


def _stale_sides(ref: MatchRef, facts: Facts,
                 turnover: dict | None) -> set[str]:
    """🔴🔴 **어느 쪽 기준이 낡았나** — `{"home"}`·`{"away"}`·둘·빈 집합.

    ⚠️ 실사고 2026-10-11(LAFC): `_stale` 은 **경기 단위 글자**였고 `_cause` 가
       그것만 보고 그 경기의 **모든** 반박에 (b) 를 붙였다 — 결장과 아무 관계 없는
       폼 가설(`S01-home`)까지 *"기준 낡음"* 이 됐다(반박 6건 중 2건이 그랬다).
    🔴 그래서 쪽을 가려 돌려준다 — 조건은 `_stale` 과 **같은 둘**이다(사본 금지:
       선수단 교체 깃발 · 결장 `ABSENT_STALE` 명 이상).
    """
    got: set[str] = set()
    for side, one in dict(turnover or {}).items():
        if dict(one).get("on") and str(side) in ("home", "away"):
            got.add(str(side))
    for side in ("home", "away"):
        key = str(getattr(ref, side))
        if len(list((facts.missing or {}).get(key) or [])) >= ABSENT_STALE:
            got.add(side)
    return got


def _stale(ref: MatchRef, facts: Facts, turnover: dict | None) -> str:
    """🔴🔴 §4-2 (b) — **기준 낡음 의심**인가. 맞으면 사유, 아니면 빈 글자.

    > 한쪽이 `squad_turnover`·**감독 교체 직후**·**핵심 3명 이상 결장**
    """
    said: list[str] = []
    for side, one in dict(turnover or {}).items():
        if dict(one).get("on"):
            name = str(getattr(ref, f"{side}_name", "") or "")
            said.append(f"{name} 선수단 교체")
    for side in ("home", "away"):
        key = str(getattr(ref, side))
        name = str(getattr(ref, f"{side}_name", "") or "")
        rows = list((facts.missing or {}).get(key) or [])
        if len(rows) >= ABSENT_STALE:
            said.append(f"{name} 결장 {len(rows)}명")
    # ⚠️ **감독 교체 직후**를 세는 자료가 없다 — `facts.coach` 는 이름뿐이고
    #    취임일이 없다(실측 2026-10-10). 🔴 그 칸은 비워 두고 그 사실을 **따로**
    #    적는다(`GAP_COACH`).
    #    ⚠️ 실사고 2026-10-10: 그 문장을 `stale` 글귀 **안에** 붙였더니 최종 평이
    #       *"선수단 교체는 **감독 교체 직후라** 취임일 자료가 없어 못 센다"* 로
    #       두 사실을 하나로 붙여 **거짓을 만들었다**. 🔴 모델에 가는 글에 군더더기를
    #       넣지 않는다.
    if not said:
        return ""
    return "🔴 **기준 낡음 의심** — " + " · ".join(said)


#: 🔴🔴 **기준을 낡게 만드는 변수 유형** — 그 가설이 이 유형을 근거로 들고,
#  그 변수가 **낡은 쪽** 것일 때만 (b) 다. ⚠️ 목록은 배치표의 그 유형들이다.
STALE_TYPES = ("absence", "def_absence", "absence_att", "suspension",
               "squad_rotation", "returning", "national_duty_return",
               "coach_change")


def _var_side(one, ref=None) -> str:
    """🔴 그 변수가 **어느 팀 것인가** — `subject` 열쇠, 없으면 id 꼬리.

    ⚠️ `favors`(누구에게 유리한가)로 뒤집어 재지 않는다 — 그것은 추측이다(#4).
    """
    rid = str(getattr(one, "id", "") or "")
    if rid.endswith("-home"):
        return "home"
    if rid.endswith("-away"):
        return "away"
    said = str(getattr(one, "subject", "") or "")
    if ref is not None and said:
        if said == str(getattr(ref, "home", "")):
            return "home"
        if said == str(getattr(ref, "away", "")):
            return "away"
    return ""


def _stale_hit(row: Row, variables: list | None, sides: set[str],
               ref=None) -> str:
    """🔴 ②-a — 그 가설의 근거 중 **낡은 쪽의 결장·교체 변수**를 적는다."""
    box = {str(v.id): v for v in (variables or [])}
    out: list[str] = []
    for vid in row.var_ids:
        one = box.get(str(vid))
        if one is None:
            continue
        if str(getattr(one, "type", "")) not in STALE_TYPES:
            continue
        side = _var_side(one, ref)
        if side and side in sides:
            out.append(f"`{vid}`({one.type}·{side})")
    return " · ".join(out)


def _cause(row: Row, *, variables: list | None, stale: str,
           why: str, stale_sides: set[str] | None = None, ref=None
           ) -> tuple[str, str]:
    """🔴🔴 §4-2 — 반박된 가설의 **원인 분류**. `(원인, 사유)`.

    | 원인 | 언제 |
    |---|---|
    | (a) `입력 누락` | 근거 변수가 **적합된 효과를 갖고도** 시뮬에 안 들어갔다 |
    | (b) `기준 낡음` | 한쪽이 선수단 교체·핵심 3명 이상 결장 |
    | (c) `가설 오류` | 위 둘이 아니다 — 시뮬과 정면으로 반대다 |
    """
    gone = _missing_inputs(row, variables)
    if gone:
        return MISS, f"{why} · 🔴 (a) **입력 누락** — {gone}"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 ②-a **(b) 는 그 가설의 근거가 낡은 쪽일 때만** — 2026-10-11
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전엔 `stale`(경기 단위 글자)만 보고 **모든** 반박에 (b) 를 붙였다 —
    #     폼 가설까지 *"기준 낡음"* 이 됐고(실측: 반박 6건 전부 (b)) 그래서 원인
    #     분류가 **아무 말도 하지 않았다**.
    if stale:
        hit = _stale_hit(row, variables, set(stale_sides or ()), ref)
        if hit:
            return STALE, f"{why} · 🔴 (b) {stale} — 이 가설의 근거 {hit}"
        # 🔴 낡은 쪽 근거가 없으면 (c) 다 — 그래도 **그 사실을 적는다**(#3)
        return WRONG, (f"{why} · 🔴 (c) **가설 오류** — 시뮬과 반대다"
                       f"(⚠️ 경기에는 기준 낡음 의심이 있지만 이 가설의 근거는 "
                       f"그 쪽 결장·교체가 **아니다**)")
    return WRONG, f"{why} · 🔴 (c) **가설 오류** — 시뮬과 반대다"


def _missing_inputs(row: Row, variables: list | None) -> str:
    """🔴 §4-2 (a) — 그 가설의 근거 변수가 **시뮬에 안 들어갔나**.

    🔴 "들어갔다"의 뜻: 그 변수가 **무게를 갖고 근거로 쓰일 수 있다**
       (`usable_as_basis` 이고 `weight > 0`). ⚠️ 무게 0 이거나 근거 불가면 ③ 이
       그것을 **안 움직였다**는 뜻이다.
    ⚠️ 변수 목록이 없으면 빈 글자다(모르면 (a) 라고 하지 않는다 · #4).
    """
    if not variables:
        return ""
    box = {str(v.id): v for v in variables}
    out: list[str] = []
    for vid in row.var_ids:
        one = box.get(str(vid))
        if one is None:
            out.append(f"`{vid}` 없는 변수")
            continue
        if not bool(getattr(one, "usable_as_basis", False)):
            out.append(f"`{vid}` 근거 불가")
        elif float(getattr(one, "weight", 0.0) or 0.0) <= 0.0:
            out.append(f"`{vid}` 무게 0")
    return " · ".join(out)


def _rerun_why(rows: list[Row], *, stale: str) -> str:
    """🔴🔴 §4-3 — **재실행 사유**(없으면 빈 글자). ⚠️ 최대 **한 번**이다.

    🔴 (a) 는 *"그 변수의 효과가 **적합돼 있는데** 빠졌을 때만"* 이다 — 우리
       계수는 **전부 임시값**이므로(실측 2026-10-10) 그 조건이 **아직 성립하지
       않는다**. 그래서 (a) 로는 재실행하지 않고 그 사실을 적는다(#4: 적합값이
       없는 변수를 검증을 맞추려고 임의로 넣지 않는다).
    🔴 (b) 기준 낡음은 **가중을 규칙대로 다시 계산해** 한 번 더 돈다 — 그 규칙은
       `config/squad_turnover.yaml` 의 `weaken` 이고 이미 적용돼 있다. 그러면
       **다시 돌 이유가 없다**(같은 수가 나온다) — 적용 안 됐을 때만 돈다.
    """
    from app.core import signals as _sg
    miss = [r for r in rows if r.verdict == _sg.NO and r.cause == MISS]
    if miss:
        return ("🔴 (a) 입력 누락 "
                f"{len(miss)}건이지만 **재실행하지 않는다** — 그 변수의 효과가 "
                "적합돼 있지 않다(전부 임시값이다 · §4-3 금지: 적합값 없는 변수를 "
                "검증을 맞추려고 넣지 않는다)")
    return ""


def rerun_needed(got: dict) -> bool:
    """🔴 §4-3 — **실제로 다시 돌아야 하나**. 지금은 늘 거짓이다.

    🔴 위 `_rerun_why` 가 적은 대로다: (a) 는 적합값이 없어 금지, (b) 는 가중이
       이미 적용돼 있다. ⚠️ 그래서 **재실행 0회**이고 그 사실이 카드에 남는다.
       🔴 적합이 들어오면 이 함수가 참을 돌려주고 파이프라인이 **한 번** 돈다.
    """
    return bool(dict(got or {}).get("rerun_do"))
