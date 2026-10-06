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
    """🔴🔴 **Ollama 추출을 지웠다** — 사용자 지시 2026-10-06(2차) ⑤.

    > v6 가 안 쓰는 옛 LLM 경로(… Ollama 경로)는 **v6 가 안 부르는 게 확인되면 삭제.**

    🔴 실측 2026-10-06: s1~s7 에 염탐을 걸어 재생으로 돌렸더니 `app.llm.call` 호출이
       **0건**이었다. 그래서 그 호출 함수를 지웠고, 이 함수는 **사유를 남기고 빈손**
       으로 돌아간다(#3 조용한 0 금지 — 조용히 `[]` 를 내지 않는다).
    ⚠️ 추출은 이제 v6 `app/core/stages/s4_extract.py` 가 한다(Solar 구조화 출력 1회).
    """
    said = ("🔴 옛 Ollama 추출 경로를 지웠다(2026-10-06 ⑤) — "
            "추출은 v6 `s4_extract` 가 한다")
    logger.info("[extract] %s · task=%s", said, task)
    return [], [said]


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
