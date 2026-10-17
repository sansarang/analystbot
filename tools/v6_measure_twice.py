"""🔴🔴 **같은 입력 2회 실측** — 사용자 지시 2026-10-06 ⑤ — **같은 입력 2회**가 같은 출력인가(temperature=0 실측).

🔴 **같은 입력**이어야 한다 — 그래서 문서는 녹화본에서 재생해 고정하고(s3), 추출만
   **라이브로 두 번** 부른다(s4 의 실제 함수 `_ask` 를 쓴다 · 프로브 금지).
"""
import asyncio, json, os, sys
from app import cassette, net as _net_mod, search as _search
from app.core.state import RunState
from app.core.stages import s2_facts, s4_extract, s4b_gapsearch
from app.core import rank

RUN = sys.argv[1] if len(sys.argv) > 1 else "kor_uzb_v7_1"


def ref_of():
    from app.core.schema import MatchRef
    from datetime import datetime, timezone
    return MatchRef(id="fotmob:6368651", sport="soccer",
                    competition="Friendlies", competition_short="Friendlies",
                    home="team:000129", away="team:000245",
                    home_name="South Korea", away_name="Uzbekistan",
                    kickoff_utc=datetime(2026, 10, 6, 11, 0, tzinfo=timezone.utc),
                    venue="Yongin Mireu Stadium", langs=["ko", "uz"],
                    openworld=True)


async def main() -> int:
    os.environ[cassette.MODE_ENV] = cassette.REPLAY
    os.environ[cassette.RUN_ENV] = RUN
    ref, st = ref_of(), RunState(match_key="measure")
    net = _net_mod.Net()
    facts = await s2_facts.run(ref, state=st, net=net)
    cache: dict = {}
    # 🔴 딥서치를 지웠다(2026-10-17) — 문서는 LLM 서치가 긷는다
    docs, _why = await s4b_gapsearch.harvest(
        ref, facts, state=st, chain=_search.build_chain(), net=net, cache=cache,
        variables=None)
    print(f"[입력 고정] 문서 {len(docs)}건 · 재정렬 {rank.warm()}")
    # 🔴 **여기서 카세트를 끈다** — 추출만 라이브로 두 번 간다
    os.environ[cassette.MODE_ENV] = cassette.OFF
    outs = []
    for i in (1, 2):
        state = RunState(match_key=f"measure{i}")
        got = await s4_extract.run(ref, docs, state=state)
        rows = sorted((c.subtask, c.type, c.subject, c.target, c.doc_id,
                       c.claim, c.quote) for c in got)
        outs.append(rows)
        print(f"[{i}회] 후보 {len(got)}개 · ${state.wallet.usd:.6f}")
    a, b = outs
    same = a == b
    print(f"[결과] 글자까지 같은가 → {'✅ 같다' if same else '🔴 다르다'}")
    # 🔴 **카드가 보는 것은 병합 열쇠다**(사용자 지시 ①) — 그 집합도 함께 센다
    ka = sorted({(r[0].split("-")[0], r[1], r[2], r[3].lower()) for r in a})
    kb = sorted({(r[0].split("-")[0], r[1], r[2], r[3].lower()) for r in b})
    print(f"[결과] 병합 열쇠(유형군·유형·주체·대상) {len(ka)} vs {len(kb)} → "
          f"{'✅ 같다' if ka == kb else '🔴 다르다'}")
    if ka != kb:
        print("  1회에만:", [x for x in ka if x not in kb])
        print("  2회에만:", [x for x in kb if x not in ka])
    if not same:
        only_a = [r[:4] for r in a if r not in b]
        only_b = [r[:4] for r in b if r not in a]
        print("  1회에만:", json.dumps(only_a, ensure_ascii=False)[:600])
        print("  2회에만:", json.dumps(only_b, ensure_ascii=False)[:600])
    return 0 if same else 1

raise SystemExit(asyncio.run(main()))
