"""🔴🔴 **결장 사다리** — 사용자 지시 2026-10-11(연쇄를 앞에서부터 고친다) ①.

> 결장 사다리: fotmob 결장 → (없으면) 명단 대조 → 연맹 징계 공지 → 국내 기사 2매체.
> 명단 대조: 최근 리그 5경기 선발 3회 이상인데 오늘 출전 명단(선발+벤치)에 없으면
> "명단 제외(사유 미상)" — 구조 사실, soft. 징계(경고 누적·퇴장)는 hard.
> "결장 명단 미확보"는 **네 칸 모두 0일 때만**, 칸별 시도 결과를 적는다.

⚠️ 왜 이 파일이 생겼나 — 광주–울산 카드(2026-10-11)의 연쇄:

    결장 미확보 → 기사 0 → 전략 버림 → 전술 예측 템플릿

fotmob 경기 페이지의 `lineup.*.unavailable` 칸 **하나**에 결장이 매달려 있었고,
그 칸이 비면 그 뒤가 전부 비었다. 🔴 사다리는 그 한 줄을 네 줄로 만든다.

🔴 **이 파일은 결장을 '찾는' 곳이다 — 등급을 정하지 않는다.** 등급(soft/hard)은
   변수 단계가 `Missing.source` 를 보고 정한다(사본 금지).

## 🔴🔴 **단계 3+5 통합**(지시 2026-10-14 *"3,5 통합"*)
칸 4(**국내 기사**)는 이 사다리를 부르는 `s2_facts` 가 **딥서치보다 먼저** 돌아
영원히 못 채워졌다 — 모든 카드에 `⏸ **변수 단계에서 센다**` 가 찍혔다(실측
2026-10-14 슬레이트 10장 **전부**). 🔴 매달린 포인터였다.

> 즉 *결장 사다리*(단계 3)와 *딥서치*(단계 5)는 **같은 일**을 둘로 쪼갠 것이다 —
> "누가 못 나오나"를 구조 사실로 묻고(1~3칸), 기사로 묻는다(4칸).

🔴 그래서 `recount` 가 **검증된 기사 결장 변수**로 칸 4 를 다시 센다. 부르는 곳은
   `pipeline` 이고 **s5(변수 검증) 뒤**다 — 그때 비로소 기사 수가 존재한다.
⚠️ 규칙으로 지은 변수(`from_rule`)는 **기사가 아니다** — 세지 않는다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 🔴 사다리 네 칸의 **이름**(카드가 이 순서로 적는다)
RUNGS: tuple[str, ...] = ("fotmob", "명단 대조", "연맹 징계", "국내 기사")

#: 🔴 명단 대조 — 최근 몇 경기를 보나 · 그 안에서 **선발 몇 회 이상**이면 주전인가
LOOK_BACK, STARTS_MIN = 5, 3

#: 🔴 명단 대조가 적는 사유 글자(지시서의 그 말)
ROSTER_WHY = "명단 제외(사유 미상) — 최근 {n}경기 중 {k}회 선발인데 오늘 명단에 없다"


def _names(xi) -> list[str]:
    """🔴 그 XI 의 **선발 이름**. 사본 금지: `strategy._names` 와 같은 규칙."""
    return ([str(p.name) for p in (getattr(xi, "lineup", None) or [])]
            or [str(x) for x in (getattr(xi, "players", None) or [])])


def squad_known(facts, key: str) -> bool:
    """🔴🔴 **오늘 출전 명단을 받았나** — 선발만으로는 모른다.

    > 오늘 출전 명단(**선발+벤치**)에 없으면 … — 사용자 지시 2026-10-11 ①

    ⚠️ 선발 11명만 아는 판에서 *"주전이 선발에 없다"* 는 **벤치인지 결장인지
       모른다**는 뜻이다 — 그것을 결장으로 적으면 거짓이 된다(#4). 🔴 그래서
       소집 명단(`facts.squad`)이나 **벤치**가 있어야 이 칸을 센다.
    """
    if ((facts.squad or {}).get(key) or []):
        return True
    one = (facts.xi or {}).get(key)
    return bool(getattr(one, "bench", None) or [])


def today_squad(facts, key: str) -> set[str]:
    """🔴 **오늘 출전 명단**(선발+벤치). ⚠️ 못 받았으면 **빈 집합**이다.

    🔴 원본은 둘이다 — `facts.squad`(소집 명단)와 오늘 `XI`(선발+벤치). 둘을
       합친다(한쪽만 온 판이 있다 · 실측 2026-10-11 광주: 명단 18명 · XI 11명).
    """
    got = {str(x) for x in ((facts.squad or {}).get(key) or []) if x}
    one = (facts.xi or {}).get(key)
    if one is not None:
        got |= {x for x in _names(one) if x}
        got |= {str(x) for x in (getattr(one, "bench", None) or []) if x}
    return got


def starts_of(facts, key: str) -> tuple[dict[str, int], int]:
    """🔴 `{선수: 선발 횟수}` 와 **본 경기 수**.

    🔴🔴 ⑥(2026-10-11) — **경기 목록의 선발**(최근 10경기)을 먼저 본다.
       ⚠️ 실측 2026-10-11(쇼난): `facts.past_xi` 는 **4경기**뿐이어서 칸이
          *"과거 XI 4경기(<5)"* 로 0 이 됐다. 🔴 `s2e_matchup._history` 는 **10경기
          선발**을 이미 들고 오고 그것이 `facts.recent[key]["games"]` 에 있다.
       🔴 그 목록이 없으면 `past_xi` 로 떨어진다(있는 자료를 버리지 않는다).
    """
    games = list(dict((facts.recent or {}).get(key) or {}).get("games") or [])
    if games:
        got: dict[str, int] = {}
        n = 0
        for one in games[-10:]:
            names = {str(x) for x in (dict(one).get("starters") or []) if x}
            if not names:
                continue           # ⚠️ 명단 없는 경기는 분모에서 뺀다(#3)
            n += 1
            for nm in names:
                got[nm] = got.get(nm, 0) + 1
        if n:
            return got, n
    rows = list((facts.past_xi or {}).get(key) or [])[-LOOK_BACK:]
    got = {}
    for xi in rows:
        for nm in _names(xi):
            if nm:
                got[nm] = got.get(nm, 0) + 1
    return got, len(rows)


def _ko_players() -> dict:
    """🔴 `names_ko.yaml` 의 선수 한글 표기(원본은 그 파일 하나다)."""
    from app import rules as _rules
    return dict(_rules.names_ko().get("players") or {})


def _pid_rows(facts, key: str) -> list[dict]:
    """🔴 ④ — 신원표 재료(오늘 XI·직전·최근 경기 선발·소집 명단·결장)."""
    out: list[dict] = []
    one = (facts.xi or {}).get(key)
    for p in (getattr(one, "lineup", None) or []):
        out.append({"name": getattr(p, "name", ""),
                    "number": getattr(p, "number", None),
                    "pos": getattr(p, "pos", ""), "source": "오늘 XI"})
    for nm in (getattr(one, "players", None) or []):
        out.append({"name": str(nm), "source": "오늘 XI"})
    for nm in (getattr(one, "bench", None) or []):
        out.append({"name": str(nm), "source": "오늘 XI/벤치"})
    for game in list(dict((facts.recent or {}).get(key) or {})
                     .get("games") or []):
        out += [{"name": str(x), "source": "최근 경기"}
                for x in (dict(game).get("starters") or []) if x]
    out += [{"name": str(nm), "source": "소집 명단"}
            for nm in ((facts.squad or {}).get(key) or [])]
    out += [{"name": getattr(m, "name", ""), "source": "결장 명단"}
            for m in ((facts.missing or {}).get(key) or [])]
    return [r for r in out if str(r.get("name") or "").strip()]


def roster_gap(facts, key: str) -> list:
    """🔴🔴 칸 2 — **명단 대조**로 찾은 결장.

    > 최근 리그 5경기 선발 3회 이상인데 오늘 출전 명단(선발+벤치)에 없으면
    > "명단 제외(사유 미상)" — 구조 사실, soft.

    ⚠️ 오늘 명단을 못 받았으면 **아무도 세지 않는다** — 없는 자료로 결장을
       만들면 조용한 거짓이 된다(#4). 그 사실은 사다리가 사유로 적는다.
    """
    from app.core.schema import Missing
    if not squad_known(facts, key):
        return []
    # 🔴🔴 ④ — **id 로 견준다**(사용자 지시 2026-10-11 ④). ⚠️ 이름 글자로 보면
    #    한글 캡처 XI 와 로마자 과거 선발이 **다른 사람**이 된다.
    from app.core import playerid as _pid
    box = _pid.build(rows=_pid_rows(facts, key), ko=_ko_players())
    squad = {_pid.resolve(box, said=x)[0] or f"name:{x}"
             for x in today_squad(facts, key)}
    starts, n = starts_of(facts, key)
    if n < LOOK_BACK:
        # ⚠️ 5경기를 못 모았으면 **문턱을 그 수에 맞춰 올리지 않는다** — 적은
        #    표본으로 주전을 가리면 로테이션이 결장으로 샌다. 그래서 안 센다.
        return []
    out = []
    for nm, k in sorted(starts.items(), key=lambda x: (-x[1], x[0])):
        ident = _pid.resolve(box, said=nm)[0] or f"name:{nm}"
        if k < STARTS_MIN or ident in squad:
            continue
        out.append(Missing(name=str(nm), reason="other", source="roster",
                           why=ROSTER_WHY.format(n=n, k=k)))
    return out


def ladder(facts, *, keys: list[str], league: str = "",
           articles: dict | None = None,
           discipline: dict | None = None) -> dict:
    """🔴🔴 **사다리를 내려간다**. 돌려주는 표:

    ```
    {"add": {팀 열쇠: [Missing …]}, "rungs": [{"rung","got","why"} …]}
    ```

    🔴 **위 칸이 찼으면 아래 칸을 안 센다**(지시서의 *"(없으면)"*). 그래도 **칸별
       시도 결과를 적는다** — 건너뛴 것과 0 건인 것을 가른다(#3).
    ⚠️ 칸 4(국내 기사)는 이 단계에 자료가 없다 — 기사 변수는 **뒤 단계**가 만든다.
       그래서 여기서는 `articles`(있으면 그 수)만 적고, 카드가 변수 단계의 수를
       덮어 적는다(지어내지 않는다).
    """
    rows: list[dict] = []
    add: dict[str, list] = {}
    # ── 칸 1 — fotmob 경기 페이지(`lineup.*.unavailable`)
    got1 = sum(len((facts.missing or {}).get(k) or []) for k in keys)
    rows.append({"rung": "fotmob", "got": got1,
                 "why": ("경기 페이지 `unavailable` 칸" if got1
                         else "🔴 **0건** — 경기 페이지에 결장 칸이 비었다")})
    # ── 칸 2 — 명단 대조
    if got1:
        rows.append({"rung": "명단 대조", "got": 0,
                     "why": "⬜ **건너뛰었다** — 위 칸이 찼다"})
    else:
        made = {k: roster_gap(facts, k) for k in keys}
        made = {k: v for k, v in made.items() if v}
        n2 = sum(len(v) for v in made.values())
        why = (f"최근 {LOOK_BACK}경기 선발 {STARTS_MIN}회 이상 ↔ 오늘 명단"
               if n2 else "🔴 **0건** — " + _why_empty(facts, keys))
        rows.append({"rung": "명단 대조", "got": n2, "why": why})
        for k, v in made.items():
            add.setdefault(k, []).extend(v)
    # ── 칸 3 — 연맹 징계 공지
    #  🔴🔴 **받아 온 공시가 있으면 그것을 센다**(지시 2026-10-13 밤 넷째 3번).
    #     ⚠️ 받는 일은 **부르는 쪽**(s2_facts · async)이 한다 — 이 함수는 동기다.
    #     🔴 L2: 공시는 **현재 값**이라 재생에서는 부르는 쪽이 **안 넘긴다**.
    if discipline is not None:
        got3 = int(dict(discipline).get("n") or 0)
        why3 = str(dict(discipline).get("why") or "")
    else:
        got3, why3 = _discipline(league)
    rows.append({"rung": "연맹 징계", "got": got3, "why": why3})
    # ── 칸 4 — 국내 기사 2매체(변수 단계가 센다)
    box = dict(articles or {})
    rows.append({"rung": "국내 기사", "got": int(box.get("n") or 0),
                 "why": str(box.get("why") or
                            "⏸ **변수 단계에서 센다** — 기사 결장 변수(F 하위)의 "
                            "매체 수를 카드가 적는다")})
    return {"add": add, "rungs": rows}


#: 🔴 **기사 결장**으로 셀 변수 유형(카탈로그의 결장 계열). ⚠️ 규칙 변수는 뺀다.
ARTICLE_TYPES: tuple[str, ...] = ("absence", "def_absence", "absence_att",
                                  "suspension", "injury", "return",
                                  "doubtful")

#: 🔴 지시서의 *"국내 기사 **2매체**"* — 그 수를 넘겨야 칸이 **찼다**고 적는다
MEDIA_MIN = 2


def articles_of(variables, *, keys: list[str] | None = None) -> dict:
    """🔴🔴 **칸 4 — 검증된 기사 결장 변수**를 센다. `{"n", "why", "rows"}`.

    🔴 `variables` 는 **s5 를 지난 것**이다(신원·날짜·유형 검사 통과).
    ⚠️ `from_rule` 이 있는 변수는 **구조 사실에서 규칙이 지은 것**이라 기사가
       아니다 — 세면 칸 1~3 을 두 번 세는 셈이다.
    ⚠️ `n_sources` 는 §6-5 가 적은 **원천 수**다. 없으면(0) 세되 매체 수는
       *"못 쟀다"* 로 적는다 — 0 으로 적으면 조용한 거짓이 된다(#3).
    """
    wanted = {str(x) for x in (keys or [])}
    rows = []
    for v in list(variables or []):
        if str(getattr(v, "from_rule", "") or ""):
            continue
        if str(getattr(v, "type", "")) not in ARTICLE_TYPES:
            continue
        if wanted and str(getattr(v, "subject", "")) not in wanted:
            continue
        rows.append(v)
    if not rows:
        return {"n": 0, "rows": [],
                "why": ("🔴 **0건** — 딥서치가 기사에서 결장 사실을 못 건졌다"
                        "(단계 3+5 통합 · 규칙으로 지은 변수는 안 센다)")}
    grades = [str(getattr(v, "grade", "") or "") for v in rows]
    srcs = [int(getattr(v, "n_sources", 0) or 0) for v in rows]
    top = next((g for g in ("S", "A", "B", "C") if g in grades), "")
    n_media = max(srcs) if srcs else 0
    said = (f"기사 결장 변수 **{len(rows)}개**"
            + (f" · 원천 등급 최고 `{top}`" if top else " · ⬜ 원천 등급을 못 쟀다")
            + (f" · 매체 최대 {n_media}곳" if n_media
               else " · ⬜ 매체 수를 못 쟀다(§6-5 칸이 비었다)"))
    if n_media and n_media < MEDIA_MIN:
        said += f" · ⚠️ 지시서 문턱 {MEDIA_MIN}매체 **미달**"
    return {"n": len(rows), "rows": rows, "why": said}


def recount(rungs: list, variables, *, keys: list[str] | None = None) -> tuple:
    """🔴🔴 **칸 4 만** 기사 수로 다시 적은 사다리와 그 사유. `(새 사다리, 글자)`.

    🔴 칸 1~3 은 **건드리지 않는다** — 그것은 s2 가 구조 사실로 센 것이다.
    ⚠️ 사다리를 안 돌린 실행(빈 목록)에는 아무것도 하지 않는다 — 없는 칸을
       지어내지 않는다(#3).
    """
    got = [dict(x) for x in (rungs or [])]
    if not got:
        return got, "⬜ 사다리를 안 돌렸다 — 칸 4 를 다시 셀 자리가 없다"
    box = articles_of(variables, keys=keys)
    for one in got:
        if str(one.get("rung")) == "국내 기사":
            was = int(one.get("got") or 0)
            one["got"] = int(box["n"])
            one["why"] = str(box["why"])
            return got, (f"칸 4(국내 기사) {was} → **{box['n']}** · {box['why']}")
    return got, "⬜ 사다리에 `국내 기사` 칸이 없다"


def _why_empty(facts, keys: list[str]) -> str:
    """🔴 #3 — 명단 대조가 0 인 **까닭을 이름으로** 적는다(셋이 다르다)."""
    said = []
    for key in keys:
        if not squad_known(facts, key):
            said.append(f"`{key}` 오늘 출전 명단(선발+벤치)을 못 받았다")
            continue
        _starts, n = starts_of(facts, key)
        if n < LOOK_BACK:
            said.append(f"`{key}` 과거 XI {n}경기(<{LOOK_BACK})")
    return " · ".join(said) or f"주전({STARTS_MIN}회 이상)이 다 명단에 있다"


def _discipline(league: str) -> tuple[int, str]:
    """🔴🔴 칸 3 — **연맹 징계 공지**. `(건수, 사유)`.

    ⚠️ 2026-10-11 현재 **공지 주소를 받아 둔 리그가 없다** — 그래서 이 칸은 늘
       0 이고 그 사실을 적는다. 🔴 주소를 **추측해 붙이지 않는다**(#4: 받아서
       확인한 것만 쓴다). 표는 `config/league_discipline.yaml` 이고, 그 파일에
       리그가 적히면 이 함수가 받아 센다.
    """
    from app import rules
    box = rules.discipline_of(str(league or ""))
    if not box:
        return 0, ("⬜ **통로 없음** — `config/league_discipline.yaml` 에 "
                   f"`{league or '그 리그'}` 공지 주소가 없다(추측해 붙이지 않는다)")
    return 0, (f"⏸ 주소는 있다({box.get('url')}) — 받아 읽는 통로는 아직 "
               f"안 이었다(`tests/test_wiring.py` 의 `NOT_WIRED`)")


def unknown(got: dict) -> bool:
    """🔴🔴 *"결장 명단 미확보"는 **네 칸 모두 0일 때만**."*"""
    return all(int(r.get("got") or 0) == 0 for r in (got.get("rungs") or []))


def said_of(got: dict) -> str:
    """🔴 카드·보고가 적는 **칸별 한 줄**."""
    return " / ".join(f"{r['rung']} {r['got']}건 — {r['why']}"
                      for r in (got.get("rungs") or []))


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **예상 XI 에서 뺄 수 있나** — 사용자 지시 2026-10-13 밤 다섯째 2번
# ══════════════════════════════════════════════════════════════════
#
#  > fotmob 결장(B) 단독 → 예상 XI 에서 빼지 않는다. "결장 의심(B 단독)" 표시만.
#  > 빼는 조건: S등급(공식 징계·구단 발표) 하나 또는 B + A/C 원천 교차 확인.
#
#  🔴 **등급은 원천이 정한다**(사본 금지):
#     · `discipline` 연맹 징계 공시 → **S**
#     · `article`    기사 → 그 도메인 등급(`search.sources.grade_of`)
#     · `page`       fotmob 경기 페이지 → **B**
#     · `roster`     명단 대조 → **구조 사실**(아래 주석)
#  🔴 **이 함수는 명단·표시만 바꾼다** — 확률 경로는 이것을 부르지 않는다(XA3).

#: 🔴 사다리 칸 → 등급. ⚠️ `roster` 는 등급이 아니라 **구조 사실**이다.
GRADE_OF: dict[str, str] = {"discipline": "S", "page": "B"}


def grade_of_row(row, *, league: str = "") -> str:
    """🔴 결장 한 줄의 **등급 글자**. `article` 만 도메인 표를 본다."""
    said = str(getattr(row, "source", "") or "page")
    if said == "article":
        from app.core.search import sources as _sr
        got, _w = _sr.grade_of(str(getattr(row, "source_url", "") or ""),
                               league=str(league or ""))
        return str(got).upper()
    return GRADE_OF.get(said, said)


def removable(rows, *, league: str = "") -> tuple[bool, str]:
    """🔴🔴 그 선수를 **예상 XI 에서 뺄 수 있나** — `(뺀다, 사유)`.

    🔴 뺀다 —
      · **S** 가 하나라도 있다(연맹 징계 공시 · 구단 발표 등급 S 도메인)
      · **B + A/C 교차**(fotmob 칸 + 다른 등급의 원천)
      · **명단 대조**(`roster`) — *"오늘 선발+벤치에 그 이름이 없다"* 는 구조
        사실이다. 명단이 공개된 판에서 그 선수는 **선발이 불가능**하다.
        ⚠️ 지시가 바꾼 것은 fotmob `unavailable` 칸 하나다(그 칸은 *"의심"*
        수준의 이름도 싣는다).
    🔴 못 뺀다 — **B 단독**. 카드는 `결장 의심(B 단독)` 으로만 적는다.
    """
    said = list(rows or [])
    if not said:
        return False, "⬜ 결장 줄이 없다"
    grades = [grade_of_row(r, league=league) for r in said]
    kinds = {str(getattr(r, "source", "") or "page") for r in said}
    if "roster" in kinds:
        return True, "명단 대조 — 오늘 출전 명단(선발+벤치)에 없다(구조 사실)"
    if "S" in grades:
        return True, f"**S등급** 원천이 있다({sorted(set(grades))})"
    cross = [g for g in grades if g in ("A", "C")]
    if "B" in grades and cross:
        return True, (f"**B + {sorted(set(cross))} 교차 확인** — 두 등급이 "
                      f"같은 결장을 말한다")
    if grades == ["B"] * len(grades):
        return False, ("🔴 **B 단독**(fotmob 경기 페이지 하나) — 예상 XI 에서 "
                       "빼지 않는다 · `결장 의심(B 단독)` 으로만 적는다")
    return False, (f"🔴 등급 {sorted(set(grades))} 만이다 — S 하나도 "
                   f"B+A/C 교차도 아니다")
