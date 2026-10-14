"""🔴🔴 **확신 픽 구성표**(후속 지시 2026-10-14 2번).

```
PYTHONPATH=. uv run python tools/sure_mix.py
```

> 줄 종류별(승무패 · 핸디 기준선 · 언오버 기준선 · 추가 옵션) 확신 수 · 적중 ·
> **평균 보드 배당**.
> 확신 픽의 평균 배당이 1.85 근처인데 적중 69.5% 면 1번 결과가 나올 때까지
> **실전 금지 표시**.

🔴 배당은 **개시(예측 시점)** 를 쓴다 — 마감 배당은 예측 시점에 볼 수 없다
   (`win_open` · 지시 1번). 🔴 보드가 없는 줄은 **배당을 지어내지 않는다**(#4).
🔴 기대값·손익분기·켈리·금액은 **계산하지 않는다**(절대규칙) — 적중률과 평균
   배당을 **나란히** 적을 뿐이다.
⚠️ 확신은 `승무패 방향` 칸에서만 선다(핸디·언오버 칸은 의심 후 확률이 55% 를
   넘지 않아 문턱 0.58 에 닿지 못한다) — 그 사실도 표에 적는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 지시가 든 네 갈래
KINDS = ("승무패", "핸디 기준선", "언오버 기준선", "추가 옵션")
#: 🔴 지시 2번의 그 수 — 평균 배당이 이 근처면 실전 금지 표시
WATCH_PRICE = 1.85


def _kind(name: str) -> str:
    if name.startswith("핸디"):
        return "핸디 기준선"
    if name.startswith(("오버", "언더")):
        return "언오버 기준선"
    if name in ("홈 승", "원정 승", "무"):
        return "승무패"
    return "추가 옵션"


def _price(board: dict | None, name: str) -> float | None:
    """🔴 그 줄의 **개시(예측 시점)** 보드 배당. 없으면 `None`(지어내지 않는다)."""
    if not board:
        return None
    if name in ("홈 승", "무", "원정 승"):
        got = list(board.get("win_open") or [])
        i = {"홈 승": 0, "무": 1, "원정 승": 2}[name]
        val = got[i] if len(got) > i else None
        return float(val) if isinstance(val, (int, float)) else None
    if name.startswith("핸디"):
        box = dict(board.get("ah_open") or {})
        side = "home" if "home" in name else ("away" if "away" in name else "")
        val = box.get(side)
        return float(val) if isinstance(val, (int, float)) else None
    if name.startswith(("오버", "언더")):
        box = dict(board.get("ou_open") or {})
        val = box.get("over" if name.startswith("오버") else "under")
        return float(val) if isinstance(val, (int, float)) else None
    return None


def main() -> int:
    import statistics as stat

    import fit_doubt as fd
    import replays
    from cut_curve import lines_of

    from app.core import doubt as _db
    plate = _db.plates()
    if not plate:
        print("🔴 보정표가 없다 — `tools/fit_doubt.py` 를 먼저 돌려라")
        return 1
    conf = dict(_db.table().get("cuts") or {})
    cut, slack = float(conf.get("확신") or 0.58), float(
        conf.get("확신_하한_여유") or 0.03)
    hold = {str(x) for x in (dict(plate and {} or {}) or {})}
    import yaml
    for path in sorted((ROOT / "data/doubt_cal").glob("*.yaml")):
        got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        hold = {str(x) for x in (dict(got.get("meta") or {})
                                 .get("홀드아웃") or [])}
        if hold:
            break
    book = fd.boards()
    wide, why_w = fd.wide_rows()
    bad_of = {(str(o.get("league")), str(o.get("day")), str(o.get("home")),
               str(o.get("away"))): (1 if dict(o.get("flag") or {})["H1"]
                                     else 0)
              for o in wide if dict(o.get("flag") or {}).get("H1") is not None}
    rows, said = replays.load()
    rows = [r for r in rows if r.get("lam") and r.get("hit") is not None
            and str(r.get("season") or "") in hold]
    print("# 🔴🔴 확신 픽 구성표 — 줄 종류별")
    print()
    print(f"- 홀드아웃 **{sorted(hold)}**(표본 밖 · {len(rows)}경기) · "
          f"확신 문턱 **{cut:.2f}** · {why_w.split('·')[0].strip()}")
    print("- 🔴 배당은 **개시(예측 시점)** 다 — 마감 배당은 예측 시점에 못 본다.")
    print("- ⚠️ 보드가 없는 줄은 **배당을 지어내지 않는다**(⬜ 로 센다).")
    print("- 🔴 기대값·손익분기·켈리·금액은 **계산하지 않는다**(절대규칙) — "
          "적중률과 평균 배당을 **나란히** 적는다.")
    print()
    # ── 경기마다 **모든 보드 줄**을 판정해 확신만 모은다
    got_rows: list[dict] = []
    for r in rows:
        key = (str(r.get("league")), str(r.get("day")), str(r.get("home")),
               str(r.get("away")))
        if key not in bad_of:
            continue
        board = book.get((str(r.get("league")), str(r.get("season")),
                          str(r.get("home")), str(r.get("away"))))
        for name, p, ok in lines_of([float(x) for x in r["lam"][:2]],
                                    int(r["hg"]), int(r["ag"])):
            cell = _db.cell_for(plate, _db.kind_of(name), float(p),
                                bad_of[key])
            if cell is None or cell.get("보류"):
                continue
            if not (float(cell["실측"]) >= cut
                    and float(cell["lo"]) >= cut - slack):
                continue
            got_rows.append({"kind": _kind(name), "name": name,
                             "ok": int(bool(ok)),
                             "after": float(cell["실측"]),
                             "price": _price(board, name),
                             "has_board": board is not None})
    print("| 줄 종류 | 확신 | 적중 | 평균 의심 후 | 배당 있는 줄 | 평균 보드 배당 |")
    print("|---|---|---|---|---|---|")
    for kind in KINDS:
        part = [x for x in got_rows if x["kind"] == kind]
        if not part:
            print(f"| {kind} | 0 | ⬜ | ⬜ | ⬜ | ⬜ |")
            continue
        prices = [x["price"] for x in part if x["price"]]
        print(f"| **{kind}** | {len(part)} | "
              f"**{sum(x['ok'] for x in part) / len(part):.1%}** | "
              f"{stat.mean(x['after'] for x in part):.1%} | "
              f"{len(prices)} | "
              + (f"**{stat.mean(prices):.3f}**"
                 f"(중앙값 {stat.median(prices):.2f})" if prices else "⬜")
              + " |")
    print()
    all_p = [x["price"] for x in got_rows if x["price"]]
    n_all = len(got_rows)
    hit_all = (sum(x["ok"] for x in got_rows) / n_all) if n_all else None
    print(f"🔴 **전체 확신 {n_all}개** · 적중 "
          + (f"**{hit_all:.1%}**" if hit_all is not None else "⬜")
          + (f" · 평균 보드 배당 **{stat.mean(all_p):.3f}**"
             f"(배당 있는 줄 {len(all_p)}개 · 중앙값 "
             f"{stat.median(all_p):.2f})" if all_p else " · 배당 ⬜"))
    print()
    print("## 🔴 실전 여부")
    print()
    if all_p and abs(stat.mean(all_p) - WATCH_PRICE) <= 0.20:
        print(f"- 🔴🔴 **실전 금지 — 기록용**(지시 2번). 평균 보드 배당 "
              f"**{stat.mean(all_p):.2f}** 가 {WATCH_PRICE} 근처인데 적중은 "
              + (f"**{hit_all:.1%}**" if hit_all is not None else "⬜")
              + " 다 — 그 짝이 **너무 좋다**. 1번(누설 점검) 결과가 확정될 "
                "때까지 기록만 쌓는다.")
    elif all_p:
        print(f"- 평균 보드 배당 **{stat.mean(all_p):.2f}** 는 {WATCH_PRICE} "
              f"근처가 아니다 — 지시 2번의 **그 조건은 아니다**. 🔴 그래도 "
              f"문턱 운영은 **지시 4번**대로 `기록용` 이다.")
    else:
        print("- ⬜ **배당이 있는 확신 줄이 없다** — 평균 배당을 못 센다. "
              "🔴 판단은 1번·4번대로 **기록용**이다.")
    print()
    print("## ⚠️ 왜 승무패만 서나")
    print()
    for kind, key in (("핸디 기준선", _db.AH), ("언오버 기준선", _db.OU)):
        rows_k = dict(plate.get(key) or {})
        best = max((float(c["실측"]) for box in rows_k.values()
                    for c in (box or []) if not c.get("보류")), default=None)
        print(f"- `{kind}` — 보정표에서 가장 높은 칸이 "
              + (f"**{best:.1%}**" if best is not None else "⬜")
              + f" 다 → 문턱 **{cut:.0%}** 에 **닿지 못한다**.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
