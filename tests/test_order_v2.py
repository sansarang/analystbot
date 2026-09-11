"""ORD-1 — 순서를 바꾼다. **경기 → 갈림길 → 보강 → 결론 → (애매하면) DB.**

사용자 지시 2026-09-11:
  "동적으로 움직여야 한다고 몇번을 애기하냐..순서만 바꾸는 거다...경기가 나왔어..
   ai가 먼저 변수 및 갈림등을 찾는다..그후에 인공위성,퍼플릭스가 x가 보강자료를
   찾는다...결론을 낸다...애매한거는 우리 디비를 참조한다..."

🔴 왜. 종전(SCT-1)은 자료1~14 를 **먼저** 통째로 주고 그 위에서 변수를 만들었다.
   실측 2026-09-11 MLB 15경기 — 근거 45줄의 출처: 자료9 13 · 자료12 11 · 자료4 8 ·
   자료1 8 · 자료10 5 · **정찰(자료15) 3**. 자료를 먼저 주면 자료가 답을 정하고,
   조사는 이미 정해진 답의 각주가 된다.

⚠️ 이 파일은 새 심볼을 **모듈 최상단에서 임포트하지 않는다.** 수정 전 코드에
   없는 이름이라 파일이 통째로 ImportError 로 죽고, 그러면 "심볼이 없다"로
   실패해 **결함 자체를 겨눈 단언**(순서가 바뀌지 않았다)에 닿지 못한다.
"""

import pytest

from app.engine import matchup as MU


def _jg():
    return {"game_id": 5620, "sport": "mlb", "league": "MLB",
            "home": "Chicago Cubs", "away": "Pittsburgh Pirates",
            "starts_at": "2026-09-11T18:20:00+00:00",
            "home_pitcher": "Shota Imanaga", "away_pitcher": "Wilber Dotel",
            "lineup_status": "none",
            "material11": {"home": {"연전": 1, "이동": "원정→홈"},
                           "away": {"연전": 4, "이동": "원정 연속"},
                           "날씨": {"라벨": "선선"}}}


def _pre():
    return {"갈림길": [{"질문": "도텔이 4이닝을 넘기는가", "왜": "선발 경험이 없다"}],
            "변수": ["도텔이 3이닝 미만으로 강판"],
            "조사요청": ["Wilber Dotel 9월 11일 등판 이닝 제한"]}


# ═══════════════ ① 경기만 본다 — DB 수치가 들어가지 않는다

def test_경기_정보에_수치가_없다():
    """🔴 여기 성적을 한 줄이라도 넣으면 그 순간 다시 'DB 먼저'가 된다."""
    b = MU.game_brief(_jg())
    for banned in ("방어율", "ERA", "레이팅", "승률", "최근 3경기", "runs_l3",
                   "박스스코어", "타율"):
        assert banned not in b, banned


def test_경기_정보에_있어야_할_것은_있다():
    """🔴 반대 위험 — 너무 비우면 ① 이 대진표만 보고 지어내기 시작한다."""
    b = MU.game_brief(_jg())
    for need in ("Chicago Cubs", "Pittsburgh Pirates", "Shota Imanaga",
                 "Wilber Dotel", "MLB", "연전"):
        assert need in b, need


def test_선발이_미정이면_미정이라고_쓴다():
    jg = _jg()
    jg.pop("home_pitcher")
    assert "홈 선발: 미정" in MU.game_brief(jg)


def test_정찰_프롬프트가_승패를_묻지_않는다():
    from app.engine.prompts import PRESCOUT

    assert "승패·확률을 적지 마라" in PRESCOUT
    assert "수치를 지어내지 마라" in PRESCOUT


def test_정찰이_채점_규칙을_재사용한다():
    """🔴 사본 금지 — 임계 규칙을 다시 적으면 채점 불가 변수가 샌다."""
    from app.engine.prompts import PRESCOUT, VARIABLE_GRADEABLE

    assert VARIABLE_GRADEABLE in PRESCOUT


# ═══════════════ ② 보강은 ①이 정한 질문만 본다

def test_보강_프롬프트가_질문_밖을_막는다():
    from app.engine.prompts import REINFORCE_ASK

    assert "질문에 없는 것은 가져오지 마라" in REINFORCE_ASK
    assert "답을 모르면 그 항목을 빼라" in REINFORCE_ASK


def test_질문_수에_상한이_있다():
    """질문이 많을수록 답이 얕아진다. 상한이 없으면 모델이 20개를 적는다."""
    from app.engine.deepsearch import MAX_ASKS

    assert 2 <= MAX_ASKS <= 8


@pytest.mark.asyncio
async def test_보강이_0건이어도_결과를_돌려준다(monkeypatch):
    """🔴 0건이라는 **사실**이 결론 프롬프트에 실려야 한다."""
    import app.engine.deepsearch as DS

    async def _none(*a, **k):
        return []

    monkeypatch.setattr(DS, "_free_articles", _none)
    monkeypatch.setattr(DS, "_ask_pplx", _none, raising=False)
    monkeypatch.setattr(DS, "_ask_grok", _none, raising=False)
    out = await DS.reinforce(_jg(), _pre(), None)
    assert out["자료"] == [] and out["질문"] == _pre()["조사요청"]


@pytest.mark.asyncio
async def test_한_채널이_터져도_나머지는_산다(monkeypatch):
    import app.engine.deepsearch as DS

    async def _boom(*a, **k):
        raise RuntimeError("터졌다")

    async def _ok(jg, asks):
        return [{"질문": asks[0], "답": "제한 65구", "소스": "x",
                 "소스유형": "뉴스", "url": "u"}]

    async def _none(*a, **k):
        return []

    monkeypatch.setattr(DS, "_free_articles", _none)
    monkeypatch.setattr(DS, "_ask_pplx", _boom, raising=False)
    monkeypatch.setattr(DS, "_ask_grok", _ok, raising=False)
    out = await DS.reinforce(_jg(), _pre(), None)
    assert len(out["자료"]) == 1 and out["출처"] == {"x": 1}


def test_답이_없는_항목은_버린다():
    """🔴 "찾지 못했다"를 답으로 실으면 결론이 그것을 사실로 읽는다."""
    from app.engine.deepsearch import _rows

    got = _rows([{"질문번호": 1, "답": ""}, {"질문번호": 1, "답": "찾음"}],
                ["q"], "pplx")
    assert [r["답"] for r in got] == ["찾음"]


def test_범위_밖_질문번호는_질문을_비운다():
    """지어낸 번호로 엉뚱한 질문에 답을 붙이면 그게 더 나쁘다."""
    from app.engine.deepsearch import _rows

    assert _rows([{"질문번호": 9, "답": "x"}], ["q"], "x")[0]["질문"] == ""


# ═══════════════ ③ 결론 — 자료1~14 가 없다

def test_결론_프롬프트에_DB_자료가_없다():
    p = MU.render_conclude_prompt(_jg(), MU.game_brief(_jg()), _pre(),
                                  {"자료": [], "질문": []})
    assert "[입력 자료]" not in p
    assert "BOXSCORE_JSON" not in p and "{{" not in p


def test_결론_프롬프트가_갈림길과_보강을_싣는다():
    reinf = {"자료": [{"질문": "q", "답": "65구 제한", "소스": "x",
                      "소스유형": "뉴스", "url": "u"}],
             "질문": ["q"], "출처": {"x": 1}}
    p = MU.render_conclude_prompt(_jg(), MU.game_brief(_jg()), _pre(), reinf)
    assert "도텔이 4이닝을 넘기는가" in p
    assert "65구 제한" in p and "[x/뉴스]" in p


def test_보강_0건이면_0건이라고_적는다():
    """🔴 빈 칸으로 두면 결론이 지어내기 시작한다."""
    p = MU.render_conclude_prompt(_jg(), MU.game_brief(_jg()), _pre(),
                                  {"자료": [], "질문": ["q"]})
    assert "조사 결과 0건" in p
    assert "아는 척하지 마라" in p


def test_출력_스키마를_판정에서_잘라_쓴다():
    """🔴 사본 금지 — 스키마를 다시 적으면 카드가 읽는 키가 갈린다."""
    from app.engine.prompts import CONCLUDE, MATCHUP, MATCHUP_OUTPUT_BLOCK

    assert MATCHUP_OUTPUT_BLOCK in MATCHUP
    assert MATCHUP_OUTPUT_BLOCK in CONCLUDE
    assert '"p_home"' in MATCHUP_OUTPUT_BLOCK


def test_없는_자료번호를_적지_말라고_한다():
    """공용 [변수 형식] 은 자료4·10·14 를 가리키는데 이 자리엔 없다."""
    from app.engine.prompts import CONCLUDE

    assert "없는 자료 번호를 적지 마라" in CONCLUDE
    assert "근거 보강" in CONCLUDE


# ═══════════════ ④ 애매할 때만 DB

def test_DB_블록을_판정_프롬프트에서_잘라_온다():
    """🔴 자료 조립을 두 벌 만들지 않는다."""
    p = "머리말\n[입력 자료]\n1. 박스스코어 {...}\n[변수 형식]\n규칙\n[출력]\n{}"
    b = MU.db_block(p)
    assert b.startswith("[입력 자료]")
    assert "박스스코어" in b
    assert "[변수 형식]" not in b and "[출력]" not in b


def test_경계를_못_찾으면_통째로_준다():
    """🔴 조용히 빈 문자열을 주면 재질의가 자료 없이 돈다."""
    assert MU.db_block("자료 경계가 없는 문자열") == "자료 경계가 없는 문자열"


def test_DB_블록이_참조임을_밝힌다():
    from app.engine.prompts import DB_ON_DEMAND

    assert "이것은 참조다" in DB_ON_DEMAND
    assert "처음부터" in DB_ON_DEMAND and "다시 쓰지 마라" in DB_ON_DEMAND
    assert "여기가 마지막이다" in DB_ON_DEMAND


def test_결론이_자료필요_칸을_갖는다():
    from app.engine.prompts import CONCLUDE

    assert '"자료필요"' in CONCLUDE
    assert "습관적으로 채우지 마라" in CONCLUDE


# ═══════════════ 스위치 · 배선

def test_스위치는_기본_꺼짐이다():
    """판정 입력을 통째로 바꾸는 스위치다 — 실측 전에 전 슬레이트에 켜지 않는다."""
    from app.config import Settings

    assert Settings.model_fields["order_v2"].default is False


def test_판정_문에_배선돼_있다():
    """🔴 존재하는 것과 불리는 것은 다르다(실사고 PGP-2)."""
    src = open("app/engine/matchup.py", encoding="utf-8").read()
    body = src[src.index("async def judge_matchup"):]
    for need in ("prescout", "reinforce", "render_conclude_prompt",
                 "game_brief", "db_block", "DB_ON_DEMAND"):
        assert need in body, need


def test_순서가_지켜진다():
    """갈림길 → 보강 → 결론. 보강이 갈림길보다 먼저 불리면 순서가 아니다."""
    src = open("app/engine/matchup.py", encoding="utf-8").read()
    body = src[src.index("async def judge_matchup"):]
    assert (body.index("_prescout(jg, _brief)")
            < body.index("_reinforce(jg, _pre, redis)")
            < body.index("render_conclude_prompt(jg, _brief"))


def test_갈림길_실패는_종전_경로다():
    """조사가 안 됐다고 판정을 멈추지 않는다."""
    src = open("app/engine/matchup.py", encoding="utf-8").read()
    body = src[src.index("_order_v2 = bool("):]
    assert "_order_v2 = False" in body[:1400]
    assert "prompt = _db_prompt" in body[:1800]


def test_재질의_실패는_첫_답을_쓴다():
    """🔴 있던 판정을 재질의 실패로 잃지 않는다."""
    src = open("app/engine/matchup.py", encoding="utf-8").read()
    i = src.index("_second = await _ask(_again)")
    assert "첫 답을 쓴다" in src[i:i + 600]


# ═══════════════ 실측이 잡은 것 (2026-09-11 game=5624 리허설)

def test_선발은_API_예고값을_먼저_쓴다():
    """🔴 `research.{side}_pitcher` 는 LLM 이 채운 칸이다. 실측 game=5624:
       거기엔 "Baltimore SP (확정 선발 불명)" 이 있었고 games 컬럼엔
       "Chris Bassitt" 이 있었다. ① 은 경기 사실만 봐야 한다."""
    jg = _jg()
    jg["research"] = {"away_pitcher": {"name": "Baltimore SP (확정 선발 불명)"}}
    jg["away_pitcher"] = "Chris Bassitt"
    assert "Chris Bassitt" in MU.game_brief(jg)
    assert "확정 선발 불명" not in MU.game_brief(jg)


def test_API_값이_없으면_종전_함수로_내려간다():
    jg = _jg()
    jg.pop("away_pitcher")
    jg["research"] = {"away_pitcher": {"name": "대체 이름"}}
    assert "대체 이름" in MU.game_brief(jg)


def test_긴_산문은_잘린다():
    """🔴 실측 game=5624: 자료11 `날씨.수치` 에 LLM 산문 400자가 들어 있었다.
    그대로 넣으면 ① 이 경기가 아니라 남의 분석문을 읽는다."""
    jg = _jg()
    jg["material11"]["날씨"] = {"수치": "가" * 900}
    b = MU.game_brief(jg)
    assert "…" in b
    assert max(len(x) for x in b.splitlines()) < 200


def test_위성은_답이_아니라_참고로_실린다():
    """🔴 실측 game=5624: 위성 48건이 전부 트랜잭션 줄이었다. 답 칸에 섞으면
    결론이 무관한 48줄을 갈림길의 근거로 읽는다."""
    reinf = {"질문": ["q"], "출처": {},
             "자료": [{"질문": "q", "답": "65구 제한", "소스": "x", "소스유형": "뉴스",
                      "url": "u"},
                     {"질문": "", "답": "Orioles optioned SS Luis Vázquez.",
                      "소스": "satellite", "소스유형": "MLB Transactions", "url": ""}]}
    p = MU.render_conclude_prompt(_jg(), MU.game_brief(_jg()), _pre(), reinf)
    assert p.index("【질문에 대한 답】") < p.index("【참고")
    assert "질문에 대한 답이 아니다" in p
    assert p.index("65구 제한") < p.index("Luis Vázquez")


def test_위성만_있고_답이_0건이면_0건이라고_쓴다():
    reinf = {"질문": ["q"], "출처": {},
             "자료": [{"질문": "", "답": "이적 공시", "소스": "satellite",
                      "소스유형": "MLB Transactions", "url": ""}]}
    p = MU.render_conclude_prompt(_jg(), MU.game_brief(_jg()), _pre(), reinf)
    assert "0건 — 위 갈림길에 아무도 답하지 못했다" in p


@pytest.mark.asyncio
async def test_위성_전량을_싣지_않는다(monkeypatch):
    import app.engine.deepsearch as DS

    async def _many(*a, **k):
        return [{"title": f"t{i}", "url": "", "body": ""} for i in range(60)]

    async def _none(*a, **k):
        return []

    monkeypatch.setattr(DS, "_free_articles", _many)
    monkeypatch.setattr(DS, "_ask_pplx", _none, raising=False)
    monkeypatch.setattr(DS, "_ask_grok", _none, raising=False)
    out = await DS.reinforce(_jg(), _pre(), None)
    assert out["출처"]["satellite"] == DS.MAX_SAT < 60


def test_배열_응답을_통째로_읽는다():
    """🔴 실측 2026-09-11 game=5624: Grok 이 `**[{..},{..}]**` 로 정답 2건을
    줬는데 `parse_json_object` 가 첫 객체만 떼어 내 0건이 됐다."""
    from app.engine.deepsearch import _parse_array, _rows

    raw = '**[{"질문번호": 1, "답": "5.2이닝 3자책"}, {"질문번호": 2, "답": "6.2이닝"}]**'
    assert len(_rows(_parse_array(raw), ["q1", "q2"], "x")) == 2


def test_객체_하나만_와도_버리지_않는다():
    from app.engine.deepsearch import _rows

    assert len(_rows({"질문번호": 1, "답": "x"}, ["q"], "x")) == 1


def test_추가확인과_자료필요를_잇는다():
    """🔴 실측 2026-09-11 game=5624: 판정이 `추가확인` 에 "최근 3경기 득점력 및
    불펜 소모"를 적고 `자료필요` 는 비워 냈다 — 같은 말인데 ④ 가 안 돌았다."""
    from app.engine.prompts import CONCLUDE

    assert "`추가확인` 에 적은 것 중 우리 DB 가 줄 수 있는 것" in CONCLUDE
