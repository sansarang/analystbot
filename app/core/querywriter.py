"""🔴🔴 **LLM 이 질의를 쓰고 매체를 고른다** — 사용자 지시 2026-10-11(②③).

> ② LLM 이 **질의를 쓴다**(현지어 포함) — 던지는 것은 **우리 검색 사슬**이다.
> ③ LLM 이 **어디를 열지 고른다** — 받은 도메인은 **확인 뒤에만** 쓴다.

⚠️ 왜 — 실측 2026-10-11(네 경기): 수확이 전부 0이었고 상류 원인이 *"그 경기 기사를
   애초에 못 집어 온다"* 였다(신원 선필터 탈락 90~134건이 **남의 글**). 그 직접
   원인은 질의가 **영어 한 꼴뿐**이라는 것이다 — `리그 미상`이면 코드가 영어만
   던진다. 일본어 매체(`ゲキサカ`·`サッカーキング`)에 그 소식이 있는데 우리는
   `Shonan Bellmare injury news` 를 던졌다.

🔴🔴 **잠금 넷**
  ① LLM 출력은 **글자(질의·도메인)뿐**이다 — 사실·숫자·판정에 닿지 않는다
     (`QueryPlan` 에 칸이 둘뿐이다).
  ② 던지는 통로는 **기존 사슬**이다(새 엔진·새 fetch 경로를 만들지 않는다) —
     매체는 `site:` 질의로 그 사슬에 들어간다.
  ③ 도메인은 **robots 를 받아 확인한 뒤에만** 쓴다(지어낸 주소 금지 · #4).
  ④ 카드가 **무엇을 던졌는지·무엇을 버렸는지** 적는다(#3).
"""
from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

#: 🔴 ② 한 경기에서 쓸 **질의 수 상한**(예산 안 · `per_subtask.search` 가 3이다)
MAX_QUERIES = 8
#: 🔴 ③ 확인까지 갈 **도메인 수 상한**(robots 를 그만큼만 받는다)
MAX_SITES = 4
#: 🔴 질의 한 개의 글자 상한(문지기가 긴 글을 안 받는다)
MAX_LEN = 90
#: 🔴 문지기 금지 문자 — **값에서 지운다**(문지기를 완화하지 않는다 · §8)
BAD_CHARS = "'\"`·()[]{}<>|\\"
#: 🔴 호스트 꼴 — 점이 있고 끝이 두 글자 이상 글자인 것만
_HOST = re.compile(r"^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$")


class QueryPlan(BaseModel):
    """🔴🔴 ① LLM 이 내는 것 — **글자 목록 둘뿐**이다.

    ⚠️ 수·판정 칸을 넣지 않는다 — 넣는 순간 LLM 출력이 확률에 닿는 길이 열린다.
    """

    queries: list[str] = Field(default_factory=list)
    sites: list[str] = Field(default_factory=list)


def keep(rows: list[str], *, aliases: list[str]) -> tuple[list[str], list[str]]:
    """🔴🔴 ② — 쓸 질의와 **버린 질의**를 가른다. `(쓸 것, 버린 것)`.

    🔴 **팀 이름이 한 글자도 없는 질의는 버린다** — 그것은 그 경기 질의가 아니다
       (모델이 *"오늘 축구 경기 일정"* 같은 것을 준다 · 실측 전에 미리 막는다).
    ⚠️ 금지 문자는 지우고, 공백을 하나로 모으고, 중복·긴 것을 자른다.
    """
    want = [str(a).strip().lower() for a in (aliases or []) if str(a).strip()]
    got: list[str] = []
    bad: list[str] = []
    for raw in (rows or []):
        said = " ".join(str(raw or "").split())
        for ch in BAD_CHARS:
            said = said.replace(ch, " ")
        said = " ".join(said.split())[:MAX_LEN].strip()
        if not said:
            continue
        low = said.lower()
        if not any(a in low for a in want):
            bad.append(f"{said} — 🔴 팀 이름이 없다")
            continue
        if said in got:
            continue
        got.append(said)
    return got[:MAX_QUERIES], bad


def hosts(rows: list[str]) -> tuple[list[str], list[str]]:
    """🔴🔴 ③ — 도메인 꼴만 남긴다. `(호스트, 버린 글)`.

    ⚠️ 모델이 문장(`일본 축구 매체를 보세요`)이나 주소 전체를 준다 — 호스트만
       뽑고 꼴이 아니면 버린다. 🔴 `localhost`·점 없는 글자는 안 받는다.
    """
    got: list[str] = []
    bad: list[str] = []
    for raw in (rows or []):
        said = str(raw or "").strip().lower()
        said = re.sub(r"^https?://", "", said).split("/")[0].strip()
        said = said.strip(".")
        if not said or not _HOST.match(said) or said.endswith(".local"):
            bad.append(f"{str(raw)[:40]} — 🔴 호스트 꼴이 아니다")
            continue
        if said not in got:
            got.append(said)
    return got[:MAX_SITES], bad


async def check_hosts(net, rows: list[str], *, state=None
                      ) -> tuple[list[str], list[str]]:
    """🔴🔴 ③ — **robots 를 받아 확인**한 도메인만 돌려준다. `(쓸 것, 사유)`.

    🔴 지어낸 주소를 쓰지 않는다(#4) — `robots.txt` 가 응답해야 그 호스트가
       **실재**한다고 본다. ⚠️ robots 를 **읽는 것**이 허용 판정까지는 아니다 —
       실제 열기는 기존 `net.get` 이 같은 규칙(§4-7)으로 다시 본다.
    """
    ok: list[str] = []
    said: list[str] = []
    for host in (rows or [])[:MAX_SITES]:
        url = f"https://{host}/robots.txt"
        try:
            page = await net.get(url)
        except Exception as exc:                            # noqa: BLE001
            said.append(f"{host} — 🔴 못 받았다({exc!r:.40})")
            continue
        code = int(getattr(page, "status", 0) or 0)
        if getattr(page, "ok", False) or 200 <= code < 500:
            ok.append(host)
            said.append(f"{host} — ✅ robots {code}")
        else:
            said.append(f"{host} — 🔴 robots {code}")
    if state is not None:
        state.note("③ 매체 확인 — " + " · ".join(said or ["없다"]))
    return ok, said


def site_queries(hosts_ok: list[str], queries: list[str]) -> list[str]:
    """🔴 ③ — 확인된 도메인을 **`site:` 질의**로 기존 사슬에 넣는다.

    🔴 새 fetch 경로를 만들지 않는다 — 통로는 그대로고 질의만 좁힌다.
    """
    out: list[str] = []
    for host in (hosts_ok or []):
        for said in (queries or [])[:2]:
            out.append(f"site:{host} {said}")
    return out[:MAX_QUERIES]


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **대회 유형에 맞춘다** — 사용자 지시 2026-10-15
# ══════════════════════════════════════════════════════════════════
#
#  > 딥서치·llm 서치할 때 **대륙경기, 그에 맞게 서치해야 한다** · 변수 관련
#  > 모든 사항도 **그 경기에 맞게** 해야 한다
#
#  🔴 유형은 **표가 든다**(`competition.row_of(key)["kind"]`) — 여기서 짓지
#     않는다. `club_continental`(UCL·ACLE·ACL2)이면 리그와 **다른 것을** 찾아야
#     한다: 두 나라 말 · 조별 순위·진출 · 주중 일정과 리그 로테이션 ·
#     장거리 이동·시차.
#  ⚠️ 고치는 것은 **글(프롬프트)뿐**이다 — 질의 문지기·변수 경로는 그대로다.


def comp_hint(ref: object) -> str:
    """🔴 그 대회 유형에 맞춘 **한 토막 지시문**. 못 알아보면 빈 글자다."""
    from app.core import competition as _c
    key, _why = _c.key_of(competition=str(getattr(ref, "competition", "") or ""))
    kind = str(dict(_c.row_of(key) if key else {}).get("kind") or "")
    if kind == "club_continental":
        return ("🔴🔴 **대륙 대회다**(`club_continental`) — 리그와 다른 것을 "
                "찾는다/본다:\n"
                "   · **두 팀 나라 말 둘 다**로 찾는다(상대 나라 매체가 그 팀을 "
                "더 자세히 쓴다)\n"
                "   · **조별 순위·진출 상황**(몇 점이 필요한가 · 탈락·확정)\n"
                "   · **주중 경기다** — 리그 경기와 겹쳐 **로테이션**이 크다"
                "(주말 리그를 위해 주전을 뺀다)\n"
                "   · **장거리 이동·시차**(나라를 넘는다) · 원정 명단 제한\n"
                "   · 득점·실점 기준은 **그 대회 것**이다 — 리그 수치와 섞지 "
                "않는다\n")
    if kind == "domestic_league":
        return ("🔴 **리그다**(`domestic_league`) — 순위·승점·강등·플레이오프 "
                "경쟁과 **주말 일정**을 본다(대륙 대회 일정과 섞지 않는다).\n")
    if kind.startswith("national"):
        return ("🔴 **대표팀 경기다** — 소집·차출·장거리 이동과 **클럽 일정**을 "
                "본다(리그 순위는 뜻이 없다).\n")
    return ""
#  ⚠️ `said_of`(질의 쓰기의 **사유 한 줄**)도 같이 지웠다 — `ask` 만 부르던
#     것이고, LLM 서치는 자기 사유를 스스로 적는다(`s4b_gapsearch.ask`).

# ══════════════════════════════════════════════════════════════════════
# 🔴🔴 **`ask` 를 지웠다 — 딥서치의 LLM 질의였다**(사용자 지시 2026-10-17)
# ══════════════════════════════════════════════════════════════════════
#
#  ⚠️ 이 함수는 ②③ 딥서치가 쓰던 **질의 쓰기**다(`s3_docs._llm_queries`).
#     딥서치를 지우자 **부르는 곳이 0** 이 됐다 — 안 이은 코드는 없는 코드보다
#     나쁘다(#2). 🔴 LLM 질의 쓰기는 이제 **`s4b_gapsearch.ask` 하나**다.
#  🔴 남은 것은 **글자 검사와 통신**이다 — `keep`(팀 표기)·`hosts`(호스트 꼴)·
#     `check_hosts`(robots)·`site_queries`(`site:`)·`comp_hint`(대회 유형).
#     ⑤-b3 2단과 LLM 서치가 그것들을 쓴다.





