"""🔴🔴 **대회 바닥 적합**(수정 지시 2026-10-14 · 1·2번) — ① 자체 / ② 검증된 대체.

```
PYTHONPATH=. uv run python tools/fit_comp_base.py --comp league:ACLE
PYTHONPATH=. uv run python tools/fit_comp_base.py --comp league:JLC --alt league:J1
```

> 바닥 순서: ① 그 대회 자체 적합 → ② **검증된** 대체 바닥 → ③ 둘 다 실패면 기계 보류.
> 어느 바닥을 썼는지 카드 1단 줄에 표시(① 자체 / ② 대체 · 검증 n · logloss).

## 🔴 "빌리지 않는다" 의 뜻이 바뀌었다
전에는 *"다른 대회 계수 금지"* 였다. 이제는 **검증 없는 빌리기 금지**다 —
그 대회 **과거 경기에 적용해 logloss 를 재서** 자체 기준선을 넘지 않으면 쓴다.

🔴 적합 함수는 `tools/fit_base_model._fit_rows` **하나**다(사본 금지).
🔴 입력은 **그 경기 앞** 등급이다(누설 금지 · 등급은 날짜 순으로 굴린다).
🔴 **중립 경기는 뺀다** — `venue: home_only` 규약이다(`config/base_model.yaml`
   머리말: 중립 줄은 결과순으로 적혀 있어 모형이 *"먼저 적힌 팀이 이긴다"* 를 배운다).
⚠️ 못 잰 것은 **이름으로** 남긴다(#3).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: 🔴 ② 대체 채택 문턱 — 그 대회 위 logloss 가 **대체의 자체 logloss + 이것** 이내
ALT_SLACK = 0.02
#: 🔴 ① 자체 적합 최소 표본(지시 1·2번의 그 수)
MIN_N = 200


def comp_rows(comp: str, *, as_of: str = "9999") -> tuple[list[dict], str]:
    """🔴 그 대륙의 **대회 경기**(`var/judge/offsets_*.json`) — 같은 꼴로 모은다.

    🔴 같은 대륙의 대륙 대회를 **함께** 본다(`tools/fit_offsets.fit` 과 같은 규칙) —
       ACL Elite + ACL2 를 한 판으로 보면 리그 쌍 표본이 커진다.
    """
    from app.core import competition as _cp
    from fit_offsets import box_of
    conf = str(_cp.row_of(comp).get("confederation") or "").upper()
    kind = _cp.kind_require(comp)[0]
    out: list[dict] = []
    said: list[str] = []
    for key, one in sorted(_cp.rows().items()):
        if kind == "club_continental":
            if (str(one.get("confederation") or "").upper() != conf
                    or _cp.kind_require(key)[0] != "club_continental"):
                continue
        elif key != comp:
            continue
        path = box_of(key)
        if not path.exists():
            continue
        got = [r for r in json.loads(path.read_text(encoding="utf-8"))
               if str(r.get("day") or "") < str(as_of)]
        out += got
        said.append(f"{key} {len(got)}경기")
    return out, (" · ".join(said) or "⬜ 모은 경기가 없다")


def pairs_of(comp: str, rows: list[dict]) -> tuple[list[tuple], dict]:
    """🔴🔴 `(등급 차, 결과)` 짝 — **국내 Elo + 리그 오프셋**으로 센다.

    돌려주는 `gone` 은 **왜 버렸나**를 수로 든다(조용히 버리지 않는다 · #3).
    """
    from app.core import competition as _cp
    from app.core import domesticelo as _de
    from app.core import offsets as off
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **누설을 고쳤다**(수정 지시 2026-10-14 1번) — **경기일 기준 Elo**
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전엔 `domestic_elo()` 가 덤프 전체를 굴린 **마지막 값**을 돌려줬다 —
    #     2024년 경기를 **2026년 등급**으로 채점한 셈이다(미래를 봤다).
    #  🔴 이제 경기마다 `ratings_at(그 경기 날짜)` 를 쓴다 — 그 날짜 **앞** 경기만
    #     굴린 값이다. 🔴 런타임(`s2b_base.continental_elo`)도 **같은 함수**다.
    #  🔴🔴 ⚠️ **수집 줄의 `day` 는 날짜가 아니라 시즌이다**(`"2026/2027"` ·
    #     실측 2026-10-14) — 그 글자로 끊으면 `"2026-05-12" < "2026/2027"` 가
    #     되어(`-` < `/`) 컷이 거의 안 듣는다. 🔴 그래서 **시즌 시작일**로 끊는다.
    #     ⚠️ 시즌 안 누설은 그래서 **아예 없다**(정보가 줄 뿐 새지 않는다).
    cache: dict = {}

    def _cut_of(said: str) -> str:
        """🔴 시즌 글자 → **그 시즌 시작일**(그 앞 경기만 Elo 에 쓴다)."""
        got = [x for x in str(said or "").replace("-", "/").split("/") if x]
        if not got or not got[0].isdigit():
            return ""
        y = int(got[0])
        # 🔴 `2026/2027`(가을–봄)은 7월 시작 · `2026`(한 해)은 1월 시작
        return f"{y}-07-01" if len(got) == 2 else f"{y}-01-01"

    def _elo_at(said: str) -> dict:
        cut = _cut_of(said)
        if cut not in cache:
            cache[cut] = _de.ratings_at(cut)[0]
        return cache[cut]
    # 🔴 `latest_plate` 는 **대륙**으로 찾는다(판이 대륙별 한 장이다) —
    #    대회 키를 넘기면 조용히 빈 판이 온다(실측 2026-10-14: 짝 0건이었다).
    conf = str(_cp.row_of(comp).get("confederation") or "").upper()
    plate, why_p = off.latest_plate(conf)
    box = dict((plate or {}).get("leagues") or {})
    out: list[tuple] = []
    gone: dict[str, int] = {}

    def _nm(one) -> str:
        return str(one.get("name") or "") if isinstance(one, dict) \
            else str(one or "")
    for r in rows:
        home, away = _nm(r.get("home")), _nm(r.get("away"))
        lh = str(r.get("home_league") or "")
        la = str(r.get("away_league") or "")
        # 🔴 **중립 경기는 뺀다**(venue: home_only 규약)
        if _cp.neutral_of(comp, stage=str(r.get("stage") or ""))[0]:
            gone["중립 경기(home_only 규약)"] = gone.get(
                "중립 경기(home_only 규약)", 0) + 1
            continue
        elo = _elo_at(str(r.get("season") or r.get("day") or ""))
        if home not in elo or away not in elo:
            gone["국내 Elo 없다(그 날짜 앞)"] = gone.get(
                "국내 Elo 없다(그 날짜 앞)", 0) + 1
            continue
        if not lh or not la:
            gone["국내 리그 모름"] = gone.get("국내 리그 모름", 0) + 1
            continue
        oh, oa = box.get(lh) or {}, box.get(la) or {}
        if oh.get("value") is None or oa.get("value") is None:
            gone["리그 오프셋 ⬜"] = gone.get("리그 오프셋 ⬜", 0) + 1
            continue
        try:
            hg, ag = int(r["hg"]), int(r["ag"])
        except (KeyError, TypeError, ValueError):
            gone["스코어 없다"] = gone.get("스코어 없다", 0) + 1
            continue
        dr = ((elo[home] + float(oh["value"]))
              - (elo[away] + float(oa["value"])))
        # 🔴 결과 꼴은 `fit_base_model` 과 같다 — 0 원정승 · 1 무 · 2 홈승
        out.append((dr, 2 if hg > ag else (1 if hg == ag else 0)))
    gone["_판"] = (f"{why_p} · 🔴 Elo 는 **시즌 시작 기준**"
                   f"(as-of 컷 {sorted(x for x in cache if x)} · "
                   f"`core/domesticelo.ratings_at`)")
    return out, gone


def refit_cuts(pairs: list[tuple], coef: dict) -> dict:
    """🔴🔴 지시 2번 — **홈 이점만 그 대회 실측으로 다시 맞춘다**.

    `b_dr`(체급 기울기)은 대체 바닥 것을 **그대로 두고** 절단점 `c1`·`c2` 만
    그 대회 경기로 다시 적합한다. 🔴 이 모형에서 **홈 이점은 절단점이 머금는다**
    (`config/base_model.yaml` 머리말 · 홈 개최 경기만 적합하므로) — 그래서
    절단점만 다시 맞추는 것이 *"홈 이점만 다시 맞춘다"* 와 같은 일이다.
    """
    import numpy as np
    from scipy.optimize import minimize

    from fit_base_model import _nll
    x = np.array([[dr / 100.0] for dr, _ in pairs], dtype=float)
    y = np.array([o for _, o in pairs], dtype=int)
    b = float(coef["b_dr"])

    def _nll2(cuts: np.ndarray) -> float:
        return _nll(np.array([cuts[0], cuts[1], b]), x, y)
    got = minimize(_nll2, np.array([float(coef["c1"]), float(coef["c2"])]),
                   method="Nelder-Mead",
                   options={"maxiter": 20000, "xatol": 1e-8, "fatol": 1e-10})
    c1, c2 = (float(v) for v in got.x)
    base = np.bincount(y, minlength=3) / len(y)
    dumb = float(-np.log(np.clip(base[y], 1e-12, 1.0)).mean())
    return {"c1": round(c1, 6), "c2": round(c2, 6), "b_dr": round(b, 6),
            "venue": "home_only", "n": int(len(y)),
            "logloss": round(float(got.fun), 6),
            "logloss_base": round(dumb, 6),
            "share_home_draw_away": [round(float(base[2]), 4),
                                     round(float(base[1]), 4),
                                     round(float(base[0]), 4)],
            "fitted_at": __import__("datetime").date.today().isoformat(),
            "converged": bool(got.success)}


def logloss_on(pairs: list[tuple], coef: dict) -> float:
    """🔴 그 계수를 **이 경기들에** 적용한 로그 손실(대체 바닥 검증 · 지시 2번)."""
    import math

    from app.core import base as _base
    if not pairs:
        return float("nan")
    tot = 0.0
    for dr, y in pairs:
        got = _base.triple_from(c1=float(coef["c1"]), c2=float(coef["c2"]),
                                b_dr=float(coef["b_dr"]), dr=float(dr))
        p = [got.away, got.draw, got.home][y]
        tot -= math.log(max(float(p), 1e-12))
    return tot / len(pairs)


def main(argv: list[str]) -> int:
    from app import rules
    from fit_base_model import _fit_rows
    ap = argparse.ArgumentParser()
    ap.add_argument("--comp", required=True)
    ap.add_argument("--alt", help="② 대체 바닥으로 쓸 대회 유형(예 `league:J1`)")
    ap.add_argument("--write", action="store_true",
                    help="채택한 계수를 `config/base_model.yaml` 에 적는다")
    args = ap.parse_args(argv[1:])
    rows, why = comp_rows(args.comp)
    print(f"# 🔴🔴 `{args.comp}` 바닥 적합")
    print()
    print(f"- 모은 경기 — {why}(합 **{len(rows)}**)")
    pairs, gone = pairs_of(args.comp, rows)
    print(f"- 쓸 수 있는 짝 **{len(pairs)}** · 오프셋 판 {gone.pop('_판', '')}")
    print("- 버린 것 — "
          + (" · ".join(f"{k} {v}건" for k, v in sorted(gone.items()))
             if gone else "없다"))
    print()
    out: dict = {}
    # ── ① 자체 적합
    print("## ① 자체 적합")
    print()
    if len(pairs) >= MIN_N:
        got = _fit_rows(pairs)
        ok = float(got["logloss"]) < float(got["logloss_base"])
        print(f"- 표본 **{got['n']}** · logloss **{got['logloss']}** ↔ 기준선 "
              f"{got['logloss_base']} · 수렴 {got['converged']} → "
              + ("✅ **채택**" if ok else "🔴 기준선보다 나쁘다 — 못 쓴다"))
        print(f"- 계수 c1={got['c1']} · c2={got['c2']} · b_dr={got['b_dr']} · "
              f"비율 {got['share_home_draw_away']}")
        if ok:
            got["바닥_출처"] = f"① 자체 적합(표본 {got['n']})"
            out = got
    else:
        print(f"- 🔴 표본 **{len(pairs)}** < {MIN_N} → **자체 적합 안 한다**")
    # ── ② 검증된 대체
    if not out and args.alt:
        print()
        print(f"## ② 대체 바닥 — `{args.alt}` 를 **이 대회 경기로 검증**")
        print()
        alt = rules.base_model(args.alt)
        if not alt:
            print(f"- 🔴 `{args.alt}` 계수가 없다 — 대체도 못 쓴다")
        elif not pairs:
            print("- 🔴 검증할 경기가 **0건**이다 — 검증 없는 빌리기는 금지다")
        else:
            said = logloss_on(pairs, alt)
            cut = float(alt["logloss"]) + ALT_SLACK
            ok = said <= cut
            print(f"- 검증 **{len(pairs)}경기** · 그 대회 위 logloss "
                  f"**{said:.6f}** ↔ 문턱 {cut:.6f}"
                  f"(= `{args.alt}` 자체 {alt['logloss']} + {ALT_SLACK}) → "
                  + ("✅ **채택**" if ok else "🔴 **넘었다**"))
            # 🔴 기준선(늘 같은 비율)도 함께 — 그보다 나쁘면 아예 못 쓴다
            dumb = _fit_rows(pairs)["logloss_base"] if len(pairs) >= 20 \
                else float("nan")
            print(f"- 그 경기들의 기준선(늘 같은 비율) logloss **{dumb}** → "
                  + ("대체가 기준선보다 낫다 ✅" if said < dumb
                     else "🔴 대체가 기준선보다 나쁘다 — 못 쓴다"))
            if ok and said < dumb:
                out = dict(alt)
                out.update({"n": len(pairs), "logloss": round(said, 6),
                            "logloss_base": round(dumb, 6),
                            "바닥_출처": (f"② 대체 `{args.alt}` · 검증 "
                                      f"{len(pairs)}경기 · logloss "
                                      f"{said:.4f}")})
            else:
                # ── 🔴 지시 2번 — **홈 이점만 그 대회 실측으로 다시 맞춰 재검증**
                print()
                print(f"### ②b 홈 이점만 다시 맞춘다(기울기 `b_dr` 는 "
                      f"`{args.alt}` 것 그대로)")
                print()
                got2 = refit_cuts(pairs, alt)
                ok2 = (float(got2["logloss"]) < float(got2["logloss_base"]))
                print(f"- 절단점 재적합 — c1 {alt['c1']} → **{got2['c1']}** · "
                      f"c2 {alt['c2']} → **{got2['c2']}** · b_dr "
                      f"{got2['b_dr']}(고정)")
                print(f"- logloss **{got2['logloss']}** ↔ 그 경기 기준선 "
                      f"{got2['logloss_base']} · 수렴 {got2['converged']} → "
                      + ("✅ **채택**" if ok2
                         else "🔴 기준선도 못 넘는다 — 못 쓴다"))
                if ok2:
                    got2["바닥_출처"] = (
                        f"② 대체 `{args.alt}` 기울기 + 홈 이점 재적합 · 검증 "
                        f"{got2['n']}경기 · logloss {got2['logloss']}")
                    out = got2
    print()
    if not out:
        print("## 🔴 ③ 둘 다 실패 — **기계 보류 유지**")
        return 0
    print(f"## ✅ 채택 — {out['바닥_출처']}")
    if args.write:
        from fit_base_model import _write
        _write({args.comp: {k: v for k, v in out.items()
                            if k != "바닥_출처"}},
               head="")
        print(f"- 🔴 `config/base_model.yaml` 에 적었다 — `{args.comp}`")
        print(f"- 🔴 바닥 출처 줄: **{out['바닥_출처']}**")
    else:
        print("- ⏸ `--write` 를 주면 `config/base_model.yaml` 에 적는다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
