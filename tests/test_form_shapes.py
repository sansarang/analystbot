"""🔴🔴 **어댑터마다 폼의 꼴이 다르다** — 실측 2026-10-04 (MLB).

══════════════════════════════════════════════════════════════════
🔴 왜 — 야구·하키는 `recent_pattern` 변수를 **한 번도 못 만들었다**
══════════════════════════════════════════════════════════════════

밀워키 브루어스 vs 샌디에이고 파드리스. 깊이 소스가 폼을 **받아 왔는데**:

```
어댑터가 낸 것   games=18 · last_game=2026-09-30 · recent=[{...}×5]
분류기가 읽은 것  val["last5"]  → 🔴 **없다**
카드가 적은 것   §7 R7 — 최근 **0경기**, 3경기 미만은 패턴이 아니다
→ 변수 **1개** · 시나리오 **0개** · §7 R5 자료 부족
```

🔴 전수 조사(2026-10-04): `last5` 를 내는 어댑터는 **`fotmob` 하나**다.
   `mlb`·`nhl` 은 `recent=[{date, home, away, home_score, away_score, state}]`,
   `npb`·`kbo`·`kleague`·`fdorg`·`espn` 은 폼 사실이 **없다**.

⚠️ 그래서 축구(fotmob)만 폼 변수를 가졌고 **야구·하키는 통째로 못 가졌다.**
🔴 `W/D/L` 은 그 행의 **스코어에서 계산된다** — 지어내는 것이 하나도 없다.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from app.classify import RECENT_MIN, last5_of

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: 🔴 실측 꼴 그대로다(`app/collect/mlb.py parse_schedule_facts`).
MLB_RECENT = [
    {"date": "2026-09-25", "home": "Milwaukee Brewers",
     "away": "San Diego Padres", "home_score": 5, "away_score": 3,
     "state": "Final"},
    {"date": "2026-09-26", "home": "San Diego Padres",
     "away": "Milwaukee Brewers", "home_score": 2, "away_score": 7,
     "state": "Final"},
    {"date": "2026-09-27", "home": "Milwaukee Brewers",
     "away": "Chicago Cubs", "home_score": 1, "away_score": 1,
     "state": "Final"},
    {"date": "2026-09-28", "home": "Milwaukee Brewers",
     "away": "Chicago Cubs", "home_score": 0, "away_score": 4,
     "state": "Final"},
    {"date": "2026-10-04", "home": "Milwaukee Brewers",
     "away": "San Diego Padres", "home_score": None, "away_score": None,
     "state": "Preview"},
]


def test_MLB_꼴에서_승패를_계산한다():
    """🔴 홈이든 원정이든 **우리 쪽** 점수로 가린다."""
    got, why = last5_of({"team": "Milwaukee Brewers", "recent": MLB_RECENT})
    # 5-3 홈 승 · 7-2 원정 승 · 1-1 무 · 0-4 홈 패
    assert got == ["W", "W", "D", "L"], (got, why)
    assert "스코어로 계산했다" in why
    # 🔴 §7 R7 문턱을 **넘는다** — 이것이 이 수정의 요점이다
    assert len(got) >= RECENT_MIN


def test_상대_쪽에서는_뒤집힌다():
    got, _ = last5_of({"team": "San Diego Padres", "recent": MLB_RECENT})
    assert got == ["L", "L"], got      # 3-5 원정 패 · 2-7 홈 패


def test_끝나지_않은_경기는_안_센다():
    """🔴 예정 경기를 승패로 읽으면 거짓이 된다."""
    got, why = last5_of({"team": "Milwaukee Brewers", "recent": MLB_RECENT})
    assert len(got) == 4, (got, why)   # 5행 중 `Preview` 1행을 뺐다
    assert "건너뜀 1행" in why, why


@pytest.mark.parametrize("state,count", [
    ("Final", 1), ("OFF", 1), ("FINAL", 1), ("완료", 1),
    ("Preview", 0), ("Live", 0), ("In Progress", 0), ("", 0),
])
def test_끝남_표시는_어댑터_글자를_그대로_받는다(state, count):
    """⚠️ MLB `abstractGameState='Final'` · NHL `gameState='OFF'` — 실측 글자다."""
    row = {"home": "A", "away": "B", "home_score": 3, "away_score": 1,
           "state": state}
    got, _ = last5_of({"team": "A", "recent": [row]})
    assert len(got) == count, (state, got)


def test_어댑터가_직접_준_last5가_이긴다():
    """🔴 fotmob 은 `last5` 를 직접 준다 — 계산하지 않는다."""
    got, why = last5_of({"team": "X", "last5": ["W", "L", "D"],
                         "recent": MLB_RECENT})
    assert got == ["W", "L", "D"] and "어댑터가 줬다" in why


@pytest.mark.parametrize("val,needle", [
    ({"team": "X", "recent": []}, "`last5` 도 `recent` 도 없다"),
    ({"team": "", "recent": MLB_RECENT}, "어느 팀인지"),
    ({"team": "Nobody", "recent": MLB_RECENT}, "건너뜀 5행"),
])
def test_못_읽으면_사유를_남긴다(val, needle):
    """#3 조용한 0 금지 — *"0경기"* 만 적으면 자료가 안 온 것인지 못 읽은 것인지
    알 수 없다. 🔴 실측에서 내가 그 구분을 못 해 **엉뚱한 데를 봤다.**"""
    got, why = last5_of(val)
    assert got == [] and needle in why, why


def test_점수가_글자로_와도_읽는다():
    """⚠️ JSONB 가 문자열로 오는 것은 이 저장소가 전에 다친 자리다(CLAUDE.md #5)."""
    row = {"home": "A", "away": "B", "home_score": "4", "away_score": "2",
           "state": "Final"}
    assert last5_of({"team": "A", "recent": [row]})[0] == ["W"]


def test_부분_일치로_팀을_넓히지_않는다():
    """🔴 `Chicago White Sox` 와 `Chicago Cubs` 가 섞이면 승패가 거짓이 된다."""
    row = {"home": "Chicago Cubs", "away": "B", "home_score": 9,
           "away_score": 0, "state": "Final"}
    assert last5_of({"team": "Chicago", "recent": [row]})[0] == []


# ══════════════════════════════════════════════════════════════════
# 🔴 구조 계약 — 꼴을 고르는 자리가 **하나**인가
# ══════════════════════════════════════════════════════════════════


def test_last5를_직접_꺼내는_곳이_없다():
    """🔴 `val["last5"]` 를 여러 곳에서 꺼내면 새 어댑터가 또 빠진다.

    ⚠️ 실측 2026-10-04 에 정확히 그렇게 됐다 — `_dir_recent` 와 `sufficiency`
       두 곳이 각자 꺼냈고, MLB 를 추가할 때 **둘 다** 빠졌다.
    """
    src = (ROOT / "app" / "classify.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "last5_of")
    inside = {id(n) for n in ast.walk(fn)}
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or id(node) in inside:
            continue
        if ast.unparse(node.func).endswith(".get") and node.args \
                and isinstance(node.args[0], ast.Constant) \
                and node.args[0].value == "last5":
            bad.append(f"classify.py:{node.lineno} — {ast.unparse(node)}")
    assert not bad, (
        "🔴 `last5` 를 `last5_of` 밖에서 꺼낸다 — 어댑터 꼴을 고르는 자리는 "
        "**하나**여야 한다:\n  " + "\n  ".join(bad))


def test_recent_를_내는_어댑터가_실제로_있다():
    """🔴 이 계산이 **누구를 위한 것인지** 못 박는다.

    ⚠️ 어댑터가 꼴을 바꿔 `recent` 를 안 내게 되면 이 계산은 죽은 코드가 된다 —
       그때 빨개져야 한다(#2 배선).
    """
    found = []
    for name in ("mlb", "nhl"):
        src = (ROOT / "app" / "collect" / f"{name}.py").read_text(
            encoding="utf-8")
        if '"recent"' in src:
            found.append(name)
    assert found, ("🔴 `recent` 꼴을 내는 어댑터가 없다 — `last5_of` 의 계산 "
                   "경로가 죽은 코드다")


def test_한국어로_물어도_영문_폼_행과_이어진다():
    """🔴🔴 **3단계가 여기서 값을 낸다**(실측 2026-10-04).

    질문은 `밀워키 브루어스`(한국어)로 오고 어댑터의 `recent` 행은
    `Milwaukee Brewers`(영문)다. ⚠️ 이름끼리 비교하면 **0경기**가 되고, 그것이
    *"이름을 신원으로 쓴다"* 는 그 병이다 — 이 저장소가 네 번 다친 자리다.

    🔴 `tests/test_identity_contract.py` 가 내 첫 판(`team == home`)을 **잡았다.**
    """
    got, why = last5_of({"team": "밀워키 브루어스", "recent": MLB_RECENT})
    assert got == ["W", "W", "D", "L"], (got, why)


def test_열쇠로_가려도_다른_팀은_안_섞인다():
    """⚠️ 열쇠 비교가 느슨해지면 같은 도시 두 팀이 섞인다."""
    from app.classify import _same_team
    assert _same_team("밀워키 브루어스", "Milwaukee Brewers")
    assert not _same_team("Chicago Cubs", "Chicago White Sox")
    assert not _same_team("Chicago", "Chicago Cubs")
    assert not _same_team("", "Milwaukee Brewers")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **표본이 낡으면 약한 주장이다** (사용자 지시 2026-10-04)
# ══════════════════════════════════════════════════════════════════
#
#  > R1 "밀워키 최근 3경기 3승" 은 **7일 전 정규시즌 마지막 경기들**이다. 바이로
#  > 쉰 팀의 "최근 폼" 은 표본이 낡았다 — `recent_pattern` 에 **"마지막 경기가
#  > 7일 이상 전이면 weight 0.4"** 를 R7 옆에 붙여라.


def _form_fact(rest_days, n: int = 3):
    from app.cells import Fact
    rows = [{"date": f"2026-09-2{i}", "home": "Milwaukee Brewers",
             "away": "X", "home_score": 5, "away_score": 1, "state": "Final"}
            for i in range(5, 5 + n)]
    return Fact(question_id="lineup:MLB:Milwaukee Brewers:2026-10-04:depth:form",
                value={"team": "Milwaukee Brewers", "recent": rows,
                       "rest_days": rest_days},
                hardness="hard", source="https://statsapi.mlb.com/x",
                publisher="MLB statsapi", tier=1, extracted_by="t", step=1)


def _recent(rest_days, n: int = 3):
    from app import classify
    g = classify.Game(home="Milwaukee Brewers", away="San Diego Padres",
                      sport="baseball", league="MLB")
    got = [c for c in classify.classify_facts([_form_fact(rest_days, n)], g)
           if c.type == "recent_pattern"]
    assert got, "recent_pattern 유형이 안 붙었다 — 대역이 틀렸다"
    return got[0]


def test_문턱_안이면_hard_그대로():
    c = _recent(4)
    assert c.hardness == "hard" and c.weight == 1.0, (c.hardness, c.why)
    assert "낡았다" not in c.why, c.why


@pytest.mark.parametrize("rest", [7, 8, 21])
def test_칠일_이상이면_weight_0점4(rest):
    """🔴 사용자가 지정한 수 — **7일 이상 · 0.4**."""
    c = _recent(rest)
    assert c.weight == 0.4, (rest, c.hardness, c.weight, c.why)
    assert f"{rest}일 전" in c.why, c.why
    # 🔴 **변수이기는 하다** — 약해지는 것이고 사라지는 것이 아니다
    assert c.is_variable, c.why


def test_문턱과_등급은_yaml_이_정한다():
    """🔴 코드에 7 도 0.4 도 박지 않는다(사본 금지)."""
    from app import rules
    cfg = rules.variable_types()["recent_pattern"]
    assert cfg["stale_days"] == 7
    assert cfg["stale_hardness"] == "soft"
    src = (ROOT / "app" / "classify.py").read_text(encoding="utf-8")
    assert "stale_days" in src and "stale_hardness" in src
    # ⚠️ 숫자를 코드에 적지 않았나 — `stale` 문단에 `7` 이 없어야 한다
    i = src.index("stale_days")
    seg = src[i - 900:i + 400]
    assert " 7)" not in seg and "= 7" not in seg, "🔴 문턱을 코드에 박았다"


def test_날짜를_모르면_안_깎고_그_사실을_적는다():
    """🔴 모르는 것과 낡은 것은 **다르다** — 고칠 곳이 규칙 vs 수집이다.

    ⚠️ 첫 판은 `hardness == "hard"` 만 봤다. 그러면 돌연변이(`days is not None`
       검사 삭제)가 **통과한다** — `int(None)` 이 `try/except` 에 걸려 조용히
       `False` 가 되므로 겉보기 결과가 같다(실측 2026-10-04).
    🔴 **사유를 남기게** 하면 관측된다(#3 조용한 0 금지).
    """
    c = _recent(None)
    assert c.hardness == "hard", (c.hardness, c.why)
    assert "못 쟀다" in c.why, c.why
    assert "rest_days=None" in c.why, c.why


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **맞대결도 칸 이름이 갈린다** — 실측 2026-10-04
# ══════════════════════════════════════════════════════════════════
#
#  `_dir_h2h` 가 `home_goals` **하나만** 읽었다. 전수 조사:
#
#      fotmob                                 home_goals / away_goals
#      mlb · nhl · npb · kbo · fdorg · espn   home_score / away_score
#
#  🔴 그래서 야구·하키의 맞대결은 **전부 0승 0패**였다. 실측 카드 원문:
#
#      §4 h2h_pattern — 창 **13경기** 홈 0승 원정 0승, 갈려서 방향이 없다
#                         · 맞대결 표본 **0경기** → hardness hard→soft
#
#  ⚠️ 13경기를 받아 놓고 한 경기도 안 센 것이다 — `last5` 와 **같은 꼴 버그**다.
#  🔴 그리고 표본 수도 같은 병이었다(`window_games`·`window` 만 봤다).


def _h2h_fact(n: int = 9, *, key: str = "score"):
    from app.cells import Fact
    hs, as_ = (f"home_{key}", f"away_{key}")
    rows = [{"date": f"2026-06-{i:02d}", "home": "Milwaukee Brewers",
             "away": "San Diego Padres", hs: 5 if i % 3 else 2,
             as_: 1 if i % 3 else 7, "state": "Final"}
            for i in range(1, n + 1)]
    return Fact(question_id="lineup:MLB:Milwaukee Brewers:2026-10-04:depth:h2h",
                value={"matches": rows, "count": len(rows)},
                hardness="hard", source="https://statsapi.mlb.com/x",
                publisher="MLB statsapi", tier=1, extracted_by="t", step=1)


def _h2h(n: int = 9, *, key: str = "score"):
    from app import classify
    g = classify.Game(home="Milwaukee Brewers", away="San Diego Padres",
                      sport="baseball", league="MLB")
    got = [c for c in classify.classify_facts([_h2h_fact(n, key=key)], g)
           if c.type == "h2h_pattern"]
    assert got, "h2h_pattern 유형이 안 붙었다"
    return got[0]


def test_맞대결이_정본_칸으로_읽힌다():
    """🔴🔴 **v5 §8-3 으로 바뀠다**(2026-10-04).

    ⚠️ 종전 이 시험은 `home_score`·`home_goals` **둘 다** 읽히는지를 봤다 —
       읽는 쪽에 `or` 분기가 있었기 때문이다. 🔴 §11-1 이 금지한 **증상 수정**이
       그것이고, §8-3 이 *"어댑터 안에서 변환하고 밖으로 나오지 않는다"* 로 닫았다.
    🔴 그래서 지금은 **정본 하나**(`home_score`)만 읽는다. fotmob 이 어댑터
       안에서 바꿔 내고, 그 사실은 `tests/contracts/test_v5_8_3_fact_schema.py` 가
       지킨다.
    """
    c = _h2h(9, key="score")
    assert c.is_variable, (c.why, c.undecided)
    assert c.direction == "home", (c.direction, c.why)
    assert "9경기 홈 6승 원정 3승" in c.why, c.why


def test_맞대결_표본_수도_matches_를_센다():
    """🔴 `count`·`matches` 를 안 보면 표본이 **0경기**가 되고 soft 로 깎인다."""
    c = _h2h(9)
    assert "표본 9경기" in c.why, c.why
    assert "표본 0경기" not in c.why, c.why
    # ⚠️ 9경기는 `h2h_min_games`(8) 위다 — 그래도 hard 는 아니다(§4 sample_weight)
    assert c.hardness in ("hard", "likely"), (c.hardness, c.why)


def test_score_of_가_한_곳이다():
    """🔴 칸 이름을 고르는 자리가 둘이면 새 호출부가 또 빠진다.

    ⚠️ 실측 2026-10-04 에 정확히 그렇게 됐다 — `last5_of` 는 `home_score` 만,
       `_dir_h2h` 는 `home_goals` 만 읽었다.
    """
    import ast
    src = (ROOT / "app" / "classify.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "score_of")
    inside = {id(n) for n in ast.walk(fn)}
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or id(node) in inside:
            continue
        if ast.unparse(node.func).endswith(".get") and node.args \
                and isinstance(node.args[0], ast.Constant) \
                and str(node.args[0].value) in ("home_goals", "away_goals",
                                                "home_score", "away_score"):
            bad.append(f"classify.py:{node.lineno} — {ast.unparse(node)}")
    assert not bad, (
        "🔴 점수 칸을 `score_of` 밖에서 꺼낸다 — 어댑터 꼴을 고르는 자리는 "
        "**하나**여야 한다:\n  " + "\n  ".join(bad))
