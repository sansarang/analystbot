"""자료14 분기점 해결의 계약 — **질문을 맞는 해결사에게 보낸다.**

🔴 실측 2026-09-07 (운영 Redis, deepsearch 기록 6건 전수):
   판정이 `추가확인` 에 적은 것이 6건 모두 **미확인**으로 돌아왔다.
     "Wrobleski 오늘 예정 투구수 한도" · "허드슨 뒤 이닝 소화 계획" ·
     "아리게티 투구 계획" · "금일 선발·라인업"
   전부 기록으로 답할 질문을 뉴스 검색기(퍼플렉시티)에 보낸 탓이었다.
   같은 질문을 우리 DB 에 물으니 즉시 답이 나왔다 —
     본인 2건 · 소속팀 22건(5이닝 이상 91%) · **리그 동류 232건(52%)**
"""

import pytest

from app.config import get_settings
from app.engine.branch_resolve import (LIVE, NEWS, RECORD, UNKNOWN, classify,
                                       payload)


# ═══════════════ ① 분류 — 여기서 틀리면 답이 있어도 못 찾는다

@pytest.mark.parametrize("q", [
    "Wrobleski 가 5이닝을 넘기는가",
    "Wrobleski의 오늘 예정 투구수 한도",          # 실측 미확인 사례
    "허드슨 뒤 이닝 소화 계획",                    # 실측 미확인 사례
    "아리게티 투구 계획",                          # 실측 미확인 사례
    "홈 불펜의 연투 누적이 후반을 감당하는가",
    "상위 타순이 한 바퀴 더 도는가",
])  # noqa: PT006
def test_기록으로_답할_질문은_기록형이다(q):
    """🔴 실측 미확인 4건 중 3건이 여기 들어온다."""
    assert classify(q) == RECORD, f"{q!r} 를 뉴스로 보내면 또 미확인이다"


@pytest.mark.parametrize("q", [
    "Ohtani 의 IL 등재 여부",
    "선발 투수의 부상 이탈 여부",
    "우천 취소 가능성",
])
def test_기사로만_알_수_있는_것은_뉴스형이다(q):
    assert classify(q) == NEWS


@pytest.mark.parametrize("q", [
    "오늘 라인업 발표 내용",
    "Wrobleski의 오늘 투구수·이닝 제한 여부(구단 발표)",   # 실측 2026-09-07
    "홈 불펜 피로 4명의 오늘 가용 여부",                    # 실측 2026-09-07
])
def test_구단_발표를_묻는_것은_실시간형이다(q):
    """🔴 실시간형이 기록형보다 **먼저**여야 한다. 실측: opus 가 자료14 로
    리그 표본을 받고도 "제한 여부(구단 발표)" 를 다시 물었다. 기록형으로
    잡으면 같은 답이 또 붙어 중복이 되고, 정작 물은 오늘의 사실은 안 간다."""
    assert classify(q) == LIVE


def test_빈_질문과_못_가리는_질문은_미분류다():
    assert classify("") == UNKNOWN
    assert classify(None) == UNKNOWN
    assert classify("이 경기 결과가 어떻게 되는가") == UNKNOWN


def test_기록형이_뉴스형보다_먼저_걸린다():
    """🔴 '오늘 예정 투구수 한도' 는 두 유형이 겹친다. 뉴스로 가면 미확인이고
    기록으로 가면 답이 있다 — 순서가 곧 결과다."""
    assert classify("부상 복귀 후 투구수 관리 계획") == RECORD


# ═══════════════ ② 해결사 — 세 갈래를 나란히, 곱하지 않는다

class _Pool:
    def __init__(self, own=(), team=None, peers=None, exc=None):
        self.own, self.team, self.peers, self.exc = list(own), team, peers, exc
        self.calls = []

    async def fetch(self, sql, *a):
        self.calls.append(("fetch", sql, a))
        if self.exc:
            raise self.exc
        return self.own

    async def fetchrow(self, sql, *a):
        self.calls.append(("row", sql, a))
        if self.exc:
            raise self.exc
        return self.peers if "prev_starts" in sql else self.team


def _own(d, starter, ip, tbf=24, r=2):
    return {"d": d, "is_starter": starter, "innings": ip, "batters": tbf, "r": r}


@pytest.mark.asyncio
async def test_본인_표본이_얇아도_리그_동류가_답한다():
    """🔴 이 모듈의 존재 이유. 본인 2건인데 리그는 232건을 준다."""
    from app.engine.branch_resolve import innings_outlook

    s = get_settings()
    pool = _Pool(own=[_own("2026-08-15", True, 6.0), _own("2026-09-02", False, 2.0)],
                 team={"n": 22, "ip": 5.64, "tbf": 23.4, "deep": 20},
                 peers={"n": 232, "ip": 4.12, "deep": 121})
    out = await innings_outlook(pool, "mlb", "Justin Wrobleski",
                                "Los Angeles Dodgers", "2026-09-07")
    assert out["본인"]["선발수"] == 1
    assert out["소속팀"]["표본"] == 22
    assert out["소속팀"]["5이닝이상"] == "20/22 (91%)"
    assert out["같은처지"]["표본"] == 232
    assert out["같은처지"]["5이닝이상"] == "121/232 (52%)"
    assert out["같은처지"]["조건"].endswith("1건인 투수")


@pytest.mark.asyncio
async def test_세_갈래를_하나의_수로_합치지_않는다():
    """⚠️ 자료13 이 무너진 자리 — 얇은 비율 셋을 곱해 sd 5.25 가 나왔다."""
    from app.engine.branch_resolve import innings_outlook

    out = await innings_outlook(
        _Pool(own=[_own("2026-08-15", True, 6.0)],
              team={"n": 22, "ip": 5.64, "tbf": 23.4, "deep": 20},
              peers={"n": 232, "ip": 4.12, "deep": 121}),
        "mlb", "P", "T", "2026-09-07")
    # 합성 확률·점수 같은 단일 수가 있으면 안 된다.
    for k in out:
        assert k in ("질문", "본인", "소속팀", "같은처지")


@pytest.mark.asyncio
async def test_표본이_얇은_갈래는_싣지_않는다():
    """얇은 답으로 얇은 표본을 메우면 없느니만 못하다."""
    from app.engine.branch_resolve import innings_outlook

    s = get_settings()
    thin = s.branch_min_n - 1
    out = await innings_outlook(
        _Pool(own=[_own("2026-08-15", True, 6.0)],
              team={"n": thin, "ip": 5.0, "tbf": 20.0, "deep": 3},
              peers={"n": thin, "ip": 4.0, "deep": 2}),
        "mlb", "P", "T", "2026-09-07")
    assert "소속팀" not in out and "같은처지" not in out


@pytest.mark.asyncio
async def test_조회가_실패해도_판정을_막지_않는다():
    from app.engine.branch_resolve import innings_outlook

    assert await innings_outlook(_Pool(exc=RuntimeError("db")), "mlb",
                                 "P", "T", "2026-09-07") == {}


@pytest.mark.asyncio
async def test_관측_창과_컷오프가_질의에_들어간다():
    """⚠️ 컷오프가 없으면 경기 이후 등판이 섞인다."""
    from app.engine.branch_resolve import innings_outlook

    pool = _Pool(own=[_own("2026-08-15", True, 6.0)],
                 team={"n": 22, "ip": 5.6, "tbf": 23.0, "deep": 20},
                 peers={"n": 232, "ip": 4.1, "deep": 121})
    await innings_outlook(pool, "mlb", "P", "T", "2026-09-07")
    sqls = " ".join(c[1] for c in pool.calls)
    assert "g.starts_at < $" in sqls, "컷오프가 없다"
    assert "make_interval(days =>" in sqls, "팀 관측 창이 없다"


# ═══════════════ ③ 답이 없으면 없다고 적는다

@pytest.mark.asyncio
async def test_뉴스형은_기사_조사_소관이라고_밝힌다():
    from app.engine.branch_resolve import resolve

    r = await resolve(None, {"sport": "mlb"}, "Ohtani 의 IL 등재 여부")
    assert r["유형"] == NEWS and "답" not in r and "deepsearch" in r["사유"]


@pytest.mark.asyncio
async def test_실시간형은_알_수_없다로_끝내지_않는다():
    """🔴 오늘의 사실은 이미 우리 손에 있다 — IL 명단·라인업 공시.
    실측 2026-09-07: 다저스 선발 자원 5명 이상이 IL 인데 그 사실이
    분기점의 답으로 가지 않았다."""
    from app.engine.branch_resolve import resolve

    jg = {"sport": "mlb", "game_id": 3725,
          "home": "Los Angeles Dodgers", "away": "Washington Nationals",
          "research": {"absence_basis": "IL 명단", "absences": [
              "Los Angeles Dodgers의 Ben Casparius(선발) Injured 60-Day로 결장",
              "Los Angeles Dodgers의 Eric Lauer(선발) Injured 15-Day로 결장",
              "Los Angeles Dodgers의 Andy Pages(주전 타자) Injured 10-Day로 결장",
              "Washington Nationals의 Josiah Gray(선발) Injured 60-Day로 결장"]}}
    r = await resolve(None, jg, "오늘 투구수 제한 여부(구단 발표)")
    assert r["유형"] == LIVE
    답 = r["답"]
    assert 답["결장"]["home"]["총"] == 3
    assert 답["결장"]["home"]["투수자원"] == 2, "IL 상의 선발 자원을 세지 못했다"
    assert 답["결장_출처"] == "IL 명단"
    assert 답["미확인"], "모르는 것을 밝히지 않으면 '없음'을 '정상'으로 읽는다"


@pytest.mark.asyncio
async def test_같은_답은_두_번_싣지_않는다():
    """실측: 분기점과 추가확인이 둘 다 같은 투수를 가리켜 블록이 두 번 실렸다."""
    from app.engine.branch_resolve import attach

    jg = {"sport": "mlb", "game_id": 1,
          "home": "H", "away": "A", "research": {"absences": []},
          "matchup": {"전개": {"분기점": "오늘 가용 여부"},
                      "추가확인": ["오늘 출전 여부"]}}
    await attach(None, jg)
    items = jg["branch"]["항목"]
    assert len(items) == 1, f"중복이 걸러지지 않았다: {len(items)}건"


@pytest.mark.asyncio
async def test_분기점이_없으면_빈_dict_이고_False():
    from app.engine.branch_resolve import attach

    jg = {"sport": "mlb", "matchup": {}}
    assert await attach(None, jg) is False
    assert jg["branch"] == {}


@pytest.mark.asyncio
async def test_분기점이_추가확인보다_먼저다():
    """분기점은 검색 가능한 한 문장으로 좁혀져 있다 — 그게 우선이다."""
    from app.engine.branch_resolve import attach

    jg = {"sport": "mlb", "game_id": 1,
          "matchup": {"전개": {"분기점": "Wrobleski 가 5이닝을 넘기는가"},
                      "추가확인": ["Ohtani IL 여부"]}}
    await attach(None, jg)
    items = jg["branch"]["항목"]
    assert items[0]["질문"].startswith("Wrobleski")
    assert items[0]["유형"] == RECORD
    assert items[1]["유형"] == NEWS


# ═══════════════ ④ 배선 — 붙지 않은 자료는 없는 것과 같다

def test_payload_는_읽기만_한다():
    assert payload({}) == {}
    assert payload({"branch": {"항목": [1]}}) == {"항목": [1]}


def test_프롬프트에_자료14_자리와_설명이_있다():
    from app.engine.prompts import MATCHUP

    assert "{{BRANCH_JSON}}" in MATCHUP
    assert "14. **분기점 조사**" in MATCHUP
    assert "같은처지" in MATCHUP
    assert "곱하지 마라" in MATCHUP


def test_프롬프트가_전개를_p_home_보다_먼저_시킨다():
    """🔴 LLM 은 왼쪽부터 생성한다 — 순서가 곧 조건화다."""
    from app.engine.prompts import MATCHUP

    i_flow = MATCHUP.index('"전개"')
    i_p = MATCHUP.index('"p_home"')
    assert i_flow < i_p, "확률을 먼저 찍으면 전개는 사후 서술이 된다"
    assert "검색 가능한 한 문장" in MATCHUP


def test_파이프라인이_판정_앞에서_분기점을_푼다():
    src = open("app/pipeline.py", encoding="utf-8").read()
    assert "from app.engine.branch_resolve import attach as _branch" in src
    b = src.index("branch_resolve import attach")
    j = src.index("if await judge_matchup(jg, redis, date, allow_final=allow_final)")
    assert b < j, "분기점 조사는 판정보다 앞이어야 한다"


def test_L1_이_자료14_숫자를_대조한다():
    """🔴 자료12 가 감시 없이 배포됐던 실수를 되풀이하지 않는다."""
    from app.engine.fact_audit import UNIT_PATTERNS

    keys = {k for _, _, ks in UNIT_PATTERNS for k in ks}
    for need in ("상대타자", "평균상대타자", "batters", "평균이닝"):
        assert need in keys, f"{need} 가 L1 대조 목록에 없다"


@pytest.mark.asyncio
async def test_오늘의_사실은_분기점과_무관하게_늘_실린다():
    """🔴 실측 2026-09-07: opus 가 두 회차 연속 "구단 발표"·"가용 인원" 을
    물었는데 그 답(IL 명단·라인업 공시)은 이미 우리 손에 있었다.
    분류가 틀려도 전달되도록 분기점 해결과 분리한다."""
    from app.engine.branch_resolve import attach

    jg = {"sport": "mlb", "game_id": 1, "home": "LAD", "away": "WSH",
          "research": {"absence_basis": "IL 명단", "absences": [
              "LAD의 A(선발) Injured 60-Day로 결장",
              "LAD의 B(선발) Injured 15-Day로 결장",
              "LAD의 C(주전 타자) Injured 10-Day로 결장"]},
          "matchup": {"전개": {"분기점": "A 가 5이닝을 넘기는가"}}}
    await attach(None, jg)
    사실 = jg["branch"]["오늘의사실"]
    assert 사실["결장"]["home"]["투수자원"] == 2
    assert 사실["미확인"]


@pytest.mark.asyncio
async def test_유형이_다르면_답이_겹쳐도_남긴다():
    """기록형(대리값)과 실시간형(오늘의 사실)은 다른 질문에 답한다."""
    from app.engine.branch_resolve import attach

    jg = {"sport": "mlb", "game_id": 1, "home": "H", "away": "A",
          "research": {"absences": []},
          "matchup": {"전개": {"분기점": "오늘 가용 여부"},
                      "추가확인": ["최근 폼이 어떤가"]}}
    await attach(None, jg)
    kinds = [x["유형"] for x in jg["branch"]["항목"]]
    assert len(set(kinds)) == 2, f"유형이 다른데 합쳐졌다: {kinds}"


def test_프롬프트가_오늘의사실을_설명한다():
    from app.engine.prompts import MATCHUP

    assert "오늘의사실" in MATCHUP
    assert "투수자원" in MATCHUP and "로테이션이 무너져" in MATCHUP


# ═══════════════ ⑤ 전개 정합 — 틀린 값을 카드로 내보내지 않는다

@pytest.mark.parametrize("sport,h,a,p,bad", [
    ("mlb", 3, 3, 0.53, True),    # 실측 2026-09-07 NYY@SD
    ("kbo", 3, 3, 0.50, False),   # KBO·NPB 는 무승부가 있다
    ("npb", 2, 2, 0.50, False),
    ("mlb", 2, 5, 0.60, True),    # 점수와 확률이 반대
    ("mlb", 5, 3, 0.56, False),   # 정상
    ("mlb", 5, 3, 0.50, False),   # 0.50 은 어느 쪽도 아니다
])
def test_예상점수가_판정과_어긋나면_무효다(sport, h, a, p, bad):
    """🔴 실측: `승자 = San Diego Padres` 인데 `예상점수 3-3` 이었다.
    MLB 는 연장으로 승부를 가르므로 존재할 수 없는 스코어다."""
    from app.engine.matchup import check_flow

    why = check_flow({"전개": {"예상점수": {"홈": h, "원정": a}}, "p_home": p},
                     sport)
    assert bool(why) is bad, why


def test_예상점수가_없으면_검사할_것도_없다():
    from app.engine.matchup import check_flow

    assert check_flow({"전개": {}}, "mlb") == []
    assert check_flow({}, "mlb") == []


def test_어긋난_예상점수는_고쳐_쓰지_않고_지운다():
    """⚠️ 점수를 우리가 지어내면 그건 판정이 아니라 우리 추정이다."""
    from app.engine.matchup import apply_matchup

    jg = {"sport": "mlb", "game_id": 1}
    apply_matchup(jg, {"p_home": 0.53, "확신도": "중", "근거": ["x"],
                       "전개": {"분기점": "q", "예상점수": {"홈": 3, "원정": 3}}})
    flow = jg["matchup"]["전개"]
    assert "예상점수" not in flow, "존재할 수 없는 스코어가 살아남았다"
    assert "무승부" in flow["예상점수_생략"], "왜 뺐는지 남기지 않았다"
    assert flow["분기점"] == "q", "나머지 전개까지 지웠다"


def test_정상_예상점수는_그대로_실린다():
    """🔴 반대 위험 — 검사가 멀쩡한 값을 버리면 안 된다."""
    from app.engine.matchup import apply_matchup

    jg = {"sport": "mlb", "game_id": 1}
    apply_matchup(jg, {"p_home": 0.56, "확신도": "중", "근거": ["x"],
                       "전개": {"예상점수": {"홈": 5, "원정": 3}}})
    assert jg["matchup"]["전개"]["예상점수"] == {"홈": 5, "원정": 3}


# ═══════════════ ⑥ 변수의 발생 확률 — 자료14 가 답을 준 것만

def test_발생확률은_선택_칸이라_기존_형식도_통과한다():
    """필수로 만들면 답 없는 변수가 통째로 형식 위반이 되어 예산에서 빠진다."""
    from app.engine.variable_parse import parse_variable

    old = ("선발 조기 강판 — 발생 시 원정 방향 약 8%p · "
           "현재 p에 3%p 기반영 · 근거 자료10")
    r = parse_variable(old)
    assert r and r["n"] == 8.0 and r["m"] == 3.0 and r["q"] is None


def test_발생확률이_있으면_숫자로_잡힌다():
    """🔴 실측 NYY@SD: 자료14 의 '5이닝 이상 35/51=69%' 를 인용하고도
    발생 확률(31%)을 적을 칸이 없어 근거 문자열에 묻혔다."""
    from app.engine.variable_parse import parse_variable

    new = ("선발 조기 강판 — 발생 시 원정 방향 약 8%p · 발생 확률 31% · "
           "현재 p에 3%p 기반영 · 근거 자료14 같은처지 35/51")
    r = parse_variable(new)
    assert r and r["q"] == 31.0 and r["m"] == 3.0
    assert "자료14" in r["source"]


def test_프롬프트가_발생확률의_출처를_자료14로_못박는다():
    from app.engine.prompts import MATCHUP

    assert "발생 확률 X%" in MATCHUP
    assert "자료14 가 그 리스크의 빈도를 알려줬을 때만" in MATCHUP
    assert "확률을 지어내지 마라" in MATCHUP


# ═══════════════ ⑦ 변수도 질문이다 — 타선 회귀 해결사

class _OffPool:
    def __init__(self, peer_n=60, next_runs=4.1, league=4.4):
        self.peer_n, self.next_runs, self.league = peer_n, next_runs, league
        self.calls = []

    async def fetchrow(self, sql, *a):
        self.calls.append((sql, a))
        if "n3 = 3" in sql:
            return {"n": self.peer_n, "next_runs": self.next_runs}
        return {"rpg": self.league}


@pytest.mark.asyncio
async def test_눌린_타선의_다음_경기를_리그_표본이_답한다():
    """🔴 실측 2026-09-07 NYY@SD 변수2 — "홈 타선 배율 0.46이 일시적 침체일
    가능성 … **근거 없음 — 보수 반영**". 답이 DB 에 있는데 아무도 묻지 않았다."""
    from app.engine.branch_resolve import offense_outlook

    out = await offense_outlook(_OffPool(), "mlb", "SD", "2026-09-06", 2.33)
    assert out["표본"] == 60
    assert out["다음경기_평균득점"] == 4.1
    assert out["리그_경기당득점"] == 4.4, "리그 평균을 나란히 줘야 읽을 수 있다"
    assert "2.33" in out["조건"]


@pytest.mark.asyncio
async def test_타선_회귀도_표본이_얇으면_싣지_않는다():
    from app.engine.branch_resolve import offense_outlook

    s = get_settings()
    out = await offense_outlook(_OffPool(peer_n=s.branch_min_n - 1), "mlb",
                                "SD", "2026-09-06", 2.33)
    assert out == {}


@pytest.mark.asyncio
async def test_회귀_폭을_우리가_계산해_주지_않는다():
    """⚠️ 두 수를 나란히 놓을 뿐 하나로 합치지 않는다 — 자료13 의 교훈."""
    from app.engine.branch_resolve import offense_outlook

    out = await offense_outlook(_OffPool(), "mlb", "SD", "2026-09-06", 2.33)
    assert set(out) == {"질문", "조건", "표본", "다음경기_평균득점", "리그_경기당득점"}


@pytest.mark.asyncio
async def test_변수의_리스크가_질문으로_들어간다():
    """🔴 `attach` 가 분기점·추가확인만 보던 것을 고쳤다."""
    from app.engine.branch_resolve import attach

    jg = {"sport": "mlb", "game_id": 1, "home": "H", "away": "A",
          "research": {"absences": [],
                       "home_usage": {"runs_per_game_l3": 2.33}},
          "matchup": {"전개": {"분기점": "오늘 가용 여부"},
                      "변수": ["홈 타선의 최근 배율이 일시적 침체일 가능성 — "
                               "발생 시 홈 방향 약 4%p · 현재 p에 1%p 기반영 · "
                               "근거 자료1"]}}
    await attach(_OffPool(), jg)
    qs = [x["질문"] for x in jg["branch"]["항목"]]
    assert any("침체" in q for q in qs), f"변수가 질문에 안 들어갔다: {qs}"


@pytest.mark.asyncio
async def test_변수의_퍼센트는_질문으로_보내지_않는다():
    """%p 는 판정의 몫이지 조사할 대상이 아니다 — 리스크 서술만 떼어 보낸다."""
    from app.engine.branch_resolve import attach

    jg = {"sport": "mlb", "game_id": 1, "home": "H", "away": "A",
          "research": {"absences": [], "home_usage": {"runs_per_game_l3": 2.3}},
          "matchup": {"변수": ["타선 침체 지속 — 발생 시 홈 방향 약 4%p · "
                               "현재 p에 1%p 기반영 · 근거 자료1"]}}
    await attach(_OffPool(), jg)
    q = jg["branch"]["항목"][0]["질문"]
    assert "%p" not in q and "기반영" not in q, f"수치가 질문에 섞였다: {q}"
    assert q == "타선 침체 지속"


# ═══════════════ 불펜·연전 해결사 (2026-09-07)
#
# 🔴 실측: 기록형 변수 501건의 내역 — 불펜 274건(42.9%) · 연전 68건(10.7%).
#    둘 다 해결사가 없어 `사유: 대상 선발을 특정하지 못했다` 로 끝났고,
#    "연전 4일차 away 피로" 는 분류가 기록형인데 답이 **빈 dict** 로 나갔다.

def test_연전_일차_세기():
    """오늘 포함, 하루라도 비면 끊긴다."""
    from datetime import date

    from app.engine.branch_resolve import consecutive_days

    t = date(2026, 9, 7)
    assert consecutive_days([date(2026, 9, 6), date(2026, 9, 5),
                             date(2026, 9, 4)], t) == 4
    assert consecutive_days([date(2026, 9, 6), date(2026, 9, 4)], t) == 2
    assert consecutive_days([date(2026, 9, 5)], t) == 1     # 어제가 비었다
    assert consecutive_days([], t) == 1
    # 더블헤더 — 같은 날 두 경기는 하루로 센다
    assert consecutive_days([date(2026, 9, 6), date(2026, 9, 6)], t) == 2


def test_불펜_질문이_선발_이름_없이도_풀린다():
    """🔴 이 라우팅이 없어서 기록형의 절반(불펜 42.9%)이 답 없이 끝났다.

    ⚠️ 소스 문자열 위치로 재지 않는다 — 주석에 같은 문구를 쓰는 순간
       테스트가 깨지고, 그때 고쳐지는 것은 코드가 아니라 주석이다.
       **실제로 호출해서** 답이 나오는지 본다.
    """
    import asyncio
    from datetime import UTC, datetime

    from app.engine.branch_resolve import resolve

    jg = {"sport": "mlb", "home": "Cincinnati Reds", "away": "Milwaukee Brewers",
          "starts_at": datetime(2026, 9, 7, 23, 10, tzinfo=UTC)}
    rec = asyncio.run(resolve(_FakePool(), jg, "홈 불펜이 조기 가동되는가"))
    assert rec["유형"] == "기록형"
    assert rec.get("사유") != "질문에서 대상 선발을 특정하지 못했다"
    assert "home" in (rec.get("답") or {}), rec
    assert "away" not in (rec.get("답") or {}), "한쪽만 물었는데 양쪽을 냈다"
    assert rec["답"]["home"]["같은처지"]["표본"] == 40


def test_연전_질문이_선발_이름_없이도_풀린다():
    import asyncio
    from datetime import UTC, datetime

    from app.engine.branch_resolve import resolve

    jg = {"sport": "mlb", "home": "Cincinnati Reds", "away": "Milwaukee Brewers",
          "starts_at": datetime(2026, 9, 7, 23, 10, tzinfo=UTC)}
    rec = asyncio.run(resolve(_FakePool(), jg, "연전 4일차 원정 피로"))
    assert rec["유형"] == "기록형"
    assert "away" in (rec.get("답") or {}), rec
    assert rec["답"]["away"]["연전일차"] == 3


def test_해결사가_답을_못_내면_사유를_남긴다():
    """모듈 규약 — 빈 칸을 만들지 않는다."""
    import inspect

    from app.engine import branch_resolve as br

    for fn in (br.bullpen_outlook, br.series_outlook):
        src = inspect.getsource(fn)
        assert "return {}" in src, f"{fn.__name__} 이 실패 경로를 안 그린다"
    # 라우팅은 빈 답을 그대로 두지 않는다
    src = inspect.getsource(br.resolve)
    assert '표본이 하한에 못 미친다' in src


def test_연전이_아니면_그렇게_적는다():
    """⚠️ "연전이 아니다"도 답이다. 조용히 빠지면 판정이 계속 물어본다."""
    import asyncio
    import inspect

    from app.engine.branch_resolve import series_outlook

    src = inspect.getsource(series_outlook)
    assert "연전이 아니다" in src
    assert asyncio.run(series_outlook(None, "mlb", "T", None)) == {}


def test_해결사가_판단하지_않는다():
    """⚠️ '지쳤다/괜찮다'는 판정의 일이다. 우리는 숫자를 나란히 놓을 뿐이다.

    ⚠️ **코드 줄만 본다.** 주석까지 잡으면 그 다짐을 주석에 적을 수 없게 된다
       (`test_shadow_panel.test_no_sdk_dependency_added` 와 같은 이유).
    """
    import ast
    import inspect

    from app.engine.branch_resolve import bullpen_outlook, series_outlook

    for fn in (bullpen_outlook, series_outlook):
        tree = ast.parse(inspect.getsource(fn).lstrip())
        lits = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        body = " ".join(lits[1:])            # [0] 은 독스트링
        for verdict in ("지쳤", "위험", "불리", "유리", "약하", "강하"):
            assert verdict not in body, f"{fn.__name__} 이 판단어를 만든다: {verdict}"


class _FakePool:
    """불펜·연전 해결사가 쓰는 두 질의만 흉내낸다."""

    async def fetch(self, sql, *a):
        from datetime import date
        if "NOT a.is_starter" in sql:                       # 최근 3경기 불펜 소모
            return [{"d": date(2026, 9, 6), "arms": 4, "ip": 3.0},
                    {"d": date(2026, 9, 5), "arms": 3, "ip": 2.0},
                    {"d": date(2026, 9, 4), "arms": 5, "ip": 4.0}]
        if "ORDER BY g.starts_at DESC LIMIT 12" in sql:      # 연전 날짜
            return [{"d": date(2026, 9, 6)}, {"d": date(2026, 9, 5)}]
        return []

    async def fetchrow(self, sql, *a):
        if "next_r" in sql:
            return {"n": 40, "next_r": 3.1, "next_ip": 3.4}
        if "avg(allowed)" in sql:
            return {"n": 55, "runs": 4.2, "allowed": 4.6}
        return None


def test_불펜_연전이_기록형으로_분류된다():
    """🔴 종전 `불펜\\s*소모` 는 "홈 불펜이 조기 가동되는가" 를 놓쳤고,
    `연전` 은 패턴에 아예 없어 `연투`·`피로` 에 우연히 걸리고 있었다.

    ⚠️ 반대 위험을 실변수 638건으로 측정했다 (2026-09-07):
       기록형 501 → 559 (+58) · 미분류 123 → 65 (−58)
       **뉴스형 → 기록형 탈취 0건.** 넓혀도 뉴스 조사가 줄지 않는다.
    """
    from app.engine.branch_resolve import classify

    for q in ("홈 불펜이 조기 가동되는가", "원정 불펜 과부하",
              "연전 4일차 홈 vs 원정 전환", "구원 소모가 누적됐는가"):
        assert classify(q) == "기록형", q


def test_실시간이_기록형보다_먼저다():
    """⚠️ "필승조 **가용 여부**" 는 오늘의 사실이지 기록이 아니다.
    넓힌 기록형이 이 우선순위를 깨지 않았음을 잠근다."""
    from app.engine.branch_resolve import classify

    assert classify("필승조 가용 여부는") == "실시간형"
    assert classify("불펜 구단 발표 여부") == "실시간형"


def test_뉴스형은_그대로_뉴스로_간다():
    """넓힌 쪽이 뉴스 조사를 빼앗지 않는다 — 실측 0건을 계약으로 잠근다."""
    from app.engine.branch_resolve import classify

    for q in ("주전 포수 부상 이탈 여부", "트레이드 마감 영입 효과",
              "우천 취소 가능성", "감독 징계 여파"):
        assert classify(q) == "뉴스형", q


def test_분기점도_지시어를_읽는다():
    """🔴 같은 결함이 두 모듈에 있었다. 변수 원장 쪽만 고쳤더니 분기점 쪽에
    "홈 선발이 5이닝을 넘기는가" 가 `사유: 대상 선발을 특정하지 못했다` 로
    남았다 — 실측 2026-09-07 배포 후 확인.
    """
    import asyncio
    from datetime import UTC, datetime

    from app.engine.branch_resolve import resolve

    jg = {"sport": "mlb", "home": "Cincinnati Reds", "away": "Milwaukee Brewers",
          "home_pitcher": "Brady Singer", "away_pitcher": "Quinn Priester",
          "starts_at": datetime(2026, 9, 7, 23, 10, tzinfo=UTC)}
    rec = asyncio.run(resolve(_InningsPool(), jg, "홈 선발이 5이닝을 넘기는가"))
    assert rec.get("사유") != "질문에서 대상 선발을 특정하지 못했다", rec
    assert "home" in (rec.get("답") or {}), rec
    assert "away" not in rec["답"], "홈만 물었는데 원정까지 냈다"


def test_판별_규칙을_베끼지_않는다():
    """⚠️ 사본 금지. 지시어 규칙은 `variable_ledger.subject_of` 하나뿐이다."""
    from pathlib import Path

    src = Path("app/engine/branch_resolve.py").read_text(encoding="utf-8")
    assert "from app.engine.variable_ledger import subject_of" in src
    for copied in ("_SIDE_WORDS", "_ROLE_WORDS", '"어웨이"'):
        assert copied not in src, f"지시어 규칙을 베꼈다: {copied}"


class _InningsPool(_FakePool):
    """선발 이닝 해결사가 쓰는 세 질의를 흉내낸다."""

    async def fetch(self, sql, *a):
        from datetime import date
        if "a.pitcher = $2" in sql:                    # 본인 등판
            return [{"d": date(2026, 9, 1), "is_starter": True, "innings": 6.0,
                     "batters": 24, "r": 2}] * 4
        return await super().fetch(sql, *a)

    async def fetchrow(self, sql, *a):
        if "avg(a.innings)" in sql:                    # 소속팀 선발
            return {"n": 22, "ip": 5.4, "tbf": 22.0, "deep": 14}
        if "avg(innings)" in sql:                      # 같은처지
            return {"n": 45, "ip": 5.2, "deep": 30}
        return await super().fetchrow(sql, *a)


# ═══════════════ [BRR-1 2026-09-08] 라우팅이 질문과 다른 영역의 답을 붙였다
#
# 🔴 실측 2026-09-08 운영 `variable_ledger` 680행 — 기록형 618건의 라우팅:
#      불펜 325 · 투수 162 · 타선 105 · 연전 26
#    그중 **타선 분기가 가로챈 투수 질문 31건**(타선 분기의 30%).
#    가로채는 낱말은 `타선` 이 아니라 `부진`·`반등` 이었다:
#      "홈 선발 카라스코 최근 3경기 평균 5.78이닝 3.67실점 **부진** — …"
#    사용자가 본 형태(2026-09-07 다저스 실카드):
#      질문 "Nick Lodolo가 홈 타선을 상대로 5이닝 이상을 소화하며 버텨주는가"
#      답   "Los Angeles Dodgers 최근 3경기 경기당 6.00득점이 다음 경기에 반등하는가"
#    투수 이닝을 물었는데 상대팀 득점 회귀가 답으로 갔다.
#
# ⚠️ 반대 위험(진짜 타선 질문을 투수로 빼앗음)을 아래에서 함께 잠근다.

class _BothPool:
    """타선·투수 **두 해결사가 모두 답할 수 있는** 상태.

    🔴 한쪽 자료를 비워 두면 "라우팅이 옳아서" 가 아니라 "자료가 없어서"
       통과할 수 있다. 그러면 라우팅이 되돌아가도 테스트가 안 운다.
    """

    async def fetch(self, sql, *a):                      # _OWN (본인 등판)
        return [_own("2026-09-01", True, 5.2), _own("2026-08-26", True, 6.0)]

    async def fetchrow(self, sql, *a):
        if "prev_starts" in sql:                          # _PEERS
            return {"n": 232, "ip": 4.12, "deep": 121}
        if "n3 = 3" in sql:                               # 타선 회귀 동류
            return {"n": 60, "next_runs": 4.1}
        if "a.is_starter AND a.team" in sql:              # _TEAM
            return {"n": 22, "ip": 5.64, "tbf": 23.4, "deep": 20}
        return {"rpg": 4.4}                               # 리그 평균 득점


def _dodgers_jg():
    from datetime import UTC, datetime
    return {"sport": "mlb", "home": "Los Angeles Dodgers",
            "away": "Cincinnati Reds",
            "home_pitcher": "Emmet Sheehan", "away_pitcher": "Nick Lodolo",
            "starts_at": datetime(2026, 9, 8, 2, 10, tzinfo=UTC),
            # 타선 해결사도 답할 수 있게 재료를 준다
            "research": {"home_usage": {"runs_per_game_l3": 6.0},
                         "away_usage": {"runs_per_game_l3": 8.0}}}


def test_투수_질문이_타선_분기에_가로채이지_않는다():
    """🔴 2026-09-07 다저스 실카드의 질문 그대로."""
    import asyncio

    from app.engine.branch_resolve import resolve

    q = "Nick Lodolo가 홈 타선을 상대로 5이닝 이상을 소화하며 버텨주는가"
    rec = asyncio.run(resolve(_BothPool(), _dodgers_jg(), q))
    ans = rec.get("답") or {}
    assert ans, rec
    blk = ans.get("away") or {}
    assert "같은처지" in blk or "본인" in blk, (
        f"투수 이닝 질문인데 투수 해결사로 안 갔다: {rec}")
    flat = str(ans)
    assert "다음경기_평균득점" not in flat, "타선 회귀가 답으로 붙었다"


def test_부진이라는_낱말이_투수_질문을_타선으로_보내지_않는다():
    """실측 31건의 다수 형태 — `부진` 하나로 영역이 바뀌었다."""
    import asyncio

    from app.engine.branch_resolve import resolve

    q = "홈 선발 Emmet Sheehan 최근 3경기 평균 5.78이닝 3.67실점 부진"
    rec = asyncio.run(resolve(_BothPool(), _dodgers_jg(), q))
    blk = (rec.get("답") or {}).get("home") or {}
    assert "같은처지" in blk or "본인" in blk, rec


def test_진짜_타선_질문은_투수_이름이_있어도_타선이_답한다():
    """⚠️ 반대 위험 — 이름만 보고 투수로 보내면 타선 회귀를 잃는다.

    투수 **결과**를 묻는 낱말(이닝·실점·소화)이 없으면 타선 그대로다.
    """
    import asyncio

    from app.engine.branch_resolve import resolve

    q = "원정 타선이 Nick Lodolo를 상대로 최근 3경기 배율 1.29를 유지하는가"
    rec = asyncio.run(resolve(_BothPool(), _dodgers_jg(), q))
    flat = str(rec.get("답") or {})
    assert "다음경기_평균득점" in flat, f"타선 질문이 투수로 샜다: {rec}"


def test_라인업_확정_여부는_실시간형이다():
    """🔴 2026-09-07 다저스 실카드 — 답이 우리 DB 에 있는데 못 받았다.

    "Ohtani의 선발 라인업 복귀 및 타순 배치 확정 여부"
      → `_RECORD_PAT` 의 `타순` 에 걸려 기록형 → 투수 분기로 낙하
      → 사유 "질문에서 대상 선발을 특정하지 못했다" (답 없음)
    라인업 공시와 결장은 `live_status` 가 이미 답한다.
    """
    from app.engine.branch_resolve import LIVE, classify

    for q in ("Ohtani의 선발 라인업 복귀 및 타순 배치 확정 여부",
              "주전 포수의 라인업 복귀 여부",
              "오타니 타순 배치 확정 여부"):
        assert classify(q) == LIVE, f"{q!r} → {classify(q)}"


def test_실시간형_확장이_기록형을_빼앗지_않는다():
    """⚠️ 반대 위험 — 기록형을 빼앗으면 리그 표본 답을 통째로 잃는다."""
    from app.engine.branch_resolve import RECORD, classify

    for q in ("타순 상위 3명의 최근 3경기 득점력",
              "부상 복귀 후 투구수 관리 계획",
              "홈 불펜이 조기 가동되는가",
              "연전 4일차 원정 피로"):
        assert classify(q) == RECORD, f"{q!r} → {classify(q)}"


# ═══════════════ [BRR-2 2026-09-08] BRR-1 의 조건이 좁았다
#
# 🔴 **오늘 카드에서 그대로 났다.** 운영 `analysis:kbo:2026-09-08` game=1721
#    (KIA @ 삼성, stage=final):
#      질문 "최원태의 이전 맞대결 부진 재발"
#      답   "Samsung Lions 최근 3경기 경기당 5.67득점이 다음 경기에 반등하는가"
#    투수를 물었는데 팀 득점 회귀가 왔다 — 2026-09-07 다저스와 같은 결함이다.
#    BRR-1 은 `주체가 투수 **그리고** 투수 결과 낱말(이닝·실점·소화…)` 을
#    요구했는데 이 문장에는 그 낱말이 없다(`맞대결 부진 재발`). 그래서 못 잡았다.
#
# ⚠️ `부진` 을 그냥 더하면 진짜 타선 질문을 빼앗는다. 가르는 신호는
#    **주격 조사**다 — `타선이/타선은/타선의` 면 타선이 주어이고,
#    `타선을 상대로` 는 목적어다. 조사가 붙지 않으면 주체 판별을 따른다.

def test_투수_주체면_결과_낱말이_없어도_투수가_답한다():
    """🔴 운영 2026-09-08 KBO 1721 실문장."""
    import asyncio

    from app.engine.branch_resolve import resolve

    q = "Emmet Sheehan의 이전 맞대결 부진 재발"
    rec = asyncio.run(resolve(_BothPool(), _dodgers_jg(), q))
    blk = (rec.get("답") or {}).get("home") or {}
    assert "같은처지" in blk or "본인" in blk, (
        f"투수를 물었는데 투수 해결사로 안 갔다: {rec}")
    assert "다음경기_평균득점" not in str(rec.get("답") or {})


def test_타선이_주어면_투수_이름이_있어도_타선이_답한다():
    """⚠️ 반대 위험 — 주격 조사가 붙은 타선은 빼앗지 않는다."""
    import asyncio

    from app.engine.branch_resolve import resolve

    for q in ("원정 타선이 Nick Lodolo를 상대로 최근 3경기 배율 1.29를 유지하는가",
              "홈 타선의 최근 침체가 Emmet Sheehan 상대로 반등하는가",
              "원정 득점력이 반등하는가"):
        rec = asyncio.run(resolve(_BothPool(), _dodgers_jg(), q))
        assert "다음경기_평균득점" in str(rec.get("답") or {}), \
            f"타선 질문이 투수로 샜다: {q!r} → {rec}"


# ═══════════════ [BRR-3 2026-09-08] 카드의 분기점과 붙은 답이 다른 질문이었다
#
# 🔴 실측 2026-09-08 운영 캐시 — 분기점과 조사 질문이 둘 다 있는 9경기:
#      유사도 ≥0.6 (사실상 같은 질문) 7건 (78%)
#      유사도 <0.6 (다른 질문)        2건 (22%)
#    판정이 회차마다 거의 같은 분기점을 반복해서 대부분은 안 보인다. 문제는 22%:
#      [mlb 4101] 유사도 0.29  ← 사용자가 지적한 어제 다저스 경기
#        이번 분기점 : "Emmet Sheehan이 5이닝을 넘기며 3실점 이하로 막는가"  (홈 선발)
#        붙은 조사   : "Nick Lodolo가 홈 타선을 상대로 5이닝 이상을 …"       (원정 선발)
#      [npb 4415] 유사도 0.38 — 같은 투수인데 기준이 5이닝 vs 7이닝
#
# 원인은 2단 구조다(`pipeline.py:2820` 주석): `attach` 는 판정 **앞**에서 돌아
# **직전 회차**의 분기점을 푼다. 그 답이 판정의 재료가 되는 것은 옳다 —
# 유료 호출을 늘리지 않는 설계다. 문제는 **카드가 그 캐시를 읽는다**는 것이다.
#
# 고침: 판정이 끝난 뒤 한 번 더 조사해 **이번 회차** 분기점의 답을 캐시에 남긴다.
#   · 판정 입력은 안 바뀐다 — 다음 회차 `attach` 가 어차피 같은 matchup 을
#     다시 풀므로 결과가 동일하다(아래 테스트가 그 등가성을 잠근다).
#   · LLM 호출 0. DB 질의만 경기당 4~8개.
#   · v1.4 동결(판정 입력·프롬프트·게이트)에 저촉되지 않는다 — 표시 계층이다.


@pytest.mark.asyncio
async def test_재조사는_이번_회차_분기점을_푼다():
    """🔴 판정이 새 분기점을 내면 `attach` 는 **그것**을 푼다."""
    from app.engine.branch_resolve import attach

    jg = _dodgers_jg()
    jg["matchup"] = {"전개": {"분기점": "Nick Lodolo가 5이닝을 넘기는가"}}
    await attach(_BothPool(), jg)
    first = (jg["branch"].get("항목") or [{}])[0].get("질문")
    assert "Lodolo" in str(first), first

    # 판정이 돌아 분기점이 바뀌었다 (다저스 경기에서 실제로 일어난 일)
    jg["matchup"] = {"전개": {"분기점": "Emmet Sheehan이 5이닝을 넘기는가"}}
    await attach(_BothPool(), jg)
    second = (jg["branch"].get("항목") or [{}])[0].get("질문")
    assert "Sheehan" in str(second), (
        f"판정이 새 분기점을 냈는데 옛 질문이 남아 있다: {second}")


@pytest.mark.asyncio
async def test_재조사는_다음_회차_판정_입력을_바꾸지_않는다():
    """⚠️ 이 수정의 안전성이 여기 걸려 있다.

    판정 뒤에 다시 조사해 두면, 다음 회차가 판정 **앞**에서 같은 matchup 을
    다시 푼 결과와 **같아야** 한다. 같지 않으면 판정 재료를 바꾼 것이고
    v1.4 동결 위반이다.
    """
    from app.engine.branch_resolve import attach

    jg1, jg2 = _dodgers_jg(), _dodgers_jg()
    m = {"전개": {"분기점": "Emmet Sheehan이 5이닝을 넘기는가"}}
    jg1["matchup"] = dict(m)
    jg2["matchup"] = dict(m)
    await attach(_BothPool(), jg1)                     # 판정 뒤 재조사
    await attach(_BothPool(), jg2)                     # 다음 회차 판정 앞 조사
    assert jg1["branch"] == jg2["branch"], "두 시점의 조사 결과가 다르다"


def test_파이프라인이_판정_뒤에도_분기점을_푼다():
    """배선 — 판정 앞뒤로 두 번 돈다. 앞은 판정 재료, 뒤는 카드가 읽는 캐시."""
    src = open("app/pipeline.py", encoding="utf-8").read()
    i = src.index("async def _run_baseball_matchups")
    seg = src[i:src.index("\nasync def ", i + 10)]
    j = seg.index("if await judge_matchup(jg, redis, date, allow_final=allow_final)")
    assert "_branch(" in seg[:j], "판정 앞 조사가 사라졌다 — 판정 재료가 빈다"
    assert "_branch(" in seg[j:], "판정 뒤 재조사가 없다 — 카드가 옛 질문의 답을 본다"


def test_재조사_실패가_판정을_막지_않는다():
    """⚠️ 표시용이다. 실패해도 카드는 나가야 한다."""
    src = open("app/pipeline.py", encoding="utf-8").read()
    i = src.index("async def _run_baseball_matchups")
    seg = src[i:src.index("\nasync def ", i + 10)]
    j = seg.index("if await judge_matchup(jg, redis, date, allow_final=allow_final)")
    tail = seg[j:]
    k = tail.index("_branch(")
    assert "except Exception" in tail[k:k + 600], "재조사 실패가 판정을 죽인다"
