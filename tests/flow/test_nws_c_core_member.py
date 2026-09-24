"""[NWS-C · NWS-A] 부상 기사가 **핵심 인물**일 때만, 그리고 **전 종목**에.

사용자 2026-09-24:
  "무조건 부상이라고 -1을 하면 안된다…기사에 난 인물이 기존 라인업
   **핵심 멤버**인지 확인해야 한다"
  "모든 경기에 적용되어야 한다…꼭 야구만 하지 말고"

🔴 NWS-S 가 배포된 직후 실측에서 잡힌 문제다. 낱말만 보고 방향을 줬다:
```
말소 — 삼성 연이틀 날벼락! 최원태도 1군 말소 "고관절 불편"   ← 선발투수. 맞다
부상 — 이럴 수가! 박건우 부상 말소→"2주 예상"                ← 주전. 맞다
```
   맞은 것은 우연이고, **후보 선수 한 명의 말소도 같은 −1** 이었다.
"""
from __future__ import annotations

import ast
import inspect

import pytest

from app.flow import attribution as A

_USUAL = {"slots": {"박건우": 2, "김성욱": 8}, "regulars": {"박건우"},
          "display": {"박건우": "박건우", "김성욱": "김성욱"}, "games": 10}


# ── 핵심 인물 ──────────────────────────────────────────────────────

def test_주전만_센다():
    assert A.core_name_in("이럴 수가! 박건우 부상 말소→2주 예상", _USUAL) == "박건우"
    assert A.core_name_in("김성욱 부상 말소", _USUAL) is None, "후보가 확률을 움직인다"


def test_투수는_타순에_없다_그래서_따로_받는다():
    """⚠️ 실물 — '최원태도 1군 말소'는 선발투수라 타순표로는 절대 못 잡는다."""
    assert A.core_name_in("삼성 최원태도 1군 말소", _USUAL) is None
    assert A.core_name_in("삼성 최원태도 1군 말소", _USUAL, ("최원태",)) == "최원태"


def test_명단을_모르면_안_움직인다():
    """🔴 "모른다"를 "없다"로 바꾸지 않는다."""
    assert A.core_name_in("누군가 부상 이탈", None) is None
    assert A.core_name_in("누군가 부상 이탈", {}) is None


def test_주전_판정을_다시_짓지_않았다():
    """🔴 무게는 `load.player_weight`, 원본은 `lineup_diff.usual_from` 이다."""
    src = inspect.getsource(A.core_name_in)
    assert "player_weight" in src
    assert "regulars" not in src.split('"""')[-1], "주전 기준을 손으로 다시 짰다"


def test_새_상수를_만들지_않았다():
    """⚠️ 문턱은 기존 `load.weight_regular` 를 그대로 쓴다."""
    src = inspect.getsource(A.core_name_in)
    assert "load.weight_regular" in src


# ── 방향 합산 ──────────────────────────────────────────────────────

def test_명단이_있어야_방향이_난다():
    t = {"away": [{"title": "이럴 수가! 박건우 부상 말소→2주 예상", "age_h": 1},
                  {"title": "김성욱 부상 말소", "age_h": 1}]}
    assert A.news_dir_sided(t) is None, "명단 없이 움직였다"
    got = A.news_dir_sided(t, rosters={"away": _USUAL})
    assert got["away"] == -1 and got["home"] == 0
    assert "박건우" in got["basis"] and "김성욱" not in got["basis"]


def test_축구는_확정XI_로_센다():
    """🔴 축구엔 평소 타순이 없다 — 확정 XI 를 `starters` 로 받는다."""
    t = {"home": [{"title": "Arsenal captain ruled out with injury", "age_h": 2}]}
    assert A.news_dir_sided(t) is None
    got = A.news_dir_sided(t, starters={"home": ["captain"]})
    assert got["home"] == -1


# ── 전 종목 ────────────────────────────────────────────────────────

def test_리그마다_언어가_다르다():
    """🔴 영어 하나로 12리그를 덮으면 고친 척이다 — 이 모듈 머리말의 실측:
    "영문명으로 던지면 72시간 필터가 전부 걸러낸다"."""
    from app.collectors.news_rss import locale_for

    assert locale_for("kbo", "")["hl"] == "ko"
    assert locale_for("npb", "")["hl"] == "ja"
    assert locale_for("soccer", "라리가")["hl"] == "es"
    assert locale_for("soccer", "세리에A")["hl"] == "it"
    assert locale_for("soccer", "분데스리가")["hl"] == "de"
    assert locale_for("soccer", "EPL")["gl"] == "GB"
    assert locale_for("soccer", "모르는리그") is None


def test_로케일_표가_한_곳이다():
    """🔴 사본 금지 — 원본은 `app.leagues` 다."""
    from app.collectors import news_rss as NR

    src = inspect.getsource(NR.locale_for)
    assert "app.leagues" in src and "news_locale" in src
    assert '"es"' not in src and "'es'" not in src, "언어표를 여기 또 적었다"


def test_모든_축구_리그에_로케일이_있다():
    """⚠️ 빠진 리그가 있으면 그 리그만 조용히 안 돈다."""
    from app.leagues import LEAGUES, news_locale

    missing = [k for k in LEAGUES if news_locale(k) is None]
    assert missing == [], f"로케일 없는 리그: {missing}"


# ── 배선의 끝 ──────────────────────────────────────────────────────

def _code_only(fn) -> str:
    tree = ast.parse(inspect.getsource(fn))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not body or not isinstance(body, list):
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            body.pop(0)
    return ast.unparse(tree)


def test_다섯번_노드가_명단을_넘긴다():
    from app.flow.nodes import n05_evidence as E

    code = _code_only(E._news_rss_dir)
    assert "_core_members" in code, "명단을 안 넘긴다"
    assert "rosters=" in code and "starters=" in code
    assert "locale_for" in code, "종목 목록을 손으로 적었다"
    core = _code_only(E._core_members)
    assert "usual_of" in core and "_xi_rows" in core
    assert "home_pitcher" in core, "투수를 빠뜨렸다"


@pytest.mark.asyncio
async def test_DB가_없으면_빈_명단이다():
    from app.flow.nodes import n05_evidence as E

    class _S:
        game_id = "1"
        sport = "baseball"
        league = "KBO"
        home = "KT Wiz"
        away = "NC Dinos"
        kickoff_utc = "2026-09-24T08:00:00+00:00"

    class _C:
        pool = None
        redis = None

    assert await E._core_members(_S(), _C()) == ({}, {})
