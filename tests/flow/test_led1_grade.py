"""[LED-1] 흐름 판정이 **원장에 남지만 채점되지 않는다.**

사용자 2026-09-23: "전부다 순서대로 수정해라" (①측정 장치부터)

🔴 실측 2026-09-23 16:00 운영:
```
decision_ledger   전체 1,118행 · result 368 · clv 96 · settled 0
  flow_v14    740행 · **채점 0**          ← 흐름 판정은 한 건도 안 세어진다
  bot_v14     369행 · 채점 359
  fable_chat    9행 · 채점 9
flow_v14 최근 5행:  p_market_at_decision = **None** (전건)
```

원인 둘:
🔴 **① 키가 안 맞는다.** `record.pick_of` 가 `n02_market["p_market"]` 을 읽는데
   ②는 `"p"` 에 `{home, draw, away}` 로 쓴다 — 740행 전건 시장 확률이 비었고
   그래서 **CLV 를 못 잰다.**
🔴 **② 채점하는 코드가 없다.** `result` 를 채우는 곳이 흐름 경로에 없다.

⚠️ 이것이 나머지 판단의 전제다 — 무엇이 맞았는지 셀 수 없으면 ⑦ 조정도
   ⑨ 확신도 고칠 근거가 없다.
"""
from __future__ import annotations

import pytest


class _S:
    run_id = "r1"
    game_id = "7"
    sport = "baseball"
    league = "KBO"
    stop_reason = None
    home = "두산"
    away = "KIA"
    pick_side = "home"
    # 🔴 ②가 실제로 쓰는 모양이다 — `p_market` 이 아니라 `p` 다.
    n02_market = {"p": {"home": 0.62, "draw": None, "away": 0.38},
                  "odds": {"home": 1.7, "away": 2.2}}
    n03_gate = {"gate": "동의"}
    n07_adjust = [{"pp": -1.2}]
    n08_pcode = {"p_code_pick": 0.6522}
    n09_conf = {"grade": "B"}


def test_시장_확률을_읽는다():
    """🔴 이 단위의 첫 결함 — 키가 안 맞아 740행이 비었다."""
    from app.flow import record as R

    side, p_model, p_mkt = R.pick_of(_S())
    assert side == "home"
    assert p_model == 0.6522
    assert p_mkt == 0.62, f"시장 확률을 못 읽는다: {p_mkt}"


def test_원정_픽이면_뒤집는다():
    """⚠️ CLV 부호가 뒤집히는 자리다(CLV-3 전례).

    🔴 [SIDE-1 2026-09-23] 종전에는 `p_code_pick` 만 0.3294 로 바꾸고
       방향이 따라 뒤집히기를 기대했다 — 그게 **확률로 방향을 되짚는**
       버그를 계약으로 굳힌 자리다. 방향은 ①이 정한다.
    """
    from app.flow import record as R

    s = _S()
    s.pick_side = "away"
    s.n08_pcode = {"p_code_pick": 0.3294}
    side, p_model, p_mkt = R.pick_of(s)
    assert side == "away"
    assert p_mkt == round(1 - 0.62, 4), p_mkt


def test_시장이_없으면_None_이다():
    """🔴 지어내지 않는다 — 시장이 없으면 CLV 를 못 잴 뿐이다."""
    from app.flow import record as R

    s = _S()
    s.n02_market = {"p": None, "odds": {}, "market_missing": True}
    side, p_model, p_mkt = R.pick_of(s)
    assert side == "home" and p_model == 0.6522 and p_mkt is None


# ── 채점 ────────────────────────────────────────────────────────────

def test_채점_함수가_있다():
    from app.learning import decisions as D

    assert hasattr(D, "grade_pending")


class _Pool:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def fetch(self, sql, *a):
        self.calls.append((sql, a))
        return self.rows

    async def execute(self, sql, *a):
        self.calls.append((sql, a))
        return "UPDATE 1"


@pytest.mark.asyncio
async def test_이긴_쪽을_win_으로_적는다():
    from app.learning import decisions as D

    rows = [{"id": 1, "side": "home", "market": "h2h", "line": None,
             "home_score": 5, "away_score": 3, "price_at_decision": 1.7},
            {"id": 2, "side": "away", "market": "h2h", "line": None,
             "home_score": 5, "away_score": 3, "price_at_decision": 2.2}]
    pool = _Pool(rows)
    got = await D.grade_pending(pool)
    assert got["graded"] == 2, got
    wrote = [a for sql, a in pool.calls if "UPDATE" in sql.upper()]
    flat = str(wrote)
    assert "win" in flat and "loss" in flat, flat


@pytest.mark.asyncio
async def test_무승부는_push_다():
    from app.learning import decisions as D

    pool = _Pool([{"id": 3, "side": "home", "market": "h2h", "line": None,
                   "home_score": 2, "away_score": 2, "price_at_decision": 1.9}])
    got = await D.grade_pending(pool)
    assert got["graded"] == 1
    assert "push" in str(pool.calls)


@pytest.mark.asyncio
async def test_점수가_없으면_건너뛴다():
    """🔴 **끝나지 않은 경기를 채점하지 않는다.**"""
    from app.learning import decisions as D

    pool = _Pool([{"id": 4, "side": "home", "market": "h2h", "line": None,
                   "home_score": None, "away_score": None,
                   "price_at_decision": 1.9}])
    got = await D.grade_pending(pool)
    assert got["graded"] == 0, got


@pytest.mark.asyncio
async def test_모르는_마켓은_건너뛴다():
    """🔴 **지어내지 않는다.** 총점·핸디 채점 규칙은 아직 없다."""
    from app.learning import decisions as D

    pool = _Pool([{"id": 5, "side": "over", "market": "totals", "line": 8.5,
                   "home_score": 5, "away_score": 4, "price_at_decision": 1.9}])
    got = await D.grade_pending(pool)
    assert got["graded"] == 0 and got.get("skipped"), got


def test_스케줄러가_부른다():
    import inspect

    import app.scheduler as S

    src = "\n".join(ln.split("#", 1)[0]
                    for ln in inspect.getsource(S).splitlines())
    # 🔴 **이름만 보면 거짓 통과한다** — `pick_ledger.grade_pending`(구경로)이
    #    이미 불리고 있어서 "grade_pending" 문자열은 원래부터 있었다.
    #    어느 모듈의 것인지까지 본다.
    assert "app.learning.decisions import grade_pending" in src \
        or "decisions.grade_pending" in src, "원장 채점이 안 불린다"
    assert "app.engine.pick_ledger import grade_pending" in src, \
        "구경로 채점이 사라졌다(반대 위험)"
