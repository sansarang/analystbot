"""🔴🔴 **§5 — 재정렬 2단**(작업 지시서 2026-10-05).

> 모델 — `BAAI/bge-reranker-v2-m3`(다국어 크로스인코더: 영·한·일·스페인어).
> **모듈 전역 싱글턴**으로 한 번만 로드한다(하위 8개가 공유).
>
> 폴백 사다리(M62) — ① `bge-reranker-v2-m3` → ② FlashRank
> `ms-marco-MultiBERT-L-12`(다국어) → ③ **재정렬 없음**(현재 순서 그대로) +
> `rerank_unavailable` 로그. **어느 단계에서도 분석은 멈추지 않는다.**
>
> ⚠️ FlashRank 기본 모델(`ms-marco-MiniLM` 계열)은 **영어 전용**이라 쓰지
>    않는다 — 다국어 모델명을 명시로 박는다.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger(__name__)

#: 🔴🔴 **폴백 사다리**(M62) — 지시서 §5 가 세 단을 **이름까지** 줬다.
#
#  ⚠️ FlashRank 기본 모델(`ms-marco-MiniLM` 계열)은 **영어 전용**이라 쓰지
#     않는다 — 다국어 모델명을 **명시로 박는다**(지시서 원문).
#  🔴 ③단은 *"재정렬 없음(현재 순서 그대로) + `rerank_unavailable` 로그"* 다 —
#     **어느 단계에서도 분석은 멈추지 않는다.**
LADDER: tuple[dict, ...] = (
    {"name": "bge-reranker-v2-m3", "how": "cross-encoder",
     "model": "BAAI/bge-reranker-v2-m3"},
    {"name": "flashrank-multibert", "how": "flashrank",
     "model": "ms-marco-MultiBERT-L-12"},
    {"name": "none", "how": "none", "model": ""},
)

#: 🔴 재정렬 뒤 프롬프트에 넣는 문단 수 — `readtext` 가 이름을 든다(#1 사본 금지).
#: 🔴 **모듈 전역 싱글턴** — 하위 8개가 공유한다(지시서 §5: *"한 번만 로드"*).
#   ⚠️ `None` 은 *"아직 안 해봤다"*, `False` 는 *"해봤고 없다"* 다 — 둘을
#      가르지 않으면 실패할 때마다 다시 받으려 한다.
_MODEL: Any = None
_WHY: str = ""

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **MPS 는 한 스레드가 소유한다** — 사용자 지시 2026-10-05
# ══════════════════════════════════════════════════════════════════
#
#  > 락 추가로 **땜질하지 않는다.** PyTorch 이슈 #197805: MPS 는 2개 이상
#  > 스레드가 동시 연산하면 **SIGSEGV/SIGABRT** 로 죽는다.
#  > 모듈 전역 `ThreadPoolExecutor(max_workers=1, thread_name_prefix="rerank")`
#  > 를 두고 **모델 로드·추론을 전부 그 안에서만** 한다.
#
#  ⚠️ 실사고 2026-10-05(인도네시아–태국): 락을 넣었더니 로드가 **4→11회로
#     늘고** 봇이 두 번 죽었다. 🔴 락은 *"같은 스레드"* 를 보장하지 않는다 —
#     여러 스레드가 번갈아 모델을 쓰는 것을 막지 못한다. **소유**가 필요하다.
#  🔴 `max_workers=1` 이므로 스레드 이름은 늘 `rerank_0` 이다 — 계약이 그
#     이름으로 소유를 확인한다.
RERANK_EXEC = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rerank")

#: 🔴 그 스레드가 들고 있는 모델. ⚠️ **다른 스레드는 읽지도 않는다** —
#   읽기만 해도 지연 초기화가 섞이면 소유가 깨진다.
_MODEL: Any = None
_WHY: str = ""
#: 🔴 **로드 횟수** — 사용자 지시 2: *"로드 횟수 카운터를 두고 계약: 경기 하나
#   분석 동안 로드 1회."* ⚠️ 이 수가 1 보다 크면 이중 import 거나 예열 누락이다.
_LOADS: int = 0


#: 🔴 **느리다고 보는 초** — 지시서 §5: *"넘으면 batch 를 늘리지 말고 1단만
#  유지하고 2단을 BM25 상위 8로 폴백(사유 `rerank_slow`)."*
SLOW_AT = 3.0


def slow_note(secs: float) -> str:
    """🔴 그 추론이 **느렸나** — 느리면 사유를 글로 남긴다(#3)."""
    got = float(secs or 0)
    if got <= SLOW_AT:
        return ""
    return (f"⚠️ `rerank_slow` — 재정렬이 {got:.1f}초 걸렸다(상한 "
            f"{SLOW_AT:g}초). 🔴 batch 를 늘리지 않는다 — 다음은 **BM25 상위 "
            f"8**로 간다(§5)")


def loads() -> int:
    """🔴 모델을 **몇 번** 올렸나(지시 2)."""
    return _LOADS


def reset() -> None:
    """🔴 싱글턴·횟수를 비운다 — 계약이 쓴다."""
    global _MODEL, _WHY, _LOADS
    _MODEL, _WHY, _LOADS = None, "", 0


def _load_in_thread(_load=None) -> Any:
    """🔴🔴 **전용 스레드 안에서** 모델을 올린다 — 여기서만 올린다.

    🔴 첫 줄에 `__name__` 과 `id(sys.modules[__name__])` 를 적는다(지시 2):
       **두 이름이 나오면 이중 import** 이고, 그것이 로드가 늘어난 원인이다.
    ⚠️ 예외를 위로 던지지 않는다(M62) — ③단으로 간다.
    """
    global _MODEL, _WHY, _LOADS
    _LOADS += 1
    logger.info("[rerank] 로드 #%d — mod=%s id=%s pid=%s tid=%s(%s)",
                _LOADS, __name__, id(sys.modules[__name__]), os.getpid(),
                threading.get_ident(), threading.current_thread().name)
    try:
        _MODEL = (_load or _ladder)() or False
    except Exception as exc:                                # noqa: BLE001
        _MODEL = False
        _WHY = (f"🔴 `rerank_unavailable` — 모델 로드가 터졌다"
                f"({type(exc).__name__}: {str(exc)[:80]})")
        logger.info("[rerank] %s", _WHY)
    return _MODEL


def _device() -> str:
    """🔴 `mps` 가능하면 `mps`, 아니면 `cpu`(지시서 §5).

    ⚠️ **전용 스레드 안에서만** 불린다 — MPS 소유가 그 스레드다.
    """
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:                                       # noqa: BLE001
        pass
    return "cpu"


def _ladder() -> Any:
    """🔴 사다리 ①→②→③. ⚠️ **전용 스레드 안에서만** 불린다."""
    global _WHY
    for step in LADDER:
        how = str(step["how"])
        if how == "none":
            _WHY = (f"🔴 `rerank_unavailable` — 사다리 끝({step['name']})까지 "
                    f"왔다. 순서를 **그대로 둔다**(분석은 멈추지 않는다)")
            return False
        try:
            if how == "cross-encoder":
                from sentence_transformers import CrossEncoder
                dev = _device()
                got = CrossEncoder(str(step["model"]), max_length=512,
                                   device=dev)
                _WHY = f"✅ {step['name']} ({dev})"
                logger.info("[rerank] %s", _WHY)
                return got
            if how == "flashrank":
                from flashrank import Ranker
                got = Ranker(model_name=str(step["model"]))
                _WHY = f"⚠️ 폴백 {step['name']} — ①단을 못 썼다"
                logger.info("[rerank] %s", _WHY)
                return got
        except Exception as exc:                            # noqa: BLE001
            logger.info("[rerank] %s 를 못 썼다(%s): %r", step["name"],
                        type(exc).__name__, str(exc)[:120])
            continue
    _WHY = "🔴 `rerank_unavailable` — 사다리를 다 밟았다"
    return False


def warm(_load=None) -> str:
    """🔴🔴 **시작 시 1회 로드 + 예열**(지시 2) — 봇 진입점이 부른다.

    > 봇 시작에서 **전용 스레드로** 모델 로드 + 더미 쌍 1개 `predict`.
    > **지연 로드 함수 삭제.**

    ⚠️ 예열까지 하는 까닭: 첫 추론이 가중치를 mps 로 옮긴다 — 그것을 분석
       중에 하면 그 경기만 느리고, **다른 스레드에서** 하면 소유가 깨진다.
    🔴 두 번 불러도 **한 번만** 올린다(`loads()` 가 1 이다).
    """
    def _job() -> str:
        # 🔴 **테스트는 실모델을 올리지 않는다**(사용자 지시 2026-10-05).
        #    ⚠️ `_load` 를 **준** 계약은 통과시킨다 — 가짜 재정렬기다.
        if _load is None and os.environ.get("ANALYSTBOT_TEST"):
            global _WHY
            _WHY = ("🔴 `rerank_unavailable` — `ANALYSTBOT_TEST=1` 이라 "
                    "실모델을 올리지 않았다(가짜 재정렬기를 주입하라)")
            return _WHY
        if _MODEL is None:
            _load_in_thread(_load)
        box = _MODEL
        if box:
            # 🔴 **더미 쌍 하나**로 예열한다(지시 2)
            try:
                _scored_here(box, [("예열", "warm up pair")])
            except Exception as exc:                        # noqa: BLE001
                logger.info("[rerank] 예열 실패(무해): %r", str(exc)[:80])
        return _WHY or "🔴 `rerank_unavailable`"

    return RERANK_EXEC.submit(_job).result()


def _call(fn, *args) -> Any:
    """🔴 **전용 스레드에서** 부른다 — 다른 길은 없다.

    ⚠️ 이미 그 스레드면 바로 부른다(`submit` 하면 자기를 기다려 교착된다).
    """
    if threading.current_thread().name.startswith("rerank"):
        return fn(*args)
    return RERANK_EXEC.submit(fn, *args).result()


def why() -> str:
    """🔴 **어느 단으로 돌았나** — 카드·로그가 그대로 적는다(#3)."""
    return _WHY


def _scored(got: Any, pairs: list) -> list[float] | None:
    """🔴 그 모델로 점수를 낸다. ⚠️ 못 내면 `None` — 호출부가 순서를 둔다.

    🔴 **전용 스레드에서** 돈다(`_call`) — 락이 아니라 **소유**다.
       MPS 는 두 스레드가 동시에 연산하면 SIGSEGV 로 죽는다(#197805).
    """
    return _call(_scored_here, got, pairs)


def _scored_here(got: Any, pairs: list) -> list[float] | None:
    """🔴 **전용 스레드 안**의 추론 본체. ⚠️ 직접 부르지 않는다(`_scored` 경유).

    느리면 사유를 남긴다(`rerank_slow` · 지시서 §5).
    """
    import time as _t
    global _WHY
    at = _t.monotonic()
    out = _scored_inner(got, pairs)
    said = slow_note(_t.monotonic() - at)
    if said:
        _WHY = f"{_WHY} · {said}"
        logger.info("[rerank] %s", said)
    return out


def _scored_inner(got: Any, pairs: list) -> list[float] | None:
    try:
        if hasattr(got, "predict"):
            return [float(x) for x in got.predict(pairs, batch_size=16)]
        if hasattr(got, "rerank"):
            # FlashRank 꼴 — 질의 하나에 문서 여러 개
            from flashrank import RerankRequest
            q = pairs[0][0] if pairs else ""
            req = RerankRequest(query=q,
                                passages=[{"id": i, "text": t}
                                          for i, (_q, t) in enumerate(pairs)])
            out = got.rerank(req)
            by = {int(r["id"]): float(r.get("score") or 0.0) for r in out}
            return [by.get(i, 0.0) for i in range(len(pairs))]
    except Exception as exc:                                # noqa: BLE001
        logger.info("[rerank] 점수를 못 냈다: %r", str(exc)[:120])
    return None


def order(query: str, rows: list, *, _load=None,
          _force: str = "") -> tuple[list, str]:
    """🔴🔴 **1단 — 받기 전 재정렬**(지시서 §5).

    > 입력: 질의당 결과 **최대 30건**의 `(질의문, 제목+스니펫)` 쌍.
    > 🔴 재정렬은 **순서만** 바꾼다 — fetch 수를 늘리지 않고(M62), 필터를
    > 통과 못 한 결과를 **되살리지 않는다.**

    돌려주는 것은 `(정렬된 행들, 어느 단으로 돌았나)`.
    ⚠️ 행 수는 **절대 안 바뀐다** — 그것이 M62 의 절반이다.
    """
    got = list(rows or [])
    if _force == "none":
        return got, ("🔴 `rerank_unavailable` — 호출부가 ③단을 지정했다"
                     "(순서 그대로)")
    # 🔴 **지연 로드를 안 한다**(지시 2) — 시작 시 `warm()` 이 올린다.
    #    ⚠️ 아직 안 올렸으면 ③단이다(사유가 그것을 말한다).
    box = _MODEL
    if not box:
        return got, why() or ("🔴 `rerank_unavailable` — 아직 예열되지 "
                              "않았다(`warm()` 을 안 불렀다)")
    pairs = [(str(query or ""),
              " ".join(str(r.get(k) or "") for k in ("title", "snippet",
                                                     "content")).strip())
             for r in got]
    scores = _scored(box, pairs)
    if scores is None or len(scores) != len(got):
        return got, "🔴 `rerank_unavailable` — 점수를 못 냈다(순서 그대로)"
    ranked = [r for _s, r in sorted(zip(scores, got, strict=False),
                                    key=lambda sr: -sr[0])]
    return ranked, f"{why()} · {len(ranked)}건 재정렬(순서만)"


def take(rows: list, *, cap: int) -> list:
    """🔴 상위에서 **fetch 상한까지**만(지시서 §5: *"하위당 2"*).

    ⚠️ 재정렬이 fetch 수를 늘리지 않는다는 말의 **집행 자리**다(M62).
    """
    return list(rows or [])[:max(0, int(cap))]


def _pool(rows: list, query: str) -> list[str]:
    """🔴🔴 **재정렬 대상 문단 20개**(지시서 §5: *"BM25 상위 20"*).

    ⚠️ 실사고 2026-10-05: `readtext.top_paragraphs` 는 **BM25 0점 문단을
       버린다**. 그래서 48문단 중 **17개**만 나왔고, 동의어만 든 문단
       (`"Mbappé remains sidelined"`)이 **재정렬 대상에 들지도 못했다** —
       M65 가 막으려는 바로 그 일이 pool 단계에서 났다.
    🔴 지시서가 **"상위 20"** 이라고 수를 줬다 — 그 수를 채운다. 점수순을
       앞에 두고 모자라면 **본문 순서로** 채운다(버리지 않는다).
    """
    from app import readtext
    best = readtext.top_paragraphs("\n".join(rows), query,
                                   n=readtext.BM25_POOL)
    out = list(best)
    for p in rows:
        if len(out) >= readtext.BM25_POOL:
            break
        if p not in out:
            out.append(p)
    return out


def paragraphs(query: str, paras: list, *, _load=None,
               _force: str = "") -> tuple[list, str]:
    """🔴🔴 **2단 — 본문 문단**(지시서 §5).

    > `trafilatura` 본문 → 문단 분할 → **BM25 상위 20** → reranker 로 재점수
    > → **상위 8 문단만** 하위 에이전트 프롬프트에 넣는다.
    >
    > 질의는 하위 과제의 **유형 핵심어 문장** — 이게 BM25 가 놓치는 동의어
    > (`"won't feature"`·`"ruled out"`·`"이탈"`·`"欠場"`)를 잡는 자리다.

    ⚠️ 폴백: 모델이 없으면 **BM25 상위 8**로 간다(사유 `rerank_slow`/
       `rerank_unavailable`) — 지시서가 그 퇴로를 적었다.
    """
    from app import readtext
    rows = [str(p) for p in (paras or []) if str(p).strip()]
    pool = _pool(rows, str(query or ""))
    # 🔴 **폴백은 `BM25 상위 8`이다**(지시서 §5: *"2단을 BM25 상위 8로 폴백"*).
    #    ⚠️ 실사고 2026-10-05: `pool[:8]` 을 썼는데 `_pool` 은 **본문 순서**로
    #       돌려준다(`top_paragraphs` 의 규약) — 그래서 폴백이 *"본문 앞 8"* 이
    #       됐고, 동의어 문단이 **거기 들어** R17 돌연변이가 통과했다.
    #    🔴 상위 8 은 `top_paragraphs(n=PROMPT_PARAS)` 가 고른다 — 한 곳이다.
    fall = readtext.top_paragraphs("\n".join(rows), str(query or ""),
                                   n=readtext.PROMPT_PARAS)
    if _force == "none":
        return fall, "🔴 `rerank_unavailable` — ③단 지정(BM25 상위 8로 간다)"
    box = _MODEL
    if not box:
        return fall, why() or ("🔴 `rerank_unavailable` — 아직 예열되지 "
                               "않았다(`warm()` 을 안 불렀다)")
    scores = _scored(box, [(str(query or ""), p) for p in pool])
    if scores is None or len(scores) != len(pool):
        return fall, "🔴 `rerank_unavailable` — 점수를 못 냈다(BM25 상위 8)"
    ranked = [p for _s, p in sorted(zip(scores, pool, strict=False),
                                    key=lambda sp: -sp[0])]
    return (ranked[:readtext.PROMPT_PARAS],
            f"{why()} · BM25 {len(pool)}문단 → 재정렬 상위 "
            f"{readtext.PROMPT_PARAS}")
