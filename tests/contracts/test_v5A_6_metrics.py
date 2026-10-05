"""🔴🔴 **v5-A §6 / 작업지시 §5 — 측정.** 켜기 전·후를 **나란히 재서** 판단한다.

v5-A §6 원문:

> DeepSeek 가 적중을 올리는지는 같은 정답지로 켜기 전·후를 나란히 재서
> 판단한다. **감으로 켜지 않는다.**
> ① 기준선 — Solar 단독 → `metrics/baseline_solar.json`
> ② 단계 3 만 켬 → `metrics/stage3.json`
> ③ 단계 3+4 켬 → `metrics/stage34.json`
> ④ `metrics/compare.py` 가 세 파일을 **표로 비교해 보고**한다.

켜는 기준(v5-A §6):

> **결과 갈래 포함률이 오르고**, **오답 재현 수가 줄거나 같고**, **등급 마켓
> 수가 기준선의 70% 이상**이면 단계 3 을 운영에 켠다. 단계 4 는 **거짓 확신
> 수가 줄 때만** 켠다. 기준을 못 넘으면 결과를 `questions/` 에 적고 **사용자
> 판단을 받는다.**

══════════════════════════════════════════════════════════════════
🔴 일곱 지표(v5-A §6 표) — **좋아지는 방향이 다르다**
══════════════════════════════════════════════════════════════════

    필수형 누락률    ↓     결과 갈래 포함률  ↑     거짓 확신 수   ↓
    오답 재현 수     ↓(0)  등급 마켓 수      너무 줄면 경고
    경기당 비용      하루 $3 안              폐기율         20% 넘으면 재조정

⚠️ **방향을 코드에 박지 않는다** — `metrics/spec.yaml` 이 든다.
"""
from __future__ import annotations

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _spec() -> dict:
    from metrics import compare
    return compare.spec()


def test_v5A_6_일곱_지표가_선언돼_있다():
    """🔴 v5-A §6 표의 **일곱 지표** 전부. ⚠️ 이름을 코드에 박지 않는다."""
    got = _spec()["metrics"]
    want = {"required_missing_rate", "outcome_hit_rate", "false_confidence",
            "wrong_repro", "graded_markets", "usd_per_match", "drop_rate"}
    assert want <= set(got), sorted(set(want) - set(got))
    for name, row in got.items():
        assert row.get("direction") in ("down", "up", "watch"), (name, row)
        assert str(row.get("means") or "").strip(), name


def test_v5A_6_켜는_기준이_선언돼_있다():
    """🔴 *"감으로 켜지 않는다"* — 기준이 **수로** 적혀 있어야 한다."""
    g = _spec()["gates"]
    s3 = g["stage3"]
    # 🔴 결과 갈래 포함률 **상승** · 오답 재현 **줄거나 같고** · 등급 마켓 **70%+**
    assert s3["outcome_hit_rate"] == "up"
    assert s3["wrong_repro"] in ("down", "same_or_down")
    assert float(s3["graded_markets_min_ratio"]) == 0.70
    # 🔴 단계 4 는 **거짓 확신 수가 줄 때만**
    assert g["stage4"]["false_confidence"] in ("down", "same_or_down")


def test_v5A_6_세_파일_이름이_지시서_그대로다():
    """🔴 `baseline_solar.json` · `stage3.json` · `stage34.json`(§5-2~§5-4)."""
    from metrics import compare
    assert compare.FILES == ("baseline_solar.json", "stage3.json",
                             "stage34.json")


def test_v5A_6_없는_파일을_0_으로_때우지_않는다():
    """🔴🔴 **조용한 0 금지**(#3) — 안 잰 것과 0 을 가른다.

    ⚠️ 기준선을 안 재고 비교하면 *"올랐다"* 가 거짓이 된다.
    """
    from metrics import compare
    got = compare.load(ROOT / "metrics")
    # 🔴 **세 칸이 다 있어야** 한다 — 빠뜨리면 표에서 사라진다
    assert set(got) == set(compare.FILES), sorted(got)
    for name, box in got.items():
        # 🔴 **없는 파일은 `None`**(0 도 `{}` 도 아니다) · 있으면 dict
        want = None if (ROOT / "metrics" / name).exists() else type(None)
        if want is None:
            assert isinstance(box, dict), name
        else:
            assert box is None, f"🔴 `{name}` 이 없는데 {box!r} 로 때웠다"
    # 🔴 **없는 것은 `None`** 이고 비교가 그것을 말한다
    rows = compare.table({"baseline_solar.json": None,
                          "stage3.json": {"outcome_hit_rate": 0.5}})
    said = "\n".join(rows)
    assert "안 쟀다" in said, said


def test_v5A_6_기준_판정이_수로_답한다():
    """🔴 `stage3` 를 켤 수 있나 — **수가 답한다**(사람이 고르지 않는다)."""
    from metrics import compare
    base = {"outcome_hit_rate": 0.40, "wrong_repro": 3, "graded_markets": 10,
            "false_confidence": 4}
    better = {"outcome_hit_rate": 0.55, "wrong_repro": 2, "graded_markets": 8,
              "false_confidence": 3}
    ok, why = compare.may_enable("stage3", base, better)
    assert ok is True, why
    # 🔴 포함률이 **안 오르면** 안 된다
    flat = dict(better, outcome_hit_rate=0.40)
    assert compare.may_enable("stage3", base, flat)[0] is False
    # 🔴 오답 재현이 **늘면** 안 된다
    worse = dict(better, wrong_repro=4)
    assert compare.may_enable("stage3", base, worse)[0] is False
    # 🔴 등급 마켓이 **70% 아래**면 안 된다
    thin = dict(better, graded_markets=6)
    ok2, why2 = compare.may_enable("stage3", base, thin)
    assert ok2 is False and "70" in why2, why2


def test_v5A_6_단계4는_거짓_확신이_줄_때만():
    """🔴 *"단계 4 는 **거짓 확신 수가 줄 때만** 켠다"*."""
    from metrics import compare
    base = {"false_confidence": 4}
    assert compare.may_enable("stage4", base, {"false_confidence": 3})[0]
    assert not compare.may_enable("stage4", base, {"false_confidence": 4})[0]


def test_v5A_6_기준_미달이면_questions_로_간다():
    """🔴 *"기준을 못 넘으면 결과를 `questions/` 에 적고 **사용자 판단**"*."""
    from metrics import compare
    ok, why = compare.may_enable("stage3", {"outcome_hit_rate": 0.5},
                                 {"outcome_hit_rate": 0.4})
    assert ok is False
    assert "questions" in why, why


def test_v5A_6_폐기율_문턱이_있다():
    """🔴 *"폐기율 — M41 로 버려진 비율 · **20% 넘으면 프롬프트 재조정**"*."""
    got = _spec()["metrics"]["drop_rate"]
    assert float(got["warn_above"]) == 0.20, got


def test_v5A_6_비용은_하루_상한과_같은_수다():
    """🔴 *"경기당 비용 — Solar+DeepSeek USD · **하루 $3 안**"*.

    ⚠️ 그 수를 **두 곳에 적지 않는다** — §2 예산이 원본이다(사본 금지).
    """
    from app import rules
    from metrics import compare
    cap = float(rules.llm_budget()["per_day_usd"])
    assert compare.day_cap() == cap
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **베껴도 통과하던 구멍을 막는다**(D46)
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 위 한 줄만으로는 `return 3.0` 이 **그대로 통과한다** — 그러면 §2
    #     예산이 바뀔 때 이 수가 **따라가지 않는다**(사본 · CLAUDE.md #1).
    #  🔴 그래서 **코드 본문에 그 수가 글자로 없어야** 한다.
    #     ⚠️ 독스트링·주석은 뺀다(D46) — 문서가 설명하는 것과 코드가 쓰는 것은
    #        다르다(README·명세는 그 수를 **설명해도** 된다).
    from tests._helpers import strip_docs
    body = strip_docs(pathlib.Path(compare.__file__).read_text(encoding="utf-8"))
    #  ⚠️ **한 글자로 찾으면 안 된다** — `$3` 의 `"3"` 은 `0.70`·`len(FILES)`
    #     같은 아무 수에나 걸린다(실측: 되돌린 뒤에도 빨갰다). 🔴 그래서
    #     **수 하나를 통째로**(낱말 경계) 본다.
    import re
    #  ⚠️ **조항 번호를 수로 세지 않는다**(실측 2026-10-05): 상한이 `$5` 가
    #     되자 `§5 순서로 재야` 의 `5` 가 걸려 거짓 양성이 났다. 🔴 `§`·`#`
    #     뒤의 수는 조항·번호다 — 그 자리는 뺀다.
    body = re.sub(r"[§#]\s*\d+(?:[-.]\d+)*", " ", body)
    for lit in {f"{cap:g}", f"{cap}"}:
        hit = re.search(rf"(?<![\w.§#]){re.escape(lit)}(?![\w.])", body)
        assert hit is None, (
            f"🔴 `metrics/compare.py` 코드에 하루 상한 `{lit}` 이 **수로** "
            f"박혀 있다(…{body[max(0, hit.start() - 40):hit.end() + 20]}…) — "
            f"사본이다. `rules.llm_budget()` 를 읽어라")


@pytest.mark.parametrize("name", ["baseline_solar.json", "stage3.json",
                                  "stage34.json"])
def test_v5A_6_아직_안_쟀다는_사실이_남아_있다(name):
    """🔴🔴 **안 쟀으면 파일이 없다** — 빈 파일로 때우지 않는다(#3).

    ⚠️ 작업지시 §5 순서: 게이트3~5 를 **Solar 단독**으로 통과한 뒤에 기준선을
       고정한다. 🔴 지금 게이트 2 도 안 닫혔다 — 그래서 **없는 것이 맞다.**
    """
    p = ROOT / "metrics" / name
    if p.exists():
        box = json.loads(p.read_text(encoding="utf-8"))
        assert box.get("as_of"), f"🔴 {name} 에 `as_of` 가 없다"
        assert box.get("matches"), f"🔴 {name} 에 경기 목록이 없다"
    else:
        # 🔴 없는 것이 **기록으로** 남아 있어야 한다
        said = (ROOT / "metrics" / "README.md").read_text(encoding="utf-8")
        assert name in said, f"🔴 `{name}` 을 아직 안 쟀다는 사실이 안 적혀 있다"
