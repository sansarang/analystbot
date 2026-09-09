"""[C2] 변수 정량 형식 — 파싱·예산·표기.

🔴 §3 은 **변수 출력 명세만** 여는 동결 예외다. 프롬프트의 다른 문장은
   한 줄도 바뀌지 않았음을 이 파일이 함께 잠근다.
"""
import pytest

from app.engine.prompts import MATCHUP
from app.engine.variable_parse import check_budget, parse_all, parse_variable

GOOD = ("원정 선발 이로운 3이닝 미만 조기 강판 — 발생 시 홈 방향 약 8%p · "
        "현재 p에 3%p 기반영 · 근거 자료10")


def test_parses_the_specified_format():
    p = parse_variable(GOOD)
    # [2026-09-07] `q`(발생 확률) 는 **선택 칸**이라 없으면 None 이다.
    #   자료14 가 그 리스크의 빈도를 알려줬을 때만 값이 붙는다.
    assert p == {"risk": "원정 선발 이로운 3이닝 미만 조기 강판", "side": "home",
                 "n": 8.0, "m": 3.0, "source": "자료10", "q": None}


def test_away_direction_and_decimals():
    p = parse_variable("타선 침체 지속 — 발생 시 원정 방향 약 4.5%p · "
                       "현재 p에 1.5%p 기반영 · 근거 자료1,자료10")
    assert p["side"] == "away" and p["n"] == 4.5 and p["m"] == 1.5
    assert p["source"] == "자료1,자료10"


def test_no_reference_variant_still_parses():
    """"근거 없음 — 보수 반영" 도 형식 안에 있어야 파싱된다."""
    p = parse_variable("불펜 과부하 — 발생 시 원정 방향 약 5%p · "
                       "현재 p에 2%p 기반영 · 근거 없음 — 보수 반영")
    assert p is not None and p["m"] == 2.0
    assert "없음" in p["source"]


def test_narrative_variable_fails_to_parse_and_is_logged(caplog):
    """🔴 종전 서술형은 **정량 실패로 남는다** — 조용히 통과시키지 않는다."""
    old = "원정 선발 이로운은 선발등판 기록이 0건이라 이닝 소화력 예측 불가"
    assert parse_variable(old) is None
    with caplog.at_level("INFO"):
        rows = parse_all({"변수": [old]})
    assert rows[0]["parsed"] is None and rows[0]["raw"] == old
    assert any("형식 위반" in r.getMessage() for r in caplog.records)


def test_budget_rule_two():
    """② M 합 ≤ |p−0.50|."""
    v = {"p_home": 0.60, "변수": [GOOD]}
    r = check_budget(v)
    assert r["budget"] == 10.0 and r["sum_m"] == 3.0 and r["ok"] is True


def test_budget_violation_warns_but_does_not_reject(caplog):
    """🔴 **판정을 막지 않는다.** 감시가 발송을 멈추면 안 된다."""
    big = ("리스크 — 발생 시 홈 방향 약 20%p · 현재 p에 15%p 기반영 · 근거 자료10")
    with caplog.at_level("WARNING"):
        r = check_budget({"p_home": 0.55, "변수": [big]})
    assert r["ok"] is False and r["sum_m"] == 15.0 and r["budget"] == 5.0
    assert any("규칙② 위반" in x.getMessage() for x in caplog.records)
    # 반환만 할 뿐 예외를 던지지 않는다
    assert isinstance(r, dict)


def test_budget_without_p_home_is_not_judged():
    r = check_budget({"변수": [GOOD]})
    assert r["budget"] is None and r["ok"] is True


# ═════════ 프롬프트 — §3 블록만 열렸는가 ═════════

def test_prompt_has_the_variable_spec():
    assert "[변수 형식]" in MATCHUP
    assert "발생 시 <홈|원정> 방향 약 N%p" in MATCHUP
    assert "현재 p에 M%p 기반영" in MATCHUP
    assert "근거 <자료 번호>" in MATCHUP


def test_prompt_has_the_three_rules():
    assert "근거 없음 — 보수 반영" in MATCHUP          # ①
    assert "M 의 합은 |p_home − 0.50| 이내" in MATCHUP  # ②
    assert "변수로 우세를 뒤집지 않는다" in MATCHUP      # ③


def test_frozen_sentences_are_untouched():
    """§3 밖 문장은 그대로다 — diff 가 이 블록을 넘으면 반려다."""
    for kept in ("p_home은 0.32~0.68 범위를 벗어나지 않는다",
                 "근거는 위 자료 안에서만 찾는다",
                 "{{BOXSCORE_JSON}}", "{{BULLPEN_JSON}}"):
        assert kept in MATCHUP, kept
    # [C2 2026-09-04] 자료7·8 은 대원칙에 따라 폐지됐다 — 동결 목록에서 뺀다.
    for gone in ("{{LINEUP_SEASON_JSON}}", "{{STARTER_SEASON_JSON}}"):
        assert gone not in MATCHUP, gone


def test_card_emits_the_variable_verbatim():
    """렌더는 **발명하지 않는다** — 문자열을 그대로 낸다."""
    from pathlib import Path

    src = Path("app/engine/form_card.py").read_text(encoding="utf-8")
    assert 'lines.append(f"변수 {v}")' in src


# ═════════ §5 표본 재시작 ═════════

def test_sample_restarts_for_all_three_leagues():
    """자료10·변수 명세는 **판정 입력 변경**이다 — 표본을 섞지 않는다."""
    from app.engine.daily_summary import (
        FREEZE_RESTART_IS_FINAL, FREEZE_RESTART_REASON, freeze_start,
    )

    assert freeze_start("kbo") == freeze_start("npb") == freeze_start("mlb")
    from app.engine.daily_summary import FREEZE_START_DEFAULT

    assert freeze_start("kbo") == FREEZE_START_DEFAULT
    # 🔴 사유 문구는 재시작마다 바뀐다 — **문구를 베끼지 않는다.**
    #    (2026-09-04 "변수 대장" → v1.4 2026-09-07 "실력 축 복원")
    #    지켜야 할 성질은 "사유가 비어 있지 않다" 하나다. 숫자가 0 부터
    #    시작하는 이유를 사용자가 묻기 전에 답할 수 있으면 된다.
    assert FREEZE_RESTART_REASON.strip()
    # 🔴 이 재시작이 마지막이다 — 재료를 바꿀 때마다 버리면 50건에 영영 못 간다
    assert FREEZE_RESTART_IS_FINAL is True


@pytest.mark.asyncio
async def test_summary_states_the_restart_reason():
    """숫자가 왜 0 부터인지 **묻기 전에** 답한다."""
    from app.engine.daily_summary import freeze_progress_lines

    class Pool:
        async def fetch(self, sql, *a):
            return [{"sport": "kbo", "n": 2}]

    lines = await freeze_progress_lines(Pool(), ("kbo",))
    # 사유 문구는 재시작마다 바뀐다 — 문구를 베끼지 말고 **원본과 대조**한다.
    from app.engine.daily_summary import FREEZE_RESTART_REASON

    assert any("표본 재시작" in x and FREEZE_RESTART_REASON in x
               for x in lines), lines


# ── [VARP-1 2026-09-08] 읽는 쪽이 실문장을 못 받아 7%가 버려졌다 ────────
#
# 🔴 실측 2026-09-08 운영 `variable_ledger` 680행: `parse_variable` 성공 631 ·
#    **실패 49(7%)**. 버려지면 `variable_ledger` 에 `unverifiable` 로 쌓일 뿐
#    아니라 `branch_resolve.attach` 의 질문 목록에서도 빠져 — **자료14 의 DB
#    조회가 시작조차 안 된다.** 사용자가 "변수를 DB에서 찾아 측정하는 것이
#    안 나온다"고 본 것이 이 자리다.
#
# ⚠️ 이 모듈은 같은 계열의 사고를 이미 겪었다(위 `_SIDE` 주석, 2026-09-07
#    grok `home` 표기). 원칙도 거기 적혀 있다 —
#    **"쓰는 쪽은 한국어로 못박고 읽는 쪽만 관대하게 한다."**
#    아래 문장은 전부 **운영 원장에서 그대로 가져온 것**이다. 지어내지 않았다.

#: 구분자가 `—` 가 아니라 `,` 였다.
REAL_COMMA = ("홈 라인업 주전 3명(Ohtani·Muncy·Rortvedt) 결장 vs 원정 주전 "
              "2명(Burleson·Gorman) 결장 — 순 1명 차이로 저득점 방향이 홈에 "
              "소폭 더 불리, 발생 시 원정 방향 약 1.5%p · 현재 p에 -1.5%p "
              "기반영 · 근거 자료6")
#: 구분자가 `→` 였다.
REAL_ARROW = ("홈 선발 김진욱 기복 위험 — 직전 등판 4.33이닝 7실점, 5경기 중 "
              "2경기 6실점 이상 → 발생 시 홈 방향 약 5%p · 현재 p에 3%p "
              "기반영 · 근거 자료4")
#: `약` 이 없었다.
REAL_NO_APPROX = ("손성빈 손목 부상으로 타선 한 자리 약화 가능성 — 발생 시 "
                  "home 방향 -2%p · 현재 p에 -2%p 기반영 · 근거 자료2")
#: `발생 시` 가 아니라 `재현 시` 였다 (같은 형태 10건).
REAL_RECUR = ("ジャクソン 직전 등판 4이닝 6실점 부진 재현 시 홈 방향 약 3%p · "
              "현재 p에 2%p 기반영 · 근거 자료4")
#: `현재 p에` 자리를 다른 말로 채웠다 (2026-09-08 KBO 실측).
REAL_NO_CURP = ("박시원의 투구수 누적 및 4이닝 미만 조기 강판 리스크 — 발생 시 "
                "원정 방향 약 4%p · 근거 없음 — 보수 반영 1.5%p 기반영 · "
                "근거 자료4")


@pytest.mark.parametrize("text,side,n,m", [
    (REAL_COMMA, "away", 1.5, -1.5),
    (REAL_ARROW, "home", 5.0, 3.0),
    (REAL_NO_APPROX, "home", -2.0, -2.0),
    (REAL_RECUR, "home", 3.0, 2.0),
    (REAL_NO_CURP, "away", 4.0, 1.5),
])
def test_운영에서_실제로_온_문장을_버리지_않는다(text, side, n, m):
    """🔴 실패하면 그 변수는 자료14 조사에서 통째로 사라진다."""
    p = parse_variable(text)
    assert p is not None, f"버려졌다: {text[:60]}"
    assert p["side"] == side
    assert p["n"] == n and p["m"] == m


def test_서술형은_여전히_실패한다():
    """⚠️ 반대 위험 — 읽는 쪽을 넓혔다고 정량이 아닌 것을 통과시키면 안 된다.

    형식을 넓히는 것이 아니라 **형식을 어겨도 값을 잃지 않게** 하는 것이다.
    """
    for bad in ("원정 선발 이로운은 선발등판 기록이 0건이라 이닝 소화력 예측 불가",
                "홈 불펜이 피로하다",
                "발생 시 홈 방향 약 3%p",           # 리스크 서술이 없다
                "리스크 — 발생 시 홈 방향 약 3%p"):  # 기반영 칸이 없다
        assert parse_variable(bad) is None, f"통과하면 안 된다: {bad}"


def test_기존_형식의_해석은_한_글자도_바뀌지_않는다():
    """⚠️ 631건이 이미 이 형식으로 파싱되고 있다. 값이 변하면 원장이 흔들린다."""
    assert parse_variable(GOOD) == {
        "risk": "원정 선발 이로운 3이닝 미만 조기 강판", "side": "home",
        "n": 8.0, "m": 3.0, "source": "자료10", "q": None}
    q = parse_variable("리스크 — 발생 시 홈 방향 약 6%p · 발생 확률 35% · "
                       "현재 p에 2%p 기반영 · 근거 자료14")
    assert q["q"] == 35.0 and q["n"] == 6.0 and q["m"] == 2.0


# ── [VAR-1 2026-09-10 사용자 지시] 변수 축 편중 ────────────────────────────
#   🔴 v1.4 동결(판정 프롬프트 문구) **예외**. 사용자 명시 지시 "셋 다 진행해라".
#      실측 2026-09-10 MLB 슬레이트 변수 16건:
#        선발 투수 11건(69%) · 타자 1건(6%) · 환경 0건(0%) · 시장괴리 4건(25%)
#      판정이 스스로 낸 12건 중 11건이 투수였다. 자료가 두꺼운 축(자료4·9·10·14)
#      에서만 뽑은 결과다 — 타자는 자료1·3 뿐이고 환경은 자료11 에 있는데도
#      한 번도 변수가 되지 못했다.

def test_variable_axes_are_not_pitcher_only():
    """프롬프트가 변수 축을 한쪽에 몰지 말라고 지시하는가."""
    from app.engine.prompts import MATCHUP as P

    assert "축" in P and "몰지" in P, "축 편중 금지 지시가 없다"
    for axis in ("불펜", "타선", "환경", "로스터"):
        assert axis in P, f"변수 후보 축에 {axis} 가 없다"


def test_variable_axes_do_not_force_padding():
    """⚠️ 반대 위험 — 축을 채우려 없는 리스크를 지어내면 더 나쁘다."""
    from app.engine.prompts import MATCHUP as P

    assert "억지로" in P or "지어내지" in P, "억지 채움 금지가 없다"
