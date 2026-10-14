"""🔴🔴 **§6 시험표** — 경기별 보드 출처 · 1단 · 봇 확률 · 의심 후 · 판정.

```
PYTHONPATH=. uv run python tools/trial_table.py            # 가장 최근 칠 표 재료
PYTHONPATH=. uv run python tools/trial_table.py --day 2026-10-14
```

> 경기마다: 보드 출처 · 1단 · 봇 확률 · 유효 의심 · 의심 후 확률 · 판정 · 결과.

🔴 **카드를 다시 돌리지 않는다** — 슬레이트가 적어 둔 **재료 줄**(`var/picks/
   <날짜>.yaml` 의 `rows`)에 `lines`·`board_lines`·`machine_hold` 가 있고,
   `core/doubt.judge` 는 **순수 함수**다. 그래서 **지금 설정**으로 다시 판정한다.
   ⚠️ 그 로그를 찍을 때의 문턱과 지금 문턱이 다를 수 있다 — 표는 **지금 문턱**을
      적는다(어느 문턱으로 읽은 표인지 머리에 찍는다).
🔴 결과(스코어)는 **아직 끝나지 않은 경기면 ⬜** 다 — 지어내지 않는다(#3).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
BOX = ROOT / "var/picks"


def main(argv: list[str]) -> int:
    import yaml

    from app.core import doubt as _db
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    args = ap.parse_args(argv[1:])
    paths = sorted(BOX.glob("*.yaml"))
    if args.day:
        paths = [p for p in paths if p.stem == args.day]
    if not paths:
        print(f"🔴 칠 표 재료가 없다 — `{BOX.relative_to(ROOT)}/<날짜>.yaml`")
        return 1
    path = paths[-1]
    got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = [dict(x) for x in (got.get("rows") or [])]
    conf = dict(_db.table().get("cuts") or {})
    ok_live, said_live = _db.live()
    print(f"# 🔴🔴 §6 시험표 — `{path.stem}`")
    print()
    if not ok_live:
        print(f"{said_live}")
        print()
    print(f"- 재료 `{path.relative_to(ROOT)}` · 경기 **{len(rows)}**")
    print(f"- 지금 문턱 — 확신 **{conf.get('확신')}** · 다리 "
          f"**{conf.get('다리')}**(의심 후 자) · 유효 의심 "
          f"**{', '.join(_live_vars()) or '없다'}**")
    print("- ⚠️ 카드를 다시 돌리지 않았다 — 슬레이트가 적어 둔 **재료 줄**로 "
          "`core/doubt.judge`(순수 함수)를 **지금 설정으로** 다시 돌렸다.")
    if all(not str(x.get("league") or "") for x in rows):
        print("- ⚠️ **대회 칸이 비었다** — 이 재료는 `slate_queue` 가 큐 줄에 "
              "대회를 싣기 **전**에 적은 것이다(고쳤다 · 다음 실행부터 들어온다).")
    print()
    print("| 경기 | 대회 | 보드 | 1단 | 1단 사유 | 승무패 최고 | 의심 후 | "
          "칸 | 판정 |")
    print("|---|---|---|---|---|---|---|---|---|")
    n_sure = n_fade = n_hold = 0
    for one in sorted(rows, key=lambda x: str(x.get("kickoff"))):
        said_m = str(one.get("machine") or "")
        mark = ("🔴 보류" if one.get("machine_hold")
                else ("✅ 정상" if "정상" in said_m else "⬜"))
        lines = {str(k): float(v) for k, v in
                 dict(one.get("lines") or {}).items() if v is not None}
        want = [str(x) for x in (one.get("board_lines") or [])]
        use = {k: v for k, v in lines.items() if not want or k in want}
        said = _db.judge(use, bad=[],
                         machine_hold=bool(one.get("machine_hold")))
        # 🔴🔴 **승무패 줄**을 보인다 — 확신·역배가 서는 자리가 거기다(지시 2번:
        #    핸디·언오버는 봇 원확률로 후보가 아니고 의심 후 칸도 안 선다).
        #    ⚠️ 종전 표는 *봇 최고 줄*(거의 핸디)을 보여 줘서 **읽히지 않았다**.
        wins = [r for r in said.rows if r.slot is not None]
        best = max((r for r in said.rows if r.verdict in (_db.SURE,
                                                          _db.FADE)),
                   key=lambda r: (r.p_after or 0.0), default=None)
        show = best or (max(wins, key=lambda r: (r.p_bot or 0.0))
                        if wins else None)
        # 🔴 1단 사유 — **첫 🔴 조각**만 짧게(전문은 카드에 있다)
        why_m = "✅"
        if one.get("machine_hold"):
            # ⚠️ 첫 조각은 **머리말**(`🔴 **1단 기계 점검 — …`)이라 사유가
            #    아니다 — 그것을 버리고 **진짜 사유**만 남긴다(#3).
            parts = [x.strip() for x in said_m.split("—")
                     if x.strip().startswith("🔴")
                     and "기계 점검" not in x and "확신·역배" not in x]
            why_m = (parts[0][:44] if parts else "🔴 보류")
        n_sure += sum(1 for r in said.rows if r.verdict == _db.SURE)
        n_fade += sum(1 for r in said.rows if r.verdict == _db.FADE)
        n_hold += sum(1 for r in said.rows if r.verdict == _db.HOLD)
        print(f"| {str(one.get('match'))[:30]} | "
              f"`{str(one.get('league') or '⬜').split(':')[-1]}` | "
              f"{str(one.get('board') or '⬜')} | {mark} | {why_m} | "
              + (f"{show.name} {show.p_bot:.1%}" if show
                 and show.p_bot is not None else "⬜")
              + " | "
              + (f"**{show.p_after:.1%}**" if show
                 and show.p_after is not None else "⬜")
              + " | " + (str(show.cell) if show and show.cell else "⬜")
              + " | " + (f"**{show.verdict}**" if show else "⬜") + " |")
    print()
    print(f"🔴 줄 판정 합계 — 확신 **{n_sure}** · 역배 **{n_fade}** · "
          f"보류 {n_hold}")
    print()
    # 🔴 1단 보류의 **까닭별** 집계 — 무엇이 막고 있나(#3)
    said_box: dict = {}
    for one in rows:
        if not one.get("machine_hold"):
            continue
        for x in str(one.get("machine") or "").split("—"):
            x = x.strip()
            if (x.startswith("🔴") and "확신·역배" not in x
                    and "기계 점검" not in x):
                said_box[x[:60]] = said_box.get(x[:60], 0) + 1
    if said_box:
        print("## 🔴 1단이 막는 까닭")
        print()
        for key, n in sorted(said_box.items(), key=lambda kv: -kv[1]):
            print(f"- **{n}경기** — {key}")
    print()
    print("⬜ **결과 칸은 비어 있다** — 이 경기들은 아직 끝나지 않았다. "
          "채점은 `scheduler score`(`analyze.score_finished`)가 한다(§3 불변: "
          "예측과 채점은 따로 쌓인다).")
    return 0


def _live_vars() -> list[str]:
    import yaml
    got = yaml.safe_load(
        (ROOT / "config/doubt_vars.yaml").read_text(encoding="utf-8")) or {}
    return [str(x) for x in (dict(got.get("의심") or {}).get("유효") or [])]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
