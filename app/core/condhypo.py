"""🔴🔴 **조건부 가설** — 사용자 지시 2026-10-11(측정 불가를 조건으로) ③.

> 데이터만으로 예측 불가능한 영역 … **조건부 시나리오를 더 쓴다** — 측정 불가
> 요인(동기·피로·결장 다수)을 **숫자로 바꾸지 말고** 가설의 **조건**으로 넣는다.

⚠️ 왜 — 실측 2026-10-11(쇼난): `⬜ 가설이 없다 — DeepSeek 단계가 못 돌았거나 근거
   변수가 0개다` → 시나리오 일곱 줄이 전부 `🔴 지지된 가설이 없다(무게만 있다)` 였다.
   🔴 모델이 못 쓰면 **그 경기에는 가설이 아예 없다** — 그러면 시나리오도 근거를
   잃고, 최종 평도 쓸 것이 없다.

🔴 **이 파일의 규율 셋**
  ① **시뮬을 보지 않는다**(C3: 가설은 단계 3 결과를 입력으로 받지 않는다) — 변수만 본다.
  ② 줄마다 **검증 가능한 신호**를 단다 — 신호는 `signals.METRICS` 안의 것만 쓰고
     기준은 **고정 수**다(시뮬에서 따온 수를 쓰지 않는다).
  ③ **측정 불가 요인은 확률에 닿지 않는다** — 여기서 만드는 것은 *가설*이고,
     확률은 상성 축만 움직인다(C7).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 🔴 조건부 가설이 쓰는 **고정 기준**. ⚠️ **임시값**이고 시뮬에서 따오지 않는다.
#
#  뜻: 그 팀이 먼저 넣었을 때 이길 확률이 이보다 낮으면 *"리드를 못 지킨다"* 다.
HOLD_MIN = 0.55
#: 🔴 후반 구간 득점이 리그 평균의 이 몫보다 낮으면 *"후반에 식는다"* 다
LATE_LOW = "리그평균*0.3"
#: 🔴 무득점 확률이 이보다 높으면 *"침묵한다"* 다
MUTE_HI = 0.30


def _side_of(ref, key: str) -> str:
    return "home" if str(key) == str(getattr(ref, "home", "")) else "away"


def _name(ref, side: str) -> str:
    return str(getattr(ref, f"{side}_name", "") or side)


def lines(ref, variables: list) -> list:
    """🔴🔴 ③ — 측정 불가 변수들 → **조건부 가설**(팀별). 없으면 빈 목록.

    보는 유형 셋(지금 봇이 실제로 내는 것):
      · `stakes`     — 연패 간절함·동기 → *"먼저 넣으면 지킨다 / 먼저 먹히면 무너진다"*
      · `fatigue`    — 일정 과부하 → *"후반에 식는다"*
      · `squad_rotation`·결장 계열 — *"침묵할 수 있다"*
    ⚠️ 그 유형이 하나도 없으면 **빈 목록**이다(지어내지 않는다 · #4).
    """
    from app.core.schema import Hypothesis, HypoLine, Signal
    box: dict[str, dict[str, list]] = {}

    def _put(side: str, where: str, text: str, vid: str, sig) -> None:
        got = box.setdefault(side, {"reasons": [], "breaks": []})
        got[where].append(HypoLine(text=text, var_ids=[vid], signal=sig))

    for v in (variables or []):
        kind = str(getattr(v, "type", "") or "")
        key = str(getattr(v, "subject", "") or "")
        vid = str(getattr(v, "id", "") or "")
        if not vid or not key:
            continue
        side = _side_of(ref, key)
        who = _name(ref, side)
        if kind == "stakes":
            # 🔴 간절함은 **방향이 아니라 갈림**이다 — 두 조건을 다 세운다
            _put(side, "reasons",
                 f"{who} 는 **먼저 득점하면** 그 리드를 지키려 내려선다 — "
                 f"간절한 팀의 선제골은 경기를 닫는 쪽으로 쓴다({vid})",
                 vid, Signal(metric="선제골후승리", direction=">=",
                             ref=str(HOLD_MIN), side=side))
            _put(side, "breaks",
                 f"{who} 는 **먼저 실점하면** 무너진다 — 간절함이 급함으로 바뀌어 "
                 f"뒤를 열고 나간다({vid})",
                 vid, Signal(metric="선제골후승리", direction="<",
                             ref=str(HOLD_MIN), side=side))
        elif kind in ("fatigue", "travel_schedule"):
            _put(side, "breaks",
                 f"{who} 는 **후반으로 갈수록 식는다** — 일정 부담이 60분 뒤에 "
                 f"나타난다({vid})",
                 vid, Signal(metric="구간득점", direction="<", ref=LATE_LOW,
                             side=side, arg="61-90+"))
        elif kind in ("squad_rotation", "absence", "absence_att",
                      "def_absence", "suspension"):
            _put(side, "breaks",
                 f"{who} 는 **빠진 자리가 메워지지 않으면 침묵한다** — 그 경로가 "
                 f"막히면 한 골도 못 넣는 쪽으로 간다({vid})",
                 vid, Signal(metric="무득점확률", direction=">",
                             ref=str(MUTE_HI), side=side))
    out = []
    for side in ("home", "away"):
        got = box.get(side)
        if not got:
            continue
        out.append(Hypothesis(team=side,  # type: ignore[arg-type]
                              reasons=got["reasons"][:3],
                              breaks=got["breaks"][:3]))
    return out


def said_of(rows: list) -> str:
    """🔴 보고·상태 기록이 적는 한 줄."""
    n = sum(len(h.reasons) + len(h.breaks) for h in (rows or []))
    return (f"조건부 가설 {len(rows or [])}팀 · {n}줄"
            if rows else "조건부 가설 0줄(측정 불가 변수가 없다)")
