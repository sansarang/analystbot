"""🔴🔴 **백필 특징 만들기** — 상성 엔진 지시서(2026-10-10 여섯째) 3-5.

> 자료: 백필(K리그1·J1 두 시즌부터). 각 과거 경기에서 **S1·S1V·S2 를 "그 경기
> 킥오프 전 시각"으로 재현**해 특징을 만들고 스코어를 정답으로.
> **누설 금지**: 경기 m 특징에 **m 자신·이후 자료**가 들어가면 실패(C11).

🔴 특징을 만드는 함수는 **운영과 같은 것들**이다(사본 금지):
   축0 `matchup.axis0` 재료(선수 가치·호흡) · 축1 `form.form_of` ·
   축2 `style.profile_of`+`fire` · 축3 `goals.profile_of`+`fire`.
⚠️ **기사 변수(R)·새 사실은 백필에 없다** — 과거 경기의 기사를 다시 모으는 통로가
   없다(그 사실을 보고서가 적는다). 그래서 적합은 **구조 특징**으로만 한다.
"""
from __future__ import annotations

import re

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: 🔴 축1·축3 이 되짚는 경기 수(운영과 같다 — `s2e_matchup.BACK`)
BACK = 10
#: 🔴 특징을 만들려면 **그 팀의 과거 경기**가 이만큼은 있어야 한다
MIN_PRIOR = 3


@dataclass
class Row:
    """🔴 백필 한 줄 — 특징 + 정답(스코어). ⚠️ 못 만든 칸은 `None`(0 이 아니다)."""

    match_id: str = ""
    utc: str = ""
    league: str = ""
    home: str = ""
    away: str = ""
    goals_home: int = 0
    goals_away: int = 0
    #: 🔴 축별 표준화 차(홈 − 원정) — `matchup` 의 그 수와 같은 뜻이다
    gaps: dict = field(default_factory=dict)
    #: 🔴 리그 평균(한 팀 몫)·홈 배율 — S3 의 그 두 수
    mean: float | None = None
    home_mul: float = 1.0
    #: 🔴 못 만든 칸의 사유(#3)
    gaps_why: dict = field(default_factory=dict)

    def ok(self) -> bool:
        return self.mean is not None and bool(self.gaps)

    def as_dict(self) -> dict:
        return {"match_id": self.match_id, "utc": self.utc,
                "league": self.league, "home": self.home, "away": self.away,
                "goals_home": self.goals_home, "goals_away": self.goals_away,
                "gaps": dict(self.gaps), "mean": self.mean,
                "home_mul": self.home_mul, "gaps_why": dict(self.gaps_why)}


def score_of(j: dict) -> tuple[int, int] | None:
    """🔴🔴 그 경기의 **최종 스코어**. 못 읽으면 `None`.

    🔴🔴 **실사고 2026-10-12(코모 0-0 로마)**: 종전에는 **골 목록**으로만 셌다
       (`goals_of` 의 마지막 줄의 `after`). 🔴 그래서 **0-0 경기는 골이 없어
       `None`** 이 되고, 백필·재생·카드 채점에서 **통째로 빠졌다** — 무승부가
       구조적으로 덜 세졌다(실측: 그 표본의 무승부율이 실제보다 낮게 나왔다).
    🔴 그래서 **헤더의 최종 스코어**(`status.scoreStr`)를 1순위로 읽고, 골 목록은
       **그것이 없을 때만** 본다. ⚠️ 끝나지 않은 경기는 여전히 `None` 이다.
    """
    from app.collect import fotmob as fm
    page = ((j or {}).get("props") or {}).get("pageProps") or {}
    for box in (dict(page.get("header") or {}), dict(page.get("general") or {})):
        st = dict(box.get("status") or {})
        if not st.get("finished"):
            continue
        said = str(st.get("scoreStr") or "").strip()
        got = re.match(r"^(\d+)\s*-\s*(\d+)$", said.replace(" ", ""))
        if got:
            return int(got.group(1)), int(got.group(2))
    rows = fm.goals_of(j)
    if not rows:
        return None
    last = rows[-1].get("after")
    if not last or len(tuple(last)) != 2:
        return None
    return int(tuple(last)[0]), int(tuple(last)[1])


def features(j: dict, *, prior: dict, league_mean: float | None,
             home_mul: float = 1.0) -> tuple[dict, dict]:
    """🔴🔴 3-5 — 그 경기의 **축별 차**를 만든다. `(차, 사유)`.

    `prior` 는 **그 경기 킥오프 전**의 두 팀 경기 목록이다 —
    `{"home": [앞 경기 줄…], "away": […]}`. 🔴 **그 경기 자신은 들어 있지 않다**
    (C11 — 호출부가 그것을 보장하고 계약이 센다).
    한 줄 꼴은 `s2e_matchup._history` 가 만드는 것과 같다
    (`{home_name, away_name, mine_home, goals, stats}`).
    """
    from app.collect import fotmob as fm
    from app.core import form as _form
    from app.core import goals as _goals
    from app.core import matchup as _mu
    from app.core import style as _style
    lu = ((fm._page(j).get("content") or {}).get("lineup") or {})
    gaps: dict = {}
    why: dict = {}
    # ── 축0 — 선수 가치 로그합 + 호흡(과거 선발과 얼마나 겹치나)
    import math
    vals, fits = {}, {}
    for side, which in (("home", "homeTeam"), ("away", "awayTeam")):
        team = dict(lu.get(which) or {})
        rows = fm.players_of(team)
        # 🔴🔴 **가치 0 합산 금지**(사용자 지시 2026-10-12 1번) — 운영(`axis0`)과
        #    **같은 문**을 지난다(사본 금지). ⚠️ 백필이 다른 재료를 보면 적합이
        #    운영과 다른 모형을 맞춘다.
        from app.core import playervalue as _pv
        said_fill, _why = _pv.fill(rows)
        got_sum, _n = _pv.log_sum(said_fill)
        vals[side] = got_sum
        names = {r["name"] for r in rows}
        past = prior.get(side) or []
        hit = [len(names & {str(x) for x in (one.get("starters") or [])})
               for one in past]
        fits[side] = (sum(hit) / len(hit) / max(1, len(names)) * len(names)
                      if hit else 0.0)
    conf = dict(_mu.table().get("axis0") or {})
    if vals["home"] is not None and vals["away"] is not None:
        w = float(conf.get("together_weight") or 0.0)
        gaps["axis0"] = round(((vals["home"] + w * fits["home"])
                               - (vals["away"] + w * fits["away"]))
                              / float(conf.get("scale") or 1.0), 4)
    else:
        why["axis0"] = "🔴 선수 가치가 없다"
    # ── 축1 — 보정 폼(과거 경기만)
    forms = {}
    for side in ("home", "away"):
        rows = prior.get(side) or []
        if len(rows) < MIN_PRIOR:
            why["axis1"] = f"🔴 과거 경기 {len(rows)}건(<{MIN_PRIOR})"
            break
        said = [{"gf": r["gf"], "ga": r["ga"], "opp": r.get("opp") or ""}
                for r in rows[-BACK:]]
        forms[side] = _form.form_of(side, said, elo={})
    if len(forms) == 2:
        a, b = forms["home"].index(), forms["away"].index()
        if a is not None and b is not None:
            gaps["axis1"] = round((float(a) - float(b))
                                  / float(dict(_mu.table().get("axis1") or {})
                                          .get("scale") or 1.0), 4)
        else:
            why["axis1"] = "🔴 폼 지수를 못 셌다"
    # ── 축2·축3 — 스타일·골 내용(과거 경기 목록으로)
    box = {"style": {}, "fired2": [], "off": {}, "fired": [], "profile": {}}
    rows_ok = all(len(prior.get(s) or []) >= MIN_PRIOR
                  for s in ("home", "away"))
    if rows_ok:
        shaped = {s: [{"home_name": r.get("home_name"),
                       "away_name": r.get("away_name"),
                       "mine_home": r.get("mine_home"),
                       "goals": r.get("goals") or [],
                       "stats": r.get("stats") or {}}
                      for r in (prior.get(s) or [])[-BACK:]]
                  for s in ("home", "away")}
        styles = {s: _style.profile_of(s, shaped[s]) for s in ("home", "away")}
        prof = {s: _goals.profile_of(s, shaped[s]) for s in ("home", "away")}
        box["style"] = styles
        box["fired2"] = _style.fire(styles["home"], styles["away"], off={})
        box["profile"] = prof
        box["fired"] = _goals.fire(prof["home"], prof["away"], rest={})
        gaps["axis2"] = _mu.axis2(box, None).gap or 0.0
        gaps["axis3"] = _mu.axis3(box, None, r={}).gap or 0.0
    else:
        why["axis2"] = why["axis3"] = "🔴 과거 경기가 모자라다"
    return gaps, why
