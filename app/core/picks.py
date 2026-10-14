"""🔴🔴 **칠 표**(후속 지시 2026-10-14g §5) — 슬레이트 끝에 낼 단폴·다폴.

🔴🔴 **공격 계층은 문턱을 못 이겼다**(실효 측정 2026-10-14 · 1,470경기) —
   (가) 문턱만 **92.8%**(655개) ↔ (나) 살아남음만 92.5%(−0.3%p · 구간
   [−3.7, +3.1]) ↔ (다) 살아남음+약해짐 92.9%(+0.1%p). 공격이 **뺀 줄**의 실제
   적중률이 **93.2%** 로 남긴 줄(92.5%)보다 높았다.
🔴 그래서 지시대로(§1 마지막 줄) **공격은 "표시만"** 이고 칠 표는 **문턱만**으로
   고른다. ⚠️ `verdict`(살아남음·약해짐·무너짐)는 **표에 적기만** 한다.
🔴 §2 — 약해짐의 줄 적중률은 살아남음과 **차이가 없다**(93.4% ↔ 92.5% ·
   [−3.2, +5.0]) → 약해짐도 **통과**다(문턱을 더 올리지 않는다).
🔴 문턱은 **곡선에서만** 고른다(`var/accept/cut_curve.log`) —
   단폴 `CUT_SINGLE` · 다리 `CUT_LEG`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: 🔴 문턱 곡선(6,696경기 · 533일)에서 고른 수 — 단폴 0.88 → 백필 94.7%
CUT_SINGLE = 0.88
#: 🔴 다리 0.90 → 2폴 92.1% · 3폴 87.8%
CUT_LEG = 0.90
#: 🔴 같은 리그·같은 킥오프에서 **다리 최대 두 개**(§4)
SAME_MAX = 2
#: 🔴 다폴 다리 수
LEGS = (2, 3)


@dataclass
class Leg:
    """🔴 줄 하나 — 어느 경기의 어느 줄인가."""

    match: str = ""
    league: str = ""
    kickoff: str = ""
    line: str = ""
    p: float = 0.0
    side: str = ""            # 🔴 홈·원정·무·총골 — "전부 같은 방향" 금지에 쓴다
    verdict: str = ""         # 🔴 공격 판정(표시만)
    board: str = ""           # 🔴 보드 배당(계기판 · 판정 미사용)

    def said(self) -> str:
        return (f"{self.match} **{self.line}** {100 * self.p:.1f}%"
                + (f" · 공격 {self.verdict}" if self.verdict else "")
                + (f" · 보드 {self.board}" if self.board else ""))


@dataclass
class Out:
    singles: list = field(default_factory=list)
    parlays: list = field(default_factory=list)
    why: str = ""


def side_of(line: str) -> str:
    """🔴 그 줄이 **어느 방향**인가(다폴의 '전부 같은 방향 금지' 재료)."""
    said = str(line or "")
    if said.startswith("오버") or said.startswith("언더"):
        return "총골"
    if "away" in said or said.startswith("원정"):
        return "원정"
    if "home" in said or said.startswith("홈"):
        return "홈"
    if said.startswith("무"):
        return "무"
    return "기타"


#: 🔴🔴 **국내 보드에 흔한 기준선**(후속 지시 2026-10-14h §1) — 백필 문턱 곡선도
#:   이 줄들로만 다시 그렸다. ⚠️ 캡처에 추가 옵션이 오면 그 줄까지 늘어난다.
BOARD_COMMON = ("홈 승", "무", "원정 승",
                "핸디 home-0.5", "핸디 home+0.5", "핸디 home-1.5",
                "핸디 home+1.5", "핸디 away-0.5", "핸디 away+0.5",
                "핸디 away-1.5", "핸디 away+1.5",
                "오버 2.5", "언더 2.5", "오버 3.5", "언더 3.5")


def board_lines(board) -> tuple[set[str], str]:
    """🔴🔴 **그 경기 보드에 실제로 있는 줄 이름**(§1). 없으면 `(빈 집합, 사유)`.

    🔴 이름은 칠 표가 쓰는 꼴로 맞춘다 —
       · `win home|draw|away` → `홈 승`·`무`·`원정 승`
       · `handicap home P` → `핸디 home{+P}`(**보드 왼쪽 = 홈 기준** · 파서가
         `away` 쪽에 `-P` 를 함께 만든다)
       · `total over|under P` → `오버 P`·`언더 P`
    🔴 **정수 기준선**(±1·±2)은 국내 보드에서 **승·무·패 세 쪽**이다 — 조정 뒤
       동점이 `무` 로 따로 선다(밀어주기(push)가 아니다). 그래서 그 줄은
       `핸디 home+1 승`·`핸디 home+1 무` 두 이름으로 낸다.
       ⚠️ 이 규칙이 쓰는 보드와 다르면 `line_hit` 과 이 함수 **두 곳**만 고친다.
    """
    rows = list(getattr(board, "lines", None) or [])
    if not rows:
        return set(), "⬜ 보드 줄이 없다 — 칠 표에서 뺀다(표시만)"
    out: set[str] = set()
    for one in rows:
        market = str(getattr(one, "market", "") or "")
        side = str(getattr(one, "side", "") or "")
        point = getattr(one, "point", None)
        if market == "win":
            out.add({"home": "홈 승", "draw": "무",
                     "away": "원정 승"}.get(side, ""))
        elif market == "draw":
            # ⚠️ 파서는 무를 **`market="draw"` · `side=""`** 로 낸다(실측)
            out.add("무")
        elif market == "handicap" and point is not None:
            got = float(point)
            name = f"핸디 {side}{got:+g}"
            if float(got).is_integer():
                out.add(f"{name} 승")
                out.add(f"{name} 무")
            else:
                out.add(name)
        elif market == "total" and point is not None:
            got = float(point)
            if "over" in side:
                out.add(f"오버 {got:g}")
            elif "under" in side:
                out.add(f"언더 {got:g}")
    out.discard("")
    return out, (f"보드 줄 {len(out)}개" if out else
                 "⬜ 보드에서 읽은 줄이 없다")


def best_of(rows: list[dict]) -> list[Leg]:
    """🔴 경기마다 **한 줄만** 고른다(§4 *"경기당 1줄"*).

    🔴🔴 **보드에 있는 줄만** 후보다(§1) — `row["board_lines"]` 가 그 목록이고,
       비어 있으면 그 경기는 **칠 표에서 빠진다**(표시만).
    🔴🔴 **1단 기계 보류면 안 받는다**(의심 검증 v2 §2·§4) — 확신·역배 둘 다
       금지이고, 다폴 다리로도 못 쓴다(§5 *"기계 보류 다리 금지"*).
    """
    out: list[Leg] = []
    for one in rows or []:
        if one.get("machine_hold"):
            continue
        want = {str(x) for x in (one.get("board_lines") or [])}
        got = [(str(k), float(v)) for k, v in
               dict(one.get("lines") or {}).items()
               if v is not None and (not want or str(k) in want)]
        if want:
            got = [x for x in got if x[0] in want]
        else:
            got = []            # 🔴 보드가 없으면 **후보가 없다**(§1)
        if not got:
            continue
        line, p = max(got, key=lambda x: x[1])
        out.append(Leg(match=str(one.get("match") or ""),
                       league=str(one.get("league") or ""),
                       kickoff=str(one.get("kickoff") or ""),
                       line=line, p=p, side=side_of(line),
                       verdict=str(one.get("verdict") or ""),
                       board=str(one.get("board") or "")))
    return sorted(out, key=lambda x: -x.p)


def of(rows: list[dict]) -> Out:
    """🔴🔴 **칠 표** — `(단폴, 다폴)`. 아무것도 없으면 그 사실을 적는다."""
    legs = best_of(rows)
    singles = [x for x in legs if x.p >= CUT_SINGLE]
    pool = [x for x in legs if x.p >= CUT_LEG]
    parlays: list[list[Leg]] = []
    for n in LEGS:
        got = _pick_legs(pool, n)
        if got:
            parlays.append(got)
    # 🔴 §2 — **기계 보류**로 빠진 경기도 **이름으로** 적는다(조용히 빼지 않는다)
    held = [str(x.get("match") or "") for x in (rows or [])
            if x.get("machine_hold")]
    # ⚠️ 보류 경기는 **보류로만** 센다 — 보드까지 못 모았다고 두 번 적으면
    #    까닭이 흐려진다(보류가 **먼저**이고 그것이 그 경기를 뺀 이유다).
    no_board = [str(x.get("match") or "") for x in (rows or [])
                if not (x.get("board_lines") or [])
                and not x.get("machine_hold")]
    why = (f"경기 {len(rows)}개 → 보드 있는 경기 {len(rows) - len(no_board)}개 "
           f"→ 줄 {len(legs)}개 · 단폴 문턱 {CUT_SINGLE:.2f} 통과 "
           f"{len(singles)}개 · 다리 문턱 {CUT_LEG:.2f} 통과 {len(pool)}개"
           + (f" · 🔴 **보드 없어 뺀 경기 {len(no_board)}개**"
              f"({' · '.join(no_board[:4])})" if no_board else "")
           + (f" · 🔴 **1단 기계 보류로 뺀 경기 {len(held)}개**"
              f"({' · '.join(held[:4])})" if held else ""))
    if not singles:
        why += " · 🔴 **오늘 단폴 없음**"
    if not parlays:
        why += " · 🔴 **오늘 다폴 없음**"
    return Out(singles=singles, parlays=parlays, why=why)


def _pick_legs(pool: list[Leg], n: int) -> list[Leg]:
    """🔴 다리 고르기 — 같은 경기 금지 · 전부 같은 방향 금지 · 같은 리그·킥오프 최대 2."""
    got: list[Leg] = []
    for one in pool:
        if any(x.match == one.match for x in got):
            continue                                   # 🔴 같은 경기 금지
        same = sum(1 for x in got
                   if x.league == one.league and x.kickoff == one.kickoff)
        if same >= SAME_MAX:
            continue                                   # 🔴 같은 리그·킥오프 2
        got.append(one)
        if len(got) == n:
            break
    if len(got) < n:
        return []
    if len({x.side for x in got}) == 1:
        # 🔴 **전부 같은 방향 금지** — 한 줄을 다른 방향으로 바꿔 본다
        for one in pool:
            if any(x.match == one.match for x in got):
                continue
            if one.side != got[-1].side:
                got[-1] = one
                break
        else:
            return []
    return got if len({x.side for x in got}) > 1 else []


def said_of(out: Out) -> str:
    """🔴 슬레이트 끝에 찍는 글 — 표 두 줄과 사유."""
    rows = [f"🎯 **칠 표**(문턱만 · 공격은 표시) — {out.why}"]
    for one in out.singles:
        rows.append(f"- 단폴 — {one.said()}")
    for got in out.parlays:
        rows.append(f"- {len(got)}폴 — " + " + ".join(x.said() for x in got))
    return "\n".join(rows)
