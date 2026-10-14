"""🔴🔴 **누설 점검 — J1 을 어느 시점 배당으로 재나**(후속 지시 2026-10-14 1번).

```
PYTHONPATH=. uv run python tools/j1_leak.py
```

> 판: (가) 지금(**마감 배당** J1) vs (나) **예측 시점 배당**(개시) J1 vs
> (다) **J1 끔** — 확신 픽 수 · 적중 · 보정 곡선.
> (가)만 좋고 (나)·(다)가 무너지면 69.5% 는 **누설**이다.

## 왜 이 점검이 필요한가
`data/board_hist` 의 `win`·`ah`·`ou` 는 **마감 배당**(`B365C*`·`AHCh`·`PSC*`)이다
— **킥오프 직전** 수이고 예측 시점(T−24h·T−3h)에는 **볼 수 없다**. 그것으로
J1(시장 괴리)을 재면 그 변수는 **미래를 본다**.
🔴 `win_open`(`B365H` 등)은 football-data 가 *"가능한 한 일찍"* 받은 값이다 —
   그것이 예측 시점에 가까운 배당이다. 둘은 실제로 다르다(실측: 평균 차 0.144 ·
   아시안 기준선 자체가 34% 에서 움직였다).

🔴 **판을 디스크에 쓰지 않는다** — `fit_doubt.plates_of` 가 칸을 메모리로 주고
   `core/doubt.cell_for` 가 그것을 그대로 읽는다(운영 판을 안 건드린다).
🔴 세 판 **전부 같은 홀드아웃**(기본 `2025/2026`)에서 센다 — 적합에 그 시즌을
   넣지 않고, 문턱·적중·곡선은 **그 시즌에서만** 센다.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

MODES = (("가", "close", "마감 배당(지금 · 누설 의심)"),
         ("나", "open", "개시 배당(예측 시점)"),
         ("다", "off", "J1 끔"))


def brier(rows: list[tuple]) -> float:
    if not rows:
        return float("nan")
    return sum((float(p) - float(ok)) ** 2 for p, ok in rows) / len(rows)


def one_mode(mode: str, *, holdout: set, rows_all: list, book: dict,
             wide_all: list, cut: float, slack: float) -> dict:
    """🔴 한 판 — 적합(홀드아웃 뺀다) → 그 칸으로 홀드아웃을 센다."""
    import fit_doubt as fd
    from cut_curve import AFTER_KINDS, lines_of

    from app.core import doubt as _db
    # ── ① 깃발 · 시험(J1 이 그 시점 배당에서도 **유효**한가)
    box = fd.flags_of(rows_all, book, j1_odds=mode)
    fit_rows = [x for x in box if str(x.get("season") or "") not in holdout]
    said_j1 = _test_j1(fit_rows)
    live = ["H1"] + (["J1"] if (mode != "off" and said_j1["유효"]) else [])
    # ── ② 칸(홀드아웃 뺀 줄로만)
    wide = [x for x in wide_all if str(x.get("season") or "") not in holdout]
    plate = fd.plates_of(fd.cells(fit_rows, book, live, wide=wide))
    # ── ③ 홀드아웃에서 센다 — 묶음은 **깃발로** 정한다
    bad_of = {}
    for one in box:
        flag = dict(one.get("flag") or {})
        if any(flag.get(k) is None for k in live):
            continue
        bad_of[(str(one.get("league")), str(one.get("day")),
                str(one.get("home")), str(one.get("away")))] = sum(
            1 for k in live if flag.get(k) is True)
    # 🔴 재생본 줄에도 묶음을 준다(H1 만 센다 — J1 은 보드가 필요하다)
    for one in wide_all:
        flag = dict(one.get("flag") or {})
        if flag.get("H1") is None:
            continue
        key = (str(one.get("league")), str(one.get("day")),
               str(one.get("home")), str(one.get("away")))
        bad_of.setdefault(key, 1 if flag["H1"] else 0)
    got: list[dict] = []
    for r in wide_all:
        if str(r.get("season") or "") not in holdout:
            continue
        key = (str(r.get("league")), str(r.get("day")), str(r.get("home")),
               str(r.get("away")))
        if key not in bad_of:
            continue
        said_lines = [x for x in lines_of([float(x) for x in r["lam"][:2]],
                                          int(r["hg"]), int(r["ag"]))
                      if x[0] in AFTER_KINDS]
        if not said_lines:
            continue
        name, p, ok = max(said_lines, key=lambda x: x[1])
        cell = _db.cell_for(plate, _db.kind_of(name), float(p), bad_of[key])
        got.append({"p": float(p), "ok": int(bool(ok)),
                    "after": (None if cell is None or cell.get("보류")
                              else float(cell["실측"])),
                    "lo": (None if cell is None or cell.get("보류")
                           else float(cell["lo"]))})
    pair = [x for x in got if x["after"] is not None]
    sure = [x for x in pair
            if x["after"] >= cut and x["lo"] >= cut - slack]
    old = sorted(got, key=lambda x: -x["p"])[:len(sure)]
    return {"mode": mode, "live": live, "j1": said_j1,
            "n_line": len(got), "n_cell": len(pair),
            "n_sure": len(sure),
            "hit": (sum(x["ok"] for x in sure) / len(sure)) if sure else None,
            "hit_old": (sum(x["ok"] for x in old) / len(old)) if old else None,
            "brier_bot": brier([(x["p"], x["ok"]) for x in pair]),
            "brier_after": brier([(x["after"], x["ok"]) for x in pair]),
            "err_bot": (sum(abs(x["p"] - x["ok"]) for x in pair) / len(pair)
                        if pair else float("nan")),
            "err_after": (sum(abs(x["after"] - x["ok"]) for x in pair)
                          / len(pair) if pair else float("nan")),
            "plate": plate}


def _test_j1(rows: list[dict]) -> dict:
    """🔴 그 시점 배당에서 J1 이 **(가) 유효**인가 — `fit_doubt` 와 같은 잣대."""
    from fit_attack2 import TIERS, ci
    out: dict = {"n_on": 0, "유효": False, "체급": {}}
    part = [x for x in rows if x["flag"].get("J1") is not None]
    on = [x["ok"] for x in part if x["flag"]["J1"]]
    off = [x["ok"] for x in part if not x["flag"]["J1"]]
    out["n_on"], out["n_off"] = len(on), len(off)
    if len(on) < 20 or len(off) < 20:
        out["why"] = f"표본 부족(걸림 {len(on)} · 안 걸림 {len(off)})"
        return out
    d, lo, hi = ci(on, off)
    out.update({"diff": d, "lo": lo, "hi": hi,
                "hit_on": sum(on) / len(on), "hit_off": sum(off) / len(off)})
    whole = (hi < 0 or lo > 0) and d < 0
    deep = []
    for name, a, b in TIERS:
        got = [x for x in part if a <= x["dr"] < b]
        t_on = [x["ok"] for x in got if x["flag"]["J1"]]
        t_off = [x["ok"] for x in got if not x["flag"]["J1"]]
        if len(t_on) < 20 or len(t_off) < 20:
            out["체급"][name] = "표본 부족"
            continue
        td, tlo, thi = ci(t_on, t_off)
        out["체급"][name] = td
        if (thi < 0 or tlo > 0) and td < 0:
            deep.append(name)
    out["유효"] = bool(whole and deep)
    out["체급유효"] = deep
    out["why"] = ("(가) 유효" if out["유효"]
                  else ("(나) 체급 통제하면 사라진다" if whole
                        else "(나) 차이 없음"))
    return out


def main(argv: list[str]) -> int:
    import fit_doubt as fd
    from fit_attack2 import rows_all

    from app.core import doubt as _db
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout", action="append", default=["2025/2026"])
    args = ap.parse_args(argv[1:])
    hold = {str(x) for x in args.holdout}
    conf = dict(_db.table().get("cuts") or {})
    cut = float(conf.get("확신") or 0.58)
    slack = float(conf.get("확신_하한_여유") or 0.03)
    rows = rows_all()
    book = fd.boards()
    wide, why_w = fd.wide_rows()
    print("# 🔴🔴 누설 점검 — J1 을 어느 시점 배당으로 재나")
    print()
    print(f"- 홀드아웃 **{sorted(hold)}** · 확신 문턱 **{cut:.2f}**"
          f"(하한 여유 {slack:.2f})")
    print(f"- 백필 보드 {len(book)}줄 · 덤프 {len(rows)}경기 · {why_w}")
    print("- 🔴 **마감 배당은 킥오프 직전 수다** — 예측 시점(T−24h·T−3h)에는 "
          "볼 수 없다. `win_open`(개시)이 예측 시점에 가까운 값이다.")
    print()
    got = {}
    for tag, mode, name in MODES:
        got[tag] = one_mode(mode, holdout=hold, rows_all=rows, book=book,
                            wide_all=wide, cut=cut, slack=slack)
        got[tag]["name"] = name
    # ══════════════════════════════════════════════════════════════════
    # ①-a 🔴🔴 **전 표본** J1 시험 — §2-3 이 J1 을 올린 그 자리에서 다시
    # ══════════════════════════════════════════════════════════════════
    print("## ①-a J1 시험 — **전 표본**(§2-3 이 올린 그 자리)에서 시점을 바꿔")
    print()
    print("| J1 기준 | 걸림 | 걸림 적중 | 안 걸림 | 차이 | 95% 구간 | 체급별 | 읽기 |")
    print("|---|---|---|---|---|---|---|---|")
    full: dict = {}
    for tag, mode, name in MODES:
        if mode == "off":
            continue
        said = _test_j1(fd.flags_of(rows, book, j1_odds=mode))
        full[mode] = said
        tier = " · ".join(
            f"{k} {v if isinstance(v, str) else f'{v * 100:+.1f}'}"
            for k, v in said.get("체급", {}).items())
        if "diff" not in said:
            print(f"| {name} | {said['n_on']} | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | "
                  f"{said['why']} |")
            continue
        print(f"| {name} | {said['n_on']} | {said['hit_on']:.1%} | "
              f"{said['hit_off']:.1%} | **{said['diff'] * 100:+.1f}%p** | "
              f"[{said['lo'] * 100:+.1f}, {said['hi'] * 100:+.1f}] | {tier} | "
              + ("🔴 **(가) 유효**" if said["유효"] else said["why"]) + " |")
    print()
    print("## ①-b J1 시험 — **적합 표본**(홀드아웃 뺀 뒤)에서")
    print()
    print("| 판 | J1 기준 | 걸림 | 걸림 적중 | 안 걸림 | 차이 | 95% 구간 | 읽기 |")
    print("|---|---|---|---|---|---|---|---|")
    for tag, _mode, name in MODES:
        one = got[tag]["j1"]
        if "diff" not in one:
            print(f"| **({tag})** | {got[tag]['name']} | {one['n_on']} | ⬜ "
                  f"| ⬜ | ⬜ | ⬜ | {one['why']} |")
            continue
        print(f"| **({tag})** | {got[tag]['name']} | {one['n_on']} | "
              f"{one['hit_on']:.1%} | {one['hit_off']:.1%} | "
              f"**{one['diff'] * 100:+.1f}%p** | "
              f"[{one['lo'] * 100:+.1f}, {one['hi'] * 100:+.1f}] | "
              + ("🔴 **" + one["why"] + "**" if one["유효"] else one["why"])
              + " |")
    print()
    print("## ② 확신 픽 · 적중 · 보정 곡선 (홀드아웃 · **표본 밖**)")
    print()
    print("| 판 | 유효 의심 | 칸 있는 줄 | 확신 | 적중 | 같은 수 봇 상위 | "
          "브라이어 봇→의심 후 | 절대 오차 봇→의심 후 |")
    print("|---|---|---|---|---|---|---|---|")
    for tag, _mode, _name in MODES:
        one = got[tag]
        print(f"| **({tag})** | {', '.join(one['live'])} | {one['n_cell']} | "
              f"{one['n_sure']} | "
              + (f"**{one['hit']:.1%}**" if one["hit"] is not None else "⬜")
              + " | "
              + (f"{one['hit_old']:.1%}" if one["hit_old"] is not None
                 else "⬜")
              + f" | {one['brier_bot']:.4f} → **{one['brier_after']:.4f}**"
              f" | {one['err_bot']:.4f} → **{one['err_after']:.4f}** |")
    print()
    # ── 판정
    a, b, c = got["가"], got["나"], got["다"]
    print("## ③ 판정")
    print()
    oks = [x for x in (a, b, c) if x["hit"] is not None]
    if not oks:
        print("🔴 셋 다 확신이 0 이다 — 판정할 수 없다")
        return 0
    worst = min(x["hit"] for x in oks)
    best = max(x["hit"] for x in oks)
    leak = (a["hit"] is not None
            and all(x["hit"] is None or a["hit"] - x["hit"] > 0.05
                    for x in (b, c)))
    print("- 적중 — "
          + " · ".join(f"({t}) "
                       + (f"**{got[t]['hit']:.1%}**"
                          if got[t]["hit"] is not None else "⬜")
                       + f"(확신 {got[t]['n_sure']})"
                       for t in ("가", "나", "다")))
    print(f"- 퍼짐 — 가장 낮은 판 {worst:.1%} ↔ 가장 높은 판 {best:.1%}"
          f"(차 {100 * (best - worst):+.1f}%p)")
    if leak:
        print("- 🔴🔴 **누설이다** — (가)만 좋고 (나)·(다)가 5%p 이상 무너진다 "
              "→ 지시 1번대로 **J1 을 예측 시점 배당(개시) 기준으로 고정**한다.")
    else:
        print("- ✅ **누설로 보이지 않는다** — (나)·(다)가 (가)에서 5%p 이상 "
              "안 무너진다. 🔴 그래도 **J1 은 예측 시점 배당으로 고정**한다 "
              "(마감 배당은 예측 시점에 못 보는 수다 — 결과가 같아도 쓰면 안 된다).")
    # ── 🔴 세 판이 **같은 수**로 나왔으면 그 까닭을 적는다(#3)
    if len({x["n_sure"] for x in (a, b, c)}) == 1 and a["hit"] == b["hit"]:
        print("- 🔴🔴 **세 판이 같다 — 확신은 J1 을 쓰지 않는다.** 확신이 서는 "
              "줄은 `승무패 방향` 이고, 그 칸의 표본은 거의 전부 **재생본**"
              "(`보드무관`)이다. 재생본에는 보드가 없어 **J1 을 아예 못 센다** → "
              "그 줄의 묶음은 **H1 하나**로 정해진다. 🔴 그래서 69.5% 는 "
              "**J1 누설이 아니다**(J1 을 꺼도 같다).")
    # ── 전 표본 시험 결과로 J1 의 처분을 적는다
    said_c, said_o = full.get("close") or {}, full.get("open") or {}
    print()
    print("### J1 의 처분")
    if said_o.get("유효"):
        print(f"- ✅ **개시(예측 시점) 배당에서도 J1 은 유효다** — "
              f"{said_o['diff'] * 100:+.1f}%p "
              f"[{said_o['lo'] * 100:+.1f}, {said_o['hi'] * 100:+.1f}] "
              f"(걸림 {said_o['n_on']}) · 체급 {said_o.get('체급유효')}.")
        if said_c.get("diff") is not None:
            print(f"- 🔴 마감 배당({said_c['diff'] * 100:+.1f}%p)보다 **개시가 더 "
                  f"세다**({said_o['diff'] * 100:+.1f}%p) → J1 은 마감 배당이 만든 "
                  f"허상이 **아니다**.")
        print("- 🔴🔴 그래도 **J1 은 개시(예측 시점) 배당으로 고정한다** — "
              "마감 배당은 예측 시점에 **볼 수 없는 수**다(결과가 같아도 쓰면 "
              "안 된다 · 지시 1번).")
    else:
        print(f"- 🔴 **개시 배당에서는 J1 이 유효가 아니다**"
              f"({said_o.get('why')}) → J1 을 **끈다**(측정된 것만 쓴다 · §3-1).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
