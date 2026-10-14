"""🔴🔴 **딥서치가 못 찾으면 LLM 이 찾는다** — 사용자 지시 2026-10-14.

> 3번(감독 이름), 4번(감독 부임후 성적), 5번(팀내 불화)은 딥서치에서 못 찾으면
> **llm 이 찾게 한다** — 그래서 llm 을 전략예측 **및 서치**로 쓰는 거다.

## 🔴🔴 이것은 새 종류의 LLM 호출이다 — 그 사실을 적어 둔다
지금까지 LLM 이 낸 것은 **글자**(질의·팀 이름·철자)와 **문서에서 뽑은 사실**
뿐이었다. 이 파일은 **문서 없이 모델의 기억**을 받는다. 그래서:

🔴 **원천을 `🔴 LLM 기억` 으로 박아 들고 다닌다** — 카드가 그 글자를 그대로
   보이고, 사람이 *"이건 검증 안 됐다"* 를 한눈에 가린다.
🔴 **확률·등급에 못 닿는다**(사용자 결정 2026-10-14: *"안 된다 — 쓰기만 한다"*).
   계약 `test_v29_2_recall.py` 가 확률 경로에서 이 모듈을 부르면 빨개진다.
🔴 **딥서치가 찾은 것이 있으면 안 묻는다**(순서가 뜻이다) — 문서 있는 사실이
   모델 기억보다 **늘** 세다.
⚠️ 모델이 *"모른다"* 를 낼 수 있게 **빈 글자를 허용**한다. 지어내게 몰지 않는다
   (프롬프트가 그렇게 적는다).

## 세 칸
| 칸 | 딥서치 경로 | 여기서 묻는 것 |
|---|---|---|
| 감독 이름 | 경기 페이지 `isCoach` | 그 경기 두 팀 감독 이름 |
| 부임 후 성적 | 🔴 **통로 없음** | 부임일·`W-D-L`·경기 수 |
| 팀내 불화 | 하위 B(`coach_conflict`) | 최근 갈등·이탈 한 줄 |
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.core.schema import Coach, MatchRef
from app.core.state import RunState

logger = logging.getLogger(__name__)

#: 🔴🔴 **원천 글자** — 이 글자가 확률 경로에 나타나면 계약이 빨개진다
SRC = "🔴 LLM 기억"

#: 🔴 그 경기 **감독 이름은 둘뿐**이라 열거로 못 막는다(모델이 내는 값이다) —
#   대신 **글자 길이**로 막는다(문장을 이름 칸에 넣는 것을 거른다)
NAME_MAX = 40
#: 🔴 불화 한 줄 상한 — 길면 서술이 된다(사실 한 줄만 받는다)
NOTE_MAX = 200


class _CoachOut(BaseModel):
    """🔴 모델이 내는 꼴. ⚠️ 모르면 **빈 글자**다(지어내지 말라고 적는다)."""

    team: str = Field(default="")
    name: str = Field(default="")
    since: str = Field(default="")
    record: str = Field(default="")
    games: int | None = Field(default=None)
    conflict: str = Field(default="")


class _RecallOut(BaseModel):
    rows: list[_CoachOut] = Field(default_factory=list)


def _system(ref: MatchRef) -> str:
    """🔴 프롬프트 — **모르면 빈 글자**를 분명히 허락한다."""
    return (
        "너는 축구 자료 정리원이다. 아래 경기의 두 팀에 대해 **아는 것만** 적어라.\n"
        f"경기: {ref.home_name or ref.home} vs {ref.away_name or ref.away}"
        f" · 대회 {ref.competition}\n\n"
        "칸:\n"
        "- team: 팀 이름(위 둘 중 하나를 그대로)\n"
        "- name: 지금 감독 이름\n"
        "- since: 부임 시점(`2024-08` 꼴 · 모르면 빈 글자)\n"
        "- record: 부임 후 성적 `승-무-패` 꼴(예 `12-5-7`)\n"
        "- games: 부임 후 경기 수(정수)\n"
        "- conflict: 최근 팀내 불화·이탈이 **있었으면** 한 줄, 없거나 모르면 빈 글자\n\n"
        "🔴 규칙\n"
        "1. **모르는 칸은 빈 글자로 둔다.** 추측해서 채우지 마라 — 빈 칸이 틀린 "
        "   답보다 낫다.\n"
        "2. 숫자를 **만들지 마라.** 성적이 기억나지 않으면 `record` 와 `games` 를 "
        "   비워라.\n"
        "3. 불화는 **보도된 일**만 적는다. 추정·소문·분위기는 적지 않는다.\n"
        "4. 설명하지 마라 — 칸만 채운다.\n")


def need(facts, *, keys: list[str]) -> dict[str, list[str]]:
    """🔴🔴 **무엇이 비었나** — 팀마다 못 받은 칸 이름. 전부 찼으면 빈 표다.

    🔴 이 함수가 *"딥서치가 못 찾았다"* 의 **단일 판정**이다 — 부르는 쪽이
       조건을 다시 쓰지 않는다(사본 금지).
    """
    out: dict[str, list[str]] = {}
    box = dict(getattr(facts, "coach", None) or {})
    for key in keys:
        one = box.get(key)
        miss = []
        if one is None or not str(getattr(one, "name", "") or ""):
            miss.append("감독 이름")
        elif not str(getattr(one, "record", "") or ""):
            miss.append("부임 후 성적")
        if miss:
            out[key] = miss
    return out


def run(ref: MatchRef, facts, *, state: RunState, keys: list[str],
        conflict_docs: int = 0) -> tuple[dict, str]:
    """🔴🔴 빈 칸을 **LLM 기억**으로 메운다. `({팀: Coach}, 사유)`.

    🔴 딥서치가 찾은 칸은 **덮지 않는다** — `need` 가 빈 칸만 고른다.
    ⚠️ 호출은 경기당 **한 번**이다(두 팀을 한 요청에 묻는다).
    """
    from app.core import llm
    from app.core.schema import LlmFail
    want = need(facts, keys=keys)
    if not want and conflict_docs:
        return {}, "✅ 딥서치가 다 찾았다 — LLM 에 안 물었다"
    said = llm.ask(
        provider="deepseek", purpose="recall", out=_RecallOut, state=state,
        enums={"team": [str(x) for x in keys]},
        messages=[llm.Message(role="system", content=_system(ref)),
                  llm.Message(role="user",
                              content="위 틀대로 두 팀을 각각 한 줄씩 채워라.")])
    if isinstance(said, LlmFail):
        why = f"🔴 LLM 회상 실패 — {getattr(said, 'why', '') or said!r}"
        state.note(f"s4b 회상 — {why}")
        return {}, why
    got: dict[str, Coach] = {}
    notes: list[str] = []
    bad = 0
    for row in (said.rows or []):
        key = str(row.team or "").strip()
        if key not in set(keys):
            bad += 1
            continue
        name = str(row.name or "").strip()
        if len(name) > NAME_MAX:
            bad += 1
            name = ""
        old = dict(getattr(facts, "coach", None) or {}).get(key)
        # 🔴 딥서치가 이름을 이미 받았으면 **그것을 지킨다**(LLM 이 덮지 않는다)
        keep = str(getattr(old, "name", "") or "")
        got[key] = Coach(
            name=keep or name,
            since=str(getattr(old, "since", "") or "") or str(row.since or "").strip(),
            interim=bool(getattr(old, "interim", False)),
            record=str(getattr(old, "record", "") or "")
            or str(row.record or "").strip(),
            games=(getattr(old, "games", None)
                   if getattr(old, "games", None) is not None else row.games),
            source=(str(getattr(old, "source", "") or "") if keep else SRC))
        note = str(row.conflict or "").strip()[:NOTE_MAX]
        if note:
            notes.append(f"{key} — {note} · 원천 {SRC}")
    why = (f"LLM 회상 — 빈 칸 {want or '없다'}"
           + (f" · 받은 팀 {len(got)}" if got else " · 🔴 받은 줄 0")
           + (f" · 🔴 버린 줄 {bad}(팀 이름·길이)" if bad else "")
           + (f" · 불화 {len(notes)}건" if notes
              else " · 불화 ⬜ 0건(모델도 모른다고 했다)")
           + f" · 🔴 원천 `{SRC}` — **확률·등급에 안 쓴다**")
    state.note(f"s4b 회상 — {why}")
    return {"coach": got, "conflict": notes}, why
