"""[v1.1 6단계] 트리거형 딥서치 — 발동 조건과 상한.

최고위험 단계다(비용·외부 의존). 그래서 **상한을 프롬프트가 아니라 코드가
강제하는지**가 가장 중요한 테스트다 — 모델이 규칙을 어겨도 값이 새어
나가지 않아야 한다.
"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.config import Settings
from app.engine.deepsearch import (
    ADJUST_CAP_PP, SEARCH_LANG, T1_BOUNDARY, T2_MARKET, T3_ASKED, T4_STARTER,
    T5_LINEUP, apply_findings, clamp_adjustment, daily_cap, lineup_anomaly,
    triggers,
)

S = Settings(_env_file=None)


def _jg(**kw):
    base = {"sport": "kbo", "p_claude": 0.50, "home": "H", "away": "A",
            "matchup": {"p_home": 0.50, "우세": "home"}}
    m = kw.pop("matchup", None)
    base.update(kw)
    if m:
        base["matchup"] = {**base["matchup"], **m}
    return base


# ---------------------------------------------------------------- 트리거 5종

def test_t1_boundary_only_near_threshold():
    """게이트 임계 ±3%p 안이면 경계 경기다. 멀면 발동하지 않는다."""
    assert T1_BOUNDARY in triggers(_jg(p_claude=0.58), S)      # 임계 정확히
    assert T1_BOUNDARY in triggers(_jg(p_claude=0.60), S)      # +2%p
    assert T1_BOUNDARY not in triggers(_jg(p_claude=0.66), S)  # +8%p — 여유


def test_t1_uses_away_premium():
    """원정은 임계가 63%다 — 홈 기준으로 재면 엉뚱한 경기가 걸린다."""
    jg = _jg(p_claude=0.36, matchup={"우세": "away"})   # 원정 64%
    assert T1_BOUNDARY in triggers(jg, S)


def test_t2_fires_on_edge_or_divergence():
    assert T2_MARKET in triggers(_jg(edge_status="candidate"), S)
    assert T2_MARKET in triggers(_jg(market_divergence=True), S)
    assert T2_MARKET not in triggers(_jg(edge_status="none"), S)


def test_t3_fires_when_judgement_asked():
    assert T3_ASKED in triggers(_jg(matchup={"추가확인": ["선발 등판 간격"]}), S)
    assert T3_ASKED not in triggers(_jg(matchup={"추가확인": []}), S)
    assert T3_ASKED not in triggers(_jg(matchup={"추가확인": ["  "]}), S)


def test_t4_fires_on_starter_change():
    jg = _jg(matchup={"직전대비": {"변경입력": ["홈 선발 안우진으로 변경"]}})
    assert T4_STARTER in triggers(jg, S)
    jg2 = _jg(matchup={"직전대비": {"변경입력": ["타순 3번 교체"]}})
    assert T4_STARTER not in triggers(jg2, S)


def test_t5_fires_on_two_starter_swaps():
    """🔴 숫자가 경계에 안 걸려도 라인업 이상 자체가 조사 사유다."""
    prev = {"lineup_home": "가-나-다-라-마-바-사-아-자"}
    jg = _jg(p_claude=0.66, lineup_home="가-나-다-라-마-바-사-차-카")  # 2명 교체
    assert T5_LINEUP in triggers(jg, S, prev_lineup=prev)
    assert lineup_anomaly(jg, prev) is True


def test_t5_ignores_single_swap():
    prev = {"lineup_home": "가-나-다-라-마-바-사-아-자"}
    jg = _jg(lineup_home="가-나-다-라-마-바-사-아-차")   # 1명만
    assert lineup_anomaly(jg, prev) is False


def test_t5_fires_when_form_key_player_is_absent():
    """폼 평가서가 근거로 삼은 선수가 빠지면 그 판정의 토대가 무너진다."""
    jg = _jg(p_claude=0.66,
             lineup_home="김핵심-나-다-라-마-바-사-아-자",
             research={"home_form": {"종합": "김핵심이 타선을 이끌고 있다"}},
             home_lineup={"결장": ["김핵심"]})
    assert lineup_anomaly(jg) is True


def test_every_game_investigated_but_real_triggers_still_visible():
    """🔴 [DS-3 2026-09-10 사용자 지시] **계약이 바뀌었다.**

    종전 계약은 "편안한 확률·이상 없음 → 발동하지 않는다(상시 검색 금지)"였다.
    그 금지는 유료 web_search 시절의 비용 방어였는데, 딥서치가 무료 사슬 전용이
    된 뒤로 근거가 약해졌고 사용자가 전수 조사를 지시했다:
        "트리거 걸린 경기만 하지 말고 전부 다 해라."

    이제 조용한 경기도 T0_전수 하나로 조사 대상이 된다. 다만 **진짜 트리거는
    앞에 그대로** 남아야 한다 — 발동 원인 추적(어떤 경기가 왜 조사됐나)이
    죽으면 실측이 불가능해진다.
    """
    from app.engine.deepsearch import T0_ALL

    quiet = triggers(_jg(p_claude=0.66), S)
    assert quiet == [T0_ALL], "조용한 경기는 전수 트리거 하나만 붙어야 한다"

    loud = triggers(_jg(p_claude=0.58), S)      # T1 경계에 걸리는 경기
    assert loud[0] == T1_BOUNDARY, "진짜 트리거가 앞에 와야 원인 추적이 산다"
    assert loud[-1] == T0_ALL


# ---------------------------------------------------------------- 상한

def test_daily_cap_is_share_of_slate():
    assert daily_cap(15, S) == 4          # 30%
    assert daily_cap(0, S) == 0


def test_daily_cap_allows_at_least_one():
    """3경기 슬레이트에서 0.9 → 0이면 경계 경기가 있어도 손을 놓게 된다."""
    assert daily_cap(3, S) == 1
    assert daily_cap(1, S) == 1


def test_adjustment_is_capped_at_10pp():
    """🔴 [2026-09-09 사용자 지시] 조정 상한을 ±4%p → ±10%p 로 올렸다.
    괴리 정보가 판정을 실제로 움직이게 하려는 것. 상한은 프롬프트가 아니라 코드가 강제."""
    assert ADJUST_CAP_PP == 10.0
    p, note = clamp_adjustment(0.60, 0.75, "home")
    assert p == pytest.approx(0.70)          # +10%p 상한
    assert f"±{ADJUST_CAP_PP:g}%p" in note
    p2, _ = clamp_adjustment(0.60, 0.40, "home")
    assert p2 == pytest.approx(0.50)         # -10%p 상한 (플립가드가 0.50 에서 멈춤)


def test_delta_pp_moves_home_probability():
    """🔴 [MKT-8] 요약기가 절대 p_home 대신 **부호 있는 %p 증감(delta_pp)** 을 낸다.
    세이부 사고: 절대/증분 모호성으로 0.03 이 극단 원정으로 오해돼 반대로 클램프됐다."""
    jg = _jg(p_claude=0.50, matchup={"우세": "home"})
    apply_findings(jg, {"조정": {"delta_pp": 8}, "요약": "s"})
    assert jg["p_claude"] == pytest.approx(0.58)


def test_delta_pp_is_capped_and_falls_back_to_p_home():
    # 상한: +25%p 요청도 +10%p 로 절사
    jg = _jg(p_claude=0.50, matchup={"우세": "home"})
    apply_findings(jg, {"조정": {"delta_pp": 25}, "요약": "s"})
    assert jg["p_claude"] == pytest.approx(0.60)
    # 하위호환: delta_pp 없으면 옛 절대 p_home 경로 그대로
    jg2 = _jg(p_claude=0.60, matchup={"우세": "home"})
    apply_findings(jg2, {"조정": {"p_home": 0.66}, "요약": "s"})
    assert jg2["p_claude"] == pytest.approx(0.66)


def test_adjustment_within_cap_passes_through():
    p, note = clamp_adjustment(0.60, 0.62, "home")
    assert p == pytest.approx(0.62) and note is None


def test_direction_cannot_be_flipped_by_search_alone():
    p, note = clamp_adjustment(0.52, 0.48, "home")
    assert p == 0.5 and "뒤집기 금지" in note
    p2, note2 = clamp_adjustment(0.48, 0.52, "away")
    assert p2 == 0.5 and "뒤집기 금지" in note2


def test_single_article_halves_the_adjustment():
    """소스 규칙 ②를 코드로도 집행한다 — 프롬프트만으로는 지켜졌는지 모른다."""
    jg = _jg(p_claude=0.60)
    out = apply_findings(jg, {"조정": {"p_home": 0.64, "단일기사여부": True},
                              "요약": "s"})
    assert jg["p_claude"] == pytest.approx(0.62), "단일 기사인데 전액 반영됐다"
    assert out["moved"] == pytest.approx(2.0)


def test_no_adjustment_leaves_probability_alone():
    jg = _jg(p_claude=0.60)
    apply_findings(jg, {"조정": {}, "요약": "새 사실 없음"})
    assert jg["p_claude"] == 0.60


def test_card_line_is_added():
    jg = _jg(p_claude=0.60)
    apply_findings(jg, {"조정": {"p_home": 0.61}, "요약": "선발 복귀 확인"})
    assert any("🔍 추가 조사 반영" in c for c in jg["breaking_changes"])


# ---------------------------------------------------------------- 언어·규칙

def test_search_language_per_sport():
    """영어로만 찾으면 KBO 구단 공지·NPB 스포츠지가 통째로 빠진다."""
    assert SEARCH_LANG["kbo"] == "한국어"
    assert SEARCH_LANG["npb"] == "일본어"
    assert SEARCH_LANG["mlb"] == SEARCH_LANG["soccer"] == "영어"


def test_prompt_carries_source_rules_and_status():
    from app.engine.deepsearch import PROMPT

    assert "뉴스만으로 조사를 끝내지 않는다" in PROMPT
    assert "단일 기사 하나뿐이면 조정 폭을 절반으로" in PROMPT
    assert "루머·익명 소스·커뮤니티발" in PROMPT
    assert "크롤 정형 데이터보다 낮은 신뢰 등급" in PROMPT
    assert "±10%p" in PROMPT


def test_search_count_is_capped_by_api_not_just_prompt():
    """유료 검색 자체가 없어졌다 — 상한이 아니라 **0** 이다.

    종전에는 `max_uses` 로 API가 경기당 검색 횟수를 강제했다. 2026-09-06
    사용자 지시로 Anthropic 을 최종 판정에만 쓰기로 하면서 유료 web_search
    폴백을 삭제했다. 상한을 재는 것보다 도구가 없는 것이 강한 보장이다.
    """
    src = Path("app/engine/deepsearch.py").read_text(encoding="utf-8")
    assert "web_search_20260318" not in src
    assert "max_uses" not in src


def test_credit_guard_applies_to_this_path():
    """유료 가드 대신 **유료 경로 부재**가 이 자리를 지킨다.

    가드는 유료 호출이 있을 때만 뜻이 있다. 딥서치가 무료 사슬 전용이 된
    지금 가드를 남겨 두면, 최종 판정이 Anthropic 잔액을 소진한 순간 조사까지
    함께 멈춘다 — 실제로 그 형태로 종목이 통째로 멈춘 적이 있다
    (2026-09-04 16:37 NPB 판정 0건 · 2026-09-06 아침 MLB 0/85).
    """
    src = Path("app/engine/deepsearch.py").read_text(encoding="utf-8")
    assert "anthropic.AsyncAnthropic" not in src
    assert "trip_credit" not in src
    assert "abort_if_credit_gone" not in src


def test_prompt_output_asks_for_additional_checks():
    from app.engine.prompts import MATCHUP

    assert '"추가확인"' in MATCHUP
    assert "외부에서 확인 가능한 정보라면" in MATCHUP


async def test_no_external_call_in_mock_mode():
    """🔴 목 모드에서는 외부를 때리지 않는다.

    실측 2026-08-31: 배선 직후 테스트 스위트가 api.anthropic.com 을 호출해
    35초 → 419초가 됐다. 판정 경로에 새 외부 호출을 붙일 때는 목 분기를
    **같은 커밋에서** 넣어야 한다 (P5-2 차단이 잡아줬지만 그 전에 넣었어야 한다).
    """
    from app.engine.deepsearch import investigate

    data, used, src = await investigate({"sport": "kbo", "home": "H", "away": "A",
                                         "matchup": {"p_home": 0.6}}, ["T1"])
    assert (data, used) == (None, 0)
    assert src == "rss", "무과금 전환 후 기본 경로는 RSS 다"


async def test_investigation_is_off_by_default_but_triggers_still_run():
    """A안: 조사 호출은 꺼두고 트리거 판별만 실전에 태운다.

    어떤 경기가 조사 대상이 되는지 먼저 관찰한다 — 작동하지 않는 호출에
    경기당 90초를 태우지 않는다.
    """
    from app.engine.deepsearch import run_for_slate

    assert Settings(_env_file=None).deepsearch_investigate is False
    jg = _jg(p_claude=0.58)                      # T1 경계 경기
    out = await run_for_slate([jg], None, "2026-09-01", settings=S)
    assert out["disabled"] is True
    assert len(out["candidates"]) == 1, "트리거 판별은 계속 돌아야 한다"
    assert out["investigated"] == 0, "조사 호출이 나갔다"
    assert "deepsearch" not in jg, "판정이 건드려졌다"


def test_flag_reads_deepsearch_enabled_env():
    assert Settings(_env_file=None,
                    DEEPSEARCH_ENABLED=True).deepsearch_investigate is True


def test_search_count_comes_from_usage_not_block_count():
    """🔴 server_tool_use 블록 수를 세면 틀린다.

    실측 2026-08-31: 블록 15개를 검색 15회로 읽고 "max_uses 초과"라고 잘못
    보고했다. API는 상한을 정확히 지키고 있었다(max_uses=2 → 실제 2회).
    정확한 값은 usage.server_tool_use.web_search_requests 다.
    """
    src = Path("app/engine/deepsearch.py").read_text(encoding="utf-8")
    # 유료 검색이 사라져 셀 블록도 없다. 반환값의 검색 수는 항상 0 이다.
    assert "web_search_requests" not in src
    assert 'getattr(b, "type", "") == "server_tool_use")' not in src
    assert "return data, 0, source" in src


def test_prompt_states_search_budget_and_forces_conclusion():
    """🔴 실측 2026-09-01: 모델이 검색 5회를 다 쓰고도 결론을 못 냈다.

    예산을 알려주지 않으면 탐색에 다 쓴다. 단순 질문 1개는 2회로 끝났다 —
    프롬프트가 예산에 비해 과했던 것이지 도구 문제가 아니었다.
    """
    from app.engine.deepsearch import PROMPT

    assert "{budget}" in PROMPT
    assert "최우선" in PROMPT
    assert "반드시 결론을 낸다" in PROMPT
    assert "예산을 다 쓰고 결론을 못 내면 실패" in PROMPT


def test_parse_failure_logs_evidence_not_just_the_word_failure(caplog):
    """🔴 실측 2026-09-01: 4/4 파싱 실패인데 로그가 "실패"만 남겼다.

    원인을 특정할 수 없었고, 그 사이 Anthropic 잔액이 소진돼 재현 호출조차
    못 했다. 실패 로그는 **다음 사람이 원인을 짚을 수 있어야** 한다 —
    `stop_reason`("max_tokens"면 절단, "end_turn"이면 형식 이탈)·출력
    토큰·본문 앞부분이 남아야 한다.
    """
    src = Path("app/engine/deepsearch.py").read_text(encoding="utf-8")
    head = src[src.index("JSON 파싱 실패"):src.index("JSON 파싱 실패") + 600]
    assert "len(body)" in head, "몇 자가 왔는지 없으면 절단을 못 본다"
    assert "%.300s" in head, "본문을 남기지 않으면 형식 이탈을 못 본다"
    # 무료 사슬 쪽 진단은 `_complete_free` 가 남긴다 — provider·model·앞부분.
    tf = Path("app/engine/team_form.py").read_text(encoding="utf-8")
    assert "응답이 JSON 이 아니다" in tf and "앞=%r" in tf


def test_output_budget_is_configurable_and_larger_than_matchup():
    """🔴 실측 2026-09-01: max_tokens=2000 → stop="max_tokens", 출력 5804토큰,
    JSON이 743자에서 절단. 조사 4/4가 이것 때문에 실패했다.

    web_search 는 한 번의 호출 안에서 검색-읽기를 여러 턴 돌고 그 중간 서술이
    전부 출력 예산을 먹는다. **판정(4000)보다 커야 한다** — 조사가 더 많이
    쓰는데 절반만 준 것이 결함이었다. 하드코딩도 함께 걷어낸다.
    """
    s = Settings(_env_file=None)
    # 🔴 [CHN-1 2026-09-15] 종전 불변식은 "딥서치 > 매치업"이었고 하한이 5,804
    #    이었다 — 둘 다 **유료 Claude/gemini-3.x 시절 실측**이다(12000·16000).
    #    이제 무료 사슬이다: groq 무료 티어가 분당 8,000토큰이라 1콜이 그 안에
    #    들어야 하고, 주전 gemini-3.5-flash-lite 는 사고 토큰을 안 먹는다
    #    (실측 2026-09-15: 프롬프트 9,247자 → 출력 260자 · JSON 파싱 OK).
    #    남는 규칙은 **딥서치가 매치업보다 작지 않다**와 **한도 안**이다.
    assert s.deepsearch_max_tokens >= s.matchup_max_tokens
    assert s.deepsearch_max_tokens <= 1500, "무료 티어 분당 한도를 넘는다"
    src = Path("app/engine/deepsearch.py").read_text(encoding="utf-8")
    assert "max_tokens=2000" not in src, "출력 예산이 하드코딩으로 남아 있다"
    assert "s.deepsearch_max_tokens" in src


def test_prompt_pins_today_so_last_season_news_is_not_read_as_today():
    """🔴 절단보다 나쁜 결함: 조사가 **작년 기사**를 오늘 일로 올렸다.

    실측 2026-09-01: Michael King의 2025-08-14 부상자명단 등재와 2025-09-09
    복귀를 오늘의 컨디션 근거로 반환했다. 프롬프트에 오늘 날짜가 없었다.
    이런 근거가 통과하면 p_home 이 1년 전 사실로 움직인다.
    """
    from app.engine.deepsearch import PROMPT, _today_kst

    assert "{today}" in PROMPT
    assert "연도" in PROMPT
    assert "기사 날짜를 확인한다" in PROMPT
    assert _today_kst() == datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")


def test_prompt_bans_odds_as_a_reason_not_as_a_subject():
    """🔴 [DS-2 2026-09-09 사용자 지시] **조사 금지는 풀었다.** 선이 옮겨졌다.

    종전 문구는 "배당·머니라인·스포츠북·시장 내재확률을 **조사하지 마라**"였고,
    그래서 `T2_시장괴리` 가 발동해도 조사가 아무것도 묻지 못했다.
    금지의 근거였던 실사고(2026-09-01 MIL@CHC)를 다시 읽으면 문제는 조사가
    아니라 **숫자를 조정 사유로 쓴 것**이었다 — 내재확률 51~53%를 근거로
    p_home 0.59→0.56.

    그래서 지금 잠그는 것은 셋이다:
      ① 옛 체크리스트 문구("배당 급변"·"시장이 아는데")는 여전히 없다
      ② **가격을 조정 사유로 쓰지 말라**는 지시가 프롬프트에 있다
      ③ 그리고 그것은 **런타임 가드**(`strip_odds`)가 실제로 강제한다 —
         프롬프트는 부탁이고, 강제는 코드가 한다.
    """
    from app.engine.deepsearch import PROMPT, strip_odds

    assert "배당 급변" not in PROMPT
    assert "시장이 아는데" not in PROMPT
    assert "사유가 될 수 없다" in PROMPT
    assert "가격 자체" in PROMPT
    # ③ 말로만이 아니라 코드가 막는다
    out, dropped = strip_odds({"발견": [], "조정": {"p_home": 0.56,
                                                   "사유": "시장 내재확률 53%"}})
    assert "p_home" not in out["조정"], "배당 사유 조정이 폐기되지 않았다"
    assert dropped


def test_odds_reason_voids_the_adjustment_not_just_the_sentence():
    """🔴 실측 2026-09-01 (MIL@CHC): 조사가 스포츠북 머니라인 내재확률
    51~53%를 근거로 p_home 을 0.59→0.56 으로 내렸고, **추천 1건이 그대로
    보드만으로 떨어졌다.** 판정 숫자가 배당에 좌우된 것이다.

    근거 문장만 지우고 숫자를 반영하면 증거만 지우고 오염은 남긴다 —
    조정 자체를 폐기해야 한다.
    """
    from app.engine.deepsearch import apply_findings, strip_odds

    data = {"발견": [{"사실": "Swanson 옆구리 부상으로 IL 등재"},
                    {"사실": "복수 스포츠북 머니라인 Cubs -106, 내재확률 51~53%"}],
            "조정": {"p_home": 0.56, "사유": "Swanson 결장과 시장 배당 접전으로 하향",
                    "단일기사여부": False},
            "요약": "x"}
    clean, dropped = strip_odds(data)
    assert len(clean["발견"]) == 1, "배당 근거가 발견에 남았다"
    assert "p_home" not in clean["조정"], "배당이 사유인데 조정이 살아 있다"
    assert len(dropped) == 2

    jg = {"p_claude": 0.59, "matchup": {"우세": "home"}, "away": "MIL", "home": "CHC"}
    assert apply_findings(jg, data)["moved"] == 0.0
    assert jg["p_claude"] == 0.59, "배당이 p_home 을 움직였다 — 금지선"


def test_non_odds_adjustment_still_applies():
    """반대 위험도 잰다 — 가드가 정상 조사까지 죽이면 안 된다."""
    from app.engine.deepsearch import apply_findings

    data = {"발견": [{"사실": "주전 1루수 햄스트링 부상으로 오늘 결장 확정"}],
            "조정": {"p_home": 0.60, "사유": "홈 주전 결장으로 하향",
                    "단일기사여부": False},
            "요약": "x"}
    jg = {"p_claude": 0.63, "matchup": {"우세": "home"}, "away": "SEA", "home": "BOS"}
    assert apply_findings(jg, data)["moved"] == -3.0
    assert jg["p_claude"] == 0.60


# ---------------------------------------------------------------- 재판정 경로

class _FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, ex=None):
        self.store[k] = v

    async def incr(self, k):
        self.store[k] = str(int(self.store.get(k) or 0) + 1)
        return int(self.store[k])

    async def expire(self, k, ttl):
        return True


def _rejudge_jg(**kw):
    """야구 analysis 캐시 형태. T5 는 research 아래 타순을 본다."""
    g = {"game_id": 11, "sport": "kbo", "league": "KBO",
         "home": "LG Twins", "away": "NC Dinos", "p_claude": 0.55,
         "research": {"home_lineup": {"order": "김현수-오스틴-박해민"},
                      "away_lineup": {"order": "손아섭-박민우-맷데이비슨"},
                      "home_pitcher": {"name": "임찬규"}},
         "matchup": {"p_home": 0.55, "우세": "home", "확신도": "중"}}
    g.update(kw)
    return g


def _starter_changed_jg():
    return _rejudge_jg(matchup={"p_home": 0.55, "우세": "home", "확신도": "중",
                                "직전대비": {"변경입력": ["홈 선발 임찬규 → 켈리"]}})


@pytest.mark.asyncio
async def test_t4_t5_fire_on_baseball_jg_shape():
    """🔴 실측 2026-09-01: T5 가 야구에서 **한 번도 발동하지 않았다.**

    `lineup_anomaly` 가 jg["lineup_home"]·jg["home_lineup"] 만 보는데 야구
    analysis 캐시는 jg["research"]["home_lineup"]["order"] 에 담는다.
    키가 어긋나 주전 교체·핵심선수 결장 분기가 둘 다 죽어 있었다.
    """
    from app.engine.deepsearch import T4_STARTER, T5_LINEUP, triggers

    assert T4_STARTER in triggers(_starter_changed_jg(), S)
    prev = {"research": {"home_lineup": {"order": "A-B-C"},
                         "away_lineup": {"order": "손아섭-박민우-맷데이비슨"}}}
    assert T5_LINEUP in triggers(_rejudge_jg(), S, prev_lineup=prev)
    # 평상시에는 오탐이 없어야 한다 (반대 위험)
    assert T5_LINEUP not in triggers(_rejudge_jg(), S)


@pytest.mark.asyncio
async def test_rejudge_runs_once_then_dedupes_on_same_lineup(monkeypatch):
    """트리거 발동 → 1회 실행. 같은 (경기, 라인업)이면 재발동해도 스킵."""
    from app.engine import deepsearch as ds

    calls = []

    async def fake_investigate(jg, trig, **_kw):
        calls.append(trig)
        # [무과금 전환] 반환은 (데이터, 유료검색수, 검색출처) 3-튜플이다.
        return ({"발견": [], "조정": {"p_home": 0.55, "사유": "변화 없음",
                                   "단일기사여부": False}, "요약": "x"}, 0, "rss")

    monkeypatch.setattr(ds, "investigate", fake_investigate)
    S_on = Settings(_env_file=None, DEEPSEARCH_ENABLED=True)
    rds = _FakeRedis()

    r1 = await ds.run_for_rejudge(_starter_changed_jg(), rds, "2026-09-01",
                                  lineup_sig="임찬규|켈리|1:김현수|1:손아섭",
                                  slate_size=10, settings=S_on)
    assert r1["triggered"] and r1["status"] == "investigated"
    # [무과금 전환] `searches` 는 이제 **유료** web_search 횟수다. RSS 경로면 0.
    assert r1["searches"] == 0 and len(calls) == 1
    assert r1["search_source"] == "rss", "무료 경로로 조사됐음이 결과에 남아야 한다"

    r2 = await ds.run_for_rejudge(_starter_changed_jg(), rds, "2026-09-01",
                                  lineup_sig="임찬규|켈리|1:김현수|1:손아섭",
                                  slate_size=10, settings=S_on)
    assert r2["status"] == "deduped", "같은 라인업인데 또 조사했다"
    assert len(calls) == 1, "중복 조사가 나갔다 — 크레딧이 샌다"

    # 라인업이 실제로 바뀌면 다시 조사한다
    r3 = await ds.run_for_rejudge(_starter_changed_jg(), rds, "2026-09-01",
                                  lineup_sig="켈리|켈리|1:오스틴|1:손아섭",
                                  slate_size=10, settings=S_on)
    assert r3["status"] == "investigated" and len(calls) == 2


@pytest.mark.asyncio
async def test_rejudge_respects_slate_cap(monkeypatch):
    """상한 도달 시 실행하지 않고 trigger_fired=True, deepsearch=capped 로 기록."""
    from app.engine import deepsearch as ds

    async def boom(*_a, **_k):
        raise AssertionError("상한을 넘겨 조사가 나갔다")

    monkeypatch.setattr(ds, "investigate", boom)
    S_on = Settings(_env_file=None, DEEPSEARCH_ENABLED=True)
    rds = _FakeRedis()
    # 슬레이트 10경기 → 상한 3. 이미 3건 소진.
    assert ds.daily_cap(10, S_on) == 3
    rds.store[ds.SLATE_COUNT_KEY.format(sport="kbo", date="2026-09-01")] = "3"

    jg = _starter_changed_jg()
    out = await ds.run_for_rejudge(jg, rds, "2026-09-01", lineup_sig="x",
                                   slate_size=10, settings=S_on)
    assert out["status"] == "capped"
    assert jg["deepsearch_trigger"] == {"trigger_fired": True,
                                        "triggers": ["T4_선발변경"],
                                        "source": "model",
                                        "deepsearch": "capped", "searches": 0}


@pytest.mark.asyncio
async def test_rejudge_records_trigger_when_flag_off(monkeypatch, caplog):
    """🔴 플래그 off 여도 **판별·기록·would_have_searched 로그는 남긴다.**

    관찰 데이터에 T4·T5 가 찍히는 것이 이 수정의 핵심 목적이다.
    """
    import logging

    from app.engine import deepsearch as ds

    async def boom(*_a, **_k):
        raise AssertionError("플래그가 꺼졌는데 조사가 나갔다")

    monkeypatch.setattr(ds, "investigate", boom)
    assert Settings(_env_file=None).deepsearch_investigate is False
    rds = _FakeRedis()
    jg = _starter_changed_jg()
    with caplog.at_level(logging.INFO, logger="app.engine.deepsearch"):
        out = await ds.run_for_rejudge(jg, rds, "2026-09-01", lineup_sig="x",
                                       slate_size=10, settings=S)
    assert "would_have_searched=5" in caplog.text, "관찰 로그가 없다"
    assert "T4_선발변경" in caplog.text
    assert out["triggered"] is True and out["status"] == "disabled"
    assert jg["deepsearch_trigger"]["trigger_fired"] is True
    assert jg["deepsearch_trigger"]["triggers"] == ["T4_선발변경"]
    assert jg["deepsearch_trigger"]["deepsearch"] == "disabled"
    # 상한 카운터를 태우지 않았다 — 조사하지 않았으므로
    assert rds.store.get(
        ds.SLATE_COUNT_KEY.format(sport="kbo", date="2026-09-01")) is None


@pytest.mark.asyncio
async def test_rejudge_ignores_t1_t3_only():
    """🔴 [DS-6 2026-09-10 사용자 지시] **계약이 바뀌었다.**

    종전 계약: "재판정 경로는 T4·T5 에만 반응한다 — T1·T3 는 1차 판정에서 이미 봤다."
    그래서 타순만 바뀐 재판정은 조사가 통째로 생략됐다(실측 HOU@PHI:
    "발동=False 트리거=-", 상한은 13/15 로 여유 있었다). 사용자 지시:
        "재판정 수정카드도 딥서치 있게 나가야 한다."

    이제 T4/T5/T6 이 없어도 T0_전수가 붙어 조사한다. 다만 **T1·T3 를 재판정
    트리거로 승격시키지는 않는다** — 그 둘은 1차 판정에서 이미 봤고, 여기서
    걸리는 것은 어디까지나 전수 조사(T0)다. 중복은 라인업 서명 키가 막는다.
    """
    from app.engine import deepsearch as ds

    jg = _rejudge_jg(p_claude=0.58,
                     matchup={"p_home": 0.58, "우세": "home", "확신도": "중",
                              "추가확인": ["선발 컨디션"]})
    trig = ds.triggers(jg, S)
    assert ds.T1_BOUNDARY in trig and ds.T3_ASKED in trig
    out = await ds.run_for_rejudge(jg, _FakeRedis(), "2026-09-01",
                                   lineup_sig="x", slate_size=10, settings=S)
    assert out["triggered"] is True              # 전수 조사로 발동한다
    assert out["triggers"] == [ds.T0_ALL], "T1·T3 가 재판정 트리거로 승격되면 안 된다"
    # 조사 호출 자체는 `deepsearch_investigate` 가 꺼져 있어 여기서 멈춘다
    assert out["status"] == "disabled"


# ------------------------------------------------- T4·T5 하드 증거 (2026-09-01)

def test_t4_fires_on_poller_fact_alone():
    """🔴 실측 2026-09-01 강제 검증: T4 가 재판정에서 한 번도 걸리지 않았다.

    `_run_baseball_matchups` 가 jg["matchup"] 을 새 판정으로 통째로 덮어써,
    run_for_rejudge 는 주입한 직전대비가 아니라 **새 모델이 스스로 보고한
    `변경입력: []`** 를 봤다. 그런데 선발이 바뀌었다는 사실은 폴러가 이미
    갖고 있다 — lineup_notes 의 "홈 선발 변경: 임찬규 → 켈리".
    """
    from app.engine.deepsearch import SRC_FACT, T4_STARTER, t4_evidence, triggers

    jg = {"lineup_notes": ["홈 선발 변경: 임찬규 → 켈리"],
          "matchup": {"직전대비": {"변경입력": []}}}
    assert t4_evidence(jg) == (True, SRC_FACT)
    assert T4_STARTER in triggers(jg, S)


def test_t4_still_fires_on_model_report_alone():
    """회귀 — 폴러 노트가 없어도 모델 자기 보고로는 여전히 걸린다."""
    from app.engine.deepsearch import SRC_MODEL, T4_STARTER, t4_evidence, triggers

    jg = {"matchup": {"직전대비": {"변경입력": ["홈 선발 임찬규 → 켈리"]}}}
    assert t4_evidence(jg) == (True, SRC_MODEL)
    assert T4_STARTER in triggers(jg, S)


def test_t4_silent_when_neither_source_says_so():
    """반대 위험 — 근거가 없으면 걸리지 않는다."""
    from app.engine.deepsearch import T4_STARTER, t4_evidence, triggers

    jg = {"lineup_notes": ["우천 지연 안내"],
          "matchup": {"직전대비": {"변경입력": ["타순 3번 교체"]}}}
    assert t4_evidence(jg) == (False, None)
    assert T4_STARTER not in triggers(jg, S)


def test_t5_fires_on_lineup_diff_fact():
    """T5 하드 증거 — 직전 대비 타순 diff. **임계값은 기존대로 주전 2명.**"""
    from app.engine.deepsearch import T5_LINEUP, t5_evidence, triggers

    cur = {"research": {"home_lineup": {"order": "김현수-오스틴-박해민"},
                        "away_lineup": {"order": "손아섭-박민우-권희동"}}}
    prev = {"research": {"home_lineup": {"order": "문보경-홍창기-박해민"},
                         "away_lineup": {"order": "손아섭-박민우-권희동"}}}
    fired, src = t5_evidence(cur, prev)
    assert fired is True and src is not None
    assert T5_LINEUP in triggers(cur, S, prev_lineup=prev)


def test_t5_silent_when_lineup_unchanged():
    """반대 위험 — diff 가 없으면 걸리지 않는다. 1명만 바뀌어도 안 된다."""
    from app.engine.deepsearch import T5_LINEUP, t5_evidence, triggers

    cur = {"research": {"home_lineup": {"order": "김현수-오스틴-박해민"},
                        "away_lineup": {"order": "손아섭-박민우-권희동"}}}
    assert t5_evidence(cur, cur) == (False, None)
    assert T5_LINEUP not in triggers(cur, S, prev_lineup=cur)
    one = {"research": {"home_lineup": {"order": "문보경-오스틴-박해민"},
                        "away_lineup": {"order": "손아섭-박민우-권희동"}}}
    assert t5_evidence(cur, one)[0] is False, "1명 교체로 걸리면 임계값이 바뀐 것"


@pytest.mark.asyncio
async def test_source_is_recorded_on_the_game():
    """근거 출처가 기록에 남는다 — model / poller_fact / both.

    모델 자백으로 걸린 건과 사실로 걸린 건은 트리거를 나중에 손볼 때
    완전히 다른 데이터다. 섞어 놓으면 구분할 수 없다.
    """
    from app.engine import deepsearch as ds

    jg = {"game_id": 7, "sport": "kbo", "p_claude": 0.55,
          "lineup_notes": ["홈 선발 변경: 임찬규 → 켈리"],
          "matchup": {"직전대비": {"변경입력": []}}}
    out = await ds.run_for_rejudge(jg, _FakeRedis(), "2026-09-01",
                                   lineup_sig="x", slate_size=10, settings=S)
    assert out["triggered"] is True
    assert out["source"] == ds.SRC_FACT
    assert jg["deepsearch_trigger"]["source"] == ds.SRC_FACT
    assert jg["deepsearch_trigger"]["triggers"] == [ds.T4_STARTER]
    assert jg["deepsearch_trigger"]["deepsearch"] == "disabled"


# ------------------------------------------- 조사 우선순위 (C · 2026-09-01)

def test_blind_starters_scores_no_data_highest():
    """자료가 없는 쪽을 센다. **새 임계값을 만들지 않고** MIN_STARTS 를 쓴다."""
    from app.engine.deepsearch import blind_starters

    def jg(hs, hr, as_, ar):
        return {"research": {"home_starter_recent": [{}] * hs,
                             "home_starter_relief": [{}] * hr,
                             "away_starter_recent": [{}] * as_,
                             "away_starter_relief": [{}] * ar}}

    assert blind_starters(jg(0, 0, 0, 0))["score"] == 6      # 양쪽 완전 무자료
    assert blind_starters(jg(0, 0, 3, 0))["score"] == 3      # 한쪽 완전 무자료
    assert blind_starters(jg(0, 3, 3, 0))["score"] == 2      # 선발0·구원있음
    assert blind_starters(jg(1, 0, 3, 0))["score"] == 1      # 표본 하한
    assert blind_starters(jg(3, 0, 4, 0))["score"] == 0      # 충분
    assert blind_starters(jg(0, 3, 3, 0))["zero"] == ["home"]


@pytest.mark.asyncio
async def test_ranking_puts_blind_games_first_within_the_same_cap():
    """🔴 실측 2026-09-01 NPB: 6경기 전부 후보인데 상한은 1건이었고, 순서가
    트리거 수로만 정해져 **자료가 통째로 없는 경기가 상한에 밀렸다.**

      戸郷 翔征  1군 등판 0 (7/7 햄스트링 이탈, 8/26 2군 복귀전이 전부)
      高野 脩汰  선발 0 (올해 26경기 전부 중계, 그날이 시즌 첫 선발)

    이런 경기는 크롤 데이터로 답이 안 나온다 — 조사가 가장 필요하다.
    ⚠️ **상한은 그대로다.** 순서만 바꾼다.
    """
    from app.engine import deepsearch as ds

    def game(gid, hs, asamples, asked):
        return {"game_id": gid, "sport": "npb", "p_claude": 0.55,
                "home": f"H{gid}", "away": f"A{gid}",
                "research": {"home_starter_recent": [{}] * hs,
                             "away_starter_recent": [{}] * asamples},
                "matchup": {"p_home": 0.55, "우세": "home", "확신도": "중",
                            "추가확인": asked}}

    # 1: 트리거 2개인데 자료는 충분  2: 트리거 1개인데 홈 선발 자료 0
    rich = game(1, 3, 3, ["x"])
    blind = game(2, 0, 3, [])
    out = await ds.run_for_slate([rich, blind], None, "2026-09-01", settings=S)
    assert out["disabled"] is True          # 플래그 off — 판별만
    assert len(out["candidates"]) == 2
    # 상한은 슬레이트 2 × 30% → 최소 1건. 순서가 무자료 우선이어야 한다.
    assert ds.daily_cap(2, S) == 1
    order = sorted(out["candidates"],
                   key=lambda c: (-c["blind"]["score"], -len(c["triggers"])))
    assert order[0]["game_id"] == 2, "자료 없는 경기가 뒤로 밀렸다"
    assert order[0]["blind"]["zero"] == ["home"]


def test_priority_does_not_change_the_cap():
    """우선순위는 순서만 바꾼다 — 상한(슬레이트 30%)은 그대로다."""
    from app.engine.deepsearch import daily_cap

    assert daily_cap(6, S) == 1
    assert daily_cap(11, S) == 3
    assert daily_cap(1, S) == 1          # 최소 1건 보장도 그대로


def test_checklist_covers_starters_with_no_record():
    """🔴 실측 2026-09-01 (NPB 요미우리전): 戸郷 翔征은 1군 등판 0으로
    판정이 "개인 폼 확인 불가"에서 멈췄다. 웹 검색 5분이면 7/7 햄스트링
    이탈·8/26 2군 복귀전 4이닝 무실점·감독 코멘트까지 나온다.
    조사가 못 찾은 게 아니라 **체크리스트에 항목이 없었다.**

    ⚠️ 찾아와도 추천은 열리지 않는다 — 표본 하한은 코드가 따로 집행한다.
    """
    from app.engine.deepsearch import PROMPT

    assert "선발 등판 기록이 없거나 1경기뿐인 투수" in PROMPT
    assert "2군·마이너 포함" in PROMPT
    assert "추천이 열리지는 않는다" in PROMPT
    # 지어내기 금지가 함께 있어야 한다
    assert '못 찾으면 "미확인"으로 적는다' in PROMPT


# ------------------------------------------ 예산 단일화 (2026-09-01)

def _slate_jg(gid, asked=("선발 컨디션",)):
    return {"game_id": gid, "sport": "npb", "league": "NPB",
            "home": f"H{gid}", "away": f"A{gid}", "p_claude": 0.55,
            "research": {"home_starter_recent": [{}, {}, {}],
                         "away_starter_recent": [{}, {}, {}]},
            "matchup": {"p_home": 0.55, "우세": "home", "확신도": "중",
                        "추가확인": list(asked)}}


@pytest.mark.asyncio
async def test_slate_and_rejudge_share_one_budget(monkeypatch):
    """🔴 종전에는 1차 판정이 로컬 카운터만, 재판정이 Redis 카운터만 써서
    **서로를 못 봤다.** 같은 슬레이트에서 1차 3건 + 재판정 3건 = 6건이 되어
    상한 30% 가 사실상 60% 로 벌어진다. 둘 다 같은 Redis 키를 쓴다.
    """
    from app.engine import deepsearch as ds

    calls = []

    async def fake_investigate(jg, trig, **_kw):
        calls.append(jg.get("game_id"))
        return ({"발견": [], "조정": {"p_home": 0.55, "사유": "변화 없음",
                                   "단일기사여부": False}, "요약": "x"}, 0, "rss")

    monkeypatch.setattr(ds, "investigate", fake_investigate)
    S_on = Settings(_env_file=None, DEEPSEARCH_ENABLED=True)
    rds = _FakeRedis()
    games = [_slate_jg(i) for i in range(10)]
    assert ds.daily_cap(10, S_on) == 3

    out = await ds.run_for_slate(games, rds, "2026-09-01", settings=S_on)
    assert out["investigated"] == 3, "1차에서 상한만큼 써야 한다"
    key = ds.SLATE_COUNT_KEY.format(sport="npb", date="2026-09-01")
    assert int(rds.store[key]) == 3, "1차가 Redis 카운터를 올리지 않았다"

    # 같은 날 재판정 — 예산이 이미 소진됐으므로 capped 여야 한다
    jg = _slate_jg(99)
    jg["lineup_notes"] = ["홈 선발 변경: A → B"]
    r = await ds.run_for_rejudge(jg, rds, "2026-09-01", lineup_sig="x",
                                 slate_size=10, settings=S_on)
    assert r["status"] == "capped", "1차가 다 썼는데 재판정이 또 조사했다"
    assert len(calls) == 3, f"총 조사 {len(calls)}건 — 상한 3을 넘었다"


@pytest.mark.asyncio
async def test_slate_uses_only_remaining_budget(monkeypatch):
    """재판정이 먼저 쓴 만큼 1차의 몫이 줄어든다 — 순서와 무관하게 합이 상한이다."""
    from app.engine import deepsearch as ds

    calls = []

    async def fake_investigate(jg, trig, **_kw):
        calls.append(jg.get("game_id"))
        return ({"발견": [], "조정": {"p_home": 0.55, "사유": "x",
                                   "단일기사여부": False}, "요약": "x"}, 0, "rss")

    monkeypatch.setattr(ds, "investigate", fake_investigate)
    S_on = Settings(_env_file=None, DEEPSEARCH_ENABLED=True)
    rds = _FakeRedis()
    key = ds.SLATE_COUNT_KEY.format(sport="npb", date="2026-09-01")
    rds.store[key] = "2"                       # 재판정이 이미 2건 씀

    out = await ds.run_for_slate([_slate_jg(i) for i in range(10)], rds,
                                 "2026-09-01", settings=S_on)
    assert out["used_before"] == 2
    assert out["investigated"] == 1, "잔여 1건만 써야 하는데 더 썼다"
    assert int(rds.store[key]) == 3


def test_game_cache_ttl_prevents_same_day_reinvestigation():
    """게임별 캐시 6h → 24h. 저녁 슬레이트가 6시간을 넘기면 같은 경기를
    하루에 두 번 조사한다. 날짜가 키에 있어 다음날과 충돌하지 않는다."""
    from app.engine.deepsearch import CACHE_KEY, CACHE_TTL

    assert CACHE_TTL == 24 * 3600
    assert "{date}" in CACHE_KEY


# ─────────────── T6: 라인업 최초 확정 (2026-09-02 사용자 지시) ───────────────

def test_t6_fires_on_first_confirmation_not_on_change():
    """🔴 "라인업이 발표되면 딥서치 바로 시작해야 한다 — 라인업 변동이 아니라."

    종전 T4·T5 는 **직전 대비 차이**만 봤다. 최초 공시는 비교 대상이 없어
    아무 트리거도 안 걸렸다 — 타순이 나온 그 순간이 가장 정보가 많은데
    조사를 건너뛰고 있었다.
    """
    from app.engine.deepsearch import first_lineup_evidence

    jg = {"lineup_status": "confirmed",
          "research": {"home_lineup": {"order": "A-B"},
                       "away_lineup": {"order": "C-D"}}}
    # 🔴 `prev_lineup` 은 **껍데기가 항상 온다.** dict 가 truthy 라고
    #    "직전이 있다"로 읽으면 T6 가 영원히 안 걸린다.
    shell = {"research": {"home_lineup": {}, "away_lineup": {}}}
    assert first_lineup_evidence(jg, shell) is True
    assert first_lineup_evidence(jg, None) is True


def test_t6_yields_to_t4_t5_once_a_lineup_exists():
    """직전 타순이 있으면 그건 '변동'이라 T4·T5 소관이다."""
    from app.engine.deepsearch import first_lineup_evidence

    jg = {"lineup_status": "confirmed",
          "research": {"home_lineup": {"order": "A-B"}, "away_lineup": {}}}
    prev = {"research": {"home_lineup": {"order": "X-Y"}, "away_lineup": {}}}
    assert first_lineup_evidence(jg, prev) is False


def test_t6_never_fires_on_a_provisional_lineup():
    """⚠️ 예상 타순으로 조사하면 그 조사가 예상에 매달린다."""
    from app.engine.deepsearch import first_lineup_evidence

    jg = {"lineup_status": "predicted",
          "research": {"home_lineup": {"order": "A-B"}, "away_lineup": {}}}
    assert first_lineup_evidence(jg, None) is False
    # 타순 자체가 없으면 확정 상태여도 발동하지 않는다
    assert first_lineup_evidence({"lineup_status": "confirmed",
                                  "research": {}}, None) is False


@pytest.mark.asyncio
async def test_t6_is_recorded_as_a_fact_not_a_model_claim(monkeypatch):
    """공시는 사실이다 — 모델 자백(SRC_MODEL)과 구분해 기록한다."""
    from app.engine import deepsearch as ds

    async def fake_investigate(jg, trig, **_kw):
        return ({"발견": [], "조정": {"p_home": 0.55, "사유": "x",
                                   "단일기사여부": False}, "요약": "x"}, 0, "rss")

    monkeypatch.setattr(ds, "investigate", fake_investigate)
    jg = {"game_id": 1, "sport": "kbo", "home": "H", "away": "A",
          "lineup_status": "confirmed",
          "matchup": {"p_home": 0.55, "우세": "home"},
          "research": {"home_lineup": {"order": "A-B"},
                       "away_lineup": {"order": "C-D"}}}
    out = await ds.run_for_rejudge(
        jg, _FakeRedis(), "2026-09-02", lineup_sig="sig-1", slate_size=5,
        prev_lineup={"research": {"home_lineup": {}, "away_lineup": {}}},
        settings=Settings(_env_file=None, DEEPSEARCH_ENABLED=True))
    assert out["triggered"] and ds.T6_FIRST_LINEUP in out["triggers"]
    assert out["source"] == ds.SRC_FACT


@pytest.mark.asyncio
async def test_t6_is_exempt_from_the_slate_cap(monkeypatch):
    """🔴 [사용자 지시] "T6 무조건 걸리게 해라."

    슬레이트 30% 상한은 `web_search` **검색 수수료** 때문에 걸었던 것이다.
    무과금 전환으로 조사가 RSS(무료)로 도니 근거가 사라졌다. 5경기 슬레이트에서
    상한 1이면 "라인업 발표되면 조사"가 리그당 1경기로 줄어 지시가 무력해진다.
    """
    from app.engine import deepsearch as ds

    calls = []

    async def fake_investigate(jg, trig, **_kw):
        calls.append(trig)
        return ({"발견": [], "조정": {"p_home": 0.55, "사유": "x",
                                   "단일기사여부": False}, "요약": "x"}, 0, "rss")

    monkeypatch.setattr(ds, "investigate", fake_investigate)
    rds = _FakeRedis()
    S = Settings(_env_file=None, DEEPSEARCH_ENABLED=True)
    shell = {"research": {"home_lineup": {}, "away_lineup": {}}}

    # 5경기 슬레이트 → 상한 1. 그래도 5경기 전부 조사돼야 한다.
    for gid in range(1, 6):
        jg = {"game_id": gid, "sport": "kbo", "home": f"H{gid}",
              "away": f"A{gid}", "lineup_status": "confirmed",
              "matchup": {"p_home": 0.55, "우세": "home"},
              "research": {"home_lineup": {"order": "A-B"},
                           "away_lineup": {"order": "C-D"}}}
        out = await ds.run_for_rejudge(jg, rds, "2026-09-02",
                                       lineup_sig=f"sig-{gid}", slate_size=5,
                                       prev_lineup=shell, settings=S)
        assert out["status"] == "investigated", f"game {gid}: {out['status']}"
    assert len(calls) == 5, "상한 1에 막히면 안 된다"


@pytest.mark.asyncio
async def test_t6_still_dedupes_per_lineup(monkeypatch):
    """⚠️ 상한은 풀어도 **중복은 막는다.** 안 그러면 5분 폴링마다 Sonnet 을 태운다."""
    from app.engine import deepsearch as ds

    calls = []

    async def fake_investigate(jg, trig, **_kw):
        calls.append(1)
        return ({"발견": [], "조정": {"p_home": 0.55, "사유": "x",
                                   "단일기사여부": False}, "요약": "x"}, 0, "rss")

    monkeypatch.setattr(ds, "investigate", fake_investigate)
    rds = _FakeRedis()
    S = Settings(_env_file=None, DEEPSEARCH_ENABLED=True)
    jg = {"game_id": 9, "sport": "kbo", "home": "H", "away": "A",
          "lineup_status": "confirmed",
          "matchup": {"p_home": 0.55, "우세": "home"},
          "research": {"home_lineup": {"order": "A-B"},
                       "away_lineup": {"order": "C-D"}}}
    shell = {"research": {"home_lineup": {}, "away_lineup": {}}}
    for _ in range(4):          # 폴링 4틱
        await ds.run_for_rejudge(jg, rds, "2026-09-02", lineup_sig="same",
                                 slate_size=5, prev_lineup=shell, settings=S)
    assert len(calls) == 1, "같은 라인업으로 두 번 조사하면 안 된다"


# ── [DS-14 2026-09-10 사용자 지시] "권한을 바꿔라" ─────────────────────────
#   🔴 실측이 이 변경의 근거다 (채점 완료 172경기, `game_id` 중복 제거):
#        딥서치 적용 전 88/172 = 51.2%
#        딥서치 적용 후 88/172 = 51.2%   ← 완전히 같다
#        우세가 뒤집힌 경기 **0건**
#      원인은 조사 품질이 아니라 **권한**이었다. `clamp_adjustment` 가
#      "우세 방향 단독 뒤집기 금지"로 0.50 에서 멈춰 세워, 딥서치는 같은 팀
#      안에서 확률만 밀 수 있었다. 승패 적중률에 기여할 길이 원천 차단돼 있었다.
#   ⚠️ 권한을 주되 **아무 근거로나 주지 않는다.** 뉴스 한 줄로 픽이 뒤집히면
#      그건 개선이 아니라 소음이다.

def test_flip_allowed_with_hard_evidence():
    from app.engine.deepsearch import clamp_adjustment

    hard = [{"사실": "선발 교체 공시", "소스유형": "공식"}]
    p, note = clamp_adjustment(0.54, 0.46, "home", evidence=hard)
    assert p < 0.5, f"공식 근거로도 못 뒤집는다: {p} {note}"


def test_flip_blocked_without_hard_evidence():
    """⚠️ 반대 위험 — 뉴스·소문만으로 픽이 뒤집히면 안 된다."""
    from app.engine.deepsearch import clamp_adjustment

    soft = [{"사실": "결장 가능성이 거론된다", "소스유형": "뉴스"}]
    p, _ = clamp_adjustment(0.54, 0.46, "home", evidence=soft)
    assert p >= 0.5, "뉴스만으로 뒤집혔다"


def test_flip_must_be_decisive():
    """⚠️ 0.4999 같은 간발의 뒤집기는 뒤집기가 아니라 잡음이다."""
    from app.engine.deepsearch import clamp_adjustment

    hard = [{"사실": "선발 교체 공시", "소스유형": "공식"}]
    p, _ = clamp_adjustment(0.54, 0.499, "home", evidence=hard)
    assert p >= 0.5, "간발 차 뒤집기가 통과했다"


def test_no_evidence_keeps_old_guard():
    """근거 정보가 없으면 종전 그대로 — 기본값이 느슨해지지 않는다."""
    from app.engine.deepsearch import clamp_adjustment

    p, note = clamp_adjustment(0.54, 0.46, "home")
    assert p == 0.5 and note and "뒤집기 금지" in note


# ── [DS-15 2026-09-10] 뒤집기 가드가 모델의 **라벨**을 보고 있었다 ─────────
#   🔴 `favored` 는 모델이 스스로 붙인 말이고, 우리가 실제로 행동하는 값은
#      `p_before` 숫자다. 라벨이 "박빙"이면 가드가 **아예 안 돌았다** —
#        clamp_adjustment(0.52, 0.49, "박빙") → (0.49, None)   ← 그냥 통과
#        clamp_adjustment(0.52, 0.49, "home") → (0.50, "뒤집기 금지")
#   실측: 채점 181경기 중 **31건(17%)이 박빙 라벨** — 그 경기들은 검사 없이
#      딥서치가 0.50 을 넘나들 수 있었다. 오늘 텍사스@시애틀(0.52→0.49,
#      실제 홈승)이 그 첫 발현으로 보인다.

def test_guard_uses_number_not_label():
    from app.engine.deepsearch import clamp_adjustment

    p, note = clamp_adjustment(0.52, 0.49, "박빙")
    assert p == 0.5 and note and "뒤집기 금지" in note, f"박빙 라벨로 새어나갔다: {p}"
    p2, _ = clamp_adjustment(0.48, 0.52, None)
    assert p2 == 0.5, "라벨이 없으면 무방비다"


def test_label_cannot_override_number():
    """라벨과 숫자가 어긋나면 **숫자가 이긴다**."""
    from app.engine.deepsearch import clamp_adjustment

    # 모델은 home 우세라 적었지만 숫자는 원정(0.48)이다 → 지켜야 할 쪽은 원정
    p, _ = clamp_adjustment(0.48, 0.53, "home")
    assert p == 0.5, "라벨을 믿고 원정 우세를 뒤집었다"


def test_exact_half_before_is_not_a_flip():
    """⚠️ 반대 위험 — p_before 가 정확히 0.50 이면 지킬 방향이 없다."""
    from app.engine.deepsearch import clamp_adjustment

    p, _ = clamp_adjustment(0.50, 0.54, "박빙")
    assert p == pytest.approx(0.54), "지킬 방향이 없는데 막았다"
