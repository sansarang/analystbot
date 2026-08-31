"""[v1.1 0단계] 캘리브레이션 집계 — 예측 확률이 실제 적중률과 맞는가.

이 모듈은 **아무것도 바꾸지 않는다.** 표를 만들 뿐이다. 임계값(58/63)·확신도
거부권·원정 프리미엄의 재검토는 표본이 쌓인 뒤 **별도 사용자 지시로만** 한다.

⚠️ 표본 30 미만 구간은 숫자를 쓰지 않고 "표본 부족"이라고 쓴다.
   얇은 표본의 적중률로 문턱을 흔드는 것이 이 프로젝트에서 가장 비싼 실수다
   (λ 모델 실측 52.3%를 "좋아 보인다"고 넘겼던 전례).
"""
from __future__ import annotations

MIN_SAMPLE = 30          # 이 미만이면 수치를 제시하지 않는다

# 확률 구간 — 게이트 임계(0.58 홈 / 0.63 원정)가 경계에 오도록 잘랐다.
# 임계 바로 아래·위가 실제로 갈리는지를 보는 것이 이 표의 목적이다.
BUCKETS = (
    (0.00, 0.50, "~0.50"),
    (0.50, 0.55, "0.50–0.55"),
    (0.55, 0.58, "0.55–0.58"),
    (0.58, 0.62, "0.58–0.62"),
    (0.62, 0.65, "0.62–0.65"),
    (0.65, 1.01, "0.65+"),
)


def _p_of_pick(row) -> float | None:
    """그 픽이 주장한 확률 = **예측한 쪽**의 확률.

    p_home은 홈 기준이라 원정 픽에 그대로 쓰면 0.4가 '예측 확률'로 잡혀
    구간 표가 통째로 어긋난다.
    """
    from app.engine.pick_ledger import predicted_side

    p = row["p_home"]
    if p is None:
        return None
    side = predicted_side(row["favored"], p)
    if side is None:
        return None
    return float(p) if side == "home" else 1.0 - float(p)


def _agg(rows) -> dict:
    """채점된 행 묶음 → {n, 예측평균, 실적중률}. 무효(void)·무승부는 뺀다."""
    usable = [r for r in rows if r["hit"] is not None and not r["void"]]
    if not usable:
        return {"n": 0, "pred": None, "actual": None}
    ps = [_p_of_pick(r) for r in usable]
    ps = [p for p in ps if p is not None]
    hits = sum(1 for r in usable if r["hit"])
    return {
        "n": len(usable),
        "pred": (sum(ps) / len(ps)) if ps else None,
        "actual": hits / len(usable),
    }


async def summarize(pool, days: int = 7, sport: str | None = None) -> dict:
    """기간 내 채점 완료 픽을 다섯 축으로 집계한다.

    반환 구조는 render_report가 그대로 읽는다. 표본이 없으면 빈 표를 낸다 —
    "데이터가 없다"와 "성적이 나쁘다"는 다른 말이고, 섞이면 안 된다.
    """
    where = ["l.graded_at IS NOT NULL",
             "l.judged_at >= now() - ($1::int * interval '1 day')"]
    args: list = [days]
    if sport:
        args.append(sport)
        where.append(f"l.sport = ${len(args)}")
    rows = await pool.fetch(
        f"""SELECT l.p_home, l.favored, l.confidence, l.gate_result, l.sport,
                   l.hit, l.void, l.lineup_status
              FROM pick_ledger l
             WHERE {' AND '.join(where)} AND l.is_final""", *args)
    rows = list(rows)

    from app.engine.pick_ledger import predicted_side

    by_bucket = []
    for lo, hi, label in BUCKETS:
        sel = [r for r in rows
               if (_p_of_pick(r) is not None and lo <= _p_of_pick(r) < hi)]
        by_bucket.append({"label": label, **_agg(sel)})

    def group(key_fn, labels):
        out = []
        for lab in labels:
            out.append({"label": lab,
                        **_agg([r for r in rows if key_fn(r) == lab])})
        return out

    return {
        "days": days,
        "total": len(rows),
        "buckets": by_bucket,
        "sides": group(lambda r: predicted_side(r["favored"], r["p_home"]),
                       ["home", "away"]),
        "confidence": group(lambda r: r["confidence"], ["상", "중", "하"]),
        "gates": group(lambda r: r["gate_result"],
                       sorted({r["gate_result"] for r in rows if r["gate_result"]})),
        "leagues": group(lambda r: r["sport"],
                         sorted({r["sport"] for r in rows if r["sport"]})),
    }


def _line(item: dict) -> str:
    if item["n"] == 0:
        return f"  {item['label']:<12} 표본 없음"
    if item["n"] < MIN_SAMPLE:
        return f"  {item['label']:<12} 표본 부족 ({item['n']}건)"
    pred = f"{item['pred']:.1%}" if item["pred"] is not None else "-"
    return (f"  {item['label']:<12} n={item['n']:<4} "
            f"예측 {pred} → 실제 {item['actual']:.1%}")


def render_report(data: dict, days: int = 7) -> str:
    """사람이 읽는 요약. 텔레그램 1장 분량."""
    if not data or data.get("total", 0) == 0:
        return (f"📊 캘리브레이션 (최근 {days}일)\n\n"
                "채점된 픽이 없습니다. 레저가 비었거나 아직 채점 전입니다.\n"
                "— 표본이 없다는 뜻이지 성적이 나쁘다는 뜻이 아닙니다.")
    out = [f"📊 캘리브레이션 (최근 {days}일 · 채점 {data['total']}건)", ""]
    out.append("■ 예측 확률 구간별")
    out += [_line(b) for b in data["buckets"]]
    out.append("")
    out.append("■ 홈/원정")
    out += [_line(x) for x in data["sides"]]
    out.append("")
    out.append("■ 확신도")
    out += [_line(x) for x in data["confidence"]]
    out.append("")
    out.append("■ 게이트 결과")
    out += [_line(x) for x in data["gates"]]
    out.append("")
    out.append("■ 리그")
    out += [_line(x) for x in data["leagues"]]
    out.append("")
    out.append(f"※ 표본 {MIN_SAMPLE} 미만 구간은 수치를 내지 않습니다. "
               "이 표로 임계값을 바꾸지 마십시오 — 재검토는 별도 지시입니다.")
    return "\n".join(out)
