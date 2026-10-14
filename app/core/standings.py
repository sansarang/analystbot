"""🔴🔴 **순위표 — 승점/경기 · 승률**(지시 2026-10-14 *"순위 및 승률을 가지고 와서
의심 단계를 만들어봐라"*).

H1(순위 동기)의 재료다. `config/doubt_vars.yaml` 의 H1 이 적고 있는 것:

> 결론이 **승점/경기 표와 반대쪽**이면 깨짐(체급 통제 뒤에도 남는다)
> (가) 유효 — 걸린 경기 적중 40.2% ↔ 53.1%(−12.9%p · [−19.5, −6.2])

## 🔴🔴 왜 이 파일이 필요했나
그 수를 **적합(`tools/fit_doubt.py`)만** 셀 수 있었다. 카드는 순위표가 없어
`유효 불리 의심 없다(묶음 0)` 로 지나갔다 — 즉 **의심 단계가 빈손으로 돌았다**
(2026-10-14 슬레이트 10경기 전부). 🔴 그래서 `domesticelo` 와 **같은 꼴**로
옮긴다: 이 파일이 원본이고 적합·운영이 같이 부른다(사본 금지).

## 🔴🔴 누설 금지 (C11)
`table_at(day)` 는 **그 날짜 앞 경기만** 쌓는다. 그 경기 결과가 그 경기의 순위표에
들어가면 미래를 보는 것이다 — 적합이 같은 규칙으로 쟀다(깃발을 세운 **뒤** 갱신).

## 🔴🔴 **빌리기 — 둘로 가른다**(실측 2026-10-14 · `var/accept/h1_borrow.log`)
컵·대륙 경기는 **그 대회 순위표가 없다**(J리그컵은 덤프에 아예 없다). 그래서 두
팀의 **국내 리그 표를 빌린다**. 🔴 지시 2026-10-14 가 *"검증 없는 빌리기 금지"*
이므로 빌린 줄을 재 봤더니 — **쓸 수 있는 줄이 2개**였다(백필이 거의 리그 경기라
빌릴 일이 없었다). 즉 **빌리기 자체는 못 쟀다.**

⚠️ 그래서 빌리기를 뜻으로 가른다:

| 빌린 모양 | 실제로 쓰는 표 | 판정 |
|---|---|---|
| **같은 리그**(J1 두 팀의 컵 경기) | 그 리그 표 — **쟨 것 그 자체** | 쓴다 |
| **다른 리그**(J1 ↔ KL1) | 승점/경기 **자가 다르다** | 🔴 표시만 |

## 🔴🔴 그리고 **리그마다 다르다** — 이것이 더 중요하다
H1 을 올릴 때 쓴 잣대는 *"전체 + **체급 통제** 뒤에도 남는다"* 였다. **리그**도
통제다. 리그별로 쪼개니:

```
전체          걸림 1696  38.1% ↔ 안 걸림 3948  54.4%   −16.3%p [−19.1, −13.5] ✅
league:ACLE   걸림   24  25.0% ↔ 안 걸림   47  61.7%   −36.7%p [−58.9, −14.5] ✅
league:J1     걸림   56  41.1% ↔ 안 걸림  182  48.9%    −7.8%p [−22.6,  +7.0] ⬜
league:KL1    걸림   77  42.9% ↔ 안 걸림  295  45.4%    −2.6%p [−15.0,  +9.9] ⬜
  (PD·PPL·BL1·DED·FL1·MLS·ELC·SA·PL 아홉은 전부 ✅)
```
🔴 **12 리그 중 10 에서 선다.** J1·KL1 은 ⬜ 지만 **구간이 전체 추정치(−16.3%)를
   품는다** — *"효과가 없다"* 가 아니라 *"표본이 얇아 확인을 못 한다"* 다.
   ⚠️ 그 둘을 섞어 말하지 않는다. 그래서 H1 은 **판정에 쓰고**, 그 리그가 개별로
   ⬜ 면 카드에 **그 사실을 같이 적는다**(`Flag.리그`).

⚠️ 덤프가 덮는 창 밖이면 ⬜ 다 — `league:J1` 은 2026-02-06 부터다. 모르는 것을
   0 으로 적지 않는다(#3 조용한 0 금지).
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: 🔴 한 팀이 이 경기 수를 넘겨야 표를 쓴다(적합이 쓴 그 문턱)
MIN_GAMES = 5

#: 🔴 빌릴 때 훑는 시즌 이름 — 덤프가 시즌을 리그마다 다르게 적는다
#   (`2026` · `2026/2027` 둘 다 나온다 · 실측)
SEASONS = ("2026/2027", "2026", "2025/2026", "2025")


@dataclass
class Row:
    """한 팀의 그 시점 성적."""

    team: str
    league: str
    season: str
    p: int = 0
    n: int = 0
    w: int = 0
    d: int = 0
    gf: int = 0
    ga: int = 0
    last: str = ""              # 🔴 그 표의 **마지막 경기 날짜**(지금 시즌 고르기)
    빌림: bool = False

    @property
    def ppg(self) -> float:
        return self.p / self.n if self.n else 0.0

    @property
    def wr(self) -> float:
        return self.w / self.n if self.n else 0.0

    def say(self) -> str:
        got = (f"{self.p}점/{self.n}경기 · **승점/경기 {self.ppg:.2f}** · "
               f"승률 {self.wr * 100:.0f}%({self.w}승 {self.d}무 "
               f"{self.n - self.w - self.d}패) · 득실 {self.gf}-{self.ga}")
        if self.빌림:
            got += f" · 🔴 **국내 리그 표를 빌렸다**(`{self.league}`)"
        return got


@dataclass
class Flag:
    """H1 깃발 — **불리/중립** 과 그 근거."""

    state: str = ""            # "불리" · "중립" · "" (못 쟀다)
    why: str = ""
    home: Row | None = None
    away: Row | None = None
    빌림: bool = False
    표시만: bool = False          # 🔴 다른 리그 표를 견줬다 — 판정에 안 쓴다
    리그: str = ""                # 🔴 두 팀이 같은 표일 때 그 리그
    rows: list = field(default_factory=list)

    def bad(self) -> bool:
        """🔴 **판정에 쓸 불리**. `표시만` 이면 불리라도 묶음에 넣지 않는다."""
        return self.state == "불리" and not self.표시만


def _dump() -> tuple[list[dict], str]:
    """🔴 `domesticelo` 와 **같은 덤프**를 읽는다(원천 하나 · 계약이 센다)."""
    from app.core import domesticelo
    return domesticelo.load()


def table_at(day: str = "", *, league: str = "", season: str = "") -> tuple[dict, str]:
    """🔴🔴 **그 날짜 앞까지의** 순위표. 열쇠는 `(리그, 시즌, 팀)` 이다.

    🔴 `day` 가 비면 덤프 전체다 — **운영은 늘 경기일을 준다**(누설 금지).
    """
    rows, why = _dump()
    got: dict[tuple, Row] = {}
    n_cut = 0
    for r in sorted(rows, key=lambda x: str(x.get("day") or "")):
        d = str(r.get("day") or "")
        if day and d >= str(day):
            n_cut += 1
            continue                      # 🔴🔴 누설 금지 — 그 날짜 **앞**만
        lg, se = str(r.get("league") or ""), str(r.get("season") or "")
        if league and lg != league:
            continue
        if season and se != season:
            continue
        hg, ag = r.get("hg"), r.get("ag")
        if hg is None or ag is None:
            continue
        hg, ag = int(hg), int(ag)
        for team, is_home in ((str(r.get("home") or ""), True),
                              (str(r.get("away") or ""), False)):
            if not team:
                continue
            one = got.setdefault((lg, se, team), Row(team=team, league=lg, season=se))
            won = (hg > ag) == is_home and hg != ag
            one.p += 3 if won else (1 if hg == ag else 0)
            one.n += 1
            one.w += int(won)
            one.d += int(hg == ag)
            one.gf += hg if is_home else ag
            one.ga += ag if is_home else hg
            one.last = max(one.last, d)
    return got, (why + f" · {day or '전체'} 앞 {len(got)}팀"
                 + (f" · 뒤 경기 {n_cut}건은 **뺐다**(누설 금지)" if n_cut else ""))


#: 🔴🔴 **리그별 H1 실측**(`var/accept/h1_borrow.log` · 2026-10-14) — 카드가
#   *"이 리그에서는 개별로 확인되지 않았다"* 를 적을 수 있게 들고 다닌다.
#   ⚠️ 값을 **판정에 쓰지 않는다**(문턱을 리그마다 바꾸지 않는다) — 글자용이다.
BY_LEAGUE: dict[str, tuple[float, float, float, int, bool]] = {
    # 리그: (차, 하한, 상한, 걸린 줄, 개별로 유효한가)
    "league:MLS": (-0.114, -0.189, -0.039, 252, True),
    "league:PD": (-0.205, -0.277, -0.133, 283, True),
    "league:PPL": (-0.246, -0.332, -0.160, 167, True),
    "league:DED": (-0.162, -0.248, -0.076, 182, True),
    "league:FL1": (-0.114, -0.201, -0.026, 185, True),
    "league:BL1": (-0.233, -0.323, -0.144, 152, True),
    "league:ELC": (-0.141, -0.239, -0.044, 158, True),
    "league:SA": (-0.202, -0.334, -0.069, 61, True),
    "league:PL": (-0.169, -0.280, -0.057, 99, True),
    "league:ACLE": (-0.367, -0.589, -0.145, 24, True),
    "league:KL1": (-0.026, -0.150, 0.099, 77, False),
    "league:J1": (-0.078, -0.226, 0.070, 56, False),
}

#: 🔴 전체 실측 — H1 이 걸린 줄의 봇 적중률과 그 차
ALL_FIT = (-0.163, -0.191, -0.135, 1696, 0.381, 0.544)

#: 🔴 "지금 시즌" 으로 받아 줄 최대 공백 — 그 리그 마지막 경기가 이보다 오래
#   전이면 **지금 시즌이 아니다**(옛 표를 지금으로 읽는 사고를 막는다)
STALE_DAYS = 120


def _days(a: str, b: str) -> int:
    """두 `YYYY-MM-DD` 사이 날짜 수. 못 읽으면 큰 수(= 낡았다)."""
    from datetime import date
    try:
        x = date(*[int(v) for v in str(a)[:10].split("-")])
        y = date(*[int(v) for v in str(b)[:10].split("-")])
    except (TypeError, ValueError):
        return 10 ** 6
    return abs((x - y).days)


def latest_of(box: dict, team: str, *, league: str, day: str = "") -> Row | None:
    """🔴 그 리그에서 그 팀의 **지금 시즌** 줄(`MIN_GAMES` 이상).

    ⚠️ 덤프가 같은 리그에 시즌을 두 이름으로 적는다(`league:J1` 에 `2026` 과
       `2026/2027` 이 **둘 다** 있다 — 원천이 football-data·fotmob 로 갈린다).
       🔴 그래서 시즌 이름을 **고르지 않고** 마지막 경기 날짜로 고른다.
    🔴🔴 그런데 그것만으로는 모자랐다 — **옛 시즌 표가 통과한다.** 실측 2026-10-14:
       비셀이 `league:ACLE` **2025/2026** 표(23점/12경기)로 잡혀 전북의 KL1
       **2026** 표와 견줘졌다. 🔴 그래서 `day` 가 있으면 그 리그 마지막 경기가
       `STALE_DAYS` 안이어야 **지금 시즌**으로 받는다.
    ⚠️ `day` 를 안 주면 그 검사를 **못 한다** — 운영은 늘 경기일을 준다.
    """
    got = [v for k, v in box.items()
           if k[0] == league and k[2] == team and v.n >= MIN_GAMES]
    if day:
        got = [v for v in got if _days(v.last, day) <= STALE_DAYS]
    return max(got, key=lambda r: (r.last, r.n)) if got else None


def pair_of(box: dict, home: str, away: str, *, league: str = "",
            day: str = "") -> tuple:
    """🔴🔴 **두 팀을 한 표에서** 찾는다. 섞어 비교하지 않는다.

    ① 이 경기 대회 표에 **둘 다** 있으면 그것.
    ② 아니면 **둘 다** 국내 리그 표로 빌린다(검증한 그 경로 · 모듈 머리의 ②).
    ③ 한쪽이라도 없으면 `(None, None, 사유)`.

    ⚠️ ① 과 ② 를 **한 경기에서 섞으면** 다른 대회의 승점/경기를 견주는 것이다 —
       ACLE 표 1.92 ↔ KL1 표 1.42 는 비교가 아니다. 적합도 섞지 않았다.
    """
    if league:
        a = latest_of(box, home, league=league, day=day)
        b = latest_of(box, away, league=league, day=day)
        if a is not None and b is not None:
            return a, b, f"이 대회 표(`{league}` · {a.season})"
    from app.core import domesticelo
    lg_a, _wa = domesticelo.league_of(home)
    lg_b, _wb = domesticelo.league_of(away)
    if not lg_a or not lg_b:
        miss = " · ".join(x for x, lg in ((home, lg_a), (away, lg_b)) if not lg)
        return None, None, f"🔴 국내 리그를 모른다 — {miss}"
    a = latest_of(box, home, league=lg_a, day=day)
    b = latest_of(box, away, league=lg_b, day=day)
    if a is None or b is None:
        miss = " · ".join(x for x, one in ((home, a), (away, b)) if one is None)
        return None, None, (f"🔴 국내 리그 표도 {MIN_GAMES}경기 미만이거나 덤프 창 "
                            f"밖이다 — {miss}")
    for one in (a, b):
        one.빌림 = True
    return a, b, (f"🔴 **국내 리그 표를 빌렸다** — {home} `{lg_a}`({a.season}) · "
                  f"{away} `{lg_b}`({b.season})")


def h1_of(*, home: str, away: str, pick: str, day: str = "",
          league: str = "", season: str = "") -> Flag:
    """🔴🔴 **H1 깃발** — 봇이 앞세운 쪽이 승점/경기가 **낮으면 불리**.

    `pick` 은 `"home"`·`"away"`·`""`(무) 다. 🔴 무를 앞세운 경기는 **중립**이다
    (적합도 `side` 가 빌 때 깃발을 안 세웠다 — 같은 규칙).
    """
    if pick not in ("home", "away"):
        return Flag(state="중립", why="⬜ 봇이 **무**를 앞세웠다 — 순위 동기를 못 가른다")
    box, why = table_at(day)
    a, b, said = pair_of(box, home, away, league=league, day=day)
    if a is None or b is None:
        return Flag(state="", why=f"{said} · {why}")
    mine, other = (a, b) if pick == "home" else (b, a)
    bad = mine.ppg < other.ppg
    borrowed = bool(a.빌림 or b.빌림)
    out = Flag(state="불리" if bad else "중립",
               home=a, away=b, 빌림=borrowed,
               rows=[f"{home} — {a.say()}", f"{away} — {b.say()}", f"표 — {said}"])
    cmp = "<" if bad else ("=" if mine.ppg == other.ppg else ">")
    out.why = (f"{'🔴 **불리**' if bad else '✅ 중립'} — 봇이 앞세운 "
               f"**{mine.team}** 승점/경기 {mine.ppg:.2f} {cmp} "
               f"{other.team} {other.ppg:.2f}")
    if bad:
        d0, lo0, hi0, n0, h_on, h_off = ALL_FIT
        out.why += (f" → 과거 이런 경기에서 봇 적중 **{h_on * 100:.1f}%**"
                    f"(안 걸린 경기 {h_off * 100:.1f}% · {d0 * 100:+.1f}%p"
                    f"[{lo0 * 100:+.1f}, {hi0 * 100:+.1f}] · 걸린 줄 {n0})")
    if borrowed:
        out.why += (f" · ⚠️ **국내 리그 표를 빌렸다**(이 대회 표가 {MIN_GAMES}경기 "
                    "미만 또는 낡았다)")
    if a.league != b.league:
        # 🔴🔴 승점/경기 자가 다르다 — 쟨 적 없다 → **표시만**
        out.표시만 = True
        out.why += (f" · 🔴🔴 **표시만** — 두 팀이 **다른 리그** 표다"
                    f"(`{a.league}` ↔ `{b.league}`) · 승점/경기 자가 다르고 "
                    "그렇게 견준 것을 **쟨 적이 없다** → 묶음에 넣지 않는다")
    # ── 🔴 그 리그에서 개별로 확인됐나(글자용 · 문턱은 안 바꾼다)
    lg = a.league if a.league == b.league else ""
    got = BY_LEAGUE.get(lg)
    if got:
        d, lo, hi, n, ok = got
        out.리그 = lg
        out.why += (f" · 📏 `{lg}` 실측 {d * 100:+.1f}%p"
                    f"[{lo * 100:+.1f}, {hi * 100:+.1f}] · 걸린 줄 {n}"
                    + ("" if ok else " · ⬜ **이 리그에서는 개별로 확인되지 "
                                     "않았다**(구간이 0 을 품는다 — 다만 전체 "
                                     f"추정치 {ALL_FIT[0] * 100:+.1f}% 를 품는다)"))
    elif lg:
        out.why += f" · ⬜ `{lg}` 는 **리그별 실측 판에 없다**"
    return out
