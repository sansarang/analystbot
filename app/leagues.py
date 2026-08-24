"""축구 리그 화이트리스트 레지스트리 — 일정·배당·모델·표기의 단일 소스.

odds_key는 The Odds API /v4/sports 실조회로 확인된 정확한 키 (2026-08-23 검증).
"""

LEAGUES: dict[str, dict] = {
    "epl": {
        "fd_code": "PL", "odds_key": "soccer_epl", "label": "EPL", "elo": "E0",
        "fd_names": ["Premier League"],
        "aliases": ["epl", "프리미어리그", "프리미어", "영국", "잉글랜드"],
    },
    "la_liga": {
        "fd_code": "PD", "odds_key": "soccer_spain_la_liga", "label": "라리가", "elo": "SP1",
        "fd_names": ["Primera Division", "La Liga"],
        "aliases": ["라리가", "스페인", "라 리가"],
    },
    "serie_a": {
        "fd_code": "SA", "odds_key": "soccer_italy_serie_a", "label": "세리에A", "elo": "I1",
        "fd_names": ["Serie A"],
        "aliases": ["세리에a", "세리에", "이탈리아"],
    },
    "bundesliga": {
        "fd_code": "BL1", "odds_key": "soccer_germany_bundesliga", "label": "분데스리가", "elo": "D1",
        "fd_names": ["Bundesliga"],
        "aliases": ["분데스리가", "분데스", "독일"],
    },
    "j1": {
        "odds_key": "soccer_japan_j_league", "label": "J1 리그", "elo": "JPN",
        "fd_names": [],
        "aliases": ["j리그", "제이리그", "j1", "일본"],
    },
    "denmark": {
        "odds_key": "soccer_denmark_superliga", "label": "덴마크 수페르리가", "elo": "DNK",
        "fd_names": [],
        "aliases": ["덴마크", "수페르리가"],
    },
    "kleague1": {
        "odds_key": "soccer_korea_kleague1", "label": "K리그1", "elo": None,  # CSV 미제공 → 모델 무효
        "fd_names": [],
        "aliases": ["k리그", "케이리그", "k리그1", "한국"],
    },
}

# 명시적으로 미지원임을 알려줄 리그 별칭 (지원 리그 오매칭 방지 — '세리에B' 등)
UNSUPPORTED_LEAGUE_ALIASES = [
    "세리에b", "분데스리가2", "분데스2", "2부", "리그앙", "리그1", "리그 1",
    "포르투갈", "프리메이라", "브라질", "에레디비시", "네덜란드", "챔피언십",
    "라리가2", "k리그2", "mls", "사우디", "챔스", "챔피언스리그", "유로파",
]


def league_labels() -> dict[str, str]:
    """label → league_key 역매핑."""
    return {v["label"]: k for k, v in LEAGUES.items()}


def find_league(text: str) -> str | None:
    """텍스트에서 지원 리그 별칭 매칭 (미지원 별칭이 먼저 매칭되면 None 처리 밖에서)."""
    lowered = text.lower()
    best, best_len = None, 0
    for key, cfg in LEAGUES.items():
        for alias in cfg["aliases"]:
            if alias in lowered and len(alias) > best_len:
                best, best_len = key, len(alias)
    return best


def find_unsupported_league(text: str) -> str | None:
    lowered = text.lower().replace(" ", "")
    for alias in UNSUPPORTED_LEAGUE_ALIASES:
        if alias.replace(" ", "") in lowered:
            return alias
    return None


def supported_league_list() -> str:
    return ", ".join(v["label"] for v in LEAGUES.values())
