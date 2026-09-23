"""[VAL-B] ⑪이 λ 확률을 버리고 투표만 믿었다. **양쪽을 다 본다.**

사용자 2026-09-23: "엣지 −13.14%는 역배일 가능성도 있는거야?" →
"결함을 해결해야 한다… 코드 수정계획부터 얘기해라" → 계획 승인

🔴 **실물 g16449 토론토@볼티모어 (09-24 02:35 KST)**:
```
λ 모델    over 41.81%  under 58.19%      ← 언더를 가리킨다
증거 투표  {"side":"over","for":2}        ← 오버라고 한다
종전 코드  side_c = [오버만] → best over −13.14%p → 거절
실재한 것  under **+8.44%p**              ← 문턱(2.0)을 넘는데 아무도 안 봤다
```

⚠️ **"−13.14 면 반대는 +13.14" 가 아니다.** 비그 때문에 +8.44 다 —
   쪽마다 `p − 1/배당` 을 **따로** 계산해야 한다(딥서치가 경고한 자리).

⚠️ 과거 자료로는 투표와 λ 중 **어느 쪽이 나은지 결론 못 낸다**(n=10~12).
   확인된 것은 "자주 갈린다"(4건 중 3건)뿐이다. 그래서 투표를 **지우지 않고**
   확신도로 옮겨 **잴 수 있게** 한다.
"""
from __future__ import annotations

import inspect

import pytest

from app.flow.nodes import n11_value as N11

#: g16449 실물 — 총점 7.0 · 오버 1.82 · 언더 2.01
_TOTAL = {"line": 7.0, "over": 1.82, "under": 2.01}
_OURS = {"total_over": {7.0: 0.4181}, "total_under": {7.0: 0.5819}}


class _S:
    game_id = "16449"
    sport = "baseball"
    league = "MLB"
    home = "Baltimore Orioles"
    away = "Toronto Blue Jays"
    hyp_side = pick_side = "home"
    n01_prior = {"p_home": 0.5439, "p_away": 0.4561}
    n03_gate = {"gate": "가치의심"}
    n09_conf = {"grade": "A"}
    n10_rejudge = None
    n11_value = None

    def __init__(self, *, over_dir=-1, under_dir=0, want="total",
                 st_dir=None, bp_dir=None):
        self.n02_market = {
            "p": {"home": 0.5274, "draw": None, "away": 0.4726},
            "odds": {"home": 1.81, "away": 2.02},
            "derivatives": {"total": dict(_TOTAL)},
            "move": {"open_home": 0.5312, "now_home": 0.5274, "move_pp": -0.38}}
        self.n08_pcode = {"p_code_pick": 0.5695, "ours_markets": _OURS,
                          "model_probs": {}}
        self.n04_hyp = [{"id": "H_break", "market": want, "vars": []}]
        # 🔴 투표 규칙(`total_direction`)을 그대로 따른다:
        #    어느 쪽이든 선발·불펜이 **음수** → 오버 표
        #    선발이 **양 팀 모두 양수** → 언더 표
        #    ⚠️ 처음에 `{home:0, away:1}` 로 언더를 기대했는데 규칙은
        #       **양 팀 다** 양수를 요구한다 — 픽스처가 규칙을 잘못 흉내 냈다.
        self.n05_evidence = [
            {"var": "starter_recent3",
             "direction": dict(st_dir or {"home": 0, "away": over_dir},
                               dev=0.4)},
            {"var": "bullpen_3d",
             "direction": dict(bp_dir or {"home": 0, "away": under_dir},
                               dev=0.4)}]


class _Ctx:
    inject: dict = {}
    pool = None
    redis = None


def _agree_ok(monkeypatch, ok=True):
    """시장 동의 검사는 이 단위의 주장이 아니다 — 고정한다."""
    monkeypatch.setattr(N11, "_market_agrees", lambda *a, **k: ok)


# ── 핵심 ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_투표가_오버여도_λ가_언더면_언더를_고른다(monkeypatch):
    """🔴 **이 계약이 이 단위의 전부다.** g16449 실물."""
    _agree_ok(monkeypatch)
    s = _S(over_dir=-1, under_dir=-1)          # 투표 → 오버 2표
    assert N11.total_direction(s)["side"] == "over", "전제가 깨졌다"
    await N11.run(s, _Ctx())
    st = s.n11_value.get("structure")
    assert st, s.n11_value
    assert st["market"] == "total_under", s.n11_value
    assert abs(st["edge_pp"] - 8.44) < 0.05, st


@pytest.mark.asyncio
async def test_채택한_쪽_엣지가_양쪽_중_최대다(monkeypatch):
    _agree_ok(monkeypatch)
    s = _S(over_dir=-1, under_dir=-1)
    await N11.run(s, _Ctx())
    cands = N11._structure_candidates(s)
    best = max(c["edge_pp"] for c in cands if c["market"].startswith("total"))
    assert s.n11_value["structure"]["edge_pp"] == best


def test_엣지는_쪽마다_따로_계산한다():
    """🔴 딥서치 경고 — "음수 엣지가 곧 반대쪽 값어치를 뜻하지 않는다"(비그).
    `-13.14` 의 반대는 `+13.14` 가 아니라 **+8.44** 다."""
    c = {x["market"]: x["edge_pp"] for x in N11._structure_candidates(_S())}
    assert abs(c["total_over"] - (-13.14)) < 0.05
    assert abs(c["total_under"] - 8.44) < 0.05
    assert abs(c["total_over"] + c["total_under"]) > 4.0, "한쪽에서 빼서 만들었다"


# ── 투표는 확신도다 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_투표와_반대면_등급이_내려간다(monkeypatch):
    from app.flow import rules as R

    _agree_ok(monkeypatch)
    s = _S(over_dir=-1, under_dir=-1)
    await N11.run(s, _Ctx())
    want = str(R.get("value.vote_conflict_grade", "C"))
    assert s.n11_value["struct_grade"] == want, s.n11_value
    assert "반대" in (s.n09_conf or {}).get("struct_reason", ""), s.n09_conf


@pytest.mark.asyncio
async def test_투표와_같으면_종전_등급이다(monkeypatch):
    """⚠️ 반대 위험 — 갈리지 않는 경기의 결과가 바뀌면 안 된다."""
    _agree_ok(monkeypatch)
    s = _S(st_dir={"home": 1, "away": 1},      # 양 팀 선발 호재 → 언더 투표
           bp_dir={"home": 0, "away": 0})
    assert N11.total_direction(s)["side"] == "under"
    await N11.run(s, _Ctx())
    assert s.n11_value["structure"]["market"] == "total_under"
    assert s.n11_value["struct_grade"] == "A", s.n11_value


@pytest.mark.asyncio
async def test_투표가_없어도_λ로_평가한다(monkeypatch):
    """🔴 종전에는 "총점 방향 미정"으로 **전건 거절**이었다."""
    _agree_ok(monkeypatch)
    s = _S(over_dir=0, under_dir=0)
    assert N11.total_direction(s)["side"] is None
    await N11.run(s, _Ctx())
    assert s.n11_value["structure"], s.n11_value
    assert s.n11_value["struct_grade"] == "B"


# ── 관문은 살아 있다 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_시장_동의는_채택한_쪽으로_본다(monkeypatch):
    """🔴 투표 쪽으로 검사하면 엉뚱한 쪽의 이동을 본다."""
    seen = []
    monkeypatch.setattr(N11, "_market_agrees",
                        lambda st, cand, side: seen.append((cand["market"], side)) or True)
    s = _S(over_dir=-1, under_dir=-1)
    await N11.run(s, _Ctx())
    assert seen and seen[-1] == ("total_under", "under"), seen


@pytest.mark.asyncio
async def test_문턱과_오류의심이_살아_있다(monkeypatch):
    from app.flow import rules as R

    _agree_ok(monkeypatch)
    # 엣지가 문턱 미만이면 거절
    s = _S()
    s.n08_pcode["ours_markets"] = {"total_over": {7.0: 0.55},
                                   "total_under": {7.0: 0.50}}
    await N11.run(s, _Ctx())
    assert s.n11_value["structure"] is None or "문턱" in str(
        s.n11_value.get("reject_reason")) or "<" in str(s.n11_value.get("reject_reason"))
    # 엣지가 너무 크면 오류의심
    s2 = _S()
    s2.n08_pcode["ours_markets"] = {"total_over": {7.0: 0.20},
                                    "total_under": {7.0: 0.80}}
    await N11.run(s2, _Ctx())
    assert "오류의심" in str(s2.n11_value.get("reject_reason")), s2.n11_value


@pytest.mark.asyncio
async def test_시장_동의_실패는_그대로_거절이다(monkeypatch):
    _agree_ok(monkeypatch, ok=False)
    s = _S(over_dir=-1, under_dir=-1)
    await N11.run(s, _Ctx())
    assert "시장 동의 실패" in str(s.n11_value.get("reject_reason"))


# ── 되돌릴 길 ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_both_sides_false면_종전_동작이다(monkeypatch):
    """🔴 나빠지면 한 줄로 되돌린다."""
    _agree_ok(monkeypatch)
    real = N11.R.get
    monkeypatch.setattr(N11.R, "get",
                        lambda k, d=None: False if k == "value.both_sides" else real(k, d))
    s = _S(over_dir=-1, under_dir=-1)
    await N11.run(s, _Ctx())
    # 종전: 투표(오버) 쪽만 보고 −13.14 → 문턱 미만으로 거절
    assert s.n11_value.get("structure") is None or \
        s.n11_value["structure"]["market"] == "total_over", s.n11_value


def test_스위치와_등급표가_config에_있다():
    from app.flow import rules as R

    assert R.get("value.both_sides") is True
    assert str(R.get("value.vote_conflict_grade")) in ("A", "B", "C")
    assert R.get("value.allow_no_vote") is True
    # ⚠️ **기본값은 사본이 아니다.** `R.get(키, 기본)` 은 이 저장소의 규약이고
    #    설정이 없을 때의 안전망이다. 잠글 것은 "코드가 설정을 **읽는가**"다 —
    #    처음에 기본값까지 잡아서 내 계약이 거짓으로 실패했다.
    src = inspect.getsource(N11._struct_grade)
    assert 'R.get("value.vote_conflict_grade"' in src, "설정을 안 읽는다"
    assert 'R.get("value.no_vote_grade"' in src, "설정을 안 읽는다"


def test_투표_함수를_지우지_않았다():
    """🔴 신호가 없다는 근거가 없다(n=12). 역할만 옮긴다."""
    assert callable(N11.total_direction)
    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(N11.run).splitlines())
    assert "total_direction(state)" in src
    assert 'endswith(vote["side"])' not in src, "아직 투표로 후보를 버린다"
