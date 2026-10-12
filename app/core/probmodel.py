"""🔴🔴 **S3 — 상성 → 기본 확률(= 최종 확률)**. 상성 엔진 지시서(여섯째) S3.

> 3-1 `log λ홈 = 리그 평균 득점(로그) + 홈 이점(리그 실측) + 대회 유형 상수
>      + β·(축0~축3 의 홈 공격 vs 원정 수비 특징)`
> **입력은 MatchupReport 뿐이다.** Elo·동기·일정(T2 경유 제외)·감독 발언·맞대결·
> 시장·LLM 문장은 **금지**(C1).
> 3-3 시뮬레이션 → 승무패·오버·무득점·시간대·선제골 후·예상 스코어.
> 3-4 **축별 기여 분해**(리그 평균 대비): 축0 x · 축1 y · 축2 z · 축3 w — 합 =
>      리그 평균 대비 변화. 축마다 그 기여를 만든 **변수 id 상위 3개**.
> 3-6 **임시 모드**: λ = 리그 평균 × 홈 이점 × exp(임시 계수 × 표준화된 축 차).

🔴 시뮬레이션은 `app/core/sim.py` 하나다(사본 금지).
🔴 C2 — 이 함수가 낸 수가 **카드의 확률**이다. 뒤 단계는 그것을 바꾸지 않는다.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ProbOut:
    """🔴 S3 산출 — 확률·λ·기여 분해·사유."""

    home: float | None = None
    draw: float | None = None
    away: float | None = None
    over: dict = field(default_factory=dict)
    scores: dict = field(default_factory=dict)
    no_goal: dict = field(default_factory=dict)
    by_bucket: dict = field(default_factory=dict)
    first_then_win: dict = field(default_factory=dict)
    first_wins: float | None = None
    lam: dict = field(default_factory=dict)
    #: 🔴 §3 — 검증이 읽는 **기대 득점**(분포 평균). `lam` 과 다르다(상태 배율 반영)
    xg: dict = field(default_factory=dict)
    #: 🔴 3-4 — `{"axis0": %p, …}`(리그 평균 대비) + 축별 주요 변수
    share: dict = field(default_factory=dict)
    share_refs: dict = field(default_factory=dict)
    #: 🔴 C10 — 임시 계수를 썼나(카드가 `🔴 임시` 를 적는다)
    provisional: bool = True
    why: str = ""
    #: 🔴 못 돌았으면 그 사유(#3)
    gap: str = ""

    def ok(self) -> bool:
        return self.home is not None

    def as_sim(self) -> dict:
        """🔴 가설 검증(§4-1)이 읽는 **시뮬 표** 꼴 — 같은 수다(사본 아님)."""
        return {"home": self.home, "draw": self.draw, "away": self.away,
                "over": dict(self.over), "scores": dict(self.scores),
                "no_goal": dict(self.no_goal),
                "by_bucket": dict(self.by_bucket),
                "first_then_win": dict(self.first_then_win),
                "first_wins": self.first_wins, "lam": dict(self.lam),
                "xg": dict(self.xg),
                "share": dict(self.share), "why": self.why}


def _kind(ref, facts) -> str:
    """🔴 대회 유형 열쇠 — `s5_verify.comp_kind` 하나가 만든다(사본 금지).

    돌려주는 꼴: `national_friendly`·`national_official`·`league:<이름>`.
    ⚠️ `ref` 가 없으면 `facts` 만으로 만든다(홈 이점 쪽에서 그렇게 부른다).
    """
    from app.core.stages.s5_verify import comp_kind
    try:
        return str(comp_kind(ref, facts) if ref is not None
                   else comp_kind(_RefShim(facts), facts))
    except Exception:                                       # noqa: BLE001
        return str(getattr(facts, "match_format", "") or "")


class _RefShim:
    """🔴 `ref` 없이 유형을 물을 때의 **최소 모양**(대회 이름만 본다)."""

    def __init__(self, facts) -> None:
        self.competition = ""
        self.competition_short = ""
        self.sport = "soccer"
        self.home = self.away = ""
        self.home_name = self.away_name = ""


def league_mean(facts, *, ref=None) -> tuple[float | None, str]:
    """🔴 3-1 — **리그 평균 득점**(한 팀 몫 = 경기당 총골 ÷ 2).

    🔴 출처는 **둘이고 좁은 쪽이 먼저**다(사본 금지 — 둘 다 이미 있는 것이다):
      ① `facts.standings["match_total_baseline"]` — **이 두 팀**의 경기당 총골
      ② `rules.goal_share(대회 유형)` — **대회 실측 평균**(`config/goal_baselines.yaml`)
    ⚠️ 둘 다 없으면 `(None, 사유)` — S3 를 **안 돈다**(지어내지 않는다 · #4).
    """
    from app import rules
    got = dict(getattr(facts, "standings", None) or {}).get(
        "match_total_baseline")
    if got is not None:
        return float(got) / 2.0, f"두 팀 경기당 총골 {float(got):g}"
    kind = _kind(ref, facts)
    said = rules.goal_share(kind)
    if said is not None:
        box = rules.goal_baseline(kind)
        return float(said), (f"대회 유형 `{kind}` 실측 평균 "
                             f"{float(box.get('goals_per_match') or 0):g}"
                             f"(표본 {box.get('n')})")
    return None, (f"🔴 리그 평균 득점을 **모른다**(두 팀 기준도, 대회 유형 "
                  f"`{kind}` 표도 없다) — S3 를 안 돈다")


#: 🔴🔴 E — 팀별 홈 효과를 **그대로 쓰기 시작하는 표본**(그보다 적으면 수축)
TEAM_HOME_FULL = 8
#: 🔴 팀별 배율의 **상한·하한**(한 팀이 리그를 벗어나지 않게)
TEAM_HOME_LO, TEAM_HOME_HI = 0.80, 1.40


def team_home_mul(games: list[dict], *, league: float) -> tuple[float, str]:
    """🔴🔴 E — 그 팀의 **홈/원정 득실**로 홈 배율. `(배율, 사유)`.

    > 홈 이점을 팀별로 — `games` 의 홈/원정 득실로, 표본 적으면 리그 값으로 수축.
    >   — 사용자 지시 2026-10-11 E

    ⚠️ 실측 2026-10-11: 카드가 *"홈 이점 실측 — 홈 팀 평균 1.6047 ÷ 한 팀 몫
       1.4651 = ×1.095(league:J1)"* 로 **리그 한 수**를 모든 팀에 썼다. 팀별 홈/원정
       득실은 **경기 목록에 이미 있다**.
    🔴 표본이 없으면 **리그 값 그대로**다(지어내지 않는다 · #4). 새 계수를 만들지
       않고 **표본 비율로 수축**한다.
    """
    rows = [dict(g) for g in (games or [])]
    at_home = [g for g in rows if str(g.get("side") or "") == "home"]
    at_away = [g for g in rows if str(g.get("side") or "") == "away"]
    n = min(len(at_home), len(at_away))
    if not n:
        return float(league), (f"리그 값 그대로 ×{float(league):.3f} — 그 팀의 "
                               f"홈 {len(at_home)}경기 · 원정 {len(at_away)}경기")
    gf_h = sum(float(g.get("gf") or 0.0) for g in at_home) / len(at_home)
    gf_a = sum(float(g.get("gf") or 0.0) for g in at_away) / len(at_away)
    if gf_a <= 0:
        return float(league), (f"리그 값 그대로 ×{float(league):.3f} — 원정 득점이 "
                               f"0 이라 비를 못 만든다")
    raw = max(TEAM_HOME_LO, min(TEAM_HOME_HI, gf_h / gf_a))
    w = min(n, TEAM_HOME_FULL) / float(TEAM_HOME_FULL)
    got = (1.0 - w) * float(league) + w * raw
    return round(got, 4), (f"팀별 홈 효과 ×{raw:.3f}(홈 {gf_h:.2f}골 ÷ 원정 "
                           f"{gf_a:.2f}골) · 표본 {n}쌍 → 수축 가중 {w:.0%} · "
                           f"리그 ×{float(league):.3f} → **×{got:.3f}**")


def home_mul(facts, varset, *, ref=None,
             home_games: list[dict] | None = None
             ) -> tuple[float | None, str]:
    """🔴🔴 3-1 — **홈 이점(리그 실측)**. ⚠️ 없으면 **1.0**(다른 대회에서 안 빌린다).

    🔴 실측은 `config/goal_baselines.yaml` 의 `home_share` 다 — *"홈 개최 경기의
       **홈 팀** 평균 득점"*. 그것을 **한 팀 몫**(경기당 ÷ 2)으로 나누면 홈 배율이다.
    🔴 `home_field`(S03) 변수는 `lambda_const` 자리에 있다 — 그 변수가 *"수치
       없음"* 이라고 적으면 그 사실을 사유에 함께 남긴다(#3).
    ⚠️ 중립 경기(홈이 없는 대회)에는 **쓰지 않는다** — `home_share` 가 없으면 1.0.
    """
    from app import rules
    from app.core import matchup as _m
    box = dict(_m.table().get("lambda_model") or {})
    # 🔴🔴 **`ref` 를 받는다** — ⚠️ 실사고 2026-10-10(제노아 vs 피오렌티나):
    #    `ref` 없이 부르면 `_RefShim` 이 대회 이름을 **빈 글자**로 주고, 그래서
    #    리그 평균은 `league:SA`(표본 810)를 보는데 홈 배율은 `` 를 봤다 —
    #    **같은 모형 안에서 열쇠가 둘**이었다. 실측 `home_share 1.3185 ÷ 1.2592
    #    = ×1.047` 이 있었는데 *"실측 없음 → 1.0"* 으로 버려졌고, 카드의 S03 줄은
    #    *"`league:SA` 의 표가 없다"* 라고 **거짓**을 적었다(표는 있다).
    kind = _kind(ref, facts)
    said = rules.goal_baseline(kind)
    share, per = said.get("home_share"), rules.goal_share(kind)
    rows = [one for one in (varset.of("lambda_const") if varset else [])
            if str(one.type) == "home_field"]
    tag = f" · 변수 `{rows[0].id}`" if rows else ""
    if share is None or not per:
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **"실측 없음 → 1.0" 경로를 지웠다**(사용자 지시 2026-10-11 ①)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 1.0 은 *"홈 이점이 없다"* 는 **주장**이다 — 못 쟀다는 말과 다르다.
        #     실측 2026-10-11: MLS 가 그 길로 1.0 을 썼는데, 리그 결과 414경기를
        #     재 보니 **홈 1.845 · 원정 1.394(×1.139)** 였다. 조용한 1.0 이
        #     원정 쪽으로 확률을 밀고 있었다.
        #  🔴 못 쟀으면 **`None` 과 사유**다 — 표를 채우는 길은
        #     `tools/measure_fotmob_baselines.py`(그 리그 결과로 잰다).
        return (None, f"🔴 홈 이점 **실측 없음**(대회 `{kind}`) — "
                      f"`tools/measure_fotmob_baselines.py` 로 그 리그 결과를 "
                      f"재서 표에 적어야 한다{tag}")
    mul = float(share) / float(per)
    # 🔴🔴 E — **팀별 홈 효과로 수축**한다(그 팀 경기 목록이 있으면)
    if home_games:
        got, said_team = team_home_mul(home_games, league=mul)
        return got, (f"홈 이점 실측 — 홈 팀 평균 {float(share):g} ÷ 한 팀 몫 "
                     f"{float(per):g} = ×{mul:.3f}(대회 `{kind}`){tag}"
                     f" · {said_team}")
    return mul, (f"홈 이점 실측 — 홈 팀 평균 {float(share):g} ÷ 한 팀 몫 "
                 f"{float(per):g} = ×{mul:.3f}(대회 `{kind}`){tag}")


def sides_move(box: dict, weights: dict, *, beta: float, cap: float) -> dict:
    """🔴🔴 **F3** — 축별 공격·수비 특징 → **쪽별 λ 이동**(로그).

    > log λ홈  = … + Σ_축 β_축 ·(홈 공격_축 − 원정 수비_축)
    > log λ원정 = … + Σ_축 β_축 ·(원정 공격_축 − 홈 수비_축)

    `box` 한 줄: `{"axis0": {"att": {"home": …, "away": …}, "dfn": {…}}}`.
    🔴 **쪽마다 자기 식**이다 — 축 종합 숫자 하나로 두 λ 를 만들지 않는다(R5).
    ⚠️ 못 잰 칸(`None`)은 **0 이 아니라 건너뛴다** — 그 축은 그 쪽 λ 를 안 민다(#3).
    """
    out = {"home": 0.0, "away": 0.0}
    for key, one in (box or {}).items():
        w = float(dict(weights or {}).get(key) or 0.0)
        if not w:
            continue
        att = dict((one or {}).get("att") or {})
        dfn = dict((one or {}).get("dfn") or {})
        pairs = (("home", att.get("home"), dfn.get("away")),
                 ("away", att.get("away"), dfn.get("home")))
        for side, mine, theirs in pairs:
            if mine is None or theirs is None:
                continue
            out[side] += w * float(beta) * (float(mine) - float(theirs))
    return {k: max(-float(cap), min(float(cap), v)) for k, v in out.items()}


def run(ref, facts, mr, varset, *, edge: dict | None = None,
        state=None) -> ProbOut:
    """🔴🔴 S3 — **상성만으로** λ 를 세고 시뮬로 바꾼다.

    `mr` 은 `matchup.MatchupReport` 다. ⚠️ `facts` 에서 읽는 것은 **리그 평균**
    하나다(C1: Elo·동기·일정·감독·맞대결·시장은 안 읽는다).
    """
    from app.core import matchup as _m
    from app.core import sim as _sim
    got = ProbOut()
    mean, why_mean = league_mean(facts, ref=ref)
    if mean is None:
        got.gap = why_mean
        _note(state, f"S3 {why_mean}")
        return got
    conf = dict(_m.table().get("lambda_model") or {})
    fit = dict(_m.table().get("fit") or {})
    got.provisional = bool(fit.get("provisional", True))
    beta = float(conf.get("beta") or 0.0)
    cap = float(conf.get("cap_pct") or 35.0) / 100.0
    # 🔴 E — **홈팀의 경기 목록**을 넘긴다(팀별 홈 효과로 수축한다)
    said_games = list(dict((getattr(facts, "recent", None) or {})
                           .get(str(getattr(ref, "home", "")) or "") or {})
                      .get("games") or [])
    mul, why_home = home_mul(facts, varset, ref=ref, home_games=said_games)
    if mul is None:
        # 🔴 홈 이점을 못 쟀으면 **S3 를 안 돈다** — 조용히 1.0 으로 가지 않는다.
        got.gap = why_home
        _note(state, f"S3 {why_home}")
        return got
    # 🔴 3-1 — 축 차 하나로 두 팀 λ 를 **반대 방향으로** 기울인다
    gaps = mr.gaps()
    weights = dict(_m.table().get("weights") or {})
    tilt = sum(float(weights.get(k) or 0.0) * float(v) for k, v in gaps.items())
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **F3 — 쪽마다 자기 식**(지시서 2026-10-11)
    # ══════════════════════════════════════════════════════════════════
    #
    #  log λ홈  = log(리그 평균) + 홈 이점 + Σ_축 β_축 ·(홈 공격_축 − 원정 수비_축)
    #  log λ원정 = log(리그 평균)          + Σ_축 β_축 ·(원정 공격_축 − 홈 수비_축)
    #
    #  ⚠️ 종전에는 **축 종합 하나**로 `exp(+move)`·`exp(-move)` 를 만들었다 — 두 λ 가
    #     거울이라 *"홈이 좋으면 원정이 그만큼 나쁘다"* 가 **식에 박혀** 있었다.
    #  🔴 `tilt` 는 이제 **보고용**이다(카드가 종합을 적는다) — λ 는 안 만든다.
    sides = {k: mr.axis(k).sides() for k in weights}
    move = sides_move(sides, weights, beta=beta, cap=cap)
    lam_h = mean * mul * math.exp(move["home"])
    lam_a = mean * math.exp(move["away"])
    got.lam = {"home": round(lam_h, 4), "away": round(lam_a, 4)}
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **3-2 시간대·경기 상태** — 축3 이 구간과 상태 배율을 준다
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 축3 **시간대 비중**으로 λ 를 구간 분할, **리드 유지력·추격력**으로
    #  > 상태별 배율.
    #
    #  🔴 그 재료를 만드는 곳은 `goals.sim_input` 하나다(사본 금지) — 발동 규칙의
    #     `lambda_own_late`·T11 상태 배율을 거기서 읽는다.
    #  ⚠️ C9 — `관찰만` 규칙은 그 함수가 **빼고** 준다(λ 에 안 들어간다).
    from app.core import goals as _g
    # 🔴 F3/R4 — **규칙 λ 를 더하지 않는다**(축 안에서 이미 한 번 셌다).
    #    시간대·상태 배율만 시뮬 안으로 보낸다(`sim_extras` 는 λ 를 안 준다).
    args = _g.sim_extras(dict(edge or {}))
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **[2c] 상태별 득점률 표를 시뮬로 넘긴다**(지시서 2026-10-12)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > ⑪ 분 단위 시뮬 루프 안. 매 분 현재 스코어로 각 팀 상태를 정하고
    #  > λ분당 × 그 상태 배율. 기존 축3 시간대 배율과 **한 표로 합친다**.
    #
    #  🔴 표가 있으면 시뮬이 **T11 임시 배율을 끈다**(`sim.run` 의 S1 규율) —
    #     같은 효과를 두 번 곱하지 않는다.
    #  ⚠️ 표는 ③ 이 `facts.state_rates` 에 실어 온다. 비면 **없는 것**이고
    #     T11 이 그대로 돈다(퇴로).
    said_state = dict(getattr(facts, "state_rates", None) or {})
    out = _sim.run(lam_h, lam_a,
                   late_home=args["late_home"], late_away=args["late_away"],
                   lead_mul=args["lead_mul"],
                   state_mult=(said_state or None))
    _fill(got, out)
    why_rules = str(args.get("why") or "")
    # 🔴 3-4 — **리그 평균 대비** 축별 기여(합 = 전체 변화)
    base = _sim.run(mean * mul, mean)
    got.share, got.share_refs = _share(mean, mul, beta, cap, weights, gaps, mr,
                                       base=base)
    got.why = (f"{why_mean} → 한 팀 평균 {mean:.3f} · {why_home} · 축 종합 "
               f"{tilt:+.3f} × β {beta:g} → λ 이동 홈 {move['home']:+.3f} · "
               f"원정 {move['away']:+.3f}"
               + (f"(상한 ±{cap:.0%})"
                  if max(abs(move['home']), abs(move['away'])) >= cap else "")
               + (f" · 규칙(축 안에서 셌다) {why_rules}" if why_rules else "")
               + (" · 📜 **상태 배율**(실측 표 · T11 끔) "
                  + _state_said(facts) if said_state else "")
               + (f" · {_m.PROVISIONAL}" if got.provisional else ""))
    _note(state, f"S3 확률(상성) — 홈 {got.home:.1%} · 무 {got.draw:.1%} · "
                 f"원정 {got.away:.1%} · {got.why}")
    logger.info("[S3] %s", got.why)
    return got


def _state_said(facts) -> str:
    """🔴 [2c] — 카드가 적을 **상태 배율 한 줄**(표의 사유까지)."""
    from app.core import staterates as _sr
    return _sr.said_of(dict(getattr(facts, "state_rates", None) or {}),
                       dict(getattr(facts, "state_rates_why", None) or {}))


def _fill(got: ProbOut, out) -> None:
    got.home, got.draw, got.away = out.home, out.draw, out.away
    got.xg = dict(out.xg)
    got.over = dict(out.over)
    got.scores = dict(sorted(out.scores.items(),
                             key=lambda kv: -float(kv[1]))[:40])
    got.no_goal = dict(out.no_goal)
    got.by_bucket = {k: dict(v) for k, v in dict(out.by_bucket).items()}
    got.first_then_win = dict(out.first_then_win)
    got.first_wins = out.first_wins


def _share(mean: float, mul: float, beta: float, cap: float, weights: dict,
           gaps: dict, mr, *, base) -> tuple[dict, dict]:
    """🔴🔴 3-4 — 축별 기여(%p). **합이 리그 평균 대비 변화와 같다**.

    🔴 재는 법: 축을 **하나씩 더해** 가며 홈 승 확률의 차를 적는다(겹침 없이
       합이 정확하다 · 잔차 0).
    """
    from app.core import sim as _sim
    out: dict = {}
    refs: dict = {}
    run = 0.0
    prev = float(base.home)
    for name in ("axis0", "axis1", "axis2", "axis3"):
        run += float(weights.get(name) or 0.0) * float(gaps.get(name) or 0.0)
        move = max(-cap, min(cap, beta * run))
        now = _sim.run(mean * mul * math.exp(move), mean * math.exp(-move))
        out[name] = round((float(now.home) - prev) * 100.0, 2)
        prev = float(now.home)
        refs[name] = list(mr.axis(name).refs)[:3]
    return out, refs


def _note(state, said: str) -> None:
    if state is not None:
        state.note(said)


def league_base(ref, facts, varset) -> dict | None:
    """🔴 3-4 의 기준선 — **리그 평균만**으로 돈 확률(축 기여가 0일 때의 수).

    ⚠️ 리그 평균이 없으면 `None`(지어내지 않는다).
    """
    from app.core import sim as _sim
    mean, _why = league_mean(facts, ref=ref)
    if mean is None:
        return None
    mul, _said = home_mul(facts, varset, ref=ref)
    if mul is None:
        return None            # 🔴 기준 분포도 홈 이점 없이는 안 만든다
    out = _sim.run(mean * mul, mean)
    return {"home": out.home, "draw": out.draw, "away": out.away}
