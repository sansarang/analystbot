"""§17-b **L1·L2·L3 추출** — 규칙 파서가 못 읽는 형식의 **대체**다.

## 왜 필요한가

규칙 파서는 **본 형식만** 읽는다. 실측 2026-09-30(단계 4): 야구 압축 타순·
footboom1 의 `팀 : 이름, 이름` 은 읽지만, 처음 보는 매체 꼴은 0건이다. 그러면
새 리그·새 매체에서 **결과가 아예 안 나온다.**

v4 는 그 자리를 이미 정해 뒀다 — §17-b:

> LLM 이 하는 일은 여섯뿐이다: **L1 결장** · **L2 인용+의도** · **L3 순위·동기** ·
> L4 경기전후·중복·시점 · L5 반증조건→검색어 · L6 카드 슬롯

스키마도 `app/llm.py` 에 이미 있었다(`L1_ABSENCE`·`L2_INTENT`·`L3_STANDINGS`).
**부르는 곳이 없었다** — 안 이어진 코드는 없는 코드보다 나쁘다(§배선).

## 🔴 경계 — 이 파일이 지키는 것

| 규칙 | 어디서 |
|---|---|
| 로컬 `qwen3:8b` 뿐 · `:cloud`·유료 0건 | §17-a · §11-7 |
| **JSON 스키마 강제** — 프롬프트로 "JSON만" 부탁하지 않는다 | §17-g-1 |
| 항목마다 **기댄 원문 문장**을 함께 낸다. 본문에 없으면 **버린다** | §17-g-2 |
| `direction`·`weight`·`strength`·`survival`·`verdict` 에 **닿지 않는다** | §17-c |
| 버린 출력은 `extraction_rejected` 에 남긴다 | §17-g-4 |
| 호출 예산을 넘기면 **unknown** — 억지로 부르지 않는다 | §17-e |

🔴 **LLM 은 사실만 낸다.** 유형·방향·가중치는 규칙이 정한다(단계 5).

## ⚠️ 여섯에 **라인업이 없다**

§17-b 의 목록에 라인업 추출이 없다. 그래서 새 형식의 라인업은 **규칙 파서로만**
읽는다 — 그것이 지금의 한계이고, 넣을지는 사용자 결정이다
(`docs/fable/questions/` 에 올렸다).
"""
from __future__ import annotations

import json
import logging

from app import llm, verify
from app.blackboard import Fact

logger = logging.getLogger(__name__)

#: 🔴 §17-b 의 여섯 중 **이 파일이 잇는 셋**. 원본은 §17-b 이고 여기 베끼지 않는다 —
#   이름만 적는다(스키마는 `app/llm.py` 가 들고 있다).
TASKS = {
    "L1": ("결장", llm.L1_ABSENCE, "absences"),
    "L2": ("인용·의도", llm.L2_INTENT, None),
    "L3": ("순위·동기", llm.L3_STANDINGS, "standings"),
}

#: §17-d 공통 머리말에 얹는 지시. 🔴 **원문 문장을 요구한다**(§17-g-2).
_ASK = """{what}

기사 제목: {title}
기사 본문:
{body}

규칙(어기면 그 항목은 버려진다):
- 기사에 **명시된 것만** 낸다. 추론·보완·요약 금지.
- 항목마다 그것이 기댄 **원문 문장을 그대로** 함께 낸다.
- 없으면 빈 목록을 낸다. 지어내지 않는다.
"""

#: 🔴 **사유 낱말** — 이 낱말이 `player_name` 에 오면 버린다(아래 `_echoed`).
#
#  ⚠️ 실측 2026-10-02: qwen3:8b 가 `player_name` 에 **프롬프트의 낱말**을 넣었다 —
#     `결장`·`징계`·`차출`. 진짜 답(`장슬기`)은 놓쳤다. 7B 급은 열거를 보기로 읽는다.
#  🔴 그래서 ① 프롬프트에서 열거를 **괄호 밖으로** 빼고 ② 코드가 그 낱말을 막는다.
#     한쪽만으로는 안 된다 — 프롬프트는 부탁이고 코드가 집행이다.
CAUSE_WORDS = ("결장", "차출", "징계", "부상", "말소", "출전정지", "경고누적",
               "absence", "suspension", "injury", "injured")

_WHAT = {
    # 🔴 **이름 칸에는 사람 이름만.** 보기를 주고 금지를 명시한다(실측으로 고쳤다).
    "L1": ("이 기사에서 **경기에 못 나오는 선수**를 뽑아라.\n"
           "- `player_name` 에는 **사람 이름만** 쓴다. "
           "`결장`·`징계`·`부상` 같은 **사유 낱말을 이름 칸에 쓰면 버려진다**.\n"
           "- 보기: 본문이 *\"수비수 장슬기는 경고 누적으로 결장한다\"* 면 "
           "`player_name=\"장슬기\"`, `basis=\"suspension\"` 이다.\n"
           "- 사람 이름이 안 적혀 있으면 **그 항목을 내지 않는다**."),
    "L2": ("이 기사에서 **감독이 한 말**을 뽑아라.\n"
           "- `quote` 에는 기사에 **따옴표로 적힌 말**을 그대로 옮긴다.\n"
           "- 따옴표 기호(\u201c \u201d \u2018 \u2019)는 **빼고** 안쪽 글자만 옮긴다.\n"
           "- 말한 사람이 감독이 아니면 **내지 않는다**."),
    "L3": "이 기사에서 **순위표 항목**(팀·승·패·무·잔여경기)을 뽑아라.",
}

#: 🔴 본문을 이만큼만 넘긴다. 7B 급은 긴 입력에서 문장을 **섞어** 낸다.
#   ⚠️ 자르는 것을 숨기지 않는다 — 자른 사실을 사유에 적는다.
BODY_CHARS = 6000

#: 🔴 **좁은 질문의 본문 상한.** 실측 2026-10-02: 긴 본문 + 긴 프롬프트에서 qwen3:8b 가
#   JSON 을 못 끝냈다(`Unterminated string`). 좁은 질문은 답이 셋뿐이라 본문도 짧게 준다.
#   ⚠️ 자른 것은 **사유로 남는다** — 조용히 자르지 않는다.
#: 🔴 2026-10-02 **올렸다**: 2500 → 4000. 실측 로그가 *"본문 3329자 중 2500자만
#   넘겼다"* 를 네 번 적었다 — 기사 타순·감독 발언은 **뒤쪽**에 있으므로 앞 2500자만
#   보면 답이 있는데 unknown 이 돌아온다.
#   ⚠️ 2500 을 고른 까닭(JSON 이 안 끝났다)은 **긴 프롬프트** 탓이었고 그 프롬프트는
#      세 줄로 줄였다 — 그때 남겨 둔 상한만 안 따라왔다.
ASK_BODY_CHARS = 4000


async def run(task: str, *, title: str, body: str, question_id: str,
              source: str = "", published_at=None, team: str | None = None,
              budget: llm.Budget | None = None, pool=None,
              step: int = 1, timeout: float | None = None,
              retry: int | None = None) -> tuple[list[Fact], list[str]]:
    """§17-b 한 과제를 돌린다. 반환은 `(사실들, 버린 사유들)`.

    🔴 **버린 것을 돌려준다.** 개수만 세면 프롬프트를 못 고친다(§19-b-6 과 같은 규약).
    🔴 **본문에 없는 문장을 든 항목은 버린다**(§17-g-2) — LLM 은 그럴듯한 인용을
       만들어낸다. 본문 대조가 유일한 방어다(§12-c-6 이 같은 이유로 있다).
    """
    # 🔴🔴 **좁은 질문**(사용자 설계 2026-10-02 ③): `ASK:<유형>` 꼴이다.
    #    ⚠️ §17-b 가 허용한 자리는 L1~L6 이다. 좁은 질문은 **L1~L3 의 변형**으로 둔다 —
    #       질문을 좁히는 것은 *프롬프트 모양*이고 새 권한이 아니다(괜히 v4 를 넓히지
    #       않는다 · `questions/2026-10-02_catalog.md`).
    ask_type = ""
    if task.startswith("ASK:"):
        ask_type = task.split(":", 1)[1].strip()
        if not _ask_question(ask_type):
            return [], [f"{task}: §4 유형 `{ask_type}` 에 판정 기준(`decides`)이 없다"]
        label, schema = f"좁은 질문({ask_type})", llm.ASK_TYPE
    elif task not in TASKS:
        return [], [f"§17-b 에 없는 과제: {task}"]
    else:
        label, schema, _ = TASKS[task]
    if not (body or "").strip():
        return [], [f"{task}({label}): 본문이 비었다 — 부르지 않았다"]

    # 🔴 좁은 질문은 **본문도 짧게** 준다. 실측 2026-10-02: 긴 본문이 긴 인용을
    #    부르고, 긴 인용에서 JSON 이 끊겼다. ⚠️ 자른 사실은 아래에서 사유로 남는다.
    cap = ASK_BODY_CHARS if ask_type else BODY_CHARS
    trimmed = body[:cap]
    prompt = _ASK.format(
        what=_ask_prompt(ask_type) if ask_type else _WHAT[task],
        title=title or "(제목 없음)", body=trimmed)
    dropped: list[str] = []
    if len(body) > cap:
        # 🔴 자른 것을 조용히 넘기지 않는다
        dropped.append(f"{task}: 본문 {len(body)}자 중 {cap}자만 넘겼다")

    try:
        # 🔴 **한 번 부르는 시간·되시도를 호출부가 정한다**(사용자 지시 2026-10-02).
        #    ⚠️ 기본값을 그대로 쓰면 `timeout=120·retry=1` → 한 건 최악 240초다.
        kw = {}
        if timeout is not None:
            kw["timeout"] = float(timeout)
        if retry is not None:
            kw["retry"] = int(retry)
        got = await llm.call(prompt, schema, budget=budget, **kw)
    except llm.LLMUnavailable as exc:
        await _reject(pool, task, "폐기", f"호출 실패: {exc}", None, source)
        return [], [*dropped, f"{task}({label}) 호출 실패: {exc}"]

    items = _items(task, got)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **모델이 "아니다"라고 한 것도 기록이다**(실측 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  라이브에서 LLM 을 **18번 불렀는데 기록이 0줄**이었다. `answer != "yes"` 면
    #  `items` 가 비고 `dropped` 도 비어서 로그 줄이 아예 안 났다 — 그리고 본문
    #  자르기 사유도 없어졌다(좁힌 글이 상한 아래라서).
    #  🔴 그러면 *"묻지 않았다"* 와 *"물었는데 아니라고 했다"* 가 구분되지 않는다
    #     (#3 조용한 0 금지). 그 둘의 처방은 정반대다.
    if ask_type and not items:
        ans = str((got or {}).get("answer") or "").strip() or "빈 답"
        dropped.append(
            f"{task}: 모델이 `{ans}` 라고 했다 — 그 기사에 그 사실이 없다"
            + (f" (주체 `{got.get('subject')}`)" if (got or {}).get("subject")
               else ""))
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **`yes` 인데 인용이 없으면 — 한 번만 되묻는다** (실측 2026-10-02)
    # ══════════════════════════════════════════════════════════════════
    #
    #  라이브에서 `ASK:emotion` 이 `{"answer": "yes"}` 를 내고 `quote` 를 비웠다.
    #  §17-g-2 는 원문 문장이 없는 항목을 버리라고 하므로 **맞게 버렸다** — 그러나
    #  그렇게 끝내면 *찾은 것*을 통째로 잃는다(그 기사에 정말 그 이야기가 있었다).
    #
    #  🔴 **느슨하게 하지 않는다.** 되묻고, 그래도 인용이 없으면 그대로 버린다.
    #     즉 규칙은 그대로고 **기회를 한 번 더** 주는 것이다(§19-b-5 *"바꿔서 다시"*).
    #  ⚠️ 한 번뿐이다 — 예산(`llm.Budget`)이 막으면 되묻지 않고 사유가 남는다.
    if ask_type and items and not str(items[0].get("quote") or "").strip():
        dropped.append(f"{task}: `yes` 인데 인용이 비었다 — 한 번 되묻는다")
        try:
            again = await llm.call(
                prompt + "\n\n🔴 앞선 답은 yes 였다. 그 판단의 근거가 된 **본문의 "
                         "한 문장만** `quote` 에 그대로 옮겨라. 못 찾으면 answer 를 "
                         "unknown 으로 적어라.",
                schema, budget=budget, **kw)
        except llm.LLMUnavailable as exc:
            dropped.append(f"{task}: 되묻기 실패 — {exc}")
        else:
            retried = _items(task, again)
            if retried and str(retried[0].get("quote") or "").strip():
                items = retried
            else:
                dropped.append(f"{task}: 되물어도 인용이 없다 — 버린다")
                items = []
    out: list[Fact] = []
    for item in items:
        # 🔴 **프롬프트의 낱말을 이름으로 낸 항목은 버린다**(실측 2026-10-02).
        #    ⚠️ 프롬프트로 부탁하는 것만으로는 안 됐다 — 코드가 집행한다.
        echoed = _echoed(task, item)
        if echoed:
            dropped.append(f"{task}: 사유 낱말을 이름 칸에 넣었다 — {echoed!r}")
            await _reject(pool, task, "규칙위반", f"사유 낱말 반복: {echoed}",
                          item, source)
            continue
        sent = str((item or {}).get("evidence_sentence") or "").strip()
        # 🔴 **L2 는 인용이 곧 근거다.** 실측 2026-10-02: 모델이 `quote` 는 맞게
        #    뽑고 `evidence_sentence` 를 비워서 **맞는 발언이 버려졌다**.
        #    ⚠️ §17-g-2 를 느슨하게 하는 것이 아니다 — 아래 본문 대조는 그대로
        #       돌고, §12-c-6(*"감독 발언은 본문에 그 문장이 있을 때만"*)이 바로
        #       그 인용을 대조하라는 규칙이다.
        if not sent and (task == "L2" or task.startswith("ASK:")):
            sent = str((item or {}).get("quote") or "").strip()
            if sent:
                dropped.append(f"{task}: `evidence_sentence` 가 비어 `quote` 로 "
                               f"대조한다 — {sent[:40]}")
        # 🔴 §17-g-2 — **원문 문장이 본문에 실재해야 한다.**
        if not sent:
            dropped.append(f"{task}: 원문 문장이 없다 — {str(item)[:80]}")
            await _reject(pool, task, "규칙위반", "원문 문장 없음", item, source)
            continue
        grounded = verify.quote_grounded(sent, trimmed)
        if not grounded.ok:
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **한 글자 오타로 진짜 발견을 버리지 않는다**(실측 2026-10-02)
            # ══════════════════════════════════════════════════════════
            #
            #  라이브에서 모델이 `ソフトバンク` 의 `ク` 를 떨어뜨렸고, 그 탓에
            #  **唐川 은퇴 세레머니(10/3)** 라는 진짜 사실이 통째로 사라졌다 —
            #  사람이 손으로 쓴 분석의 변수 R7 이 바로 그것이다.
            #  🔴 검증을 느슨하게 하지 않는다. **본문의 실제 문장으로 되돌린다** —
            #     저장되는 글자는 늘 본문에 실재하므로 §17-g-2 는 그대로 지켜진다.
            #  ⚠️ 층은 한 칸 내린다(`likely`) — 모델이 정확히 옮기지 못한 것은 사실이다.
            fixed, why = verify.grounded_span(sent, trimmed)
            if not fixed:
                dropped.append(f"{task}: 본문에 없는 문장 — {sent[:60]} ({why})")
                await _reject(pool, task, "환각",
                              f"본문에 없는 문장: {sent[:120]}", item, source)
                continue
            dropped.append(f"{task}: 인용을 본문 문장으로 되돌렸다 — {why}")
            sent = fixed
            grounded = verify.quote_grounded(sent, trimmed)
            if not grounded.ok:
                # 🔴 되돌린 문장이 본문에 없으면 그것은 **우리 버그다** — 그대로 버린다
                dropped.append(f"{task}: 되돌린 문장도 본문에 없다(버그) — {sent[:60]}")
                continue
            grounded = verify.Verdict(True, why, hardness="likely")
        out.append(Fact(
            question_id=question_id, value=_value(task, item),
            # 🔴 인용이 본문에 실재하므로 `quote_grounded` 가 정한 층을 쓴다.
            #    ⚠️ 그래도 **hard 를 스스로 올리지 않는다** — 층은 검증기가 정한다.
            hardness=grounded.hardness,
            source=source, published_at=published_at,
            quote=sent[:400], article_title=title or "",
            article_body=trimmed,
            # 🔴 §17-e — **무엇이 뽑았는지 남긴다.** 모델이 바뀌면 그것이 보인다
            extracted_by=f"{task}:{llm.MODEL}", step=step, team=team))
    if out or dropped:
        logger.info("[%s] %d건 채택 · %d건 버림 (%s)", task, len(out),
                    len(dropped), source[:60])
    return out, dropped


def _echoed(task: str, item: dict) -> str:
    """🔴 LLM 이 **사유 낱말을 이름 칸에** 넣었나. 그 낱말을 돌려준다(없으면 빈 문자열).

    ⚠️ 실측 2026-10-02: `player_name` 이 `결장`·`징계`·`차출` 로 왔다 — 프롬프트가
       열거한 낱말을 그대로 베낀 것이다. 그런 항목은 **사실이 아니다.**
    """
    if task != "L1":
        return ""
    name = " ".join(str((item or {}).get("player_name") or "").split())
    if not name:
        return ""
    low = name.lower()
    for word in CAUSE_WORDS:
        if low == word.lower() or name == word:
            return name
    return ""


def _ask_question(vtype: str) -> str:
    """🔴 좁은 질문의 **내용은 카탈로그가 정한다**(§4 `asks`).

    ⚠️ **`decides` 가 아니다.** `decides` 는 **코드**가 쓰는 판정 기준이고 `asks` 는
       **기사에 던지는 한 문장**이다. 실측 2026-10-02: `decides`(*"결장 선수의 자리가
       수비(DF·GK)다"*)를 그대로 물었더니 7B 가 **전부 `unknown`** 을 냈다 — 기준은
       질문이 아니다.
    🔴 여기 질문을 적지 않는다 — 적으면 유형표와 갈린다(사본 금지).
    """
    from app import rules
    return str((rules.variable_types().get(vtype) or {}).get("asks") or "")


def _ask_prompt(vtype: str) -> str:
    """*"이 기사가 X 를 말하나?"* — **짧은 질문 하나.**

    ══════════════════════════════════════════════════════════════════
    🔴 **프롬프트가 길면 7B 가 JSON 을 못 끝낸다** (실측 2026-10-02)
    ══════════════════════════════════════════════════════════════════

    처음 판은 설명을 다섯 줄 붙였다. 결과:

        qwen3:8b 실패: Unterminated string starting at line 3

    같은 스키마에 **짧은 프롬프트**를 주면 `{"answer": "yes"}` 가 바로 나온다.
    🔴 즉 스키마 탓이 아니라 **내 프롬프트 탓**이었다. 그래서 세 줄로 줄이고
       `quote` 를 **한 문장**으로 못 박는다 — 긴 인용을 쓰다가 토큰이 끊긴다.
    ⚠️ 본문 대조는 한 문장으로 충분하다(§17-g-2 는 *그 문장이 본문에 있나*만 본다).
    """
    return (f"질문: {_ask_question(vtype)}\n"
            f"answer 는 yes/no/unknown 중 하나. 기사에 그 이야기가 없으면 unknown.\n"
            f"yes 면 quote 에 그 **한 문장**만 원문 그대로. subject 에 대상 이름.")


def _items(task: str, got: dict) -> list[dict]:
    """스키마별 항목 목록. 🔴 L2 는 **항목이 하나**다(스키마가 객체다)."""
    if task.startswith("ASK:"):
        # 🔴 `yes` 만 사실이 된다. `no`·`unknown` 은 **사실이 아니고 사유다**
        return [got] if str(got.get("answer") or "") == "yes" else []
    if task == "L2":
        return [got] if got.get("type") else []
    key = {"L1": "absences", "L3": "standings"}[task]
    return [x for x in (got.get(key) or []) if isinstance(x, dict)]


def _value(task: str, item: dict) -> dict:
    """사실의 값. 🔴 **LLM 이 낸 칸만** 담는다 — 유형·방향을 붙이지 않는다(§17-c)."""
    if task.startswith("ASK:"):
        # 🔴 `ask` 는 **어느 유형의 질문이었나** 다 — 유형·방향을 LLM 이 정한 것이
        #    아니다. 방향은 단계 5 가 §4 규칙으로 붙인다.
        return {"ask": task.split(":", 1)[1], "answer": item.get("answer"),
                "quote": item.get("quote"),
                # ⚠️ 명단 대조(④)가 이 칸을 쓴다 — 칸 이름을 `player_name` 으로
                #    맞춘다(세포가 그 이름으로 찾는다)
                "player_name": item.get("subject")}
    if task == "L2":
        return {"intent_type": item.get("type"), "quote": item.get("quote"),
                "speaker": item.get("speaker")}
    if task == "L1":
        return {"player_name": item.get("player_name"),
                "basis": item.get("basis"),
                "team_hint": item.get("team_hint"),
                "until_hint": item.get("until_hint")}
    return {k: item.get(k) for k in ("team", "w", "l", "d", "remaining", "note")}


async def _reject(pool, task: str, stage: str, reason: str, raw,
                  source: str) -> None:
    """§17-g-4 — 버린 출력을 `extraction_rejected` 에 남긴다.

    ⚠️ 적재 실패가 수집을 멈추지 않는다 — 진단을 못 남긴 것이 수집 실패보다
       가벼운 사고다. 🔴 대신 로그에는 남는다.
    """
    if pool is None:
        return
    try:
        await pool.execute(
            "INSERT INTO extraction_rejected (task, stage, reason, raw, "
            "source_url, model) VALUES ($1,$2,$3,$4::jsonb,$5,$6)",
            task, stage, reason,
            json.dumps(raw, ensure_ascii=False) if raw is not None else None,
            source or None, llm.MODEL)
    except Exception as exc:                        # noqa: BLE001
        logger.warning("[%s] extraction_rejected 적재 실패: %s", task, exc)
