"""[2026-09-04] 라인업 **모양**이 트리거를 죽이고 있었다 — 두 번째다.

🔴 운영 실측 2026-09-04 KBO 저녁 슬레이트, 재판정 8건 전부:
     [pipeline] 재판정 딥서치 생략 — 판정은 계속: 'str' object has no attribute 'get'
   `first_lineup_evidence` 가 `research[f"{side}_lineup"]` 을 **dict 라고
   가정**하고 `.get("order")` 를 불렀다. KBO·NPB 는 크롤러가 준 타순을
   **문자열**("홍창기-신민재-…")로 담는다. 예외가 호출부의 넓은 except 에
   삼켜져 **T4·T5·T6 가 야구에서 통째로 죽어 있었다.**

🔴 이 파일이 스스로 같은 사고를 기록해 뒀다 (`_lineup_of` 주석, 2026-09-01):
   "T5 가 야구에서 한 번도 발동하지 않았다 — 키가 어긋나".
   그때는 **dict 경로만** 열고 문자열 경로는 안 열었다. 같은 결함의 절반이
   그대로 남아 있었던 것이다.

→ **모양을 아는 곳은 `_lineup_of` 한 군데뿐이어야 한다.** 트리거 판별은
  그것을 재사용한다. 모양 분기를 다시 적는 순간 그것이 다음 사본이다.
"""
import pytest

from app.engine.deepsearch import _lineup_of, _names, first_lineup_evidence


# ─────────────────── 모양 ───────────────────

@pytest.mark.parametrize("research,expected", [
    ({"home_lineup": "홍창기-신민재-오스틴"}, True),      # KBO·NPB 문자열
    ({"home_lineup": {"order": "A-B-C"}}, True),          # 축구 dict
    ({"home_lineup": ""}, False),
    ({"home_lineup": {}}, False),
    ({}, False),
])
def test_lineup_of_reads_every_shape_we_actually_store(research, expected):
    assert bool(_lineup_of({"research": research}, "home")) is expected


def test_string_lineup_yields_names():
    got = _names(_lineup_of({"research": {"home_lineup": "홍창기-신민재"}}, "home"))
    assert got == {"홍창기", "신민재"}


# ─────────────────── T6 최초 공시 ───────────────────

def _jg(order, status="confirmed"):
    return {"lineup_status": status,
            "research": {"home_lineup": order, "away_lineup": ""}}


def test_t6_fires_on_a_string_lineup_with_no_previous():
    """🔴 이것이 운영에서 예외로 죽던 자리다."""
    assert first_lineup_evidence(_jg("홍창기-신민재-오스틴"), None) is True


def test_t6_does_not_fire_when_previous_exists():
    prev = {"research": {"home_lineup": "홍창기-신민재", "away_lineup": ""}}
    assert first_lineup_evidence(_jg("홍창기-신민재"), prev) is False


def test_t6_ignores_the_empty_shell_prev_lineup():
    """껍데기는 항상 온다 — dict 가 truthy 라고 '직전 있음'으로 읽으면 안 된다."""
    shell = {"research": {"home_lineup": {}, "away_lineup": {}}}
    assert first_lineup_evidence(_jg("A-B-C"), shell) is True


def test_t6_needs_a_confirmed_lineup():
    assert first_lineup_evidence(_jg("A-B-C", status="predicted"), None) is False


def test_t6_needs_an_actual_order():
    assert first_lineup_evidence(_jg(""), None) is False


@pytest.mark.parametrize("bad", ["홍창기-신민재", {"order": "A-B"}, ["A", "B"]])
def test_no_shape_raises(bad):
    """🔴 어떤 모양이 와도 **예외를 던지지 않는다.** 삼켜진 예외가 원인이었다."""
    jg = {"lineup_status": "confirmed",
          "research": {"home_lineup": bad, "away_lineup": bad}}
    first_lineup_evidence(jg, {"research": {"home_lineup": bad}})


def test_trigger_code_does_not_re_implement_shape_knowledge():
    """모양 분기를 트리거 안에 다시 적으면 그것이 다음 사본이다."""
    import inspect

    src = inspect.getsource(first_lineup_evidence)
    assert "_lineup_of" in src and "_names" in src
    # ⚠️ 주석에는 옛 코드가 인용돼 있다(왜 고쳤는지 남기려고). **실행되는
    #    줄만** 본다 — 주석까지 금지하면 사고 기록을 지우게 된다.
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith("#"))
    assert '.get("order")' not in code, "모양 가정이 되살아났다"
    assert "isinstance" not in code, "모양 분기가 되살아났다"
