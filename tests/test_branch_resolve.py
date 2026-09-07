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
