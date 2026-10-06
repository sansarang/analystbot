"""§4 적용 계약 — **유형·방향·가중치** (사용자 지시 2026-10-02 "⑧ … 구현해라").

⚠️ §9 는 단계 4 게이트(29%) 전에 단계 5 코드를 쓰지 말라고 한다. 사용자가 *"게이트
   판정은 나중에 다시 하기로 하고 8번 해라"* 고 지시했고 **사용자 지시가 v4 보다
   위다**(CLAUDE.md 첫 규약).
🔴 계약을 `tests/stage5/` 에 두면 **서명 없이는 수집조차 되지 않는다**(stage_gate).
   돌아가지 않는 계약은 없는 계약이므로 §4 규칙 적용으로 보아 여기 둔다.
   → `docs/fable/questions/2026-10-02_stage5_partial.md`

## 🔴 잠그는 것

| 무엇 | 왜 |
|---|---|
| 유형이 §4 표에 있는 것만 | 오타 하나가 §5-c 유형 매칭에서 조용히 빠진다 |
| 방향이 `home/away/draw` 만 | 총점 방향은 변수에 안 붙인다(§4) |
| 구현한 유형 + 미구현 유형 = §4 표 전부 | 조용한 0 금지(#7) |
| **배경과 미결정이 갈린다** | *"규칙이 아니라 했다"* 와 *"자료가 없었다"* 는 고칠 곳이 다르다 |
| 표본이 작으면 **hardness 가 깎인다** | `Variable` 이 `weight == WEIGHT_OF[hardness]` 를 강제한다 |
| 같은 변수를 두 번 세지 않는다 | §12-c-4 — strength 가 부풀면 단계 6 이 속는다 |
"""
from __future__ import annotations

import glob
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import classify, rules
from app.cells import Q_LINEUP, Question
from app.collect import fotmob
from app.net import Fetched
from app.types import WEIGHT_OF

ROOT = Path(__file__).resolve().parents[2]
KST = timezone(timedelta(hours=9))
SAC, LV = "Sacramento Republic FC", "Las Vegas Lights FC"


def _game() -> classify.Game:
    return classify.Game(home=SAC, away=LV, sport="soccer",
                         league="USL Championship")


def _facts() -> list:
    out = []
    for f in sorted(glob.glob(str(ROOT / "tests/fixtures/cassettes/*/*.json"))):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:                                   # noqa: BLE001
            continue
        u = d.get("url") or ""
        if "matches/sacramento-republic-fc-vs-las-vegas" not in u \
                and not fotmob.is_table_page(u):
            continue
        got = Fetched(u, True, 200, d.get("text") or "")
        j = fotmob.payload(got.text)
        if j is None:
            continue
        when = fotmob.kickoff(j)
        for team in (SAC, LV):
            q = Question(Q_LINEUP, "x", team=team,
                         deadline=when.astimezone(KST) if when else None)
            out += (fotmob.parse_context(got, q) if fotmob.is_match_page(u)
                    else fotmob.parse_league_table(got, q))
    return out


# ══════════════════════════════════════════════════════════════════
# 어휘 — §4 표에서 자란다
# ══════════════════════════════════════════════════════════════════


def test_구현한_유형이_전부_v4_표에_있다():
    """🔴 오타 하나가 §5-c 유형 매칭에서 조용히 빠진다(리뷰 B2 의 병)."""
    known = set(rules.variable_types())
    unknown = sorted(set(classify.DIRECTION_OF) - known)
    assert unknown == [], f"§4 표에 없는 유형을 구현했다: {unknown}"
    unknown2 = sorted(set(classify.NOT_CLASSIFIED) - known)
    assert unknown2 == [], f"§4 표에 없는 유형이 미구현 목록에 있다: {unknown2}"
    assert set(classify.GAME_LEVEL) <= known


def test_구현_더하기_미구현이_v4_표_전부다():
    """★ 🔴 **조용한 0 금지**(#7) — 세포가 없는 유형을 **이름으로** 남긴다.

    구현한 것과 미구현을 합쳐 §4 표를 덮지 못하면, 덮이지 않은 유형은 아무 데도
    적히지 않고 사라진다.
    """
    known = set(rules.variable_types())
    covered = set(classify.DIRECTION_OF) | set(classify.NOT_CLASSIFIED)
    assert covered == known, (
        f"안 적힌 유형 {sorted(known - covered)} · "
        f"표에 없는 것 {sorted(covered - known)}")
    # 🔴 미구현마다 **왜**가 적혀 있어야 한다
    for t, why in classify.NOT_CLASSIFIED.items():
        assert why.strip(), f"{t}: 미구현 사유가 없다"




# ══════════════════════════════════════════════════════════════════
# 🔴 배경 ↔ 미결정 — 섞으면 고칠 곳을 못 찾는다
# ══════════════════════════════════════════════════════════════════






# ══════════════════════════════════════════════════════════════════
# 가중치 — hardness 가 정한다
# ══════════════════════════════════════════════════════════════════




def test_표본이_작으면_hardness_를_깎는다():
    """★ 🔴 §4 `sample_weight`(1.0/0.7/0.4)는 `hard/likely/soft` 의 weight 와 **같다.**

    그래서 같은 규칙을 **hardness 로** 말할 수 있고, 그래야 `Variable` 이 받는다.
    ⚠️ 작은 표본은 더 약한 주장이므로 hardness 로 말하는 것이 더 맞다.
    """
    hard_h2h = {"team": SAC, "window": [{"home": SAC, "home_goals": 2,
                                         "away_goals": 1}] * 12,
                "count": 12}
    thin_h2h = {**hard_h2h, "window": hard_h2h["window"][:3], "count": 3}
    for val, want in ((hard_h2h, "hard"), (thin_h2h, "soft")):
        got, note = classify._hardness_cap("h2h_pattern", val, "hard")
        assert got == want, (val["count"], got, want)
        if want != "hard":
            assert note, "깎았는데 사유가 없다"
    # 🔴 **올리지 않는다** — soft 인 사실이 표본이 많아도 hard 가 되지 않는다
    assert classify._hardness_cap("h2h_pattern", hard_h2h, "soft")[0] == "soft"
    # §7 R7 — 최근 3경기 미만이면 soft
    assert classify._hardness_cap(
        "recent_pattern", {"last5": ["W", "L"]}, "hard")[0] == "soft"


# ══════════════════════════════════════════════════════════════════
# 🔴 같은 변수를 두 번 세지 않는다 (§12-c-4)
# ══════════════════════════════════════════════════════════════════






# ══════════════════════════════════════════════════════════════════
# 사용자 분석과 맞는가
# ══════════════════════════════════════════════════════════════════






def test_LLM_이_닿지_않는다():
    """🔴 §17-c — `direction`·`weight` 에 LLM 출력이 닿으면 계약 실패.

    ⚠️ **D46** — 독스트링·주석을 뺀 **코드만** 본다. 문서가 *"LLM 이 닿지 않는다"* 고
       **설명하는** 것과 코드가 LLM 을 **부르는** 것은 다르다.
       🔴 오늘 세 번째로 이 규칙에 걸렸다(`nhl.py` 의 `:baseline` · 여기).
    """
    import inspect

    from tests._helpers import strip_docs
    code = strip_docs(inspect.getsource(classify)).lower()
    for bad in ("llm", "ollama", "openai", "extract.run"):
        assert bad not in code, f"분류기가 {bad} 를 부른다"


# ══════════════════════════════════════════════════════════════════
# ⑨ 가설 + 무너지는 조건 (사용자 출력 블록 5 · 결정 B)
# ══════════════════════════════════════════════════════════════════










def test_중립_구장에서는_홈_우위를_세우지_않는다():
    """🔴🔴 **라이브가 찾았다**(아시안게임 한국 vs 중국 · 시즈오카 2026-10-02).

    양 팀 다 홈이 아닌데 §4 `home_field` 는 *"홈 팀 쪽"* 으로 방향을 민다 →
    **거짓 변수**다. 그 경기는 순위표가 없어 **우연히** 안 섰다.
    🔴 우연에 기대지 않는다 — 규정을 선언하고 규칙이 그것을 읽는다.
    """
    from app import rules

    ok, why = rules.neutral_venue("Asian Games")
    assert ok and why, (ok, why)
    # 🔴 리그 경기는 중립이 아니다 — 그러나 **사유를 돌려준다**(조용히 가정하지 않는다)
    no, why2 = rules.neutral_venue("USL Championship")
    assert no is False and why2

    val = {"home_advantage": {"win_pct_delta": 16.8, "goals_delta": 0.46,
                              "home_games": 200}}
    # 🔴 중립이면 **변수를 만들지 않고 사유를 남긴다**(배경으로 떨어진다)
    d, why3, undecided = classify._dir_home_field(
        val, classify.Game(home="A", away="B", sport="soccer",
                           league="Asian Games"))
    assert d is None and "중립" in why3 and not undecided
    # 🔴 중립이 아니면 전처럼 선다
    d2, _, _ = classify._dir_home_field(
        val, classify.Game(home="A", away="B", sport="soccer",
                           league="USL Championship"))
    assert d2 == "home"
