"""🔴🔴 **v5 §9-2·§9-4 — 남은 M 들.** M15·M16·M17·M23·M27·M32.

§9-2 원문(v4 §15 그대로):

> … **M15 `source_url` 필수** · **M16 날씨 수치 없으면 soft** ·
> **M17 몰수 상대전 제외** · … · **M23 `def` 결장 상향 부착** · …

§9-4 원문:

> **M27** 콜롬비아–파라과이 0-1 (10-03) — h2h·팁 사이트 숫자로 시나리오 약화
> 금지, 중립 친선 실험 팀 무패 상한 0.8
> **M32** 한일전 총점 1.5 vs 내 3.5 (10-03) — 보드 없는 분석은 종목별 기준선
> 복수 대입, 보드 오면 무효

⚠️ M1~M14·M18~M26·M28~M31·M33~M40 은 다른 파일이 든다(이름에 번호가 있다).
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]




def test_v5_9_2_날씨_수치가_없으면_soft_다_M16():
    """🔴 M16 — *"날씨 수치 없으면 soft"*.

    ⚠️ *"비가 온다"* 는 말과 *"강수 8mm"* 는 다르다. 🔴 수가 없으면 hard 로
       쓸 수 없다 — 그 변수가 얼마나 센지 모른다.
    """
    from app import rules
    cfg = rules.variable_types().get("venue_weather") or {}
    said = " ".join(str(v) for v in cfg.values())
    assert "soft" in said, (
        f"🔴 M16 — `venue_weather` 선언이 *수치 없으면 soft* 를 말하지 않는다: "
        f"{sorted(cfg)}")


def test_v5_9_2_몰수_경기는_맞대결에서_뺀다_M17():
    """🔴 M17 — *"몰수 상대전 제외"*.

    ⚠️ 몰수(forfeit)는 **경기가 아니다** — 그 스코어를 맞대결 통계에 넣으면
       평균이 거짓이 된다.
    """
    import inspect

    from app import classify
    src = inspect.getsource(classify)
    assert "몰수" in src or "forfeit" in src.lower(), (
        "🔴 M17 — 맞대결 계산이 몰수 경기를 **말하지 않는다**")


def test_v5_9_2_맞대결_변수가_몰수를_뺀다_M17():
    """🔴🔴 **돌연변이 E 가 통과했다**(2026-10-04).

    `win, forfeits = forfeit_rows(win)` 를 `forfeits = []` 로 바꿔도 **초록**
    이었다 — 내 계약이 *"`몰수` 라는 글자가 코드에 있나"* 만 봤다.
    🔴 **분류를 실제로 돌려** 승패 수가 달라지나 본다.
    """
    from app import classify
    g = classify.Game(home="Hanshin", away="Yomiuri", sport="baseball",
                      league="NPB")
    #: 🔴 넷 중 하나가 **몰수**다 — 그것을 빼면 홈 2승, 안 빼면 3승이다
    rows = [{"home": "Hanshin", "away": "Yomiuri", "home_score": 3,
             "away_score": 1},
            {"home": "Hanshin", "away": "Yomiuri", "home_score": 2,
             "away_score": 0},
            {"home": "Hanshin", "away": "Yomiuri", "home_score": 9,
             "away_score": 0, "note": "몰수 경기"},
            {"home": "Yomiuri", "away": "Hanshin", "home_score": 4,
             "away_score": 1}]
    val = {"matches": rows, "team": "Hanshin"}
    side, why, _ = classify._dir_h2h(val, g)
    assert "몰수 1경기를 **뺐다**" in why, (
        f"🔴 M17 — 맞대결 변수가 몰수를 **안 뺐다**(사유에 없다): {why}")
    # 🔴 그리고 **수가 달라진다** — 안 빼면 홈 3승이다
    assert "2승" in why or "2 승" in why, why


def test_v5_9_2_def_결장은_상향에_붙는다_M23():
    """🔴 M23 — *"`def` 결장 상향 부착"*.

    ⚠️ 수비 결장은 **상대 득점을 올린다** — 그 시나리오에 붙어야 뜻이 있다.
    🔴 그 부착은 §4 선언(`attaches_to`)이 정한다(코드가 짐작하지 않는다).
    """
    from app import rules
    got = rules.attaches_to("def_absence")
    assert got, "🔴 M23 — `def_absence` 에 `attaches_to` 선언이 없다"
    # 🔴 그 규칙이 **난타전/대량득점** 쪽이어야 한다(상향이다)
    rule = rules.cross_rule(str(got))
    said = f"{rule.get('name', '')} {rule.get('then', '')}"
    assert any(w in said for w in ("난타전", "대량", "득점")), (got, said)




def test_v5_9_4_중립_친선_실험팀_무패_상한_M27():
    """🔴 M27 뒷절 — *"중립 친선 실험 팀 무패 상한 0.8"*.

    ⚠️ 중립 구장 친선에서 **실험 중인 팀**은 무엇이든 할 수 있다. 🔴 그 경기의
       무패 마켓에 상한을 건다 — §6-5 가 그 수를 적었다.
    """
    from app import rules
    caps = rules.xi_state_cap().get("caps") or {}
    # 🔴 그 상한(0.8)이 **선언에 있다** — 코드가 짐작하지 않는다
    assert 0.8 in {float(v) for v in caps.values()}, caps


def test_v5_9_4_보드_없으면_기준선_복수_대입_M32():
    """🔴🔴 M32 — *"보드 없는 분석은 종목별 기준선 **복수 대입**, 보드 오면 무효"*.

    ⚠️ 실사고(한일전 10-03): 보드는 총점 **1.5** 였고 내 분석은 **3.5** 였다 —
       한 줄만 대입하면 그 줄이 맞는지 아무도 모른다.
    """
    from app import rules, survive
    # 🔴 **여러 줄**이다(하나가 아니다). ⚠️ `total_lines` 는 **기준선 수**를
    #    받는다(종목이 아니다) — 리그 평균에서 양쪽으로 펼친다(§6-c-3).
    lines = rules.total_lines(8.5)
    assert len(lines) >= 2, lines
    assert len(set(lines)) == len(lines), lines
    assert len(survive.OUR_HANDICAP_LINES) >= 2, survive.OUR_HANDICAP_LINES
    # 🔴 그리고 **"보드 오면 무효"** 꼬리표가 코드에 있다
    import inspect
    assert "보드 오면 무효" in inspect.getsource(survive)


# ── 대역 ──────────────────────────────────────────────────────────




