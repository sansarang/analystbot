"""🔴🔴 **v6 — 재정렬도 녹음한다.** `rerank` 를 거치는 **유일한 자리**(§5 · §7).

══════════════════════════════════════════════════════════════════
🔴 왜 이 파일이 생겼나 — 실측 2026-10-06
══════════════════════════════════════════════════════════════════

재생 테스트가 **변수 0개**를 냈다. 까닭을 재어 보니 재정렬이었다:

| 어디서 | 재정렬 | 결과 |
|---|---|---|
| 라이브(`tools/v6_run.py`) | ✅ `bge-reranker-v2-m3` (mps) | `C-홈` 문단 4개 |
| 재생(pytest) | 🔴 **모델 없음**(`ANALYSTBOT_TEST=1`) → BM25 | `C-홈` 문단 6개 |

🔴 입력이 달라지면 **추출 요청이 달라지고** LLM 카세트가 전부 빗나간다.
⚠️ 그런데 **테스트는 실모델을 올리지 않는다**(사용자 지시 2026-10-05: 스위트가
   11분이 됐다) — 그러니 "테스트에서도 모델을 켠다"는 길은 막혀 있다.

🔴 그래서 **재정렬 결정을 카세트에 녹음한다.** 외부 호출을 녹음하는 그 장치
   하나로 **지역 모델의 결정**도 고정한다 — 재생은 모델 없이, 라이브와 **같은
   순서**로 돈다. ⚠️ 빗나가면 `replay_miss` 로 **실패한다**(몰래 BM25 로 떨어지지
   않는다 · §5).
"""
from __future__ import annotations

import hashlib
from typing import Any

#: 🔴 카세트 종류 이름 — 열기(`fetch`)·검색(`search`)·LLM 과 갈린다
KIND = "rerank"
#: 🔴 열쇠의 `url` 자리 — 망 주소가 아니라 **무엇을 재정렬했나**를 적는다
WHERE = "local://rerank"


def _key_of(query: str, rows: list[str]) -> str:
    """🔴 같은 질의·같은 줄들이면 같은 글자. ⚠️ **순서까지** 센다(입력이 다르면 다르다)."""
    box = hashlib.sha256()
    box.update(str(query).encode("utf-8", "replace"))
    for r in rows:
        box.update(b"\x00")
        box.update(str(r).encode("utf-8", "replace"))
    return f"n={len(rows)} {box.hexdigest()[:32]}"


def paragraphs(query: str, rows: list[str]) -> tuple[list[str], str]:
    """🔴 `rerank.paragraphs` 와 같은 꼴 — 녹음·재생을 거친다. `(순서, 사유)`.

    🔴 재생에서 **모델을 올리지 않는다** — 녹음된 순서를 그대로 돌려준다.
    ⚠️ 녹음이 없으면 `replay_miss` 를 사유로 **빈 순서**를 돌려준다(부르는 쪽이
       그것을 보고 원래 순서를 쓴다 — 조용히 다른 순서로 가지 않는다).
    """
    from app import cassette
    said = [str(r) for r in (rows or [])]
    if not said:
        return [], "줄이 없다"
    qs = _key_of(query, said)
    if cassette.mode() == cassette.REPLAY:
        try:
            got = cassette.load(KIND, WHERE, qs)
        except cassette.CassetteMiss as exc:
            if not cassette.fallthrough():
                return [], f"🔴 {exc}"
            got = None
        if got is not None:
            order = [str(x) for x in (got.get("order") or [])]
            return order, f"재생 — {got.get('why') or ''}".strip()
    from app.research import rerank
    order, why = rerank.paragraphs(query, said)
    out = [str(x) for x in order]
    if cassette.mode() in (cassette.RECORD, cassette.REPLAY):
        cassette.save(KIND, WHERE, qs, {"order": out, "why": str(why),
                                        "query": str(query)[:200]})
    return out, str(why)


def warm() -> str:
    """🔴 라이브는 입구에서 예열한다 — 재생에서는 **아무것도 올리지 않는다**."""
    from app import cassette
    if cassette.mode() == cassette.REPLAY:
        return "재생 — 모델을 올리지 않는다"
    from app.research import rerank
    return str(rerank.warm())


def order_of(rows: list[Any], key: Any, query: str
             ) -> tuple[list[Any], str]:
    """🔴 `rows` 를 재정렬 순서로 **다시 늘어놓는다**. `(줄들, 사유)`.

    `key(row)` 는 그 줄을 글자로 만드는 함수다(제목+스니펫·문단 글자).
    ⚠️ 순서를 못 받으면 **그대로** 돌려주고 사유를 함께 낸다 — 조용히 다른 순서로
       가지 않는다. 🔴 못 받은 줄은 **뒤로** 간다(빠뜨리지 않는다 · #3).
    """
    said = [str(key(r)) for r in rows]
    got, why = paragraphs(query, said)
    if not got:
        return list(rows), why
    rank = {t: i for i, t in enumerate(got)}
    return sorted(rows, key=lambda r: rank.get(str(key(r)), len(got))), why
