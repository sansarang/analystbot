"""🔴🔴 **v6 파이프라인 실행기** — 지시서 2026-10-06 §8.

```
PYTHONPATH=. python tools/v6_run.py "기아 vs 삼성" --to s3 --record kbo_1
```

🔴 **옛 경로(`cmd_analyze`)를 안 부른다** — §9 는 4단계 전까지 옛 경로 수정을
   금지하고, v6 는 **옆에 짓는다**. 이 실행기가 새 경로의 입구다.
⚠️ `--to` 로 어디까지 돌릴지 정한다(2단계는 `s3` 까지다).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))


async def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print('쓰는 법: tools/v6_run.py "<팀> vs <상대>" [--to s1|s2|s3|card] [--record id]')
        return 2
    arg = argv[1]
    to = argv[argv.index("--to") + 1] if "--to" in argv else "card"
    from app import cassette
    for flag, mode in (("--record", cassette.RECORD), ("--replay", cassette.REPLAY)):
        if flag in argv:
            os.environ[cassette.MODE_ENV] = mode
            os.environ[cassette.RUN_ENV] = argv[argv.index(flag) + 1]
            print(f"[v6] 카세트 {mode} · 실행 id "
                  f"`{os.environ[cassette.RUN_ENV]}`", flush=True)
    if "--replay-fallthrough" in argv:
        os.environ[cassette.FALLTHROUGH_ENV] = "1"

    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **`--as-of` — 재현 모드**(사용자 지시 2026-10-10(재작성) §4)
    # ══════════════════════════════════════════════════════════════
    #
    #  🔴 시계는 `app/window.set_clock` **하나다** — 운영(`app/`)이 부르면 계약이
    #     빨개진다. **도구 입구만** 부른다(`tools/run_stage8.py` 와 같은 자리).
    #  🔴 `_as_of` 는 **들여온다**(사본 금지 · CLAUDE.md #1).
    #  ⚠️ 끝난 경기를 *"안 끝났다는 가정"* 으로 다시 돌릴 때 쓴다 — 창·라인업
    #     상태·"이미 시작" 판단이 **그 시각** 기준이 된다.
    if "--as-of" in argv:
        from run_stage8 import _as_of
        from app import window as _w
        _w.set_clock(_as_of(argv[argv.index("--as-of") + 1]))
        print(f"[v6] 🕒 `--as-of` {_w.now_utc():%Y-%m-%d %H:%M}Z — "
              f"모든 창이 이 시각 기준이다", flush=True)
    from app import net as _net_mod
    from app import search as _search
    from app.config import get_settings
    from app.core.schema import Ambiguous, Question
    # ⚠️ 카드 경로는 `pipeline.analyze` 가 돈다 — s4~s7 을 여기서 **들여오지 않는다**
    #    (들여오면 또 손으로 이을 유혹이 생긴다 · CLAUDE.md #12)
    from app.core.stages import s1_resolve, s2_facts
    from app.core.state import RunState
    from app.db import get_pool
    from app.core import rank

    team, opp = arg, ""
    low = arg.lower()
    for sep in (" vs ", " vs. ", " - ", " 대 "):
        if sep in low:
            i = low.index(sep)
            team, opp = arg[:i].strip(), arg[i + len(sep):].strip()
            break
    # 🔴 재정렬은 **전용 스레드가 소유한다** — 입구에서 올린다(§6 부품)
    print(f"[v6] 재정렬 예열 — {rank.warm()}", flush=True)
    pool = await get_pool(get_settings().database_url)
    state = RunState()
    q = Question(raw=arg, team=team, opponent=opp,
                 asked_at=datetime.now(timezone.utc))

    net = _net_mod.Net()
    ref = await s1_resolve.run(q, pool=pool, state=state, net=net)
    if isinstance(ref, Ambiguous):
        print("🔴 s1 — 경기를 확정하지 못했다")
        print("  ", ref.why)
        for c in ref.candidates:
            print("   후보 ·", c)
        # 🔴 **밟은 단계를 찍는다**(#3) — 어디서 빗나갔나가 안 보이면 고칠 수 없다
        for n in state.notes:
            print("   밟음 ·", n[:150])
        return 1
    print(f"[s1] ✅ {ref.away_name} @ {ref.home_name} · {ref.competition_short}"
          f" · {ref.kickoff_utc:%Y-%m-%d %H:%M}Z · 열쇠 {ref.home}/{ref.away}"
          f" · 오픈월드 {ref.openworld}", flush=True)
    if to == "s1":
        return 0

    facts = await s2_facts.run(ref, state=state, net=net)
    print(f"[s2] 형식 {facts.match_format} · XI {len(facts.xi)}팀 · "
          f"순위 {len(facts.standings)}칸 · 폼 {len(facts.recent)}팀 · "
          f"출처 {len(facts.sources)}곳", flush=True)
    if to == "s2":
        return 0

    cache: dict = {}
    chain = _search.build_chain()
    # 🔴 딥서치를 지웠다(2026-10-17) — 문서는 LLM 서치가 긷는다
    from app.core.stages import s4b_gapsearch as _gs
    docs, _why = await _gs.harvest(ref, facts, state=state, chain=chain,
                                   net=net, cache=cache, variables=None)
    print(f"\n[s3] 문서 {len(docs)}건 · 장부 {state.book}")
    dated = sum(1 for d in docs if d.published_at is not None)
    print(f"     발행일 있는 것 {dated}/{len(docs)}"
          + (f" ({100 * dated // len(docs)}%)" if docs else ""))
    seen: dict[str, int] = {}
    for d in docs:
        seen[d.url] = seen.get(d.url, 0) + 1
    dup = {u: n for u, n in seen.items() if n > 1}
    print(f"     같은 URL 중복 {len(dup)}건" + (f" {list(dup)[:2]}" if dup else ""))
    for d in docs:
        print(f"  {d.id} [{d.subtask}] {d.tier:10} "
              f"{str(d.published_at)[:10] or '발행일 없음':10} "
              f"{d.date_source:9} {d.url[:70]}")
    _funnel(state)
    if to == "s3":
        return 0

    # ══════════════════════════════════════════════════════════════════
    # 🔴 s4~s7 · 카드 — **파이프라인 함수를 부른다**(프로브 금지 · CLAUDE.md #12)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 여기서 단계를 다시 이으면 그것은 **프로브**다 — 실제 경로가 아니라
    #     이 파일의 순서를 검사하게 된다. 🔴 `pipeline.analyze` 가 입구다.
    from app.core import pipeline, render
    # ══════════════════════════════════════════════════════════════════
    # 🔴 **재분석 경로**(축구 완성 지시서 §4) — `--again` 이면 s3·s4 를 안 돈다
    # ══════════════════════════════════════════════════════════════════
    if "--again" in argv:
        print("[v6] 🔁 재분석 — s2 만 다시 돌고 s6·s7 을 다시 센다", flush=True)
        got2 = await pipeline.reanalyze(arg, pool=pool, net=net, chain=chain,
                                        state=state)
        if isinstance(got2, Ambiguous):
            print("🔴 재분석 — 경기를 확정하지 못했다:", got2.why)
            return 1
        _funnel(state)
        print("\n" + "=" * 70 + "\n[재분석 카드]\n" + "=" * 70)
        print(render.card_text(got2))
        for n in state.notes[-12:]:
            print("  ·", n[:160])
        return 0
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **입구는 `pipeline.analyze` 하나다**(CLAUDE.md #12 프로브 금지)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전 이 실행기는 s4~s7 을 **손으로 다시 이었다** — 그래서 네 층(①②④)이
    #     붙은 뒤에도 실행기 카드에는 *"① 을 안 돌렸다"* 가 찍혔다(실측 2026-10-06).
    #  🔴 운영이 타는 길과 같은 길로만 돈다. 단계별 수는 `state` 의 자취가 든다.
    board_text = ""
    if "--board" in argv:
        board_text = argv[argv.index("--board") + 1]
        print(f"[v6] 보드 글 — {board_text}(경기 단서로만 쓴다 · 배당 미사용)",
              flush=True)
    # ⚠️ `--image`(보드 캡처 → 로컬 OCR → 배당 파서)는 **걷혔다**(2026-10-19)
    got = await pipeline.analyze(arg, pool=pool, net=net, chain=chain,
                                state=state, board_text=board_text)
    if isinstance(got, Ambiguous):
        print("🔴 경기를 확정하지 못했다:", got.why)
        return 1
    card = got
    print(f"\n[s5] 변수 {len(card.variables)}개 "
          f"(근거 가능 {sum(1 for v in card.variables if v.usable_as_basis)})")
    for v in card.variables:
        print(f"  {v.id} [{v.type:18}] {v.favors:10} {v.hardness:5} "
              f"{v.weight} · {v.claim[:60]}")
    scen = list(card.hypo.scenarios) if card.hypo is not None else []
    print(f"\n[s6] 시나리오 {len(scen)}개"
          + (f" · 반증 {len(card.hypo.redteam)}줄" if card.hypo is not None else ""))
    print(f"[s7] 마켓 {len(card.evals)}줄 · 등급 낸 줄 "
          f"{sum(1 for e in card.evals if e.grade != '자료부족')}")
    _funnel(state)
    print("\n" + "=" * 70 + "\n[카드]\n" + "=" * 70)
    print(render.card_text(card))
    print("\n[밟은 자취]")
    for n in state.notes:
        print("  ·", n[:160])
    # ══════════════════════════════════════════════════════════════════
    # 🔴 **2회차**(축구 완성 지시서 §6: 경기마다 두 번) — `--twice` 면 이어서 재분석
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 재분석은 **같은 프로세스의 기억**을 쓴다(§4-1) — 그래서 한 프로세스에서
    #     이어 돌린다. 🔴 운영 봇은 프로세스가 길게 살아서 저절로 그렇다.
    if "--twice" in argv:
        from app.core.state import RunState as _RS
        st2 = _RS(match_key=ref.id)
        print("\n" + "=" * 70 + "\n[2회차 · 재분석]\n" + "=" * 70, flush=True)
        got2 = await pipeline.reanalyze(arg, pool=pool, net=net, chain=chain,
                                        state=st2)
        if isinstance(got2, Ambiguous):
            print("🔴 재분석 — 경기를 확정하지 못했다:", got2.why)
            return 1
        _funnel(st2)
        print(render.card_text(got2))
        print("\n[2회차 자취]")
        for n in st2.notes[-14:]:
            print("  ·", n[:160])
    return 0


def _funnel(state: Any) -> None:
    """🔴 깔때기·버린 것·비용 — **안 잰 칸은 `null`** 로 보인다(#3)."""
    print(f"\n[깔때기] {json.dumps(state.counted(), ensure_ascii=False)}")
    by: dict[str, int] = {}
    for drop in state.drops:
        by[drop.reason.value] = by.get(drop.reason.value, 0) + 1
    print(f"[버린 것] {json.dumps(by, ensure_ascii=False)}")
    print(f"[비용] ${state.wallet.usd:.6f} · 호출 {state.wallet.calls}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    raise SystemExit(asyncio.run(main(sys.argv)))
