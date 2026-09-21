"""[W2] 식별자 배선 — **이름은 키가 아니다.**

🔴 09-21 실측이 지시문의 전제 하나를 뒤집었다.

    SELECT batter, team, count(*) … WHERE batter='박건우'
      박건우 · NC Dinos      26회 · 타순 5~6번
      박건우 · Lotte Giants   9회 · 타순 8번
      g1723(NC vs 롯데 09-08) 에 **양 팀 모두** 등장 (NC 2번 · 롯데 8번)
      둘 다 source='boxscore'

   즉 **동명이인이 실재한다.** "롯데 결장 목록의 박건우는 타 팀 선수"라는
   지시문 서술(D14b)은 사실이 아니었다. 이름만으로 소속을 판정하면 진짜
   롯데 박건우가 지워진다 — 그것이 더 큰 결함이다.
   → 이름이 **한 팀으로만** 이어질 때만 판정하고, 두 팀 이상이면 `ambiguous`
     로 두고 **어느 쪽으로도 세지 않는다.**

🔴 양쪽 복사의 원인은 **둘로 갈렸다**(운영 상자 실측):

    scout:soccer:11330   양쪽 카드의 team 이 **둘 다** 'Club Atlético de Madrid'
                         → `_same_team('Club Atlético de Madrid','Real Madrid CF')`
                           가 공통 토큰 **'madrid'** 로 True 였다.
    scout:soccer:11334   team 은 'SonderjyskE' / 'Randers FC' 로 **다른데**
                         out 목록이 글자까지 같다 → LLM 이 한쪽 명단을 양쪽에 적었다.

   원인이 다르므로 고치는 곳도 다르다. 앞은 **귀속 규칙**, 뒤는 **중복 탐지**다.
"""
from __future__ import annotations

import pytest


# ── ① 귀속 규칙 — 공통 토큰으로 붙이지 않는다 ─────────────────────
def test_공통_토큰만으로_귀속하지_않는다():
    """🔴 11330 재현: 'madrid' 가 겹친다고 AT마드리드 카드를 레알에 붙였다."""
    from app.collectors.satellite import assign_side

    home, away = "Real Madrid CF", "Club Atlético de Madrid"
    assert assign_side("Club Atlético de Madrid", home, away) == "away"
    assert assign_side("Real Madrid CF", home, away) == "home"
    # 🔴 두 팀이 **공유하는** 토큰뿐이면 못 정한다 — 한쪽으로 찍지 않는다.
    assert assign_side("Madrid", home, away) is None


def test_고유_토큰이_있으면_귀속한다():
    """⚠️ 반대 위험 — 규칙을 좁히느라 정상 귀속까지 막으면 안 된다."""
    from app.collectors.satellite import assign_side

    home, away = "Kashiwa Reysol", "FC Machida Zelvia"
    assert assign_side("Machida Zelvia", home, away) == "away"
    assert assign_side("Kashiwa Reysol", home, away) == "home"
    assert assign_side("가시와 레이솔", home, away) is None   # 한글표기는 토큰이 다르다


def test_일반_토큰은_식별자가_아니다():
    from app.collectors.satellite import assign_side

    # FC·United 같은 흔한 말로 팀을 가르지 않는다.
    assert assign_side("FC", "FC Seoul", "FC Anyang") is None
    assert assign_side("United", "Incheon United", "Manchester United") is None


# ── ② 중복 탐지 — 같은 명단이 양쪽에 오면 둘 다 미상 ──────────────
def test_같은_명단이_양쪽이면_어느_쪽에도_세지_않는다():
    """🔴 11334 재현: team 은 다른데 out 목록이 글자까지 같다."""
    from app.collectors.satellite import resolve_attribution

    box = {
        "home": {"team": "SonderjyskE",
                 "out": ["Mike Themsen — Hamstring injury",
                         "Wessel Dammers — unknown injury"]},
        "away": {"team": "Randers FC",
                 "out": ["Mike Themsen — Hamstring injury",
                         "Wessel Dammers — unknown injury"]},
    }
    got = resolve_attribution(box)
    for side in ("home", "away"):
        assert got[side]["out"] == [], f"{side}: 못 믿을 명단을 그대로 뒀다"
        assert got[side].get("out_unknown"), "버리기만 하고 기록을 안 남겼다"
        assert got[side].get("attribution") == "unknown"


def test_명단이_다르면_그대로_둔다():
    """⚠️ 반대 위험 — 정상 명단까지 지우면 결장이 영영 판정에 안 닿는다."""
    from app.collectors.satellite import resolve_attribution

    box = {"home": {"team": "A", "out": ["가"]},
           "away": {"team": "B", "out": ["나"]}}
    got = resolve_attribution(box)
    assert got["home"]["out"] == ["가"]
    assert got["away"]["out"] == ["나"]
    assert not got["home"].get("out_unknown")


def test_한쪽만_있으면_복사로_보지_않는다():
    from app.collectors.satellite import resolve_attribution

    box = {"home": {"team": "A", "out": ["가", "나"]}, "away": {"team": "B", "out": []}}
    got = resolve_attribution(box)
    assert got["home"]["out"] == ["가", "나"]


# ── ③ 로스터 대조 — 유일할 때만 판정한다 ──────────────────────────
def test_이름이_한_팀으로만_이어지면_불일치를_잡는다():
    from app.engine.performance import filter_by_roster

    roster = {"양석환": {"Doosan Bears"}, "고승민": {"Lotte Giants"}}
    kept, dropped = filter_by_roster(["롯데 양석환 결장", "롯데 고승민 결장"],
                                     team="Lotte Giants", roster=roster)
    assert kept == ["롯데 고승민 결장"]
    assert dropped and "양석환" in dropped[0]["name"]


def test_동명이인은_지우지_않는다():
    """🔴 실측: 박건우는 NC·롯데 **둘 다** 있다(동명이인). 이름으로 지우면
    진짜 롯데 박건우가 사라진다 — 그것이 더 큰 결함이다."""
    from app.engine.performance import filter_by_roster

    roster = {"박건우": {"NC Dinos", "Lotte Giants"}}
    kept, dropped = filter_by_roster(["롯데 박건우 결장"],
                                     team="Lotte Giants", roster=roster)
    assert kept == ["롯데 박건우 결장"], "동명이인을 불일치로 지웠다"
    assert not dropped


def test_로스터에_없는_이름은_지우지_않는다():
    """⚠️ 모름을 위반으로 만들지 않는다 — 신인·외국인 표기 차이가 그렇다."""
    from app.engine.performance import filter_by_roster

    kept, dropped = filter_by_roster(["롯데 아무개 결장"],
                                     team="Lotte Giants", roster={"고승민": {"Lotte Giants"}})
    assert kept == ["롯데 아무개 결장"]
    assert not dropped


def test_로스터가_비면_아무것도_지우지_않는다():
    from app.engine.performance import filter_by_roster

    kept, dropped = filter_by_roster(["가", "나"], team="X", roster={})
    assert kept == ["가", "나"] and not dropped


# ── ④ 별칭 — 자동 승격 금지 (기존 계약 유지) ──────────────────────
def test_alias_no_auto_promote():
    """🔴 사람이 `approved: true` 로 바꾼 행만 별칭표로 간다(AC밀란 오매칭 방지)."""
    import pathlib

    import yaml

    p = pathlib.Path("config/team_alias_pending.yaml")
    assert p.exists(), "대기표가 없다"
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    rows = doc.get("pending") or doc.get("teams") or []
    assert isinstance(rows, list) and rows, doc
    for r in rows:
        assert "fotmob_id" in r, f"FotMob id 칸이 없다: {r}"


def test_승인되지_않은_별칭은_쓰이지_않는다():
    from app.collectors.fotmob import _name_map

    m = _name_map()
    assert isinstance(m, dict)
    # 대기표의 미승인 이름이 치환표에 새어 들어오면 안 된다.
    import pathlib

    import yaml

    doc = yaml.safe_load(
        pathlib.Path("config/team_alias_pending.yaml").read_text(encoding="utf-8")) or {}
    for r in (doc.get("pending") or doc.get("teams") or []):
        if r.get("approved"):
            continue
        ours = str(r.get("ours") or r.get("our_name") or "")
        if ours:
            assert ours.lower() not in {k.lower() for k in m}, \
                f"미승인 별칭이 치환표에 있다: {ours}"


# ── ⑤ 배선 — 추출이 실제로 이 규칙을 지나는가 ─────────────────────
def test_추출이_귀속_규칙을_지난다():
    import inspect

    from app.collectors import satellite as SAT

    src = "\n".join(ln for ln in inspect.getsource(SAT.extract_game_facts)
                    .splitlines() if not ln.strip().startswith("#"))
    assert "assign_side" in src or "resolve_attribution" in src, \
        "추출이 종전 `_same_team` 그대로다"


@pytest.mark.asyncio
async def test_한_카드가_양쪽에_들어가지_않는다():
    """🔴 11330 의 진짜 모양 — LLM 이 팀 하나만 돌려줬을 때."""
    from app.collectors import satellite as SAT

    rows = [{"team": "Club Atlético de Madrid", "out": ["Sørloth"],
             "doubt": [], "xi": [], "xi_status": None, "bench_notable": [],
             "last3": [], "midweek": "", "notes": "", "source": "", "published": ""}]
    got = SAT.split_rows_by_side(rows, home="Real Madrid CF",
                                 away="Club Atlético de Madrid")
    assert got.get("away") is not None
    assert got.get("home") is None, "한 팀 카드가 양쪽에 들어갔다"


# ── ⑥ 배선 — ⑤가 실제로 로스터를 지나는가 ────────────────────────
def test_결장이_로스터_대조를_지난다():
    import inspect

    from app.flow.nodes import n05_evidence as N

    src = inspect.getsource(N)
    assert "filter_by_roster" in src, "⑤가 로스터를 보지 않는다(만들어 놓고 안 이음)"
    assert "_ROSTER_SQL" in src, "로스터를 어디서 읽는지 코드에 없다"


@pytest.mark.asyncio
async def test_타_팀_선수는_증거에서_빠진다():
    """🔴 배선 확인 — 주입한 로스터로 ⑤가 실제로 거른다."""
    from app.flow.ctx import Ctx
    from app.flow.nodes import n05_evidence as N
    from app.flow.state import State

    st = State(run_id="r", game_id="1", sport="baseball", league="KBO",
               home="Lotte Giants", away="NC Dinos",
               kickoff_utc="2026-09-21T09:00:00+00:00", pick_side="home")
    st.n04_hyp = [{"id": "H", "vars": [{"var": "lineup_out", "is_core": True}]}]
    ctx = Ctx()
    ctx.inject = {
        "extract": {},
        # 🔴 양석환은 두산 선수다 — 롯데 명단에 있으면 빠져야 한다.
        #    고승민은 롯데다 — 남아야 한다.
        "absences": ["Lotte Giants 양석환 오늘 라인업에서 빠짐",
                     "Lotte Giants 고승민 오늘 라인업에서 빠짐"],
        "roster": {"양석환": {"Doosan Bears"}, "고승민": {"Lotte Giants"}},
    }
    st = await N.run(st, ctx)
    vals = [v for e in (st.n05_evidence or []) for v in (e.get("value") or [])]
    joined = " ".join(str(v) for v in vals)
    assert "고승민" in joined, f"같은 팀 선수가 사라졌다: {vals}"
    assert "양석환" not in joined, f"타 팀 선수가 증거로 들어갔다: {vals}"


# ── ⑦ 매칭 미연결을 실제로 세는가 ─────────────────────────────────
def test_match_unmapped를_세는_코드가_있다():
    """🔴 `CODES` 에 이름만 있고 세는 코드가 없으면 그것은 '만들어 놓고 안 이음'이다."""
    import inspect

    from app.ops import selfcheck as SC

    assert "match_unmapped" in SC.CODES
    src = inspect.getsource(SC)
    assert "_unmapped" in src, "이름표만 있고 세는 함수가 없다"
    assert "_unmapped(pool)" in inspect.getsource(SC.run), "run() 이 부르지 않는다"


def test_대기표의_확인된_이름은_추정이_아니다():
    """🔴 `fotmob_id` 가 있는 행은 **실제로 읽은 값**이어야 한다.
    추정으로 채우면 AC밀란 오매칭이 재발한다."""
    import pathlib

    import yaml

    doc = yaml.safe_load(pathlib.Path(
        "config/team_alias_pending.yaml").read_text(encoding="utf-8")) or {}
    rows = doc.get("pending") or []
    ids = {r["ours"]: r.get("fotmob_id") for r in rows}
    # 09-20 하루치 목록에서 실제로 읽은 값들(실측).
    assert ids.get("Brondby IF") == 8595
    assert ids.get("SonderjyskE") == 8487, "확인한 id 를 적지 않았다"
    # 🔴 확인했다고 자동 승격하지 않는다.
    assert all(not r.get("approved") for r in rows), "사람 승인 없이 승격됐다"


@pytest.mark.asyncio
async def test_어제_경기한_팀을_미연결로_세지_않는다():
    """🔴 첫 구현의 오탐 재현 — ±1일 경기를 **오늘** 목록과 대조해서
    Kashiwa Reysol·Manchester City FC 까지 25건이 찍혔다.
    FotMob 목록은 그 날짜에 경기하는 팀만 담는다."""
    import inspect

    from app.ops import selfcheck as SC

    src = inspect.getsource(SC._unmapped)
    assert "interval '1 day'" not in src, "±1일 창을 그대로 쓴다(오탐)"
    assert "::date = $1" in src, "같은 날짜끼리 대조하지 않는다"


def test_매칭_규칙을_베끼지_않는다():
    """🔴 두 번째 오탐 — "정규화 후 정확 일치"로 베껴 썼더니 AC Milan·
    Juventus FC 까지 20건이 찍혔다. 운영이 쓰는 `find_match` 는 **포함 관계**를
    허용한다(`Juventus` ⊂ `Juventus FC`). 사본은 원본을 따라가지 않는다."""
    import inspect

    from app.ops import selfcheck as SC

    src = inspect.getsource(SC._unmapped)
    assert "find_match" in src, "진짜 매처를 부르지 않는다"
    assert "norm(" not in src, "정규화 규칙을 여기서 다시 쓴다(사본)"


def test_FotMob_날짜는_UTC_기준이다():
    """🔴 세 번째 오탐 — KST 날짜로 찾으면 유럽 야간 경기가 전부 빠진다.
    실측 2026-09-21:
        13979 US Lecce@AC Milan  UTC 09-20 18:45 · KST 날짜 09-21
          FotMob 20260920 → 찾음(5749680)  ·  20260921 → 없음
    """
    import inspect

    from app.ops import selfcheck as SC

    src = inspect.getsource(SC._unmapped)
    assert "astimezone(timezone.utc)" in src, "FotMob 날짜를 UTC 로 잡지 않는다"
    assert 'strftime("%Y%m%d")' in src
