"""SMK-1 — 스모크가 **0경기를 통과로 보고하지 않는다.**

🔴 실측 2026-09-11 13:37. 로컬 DB 에 오늘 슬레이트가 없는 상태로
   `tools/smoke_e2e.py --sport kbo,npb` 를 돌렸더니:

       ✅ ①수집 0/0 PASS  …  ✅ ⑩안정성 0/0 PASS
       ── FAIL 원인 ──
          없음

   같은 시각 운영에는 KBO 8건·NPB 3건이 있었다. **아무것도 검사하지 않고
   전부 통과했다고 말한 것이다.** `ok == tot` 가 `0 == 0` 으로 참이 됐다.

   CLAUDE.md 5대 반복 결함의 **"조용한 성공"**(분모가 사라지는 실패)이다.
   그리고 이 도구는 종료 코드도 내지 않아 게이트에 걸 수 없었다.
"""

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from smoke_e2e import Result, report  # noqa: E402


def _run(results, skipped=None):
    """⚠️ `skipped` 가 없으면 **인자 하나로** 부른다.

    수정 전 `report()` 는 인자가 하나뿐이라, 둘로 부르면 TypeError 로 죽는다.
    그러면 "시그니처가 다르다"로 실패하고 정작 **결함 자체를 겨눈 단언**
    (0경기를 PASS 라고 말한다)에 닿지 못한다.
    """
    buf = io.StringIO()
    with redirect_stdout(buf):
        ok = report(results) if skipped is None else report(results, skipped)
    return ok, buf.getvalue()


def test_대상이_0이면_통과가_아니다():
    ok, out = _run([])
    assert ok is False, "0경기를 통과로 보고했다"
    assert "0/0 PASS" not in out, out
    assert "대상 0경기" in out


def test_0경기_사유가_보고에_남는다():
    """단순 실패가 아니라 **무엇이 0이었는지**가 보여야 한다 — 휴식일인지
    수집 실패인지는 사람이 판단한다."""
    ok, out = _run([], ["kbo 2026-09-11", "npb 2026-09-11"])
    assert ok is False
    assert "kbo 2026-09-11" in out and "npb 2026-09-11" in out


def test_한_종목만_0이어도_잡는다():
    """전부 0 과 한 종목만 0 은 다른 사건이다. 둘 다 통과가 아니다."""
    r = _ok_result()
    ok, out = _run([r], ["npb 2026-09-11"])
    assert ok is False
    assert "npb 2026-09-11" in out


def test_전부_통과하면_통과다():
    """반대 위험 — 가드가 정상까지 실패로 만들면 안 된다."""
    ok, out = _run([_ok_result()])
    assert ok is True, out
    assert "없음" in out


def test_한_단계라도_실패하면_통과가_아니다():
    ok, out = _run([_fail_result()])
    assert ok is False
    assert "터졌다" in out


def _ok_result() -> Result:
    r = _blank()
    for s in _steps():
        r.steps[s] = (True, "")
    return r


def _fail_result() -> Result:
    r = _blank()
    steps = _steps()
    for s in steps:
        r.steps[s] = (True, "")
    r.steps[steps[0]] = (False, "터졌다")
    return r


def _blank() -> Result:
    import smoke_e2e as sm

    try:
        return sm.Result(sport="kbo", label="A@B")
    except TypeError:
        r = sm.Result.__new__(sm.Result)
        r.sport, r.label, r.steps = "kbo", "A@B", {}
        return r


def _steps():
    import smoke_e2e as sm

    return list(sm.STEPS)


@pytest.mark.parametrize("bad", [0])
def test_종료코드를_낼_수_있다(bad):
    """🔴 종전에는 무엇이 나와도 exit 0 이라 게이트에 걸 수 없었다."""
    src = (Path(__file__).resolve().parent.parent
           / "tools" / "smoke_e2e.py").read_text(encoding="utf-8")
    assert "raise SystemExit(1)" in src, "실패해도 종료 코드가 0 이다"
