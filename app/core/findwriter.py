"""🔴🔴 **경기 찾기 — LLM 은 이름 후보만 댄다** — 사용자 지시 2026-10-11(3번).

> 라인업 확인하는것도 llm 한번 호출로 찾게하는것도 검토해라..(경기 찾는것도)

⚠️ 왜 — 2026-10-11 하루에 **네 번** 경기를 못 찾았다:
    `openworld_not_found` (미토+이와키 · 쇼난+니가타) ·
    `match_not_found`     (미토 — 창 안 2경기라 안 골랐다) ·
    한글 `위트레흐트` 가 이름표에 없어 검색으로 빠졌다.
   넷 다 **이름 문제**다(한글 짧은 이름·J2 미등록 클럽).

🔴🔴 **잠금 넷**(`querywriter` 와 같은 선)
  ① LLM 출력은 **글자뿐**이다(팀 이름·슬러그·매체) — 수·판정 칸이 없다.
  ② **팀 색인에서 확인된 글자만** 쓴다 — 지어낸 슬러그는 색인에 없으니 자동으로
     버려진다(#4: 추측이 결과에 못 들어간다).
  ③ 색인 사다리가 **먼저** 돈다 — LLM 은 그것이 **실패한 뒤에만** 부른다(비용).
  ④ 카드·기록이 **후보 N개 중 확인 M개**를 적는다(#3).

🔴 **라인업 값은 묻지 않는다.** LLM 은 웹이 없어서(`llm._body`: *"tools 는 없다"*)
   오늘 선발을 물으면 **지어낸다** — 절대규칙 5·#4 위반이다. 그래서 이 파일은
   *"어느 팀·어느 주소"* 만 받고, 명단은 **받아 온 쪽에서만** 읽는다.
"""
from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

#: 🔴 LLM 에게 받을 **팀 이름 후보** 수 상한
MAX_TEAMS = 6
#: 🔴 **슬러그 후보** 수 상한
MAX_SLUGS = 6
#: 🔴 슬러그 꼴 — 소문자·숫자·붙임표만(주소·대문자·공백은 버린다)
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{2,}$")


class TeamGuess(BaseModel):
    """🔴🔴 ① LLM 이 내는 것 — **글자 목록 셋뿐**이다."""

    teams: list[str] = Field(default_factory=list)
    slugs: list[str] = Field(default_factory=list)
    sites: list[str] = Field(default_factory=list)


def keep_slugs(rows: list[str]) -> tuple[list[str], list[str]]:
    """🔴 슬러그 꼴만 남긴다. `(쓸 것, 버린 글)`."""
    got: list[str] = []
    bad: list[str] = []
    for raw in (rows or []):
        said = str(raw or "").strip()
        if not said or not _SLUG.match(said):
            bad.append(f"{said[:40] or '빈 글자'} — 🔴 슬러그 꼴이 아니다")
            continue
        if said not in got:
            got.append(said)
    return got[:MAX_SLUGS], bad


def keep_teams(rows: list[str]) -> tuple[list[str], list[str]]:
    """🔴 팀 이름 후보를 다듬는다. `(쓸 것, 버린 글)`."""
    got: list[str] = []
    bad: list[str] = []
    for raw in (rows or []):
        said = " ".join(str(raw or "").split())
        if not said:
            continue
        if "://" in said or said.lower().startswith("http"):
            bad.append(f"{said[:40]} — 🔴 주소다(이름이 아니다)")
            continue
        if said not in got:
            got.append(said)
    return got[:MAX_TEAMS], bad


def confirm(idx: dict, *, names: list[str], slugs: list[str]
            ) -> tuple[list[tuple[str, str]], str]:
    """🔴🔴 ② — **팀 색인에서 확인**한다. `([(팀 번호, 슬러그)…], 사유)`.

    🔴 확인은 `discover._slug_hit` 하나가 한다(사본 금지) — 이름은 그 함수가
       별칭표로 맞추고, 슬러그는 색인 값과 **글자 그대로** 견준다.
    ⚠️ 하나도 못 걸리면 **빈 목록**이다 — 지어낸 글자는 여기서 전부 죽는다.
    """
    from app.core import discover as _d
    out: list[tuple[str, str]] = []
    said: list[str] = []
    for nm in (names or []):
        hit = _d._slug_hit(dict(idx or {}), str(nm))
        if hit:
            out.append(hit[0])
            said.append(f"이름 `{nm}` → `{hit[0][1]}`")
        else:
            said.append(f"이름 `{nm}` — 🔴 색인에 없다(버렸다)")
    want = {str(v): str(k) for k, v in dict(idx or {}).items()}
    for slug in (slugs or []):
        tid = want.get(str(slug))
        if tid:
            got = (tid, str(slug))
            if got not in out:
                out.append(got)
            said.append(f"슬러그 `{slug}` → 팀 {tid}")
        else:
            said.append(f"슬러그 `{slug}` — 🔴 색인에 없다(버렸다)")
    return list(dict.fromkeys(out)), " · ".join(said or ["후보가 없다"])


def ask(asked: str, *, state, day: str = "", aliases: list[str] | None = None
        ) -> TeamGuess | None:
    """🔴🔴 LLM **1회** — 그 질문 글자로 **팀 이름·슬러그·매체 후보**를 받는다.

    ⚠️ 실패하면 `None` 이고 지금 사다리가 그대로 돈다(퇴로가 있다).
    ⚠️ **재생(카세트)에서는 부르지 않는다** — 녹음이 그 질문을 모른다(부르는 쪽이
       그 검사를 한다).
    """
    from app.core import llm
    said_alias = " · ".join(str(a) for a in (aliases or [])[:8])
    msgs = [
        llm.Message(role="system", content=(
            "너는 팀 이름을 정규화하는 사람이다. **경기 결과·라인업·순위를 "
            "말하지 않는다** — 네가 내는 것은 **이름 글자**뿐이다. "
            "모르면 빈 목록으로 둔다(지어내지 않는다).")),
        llm.Message(role="user", content=(
            f"사용자가 이렇게 물었다: `{asked}`\n"
            + (f"우리가 아는 표기: {said_alias}\n" if said_alias else "")
            + (f"날짜: {day}\n" if day else "")
            + "\n🔴 `teams` — 그 팀의 **정식 이름 후보**(영어 · 현지어 둘 다 · "
              f"{MAX_TEAMS}개 이하).\n"
              "🔴 `slugs` — fotmob 팀 주소에 쓰이는 **슬러그 후보**"
              "(`fc-utrecht` 꼴 · 소문자·붙임표 · 주소 전체 금지 · "
              f"{MAX_SLUGS}개 이하).\n"
              "🔴 `sites` — 그 리그 소식이 실리는 매체 도메인(모르면 빈 목록).\n"
              "⚠️ 상대 팀·스코어·날짜를 **추측해 적지 않는다**.")),
    ]
    # 🔴🔴 **① 의 이름 풀이는 solar 다** — 사용자 지시 2026-10-15.
    #    ⚠️ 실측 2026-10-15: deepseek 가 "Say OK" 3토막 요청에도 **59.3초 읽기
    #       타임아웃**이었고(solar 는 0.5초) 그 멈춤이 ① 에서 13분을 태웠다.
    #       그 바람에 카드 예산이 말라 **멀쩡한 solar 호출까지** 못 나갔다.
    got = llm.ask(provider="solar", purpose="query", messages=msgs,
                  out=TeamGuess, state=state)
    if isinstance(got, TeamGuess):
        return got
    state.note(f"3번 경기 찾기 — 🔴 LLM 실패({getattr(got, 'reason', '?')}) "
               f"— 지금 사다리로만 간다")
    return None


def said_of(*, teams: list[str], slugs: list[str],
            ok: list, bad: list[str]) -> str:
    """🔴 #3 — **후보 N개 중 확인 M개**(카드·기록이 적는다)."""
    n = len(teams or []) + len(slugs or [])
    return (f"후보 {n}개(이름 {len(teams or [])} · 슬러그 {len(slugs or [])})"
            f" → **확인 {len(ok or [])}개**"
            + (f"({', '.join(str(x[1]) for x in ok[:3])})" if ok else "")
            + (f" · 버린 글 {len(bad or [])}개" if bad else ""))
