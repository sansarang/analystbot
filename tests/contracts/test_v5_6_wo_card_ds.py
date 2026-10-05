"""🔴🔴 **지시 ②③④ — 가설은 문장, 시나리오는 DeepSeek 것, 난타전 필수.**

사용자 지시 2026-10-05 (카드 불합격):

> **2. 가설을 문장으로**: 팀별로 *"이긴다면 왜(변수 번호)"* + *"무너지는 조건
>    (변수 번호)"* 을 **DeepSeek `HypoOutput.hypotheses`** 에서 받아 카드에
>    **문장으로** 출력.
>
> **3. 카드 시나리오 = DeepSeek 시나리오.** 각 시나리오에 `driver_vars` 번호와
>    `mechanism` **문장**을 출력. 템플릿 시나리오는 **코드 필수형 보강일 때만**,
>    `added_by:code` 표시와 함께. **DeepSeek 시나리오가 카드에 0개면 실패.**
>    **반증(단계 4) 결과도 카드 "반증" 블록에 실제 내용으로.**
>
> **4. 거짓 1.0 계약 실제로 물리게**: 양 팀 최근 평균 득점 **합이 4 이상**이거나
>    **한쪽 평균 3 이상**이면 **난타전(합계 4골+) 시나리오 필수**. 없으면
>    `scenario_incomplete`. **돌연변이로 확인.**

══════════════════════════════════════════════════════════════════
🔴 왜 — 카드가 **수만** 적었다(실측 pn7)
══════════════════════════════════════════════════════════════════

```
■ 5 가설과 무너지는 조건
  Portugal: 근거 6건 · 깨는 변수 2건
      근거: R1(h2h_pattern) · R2(recent_pattern) · …      ← 🔴 **문장이 없다**
■ 6 시나리오
  A ['2-1','1-0'] 근거 3.6 [soccer_home_normal]           ← 🔴 **템플릿**이다
■ 반증
  ⚠️ 반증을 돌렸지만 결과를 못 받았다                        ← 🔴 **내용이 없다**
```

⚠️ 그리고 최근 평균이 **2.8 + 3.4 = 6.2** 였는데 **난타전 시나리오가 없었다** —
   `언더 3.5` 가 **모든 시나리오에서 살아** 1.0 이 됐다. 🔴 그것이 거짓 1.0 이다.
"""
from __future__ import annotations

import pytest


# ══════════════════════════════════════════════════════════════════
# ② 가설을 **문장으로**
# ══════════════════════════════════════════════════════════════════

def test_ds_가설이_문장을_든다():
    """🔴 `Hypothesis` 에 **문장 칸**이 있어야 한다 — 번호만으로는 못 읽는다."""
    import dataclasses

    from app import classify   # ⚠️ `Hypothesis` 는 `classify` 에 있다(재서 고쳤다)
    names = {f.name for f in dataclasses.fields(classify.Hypothesis)}
    for want in ("win_why", "break_why"):
        assert want in names, (
            f"🔴 `Hypothesis.{want}` 가 없다 — *'이긴다면 왜'* 를 담을 자리"
            f"(지시 ②)")


def test_ds_가설_문장이_DeepSeek_에서_온다():
    """🔴 `HypoResult.hypotheses` 의 `reasons`·`breaks` 를 **문장으로** 받는다."""
    from app import analyze
    # 🔴 열쇠는 **자리**다(`home`·`away`) — 팀 이름이 아니다(§8-1 · 지시 ②)
    said = {"home": {"reasons": ["호날두 없이도 홈에서 점유를 쥔다"],
                     "breaks": ["노르웨이 역습에 두 번 뚫리면 흔들린다"]},
            "away": {"reasons": ["홀란이 뒷공간을 한 번만 잡으면 된다"],
                     "breaks": ["전반에 실점하면 되돌릴 자원이 없다"]}}
    # ⚠️ `(이긴다면, 무너지면)` **두 목록**을 돌려준다(재서 고쳤다)
    wins, breaks = analyze.hypo_sentences(said, side="home")
    assert any("점유" in x for x in wins), wins
    assert any("역습" in x for x in breaks), breaks
    # 🔴 **팀 이름으로는 안 찾는다** — 이름을 받는 자리를 늘리지 않는다(§8-1)
    none = analyze.hypo_sentences(said, side="Portugal")
    assert none == ([], []), f"🔴 이름으로도 찾는다: {none}"


def test_ds_카드가_그_문장을_찍는다():
    """🔴 **배선**(#2) — 받아 두고 안 찍으면 없는 것이다."""
    import inspect

    from app import analyze
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(analyze.render))
    i = body.index("■ 5")
    seg = body[i:i + 1600]
    assert "win_why" in seg or "hypo_sentences" in seg, (
        "🔴 카드가 가설 **문장**을 안 찍는다 — 번호만 적는다(지시 ②)")


# ══════════════════════════════════════════════════════════════════
# ③ 카드 시나리오 = **DeepSeek 시나리오**
# ══════════════════════════════════════════════════════════════════

def test_ds_시나리오에_mechanism_과_driver_vars_가_있다():
    """🔴 *"각 시나리오에 `driver_vars` 번호와 `mechanism` 문장을 출력"*."""
    from app import scenarios
    import dataclasses
    names = {f.name for f in dataclasses.fields(scenarios.Draft)}
    for want in ("mechanism", "driver_vars"):
        assert want in names, f"🔴 `Draft.{want}` 가 없다(지시 ③)"


def test_ds_템플릿은_added_by_code_로만():
    """🔴 *"템플릿 시나리오는 **코드 필수형 보강일 때만**, `added_by:code` 표시"*."""
    from app import scenarios
    assert "code" in scenarios.FLOOR_ORIGINS, scenarios.FLOOR_ORIGINS
    # 🔴 `template` 은 **DeepSeek 가 꺼졌을 때의 퇴로**다 — 그 사실이 적혀야 한다
    import inspect

    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(scenarios))
    assert "added_by" in body


def test_ds_DeepSeek_시나리오가_0개면_실패로_적는다():
    """🔴🔴 *"DeepSeek 시나리오가 카드에 **0개면 실패**"*.

    ⚠️ 조용히 템플릿으로 때우지 않는다 — 그러면 카드가 *"분석했다"* 고 거짓말한다.
    """
    from app import reasons
    assert hasattr(reasons.Reason, "DEEPSEEK_NO_SCENARIO"), (
        "🔴 `Reason.DEEPSEEK_NO_SCENARIO` 가 없다 — 0개를 **이름으로** 남겨라")


def test_ds_반증_블록이_실내용을_낸다():
    """🔴 *"반증(단계 4) 결과도 카드 '반증' 블록에 **실제 내용으로**"*."""
    from app import redteam
    assert hasattr(redteam, "card_line"), "🔴 `redteam.card_line` 이 없다"
    # ⚠️ `card_line` 은 **인자 여럿**을 받는다(재서 고쳤다): 마켓·상태·생존 전후.
    said = redteam.card_line("언더 2.5", "covered", before=0.80, after=0.80,
                             by=["E 2-2"])
    assert "언더 2.5" in said and "covered" in said and "0.80" in said, said
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **제안이 오면 그 글이 보여야** 한다 — 지시 ③ (2026-10-05)
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 pn8: 반증 블록이 `(추가 없음)` + `covered` 줄만 냈다 — **제안의
    #     전개 문장이 없었다.**
    got = redteam.card_line("잉글랜드 무패", "proposed", before=0.85,
                            after=0.85, by=["RT1"])
    assert "proposed" in got and "RT1" in got, got
    # 🔴 그리고 **카드가 그 줄을 쓴다**(#2 배선)
    import inspect

    from app import analyze
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(analyze))
    assert "card_line(" in body or "redteam" in body, (
        "🔴 카드가 반증 줄을 **안 만든다**(#2 배선)")


# ══════════════════════════════════════════════════════════════════
# ④ **거짓 1.0** — 난타전 필수
# ══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("home_avg,away_avg,need", [
    (2.8, 3.4, True),     # 🔴 합 6.2 — 실측 pn7 의 그 값
    (2.0, 2.0, True),     # 🔴 합 4.0 — 경계(이상)
    (1.5, 2.0, False),    # 합 3.5 — 아니다
    (3.0, 0.5, True),     # 🔴 한쪽 3.0 — 경계(이상)
    (2.9, 0.5, False),    # 아니다
])
def test_ds_난타전이_필요한가(home_avg, away_avg, need):
    """🔴 *"합이 **4 이상** 이거나 **한쪽 평균 3 이상**이면 난타전 필수"*."""
    from app import scenarios
    got, why = scenarios.slugfest_needed(home_avg=home_avg, away_avg=away_avg)
    assert got is need, (home_avg, away_avg, why)
    assert why, "🔴 **조용히** 판단하지 않는다(#3) — 사유를 적어라"


def test_ds_난타전이_없으면_불완전이다():
    """🔴🔴 **거짓 1.0 을 막는 자리다** — 실측: `언더 3.5` 가 1.0 이었다."""
    from app import classify, scenarios
    res = scenarios.Result()
    # 🔴 **합계 4골 이상**인 스코어가 **하나도 없는** 세트
    res.drafts = [
        scenarios.Draft(id="A", scores=["2-1", "1-0"], strength=3.6,
                        template_id="t", why="홈", variables=["V"],
                        added_by="template"),
        scenarios.Draft(id="B", scores=["0-1", "1-2"], strength=0.8,
                        template_id="t", why="원정", variables=["V"],
                        added_by="template")]
    g = classify.Game(home="Portugal", away="Norway", sport="soccer",
                      league="UNL", home_id="team:1", away_id="team:2")
    scenarios.require_slugfest(res, g, home_avg=2.8, away_avg=3.4)
    assert res.incomplete is True, (
        "🔴 난타전이 없는데 **완전하다**고 했다 — `언더 3.5` 가 공짜로 1.0 을 "
        "받는다(§6-7)")
    assert any("난타전" in x for x in res.incomplete_why), res.incomplete_why


def test_ds_난타전이_있으면_통과한다():
    """⚠️ 반대쪽 — **있으면** 막지 않는다(막는 일 자체가 목적이 아니다)."""
    from app import classify, scenarios
    res = scenarios.Result()
    res.drafts = [
        scenarios.Draft(id="A", scores=["2-1"], strength=3.6, template_id="t",
                        why="홈", variables=["V"], added_by="template"),
        scenarios.Draft(id="F", scores=["3-2"], strength=0.5, template_id="t",
                        why="난타전", variables=["V"], added_by="required")]
    g = classify.Game(home="P", away="N", sport="soccer", league="UNL",
                      home_id="team:1", away_id="team:2")
    scenarios.require_slugfest(res, g, home_avg=2.8, away_avg=3.4)
    assert res.incomplete is False, res.incomplete_why


def test_ds_난타전_보강이_빌드_경로에서_돈다():
    """🔴 **배선**(#2) — 만들고 안 부르면 없는 코드다."""
    import inspect

    from app import scenarios
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(scenarios))
    calls = [ln for ln in body.splitlines()
             if "require_slugfest(" in ln and "def " not in ln]
    assert calls, (
        "🔴 `require_slugfest` 를 **아무 데서도 안 부른다** — 거짓 1.0 이 "
        "그대로 난다(#2)")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **지나간 패로 판정하지 않는다** — 실측 2026-10-05 (pn10)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실사고: 카드가 *"합계 4골 이상인 스코어가 **하나도 없다**: ['2-1','1-0',…]"*
#     이라고 적고, **바로 아래** 시나리오 `A ['3-1','2-1']` 을 보여 줬다.
#     → 난타전 게이트가 `generate` 안에서 **템플릿**을 보고 돌았고, 그 **뒤에**
#       §3 이 시나리오를 DeepSeek 것으로 갈아 치웠다. 판정이 한 발 늦었다.
#  🔴 그래서 **두 가지를** 건다: ① 게이트는 다시 불릴 수 있다(자기 흔적을 걷는다)
#     ② 교체한 자리가 **그 게이트를 다시 부른다**(#2 배선).
def test_ds_교체_뒤_난타전_게이트가_다시_돈다():
    from app import classify, scenarios
    game = classify.Game(home="Portugal", away="Norway", sport="soccer",
                         league="UEFA Nations League")
    res = scenarios.Result()
    # ① 템플릿 — 4골 합계가 **없다** → `incomplete` 가 선다
    res.drafts = [scenarios.Draft(id="A", scores=["1-0", "0-1"], strength=1.0,
                                  template_id="t", why="w")]
    assert not scenarios.require_slugfest(res, game, home_avg=2.8,
                                          away_avg=3.4)
    assert res.incomplete
    mark_first = [w for w in res.incomplete_why if scenarios.MARK in w]
    assert mark_first, "🔴 난타전 사유에 표식이 없다 — 되돌릴 수 없다"

    # ② DeepSeek 것으로 **갈아 치우고 다시 센다** — 4골이 있으니 사유가 걷혀야
    res.drafts = [scenarios.Draft(id="A", scores=["3-1", "2-1"], strength=2.0,
                                  template_id="deepseek", why="w")]
    assert scenarios.require_slugfest(res, game, home_avg=2.8, away_avg=3.4)
    left = [w for w in res.incomplete_why if scenarios.MARK in w]
    assert not left, (
        f"🔴 교체했는데 **지나간 난타전 사유가 남았다**: {left} — 카드가 "
        f"있는 시나리오를 '없다'고 적는다")


def test_ds_교체_자리가_난타전을_다시_부른다():
    """🔴 **배선**(#2) — `from_deepseek` 로 갈아 치운 뒤 게이트를 다시 부른다."""
    import inspect

    from app import analyze
    from tests._helpers import strip_docs
    src = strip_docs(inspect.getsource(analyze._run_hypo))
    at = src.find("sc.drafts = fresh")
    assert at > 0, "🔴 교체 자리를 못 찾았다 — 이 계약을 고쳐라"
    tail = src[at:]
    assert ("_slugfest_gate" in tail or "require_slugfest" in tail), (
        "🔴 DeepSeek 로 갈아 치운 **뒤에** 난타전 게이트를 다시 안 부른다 — "
        "판정이 지나간 패를 본다(실측 pn10)")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **전개 문장이 카드 줄에 실린다** — 지시 ③ (2026-10-05)
# ══════════════════════════════════════════════════════════════════
#
#  > 각 시나리오에 `driver_vars` 번호와 `mechanism` **문장**을 출력.
#
#  ⚠️ 실측 pn10: 카드 줄이 *"v5-A §3 DeepSeek — 근거 변수 ['R5','R7',…]"* 였다 —
#     **번호만** 있고 *"그 변수들이 어떻게 작동해 그 결과가 나오나"* 가 없었다.
#     🔴 M92 가 통과해서 이 계약이 **없다는 것**이 드러났다(§9-5).
def test_ds_시나리오_줄에_전개_문장이_실린다():
    from app import classify, scenarios
    game = classify.Game(home="Portugal", away="Norway", sport="soccer",
                         league="UEFA Nations League")
    말 = "공백을 Ramos 가 메워 전방이 유지되고 노르웨이 수비가 늦는다"
    got = scenarios.from_deepseek(
        [{"id": "A", "driver_vars": ["R1", "R2"], "mechanism": 말,
          "outcomes": [[3, 1]], "type": "normal"}], game)
    assert got, "🔴 DeepSeek 한 줄에서 시나리오가 안 나왔다"
    assert 말 in got[0].why, (
        f"🔴 카드가 찍는 줄(`why`)에 **전개 문장이 없다**: {got[0].why!r}")
    assert "R1" in got[0].why, "🔴 근거 변수 번호도 함께 있어야 한다"
    # 🔴 **mechanism 이 비면 그 사실을 적는다**(#3 조용한 0 금지)
    none = scenarios.from_deepseek(
        [{"id": "A", "driver_vars": ["R1"], "mechanism": "",
          "outcomes": [[1, 0]], "type": "normal"}], game)
    assert none and ("안 줬다" in none[0].why or "없" in none[0].why), (
        f"🔴 `mechanism` 이 비었는데 **조용히** 넘어갔다: {none[0].why!r}")
    # 🔴 **배선**(#2) — 카드 렌더러가 그 줄을 찍는다
    import inspect

    from app import analyze
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(analyze))
    assert ".why" in body, "🔴 렌더러가 시나리오 `why` 를 안 찍는다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **가설은 문장이다** — 지시 ② (2026-10-05)
# ══════════════════════════════════════════════════════════════════
#
#  > 가설은 **문장**으로 — DeepSeek `HypoOutput.hypotheses` 에서.
#
#  ⚠️ 실측 pn10: 카드가 `이긴다면: R1` / `무너지면: R3` 을 찍었다 — DeepSeek 가
#     `reasons: ["R1","R2"]` 로 **번호만** 줬고 코드가 그것을 문장 자리에
#     그대로 찍었다. 🔴 프롬프트만 고치면 모델이 또 번호를 줄 때 같은 카드가
#     나간다 — **코드가 막는다.**
def test_ds_가설_번호만_오면_문장_자리에_안_찍는다():
    from app import analyze
    assert not analyze.is_sentence("R1")
    assert not analyze.is_sentence("R4, R10")
    assert not analyze.is_sentence("['R1']")
    assert analyze.is_sentence("공백을 Ramos 가 메워 전방이 유지된다(R4, R10)"), (
        "🔴 번호가 **들어 있는 문장**은 문장이다 — 그것까지 버리면 안 된다")
    wins, breaks = analyze.hypo_sentences(
        {"home": {"reasons": ["R1", "문장이다(R2)"], "breaks": ["R4"]}},
        side="home")
    assert wins == ["문장이다(R2)"], wins
    assert breaks == [], breaks


def test_ds_가설_버린_수를_카드가_적는다(monkeypatch):
    """🔴 **조용히 버리지 않는다**(#3) — 몇 개가 번호뿐이었나를 적는다.

    ⚠️ 이 계약은 **돌려서** 본다. 종전엔 `_run_hypo` 원문에 `"번호"`·
       `"notes.append"` 가 있나만 봤다 — 🔴 M95(적는 줄을 `_ = (` 로 죽이기)가
       **통과했다**: 두 글자가 파일 다른 자리에 있어 검사가 못 알아챘다(D46).
    """
    from app import analyze, classify, hypo, scenarios
    from app.reasons import Reason

    game = classify.Game(home="Portugal", away="Norway", sport="soccer",
                         league="UEFA Nations League")
    card = analyze.Card(game=game)
    card.hypotheses = [classify.Hypothesis(team="Portugal", side="home")]
    card.variables = []
    card.form = {}

    def fake(inp, **kw):
        return hypo.HypoResult(
            reason=Reason.OK, why="대역",
            hypotheses={"home": {"reasons": ["R1", "R2"],
                                 "breaks": ["R4"]}},
            scenarios=[{"id": "A", "driver_vars": ["R1"],
                        "mechanism": "전개 문장이다",
                        "outcomes": [[3, 1]], "type": "normal"}])
    monkeypatch.setattr(hypo, "run", fake)

    sc = scenarios.Result()
    analyze._run_hypo(card, game, [], None, sc)
    said = [n for n in (sc.notes or []) if "번호" in str(n)]
    assert said, (
        f"🔴 번호만 온 가설 **3개**를 조용히 버렸다 — 카드 노트에 그 수가 "
        f"없다: {list(sc.notes or [])}")
    assert "3" in " ".join(said), f"🔴 버린 수가 안 적혔다: {said}"
    h = card.hypotheses[0]
    assert not (h.win_why or h.break_why), (
        f"🔴 번호를 문장 자리에 **그대로 찍었다**: {h.win_why} {h.break_why}")


def test_ds_프롬프트가_문장을_요구한다():
    """🔴 그리고 **묻는 말**도 고친다 — 코드 방벽만으로는 빈 가설이 된다."""
    from app import hypo
    said = hypo.system_prompt()
    assert said, "🔴 프롬프트가 비었다"
    assert "한 문장" in said and "ID 만 적으면" in said, (
        "🔴 프롬프트가 `reasons`·`breaks` 를 **문장으로** 요구하지 않는다")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **사유 없는 `incomplete` 는 없다** — 실측 2026-10-05 (pn11)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실사고: 난타전 재평가가 **통과**(`['B','E']`)했는데도 카드가
#     `🔴🔴 §6-2 scenario_incomplete — 등급을 내지 않는다` 를 **사유 한 줄 없이**
#     찍었다 — 사유는 걷혔고 **깃발만 남았다**. 등급 0 의 까닭이 사라졌다(#3).
#  🔴 그래서 깃발은 **사유에서 자란다**: 사유가 비면 깃발도 내려간다.
def test_난타전_통과하면_깃발도_내려간다():
    from app import classify, scenarios
    game = classify.Game(home="Portugal", away="Norway", sport="soccer",
                         league="UEFA Nations League")
    res = scenarios.Result()
    res.drafts = [scenarios.Draft(id="A", scores=["1-0"], strength=1.0,
                                  template_id="t", why="w")]
    assert not scenarios.require_slugfest(res, game, home_avg=2.8, away_avg=3.4)
    assert res.incomplete and res.incomplete_why
    res.drafts = [scenarios.Draft(id="A", scores=["3-2"], strength=2.0,
                                  template_id="deepseek", why="w")]
    assert scenarios.require_slugfest(res, game, home_avg=2.8, away_avg=3.4)
    assert not res.incomplete_why, res.incomplete_why
    assert not res.incomplete, (
        "🔴 사유는 걷혔는데 **깃발이 남았다** — 카드가 까닭 없이 "
        "`scenario_incomplete` 를 찍는다(실측 pn11)")


def test_깃발이_서면_사유가_반드시_있다():
    """🔴 **불변식** — `incomplete` 를 세우는 자리는 사유를 함께 적는다(#3)."""
    import ast
    import inspect

    from app import scenarios
    tree = ast.parse(inspect.getsource(scenarios))
    bad = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = ast.dump(fn)
        if "attr='incomplete', ctx=Store" not in body:
            continue
        if "incomplete_why" not in body:
            bad.append(fn.name)
    assert not bad, (
        f"🔴 사유 없이 `incomplete` 를 세우는 함수: {bad} — 등급 0 의 까닭이 "
        f"카드에서 사라진다(#3 조용한 0 금지)")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **반증 블록은 실내용을 낸다** — 지시 ③ (2026-10-05)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측 pn15: 블록이 `(추가 없음)` 한 줄이었다 — 독자가 *"모델이 0개를
#     냈나, 다 폐기됐나, 단계가 안 돌았나"* 를 **구별할 수 없다**(#3).
#  🔴 셋은 고칠 곳이 다르다: 0개면 프롬프트, 폐기면 검증층, 안 돌았으면 설정.
def test_반증_빈_블록이_까닭을_적는다():
    from app import judgeorder
    out = judgeorder.Outcome(steps=("반증",))
    out.survival_before = {"언더 3.5": 0.63}
    out.survival_after = {"언더 3.5": 0.63}
    out.added = []
    out.dropped = [{"id": "RT1", "why": "입력 밖 고유명사"}]
    said = " ".join(judgeorder.card_block(out))
    assert "폐기" in said and "RT1" in said, (
        f"🔴 폐기한 제안을 **안 적는다** — 고칠 곳이 검증층인지 프롬프트인지 "
        f"알 수 없다: {said!r}")
    # 🔴 **배선**(#2) — `redteam` 이 센 폐기를 `Outcome` 이 실어 온다.
    #    ⚠️ M101(싣는 줄을 죽이기)이 **통과했다** — 블록만 보면 이 줄이
    #       비어 있어도 초록이다(대역이 직접 채웠으니).
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(judgeorder))
    hit = [n for n in ast.walk(tree)
           if isinstance(n, ast.Attribute) and n.attr == "dropped"
           and isinstance(n.ctx, ast.Store)]
    assert hit, (
        "🔴 `Outcome.dropped` 에 **아무도 안 싣는다** — 카드가 늘 "
        "*'모델이 0개 냈다'* 로 적는다(실측 M101)")
    out.dropped = []
    bare = " ".join(judgeorder.card_block(out))
    assert "0개" in bare or "내지 않았다" in bare, (
        f"🔴 모델이 0개를 낸 것과 다 폐기된 것이 같은 글이다: {bare!r}")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **반증 제안도 `Draft` 로 섞는다** — 실측 2026-10-05 (pn16)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실사고: `redteam.merge` 가 모델이 준 **dict** 를 시나리오 목록에 그대로
#     붙였고, 바로 뒤 재대입(`grade`)이 `d.strength` 를 읽다 터졌다 —
#     `'dict' object has no attribute 'strength'`. 🔴 카드는 *"반증을 돌렸지만
#     결과를 못 받았다"* 로 **삼켰다**: 모델이 제안을 **낼 때만** 도는 줄이라
#     제안 0개였던 판에서는 보이지 않았다.
#  🔴 그래서 섞는 자리에서 **꼴을 맞춘다** — 뒤에서 `getattr` 로 더듬지 않는다.
def test_반증_제안이_시나리오_꼴로_섞인다():
    from app import redteam, scenarios
    have = [scenarios.Draft(id="A", scores=["1-0"], strength=1.0,
                            template_id="t", why="w")]
    said = redteam.merge(have, [{"id": "RT1", "scores": ["3-3"],
                                 "why": "난타전", "strength": 2}])
    assert len(said) == 2, said
    for d in said:
        assert hasattr(d, "strength") and hasattr(d, "scores"), (
            f"🔴 `dict` 가 그대로 섞였다({type(d).__name__}) — 재대입이 "
            f"`d.strength` 에서 터진다(실측 pn16)")
    # 🔴 **스코어가 없으면 섞지 않는다** — 대입할 수 없는 줄은 생존을 왜곡한다
    bad = redteam.merge(have, [{"id": "RT2", "why": "스코어 없다"}])
    assert len(bad) == 1, f"🔴 스코어 없는 제안을 섞었다: {bad}"


def test_반증_제안이_outcomes_로_와도_섞인다():
    """🔴 꼴이 **둘**이다 — 프롬프트는 `outcomes`, 검증층 뒤는 `scores`.

    ⚠️ 실사고 2026-10-05: `scores` 만 받아 `outcomes` 제안이 **조용히 사라졌다**
       — 기존 계약(§4 추가만 가능)이 그것을 잡았다.
    """
    from app import redteam, scenarios
    have = [scenarios.Draft(id="A", scores=["1-0"], strength=1.0,
                            template_id="t", why="w")]
    said = redteam.merge(have, [{"id": "RT1", "outcomes": [[2, 2]],
                                 "why": "양팀 득점"}])
    assert len(said) == 2, said
    assert "2-2" in said[-1].scores, said[-1].scores
