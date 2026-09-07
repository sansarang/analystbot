"""[감시 L1] 사실 감시 — 판정이 인용한 수치가 **원문 자료에 실재하는가.**

🔴 **판정을 건드리지 않는다.** 판정 JSON 이 캐시에 저장된 **뒤에** 읽는다.
   결과는 `judgement_audit` 에만 쌓이고 판정·게이트·카드로 되돌아가지 않는다 —
   되먹이는 순간 감시가 아니라 입력이 된다.

⚠️ **오탐이 이 층의 최대 리스크다.** 그래서 추출을 좁게 잡았다:
   · 근거1~3·변수1~2 **텍스트만** 본다. 카드 헤더(p·별점·필요배당)는 모델
     산출물이지 인용이 아니다.
   · **단위가 붙은 수치만** 뽑는다. 맨숫자·날짜·"2경기" 같은 배수·백분율은
     제외한다 — 그것들은 원문에 없어도 정상이다.
   · 판정을 4분류한다:
       verified          원문에 같은 값이 있다
       verified(derived) 평균 등 계산값을 원본 배열에서 재계산해 맞았다
       not_found         원문에 그 단위 수치가 아예 없다 (환각 **후보**, 확정 아님)
       mismatch          같은 단위 수치가 원문에 있는데 값이 다르다  ← 이것만 경보
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

#: 인용 대상 필드. 헤더는 보지 않는다.
CLAIM_FIELDS = ("근거", "변수")

#: 단위 사전 — `(정규식, 단위키, 원문에서 찾을 키들)`.
#  🔴 여기 없는 패턴은 **추출하지 않는다.** 넓히면 오탐이 는다.
#: 🔴 [v1.4 2026-09-07] **자료12(실력 레이팅)도 감시 대상이다.**
#   자료12 는 판정의 **기본 축**인데 L1 이 대조하지 않았다 — 실측:
#   맞는 인용과 틀린 인용(홈 1590/원정 1410)이 **둘 다** verified 0 ·
#   mismatch 0 으로 나왔다. 단위 없는 숫자는 애초에 후보에 안 들어갔다.
#   ⚠️ 레이팅은 1000~1999 구간이라 이닝·실점(한 자리~두 자리)과 겹치지
#      않는다. 그래서 값 범위 자체가 단위 노릇을 한다.
UNIT_PATTERNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # ⚠️ [자료10 2026-09-04] 분위수·최장·회귀 참조 키를 함께 본다. 이 값들이
    #    빠지면 자료10 을 인용한 변수가 통째로 `not_found` 로 찍힌다 —
    #    실측: `"p50": 1.2` 가 프롬프트에 있는데 L1 이 ip 값을 0개로 읽었다.
    (r"(\d+(?:\.\d+)?)\s*이닝", "ip",
     ("innings", "starter_ip", "이닝", "최장", "p25", "p50", "p75",
      "다음등판_평균이닝")),
    # ⚠️ [2026-09-05] `실점`·`경기당실점` 은 **자료9(불펜)의 실제 키**다.
    #    목록에 없어 불펜 실점이 감시에 통째로 안 보였다 — 실판정 20건에
    #    걸어보고 알았다(불펜 블록의 숫자 키를 세어 확인).
    (r"(\d+(?:\.\d+)?)\s*실점", "r",
     ("r", "starter_r", "opp_runs", "runs_allowed_l3", "다음등판_평균실점",
      "실점", "경기당실점")),
    (r"(\d+(?:\.\d+)?)\s*자책", "er", ("er", "자책")),
    # [자료12] 레이팅 — 1000~1999 만 잡는다(1500 이 리그 평균).
    (r"\b(1\d{3}(?:\.\d+)?)\b", "elo", ("레이팅",)),
    # [자료12] 격차 — 부호가 붙을 수 있다. `−`(U+2212)도 받는다.
    (r"격차\s*[:은는]?\s*([+\-\u2212]?\d+(?:\.\d+)?)", "elo_gap", ("격차",)),
    (r"리그\s*평균\s*(?:대비)?\s*([+\-\u2212]?\d+(?:\.\d+)?)", "elo_rel",
     ("리그평균대비",)),
    (r"ERA\s*(?:환산\s*)?(?:약\s*)?(\d+(?:\.\d+)?)", "era", ("ERA", "era")),
    (r"WHIP\s*(\d+(?:\.\d+)?)", "whip", ("WHIP", "whip")),
    (r"(?:가중)?OPS\s*(\d+(?:\.\d+)?)", "ops", ("OPS", "가중OPS")),
    (r"(\d+(?:\.\d+)?)\s*득점", "runs", ("runs", "runs_l3", "runs_per_game_l3")),
    (r"(\d+(?:\.\d+)?)\s*안타", "hits", ("hits", "H")),
    (r"(\d+(?:\.\d+)?)\s*홈런", "hr", ("hr", "HR")),
    (r"(\d+(?:\.\d+)?)\s*볼넷", "bb", ("bb", "BB", "四球")),
    (r"(\d+(?:\.\d+)?)\s*삼진", "so", ("k", "K", "SO", "三振")),
)

#: 계산값 표현 — 이 말이 붙으면 원본 배열에서 재계산해 본다.
#  🔴 [2026-09-03] **합계 표현이 빠져 있었다.** "최근 4경기 27이닝" 의 27 은
#     합계인데, 마커가 없어 `derived=False` 로 분류돼 곧장 근사 비교를 탔고
#     원문의 경기별 이닝(≈8)과 19이닝 차이로 **환각(mismatch)** 이 됐다.
#     판정은 옳았고 감시가 틀렸다 (리허설 실측 2026-09-03, NPB 2건).
DERIVED_MARKERS = ("평균", "경기당", "/경기", "환산", "합계", "총", "도합")

#: 야구 이닝 표기 — `.1` = ⅓(1아웃), `.2` = ⅔(2아웃).
#  🔴 [2026-09-05] 원문 이닝은 `kbo_usage.parse_innings` 가 만든 **소수**다
#     (5⅔ → 5.667). 판정은 같은 이닝을 **야구 표기**(5.2)로 적는다. 숫자만
#     비교하면 5.2 ≠ 5.667 이라 **정확한 인용이 환각으로 찍힌다.**
#     실측 2026-09-05: `5.2이닝`·`6.1이닝`(원문과 동일한 값) 둘 다 mismatch,
#     game=1711 경보가 이것이었다.
_IP_NOTATION = {1: 1.0 / 3.0, 2: 2.0 / 3.0}

#: 자릿수 해석의 상한. 정수 인용("6이닝")이 6.9 를 덮지 않게 막는다.
_WRITTEN_MAX_GAP = 0.1


def readings(value: float, unit: str) -> list[float]:
    """이 인용이 가리킬 수 있는 값들. 이닝만 표기법 해석을 덧붙인다."""
    out = [round(value, 3)]
    if unit == "ip":
        whole = int(value)
        tenth = round((value - whole) * 10)
        if abs((value - whole) - tenth / 10.0) < 1e-9 and tenth in _IP_NOTATION:
            out.append(round(whole + _IP_NOTATION[tenth], 3))
    return out


def written_at(claimed: float, source: float) -> bool:
    """원문을 **인용이 쓴 자릿수로** 줄이면 같아지는가.

    쓰지 않은 자릿수를 요구할 수 없다 — 5.667 을 "5.6" 으로 적은 것은 절사이지
    오류가 아니다. 종전 tolerance(0.05)는 1자리 절사 최대오차(0.0999)보다
    작아 정상 인용을 걸렀다.
    """
    if abs(claimed - source) >= _WRITTEN_MAX_GAP:
        return False
    txt = f"{claimed:.6f}".rstrip("0")
    d = len(txt.split(".")[1]) if "." in txt else 0
    f = 10 ** d
    return (abs(int(source * f) / f - claimed) < 1e-9
            or abs(round(source * f) / f - claimed) < 1e-9)


def same_number(claimed: float, source: float, unit: str, tol: float) -> bool:
    """인용과 원문이 **같은 수를 가리키는가.** 표기법·자릿수를 함께 본다."""
    return any(abs(r - source) <= tol or written_at(r, source)
               for r in readings(claimed, unit))


#: "최근 4경기" · "3등판" — 표본 크기를 명시한 표현.
#  ⚠️ [2026-09-05] `선발` 이 빠져 있었다. "최근 3선발 21이닝 3실점 26삼진" 은
#     3등판 **합계**인데 표본수를 못 읽어 재계산을 못 했고, 합계가 개별 등판
#     이닝과 대조돼 환각으로 찍혔다 (실측 game=2882, 2건).
SAMPLE_N_RE = re.compile(r"(\d+)\s*(?:경기|등판|선발)")

#: 🔴 (c) [2026-09-05] **비율의 분모는 값이 아니다.**
#   "5.0이닝 2.4실점·9이닝 4.4볼넷" 의 `9이닝` 은 BB/9 의 분모이지 "9이닝을
#   던졌다"는 주장이 아니다. 감시가 그것을 이닝 주장으로 읽어 원문의 11.0 과
#   대조했다 (실측 game=1714, `ip 주장 9.0 vs 원문 11.0`).
#   ⚠️ 좁게 잡는다 — **정확히 9이닝**이고 **바로 뒤에 다른 지표가 붙을 때만**
#      분모로 본다. 그래서 완투(9이닝 1실점)도 걸러지지만, 감시는 놓치는 쪽이
#      틀리는 쪽보다 낫다.
_RATE_DENOM = re.compile(r"^\s*\d+(?:\.\d+)?\s*(?:실점|자책|볼넷|삼진|안타|홈런)")

#: 🔴 [2026-09-05] **전망은 인용이 아니다.** "홈 불펜 6이닝↑ 소화 부담" 의 6 은
#   "6이닝을 던졌다"가 아니라 "6이닝 이상 던져야 할 수도 있다"는 예상이다.
#   원문에 없는 것이 당연하다 — 감시가 이것을 환각으로 찍었다(실측 game=2888).
#   ⚠️ **화살표·부호만** 본다. `미만`·`이상` 까지 넣었더니 변수의 조건
#      ("원정 선발 3이닝 미만 조기 강판 … 근거 자료10 최장 3.0이닝")에서
#      3이닝이 빠져 자료10 검증이 깨졌다 — 기존 계약 테스트가 잡았다.
#      그 값은 자료10 에 실재하므로 검증 대상이 맞다. 측정한 것만 넣는다.
#   ⚠️ [2026-09-06] "꾸준히 6이닝 이상을 책임져온" 같은 **서술형 문턱**은
#      여전히 새어 들어온다(실측 game=1716). 값이 원문에 있으면 검증되고
#      없으면 `not_found` 가 되므로 **경보로는 가지 않는다** — mismatch 는
#      "같은 단위 값이 원문에 있는데 다를 때"만이다. 그 구분에 기댄다.
_THRESHOLD = re.compile(r"^\s*(?:↑|↓|\+)")


def is_rate_denominator(text: str, value: float, end: int) -> bool:
    return abs(value - 9.0) < 1e-9 and bool(_RATE_DENOM.match(text[end:]))


def is_threshold(text: str, end: int) -> bool:
    """관측치가 아니라 문턱·전망을 가리키는 수인가."""
    return bool(_THRESHOLD.match(text[end:]))


#: 🔴 [2026-09-06] **자료 번호는 값이 아니다.**
#   "근거 자료10 이닝분포 p25" 의 `10` 이 `(\d+)\s*이닝` 에 걸려 "10이닝"으로
#   읽혔다. 자료10 의 이름이 하필 "이닝분포"라서, **자료10 을 인용하는 변수는
#   전부 이 오탐이 난다** — 그래서 같은 경보가 반복됐다
#   (실측 game=1716: ip 주장 10.0 vs 원문 12.0).
_MATERIAL_REF = re.compile(r"자료\s*$")


def is_material_ref(text: str, start: int) -> bool:
    """이 숫자가 `자료N` 의 번호인가. 앞이 "자료"면 값이 아니다."""
    return bool(_MATERIAL_REF.search(text[:start]))


#: 🔴 (b) [2026-09-05] **선발과 불펜을 한 풀에 섞지 않는다.**
#   프롬프트는 자료를 번호로 나눈다 — `4.` 선발 최근 등판, `9.` 불펜 최근 폼.
#   종전에는 둘의 이닝·실점이 같은 단위 키로 수집돼 **서로 대조됐다**:
#   "원정 불펜 최근 3경기 0.67실점/11이닝(자료9)" 의 11이닝이 자료4 의 선발
#   이닝과 비교됐다 (실측 game=1712 `ip 주장 5.8 vs 원문 6.0`, game=3203).
_BULLPEN_NO = 9
#: ⚠️ **`구원` 은 불펜 단서가 아니다.** 구원 등판 기록은 자료4(`구원등판`)와
#   자료10(이닝분포)에 있다 — 오늘 선발이 최근에 구원으로 나왔다는 뜻이기
#   때문이다. 단서로 넣었더니 "구원 3경기 p50 2.0이닝(근거 10)" 같은 자료10
#   인용이 자료9 에서 검색돼 오탐 4건이 새로 생겼다(실판정 20건 실측).
_BULLPEN_WORDS = ("불펜", "자료9")


def material_block(prompt: str, n: int) -> str:
    """프롬프트의 `N. …` 자료 블록. 못 찾으면 빈 문자열 — 추측하지 않는다."""
    m = re.search(rf"(?m)^{n}\.\s", prompt)
    if not m:
        return ""
    tail = prompt[m.end():]
    nxt = re.search(r"(?m)^\d+\.\s", tail)
    return tail[: nxt.start()] if nxt else tail


#: 선발 쪽 단서. 불펜 단서와 **가까운 쪽**이 이긴다.
_STARTER_WORDS = ("선발", "등판", "자료4")


def claim_scope(text: str, at: int) -> str | None:
    """이 **숫자**가 어느 자료 얘기인가. 모르면 None — 범위를 좁히지 않는다.

    🔴 [2026-09-05] 종전에는 **줄 단위**로 판단했다. 그런데 한 근거 줄에는
       선발과 불펜 숫자가 섞여 있다:
         "선발 이닝 소화력(5.8이닝) … 불펜은 원정 우위"
       줄에 "불펜"이 한 번 나왔다고 그 줄의 모든 숫자를 불펜 블록에서만
       찾으면, 선발 숫자가 통째로 `not_found` 가 된다.
       실측: 실판정 20건에 걸어보니 검증 184건 → 137건, 불일치 3건 → 12건으로
       **오히려 나빠졌다.** 그래서 `claim_subject` 와 같은 방식으로 —
       **그 숫자 바로 앞의 가장 가까운 단서**로 가른다.
    """
    best, kind = -1, None
    for words, label in ((_BULLPEN_WORDS, "bullpen"), (_STARTER_WORDS, "starter")):
        for w in words:
            i = text.rfind(w, 0, at)
            if i > best:
                best, kind = i, label
    return kind


def scope_text(prompt: str, scope: str | None) -> str:
    """그 자료의 원문. 불펜만 좁힌다.

    ⚠️ 선발·불명은 **좁히지 않는다.** 좁히면 못 찾는 값이 늘어 오탐이 된다.
       감시는 놓치는 쪽이 틀리는 쪽보다 낫다 — 이 층의 최대 리스크는 오탐이다.
    """
    if scope != "bullpen":
        return prompt
    return material_block(prompt, _BULLPEN_NO) or prompt


#: 주체 귀속 — 이 말이 있으면 그쪽 진영의 배열만 본다.
SUBJECT_WORDS = {"home": ("home", "홈", "홈팀"), "away": ("away", "원정", "원정팀")}


def claim_subject(text: str, at: int | None = None,
                  names: dict[str, str] | None = None) -> str | None:
    """이 인용이 누구 것인가. **모르면 None** — 추측해서 재계산하지 않는다.

    🔴 [2026-09-04] 종전에는 문장에 진영 단어가 **둘 다** 있으면 무조건 None
       이었다. 그런데 근거는 거의 항상 비교문이다:
         "홈 선발(원태인) 최근5경기 31.1이닝 … vs 원정 선발(비슬리) 29.2이닝"
       그래서 주체가 영영 안 붙었고, 재계산을 건너뛰어 **derived 가 7경기 내내
       0건**이었다(실측 2026-09-03). not_found 34% 의 실체가 이것이다.

    이제 `at`(그 수치가 문장에서 나온 위치)이 오면 **가장 가까운 앞쪽 단서**로
    가른다. 사람이 읽는 방식과 같다 — "홈 …31.1이닝"의 31.1 은 홈 것이다.
    ⚠️ 단서가 앞에 하나도 없으면 여전히 None 이다. 뒤쪽 단서로 넘겨짚지 않는다.
    """
    cues: list[tuple[int, str]] = []
    for side, words in SUBJECT_WORDS.items():
        for w in words:
            start = 0
            while (i := text.find(w, start)) >= 0:
                cues.append((i, side))
                start = i + 1
    for name, side in (names or {}).items():
        if not name:
            continue
        start = 0
        while (i := text.find(name, start)) >= 0:
            cues.append((i, side))
            start = i + 1
    if not cues:
        return None
    if at is None:
        sides = {sd for _, sd in cues}
        return next(iter(sides)) if len(sides) == 1 else None
    before = [(i, sd) for i, sd in cues if i <= at]
    if not before:
        return None
    return max(before, key=lambda x: x[0])[1]


def sample_n(text: str) -> int | None:
    """"최근 N경기" 의 N. 여러 개면 **가장 앞의 것** (그 문장의 주 표본)."""
    m = SAMPLE_N_RE.search(text)
    return int(m.group(1)) if m else None


def _region(prompt: str, side: str) -> str:
    """프롬프트에서 그 진영 블록들만 이어 붙인다. 중괄호 균형으로 자른다.

    ⚠️ 원문은 JSON 이 섞인 텍스트다. `"home": {...}` 을 만나면 짝이 맞는
       닫는 괄호까지가 그 진영의 몫이다. 못 자르면 **빈 문자열**을 준다 —
       엉뚱한 범위로 재계산하느니 재계산을 포기한다.
    """
    out = []
    for m in re.finditer(rf'"{side}"\s*:\s*(\{{|\[)', prompt):
        i = m.end() - 1
        depth, opens = 0, {"{": "}", "[": "]"}
        close = opens[prompt[i]]
        for j in range(i, min(len(prompt), i + 20000)):
            if prompt[j] in "{[":
                depth += 1
            elif prompt[j] in "}]":
                depth -= 1
                if depth == 0:
                    out.append(prompt[i:j + 1])
                    break
    return "\n".join(out)


def extract_claims(verdict: dict, names: dict[str, str] | None = None) -> list[dict]:
    """판정 JSON → [{text, unit, value, …}]. 단위 없는 수치는 뽑지 않는다.

    `names`: 선수명 → 진영. 있으면 "곽빈 … 6.4이닝"처럼 **이름만 나오는**
    문장도 주체를 붙일 수 있다.
    """
    out: list[dict] = []
    for field in CLAIM_FIELDS:
        for line in verdict.get(field) or []:
            s = str(line)
            for pat, unit, _keys in UNIT_PATTERNS:
                for m in re.finditer(pat, s):
                    try:
                        val = float(m.group(1))
                    except (TypeError, ValueError):
                        continue
                    if unit == "ip" and is_rate_denominator(s, val, m.end()):
                        continue
                    if is_threshold(s, m.end()):
                        continue
                    if is_material_ref(s, m.start()):
                        continue
                    out.append({"text": s[:200], "unit": unit, "value": val,
                                "derived": any(k in s for k in DERIVED_MARKERS),
                                "subject": claim_subject(s, m.start(), names),
                                "scope": claim_scope(s, m.start()),
                                "n": sample_n(s)})
    return out


def numbers_in_prompt(prompt: str, unit: str) -> set[float]:
    """프롬프트 원문에서 그 단위에 해당하는 값들을 모은다.

    ⚠️ 원문은 JSON 이 섞인 텍스트다. 키 이름 옆의 숫자와, 사람이 읽는
       표기(`5.13이닝`) 둘 다 잡는다.
    """
    keys = next((k for p, u, k in UNIT_PATTERNS if u == unit), ())
    found: set[float] = set()
    for key in keys:
        for m in re.finditer(rf'"{re.escape(key)}"\s*:\s*"?(-?\d+(?:\.\d+)?)',
                             prompt):
            try:
                found.add(round(float(m.group(1)), 3))
            except ValueError:
                continue
        # ⚠️ 배열 값도 값이다 — `"이닝": [1.0, 2.0, 1.2]` (자료10 이닝 분포).
        for m in re.finditer(rf'"{re.escape(key)}"\s*:\s*\[([^\]]*)\]', prompt):
            for tok in re.finditer(r"-?\d+(?:\.\d+)?", m.group(1)):
                try:
                    found.add(round(float(tok.group(0)), 3))
                except ValueError:
                    continue
    for pat, u, _ in UNIT_PATTERNS:
        if u != unit:
            continue
        for m in re.finditer(pat, prompt):
            try:
                found.add(round(float(m.group(1)), 3))
            except ValueError:
                continue
    return found


def values_in(text: str, unit: str) -> list[float]:
    """그 단위의 값들을 **순서·중복 그대로** 모은다.

    🔴 종전 `numbers_in_prompt` 는 `set` 이었다. 합계를 검증하려면 같은 값이
       두 번 나온 것도 두 번 세야 한다 — 집합으로는 합을 복원할 수 없다.
    """
    keys = next((k for p, u, k in UNIT_PATTERNS if u == unit), ())
    found: list[float] = []
    for key in keys:
        for m in re.finditer(rf'"{re.escape(key)}"\s*:\s*"?(-?\d+(?:\.\d+)?)', text):
            try:
                found.append(round(float(m.group(1)), 3))
            except ValueError:
                continue
        for m in re.finditer(rf'"{re.escape(key)}"\s*:\s*\[([^\]]*)\]', text):
            for tok in re.finditer(r"-?\d+(?:\.\d+)?", m.group(1)):
                try:
                    found.append(round(float(tok.group(0)), 3))
                except ValueError:
                    continue
    for pat, u, _ in UNIT_PATTERNS:
        if u != unit:
            continue
        for m in re.finditer(pat, text):
            try:
                found.append(round(float(m.group(1)), 3))
            except ValueError:
                continue
    return found


def _recompute_hits(val: float, vals: list[float], n: int | None,
                    tolerance: float) -> bool:
    """합·평균을 **명시된 표본 크기**로 맞춰 본다.

    ⚠️ 순서를 모르므로 앞 N개와 뒤 N개 둘 다 본다. 그래도 안 맞으면
       **포기한다** — 조합을 뒤지면 우연히 맞는 값이 나와 검증이 무의미해진다.
    """
    if not vals:
        return False
    cands = [vals]
    if n and 0 < n <= len(vals):
        cands += [vals[:n], vals[-n:]]
    for c in cands:
        if not c:
            continue
        if abs(val - sum(c)) <= tolerance * len(c):
            return True
        if abs(val - sum(c) / len(c)) <= tolerance:
            return True
    return False


#: 🔴 (a) [2026-09-05] **판정이 한 정확한 산수를 감시가 못 따라갔다.**
#   근거에 "최근3경기 8.0이닝 6실점 ERA 6.75" 라고 썼다. 6×9÷8 = 6.75 로
#   **판정이 맞다.** 그런데 원문에 그 ERA 가 없으니 감시가 환각으로 찍었다
#   (실측 game=1713, `era 주장 6.75 vs 원문 15.0` — 2건).
#   ERA 는 이닝과 실점에서 나오는 값이다. 같은 문장에 재료가 있으면 계산해
#   본다 — 원문에 그 숫자가 없다는 것은 환각의 증거가 아니다.
def era_recomputed(text: str, claimed: float, tolerance: float) -> bool:
    """같은 문장의 (이닝, 실점) 조합으로 ERA 를 복원할 수 있는가."""
    ips = [float(m.group(1)) for m in re.finditer(UNIT_PATTERNS[0][0], text)]
    rs = [float(m.group(1)) for m in re.finditer(UNIT_PATTERNS[1][0], text)]
    rs += [float(m.group(1)) for m in re.finditer(UNIT_PATTERNS[2][0], text)]
    for ip in ips:
        for r in rs:
            for reading in readings(ip, "ip"):
                if reading <= 0:
                    continue
                if abs(r * 9.0 / reading - claimed) <= tolerance:
                    return True
    return False


def classify(claim: dict, prompt: str, tolerance: float) -> tuple[str, dict | None]:
    """한 인용의 판정. 반환 (verified|derived|not_found|mismatch, 상세|None).

    🔴 **`mismatch` 의 정의를 좁게 박는다** (2026-09-03):
       *동일 주체·동일 단위·동일 표본*의 값이 원문과 다를 때만 불일치다.
       주체를 모르거나(어느 팀 얘기인지 불명) 재계산이 안 맞으면 **`not_found`**
       다 — "틀렸다"가 아니라 "검증 못 했다"는 뜻이다.
       리허설 실측: 이 구분이 없어 합계 인용 2건이 환각으로 찍혔다.

    ⚠️ 그래서 `not_found` 는 **환각률이 아니라 검증 불가율**이다. 보고서에서
       그렇게 읽어야 한다.
    """
    unit = claim["unit"]
    val = round(float(claim["value"]), 3)
    # (b) 이 **숫자**가 불펜 얘기면 자료9 안에서만 찾는다.
    prompt = scope_text(prompt, claim.get("scope"))
    pool = numbers_in_prompt(prompt, unit)
    if any(same_number(val, x, unit, tolerance) for x in pool):
        return "verified", None
    # (a) ERA 는 이닝·실점에서 나온다. 같은 문장에 재료가 있으면 복원해 본다.
    if unit == "era" and era_recomputed(claim.get("text") or "", val, tolerance):
        return "derived", None
    if not pool:
        return "not_found", None

    # 주체가 특정되면 **그 진영의 배열만** 본다.
    # ⚠️ 모호함은 진영이 **둘 다 있을 때만** 생긴다. 원문에 진영 구조가 아예
    #    없으면(단편 자료) 헷갈릴 대상이 없으므로 전체를 쓴다.
    side = claim.get("subject")
    homes, aways = _region(prompt, "home"), _region(prompt, "away")
    structured = bool(homes or aways)
    if side and structured:
        vals = values_in(_region(prompt, side), unit)
    elif not structured:
        vals = values_in(prompt, unit)
    else:
        vals = []                          # 진영은 있는데 어느 쪽인지 모른다

    if claim.get("derived"):
        if vals and any(_recompute_hits(r, vals, claim.get("n"), tolerance)
                        for r in readings(val, unit)):
            return "derived", None
        # 주체 불명이거나 재계산 실패 → **추측하지 않는다.**
        return "not_found", None

    if not vals:
        # 재계산은 못 해도 **직접 인용**은 전체 풀로 대조할 수 있다.
        # 값 하나를 그대로 적은 것이라 부분집합 모호성이 없다.
        vals = values_in(prompt, unit)
    if not vals:
        return "not_found", None
    near = min(vals, key=lambda x: min(abs(x - r)
                                      for r in readings(val, unit)))
    if same_number(val, near, unit, tolerance):
        return "verified", None
    # 합계로 읽으면 맞는 경우가 있다 — 마커가 없어도 한 번 봐준다.
    if any(_recompute_hits(r, vals, claim.get("n"), tolerance)
           for r in readings(val, unit)):
        return "derived", None
    return "mismatch", {"claim": claim["text"], "unit": unit,
                        "claimed": val, "nearest_in_source": near,
                        "subject": side, "sample_n": claim.get("n")}


def audit(verdict: dict, prompt: str, *, tolerance: float | None = None,
          names: dict[str, str] | None = None) -> dict:
    """판정 1건 감사. 순수 함수 — I/O 없음.

    `names`: 선발 이름 → 진영. 넘기면 이름만 나오는 인용도 주체가 붙는다.
    """
    from app.config import get_settings

    tol = tolerance if tolerance is not None else get_settings().fact_audit_tolerance
    out = {"verified_n": 0, "derived_n": 0, "not_found_n": 0,
           "mismatch_n": 0, "mismatch_detail": []}
    for c in extract_claims(verdict, names):
        kind, detail = classify(c, prompt, tol)
        out[f"{kind}_n"] += 1
        if detail:
            out["mismatch_detail"].append(detail)
    return out


PROMPT_KEY = "judge_prompt:{game_id}"


async def load_prompt(redis, game_id) -> str | None:
    """판정 **시점의** 프롬프트. 재렌더하지 않는다 — 그 사이 재료가 바뀐다."""
    if redis is None:
        return None
    try:
        return await redis.get(PROMPT_KEY.format(game_id=game_id))
    except Exception as exc:
        logger.debug("[fact-audit] 프롬프트 조회 실패 game=%s: %s", game_id, exc)
        return None


async def run(pool, redis, jg: dict) -> dict | None:
    """훅 진입점. **어떤 예외도 밖으로 던지지 않는다** (P4).

    실패는 조용히 삼키지 않는다 — `W-MONITOR-DOWN` 한 줄 + skip 기록.
    """
    from app.config import get_settings

    if not get_settings().fact_audit_enabled:
        return None
    gid = jg.get("game_id")
    try:
        verdict = jg.get("matchup") or {}
        if not verdict.get("근거"):
            return None
        prompt = await load_prompt(redis, gid)
        if not prompt:
            logger.info("[fact-audit] game=%s 프롬프트 원문 없음 — skip", gid)
            return None
        # 선발 이름 → 진영. "곽빈 … 6.4이닝" 처럼 **이름만 나오는** 인용도
        #   주체가 붙어야 재계산할 수 있다.
        names = {}
        try:
            from app.engine.starter_recent import pitcher_name

            for side in ("home", "away"):
                nm = pitcher_name(jg, side)
                if nm:
                    names[nm] = side
        except Exception as exc:
            logger.debug("[fact-audit] 선발 이름 수집 생략: %s", exc)
        res = audit(verdict, prompt, names=names or None)
        res.update(game_id=gid, sport=jg.get("sport") or "")
        await _store(pool, res)
        logger.info("[fact-audit] game=%s v=%d d=%d nf=%d mismatch=%d",
                    gid, res["verified_n"], res["derived_n"],
                    res["not_found_n"], res["mismatch_n"])
        if res["mismatch_n"]:
            await _alert(res)
        return res
    except Exception as exc:
        logger.warning("[fact-audit] game=%s 감사 실패 — 판정·발송은 계속: %s",
                       gid, exc)
        await _monitor_down("fact_audit", gid, exc)
        return None


async def _store(pool, res: dict) -> None:
    if pool is None:
        return
    try:
        await pool.execute(
            """INSERT INTO judgement_audit
                   (game_id, sport, judged_at, verified_n, derived_n,
                    not_found_n, mismatch_n, mismatch_detail)
               VALUES ($1,$2, now(), $3,$4,$5,$6,$7::jsonb)""",
            int(res["game_id"]), res["sport"], res["verified_n"],
            res["derived_n"], res["not_found_n"], res["mismatch_n"],
            json.dumps(res["mismatch_detail"], ensure_ascii=False))
    except Exception as exc:
        logger.warning("[fact-audit] 저장 실패: %s", exc)


async def _alert(res: dict) -> None:
    """기존 워치독 억제 체계를 **재사용**한다 (P5) — 새로 만들지 않는다."""
    try:
        from app.alerts import watchdog

        first = (res["mismatch_detail"] or [{}])[0]
        # 🔴 [2026-09-05] **인용 원문을 함께 보낸다.** 종전 경보는
        #    "ip 주장 5.8 vs 원문 6.0" 까지만 줬고, 그 숫자만으로는
        #    무엇을 잘못 인용했는지 알 수 없어 원인 특정이 불가능했다 —
        #    실제 문장은 `mismatch_detail["claim"]` 에 **이미 담겨 있었는데**
        #    경보가 그것을 버리고 있었다. DB 를 열 수 없는 상황에서는
        #    경보가 유일한 창이다.
        claim = str(first.get("claim") or "").replace("\n", " ")[:180]
        await watchdog("W-FACT-MISMATCH",
                       f"{res['mismatch_n']}건 — {first.get('unit')} "
                       f"주장 {first.get('claimed')} vs 원문 "
                       f"{first.get('nearest_in_source')}"
                       + (f'\n  인용: "{claim}"' if claim else ""),
                       target=f"game={res['game_id']}")
    except Exception as exc:
        logger.warning("[fact-audit] 경보 실패: %s", exc)


async def _monitor_down(layer: str, gid, exc: Exception) -> None:
    try:
        from app.alerts import watchdog

        await watchdog("W-MONITOR-DOWN",
                       f"{layer} 실패 — {type(exc).__name__}: {exc}"[:180],
                       target=f"game={gid}")
    except Exception:
        pass
