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
    # 🔴 [LGA-1 / STEP 1-i-1 2026-09-20] **이미 오는 자료를 버리고 있었다.**
    #    football-data 무료 전역 `/matches` 가 매일 이 둘을 돌려준다
    #    (실측 2026-09-19: Ligue 1 6경기·Eredivisie 5경기, 전부 종료).
    #    그런데 `collectors/football.py:123` 이 화이트리스트 밖이라며 전건
    #    버렸다 — `9528ba5`(2026-08-23, 축구 7리그를 **처음 연** 커밋)의
    #    "리그앙·브라질 등 제외" 주석은 정책이 아니라 **그때의 범위**였다.
    #
    # ⚠️ **결과 적재만 켠다.** 이 표는 칸 단위로 기능이 갈린다 —
    #      odds_key  → 배당 수집(odds.py:25·48)
    #      fd_names  → 결과 적재(football.py:112)        ← 이것만 채운다
    #      tm_code   → 부상표(satellite_soccer.py:339)
    #      elo       → 축구 사전값(pipeline.py:279)
    #      aliases   → 라우터 노출(bot/main.py·find_league)
    #    🔴 `aliases` 를 **비워 둔다.** 자료가 없는 리그가 라우터에 보이면
    #       사용자가 부를 수 있고, 그때 "자료 없음"이 아니라 빈 카드가 나간다.
    # ⚠️ `fd_names` 는 **실측한 응답 문자열 그대로**다. 추측한 철자를 쓰지 않는다.
    "ligue1": {
        "fd_code": "FL1", "odds_key": None, "label": "리그앙", "elo": None,
        "fd_names": ["Ligue 1"],
        "tm_code": None,
        "aliases": [],
        "features": ("results",),
    },
    "eredivisie": {
        "fd_code": "DED", "odds_key": None, "label": "에레디비시", "elo": None,
        "fd_names": ["Eredivisie"],
        "tm_code": None,
        "aliases": [],
        "features": ("results",),
    },
}

#: 🔴 [LGA-1 2026-09-20] **리그별 기능 플래그.** 없으면 `FULL`(종전 그대로)이다.
#   결과만 쌓는 리그를 표에 넣을 때, 배당·위성·라우터가 **따라 켜지지 않게**
#   한다. 계약 테스트가 "모든 축구 리그가 위성에 있다"를 잠그고 있었고,
#   그 계약은 **전 기능이 준비된 리그**를 뜻했다 — 그 뜻을 여기서 명시한다.
FULL_FEATURES = ("results", "odds", "satellite", "router", "judge")

# ══════════════════════════════════════════════════════════════════
# 🔴 [LGA-1b 2026-09-20] **리그를 여는 기준.** `results` 만 켠 리그를 언제
#    `odds`·`satellite`·`router`·`judge` 로 넓히나.
#
#    셋이 **모두** 갖춰졌을 때만 넓히고 `aliases` 를 채운다:
#      (a) 소급 적재 완결   — 팀당 경기 수가 리그 라운드 수와 맞는다(STEP 1-i-3)
#      (b) 배당 스냅샷      — 그 리그 경기에 `open`/`open_proxy` 가 실제로 있다
#      (c) 위성 URL 실측    — `config/sources.yaml` 의 그 리그 소스가 fetch 성공
#
# ⚠️ 그 전에는 **열지 않는다.** 라우터에 보이면 사용자가 부르고, 그때
#    "자료 없음"이 아니라 **빈 카드**가 나간다.
# ⚠️ 반대 방향도 잠겨 있다 — `judge`/`router` 를 켜려면 `results` 와 그
#    적재 경로(`fd_names` 또는 `fotmob_id`)가 **먼저** 있어야 한다.
#    그것이 없으면 판정만 쌓이고 영원히 채점되지 않는다(실측: ACL 8건).
#    계약: `tests/test_lga1b_feature_lock.py::test_judge_requires_results`
#
# 대상(2026-09-20): ligue1 · eredivisie — 셋 다 미충족이라 `results` 만.
# ══════════════════════════════════════════════════════════════════


def features_of(key: str) -> tuple:
    """그 리그가 켜 둔 기능. 🔴 명시가 없으면 전부다(종전 동작 보존)."""
    return tuple((LEAGUES.get(key) or {}).get("features") or FULL_FEATURES)


def leagues_with(feature: str) -> list:
    """그 기능이 켜진 리그 키 목록. 🔴 소비처는 이것으로 고른다."""
    return [k for k in LEAGUES if feature in features_of(k)]


# 명시적으로 미지원임을 알려줄 리그 별칭 (지원 리그 오매칭 방지 — '세리에B' 등)
UNSUPPORTED_LEAGUE_ALIASES = [
    "세리에b", "분데스리가2", "분데스2", "2부", "리그앙", "리그1", "리그 1",
    "포르투갈", "프리메이라", "브라질", "에레디비시", "네덜란드", "챔피언십",
    "라리가2", "k리그2", "mls", "사우디", "유로파",
    # 🔴 [ACL-1] "챔스"·"챔피언스리그" 를 뺐다 — 이제 acl 이 지원 리그다.
    #    ⚠️ UEFA 챔스는 여전히 미지원이다. 그 구분은 별칭으로 못 한다 —
    #       사용자가 "챔스"라고 하면 ACL 로 간다. 알고 남긴다.
]


#: 🔴 [EXT-2 2026-09-20] **야구 리그 키.** `LEAGUES` 는 축구 전용이라
#   `league_labels().get("KBO")` 가 None 이었고, 호출부가 `or ""` 로 받아
#   빈 키가 됐다. 그 키는 `scout_config.rank(url, league)` 가 소스 tier 를
#   고르는 데 쓰므로 비면 **야구 기사 등급이 전부 미상**이 된다.
#   ⚠️ `config/sources.yaml` 에는 `kbo`·`npb`·`mlb` 가 **이미 있다**
#      (tier1·tier2). 표가 있는데 키가 안 닿았을 뿐이다 — 그 키와 같은 글자다.
BASEBALL_LEAGUE_KEYS = {"KBO": "kbo", "NPB": "npb", "MLB": "mlb"}


def league_labels() -> dict[str, str]:
    """label → league_key 역매핑. 🔴 야구도 포함한다(소스 tier 용).

    ⚠️ 축구 `LEAGUES` 는 그대로다 — 야구를 그 표에 넣으면 `find_league`·
       슬레이트 적재 같은 축구 전용 경로가 야구를 리그로 본다.
    """
    out = {v["label"]: k for k, v in LEAGUES.items()}
    out.update(BASEBALL_LEAGUE_KEYS)
    return out


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
