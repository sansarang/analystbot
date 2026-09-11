"""픽은 두 장, 최종 분석은 한 번 — 2026-09-06 사용자 지시.

  "픽은 딱 두 번만 오는 걸로 하고, 만약에 두 번째가 왔을 때만 안트로픽이
   최종 분석한다. 그래서 분석은 딱 한 번이다."

종전에는 `judge_matchup` 이 경기당 3~5회 돌았고(슬레이트·속보·리서치 갱신·
라인업 ×2) 카드는 해시가 바뀔 때마다 무제한으로 나갔다. `JUDGE_PROVIDER=
anthropic` 하나가 그 전부를 유료로 보냈다 — 실측 2026-09-06 11:15~11:27,
12분에 11콜.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class _Cfg:
    """최종 판정이 Anthropic 인 설정 — 가장 위험한 상태에서 검사한다."""
    judge_provider = "anthropic"
    matchup_model = "claude-opus-5"
    paid_llm_allowed = True
    judge_chain = "gemini/gemini-3.7-flash,nvidia/nvidia/nemotron-3"
    form_chain = "groq/qwen3"


@pytest.fixture
def paid_primary(monkeypatch):
    from app.llm import judge_route

    monkeypatch.setattr(judge_route, "_cfg", lambda: _Cfg())
    return judge_route


# ── ① 역할 분리 ────────────────────────────────────────────────
def test_prelim_is_free_even_when_final_is_anthropic(paid_primary):
    jr = paid_primary
    assert jr.chain(jr.MATCHUP_ROLE) == [("anthropic", "claude-opus-5")]
    assert all(p != "anthropic" for p, _ in jr.chain(jr.PRELIM_ROLE))


def test_prelim_uses_the_judge_chain_not_the_form_chain(paid_primary):
    """예비도 같은 판정 프롬프트를 받는다 — 폼 사슬로 보내면 답이 다르다."""
    jr = paid_primary
    assert jr.chain(jr.PRELIM_ROLE) == [("gemini", "gemini-3.7-flash"),
                                        ("nvidia", "nvidia/nemotron-3")]
    assert jr.chain("form") == [("groq", "qwen3")]


def test_prelim_is_asked_only_once(paid_primary):
    """같은 재료를 두 번 물으면 회차마다 답이 달라진다 — 1차도 한 번이다."""
    src = _src("app/engine/team_form.py")
    assert "soft_retries = 1 if role in JUDGE_ROLES else 2" in src
    assert "attempts = 1 if role in JUDGE_ROLES else 3" in src


# ── ② 최종은 경기당 한 번 ──────────────────────────────────────
class _FakeRedis:
    def __init__(self):
        self.kv = {}

    async def delete(self, key):
        return int(self.kv.pop(key, None) is not None)

    async def set(self, key, val, ex=None, nx=False):
        if nx and key in self.kv:
            return None
        self.kv[key] = val
        return True

    async def get(self, key):
        return self.kv.get(key)


def test_claim_final_grants_exactly_one():
    from app.engine.matchup import claim_final

    r = _FakeRedis()
    jg = {"sport": "kbo", "game_id": 1713}
    first = asyncio.run(claim_final(r, jg, "2026-09-06"))
    second = asyncio.run(claim_final(r, jg, "2026-09-06"))
    assert (first, second) == (True, False)


def test_stranded_lock_falls_back_to_prelim_not_silence(monkeypatch):
    """🔴 P0 실사고 2026-09-06 (npb game=3603 니혼햄@라쿠텐).

    락은 잡혔는데 판정이 없는 상태가 실제로 났다. 종전에는 그 뒤 모든
    재판정이 "이미 완료"로 막혀 **그 경기는 카드가 영영 0장**이었다 —
    `W-SEND-PENDING` 이 15:29 에 잡을 때까지 8분간 조용히 막혀 있었다.
    잠긴 것은 "유료 최종을 또 부르지 않는다"까지다. 판정 자체가 아니다.
    """
    from app.llm.judge_route import PRELIM_ROLE

    r = _FakeRedis()
    jg = _jg(lineup_status="confirmed")
    asyncio.run(r.set("matchup:final:kbo:1713:2026-09-06", "1", nx=True))

    from app.engine import matchup as m

    seen = {}

    async def _fake_complete(prompt, *, model, max_tokens, role, mock):
        seen["role"] = role
        return json.dumps({"p_home": 0.55, "우세": "홈", "확신도": "중",
                           "근거": ["x"], "변수": []})

    monkeypatch.setattr(m, "complete_json", _fake_complete)
    monkeypatch.setattr(m, "_form_or_analyze", lambda *a, **k: asyncio.sleep(0, {}))
    monkeypatch.setattr(m, "boxscore_payload", lambda _jg: {"home": [1], "away": [1]})
    monkeypatch.setattr(m, "persist_matchup_record", lambda *a, **k: asyncio.sleep(0))
    monkeypatch.setattr(m, "_trace", lambda *a, **k: asyncio.sleep(0))

    out = asyncio.run(m.judge_matchup(jg, r, "2026-09-06", mock=False,
                                      allow_final=True))
    assert out is not None, "락 때문에 판정이 통째로 막혔다 — 카드 0장이 된다"
    assert seen["role"] == PRELIM_ROLE, "유료 최종을 또 불렀다"


def test_already_final_with_verdict_is_not_rejudged(monkeypatch):
    """판정이 이미 붙어 있으면 재판정하지 않는다 — 픽은 두 장이다."""
    from app.engine import matchup as m

    r = _FakeRedis()
    asyncio.run(r.set("matchup:final:kbo:1713:2026-09-06", "1", nx=True))
    jg = _jg(lineup_status="confirmed", p_claude=0.61)

    async def boom(*a, **k):
        raise AssertionError("판정이 있는데 다시 물었다")

    monkeypatch.setattr(m, "complete_json", boom)
    assert asyncio.run(m.judge_matchup(jg, r, "2026-09-06", mock=False,
                                       allow_final=True)) is None


def test_failed_final_returns_the_permit(monkeypatch):
    """최종이 답을 못 내면 권한을 돌려놓는다 — 다음 폴링이 다시 시도한다."""
    from app.engine import matchup as m

    r = _FakeRedis()
    jg = _jg(lineup_status="confirmed")

    async def _empty(prompt, *, model, max_tokens, role, mock):
        return ""                      # 파싱 실패

    monkeypatch.setattr(m, "complete_json", _empty)
    monkeypatch.setattr(m, "_form_or_analyze", lambda *a, **k: asyncio.sleep(0, {}))
    monkeypatch.setattr(m, "boxscore_payload", lambda _jg: {"home": [1], "away": [1]})
    monkeypatch.setattr(m, "persist_matchup_record", lambda *a, **k: asyncio.sleep(0))
    monkeypatch.setattr(m, "_trace", lambda *a, **k: asyncio.sleep(0))

    assert asyncio.run(m.judge_matchup(jg, r, "2026-09-06", mock=False,
                                       allow_final=True)) is None
    assert "matchup:final:kbo:1713:2026-09-06" not in r.kv, \
        "권한만 태우고 판정은 못 냈다 — 그 경기는 영영 카드가 없다"


def test_claim_final_allows_when_redis_is_absent():
    """잠그지 못한다고 판정을 통째로 막는 쪽이 더 나쁘다."""
    from app.engine.matchup import claim_final

    assert asyncio.run(claim_final(None, {"game_id": 1}, "2026-09-06")) is True


def test_lineup_confirmation_is_read_not_recopied():
    """타순 9명을 세는 규칙은 `lineup_confirmed` 하나뿐이다 — 여기 베끼지 않는다."""
    from app.engine.matchup import lineup_is_confirmed

    assert lineup_is_confirmed({"lineup_status": "confirmed"}) is True
    assert lineup_is_confirmed({"lineup_status": "predicted"}) is False
    assert lineup_is_confirmed({"lineup_status": "conflict"}) is False, \
        "소스 불일치는 최종 픽 자격 박탈이다"
    assert lineup_is_confirmed({}) is False
    # ⚠️ [범위 정정 2026-09-07] 파일 전체를 보면 **다른 함수**가 정당하게
    #    `parse_order` 를 부르는 것까지 걸린다(`lineups_payload` 폴백).
    #    이 테스트가 막을 것은 **확정 판별 함수 안에서** 9명을 다시 세는 것이다.
    src = _src("app/engine/matchup.py")
    i = src.index("def lineup_is_confirmed")
    seg = src[i:src.index("\ndef ", i + 10)]
    assert "parse_order" not in seg, "확정 판별 규칙을 베꼈다"
    assert "9" not in seg, "9명 세기를 확정 판별에 베꼈다"


# ── ③ judge_matchup 의 회차 ────────────────────────────────────
def _jg(**over):
    jg = {"sport": "kbo", "game_id": 1713, "home": "KIA", "away": "KT",
          "status": "scheduled", "lineup_status": "predicted"}
    jg.update(over)
    return jg


def _run_judge(jg, *, allow_final, monkeypatch):
    """실제 LLM 을 부르지 않고 **어떤 역할로 갔는지**만 잡는다."""
    from app.engine import matchup as m

    seen = {}

    async def _fake_complete(prompt, *, model, max_tokens, role, mock):
        seen["role"] = role
        return json.dumps({"p_home": 0.55, "우세": "홈", "확신도": "중",
                           "근거": ["x"], "변수": []})

    async def _fake_form(jg_, redis, date, side, mock):
        return {}

    monkeypatch.setattr(m, "complete_json", _fake_complete)
    monkeypatch.setattr(m, "_form_or_analyze", _fake_form)
    monkeypatch.setattr(m, "boxscore_payload",
                        lambda _jg: {"home": [1], "away": [1]})
    monkeypatch.setattr(m, "persist_matchup_record",
                        lambda *a, **k: asyncio.sleep(0))
    monkeypatch.setattr(m, "_trace", lambda *a, **k: asyncio.sleep(0))
    r = _FakeRedis()
    out = asyncio.run(m.judge_matchup(jg, r, "2026-09-06",
                                      mock=False, allow_final=allow_final))
    return seen.get("role"), out


def test_unconfirmed_lineup_stays_preliminary(monkeypatch):
    """타순이 안 떴으면 `allow_final=True` 라도 유료로 가지 않는다."""
    from app.llm.judge_route import PRELIM_ROLE

    role, _ = _run_judge(_jg(), allow_final=True, monkeypatch=monkeypatch)
    assert role == PRELIM_ROLE


def test_confirmed_lineup_goes_final_once(monkeypatch):
    from app.llm.judge_route import MATCHUP_ROLE

    jg = _jg(lineup_status="confirmed")
    role, out = _run_judge(jg, allow_final=True, monkeypatch=monkeypatch)
    assert role == MATCHUP_ROLE and out is not None
    assert jg["final_verdict"] is True and jg["judge_stage"] == "final"


def test_slate_pass_never_goes_final(monkeypatch):
    """슬레이트 프리페치는 타순이 확정돼 있어도 예비다 — 1차 카드 자리다."""
    from app.llm.judge_route import PRELIM_ROLE

    role, _ = _run_judge(_jg(lineup_status="confirmed"),
                         allow_final=False, monkeypatch=monkeypatch)
    assert role == PRELIM_ROLE


# ── ④ 판정 트리거는 둘뿐 ───────────────────────────────────────
def test_only_the_lineup_path_may_go_final():
    src = _src("app/pipeline.py")
    assert src.count("allow_final=True") == 2, \
        "최종이 열리는 자리는 라인업 재판정 두 곳뿐이다"
    assert src.count("_run_baseball_matchups(") == 4, \
        "정의 1 + 슬레이트 1 + 라인업 2. 속보·리서치 갱신은 부르지 않는다"


def test_breaking_and_refresh_do_not_rejudge_baseball():
    src = _src("app/pipeline.py")
    for head in ("async def _rejudge_after_breaking",
                 "async def _refresh_stale_research"):
        body = src[src.index(head):]
        body = body[:body.index("\nasync def ", 1)]
        assert "_run_baseball_matchups" not in body, f"{head} 가 야구를 재판정한다"
        assert "야구는 재판정하지 않는다" in body


# ── ⑤ 카드 2장 상한 ───────────────────────────────────────────
def test_card_cap_is_two():
    from app.engine.pregame_push import CARD_CAP

    assert CARD_CAP == 2


def test_third_card_is_skipped_with_a_reason():
    """세 장째는 조용히 사라지지 않는다 — 사유가 붙어 집계에 남는다."""
    from app.engine import pregame_push as pp
    from app.engine.dispatch_stats import REASON_KR

    assert "card_cap" in REASON_KR
    src = _src("app/engine/pregame_push.py")
    seg = src[src.index("prev = _parse_sent"):]
    assert 'return await _skip("card_cap")' in seg[:900]
    assert seg.index("card_cap") < seg.index("both_hash_same"), \
        "상한 검사가 해시 비교보다 앞에 있어야 세 장째를 막는다"


def test_second_slot_is_reserved_for_the_final_card():
    """예비 재판정이 2장째를 먹으면 정작 최종 픽이 상한에 막힌다."""
    from app.engine.dispatch_stats import REASON_KR

    assert "card_reserved" in REASON_KR
    src = _src("app/engine/pregame_push.py")
    src2 = _src("app/engine/pregame_push.py")
    assert 'if _n >= 1 and not jg.get("final_verdict")' in src2
    assert 'return await _skip("card_reserved")' in src2
    # 해시 비교 뒤여야 한다 — 안 바뀐 카드의 사유는 `변경 없음` 그대로다.
    assert src2.index("both_hash_same") < src2.index("card_reserved")


def test_old_key_without_a_counter_reads_as_one_card():
    from app.engine.pregame_push import _parse_sent

    assert _parse_sent(json.dumps({"lineup": "a", "verdict": "b"}))["n"] == 1
    assert _parse_sent("legacy-string")["n"] == 1
    assert _parse_sent(None) == {}


def test_final_verdict_gets_the_whole_card_not_a_lineup_diff():
    src = _src("app/engine/pregame_push.py")
    assert 'and not jg.get("final_verdict")' in src
    # [실사고 2026-09-02] 전체 카드라도 **무엇이 달라졌는지**는 남아야 한다.
    assert "라인업 diff %d건 첨부" in src


# ── ⑥ 최종 모델 ───────────────────────────────────────────────
def test_final_model_is_opus():
    from app.config import Settings

    assert Settings(_env_file=None).matchup_model == "claude-opus-5"


def test_opus_gets_no_temperature():
    """SDK 가 거절하는 인자를 보내지 않는다 — 모르면 안 보낸다."""
    from app.engine.team_form import _sampling_allowed

    assert _sampling_allowed("claude-opus-5") is False


# ═══════════════ [RJG-1 2026-09-08] 타순만 바뀌었는데 판정을 다시 돌렸다
#
# 🔴 운영 실측(경기 단위 `is_final`, 157경기, 기준 54.8%):
#      잠정            27경기  70.4%      ← 투수 재료만으로 낸 1차 판정
#      확정(재판정함)   130경기  51.5%
#      확률 이동 없음   48경기  62.5%  |  큼(>=0.10)  7경기  28.6%
#      우세가 뒤집힌 11경기 — 1차 7 맞음 / 최종 4 맞음   ← 같은 경기 안 비교
#      평균 이동 2.59%p · 중앙값 2.00%p · 이동 0인 경기 42건
#
#    이유는 **재료 비대칭**이다. 라인업이 확정되면 도착하는 것은
#      today_nine.order = [{"slot":1,"name":"度会 隆輝","pos":"左"}, …]
#    **이름과 포지션뿐, 숫자가 하나도 없다.** 투수 쪽은 개인 경기별 로그가 있다:
#      home_starter_recent = [{"innings":7.0,"r":1,"hits":4,"k":7,…}, ×5]
#    프롬프트가 그 빈자리를 "순서가 곧 정보다"로 메운다 — 숫자가 없으니 타순
#    순서에서 추론하라는 뜻이다. 그 추론이 확률을 흔들고, 흔들린 만큼 나빠진다.
#
# ⚠️ **순진하게 재판정을 끄면 추천이 영원히 0이 된다.** `form_card.rec_label` 이
#    `pick_state != "final"` 이면 무조건 보드만인데, `pick_state` 는
#    `rejudge_after_lineup` **안에서** 설정된다. 그래서 그 함수는 계속 돌리고
#    **안쪽 `_run_baseball_matchups` 호출만** 조건부로 만든다.


def _jg_with(p_claude, home_name, away_name):
    return {"sport": "kbo", "p_claude": p_claude,
            "research": {"home_pitcher": {"name": home_name},
                         "away_pitcher": {"name": away_name}}}


def test_타순만_바뀌면_판정을_다시_돌리지_않는다():
    """🔴 이 경우가 실측에서 판정을 나쁘게 만든 자리다."""
    from app.engine.pregame_push import needs_rejudge

    jg = _jg_with(0.58, "최원태", "하영민")
    ok, why = needs_rejudge(jg, {"home": "최원태", "away": "하영민"}, notes=[])
    assert ok is False, why
    assert "선발" in why


def test_선발이_바뀌면_다시_돌린다():
    from app.engine.pregame_push import needs_rejudge

    jg = _jg_with(0.58, "박세웅", "하영민")
    ok, why = needs_rejudge(jg, {"home": "최원태", "away": "하영민"}, notes=[])
    assert ok is True and "변경" in why


def test_선발이_새로_밝혀지면_다시_돌린다():
    """⚠️ NPB 는 선발 공시가 T-30 이다. 1차 판정이 선발을 모른 채 나갔다면
    라인업 확정이 **처음으로** 선발을 알려주는 순간이므로 반드시 재판정한다.

    🔴 기존 `starter_change_notes` 는 양쪽이 **다 있을 때만** 발화해서
       이 경우를 못 잡는다. 그래서 판별을 따로 둔다.
    """
    from app.engine.pregame_push import needs_rejudge

    jg = _jg_with(0.58, "최원태", "하영민")
    ok, why = needs_rejudge(jg, {"home": "", "away": "하영민"}, notes=[])
    assert ok is True and ("새로" in why or "확인" in why), why


def test_판정이_없으면_다시_돌린다():
    from app.engine.pregame_push import needs_rejudge

    jg = _jg_with(None, "최원태", "하영민")
    ok, why = needs_rejudge(jg, {"home": "최원태", "away": "하영민"}, notes=[])
    assert ok is True and "판정" in why


def test_불일치_통지가_오면_다시_돌린다():
    """`refresh_mlb_lineup` 이 statsapi 와 예고가 어긋났다고 알리는 경우."""
    from app.engine.pregame_push import needs_rejudge

    jg = _jg_with(0.58, "최원태", "하영민")
    ok, _ = needs_rejudge(jg, {"home": "최원태", "away": "하영민"},
                          notes=["home 선발 정보 불일치 — statsapi A vs 예고 B"])
    assert ok is True


def test_파이프라인이_그_판별로_판정을_가른다():
    """배선 — `rejudge_after_lineup` 이 `needs_rejudge` 로 판정을 감싼다."""
    src = (ROOT / "app" / "pipeline.py").read_text(encoding="utf-8")
    i = src.index("async def rejudge_after_lineup")
    seg = src[i:src.index("\nasync def ", i + 10)]
    j = seg.index("_run_baseball_matchups")
    assert "needs_rejudge" in seg[:j], "판정 앞에 판별이 없다 — 타순만 바뀌어도 돈다"


def test_최종_승격은_판별과_무관하다():
    """🔴 **추천이 죽지 않는 것을 잠근다.**

    `pick_state` 는 판정 여부와 상관없이 라인업 상태만 보고 정해져야 한다.
    이것이 깨지면 카드가 영원히 '🕐 잠정'이고 추천 자격을 못 얻는다.
    """
    from app.collectors.lineups import pick_state

    assert pick_state("confirmed")[0] == "final"
    src = (ROOT / "app" / "pipeline.py").read_text(encoding="utf-8")
    i = src.index("async def rejudge_after_lineup")
    seg = src[i:src.index("\nasync def ", i + 10)]
    ps = seg.index("pick_state(lineup[")
    nj = seg.index("needs_rejudge")
    assert ps < nj, "pick_state 승격이 판정 판별 뒤로 밀렸다 — 추천이 죽는다"


def test_건너뛸_때_조용하지_않다():
    """⚠️ 조용한 생략은 다음에도 아무도 모른다."""
    src = (ROOT / "app" / "pipeline.py").read_text(encoding="utf-8")
    i = src.index("async def rejudge_after_lineup")
    seg = src[i:src.index("\nasync def ", i + 10)]
    j = seg.index("needs_rejudge")
    assert "logger." in seg[j:j + 900], "생략을 로그로 남기지 않는다"
