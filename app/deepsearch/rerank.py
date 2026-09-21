"""[DS-5a] 재순위 — 질문과 **실제로 관련된 문단만** LLM 에 넣는다.

🔴 **왜.** 실측 2026-09-21 (운영 `game=Valencia CF`):
     기사 14건 · 본문 9,177자 → 창 6,000자(상한에 딱 걸림) → 프롬프트 7,101자
   그 6,000자 안에 이런 것이 들어 있었다:
     "'피카츄'가 등장한다. 참여 시설은 ▲영국 런던 과학박물관…"        1,200자
     "…경기후 이강인의 SNS에서도 레알 마드리드 팬들로 추정되는 악플…"  1,200자
   발렌시아–레알소시에다드 경기 입력의 **40%가 무관한 글**이다.
   추출이 0건인 것이 이상하지 않다.

🔴 **키워드를 여기서 만들지 않는다.** `config/evidence_lexicon.yaml` 이 원본이고
   `satellite._lexicon()` 이 이미 그것을 읽는다 — **그 함수를 부른다.**

⚠️ `satellite._windows`(팀 이름 ±300자)와 **역할이 다르다.** 그쪽은 자르고,
   이쪽은 **줄 세운다.** 합치지 않는다.
⚠️ (c) 재순위 모델은 **기본 꺼짐**이고 구현하지 않았다 — 지시문이 "(a)(b)만으로도
   동작해야 한다"고 못박았고, 채택은 사용자 승인 사항이다.
⚠️ LLM 은 여기서 부르지 않는다. 이 모듈은 **순수 함수**다.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.deepsearch.runtime import load_config

_SPLIT = re.compile(r"(?:\r?\n){1,}|(?<=[.。!?！？])\s+")
_WS = re.compile(r"\s+")


def _r(key, default=None):
    return ((load_config().get("rerank") or {}).get(key, default))


def model_enabled() -> bool:
    """(c) 소형 재순위 모델. 🔴 기본 꺼짐 — 켜려면 사용자 승인이다."""
    return bool((_r("model") or {}).get("enabled"))


@dataclass(frozen=True)
class Para:
    article_idx: int
    para_idx: int
    text: str
    url: str = ""
    title: str = ""
    score: float = 0.0


def _norm(s: str) -> str:
    return _WS.sub(" ", unicodedata.normalize("NFKC", str(s or ""))).strip()


def split(articles) -> list[Para]:
    """기사 → 문단. 🔴 **어느 기사 몇 번째 문단인지를 붙인다** —
    안 붙이면 LLM 인용이 어디서 왔는지 코드가 검증할 수 없다."""
    lo = int(_r("min_para_chars") or 40)
    out: list[Para] = []
    for ai, a in enumerate(articles or []):
        body = _norm(a.get("body") or "")
        if not body:
            continue
        pi = 0
        for chunk in _SPLIT.split(body):
            t = _norm(chunk)
            if len(t) < lo:
                continue
            out.append(Para(article_idx=ai, para_idx=pi, text=t,
                            url=a.get("url") or "", title=a.get("title") or ""))
            pi += 1
    return out


def _name_tokens(names) -> list[str]:
    """팀·선수 이름 조각.

    🔴 **잡토큰을 뺀다** — 원본은 `pipeline._GENERIC_TEAM_TOKENS` 이고
       `satellite._generic_tokens()` 가 이미 그것을 읽는다(사본 금지).
       안 빼면 `cf`·`de` 가 아무 데나 걸린다: 실측 2026-09-21 에
       `Valencia CF` 의 `cf` 가 **이강인(PSG) 기사**에 걸려 상위 k 를 채웠다.
       같은 실패를 `assign_side`(W2)가 이미 겪었다.
    ⚠️ 한 글자 토큰도 버린다.
    """
    from app.collectors.satellite import _generic_tokens

    gen = _generic_tokens()
    out = []
    for n in (names or []):
        for tok in re.split(r"[\s·,/]+", _norm(n)):
            tok = tok.strip(".").lower()
            if len(tok) >= 2 and tok not in gen:
                out.append(tok)
    return out


def score(para: Para, *, names=(), extra_terms=()) -> float:
    """(a) 키워드 사전 적중 **(게이트)** × (b) 이름 적중(순서).

    🔴 **증거 낱말이 없으면 0 이다.** 처음엔 이름 가중치를 더 줬는데
       (`2*이름 + 1*사전`) 실측에서 상위 6개가 전부 **경기 사진 캡션**이
       됐다(실측 2026-09-21):
         `epa13253162 Real Sociedad's Ander Barrenetxea (C) celebrates …`  8.0
         `epa13253084 Valencia's Aaron Mayol (L) celebrates after scoring…` 6.0
       팀 이름만 많은 글이 이긴다. 정작 부상자 표(`Muscle injury · 복귀 예정`)는
       밀렸다. **팀 이름은 증거가 아니라 대상이다.**
    ⚠️ 제목도 함께 본다 — Transfermarkt 부상표는 `부상자 7명` 이 **제목에만**
       있고 본문은 선수 목록이다(실측). 제목을 안 보면 그 기사가 증거임을
       모른다.
    """
    from app.collectors.satellite import _lexicon

    t = para.text
    hay = f"{t} {para.title or ''}"
    low = f"{t} {para.title or ''}".lower()
    a = sum(1 for w in _lexicon() if w and w in hay)
    c = sum(1 for w in (extra_terms or []) if w and str(w) in hay)
    if a == 0 and c == 0:
        return 0.0                 # 🔴 게이트 1 — 증거 낱말이 없으면 증거가 아니다
    b = sum(1 for tok in _name_tokens(names) if tok in low)
    if names and b == 0:
        # 🔴 게이트 2 — **이 경기 팀을 언급해야 이 경기 증거다.**
        #    실측 2026-09-21: 99문단 중 게이트 1 통과가 36개인데 그중 이 경기
        #    팀을 언급한 것은 **2개**였다. k=6 으로 채우면 나머지 4자리를
        #    피카츄·이강인(PSG) 기사가 가져간다. **모자란 채로 돌려주는 것이
        #    맞다** — 없는 증거를 자리 채우기로 만들지 않는다.
        return 0.0
    return 3.0 * a + 2.0 * c + 1.0 * b


def top_k(paras, *, names=(), extra_terms=(), k=None) -> list[Para]:
    """관련도 상위 k 문단. **점수 0 은 넣지 않는다.**

    🔴 점수 0 을 채워 넣으면 피카츄 기사가 자리를 다시 차지한다 —
       그게 이 모듈을 만든 이유다. 모자라면 **모자란 채로** 돌려준다.
    ⚠️ 동점이면 기사 순서·문단 순서를 지킨다(재현성).
    """
    kk = int(k if k is not None else (_r("k") or 6))
    scored = [Para(p.article_idx, p.para_idx, p.text, p.url, p.title,
                   score(p, names=names, extra_terms=extra_terms))
              for p in paras or []]
    scored = [p for p in scored if p.score > 0]
    scored.sort(key=lambda p: (-p.score, p.article_idx, p.para_idx))
    return scored[:kk]


def locate_quote(quote: str, paras):
    """이 인용이 **어느 문단에서 왔나.** 없으면 None.

    🔴 지어낸 인용을 잡는 장치다 — LLM 이 그럴듯한 문장을 만들어 오면
       여기서 None 이 나오고, 호출부가 그 사실을 버린다.
    ⚠️ 공백·전각/반각만 정규화한다. 그 이상 느슨하게 하면 지어낸 것도 통과한다.
    """
    q = _norm(quote)
    if not q:
        return None
    for p in paras or []:
        if q in p.text:
            return p
    return None
