"""🔴🔴 **백필 보드**(의심 검증 통합본 v2 · 2026-10-14i §1-4 · 인계 §2-1).

```
PYTHONPATH=. uv run python tools/fit_board_hist.py            # 백필이 있는 리그·시즌 전부
PYTHONPATH=. uv run python tools/fit_board_hist.py --league league:ELC
```

> 과거 마감 배당 공개 데이터셋을 리그별로 확보해 **"그 경기의 보드 한 줄"**로 쓴다.
> 원천 없는 리그·시즌은 **봇 확률로 양쪽 50%에 가장 가까운 0.5 단위 기준선**
> (근사) · `근사 보드` 표시 · 판정표는 실보드 표본과 **따로** 집계.

🔴 원천 표는 `config/competitions.yaml` 의 `sources.football_data_hist` 다
   (코드에 박지 않는다 · 그 파일 머리말이 꼴을 적고 있다).
🔴 **마감 배당**을 쓴다 — `B365C*`·`AHCh`(`C` = closing). 개장가는 보드가 아니다.
🔴 근사 기준선은 `probfloor.score_grid` + `markets_of` **그 함수**로 센다
   (봇이 카드에서 쓰는 격자와 같은 수여야 한다 · 사본 금지).
⚠️ 이름 맞춤은 `teamname.pick` 하나다. **못 붙인 이름은 이름으로 남긴다**(#3) —
   조용히 버리면 백필 표본이 소리 없이 줄어든다.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / "data/board_hist"
JUDGE = ROOT / "var/judge"
BASE = "https://www.football-data.co.uk"

#: 🔴 국내 보드 언오버 기준선 — `boardfeed.TOTAL_LINES` 와 **같은 표**를 본다
#   (사본 금지: 거기서 가져온다).


def season_code(season: str) -> str:
    """🔴 `2025/2026` → `2526`(mmz4281 의 시즌 폴더). 한 해짜리는 빈 글자."""
    got = [x for x in str(season or "").replace("-", "/").split("/") if x]
    if len(got) != 2:
        return ""
    try:
        y1, y2 = int(got[0]), int(got[1])
    except ValueError:
        return ""
    return f"{y1 % 100:02d}{y2 % 100:02d}"


def _num(said: object) -> float | None:
    try:
        got = float(str(said).strip())
    except (TypeError, ValueError):
        return None
    return got


def _day(said: str) -> str:
    """🔴 `08/08/2025` → `2025-08-08`. 못 읽으면 빈 글자(추측 금지)."""
    got = [x for x in str(said or "").split("/") if x]
    if len(got) != 3:
        return ""
    d, m, y = got
    if len(y) == 2:
        y = f"20{y}"
    return f"{y}-{int(m):02d}-{int(d):02d}"


# ══════════════════════════════════════════════════════════════════
# 원천 둘 — mmz4281(핸디·언오버 있다) · new/<국가>(승무패뿐)
# ══════════════════════════════════════════════════════════════════

async def _rows_mmz(net, code: str, season: str) -> tuple[list[dict], str]:
    got = season_code(season)
    if not got:
        return [], f"🔴 시즌 `{season}` 을 mmz4281 폴더 꼴로 못 바꿨다"
    url = f"{BASE}/mmz4281/{got}/{code}.csv"
    said = await net.get(url)
    text = getattr(said, "text", "") or ""
    if not text:
        return [], f"🔴 `{url}` 을 못 받았다({getattr(said, 'reason', '')})"
    rows = [{str(k or "").lstrip("﻿"): v for k, v in r.items()}
            for r in csv.DictReader(io.StringIO(text))]
    rows = [r for r in rows if str(r.get("Div") or "") == code]
    return rows, f"`mmz4281/{got}/{code}.csv` {len(rows)}줄"


async def _rows_extra(net, file: str, league: str, season: str
                      ) -> tuple[list[dict], str]:
    url = f"{BASE}/new/{file}.csv"
    said = await net.get(url)
    text = getattr(said, "text", "") or ""
    if not text:
        return [], f"🔴 `{url}` 을 못 받았다({getattr(said, 'reason', '')})"
    rows = [{str(k or "").lstrip("﻿"): v for k, v in r.items()}
            for r in csv.DictReader(io.StringIO(text))]
    # ⚠️ 그 파일의 `League` 칸에 **앞뒤 공백**이 섞여 있다(실측: `' J1 League'`)
    want = str(league).strip().lower()
    rows = [r for r in rows
            if str(r.get("League") or "").strip().lower() == want
            and (not season
                 or str(r.get("Season") or "").strip() == str(season))]
    return rows, (f"`new/{file}.csv` 의 `{league}`"
                  + (f" {season}" if season else " 전 시즌")
                  + f" {len(rows)}줄")


def _line_mmz(r: dict) -> dict:
    """🔴🔴 mmz4281 한 줄 → 보드 한 줄. **개시와 마감을 둘 다** 담는다.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **왜 둘을 다 담나 — 누설**(후속 지시 2026-10-14 1번)
    ══════════════════════════════════════════════════════════════════

    `B365C*`·`AHCh` 는 **마감**(킥오프 직전)이다 — 예측 시점(T−24h·T−3h)에는
    **볼 수 없는 수**다. 그것으로 **J1 시장 괴리**를 재면 그 변수는 미래를 본다.
    🔴 `B365H`·`AHh` 는 football-data 가 *"가능한 한 일찍"* 받은 값이다(주중) —
       그것이 **예측 시점에 가까운 배당**이다.
    ⚠️ 둘은 실제로 다르다(실측 2026-10-14 · E1 552줄):
       평균 차 **0.144** · 중앙값 0.100 · 최대 1.15 · 완전 동일은 **80줄뿐** ·
       아시안 **기준선 자체가 190/552(34%)** 에서 움직였다.
    🔴 그래서 `win`·`ah`·`ou` 는 **마감**(보드의 정본)이고 `*_open` 이
       **개시**다 — 어느 것으로 변수를 재는지는 **쓰는 쪽이 고른다**.
    """
    ah = _num(r.get("AHCh"))
    if ah is None:
        ah = _num(r.get("AHh"))
    return {
        # ── 마감(보드의 정본 · 줄 종류와 기준선은 이것으로 정한다)
        "win": [_num(r.get("B365CH")) or _num(r.get("B365H")),
                _num(r.get("B365CD")) or _num(r.get("B365D")),
                _num(r.get("B365CA")) or _num(r.get("B365A"))],
        "ah": {"point": ah,
               "home": _num(r.get("B365CAHH")) or _num(r.get("B365AHH")),
               "away": _num(r.get("B365CAHA")) or _num(r.get("B365AHA"))},
        "ou": {"point": 2.5,
               "over": _num(r.get("B365C>2.5")) or _num(r.get("B365>2.5")),
               "under": _num(r.get("B365C<2.5")) or _num(r.get("B365<2.5"))},
        # ── 🔴 개시(예측 시점에 **볼 수 있던** 수) — 없으면 `None` 으로 남는다
        "win_open": [_num(r.get("B365H")), _num(r.get("B365D")),
                     _num(r.get("B365A"))],
        "ah_open": {"point": _num(r.get("AHh")),
                    "home": _num(r.get("B365AHH")),
                    "away": _num(r.get("B365AHA"))},
        "ou_open": {"point": 2.5, "over": _num(r.get("B365>2.5")),
                    "under": _num(r.get("B365<2.5"))},
        "시점": "마감+개시",
    }


def _line_extra(r: dict) -> dict:
    """🔴 `new/<국가>.csv` 한 줄 — **승무패뿐이다**.

    🔴🔴 그 파일은 **마감 배당만** 든다(`PSCH`·`B365CH` — `C` 가 closing) —
       **개시 배당 칸이 없다**(실측 2026-10-14: 열 25개가 전부 `*C*` 다).
    ⚠️ 그래서 이 원천의 줄은 **예측 시점 배당을 못 준다** → `win_open` 이 비고,
       J1 을 `open` 으로 재면 그 줄은 **빠진다**(지어내지 않는다 · #4).
    """
    return {
        "win": [_num(r.get("PSCH")) or _num(r.get("B365CH")),
                _num(r.get("PSCD")) or _num(r.get("B365CD")),
                _num(r.get("PSCA")) or _num(r.get("B365CA"))],
        "ah": {"point": None, "home": None, "away": None},
        "ou": {"point": None, "over": None, "under": None},
        "win_open": [None, None, None],
        "ah_open": {"point": None, "home": None, "away": None},
        "ou_open": {"point": None, "over": None, "under": None},
        "시점": "마감만(개시 칸이 없는 원천)",
    }


# ══════════════════════════════════════════════════════════════════
# 근사 보드 — 봇 확률에서 양쪽 50% 에 가장 가까운 0.5 단위
# ══════════════════════════════════════════════════════════════════

def approx_lines(lam: list) -> tuple[dict, str]:
    """🔴🔴 §1-4 근사 — λ 로 격자를 세우고 **양쪽이 가장 비슷한** 기준선을 고른다.

    🔴 격자·마켓은 `probfloor` 그 함수다 — 봇 카드가 쓰는 수와 같아야 한다.
    🔴 핸디는 **0.5 단위 전부**(정수 포함 · §1-2)에서 고르고, 고르는 잣대는
       *"두 쪽 승 확률 차가 가장 작은 줄"* 이다.
       ⚠️ 정수 줄은 **무(푸시)** 가 있어 두 쪽 합이 1 이 아니다 — 그래서
          `|홈 − 0.5|` 로 재면 정수 줄이 늘 불리해진다(실측: 핸디 0 에서 홈 0.42 ·
          원정 0.33 · 무 0.25). 🔴 **두 쪽의 차**로 재야 푸시가 상쇄된다.
    ⚠️ 언오버는 **반 단위만** 고른다 — 정수 총점 줄은 국내 보드에 거의 없고,
       푸시를 빼고 비교하려면 격자를 다시 세야 한다(안 잰 것을 쓰지 않는다 · #4).
    ⚠️ 배당은 **없다**(근사 보드에 배당을 지어 적지 않는다 · #4).
    """
    from app.core import probfloor as _pf
    got = [x for x in (lam or []) if isinstance(x, (int, float))]
    if len(got) < 2 or min(got) <= 0:
        return {}, "🔴 λ 가 없다 — 근사 보드를 못 만든다"
    box = _pf.markets_of(_pf.score_grid(lam_home=float(got[0]),
                                        lam_away=float(got[1])),
                         ah_lines=_pf.AH_LINES_FULL)
    ah = dict(box.get("ah") or {})
    over = {float(k): v for k, v in (box.get("over") or {}).items()}
    # 🔴 홈 줄 `hp` 의 **반대쪽**은 `away{-hp}` 다(보드 왼쪽 = 홈 기준 · §1-2)
    pairs = {}
    for key, val in ah.items():
        if not key.startswith("home"):
            continue
        hp = float(key[4:])
        # ⚠️ **음수 0 을 피한다** — `f"{-0.0:+.1f}"` 는 `"-0.0"` 이고 격자 열쇠는
        #    `away+0.0` 이다. 그래서 **핸디 0 줄이 통째로 빠졌다**(실측 10-14:
        #    λ 가 같은 경기에서 0 대신 −0.5 가 뽑혀 봄이 0.362/0.638 로 벌어졌다).
        mirror = (-hp) if hp else 0.0
        other = ah.get(f"away{mirror:+.1f}")
        if other is not None:
            pairs[hp] = (float(val), float(other))
    if not pairs or not over:
        return {}, "🔴 격자가 줄을 안 냈다"
    hp = min(pairs, key=lambda x: abs(pairs[x][0] - pairs[x][1]))
    op = min(over, key=lambda x: abs(over[x] - 0.5))
    a, b = pairs[hp]
    return ({"win": [None, None, None],
             "ah": {"point": hp, "home": None, "away": None},
             "ou": {"point": op, "over": None, "under": None}},
            f"근사 — 핸디 {hp:+g}(봇 홈 {a:.3f} · 원정 {b:.3f}"
            + (f" · 무 {1 - a - b:.3f}" if float(hp).is_integer() else "")
            + f") · 언오버 {op:g}(봇 오버 {over[op]:.3f})")


# ══════════════════════════════════════════════════════════════════
# 백필 재료 — `var/judge/atk_*.json`(우리 이름·시즌·봇 확률이 거기 있다)
# ══════════════════════════════════════════════════════════════════

def judge_rows() -> list[dict]:
    out: list[dict] = []
    for path in sorted(JUDGE.glob("atk_*.json")):
        got = json.loads(path.read_text(encoding="utf-8"))
        out += [r for r in got if isinstance(r, dict)]
    return out


def _names_of(rows: list[dict]) -> list[str]:
    got: list[str] = []
    for r in rows:
        for side in ("home", "away"):
            said = str(r.get(side) or "")
            if said and said not in got:
                got.append(said)
    return got


def _in_window(day: str, span: tuple) -> bool:
    """🔴 그 날짜가 **우리 경기 기간 ±30일** 안인가. 창이 없으면 전부 안이다."""
    lo, hi = span
    if not (lo and hi and day):
        return True
    from datetime import date as _d, timedelta as _td
    def _p(said: str):
        try:
            y, m, d = (int(x) for x in str(said).split("-"))
            return _d(y, m, d)
        except (TypeError, ValueError):
            return None
    one, a, b = _p(day), _p(lo), _p(hi)
    if not (one and a and b):
        return True
    return a - _td(days=30) <= one <= b + _td(days=30)


def _match(box: list[dict], day: str) -> dict | None:
    """🔴 그 짝의 실보드 줄 중 **날짜가 맞는 것**. ±2일까지 본다.

    ⚠️ 현지 날짜와 UTC 날짜가 한 칸 어긋난다(절대규칙 2) — 그래서 ±1 이 필요하고,
       ±2 는 연기된 경기가 하루 넘게 밀린 경우다.
    🔴 날짜가 없으면 그 짝이 **딱 하나일 때만** 쓴다(짐작으로 고르지 않는다).
    """
    if not box:
        return None
    if not day:
        return box[0] if len(box) == 1 else None
    from datetime import date as _d
    def _parse(said: str):
        try:
            y, m, d = (int(x) for x in str(said).split("-"))
            return _d(y, m, d)
        except (TypeError, ValueError):
            return None
    want = _parse(day)
    if want is None:
        return box[0] if len(box) == 1 else None
    near = []
    for one_row in box:
        got = _parse(str(one_row.get("day") or ""))
        if got is None:
            continue
        near.append((abs((got - want).days), one_row))
    if not near:
        return box[0] if len(box) == 1 else None
    gap, best = min(near, key=lambda kv: kv[0])
    return best if gap <= 2 else None


async def one(net, league: str, season: str, rows: list[dict]) -> dict:
    """🔴 리그·시즌 하나 — 실보드를 받아 우리 경기에 붙인다. 못 붙인 것은 근사."""
    from app.core import competition as _cp
    from app.core import teamname as _tn
    src = dict((_cp.row_of(league).get("sources") or {})
               .get("football_data_hist") or {})
    names = _names_of(rows)
    days = sorted(str(r.get("day") or "") for r in rows if r.get("day"))
    span = (days[0], days[-1]) if days else ("", "")
    out_of_window = 0
    hist: list[dict] = []
    why = ""
    if src.get("kind") == "mmz4281":
        hist, why = await _rows_mmz(net, str(src.get("code")), season)
        make = _line_mmz
    elif src.get("kind") == "extra":
        # 🔴🔴 **시즌 꼬리표로 거르지 않는다** — 실측 2026-10-14: `new/JPN.csv` 는
        #    `2025`(380경기) 다음이 바로 `2026/2027`(90경기)이고 우리 판의
        #    `2026`(200경기) 라는 꼬리표가 **그 파일에 없다**. 꼬리표로 걸렀더니
        #    200경기가 전부 근사로 떨어졌다. 🔴 그래서 그 리그 **전부**를 받아
        #    **날짜+두 팀**으로 붙인다(아래 `_match`).
        hist, why = await _rows_extra(net, str(src.get("file")),
                                      str(src.get("league")), "")
        make = _line_extra
    else:
        why = f"🔴 `{league}` 에 `football_data_hist` 가 없다 → 전부 근사"
        make = _line_mmz
    # 🔴 실보드 줄을 **두 팀 + 날짜**로 색인한다(한 시즌에 같은 짝이 두 번 있다 —
    #    홈/원정이 바뀌지만 컵·플레이오프가 섞이면 같은 짝이 또 온다)
    book: dict[tuple, list[dict]] = {}
    unmatched: list[str] = []
    seen: dict[str, set] = {}
    for r in hist:
        day = _day(str(r.get("Date") or ""))
        h_raw = str(r.get("HomeTeam") or r.get("Home") or "")
        a_raw = str(r.get("AwayTeam") or r.get("Away") or "")
        home, _wh = _tn.pick(h_raw, names)
        away, _wa = _tn.pick(a_raw, names)
        if not (home and away):
            # 🔴 **우리 경기 날짜 창 안의 줄만** 센다 — `kind: extra` 는 그 리그
            #    **전 시즌**(2012~)을 받으므로, 옛 시즌의 팀(오미야·베갈타…)이
            #    우리 20팀에 없는 것은 **결함이 아니다**. 창 밖은 소리 없이가
            #    아니라 **수로** 남긴다(아래 `out_of_window`).
            if _in_window(day, span):
                unmatched.append(f"{day} {h_raw} vs {a_raw}")
            else:
                out_of_window += 1
            continue
        seen.setdefault(home, set()).add(h_raw)
        seen.setdefault(away, set()).add(a_raw)
        got = make(r)
        got.update({"day": day, "home": home, "away": away,
                    "raw": [h_raw, a_raw], "kind": "실보드"})
        book.setdefault((home, away), []).append(got)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **한 우리 이름에 원천 표기가 둘이면 하나는 남의 팀이다**
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-14: `new/JPN.csv` 의 **`Yokohama FC`** 가
    #     `Yokohama F.Marinos` 에 붙었다(겹침 `yokohama` 하나 ÷ 1 = 1.00) —
    #     **다른 구단**이다. 그대로 두면 마리노스 경기에 남의 보드가 섞인다.
    #  🔴 이름으로는 못 가르니 **표기를 하나로 좁힌다** — 겹침 비율이 같으면
    #     겹친 낱말이 많은 쪽(그 이름을 제대로 쓴 쪽)을 남긴다. 버린 표기는
    #     **이름으로 적는다**(#3).
    #  ⚠️ 같은 구단의 옛 표기(`Urawa Reds` ↔ `Urawa Red Diamonds`)는 겹침 수가
    #     달라 제대로 남는다.
    clash: list[str] = []
    keep: dict[str, str] = {}
    for ours, raws in seen.items():
        if len(raws) < 2:
            keep[ours] = next(iter(raws))
            continue
        rank = sorted(raws, key=lambda x: (
            -_tn.share(x, ours), -len(_tn._core(x) & _tn._core(ours)), x))
        keep[ours] = rank[0]
        clash.append(f"`{ours}` ← {rank[0]}(남김) · 버린 표기 "
                     + " · ".join(rank[1:4]))
    if clash:
        for key in list(book):
            box = [x for x in book[key]
                   if x["raw"][0] == keep.get(key[0])
                   and x["raw"][1] == keep.get(key[1])]
            if box:
                book[key] = box
            else:
                del book[key]
    lines: list[dict] = []
    tally = {"실보드": 0, "근사": 0, "없음": 0}
    for r in rows:
        key = (str(r.get("home") or ""), str(r.get("away") or ""))
        got = _match(book.get(key) or [], str(r.get("day") or ""))
        if got:
            lines.append(dict(got, day=str(r.get("day") or got.get("day") or "")))
            tally["실보드"] += 1
            continue
        said, note = approx_lines(list(r.get("lam") or []))
        if said:
            said.update({"day": str(r.get("day") or ""), "home": key[0],
                         "away": key[1], "raw": [], "kind": "근사",
                         "note": note})
            lines.append(said)
            tally["근사"] += 1
        else:
            lines.append({"day": str(r.get("day") or ""), "home": key[0],
                          "away": key[1], "kind": "없음", "note": note})
            tally["없음"] += 1
    # 🔴 실보드인데 핸디·언오버 기준선이 **없는 줄**은 그 칸만 근사로 메운다
    part = 0
    for i, one_line in enumerate(lines):
        if one_line.get("kind") != "실보드":
            continue
        if (one_line.get("ah") or {}).get("point") is not None:
            continue
        said, note = approx_lines(list((rows[i].get("lam") or [])))
        if not said:
            continue
        one_line["ah"] = said["ah"]
        one_line["ou"] = (one_line.get("ou") if (one_line.get("ou") or {})
                          .get("point") is not None else said["ou"])
        one_line["note"] = f"핸디·언오버 칸이 비어 근사로 메웠다 · {note}"
        one_line["kind"] = "실보드(승무패만)"
        part += 1
    return {"league": league, "season": season, "why": why,
            "rows": len(rows), "hist": len(hist), "book": len(book),
            "unmatched": unmatched, "tally": tally, "part": part,
            "clash": clash, "out_of_window": out_of_window, "lines": lines}


async def main(argv: list[str]) -> int:
    import yaml
    from app.net import Net
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", action="append")
    ap.add_argument("--season", action="append")
    args = ap.parse_args(argv[1:])
    got = judge_rows()
    if not got:
        print("🔴 `var/judge/atk_*.json` 이 없다 — 백필 재료가 없다")
        return 1
    pairs: dict[tuple, list[dict]] = {}
    for r in got:
        key = (str(r.get("league") or ""), str(r.get("season") or ""))
        if args.league and key[0] not in args.league:
            continue
        if args.season and key[1] not in args.season:
            continue
        pairs.setdefault(key, []).append(r)
    net = Net(cache=True)
    BOX.mkdir(parents=True, exist_ok=True)
    print("# 🔴🔴 백필 보드 — 리그·시즌별 실보드/근사")
    print()
    print("| 리그 | 시즌 | 경기 | 실보드 | 실보드(승무패만) | 근사 | 없음 | 원천 |")
    print("|---|---|---|---|---|---|---|---|")
    tot = {"실보드": 0, "근사": 0, "없음": 0}
    misses: list[str] = []
    for key in sorted(pairs):
        league, season = key
        box = await one(net, league, season, pairs[key])
        path = (BOX / league.replace(":", "_")
                / f"{season.replace('/', '-')}.yaml")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(
            {"meta": {"league": league, "season": season,
                      "source": box["why"], "rows": box["rows"],
                      "hist_rows": box["hist"], "matched": box["book"],
                      "got_at": datetime.now(timezone.utc)
                      .isoformat(timespec="minutes"),
                      "tally": box["tally"], "part_approx": box["part"],
                      "clash": box["clash"],
                      "out_of_window": box["out_of_window"],
                      "unmatched": box["unmatched"][:40]},
             "lines": box["lines"]},
            allow_unicode=True, sort_keys=False), encoding="utf-8")
        for k in tot:
            tot[k] += box["tally"][k]
        print(f"| `{league}` | {season} | {box['rows']} | "
              f"**{box['tally']['실보드'] - box['part']}** | {box['part']} | "
              f"{box['tally']['근사']} | {box['tally']['없음']} | "
              f"{box['why']} |")
        if box.get("clash"):
            misses.append(f"`{league}` {season} — 🔴 **한 이름에 원천 표기가 둘** "
                          f"{len(box['clash'])}건: " + " / ".join(box["clash"][:4]))
        if box["unmatched"]:
            misses.append(f"`{league}` {season} — 이름 못 붙인 실보드 줄 "
                          f"**{len(box['unmatched'])}건**(우리 경기 기간 안): "
                          + " · ".join(box["unmatched"][:6]))
        if box["out_of_window"]:
            misses.append(f"`{league}` {season} — ⏸ 기간 밖 줄 "
                          f"{box['out_of_window']}건(옛 시즌 팀 — 결함 아니다)")
    print()
    all_n = sum(tot.values()) or 1
    print(f"🔴 **전체 {all_n}경기** — 실보드 {tot['실보드']}"
          f"({tot['실보드'] / all_n:.0%}) · 근사 {tot['근사']}"
          f"({tot['근사'] / all_n:.0%}) · 없음 {tot['없음']}")
    if misses:
        print()
        print("## ⚠️ 이름 맞춤에서 걸린 것 (조용히 버리지 않는다 · #3)")
        for said in misses:
            print(f"- {said}")
    print()
    print(f"판은 `{BOX.relative_to(ROOT)}/<리그>/<시즌>.yaml` 이다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
