"""🔴🔴 **기사를 사람처럼 읽는다** — 본문 추출 + 관련 문단 선별.

사용자 기술 지시 2026-10-03:

> 나는 검색 요약이 아니라 **본문을 읽는다**. 봇은 `trafilatura` 로 광고·메뉴를 걷어낸
> 본문을 얻고, 팀·선수 이름이 나오는 문단만 **BM25** 로 골라 LLM 에 넘긴다.
> **입력이 짧아야 8B 모델도 정확하다.**

══════════════════════════════════════════════════════════════════
🔴 왜 이 파일이 생겼나 — 실측이 요구했다
══════════════════════════════════════════════════════════════════

종전 경로는 이랬다:

```
_strip_tags(html)      정규식으로 태그만 벗긴다 (광고·메뉴·푸터가 남는다)
  → body[:4000]        **앞 4000자**를 그대로 LLM 에 넘긴다
```

🔴 그래서 두 가지가 동시에 깨졌다:

1. **광고·메뉴가 입력을 채운다.** 8B 모델은 긴 잡음에서 문장을 섞어 낸다.
2. **앞을 자른다.** 타순·감독 발언은 기사 **뒤쪽**에 있다 — 실측 로그가
   *"본문 3329자 중 2500자만 넘겼다"* 를 네 번 적었고, 그 네 번이 전부 `unknown` 이었다.

⚠️ 좁은 질문(③)과 인용 검증(④)은 **이미 있었다.** 못 맞힌 까닭은 판정이 아니라
   **입력**이었다. 그래서 이 파일이 그 둘의 정확도를 올리는 **유일한 길**이다.

🔴 **BM25 를 직접 쓴다** — `rank_bm25` 를 들이지 않는다. 20줄이면 되고, 의존성 하나가
   늘면 설치가 무거워지고 무엇이 살아 있는지 알기 어려워진다(pyproject 머리글의 규율).
"""
from __future__ import annotations

import logging
import math
import re

logger = logging.getLogger(__name__)

#: 🔴 문단으로 볼 최소 길이. 짧은 줄은 메뉴·버튼·캡션이다.
#   ⚠️ 사용자 예시 코드가 `len(p) > 60` 이다 — 그것을 그대로 쓴다.
MIN_PARA = 60

#: 🔴🔴 **1단 재료 수** — BM25 가 뽑는 문단 수(§5 지시서 2026-10-05).
#  > `trafilatura` 본문 → 문단 분할 → **BM25 상위 20** → reranker 로 재점수
#  > → **상위 8 문단만** 하위 에이전트 프롬프트에 넣는다.
#  ⚠️ 종전 `TOP_PARAS = 6` 은 **BM25 단독 선택**이었고 동의어 표현
#     ("won't feature")을 놓쳤다 — 그래서 §5 하이브리드로 바꿨다.
BM25_POOL = 20
#: 🔴 재정렬 뒤 **프롬프트에 넣는** 문단 수(§5).
PROMPT_PARAS = 8

#: BM25 의 두 상수. 🔴 **정보검색 교과서 값이다** — 우리가 맞춘 모수가 아니다
#  (Robertson 의 원 논문 이후 `k1∈[1.2,2.0]`·`b=0.75` 가 표준이다).
BM25_K1 = 1.5
BM25_B = 0.75

#: 🔴 낱말 자르기. 라틴·한글을 덩어리로 보고, **글자 2-그램**을 함께 센다.
#
#  ⚠️ 두 언어가 공백으로 안 갈린다:
#    일본어·중국어 — 애초에 띄어쓰기가 없다
#    🔴 **한국어 — 조사가 붙는다.** 실측 2026-10-03: 질의 `앙굴로` 가 본문
#       `앙굴로**가** 발목 부상으로…` 를 못 맞혔다(토큰이 `앙굴로가` 다).
#       이 저장소가 같은 병으로 전에도 다쳤다(기사 속 선수명 매칭).
#  🔴 그래서 **한글도 2-그램에 넣는다**: `앙굴로가` → 앙굴·굴로·로가,
#     질의 `앙굴로` → 앙굴·굴로 → 맞는다.
#  ⚠️ 2-그램은 잡음을 늘리지만 BM25 의 `idf` 가 흔한 조각의 무게를 낮춘다.
_WORD = re.compile(r"[0-9A-Za-zÀ-ɏ]+|[가-힣]+")
_NGRAM = re.compile(r"[぀-ヿ一-鿿가-힣]")


def published_of(html: str, *, url: str = "") -> str:
    """🔴🔴 **③층 — 발행일의 원본**(사용자 지시 2026-10-05).

    > **fetch 후**: `htmldate` 로 발행일을 뽑는다(**메타·JSON-LD·time 태그**).
    > 이 값이 `published_at` 의 **원본**이다. 검색 엔진이 준 날짜는 보조로만.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 이 층이 필요한가 — 실측 2026-10-05
    ══════════════════════════════════════════════════════════════════

    SearXNG 이 **발행 시각을 주지 않는다**(엔진 전부 `publishedDate` 0건).
    그래서 날짜는 **본문에서** 와야 한다. ⚠️ `trafilatura` 의 `date` 도
    `htmldate` 를 쓰지만 보수적이라 놓치는 자리가 있다 — 그래서 **직접** 부르고
    `extensive_search` 로 `time` 태그·JSON-LD 까지 본다.

    🔴 **못 찾으면 빈 문자열**이다 — 지어내지 않는다(#4). 그러면 기존 규칙대로
       `date_missing` 으로 변수 근거에서 빠진다.
    """
    if not str(html or "").strip():
        return ""
    try:
        from htmldate import find_date
    except ImportError as exc:                              # pragma: no cover
        logger.info("[readtext] htmldate 가 없다: %s", exc)
        return ""
    try:
        got = find_date(html, url=url or None, extensive_search=True,
                        outputformat="%Y-%m-%d",
                        # 🔴 **원본 발행일**을 원한다 — 수정일이 아니다
                        original_date=True)
    except Exception as exc:                                # noqa: BLE001
        logger.info("[readtext] 발행일 추출 실패(%s): %r", str(url)[:60], exc)
        return ""
    return str(got or "").strip()


def extract(html: str, *, url: str = "") -> tuple[str, str]:
    """HTML → `(본문, 발행일 문자열)`. 🔴 못 뽑으면 `("", "")`.

    ⚠️ `trafilatura` 가 **광고·메뉴·푸터를 걷는다**(우리 정규식은 태그만 걷었다).
    🔴 실패하면 **빈 문자열**이다 — 호출부가 종전 경로(`_strip_tags`)로 떨어진다.
       여기서 조용히 태그만 걷어 돌려주면 *"본문을 뽑았다"* 가 거짓이 된다.
    """
    if not (html or "").strip():
        return "", ""
    try:
        import trafilatura
        from trafilatura.settings import use_config
    except ImportError as exc:                              # pragma: no cover
        logger.info("[readtext] trafilatura 가 없다: %s", exc)
        return "", ""
    try:
        cfg = use_config()
        # 🔴 **네트워크에 나가지 않는다** — 이 함수는 이미 받아 온 HTML 만 읽는다.
        #    ⚠️ trafilatura 는 기본값에서 외부 요청을 할 수 있다(URL 보강).
        cfg.set("DEFAULT", "EXTRACTION_TIMEOUT", "0")
        got = trafilatura.extract(
            html, url=url or None, config=cfg,
            # 🔴 댓글·표는 뺀다 — 기사 본문이 아니다
            include_comments=False, include_tables=False,
            # ⚠️ 발행일을 함께 받는다(§12-c-1 날짜 검증의 재료다)
            with_metadata=True, output_format="json")
    except Exception as exc:                                # noqa: BLE001
        logger.info("[readtext] 본문 추출 실패(%s): %r", url[:60], exc)
        return "", ""
    if not got:
        return "", ""
    import json
    try:
        doc = json.loads(got)
    except ValueError:
        return "", ""
    text = str(doc.get("text") or "").strip()
    # 🔴 **③층이 원본이다**(지시 2026-10-05) — `htmldate` 를 직접 부른다.
    #    ⚠️ trafilatura 의 `date` 는 보수적이라 `time` 태그·JSON-LD 를 놓친다.
    #       그것은 **퇴로**로 둔다(둘 다 없으면 빈 글 → `date_missing`).
    when = published_of(html, url=url) or str(doc.get("date") or "").strip()
    if text:
        logger.info("[readtext] 본문 %d자 · 발행 %s · %s", len(text),
                    when or "미상", url[:60])
    return text, when


def paragraphs(text: str) -> list[str]:
    """본문 → 문단 목록. 🔴 짧은 줄은 **버린다**(메뉴·버튼·캡션이다)."""
    out = []
    for raw in str(text or "").replace("\r", "\n").split("\n"):
        p = " ".join(raw.split())
        if len(p) >= MIN_PARA:
            out.append(p)
    return out


def _terms(s: str) -> list[str]:
    """낱말 목록. 🔴 한글·CJK 는 **글자 2-그램**을 함께 센다(위 주석)."""
    low = str(s or "").lower()
    out = _WORD.findall(low)
    ch = _NGRAM.findall(low)
    out += ["".join(pair) for pair in zip(ch, ch[1:], strict=False)]
    return out


def top_paragraphs(text: str, query: str, *, n: int = BM25_POOL) -> list[str]:
    """🔴🔴 **질의와 가까운 문단만** 고른다(BM25).

    사용자 지시의 핵심이다 — *"팀·선수 이름이 나오는 문단만 골라 LLM 에 넘긴다.
    입력이 짧아야 8B 모델도 정확하다."*

    ⚠️ 문단이 `n` 개 이하면 **그대로 돌려준다**(고를 것이 없다).
    🔴 **순서를 본문 순서로 돌려준다** — 점수 순으로 주면 문맥이 끊기고, 모델이
       앞뒤가 뒤집힌 글에서 인용을 만들어 낸다.
    """
    paras = paragraphs(text)
    if len(paras) <= n:
        return paras
    q = [t for t in _terms(query) if len(t) > 1]
    if not q:
        return paras[:n]
    docs = [_terms(p) for p in paras]
    nd = len(docs)
    avg = sum(len(d) for d in docs) / nd
    # 🔴 문서 빈도 — 흔한 낱말의 무게를 낮춘다(그것이 BM25 의 요점이다)
    df: dict[str, int] = {}
    for d in docs:
        for w in set(d):
            df[w] = df.get(w, 0) + 1
    scored: list[tuple[float, int]] = []
    for i, d in enumerate(docs):
        tf: dict[str, int] = {}
        for w in d:
            tf[w] = tf.get(w, 0) + 1
        s = 0.0
        for w in q:
            f = tf.get(w, 0)
            if not f:
                continue
            idf = math.log(1 + (nd - df.get(w, 0) + 0.5) / (df.get(w, 0) + 0.5))
            s += idf * (f * (BM25_K1 + 1)) / (
                f + BM25_K1 * (1 - BM25_B + BM25_B * len(d) / avg))
        scored.append((s, i))
    best = sorted(scored, key=lambda x: (-x[0], x[1]))[:n]
    keep = sorted(i for s, i in best if s > 0)
    if not keep:
        # 🔴 **한 문단도 안 걸렸다** — 앞에서 자르는 것이 유일한 정직한 대안이다.
        #    ⚠️ 그 사실을 사유로 남기는 것은 호출부 몫이다(여기는 로그만).
        logger.info("[readtext] BM25 0점 — 질의 %r 가 어느 문단에도 없다", query[:60])
        return paras[:n]
    return [paras[i] for i in keep]


def read(html: str, *, url: str = "", query: str = "",
         n: int = BM25_POOL) -> tuple[str, str, str, int]:
    """🔴 한 번에: `(넘길 글, 발행일, 사유, 본문 전체 길이)`.

    `사유` 는 **무엇을 어떻게 줄였나**다 — 조용히 자르지 않는다(#3).
    ⚠️ 본문을 못 뽑으면 `("", "", 사유, 0)` 이고 호출부가 종전 경로로 간다.

    🔴 **본문 전체 길이를 함께 돌려준다** — 호출부가 *"페이지가 얄팍한가"* 를 그
       수로 판단해야 한다. ⚠️ 좁힌 글로 재면 **깨끗하고 충분한 글이 거부된다**
       (실측 2026-10-03: 271자·286자로 좁힌 글이 최소 400자 문턱에 걸렸다).
       그 수를 얻으려고 `extract` 를 두 번 부르면 큰 HTML 을 두 번 파싱한다.
    """
    text, when = extract(html, url=url)
    if not text:
        return "", "", "trafilatura 가 본문을 못 뽑았다", 0
    paras = paragraphs(text)
    if not query or len(paras) <= n:
        return text, when, (f"본문 {len(text)}자 · 문단 {len(paras)}개 — "
                            f"고르지 않고 전부 넘긴다"), len(text)
    top = top_paragraphs(text, query, n=n)
    joined = "\n".join(top)
    return joined, when, (
        f"본문 {len(text)}자 · 문단 {len(paras)}개 중 **질의와 가까운 {len(top)}개**"
        f"({len(joined)}자)만 넘긴다 — 입력이 짧아야 8B 가 정확하다"), len(text)
