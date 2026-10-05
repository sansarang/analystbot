"""단계 4 계약 — **규칙이 요구하는 숫자를 자료에서 계산한다.**

사용자 지시 2026-10-02 로 규칙 네 개가 바뀌었고(`questions/2026-10-02_rule_defects.md`),
그 규칙들이 코드에 없던 숫자를 요구했다:

| 규칙 | 숫자 | 어디서 |
|---|---|---|
| §5-c-1 난타전 | 리그 평균 총득점 + 여유 | `league.open_game_threshold` |
| §6-c-3 총점 기준선 | 리그 평균 → 가장 가까운 `X.5` | `league.baseline_total` |
| §4 `home_field` | 홈/원정 쪼갠 승률·득점 차 | `league.home_advantage` |
| §4 `h2h_pattern` | 최근 N경기 창 + 표본별 weight | `league.h2h_window` · `h2h_weight` |

🔴 **문턱·창·가중치를 여기 적지 않는다** — `config/*.yaml` 이 원본이고 계약은 그것을
   읽어 **코드가 선언을 지키는지** 본다.
"""
from __future__ import annotations

import glob
import inspect
import json
from pathlib import Path

import pytest

from app import league, rules
from app.cells import Q_LINEUP, Question
from app.collect import fotmob
from app.net import Fetched
from tests._helpers import strip_docs

ROOT = Path(__file__).resolve().parents[2]


def _cassettes(pred):
    out = []
    for f in sorted(glob.glob(str(ROOT / "tests/fixtures/cassettes/*/*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        if pred(d.get("url") or "") and (d.get("text") or ""):
            out.append(d)
    return out


# ══════════════════════════════════════════════════════════════════
# 리그 평균 · 기준선 · 난타전 문턱
# ══════════════════════════════════════════════════════════════════


def test_리그_평균을_순위표에서_계산한다():
    """🔴 식: Σ 득점 ÷ (Σ 경기 ÷ 2). 한 경기가 두 팀에 세어진다.

    실측 2026-10-02: MLS 3.22 · USL 2.73 · UEFA NL C2 2.50.
    ⚠️ **리그가 0.7골 차로 갈린다** — 절대 숫자 문턱은 어느 리그에서든 틀린다.
    """
    pages = _cassettes(fotmob.is_table_page)
    if not pages:
        pytest.skip("리그 표 카세트가 없다")
    for d in pages:
        got = Fetched(d["url"], True, 200, d["text"])
        facts = fotmob.parse_league_table(
            got, Question(Q_LINEUP, "x", team="Sacramento Republic"))
        if not facts:
            continue
        v = facts[0].value
        assert v["league_avg_goals"] and 1.5 < v["league_avg_goals"] < 6.0, v
        # 🔴 **대회 전체로 셌나** — 표가 여럿이면 다 합해야 한다
        assert v["league_tables"] >= 1
        return
    pytest.skip("우리 팀이 든 표를 못 찾았다")


def test_기준선이_X_5_이고_리그_평균에서_나온다():
    """★ 🔴 v4 §6-c-3 원문(*"시나리오 최대합 + 0.5"*)은 **순환**이었다.

    ⚠️ `X.5` 만 쓴다 — 정수 기준선은 밀어내기(push)가 생긴다.
    """
    cfg = rules.total_baseline_cfg()
    assert cfg.get("only_half_lines") is True
    # (평균, 기대 기준선) — 🔴 `3.00` 은 **동점**이다(2.5 ↔ 3.5 등거리).
    #    yaml 의 `tie_goes: 아래` 가 그것을 정한다 — 코드에 숨지 않는다.
    assert rules.total_baseline_cfg().get("tie_goes") == "아래"
    for avg, want in ((3.22, 3.5), (2.73, 2.5), (2.50, 2.5), (3.60, 3.5),
                      (4.10, 4.5),
                      # 🔴 **동점** — 평균이 정확히 X.00 이면 2.5↔3.5 등거리다.
                      #    `tie_goes: 아래` 가 낮은 줄을 고른다(언더가 더 어렵게).
                      (3.00, 2.5), (2.00, 1.5), (4.00, 3.5),
                      # 동점이 아닌 경계
                      (1.50, 1.5), (3.49, 3.5), (3.51, 3.5)):
        rows = [{"played": 2, "goals_for": avg}]      # Σ득점/(Σ경기/2) = avg
        got = league.baseline_total(rows)
        assert got == want, f"평균 {avg} → {got} (기대 {want})"
        assert (got * 2) % 2 == 1, f"{got} 가 X.5 가 아니다"


def test_난타전_문턱이_리그_평균_더하기_여유다():
    """🔴 절대 숫자를 쓰지 않는다(§5-c-1, 사용자 지시 2026-10-02)."""
    margin = float(rules.cross_rule("5c-1")["league_avg_margin"])
    rows = [{"played": 2, "goals_for": 3.0}]
    assert league.open_game_threshold(rows) == pytest.approx(3.0 + margin)


def test_리그_평균을_못_구하면_전부_None():
    """★ 🔴 **친선·A매치는 순위표가 없다.** 절대 숫자로 때우지 않는다 —
    그 OR 조건은 발동하지 않고, 총점 마켓은 이름을 적지 않는다.
    """
    for rows in ([], [{"played": None, "goals_for": None}],
                 [{"played": 1, "goals_for": None}]):
        assert league.avg_goals(rows) is None, rows
        assert league.baseline_total(rows) is None, rows
        assert league.open_game_threshold(rows) is None, rows


# ══════════════════════════════════════════════════════════════════
# 홈 우위 (§4 `home_field`)
# ══════════════════════════════════════════════════════════════════


def test_홈_우위를_쪼갠_표에서_잰다():
    """★ 실측 2026-10-02 — 홈 우위는 **크다.**

    ```
    MLS 홈 200경기  홈 승 45.0% vs 원정 28.2% → +16.8%p · 득점 +0.46골
    USL 홈 169경기                            → +18.3%p · +0.50골
    ```

    🔴 §5-a 는 home 방향 변수 묶음에서 시나리오 A 를 만든다 — 홈 변수가 없으면
       홈으로 기울 변수가 없는 경기에서 **A 가 아예 생성되지 않는다**(실제 45%).
    """
    pages = _cassettes(fotmob.is_table_page)
    if not pages:
        pytest.skip("리그 표 카세트가 없다")
    for d in pages:
        facts = fotmob.parse_league_table(
            Fetched(d["url"], True, 200, d["text"]),
            Question(Q_LINEUP, "x", team="Sacramento Republic"))
        if not facts:
            continue
        ha = facts[0].value["home_advantage"]
        assert ha and ha["home_games"] > 50, ha
        # 🔴 홈이 유리하다는 사실 자체가 측정으로 확인돼야 한다
        assert ha["win_pct_delta"] > 5.0, f"홈 우위가 {ha['win_pct_delta']}%p 뿐이다"
        assert ha["home_win_pct"] > ha["away_win_pct"]
        return
    pytest.skip("우리 팀이 든 표를 못 찾았다")


def test_쪼갠_표가_없으면_홈_우위를_만들지_않는다():
    """🔴 하키 `standings/now` 는 홈/원정을 안 준다. 있는 척하지 않는다."""
    assert league.home_advantage([], []) is None
    assert league.home_advantage([{"played": 0}], [{"played": 0}]) is None


# ══════════════════════════════════════════════════════════════════
# 맞대결 창·표본 weight (§4 `h2h_pattern`)
# ══════════════════════════════════════════════════════════════════


def test_표본이_작으면_weight_가_깎인다():
    """★ 🔴 실측 2026-10-02 가 이 규칙을 만들었다.

    ```
     3경기 창  시애틀 승 66.7% · KC 승 **0.0%** · 경기당 4.67골
    30경기 창            46.7% ·      36.7%   ·        2.73골
    ```

    3경기 창은 *"상대가 한 번도 못 이겼다"* 고 말한다 — 실제는 36.7% 다.
    ⚠️ 2026-10-01 에 그 함정으로 맞대결 3경기에 언더 0.9 를 걸고 낙첨했다.
    """
    cfg = rules.h2h_sample_cfg()
    assert league.h2h_weight(30) == float(cfg[">=10"])
    assert league.h2h_weight(10) == float(cfg[">=10"])
    assert league.h2h_weight(9) == float(cfg["5~9"])
    assert league.h2h_weight(5) == float(cfg["5~9"])
    assert league.h2h_weight(4) == float(cfg["<5"])
    assert league.h2h_weight(3) == float(cfg["<5"])
    # 🔴 작은 표본이 큰 표본보다 무거울 수 없다
    assert league.h2h_weight(3) < league.h2h_weight(10)


def test_맞대결_창이_실제로_잘린다():
    """★ 🔴 실측 2026-10-02 — **날짜 자리가 블록마다 다르다.**

    `teamForm` 은 `date.utcTime` 에 싣고 **`h2h` 는 `date` 가 `null` 이고
    `status.utcTime` 에 싣는다.** 한 자리만 보다가 맞대결 33경기 전부가
    "날짜 없음"이 되어 **창이 안 잘렸다.**
    """
    n = int(str(rules.h2h_sample_cfg()["window"]).split("경기")[0].split()[-1])
    seen_trim = False
    for d in _cassettes(fotmob.is_match_page):
        got = Fetched(d["url"], True, 200, d["text"])
        j = fotmob.payload(got.text)
        when = fotmob.kickoff(j) if j else None
        home = (fotmob._side(j, "homeTeam") or {}).get("name") if j else None
        if not (when and home):
            continue
        for f in fotmob.parse_context(got, Question(
                Q_LINEUP, "x", team=home,
                deadline=when.astimezone(fotmob.KST))):
            if not f.question_id.endswith(":h2h"):
                continue
            v = f.value
            assert v["count"] <= n, f"창이 {v['count']}경기다 (상한 {n})"
            assert v["count"] <= v["all_games"]
            assert v["sample_weight"] == league.h2h_weight(v["count"])
            if v["all_games"] > n:
                seen_trim = True
                assert v["count"] == n, "창보다 많은데 안 잘렸다"
    assert seen_trim, (
        f"{n}경기를 넘는 맞대결 카세트가 없어 **자르는 것을 확인하지 못했다** — "
        f"계약이 공허하다")


def test_창과_전체를_둘_다_남긴다():
    """🔴 §7 R7 — *"최근 폼은 최근 5경기+월간 **두 창**을 함께 본다."* 맞대결도 같다.

    ⚠️ 창만 남기면 "표본이 얼마나 있었나"를 되짚을 수 없다(조용한 0 금지).
    """
    for d in _cassettes(fotmob.is_match_page):
        got = Fetched(d["url"], True, 200, d["text"])
        j = fotmob.payload(got.text)
        when = fotmob.kickoff(j) if j else None
        home = (fotmob._side(j, "homeTeam") or {}).get("name") if j else None
        if not (when and home):
            continue
        for f in fotmob.parse_context(got, Question(
                Q_LINEUP, "x", team=home, deadline=when.astimezone(fotmob.KST))):
            if f.question_id.endswith(":h2h"):
                # 🔴 v5 §8-3 정본 — `matches`(창 안의 경기)·`count`·`all_games`.
                #    ⚠️ 종전 `window`·`window_games` 는 **fotmob 고유 칸**이었고
                #       §8-3 이 어댑터 안으로 되돌렸다(#6).
                for k in ("matches", "count", "all_games",
                          "sample_weight", "window_avg_goals"):
                    assert k in f.value, f"{k} 가 없다"
                # 🔴 §7 R7 *"두 창"* 은 그대로다 — 창과 전체가 **둘 다** 있다
                assert f.value["count"] == len(f.value["matches"])
                assert f.value["all_games"] >= f.value["count"]
                return
    pytest.skip("맞대결 카세트가 없다")


# ══════════════════════════════════════════════════════════════════
# 🔴 공통 꼴 — 종목마다 칸 이름이 갈리면 단계 5~7 이 분기를 쓴다
# ══════════════════════════════════════════════════════════════════


def test_세_종목_순위가_같은_칸_이름을_낸다():
    """★ 🔴 실측 2026-10-02: 같은 "순위" 질문인데 `fotmob` 은 `wins/draws/losses`,
    `mlb` 는 `w/d/l` 을 냈다. 그러면 단계 5~7 이 **종목별 분기**를 써야 하고,
    분기는 한 종목이 바뀔 때 다른 종목을 조용히 깨뜨린다.

    ⚠️ 없는 칸은 **`None`** 이다 — 하키엔 무승부가 없다. 0 으로 때우면
       "무승부가 0회"라는 거짓이 된다.
    """
    import inspect
    from app.collect import mlb, nhl
    need = {"team", "played", "wins", "losses", "draws"}
    for name, mod, fn in (("fotmob", fotmob, fotmob.parse_league_table),
                          ("mlb", mlb, mlb.parse_standings),
                          ("nhl", nhl, nhl.parse_standings)):
        src = inspect.getsource(fn)
        miss = [k for k in need if f'"{k}"' not in src]
        assert not miss, f"{name}: 공통 칸이 없다 {miss}"
    # 🔴 공통 꼴의 원본은 `league.TABLE_FIELDS` 다
    assert need <= set(league.TABLE_FIELDS)


# ══════════════════════════════════════════════════════════════════
# 🔴 §5-c-1 ② — **포아송 기대 득점** (사용자 지시 2026-10-02 2차)
# ══════════════════════════════════════════════════════════════════


def test_홈_원정_평균을_따로_센다():
    """🔴 딥서치 조건 — *"same venue context"*. 장소를 섞으면 안 된다.

    실측 2026-10-02(USL 325경기): 홈 **1.526** · 원정 **1.206** — 0.32골 차다.
    ⚠️ 1차 판의 난타전 조건은 이 차이를 무시했고, 그래서 정답지 경기를 놓쳤다.
    """
    pages = _cassettes(fotmob.is_table_page)
    if not pages:
        pytest.skip("리그 표 카세트가 없다")
    for d in pages:
        facts = fotmob.parse_league_table(
            Fetched(d["url"], True, 200, d["text"]),
            Question(Q_LINEUP, "x", team="Sacramento Republic"))
        if not facts:
            continue
        v = facts[0].value
        avgs = v["venue_averages"]
        assert avgs and avgs["home"] > avgs["away"], avgs
        # 🔴 합이 **리그 평균 총득점**과 맞아야 한다 — 두 셈이 서로를 검산한다
        assert abs((avgs["home"] + avgs["away"]) - v["league_avg_goals"]) < 0.05
        # 🔴 두 팀의 줄을 고르려면 표가 필요하다 — 필요한 칸만 실렸나
        vr = v["venue_rows"]
        assert vr and len(vr["home"]) > 10 and len(vr["away"]) > 10
        assert set(vr["home"][0]) == {"team", "played", "goals_for",
                                      "goals_against"}
        return
    pytest.skip("우리 팀이 든 표가 없다")


def test_기대_득점이_실측과_맞는다():
    """🔴 정답지 경기를 **경기 전 값**으로 계산한다 — 그것이 이 지시의 시험이다.

    사용자 폼 줄: *"홈 12경기 20득점 9실점"* · 라스베이거스 원정 12경기 18득 21실.
    실측 2026-10-02: λ 홈 1.911 · 원정 0.933 → 기대 **2.844** (리그 2.732).
      P(총 ≥ 4) 0.3179 vs 리그 기준 0.293 → 비율 **1.085** → 발동.
    ⚠️ 1차 판(맞대결 2.5 · 최근 2.2 vs 문턱 3.732)은 **미발동**이었고 결과는 3-2 였다.
    """
    avgs = {"home": 1.526, "away": 1.206}
    sac = {"team": "Sacramento", "played": 12, "goals_for": 20,
           "goals_against": 9}
    lv = {"team": "Las Vegas", "played": 12, "goals_for": 18,
          "goals_against": 21}
    got = league.open_game_ratio(sac, lv, avgs)
    assert got, "모형이 서지 않았다"
    assert abs(got["total"] - 2.844) < 0.01, got
    assert got["total"] > got["league_total"], got
    # 🔴 문턱은 yaml 이 정한다 — 여기 적지 않고 읽어서 비교한다
    need = float((rules.cross_rule("5c-1")["model"])["prob_ratio"])
    assert got["ratio"] >= need, (got, need)
    # 🔴 **못 잰 칸은 `None`** — 0 으로 때우지 않는다
    assert league.expected_goals({"team": "x"}, lv, avgs) is None


def test_포아송_설정이_코드에_박혀_있지_않다():
    """🔴 사본 금지 — `open_goals`·`prob_ratio` 는 yaml 이 원본이다.

    없으면 **멈춘다**(조용히 기본값을 쓰지 않는다).
    """
    src = strip_docs(inspect.getsource(league.open_game_ratio))
    assert "open_goals" in src and "cross_rule" in src
    # 🔴 숫자 리터럴로 때우지 않았나 — 설정 이름만 있고 값은 없어야 한다
    model = rules.cross_rule("5c-1")["model"]
    for key in ("open_goals", "prob_ratio"):
        assert str(model[key]) not in src, f"{key} 값이 코드에 박혀 있다"


# ══════════════════════════════════════════════════════════════════
# 🔴 하키도 **같은 이름**을 낸다 (사용자 지시 2026-10-02 — 라이브가 찾았다)
# ══════════════════════════════════════════════════════════════════


def test_하키_순위가_홈_원정_쪼갠_표를_낸다():
    """🔴 라이브 실측 2026-10-02: `home_field` 가 *"홈/원정 쪼갠 표가 없다"* 로
    **미결정**이었다 — 그런데 `standings/now` 응답이 그 칸을 다 들고 있었다
    (`homeGoalsFor`·`roadGoalsFor`…). **안 뽑고 있던 것이다.**

    ⚠️ 축구와 **같은 이름**을 내야 한다 — 이름이 갈리면 단계 5~7 이 종목별 분기를
       쓰고, 분기는 한 종목이 바뀔 때 다른 종목을 조용히 깨뜨린다.
    """
    from app.collect import nhl
    pages = _cassettes(lambda u: "api-web.nhle.com" in u and "/standings" in u)
    if not pages:
        pytest.skip("NHL 순위 카세트가 없다")
    for d in pages:
        facts = nhl.parse_standings(Fetched(d["url"], True, 200, d["text"]),
                                    Question(Q_LINEUP, "x", team="Detroit Red Wings"))
        if not facts:
            continue
        v = facts[0].value
        # 🔴 축구가 내는 칸과 **같은 이름**인가
        for key in ("league_avg_goals", "total_baseline", "open_game_threshold",
                    "home_advantage", "venue_averages", "venue_rows",
                    "league_tables"):
            assert key in v, f"{key} 가 없다 — 축구와 이름이 갈렸다"
        avgs = v["venue_averages"]
        assert avgs and avgs["home"] > 0 and avgs["away"] > 0, avgs
        # 🔴 합이 리그 평균과 맞나 — 두 셈이 서로를 검산한다
        assert abs((avgs["home"] + avgs["away"]) - v["league_avg_goals"]) < 0.05
        # ⚠️ **시즌 초라 표본이 작다** — 실측 2026-10-02 리그 전체 홈 12경기.
        #    수가 크다고 단정하지 않는다. 있는지와 꼴만 본다.
        assert v["home_advantage"] and v["home_advantage"]["home_games"] >= 1
        vr = v["venue_rows"]
        assert vr and len(vr["home"]) > 20 and len(vr["away"]) > 20
        # 🔴 **경계는 리그 규정에서 온다**(사용자 지시 2026-10-02) — 자료가 주지
        #    않는 수이고, 선언에 출처·확인 날짜가 붙는다. 전 판은 `None` 이었다.
        assert v["playoff_cut"] and v["cut_lines"], v
        assert v["cut_reason"], "경계를 어디서 얻었는지 안 적었다"
        # 🔴 하키에 무승부는 **없다** — `None` 이어야 한다(0 으로 때우지 않는다)
        assert v["draws"] is None
        assert all(r["draws"] is None for r in vr["home"])
        return
    pytest.skip("우리 팀 줄이 없다")


def test_하키_기대_득점이_선다():
    """🔴 그러면 포아송 격자도 하키에서 **선다** — 축구 전용이 아니다."""
    from app.collect import nhl
    pages = _cassettes(lambda u: "api-web.nhle.com" in u and "/standings" in u)
    if not pages:
        pytest.skip("NHL 순위 카세트가 없다")
    facts = nhl.parse_standings(
        Fetched(pages[0]["url"], True, 200, pages[0]["text"]),
        Question(Q_LINEUP, "x", team="Detroit Red Wings"))
    if not facts:
        pytest.skip("우리 팀 줄이 없다")
    v = facts[0].value
    vr, avgs = v["venue_rows"], v["venue_averages"]
    hr = next(r for r in vr["home"] if "Detroit" in r["team"])
    ar = next(r for r in vr["away"] if "Rangers" in r["team"])
    need = int(rules.cross_rule("5c-1")["model"]["min_venue_games"])
    # 🔴 **돌연변이가 통과해서 더한 줄이다.** 위 카세트는 홈 0경기라 `_rate` 가
    #    `None` 을 내 저절로 막힌다 — 그래서 표본 가드를 떼어내도 초록이었다.
    #    가드가 **실제로 일하는 구간**(0 < 경기수 < 문턱)으로 직접 물린다.
    thin_h = {"team": "H", "played": need - 1, "goals_for": 9,
              "goals_against": 3}
    thin_a = {"team": "A", "played": need - 1, "goals_for": 3,
              "goals_against": 9}
    assert league.expected_goals(thin_h, thin_a, avgs) is None, \
        f"표본 {need - 1}경기로 모형이 섰다 — 한 경기가 전부인 λ 다"
    fat = {k: (v * 9 if k in ("played", "goals_for", "goals_against") else v)
           for k, v in thin_h.items()}
    assert league.expected_goals(fat, {**thin_a, "played": need,
                                       "goals_for": 3 * need,
                                       "goals_against": 9}, avgs) is not None
    got = league.open_game_ratio(hr, ar, avgs)
    if min(hr["played"] or 0, ar["played"] or 0) < need:
        # 🔴 **표본이 모자라면 서지 않는다.** 실측 2026-10-02: 개막 직후라 홈
        #    0경기·원정 1경기였다 — 그 표로 λ 를 내면 한 경기가 전부다.
        assert got is None, got
        # 🔴 표본을 채워 주면 **선다** — 식이 하키에서도 돈다는 증거
        hr2 = {**hr, "played": need, "goals_for": 3 * need,
               "goals_against": 2 * need}
        ar2 = {**ar, "played": need, "goals_for": 2 * need,
               "goals_against": 3 * need}
        got = league.open_game_ratio(hr2, ar2, avgs)
    assert got and got["total"] > 0 and 0 < got["p"] < 1, got
    # 🔴 하키는 득점이 많다 — 리그 평균이 축구보다 **훨씬** 높아야 한다
    assert got["league_total"] > 4.0, got["league_total"]


def test_플레이오프_경계는_리그_규정에서_온다():
    """🔴 §4 `stakes` — *"몇 위까지 진출인가"* 는 **자료가 주지 않는다.**

    축구 fotmob 은 `legend[].indices` 로 알려 주고, NHL api-web 은
    `divisionSequence`·`wildcardSequence` 는 주지만 **`3`·`2` 라는 수는 안 준다.**
    ⚠️ 사본 금지와 충돌하지 않는다 — 리그 규정은 **우리 자료 어디에도 없다.**
       그래서 선언이 맞고, 선언에는 **출처와 확인 날짜**가 붙는다.
    """
    cfg = rules.playoff_cut("NHL")
    assert cfg and not cfg.get("unknown"), cfg
    assert cfg["division_top"] and cfg["wildcard_slots"]
    assert str(cfg["source"]).startswith("http"), "출처가 없다"
    assert cfg["verified"], "확인 날짜가 없다"
    # 🔴 **모르는 리그는 사유를 들고 있다** — 조용히 빈칸이 아니다
    #    ⚠️ NPB 는 2026-10-02 에 **빠졌다** — 클라이맥스 시리즈는 리그 **상위 3팀**이고
    #       그것은 한 수다. 전 판에 *"한 수로 안 떨어진다"* 고 적은 것이 틀렸다
    #       (사용자 지시 *"변수 0건은 말이 안된다"* 가 그 오판을 드러냈다).
    assert rules.playoff_cut("USL Championship").get("unknown")
    assert int(rules.playoff_cut("NPB")["division_top"]) == 3
    # 🔴 **아예 선언 없는 리그는 빈 dict** — 지어내지 않는다
    assert rules.playoff_cut("없는리그") == {}


def test_하키_순위가_경계를_두_개로_낸다():
    """🔴 하키는 경계가 **둘이다** — 디비전 순위와 와일드카드 순번.

    하나로 뭉개면 *"5위인데 진출권"*(와일드카드로 들어가는 자리)을 설명할 수 없다.
    🔴 값은 yaml 이 원본이고 **코드에 박히지 않았나**를 함께 본다.
    """
    from app.collect import nhl
    pages = _cassettes(lambda u: "api-web.nhle.com" in u and "/standings" in u)
    if not pages:
        pytest.skip("NHL 순위 카세트가 없다")
    facts = nhl.parse_standings(
        Fetched(pages[0]["url"], True, 200, pages[0]["text"]),
        Question(Q_LINEUP, "x", team="Detroit Red Wings"))
    if not facts:
        pytest.skip("우리 팀 줄이 없다")
    v = facts[0].value
    cfg = rules.playoff_cut("NHL")
    assert v["cut_lines"] and len(v["cut_lines"]) == 2, v["cut_lines"]
    assert v["playoff_cut"] == int(cfg["division_top"])
    assert str(cfg["source"]) in str(v["cut_reason"]), v["cut_reason"]
    # 🔴 수를 코드에 박지 않았나 — 선언에서 읽어 쓴다
    src = strip_docs(inspect.getsource(nhl._cut))
    for key in ("division_top", "wildcard_slots"):
        assert str(cfg[key]) not in src, f"{key} 값이 코드에 박혀 있다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **변수가 λ 에 닿는다** — 딥서치 2026-10-03 (사용자 지시)
# ══════════════════════════════════════════════════════════════════
#
# > ① 무게를 확률로 둘지 근거와 곱할지(A/B/C) 이거는 **딥서치 해서 찾아라**
#
# 답은 **A** 다: 확률에 근거를 **곱하지 않고**(그러면 확률이 아니게 된다) 변수가
# **λ 를 움직인다.** 🔴 단 **계수를 짓지 않는 자리**에만 — 야구 선발이 그 자리다
# (`ERA` 의 정의가 *"9이닝당 자책점"* 이라 맞출 모수가 없다).


def test_평범한_선발은_모형을_건드리지_않는다():
    """🔴 **이 꼴을 고른 까닭이다.** 선발 ERA = 팀 ERA 면 배수가 정확히 1 이다.

    ⚠️ 자료가 *"평범하다"* 고 말할 때 모형을 밀면 그것이 지어내는 것이다.
    """
    f, why = league.starter_factor(era_starter=3.5, era_team=3.5, innings=6.0,
                                   season_innings=150.0)
    assert f == 1.0, (f, why)


def test_좋은_선발은_상대_득점을_낮춘다():
    """🔴 산수 그대로다 — `(이닝/9)×(ERA선발/ERA팀) + (1−이닝/9)`."""
    f, why = league.starter_factor(era_starter=1.99, era_team=2.88, innings=6.2,
                                   season_innings=150.0)
    assert 0.78 < f < 0.79, (f, why)
    assert "1.99" in why and "2.88" in why, why
    bad, _ = league.starter_factor(era_starter=5.0, era_team=3.0, innings=6.0,
                                   season_innings=150.0)
    assert bad > 1.0, bad


def test_표본이_모자라면_λ를_건드리지_않는다():
    """🔴🔴 실측 2026-10-03: 唐川(은퇴 등판)의 그 해 성적이 **1경기 5이닝 ERA 7.20**
    이었고, 그 수로 보정하니 상대 기대 득점이 **4.66 → 6.92(+48%)** 로 튀었다.

    ⚠️ 표본으로 줄이는(shrinkage) 방법은 **사전 분포의 세기**라는 맞출 모수를
       요구한다 — 금지다. 그래서 **문턱**으로 막고, 문턱은 yaml 이 정한다.
    """
    floor = rules.variable_types()["pitcher_state"]["min_innings"]
    f, why = league.starter_factor(era_starter=7.2, era_team=3.85, innings=5.0,
                                   season_innings=float(floor) - 1)
    assert f is None and str(floor) in why, (f, why)
    # 🔴 문턱을 넘으면 선다
    ok, _ = league.starter_factor(era_starter=7.2, era_team=3.85, innings=5.0,
                                  season_innings=float(floor) + 1)
    assert ok is not None and ok > 1.0, ok
    # 🔴 **못 재면 보정하지 않는다** — 모르는 것을 통과시키지 않는다
    f2, why2 = league.starter_factor(era_starter=2.0, era_team=3.0, innings=6.0)
    assert f2 is None and "모른다" in why2, why2


def test_셋_중_하나라도_없으면_보정하지_않는다():
    """🔴 반쪽으로 모형을 돌리지 않는다 — **사유를 이름으로** 돌려준다."""
    for kw in ({"era_starter": None, "era_team": 3.0, "innings": 6.0,
                "season_innings": 150.0},
               {"era_starter": 2.0, "era_team": None, "innings": 6.0,
                "season_innings": 150.0},
               {"era_starter": 2.0, "era_team": 3.0, "innings": None,
                "season_innings": 150.0}):
        f, why = league.starter_factor(**kw)
        assert f is None and "없다" in why, (kw, why)
    f, why = league.starter_factor(era_starter=2.0, era_team=0.0, innings=6.0,
                                   season_innings=150.0)
    assert f is None and "0 이하" in why


def test_선발이_λ를_움직인다():
    """🔴🔴 **변수가 생존에 닿는 자리다.** 교차가 맞나까지 본다.

    ⚠️ 홈팀 득점을 누르는 것은 **원정 선발**이다 — 바꿔 넣으면 조용히 반대로 틀린다.
    """
    home = {"team": "H", "played": 20, "goals_for": 80, "goals_against": 70}
    away = {"team": "A", "played": 20, "goals_for": 90, "goals_against": 60}
    avgs = {"home": 4.0, "away": 4.0}
    base = league.expected_goals(home, away, avgs)
    assert base is not None
    got = league.expected_goals(home, away, avgs, starters={
        "away": {"era_starter": 1.5, "era_team": 3.0, "innings": 6.0,
                 "season_innings": 150.0}})
    assert got["home"] < base["home"], (got, base)
    assert got["away"] == base["away"], (got, base)
    assert any("홈 득점 ← 원정 선발" in n for n in got["starter_notes"])
    got2 = league.expected_goals(home, away, avgs, starters={
        "home": {"era_starter": 1.5, "era_team": 3.0, "innings": 6.0,
                 "season_innings": 150.0}})
    assert got2["away"] < base["away"] and got2["home"] == base["home"]


def test_선발_보정이_두_길에_같이_걸렸다():
    """🔴 카드의 λ 와 시나리오의 λ 가 **갈리면 안 된다**(사본 금지).

    ⚠️ D46 — 독스트링·주석을 뺀 **코드만** 본다.
    """
    from app import analyze, scenarios
    from tests._helpers import strip_docs
    for fn in (analyze.grid, scenarios._grid):
        src = strip_docs(inspect.getsource(fn))
        assert "starters=" in src and "starters_for(" in src, fn.__name__


def test_선발_보정에_지어낸_계수가_없다():
    """🔴🔴 **계수는 짓지 않는다**(CLAUDE.md). 쓰는 수는 `INNINGS`(=9)뿐이다.

    ⚠️ 9 는 지어낸 값이 아니라 **ERA 의 정의**다(9이닝당 자책점).
    """
    import re as _re

    from tests._helpers import strip_docs
    src = strip_docs(inspect.getsource(league.starter_factor))
    # 🔴 **구조 상수만 허용한다**: `0.0`(바닥) · `1.0`(항등). 그 밖의 소수는
    #    전부 "어디서 왔나"를 못 대는 수이고, 그것이 지어낸 계수다.
    ok = {"0.0", "1.0"}
    nums = {x for x in _re.findall(r"(?<![\w.])\d+\.\d+", src)} - ok
    assert not nums, f"선발 보정에 지어낸 계수가 있다: {nums}"
    assert "INNINGS" in src and league.INNINGS == 9.0


def test_선수_페이지_표기를_그대로_읽는다():
    """🔴 실측 2026-10-03 — npb.jp 선수 페이지가 **칸을 쪼개서** 그린다.

    | 표기 | 뜻 | 전 판이 읽은 값 |
    |---|---|---|
    | `投球回` 가 **두 칸**(`117` + `.1`) | 117⅓이닝 | 🔴 머리글 자리로 읽어 **자책점**을 ERA 로 읽었다 |
    | `1264 .2` (칸 안에 공백) | 1264⅔이닝 | 🔴 `None`(이닝이 통째로 안 들어왔다) |
    """
    from app.collect import npb
    assert npb._ip("1264 .2") == 1264.667
    assert npb._ip("117.1") == 117.333
    assert npb._ip("88") == 88.0
    # 🔴 읽을 수 없는 것은 `None` — 0 으로 때우지 않는다
    assert npb._ip("abc") is None


def test_선수_이름을_제목에서_읽는다():
    """🔴 실측 2026-10-03: `id="pc_v_name"` 선택자가 **등번호 `19`** 를 집었다."""
    from app.collect import npb
    html = ("<title>唐川　侑己（千葉ロッテマリーンズ） | 個人年度別成績 | "
            "NPB.jp 日本野球機構</title>")
    assert npb._player_name(html) == "唐川侑己"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **라인업 시장가치** — 딥서치 2026-10-03 (사용자 지시)
# ══════════════════════════════════════════════════════════════════
#
# > 축구 라인업 시장가치 소스를 쓰나? **딥서치해서 찾아서 넣어라.**
#
# ✅ 자료는 이미 손에 있었다(fotmob 라인업의 `marketValue` — 선발·교체 전원).
# 🔴 **λ 에는 넣지 않는다**: 가치를 골 단위로 바꾸는 계수가 발표된 적이 없다.
#    발표된 모형(Peeters 2018 · arXiv 2411.09085)은 `(log 가치차)` 순서 프로빗으로
#    승/무/패를 내고 **계수는 논문에 실려 있지 않다.** → 변수로만 쓴다.


def test_라인업_가치가_λ에_닿지_않는다():
    """🔴🔴 **이 계약이 요점이다.** 가치는 변수이고 λ 는 안 건드린다.

    ⚠️ 누가 `starter_factor` 처럼 가치 배수를 만들면 여기서 빨개진다 — 그 순간
       **발표되지 않은 탄력성을 지어낸 것**이다(CLAUDE.md: 계수는 짓지 않는다).
    """
    from tests._helpers import strip_docs
    src = strip_docs(inspect.getsource(league))
    for bad in ("market_value", "marketvalue", "value_sum"):
        assert bad not in src.lower(), f"`league.py` 가 {bad} 로 λ 를 만든다"


def test_가치_하락은_그_팀_반대_방향이다():
    """🔴 §4 `direction_rule` 그대로 — 약해진 팀의 반대다."""
    from app import classify
    g = classify.Game(home="A", away="B", sport="soccer", league="X")
    cfg = rules.variable_types()["lineup_value"]
    drop = float(cfg["value_drop_pct"])
    val = {"team": "A", "pct": -(drop + 5), "today_value": 800,
           "baseline_value": 1000, "lineup_kind": "confirmed"}
    side, why, bad = classify._dir_lineup_value(val, g)
    assert side == "away" and not bad, (side, why, bad)
    assert "반대 방향" in why


def test_문턱_아래는_배경이고_예상_XI_는_안_쓴다():
    """🔴 작은 차이를 변수로 세면 **모든 경기에 변수가 생긴다** — 그건 변수가 아니다.

    🔴 그리고 **확정 XI 가 아니면 쓰지 않는다** — 예상 XI 로 하락을 말하면 거짓이다.
    """
    from app import classify
    g = classify.Game(home="A", away="B", sport="soccer", league="X")
    small = {"team": "A", "pct": -1.0, "today_value": 990,
             "baseline_value": 1000, "lineup_kind": "confirmed"}
    side, why, bad = classify._dir_lineup_value(small, g)
    assert side is None and not bad and "비슷하다" in why, (side, why, bad)
    # 🔴 예상 XI → **미결정**(배경이 아니다 — 자료가 아직 아니다)
    guess = {**small, "pct": -40.0, "lineup_kind": "baseline"}
    side2, _, bad2 = classify._dir_lineup_value(guess, g)
    assert side2 is None and "확정 XI" in bad2, bad2


def test_가치_합은_인원이_다_읽혀야_쓴다():
    """🔴 11명 중 일부만 읽히면 합이 작아져 **거짓 하락**이 된다."""
    from app.collect import fotmob
    team = {"starters": [{"marketValue": 100} for _ in range(11)]}
    assert fotmob.value_sum(team) == (1100, 11)
    # 🔴 한 명도 못 읽으면 `(None, 0)` — 0 으로 때우지 않는다
    assert fotmob.value_sum({"starters": [{"name": "x"}]}) == (None, 0)
    assert fotmob.value_sum({}) == (None, 0)
    need = rules.variable_types()["lineup_value"]["min_value_players"]
    assert int(need) == 11, need


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **B — 버리던 칸을 읽는다** (사용자 지적 2026-10-03)
# ══════════════════════════════════════════════════════════════════


def test_전반_스코어를_골_분에서_유도한다():
    """🔴 페이로드에 전반 칸이 **없다** — 과거 경기의 골 분(`≤45`)에서 유도한다.

    ⚠️ 무료 CSV(`football-data.co.uk`)에는 `HTHG/HTAG` 가 있으나 **클럽 리그만**이고
       대표팀 친선이 없다. 그래서 외부 소스를 들이지 않았다.
    """
    from app.collect import fotmob
    j = {"props": {"pageProps": {"content": {"matchFacts": {"events": {
        "events": [
            {"type": "Goal", "time": 16, "isHome": False},
            {"type": "Goal", "time": 44, "isHome": True},
            {"type": "Goal", "time": 45, "isHome": True},   # 전반 추가시간
            {"type": "Goal", "time": 70, "isHome": True},   # 후반 — 안 센다
            {"type": "Card", "time": 20, "isHome": True},   # 골이 아니다
        ]}}}}}}
    assert fotmob.half_time_score(j) == (2, 1)
    # 🔴 자기 골은 **상대 득점**이다
    j2 = {"props": {"pageProps": {"content": {"matchFacts": {"events": {
        "events": [{"type": "Goal", "time": 10, "isHome": True,
                    "ownGoal": True}]}}}}}}
    assert fotmob.half_time_score(j2) == (0, 1)
    # 🔴 **골 이벤트가 없으면 `None`** — 0-0 경기와 "못 읽었다"를 섞지 않는다
    j3 = {"props": {"pageProps": {"content": {"matchFacts": {"events": {
        "events": [{"type": "Card", "time": 5, "isHome": True}]}}}}}}
    assert fotmob.half_time_score(j3) is None
    assert fotmob.half_time_score({}) is None


def test_맞대결_주소는_조각_번호로_연다():
    """🔴 fotmob 맞대결 목록의 슬러그는 **지금 경기** 것이다 — 과거 경기는 `#` 뒤
    번호다. `#` 앞만 쓰면 열 때마다 **같은 경기**가 열린다(실측: 2차 소스 1개)."""
    from app.blackboard import Fact
    from app.collect import fotmob
    f = Fact(question_id="lineup:x:h2h", value={"matches": [
        {"matchUrl": "/matches/paraguay-vs-colombia/1utthz#4196575"},
        {"matchUrl": "/matches/paraguay-vs-colombia/1utthz#4377210"},
        {"matchUrl": "/matches/paraguay-vs-colombia/1utthz"},   # 조각 없음 → 건너뛴다
    ]}, hardness="hard")
    got = fotmob.sources_followup([f], "fotmob-6299693")
    assert [s.url for s in got] == [fotmob.match_url("4196575"),
                                    fotmob.match_url("4377210")], got
    # 🔴 접두가 아니면 안 돈다
    assert fotmob.sources_followup([f], "npb-20261003-m-h") == []


def test_연속_전반_리드를_묶음이_센다():
    """🔴 전반 스코어는 경기마다 **따로** 오고, "연속"은 날짜 순으로 이어야 나온다.

    ⚠️ 방향을 만들지 않는다 — `h2h_pattern` 변수의 **사유에 얹힌다**(이중 계산 금지).
    """
    from app import classify
    from app.blackboard import Fact
    g = classify.Game(home="Colombia", away="Paraguay", sport="soccer",
                      league="Friendlies")
    facts = [
        Fact(question_id="lineup:x:h2h", value={"matches": [], "team": "Colombia"},
             hardness="hard", team="Colombia"),
        Fact(question_id="lineup:x:h2h_half",
             value={"date": "2025-03-26", "home": "Colombia", "away": "Paraguay",
                    "ht_home": 2, "ht_away": 1}, hardness="soft"),
        Fact(question_id="lineup:x:h2h_half",
             value={"date": "2024-06-24", "home": "Colombia", "away": "Paraguay",
                    "ht_home": 2, "ht_away": 0}, hardness="soft"),
        Fact(question_id="lineup:x:h2h_half",
             value={"date": "2023-11-21", "home": "Paraguay", "away": "Colombia",
                    "ht_home": 0, "ht_away": 1}, hardness="soft"),
    ]
    classify._fill_half_time(facts, g)
    h2h = facts[0].value
    assert h2h["ht_lead_streak"] == 3 and h2h["ht_sample"] == 3, h2h
    assert "연속 전반 리드" in classify._h2h_tail(h2h)
    # 🔴 끊기면 0 이고 **그 사실도 적는다**
    assert "없음" in classify._h2h_tail({"ht_lead_streak": 0, "ht_sample": 3})


def test_중립_구장을_잰다():
    """🔴 `countryCode=INT` 이고 구장 나라가 홈팀 이름과 안 맞으면 **중립**이다.

    ⚠️ `INT` 가 아니면 판정하지 않는다 — 리버풀과 England 는 이름이 안 맞지만
       그것이 중립을 뜻하지 않는다.
    """
    from app.cells import Question
    from app.collect import fotmob

    def _j(cc, country, home):
        return {"props": {"pageProps": {
            "general": {"countryCode": cc, "homeTeam": {"name": home},
                        "awayTeam": {"name": "X"},
                        "matchTimeUTCDate": "2026-10-03T00:00:00Z"},
            "content": {"matchFacts": {"infoBox": {
                "Stadium": {"name": "S", "country": country}}}}}}}

    q = Question("lineup", "x", team="Colombia", league="Friendlies")
    got = fotmob.parse_info(_j("INT", "United States", "Colombia"), q,
                            url="u", when=None)
    assert got and got[0].value["neutral_venue"] is True, got
    got2 = fotmob.parse_info(_j("INT", "China", "China"), q, url="u", when=None)
    assert got2[0].value["neutral_venue"] is False
    # 🔴 클럽 경기는 **판정하지 않는다**
    got3 = fotmob.parse_info(_j("ENG", "England", "Liverpool"), q, url="u",
                             when=None)
    assert "neutral_venue" not in got3[0].value, got3[0].value


def test_맞대결은_경기_하나에_한_번이다():
    """🔴🔴 실측 2026-10-03 — 같은 맞대결이 **변수 둘**로 세어졌다.

        콜–파: `R1 [h2h_pattern·home]` + `R5 [h2h_pattern·home]` (같은 10경기)
        NPB:  `R3 [h2h_pattern·away]` + `R4 [h2h_pattern·away]` (같은 22경기)

    깊이 세포가 **팀마다** 돌아 같은 맞대결이 사실 둘로 오고, 그 둘이 변수 둘이 됐다.
    ⚠️ 종전에는 두 사유가 **글자까지 같아서** 우연히 지워졌다 — 전반 연속 리드를
       사유에 적자(팀마다 다르다) 그 우연이 깨져 드러났다.
    """
    from app import classify
    assert "h2h_pattern" in classify.GAME_LEVEL
    g = classify.Game(home="A", away="B", sport="soccer", league="X")
    two = [classify.Classified(text="t1", source_url="u1", type="h2h_pattern",
                               direction="home", hardness="hard", team="A",
                               why="§4 h2h_pattern — A 8경기 연속 전반 리드"),
           classify.Classified(text="t2", source_url="u2", type="h2h_pattern",
                               direction="home", hardness="hard", team="B",
                               why="§4 h2h_pattern — 전반 연속 리드 없음")]
    got = classify._dedupe_variables(two)
    assert len([c for c in got if c.is_variable]) == 1, [c.why for c in got]
    del g


def test_같은_과거_경기를_두_번_세지_않는다():
    """🔴 깊이 세포가 팀마다 도므로 같은 4경기가 **8건**으로 들어와 연속이
    `8경기` 로 부풀었다(실제 4경기)."""
    from app import classify
    from app.blackboard import Fact
    g = classify.Game(home="Colombia", away="Paraguay", sport="soccer",
                      league="Friendlies")
    one = {"date": "2025-03-26", "home": "Colombia", "away": "Paraguay",
           "ht_home": 2, "ht_away": 1}
    facts = [Fact(question_id="lineup:x:h2h", value={"matches": []},
                  hardness="hard", team="Colombia")]
    # 🔴 같은 경기를 **두 번** 넣는다(팀마다 한 번씩 온 꼴)
    for _ in range(2):
        facts.append(Fact(question_id="lineup:x:h2h_half", value=dict(one),
                          hardness="soft"))
    classify._fill_half_time(facts, g)
    v = facts[0].value
    assert v["ht_sample"] == 1, v
    assert v["ht_lead_streak"] == 1 and v["ht_lead_team"] == "Colombia", v
    # 🔴 꼬리에 **누구의 연속인지** 적는다
    assert "Colombia" in classify._h2h_tail(v)
