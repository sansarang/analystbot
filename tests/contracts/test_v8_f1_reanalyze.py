"""🔴🔴 **F1 — 확정 XI 재분석 때 상성부터 다시**(지시서 2026-10-11 §2 F1).

> reanalyze: 확정(또는 2매체 보도) XI가 들어오면 ④ 깃발부터 ⑯까지 **전부 다시** 돈다.
> 재사용은 ③의 기사 문서·⑤의 기사 추출 결과만. "상성·시뮬 그대로, 시나리오 필수형
> 보강만" 경로 **삭제**.

🔴 왜 이렇게 됐었나(실측 2026-10-11): `reanalyze` 가 **파이프라인의 두 번째 사본**
   이었다 — `analyze` 의 ⑧ 상성 재료·⑨ 상성 판정·⑪ 확률·⑫ 검증을 **아예 안 불렀고**,
   그래서 재분석 카드에는 **우리 확률이 없었다**. 사본이 원본을 따라가지 못한 것이다
   (CLAUDE.md #1).
"""
from __future__ import annotations

import inspect


# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_F1_재분석이_파이프라인_사본을_들지_않는다`

def test_F1_옛_경로가_지워졌다():
    """🔴 *"상성·시뮬 그대로, 시나리오 **필수형 보강만**"* 경로는 **삭제**다.

    ⚠️ 돌연변이: 그 말이 코드에 남아 있으면 빨개진다(문서가 아니라 **코드**가 과녁이다).
    """
    from app.core import pipeline as _pl
    body = inspect.getsource(_pl)
    code = "\n".join(x for x in body.splitlines()
                     if not x.strip().startswith("#"))
    for ban in ("시뮬 분포가 없다(상성을 다시 안 돈다)", "필수형 보강만**이다"):
        assert ban not in code, f"🔴 옛 경로가 남아 있다 — {ban!r}"


def test_F1_analyze_가_재사용과_직전_카드를_받는다():
    """🔴 재사용은 **③ 문서·⑤ 추출**뿐이다(검색·LLM 추출 비용만 아낀다).

    구조 사실(s2)·라인업·새 사실 72시간은 **다시 받는다** — 그래서 `facts` 는
    재사용 목록에 **없다**.
    """
    from app.core import pipeline as _pl
    got = inspect.signature(_pl.analyze).parameters
    assert "reuse" in got, "🔴 `analyze` 가 재사용을 못 받는다"
    assert "before" in got, "🔴 `analyze` 가 직전 카드를 못 받는다(바뀐 것 비교)"
    said = inspect.getsource(_pl.analyze)
    i = said.index("said_reuse")
    win = said[i:i + 1200]
    assert "docs" in win and "cands" in win, (
        "🔴 재사용이 문서·추출 둘을 가리키지 않는다")
    # 🔴 **구조 사실은 재사용하지 않는다**
    assert "reuse" not in inspect.getsource(_pl.analyze).split(
        "s2_facts.run")[0][-200:], "🔴 s2(구조 사실)를 재사용하려 한다"


def test_F1_R1_상성_해시는_XI_가_바뀌면_다시_센다():
    """🔴🔴 **계약 R1** — 같은 경기에서 XI 가 예상→확정으로 바뀌면 `MatchupReport`
    해시가 **다시 계산된다**(같은 XI 면 같은 해시).

    ⚠️ 돌연변이: `fingerprint` 가 축 값을 안 보면(상수 반환) 빨개진다.
    """
    from app.core import matchup as _mu

    class _Axis:
        def __init__(self, gap, why=""):
            self.gap, self.why, self.strength = gap, why, "중"
            self.home = self.away = None
            self.refs: list[str] = []

    class _MR:
        def __init__(self, gaps, state="confirmed"):
            self._a = {f"axis{i}": _Axis(g) for i, g in enumerate(gaps)}
            self.total = sum(gaps)
            self.verdict = {"who": "home", "strength": "중"}
            self.xi_state = state

        def axis(self, key):
            return self._a[key]

    a = _MR([0.1, 0.2, 0.0, -0.1])
    b = _MR([0.1, 0.2, 0.0, -0.1])
    c = _MR([0.4, 0.2, 0.0, -0.1])          # 🔴 XI 가 바뀌어 축0 이 움직였다
    assert _mu.fingerprint(a) == _mu.fingerprint(b), "🔴 같은 XI 인데 해시가 다르다"
    assert _mu.fingerprint(a) != _mu.fingerprint(c), "🔴 축이 바뀌었는데 해시가 같다"
    # 🔴 XI 상태만 바뀌어도 **다시 센 것**이 보여야 한다
    d = _MR([0.1, 0.2, 0.0, -0.1], state="predicted")
    assert _mu.fingerprint(a) != _mu.fingerprint(d), "🔴 XI 상태를 안 센다"


def test_F1_카드_머리에_확정_XI_반영_줄이_있다():
    """🔴 카드 머리: *"🔁 확정 XI 반영 — 바뀐 것: 상성 축(전→후)·확률(전→후)·등급(전→후)"*."""
    from app.core import render as _r
    said = inspect.getsource(_r._head)
    assert "🔁 **확정 XI 반영**" in said, "🔴 그 줄을 카드가 안 적는다"
    for want in ("상성 축(전→후)", "확률(전→후)", "등급(전→후)"):
        assert want in said, f"🔴 `{want}` 가 없다"
    # 🔴 **확정이 아닐 때는 그 말을 쓰지 않는다**(#3 — 안 바뀐 것을 바뀌었다고 안 한다)
    assert "confirmed" in said and "else" in said, (
        "🔴 확정 여부를 안 가리고 늘 '확정 XI 반영' 이라고 적는다")
