"""[SWAP-1] 흐름 판정을 **결정 원장**에 남긴다 — 전환의 첫 걸음.

사용자 2026-09-22: "바꿔끼우기 진행해라… **버그가 있어서도 안 되고
옛 경로로 가서는 안 된다**"

🔴 **원장이 먼저인 이유.** 흐름이 구경로보다 나은지 **재지 않고** 갈아끼우면
   나빠져도 모른다. 오늘 만든 `decision_ledger` 와 지표 모듈이 그 자리다.

🔴 실측 2026-09-22 — 흐름은 살아 있고 깊이까지 돈다:
```
n01_prior 152경기 → n03_gate 152 → n04_hyp 111 → n06_verdict 111
→ n07_adjust 54 → n11_value 54 → n12_text 6 → n13_send 2
흐름 1회: games 19 · stopped {n11_no_value: 16, n06_unknown: 3} · sent 0
```
"""
from __future__ import annotations

import inspect

import pytest

from app.flow import record as R


class _S:
    """흐름 상태 대역."""

    run_id = "r1"
    game_id = "7"
    sport = "baseball"
    league = "KBO"
    stop_reason = None
    # 🔴 [LED-1 2026-09-23] **이 대역이 틀려 있었다.** ②는 `p_market` 을
    #    만들지 않는다 — `p` 에 `{home, draw, away}` 로 쓴다. 대역이 없는
    #    모양을 쓰는 바람에 이 계약이 740행 전건 시장 확률 누락을 못 잡았다.
    n02_market = {"p": {"home": 0.64, "draw": None, "away": 0.36}}
    n03_gate = {"label": "동의"}
    n07_adjust = [{"pp": -1.2}]
    n08_pcode = {"p_code_pick": 0.6522}
    n09_conf = {"grade": "B"}


class _Pool:
    def __init__(self, boom=False, dup=None):
        self.calls = []
        self.boom = boom
        self.dup = dup          # [LED-2] 같은 판단이 이미 있으면 여기에 행

    async def fetchrow(self, sql, *args):
        # 🔴 [LED-2 2026-09-23] 실제 풀에는 있는 메서드다. 대역에 없어서
        #    중복 검사가 AttributeError 로 떨어졌다(대역이 운영과 달랐다).
        if self.boom:
            raise RuntimeError("DB 없음")
        self.calls.append((sql, args))
        return self.dup

    async def execute(self, sql, *args):
        if self.boom:
            raise RuntimeError("DB 없음")
        self.calls.append((sql, args))


class _Ctx:
    def __init__(self, pool=None):
        self.pool = pool


def _code_only(mod) -> str:
    """주석·독스트링을 뗀 **코드 본문**.

    🔴 원문 grep 은 "`pick_ledger` 를 건드리지 않는다"는 **설명 자체**에
       걸린다. 이 저장소가 그 거짓 실패를 겪은 것이 여덟 번째다(D46).
    """
    import ast

    tree = ast.parse(inspect.getsource(mod))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not body or not isinstance(body, list):
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            body.pop(0)          # 독스트링 제거
    return ast.unparse(tree)     # 주석은 unparse 가 이미 버린다


def test_구경로_원장을_건드리지_않는다():
    """🔴 `pick_ledger` 는 구경로 소유다. 둘이 같은 표에 쓰면 **어느 경로의
    성적인지 갈리지 않는다.**"""
    code = _code_only(R)
    assert "decision_ledger" in code
    assert "pick_ledger" not in code, "흐름이 구경로 원장에 쓴다"
    assert R.ENGINE == "flow_v14", R.ENGINE


def test_확률이_없으면_남기지_않는다():
    """🔴 0 이나 0.5 로 채우면 원장이 거짓이 된다
    (`apply_code_verdict` 와 같은 규약)."""
    s = _S()
    s.n08_pcode = {"p_code_pick": None}
    assert R.pick_of(s) == (None, None, None)
    s.n08_pcode = {}
    assert R.pick_of(s) == (None, None, None)
    s.n08_pcode = {"p_code_pick": "x"}
    assert R.pick_of(s) == (None, None, None)


def test_우리쪽_확률로_바꿔_넣는다():
    """🔴 `p_code_pick` 은 **홈 기준**이다. 원정 픽에 그대로 쓰면 CLV 의
    부호가 뒤집힌다(CLV-3 이 겪은 실패)."""
    s = _S()
    side, pm, pk = R.pick_of(s)
    assert side == "home" and pm == 0.6522 and pk == 0.64

    s.n08_pcode = {"p_code_pick": 0.3294}
    s.n02_market = {"p": {"home": 0.34, "draw": None, "away": 0.66}}
    side, pm, pk = R.pick_of(s)
    assert side == "away"
    assert pm == round(1 - 0.3294, 4) and pk == round(1 - 0.34, 4)


def test_변환_규약이_한_곳이다():
    """🔴 사본 금지 — `learning.decisions._our_side_p` 가 원본이다."""
    src = inspect.getsource(R._our_side_p)
    assert "learning.decisions" in src


def test_시장이_없어도_판정은_남긴다():
    """⚠️ 시장 확률이 없다고 흐름 판정을 버리지 않는다 — CLV 만 못 잰다."""
    s = _S()
    s.n02_market = {"p": None, "market_missing": True}
    side, pm, pk = R.pick_of(s)
    assert side == "home" and pm == 0.6522 and pk is None


@pytest.mark.asyncio
async def test_원장에_한_줄이_들어간다():
    pool = _Pool()
    assert await R.record(_S(), _Ctx(pool)) is True
    # [LED-2] 중복 조회 1 + INSERT 1
    assert len(pool.calls) == 2, pool.calls
    sql, args = pool.calls[1]
    assert "INSERT INTO decision_ledger" in sql
    assert "ON CONFLICT" in sql and "DO NOTHING" in sql, "멱등이 아니다"
    assert args[0] == "flow_v14" and args[1] == 7
    assert args[4] == "home"
    # 🔴 [LED-2] **가격이 실린다** — 없으면 ROI 를 영영 못 낸다.
    assert args[5] is None or isinstance(args[5], float), args


@pytest.mark.asyncio
async def test_기록_실패가_흐름을_막지_않는다():
    """🔴 관측이 판정을 죽이면 안 된다."""
    assert await R.record(_S(), _Ctx(_Pool(boom=True))) is False
    assert await R.record(_S(), _Ctx(None)) is False
    assert await R.record(_S(), None) is False


@pytest.mark.asyncio
async def test_확률_없으면_아무것도_안_쓴다():
    pool = _Pool()
    s = _S()
    s.n08_pcode = {"p_code_pick": None}
    assert await R.record(s, _Ctx(pool)) is False
    assert pool.calls == [], "확률이 없는데 행을 넣었다"


def test_무엇을_보고_정했는지_남긴다():
    """🔴 조용한 기록을 만들지 않는다."""
    note = R.note_of(_S())
    for must in ("run=", "게이트=", "확신=", "조정="):
        assert must in note, note


def test_finish_가_원장을_부른다():
    """🔴 배선 확인 — 스냅샷과 같은 자리에서 남긴다.

    ⚠️ **주석을 떼고 본다** — 원문 grep 은 내 주석에 걸린다(D46, 이 저장소 7회).
    """
    from app.flow import run as FR

    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(FR.finish).splitlines())
    assert "from app.flow.record import record" in src
    i_rec = src.index("_rec(state, ctx)")
    i_snap = src.index('snapshot(state, "finish"')
    assert i_rec < i_snap, "스냅샷보다 뒤에 기록한다"
    assert "except Exception" in src, "기록 실패가 흐름을 죽인다"


def test_발송_스위치를_건드리지_않았다():
    """🔴 전환과 발송은 **다른 결정**이다."""
    code = _code_only(R)
    assert "pipeline_v14_send" not in code
    assert "send_telegram" not in code
