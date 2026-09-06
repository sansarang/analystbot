"""KBO·NPB 경기마다 1차 발송 · 변동 시 재발송. Judge는 호출하지 않는다."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.engine.pregame_push import (
    HARD_TARGET_MIN,
    NPB_FINISH_MIN,
    SEND_OPEN_MIN,
    SPORTS,
    STAGE1_DEADLINE_MIN,
    analysis_open,
    card_sig_key,
    card_signature,
    compose_card,
    header_line,
    in_send_window,
    roster_signature,
    run_pregame_push,
    send_game_prediction,
    still_upcoming,
)


def test_only_kbo_npb_mlb():
    assert SPORTS == ("kbo", "npb", "mlb")
    assert "soccer" not in SPORTS


def test_deadlines_are_30_and_15():
    assert STAGE1_DEADLINE_MIN == 30
    assert HARD_TARGET_MIN == 15
    assert NPB_FINISH_MIN == 15
    assert SEND_OPEN_MIN == {"kbo": 70, "npb": 40, "mlb": 180}


def test_header_is_stage_not_clock():
    assert header_line("kbo") == "⏰ KBO · 1차"
    assert header_line("npb", revision=True) == "⏰ NPB · 라인업 변경 재판정"


def test_still_upcoming_skips_started():
    now = datetime(2026, 8, 28, 8, 45, tzinfo=UTC)  # KST 17:45
    assert still_upcoming(now + timedelta(minutes=15), now) is True   # NPB 18:00
    assert still_upcoming(now + timedelta(minutes=45), now) is True   # KBO 18:30
    assert still_upcoming(now, now) is False
    assert still_upcoming(now - timedelta(minutes=1), now) is False


def test_send_window_opens_at_1720():
    now = datetime(2026, 8, 28, 8, 20, tzinfo=UTC)  # KST 17:20
    kbo = datetime(2026, 8, 28, 9, 30, tzinfo=UTC)  # 18:30, T-70
    npb = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)   # 18:00, T-40
    assert in_send_window("kbo", kbo, now) is True
    assert in_send_window("npb", npb, now) is True
    assert in_send_window("kbo", kbo, now - timedelta(minutes=1)) is False  # T-71
    assert in_send_window("npb", npb, now - timedelta(minutes=1)) is False  # T-41
    assert in_send_window("kbo", now - timedelta(minutes=1), now) is False


def test_mlb_send_window_is_180():
    now = datetime(2026, 8, 29, 0, 10, tzinfo=UTC)  # KST 09:10
    start = now + timedelta(minutes=180)
    assert in_send_window("mlb", start, now) is True
    assert in_send_window("mlb", start, now - timedelta(minutes=1)) is False
    assert in_send_window("mlb", now - timedelta(minutes=1), now) is False
    assert analysis_open("mlb", start, now) is True


def test_npb_analysis_closes_at_1745_send_does_not():
    """18:00 NPB: 17:45에 크롤·분석 종료. 이미 판정된 카드는 시작 전까지 보낸다."""
    now = datetime(2026, 8, 28, 8, 45, tzinfo=UTC)  # KST 17:45
    npb = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)   # 18:00
    kbo = datetime(2026, 8, 28, 9, 30, tzinfo=UTC)  # 18:30
    assert analysis_open("npb", npb, now) is False
    assert analysis_open("npb", npb, now - timedelta(minutes=1)) is True  # 17:44
    assert analysis_open("kbo", kbo, now) is True
    assert in_send_window("npb", npb, now) is True
    assert still_upcoming(npb, now) is True


def test_roster_signature_ignores_status_clock():
    a = roster_signature("Takahashi", "Takinaka", "A-B-C", "D-E-F")
    b = roster_signature("Takahashi", "Takinaka", "A-B-C", "D-E-F")
    c = roster_signature("Takahashi", "Takinaka", "A-B-X", "D-E-F")
    assert a == b
    assert a != c
    assert "confirmed" not in a and "predicted" not in a


def test_compose_card_is_game_prediction():
    jg = {
        "game_id": 11, "sport": "kbo", "home": "LG Twins", "away": "NC Dinos",
        "starts_at_kst": "08/28 18:30", "status": "scheduled", "league": "KBO",
        "p_claude": 0.61, "judge_confidence": "medium", "verdict": "홈 우세",
        "best_odds": {}, "expert_picks": [], "stats": {},
        "research": {
            "home_recent_form": {"form": "WWLWW", "runs_avg": 5.1},
            "away_recent_form": {"form": "LLWLL", "runs_avg": 3.2},
            "home_pitcher": {"name": "임찬규", "era_season": 3.40},
        },
        "market_board": [],
    }
    text = compose_card(jg, "", "kbo")
    assert "1차" in text
    assert "17:45" not in text
    assert "LG" in text or "트윈스" in text or "NC" in text
    assert "라인업 변경 재판정" in compose_card(jg, "", "kbo", revision=True)


class _Redis:
    def __init__(self, store=None):
        self.store = store if store is not None else {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, val, nx=False, ex=None):
        if nx and key in self.store:
            return False
        self.store[key] = val
        return True

    async def delete(self, key):
        self.store.pop(key, None)

    async def ttl(self, key):
        return -1



class _Pool:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    async def fetch(self, *_a, **_k):
        return self.rows

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


def _row(gid=11, sport="kbo", minutes=45):
    now = datetime(2026, 8, 28, 8, 45, tzinfo=UTC)
    return now, {
        "id": gid, "sport": sport, "home": "LG Twins", "away": "NC Dinos",
        "starts_at": now + timedelta(minutes=minutes), "league": "KBO",
    }


def _game(gid=11, sport="kbo", p=0.61, pitcher="임찬규", nine="김현수",
          final=False):
    # [2026-09-06] `final_verdict` 는 "이 판정이 최종(Anthropic)인가"다.
    #   두 번째 카드 자리는 최종의 몫이라, 재발송 검사는 최종을 세워야 한다.
    return {
        "game_id": gid, "sport": sport, "home": "LG Twins", "away": "NC Dinos",
        "starts_at_kst": "08/28 18:30", "status": "scheduled", "league": "KBO",
        "final_verdict": final,
        "p_claude": p, "judge_confidence": "medium", "verdict": "홈 우세",
        "best_odds": {}, "expert_picks": [], "stats": {},
        "research": {
            "home_recent_form": {"form": "WWLWW", "runs_avg": 5.1},
            "away_recent_form": {"form": "LLWLL", "runs_avg": 3.2},
            "home_pitcher": {"name": pitcher},
            "home_lineup": {"order": nine},
        },
        "today_nine": {
            "home": {"order": [{"slot": 1, "name": nine, "pos": "LF", "status": "usual"}]},
            "away": {"order": []},
        },
        "compare": {"favored": "home"},
        "scoring": {"level": "보통"},
        "market_board": [],
    }


def _analysis(gid=11, **kw):
    return json.dumps({"games": [_game(gid, **kw)], "news": ""})


def _block_claude(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("Claude 분석은 이 경로에서 호출되면 안 된다")

    async def boom_async(*_a, **_k):
        raise AssertionError("Claude 분석은 이 경로에서 호출되면 안 된다")

    monkeypatch.setattr("app.pipeline.ensure_analysis_cache", boom_async)
    monkeypatch.setattr("app.engine.judge.Judge.judge", boom_async)
    monkeypatch.setattr("app.pipeline.Judge.judge", boom_async)


@pytest.mark.asyncio
async def test_sends_kbo_and_npb_per_game(monkeypatch):
    now = datetime(2026, 8, 28, 8, 45, tzinfo=UTC)
    rows = [
        {"id": 11, "sport": "kbo", "home": "LG Twins", "away": "NC Dinos",
         "starts_at": now + timedelta(minutes=45), "league": "KBO"},
        {"id": 22, "sport": "npb", "home": "Hanshin Tigers", "away": "Yomiuri Giants",
         "starts_at": now + timedelta(minutes=15), "league": "NPB"},
    ]
    rds = _Redis()
    sent = []

    async def fake_send(text, **_k):
        sent.append(text)
        return True

    rds.store["analysis:kbo:2026-08-28"] = _analysis(11)
    rds.store["analysis:npb:2026-08-28"] = json.dumps({
        "games": [{
            **_game(22, sport="npb", p=0.58, pitcher="村上", nine="佐藤"),
            "home": "Hanshin Tigers", "away": "Yomiuri Giants",
            "starts_at_kst": "08/28 18:00", "league": "NPB",
        }],
        "news": "",
    })
    _block_claude(monkeypatch)
    monkeypatch.setattr("app.engine.pregame_push.today_kst", lambda: "2026-08-28")
    monkeypatch.setattr("app.notify.send_telegram", fake_send)

    out = await run_pregame_push(_Pool(rows), rds, now)
    assert out["sent"] == 2 and len(sent) == 2
    assert any("KBO" in t and "1차" in t for t in sent)
    assert any("NPB" in t and "1차" in t for t in sent)

    out2 = await run_pregame_push(_Pool(rows), rds, now)
    assert out2["sent"] == 0 and out2["revised"] == 0
    assert out2["skipped"] == 2
    assert len(sent) == 2


@pytest.mark.asyncio
async def test_lineup_change_resends_as_revision(monkeypatch):
    now, row = _row()
    rds = _Redis()
    rds.store["analysis:kbo:2026-08-28"] = _analysis(pitcher="임찬규", nine="김현수")
    sent = []

    async def fake_send(text, **_k):
        sent.append(text)
        return True

    _block_claude(monkeypatch)
    monkeypatch.setattr("app.engine.pregame_push.today_kst", lambda: "2026-08-28")
    monkeypatch.setattr("app.notify.send_telegram", fake_send)

    assert await send_game_prediction(rds, row, "2026-08-28", now=now) == "sent"
    rds.store["analysis:kbo:2026-08-28"] = _analysis(
        pitcher="켈리", nine="오스틴", p=0.64, final=True)
    assert await send_game_prediction(rds, row, "2026-08-28", now=now) == "revised"
    assert "라인업 변경 재판정" in sent[1]
    assert await send_game_prediction(rds, row, "2026-08-28", now=now) == "skipped"
    assert len(sent) == 2


@pytest.mark.asyncio
async def test_verdict_change_resends_even_if_lineup_same(monkeypatch):
    """[계약 갱신] 종전에는 라인업이 같으면 판정이 움직여도 스킵했다.

    재발송은 이제 (라인업 변경) OR (판정 변경)이다. 같은 라인업에서 승률이
    0.61 → 0.66 으로 움직였으면 그것이 곧 새 정보다.
    """
    now, row = _row()
    rds = _Redis()
    rds.store["analysis:kbo:2026-08-28"] = _analysis(p=0.61)
    sent = []

    async def fake_send(text, **_k):
        sent.append(text)
        return True

    _block_claude(monkeypatch)
    monkeypatch.setattr("app.notify.send_telegram", fake_send)
    assert await send_game_prediction(rds, row, "2026-08-28", now=now) == "sent"
    rds.store["analysis:kbo:2026-08-28"] = _analysis(p=0.66, final=True)
    assert await send_game_prediction(rds, row, "2026-08-28", now=now) == "revised"
    assert len(sent) == 2
    assert "라인업 변경 재판정" in sent[1]


@pytest.mark.asyncio
async def test_lineup_change_same_verdict_sends_compact_card(monkeypatch):
    """🔴 [계약 갱신 ②, 2026-09-06] 라인업만 바뀐 두 번째 카드도 **전체 카드**다.

    종전 계약(2026-09-02): 라인업이 실제로 바뀌었는데 확률·우세·확신도가
    우연히 같으면 스킵됐고, 사용자는 **바뀐 라인업을 영영 못 봤다.** 그래서
    축약 카드(`compose_lineup_only_card`)를 만들었다.

    이번 계약(사용자 지시): 픽은 두 장이고 두 번째는 **최종 판정 카드**다.
    그 한 장이 이 경기에 대한 마지막 답이므로 축약본이 아니라 전체 카드로
    나가야 한다 — 라인업만 바뀌었더라도 사용자가 마지막으로 보는 것은
    승률·근거가 다 실린 카드여야 한다.
    ⚠️ 그 결과 `compose_lineup_only_card` 는 도달하지 않는다. 지우지 않고
       둔다 — 계약이 또 바뀔 때 되살릴 자리다.
    """
    now, row = _row()
    rds = _Redis()
    rds.store["analysis:kbo:2026-08-28"] = _analysis(pitcher="임찬규", p=0.61)
    sent = []

    async def fake_send(text, **_k):
        sent.append(text)
        return True

    _block_claude(monkeypatch)
    monkeypatch.setattr("app.notify.send_telegram", fake_send)
    assert await send_game_prediction(rds, row, "2026-08-28", now=now) == "sent"
    rds.store["analysis:kbo:2026-08-28"] = _analysis(pitcher="켈리", p=0.61,
                                                     final=True)
    assert await send_game_prediction(rds, row, "2026-08-28", now=now) == "revised"
    assert len(sent) == 2
    card = sent[1]
    assert "라인업 변경 재판정" in card, "수정 카드 표기가 없다"
    assert "우세" in card and "%" in card, "최종 카드인데 승률이 없다"
    assert "임찬규 → 켈리" in card, "무엇이 바뀌었는지 카드에 없다"
    # 종전 축약 카드는 "판정 변동 없음"이라고 **적었다** — 침묵하면 판정도
    #   바뀐 줄 알기 때문이다. 전체 카드는 확률을 그대로 실으므로 침묵이
    #   아니다: 61% 가 카드에 있고 사용자는 직전 카드와 대조할 수 있다.
    assert "61.0%" in card, "전체 카드인데 판정 수치가 없다"


@pytest.mark.asyncio
async def test_send_failure_does_not_mark_sent(monkeypatch):
    now, row = _row()
    rds = _Redis()
    rds.store["analysis:kbo:2026-08-28"] = _analysis()

    async def boom(text, **_k):
        return False

    _block_claude(monkeypatch)
    monkeypatch.setattr("app.notify.send_telegram", boom)

    out = await send_game_prediction(rds, row, "2026-08-28", now=now)
    assert out == "failed"
    assert card_sig_key(11) not in rds.store


@pytest.mark.asyncio
async def test_missing_cache_does_not_send_empty_card(monkeypatch):
    now, row = _row()
    rds = _Redis()
    sent = []

    async def fake_send(text, **_k):
        sent.append(text)
        return True

    _block_claude(monkeypatch)
    monkeypatch.setattr("app.notify.send_telegram", fake_send)

    out = await send_game_prediction(rds, row, "2026-08-28", now=now)
    assert out == "skipped"
    assert sent == []
    assert card_sig_key(11) not in rds.store


@pytest.mark.asyncio
async def test_unjudged_cache_does_not_send(monkeypatch):
    now, row = _row()
    rds = _Redis({
        "analysis:kbo:2026-08-28": json.dumps({
            "games": [{
                "game_id": 11, "home": "LG Twins", "away": "NC Dinos",
                "starts_at_kst": "08/28 18:30", "status": "scheduled",
            }],
        }),
    })
    sent = []

    async def fake_send(text, **_k):
        sent.append(text)
        return True

    _block_claude(monkeypatch)
    monkeypatch.setattr("app.notify.send_telegram", fake_send)

    out = await send_game_prediction(rds, row, "2026-08-28", now=now)
    assert out == "skipped"
    assert sent == []


@pytest.mark.asyncio
async def test_cancelled_crawler_game_is_not_sent(monkeypatch):
    """네이버 취소가 Redis에만 있어도 카드는 나가지 않고 DB를 cancelled로 맞춘다."""
    now = datetime(2026, 8, 28, 8, 45, tzinfo=UTC)
    row = {
        "id": 506, "sport": "kbo", "home": "Lotte Giants", "away": "LG Twins",
        "starts_at": now + timedelta(minutes=45), "league": "KBO",
    }
    rds = _Redis({
        "crawl:kbo:2026-08-28:latest": json.dumps({
            "LG Twins@Lotte Giants": {
                "status": "경기취소", "home_pitcher": "나균안",
            },
        }),
        "analysis:kbo:2026-08-28": _analysis(506),
    })
    sent = []

    async def fake_send(text, **_k):
        sent.append(text)
        return True

    _block_claude(monkeypatch)
    monkeypatch.setattr("app.engine.pregame_push.today_kst", lambda: "2026-08-28")
    monkeypatch.setattr("app.notify.send_telegram", fake_send)

    pool = _Pool([row])
    out = await run_pregame_push(pool, rds, now)
    assert out["sent"] == 0 and out["skipped"] == 1
    assert sent == []
    assert pool.executed
    assert card_sig_key(506) not in rds.store


@pytest.mark.asyncio
async def test_voided_judgement_is_not_sent(monkeypatch):
    now, row = _row()
    rds = _Redis({
        "analysis:kbo:2026-08-28": json.dumps({
            "games": [{**_game(), "judgement_void": True}],
            "news": "",
        }),
    })
    sent = []

    async def fake_send(text, **_k):
        sent.append(text)
        return True

    _block_claude(monkeypatch)
    monkeypatch.setattr("app.notify.send_telegram", fake_send)
    assert await send_game_prediction(rds, row, "2026-08-28", now=now) == "skipped"
    assert sent == []
    a = _game(nine="김현수")
    b = _game(nine="오스틴")
    assert card_signature(a) != card_signature(b)
    assert card_signature(a) == card_signature(_game(nine="김현수"))


def test_checklist_contract_states_1745_and_not_1730_guarantee():
    from app.engine.pregame_checklist import (
        contract_lines, incident_lines, research_lines,
    )

    text = "\n".join(contract_lines() + incident_lines() + research_lines())
    assert "17:45" in text
    assert "빈 카드" in text
    assert "강제 아님" in text
    assert "창 놓침" in text
    assert "KBO 전경기 취소" in text
    assert "parlay" in text or "odds=None" in text
    assert "세이부" in text
    assert "직렬 Judge" in text
    assert "ensure_analysis_cache" in text
    assert "today_nine" in text
    assert "prefetch_daily" in text
    assert "관중" in text
    assert "미구현" in text
    assert "200~300픽" in text
    assert "딥서치" in text


@pytest.mark.asyncio
async def test_checklist_reports_npb_window_by_clock():
    from app.engine.pregame_checklist import build_pregame_checklist

    rds = _Redis()
    open_at = datetime(2026, 8, 29, 8, 30, tzinfo=UTC)   # KST 17:30
    text_open = await build_pregame_checklist(None, rds, now=open_at)
    assert "NPB 분석창" in text_open and "열림" in text_open
    assert "docs/PREGAME_CHECKLIST.md" in text_open

    closed_at = datetime(2026, 8, 29, 8, 45, tzinfo=UTC)  # KST 17:45
    text_closed = await build_pregame_checklist(None, rds, now=closed_at)
    assert "NPB 분석창" in text_closed and "닫힘" in text_closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "second,expect,why",
    [
        (dict(pitcher="임찬규", nine="김현수", p=0.61), "skipped", "둘 다 동일"),
        (dict(pitcher="켈리", nine="김현수", p=0.61), "revised", "라인업만 변경"),
        (dict(pitcher="임찬규", nine="김현수", p=0.66), "revised", "판정만 변경"),
        (dict(pitcher="켈리", nine="오스틴", p=0.66), "revised", "둘 다 변경"),
    ],
)
async def test_resend_matrix_is_lineup_or_verdict(monkeypatch, second, expect, why):
    """재발송 = (라인업 변경) OR (판정 변경). 둘 다 같을 때만 스킵한다.

    종전 규칙은 "둘 중 하나라도 같으면 스킵"이라 4케이스 중 2건이
    잘못 눌렸다(라인업만 변경 · 판정만 변경).
    """
    now, row = _row()
    rds = _Redis()
    first = dict(pitcher="임찬규", nine="김현수", p=0.61)
    rds.store["analysis:kbo:2026-08-28"] = _analysis(**first)
    sent = []

    async def fake_send(text, **_k):
        sent.append(text)
        return True

    _block_claude(monkeypatch)
    monkeypatch.setattr("app.notify.send_telegram", fake_send)
    assert await send_game_prediction(rds, row, "2026-08-28", now=now) == "sent"
    rds.store["analysis:kbo:2026-08-28"] = _analysis(final=True, **second)
    out = await send_game_prediction(rds, row, "2026-08-28", now=now)
    assert out == expect, f"{why}: {out}"
    assert len(sent) == (1 if expect == "skipped" else 2)


@pytest.mark.asyncio
async def test_both_hash_same_logs_skip_reason(monkeypatch, caplog):
    """스킵은 조용히 사라지면 안 된다 — 사유가 로그에 남아야 원인을 짚는다."""
    import logging

    now, row = _row()
    rds = _Redis()
    rds.store["analysis:kbo:2026-08-28"] = _analysis(p=0.61)

    async def fake_send(_text, **_k):
        return True

    _block_claude(monkeypatch)
    monkeypatch.setattr("app.notify.send_telegram", fake_send)
    assert await send_game_prediction(rds, row, "2026-08-28", now=now) == "sent"
    with caplog.at_level(logging.INFO, logger="app.engine.pregame_push"):
        assert await send_game_prediction(rds, row, "2026-08-28", now=now) == "skipped"
    assert "skip_reason=both_hash_same" in caplog.text


def test_lineup_diff_reads_the_signature_itself():
    """서명이 곧 읽을 수 있는 형식이라 별도 저장 없이 diff 를 만든다."""
    from app.engine.pregame_push import lineup_diff

    assert lineup_diff("임찬규|켈리|1:김현수|1:손아섭",
                       "최원태|켈리|1:김현수|1:손아섭") == ["홈 선발 임찬규 → 최원태"]
    assert lineup_diff("A|B|1:가,2:나|1:다",
                       "A|B|1:가,2:라|1:다") == ["홈 2번 나 → 라"]
    # 이전 서명이 없거나 형식이 다르면 **지어내지 않는다**
    assert lineup_diff(None, "A|B|C|D") == []
    assert lineup_diff("legacy-string", "A|B|C|D") == []


def test_verdict_hash_ignores_sub_percent_jitter():
    """🔴 실측 2026-09-01: 같은 입력으로 matchup 을 2회 연속 호출했더니
    p_home 이 0.38 / 0.34 로 갈렸다(diff 0.0400, claude-sonnet-5, mock 아님).
    "temperature 0 전제"는 사실이 아니었다 — 매치업 경로는 temperature 를
    넘기지도 않는다(sonnet-5 가 400 으로 거부해 2026-08-29 에 뺐다).

    4자리 해시면 0.5842 vs 0.5847 이 다른 해시가 되어, 입력이 그대로인데도
    수정 카드가 나간다.
    """
    from app.engine.pregame_push import verdict_hash

    base = {"matchup": {"우세": "home", "확신도": "중"}}
    h1 = verdict_hash({**base, "p_claude": 0.5842})
    h2 = verdict_hash({**base, "p_claude": 0.5847})
    assert h1 == h2, "1%p 미만 흔들림이 재발송을 만든다"

    h3 = verdict_hash({**base, "p_claude": 0.58})
    h4 = verdict_hash({**base, "p_claude": 0.61})
    assert h3 != h4, "3%p 차이는 재발송해야 한다"


def test_verdict_hash_still_reacts_to_side_and_confidence():
    """우세·확신도는 실측에서 흔들리지 않았다 — 바뀌면 반드시 알려야 한다."""
    from app.engine.pregame_push import verdict_hash

    a = {"p_claude": 0.60, "matchup": {"우세": "home", "확신도": "중"}}
    assert verdict_hash(a) != verdict_hash(
        {**a, "matchup": {"우세": "away", "확신도": "중"}})
    assert verdict_hash(a) != verdict_hash(
        {**a, "matchup": {"우세": "home", "확신도": "하"}})
# ---------------------------------------------------------------- NPB 창 이원화

def test_rejudge_window_is_wider_than_full_analysis_for_npb():
    """🔴 NPB 공시는 T-30이다. 풀 분석과 경량 재판정을 같이 T-15에 닫으면
    창이 15분뿐이고, 놓친 경기는 잠정으로 남아 추천 게이트에서 탈락한다.

    풀 분석(analysis_open)은 T-15 그대로, 경량 재판정(rejudge_open)만 T-10.
    """
    from app.engine.pregame_push import NPB_REJUDGE_FINISH_MIN, rejudge_open

    assert NPB_REJUDGE_FINISH_MIN == 10
    now = datetime(2026, 8, 28, 8, 45, tzinfo=UTC)          # KST 17:45
    npb_1800 = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)      # T-15
    # T-15: 풀 분석은 닫히고 경량 재판정은 열려 있다 — 이것이 이원화의 핵심
    assert analysis_open("npb", npb_1800, now) is False
    assert rejudge_open("npb", npb_1800, now) is True
    # T-11 열림 / T-10 닫힘 (기존 NPB_FINISH_MIN 과 같은 `>` 경계 관례)
    assert rejudge_open("npb", now + timedelta(minutes=11), now) is True
    assert rejudge_open("npb", now + timedelta(minutes=10), now) is False
    # 🔴 [2026-09-03 사용자 결정] KBO 도 **T-15 에 닫는다.**
    #    NPB 처럼 15/10 으로 나누지 않았다 — 지시가 "시작 15분 전"이라
    #    경량까지 하나로 둔다. NPB 의 이원화는 공시가 T-30 이라 15분 창이
    #    너무 좁다는 실측에서 나온 것이라 **NPB 에만** 남긴다.
    assert rejudge_open("kbo", now + timedelta(minutes=1), now) is False
    assert rejudge_open("kbo", now + timedelta(minutes=21), now) is True
    assert rejudge_open("kbo", now + timedelta(minutes=20), now) is False
    assert analysis_open("kbo", now + timedelta(minutes=20), now) is False
    # MLB 는 마감선 없음 — 라인업 공시가 T-180 이라 사정이 다르다
    assert rejudge_open("mlb", now + timedelta(minutes=1), now) is True
    # 이미 시작한 경기는 어느 창도 열지 않는다
    assert rejudge_open("npb", now - timedelta(minutes=1), now) is False


def test_full_analysis_window_unchanged():
    """이원화가 풀 분석 창을 건드리지 않았다는 회귀 확인."""
    from app.engine.pregame_push import NPB_FINISH_MIN

    assert NPB_FINISH_MIN == 15 and HARD_TARGET_MIN == 15
    now = datetime(2026, 8, 28, 8, 45, tzinfo=UTC)
    npb = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)
    assert analysis_open("npb", npb, now) is False
    assert analysis_open("npb", npb, now - timedelta(minutes=1)) is True


def test_pending_card_says_what_is_missing():
    """T-10에도 미확정이면 침묵하지 않는다 — "카드가 안 온 것"과
    "라인업이 안 나온 것"은 사용자에게 다른 일이다."""
    from app.engine.pregame_push import lineup_pending_card

    card = lineup_pending_card("npb", "Hanshin Tigers", "Yomiuri Giants", 10)
    assert "라인업 미확정 — 관망" in card
    assert "10분 전" in card
    assert "추천하지 않습니다" in card
    assert "공시되면 즉시 재판정" in card
