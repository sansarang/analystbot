"""[CAP5] ⑤의 경기당 상한이 **핵심 변수를 자른다.**

F-17 로 `동의` 게이트도 전 변수(야구 6개)를 묻게 되자 드러났다.

🔴 실측 2026-09-23 (F-17 배포 직후 · 흐름 1회):
```
경기당 상한 deepsearch_cap.per_game = 5
  Orix@Chiba Lotte   행 5개  [starter, bullpen, travel_backtoback, park, weather]
  Kia@Doosan         행 5개  [starter, bullpen, travel_backtoback, park, weather]
  Lotte@Hanwha       행 5개  [starter, bullpen, lineup_out, travel_backtoback, park]
                             ← `weather` 가 상한에 잘렸다
```
변수는 6개인데 상한이 5다 — **언제나 마지막 하나가 잘린다.**

🔴 바로 그 위 주석이 모순을 이미 적고 있었다(BUD-1):
> "**여기서 예산을 차감하지 않는다.** 이 노드에는 **기사 fetch 가 없다** —
>  바깥 호출이 Redis 읽기와 DB 조회뿐이고 httpx/aiohttp/requests 가 0건이다.
>  기사는 별도 잡(`satellite_15m`)이 긁고 ⑤는 읽기만 한다."

예산을 안 쓰는데 예산 상한으로 **조사를 끊고 있었다.** 끊긴 자리는 `unknown`
이 되어 ⑥의 분모에 들어간다 — "안 봤다"가 아니라 **"못 보게 막았다"**이다.

⚠️ `Ctx.take_search` 는 그대로 둔다. 기사 수집이 ⑤에 붙는 날(STEP 7-4)
   그 자리에서 쓰고, 그때 경기별 예약도 함께 만든다.
"""
from __future__ import annotations

import inspect

import pytest

from app.flow.nodes import n05_evidence as N5


class _P:
    async def fetch(self, *a, **k):
        return []


class _R:
    async def get(self, k):
        return None


async def _run(vars_):
    from app.flow.ctx import Ctx
    from app.flow.state import State

    st = State.new({"id": "1", "sport": "kbo", "league": "KBO",
                    "home": "두산", "away": "KIA",
                    "starts_at": "2026-09-23T09:30:00+00:00"})
    st.sport = "baseball"
    st.pick_side = "home"
    st.n04_hyp = [{"id": "H_break", "vars": [{"var": v} for v in vars_]}]
    return await N5.run(st, Ctx(pool=_P(), redis=_R()))


@pytest.mark.asyncio
async def test_상한을_낮춰도_안_잘린다(monkeypatch):
    """🔴 이 단위의 전부 — **상한이 더 이상 조사를 끊지 않는다.**

    ⚠️ "모든 변수가 행을 남긴다"로 쓰면 안 된다 — 소스가 있는데 자료가 없어
       행이 안 나는 것(정상적인 미상)과 **잘리는 것**은 다르다. 그래서 상한을
       **1로 낮춰 놓고** 그보다 많은 행이 나오는지로 본다. 종전 코드였다면
       첫 행에서 끊겼다.
    """
    from app.flow import rules as R

    orig = R.get
    monkeypatch.setattr(
        R, "get",
        lambda k, d=None: 1 if k == "deepsearch_cap.per_game" else orig(k, d))
    names = list(R.vars_for("baseball"))
    out = await _run(names)
    got = [e["var"] for e in (out.n05_evidence or [])]
    assert len(got) > 1, f"상한 1 에서 끊겼다: {got}"


@pytest.mark.asyncio
async def test_소스_없는_변수는_위치와_무관하게_남는다():
    """⚠️ 목록 끝에 있어도 미실행 행이 남는다 — 종전에는 끝이 잘렸다."""
    from app.flow import rules as R

    names = [v for v in R.vars_for("baseball")
             if v not in ("weather", "travel_backtoback")]
    out = await _run(names + ["travel_backtoback", "weather"])
    got = {e["var"] for e in (out.n05_evidence or [])}
    assert {"weather", "travel_backtoback"} <= got, got


def test_예산_상한_문구가_남아_있지_않다():
    """🔴 **예산을 안 쓰는 노드가 예산 상한으로 끊고 있었다.**

    ⚠️ 주석을 뗀 코드 본문만 본다(D46, 이 저장소 11회).
    """
    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(N5.run).splitlines())
    assert "per_game_cap" not in src, "아직 상한으로 끊는다"


def test_검색_예약은_남겨_둔다():
    """⚠️ 기사 수집이 ⑤에 붙는 날 쓴다 — 지우지 않았다."""
    from app.flow.ctx import Ctx

    assert hasattr(Ctx, "take_search")
