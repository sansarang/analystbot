"""SRCH-7 — 판정이 **필요한 것을 받아 온다.** DB에 있으면 DB, 없으면 검색.

사용자 지시 2026-09-12: "양팀 선발의 상세 투구는 있다.. 없으면 안트로픽이나
퍼플릭스한테 요청을 해서 받으라고 해야 한다.. 제미니는 필요한 거를
재요청할 수 있다"

🔴 무엇이 잘못됐나. 실측 2026-09-12, 제미니가 쓴 분석글 4/4 가 이렇게 끝났다:

    "다만 양 팀 선발 투수의 최근 등판 이닝과 실점 세부 기록이 확인되지 않은
     점은 변수입니다."
    "다만 양 팀 선발 투수의 최근 상세 성적과 구체적인 투구 내용을 확인하지
     못한 점은 변수로 남아 있습니다."

   **그 기록은 우리 DB에 있다**(`dbref.ITEMS` 의 `선발 최근 등판`).
   그런데 판정 프롬프트가 "우리 DB는 이 자리에 오지 않는다"로 막고 있었고,
   DB 참조는 판정 **뒤**(4단계)였다. 순서가 거꾸로였다.

🔴 게다가 2단계 선별은 이미 정확히 지목하고 있었다 —
   `DB요청: 선발 최근 등판`. 그 칸을 **아무도 읽지 않았다**(ORD-15 에서
   키워드 매칭을 걷어내며 죽은 칸이 됐다). 만들어 놓고 안 쓴 것이다.

⚠️ 반대 위험: 재요청이 습관이 되면 호출이 두 배가 된다. **1회로 묶고**,
   DB로 채워지는 것은 검색을 부르지 않는다(무료 우선).
"""

import asyncio

import pytest

from app.engine import dbref as DR
from app.engine import matchup as MU


# ── [NOLLM 2026-09-22] 이 파일은 **LLM 판정 경로**를 시험한다 ──────────────
#
# 🔴 사용자 지시로 `judge.llm_verdict` 기본값이 **false** 가 됐다("판정은 원래
#    코드에서 낸다"). 그러면 이 파일의 시험 대상 경로가 아예 안 돈다.
# 🔴 **그 경로를 지우지 않았다** — 스위치 한 줄로 되돌릴 수 있어야 하고,
#    되돌렸을 때 종전대로 도는지는 **계약이 지켜야 한다.**
#    그래서 여기서는 스위치를 **켜고** 시험한다.
# ⚠️ 스위치가 꺼진 동작은 `tests/test_nollm.py` 가 따로 잠근다.
import pytest as _pytest


@_pytest.fixture(autouse=True)
def _llm_verdict_on(monkeypatch):
    monkeypatch.setattr("app.engine.matchup._llm_verdict_on", lambda: True)


def _jg():
    return {"game_id": 1, "sport": "kbo", "league": "KBO",
            "home": "Doosan Bears", "away": "NC Dinos"}


# ═══════════════ ① DB 항목을 이름으로 꺼낸다

def test_이름으로_DB_항목을_꺼낸다(monkeypatch):
    monkeypatch.setattr(DR, "bundle", lambda jg: {
        "줄": [("선발 최근 등판", "구창모 6.0·5.1·6.0이닝"),
               ("오늘 타순", "1번 김주원…")],
        "있음": ["선발 최근 등판", "오늘 타순"], "없음": []})
    rows = DR.fetch(_jg(), ["선발 최근 등판"])
    assert len(rows) == 1
    assert "구창모" in rows[0]["답"]
    assert rows[0]["소스"] == DR.SOURCE


def test_행_모양이_수집_행과_같다(monkeypatch):
    """🔴 사본 금지 — 원본은 `gather._row` 다."""
    from app.engine.gather import _row

    monkeypatch.setattr(DR, "bundle", lambda jg: {
        "줄": [("오늘 타순", "x")], "있음": ["오늘 타순"], "없음": []})
    rows = DR.fetch(_jg(), ["오늘 타순"])
    assert set(rows[0]) == set(_row("x", src="y"))


def test_풀어_쓴_이름도_맞춘다(monkeypatch):
    """🔴 실측 2026-09-12: 4경기 중 2경기가 "양 팀 선발 투수의 최근 등판
    성적 및 평균자책점"처럼 풀어 써서 매핑에 실패했다."""
    monkeypatch.setattr(DR, "bundle", lambda jg: {
        "줄": [("선발 최근 등판", "v")], "있음": ["선발 최근 등판"], "없음": []})
    rows = DR.fetch(_jg(), ["양 팀 선발 투수의 최근 등판 기록"])
    assert len(rows) == 1


def test_없는_이름은_조용히_버리지_않는다(monkeypatch):
    """🔴 못 맞춘 것을 세지 않으면 "DB에 없다"와 "이름을 못 알아들었다"를
    구분할 수 없다."""
    monkeypatch.setattr(DR, "bundle", lambda jg: {
        "줄": [("오늘 타순", "x")], "있음": ["오늘 타순"], "없음": []})
    rows, miss = DR.fetch(_jg(), ["오늘 타순", "우주의 기운"], with_miss=True)
    assert len(rows) == 1 and miss == ["우주의 기운"]


def test_값이_없는_항목은_행이_되지_않는다(monkeypatch):
    """🔴 빈 값을 실으면 판정이 "있다"고 읽는다."""
    monkeypatch.setattr(DR, "bundle", lambda jg: {
        "줄": [("선발 최근 등판", None)], "있음": [], "없음": ["선발 최근 등판"]})
    assert DR.fetch(_jg(), ["선발 최근 등판"]) == []


def test_요청이_없으면_빈_목록이다():
    assert DR.fetch(_jg(), []) == []
    assert DR.fetch(_jg(), None) == []


# ═══════════════ ② 판정이 재요청할 수 있다

def test_프롬프트가_재요청_칸을_준다():
    from app.engine.prompts import JUDGE2

    assert "추가요청" in JUDGE2


def test_프롬프트가_DB에_무엇이_있는지_알려준다():
    """🔴 무엇을 달라고 할 수 있는지 모르면 재요청은 안 온다.
    ⚠️ 항목 이름을 템플릿에 **손으로 적지 않는다** — `dbref.ITEMS` 에서
       렌더 시점에 주입한다. 그래서 렌더 결과를 본다(사본 금지)."""
    from app.engine import verdict as VD

    p = VD.render(_jg(), "brief", {"채택": [{"답": "x", "소스": "s"}],
                                   "갈림길": [], "없는것": []})
    for name, _ in DR.ITEMS:
        assert name in p, name


def test_DB_메뉴를_손으로_적지_않는다():
    """🔴 사본 드리프트 — 항목이 늘면 프롬프트만 옛것이 된다."""
    from app.engine.prompts import JUDGE2

    assert "{{DB_MENU}}" in JUDGE2
    for name, _ in DR.ITEMS:
        assert name not in JUDGE2, f"{name} 이 템플릿에 박혀 있다"


def test_프롬프트가_DB는_안_온다는_옛_문구를_버렸다():
    """🔴 이제 2단계가 지목한 DB 항목은 판정 자리에 **온다.**
    옛 문구가 남으면 모델이 있는 것을 없다고 읽는다."""
    from app.engine.prompts import JUDGE2

    assert "우리 DB(최근 3경기·팀 폼·레이팅·불펜·타순)는" not in JUDGE2


def test_판정이_추가요청을_돌려준다(monkeypatch):
    import json

    from app.engine import verdict as VD

    async def _c(prompt, **k):
        return json.dumps({"승자": "Doosan Bears", "확신": "하",
                           "추가요청": ["선발 최근 등판"]}, ensure_ascii=False)

    monkeypatch.setattr("app.engine.team_form.complete_json", _c)
    out = asyncio.run(VD.decide(
        _jg(), "b", {"채택": [{"답": "x", "소스": "s"}], "갈림길": [], "없는것": []}))
    assert out["추가요청"] == ["선발 최근 등판"]


def test_추가요청도_상한이_있다(monkeypatch):
    """🔴 습관적 재요청은 호출을 두 배로 만든다."""
    import json

    from app.engine import verdict as VD

    async def _c(prompt, **k):
        return json.dumps({"승자": "Doosan Bears", "확신": "하",
                           "추가요청": [f"q{i}" for i in range(9)]},
                          ensure_ascii=False)

    monkeypatch.setattr("app.engine.team_form.complete_json", _c)
    out = asyncio.run(VD.decide(
        _jg(), "b", {"채택": [{"답": "x", "소스": "s"}], "갈림길": [], "없는것": []}))
    assert len(out["추가요청"]) <= 3


# ═══════════════ ③ 배선 — 실제로 채워 주는가

def test_판정_앞에서_DB요청을_채운다():
    """🔴 2단계가 지목한 것을 판정 **앞**에서 준다. 뒤에 주면 늦다."""
    import inspect

    src = inspect.getsource(MU._judge_v3)
    i = src.index("verdict.decide")
    assert "dbref.fetch" in src[:i], "DB 보충이 판정보다 뒤에 있다"
    assert "DB요청" in src[:i]


def test_재요청을_처리하고_다시_판정한다():
    """🔴 받아 놓고 다시 안 물으면 받은 의미가 없다."""
    import inspect

    src = inspect.getsource(MU._judge_v3)
    i = src.index("verdict.decide")
    tail = src[i + 10:]
    assert "추가요청" in tail
    assert "verdict.decide" in tail, "재판정이 없다"


def test_재요청은_한_번뿐이다():
    """🔴 무한 되묻기를 막는다 — 호출이 폭발한다."""
    import inspect

    src = inspect.getsource(MU._judge_v3)
    assert src.count("verdict.decide") == 2, "판정 호출이 2회를 넘는다"


def test_DB로_채워지면_검색을_부르지_않는다():
    """🔴 무료 우선. DB에 있는 것을 유료로 다시 사지 않는다."""
    import inspect

    src = inspect.getsource(MU._judge_v3)
    # 🔴 [NOLLM 2026-09-22] 앵커를 **재요청 블록의 첫 문장**으로 바꿨다.
    #    종전 `src.index("추가요청")` 은 그 단어의 **첫 등장**을 잡았는데,
    #    LLM 생략 스텁(`{"승자": None, …, "추가요청": []}`)이 앞에 생기면서
    #    창이 엉뚱한 곳에서 시작했다. 단언은 그대로다.
    i = src.index('asks2 = list(v.get("추가요청")')
    body = src[i:i + 1200]
    assert "dbref.fetch" in body
    j = body.index("dbref.fetch")
    assert "search" in body[j:], "검색이 DB 보충보다 앞에 있다"
    assert "못찾" in body or "miss" in body or "남은" in body, \
        "DB로 못 채운 것만 검색하는 갈래가 없다"
