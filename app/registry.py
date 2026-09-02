"""[설계 규율 · 2026-09-02] **배당 소스와 잡의 단일 정의처.**

🔴 왜 이 파일이 있는가 — 오탐 4건이 전부 "사본이 원본과 어긋남"이었다:
     `W-JOB-LATE mlb_pregame_5m`     워치독이 적은 "주기 5분" vs 실제 cron(5-11시)
     `W-JOB-LATE research_retry_45m` 재기동 개념 누락
     `W-ODDS-STALE betman`           미구현 소스를 감시 목록에 등재
     `W-ODDS-STALE espn`             `due` 를 전 종목 합산으로 셈
   담당 리그·활성 여부를 **여기 한 곳에만** 두고 워치독·수집기·일일요약이
   전부 이걸 읽는다. 사본이 없으면 어긋날 것도 없다.

⚠️ 잡의 **주기는 여기 적지 않는다.** 트리거 객체(`scheduler._JOB_TRIGGERS`)가
   원본이다 — cron 창이든 인터벌이든 그쪽이 정답을 안다. 여기 옮겨 적으면
   그 순간 다시 사본이 된다.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OddsProvider:
    """배당 소스 하나. **담당 리그가 곧 감시 범위다.**"""

    name: str
    sports: tuple[str, ...]          # 이 소스가 실제로 커버하는 종목
    label: str
    #: 수집기가 붙어 실제로 적재되는가. False면 감시하지 않는다 —
    #  끄거나 미구현인 것을 고장이라 울리는 것이 오탐의 최대 원인이다.
    wired: bool = True
    #: 키가 있어야 도는 소스. 키가 없으면 활성에서 자동으로 빠진다.
    key_setting: str = ""
    note: str = ""


#: 배당 소스 전수. 여기 없는 이름은 시스템에 존재하지 않는 소스다.
ODDS_PROVIDERS: tuple[OddsProvider, ...] = (
    OddsProvider("espn", ("mlb",), "ESPN Core API",
                 note="무인증·무제한. MLB 1순위"),
    OddsProvider("sharp", ("mlb",), "SharpAPI 무료 티어",
                 key_setting="sharpapi_key",
                 note="MLB 2순위 폴백. 키가 없으면 자동 비활성"),
    OddsProvider("oddsportal", ("kbo", "npb"), "oddsportal 크롤",
                 note="KBO·NPB. 리그당 1요청·10분 최소 간격"),
    OddsProvider("betman", ("kbo", "npb"), "배트맨 프로토", wired=False,
                 note="엔드포인트가 전부 '페이지 오류' — 수집기 미배선"),
    OddsProvider("theodds", ("mlb", "kbo", "npb"), "The Odds API (유료)",
                 wired=False,
                 note="ODDS_PROVIDER=theodds 일 때만. 코드 보존·기본 비활성"),
)

_BY_NAME = {p.name: p for p in ODDS_PROVIDERS}


def provider(name: str) -> OddsProvider | None:
    return _BY_NAME.get(name)


def active_providers(settings=None) -> tuple[OddsProvider, ...]:
    """지금 **실제로 돌고 있어야 하는** 소스들.

    ⚠️ 워치독의 감시 범위가 이 함수 하나로 정해진다. 미배선·키 없음·
       유료 모드 여부를 여기서 한 번에 판단한다.
    """
    from app.config import get_settings

    s = settings or get_settings()
    paid = (getattr(s, "odds_provider", "free") or "free").lower() == "theodds"
    out = []
    for p in ODDS_PROVIDERS:
        if paid:
            if p.name == "theodds":
                out.append(p)
            continue
        if p.name == "theodds" or not p.wired:
            continue
        if p.key_setting and not (getattr(s, p.key_setting, "") or "").strip():
            continue          # 키가 없으면 안 도는 게 정상이다
        out.append(p)
    return tuple(out)


def sports_of(name: str) -> tuple[str, ...]:
    p = _BY_NAME.get(name)
    return p.sports if p else ()


def watched_sports(settings=None) -> tuple[str, ...]:
    """활성 소스들이 커버하는 종목 합집합."""
    out: list[str] = []
    for p in active_providers(settings):
        for sp in p.sports:
            if sp not in out:
                out.append(sp)
    return tuple(out)


#: 워치독이 지연을 볼 잡과 **유예(분)**. 주기는 적지 않는다 —
#  다음 실행 시각은 `scheduler._JOB_TRIGGERS` 에서 계산한다.
@dataclass(frozen=True)
class WatchedJob:
    job_id: str
    grace_min: int
    why: str = ""


WATCHED_JOBS: tuple[WatchedJob, ...] = (
    WatchedJob("heartbeat_2m", 4, "스케줄러 생존 신호"),
    WatchedJob("mlb_pregame_5m", 10, "MLB 아침 발송 (cron 05~11시)"),
    WatchedJob("asia_pregame_5m", 10, "KBO 저녁 폴링"),
    WatchedJob("npb_pregame_2m", 6, "NPB 공시~T-10 창이 좁다"),
    WatchedJob("odds_snapshot_30m", 35, "배당 수집"),
    WatchedJob("lineup_poll_30m", 35, "라인업 폴링"),
    WatchedJob("research_retry_45m", 50, "리서치 재시도 큐"),
)

JOB_GRACE = {j.job_id: j.grace_min for j in WATCHED_JOBS}
