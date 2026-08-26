"""리서치 응답 품질 게이트 — 프롬프트 문구 노출 차단·재료 없으면 분석 금지·
문구 중복 차단·종목별 용어 분리 회귀 테스트.

실사고(2026-08-24 슬레이트): Perplexity가 데이터를 못 찾자 우리가 보낸 요청 문구를
되풀이하는 산문을 돌려줬고, 그것이 "선발 최근:" 자리에 데이터인 척 출력됐다.
또 서로 다른 두 경기(디트로이트-탬파베이 / 마이애미-보스턴)의 "조심할 점"·"걸 만한가"가
동일 문장이었고, 야구 경기에 "킥오프 직전"이 나갔다.
"""

import pytest

from app.pipeline import (
    DETAIL_SEP,
    NO_MATERIAL_MSG,
    line_is_game_specific,
    render_game_easy,
    render_game_section,
    render_games_easy,
)
from app.research.validate import (
    clean_text,
    has_material,
    invalid_reason,
    is_prompt_echo,
    is_unavailable_prose,
    sanitize_research,
)

# 실제로 화면에 출력됐던 오염 값 (게임 406 캐시)
LEAKED_LAST5 = ("최근 5~7경기별 일자·상대·이닝·실점·피OPS 등을 확인할 수 있는 상세 로그에 "
                "접근할 수 없어, 정확한 최근 5~7경기 ERA/피OPS/이닝을 제시할 수 없다.")
LEAKED_NOTE = ("실시간 경기 전적과 득점 추세를 확인할 수 있는 데이터 소스에 현재 접근할 수 없어 "
               "구체 수치를 제공할 수 없다.")


# ---------------------------------------------------------------- [1] 파싱 검증

def test_leaked_prompt_prose_is_invalid():
    """[1] 요청 문구를 되풀이한 '확인 불가' 산문은 데이터가 아니다."""
    assert invalid_reason(LEAKED_LAST5) == "unavailable"
    assert invalid_reason(LEAKED_NOTE) == "unavailable"
    assert is_unavailable_prose(LEAKED_LAST5)


def test_schema_placeholder_is_invalid():
    """[1] 스키마 자리표시자를 그대로 돌려준 응답도 무효."""
    assert is_prompt_echo("최근 5~7경기 ERA·피OPS·이닝 요약(한국어)")
    assert invalid_reason("WWLWL (최근 5경기, 최신부터)") == "prompt_echo"


def test_recent_form_without_number_is_invalid():
    """[1] recent_form류 텍스트에 숫자가 없으면 무효."""
    assert invalid_reason("타선 흐름이 좋다") == "no_number"
    assert invalid_reason("최근 5경기 팀 OPS .812로 상승세") is None   # 정상 데이터는 통과


def test_real_data_survives_validation():
    """[1] 오탐 방지 — 수치가 있는 진짜 데이터는 그대로 살아남는다."""
    ok = [
        "8/15 vs SGT 1-0 승, 8/12 @ MCF 2-2 무, 8/7 vs CRY 2-1 패",
        "최근 5경기 ERA 2.41, 피OPS .610, 평균 6.2이닝",
        "리그 23경기 9승 7무 7패, 홈 13경기 4승 5무 4패",
    ]
    for text in ok:
        assert invalid_reason(text) is None, text


def test_sanitize_drops_polluted_fields_and_reports_no_material():
    """[1][2] 오염 페이로드는 정제 후 '재료 없음'으로 떨어진다."""
    payload = {
        "home_recent_form": {"form": None, "runs_avg": None, "note": LEAKED_NOTE},
        "away_recent_form": {"form": None, "runs_avg": None, "note": LEAKED_NOTE},
        "home_pitcher": {"name": "Framber Valdez", "last5": LEAKED_LAST5,
                         "era_recent": None, "era_season": 4.35},
        "absences": ["현재 결장자 정보는 확인 불가"],
        "expert_picks": [], "form_reversal": [], "predicted_scores": [],
    }
    clean, dropped = sanitize_research(payload, "mlb")
    assert "note" not in (clean.get("home_recent_form") or {})
    assert "last5" not in (clean.get("home_pitcher") or {})
    assert clean["absences"] == []
    assert not has_material(clean)
    assert len(dropped) >= 4


async def test_deep_research_rejects_material_less_response(monkeypatch):
    """[1] 재료 없는 응답은 1회 재요청 후에도 실패로 처리한다 (성공인 척 금지)."""
    import json as _json

    from app.research.deep import ResearchUnusableError, deep_research_game
    from app.research.perplexity import PerplexityClient

    calls = []
    body = _json.dumps({
        "home_recent_form": {"form": None, "note": LEAKED_NOTE},
        "away_recent_form": {"form": None, "note": LEAKED_NOTE},
        "home_pitcher": {"name": "A", "last5": LEAKED_LAST5},
        "absences": [], "expert_picks": [],
    }, ensure_ascii=False)

    class FakeClient(PerplexityClient):
        def __init__(self):
            super().__init__(mock=False)

        async def chat(self, prompt):
            calls.append(prompt)
            return {"choices": [{"message": {"content": body}}]}

    game = {"home": "Detroit Tigers", "away": "Tampa Bay Rays", "league": "MLB",
            "starts_at": "2026-08-25T22:40:00+00:00"}
    with pytest.raises(ResearchUnusableError):
        await deep_research_game(game, "mlb", FakeClient())
    assert len(calls) == 2   # 1회 재요청까지 시도


# ---------------------------------------------------------------- [2][3][4] 렌더

def _mlb_jg(**over):
    jg = {
        "game_id": 406, "sport": "mlb", "home": "Detroit Tigers", "away": "Tampa Bay Rays",
        "league": "MLB", "status": "scheduled", "status_label": "",
        "starts_at_kst": "08/25 07:40", "model_valid": True,
        "p_model": 0.438, "p_market": 0.451, "p_claude": 0.42,
        "market_probs": {"Detroit Tigers": 0.451, "Tampa Bay Rays": 0.549},
        "best_odds": {"Detroit Tigers": 2.22, "Tampa Bay Rays": 1.79},
        "stats": {"home_pitcher": "Framber Valdez", "away_pitcher": "Drew Rasmussen"},
        "expert_picks": [], "judge_confidence": "medium", "judge_pass": False,
        "verdict": "레이즈 우위",
        "pick_summary": {"side": "Tampa Bay Rays", "desc": "탬파베이 레이스 승",
                         "market": "h2h", "odds": 1.79, "p_final": 0.56, "ev": -0.001,
                         "flags": [], "approved": False, "reject_reason": "판정 패스 권장 경기"},
        "market_board": [
            {"market": "h2h", "side": "Tampa Bay Rays", "line": None,
             "desc": "탬파베이 레이스 승", "odds": 1.79, "p": 0.56, "ev": -0.001,
             "axes_kr": "실데이터+모델", "approved": True, "reject_reason": None},
            {"market": "totals", "side": "Under", "line": 7.5, "desc": "언더 7.5",
             "odds": 1.98, "p": 0.54, "ev": 0.069, "axes_kr": "전문가+시장",
             "approved": True, "reject_reason": None},
        ],
        "research": {
            "home_recent_form": {"form": "WLWLL", "runs_avg": 3.9},
            "away_recent_form": {"form": "WWLWW", "runs_avg": 5.2},
            "home_pitcher": {"name": "Framber Valdez", "era_season": 4.35},
            "absences": ["Detroit Tigers의 Riley Greene 손목 부상 결장"],
        },
    }
    jg.update(over)
    _grade(jg)
    return jg


def _grade(jg: dict) -> None:
    from app.engine.markets import grade_candidate

    for c in jg.get("market_board") or []:
        c["grade"], c["grade_note"] = grade_candidate(c)


def _mlb_jg2(**over):
    jg = _mlb_jg(
        game_id=407, home="Miami Marlins", away="Boston Red Sox",
        p_model=0.521, p_market=0.464, p_claude=0.50,
        market_probs={"Miami Marlins": 0.464, "Boston Red Sox": 0.536},
        best_odds={"Miami Marlins": 2.12, "Boston Red Sox": 1.84},
        stats={"home_pitcher": "Sandy Alcantara", "away_pitcher": "Ranger Suarez"},
        pick_summary={"side": "Miami Marlins", "desc": "마이애미 말린스 승",
                      "market": "h2h", "odds": 2.12, "p_final": 0.49, "ev": 0.035,
                      "flags": [], "approved": False, "reject_reason": "판정 패스 권장 경기"},
        market_board=[
            {"market": "h2h", "side": "Miami Marlins", "line": None,
             "desc": "마이애미 말린스 승", "odds": 2.12, "p": 0.49, "ev": 0.035,
             "axes_kr": "모델", "approved": True, "reject_reason": None},
            {"market": "spreads", "side": "Miami Marlins", "line": 1.5,
             "desc": "마이애미 말린스 런라인 +1.5", "odds": 1.65, "p": 0.60, "ev": -0.01,
             "axes_kr": "시장", "approved": True, "reject_reason": None},
        ],
        research={
            "home_recent_form": {"form": "WWWLL", "runs_avg": 4.4},
            "away_recent_form": {"form": "WWLWW", "runs_avg": 4.8},
            "home_pitcher": {"name": "Sandy Alcantara", "era_season": 3.46},
            "absences": ["Boston Red Sox의 Trevor Story 결장"],
        },
    )
    jg.update(over)
    _grade(jg)
    return jg


def _soccer_jg(**over):
    jg = {
        "game_id": 341, "sport": "soccer", "home": "Fulham", "away": "Chelsea",
        "league": "EPL", "status": "scheduled", "status_label": "",
        "starts_at_kst": "08/25 23:00", "model_valid": True,
        "p_model": 0.35, "p_market": 0.30, "p_claude": 0.32,
        "market_probs": {"Fulham": 0.30, "Draw": 0.30, "Chelsea": 0.40},
        "best_odds": {"Fulham": 3.30, "Draw": 3.40, "Chelsea": 2.20},
        "stats": {}, "expert_picks": [], "judge_confidence": "medium",
        "verdict": "첼시 우위",
        "pick_summary": {"side": "Chelsea", "desc": "첼시 승", "market": "h2h",
                         "odds": 2.20, "p_final": 0.42, "ev": -0.076, "flags": [],
                         "approved": False, "reject_reason": "EV 없음"},
        "research": {
            "home_recent_form": {"form": "WWDLW", "gf5": 8, "ga5": 6, "rank": 9},
            "away_recent_form": {"form": "WWDLL", "gf5": 10, "ga5": 5, "rank": 4},
            "absences": ["Fulham의 Joachim Andersen 징계 결장"],
        },
    }
    jg.update(over)
    _grade(jg)
    return jg


def test_no_prompt_phrase_reaches_output():
    """[1] 오염 리서치가 캐시에 남아 있어도 렌더 단계에서 걸러진다."""
    jg = _mlb_jg(research={
        "home_recent_form": {"form": "WLWLL", "note": "최근 30일 좌/우완 상대 타선 성적 요약(한국어)"},
        "away_recent_form": {"form": None, "note": LEAKED_NOTE},
        "home_pitcher": {"name": "Framber Valdez", "last5": LEAKED_LAST5},
        "absences": [],
    })
    out = render_game_section(jg)
    for fragment in ("등을 확인할 수 있는", "접근할 수 없", "요약(한국어)", "제시할 수 없"):
        assert fragment not in out, f"프롬프트/미확보 문구 노출: {fragment}"
    assert "선발 최근:" not in out   # 무효 last5는 줄 자체가 사라진다


def test_no_material_blocks_deep_analysis():
    """[2] recent_form·전문가 픽·부상 정보가 모두 비면 심층 분석을 만들지 않는다."""
    jg = _mlb_jg(research={"home_recent_form": {}, "away_recent_form": {},
                           "absences": [], "expert_picks": []})
    out = render_game_section(jg)
    assert NO_MATERIAL_MSG in out
    assert "⑧ 마켓 보드" not in out and "판단:" not in out
    assert len(out.splitlines()) <= 3


def test_two_games_do_not_share_sentences():
    """[3] 서로 다른 경기의 '조심할 점'·'걸 만한가'가 동일하면 안 된다."""
    easy_a, easy_b = (x.split(DETAIL_SEP)[0]
                      for x in render_games_easy([_mlb_jg(), _mlb_jg2()]))

    def pick(text, prefix):
        return next((ln for ln in text.splitlines() if ln.startswith(prefix)), None)

    for prefix in ("걸 만한가?", "조심할 점:"):
        a, b = pick(easy_a, prefix), pick(easy_b, prefix)
        assert a and b, f"{prefix} 줄 누락"
        assert a != b, f"두 경기의 {prefix} 문장이 동일: {a}"


def test_every_line_carries_game_specific_token():
    """[3] 각 줄은 그 경기 고유의 숫자나 선수 이름을 최소 1개 포함한다."""
    jg = _mlb_jg()
    easy = render_game_easy(jg).split(DETAIL_SEP)[0]
    names = ["Framber Valdez", "Drew Rasmussen", "Riley Greene"]
    for line in easy.splitlines():
        if line.startswith(("걸 만한가?", "조심할 점:")):
            assert line_is_game_specific(line, names), f"고유 수치/이름 없음: {line}"


def test_generic_caution_line_is_omitted_when_not_specific():
    """[3] 고유 수치·이름을 못 만들면 '조심할 점' 줄을 생략한다 (빈말 금지)."""
    jg = _soccer_jg(
        research={"home_recent_form": {"form": "WWDLW"}, "absences": []},
        market_probs={"Fulham": 0.35, "Draw": 0.20, "Chelsea": 0.45},
        starts_at_kst="", model_valid=True, p_market=None,
    )
    easy = render_game_easy(jg).split(DETAIL_SEP)[0]
    assert not [ln for ln in easy.splitlines() if ln.startswith("조심할 점:")]


def test_baseball_never_says_kickoff():
    """[4] 야구 출력에 '킥오프'가 등장하지 않고 '라인업 발표'를 쓴다."""
    jg = _mlb_jg(research={"home_recent_form": {"form": "WLWLL"}, "absences": []})
    out = render_game_easy(jg)
    assert "킥오프" not in out
    caution = [ln for ln in out.splitlines() if ln.startswith("조심할 점:")]
    assert caution and "라인업 발표" in caution[0]


def test_soccer_uses_kickoff_wording():
    """[4] 축구는 '킥오프 직전' 표현을 유지한다."""
    jg = _soccer_jg(
        research={"home_recent_form": {"form": "WWDLW"}, "absences": []},
        market_probs={"Fulham": 0.35, "Draw": 0.20, "Chelsea": 0.45},  # 무승부 경고 조건 밖
    )
    easy = render_game_easy(jg).split(DETAIL_SEP)[0]
    assert "킥오프 직전" in easy


def test_sport_specific_market_wording():
    """[4] 야구엔 '더블찬스'가 없고 핸디캡은 '런라인'으로 표기한다."""
    from app.engine.markets import reviewed_markets_kr, spread_desc

    assert "더블찬스" not in reviewed_markets_kr("mlb")
    assert "더블찬스" in reviewed_markets_kr("soccer")
    assert spread_desc("mlb", "디트로이트", -1.5) == "디트로이트 런라인 -1.5"
    assert spread_desc("soccer", "첼시", 1.5) == "첼시 핸디 +1.5"


async def test_material_less_cache_does_not_burn_quota(redis_client, monkeypatch):
    """[1][2] 6시간 내 조사했는데 재료가 없으면 즉시 '리서치 실패' — 재조사 콜을 낭비하지 않는다."""
    import json as _json
    from datetime import UTC, datetime, timedelta

    import app.research.deep as deepmod

    called = []

    class NeverCalled(deepmod.PerplexityClient):
        def __init__(self):
            super().__init__(mock=False)

        async def chat(self, prompt):
            called.append(prompt)
            raise AssertionError("재조사가 일어나면 안 된다")

    monkeypatch.setattr(deepmod, "PerplexityClient", NeverCalled)
    game = {"game_id": 994, "home": "H", "away": "A",
            "starts_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()}
    await redis_client.set(f"research:{game['game_id']}", _json.dumps({
        "at": datetime.now(UTC).isoformat(),
        "data": {"home_recent_form": {"form": None, "note": LEAKED_NOTE},
                 "away_recent_form": {}, "absences": [], "expert_picks": []},
    }, ensure_ascii=False))
    data, status = await deepmod.get_game_research(redis_client, game, "mlb")
    assert data is None and status == "invalid"
    assert called == []


# ---------------------------------------------------------------- 문장 단위 필터 (오탐 방지)

MIXED_BULLPEN = (
    "전용 불펜 사용량 트래커에 따르면 Reds 불펜은 최근 7일 기준 약 24.2이닝을 소화한 것으로 집계된다. "
    "다만 '지난 3일'만 분리해 재집계하는 것은 현재 데이터만으로 불가능해 수치를 제시할 수는 없음."
)


def test_mixed_sentence_keeps_real_numbers():
    """[1] 오탐 방지: 실수치 문장 + '못 찾았다' 문장이 섞이면 앞만 남긴다."""
    from app.research.validate import clean_text

    out = clean_text(MIXED_BULLPEN, sentencewise=True)
    assert out and "24.2이닝" in out
    assert "불가능" not in out


def test_all_prose_value_is_fully_dropped():
    """[1] 전부 미확보 진술이면 문장 필터를 거쳐도 남는 게 없다."""
    from app.research.validate import clean_text

    prose = ("최신 데이터는 제공된 자료에 포함되어 있지 않습니다. "
             "좌·우완 스플릿을 정확히 추적하기 어렵습니다. "
             "따라서 '불명'으로 처리하는 것이 합리적입니다.")
    assert clean_text(prose, sentencewise=True) is None


def test_window_asserting_field_is_all_or_nothing():
    """[1] '최근 5경기'를 단언하는 last5는 문장 필터를 쓰지 않는다.

    시즌 수치만 남겨 두면 '선발 최근' 자리에 시즌 성적이 표기되는 새 오표기가 생긴다.
    """
    from app.research.validate import sanitize_research

    payload = {
        "home_pitcher": {
            "name": "Jose Urena", "era_season": 2.80,
            "last5": ("Ureña는 시즌 성적이 8-9, ERA 2.80, WHIP 1.24, 112.2이닝이다. "
                      "다만 최근 5~7경기별 게임로그는 이 턴에서 접근이 불가능하다."),
        },
        "home_recent_form": {"form": "WLWLW"}, "absences": [], "expert_picks": [],
    }
    clean, _ = sanitize_research(payload, "mlb")
    assert "last5" not in clean["home_pitcher"]
    assert clean["home_pitcher"]["era_season"] == 2.80   # 수치 필드는 유지


def test_normal_analysis_with_difficult_is_not_dropped():
    """[1] 오탐 방지: '공략하기 어렵다' 같은 정상 평가는 미확보 진술이 아니다."""
    from app.research.validate import is_unavailable_prose

    assert not is_unavailable_prose("Rasmussen의 구위는 상대 타선이 공략하기 어렵다는 평가가 많다")
    assert not is_unavailable_prose("Wrigley Field는 바람 탓에 타구 판단이 어렵다")
    # 반면 '<동작>하기 어렵' 형태의 미확보 진술은 잡는다
    assert is_unavailable_prose("구체적으로 숫자를 들어 설명하기 어렵다")
    assert is_unavailable_prose("최근 3일 불펜 피로도를 수치로 비교하기 어려움")


# ---------------------------------------------------------------- [C] 속보 매칭·문장 완결성

def test_news_does_not_leak_across_teams_sharing_a_token():
    """[C] 회귀: 'sox' 공유 토큰 때문에 레드삭스 속보가 화이트삭스 경기에 붙었다."""
    from app.pipeline import _team_news_lines

    news = ("확정 라인업: Boston Red Sox — Devers 3번\n"
            "라인 이동: TEX @ CWS - White Sox ML -110 to -118")
    ws = _team_news_lines(news, "Chicago White Sox", "Texas Rangers")
    assert len(ws) == 1 and "White Sox ML" in ws[0]
    assert not any("Boston" in ln for ln in ws)

    rs = _team_news_lines(news, "Boston Red Sox", "Miami Marlins")
    assert len(rs) == 1 and "Boston Red Sox" in rs[0]


def test_news_matches_korean_and_full_name():
    from app.pipeline import _team_news_lines

    news = "시카고 화이트삭스 선발 교체\nLos Angeles Dodgers 불펜 소모"
    assert len(_team_news_lines(news, "Chicago White Sox", "Texas Rangers")) == 1
    assert len(_team_news_lines(news, "Los Angeles Dodgers", "Chicago Cubs")) == 1


def test_clip_sentences_drops_incomplete_tail():
    """[C] 회귀: '최근 구간에서도 경 / 원정 ?'처럼 단어 중간에서 끊긴 출력 금지."""
    from app.pipeline import clip_sentences

    s = ("Kelly는 시즌 8승 11패, ERA 5.37이다. 최근 5경기 중 3경기에서 5이닝을 못 채웠다. "
         "불펜이 일찍 가동돼 후반 실점 위험이 커진다.")
    out = clip_sentences(s, 45)
    assert out.endswith("다.") and "채웠" not in out      # 완결 문장까지만
    assert clip_sentences("완결 문장이 없는 아주 긴 한 덩어리 텍스트입니다", 10) == ""
    assert clip_sentences("짧은 문장.", 100) == "짧은 문장."
    assert clip_sentences(None, 50) == ""


def test_truncated_pitcher_line_is_omitted():
    """[C] 잘린 문장만 남으면 '선발 최근' 줄 자체를 내지 않는다."""
    from app.pipeline import render_game_section

    jg = _mlb_jg(research={
        "home_recent_form": {"form": "WLWLL"},
        "home_pitcher": {"name": "Framber Valdez",
                         "last5": "매우 길게 이어지는 완결되지 않은 서술이 계속 이어지고 또 이어지며"},
        "absences": ["Riley Greene 결장"],
    })
    out = render_game_section(jg)
    assert "선발 최근:" not in out


# --- [3] 조건부 강제 재조사 (2026-08-25) ---

def test_needs_refresh_on_lineup_confirmed():
    """라인업이 방금 확정되면 6시간 캐시라도 다시 조사한다."""
    from app.research.deep import needs_refresh

    assert needs_refresh({"lineup_just_confirmed": True}) == "라인업 확정"


def test_needs_refresh_on_starter_change():
    from app.research.deep import needs_refresh

    assert needs_refresh({"starter_changed": True}) == "선발 변경"


def test_needs_refresh_none_for_ordinary_game():
    """평범한 경기는 재조사하지 않는다 — 6시간 내 두 번 조사는 콜 낭비다."""
    from app.research.deep import needs_refresh

    assert needs_refresh({"home": "A", "away": "B"}) is None


# ---------------------------------------------------------------- [§8-7] 신규 맥락 필드

_NEW_CONTEXT = ("motivation", "schedule_load", "umpire", "line_move_reason")


def test_new_context_fields_survive_sanitize():
    """동기·일정부담·주심·라인무브 사유가 정제를 통과해야 판정이 볼 수 있다.

    이 넷은 λ 계수로 쓰지 않는다(측정된 계수가 없다 — 임의 튜닝 금지).
    대신 judge 페이로드로 들어가 `p_claude`를 움직인다. 정제에서 떨어지면
    수집만 하고 아무것도 못 움직이는 상태가 된다.
    """
    data = {
        "motivation": "홈은 와일드카드 1경기 차 추격 중이고 원정은 이미 탈락이 확정됐다.",
        "schedule_load": "원정은 3연전 마지막 경기이며 직전 경기가 연장 12회로 끝났다.",
        "umpire": "주심 Angel Hernandez는 존이 넓은 편으로 삼진율이 리그 평균보다 높다.",
        "line_move_reason": "홈 선발이 경기 2시간 전 교체되며 배당이 1.70에서 1.92로 밀렸다.",
    }
    out, dropped = sanitize_research(data, "mlb")
    for key in _NEW_CONTEXT:
        assert key in out, f"{key}가 정제에서 사라졌다 (dropped={dropped})"


def test_new_context_fields_drop_unavailable_prose():
    """'못 찾았다'는 산문은 걷어낸다 — 200 OK 산문 사고의 방어선이다."""
    data = {k: "해당 정보를 찾을 수 없습니다." for k in _NEW_CONTEXT}
    out, dropped = sanitize_research(data, "mlb")
    for key in _NEW_CONTEXT:
        assert key not in out
        assert key in dropped


def test_new_context_fields_keep_qualitative_only():
    """수치가 없어도 남긴다 — 정성 정보라도 판정에는 가치가 있다.

    (구간을 단언하는 필드가 아니므로 전량 폐기 대상이 아니다 — CLAUDE.md 정책 분기)
    """
    out, _ = sanitize_research(
        {"motivation": "원정은 이미 포스트시즌 진출이 확정돼 주전을 아낄 가능성이 있다."}, "mlb")
    assert "motivation" in out


def test_new_context_fields_partial_sentence_filter():
    """한 필드 안에서 미확보 문장만 빠지고 실제 정보는 살아남는다."""
    out, _ = sanitize_research({
        "schedule_load": "원정은 4연전 마지막이며 이동 없이 같은 구장이다. "
                         "직전 경기 종료 시각은 확인할 수 없습니다."}, "mlb")
    assert "schedule_load" in out
    assert "4연전" in out["schedule_load"]
    assert "확인할 수 없" not in out["schedule_load"]


def test_fill_stats_track_new_fields():
    """채움률 감시에 신규 필드가 들어가야 프롬프트 과잉 금지문을 탐지할 수 있다."""
    from app.research.deep import _filled_fields

    empty = _filled_fields({})
    for key in _NEW_CONTEXT:
        assert key in empty and empty[key] is False
    filled = _filled_fields({"motivation": "순위 경쟁 중"})
    assert filled["motivation"] is True


def test_new_fields_present_in_both_schemas():
    """MLB·축구 프롬프트 스키마 양쪽에 들어가야 한다 — 한쪽만 넣으면 조용히 반쪽이다."""
    from app.research.deep import _SCHEMA_MLB, _SCHEMA_SOCCER

    for key in ("motivation", "schedule_load", "line_move_reason"):
        assert key in _SCHEMA_MLB, f"MLB 스키마에 {key} 없음"
        assert key in _SCHEMA_SOCCER, f"축구 스키마에 {key} 없음"
    # 주심 스트라이크존은 야구 고유 개념이다 (종목별 용어 분리 규칙)
    assert "umpire" in _SCHEMA_MLB and "umpire" not in _SCHEMA_SOCCER


# ---------------------------------------------------------------- [§8-14] KBO·NPB

def test_unavailable_prose_with_digits_is_dropped():
    """숫자가 섞인 미확보 산문도 걸러야 한다.

    실사고(2026-08-26 KBO 첫 실호출): Perplexity가
      "…세부 로그에 현재 바로 접근이 되지 않아, 구체적인 최근 5경기 ERA·피OPS·
       평균 소화 이닝을 숫자로 정리하기 어렵다"
    를 보냈는데, 문장에 숫자([13]·5경기)가 있어 **숫자 요구 조건을 통과**했고
    '접근이 되지 않'·'정리하기 어렵'이 키워드 목록에 없어 미확보 판정도 피했다.
    결과적으로 '못 찾았다'는 문장이 선발 지표(last5)로 판정에 들어갈 뻔했다.
    """
    text = ("KBO 공시 자료에서 8월 26일 잠실 NC전 선발로 예고된 임찬규는[13], "
            "시즌 전체 성적(ERA·WHIP, 최근 5경기 이닝·자책·투구수)까지 포함한 "
            "세부 로그에 현재 바로 접근이 되지 않아, 구체적인 최근 5경기 "
            "ERA·피OPS·평균 소화 이닝을 숫자로 정리하기 어렵다")
    assert clean_text(text, sentencewise=True) is None


def test_new_markers_do_not_eat_real_numbers():
    """⚠️ 반대 위험 측정 — 새 키워드가 정상 수치 문장을 폐기하면 안 된다.

    (규율: 새 필터·가드를 추가할 때는 반대 위험을 함께 측정한다)
    """
    good = ("임찬규는 최근 5경기에서 평균자책점 3.42, 이닝당 출루허용 1.21을 기록했고 "
            "평균 5.2이닝을 소화했다. 직전 등판은 8월 20일 두산전 6이닝 2실점이었다.")
    out = clean_text(good, sentencewise=True)
    assert out is not None
    assert "3.42" in out and "6이닝 2실점" in out


def test_mixed_sentence_keeps_only_the_real_one():
    """한 필드 안에서 실수치 문장은 살고 미확보 문장만 빠진다."""
    mixed = ("구창모는 최근 3경기 평균자책점 2.70을 기록했다. "
             "다만 투구수 세부 로그는 접근이 되지 않아 확인하지 못했다.")
    out = clean_text(mixed, sentencewise=True)
    assert out is not None
    assert "2.70" in out and "접근이 되지 않" not in out


def test_kbo_npb_have_research_targets_and_labels():
    """[§8-14] KBO·NPB 조사 목표·리그 라벨이 있어야 한다.

    없으면 `TARGETS[sport]`가 KeyError로 죽고(실제로 죽었다), 라벨이 없으면
    "football(soccer)"로 폴백해 야구 경기를 축구로 조사한다.
    """
    from app.research.deep import _SCHEMA_MLB, _SPORT_LABEL, TARGETS

    for sport in ("kbo", "npb"):
        assert sport in TARGETS, f"{sport} 조사 목표 없음"
        assert sport in _SPORT_LABEL, f"{sport} 리그 라벨 없음"
    # MLB 기사로 새지 않게 리그를 명시하고 현지 소스를 지정한다
    assert "Korea" in _SPORT_LABEL["kbo"] and "한국프로야구" in _SPORT_LABEL["kbo"]
    assert "Nippon" in _SPORT_LABEL["npb"] and "日本プロ野球" in _SPORT_LABEL["npb"]
    assert "koreabaseball.com" in TARGETS["kbo"]
    assert "npb.jp" in TARGETS["npb"]
    assert "do NOT return MLB" in TARGETS["kbo"]
    assert "do NOT return MLB" in TARGETS["npb"]
    # KBO/NPB는 야구 스키마를 쓴다 (축구 스키마면 선발투수 필드가 통째로 없다)
    assert "home_pitcher" in _SCHEMA_MLB


def test_kbo_targets_avoid_unavailable_metrics():
    """KBO·NPB에 SIERA·xFIP를 요구하지 않는다.

    공개 매체가 거의 제공하지 않는 지표를 요구하면 Perplexity는 200 OK로
    '왜 못 찾았는지'를 산문으로 채워 보내고, 그것이 전량 폐기돼 재료가 0이 된다.
    """
    from app.research.deep import TARGETS

    for sport in ("kbo", "npb"):
        assert "SIERA" not in TARGETS[sport]
        assert "xFIP" not in TARGETS[sport]
        assert "ERA" in TARGETS[sport]          # 공개되는 지표는 요구한다


# ---------------------------------------------------------------- [§8-17] 한국어/일본어 폼 표기

def test_form_accepts_korean_and_japanese_notation():
    """[§8-17] 딥서치는 **한국어로 답한다** — 필터가 영문 W/L만 받으면 통째로 버려진다.

    실사고(2026-08-26 KBO): '승승패승패'가 `clean_form`에서 None이 돼
    home/away_recent_form.form이 매번 폐기됐다. "못 가져왔다"가 아니라
    "가져왔는데 버렸다"였다.
    """
    from app.research.validate import clean_form

    assert clean_form("승승패승패") == "WWLWL"
    assert clean_form("승-패-승-승-패") == "WLWWL"
    assert clean_form("勝勝敗分勝") == "WWLDW"
    assert clean_form("WWLWL") == "WWLWL"           # 기존 동작 유지
    assert clean_form("W W L W L") == "WWLWL"


def test_form_rejects_tally_without_order():
    """⚠️ 반대 위험 — '3승 2패'는 **집계**다. 순서 정보가 없으므로 폼이 아니다.

    이걸 받으면 'WWLL' 같은 가짜 시퀀스가 만들어져 최근 폼 판정이 오염된다.
    """
    from app.research.validate import clean_form

    assert clean_form("5경기 3승 2패") is None
    assert clean_form("최근 3승 2패") is None
    assert clean_form("10경기 6승 4패") is None


def test_form_still_rejects_unavailable_prose():
    from app.research.validate import clean_form

    assert clean_form("최근 폼 정보를 찾을 수 없습니다") is None
    assert clean_form("") is None and clean_form(None) is None


def test_kbo_prompt_stays_lean():
    """[§8-17] 프롬프트 과잉은 채움률을 무너뜨린다 — 길이를 MLB 수준으로 묶는다.

    실사고(2026-08-26): KBO 조사 목표를 962→1442자로 늘리고 "한 소스에 없으면
    다른 곳을 확인하라"를 넣었더니 **채움률이 6/10 → 0/10으로 붕괴**했다.
    응답이 전부 "이 턴에서 조회가 불가"라는 변명 산문이 됐다.
    (CLAUDE.md 튜닝 기준: 채움률 급락 = 프롬프트 금지문 과잉 → 롤백)
    """
    from app.research.deep import TARGETS

    mlb_len = len(TARGETS["mlb"])
    for sport in ("kbo", "npb"):
        assert len(TARGETS[sport]) <= mlb_len * 1.15, (
            f"{sport} 조사 목표가 MLB보다 15% 넘게 길다 — 채움률 붕괴 위험")


def test_kbo_prompt_keeps_measured_wins():
    """롤백하되 **효과가 확인된 것**은 남긴다."""
    from app.research.deep import TARGETS

    kbo = TARGETS["kbo"]
    assert "승/패/무" in kbo                    # 필터와 표기 계약을 맞춘다
    assert "SEQUENCE" in kbo and "not a tally" in kbo
    assert "1군 등록·말소" in kbo                # KBO는 말소로 결장을 알린다
    assert "네이버 스포츠" in kbo                 # 포털이 가장 빠르다
    assert "do NOT return MLB" in kbo
    npb = TARGETS["npb"]
    assert "勝/敗/分" in npb and "出場選手登録・抹消" in npb
