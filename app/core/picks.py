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
#:
#:  🔴 **핸디·총점 줄은 이 자를 쓰지 못한다**(지시 2026-10-14 3번) — 봇 핸디
#:     확률의 AUC 가 0.511 이라 줄을 못 세운다(`tools/ah_cause.py`).
#:     ⚠️ 이 잠금은 **의심 단계가 걷힌 뒤에도 유지한다** — 근거는 보정표가
#:        아니라 그 실측이다(`docs/fable/archive/doubt_v2/ah_cause.log`).
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
    verdict: str = ""         # 🔴 2단 판정(확신·역배) · 없으면 빈 글자
    board: str = ""           # 🔴 보드 배당(계기판 · 판정 미사용)
    #: 🔴🔴 **의심 후 확률**(§4) — 있으면 `p` 가 이 수다(자가 다르다)
    after: float | None = None
    #: 🔴 그 칸(구간·경기 수) — 어디서 온 수인지 표에 적는다
    cell: str = ""

    def said(self) -> str:
        return (f"{self.match} **{self.line}** {100 * self.p:.1f}%"
                + (f"(의심 후 · 칸 {self.cell})" if self.after is not None
                   else "")
                + (f" · **{self.verdict}**" if self.verdict else "")
                + (f" · 보드 {self.board}" if self.board else ""))


@dataclass
class Out:
    singles: list = field(default_factory=list)
    parlays: list = field(default_factory=list)
    #: 🔴🔴 **표시만 줄**(후속 지시 2026-10-14 2번) — 봇 원확률로는 후보가 안 되고
    #:    의심 후 칸도 서지 않은 핸디·언오버 줄. **칠 표에 적되 고르지 않는다**.
    #:    ⚠️ 조용히 버리면 *"그 줄을 안 봤다"* 와 구별되지 않는다(#3).
    shown: list = field(default_factory=list)
    why: str = ""


def grid_of(box: dict) -> dict:
    """🔴🔴 상성 묶음 → **스코어 격자**. 열쇠 꼴이 두 가지라 둘 다 받는다.

    ⚠️ 판에 적힐 때는 `"2-1"` 이고 메모리에서는 `(2, 1)` 이다 — 한 꼴만 받으면
       한쪽 길에서 조용히 **빈 격자**가 된다.
    """
    said = dict(box or {})
    rows = dict((said.get("sim") or {}).get("scores")
                or getattr(said.get("prob"), "scores", None) or {})
    out: dict = {}
    for key, val in rows.items():
        if isinstance(key, str) and "-" in key:
            h, a = key.split("-", 1)
            out[(int(h), int(a))] = float(val)
        elif isinstance(key, (tuple, list)) and len(key) == 2:
            out[(int(key[0]), int(key[1]))] = float(val)
    return out


def lines_of(grid: dict) -> dict:
    """🔴🔴 격자 → **줄 이름 → 확률**. 이름 꼴은 `board_lines` 와 같아야 한다.

    🔴 이 함수가 **하나**인 까닭 — 슬레이트(`tools/slate_queue`)와 파이프라인
       (2단 의심)이 **같은 이름**으로 줄을 불러야 보드 줄과 맞물린다(사본 금지).
    ⚠️ 마켓은 `probfloor.markets_of` 그 격자에서 센다.
    """
    from app.core import probfloor as _pf
    if not grid:
        return {}
    mk = _pf.markets_of(dict(grid))
    out = {"홈 승": mk.get("home"), "무": mk.get("draw"),
           "원정 승": mk.get("away")}
    for key, val in dict(mk.get("ah") or {}).items():
        out[f"핸디 {key}"] = val
    for key, val in dict(mk.get("over") or {}).items():
        out[f"오버 {key}"] = val
        out[f"언더 {key}"] = 1.0 - float(val)
    return out


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


def best_of(rows: list[dict]) -> tuple[list[Leg], list[tuple]]:
    """🔴 경기마다 **한 줄만** 고른다(§4 *"경기당 1줄"*).

    🔴🔴 **보드에 있는 줄만** 후보다(§1) — `row["board_lines"]` 가 그 목록이고,
       비어 있으면 그 경기는 **칠 표에서 빠진다**(표시만).
    🔴🔴 **1단 기계 보류면 안 받는다**(의심 검증 v2 §2·§4) — 확신·역배 둘 다
       금지이고, 다폴 다리로도 못 쓴다(§5 *"기계 보류 다리 금지"*).

    돌려주는 것은 `(다리들, 표시만 줄들)` 이다 — **표시만** 은 핸디·언오버 중
    후보가 못 된 줄이고, 표 끝에 적되 **고르지 않는다**(지시 2026-10-14 2번).
    """
    out: list[Leg] = []
    #: 🔴 **표시만** 으로 남길 줄(핸디·언오버 · 지시 2026-10-14 2번)
    shown: list[tuple] = []
    #: 🔴 보드 없이 **표준 줄**로 고른 경기(칠 표가 그 사실을 적는다)
    no_board_rows: list[str] = []
    for one in rows or []:
        if one.get("machine_hold"):
            continue
        want = {str(x) for x in (one.get("board_lines") or [])}
        # 🔴 보드가 없으면 **어느 길로 가든** 그 사실을 적는다(지시 "보드없이 진행")
        if not want:
            no_board_rows.append(str(one.get("match") or ""))
        got = [(str(k), float(v)) for k, v in
               dict(one.get("lines") or {}).items()
               if v is not None and (not want or str(k) in want)]
        if want:
            got = [x for x in got if x[0] in want]
        else:
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **보드가 없으면 표준 줄로 간다** — 사용자 지시 2026-10-14
            #    *"보드없이 진행해라"*
            # ══════════════════════════════════════════════════════════
            #
            #  ⚠️ §1 은 *"보드에 있는 줄 안에서만"* 이었다 — 직접 지시가 이긴다.
            #  🔴 표준 줄은 `BOARD_COMMON`(국내 보드에 흔한 기준선) 이고, 그 중
            #     **승무패만** 판정으로 간다 — 핸디·언오버 칸은 *그 경기 보드의
            #     메인 라인 하나*로 쟀으므로 보드 없는 줄에 붙이면 거짓이 된다
            #     (아래 핸디·총점 잠금이 그것을 막는다 · AUC 0.511).
            got = [x for x in got if x[0] in BOARD_COMMON]
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **봇 원래 핸디·총점 확률은 판정에 쓰지 않는다**(지시 3번)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 실측 2026-10-14(`var/accept/ah_cause.log`): 보드 메인 핸디의 실제
        #     커버율은 **50.0%**(1,321줄)이고 봇 확률의 **AUC 가 0.511** 이다 —
        #     **줄을 세우지 못한다**(언오버는 0.496). 보정표에서도 70%+ 칸이
        #     실측 **51.0%** 였다. 🔴 그 수로 문턱을 넘기면 **거짓 확신**이다.
        #  🔴 그래서 핸디·총점 줄은 **후보가 아니다** — 표시만으로 남긴다.
        # 🔴 후보가 못 되는 핸디·언오버는 **표시만** 으로 남긴다(지시 2번) —
        #    조용히 버리면 *"그 줄을 안 봤다"* 와 구별되지 않는다(#3).
        shown += [(str(one.get("match") or ""), x[0], x[1]) for x in got
                  if str(x[0]).startswith(("핸디", "오버", "언더"))]
        got = [x for x in got if not str(x[0]).startswith(
            ("핸디", "오버", "언더"))]
        if not got:
            continue
        line, p = max(got, key=lambda x: x[1])
        out.append(Leg(match=str(one.get("match") or ""),
                       league=str(one.get("league") or ""),
                       kickoff=str(one.get("kickoff") or ""),
                       line=line, p=p, side=side_of(line),
                       verdict=str(one.get("verdict") or ""),
                       board=str(one.get("board") or "")))
    return sorted(out, key=lambda x: -x.p), shown, no_board_rows


def of(rows: list[dict]) -> Out:
    """🔴🔴 **칠 표** — `(단폴, 다폴)`. 아무것도 없으면 그 사실을 적는다."""
    legs, shown, no_board_rows = best_of(rows)
    # 🔴🔴 **자가 둘이다** — 2단 판정이 붙은 줄은 그 판정이 문턱을 이미 걸었고,
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
    # 🔴 보드 없는 경기는 이제 **빠지지 않는다**(표준 줄로 간다) — 그 사실만 적는다
    no_board = list(dict.fromkeys(no_board_rows))
    why = (f"경기 {len(rows)}개 → 보드 있는 경기 {len(rows) - len(no_board)}개 "
           f"· 보드 없이 표준 줄 {len(no_board)}개 "
           f"→ 줄 {len(legs)}개 · 단폴 **{len(singles)}개**(2단 판정 또는 봇 "
           f"원확률 {CUT_SINGLE:.2f} 이상) · 다리 후보 {len(pool)}개"
           + (f" · ⚠️ **보드 없음 — 표준 줄로 골랐다 {len(no_board)}개**"
              f"({' · '.join(no_board[:4])})" if no_board else "")
           + (f" · 🔴 **1단 기계 보류로 뺀 경기 {len(held)}개**"
              f"({' · '.join(held[:4])})" if held else "")
)
    if not singles:
        why += " · 🔴 **오늘 단폴 없음**"
    if not parlays:
        why += " · 🔴 **오늘 다폴 없음**"
    return Out(singles=singles, parlays=parlays, why=why,
               shown=list(shown))


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
    """🔴🔴 슬레이트 끝에 찍는 글 — **단폴 · 다폴**.

    🔴 **의심 단계는 걷혔다**(지시 2026-10-14) — 확신/보류/역배 등급도 함께
       사라졌다. 문턱은 **봇 원확률 자** 하나다(`CUT_SINGLE`·`CUT_LEG`).
    """
    rows = [f"🎯 **칠 표** — {out.why}"]
    for one in out.singles:
        rows.append(f"- 단폴 — {one.said()}")
    for got in out.parlays:
        rows.append(f"- {len(got)}폴 — " + " + ".join(x.said() for x in got))
    # 🔴🔴 **표시만**(지시 2026-10-14 2번) — 봇 원확률을 판정에 쓸 수 없는
    #    핸디·언오버 줄(AUC 0.511). 조용히 버리지 않는다(#3).
    if out.shown:
        top = sorted(out.shown, key=lambda x: -float(x[2]))[:6]
        rows.append("- 📋 **표시만**(핸디·언오버 — 봇 원확률은 판정에 안 쓴다 · "
                    f"{len(out.shown)}줄): "
                    + " · ".join(f"{m} {ln} {100 * p:.0f}%"
                                 for m, ln, p in top))
    return "\n".join(rows)
