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
        "research": {
            "home_recent_form": {"form": "WLWLL", "runs_avg": 3.9},
            "away_recent_form": {"form": "WWLWW", "runs_avg": 5.2},
            "home_pitcher": {"name": "Framber Valdez", "era_season": 4.35},
            "absences": ["Detroit Tigers의 Riley Greene 손목 부상 결장"],
        },
    }
    jg.update(over)
    return jg


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
        research={
            "home_recent_form": {"form": "WWWLL", "runs_avg": 4.4},
            "away_recent_form": {"form": "WWLWW", "runs_avg": 4.8},
            "home_pitcher": {"name": "Sandy Alcantara", "era_season": 3.46},
            "absences": ["Boston Red Sox의 Trevor Story 결장"],
        },
    )
    jg.update(over)
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
