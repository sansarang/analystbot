"""🔴🔴 **v5 §10-4 — 단계 게이트와 배포.** 여덟 칸이고 **사용자가 서명**한다.

지시문 §10-4 원문(배포 전 일곱 단계):

```
1. §8 데이터 모델·§9-3 계약 커버리지 → 전 테스트 통과 · 돌연변이 전부 빨강
2. §2~§4 에이전트+도구 → 정답지 5경기에서 깔때기 verified_vars ≥ 6
3. §5 검증층 → 지어낸 변수 주입 테스트(가짜 quote 10건)가 전부 폐기됨
4. 측정 1 통과 (70%/50%)
5. §6~§7 판정층·T-60 → 측정 2 통과
6. 실전 슬레이트 배포(발송 off) — 7일간 카드 생성·채점만, 계약 위반 0,
   자료 부족 30% 이하, 비용 하루 $3 이하
7. 발송 on — 사용자 승인
```

══════════════════════════════════════════════════════════════════
🔴🔴 **게이트 2·4·5 는 기준을 잃었다** — 사용자 결정 C(2026-10-04)
══════════════════════════════════════════════════════════════════

사용자 지시 2026-10-02: *"정답지는 없다 … 정답지는 지운다 … 스포츠는 정답이
없는거다."* 그리고 2026-10-03: *"나는 **예시를 준거다** … **0.85는 누가
맞는지는 모른다.**"* → 결정 **C**: `golden_v5.yaml` 은 **방법 예시**이고
정답지가 아니다.

⚠️ 그러면 §10-2(변수 재현율 70%/50%)·§10-3(카드 비교)은 **무엇과 견줄지가
   없다.** 🔴 그 게이트를 *"통과했다"* 고 적을 수 없고, *"실패했다"* 고도 적을
   수 없다 — **기준이 없다.**
🔴 그래서 상태를 **`기준상실`** 로 적는다. ⚠️ `보류`(아직 안 함)와 다르다:
   보류는 하면 되고, 기준상실은 **사용자가 새 기준을 주어야** 풀린다.

🔴 **내가 통과를 선언하지 않는다**(사용자 지시 2026-09-30). 서명은 사용자다.
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _gates() -> dict:
    from app import rules
    return rules.stage_gates()


def test_v5_10_4_여덟_칸이_선언돼_있다():
    """🔴 지시문의 배포 단계 **여덟 개** 전부. ⚠️ 번호가 뜻이다(순서다).

    🔴 처음에 **일곱**이라고 적었다 — 지시문에는 **8번**이 있다
    (*"원장 30건 → 등급 경계값 재보정"*). ⚠️ 그 줄이 사용자 지시 2026-10-02 와
    **정면으로 충돌한다**(원장으로 규칙을 고치지 않는다) — 그래서 더 중요하다.
    """
    got = _gates()
    assert sorted(got) == list(range(1, 9)), sorted(got)
    for n, row in got.items():
        assert str(row.get("what") or "").strip(), n
        assert str(row.get("criterion") or "").strip(), n
        assert row.get("state") in ("통과", "보류", "기준상실", "실패"), (n, row)


def test_v5_10_4_문서에서_자란다():
    """🔴🔴 **베끼지 않는다** — 일곱 줄이 문서에 있는지 대조한다(#1 사본 금지).

    ⚠️ 손으로 적은 표는 지시문이 바뀔 때 한 발 늦는다.
    """
    text = (ROOT / "docs" / "fable" / "inbox"
            / "2026-10-04_v5_solar.md").read_text(encoding="utf-8")
    # 🔴 §10-4 아래의 **번호 목록**이 일곱 줄인지 센다
    i = text.index("10-4 단계  게이트와  배포")
    seg = text[i:i + 2500]
    import re
    nums = {int(m) for m in re.findall(r"^(\d)\. ", seg, re.M)}
    assert nums == set(range(1, 9)), (
        f"🔴 문서에서 배포 단계를 {sorted(nums)} 로 읽었다 — **여덟**이어야 한다")


def test_v5_10_4_정답지_게이트는_기준상실이다():
    """🔴🔴 **결정 C** — 정답지에 기댄 게이트는 *통과/실패* 를 말할 수 없다.

    ⚠️ 게이트 2(정답지 5경기) · 4(측정 1) · 5(측정 2)가 그것이다.
    🔴 *"통과"* 로 적으면 **기준 없이 통과**를 선언하는 것이고, 그것이 사용자가
       2026-10-03 에 지적한 바로 그 함정이다(*"0.85는 누가 맞는지는 모른다"*).
    """
    got = _gates()
    # 🔴 정답지에 기댄 셋
    for n in (2, 4, 5):
        assert got[n]["state"] == "기준상실", (n, got[n])
        why = str(got[n].get("why") or "")
        assert "정답지" in why or "결정 C" in why, (n, why)
    # 🔴🔴 **8번은 다른 충돌이다** — 원장으로 규칙을 고치지 않는다(2026-10-02).
    #    ⚠️ 처음에 넷을 한 묶음으로 봤다. 그 둘은 **다른 까닭**이고, 섞으면
    #       *"정답지가 없어서"* 로 읽힌다 — 8번은 정답지와 무관하다.
    assert got[8]["state"] == "기준상실", got[8]
    why8 = str(got[8].get("why") or "")
    assert "2026-10-02" in why8 and "검증" in why8, why8
    assert "재보정" in why8, "🔴 그 줄이 무엇과 충돌하는지 안 적혀 있다"


def test_v5_10_4_게이트_1은_기계가_답한다():
    """🔴 게이트 1 은 *"전 테스트 통과 · 돌연변이 전부 빨강"* 이다 — **기계**다.

    ⚠️ 그래서 그 칸만 코드가 상태를 말할 수 있다. 🔴 나머지는 사용자 서명이다.
    """
    got = _gates()
    assert got[1].get("machine") is True
    for n in (2, 3, 4, 5, 6, 7, 8):
        assert not got[n].get("machine"), n


def test_v5_10_4_서명은_사용자다():
    """🔴🔴 **내가 통과를 선언하지 않는다**(사용자 지시 2026-09-30).

    ⚠️ `통과` 로 적힌 칸은 **서명 파일**이 있어야 한다(`docs/fable/stages/`).
    """
    got = _gates()
    stages = ROOT / "docs" / "fable" / "stages"
    for n, row in got.items():
        if row.get("state") != "통과":
            continue
        sig = str(row.get("signed") or "")
        assert sig, f"🔴 게이트 {n} 이 `통과` 인데 **서명이 없다**"
        assert (stages / sig).exists(), (
            f"🔴 게이트 {n} 의 서명 파일이 없다: {sig}")


def test_v5_10_4_배포는_마지막_칸이다():
    """🔴 *"발송 on — 사용자 승인"* 이 **일곱 번째**다.

    ⚠️ `SEND_ENABLED` 가 켜져 있으면서 그 칸이 `통과` 가 아니면 **계약 실패**다.
    """
    from app.config import get_settings
    got = _gates()
    assert "발송" in got[7]["what"], got[7]
    if get_settings().send_enabled:
        assert got[7]["state"] == "통과", (
            "🔴 발송이 켜져 있는데 게이트 7 이 통과가 아니다 — §11-11 위반")


def test_v5_10_4_6번_칸의_수가_적혀_있다():
    """🔴 게이트 6 은 수가 넷이다 — *"계약 위반 0 · 자료 부족 30% 이하 · 비용
    하루 $3 이하 · 7일"*. ⚠️ 수를 글자로만 적으면 아무도 재지 못한다."""
    row = _gates()[6]
    nums = row.get("numbers") or {}
    assert int(nums.get("days")) == 7, nums
    assert int(nums.get("violations_max")) == 0, nums
    assert float(nums.get("insufficient_max_pct")) == 30, nums
    assert float(nums.get("usd_per_day_max")) == 3, nums
    # 🔴 **비용 상한은 `config/llm.yaml` 과 같은 수여야 한다**(두 곳이 갈리면
    #    하나가 거짓이다)
    from app import rules
    assert float(nums["usd_per_day_max"]) == float(
        rules.llm_budget()["per_day_usd"]), (
        "🔴 게이트 6 의 하루 상한과 `llm.yaml` 의 `per_day_usd` 가 다르다")


def test_v5_10_4_발송_경로가_게이트를_묻는다():
    """🔴🔴 **돌연변이 F 가 통과했다**(2026-10-04).

    `rules.stage_gates().get(7)` 를 `{"state": "통과"}` 로 바꿔도 **초록**
    이었다 — 표를 만들어 두고 **발송 경로가 묻는지** 아무도 안 봤다.
    🔴 `SEND_ENABLED` 한 줄은 실수로도 켜진다. 게이트 표는 **서명 파일**을
       요구하므로 두 겹이고, 그 두 번째 겹이 **이어져 있어야** 겹이다(#2).
    """
    import ast
    import inspect
    import textwrap

    from app import analyze
    tree = ast.parse(textwrap.dedent(inspect.getsource(analyze.deliver)))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") == "stage_gates"]
    assert calls, (
        "🔴 발송 경로가 §10-4 게이트를 **묻지 않는다** — `SEND_ENABLED` 한 줄이 "
        "켜지면 그대로 나간다(두 겹이 아니다)")
    # 🔴 그리고 **7번 칸**을 봐야 한다(아무 칸이나가 아니다)
    src = textwrap.dedent(inspect.getsource(analyze.deliver))
    assert "(7)" in src or "[7]" in src, (
        "🔴 게이트 표를 읽는데 **7번 칸**을 안 본다 — 발송은 마지막 칸이다")


def test_v5_10_4_기동이_게이트를_로그에_남긴다():
    """🔴 *"무엇이 남았나"* 를 로그만 보고 알 수 있어야 한다(#3 조용한 0 금지)."""
    import ast
    import inspect
    import textwrap

    from app import scheduler
    tree = ast.parse(textwrap.dedent(inspect.getsource(scheduler.main)))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") == "stage_gates"]
    assert calls, (
        "🔴 기동이 §10-4 게이트 표를 **안 남긴다** — 어느 칸이 열려 있는지 "
        "로그만 보고는 알 수 없다")

