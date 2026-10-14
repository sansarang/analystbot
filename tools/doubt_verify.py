"""🔴🔴 **§5 검증** — 의심 후 확률이 **봇 원확률보다 실측에 가까운가**.

```
PYTHONPATH=. uv run python tools/doubt_verify.py
```

> 보정 곡선(의심 후 확률이 봇 원래보다 실측에 가까운가) · 성적(확신·역배
> 적중률·보류 비율·하루 수 · 줄 종류별 · 실보드/근사 따로) · 비교(원래 픽 vs
> 의심 후 픽 · **같은 하루 수**) · 시즌 교차 유지 · 무너지는 칸 폐기.

🔴 **표본 밖에서 센다** — 보정표는 `var/judge/atk_*.json`(1,470경기 · ELC·J1·
   PD·SA)로 적합했고, 이 검증은 `replays`(6,985경기 · 13리그)로 돌린다.
🔴 줄 확률·칸 찾기는 `core/picks.lines_of`·`core/doubt.cell_for` **그 함수**다.
🔴 ⚠️ 보정표의 `보드 핸디`·`보드 언오버` 칸은 **그 경기 보드의 메인 라인 하나**로
   쟀다 — 재생 줄에는 보드가 없으므로 **승무패 줄만** 검증한다
   (`cut_curve.AFTER_KINDS` 와 같은 까닭 · 사본 금지로 그것을 가져온다).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 보정 곡선을 그릴 봇 원확률 구간 — `tools/fit_doubt.BANDS` 그 목록이다


def brier(rows: list[tuple]) -> float:
    """🔴 브라이어 — `(확률, 맞았나)` 묶음. **작을수록** 실측에 가깝다."""
    if not rows:
        return float("nan")
    return sum((float(p) - float(ok)) ** 2 for p, ok in rows) / len(rows)


def main() -> int:
    import replays
    from cut_curve import AFTER_KINDS, lines_of
    from fit_doubt import BANDS, wilson

    from app.core import doubt as _db
    box = _db.plates()
    if not box:
        print("🔴 보정표가 없다 — `tools/fit_doubt.py` 를 먼저 돌려라")
        return 1
    rows, said = replays.load()
    rows = [r for r in rows if r.get("lam") and r.get("hit") is not None]
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **홀드아웃만 센다** — 판의 `홀드아웃` 칸을 읽는다
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 보정표를 재생본으로 적합했으면(`fit_doubt --wide`) 같은 재생본으로
    #     검증하는 것은 **표본 안**이다. 🔴 판이 뺀 시즌이 적혀 있으면 **그
    #     시즌만** 센다(그 사실을 머리에 적는다).
    import yaml
    hold: list[str] = []
    for path in sorted((ROOT / "data/doubt_cal").glob("*.yaml")):
        got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        hold = [str(x) for x in (dict(got.get("meta") or {})
                                 .get("홀드아웃") or [])]
        if hold:
            break
    print(f"# 🔴🔴 §5 검증 — {said}")
    print()
    if hold:
        rows = [r for r in rows if str(r.get("season") or "") in set(hold)]
        print(f"- 🔴🔴 **홀드아웃 {hold} 만 센다** — 보정표가 그 시즌을 빼고 "
              f"적합했다(표본 밖 · 남은 경기 **{len(rows)}**).")
    else:
        print("- 🔴 **표본 밖이다** — 보정표는 1,470경기(ELC·J1·PD·SA)로 "
              "적합했고 이 검증은 위 재생본으로 돌린다.")
    print(f"- ⚠️ **승무패 줄만** 센다 — 보드 핸디·언오버 칸은 그 경기 보드의 "
          f"메인 라인 하나로 쟀고 재생 줄에는 보드가 없다({', '.join(AFTER_KINDS)}).")
    print()
    # ── 경기마다 **봇이 앞세운 승무패 줄** 하나
    got: list[dict] = []
    for r in rows:
        said_lines = [x for x in lines_of([float(x) for x in r["lam"][:2]],
                                          int(r["hg"]), int(r["ag"]))
                      if x[0] in AFTER_KINDS]
        if not said_lines:
            continue
        name, p, ok = max(said_lines, key=lambda x: x[1])
        cell = _db.cell_for(box, _db.kind_of(name), float(p), 0)
        got.append({"name": name, "p": float(p), "ok": int(bool(ok)),
                    "after": (None if cell is None or cell.get("보류")
                              else float(cell["실측"])),
                    "cell": ("" if cell is None else str(cell.get("구간"))),
                    "day": str(r.get("day")), "league": str(r.get("league")),
                    "season": str(r.get("season") or "")})
    pair = [x for x in got if x["after"] is not None]
    print(f"- 줄 {len(got)}개 중 칸이 있는 줄 **{len(pair)}개**"
          f"({len(pair) / max(1, len(got)):.0%})")
    print()
    # ── ① 보정 곡선 — 구간마다 봇 · 의심 후 · 실측
    print("## ① 보정 곡선 — 봇 원확률 ↔ 의심 후 ↔ 실측")
    print()
    print("| 봇 구간 | 줄 | 봇 평균 | 의심 후 | 실측 | 95% 구간 | "
          "봇 오차 | 의심 후 오차 | 더 가까운 쪽 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for lo, hi in BANDS:
        part = [x for x in pair if lo <= x["p"] < hi]
        if not part:
            print(f"| {lo:.0%}~{hi - 0.01:.0%} | 0 | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ "
                  f"| ⬜ | ⬜ |")
            continue
        n = len(part)
        real, r_lo, r_hi = wilson(sum(x["ok"] for x in part), n)
        p_bot = sum(x["p"] for x in part) / n
        p_aft = sum(x["after"] for x in part) / n
        e_bot, e_aft = abs(p_bot - real), abs(p_aft - real)
        print(f"| {lo:.0%}~{hi - 0.01:.0%} | {n} | {p_bot:.1%} | "
              f"**{p_aft:.1%}** | {real:.1%} | [{r_lo:.1%}, {r_hi:.1%}] | "
              f"{e_bot:.1%} | {e_aft:.1%} | "
              + ("🔴 **의심 후**" if e_aft < e_bot else "봇") + " |")
    print()
    b_bot = brier([(x["p"], x["ok"]) for x in pair])
    b_aft = brier([(x["after"], x["ok"]) for x in pair])
    print(f"- 🔴 **브라이어** — 봇 **{b_bot:.4f}** ↔ 의심 후 **{b_aft:.4f}** "
          f"({'의심 후가 낫다' if b_aft < b_bot else '봇이 낫다'} · "
          f"차 {b_aft - b_bot:+.4f})")
    e_bot = sum(abs(x["p"] - x["ok"]) for x in pair) / max(1, len(pair))
    e_aft = sum(abs(x["after"] - x["ok"]) for x in pair) / max(1, len(pair))
    print(f"- 절대 오차 — 봇 {e_bot:.4f} ↔ 의심 후 {e_aft:.4f}")
    print()
    # ── ② 성적 — 확신 · 보류 · 하루 수 · **같은 하루 수**로 비교
    print("## ② 성적 — 확신 · 보류 · 하루 수")
    print()
    conf = dict(_db.table().get("cuts") or {})
    cut = conf.get("확신")
    slack = float(conf.get("확신_하한_여유") or 0.0)
    days = len({x["day"] for x in got}) or 1
    sure = []
    for x in pair:
        cell = _db.cell_for(box, _db.kind_of(x["name"]), x["p"], 0)
        if cell is None or cut is None:
            continue
        if (float(cell["실측"]) >= float(cut)
                and float(cell["lo"]) >= float(cut) - slack):
            sure.append(x)
    print(f"- **확신** {len(sure)}개 · 적중 "
          + (f"**{sum(x['ok'] for x in sure) / len(sure):.1%}**"
             if sure else "⬜")
          + f" · 하루 {len(sure) / days:.2f}개")
    print(f"- **보류** {len(got) - len(sure)}개"
          f"({(len(got) - len(sure)) / max(1, len(got)):.0%})")
    # 🔴 **같은 하루 수**로 옛 픽과 견준다(§5 그 줄)
    old = sorted(got, key=lambda x: -x["p"])[:len(sure)]
    a = (sum(x["ok"] for x in old) / len(old)) if old else None
    b = (sum(x["ok"] for x in sure) / len(sure)) if sure else None
    print(f"- 🔴 **같은 하루 수로 비교** — 봇 원확률 상위 {len(old)}개 적중 "
          + (f"**{a:.1%}**" if a is not None else "⬜")
          + " ↔ 확신 " + (f"**{b:.1%}**" if b is not None else "⬜")
          + ((" · 🔴 **차이 없다**" if abs(a - b) < 1e-9
              else f" · 차 **{(b - a) * 100:+.1f}%p**")
             if (a is not None and b is not None) else ""))
    if a is not None and b is not None and abs(a - b) < 1e-9:
        print("  ⚠️ 🔴🔴 **보정은 수를 고치고 순서를 안 고친다** — 칸이 봇 확률에"
              " 대해 **단조**라 고르는 줄이 같다. 그래서 2단이 바꾸는 것은"
              " *어느 줄을 고르나*가 아니라 **그 줄에 얼마를 주나**다(그 수가"
              " 확신 문턱을 뜻 있게 만든다).")
    print()
    # ── ③ 시즌 교차 — 같은 칸이 시즌마다 유지되나
    print("## ③ 시즌 교차 — **판의 칸**이 시즌마다 유지되나")
    print()
    print("🔴 홀드아웃이 한 시즌이면 여기서는 교차를 **못 잰다** — 교차는 "
          "`tools/fit_doubt.py` 가 **칸마다** 적어 둔다(`시즌교차`).")
    print()
    print("| 줄 종류 | 의심 | 구간 | 경기 | 실측 | 시즌교차 | "
          "시즌별 실측/봇(n) |")
    print("|---|---|---|---|---|---|---|")
    for kind, rows_k in sorted(box.items()):
        for bucket, cells in sorted(dict(rows_k).items()):
            for one in list(cells or []):
                cross = one.get("시즌교차")
                said_s = " · ".join(
                    f"{k} {float(v['실측']):.0%}/{float(v['봇평균']):.0%}"
                    f"({v['n']})"
                    for k, v in dict(one.get("시즌별") or {}).items())
                print(f"| {kind} | {bucket} | {one.get('구간')} | "
                      f"{one.get('n')} | {float(one['실측']):.1%} | "
                      + ("✅ 유지" if cross is True
                         else ("🔴 **뒤집힌다**" if cross is False
                               else "⬜ 못 쟀다"))
                      + f" | {said_s or '⬜'} |")
    print()
    print("| 홀드아웃 시즌 | 확신 | 적중 |")
    print("|---|---|---|")
    by: dict[str, list] = {}
    for x in sure:
        by.setdefault(x["season"] or "미상", []).append(x)
    for key in sorted(by):
        part = by[key]
        print(f"| {key} | {len(part)} | "
              f"**{sum(y['ok'] for y in part) / len(part):.1%}** |")
    print()
    # ── ④ 줄 종류별 · 리그별(무너지는 칸을 찾는다)
    print("## ④ 리그별 — 무너지는 칸을 찾는다")
    print()
    print("| 리그 | 확신 | 적중 | 95% 구간 |")
    print("|---|---|---|---|")
    lg: dict[str, list] = {}
    for x in sure:
        lg.setdefault(x["league"], []).append(x)
    for key in sorted(lg, key=lambda k: -len(lg[k])):
        part = lg[key]
        p, a, b = wilson(sum(y["ok"] for y in part), len(part))
        mark = " 🔴 **무너진다**" if b < float(cut or 0) else ""
        print(f"| `{key}` | {len(part)} | **{p:.1%}** | "
              f"[{a:.1%}, {b:.1%}]{mark} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
