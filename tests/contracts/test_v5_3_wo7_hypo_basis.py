"""🔴🔴 **⑦ 가설 근거 검사** — 사용자 지시 2026-10-06.

> 가설 근거 검사: **표본 부족·검증 탈락으로 표시된 변수는 가설 근거에 못 쓴다.**
> 한 팀 근거가 0건이면 **"이긴다면" 문장 대신** "근거 변수 없음 — 반대 팀
> 가설이 무너지는 조건만" 경로로 쓴다.

══════════════════════════════════════════════════════════════════
🔴 왜 (실측 2026-10-06 · 북아일랜드–조지아 카드 원문)
══════════════════════════════════════════════════════════════════

```
Georgia: 근거 0건 · 깨는 변수 4건
    이긴다면: 최근 5경기에 승리를 포함해 반격 득점을 만들 수 있는 흐름이 있다(R4).
    이긴다면: 상대도 3일 휴식이라 체력 조건이 같아 후반으로 갈수록 승부가 열린다(R2).
```

🔴 R2·R4 는 **홈 쪽** 변수다. 근거가 0건인데 세 문장이 섰다.
그리고 `R1 [h2h_pattern·home·soft] … 맞대결 표본 1경기` 가 *"맞대결 전적이
앞서 있어 초반 기세를 잡는다"* 의 근거로 쓰였다 — **1경기**로 한 말이다.
"""
from __future__ import annotations

import inspect

from app import classify


def _game() -> classify.Game:
    return classify.Game(home="Northern Ireland", away="Georgia",
                         sport="soccer", league="UEFA Nations League B Grp. 2")


def _var(direction: str, *, thin: str = "", vtype: str = "recent_pattern"):
    return classify.Classified(
        text="x", source_url="https://x.test/1", hardness="soft",
        type=vtype, direction=direction, why="§4", thin_sample=thin)


def test_wo7_표본_부족_변수는_근거가_못_된다():
    """🔴 근거에서는 빠지고 **깨는 쪽에는 남는다**(주장의 세기가 다르다)."""
    thin = _var("home", thin=f"{classify.THIN_MARK} 맞대결 표본 1경기",
                vtype="h2h_pattern")
    solid = _var("home")
    away = _var("away")
    got = {h.side: h for h in classify.hypotheses([thin, solid, away], _game())}
    home = got["home"]
    assert solid in home.supports, "🔴 멀쩡한 변수가 근거에서 빠졌다"
    assert thin not in home.supports, (
        "🔴 **표본 1경기** 변수가 근거로 쓰였다(사용자 지시 2026-10-06 ⑦)")
    # 🔴 **버린 것을 이름으로 남긴다**(#3 조용한 0 금지)
    assert thin in home.thin_dropped, home.thin_dropped
    # 🔴 상대 가설의 **깨는 쪽**에는 그대로 있다
    assert thin in got["away"].breaks, got["away"].breaks


def test_wo7_표시는_글자_찾기가_아니라_칸이다():
    """🔴 D46 — `why` 에서 *"표본"* 을 찾으면 문장이 바뀔 때 조용히 안 걸린다.

    🔴 `_hardness_cap` 이 표본 때문에 깎을 때 **표식을 붙이고**, 호출부가 그것을
       칸으로 옮긴다. ⚠️ 그 둘이 다 돌아야 칸이 선다 — 돌려서 센다.
    """
    val = {"count": 1, "matches": [{}]}
    got, note = classify._hardness_cap("h2h_pattern", val, "hard")
    assert got != "hard", (got, note)
    assert classify.THIN_MARK in note, note
    # 🔴 표본과 **무관한** 깎임에는 표식이 없다
    _h2, note2 = classify._hardness_cap("home_field", {}, "soft")
    assert classify.THIN_MARK not in note2, note2


def test_wo7_근거_0건이면_이긴다면을_안_쓴다():
    """🔴🔴 **배선**(#2) — `_run_hypo` 가 `supports` 를 보고 끊어야 한다."""
    from app import analyze
    from tests._helpers import strip_docs
    src = strip_docs(inspect.getsource(analyze._run_hypo))
    assert "h.supports" in src, (
        "🔴 `_run_hypo` 가 `supports` 를 **안 본다** — 근거 0건인 팀에도 "
        "*이긴다면* 문장이 선다(실측 2026-10-06)")
    # 🔴 그리고 그때 `win_why` 를 **비운다**
    at = src.find("h.supports")
    seg = src[at:at + 400]
    assert "win_why" in seg and "[]" in seg, seg[:200]


def test_wo7_카드가_그_사실을_적는다():
    """🔴 #3 — 조용히 비우면 *"모델이 문장을 못 냈다"* 로 읽힌다."""
    from app import analyze
    from tests._helpers import strip_docs
    src = strip_docs(inspect.getsource(analyze))
    assert "근거 변수 없음" in src, (
        "🔴 카드가 *'근거 변수 없음 — 반대 팀 가설이 무너지는 조건만'* 을 "
        "안 적는다(사용자 지시 2026-10-06 ⑦)")
    assert "표본 부족으로 뺀 근거" in src, (
        "🔴 표본 부족으로 **무엇을 뺐는지** 안 적는다(#3)")
