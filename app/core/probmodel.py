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
    #: 🔴🔴 **그림자 확률**(사용자 결정 2026-10-12 (a)) — **옛 구조**(네 축)의 수다.
    #   ⚠️ **표시만** 한다 — 판정·등급·보드는 새 구조(Elo 바닥 + 축0·축1)가 낸다.
    shadow: dict = field(default_factory=dict)
    #: 🔴 바닥(Elo)이 낸 승무패 — 카드가 그 줄을 적는다
    floor: dict = field(default_factory=dict)
    #: 🔴🔴 **앙상블**(지시 2026-10-13 밤 다섯째 1번 · 판정 E1 채택) — 무엇을 어떤
    #   가중치로 섞었나 · 섞기 **전** 수. 안 섞었으면 사유만 든다.
    ens: dict = field(default_factory=dict)
    #: 🔴🔴 **무승부 보정**(5번) — 걸었으면 그 판과 값, 안 걸었으면 비어 있다
    draw_fix: dict = field(default_factory=dict)
    #: 🔴🔴 **C4 재정의**(사용자 결정 2026-10-12) — 상성이 λ 를 **민 방향**이다.
    #   `{"home": +x, "away": -x}` · 홈 이점(상수)은 **여기 안 들어간다**.
    move: dict = field(default_factory=dict)
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
    🔴🔴 **①은 표본으로 ②에 수축한다**(수정 지시 2026-10-13 4번) —
       `w = min(1, 표본/BASE_FULL)` · 표본 ≥8경기면 ① 그대로다.
    ⚠️ 둘 다 없으면 `(None, 사유)` — S3 를 **안 돈다**(지어내지 않는다 · #4).
    """
    from app import rules
    box_std = dict(getattr(facts, "standings", None) or {})
    got = box_std.get("match_total_baseline")
    kind = _kind(ref, facts)
    if got is not None:
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **표본으로 수축한다**(수정 지시 2026-10-13 4번)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 실사고 2026-10-13(상하이–대전): **ACL 리그 단계 2경기**로 센 두 팀
        #     총골 **5.5** 가 λ 바닥이 됐다 — 대회 실측 2.8213 의 **1.95배**이고
        #     총골 기대가 4.99 로 나왔다. 좁은 출처가 먼저인 것은 맞지만
        #     **표본 2경기는 잡음**이다.
        #  🔴 새 계수를 만들지 않는다 — `team_home_mul` 과 **같은 수축**이다:
        #     가중 `w = min(1, 표본/BASE_FULL)` 로 **대회 실측 평균**과 섞는다.
        #     표본이 충분하면(≥8경기) 종전과 **같은 수**다.
        said_comp = rules.goal_share(kind)
        said_n = box_std.get("match_total_played")
        mine = float(got) / 2.0
        if said_comp is None:
            return mine, (f"두 팀 경기당 총골 {float(got):g}"
                          f"(표본 {said_n if said_n is not None else '?'}경기)"
                          f" · ⬜ 대회 실측 평균이 없어 **수축 못 했다**")
        if said_n is None:
            # 🔴 **표본을 모르면 수축하지 않는다** — 모르는 것을 작다고 보면
            #    옛 카드·계약의 수가 조용히 바뀐다(실측: 계약 둘이 빨개졌다).
            return mine, (f"두 팀 경기당 총골 {float(got):g} · ⬜ **표본 칸이 "
                          f"없다**(`match_total_played`) — 수축 못 했다")
        n_played = int(said_n or 0)
        w = min(1.0, n_played / BASE_FULL) if n_played else 0.0
        mix = w * mine + (1.0 - w) * float(said_comp)
        if w >= 1.0:
            return mine, (f"두 팀 경기당 총골 {float(got):g}"
                          f"(표본 {n_played}경기 ≥ {BASE_FULL} → 그대로)")
        return mix, (f"두 팀 경기당 총골 {float(got):g}(표본 "
                     f"{n_played or 0}경기) **수축 {w:.0%}** ↔ 대회 "
                     f"`{kind}` 실측 {float(said_comp) * 2:g}골 "
                     f"{1 - w:.0%} → 한 팀 몫 {mix:.3f}"
                     f"(두 팀 총골 {mix * 2:.3f})")
    said = rules.goal_share(kind)
    if said is not None:
        box = rules.goal_baseline(kind)
        return float(said), (f"대회 유형 `{kind}` 실측 평균 "
                             f"{float(box.get('goals_per_match') or 0):g}"
                             f"(표본 {box.get('n')})")
    return None, (f"🔴 리그 평균 득점을 **모른다**(두 팀 기준도, 대회 유형 "
                  f"`{kind}` 표도 없다) — S3 를 안 돈다")


#: 🔴🔴 **두 팀 총골 기준을 그대로 쓰기 시작하는 표본**(그보다 적으면 대회 실측
#   평균으로 수축 · 수정 지시 2026-10-13 4번). 🔴 `TEAM_HOME_FULL` 과 **같은 수**다
#   (새 계수를 만들지 않는다 — 이미 쓰고 있는 문턱을 쓴다).
BASE_FULL = 8

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


def away_mul(*, home_share: float | None, per_team: float | None
             ) -> tuple[float, str]:
    """🔴🔴 2(b) — **원정 배율**. `(배율, 사유)`. 실측이 없으면 `1.0`.

    > λ 기준: … **원정 λ 에 원정 배율**(원정 평균 ÷ 한 팀 몫)이 들어가는가.

    🔴 감사 2026-10-12: 종전 식은 `lam_a = mean`(= 한 팀 평균)이었다 — 원정 팀이
       평균보다 **덜 넣는다**는 실측을 버린 것이다. 라리가 per_team 1.3444 ·
       home_share 1.5296 → away_share **1.1592** 인데 1.3444 를 써서 **+16% 과대**.
    🔴 `away_share = 2 × per_team − home_share`(총골 = 홈 몫 + 원정 몫).
    """
    if home_share is None or not per_team:
        return 1.0, "⬜ 원정 배율 — 실측이 **없다**(1.0 · 다른 대회에서 안 빌린다)"
    away = 2.0 * float(per_team) - float(home_share)
    if away <= 0:
        return 1.0, "🔴 원정 몫이 0 이하다 — 1.0 으로 둔다(수가 이상하다)"
    got = away / float(per_team)
    return got, (f"원정 몫 {away:.4f} ÷ 한 팀 몫 {float(per_team):.4f} = "
                 f"×{got:.3f}")


def side_center(*, home_share: float | None, per_team: float | None
                ) -> tuple[float, str]:
    """🔴🔴 2(a) — **쪽 폼 중심화 값 Δ**. `(Δ, 사유)`. 실측이 없으면 `0.0`.

    🔴 홈에서 뛴 팀의 득실차에는 **홈 이점이 이미** 들어 있다:
       기대 득 `home_share` − 기대 실 `away_share` = **Δ**.
       그 Δ 가 축1 로 들어가고 λ 홈 배율이 **또** 걸리면 **이중 계산**이다.
    🔴 그래서 쪽 폼에서 Δ 를 뺀다(원정 쪽은 더한다).
    """
    if home_share is None or not per_team:
        return 0.0, "⬜ 중심화 — 홈 이점 실측이 없다(0.0)"
    away = 2.0 * float(per_team) - float(home_share)
    got = float(home_share) - away
    return got, (f"중심화 Δ = 홈 몫 {float(home_share):.4f} − 원정 몫 "
                 f"{away:.4f} = {got:.4f}")


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
        state=None, floor: object = None) -> ProbOut:
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
    # 🔴🔴 2(b) — **원정 배율을 건다**(사용자 지시 2026-10-12). ⚠️ 종전엔 원정이
    #    `mean`(한 팀 평균)이었다 — 원정 팀이 덜 넣는다는 실측을 버린 식이다.
    from app import rules as _rules
    said_kind = _kind(ref, facts)
    said_base = _rules.goal_baseline(said_kind)
    mul_a, why_mul_a = away_mul(home_share=said_base.get("home_share"),
                                per_team=_rules.goal_share(said_kind))
    lam_h = mean * mul * math.exp(move["home"])
    lam_a = mean * mul_a * math.exp(move["away"])
    got.lam = {"home": round(lam_h, 4), "away": round(lam_a, 4)}
    # 🔴 C4 — **상성이 민 방향**을 따로 싣는다(상수를 뺀 수다)
    got.move = {k: round(float(v), 4) for k, v in dict(move).items()}
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
    # 🔴 기준선도 **같은 식**이어야 한다 — 원정 배율을 빼면 분해 합이 안 맞는다
    #    (계약 `test_v7_기여_합이_리그_평균_대비_변화와_같다` 가 그것을 센다)
    base = _sim.run(mean * mul, mean * mul_a)
    got.share, got.share_refs = _share(mean, mul, beta, cap, weights, gaps, mr,
                                       base=base, mul_a=mul_a)
    got.why = (f"{why_mean} → 한 팀 평균 {mean:.3f} · {why_home} · "
               f"{why_mul_a} · 축 종합 "
               f"{tilt:+.3f} × β {beta:g} → λ 이동 홈 {move['home']:+.3f} · "
               f"원정 {move['away']:+.3f}"
               + (f"(상한 ±{cap:.0%})"
                  if max(abs(move['home']), abs(move['away'])) >= cap else "")
               + (f" · 규칙(축 안에서 셌다) {why_rules}" if why_rules else "")
               + (" · 📜 **상태 배율**(실측 표 · T11 끔) "
                  + _state_said(facts) if said_state else "")
               + (f" · {_m.PROVISIONAL}" if got.provisional else ""))
    # 🔴🔴 **C4 재정의**(사용자 결정 2026-10-12) — 상성이 민 방향과 **최종 확률**이
    #    다르면 그 사실을 사유에 적는다: *"상성 X 우위 · 홈 이점이 뒤집음(배율)"*.
    said_edge = mr.edge_of() if hasattr(mr, "edge_of") else ""
    said_win = "home" if got.home >= got.away else "away"
    if said_edge and said_win != said_edge:
        got.why += (f" · 🔴 **상성 {said_edge} 우위 · 홈 이점이 뒤집음**"
                    f"(배율 홈 ×{mul:.3f} · 원정 ×{mul_a:.3f})")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **⑯ 배선 — 새 구조가 판정이다**(사용자 결정 2026-10-12 (a))
    # ══════════════════════════════════════════════════════════════════
    #
    #  > (a) 새 구조로 운영 ⑯ 을 잇는다. 옛 구조는 **그림자 확률**로 카드에 함께
    #  > 기록(표시만, 판정은 새 구조).
    #
    #  🔴 새 구조 = **Elo 바닥**(③)을 λ 로 번역하고 그 위에 **축0·축1 잔차**만 얹는다.
    #     축2·축3 은 백필에서 **손실**이었다(−0.0038 · −0.0039) → 확률 경로 밖이다.
    #  ⚠️ 바닥이 없으면(Elo 없음) **옛 구조가 그대로 남는다** — 그 사실을 사유에 적는다.
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **운영 교체 — ⑯ = M1(옛 경로) · 그림자 = M3**(사용자 결정 2026-10-12)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 운영 교체: 운영 ⑯ = **M1**(옛 경로 legacy-4axis), 그림자 = **M3**.
    #  > 근거: M3 가 **어느 지표에서도 M1 을 앞서지 못함**(방향·선택 적중률·로그
    #  > 손실 점추정 모두 M1 우세). 2층 통로·경고·InfoQ·역배 표시·코드 서술은
    #  > 유지(**확률 엔진만** 교체).
    #
    #  🔴 비교 시험(460경기 · 시즌 교차): M1 로그손실 **1.0471** vs M3 1.0548 ·
    #     방향 **51.5%** vs 45.7% · 상위 30/20/10% **57.2/58.7/65.2** vs
    #     50.0/54.3/56.5 · 맥니마 b=54·c=27·p=0.0036.
    #  ⚠️ **규칙 해석으로는 M3 유지**였다(§7 (a) 의 구간 상한 +0.005 를 못 넘었다)
    #     — 그 기록은 `docs/fable/stages/2026-10-12_compare_paths.md` 에 그대로
    #     남는다. 🔴 **운영 판단은 사용자가 따로** 내렸다(이 주석이 그 자리다).
    #  🔴 **M1 은 얼린 코드**다(`legacy/old_engine` · 계약 K0) — 이 모듈이 다시
    #     계산하지 않는다. 그래야 운영이 백필의 M1 과 **같은 모형**을 쓴다.
    from app.core.legacy import old_engine as _oe
    said_m1 = None
    try:
        said_m1 = _oe.run(ref, facts, mr, varset, edge=edge, state=None)
    except Exception as exc:                                # noqa: BLE001
        logger.info("[S3] M1(얼린 옛 경로) 실패 — %r", exc)
    said_floor = _floor_triple(floor)
    if said_floor:
        got.floor = {"home": round(said_floor[0], 4),
                     "draw": round(said_floor[1], 4),
                     "away": round(said_floor[2], 4)}
    # ── 🔴 **M3(새 경로)를 먼저 세운다** — 이제 그것이 **그림자**다
    said_m3: dict = {}
    if said_floor:
        from app.core import probfloor as _pf
        m0, why_m0 = _pf.solve_move(said_floor, mean=mean, mul_home=mul,
                                    mul_away=mul_a)
        if m0 is not None:
            res = sum(float(weights.get(k) or 0.0)
                      * float(gaps.get(k) or 0.0) for k in _pf.RESIDUAL_AXES)
            rmove = max(-cap, min(cap, beta * res))
            lam_h3 = mean * mul * math.exp(m0 + rmove)
            lam_a3 = mean * mul_a * math.exp(-(m0 + rmove))
            out3 = _sim.run(lam_h3, lam_a3,
                            late_home=args["late_home"],
                            late_away=args["late_away"],
                            lead_mul=args["lead_mul"],
                            state_mult=(said_state or None))
            said_m3 = {"home": out3.home, "draw": out3.draw,
                       "away": out3.away,
                       # 🔴 **격자를 들고 있는다** — 앙상블이 승무패가 아니라
                       #    **격자**를 섞는다(C2 · EW1)
                       "grid": {(int(h), int(a)): float(v)
                                for (h, a), v in dict(out3.scores or {}).items()},
                       "lam": {"home": round(lam_h3, 4),
                               "away": round(lam_a3, 4)},
                       "why": (f"M3 **새 경로**(Elo 바닥 + 축0·축1 잔차) — "
                               f"{why_m0} · 잔차 {res:+.3f}×β {beta:g} → "
                               f"λ 이동 {rmove:+.3f} · 표시·채점용이고 "
                               f"**판정에 안 쓴다**")}
        else:
            said_m3 = {"why": f"🔴 M3 를 못 세웠다 — {why_m0}"}
    # ── 🔴🔴 **운영 수 = M1**(얼린 옛 경로). 못 내면 이 모듈의 네 축 수를 둔다.
    if said_m1 is not None and said_m1.ok():
        got.home, got.draw, got.away = (said_m1.home, said_m1.draw,
                                        said_m1.away)
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **5번 무승부 보정** — 얼린 격자 **뒤**에 건다(K0 를 안 건드린다)
        # ══════════════════════════════════════════════════════════════
        #
        #  🔴 실측(460경기 교차): ρ+0.2 로 로그손실 1.0527 → **1.0474**
        #     (−0.0054 · 95% −0.0127~+0.0015) · 방향 **49.5% 그대로** ·
        #     무승부 예측 26.8% → **22.7%**(실제 22.1%).
        #  ⚠️ 판이 없으면 **보정하지 않는다**(손값 금지) — 사유를 적는다.
        from app.core import drawfix as _dfx
        # 🔴🔴 **전체 격자를 한 번 만든다** — 꼴 맞추기(글자 열쇠 → 쌍)를 **여기
        #    한 곳**에서 한다. ⚠️ 종전에는 무승부 보정이 격자를 굽히고 **그 아래
        #    줄이 굽지 않은 격자로 다시 덮어썼다** — 그래서 승무패는 보정 뒤 수,
        #    스코어 줄은 보정 **전** 수였다(한 카드가 두 분포를 말했다 · C2 위반).
        grid_m1: dict = {}
        for key, val in dict(said_m1.scores or {}).items():
            if isinstance(key, str) and "-" in key:
                h, a = key.split("-", 1)
                grid_m1[(int(h), int(a))] = float(val)
            else:
                grid_m1[(int(key[0]), int(key[1]))] = float(val)
        said_fix, why_fix = _dfx.load(
            league=_kind(ref, facts),
            as_of=getattr(ref, "kickoff_utc", None))
        if said_fix and grid_m1:
            bent = _dfx.bend(grid_m1, rho=float(said_fix.get("rho") or 0.0),
                             draw=float(said_fix.get("draw") or 0.0))
            said_three = _dfx.triple(bent)
            # 🔴 **보정 전 수를 남긴다** — 축 기여 분해(`share`)는 **보정 전**
            #    확률을 설명한다. ⚠️ 그 사실을 칸으로 두지 않으면 카드의 분해 합이
            #    최종 확률과 안 맞는 이유를 아무도 모른다(계약이 그것을 잡았다).
            got.draw_fix = {"before_home": round(float(got.home), 6),
                            "before_draw": round(float(got.draw), 6),
                            "before_away": round(float(got.away), 6)}
            got.home, got.draw, got.away = said_three
            grid_m1 = dict(bent)          # 🔴 **굽힌 격자가 M1 격자다**
            got.draw_fix.update({"why": why_fix,
                                 **{k: float(v) for k, v in said_fix.items()
                                    if isinstance(v, (int, float))}})
        # ⚠️ **꼴은 위에서 맞췄다** — 얼린 경로는 스코어 열쇠를 `"1-0"` 글자로
        #    담고, 카드·생존은 `(1, 0)` 쌍을 본다(얼린 파일은 안 고친다 · K0).
        got.scores = dict(grid_m1)
        got.over = dict(said_m1.over or {})
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **앙상블 — ⑯ 안에서 격자로 섞는다**(지시 2026-10-13 밤 다섯째 1번)
        # ══════════════════════════════════════════════════════════════
        #
        #  🔴 판정(누설 제거 뒤 **2,582경기** · 규칙 v2+(d)): **E1 채택** —
        #     로그 손실 1.0498 vs E0 1.0525 · 짝지은 −0.0026(95% −0.0058~+0.0007)
        #     · 맥니마 p 0.1334 · 상위 20% 61.43% vs 60.85%.
        #  ⚠️ **방향은 E0 가 낫다**(46.51% vs 47.37% · 뒤집힌 288경기에서 E0
        #     109 : E1 87) — 규칙 (b) 는 *"B 우세가 유의하지 않으면 통과"* 라서
        #     통과했다. 🔴 그 사실을 **카드가 적는다**(숨기지 않는다).
        #  🔴 **EW1** 섞는 것은 **격자**다(승무패만 섞으면 오버·핸디캡이 그 확률과
        #     어긋난다 · C2) · **EW2** 판이 없으면 **M1 단독** · **EW3** 섞은 뒤의
        #     모든 시장 줄은 `probfloor.markets_of` 로 **그 격자 하나**에서 나온다.
        #  ⚠️ **순서** — 무승부 보정(ρ)을 **먼저** 걸고 그 격자를 섞는다. 두 보정의
        #     **합성은 아직 안 재 봤다**(각각 M1 대비로만 쟀다) — 후속 과제다.
        from app.core import ensemble as _en
        said_plate, why_plate = _en.plate_of(
            league=_kind(ref, facts), as_of=getattr(ref, "kickoff_utc", None))
        if not dict(said_plate or {}).get("adopted"):
            got.ens = {"why": (f"⬜ **앙상블 미적용** — 채택된 판이 없다"
                               f"(M1 단독 · {why_plate})")}
        else:
            box_g: dict = {}
            why_g = ""
            for name, one in (("M1", grid_m1),
                              ("M3", dict(said_m3.get("grid") or {}))):
                said_n, why_n = _en.normalise(one)
                if said_n:
                    box_g[name] = said_n
                else:
                    why_g += f" · {name}: {why_n}"
            mixed, why_mix = _en.of(box_g, plate=dict(said_plate))
            if not mixed:
                got.ens = {"why": f"🔴 {why_mix}{why_g}"}
            else:
                # 🔴 **C1** — `run` 안에 시장(`market`) 글자를 두지 않는다. 격자
                #    에서 줄을 뽑는 일은 **모듈 함수**가 한다(`_lines_from`).
                said_mk = _lines_from(mixed)
                got.ens = {"w": dict(dict(said_plate).get("w") or {}),
                           "before": {"home": round(float(got.home), 6),
                                      "draw": round(float(got.draw), 6),
                                      "away": round(float(got.away), 6)},
                           "why": (f"{why_mix} · 판 {why_plate}"),
                           # 🔴 방향 주의 — 판정에서 **방향은 E0 가 나았다**
                           "note": ("⚠️ 방향 적중률은 판정에서 **M1 단독이 더 "
                                    "높았다**(46.5% vs 47.4% · 유의하지 않다)")}
                got.home = round(float(said_mk["home"]), 6)
                got.draw = round(float(said_mk["draw"]), 6)
                got.away = round(float(said_mk["away"]), 6)
                got.scores = dict(sorted(mixed.items(),
                                         key=lambda kv: -kv[1])[:40])
                # 🔴 **EW3** — 오버도 그 격자에서(열쇠 꼴은 시뮬과 같다)
                got.over = {f"{k}": round(float(v), 4)
                            for k, v in dict(said_mk.get("over") or {}).items()}
                got.xg = {"home": round(sum(h * v for (h, _a), v
                                            in mixed.items()), 4),
                          "away": round(sum(a * v for (_h, a), v
                                            in mixed.items()), 4)}
        got.lam = dict(said_m1.lam or {})
        got.move = dict(said_m1.move or {})
        if said_m1.share:
            got.share = dict(said_m1.share)
        got.why = (f"🔴🔴 **운영 = M1 얼린 옛 경로**(legacy-4axis · 네 축) — "
                   f"{said_m1.why}"
                   + (f" · 🎯 **무승부 보정** ρ "
                      f"{float(got.draw_fix.get('rho') or 0.0):+.2f}"
                      f"({got.draw_fix.get('why')})"
                      if got.draw_fix else " · ⬜ 무승부 보정 없음(판 없음)")
                   + (f" · 🕯 그림자 M3 홈 {float(said_m3['home']):.1%}"
                      if said_m3.get("home") is not None
                      else f" · 🕯 {said_m3.get('why', '그림자 없음')}"))
    else:
        got.why = (f"⚠️ **M1 을 못 냈다** — 이 모듈의 네 축 수로 간다 · {got.why}")
    got.shadow = dict(said_m3)
    _note(state, f"S3 확률(상성) — 홈 {got.home:.1%} · 무 {got.draw:.1%} · "
                 f"원정 {got.away:.1%} · {got.why}")
    logger.info("[S3] %s", got.why)
    return got


def _floor_triple(floor: object) -> list[float] | None:
    """🔴 바닥을 **세 수**로 받는다(`ProbTriple`·사전·목록 전부). 없으면 `None`."""
    if floor is None:
        return None
    got = floor
    if hasattr(got, "home") and hasattr(got, "away"):
        got = {"home": got.home, "draw": got.draw, "away": got.away}
    if isinstance(got, dict):
        said = [got.get("home"), got.get("draw"), got.get("away")]
    elif isinstance(got, (list, tuple)) and len(got) == 3:
        said = list(got)
    else:
        return None
    if any(v is None for v in said):
        return None
    out = [float(v) for v in said]
    return out if abs(sum(out) - 1.0) < 0.02 else None


def _state_said(facts) -> str:
    """🔴 [2c] — 카드가 적을 **상태 배율 한 줄**(표의 사유까지)."""
    from app.core import staterates as _sr
    return _sr.said_of(dict(getattr(facts, "state_rates", None) or {}),
                       dict(getattr(facts, "state_rates_why", None) or {}))


def _lines_from(grid: dict) -> dict:
    """🔴🔴 **EW3** — 섞은 격자 **하나**에서 모든 줄을 뽑는다(`probfloor` 가 센다).

    🔴 이 함수가 따로 있는 까닭은 **C1** 이다 — `run` 안에는 시장 글자를 두지
       않는다(C1 이 막는 것은 *"배당·시장 정보를 S3 가 읽는 것"* 이고, 이 함수는
       **우리 격자**에서 줄을 뽑는다).
    """
    from app.core import probfloor as _pf2
    return dict(_pf2.markets_of(dict(grid or {})))


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
           gaps: dict, mr, *, base, mul_a: float = 1.0, move0: float = 0.0
           ) -> tuple[dict, dict]:
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
        move = max(-cap, min(cap, beta * run)) + float(move0)
        # 🔴 **λ 식과 같은 꼴**이어야 한다 — 원정 배율을 빼면 합이 안 맞는다
        now = _sim.run(mean * mul * math.exp(move),
                       mean * mul_a * math.exp(-move))
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
    # 🔴 **λ 식과 같은 꼴** — 원정 배율도 건다(2026-10-12 2-b). ⚠️ 여기만 빠지면
    #    기여 분해의 합이 리그 평균 대비 변화와 **안 맞는다**(계약이 센다).
    from app import rules as _r2
    said_kind2 = _kind(ref, facts)
    mul_a2, _w = away_mul(home_share=_r2.goal_baseline(said_kind2).get(
        "home_share"), per_team=_r2.goal_share(said_kind2))
    out = _sim.run(mean * mul, mean * mul_a2)
    return {"home": out.home, "draw": out.draw, "away": out.away}
