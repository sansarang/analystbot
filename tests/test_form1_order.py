"""[FORM-1 / STEP 1-h] 폼 문자열의 **순서를 아무도 검증하지 않는다.**

🔴 생산자 둘 다 순서 가정이 **검증되지 않는다**:
     `app/collectors/football.py:168`
        "form": (row.get("form") or "").replace(",", "")
        → football-data.org 가 준 문자열을 **그대로** 넣는다. 순서 가정 **없음**.
     `app/research/deep.py:33·62`
        "form": "WWLWL (최근 5경기, 최신부터)"
        → LLM 에게 "최신부터"를 **요구**할 뿐, 돌아온 값을 검증하지 않는다.
   그 값은 `pipeline.py:462·466` 이 `season_h/season_a["form"]` 으로 싣는다.

🔴 왜 위험한가 — 소스가 순서를 뒤집어 내보내면 "직전 승"이 "직전 패"로 읽혀
   **정반대 판정**이 된다. 값이 그럴듯해서 아무도 모른다.
   (딥서치 실측 2026-09-13 J리그: 표만 보고는 방향을 알 수 없어, 기사의
    "고베 4연승"과 표 `L W W W W` 를 대조해서야 오래된→최신임을 확정했다.)

⚠️ v1.4 흐름은 이 결함이 **없다** — `n05` 의 `form_recent5` 는 `_LAST3_SQL`
   (`ORDER BY starts_at DESC`)로 DB 에서 만든다. 날짜가 순서를 정한다.
   고치는 대상은 **외부에서 문자열로 받는 경로**다.
"""
from __future__ import annotations

import pytest


def test_검증_함수가_있다():
    from app.engine import form_order as FO

    assert hasattr(FO, "verify")


@pytest.mark.asyncio
async def test_f_form_ok_최신이_맞으면_그대로():
    """소스가 '최신부터'로 줬고 DB 최근 1경기와 첫 글자가 맞다."""
    from app.engine.form_order import verify

    got = await verify("WLWDW", last_result="W")
    assert got["form"] == "WLWDW" and got["order"] == "verified", got


@pytest.mark.asyncio
async def test_f_form_flipped_두_경기_연속_역순이면_뒤집는다():
    """🔴 [가드 3] **1경기 대조로 뒤집지 않는다.**

    뒤집기는 최근 **2경기가 연속으로 역순 일치**할 때만이다. 한 경기는
    우연히 맞을 수 있고, 그 우연으로 폼 전체를 뒤집으면 더 나쁘다.
    """
    from app.engine.form_order import verify

    # 소스 "LLLDW"(오래된→최신) · 최근 = 직전 W, 그 전 D → 역순 2연속 일치
    got = await verify("LLLDW", recent=["W", "D"])
    assert got["form"] == "WDLLL" and got["order"] == "flipped", got


@pytest.mark.asyncio
async def test_f_form_single_mismatch_한_경기는_뒤집지_않는다():
    """🔴 [가드 3] 1경기만 있고 불일치 → 뒤집지 말고 **버린다.**"""
    from app.engine.form_order import verify

    got = await verify("LLLLW", recent=["W"])
    assert got["form"] is None and got["order"] == "unverified", got


@pytest.mark.asyncio
async def test_f_form_dated_날짜가_있으면_DB를_안_쓴다():
    """🔴 [가드 1] 날짜가 붙은 항목은 **정렬로 확정**한다."""
    from app.engine.form_order import verify

    items = [{"date": "2026-09-10", "result": "L"},
             {"date": "2026-09-17", "result": "W"},
             {"date": "2026-09-14", "result": "D"}]
    got = await verify("LLL", dated_items=items, db_state="stale")
    assert got["form"] == "WDL" and got["order"] == "dated_items", got
    assert got["reason"] is None, got


@pytest.mark.asyncio
async def test_f_form_db_stale_낡은_DB와는_대조하지_않는다():
    """🔴 [가드 2] 끝났어야 할 경기가 미기록이면 **대조 자체가 거짓**이다."""
    from app.engine.form_order import verify

    got = await verify("WWWWW", recent=["W"], db_state="stale")
    assert got["form"] is None and got["order"] == "db_stale", got
    assert got["reason"] == "form_db_stale", got


@pytest.mark.asyncio
async def test_f_form_no_schedule_일정이_없으면_따로_적는다():
    """⚠️ "낡았다"와 "아예 없다"를 섞지 않는다."""
    from app.engine.form_order import verify

    got = await verify("WWWWW", recent=["W"], db_state="none")
    assert got["order"] == "no_schedule" and got["reason"] == "form_no_schedule", got


def test_검증결과_이름은_한_곳이다():
    """🔴 보고·집계가 이 이름으로 센다 — 손으로 적지 않는다."""
    from app.engine import form_order as FO

    assert set(FO.ORDERS) == {"dated_items", "verified", "flipped",
                              "db_stale", "no_schedule", "unverified"}


@pytest.mark.asyncio
async def test_f_form_unverified_둘_다_아니면_null():
    """🔴 모르면 쓰지 않는다 — 폼은 null, 사유를 남긴다."""
    from app.engine.form_order import verify

    got = await verify("LLLLL", last_result="W")
    assert got["form"] is None, got
    assert got["reason"] == "form_order_unverified", got
    assert got["order"] == "unverified", got


@pytest.mark.asyncio
async def test_최근_경기를_모르면_null():
    """⚠️ `games(final)` 에 최근 경기가 없으면 검증 자체가 불가능하다."""
    from app.engine.form_order import verify

    got = await verify("WWWWW", last_result=None)
    assert got["form"] is None and got["reason"] == "form_order_unverified", got


def test_빈_폼은_조용히_통과하지_않는다():
    """⚠️ 반대 위험 — 빈 문자열을 'verified' 로 적으면 그것도 거짓이다."""
    import asyncio

    from app.engine.form_order import verify

    got = asyncio.run(verify("", last_result="W"))
    assert got["form"] is None and got["order"] == "unverified", got


def test_생산자_경로가_검증을_지난다():
    """🔴 만들어 놓고 안 이으면 그대로다 — `pipeline` 이 실제로 부르는가."""
    import inspect

    import app.pipeline as P

    src = inspect.getsource(P)
    assert "_verify_form_orders" in src, "pipeline 이 폼 방향 검증을 부르지 않는다"
    caller = inspect.getsource(P._verify_form_orders)
    assert "form_order" in caller and "verify" in caller


def test_검증_규칙은_한_곳이다():
    """🔴 사본 금지 — 생산자마다 각자 판정하면 어긋난다."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    hits = []
    for f in root.rglob("*.py"):
        if f.name == "form_order.py":
            continue
        body = "\n".join(ln for ln in f.read_text(encoding="utf-8").splitlines()
                         if ln.strip() and not ln.strip().startswith("#"))
        if "[::-1]" in body and "form" in body.lower():
            hits.append(str(f.relative_to(root)))
    assert not hits, f"폼 뒤집기 규칙이 다른 곳에도 있다: {hits}"
