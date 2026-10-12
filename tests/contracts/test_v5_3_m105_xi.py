"""🔴🔴 **M105~M108 — XI 변수·평균 보정·경기 형식**.

지시서 `docs/fable/archive/2026-10-05_workorder_idn_tha_fixes.md` §3.

> **3-1 확정 XI 를 변수로**(`lineup_intent` 유형, **코드가 생성**)
>  · **수비 숫자**: 포메이션 첫 숫자(`5-3-2`·`3-4-3`), 없으면 XI 포지션 집계.
>    5백 → `favors: goals_down`, 주장 문장 `"{팀} 5백 선발 — 내려앉는 운영"`.
>  · **주전 이탈**: 직전 경기 XI 중 선발에서 빠진 선수 → `absence_att`(공격수·
>    공격형 MF) 또는 `absence_def`. 벤치면 "벤치", 명단에 없으면 "결장".
>  · **복귀**: 직전 경기 징계·부상으로 빠졌다 돌아온 선수 → 그 팀 쪽.
>  🔴 이 셋은 리드·에이전트가 아니라 **코드가 XI 사실에서 만든다**(재현 가능).
>
> **3-2 평균 득점 보정** — 최근 N경기 중 한 경기 득점이 나머지 평균의 **2배
> 이상**이면 그 경기를 뺀 평균을 함께 계산한다. 주장 문장:
> `"평균 3.6골(9-2 방글라데시전 제외 시 2.0)"`. 🔴 시나리오 strength·필수형
> 판정에는 **보정 평균**을 쓴다. 보정이 원 평균보다 **1.0 이상 낮으면 회귀형
> (저득점) 시나리오 필수**.
>
> **3-3 경기 형식** — `match_format`: `league|group|knockout_single|
> knockout_two_leg_1st|knockout_two_leg_2nd|final_single|friendly` +
> `extra_time: bool`·`penalties: bool`. 모르면 `unknown`(지어내지 않는다).
> 🔴 `final_single`·`knockout_single`·`knockout_two_leg_1st` 이면 **90분
> 무승부(0-0·1-1) 시나리오 필수**.
"""
from __future__ import annotations

import ast
import inspect
from datetime import datetime, timezone


# ══════════════════════════════════════════════════════════════════
# M105 — 5백 XI → `goals_down` 변수(확정 XI 면 hard)
# ══════════════════════════════════════════════════════════════════






# ══════════════════════════════════════════════════════════════════
# M106 — 직전 XI 주전이 벤치면 `absence` 변수(그 팀 **반대쪽** favors)
# ══════════════════════════════════════════════════════════════════




# ══════════════════════════════════════════════════════════════════
# M107 — 이상치 경기를 뺀 보정 평균 · 1.0 이상 낮으면 회귀 필수
# ══════════════════════════════════════════════════════════════════
def test_M107_이상치를_뺀_보정_평균():
    from app.collect import fotmob
    assert hasattr(fotmob, "trimmed_avg"), (
        "🔴 `fotmob.trimmed_avg(득점들)` 이 없다")
    # 🔴 인도네시아 실측: 9-2 한 경기(9골)가 평균을 끌어올렸다
    got, why = fotmob.trimmed_avg([9, 1, 2, 1, 3])
    assert abs(got - 1.75) < 0.01, (got, why)
    assert "9" in why, why
    # 🔴 이상치가 없으면 **원 평균 그대로**이고 사유는 빈 글
    same, why2 = fotmob.trimmed_avg([2, 2, 3, 1, 2])
    assert abs(same - 2.0) < 0.01 and not why2, (same, why2)
    # ⚠️ 표본이 2개 미만이면 **안 깎는다**
    one, _w = fotmob.trimmed_avg([5])
    assert abs(one - 5.0) < 0.01




# ══════════════════════════════════════════════════════════════════
# M108 — `final_single` 등이면 90분 무승부 시나리오 필수
# ══════════════════════════════════════════════════════════════════
def test_M108_형식이_필수형을_정한다():
    from app import scenarios
    assert hasattr(scenarios, "FORMATS"), "🔴 `scenarios.FORMATS` 가 없다"
    for want in ("league", "group", "knockout_single",
                 "knockout_two_leg_1st", "knockout_two_leg_2nd",
                 "final_single", "friendly", "unknown"):
        assert want in scenarios.FORMATS, f"🔴 `{want}` 가 없다"
    assert hasattr(scenarios, "draw_needed")
    for fmt in ("final_single", "knockout_single", "knockout_two_leg_1st"):
        need, why = scenarios.draw_needed(fmt)
        assert need, f"🔴 `{fmt}` 인데 90분 무승부가 필수가 아니다: {why}"
        assert "연장" in why or "승부차기" in why, why
    for fmt in ("league", "group", "friendly", "unknown"):
        assert not scenarios.draw_needed(fmt)[0], fmt




# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_M108_보강이_불가능하면_막는다`

def test_M108_형식을_경기_페이지에서_읽는다():
    """🔴🔴 **①-1 실사고** — 재료가 있는데 안 읽었다(실측 2026-10-05).

    fotmob `6232991`(인도네시아–태국 결승) 페이지가 `"roundName":"final"` 을
    **명시**하는데 `games.round_note` 가 `None` 이었다. 🔴 그래서 형식이
    `unknown` 이고 90분 무승부 필수형이 **한 번도 발동하지 못했다.**
    """
    from app import scenarios
    from app.collect import fotmob
    # ① 수집기가 그 칸을 읽는가 — **페이지 꼴 그대로** 돌려서 본다
    page = {"props": {"pageProps": {"content": {"matchFacts": {"infoBox": {
        "Tournament": {"leagueName": "FIFA ASEAN Cup Premier Division",
                       "roundName": "final", "round": "final"}}}}}}}
    assert fotmob.round_note(page) == "final", fotmob.round_note(page)
    assert fotmob.round_note({}) == "", "🔴 못 읽으면 빈 문자열이어야 한다"
    # ② 그 글자가 형식이 되는가
    got, why = scenarios.match_format(
        round_note="final", competition="FIFA ASEAN Cup Premier Division")
    assert got == "final_single", (got, why)
    assert scenarios.draw_needed(got)[0], "🔴 그 형식이 필수형을 안 켠다"
    # ③ **지어내지 않는다** — 리그 라운드 번호는 형식이 아니다
    num, why2 = scenarios.match_format(round_note="1",
                                       competition="USL Championship")
    assert num == "unknown", (num, why2)
    assert "모른다" in why2, why2
    # ④ `semi-final` 이 `final` 로 새지 않는다(글자 포함 함정)
    semi, _ = scenarios.match_format(round_note="Semi-final", competition="x")
    assert semi == "knockout_single", semi




# ══════════════════════════════════════════════════════════════════
# 🔴 **배선**(#2) — 안 이은 코드는 없는 코드보다 나쁘다
# ══════════════════════════════════════════════════════════════════


def test_배선_폼이_보정_평균을_싣는다():
    from app.collect import fotmob
    src = inspect.getsource(fotmob)
    assert '"recent_trimmed_avg"' in src, (
        "🔴 폼 사실에 `recent_trimmed_avg` 칸이 없다 — 보정 평균이 판정에 "
        "닿을 길이 없다(지시서 §3-2)")
    assert "trimmed_why" in src, (
        "🔴 보정 **사유**를 안 싣는다 — 카드가 *'9-2 제외 시'* 를 못 적는다(#3)")


