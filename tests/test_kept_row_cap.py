"""PRM-2 — 채택 자료 300자 절단이 DB 행의 원정 블록을 통째로 잘랐다.

🔴 **실측 2026-09-13 (운영, Seattle Mariners @ Athletics, game 6003).**
   제미니가 "원정 선발 Bryan Woo의 최근 등판 기록을 확인하지 못했다"를 반복했다.
   자료는 전부 있었다:
     운영 DB          Bryan Woo 등판 5건 (9/6 8.0이닝 … 8/11 5.0이닝)
     payload          home 5건 · away 5건 · 키 동일
     dbref.bundle 행  1331자 (ITEM_MAX 2600 → 잘림 없음)
   그런데 **최종 프롬프트에는 `선발등판` 이 1회**뿐이었다(두 블록이면 2회).
   복사만 시키는 분리 실험에서도 모델이 `{"복사": "없음"}` 이라 답했다 —
   **읽고도 안 쓴 것이 아니라 프롬프트에 정말 없었다.**

   범인은 `fmt_kept` 의 행당 300자 절단이다:
       " ".join(str(r.get("답") or "").split())[:300]
   그 상한은 **뉴스 기사 한 줄** 기준인데, DB 행(1331자)이 같은 줄로 들어가
   `{"home": {...Gage Jump...}` 까지만 남고 `"away"` 가 사라졌다.

⚠️ 뉴스 행의 상한은 **건드리지 않는다** — 300자는 기사 한 줄에 맞춘 값이다.
   길이가 필요한 것은 DB 행이다(`소스 == dbref.SOURCE`).
"""
import json

from app.engine import dbref, verdict


def _news(text):
    return {"소스": "satellite", "답": text}


def _db(text):
    return {"소스": dbref.SOURCE, "답": text}


def test_DB행은_원정_블록까지_살아남는다():
    """🔴 실측된 결함 그대로 — away 가 잘려 나갔다."""
    payload = {"home": {"팀": "Athletics", "선발": "Gage Jump",
                        "선발등판": [{"innings": 4.0, "date": f"2026-09-0{i}"}
                                   for i in range(1, 6)]},
               "away": {"팀": "Seattle Mariners", "선발": "Bryan Woo",
                        "선발등판": [{"innings": 8.0, "date": f"2026-08-1{i}"}
                                   for i in range(1, 6)]}}
    row = _db("선발 최근 등판 — " + json.dumps(payload, ensure_ascii=False))
    out = verdict.fmt_kept([row])
    assert "Bryan Woo" in out, out
    assert "Seattle Mariners" in out, out
    assert out.count("선발등판") == 2, out


def test_뉴스행은_종전대로_300자다():
    """⚠️ 반대 위험 — 기사 한 줄까지 길어지면 프롬프트가 부푼다."""
    long_text = "가" * 900
    out = verdict.fmt_kept([_news(long_text)])
    body = out.split("] ", 1)[1]
    assert len(body) == 300, len(body)


def test_DB행도_무한은_아니다():
    """⚠️ `dbref.ITEM_MAX` 가 원본이다 — 숫자를 두 곳에 적지 않는다."""
    out = verdict.fmt_kept([_db("x" * 9000)])
    body = out.split("] ", 1)[1]
    assert len(body) == dbref.ITEM_MAX, (len(body), dbref.ITEM_MAX)


def test_소스가_없으면_뉴스로_본다():
    out = verdict.fmt_kept([{"답": "나" * 900}])
    assert len(out.split("] ", 1)[1]) == 300
