"""🔴🔴 **v5-A §4 단계 4 — 반증(레드팀).** *"이 마켓을 죽이는 갈래가 빠졌나."*

부록 v5-A §4:

> 판정 직전에 **이 마켓을 죽이는 시나리오가 세트에 빠졌나**를 따로 묻는다.
> 페이블이 채팅에서 놓쳤던 질문이 이것이다 — 남아공 5-0(언더를 죽이는
> 대량득점형 부재) · 크로아티아 봇(언더 3.5 를 죽이는 난타전 부재) ·
> 콜롬비아(무패를 죽이는 파라과이 승 갈래를 h2h 로 눌러 무시).

══════════════════════════════════════════════════════════════════
🔴 **추가만 한다** — 그것이 이 단계의 전부다
══════════════════════════════════════════════════════════════════

v5-A §1: *"시나리오 삭제 — 반증 단계는 **추가만** 할 수 있다. 기존 시나리오를
지우거나 무게를 낮추지 못한다(**시나리오를 줄이면 거짓 1.0 이 다시 생긴다**)."*

🔴 **M44** — 시나리오가 늘면 **죽을 자리가 늘어난다.** 그래서 생존율은 같거나
   내려간다. ⚠️ **올라갔다면** 우리가 시나리오를 지웠거나 무게를 바꾼 것이다 —
   **버그로 보고 카드를 금지한다.**
🔴 **M46** — 모델이 *"못 만든다"*(`impossible`) 고 해도 **§6-2 필수형 조건**이
   걸리면 코드가 템플릿을 넣는다(`redteam_overruled`). 판정은 **코드 자리**다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.reasons import Reason

logger = logging.getLogger(__name__)

#: 🔴 **언제 도나**(v5-A §4). ⚠️ 등급 후보가 없으면 반증할 결론도 없다 —
#  **비용을 쓰지 않는다**. 🔴 그 수는 §6-8 의 `소액` 바닥과 같다.
MIN_SURVIVAL = 0.8


@dataclass
class Result:
    """🔴 단계 4 산출. ⚠️ **못 돌았어도 이 꼴로 온다**(예외가 아니다)."""

    added: list = field(default_factory=list)
    markets: list = field(default_factory=list)
    overruled: list = field(default_factory=list)
    drops: list = field(default_factory=list)
    reason: Reason = Reason.OK
    why: str = ""
    usd: float = 0.0


def due(survivals: list) -> tuple[bool, str]:
    """🔴 반증을 **돌 때인가.** `(돈다, 왜)`.

    ⚠️ *"생존 0.8 이상인 마켓이 **하나라도** 있을 때만"*(v5-A §4).
    """
    hot = [(str(m), float(s)) for m, s in (survivals or [])
           if float(s) >= MIN_SURVIVAL]
    if not hot:
        said = max((float(s) for _, s in (survivals or [])), default=0.0)
        return False, (f"🔴 생존 **{MIN_SURVIVAL} 이상인 마켓이 없다**"
                       f"(가장 높은 것 {said:.2f}) — 반증할 결론이 없으니 "
                       f"비용을 쓰지 않는다(v5-A §4)")
    return True, f"생존 {MIN_SURVIVAL}+ 마켓 {len(hot)}개: {[m for m, _ in hot]}"


def check_proposals(rows: list, inp) -> tuple[list, list]:
    """🔴 `proposal` 을 **§3 과 같은 검사**에 넣는다(v5-A §4 코드 처리).

    ⚠️ 검사를 여기서 다시 짓지 않는다 — `hypo.check_scenarios` 하나다(#1).
    🔴 통과한 것에 **`added_by:redteam`** 을 단다.
    """
    from app import hypo
    want: list = []
    for row in (rows or []):
        if not isinstance(row, dict):
            continue
        p = row.get("proposal")
        if str(row.get("status") or "") != "proposed" or not isinstance(p, dict):
            continue
        want.append(dict(p))
    kept, drops = hypo.check_scenarios(want, inp)
    for row in kept:
        # 🔴 **누가 넣었나**를 바꿔 적는다(§6-2 의 `added_by` 와 같은 칸)
        row["added_by"] = "redteam"
    return kept, drops


def merge(scenarios: list, added: list, *, drop: list | None = None) -> list:
    """🔴🔴 **추가만 한다**(v5-A §1). ⚠️ `drop` 은 **받고 버린다**.

    🔴 왜 `drop` 인자가 있나: 모델이 *"A 를 지워라"* 라고 **말할 수 있다.** 그
       말을 **받는 자리**를 두고 **아무 일도 하지 않는** 것이 그것을 거절하는
       가장 분명한 방법이다 — 사유로 남는다(#3 조용한 0 금지).
    """
    if drop:
        logger.info("[redteam] 🔴 삭제 요청 %s 를 **받지 않는다**(v5-A §1: "
                    "추가만 가능 · 시나리오를 줄이면 거짓 1.0 이 생긴다)", drop)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **꼴을 여기서 맞춘다** — 실측 2026-10-05 (pn16)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고: 모델이 준 **dict** 를 그대로 붙였고 바로 뒤 재대입이
    #     `d.strength` 에서 터졌다 — `'dict' object has no attribute
    #     'strength'`. 카드는 *"결과를 못 받았다"* 로 삼켰다.
    #  🔴 섞는 자리가 **하나**이므로 여기서 맞춘다 — 뒤에서 `getattr` 로
    #     더듬으면 그런 자리가 끝없이 늘어난다.
    from app.scenarios import Draft
    out = list(scenarios or [])
    for row in (added or []):
        if not isinstance(row, dict):
            out.append(row)
            continue
        # 🔴 꼴이 **둘**이다 — 프롬프트는 `outcomes`(`[[2,2]]`)를 쓰고, 검증층을
        #    지난 줄은 `scores`(`"2-2"`)로 올 수 있다. ⚠️ 하나만 받으면 다른
        #    쪽이 **조용히 사라진다**(실측 2026-10-05: `outcomes` 제안이 버려졌다).
        scores = [str(x) for x in (row.get("scores") or []) if str(x).strip()]
        for pair in (row.get("outcomes") or []):
            try:
                said = f"{int(pair[0])}-{int(pair[1])}"
            except (TypeError, ValueError, IndexError):
                continue
            if said not in scores:
                scores.append(said)
        if not scores:
            # 🔴 **대입할 수 없는 줄은 섞지 않는다** — 생존이 왜곡된다
            logger.info("[redteam] ⚠️ 스코어 없는 제안 %r 을 **안 섞는다**",
                        row.get("id"))
            continue
        out.append(Draft(
            id=str(row.get("id") or "RT"), scores=scores,
            strength=float(row.get("strength") or 1.0),
            template_id="redteam", added_by="redteam",
            why=str(row.get("why") or "v5-A §4 반증 제안")))
    return out


def check_survival(before: dict, after: dict) -> tuple[bool, str]:
    """🔴🔴 **M44** — 어떤 마켓의 생존율도 **올라가지 않는다**.

    ⚠️ 시나리오가 늘면 죽을 자리가 늘어난다 — 올라갔다면 우리가 **지웠거나
       무게를 바꾼** 것이다. 🔴 그때는 **카드 금지**다.
    """
    up = [(m, float(before.get(m, 0)), float(v))
          for m, v in (after or {}).items()
          if float(v) > float(before.get(m, 0)) + 1e-9]
    if up:
        return False, (
            f"🔴🔴 **M44 — 카드 금지.** 반증 뒤 생존율이 **올라갔다**: "
            + " · ".join(f"{m} {b:.2f} → {a:.2f}" for m, b, a in up)
            + ". ⚠️ 시나리오가 늘면 죽을 자리가 늘어난다 — 올라갔다면 우리가 "
              "시나리오를 지웠거나 무게를 바꾼 것이다(버그다)")
    return True, f"생존율이 같거나 내려갔다({len(after or {})}개 마켓)"


@dataclass(frozen=True)
class Overruled:
    """🔴 M46 — `impossible` 을 뒤집은 결과."""

    types: list
    reason: Reason
    why: str = ""


def overrule(rows: list, inp) -> Overruled:
    """🔴🔴 **M46** — *"필수형 조건이 걸리는데 `impossible` 이라 했으면 무시하고
    템플릿 시나리오를 넣는다"*.

    ⚠️ 모델이 *"못 만든다"* 고 해도 **§6-2 조건**이 걸리면 코드가 넣는다 —
       판정은 **코드 자리**다(v5-A §1).
    """
    said = [r for r in (rows or [])
            if isinstance(r, dict) and str(r.get("status") or "") == "impossible"]
    need = [str(t) for t in (inp.required_types or [])]
    if not said or not need:
        return Overruled([], Reason.OK,
                         f"`impossible` {len(said)}건 · 필수형 {need or '없다'}")
    logger.info("[redteam] 🔴 %s — `impossible` 을 뒤집는다: 필수형 %s",
                Reason.REDTEAM_OVERRULED.value, need)
    return Overruled(
        need, Reason.REDTEAM_OVERRULED,
        f"🔴 반증이 `impossible` 이라 했지만 **필수형 {need} 이 걸린다** — "
        f"코드가 템플릿 시나리오를 넣는다(v5-A M46)")


def card_line(market: str, status: str, *, before: float, after: float,
              by: list | None = None) -> str:
    """🔴 카드 하단 한 줄(v5-A §4 출력 예 그대로).

    ```
    언더 2.5   covered (E 2-2)            생존 0.80 유지
    잉글랜드 무패 proposed RT1(…)          생존 0.85 → 0.85 (C와 같은 갈래)
    ```
    """
    who = f"({' · '.join(str(x) for x in (by or []))})" if by else ""
    if abs(float(after) - float(before)) < 1e-9:
        tail = f"생존 {before:.2f} 유지"
    else:
        tail = f"생존 {before:.2f} → {after:.2f}"
    return f"  {market}  {status} {who}  {tail}".rstrip()


def run(inp, scenarios: list, *, survivals: list, spent_in: int = 0,
        now=None, _net=None) -> Result:
    """🔴🔴 **단계 4 전체.** ⚠️ 돌 때가 아니면 **비용을 쓰지 않는다**.

    순서(v5-A §4):
      ① 생존 0.8+ 가 있나 → 없으면 `redteam_skipped`
      ② 예산을 넘었나 → 넘으면 `redteam_skipped`(v5-A §2)
      ③ 물어서 `proposal` 을 받고 **§3 과 같은 검사**를 지난 것만 추가
      ④ `impossible` 인데 필수형이 걸리면 **뒤집는다**(M46)
    """
    from app import deepseek, rules
    ok, why = due(survivals)
    if not ok:
        return Result(reason=Reason.REDTEAM_SKIPPED, why=why)
    cap = int((rules.deepseek_cfg().get("budget", {}).get("per_match") or {})
              .get("input_tokens") or 30_000)
    if int(spent_in) > cap:
        return Result(reason=Reason.REDTEAM_SKIPPED,
                      why=(f"🔴 DeepSeek 경기당 입력 {int(spent_in):,} > "
                           f"{cap:,} — **단계 4 생략**(v5-A §2)"))
    from app import hypo
    payload = dict(hypo.to_payload(inp))
    payload["scenarios"] = list(scenarios or [])
    payload["hot_markets"] = [str(m) for m, s in (survivals or [])
                              if float(s) >= MIN_SURVIVAL]
    got = deepseek.ask([{"role": "system", "content": system_prompt()},
                        {"role": "user", "content": hypo._dump(payload)}],
                       match=(getattr(inp, "match_key", "")
                              or f"{inp.home}|{inp.away}"),
                       stage="stage4",
                       now=now, _net=_net)
    if not got.ok:
        return Result(reason=got.reason, why=got.why)
    box, bad = got.json()
    if box is None:
        return Result(reason=Reason.DONE_PARSE_FAIL, why=bad, usd=got.usd)
    rows = list(box.get("markets") or [])
    added, drops = check_proposals(rows, inp)
    over = overrule(rows, inp)
    return Result(added=added, markets=rows, overruled=list(over.types),
                  drops=drops, reason=Reason.OK, usd=got.usd,
                  why=(f"단계 4 — 제안 {len(added)}개 추가 · 폐기 {len(drops)}개"
                       + (f" · {over.why}" if over.types else "")))


def system_prompt() -> str:
    """🔴 v5-A §4 프롬프트 요지 — **일곱 줄 그대로**(고정 문자열)."""
    return (
        "1. 🔴 너의 일은 아래 마켓들이 **틀릴 수 있는 길**을 찾는 것이다. "
        "마켓을 **지지하지 마라.**\n"
        "2. 마켓마다: 이 마켓을 **죽이는 스코어 범위**를 적는다"
        "(예: 언더 2.5 → 합계 3골 이상).\n"
        "3. 그 범위에 들어가는 시나리오가 세트에 있는지 본다. 있으면 "
        "`covered`.\n"
        "4. 없으면, **입력 변수만으로** 그 범위를 만드는 시나리오가 가능한지 "
        "판단한다. 가능하면 `driver_vars`·`mechanism`·`outcomes` 로 새 "
        "시나리오를 제안한다. 근거 변수가 **하나라도 있으면 제안한다** — "
        "약해도 제안하고 `weak:true`.\n"
        "5. 입력 변수로 **정말 만들 수 없으면** `impossible` 과 이유 한 줄.\n"
        "6. 🔴 **기존 시나리오를 지우거나 약하다고 평가하지 마라. 추가만 한다.**\n"
        "7. 🔴 **새 사실을 만들지 마라.**\n"
        "\n"
        "출력은 JSON 하나다: "
        '{"markets":[{"market":"total_under_2.5","kill_range":"sum>=3",'
        '"status":"covered|proposed|impossible","covered_by":["E"],'
        '"proposal":{"id":"RT1","driver_vars":[],"mechanism":"",'
        '"outcomes":[[2,2]],"weak":true},"reason":""}]}\n'
    )
