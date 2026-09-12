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


def test_출력은_승자_하나다():
    """🔴 [ORD-3] "어느팀이 승리한다만 제미나이가 판다."
    확률·근거·변수·전개·확신도는 전부 설명이고, 설명은 카드에 나가지 않는다."""
    from app.engine.prompts import CONCLUDE

    out = CONCLUDE[CONCLUDE.index("[출력]"):]
    assert '"승자"' in out
    # 출력 칸에 승자 말고는 아무것도 없다. (본문의 "…적지 마라" 는 금지 문구다)
    for gone in ("p_home", "우세", "확신도", "전개", "예상점수", "직전대비",
                 "뉴스반영", "추가확인", "자료필요", "근거", "변수"):
        assert gone not in out, gone


def test_확률과_설명을_적지_말라고_한다():
    from app.engine.prompts import CONCLUDE

    assert "확률·근거·설명을 적지 마라" in CONCLUDE
    assert "기억으로 판단하지 마라" in CONCLUDE


def test_승자는_두_팀_중_하나여야_한다고_못박는다():
    from app.engine.prompts import CONCLUDE

    assert "두 팀 중 하나의 이름을 그대로" in CONCLUDE
    assert "KT Wiz" in CONCLUDE          # 실측 사례를 근거로 남긴다


# ═══════════════ ④ 는 없다 — DB 를 전부 뺐다 (ORD-2)

def test_DB_참조_경로가_없다():
    """🔴 사용자 지시 2026-09-11: "데이타 베이스는 전부 삭제…db가 답을 바꾼다."
    실측(ORD-1 리허설 3경기): ④ 가 3/3 돌았고 NYM@NYY 는 0.54 NYY → 0.46 NYM
    으로 **승자째 뒤집혔다.** DB 를 뒤로 미뤄도 DB 가 답을 정했다."""
    from app.engine import prompts as P

    assert not hasattr(MU, "db_block")
    assert not hasattr(P, "DB_ON_DEMAND")


def test_결론이_DB_를_요청할_칸이_없다():
    from app.engine.prompts import CONCLUDE

    assert "자료필요" not in CONCLUDE
    assert "여기 있는 것이 전부다" in CONCLUDE


def test_DB_가_오지_않는다고_못박는다():
    """🔴 DB 를 뺀 자리를 기억으로 메우는 것이 유일하게 치명적인 실패다."""
    from app.engine.prompts import CONCLUDE

    assert "너에게 오지 않는다" in CONCLUDE
    assert "조사 결과가 가리키는 쪽을 고른다" in CONCLUDE


def test_박스스코어와_폼을_새_순서에서는_만들지_않는다():
    """🔴 "최근 3경기 폼도 삭제" — 만들어 봐야 프롬프트에 안 들어간다."""
    src = open("app/engine/matchup.py", encoding="utf-8").read()
    body = src[src.index("async def judge_matchup"):]
    assert "boxes = {} if _order_v2 else boxscore_payload(jg)" in body
    i = body.index('_form_or_analyze(jg, redis, date, "home"')
    assert "if _order_v2:" in body[i - 700:i]


def test_새_순서는_판정_프롬프트를_조립하지_않는다():
    src = open("app/engine/matchup.py", encoding="utf-8").read()
    body = src[src.index("async def judge_matchup"):]
    i = body.index("render_matchup_prompt(jg, boxes, news, prev)")
    assert "else:" in body[i - 60:i], "종전 경로에서만 조립해야 한다"


def test_조사가_비면_판정하지_않는다():
    """🔴 절대 규칙 6 — 재료 없으면 분석 생성 금지. 팀 이름 위에서 확률을
    만드는 것이 곧 '기억으로 판정하기'다."""
    src = open("app/engine/matchup.py", encoding="utf-8").read()
    body = src[src.index("async def judge_matchup"):]
    i = body.index('if not (_reinf.get("자료") or [])')
    blk = body[i:i + 900]
    assert 'jg["form_unavailable"] = True' in blk
    assert "return None" in blk
    assert "보강 0건" in blk        # 미발송 사유가 남는다


def test_새_순서는_종전_경로로_폴백하지_않는다():
    """자료를 조립하지 않았으므로 폴백해도 빈 프롬프트다 — 조용한 0 을 만든다."""
    src = open("app/engine/matchup.py", encoding="utf-8").read()
    body = src[src.index("async def judge_matchup"):]
    assert "prompt = _db_prompt" not in body
    i = body.index("_pre = await _prescout")
    assert "추천 탈락" in body[i:i + 800]


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
                 "game_brief"):
        assert need in body, need


def test_순서가_지켜진다():
    """갈림길 → 보강 → 결론. 보강이 갈림길보다 먼저 불리면 순서가 아니다."""
    src = open("app/engine/matchup.py", encoding="utf-8").read()
    body = src[src.index("async def judge_matchup"):]
    assert (body.index("_prescout(jg, _brief)")
            < body.index("_reinforce(jg, _pre, redis)")
            < body.index("render_conclude_prompt(jg, _brief"))


def test_갈림길_실패는_조용하지_않다():
    """🔴 판정을 안 한 이유가 남아야 한다 — "조용한 0" 은 결함이다."""
    src = open("app/engine/matchup.py", encoding="utf-8").read()
    i = src.index("갈림길을 못 세웠다")
    assert "추천 탈락" in src[i:i + 120]
    blk = src[i - 500:i]
    assert 'jg["form_unavailable"] = True' in blk
    assert "release_final" in blk, "최종 권한을 돌려놔야 다음 폴링이 다시 본다"


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


def test_카드가_읽을_조사_원문이_남는다():
    """🔴 카드가 자료를 다시 모으면 그것이 사본이고, 두 곳이 다른 것을 본다."""
    src = open("app/engine/matchup.py", encoding="utf-8").read()
    i = src.rindex('jg["order_v2"] = {"갈림길목록"')
    for k in ("자료", "질문", "출처"):
        assert k in src[i:i + 500], k
    # 탈락한 경기에도 사유가 남아야 한다 — "조용한 0" 금지
    j = src.index('jg["order_v2"] = {"갈림길"')
    assert "탈락" in src[j:j + 600]


# ═══════════════ ORD-3 — 카드는 조사 결과만, 판정은 승자만

def _ov_jg():
    """ORD-3 판정을 끝낸 경기. 카드가 읽는 것이 전부 여기 있다."""
    return {"sport": "mlb", "league": "MLB",
            "home": "Milwaukee Brewers", "away": "Cincinnati Reds",
            "starts_at_kst": "09/12 08:45", "lineup_status": "none",
            "winner": "Milwaukee Brewers",
            "matchup": {"승자": "Milwaukee Brewers"},
            "order_v2": {
                "갈림길목록": [{"질문": "애벗이 5이닝 이상을 3실점 이하로 막는가",
                              "왜": "x"}],
                "질문": ["앤드루 애벗 최근 5경기 이닝", "레즈 원정 득점"],
                "출처": {"pplx": 1, "satellite": 2},
                "자료": [
                    {"질문": "앤드루 애벗 최근 5경기 이닝", "답": "8/29 3.0이닝 7자책",
                     "소스": "pplx", "소스유형": "기록", "url": "u"},
                    {"질문": "", "답": "Brewers activated RHP Abner Uribe",
                     "소스": "satellite", "소스유형": "MLB Transactions", "url": ""},
                    {"질문": "", "답": "Brewers activated LHP JoJo Romero",
                     "소스": "satellite", "소스유형": "MLB Transactions", "url": ""}]}}


def test_카드에_우리_수치가_하나도_없다():
    """🔴 "추천 로직도 다 삭제...수치는 전부다 삭제..." · "서술형 기본 레이팅도 삭제" """
    from app.engine.form_card import render_form_card

    card = render_form_card(_ov_jg(), "mlb")
    for gone in ("%", "★", "신호등", "가치", "배당", "시장", "레이팅",
                 "보드만", "추천", "엣지"):
        assert gone not in card, gone


def test_카드에_설명이_없다():
    """🔴 "설명도 삭제...서치에 의한 정보만 명시..." """
    jg = _ov_jg()
    jg["narrative_card"] = "밀워키가 여러모로 앞선다."
    jg["matchup"]["근거"] = ["레이팅이 앞선다"]
    from app.engine.form_card import render_form_card

    card = render_form_card(jg, "mlb")
    assert "밀워키가 여러모로" not in card
    assert "근거" not in card and "변수" not in card


def test_카드에_조사_결과가_질문별로_실린다():
    from app.engine.form_card import render_form_card

    card = render_form_card(_ov_jg(), "mlb")
    assert "🔎 조사 결과" in card
    assert "앤드루 애벗 최근 5경기 이닝" in card
    assert "8/29 3.0이닝 7자책 (퍼플렉시티)" in card


def test_못_찾은_질문을_지우지_않는다():
    """🔴 지우면 카드가 다 아는 것처럼 보인다."""
    from app.engine.form_card import render_form_card

    card = render_form_card(_ov_jg(), "mlb")
    i = card.index("레즈 원정 득점")
    assert "찾지 못함" in card[i:i + 80]


def test_공시는_따로_실린다():
    from app.engine.form_card import render_form_card

    card = render_form_card(_ov_jg(), "mlb")
    assert "📋 최근 공시" in card
    assert card.index("🔎 조사 결과") < card.index("📋 최근 공시")
    assert "Abner Uribe" in card


def test_공시가_많으면_자르고_몇_건인지_밝힌다():
    from app.engine import form_card as FC

    jg = _ov_jg()
    jg["order_v2"]["자료"] += [{"질문": "", "답": f"공시{i}", "소스": "satellite",
                               "소스유형": "t", "url": ""} for i in range(20)]
    card = FC.render_form_card(jg, "mlb")
    assert f"외 {22 - FC._NOTICE_MAX}건" in card


def test_카드_마지막은_승자다():
    from app.engine.form_card import render_form_card

    card = render_form_card(_ov_jg(), "mlb")
    assert "🏆 승리 예상 — 밀워키 브루어스" in card


def test_잠정과_최종을_밝힌다():
    from app.engine.form_card import render_form_card

    assert "🕐 잠정 · 타순 전" in render_form_card(_ov_jg(), "mlb")
    jg = _ov_jg()
    jg["lineup_status"] = "confirmed"
    assert "✅ 최종 · 타순 확정" in render_form_card(jg, "mlb")


def test_종전_경로_카드는_한_글자도_안_바뀐다():
    """🔴 스위치가 꺼진 경기·축구는 종전 카드 그대로여야 한다."""
    from app.engine.form_card import render_form_card

    jg = {"sport": "mlb", "league": "MLB", "home": "A", "away": "B",
          "lineup_status": "confirmed", "p_claude": 0.64,
          "matchup": {"p_home": 0.64, "우세": "home"}}
    card = render_form_card(jg, "mlb")
    assert "64.0%" in card and "신호등" in card


# ── 추천

def test_새_순서_경기는_추천되지_않는다():
    """🔴 "추천 로직도 다 삭제." 확률이 없어 하한과 비교할 값도 없다."""
    from app.pipeline import qualifies

    assert qualifies({"sport": "mlb", "p": 0.90, "pick_state": "final",
                      "order_v2": True}) is False


def test_픽_딕셔너리가_표식을_싣는다():
    """🔴 존재하는 것과 전달되는 것은 다르다 — 게이트가 못 보면 무의미하다."""
    src = open("app/pipeline.py", encoding="utf-8").read()
    assert src.count('"order_v2": bool(jg.get("order_v2"))') >= 2


# ── 승자 정합성 · 원장

def test_경기의_팀이_아니면_판정을_버린다():
    """🔴 확률이 없으므로 고쳐 쓸 근거가 없다. 실측: gemini 가 `KT Wiz` 를 냈다."""
    jg = {"game_id": 1, "home": "Samsung Lions", "away": "Kiwoom Heroes"}
    assert MU.apply_winner(jg, {"승자": "KT Wiz"}) is False
    assert "matchup" not in jg and "winner" not in jg


@pytest.mark.parametrize("w", ["삼성", "Samsung Lions", "samsung lions"])
def test_약칭도_정식표기도_받는다(w):
    jg = {"game_id": 1, "home": "Samsung Lions", "away": "Kiwoom Heroes"}
    assert MU.apply_winner(jg, {"승자": w}) is True
    assert jg["winner"] == "Samsung Lions"


def test_확률이_없어도_원장에_남는다():
    """🔴 안 남기면 이 방식이 맞는지 영영 못 잰다 — 조용한 손실."""
    from app.engine.pick_ledger import _row_from_game

    jg = {"game_id": 9, "sport": "mlb", "home": "Milwaukee Brewers",
          "away": "Cincinnati Reds", "winner": "Milwaukee Brewers",
          "matchup": {"승자": "Milwaukee Brewers"}}
    row = _row_from_game(jg, {"sport": "mlb", "date": "2026-09-11"}, {})
    assert row is not None
    assert row["p_home"] is None
    assert row["predicted_side"] == "home"


def test_예측을_실제_승자_칸에_넣지_않는다():
    """🔴 `winner` 는 채점이 채우는 **실제 승자**다. 같은 칸을 쓰면 채점이
    제 예측을 정답으로 덮어쓴다."""
    from app.engine.pick_ledger import _row_from_game

    jg = {"game_id": 9, "sport": "mlb", "home": "A", "away": "B",
          "matchup": {"승자": "A"}}
    row = _row_from_game(jg, {"sport": "mlb", "date": "2026-09-11"}, {})
    assert "winner" not in row


def test_채점이_저장된_방향을_읽는다():
    from app.engine.pick_ledger import predicted_side

    assert predicted_side(None, None, "away") == "away"
    assert predicted_side("home", None, "away") == "home"   # 우세가 우선
    assert predicted_side(None, 0.61, None) == "home"       # 종전 규약 불변


# ── ORD-3 실측이 잡은 것 (2026-09-11 23:0x 리허설)

def test_공시의_제목과_본문을_두_번_싣지_않는다():
    """🔴 실측 game=5629: MLB 트랜잭션은 title == body 라 카드가
    "X 를 IL 에 올렸다 — X 를 IL 에 올렸다" 를 찍었다."""
    from app.engine.deepsearch import MAX_SAT  # noqa: F401
    import app.engine.deepsearch as DS

    same = "Milwaukee Brewers activated RHP Abner Uribe from the 15-day IL."
    rows = []

    class _Fake:
        pass

    # `reinforce` 내부 조립과 같은 규칙을 직접 확인한다
    import asyncio

    async def _run():
        async def _sat(*a, **k):
            return [{"title": same, "body": same, "url": "", "source": "t"}]

        async def _none(*a, **k):
            return []

        orig = DS._free_articles, DS._ask_pplx, DS._ask_grok
        DS._free_articles, DS._ask_pplx, DS._ask_grok = _sat, _none, _none
        try:
            return await DS.reinforce(_jg(), _pre(), None)
        finally:
            DS._free_articles, DS._ask_pplx, DS._ask_grok = orig

    out = asyncio.get_event_loop().run_until_complete(_run()) \
        if False else asyncio.run(_run())
    rows = out["자료"]
    assert rows[0]["답"] == same
    assert rows[0]["답"].count("Abner Uribe") == 1


def test_오래된_공시는_안_보인다():
    """🔴 "오늘 공시"라 써놓고 2주 전 것을 보이면 그것이 거짓말이다."""
    from app.engine import form_card as FC

    jg = _ov_jg()
    jg["order_v2"]["자료"] = [
        {"질문": "", "답": "어제 복귀", "소스": "satellite", "age_h": 20.0, "url": ""},
        {"질문": "", "답": "2주 전 이적", "소스": "satellite", "age_h": 400.0,
         "url": ""}]
    card = FC.render_form_card(jg, "mlb")
    assert "어제 복귀" in card
    assert "2주 전 이적" not in card
    assert "7일 지난 공시 1건 제외" in card


def test_며칠_전_로스터_이동은_남는다():
    """🔴 48시간으로 잡았더니 실측에서 15건이 전부 빠졌다 — 유리베·로메로
    IL 복귀처럼 오늘 경기에 그대로 유효한 것까지 사라졌다."""
    from app.engine import form_card as FC

    jg = _ov_jg()
    jg["order_v2"]["자료"] = [{"질문": "", "답": "유리베 IL 복귀",
                              "소스": "satellite", "age_h": 72.0, "url": ""}]
    assert "유리베 IL 복귀" in FC.render_form_card(jg, "mlb")


def test_나이를_모르는_공시는_버리지_않는다():
    """🔴 `age_h=None` 은 "오래됐다"가 아니라 "모른다"다(NPB 가 그렇다)."""
    from app.engine import form_card as FC

    jg = _ov_jg()
    jg["order_v2"]["자료"] = [{"질문": "", "답": "나이 미상 공시",
                              "소스": "satellite", "url": ""}]
    assert "나이 미상 공시" in FC.render_form_card(jg, "mlb")


def test_헤더에_산문이_들어오면_자른다():
    """🔴 실측 game=5624: 구장 칸에 LLM 산문 400자가 들어와 카드 둘째 줄을
    통째로 먹었다."""
    from app.engine import form_card as FC

    jg = _ov_jg()
    jg["venue"] = "로저스 센터는 " + "가" * 500
    card = FC.render_form_card(jg, "mlb")
    assert "가가가" not in card, "잘라 붙이면 잘린 산문이 남는다 — 빼야 한다"
    assert "09/12 08:45" in card, "시각까지 함께 지우면 안 된다"


def test_짧은_구장_이름은_그대로_싣는다():
    from app.engine import form_card as FC

    jg = _ov_jg()
    jg["venue"] = "American Family Field"
    assert "American Family Field" in FC.render_form_card(jg, "mlb")


@pytest.mark.asyncio
async def test_위성은_최신순으로_자른다(monkeypatch):
    """🔴 실측 2026-09-11 game=5629: 위성 25건 중 7일 이내가 10건이었는데
    앞에서 15건을 자르니 그 10건이 통째로 밀려났다 — 카드 공시가 0건이 됐다."""
    import app.engine.deepsearch as DS

    old = [{"title": f"old{i}", "body": "", "url": "", "age_h": 500.0 + i}
           for i in range(DS.MAX_SAT)]
    fresh = [{"title": "오늘 복귀", "body": "", "url": "", "age_h": 3.0}]

    async def _sat(*a, **k):
        return old + fresh          # 신선한 것이 **뒤에** 있다

    async def _none(*a, **k):
        return []

    monkeypatch.setattr(DS, "_free_articles", _sat)
    monkeypatch.setattr(DS, "_ask_pplx", _none, raising=False)
    monkeypatch.setattr(DS, "_ask_grok", _none, raising=False)
    out = await DS.reinforce(_jg(), _pre(), None)
    assert any(r["답"] == "오늘 복귀" for r in out["자료"])


@pytest.mark.asyncio
async def test_나이를_모르는_위성도_버리지_않는다(monkeypatch):
    import app.engine.deepsearch as DS

    async def _sat(*a, **k):
        return [{"title": "나이 미상", "body": "", "url": ""}]

    async def _none(*a, **k):
        return []

    monkeypatch.setattr(DS, "_free_articles", _sat)
    monkeypatch.setattr(DS, "_ask_pplx", _none, raising=False)
    monkeypatch.setattr(DS, "_ask_grok", _none, raising=False)
    out = await DS.reinforce(_jg(), _pre(), None)
    assert [r["답"] for r in out["자료"]] == ["나이 미상"]


def test_옛_모양의_캐시를_만나도_카드가_죽지_않는다():
    """🔴 배포 직후 Redis `analysis:*` 에는 숫자만 담긴 `order_v2` 가 남아 있다.
    거기서 죽으면 그 경기는 카드가 통째로 못 나간다."""
    from app.engine.form_card import render_form_card

    jg = {"sport": "mlb", "league": "MLB", "home": "A", "away": "B",
          "lineup_status": "none", "winner": "A",
          "order_v2": {"갈림길": 2, "질문": 4, "보강": 6, "출처": {"pplx": 3}}}
    card = render_form_card(jg, "mlb")
    assert "🏆 승리 예상" in card
    assert "🔎 조사 결과" in card


# ═══════════════ ORD-4 — 판정 수락 조건 (P0 실사고 2026-09-12)

def test_새_순서는_승자_출력을_수락한다():
    """🔴 실사고 2026-09-12 09:4x 운영: ORDER_V2 를 켠 첫 슬레이트에서
    MLB 5632·5633 이 둘 다 탈락했다. 로그가 원인을 그대로 적었다 —
      "JSON 파싱 실패 1회 … 응답19자 절단추정=False" → "분석 불가 — 추천 탈락"
    그 19자는 `{"승자": "Athletics"}` 로 **정상**이었고, 수락 조건이
    `"p_home" in parsed` 라 새 출력을 전부 버렸다. 카드 0장이 되는 길이었다.
    """
    src = open("app/engine/matchup.py", encoding="utf-8").read()
    body = src[src.index("async def judge_matchup"):]
    i = body.index("parsed = parse_json_object(text)")
    blk = body[i:i + 900]
    assert '_want = "승자" if _order_v2 else "p_home"' in blk
    assert "if parsed and _want in parsed:" in blk


def test_종전_경로의_수락_조건은_느슨해지지_않는다():
    """🔴 종전 경로는 확률이 필수다 — 승자만 온 응답을 받으면 안 된다."""
    src = open("app/engine/matchup.py", encoding="utf-8").read()
    body = src[src.index("async def judge_matchup"):]
    i = body.index("parsed = parse_json_object(text)")
    assert 'else "p_home"' in body[i:i + 900]
    # 키를 안 보고 `if parsed:` 로 통과시키면 빈 dict 도 판정이 된다
    assert "if parsed:\n" not in body[i:i + 900]


def test_실패_로그가_무엇을_기대했는지_밝힌다():
    """🔴 이 줄이 "응답19자"만 말해 모델 탓처럼 읽혔다 — 실제로는 우리가
    엉뚱한 키를 찾고 있었다."""
    src = open("app/engine/matchup.py", encoding="utf-8").read()
    i = src.index("JSON 파싱 실패 %d회")
    blk = src[i:i + 500]
    assert "기대키=%s" in blk and "받은키=%s" in blk


# ═══════════════ ORD-5 — 조사요청이 성적이 아니라 변수를 겨눈다

def test_성적_조회를_금지한다():
    """🔴 실측 2026-09-12: 실제로 나간 조사요청 38문 중 28문(74%)이 성적
    조회였다. 적중률은 성적 65% · 변수 67% — 검색이 못 찾는 것이 아니라
    우리가 변수를 안 물었다. 원인은 PRESCOUT 의 한 줄이었다:
      "숫자가 필요하면 그것을 `조사요청` 에 적어라. 그것이 이 단계의 목적이다."
    ORD-2 에서 DB 를 지웠는데 그 줄이 남아 검색이 통계 조회기가 됐다."""
    from app.engine.prompts import PRESCOUT

    assert "숫자가 필요하면 그것을 `조사요청` 에 적어라" not in PRESCOUT
    assert "조사요청에 성적을 묻지 마라" in PRESCOUT
    for banned in ("시즌 성적", "평균자책점", "팀 타율", "OPS", "게임로그",
                   "통산 전적"):
        assert banned in PRESCOUT, banned


def test_변수_축을_제시한다():
    """🔴 금지만 하면 모델이 질문을 줄이고, 그러면 보강 0건 → 경기 탈락이
    는다. 무엇을 물어야 하는지 축을 함께 준다."""
    from app.engine.prompts import PRESCOUT

    for axis in ("부상", "말소", "투구수 제한", "연투", "지붕 개폐",
                 "라인업", "트레이드"):
        assert axis in PRESCOUT, axis


def test_리그별_이름을_함께_적는다():
    """🔴 같은 사건을 KBO 는 '말소', MLB 는 'IL' 이라 부른다. 한쪽만 적으면
    다른 리그가 그 축을 통째로 건너뛴다."""
    from app.engine.prompts import PRESCOUT

    assert "KBO" in PRESCOUT and "MLB" in PRESCOUT
    assert "1군 등록·말소" in PRESCOUT and "IL" in PRESCOUT


def test_좋은_예와_나쁜_예가_실측이다():
    """🔴 예시를 지어내면 그것이 미래의 오탐이다 — 실제로 나간 질문과
    실제로 답이 온 질문만 적는다."""
    from app.engine.prompts import PRESCOUT

    assert "George Kirby 2026 season stats" in PRESCOUT      # 실제로 나갔던 것
    assert "Wilber Dotel" in PRESCOUT                        # 실제로 답이 온 것
    assert "실제로 답이 온 질문" in PRESCOUT


def test_개수를_억지로_채우지_말라고_한다():
    """🔴 지어낸 질문은 "찾지 못함" 한 줄로 돌아온다 — 카드만 지저분해진다."""
    from app.engine.prompts import PRESCOUT

    assert "억지로 개수를 채우지 마라" in PRESCOUT


def test_답에_시점을_요구한다():
    """🔴 실측 2026-09-12: 변수를 묻기 시작하자 4·6·7월 기사가 오늘 일처럼
    돌아왔다 — "Scherzer 4월 27일 부상자 명단", "May 7월 초 발목 타박상"."""
    from app.engine.prompts import REINFORCE_ASK

    assert "언제 있었던 일인지를 `시점`" in REINFORCE_ASK
    assert "가장 최근 것 하나만" in REINFORCE_ASK


def test_날짜를_모른다고_답을_버리지_않는다():
    """🔴 규칙을 조이면 답이 함께 줄어든다. 실측 2026-09-12: 같은 질문 2개에
    PPLX 가 6회 중 2~6건으로 흔들렸고 한 번은 `{"답": []}` 을 냈다 —
    표본이 작을 때 "규칙 탓"과 "채널 변동"은 구분되지 않는다."""
    from app.engine.prompts import REINFORCE_ASK

    assert "날짜를 모른다고 답을 버리지는 마라" in REINFORCE_ASK
    assert "채널 변동" in REINFORCE_ASK


def test_시점을_행에_싣는다():
    from app.engine.deepsearch import _rows

    r = _rows([{"질문번호": 1, "답": "x", "시점": "2026-09-10"}], ["q"], "pplx")[0]
    assert r["시점"] == "2026-09-10"


def test_카드가_시점을_보여준다():
    from app.engine import form_card as FC

    jg = _ov_jg()
    jg["order_v2"]["자료"] = [{"질문": "앤드루 애벗 최근 5경기 이닝",
                              "답": "발목 타박상으로 65구 제한",
                              "시점": "2026-07-03", "소스": "pplx", "url": ""}]
    assert "[2026-07-03] 발목 타박상으로 65구 제한 (퍼플렉시티)" in \
        FC.render_form_card(jg, "mlb")


def test_날짜로_시작하는_답은_겹쳐_적지_않는다():
    from app.engine import form_card as FC

    jg = _ov_jg()
    jg["order_v2"]["자료"] = [{"질문": "앤드루 애벗 최근 5경기 이닝",
                              "답": "2026-09-10 IL 복귀", "시점": "2026-09-10",
                              "소스": "x", "url": ""}]
    card = FC.render_form_card(jg, "mlb")
    assert "[2026-09-10] 2026-09-10" not in card
    assert "2026-09-10 IL 복귀 (X)" in card
