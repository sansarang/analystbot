"""🔴🔴 **§7 경기 직전 상태** — 지시서 2026-10-12(둘째) §7.

> `ContextRow{rest_days · load_14d · cup_4d · break_days ·
> league_n_since_break · travel_km · form3 · streak_len·kind}`
> 전부 `before_as_of` 를 지난 목록에서(리그+컵+대표팀 차출 기간 포함).

🔴 왜 — 실사고 둘(광주 4-3 울산 · 가와사키 1-2 나고야)에서 봇은 **과거 성적**만
   보고 *"경기 직전 상태"* 를 몰랐다: 광주는 **3주 휴식 후 홈**, 가와사키는
   **직전 컵 일정**. 그 둘은 과거 성적표에 **안 적혀 있다**.
🔴 이 모듈은 **수를 만들 뿐 확률을 바꾸지 않는다** — λ 에 들어갈지는 §9 전진
   선택이 정한다(계약 S1). ⚠️ `streak_*` 은 **검증 전용**이다(§12 · C12-1).
🔴 누설 금지(C7-1) — 문은 `fotmob.before_as_of` 하나다.
⚠️ `travel_km` 은 **구장 좌표 표가 없으면 ⬜**다(지어내지 않는다 · #3).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

#: 🔴 rest 를 자르는 상한(일) — 지시 §7(`clip(rest, 0, 10)`)
REST_CAP = 10

#: 🔴 부하 창(일) · 컵 창(일) — 지시가 적은 수
LOAD_DAYS = 14
CUP_DAYS = 4

#: 🔴 휴식기로 보는 길이(일) — `pb_home` 의 기준(§7)
BREAK_DAYS = 14

#: 🔴 폼 창 — 최근 리그 **3경기 승점**(최대 9점으로 나눈다)
FORM_N = 3

# 🔴 컵 판정은 `app/core/level.is_cup` **하나다**(사본 금지 · #1) — 그 표가
#    `CUP_WORDS` 를 든다. ⚠️ 여기서 대회 이름을 다시 적지 않는다.


@dataclass
class ContextRow:
    """🔴 그 팀의 경기 직전 상태 한 줄. ⚠️ 못 잰 칸은 `None`(⬜)이다."""

    team: str = ""
    as_of: object = None
    rest_days: int | None = None
    load_14d: int = 0
    cup_4d: bool = False
    break_days: int | None = None
    league_n_since_break: int = 0
    travel_km: float | None = None
    form3: float | None = None
    streak_len: int = 0
    streak_kind: str = ""
    n_used: int = 0
    why: str = ""

    def full(self) -> bool:
        """🔴 §13 InfoQ 가 묻는다 — 휴식·부하가 **둘 다** 있나."""
        return self.rest_days is not None


def _is_cup(row: dict) -> bool:
    """🔴 그 줄이 **컵**인가 — `comp` 가 있으면 그것, 없으면 대회 이름을 본다.

    🔴 판정은 `level.is_cup` 하나다(사본 금지). ⚠️ `comp: "cup"` 처럼 어댑터가
       꼴을 적어 주면 그 글자가 이긴다.
    """
    from app.core import level as _lv
    said = str(dict(row).get("comp") or dict(row).get("league") or "")
    return _lv.is_cup(said) or said.strip().lower() == "cup"


def row_of(team: str, rows: list[dict], *, as_of) -> ContextRow:
    """🔴🔴 §7 — 그 팀의 `ContextRow`. **`as_of` 이전 경기만** 본다(C7-1).

    `rows` 는 `{utc, comp, gf, ga}` 꼴이다. ⚠️ `comp` 는 어댑터가 적은 대회 꼴
    (`league`·`cup`)이고 **여기서 이름을 추측하지 않는다**.
    """
    from app.collect import fotmob as fm
    said = fm.before_as_of(list(rows or []), as_of=as_of, key="utc")
    got = ContextRow(team=str(team), as_of=as_of, n_used=len(said))
    if not said:
        got.why = "⬜ **지난 경기가 없다** — 휴식·부하를 셀 수 없다(⬜ 이동거리도)"
        return got
    rows_ok: list[tuple] = []
    for r in said:
        got_when = datetime.fromisoformat(str(r["utc"]).replace("Z", "+00:00"))
        # 🔴 절대규칙 2 — **tz 없는 값은 받지 않는다**(naive 가 새면 날짜가 조용히
        #    기계 시간대로 바뀐다). ⚠️ `before_as_of` 를 이미 지났지만 **여기서도**
        #    확인한다(계약 `test_fromisoformat_뒤에_tz_를_확인한다`).
        if got_when.tzinfo is None:
            continue
        rows_ok.append((got_when, r))
    when = sorted(rows_ok)
    got.n_used = len(when)
    if not when:
        got.why = "⬜ **쓸 수 있는 지난 경기가 없다**(시간대 없는 줄은 버렸다)"
        return got
    # 🔴 **달력 날짜 차**로 센다 — 축구에서 *"3일 쉬었다"* 는 토→화를 뜻한다.
    #    ⚠️ 시각 차(66시간 = 2.8일)로 세면 그 말과 어긋난다.
    def _gap(w) -> int:
        return (as_of.date() - w.date()).days

    last_when, _last = when[-1]
    got.rest_days = _gap(last_when)
    got.load_14d = sum(1 for w, _r in when if _gap(w) <= LOAD_DAYS)
    got.cup_4d = any(_is_cup(r) for w, r in when if _gap(w) <= CUP_DAYS)
    league = [(w, r) for w, r in when if not _is_cup(r)]
    if league:
        got.break_days = _gap(league[-1][0])
        # 🔴 휴식기(BREAK_DAYS 이상) **뒤에 치른 리그 경기 수**
        gap = 0
        for i in range(len(league) - 1, 0, -1):
            if (league[i][0] - league[i - 1][0]).days >= BREAK_DAYS:
                gap = len(league) - i
                break
        got.league_n_since_break = (0 if got.break_days >= BREAK_DAYS else gap)
        # 🔴 최근 리그 FORM_N 경기 승점(0~1 로 눌러 담는다)
        take = league[-FORM_N:]
        pts = sum(3 if int(r["gf"]) > int(r["ga"])
                  else (1 if int(r["gf"]) == int(r["ga"]) else 0)
                  for _w, r in take)
        got.form3 = pts / (3.0 * FORM_N)
        # 🔴 연속 기록 — **검증 전용**(§12 · 확률에 안 들어간다)
        kind = ""
        for _w, r in reversed(take if len(take) == len(league) else league):
            said_one = ("승" if int(r["gf"]) > int(r["ga"])
                        else ("무" if int(r["gf"]) == int(r["ga"]) else "패"))
            if not kind:
                kind = said_one
            if said_one != kind:
                break
            got.streak_len += 1
        got.streak_kind = kind
    parts = [f"휴식 {got.rest_days}일(직전 공식 경기)",
             f"14일 내 {got.load_14d}경기",
             ("4일 내 컵 **있다**" if got.cup_4d else "4일 내 컵 없다")]
    if got.break_days is not None:
        parts.append(f"직전 리그부터 {got.break_days}일 · 휴식기 뒤 리그 "
                     f"{got.league_n_since_break}경기")
    if got.form3 is not None:
        parts.append(f"최근 {FORM_N}경기 승점 {got.form3:.2f}"
                     f"(연속 {got.streak_kind}{got.streak_len} · 검증용)")
    parts.append("⬜ 이동거리 — 구장 좌표 표가 없다(지어내지 않는다)")
    got.why = " · ".join(parts)
    return got


def covariates(home: ContextRow, away: ContextRow) -> dict:
    """🔴🔴 §7 — ⑬ 이 받는 **홈 − 원정** 공변량. ⚠️ `streak` 은 **넣지 않는다**.

    `{rest_d, load_d, cup_d, pb_home, form3_d}` — 못 잰 칸은 **0**이고 그 사실을
    `why` 가 아니라 **`missing`** 이 든다(조용한 0 금지 · #3).
    """
    def _clip(v) -> float:
        return 0.0 if v is None else max(0.0, min(float(REST_CAP), float(v)))

    miss = [n for n, v in (("홈 휴식", home.rest_days),
                           ("원정 휴식", away.rest_days)) if v is None]
    pb = 0
    for one in (home, away):
        if (one.break_days is not None and one.break_days >= BREAK_DAYS
                and one.league_n_since_break == 0):
            pb = 1
            break
    return {
        "rest_d": _clip(home.rest_days) - _clip(away.rest_days),
        "load_d": int(home.load_14d) - int(away.load_14d),
        "cup_d": int(bool(home.cup_4d)) - int(bool(away.cup_4d)),
        "pb_home": pb,
        "form3_d": (float(home.form3 or 0.0) - float(away.form3 or 0.0)),
        "missing": miss,
    }
