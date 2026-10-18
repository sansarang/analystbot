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
