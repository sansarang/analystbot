"""단계 잠금 기계 계약 — v4 §13-2 · §9. [infra]

🔴 **잠금 자체가 틀리면 다른 모든 계약이 헛돈다.** 잠금이 아무것도 안 잠그면
   단계를 건너뛰어도 초록이고, 잠금이 원본과 어긋나면 새 단계가 소리 없이
   무방비로 열린다.

⚠️ 이 파일은 **잠기지 않은 자리**에 있어야 한다. 잠긴 디렉터리에 두면 잠금이
   고장났을 때 그것을 알려 줄 계약이 함께 사라진다.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import tests.stage_gate as SG
# 🔴 D46 헬퍼 — 독스트링·주석을 뺀 코드만 본다. 사본을 만들지 않는다.
#    ⚠️ 리뷰 N8: 종전에는 `tests.test_wiring` 에서 가져와 테스트 모듈끼리
#       엮였다. 비-테스트 헬퍼로 뺐다.
from tests._helpers import strip_docs

ROOT = Path(__file__).resolve().parents[1]
INBOX = "docs/fable/inbox/2026-09-29_v4.md"


def _v4_stages() -> list[int]:
    """🔴 **단계 목록을 베끼지 않는다.** v4 §9 표에서 읽는다.

    ⚠️ §2 의 STEP 표도 `| 0 |` 로 시작하는 행을 갖는다 — 절만 잘라 본다.
       처음 전체 문서에서 긁었더니 STEP 0~8 이 섞여 단계가 19개로 나왔다
       (실측 2026-09-30).
    🔴 **한 자리 수만 잡으면 안 된다**(리뷰 N1). 단계 10 이 생겼을 때
       그 행이 **조용히 빠진다.** 같은 병으로 `h2h_pattern` 을 놓친 적이 있다.
    🔴 그리고 **행 수를 대조한다** — 정규식이 빠뜨리면 그 자리에서 터진다.
    """
    text = (ROOT / INBOX).read_text(encoding="utf-8")
    sec = text.split("## 9. 단계별")[1].split("## 10.")[0]
    data = [ln for ln in sec.splitlines()
            if ln.startswith("|") and not re.match(r"^\|\s*-", ln)
            and not re.match(r"^\|\s*단계\s*\|", ln)]
    got = re.findall(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|", sec, re.M)
    assert len(got) == len(data), (
        f"§9 표 데이터 행 {len(data)}개 중 {len(got)}개만 뽑았다 — "
        f"정규식이 행을 빠뜨린다: {[g[0] for g in got]}")
    return [int(n) for n, _ in got]


def test_v4_의_단계를_전부_잠금표가_덮는다():
    """🔴 사본 금지 — 새 단계가 v4 에 생기면 **여기가 빨개져** 잠금을 요구한다.

    단계 0·1 은 잠그지 않는다(이미 승인됐고, 계약이 `tests/*.py` 에 평평하다).
    2 부터 9 까지가 잠금 대상이다.
    """
    want = [s for s in _v4_stages() if s >= 2]
    have = [g["stage"] for g in SG.load()["gates"]]
    assert have == want, f"잠금표 단계 {have} ≠ v4 §9 단계 {want}"


def test_각_단계는_앞_단계의_서명을_요구한다():
    """단계 N 은 단계 N-1 의 승인 서명 파일을 요구한다(§9 · §13-2)."""
    for g in SG.load()["gates"]:
        assert g["requires"] == f"v4_{g['stage'] - 1}_done.md", \
            f"단계 {g['stage']} 가 엉뚱한 서명을 본다: {g['requires']}"
        # 🔴 **`locks` 를 표에 적지 않는다**(리뷰 P4) — 규칙이 계산한다.
        assert "locks" not in g, \
            f"단계 {g['stage']} 가 locks 를 손으로 적었다 — 규칙에서 자라야 한다"
        assert SG.locks_of(g["stage"]) == [f"tests/stage{g['stage']}"]


def test_서명_형식이_사용자_원문을_담게_한다():
    """🔴 `APPROVED <ISO시각> <사용자 메시지 원문>`.

    ⚠️ 시각만 받고 원문을 안 받으면 **무엇에 대한 승인이었는지**가 사라진다.
       단계 0 의 서명이 그랬다(`> "승인" — 사용자, 2026-09-29`).
    """
    pat = re.compile(SG.load()["signature_pattern"], re.M)
    ok = pat.search('> APPROVED 2026-09-30 "승인 + 사고 기록으로 남긴다" — 사용자')
    assert ok, "인용 안의 정상 서명을 못 읽는다"
    assert ok.group(1) == "2026-09-30"
    assert "사고 기록" in ok.group(2), "사용자 원문을 안 잡는다"
    assert pat.search("APPROVED 2026-09-30T14:05+09:00 승인"), "ISO 시각을 못 읽는다"
    # 🔴 원문이 없으면 승인이 아니다
    assert not pat.search("APPROVED 2026-09-30"), "원문 없는 줄을 승인으로 읽는다"
    assert not pat.search("APPROVED 승인"), "시각 없는 줄을 승인으로 읽는다"


def test_단계_1_서명이_실제로_읽힌다():
    """지금 열린 단계가 **서명 때문에** 열린 것임을 확인한다."""
    cfg = SG.load()
    gate = next(g for g in cfg["gates"] if g["stage"] == 2)
    path, when, msg = SG.signature_of(gate, cfg)
    # ⚠️ **날짜를 베끼지 않는다**(리뷰 N2). 종전 판은 `when == "2026-09-30"` 을
    #    박아 둬서, 서명을 ISO 시각으로 고치거나 재승인하면 **거짓으로 빨개졌다.**
    assert when is not None, "단계 1 서명 시각을 못 읽었다"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}(T[\d:.+\-Z]+)?", when), when
    assert msg and msg.strip(), f"사용자 원문을 못 읽었다: {msg!r}"
    assert path.name == "v4_1_done.md"


def test_서명_없는_단계는_잠긴다():
    """🔴 아직 승인 안 된 단계가 **실제로** 잠겨 있나. [§13-2]

    ⚠️ 이 계약이 없으면 잠금이 전부 열려도 아무도 모른다.
    🔴 **기대 목록을 손으로 적지 않는다.** 종전 판은 `[3,4,5,6,7,8,9]` 를 박아
       뒀고, 단계 2 승인 서명이 들어오자 **정상 동작인데 빨개졌다**(실측
       2026-09-30 · 리뷰 N3 이 예고한 사본). 잠긴 단계는 **서명 유무에서
       자란다.**
    """
    cfg = SG.load()
    want = sorted(g["stage"] for g in cfg["gates"]
                  if SG.signature_of(g, cfg)[1] is None)
    locked = SG.locked_dirs()
    assert sorted(v["stage"] for v in locked.values()) == want
    # 🔴 잠금이 살아 있다는 증거 — 전부 열려 있으면 장식이다.
    #    단계 9 까지 전부 승인되면 이 줄을 지우고 잠금을 걷는다.
    assert want, "잠긴 단계가 하나도 없다 — 잠금이 장식인지 확인하라"
    for d, why in locked.items():
        assert why["why"].strip(), f"{d} 가 왜 잠겼는지 안 적혔다"
        assert "APPROVED" in why["why"], f"{d} 의 사유가 서명을 가리키지 않는다"


def _first_locked() -> str:
    """지금 **잠긴 첫 디렉터리**. 🔴 단계 번호를 손으로 적지 않는다.

    ⚠️ 승인이 하나 나갈 때마다 그 번호가 바뀐다 — 박아 두면 정상 동작에
       빨개진다(리뷰 N3).
    """
    locked = SG.locked_dirs()
    return min(locked, key=lambda d: locked[d]["stage"])


def test_잠긴_경로_판정이_하위까지_미친다():
    """디렉터리 안의 파일도 잠긴 것으로 봐야 한다 — 훅이 파일 단위로도 온다. [§13-2]"""
    d = _first_locked()
    assert SG.is_locked(ROOT / d) is not None
    assert SG.is_locked(ROOT / d / "test_x.py") is not None
    assert SG.is_locked(ROOT / "tests" / "stage2") is None, "열린 단계가 잠겼다"
    assert SG.is_locked(ROOT / "tests" / "test_judge.py") is None, \
        "단계 0·1 의 평평한 계약이 잠겼다 — 스위트가 스스로를 막는다"


def test_conftest_가_잠금을_실제로_배선한다():
    """★ 만든 것은 부르는 곳이 있어야 한다.

    🔴 `stage_gate` 를 만들어 두고 `conftest` 가 안 부르면 **잠금은 장식**이다.
       그래도 위의 계약들은 전부 초록이다 — 그것이 가장 위험한 모양이다.
    """
    src = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    # 🔴 **문자열로 보면 안 된다**(리뷰 B2). 실측 2026-09-30: 훅을 통째로 지우고
    #    낱말만 독스트링에 남기니 이 계약이 **초록**이었고 잠금은 죽어 있었다
    #    (288 passed — 단계 3 테스트가 수집됐다). 금지 방향엔 D46 대책을
    #    넣고 **존재 방향엔 안 넣은** 비대칭이 그 원인이다.
    #    → `FunctionDef` 가 실재하고 그 **본문이** 판단을 부르는지 본다.
    fns = {n.name: n for n in ast.walk(ast.parse(src))
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    hook = fns.get("pytest_ignore_collect")
    assert hook is not None, "수집 훅이 없다 — 독스트링에 이름만 있어도 안 된다"
    calls = {getattr(c.func, "attr", getattr(c.func, "id", ""))
             for c in ast.walk(hook) if isinstance(c, ast.Call)}
    assert "is_locked" in calls, "수집 훅이 잠금 판단을 부르지 않는다"
    # 🔴 skip 으로 때우면 "수집조차 되지 않는다"(§13-2)를 어긴다.
    # ⚠️ **D46 — 이 저장소에서 여섯 번째로 다친 자리.** 첫 판은 `#`·인용으로
    #    시작하는 줄만 걸렀는데, `conftest` 의 **독스트링 본문**이 "건너뛰기
    #    (skip) 하면 안 된다"고 *설명*하는 바람에 계약이 거짓으로 빨개졌다.
    #    문서가 금칙 낱말을 설명하는 것과 코드가 그것을 부르는 것은 다르다.
    assert "skip" not in strip_docs(src).lower(), \
        "잠금을 skip 으로 때웠다 — §13-2 는 '수집조차'라고 못 박았다"


def test_잠긴_단계를_보고에_항상_적는다():
    """🔴 **조용한 0 금지.** "286 passed" 만 보이면 잠긴 단계가 **없는 것처럼** 읽힌다.

    ⚠️ 수집 훅은 **존재하는 경로에만** 불린다. 그래서 잠긴 것만 세면
       `tests/stage3` 이 없는 동안 스위트는 아무 말도 하지 않는다 — 실측
       2026-09-30 에 그랬다. 디렉터리가 없어도 닫힌 단계를 말해야 한다.
    """
    src = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    fns = {n.name: n for n in ast.walk(ast.parse(src))
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    hook = fns.get("pytest_report_collectionfinish")
    assert hook is not None, "잠긴 것을 보고하지 않는다"
    calls = {getattr(c.func, "attr", getattr(c.func, "id", ""))
             for c in ast.walk(hook) if isinstance(c, ast.Call)}
    assert "locked_dirs" in calls, \
        "버린 경로만 센다 — 디렉터리가 없는 단계는 조용히 사라진다"


def test_수집_훅을_직접_불러_동작을_확인한다():
    """🔴 **구조만 보면 "있는데 아무것도 안 하는 훅"을 못 막는다**(리뷰 B2).

    실측 2026-09-30: 훅 본문을 `why = None` 으로 바꾸니(판단은 부르지만 결과를
    버린다) **288 passed** — 단계 3 테스트가 수집됐는데 계약 전부 초록이었다.
    `is_locked` 를 부르는지(구조)와 **그 답대로 경로를 버리는지**(동작)는 다르다.

    ⚠️ 그래서 훅을 **직접 부른다.** pytest 가 그것을 부르는지는 위의 구조 계약이,
       불렸을 때 옳게 답하는지는 여기가 본다.
    """
    import types

    import tests.conftest as C

    cfg = types.SimpleNamespace(stash={})
    locked = C.pytest_ignore_collect(ROOT / _first_locked() / "t.py", cfg)
    assert locked is True, \
        f"잠긴 단계의 경로를 버리지 않는다({locked!r}) — 잠금이 장식이다"
    opened = C.pytest_ignore_collect(ROOT / "tests" / "test_judge.py", cfg)
    assert opened is None, \
        f"단계 0·1 의 평평한 계약을 버린다({opened!r}) — 스위트가 스스로를 막는다"
    assert C.pytest_ignore_collect(ROOT / "tests" / "stage2" / "t.py", cfg) is None, \
        "승인된 단계 2 를 버린다"


def test_보고_훅을_직접_불러_닫힌_단계를_적는지_본다():
    """🔴 조용한 0 금지 — 보고 훅이 `[]` 만 돌려주면 잠긴 단계가 사라진다."""
    import types

    import tests.conftest as C

    out = C.pytest_report_collectionfinish(types.SimpleNamespace(stash={}))
    text = "\n".join(out)
    assert "단계 잠금" in text, f"닫힌 단계를 보고에 안 적는다: {out!r}"
    # 🔴 **`str(n) in text` 로 보면 헛돈다**(리뷰 P1). 보고 줄에 `(v4 §13-2)` 가
    #    있어서 `"3"` 은 단계 목록이 통째로 빠져도 참이었다 — `"9"` 만 의미가
    #    있었다. 내가 계속 고쳐 온 거짓 통과를 새 계약에서 또 만들었다.
    # 🔴 그리고 **기대값을 손으로 적지 않는다** — `locked_dirs()` 에서 자란다.
    m = re.search(r"닫힌 단계:\s*([\d,\s]+)", text)
    assert m, f"보고 줄에 닫힌 단계 목록이 없다: {out!r}"
    reported = {int(x) for x in m.group(1).replace(" ", "").strip(",").split(",")}
    want = {v["stage"] for v in SG.locked_dirs().values()}
    assert reported == want, f"보고한 닫힌 단계 {sorted(reported)} ≠ 실제 {sorted(want)}"


def test_잠긴_디렉터리가_사라지면_알린다():
    """🔴 **디렉터리를 통째로 지우면 어느 계약도 안 빨개졌다**(리뷰 N9).

    수집 수만 조용히 줄고 초록이다 — 계약이 사라진 것과 계약이 통과한 것을
    구분할 수 없다. 🔴 열린 단계의 디렉터리는 **실재해야** 한다. [§13-2]
    """
    cfg = SG.load()
    for gate in cfg["gates"]:
        n = gate["stage"]
        # ⚠️ **착수하지 않은 단계는 디렉터리가 없어도 된다.** 열렸다고 곧바로
        #    계약이 있는 것은 아니다 — 그 단계의 **보고서가 생긴 뒤**부터 요구한다.
        if not (ROOT / cfg["signature_dir"] / f"v4_{n}_done.md").exists():
            continue
        for d in SG.locks_of(n):
            assert (ROOT / d).is_dir(), \
                f"단계 {n} 의 보고서가 있는데 {d} 가 없다 — 계약이 사라졌나"
            assert list((ROOT / d).glob("test_*.py")), \
                f"{d} 에 계약이 하나도 없다"


def test_stage_gate_헬퍼가_전부_불린다():
    """🔴 `tests/stage_gate.py` 의 공개 함수가 **어느 고아 계약의 감시도 받지
    않는다**(리뷰 N4) — `test_wiring` 의 `mods` 는 `app/**` 만 본다.

    ⚠️ 만든 것에 부르는 곳이 있어야 한다. 여기서 그 자리를 메운다. [infra]
    """
    import inspect as _i

    used = (ROOT / "tests").rglob("*.py")
    code = "\n".join(strip_docs(p.read_text(encoding="utf-8")) for p in used
                     if p.name != "stage_gate.py")
    code += strip_docs((ROOT / "tests" / "stage_gate.py").read_text(encoding="utf-8"))
    orphans = [n for n, o in _i.getmembers(SG, _i.isfunction)
               if not n.startswith("_") and o.__module__ == "tests.stage_gate"
               and code.count(n) == 0]
    assert orphans == [], f"부르는 곳이 없다: {orphans}"
