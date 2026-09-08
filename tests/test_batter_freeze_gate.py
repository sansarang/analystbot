"""[BAT-6] 자료3 타자 주입을 **동결 게이트** 뒤에 둔다.

🔴 **내가 근거를 잘못 읽었다 (2026-09-08 23:2x).** BAT-4 커밋과 진단 §11-3 에
   "동결 해제 조건 충족(graded kbo 158 · mlb 369 · npb 130)"이라고 적었는데,
   시스템 자신의 카운터(`daily_summary.freeze_progress_lines`)로 운영에서
   다시 재니:

       FREEZE_START = 2026-09-07 (세 리그 공통, 표본 재시작)
       mlb 10/50 · kbo 0/50 · npb 0/50   ← **해제 조건 미충족**

   내가 인용한 수는 (a) `is_final` 없이 **행 단위**로 셌고 (b) 표본 재시작일을
   무시했다. 같은 실수를 이미 백테스트에서 한 번 했었다.

⚠️ 그래서 **자료3 주입과 프롬프트 문구는 기본 꺼짐**이다. 수집·적재(BAT-1~3)와
   분기점 해결사(BAT-5)는 자료 1~11 구성이 아니므로 계속 돈다 —
   표본은 쌓이고, 판정 입력은 동결된 채로 남는다.
   켜는 것은 **사람의 결정**이다: `BATTER_MATERIAL_ENABLED=1`.
"""
from __future__ import annotations

from datetime import UTC, datetime


def _jg():
    return {
        "sport": "kbo", "starts_at": datetime(2026, 9, 8, tzinfo=UTC),
        "research": {
            "today_nine": {"home": {"order": [{"slot": 1, "name": "홍창기",
                                               "pos": "우익수"}]},
                           "away": {"order": []}},
            "home_batter_recent": {"홍창기": {"경기": 5, "타수": 20, "안타": 6}},
        },
    }


def test_꺼져_있으면_자료3_이_전과_같다(monkeypatch):
    from app.config import get_settings
    from app.engine.matchup import lineups_payload

    get_settings.cache_clear()
    monkeypatch.delenv("BATTER_MATERIAL_ENABLED", raising=False)
    get_settings.cache_clear()
    item = lineups_payload(_jg())["home"]["타순"][0]
    assert set(item) == {"타순", "이름", "포지션"}, item
    get_settings.cache_clear()


def test_켜면_숫자가_실린다(monkeypatch):
    from app.config import get_settings
    from app.engine.matchup import lineups_payload

    monkeypatch.setenv("BATTER_MATERIAL_ENABLED", "1")
    get_settings.cache_clear()
    item = lineups_payload(_jg())["home"]["타순"][0]
    assert item["최근5"]["안타"] == 6, item
    get_settings.cache_clear()


def test_꺼져_있으면_프롬프트_문구도_전과_같다(monkeypatch):
    """🔒 동결 대상은 자료 구성**과 프롬프트 문구**다 — 둘 다 잠근다."""
    from app.config import get_settings
    from app.engine import prompts

    monkeypatch.delenv("BATTER_MATERIAL_ENABLED", raising=False)
    get_settings.cache_clear()
    off = prompts.baseball_material_note()
    monkeypatch.setenv("BATTER_MATERIAL_ENABLED", "1")
    get_settings.cache_clear()
    on = prompts.baseball_material_note()
    assert off == ""
    assert "최근5" in on and "부진한 것이 아니다" in on
    get_settings.cache_clear()


def test_적재는_게이트와_무관하다(monkeypatch):
    """⚠️ 표본은 꺼져 있는 동안에도 쌓여야 한다 — 켜는 날 0건이면 의미가 없다."""
    from pathlib import Path

    src = Path("app/collectors/batter_log.py").read_text(encoding="utf-8")
    assert "BATTER_MATERIAL_ENABLED" not in src
    assert "batter_material_enabled" not in src


def test_꺼지면_프롬프트가_BAT4_이전과_바이트로_같다(monkeypatch):
    """🔒 "문구를 뺐다"가 아니라 **원래 프롬프트로 되돌아간다**를 잠근다.

    빈 줄 하나라도 남으면 그것은 동결된 프롬프트를 바꾼 것이다.
    """
    import subprocess

    from app.config import get_settings
    from app.engine.prompts import MATCHUP, baseball_material_note, fill

    monkeypatch.delenv("BATTER_MATERIAL_ENABLED", raising=False)
    get_settings.cache_clear()
    now = fill(MATCHUP, BATTER_MATERIAL_NOTE=baseball_material_note())
    # f9e16ef = BAT-1. 자료3 문구를 건드리기 직전 커밋이다.
    src = subprocess.run(["git", "show", "f9e16ef:app/engine/prompts.py"],
                         capture_output=True, text=True).stdout
    ns: dict = {}
    exec(compile(src, "old_prompts.py", "exec"), ns)
    assert now == ns["MATCHUP"]
    get_settings.cache_clear()


def test_문구가_없는_칸을_약속하지_않는다(monkeypatch):
    """🔴 [BAT-7] 내가 쓴 문구가 KBO 에 없는 칸을 약속하고 있었다.

    실측 2026-09-08 로컬 적재 1,392행:
        mlb  hr/bb/so **582/582**
        npb  hr/bb/so **119/119**
        kbo  hr/bb/so **0/691**   ← 공식 `arrHitter.table3` 이 5열뿐이다
                                    [타수, 안타, 타점, 득점, 타율]
    그런데 문구는 "경기·타수·안타·홈런·타점·득점·볼넷·삼진"이라고 **여덟 칸을
    적어 놓았다.** 판정이 없는 칸을 찾다가 "자료 결손"으로 읽거나, 없는 것을
    0으로 상상할 수 있다. 손으로 적은 목록이 곧 미래의 오탐이다.
    """
    from app.config import get_settings
    from app.engine.prompts import baseball_material_note

    monkeypatch.setenv("BATTER_MATERIAL_ENABLED", "1")
    get_settings.cache_clear()
    note = baseball_material_note()
    assert "홈런" not in note and "볼넷" not in note and "삼진" not in note, note
    assert "리그마다" in note, "칸이 리그마다 다르다는 사실을 말해야 한다"
    get_settings.cache_clear()


def test_kbo_는_홈런_볼넷_삼진이_없다():
    """⚠️ 없는 칸을 **만들지 않는다**. 0으로 채우면 그것은 지어낸 사실이다."""
    from app.collectors.kbo_boxscore import parse_batting

    box = {"arrHitter": [
        _kbo_blk([["1", "二", "신민재"]], [["4", "1", "0", "1", "0.263"]]),
        _kbo_blk([], []),
    ]}
    b = parse_batting(box)["away"][0]
    assert b["ab"] == 4 and b["h"] == 1
    assert b["hr"] is None and b["bb"] is None and b["so"] is None


def _kbo_blk(rows1, rows3):
    import json

    def tbl(rows):
        return json.dumps({"rows": [{"row": [{"Text": c} for c in r]} for r in rows],
                           "tfoot": []}, ensure_ascii=False)
    return {"table1": tbl(rows1), "table2": tbl([]), "table3": tbl(rows3)}
