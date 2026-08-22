"""한국어 팀 별칭 → (종목, 정식 팀명) 사전. 자유 질문의 범위 인식용."""

TEAM_ALIASES: dict[str, tuple[str, str]] = {
    # ---- MLB 30개 구단 ----
    "다저스": ("mlb", "Los Angeles Dodgers"),
    "양키스": ("mlb", "New York Yankees"),
    "메츠": ("mlb", "New York Mets"),
    "레드삭스": ("mlb", "Boston Red Sox"),
    "컵스": ("mlb", "Chicago Cubs"),
    "화이트삭스": ("mlb", "Chicago White Sox"),
    "브레이브스": ("mlb", "Atlanta Braves"),
    "오리올스": ("mlb", "Baltimore Orioles"),
    "레이스": ("mlb", "Tampa Bay Rays"),
    "블루제이스": ("mlb", "Toronto Blue Jays"),
    "가디언스": ("mlb", "Cleveland Guardians"),
    "타이거스": ("mlb", "Detroit Tigers"),
    "로열스": ("mlb", "Kansas City Royals"),
    "트윈스": ("mlb", "Minnesota Twins"),
    "애스트로스": ("mlb", "Houston Astros"),
    "휴스턴": ("mlb", "Houston Astros"),
    "에인절스": ("mlb", "Los Angeles Angels"),
    "엔젤스": ("mlb", "Los Angeles Angels"),
    "애슬레틱스": ("mlb", "Athletics"),
    "매리너스": ("mlb", "Seattle Mariners"),
    "레인저스": ("mlb", "Texas Rangers"),
    "필리스": ("mlb", "Philadelphia Phillies"),
    "내셔널스": ("mlb", "Washington Nationals"),
    "말린스": ("mlb", "Miami Marlins"),
    "브루어스": ("mlb", "Milwaukee Brewers"),
    "카디널스": ("mlb", "St. Louis Cardinals"),
    "파이리츠": ("mlb", "Pittsburgh Pirates"),
    "피츠버그": ("mlb", "Pittsburgh Pirates"),
    "레즈": ("mlb", "Cincinnati Reds"),
    "디백스": ("mlb", "Arizona Diamondbacks"),
    "다이아몬드백스": ("mlb", "Arizona Diamondbacks"),
    "로키스": ("mlb", "Colorado Rockies"),
    "자이언츠": ("mlb", "San Francisco Giants"),
    "파드리스": ("mlb", "San Diego Padres"),
    # ---- 주요 축구팀 (EPL) ----
    "맨시티": ("soccer", "Manchester City"),
    "맨체스터 시티": ("soccer", "Manchester City"),
    "아스날": ("soccer", "Arsenal"),
    "아스널": ("soccer", "Arsenal"),
    "리버풀": ("soccer", "Liverpool"),
    "첼시": ("soccer", "Chelsea"),
    "토트넘": ("soccer", "Tottenham"),
    "맨유": ("soccer", "Manchester United"),
    "맨체스터 유나이티드": ("soccer", "Manchester United"),
    "뉴캐슬": ("soccer", "Newcastle"),
    "애스턴 빌라": ("soccer", "Aston Villa"),
    "브라이턴": ("soccer", "Brighton"),
    "웨스트햄": ("soccer", "West Ham"),
}

# 영문 소문자 별칭 (팀명 마지막 단어)
_EN_EXTRA = {
    ("mlb", "Los Angeles Dodgers"): ["dodgers"],
    ("mlb", "New York Yankees"): ["yankees"],
    ("mlb", "Chicago Cubs"): ["cubs"],
    ("soccer", "Arsenal"): ["arsenal"],
    ("soccer", "Liverpool"): ["liverpool"],
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
