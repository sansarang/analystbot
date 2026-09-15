"""축구 리그 화이트리스트 레지스트리 — 일정·배당·모델·표기의 단일 소스.

odds_key는 The Odds API /v4/sports 실조회로 확인된 정확한 키 (2026-08-23 검증).
tm_code 는 Transfermarkt 대회 코드 — 부상표 URL 에 쓴다
(`verletztespieler/wettbewerb/{tm_code}`). 7리그 전부 실파싱 확인 (2026-09-12).
"""

LEAGUES: dict[str, dict] = {
    "epl": {
        "fd_code": "PL", "odds_key": "soccer_epl", "label": "EPL", "elo": "E0",
        "fd_names": ["Premier League"],
        "tm_code": "GB1",
        "aliases": ["epl", "프리미어리그", "프리미어", "영국", "잉글랜드"],
    },
    "la_liga": {
        "fd_code": "PD", "odds_key": "soccer_spain_la_liga", "label": "라리가", "elo": "SP1",
        "fd_names": ["Primera Division", "La Liga"],
        "tm_code": "ES1",
        "aliases": ["라리가", "스페인", "라 리가"],
    },
    "serie_a": {
        "fd_code": "SA", "odds_key": "soccer_italy_serie_a", "label": "세리에A", "elo": "I1",
        "fd_names": ["Serie A"],
        "tm_code": "IT1",
        "aliases": ["세리에a", "세리에", "이탈리아"],
    },
    "bundesliga": {
        "fd_code": "BL1", "odds_key": "soccer_germany_bundesliga", "label": "분데스리가", "elo": "D1",
        "fd_names": ["Bundesliga"],
        "tm_code": "L1",
        "aliases": ["분데스리가", "분데스", "독일"],
    },
    "j1": {
        "odds_key": "soccer_japan_j_league", "label": "J1 리그", "elo": "JPN",
        "fd_names": [],
        "tm_code": "JAP1",
        "aliases": ["j리그", "제이리그", "j1", "일본"],
    },
    "denmark": {
        "odds_key": "soccer_denmark_superliga", "label": "덴마크 수페르리가", "elo": "DNK",
        "fd_names": [],
        "tm_code": "DK1",
        "aliases": ["덴마크", "수페르리가"],
    },
    "kleague1": {
        "odds_key": "soccer_korea_kleague1", "label": "K리그1", "elo": None,  # CSV 미제공 → 모델 무효
        "fd_names": [],
        "tm_code": "RSK1",
        "aliases": ["k리그", "케이리그", "k리그1", "한국"],
    },
    # 🔴 [ACL-1 2026-09-15 사용자 지시] AFC 챔피언스리그 엘리트.
    #    ⚠️ `odds_key` 가 **None** 이다 — The Odds API 종목 178개를 전수 조회했고
    #       AFC 계열 키가 하나도 없다(2026-09-15). 그래서 이 리그는
    #       **경기를 FotMob 에서** 받고(`fotmob.upsert_slate`) **배당은
    #       오즈포털**에서 받는다. 읽는 쪽이 None 을 걸러야 한다 —
    #       계약(test_acl_wiring)이 그 자리를 전수로 잠근다.
    #    ⚠️ `elo` 도 None 이다(CSV 미제공) → 모델 무효. K리그1 과 같은 처지다.
    #    ⚠️ `tm_code` 없음 — Transfermarkt 는 대회별 부상표라 ACL 표가 없다.
    #       결장 정보는 FotMob `unavailable` 로만 온다.
    "acl": {
        "fd_code": None, "odds_key": None, "label": "ACL엘리트", "elo": None,
        "fd_names": [],
        "tm_code": None,
        #: FotMob 리그명에 이 문자열이 들어가면 이 리그로 적재한다.
        "fotmob_contains": "AFC Champions League Elite",
        "aliases": ["acl", "acle", "챔스", "아챔", "챔피언스리그엘리트",
                    "afc챔피언스리그"],
    },
}

# 명시적으로 미지원임을 알려줄 리그 별칭 (지원 리그 오매칭 방지 — '세리에B' 등)
UNSUPPORTED_LEAGUE_ALIASES = [
    "세리에b", "분데스리가2", "분데스2", "2부", "리그앙", "리그1", "리그 1",
    "포르투갈", "프리메이라", "브라질", "에레디비시", "네덜란드", "챔피언십",
    "라리가2", "k리그2", "mls", "사우디", "유로파",
    # 🔴 [ACL-1] "챔스"·"챔피언스리그" 를 뺐다 — 이제 acl 이 지원 리그다.
    #    ⚠️ UEFA 챔스는 여전히 미지원이다. 그 구분은 별칭으로 못 한다 —
    #       사용자가 "챔스"라고 하면 ACL 로 간다. 알고 남긴다.
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
