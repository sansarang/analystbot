"""[KEY-1] 흐름이 **엉뚱한 키**로 기사를 찾고 있었다.

사용자 2026-09-24: "배당이 바뀌면 근거를 찾은 경우가 있었니?" → **0건**.
근거가 없어서가 아니라 **읽지를 않아서**였다.

🔴 실측 2026-09-24 10:17 (배포 14시간 뒤):
```
Go 가 쌓은 것     crawl:news_mlb:2026-09-24:changes   317건
                  crawl:news_npb:…                    295건
                  crawl:news_kbo:…                    274건   → 합 886건
흐름이 읽은 것     19경기 전건 observed=False · 근거 찾은 이동 **0건**

load_changes('news_mlb',      '2026-09-24') → 5건  ✅
load_changes('news_baseball', '2026-09-24') → 0건  🔴 ← 흐름이 부르던 것
```

🔴 **원인 둘 다 내 잘못이다:**
```
① code_for(league, sport) 인데 code_for(sport, league) 로 **인자를 바꿔** 불렀다
   → code_for('baseball','MLB') = 'baseball'  (league 자리에 sport 가 들어감)
② ⑤에 이미 `_sport_code` 가 있는데 ②에 `_league_code` 를 **새로 지었다**(사본)
```

⚠️ 분류가 전건 `unobserved` 로 나온 것은 **코드가 정직했던 것**이다 —
   찾아보지도 않고 "자금"이라 부르지 않았다(NWS-D 의 그 구분이 작동했다).
"""
from __future__ import annotations

import inspect

import pytest

from app.flow.nodes import n02_market as N2


def test_야구는_리그_코드로_찾는다():
    """🔴 Go 는 `crawl:news_mlb:…` 로 쌓는다. `baseball` 로 찾으면 0건이다."""
    class _S:
        sport = "baseball"
        league = "MLB"

    assert N2._news_code(_S()) == "mlb"
    _S.league = "KBO"; assert N2._news_code(_S()) == "kbo"
    _S.league = "NPB"; assert N2._news_code(_S()) == "npb"


def test_축구는_종목_코드다():
    """⚠️ `games.sport` 열의 실제 값이 그렇게 생겼다 — 야구는 리그별로
    sport 가 갈리고 축구는 전부 `soccer` 다."""
    class _S:
        sport = "soccer"
        league = "EPL"

    assert N2._news_code(_S()) == "soccer"


def test_코드를_다시_짓지_않았다():
    """🔴 사본 금지 — ⑤의 `_sport_code` 가 원본이다. 내가 ②에 똑같은 것을
    새로 지어서 인자 순서를 틀렸다."""
    # ⚠️ **독스트링을 뗀다** — 위 설명이 `code_for`·`mlb` 를 그대로 담고 있어
    #    원문 grep 이 거짓으로 실패한다(D46, 17회째).
    import ast

    tree = ast.parse(inspect.getsource(N2._news_code).strip())
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if body and isinstance(body, list):
            first = body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                body.pop(0)
    code = ast.unparse(tree)
    assert "sport_code" in code, "원본을 안 쓴다"
    assert "code_for" not in code, "인자 순서를 틀린 그 함수를 다시 쓴다"
    assert "'mlb'" not in code, "리그 이름을 손으로 적었다"


def test_두_구현이_같은_답을_낸다():
    """🔴 **이 계약이 이번 사고를 막는다.** ②와 ⑤가 다른 답을 내면 한쪽이
    빈 키를 두드린다. 원본은 `labels.sport_code` 하나다 — 노드끼리
    import 하지 않는 규약을 지키면서 사본을 없애는 유일한 자리다."""
    from app.flow.labels import sport_code
    from app.flow.nodes import n05_evidence as N5

    class _S:
        sport = ""
        league = ""

    for sp, lg in (("baseball", "MLB"), ("baseball", "KBO"), ("baseball", "NPB"),
                   ("soccer", "EPL"), ("soccer", "J1"), ("", "")):
        _S.sport, _S.league = sp, lg
        want = sport_code(_S())
        assert N2._news_code(_S()) == want, (sp, lg)
        assert N5._sport_code(_S()) == want, (sp, lg)


@pytest.mark.asyncio
async def test_2가_두_키를_다_읽는다():
    """⚠️ 라인업 변화(`crawl:<코드>:…`)와 기사(`crawl:news_<코드>:…`)는
    **다른 키**다. 둘 다 읽어야 한다."""
    seen = []

    class _R:
        async def lrange(self, key, *a):
            seen.append(key)
            return []

    class _Ctx:
        inject: dict = {}
        pool = None
        redis = _R()

    class _S:
        game_id = "1"
        sport = "baseball"
        league = "MLB"
        kickoff_utc = "2026-09-24T02:10:00+00:00"

    await N2._changes(_S(), _Ctx())
    assert any(k.startswith("crawl:mlb:") for k in seen), seen
    assert any(k.startswith("crawl:news_mlb:") for k in seen), seen
    assert not any("baseball" in k for k in seen), f"아직 종목명으로 찾는다: {seen}"


# ── 영문 리그 팀 매칭 ───────────────────────────────────────────────

def test_영문_제목은_우리_팀_이름으로_맞춘다():
    """🔴 [실측 2026-09-24] `_local_names` 는 KBO(한글)·NPB(일어) **22개뿐**이고
    MLB 가 없다. 그런데 MLB 제목은 팀명이 영문 그대로 나온다:
    ```
    "Rangers Set Probable Pitchers … with Athletics"
    "Astros vs Braves series preview …"
    ```
    그래서 대조표를 새로 만들지 않고 **우리가 가진 팀 이름**으로 맞춘다.
    """
    from app.flow import attribution as A

    teams = ("Athletics", "Los Angeles Angels")
    c = {"at": "2026-09-24T01:00:00+00:00", "field": "h", "from": "",
         "to": "2026-09-24T01:00:00+00:00|Rangers Set Probable Pitchers with Athletics"}
    assert A._is_ours(c, teams) is True
    c2 = dict(c, to="2026-09-24T01:00:00+00:00|Astros vs Braves series preview")
    assert A._is_ours(c2, teams) is False


def test_별명으로도_맞춘다():
    """⚠️ 제목은 전체 이름 대신 별명을 쓴다 — "Houston Astros" → "Astros"."""
    from app.flow import attribution as A

    c = {"at": "2026-09-24T01:00:00+00:00", "field": "h", "from": "",
         "to": "2026-09-24T01:00:00+00:00|Astros vs Braves series preview"}
    assert A._is_ours(c, ("Houston Astros", "Seattle Mariners")) is True


def test_짧은_별명은_쓰지_않는다():
    """🔴 반대 위험 — 3자 이하 별명("Sox"·"Jays")은 우연히 걸린다."""
    from app.flow import attribution as A

    c = {"at": "2026-09-24T01:00:00+00:00", "field": "h", "from": "",
         "to": "2026-09-24T01:00:00+00:00|Boxing news roundup"}
    assert A._is_ours(c, ("Chicago Sox", "New York Jays")) is False


def test_대조표를_새로_만들지_않았다():
    """🔴 사본 금지 — MLB 팀 목록을 코드에 적지 않는다. `state.home/away` 가
    원본이다."""
    import inspect

    from app.flow import attribution as A

    src = inspect.getsource(A._is_ours)
    for banned in ('"Athletics"', "'Athletics'", '"Yankees"', "'Dodgers'"):
        assert banned not in src, banned


def test_뉴스의_가짜_경기키에_속지_않는다():
    """🔴 **실측 2026-09-24가 잡은 마지막 자리.** Go 는 뉴스를
    `NewsKey(리그)` = `"news_mlb"` 라는 가짜 경기 키에 담는다.
    ```
    raw=True(제목에 Houston Astros 있음)  ·  is_ours=False   ← 28건 전부
    ```
    `game` 칸이 있으면 거기서 끝내버려 **제목을 보지도 않았다.**
    진짜 경기 키는 `"원정@홈#id"` 라 `@` 가 있다.
    """
    from app.flow import attribution as A

    at = "2026-09-24T01:00:00+00:00"
    news = {"at": at, "game": "news_mlb", "field": "abc", "from": "",
            "to": f"{at}|Houston Astros Announce Probable Starting Pitchers"}
    assert A._is_ours(news, ("Houston Astros", "Seattle Mariners")) is True
    assert A._is_ours(news, ("New York Mets", "Texas Rangers")) is False

    # ⚠️ 반대 위험 — 진짜 경기 키는 종전대로 경기 이름으로 가린다
    real = {"at": at, "game": "Kia Tigers@Doosan Bears#1", "field": "lineup_home",
            "from": "", "to": "김호령-김민규"}
    assert A._is_ours(real, ("Doosan Bears", "Kia Tigers")) is True
    assert A._is_ours(real, ("KT Wiz", "NC Dinos")) is False
