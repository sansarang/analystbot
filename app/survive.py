"""§6 생존 계산·보드·등급 — **수동 12단계의 ⑪**.

사용자 지시 2026-10-02: *"11부터 가라"* · *"최종 목표는 니가 수동으로 돌려던 거를
자동화 하는 거다"*.

## 🔴 이 파일이 하는 일 하나

마켓마다 **각 시나리오의 스코어를 대입**해서 `○ / △ / ✗` 를 매기고,
`survival = Σ(○ 무게 + △ 무게×통과비율) ÷ Σ 무게` 를 센다(§6-a).
등급은 **수가 정한다** — `survival` 1.0 → 낸다 · 0.8 이상 → 소액 · 그 미만 → 이름
없음(§6-b). 🔴 **고르는 사람이 없다.** `types.MarketSurvival` 이 그것을 검증한다.

## 🔴 두 수를 나란히 낸다 — 내가 전 판에 틀렸던 자리

전 판 생존은 **덮은 확률 안에서만** 정규화됐다(실측 0.67). 그러면 *"전부 따졌다"* 로
읽힌다. 나는 사용자에게 *"분모를 1.0 으로 두고 안 덮인 결과는 살지 않는다고 보자"*
고 말했다. 🔴 **그 말이 틀렸다** — 안 덮인 스코어는 *모르는 결과*가 아니다.
`3-0` 은 어느 시나리오에도 없지만 **총점 2.5 오버인지 아닌지는 정확히 안다.**

그래서 이렇게 한다:

| 수 | 식 | 뜻 |
|---|---|---|
| `survival` | §6-a 그대로 — 시나리오 무게의 통과 비율 | *"내가 세운 이야기들 중 몇이 살아남나"* — **등급은 이것이 정한다**(v4) |
| `p_market` | **격자 전체**에서 그 마켓이 맞을 확률 | *"실제로 맞을 확률"* — 지어낸 수가 아니라 포아송 격자 |

🔴 둘이 크게 벌어지면 **경고를 남긴다.** `survival 1.0` 이 덮은 67% 안의 1.0 이라는
사실을 숨기면 그것이 과신이다(§11-3).
⚠️ 등급 체계를 바꾸지 않았다 — §6-b 의 `1.0 / 0.8` 은 *"모든 시나리오에서 살아남나"*
   라는 **견고성** 기준이고 확률 문턱이 아니다. 바꾸는 것은 사용자 결정이다.

## 🔴 배당은 들어오지 않는다

§1·§6-c-5·§7 R8: 보드는 *"어떤 마켓과 기준선이 있는가"* 만 읽는다. 이 파일은
`types.Market` 만 받고 그 스키마에는 **가격 칸이 없다.**
"""
from __future__ import annotations

import logging
import re

from app import league, rules, thresholds
from app.types import (BTTS_SIDES, NAME_AT, SMALL_AT, Market, MarketSurvival,
                       Survival, Verdict)

logger = logging.getLogger(__name__)

#: §6-a 표기. 🔴 **사람이 읽는 기호가 원본이다** — 카드가 이것을 그대로 쓴다.
PASS, FAIL, PART = "○", "✗", "△"

#: 🔴 `btts` 의 두 쪽. 원본은 `types.BTTS_SIDES` 다 — 여기서 글자를 다시 적지 않는다.
BTTS_YES, BTTS_NO = BTTS_SIDES
BTTS_YES_NO = BTTS_SIDES

#: 승패 묶음. 🔴 `handicap`·`total` 은 기준선이 있어야 하므로 따로 본다.
WIN_MARKETS = ("home", "draw", "away", "home_dc", "away_dc")

#: 🔴 **손익분기.** `p_market` 이 이보다 낮으면 **이름을 적지 않는다**(아래 veto).
#
#  ⚠️ 사용자 지시 2026-10-02 로 정한 것이고, **지어낸 값이 아니다** — 두 쪽 마켓의
#     손익분기점이다. 0.5 아래는 *"맞을 확률보다 틀릴 확률이 큰 자리에 이름을
#     적는다"* 는 뜻이고, 그것은 §0 (*"전부 살아남는 마켓만 낸다"*)과 정면으로
#     어긋난다.
#  🔴 실측(실측 경기(새크라멘토 vs 라스베이거스))이 이 veto 가 필요한 까닭을 보여 준다:
#       Las Vegas +1.5  survival 0.8503(소액)  ↔  격자 확률 0.6146
#     생존은 소액을 내라고 하는데 실제로 맞을 확률은 61% 다. 그 간격은 시나리오가
#     분포를 덜 덮어서 생기고, veto 가 그 자리를 막는다.
BREAK_EVEN = 0.5

#: §1 — `total(over/under, 기준선)`. 그 **over/under 가 `team` 칸에 온다.**
#  ⚠️ v4 §1 이 마켓의 칸을 `market_type`·`team`·`line` 셋으로 못 박았고 총점의
#     방향을 담을 다른 칸이 없다. `types.Market` 이 그것을 강제한다.
OVER, UNDER = "over", "under"


def _score(score: str) -> tuple[int, int] | None:
    """`"3-1"` → `(3, 1)`. 🔴 못 읽으면 `None` — 0 으로 때우지 않는다."""
    m = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*$", str(score or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _side(market: Market, home: str, away: str) -> str | None:
    """핸디의 `team` 이 홈인가 원정인가. 🔴 못 가리면 `None`(계산하지 않는다)."""
    from app import verify
    name = (market.team or "").strip()
    if not name:
        return None
    if verify.mentions_team(home, name, None) or verify.mentions_team(name, home, None):
        return "home"
    if verify.mentions_team(away, name, None) or verify.mentions_team(name, away, None):
        return "away"
    return None


def passes(market: Market, score: str, *, home: str = "", away: str = "",
           sport: str = "") -> bool | None:
    """이 스코어에서 그 마켓이 맞나. 🔴 **판단할 수 없으면 `None`.**

    ⚠️ `None` 을 `False` 로 때우면 *"틀렸다"* 가 되고 생존이 내려간다 — 못 읽은
       것과 틀린 것은 다르다(조용한 0 금지).
    """
    got = _score(score)
    if got is None:
        return None
    h, a = got

    # 🔴 §6-a — 연장 규정이 있는 리그의 `n-n` 은 승패 마켓에서 **보수적으로 ✗**.
    #    ⚠️ 북 규정을 확인하지 못했으므로 유리한 쪽으로 읽지 않는다.
    if sport == "baseball" and h == a and market.market_type in WIN_MARKETS:
        return False

    if market.market_type == "home":
        return h > a
    if market.market_type == "away":
        return a > h
    if market.market_type == "draw":
        return h == a
    if market.market_type == "home_dc":
        return h >= a
    if market.market_type == "away_dc":
        return a >= h
    if market.market_type == "handicap":
        side = _side(market, home, away)
        if side is None or market.line is None:
            return None
        # 🔴 **더하는 꼴로 센다.** 전에 `a - h < 2` 로 적었더니 `+1.5` 가 `2-0` 을
        #    통과시켰다. 기준선은 그 팀 점수에 더하는 값이다.
        mine, theirs = (h, a) if side == "home" else (a, h)
        return (mine + float(market.line)) > theirs
    if market.market_type == "btts":
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **양팀득점**(사용자 지적 2026-10-03) — 보드에 그 마켓이 없었다
        # ══════════════════════════════════════════════════════════════
        #
        #  사용자가 손으로 쓴 보드: *"양팀득점: B(1-1) C○ A D✗ — 없음"*.
        #  🔴 승패·핸디·총점으로는 **못 말하는 것**이다 — 0-0 과 2-0 은 총점이
        #     다르지만 양팀득점은 둘 다 `아니오` 다.
        #  ⚠️ 밀어내기가 없다 — 두 쪽이 **정확한 여집합**이다.
        if market.team not in BTTS_YES_NO:
            return None
        both = h > 0 and a > 0
        return both if market.team == BTTS_YES else (not both)
    if market.market_type == "total":
        if market.line is None or market.team not in (OVER, UNDER):
            return None
        tot = h + a
        # ⚠️ 정수 기준선이면 **밀어내기(push)** 가 있다 — 이기는 것이 아니므로 ✗.
        if tot == float(market.line):
            return False
        return tot > float(market.line) if market.team == OVER else \
            tot < float(market.line)
    return None


def from_dist(market: Market, dist: dict, *, home: str = "", away: str = "",
              sport: str = "") -> float:
    """🔴🔴 **F5** — 그 줄의 생존을 **시뮬 분포에서 바로** 센다.

    > ⑭ 생존은 ⑪ 스코어 분포에서 **직접** 계산. 시나리오와 필수형 보강 갈래는
    > **표시용** — 생존 계산에 안 쓴다.  — 지시서 2026-10-11 F5

    `dist` 는 `{(홈, 원정): 확률}`(`sim.run` 산출 · `ProbOut.scores`)이다.
    🔴 줄 하나를 읽는 규칙은 `apply` **하나**다(사본 금지) — 스코어마다 그것을
       부르고 확률로 가중해 더한다.
    ⚠️ **못 읽은 스코어는 분모에서 뺀다** — `False` 로 세면 생존이 거짓으로
       내려간다(#3). 다 못 읽으면 `0.0` 이 아니라 그 사실이 분모 0 으로 남는다.
    """
    hit, mass = 0.0, 0.0
    for key, prob in dict(dist or {}).items():
        try:
            h, a = (int(key[0]), int(key[1])) if not isinstance(key, str) else (
                int(str(key).split("-")[0]), int(str(key).split("-")[1]))
        except (TypeError, ValueError, IndexError):
            continue
        sym, ratio, _bad = apply(market, [f"{h}-{a}"], home=home, away=away,
                                 sport=sport)
        if sym == "?":
            continue
        mass += float(prob)
        hit += float(prob) * float(ratio)
    return round(hit / mass, 6) if mass else 0.0


def apply(market: Market, scores: list[str], *, home: str = "", away: str = "",
          sport: str = "", probs: dict | None = None) -> tuple[str, float, int]:
    """§6-a — 스코어 집합 하나를 대입한다.

    돌려주는 것: `(기호, 통과비율, 못_읽은_개수)`.
    🔴 전부 통과 `○` · 전부 실패 `✗` · 섞이면 `△`(통과 비율만큼 부분 인정).
    ⚠️ **못 읽은 스코어는 분모에서 뺀다** — `False` 로 세면 생존이 거짓으로 내려간다.
       한 집합이 통째로 안 읽히면 `(△, 0.0, n)` 이 아니라 **기호를 `"?"`** 로 낸다.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **통과 "비율"을 개수가 아니라 확률로 센다** (사용자 지시 2026-10-02)
    ══════════════════════════════════════════════════════════════════

    §6-a 원문은 *"통과 비율만큼 strength 를 부분 인정"* 이다. 전 판은 그 비율을
    **스코어 개수**로 셌다 — `2-1` 과 `1-0` 을 똑같이 반반으로 봤다.
    🔴 **그 둘은 똑같이 그럴듯하지 않다.** 실측(실측 경기(새크라멘토 vs 라스베이거스), 포아송 격자):
        P(2-1) 0.0988 · P(1-0) 0.0856  →  오버 2.5 비율 **0.536**(개수로는 0.5)
    격자는 이미 있다 — 안 쓰고 개수로 세는 것이 조용한 근사였다.
    ⚠️ 격자가 없으면 **개수로 돌아간다**(그 사실이 호출부 기록에 남는다).
    """
    seen = [(s, passes(market, s, home=home, away=away, sport=sport))
            for s in scores]
    bad = sum(1 for _, v in seen if v is None)
    ok = [(s, v) for s, v in seen if v is not None]
    if not ok:
        return "?", 0.0, bad
    grid = (probs or {}).get("scores") or {}
    mass = {s: grid.get(s) for s, _ in ok}
    if grid and all(v is not None for v in mass.values()) and sum(mass.values()) > 0:
        ratio = sum(mass[s] for s, v in ok if v) / sum(mass.values())
    else:
        ratio = sum(1 for _, v in ok if v) / len(ok)
    # 🔴 **경계를 확률로 흐리지 않는다** — 전부 통과면 ○, 전부 실패면 ✗ 다.
    #    ⚠️ 확률 가중을 쓰면 반올림으로 0.9999 가 나올 수 있다. 통과·실패의
    #       **개수**로 기호를 정하고 **크기**만 확률로 센다.
    n_pass = sum(1 for _, v in ok if v)
    if n_pass == len(ok):
        return PASS, 1.0, bad
    if n_pass == 0:
        return FAIL, 0.0, bad
    return PART, round(ratio, 4), bad


# ══════════════════════════════════════════════════════════════════
# 무게 — 🔴 확률이 있으면 확률, 없으면 §5-d
# ══════════════════════════════════════════════════════════════════


#: 🔴🔴 **무게 바닥** — 지시 ① (2026-10-05). `strength 0` 인 시나리오가 생존
#   계산에서 **사라지지 않게** 한다.
#
#  ⚠️ 실측 pn8: `G`(strength 0)가 분모에서 빠져 `언더 3.5` 가 **1.0** 이 됐고,
#     같은 카드의 표는 그 갈래에서 **죽는다**고 그렸다.
#  🔴 바닥은 *"근거가 없다"* 를 뜻한다 — **그 갈래가 없다는 뜻이 아니다.**
WEIGHT_FLOOR = 0.1


def weights(drafts: list) -> tuple[dict[str, float], str]:
    """시나리오별 무게와 **무엇으로 쟀는지**.

    🔴 `scenario_weight` 선언이 원본이다(`config/scenario_rules.yaml`):
       확률이 1순위 · 격자를 못 만들면 §5-d 변수 weight 합.
    ⚠️ **섞지 않는다** — 하나라도 확률이 없으면 전부 `strength` 로 간다. 분자·분모에
       확률과 근거 개수가 섞이면 그 비는 어떤 뜻도 갖지 않는다.
    """
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **변수가 생존을 정한다** — 사용자 결정 2026-10-04
    # ══════════════════════════════════════════════════════════════════
    #
    #  > v4 §5-a 는 **시나리오 strength = 변수 weight 합**이라고 적혀 있다.
    #  > 포아송 격자는 **v4 에 없는 봇의 추가물**이고, 순위표에서 나오니 변수와
    #  > 무관할 수밖에 없다 … 변수 → strength, 격자 → **스코어를 고르는 도구로만**.
    #  > 이렇게 하면 §0 의 "변수 개수·정확도 = 시나리오 품질" 이 코드에서 참이 된다.
    #  > **지금은 변수가 장식이다.**
    #
    #  ⚠️ 종전에는 **격자 확률이 1순위**였다. 그래서 봇이 카드에 스스로 적었다:
    #     *"변수 3개가 근거는 바꾸는데 등급은 하나도 안 바꾼다."* 그 줄이 맞았다.
    #  🔴 격자는 **지우지 않았다** — `p_market`(실제로 맞을 확률)과 스코어 고르기와
    #     커버리지 경고로 계속 쓴다. 생존의 분자·분모만 아니다.
    cfg = rules.scenario_weight()
    mode = f"strength(v4 §5-a — {cfg['weight']})"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **무게 0 인 시나리오도 분모에 남는다** — 지시 ① (2026-10-05)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 pn8: `G`(대량득점형 · 3-1·2-2)의 `strength` 가 **0.0** 이었다.
    #     🔴 그래서 분자·분모에서 **통째로 사라지고** `언더 3.5` 가 A 에서만
    #     살아 **9.6/9.6 = 1.0** 이 됐다 — 그런데 카드 표는 `G` 에서 **죽는다고
    #     그렸다.** **그림과 수가 어긋났다.**
    #
    #  🔴 사용자 지시: *"**strength 0 시나리오도 생존 계산에서 빠지지 않는다.**"*
    #  ⚠️ 그래서 **바닥 무게**를 준다 — 0 이면 `FLOOR` 다. 그 수는 *"근거가
    #     없다"* 를 뜻하지만 **그 갈래가 없다는 뜻은 아니다**(일어날 수 있다).
    #  🔴 수를 **여기 하나**에 둔다. ⚠️ `0.4`(축구 무승부 바닥)와 같은 뜻의
    #     수를 쓰지 않는다 — 그것은 §5-a 가 정한 **다른** 바닥이다.
    out: dict[str, float] = {}
    floored: list[str] = []
    for d in drafts:
        got = float(d.strength or 0.0)
        if got <= 0:
            got = WEIGHT_FLOOR
            floored.append(str(d.id))
        out[d.id] = got
    if floored:
        mode += (f" · 🔴 무게 0 인 시나리오 {floored} 에 바닥 "
                 f"{WEIGHT_FLOOR:g} 을 줬다(지시 ① — 빠지면 거짓 1.0 이 난다)")
    return out, mode


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **§6-8 — 등급·결론 어휘 다섯**
# ══════════════════════════════════════════════════════════════════
#
#  > 등급은 **1.0 낸다 / 0.85·0.9 소액 / 0.8 소액 하단 / 그 아래 없음 /
#  > 자료 부족.**  (§11-3 기본값 표도 같은 다섯을 적었다)
#
#  ⚠️ 종전에 `analyze` 가 이렇게 적고 있었다:
#
#      word = "낸다" if r["verdict"] == "name" else "소액"
#
#  🔴 그 한 줄에 **두 결함**이 있었다:
#     ① `0.8`(소액 **하단**)과 `0.9`(소액)가 **같은 글자**를 받는다 — 상한에
#        걸려 내려온 마켓과 바닥에서 간신히 선 마켓이 카드에서 안 갈린다.
#     ② 어휘가 **코드에 박혀 있다**(§6-8 은 경계값을 yaml 에 두라고 했다).
#
#  🔴 `Verdict`(`name`/`small`/`none`)는 **DB 에 쌓이는 값**이라 그대로 둔다 —
#     쌓인 행의 뜻을 바꾸면 원장이 거짓이 된다(§3 불변). 어휘는 **표시**다.
WORD_NAME = "낸다"
WORD_SMALL = "소액"
WORD_SMALL_LOW = "소액 하단"
WORD_NONE = "없음"
#: 🔴 수가 아니다 — 변수가 모자라 **애초에 등급을 매길 수 없는** 상태(§7 R5).
#  ⚠️ `없음`(재 봤는데 안 섰다)과 섞으면 *"우리가 안 했다"* 와 *"해 봤는데
#     없다"* 가 한 글자가 된다(§8-6 이 막는 섞임이다).
WORD_NOT_ENOUGH = "자료 부족"


def verdict_words() -> tuple[str, ...]:
    """🔴 §11-3 표가 이름으로 댄 **다섯**. 순서가 센 쪽부터다."""
    return (WORD_NAME, WORD_SMALL, WORD_SMALL_LOW, WORD_NONE, WORD_NOT_ENOUGH)




def cap_for(state: str) -> float:
    """🔴 그 라인업 상태의 **등급 상한** — 지시 ② (2026-10-05).

    > `lineup_state` 가 `confirmed` 가 아니면 **"낸다"(1.0) 금지**.

    ⚠️ 칸 이름은 `config/thresholds.yaml` 이 든다(`xi_state_cap`). 🔴 영어 이름
       (`confirmed`·`baseline`·`predicted`)은 **그 표의 한국어 칸으로** 옮긴다 —
       표를 두 벌 만들지 않는다(사본 금지).
    🔴 **모르면 가장 센 상한**이다(fail-closed) — 모르는데 푸는 것은 우리에게
       유리한 쪽으로 거짓말하는 것이다.
    """
    caps = {str(k): float(v)
            for k, v in (rules.xi_state_cap().get("caps") or {}).items()}
    said = str(state or "").strip()
    # 🔴 **표의 칸이 이긴다** — 여섯 칸이 있다(`양쪽예상`·`선발확정_타순미공개`…).
    #    ⚠️ 실사고 2026-10-05: 여기 세 칸만 손으로 적어 두어 `양쪽예상`(0.85)이
    #       `없음`(0.8)으로 **깎였다** — 사본은 표가 자랄 때 따라가지 않는다(#1).
    if said in caps:
        return caps[said]
    # 영어 이름만 표의 칸으로 **옮긴다**(수는 안 적는다)
    key = {"confirmed": "양쪽확정", "half": "한쪽확정",
           "predicted": "양쪽예상"}.get(said.lower())
    if key and key in caps:
        return caps[key]
    # 🔴 `baseline`·`unknown`·빈 값 — **확정이 아니다**. 모르면 가장 센 상한
    #    (fail-closed) — 모르는데 푸는 것은 우리에게 유리한 거짓말이다.
    return min(caps.values()) if caps else 0.8


def dead_marks(marks: dict, ids: list) -> list[str]:
    """🔴🔴 **죽는 시나리오 목록** — `✗` 와 `△` 를 **둘 다**(지시서 §2-1).

    > *"죽는 시나리오" 목록에는 `✗` 와 `△` 를 둘 다 적는다 — **`△` 가 있는데
    > "죽는 시나리오 없다"는 표기 금지.**

    ⚠️ 실사고 2026-10-05(it4): 결론이 *"오버 1.5 (생존 0.8462) — **죽는
       시나리오 없다**"* 였다. 🔴 그런데 블록 7 표는 `○ ○ ○ ○ △ △` 였다 —
       `E(2-1·1-0)`·`F(1-1·0-1)` 에서 **`1-0`·`0-1` 이 오버 1.5 를 죽인다.**
       생존 수(0.8462 = 11/13)는 그것을 반영했는데 **글이 안 했다.**
    🔴 `△` 를 빼면 "소액"이 **안전해 보인다** — 그것이 돈 사고로 간다.
    """
    out: list[str] = []
    for i in list(ids or []):
        sym = (marks or {}).get(i)
        if sym == FAIL:
            out.append(f"{i}({FAIL})")
        elif sym == PART:
            out.append(f"{i}({PART})")
    return out


#: 🔴🔴 **방향을 가르는 차이** — 지시서 §2-2.
#  > 홈승·원정승 확률 중 큰 쪽이 작은 쪽보다 **0.15 이상** 크면 그 팀 이름으로,
#  > 미만이면 `반반` 과 함께 **기울기**를 한 단어로 적는다.
DIR_GAP = 0.15


def direction_line(home_p: float, away_p: float, draw_p: float, *,
                   home: str = "", away: str = "") -> str:
    """🔴🔴 **방향 한 줄** — 등급과 **무관하게** 매 경기 낸다(지시서 §2-2).

    > 카드 블록 9 는 등급 유무와 무관하게 매 경기 한 줄을 낸다.
    > 🔴 **"방향 없음" 문자열은 코드에서 제거한다.**
    > ⚠️ 시작한 경기(M97)도 방향 줄은 낸다 — **등급만** 거둔다.

    ⚠️ 실사고 2026-10-05(it4): `홈승 0.62 · 원정승 0.23` 인데 블록 9 가
       *"방향 없음 — 승패 5줄 중 이름 0줄"* 이었다. 🔴 **등급 문턱과 방향
       판정을 같은 문턱으로 묶었다** — 사용자 규칙은 *"경기마다 누가 이길지
       분명히"* 다.
    """
    h, a, d = float(home_p or 0), float(away_p or 0), float(draw_p or 0)
    hn = str(home or "홈"), str(away or "원정")
    tail = f"홈승 {h:.2f} · 원정승 {a:.2f} · 무 {d:.2f}"
    # 🔴 **전부 0 이면 못 쟀다** — 그것을 "반반"으로 적으면 거짓이다(#3).
    #    ⚠️ 실사고 it6: 시나리오가 0개라 확률이 전부 0 이었다.
    if h <= 0 and a <= 0 and d <= 0:
        # 🔴 **까닭을 지어내지 않는다**(§8-6) — ⚠️ 실측 2026-10-06: 시나리오
        #    7개가 선 카드에서도 이 줄이 *"시나리오가 없어"* 라고 적었다.
        #    🔴 이 함수는 **확률 셋만** 받는다 — 시나리오가 몇 개인지 모른다.
        #       그러니 **모른다고** 적는다(그 수는 카드가 옆줄에 적는다).
        return (f"방향: **못 쟀다** — {tail}. 승패 확률이 서지 않았다"
                f"(⚠️ 반반이 아니다 — 모른다)")
    gap = abs(h - a)
    if gap >= DIR_GAP:
        who = hn[0] if h > a else hn[1]
        return f"방향: {who} — {tail}"
    # 🔴 **반반이어도 기울기는 적는다** — "모르겠다"로 끝내지 않는다
    lean = hn[0] if h >= a else hn[1]
    return f"방향: 반반 — {tail} · 기울기는 {lean}"


def same_branch_note(rows: list) -> str:
    """🔴🔴 **추천이 전부 같은 갈래인가** — 지시 ⑮ (실측 2026-10-05).

    ⚠️ 실사고: `양팀득점 예` 0.87 · `오버 1.5` 0.93 · `오버 2.5` 0.93 셋이 추천
       됐다. 3줄 상한(`max_same_direction`)은 통과하지만 **셋이 같은 쪽**이라
       하나가 틀리면 셋 다 틀린다 — 분산이 없다.
    🔴 **규칙은 바꾸지 않는다**(사용자 것이다) — 그 사실을 적는다(#3).
    ⚠️ 판단 기준은 **죽는 시나리오 집합**이다: 그것이 같으면 같은 갈래다.
    """
    named = [r for r in (rows or [])
             if str((r.get("verdict") if isinstance(r, dict) else "")) != "none"]
    if len(named) < 2:
        return ""
    sets = {frozenset(str(x) for x in (r.get("dead") or [])) for r in named}
    if len(sets) > 1:
        return ""
    who = ", ".join(str(r.get("market")) for r in named)
    return (f"🔴 **추천 {len(named)}줄이 전부 같은 갈래다**({who}) — 죽는 "
            f"시나리오가 같으니 하나가 틀리면 **셋 다 틀린다**. ⚠️ 규칙상 "
            f"허용되는 줄 수지만 **분산은 없다**")


def started(kickoff, now=None) -> tuple[bool, str]:
    """🔴 그 경기가 **이미 시작했나** — 지시 ③ (2026-10-05).

    > 킥오프가 지난 경기는 **등급을 내지 않는다**(카드에 *"이미 시작 — 예측
    > 아님"* + 결론 줄 **등급 없음**).

    ⚠️ 카드는 **그대로 낸다** — 분석은 보여 준다. 🔴 등급만 안 낸다: 끝난 일에
       *"낸다"* 를 적으면 그것은 예측이 아니라 **사후 설명**이다.
    """
    import datetime as _dt
    if kickoff is None:
        return False, ""
    try:
        k = kickoff.astimezone(_dt.timezone.utc)
    except (AttributeError, ValueError, TypeError):
        return False, ""
    from app import window as _w
    t = (now or _w.now_utc())
    try:
        t = t.astimezone(_dt.timezone.utc)
    except (AttributeError, ValueError, TypeError):
        return False, ""
    if k > t:
        return False, ""
    gone = (t - k).total_seconds() / 60
    return True, (f"🔴 **이미 시작한 경기다 — 예측이 아니다**: 킥오프가 "
                  f"{gone:.0f}분 지났다. 분석은 그대로 내지만 **등급은 내지 "
                  f"않는다**(지시 ③ 2026-10-05)")


def verdict_word(survival: float, *, enough: bool = True) -> str:
    """🔴🔴 **§6-8 — 그 수를 사람이 읽는 글자로.** 경계는 yaml 이 정한다.

    ⚠️ `enough=False` 는 **자료 부족**이다 — 수를 보지 않는다. 변수가 3개 미만
       이거나 반대 방향이 0개인 경기(§7 R5)는 생존이 1.0 이어도 등급이 아니다.
    🔴 경계값을 여기 베끼지 않는다(`config/thresholds.yaml` · §6-8).
    """
    if not enough:
        return WORD_NOT_ENOUGH
    sv = float(survival or 0.0)
    if sv >= float(thresholds.value("verdict_name_at")):
        return WORD_NAME
    if sv >= float(thresholds.value("verdict_small_at")):
        return WORD_SMALL
    if sv >= float(thresholds.value("verdict_small_low_at")):
        return WORD_SMALL_LOW
    return WORD_NONE


def _verdict(sv: float) -> Verdict:
    """§6-b — 🔴 **수가 정한다.** 고르는 사람도 LLM 도 없다.

    🔴 사다리는 `verdict_word` **한 곳**이다(#1 사본 금지).
    ⚠️ 실사고 2026-10-05: 여기서 `NAME_AT`·`SMALL_AT` 로 **따로 재어** 두 사다리가
       `0.80` 에서 갈렸다 — `verdict_word(0.80)` 은 `소액 하단`, 여기는 `소액`
       이었다. 수를 두 군데 적으면 한쪽만 고쳐진다.
    ⚠️ `Verdict` 는 **코드 셋**이다(`name`·`small`·`none`) — 어휘는 넷이라
       `소액`·`소액 하단` 두 띠가 같은 코드 `small` 로 간다(경계는 그대로 0.80).
    """
    words = verdict_words()
    back = dict(zip(words[:4], ("name", "small", "small", "none"), strict=False))
    return back.get(verdict_word(sv), "none")


# ══════════════════════════════════════════════════════════════════
# §6-c-3 보드 없는 경기 — **우리 기준선**
# ══════════════════════════════════════════════════════════════════

#: §6-c-3 — 핸디 **기준선**은 `0.5` 와 `1.5` 둘이다. 🔴 다른 줄을 지어내지 않는다.
#
#  ══════════════════════════════════════════════════════════════════
#  🔴🔴 **줄 하나 = 마켓 하나**(사용자 지적 2026-10-03)
#  ══════════════════════════════════════════════════════════════════
#
#  > 축구는 승무패 왜 **어느 한쪽에만 핸디가 적용된다**
#
#  ⚠️ 종전은 `(-0.5, 0.5, -1.5, 1.5) × (홈, 원정)` = **여덟 줄**이었다. 그러면 같은
#     기준선이 **favorite 을 바꿔 두 번** 생기고(`A -1.5/B +1.5` 와 `B -1.5/A +1.5`),
#     실측 2026-10-03 에 그 둘이 **똑같이 0.9388** 로 나와 미러 가드가 다 거뒀다
#     → 결론이 비었다.
#  🔴 이제 기준선마다 **마켓 하나**다 — 마이너스는 `_favorite()` 이 정한다.
OUR_HANDICAP_LINES = (0.5, 1.5)


def _favorite(game, drafts: list | None,
              w: dict | None) -> tuple[str, str, str]:
    """🔴🔴 **핸디의 마이너스를 어느 쪽에 붙이나** — 사용자 결정 2026-10-03.

    ══════════════════════════════════════════════════════════════════
    > 핸디는 **A로 간다**...우리 시나리오 weight 큰 쪽에 마이너스
    ══════════════════════════════════════════════════════════════════

    `questions/2026-10-03_handicap_which_side.md` 의 보기 다섯 중 **A** 다.
    배당은 못 쓰고(절대규칙 6), 순위표는 국제 친선·네이션스리그에 **없다**.
    남은 것 중 사용자가 A 를 골랐다.

    🔴🔴 **이것이 순환이라는 사실을 카드가 매번 적는다.**
       기준선의 favorite 을 **우리 수로 고르고**, 그 수로 생존을 잰다. 그러면
       favorite 의 `+핸디` 가 **기계적으로** 높게 나온다 — yaml 이 총점에서
       *"시나리오 최대합 + 0.5 금지 — 언더가 늘 1.00 이 되어 자기 자신을 증명한다"*
       로 막은 것과 **같은 모양**이다.
    ⚠️ 그래서 지우지 않고 **밝힌다.** 사용자가 알고 고른 것이고, 맞았는지는
       경기 결과만 말한다(원장). 이 사유 줄이 그때 되짚는 자리다.

    돌려주는 것: `(마이너스 쪽, 플러스 쪽, 사유)`. 🔴 **잴 수 없으면 빈 쪽**이고
    그러면 핸디 줄을 **아예 만들지 않는다** — 동전 던지기로 정하지 않는다.
    """
    home = str(getattr(game, "home", "") or "")
    away = str(getattr(game, "away", "") or "")
    if not drafts or not w:
        return "", "", ("🔴 핸디 줄 없음 — 시나리오 무게가 없어 **어느 쪽이 favorite "
                        "인지 못 쟀다**(사용자 규칙 A). 동전 던지기로 정하지 않는다")
    got: dict[str, float] = {}
    for mt, team in (("home", home), ("away", away)):
        tot = 0.0
        for d in drafts:
            sym, ratio, _bad = apply(Market(market_type=mt), d.scores,
                                     home=home, away=away,
                                     sport=getattr(game, "sport", ""))
            if sym != "?":
                tot += float(w.get(d.id, 0.0)) * ratio
        got[team] = round(tot, 4)
    if got[home] == got[away]:
        return "", "", (f"🔴 핸디 줄 없음 — 두 쪽 무게가 **같다**"
                        f"({home} {got[home]} = {away} {got[away]}). favorite 이 "
                        f"없으면 핸디는 뜻이 없다(사용자 규칙 A)")
    fav, dog = ((home, away) if got[home] > got[away] else (away, home))
    return fav, dog, (
        f"🔴 **핸디 마이너스는 `{fav}`** — 시나리오 무게가 더 크다"
        f"({fav} {got[fav]} vs {dog} {got[dog]}). 사용자 결정 2026-10-03 보기 **A**"
        f"(*\"우리 시나리오 weight 큰 쪽에 마이너스\"*). "
        f"⚠️ **이것은 순환이다** — 줄을 우리 수로 고르고 그 수로 생존을 재므로 "
        f"`{dog} +핸디` 가 기계적으로 높게 나온다. 사용자가 알고 고른 길이고, "
        f"맞았는지는 **경기 결과만** 말한다")


def our_board(game, standings: dict | None, *, drafts: list | None = None,
              w: dict | None = None) -> tuple[list[Market], list[str]]:
    """보드가 없을 때 쓰는 **우리 기준선**(§6-c-3). 🔴 사유를 함께 낸다.

    총점 기준선은 **리그 평균 → 가장 가까운 `X.5`** 다(`total_baseline_no_board`).
    ⚠️ yaml 이 *"시나리오 스코어 최대합 + 0.5"* 를 **금지**로 못 박았다 — 그러면
       언더가 늘 1.00 이 되어 자기 자신을 증명한다(순환).
    🔴 리그 평균을 못 구하면 **일반 마켓 줄**로 간다(분석 과정 9단계: *"보드 줄만,
       없으면 일반 마켓"*). 그 줄도 없는 종목이면 총점 마켓을 **만들지 않는다**.
    """
    notes: list[str] = []
    out: list[Market] = [Market(market_type=t) for t in WIN_MARKETS]
    fav, dog, why = _favorite(game, drafts, w)
    notes.append(why)
    if fav:
        for ln in OUR_HANDICAP_LINES:
            # 🔴 **줄 하나에 두 쪽**이다 — 마이너스는 favorite, 플러스는 상대
            out.append(Market(market_type="handicap", team=fav, line=-ln))
            out.append(Market(market_type="handicap", team=dog, line=ln))
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **양팀득점**(사용자 지적 2026-10-03) — 보드에 그 마켓이 없었다
    # ══════════════════════════════════════════════════════════════════
    #
    #  사용자가 손으로 쓴 보드에 *"양팀득점"* 줄이 있었다. 🔴 승패·핸디·총점으로는
    #  못 말하는 것이다 — `0-0` 과 `2-0` 은 총점이 다르지만 양팀득점은 둘 다 `아니오` 다.
    #  ⚠️ 기준선이 없으므로 **리그 평균을 안 쓴다** — 늘 낼 수 있다.
    for side in BTTS_SIDES:
        out.append(Market(market_type="btts", team=side))
    notes.append("§6-c-3 보드 없음 · 양팀득점 두 쪽을 센다(기준선이 없는 마켓이다)")
    cfg = rules.total_baseline_cfg()
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **참고 줄은 관례 줄로 되돌린다**(사용자 지시 2026-10-09(6차) ③)
    # ══════════════════════════════════════════════════════════════════
    #
    # > 참고 줄은 **1.5/2.5/3.5 로 되돌린다**(1.2·2.2·3.2 는 실제로 걸 수 없는
    # > 줄이다). 기준 총골(2.25)은 **블록 3 에 숫자로만** 적고, 줄 판정은 실제
    # > 보드·피드 줄에만.
    #
    # ⚠️ 그래서 `match_total_baseline` 을 **여기서 쓰지 않는다** — 실측 2026-10-09
    #    (강원–부천): 기준 2.25 가 `over 1.2 / 2.2 / 3.2` 를 만들었고 그런 줄은
    #    북에 없다. 🔴 그 수는 사실로만 남고(블록 3), 줄은 관례·보드가 정한다.
    base = (standings or {}).get("total_baseline")
    if base is None:
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **분석 과정 9단계** — *"보드 줄만, **없으면 일반 마켓**"*
        # ══════════════════════════════════════════════════════════════
        #
        #  실측 2026-10-03(엘살바도르 vs 자메이카 · CONCACAF 네이션스리그):
        #  순위표 어댑터가 없어 리그 평균이 없다 → 총점 줄이 **0개**였다.
        #  🔴 그런데 사용자 분석의 결론은 **통째로 언더**였다(2.5 · 3.5).
        #  ⚠️ 리그 평균이 없다고 총점을 포기하면 **대표팀 경기에서 봇이 할 말이
        #     없어진다** — 친선·네이션스리그는 순위표가 애초에 없다.
        #  🔴 관례 줄은 **우리 수가 아니다** — `forbidden`(순환 식)에 안 걸린다.
        common = rules.common_total_lines(str(getattr(game, "sport", "") or ""))
        if not common:
            notes.append(f"§6-c-3 총점 기준선을 못 구했다 — {cfg['no_league_avg']}")
        else:
            for ln in common:
                for side in (OVER, UNDER):
                    out.append(Market(market_type="total", team=side, line=ln))
            # 🔴 **어느 쪽을 썼는지 적는다** — 리그 평균 줄과 관례 줄은 뜻이 다르고,
            #    그 차이를 안 적으면 카드를 읽는 사람이 둘을 구분할 수 없다.
            notes.append(
                f"🔴 §9단계 보드 없음 · **리그 평균도 없다** → **일반 마켓 줄** "
                f"{common} 로 센다 (출처: {cfg.get('common_lines_source')}). "
                f"⚠️ 이것은 리그 평균에서 나온 줄이 **아니다** — 관례다. "
                # 🔴🔴 **v5 §6-3 — "보드 오면 무효" 꼬리표**(2026-10-04)
                #
                #  > 보드가 없으면 종목별 기준선 후보에 **복수 대입**하고 전부
                #  > **"보드 오면 무효" 꼬리표**.
                #
                #  ⚠️ 그 꼬리표가 없으면 이 줄이 **보드 줄처럼 읽힌다** — 그런데
                #     북메이커가 다른 기준선을 내면 이 생존율은 **뜻이 없다**
                #     (§6-3 *"보드 기준선이 다르면 다시 센다"*).
                f"🔴 **보드 오면 무효** — 보드가 다른 기준선을 내면 다시 센다"
                f"(v5 §6-3)")
    else:
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **기준선을 여러 개 낸다**(사용자 지적 2026-10-03)
        # ══════════════════════════════════════════════════════════════
        #
        #  사용자는 **언더 2.5 와 언더 3.5 를 둘 다** 대입했다. 봇은 리그 평균에서
        #  **하나**만 뽑아 그 줄만 셌다 — 보드는 그렇게 생기지 않았다(북메이커는
        #  사다리로 여러 줄을 낸다).
        #  🔴 리그 평균 줄을 **가운데 두고 양쪽으로** 펼친다. 몇 칸인지는 yaml 이
        #     정한다 — 코드가 숫자를 박지 않는다.
        for ln in rules.total_lines(float(base)):
            for side in (OVER, UNDER):
                out.append(Market(market_type="total", team=side, line=ln))
        notes.append(f"§6-c-3 보드 없음 · 우리 기준선 총점 "
                     f"{rules.total_lines(float(base))} "
                     f"(가운데 {base} · {cfg['source']})")
    return out, notes


# ══════════════════════════════════════════════════════════════════
# 본체
# ══════════════════════════════════════════════════════════════════


def name_of(m: Market) -> str:
    """사람이 읽는 마켓 이름. 🔴 **가격을 쓰지 않는다**(§7 R8)."""
    ko = {"home": "홈 승", "away": "원정 승", "draw": "무승부",
          "home_dc": "홈 무패", "away_dc": "원정 무패"}
    if m.market_type in ko:
        return ko[m.market_type]
    if m.market_type == "handicap":
        return f"{m.team} {m.line:+g}"
    if m.market_type == "total":
        return f"{'오버' if m.team == OVER else '언더'} {m.line:g}"
    if m.market_type == "btts":
        return f"양팀득점 {'예' if m.team == BTTS_YES else '아니오'}"
    return str(m.market_type)


class Result:
    """§6 산출. 🔴 **못 센 것과 경고를 함께** 들고 온다."""

    def __init__(self) -> None:
        self.markets: list[MarketSurvival] = []
        #: 사람이 읽을 줄 — `(이름, survival, verdict, 시나리오별 기호)`
        self.rows: list[dict] = []
        #: §6-c-2 — 보드엔 없지만 생존 1.0 인 마켓. **결론 줄과 섞지 않는다**
        self.extra: list[dict] = []
        #: 🔴 무게를 무엇으로 쟀나 — `probability` 또는 `strength(…)`
        self.weight_mode: str = ""
        #: 🔴 덮은 확률(격자가 있을 때만). `survival` 이 그 안의 비율이라는 사실
        self.coverage: float | None = None
        self.notes: list[str] = []
        #: §6-f — 총점 마켓의 **기준선별** 생존
        self.by_line: list[dict] = []

    def to_survival(self, game_id: int) -> Survival:
        return Survival(game_id=game_id, markets=list(self.markets))


def run(drafts: list, game, *, board: list[Market] | None = None,
        standings: dict | None = None, probs: dict | None = None,
        coverage: float | None = None,
        fold: set[str] | None = None,
        xi_state: str = "",
        # 🔴🔴 **거짓 1.0 계약**의 재료(사용자 수정 ⑤ · 2026-10-04).
        #    ⚠️ 안 주면 가드가 **막지 않는다** — 모르는 것과 0 은 다르다.
        variables: list | None = None,
        # 🔴🔴 **킥오프가 지났으면 등급을 안 낸다** — 지시 ③ (2026-10-05).
        #    ⚠️ 안 주면 **막지 않는다**(모르는 것과 지난 것은 다르다).
        kickoff=None, now=None,
        # 🔴🔴 **자료가 얇으면 등급만 거둔다** — 사용자 규칙 2026-10-06.
        #    > §7 R5 자료 부족은 "등급 금지"로만 작동한다. 시나리오·대입·방향
        #    > 판정은 항상 낸다.
        #    ⚠️ 빈 문자열이면 막지 않는다(모르는 것과 얇은 것은 다르다).
        thin_why: str = "") -> Result:
    """§6-a~§6-f 를 적용한다.

    `board` 가 비면 §6-c-3 **우리 기준선**으로 센다(그 사실을 기록에 남긴다).
    `probs` 는 포아송 스코어 격자(`league.score_probabilities`) — 있으면 `p_market`
    (격자 전체에서 맞을 확률)을 함께 낸다.
    """
    res = Result()
    # 🔴 `market_key` 가 핸디의 **상대 쪽**을 찾는 데 쓴다(위 `_SIDES` 주석)
    global _SIDES
    _SIDES = (str(getattr(game, "home", "") or ""),
              str(getattr(game, "away", "") or ""))
    if not drafts:
        res.notes.append("시나리오가 없다 — 생존을 셀 것이 없다(§7 R5 자료 부족)")
        return res

    w, mode = weights(drafts)
    res.weight_mode = mode
    total = sum(w.values())
    if total <= 0:
        res.notes.append("무게 합이 0 이다 — 생존을 셀 수 없다")
        return res
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **덮은 확률은 격자의 사실이다 — 무게 꼴과 무관하다**(2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전엔 `mode == "probability"` 일 때만 쟀다. ②로 무게가 늘 변수 합이
    #     되자 **그 수가 통째로 사라졌다**(계약이 잡았다).
    #  🔴 그런데 *"우리 시나리오가 확률 공간의 몇 %를 덮나"* 는 **격자가 답하는
    #     것**이고, 사용자가 격자에 남긴 역할 셋 중 하나다. 무게를 어떻게 세든
    #     그 수는 뜻이 있다 — 숨기면 과신이 된다(`report_uncovered: true`).
    cov = [float(d.probability) for d in drafts
           if getattr(d, "probability", None) is not None]
    res.coverage = (round(sum(cov), 4)
                    if len(cov) == len(drafts) and drafts else None)

    lines = list(board or [])
    if not lines:
        lines, notes = our_board(game, standings, drafts=drafts, w=w)
        res.notes += notes
    else:
        res.notes.append(f"보드 {len(lines)}줄 — §6-c-1 **보드에 있는 줄만** "
                         f"결론에 쓴다")

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **확정 XI 가 없으면 등급 상한**(사용자 규칙 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 확정 XI는 킥오프 1시간 전 발표라 아직 없다 → **상한 0.85**
    #
    #  ⚠️ 생존 수는 **그대로 둔다** — 등급만 거둔다. 0.85 는 `SMALL_AT`(0.8)과
    #     `NAME_AT`(1.0) 사이라, 상한이 걸리면 *"이름은 못 적고 소액까지"* 가 된다.
    cap = _xi_cap(res, game, xi_state)
    for m in lines:
        row = _one(res, m, drafts, w, total, game, probs, fold=fold, cap=cap)
        if m.market_type == "total":
            _by_line(res, m, drafts, w, total, game, probs)
        res.rows.append(row)

    # 🔴 폼 변수 사유 글을 가드가 읽을 자리에 둔다(위 `_streak_whys` 주석)
    _streak_whys.clear()
    _streak_whys.extend(str(getattr(v, "why", "") or "")
                        for v in (variables or []))

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **이미 시작한 경기는 등급을 거둔다** — 지시 ③ (2026-10-05)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 카드는 **그대로 낸다**(분석은 보여 준다) — 등급만 안 낸다.
    #  🔴 끝난 일에 *"낸다"* 를 적으면 그것은 예측이 아니라 **사후 설명**이다.
    gone, said = started(kickoff, now)
    if gone:
        res.notes.append(said)
        for row in res.rows:
            if row.get("verdict") in ("name", "small", "low"):
                row["verdict"] = "none"
                row["why"] = str(row.get("why") or "") + " · " + said
        for mk in (res.markets or []):
            if str(getattr(mk, "verdict", "")) in ("name", "small", "low"):
                mk.verdict = "none"

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **자료 얇음 — 등급을 거둔다**(사용자 규칙 2026-10-06)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `gone`(이미 시작한 경기)과 **같은 길**이다 — 대입은 그대로 보이고
    #     `verdict` 만 `none` 이 된다. 🔴 그래야 *"무엇이 어느 시나리오에서
    #     죽는지"* 는 읽히고 **등급만** 없다.
    #  🔴 §6-7 이 막으려던 거짓 1.0 은 이것으로 막힌다: 얇은 세트에서 1.0 이
    #     나와도 그것이 **등급이 되지 않는다.**
    if str(thin_why or "").strip():
        said_thin = (f"🔴 **자료 얇음 — 등급 없음**({thin_why}) · "
                     f"대입·방향은 그대로 낸다(사용자 규칙 2026-10-06)")
        res.notes.append(said_thin)
        for row in res.rows:
            if row.get("verdict") in ("name", "small", "low"):
                row["verdict"] = "none"
                row["why"] = str(row.get("why") or "") + " · " + said_thin
        for mk in (res.markets or []):
            if str(getattr(mk, "verdict", "")) in ("name", "small", "low"):
                mk.verdict = "none"

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **총점 줄은 등급 보류**(사용자 지시 2026-10-09 ②)
    # ══════════════════════════════════════════════════════════════════
    #
    # > 결과 대조 지시 1번(총골 기준 층)을 이어서 진행 — **그 전까지 총점 줄은
    # > 등급 보류 유지.**
    #
    # 🔴 그 지시 문서가 **저장소에 없다**(`docs/fable/inbox/` 에 `결과 대조` 가
    #    없다 · 2026-10-09 확인). ⚠️ 파일에 없는 지시는 인용하지 않는다(v4 §11-1)
    #    — 그래서 **지금 실행 가능한 절만** 넣는다: 총점 줄의 등급을 거둔다.
    # 🔴 대입·생존 수는 **그대로 보인다** — `gone`·`thin` 과 같은 길이다.
    #    ⚠️ 총골 기준 층이 생기면 이 자리를 걷는다(그때 계약도 함께 고친다).
    said_tot = ("🔴 **총점 줄 등급 보류** — 총골 기준 층(결과 대조 지시 1번)이 "
                "아직 없다 · 생존 수는 그대로 낸다(지시 2026-10-09 ②)")
    hit_tot = False
    # ⚠️ **글자로 맞추지 않는다** — `row["name"]` 은 `name_of` 가 지은 한국어
    #    (`오버 2.5`)다. 🔴 줄이 든 **마켓 객체**의 `market_type` 으로 센다
    #    (글자를 보면 번역·표기가 바뀔 때 조용히 빠진다 · D46 의 형제 문제).
    for row in res.rows:
        mkt = row.get("market")
        if getattr(mkt, "market_type", "") == "total" \
                and row.get("verdict") in ("name", "small", "low"):
            row["verdict"] = "none"
            row["why"] = str(row.get("why") or "") + " · " + said_tot
            hit_tot = True
    for mk in (res.markets or []):
        if getattr(mk, "market_type", "") == "total" \
                and str(getattr(mk, "verdict", "")) in ("name", "small", "low"):
            mk.verdict = "none"
            hit_tot = True
    if hit_tot:
        res.notes.append(said_tot)

    _mirror_guard(res)
    # 🔴 **순서가 뜻이다**: ① 여집합 쌍을 거두고 ② 같은 방향을 3줄로 줄인 뒤
    #    ③ 서로 다른 방향이 남으면 하나로 고른다. ②를 ③보다 뒤에 두면 ③이 이미
    #    하나만 남겨 ②가 할 일이 없어진다.
    _same_direction_cap(res)
    _pick_one(res)
    # 🔴 **분산이 없으면 적는다**(⑮ · 실측 2026-10-05) — 규칙은 안 바꾼다.
    #    ⚠️ `_pick_one` 뒤에 둔다: 남은 줄이 무엇인지 그때 정해진다.
    said = same_branch_note(res.rows)
    if said:
        res.notes.append(said)
    _coverage_warning(res)
    # 🔴🔴 **거짓 1.0 계약** — 사용자 수정 ⑤ (2026-10-04).
    #    ⚠️ **맨 뒤다.** 앞의 상한·고르기가 끝난 뒤에 남은 1.0 을 본다 — 앞에 두면
    #       `_pick_one` 이 지운 줄까지 세어 사유가 거짓이 된다.
    _thin_set_guard(res, game, drafts,
                    n_vars=(len(variables) if variables is not None else None))
    _scoring_streak_guard(res, drafts, game)
    # 🔴🔴 **M18** — 야구는 `pitcher_state` 없이 총점·핸디를 적지 않는다
    _m18_guard(res, game, variables=variables)
    return res


def _pick_one(res: Result) -> None:
    """🔴🔴 **다른 갈래에서 죽는 추천이 여럿이면 하나만 고른다**(사용자 규칙 2026-10-03).

    ══════════════════════════════════════════════════════════════════
    > 콜롬비아 무패 0.85 … 언더 3.5 0.85 — **둘은 다른 갈래에서 죽으니 하나만
    > 고른다 → 무패 우선**
    ══════════════════════════════════════════════════════════════════

    봇은 둘을 **다 적었다.** 같은 경기에 추천을 여럿 적으면 돈이 쪼개지고, 두 추천이
    **다른 시나리오에서 죽으면** 둘 중 하나는 거의 반드시 틀린다.

    ⚠️ `_mirror_guard` 와 다른 문제다 — 그쪽은 **서로를 상쇄**하는 쌍(같은 마켓의
       두 쪽)이고, 이쪽은 둘 다 맞을 수 **있지만** 같이 걸 이유가 없는 쌍이다.
    🔴 **죽는 갈래가 같으면 그대로 둔다** — 같은 이야기에 걸린 것이므로 쪼개지지 않는다.
    🔴 고르는 기준(종류 순서)은 **yaml 이 선언한다** — 코드가 임의로 고르면 그것이
       승자를 고르는 것이 된다.
    """
    cfg = rules.pick_one_cfg()
    # ⚠️ 열쇠가 `enabled` 다 — `on` 은 YAML 이 불리언 키로 읽는다(위 yaml 주석)
    if not cfg.get("enabled"):
        return
    named = [r for r in res.rows if r["verdict"] != "none"]
    if len(named) < 2:
        return
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **두 지시를 맞춘다** — 이 규칙은 **다른 방향끼리만** 건다
    # ══════════════════════════════════════════════════════════════════
    #
    #  이 함수는 사용자 분석 2026-10-03(콜롬비아)의 *"둘은 다른 갈래에서 죽으니
    #  하나만 고른다"* 에서 왔다. ⚠️ 그런데 같은 날 받은 **분석 과정 10단계**는
    #  *"**같은 방향 3개까지**"* 라고 말한다 — 그대로 두면 이 함수가 먼저 하나만
    #  남겨 10단계가 **아무 일도 못 한다**.
    #
    #  🔴 두 지시가 함께 서는 읽기는 하나뿐이다:
    #     같은 방향 → **3줄까지**(`_same_direction_cap`)
    #     다른 방향 → **하나만**(여기)
    #  ⚠️ 그 근거는 사용자 자신의 결론이다 — `언더 3.5`(0.85)와 `언더 2.5`(0.8)를
    #     **둘 다** 적었고 그 둘은 죽는 갈래가 다르다(E / D·E). 종전 코드라면
    #     하나가 거둬졌을 것이다.
    ways = {direction_of(r["market"]) for r in named}
    if len(ways) < 2:
        res.notes.append(
            f"§10단계 — 남은 추천 {len(named)}줄이 **같은 방향**({ways}) 이다 → "
            f"'하나만 고른다'를 걸지 않는다(같은 방향은 3줄까지)")
        return

    def _dead(r: dict) -> frozenset:
        return frozenset(k for k, v in (r["marks"] or {}).items() if v == FAIL)

    # 🔴 죽는 갈래가 **서로 다른** 쌍이 하나라도 있나
    deads = {id(r): _dead(r) for r in named}
    if len({frozenset(d) for d in deads.values()}) < 2:
        return
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **v5 §6-6 — 생존율이 1순위다** (2026-10-04) [#26]
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 같은 경기에서 등급이 선 줄이 여럿이면 **생존율 높은 순**, 동률이면 **더
    #  > 강한 주장**(승 > 무패 > 핸디 > 총점). **선언 순서로 고르지 않는다.**
    #
    #  ⚠️ 종전 `_rank` 는 **종류를 먼저** 봤다(`pick_one.prefer` 선언 순서).
    #     🔴 실측 2026-10-04: `btts 예`(**0.8**)가 `오버 2.5`(**1.0**)를 이겼고
    #        `홈 무패`(1.0)가 `홈 승`(1.0)을 이겼다 — 생존율이 낮은 줄이 뽑혔다.
    #  🔴 §6-6 이 그것을 뒤집었다. ⚠️ `prefer` 선언은 **남겨 둔다** — 되돌린 것을
    #     숨기지 않는다. 그러나 **쓰지 않는다**(`claim_strength` 가 동률을 가린다).
    strength = rules.claim_strength()

    def _claim(r: dict) -> int:
        """🔴 그 줄이 **얼마나 센 주장**인가. 작을수록 세다."""
        kind = str(r["market_key"][0])
        mt = str(getattr(r["market"], "market_type", ""))
        # ⚠️ 더블찬스(`*_dc`)는 **무패**다 — 승보다 약한 주장이다
        tag = "dc" if mt.endswith("_dc") else kind
        return strength.index(tag) if tag in strength else len(strength)

    def _rank(r: dict) -> tuple:
        # 🔴 **생존율 → 주장 강도 → 죽는 갈래 적은 쪽 → 이름**(§6-6)
        return (-float(r["survival"]), _claim(r), len(deads[id(r)]), r["name"])

    keep = min(named, key=_rank)
    dropped = [r for r in named if r is not keep]
    res.notes.append(
        f"🔴 추천이 {len(named)}줄인데 **죽는 갈래가 서로 다르다** — 둘 중 하나는 "
        f"거의 반드시 틀린다. {cfg.get('why')} → **하나만 고른다**: "
        f"{name_of(keep['market'])}(생존 {keep['survival']} · 남김) · "
        + " · ".join(f"{name_of(r['market'])}({r['survival']})"
                      for r in dropped) + "(거둠). "
        f"🔴 **생존율 순**이고 동률이면 더 강한 주장({strength}) — v5 §6-6: "
        f"*\"선언 순서로 고르지 않는다\"*")
    for r in dropped:
        _ungrade(res, r)


def direction_of(m: Market) -> str:
    """🔴🔴 **이 줄이 어느 방향을 말하나** — 분석 과정 10단계가 세는 단위.

    > 10. 상한·상관 → 결론·방아쇠 — **같은 방향 3개까지**, 확인 항목 첨부

    ⚠️ "방향"은 **마켓 종류가 아니다.** `El Salvador +1.5` 와 `원정 무패` 는 종류가
       다르지만 같은 쪽을 말하고, 틀리면 **같이 틀린다**(상관이 1 에 가깝다).
    🔴 그래서 **승자를 가리키는 줄은 팀 이름으로**, 총점은 `오버`/`언더` 로,
       양팀득점은 그 두 쪽으로 묶는다. 무승부는 자기 혼자다.
    """
    kind = m.market_type
    if kind == "total":
        return f"총점:{m.team}"
    if kind == "btts":
        return f"양팀득점:{m.team}"
    if kind == "handicap":
        # 🔴 핸디는 **그 줄이 편드는 팀**이 방향이다(`X +1.5` 는 X 를 편든다)
        return f"팀:{m.team}"
    a, b = _SIDES
    return {"home": f"팀:{a}", "home_dc": f"팀:{a}",
            "away": f"팀:{b}", "away_dc": f"팀:{b}",
            "draw": "무승부"}.get(str(kind), str(kind))


def _same_direction_cap(res: Result) -> None:
    """🔴🔴 **분석 과정 10단계** — *"같은 방향 3개까지."*

    같은 방향으로 네 줄 이상을 내면 그것은 **네 개의 추천이 아니라 한 추천을 네 번
    적은 것**이다 — 틀리면 넷이 같이 틀린다.
    🔴 남기는 것은 **생존이 높은 쪽**이고, 거두는 줄도 **표에는 그대로 남는다**
       (§6-f) — 등급만 거둔다(#3 조용한 0 금지).
    """
    cfg = rules.conclusion_cfg()
    cap = int(cfg.get("max_same_direction") or 0)
    if cap <= 0:
        return
    by: dict[str, list[dict]] = {}
    for r in res.rows:
        if r["verdict"] != "none":
            by.setdefault(direction_of(r["market"]), []).append(r)
    for way, rows in by.items():
        if len(rows) <= cap:
            continue
        # ══════════════════════════════════════════════════════════════
        # 🔴 **동점일 때 무엇으로 가르나** — 알파벳이 아니다
        # ══════════════════════════════════════════════════════════════
        #
        #  실측: 네 줄이 **전부 생존 1.0** 이었고 이름순으로 잘려 `홈 승` 이 거뒀다
        #  (`A +0.5` · `A -0.5` · `홈 무패` 가 남았다). 🔴 알파벳은 **규칙이 아니다** —
        #  그렇게 고르면 팀 이름이 추천을 정하는 꼴이 된다.
        #  ⚠️ 이 저장소에는 **이미 선언된 순서**가 있다(`pick_one.prefer`) — 같은
        #     질문("여럿이면 무엇을 먼저")에 두 번째 답을 짓지 않는다(사본 금지).
        order = [str(x) for x in (rules.pick_one_cfg().get("prefer") or [])]

        def _rank(r: dict) -> tuple:
            kind = r["market_key"][0]
            return (-float(r["survival"]),
                    order.index(kind) if kind in order else len(order),
                    r["name"])

        rows = sorted(rows, key=_rank)
        drop = rows[cap:]
        res.notes.append(
            f"🔴 **{way}** 방향으로 {len(rows)}줄이 이름을 받았다 — {cfg.get('why')} "
            f"→ 생존 높은 {cap}줄만 남긴다"
            f"({', '.join(name_of(r['market']) for r in rows[:cap])}). "
            f"거둠: {', '.join(name_of(r['market']) for r in drop)} "
            f"(출처: {cfg.get('source')})")
        for r in drop:
            _ungrade(res, r)


def market_key(m: Market) -> tuple:
    """🔴🔴 **이 줄이 어느 마켓의 한 쪽인가.** 같은 열쇠면 **같은 마켓**이다.

    ══════════════════════════════════════════════════════════════════
    🔴 사용자 지적 2026-10-03 — 보드 **구조**가 틀렸다
    ══════════════════════════════════════════════════════════════════

    > 핸드 +1.5 두팀다 성립이 안된다는거야..축구는 승무패 **왜 어느 한쪽에만
    > 핸디가 적용된다**..언오버는 토탈이고

    종전 `our_board` 는 핸디를 `(팀 × ±0.5 × ±1.5)` = **여덟 줄**로 늘어놓고 각
    줄을 **독립 베팅처럼** 셌다. 실제 보드는 그렇지 않다:

    | 마켓 | 쪽 | 성질 |
    |---|---|---|
    | 승무패 | 홈 승 · 무승부 · 원정 승 | 세 쪽, 합 1.0 |
    | **핸디 한 라인** | `X −L` · `Y +L` | **두 쪽, 여집합** |
    | **토탈 한 기준선** | 오버 · 언더 | **두 쪽, 여집합** |

    🔴 즉 여덟 줄은 **마켓 네 개 × 두 쪽**이고, 한 마켓의 두 쪽은 **동시에 맞을 수
       없다**. 그 둘을 같은 결론에 적으면 거짓이다.
    ⚠️ 열쇠를 `|L|` 로 두지 않는다 — `(C +1.5 / P −1.5)` 와 `(P +1.5 / C −1.5)` 는
       **다른 마켓**이다. 그 둘을 함께 막는 것은 `_mirror_guard` 의 일이다.
    """
    if m.market_type == "handicap" and m.line is not None:
        # 🔴 **`+` 를 받는 쪽**이 마켓의 이름이다 — `X −L` 은 그 마켓의 반대쪽이다
        plus = m.team if float(m.line) > 0 else _other(m.team)
        return ("handicap", abs(float(m.line)), plus or "")
    if m.market_type == "total" and m.line is not None:
        return ("total", float(m.line))
    # 🔴 양팀득점은 **기준선이 없는 한 마켓**이고 두 쪽이 여집합이다
    if m.market_type == "btts":
        return ("btts",)
    if m.market_type in WIN_MARKETS:
        return ("win",)
    return (m.market_type,)


#: 🔴 핸디 마켓의 **상대 쪽**을 찾기 위한 자리. `run()` 이 경기를 넣어 둔다.
#  ⚠️ 모듈 상태를 쓰는 까닭: `Market` 에는 상대 팀 칸이 없다(§1 스키마). 열쇠를
#     만들려면 상대 이름이 필요하고, 스키마를 늘리는 것은 단계 2 범위다.
_SIDES: tuple[str, str] = ("", "")


def _other(team: str | None) -> str:
    a, b = _SIDES
    t = str(team or "")
    if t and t == a:
        return b
    if t and t == b:
        return a
    return ""


def _mirror_guard(res: Result) -> None:
    """🔴🔴 **서로를 상쇄하는 두 줄에 동시에 이름을 적지 않는다**(사용자 지적 2026-10-03).

    ══════════════════════════════════════════════════════════════════
    > 이거는 둘다 핸디잖아..말이 안되는 결론이지 않니?
    ══════════════════════════════════════════════════════════════════

    실측(콜롬비아 vs 파라과이): 결론이 이랬다.

    ```
    소액: Colombia +1.5 (0.955) — 죽는 시나리오 ['E']
    소액: Paraguay +1.5 (0.955) — 죽는 시나리오 ['D']
    ```

    🔴 **같은 핸디 기준선의 두 쪽이다.** 둘을 다 걸면 어느 결과에서도 한쪽이 지므로
       **확정 손실**이다 — 추천으로서 뜻이 없다. 각각은 계산이 맞지만(각자 시나리오
       하나에만 죽는다) **같은 카드에 둘이 같이 있으면 거짓 신호**다.
    ⚠️ `X +L` 과 `Y −L` 은 더 나쁘다 — **논리적으로 동시에 맞을 수 없다**(정확한
       여집합이다). 같은 규칙이 둘 다 막는다: `|기준선|` 이 같고 팀이 다르면 거둔다.
    🔴 거두면서 **그 쌍이 실제로 말하는 것**을 기록에 남긴다 — 그것은 승자에 대한
       말이 아니라 **마진에 대한 말**이고, 우리 보드에는 마진 마켓이 없다.
    ⚠️ 총점도 같다(`오버 L` + `언더 L` 은 정확한 여집합이다).
    """
    named = [r for r in res.rows if r["verdict"] != "none"]
    if len(named) < 2:
        return
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **한 마켓의 두 쪽은 동시에 맞을 수 없다**(사용자 지적 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    same: dict[tuple, list[dict]] = {}
    for r in named:
        same.setdefault(r["market_key"], []).append(r)
    for key, rows in same.items():
        if len(rows) < 2 or key[0] == "win":
            continue          # 승무패는 세 쪽이고 그 안에서 하나만 사는 것이 정상
        res.notes.append(
            f"🔴 **한 마켓의 두 쪽이 동시에 이름을 받았다** — "
            f"{', '.join(name_of(r['market']) for r in rows)}. 두 쪽은 "
            f"**여집합**이라 동시에 맞을 수 없다 → 둘 다 등급을 거둔다")
        for r in rows:
            _ungrade(res, r)
    by: dict[tuple, list[dict]] = {}
    for r in named:
        m = r["market"]
        if m.market_type == "handicap" and m.line is not None:
            by.setdefault(("handicap", abs(float(m.line))), []).append(r)
        elif m.market_type == "total" and m.line is not None:
            by.setdefault(("total", float(m.line)), []).append(r)
    for (kind, line), rows in by.items():
        sides = {str((r["market"].team or "")) for r in rows}
        if len(rows) < 2 or len(sides) < 2:
            continue
        what = ("마진" if kind == "handicap" else "총점")
        res.notes.append(
            f"🔴 같은 {what} 기준선 {line:g} 의 **두 쪽이 동시에 이름을 받았다** — "
            f"{', '.join(name_of(r['market']) for r in rows)}. 둘을 다 걸면 어느 "
            f"결과에서도 한쪽이 지므로 **확정 손실**이다 → 둘 다 등급을 거둔다. "
            f"이 쌍이 말하는 것은 승자가 아니라 **{what}** 이고, 우리 보드에는 그 "
            f"마켓이 없다")
        for r in rows:
            _ungrade(res, r)


def _ungrade(res: Result, row: dict) -> None:
    """🔴 등급만 거둔다 — **생존 수는 지우지 않는다**(왜 못 받았는지가 남아야 한다)."""
    row["verdict"] = "none"
    m = row["market"]
    for ms in res.markets:
        if (ms.market_type == m.market_type and ms.team == m.team
                and ms.line == m.line):
            ms.verdict = "none"


#: 🔴 §6-5 *"한 단계 아래"* 가 쓰는 꼬리표. ⚠️ **글자를 여기 한 번만** 적는다 —
#  `analyze.xi_state` 가 붙이고 `_xi_cap` 이 뗀다.
UNVERIFIED_MARK = "·미검증"


def step_down(cap: float) -> float:
    """🔴🔴 **§6-5 — 상한을 한 단계 내린다**(*"미검증 … 한 단계 아래"*).

    ⚠️ `cap - 0.05` 로 짓지 않는다 — 칸이 `1.0 / 0.9 / 0.85 / 0.8` 이라 간격이
       고르지 않다(0.1 · 0.05 · 0.05). 산수로 지으면 `1.0 → 0.95` 라는 **없는
       칸**이 나온다.
    🔴 사다리는 yaml 이 정한다(`xi_state_cap.ladder`) — 여기 베끼지 않는다.
    ⚠️ 사다리에 없는 수는 **그 아래 첫 칸**으로 내린다. 바닥에서는 바닥이다
       (0 으로 떨어뜨리면 *"상한"*이 *"금지"*가 된다 — 다른 규칙이다).
    """
    cfg = rules.xi_state_cap()
    ladder = sorted((float(x) for x in (cfg.get("ladder") or [])), reverse=True)
    if not ladder:
        raise KeyError("`xi_state_cap.ladder` 가 없다 — §6-5 의 '한 단계'를 "
                       "코드가 지어내지 않는다")
    below = [x for x in ladder if x < float(cap)]
    return below[0] if below else ladder[-1]


def _xi_cap(res: Result, game, xi_state: str) -> float | None:
    """🔴🔴 **분석 과정 5단계** — 라인업 상태가 등급 상한을 정한다.

    ```
    5. 라인업 상태 → 상한        확정 1.0 / 예상 0.85 / 없음 0.8
    ```

    ⚠️ 종전은 **두 칸**이었다(`xi_confirmed: bool`). 라인업을 **아예 못 잡은
       경기**와 **예상 XI 를 잡은 경기**가 같은 상한 0.85 를 받았다 — 모르는 양이
       다른데 대접이 같았다.
    🔴 상한 `1.0` 은 **상한이 없는 것과 같다**(생존이 1.0 을 넘을 수 없다) — 그래도
       `None` 으로 돌리지 않고 **그 칸을 밟았다는 사실을 사유에 적는다**. 어느 칸에
       걸렸는지가 카드에서 사라지면 "왜 이 수인가"를 되짚을 수 없다.
    ⚠️ 칸 이름을 **모르면**(빈 문자열) 가장 센 상한을 건다 — fail-closed. 모르는데
       상한을 푸는 것은 우리에게 유리한 쪽으로 거짓말하는 것이다.
    """
    cfg = rules.xi_state_cap()
    caps = {str(k): float(v) for k, v in (cfg.get("caps") or {}).items()}
    sports = [str(x) for x in (cfg.get("sports") or [])]
    sport = str(getattr(game, "sport", "") or "")
    if sports and sport not in sports:
        res.notes.append(
            f"§5단계 상한 — `{sport}` 은 적용 종목 {sports} 이 아니다(안 건다)")
        return None
    state = str(xi_state or "").strip()
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **§6-5 — 발표됐으나 미검증인 XI 는 "한 단계 아래"**
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 발표됐으나 미검증인 XI 는 **"미공개"가 아니라 "미검증"으로 적고 한 단계
    #  > 아래.**
    #
    #  ⚠️ 둘을 같은 칸에 넣으면 **고칠 곳이 섞인다**: 미공개는 *기다리면 온다*,
    #     미검증은 *우리가 대조를 못 했다*(§8-6 이 막는 거짓 사유다).
    unverified = state.endswith(UNVERIFIED_MARK)
    if unverified:
        state = state[:-len(UNVERIFIED_MARK)]
    if state not in caps:
        # 🔴 **모르면 가장 센 상한** — 그리고 모른다고 적는다
        #    ⚠️ 수는 `cap_for` 한 곳에서 온다(#1 사본 금지).
        worst = cap_for(state)
        res.notes.append(
            f"🔴 **등급 상한 {worst}** — 라인업 상태를 **못 쟀다**"
            f"(받은 값 {state!r}). 모르면 가장 센 상한을 건다(fail-closed)")
        return worst
    cap = cap_for(state)       # 🔴 표 읽기는 **한 곳**이다(#1)
    why = ""
    if unverified:
        # 🔴 **한 단계 아래** — 사다리로 내린다(산수로 짓지 않는다)
        down = step_down(cap)
        why = (f" · 🔴 XI 가 **발표됐으나 미검증**이다(§6-5) → 한 단계 아래 "
               f"{cap} → **{down}**")
        cap = down
    res.notes.append(
        f"🔴 **5단계 라인업 상태 `{state}` → 등급 상한 {cap}** — "
        f"{cfg.get('why')} (출처: {str(cfg.get('source') or '').strip()}){why}")
    return cap if cap < 1.0 else None


def _one(res: Result, m: Market, drafts: list, w: dict, total: float, game,
         probs: dict | None, fold: set[str] | None = None,
         cap: float | None = None) -> dict:
    """마켓 하나. 🔴 **기호를 시나리오별로 남긴다** — 왜 그 수가 나왔는지 보이게."""
    alive, dead, marks = [], [], {}
    got = 0.0
    unread = 0
    for d in drafts:
        sym, ratio, bad = apply(m, d.scores, home=game.home, away=game.away,
                                sport=game.sport, probs=probs)
        marks[d.id] = sym
        unread += bad
        if sym == "?":
            # 🔴 못 읽은 집합은 **분모에서 뺀다** — 틀린 것으로 세지 않는다
            continue
        got += w[d.id] * ratio
        (alive if ratio > 0 else dead).append(d.id)
    denom = sum(w[d.id] for d in drafts
                if marks[d.id] != "?") or total
    sv = round(min(1.0, got / denom), 4)
    vd = _verdict(sv)
    # 🔴 **손익분기 veto**(사용자 지시 2026-10-02). 격자 확률이 `BREAK_EVEN` 아래면
    #    이름을 적지 않는다 — 맞을 확률보다 틀릴 확률이 큰 자리다.
    #    ⚠️ 격자가 없으면 veto 가 없다(물을 수가 없다). 그 사실이 기록에 남는다.
    pm = _p_market(m, game, probs)
    if vd != "none" and pm is not None and pm < BREAK_EVEN:
        res.notes.append(
            f"🔴 손익분기 veto — {name_of(m)}: survival {sv}({vd}) 이지만 격자 "
            f"전체 확률이 {pm} 로 {BREAK_EVEN} 아래다. 맞을 확률보다 틀릴 확률이 "
            f"큰 자리에 이름을 적지 않는다 → **등급을 거둔다**")
        vd = "none"
    # 🔴 §7 R6 — *"+1.5 마켓 계산 시 0-2 스코어 시나리오 없으면 **실패**."*
    #    깨질 시나리오가 아예 없는 핸디는 생존이 1.0 로 **보이기만** 한다.
    # 🔴 **상한** — 확정 XI 가 없으면 그 위의 등급을 주지 않는다(위 주석)
    if cap is not None and vd != "none" and sv > cap:
        want = _verdict(cap)
        if want != vd:
            res.notes.append(
                f"🔴 §5단계 상한 {cap} — {name_of(m)}: survival {sv}({vd}) 이지만 "
                f"라인업을 그만큼 모른다 → **{want}** 로 내린다")
            vd = want
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **확률이 아니면 `소액` 을 주지 않는다** (사용자 지적 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 이거는 둘다 핸디잖아..말이 안되는 결론이지 않니?
    #
    #  실측(콜롬비아 vs 파라과이 친선): 격자가 없어 무게가 **§5-d 근거 합**이었고,
    #  `Colombia +1.5` 와 `Paraguay +1.5` 가 **둘 다 0.9545 → 소액**으로 나왔다.
    #
    #  🔴 그 `0.9545` 는 확률이 아니다 — *"내가 세운 이야기들의 근거 비중 중 4/5가
    #     살았다"* 는 뜻이다. 그런데 `SMALL_AT`(0.8)은 **확률의 선**이다(§6-b 가
    #     손익분기 위라는 뜻으로 그 수를 쓴다). 둘을 같은 자로 재면 거짓이 된다.
    #  ⚠️ 그리고 격자가 없으면 **손익분기 veto 가 물을 데가 없다**(아래) — 즉 그
    #     자리에서는 0.8 밴드를 **아무것도 막지 않는 채로** 쓰고 있었다.
    #
    #  🔴 `1.0`(= `name`)은 다르다: *"죽는 시나리오가 0건"* 은 무게와 무관한
    #     **논리적 사실**이다. 그래서 그것만 남긴다.
    #
    #  ⚠️ **순서가 뜻을 가진다 — 이 가드가 상한 뒤에 온다.** 상한(확정 XI 없음)이
    #     `name` 을 `small` 로 내리는데, 무게가 확률이 아니면 그 `small` 은 줄 수
    #     없는 등급이다. 가드가 먼저 돌면 상한이 그 금지를 **우회한다** —
    #     실측 2026-10-03 에 계약이 그 모순을 잡았다(`홈 승 1.0 → small`).
    #  🔴 그래서 둘이 함께 걸리면 **아무 등급도 안 준다**: 확정 XI 도 없고 확률
    #     격자도 없으면 이름을 적지 않는다. 그것이 정직한 답이다.
    #  ══════════════════════════════════════════════════════════════════
    #  🔴🔴 **예외를 `vd` 가 아니라 `sv` 로 본다** (실측 2026-10-03)
    #  ══════════════════════════════════════════════════════════════════
    #
    #  위 문단이 제 예외를 이미 적어 뒀다 — *"`1.0`(죽는 시나리오 0건)은 무게와
    #  무관한 **논리적 사실**이라 그것만 남긴다."* ⚠️ 그런데 검사가 `vd` 를 봤고,
    #  **바로 앞의 §5단계 상한이 `name` 을 `small` 로 바꿔 놓는다.** 그래서 그
    #  예외가 **닿지 못했다.**
    #
    #  🔴 실측(엘살바도르 vs 자메이카): `언더 3.5` 가 **다섯 시나리오에서 하나도
    #     안 죽었는데**(생존 1.0) 등급이 `none` 이었고, 결론이 *"살아남는 마켓
    #     없음"* 이었다. 그 문장은 거짓이다 — 죽는 시나리오가 0건인 줄이 있었다.
    #  ⚠️ 두 규칙이 말하는 의심이 **서로 다르다**: 상한은 *"라인업을 모른다"* 이고
    #     가드는 *"이 수는 확률이 아니다"* 다. 생존 1.0 은 **두 번째 의심에 해당하지
    #     않는다**(무게를 어떻게 세든 죽는 칸이 0개다). 첫 번째 의심은 그대로 남아
    #     `name` 이 `small` 로 내려간 것으로 이미 반영돼 있다.
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **이 가드를 걷었다** — 사용자 결정 2026-10-04 (②)
    # ══════════════════════════════════════════════════════════════════
    #
    #  종전 가드: *"무게가 확률이 아니면 `small`(0.8 선)을 주지 않는다 — §6-b 의
    #  소액 선은 **확률의 선**이고, 격자가 없으면 그 수는 확률이 아니다."*
    #
    #  ⚠️ 그 전제가 ②로 무너졌다. 사용자 결정:
    #
    #  > v4 §5-a 는 **시나리오 strength = 변수 weight 합**이라고 적혀 있다.
    #  > 포아송 격자는 **v4 에 없는 봇의 추가물**이다 … 변수 → strength, 이게
    #  > **생존율을 정한다.**
    #
    #  🔴 §6-b(0.8·1.0)와 §5-a(strength)는 **같은 문서의 같은 설계**다 — v4 는 제
    #     무게에 제 문턱을 쓰라고 적었다. *"0.8 은 확률의 선"* 이라는 말은 봇이
    #     격자를 들여온 뒤에 **봇이 지어낸 단서**이고, 격자를 생존에서 뺀 지금
    #     그 단서는 §6-b 를 **통째로 막는** 것이 된다(무게가 늘 strength 이므로).
    #
    #  ⚠️ **이것은 봇을 느슨하게 만든다** — 종전에는 생존 1.0 에만 소액이 붙었고,
    #     이제 0.8 이상이면 붙는다. 🔴 그 사실을 사용자에게 보고할 것으로 적어 둔다.
    #     막는 것은 여전히 넷이다: §5단계 상한(확정 XI 없음) · §7 R6(2골 차 시나리오
    #     없음) · M18(야구 선발 모름) · 거짓 1.0 계약(변수 5개 미만).
    #  🔴 되돌리려면 **여기 한 곳**이다(`git log` 로 이 문단을 찾는다).
    # 🔴🔴 §4 `fold_win_markets` — **접힌 마켓은 이름을 적지 않는다**.
    #
    #  ⚠️ 2026-10-02 까지 이 규칙이 장식이었다: `event_match` 의 `attaches_to` 에
    #     `fold_win_markets` 가 적혀 있었고 **읽는 코드가 없었다.**
    #  🔴 생존은 그대로 센다 — 지우지 않고 **등급만 거둔다.** 왜 안 적었는지가
    #     기록에 남아야 한다(#3 조용한 0 금지).
    if fold and m.market_type in fold:
        if vd != "none":
            res.notes.append(
                f"🔴 §4 fold_win_markets — {name_of(m)}: survival {sv}({vd}) 이지만 "
                f"**행사·소화 경기라 승패를 접는다** → 등급을 거둔다")
        vd = "none"
    # 🔴 §7 R6 — *"+1.5 마켓 계산 시 0-2 스코어 시나리오 없으면 **실패**."*
    #    깨질 시나리오가 아예 없는 핸디는 생존이 1.0 로 **보이기만** 한다.
    r6 = _r6_missing(m, drafts, game)
    if r6:
        res.notes.append(
            f"🔴 §7 R6 — {name_of(m)}: {r6} 시나리오가 없다. 깨질 자리가 없으니 "
            f"survival {sv} 는 뜻이 없다 → **등급을 매기지 않는다**")
        vd = "none"
    ms = MarketSurvival(market_type=m.market_type, team=m.team, line=m.line,
                        alive_scenarios=alive, dead_scenarios=dead,
                        survival=sv, verdict=vd)
    res.markets.append(ms)
    row = {"name": name_of(m), "market": m, "survival": sv,
           "verdict": ms.verdict, "marks": marks, "unread": unread,
           "p_market": pm,
           # 🔴 **어느 마켓의 한 쪽인가** — 카드가 마켓 단위로 묶어 그린다
           "market_key": market_key(m)}
    # §6-c-2 — 보드 밖인데 1.0 이면 **따로** 적는다(결론 줄과 섞지 않는다)
    return row


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **거짓 1.0 계약** — 사용자 수정 ⑤ (2026-10-04)
# ══════════════════════════════════════════════════════════════════
#
#  > 변수가 **5개 미만**인 경기에서 어떤 마켓이든 **생존 1.0** 이 나오면 카드를
#  > 내지 말고 *"시나리오 세트 불완전"* 으로 **실패**. 그리고 양 팀 폼 변수에
#  > *"연속 득점"* 이 있으면 **대량득점·난타전 시나리오가 없을 때 실패**.
#
#  🔴 왜 — 사용자 진단 2026-10-04:
#
#  > 변수가 폼·h2h뿐이면 시나리오 엔진은 **매번 같은 세트**를 만든다 — *"최근 N승
#  > N패"* 로는 A/B/C 가 갈리지 않는다. 그래서 **어떤 경기를 넣어도 언더 3.5 1.0**
#  > 이 나온다. 그 1.0 은 크로아티아 카드 때와 **같은 거짓 1.0** 이다 — 대량득점
#  > 시나리오가 없어서 **안 죽는 것뿐**이다.
#
#  ⚠️ 실측 2026-10-04(북마케도니아 vs 스코틀랜드): 변수 **3개**(h2h 1 · 폼 2),
#     그때의 시나리오 **다섯**(당시 글자가 A~E 였다 · 결정 ① 이전)의 스코어가
#     `2-1·1-0·0-1·1-2·0-0·1-1·2-0·0-2` — **최대 3골**이다.
#     그래서 `오버 3.5` 가 생존 **0.0** 이고 `언더 3.5` 가 **1.0** 이 됐다.
#     🔴 그 1.0 은 *"죽는 시나리오가 0건"* 이 아니라 **4골 이상을 아무도 안 그렸다**
#        는 뜻이다. 그 둘은 전혀 다른 말이다.
#
#  🔴 이 저장소에 **같은 모양의 가드가 이미 있다** — `_r6_missing`(§7 R6: `±1.5`
#     핸디는 *"상대가 2골 차로 이기는"* 시나리오가 없으면 셀 수 없다). ⑤는 그것을
#     **일반화**한 것이다. 그래서 이름도 그 결로 짓는다.

#: 🔴 이 수 미만이면 "한 방향짜리 얇은 세트"로 본다(사용자 수정 ⑤).
#   ⚠️ `scenarios.MIN_VARIABLES`(3)와 **다른 수**다 — 그쪽은 *"시나리오를 만드나"*
#      (v4 §7 R5)이고 이것은 *"1.0 을 **발표하나**"* 다. 🔴 사용자가 5 를 지정했다.
def _thin_set_vars() -> int:
    """🔴 §5-6 — 수는 `config/thresholds.yaml` 이 든다(근거와 함께).

    ⚠️ 코드에 박으면 그 수의 **까닭**이 사라진다 — 그것이 `era_gap_min 0.75` 가
       열한 달을 버틴 길이다.
    """
    from app import thresholds
    got = thresholds.value("thin_set_vars")
    return int(got) if got is not None else 5


#: ⚠️ 뒤로 호환 — 읽는 쪽이 상수로 쓰던 자리. 🔴 값은 yaml 이 정한다.
THIN_SET_VARS = _thin_set_vars()


def _thin_set_guard(res: "Result", game, drafts: list, *,
                    n_vars: int | None = None) -> None:
    """🔴🔴 **얇은 변수 세트의 1.0 은 발표하지 않는다**(사용자 수정 ⑤).

    ⚠️ 생존 수는 **그대로 둔다** — 카드가 그 수를 보여야 사람이 왜 막혔는지 안다.
       🔴 거두는 것은 **등급**이다(`verdict`): 1.0 이어도 이름·소액을 주지 않는다.
    """
    if n_vars is None:
        return                     # 🔴 안 넘겨 주면 **막지 않는다**(모른다 ≠ 0)
    ones = [m for m in res.markets if float(m.survival or 0) >= NAME_AT]
    if not ones:
        return
    if int(n_vars) >= THIN_SET_VARS:
        return
    # ⚠️ `MarketSurvival` 에 **이름 칸이 없다**(실측: 계약이 잡았다) — 꼴·팀·줄로
    #    짓는다. 🔴 `res.rows` 쪽에는 `name` 이 있지만 둘이 1:1 이라고 가정하지 않는다.
    names = ", ".join(sorted({
        " ".join(x for x in (str(m.market_type), str(m.team or ""),
                             ("" if m.line is None else str(m.line))) if x)
        for m in ones}))
    for m in ones:
        m.verdict = "none"
    for row in res.rows:
        if float(row.get("survival") or 0) >= NAME_AT:
            row["verdict"] = "none"
    res.notes.append(
        f"🔴🔴 **시나리오 세트 불완전** — 변수가 {n_vars}개뿐인데(최소 "
        f"{THIN_SET_VARS}) 생존 1.0 마켓이 있다({names}). ⚠️ 그 1.0 은 *\"죽는 "
        f"시나리오가 0건\"* 이 아니라 **그 결과를 아무도 안 그렸다**는 뜻이다 — "
        f"폼·맞대결만으로는 시나리오가 경기마다 갈리지 않는다. 🔴 **등급을 거뒀다** "
        f"(사용자 수정 ⑤ 2026-10-04). 생존 수는 그대로 보여 준다")


def _scoring_streak_guard(res: "Result", drafts: list, game) -> None:
    """🔴 **연속 득점이 있는데 난타전 시나리오가 없으면** 1.0 을 발표하지 않는다.

    > 양 팀 폼 변수에 *"연속 득점"* 이 있으면 대량득점·난타전 시나리오가 없을 때
    > 실패 — 이건 **R3 계약이 안 물리고 있다**는 뜻이니 돌연변이로 확인.

    ⚠️ `streak_away_scored` 는 `classify._form_streaks` 가 세어 **사유 글에** 적는다
       (§4 가 *"총점 방향은 변수에 안 붙인다"* 고 해서 방향은 안 바꾼다). 🔴 그래서
       **글에서 읽는다** — 그 사실을 변수에 안 실은 것이 설계이기 때문이다.
    """
    streak = [n for n in res.notes if "연속 득점" in n]
    whys = [w for w in _streak_whys if "연속 득점" in w]
    if not (streak or whys):
        return
    # 🔴 **난타전이 그려졌나** — 한 시나리오라도 양 팀 합계 4골 이상이면 있다
    big = max((sum(_goals(x)) for d in drafts for x in d.scores), default=0)
    if big >= 4:
        return
    ones = [m for m in res.markets if float(m.survival or 0) >= NAME_AT]
    if not ones:
        return
    for m in ones:
        m.verdict = "none"
    for row in res.rows:
        if float(row.get("survival") or 0) >= NAME_AT:
            row["verdict"] = "none"
    res.notes.append(
        f"🔴🔴 **시나리오 세트 불완전** — 폼에 **연속 득점**이 있는데 시나리오 "
        f"최대 합계가 {big}골이다(난타전 없음). ⚠️ 그래서 `언더` 쪽이 "
        f"**죽을 자리가 없어** 1.0 이 됐다 — 그것은 자료가 아니라 **세트의 모양** "
        f"때문이다. 🔴 등급을 거뒀다(사용자 수정 ⑤ 2026-10-04 · §5-c-2 대량득점 "
        f"규칙이 `strength_gap`·`lineup_intent` 미구현으로 발동하지 않는 것이 뿌리다)")


#: 🔴 `_scoring_streak_guard` 가 읽을 **폼 변수 사유 글**. ⚠️ 전역이 아니라
#   `run()` 이 한 번 채우고 가드가 읽는다 — 변수 목록이 `survive` 에 안 들어온다.
_streak_whys: list[str] = []


def _goals(score: str) -> tuple[int, int]:
    """`'2-1'` → `(2, 1)`. 🔴 못 읽으면 `(0, 0)`(지어내지 않는다)."""
    try:
        a, b = str(score).split("-", 1)
        return int(a.strip()), int(b.strip())
    except Exception:                                       # noqa: BLE001
        return 0, 0


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **M18** — 야구는 `pitcher_state` 없이 총점·핸디를 적지 않는다
# ══════════════════════════════════════════════════════════════════
#
#  v4 §15 M18 원문:
#
#  | M18 | KBO 선발 최근 창을 못 찾고도 5경기 시나리오를 냄(09-29) | 자료 없는 축을
#  | "미확인"으로 적고 계속 진행 | **야구는 pitcher_state 변수 없으면 총점·핸디
#  | 마켓 계산 금지** | 계약: pitcher_state 없는 야구 경기에 total/handicap
#  | verdict name 이면 실패 |
#
#  🔴 **그 계약이 코드에 없었다**(실측 2026-10-04 · 전수 검색). v4 가 *"계약"* 이라고
#     적어 둔 것이 네 번째 줄에만 있고 `app/` 에는 한 글자도 없다 — v4 §15 가
#     막으려던 바로 그 꼴이다(CLAUDE.md #2 배선).
#
#  사용자 지시 2026-10-04:
#
#  > 야구 포스트시즌 1차전 카드에 `pitcher_state` 변수가 0개다 … 카드는 밀워키
#  > -0.5·샌디에이고 +1.5 생존율을 **계산해서 냈다.** 결론이 "없음"이라 돈은 안
#  > 나갔지만, **계약이 안 물린 것이다.**
#
#  ⚠️ 사용자의 읽기가 v4 보다 **엄하다**: v4 는 `verdict name` 만 금지하고, 사용자는
#     *"총점·핸디 **결론** 금지"* 라고 한다. 🔴 **직접 지시가 이긴다** — `small` 도
#     막는다(소액도 결론이다 · §6-b 가 돈을 걸라는 말이다).
#  🔴 **생존 수는 그대로 둔다** — 사람이 그 수를 봐야 왜 막혔는지 안다. 거두는 것은
#     **등급**이고, 그 사실을 사유로 적는다(#3 조용한 0 금지).

#: 🔴 M18 이 거는 종목. ⚠️ v4 가 *"야구는"* 이라고 적었다 — 축구·하키는 선발이
#   그렇게 결정적이지 않다(그 종목에 선발 투수가 없다).
M18_SPORTS = ("baseball",)

#: 🔴 M18 이 막는 마켓. ⚠️ v4 가 *"총점·핸디"* 라고 이름을 댔다.
M18_MARKETS = ("total", "handicap")


def _m18_guard(res: "Result", game, *, variables: list | None = None) -> None:
    """🔴🔴 **M18** — 야구에서 `pitcher_state` 변수가 없으면 총점·핸디 등급을 거둔다.

    ⚠️ `variables` 를 **안 주면 막지 않는다** — 모르는 것과 0 은 다르다.
    🔴 `pitcher_state` 가 **배경**(유형은 붙었지만 방향이 없다)인 것도 **없는 것**으로
       센다. v4 가 *"pitcher_state **변수**"* 라고 적었고, 방향이 없으면 변수가 아니다.
       ⚠️ 실측 2026-10-04: 두 선발 방어율 2.47 vs 3.21 — 차이 0.74 가 문턱 0.75 에
          0.01 모자라 `비슷하다고 본다` 로 떨어졌다. 그것은 **변수가 아니다.**
    """
    if variables is None:
        return
    sport = str(getattr(game, "sport", "") or "")
    if sport not in M18_SPORTS:
        return
    # 🔴🔴 **방향까지 선 것만** 센다(v4 가 *"pitcher_state **변수**"* 라고 적었다).
    #    ⚠️ 내 첫 판은 `type` 만 봤다 — 그런데 **배경**도 `type` 은 `pitcher_state` 다
    #       (`차이 0.74 < 문턱 0.75 · 비슷하다고 본다`). 그러면 M18 이 뚫린다.
    #    🔴 `tests/test_m18.py` 가 그 자리를 잡았다 — 그것이 가장 흔한 꼴이다.
    #    ⚠️ `is_variable` 이 없는 대역이 올 수도 있으니 **방향도 함께** 본다.
    for v in variables:
        if str(getattr(v, "type", "")) != "pitcher_state":
            continue
        ok = getattr(v, "is_variable", None)
        if ok is None:
            ok = bool(getattr(v, "direction", None))
        if ok:
            return
    hit = [m for m in res.markets
           if str(m.market_type) in M18_MARKETS and str(m.verdict) != "none"]
    for m in hit:
        m.verdict = "none"
    for row in res.rows:
        mk = row.get("market")
        if mk is not None and str(getattr(mk, "market_type", "")) in M18_MARKETS:
            row["verdict"] = "none"
    res.notes.append(
        f"🔴🔴 **M18** — `{sport}` 경기인데 `pitcher_state` **변수가 없다** → "
        f"총점·핸디 마켓에 **등급을 주지 않는다**"
        + (f"(거둔 줄 {len(hit)}개)" if hit else "(거둘 줄이 없었다)")
        + ". ⚠️ 야구에서 선발은 변수 하나가 아니라 **변수의 절반**이다 — 그것을 "
          "모르고 총점·핸디를 적으면 그 수는 뜻이 없다(v4 §15 M18 · 사용자 지시 "
          "2026-10-04). 🔴 생존 수는 그대로 보여 준다")


def _rule_handicap_line(rule: dict) -> float | None:
    """§7 R6 이 말하는 **핸디 기준선**. 🔴 규칙 글에서 숫자를 읽는다 — 베끼지 않는다.

    ⚠️ 규칙 원문이 *"핸디 +1.5가 후보 마켓이다"* 다. 그 숫자가 바뀌면 여기가 따라간다.
    """
    import re as _re
    blob = " ".join(str(v) for v in rule.values())
    got = _re.findall(r"[+-]?\d+\.\d", blob)
    return abs(float(got[0])) if got else None


def _r6_missing(m: Market, drafts: list, game) -> str:
    """§7 R6 — `±1.5` 핸디는 **상대가 2골 차로 이기는 시나리오**가 있어야 센다.

    🔴 09-29 돗토리·후쿠시마가 그것을 빠뜨렸다가 1.0 → 0.85 로 내려갔다. 없으면
       **생존을 셀 수 없다**(계산 실패) — 1.0 으로 보이지만 깨질 자리가 없는 1.0 이다.
    ⚠️ 빈 문자열이면 문제 없음이다.
    """
    if m.market_type != "handicap" or m.line is None:
        return ""
    # 🔴 **§7 번호로 규칙을 찾는다**(`rules.by_sec7_rule`) — `1.5` 와 `2` 를 코드에
    #    박지 않는다. §9 단계 6 이 교차 규칙을 **§7 번호로** 지목하므로 그 문이 원본이다.
    #    ⚠️ 규칙이 없으면 가드를 걸지 않는다 — 없는 규칙을 집행하지 않는다.
    rule = rules.by_sec7_rule("R6")
    if not rule:
        return ""
    line = _rule_handicap_line(rule)
    if line is None or abs(float(m.line)) < line:
        return ""
    side = _side(m, game.home, game.away)
    if side is None:
        return ""
    # `+1.5` 는 **상대가 2골 차로 이겨야** 죽는다. `-1.5` 는 **내가 2골 차로 이겨야**
    # 산다 — 둘 다 "2골 차 승" 시나리오를 요구하지만 방향이 다르다.
    need = ("away" if side == "home" else "home") if float(m.line) > 0 else side
    from app.scenarios import _wins_by
    margin = int(round(line + 0.5))     # 🔴 ±1.5 는 **2골** 차다(§6-a)
    if any(_wins_by(x, need, margin) for d in drafts for x in d.scores):
        return ""
    return f"{need} 가 {margin}골 차로 이기는"


def _p_market(m: Market, game, probs: dict | None) -> float | None:
    """🔴 **격자 전체**에서 그 마켓이 맞을 확률. 지어낸 수가 아니다.

    ⚠️ `survival` 과 **다른 것을 뜻한다**: `survival` 은 *"내가 세운 이야기들 중"*,
       이것은 *"실제로"* 다. 둘이 벌어지면 `_coverage_warning` 이 말한다.
    """
    if not probs:
        return None
    grid = probs.get("scores") or {}
    hit = 0.0
    for sc, p in grid.items():
        ok = passes(m, sc, home=game.home, away=game.away, sport=game.sport)
        if ok is None:
            return None
        if ok:
            hit += float(p)
    return round(hit, 4)


def _by_line(res: Result, m: Market, drafts: list, w: dict, total: float,
             game, probs: dict | None = None) -> None:
    """§6-f — **기준선별 생존**을 함께 적는다.

    *"언더 X.5 (기준선 Y.5면 △, Z.5면 ✗)"* — 사용자가 다른 북을 봐도 대입할 수 있게.
    🔴 ±1 골 두 칸만 본다. 더 넓히면 카드가 표가 된다.
    """
    if m.line is None:
        return
    out = []
    for ln in (float(m.line) - 1.0, float(m.line), float(m.line) + 1.0):
        if ln <= 0:
            continue
        alt = Market(market_type="total", team=m.team, line=ln)
        got = denom = 0.0
        for d in drafts:
            sym, ratio, _ = apply(alt, d.scores, home=game.home,
                                  away=game.away, sport=game.sport,
                                  probs=probs)
            if sym == "?":
                continue
            got += w[d.id] * ratio
            denom += w[d.id]
        if denom:
            sv = round(min(1.0, got / denom), 4)
            out.append({"line": ln, "survival": sv, "verdict": _verdict(sv)})
    if out:
        res.by_line.append({"name": name_of(m), "lines": out})


def _coverage_warning(res: Result) -> None:
    """🔴 **`survival` 이 무엇 안의 비율인지 말한다.**

    덮은 확률이 1 보다 작으면 `survival 1.0` 은 *"덮은 것 안에서 1.0"* 이다. 그
    사실을 적지 않으면 과신이 된다 — 내가 전 판에 그렇게 읽었다.
    """
    if res.coverage is not None and res.coverage < 0.999:
        res.notes.append(
            f"🔴 survival 은 **덮은 확률 {res.coverage} 안의 비율**이다 — "
            f"어느 시나리오에도 없는 결과 {round(1 - res.coverage, 4)} 는 이 수에 "
            f"들어 있지 않다. 아래 `p_market`(격자 전체에서 맞을 확률)과 비교하라")
    for r in res.rows:
        p = r.get("p_market")
        # 🔴 **양쪽을 다 본다.** 전 판은 등급이 붙은 줄만 봤다 — 그러면 *"실제론
        #    62% 인데 survival 41% 로 이름을 못 적은"* 자리가 **조용히** 지나간다.
        #    놓친 call 도 틀린 call 과 똑같이 손해다.
        #
        # ══════════════════════════════════════════════════════════
        # 🔴 **문턱을 없앴다** (사용자 지시 2026-10-02)
        # ══════════════════════════════════════════════════════════
        #  전 판은 `0.15` 로 물었고 그것은 **지어낸 값이었다**(그렇게 적어 뒀다).
        #  이제 **등급으로 묻는다** — 두 수가 §6-b 의 **다른 밴드**에 떨어지면
        #  경고한다. 숫자가 하나도 없고, §6-b 가 이미 정한 선을 그대로 쓴다.
        if p is not None and _verdict(p) != r["verdict"]:
            which = "낮게" if r["survival"] < p else "높게"
            res.notes.append(
                f"⚠️ {r['name']}: survival {r['survival']}→{r['verdict']} 인데 "
                f"격자 전체 확률 {p}→{_verdict(p)} 다 — **등급 밴드가 다르다**"
                f"(survival 이 {which} 나온다). 시나리오가 분포를 덜 덮어서 생기는 "
                f"간격이다")
        if r["unread"]:
            res.notes.append(
                f"⚠️ {r['name']}: 못 읽은 스코어 {r['unread']}건 — 분모에서 뺐다")
        # 🔴 §5-b 템플릿이 **기준선을 가로지르면** 그 시나리오는 영영 △ 다
        straddle = [i for i, m in r["marks"].items() if m == PART]
        if r["market"].market_type == "total" and straddle:
            res.notes.append(
                f"🔴 {r['name']}: 시나리오 {straddle} 가 기준선을 **가로지른다** "
                f"(한 집합에 오버 스코어와 언더 스코어가 같이 있다) — §5-b 템플릿의 "
                f"모양 때문이고, 그런 시나리오가 있으면 이 마켓은 **1.0 에 닿을 수 "
                f"없다**")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 채점 — **실제 결과로** 센다 (사용자 지시 2026-10-02)
# ══════════════════════════════════════════════════════════════════
#
# > 정답지는 없다... 정답은 없는거다... 명심해라... 정답지는 지운다...
# > 데이타가 쌓이고 그럼 그거가지고 분석을 하고... 스포츠는 정답이 없는거다...
#
# 🔴 그래서 *"페이블의 분석과 같은가"* 를 묻지 않는다. 묻는 것은 하나다:
#    **경기가 끝난 뒤, 우리가 이름을 적은 마켓이 맞았나.**
#
# ⚠️ 이 함수는 **예측을 고치지 않는다.** §3 은 *"결과 후 survival.json 수정 금지
#    (불변)"* 이다 — 채점은 **따로** 쌓인다(`ledger` 표). 그래야 "그때 무엇을
#    냈는가"와 "그것이 맞았나"가 서로를 못 바꾼다.


def grade(markets: list, drafts: list, home_score: int, away_score: int, *,
          game, probs: dict | None = None) -> dict:
    """실제 스코어로 채점한다. 🔴 **맞춘 것과 틀린 것을 둘 다** 들고 온다.

    돌려주는 것:
      `{"result": "3-2", "verdicts": [{market, verdict, hit}…],
        "realized": "D", "named": n, "hit": n, "notes": [...]}`
    ⚠️ `realized` 는 **실제 스코어를 담은 시나리오**다. 없으면 `None` —
       *"어느 시나리오에도 없던 결과"* 이고 그것이 가장 값진 기록이다.
    """
    score = f"{int(home_score)}-{int(away_score)}"
    out: dict = {"result": score, "verdicts": [], "realized": None,
                 "named": 0, "hit": 0, "notes": []}
    for ms in markets:
        m = Market(market_type=ms.market_type, team=ms.team, line=ms.line)
        ok = passes(m, score, home=game.home, away=game.away, sport=game.sport)
        row = {"market": name_of(m), "verdict": ms.verdict,
               "survival": float(ms.survival), "hit": ok}
        out["verdicts"].append(row)
        if ms.verdict in ("name", "small"):
            out["named"] += 1
            if ok:
                out["hit"] += 1
        if ok is None:
            out["notes"].append(f"{name_of(m)}: 스코어를 대입할 수 없다 — 채점 못 함")
    hit_ids = [d.id for d in drafts if score in d.scores]
    if hit_ids:
        out["realized"] = hit_ids[0]
        if len(hit_ids) > 1:
            out["notes"].append(
                f"결과 {score} 가 시나리오 {hit_ids} 에 겹쳐 있다 — 첫 것을 적는다")
    else:
        # 🔴 **이 줄이 가장 값지다** — 우리가 그 결과를 아예 그리지 않았다는 기록이다
        out["notes"].append(
            f"🔴 결과 {score} 는 **어느 시나리오에도 없었다** — 시나리오 "
            f"{[d.id for d in drafts]} · 덮인 스코어 "
            f"{sorted({s for d in drafts for s in d.scores})}")
    if probs:
        p = (probs.get("scores") or {}).get(score)
        if p is not None:
            # 🔴 그때 우리가 그 결과에 **얼마를 줬나.**
            #    ⚠️ 이 수로 **모형을 맞추지 않는다**(사용자 지시 2026-10-02 —
            #       *"검증하는 방법으로만"*). 보는 것은 *"우리 수가 그 말을 했나"* 다.
            out["result_probability"] = round(float(p), 6)
    return out
