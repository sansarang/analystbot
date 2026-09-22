"""[LE-2] 기준선 3개 — **엔진은 이것을 이겨야 후보를 낸다.**

지시문 LE-2-4:
> "기준선 3개를 항상 같이 잰다: (i) 시장 디빅값 그대로 (ii) 50% 고정
>  (iii) 팀 Elo 만. **엔진이 (i) 을 Brier·CLV 에서 못 이기면 후보를 내지 않는다.**"

🔴 **(iii) Elo 를 여기서 다시 짜지 않는다.** `app/models/soccer_elo.py` 가 이미
   같은 CSV 로 Elo 를 피팅하고 walk-forward 백테스트까지 한다. 값이 없으면
   **"미가용"** 으로 적는다 — 0 이나 0.5 로 채우면 (ii) 와 구별되지 않아
   기준선이 하나 준다.

⚠️ 기준선은 **같은 표본**에서 재야 비교가 된다. 한 기준선이 못 내는 행은
   비교에서 통째로 뺀다(`common_rows`).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

MARKET, FIFTY, ELO = "market", "fifty", "elo"
NAMES = (MARKET, FIFTY, ELO)


def market_p(row) -> float | None:
    """(i) 시장 디빅값 그대로. 🔴 **가장 이기기 어려운 기준선**이다 —
    실측 2026-09-22: `p_market` AUC 0.6167 [0.547, 0.686]."""
    try:
        f = float((row or {}).get("p_market"))
    except (TypeError, ValueError):
        return None
    return f if 0.0 <= f <= 1.0 else None


def fifty_p(row) -> float:
    """(ii) 50% 고정. Brier 0.25 · 로그손실 0.6931 이 나온다.
    🔴 이것을 못 이기면 그 확률에는 **정보가 없다.**"""
    return 0.5


def elo_p(row) -> float | None:
    """(iii) 팀 Elo 만. 행이 미리 담아 온 값을 읽는다.

    🔴 Elo 계산을 여기서 하지 않는다 — 원본은 `app/models/soccer_elo` 다.
    ⚠️ 없으면 **None**. 0.5 로 채우지 않는다.
    """
    try:
        f = float((row or {}).get("p_elo"))
    except (TypeError, ValueError):
        return None
    return f if 0.0 <= f <= 1.0 else None


_FN = {MARKET: market_p, FIFTY: fifty_p, ELO: elo_p}


def available(rows) -> tuple:
    """이 표본에서 **낼 수 있는** 기준선 이름들."""
    out = [MARKET, FIFTY]
    if any(elo_p(r) is not None for r in (rows or [])):
        out.append(ELO)
    return tuple(out)


def common_rows(rows, names=NAMES) -> list:
    """주어진 기준선이 **모두** 값을 내는 채점된 행만."""
    fns = [_FN[n] for n in names if n in _FN]
    return [r for r in (rows or [])
            if all(f(r) is not None for f in fns)
            and (r or {}).get("result") in ("win", "loss")]


def score(rows, *, names=None) -> dict:
    """기준선별 지표. 🔴 세 기준선을 **같은 행**에서 잰다 — 다르면
    "누가 낫다"가 성립하지 않는다."""
    from app.learning import metrics as M

    names = tuple(names or available(rows))
    sample = common_rows(rows, names)
    out: dict = {"_names": names, "_sample": len(sample),
                 "_dropped": len(list(rows or [])) - len(sample)}
    for n in names:
        fn = _FN[n]
        out[n] = M.summarize([{**r, "p_model": fn(r)} for r in sample])
    return out


def beats_market(engine_summary: dict, base: dict) -> bool | None:
    """엔진이 기준선 (i) 을 **Brier 와 CLV 둘 다에서** 이기나.

    🔴 지시문: "엔진이 (i) 을 Brier·CLV 에서 못 이기면 **후보를 내지 않는다**."
    ⚠️ 한쪽이라도 못 재면 `None`(모른다). 모르면 후보를 내지 않는 쪽이 맞다.
    """
    mk = (base or {}).get(MARKET) or {}
    if (engine_summary or {}).get("insufficient") or mk.get("insufficient"):
        return None
    eb, mb = engine_summary.get("brier"), mk.get("brier")
    ec, mc = engine_summary.get("clv_mean"), mk.get("clv_mean")
    if eb is None or mb is None or ec is None or mc is None:
        return None
    return bool(eb < mb and ec > mc)
