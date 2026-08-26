"""팀명 사전 — ① 한국어 별칭 → (종목, 정식 팀명) 질문 매칭 ② 영문 팀명 → 한국어 표기."""

TEAM_ALIASES: dict[str, tuple[str, str]] = {
    # ---- MLB 30개 구단 ----
    "다저스": ("mlb", "Los Angeles Dodgers"), "양키스": ("mlb", "New York Yankees"),
    "메츠": ("mlb", "New York Mets"), "레드삭스": ("mlb", "Boston Red Sox"),
    "컵스": ("mlb", "Chicago Cubs"), "화이트삭스": ("mlb", "Chicago White Sox"),
    "브레이브스": ("mlb", "Atlanta Braves"), "오리올스": ("mlb", "Baltimore Orioles"),
    "레이스": ("mlb", "Tampa Bay Rays"), "블루제이스": ("mlb", "Toronto Blue Jays"),
    "가디언스": ("mlb", "Cleveland Guardians"), "타이거스": ("mlb", "Detroit Tigers"),
    "로열스": ("mlb", "Kansas City Royals"), "트윈스": ("mlb", "Minnesota Twins"),
    "애스트로스": ("mlb", "Houston Astros"), "휴스턴": ("mlb", "Houston Astros"),
    "에인절스": ("mlb", "Los Angeles Angels"), "엔젤스": ("mlb", "Los Angeles Angels"),
    "애슬레틱스": ("mlb", "Athletics"), "매리너스": ("mlb", "Seattle Mariners"),
    "레인저스": ("mlb", "Texas Rangers"), "필리스": ("mlb", "Philadelphia Phillies"),
    "내셔널스": ("mlb", "Washington Nationals"), "말린스": ("mlb", "Miami Marlins"),
    "브루어스": ("mlb", "Milwaukee Brewers"), "카디널스": ("mlb", "St. Louis Cardinals"),
    "파이리츠": ("mlb", "Pittsburgh Pirates"), "피츠버그": ("mlb", "Pittsburgh Pirates"),
    "레즈": ("mlb", "Cincinnati Reds"), "디백스": ("mlb", "Arizona Diamondbacks"),
    "다이아몬드백스": ("mlb", "Arizona Diamondbacks"), "로키스": ("mlb", "Colorado Rockies"),
    "자이언츠": ("mlb", "San Francisco Giants"), "파드리스": ("mlb", "San Diego Padres"),
    # ---- EPL ----
    "맨시티": ("soccer", "Manchester City"), "맨체스터 시티": ("soccer", "Manchester City"),
    "아스날": ("soccer", "Arsenal"), "아스널": ("soccer", "Arsenal"),
    "리버풀": ("soccer", "Liverpool"), "첼시": ("soccer", "Chelsea"),
    "토트넘": ("soccer", "Tottenham Hotspur"), "맨유": ("soccer", "Manchester United"),
    "맨체스터 유나이티드": ("soccer", "Manchester United"),
    "뉴캐슬": ("soccer", "Newcastle United"), "애스턴 빌라": ("soccer", "Aston Villa"),
    "아스톤 빌라": ("soccer", "Aston Villa"), "브라이턴": ("soccer", "Brighton and Hove Albion"),
    "브라이튼": ("soccer", "Brighton and Hove Albion"), "웨스트햄": ("soccer", "West Ham United"),
    "브렌트포드": ("soccer", "Brentford"), "풀럼": ("soccer", "Fulham"),
    "에버턴": ("soccer", "Everton"), "에버튼": ("soccer", "Everton"),
    "울버햄튼": ("soccer", "Wolverhampton Wanderers"), "울브스": ("soccer", "Wolverhampton Wanderers"),
    "크리스탈 팰리스": ("soccer", "Crystal Palace"), "팰리스": ("soccer", "Crystal Palace"),
    "본머스": ("soccer", "Bournemouth"), "노팅엄": ("soccer", "Nottingham Forest"),
    "레스터": ("soccer", "Leicester City"), "리즈": ("soccer", "Leeds United"),
    "번리": ("soccer", "Burnley"), "선덜랜드": ("soccer", "Sunderland"),
    # ---- 라리가 ----
    "레알 마드리드": ("soccer", "Real Madrid"), "레알": ("soccer", "Real Madrid"),
    "바르셀로나": ("soccer", "Barcelona"), "바르사": ("soccer", "Barcelona"),
    "아틀레티코": ("soccer", "Atlético Madrid"), "아틀레티코 마드리드": ("soccer", "Atlético Madrid"),
    "세비야": ("soccer", "Sevilla"), "발렌시아": ("soccer", "Valencia"),
    "비야레알": ("soccer", "Villarreal"), "빌바오": ("soccer", "Athletic Bilbao"),
    "아틀레틱 빌바오": ("soccer", "Athletic Bilbao"), "레알 소시에다드": ("soccer", "Real Sociedad"),
    "소시에다드": ("soccer", "Real Sociedad"), "베티스": ("soccer", "Real Betis"),
    "셀타": ("soccer", "Celta Vigo"), "셀타 비고": ("soccer", "Celta Vigo"),
    "헤타페": ("soccer", "Getafe"), "오사수나": ("soccer", "Osasuna"),
    "마요르카": ("soccer", "Mallorca"), "지로나": ("soccer", "Girona"),
    "알라베스": ("soccer", "Alavés"), "에스파뇰": ("soccer", "Espanyol"),
    "라요": ("soccer", "Rayo Vallecano"), "라요 바예카노": ("soccer", "Rayo Vallecano"),
    "레반테": ("soccer", "Levante"), "엘체": ("soccer", "Elche"),
    "오비에도": ("soccer", "Real Oviedo"),
    # ---- 세리에A ----
    "유벤투스": ("soccer", "Juventus"), "유베": ("soccer", "Juventus"),
    "인터밀란": ("soccer", "Inter Milan"), "인테르": ("soccer", "Inter Milan"),
    "ac밀란": ("soccer", "AC Milan"), "밀란": ("soccer", "AC Milan"),
    "나폴리": ("soccer", "Napoli"), "로마": ("soccer", "AS Roma"),
    "라치오": ("soccer", "Lazio"), "아탈란타": ("soccer", "Atalanta BC"),
    "피오렌티나": ("soccer", "Fiorentina"), "볼로냐": ("soccer", "Bologna"),
    "토리노": ("soccer", "Torino"), "우디네세": ("soccer", "Udinese"),
    "제노아": ("soccer", "Genoa"), "칼리아리": ("soccer", "Cagliari"),
    "파르마": ("soccer", "Parma"), "레체": ("soccer", "Lecce"),
    "코모": ("soccer", "Como"), "베로나": ("soccer", "Hellas Verona"),
    "사수올로": ("soccer", "Sassuolo"), "크레모네세": ("soccer", "Cremonese"),
    "피사": ("soccer", "Pisa"), "몬차": ("soccer", "Monza"),
    # ---- 분데스리가 ----
    "바이에른": ("soccer", "Bayern Munich"), "바이에른 뮌헨": ("soccer", "Bayern Munich"),
    "뮌헨": ("soccer", "Bayern Munich"), "도르트문트": ("soccer", "Borussia Dortmund"),
    "돌문": ("soccer", "Borussia Dortmund"), "레버쿠젠": ("soccer", "Bayer Leverkusen"),
    "라이프치히": ("soccer", "RB Leipzig"), "프랑크푸르트": ("soccer", "Eintracht Frankfurt"),
    "슈투트가르트": ("soccer", "VfB Stuttgart"), "볼프스부르크": ("soccer", "VfL Wolfsburg"),
    "글라드바흐": ("soccer", "Borussia Monchengladbach"),
    "묀헨글라트바흐": ("soccer", "Borussia Monchengladbach"),
    "프라이부르크": ("soccer", "SC Freiburg"), "호펜하임": ("soccer", "TSG Hoffenheim"),
    "마인츠": ("soccer", "FSV Mainz 05"), "아우크스부르크": ("soccer", "Augsburg"),
    "브레멘": ("soccer", "Werder Bremen"), "베르더 브레멘": ("soccer", "Werder Bremen"),
    "우니온 베를린": ("soccer", "Union Berlin"), "우니온": ("soccer", "Union Berlin"),
    "쾰른": ("soccer", "FC Cologne"), "함부르크": ("soccer", "Hamburger SV"),
    "장크트 파울리": ("soccer", "FC St. Pauli"), "하이덴하임": ("soccer", "1. FC Heidenheim"),
    # ---- K리그1 ----
    "울산": ("soccer", "Ulsan HD FC"), "울산hd": ("soccer", "Ulsan HD FC"),
    "전북": ("soccer", "Jeonbuk Hyundai Motors"), "전북 현대": ("soccer", "Jeonbuk Hyundai Motors"),
    "포항": ("soccer", "Pohang Steelers"), "포항 스틸러스": ("soccer", "Pohang Steelers"),
    "서울": ("soccer", "FC Seoul"), "fc서울": ("soccer", "FC Seoul"),
    "수원fc": ("soccer", "Suwon FC"), "대구": ("soccer", "Daegu FC"),
    "인천": ("soccer", "Incheon United"), "강원": ("soccer", "Gangwon FC"),
    "제주": ("soccer", "Jeju United"), "광주": ("soccer", "Gwangju FC"),
    "대전": ("soccer", "Daejeon Hana Citizen"), "김천": ("soccer", "Gimcheon Sangmu"),
    "안양": ("soccer", "FC Anyang"),
    # ---- J1·덴마크 주요 ----
    "마치다": ("soccer", "FC Machida Zelvia"), "우라와": ("soccer", "Urawa Red Diamonds"),
    "가시마": ("soccer", "Kashima Antlers"), "감바": ("soccer", "Gamba Osaka"),
    "비셀 고베": ("soccer", "Vissel Kobe"), "고베": ("soccer", "Vissel Kobe"),
    "미트윌란": ("soccer", "FC Midtjylland"), "코펜하겐": ("soccer", "FC Copenhagen"),
}

# 영문 소문자 별칭
_EN_EXTRA = {
    ("mlb", "Los Angeles Dodgers"): ["dodgers"],
    ("mlb", "New York Yankees"): ["yankees"],
    ("mlb", "Chicago Cubs"): ["cubs"],
    ("soccer", "Arsenal"): ["arsenal"],
    ("soccer", "Liverpool"): ["liverpool"],
    ("soccer", "Real Madrid"): ["real madrid"],
    ("soccer", "Juventus"): ["juventus"],
    ("soccer", "Bayern Munich"): ["bayern"],
}
for key, names in _EN_EXTRA.items():
    for n in names:
        TEAM_ALIASES[n] = key


def find_team(text: str) -> tuple[str, str] | None:
    """텍스트에서 가장 긴 별칭 매치를 찾는다. 없으면 None."""
    lowered = text.lower()
    best: tuple[str, str] | None = None
    best_len = 0
    for alias, value in TEAM_ALIASES.items():
        if alias in lowered and len(alias) > best_len:
            best, best_len = value, len(alias)
    return best


# ---------------------------------------------------------------- 한국어 표기 사전

KR_TEAM_NAMES: dict[str, str] = {
    # MLB
    "Los Angeles Dodgers": "LA 다저스", "New York Yankees": "뉴욕 양키스",
    "New York Mets": "뉴욕 메츠", "Boston Red Sox": "보스턴 레드삭스",
    "Chicago Cubs": "시카고 컵스", "Chicago White Sox": "시카고 화이트삭스",
    "Atlanta Braves": "애틀랜타 브레이브스", "Baltimore Orioles": "볼티모어 오리올스",
    "Tampa Bay Rays": "탬파베이 레이스", "Toronto Blue Jays": "토론토 블루제이스",
    "Cleveland Guardians": "클리블랜드 가디언스", "Detroit Tigers": "디트로이트 타이거스",
    "Kansas City Royals": "캔자스시티 로열스", "Minnesota Twins": "미네소타 트윈스",
    "Houston Astros": "휴스턴 애스트로스", "Los Angeles Angels": "LA 에인절스",
    "Athletics": "애슬레틱스", "Seattle Mariners": "시애틀 매리너스",
    "Texas Rangers": "텍사스 레인저스", "Philadelphia Phillies": "필라델피아 필리스",
    "Washington Nationals": "워싱턴 내셔널스", "Miami Marlins": "마이애미 말린스",
    "Milwaukee Brewers": "밀워키 브루어스", "St. Louis Cardinals": "세인트루이스 카디널스",
    "Pittsburgh Pirates": "피츠버그 파이리츠", "Cincinnati Reds": "신시내티 레즈",
    "Arizona Diamondbacks": "애리조나 다이아몬드백스", "Colorado Rockies": "콜로라도 로키스",
    "San Francisco Giants": "샌프란시스코 자이언츠", "San Diego Padres": "샌디에이고 파드리스",
    # EPL
    "Manchester City": "맨체스터 시티", "Arsenal": "아스날", "Liverpool": "리버풀",
    "Chelsea": "첼시", "Tottenham Hotspur": "토트넘", "Manchester United": "맨체스터 유나이티드",
    "Newcastle United": "뉴캐슬", "Aston Villa": "애스턴 빌라",
    "Brighton and Hove Albion": "브라이턴", "West Ham United": "웨스트햄",
    "Brentford": "브렌트포드", "Fulham": "풀럼", "Everton": "에버턴",
    "Wolverhampton Wanderers": "울버햄튼", "Crystal Palace": "크리스탈 팰리스",
    "Bournemouth": "본머스", "Nottingham Forest": "노팅엄 포레스트",
    "Leicester City": "레스터 시티", "Leeds United": "리즈", "Burnley": "번리",
    "Sunderland": "선덜랜드",
    # 라리가
    "Real Madrid": "레알 마드리드", "Barcelona": "바르셀로나",
    "Atlético Madrid": "아틀레티코 마드리드", "Atletico Madrid": "아틀레티코 마드리드",
    "Sevilla": "세비야", "Valencia": "발렌시아", "Villarreal": "비야레알",
    "Athletic Bilbao": "아틀레틱 빌바오", "Real Sociedad": "레알 소시에다드",
    "Real Betis": "레알 베티스", "Celta Vigo": "셀타 비고", "Getafe": "헤타페",
    "Osasuna": "오사수나", "Mallorca": "마요르카", "Girona": "지로나",
    "Alavés": "알라베스", "Alaves": "알라베스", "Espanyol": "에스파뇰",
    "Rayo Vallecano": "라요 바예카노", "Levante": "레반테", "Elche": "엘체",
    "Real Oviedo": "레알 오비에도",
    # 세리에A
    "Juventus": "유벤투스", "Inter Milan": "인터 밀란", "AC Milan": "AC 밀란",
    "Napoli": "나폴리", "AS Roma": "AS 로마", "Lazio": "라치오",
    "Atalanta BC": "아탈란타", "Fiorentina": "피오렌티나", "Bologna": "볼로냐",
    "Torino": "토리노", "Udinese": "우디네세", "Genoa": "제노아",
    "Cagliari": "칼리아리", "Parma": "파르마", "Lecce": "레체", "Como": "코모",
    "Hellas Verona": "엘라스 베로나", "Sassuolo": "사수올로",
    "Cremonese": "크레모네세", "Pisa": "피사", "Monza": "몬차",
    # 분데스리가
    "Bayern Munich": "바이에른 뮌헨", "Borussia Dortmund": "도르트문트",
    "Bayer Leverkusen": "레버쿠젠", "RB Leipzig": "RB 라이프치히",
    "Eintracht Frankfurt": "프랑크푸르트", "VfB Stuttgart": "슈투트가르트",
    "VfL Wolfsburg": "볼프스부르크", "Borussia Monchengladbach": "묀헨글라트바흐",
    "SC Freiburg": "프라이부르크", "TSG Hoffenheim": "호펜하임",
    "FSV Mainz 05": "마인츠", "Augsburg": "아우크스부르크",
    "Werder Bremen": "베르더 브레멘", "Union Berlin": "우니온 베를린",
    "FC Cologne": "쾰른", "Hamburger SV": "함부르크", "FC St. Pauli": "장크트 파울리",
    "1. FC Heidenheim": "하이덴하임",
    # K리그1
    "Ulsan HD FC": "울산 HD", "Jeonbuk Hyundai Motors": "전북 현대",
    "Pohang Steelers": "포항 스틸러스", "FC Seoul": "FC 서울", "Suwon FC": "수원 FC",
    "Daegu FC": "대구 FC", "Incheon United": "인천 유나이티드", "Gangwon FC": "강원 FC",
    "Jeju United": "제주 유나이티드", "Gwangju FC": "광주 FC",
    "Daejeon Hana Citizen": "대전 하나시티즌", "Gimcheon Sangmu": "김천 상무",
    "FC Anyang": "FC 안양",
    # J1
    "FC Machida Zelvia": "마치다 젤비아", "Urawa Red Diamonds": "우라와 레즈",
    "Kashima Antlers": "가시마 앤틀러스", "Gamba Osaka": "감바 오사카",
    "Vissel Kobe": "비셀 고베", "FC Tokyo": "FC 도쿄",
    "Sanfrecce Hiroshima": "산프레체 히로시마", "Yokohama F Marinos": "요코하마 F 마리노스",
    "Kawasaki Frontale": "가와사키 프론탈레", "Cerezo Osaka": "세레소 오사카",
    "Avispa Fukuoka": "아비스파 후쿠오카", "Kyoto Sanga": "교토 상가",
    "Shimizu S-Pulse": "시미즈 S펄스", "Kashiwa Reysol": "가시와 레이솔",
    "V-Varen Nagasaki": "V파렌 나가사키",
    # 덴마크
    "FC Copenhagen": "FC 코펜하겐", "FC Midtjylland": "FC 미트윌란",
    "FC Nordsjaelland": "FC 노르셸란", "AGF Aarhus": "AGF 오르후스",
    "OB Odense BK": "OB 오덴세", "Randers FC": "란데르스",
    "SonderjyskE": "쇤데르위스케", "AC Horsens": "AC 호르센스", "Lyngby": "륑비",
    "Brondby": "브뢴비", "Viborg FF": "비보르",
}


# [§8-14] KBO 10팀 — Odds API 표기 기준(실조회 2026-08-26)
KR_TEAM_NAMES.update({
    "LG Twins": "LG 트윈스",
    "Doosan Bears": "두산 베어스",
    "KT Wiz": "KT 위즈",
    "SSG Landers": "SSG 랜더스",
    "NC Dinos": "NC 다이노스",
    "Kiwoom Heroes": "키움 히어로즈",
    "Hanwha Eagles": "한화 이글스",
    "Samsung Lions": "삼성 라이온즈",
    "Lotte Giants": "롯데 자이언츠",
    "Kia Tigers": "KIA 타이거즈",
    "KIA Tigers": "KIA 타이거즈",
})

# [§8-14] NPB 12팀 — Odds API 표기 기준(실조회 2026-08-26)
#   ⚠️ '롯데'가 KBO(롯데 자이언츠)와 NPB(지바 롯데 마린스) 양쪽에 있다.
#      Odds 표기가 다르므로 사전 키로는 충돌하지 않지만, 사용자 질의에서
#      '롯데'만 오면 종목으로 구분해야 한다.
KR_TEAM_NAMES.update({
    "Yomiuri Giants": "요미우리 자이언츠",
    "Hanshin Tigers": "한신 타이거스",
    "Chunichi Dragons": "주니치 드래건스",
    "Tokyo Yakult Swallows": "야쿠르트 스왈로스",
    "Yokohama DeNA BayStars": "요코하마 DeNA 베이스타스",
    "Hiroshima Toyo Carp": "히로시마 도요 카프",
    "Fukuoka SoftBank Hawks": "소프트뱅크 호크스",
    "Chiba Lotte Marines": "지바 롯데 마린스",
    "Saitama Seibu Lions": "세이부 라이온스",
    "Hokkaido Nippon-Ham Fighters": "니혼햄 파이터스",
    "Tohoku Rakuten Golden Eagles": "라쿠텐 골든이글스",
    "Orix Buffaloes": "오릭스 버펄로스",
})


def kr_team(name: str) -> str:
    """영문 팀명 → 한국어 표기. 정확 일치 → 퍼지 → 원문 유지(로그)."""
    if name in KR_TEAM_NAMES:
        return KR_TEAM_NAMES[name]
    from app.collectors.football import team_tokens

    target = team_tokens(name)
    best, best_score = None, 0
    for en, kr in KR_TEAM_NAMES.items():
        entry = team_tokens(en)
        score = len(target & entry)
        # 작은 쪽 토큰 집합이 완전히 겹칠 때만 매칭 (부분 일치 오인 방지)
        if score == 0 or score < min(len(target) or 1, len(entry) or 1):
            continue
        if score > best_score:
            best, best_score = kr, score
        elif score == best_score and best != kr:
            best = None  # 동점 모호 → 원문 유지
    return best or name
