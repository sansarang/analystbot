"""[U13 2026-09-15] 마감 채점 리포트 — 학습 루프의 눈.

🔴 **순수 함수다.** DB 도 HTTP 도 부르지 않는다. 행 목록(dict)을 받아 표를
   돌려준다 — 그래야 표본 0 에서도 골격이 나오고, 테스트가 DB 없이 돈다.
🔴 **표본이 없으면 "없다"고 쓴다.** 0 으로 채우지 않는다. 0건과 0%는 다르다.
⚠️ 스케줄러에 걸지 않는다. 사람이 부른다(지시받지 않았다).

표본 구간(`report.checkpoints` = 50·150·300)은 1차 결정에서 온 값이다 —
그 수가 쌓일 때마다 위생·방향·결정을 다시 본다.
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict

from app.engine import rules as _R

logger = logging.getLogger(__name__)

#: 표본이 이 수에 닿을 때마다 본다. 원본은 `config/rules.yaml`.
CHECKPOINTS = tuple(_R.get("report.checkpoints") or ())

#: 값이 없다는 뜻. 🔴 0 과 구분한다.
NONE = None

#: [PA-28] 변수별 채점의 표본 문턱. 원본은 `config/rules.yaml`.
#  🔴 이 수에 닿기 전에는 **판단하지 않는다** — 적은 표본으로 변수를 끄는 것이
#     켜 두는 것보다 위험하다(끈 변수는 다시 켜 볼 기회가 없다).
VAR_MIN_N = _R.get("report.var_min_n")

#: 제안 문구. 🔴 **제안일 뿐이다** — 표 크기(`prob.ADJ_SHRINK`)를 바꾸는 것은
#  사용자 결정이다(prob.py 결정 B: "판단은 사용자가 한다").
KEEP, DROP, THIN = "유지", "끄기 검토", "표본 부족"


def _f(v):
    """숫자로. 숫자가 아니면 None — 0 으로 읽지 않는다."""
    try:
        if v is None:
            return None
        x = float(v)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def _mean(xs):
    xs = [x for x in (_f(v) for v in xs) if x is not None]
    return (sum(xs) / len(xs)) if xs else NONE


def _brier(rows):
    """브라이어. `p` 와 `hit`(0/1) 둘 다 있는 행만 본다."""
    pairs = [(_f(r.get("p")), r.get("hit")) for r in rows]
    pairs = [(p, int(h)) for p, h in pairs if p is not None and h is not None]
    if not pairs:
        return NONE
    return sum((p - h) ** 2 for p, h in pairs) / len(pairs)


def _rate(rows, key):
    got = [r for r in rows if r.get(key) is not None]
    return (len(got) / len(rows)) if rows else NONE


def hygiene(rows: list | None) -> dict:
    """50/150/300 위생·방향·결정.

    위생 = 자료가 있었는가. 방향 = 맞췄는가. 결정 = 낼 만했는가.
    """
    rows = list(rows or [])
    n = len(rows)
    out = {"n": n, "checkpoints": list(CHECKPOINTS), "reached": NONE,
           "위생": {}, "방향": {}, "결정": {}}
    out["reached"] = max((c for c in CHECKPOINTS if n >= c), default=NONE)

    out["위생"] = {
        "가설_있음": _rate(rows, "hypothesis"),
        "확인_있음": _rate(rows, "confirmed"),
        "배당_있음": _rate(rows, "p_market"),
        "분석_실패": (sum(1 for r in rows if r.get("analyze_failed")) / n
                      if n else NONE),
    }
    hits = [r.get("hit") for r in rows if r.get("hit") is not None]
    out["방향"] = {
        "채점됨": len(hits),
        "적중률": (sum(int(h) for h in hits) / len(hits)) if hits else NONE,
        "브라이어": _brier(rows),
        "평균_CLV": _mean(r.get("clv") for r in rows),
        "평균_라인이동": _mean(r.get("clv_line_shift") for r in rows),
    }
    out["결정"] = {
        "추천": sum(1 for r in rows if r.get("watch_state") == "추천"),
        "취소": sum(1 for r in rows if r.get("watch_state") == "취소"),
        "보드": sum(1 for r in rows if r.get("board_only")),
        "게이트_LLM_불일치": sum(1 for r in rows
                                 if r.get("gate_vs_llm") == "diff"),
    }
    return out


def _group(rows, key):
    box = defaultdict(list)
    for r in rows:
        box[r.get(key)].append(r)
    return box


def by_axis(rows: list | None, key: str = "main_axis") -> dict:
    """축별(또는 flow_class·grade별) CLV·브라이어.

    🔴 `key` 하나로 세 표를 다 낸다 — 축마다 함수를 늘리지 않는다.
    """
    rows = list(rows or [])
    out = {"key": key, "n": len(rows), "groups": {}}
    for k, grp in sorted(_group(rows, key).items(), key=lambda kv: str(kv[0])):
        hits = [r.get("hit") for r in grp if r.get("hit") is not None]
        out["groups"][k] = {
            "n": len(grp),
            "적중률": (sum(int(h) for h in hits) / len(hits)) if hits else NONE,
            "브라이어": _brier(grp),
            "평균_CLV": _mean(r.get("clv") for r in grp),
        }
    return out


def source_score(rows: list | None) -> dict:
    """도메인별 결장 적중 — **어느 소스를 믿을지**를 여기서 정한다.

    행 모양: `{"source": "transfermarkt.com", "claimed": [...],
               "actual": [...]}`. 실제 결장 명단과 대조한다.
    🔴 `actual` 이 없으면 **세지 않는다**(라인업을 못 받은 경기다).
       없는 것을 0점으로 세면 소스가 틀린 것처럼 보인다.
    """
    rows = list(rows or [])
    box = defaultdict(lambda: {"claimed": 0, "hit": 0, "games": 0})
    for r in rows:
        actual = r.get("actual")
        if actual is None:
            continue
        dom = str(r.get("source") or "").strip() or "미상"
        act = {str(x).lower() for x in actual}
        b = box[dom]
        b["games"] += 1
        for name in (r.get("claimed") or []):
            b["claimed"] += 1
            if str(name).lower() in act:
                b["hit"] += 1
    out = {"n": len(rows), "domains": {}}
    for dom, b in sorted(box.items()):
        out["domains"][dom] = {
            **b,
            "정확도": (b["hit"] / b["claimed"]) if b["claimed"] else NONE,
        }
    return out


def cancel_clv(rows: list | None) -> dict:
    """취소한 픽의 **가상 CLV**. 취소가 옳았는지를 잰다.

    🔴 가상 CLV 평균이 **양수면 취소가 손해**였다는 뜻이다 — 취소 규칙
       (조건 B contra)을 다시 봐야 한다. 이 숫자 없이는 영영 모른다.
    """
    rows = [r for r in (rows or []) if r.get("watch_state") == "취소"]
    vals = [_f(r.get("cancel_virtual_clv")) for r in rows]
    vals = [v for v in vals if v is not None]
    return {
        "취소건": len(rows),
        "가상CLV_있음": len(vals),
        "평균_가상CLV": (sum(vals) / len(vals)) if vals else NONE,
        "양수_건": sum(1 for v in vals if v > 0),
        "판정": ("취소가 손해였다" if vals and (sum(vals) / len(vals)) > 0
                 else ("취소가 이득이었다" if vals else "표본 없음")),
    }


# ═══════════════ [PA-28 2026-09-17 · 지시문 10단계] 변수별 채점
#
# 🔴 `by_axis` 는 **결정축(상위 2개)** 으로만 묶는다. 그래서 `이동연전` 처럼
#    늘 3등인 변수는 **영영 채점되지 않는다.** 변수 하나하나를 봐야 표 크기를
#    변수 단위로 조정할 수 있다(prob.py 결정 B).
#
# 🔴 **채점 기준은 CLV 다. 적중률이 아니다.** prob.py 결정 B 가 이미 그렇게
#    적었고(1차 결정 6), 이 저장소의 실측이 같은 말을 한다 — 판정 확률
#    AUC 0.5122(판별력 없음) 대 시장 확률 AUC 0.6421. 업계 자료도 같다:
#    "CLV 는 단기 승률보다 장기 수익성을 더 잘 예측한다"(ThePowerRank ·
#    SharpFootball) · "여러 베팅에 **걸쳐 합산되므로** 개별 사건에 덜
#    흔들린다"(Bet2Invest) — 그래서 **평균 CLV** 로 판정하고 건별 부호
#    일치율은 참고로만 둔다. 자세히는 docs/FORKS.md F-4.
#
# 🔴 **부호는 픽 기준으로 돌린다.** `adj_pp` 는 홈 확률 기준이고 CLV 는 우리가
#    고른 쪽 기준이다(`clv_pp`: 마감 확률 − 판정시각 확률). 원정을 골랐으면
#    홈에 −2%p 를 준 것이 **우리 픽에는 +2%p** 다. 안 돌리면 원정 픽에서
#    부호가 통째로 뒤집힌다.
#
# ⚠️ **제안일 뿐이다.** `prob.ADJ_SHRINK`·`ADJ_RULES` 를 바꾸는 것은 사용자
#    결정이다(prob.py 결정 B: "판단은 사용자가 한다").


def _sign(x) -> int:
    x = _f(x)
    return 0 if x is None or x == 0 else (1 if x > 0 else -1)


def toward_pick(delta, predicted_side) -> float | None:
    """홈 기준 조정(%p) → **우리 픽 기준** 조정(%p).

    🔴 원정 픽이면 부호를 뒤집는다. 픽을 모르면 **None** — 0 으로 읽지 않는다
       (0 은 "조정이 없었다"는 뜻이고 여기는 "어느 쪽인지 모른다"이다).
    """
    d = _f(delta)
    side = str(predicted_side or "").strip().lower()
    if d is None or side not in ("home", "away"):
        return None
    return d if side == "home" else -d


def by_variable(rows: list | None, *, min_n: int | None = None) -> dict:
    """변수 하나하나의 채점표. 지시문 10단계.

    행 모양: `{"adj_pp": {변수: %p}, "predicted_side": "home"|"away",
               "clv": %p, "hit": 0|1, "adj_evidence": {변수: {"source": …}}}`

    🔴 **변수가 발생한 행만** 센다. 안 나온 경기를 0 으로 세면 모든 변수가
       "거의 0"으로 수렴한다.
    🔴 표본이 `min_n` 에 못 미치면 **판단하지 않는다**(`표본 부족`). 적은
       표본으로 변수를 끄는 쪽이 켜 두는 쪽보다 위험하다 — 끈 변수는 다시
       켜 볼 기회가 없다.
    """
    rows = list(rows or [])
    need = VAR_MIN_N if min_n is None else min_n
    box: dict = defaultdict(lambda: {"deltas": [], "clvs": [], "hits": [],
                                     "agree": [], "sources": defaultdict(int)})
    for r in rows:
        adj = r.get("adj_pp") or {}
        if not isinstance(adj, dict):
            continue
        ev = r.get("adj_evidence") or {}
        clv = _f(r.get("clv"))
        for name, raw in adj.items():
            toward = toward_pick(raw, r.get("predicted_side"))
            b = box[str(name)]
            b["deltas"].append(toward)
            if r.get("hit") is not None:
                b["hits"].append(int(r["hit"]))
            if clv is not None and toward is not None:
                b["clvs"].append(clv)
                # 조정이 픽 쪽으로 밀었는데 시장도 픽 쪽으로 왔는가.
                b["agree"].append(1 if _sign(toward) == _sign(clv) else 0)
            src = (ev.get(name) or {}).get("source")
            if src:
                b["sources"][str(src)] += 1

    out = {"n": len(rows), "min_n": need, "variables": {}}
    for name, b in sorted(box.items()):
        n = len(b["deltas"])
        mean_clv = _mean(b["clvs"])
        mean_toward = _mean(b["deltas"])
        enough = bool(need) and n >= need
        if not enough or mean_clv is None or mean_toward is None:
            verdict = THIN
        elif _sign(mean_clv) == _sign(mean_toward) and _sign(mean_clv) != 0:
            verdict = KEEP
        else:
            verdict = DROP
        out["variables"][name] = {
            "n": n,
            "평균_기여_픽기준": mean_toward,
            "CLV_건수": len(b["clvs"]),
            "평균_CLV": mean_clv,
            "부호_일치율": (sum(b["agree"]) / len(b["agree"])
                            if b["agree"] else NONE),
            "적중률": (sum(b["hits"]) / len(b["hits"]) if b["hits"] else NONE),
            "출처": dict(b["sources"]) or NONE,
            "표본_충분": enough,
            "제안": verdict,
        }
    return out
