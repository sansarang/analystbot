"""🔴🔴 **총평 검열**(사용자 지시 2026-10-07 §4) — 논평 생성 뒤, 카드 렌더 **전**.

> 두 겹으로 검사한다. **앞 겹은 코드, 뒤 겹은 다른 모델**이다. 작성자와 검열자를
> 같은 모델로 두지 않는다.

```
작성자  DeepSeek  (s8_comment.write)
검열자  Solar     (이 파일 · purpose="audit" · 출력 상한 600)
```

🔴 처리(§4-3): 위반 0 → 통과 · 위반 있음 → **재작성 1회** → 또 위반이면 **코드
   템플릿**. ⚠️ 사용자 카드(1겹)에는 **통과한 논평만** 나간다.
🔴 **검열을 통과시키려고 판정 수치·양상 문턱을 고치지 않는다**(지시 금지) — 유일한
   예외는 §4-1 (d) 가 말한 *"양상 근거 충돌 → shape 를 접전으로 낮춘다"* 이고,
   그것은 **문턱을 바꾸는 것이 아니라 그 경기의 판정을 내리는 것**이다.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.schema import (AuditOut, Commentary, CommentOut, Facts, HypoSet,
                             Judgement, MatchRef, Variable)
from app.core.state import RunState

logger = logging.getLogger(__name__)

#: 🔴 검열자 — **작성자와 달라야 한다**(§4-2). 계약이 그 둘을 비교한다.
AUDITOR = "solar"
WRITER = "deepseek"
#: 🔴 모델 검열이 위반으로 세는 판정(§4-2) — `overclaim` 은 **경고**다(로그만)
HARD = ("contradicts", "unsupported")



# ══════════════════════════════════════════════════════════════════
# 🔴 목록은 `layer1.SPECIFIC_KINDS` **하나**다(사본 금지 · #1)
# ⚠️ F7(2026-10-11)이 이 파일의 **글 쓰는 입구**(`run`)를 지웠다 — 남은 것은
#    검열·점수 **도우미**다. 그때 이 import 가 함께 잘려 되살렸다.
# ══════════════════════════════════════════════════════════════════
from app.core.layer1 import SPECIFIC_KINDS  # noqa: E402


# 🔴 F7 이 `run` 을 지울 때 함께 잘린 상수들(원본 그대로)
NEED_KINDS = 3


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **F7(2026-10-11) — 이 파일은 더 이상 글을 쓰지 않는다**
# ══════════════════════════════════════════════════════════════════
#
#  > 논평·이유 문단·전술 예측·최종 평 → **최종 평 한 번**(작성 1 + 검열 1).
#
#  🔴 그래서 `run`(LLM 작성 입구)을 **지웠다**. 남은 것은 검열·점수 **도우미**이고
#     `s9_say`·`layer1`·`render` 가 그것을 쓴다. 입구가 없으므로 아래에 적어 둔다.
STAGES = ("new_fact_check", "strategy_check", "reason_check", "h2h_direction_check", "top_scores", "score_drivers")


# 🔴 F7 삭제에 함께 잘린 상수들(원본 그대로)
H2H_EVEN_WORDS = ("대등", "비슷", "팽팽", "좁게", "좁은", "좁다", "호각",
                  "우열을 가리기", "격차가 좁", "크게 벌어지지", "밀리지 않")



_LATIN_NAME = __import__("re").compile(
    r"\b[A-Z][a-zA-ZÀ-ɏ'’\-]+(?:\s+[A-Z][a-zA-ZÀ-ɏ'’\-]+)+")


# 🔴 F7(2026-10-11) — `s8b_reason` 을 지우면서 **이 두 수를 여기로 옮겼다**
#    (사본이 아니라 이사다 — 쓰는 곳이 여기뿐이다).
#: 🔴 1겹 이유 문단의 문장 수(v6 §3)
MIN_SENT = 3
MAX_SENT = 5

def _nums(said: str) -> list[str]:
    """🔴 글에서 **숫자**를 뽑는다(§4-1 (f)) — 골·경기 수·%·날짜."""
    return re.findall(r"\d+(?:[.,]\d+)?", str(said or ""))



def top_scores(hypo: HypoSet | None, n: int = 3) -> list[tuple[str, float]]:
    """🔴🔴 **무게 상위 스코어 n개**(사용자 지시 2026-10-09(6차) ①) — 순서 그대로.

    > 예상 스코어: **재가중된 스코어 무게 상위 3개를 그대로 쓴다**(지금은 무게 1위
    > 갈래를 빼고 고른다).

    ⚠️ 실사고 2026-10-09(강원–부천): 무게 1위가 `C 1-2·0-1`(away 1.3525)인데 예상
       스코어가 `3-0 · 2-0 · 0-0` 이었다 — **1위 갈래가 빠졌다**(작성자가 골랐다).
    🔴 그래서 **코드가 고른다** — 작성자는 그 목록을 받아서 글만 쓴다.
    """
    box: dict[str, float] = {}
    for sc in (hypo.scenarios if hypo else []):
        pairs = list(sc.outcomes or [])
        if not pairs:
            continue
        share = float(sc.strength or 0.0) / len(pairs)
        for h, a in pairs:
            key = f"{h}-{a}"
            box[key] = box.get(key, 0.0) + share
    return sorted(box.items(), key=lambda kv: (-kv[1], kv[0]))[:max(0, int(n))]


def score_drivers(hypo: HypoSet | None, spot: str) -> list[str]:
    """🔴 그 스코어를 그린 갈래들의 **근거 변수 id**(지시 ① 마지막 줄).

    > `0-0` 이 들어가면 **근거 변수 id 를 옆에 적는다**.
    """
    out: list[str] = []
    for sc in (hypo.scenarios if hypo else []):
        if spot not in {f"{h}-{a}" for h, a in (sc.outcomes or [])}:
            continue
        # 🔴 칸 이름은 `driver_vars` 다(`drivers` 가 아니다 — 추측하면 조용히 빈다)
        for vid in (getattr(sc, "driver_vars", None) or []):
            if str(vid) not in out:
                out.append(str(vid))
    return out


def _top_spots(hypo: HypoSet | None, n: int) -> set[str]:
    """🔴 **스코어 무게 상위 n개** — 갈래 무게를 스코어 수로 나눠 센다."""
    box: dict[str, float] = {}
    for sc in (hypo.scenarios if hypo else []):
        pairs = list(sc.outcomes or [])
        if not pairs:
            continue
        share = float(sc.strength or 0.0) / len(pairs)
        for h, a in pairs:
            key = f"{h}-{a}"
            box[key] = box.get(key, 0.0) + share
    return {k for k, _v in sorted(box.items(), key=lambda kv: -kv[1])[:n]}





def _names_in(said: str) -> list[str]:
    """🔴 문장에서 **선수 이름일 수 있는 조각**을 뽑는다.

    ⚠️ 한글 이름은 조사가 붙어(`안톤이`) 글자만으로는 못 가른다 — 🔴 그래서
       라틴 문자 이름만 뽑고, 한글은 (l) 대신 (j)·(i) 가 사실 id 로 센다.
       그 한계를 여기 적어 둔다(#3 · 지어내지 않는다).
    """
    return [m.group(0).strip() for m in _LATIN_NAME.finditer(str(said or ""))]


def strategy_check(rows: list, *, card) -> list[str]:
    """🔴🔴 **(p) §4** — 전략 판정이 있으면 **이유 문단에 전략 문장 최소 1개**.

    > 헤드라인·이유 문단·예상 스코어·보드 판정은 **최종 확률로 다시 만든다**.
    > 이유 문단에 **전략 문장 최소 1개**(검열 항목 추가).
    > 계약: … **전략 문장이 최종 확률과 같은 방향**.

    🔴 두 가지를 센다:
      ① 전략 낱말(`공격 위주`·`수비 위주` …)이나 그 팀 이름+전략 뜻이 한 문장에 있나
      ② 그 문장이 **최종 확률의 방향과 같은 쪽**인가
         ⚠️ 방향은 `layer1.dir_side`(최종 확률을 보는 함수) 하나가 정한다.
    ⚠️ 전략 판정이 **`통과` 가 아니면 아무것도 세지 않는다**(없는 것을 쓰라고 할
       수는 없다 — 그 사실은 카드가 이미 적는다).
    """
    plan = getattr(card, "strategy", None)
    if str(getattr(plan, "audit", "") or "") != "통과":
        return []
    from app.core import layer1
    words = {str(getattr(x, "strategy", "")) for x in
             (getattr(plan, "lines", None) or [])} - {""}
    if not words:
        return []
    hit = [str(getattr(line, "text", "") or "") for line in (rows or [])
           if any(w in str(getattr(line, "text", "") or "") for w in words)]
    if not hit:
        return [f"(p) 전략 판정 {sorted(words)} 이 있는데 이유 문단이 **하나도 "
                f"안 썼다** — §4(이유 문단에 전략 문장 최소 1개)"]
    # 🔴 ② **최종 확률과 같은 방향**인가 — 반대 팀만 앞세우면 위반
    side = layer1.dir_side(card)
    if not side:
        return []
    who = (card.match.home_name if side == "home" else card.match.away_name)
    other = (card.match.away_name if side == "home" else card.match.home_name)
    for said in hit:
        if other in said and who not in said:
            return [f"(p) 전략 문장이 **최종 확률 방향({who})과 다른 쪽**만 "
                    f"말한다 — {said[:60]}"]
    return []


def new_fact_check(rows: list, *, card) -> list[str]:
    """🔴🔴 **(o) §3-5** — 새 사실이 있으면 **한 문장 이상**이 그것을 써야 한다.

    🔴 어떻게 세나: 새 사실 변수의 **id**(`R3`)가 그 문장의 `fact_refs` 에 있거나,
       그 변수의 **대상**(선수·팀 이름)이 문장 글자에 있으면 쓴 것으로 본다.
    ⚠️ `fact_refs` 만 보면 모델이 번호를 안 적었을 때 **멀쩡한 문장을 위반으로**
       센다(실측: 모델이 번호를 자주 빼먹는다). 🔴 그래서 글자도 본다.
    """
    from app.core import render
    got = render.new_facts(card)
    if not got:
        return []
    ids = {str(v.id) for v in got}
    words: set[str] = set()
    for v in got:
        for said in (str(v.target or ""), str(v.subject or "")):
            # ⚠️ `absence:손흥민` 처럼 **유형:대상** 꼴이다 — 뒤쪽만 쓴다
            one = said.split(":")[-1].strip()
            if len(one) >= 2:
                words.add(one)
    for line in (rows or []):
        if ids & {str(f) for f in (getattr(line, "fact_refs", None) or [])}:
            return []
        low = str(getattr(line, "text", "") or "")
        if any(w in low for w in words):
            return []
    return [f"(o) 새 사실 {len(got)}건이 있는데 이유 문단이 **하나도 안 썼다** — "
            f"§3-5(새 뉴스는 판단에 반드시 들어간다) · 새 사실 {sorted(ids)}"]


def reason_check(said, *, card) -> list[str]:
    """🔴🔴 **(i)~(l)** — 1겹 이유 문단의 코드 검열. 위반 목록(비면 통과).

    | 번호 | 무엇 |
    |---|---|
    | (i) | **구체성** — 이 경기 고유 사실이 **종류가 다른 셋** 이상 |
    | (j) | **범용 문장** — 문장마다 고유 사실이 하나 이상 |
    | (k) | **단정** — 단정어 금지 · 마지막 문장 방향 = 헤드라인 방향 |
    | (l) | **선수 사실** — 글에 나온 선수가 XI·결장·변수 대상에 있어야 한다 |
    """
    import re as _re

    from app.core import layer1
    if said is None or not getattr(said, "sentences", None):
        return ["(i) 이유 문단이 없다"]
    rows = list(said.sentences)
    bad: list[str] = []
    box = layer1.facts_catalog(card)
    # ── 문장 수(§3) — 3~5개
    if not (MIN_SENT <= len(rows) <= MAX_SENT):
        bad.append(f"(i) 문장이 {len(rows)}개다 — "
                   f"{MIN_SENT}~{MAX_SENT}개여야 한다")
    # ── (i) 구체성 — `fact_refs` 가 가리킨 사실의 **종류**를 센다
    kinds: set[str] = set()
    for line in rows:
        for fid in (line.fact_refs or []):
            kind = str((box.get(str(fid)) or {}).get("kind") or "")
            if kind in SPECIFIC_KINDS:
                kinds.add(kind)
    if len(kinds) < NEED_KINDS:
        bad.append(f"(i) 구체성 — 고유 사실 종류가 {sorted(kinds) or '없음'} "
                   f"({len(kinds)}종)뿐이다 · {NEED_KINDS}종 이상이어야 한다")
    # ── (j) 범용 문장 — 팀 이름 말고 고유 사실이 하나도 없으면 위반
    pool = layer1.player_pool(card)
    teams = {card.match.home_name, card.match.away_name}
    for line in rows:
        low = str(line.text or "")
        said_no_team = low
        for t in teams:
            said_no_team = said_no_team.replace(t, "")
        has_num = bool(_re.search(r"\d", said_no_team))
        has_player = any(nm and nm in low for nm in pool)
        has_ref = bool([f for f in (line.fact_refs or [])
                        if str(f) in box
                        and box[str(f)]["kind"] in SPECIFIC_KINDS])
        if not (has_num or has_player or has_ref):
            bad.append(f"(j) 범용 문장 — 이 경기 고유 사실이 없다: {low[:50]}")
    # ── (k) 단정어 · 마지막 문장 방향
    for line in rows:
        low = str(line.text or "")
        hit = [w for w in layer1.SURE_WORDS if w in low]
        if hit:
            bad.append(f"(k) 단정어 {hit[:2]} — {low[:40]}")
    side = layer1.dir_side(card)
    tail = str(rows[-1].text or "")
    if side:
        who = (card.match.home_name if side == "home"
               else card.match.away_name)
        other = (card.match.away_name if side == "home"
                 else card.match.home_name)
        # 🔴 **마지막 문장이 반대 팀만** 앞세우면 위반이다(방향이 어긋난다)
        if other in tail and who not in tail:
            bad.append(f"(k) 마지막 문장이 방향({who})과 다른 쪽을 말한다 — "
                       f"{tail[:50]}")
    elif not any(w in tail for w in ("어느 쪽도", "반반", "확신할 근거",
                                     "가리기 어렵", "단정할 수 없")):
        bad.append(f"(k) 방향이 **반반**인데 마지막 문장이 그 말을 안 한다 — "
                   f"{tail[:50]}")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **(n) `must_win` 은 조건을 만족했을 때만**(지시 2026-10-09(5차) ①)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > `must_win` 문장이 이유 문단에 들어가면 **그 조건을 만족했는지** 검열에서
    #  > 확인.
    #
    #  🔴 게이트가 닫혀 있으면(시즌 초) 그 글자는 **거짓**이다 — 실사고
    #     2026-10-09(가시마–감바 8라운드)에서 그 문장이 이유 문단에 들어갔다.
    look = dict(getattr(card, "outlook", None) or {})
    if not look.get("gate_open", True):
        for line in rows:
            low = str(line.text or "")
            hit = [w for w in ("must_win", "이겨야", "반드시 이겨", "승점이 급한",
                               "경우의 수") if w in low]
            if hit:
                bad.append(f"(n) 경우의 수 문장 — 게이트가 닫혔다"
                           f"({look.get('gate_why')})인데 {hit[:2]} 라고 적었다 — "
                           f"{low[:50]}")
    # ── (l) 선수 사실 — 사실 목록의 선수 id 로 대조한다
    known = {str(k)[2:] for k in box if str(k).startswith("P:")}
    known |= {str(k)[4:] for k in box if str(k).startswith("ABS:")}
    known |= pool
    for line in rows:
        for nm in _names_in(str(line.text or "")):
            if nm in teams:
                continue
            if not any(nm in k or k in nm for k in known if k):
                bad.append(f"(l) 선수 사실 — `{nm}` 은 XI·결장 명단·변수 대상에 "
                           f"없다(없는 선수 언급)")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **(o) 새 사실이 있으면 한 문장은 그것을 쓴다**(§3-5 · 2026-10-10)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 카드 이유 문단에 새 사실이 하나라도 있으면 **최소 한 문장은 새 사실을
    #  > 쓴다**(검열 항목 추가).
    #
    #  🔴 세는 규칙은 `render.new_facts` 하나다(사본 금지).
    #  ⚠️ 새 사실이 **0건이면 이 항목은 아무것도 세지 않는다** — 없는 것을
    #     쓰라고 할 수는 없다(그 0건은 §3-4 가 카드에 적는다).
    bad += new_fact_check(rows, card=card)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **(p) 전략이 있으면 이유 문단이 한 문장은 쓴다**(§4 · 2026-10-10 둘째)
    # ══════════════════════════════════════════════════════════════════
    bad += strategy_check(rows, card=card)
    return bad


def h2h_direction_check(got: Commentary, *, ref: MatchRef,
                        facts: Facts) -> list[str]:
    """🔴🔴 **(m) 맞대결 해석 방향**(사용자 지시 2026-10-09 ④).

    ⚠️ **번호가 (i) 에서 (m) 으로 바뀌었다** — 2026-10-09(3차) §4 가 (i)~(l) 을
       구체성·범용 문장·단정·선수 사실로 **못 박았다.** 🔴 번호는 사용자 지시가
       든다(그 글자로 사람이 말한다).

    > 총평 검열에 "맞대결 해석 방향" 검사 추가 — 한쪽 승이 다른 쪽의 **2배 이상**
    > 이면 "대등·좁다" 류 표현은 **위반**.

    🔴 왜 — 실측 2026-10-09(대전–전북): 맞대결이 대전 **1승 4무 5패**(상대 5승 =
       5배)인데 총평이 *"좀처럼 크게 벌어지지 않아 양 팀 간 격차가 좁게 유지돼
       왔다"* 고 적었다. ⚠️ 무승부가 많은 것과 **대등한 것**은 다르다 — 이기는
       쪽이 한쪽뿐이면 그 상성은 기울어 있다.
    ⚠️ 전적을 못 세면 **검사하지 않는다**(없는 것으로 위반을 만들지 않는다).
    """
    box = dict(facts.h2h or {})
    again = dict(box.get("recounted") or {})
    if again.get("n"):
        w, lose = int(again.get("w") or 0), int(again.get("l") or 0)
    else:
        said = box.get("summary")
        n = int(box.get("count") or 0)
        if not (isinstance(said, (list, tuple)) and len(said) == 3 and n
                and sum(int(x) for x in said) == n):
            return []
        w, lose = int(said[0]), int(said[2])
    hi, lo = max(w, lose), min(w, lose)
    # 🔴 **2배 이상**이 문턱이다. ⚠️ 적은 쪽이 0 이면(한쪽이 한 번도 못 이겼다)
    #    그것은 2배보다 더 기운 것이다 — 0 으로 나누지 않고 그 자리를 따로 센다.
    tilted = hi >= 2 * lo if lo else hi > 0
    if not tilted:
        return []
    lead = ref.home_name if w > lose else ref.away_name
    bad: list[str] = []
    for line in [*[x.text for x in got.reasons], got.flow, got.title]:
        said_line = str(line or "")
        hit = [x for x in H2H_EVEN_WORDS if x in said_line]
        if hit:
            bad.append(f"(m) 맞대결 해석 방향 — 전적이 {w}승 {lose}패로 "
                       f"**{lead} 쪽으로 기울었다**(한쪽이 다른 쪽의 "
                       f"{'∞' if not lo else f'{hi / lo:.1f}'}배)인데 문장이 "
                       f"{hit[:2]} 라고 적었다 — {said_line[:50]}")
    return bad
