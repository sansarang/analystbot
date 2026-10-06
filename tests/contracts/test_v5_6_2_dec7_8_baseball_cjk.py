"""🔴🔴 **결정 ⑦ 야구도 최소 4개 · ⑧ CJK 이름은 열쇠 별칭 + 두 조건**.

사용자 결정 2026-10-04:

> **⑦** v5 §6-2의 **최소 4개는 야구에도 적용**한다. v4 템플릿(**에이스 저득점·
> 불펜 데이·난타전·전날 재현**)이 있으니 **코드 보강으로 채우고**, 2개만 나오면
> `scenario_incomplete`.
>
> **⑧** 한자·가나·로마자 표기를 **같은 팀 열쇠의 별칭**으로 묶어 대조하되,
> **부분 문자열 일치는 2자 이상이고 명단 선수 1명 이상이 같이 나올 때만**
> 인정한다. `広島`가 다른 단어 안에 섞여 통과하는 걸 막는 조건이다.
"""
from __future__ import annotations


# ══════════════════════════════════════════════════════════════════
# ⑦ 야구 — 최소 4개
# ══════════════════════════════════════════════════════════════════

def test_dec7_야구도_최소_4개다():
    """🔴 종목별로 낮추지 않는다 — *"최소 4개는 야구에도 적용"*."""
    from app import rules, scenarios
    assert scenarios.MIN_SCENARIOS >= 4, scenarios.MIN_SCENARIOS
    box = rules.required_min()
    # ⚠️ 종목별 완화가 **없어야** 한다(A 안을 사용자가 안 골랐다)
    assert not isinstance(box, dict), (
        f"🔴 최소 개수를 **종목별로** 뒀다({box}) — 사용자는 *'야구에도 적용'* "
        f"이라고 했다")


def test_dec7_네_템플릿이_선언돼_있다():
    """🔴 사용자가 **이름을 댄 넷**이다 — 내가 고른 것이 아니다."""
    import pathlib

    import yaml
    root = pathlib.Path(__file__).resolve().parents[2]
    box = yaml.safe_load(
        (root / "config" / "scenario_rules.yaml").read_text(encoding="utf-8"))
    said = str(box)
    for name in ("baseball_ace_low", "baseball_bullpen_day",
                 "baseball_slugfest", "baseball_repeat_yesterday"):
        assert name in said, f"🔴 `{name}` 템플릿이 선언에 없다"


def test_dec7_네_템플릿의_조건을_코드가_읽는다():
    """🔴🔴 **코드 보강으로 채운다** — 조건을 못 읽으면 영영 2개다.

    ⚠️ 지금 선언에 *"unread_condition: … 미구현"* 이 적혀 있다 — 그 글자가
       남아 있으면 **읽는 코드가 없다는 뜻**이다.
    """
    import pathlib

    import yaml
    root = pathlib.Path(__file__).resolve().parents[2]
    # ══════════════════════════════════════════════════════════════
    # 🔴 **D46** — 주석이 *"한때 미구현이었다"* 를 설명하는 것과, 선언이
    #    *"읽을 수 없다"* 를 **값으로** 드는 것은 다르다.
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 첫 판은 파일 글자에서 `미구현` 을 찾았고, **내가 쓴 설명 주석**에
    #     걸렸다(파이썬에서 네 번 다친 그 자리다).
    #  🔴 그래서 **값**을 본다: `unread_condition` 이 비어 있어야 한다.
    box = yaml.safe_load(
        (root / "config" / "scenario_rules.yaml").read_text(encoding="utf-8"))
    for name, row in (box.get("direction_templates") or {}).items():
        if not isinstance(row, dict):
            continue
        assert not row.get("unread_condition"), (
            f"🔴 `{name}` 이 아직 *'조건을 읽을 수 없다'* 를 든다: "
            f"{row['unread_condition']}")
    from app import scenarios
    for fn in ("baseball_templates", "bullpen_day", "repeat_yesterday"):
        assert hasattr(scenarios, fn), f"🔴 `scenarios.{fn}` 가 없다"


def test_dec7_둘만_나오면_사유가_남는다():
    """🔴 *"2개만 나오면 `scenario_incomplete`"* — 조용히 넘기지 않는다."""
    from app import reasons
    assert hasattr(reasons.Reason, "SCENARIO_INCOMPLETE")


# ══════════════════════════════════════════════════════════════════
# ⑧ CJK — 열쇠 별칭 + 두 조건
# ══════════════════════════════════════════════════════════════════

def test_dec8_세_표기가_한_열쇠에_묶인다():
    """🔴 한자·가나·로마자가 **같은 팀 열쇠**의 별칭이어야 한다."""
    from app import teamref
    keys = {teamref.key_of(x)[0] for x in
            ("広島東洋カープ", "Hiroshima Toyo Carp")}
    keys.discard("")
    assert len(keys) == 1, (
        f"🔴 한자/로마자 표기가 **다른 열쇠**를 가리킨다: {keys}")








# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **돌연변이가 뚫은 자리를 메운다** (2026-10-04)
# ══════════════════════════════════════════════════════════════════
#
#  M83 `baseball_templates(res, game, varis)` → `pass`   ⚠️ **통과했다**
#  M85 `if len(nm) < 2: continue` → `if False:`          ⚠️ **통과했다**
#
# 🔴 둘 다 *"함수는 보고 **쓰는 곳**은 안 봤다"* 다 — §9-5 가 무효로 보는 꼴.


def test_dec7_M83_보강_경로가_야구_셋을_부른다():
    """🔴🔴 **M83** — 배선을 끊으면 빨개져야 한다(#2).

    ⚠️ 종전 계약은 `hasattr(scenarios, 'baseball_templates')` 만 봤다 —
       🔴 **부르는 곳**을 지워도 통과했다.
    """
    import inspect

    from app import scenarios
    from tests._helpers import strip_docs
    body = strip_docs(inspect.getsource(scenarios.require_set))
    assert "baseball_templates(" in body, (
        "🔴 §6-2 보강(`require_set`)이 **야구 템플릿을 안 부른다** — 안 이어진 "
        "코드는 없는 코드보다 나쁘다(#2)")

    # 🔴 그리고 **실제로 더하나** — 불펜 데이 변수를 주고 센다
    from app import classify
    res = scenarios.Result()
    g = classify.Game(home="H", away="A", sport="baseball", league="MLB",
                      home_id="team:1", away_id="team:2")

    class _V:
        type = "pitcher_state"
        quote = "Milwaukee will use a bullpen day on Saturday"
        claim = ""
        why = ""
    n = scenarios.baseball_templates(res, g, [_V()])
    assert n >= 1, (n, res.notes)
    assert any(d.template_id == "baseball_bullpen_day" for d in res.drafts), \
        [d.template_id for d in res.drafts]


