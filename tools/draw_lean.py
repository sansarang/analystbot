"""🔴🔴 **확률 측정 도구** — 지금 운영 엔진이 과거 경기에서 무엇을 내나.

```
PYTHONPATH=. uv run python tools/draw_lean.py --league 9080 \
    --name "K League 1" --short K1 --limit 10 --dump var/draw_lean.json
PYTHONPATH=. uv run python tools/draw_lean.py --match 5140052 --match 5140053
```

## 무엇을 재나 — 셋

```
① 쏠림 단계 → 실측 무 비율
② 기대 총골 ÷ 리그 기준 → 실측 무 비율
③ 변수 전수 — 확률에 닿았나 · 못 닿았으면 어느 문에서 걸렸나
```

⚠️ **재기만 한다.** 확률 경로를 건드리지 않는다.
🔴 `data/draw_bands/` 에 적지 않는다 — `core/drawband` 가 그 디렉터리를 **전부**
   읽어 가장 최근 판을 쓴다(실사고 2026-10-19: 내 측정 파일이 그 자리를 차지해
   카드의 `무 신뢰` 줄이 바뀌었다 · 계약 `test_v25_5_drawband` 가 잡았다).

## 2026-10-19 에 이 도구로 재서 나온 것

```
쏠림 → 무          0단계 0% · 1단계 50% · 2단계 50% · 3단계 0%   → 🔴 비단조
기대 총골(공격만)   ~0.5칸 40% ↔ 0.5~0.75칸 20%                 → 방향은 맞다
무 눈금            실측 30.0% ↔ 우리 평균 31.3%(K리그 10판)      → 크기는 맞다
해상도             최고 확률이 **네 값**(33.3·34.9·36.5·38.1)뿐
변수               129개 중 확률에 닿는 것 **26.4%**
```

🔴🔴 **해상도가 네 값인 까닭**(사용자 지적 2026-10-19) — **결함이 아니다.**
   **모든 경기가 같은 기준점(1/3 씩)에서 출발**하고 걸음 크기도 같다. 그러면
   나오는 수는 **걸음 수의 함수일 수밖에 없다.** 경기는 다른데 기준점이 안 다르다.
⚠️ 그리고 **변수를 더 넣으면 나아지지 않는다** — 문을 열어 변수를 전부 세게
   했더니 적중이 **9/14 → 6/14** 로 떨어졌다. 변수가 많을수록 **혼돈**이 늘었다.
   🔴 그래서 2026-10-19 에 **문을 닫은 채로 두기로** 정했다(후보 플래그는 전부
   되돌렸다 — `app/core/probmodel.py` 와 `config/m1v2.yaml` 은 그날 원래대로).

## 누설 — 무엇이 막히고 무엇이 새나

🔴 **막힌다** — 폼·직전 5경기·맞대결·골 시간은 `fotmob.before_as_of` 하나를
   지나고 그 `as_of` 는 **그 경기 킥오프**다(`s2_facts` 가 넘긴다 · 계약 L1).
🔴🔴 **샌다** — `core/ability` 가 읽는 선수 페이지 백분위는 **지금 시즌 누계**다.
   `core/asof.py` 가 `player_stats — 현재 값 · 재현 불가` 로 적어 뒀는데
   ⚠️ **그 표를 읽는 코드가 0** 이다(실측 2026-10-19 — 배선 안 된 표).
   영향: `squad_ability`·`branch_numbers`·`lineup_value`. 그래서 **최근 경기부터**
   센다(`--limit` 이 꼬리를 자른다) — 표는 **낙관 쪽으로 기운다**.

## 비용(실측 2026-10-19)

`Net(cache=True, day_cache=True)` 로 경기당 **13~41초**. ⚠️ `day_cache` 를 켜야
`/players/`(능력치)가 디스크 캐시에서 나온다 — 안 켜면 경기당 **2~3분**이다
(`_day_path` 첫 줄이 `if not self._day: return None` 이라, `cache=True` 만 주면
하루 캐시가 **통째로 꺼진다** — 그걸 모르고 *"빨라진다"* 고 먼저 말한 적 있다).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger("draw_lean")

#: 🔴 `flat_prob` 이 사유에 적는 글자 — **그 함수 하나가 원본이다**(사본 금지).
#   ⚠️ 쏠림을 여기서 다시 세지 않는다. 세면 규칙이 두 벌이 되고 한쪽만 고쳐진다.
_LEAN = re.compile(r"쏠림 (\d+)단계")

RESULTS = ("home", "draw", "away")


def _lean_of(why: str) -> int:
    """🔴 사유에서 **순 쏠림 단계**. ⚠️ 글자가 없으면 **0 단계**다.

    `flat_prob` 은 쏠림이 0 이면 그 줄을 **아예 안 적는다**(`if lean:`) — 글자가
    없는 것이 *"못 쟀다"* 가 아니라 양쪽이 상쇄됐다는 뜻이다.
    """
    got = _LEAN.search(str(why or ""))
    return int(got.group(1)) if got else 0


def _result_of(gh: int, ga: int) -> str:
    return "home" if gh > ga else ("draw" if gh == ga else "away")


def _top_of(p: dict) -> str:
    """🔴 그 확률의 **1위**. ⚠️ 동률이면 `tie`(1위를 지어내지 않는다)."""
    best = max(p.values())
    got = [k for k in RESULTS if abs(float(p[k]) - best) < 1e-9]
    return got[0] if len(got) == 1 else "tie"


# ══════════════════════════════════════════════════════════════════
# 🔴 **기대 총골** — 무의 1차 재료다(골이 적으면 무가 잦다)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 지금 확률 경로에 득점 자료가 닿는 길이 **0개**다 — `기대득점·λ·격자` 는
#     2026-10-17 에 지웠고 `S01`(두 팀 보정 득점·실점)은 2026-10-19 에 맥락으로
#     내렸다. 그래서 엔진 눈에 `포항 0-0` 과 `광주 4-3` 이 **구별이 없다**.
#  🔴 **수를 짓지 않는다**(#4) — 잰 값끼리 더하고 나누기만 한다. 재료는
#     `s5_verify` 가 쓰는 그 수다(`recent_trimmed_avg` · `_ga_avg`).
#  🔴 자는 **리그 기준 대비 비율**이다 — 보정 평균이 체계적으로 낮아(실측: 리그
#     기준 2.74 인데 잰 값 1.00~2.00) 절대값으로 자르면 한 칸에 다 몰린다.
def _goals_of(ref, facts) -> dict:
    """🔴 그 경기의 **기대 총골** 두 꼴 + 리그 기준 + 비율. 못 재면 `None`."""
    from app import rules as _rules
    from app.core.stages.s5_verify import _ga_avg, comp_kind
    box: dict = {}
    for side in ("home", "away"):
        key = str(getattr(ref, side, "") or "")
        one = facts.recent.get(key)
        one = dict(one) if isinstance(one, dict) else {}
        gf = one.get("recent_trimmed_avg")
        box[side] = {"gf": None if gf is None else float(gf),
                     "ga": _ga_avg(one),
                     "n": int(one.get("matches")
                              or len(one.get("last5") or []) or 0)}
    h, a = box["home"], box["away"]
    got: dict = {"home_gf": h["gf"], "home_ga": h["ga"], "home_n": h["n"],
                 "away_gf": a["gf"], "away_ga": a["ga"], "away_n": a["n"]}
    kind = comp_kind(ref, facts)
    share = _rules.goal_share(kind)
    got["kind"] = kind
    got["league_total"] = None if share is None else round(float(share) * 2, 4)
    if h["gf"] is not None and a["gf"] is not None:
        got["gf"] = round(h["gf"] + a["gf"], 3)
    if None not in (h["gf"], a["gf"], h["ga"], a["ga"]):
        got["mix"] = round((h["gf"] + a["ga"]) / 2
                           + (a["gf"] + h["ga"]) / 2, 3)
    lg = got.get("league_total")
    for key in ("gf", "mix"):
        v = got.get(key)
        got[f"{key}_r"] = (None if (v is None or not lg)
                           else round(float(v) / float(lg), 4))
    return got


#: 🔴 비율 구간 — ⚠️ **0.25 등간**이다(칸을 유리하게 짓지 않는다)
GOAL_BANDS = (0.5, 0.75, 1.0, 1.25)


def _band_of(value, bands=GOAL_BANDS) -> str:
    """🔴 그 수가 어느 칸인가. ⚠️ 못 쟀으면 `⬜`(0 으로 세지 않는다)."""
    if value is None:
        return "⬜ 못 쟀다"
    v = float(value)
    if v < bands[0]:
        return f"~{bands[0]:g}"
    for lo, hi in zip(bands, bands[1:], strict=False):
        if v < hi:
            return f"{lo:g}~{hi:g}"
    return f"{bands[-1]:g}~"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **변수가 확률에 닿았나 · 못 닿았으면 어느 문인가**(감사 2026-10-19)
# ══════════════════════════════════════════════════════════════════
#
#  🔴 **규칙을 베끼지 않는다**(#1) — 하는 일은 둘뿐이다:
#     ① `flat_prob` **사유 글자**에 그 변수 id 가 있나(= 닿았다)
#     ② 못 닿았으면 **변수 자신의 칸**과 **설정 표**를 보여 준다(그 표는
#        `flat_prob` 가 읽는 **그 표 그대로**다).
#  🔴 문은 **넷**이다 — ㉮ 기사(`from_doc`) · ㉯ 맥락 전용 · ㉰ 자리가 축·λ 가
#     아니다 · ㉱ 유형이 `by_var` 표에 없다. ⚠️ 한 변수가 **여러 문에 동시에**
#     걸린다 — 그래서 하나만 열면 아무것도 안 들어온다(실측).
def _gates() -> tuple[set, set]:
    """🔴 방향(`favors`·`goals`)을 받을 수 있는 **유형 목록**(설정 표 그대로)."""
    from app.core import routing as _rt
    box = dict(dict(_rt.table().get("lambda_rules") or {}).get("by_var") or {})
    f = {str(x) for x in (dict(box.get("favors") or {}).get("types") or [])}
    g = {str(x) for x in (dict(box.get("goals") or {}).get("types") or [])}
    return f, g


def _why_blocked(one, *, f_types: set, g_types: set) -> str:
    """🔴 그 변수가 **왜 확률에 못 닿았나**. ⚠️ 여러 문이면 **전부** 적는다."""
    from app.core import routing as _rt
    said: list[str] = []
    if bool(getattr(one, "from_doc", False)):
        said.append("㉮ 기사 변수")
    if bool(getattr(one, "context_only", False)):
        said.append("㉯ 맥락 전용")
    places = [str(x) for x in (getattr(one, "places", None) or [])]
    if not any(x in (*_rt.AXES, _rt.CONST) for x in places):
        said.append(f"㉰ 자리 {places or ['없다']}")
    kind = str(getattr(one, "type", "") or "")
    if kind not in f_types and kind not in g_types:
        said.append(f"㉱ 유형 `{kind}` 가 by_var 표에 없다")
    return " · ".join(said) or "⬜ 문에 안 걸렸다(방향이 없었다)"


async def _one(mid: str, *, net, league: str, short: str, state_cls,
               row: dict) -> dict | None:
    """🔴 경기 하나 → 한 줄. ⚠️ 못 재면 **사유를 담아** 돌려준다(#3).

    🔴 부르는 것은 **확률이 실제로 세는 것뿐**이다 — 검색·LLM 추출은 안 부른다
       (`flat_prob` 이 기사 변수를 건너뛴다 · 세지 않는 것을 받을 까닭이 없다).
    """
    from app import window as _w
    from app.collect import fotmob as fm
    from app.core import ability as _ab
    from app.core import backfill as bf
    from app.core import datavars as _dvar
    from app.core import probmodel as _pm
    from app.core import routing as _rt
    from app.core.schema import MatchRef
    from app.core.stages import s2_facts, s5_verify

    page = await net.get(fm.match_url(mid))
    j = fm.payload(getattr(page, "text", "") or "")
    if not j:
        return {"id": mid, "why": "경기 페이지를 못 읽었다"}
    score = bf.score_of(j)
    if score is None:
        return {"id": mid, "why": "최종 스코어가 없다(안 끝났거나 못 읽었다)"}
    gh, ga = score
    said_utc = str(row.get("utc") or "")
    try:
        kick = datetime.fromisoformat(said_utc.replace("Z", "+00:00"))
    except ValueError:
        return {"id": mid, "why": f"킥오프 꼴이 아니다({said_utc!r})"}
    if kick.tzinfo is None:
        kick = kick.replace(tzinfo=timezone.utc)
    # 🔴 시계를 킥오프로 되돌린다 — 폼·맞대결은 `as_of` 로도 막히지만 창(36시간)·
    #    신선도·`started` 는 **"지금"** 을 본다(오늘을 보면 과거 경기가 다 떨어진다).
    _w.set_clock(kick)
    try:
        ref = MatchRef(
            # 🔴 **접두가 있어야** fotmob 깊이가 열린다(`matchkey.source_of`)
            id=f"fotmob:{mid}", sport="soccer",
            competition=league, competition_short=short,
            # 🔴 팀 열쇠는 **꼴만** 맞으면 된다 — 짝은 **이름으로** 맞춘다
            home="team:000001", away="team:000002",
            home_name=str(row.get("home") or ""),
            away_name=str(row.get("away") or ""),
            kickoff_utc=kick)
        st = state_cls()
        facts = await s2_facts.run(ref, state=st, net=net)
        variables = s5_verify.run(ref, facts, [], [], state=st, turnover=None)
        said_sq, why_sq = await _ab.squad_fetch(net, facts, ref)
        var_dv, why_dv = _dvar.run(ref, facts, said_sq, state=st)
        if var_dv:
            variables = _dvar.one_fact_one_vote([*variables, *var_dv],
                                                state=st)
        varset = _rt.place(variables)
        said_g = _goals_of(ref, facts)
        prob, why = _pm.flat_prob(varset, ref=ref)
    finally:
        # 🔴 시계를 **반드시** 돌려놓는다(전역이다)
        _w.set_clock(None)
    f_types, g_types = _gates()
    said_vars = [{
        "id": str(getattr(v, "id", "") or ""),
        "type": str(getattr(v, "type", "") or ""),
        "favors": str(getattr(v, "favors", "") or ""),
        "goals": str(getattr(v, "goals", "") or ""),
        "weight": float(getattr(v, "weight", 0.0) or 0.0),
        "touched": f"[{getattr(v, 'id', '')}]" in why,
        "why": ("" if f"[{getattr(v, 'id', '')}]" in why
                else _why_blocked(v, f_types=f_types, g_types=g_types)),
    } for v in list(getattr(varset, "rows", None) or [])]
    push_h = why.count("] home ×")
    push_a = why.count("] away ×")
    said_p = {k: round(float(prob[k]), 6) for k in RESULTS}
    return {
        "id": mid, "home": ref.home_name, "away": ref.away_name,
        "kickoff": kick.isoformat(), "score": f"{gh}-{ga}",
        "result": _result_of(gh, ga), "lean": _lean_of(why),
        "p": said_p, "top": _top_of(said_p),
        "goals": said_g, "vars": said_vars,
        "n_var": len(said_vars), "n_push": push_h + push_a,
        "push_home": push_h, "push_away": push_a,
        "pair": min(push_h, push_a),
        "ability_n": len(said_sq or {}),
        "why_sq": why_sq[:120], "why_dv": why_dv[:120],
        "why_full": why, "why": "",
    }


def _table(rows: list[dict]) -> dict:
    """🔴🔴 **쏠림 단계 → 실측 무 비율**.

    🔴 칸마다 **경기 수를 함께** 적는다 — 비율만 적으면 표본 3건과 300건이 같아
       보인다(2026-10-19 규율: *"표본 수가 다르면 안 견준다"*).
    """
    box: dict[int, list[dict]] = defaultdict(list)
    for one in rows:
        box[int(one["lean"])].append(one)
    out: dict = {}
    for lean in sorted(box):
        mine = box[lean]
        n = len(mine)
        got = {k: sum(1 for x in mine if x["result"] == k) for k in RESULTS}
        p_draw = sum(float(x["p"]["draw"]) for x in mine) / n
        out[lean] = {"경기": n, "무": got["draw"],
                     "실측_무_비율": round(got["draw"] / n, 4),
                     "우리_무_확률_평균": round(p_draw, 4),
                     "차이": round(got["draw"] / n - p_draw, 4),
                     "홈": got["home"], "원정": got["away"]}
    return out


def _report_goals(rows: list[dict]) -> list[str]:
    """🔴 **기대 총골 ÷ 리그 기준 → 실측 무 비율**. 두 꼴을 나란히 낸다."""
    out = ["## 🔴 기대 총골(기준 대비) → 실측 무 비율"]
    if not rows:
        return [*out, "", "🔴 잰 경기가 없다."]
    said_lg = {str((x.get("goals") or {}).get("league_total"))
               for x in rows} - {"None"}
    out += ["", f"- 리그 기준(경기당 총골) — {' · '.join(sorted(said_lg)) or '⬜'}"]
    for key, label in (("gf_r", "공격만 (홈 득점 + 원정 득점) ÷ 기준"),
                       ("mix_r", "공수 섞음 ÷ 기준")):
        box: dict[str, list[dict]] = defaultdict(list)
        for one in rows:
            box[_band_of((one.get("goals") or {}).get(key))].append(one)
        out += ["", f"**{label}**", "",
                "| 기준 대비 | 경기 | 무 | 실측 무 비율 | 우리 무(평균) | 평균 비율 |",
                "|---|---|---|---|---|---|"]
        for band in sorted(box, key=lambda s: (s.startswith("⬜"), s)):
            mine = box[band]
            k = len(mine)
            got = sum(1 for x in mine if x["result"] == "draw")
            p = sum(float(x["p"]["draw"]) for x in mine) / k
            vals = [(x.get("goals") or {}).get(key) for x in mine]
            vals = [float(v) for v in vals if v is not None]
            said_r = f"{sum(vals) / len(vals):.2f}" if vals else "⬜"
            out.append(f"| {band} | {k} | {got} | **{got / k:.1%}** | "
                       f"{p:.1%} | {said_r} |")
    out += ["", "🔴 **보는 것** — 기준 대비 기대 총골이 **낮은 칸에서 무가 잦아야** "
                "한다(축구의 메커니즘). ⚠️ 그렇지 않으면 이 자도 버린다."]
    return out


def _report_vars(rows: list[dict]) -> list[str]:
    """🔴 **변수가 확률에 어떻게 닿나** — 문별 합계 + 유형별."""
    out = ["## 🔴 변수가 확률에 어떻게 닿나"]
    tot = sum(len(x.get("vars") or []) for x in rows)
    if not tot:
        return [*out, "", "🔴 변수가 없다."]
    hit = sum(1 for x in rows for v in (x.get("vars") or []) if v["touched"])
    gate: dict[str, int] = defaultdict(int)
    kind_t: dict[str, int] = defaultdict(int)
    kind_h: dict[str, int] = defaultdict(int)
    for x in rows:
        for v in (x.get("vars") or []):
            kind_t[v["type"]] += 1
            if v["touched"]:
                kind_h[v["type"]] += 1
                continue
            for g in str(v["why"]).split(" · "):
                gate[g.split("(")[0].strip()[:44]] += 1
    out += ["", f"- 변수 **{tot}개** 중 확률에 닿은 것 **{hit}개**"
                f"({100 * hit / tot:.1f}%)",
            "", "**걸린 문**(한 변수가 여러 문에 동시에 걸린다)", "",
            "| 문 | 건수 |", "|---|---|"]
    for k, v in sorted(gate.items(), key=lambda x: -x[1]):
        out.append(f"| {k} | {v} |")
    out += ["", "**유형별**", "", "| 유형 | 전체 | 닿음 |", "|---|---|---|"]
    for k, v in sorted(kind_t.items(), key=lambda x: -x[1]):
        out.append(f"| {k} | {v} | {kind_h[k]} |")
    return out


def _report(rows: list[dict], bad: list[dict], *, leagues: list[str]) -> str:
    """🔴 사람이 읽는 보고 — ⚠️ 못 잰 경기를 **이름으로** 적는다(#3)."""
    said: list[str] = []
    n = len(rows)
    said += [f"# 🔴 확률 측정 — 경기 **{n}건**", "",
             f"- 리그 {', '.join(leagues)}"]
    if bad:
        said.append(f"- 🔴 **못 쟨 경기 {len(bad)}건** — "
                    + " · ".join(f"`{x['id']}`({x['why']})" for x in bad[:6])
                    + (" …" if len(bad) > 6 else ""))
    else:
        said.append("- 못 쟨 경기 **0건**")
    if not rows:
        return "\n".join([*said, "", "🔴 **잰 경기가 없다** — 표를 만들지 않는다."])
    got_all = sum(1 for x in rows if x["result"] == "draw")
    said += [f"- 전체 실측 무 비율 **{got_all / n:.1%}**({got_all}/{n}) · "
             f"우리 무 확률 평균 "
             f"**{sum(float(x['p']['draw']) for x in rows) / n:.1%}**",
             f"- 적중(1위 기준) "
             f"**{sum(1 for x in rows if x['top'] == x['result'])}/{n}**"
             f"(동률 {sum(1 for x in rows if x['top'] == 'tie')}건은 1위가 없다)",
             "- ⚠️ 능력치(선수 페이지 백분위)는 **지금 시즌 누계**다 — "
             "이 표는 낙관 쪽으로 기운다(머리말 참조)"]
    # 🔴 해상도 — 기준점이 모든 경기에 같아서(1/3) 걸음 수의 함수다(머리말)
    tops = {round(max(x["p"].values()), 4) for x in rows}
    said += ["", f"- 🔴 **해상도** — 최고 확률이 **{len(tops)}가지 값**"
                 f"({100 * min(tops):.1f}% ~ {100 * max(tops):.1f}%) · "
                 f"⚠️ 기준점이 모든 경기에 같아서(1/3) 걸음 수의 함수다",
             "", "| 쏠림 | 경기 | 무 | 실측 무 비율 | 우리 무(평균) | 차이 |",
             "|---|---|---|---|---|---|"]
    for lean, one in _table(rows).items():
        said.append(f"| {lean}단계 | {one['경기']} | {one['무']} | "
                    f"**{one['실측_무_비율']:.1%}** | "
                    f"{one['우리_무_확률_평균']:.1%} | {one['차이']:+.1%} |")
    said += ["", "🔴 **읽는 법** — `차이` 가 꾸준히 `+` 면 우리가 무를 **덜** 주고 "
                 "있다는 뜻이다. ⚠️ 경기 수가 적은 칸은 견주지 않는다."]
    said += ["", *_report_goals(rows)]
    said += ["", *_report_vars(rows)]
    return "\n".join(said)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", action="append", default=[],
                    help="fotmob 리그 id(여러 번 가능)")
    ap.add_argument("--name", action="append", default=[],
                    help="그 리그의 대회 이름(`MatchRef.competition`)")
    ap.add_argument("--short", action="append", default=[],
                    help="짧은 이름(`competition_short`)")
    ap.add_argument("--match", action="append", default=[],
                    help="fotmob 경기 번호(여러 번 가능 · `--league` 대신). "
                         "🔴 두 팀·킥오프·대회 이름은 **페이지가** 든다")
    ap.add_argument("--limit", type=int, default=20,
                    help="리그마다 **최근** 끝난 경기 수(최근부터 — 누설이 적다)")
    ap.add_argument("--dump", default="",
                    help="경기별 줄을 JSON 으로 적는다. ⚠️ "
                         "`data/draw_bands/` 는 운영이 읽으므로 거부한다")
    args = ap.parse_args()
    from app.collect import fotmob as fm
    from app.core.state import RunState
    from app.net import Net

    if not args.league and not args.match:
        print("🔴 `--league` 나 `--match` 중 하나는 있어야 한다")
        return 2
    if "draw_bands" in str(args.dump):
        print(f"🔴 `{args.dump}` 는 **운영이 읽는 자리**다(`core/drawband`) — "
              f"측정 결과를 거기 적지 않는다. `var/` 아래로 주십시오.")
        return 2
    # 🔴 `day_cache=True` 가 있어야 `/players/` 가 디스크에서 나온다(머리말)
    net = Net(cache=True, day_cache=True)
    rows: list[dict] = []
    bad: list[dict] = []
    names: list[str] = []
    if args.match:
        names.append(f"번호로 집은 {len(args.match)}경기")
        for i, mid in enumerate(args.match, 1):
            mid = str(mid).strip()
            page = await net.get(fm.match_url(mid))
            j = fm.payload(getattr(page, "text", "") or "")
            if not j:
                bad.append({"id": mid, "why": "경기 페이지를 못 읽었다"})
                continue
            gen = (((j.get("props") or {}).get("pageProps") or {})
                   .get("general") or {})
            kick = fm.kickoff(j)
            one = {"id": mid,
                   "home": str((gen.get("homeTeam") or {}).get("name") or ""),
                   "away": str((gen.get("awayTeam") or {}).get("name") or ""),
                   "utc": kick.isoformat() if kick else "", "finished": True}
            said_comp = str(gen.get("leagueName") or "") or "?"
            try:
                said = await _one(mid, net=net, league=said_comp,
                                  short=said_comp[:8], state_cls=RunState,
                                  row=one)
            except Exception as exc:                        # noqa: BLE001
                bad.append({"id": mid, "why": f"터졌다 {exc!r:.80}"})
                print(f"   {i}/{len(args.match)} `{mid}` 🔴 터졌다 — "
                      f"{exc!r:.80}", flush=True)
                continue
            if said is None or said.get("why"):
                bad.append({"id": mid,
                            "why": (said or {}).get("why") or "사유 없음"})
                continue
            said["league"] = said_comp
            rows.append(said)
            print(f"   {i}/{len(args.match)} [{said_comp}] {said['home']} "
                  f"{said['score']} {said['away']} — 쏠림 {said['lean']}단계 "
                  f"· 홈 {said['p']['home']:.1%}/무 {said['p']['draw']:.1%}/"
                  f"원정 {said['p']['away']:.1%} · 변수 {said['n_var']}"
                  f"(민 것 {said['n_push']}) · 능력치 {said['ability_n']}명",
                  flush=True)
    for lid, name, short in zip(args.league, args.name, args.short,
                                strict=True):
        names.append(f"{name}({lid})")
        got = await fm.league_matches(net, lid)
        done = sorted([r for r in got if r.get("finished") and r.get("utc")],
                      key=lambda r: str(r["utc"]))[-int(args.limit):]
        print(f"[리그 {lid}] {name} — 끝난 경기 {len(done)}건을 잰다"
              f"(전체 {len(got)}건 중 **최근**)", flush=True)
        for i, one in enumerate(reversed(done), 1):
            mid = str(one.get("id") or "")
            if not mid:
                bad.append({"id": "?", "why": "경기 번호가 없다"})
                continue
            try:
                said = await _one(mid, net=net, league=name, short=short,
                                  state_cls=RunState, row=one)
            except Exception as exc:                        # noqa: BLE001
                bad.append({"id": mid, "why": f"터졌다 {exc!r:.80}"})
                print(f"   {i}/{len(done)} `{mid}` 🔴 터졌다 — {exc!r:.80}",
                      flush=True)
                continue
            if said is None or said.get("why"):
                bad.append({"id": mid,
                            "why": (said or {}).get("why") or "사유 없음"})
                continue
            rows.append(said)
            print(f"   {i}/{len(done)} {said['home']} {said['score']} "
                  f"{said['away']} — 쏠림 {said['lean']}단계 · "
                  f"무 {said['p']['draw']:.1%} · 변수 {said['n_var']}"
                  f"(민 것 {said['n_push']}) · 능력치 {said['ability_n']}명",
                  flush=True)
    print()
    print(_report(rows, bad, leagues=names))
    if args.dump:
        import json
        p = Path(args.dump)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"rows": rows, "bad": bad},
                                ensure_ascii=False, indent=1),
                     encoding="utf-8")
        print(f"\n🔴 경기별 줄을 적었다 — {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
