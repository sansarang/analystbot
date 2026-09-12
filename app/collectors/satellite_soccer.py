"""[SAT-S1·S2·S3] 축구 전용 인공위성 — **야구와 분리된 파일**이다.

사용자 지시 2026-09-12:
  "우선 축구전용 인공위성을 만들어라"
  "j리그 k리그 국한하지 말고 내 프로그램에 있는 전 리그를 추가해라"
  "고급 파싱이 아니라 **고급 서치 기능**이 있다"
  "인공위성 서치기능은 야구와 축구를 분리해라"

🔴 **검색 원시함수를 여기서 다시 만들지 않는다.** 다음·야후 검색, 본문 수집,
   기사 모양, 토르 보강은 전부 `satellite` 에 한 벌만 있고 여기서는 부른다.
   두 벌이 되면 한쪽을 고칠 때 다른 쪽이 안 따라온다(이 저장소의 사본 드리프트).

⚠️ 그 임포트는 **함수 안에서** 한다 — `satellite` 가 파일 끝에서 이 모듈을
   임포트하므로 위쪽에서 가져오면 순환이다. 함수 안이면 호출 시점에 조회되고,
   테스트가 `satellite._daum_fetch` 를 패치해도 그대로 먹는다.
"""

from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

#: 🔴 **검색어를 붙이지 않는다.** 실측 2026-09-12(운영, 상위 8건 중 축구 기사):
#     K리그1·다음 (5팀 40건 만점)
#       (팀명만)   **39**  ← 최선
#       K리그 선발   37 · 부상 결장 34 · 선발 라인업 32 · 축구 라인업 32 · 라인업 30
#     J1·야후 (팀명만)  6팀 전부 **8/8**
#       검색어를 붙이자 맥도날드·프로야구·연예 기사가 왔다
#   **야구와 반대다** — KBO 는 `_KBO_TERMS_LIST` 4개를 돌지만 축구는 팀명만이
#   가장 정확하다. 이 상수를 채우기 전에 **반드시 다시 재라.**
_SOCCER_TERMS = ""

#: 팀당 상위 N. 야구(`_KBO_TOP_N`=6)와 값을 공유하지 않는다 — 수율이 다르다.
_SOCCER_TOP_N = 6

#: 영어 팀명 → 검색용 현지 표기.
#  🔴 `news_rss.QUERY_ALIAS` 에 섞지 않는다 — 그쪽은 야구 팀이고 RSS 질의가
#     쓴다. 한 표를 공유하면 한쪽을 고칠 때 다른 쪽이 깨진다.
#  ⚠️ **없으면 영어 이름 그대로 검색한다.** 버리면 그 팀은 영영 재료가 없다.
#     대신 "별칭 없음"을 로그로 세어 표를 언제 늘릴지 알 수 있게 한다.
SOCCER_ALIAS: dict[str, str] = {
    # ── K리그1 (DB 실측 12팀)
    "Ulsan Hyundai FC": "울산 HD", "Jeonbuk Hyundai Motors": "전북 현대",
    "FC Seoul": "FC서울", "Pohang Steelers": "포항 스틸러스",
    "Daejeon Citizen": "대전 하나시티즌", "Gwangju FC": "광주FC",
    "Gangwon FC": "강원FC", "Incheon United": "인천 유나이티드",
    "Jeju United FC": "제주 유나이티드", "FC Anyang": "FC안양",
    "Bucheon FC 1995": "부천FC", "Sangju Sangmu FC": "김천 상무",
    # ── J1 (야후 실측으로 표기 확인)
    "FC Machida Zelvia": "FC町田ゼルビア", "Urawa Red Diamonds": "浦和レッズ",
    "Yokohama F. Marinos": "横浜F・マリノス", "Gamba Osaka": "ガンバ大阪",
    "FC Tokyo": "FC東京", "Sanfrecce Hiroshima": "サンフレッチェ広島",
    "Cerezo Osaka": "セレッソ大阪", "V-Varen Nagasaki": "V・ファーレン長崎",
    "Nagoya Grampus": "名古屋グランパス",
    # ── EPL (DB 실측 17행. 같은 팀의 두 표기가 섞여 있어 둘 다 넣는다)
    "Arsenal FC": "아스널", "Aston Villa": "아스톤 빌라",
    "Aston Villa FC": "아스톤 빌라", "Bournemouth": "본머스",
    "Brentford FC": "브렌트포드", "Brighton and Hove Albion": "브라이턴",
    "Chelsea FC": "첼시", "Crystal Palace FC": "크리스탈 팰리스",
    "Fulham FC": "풀럼", "Hull City AFC": "헐 시티",
    "Ipswich Town FC": "입스위치", "Liverpool FC": "리버풀",
    "Manchester City": "맨체스터 시티", "Manchester City FC": "맨체스터 시티",
    "Manchester United FC": "맨체스터 유나이티드",
    "Newcastle United FC": "뉴캐슬", "Tottenham Hotspur FC": "토트넘",
    # ── 라리가 (DB 실측 20팀)
    "Athletic Club": "아틀레틱 빌바오", "CA Osasuna": "오사수나",
    "Club Atletico de Madrid": "아틀레티코 마드리드",
    "Club Atl\u00e9tico de Madrid": "아틀레티코 마드리드",
    "Deportivo Alav\u00e9s": "알라베스", "Elche CF": "엘체",
    "FC Barcelona": "바르셀로나", "Getafe CF": "헤타페",
    "Levante UD": "레반테", "M\u00e1laga CF": "말라가",
    "Rayo Vallecano de Madrid": "라요 바예카노",
    "RC Celta de Vigo": "셀타 비고", "RC Deportivo La Coru\u00f1a": "데포르티보",
    "RCD Espanyol de Barcelona": "에스파뇰",
    "Real Betis Balompi\u00e9": "레알 베티스", "Real Madrid CF": "레알 마드리드",
    "Real Racing Club de Santander": "라싱 산탄데르",
    "Real Sociedad de F\u00fatbol": "레알 소시에다드", "Sevilla FC": "세비야",
    "Valencia CF": "발렌시아", "Villarreal CF": "비야레알",
    # ── 세리에A (DB 실측 20팀)
    "ACF Fiorentina": "피오렌티나", "AC Milan": "AC밀란", "AC Monza": "몬차",
    "AS Roma": "AS로마", "Atalanta BC": "아탈란타",
    "Bologna FC 1909": "볼로냐", "Cagliari Calcio": "칼리아리",
    "Como 1907": "코모", "FC Internazionale Milano": "인터 밀란",
    "Frosinone Calcio": "프로시노네", "Genoa CFC": "제노아",
    "Juventus FC": "유벤투스", "Parma Calcio 1913": "파르마",
    "SSC Napoli": "나폴리", "SS Lazio": "라치오", "Torino FC": "토리노",
    "Udinese Calcio": "우디네세", "US Lecce": "레체",
    "US Sassuolo Calcio": "사수올로", "Venezia FC": "베네치아",
    # ── 분데스리가 (DB 실측 9팀)
    "1. FC K\u00f6ln": "쾰른", "1. FC Union Berlin": "우니온 베를린",
    "Borussia Dortmund": "도르트문트", "Eintracht Frankfurt": "프랑크푸르트",
    "FC Augsburg": "아우크스부르크", "FC Bayern M\u00fcnchen": "바이에른 뮌헨",
    "FC Schalke 04": "샬케", "Hamburger SV": "함부르크",
    "VfB Stuttgart": "슈투트가르트",
    # ── 덴마크 수페르리가 (DB 실측 10팀)
    "AC Horsens": "호르센스", "AGF Aarhus": "오르후스",
    "Brondby IF": "브뢴뷔", "FC Midtjylland": "미트윌란",
    "FC Nordsjaelland": "노르셸란", "Lyngby": "륑비",
    "OB Odense BK": "오덴세", "Randers FC": "란데르스",
    "Silkeborg IF": "실케보르", "SonderjyskE": "쇤데르위스케",
}

#: 토르 DDG 보강용 **영어** 질의 꼬리. 🔴 한국어는 토르로 보내지 않는다
#  (`tor_search.is_tor_safe_query` 가 거부 — 한국 사이트가 출구노드에 깨진다).
_SOCCER_TOR_TAIL = "team news injury suspension predicted lineup"

#: 리그 라벨 → 검색 갈래. 🔴 라벨 원본은 `app/leagues.py` 다.
#  실측 2026-09-12 (상위 8건 중 축구 기사): K리그1 39/40 · EPL 33/40 ·
#  라리가 33/40 · 분데스리가 32/40 · 세리에A 30/40 · 덴마크 27/40 · J1 8/8.
#  **한국 언론이 유럽 축구를 두껍게 다룬다** — 다음 하나로 여섯 리그가 된다.
_SOCCER_SOURCE = {
    "K리그1": "daum", "EPL": "daum", "라리가": "daum",
    "세리에A": "daum", "분데스리가": "daum", "덴마크 수페르리가": "daum",
    "J1 리그": "yahoo",
}


def soccer_query(team: str) -> str:
    """검색용 팀 표기. 별칭이 없으면 **영어 그대로** — 버리지 않는다."""
    return SOCCER_ALIAS.get(team, team)


async def gather_soccer(jg: dict, *, client=None, now: datetime | None = None) -> list[dict]:
    """축구 경기 1건 — 리그에 맞는 뉴스검색으로 팀별 기사·본문을 긁는다.

    🔴 **검색어를 붙이지 않는다**(`_SOCCER_TERMS` 주석의 실측).
    🔴 소스가 없는 리그(유럽 5리그)는 **빈손 + 로그**다 — "소스가 없다"와
       "긁었는데 0건"을 가를 수 있어야 한다.
    ⚠️ 한 팀이 터져도 나머지는 산다. 실패는 로그 한 줄.
    """
    # 🔴 [SAT-S3] 공용 검색 함수는 `satellite` 에 한 벌만 있다 —
    #    **함수 안에서** 가져온다(순환 임포트 회피 + 패치 가능).
    from app.collectors.satellite import (_article, _daum_fetch,
                                          _fetch_article_body, _tor_supplement,
                                          _yahoo_fetch, parse_daum_news,
                                          parse_yahoo_news)

    league = jg.get("league") or ""
    kind = _SOCCER_SOURCE.get(league)
    if kind is None:
        # 🔴 지원 목록을 **손으로 적지 않는다** — `_SOCCER_SOURCE` 가 원본이다.
        #    손으로 적으면 리그가 늘 때 로그만 옛것이 된다(사본 드리프트).
        logger.info("[satellite] 축구 %s — 이 리그는 위성 소스가 없다 (지원: %s)",
                    league or "(리그 없음)", ", ".join(sorted(_SOCCER_SOURCE)))
        return []
    out: list[dict] = []
    seen: set[str] = set()
    no_alias: list[str] = []
    for side in ("home", "away"):
        team = jg.get(side) or ""
        if not team:
            continue
        if team not in SOCCER_ALIAS:
            no_alias.append(team)
        q = f"{soccer_query(team)} {_SOCCER_TERMS}".strip()
        try:
            if kind == "daum":
                items = parse_daum_news(await _daum_fetch(q))
                src_name = "다음뉴스"
            else:
                items = parse_yahoo_news(await _yahoo_fetch(q))
                src_name = "Yahoo!ニュース"
        except Exception as exc:
            logger.warning("[satellite] 축구 %s 검색 실패 %s: %s",
                           league, team, exc)
            continue
        for it in items[:_SOCCER_TOP_N]:
            u = it.get("url") or ""
            if not u or u in seen:
                continue
            seen.add(u)
            body = await _fetch_article_body(u)
            out.append(_article(title=it.get("title") or "", url=u,
                                source=src_name, team=team,
                                body=body or it.get("title") or "", age_h=None))
    if no_alias:
        # 🔴 커버리지를 모르면 별칭표를 언제 늘려야 하는지 알 수 없다.
        #    ⚠️ 영어 이름으로는 다음 검색이 거의 안 나온다(실측 2026-09-12:
        #       Arsenal FC 0/8 · SSC Napoli 0/8 · Brondby IF 0/8,
        #       한국어는 7·7·6). 별칭이 답이고 폴백은 최후 수단이다.
        logger.info("[satellite] 축구 %s 별칭 없음 %d팀: %s — 영어 이름으로 검색했다",
                    league, len(no_alias), no_alias)
    # 🔴 [SAT-S2] **토르 DDG 영어 보강** — 고급 검색(SAT-7). MLB·NPB 는 이미
    #    쓰는데 축구는 안 썼다. 실측 2026-09-12: 질이 높다 —
    #    "Chelsea vs Hull: predicted lineup, confirmed team news, injury/
    #     suspension list" 가 한 기사에 다 들어 있다.
    #    ⚠️ **속도 제한이 심하다** — 연속 질의는 DDG 403, 15초를 띄워도 1/3 만
    #       통과했다. 그래서 **경기당 2질의**(팀당 1)로 묶는다. 늘리면 전부 막힌다.
    #    ⚠️ `tor_search` 머리말대로 **순수 보강**이다 — 주력은 위 뉴스검색이다.
    #    ⚠️ 한국어는 나가지 않는다(`is_tor_safe_query` 가 거부).
    out += await _tor_supplement(jg, [
        (jg.get(side) or "", f"{jg.get(side) or ''} {_SOCCER_TOR_TAIL}")
        for side in ("home", "away") if jg.get(side)])
    logger.info("[satellite] 축구 %s %s@%s 기사 %d건",
                league, jg.get("away"), jg.get("home"), len(out))
    return out


