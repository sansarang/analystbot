"""[NWS-D] 기사의 호재·악재를 판정해 **예측을 움직인다.**

사용자 2026-09-23: "기사가 악재인가 호재인가를 판단해서 부상이나 다른 문제가
있으면 **예측에 무조건 좌우되어야 한다**. 그리고 **배선이 되어 있어야 한다**."

🔴 MOV-C 로 기사는 들어왔는데 **시각만** 썼다. 라벨만 붙고 확률은 한 톨도
   안 움직였다. 여기서 방향을 붙여 ⑤→⑦→⑧까지 잇는다.

⚠️ **앞서 잰 49.7% 는 다른 것이다**(내가 요지를 놓쳤다). `lineup_type_ledger`
   634건 49.7% 는 `regular_out`("오늘 라인업에 없다")이고 휴식·플래툰이 섞여
   있다. **부상 결장과 하루 휴식을 구분하지 못한다** — 그 구분이 기사가 하는
   일이다. 49.7% 는 이 작업을 부정하지 않고 왜 필요한지를 보여준다.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.flow import attribution as A

T = dt.datetime(2026, 9, 23, 9, 0, tzinfo=dt.UTC)
KBO = ("Doosan Bears", "Kia Tigers")


# ── 방향 판정 ───────────────────────────────────────────────────────

def test_악재만_있으면_음수():
    d = A.direction_of("두산 강승호 부상으로 엔트리 말소", KBO)
    assert d["dir"] == -1 and d["team"] == "Doosan Bears"
    assert d["word"] in ("부상", "말소")


def test_호재만_있으면_양수():
    d = A.direction_of("KIA 나성범 1군 등록, 오늘 복귀전", KBO)
    assert d["dir"] == 1 and d["team"] == "Kia Tigers"


def test_둘_다_있으면_지어내지_않는다():
    """🔴 "부상 딛고 복귀"를 악재로 읽으면 정반대가 된다."""
    assert A.direction_of("두산 강승호 부상 딛고 1군 복귀", KBO) is None


def test_낱말이_없으면_없다():
    assert A.direction_of("두산 오늘 선발 라인업 발표", KBO) is None
    assert A.direction_of("", KBO) is None
    assert A.direction_of(None, KBO) is None


def test_팀을_못_찾으면_없다():
    """🔴 리그 맥락 기사를 특정 경기에 붙이지 않는다."""
    assert A.direction_of("'류지현호' 주전 포수 부상", KBO) is None
    assert A.direction_of("삼성 구자욱 부상", KBO) is None


@pytest.mark.parametrize("title,teams,want", [
    ("巨人 坂本 故障で登録抹消", ("Yomiuri Giants", "Chunichi Dragons"), -1),
    ("ヤクルト 山田 一軍登録 復帰", ("Tokyo Yakult Swallows", "Hanshin Tigers"), 1),
])
def test_일본어도_읽는다(title, teams, want):
    d = A.direction_of(title, teams)
    assert d and d["dir"] == want, (title, d)


def test_사전을_코드에_적지_않았다():
    """🔴 원본은 `config/evidence_lexicon.yaml` 하나다."""
    import inspect

    src = inspect.getsource(A)
    for banned in ('"부상"', "'부상'", '"故障"', '"injury"'):
        assert banned not in src, banned


def test_사전에_방향_블록이_있다():
    from app.engine.scout_config import LEXICON_DIR

    assert set(LEXICON_DIR) >= {"bad", "good"}
    assert "부상" in LEXICON_DIR["bad"]["ko"]
    assert "복귀" in LEXICON_DIR["good"]["ko"]
    # ⚠️ 같은 낱말이 양쪽에 있으면 판정이 영영 None 이 된다.
    for lang in ("ko", "ja", "en"):
        bad = set(LEXICON_DIR["bad"].get(lang) or [])
        good = set(LEXICON_DIR["good"].get(lang) or [])
        assert not (bad & good), (lang, bad & good)


# ── ② 합산 ──────────────────────────────────────────────────────────

def _news(mins, title):
    at = (T + dt.timedelta(minutes=mins)).isoformat()
    return {"at": at, "field": "abc", "from": "", "kind": "added",
            "to": f"{at}|{title}"}


def test_팀별로_합산한다():
    got = A.news_dir([_news(10, "두산 강승호 부상 말소")], KBO, at=T)
    assert got["home"] == -1 and got["away"] == 0
    assert "부상" in got["basis"] or "말소" in got["basis"]


def test_한_팀에_악재와_호재가_섞이면_0():
    got = A.news_dir([_news(10, "두산 강승호 부상 말소"),
                      _news(20, "두산 양석환 1군 등록")], KBO, at=T)
    assert got["home"] == 0, got


def test_창_밖_기사는_안_쓴다():
    """⚠️ 창 폭은 MOV-C 의 `move.window_min` 을 재사용한다(사본 금지)."""
    assert A.news_dir([_news(600, "두산 강승호 부상 말소")], KBO, at=T)["home"] == 0


def test_기사가_없으면_None():
    assert A.news_dir([], KBO, at=T) is None
    assert A.news_dir(None, KBO, at=T) is None


# ── ⑤ 증거 행 ──────────────────────────────────────────────────────

class _Ctx:
    inject: dict = {}
    pool = None
    redis = None


def _state(news_dir=None, *, market=True):
    from app.flow.state import State

    s = State(run_id="r", game_id="1", sport="baseball", league="KBO",
              home="Doosan Bears", away="Kia Tigers",
              kickoff_utc="2026-09-23T09:30:00+00:00")
    s.hyp_side = s.pick_side = "home"
    s.n01_prior = {"p_home": 0.52, "p_away": 0.48}
    s.n02_market = ({"p": {"home": 0.5, "draw": None, "away": 0.5},
                     "move": {"news_dir": news_dir}} if market else None)
    s.n04_hyp = [{"id": "H", "vars": [{"var": "news_injury", "is_core": False}]}]
    return s


@pytest.mark.asyncio
async def test_5가_증거_행을_만든다():
    from app.flow.nodes import n05_evidence as N5

    nd = {"home": -1, "away": 0, "basis": "부상 — 두산 강승호 말소"}
    out = await N5.run(_state(nd), _Ctx())
    row = next(e for e in out.n05_evidence if e["var"] == "news_injury")
    assert row["direction"]["home"] == -1
    assert row["status"] == ""
    assert "부상" in row["raw_excerpt"]


@pytest.mark.asyncio
async def test_기사가_없으면_미실행이다():
    """🔴 0 과 모름은 다르다. 소스가 없으면 ⑥ 분모에서 빠진다."""
    from app.flow.nodes import n05_evidence as N5

    out = await N5.run(_state(None), _Ctx())
    row = next(e for e in out.n05_evidence if e["var"] == "news_injury")
    assert row["status"] == "미실행", row


# ── ⑦ 배선의 끝 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_7이_그_행으로_확률을_움직인다():
    """🔴 **사용자 요구가 이것이다** — "예측에 무조건 좌우되어야 한다"."""
    from app.flow.nodes import n05_evidence as N5
    from app.flow.nodes import n07_adjust as N7

    nd = {"home": -1, "away": 0, "basis": "부상 — 두산 강승호 말소"}
    s = await N5.run(_state(nd), _Ctx())
    s.n06_verdict = {"per_var": {"news_injury": "confirmed"}}
    s = await N7.run(s, _Ctx())
    adj = [a for a in (s.n07_adjust or []) if a["var"] == "news_injury"]
    assert adj, f"기사가 확률을 안 움직였다: {s.n07_adjust}"
    assert adj[0]["pp"] < 0, adj


def test_변수가_config_에_있고_한_줄로_끌_수_있다():
    """🔴 되돌릴 길 — 이 줄을 지우면 ④⑤⑥⑦에서 통째로 사라진다."""
    from app.flow import rules as R

    spec = (R.vars_for("baseball") or {}).get("news_injury")
    assert spec, "변수가 없다 — ⑦이 영영 안 집는다"
    assert 0 < float(spec["max_abs"]) <= 2.5
    assert spec.get("core") is False


def test_5가_변수표를_보고_움직인다():
    """🔴 **배선의 끝.** 변수표에서 빼면 ⑤도 그 행을 만들지 않아야 한다 —
    한 곳만 끊겨도 조용한 0 이 된다(사용자 지시 2026-09-23)."""
    import inspect

    from app.flow.nodes import n05_evidence as N5

    src = inspect.getsource(N5)
    assert "news_injury" in src, "⑤에 분기가 없다"


def test_상대_표기는_주체가_아니다():
    """🔴 **실측 2026-09-23 라이브 RSS 가 잡은 오탐.**
    "'SSG 대체 외인' 마드리스, 16일 **LG전**이 마지막! 에레디아 21일 1군 복귀"
    → SSG 기사인데 LG 호재로 붙었다. `LG전` 은 "LG를 상대로"다.
    """
    lg = ("LG Twins", "KT Wiz")
    assert A.direction_of("SSG 에레디아, LG전 앞두고 1군 복귀", lg) is None
    # ⚠️ 반대 위험 — 주체로 나오면 그대로 잡아야 한다
    d = A.direction_of("LG 김윤식 1군 복귀", lg)
    assert d and d["team"] == "LG Twins"


def test_같은_팀이_두_번_나오면_주체_쪽을_본다():
    """⚠️ "LG전 ... LG 김윤식 복귀" 처럼 상대 표기와 주체가 함께 나오면
    주체가 이긴다 — 먼저 나온 것만 보고 포기하면 안 된다."""
    lg = ("LG Twins", "KT Wiz")
    d = A.direction_of("KT, LG전 앞두고… LG 김윤식 1군 복귀", lg)
    assert d and d["team"] == "LG Twins"


def test_문법_규칙을_사전에_넣지_않았다():
    """⚠️ `evidence_lexicon.yaml` 은 '무엇이 악재인가'의 목록이다.
    조사(`전`)는 낱말이 아니라 문법이라 코드에 둔다 — 섞으면 둘 다 흐려진다."""
    from app.engine.scout_config import LEXICON_DIR

    for kind in ("bad", "good"):
        for words in LEXICON_DIR[kind].values():
            assert "전" not in words
