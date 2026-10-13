"""🔴🔴 **대회 이력 칸 검증**(수정 지시 2026-10-14c · CR1~CR6).

> 1 0-0 누락 재발 점검 — 경기 결과 칸(`scoreStr`·`finished`)으로 센다.
>   계약 테스트: 0-0 경기가 **무로 집계**되는지(스포르팅 아스날 원정 0-0 사례).
> 2 "직전 2시즌" = 지금 시즌 **제외** 직전 두 시즌 + (별도 줄) 지금 시즌 진행분.
>   리그 단계·플레이오프·토너먼트 **전부 포함** · 중립 경기는 **따로 표시**.
> 3 외부 대조가 끝나기 전에는 🔴 "검증 전 — 판단에 쓰지 말 것" 꼬리표.

⚠️ **왜 빠졌나** — `neutral: ["final"]` 을 **부분 문자열**로 맞춰
   `Quarter-Finals`·`Semi-Finals` 가 중립으로 잡혀 그 단계가 통째로 빠졌다.
   0-0 은 득실에도 자취가 없어(0·0) 눈에 더 늦게 띄었다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))


def _build(rows):
    from fit_comp_record import build
    return build("league:UCL", rows)


def _row(home, away, hg, ag, *, stage="1", season="2025/2026", now=False):
    return {"home": home, "away": away, "hg": hg, "ag": ag,
            "stage": stage, "season": season, "now": now}


def test_cr1_영대영이_무로_들어간다() -> None:
    """CR1 — **스포르팅 아스날 원정 0-0**(2025/26 준준결승)이 무 1건이다."""
    got = _build([_row("Arsenal", "Sporting CP", 0, 0, stage="Quarter-Finals")])
    said = got["teams"]["Sporting CP"]["away"]
    assert (said["d"], said["n"]) == (1, 1), said
    assert (said["gf"], said["ga"]) == (0, 0), said


def test_cr2_준준결승은_중립이_아니다() -> None:
    """CR2 — `Quarter-Finals` 가 중립으로 잡히면 그 단계가 통째로 빠진다."""
    from app.core import competition as _cp
    for stage in ("Quarter-Finals", "Semi-Finals", "준결승", "8강"):
        ok, why = _cp.neutral_of("league:UCL", stage=stage)
        assert ok is False, (stage, why)
    for stage in ("Final", "final", "결승", "Final Four"):
        ok, why = _cp.neutral_of("league:UCL", stage=stage)
        assert ok is True, (stage, why)


def test_cr3_중립은_따로_센다() -> None:
    """CR3 — 결승(중립)은 `neutral` 칸에 가고 홈/원정에는 **안 들어간다**."""
    got = _build([_row("Sporting CP", "Arsenal", 1, 0, stage="Final")])
    said = got["teams"]["Sporting CP"]
    assert said["neutral"]["n"] == 1 and said["home"]["n"] == 0, said
    # 🔴 대회 전체 수치는 중립을 뺀다(CC3)
    assert got["n_graded"] == 0 and got["n"] == 1, got["n_graded"]


def test_cr4_지금_시즌은_따로_센다() -> None:
    """CR4 — 지금 시즌(`now`)은 직전 두 시즌 합계에 **섞이지 않는다**."""
    got = _build([_row("Sporting CP", "A", 2, 0, season="2026/2027", now=True),
                  _row("Sporting CP", "B", 1, 0, season="2025/2026")])
    said = got["teams"]["Sporting CP"]
    assert said["home"]["n"] == 1 and said["now"]["home"]["n"] == 1, said
    assert set(said["by_season"]) == {"2026/2027", "2025/2026"}


def test_cr5_도구가_지금_시즌_더해_받는다() -> None:
    """CR5 — `--seasons 2` 는 지금 시즌 **+ 직전 2시즌**(세 장)을 받는다."""
    said = (ROOT / "tools/fit_comp_record.py").read_text(encoding="utf-8")
    assert "want = said[:1 + max(1, int(seasons))]" in said


def test_cr6_검증_전_꼬리표가_붙는다() -> None:
    """CR6 — 외부 대조 전이면 카드 줄에 🔴 **검증 전**이 붙는다."""
    from app.core import comprecord as cr
    ok, said = cr.verified_of("league:UCL")
    assert ok is False and "검증 전" in said, said
    line = cr.said_of("league:UCL", home="Racing Club de Lens",
                      away="Sporting Clube de Portugal")
    assert "검증 전 — 판단에 쓰지 말 것" in line
    # 🔴 시즌별로 나눠 적는다(②)
    assert "직전 두 시즌" in line and "지금 시즌" in line
    assert "2025/2026" in line and "2024/2025" in line


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **④ 판정 보류** — 이 칸은 **표시 전용**이다(경로 후보로 안 쓴다)
# ══════════════════════════════════════════════════════════════════

def test_cr7_확률_판정_경로가_이_칸을_안_읽는다() -> None:
    """CR7 — ④ *"대회 이력을 경로 후보로 쓰는 판정은 1~3 끝난 뒤"*.

    🔴 그래서 확률·판정 쪽 어느 파일도 `comprecord`·`comphistory` 를 **안 읽는다**.
    ⚠️ 읽는 자리는 `s2_facts`(사실 모으기)와 `render`(카드 글자)뿐이다.
    """
    want = ("app/core/probmodel.py", "app/core/probfloor.py",
            "app/core/sim.py", "app/core/stages/s7_judge.py",
            "app/core/ensemble.py", "app/core/survive.py",
            "tools/judge_models.py", "tools/fit_ensemble.py")
    for rel in want:
        path = ROOT / rel
        if not path.exists():
            continue
        said = path.read_text(encoding="utf-8")
        for bad in ("comprecord", "comphistory", "comp_record", "comp_history"):
            assert bad not in said, (rel, bad)


def test_cr8_대조_도구가_검증을_스스로_올리지_않는다() -> None:
    """CR8 — 위키백과 대조는 **공식이 아니다** — `verified` 를 못 올린다."""
    said = (ROOT / "tools/comp_record_verify.py").read_text(encoding="utf-8")
    assert "verified" in said          # 🔴 그 낱말을 **설명**은 한다
    # 🔴 **올리는 코드가 없어야** 한다(D46 — 글자 그대로의 대입을 센다)
    for bad in ("verified\"] = True", "verified'] = True",
                "verified=True", "\"verified\": True"):
        assert bad not in said, bad
