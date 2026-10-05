"""🔴🔴 **프랑스–벨기에 실측(2026-10-05)이 드러낸 열여섯 자리.**

사용자 지시: *"전부다 순서대로 수정하고"*. 그 열여섯을 순서대로 잠근다.
⚠️ 전부 **파이프라인 앞단**(자료 수집)이다 — 판정·시나리오는 건강했다.
"""
from __future__ import annotations

import ast
import inspect


# ══════════════════════════════════════════════════════════════════
# ① `done.variables` 가 **문자열**로 와도 변수를 잃지 않는다
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측: 프랑스 에이전트가 `variables` 를 **JSON 문자열**로 보냈고
#     (`'[{"id": "V1", …'`), 코드가 `row.get` 을 불러 터졌다 —
#     `'str' object has no attribute 'get'`. **15,455자가 통째로 버려졌다.**
#  🔴 스키마는 `{"type":"array"}` 로 맞았다. 모델이 안 지킨 것이고, 그렇다면
#     **코드가 꼴을 맞춰야** 한다(§8-3: 고유한 모양은 들어오는 자리에서 바꾼다).
def test_fb1_done_변수가_문자열로_와도_읽는다():
    from app import agentloop
    rows = [{"id": "V1", "type": "absence", "team": "team:000081",
             "subject": "team:000081", "claim": "결장이다", "quote": "out",
             "source_url": "https://e.com/a", "lang": "en",
             "direction_hint": "away", "confidence": "high",
             "checked": True}]
    import json
    got, why = agentloop.parse_args({"variables": json.dumps(rows)}, inp=None)
    assert got or "variables" not in why, (
        f"🔴 문자열로 온 `variables` 를 **버렸다** — 실측에서 15,455자가 "
        f"사라졌다: {why!r}")
    plain, _ = agentloop.parse_args({"variables": rows}, inp=None)
    assert len(got) == len(plain), (
        f"🔴 문자열 길과 목록 길이 **다른 수**를 낸다: {len(got)} vs "
        f"{len(plain)}")


def test_fb1_로그가_문자수를_줄수라고_적지_않는다():
    """🔴 `변수 15455줄` 은 **문자 수**였다 — 터지기 전 유일한 단서가 거짓말했다."""
    from app import agentloop
    src = inspect.getsource(agentloop)
    at = src.find("인자 칸=")
    assert at > 0, "🔴 그 로그 줄을 못 찾았다 — 이 계약을 고쳐라"
    seg = src[at:at + 400]
    assert "줄" not in seg.split("첫 줄")[0].replace("인자 칸=", ""), (
        "🔴 로그가 아직 `줄` 로 센다 — 문자열이 오면 **문자 수**를 줄 수라고 "
        "적는다(실측: `변수 15455줄`)")


# ══════════════════════════════════════════════════════════════════
# ② 대회 축이 **정식명 한 덩어리**로만 비교한다
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측: 경기 대회가 `UEFA Nations League A Grp. 1` 인데 에이전트 질의
#     `… 2026 Nations League` 가 대회를 **0개**로 셌다. 검색 22건 중 **15건**이
#     거부(68%)되고 그중 **10건이 `Nations League` 를 들고 있었다.**
#     `Grp.` ↔ `Group` **한 글자** 차이로도 실패했다.
#  🔴 파라과이 별칭 `Albirroja`·`NLDS` 와 **같은 병**이다 — 정식명만 본다.
#  🔴 고치는 방향: 대회명을 **낱말로 쪼개** 질의가 그 핵을 담았나 본다.
#     ⚠️ 짧은 조각(`A`·`1`·`Grp.`)으로 거짓 통과를 만들면 안 된다.
_COMP = "UEFA Nations League A Grp. 1"


#  ⚠️ `count_parts` 는 **선언을 믿는다**(호출부가 질의에 있는 것만 넘긴다는
#     약속). 그래서 진짜 자리는 **선언하는 쪽**이다 — `agentloop._parts` 가
#     `comp.lower() in low` 로 정식명 한 덩어리만 봤다.
#  🔴 판정을 **한 곳**(`querygate.comp_in`)에 두고 `_parts` 가 그것을 부른다.
def test_fb2_대회_일치_판정이_한_곳에_있다():
    from app import querygate as Q
    assert hasattr(Q, "comp_in"), (
        "🔴 `querygate.comp_in(대회, 질의)` 가 없다 — 대회 일치 판정이 "
        "호출부마다 흩어지면 한쪽만 고쳐진다(#1)")
    for q in ("France national team recent results 2026 Nations League",
              "France Belgium head to head rivals 2026 Nations League",
              "France vs Belgium UEFA Nations League A Group 1 5 October 2026",
              "Chiba Lotte Seibu 日本シリーズ 2026"):
        if "Nations" in q or "Group" in q:
            assert Q.comp_in(_COMP, q), (
                f"🔴 `{_COMP}` 인데 못 알아본다: {q!r}")


def test_fb2_짧은_조각으로는_안_센다():
    """🔴 `A`·`1`·`Grp.` 같은 조각이 아무 글에 섞여 거짓으로 서면 안 된다."""
    from app import querygate as Q
    for q in ("France A 1 weather", "Belgium grp 1 shop", "France hotel A",
              "France league table shop"):
        assert not Q.comp_in(_COMP, q), f"🔴 조각만 들고 대회로 봤다: {q!r}"


def test_fb2_파트가_그_판정을_쓴다():
    """🔴 **배선**(#2) — `_parts` 가 `comp.lower() in low` 를 안 쓴다."""
    import textwrap

    from app import agentloop
    src = textwrap.dedent(inspect.getsource(agentloop.Tools._parts))
    tree = ast.parse(src)
    # 🔴 **부르는지**를 본다 — 주석에 이름이 있는 것과 부르는 것은 다르다(D46).
    #    ⚠️ F03(정식명 한 덩어리로 되돌리기)이 **통과했다**: 주석에 남은
    #       `comp_in` 글자를 문자열 검사가 세어 버렸다.
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "comp_in" in called, (
        f"🔴 `_parts` 가 `comp_in` 을 **안 부른다**(부르는 것: "
        f"{sorted(called)}) — 대회 판정이 흩어진다")


# ══════════════════════════════════════════════════════════════════
# ③ 서는 `competition` 이 **가짜 이름**이다
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측: 이 경기에서 `competition` 으로 센 4건을 전부 재 봤더니 **정식명
#     전체일치는 모두 실패**였다. 실제로 센 것은 `WHEN_WORDS`(`preview`·
#     `injury`)의 **중복 카운트**이고, 거기에 `competition` 이름이 붙었다.
#  🔴 수를 늘리는 규칙 자체는 둔다(핵심어가 둘이면 질의가 구체적이다) —
#     **이름을 바로잡는다.** 축 이름이 거짓이면 *"왜 통과했나"* 를 못 되짚는다.
def test_fb3_핵심어_중복을_대회라고_부르지_않는다():
    from app import querygate as Q
    # 🔴 대회 선언이 **없고** 핵심어만 둘인 질의
    n, got = Q.count_parts("Portugal preview injury team news 2026-10-05",
                           parts={"team": "Portugal"})
    assert "competition" not in got, (
        f"🔴 핵심어 중복을 `competition` 이라 부른다({got}) — 그 질의에 대회는 "
        f"없다. 실측 프랑스–벨기에에서 네 번 그렇게 적혔다")
    assert n >= 3, (
        f"🔴 이름만 고치면서 **수를 깎았다**({n}개) — 핵심어가 둘이면 구체적인 "
        f"질의라는 판단은 그대로 둬야 한다")


# ══════════════════════════════════════════════════════════════════
# ④ 난타전이 **거의 무조건** 걸렸다 — 지표가 두 배였다
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측: `recent_avg_goals` 는 코드 자신이 **"최근 평균 총득점"**이라 적는다
#     (홈골+원정골). 그런데 난타전 판정이 **두 팀 것을 더했다**:
#     프랑스 3.2 + 벨기에 2.8 = **6.0** ≥ 4.0. 🔴 총득점을 **두 번 센다.**
#     → 양 팀이 각각 평균 2골 경기만 해도 합 4.0 → 거의 모든 축구 경기가
#       난타전 필수가 된다(축구 경기 평균 총득점은 보통 2.5~3.0).
#  🔴 사용자 결정 2026-10-05: *"**팀 득점 평균**으로 바꾼다(지시 원문대로)"* —
#     문턱 4.0·3.0 은 그대로, 차단(`scenario_incomplete`)도 유지.
#  ⚠️ 새 자료는 필요 없다 — `_form_sequence` 가 `goals_for` 를 **이미** 든다.
def test_fb4_폼이_팀_득점_평균을_낸다():
    from app.collect import fotmob
    assert hasattr(fotmob, "scored_avg"), (
        "🔴 `fotmob.scored_avg(수열)` 이 없다 — 팀 득점 평균을 셀 곳이 없다")
    seq = [{"goals_for": 1, "goals_against": 0},
           {"goals_for": 1, "goals_against": 0},
           {"goals_for": 1, "goals_against": 1}]
    assert fotmob.scored_avg(seq) == 1.0, fotmob.scored_avg(seq)
    # 🔴 **못 재면 `None`** — 0 으로 때우면 난타전이 통째로 면제된다(#3)
    assert fotmob.scored_avg([]) is None
    assert fotmob.scored_avg([{"goals_against": 2}]) is None


def test_fb4_폼_사실에_그_칸이_실린다():
    """🔴 **배선**(#2) — 폼 사실이 `recent_scored_avg` 를 들고 나간다."""
    from app.collect import fotmob
    src = inspect.getsource(fotmob)
    assert '"recent_scored_avg"' in src, (
        "🔴 폼 사실에 `recent_scored_avg` 칸이 없다 — 판정이 그 수를 받을 "
        "길이 없다")


def test_fb4_난타전이_팀_득점_평균을_쓴다():
    """🔴 `avg_goals_by_team` 이 **총득점**이 아니라 **팀 득점**을 담는다."""
    from app import analyze
    src = inspect.getsource(analyze.context)
    at = src.find("avg_goals_by_team")
    assert at > 0, "🔴 그 칸을 못 찾았다 — 이 계약을 고쳐라"
    seg = src[max(0, at - 700):at + 700]
    assert "recent_scored_avg" in seg, (
        "🔴 난타전이 아직 `recent_avg_goals`(**총득점**)를 쓴다 — 두 팀 것을 "
        "더하면 총득점을 두 번 센다(실측 3.2+2.8=6.0)")


def test_fb4_실측_두_경기가_갈린다():
    """🔴 **실측으로 확인한다** — 프랑스–벨기에는 면제, 포르투갈–노르웨이는 필요.

    ⚠️ 수는 그 경기 스코어에서 나온 것이다(카드 R4·R5 가 인용한 사실).
    """
    from app import scenarios as S
    need_fb, why_fb = S.slugfest_needed(home_avg=1.0, away_avg=1.7)
    assert not need_fb, f"🔴 프랑스–벨기에(1.0+1.7=2.7)가 아직 걸린다: {why_fb}"
    need_pn, why_pn = S.slugfest_needed(home_avg=2.3, away_avg=1.7)
    assert need_pn, f"🔴 포르투갈–노르웨이(2.3+1.7=4.0)가 안 걸린다: {why_pn}"


def test_fb4_못_잰_팀을_카드가_적는다():
    """🔴 팀 득점 평균을 **못 잰 팀**이 이름으로 남는다(#3 조용한 0 금지).

    ⚠️ 못 재면 난타전이 **통째로 면제**된다 — 그 사실이 안 보이면 독자는
       *"난타전이 필요 없었다"* 로 읽는다.
    """
    from app import classify, scenarios
    game = classify.Game(home="France", away="Belgium", sport="soccer",
                         league="UEFA Nations League A Grp. 1")
    res = scenarios.Result()
    res.drafts = [scenarios.Draft(id="A", scores=["1-0"], strength=1.0,
                                  template_id="t", why="w")]
    scenarios._slugfest_gate(res, game, {"avg_goals_missing": ["France"]})
    said = " ".join(res.notes or [])
    assert "못 쟀다" in said or "못 잰" in said, (
        f"🔴 못 잰 것을 조용히 넘겼다: {res.notes}")
    assert "France" in said, (
        f"🔴 **어느 팀**을 못 쟀는지 이름이 없다: {res.notes}")


# ══════════════════════════════════════════════════════════════════
# ⑤ 리그 순위표가 **404** 였다 — 조별 하위 id 를 썼다
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측: `fotmob.com/leagues/920741/table/uefa-nations-league-a-grp-1`
#     → **HTTP 404**(두 팀 모두). 그래서 포아송 격자가 전멸하고
#     *"확률 격자를 못 만들었다 ×2"* 가 났다 — 생존 수가 확률이 아니라
#     **strength 개수** 가중으로만 섰다.
#  🔴 받아서 확인했다: 경기 JSON 의 `leagueId=920741`(조별 하위)은 404 이고
#     `parentLeagueId=9806`(대회)은 **200 이며 두 팀 이름이 들어 있다.**
#     → 종전 코드가 `leagueId` 를 **먼저** 썼다.
def test_fb5_순위표_주소가_부모_리그를_먼저_쓴다():
    from app.collect import fotmob
    j = {"props": {"pageProps": {"content": {"table": {
        "leagueId": "920741", "parentLeagueId": 9806,
        "tournamentNameForUrl": "UEFA Nations League A Grp. 1"}}}}}
    got = fotmob.league_table_url(j)
    assert got and "/leagues/9806/" in got, (
        f"🔴 조별 하위 id 를 쓴다(404 였다): {got!r}")
    # 🔴 **부모가 없으면** 그때는 하위 id 로 간다(그 리그는 그것뿐이다)
    j2 = {"props": {"pageProps": {"content": {"table": {
        "leagueId": "47", "tournamentNameForUrl": "Premier League"}}}}}
    got2 = fotmob.league_table_url(j2)
    assert got2 and "/leagues/47/" in got2, got2


# ══════════════════════════════════════════════════════════════════
# ⑥ `Stade de France` 의 **"France" 가 팀 축**으로 센다
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측: 결정 ⑥ 은 *"경기장+날짜만 있는 질의는 **여전히 bare**"* 를 요구한다.
#     그런데 `'Stade de France weather forecast October 5 2026'` 이
#     `['team','when','venue']` **3개**로 통과했다 — 경기장 이름 안의 `France`
#     를 **팀 이름**으로 센 것이다. 그 질의 결과: **본 URL 0개 · 본문 0개.**
#     결정 ⑥ 이 막으려던 바로 그 쓰레기다.
#  🔴 팀 이름을 찾을 때 **경기장 글자를 먼저 뺀다.**
def test_fb6_경기장_안의_나라이름을_팀으로_안_센다():
    from app import agentloop
    import datetime as _dt
    inp = agentloop.AgentInput(
        match_key="fotmob:5181794", home="team:000081", away="team:000021",
        kickoff_utc=_dt.datetime(2026, 10, 5, 18, 45,
                                 tzinfo=_dt.timezone.utc),
        home_names=("France",), away_names=("Belgium",),
        competition="UEFA Nations League A Grp. 1", venue="Stade de France",
        sport="soccer")
    tools = agentloop.Tools(inp)
    got = tools._parts("Stade de France weather forecast October 5 2026")
    assert "team" not in got, (
        f"🔴 경기장 안의 `France` 를 팀으로 셌다({got}) — 결정 ⑥ 이 무력화된다")
    assert got.get("venue"), f"🔴 경기장은 세야 한다({got})"
    # 🔴 **팀이 정말 있으면** 센다 — 지워 버리면 안 된다
    both = tools._parts("France vs Belgium at Stade de France October 5 2026")
    assert both.get("team") and both.get("opponent"), both


# ══════════════════════════════════════════════════════════════════
# ⑦ 변수가 **한 출처에 쏠린** 것을 카드가 말하지 않는다
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측: 검증 변수 5개 중 **3개가 같은 URL**(yahoo 프리뷰)에서 왔고 셋 다
#     `aggregator`(무게 0). 실질 무게는 구조 변수 둘뿐이었다. 🔴 카드만 보면
#     *"다섯 각도에서 봤다"* 로 읽힌다 — 실제로는 **한 기사**다.
#  🔴 상한을 걸지 않는다(변수가 더 줄어든다) — **사실을 적는다.**
def test_fb7_한_출처_쏠림을_카드가_적는다():
    from app import analyze
    assert hasattr(analyze, "source_spread"), (
        "🔴 `analyze.source_spread(변수들)` 이 없다 — 쏠림을 셀 곳이 없다")
    rows = [{"source_url": "https://a.com/1"}, {"source_url": "https://a.com/2"},
            {"source_url": "https://a.com/3"}, {"source_url": "https://b.com/1"}]
    n, said = analyze.source_spread(rows)
    assert n == 2, f"🔴 호스트 수가 틀렸다: {n}"
    assert "a.com" in said and "3" in said, said
    none, why = analyze.source_spread([])
    assert none == 0 and why, "🔴 0건일 때도 사유를 내야 한다(#3)"


def test_fb7_카드가_그_줄을_쓴다():
    """🔴 **배선**(#2) — 카드가 쏠림 줄을 만든다."""
    from app import analyze
    src = inspect.getsource(analyze)
    tree = ast.parse(src)
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "source_spread" in called, (
        "🔴 카드가 `source_spread` 를 **안 부른다** — 쏠림이 안 보인다")


# ══════════════════════════════════════════════════════════════════
# ⑧ 한 변수가 **여러 사실 묶음**이다
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측: `R4` 의 글이 **+617자**였다 — 터키 원정 1-0, 벨기에전 1-0,
#     이탈리아전 1-1, 경기장까지 한 덩어리. 🔴 변수 하나 = 사실 하나가 깨지면
#     방향·hardness 가 **무엇에 붙은 것인지** 알 수 없다.
#  🔴 버리지 않는다(쓸 사실이 들어 있다) — **그 사실을 표시한다.**
def test_fb8_묶음_변수를_표시한다():
    from app import classify
    assert hasattr(classify, "LUMP_CHARS"), (
        "🔴 `classify.LUMP_CHARS`(묶음으로 볼 길이)가 없다")
    assert hasattr(classify, "is_lump"), "🔴 `classify.is_lump` 가 없다"
    assert classify.is_lump("가" * (classify.LUMP_CHARS + 1))
    assert not classify.is_lump("짧은 사실 하나다")


def test_fb8_카드가_묶음을_적는다():
    """🔴 **돌려서** 본다 — F12(표시를 죽이기)가 문자열 검사를 빠져나갔다(D46)."""
    from app import analyze, classify
    long = classify.Classified(
        type="recent_pattern", team="France", direction="home",
        hardness="soft", text="가" * (classify.LUMP_CHARS + 50),
        source_url="https://a.com/1", why="규칙 사유")
    said = analyze.var_line(long)
    assert "묶음" in said, f"🔴 묶음을 표시하지 않았다: {said[-80:]!r}"
    short = classify.Classified(
        type="recent_pattern", team="France", direction="home",
        hardness="soft", text="짧은 사실 하나다",
        source_url="https://a.com/1", why="규칙 사유")
    assert "묶음" not in analyze.var_line(short), (
        "🔴 짧은 변수에도 묶음이라 적는다")


# ══════════════════════════════════════════════════════════════════
# ⑨ 카드가 **상충하는 두 사실**을 나란히 내고 사유를 안 적는다
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측: 블록 3 이 `France last5 ['L','L','W','W','D']` 를 적고, 변수 `R4`
#     가 *"France have an **unbeaten** start"* 를 적었다. **둘 다 카드에 있고
#     어느 쪽도 그 어긋남을 말하지 않는다.** (대회만 보면 무패, `last5` 는
#     친선 포함으로 보이지만 — 카드는 그 말을 안 한다.)
#  🔴 어느 쪽이 맞는지 **고르지 않는다**(정답은 경기 결과가 말한다) —
#     **어긋났다는 사실**을 적는다.
def test_fb9_무패_주장과_패배_기록이_어긋나면_적는다():
    from app import classify
    assert hasattr(classify, "clash_with_form"), (
        "🔴 `classify.clash_with_form(글, last5)` 가 없다 — 어긋남을 셀 곳이 없다")
    bad = classify.clash_with_form(
        "France have an unbeaten start to their campaign",
        ["L", "L", "W", "W", "D"])
    assert bad, "🔴 `unbeaten` 과 `L` 두 번이 어긋나는데 조용하다"
    assert "unbeaten" in bad or "무패" in bad, bad
    ok = classify.clash_with_form("France have an unbeaten start",
                                  ["W", "W", "D", "W", "D"])
    assert not ok, f"🔴 정말 무패인데 어긋났다고 한다: {ok}"
    # 🔴 `last5` 가 없으면 **아무 말도 하지 않는다**(지어내지 않는다)
    assert not classify.clash_with_form("unbeaten", [])


def test_fb9_카드가_그_어긋남을_적는다():
    """🔴 **배선**(#2) — 변수 줄이나 한계 블록이 그것을 낸다."""
    from app import analyze
    src = inspect.getsource(analyze)
    tree = ast.parse(src)
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "clash_with_form" in called, (
        "🔴 카드가 `clash_with_form` 을 **안 부른다** — 어긋남이 안 보인다")
    # 🔴 **`getattr` 로 더듬지 않는다** — 지난번 `Card.kickoff` 와 같은 함정:
    #    칸이 없으면 기본값이 늘 와서 **조용히 꺼진다**(실측 2026-10-05).
    #    ⚠️ `Classified` 에 `last5` 칸이 **없다**(재서 확인했다) → 폼은
    #       **인자로** 받아야 한다.
    import textwrap
    src2 = textwrap.dedent(inspect.getsource(analyze.var_line))
    assert "last5" not in src2 or "form" in src2.split("def var_line")[1][:200], (
        "🔴 `var_line` 이 변수에서 `last5` 를 **더듬는다** — 그 칸은 없다. "
        "폼을 인자로 받아라")


def test_fb9_폼을_인자로_받는다():
    """🔴 돌려서 본다 — 폼을 주면 어긋남이 **실제로** 줄에 실린다."""
    from app import analyze, classify
    c = classify.Classified(
        type="recent_pattern", team="France", direction="home",
        hardness="soft", text="France have an unbeaten start to the campaign",
        source_url="https://a.com/1", why="규칙 사유")
    said = analyze.var_line(c, form={"France": {"last5": ["L", "L", "W",
                                                          "W", "D"]}})
    assert "어긋난다" in said, f"🔴 폼을 줬는데 어긋남이 없다: {said[-90:]!r}"
    quiet = analyze.var_line(c, form={"France": {"last5": ["W", "W", "D"]}})
    assert "어긋난다" not in quiet, "🔴 무패인데 어긋났다고 한다"


def test_fb9_렌더러가_폼을_넘긴다():
    """🔴 **배선**(#2) — F14(폼 인자를 떼기)가 통과했다. AST 로 본다."""
    from app import analyze
    tree = ast.parse(inspect.getsource(analyze))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "var_line"]
    assert calls, "🔴 `var_line` 을 부르는 곳이 없다"
    for n in calls:
        kw = {k.arg for k in n.keywords}
        assert "form" in kw, (
            "🔴 렌더러가 `var_line` 에 **폼을 안 넘긴다** — 폼이 없으면 어긋남 "
            "검사가 조용히 꺼진다(`Card.kickoff` 와 같은 함정)")


# ══════════════════════════════════════════════════════════════════
# ⑩ GDELT 가 **한 실행에서 통째로 막혔다** — 간격 기억이 초기화된다
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측: 첫 질의는 `GDELT → 2건`, 그 뒤 `429 — 900초 쉰다`, 그 뒤
#     `724초 더 쉰다`. 🔴 `build_chain()` 이 **호출마다 새 `GdeltSearch()`** 를
#     만들고(findgame·analyze·resolve·scheduler 네 곳) 새 인스턴스는
#     `_last = 0` · `_rest_until = 0` 이라 **간격과 벌점이 통째로 잊힌다.**
#  🔴 호스트 하나에 대한 예의는 **인스턴스가 아니라 과정 전체**의 것이다.
def test_fb10_gdelt_간격이_인스턴스를_넘어_기억된다():
    import time

    from app import search
    a, b = search.GdeltSearch(), search.GdeltSearch()
    a._mark_called(time.time())
    assert b._wait_for() > 0, (
        "🔴 새 인스턴스가 **간격을 잊었다** — `build_chain()` 이 네 곳에서 "
        "따로 만든다(실측 2026-10-05: 한 실행에서 429 → 900초 봉쇄)")
    a._mark_rest(time.time() + 60)
    left = b._rest_left()
    assert left > 0, "🔴 벌점도 인스턴스를 넘어 기억돼야 한다"


def test_fb10_체인을_여러_번_만들어도_같은_상태다():
    from app import search
    one, two = search.build_chain(), search.build_chain()
    assert one.gdelt is not None and two.gdelt is not None
    import time
    one.gdelt._mark_rest(time.time() + 30)
    assert two.gdelt._rest_left() > 0, (
        "🔴 사슬을 다시 만들면 벌점이 사라진다 — 실측에서 그렇게 429 를 또 받았다")


# ══════════════════════════════════════════════════════════════════
# ⑫⑬ 비용 원장이 **한 경기를 하나로 모으지 못한다**
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측: 같은 실행의 26행이 `match` 를 세 가지로 적었다 —
#     `fotmob:5181794`(solar) · `team:000081|team:000021`(deepseek) ·
#     그리고 **`'|'`**(두 열쇠가 **둘 다 비었다**). 🔴 경기당 비용을 세려면
#     손으로 맞춰야 하고, `'|'` 행은 **어느 경기인지 알 수 없다.**
#  🔴 `match` 는 **경기 열쇠 하나**(`match_key`)로 적는다.
def test_fb12_단계3_4가_경기_열쇠를_적는다():
    from app import hypo, redteam
    for mod in (hypo, redteam):
        src = inspect.getsource(mod)
        assert 'match=f"{inp.home}|{inp.away}"' not in src, (
            f"🔴 `{mod.__name__}` 이 아직 팀 열쇠 두 개를 이어 붙인다 — "
            f"둘이 비면 `'|'` 가 되고 경기를 알 수 없다")
        assert "match_key" in src, (
            f"🔴 `{mod.__name__}` 이 `match_key` 를 안 쓴다 — solar 행과 같은 "
            f"열쇠여야 한 경기로 모인다")


def test_fb12_입력에_경기_열쇠_칸이_있다():
    from app import hypo
    assert "match_key" in hypo.HypoInput.__dataclass_fields__, (
        "🔴 `HypoInput` 에 `match_key` 칸이 없다 — `getattr` 로 더듬으면 늘 "
        "빈 값이 온다(`Card.kickoff` 와 같은 함정)")


def test_fb13_빈_열쇠로는_원장에_적지_않는다():
    """🔴 `'|'` 같은 **식별 불가 행**을 남기지 않는다(#3)."""
    from app import solar
    assert hasattr(solar, "match_or_unknown"), (
        "🔴 `solar.match_or_unknown(열쇠)` 가 없다 — 빈 열쇠를 그대로 적는다")
    assert solar.match_or_unknown("fotmob:1") == "fotmob:1"
    said = solar.match_or_unknown("")
    assert said and said != "|", said
    assert "열쇠" in said or "unknown" in said, (
        f"🔴 빈 열쇠를 **이름으로** 남기지 않았다: {said!r}")


def test_fb12_카드가_경기_열쇠를_채운다():
    """🔴 **배선**(#2) — `HypoInput(match_key=…)` 를 실제로 넘긴다.

    ⚠️ 칸만 만들고 안 채우면 `'|'` 행이 그대로 남는다(`Card.kickoff` 함정).
    """
    from app import analyze
    tree = ast.parse(inspect.getsource(analyze))
    made = [n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "HypoInput"]
    assert made, "🔴 `HypoInput` 을 만드는 곳이 없다"
    for n in made:
        kw = {k.arg for k in n.keywords}
        assert "match_key" in kw, (
            "🔴 `HypoInput(match_key=…)` 를 **안 넘긴다** — 원장이 단계 3·4 를 "
            "경기에 못 붙인다(실측: `match` 가 `'|'` 인 행)")


def test_fb13_원장_쓰기가_빈_열쇠를_이름으로_바꾼다(tmp_path):
    """🔴 **돌려서** 본다 — F18(정규화를 죽이기)이 통과했다.

    ⚠️ `match_or_unknown` 만 시험하면 그것을 **부르는 자리**가 비어도 초록이다.
    """
    from app import solar
    row = {"match": "|", "provider": "solar", "model": "m",
           "in": 1, "cache": 0, "out": 1, "usd": 0.0,
           "reasoning_effort": "low", "price_verified": False}
    path = solar.write_ledger(dict(row), root=tmp_path)
    import json
    said = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()
            if x.strip()]
    assert said and said[-1]["match"] != "|", (
        f"🔴 `'|'` 를 그대로 적었다 — 그 행은 어느 경기인지 알 수 없다: "
        f"{said[-1]['match']!r}")
    assert said[-1]["match"] == solar.MATCH_UNKNOWN, said[-1]["match"]


# ══════════════════════════════════════════════════════════════════
# ⑭ 깔때기가 **한 쪽 에이전트 전멸**을 숨긴다
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측: 프랑스 에이전트가 터졌는데 `agent_vars:20`(벨기에 것뿐)만 적히고
#     탈락 사유 목록에 그 말이 없었다. 🔴 세포 장부에는 있었지만 **깔때기만
#     읽는 사람은 두 팀이 다 돌았다고 읽는다.**
def test_fb14_에이전트가_터지면_깔때기에_남는다():
    from app import funnel as _f
    from app.reasons import Reason
    assert hasattr(Reason, "AGENT_CRASHED"), (
        "🔴 `agent_crashed` 사유가 없다 — 터진 것과 0개를 낸 것은 고칠 곳이 다르다")
    fun = _f.Funnel()
    fun.drop(Reason.AGENT_CRASHED, "agent_vars")
    assert "agent_crashed" in fun.drop_line(), fun.drop_line()


def test_fb14_카드가_그_사유를_붙인다():
    from app import analyze
    tree = ast.parse(inspect.getsource(analyze))
    hit = [n for n in ast.walk(tree)
           if isinstance(n, ast.Attribute) and n.attr == "AGENT_CRASHED"]
    assert hit, (
        "🔴 카드가 `AGENT_CRASHED` 를 **안 쓴다** — 전멸이 깔때기에 안 남는다")


# ══════════════════════════════════════════════════════════════════
# ⑮ 추천 세 줄이 **전부 같은 갈래**였다
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측: `양팀득점 예` 0.87 · `오버 1.5` 0.93 · `오버 2.5` 0.93 — 셋이 다
#     득점 많음 쪽이다. 3줄 상한은 통과하지만 **하나가 틀리면 셋 다 틀린다.**
#  🔴 규칙(사용자 것)은 **바꾸지 않는다** — 그 사실을 적는다.
def test_fb15_같은_갈래_추천을_카드가_적는다():
    from app import survive
    assert hasattr(survive, "same_branch_note"), (
        "🔴 `survive.same_branch_note(줄들)` 이 없다 — 분산 없음을 셀 곳이 없다")
    rows = [{"market": "오버 1.5", "verdict": "small", "dead": []},
            {"market": "오버 2.5", "verdict": "small", "dead": []},
            {"market": "양팀득점 예", "verdict": "small", "dead": []}]
    said = survive.same_branch_note(rows)
    assert said and "같은" in said, said
    mixed = [{"market": "오버 1.5", "verdict": "small", "dead": ["A"]},
             {"market": "언더 3.5", "verdict": "small", "dead": ["B"]}]
    assert not survive.same_branch_note(mixed), (
        "🔴 죽는 갈래가 다른데 같은 갈래라고 한다")


def test_fb15_카드가_같은_갈래_줄을_쓴다():
    """🔴 **배선**(#2) — 안 이은 코드는 없는 코드보다 나쁘다."""
    from app import survive
    tree = ast.parse(inspect.getsource(survive))
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "same_branch_note" in called, (
        "🔴 `same_branch_note` 를 **부르는 곳이 없다** — 카드에 안 나온다")


# ══════════════════════════════════════════════════════════════════
# ⑯ `learn_names` 로그가 **두 경우를 한 글로** 적는다
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실측: `안 배운다 — 짝이 하나로 안 정해진다 (물은 것 'France'/'Belgium' ·
#     아는 열쇠 'team:000081'/'team:000021')`. 🔴 재서 확인했다 — 그것은
#     **결함이 아니다**: 둘 다 이미 아는 이름이라 **배울 것이 없다.**
#  🔴 그런데 *"둘 다 안다"* 와 *"둘 다 모른다"* 가 **같은 글**로 찍힌다 —
#     앞은 정상이고 뒤는 고칠 것이 있다(#3: 구별해 적는다).
def test_fb16_배울_것이_없는_것과_못_가리는_것을_가른다():
    from app import learn_names
    assert hasattr(learn_names, "why_not_learned"), (
        "🔴 `learn_names.why_not_learned(두 열쇠)` 가 없다 — 두 경우가 같은 "
        "글로 찍힌다")
    both = learn_names.why_not_learned("team:000081", "team:000021")
    assert "배울 것이 없다" in both or "둘 다 안다" in both, both
    none = learn_names.why_not_learned("", "")
    assert "못" in none or "모른다" in none, none
    assert both != none, "🔴 두 경우가 같은 글이다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **계약은 이 기계의 원장을 읽지 않는다** — 실사고 2026-10-05
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 봇을 하루에 여러 번 돌려 하루 상한에 닿자 LLM 계약 **10건이 한꺼번에**
#     빨개졌다: `day_cap_stop: 오늘 $3.0074 / 상한 $3.00`. 그것은 **봇 결함이
#     아니라 기계 상태**다. 🔴 `_unplug_env` 가 `.env` 를 뗀 것과 같은 이유로
#     원장도 뗀다.
def test_원장이_기계에서_떨어져_있다():
    from app import solar
    said = str(solar._ledger_path())
    assert "ledger-unplug-" in said, (
        f"🔴 원장 경로가 이 기계의 저장소를 가리킨다({said}) — 계약이 오늘 얼마를 "
        f"썼는지에 따라 색이 바뀐다(`tests/conftest.py` 의 `_unplug_ledger`)")
    assert "Desktop/analystbot/ledger" not in said, said


# ══════════════════════════════════════════════════════════════════
# 🔴 **같은 경기를 두 번 세지 않는다** — 실측 2026-10-05 (인도네시아–태국)
# ══════════════════════════════════════════════════════════════════
#
#  ⚠️ 실사고: `[findgame] 2경기를 슬레이트에 적었다 — id [117, 117]`.
#     같은 경기를 두 URL(`1b-vs-indonesia`·`thailand-vs-indonesia`)로 찾아
#     둘 다 올렸다. DB 는 upsert 라 하나지만 **"2경기"가 거짓**이다.
#  🔴 수를 거짓으로 적으면 깔때기도 거짓이 된다(#3).
def test_슬레이트가_같은_경기를_두_번_세지_않는다():
    from app import findgame
    import inspect
    src = inspect.getsource(findgame)
    at = src.find("경기를 슬레이트에 적었다")
    assert at > 0, "🔴 그 줄을 못 찾았다 — 이 계약을 고쳐라"
    # 🔴 **중복을 지운 수**를 적어야 한다
    seg = src[max(0, at - 700):at]
    assert "dict.fromkeys" in seg or "set(" in seg or "중복" in seg, (
        "🔴 `ids` 를 그대로 센다 — 같은 경기를 두 URL 로 찾으면 "
        "`id [117, 117]` 처럼 두 번 센다")
