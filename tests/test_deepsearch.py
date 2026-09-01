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


def test_no_trigger_means_no_investigation():
    """편안한 확률·이상 없음 → 발동하지 않는다. 상시 검색 금지."""
    assert triggers(_jg(p_claude=0.66), S) == []


# ---------------------------------------------------------------- 상한

def test_daily_cap_is_share_of_slate():
    assert daily_cap(15, S) == 4          # 30%
    assert daily_cap(0, S) == 0


def test_daily_cap_allows_at_least_one():
    """3경기 슬레이트에서 0.9 → 0이면 경계 경기가 있어도 손을 놓게 된다."""
    assert daily_cap(3, S) == 1
    assert daily_cap(1, S) == 1


def test_adjustment_is_capped_at_4pp():
    """🔴 프롬프트가 아니라 코드가 강제한다."""
    p, note = clamp_adjustment(0.60, 0.75, "home")
    assert p == pytest.approx(0.64)
    assert f"±{ADJUST_CAP_PP:g}%p" in note
    p2, _ = clamp_adjustment(0.60, 0.40, "home")
    assert p2 == pytest.approx(0.56)


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
    assert "±4%p" in PROMPT


def test_search_count_is_capped_by_api_not_just_prompt():
    """max_uses 로 API가 강제한다 — 모델의 자제에 기대지 않는다."""
    src = Path("app/engine/deepsearch.py").read_text(encoding="utf-8")
    assert '"max_uses": int(s.deepsearch_max_searches)' in src
    assert "web_search_20260318" in src


def test_credit_guard_applies_to_this_path():
    src = Path("app/engine/deepsearch.py").read_text(encoding="utf-8")
    assert "abort_if_credit_gone" in src and "trip_credit" in src


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

    data, used = await investigate({"sport": "kbo", "home": "H", "away": "A",
                                    "matchup": {"p_home": 0.6}}, ["T1"])
    assert (data, used) == (None, 0)


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
    assert "web_search_requests" in src
    assert 'getattr(b, "type", "") == "server_tool_use")' not in src


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
    assert "stop_reason" in head, "절단인지 형식 이탈인지 구분할 수 없다"
    assert "output_tokens" in head
    assert "%.400s" in head, "본문을 남기지 않으면 형식 이탈을 못 본다"


def test_output_budget_is_configurable_and_larger_than_matchup():
    """🔴 실측 2026-09-01: max_tokens=2000 → stop="max_tokens", 출력 5804토큰,
    JSON이 743자에서 절단. 조사 4/4가 이것 때문에 실패했다.

    web_search 는 한 번의 호출 안에서 검색-읽기를 여러 턴 돌고 그 중간 서술이
    전부 출력 예산을 먹는다. **판정(4000)보다 커야 한다** — 조사가 더 많이
    쓰는데 절반만 준 것이 결함이었다. 하드코딩도 함께 걷어낸다.
    """
    s = Settings(_env_file=None)
    assert s.deepsearch_max_tokens > s.matchup_max_tokens
    assert s.deepsearch_max_tokens >= 5804, "실측 소진량보다 작으면 또 잘린다"
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


def test_prompt_does_not_ask_about_odds():
    """🔴 프롬프트 체크리스트 ④가 "시장이 아는데 우리가 모르는 정보
    (배당 급변·역방향 사유)"를 물었다 — 배당을 보라고 코드가 시킨 것이다.
    """
    from app.engine.deepsearch import PROMPT

    assert "배당 급변" not in PROMPT
    assert "시장이 아는데" not in PROMPT
    assert "배당·머니라인·스포츠북·시장 내재확률을 조사하지 마라" in PROMPT


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
        return {"발견": [], "조정": {"p_home": 0.55, "사유": "변화 없음",
                                  "단일기사여부": False}, "요약": "x"}, 3

    monkeypatch.setattr(ds, "investigate", fake_investigate)
    S_on = Settings(_env_file=None, DEEPSEARCH_ENABLED=True)
    rds = _FakeRedis()

    r1 = await ds.run_for_rejudge(_starter_changed_jg(), rds, "2026-09-01",
                                  lineup_sig="임찬규|켈리|1:김현수|1:손아섭",
                                  slate_size=10, settings=S_on)
    assert r1["triggered"] and r1["status"] == "investigated"
    assert r1["searches"] == 3 and len(calls) == 1

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
    """재판정 경로는 T4·T5 에만 반응한다 — T1·T3 는 1차 판정에서 이미 봤다."""
    from app.engine import deepsearch as ds

    jg = _rejudge_jg(p_claude=0.58,
                     matchup={"p_home": 0.58, "우세": "home", "확신도": "중",
                              "추가확인": ["선발 컨디션"]})
    trig = ds.triggers(jg, S)
    assert ds.T1_BOUNDARY in trig and ds.T3_ASKED in trig
    out = await ds.run_for_rejudge(jg, _FakeRedis(), "2026-09-01",
                                   lineup_sig="x", slate_size=10, settings=S)
    assert out["triggered"] is False and out["status"] is None
    assert "deepsearch_trigger" not in jg
