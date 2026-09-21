"""[W3-1] 결과 소스를 리그마다 정하고, finals 잡이 실제로 적재한다.

🔴 재현 (실측 2026-09-21):

    최근 30일 종료 경기
      J1 리그   0/11      K리그1  0/14
      ACL엘리트 0/10      덴마크  0/8      ← 전건 `scheduled`

   원인은 **결과 소스가 없다**는 것이다:
      j1 · kleague1 · denmark  → `fd_names` 없음 · `fotmob_contains` 없음
      acl                      → `fotmob_contains` 있음, 그러나 **finals 잡이
                                  FotMob 경로를 부르지 않는다**
   `upsert_slate` 는 일정 프리페치에서만 불린다(pipeline:1457) — 그때는 경기가
   아직 안 끝났으므로 점수가 없다. 끝난 뒤 다시 받는 경로가 **없었다.**

🔴 FotMob 리그 이름은 실측했다(하루치 목록 3일분):
      KOR 'K-League 1'      (2부는 'K League 2' — 하이픈이 다르다)
      JPN 'J. League'       ⚠️ 2부·3부가 'J. League 2'·'J. League 3'
      DEN 'Superligaen'
      INT 'AFC Champions League Elite'

⚠️ `fotmob_contains` 는 **부분 문자열**로 고른다(`upsert_slate`).
   `'J. League'` 를 그대로 쓰면 **2부·3부가 J1 으로 적재된다.**
"""
from __future__ import annotations

import inspect

import pytest


# ── ① 리그 설정 ───────────────────────────────────────────────────
def test_판정을_켠_리그는_결과_소스가_있다():
    """🔴 `test_judge_requires_results` 의 뜻 — 채점할 수 없는 리그로
    판정을 내보내지 않는다."""
    from app.leagues import LEAGUES, features_of

    missing = []
    for key, cfg in LEAGUES.items():
        if "judge" not in features_of(key):
            continue
        if not cfg.get("result_source"):
            missing.append(key)
    assert not missing, f"결과 소스가 없는데 판정이 켜져 있다: {missing}"


def test_결과_소스는_두_값_중_하나다():
    from app.leagues import LEAGUES

    for key, cfg in LEAGUES.items():
        src = cfg.get("result_source")
        if src is None:
            continue
        assert src in ("fd", "fotmob"), f"{key}: 모르는 소스 {src!r}"


def test_fd_이름이_있으면_fd_가_주_소스다():
    """⚠️ 이미 오는 자료를 버리고 다른 소스로 갈아타지 않는다."""
    from app.leagues import LEAGUES

    for key, cfg in LEAGUES.items():
        if cfg.get("fd_names"):
            assert cfg.get("result_source") == "fd", key


def test_fotmob_리그는_실측한_이름을_쓴다():
    """🔴 이름을 추측해 적지 않는다 — 실측값 그대로."""
    from app.leagues import LEAGUES

    assert LEAGUES["kleague1"].get("fotmob_league") == "K-League 1"
    assert LEAGUES["j1"].get("fotmob_league") == "J. League"
    assert LEAGUES["denmark"].get("fotmob_league") == "Superligaen"


# ── ② J리그 2부·3부가 섞이지 않는가 ──────────────────────────────
def test_J리그_2부_3부가_1부로_적재되지_않는다():
    """🔴 `'J. League' in 'J. League 2'` 는 **참**이다. 부분 문자열로 고르면
    2부·3부 17경기가 J1 으로 들어온다(실측: 하루 9+8경기)."""
    from app.collectors.fotmob import league_matches

    assert league_matches("J. League", "j1") is True
    assert league_matches("J. League 2", "j1") is False
    assert league_matches("J. League 3", "j1") is False


def test_K리그_2부도_섞이지_않는다():
    from app.collectors.fotmob import league_matches

    assert league_matches("K-League 1", "kleague1") is True
    assert league_matches("K League 2", "kleague1") is False


def test_ACL은_종전_규칙_그대로다():
    """⚠️ 이미 도는 리그의 동작을 바꾸지 않는다."""
    from app.collectors.fotmob import league_matches

    assert league_matches("AFC Champions League Elite", "acl") is True
    assert league_matches("AFC Champions League Two", "acl") is False


# ── ③ finals 잡 배선 ─────────────────────────────────────────────
def test_finals_잡이_fotmob_결과를_적재한다():
    """🔴 `upsert_slate` 는 일정 프리페치에서만 불렸다 — 끝난 뒤 다시 받는
    경로가 없어 J·K·ACL·덴마크가 영원히 `scheduled` 였다."""
    from app import scheduler as S

    src = inspect.getsource(S)
    assert "ingest_fotmob_finals" in src, "finals 잡에 FotMob 경로가 없다"
    body = inspect.getsource(S.finals_job)
    assert "ingest_fotmob_finals" in body, "만들어 놓고 finals 잡에서 안 부른다"


def test_fotmob_결과는_UTC_날짜로_받는다():
    """🔴 [W2 실측] FotMob 은 경기를 **UTC 날짜**로 색인한다.
    KST 날짜로 받으면 유럽 야간 경기가 통째로 빠진다."""
    from app import scheduler as S

    src = inspect.getsource(S.ingest_fotmob_finals)
    assert "timezone.utc" in src, "UTC 기준으로 날짜를 잡지 않는다"


@pytest.mark.asyncio
async def test_어제와_오늘_두_날을_받는다():
    """지시문 W3-3: 일일 적재는 오늘·어제 2일치."""
    from app import scheduler as S

    days: list = []

    async def _fake(pool, day, *, league_key):
        days.append(day)
        return {"fetched": 0, "matched": 0, "saved": 0, "ext_ids": []}

    got = await S.ingest_fotmob_finals(pool=None, upsert=_fake)
    assert len(set(days)) == 2, f"받은 날짜 {sorted(set(days))}"
    assert isinstance(got, dict)


@pytest.mark.asyncio
async def test_한_리그가_실패해도_나머지는_돈다():
    """⚠️ 적재는 한 리그 실패로 멈추지 않는다(기존 finals 규약과 같다)."""
    from app import scheduler as S

    calls: list = []

    async def _fake(pool, day, *, league_key):
        calls.append(league_key)
        if league_key == "j1":
            raise RuntimeError("일부러 터뜨린다")
        return {"fetched": 1, "matched": 1, "saved": 1, "ext_ids": ["fotmob:1"]}

    got = await S.ingest_fotmob_finals(pool=None, upsert=_fake)
    assert "j1" in calls and len(set(calls)) >= 2
    assert got.get("failed"), "실패를 조용히 삼켰다"


# ── ④ 중복 행 금지 (지시문 W3-1b "같은 games 행에 upsert") ────────
@pytest.mark.asyncio
async def test_다른_소스의_같은_경기에_점수를_쓴다():
    """🔴 W3-1 배포 직후 실측 — 같은 경기가 두 행이 됐다.

        K리그1 Incheon United vs Daejeon Citizen  2026-09-20 10:00Z
          odds:f882c79a…    status=scheduled  score=None   ← 판정·픽이 붙은 행
          fotmob:5140040    status=final      score=1      ← 점수가 들어간 행

    판정이 붙은 행은 여전히 `scheduled` 라 **채점이 안 닫힌다.** 점수를
    엉뚱한 행에 쓴 것이다. 기존 매칭기(`game_match.apply_result`)가 바로
    이 일을 한다 — "기존 행을 찾으면 그 행을 갱신한다".
    """
    import inspect

    from app.collectors import fotmob as F

    src = inspect.getsource(F.upsert_slate)
    assert "apply_result" in src, "자기 ext_id 로만 upsert 한다(중복 행이 생긴다)"
    assert "INSERT INTO games" not in src, "직접 INSERT 가 남아 있다(사본)"


@pytest.mark.asyncio
async def test_킥오프_시각_갱신은_유지된다():
    """⚠️ 반대 위험 — 중복을 막느라 **일정 갱신**을 잃으면 안 된다.
    종전 `ON CONFLICT` 는 `starts_at` 도 새로 썼다."""
    import inspect

    from app.collectors import fotmob as F

    src = inspect.getsource(F.upsert_slate)
    assert "starts_at" in src, "킥오프 갱신이 통째로 사라졌다"


# ── ⑤ 유럽 리그도 소급할 수 있어야 한다 (사용자 지시 2026-09-21) ──
def test_유럽_리그도_fotmob_이름이_있다():
    """🔴 소급 적재는 FotMob 하루치로 한다 — fd 가 주 소스여도 이름이 있어야
    그 리그를 고를 수 있다. 실측 팀당 종료 경기:
        리그앙 1.7 · 에레디비시 1.7 · 분데스 2.7 · EPL 3.2 · 세리에A 4.7 · 라리가 5.9
    **최근 5경기 폼도 안 되는 리그가 넷**이다."""
    from app.leagues import LEAGUES

    want = {"epl": "Premier League", "la_liga": "LaLiga", "serie_a": "Serie A",
            "bundesliga": "Bundesliga", "ligue1": "Ligue 1",
            "eredivisie": "Eredivisie"}
    for key, nm in want.items():
        assert LEAGUES[key].get("fotmob_league") == nm, key


def test_하위_여자부가_섞이지_않는다():
    """🔴 전부 접두사 관계다 — 부분 문자열이면 통째로 섞인다.
    `'Bundesliga' in '2. Bundesliga'` 는 **참**이다."""
    from app.collectors.fotmob import league_matches

    for name, key, ok in (
            ("Premier League", "epl", True),
            ("Premier League 2", "epl", False),
            ("Premier League U18", "epl", False),
            ("LaLiga", "la_liga", True), ("LaLiga2", "la_liga", False),
            ("Serie A", "serie_a", True), ("Serie B", "serie_a", False),
            ("Bundesliga", "bundesliga", True),
            ("2. Bundesliga", "bundesliga", False),
            ("Frauen-Bundesliga", "bundesliga", False),
            ("Ligue 1", "ligue1", True), ("Ligue 2", "ligue1", False),
            ("Eredivisie", "eredivisie", True),
            ("Eredivisie Vrouwen", "eredivisie", False)):
        assert league_matches(name, key) is ok, f"{name} → {key}"


def test_주_소스는_그대로_fd_다():
    """⚠️ 이름을 넣었다고 소스를 갈아타지 않는다 — 이미 오는 자료가 있다."""
    from app.leagues import LEAGUES

    for key in ("epl", "la_liga", "serie_a", "bundesliga", "ligue1", "eredivisie"):
        assert LEAGUES[key].get("result_source") == "fd", key


# ── ⑥ UEFA 본선 (사용자 지시 2026-09-21) ─────────────────────────
def test_UEFA_본선이_있다():
    from app.leagues import LEAGUES

    assert LEAGUES["ucl"]["fotmob_league"] == "Champions League"
    assert LEAGUES["uel"]["fotmob_league"] == "Europa League"


def test_UEFA_는_결과만_켠다():
    """⚠️ 자료가 없는 리그를 라우터·판정에 열면 **빈 카드**가 나간다
    (LGA-1 이 리그앙·에레디비시에서 같은 판단을 했다)."""
    from app.leagues import LEAGUES, features_of

    for key in ("ucl", "uel"):
        assert features_of(key) == ("results",), key
        assert not LEAGUES[key]["aliases"], f"{key}: 라우터에 노출된다"


def test_UEFA_예선과_여자부가_섞이지_않는다():
    """🔴 전부 포함 관계다 — 부분 문자열이면 예선 37경기가 본선으로 들어온다."""
    from app.collectors.fotmob import league_matches

    for name, key, ok in (
            ("Champions League", "ucl", True),
            ("Champions League Qualification", "ucl", False),
            ("Women's Champions League Qualification 3rd Round", "ucl", False),
            ("CAF Champions League Qualification", "ucl", False),
            ("AFC Champions League Elite East", "ucl", False),
            ("Europa League", "uel", True),
            ("Europa League Qualification", "uel", False),
            ("UEFA Women's Europa Cup", "uel", False)):
        assert league_matches(name, key) is ok, f"{name} → {key}"


def test_ACL_은_동서_조를_함께_받는다():
    """⚠️ ACL 은 `fotmob_contains` 로 남겨 뒀다 — East/West 로 나뉘어 오기
    때문이고, 그것이 의도된 동작이다."""
    from app.collectors.fotmob import league_matches

    assert league_matches("AFC Champions League Elite East", "acl") is True
    assert league_matches("AFC Champions League Elite West", "acl") is True


# ── ⑦ 나라를 안 보면 같은 이름 리그가 섞인다 (실측 2026-09-21) ────
def test_같은_이름_리그가_나라로_갈린다():
    """🔴 실측 — 캐시 45일치에서 같은 이름이 여러 나라에 있었다:

        'Premier League'  WAL 71 · BLR 59 · RUS 56 · KAZ 50 · ENG 50 ·
                          EGY 50 · UKR 48 · TAN 48
        'Serie A'         ECU 56 · ITA 50 · BRA 20
        'Bundesliga'      AUT 36 · GER 36
        'Ligue 1'         FRA 45 · ALG 28

    이름만 보고 적재했더니 EPL 에 **694경기**가 들어왔다(45일 상한은 ~70).
    웨일스·벨라루스·러시아 리그가 EPL 로 둔갑한 것이다.
    """
    from app.collectors.fotmob import league_matches

    for name, cc, key, ok in (
            ("Premier League", "ENG", "epl", True),
            ("Premier League", "WAL", "epl", False),
            ("Premier League", "RUS", "epl", False),
            ("Premier League", "EGY", "epl", False),
            ("Serie A", "ITA", "serie_a", True),
            ("Serie A", "ECU", "serie_a", False),
            ("Serie A", "BRA", "serie_a", False),
            ("Bundesliga", "GER", "bundesliga", True),
            ("Bundesliga", "AUT", "bundesliga", False),
            ("Ligue 1", "FRA", "ligue1", True),
            ("Ligue 1", "ALG", "ligue1", False)):
        assert league_matches(name, key, cc) is ok, f"{name} {cc} → {key}"


def test_국제대회는_나라를_따지지_않는다():
    """⚠️ ACL·UCL·UEL 은 ccode 가 INT 다 — 설정과 맞아야 한다."""
    from app.collectors.fotmob import league_matches

    assert league_matches("Champions League", "ucl", "INT") is True
    assert league_matches("Europa League", "uel", "INT") is True
    assert league_matches("AFC Champions League Elite East", "acl", "INT") is True


def test_모든_국내리그에_나라코드가_있다():
    """🔴 하나라도 빠지면 그 리그가 다시 오염된다."""
    from app.leagues import LEAGUES

    for key, cfg in LEAGUES.items():
        if not cfg.get("fotmob_league"):
            continue
        assert cfg.get("fotmob_ccode"), f"{key}: 나라 코드가 없다"


def test_적재가_나라코드를_넘긴다():
    import inspect

    from app.collectors import fotmob as F

    src = inspect.getsource(F.upsert_slate)
    assert 'r.get("ccode")' in src, "적재가 나라를 보지 않는다"
