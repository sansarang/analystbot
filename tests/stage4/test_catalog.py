"""① **카탈로그** 계약 (사용자 설계 2026-10-02).

> 핵심은 ① 카탈로그다. 내 "딥서치"의 8할은 **이 경기에서 뭘 확인해야 하는지 아는
> 것**이다 … 봇이 경기마다 카탈로그 전 유형을 돌린다. 그러면 "무엇을 찾을지"를 모델이
> 정할 필요가 없다. **8B 모델이 제일 못하는 게 바로 그 판단**이라 코드로 뺀다.

🔴 **모델을 부르지 않는 계약이다.** 카탈로그는 코드만으로 돈다 — 그것이 설계의 요점이다.
"""
from __future__ import annotations

import pathlib

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


# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_행사_경기는_승패_마켓을_접는다`

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


# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_우리_보드는_같은_기준선을_두_번_내지_않는다`

# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_미러_가드는_진짜_보드에_아직_필요하다`

# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_무게는_늘_변수_합이고_그_수에_6b_문턱을_쓴다`

# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_보드가_마켓_단위로_묶인다`

# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_한_마켓의_두_쪽에_동시에_이름을_적지_않는다`

# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_라인업_상태가_등급_상한을_정한다`

# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_죽는_갈래가_다른_추천이_여럿이면_하나만_고른다`

# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_같은_방향은_세_줄까지_남는다`

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






# ⚠️ **걷은 시험** — `our_board(drafts=…)`(시나리오로 강팀·줄을 고르던 길)이
#    §1 처분으로 바뀌었다: 강팀은 **격자**가 댄다(`fav=`·`dog=`).
#    🔴 거짓 1.0 계약은 **구조적으로 사라졌다** — 격자가 모든 스코어를 센다.
#    걷은 시험: `test_죽는_시나리오가_0건이면_상한이_가드를_뚫지_않는다`
