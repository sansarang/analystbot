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


def test_M18_선발을_모르면_총점_핸디에_등급이_없다():
    """🔴 실측 카드가 낸 밀워키 -0.5 · 샌디에이고 +1.5 가 이 자리다."""
    res = survive.run(_drafts(), _game(),
                      variables=[_var("recent_pattern"),
                                 _var("travel_schedule"),
                                 _var("recent_pattern", "away")])
    assert not _graded(res), [
        (m.market_type, m.team, m.line, m.survival, m.verdict)
        for m in _graded(res)]
    assert any("M18" in n for n in res.notes), res.notes


def test_M18_생존_수는_그대로_보여_준다():
    """🔴 거두는 것은 **등급**이다 — 수를 지우면 왜 막혔는지 못 본다(#3)."""
    res = survive.run(_drafts(), _game(), variables=[_var("recent_pattern")])
    hands = [m for m in res.markets if str(m.market_type) == "handicap"]
    assert hands, "핸디 줄이 아예 없으면 이 계약은 아무것도 안 본다"
    assert any(float(m.survival or 0) > 0 for m in hands), [
        (m.team, m.line, m.survival) for m in hands]


def test_M18_선발을_알면_막지_않는다():
    """⚠️ 늘 거두면 야구가 벙어리가 된다."""
    res = survive.run(_drafts(), _game(),
                      variables=[_var("pitcher_state"),
                                 _var("recent_pattern"),
                                 _var("travel_schedule"),
                                 _var("recent_pattern", "away"),
                                 _var("individual", "away")])
    assert not any("M18" in n for n in res.notes), res.notes


def test_M18_축구에는_안_건다():
    """🔴 v4 가 *"야구는"* 이라고 적었다 — 축구에 선발 투수가 없다."""
    res = survive.run(_drafts(), _game("soccer"),
                      variables=[_var("recent_pattern")])
    assert not any("M18" in n for n in res.notes), res.notes


def test_M18_변수를_안_주면_막지_않는다():
    """🔴 **모르는 것과 0 은 다르다.**"""
    res = survive.run(_drafts(), _game())
    assert not any("M18" in n for n in res.notes), res.notes


def test_M18_배경으로_떨어진_pitcher_state는_없는_것으로_센다():
    """🔴🔴 v4 가 *"pitcher_state **변수**"* 라고 적었다 — 방향이 없으면 변수가 아니다.

    ⚠️ 실측 2026-10-04: 두 선발 ERA 2.47 vs 3.21 — 차이 **0.74** 가 문턱
       **0.75** 에 0.01 모자라 `비슷하다고 본다` 로 **배경**이 됐다.
    🔴 그것을 *"선발을 안다"* 로 세면 M18 이 뚫린다 — 가장 흔한 꼴이 그것이다.
    """
    bg = classify.Classified(
        text="x", source_url="https://statsapi.mlb.com/x", hardness="hard",
        type="pitcher_state", direction=None,          # 🔴 방향이 없다
        why="§4 pitcher_state — 차이 0.74 < 문턱 0.75 · 비슷하다고 본다")
    assert not bg.is_variable
    res = survive.run(_drafts(), _game(), variables=[bg, _var("recent_pattern")])
    assert not _graded(res), "🔴 배경을 변수로 세어 M18 이 뚫렸다"
    assert any("M18" in n for n in res.notes), res.notes


# ══════════════════════════════════════════════════════════════════
# 🔴 배선 — 예고 선발이 **실제로 사실이 되나**
# ══════════════════════════════════════════════════════════════════


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


@pytest.mark.parametrize("fn", ["parse_probable", "parse_pitcher_stats"])
def test_M18_빈_응답에_사실을_지어내지_않는다(fn):
    from app.collect import mlb
    from app.cells import Question

    class _Got:
        ok = True
        url = "https://statsapi.mlb.com/api/v1/schedule?gamePk=1&hydrate=probablePitcher"
        text = "{}"

    q = Question("lineup", "MLB:x:2026-10-04", team="x", league="MLB")
    assert getattr(mlb, fn)(_Got(), q) == []


def test_M18_가드가_run_안에서_불린다():
    """🔴 함수만 있고 안 부르면 없는 코드보다 나쁘다."""
    src = (ROOT / "app" / "survive.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    run = next(n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "run")
    called = {ast.unparse(n.func) for n in ast.walk(run)
              if isinstance(n, ast.Call)}
    assert "_m18_guard" in called


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **등급이 실제로 서는 세트**로 봐야 한다 (2026-10-04)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 위 `_drafts()` 는 실측 카드의 세트인데, 그 세트의 핸디 생존이 0.6667 로
#     `SMALL_AT`(0.8) **아래**라 등급이 애초에 `none` 이다. 🔴 그래서 M18 이
#     *"등급을 거뒀다"* 와 *"거둘 것이 없었다"* 가 구분되지 않았고, 돌연변이 둘이
#     그대로 통과했다:
#
#       C `M18_MARKETS` 에서 `handicap` 을 뺀다   → ⚠️ 초록
#       E 등급을 **안 거둔다**(사유만 적는다)      → ⚠️ 초록
#
#  🔴 그래서 **생존 1.0 이 나오는 세트**로 다시 짠다 — 그때 등급이 `name` 으로 서고,
#     M18 이 그것을 거두는지가 눈에 보인다.
#  ⚠️ 변수를 **다섯 개** 준다 — `_thin_set_guard`(변수 5개 미만 + 1.0 → 거둠)가
#     먼저 거두면 M18 이 한 일을 또 못 가린다.


def _one_sided():
    """🔴 양쪽 다 1골 차 — 핸디 ±1.5 와 토탈이 **전부 산다**(생존 1.0)."""
    return [Draft(id="A", scores=["1-0"], strength=2.0,
                  template_id="baseball_ace_low", why="테스트"),
            Draft(id="B", scores=["0-1"], strength=1.0,
                  template_id="mirror:baseball_ace_low", why="테스트")]


def _five_vars():
    """⚠️ `pitcher_state` 가 **없는** 변수 다섯(얇은 세트 가드를 비껴간다)."""
    return [_var("recent_pattern"), _var("travel_schedule"),
            _var("recent_pattern", "away"), _var("individual", "away"),
            _var("h2h_pattern", "away")]


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **선언을 v4 원문에서 자라게 한다** (2026-10-04)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 값으로 거는 시험이 **핸디에는 못 닿는다**: §6 `_pick_one` 이 결론 줄을
#     하나만 남기므로 등급이 서는 마켓은 실측에서 `total`·`btts` 뿐이었고,
#     핸디 0.9 짜리도 `verdict=none` 으로 내려간다(실측 2026-10-04).
#  🔴 그래서 돌연변이 *"`M18_MARKETS` 에서 핸디를 뺀다"* 가 값 시험으로는 안 잡힌다.
#     **선언을 v4 원문과 대조한다** — 그것이 이 저장소의 방식이다(사본 금지).

V4 = pathlib.Path(ROOT / "docs" / "fable" / "inbox" / "2026-09-29_v4.md")

#: 🔴 v4 가 이름 댄 마켓 → 우리 `market_type`. ⚠️ **번역표만** 여기 둔다 —
#   어느 마켓을 막나는 v4 원문이 정한다(아래가 그 줄을 읽는다).
WORD_TO_MARKET = {"총점": "total", "핸디": "handicap"}


def _m18_row() -> str:
    """🔴 v4 §15 의 **M18 줄 원문**. 없으면 터진다 — 조용히 넘기지 않는다."""
    for line in V4.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("| M18 "):
            return line
    raise AssertionError("🔴 v4 에 M18 줄이 없다 — 계약이 기댈 원본이 사라졌다")


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
