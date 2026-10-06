"""① **카탈로그** 계약 (사용자 설계 2026-10-02).

> 핵심은 ① 카탈로그다. 내 "딥서치"의 8할은 **이 경기에서 뭘 확인해야 하는지 아는
> 것**이다 … 봇이 경기마다 카탈로그 전 유형을 돌린다. 그러면 "무엇을 찾을지"를 모델이
> 정할 필요가 없다. **8B 모델이 제일 못하는 게 바로 그 판단**이라 코드로 뺀다.

🔴 **모델을 부르지 않는 계약이다.** 카탈로그는 코드만으로 돈다 — 그것이 설계의 요점이다.
"""
from __future__ import annotations

import inspect
from datetime import date, datetime, timezone
from pathlib import Path

from app import cells, classify, queries, rules, scenarios, searchcells
from tests._helpers import strip_docs

ROOT = Path(__file__).resolve().parents[2]
DAY = date(2026, 10, 2)
KICK = datetime(2026, 10, 2, 6, tzinfo=timezone.utc)

#: 사용자가 설계에 적은 다섯. 🔴 **여기 적는 것이 아니라 yaml 에서 읽어야** 하지만,
#  "그 다섯이 실제로 들어왔나"는 이 목록으로만 확인된다(설계문 대조).
DESIGNED = ("coach_conflict", "def_absence", "squad_rotation", "event_match",
            "national_duty_return")


def test_설계한_다섯이_선언과_함께_들어왔다():
    """🔴 v4 §4 표에 **없는** 유형이다 — `home_field` 때와 같은 선언 방식이어야 한다."""
    types = rules.variable_types()
    added = {a["type"]: a for a in rules.added_types()}
    for t in DESIGNED:
        assert t in types, f"{t} 가 유형표에 없다"
        assert t in added, f"{t} 가 선언 없이 더해졌다"
        a = added[t]
        assert a.get("date") and a.get("instruction") and a.get("why")
        # 🔴 근거 문서가 **실재해야** 한다
        assert (ROOT / str(a["doc"])).is_file(), a["doc"]


def test_유형이_자기_템플릿과_작동을_들고_있다():
    """🔴 카탈로그의 세 칸 — `templates`(무엇으로 찾나) · `decides`(판정) ·
    `attaches_to`(작동, 어느 시나리오에 붙나)."""
    types = rules.variable_types()
    for t in DESIGNED:
        v = types[t]
        assert v.get("templates"), f"{t} 에 검색 템플릿이 없다"
        assert v.get("decides"), f"{t} 에 판정 기준이 없다"
        assert v.get("attaches_to"), f"{t} 에 작동(부착)이 없다"
        # 🔴🔴 **자리표 목록은 `queries.TEMPLATE_SLOTS` 하나다**(사본 금지).
        #    ⚠️ 종전엔 여기 손으로 박아 뒀다 — 지시서 2026-10-06 §2 가 이름을
        #       바꾸자(`league`→`comp` · `star`→`player` · `date` 폐지) 이 계약이
        #       **한 발 늦었다.** 🔴 원본에서 자라게 짠다(#1).
        from app import queries as _Q
        import re as _re
        for tpl, lang in rules.type_templates_tagged(t):
            for slot in _re.findall(r"\{([a-z_]+)\}", tpl):
                assert slot in _Q.TEMPLATE_SLOTS, (
                    f"{t}: 모르는 자리표 {slot} — 허용 목록은 "
                    f"{_Q.TEMPLATE_SLOTS} 다(지시서 §2)")











def test_작동이_교차_규칙에_붙는다():
    """🔴 `attaches_to` 가 **실제로 읽히나** — 안 읽으면 그 칸은 장식이다.

    ⚠️ 유형이 아직 미구현이라 지금은 0건이다. **그 사실이 기록에 남아야** 한다 —
       안 남으면 "규칙이 돌았다"로 읽힌다.
    """
    assert rules.attaches_to("def_absence") == "5c-1"
    assert rules.attaches_to("squad_rotation") == "5c-3"
    assert rules.attaches_to("없는유형") == ""
    src = strip_docs(inspect.getsource(scenarios))
    assert "_feeders(" in src and "attaches_to" in src


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **`attaches_to` 의 이름이 전부 읽히나** (2026-10-02)
# ══════════════════════════════════════════════════════════════════
#
# ⚠️ `fold_win_markets`·`invalidate_recent_form` 은 yaml 에 적혀 있기만 하고
#    **읽는 코드가 없었다.** 즉 두 규칙이 장식이었다. 계약이 그것을 못 잡고 있었다 —
#    `attaches_to` 가 비었나만 봤기 때문이다.
# 🔴 그래서 **이름마다 그것을 읽는 코드가 있나**를 본다.


def test_attaches_to_의_모든_이름이_코드에서_읽힌다():
    """🔴 §4 표가 말한 작동은 전부 **부르는 곳이 있어야** 한다.

    ⚠️ D46 — 독스트링·주석을 뺀 **코드만** 본다. 주석이 이름을 *설명하는* 것과
       코드가 그것을 *읽는* 것은 다르다.
    """
    from app import survive
    names = {rules.attaches_to(v) for v in rules.variable_types()}
    names.discard("")
    code = "\n".join(strip_docs(inspect.getsource(m))
                     for m in (scenarios, classify, survive))
    for name in sorted(names):
        if name == "both":
            continue        # 🔴 "두 방향에 다 붙는다" — §5-a 기본이라 특별 코드가 없다
        if name.startswith("5c-"):
            # 🔴 교차 규칙은 `_feeders` 가 `attaches_to` 로 찾는다(위 시험)
            assert "_feeders(" in code, name
            continue
        assert name in code, (
            f"`attaches_to: {name}` 를 읽는 코드가 없다 — 그 규칙은 장식이다")


def test_행사_경기는_승패_마켓을_접는다():
    """🔴 `fold_win_markets` 가 **실제로 등급을 거두나.**"""
    from app import survive
    from app.scenarios import Draft
    g = classify.Game(home="A", away="B", sport="soccer", league="X")
    # ⚠️ **v5 §6-1·§6-6 으로 바뀠다**(2026-10-04): 무게는 **늘 변수 합**이고
    #    `probability` 는 생존에 안 쓰인다. 🔴 그래서 같은 비율을 `strength` 로
    #    준다 — 이 시험의 요점은 **접기**이고 무게 꼴이 아니다.
    #    ⚠️ 접기 **전에** 이름이 붙은 승패 줄이 있어야 뜻이 있으므로 한쪽을
    #       크게 기울인다(0.9 vs 0.1 → `홈 승` 생존 0.9).
    drafts = [Draft(id="A", scores=["2-1", "1-0"], strength=0.9,
                    template_id="t", why="시험"),
              Draft(id="B", scores=["1-2", "0-1"], strength=0.1,
                    template_id="t", why="시험")]
    # 🔴 **라인업 상한을 끈다**(`확정` = 1.0) — 이 시험은 *접기 하나*를 본다.
    #    ⚠️ 안 켜면 상한 0.8 이 먼저 거둬 접기 전에도 이름이 0줄이 된다
    #       (실측 2026-10-04: `홈 승 0.9` 인데 `none`).
    plain = survive.run(drafts, g, standings=None, xi_state="양쪽확정")
    folded = survive.run(drafts, g, standings=None, xi_state="양쪽확정",
                         fold=set(survive.WIN_MARKETS))
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **v5 §6-6 이 `_pick_one` 을 바꿨다**(2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `_pick_one` 이 이제 **생존율 순**으로 고른다. 이 세트에서는 `언더 3.5`
    #     (**1.0**)가 `홈 승`(0.9)을 이겨, 접기 **전에도** 승패 이름이 0줄이다.
    #  🔴 그것은 §6-6 이 옳게 한 일이고 **접기와 무관하다.** 그래서 이 시험은
    #     `_pick_one` 앞의 수(`res.markets`)로 본다 — 접기가 등급을 거뒀나만 묻는다.
    named = [m for m in plain.markets
             if str(m.market_type) in survive.WIN_MARKETS
             and float(m.survival or 0) >= survive.SMALL_AT]
    assert named, (
        "접기 전에 **소액 선을 넘는** 승패 줄이 없다 — 시험이 뜻이 없다: "
        + str([(m.market_type, m.survival) for m in plain.markets]))
    for m in folded.markets:
        if str(m.market_type) in survive.WIN_MARKETS:
            # 🔴 접기 뒤에는 **등급이 없다**
            assert str(m.verdict) == "none", (m.market_type, m.survival,
                                              m.verdict)
            # 🔴 **생존은 그대로 센다** — 지우는 것이 아니라 등급만 거둔다
            assert m.survival is not None
    assert any("fold_win_markets" in n for n in folded.notes), folded.notes


def test_대표팀_복귀는_최근_폼_표본을_무효화한다():
    """🔴 `invalidate_recent_form` 이 **실제로 변수를 내리나.**"""
    items = [
        classify.Classified(text="t", source_url="u", type="recent_pattern",
                            direction="home", hardness="hard", team="A",
                            why="§4 recent_pattern — 3연승"),
        classify.Classified(text="t2", source_url="u", type="recent_pattern",
                            direction="away", hardness="hard", team="B",
                            why="§4 recent_pattern — 2연패"),
        classify.Classified(text="t3", source_url="u",
                            type="national_duty_return",
                            hardness="hard", team="A",
                            why="§4 national_duty_return '방향 없음' (근거: …)"),
    ]
    classify._invalidate_recent(items)
    assert not items[0].is_variable and "invalidate_recent_form" in items[0].undecided
    # 🔴 **상대 팀 폼은 그대로다**
    assert items[1].is_variable and not items[1].undecided


def test_미구현은_이름으로_남고_구현한_것은_방향_규칙이_있다():
    """🔴 yaml 의 `implemented` 와 코드가 **같은 수를 센다.**

    ⚠️ 종전에는 *"다섯 다 아직 방향 규칙이 없다"* 를 못 박고 있었다. 사용자 지시
       2026-10-02(*"한꺼번에 전부다 수정해라"*)로 여덟을 구현하자 이 줄이 빨개졌다 —
       **계약이 상태를 박아 두면 구현이 진전될 때마다 거짓이 된다.** 그래서 박지
       않고 **대조**한다: yaml 이 미구현이라 적은 것만 `NOT_CLASSIFIED` 에 있고,
       구현이라 적은 것은 **방향 규칙이 실재해야** 한다.
    🔴 그것이 *"있는 척"* 을 막는 진짜 조건이다(#7 조용한 0 금지).
    """
    # 🔴 yaml 과 코드가 같은 수를 센다
    assert sorted(classify.NOT_CLASSIFIED) == rules.unimplemented_types()
    for t, why in classify.NOT_CLASSIFIED.items():
        assert len(why) > 10, t
        # ⚠️ 미구현인데 방향 함수가 있으면 둘 중 하나가 거짓말이다
        assert t not in classify.DIRECTION_OF, f"{t} 가 양쪽에 다 있다"
    for t, v in rules.variable_types().items():
        if not v.get("implemented"):
            continue
        assert t in classify.DIRECTION_OF, \
            f"{t} 는 yaml 이 구현이라 적었는데 방향 규칙이 없다"
    # 🔴 설계한 다섯은 **전부 구현됐거나 사유가 있다** — 둘 중 하나여야 한다
    for t in DESIGNED:
        assert t in classify.DIRECTION_OF or t in classify.NOT_CLASSIFIED, t



# ══════════════════════════════════════════════════════════════════
# 🔴 라이브가 찾아낸 셋 — 다시 생기지 않게 못 박는다 (2026-10-02)
# ══════════════════════════════════════════════════════════════════




def test_난타전_템플릿도_종목별이다():
    """🔴 라이브 카드의 시나리오 D 가 야구 경기에 `['2-2','2-3','3-2']
    [soccer_open]` 이었다 — 야구 총점 기준선은 **7.5** 다.
    """
    assert rules.direction_templates("soccer").get("open") == "soccer_open"
    # 🔴 야구는 선언이 `null` 이다 → 격자에서 뽑는다(지어낸 스코어가 아니다)
    assert rules.direction_templates("baseball").get("open") is None
    src = strip_docs(inspect.getsource(scenarios))
    # ⚠️ D46 — 코드가 그 이름을 **박아 쓰지 않는지** 본다
    assert '"soccer_open"' not in src and "'soccer_open'" not in src, \
        "5c-1 이 템플릿 이름을 박아 쓴다 — 종목이 바뀌면 틀린 스코어가 나온다"


def test_깊이_세포는_모았으면_성공이라_적는다():
    """🔴 카드가 *"깊이: unknown"* 으로 나왔는데 사실은 26건이 들어와 있었다.

    ⚠️ 원인: 모은 사실은 `{질문}:{접미사}` 칸으로 가고 질문 자체의 칸은 비어 있다.
       `bb.note` 가 만든 **빈 칸의 기본 상태**(`unknown`)를 읽고 있었다.
    """
    src = strip_docs(inspect.getsource(cells.Cell.run))
    assert "found_any" in src
    # 🔴 `collect_all` 성공 경로가 칸 상태를 읽지 않는다
    head = src.split("found_any:")[-1][:400]
    assert "bb.get(" not in head, head


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **말이 안 되는 결론을 내지 않는다** (사용자 지적 2026-10-03)
# ══════════════════════════════════════════════════════════════════
#
# > 소액: Colombia +1.5 (0.955) … 소액: Paraguay +1.5 (0.955)
# > 이거는 둘다 핸디잖아..말이 안되는 결론이지 않니?
#
# 라이브(콜롬비아 vs 파라과이 친선)가 낸 결론이다. 원인이 **둘**이었다.


def _draft(did, scores, *, strength=1.0, probability=None):
    from app.scenarios import Draft
    return Draft(id=did, scores=scores, strength=strength, template_id="t",
                 why="시험", probability=probability)


def test_우리_보드는_같은_기준선을_두_번_내지_않는다():
    """🔴🔴 **뿌리에서 막는다** — 사용자 결정 2026-10-03 보기 **A**.

    > 핸디는 **A로 간다**...우리 시나리오 weight 큰 쪽에 마이너스

    ⚠️ 종전 `our_board` 는 `(±0.5, ±1.5) × (홈, 원정)` = **여덟 줄**이었다. 같은
       기준선이 **favorite 을 바꿔 두 번** 생겼고, 실측 2026-10-03(엘살바도르 vs
       자메이카)에서 `Jamaica +1.5` 와 `El Salvador +1.5` 가 **똑같이 0.9388** 로
       나와 미러 가드가 둘 다 거뒀다 → 결론이 비었다.
    🔴 이제 기준선마다 **마켓 하나**이고 마이너스는 무게가 큰 쪽이 받는다.
    """
    # ⚠️ 종전엔 `probability=` 로 무게를 줬다 — ②(2026-10-04)로 무게가
    #    **늘 변수 합**이 되어 그 칸은 생존에 안 쓰인다. 🔴 이 시험의 요점은
    #    **보드 모양**이므로 같은 비율을 `strength` 로 준다(뜻은 그대로다).
    from app import survive
    g = classify.Game(home="A", away="B", sport="soccer", league="X")
    # 🔴 B 쪽이 더 무겁다(0.3+0.2 vs 0.3+0.2 는 같으므로 기울여 준다)
    drafts = [_draft("A", ["2-1"], strength=0.2),
              _draft("B", ["1-2"], strength=0.4),
              _draft("D", ["2-0"], strength=0.1),
              _draft("E", ["0-2"], strength=0.3)]
    res = survive.run(drafts, g, standings=None)
    hs = [r for r in res.rows if r["market"].market_type == "handicap"]
    # 🔴 기준선 둘 × 두 쪽 = **네 줄**(여덟 줄이 아니다)
    assert len(hs) == 4, [r["name"] for r in hs]
    plus = {r["market"].team for r in hs if r["market"].line == 1.5}
    minus = {r["market"].team for r in hs if r["market"].line == -1.5}
    # 🔴 **한 기준선에 플러스 한 쪽 · 마이너스 한 쪽**이고 서로 다른 팀이다
    assert len(plus) == 1 and len(minus) == 1 and plus != minus, (plus, minus)
    # 🔴 마이너스는 **무게가 큰 쪽**(B 가 1-2·0-2 로 이긴다)
    assert minus == {"B"}, minus
    assert any("핸디 마이너스는 `B`" in n for n in res.notes), res.notes
    # 🔴🔴 **순환이라는 사실을 카드가 적는다** — 사용자가 알고 고른 길이다
    assert any("순환이다" in n for n in res.notes), res.notes


def test_미러_가드는_진짜_보드에_아직_필요하다():
    """🔴 우리 보드는 이제 쌍을 안 만든다 — 그런데 **북메이커 보드**는 만든다.

    ⚠️ `_mirror_guard` 를 지우면 보드가 있는 경기에서 그 쌍이 다시 돌아온다.
       **뿌리를 고쳤다고 가드를 걷지 않는다** — 들어오는 문이 둘이다.
    """
    # ⚠️ 종전엔 `probability=` 로 무게를 줬다 — ②(2026-10-04)로 무게가
    #    **늘 변수 합**이 되어 그 칸은 생존에 안 쓰인다. 🔴 이 시험의 요점은
    #    **보드 모양**이므로 같은 비율을 `strength` 로 준다(뜻은 그대로다).
    from app import survive
    from app.types import Market
    g = classify.Game(home="A", away="B", sport="soccer", league="X")
    drafts = [_draft("A", ["2-1"], strength=0.3),
              _draft("B", ["1-2"], strength=0.3),
              _draft("D", ["2-0"], strength=0.2),
              _draft("E", ["0-2"], strength=0.2)]
    # 🔴 **보드가 두 쪽을 다 들고 왔다**(실제 북은 그럴 수 있다)
    board = [Market(market_type="handicap", team="A", line=1.5),
             Market(market_type="handicap", team="B", line=1.5)]
    res = survive.run(drafts, g, board=board, standings=None)
    plus = [r for r in res.rows if r["market"].market_type == "handicap"]
    assert len(plus) == 2, plus
    # 🔴 각자 **한 시나리오에만** 죽는다 — 0.8 이라 소액 선을 넘는다
    assert all(abs(r["survival"] - 0.8) < 1e-9 for r in plus), plus
    # 🔴 **그런데 둘 다 거둬졌다**
    assert all(r["verdict"] == "none" for r in plus), plus
    assert any("확정 손실" in n for n in res.notes), res.notes


def test_무게는_늘_변수_합이고_그_수에_6b_문턱을_쓴다():
    """🔴🔴 **뒤집힌 계약**(사용자 결정 2026-10-04 ②).

    ══════════════════════════════════════════════════════════════════
    🔴 종전 계약 — *"확률이 아니면 소액을 주지 않는다"*
    ══════════════════════════════════════════════════════════════════

    전 판은 *"§6-b 의 소액 선(0.8)은 **확률의 선**이고, 격자가 없으면 그 수는
    확률이 아니다"* 라고 적고 `small` 을 전부 거뒀다.

    ⚠️ 그 전제가 ②로 무너졌다. 사용자 결정:

    > v4 §5-a 는 **시나리오 strength = 변수 weight 합**이라고 적혀 있다. 포아송
    > 격자는 **v4 에 없는 봇의 추가물**이고 … 변수 → strength, **이게 생존율을
    > 정한다.** 이렇게 하면 §0 의 "변수 개수·정확도 = 시나리오 품질" 이 코드에서
    > 참이 된다. **지금은 변수가 장식이다.**

    🔴 §6-b(0.8·1.0)와 §5-a(strength)는 **같은 문서의 같은 설계**다 — v4 는 제
       무게에 제 문턱을 쓰라고 적었다. *"0.8 은 확률의 선"* 은 봇이 격자를 들여온
       뒤에 지어낸 단서이고, 격자를 생존에서 뺀 지금 §6-b 를 통째로 막는다.
    ⚠️ **이것은 봇을 느슨하게 만든다** — 그 사실을 숨기지 않는다. 막는 것은
       여전히 넷이다: §5단계 상한 · §7 R6 · M18 · 거짓 1.0 계약.
    """
    from app import survive
    g = classify.Game(home="A", away="B", sport="soccer", league="X")
    drafts = [_draft("A", ["2-1"], strength=0.9),
              _draft("B", ["3-1"], strength=0.1)]
    res = survive.run(drafts, g, standings=None, xi_state="양쪽확정")
    # 🔴 무게는 **늘** 변수 합이다(격자가 1순위가 아니다)
    assert res.weight_mode.startswith("strength"), res.weight_mode
    assert "§5-a" in res.weight_mode, res.weight_mode
    # 🔴 **그 단서가 사라졌다**
    assert not any("확률이 아니다" in n for n in res.notes), res.notes
    # 🔴 홈 쪽 1.0 줄이 **이름을 받는다** — 두 시나리오가 다 홈 승이다
    hs = [r for r in res.rows
          if r["market"].market_type in ("home", "home_dc")]
    assert all(r["survival"] == 1.0 for r in hs), hs
    named = [r for r in hs if r["verdict"] == "name"]
    assert len(named) == 1, [(r["name"], r["verdict"]) for r in hs]
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **②가 드러낸 것 — `_pick_one` 이 이제 실제로 일한다**
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전에는 걷힌 가드가 1.0 아래를 **전부** `none` 으로 만들어 `_pick_one` 이
    #     볼 줄이 하나뿐이었다. 이제 여러 줄이 등급을 갖고, 그중 하나가 뽑힌다.
    #  🔴 뽑히는 것은 `홈 무패`(`home_dc`)다 — `pick_one_when_disjoint.prefer` 의
    #     주석이 *"사용자가 **무패 우선**이라고 적은 것을 그대로 선언으로 옮겼다"*
    #     고 한다. **선언대로**이고 내가 고른 것이 아니다.
    #  ⚠️ 그 순서가 맞는지는 **아직 모른다**(그 주석도 그렇게 적어 뒀다) —
    #     경기 결과가 쌓여야 말할 수 있다.
    # 🔴🔴 **v5 §6-6 이 뒤집었다**(2026-10-04) — *"생존율 높은 순, 동률이면
    #    **더 강한 주장**(승 > 무패 > 핸디 > 총점). **선언 순서로 고르지
    #    않는다**."* ⚠️ 종전엔 `prefer` 선언의 *"무패 우선"* 이 `홈 무패` 를
    #    골랐다 — 둘이 똑같이 1.0 인데 **더 약한 주장**이 뽑혔다.
    assert named[0]["market"].market_type == "home", named[0]
    # 🔴🔴 **0.8~1.0 사이에 소액이 붙는다** — 그것이 ②가 바꾼 것이다.
    #    ⚠️ `_pick_one` 이 거두기 **전**의 수로 본다 — 뽑기 뒤를 보면 늘 한 줄이다.
    raw = [m for m in res.markets if 0.8 <= float(m.survival or 0) < 1.0]
    for m in raw:
        assert survive._verdict(float(m.survival)) == "small", (
            m.market_type, m.survival)


def test_보드가_마켓_단위로_묶인다():
    """🔴🔴 사용자 지적 2026-10-03 — 보드 **구조**가 틀렸다.

    > 핸드 +1.5 두팀다 성립이 안된다는거야..축구는 승무패 **왜 어느 한쪽에만
    > 핸디가 적용된다**..언오버는 토탈이고

    | 마켓 | 쪽 |
    |---|---|
    | 승무패 | 홈 승 · 무승부 · 원정 승 (세 쪽) |
    | 핸디 한 라인 | `X −L` · `Y +L` (**두 쪽 · 여집합**) |
    | 토탈 한 기준선 | 오버 · 언더 (**두 쪽 · 여집합**) |
    """
    from app import survive
    g = classify.Game(home="A", away="B", sport="soccer", league="X")
    # ⚠️ 무게를 **기울인다** — 좌우가 똑같으면 favorite 이 없어 핸디 줄이 아예
    #    안 생긴다(사용자 규칙 A: 동전 던지기로 정하지 않는다). 그 성질은 아래에서
    #    따로 검사한다.
    drafts = [_draft("A", ["2-1"], strength=0.35),
              _draft("B", ["1-2"], strength=0.25),
              _draft("D", ["2-0"], strength=0.2),
              _draft("E", ["0-2"], strength=0.2)]
    res = survive.run(drafts, g, standings=None)
    # 🔴 **무게가 같으면 핸디를 만들지 않는다** — 뜻이 없는 줄을 내지 않는다
    even = survive.run([_draft("A", ["2-1"], strength=0.5),
                        _draft("B", ["1-2"], strength=0.5)],
                       g, standings=None)
    assert not [r for r in even.rows if r["market"].market_type == "handicap"]
    assert any("두 쪽 무게가 **같다**" in n for n in even.notes), even.notes
    groups: dict = {}
    for r in res.rows:
        groups.setdefault(r["market_key"], []).append(r)
    # 🔴 승무패는 **한 마켓**이다(세 쪽 + 더블찬스)
    win = [k for k in groups if k[0] == "win"]
    assert len(win) == 1, win
    # 🔴 핸디는 **라인 × `+` 받는 쪽** 마다 한 마켓이고 **두 쪽**이다
    hand = {k: v for k, v in groups.items() if k[0] == "handicap"}
    assert hand, groups
    for k, rows in hand.items():
        assert len(rows) == 2, (k, [r["name"] for r in rows])
        lines = sorted(float(r["market"].line) for r in rows)
        # 🔴 **한 쪽은 `+`, 다른 쪽은 `−`** — 같은 부호 둘이 한 마켓일 수 없다
        assert lines[0] < 0 < lines[1], (k, lines)
        teams = {r["market"].team for r in rows}
        assert len(teams) == 2, (k, teams)


def test_한_마켓의_두_쪽에_동시에_이름을_적지_않는다():
    """🔴 두 쪽은 **여집합**이다 — 동시에 맞을 수 없다."""
    from app import survive
    g = classify.Game(home="A", away="B", sport="soccer", league="X")
    # 🔴 밀어내기(△)가 생기게 — `±0.5` 는 무승부에서 밀린다
    drafts = [_draft("A", ["1-1"], probability=1.0)]
    res = survive.run(drafts, g, standings=None)
    for r in res.rows:
        if r["market_key"][0] in ("handicap", "total"):
            same = [x for x in res.rows
                    if x["market_key"] == r["market_key"]
                    and x["verdict"] != "none"]
            assert len(same) <= 1, [x["name"] for x in same]


def test_라인업_상태가_등급_상한을_정한다():
    """🔴🔴 **분석 과정 5단계** (사용자 지시 2026-10-03 · 10단계 그림):

    ```
    5. 라인업 상태 → 상한        확정 1.0 / 예상 0.85 / 없음 0.8

    🔴 **v5 §6-5 가 네 칸으로 늘렸다**: 양쪽확정 1.0 / 한쪽확정 0.9 /
       양쪽예상 0.85 / 없음 0.8 (+ 야구 선발확정_타순미공개 0.9 · 선발폼공백 0.85)
    ```

    ⚠️ 종전은 **두 칸**이었다(확정이냐 아니냐 · 0.85). 라인업을 **아예 못 잡은
       경기**와 **예상 XI 를 잡은 경기**가 같은 상한을 받았다 — 모르는 양이 다른데.
    🔴 생존 수는 **그대로 둔다** — 등급만 거둔다.
    """
    from app import rules, survive
    caps = {str(k): float(v) for k, v in rules.xi_state_cap()["caps"].items()}
    # 🔴 **v5 §6-5 가 세 칸을 네 칸으로** 바꿨다(+ 야구 두 칸). 그 표는
    #    `tests/contracts/test_v5_6_5_caps.py` 가 값까지 본다 — 여기는
    #    **순서**만 본다(사본을 만들지 않는다).
    assert {"양쪽확정", "한쪽확정", "양쪽예상", "없음"} <= set(caps), caps
    # 🔴 **사다리가 내려가야 한다** — 모를수록 상한이 세다
    assert (caps["양쪽확정"] > caps["한쪽확정"] > caps["양쪽예상"]
            > caps["없음"]), caps
    g = classify.Game(home="A", away="B", sport="soccer", league="X")
    # 🔴 확률 무게 + 전부 홈 승 → 홈 승 생존 1.0
    drafts = [_draft("A", ["2-1"], probability=0.6),
              _draft("B", ["3-1"], probability=0.4)]

    free = survive.run(drafts, g, standings=None, xi_state="양쪽확정")
    win = next(r for r in free.rows if r["market"].market_type == "home")
    assert win["survival"] == 1.0 and win["verdict"] == "name", win

    for state in ("한쪽확정", "양쪽예상", "없음"):
        capped = survive.run(drafts, g, standings=None, xi_state=state)
        row = next(r for r in capped.rows if r["market"].market_type == "home")
        # 🔴 생존은 그대로, 등급만 내려갔다
        assert row["survival"] == 1.0 and row["verdict"] == "small", (state, row)
        assert any(f"`{state}` → 등급 상한 {caps[state]}" in n
                   for n in capped.notes), (state, capped.notes)

    # ⚠️ **모르면 가장 센 상한**(fail-closed) — 모르는데 푸는 것은 우리에게
    #    유리한 쪽으로 거짓말하는 것이다
    unknown = survive.run(drafts, g, standings=None)
    win3 = next(r for r in unknown.rows if r["market"].market_type == "home")
    assert win3["verdict"] == "small", win3
    assert any("못 쟀다" in n and f"상한 {min(caps.values())}" in n
               for n in unknown.notes), unknown.notes

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **v5 §6-5 가 이 줄을 뒤집었다** — 야구도 적용 종목이다
    # ══════════════════════════════════════════════════════════════════
    #
    #  종전 주석: *"야구는 적용 종목이 아니다(예고 선발이 그 자리다)"*.
    #  🔴 v5 §6-5 가 **야구 칸을 이름으로 댔다**: *"야구는 선발 확정·타순 미공개
    #     0.9, 선발 폼 자료 공백 0.85."* 그래서 `sports` 에 야구가 들어갔고
    #     `없음`(선발을 아예 모른다)도 야구에서 상한을 받는다.
    #  ⚠️ 하키는 §6-5 가 말하지 않았다 — **지어내지 않는다**(안 건다).
    gb = classify.Game(home="A", away="B", sport="baseball", league="NPB")
    bb = survive.run(drafts, gb, standings=None, xi_state="없음")
    winb = next(r for r in bb.rows if r["market"].market_type == "home")
    assert winb["verdict"] == "small", winb
    # 🔴 야구 **자기 칸**이 듣는다
    for state, want in (("선발확정_타순미공개", 0.9), ("선발폼공백", 0.85)):
        got = survive.run(drafts, gb, standings=None, xi_state=state)
        assert any(f"`{state}` → 등급 상한 {want}" in n for n in got.notes), (
            state, got.notes)
    # ⚠️ 하키는 **안 건다** — 그 사실을 사유가 적는다
    gh = classify.Game(home="A", away="B", sport="hockey", league="NHL")
    hh = survive.run(drafts, gh, standings=None, xi_state="없음")
    assert any("적용 종목" in n for n in hh.notes), hh.notes




def test_죽는_갈래가_다른_추천이_여럿이면_하나만_고른다():
    """🔴🔴 사용자 규칙 2026-10-03:

    > 콜롬비아 무패 0.85 … 언더 3.5 0.85 — **둘은 다른 갈래에서 죽으니 하나만
    > 고른다 → 무패 우선**

    ⚠️ `_mirror_guard` 와 다른 문제다 — 그쪽은 **서로를 상쇄**하는 쌍이고, 이쪽은
       둘 다 맞을 수 **있지만** 같이 걸 이유가 없는 쌍이다.
    """
    from app import rules, survive
    cfg = rules.pick_one_cfg()
    # 🔴 `on:` 은 YAML 이 **불리언 키**로 읽는다 — 그래서 `enabled` 다(실측에서
    #    이 규칙이 조용히 꺼져 있었다). 계약이 그 함정을 지킨다.
    assert cfg.get("enabled") and cfg.get("prefer"), cfg
    assert True not in cfg, "yaml 에 `on:` 이 다시 들어왔다 — 불리언 키가 된다"
    g = classify.Game(home="A", away="B", sport="soccer", league="X")
    # 🔴 홈 무패는 C(0-2)에서, 언더 3.5 는 D(3-1)에서 죽는다 — **다른 갈래**다
    drafts = [_draft("A", ["1-0"], strength=0.45),
              _draft("B", ["1-1"], strength=0.3),
              _draft("C", ["0-2"], strength=0.1),
              _draft("D", ["3-1"], strength=0.15)]
    res = survive.run(drafts, g, standings={"total_baseline": 3.5},
                      xi_state="양쪽확정")
    named = [r for r in res.rows if r["verdict"] != "none"]
    assert len(named) <= 1, [r["name"] for r in named]
    if len(named) == 1:
        # 🔴 **승패 쪽을 먼저 고른다**(선언 순서대로 · 사용자 *"무패 우선"*)
        # 🔴 **v5 §6-6** — 선언 순서(`prefer`)가 아니라 **생존율 → 주장 강도**다.
        #    ⚠️ 이 세트에서는 `언더 4.5`(1.0)가 이긴다 — 승패 줄보다 생존이 높다.
        best = max(float(r["survival"]) for r in res.rows)
        assert float(named[0]["survival"]) >= best - 1e-9, (named[0], best)
        assert any("하나만 고른다" in n for n in res.notes), res.notes


def test_같은_방향은_세_줄까지_남는다():
    """🔴🔴 **분석 과정 10단계** (사용자 지시 2026-10-03):

    > 10. 상한·상관 → 결론·방아쇠 — **같은 방향 3개까지**, 확인 항목 첨부

    ⚠️ 이 규칙은 `_pick_one`(*"다른 갈래면 하나만"*)과 **부딪친다** — 그대로 두면
       `_pick_one` 이 먼저 하나만 남겨 10단계가 아무 일도 못 한다.
    🔴 두 지시가 함께 서는 읽기는 하나다: **같은 방향 3줄까지 · 다른 방향 하나만.**
       그 근거는 사용자 자신의 결론이다 — `언더 3.5`(0.85)와 `언더 2.5`(0.8)를
       **둘 다** 적었고 죽는 갈래가 다르다(E / D·E).
    """
    from app import rules, survive
    cap = int(rules.conclusion_cfg()["max_same_direction"])
    assert cap >= 1
    # 🔴 방향은 **마켓 종류가 아니다** — 종류가 달라도 같은 쪽을 말하면 같은 방향
    from app.types import Market
    survive._SIDES = ("A", "B")
    assert survive.direction_of(Market(market_type="home")) == "팀:A"
    assert survive.direction_of(
        Market(market_type="handicap", team="A", line=1.5)) == "팀:A"
    assert survive.direction_of(
        Market(market_type="total", team="under", line=2.5)) == "총점:under"
    assert survive.direction_of(Market(market_type="draw")) == "무승부"

    g = classify.Game(home="A", away="B", sport="soccer", league="X")
    # 🔴 전부 저득점 → **언더가 여러 줄** 살아남는다(같은 방향)
    drafts = [_draft("A", ["1-0"], probability=0.5),
              _draft("B", ["0-0"], probability=0.5)]
    res = survive.run(drafts, g, standings={"total_baseline": 3.5},
                      xi_state="양쪽확정")
    unders = [r for r in res.rows if r["verdict"] != "none"
              and survive.direction_of(r["market"]) == "총점:under"]
    assert len(unders) <= cap, [r["name"] for r in unders]
    # 🔴 거둔 줄이 있으면 **왜 거뒀는지** 적혀 있다(#3 조용한 0 금지)
    tot = [r for r in res.rows
           if survive.direction_of(r["market"]) == "총점:under"]
    if len(tot) > cap:
        assert any("방향으로" in n and "생존 높은" in n for n in res.notes), res.notes
    # ⚠️ 거둔 줄도 **표에는 남는다** — 지우는 것이 아니라 등급만 거둔다(§6-f)
    assert len(tot) == len(rules.total_lines(3.5))


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **별칭 사전 + 검색 사다리** (사용자 기술 지시 2026-10-03 · 기술 1·2)
# ══════════════════════════════════════════════════════════════════
#
# > 내가 잘 찾는 이유의 절반은 팀을 **공식명이 아니라 현지 매체가 부르는 이름**으로
# > 치기 때문이다 … **감독·주장·핵심 선수 이름도 검색어가 된다.** 오늘 자메이카
# > 이탈자 5명은 `Speid` 로 찾았다.


def test_별칭_선언에_출처가_있다():
    """🔴🔴 **지어내지 않는다.** 팀 별칭·감독은 **사실**이다 — 틀리면 검색이 통째로
    엉뚱한 데로 가고 그것이 0건보다 나쁘다(거짓 변수를 만든다).

    ⚠️ 그래서 선언마다 `source:` 를 요구한다(사용자가 준 것 / 실측으로 확인한 것).
    """
    import yaml
    box = yaml.safe_load((ROOT / "config/entities.yaml").read_text(
        encoding="utf-8"))
    teams = box.get("teams") or {}
    assert teams, "선언이 비었다"
    for name, row in teams.items():
        assert str(row.get("source") or "").strip(), f"{name} 에 출처가 없다"
        assert "2026-10-03" in str(row["source"]) or "실측" in str(row["source"])
        # 🔴 별칭은 **언어별**이다 — 언어를 모르면 어느 질의에 넣을지 모른다
        for lang in (row.get("aliases") or {}):
            assert lang in ("en", "es", "ja", "ko", "zh"), (name, lang)


def test_별칭이_선언된_언어가_검색_언어에_들어간다():
    """🔴 실측 2026-10-03 — 파라과이 별칭 `Albirroja` 를 `es` 로 선언했는데 검색
    언어가 `en` 뿐이라 **그 별칭이 한 번도 안 던져졌다.** 선언이 있는데 안 쓰이는
    것이 가장 나쁘다."""
    from app import entities
    assert "es" in entities.langs_of("Paraguay")
    langs, why = queries.langs_for("Friendlies", "Paraguay", "Colombia")
    assert "es" in langs and langs[0] == "en", (langs, why)






def test_별칭으로도_귀속을_본다():
    """🔴 `Albirroja` 만 적힌 기사가 파라과이 기사가 아니라고 하면 그것이 거짓이다."""
    from app import cells
    assert cells._names_match("La Albirroja viaja a Estados Unidos",
                              "Paraguay", None)
    assert not cells._names_match("Mexico friendlies in November",
                                  "Paraguay", None)


def test_현지_매체를_먼저_연다():
    """🔴 `rules.host_rank` 는 **전 지구 공용**이다 — 자메이카 기사를 찾는데
    `espn.com` 과 `jamaica-gleaner.com` 이 같은 등급이면 순서가 운에 달린다."""
    import inspect

    from app import cells, entities
    from tests._helpers import strip_docs
    assert "jamaica-gleaner.com" in entities.outlets_of("Jamaica")
    src = strip_docs(inspect.getsource(cells.Cell._open_hits))
    assert "outlets_of(" in src, "열기 순서가 팀 매체를 안 본다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **종목 게이트가 카탈로그에도 걸린다** (실측 2026-10-03)
# ══════════════════════════════════════════════════════════════════






def test_죽는_시나리오가_0건이면_상한이_가드를_뚫지_않는다():
    """🔴🔴 두 규칙이 **엇갈려** 1.0 짜리 줄이 사라졌다 (실측 2026-10-03).

    엘살바도르 vs 자메이카: `언더 3.5` 가 **다섯 시나리오에서 하나도 안 죽었는데**
    (생존 1.0) 등급이 `none` 이었고 결론이 *"살아남는 마켓 없음"* 이었다.
    🔴 그 문장은 **거짓**이다 — 죽는 시나리오가 0건인 줄이 있었다.

    까닭:
    ```
    ① §5단계 상한(라인업 `양쪽예상` → 0.85)  :  name → small
    ② 확률 가드(무게가 확률이 아니다)      :  small → none
    ```
    ⚠️ 🔴 **②는 2026-10-04 에 걷혔다**(사용자 결정 ②): 무게가 **늘** §5-a 변수
       합이 되었고, §6-b 의 0.8·1.0 은 **그 무게에 쓰는 v4 자신의 문턱**이다.
       *"0.8 은 확률의 선"* 은 봇이 격자를 들여온 뒤에 지어낸 단서였다.
    🔴 그래서 이 시험이 지키는 것은 이제 **하나**다: 상한(①)이 `name` 을 `small`
       로 내려도 **그 `small` 이 살아남는다.** 그것이 그때 사라진 줄이다.
    """
    from app import rules, survive
    g = classify.Game(home="A", away="B", sport="soccer", league="X")
    drafts = [_draft("A", ["1-0"], strength=0.6),
              _draft("B", ["0-0"], strength=0.4)]
    caps = rules.xi_state_cap()["caps"]
    res = survive.run(drafts, g, standings={"total_baseline": 3.5},
                      xi_state="양쪽예상")
    # 🔴 무게는 **늘** 변수 합이다(②)
    assert res.weight_mode.startswith("strength"), res.weight_mode
    u35 = next(r for r in res.rows if r["name"] == "언더 3.5")
    # 🔴 **둘 중 하나도 안 죽었다** — 그 사실이 등급으로 남아야 한다
    assert u35["survival"] == 1.0, u35
    assert u35["verdict"] == "small", u35
    # ⚠️ 걷힌 가드의 사유가 **다시 나타나면** 안 된다
    assert not any("확률이 아니다" in n for n in res.notes), res.notes
    # ⚠️ 그래도 **이름은 못 적는다** — ①의 의심이 남아 있다
    assert float(caps["양쪽예상"]) < 1.0

    # 🔴 생존이 1.0 **미만**이면 가드가 그대로 막는다(바뀐 것은 예외 하나뿐이다)
    o35 = next(r for r in res.rows if r["name"] == "오버 2.5")
    assert o35["survival"] < 1.0
    assert o35["verdict"] == "none", o35
