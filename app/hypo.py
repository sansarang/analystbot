"""🔴🔴 **v5-A §3 단계 3 — 가설·시나리오.** DeepSeek 가 쓰고 **코드가 검사한다**.

부록 v5-A §1·§3:

> 단계 3 — DeepSeek · 입력: 검증된 변수 + 구조 사실 + 보드 줄 ·
> 출력: 팀별 가설, 시나리오 A~H(최대 8) · **웹 접근 없음**
> 코드 처리 — `driver_vars` 의 ID 가 입력 `variables` 에 없으면 폐기
> (`unknown_var`) · `mechanism` 에 **입력에 없는 고유명사**면 폐기(`new_fact`) ·
> `outcomes` 범위 밖이면 폐기 · 남은 세트에 §6-2 자동 보강 ·
> **`strength` 는 `driver_vars` 의 hardness 합**(`weak:true` 는 표시만).

══════════════════════════════════════════════════════════════════
🔴 왜 이 단계가 생겼나 — **찾은 변수로 시나리오를 잘못 짰다**
══════════════════════════════════════════════════════════════════

v5-A §0: *"09-29~10-04 미적중을 갈라 보면 변수를 못 찾아서 난 것보다 **찾은
변수로 시나리오를 잘못 짜서** 난 것이 많다. 남아공 5-0(결장 변수는 있었는데
대량득점 시나리오 부재), 콜롬비아 0-1(h2h 로 한 시나리오를 눌러 무패 0.85),
크로아티아 봇 카드(난타전 시나리오 부재로 거짓 1.0)."*

🔴 **M41** — 모델이 **사실을 만들면 그 시나리오는 폐기**다. 고유명사 목록은
   입력에서 **코드가 뽑는다** — 모델에게 묻지 않는다.
🔴 **M43** — 등급·확률·승자 단어는 **판정 입력에 닿지 않는다**(절대규칙 5).
   ⚠️ 버린 칸을 **이름으로 남긴다**(#3 조용한 0 금지).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.reasons import Reason

logger = logging.getLogger(__name__)

#: 🔴 필수형 누락을 세는 사유(§6 측정의 **필수형 누락률**).
MISSED_REASON = Reason.DEEPSEEK_MISSED_REQUIRED

#: 🔴🔴 **M43 — 판정에 닿으면 안 되는 칸.** ⚠️ 모델이 적어도 **버린다**.
#
#  v5-A §1: *"등급·생존율·pick·상한 — **코드 자리**다. DeepSeek 출력에 등급·
#  확률·승자 단어가 있으면 **무시하고 로그만 남긴다**."*
BANNED_FIELDS: tuple[str, ...] = (
    "confidence", "verdict", "probability", "winner", "grade", "survival",
    "pick", "odds", "edge", "strength_hint",
)

#: 🔴 종목별 스코어 범위(v5-A §3). ⚠️ 코드가 **범위를 지어내지 않는다** —
#  부록이 이름으로 댄 둘만 있고, 모르는 종목은 **받지 않는다**(fail-closed).
SCORE_RANGE: dict[str, tuple[int, int]] = {
    "soccer": (0, 9),
    "baseball": (0, 25),
}

#: 🔴🔴 **이름 후보로 볼 글자.**
#
#  ══════════════════════════════════════════════════════════════════
#  🔴 **첫 판이 한글 전부를 고유명사로 봤다**(실측 2026-10-04)
#  ══════════════════════════════════════════════════════════════════
#
#  내 정규식이 `[가-힣]{2,}` 였다 — 그러면 `결장이`·`수비를`·`흔든다` 가
#  **전부 고유명사**이고 **정상 시나리오가 `new_fact` 로 폐기**됐다.
#
#  ⚠️ 한글·가나·한자에는 **대문자가 없다** — 라틴처럼 머리글자로 못 가린다.
#  🔴 그래서 **두 겹**이다:
#     ① 이 정규식이 **후보**를 뽑는다(라틴은 머리글자 · CJK 는 두 글자 이상)
#     ② 그 후보가 **이름 사전에 없고** 조사·어미를 떼도 없을 때만 **새 이름**
#        이다(`_new_names`). ⚠️ 사전은 입력·`teamref` 에서 자란다(사본 금지).
_WORD = re.compile(r"[A-Z][a-zA-Z'\-]{2,}|[가-힣]{2,}|[ぁ-んァ-ン一-鿿]{2,}")

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **M41 의 고유명사 검사는 *라틴 머리글자*로만 한다**(실측 2026-10-04)
# ══════════════════════════════════════════════════════════════════
#
# 세 판을 거쳐 여기 왔다:
#
#   ① `[가-힣]{2,}` 를 전부 이름으로 봤다 → `결장이`·`수비를` 가 이름이 됐고
#      **정상 시나리오가 폐기**됐다.
#   ② 보통 낱말 **사전**(§4 선언·낱말표)으로 걸렀다 → `흔든다` 가 남았다.
#   ③ **용언 어미**로 걸렀다 → `흔들어`·`중원을` 이 남았다.
#
# 🔴 **사전·어미로는 끝이 없다.** 한국어·일본어는 **이름과 보통 낱말이 글자
#    모양으로 안 갈린다**(대문자가 없다). 그 길로 가면 *"다음 동사"* 가 영영
#    남고, 그때마다 **정상 시나리오가 사라진다** — 그것이 M41 이 막으려던 것과
#    **반대** 결과다(시나리오를 줄이면 거짓 1.0 이 다시 생긴다 · v5-A §1).
#
# ✅ 그래서 **라틴 머리글자만** 본다. ⚠️ 그 뜻:
#     · `Modric` 같은 **라틴 이름**은 잡는다(유럽·미국 선수가 대부분이다)
#     · 한글·가나 글은 **이 검사를 지난다** — 🔴 그 사실을 **사유로 남긴다**
#       (조용히 통과시키지 않는다 · #3)
# 🔴 왜 이쪽이 맞나: **거짓 폐기가 거짓 통과보다 나쁘다.** 거짓 통과는 §5 인용
#    검증과 §6-2 보강이 뒤에서 또 거르지만, 거짓 폐기는 **그 갈래를 영영
#    없앤다**(남아공 5-0 이 그렇게 났다).
# ⚠️ 한글 글의 지어낸 이름은 **다른 자**가 필요하다 — `questions/` 에 적었다.
_LATIN_NAME = re.compile(r"\b[A-Z][a-zA-Z'\-]{2,}\b")

#: 🔴 라틴 이름이지만 **이름이 아닌** 말. ⚠️ 문장 머리 대문자가 여기 걸린다.
#  🔴 손으로 늘리지 않는다 — 이 목록이 자라면 그것이 ③ 의 실패를 반복하는
#     것이다. 지금 것은 **영어 문장 머리에 오는 기능어**뿐이다.
_LATIN_STOP: frozenset[str] = frozenset({
    "The", "This", "That", "These", "Those", "There", "Their", "They",
    "And", "But", "With", "Without", "When", "While", "Because", "Since",
    "If", "Then", "Both", "Each", "Home", "Away", "Over", "Under",
})


@dataclass
class HypoInput:
    """🔴 단계 3 입력. **코드가 만든다**(v5-A §3).

    ⚠️ 여기 **URL·기사 원문·배당이 없다**(v5-A §2 가 금지했다).
    """

    home: str
    away: str
    sport: str
    competition: str
    variables: list = field(default_factory=list)
    facts: dict = field(default_factory=dict)
    board: list = field(default_factory=list)
    required_types: list = field(default_factory=list)
    lineup_state: dict = field(default_factory=dict)
    #: ⚠️ v5-A §1 — Solar 초안은 **참고**다(필수가 아니다 · §3-6 선택)
    solar_draft: dict | None = None

    def var_ids(self) -> set[str]:
        return {str(v.get("id") or "") for v in (self.variables or [])
                if str(v.get("id") or "")}

    def hardness(self, vid: str) -> int:
        for v in (self.variables or []):
            if str(v.get("id") or "") == str(vid):
                return int(v.get("hardness") or 0)
        return 0


@dataclass
class HypoResult:
    """🔴 단계 3 산출. ⚠️ **못 돌았어도 이 꼴로 온다**(예외가 아니다)."""

    scenarios: list = field(default_factory=list)
    hypotheses: dict = field(default_factory=dict)
    form: dict = field(default_factory=dict)
    drops: list = field(default_factory=list)
    missed: list = field(default_factory=list)
    reason: Reason = Reason.OK
    why: str = ""
    usd: float = 0.0


def to_payload(inp: HypoInput) -> dict:
    """🔴 모델에게 **보내는 것**. ⚠️ URL·기사 원문·배당은 **안 보낸다**(v5-A §2).

    🔴 변수는 **요약만** 보낸다(유형·방향·주장·인용 요약) — 원문을 보내면 그
       자체가 v5-A §2 가 금지한 것이다.
    """
    return {
        "match": {"home": inp.home, "away": inp.away, "sport": inp.sport,
                  "competition": inp.competition},
        "lineup_state": dict(inp.lineup_state or {}),
        "facts": _clean_facts(inp.facts),
        "variables": [
            {"id": v.get("id"), "type": v.get("type"), "team": v.get("team"),
             "direction": v.get("direction"),
             "hardness": int(v.get("hardness") or 0),
             "claim": str(v.get("claim") or "")[:200],
             "conflict": bool(v.get("conflict"))}
            for v in (inp.variables or [])],
        # 🔴 **마켓 종류와 기준선만**(v5-A §1: *"보드는 … 숫자(배당) 없음"*)
        "board": [{"market": b.get("market"), "point": b.get("point"),
                   "side": b.get("side")} for b in (inp.board or [])],
        "required_types": [str(x) for x in (inp.required_types or [])],
        "solar_draft": inp.solar_draft or None,
    }


def _clean_facts(facts: dict) -> dict:
    """🔴 구조 사실에서 **URL 을 걷는다**(v5-A §2 가 금지했다)."""
    import json
    try:
        said = json.dumps(facts or {}, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return {}
    said = re.sub(r'"[^"]*https?://[^"]*"', '"(주소 뺐다)"', said)
    try:
        return json.loads(said)
    except ValueError:
        return {}


def proper_nouns(inp: HypoInput) -> set[str]:
    """🔴🔴 **M41 — 고유명사 목록을 코드가 뽑는다**(모델에게 묻지 않는다).

    ⚠️ 어디서 뽑나: **입력 변수의 `claim`·구조 사실·XI**(v5-A §3). 🔴 그
       바깥의 이름이 `mechanism` 에 나오면 모델이 **지어낸** 것이다.
    """
    import json
    blob = [str(v.get("claim") or "") for v in (inp.variables or [])]
    try:
        blob.append(json.dumps(inp.facts or {}, ensure_ascii=False,
                               default=str))
    except (TypeError, ValueError):
        pass
    blob += [inp.competition, inp.home, inp.away]
    got: set[str] = set()
    for line in blob:
        got |= set(_WORD.findall(str(line)))
    return got


def known_names(inp: HypoInput) -> set[str]:
    """🔴🔴 **이름 사전** — 입력 + `teamref` + §4 낱말에서 **자란다**.

    ⚠️ 손으로 이름 목록을 적으면 한 발 늦는다(#1 사본 금지). 🔴 `teamref` 는
       **모든 언어의 팀 이름**을 들고 있고, 입력은 XI·명단·변수 주장을 든다.
    """
    got = set(proper_nouns(inp))
    try:
        from app import teamref
        for key in (inp.home, inp.away):
            for lang in ("en", "ko", "ja", "es"):
                for w in _WORD.findall(str(teamref.label_of(key, lang) or "")):
                    got.add(w)
    except Exception as exc:                                # noqa: BLE001
        logger.info("[hypo] 팀 이름을 못 읽었다: %r", exc)
    # ⚠️ **보통 낱말 사전은 쓰지 않는다** — 위 머리글의 ②·③ 이 그 길의 실패다.
    #    🔴 라틴 머리글자 검사는 사전이 작아도 된다(기능어만 걷는다).
    return got


def _has_cjk(text: object) -> bool:
    """🔴 그 글에 한글·가나·한자가 있나 — 있으면 이름 검사가 **라틴만**이다."""
    return bool(re.search(r"[가-힣ぁ-んァ-ン一-鿿]", str(text or "")))


def _new_names(text: object, known: set[str]) -> list[str]:
    """🔴 그 글에서 **사전에 없는 라틴 이름**만(위 머리글의 까닭).

    ⚠️ 한글·가나 이름은 **이 검사가 못 잡는다** — 그 사실은 호출부가 사유로
       남긴다(`check_scenarios` 가 `name_check` 를 적는다).
    """
    out: list[str] = []
    for w in _LATIN_NAME.findall(str(text or "")):
        if w in _LATIN_STOP or w in known:
            continue
        # 🔴 사전 이름의 **조각**이면 그 이름이다(`Modrić` ↔ `Modric`)
        if any(w.lower() in k.lower() or k.lower() in w.lower()
               for k in known if len(k) > 2):
            continue
        out.append(w)
    return out

def check_scenarios(rows: list, inp: HypoInput) -> tuple[list, list]:
    """🔴🔴 **M41·M43 관문.** `(남은 시나리오, [(id, 사유, 왜)])`.

    🔴 순서가 뜻이다 — **싼 것부터**: 금지 칸 걷기 → 변수 ID → 고유명사 →
       스코어 범위. ⚠️ 폐기는 **사유 enum** 으로 돌려준다(§8-6).
    """
    ids = inp.var_ids()
    nouns = known_names(inp)
    lo, hi = SCORE_RANGE.get(str(inp.sport), (None, None))
    kept: list = []
    drops: list = []
    for raw in (rows or []):
        if not isinstance(raw, dict):
            drops.append(("?", Reason.UNKNOWN_VAR, "시나리오가 사전이 아니다"))
            continue
        sid = str(raw.get("id") or "?")
        # ── 🔴 M43 — 금지 칸을 **걷는다**(모델이 적어도 버린다)
        row = {k: v for k, v in raw.items() if k not in BANNED_FIELDS}
        gone = sorted(k for k in raw if k in BANNED_FIELDS)
        if gone:
            # ⚠️ **로그만 남긴다**(v5-A §1) 그리고 카드가 읽게 칸에도 적는다
            logger.info("[hypo] %s — 판정 금지 칸을 버렸다: %s", sid, gone)
            row["dropped_fields"] = gone
        # ── 🔴 M41 ① 변수 ID
        said = [str(x) for x in (row.get("driver_vars") or [])]
        unknown = [x for x in said if x not in ids]
        if not said or unknown:
            drops.append((sid, Reason.UNKNOWN_VAR,
                          f"🔴 `driver_vars` {unknown or '없음'} 이 검증 변수가 "
                          f"아니다(있는 것 {sorted(ids)})"))
            continue
        # ── 🔴 M41 ② 고유명사
        new = _new_names(row.get("mechanism"), nouns)
        # 🔴 **못 잡는 범위를 적는다**(#3 조용한 0 금지) — 한글·가나 글의
        #    지어낸 이름은 이 검사가 못 가른다(위 머리글).
        row["name_check"] = ("latin_only" if _has_cjk(row.get("mechanism"))
                             else "latin")
        if new:
            drops.append((sid, Reason.NEW_FACT,
                          f"🔴 `mechanism` 에 **입력 밖 고유명사**가 있다: "
                          f"{new[:3]} — 모델이 지어냈다"))
            continue
        # ── 🔴 스코어 범위
        out = [x for x in (row.get("outcomes") or [])]
        if not out or lo is None:
            drops.append((sid, Reason.UNKNOWN_VAR,
                          f"🔴 `outcomes` 가 비었거나 종목 `{inp.sport}` 의 "
                          f"범위를 **모른다**(선언: {sorted(SCORE_RANGE)})"))
            continue
        bad = [p for p in out
               if not (isinstance(p, (list, tuple)) and len(p) == 2
                       and all(isinstance(n, int) and lo <= n <= hi
                               for n in p))]
        if bad:
            drops.append((sid, Reason.UNKNOWN_VAR,
                          f"🔴 스코어가 범위({lo}~{hi}) 밖이다: {bad[:2]}"))
            continue
        # ── 🔴 §6-1 — strength 는 **hardness 합**. `weak` 는 표시만.
        row["strength"] = sum(inp.hardness(x) for x in said)
        row["added_by"] = "deepseek"
        kept.append(row)
    return kept, drops


def missed_required(rows: list, inp: HypoInput) -> list[str]:
    """🔴 **필수형 누락** — `required_types` 중 세트에 없는 것.

    ⚠️ 그 수가 §6 측정의 **필수형 누락률**이다(원장이 센다).
    """
    said = {str(r.get("type") or "") for r in (rows or [])}
    return [t for t in (inp.required_types or []) if str(t) not in said]


def run(inp: HypoInput, *, now=None, _net=None) -> HypoResult:
    """🔴🔴 **단계 3 전체** — 묻고 **코드가 검사한다**.

    ⚠️ 꺼져 있거나 장애면 **빈 세트와 사유**를 낸다(M45) — v5 원래 경로가 돈다.
    """
    from app import deepseek
    got = deepseek.ask([{"role": "system", "content": system_prompt()},
                        {"role": "user", "content": _dump(to_payload(inp))}],
                       match=f"{inp.home}|{inp.away}", stage="stage3",
                       now=now, _net=_net)
    if not got.ok:
        return HypoResult(reason=got.reason, why=got.why)
    box, why = got.json()
    if box is None:
        return HypoResult(reason=Reason.DONE_PARSE_FAIL, why=why,
                          usd=got.usd)
    kept, drops = check_scenarios(box.get("scenarios") or [], inp)
    missed = missed_required(kept, inp)
    if missed:
        logger.info("[hypo] 🔴 %s — 필수형 누락 %s", MISSED_REASON.value, missed)
    return HypoResult(
        scenarios=kept, hypotheses=dict(box.get("hypotheses") or {}),
        form=dict(box.get("form") or {}), drops=drops, missed=missed,
        reason=Reason.OK, usd=got.usd,
        why=(f"단계 3 — 시나리오 {len(kept)}개 · 폐기 {len(drops)}개"
             + (f" · 🔴 필수형 누락 {missed}" if missed else "")))


def _dump(box: dict) -> str:
    import json
    return json.dumps(box, ensure_ascii=False, default=str)


def system_prompt() -> str:
    """🔴 v5-A §3 프롬프트 요지 — **여덟 줄 그대로**(고정 문자열 · 캐시 단가)."""
    return (
        "너는 스포츠 경기 하나의 가설과 시나리오를 쓴다. 웹에 닿을 수 없다.\n"
        "\n"
        "1. 🔴 너는 **사실을 만들지 않는다.** `variables` 와 `facts` 에 없는 "
        "사실은 쓰지 않는다. 모르면 시나리오에 넣지 않는다.\n"
        "2. 먼저 두 팀의 폼을 `facts.recent` 로 요약한다(최근 5경기·연속·"
        "직전 득실).\n"
        "3. 팀별 가설: 열쇠는 **`home`·`away` 두 글자**다(팀 이름이 아니다). "
        "`reasons` 는 **이긴다면 왜**, `breaks` 는 **무너지는 조건**이다. 🔴 각 항목은 **한 문장**이고 그 안에 근거 변수 ID 를 "
        "괄호로 적는다 — 예: \"공백을 Ramos 가 메워 전방이 유지된다(R4, R10)\". "
        "⚠️ **ID 만 적으면 안 된다.** 양방향 변수는 **양쪽에 다** 쓴다.\n"
        "4. 시나리오 4~6개. 각 시나리오는 `driver_vars`(변수 ID), "
        "`mechanism`(그 변수들이 어떻게 작동해 그 결과가 나오는지 1~2문장), "
        "`outcomes`(스코어 1~2개).\n"
        "5. `required_types` 의 시나리오를 **반드시 포함**한다. 근거 변수가 "
        "약하면 `weak:true` 로 표시하되 **빼지 않는다**.\n"
        "6. 전부 같은 방향이면 안 된다. 각 팀이 이기는 시나리오가 **적어도 "
        "하나씩** 있어야 한다(근거가 약하면 `weak`).\n"
        "7. h2h 는 메커니즘(세트피스·역습 방식)이 있을 때만 driver 로 쓰고, "
        "**다른 시나리오를 누르는 근거로 쓰지 않는다.**\n"
        "8. 🔴 **등급·확률·승자·배당·추천 단어를 쓰지 않는다.**\n"
        "\n"
        "출력은 JSON 하나다: "
        '{"form":{...},"hypotheses":{"home":'
        '{"reasons":["문장(R1, R2)"],"breaks":["문장(R4)"]},"away":{...}},'
        '"scenarios":[{"id":"A","driver_vars":[],"mechanism":"",'
        '"outcomes":[[1,2]],"type":"normal","weak":false}]}\n'
    )
