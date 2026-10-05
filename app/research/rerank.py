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
import threading
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

#: 🔴🔴 **싱글턴 락** — 실사고 2026-10-05 (인도네시아–태국): 봇이 **죽었다.**
#
#  하위 4개가 `asyncio.to_thread` 안에서 **동시에** `model()` 을 불러
#  `_MODEL is None` 을 넷이 함께 봤고, 수 GB 모델이 **네 번** mps 에 올라가
#  프로세스가 끝났다(`resource_tracker: There appear to be …`).
#
#  ⚠️ `asyncio.Lock` 이 아니라 `threading.Lock` 이다 — 하위는 **스레드**에서
#     돈다(`to_thread`). 🔴 LDR 의 속도 제한 모듈도 같은 꼴을 쓴다(메타 락으로
#     게으른 생성을 감싼다 — 읽고 확증했다).
_LOCK = threading.Lock()

#: 🔴🔴 **추론 락** — 로드 락과 **따로** 둔다.
#  ⚠️ 로드를 한 번으로 줄여도 하위 8개가 **동시에 mps 추론**을 하면 같은
#     리소스를 다툰다. 🔴 지시서 §5 가 *"mps 에서 1초 안팎 · 경기 전체 30초
#     이내"* 라 했으니 **직렬이어도 그 안**이다.
_RUN = threading.Lock()

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


def reset() -> None:
    """🔴 싱글턴을 비운다 — 계약이 로드 횟수를 셀 때 쓴다."""
    global _MODEL, _WHY
    _MODEL, _WHY = None, ""


def _load_model() -> Any:
    """🔴 ①단 → ②단 → ③단. **예외를 위로 던지지 않는다**(M62).

    ⚠️ 모델이 수 GB 다 — 받을 수 없는 기계에서는 ③단으로 가고 **그 사실을
       이름으로** 남긴다(#3). 🔴 거기서 멈추면 분석이 통째로 죽는다.
    """
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
                # 🔴 **누가 로드했나를 적는다** — 실측 2026-10-05: 락을 넣었는데
                #    로드가 4→11회로 **늘었다**. 추측하지 않고 잰다(#4):
                #    같은 프로세스·같은 모듈이면 락이 걸려야 한다.
                import os as _os
                import threading as _th
                logger.info("[rerank] %s · pid=%s tid=%s mod=%s", _WHY,
                            _os.getpid(), _th.get_ident(), id(globals()))
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


def _device() -> str:
    """🔴 `mps` 가능하면 `mps`, 아니면 `cpu`(지시서 §5)."""
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:                                       # noqa: BLE001
        pass
    return "cpu"


def model(_load=None) -> Any:
    """🔴 싱글턴을 돌려준다 — **한 번만** 로드한다(지시서 §5).

    ⚠️ `_load` 는 계약용 주입구다(기계에 모델이 없어도 사다리를 시험한다).
    """
    global _MODEL, _WHY
    # 🔴 **빠른 길** — 이미 받았으면 락을 잡지 않는다(하위 8개가 공유한다)
    if _MODEL is not None:
        return _MODEL
    with _LOCK:
        # 🔴 **락 안에서 다시 본다** — 기다리는 동안 다른 스레드가 받았을 수 있다
        if _MODEL is not None:
            return _MODEL
        try:
            _MODEL = (_load or _load_model)() or False
        except Exception as exc:                            # noqa: BLE001
            # 🔴 **위로 던지지 않는다**(M62) — 분석이 통째로 죽는다
            _MODEL = False
            _WHY = (f"🔴 `rerank_unavailable` — 모델 로드가 터졌다"
                    f"({type(exc).__name__}: {str(exc)[:80]})")
            logger.info("[rerank] %s", _WHY)
    return _MODEL


def why() -> str:
    """🔴 **어느 단으로 돌았나** — 카드·로그가 그대로 적는다(#3)."""
    return _WHY


def _scored(got: Any, pairs: list) -> list[float] | None:
    """🔴 그 모델로 점수를 낸다. ⚠️ 못 내면 `None` — 호출부가 순서를 둔다.

    🔴 **직렬이다**(`_RUN`) — 한 모델을 여러 스레드가 동시에 쓰면 리소스를
       다툰다(실사고 2026-10-05: 프로세스가 죽었다).
    """
    import time as _t
    with _RUN:
        at = _t.monotonic()
        out = _scored_inner(got, pairs)
        said = slow_note(_t.monotonic() - at)
    if said:
        global _WHY
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
    box = model(_load)
    if not box:
        return got, why() or "🔴 `rerank_unavailable`"
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
    box = model(_load)
    if not box:
        return fall, why() or "🔴 `rerank_unavailable`"
    scores = _scored(box, [(str(query or ""), p) for p in pool])
    if scores is None or len(scores) != len(pool):
        return fall, "🔴 `rerank_unavailable` — 점수를 못 냈다(BM25 상위 8)"
    ranked = [p for _s, p in sorted(zip(scores, pool, strict=False),
                                    key=lambda sp: -sp[0])]
    return (ranked[:readtext.PROMPT_PARAS],
            f"{why()} · BM25 {len(pool)}문단 → 재정렬 상위 "
            f"{readtext.PROMPT_PARAS}")
