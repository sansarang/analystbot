"""§5 계약 — **시나리오 A~E 생성** (사용자 출력 블록 6).

⚠️ §9 는 단계 4 게이트(29%) 전에 단계 5·6 코드를 쓰지 말라고 한다. 사용자 지시가
   v4 보다 위다(*"게이트 판정은 나중에 다시 하기로 하고"*).
🔴 계약을 `tests/stage5` 나 `tests/stage6` 에 두면 **서명 없이 수집되지 않는다** —
   돌아가지 않는 계약은 없는 계약이므로 여기 둔다.
   → `docs/fable/questions/2026-10-02_stage5_partial.md`

## 🔴 잠그는 것

| 무엇 | 왜 |
|---|---|
| §7 R5 가 얇으면 **등급만 없다**(시나리오는 낸다) | 🔴 사용자 규칙 2026-10-06 — 종전 *"만들지 않는다"* 는 걷혔다 |
| 스코어는 **yaml 이 원본** | 코드에 박으면 §5-b 표가 바뀔 때 갈린다 |
| 발동하지 않은 교차 규칙도 **사유를 남긴다** | 09-28~29 실패가 전부 *"있었는데 안 돌았다"* 였다 |
| 템플릿 없는 종목은 **멈춘다** | 하키·농구·배구는 §5-b 에 없다 — 지어내지 않는다 |
| §5-c-6 단일 방향 금지 | 한 방향뿐이면 예측불허가 아니다 |
"""
from __future__ import annotations

import glob
import json
import re
from datetime import timedelta, timezone
from pathlib import Path

import pytest

from app import classify, league, rules, scenarios
from app.cells import Q_LINEUP, Question
from app.collect import fotmob
from app.net import Fetched
from app.types import Scenarios
from tests._helpers import strip_docs

ROOT = Path(__file__).resolve().parents[2]
KST = timezone(timedelta(hours=9))
SAC, LV = "Sacramento Republic FC", "Las Vegas Lights FC"


def _game(sport="soccer") -> classify.Game:
    return classify.Game(home=SAC, away=LV, sport=sport,
                         league="USL Championship")


def _collect():
    facts, st = [], None
    for f in sorted(glob.glob(str(ROOT / "tests/fixtures/cassettes/*/*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        u = d.get("url") or ""
        if "matches/sacramento-republic-fc-vs-las-vegas" not in u \
                and not fotmob.is_table_page(u):
            continue
        got = Fetched(u, True, 200, d.get("text") or "")
        j = fotmob.payload(got.text)
        if j is None:
            continue
        when = fotmob.kickoff(j)
        for team in (SAC, LV):
            q = Question(Q_LINEUP, "x", team=team,
                         deadline=when.astimezone(KST) if when else None)
            new = (fotmob.parse_context(got, q) if fotmob.is_match_page(u)
                   else fotmob.parse_league_table(got, q))
            facts += new
            for fa in new:
                if fa.question_id.endswith(":standings"):
                    st = dict(fa.value)
                if fa.question_id.endswith(":h2h") and st is not None:
                    st["h2h_window_avg_goals"] = fa.value.get("window_avg_goals")
                    # 🔴 **표본 수도 싣는다** — 5c-1 ③ 이 8경기 미만을 버린다
                    st["h2h_window_games"] = fa.value.get("window_games")
                if fa.question_id.endswith(":form") and st is not None:
                    v = fa.value.get("recent_avg_goals")
                    if v is not None:
                        st["recent_avg_goals"] = max(
                            st.get("recent_avg_goals") or 0, v)
    return facts, st




# ══════════════════════════════════════════════════════════════════
# §5-a 기본 생성
# ══════════════════════════════════════════════════════════════════








# ══════════════════════════════════════════════════════════════════
# §7 R5 — 얇으면 **등급만** 없다(사용자 규칙 2026-10-06)
# ══════════════════════════════════════════════════════════════════


def test_자료가_얇으면_등급만_없다_시나리오는_낸다():
    """🔴🔴 **§7 R5 는 "등급 금지"다** — 사용자 규칙 2026-10-06.

    > §7 R5 자료 부족은 **"등급 금지"로만** 작동한다. 시나리오·대입·방향
    > 판정은 **항상** 낸다. DeepSeek 시나리오가 있으면 버리지 않는다.
    > 카드에 *"자료 얇음 — 등급 없음(사유)"* 만 표시.
    > (자료가 얇아도 자료 부족으로 넘기지 말고 분석한다.)

    ══════════════════════════════════════════════════════════════════
    ⚠️ 종전 계약은 *"멈추는 것이 맞는 답"* 이라고 적혀 있었다 — 걷혔다
    ══════════════════════════════════════════════════════════════════

    🔴 실측 2026-10-06(북아일랜드–조지아): DeepSeek 가 **시나리오 6개**를
       냈는데 `generate` 가 R5 에서 **즉시 돌아가** 카드가 *"시나리오를 만들지
       않는다"* 만 적고 그 여섯을 통째로 버렸다.
    """
    one = classify.Classified(
        text="홈 우위", source_url="https://x.test/t", hardness="soft",
        type="home_field", direction="home", why="§4 home_field")
    got = scenarios.generate([one], _game())
    # 🔴 ① 플래그는 선다 — 그 뜻은 **등급 금지**다
    assert got.insufficient, got.notes
    # 🔴 ② 그런데 **멈추지 않는다** — 시나리오가 나와야 한다
    assert got.drafts, (
        "🔴 얇다고 시나리오를 안 만들었다 — 사용자 규칙 2026-10-06 위반"
        f" · 사유 {got.notes}")
    # 🔴 ③ **왜 얇은지**를 한 줄로 들고 있다(카드가 그것을 적는다 · #3)
    assert got.thin_why and "최소" in got.thin_why, got.thin_why
    assert any("등급 없음" in n for n in got.notes), got.notes
    # 🔴 ④ 방향이 한쪽뿐이어도 같다 — 등급만 없다
    two = classify.Classified(
        text="맞대결", source_url="https://x.test/h", hardness="hard",
        type="h2h_pattern", direction="home", why="§4 h2h_pattern")
    got2 = scenarios.generate([one, two, two], _game())
    assert got2.insufficient and got2.drafts, got2.notes


def test_얇으면_생존이_등급을_거둔다():
    """🔴 대입은 **보이고** `verdict` 만 `none` 이다 — §6-7 거짓 1.0 을 그것으로 막는다.

    ⚠️ 이 반대 증거가 없으면 위 계약이 *"얇아도 등급을 낸다"* 를 허락한다.
    """
    from app import survive
    one = classify.Classified(
        text="홈 우위", source_url="https://x.test/t", hardness="soft",
        type="home_field", direction="home", why="§4 home_field")
    sc = scenarios.generate([one], _game())
    assert sc.insufficient and sc.drafts
    # 🔴 얇음을 **안 넘기면** 등급이 선다(그래야 아래 비교가 뜻을 갖는다)
    graded = survive.run(sc.drafts, _game(), board=None)
    # 🔴 얇음을 넘기면 그 등급이 **전부 사라진다**
    thin = survive.run(sc.drafts, _game(), board=None,
                       thin_why="변수 1개(최소 3)")
    named = [r for r in graded.rows if r.get("verdict") in ("name", "small", "low")]
    assert named, f"전제가 깨졌다 — 등급이 애초에 0줄이다: {graded.rows[:2]}"
    left = [r for r in thin.rows if r.get("verdict") in ("name", "small", "low")]
    assert not left, f"🔴 얇은데 등급이 남았다: {left[:2]}"
    # 🔴 **대입 줄 자체는 남아 있다**(거두는 것은 등급뿐이다)
    assert len(thin.rows) == len(graded.rows), (len(thin.rows), len(graded.rows))
    assert any("자료 얇음" in str(n) for n in thin.notes), thin.notes




# ══════════════════════════════════════════════════════════════════
# §5-c 교차 규칙 — 🔴 발동하지 않은 것도 남는다
# ══════════════════════════════════════════════════════════════════








# ══════════════════════════════════════════════════════════════════
# §3 스키마 · §5-e
# ══════════════════════════════════════════════════════════════════






def test_단일_방향이면_되돌린다():
    """🔴 §5-c-6 · §3 STEP 5 — 한 방향뿐이면 예측불허가 아니다.

    ⚠️ `types.Scenarios` 도 같은 것을 막는다(두 겹). 여기서 **먼저** 잡아 사유를
       남긴다 — 스키마 예외만 터지면 왜인지 안 보인다.
    """
    import inspect
    src = strip_docs(inspect.getsource(scenarios._single_direction_guard))
    assert "all_one_direction" in src
    assert "insufficient" in src


# ══════════════════════════════════════════════════════════════════
# 🔴 §5-c-1 ② — **포아송 난타전** (사용자 지시 2026-10-02 2차)
# ══════════════════════════════════════════════════════════════════
#
# 지시: *"난타전(5c-1)이 안 섰고 심층서치 찾아서 해결해라"*
#
# 🔴 정답지 경기는 **3-2(5골)** 였고 1차 판(맞대결·최근 평균)은 미발동했다.
#    딥서치가 그 두 신호를 가장 약한 예측자로 지목했고, 표준 모형(포아송 공격비·
#    수비비, 홈/원정 쪼갠 표)으로 바꾸니 발동했다.


def _result_from_cassette() -> tuple[int, int] | None:
    """🔴 **결과를 손으로 적지 않는다** — 순위표의 `ongoing` 이 들고 있다."""
    for f in sorted(glob.glob(str(ROOT / "tests/fixtures/cassettes/*/*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        if not fotmob.is_table_page(d.get("url") or ""):
            continue
        j = fotmob.payload(d.get("text") or "")
        for tb in fotmob._tables(j or {}):
            for r in (tb.get("table") or {}).get("all") or []:
                og = r.get("ongoing") or {}
                if SAC in str(og.get("hTeam") or "") \
                        and LV in str(og.get("aTeam") or ""):
                    if og.get("hScore") is None:
                        continue
                    return int(og["hScore"]), int(og["aScore"])
    return None






def test_포아송은_장소를_섞지_않는다():
    """🔴 딥서치가 못 박은 조건 — *"same venue context"*.

    홈 줄과 원정 줄을 **바꿔 넣으면 답이 달라야** 한다. 같으면 장소를 안 쓰는 것이다.
    """
    avgs = {"home": 1.526, "away": 1.206}
    h = {"team": "H", "played": 12, "goals_for": 20, "goals_against": 9}
    a = {"team": "A", "played": 12, "goals_for": 18, "goals_against": 21}
    one = league.expected_goals(h, a, avgs)
    two = league.expected_goals(a, h, avgs)
    assert one and two and one["total"] != two["total"], (one, two)
    # 🔴 장소 평균을 못 구하면 모형을 **돌리지 않는다**
    assert league.expected_goals(h, a, None) is None
    assert league.venue_averages([], []) is None


def test_문턱은_리그_기준_확률_대비_비율이다():
    """🔴 **절대 확률을 쓰지 않는다** — 리그 기준이 리그마다 다르다.

    같은 두 팀이라도 리그 평균이 낮으면 같은 기대값이 **더 높은 비율**이 된다.
    """
    h = {"team": "H", "played": 12, "goals_for": 20, "goals_against": 9}
    a = {"team": "A", "played": 12, "goals_for": 18, "goals_against": 21}
    low = league.open_game_ratio(h, a, {"home": 1.3, "away": 1.0})
    high = league.open_game_ratio(h, a, {"home": 1.8, "away": 1.5})
    assert low and high
    assert low["league_p"] < high["league_p"], (low, high)
    # 🔴 `open_goals`·`prob_ratio` 는 yaml 이 원본이다
    model = (rules.cross_rule("5c-1") or {}).get("model") or {}
    assert model.get("open_goals") and model.get("prob_ratio") is not None
    assert str(model.get("source", "")).startswith("http"), "출처가 없다"
    assert low["goals"] == int(model["open_goals"])


def test_포아송_확률이_포아송_분포다():
    """🔴 식이 맞나 — 손으로 셀 수 있는 값으로 물린다.

    λ=1 이면 P(≥1) = 1 − e⁻¹ = 0.6321.
    """
    import math
    assert league.total_at_least(1.0, 1) == round(1 - math.exp(-1), 4)
    # 🔴 P(총 ≥ 0) 은 **1.0** 이다 — 0 이 아니다(한 번 거꾸로 적었다)
    assert league.total_at_least(1.0, 0) == 1.0
    # 🔴 못 구하면 `None` — 0 으로 때우지 않는다
    assert league.total_at_least(None, 4) is None
    # 🔴 n 이 커지면 확률은 단조 감소한다
    seq = [league.total_at_least(2.8, n) for n in range(1, 7)]
    assert seq == sorted(seq, reverse=True), seq


def test_맞대결_표본이_모자라면_버린다():
    """🔴 딥서치: 맞대결 평균은 **8경기 미만이면 쓰지 말라** — 한 경기가 왜곡한다.

    ⚠️ 실측 정답지의 맞대결에 5-0 이 끼어 있다. 그 한 경기가 평균을 끌어올린다.
    """
    cfg = rules.cross_rule("5c-1")
    need = cfg.get("h2h_min_games")
    assert need and int(need) >= 8, f"표본 문턱이 {need} 다"
    res = scenarios.Result()
    got = scenarios._open_signals(
        {"h2h_window_avg_goals": 9.9, "h2h_window_games": int(need) - 1}, cfg, res)
    assert dict(got)["맞대결 창"] is None, got
    assert any("표본" in n for n in res.notes), res.notes
    # 🔴 표본이 차면 **쓴다**
    ok = scenarios._open_signals(
        {"h2h_window_avg_goals": 9.9, "h2h_window_games": int(need)}, cfg, None)
    assert dict(ok)["맞대결 창"] == 9.9




# ══════════════════════════════════════════════════════════════════
# 🔴 무게를 **확률**로 (사용자 지시 2026-10-02 3차)
# ══════════════════════════════════════════════════════════════════
#
# 지시: *"② D 의 strength 를 확률로 바꾸나 … 이것도 딥서치해서 바꿔라"*
#
# 🔴 딥서치의 답: 근거 개수는 확률이 아니다(적정 채점 규칙). **D 만 바꾸면 더 나쁘다** —
#    생존이 Σ(사는 무게)÷Σ(전체)인데 분자·분모에 확률과 개수가 섞이면 뜻이 없다.










def test_확률_격자가_1_로_모인다():
    """🔴 격자가 확률 분포인가 — 합 + 꼬리 = 1."""
    g = league.score_probabilities(1.911, 0.933)
    assert g
    assert abs(sum(g["scores"].values()) + g["tail"] - 1.0) < 1e-6
    # 🔴 격자에 없는 스코어는 **0 이 아니라 `None`** 이다(조용한 0 금지)
    assert league.scores_mass(g, ["99-0"]) is None
    assert league.scores_mass(None, ["1-0"]) is None
    assert league.score_probabilities(None, 1.0) is None


def _draw_only(drafts) -> list:
    """🔴 **무승부 시나리오** = 스코어가 **전부** 무승부인 시나리오.

    ⚠️ 종전 계약은 이것을 `d.id == "C"` 로 봤다 — **글자 자리**다. 그래서
       난타전(`['3-1', '2-2', '3-2']`)이 `D` 를 쓰는 동안 그 안의 `2-2` 를
       **한 번도 못 봤다**(§6-2 가 글자 배정을 모으자 그 결함이 드러났다).
    🔴 섞인 스코어 안의 무승부는 `drop_impossible_draws` 가 따로 걷는다.
    """
    def tie(sc: str) -> bool:
        parts = str(sc).split("-")
        return len(parts) == 2 and parts[0] == parts[1]
    return [d for d in drafts if d.scores and all(tie(x) for x in d.scores)]


