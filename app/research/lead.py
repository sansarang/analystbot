"""🔴🔴 **§3 — 리드**(작업 지시서 2026-10-05). **리드는 코드다**(LLM 아님).

> `lead.py` 가 하는 일은 **넷뿐**이고, 그 밖의 일을 하면 계약 위반이다.
>  1. **병합** — 하위 8개의 `variables[]` 조각을 합친다
>  2. **장부 갱신** — 유형군 × 팀 칸마다 `searched`/`found`/`empty`/`not_tried`
>  3. **2차 보충(최대 1회)** — `not_tried`·`empty` 유형군만, 남은 예산 안에서
>  4. **깔때기 집계** — 하위별 한 줄 + 합계
>
> **리드가 하지 않는 것**: LLM 호출로 변수·가설·시나리오를 만들지 않는다(M60).
> 변수 내용을 고치지 않는다. 하위 결과를 버리지 않는다(버리는 건 검증층의
> 사유 코드만).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

#: 🔴 세마포어는 **과정 전체**의 것이다 — 하위 8개가 공유해야 상한이 뜻을 갖는다.
#  ⚠️ LDR 의 속도 제한 모듈이 같은 결론을 적는다: *"에이전트가 호출마다 새
#     인스턴스를 만들어 per-instance 간격이 안 걸렸다."* 🔴 이 저장소도 같은
#     병을 GDELT 에서 겪었다(2026-10-05: 체인마다 벌점을 잊었다).
_GATES: dict[str, asyncio.Semaphore] = {}


def limits() -> dict[str, int]:
    """🔴 동시성 상한 — `config/llm.yaml` `budget.concurrency`(M66).

    ⚠️ 수를 코드에 박지 않는다(지시서 §2: *"전부 설정에 상수로"*).
    """
    from app import solar
    box = dict(solar.budget_cfg().get("concurrency") or {})
    if not box:
        raise KeyError("🔴 `budget.concurrency` 가 `config/llm.yaml` 에 없다")
    return {str(k): int(v) for k, v in box.items()}


def gate(name: str) -> asyncio.Semaphore:
    """🔴🔴 **그 통로의 세마포어**(M66) — 같은 이름이면 같은 객체다.

    ⚠️ `asyncio.Semaphore` 는 만든 이벤트 루프에 묶인다. 루프가 바뀌면 새로
       만든다 — 안 그러면 *"다른 루프의 future"* 로 터진다.
    """
    key = str(name)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    got = _GATES.get(key)
    if got is None or getattr(got, "_loop", loop) is not loop:
        got = asyncio.Semaphore(limits()[key])
        got._loop = loop          # noqa: SLF001  (루프 바뀜을 우리가 센다)
        _GATES[key] = got
    return got


async def run_all(jobs: list) -> tuple[list, list]:
    """🔴🔴 **병렬 격리**(M63) — `(산 결과들, 터진 것들)`.

    > 하위 하나의 예외·타임아웃·`budget_cut` 이 **다른 하위를 멈추지 않는다.**
    > 실패 하위는 장부에 `searched`(빈손) 또는 **사유 코드**로 남긴다.

    ⚠️ 실측 2026-10-05(프랑스–벨기에): 한 팀 에이전트가 `'str' object has no
       attribute 'get'` 으로 터졌고 **그 팀 변수가 통째로 없었다**. 🔴 분할
       뒤에는 그 하나가 나머지 일곱을 끌고 내려가면 안 된다.
    🔴 **터진 것을 조용히 버리지 않는다**(#3) — 돌려주고 호출부가 적는다.
    """
    got = await asyncio.gather(*jobs, return_exceptions=True)
    live: list[Any] = []
    bad: list[BaseException] = []
    for x in got:
        (bad if isinstance(x, BaseException) else live).append(x)
    if bad:
        logger.info("[lead] 🔴 하위 %d개가 터졌다 — 나머지 %d개로 간다: %s",
                    len(bad), len(live),
                    " · ".join(f"{type(e).__name__}: {e}"[:80] for e in bad))
    return live, bad


#: 🔴 2차 보충 횟수 — **한 번뿐**이다(M64). ⚠️ *"2차 뒤에도 비면 그대로
#  `gaps` 로 보고한다 — **3차는 없다**."*
SECOND_ROUNDS = 1

#: 🔴 2차가 돌 **대상 상태** — 지시서 §3-3: *"`not_tried`·`empty` 인 유형군만"*.
SECOND_STATES: tuple[str, ...] = ("not_tried", "empty")


def merge(parts: list) -> dict:
    """🔴🔴 **① 병합** — 하위 조각을 합친다(지시서 §3-1).

    > 같은 주장(MinHash 0.8, 기존 §5-7)은 한 묶음으로 세어 **독립 출처 수를
    > 올리고**, 유형·방향은 건드리지 않는다(방향은 검증층이 재계산). 하위가
    > 담당 밖 유형을 적어 왔으면 **그대로 받는다** — 폐기는 검증층 몫이다.

    🔴 **버리지 않는다**(M60) — 리드가 버리면 그 사실이 사유 없이 사라진다.
    ⚠️ 유사도 판정은 `verifylayer.similarity`·`SIM_SAME` **한 곳**이다(#1).
    """
    from urllib.parse import urlparse

    from app import verifylayer
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **두 꼴을 다 받는다** — 실사고 2026-10-05 (인도네시아–태국)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 봇이 죽었다: `dict(v)` → `TypeError: 'Classified' object is not
    #     iterable`. 🔴 `_run_agent` 는 **판정층 변수**(`classify.Classified`)
    #     를 돌려주는데 여기서 dict 로 믿었다 — ①번(`done.variables` 가
    #     문자열)과 **같은 병**이다.
    #  🔴 **원본 객체를 바꾸지 않는다** — 검증층이 그 객체를 쓴다. dict 로
    #     바꿔 담으면 그 뒤가 전부 깨진다.
    rows: list = []
    for part in (parts or []):
        for v in ((part or {}).get("variables") or []):
            if isinstance(v, dict):
                got = dict(v)
                got["from_subtask"] = str((part or {}).get("name") or "")
                rows.append(got)
            else:
                # 🔴 객체는 **그대로** 담는다(원본을 잃지 않는다)
                rows.append(v)

    def _get(x: object, key: str) -> str:
        """🔴 dict·객체 **둘 다**에서 칸을 읽는다(#1 — 읽는 자리를 하나로)."""
        if isinstance(x, dict):
            return str(x.get(key) or "")
        # ⚠️ 판정층 변수는 주장을 `text` 칸에 든다(`claim` 이 아니다)
        alt = "text" if key == "claim" else key
        return str(getattr(x, key, None) or getattr(x, alt, None) or "")

    def _host(x: object) -> str:
        return (urlparse(_get(x, "source_url")).netloc
                or "").lower().removeprefix("www.")

    # 🔴 같은 주장끼리 묶어 **독립 출처 수**를 센다(유형·방향은 그대로).
    for i, a in enumerate(rows):
        hosts = {_host(a)}
        for j, b in enumerate(rows):
            if i == j:
                continue
            sim = verifylayer.similarity(_get(a, "claim"), _get(b, "claim"))
            if sim >= verifylayer.SIM_SAME:
                got_h = _host(b)
                if got_h:
                    hosts.add(got_h)
        n = len([h for h in hosts if h])
        if isinstance(a, dict):
            a["outlets"] = n
        else:
            # ⚠️ dataclass 에 칸이 없으면 **더한다**(원본을 바꾸지 않는 선에서)
            try:
                a.outlets = n
            except (AttributeError, TypeError):
                pass
    said = [int(_get(r, "outlets") or 1) for r in rows]
    logger.info("[lead] 병합 — 하위 %d개 → 변수 %d줄(독립 출처 최대 %d곳)",
                len(parts or []), len(rows), max(said or [0]))
    return {"variables": rows}


def write_book(book, parts: list) -> None:
    """🔴🔴 **② 장부 갱신** — 유형군 × 팀 칸(지시서 §3-2).

    > 하위가 검색을 돌았으면 `searched`, **검증 통과 변수가 생기면 `found`**,
    > 검색했는데 후보 0 이면 `empty`, 하위가 실패했으면 `not_tried` + 사유.
    > 🔴 **`found` 배선이 이번에 완성돼야 한다** — 지금은 `searched` 만 적힌다.
    """
    for part in (parts or []):
        box = dict(part or {})
        group = str(box.get("group") or "")
        key = str(box.get("team_key") or "")
        if not group or not key:
            continue
        fail = str(box.get("failed") or "")
        if fail:
            # 🔴 **사유를 함께 적는다**(#3) — 실패와 안 해본 것을 가른다
            book.mark(group, key, "not_tried")
            _why(book, group, key, f"하위 실패 — {fail}")
            continue
        if int(box.get("verified") or 0) > 0:
            book.mark(group, key, "found")          # 🔴 이번에 완성한 배선
        elif not (box.get("variables") or []):
            book.mark(group, key, "empty")
        else:
            book.mark(group, key, "searched")


def _why(book, group: str, key: str, said: str) -> None:
    """🔴 장부 칸의 **사유** — `Book` 이 칸을 들면 그것을 쓰고, 없으면 만든다."""
    box = getattr(book, "whys", None)
    if box is None:
        box = {}
        book.whys = box
    box[(str(group), str(key))] = str(said)


def second_round(book, groups: list, keys: list) -> list[tuple[str, str]]:
    """🔴🔴 **③ 2차 보충 — 최대 1회**(M64 · 지시서 §3-3).

    > 장부에서 `not_tried`·`empty` 인 유형군만 골라, 남은 예산 안에서 해당
    > 하위 과제를 **한 번** 다시 돌린다(턴 6). 2차 뒤에도 비면 그대로 `gaps`
    > 로 보고한다 — **3차는 없다.**

    돌려주는 것은 다시 돌 `(유형군, 팀 열쇠)` 들이다.
    """
    out: list[tuple[str, str]] = []
    for g in (groups or []):
        for k in (keys or []):
            if book.state(str(g), str(k)) in SECOND_STATES:
                out.append((str(g), str(k)))
    logger.info("[lead] 2차 보충 %d칸 — %s", len(out),
                " · ".join(f"{g}/{k}" for g, k in out[:8]) or "없다")
    return out


def second_budget(used: list) -> dict[str, int]:
    """🔴 **남은 예산**(지시서 §3-3: *"남은 예산(미사용 search/fetch/토큰) 안에서"*).

    ⚠️ 합계 상한은 기존 그대로다 — 2차가 상한을 넘지 않는다.
    """
    from app import solar
    box = dict(solar.budget_cfg().get("per_subtask") or {})
    n = len(used or []) or 1
    cap_s = int(box["search"]) * n
    cap_f = int(box["fetch"]) * n
    cap_o = int(box["output_tokens"]) * n
    got_s = sum(int((u or {}).get("searched") or 0) for u in (used or []))
    got_f = sum(int((u or {}).get("fetched") or 0) for u in (used or []))
    got_o = sum(int((u or {}).get("out") or 0) for u in (used or []))
    return {"search": max(0, cap_s - got_s), "fetch": max(0, cap_f - got_f),
            "out": max(0, cap_o - got_o)}


def _k(n: object) -> str:
    """🔴 토큰을 `4.1k` 꼴로 — 자리를 아낀다(지시서 §3-4 의 예시 그대로)."""
    got = int(n or 0)
    return f"{got / 1000:.1f}k" if got >= 1000 else str(got)


def funnel_lines(parts: list) -> list[str]:
    """🔴🔴 **④ 깔때기 집계**(지시서 §3-4).

    > 하위별 한 줄(`A-홈: q3 통과2 거부1 fetch2 후보4 검증3 4.1k tok 38s`)과
    > **합계**를 기존 깔때기 로그에 쓴다.
    """
    out: list[str] = []
    tot = dict.fromkeys(("searched", "passed", "rejected", "fetched",
                         "cands", "verified", "out"), 0)
    secs = 0.0
    for p in (parts or []):
        box = dict(p or {})
        for k in tot:
            tot[k] += int(box.get(k) or 0)
        secs = max(secs, float(box.get("secs") or 0))
        out.append(
            f"  {box.get('name') or '?'}: q{int(box.get('searched') or 0)} "
            f"통과{int(box.get('passed') or 0)} "
            f"거부{int(box.get('rejected') or 0)} "
            f"fetch{int(box.get('fetched') or 0)} "
            f"후보{int(box.get('cands') or 0)} "
            f"검증{int(box.get('verified') or 0)} "
            f"{_k(box.get('out'))} tok {float(box.get('secs') or 0):.0f}s")
    out.append(
        f"  합계: q{tot['searched']} 통과{tot['passed']} 거부{tot['rejected']} "
        f"fetch{tot['fetched']} 후보{tot['cands']} 검증{tot['verified']} "
        f"{_k(tot['out'])} tok · 벽시계 {secs:.0f}s(병렬 최댓값)")
    return out
