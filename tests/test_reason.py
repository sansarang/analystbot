"""🔴🔴 **실패한 조건이 사유를 정한다** — 4단계(사용자 설계 2026-10-03).

> 사유 문자열을 **사람이 쓰지 않는다** — 실패한 `if` 문이 enum 을 돌려준다.

══════════════════════════════════════════════════════════════════
🔴 왜 — 거짓 사유가 사용자를 **두 번** 헛돌게 했다
══════════════════════════════════════════════════════════════════

실측 2026-10-03: 봇이 `Croatia` 로 적어 놓고 `크로아티아` 로 되찾아 실패한 뒤
*"질문 창 밖이다 — 날짜를 지정해 다시 물어라"* 라고 적었다. 🔴 **날짜는 맞았고
이름이 달랐다.** 사용자가 날짜를 지정해 다시 물었고 **같은 자리에서 또 막혔다.**

⚠️ 문장을 자리마다 쓰면 *"무엇이 막았나"* 와 *"무엇이 막았다고 내가 생각했나"* 가
   갈린다. 🔴 enum → 문장이 **한 표**이면 그 거짓이 생길 자리가 없다.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

import pytest

from app import matchref
from app.matchref import SAY, Reason, say

ROOT = Path(__file__).resolve().parents[1]


def test_모든_사유에_사용자_문장이_있다():
    """🔴 빠진 사유가 있으면 그 자리에서 **사용자가 아무 말도 못 듣는다**."""
    missing = [r for r in Reason if r is not Reason.OK and r not in SAY]
    assert not missing, f"사용자 문장이 없는 사유: {missing}"
    for r, text in SAY.items():
        # ⚠️ 표시는 🔴 또는 ⚠️ 다 — **우리 버그가 아닌 사유**(장애·예산)는
        #    ⚠️ 로 적는 것이 맞다(v5-A `deepseek_unavailable` 이 그 꼴이다).
        assert text.strip() and ("🔴" in text or "⚠️" in text), r


def test_다시_물어서_풀리는지를_구조로_가른다():
    """🔴🔴 그 구분이 **거짓말을 막는다**.

    ⚠️ `fixable_by_asking_again` 이 거짓인데 *"다시 물어라"* 라고 적으면 사용자가
       헛돈다 — 실측에서 정확히 그 일이 있었다.
    """
    assert Reason.OUT_OF_WINDOW.fixable_by_asking_again
    assert Reason.AMBIGUOUS.fixable_by_asking_again
    # 🔴 **이름·수집 문제는 다시 물어도 안 풀린다**
    assert not Reason.NAME_UNRESOLVED.fixable_by_asking_again
    assert not Reason.NOT_COLLECTED.fixable_by_asking_again
    assert Reason.NAME_UNRESOLVED.is_our_bug
    assert Reason.NOT_COLLECTED.is_our_bug
    # 🔴 **둘이 겹치면 안 된다** — 겹치면 그 분류가 뜻을 잃는다
    for r in Reason:
        if r is Reason.OK:
            continue
        assert not (r.fixable_by_asking_again and r.is_our_bug), r


def test_문장과_분류가_어긋나지_않는다():
    """🔴🔴 **표 자신이 거짓말하지 않게** 본다.

    ⚠️ *"다시 물어라"* 라고 적어 놓고 `fixable_by_asking_again` 이 거짓이면 그
       표가 바로 그 거짓말이다 — 실측에서 난 사고를 표 안에서 재현한 꼴이다.
    """
    for r, text in SAY.items():
        tells_retry = ("다시 물어라" in text) or ("지목해라" in text) \
            or ("적어 달라" in text)
        if tells_retry:
            assert r.fixable_by_asking_again, f"{r}: 다시 물으라는데 안 풀린다"
        if r.is_our_bug:
            assert "다시 물어도 같다" in text, f"{r}: 안 풀린다고 안 적었다"


def test_실패_조건이_enum_을_넣는다():
    """🔴 조회·탐색이 **실패할 때마다** 그 조건이 enum 을 넣어야 한다.

    ⚠️ 빠뜨리면 그 실패만 `None` 으로 남고, 부르는 쪽이 *"모르겠다"* 를 아무
       문장으로나 메우게 된다.
    """
    from app import findgame, slate
    for fn in (slate.find, slate.by_key, findgame.find):
        code = ast.unparse(ast.parse(textwrap.dedent(inspect.getsource(fn))))
        assert ".reason = " in code, fn.__qualname__
        # 🔴 `why` 만 적고 `reason` 을 안 넣는 자리가 없나 — 수로 본다
        assert code.count(".why = ") <= code.count(".reason = "), \
            f"{fn.__qualname__}: 사유 문장만 적고 분류를 안 넣는 자리가 있다"


def test_사용자_문장을_손으로_쓰지_않는다():
    """🔴🔴 **구조 계약** — `answer` 가 사유 문장을 짓는 순간 표가 뜻을 잃는다.

    ⚠️ 종전엔 `answer` 안에 `{Reason.X: "…"}` 표를 **또** 들고 있었다(사본).
       한쪽만 고치면 사용자에게 보이는 말과 분류가 갈린다.
    """
    from app import analyze
    code = ast.unparse(ast.parse(textwrap.dedent(
        inspect.getsource(analyze.answer))))
    assert "say(look.reason" in code
    # 🔴 **표를 두 번 짓지 않는다**
    for word in ("Reason.OUT_OF_WINDOW:", "Reason.AMBIGUOUS:"):
        assert word not in code, f"`answer` 가 사유 표를 또 들고 있다: {word}"


def test_모르는_사유를_조용히_넘기지_않는다():
    """🔴 #3 조용한 0 금지 — 표에 없는 사유가 와도 **빈 문자열을 내지 않는다**."""
    class _Fake:
        value = "새로운사유"

    got = say(_Fake())            # type: ignore[arg-type]
    assert "새로운사유" in got and got.strip()


def test_사유를_쓰는_곳이_한_모듈이다():
    """🔴 `Reason` 이 여러 파일에 복제되면 그 순간 뜻이 갈린다(사본 금지)."""
    hits = []
    for p in sorted((ROOT / "app").rglob("*.py")):
        src = p.read_text(encoding="utf-8")
        if "class Reason(Enum)" in src:
            hits.append(str(p.relative_to(ROOT)))
    # ⚠️ **v5 §8-6 으로 자리가 옮겼다**(2026-10-04) — 사유는 전 구간(검색·읽기·
    #    검증·판정·예산)을 덮으므로 입구 모듈이 들 것이 아니다.
    #    🔴 **여전히 한 파일이다** — 그것이 이 계약의 요점이고 자리만 바뀌었다.
    assert hits == ["app/reasons.py"], hits
    assert matchref.Reason is Reason


@pytest.mark.asyncio
async def test_빈_열쇠와_없는_열쇠를_가른다():
    """🔴 *"무엇을 물었는지 모르겠다"* 와 *"그것이 표에 없다"* 는 처방이 다르다."""
    from app import slate

    class _Pool:
        async def fetch(self, *a, **k):
            return []

    assert (await slate.by_key(_Pool(), "")).reason is Reason.NO_QUERY
    assert (await slate.by_key(_Pool(), "x-1")).reason is Reason.MATCH_NOT_FOUND
