"""🔴🔴 **⑯ 검열의 거짓 양성** — 사용자 지시 2026-10-15 *"왜 llm 평문이 지어내냐"*.

실측(오늘 실행 전부 · 위반 54건):
  · 길이 초과 **27건**(227~279자) → 🔴 상한을 **300** 으로 올렸다
  · (라) **19건 전부 거짓 양성** — `S01-home은`·`S01-home의`·`S01-away가`(조사) ·
    `S01`(집안 접두)
  · (다) 5건 중 **4건 거짓 양성** — `UEFA Champions League`(대회 이름) ·
    `WW DD`(폼 글자)

🔴 이 계약은 **그 네 모양이 다시 위반으로 잡히면** 빨개진다.
"""
from __future__ import annotations

from app.core.stages import s6_verdict as V

BOX = [
    "확률 — 홈 33.3% · 무 33.3% · 원정 33.3%",
    "  변수 `S01-home` [recent_pattern] 자리 ['axis1'] — 최근 5경기 W W D D",
    "  변수 `S01-away` [recent_pattern] 자리 ['axis1'] — 최근 3경기 W L L",
    "대회 — AFC Champions League Two",
]


def _bad(*said: str) -> list:
    got = V.Verdict(sentences=list(said), refs=["확률"] * len(said),
                    pick="draw", score="1-1")
    return V.judge(got, BOX)[1]


def test_vd14_josa() -> None:
    """VD14 🔴 **조사가 붙은 변수 번호**를 (라) 가 잡지 않는다."""
    for one in ("S01-home은", "S01-home의", "S01-away가", "S01-home이",
                "S01-home과"):
        bad = _bad(f"{one} 최근 흐름이 약하다.")
        assert not [x for x in bad if "(라)" in x], f"🔴 {one} — {bad}"


def test_vd15_family_prefix() -> None:
    """VD15 🔴 **집안 접두**(`S01` ↔ `S01-home`)는 같은 것으로 센다."""
    assert not [x for x in _bad("S01 집안이 균등을 만들었다.") if "(라)" in x]


def test_vd16_not_a_person() -> None:
    """VD16 🔴 **대회 이름·폼 글자**를 사람 이름으로 세지 않는다."""
    for one in ("AFC Champions League Two 라 로테이션이 크다.",
                "최근 WW DD 흐름이다."):
        assert not [x for x in _bad(one) if "(다)" in x], one


def test_vd17_sent_max() -> None:
    """VD17 🔴 문장 상한은 **300 자 이상**이다(실측 최장 279자)."""
    assert V.SENT_MAX >= 300, f"🔴 SENT_MAX={V.SENT_MAX}"


def test_vd18_still_catches() -> None:
    """VD18 🔴 그래도 **진짜 지어냄**은 잡는다 — 없는 번호·없는 수."""
    assert [x for x in _bad("S09-home 이 홈을 밀었다.") if "(라)" in x]
    assert [x for x in _bad("홈 승률이 42%p 다.") if "(가)" in x]


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **자리 글자·한 낱말 이름** — 사용자 지시 2026-10-16
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실사고 2026-10-16(코스타리카 Saprissa): deepseek 평이 *"CB **Waston**"* ·
#     *"CM **Soto**"* · *"DM **López**"* 라고 썼고 (다) 가 셋 다 **없는 이름**
#     이라 했다 — 묶음에는 `Waston`·`Soto`·`Alexander López` 가 **그대로** 있었다.
#  🔴 까닭은 **비대칭**이다: `_NAME` 이 두 낱말 이상만 이름으로 보므로 묶음의
#     한 낱말 이름(`Waston`)을 못 모으고, 문장 쪽은 접두가 붙어 두 낱말이 된다.

NAME_BOX = [
    "확률 — 홈 32.2% · 무 32.2% · 원정 35.5%",
    "  전략 `SL1` — 홈은 실점 2.0 으로 흔들리고 CB에 Waston·Taylor·Azofeifa를 "
    "새로 넣어 라인이 높아진다",
    "  전략 `SL3` — 홈은 CM에 Soto·Acuña를 투입하고 원정은 DM Alexander López가 "
    "빠져 중원에서 홈이 우위다",
]


def _bad_name(*said: str) -> list:
    got = V.Verdict(sentences=list(said), refs=["확률"] * len(said),
                    pick="home", score="2-1")
    return [x for x in V.judge(got, NAME_BOX)[1] if "(다)" in x]


def test_vd19_자리_글자는_이름이_아니다() -> None:
    """VD19 🔴 `CB Waston`·`CM Soto` — 접두를 떼면 묶음에 있다."""
    assert not _bad_name("홈은 CB Waston 과 CM Soto 를 새로 넣었다.")


def test_vd20_성만_써도_같은_사람이다() -> None:
    """VD20 🔴 `DM López` — 묶음의 `Alexander López` 를 가리킨 것이다."""
    assert not _bad_name("원정은 DM López 가 빠져 중원이 얇다.")


def test_vd21_지어낸_이름은_그래도_잡는다() -> None:
    """VD21 🔴🔴 느슨해진 뒤에도 **없는 선수**는 잡아야 한다."""
    assert _bad_name("GK Hyun-Woo Kim 이 선발로 들어왔다.")
    assert _bad_name("교체로 Marco Verratti 가 들어온다.")


def test_vd22_strip_pos() -> None:
    """VD22 🔴 자리 글자 떼기 — `FB/WB` 처럼 겹친 꼴도 떼낸다."""
    from app.core.stages import s9_say as say
    assert say.strip_pos("FB/WB Carvajal") == "Carvajal"
    assert say.strip_pos("CB Waston") == "Waston"
    assert say.strip_pos("Alexander López") == "Alexander López"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **(가) 수 검사 — 소수는 글자 그대로 · 맨 정수는 안 센다**
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실사고 2026-10-16(Sydney FC): 묶음에 **폼이 한 줄도 없는데** 평이
#     *"최근 5경기 득점 평균 1.7골, 실점 1.4골 · 원정 1.3/1.5"* 라고 썼다.
#     🔴 검열은 그 넷을 **놓치고**(상대 오차 5% 가 삼켰다) 엉뚱하게 `5`
#     (최근 **5**경기)를 잡았다 — **두 방향 다 틀렸다**.

NUMBOX = [
    "확률 — 홈 33.3% · 무 33.3% · 원정 33.3%",
    "변수 `S03` — 홈 승률 수치 없음 · λ 홈 배율은 득점 실측(홈 평균 1.6444)",
    "  axis1 — 홈 0.6250 · 원정 0.0150 · 차 +0.6100",
]


def _num_only(one: str) -> str:
    from app.core.stages.s6_verdict import num_bad
    return num_bad(one, "\n".join(NUMBOX))


def test_vd23_지어낸_소수를_잡는다() -> None:
    """VD23 🔴🔴 `1.7`·`1.4` — 묶음의 `1.6444` 와 가깝다고 통과시키지 않는다."""
    assert "1.7" in _num_only("최근 5경기 득점 평균은 1.7골, 실점 1.4골이다.")
    assert "1.3" in _num_only("원정은 득점 1.3골에 실점 1.5골이다.")


def test_vd24_맨_정수는_안_센다() -> None:
    """VD24 🔴 `최근 5경기`·`11명`·`3연승` 은 **낱말**이다(거짓 양성 금지)."""
    assert not _num_only("최근 5경기 자료가 없어 홈 이점만 남았다.")
    assert not _num_only("11명 명단과 3연승 흐름은 묶음에 없다.")


def test_vd25_묶음에_있는_수는_통과() -> None:
    """VD25 🔴 글자 그대로 있는 수는 지난다."""
    assert not _num_only("축1 은 홈 0.6250 · 원정 0.0150 이다.")
    assert not _num_only("확률은 33.3%씩 균등하다.")


def test_vd26_퍼센트는_수로_본다() -> None:
    """VD26 🔴 `42%p` 처럼 **없는 퍼센트**는 여전히 잡는다."""
    assert "42" in _num_only("홈 승률이 42%p 올라간다.")


def test_vd27_묶음에_없는_수는_버려진다() -> None:
    """🔴🔴 **묶음에 없는 수 금지**는 남는다 — 사용자 지시 2026-10-18.

    ⚠️ 종전 어림은 *"`최근 경기 득점·실점 평균이 없으면 그 수를 쓰지 마라`"*
       였다(Sydney FC 실사고 — 폼이 0건인데 네 수를 지어냈다). 🔴 프롬프트를
       **변수만**으로 줄이면서 그 줄이 걷혔고, 남은 못은 **대조**다.
    """
    import inspect

    from app.core.stages.s6_verdict import ask
    src = inspect.getsource(ask)
    assert "묶음에 없는 수를 쓰면 **버려진다**" in src, src[-500:]
    assert "만들지 " in src, src[-500:]
