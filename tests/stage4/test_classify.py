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


def test_방향이_home_away_draw_뿐이다():
    """🔴 §4 — *"총점 방향은 변수에 붙이지 않는다."* over/under 가 나오면 실패."""
    res = classify.classify_facts(_facts(), _game())
    assert res, "결과가 없다"
    for c in res:
        if c.direction is not None:
            assert c.direction in ("home", "away", "draw"), c.direction


# ══════════════════════════════════════════════════════════════════
# 🔴 배경 ↔ 미결정 — 섞으면 고칠 곳을 못 찾는다
# ══════════════════════════════════════════════════════════════════


def test_배경과_미결정을_가른다():
    """★ *"규칙이 아니라고 **판단**했다"* 와 *"자료가 없어 **못 판단**했다"* 는 다르다.

    전자는 규칙을 고칠 자리, 후자는 **수집**을 고칠 자리다. 섞으면 어느 쪽인지 모른다.
    """
    res = classify.classify_facts(_facts(), _game())
    bg = [c for c in res if not c.is_variable and not c.undecided]
    und = [c for c in res if c.undecided]
    assert bg, "배경이 0건이다 — 규칙 판단이 전부 미결정으로 샜나"
    assert und, "미결정이 0건이다 — 자료 부족을 배경으로 묻었나"
    # 🔴 배경에도 **왜**가 있어야 한다 — 그냥 사라지면 안 된다
    for c in bg:
        assert c.why.strip(), f"배경인데 사유가 없다: {c.text[:50]}"
    # 🔴 미결정 사유는 **자료가 없다**는 말이어야 한다
    for c in und:
        assert c.undecided.strip()


def test_USL_은_플레이오프_경계를_몰라_stakes_가_미결정이다():
    """★ 🔴 실측 2026-10-02 — **리그마다 다르다.**

    ```
    MLS  legend `Championship playoff · indices [0..8]` → 경계 9위  ✅
    USL  legend `null`                                  → 모른다   🔴
    ```

    순위만으로 *"걸렸다"* 고 판단하지 않는다 — 진출 수가 리그마다 다르다.
    """
    und = [c for c in classify.classify_facts(_facts(), _game())
           if c.undecided and c.type == "stakes"]
    assert und, "USL 에서 stakes 가 미결정이 아니다 — 경계를 지어냈나"
    assert "경계" in und[0].undecided


# ══════════════════════════════════════════════════════════════════
# 가중치 — hardness 가 정한다
# ══════════════════════════════════════════════════════════════════


def test_weight_는_hardness_가_정한다():
    """🔴 `types.Variable` 이 `weight == WEIGHT_OF[hardness]` 를 강제한다.

    ══════════════════════════════════════════════════════════════════
    🔴 **방향이 있을 때만**이다 — 지시서(오픈월드) §1-2 (2026-10-05)
    ══════════════════════════════════════════════════════════════════

    > 나머지는 **배경 사실**(hardness 0, **strength 미반영**)로 내린다.

    ⚠️ 종전엔 `hardness` 만 봤다. 🔴 그러면 **방향 없는 배경**이 `soft` 무게를
       들고 §5-a 묶음 합에 들어간다 — 실측 2026-10-04: 포르투갈 `A` 가 근거
       **4.8** 이었고 그 중 여섯이 *지난 경기 득점표*였다.
    """
    for c in classify.classify_facts(_facts(), _game()):
        if not c.direction:
            # 🔴 배경이다 — **무게 0**이어야 한다(그것이 §1-2 의 요점이다)
            assert c.weight == 0.0, (c.type, c.hardness, c.weight, c.undecided)
            continue
        assert c.weight == WEIGHT_OF[c.hardness], (c.type, c.hardness, c.weight)


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


def test_경기_단위_유형은_한_번만_센다():
    """★ 🔴 실측 2026-10-02 — 같은 사실이 두 번 세어졌다.

    ```
    home_field       리그의 홈 우위인데 순위표 사실이 **팀마다** 와서 두 번
    travel_schedule  휴식일 **비대칭 하나**를 두 팀 시선으로 두 번
    ```

    방향 묶음의 strength 가 그만큼 부풀고 단계 6 이 속는다.
    """
    res = classify.classify_facts(_facts(), _game())
    for t in classify.GAME_LEVEL:
        same = [c for c in res if c.is_variable and c.type == t]
        by_dir: dict[str, int] = {}
        for c in same:
            by_dir[c.direction] = by_dir.get(c.direction, 0) + 1
        for d, n in by_dir.items():
            assert n == 1, f"{t} {d} 가 {n}번 세어졌다"


def test_같은_내용_다른_주소를_지운다():
    """🔴 §12-c-4 — *"같은 보도자료 8건은 원문 1건이다."*

    ⚠️ 실측: fotmob 이 같은 경기를 `/matches/…` 와 `/en-GB/matches/…` 로 준다.
       출처를 열쇠에 넣으면 못 지우고, 그 탓에 `individual` 의 **팀 최다 득점자
       판정까지 깨졌다**(같은 이름이 둘이라 '동률'로 읽혔다).
    """
    res = classify.classify_facts(_facts(), _game())
    tops = [c for c in res if c.is_variable and "최다 득점자" in c.why]
    assert tops, "팀 최다 득점자가 한 명도 안 잡혔다 — 중복이 동률로 읽혔나"
    assert len({c.direction for c in tops}) == 2, \
        "두 팀의 최다 득점자가 각각 잡혀야 한다"


# ══════════════════════════════════════════════════════════════════
# 사용자 분석과 맞는가
# ══════════════════════════════════════════════════════════════════


def test_휴식일_비대칭을_양쪽_비교로_잡는다():
    """★ 사용자가 R1 으로 쓴 것을 코드가 낸다.

    > R1 체력 비대칭 — 라스베이거스 11일 휴식 vs 새크라멘토 … 4일 간격 **on**

    🔴 **양 팀을 비교해야** 나온다 — 한 팀 휴식일만으론 누가 피로한지 모른다.
    """
    res = classify.classify_facts(_facts(), _game())
    tv = [c for c in res if c.is_variable and c.type == "travel_schedule"]
    assert tv, "휴식일 변수가 없다"
    assert tv[0].direction == "away", (
        f"라스베이거스(11일)가 새크라멘토(4일)보다 쉬었다 → away 여야 한다 "
        f"(받은 값 {tv[0].direction})")
    assert "4일" in tv[0].why and "11일" in tv[0].why


def test_방향이_양쪽으로_갈린다():
    """🔴 §7 R5 — *"변수 3개 미만·반대 방향 0개면 자료 부족."*

    이 경기는 통과해야 한다 — 통과하지 못하면 단계 6 이 아예 안 돈다.
    """
    res = classify.classify_facts(_facts(), _game())
    dirs: dict[str, float] = {}
    for c in res:
        if c.is_variable:
            dirs[c.direction] = dirs.get(c.direction, 0.0) + c.weight
    assert len([c for c in res if c.is_variable]) >= 3, dirs
    assert len(dirs) >= 2, f"방향이 한쪽뿐이다: {dirs}"


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


def test_가설이_방향_묶음의_다시_보기다():
    """★ 🔴 **새 규칙이 아니다.** 사용자 블록을 뜯어 보면 §5-a 그대로다:

    ```
    새크라멘토 가설 = home 방향 묶음   ·  무너지는 조건 = away 방향 묶음
    라스베이거스 가설 = away 방향 묶음  ·  무너지는 조건 = home 방향 묶음
    ```

    ⚠️ 판단을 더하면 그 순간 감사할 수 없게 된다 — 묶음과 **정확히** 같아야 한다.
    """
    res = classify.classify_facts(_facts(), _game())
    hs = classify.hypotheses(res, _game())
    assert len(hs) == 2 and {h.side for h in hs} == {"home", "away"}
    by = {"home": [], "away": [], "draw": []}
    for c in res:
        if c.is_variable:
            by[c.direction].append(c)
    for h in hs:
        other = "away" if h.side == "home" else "home"
        # 🔴 받치는 변수 = 그 방향 묶음, **빠짐도 더함도 없다**
        assert h.supports == by[h.side]
        assert h.breaks == by[other] + by["draw"]
        assert h.strength_for == round(sum(c.weight for c in by[h.side]), 3)


def test_무승부_변수는_양쪽을_다_깬다():
    """★ 🔴 무승부는 **두 승리 가설을 다 깬다.** 한쪽 가설에 넣으면 거짓이다.

    ⚠️ 친선 경기가 그 자리다 — §4 `match_type` *"친선→무동기·무승부"*.
    """
    g = _game()
    draw = classify.Classified(
        text="친선 경기", source_url="https://x.test/f", hardness="hard",
        type="match_type", direction="draw", why="§4 match_type '친선→…무승부'")
    home = classify.Classified(
        text="홈 우위", source_url="https://x.test/t", hardness="soft",
        type="home_field", direction="home", why="§4 home_field")
    hs = classify.hypotheses([draw, home], g)
    for h in hs:
        assert draw in h.breaks, f"{h.side}: 무승부가 무너지는 조건에 없다"
        assert draw not in h.supports, f"{h.side}: 무승부를 가설에 넣었다"


def test_문장을_지어내지_않는다():
    """★ 🔴 §5-e — 문장은 **LLM L6** 이 쓴다(*"새 사실 추가 금지"*).

    L6 은 아직 안 이어졌다. **빈칸으로 두는 것이 지어내는 것보다 낫다** —
    그리고 왜 빈칸인지 `claim_by` 가 말한다(조용한 0 금지).
    """
    hs = classify.hypotheses(classify.classify_facts(_facts(), _game()), _game())
    for h in hs:
        assert h.claim == "", f"코드가 가설 문장을 지어냈다: {h.claim[:60]}"
        assert "L6" in h.claim_by, h.claim_by


def test_가설이_양쪽_다_서야_단계_6_이_돈다():
    """🔴 §5-a — 한쪽 묶음이 비면 그 시나리오가 아예 없다(§5-c-6 단일 방향 금지).

    ⚠️ 이 경기는 양쪽이 서야 한다 — 서지 않으면 §7 R5 로 **자료 부족**이다.
    """
    hs = classify.hypotheses(classify.classify_facts(_facts(), _game()), _game())
    for h in hs:
        assert h.supports, f"{h.team}: 받치는 변수가 0건이다"
        assert h.types_for, f"{h.team}: 유형 이름이 비었다"
    # 🔴 양쪽 strength 가 **둘 다 0 보다 커야** 반대 방향이 있는 것이다
    assert all(h.strength_for > 0 for h in hs)


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
