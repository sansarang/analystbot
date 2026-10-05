"""§5 계약 — **시나리오 A~E 생성** (사용자 출력 블록 6).

⚠️ §9 는 단계 4 게이트(29%) 전에 단계 5·6 코드를 쓰지 말라고 한다. 사용자 지시가
   v4 보다 위다(*"게이트 판정은 나중에 다시 하기로 하고"*).
🔴 계약을 `tests/stage5` 나 `tests/stage6` 에 두면 **서명 없이 수집되지 않는다** —
   돌아가지 않는 계약은 없는 계약이므로 여기 둔다.
   → `docs/fable/questions/2026-10-02_stage5_partial.md`

## 🔴 잠그는 것

| 무엇 | 왜 |
|---|---|
| §7 R5 부족이면 **시나리오를 만들지 않는다** | R5 계약 원문이 그렇다 |
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


def _run(sport="soccer", board=None):
    facts, st = _collect()
    items = classify.classify_facts(facts, _game(sport))
    return scenarios.generate(items, _game(sport), standings=st, board=board)


# ══════════════════════════════════════════════════════════════════
# §5-a 기본 생성
# ══════════════════════════════════════════════════════════════════


def test_방향_묶음에서_A_B_C_가_나온다():
    """🔴 §5-a — strength 는 **그 묶음의 weight 합**이다(§5-d)."""
    facts, st = _collect()
    items = classify.classify_facts(facts, _game())
    got = scenarios.generate(items, _game(), standings=st)
    assert not got.insufficient, got.notes
    by = {d.id: d for d in got.drafts}
    assert {"A", "B", "C"} <= set(by), sorted(by)
    groups: dict[str, float] = {}
    for c in items:
        if c.is_variable:
            groups[c.direction] = groups.get(c.direction, 0.0) + c.weight
    assert by["A"].strength == round(groups["home"], 3)
    assert by["B"].strength == round(groups["away"], 3)


def test_축구는_무승부_묶음이_비어도_생성한다():
    """🔴 §5-a — *"무승부는 항상 살아 있는 결과"* · floor 는 yaml 이 정한다."""
    got = _run()
    c = next(d for d in got.drafts if d.id == "C")
    floor = float((rules._load(rules.SCENARIO_RULES)["base"])["soccer_draw_floor"])
    assert c.strength == floor, (c.strength, floor)
    assert c.template_id == "soccer_lock"


def test_스코어를_코드에_박지_않는다():
    """★ 🔴 §5-b 표·§5-c 규칙이 **원본**이다. 코드에 박으면 표가 바뀔 때 갈린다.

    ⚠️ **D46** — 독스트링·주석을 뺀 코드만 본다.
    """
    code = strip_docs((ROOT / "app" / "scenarios.py").read_text(encoding="utf-8"))
    # 🔴 `"2-1"` 같은 스코어 리터럴이 코드에 있으면 실패
    lits = re.findall(r'"\d{1,2}-\d{1,2}"', code)
    assert lits == [], f"스코어를 코드에 박았다: {sorted(set(lits))}"
    # 🔴 쓰는 스코어가 전부 yaml 에서 온다
    got = _run()
    tpl_scores = {s for t in rules.templates().values()
                  for s in (t.get("scores") or [])}
    rule_scores = {s for r in rules.cross_rules() for s in (r.get("scores") or [])}
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **파생 스코어를 인정한다** — 결정 ① 이후(2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 글자가 여덟이 되자 §6-2 보강이 **실제로 자리를 얻었고**, 그 보강은
    #     스코어를 **계산한다**(뒤집기 `_mirror` · 실점 동반 `X-1`). 🔴 그래서
    #     `0-2`(= `2-0` 의 뒤집기)가 섰고 이 계약이 걸렸다.
    #  🔴 이 계약이 **진짜 막는 것**은 *"코드에 스코어 리터럴을 박는 것"* 이고
    #     그것은 위 `lits` 검사다. 계산으로 나온 것은 **박은 것이 아니다.**
    #  ⚠️ 그래도 아무 수나 허용하지 않는다 — 선언된 스코어에서 **선언된
    #     연산으로** 닿는 것만이다(그 연산도 `app` 의 함수를 쓴다 · 사본 금지).
    declared = tpl_scores | rule_scores
    from app import scenarios as _S
    ok_scores = set(declared)
    for _ in range(2):          # 🔴 파생의 파생까지 두 겹
        ok_scores |= set(_S._mirror(sorted(ok_scores)))
        ok_scores |= set(_S._conceding_scores(sorted(ok_scores)))
    for d in got.drafts:
        assert set(d.scores) <= ok_scores, (
            f"🔴 `{d.id}` 의 스코어 {d.scores} 가 **선언에서도 파생에서도** "
            f"안 나온다 — 지어낸 수다")


# ══════════════════════════════════════════════════════════════════
# §7 R5 — 부족이면 만들지 않는다
# ══════════════════════════════════════════════════════════════════


def test_자료_부족이면_시나리오를_만들지_않는다():
    """★ 🔴 §7 R5 계약 원문 — *"sufficiency insufficient 인데 scenarios 생성 시 실패."*

    ⚠️ 2026-10-02 에 손으로 돌려 보니 네이션스리그 두 경기가 여기서 멈췄다.
       멈추는 것이 맞는 답이다 — 내 판단은 그 자리에서 낙첨했다.
    """
    one = classify.Classified(
        text="홈 우위", source_url="https://x.test/t", hardness="soft",
        type="home_field", direction="home", why="§4 home_field")
    got = scenarios.generate([one], _game())
    assert got.insufficient and got.drafts == []
    assert any("R5" in n for n in got.notes), got.notes
    # 🔴 방향이 한쪽뿐이어도 부족이다
    two = classify.Classified(
        text="맞대결", source_url="https://x.test/h", hardness="hard",
        type="h2h_pattern", direction="home", why="§4 h2h_pattern")
    got2 = scenarios.generate([one, two, two], _game())
    assert got2.insufficient, got2.notes


def test_템플릿이_없는_종목은_격자에서_뽑고_격자도_없으면_멈춘다():
    """★ 🔴 §5-b 에 **축구·야구만** 있다. 하키·농구·배구는 없다.

    ⚠️ 전 판은 거기서 **멈췄다** — 스코어를 손으로 적으면 지어내는 것이기 때문이다.
       그 판단은 맞았고, **격자가 생기면서 답이 달라졌다**(사용자 지시 2026-10-02):
       그 경기의 포아송 분포에서 **가장 그럴듯한 스코어**를 뽑으면 적을 것이 없다.
    🔴 개수도 고르지 않는다 — v4 §5-b 축구 템플릿의 개수를 **세어** 쓴다.
    🔴 **격자가 없으면 여전히 멈춘다** — 뽑을 분포가 없다.
    """
    for sport in ("hockey", "basketball", "volleyball"):
        got = _run(sport=sport)
        # 🔴 격자가 있으면 **파생으로 선다**
        assert not got.insufficient, (sport, got.notes)
        assert any("격자에서 뽑는다" in n for n in got.notes), got.notes
        derived = [d for d in got.drafts if d.template_id.startswith("derived:")]
        assert derived, [d.template_id for d in got.drafts]
        n = rules.derived_shape()["direction"]
        for d in derived:
            if not d.template_id.startswith("derived:open"):
                assert len(d.scores) == n, (d.template_id, d.scores)
    # 🔴 격자가 없으면 멈춘다 — 그때는 지어내지 않는다
    facts, _ = _collect()
    items = classify.classify_facts(facts, _game("hockey"))
    bare = scenarios.generate(items, _game("hockey"), standings={})
    assert bare.insufficient
    assert any("격자도 못 만들었다" in n for n in bare.notes), bare.notes
    # 🔴 야구는 템플릿이 있다 — 파생으로 가지 않는다
    assert not any("격자에서 뽑는다" in n for n in _run(sport="baseball").notes)


# ══════════════════════════════════════════════════════════════════
# §5-c 교차 규칙 — 🔴 발동하지 않은 것도 남는다
# ══════════════════════════════════════════════════════════════════


def test_교차_규칙_여섯이_전부_사유를_남긴다():
    """★ 🔴 09-28~29 실패가 전부 *"규칙이 있었는데 안 돌았다"* 였다.

    안 돈 것이 보이지 않으면 또 그렇게 된다. 여섯 규칙이 **발동하든 안 하든**
    이름이 기록에 나와야 한다.
    """
    got = _run()
    blob = " ".join(got.notes) + " ".join(d.why for d in got.drafts)
    for rid in (r["id"] for r in rules.cross_rules()):
        short = str(rid).replace("5c-", "")
        assert f"5c-{short}" in blob or f"§5-c-{short}" in blob, (
            f"{rid} 가 기록에 없다 — 발동했는지 안 했는지 알 수 없다")


def test_난타전_대타_문턱이_리그_평균에서_온다():
    """🔴 §5-c-1 ③(대타) — 절대 숫자가 아니라 **리그 평균 + 여유**다.

    ⚠️ ③ 은 ② (포아송)가 못 설 때만 본다. 1차 판에서 이것이 **유일한** 조건이었고
       정답지 경기(3-2·5골)를 놓쳤다 — 맞대결 2.5 · 최근 2.2 vs 문턱 3.732.
    🔴 리그 평균을 못 구하면 ③ 도 **발동하지 않는다**(친선·A매치). 절대 숫자로
       때우지 않는다.
    """
    facts, _ = _collect()
    items = classify.classify_facts(facts, _game())
    bare = scenarios.generate(items, _game(), standings={})
    assert any("5c-1 ③" in n and "리그 평균을 못 구했다" in n
               for n in bare.notes), bare.notes
    # 🔴 문턱이 **평균 + 여유**인지 — 값을 여기 적지 않고 yaml 에서 읽어 센다
    cfg = rules.cross_rule("5c-1")
    rows = [{"team": "a", "played": 10, "goals_for": 15, "goals_against": 15},
            {"team": "b", "played": 10, "goals_for": 15, "goals_against": 15}]
    assert league.open_game_threshold(rows) == round(
        league.avg_goals(rows) + float(cfg["league_avg_margin"]), 3)


def test_핸디_1_5_후보면_2골차_시나리오를_만든다():
    """🔴 §5-c-5 — 돗토리·후쿠시마가 이 시나리오를 빠뜨려 1.0 → 0.85 로 내려갔다.

    보드가 없으면 §6-c-3 대로 ±0.5/±1.5 만 후보이므로 **항상** 발동한다.
    """
    got = _run(board=None)
    two = [d for d in got.drafts
           if any(abs(int(s.split("-")[0]) - int(s.split("-")[1])) >= 2
                  for s in d.scores)]
    assert two, "2골 차 시나리오가 없다"
    # 🔴 보드에 ±1.5 가 없으면 발동하지 않는다(§6-c-1)
    off = _run(board=["총점 2.5", "홈 -0.5"])
    assert any("보드에 ±1.5 줄이 없다" in n for n in off.notes), off.notes


# ══════════════════════════════════════════════════════════════════
# §3 스키마 · §5-e
# ══════════════════════════════════════════════════════════════════


def test_3_스키마로_들어간다():
    """🔴 §3 STEP 5 — 2개 이상 · id 겹침 없음 · 단일 방향 금지."""
    got = _run()
    obj = Scenarios(game_id=1, scenarios=[d.to_scenario() for d in got.drafts])
    assert len(obj.scenarios) >= 2
    assert len({s.id for s in obj.scenarios}) == len(obj.scenarios)
    for s in obj.scenarios:
        assert s.scores and s.strength >= 0 and s.template_id


def test_narrative_를_지어내지_않는다():
    """🔴 §5-e — 문장은 LLM **L6** 이다. 미배선이므로 빈칸이다."""
    for d in _run().drafts:
        assert d.to_scenario().narrative == "", d.id


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


def test_난타전이_포아송으로_선다():
    """🔴 §5-c-1 ② — 평균이 아니라 **기대 득점의 확률**로 묻는다.

    ⚠️ 1차 판은 맞대결 2.5 · 최근 2.2 로 문턱 3.732 에 못 미쳐 **미발동**이었다.
       같은 경기의 홈/원정 쪼갠 표로 계산하면 기대 총득점이 리그 평균을 넘는다.
    """
    got = _run()
    d = next((x for x in got.drafts if x.template_id == "soccer_open"), None)
    assert d is not None, f"난타전이 또 안 섰다 — {got.notes}"
    assert "포아송" in d.why, d.why
    # 🔴 발동 근거를 **숫자로** 남겼나 — 안 남기면 왜 섰는지 못 따진다
    for bit in ("기대 총득점", "P(총 ≥"):
        assert bit in d.why, (bit, d.why)
    # 🔴 **비교 대상이 이미 둔 시나리오여야 한다**(3차 지시) — 리그 평균이 아니다.
    #    ⚠️ 격자가 없을 때만 리그 기준으로 내려간다.
    assert "이미 둔 시나리오" in d.why, d.why


def test_난타전_시나리오가_실제_결과를_덮는다():
    """🔴 **이 계약이 지시의 핵심이다.** 결과 3-2 가 시나리오 집합에 들어야 한다.

    ⚠️ 결과는 카세트의 `ongoing` 에서 읽는다 — 손으로 적으면 사본이 된다.
    """
    res = _result_from_cassette()
    if res is None:
        pytest.skip("카세트에 결과가 없다")
    got = _run()
    seen = {sc for d in got.drafts for sc in d.scores}
    assert f"{res[0]}-{res[1]}" in seen, \
        f"결과 {res[0]}-{res[1]} 가 시나리오 {sorted(seen)} 에 없다"


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


def test_포아송이_안_서면_사유가_남는다():
    """🔴 **조용히 빠지면 ③ 이 발동한 것으로 읽힌다.** 09-28~29 실패가 그 꼴이었다."""
    items = classify.classify_facts(_collect()[0], _game())
    got = scenarios.generate(items, _game(), standings={"league_avg_goals": 2.7})
    notes = [n for n in got.notes if n.startswith("5c-1 ②")]
    assert notes, got.notes
    assert "없다" in notes[0] or "못" in notes[0], notes


# ══════════════════════════════════════════════════════════════════
# 🔴 무게를 **확률**로 (사용자 지시 2026-10-02 3차)
# ══════════════════════════════════════════════════════════════════
#
# 지시: *"② D 의 strength 를 확률로 바꾸나 … 이것도 딥서치해서 바꿔라"*
#
# 🔴 딥서치의 답: 근거 개수는 확률이 아니다(적정 채점 규칙). **D 만 바꾸면 더 나쁘다** —
#    생존이 Σ(사는 무게)÷Σ(전체)인데 분자·분모에 확률과 개수가 섞이면 뜻이 없다.


def test_모든_시나리오가_확률을_갖는다():
    """🔴 **섞지 않는다** — 하나만 확률이면 생존 비가 뜻을 잃는다."""
    got = _run()
    miss = [d.id for d in got.drafts if d.probability is None]
    assert not miss, f"확률이 없는 시나리오 {miss}"
    assert got.total_probability and 0 < got.total_probability < 1.0
    # 🔴 §5-d 는 **남는다** — 가설·방향이 그것을 쓴다(`keep_strength: true`)
    assert all(d.strength > 0 for d in got.drafts)
    assert rules.scenario_weight()["keep_strength"] is True


def test_두_셈의_순서가_다른_것을_드러낸다():
    """🔴 이것이 지시의 근거다 — 무승부가 **두 번째로 그럴듯한데** strength 로는 꼴찌급.

    실측 2026-10-02: 확률 순 A C D B E · strength 순 A B C D E.
    """
    got = _run()
    by_p = [d.id for d in sorted(got.drafts, key=lambda d: -(d.probability or 0))]
    by_s = [d.id for d in sorted(got.drafts, key=lambda d: -d.strength)]
    assert by_p != by_s, (by_p, by_s)
    # 🔴 무승부 C 의 확률이 strength 정규화보다 **크다** — 과소평가를 보인다
    c = next(d for d in got.drafts if d.template_id == "soccer_lock")
    assert c.probability > c.strength / got.total_strength, c


def test_덮이지_않은_확률을_낸다():
    """🔴🔴 **가장 큰 조용한 0** — 전 판은 덮은 67% 안에서만 정규화했다.

    실측: 덮이지 않은 확률이 0.3 을 넘고, 가장 큰 누락 하나가 D 전체에 가깝다.
    ⚠️ `3-1` 은 §5-b 에 **템플릿이 아예 없다** — 지어내지 않고 이름으로 남긴다.
    """
    got = _run()
    assert got.uncovered and got.uncovered > 0.1, got.uncovered
    assert got.uncovered_scores, "누락 스코어를 이름으로 안 남겼다"
    assert any("없는 결과" in n for n in got.notes), got.notes
    # 🔴 덮은 것 + 안 덮은 것 = **1** 이어야 한다 — 격자 밖 꼬리까지 세었나.
    #    ⚠️ 여유를 0.01 로 뒀더니 **꼬리를 빼는 돌연변이가 통과했다**(꼬리 0.0017).
    #       두 수가 4자리로 둥글려지니 오차는 1e-4 를 넘지 않는다 — 그만큼만 준다.
    assert abs((got.total_probability or 0) + got.uncovered - 1.0) < 5e-4, (
        got.total_probability, got.uncovered)
    # 🔴 선언이 yaml 에 있고 출처가 붙어 있나
    cfg = rules.scenario_weight()
    assert cfg["report_uncovered"] is True
    assert str(cfg.get("source", "")).startswith("http")


def test_격자가_없으면_확률이_빈다_그리고_사유가_남는다():
    """🔴 **조용히 빠지지 않는다** — 격자가 없으면 §6 이 `strength` 로 돈다는 사실이
    기록에 남아야 한다(`scenario_weight.fallback`)."""
    items = classify.classify_facts(_collect()[0], _game())
    got = scenarios.generate(items, _game(), standings={"league_avg_goals": 2.7})
    assert got.drafts
    assert all(d.probability is None for d in got.drafts)
    assert got.total_probability is None
    # 🔴 못 쟀으면 `uncovered` 도 **`None`** — 0 이면 "다 덮었다"는 거짓이다
    assert got.uncovered is None
    assert any("격자를 못 만들었다" in n for n in got.notes), got.notes


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


def test_무승부가_없는_리그에서는_C_를_만들지_않는다():
    """🔴🔴 **돌연변이가 통과해서 더한 계약이다.**

    라이브 실측 2026-10-02: 격자에서 하키 스코어를 뽑으니 무승부 `3-3`·`2-2` 가
    나왔다 — **NHL 은 슛아웃으로 반드시 승자를 가린다.** 그 시나리오를 내면 카드가
    **일어날 수 없는 결과**를 적고, 그 확률이 다른 마켓의 생존을 깎는다.
    🔴 규정은 `config/league_rules.yaml` 이 들고 있다(출처·확인 날짜 붙음).
    """
    facts, _ = _collect()
    hockey = classify.Game(home=SAC, away=LV, sport="hockey", league="NHL")
    items = classify.classify_facts(facts, hockey)
    st = _collect()[1]
    got = scenarios.generate(items, hockey, standings=st)
    assert rules.draw_possible("NHL")[0] is False
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **글자가 아니라 스코어를 본다**(수정 2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전 이 줄은 `d.id == "C"` 였다 — **글자 자리**를 봤다. 그래서 난타전이
    #     `D` 를 쓰는 동안 그 안의 **`2-2`** 를 **한 번도 못 봤다.**
    #  🔴 §6-2 가 글자 배정을 한 곳으로 모으자 난타전이 `C` 를 집었고 그 순간
    #     이 계약이 터졌다 — **결함은 처음부터 있었고 계약이 눈이 멀어 있었다.**
    #  🔴 그래서 **무승부 스코어 자체**를 본다. 글자는 상관없다.
    ties = [(d.id, sc) for d in got.drafts for sc in d.scores
            if len(sc.split("-")) == 2 and sc.split("-")[0] == sc.split("-")[1]]
    assert not ties, (
        f"🔴 무승부가 **없는** 리그에 무승부 스코어를 냈다: {ties} — 카드가 "
        f"**일어날 수 없는 결과**를 적고 그 확률이 다른 마켓의 생존을 깎는다")
    assert any("무승부가 없다" in n for n in got.notes), got.notes
    # 🔴 무승부가 **있는** 리그는 **막지 않는다**
    #    ⚠️ 그렇다고 C 가 늘 생기는 것은 아니다 — §5-a 의 하한은 **축구 전용**이라
    #       다른 종목은 draw 방향 변수가 있어야 C 가 선다. 두 사실을 섞지 않는다.
    can = classify.Game(home=SAC, away=LV, sport="hockey",
                        league="USL Championship")
    assert rules.draw_possible("USL Championship")[0] is True
    got2 = scenarios.generate(classify.classify_facts(facts, can), can,
                              standings=st)
    assert not [n for n in got2.notes
                if n.startswith("C:") and "만들지 않는다" in n], got2.notes
    # 🔴 축구라면 하한으로 선다(같은 리그·같은 사실)
    #    ⚠️ 글자가 아니라 **무승부 스코어가 있나**로 본다(위와 같은 까닭)
    got2b = _run()
    assert _draw_only(got2b.drafts), got2b.notes
    # 🔴🔴 **가드가 실제로 일하는 자리로 물린다.** 위 경기는 draw 방향 변수가 없어
    #    가드를 떼어내도 C 가 안 생긴다 — 그 돌연변이가 **통과했다.**
    #    draw 변수를 들고 무승부 없는 리그로 가는 것이 가드가 일하는 자리다.
    draw_item = classify.Classified(
        text="무승부 밀기", source_url="https://x/1", hardness="hard",
        type="match_type", direction="draw", why="시험",
        dateless_reason="시험 자료")
    for league_, want_c in (("NHL", False), ("USL Championship", True)):
        g2 = classify.Game(home=SAC, away=LV, sport="hockey", league=league_)
        res = scenarios.Result()
        scenarios._base(res, {"home": [], "away": [], "draw": [draw_item]}, g2,
                        scenarios._grid(res, g2, st))
        has_c = bool(_draw_only(res.drafts))
        assert has_c is want_c, (league_, has_c, res.notes)

    # 🔴 **모르는 리그는 만들지 않는다** — 있는 척하지 않는다
    unknown = classify.Game(home=SAC, away=LV, sport="hockey", league="없는리그")
    got3 = scenarios.generate(classify.classify_facts(facts, unknown), unknown,
                              standings=st)
    # ⚠️ 글자가 아니라 **무승부 전용 시나리오가 있나**로 본다(위와 같은 까닭)
    assert not _draw_only(got3.drafts), [d.id for d in got3.drafts]
    assert any("선언되지 않았다" in n for n in got3.notes), got3.notes
