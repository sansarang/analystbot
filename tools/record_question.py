"""질문형 **카세트 녹음** — 정답지 한 경기에 예산을 몰아 딥서치를 돌리고 담는다.

🔴 **왜 급한가.** §9 단계 4 는 *"경기 전 시점 웹(카세트)에서 재현"* 을 요구한다.
   그 웹은 **킥오프가 지나면 사라진다** — 검색 색인이 라이브·경기 후 기사로 덮이고,
   프리뷰·예고 기사는 순위에서 밀려 내려간다. 2026-09-27~29 경기로 그 일을 이미
   겪었다(그날 응답이 3건만 남았다).

   🔴 실측 2026-10-01 11:12 KST: 정답지 경기 킥오프가 **11:00** 이었다.
      12분 지난 시점에 녹음을 시작했다 — 그 사실을 보고에 적는다(§11-3).

돌리는 법:

    PYTHONPATH=. uv run python tools/record_question.py            # 녹음
    PYTHONPATH=. uv run python tools/record_question.py --replay   # 재생만

⚠️ **이 도구는 채점하지 않는다.** 채점은 `tools/measure_question.py`(4-Q-7) 다.
   여기서 하는 일은 **담는 것**이고, 담긴 뒤에는 몇 번이고 다시 잴 수 있다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
GOLDEN = ROOT / "docs" / "fable" / "golden_v4.yaml"

#: 🔴 돌릴 세포 — `(이름, 질문타입)`. **질문타입은 `cells.Q_TYPES` 어휘다.**
#
#  ⚠️ 실측 2026-10-01: 첫 판은 `"coach_change"` 를 질문타입으로 썼다. 그런 타입은
#     없다 — 감독 교체 세포는 `intent` 를 쓰고 `subject` 에 `:coach` 를 붙여 질문
#     id 만 가른다(`searchcells.coach_cell` 머리글). 그래서 `queries.asks` 가
#     그것을 "축구에 없는 질문"으로 **건너뛰었다.** 어휘를 지어낸 값이다.
CELLS = (("lineup", "lineup"), ("intent", "intent"),
         ("coach", "intent"), ("starter_recent", "starter_recent"))


def load_game(game_id: str | None) -> dict:
    d = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))
    games = d["games"]
    if game_id:
        got = [g for g in games if g["id"] == game_id]
        if not got:
            raise SystemExit(f"정답지에 없는 경기: {game_id}")
        return got[0]
    if len(games) != 1:
        raise SystemExit(f"경기가 {len(games)}건이다 — `--game` 으로 지목하라")
    return games[0]


async def record(game: dict, *, replay: bool) -> dict:
    from app import cassette, queries, searchcells, secrets_mask
    from app.blackboard import Blackboard
    from app.cells import DEEP, SourceScores
    from app.net import Net
    from app.search import build_chain

    secrets_mask.install_log_filter()
    kick = datetime.fromisoformat(game["kickoff_kst"])
    day = kick.date()
    # 🔴 **시계를 경기 날짜로 세운다.** 없으면 목표 기사가 "지난 기사"로 거부된다
    #    (실측 2026-09-30). ⚠️ 느슨해지는 것이 아니다 — 더 오래된 기사는 여전히
    #    거부된다.
    os.environ[cassette.AS_OF_ENV] = str(day)
    os.environ["CASSETTE_MODE"] = "replay" if replay else "record"
    os.environ["CASSETTE_DAY"] = str(day)

    net, scores, search = Net(), SourceScores(), build_chain()
    out: dict = {"game": game["id"], "kickoff_kst": game["kickoff_kst"],
                 "recorded_at_kst": datetime.now(KST).isoformat(timespec="minutes"),
                 "mode": os.environ["CASSETTE_MODE"], "cells": {}}
    # 🔴 **킥오프가 지났는지 적는다.** 지난 뒤 녹음은 경기 전 웹이 아니다 —
    #    그 사실을 숨기면 뒤 측정이 자기 조건을 모른다.
    late = (datetime.now(KST) - kick).total_seconds() / 60
    out["kickoff_passed_min"] = round(late, 1)

    teams = [("home", game["home"]), ("away", game["away"])]
    for side, team in teams:
        other = game["away"] if side == "home" else game["home"]
        for name, qtype in CELLS:
            # 🔴 **이 종목에 없는 질문은 묻지 않는다** — 묻지 않았다고 적는다
            ok, why = queries.asks(game.get("sport", ""), qtype)
            if why:
                # 🔴 막히지 않아도 **사유는 남긴다**(모르는 종목·모르는 이름)
                logging.info("[record] %s/%s — %s", team, name, why)
            if not ok:
                out["cells"][f"{team}:{name}"] = {"state": "skipped",
                                                  "facts": 0, "why": why}
                continue
            make = {"lineup": searchcells.lineup_cell,
                    "intent": searchcells.intent_cell,
                    "coach": searchcells.coach_cell,
                    "starter_recent": searchcells.starter_recent_cell}[name]
            kw = dict(team=team, league=game["league"], day=day, game_id=None,
                      starts=kick, mode=DEEP)
            if name in ("lineup", "coach"):
                kw["opponent"] = other
            if name == "lineup":
                # 🔴 §19-d 시간축을 비켜 간다 — 측정 대상은 시간축이 아니라
                #    **검색이 그 사실에 닿나** 다(`measure_stage4` 와 같은 이유).
                kw["now"] = kick - timedelta(minutes=30)
            cell, dropped = make(**kw)
            bb = Blackboard()
            try:
                state = await cell.run(net, bb, search=search, scores=scores)
            except Exception as exc:                      # noqa: BLE001
                logging.exception("[record] %s/%s 실패", team, name)
                out["cells"][f"{team}:{name}"] = {"error": repr(exc)}
                continue
            facts = [f for qid, slot in bb.slots.items()
                     if qid == cell.question.id
                     or qid.startswith(cell.question.id + ":")
                     for f in slot.facts]
            out["cells"][f"{team}:{name}"] = {
                "state": state, "facts": len(facts),
                "budget": cell.budget.spent,
                "sources": len(cell.sources),
                "dropped_queries": dropped[:4],
                "tried": cell.tried[:10],
                # 🔴 **어디서 왔는지 남긴다** — 출처 없는 변수 0 을 재려면 필요하다
                "fact_sources": sorted({(f.source or "")[:110] for f in facts}),
            }
            logging.info("[record] %s/%s → %s · 사실 %d · %s",
                         team, name, state, len(facts), cell.budget.spent)
    return out


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game")
    ap.add_argument("--replay", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    game = load_game(a.game)
    got = await record(game, replay=a.replay)
    outdir = ROOT / "logs" / "stage4"
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"record_{game['id']}.json"
    path.write_text(json.dumps(got, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(json.dumps({k: v for k, v in got.items() if k != "cells"},
                     ensure_ascii=False, indent=2))
    print(f"\n보고 → {path.relative_to(ROOT)}")
    hit = sum(1 for c in got["cells"].values() if c.get("facts"))
    print(f"사실을 낸 세포 {hit}/{len(got['cells'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
