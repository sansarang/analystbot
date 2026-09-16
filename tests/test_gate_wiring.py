"""GATE-2 — 사전값·괴리·게이트 배선.

🔴 실측 결함 2026-09-14: `PRI-1`(prior)·`GATE-1`(gate)이 순수 함수를 만들었는데
   **부르는 곳이 0** 이었다. `pick_ledger.p_prior·prior_src·gate_reason` 은
   영원히 NULL 이었고, 딥서치 대상 선정(조건 A)이 설 자리가 없었다.

⚠️ 게이트 라벨을 별도 칸에 복사하지 않는다 — `gate_reason` 의 **첫 토큰**이
   라벨이고 구분자는 " · " 다. 같은 사실을 두 칸에 적으면 한쪽만 고쳐진다.
"""
import ast
import inspect

import pytest

from app.engine import gate as G
from app.engine import pick_ledger as PL


class _Conn:
    def __init__(self, game, snaps):
        self.game = game
        self.snaps = snaps
        self.executed: list[tuple] = []

    async def fetchrow(self, sql, *args):
        # ⚠️ [PRI-4] 성적 집계도 `FROM games` 다 — 경기 조회와 구분해야 한다.
        if "count(*) FILTER" in sql:
            return {"w": 0, "d": 0, "l": 0}
        return self.game if "FROM games" in sql else None

    async def fetch(self, sql, *args):
        return self.snaps

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "UPDATE 1"


def _snap(side, odds, home, away, tag="open"):
    return {"provider": "oddsportal", "snap_tag": tag, "side": side,
            "odds": odds, "home": home, "away": away}


@pytest.mark.asyncio
async def test_티어_사전값과_open_시장을_대조해_원장에_남긴다():
    home, away = "FC Internazionale Milano", "Udinese Calcio"   # 티어 1 · 3
    conn = _Conn({"sport": "soccer", "league": "세리에A", "home": home, "away": away},
                 [_snap(home, 2.00, home, away), _snap(away, 2.00, home, away)])

    out = await PL.record_prior(conn, game_id=7434)

    assert out["prior_src"] == "tier", "티어가 채워졌으면 미기입이 아니다"
    assert 0.55 < out["p_prior"] < 0.70, out["p_prior"]
    assert out["label"] in (G.OVER, G.DOUBT, G.AGREE, G.BOARD)
    # 🔴 [U5 2026-09-15] 종전 계약은 "원장 UPDATE 1회"였다. 가설(H1)을
    #    게이트 직후에 기록하면서 2회가 된다 — **둘 다 필요하다**.
    #    재는 뜻은 그대로다: 같은 값을 여러 번 쓰지 않는다.
    prior_w = [c for c in conn.executed if "prior_src" in str(c[0])]
    hyp_w = [c for c in conn.executed if "SET hypothesis" in str(c[0])]
    assert len(prior_w) == 1, conn.executed
    assert len(hyp_w) <= 1, conn.executed
    _, args = conn.executed[0]
    assert args[0] == 7434
    assert args[2] == "tier"
    # 🔴 라벨은 gate_reason 의 첫 토큰이다(별도 칸에 복사하지 않는다).
    assert args[4].split(" · ")[0] == out["label"]


@pytest.mark.asyncio
async def test_티어가_비면_사전값을_안_만든다():
    """🔴 [U3 2026-09-15 사용자 지시] 종전 계약은 "중앙값으로 메우되 그 사실을
    남긴다"(prior_src='tier:미기입')였다. 이제 **사전값 자체를 만들지 않는다** —
    채운 팀과 안 채운 팀이 같은 근거를 가진 것처럼 보이면 안 된다(리즈 사례).
    ⚠️ 조용히 빠지지도 않는다. p_prior=NULL · prior_src='none' 으로 **기록**하고
       gate_reason 에 어느 팀이 비었는지 남긴다."""
    conn = _Conn({"sport": "soccer", "league": "덴마크 수페르리가",
                  "home": "AC Horsens", "away": "AGF Aarhus"},
                 [_snap("AC Horsens", 2.0, "AC Horsens", "AGF Aarhus"),
                  _snap("AGF Aarhus", 2.0, "AC Horsens", "AGF Aarhus")])

    out = await PL.record_prior(conn, game_id=1)

    # 🔴 [PA-6 2026-09-16] 종전에는 `out is None` 을 단언했다. 그건 규칙이
    #    아니라 **구현 방식**이었다 — 그 조기 반환 때문에 U5~U12 가 통째로
    #    건너뛰어졌다(실측 ACLE 2경기: 가설·확인·가감·흐름·구조·결정축 전부 빔).
    #    U3 이 말로 적은 규칙("사전값을 만들지 않고 NULL·none 으로 기록한다")은
    #    그대로다 — 아래에서 그 규칙을 직접 잰다.
    from app.engine import gate as _G
    assert out is not None, "보드 고정을 돌려줘야 U5~U12 가 돈다"
    assert out["label"] == _G.BOARD, out
    assert out["p_prior"] is None and out["prior_src"] == "none", out
    saved = [c for c in conn.executed if "prior_src" in str(c[0])]
    assert saved, "조용히 빠졌다 — 기록이 없다"
    args = saved[-1][1]
    assert args[1] is None, f"p_prior 가 NULL 이 아니다: {args[1]}"
    assert args[2] == "none", args[2]
    assert "티어 미기입" in str(args[4]), args[4]


@pytest.mark.asyncio
async def test_기준선_시장이_없어도_확률을_지어내지_않는다():
    """⚠️ [GATE-3 2026-09-14] 종전 계약은 "아무것도 쓰지 않는다" 였다. 사용자
    지시로 **사유는 남기되 값은 비운다** 로 바뀌었다 — 아래 GATE-3 테스트가
    본문을 단언한다. 여기서는 **없는 값을 채우지 않는다**만 지킨다."""
    conn = _Conn({"sport": "soccer", "league": "세리에A",
                  "home": "AC Milan", "away": "AS Roma"}, [])

    await PL.record_prior(conn, game_id=1)

    # 🔴 [U5 2026-09-15] 종전 계약은 "원장 UPDATE 1회"였다. 가설(H1)을
    #    게이트 직후에 기록하면서 2회가 된다 — **둘 다 필요하다**.
    #    재는 뜻은 그대로다: 같은 값을 여러 번 쓰지 않는다.
    prior_w = [c for c in conn.executed if "prior_src" in str(c[0])]
    hyp_w = [c for c in conn.executed if "SET hypothesis" in str(c[0])]
    assert len(prior_w) == 1, conn.executed
    assert len(hyp_w) <= 1, conn.executed
    assert conn.executed[0][1][3] is None, "시장 확률을 지어내지 않는다"


def test_티어_파일_키는_야구가_종목_축구가_리그다():
    assert PL._tier_key("mlb", "MLB") == "mlb"
    assert PL._tier_key("kbo", "KBO") == "kbo"
    assert PL._tier_key("soccer", "세리에A") == "serie_a"
    assert PL._tier_key("soccer", "없는리그") is None


def test_판정_기록이_사전값을_부른다():
    tree = ast.parse(inspect.getsource(PL))
    # 🔴 [PA-19 2026-09-16] 호출이 `_record_side_effects` 안으로 한 단계
    #    들어갔다 — `unchanged` 분기와 삽입 분기가 **같은 함수**를 부르게
    #    모았기 때문이다(사본 금지). 뜻은 그대로다: 판정 기록이 이것을 부른다.
    #    그래서 `record_analysis` 본문이 아니라 **호출 사슬**을 본다.
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "record_analysis")
    assert [n for n in ast.walk(fn) if isinstance(n, ast.Call)
            and getattr(n.func, "id", "") == "_record_side_effects"], \
        "record_analysis 가 부수 기록을 안 부른다"
    helper = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.AsyncFunctionDef)
                  and n.name == "_record_side_effects")
    calls = [n for n in ast.walk(helper)
             if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "record_prior"]
    assert len(calls) == 1


# ── GATE-3: 기준선이 없어도 사유를 남긴다

@pytest.mark.asyncio
async def test_기준선_배당이_없어도_사유를_원장에_남긴다():
    """🔴 [GATE-3 사용자 지시] 조용히 빠져나가면 "게이트를 안 돌린 경기"와
    "배당이 없어 못 돌린 경기"를 나중에 구분할 수 없다.

    ⚠️ 시장 확률을 지어내지 않는다 — `gate.classify(prior, None)` 이 돌려주는
       **보드 고정**을 그대로 쓴다(판정 규칙은 원본이 정한다).
    """
    conn = _Conn({"sport": "soccer", "league": "세리에A",
                  "home": "FC Internazionale Milano", "away": "Udinese Calcio"}, [])

    out = await PL.record_prior(conn, game_id=7434)

    # 🔴 [U5 2026-09-15] 종전 계약은 "원장 UPDATE 1회"였다. 가설(H1)을
    #    게이트 직후에 기록하면서 2회가 된다 — **둘 다 필요하다**.
    #    재는 뜻은 그대로다: 같은 값을 여러 번 쓰지 않는다.
    prior_w = [c for c in conn.executed if "prior_src" in str(c[0])]
    hyp_w = [c for c in conn.executed if "SET hypothesis" in str(c[0])]
    assert len(prior_w) == 1, conn.executed
    assert len(hyp_w) <= 1, conn.executed
    _, args = conn.executed[0]
    assert args[0] == 7434
    assert args[3] is None, "없는 시장 확률을 채우지 않는다"
    assert args[4].split(" · ")[0] == G.BOARD
    assert "기준선" in args[4], "왜 못 쟀는지가 남아야 한다"
    assert out is not None and out["label"] == G.BOARD


# ── PRI-4: 올해 성적이 사전값에 들어간다

class _FormConn(_Conn):
    """성적 집계에 답하는 커넥션. 팀별 (승,무,패)를 주입한다."""

    def __init__(self, game, snaps, form):
        super().__init__(game, snaps)
        self.form = form
        self.form_args: list[tuple] = []

    async def fetchrow(self, sql, *args):
        if "count(*) FILTER" in sql:
            self.form_args.append(args)
            w, d, l = self.form.get(args[3], (0, 0, 0))
            return {"w": w, "d": d, "l": l}
        return await super().fetchrow(sql, *args)


@pytest.mark.asyncio
async def test_올해_성적이_사전값을_움직인다():
    """🔴 실측 2026-09-14: gp=0 으로 넣으면 티어 한 단계 차이가 홈 이점(60)과
    상쇄돼 Roma@Torino 가 36.5/27.0/36.5 로 평평했다. 로마는 3전 전승이었다."""
    game = {"sport": "soccer", "league": "세리에A",
            "home": "Torino FC", "away": "AS Roma"}
    flat = await PL.record_prior(_FormConn(game, [], {}), game_id=7433)
    conn = _FormConn(game, [], {"AS Roma": (3, 0, 0), "Torino FC": (0, 0, 2)})
    with_form = await PL.record_prior(conn, game_id=7433)

    assert flat["prior_src"] == "tier"
    assert with_form["prior_src"] == "tier+form(2/3)", "gp 를 원장이 말해야 한다"
    assert with_form["p_prior"] < flat["p_prior"] - 0.05, \
        "2패 팀의 홈 사전값이 내려가야 한다"


@pytest.mark.asyncio
async def test_성적_집계는_그_리그_그_시즌만_센다():
    """🔴 컵·대항전은 `games` 에 없다(리그 일정만 적재). 그래도 **리그·시즌**으로
    좁히는 것을 계약으로 잠근다 — 나중에 컵이 들어와도 새지 않게."""
    game = {"sport": "soccer", "league": "세리에A",
            "home": "Torino FC", "away": "AS Roma"}
    conn = _FormConn(game, [], {})

    await PL.record_prior(conn, game_id=7433)

    assert len(conn.form_args) == 2
    for args in conn.form_args:
        assert args[0] == "soccer" and args[1] == "세리에A"
        assert args[2].date().isoformat() == "2026-07-01", "티어 파일의 시즌이 원본"


def test_시즌_시작일은_티어_파일이_정한다():
    from app.engine import prior as P

    assert P.season_start("serie_a").isoformat() == "2026-07-01"   # 가을~봄
    assert P.season_start("kbo").isoformat() == "2026-01-01"       # 달력 연도
    assert P.season_start("없는리그") is None
