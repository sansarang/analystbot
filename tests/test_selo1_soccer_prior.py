"""[SELO-1 2026-09-20] 축구 ① 사전값이 **구조적으로 없었다.**

🔴 실측 2026-09-20 (STEP 0-e):
     축구 7리그 전부 `① 사전값 = null — elo 캐시 키 없음`
     Redis `elo:*` = mlb·kbo·npb 뿐. 축구 키 **0개**
     오늘 슬레이트 32경기 중 `n03_freeze` **21건**(그중 18건이 축구)

🔴 왜 그랬나 — `bridge.ELO_SPORTS = ("mlb","kbo","npb")` 가 축구를 뺐다.
   뺀 이유는 주석에 있다: `team_elo.refresh` 가 `WHERE sport=$1` 로 긁는데
   축구 캐시 키는 **리그 코드**라 종목으로 긁으면 리그 간 비교가 된다.

🔴 갈림길 셋을 **실측으로** 닫았다(docs/FORKS.md F-21):
   (a) 자체 Elo   — 축구 종료 경기가 팀당 2.5~5.1 (야구 35~71). **기각**
   (b) ClubElo API — 전 엔드포인트 502 · Fixtures deactivated. **기각**
   (c) football-data.co.uk (`soccer_elo`) — 서버에서 refresh 성공, 10리그.
       유일하게 남았다. 막는 것은 **이름 불일치**뿐이었다(144팀 중 2개 일치).
"""
from __future__ import annotations

import pathlib

import pytest
import yaml

CFG = pathlib.Path(__file__).resolve().parents[1] / "config" / "elo_names.yaml"


def test_대조표가_있다():
    assert CFG.exists(), "config/elo_names.yaml 이 없다"
    doc = yaml.safe_load(CFG.read_text(encoding="utf-8")) or {}
    assert doc.get("elo_names"), "elo_names 키가 비었다"


def test_대조표는_리그별_1대1이다():
    """🔴 같은 elo 이름에 **다른 팀**이 붙으면 레이팅이 섞인다.

    ⚠️ 우리 표기 중복은 허용한다 — `Alavés` / `Deportivo Alavés` 는 같은
       팀이다. 판정 기준은 **한쪽 토큰이 다른 쪽에 전부 들어 있는가** 이고,
       그러면 같은 클럽의 긴 표기/짧은 표기다. 그게 아니면 다른 팀이다.
    """
    import unicodedata

    stop = {"fc", "afc", "cf", "rcd", "rc", "ca", "cd", "sc", "ac", "de", "and",
            "club", "real", "deportivo", "calcio", "cfc", "us", "ss", "ssc",
            "acf", "balompie", "bk", "if", "1895", "07", "04", "1"}

    def toks(n):
        t = unicodedata.normalize("NFKD", n)
        t = "".join(c for c in t if not unicodedata.combining(c))
        for ch in "&.-'":
            t = t.replace(ch, " ")
        return {x for x in t.lower().split() if x not in stop}

    doc = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    for lg, box in (doc["elo_names"] or {}).items():
        seen: dict = {}
        for ours, elo in (box or {}).items():
            seen.setdefault(elo, []).append(ours)
        for elo, names in seen.items():
            if len(names) == 1:
                continue
            sets = [toks(n) for n in names]
            base = min(sets, key=len)
            for other in sets:
                assert base <= other or other <= base, \
                    f"{lg}: {elo} 에 다른 팀들이 붙었다 — {names}"


def test_축구도_elo_보장_대상이다():
    """🔴 `ensure_elo` 가 축구를 지나치면 ①은 영영 None 이다."""
    import inspect

    from app.flow import bridge

    src = inspect.getsource(bridge)
    assert "soccer" in src.split("ELO_SPORTS")[1][:400] or "ensure_soccer_elo" in src, \
        "bridge 가 축구 elo 를 보장하지 않는다"


def test_soccer_elo가_redis에_싣는_함수를_가진다():
    from app.models import soccer_elo as SE

    assert hasattr(SE, "publish_ratings"), "레이팅을 캐시에 싣는 함수가 없다"


def test_대조표에_없는_팀은_지어내지_않는다():
    """🔴 미매칭은 **비워 둔다.** 리그 평균으로 메우면 ③이 오분류한다."""
    from app.models.soccer_elo import ratings_for_league

    got = ratings_for_league("K리그1", {"E0": {"Arsenal": 1800}})
    assert got == {}, got


def test_아티팩트는_볼륨에_둔다(monkeypatch):
    """🔴 이미지 안에 두면 **배포할 때마다 날아간다.**

    실측 2026-09-20: SELO-1 배포 직후 `ratings.json 리그 0` 이라 축구 ①이
    전건 `elo 미기입` 이었다. 볼륨 경로는 Railway 가 env 로 준다.
    """
    import importlib

    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", "/data")
    from app.models import soccer_elo as SE

    importlib.reload(SE)
    assert str(SE.DATA_DIR) == "/data/elo", SE.DATA_DIR
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH")
    importlib.reload(SE)
    assert str(SE.DATA_DIR).endswith("data/elo"), SE.DATA_DIR


@pytest.mark.asyncio
async def test_아티팩트가_없으면_하루_한_번만_피팅한다():
    """⚠️ CSV 를 매번 내려받으면 슬레이트가 그만큼 느려진다."""
    from app.models import soccer_elo as SE

    calls = {"n": 0}

    class _R:
        def __init__(self):
            self.mark = {}

        async def set(self, k, v, ex=None, nx=False):
            if nx and k in self.mark:
                return False
            self.mark[k] = v
            return True

    def _fake_refresh():
        calls["n"] += 1

    r = _R()
    import unittest.mock as M

    with M.patch.object(SE, "refresh", _fake_refresh), \
         M.patch.object(SE, "_load_ratings_file", lambda: {}):
        await SE.ensure_ratings_file(r, "2026-09-20")
        await SE.ensure_ratings_file(r, "2026-09-20")
    assert calls["n"] == 1, calls


def test_캐시_코드_규칙은_한_곳이다():
    """🔴 [SELO-1c] 쓰는 쪽과 읽는 쪽이 규칙을 따로 갖고 있어 어긋났다.

    실측 2026-09-20: `elo:EPL:{날짜}` 로 쓰고 `elo:epl:{날짜}` 로 읽어
    EPL·J1 이 전건 `elo 미기입` 이었다. 한글 리그는 `.lower()` 가 무해해
    **덴마크만 우연히** 맞았다.
    """
    import inspect

    from app.flow.nodes import n01_prior
    from app.models import soccer_elo as SE
    from app.models.team_elo import code_for

    assert "code_for" in inspect.getsource(n01_prior._code)
    assert "code_for" in inspect.getsource(SE.publish_ratings)
    # 같은 입력 → 같은 코드
    for lg in ("EPL", "J1 리그", "라리가", "세리에A", "덴마크 수페르리가"):
        assert code_for(lg, "soccer") == lg.lower()
    assert code_for("MLB", "mlb") == "mlb"


def test_한글_리그_라벨이_CSV_코드로_풀린다():
    """🔴 우리 `games.league` 는 한글이다. 영문 키만 있으면 전건 미기입이다."""
    from app.models.soccer_elo import LABEL_TO_CODE

    def code(lg):
        low = lg.lower()
        return next((c for k, c in LABEL_TO_CODE if k in low), None)

    assert code("라리가") == "SP1"
    assert code("세리에A") == "I1"
    assert code("분데스리가") == "D1"
    assert code("EPL") == "E0"
    assert code("J1 리그") == "JPN"
    assert code("덴마크 수페르리가") == "DNK"
    assert code("K리그1") is None, "없는 리그를 억지로 매핑하면 안 된다"
