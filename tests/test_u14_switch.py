"""U14 계약 — 전환·라운드로빈·출력 규격.

🔴 이 파일이 지키는 가장 중요한 것: **스위치를 켜지 않는다.**
"""
import pytest

from app.engine import shadow_v3 as SV
from app.engine import spec_render as SR
from app.llm import quota as Q


@pytest.fixture(autouse=True)
def _clean():
    Q.reset()
    yield
    Q.reset()


# ───────────────────────── 라운드로빈

def test_429맞은_제공자는_다음_호출에서_뒤로():
    Q.note_headers("groq", {"retry-after": "45"}, status=429)
    assert Q.order_by_remaining(["groq/a", "cerebras/b", "gemini/c"]) == \
        ["cerebras/b", "gemini/c", "groq/a"]


def test_헤더가_없으면_순서를_바꾸지_않는다():
    """🔴 반대 위험 — 모름을 0 으로 읽으면 멀쩡한 제공자가 영영 뒤로 간다."""
    Q.note_headers("gemini", {}, status=200)
    assert Q.remaining("gemini") is None
    assert Q.order_by_remaining(["gemini/c", "groq/a"]) == ["gemini/c", "groq/a"]


def test_전부_한도면_그때만_기다린다():
    for p in ("groq", "cerebras"):
        Q.note_headers(p, {"retry-after": "30"}, status=429)
    chain = ["groq/a", "cerebras/b"]
    assert Q.all_cooling(chain) is True
    assert Q.order_by_remaining(chain) == chain      # 순서 그대로
    assert 0 < Q.wait_secs(chain) <= 30


def test_한_제공자만_살아있으면_기다리지_않는다():
    Q.note_headers("groq", {"retry-after": "30"}, status=429)
    assert Q.all_cooling(["groq/a", "gemini/c"]) is False


def test_잔량은_음수로_안_내려간다():
    Q.note_headers("groq", {"x-ratelimit-remaining-tokens": "-5"})
    assert Q.remaining("groq") == 0


def test_리셋_표기를_읽는다():
    Q.note_headers("groq", {"x-ratelimit-reset-tokens": "1m30s"}, status=429)
    assert 85 < Q.cooling("groq") <= 90


def test_리셋을_못_읽으면_기본_대기():
    Q.note_headers("groq", {"retry-after": "알 수 없음"}, status=429)
    assert 0 < Q.cooling("groq") <= Q.DEFAULT_COOLDOWN


def test_chain이_한도를_반영한다(monkeypatch):
    """배선 계약 — 모듈만 있고 사슬이 안 쓰면 소용없다."""
    from app.llm import judge_route as JR

    monkeypatch.setattr(JR, "_cfg", lambda: type("S", (), {
        "judge_provider": "groq", "judge_chain": "groq/a,cerebras/b",
        "form_chain": "groq/a,cerebras/b", "xai_api_key": "",
        "paid_llm_allowed": True, "matchup_model": "m", "grok_model": "g"})())
    monkeypatch.setattr(JR, "is_free", lambda p, m: True)
    assert [p for p, _ in JR.chain("form")] == ["groq", "cerebras"]
    Q.note_headers("groq", {"retry-after": "45"}, status=429)
    assert [p for p, _ in JR.chain("form")] == ["cerebras", "groq"]


# ───────────────────────── 출력 규격

def test_확인은_체크_못한_것은_엑스():
    out = SR.checks(["away.out"], ["home.midweek"], ["home.xi_status"])
    assert out[0].startswith("✔") and "원정" in out[0]
    assert out[1].startswith("✗") and "반대 사실" in out[1]
    assert out[2].startswith("✗") and "못 찾음" in out[2]


def test_반증과_미상은_다른_말이다():
    """🔴 둘 다 ✗ 지만 뜻이 다르다 — 섞으면 '찾아봤는데 아니다'와
    '못 찾았다'가 같아진다."""
    a = SR.checks(refuted=["home.out"])[0]
    b = SR.checks(unknown=["home.out"])[0]
    assert a != b


def test_시장흐름_줄에_class와_이유():
    line = SR.flow_line({"class": "steam", "pp": 3.4, "reason": "3북 동일"})
    assert "steam" in line and "+3.4%p" in line and "3북 동일" in line


def test_분류가_없으면_흐름_줄이_없다():
    """🔴 지어내지 않는다 — 못 잰 것을 '잡음'이라 쓰면 거짓이다."""
    assert SR.flow_line({}) is None and SR.flow_line(None) is None


def test_결정축_반대축_조건이_렌더된다():
    txt = SR.render({"main_axis": "핵심결장", "counter_axis": None,
                     "conditions": {"official 라인업": True, "edge 유지": False}})
    assert "결정축: 핵심결장" in txt
    assert "반대축: 없음" in txt, "반대축을 빼면 한쪽만 본 것처럼 읽힌다"
    assert "✔ official 라인업" in txt and "✗ edge 유지" in txt


def test_렌더는_숫자를_지어내지_않는다():
    """반대 위험 — 빈 블록에서 확률·%p 가 튀어나오면 안 된다."""
    txt = SR.render({})
    assert txt == ""
    txt2 = SR.render({"title": "A vs B"})
    assert txt2 == "A vs B" and "%" not in txt2


# ───────────────────────── 전환 기준

def test_전환기준_네_항목():
    c = SV.criteria()
    assert set(c) >= {"카드생성률", "자기모순", "브라이어", "토큰"}
    assert SV.CARD_RATE_MIN == 0.98 and SV.BRIER_SLACK == 0.005
    assert SV.TOKEN_MULT_MAX == 2.0 and SV.SHADOW_DAYS == 7


def _rows(days=7, **over):
    out = []
    for i in range(days):
        r = {"day": f"2026-09-{15 + i}", "card": True, "before_t30": True,
             "self_contra": False, "p": 0.6, "hit": 1, "tokens": 100}
        r.update(over)
        out.append(r)
    return out


_BASE = {"brier": 0.25, "tokens": 400}


def test_전부_충족하면_전환가능():
    assert SV.evaluate(_rows(), baseline=_BASE)["전환가능"] is True


def test_자기모순이_하나라도_있으면_전환불가():
    """🔴 반대 위험 — 수치가 좋아도 모순 카드는 나간다."""
    rows = _rows()
    rows[3]["self_contra"] = True
    out = SV.evaluate(rows, baseline=_BASE)
    assert out["전환가능"] is False and "자기모순" in out["미달"]


def test_T30_이후_카드는_생성률에_안_센다():
    rows = _rows()
    for r in rows[:2]:
        r["before_t30"] = False
    out = SV.evaluate(rows, baseline=_BASE)
    assert out["항목"]["카드생성률"]["값"] == pytest.approx(5 / 7)
    assert out["전환가능"] is False


def test_브라이어가_종전보다_나쁘면_전환불가():
    out = SV.evaluate(_rows(p=0.4, hit=0), baseline={"brier": 0.10,
                                                     "tokens": 400})
    assert out["전환가능"] is False and "브라이어" in out["미달"]


def test_토큰이_두_배를_넘으면_전환불가():
    out = SV.evaluate(_rows(tokens=200), baseline={"brier": 0.25,
                                                   "tokens": 100})
    assert out["전환가능"] is False and "토큰" in out["미달"]


def test_기간이_안_차면_통과라고_쓰지_않는다():
    """🔴 반대 위험 — 표본 없음은 통과가 아니다."""
    out = SV.evaluate(_rows(days=3), baseline=_BASE)
    assert out["전환가능"] is False and "7일 미충족" in out["사유"]
    assert SV.evaluate([])["전환가능"] is False


def test_스위치_기본값을_건드리지_않는다():
    """🔴 U14 는 전환 **가부를 잴 뿐** 켜지 않는다. 전환 시각은 사용자다."""
    import pathlib
    src = pathlib.Path("app/config.py").read_text(encoding="utf-8")
    assert "order_v3: bool = Field(default=False" in src
    # shadow_v3 가 설정을 쓰지 않는다 — 순수 함수다
    mod = pathlib.Path("app/engine/shadow_v3.py").read_text(encoding="utf-8")
    assert "get_settings" not in mod and "order_v3" not in mod
