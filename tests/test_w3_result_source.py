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
