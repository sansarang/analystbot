"""🔴🔴 **공격형 검증 v2**(지시 2026-10-14f · AT1~AT10).

> [확정] 백필에서 효과가 측정된 변수 — **깨짐 판정에 쓴다**
> [관찰] 데이터는 있으나 효과 미측정 — 카드에 **표시만**, 판정 안 함
> [가설] 데이터 미확보 — **수집 목록**에만
> [관찰]→[확정] 승격은 백필 측정으로만. 효과 없으면 강등·제거.

🔴 계약이 지키는 것 —
   ① 등급표가 **하나**이고(사본 금지) 등급과 `judge` 가 **어긋나지 않는다**
   ② [관찰]·[가설]은 **깨짐·반격에 못 쓴다**(표시만)
   ③ 공격 결과는 **같은 시뮬 식**으로 재계산된다(새 확률 경로 금지)
   ④ 등급 승격은 **측정 도구만** 한다(손으로 올리면 빨개진다)
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _box(**kw) -> dict:
    got = {"pick": 0, "gaps": {"axis0": 0.5, "axis1": 0.2, "axis2": 0.0,
                               "axis3": 0.0},
           "ours": [0.5, 0.25, 0.25], "mul": 1.12, "league_mul": 1.12,
           "away_mul": 0.88, "base": [1.2771, 1.2771], "xi_state": "확정",
           "team_mul": 0.0, "elo": [0.5, 0.25, 0.25], "market": None,
           "gaps_missing": [], "band_dev": None, "neutral": False,
           "t12": "", "form_games": 9, "axis_why": {}, "axis0_sd": 0.935,
           "discipline": None, "absence_src": "A", "key_missing": []}
    got.update(kw)
    return got


def test_at1_등급표가_하나이고_어긋나지_않는다() -> None:
    from app.core import attack
    box = dict(attack.table().get("vars") or {})
    assert len(box) >= 40, len(box)
    assert set(attack.table().get("grades") or []) == {"확정", "관찰", "가설"}
    for key, one in box.items():
        if (one or {}).get("judge") is True:
            assert one.get("grade") == "확정", (key, one.get("grade"))
        else:
            assert one.get("grade") in ("관찰", "가설"), (key, one)


def test_at2_판정은_확정_변수만() -> None:
    """🔴 ② [관찰]·[가설] 변수는 깨짐·반격에 **안 쓴다**."""
    from app.core import attack
    want = set(attack.judges())
    got = attack.of(_box())
    for shot in got.shots:
        assert shot.key in want, shot.key
    # 🔴 1차 측정 대상(B2·C3·D1·D4·F1)은 아직 [관찰] → 공격에 **없다**
    for key in ("B2", "C3", "D1", "D4", "F1"):
        assert attack.grade(key) in ("관찰", "가설"), key
        assert key not in want


def test_at3_깨지면_그_축_기여가_0_이_된다() -> None:
    from app.core import attack
    got = attack.of(_box(form_games=3))        # 🔴 B1 표본 부족 → 깨짐
    assert any(s.key == "B1" and s.verdict == "깨짐" for s in got.shots)
    assert got.gaps["axis1"] == 0.0
    assert abs(got.sigma - (got.sigma0 - 0.3 * 0.2)) < 1e-9


def test_at4_시장_괴리는_못_센_칸이_있을_때만_깨뜨린다() -> None:
    from app.core import attack
    far = {"market": [0.30, 0.25, 0.45], "ours": [0.50, 0.25, 0.25]}
    only = attack.of(_box(**far))
    assert any(s.key == "J1" and s.verdict == "표시만" for s in only.shots)
    with_gap = attack.of(_box(**far, gaps_missing=["Elo 기준"]))
    assert any(s.key == "J1" and s.verdict == "깨짐" for s in with_gap.shots)


def test_at5_중립이면_홈_이점이_0_이다() -> None:
    from app.core import attack
    got = attack.of(_box(neutral=True))
    assert got.mul == 1.0
    assert any(s.key == "C4" and s.verdict == "깨짐" for s in got.shots)


def test_at6_예상_XI_면_라인업_판정을_보류한다() -> None:
    from app.core import attack
    got = attack.of(_box(xi_state="예상", key_missing=["누구"]))
    assert any(s.key == "E4" and s.verdict == "보류" for s in got.shots)
    assert not any(s.key == "E1" for s in got.shots)


def test_at7_팀_홈_배율_상위_분위는_깨진다() -> None:
    from app.core import attack
    got = attack.of(_box(team_mul=1.40))
    assert any(s.key == "C2" and s.verdict == "깨짐" for s in got.shots)
    assert got.mul == 1.12          # 🔴 리그값으로 되돌린다
    safe = attack.of(_box(team_mul=1.10))
    assert any(s.key == "C2" and s.verdict == "버팀" for s in safe.shots)


def test_at8_K1_은_측정으로_강등됐다() -> None:
    """🔴🔴 §0 *"효과 없으면 **강등·제거**"* — K1 은 측정으로 [관찰]로 내려갔다.

    🔴 까닭(측정 2026-10-14 · `var/accept/fit_attack.log`) — 무 구간 편차의
       **부호가 표본 사이에서 뒤집혔다**: 2,582경기 판에서 20~25% 구간이
       **+2.7%p 과소**였는데 1,470경기 재료 판에서는 **−4.1%p 과대**였다.
    🔴 그래서 K1 은 **공격에서 빠진다**(표시만) — 그 사실이 등록표에 적혀 있다.
    """
    from app.core import attack
    assert attack.grade("K1") == "관찰"
    assert "K1" not in attack.judges()
    got = attack.of(_box(band_dev=-0.027))
    assert not any(s.key == "K1" for s in got.shots)
    one = dict((attack.table().get("vars") or {}).get("K1") or {})
    assert (one.get("fit") or {}).get("demote") is True, one
    # 🔴 그래도 **그 식은 코드에 남아 있다**(다시 측정해 올릴 수 있다)
    import inspect
    assert "band_dev" in inspect.getsource(attack.of)


def test_at9_재계산은_운영과_같은_식이다() -> None:
    """🔴 ③ `λ = 바닥 × 배율 × e^{β·Σ}` — 새 확률 경로를 만들지 않는다."""
    import inspect

    from app.core import attack
    said = inspect.getsource(attack.lam_of)
    assert "math.exp(m)" in said and "out.mul" in said
    assert "BETA * out.sigma" in said
    # 🔴 공격 모듈이 **확률을 스스로 만들지 않는다**(시뮬은 호출부가 부른다)
    tree = ast.parse((ROOT / "app/core/attack.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)):
            node.body = body[1:] or [ast.Pass()]
    code = ast.unparse(tree)
    for bad in ("sim.run", "markets_of", "score_grid"):
        assert bad not in code, bad


def test_at10_등급_승격은_측정_도구만_한다() -> None:
    """🔴 ④ 등급을 올리는 코드는 `tools/fit_attack.py` **한 곳**이다."""
    said = (ROOT / "tools/fit_attack.py").read_text(encoding="utf-8")
    assert '["grade"] = "확정"' in said and "promote" in said
    # 🔴 `app/` 에서 등급을 쓰는 코드가 **없다**(읽기만 한다)
    for path in (ROOT / "app").rglob("*.py"):
        body = path.read_text(encoding="utf-8")
        assert '"grade"] = ' not in body, path


def test_at11_카드가_공격표를_찍는다() -> None:
    """🔴 §1·§3 — 카드에 **공격표**가 있고 그 줄은 `core/attack` 이 센 것이다."""
    from app.core import render
    said = (ROOT / "app/core/render.py").read_text(encoding="utf-8")
    assert "_attack_line(card)" in said and "🗡 **공격표**" in said
    # 🔴 그 줄이 **수를 새로 만들지 않는다**(살아남은 λ 로 시뮬만 돈다)
    import inspect
    body = inspect.getsource(render._attack_line)
    assert "card, \"attack\"" in body or 'card, "attack"' in body
    assert "sim.run" in body and "markets_of" not in body


def test_at12_파이프라인이_공격을_돈다() -> None:
    """🔴 배선 — `pipeline` 이 `_attack_of` 를 부르고 카드가 그 칸을 든다."""
    said = (ROOT / "app/core/pipeline.py").read_text(encoding="utf-8")
    assert 'layers["attack"] = _attack_of(' in said
    assert "attack=dict(box.get(\"attack\") or {})" in said
    from app.core.schema import Card
    assert "attack" in Card.model_fields
