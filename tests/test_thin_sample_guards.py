"""[표본 하한 3칸] 얇은 숫자가 결정 변수의 크기를 정하지 못하게 한다.

실측 2026-09-07 (WSH@LAD 리허설, 운영 코드):
  판정이 결정 변수의 크기를 `자료10 이닝분포 p25(2.0이닝)` 에서 가져왔는데
  그 분위수의 표본은 **등판 2건**이었다 — 로그 원문
  `[var-ref] mlb Justin Wrobleski 이닝 분포 n=2 선발1 p50=6.0 최장=6.0`.
  판정은 "표본 2뿐"이라고 단서까지 달았다. 추론은 옳았고 숫자가 얇았다.

세 칸:
  ① 자료10 — 표본이 얇으면 **분위수를 빼고** 원시 배열만 남긴다
  ② 자료10 — 얇은 선발에 **리그 최근 창 기준선**을 붙인다
  ③ 자료1  — 최근 3경기 득점에 **상대의 최근 실점률** 보정을 숫자로 붙인다
"""

import pytest

from app.config import get_settings
from app.engine.variable_ref import quantiles


# ═══════════════ ① 자료10 분위수 표본 하한

def test_비보간_분위수는_표본이_얇으면_퇴화한다():
    """🔴 하한이 필요한 **이유**를 못박는다 — 이 성질이 깨지면 값을 재검토하라.

    `quantiles` 는 보간하지 않고 실제 값 하나를 고른다. 그래서 n<5 에서는
    서로 다른 분위수가 같은 순서통계량을 가리킨다.
    """
    q2 = quantiles([6.0, 2.0])              # 실측 Wrobleski
    assert q2["p50"] == q2["p75"] == 6.0    # 두 분위수가 최댓값으로 퇴화
    assert q2["p25"] == 2.0                 # "분포"가 아니라 두 값 중 작은 쪽
    q4 = quantiles([2.0, 4.0, 6.0, 7.0])
    assert q4["p50"] == q4["p75"]           # n=4 도 여전히 퇴화
    q5 = quantiles([2.0, 4.0, 5.0, 6.0, 7.0])
    assert len({q5["p25"], q5["p50"], q5["p75"]}) == 3   # n=5 에서 처음 셋이 갈린다


def test_하한값은_퇴화가_풀리는_지점이다():
    assert get_settings().var_ref_min_quantile_n == 5


class _Pool:
    def __init__(self, rows=(), exc=None):
        self.rows, self.exc, self.calls = list(rows), exc, []

    async def fetch(self, sql, *a):
        self.calls.append((sql, a))
        if self.exc:
            raise self.exc
        return self.rows

    async def fetchrow(self, sql, *a):
        self.calls.append((sql, a))
        if self.exc:
            raise self.exc
        return self.rows[0] if self.rows else None


def _app(ip, r=1.0, starter=True):
    return {"innings": ip, "r": r, "is_starter": starter,
            "starts_at": "2026-09-01"}


@pytest.mark.asyncio
async def test_표본이_얇으면_분위수를_빼고_배열은_남긴다():
    """지우는 것은 **추정**뿐이다. 배열은 사실이므로 남는다."""
    from app.engine.variable_ref import innings_profile

    out = await innings_profile(_Pool([_app(6.0), _app(2.0, starter=False)]),
                                "mlb", "Justin Wrobleski", "2026-09-07")
    assert out["n"] == 2
    assert out["이닝"] == [6.0, 2.0]          # 사실은 그대로
    assert out["최장"] == 6.0
    assert "p25" not in out and "p50" not in out and "p75" not in out
    assert "주의" in out and "이닝" in out["주의"]


@pytest.mark.asyncio
async def test_표본이_충분하면_분위수가_그대로_나간다():
    """🔴 반대 위험 — 하한이 정상 데이터를 버리면 안 된다."""
    from app.engine.variable_ref import innings_profile

    rows = [_app(x) for x in (7.0, 6.0, 6.0, 5.0, 2.0)]
    out = await innings_profile(_Pool(rows), "mlb", "Andrew Alvarez",
                                "2026-09-07")
    assert out["n"] == 5
    assert {"p25", "p50", "p75"} <= set(out)
    assert "주의" not in out


@pytest.mark.asyncio
async def test_등판이_아예_없으면_종전대로_빈_dict():
    from app.engine.variable_ref import innings_profile

    assert await innings_profile(_Pool([]), "mlb", "누구", "2026-09-07") == {}


# ═══════════════ ② 리그 선발 기준선

@pytest.mark.asyncio
async def test_리그_기준선은_표본이_얇으면_붙지_않는다():
    """얇은 선발을 더 얇은 기준선으로 재면 없느니만 못하다."""
    from app.engine.variable_ref import league_starter_reference

    s = get_settings()
    thin = {"n": s.var_ref_league_min_n - 1, "ip": 5.0, "r": 2.5}
    assert await league_starter_reference(_Pool([thin]), None, "mlb",
                                          "2026-09-07") == {}


@pytest.mark.asyncio
async def test_리그_기준선은_최근_창만_본다():
    """⚠️ 시즌 누적이면 대원칙(집계표 금지) 위반이다."""
    from app.engine.variable_ref import league_starter_reference

    s = get_settings()
    pool = _Pool([{"n": s.var_ref_league_min_n + 10, "ip": 5.31, "r": 2.44}])
    out = await league_starter_reference(pool, None, "mlb", "2026-09-07")
    assert out["평균이닝"] == 5.31 and out["평균실점"] == 2.44
    assert out["표본"] == s.var_ref_league_min_n + 10
    assert str(s.var_ref_league_days) in out["창"]
    sql, args = pool.calls[0]
    assert "make_interval(days =>" in sql, "창 없이 전 시즌을 세면 집계표다"
    assert "starts_at < $2" in sql, "컷오프가 없으면 미래 경기가 섞인다"
    assert args[2] == s.var_ref_league_days


@pytest.mark.asyncio
async def test_리그_기준선_조회가_실패해도_판정을_막지_않는다():
    from app.engine.variable_ref import league_starter_reference

    assert await league_starter_reference(_Pool(exc=RuntimeError("boom")),
                                          None, "mlb", "2026-09-07") == {}


# ═══════════════ ③ 자료1 상대 보정

def _jg(side_games):
    return {"sport": "mlb", "game_id": 1,
            "research": {"home_usage": {"games": side_games,
                                        "runs_per_game_l3": 4.67}}}


class _AdjPool:
    """상대별 최근 실점을 이름으로 돌려주는 목."""

    def __init__(self, table):
        self.table = table

    async def fetchrow(self, sql, sport, team, before, limit):
        v = self.table.get(team)
        return None if v is None else {"n": v[0], "ra": v[1]}


@pytest.mark.asyncio
async def test_상대가_평소_내주는_만큼_내면_배율은_1이다():
    from app.engine.opponent_adjust import side_block

    games = [{"date": "2026-09-01", "opponent": "A", "runs": 4},
             {"date": "2026-09-02", "opponent": "B", "runs": 4},
             {"date": "2026-09-03", "opponent": "C", "runs": 4}]
    pool = _AdjPool({"A": (5, 4.0), "B": (5, 4.0), "C": (5, 4.0)})
    out = await side_block(pool, "mlb", _jg(games), "home")
    assert out["배율"] == 1.0
    assert out["대상경기"] == 3 and out["총경기"] == 3
    assert "주의" not in out


@pytest.mark.asyncio
async def test_잘_내주는_상대에게_낸_득점은_배율이_깎인다():
    """🔴 약팀 상대 5득점과 강팀 상대 5득점은 같은 5점이 아니다."""
    from app.engine.opponent_adjust import side_block

    games = [{"date": "2026-09-0%d" % i, "opponent": "약", "runs": 5}
             for i in (1, 2, 3)]
    후한상대 = await side_block(_AdjPool({"약": (5, 6.0)}), "mlb",
                                _jg(games), "home")
    구두쇠상대 = await side_block(_AdjPool({"약": (5, 2.5)}), "mlb",
                                  _jg(games), "home")
    assert 후한상대["배율"] < 1.0 < 구두쇠상대["배율"]


@pytest.mark.asyncio
async def test_표본이_얇은_상대는_보정에서_빠지고_그_사실을_밝힌다():
    """조용히 빼면 3경기 보정인 줄 안다 — 몇 건을 썼는지 적는다."""
    from app.engine.opponent_adjust import side_block

    s = get_settings()
    games = [{"date": "2026-09-01", "opponent": "A", "runs": 4},
             {"date": "2026-09-02", "opponent": "얇", "runs": 9},
             {"date": "2026-09-03", "opponent": "C", "runs": 4}]
    pool = _AdjPool({"A": (5, 4.0), "C": (5, 4.0),
                     "얇": (s.m1_opp_min_games - 1, 1.0)})
    out = await side_block(pool, "mlb", _jg(games), "home")
    assert out["대상경기"] == 2 and out["총경기"] == 3
    assert "주의" in out
    assert out["배율"] == 1.0, "빠진 경기의 9득점이 새어 들어왔다"


@pytest.mark.asyncio
async def test_전부_얇으면_보정을_붙이지_않는다():
    from app.engine.opponent_adjust import side_block

    games = [{"date": "2026-09-01", "opponent": "A", "runs": 4}]
    assert await side_block(_AdjPool({"A": (1, 4.0)}), "mlb",
                            _jg(games), "home") == {}


@pytest.mark.asyncio
async def test_자료1이_없으면_조용히_넘어간다():
    from app.engine.opponent_adjust import side_block

    assert await side_block(_AdjPool({}), "mlb", {"research": {}}, "home") == {}


@pytest.mark.asyncio
async def test_보정_실패가_판정을_막지_않는다():
    """attach 는 실패해도 True/False 만 돌려주고 예외를 올리지 않는다."""
    from app.engine.opponent_adjust import attach

    class _Boom:
        async def fetchrow(self, *a):
            raise RuntimeError("db down")

    jg = _jg([{"date": "2026-09-01", "opponent": "A", "runs": 4}])
    assert await attach(_Boom(), jg) is False
    assert jg["m1_adjust"] == {}


# ═══════════════ 배선 — 붙지 않은 자료는 없는 것과 같다

def test_보정이_자료1_페이로드에_실린다():
    from app.engine.matchup import boxscore_payload

    jg = _jg([{"date": "2026-09-01", "opponent": "A", "runs": 4}])
    jg["m1_adjust"] = {"home": {"배율": 1.24, "상대평균실점": 3.8}}
    out = boxscore_payload(jg)
    assert out["home"]["상대보정"]["배율"] == 1.24


def test_보정이_없으면_칸을_만들지_않는다():
    """⚠️ 없는 칸은 만들지 않는다 — 빈 칸도 프롬프트를 늘린다."""
    from app.engine.matchup import boxscore_payload

    jg = _jg([{"date": "2026-09-01", "opponent": "A", "runs": 4}])
    assert "상대보정" not in boxscore_payload(jg)["home"]


def test_파이프라인이_자료11_뒤에_보정을_부른다():
    src = open("app/pipeline.py", encoding="utf-8").read()
    assert "from app.engine.opponent_adjust import attach as _m1adj" in src
    ctx = src.index("자료11 조립 실패")
    adj = src.index("opponent_adjust import attach")
    judge = src.index("if await judge_matchup(jg, redis, date")
    assert ctx < adj < judge, "보정은 자료11 뒤·판정 앞이어야 한다"


def test_프롬프트가_새_필드를_설명한다():
    """판정이 무엇인지 모르는 숫자는 근거가 되지 못한다."""
    from app.engine.prompts import MATCHUP

    assert "상대보정" in MATCHUP and "배율" in MATCHUP
    from app.engine.matchup import _LEDGER_REF

    assert "선발기준선" in _LEDGER_REF
    assert "분위수가 없으면" in _LEDGER_REF


def test_L1_이_새_숫자를_대조한다():
    """🔴 자료12 가 감시 없이 배포됐던 실수를 되풀이하지 않는다."""
    import re

    from app.engine.fact_audit import UNIT_PATTERNS

    keys = {k for _, _, ks in UNIT_PATTERNS for k in ks}
    for need in ("상대평균실점", "우리득점", "배율", "평균이닝", "평균실점"):
        assert need in keys, f"{need} 가 L1 대조 목록에 없다"
    pats = [p for p, _, _ in UNIT_PATTERNS]
    assert len(pats) == len(set(pats)), "같은 패턴을 두 번 적었다 — 사본이다"
    for p in pats:
        assert re.compile(p).groups == 1, f"캡처 그룹이 1개가 아니다: {p}"
