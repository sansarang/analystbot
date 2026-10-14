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


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **공격 계층은 "표시만"이다**(후속 지시 2026-10-14g §1 마지막 줄)
# ══════════════════════════════════════════════════════════════════

def test_at13_공격_계층_상태가_등록표에_적혀_있다() -> None:
    """🔴 실효 측정이 문턱을 못 이겼다 → `layer.state == 표시만` · 근거가 함께."""
    from app.core import attack
    box = dict(attack.table().get("layer") or {})
    assert box.get("state") == "표시만", box
    assert "92.8" in str(box.get("why")) and "93.2" in str(box.get("why"))
    assert (ROOT / str(box.get("판정표"))).exists()


def test_at14_칠_표는_공격으로_걸러내지_않는다() -> None:
    """🔴 §1·§5 — 단폴·다폴은 **문턱만**으로 고른다(판정은 표에 적기만)."""
    import inspect

    from app.core import picks
    said = inspect.getsource(picks)
    assert "CUT_SINGLE = 0.88" in said and "CUT_LEG = 0.90" in said
    # 🔴 `verdict` 로 **거르는 코드가 없다**(적기만 한다)
    for bad in ("verdict ==", "verdict !=", 'verdict in ('):
        assert bad not in said, bad
    rows = [{"match": "A vs B", "league": "L", "kickoff": "1",
             "lines": {"핸디 home+1.5": 0.95}, "verdict": "무너짐",
             "board_lines": ["핸디 home+1.5"]}]
    got = picks.of(rows)
    assert len(got.singles) == 1, "🔴 무너짐도 문턱을 넘으면 단폴에 든다"


def test_at15_다폴_규칙이_지켜진다() -> None:
    """🔴 §4 — 같은 경기 금지 · 전부 같은 방향 금지 · 같은 리그·킥오프 최대 2."""
    from app.core import picks
    same = [{"match": f"A{i} vs B{i}", "league": "L", "kickoff": "1",
             "lines": {"핸디 home+1.5": 0.95},
             "board_lines": ["핸디 home+1.5"]} for i in range(4)]
    got = picks.of(same)
    assert not got.parlays, "🔴 전부 홈 쪽인데 다폴이 나왔다"
    mixed = [{"match": "A vs B", "league": "L1", "kickoff": "1",
              "lines": {"핸디 home+1.5": 0.95},
              "board_lines": ["핸디 home+1.5"]},
             {"match": "C vs D", "league": "L2", "kickoff": "2",
              "lines": {"핸디 away+1.5": 0.94},
              "board_lines": ["핸디 away+1.5"]}]
    got2 = picks.of(mixed)
    assert got2.parlays and len(got2.parlays[0]) == 2
    assert len({x.match for x in got2.parlays[0]}) == 2


def test_at16_칠_표가_슬레이트에_배선됐다() -> None:
    """🔴 §5 — 슬레이트 끝이 칠 표를 찍고 **적어 둔다** · `score_cards` 가 센다."""
    said = (ROOT / "tools/slate_queue.py").read_text(encoding="utf-8")
    assert "picks as _pk" in said and "_pk.said_of(out)" in said
    assert "save_picks(" in said and "var/picks" in said
    got = (ROOT / "tools/score_cards.py").read_text(encoding="utf-8")
    assert "score_picks(net)" in got and "line_hit(" in got


def test_at17_줄_채점이_스코어와_맞는다() -> None:
    """🔴 §5 — 줄 적중은 **스코어**로 센다(0-1 경기로 전부 확인)."""
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    from score_cards import line_hit
    for line, want in (("핸디 home+1.5", True), ("핸디 home-0.5", False),
                       ("핸디 away+1.5", True), ("핸디 away-0.5", True),
                       ("오버 2.5", False), ("언더 2.5", True),
                       ("홈 승", False), ("원정 승", True), ("무", False)):
        assert line_hit(line, 0, 1) is want, line


def test_at18_봇_명령이_같은_식으로_고른다() -> None:
    """🔴 §5 — `/칠표` 는 `core/picks.of` 를 부른다(문턱을 고치면 따라온다)."""
    import inspect

    from app.bot import main as bm
    said = inspect.getsource(bm.cmd_picks)
    assert "_pk.of(" in said and "_pk.said_of(" in said
    assert "var/picks" in said


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **보드에 있는 줄만**(후속 지시 2026-10-14h §1 · AT19~AT21)
# ══════════════════════════════════════════════════════════════════

def test_at19_보드_없는_경기는_칠_표에서_빠진다() -> None:
    from app.core import picks
    rows = [{"match": "A vs B", "league": "L", "kickoff": "1",
             "lines": {"핸디 home+1.5": 0.97}},            # 🔴 보드 없다
            {"match": "C vs D", "league": "L", "kickoff": "1",
             "lines": {"핸디 home+1.5": 0.95, "오버 1.5": 0.99},
             "board_lines": ["핸디 home+1.5"]}]            # 🔴 보드에 한 줄만
    got = picks.of(rows)
    assert [x.match for x in got.singles] == ["C vs D"], got.singles
    # 🔴 보드에 **없는 줄**(오버 1.5 · 0.99)은 더 높아도 안 고른다
    assert got.singles[0].line == "핸디 home+1.5"
    assert "보드 없어 뺀 경기 1개" in got.why


def test_at20_보드_줄_이름이_파서와_맞는다() -> None:
    """🔴 보드 → 줄 이름 — 승무패·핸디(**왼쪽=홈 기준**)·오버언더."""
    from app.core import board, picks
    got, _extra, _bad = board.parse(
        "승무패 2.15 3.25 3.40\n핸디 1.5 1.80 2.05\n언더오버 2.5 1.90 1.95")
    said, why = picks.board_lines(got)
    assert {"홈 승", "무", "원정 승", "핸디 home+1.5", "핸디 away-1.5",
            "오버 2.5", "언더 2.5"} <= said, (said, why)
    # 🔴 **정수 기준선은 세 쪽**(승·무·패) — 국내 보드 규칙
    got2, _e2, _b2 = board.parse("핸디 1 1.80 1.95")
    said2, _w2 = picks.board_lines(got2)
    assert {"핸디 home+1 승", "핸디 home+1 무"} <= said2, said2
    # 🔴 보드가 없으면 **빈 집합과 사유**
    none, why2 = picks.board_lines(None)
    assert not none and "⬜" in why2


def test_at21_카드가_보드_줄을_든다() -> None:
    """🔴 배선 — 파이프라인이 `picks.board_lines` 를 세어 카드 칸에 싣는다."""
    from app.core.schema import Card
    assert "board_lines" in Card.model_fields
    said = (ROOT / "app/core/pipeline.py").read_text(encoding="utf-8")
    assert "_pk.board_lines(got_board)" in said
    assert 'layers["board_lines"]' in said
    got = (ROOT / "tools/slate_queue.py").read_text(encoding="utf-8")
    assert 'getattr(card, "board_lines"' in got and "board_text_of(" in got
