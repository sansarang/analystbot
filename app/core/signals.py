"""🔴🔴 **예측 신호 — 지표 목록과 대조**. 순서 재편 지시서(2026-10-10 다섯째).

> §2-2 … 각 가설은 반드시 시뮬레이션으로 **확인할 수 있는 신호**를 단다:
> `{가설 문장, 근거 변수 id, 예측 신호 = 지표·방향·기준}`
> **쓸 수 있는 지표 목록은 코드가 준다**(기대득점·무득점 확률·시간대 득점·선제골
> 후 결과·스코어 분포·승무패·오버). **목록 밖 지표 금지.**
> §4-1 가설마다 예측 신호를 시뮬레이션 출력과 대조(코드): **지지 / 반박 /
> 판단 불가**(지표 없음·표본 부족).

🔴 이 파일이 하는 일 셋:
  ① **허용 목록**(`METRICS`)과 그 설명 글(`menu`) — 프롬프트가 그대로 쓴다
  ② 시뮬 산출에서 그 지표를 **읽는다**(`value_of`)
  ③ 신호와 값을 **대조**한다(`check`) — 판정 셋 중 하나와 사유

🔴 **확률을 만들지 않는다** — 읽고 견주기만 한다(LLM 이 확률을 못 움직인다는 원칙).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 🔴 판정 세 글자(§4-1)
OK, NO, NA = "지지", "반박", "판단 불가"
#: 🔴 방향 글자
DIRS = (">", "<", ">=", "<=")

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 ① **허용 지표** — 지시서가 적은 일곱
# ══════════════════════════════════════════════════════════════════
#
#  칸 뜻: `side` 가 참이면 팀을 지정해야 한다 · `arg` 는 덧붙는 인자의 뜻이다.
#  🔴🔴 `unit` — **골 수**(`goals`)인가 **확률**(`prob`)인가. ⚠️ 실사고
#     2026-10-10: 모델이 `무득점확률 > 리그평균` 을 냈고 검증이 **0.20 > 1.26** 을
#     견주어 *"반박"* 이라 적었다 — 단위가 다르면 그 비교는 **뜻이 없다**.
METRICS: dict[str, dict] = {
    "기대득점": {"side": True, "arg": "", "unit": "goals",
                 "why": "그 팀 기대 득점(분포 평균)"},
    "무득점확률": {"side": True, "arg": "", "unit": "prob",
                   "why": "그 팀이 **한 골도 못 넣을** 확률"},
    "구간득점": {"side": True, "arg": "구간(`0-30`·`31-60`·`61-90+`)",
                 "unit": "goals", "why": "그 팀의 **그 구간** 기대 득점"},
    "선제골후승리": {"side": True, "arg": "", "unit": "prob",
                     "why": "그 팀이 **선제골을 넣었을 때** 이길 확률"},
    "승무패": {"side": False, "arg": "`home`·`draw`·`away`", "unit": "prob",
               "why": "그 결과의 확률"},
    "오버": {"side": False, "arg": "줄(`1.5`·`2.5`·`3.5`)", "unit": "prob",
             "why": "총골이 그 줄을 넘을 확률"},
    "스코어": {"side": False, "arg": "스코어(`1-0`)", "unit": "prob",
               "why": "그 스코어의 확률"},
}
#: 🔴 기준에 쓸 수 있는 **말**(수 말고)
REFS = ("상대", "리그평균")
#: 🔴🔴 `리그평균` 은 **골 단위 지표에만** 쓴다(그 수가 경기당 한 팀 기대 득점이다)
LEAGUE_OK = tuple(k for k, v in METRICS.items() if v["unit"] == "goals")


def menu() -> str:
    """🔴 프롬프트에 넣는 **지표 목록 글**. ⚠️ 표에서 자라게 한다(사본 금지)."""
    rows = [f"- `{k}`{' (팀 지정)' if v['side'] else ''}"
            + (f" · 인자: {v['arg']}" if v["arg"] else "")
            + f" — {v['why']}"
            for k, v in METRICS.items()]
    return ("\n".join(rows)
            + f"\n- 기준(`ref`)은 **수**(`0.35`) 또는 {', '.join(REFS)} 이고, "
              "`리그평균*0.7` 처럼 곱해 쓸 수 있다.\n"
              f"- 🔴🔴 `리그평균` 은 **{' · '.join(LEAGUE_OK)}** 에만 쓴다"
              "(그 수는 **경기당 한 팀 기대 득점**이다). **확률 지표**"
              "(무득점확률·승무패·오버·스코어·선제골후승리)에는 쓰지 마라 — "
              "단위가 달라 버려진다. 확률에는 **수**(`0.35`)나 `상대` 를 쓴다.\n"
              f"- 방향(`direction`)은 {' · '.join(DIRS)} 중 하나다.")


def known(metric: object) -> bool:
    """🔴 §계약 — **허용 목록 안**인가."""
    return str(metric or "") in METRICS


def bad_signal(sig) -> str:
    """🔴 신호가 **쓸 수 있는 꼴**인가 — 어긋나면 사유 글자, 멀쩡하면 빈 글자."""
    if sig is None:
        return "🔴 예측 신호가 없다 — 검증할 수 없는 가설이다(§2-2)"
    metric = str(getattr(sig, "metric", "") or "")
    if not known(metric):
        return (f"🔴 **목록 밖 지표**(`{metric}`) — 쓸 수 있는 것은 "
                f"{sorted(METRICS)} 뿐이다")
    box = METRICS[metric]
    if str(getattr(sig, "direction", "") or "") not in DIRS:
        return f"🔴 방향이 이상하다(`{getattr(sig, 'direction', '')}`)"
    if box["side"] and str(getattr(sig, "side", "") or "") not in ("home",
                                                                  "away"):
        return f"🔴 `{metric}` 은 **팀을 지정**해야 한다(`home`·`away`)"
    if box["arg"] and not str(getattr(sig, "arg", "") or ""):
        return f"🔴 `{metric}` 은 인자가 있어야 한다 — {box['arg']}"
    said = str(getattr(sig, "ref", "") or "")
    if not said:
        return "🔴 기준(`ref`)이 비었다"
    # 🔴🔴 **단위가 맞아야 한다** — `리그평균`(골 수)을 확률 지표에 쓰지 않는다
    if "리그평균" in said and metric not in LEAGUE_OK:
        return (f"🔴 **단위가 다르다** — `리그평균` 은 경기당 한 팀 **기대 득점**"
                f"이고 `{metric}` 은 **확률**이다. 확률에는 수나 `상대` 를 쓴다")
    # 🔴🔴 `상대` 는 **팀을 지정하는 지표**에만 쓴다 — ⚠️ 실사고 2026-10-10:
    #    `승무패[home] > 상대` 가 왔고, 그 지표는 팀 칸이 뜻이 없어 **자기 자신과
    #    비교**했다(`시뮬 0.461 > 기준 0.461` → 늘 반박). 그것은 판정이 아니다.
    if said == "상대" and not box["side"]:
        return (f"🔴 `상대` 는 **팀을 지정하는 지표**에만 쓴다 — `{metric}` 은 "
                "그렇지 않다(두 팀 몫이 한 분포 안에 있다). 수를 쓰거나 "
                "`승무패[home]` 과 `승무패[away]` 를 **각각** 신호로 달아라")
    return ""


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 ② 시뮬 산출에서 **읽기**
# ══════════════════════════════════════════════════════════════════

def value_of(sig, sim: dict) -> tuple[float | None, str]:
    """🔴 그 신호가 가리키는 **시뮬 값**. `(값, 사유)` — 못 읽으면 `(None, 사유)`.

    `sim` 은 **S3**(`probmodel.run`)이 돌려준 표다(새 계산 0건).
    """
    metric = str(getattr(sig, "metric", "") or "")
    side = str(getattr(sig, "side", "") or "")
    arg = str(getattr(sig, "arg", "") or "")
    box = dict(sim or {})
    if not box or box.get("home") is None:
        return None, "🔴 시뮬 산출이 없다"
    if metric == "기대득점":
        got = dict(box.get("xg") or {}).get(side)
        return (float(got), "") if got is not None else (None, "🔴 기대득점 칸이 없다")
    if metric == "무득점확률":
        got = dict(box.get("no_goal") or {}).get(side)
        return (float(got), "") if got is not None else (None, "🔴 무득점 칸이 없다")
    if metric == "구간득점":
        rows = dict(dict(box.get("by_bucket") or {}).get(side) or {})
        if arg not in rows:
            return None, f"🔴 구간 `{arg}` 이 없다(있는 것 {sorted(rows)})"
        return float(rows[arg]), ""
    if metric == "선제골후승리":
        got = dict(box.get("first_then_win") or {}).get(side)
        if got is None:
            return None, "🔴 선제골 후 결과를 못 셌다(그 팀이 선제골 낼 경우가 없다)"
        return float(got), ""
    if metric == "승무패":
        if arg not in ("home", "draw", "away"):
            return None, f"🔴 결과 인자가 이상하다(`{arg}`)"
        return float(box.get(arg) or 0.0), ""
    if metric == "오버":
        rows = dict(box.get("over") or {})
        if arg not in rows:
            return None, f"🔴 오버 줄 `{arg}` 이 없다(있는 것 {sorted(rows)})"
        return float(rows[arg]), ""
    if metric == "스코어":
        want = _score(arg)
        if want is None:
            return None, f"🔴 스코어 인자가 이상하다(`{arg}`)"
        rows = dict(box.get("scores") or {})
        got = rows.get(want)
        if got is None:
            return None, (f"🔴 스코어 `{arg}` 가 분포 상위에 없다"
                          "(무게가 아주 작다)")
        return float(got), ""
    return None, f"🔴 모르는 지표(`{metric}`)"


def _score(said: str) -> tuple[int, int] | None:
    try:
        h, a = str(said or "").split("-")
        return int(h), int(a)
    except (ValueError, TypeError):
        return None


def ref_of(sig, sim: dict, *, league: dict | None = None,
           ) -> tuple[float | None, str]:
    """🔴 기준 값 — 수·`상대`·`리그평균`(`*0.7` 가능). `(값, 사유)`.

    `league` 는 리그 평균 재료다 — `{"per_team": 경기당 한 팀 기대 득점}`.
    ⚠️ 그 재료가 없으면 **`판단 불가`** 다(지어내지 않는다 · #4).
    """
    said = str(getattr(sig, "ref", "") or "").strip()
    mul = 1.0
    if "*" in said:
        head, _sep, tail = said.partition("*")
        said = head.strip()
        try:
            mul = float(tail)
        except ValueError:
            return None, f"🔴 곱이 이상하다(`{tail}`)"
    if said == "상대":
        other = {"home": "away", "away": "home"}.get(
            str(getattr(sig, "side", "") or ""))
        if not other:
            return None, "🔴 `상대` 기준은 **팀을 지정한 지표**에만 쓴다"
        got, why = value_of(_flip(sig, other), sim)
        return (got * mul if got is not None else None), why
    if said == "리그평균":
        box = dict(league or {})
        per = box.get("per_team")
        if per is None:
            return None, ("🔴 리그 평균을 **모른다** — 이 경기 총골 기준이 없다"
                          "(지어내지 않는다)")
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **측별 기준**(사용자 지시 2026-10-11) — 홈은 홈 이점을 머금는다
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 종전엔 양 쪽이 **같은 수**(한 팀 몫)를 봤다. 홈 λ 는 홈 이점을
        #     머금으므로 *거의 언제나* 그 수를 넘어 **홈 폼 가설이 구조적으로
        #     반박**됐다(실측 2026-10-11 LAFC: 반박 6건 중 넷).
        #  🔴 `기대득점`(그 팀의 한 경기 기대 득점)에만 쓴다 — `구간득점` 은 한
        #     경기 몫이 아니라 **구간 몫**이므로 그 기준을 그대로 두면 거짓이 된다.
        side = str(getattr(sig, "side", "") or "")
        metric = str(getattr(sig, "metric", "") or "")
        if metric == "기대득점" and side in ("home", "away"):
            one = box.get("per_home" if side == "home" else "per_away")
            if one is not None:
                return float(one) * mul, (
                    f"측별 리그 기준({side} {float(one):.3f}) — "
                    + str(box.get("sides_why") or ""))
            return float(per) * mul, (
                "⚠️ 측별 기준을 못 만들어 **한 팀 몫**을 썼다 — "
                + str(box.get("sides_why") or ""))
        return float(per) * mul, ""
    try:
        return float(said) * mul, ""
    except ValueError:
        return None, f"🔴 기준을 못 읽었다(`{said}`)"


def _flip(sig, side: str):
    """🔴 `상대` 기준을 읽기 위해 **팀만 바꾼** 신호."""
    return sig.model_copy(update={"side": side}) if hasattr(
        sig, "model_copy") else sig


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 ③ **대조** — §4-1
# ══════════════════════════════════════════════════════════════════

def check(sig, sim: dict, *, league: dict | None = None) -> dict:
    """🔴🔴 §4-1 — 신호 하나를 시뮬과 대조한다. 돌려주는 표:

    ```
    {"verdict": "지지"|"반박"|"판단 불가", "value": 시뮬 값|None,
     "want": 기준 값|None, "why": "사유"}
    ```

    🔴 **판단 불가**는 *"지표가 없거나 기준을 모를 때"* 다 — 반박이 아니다(§4-1).
    """
    bad = bad_signal(sig)
    if bad:
        return {"verdict": NA, "value": None, "want": None, "why": bad}
    got, why1 = value_of(sig, sim)
    want, why2 = ref_of(sig, sim, league=league)
    if got is None or want is None:
        return {"verdict": NA, "value": got, "want": want,
                "why": (why1 or why2 or "🔴 못 읽었다")}
    d = str(sig.direction)
    hit = ((got > want) if d == ">" else (got < want) if d == "<"
           else (got >= want) if d == ">=" else (got <= want))
    return {"verdict": (OK if hit else NO), "value": round(got, 4),
            "want": round(want, 4),
            "why": (f"{_say(sig)} — 시뮬 {got:.3f} {d} 기준 {want:.3f} "
                    f"→ **{OK if hit else NO}**")}


def _say(sig) -> str:
    """🔴 신호를 사람 말로 한 토막."""
    side = str(getattr(sig, "side", "") or "")
    arg = str(getattr(sig, "arg", "") or "")
    return (f"{side + ' ' if side else ''}{sig.metric}"
            + (f"[{arg}]" if arg else "")
            + f" {sig.direction} {sig.ref}")


def league_of(facts, *, ref=None) -> dict:
    """🔴 리그 평균 재료 — **이 경기 총골 기준의 절반**(한 팀 몫).

    🔴 1순위는 `facts.standings["match_total_baseline"]`(그 경기 리그의 표)다.
    🔴🔴 **없으면 S3 가 쓰는 그 수를 쓴다** — ⚠️ 실사고 2026-10-10(제노아):
       순위표가 없어 이 표가 비었고, 가설 넷이 *"🔴 리그 평균을 **모른다** — 이
       경기 총골 기준이 없다"* 로 `판단 불가` 가 됐다. **그런데 같은 카드가**
       `[S3] 대회 유형 league:SA 실측 평균 2.5185(표본 810)` 을 적고 블록 4 도
       `기준 팀당 1.2592골(대회 league:SA)` 을 적었다 — 한 카드가 **같은 수를
       알면서 모른다고** 했다.
    🔴 그 수를 여기서 다시 세지 않는다 — `probmodel.league_mean` 을 부른다(사본 금지).
    ⚠️ 둘 다 없으면 **빈 표**이고 `리그평균` 기준은 `판단 불가` 다(지어내지 않는다).
    """
    got = dict(getattr(facts, "standings", None) or {}).get(
        "match_total_baseline")
    # 🔴🔴 **L2**(지시 2026-10-12 2번) — 순위표 총골은 **지금 누계**다. 재현에서
    #    그것을 쓰면 λ 기준이 미래를 본다 → 안 쓰고 아래 리그 평균으로 간다.
    from app import cassette as _cas
    from app.core import asof as _asof
    ok_now, why_now = _asof.may_use("standings.match_total_baseline",
                                    replay=_cas.mode() == _cas.REPLAY)
    if got is not None and not ok_now:
        got = None
    if got is not None:
        return _sides_of({"per_team": float(got) / 2.0, "total": float(got),
                          "why": "순위표의 그 리그 총골 기준"},
                         facts, ref=ref)
    from app.core import probmodel as _pm
    per, why = _pm.league_mean(facts, ref=ref)
    if per is None:
        return {}
    return _sides_of({"per_team": float(per), "total": float(per) * 2.0,
                      "why": f"S3 와 같은 수 — {why}"}, facts, ref=ref)


def _sides_of(box: dict, facts, *, ref=None) -> dict:
    """🔴🔴 **측별 리그 기준** — 홈은 홈 이점을 머금는다(사용자 지시 2026-10-11).

    ⚠️ 실사고 2026-10-11(LAFC): `리그평균` 기준이 양 쪽에 **같은 수**(한 팀 몫
       1.476)였다. 홈 λ 는 홈 이점(×1.139)을 머금으므로 *거의 언제나* 그 수를
       넘는다 — 그래서 **홈 폼 가설은 구조적으로 반박**됐다(실측: 반박 6건 중
       넷이 `기대득점 vs 리그평균` 이었다).
    🔴 측별 기준: 홈 = 한 팀 몫 × 홈 배율 · 원정 = 총골 − 홈 기준.
       그 배율은 **S3 가 쓰는 그 함수**다(`probmodel.home_mul` · 사본 금지).
    ⚠️ 배율을 못 받으면 측별 칸을 **안 만든다**(지어내지 않는다 · #4) — 그러면
       `ref_of` 가 한 팀 몫으로 돌아가고 그 사실을 사유에 적는다.
    """
    from app.core import probmodel as _pm
    mul, why = _pm.home_mul(facts, None, ref=ref)
    if mul is None:
        return {**box, "sides_why": f"🔴 홈 배율을 못 받았다 — {why}"}
    home = float(box["per_team"]) * float(mul)
    return {**box, "home_mul": float(mul), "per_home": round(home, 4),
            "per_away": round(float(box["total"]) - home, 4),
            "sides_why": f"홈 배율 ×{float(mul):.3f} — {why}"}
