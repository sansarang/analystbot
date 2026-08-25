"""§9 실슬레이트 검증 (a)~(f) — 프리페치 직후 캐시된 analysis를 읽어 보고한다.

읽기 전용. 라이브 API를 호출하지 않는다(프리페치가 채운 캐시만 본다).
"""
import asyncio, json, sys
import redis.asyncio as aioredis
from app.config import get_settings
from app.pipeline import default_date

SEP = "=" * 62


def _pct(x):
    return "—" if x is None else f"{x:.1%}"


async def load(redis, sport):
    raw = await redis.get(f"analysis:{sport}:{default_date(sport)}")
    return json.loads(raw) if raw else None


def sec_a(games, sport, settings):
    """(a) 전 경기 λ와 승률 — 상한 초과 0건인지."""
    from app.engine.scoring import prob_bounds
    lo, hi = prob_bounds(sport, settings)
    print(f"{SEP}\n(a) λ·승률 — 상한 [{lo:.2f}, {hi:.2f}]\n{SEP}")
    capped, no_dist = [], []
    for g in games:
        d = g.get("distribution")
        pf = g.get("p_final") or {}
        home, away = g["home"], g["away"]
        if not d:
            no_dist.append(f"{away}@{home}: {', '.join(g.get('lambda_missing') or ['사유 미기록'])}")
            continue
        lam = g.get("lam") or {}
        lh, la = lam.get("home"), lam.get("away")
        if lh is None or la is None:
            print(f"  {away}@{home}: λ 미기록(구 캐시) · 승률 {_pct(pf.get(away))}/{_pct(pf.get(home))}")
            continue
        note = g.get("prob_cap_note")
        flag = "  ⚠️ 절사" if note else ""
        print(f"  {away}@{home}: λ {la:.2f}/{lh:.2f} · 승률 {_pct(pf.get(away))}/{_pct(pf.get(home))}{flag}")
        if note:
            capped.append(f"{away}@{home}: {note} (원값 홈 {_pct(g.get('prob_raw_home'))})")
    print(f"\n  분포 산출: {len(games) - len(no_dist)}/{len(games)}경기")
    print(f"  상한 초과(절사): {len(capped)}건" + (" ✅ 0건" if not capped else ""))
    for c in capped:
        print(f"    - {c}")
    if no_dist:
        print(f"  분포 미산출 {len(no_dist)}건 (폴백 경로):")
        for n in no_dist:
            print(f"    - {n}")
    alert_n = settings.prob_cap_alert_n
    if len(capped) >= alert_n:
        print(f"  ❌ 절사 {len(capped)}건 ≥ {alert_n} — 확률 계산 로직 점검 필요")


def sec_b(games):
    """(b) 마켓 보드 '근거 부족' 탈락 수."""
    print(f"{SEP}\n(b) 마켓 보드 탈락 사유 분포\n{SEP}")
    total = approved = 0
    reasons: dict[str, int] = {}
    for g in games:
        for c in g.get("market_board") or []:
            total += 1
            if c.get("approved"):
                approved += 1
            else:
                r = (c.get("reject_reason") or "사유 미기록").split(" (")[0]
                reasons[r] = reasons.get(r, 0) + 1
    print(f"  전체 행 {total} · 승인 {approved} · 탈락 {total - approved}")
    for r, n in sorted(reasons.items(), key=lambda x: -x[1]):
        share = n / total if total else 0
        mark = "  ← 근거 부족 계열" if "근거 부족" in r else ""
        print(f"    {n:>3}건 ({share:>5.1%})  {r}{mark}")
    lack = sum(n for r, n in reasons.items() if "근거 부족" in r)
    if total:
        print(f"\n  '근거 부족' 합계 {lack}건 ({lack/total:.1%})")


def sec_c(games):
    """(c) 임의 1경기의 λ 산출 전 과정."""
    print(f"{SEP}\n(c) λ 산출 전 과정 (1경기)\n{SEP}")
    g = next((x for x in games if x.get("lambda_trace")), None)
    if not g:
        print("  ❌ lambda_trace를 가진 경기가 없다 — 전 경기가 폴백 경로다")
        return
    lam = g.get("lam") or {}
    print(f"  {g['away']} @ {g['home']}  (away={g['away']}, home={g['home']})")
    print(f"  λ 최종: away {lam.get('away')} / home {lam.get('home')}\n")
    for i, step in enumerate(g["lambda_trace"] or [], 1):
        print(f"    {i:>2}. {step}")
    miss = g.get("lambda_missing")
    if miss:
        print(f"\n  미수집 입력: {', '.join(miss)}")


def sec_d(games, sport):
    """(d) Statcast/xG 수집 지표와 실패 항목."""
    print(f"{SEP}\n(d) 1차 소스 수집 현황\n{SEP}")
    key = "statcast_filled" if sport == "mlb" else "xg_filled"
    filled_n = 0
    fields: dict[str, int] = {}
    missing: dict[str, int] = {}
    for g in games:
        f = g.get(key) or []
        if f:
            filled_n += 1
        for name in f:
            fields[name] = fields.get(name, 0) + 1
        for m in g.get("lambda_missing") or []:
            missing[m] = missing.get(m, 0) + 1
    print(f"  {key}: {filled_n}/{len(games)}경기에 주입")
    for name, n in sorted(fields.items(), key=lambda x: -x[1]):
        print(f"    ✅ {name:<28} {n}경기")
    if missing:
        print("\n  미수집 항목:")
        for m, n in sorted(missing.items(), key=lambda x: -x[1]):
            print(f"    ❌ {m:<28} {n}경기")
    else:
        print("\n  미수집 항목 없음")


def sec_e(games):
    """(e) 새 모델(분포) vs 기존(시장 반영 legacy) 승률 차이 상위 3경기."""
    print(f"{SEP}\n(e) 새 모델 vs 기존 모델 승률 차이 상위 3\n{SEP}")
    rows = []
    for g in games:
        pf, pl = g.get("p_final") or {}, g.get("p_legacy") or {}
        home = g["home"]
        if home in pf and home in pl:
            rows.append((abs(pf[home] - pl[home]), g, pf[home], pl[home]))
    if not rows:
        print("  비교 가능한 경기 없음")
        return
    for d, g, new, old in sorted(rows, key=lambda x: -x[0])[:3]:
        heur = (g.get("p_heuristic") or {}).get(g["home"])
        learned = (g.get("p_learned") or {}).get(g["home"])
        print(f"  {g['away']}@{g['home']} (홈 기준)")
        print(f"    신(경기력 0.5모델+0.5judge) {new:.1%} vs 구(시장 반영 legacy) {old:.1%}"
              f"  → 차이 {new - old:+.1%}p")
        print(f"    참고: 분포단독 {_pct(heur)} · 학습모델 {_pct(learned)}")


def sec_f(games):
    """(f) 라인 무브 일치/역행 사례."""
    print(f"{SEP}\n(f) 라인 무브먼트 신뢰도 조정\n{SEP}")
    def by(v):
        return [g for g in games if (g.get("line_move") or {}).get("verdict") == v]

    agree, diverge, neutral = by("agree"), by("diverge"), by("neutral")
    none_ = [g for g in games if not g.get("line_move")]
    print(f"  일치 {len(agree)} · 역행 {len(diverge)} · 무의미 {len(neutral)} · 미수집 {len(none_)}")
    for label, lst in (("일치(신뢰도 +1)", agree), ("역행(신뢰도 −1 + 경고)", diverge)):
        if lst:
            g = lst[0]
            lm = g["line_move"]
            print(f"\n  [{label}] {g['away']}@{g['home']} — {lm.get('desc')}")
            print(f"    {lm.get('line')}")
            print(f"    신뢰도 {lm.get('confidence_before')} → {lm.get('confidence_after')}"
                  + (f"  ⚠️ {lm['warning']}" if lm.get("warning") else ""))
            # 계약 확인: 라인 무브는 확률을 건드리지 않는다
            pf, ph = g.get("p_final") or {}, g.get("p_heuristic") or {}
            print(f"    p_final(홈) {_pct(pf.get(g['home']))} — 라인 무브 반영 전후 동일해야 함")
        else:
            print(f"\n  [{label}] 사례 없음")
    if none_:
        print(f"\n  ⚠️ 라인 무브 미수집 {len(none_)}경기 — 개장 스냅샷 부재")


async def main():
    settings = get_settings()
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        for sport in ("mlb", "soccer"):
            a = await load(redis, sport)
            print(f"\n\n{'#' * 62}\n#  §9 검증 — {sport.upper()}  ({default_date(sport)})\n{'#' * 62}")
            if not a:
                print("  ❌ 캐시 없음 — 프리페치가 이 종목을 채우지 못했다")
                continue
            games = a.get("games") or []
            if not games:
                print("  경기 없음 (슬레이트 비었거나 전부 종료)")
                continue
            sec_a(games, sport, settings)
            sec_b(games)
            sec_c(games)
            sec_d(games, sport)
            sec_e(games)
            sec_f(games)
    finally:
        await redis.aclose()

asyncio.run(main())
