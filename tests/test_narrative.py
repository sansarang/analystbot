"""SRCH-6 — 제미니가 쓴 분석글을 **그대로** 카드에 싣는다.

사용자 지시 2026-09-12(실물 카드를 보고): "이건 모냐? 제미니가 분석한 거를
서술형으로 해야. 예전처럼" · "제미니 프롬프트 그냥 작성하라고 해.. 제미니가
분석한 글을 그대로 보여달라고 해라..어떤 근거로 승패를 예측했는지"

🔴 무엇이 잘못됐나. ORD-3("설명도 삭제…서치에 의한 정보만 명시")을 그대로
   구현한 결과, 카드가 수집물 **원문을 쌓기만 했다.** 실물:

     📋 최근 공시
     · 2026 KBO리그 SSG전에 구원 등판해 역투하고 있다. 사진 | 롯데 자이언츠
       [스포츠서울 | 고척=이소영 기자] '윤성빈 IN-나승엽 OUT...타율 0.189로
       부진한 나승엽(24)은 선발 라인업 에서 빠졌다… — 라인업 변경 부른 수비
       실책…'나승엽 선발 제외' … [SS고척in] 야구…

   기사 본문 조각이 잘려 붙고 헤드라인 반복까지 딸려 나온다. **왜 그 팀이
   이기는지는 어디에도 없다.**

⚠️ 서술은 **창작의 자리**다. 채택 자료에 없는 성적·순위를 지어내면 그게 이
   저장소가 가장 경계하는 실패다. 프롬프트가 막고, 계약이 프롬프트를 막는다.
"""

from app.engine import form_card as FC
from app.engine import matchup as MU


def _row(ans, src="satellite"):
    return {"질문": "", "답": ans, "소스": src, "소스유형": "뉴스",
            "시점": "2026-09-12", "계정": "", "url": "", "age_h": 1.0}


def _jg(**kw):
    jg = {"game_id": 1, "sport": "kbo", "league": "KBO",
          "home": "Doosan Bears", "away": "NC Dinos",
          "winner": "Doosan Bears",
          "matchup": {"승자": "Doosan Bears", "확신": "중"},
          "order_v3": {"자료": [], "갈림길목록": [], "질문": [],
                       "DB본것": [], "승자변경": False, "DB사유": ""}}
    jg["order_v3"].update(kw.pop("ov", {}))
    jg.update(kw)
    return jg


# ═══════════════ ① 제미니에게 분석글을 쓰게 한다

def test_판정_프롬프트가_분석글을_요구한다():
    from app.engine.prompts import JUDGE2

    assert "서술" in JUDGE2


def test_어떤_근거로_골랐는지_쓰라고_한다():
    """사용자 지시: "어떤 근거로 승패를 예측했는지"."""
    from app.engine.prompts import JUDGE2

    i = JUDGE2.index("서술")
    body = JUDGE2[max(0, i - 700):i + 900]
    assert "근거" in body


def test_프롬프트가_지어내기를_막는다():
    """🔴 채택 자료에 없는 수치를 쓰면 그게 창작이다."""
    from app.engine.prompts import JUDGE2

    i = JUDGE2.index("서술")
    body = JUDGE2[max(0, i - 700):i + 900]
    assert "지어내" in body or "없는" in body


def test_출력_형식에_서술이_있다():
    from app.engine.prompts import JUDGE2

    tail = JUDGE2[JUDGE2.index("[출력]"):]
    assert '"서술"' in tail and '"승자"' in tail and '"확신"' in tail


def test_판정이_서술을_돌려준다(monkeypatch):
    import asyncio
    import json

    from app.engine import verdict as VD

    async def _c(prompt, **k):
        return json.dumps({"승자": "Doosan Bears", "확신": "중",
                           "서술": "두산이 맞춤 라인업을 냈다."}, ensure_ascii=False)

    monkeypatch.setattr("app.engine.team_form.complete_json", _c)
    out = asyncio.run(VD.decide(
        {"game_id": 1, "home": "Doosan Bears", "away": "NC Dinos", "sport": "kbo"},
        "brief", {"채택": [_row("x")], "갈림길": [], "없는것": []}))
    assert out["서술"] == "두산이 맞춤 라인업을 냈다."


def test_서술이_없어도_판정은_산다(monkeypatch):
    """🔴 서술 실패로 판정을 버리지 않는다 — 승자가 본체다."""
    import asyncio
    import json

    from app.engine import verdict as VD

    async def _c(prompt, **k):
        return json.dumps({"승자": "Doosan Bears", "확신": "중"},
                          ensure_ascii=False)

    monkeypatch.setattr("app.engine.team_form.complete_json", _c)
    out = asyncio.run(VD.decide(
        {"game_id": 1, "home": "Doosan Bears", "away": "NC Dinos", "sport": "kbo"},
        "brief", {"채택": [_row("x")], "갈림길": [], "없는것": []}))
    assert out["승자"] == "Doosan Bears" and out["서술"] == ""


def test_판정_결과가_원장에_실린다():
    """🔴 존재하는 것과 실리는 것은 다르다(PGP-2)."""
    jg = {"game_id": 1, "sport": "kbo", "home": "Doosan Bears", "away": "NC Dinos"}
    MU.apply_winner(jg, {"승자": "Doosan Bears", "확신": "중",
                         "서술": "두산이 앞선다."})
    assert jg["matchup"]["서술"] == "두산이 앞선다."


# ═══════════════ ② 그 글을 **그대로** 싣는다

def test_카드가_서술을_그대로_싣는다():
    """🔴 우리가 다시 쓰지 않는다 — 자르거나 고치면 그게 사본이다."""
    text = ("NC는 주전 박민우가 잭로그 상대 열세로 선발에서 빠졌고, 두산은 구창모에 "
            "강한 박준순을 앞세워 맞춤 라인업을 짰다. NC 불펜은 전사민이 3연투에 "
            "걸리는 등 다수가 연투 상태라 후반 운용이 불리하다.")
    out = FC.render_search_card(_jg(matchup={"승자": "Doosan Bears", "확신": "중",
                                             "서술": text}), "kbo")
    assert text in out, "서술이 잘리거나 바뀌었다"


def test_서술이_승자보다_먼저_나온다():
    """결론만 있고 이유가 없으면 읽을 것이 없다."""
    out = FC.render_search_card(
        _jg(matchup={"승자": "Doosan Bears", "확신": "중", "서술": "두산이 앞선다."}),
        "kbo")
    assert out.index("두산이 앞선다") < out.index("승리 예상")


def test_서술이_없으면_그_칸이_통째로_빠진다():
    """🔴 빈 칸을 만들지 않는다 — 없는 것은 없는 대로."""
    out = FC.render_search_card(_jg(), "kbo")
    assert "🧠" not in out


def test_서술_칸에_머리표가_있다():
    out = FC.render_search_card(
        _jg(matchup={"승자": "Doosan Bears", "확신": "중", "서술": "두산이 앞선다."}),
        "kbo")
    assert "🧠" in out
