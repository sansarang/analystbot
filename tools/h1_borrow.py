"""🔴🔴 **H1 을 국내 리그 표로 빌려도 되나** — 지시 2026-10-14 검증.

> *"순위 및 승률을 가지고 와서 의심 단계를 만들어봐라"*

컵·대륙 경기는 **그 대회 순위표가 없다**(J리그컵은 덤프에 아예 없다). 그래서 두
팀의 **국내 리그 표를 빌린다.** 🔴 빌리기는 지시 2026-10-14 가 *"검증 없는 빌리기
금지 → 그 대회 과거 경기로 검증한 바닥은 쓴다"* 로 뜻을 바꾼 그 규칙을 따른다 —
**빌린 줄만 따로 재서** 효과가 남는지 본다.

🔴 깃발은 `app/core/standings.h1_of` 가 센다(적합·운영 한 함수 · 사본 금지).
🔴 누설 금지 — 순위표는 그 경기 **앞**까지만 쌓는다(C11).

    PYTHONPATH=.:tools uv run python tools/h1_borrow.py > var/accept/h1_borrow.log
"""
from __future__ import annotations

import math

import replays

from app.core import standings


def wilson_diff(on: list[int], off: list[int]) -> tuple[float, float, float]:
    """두 비율 차와 95% 구간(정규 근사)."""
    ho, hf = sum(on) / len(on), sum(off) / len(off)
    se = math.sqrt(ho * (1 - ho) / len(on) + hf * (1 - hf) / len(off))
    return ho - hf, (ho - hf) - 1.96 * se, (ho - hf) + 1.96 * se


def report(name: str, got: list[tuple]) -> None:
    on = [ok for ok, f in got if f]
    off = [ok for ok, f in got if not f]
    if not on or not off:
        print(f"\n**{name}** — 🔴 표본 부족(걸림 {len(on)} · 안 걸림 {len(off)})")
        return
    d, lo, hi = wilson_diff(on, off)
    ok = "✅ **유효**(구간이 0 을 안 품는다)" if lo * hi > 0 else "⬜ 구간이 0 을 품는다"
    print(f"\n**{name}**")
    print(f"- 걸린 경기 **{len(on)}** — 봇 적중 **{sum(on) / len(on) * 100:.1f}%**")
    print(f"- 안 걸린 것 **{len(off)}** — 봇 적중 **{sum(off) / len(off) * 100:.1f}%**")
    print(f"- 차 **{d * 100:+.1f}%p** [{lo * 100:+.1f}, {hi * 100:+.1f}] — {ok}")


def main() -> int:
    rows, why = replays.load()
    rows = [r for r in rows if r.get("ours") and r.get("hit") is not None
            and r.get("hg") is not None]
    rows.sort(key=lambda r: str(r.get("day")))
    print("# H1 빌리기 검증")
    print(f"\n{why[:160]}\n\n- 쓸 수 있는 줄 **{len(rows)}**")

    import collections
    by_lg: dict = collections.defaultdict(list)
    same: list[tuple] = []
    borrow: list[tuple] = []
    same_w: list[tuple] = []
    n_none = 0
    box, _w = standings.table_at()          # 🔴 한 번 쌓고 날짜로 걸러 쓴다
    # 🔴 날짜별로 다시 쌓는 것은 너무 느리다 → 날짜 순으로 돌며 직접 센다
    tbl: dict[tuple, standings.Row] = {}

    def latest(team: str, league: str, day: str):
        """🔴 `standings.latest_of` 와 **같은 규칙**(지금 시즌 · 낡은 표 제외)."""
        got = [v for k, v in tbl.items()
               if k[0] == league and k[2] == team and v.n >= standings.MIN_GAMES
               and standings._days(v.last, day) <= standings.STALE_DAYS]
        return max(got, key=lambda r: (r.last, r.n)) if got else None

    from app.core import domesticelo
    for r in rows:
        lg, se = str(r["league"]), str(r["season"])
        h, a = str(r["home"]), str(r["away"])
        ours = [float(x) for x in r["ours"]]
        pick = max(range(3), key=lambda i: ours[i])
        side = "home" if pick == 0 else ("away" if pick == 2 else "")
        ok = int(pick == int(r["hit"]))
        if side:
            d0 = str(r["day"])
            A, B = latest(h, lg, d0), latest(a, lg, d0)
            if A is not None and B is not None:
                mine, other = (A, B) if side == "home" else (B, A)
                same.append((ok, mine.ppg < other.ppg))
                same_w.append((ok, mine.wr < other.wr))
                by_lg[lg].append((ok, mine.ppg < other.ppg))
            else:
                la, _x = domesticelo.league_of(h)
                lb, _y = domesticelo.league_of(a)
                A2 = latest(h, la, d0) if la else None
                B2 = latest(a, lb, d0) if lb else None
                if A2 is not None and B2 is not None:
                    mine, other = (A2, B2) if side == "home" else (B2, A2)
                    borrow.append((ok, mine.ppg < other.ppg))
                else:
                    n_none += 1
        hg, ag = int(r["hg"]), int(r["ag"])
        d = str(r["day"])
        for team, ish in ((h, True), (a, False)):
            won = (hg > ag) == ish and hg != ag
            one = tbl.setdefault((lg, se, team),
                                 standings.Row(team=team, league=lg, season=se))
            one.p += 3 if won else (1 if hg == ag else 0)
            one.n += 1
            one.w += int(won)
            one.d += int(hg == ag)
            one.last = max(one.last, d)

    print(f"- 같은 대회 표 **{len(same)}** · 국내 표 빌림 **{len(borrow)}** · "
          f"못 셈 **{n_none}**")
    report("① 같은 대회 순위표 (적합이 쓴 그것)", same)
    report("② 국내 리그 표를 **빌린 줄만**", borrow)
    report("③ 둘 합친 것 — 승점/경기(판정 기준)", same + borrow)
    report("④ 같은 대회 — **승률**로 재면(참고 · 판정 미사용)", same_w)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **리그별로 쪼갠다** — 오늘 경기 리그에서 서는지 봐야 한다
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 H1 을 올릴 때 쓴 잣대는 *"전체 + 체급 통제 뒤에도 남는다"* 였다.
    #     **리그**도 통제다 — 그 리그에서 안 서면 그 리그 카드에 쓸 수 없다.
    print("\n## 리그별 (같은 대회 표)")
    print("\n| 리그 | 걸림 | 적중 | 안 걸림 | 적중 | 차 | 구간 | |")
    print("|---|---|---|---|---|---|---|---|")
    for lg in sorted(by_lg, key=lambda k: -len(by_lg[k])):
        got = by_lg[lg]
        on = [o for o, f in got if f]
        off = [o for o, f in got if not f]
        if len(on) < 15 or len(off) < 15:
            print(f"| `{lg}` | {len(on)} | — | {len(off)} | — | — | 표본 부족 | ⬜ |")
            continue
        d, lo, hi = wilson_diff(on, off)
        mark = "✅" if lo * hi > 0 else "⬜"
        print(f"| `{lg}` | {len(on)} | {sum(on) / len(on) * 100:.1f}% | {len(off)} | "
              f"{sum(off) / len(off) * 100:.1f}% | **{d * 100:+.1f}%p** | "
              f"[{lo * 100:+.1f}, {hi * 100:+.1f}] | {mark} |")
    print("\n## 판정")
    print("- ② 가 ✅ 면 빌리기를 **쓴다**(지시 2026-10-14 ②: 검증된 대체 바닥).")
    print("- 🔴 ② 의 **걸린 줄 수**를 함께 읽어라 — 얇으면 카드에 그 사실을 적는다.")
    print("- 🔴 판정 기준은 **승점/경기**다(③ 이 ④ 보다 강하면 그쪽을 쓴다).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
