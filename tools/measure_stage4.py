"""단계 4 측정 — v4 §9 **필수 8건**을 실제로 재는 자리.

🔴 **이것은 계약이 아니다. 측정이다.** 라이브 웹을 때리고 결과를 카세트로 남긴다.
   계약은 그 카세트를 재생해 **잰 값을 잠근다**(`tests/stage4/test_essential8.py`).

§9 단계 4 완료 조건 원문:

> §10 정답지의 변수 목록을 경기 전 시점 웹(카세트)에서 재현: 재현율 80% 이상,
> 방향 오류 5% 이하, 출처 없는 변수 0, 경기 후 기사 혼입 0. **필수 8건 개별 통과**

## 🔴 이 측정이 **원문과 다른 점** — 숨기지 않는다

원문은 *"경기 전 시점 웹(카세트)"* 을 요구한다. 그 웹은 **남아 있지 않다** —
2026-09-27~29 의 페이지는 되돌릴 수 없고, 저장소에 남은 그날 응답은 3건뿐이다
(`docs/fable/questions/2026-09-30_stage3_gate_partial.md`).

그래서 이 측정은 **오늘 웹에서 그날 사실을 찾는다.** 그 차이가 뜻하는 것:

| | 원문(경기 전 시점 웹) | 이 측정(오늘 웹) |
|---|---|---|
| 경기 후 기사 | 아예 없다 | 🔴 **가득하다** — 그래서 *"혼입 0건"* 이 **더 어려운** 시험이 된다 |
| 예고·프리뷰 기사 | 1순위로 나온다 | 검색 순위에서 밀린다 — 재현율에 **불리하다** |
| 판정 | "경기 전에 찾을 수 있었나" | "그 사실을 찾아낼 수 있나 + 경기 후 기사를 거부하나" |

🔴 즉 이 측정은 **원문보다 재현에 불리하고 혼입 검사에 유리하다.** 통과하면 뜻이
있고, 못 넘으면 *"경기 전 웹이었으면 됐을 수도 있다"* 는 여지가 남는다 — 그 여지를
보고에 그대로 적는다(§11-3 추측 금지).

## 🔴 4a 도달 / 4b 변환 (사용자 승인 2026-09-30)

§9 단계 4↔5 에 **순환**이 있었다: 게이트가 "같은 유형·같은 방향"을 요구하는데
유형·방향을 붙이는 추출기는 단계 5 이고, 단계 5 는 게이트 통과 후다.
→ `docs/fable/questions/2026-09-30_stage4_split.md` (사용자 결정)

그래서 이 도구는 **두 축을 갈라** 잰다:

| 축 | 무엇 | 실패하면 고칠 곳 |
|---|---|---|
| **도달** | 검색이 그 사실을 담은 자료에 닿았나 | 검색어·소스 지도 (4a) |
| **변환** | 그 자료에서 사실을 뽑았나 | **추출기** (4b) |

🔴 이 둘을 섞으면 *"0/8"* 만 남고 **어디를 고칠지 사라진다.**

돌리는 법:
    PYTHONPATH=. uv run python tools/measure_stage4.py            # 라이브 + 녹음
    PYTHONPATH=. uv run python tools/measure_stage4.py --replay   # 카세트만
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
CASES = "config/stage4_essential8.yaml"
KST = timezone(timedelta(hours=9))
#: 🔴 건 사이 간격(초). 한 건이 검색어 4~5개를 던지므로 이 간격이 없으면
#  업스트림 엔진이 요청 과다로 정지한다(실측 2026-09-30 — 그래서 0/8 이 나왔다).
THROTTLE_SEC = float(os.getenv("STAGE4_THROTTLE_SEC", "20"))


def load_cases() -> dict:
    return yaml.safe_load((ROOT / CASES).read_text(encoding="utf-8"))["items"]


# ══════════════════════════════════════════════════════════════════
# 채점
# ══════════════════════════════════════════════════════════════════

def _terms(case: dict) -> list[str]:
    return [t for t in (list(case.get("origin_terms") or [])
                        + list(case.get("extra_terms") or [])) if t]


def _origin_hit(case: dict, blob: str) -> list[str]:
    """🔴 **정본 낱말을 찾았나 — 표기가 달라도 같은 사실이면 찾은 것이다.**

    §10 게이트 계산법: *"같은 사실을(… 출처가 같은 원문 또는 **동일 사실을 보도한
    다른 매체**) 찾아낸 수"*. 정본은 `스바나제` 라고 쓰고 자료는 `Svanadze` 라고
    쓴다 — 한국어 표기만 보면 **완벽한 파서도 0점**이다(실측 2026-09-30).

    🔴 대응은 **선언된 것만**(`same_as`) 쓴다. 그 키가 `origin_terms` 안에 있는지는
       계약이 잠근다 — 아무 낱말이나 대응으로 붙이면 시험을 고쳐 쓰는 것이다.
    """
    same = case.get("same_as") or {}
    got = []
    for t in case.get("origin_terms") or []:
        forms = [t, *[str(x) for x in (same.get(t) or [])]]
        if any(f and f in blob for f in forms):
            got.append(t)
    return got


def reached_fact(case: dict, hits) -> tuple[bool, str]:
    """🔴 **낱말이 아니라 "그 사실"에 닿았나.**

    `reach` 는 `[[대안,…],[대안,…]]` 이고 **각 묶음에서 하나씩 같은 스니펫에**
    있어야 도달이다.

    ⚠️ 실측 2026-09-30: 낱말 하나로 재던 첫 판이 거짓 양성을 냈다 —
       ② `발베르데·벤탄쿠르·누녜스가 한국 땅을 밟습니다`(결장의 **반대**)와
       ⑧ 이름만 있는 8월 회견 기사 열두 건을 **도달로 셌다.**
       전자는 M11(명단 없이 "완전체"로 씀)을 그대로 되풀이하는 판정이다.
    """
    groups = case.get("reach") or []
    if not groups:
        return False, "🔴 `reach` 가 정의되지 않았다 — 도달을 잴 수 없다"
    for h in hits or []:
        text = f"{getattr(h, 'title', '')} {getattr(h, 'snippet', '')}"
        if all(any(t in text for t in g) for g in groups):
            return True, f"{getattr(h, 'publisher', '')} — {text[:150]}"
    return False, ""


def backend_alive(search) -> tuple[bool, dict]:
    """검색 백엔드가 지금 살아 있나. 🔴 **죽었으면 채점하지 않는다.**

    ⚠️ 실측 2026-09-30: 이 도구의 첫 판은 모든 질의가 0건인 것을 *"미발견"* 으로
       채점해 **0/8** 을 냈다. 그런데 원인은 봇이 아니라 **SearXNG 엔진 전부 정지**
       였다(`brave`·`duckduckgo`·`google cse` 가 요청 과다·타임아웃으로 suspended —
       내 라이브 측정이 그것을 유발했다).
       🔴 그것을 "못 찾았다"로 보고하면 **거짓 측정**이고, 그 숫자를 보고 설계를
       고치려 들게 된다(조용한 0 금지 · §11-3 추측 금지).
    """
    searx = getattr(search, "searx", None)
    if searx is None:
        return False, {"왜": "SearXNG 가 사슬에 없다"}
    reasons = searx.engine_reasons() if hasattr(searx, "engine_reasons") else {}
    return True, reasons


def score_one(case: dict, facts, hits, rejected: list[str]) -> dict:
    """한 건 채점. 🔴 **어느 낱말이 어디서 나왔는지**까지 남긴다.

    세 값을 가른다:
      · `found`     — 검증을 **통과한** 사실에 그 낱말이 있다
      · `in_search` — 검색 결과에는 있는데 사실로 못 뽑았다(**파서 결함**)
      · `absent`    — 검색 결과에도 없다(**소스·검색어 결함**)

    🔴 이 셋을 구분하는 것이 이 측정의 값어치다 — 고칠 곳이 다르다
       (CLAUDE.md §"자료가 안 왔다"와 "왔는데 못 뽑았다"를 구분해 적는다).
    """
    terms = _terms(case)
    fact_blob = " ".join(str(f.value) + " " + (f.quote or "") for f in facts)
    hit_blob = " ".join(f"{getattr(h, 'title', '')} {getattr(h, 'snippet', '')}"
                        for h in hits or [])

    in_fact = [t for t in terms if t in fact_blob]
    in_hits = [t for t in terms if t in hit_blob and t not in in_fact]
    missing = [t for t in terms if t not in fact_blob and t not in hit_blob]

    # 🔴 정본이 댄 낱말이 하나라도 사실에 있어야 **통과**다 — 표기가 달라도
    #    선언된 대응(`same_as`)이면 같은 사실로 센다(§10 계산법).
    origin = set(case.get("origin_terms") or [])
    origin_found = _origin_hit(case, fact_blob)
    passed = bool(origin_found)

    # 🔴 **"부재"를 재는 건은 반대로 본다.** `세이부 겐다 벤치` 는 *스타멘 표에
    #    그가 **없다***는 사실이다 — 이름을 찾는 것이 아니라 **표를 찾고 그 안에
    #    없는지** 봐야 한다. 이름으로 채점하면 정답이 "미발견"으로 찍힌다
    #    (실측 2026-09-30: 5번이 정확히 그렇게 오채점됐다).
    absent_of = case.get("absent_from_lineup")
    if absent_of:
        rows = [v for f in facts if isinstance(f.value, list) for v in f.value]
        names = " ".join(str(v.get("name") or "") for v in rows)
        got_table = len(rows) >= int(case.get("min_slots") or 5)
        passed = got_table and all(t not in names for t in absent_of)
        # 🔴 이 유형의 "도달"은 **그날 타순 표를 뽑았나** 다 — 검색 결과가
        #    있다는 것만으로는 도달이 아니다(실측: 전날 경기 표가 잡혔다).
        reached = got_table
        return {
            "origin": case["origin"],
            "도달": "O" if reached else "X",
            "도달_근거": (f"타순 {len(rows)}칸을 뽑았다" if got_table
                        else "그날 타순 표를 못 뽑았다"),
            "변환": "O" if passed else "X",
            "verdict": ("통과" if passed
                        else ("도달O·변환X(추출기)" if reached
                              else "도달X(검색어·소스)")),
            "재는_방식": f"🔴 **부재**를 잰다 — 타순 표를 뽑고 그 안에 "
                        f"{absent_of} 가 없어야 통과",
            "뽑은_타순_칸": len(rows),
            "타순에_있는_이름": sorted({str(v.get("name") or "") for v in rows}),
            "찾던_이름이_타순에_있나": [t for t in absent_of if t in names],
            "사실_수": len(facts),
            "검색_결과_수": len(hits or []),
            "검증_거부": rejected[:6],
        }

    # 🔴 **두 축을 갈라 낸다**(사용자 결정 2026-09-30: 4a 도달 / 4b 변환).
    #    섞으면 "0/8" 만 남고 어디를 고칠지 사라진다.
    #    ⚠️ 도달은 **낱말 존재가 아니라 사실 도달**이다(`reached_fact`).
    reached, where = reached_fact(case, hits)
    return {
        "origin": case["origin"],
        "도달": "O" if reached else "X",
        "도달_근거": where,
        "변환": "O" if passed else "X",
        "verdict": ("통과" if passed
                    else ("도달O·변환X(추출기)" if reached
                          else "도달X(검색어·소스)")),
        "정본_낱말_사실에서": sorted(origin_found),
        "덧붙인_낱말_사실에서": sorted(set(in_fact) - origin),
        "검색결과엔_있는데_못_뽑음": in_hits,
        "검색결과에도_없음": missing,
        "사실_수": len(facts),
        "검색_결과_수": len(hits or []),
        "검증_거부": rejected[:6],
    }


def _zero_checks(facts, hits) -> dict:
    """§9 단계 4 의 **"0건" 두 항목** — 4a 에 속한다(정답지가 필요 없다).

    | 항목 | 어떻게 재나 |
    |---|---|
    | 출처 없는 변수 0 | 채택된 사실에 `source` 가 **없는 것**을 센다 |
    | 경기 후 기사 혼입 0 | 검색 결과 중 경기 후 기사를 세고, **그것이 사실로
      들어왔는지** 본다(§12-c-2 `not_post_game` 이 막는 자리) |

    🔴 **혼입은 "검색 결과에 있었나"가 아니라 "사실로 들어왔나"다.** 오늘 웹에는
       경기 후 기사가 가득하고(§9 원문의 "경기 전 시점 웹"과 다른 점), 그것을
       **거부하는지**가 검사 대상이다.
    """
    from app import verify

    sourceless = [str(f.value)[:60] for f in facts if not (f.source or "").strip()]

    post_in_hits, post_in_facts = [], []
    for h in hits or []:
        title = getattr(h, "title", "") or ""
        body = getattr(h, "snippet", "") or ""
        if verify.not_post_game(title, body).ok:
            continue
        post_in_hits.append(getattr(h, "url", ""))
        # 🔴 그 URL 이 채택된 사실의 출처로 들어왔나
        if any((f.source or "") == getattr(h, "url", "") for f in facts):
            post_in_facts.append(getattr(h, "url", ""))

    return {
        "출처_없는_사실": sourceless,
        "검색결과_중_경기후_기사": len(post_in_hits),
        "경기후_기사_혼입": post_in_facts,
    }


# ══════════════════════════════════════════════════════════════════
# 한 건 돌리기
# ══════════════════════════════════════════════════════════════════

async def run_one(n: int, case: dict, *, net, search, scores) -> dict:
    from app import searchcells
    from app.blackboard import Blackboard

    if not case.get("day"):
        return {"origin": case["origin"], "verdict": "못 잼",
                "왜": "🔴 정본이 경기 날짜를 대지 않는다 — 지어내지 않는다"}
    if not case.get("team"):
        return {"origin": case["origin"], "verdict": "못 잼",
                "왜": "🔴 정본이 소속 팀을 대지 않는다 — 지어내지 않는다"}

    day = case["day"] if isinstance(case["day"], date) else \
        date.fromisoformat(str(case["day"]))
    starts = datetime(day.year, day.month, day.day, 21, 0, tzinfo=KST)

    # 🔴 **시계를 그 경기 날짜로 세운다**(§9: "경기 전 시점 웹에서 재현").
    #    실측 2026-09-30: 이것 없이 재면 목표 기사가 전부 "3일 지난 기사"로
    #    거부된다 — 봇의 결함이 아니라 시계가 틀린 것이다.
    #    ⚠️ 느슨해지는 것이 아니다. 그 시각 기준으로 **더 오래된** 기사는 여전히
    #       거부되고, 실제로 33일 지난 기사가 그렇게 떨어졌다.
    from app import cassette as _c
    os.environ[_c.AS_OF_ENV] = str(day)
    make = {"lineup": searchcells.lineup_cell,
            "intent": searchcells.intent_cell,
            # 🔴 감독 **교체**는 감독 **의도**와 다른 질문이고 세포도 다르다(§19-a)
            "coach_change": searchcells.coach_cell,
            "starter_recent": searchcells.starter_recent_cell}[case["qtype"]]

    kw = dict(team=case["team"], league=case["league"], day=day,
              game_id=None, starts=starts, local=case.get("local") or "")
    if case["qtype"] == "coach_change":
        kw["opponent"] = case.get("opponent") or ""
    if case["qtype"] == "lineup":
        kw["opponent"] = case.get("opponent") or ""
        kw["opponent_local"] = case.get("opponent_local") or ""
        # 🔴 §19-d 시간축을 **측정 때는 비켜 간다** — 그날 경기는 이미 끝났고,
        #    `awake()` 로는 세포가 아예 안 돈다. 측정 대상은 시간축이 아니라
        #    **검색이 그 사실에 닿나** 이므로 세포를 직접 돌린다.
        kw["now"] = starts - timedelta(minutes=30)
    cell, dropped = make(**kw)

    bb = Blackboard()
    state = await cell.run(net, bb, search=search, scores=scores)
    # 🔴 **세포가 쓴 사실을 전부 모은다.** 한 세포가 여러 질문에 쓸 수 있다 —
    #    감독 교체 사실은 `…:coach` 로 간다(인용 사실과 섞이면 §19-c 가 모순으로
    #    판정하므로 id 를 갈랐다). 주 질문만 보면 그 사실을 놓친다.
    facts = [f for qid, slot in bb.slots.items()
             if qid == cell.question.id or qid.startswith(cell.question.id + ":")
             for f in slot.facts]

    # 🔴 같은 검색어를 다시 던져 **검색 결과 원본**을 본다(파서 결함 판별용).
    #    ⚠️ 카세트가 있으므로 네트워크 비용은 0 이다.
    hits = []
    for src in cell.sources[:3]:
        try:
            hits += await search.query(src.query or "", lang=src.lang)
        except Exception as exc:                          # noqa: BLE001
            logging.info("[stage4] %s 재조회 실패: %s", src.name, exc)

    os.environ.pop("CASSETTE_AS_OF", None)   # 🔴 건마다 걷는다 — 새지 않게
    out = score_one(case, facts, hits,
                    [t for t in cell.tried if "검증거부" in t])
    out.update(_zero_checks(facts, hits))
    out.update({"질문": cell.question.id, "상태": state,
                "버린_검색어": dropped,
                "시도": cell.tried[:8],
                "예산": cell.budget.spent})

    # 🔴 **검색이 0건이면 채점하지 않는다.** "못 찾았다"와 "찾을 수단이 죽어
    #    있었다"는 완전히 다른 진단이고, 후자를 전자로 적으면 거짓 측정이다.
    if not hits and all("0건" in t or "SearXNG" in t for t in cell.tried):
        _, reasons = backend_alive(search)
        out["verdict"] = "측정 무효"
        out["왜"] = (f"🔴 검색 결과가 **전 질의 0건**이다 — 봇이 못 찾은 것이 "
                     f"아니라 검색 수단이 답하지 않았다. 정지 엔진: "
                     f"{reasons or '알 수 없음'}")
    return out


# ══════════════════════════════════════════════════════════════════
# 전체
# ══════════════════════════════════════════════════════════════════

async def main(replay: bool) -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    from app import cassette, secrets_mask
    secrets_mask.install_log_filter()

    os.environ[cassette.MODE_ENV] = cassette.REPLAY if replay \
        else cassette.RECORD
    # 🔴 카세트는 **측정한 날**로 묶는다 — 그날 웹이 아니라 오늘 웹이므로
    #    09-27 로 두면 거짓이 된다.
    os.environ.setdefault(cassette.DAY_ENV, str(datetime.now(KST).date()))

    from app.cells import SourceScores
    from app.net import Net
    from app.search import build_chain

    net, scores, search = Net(), SourceScores(), build_chain()
    print(f"\n### 모드 {cassette.mode()} · 카세트 날짜 {cassette.day()}")
    print(f"### 검색 사슬 searx={search.searx and search.searx.base} "
          f"google={'붙음' if search.google else '잠김'}\n")

    cases = load_cases()
    results = {}
    for i, n in enumerate(sorted(cases)):
        # 🔴 **간격을 둔다.** 실측 2026-09-30: 연달아 던져 `brave`·`duckduckgo`·
        #    `google cse` 를 전부 정지시켰고, 그 상태로 잰 0/8 은 무효였다.
        #    ⚠️ 이것은 §19-f 의 "우회 없음"과 같은 결의 문제다 — 상대 서버에
        #       예의를 지키는 것이 측정의 전제다.
        if i and cassette.mode() != cassette.REPLAY:
            await asyncio.sleep(THROTTLE_SEC)
        print(f"\n{'='*70}\n[{n}] {cases[n]['origin']}")
        results[n] = await run_one(n, cases[n], net=net, search=search,
                                   scores=scores)
        r = results[n]
        print(f"   판정: {r['verdict']}")
        for k in ("왜", "정본_낱말_사실에서", "검색결과엔_있는데_못_뽑음",
                  "검색결과에도_없음", "검증_거부"):
            if r.get(k):
                print(f"   {k}: {r[k]}")

    print(f"\n\n{'='*70}\n### 필수 8건 채점")
    tally: dict[str, list[int]] = {}
    for n, r in results.items():
        tally.setdefault(r["verdict"], []).append(n)
    for v in ("통과", "도달O·변환X(추출기)", "도달X(검색어·소스)",
              "못 잼", "측정 무효"):
        if v in tally:
            print(f"   {v:<22} {len(tally[v])}건  {tally[v]}")

    measured = [n for n, r in results.items() if r.get("도달")]
    reached = [n for n in measured if results[n]["도달"] == "O"]
    converted = [n for n in measured if results[n]["변환"] == "O"]
    void = [n for n, r in results.items() if not r.get("도달")]

    print(f"\n{'─'*70}\n### 4a 도달 / 4b 변환 (사용자 결정 2026-09-30)")
    print(f"   🔴 **4a 도달  {len(reached)}/{len(measured)}** "
          f"(잰 것 중) — 검색이 자료에 닿았나  {reached}")
    print(f"   🔴 **4b 변환  {len(converted)}/{len(measured)}** "
          f"— 그 자료에서 사실을 뽑았나  {converted}")
    if void:
        print(f"   ⚠️ **못 잰 것 {len(void)}건** {void} — 봇의 실력이 아니다")

    # 🔴 §9 의 "0건" 두 항목 — 4a 에 속한다
    sourceless = [n for n, r in results.items() if r.get("출처_없는_사실")]
    mixed = [n for n, r in results.items() if r.get("경기후_기사_혼입")]
    post_seen = sum(r.get("검색결과_중_경기후_기사") or 0
                    for r in results.values())
    print(f"\n### 4a 의 \"0건\" 두 항목")
    print(f"   출처 없는 변수      {'0건 ✅' if not sourceless else f'🔴 {sourceless}'}")
    print(f"   경기 후 기사 혼입    {'0건 ✅' if not mixed else f'🔴 {mixed}'}")
    print(f"      ⚠️ 검색 결과에 경기 후 기사가 **{post_seen}건** 있었고 "
          f"그중 {len(mixed)}건이 사실로 들어왔다")
    print(f"      🔴 오늘 웹이라 경기 후 기사가 가득하다 — 원문(경기 전 웹)보다 "
          f"**어려운** 시험이다")

    ok = len(tally.get("통과", []))
    print(f"\n🔴 **필수 8건: {ok}/8 통과** — §9 는 8건 **개별** 통과를 요구한다")
    if len(tally.get("측정 무효", [])) >= 3:
        print("\n🔴 **이 측정은 무효다.** 검색 백엔드가 답하지 않는 동안 돌았다 — "
              "엔진이 살아난 뒤 다시 돌려라(`--replay` 아님, 라이브로).")

    p = ROOT / "logs" / "stage4" / f"essential8_{datetime.now(KST):%Y-%m-%d}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str),
                 encoding="utf-8")
    print(f"\n측정 원문 → {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", action="store_true",
                    help="카세트만 쓴다 — 네트워크에 가지 않는다")
    sys.exit(asyncio.run(main(ap.parse_args().replay)))
