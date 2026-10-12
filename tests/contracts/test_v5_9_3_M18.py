"""🔴🔴 **M18** — 야구는 `pitcher_state` 없이 총점·핸디를 적지 않는다.

v4 §15 M18 원문 네 번째 칸: *"계약: pitcher_state 없는 야구 경기에
total/handicap verdict name 이면 실패"*.

══════════════════════════════════════════════════════════════════
🔴 그 계약이 **코드에 없었다** (실측 2026-10-04 · 전수 검색)
══════════════════════════════════════════════════════════════════

v4 가 *"계약"* 이라고 적어 둔 것이 **문서 한 줄**에만 있고 `app/` 에는 한 글자도
없었다 — v4 §15 가 막으려던 바로 그 꼴이다(CLAUDE.md #2 배선).

사용자 지시 2026-10-04(밀워키 vs 샌디에이고 카드를 보고):

> 야구 포스트시즌 1차전 카드에 `pitcher_state` 변수가 **0개**다 … 카드는 밀워키
> -0.5·샌디에이고 +1.5 생존율을 **계산해서 냈다.** 결론이 "없음"이라 돈은 안
> 나갔지만, **계약이 안 물린 것이다.**

⚠️ 사용자의 읽기가 v4 보다 **엄하다** — v4 는 `name` 만, 사용자는 *"결론 금지"* 다.
   🔴 직접 지시가 이긴다: `small` 도 막는다(소액도 돈을 걸라는 말이다).
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from app import classify, survive
from app.scenarios import Draft

ROOT = pathlib.Path(__file__).resolve().parents[2]

WORD_TO_MARKET = {"총점": "total", "핸디": "handicap"}

V4 = pathlib.Path(ROOT / "docs" / "fable" / "inbox" / "2026-09-29_v4.md")


def _game(sport: str = "baseball"):
    return classify.Game(home="Milwaukee Brewers", away="San Diego Padres",
                         sport=sport, league="MLB",
                         home_id="team:000338", away_id="team:000325")


def _drafts():
    """🔴 실측 카드의 그 세트다(블록 6)."""
    return [Draft(id="A", scores=["3-0", "3-1", "2-1"], strength=2.0,
                  template_id="baseball_ace_low", why="테스트"),
            Draft(id="B", scores=["0-3", "1-3", "1-2"], strength=1.0,
                  template_id="mirror:baseball_ace_low", why="테스트")]


def _var(vtype: str, direction: str = "home"):
    return classify.Classified(
        text="테스트", source_url="https://statsapi.mlb.com/x",
        hardness="hard", type=vtype, direction=direction, why="테스트")


def _graded(res, kinds=("total", "handicap")):
    return [m for m in res.markets
            if str(m.market_type) in kinds and str(m.verdict) != "none"]


# ══════════════════════════════════════════════════════════════════
# 🔴 물리나
# ══════════════════════════════════════════════════════════════════


# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_M18_선발을_모르면_총점_핸디에_등급이_없다`

# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_M18_생존_수는_그대로_보여_준다`

# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_M18_선발을_알면_막지_않는다`

# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_M18_축구에는_안_건다`

# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_M18_변수를_안_주면_막지_않는다`

# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_M18_배경으로_떨어진_pitcher_state는_없는_것으로_센다`

def test_M18_mlb_깊이_소스에_예고_선발이_있다():
    """🔴 `_probable` 은 **이미 있었다** — 슬레이트 행에만 들어가고 질문 경로의
    깊이 소스에는 **없었다.** 그것이 야구 `pitcher_state` 가 0 이던 까닭이다."""
    from app.collect import mlb
    names = [s.name for s in mlb.sources_context("849825")]
    assert any("예고 선발" in n for n in names), names


#: 🔴 실측 응답의 **모양 그대로**(2026-10-04 · `gamePk=849825`). 통신하지 않는다.
PROBABLE_JSON = """
{"dates": [{"games": [{"gamePk": 849825, "teams": {
  "home": {"team": {"id": 158, "name": "Milwaukee Brewers"},
           "probablePitcher": {"id": 701656, "fullName": "Logan Henderson"}},
  "away": {"team": {"id": 135, "name": "San Diego Padres"},
           "probablePitcher": {"id": 650633, "fullName": "Michael King"}}}}]}]}
"""

#: 🔴 `people/{id}/stats` 의 모양 그대로(실측 2026-10-04).
STATS_JSON = """
{"stats": [{"splits": [{"player": {"id": 701656, "fullName": "Logan Henderson"},
  "stat": {"era": "2.47", "whip": "0.84", "inningsPitched": "98.1",
           "gamesPlayed": 18}}]}]}
"""


class _Resp:
    ok = True

    def __init__(self, url: str, text: str):
        self.url, self.text = url, text


def _probable_resp():
    return _Resp("https://statsapi.mlb.com/api/v1/schedule?gamePk=849825"
                 "&hydrate=probablePitcher,team", PROBABLE_JSON)


def test_M18_예고_선발_파서가_칸을_채운다():
    """🔴 `_dir_pitcher_state` 가 요구하는 칸을 **실제 사실에서** 확인한다.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **첫 판이 돌연변이를 통과시켰다**(2026-10-04)
    ══════════════════════════════════════════════════════════════════

    첫 판은 `inspect.getsource(parse_probable)` 에 `'"team"'` 이 **있나**만 봤다.
    🔴 그런데 그 함수에는 `tm.get(side).get("team")` 처럼 **다른 줄에도** 그 글자가
       있다 — 그래서 사실의 칸을 `"teamX"` 로 바꾼 돌연변이가 **초록이었다.**
    ⚠️ 문자열이 있나가 아니라 **사실에 그 칸이 있나**를 봐야 한다.
    """
    import inspect

    from app.cells import Question
    from app.collect import mlb
    src = inspect.getsource(classify._dir_pitcher_state)
    want = {k for k in ("era", "opponent_era", "team", "player")
            if f'"{k}"' in src or f"'{k}'" in src}
    assert {"era", "opponent_era", "team"} <= want, want
    q = Question("lineup", "MLB:Milwaukee Brewers:2026-10-04",
                 team="Milwaukee Brewers", league="MLB")
    facts = mlb.parse_probable(_probable_resp(), q)
    assert len(facts) == 2, facts
    for f in facts:
        for k in want:
            assert k in f.value, (
                f"🔴 예고 선발 사실에 `{k}` 칸이 없다 — `_dir_pitcher_state` 가 "
                f"그 칸을 본다: {sorted(f.value)}")
    got = {f.value["team"]: f.value["player"] for f in facts}
    assert got == {"Milwaukee Brewers": "Logan Henderson",
                   "San Diego Padres": "Michael King"}, got
    # 🔴 **상대 선발도** 같은 사실에 들어 있어야 한다(한쪽만 알면 방향을 못 낸다)
    assert all(f.value["opponent_player"] for f in facts), facts


def test_M18_방어율_파서가_이름과_방어율을_낸다():
    """🔴 이름 없는 성적은 쓸 데가 없다 — `_fill_starter_era` 가 이름으로 맞춘다."""
    from app.cells import Question
    from app.collect import mlb
    q = Question("lineup", "MLB:x:2026-10-04", team="x", league="MLB")
    got = mlb.parse_pitcher_stats(
        _Resp("https://statsapi.mlb.com/api/v1/people/701656/stats?stats=season"
              "&group=pitching", STATS_JSON), q)
    assert len(got) == 1, got
    assert got[0].value["player"] == "Logan Henderson"
    assert got[0].value["era"] == 2.47
    assert got[0].question_id.endswith(":starter_stats")




def test_M18_방어율을_따라간다():
    """🔴 이름만으로는 변수가 안 된다 — §19-c 로 두 투수 성적을 따라가야 한다.

    ⚠️ 실측 2026-10-04: `probablePitcher` 칸은 `['fullName','id','link']` **셋뿐**
       이고 `hydrate=probablePitcher(stats(...))` 로도 성적이 **안 붙는다.**
    """
    from app.collect import mlb
    srcs = [s for s in mlb.sources_context("849825") if "예고 선발" in s.name]
    assert srcs
    s = srcs[0]
    assert callable(s.follow) and callable(s.parse_follow), s
    # 🔴 주소가 **투수 성적**을 가리키나
    assert "people/" in mlb.pitcher_stats_url(701656)
    assert "group=pitching" in mlb.pitcher_stats_url(701656)


# ⚠️ **걷은 시험** — §1 처분(2026-10-12 셋째)으로 그 입구가 바뀌었다
#    (`our_board(drafts=)` → `fav=/dog=` · `s7_judge.run(hypo)` → 격자).
#    걷은 시험: `test_M18_빈_응답에_사실을_지어내지_않는다`

def test_M18_막는_마켓은_v4가_이름_댄_것과_같다():
    """🔴🔴 v4 원문: *"야구는 pitcher_state 변수 없으면 **총점·핸디** 마켓 계산 금지"*.

    ⚠️ 돌연변이 *"`M18_MARKETS` 에서 핸디를 뺀다"* 가 값 시험을 통과했다 —
       `_pick_one` 때문에 핸디에 등급이 서는 세트를 만들기 어려웠다.
    🔴 그래서 **선언을 원문과 대조한다.** v4 가 그 줄을 고치면 여기가 따라간다.
    """
    row = _m18_row()
    want = {m for word, m in WORD_TO_MARKET.items() if word in row}
    assert want, f"🔴 M18 줄에서 마켓 이름을 못 읽었다: {row}"
    assert set(survive.M18_MARKETS) == want, (
        f"🔴 v4 는 {sorted(want)} 를 막으라고 적었는데 코드는 "
        f"{sorted(survive.M18_MARKETS)} 를 막는다 — 원문: {row.strip()}")


def test_M18_야구에만_걸린다는_것도_원문에서_온다():
    """🔴 v4 가 *"**야구는**"* 이라고 적었다 — 넓히면 축구가 벙어리가 된다."""
    row = _m18_row()
    assert "야구" in row, row
    assert tuple(survive.M18_SPORTS) == ("baseball",), survive.M18_SPORTS


def test_M18_승무패를_막지_않는다():
    """🔴 v4 가 이름 댄 것은 총점·핸디뿐이다 — 승패는 선발을 몰라도 적는다.

    ⚠️ 값으로 못 본다(위 주석) — **선언으로** 본다.
    """
    for mt in ("home", "draw", "away", "home_dc", "away_dc", "btts"):
        assert mt not in survive.M18_MARKETS, mt


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **가드를 직접 친다** — 등급을 **실제로 거두나** (2026-10-04)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ `survive.run` 을 통과시켜서는 이것을 못 본다. 실측 2026-10-04:
#
#    · 야구는 **총점 마켓이 아예 안 만들어진다** — §6-c-3 *"총점 기준선을 못
#      구했다 → 총점 마켓을 이름으로 적지 않는다"*(카드가 그렇게 적었다).
#    · 핸디는 만들어지지만 §6 `_pick_one`·§7 R6 가 **먼저** 등급을 거둬서
#      `verdict` 가 이미 `none` 이다(핸디 0.9 짜리도 `none` 이었다).
#
#  🔴 그래서 돌연변이 *"등급을 안 거둔다(`for m in []`)"* 가 값 시험을 통과했다 —
#     거둘 등급이 애초에 없었기 때문이다. **가드를 직접 쳐야** 물린다.


def _result_with(market_type: str, verdict: str = "small",
                 survival: float = 0.9):
    """🔴 등급이 **선** 마켓 하나짜리 `Result`. ⚠️ 통신·엔진을 안 지난다."""
    from app.types import MarketSurvival
    res = survive.Result()
    ms = MarketSurvival(market_type=market_type, team=None, line=None,
                        alive_scenarios=["A"], dead_scenarios=["B"],
                        survival=survival, verdict=verdict)
    res.markets.append(ms)
    res.rows.append({"name": market_type, "market": ms,
                     "survival": survival, "verdict": verdict})
    return res


@pytest.mark.parametrize("market_type", ["total", "handicap"])
def test_M18_가드가_등급을_실제로_거둔다(market_type):
    """🔴 `for m in hit: m.verdict = "none"` 을 지우면 **빨개진다**."""
    res = _result_with(market_type)
    assert res.markets[0].verdict == "small", "대역이 등급을 못 세웠다"
    survive._m18_guard(res, _game("baseball"),
                       variables=[_var("recent_pattern")])
    assert res.markets[0].verdict == "none", (
        f"🔴 `{market_type}` 등급을 안 거뒀다 — M18 이 뜻을 잃는다")
    assert res.rows[0]["verdict"] == "none", res.rows
    assert any("M18" in n for n in res.notes), res.notes
    # 🔴 생존 수는 **그대로**다(#3 — 사람이 왜 막혔는지 봐야 한다)
    assert res.markets[0].survival == 0.9


@pytest.mark.parametrize("market_type", ["home", "away", "draw", "btts"])
def test_M18_가드가_다른_마켓은_안_건드린다(market_type):
    """🔴 v4 가 이름 댄 것은 총점·핸디뿐이다."""
    res = _result_with(market_type)
    survive._m18_guard(res, _game("baseball"),
                       variables=[_var("recent_pattern")])
    assert res.markets[0].verdict == "small", market_type
    assert res.rows[0]["verdict"] == "small", res.rows


def test_M18_가드가_선발을_알면_등급을_남긴다():
    res = _result_with("total")
    survive._m18_guard(res, _game("baseball"),
                       variables=[_var("pitcher_state")])
    assert res.markets[0].verdict == "small"
    assert not any("M18" in n for n in res.notes), res.notes


def test_M18_가드가_축구에는_안_걸린다():
    res = _result_with("total")
    survive._m18_guard(res, _game("soccer"),
                       variables=[_var("recent_pattern")])
    assert res.markets[0].verdict == "small"


# ⚠️ **되살린 도움 함수** — 걷은 시험 블록에 묶여 함께 사라졌다(§1 정리)
def _m18_row() -> str:
    """🔴 v4 §15 의 **M18 줄 원문**. 없으면 터진다 — 조용히 넘기지 않는다."""
    for line in V4.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("| M18 "):
            return line
    raise AssertionError("🔴 v4 에 M18 줄이 없다 — 계약이 기댈 원본이 사라졌다")
