"""🔴🔴 **v5 게이트 3 — 지어낸 변수 주입.** 가짜 `quote` **10건이 전부 폐기**돼야.

§10-4 게이트 3 원문:

> §5 검증층 → **지어낸 변수 주입 테스트(가짜 quote 10건)가 전부 폐기됨**

══════════════════════════════════════════════════════════════════
🔴 이 게이트는 **정답지가 필요 없다** — 그래서 지금 기계가 답할 수 있다
══════════════════════════════════════════════════════════════════

⚠️ 게이트 2·4·5 는 정답지에 기대어 **기준을 잃었다**(결정 C). 🔴 이 게이트는
   다르다: 가짜를 **우리가 만들어 넣는다.** 견줄 정답이 필요 없고, 물음은
   하나다 — *"검증층이 그것을 전부 거절하나."*

🔴 **열 건을 서로 다른 방식으로** 지어낸다. ⚠️ 같은 꼴 열 번은 **한 건**이다
   (한 가지만 막아도 10/10 이 된다).

🔴 **§10-4 게이트 3** — 이 계약이 그 칸을 기계가 답할 수 있게 만든다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

KICK = datetime.now(timezone.utc) + timedelta(hours=2)
BODY = ("Milwaukee Brewers manager Pat Murphy said Logan Henderson will start "
        "on Saturday against the San Diego Padres. The club confirmed the "
        "rotation plan after Friday's workout.")
URL = "https://www.mlb.com/brewers/news/rotation"


def _ctx(**kw):
    from app import verifylayer
    base = {
        "home": "team:000338", "away": "team:000325",
        "home_names": ["Milwaukee Brewers", "Brewers"],
        "away_names": ["San Diego Padres", "Padres"],
        "competition": "MLB", "roster": ["Logan Henderson", "Pat Murphy"],
        "kickoff": KICK, "bodies": {URL: BODY},
    }
    base.update(kw)
    return verifylayer.Context(**base)


def _var(**kw):
    """🔴 **통과할 수 있는** 변수 하나. 주입은 여기서 한 칸만 비튼다."""
    from app import agentschema
    base = {
        "id": "A1", "type": "pitcher_state", "team": "team:000338",
        "direction_hint": "home", "claim": "선발이 바뀐다",
        "quote": "Logan Henderson will start",
        "url": URL, "published_at": KICK - timedelta(hours=20),
        "lang": "en",
    }
    base.update(kw)
    return agentschema.AgentVar(**base)


#: 🔴🔴 **열 가지 지어내기.** ⚠️ 서로 **다른 방식**이어야 한다 — 같은 꼴 열 번은
#  한 건이고, 한 가지만 막아도 10/10 이 된다.
FAKES: list[tuple[str, dict]] = [
    # ① 아예 없는 말을 인용한다
    ("없는 인용", {"quote": "Henderson is out for the season"}),
    # ② 본문의 말을 **바꿔** 적는다(한 낱말)
    ("바꾼 인용", {"quote": "Logan Henderson will not start"}),
    # ③ 본문을 **안 받아 둔** 주소를 댄다
    ("안 받은 본문", {"url": "https://example.com/never-fetched"}),
    # ④ **남의 경기** 기사다(다른 대회)
    ("다른 대회", {"quote": "noncommittal about his WBC participation",
                   "claim": "WBC 참가 여부"}),
    # ⑤ 발행이 **킥오프 뒤**다
    ("킥오프 뒤", {"published_at": KICK + timedelta(hours=1)}),
    # ⑥ **너무 낡았다**(창 밖)
    ("낡은 기사", {"published_at": KICK - timedelta(days=30)}),
    # ⑦ **tip 등급** 도메인이다(§5-5: 변수가 못 된다)
    # 🔴 등급은 **도메인 표**가 정한다(`tier` 칸을 변수가 들고 있지 않다)
    ("tip 도메인", {"url": "https://www.forebet.com/en/predictions"}),
    # ⑧ **남의 팀** 열쇠를 붙인다
    ("남의 팀", {"team": "team:999999"}),
    # ⑨ 인용이 **비어 있다**
    ("빈 인용", {"quote": ""}),
    # ⑩ 발행 시각이 **없다**
    ("발행 없음", {"published_at": None}),
]


def test_v5_10_3_주입_열_건이_서로_다르다():
    """🔴 같은 꼴 열 번은 **한 건**이다 — 한 가지만 막아도 10/10 이 된다.

    ══════════════════════════════════════════════════════════════════
    🔴 **다양성을 무엇으로 재나** — 칸이 아니라 **사유**다
    ══════════════════════════════════════════════════════════════════

    ⚠️ 처음에 *"비트는 칸이 달라야 한다"* 로 쟀다. 🔴 그것은 틀린 자다:
       `quote` 한 칸을 비틀어도 *"없는 인용"* 과 *"바꾼 인용"* 은 **다른 길**로
       잡힐 수 있고, `published_at` 한 칸이 *"킥오프 뒤"* 와 *"너무 낡았다"* 라는
       **다른 사유**를 낸다.
    🔴 그래서 **검증층이 돌려주는 사유 가짓수**를 센다 — 그것이 *"여러 가지
       방어가 실제로 일하고 있나"* 다.
    """
    from app import verifylayer
    assert len(FAKES) == 10, len(FAKES)
    reasons = {verifylayer.verify_one(_var(**kw), _ctx())[1] for _, kw in FAKES}
    assert len(reasons) >= 5, (
        f"🔴 주입 열 건이 **{len(reasons)}가지 사유**로만 잡힌다 — 방어 하나만 "
        f"막아도 10/10 이 된다: {sorted(r.value for r in reasons)}")


@pytest.mark.parametrize(("name", "kw"), FAKES, ids=[n for n, _ in FAKES])
def test_v5_10_3_지어낸_변수는_폐기된다(name, kw):
    """🔴🔴 **게이트 3** — 가짜 열 건이 **전부** 폐기돼야 한다."""
    from app import verifylayer
    ok, reason, why = verifylayer.verify_one(_var(**kw), _ctx())
    assert ok is False, f"🔴 `{name}` 가 **통과했다** — {reason} · {why}"
    # 🔴 그리고 **왜 폐기했나**가 사유 enum 으로 와야 한다(§8-6)
    from app.reasons import Reason
    assert reason is not Reason.OK, name
    assert str(why).strip(), name


def test_v5_10_3_통과할_수_있는_변수는_통과한다():
    """🔴🔴 **반대 증거** — 전부 거절하는 검증층은 **아무것도 증명하지 않는다.**

    ⚠️ 주입 열 건이 전부 빨개지는 가장 쉬운 방법은 `return False` 다. 🔴 그래서
       *"지어내지 않은 변수는 통과한다"* 를 함께 본다.
    """
    from app import verifylayer
    from app.reasons import Reason
    ok, reason, why = verifylayer.verify_one(_var(), _ctx())
    assert ok is True, f"🔴 진짜 변수가 폐기됐다 — {reason} · {why}"
    assert reason is Reason.OK


def test_v5_10_3_열_건_전부를_한_번에_센다():
    """🔴 게이트 3 은 *"**전부** 폐기됨"* 이다 — 수를 **세어** 보고한다.

    ⚠️ 한 건이라도 통과하면 그 게이트는 실패다(부분 통과가 없다).
    """
    from app import verifylayer
    passed = [name for name, kw in FAKES
              if verifylayer.verify_one(_var(**kw), _ctx())[0]]
    assert passed == [], (
        f"🔴 **게이트 3 실패** — 지어낸 변수 {len(passed)}/10 건이 통과했다: "
        f"{passed}")
