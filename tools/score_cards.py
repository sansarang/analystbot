"""🔴🔴 **전 경기 평가 — 봇 vs 비교 기준** (사용자 지시 2026-10-12 3번).

> 봇(득실판) · 봇(xG판, 양 팀 xG 있는 경기만) · 비교 기준 둘 — **Elo만**(리그
> Elo→승무패 변환) · **리그 기본률**(홈/무/원정 비율). 지표: **브라이어·로그
> 손실·보정표(5%p 구간)**, 리그별. 시장 배당 있는 경기는 시장도 같은 표에
> (표시만). **봇이 Elo만 쓴 기준보다 못하면 그 사실을 첫 줄에 적는다.**

🔴 예측은 **카드에 적힌 그 수**를 쓴다(다시 돌리지 않는다) — 카드가 그때의 봇이다.
🔴 결과는 **fotmob 경기 페이지**에서 받는다(원장이 아니라 경기 결과가 기준이다).
⚠️ 표본이 작으면 **신뢰구간**을 함께 적는다(브라이어의 부트스트랩 95%).

쓰기:
    PYTHONPATH=. uv run python tools/score_cards.py
    PYTHONPATH=. uv run python tools/score_cards.py --glob "var/accept/*_card.md"
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import math
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger("score_cards")

#: 🔴 카드 머리 — `🏟 **A vs B** · 리그 · 10-11 16:00 KST`
HEAD = re.compile(r"^🏟 \*\*(.+?) vs (.+?)\*\* · (.+?) · (\d\d)-(\d\d) ")
#: 🔴 우리 확률 — `🎯 상성 확률 (S3)** — 홈 54% · 무 22% · 원정 24%`
OURS = re.compile(r"상성 확률 \(S3\)\*\* — 홈 (\d+)% · 무 (\d+)% · 원정 (\d+)%")
#: 🔴 xG 판 — `| xG 판 | 61% | 19% | 20% |`
XGB = re.compile(r"\|\s*xG 판\s*\|\s*(\d+)%\s*\|\s*(\d+)%\s*\|\s*(\d+)%")
#: 🔴 기준(Elo) — `- Elo: A **1472** · B **1499** · 차 -27 → 승 35% · 무 29% · 패 35%`
ELO = re.compile(r"Elo:.*?→ 승 (\d+)% · 무 (\d+)% · 패 (\d+)%")
#: 🔴 시장 — `| A 승 | … | 33% (2.75) |`
MKT = re.compile(r"시장 홈 (\d+)% · 원정 (\d+)%")


def _pct(*vals: str) -> list[float]:
    got = [float(v) / 100.0 for v in vals]
    tot = sum(got)
    return [x / tot for x in got] if tot else got


def read_card(path: Path) -> dict | None:
    """🔴 카드 한 장 → `{home, away, league, day, ours, xg, elo, market}`."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    head = HEAD.search(text)
    if not head:
        return None
    out: dict = {"file": path.name, "home": head.group(1).strip(),
                 "away": head.group(2).strip(), "league": head.group(3).strip(),
                 "day": f"2026-{head.group(4)}-{head.group(5)}"}
    got = OURS.search(text)
    if not got:
        return None
    out["ours"] = _pct(*got.groups())
    said = XGB.search(text)
    if said:
        out["xg"] = _pct(*said.groups())
    said = ELO.search(text)
    if said:
        out["elo"] = _pct(*said.groups())
    said = MKT.search(text)
    if said:
        h, a = float(said.group(1)) / 100.0, float(said.group(2)) / 100.0
        d = max(0.0, 1.0 - h - a)
        out["market"] = [x / (h + d + a) for x in (h, d, a)] if (h + a) else None
    return out


async def result_of(net, row: dict) -> tuple[int, str] | None:
    """🔴 그 경기의 **결과**(0 홈승·1 무·2 원정승)와 스코어. 못 찾으면 `None`."""
    from app.collect import fotmob as fm
    from app.core import discover as d
    idx = await fm.team_index(net)
    for name in (row["home"], row["away"]):
        for tid, slug in d._slug_hit(idx, name)[:3]:
            page = await net.get(fm.team_fixtures_url(tid, slug))
            rows = d.team_fixtures(getattr(page, "text", "") or "", tid)
            for one in rows:
                if not str(one.get("utc") or "").startswith(row["day"]):
                    continue
                if not one.get("finished"):
                    continue
                g = await net.get(fm.match_url(str(one.get("id") or "")))
                j = fm.payload(getattr(g, "text", "") or "") or {}
                goals = fm.goals_of(j)
                if not goals:
                    continue
                h = sum(1 for x in goals
                        if bool(x.get("home")) != bool(x.get("own_goal")))
                a = len(goals) - h
                return (0 if h > a else (1 if h == a else 2)), f"{h}-{a}"
    return None


def brier(p: list[float], hit: int) -> float:
    return sum((p[i] - (1.0 if i == hit else 0.0)) ** 2 for i in range(3))


def logloss(p: list[float], hit: int) -> float:
    return -math.log(max(1e-9, min(1.0, p[hit])))


def boot_ci(vals: list[float], *, n: int = 2000) -> tuple[float, float]:
    """🔴 부트스트랩 95% — 표본이 작을 때 **반드시** 함께 적는다."""
    if len(vals) < 2:
        return (float("nan"), float("nan"))
    rnd = random.Random(7)
    got = []
    for _ in range(n):
        said = [vals[rnd.randrange(len(vals))] for _ in vals]
        got.append(sum(said) / len(said))
    got.sort()
    return got[int(0.025 * n)], got[int(0.975 * n)]


def _bins(rows: list[tuple[float, int]]) -> str:
    """🔴 보정표 — **5%p 구간**(예측 확률 ↔ 실제 비율)."""
    box: dict[int, list[int]] = {}
    for p, hit in rows:
        key = min(19, int(float(p) * 20))
        box.setdefault(key, []).append(hit)
    out = ["    | 구간 | n | 예측 | 실제 |", "    |---|---|---|---|"]
    for key in sorted(box):
        got = box[key]
        out.append(f"    | {key * 5}~{key * 5 + 5}% | {len(got)} | "
                   f"{key * 5 + 2.5:.0f}% | {sum(got) / len(got):.0%} |")
    return "\n".join(out)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="var/accept/*_card.md")
    args = ap.parse_args()
    from app.net import Net
    net = Net(cache=True)
    rows: list[dict] = []
    seen: set[str] = set()
    for path in sorted(ROOT.glob(args.glob)):
        got = read_card(path)
        if not got:
            continue
        key = f"{got['home']}|{got['away']}|{got['day']}"
        if key in seen:          # 🔴 같은 경기 여러 카드 → **마지막 것만**
            rows = [r for r in rows if f"{r['home']}|{r['away']}|{r['day']}" != key]
        seen.add(key)
        rows.append(got)
    print(f"카드 {len(rows)}장(같은 경기는 마지막 카드만)")
    scored: list[dict] = []
    for one in rows:
        said = await result_of(net, one)
        if said is None:
            continue
        one["hit"], one["score"] = said
        scored.append(one)
    print(f"결과를 받은 경기 **{len(scored)}장**")
    if not scored:
        return
    # ── 리그 기본률(그 표본 자체의 홈/무/원정 비율)
    base = [sum(1 for r in scored if r["hit"] == i) / len(scored)
            for i in range(3)]
    print(f"리그 기본률(이 표본) — 홈 {base[0]:.0%} · 무 {base[1]:.0%} · "
          f"원정 {base[2]:.0%}")
    #: 🔴 1번 — **균등 기준**(33/33/33)을 더한다(사용자 지시 2026-10-12)
    even = [1 / 3, 1 / 3, 1 / 3]
    models = {
        "봇(득실판)": [(r["ours"], r["hit"]) for r in scored],
        "봇(xG판)": [(r["xg"], r["hit"]) for r in scored if r.get("xg")],
        "Elo만": [(r["elo"], r["hit"]) for r in scored if r.get("elo")],
        "리그 기본률": [(base, r["hit"]) for r in scored],
        "균등 33/33/33": [(even, r["hit"]) for r in scored],
        "시장(표시만)": [(r["market"], r["hit"]) for r in scored
                    if r.get("market")],
    }
    print()
    print("| 모형 | n | 브라이어 | 95% 구간 | 로그 손실 |")
    print("|---|---|---|---|---|")
    got_brier: dict[str, float] = {}
    for name, box in models.items():
        if not box:
            print(f"| {name} | 0 | — | — | — |")
            continue
        b = [brier(p, h) for p, h in box]
        ll = [logloss(p, h) for p, h in box]
        lo, hi = boot_ci(b)
        got_brier[name] = sum(b) / len(b)
        print(f"| {name} | {len(box)} | **{sum(b) / len(b):.4f}** | "
              f"{lo:.4f}~{hi:.4f} | {sum(ll) / len(ll):.4f} |")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **1번 짝지은 비교** — 모든 모형이 예측을 가진 **같은 경기만**
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 왜 — 모형마다 n 이 다르면(봇 11 · Elo만 8) 그 차이가 **표본 차이**인지
    #     **실력 차이**인지 가릴 수 없다. 짝지어야 차이의 구간을 낼 수 있다.
    pairs = [r for r in scored if r.get("elo")]
    print()
    print(f"**짝지은 비교**(모든 모형이 예측을 가진 경기 **{len(pairs)}장**)")
    if pairs:
        got_rate = [sum(1 for r in pairs if r["hit"] == i) / len(pairs)
                    for i in range(3)]
        print(f"그 표본의 실제 비율 — 홈 {got_rate[0]:.0%} · 무 "
              f"{got_rate[1]:.0%} · 원정 {got_rate[2]:.0%}")
        box = {"봇(득실판)": [(r["ours"], r["hit"]) for r in pairs],
               "Elo만": [(r["elo"], r["hit"]) for r in pairs],
               "리그 기본률": [(base, r["hit"]) for r in pairs],
               "균등 33/33/33": [(even, r["hit"]) for r in pairs]}
        print()
        print("| 모형 | 브라이어 | 로그 손실 |")
        print("|---|---|---|")
        for name, rows_p in box.items():
            b = [brier(p, h) for p, h in rows_p]
            ll = [logloss(p, h) for p, h in rows_p]
            print(f"| {name} | **{sum(b) / len(b):.4f}** | "
                  f"{sum(ll) / len(ll):.4f} |")
        # 🔴 **차이의 부트스트랩 구간** — 경기별 차이를 다시 뽑는다(짝 유지)
        print()
        print("| 차이(봇 − 기준) | 브라이어 차 | 95% 구간 | 0 을 품나 |")
        print("|---|---|---|---|")
        mine = [brier(r["ours"], r["hit"]) for r in pairs]
        for name in ("Elo만", "리그 기본률", "균등 33/33/33"):
            other = [brier(p, h) for p, h in box[name]]
            diff = [a - b for a, b in zip(mine, other, strict=True)]
            lo, hi = boot_ci(diff)
            print(f"| vs {name} | {sum(diff) / len(diff):+.4f} | "
                  f"{lo:+.4f}~{hi:+.4f} | "
                  + ("⚠️ 품는다(판정 못 한다)" if lo <= 0 <= hi
                     else ("🔴 **봇이 나쁘다**" if lo > 0 else "✅ 봇이 낫다"))
                  + " |")
    print()
    if "Elo만" in got_brier and got_brier.get("봇(득실판)", 9) > got_brier["Elo만"]:
        print(f"🔴🔴 **봇이 `Elo만` 쓴 기준보다 못하다** — 봇 "
              f"{got_brier['봇(득실판)']:.4f} vs Elo만 {got_brier['Elo만']:.4f}")
    elif "Elo만" in got_brier:
        print(f"✅ 봇이 `Elo만` 기준보다 낫다 — 봇 {got_brier['봇(득실판)']:.4f} "
              f"vs Elo만 {got_brier['Elo만']:.4f}")
    print()
    print("보정표 — 봇(득실판) 홈 확률")
    print(_bins([(r["ours"][0], 1 if r["hit"] == 0 else 0) for r in scored]))
    # ── 리그별
    print()
    print("| 리그 | n | 봇 브라이어 | Elo만 |")
    print("|---|---|---|---|")
    by: dict[str, list[dict]] = {}
    for r in scored:
        by.setdefault(r["league"], []).append(r)
    for lg, box in sorted(by.items(), key=lambda kv: -len(kv[1])):
        b = sum(brier(r["ours"], r["hit"]) for r in box) / len(box)
        said = [r for r in box if r.get("elo")]
        e = (sum(brier(r["elo"], r["hit"]) for r in said) / len(said)
             if said else None)
        print(f"| {lg} | {len(box)} | {b:.4f} | "
              + (f"{e:.4f} |" if e is not None else "— |"))


if __name__ == "__main__":
    asyncio.run(main())
