"""[HYC-3] "안 봤다"와 "**볼 방법이 없다**"를 가른다.

사용자 2026-09-23: "가 해라..그리고 재분석해라"

🔴 실측 (SP-3 이후 깨끗한 1회 · 오늘 9경기):
```
변수                 확인  미상   미상률
bullpen_3d            7    0    0.0%
starter_recent3       7    0    0.0%
lineup_out            1    6   85.7%
park_factor           0    2  100.0%   ← NPB 는 모듈이 없다
travel_backtoback     0    2  100.0%   ← ⑤에 분기가 없다
weather               0    2  100.0%   ← ⑤에 분기가 없다

요미우리@히로시마  미상 4/6 = 0.667 → 모름과반
  weather·travel_backtoback 만 빼면  2/4 = 0.500 → 확인됨
  park_factor(NPB 모듈 없음)까지 빼면 1/3 = 0.333 → 확인됨
```
전 기간으로도 `weather`·`travel_backtoback` 은 **확인 0 / 등장 2,129** 다.
⑤의 코드가 그것을 이미 말하고 있었다 — `"그 밖의 변수는 아직 소스가 없다"`.

🔴 **목록을 손으로 적지 않는다.** 못 찾는 것을 아는 쪽은 ⑤다 — ⑤가 그 자리에서
   `미실행` 행을 남기고 ⑥은 그것을 읽는다. 별도 표를 두면 그게 사본이고,
   `rules.yaml` 에 변수가 추가될 때 따라가지 않는다.

⚠️ 미상을 **숨기는 것이 아니다.** `per_var` 에 `미실행` 로 남아 export·서술에
   그대로 보인다. 빠지는 것은 **분모**뿐이다.
"""
from __future__ import annotations

import ast
import inspect

import pytest

from app.flow import labels as L
from app.flow.nodes import n05_evidence as N5
from app.flow.nodes import n06_verdict as N6


def test_상태값이_labels_에_있다():
    """🔴 원본은 `labels` 하나다 — 노드에 문자열을 적지 않는다."""
    assert hasattr(L, "UNRUN")
    assert L.UNRUN not in (L.CONFIRMED, L.REFUTED, L.UNKNOWN)


class _S:
    def __init__(self, vars_, ev):
        self.game_id = "1"
        self.n04_hyp = [{"id": "H_deriv", "refuted_means": "중립",
                         "vars": [{"var": v} for v in vars_]}]
        self.n05_evidence = ev
        self.n06_verdict = None


def _ev(var, value=None, status=None, excerpt="x"):
    r = {"var": var, "value": value, "raw_excerpt": excerpt, "sides": {},
         "direction": {}, "source": "", "source_url": "", "fetched_at": None,
         "untrusted_reason": ""}
    if status:
        r["status"] = status
    return r


@pytest.mark.asyncio
async def test_미실행은_분모에서_빠진다():
    """🔴 이 단위의 전부 — 실측 그대로다(4/6 → 1/3)."""
    st = _S(["starter_recent3", "bullpen_3d", "lineup_out",
             "weather", "travel_backtoback", "park_factor"],
            [_ev("starter_recent3", ["a"]), _ev("bullpen_3d", ["b"]),
             _ev("weather", status=L.UNRUN), _ev("travel_backtoback", status=L.UNRUN),
             _ev("park_factor", status=L.UNRUN)])
    out = await N6.run(st, None)
    v = out.n06_verdict
    assert v["per_var"]["weather"] == L.UNRUN, v["per_var"]
    assert v["unknown_ratio"] == round(1 / 3, 4), v
    assert v["verdict"] == L.V_OK, v


@pytest.mark.asyncio
async def test_미상을_숨기지_않는다():
    """⚠️ `per_var` 에 그대로 남는다 — 사라지는 것은 분모뿐이다."""
    st = _S(["weather", "starter_recent3"],
            [_ev("weather", status=L.UNRUN)])
    v = (await N6.run(st, None)).n06_verdict
    assert set(v["per_var"]) == {"weather", "starter_recent3"}
    assert v["per_var"]["starter_recent3"] == L.UNKNOWN
    assert v.get("unrun") == ["weather"], v


@pytest.mark.asyncio
async def test_전부_미실행이면_모름과반이다():
    """🔴 **잴 것이 하나도 없으면 확인됨이 아니다.** 분모가 0 일 때 통과시키면
    "아무것도 안 보고 확인"이 된다 — 이 저장소가 가장 경계하는 방향이다."""
    st = _S(["weather", "travel_backtoback"],
            [_ev("weather", status=L.UNRUN), _ev("travel_backtoback", status=L.UNRUN)])
    v = (await N6.run(st, None)).n06_verdict
    assert v["verdict"] == L.V_UNKNOWN, v


@pytest.mark.asyncio
async def test_종전_동작은_그대로다():
    """⚠️ 반대 위험 — 미실행이 없으면 계산이 종전과 같아야 한다."""
    st = _S(["starter_recent3", "bullpen_3d", "lineup_out"],
            [_ev("starter_recent3", ["a"])])
    v = (await N6.run(st, None)).n06_verdict
    assert v["unknown_ratio"] == round(2 / 3, 4)
    assert v["verdict"] == L.V_UNKNOWN


# ── ⑤가 표시한다 ────────────────────────────────────────────────────

def test_분기_없는_변수를_다섯번노드가_표시한다():
    """🔴 **목록을 손으로 적지 않는다.** ⑤가 "소스 없음"으로 떨어뜨리는 그
    자리에서 미실행을 남긴다."""
    src = inspect.getsource(N5.run)
    i = src.index("소스 없음")
    assert "UNRUN" in src[i - 400:i + 400], "소스 없음 자리에서 미실행을 안 남긴다"


def test_목록을_어디에도_적지_않았다():
    """🔴 사본 금지 — 변수 이름을 열거한 집합이 있으면 `rules.yaml` 이 바뀔 때
    따라가지 않는다.

    ⚠️ [LOAD-1 2026-09-23] `travel_backtoback` 을 이 목록에서 **뺐다.**
       분기가 생겼기 때문이다 — `_recent_match()` 가 이미 있었는데 야구가
       안 부르고 있었다. 분기가 있는 변수는 `rotation_risk`·`xi_confirmed`·
       `news_injury` 처럼 이름이 코드에 나오는 것이 정상이다.
       🔴 남은 둘(`weather`·`motivation`)은 **여전히 분기가 없다** — 그 둘에
          대해서는 이 계약이 그대로 산다.
    """
    for mod in (N5, N6):
        code = ast.unparse(ast.parse(inspect.getsource(mod)))
        for name in ("weather", "motivation"):
            assert f'"{name}"' not in code and f"'{name}'" not in code, \
                f"{mod.__name__} 에 {name} 를 손으로 적었다"


@pytest.mark.asyncio
async def test_모듈_없는_종목의_park_factor_도_미실행이다():
    """🔴 NPB 는 파크팩터 모듈이 **없다** — 못 잰 것이 아니라 잴 수 없는 것이다."""
    from app.flow.ctx import Ctx
    from app.flow.state import State

    st = State.new({"id": "1", "sport": "npb", "league": "NPB",
                    "home": "H", "away": "A",
                    "starts_at": "2026-09-23T09:00:00+00:00"})
    st.sport = "baseball"
    st.pick_side = "home"
    st.n04_hyp = [{"id": "H", "vars": [{"var": "park_factor"}]}]

    class _R:
        async def get(self, k):
            return None

    out = await N5.run(st, Ctx(redis=_R()))
    rows = [e for e in (out.n05_evidence or []) if e["var"] == "park_factor"]
    assert rows and rows[0].get("status") == L.UNRUN, rows
