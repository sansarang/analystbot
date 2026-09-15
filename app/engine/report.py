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
