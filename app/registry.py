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


# ══════════════════ 정찰(Scout) 종목 정의 — C0 2026-09-04 ══════════════════
#
# 🔴 **종목 이름을 코드에 다시 적지 않는다.** 정찰·카나리아·워치독이 전부
#    이 표만 읽는다. 종목을 늘리려면 여기 한 줄을 더하면 되고, 코드는 손대지
#    않는다 (테스트가 가짜 종목 주입으로 그걸 증명한다).
#
# ⚠️ 이 표는 "무엇을 정찰하는가"이지 "어떻게 판정하는가"가 아니다.
#    판정 프롬프트·게이트·클립·트리거는 이 파일과 무관하다.


@dataclass(frozen=True)
class ScoutSport:
    """한 종목의 정찰 정의.

    `active=False` 면 정찰이 **기록만** 하고 카드·딥서치에 연결하지 않는다.
    끄는 이유를 `reason` 에 남긴다 — 이유 없는 비활성은 다음 사람이 켜 본다.
    """

    sport: str
    #: 뉴스 소스. `rss` 는 무료 상시, `xsearch` 는 조건부(캡 있음).
    news_sources: tuple[str, ...] = ("rss",)
    #: 라인업이 오는 경로. 종목마다 다르다 — 여기가 원본이다.
    lineup_source: str = ""
    #: 정찰을 시작하는 시각(시작 몇 시간 전) · 보고 카드 시각(분 전).
    scout_open_h: float = 4.0
    report_at_min: int = 120
    #: 카드·딥서치에 연결하는가. False 면 기록만 한다.
    active: bool = True
    reason: str = ""


#: 정찰 대상 전수. 배당 provider 는 `ODDS_PROVIDERS` 가 원본이라 **여기 적지
#  않는다** — `odds_provider_for()` 로 조회한다(사본 금지).
SCOUT_SPORTS: tuple[ScoutSport, ...] = (
    ScoutSport("kbo", ("rss", "xsearch"), lineup_source="naver_kbo"),
    ScoutSport("npb", ("rss", "xsearch"), lineup_source="yahoo_npb"),
    ScoutSport("mlb", ("rss", "xsearch"), lineup_source="statsapi"),
    # ⚠️ 축구는 **정찰 기록만** 한다. 카드·딥서치에 연결하지 않는다.
    #    이유: `soccer_trial` 경로가 야구와 달리 실전 검증을 못 거쳤고,
    #    라인업 공시 리드타임·소스 신뢰도 실측이 없다. 검증 없는 신호를
    #    카드에 실으면 그 카드의 다른 숫자까지 못 믿게 된다.
    #    → 켜기 전에 필요한 것: 라인업 소스 확정 + 리드타임 실측 표본.
    ScoutSport("soccer", ("rss",), lineup_source="", active=False,
               reason="파이프라인 미검증 — 라인업 소스·리드타임 실측 없음"),
)

_SCOUT_BY_SPORT = {x.sport: x for x in SCOUT_SPORTS}


def scout_sport(sport: str) -> ScoutSport | None:
    """그 종목의 정찰 정의. 없으면 None — 정찰 대상이 아니다."""
    return _SCOUT_BY_SPORT.get((sport or "").lower())


def scout_sports(*, active_only: bool = False) -> tuple[ScoutSport, ...]:
    """정찰 대상 목록. `active_only` 면 카드·딥서치 연결분만."""
    return tuple(x for x in SCOUT_SPORTS if x.active or not active_only)


def odds_provider_for(sport: str, settings=None) -> str | None:
    """그 종목 담당 **활성** 배당 소스. `ODDS_PROVIDERS` 가 원본이다."""
    for p in active_providers(settings):
        if sport in p.sports:
            return p.name
    return None


def uses_source(sport: str, name: str) -> bool:
    """그 종목이 이 뉴스 소스를 쓰는가. 문자열 비교를 호출부에 흩지 않는다."""
    sc = scout_sport(sport)
    return bool(sc and name in sc.news_sources)


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


# ── [상황 변수 2026-09-06] 팀의 공기 ────────────────────────────────
# 🔴 **여기가 원본이다.** 코드에는 종목 분기를 두지 않는다 — 수집기·분류기는
#    `situation_axes(sport)` 만 부르고, 종목별 차이는 이 표에만 있다.
#    새 종목이 생기면 여기 한 줄을 더한다.
#
# 각 축은 `(유형, (키워드…))`. 유형은 **전 종목 공통 스키마**이고
# 키워드만 리그 현지어다 — 그래야 `variable_ledger` 가 종목을 가로질러
# 같은 유형을 20건까지 셀 수 있다.
SITUATION_TYPES: tuple[str, ...] = (
    "retirement", "ceremony", "manager", "coaching", "trade", "contract",
    "streak", "extra_practice", "front_office", "crowd", "travel",
    "conflict", "captain", "roster_move",
)

_SIT_KO = {
    "retirement": ("은퇴식", "은퇴 경기", "은퇴 투어"),
    "ceremony": ("영구결번", "시상식", "기념 행사", "헌액", "시구"),
    "manager": ("감독 경질", "감독 사퇴", "감독 교체", "감독대행", "경질설"),
    "coaching": ("코치 경질", "코치진 개편", "수석코치", "코치 보직"),
    "trade": ("트레이드", "웨이버", "방출", "지명 철회"),
    "contract": ("FA 계약", "다년 계약", "연장 계약", "잔류"),
    "streak": ("연패", "연승", "분위기 반전", "탈꼴찌"),
    "extra_practice": ("특타", "특별타격훈련", "긴급 미팅", "선수단 미팅"),
    "front_office": ("구단주", "사장 방문", "단장 방문", "프런트"),
    "crowd": ("매진", "만원 관중", "팬 이벤트", "홈 최종전"),
    "travel": ("장거리 이동", "원정 강행군", "이동일 없이"),
    "conflict": ("벤치클리어링", "사구", "빈볼", "충돌"),
    "captain": ("주장 교체", "주장 선임", "주장 박탈"),
    "roster_move": ("2군 강등", "1군 말소", "콜업", "1군 등록"),
}
_SIT_JA = {
    "retirement": ("引退試合", "引退セレモニー", "現役引退"),
    "ceremony": ("永久欠番", "表彰式", "始球式", "記念試合"),
    "manager": ("監督交代", "監督解任", "監督辞任", "代行"),
    "coaching": ("コーチ解任", "コーチ人事"),
    "trade": ("トレード", "戦力外", "自由契約"),
    "contract": ("契約更改", "複数年契約", "残留"),
    "streak": ("連敗", "連勝", "巻き返し"),
    "extra_practice": ("特打", "緊急ミーティング", "居残り練習"),
    "front_office": ("オーナー", "球団社長", "編成"),
    "crowd": ("満員御礼", "ファンイベント", "最終戦"),
    "travel": ("移動日なし", "長距離移動"),
    "conflict": ("乱闘", "死球", "報復"),
    "captain": ("主将交代", "キャプテン"),
    "roster_move": ("抹消", "昇格", "登録"),
}
_SIT_EN = {
    "retirement": ("retirement ceremony", "final game", "retires"),
    "ceremony": ("jersey retirement", "hall of fame", "tribute", "first pitch"),
    "manager": ("manager fired", "manager resigns", "interim manager"),
    "coaching": ("coaching staff", "hitting coach fired"),
    "trade": ("traded", "designated for assignment", "DFA", "waivers", "released"),
    "contract": ("extension", "free agent deal", "signs"),
    "streak": ("losing streak", "winning streak", "skid"),
    "extra_practice": ("extra batting practice", "team meeting", "players-only"),
    "front_office": ("owner", "front office", "general manager visit"),
    "crowd": ("sellout", "fan event", "home finale"),
    "travel": ("long road trip", "no off day", "getaway day"),
    "conflict": ("benches clear", "hit by pitch", "retaliation", "brawl"),
    "captain": ("named captain", "stripped of captaincy"),
    "roster_move": ("call-up", "optioned", "recalled", "sent down"),
}
_SIT_SOCCER = {
    "retirement": ("testimonial", "은퇴 경기", "farewell match"),
    "ceremony": ("trophy presentation", "시상식"),
    "manager": ("sack", "sacked", "manager fired", "감독 경질", "caretaker"),
    "coaching": ("assistant coach", "코치진"),
    "trade": ("transfer", "loan move", "이적"),
    "contract": ("new contract", "재계약"),
    "streak": ("winless run", "연패", "unbeaten run"),
    "extra_practice": ("crisis talks", "긴급 미팅"),
    "front_office": ("owner", "sporting director", "구단주"),
    "crowd": ("sold out", "fan protest", "매진"),
    "travel": ("midweek travel", "원정 연전"),
    "conflict": ("red card", "touchline row", "충돌"),
    "captain": ("captaincy", "주장 박탈", "new captain"),
    "roster_move": ("squad list", "명단 제외"),
}

#: 종목 → 상황 축 키워드. 없는 종목은 빈 표(수집은 돌되 태그가 안 붙는다).
SITUATION_AXES: dict[str, dict[str, tuple[str, ...]]] = {
    "kbo": _SIT_KO, "npb": _SIT_JA, "mlb": _SIT_EN, "soccer": _SIT_SOCCER,
}


def situation_axes(sport: str) -> dict[str, tuple[str, ...]]:
    """그 종목의 상황 축. 모르는 종목이면 빈 표 — 수집을 멈추지 않는다."""
    return SITUATION_AXES.get((sport or "").lower(), {})


def situation_types() -> tuple[str, ...]:
    """전 종목 공통 유형 목록. `variable_ledger` 가 이것으로 센다."""
    return SITUATION_TYPES


#: 공식·언론으로 인정하는 도메인 조각. 여기 없으면 `[미확인]` 이고 %p 0 이다.
#  ⚠️ 사이트를 **허용하기 위한** 목록이 아니라 **신뢰도를 표시하기 위한**
#     목록이다. 수집은 열린 웹 전체에서 하고, 라벨만 여기서 갈린다.
TRUSTED_SOURCE_MARKERS: tuple[str, ...] = (
    # 통신·방송·일간지 (공통 접미 포함)
    ".go.kr", ".or.kr", "yna.co.kr", "newsis.com", "news1.kr", "chosun.com",
    "joongang.co.kr", "donga.com", "hankyung.com", "mk.co.kr", "khan.co.kr",
    "hani.co.kr", "sportschosun.com", "sportsseoul.com", "osen.co.kr",
    "mydaily.co.kr", "xportsnews.com", "spotvnews.co.kr", "star.mt.co.kr",
    "nikkansports.com", "sponichi.co.jp", "hochi.news", "sanspo.com",
    "asahi.com", "yomiuri.co.jp", "mainichi.jp", "nikkei.com", "nhk.or.jp",
    "baseball.yahoo.co.jp", "npb.jp",
    "mlb.com", "espn.com", "cbssports.com", "si.com", "theathletic.com",
    "apnews.com", "reuters.com", "nytimes.com", "washingtonpost.com",
    "usatoday.com", "nbcsports.com", "foxsports.com", "bleacherreport.com",
    "bbc.co.uk", "bbc.com", "skysports.com", "goal.com", "uefa.com",
    "fifa.com", "premierleague.com", "kbaseball.or.kr", "koreabaseball.com",
)


def is_trusted_source(url_or_domain: str) -> bool:
    """공식·언론인가. **모르면 False** — 모호하면 `[미확인]` 이 안전하다."""
    s = (url_or_domain or "").lower()
    return any(m in s for m in TRUSTED_SOURCE_MARKERS)
