"""🔴🔴 **역배 성적**(후속 지시 2026-10-14 1번).

```
PYTHONPATH=. uv run python tools/fade_grade.py
```

> 홀드아웃 2,865경기: 역배 판정 수 · 적중 · 의심 후 확률 평균 · 줄 종류 ·
> 평균 보드 배당(개시) · 의심 변수별 분해 · 역배 문턱 곡선(0.50·0.55·0.60) ·
> J1 걸린 경기의 반대쪽 실측(더블찬스 · DNB · +0.5).

## 🔴 "반대쪽" 이 무엇인가 — 1X2 의 반대는 **한 줄이 아니다**
봇이 `홈 승` 을 앞세웠는데 역배가 서면, 그 반대는
  · **더블찬스 X2** — 무 또는 원정(무면 **이긴다**)
  · **DNB 원정** — 원정 승만(무면 **무효** → 표본에서 뺀다)
  · **핸디 원정 +0.5** — 원정 승 또는 무 → 🔴 **더블찬스와 같은 베팅**이다
🔴 그래서 셋을 **따로** 센다(+0.5 는 더블찬스와 같은 수가 나오는 것이 정상이다 —
   다르면 세는 쪽이 틀렸다는 뜻이고, 그 확인을 표가 한다).
⚠️ `무` 를 앞세운 픽의 반대는 *"무가 아니다"* = 홈 또는 원정이다(DNB 는 없다).

🔴 배당은 **개시(예측 시점)** 만 쓴다(`win_open`·`ah_open`) — 마감은 예측 시점에
   볼 수 없다. 🔴 없는 배당은 **지어내지 않는다**(⬜).
🔴 기대값·손익분기·켈리·금액은 **계산하지 않는다**(절대규칙).
"""
from __future__ import annotations

import statistics as stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 역배 문턱 곡선의 자리(지시 1번의 그 셋)
FADE_CUTS = (0.50, 0.55, 0.60)


def _opposite(pick: str, hg: int, ag: int) -> dict:
    """🔴 그 픽의 **반대쪽**이 맞았나 — 셋으로. `무효`는 `None` 이다."""
    d = int(hg) - int(ag)
    if pick == "홈 승":
        return {"더블찬스": int(d <= 0), "DNB": (None if d == 0 else int(d < 0)),
                "+0.5": int(d <= 0)}
    if pick == "원정 승":
        return {"더블찬스": int(d >= 0), "DNB": (None if d == 0 else int(d > 0)),
                "+0.5": int(d >= 0)}
    # 🔴 `무` 의 반대는 *"무가 아니다"* — DNB 는 없다
    return {"더블찬스": int(d != 0), "DNB": None, "+0.5": None}


def _price(board: dict | None, pick: str) -> dict:
    """🔴 반대쪽의 **개시** 보드 배당 — 보드가 실제로 든 것만."""
    out: dict = {"반대 단일": None, "핸디 ±0.5": None}
    if not board:
        return out
    win = list(board.get("win_open") or [])
    if len(win) == 3:
        i = {"홈 승": 2, "원정 승": 0}.get(pick)
        if i is not None and isinstance(win[i], (int, float)):
            out["반대 단일"] = float(win[i])
    ah = dict(board.get("ah_open") or {})
    point = ah.get("point")
    if point is not None and abs(abs(float(point)) - 0.5) < 1e-9:
        # 🔴 반대쪽이 **+0.5 를 받는 쪽**일 때만 그 배당이 그 베팅이다
        side = "away" if pick == "홈 승" else ("home" if pick == "원정 승"
                                              else "")
        want = (float(point) < 0) if side == "away" else (float(point) > 0)
        val = ah.get(side) if side else None
        if want and isinstance(val, (int, float)):
            out["핸디 ±0.5"] = float(val)
    return out


def main() -> int:
    import yaml

    import fit_doubt as fd
    import replays
    from cut_curve import AFTER_KINDS, lines_of

    from app.core import doubt as _db
    plate = _db.plates()
    if not plate:
        print("🔴 보정표가 없다 — `tools/fit_doubt.py` 를 먼저 돌려라")
        return 1
    hold: list[str] = []
    for path in sorted((ROOT / "data/doubt_cal").glob("*.yaml")):
        got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        hold = [str(x) for x in (dict(got.get("meta") or {})
                                 .get("홀드아웃") or [])]
        if hold:
            break
    conf = dict(_db.table().get("cuts") or {})
    fade_lo = float(conf.get("역배_하한") or 0.50)
    book = fd.boards()
    wide, why_w = fd.wide_rows()
    bad_of = {(str(o.get("league")), str(o.get("day")), str(o.get("home")),
               str(o.get("away"))): (1 if dict(o.get("flag") or {})["H1"]
                                     else 0)
              for o in wide if dict(o.get("flag") or {}).get("H1") is not None}
    rows, said = replays.load()
    rows = [r for r in rows if r.get("lam") and r.get("hit") is not None
            and str(r.get("season") or "") in set(hold)]
    print("# 🔴🔴 역배 성적")
    print()
    print(f"- 홀드아웃 **{sorted(hold)}**(표본 밖 · {len(rows)}경기) · "
          f"역배 하한 **{fade_lo:.0%}** · 시즌 교차 필수 "
          f"**{_db.table().get('역배_시즌교차_필수')}**")
    print("- 🔴 배당은 **개시(예측 시점)** 만 쓴다 · 없는 배당은 ⬜ 다.")
    print("- 🔴 `무` 를 앞세운 픽의 반대는 *무가 아니다* — **DNB 가 없다**.")
    print()
    # ── 경기마다 봇 최고 승무패 줄 → 칸 → 역배인가
    got_rows: list[dict] = []
    for r in rows:
        key = (str(r.get("league")), str(r.get("day")), str(r.get("home")),
               str(r.get("away")))
        if key not in bad_of:
            continue
        n_bad = bad_of[key]
        said_lines = [x for x in lines_of([float(x) for x in r["lam"][:2]],
                                          int(r["hg"]), int(r["ag"]))
                      if x[0] in AFTER_KINDS]
        if not said_lines:
            continue
        name, p, _ok = max(said_lines, key=lambda x: x[1])
        cell = _db.cell_for(plate, _db.kind_of(name), float(p), n_bad)
        if cell is None or cell.get("보류"):
            continue
        board = book.get((str(r.get("league")), str(r.get("season")),
                          str(r.get("home")), str(r.get("away"))))
        got_rows.append({
            "pick": name, "p": float(p), "n_bad": n_bad,
            "after": float(cell["실측"]), "lo": float(cell["lo"]),
            "hi": float(cell["hi"]), "cell": str(cell.get("구간")),
            "cross": cell.get("시즌교차"), "day": str(r.get("day")),
            "league": str(r.get("league")),
            "other_lo": 1.0 - float(cell["hi"]),
            **_opposite(name, int(r["hg"]), int(r["ag"])),
            **_price(board, name)})
    days = len({x["day"] for x in got_rows}) or 1
    # ── ① 역배 판정 — 지금 규칙대로
    fade = [x for x in got_rows
            if x["other_lo"] > fade_lo and x["cross"] is True]
    blocked = [x for x in got_rows
               if x["other_lo"] > fade_lo and x["cross"] is not True]
    print("## ① 역배 판정 — 지금 규칙(하한 > 50% **그리고** 시즌 교차 ✅)")
    print()
    if not fade:
        print("- ⬜ **역배가 서지 않는다** — 하한을 넘은 칸이 "
              f"{len(blocked)}개인데 전부 **시즌 교차가 없다**.")
    else:
        print(f"- 역배 **{len(fade)}개** · 하루 {len(fade) / days:.2f}개 · "
              f"의심 후 평균 **{stat.mean(x['after'] for x in fade):.1%}** · "
              f"반대쪽 하한 평균 **{stat.mean(x['other_lo'] for x in fade):.1%}**")
        print(f"- 칸 — "
              + " · ".join(sorted({f"{x['cell']}(묶음 {x['n_bad']})"
                                   for x in fade})))
        print()
        print("| 반대쪽 베팅 | 센 줄 | 적중 | 95% 구간 | 평균 개시 배당 |")
        print("|---|---|---|---|---|")
        from fit_doubt import wilson
        for way, price_key in (("더블찬스", "핸디 ±0.5"), ("DNB", "반대 단일"),
                               ("+0.5", "핸디 ±0.5")):
            part = [x for x in fade if x.get(way) is not None]
            if not part:
                print(f"| {way} | 0 | ⬜ | ⬜ | ⬜ |")
                continue
            p2, lo2, hi2 = wilson(sum(x[way] for x in part), len(part))
            prices = [x[price_key] for x in part if x.get(price_key)]
            print(f"| **{way}** | {len(part)} | **{p2:.1%}** | "
                  f"[{lo2:.1%}, {hi2:.1%}] | "
                  + (f"**{stat.mean(prices):.3f}**(줄 {len(prices)})"
                     if prices else "⬜") + " |")
        same = [x for x in fade
                if x.get("더블찬스") is not None and x.get("+0.5") is not None]
        bad = [x for x in same if x["더블찬스"] != x["+0.5"]]
        print()
        print(f"- 🔴 **더블찬스 ↔ +0.5 는 같은 베팅이다** — 어긋난 줄 "
              f"**{len(bad)}/{len(same)}**"
              + (" ✅ 센 쪽이 맞다" if not bad else " 🔴 세는 쪽이 틀렸다"))
    if blocked:
        print()
        print(f"- ⚠️ **하한은 넘었는데 시즌 교차가 없어 막힌 줄 {len(blocked)}개** "
              "— 그 줄의 반대쪽 더블찬스 실측 "
              + (f"**{sum(x['더블찬스'] for x in blocked) / len(blocked):.1%}**"
                 if blocked else "⬜")
              + "(참고만 · 역배로 내지 않는다)")
    print()
    # ── ② 의심 변수별 분해
    print("## ② 역배를 만든 **의심 변수별** 분해")
    print()
    print("| 묶음(유효 불리 의심 수) | 역배 | 반대 더블찬스 적중 | 비고 |")
    print("|---|---|---|---|")
    for n in (0, 1, 2):
        part = [x for x in fade if x["n_bad"] == n]
        if not part:
            print(f"| {n} | 0 | ⬜ | — |")
            continue
        print(f"| **{n}** | {len(part)} | "
              f"**{sum(x['더블찬스'] for x in part) / len(part):.1%}** | "
              f"칸 {sorted({x['cell'] for x in part})} |")
    print()
    print("🔴 ⚠️ **변수 하나씩으로는 못 쪼갠다** — 이 표본의 묶음은 **H1 하나**로"
          " 정해진다(재생본에는 보드가 없어 J1 을 못 센다 · 판의 `오염` 칸). "
          "그래서 역배는 사실상 **H1 이 만든 것**이고, J1 몫은 아래 ④ 에서 "
          "덤프(1,470경기)로 따로 센다.")
    print()
    # ── ③ 역배 문턱 곡선
    print("## ③ 역배 문턱 곡선 — 반대쪽 의심 후 확률 **하한**")
    print()
    print("| 하한 | 역배 수 | 반대 더블찬스 적중 | 95% 구간 | 하루 수 | "
          "교차 ✅ 만 |")
    print("|---|---|---|---|---|---|")
    from fit_doubt import wilson
    for cut in FADE_CUTS:
        part = [x for x in got_rows if x["other_lo"] > cut]
        strict = [x for x in part if x["cross"] is True]
        if not part:
            print(f"| {cut:.2f} | 0 | ⬜ | ⬜ | 0.00 | 0 |")
            continue
        p2, lo2, hi2 = wilson(sum(x["더블찬스"] for x in part), len(part))
        print(f"| **{cut:.2f}** | {len(part)} | **{p2:.1%}** | "
              f"[{lo2:.1%}, {hi2:.1%}] | {len(part) / days:.2f} | "
              f"{len(strict)} |")
    print()
    # ── ④ J1 걸린 경기의 반대쪽 실측(덤프 · 개시 기준)
    print("## ④ J1 걸린 경기의 **반대쪽 실측**(덤프 1,470경기 · 개시 기준)")
    print()
    from fit_attack2 import rows_all
    dump = fd.flags_of(rows_all(), book, j1_odds="open")
    hit_j1 = [x for x in dump if dict(x.get("flag") or {}).get("J1") is True]
    print(f"- J1 걸린 경기 **{len(hit_j1)}** · 봇이 앞세운 쪽 적중 "
          + (f"**{sum(x['ok'] for x in hit_j1) / len(hit_j1):.1%}**"
             if hit_j1 else "⬜"))
    print()
    print("| 반대쪽 베팅 | 센 줄 | 적중 | 95% 구간 | 평균 개시 배당 |")
    print("|---|---|---|---|---|")
    for way, price_key in (("더블찬스", "핸디 ±0.5"), ("DNB", "반대 단일"),
                           ("+0.5", "핸디 ±0.5")):
        box = []
        for r in hit_j1:
            ours = [float(x) for x in r["ours"]]
            pick = ("홈 승", "무", "원정 승")[
                max(range(3), key=lambda i: ours[i])]
            got_o = _opposite(pick, int(r["hg"]), int(r["ag"]))
            if got_o.get(way) is None:
                continue
            board = book.get((str(r.get("league")), str(r.get("season")),
                              str(r.get("home")), str(r.get("away"))))
            box.append((got_o[way], _price(board, pick).get(price_key)))
        if not box:
            print(f"| {way} | 0 | ⬜ | ⬜ | ⬜ |")
            continue
        p2, lo2, hi2 = wilson(sum(o for o, _pr in box), len(box))
        prices = [pr for _o, pr in box if pr]
        print(f"| **{way}** | {len(box)} | **{p2:.1%}** | "
              f"[{lo2:.1%}, {hi2:.1%}] | "
              + (f"**{stat.mean(prices):.3f}**(줄 {len(prices)})"
                 if prices else "⬜") + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
