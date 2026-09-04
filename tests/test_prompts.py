"""5단계 — 폼·매치업 프롬프트. 지시문 문구를 바꾸지 않았는지 지킨다."""
from app.engine.prompts import MATCHUP, TEAM_FORM, fill


def test_team_form_prompt_keeps_tag_dictionary_and_opponent_rank():
    assert "감독교체, 트레이드/이적, 주축부상, 주축복귀, 내부불화, 순위경쟁절박, 연패분위기, 더비/라이벌전" in TEAM_FORM
    assert "상대팀의 현재 순위·승률" in TEAM_FORM
    assert "시즌 전체 통념" in TEAM_FORM
    assert "{{TEAM_NAME}}" in TEAM_FORM
    assert "{{GAMES_JSON}}" in TEAM_FORM
    assert "{{NEWS_HEADLINES}}" in TEAM_FORM


def test_matchup_prompt_keeps_clip_and_news_cap():
    assert "p_home은 0.32~0.68 범위를 벗어나지 않는다" in MATCHUP
    assert "확률을 최대 ±3%p까지만 조정" in MATCHUP
    assert "실적 데이터가 가리키는 우세 방향을 뉴스만으로 뒤집을 수 없다" in MATCHUP
    assert "오늘 나온 9명이 기준이다" in MATCHUP
    # [E 2026-09-02] 자료1·2가 헤이쿠 평가서 → 원본 박스스코어 + 뉴스태그로 교체됐다.
    assert "{{BOXSCORE_JSON}}" in MATCHUP
    assert "{{NEWS_JSON}}" in MATCHUP
    assert "{{STARTERS_RECENT_JSON}}" in MATCHUP


def test_fill_replaces_placeholders_not_json_braces():
    """출력 JSON 예시의 중괄호를 format 필드로 오인하면 KeyError가 난다."""
    out = fill(TEAM_FORM, TEAM_NAME="한화", GAMES_JSON="[]", NEWS_HEADLINES="[]")
    assert "{{TEAM_NAME}}" not in out
    assert '"team": "한화"' in out
    assert '"타선": {"평가": "상|중|하"' in out
    out2 = fill(
        MATCHUP,
        HOME_FORM_JSON="{}",
        AWAY_FORM_JSON="{}",
        LINEUPS_JSON="{}",
        STARTERS_RECENT_JSON="{}",
        LINEUP_INTENT_JSON="{}",
    )
    assert '"p_home": 0.00' in out2
    assert "{{HOME_FORM_JSON}}" not in out2


def test_matchup_receives_lineup_intent_as_interpretation():
    """🔴 실측 2026-09-01: 라인업 의도가 카드에만 실리고 매치업 프롬프트에는
    없었다. 수집한 정보가 확률을 움직이지 않는 상태였다 — 파드리스전에서
    핵심 4명 이탈을 서술에 써놓고 승률은 그대로였던 것과 같은 모양이다.

    ⚠️ 넣되 **해석으로** 넣는다. lineup_intent 모듈 자신의 규율이
       "사실과 해석을 끝까지 분리한다 — 섞으면 3단이 추측을 사실로 읽는다"다.
    """
    assert "{{LINEUP_INTENT_JSON}}" in MATCHUP
    assert "사실이 아니라 해석이다" in MATCHUP
    assert '"해석:"으로 시작해 사실과 구분하라' in MATCHUP


def test_intent_is_capped_together_with_news_and_cannot_flip():
    """의도는 보조 신호다. 뉴스와 **합쳐서** ±3%p, 우세 방향 뒤집기 금지.

    새 임계값을 만들지 않았다 — 기존 뉴스 상한을 공유하도록 좁혔을 뿐이다.
    """
    assert "뉴스와 의도를 **합쳐서** ±3%p를" in MATCHUP
    assert "이 둘만으로 뒤집을 수 없다" in MATCHUP
    # 기존 뉴스 규칙은 그대로 살아 있다 (회귀)
    assert "확률을 최대 ±3%p까지만 조정" in MATCHUP


def test_intent_boryu_is_not_evidence():
    """'보류'는 "판단 못 함"이지 "중립"이 아니다 — 근거로 쓰면 안 된다."""
    assert "'보류'인 항목은 **근거로 쓰지 마라.**" in MATCHUP


def test_fill_replaces_intent_slot():
    out = fill(
        MATCHUP,
        HOME_FORM_JSON="{}", AWAY_FORM_JSON="{}", LINEUPS_JSON="{}",
        STARTERS_RECENT_JSON="{}", PREV_VERDICT_JSON="null",
        LINEUP_INTENT_JSON='{"home": {"요약": "주전 2명 휴식"}}',
    )
    assert "{{LINEUP_INTENT_JSON}}" not in out
    assert "주전 2명 휴식" in out


def test_interpreter_role_is_actually_usable():
    """🔴 기본값이 서로 모순이었다: interpreter_provider="groq" 인데 groq 은
    disabled_providers 기본값에 들어 있다. 그래서 의도 해석이 한 번도 돌지
    않았고, role_enabled 는 True 를 돌려줘 그 사실이 드러나지도 않았다.
    """
    from app.config import Settings
    from app.llm.provider import resolve_model, role_enabled

    s = Settings(_env_file=None)
    assert role_enabled("interpreter", s) is True
    assert s.is_disabled(s.interpreter_provider) is False, \
        "해석봇 프로바이더가 비활성 목록에 있다 — 영원히 안 돈다"


def test_interpreter_model_is_pinned_not_opus_fallback():
    """⚠️ 비우면 역할 폴백이 judge_model(=Opus)을 넣는다. 해석봇은 경기×양팀이라
    호출량이 가장 많은 역할이다 — 슬레이트당 20콜이 조용히 Opus가 된다."""
    from app.config import Settings
    from app.llm.provider import resolve_model

    s = Settings(_env_file=None)
    assert s.interpreter_model, "비어 있으면 Opus 폴백이다"
    assert resolve_model("interpreter", s) == s.interpreter_model
    assert resolve_model("interpreter", s) != s.judge_model


def test_season_line_is_sample_correction_only():
    """🔴 규율 개정 2026-09-01 — "시즌 ERA 금지"를 **선발투수 한 칸만** 푼다.

    실사고(NYY@LAA 1:7): 최근 등판 1경기(6이닝 3실점)를 "안정적"으로 읽고
    NYY 66% 추천. 그 투수의 시즌은 ERA 5.40·BB/9 5.4 였고 오늘 3.2이닝
    3볼넷 4실점으로 무너졌다. 시즌 데이터가 결과를 예측하고 있었는데
    판정이 볼 수 없게 되어 있었다.
    """
    assert "{{STARTER_SEASON_JSON}}" in MATCHUP
    assert "표본 보정 전용" in MATCHUP
    assert "이것으로\n  우세를 정하지 마라" in MATCHUP
    assert '"표본 보정:"으로 시작하라' in MATCHUP
    # 자료7은 여전히 **선발투수 전용** 이다 — 타선은 자료8로 분리돼 있다.
    assert "이 칸은 선발투수다. 타선 시즌은 8번 자료를 쓴다." in MATCHUP


def test_batting_season_is_first_class_evidence():
    """🔴 규율 개정 2026-09-02 — "타선·팀 시즌 지표 금지"를 **해제**한다.

    9/01 개정은 선발투수 한 칸만 풀고 타선은 닫아뒀다. 그런데 판정은 "오늘
    나온 9명이 기준"이라고 말하면서 그 9명이 어떤 타자인지는 볼 수 없었다 —
    타선 재료가 팀 3경기 총득점 하나뿐이었기 때문이다. 표본 3이고 상대
    선발에 좌우된다. 선발에서 겪은 실수를 타선에서 반복할 구조였다.

    선발과 달리 **표본 보정 전용이 아니라 정식 근거**다 (사용자 결정 2026-09-02).
    """
    assert "{{LINEUP_SEASON_JSON}}" in MATCHUP
    assert "자료8(타선 시즌)은 **정식 근거다.**" in MATCHUP
    assert "타선 평가의 주 근거로 쓴다" in MATCHUP
    assert '"타선 시즌:"으로 시작하라' in MATCHUP
    # 금지문이 실제로 사라졌는가
    assert "타선·팀 지표의 시즌 값은 여전히 쓰지 않는다" not in MATCHUP


def test_batting_season_does_not_override_the_starter():
    """타선은 9명이 나눠 갖고 선발은 혼자 던진다 — 반대를 가리키면 선발이 무겁다."""
    assert "선발 쪽을 무겁게 본다" in MATCHUP
    assert "`PA`가 작은 타자" in MATCHUP


def test_missing_batting_material_is_not_a_bad_lineup():
    """수집 실패를 '타선이 약하다'로 읽으면 없는 근거로 판정이 기운다."""
    assert "없는 쪽을 나쁘다고 보지 마라" in MATCHUP


def test_hard_limits_survive_the_revision():
    """개정이 완화하면 안 되는 것까지 건드리지 않았는가."""
    assert "0.32~0.68" in MATCHUP
    assert "±3%p" in MATCHUP
    assert "배당, 팀 명성, 시즌 승률, 사전 지식은 쓰지 않는다" in MATCHUP


def test_low_recent_sample_pulls_toward_half():
    """표본이 적으면 0.50 쪽으로 당긴다 — 적은 표본에 확신을 싣지 않는다."""
    assert "**2경기 이하**면 그 표본은 그 투수를 대표하지 않는다" in MATCHUP
    assert "표본이 적을수록 0.50 쪽으로 당긴다" in MATCHUP


def test_judge_reads_numbers_not_another_models_grades():
    """🔴 [E 2026-09-02] 판정이 다른 모델의 등급을 근거로 인용하고 있었다.

    실측 2026-09-02 (한신@야쿠르트 직전 판정 근거 3번):
      "자료2 원정팀 종합: 선발진 평가 '상'과 '흐름 상승'이 자료1 홈팀
       선발진 '중' 대비 우위를 뒷받침한다"
    헤이쿠가 박스스코어를 읽고 매긴 등급을 소나가 근거로 베낀 것이다.
    "수치는 있는 그대로 판단하게 하고 분석만 AI가 한다" (사용자 지시).
    """
    # 등급을 만드는 평가서 자체가 입력에서 사라졌는가
    assert "{{HOME_FORM_JSON}}" not in MATCHUP
    assert "{{AWAY_FORM_JSON}}" not in MATCHUP
    assert "경기력 평가서" not in MATCHUP
    # 원본 숫자가 그 자리에 들어왔는가
    assert "원본 박스스코어" in MATCHUP
    assert "starter_pitches" in MATCHUP and "bullpen_count" in MATCHUP
    # 등급 인용 금지가 명시됐는가
    assert "다른 모델이 매긴 등급" in MATCHUP
    assert "어느 숫자에서 그 결론이 나왔는지를 적어라" in MATCHUP


def test_batting_order_carries_slot_and_position():
    """1번과 8번은 타석 수가 다르다 — 순서가 곧 정보다."""
    assert "타순 번호·이름·포지션" in MATCHUP
    assert "순서가 곧 정보다" in MATCHUP


def test_bullpen_is_an_input():
    """선발이 일찍 내려가면 불펜에서 갈린다."""
    assert "{{BULLPEN_JSON}}" in MATCHUP
    # 🔴 [C1 2026-09-04] **계약이 바뀌었다.**
    #   전: 자료9 = 시즌 팀 불펜 ERA + 컨디션. "ERA와 별개 항목" 을 잠갔다.
    #   후: 자료9 = **최근 3경기 실점 + 최근 3일 가용성.** 시즌 값은 제거.
    #   사유: 대원칙(최근 폼 전용, 2026-09-04 사용자 확정) — 시즌 누적은
    #        판정 입력이 아니다.
    assert "최근 폼만" in MATCHUP
    assert "최근3경기" in MATCHUP and "가용성" in MATCHUP
    assert "단독 근거로 쓰지 마라" in MATCHUP, "얇은 표본 경고가 빠졌다"
    assert "상대 타자 수를 소모 대리값" in MATCHUP, "대리값임을 숨기면 안 된다"


def test_three_game_sample_rules_survive():
    """자료1이 원본으로 바뀌어도 표본 3의 한계는 그대로 경고해야 한다."""
    assert "표본 3이다" in MATCHUP
    assert "opponent_rank" in MATCHUP
    assert "승패(W-L)는 쓰지 않는다" in MATCHUP
