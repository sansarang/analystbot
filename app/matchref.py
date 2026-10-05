"""🔴🔴 **입구 — 이름을 ID 로 바꾸는 곳은 여기 하나다**(2단계 · 사용자 설계 2026-10-03).

══════════════════════════════════════════════════════════════════
🔴 병의 정체 — *"이름을 신원으로 쓴다"*
══════════════════════════════════════════════════════════════════

> 단계를 넘어갈 때마다 **이름을 다시 비교**하고, 비교하는 쪽과 저장한 쪽의 언어가
> 다르면 자기가 찾은 걸 버린다.

| 실측 2026-10-03 | 저장 | 재조회 | 결과 |
|---|---|---|---|
| J리그 | `柏レイソル` | `가시와 레이솔` | 찾은 페이지 **폐기** |
| 자동완성 | `크로아티아` | `Croatia` | 정확한 경기를 집고도 **폐기** |
| `slate.find` | `Croatia` | `크로아티아` | *"창 밖"* 이라는 **거짓 사유** |

🔴 **고치는 법**: 입구에서 **단 한 번** 이름을 ID 로 바꾸고, 그 뒤로는 ID 만 쓴다.

══════════════════════════════════════════════════════════════════
🔴 열쇠를 새로 만들지 않는다
══════════════════════════════════════════════════════════════════

사용자 설계가 `key = "fotmob:5181853"` 을 들었는데, 이 저장소에는 **이미 그 열쇠가
있다**: `games.ext_id`(`fotmob-5181853`)이고 `UNIQUE(sport, ext_id)` 로 묶여 있다.
⚠️ 비슷한 열쇠를 하나 더 만들면 **둘을 맞추는 코드**가 또 생기고, 그것이 지금
   고치려는 병의 모양이다. 🔴 **그 열쇠를 쓴다**(사본 금지).

팀 열쇠는 1단계의 `teamref` 다(`tsdb:137708` · `iso:HR` · `name:KBO:lgtwins`).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **사유는 `app/reasons.py` 하나다** — v5 §8-6 (2026-10-04)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 종전에는 이 파일이 `Reason` enum 과 `SAY` 표를 **직접** 들고 있었다(일곱).
#     §8-6 은 **전 구간**(검색·읽기·검증·판정·예산)의 사유를 하나의 표로 요구하고,
#     계약(`tests/test_reason.py::test_사유를_쓰는_곳이_한_모듈이다`)이
#     *"`Reason` 이 여러 파일에 복제되면 그 순간 뜻이 갈린다"* 고 못 박았다.
#
#  🔴 그래서 정의를 `app/reasons.py` 로 옮기고 여기서는 **가져다 쓴다.**
#     ⚠️ 이 파일의 `say()` 는 남는다 — 입구에서만 하는 일(④ 후보 제시)이 있다.
#  🔴 입구 전용 문구(스케줄러 미실행·날짜 창 등)는 `reasons.SAY` 로 **옮겼다** —
#     두 표가 같은 사유를 다른 말로 하면 그것이 또 거짓 사유다.
from app.reasons import SAY, Reason

__all__ = ["SAY", "Lookup", "MatchRef", "Reason", "ref_from_row", "say"]


def say(reason: Reason, *, asked: str = "") -> str:
    """🔴 그 사유를 사용자 말로. ⚠️ **여기 없는 사유는 조용히 넘기지 않는다.**

    🔴 `asked` 를 주면 **후보를 얹는다**(④) — *"맨시티를 못 찾았다.
       `Manchester City FC`?"* ⚠️ **고르지는 않는다.** 그럴듯한 후보를 자동으로
       채택하는 것이 *"거짓 사유"* 의 반대 방향 실수다(사용자 지적 2026-10-04).
    ⚠️ 문장 자체는 `reasons.SAY` 가 든다 — 여기서 짓지 않는다(§8-6).
    """
    got = SAY.get(reason)
    if got is None:
        logger.warning("[matchref] 사용자 문장이 없는 사유: %r", reason)
        return f"🔴 못 했다 — `{getattr(reason, 'value', reason)}`"
    if reason is Reason.NAME_UNRESOLVED and asked:
        from app import teamref
        near = teamref.suggest(asked)
        if near:
            got += ("\n   혹시 이것인가 — "
                    + " · ".join(f"`{x}`" for x in near)
                    + " ⚠️ **고르지 않았다**. 맞으면 그 이름으로 다시 물어라")
    return got


@dataclass(frozen=True)
class MatchRef:
    """🔴 **경기 하나의 신원.** 이 뒤로는 이름으로 비교하지 않는다.

    ⚠️ `frozen` 이다 — 중간 단계가 슬그머니 고치면 그 자체가 이 병의 재발이다.
    """

    #: 🔴 `games.ext_id` 다(`fotmob-5181853`). **새 열쇠를 만들지 않는다.**
    key: str
    #: `games.id` — 표를 다시 뒤지지 않게 들고 간다
    game_id: int | None = None
    home: str = ""
    away: str = ""
    #: 🔴 `teamref` 열쇠(`tsdb:137708`·`iso:HR`). 이름이 아니라 **이것**이 신원이다
    home_id: str = ""
    away_id: str = ""
    #: 🔴 **UTC 만** 들고 다닌다. KST 는 **출력할 때만**(절대규칙 2)
    kickoff_utc: datetime | None = None
    #: 그 경기가 속한 대회(`League Cup`) — ⚠️ 리그가 아니다
    competition: str = ""
    #: 리그 명부 열쇠(`J리그`) — 언어·어댑터가 여기서 나온다
    league: str = ""
    sport: str = ""
    venue: str = ""
    status: str = ""
    #: 그 리그 언어의 현지 표기(`柏レイソル`) — 검색어가 여기서 나온다
    home_local: str = ""
    away_local: str = ""


@dataclass
class Lookup:
    """입구가 돌려주는 것. 🔴 **찾았거나, 왜 못 찾았나**."""

    ref: MatchRef | None = None
    reason: Reason = Reason.OK
    #: 사람이 읽을 사유들 — 🔴 **enum 을 대신하지 않는다**(곁들이는 설명이다)
    steps: list[str] = field(default_factory=list)
    #: 여럿이 맞을 때의 후보들(§17-g-3 — 고르는 것은 사용자다)
    candidates: list[dict] = field(default_factory=list)
    #: 🔴🔴 **그 경기 기사의 언어** — 사다리가 정한 것을 하류로 **그대로** 내린다.
    #
    #  ⚠️ 종전에 하류(`searchcells`·`queries`)가 `langs_for(league, team)` 로 **다시
    #     계산**했다. 대표팀은 리그가 없어 그것이 `('en',)` 로 떨어지고, 그래서
    #     북마케도니아 질의가 전부 영어였다(실측 2026-10-04: 카탈로그 템플릿 6종이
    #     *"템플릿 언어 ko 가 이 경기 언어 ['en'] 에 없다"* 로 건너뛰었다).
    #  🔴 사다리 ②가 Babel CLDR 로 `mk` 를 안다 — **그것을 싣고 간다.**
    #     같은 사실을 두 곳에서 계산하면 한쪽이 늘 한 발 늦는다(#1 사본 금지).
    langs: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.ref is not None and self.reason is Reason.OK


def _utc(v) -> datetime | None:
    """🔴 **tz 를 잃지 않는다**(절대규칙 2). 시간대 없는 값은 **안 받는다**."""
    if not isinstance(v, datetime):
        return None
    if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
        logger.warning("[matchref] 시간대 없는 값이 왔다: %r — 쓰지 않는다", v)
        return None
    from datetime import timezone
    return v.astimezone(timezone.utc)


def ref_from_row(row: dict, *, league: str = "", home_local: str = "",
                 away_local: str = "") -> MatchRef:
    """🔴 `games` 표의 행 하나 → `MatchRef`. **여기서만** 행을 ref 로 바꾼다.

    ⚠️ 여러 곳에서 각자 바꾸면 한 곳이 칸을 빠뜨려도 안 보인다(사본 금지).
    """
    from app import teamref
    home, away = str(row.get("home") or ""), str(row.get("away") or "")
    hk, _ = teamref.key_of(home)
    ak, _ = teamref.key_of(away)
    return MatchRef(
        key=str(row.get("ext_id") or ""),
        game_id=(int(row["id"]) if row.get("id") is not None else None),
        home=home, away=away, home_id=hk, away_id=ak,
        kickoff_utc=_utc(row.get("starts_kst") or row.get("starts_utc")),
        competition=str(row.get("league") or ""),
        league=league,
        sport=str(row.get("sport") or ""),
        venue=str(row.get("venue") or ""),
        status=str(row.get("status") or ""),
        home_local=home_local, away_local=away_local)
