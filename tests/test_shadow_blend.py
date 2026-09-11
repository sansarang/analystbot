"""BLD-1 — PL-1 섀도 앙상블의 계약.

🔴 이것은 **섀도다.** 카드·게이트·판정이 이 값을 읽으면 그 순간 "우리 판정"이
   아니라 앙상블이 된다. 그건 동결 대상(확률 게이트·클립)의 변경이고
   사용자 결정 사항이다. 지금은 **기록만** 한다.

근거(운영 원장 재측정 2026-09-08, 경기 단위 `is_final`):
    우리 LLM 판정  AUC 0.470~0.519 · 브라이어 0.2530
    단순 Elo       AUC 0.558
    시장           AUC 0.654
"""

import pytest

from app.engine import shadow_blend as sb


def _jg(p_claude=0.54, home=1520.0, away=1480.0):
    g = {"game_id": 1, "p_claude": p_claude}
    if home is not None and away is not None:
        g["elo"] = {"home": {"레이팅": home}, "away": {"레이팅": away}}
    return g


# ═══════════════ ① 값이 맞는가 — 식은 원본에서 온다

def test_p_elo_는_원본_식과_홈이점을_쓴다():
    """🔴 사본 금지 — `elo_core.expected_home` 과 `team_elo.HOME_ADV` 가 원본."""
    from app.models.elo_core import expected_home
    from app.models.team_elo import HOME_ADV

    got = sb.p_elo(_jg(home=1520.0, away=1480.0))
    want = round(expected_home(1520.0 - 1480.0 + HOME_ADV), 4)
    assert got == want


def test_가중치_세_값이_전부_남는다():
    out = sb.compute(_jg())
    assert set(out) == {"p_claude", "p_elo", "w0.3", "w0.5", "w0.7"}, out
    for w in sb.WEIGHTS:
        assert f"w{w}" in out


def test_혼합이_가중_평균이다():
    out = sb.compute(_jg(p_claude=0.40))
    pe = out["p_elo"]
    for w in sb.WEIGHTS:
        assert out[f"w{w}"] == pytest.approx(w * pe + (1 - w) * 0.40, abs=1e-4)


def test_가중이_클수록_Elo_쪽에_가깝다():
    out = sb.compute(_jg(p_claude=0.30, home=1600.0, away=1400.0))
    assert out["w0.3"] < out["w0.5"] < out["w0.7"] <= out["p_elo"]


# ═══════════════ ② 모르는 것을 아는 척하지 않는다

def test_Elo_가_없으면_사유를_남긴다():
    """🔴 0.5 로 채우면 '박빙'과 '모른다'가 같아진다."""
    out = sb.compute(_jg(home=None, away=None))
    assert out["p_elo"] is None
    assert out["why"] == "elo 없음"
    assert not any(k.startswith("w0.") for k in out), out


def test_한쪽_레이팅만_있으면_기록하지_않는다():
    jg = {"game_id": 1, "p_claude": 0.5, "elo": {"home": {"레이팅": 1520}}}
    assert sb.p_elo(jg) is None


def test_판정이_없으면_아무것도_남기지_않는다():
    assert sb.compute({"game_id": 1}) is None
    assert sb.compute({"game_id": 1, "p_claude": None}) is None


def test_레이팅이_숫자가_아니면_None(caplog):
    jg = {"game_id": 1, "p_claude": 0.5,
          "elo": {"home": {"레이팅": "없음"}, "away": {"레이팅": 1480}}}
    assert sb.p_elo(jg) is None


# ═══════════════ ③ 섀도가 본체를 죽이지 않는다
#   ⚠️ 배선 계약(원장 행에 실제로 실리는가)은 `test_shadow_blend_wiring.py` 에
#      따로 있다 — 이 파일은 `shadow_blend` 를 최상단에서 임포트하므로
#      수정 전 코드에서 통째로 죽어 배선을 증명하지 못한다.

def test_계산이_터져도_원장_기록을_막지_않는다(monkeypatch):
    """원장은 판정의 유일한 영구 기록이다 — 섀도 때문에 행이 빠지면 안 된다."""
    def _boom(jg):
        raise RuntimeError("터졌다")

    monkeypatch.setattr(sb, "compute", _boom)
    assert sb.safe_compute(_jg()) is None


def test_INSERT_가_컬럼을_적는다():
    src = open("app/engine/pick_ledger.py", encoding="utf-8").read()
    assert "shadow_blend" in src.split("INSERT INTO pick_ledger")[1][:600]


def test_스키마에_컬럼이_있다():
    src = open("db/schema.sql", encoding="utf-8").read()
    assert "ADD COLUMN IF NOT EXISTS shadow_blend JSONB" in src


# ═══════════════ ④ 되돌아가지 않는다 — import 경계

@pytest.mark.parametrize("path", [
    "app/engine/matchup.py",        # 판정
    "app/engine/value_gate.py",     # 게이트
    "app/engine/card.py",           # 카드
    "app/engine/form_card.py",      # 추천 라벨
    "app/engine/pregame_push.py",   # 발송
])
def test_판정_게이트_카드는_섀도를_읽지_않는다(path):
    """🔴 이 경계가 무너지면 '우리 판정'이 사실은 앙상블이 된다.

    그건 동결 대상(확률 게이트·클립)의 변경이고 사용자 결정 사항이다.
    """
    import pathlib

    p = pathlib.Path(path)
    if not p.exists():
        pytest.skip(f"{path} 없음")
    assert "shadow_blend" not in p.read_text(encoding="utf-8"), path
