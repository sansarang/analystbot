"""수동 재발송도 L1 감사를 받는다 — 배선 지도 §3 의 빈 칸 (2026-09-07).

`_spawn_fact_audit` 은 `_run_baseball_matchups` 안에만 있었다
(pipeline.py:2732). `tools/resend` 는 캐시의 판정을 그대로 보내므로
**그 경로로 나간 카드는 L1 을 통과한 적이 없었다.**
"무엇이 무엇을 부르는가"를 그려보고서야 보인 구멍이다.
"""
from __future__ import annotations

import pathlib

SRC = pathlib.Path("tools/resend.py").read_text(encoding="utf-8")


def test_resend_spawns_the_audit():
    assert "_spawn_fact_audit" in SRC, "수동 재발송이 감사를 안 부른다"


def test_audit_runs_only_for_actually_sent_cards():
    i = SRC.index("_spawn_fact_audit(jg)")
    head = SRC[max(0, i - 400):i]
    assert 'res in ("sent", "revised")' in head, "안 나간 카드까지 감사한다"


def test_audit_needs_a_verdict():
    i = SRC.index("_spawn_fact_audit(jg)")
    head = SRC[max(0, i - 400):i]
    assert 'p_claude' in head, "판정 없는 경기를 감사한다"


def test_audit_does_not_block_sending():
    """감사는 발송 뒤에 온다 — 실패해도 카드는 이미 나갔다."""
    i = SRC.index("_spawn_fact_audit(jg)")
    j = SRC.index("res = await send_game_prediction")
    assert j < i, "감사가 발송보다 앞에 있다"


def test_resend_still_does_not_rejudge():
    """계약 유지 — resend 는 '재발송'이지 '재판정'이 아니다."""
    # 주석에 이름이 나오는 것은 호출이 아니다 — **코드 줄**만 본다.
    code = "\n".join(ln for ln in SRC.split("\n")
                     if not ln.lstrip().startswith("#"))
    assert "judge_matchup(" not in code
    assert "_run_baseball_matchups(" not in code
