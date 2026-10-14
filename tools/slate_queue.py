"""🔴🔴 **P0 슬레이트 스케줄러**(수정 지시 2026-10-13 밤 P0).

```
PYTHONPATH=. python tools/slate_queue.py --comp league:ACLE
PYTHONPATH=. python tools/slate_queue.py --comp league:ACLE --run
```

> 슬레이트 스케줄러: 그날 대상 경기 **전부를 킥오프 순으로 큐에 올리고** 각 단계
> 시각을 카드 머리에 찍는다(T−24h/T−3h/XI 확정 판 각각).
> 사전 실행: T−24h 기본 → T−3h 갱신 → 확정 XI 뜨면 즉시 ⑲.

🔴 단계 시각을 세는 곳은 `app/core/slate.py` **하나**다(사본 금지).
🔴 `--run` 은 **실제 핸들러**(`cmd_deep`)를 부른다(CLAUDE.md #12 프로브 금지) ·
   카드 한 장에 **15분 상한**(`core/deadline.CARD_CAP_MIN`)을 건다.
⚠️ 킥오프를 지난 경기는 **돌리지 않는다**(사후 기록용 카드를 새로 만들지 않는다) —
   그 사실을 큐에 적는다.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

KST = timezone(timedelta(hours=9))


async def fixtures(comp: str, *, hours: float, back: float = 3.0
                   ) -> tuple[list[dict], str]:
    """🔴 그 대회의 **다가오는 경기**(지금부터 `hours` 안) — 일정 한 장에서.

    ⚠️ `back` 은 **뒤로 얼마까지** 볼지다(기본 3시간 — 돌고 있는 경기). 실측에
       쓰는 도구는 **이미 끝난 그날 슬레이트**를 다시 세야 해서 늘려 부른다
       (`tools/board_ladder.py`) — 🔴 큐는 기본값 그대로다(사후 카드 금지).
    """
    from app.collect import fotmob as fm
    from app.core import competition as _cp
    from app.net import Net
    ids = [str(x) for x in ((_cp.row_of(comp).get("sources") or {})
                            .get("fotmob_ids") or [])]
    if not ids:
        return [], f"🔴 `{comp}` 의 fotmob id 가 표에 없다"
    net = Net(cache=True)
    rows = await fm.league_matches(net, ids[0])
    now = datetime.now(timezone.utc)
    out: list[dict] = []
    for r in rows:
        said = str(r.get("utc") or "")
        if not said:
            continue
        when = datetime.fromisoformat(said.replace("Z", "+00:00"))
        if not (now - timedelta(hours=back) <= when
                <= now + timedelta(hours=hours)):
            continue
        out.append({"name": f"{r.get('home')} vs {r.get('away')}",
                    "kickoff": when, "finished": bool(r.get("finished"))})
    return out, f"일정 {len(rows)}경기 중 창 안 **{len(out)}경기**"


async def main(argv: list[str]) -> int:
    from app.core import deadline as _dl
    from app.core import slate as _sl
    ap = argparse.ArgumentParser()
    ap.add_argument("--comp", action="append", required=True)
    ap.add_argument("--hours", type=float, default=36.0)
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args(argv[1:])
    now = datetime.now(timezone.utc)
    rows: list[dict] = []
    print("# 🔴🔴 P0 슬레이트 큐")
    print()
    for comp in args.comp:
        got, why = await fixtures(comp, hours=args.hours)
        print(f"- `{comp}` — {why}")
        for one in got:
            one["comp"] = comp
        rows += got
    box = _sl.queue(rows, now=now)
    print()
    print("| 킥오프(KST) | 경기 | 대회 | 지금 단계 | 기본 T−24h | 갱신 T−3h | "
          "XI T−1h |")
    print("|---|---|---|---|---|---|---|")
    for one in box:
        t = one["times"]
        src = next((r["comp"] for r in rows
                    if r["name"] == one["name"]), "")
        print(f"| {one['kickoff'].astimezone(KST):%m-%d %H:%M} | "
              f"{one['name']} | `{src}` | **{one['stage']}** | "
              + " | ".join(f"{t[k].astimezone(KST):%m-%d %H:%M}"
                           for k in ("기본", "갱신", "XI")) + " |")
    print()
    # 🔴 큐 줄에 **대회**를 싣는다 — `_sl.queue` 는 그 칸을 안 들고 오므로
    #    칠 표 재료의 `league` 가 **빈 글자**였다(실측 2026-10-14 시험표).
    for one in box:
        one["comp"] = next((r["comp"] for r in rows
                            if r["name"] == one["name"]), "")
    due = [one for one in box if one["stage"] in ("기본", "갱신", "XI")]
    print(f"🔴 **지금 돌릴 경기 {len(due)}건** — "
          + (" · ".join(f"{x['name']}({x['stage']})" for x in due)
             if due else "없다"))
    gone = [one for one in box if one["stage"] == "사후"]
    if gone:
        print(f"⚠️ **킥오프를 지났다 {len(gone)}건** — 새 카드를 만들지 않는다"
              f"(사후 기록용) — " + " · ".join(x["name"] for x in gone))
    if not args.run:
        print()
        print("⏸ `--run` 을 주면 **실제 핸들러**(`cmd_deep`)로 차례로 돈다 "
              f"· 카드 한 장 상한 **{_sl.CARD_CAP_MIN:g}분**")
        return 0
    # ── 🔴 실제 핸들러로 차례로 돈다(프로브 금지 · #12)
    import app.bot.main as _bm
    from app import cassette
    import os
    # 🔴 카드를 **받아야** 칠 표를 세울 수 있다 → 연결을 하나 연다
    from app.config import get_settings
    from app.db import get_pool
    pool = await get_pool(get_settings().database_url)
    rows_pick: list[dict] = []
    for one in due:
        said = one["name"]
        print(f"\n▶ {said} — {one['stage']} 단계 시작 "
              f"{datetime.now(KST):%H:%M:%S} KST", flush=True)
        os.environ[cassette.MATCH_ENV] = said
        clock = _dl.Deadline(_sl.CARD_CAP_MIN)
        try:
            # 🔴 **실제 핸들러**를 쓰면서 카드를 **받는다**(칠 표 재료가 필요하다)
            body, card = await _bm._v6_card(
                pool, said=said, again=False, deep=True, want_ref=True,
                # 🔴🔴 **보드 캡처**(후속 지시 2026-10-14h §1) — 있으면 넘긴다.
                #    칠 표 후보는 **보드에 있는 줄만**이므로 이것이 없으면 그
                #    경기는 표에서 빠진다(표시만).
                board_text=board_text_of(said))
            for chunk in _bm._split(body):
                print(chunk)
            got = pick_row(said, one, card)
            if got:
                rows_pick.append(got)
        except Exception as exc:                            # noqa: BLE001
            print(f"🔴 {said} — 카드가 터졌다: {exc!r:.200}")
        print(f"◀ {said} — {clock.said_of()}", flush=True)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **슬레이트 끝 — 칠 표**(후속 지시 2026-10-14g §5)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 고르는 것은 **문턱만**이다(공격 계층은 실효 측정에서 문턱을 못 이겼다 ·
    #     `core/picks` 머리글). 공격 판정은 **표에 적기만** 한다.
    if rows_pick:
        from app.core import picks as _pk
        out = _pk.of(rows_pick)
        print()
        print(_pk.said_of(out))
        save_picks(out, rows_pick)
    return 0


def board_text_of(name: str) -> str:
    """🔴 `var/board/<날짜>.yaml` 에서 그 경기 보드 글을 찾는다(없으면 빈 글자).

    🔴 꼴 — `{경기 이름: "승무패 2.15 3.25 3.40\n핸디 1.5 1.80 2.05\n…"}`.
    ⚠️ 이름은 **느슨하게** 맞춘다(`core/teamname.share`) — 보드를 손으로 적을 때
       약칭을 쓰기 때문이다. 못 찾으면 **빈 글자**다(지어내지 않는다).
    """
    import yaml
    from datetime import date as _date

    from app.core import teamname as _tn
    for day in (_date.today(), _date.today().replace(
            day=_date.today().day)):
        path = ROOT / "var/board" / f"{day.isoformat()}.yaml"
        if not path.is_file():
            continue
        box = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if name in box:
            return str(box[name])
        for key, val in box.items():
            if _tn.share(str(key), name) >= 0.5:
                return str(val)
    return ""


def pick_row(name: str, one: dict, card) -> dict | None:
    """🔴 카드 하나 → 칠 표 한 줄(줄 확률은 **격자 하나**에서 · 사본 금지).

    🔴🔴 **기계 보류 경기도 줄을 낸다**(의심 검증 v2 §2 · CLAUDE.md #3).
       ⚠️ 실측 2026-10-14(노리치–사우샘프턴): 그 카드는 격자가 없어서 이 함수가
          `None` 을 돌려줬고, 그래서 칠 표가 *"경기 3개"* 라고만 적었다 —
          **보류로 빠진 경기가 어디에도 안 남았다**(조용한 0). 🔴 격자가 없어도
          깃발만 실은 줄을 내면 `core/picks.of` 가 **이름으로** 적는다.
    """
    from app.core import picks as _pk2
    held = bool(getattr(card, "machine_hold", False))
    # 🔴 격자·줄 이름을 세는 곳은 `core/picks` **하나**다(사본 금지)
    grid = _pk2.grid_of(dict(getattr(card, "matchup", None) or {}))
    if not grid:
        # 🔴 격자가 없다 — 보류 경기면 **그 사실을 적은 줄**을 낸다
        if not held:
            return None
        return {"match": name, "league": str(one.get("comp") or ""),
                "board_lines": [], "lines": {},
                "board_why": "⬜ 격자가 없다(1단 기계 보류)",
                "kickoff": f"{one['kickoff'].astimezone(KST):%H:%M}",
                "machine_hold": True,
                "machine": str(getattr(card, "machine", "") or ""),
                "verdict": "",
                "board": str(getattr(card, "board_source", "") or "")}
    lines = _pk2.lines_of(grid)
    # 🔴 보드 줄은 **파이프라인이 센 칸**을 읽는다(사본 금지 · `core/picks`)
    said_board = [str(x) for x in (getattr(card, "board_lines", None) or [])]
    return {"match": name, "league": str(one.get("comp") or ""),
            "board_lines": said_board,
            "board_why": ("보드 줄 %d개" % len(said_board) if said_board
                          else "⬜ 보드가 없다 — 칠 표에서 뺀다"),
            "kickoff": f"{one['kickoff'].astimezone(KST):%H:%M}",
            "lines": lines,
            # 🔴🔴 **1단 기계 점검**(의심 검증 v2 §2) — 보류면 `core/picks` 가
            #    그 경기를 **안 받는다**(확신·역배 둘 다 금지 · 다리도 금지).
            #    ⚠️ 옛 `card.attack`(공격 계층)은 **지웠다** — 그 칸을 읽던
            #       `verdict` 는 늘 빈 글자였다(죽은 줄이었다).
            "machine_hold": bool(getattr(card, "machine_hold", False)),
            "machine": str(getattr(card, "machine", "") or ""),
            # 🔴🔴 **2단 판정**(의심 검증 v2 §4) — 칠 표는 **확신·역배만** 받는다
            "doubt_picks": dict(getattr(card, "doubt_picks", None) or {}),
            "doubt": str(getattr(card, "doubt", "") or ""),
            "verdict": "",
            "board": str(getattr(card, "board_source", "") or "")}


def save_picks(out, rows: list[dict]) -> None:
    """🔴 칠 표를 **적어 둔다** — `score_cards` 가 적중률을 누적한다(§5)."""
    import yaml
    from datetime import date as _date
    path = ROOT / "var/picks" / f"{_date.today().isoformat()}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    said = {"singles": [vars(x) for x in out.singles],
            "parlays": [[vars(x) for x in got] for got in out.parlays],
            "why": out.why, "n_matches": len(rows),
            # 🔴 **재료 줄도 적는다** — 봇 `/칠표` 가 `core/picks.of` 로 **같은
            #    식으로 다시** 고른다(사본 금지 · 문턱이 바뀌면 그대로 따라온다)
            "rows": [dict(x) for x in rows]}
    path.write_text(yaml.safe_dump(said, allow_unicode=True,
                                   sort_keys=False), encoding="utf-8")
    print(f"🔴 **칠 표를 적었다** — `{path.relative_to(ROOT)}`"
          f"(단폴 {len(out.singles)} · 다폴 {len(out.parlays)})")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
