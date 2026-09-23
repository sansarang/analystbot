"""[HYC-6] **잴 수 없는 칸을 운영에 드러낸다.**

사용자 2026-09-23: "hyc 전부 다 해라"
계획서 `hyp_conditions_0920` §4(HYC-6):
> 조건별 상태 = **성립 / 불성립 / 미상 / 미실행**. ⑥ 스냅샷과 ⑫ 서술에
> 싣는다. **⑦ 조정에는 넣지 않는다**(observe_only).
> `/health` 한 줄 + `app/export/for_fable.py` 의 `coverage` 블록.

🔴 HYC-3 로 `미실행` 이 생겼지만 **운영에서 볼 방법이 없었다** — ⑥ 스냅샷과
   ⑫ 글에만 있고 `/health`·export 에는 없다. 그러면 "왜 이 변수는 영원히
   비어 있나"를 사람이 DB 를 파야 안다.

🔴 실측 (오늘 흐름 1회):
```
미실행 ['travel_backtoback', 'park_factor', 'weather']   NPB 3경기
미실행 ['travel_backtoback', 'weather']                  KBO
```
전 기간으로도 `weather`·`travel_backtoback` 은 **확인 0 / 등장 2,129** 다.

⚠️ **⑦ 조정에는 안 넣는다**(observe_only) — 관측 장치가 판정을 건드리면
   그게 이 저장소가 반복해 겪은 결함이다(감시 3층 규약).
"""
from __future__ import annotations

import inspect

import pytest


def test_집계_함수가_있다():
    from app.flow import coverage as C

    assert hasattr(C, "summarize")


def test_상태_넷을_센다():
    """🔴 계획서 그대로 — 성립/불성립/미상/미실행."""
    from app.flow import coverage as C

    got = C.summarize([
        {"per_var": {"a": "confirmed", "b": "unknown", "c": "미실행"}},
        {"per_var": {"a": "confirmed", "b": "refuted", "c": "미실행"}},
    ])
    assert got["vars"]["a"]["confirmed"] == 2
    assert got["vars"]["b"]["unknown"] == 1 and got["vars"]["b"]["refuted"] == 1
    assert got["vars"]["c"]["미실행"] == 2
    assert got["games"] == 2


def test_영원히_미실행인_칸을_따로_알려준다():
    """🔴 **이것이 이 단위의 값어치다** — "한 번도 잴 수 없었다"를 센다."""
    from app.flow import coverage as C

    got = C.summarize([
        {"per_var": {"weather": "미실행", "starter_recent3": "confirmed"}},
        {"per_var": {"weather": "미실행", "starter_recent3": "unknown"}},
    ])
    assert got["always_unrun"] == ["weather"], got


def test_옛_이력이_섞여도_잡는다():
    """🔴 [HYC6b 2026-09-23] **배포 직후 실측으로 드러난 결함.**

    `always_unrun` 을 "전건 미실행"으로 정의했더니 `/health` 줄이 **안 나왔다** —
    HYC-3 이전 이력에서 그 칸은 `unknown` 으로 남아 있어 "전건"이 깨진다:
```
weather            unknown 1,567 · 미실행 28      → 전건 미실행 아님 → 누락
travel_backtoback  unknown 1,565 · 미실행 30      → 누락
always_unrun = []                                 ← /health 가 침묵
```
    뜻은 "**한 번도 확인된 적이 없고** 미실행으로 표시된 적이 있는 칸"이다.
    """
    from app.flow import coverage as C

    got = C.summarize([{"per_var": {"weather": "unknown"}}] * 50
                      + [{"per_var": {"weather": "미실행"}}] * 5)
    assert got["always_unrun"] == ["weather"], got


def test_미실행_표시가_없으면_안_센다():
    """⚠️ 반대 위험 — 그냥 자료가 없어 미상인 칸까지 "잴 방법이 없다"고
    적으면 거짓이다. 미실행 표시가 **한 번은** 있어야 한다."""
    from app.flow import coverage as C

    got = C.summarize([{"per_var": {"lineup_out": "unknown"}}] * 20)
    assert got["always_unrun"] == [], got


def test_한_번이라도_잰_칸은_빠진다():
    """⚠️ 반대 위험 — 가끔 되는 칸을 "영원히 안 됨"으로 적으면 거짓이다."""
    from app.flow import coverage as C

    got = C.summarize([
        {"per_var": {"park_factor": "미실행"}},
        {"per_var": {"park_factor": "confirmed"}},
    ])
    assert got["always_unrun"] == [], got


def test_사람_이름으로_적는다():
    """🔴 [VIS-1] 사용자가 읽는 자리다 — 코드 이름을 쓰지 않는다."""
    from app.flow import coverage as C

    line = C.line([{"per_var": {"weather": "미실행",
                                "travel_backtoback": "미실행"}}])
    assert line
    assert "weather" not in line and "travel_backtoback" not in line, line
    assert "날씨" in line, line


def test_빈_입력이면_줄을_만들지_않는다():
    """⚠️ 조용한 0 과 다르다 — 잴 것이 없으면 할 말도 없다."""
    from app.flow import coverage as C

    assert C.line([]) is None


@pytest.mark.asyncio
async def test_health_에_한_줄이_붙는다():
    """🔴 배선의 끝 — 운영에서 보인다."""
    import app.health as H

    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(H.build_health).splitlines())
    assert "coverage" in src, "/health 가 집계를 안 읽는다"


def test_export_에_블록이_붙는다():
    import app.export.for_fable as F

    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(F).splitlines())
    assert "coverage" in src


def test_조정에는_안_들어간다():
    """🔴 **관측 장치가 판정을 건드리면 안 된다**(감시 3층 규약)."""
    import inspect as _i

    from app.flow.nodes import n07_adjust as N7

    src = _i.getsource(N7)
    assert "coverage" not in src, "⑦이 관측 집계를 읽는다"


def test_이름의_원본이_설정이다():
    """🔴 사본 금지 — `flow.var_names` 하나다."""
    from app.flow import coverage as C

    src = inspect.getsource(C)
    assert "var_names" in src or "_var_ko" in src
