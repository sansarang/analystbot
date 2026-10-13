"""🔴🔴 **판정 시험** — 새 구조 vs 옛 구조(사용자 지시 2026-10-12 · 규칙 고정).

```
PYTHONPATH=. python tools/judge_models.py var/judge/replay_444.json
```

> 1. **시즌 교차 확인** — 새 구조의 계수가 평가 시즌 밖에서 적합됐나. 아니면
>    시즌 교차로 다시 한다.
> 2. **맥니마 검정** — 두 모형의 방향 예측이 **다른** 경기 수(b·c)와 p 값.
> 3. **선택 적중률** — 각 모형의 최고 확률 상위 30%·20%·10%: 경기 수·실제
>    적중률·95% 구간. **같은 경기 수**로 비교.
> 4. **판정** — 옛 구조가 3의 **세 구간 모두** 높고 2가 `p<0.05` → 옛 구조로 교체.
>    그 밖 → 새 구조 유지.

🔴 **규칙은 결과를 보기 전에 고정했다** — 이 파일이 그 증거다(결과 보고 뒤에
   고치지 않는다).
🔴 재생은 `tools/backfill_score.py --dump` 가 적어 둔 **그 한 번**을 읽는다 —
   두 모형이 **같은 표본·같은 Elo 굴림**을 쓴다.
⚠️ 시즌 교차는 **바닥 계수**(c1·c2·b_dr)에 건다. 상성 비중·β 는
   `config/matchup_model.yaml` 의 `fit.provisional: true` — **적합한 적이 없는
   임시값**이라 평가 시즌을 본 적이 없다(두 모형이 같은 값을 쓴다).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def binom_two_sided(b: int, c: int) -> float:
    """🔴 맥니마 **정확 검정**(이항) — `n = b + c` · `p = 0.5`.

    ⚠️ 카이제곱 근사는 `b + c` 가 작을 때 거짓 유의를 낸다 — 정확 검정을 쓴다.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def main(argv: list[str]) -> int:
    said = argv[1] if len(argv) > 1 else "var/judge/replay_444.json"
    rows = json.loads(Path(said).read_text(encoding="utf-8"))
    rows = [r for r in rows if r.get("ours") and r.get("dr") is not None]
    # 🔴🔴 시즌은 **fotmob 이 말한 그 시즌**이다(달력 연도로 가르지 않는다 —
    #    J1 의 `2026/2027` 과 `2026` 이 둘 다 2026 이 된다). ⚠️ 꼬리표가 없는
    #    옛 덤프는 달력 연도로 떨어진다 — 그 사실을 보고가 적는다.
    tagged = sum(1 for r in rows if r.get("season"))
    for r in rows:
        r["season"] = str(r.get("season") or "") or str(r.get("day") or "")[:4]
    from app.core import base as _base
    from app.core import matchup as _mu
    from app.core import metrics as _me
    from app.core import probfloor as _pf
    sys.path.insert(0, str(ROOT / "tools"))
    from fit_base_model import _fit_rows

    conf = dict(_mu.table().get("weights") or {})
    beta = float(dict(_mu.table().get("lambda_model") or {}).get("beta") or 0.25)
    fit_meta = dict(_mu.table().get("fit") or {})

    # ══════════════════════════════════════════════════════════════════
    # 1. 시즌 교차 확인
    # ══════════════════════════════════════════════════════════════════
    print("# 🔴🔴 판정 시험 — 새 구조 vs 옛 구조")
    print()
    print("## 1. 시즌 교차 확인")
    print()
    kinds = sorted({str(r.get("league")) for r in rows})
    for kind in kinds:
        m = dict(__import__("app.rules", fromlist=["x"]).base_model(kind) or {})
        said_n = m.get("n")
        print(f"- `{kind}` 바닥 계수 — 적합 표본 **{said_n}경기** · 적합일 "
              f"{m.get('fitted_at')} · 출처 {m.get('source')}")
    years = sorted({r["season"] for r in rows})
    print(f"- 평가 표본의 시즌 — {years}"
          + (f" · 🔴 꼬리표 있는 줄 {tagged}/{len(rows)}" if tagged
             else " · ⚠️ **꼬리표 없다** — 달력 연도로 갈랐다"))
    print("- 🔴 **운영 계수는 시즌을 안 가렸다** — 바닥 계수는 그 리그의 **전 시즌**"
          "(J1 960경기 · KL1 636경기)으로 적합했고, 평가 표본이 그 안에 있다 →"
          " **같은 시즌을 보고 적합한 계수다**(누설).")
    print("- 🔴 그래서 **시즌 교차로 다시 적합한다** — 평가 시즌 `S` 의 경기는"
          " **`S` 밖 시즌**으로 적합한 계수로만 바닥을 만든다.")
    print(f"- ⚠️ 상성 비중·β 는 `fit.provisional={fit_meta.get('provisional')}`"
          f"(n={fit_meta.get('n')}) — **적합한 적이 없는 임시값**이라 평가 시즌을"
          " 본 적이 없다. 두 모형이 **같은 값**을 쓴다.")
    print()

    # ── 🔴 시즌 교차 적합: (리그, 평가 시즌) → 그 밖 시즌으로 적합한 계수
    cross: dict[tuple[str, str], dict] = {}
    for kind in kinds:
        mine = [r for r in rows if str(r.get("league")) == kind]
        seasons = sorted({r["season"] for r in mine})
        for s in seasons:
            other = [r for r in mine if r["season"] != s]
            if len(other) < 100:
                print(f"- ⚠️ `{kind}` 평가 시즌 {s} — 바깥 표본 {len(other)}경기로는"
                      " **적합하지 않는다**(100 미만) → 그 시즌은 **뺀다**")
                continue
            got = _fit_rows([(float(r["dr"]), 2 - int(r["hit"])) for r in other])
            # 🔴🔴 **계약 E1** — 적합 기간과 평가 기간이 겹치면 **예외**다.
            #    ⚠️ 같은 데이터로 적합·평가한 수는 **보고 금지**(지시 §1).
            _me.check_split(fit={r["season"] for r in other}, eval={s})
            cross[(kind, s)] = got
            print(f"- 교차 적합 `{kind}` 평가 {s} ← 바깥 {len(other)}경기 · "
                  f"b_dr {got['b_dr']} · c1 {got['c1']} · c2 {got['c2']} · "
                  f"logloss {got['logloss']}(기준선 {got['logloss_base']})")
    print()

    # ── 두 모형의 수를 **같은 표본**에서 만든다
    pairs: list[dict] = []
    for r in rows:
        key = (str(r.get("league")), r["season"])
        co = cross.get(key)
        if not co:
            continue
        got = _base.triple_from(c1=co["c1"], c2=co["c2"], b_dr=co["b_dr"],
                                dr=float(r["dr"]))
        floor = [got.home, got.draw, got.away]
        # 🔴 옛 구조 잔차 식은 **채점기**에 있다(§3 가 `probfloor` 에서 걷었다)
        from backfill_score import legacy_blend as _blend
        fresh, _w = _blend(floor, gaps=dict(r.get("gaps") or {}),
                           weights=conf, beta=beta)
        pairs.append({"hit": int(r["hit"]), "new": fresh, "old": list(r["ours"]),
                      "floor": floor, "league": r.get("league"),
                      "season": r["season"]})
    n = len(pairs)
    print(f"🔴 판정 표본 **{n}경기**(시즌 교차 계수를 만들 수 있는 경기만)")
    print()

    def rate(key: str, sub: list[dict]) -> tuple[int, int]:
        got = sum(1 for p in sub if _me.direction_hit(p[key], p["hit"]))
        return got, len(sub)

    # ══════════════════════════════════════════════════════════════════
    # 첫 줄 지표 — 방향 적중률
    # ══════════════════════════════════════════════════════════════════
    print("## 방향 적중률(시즌 교차)")
    print()
    print("| 모형 | **로그 손실** | RPS | 방향 적중 | 적중률 | 브라이어 |")
    print("|---|---|---|---|---|---|")
    for nm, key in (("**새 구조**(Elo 바닥+축0·축1)", "new"),
                    ("옛 구조(네 축)", "old"),
                    ("Elo만(교차 적합 바닥)", "floor")):
        h, m_ = rate(key, pairs)
        ll = sum(_me.logloss(p[key], p["hit"]) for p in pairs) / max(1, m_)
        rp = sum(_me.rps(p[key], p["hit"]) for p in pairs) / max(1, m_)
        br = sum(_me.brier(p[key], p["hit"]) for p in pairs) / max(1, m_)
        print(f"| {nm} | **{ll:.4f}** | {rp:.4f} | {h}/{m_} | "
              f"**{h / max(1, m_):.1%}** | {br:.4f} |")
    print()
    # 🔴🔴 **짝지은 차이**(지시 §1) — 주지표는 로그 손실이다
    print("| 짝지은 차이(로그 손실) | 평균 | 95% 구간 | 판정 |")
    print("|---|---|---|---|")
    for nm, a, b in (("새 구조 − Elo만", "new", "floor"),
                     ("새 구조 − 옛 구조", "new", "old"),
                     ("옛 구조 − Elo만", "old", "floor")):
        got = _me.paired([_me.logloss(p[a], p["hit"]) for p in pairs],
                         [_me.logloss(p[b], p["hit"]) for p in pairs])
        print(f"| {nm} | {got['mean']:+.4f} | {got['lo']:+.4f}~{got['hi']:+.4f}"
              f" | **{_me.verdict_of(got)}** |")
    print()

    # ══════════════════════════════════════════════════════════════════
    # 2. 맥니마 검정
    # ══════════════════════════════════════════════════════════════════
    print("## 2. 맥니마 검정 — 두 모형의 방향이 **다른** 경기")
    print()
    def _ok(p: dict, key: str) -> bool:
        return _me.direction_hit(p[key], p["hit"])

    both = sum(1 for p in pairs if _ok(p, "new") and _ok(p, "old"))
    b = sum(1 for p in pairs if _ok(p, "new") and not _ok(p, "old"))
    c = sum(1 for p in pairs if not _ok(p, "new") and _ok(p, "old"))
    none = n - both - b - c
    p_val = binom_two_sided(b, c)
    print(f"- 둘 다 맞음 **{both}** · 둘 다 틀림 **{none}**")
    print(f"- 🔴 **b = {b}**(새 구조만 맞음) · **c = {c}**(옛 구조만 맞음) — "
          f"다른 경기 **{b + c}건**")
    print(f"- 🔴 정확 이항 양측 **p = {p_val:.4f}** "
          f"→ {'**유의하다**(p<0.05)' if p_val < 0.05 else '유의하지 않다(p≥0.05)'}")
    print()

    # ══════════════════════════════════════════════════════════════════
    # 3. 선택 적중률
    # ══════════════════════════════════════════════════════════════════
    print("## 3. 선택 적중률 — 최고 확률 상위 구간(**같은 경기 수**)")
    print()
    print("| 구간 | 경기 | 새 구조 | 95% | 옛 구조 | 95% |")
    print("|---|---|---|---|---|---|")
    bands: dict[float, tuple[float, float]] = {}
    said_bands = _me.bands(pairs, keys=("new", "old"))
    for frac, box in said_bands.items():
        a, b = box["new"], box["old"]
        bands[frac] = (a["rate"], b["rate"])
        print(f"| 상위 {frac:.0%} | {a['n']} | **{a['rate']:.1%}**"
              f"({a['hit']}/{a['n']}) | {a['lo']:.1%}~{a['hi']:.1%} | "
              f"**{b['rate']:.1%}**({b['hit']}/{b['n']}) | "
              f"{b['lo']:.1%}~{b['hi']:.1%} |")
    print()

    # ══════════════════════════════════════════════════════════════════
    # 4. 판정
    # ══════════════════════════════════════════════════════════════════
    old_higher_all = all(o > nw for nw, o in bands.values())
    swap = bool(old_higher_all and p_val < 0.05)
    print("## 4. 판정(규칙 고정 · 결과 보고 뒤 바꾸지 않는다)")
    print()
    print(f"- 옛 구조가 **세 구간 모두** 높나 — "
          f"{'**예**' if old_higher_all else '**아니다**'}"
          + " ("
          + " · ".join(f"상위 {int(f * 100)}% 새 {v[0]:.1%} vs 옛 {v[1]:.1%}"
                       for f, v in bands.items()) + ")")
    print(f"- 맥니마 `p<0.05` 인가 — {'**예**' if p_val < 0.05 else '**아니다**'}"
          f"(p={p_val:.4f})")
    print()
    print(f"# 🔴🔴 판정: **{'교체 — 옛 구조로 돌린다' if swap else '유지 — 새 구조'}**")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **§7 판정 규칙(고정)** — 비교 시험 지시서 2026-10-12 §7
# ══════════════════════════════════════════════════════════════════
#
#  > 기준 = **M3**(새 경로). 도전 = M1, M4, M5.
#  > 도전 모형 채택 조건(**셋 다**):
#  >   (a) 로그 손실 짝지은 차이 **점추정이 기준보다 낮고**, 구간 상한이
#  >       **+0.005 미만**
#  >   (b) **방향 적중률이 기준보다 높고** 맥니마 **p < 0.05**
#  >   (c) **상위 30/20/10% 선택 적중률 세 값의 평균**이 기준보다 높음
#  > 여럿 통과 → **로그 손실 최저**. 차이 구간이 서로 겹치면 **항 수가 적은 쪽**.
#  > 아무도 통과 못 함 → **M3 유지**.
#
#  🔴🔴 **이 규칙은 결과를 보기 전에 커밋했다**(계약 J1). 실행 뒤 고치지 않는다.
#  ⚠️ (a) 의 *"구간 상한 +0.005 미만"* 은 **느슨한 상한**이다 — 지시가 그렇게
#     적었다(완전히 0 밖일 것을 요구하지 않는다).

#: 🔴 (a) 가 허용하는 구간 상한(로그 손실 단위) — 지시서 §7 의 그 수
#
#  🔴🔴 **규칙 결함 기록**(사용자 2026-10-12 · 비교 시험 확인):
#     *"(a) 상한 +0.005 는 460경기 구간 폭(±0.02)으로는 **도달 불가** — 다음
#     시험부터 (a) = 점추정이 낮고 **구간 하한 < 0**."*
#  ⚠️ 그래서 `HI_CAP` 은 **이번 시험의 기록용**으로 남기고, 다음 시험은
#     `passes(..., rule="v2")` 로 부른다(아래). 🔴 지난 판정을 **소급해 고치지
#     않는다** — 그 기록은 `docs/fable/stages/2026-10-12_compare_paths.md` 다.
HI_CAP = 0.005

#: 🔴 (b) 의 유의 문턱 — 맥니마 p < 0.05
P_CAP = 0.05

#: 🔴 (c) 가 보는 구간 — 상위 30/20/10%
BANDS = (0.30, 0.20, 0.10)


def passes(*, diff: dict, dir_rate: float, base_dir: float, p_value: float,
           bands: dict, base_bands: dict,
           rule: str = "v1") -> tuple[bool, dict, str]:
    """🔴🔴 §7 — 도전 모형이 **(a)(b)(c) 셋 다** 통과하나. `(통과, 칸, 사유)`.

    `diff` 는 `metrics.paired(도전 로그손실, 기준 로그손실)` 다(음수면 도전이 낫다).
    `bands`·`base_bands` 는 `{비율: 적중률}`.
    """
    # 🔴 `rule="v1"` — 이번 시험의 규칙(구간 **상한** < +0.005)
    #    `rule="v2"` — 다음 시험부터(사용자 결정): 점추정이 낮고 **구간 하한 < 0**
    # 🔴🔴 `rule="lineup"` — **라인업 지시서 §6**(2026-10-13)이 다시 쓴 v2 다.
    #    > (a) 로그 손실 점추정 < B · 구간 하한 < 0
    #    > (b) 방향이 B 보다 **낮지 않음**(맥니마 **B 우세** p<0.05 탈락)
    #    > (c) 상위 30/20/10% 평균 **≥ B**
    #    ⚠️ 앞선 v2 의 (b)는 *"도전이 유의하게 낫다"* 였다 — **더 엄격**했다.
    #       그래서 이름을 가른다(옛 시험의 판정이 바뀌지 않도록).
    if str(rule) == "lineup":
        a = bool(float(diff.get("mean", 1.0)) < 0.0
                 and float(diff.get("lo", 1.0)) < 0.0)
        worse = bool(float(dir_rate) < float(base_dir)
                     and float(p_value) < P_CAP)
        b = not worse
        mine = [float(bands.get(x, float("nan"))) for x in BANDS]
        theirs = [float(base_bands.get(x, float("nan"))) for x in BANDS]
        c = bool(sum(mine) / len(mine) >= sum(theirs) / len(theirs))
        said = (f"(a) 점추정 {float(diff.get('mean', 0.0)):+.4f} · 하한 "
                f"{float(diff.get('lo', 0.0)):+.4f} < 0 → "
                f"{'✅' if a else '🔴'} · "
                f"(b) 방향 {float(dir_rate):.1%} vs {float(base_dir):.1%} · "
                f"B 우세 p {float(p_value):.4f} → {'✅' if b else '🔴'} · "
                f"(c) 구간 평균 {sum(mine) / len(mine):.1%} ≥ "
                f"{sum(theirs) / len(theirs):.1%} → {'✅' if c else '🔴'}")
        return (a and b and c), {"a": a, "b": b, "c": c}, said
    if str(rule) == "v2":
        a = bool(float(diff.get("mean", 1.0)) < 0.0
                 and float(diff.get("lo", 1.0)) < 0.0)
    else:
        a = bool(float(diff.get("mean", 1.0)) < 0.0
                 and float(diff.get("hi", 1.0)) < HI_CAP)
    b = bool(float(dir_rate) > float(base_dir) and float(p_value) < P_CAP)
    mine = [float(bands.get(x, float("nan"))) for x in BANDS]
    theirs = [float(base_bands.get(x, float("nan"))) for x in BANDS]
    c = bool(sum(mine) / len(mine) > sum(theirs) / len(theirs))
    said = (f"(a) 점추정 {float(diff.get('mean', 0.0)):+.4f} · 상한 "
            f"{float(diff.get('hi', 0.0)):+.4f} < {HI_CAP:+.3f} → "
            f"{'✅' if a else '🔴'} · "
            f"(b) 방향 {float(dir_rate):.1%} vs {float(base_dir):.1%} · p "
            f"{float(p_value):.4f} < {P_CAP} → {'✅' if b else '🔴'} · "
            f"(c) 구간 평균 {sum(mine) / len(mine):.1%} vs "
            f"{sum(theirs) / len(theirs):.1%} → {'✅' if c else '🔴'}")
    return (a and b and c), {"a": a, "b": b, "c": c}, said


def pick(rows: list[dict]) -> tuple[str, str]:
    """🔴 §7 — 통과한 도전들 중 **로그 손실 최저**. 구간이 겹치면 **항 수가 적은 쪽**.

    `rows` 한 줄: `{name, ll, lo, hi, n_terms}`.
    """
    said = [r for r in (rows or [])]
    if not said:
        return "", "통과한 도전 모형이 없다 → **M3 유지**"
    said.sort(key=lambda r: float(r["ll"]))
    best = said[0]
    close = [r for r in said[1:]
             if not (float(r["lo"]) > float(best["hi"])
                     or float(r["hi"]) < float(best["lo"]))]
    if close:
        pool = [best, *close]
        pool.sort(key=lambda r: (int(r.get("n_terms") or 0), float(r["ll"])))
        got = pool[0]
        return str(got["name"]), (
            f"로그 손실 최저 `{best['name']}` 와 구간이 겹치는 것 "
            f"{[r['name'] for r in close]} → **항 수가 적은 쪽** "
            f"`{got['name']}`({got.get('n_terms')}항)")
    return str(best["name"]), f"로그 손실 최저 `{best['name']}`({best['ll']:.4f})"

