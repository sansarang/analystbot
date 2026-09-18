"""U3 — 티어 미기입은 중앙값이 아니라 **없음**이다.

🔴 실측 2026-09-15:
     team_elo(None) → elo=1560.0 src='tier:미기입'   ← 리그 중앙(3)으로 메웠다
     티어 파일 11개 · 빠진 것 ['eredivisie','jleague2','kleague2','ligue1']
     load_tiers('acl') → 0팀                          ← 키가 'teams:' 였다(ACL-1 실수)
     form_pp('WWDWD') = 4.0 (기대 2.0)
   채운 팀과 안 채운 팀이 같은 근거를 가진 것처럼 보였다 — 리즈 사례가 그 결과다.
"""
from __future__ import annotations

import inspect
import pathlib

import pytest

from app.engine import prior as P

LEAGUES = {"epl", "la_liga", "serie_a", "bundesliga", "ligue1", "eredivisie",
           "j1", "jleague2", "kleague1", "kleague2", "denmark", "acl",
           "mlb", "kbo", "npb"}


def test_티어_미기입이면_사전값이_없다():
    elo, src = P.team_elo(None, w=3, d=1, lose=0)
    assert elo is None
    assert src == "none", src


def test_미기입이어도_예외가_안_난다():
    """🔴 반대 위험 — None 을 그대로 soccer_prior 에 넘기면 TypeError 다."""
    elo, _ = P.team_elo(None, w=0, d=0, lose=0)
    assert elo is None
    with pytest.raises(TypeError):
        P.soccer_prior(elo, 1600.0)      # 그래서 호출부가 먼저 막아야 한다


def test_호출부가_먼저_막는다():
    """🔴 [GAT-1 2026-09-18] 계산이 `record_prior` → `gate_of` 로 옮겨갔다.

    규칙은 그대로다 — **티어가 비면 `soccer_prior` 를 부르기 전에 막는다.**
    보는 자리만 옮긴다(계산이 있는 곳을 본다).
    """
    from app.engine import pick_ledger as PL

    src = inspect.getsource(PL.gate_of)
    assert "if th is None or ta is None" in src, "None 을 그대로 넘긴다"
    # 주석을 뺀 실행 줄만 본다 — 주석에는 soccer_prior 가 설명으로 나온다.
    code = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
    i = code.index("if th is None or ta is None")
    assert "P.soccer_prior" not in code[:i], "막기 전에 이미 썼다"
    # 🔴 조용히 빠지지 않는다 — 쓰는 쪽(`record_prior`)이 `none` 으로 남긴다.
    wsrc = inspect.getsource(PL.record_prior)
    assert '"none"' in wsrc and "_PRIOR_SAVE" in wsrc, "조용히 빠진다"


def test_중앙값_대체_코드가_없다():
    """🔴 사본 금지 — TIER_DEFAULT 로 메우는 줄이 team_elo 에 남으면 안 된다."""
    src = inspect.getsource(P.team_elo)
    assert "tier, src = TIER_DEFAULT" not in src
    assert "tier:미기입" not in src


def test_티어_파일_15개가_로드된다():
    have = {p.stem for p in pathlib.Path("config/tiers").glob("*.yaml")}
    assert LEAGUES <= have, sorted(LEAGUES - have)


@pytest.mark.parametrize("league", sorted(LEAGUES))
def test_모든_티어_파일이_tiers_키다(league):
    """🔴 acl.yaml 이 'teams:' 라 처음부터 0팀이었다(ACL-1 실수)."""
    import yaml

    doc = yaml.safe_load(pathlib.Path(f"config/tiers/{league}.yaml")
                         .read_text(encoding="utf-8")) or {}
    assert "tiers" in doc, f"{league}.yaml 에 tiers 키가 없다: {sorted(doc)}"


def test_acl_티어가_실제로_로드된다():
    """🔴 ACL-1: `teams:` 로 잘못 써서 처음부터 0팀이었다. 그게 이 계약의 뜻이다.

    ⚠️ [PA-7 2026-09-16] 종전에는 `len(t) == 8`(골격 시절 팀 수)을 박아
       뒀는데, 값을 채우면 팀이 늘어 빨개진다. **개수가 아니라 '로드되는가'와
       '오늘 쓰는 팀이 풀리는가'를 잰다** — 이쪽이 더 강한 계약이다.
    """
    t = P.load_tiers("acl")
    assert t, "ACL 티어가 0팀 — tiers 키를 확인하라(ACL-1)"
    assert "Daejeon Citizen" in t or "Daejeon Hana Citizen" in t
    # 🔴 이름 불일치는 조용히 미기입이 된다(리즈 사례). DB 표기로 풀려야 한다.
    for name in ("Jeonbuk Hyundai Motors FC", "Kashiwa Reysol",
                 "Vissel Kobe", "Port FC"):
        assert name in t, f"{name} 가 티어 표에 없다 — DB 표기와 어긋났다"


def test_acl_티어값은_1에서_5_사이다():
    """값을 채운 팀은 TIER_ELO 가 아는 범위여야 한다. 모르면 null 이다."""
    t = P.load_tiers("acl")
    filled = {k: v for k, v in t.items() if v is not None}
    assert filled, "값이 하나도 안 채워졌다"
    assert all(isinstance(v, int) and 1 <= v <= 5 for v in filled.values()), \
        {k: v for k, v in filled.items() if not (isinstance(v, int) and 1 <= v <= 5)}


@pytest.mark.parametrize("last5,want", [
    ("WWWWW", 4.0), ("LLLLL", -4.0),          # 전승·전패
    ("WWDWD", 2.0), ("DDDDD", 2.0),           # 무패(패 0)
    ("LDLDL", -2.0),                          # 무승(승 0)
    ("WLWDL", 0.0), ("WWWWL", 0.0),           # 섞였다
])
def test_form5가_네_등급이다(last5, want):
    assert P.form_pp(last5) == want


def test_다섯경기가_아니면_0():
    """⚠️ 얇은 표본에 보정을 붙이지 않는다(기존 규칙 유지)."""
    for s in ("", "WWW", "WWWWWW", "WWWWX", None):
        assert P.form_pp(s) == 0.0


def test_DDDDD는_무패이자_무승이다():
    """경계 — 전부 무승부면 '패 0' 이 먼저 걸려 +2 다. 규칙이 결정적이어야 한다."""
    assert P.form_pp("DDDDD") == 2.0


def test_리즈가_티어4로_잡힌다():
    """🔴 키가 우리 games 표기여야 한다 — "Leeds" 로 적으면 미기입이 된다."""
    t = P.load_tiers("epl")
    assert "Leeds United FC" in t, [k for k in t if "Leeds" in k]
    assert t["Leeds United FC"] == 4, t.get("Leeds United FC")
