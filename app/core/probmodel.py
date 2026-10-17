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


# 🔴 **`lambda_rules` 를 지웠다** — λ 배율(이동·피로)을 곱하던 함수다.
#    기대 득점(λ)을 지우자(사용자 지시 2026-10-17) 부르는 곳이 없어졌다(#2).
#    ⚠️ 설정 표 `config/variable_routing.yaml: lambda_rules` 는 **남는다** —
#       `flat_prob` 가 그 `by_var` 칸으로 변수 방향을 읽는다(같은 이름 다른 칸).


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
        # 🔴🔴 **수축은 ③ 에서 이미 했다**(`core/goalbase.shrink` · 한 곳) —
        #    여기서 다시 하지 않는다(두 번 수축하면 수가 또 틀린다).
        #    ⚠️ 운영 확률은 **얼린 M1** 이 내고 그것도 같은 칸을 읽는다 — 그래서
        #       칸을 고치는 것이 유일한 길이다(K0).
        return float(got) / 2.0, (f"두 팀 경기당 총골 {float(got):g}"
                                  + (f" · {box_std['match_total_why']}"
                                     if box_std.get("match_total_why")
                                     else ""))
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
    # 🔴🔴 **후보 ③**(지시 2026-10-14e · 기본 꺼짐) — a 끄기 · b 대칭식 ·
    #    c 수축 강화 · d 이월. ⚠️ 지금 식은 **반예측**이다(백필: 상위 20% 홈 승
    #    40.7% < 기준 43.4% · 시즌 초 −6.2%p · `tools/home_mul_audit.py`).
    from app.core import m1v2 as _c
    said_v = _c.which("home_mul")
    if said_v:
        return _c.team_home(said_v, games, league=league)
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


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **초기 확률은 1/3 균등** — 사용자 지시 2026-10-15
# ══════════════════════════════════════════════════════════════════
#
#  > 변수 넣기전 **초기 확률 33.3 프로로 동등**하게 해라 … 그외에는 아무 의미
#  > 없다
#
#  🔴 그래서 승무패는 **홈 1/3 · 무 1/3 · 원정 1/3** 에서 출발하고, **변수만**
#     그것을 움직인다. 리그 평균 총골·홈 이점·팀별 홈 효과는 승무패에 **안
#     쓴다**(그 재료는 λ·오버·스코어에만 남는다).
#  🔴 크기는 **새 수가 아니다** — 이동·피로·순위 동기에 사용자가 정한 **±5%** 를
#     확률 비로 쓴다(유리한 쪽 ×1.05 · 상대 ÷1.05 · 그 뒤 정규화).
#  ⚠️ 어느 변수가 어느 쪽을 밀었는지 **이름으로** 적는다(#3).


def flat_prob(varset, *, ref) -> tuple[dict, str]:
    """🔴 1/3 균등에서 변수만 움직인 승무패. `({home,draw,away}, 사유)`."""
    from app.core import routing as _rt
    box = dict(_rt.table().get("lambda_rules") or {})
    by = dict(box.get("by_var") or {})
    got = {"home": 1.0 / 3.0, "draw": 1.0 / 3.0, "away": 1.0 / 3.0}
    #: 🔴 쏠림을 세는 칸 — 어느 쪽을 몇 번 밀었나(무를 깎는 데 쓴다)
    net: dict = {"home": 0, "away": 0}
    if not by:
        return got, "⬜ 변수 보정표가 없다 — 1/3 균등 그대로"
    g_box, f_box = dict(by.get("goals") or {}), dict(by.get("favors") or {})
    g_types = {str(x) for x in (g_box.get("types") or [])}
    f_types = {str(x) for x in (f_box.get("types") or [])}
    from app.core import routing as _rt
    said: list[str] = []
    n_doc = 0
    #: 🔴 **맥락 전용이라 안 센 변수** 수(위 머리말 · #3 이름으로 남긴다)
    n_ctx = 0
    for one in list(getattr(varset, "rows", None) or []):
        kind = str(getattr(one, "type", "") or "")
        rid = str(getattr(one, "id", "") or "")
        fav = str(getattr(one, "favors", "") or "both")
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **기사는 세지 않는다** — 사용자 지시 2026-10-15
        # ══════════════════════════════════════════════════════════════
        #
        #  > 기사 **내용으로 판단**을 해야지 기사 **횟수로 하는거는 바보같은
        #  > 짓**이다 … 추출수가 아니다
        #
        #  ⚠️ 실사고(노리치): 같은 사실(18위·승점 삭감)이 `R1~R7` 다섯 변수로
        #     쪼개져 **다섯 표**가 됐고 승무패가 뒤집혔다(원정 40.1% → 홈 35.5%).
        #  🔴 기사 변수는 **전략 전문가(LLM)가 내용으로 읽어** 부등호 하나로
        #     정리한다 — 그 산출(`SL*`)만 센다.
        if bool(getattr(one, "from_doc", False)):
            n_doc += 1
            continue
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **확률 자리에 배치된 변수만 센다** — 사용자 지시 2026-10-16
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 실사고 2026-10-16(PSIM vs PSM 검수): ⑩ 이 `S01-away` 를
        #     **맥락 전용**(`자리 ['hypo']`)으로 내렸는데 ⑮ 유도에는
        #     `[S01-away] home ×1.05` 가 찍혔다 — **표를 던졌다**.
        #     🔴 이 자리가 `varset.rows` 를 **전부** 훑고 `from_doc` 만
        #        걸렀기 때문이다. 그래서 어제 넣은 **안전장치**(두 경로 대조·
        #        말이 되나·누설)와 `s5_verify` 의 *"맥락 전용으로 내린다"* 가
        #        **확률 경로에서는 지켜지지 않았다**(표본 부족 변수도 같다).
        #  🔴 배치 규율 그대로다 — *"확률에 닿는 길은 축(또는 λ 상수)뿐"*
        #     (`core/routing` 머리말). 자리가 그 둘이 아니면 **안 센다**.
        said_places = [str(x) for x in (getattr(one, "places", None) or [])]
        if bool(getattr(one, "context_only", False)):
            n_ctx += 1
            continue
        if not any(x in (*_rt.AXES, _rt.CONST) for x in said_places):
            n_ctx += 1
            continue
        goals = str(getattr(one, "goals", "") or "none")
        key = str(getattr(one, "subject", "") or "")
        side = ("home" if key == str(getattr(ref, "home", "") or "")
                else "away" if key == str(getattr(ref, "away", "") or "")
                else "")
        # 🔴 **승패를 미는 칸은 `favors` 다** — `goals` 는 총골 이야기다.
        #    ⚠️ `goals` 만 있고 `favors` 가 없는 변수(폼 S01 처럼)는 **그 팀이
        #       많이 넣는다/적게 넣는다** 이므로 그 팀 쪽으로 센다.
        want = ""
        why = ""
        if kind in f_types and fav in ("home", "away"):
            want, why = fav, "favors"
        elif side and kind in g_types and goals in ("up", "down"):
            want = side if goals == "up" else (
                "away" if side == "home" else "home")
            why = f"goals {goals}"
        if not want:
            continue
        mul = float(f_box.get("mul") or 1.05)
        other = "away" if want == "home" else "home"
        got[want] *= mul
        got[other] /= mul
        said.append(f"[{rid}] {want} ×{mul:g}({why})")
        net[want] = net.get(want, 0) + 1
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **쏠리면 무를 깎는다** — 사용자 결정 2026-10-15(2번)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 홈쪽이 올라가면 상대쪽은 내려가는거여야 하지 않냐 → **2번으로 해라**
    #    (홈·원정 차가 커지면 **무를 깎는다**)
    #
    #  🔴 크기는 **새 수가 아니다** — 변수 하나가 쓰는 그 ±5% 를 쓴다.
    #  🔴 세는 것은 **순 단계수**다 — 홈 밀기 수 − 원정 밀기 수. 그래서
    #     **상쇄되면 무는 그대로**다(홈1·원정1 → 균등 그대로).
    #  ⚠️ 변수 수가 아니라 **쏠림**을 본다 — 양쪽에 똑같이 많아도 무는 안 깎인다.
    if n_ctx:
        said.append(f"⚠️ 맥락 전용 변수 {n_ctx}개는 **안 셌다**(확률 자리에 "
                    f"배치되지 않았다 — 안전장치·표본 부족)")
    if n_doc:
        said.append(f"⚠️ 기사 변수 {n_doc}개는 **안 셌다**(내용 판단은 전략 "
                    "전문가가 한다 · 개수로 세지 않는다)")
    lean = abs(int(net.get("home", 0)) - int(net.get("away", 0)))
    if lean:
        mul = float(f_box.get("mul") or 1.05)
        got["draw"] /= mul ** lean
        said.append(f"무 ÷{mul:g}^{lean}(쏠림 {lean}단계)")
    total = sum(got.values()) or 1.0
    got = {k: v / total for k, v in got.items()}
    head = "🎯 **초기 1/3 균등 + 변수**(사용자 지시 2026-10-15)"
    if not said:
        return got, head + " — ⬜ 민 변수가 없다(균등 그대로)"
    return got, (head + " — " + " · ".join(said)
                 + f" → 홈 {got['home']:.1%} · 무 {got['draw']:.1%} "
                   f"· 원정 {got['away']:.1%}")


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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **상성을 삭제했다** — 사용자 결정 2026-10-15
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 그냥 **상성 삭제**하라고
    #
    #  🔴 축 종합·쪽값이 λ 를 **움직이지 않는다**(이동 0 고정). 축 값 자체는
    #     계속 센다 — 카드가 **근거로** 적는다(표시·검증).
    #  ⚠️ 그래서 두 팀 전력·폼 차가 확률에 **안 들어간다** — 남는 재료는 리그
    #     실측 총골 · 홈 이점 · 팀별 홈 효과 · λ 규칙(IR13·IR11·IR14)뿐이다
    #     (실측 2026-10-15: 여섯 경기 홈 확률 퍼짐 7.7% → 6.0%).
    move = {"home": 0.0, "away": 0.0}
    tilt = 0.0
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **상성을 뺀다** — 사용자 결정 2026-10-15
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 상성을 빼라 … 빼고 노리치 경기가 어떻게 바뀄는지 확인해라
    #
    #  🔴 빼면 λ 는 **리그 실측 총골 + 홈 이점 + 팀별 홈 효과 + λ 규칙**만으로
    #     선다 — 두 팀의 **전력·폼 차가 확률에 안 들어간다**(실측 2026-10-15:
    #     여섯 경기 홈 확률 퍼짐 7.7% → 6.0%).
    #  ⚠️ 축 값은 **그대로 센다**(카드가 근거로 적는다) — λ 에만 안 넣는다.
    #  🔴 되돌릴 수 있게 플래그다(`m1v2.flags.matchup_off`).
    said_off = ""
    from app.core import m1v2 as _c
    if _c.on("matchup_off"):
        said_off = (f"🔴 **상성 뺐다**(`matchup_off`) — 종전 이동 홈 "
                    f"{move['home']:+.3f} · 원정 {move['away']:+.3f} 를 **0 으로** "
                    "둔다(축 값은 카드에 그대로 적는다)")
        move = {k: 0.0 for k in move}
        _note(state, f"S3 {said_off}")
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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **기대 득점(λ)을 지웠다 — 옛 엔진을 부르지 않는다**
    # ══════════════════════════════════════════════════════════════════
    #
    #  사용자 지시 2026-10-17: *"λ 경로(M1 얼린 옛 경로 · legacy-4axis) 로
    #  찍힙니다 → **다 지워라 · 필요없다**"* · *"**기대득점 지워라**"*
    #
    #  ⚠️ 실측 2026-10-17(가시마 라이브): `app.core.legacy.old_engine` 이
    #     `[S3] 두 팀 경기당 총골 3.444 → 한 팀 평균 1.722 · … λ 이동 …` 을
    #     **계속 찍고 있었다**. 🔴 그런데 그가 낸 것은 **전부 버려진다** —
    #     승무패는 `flat_prob`(1/3 균등 + 변수)이 **덮고**, λ·오버·스코어는
    #     그 아래에서 **비운다**(사용자 결정 2026-10-15 3번).
    #  🔴 그래서 **부르지 않는다** — 버릴 수를 계산하느라 시간을 쓰지 않는다.
    #     ⚠️ 얼린 파일(`legacy/old_engine` · 계약 K0)은 **지우지 않았다** —
    #        백필·비교 도구가 그 모형을 읽는다(운영이 안 부를 뿐이다).
    said_m1 = None
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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **옛 M1 블록을 지웠다**(180줄) — 사용자 지시 2026-10-17
    # ══════════════════════════════════════════════════════════════════
    #
    #  > λ 경로 **다 지워라 · 필요없다** · **기대득점 지워라** ·
    #  > 오늘 로직에서 불필요한 **옛 코드는 더이상 필요하지 않다**
    #
    #  🔴 그 블록이 하던 일을 **실측으로 세어** 효과가 0 인 것만 걷었다:
    #       · λ 보정(이동·피로)   → **0**(바로 아래에서 λ 를 비운다)
    #       · 무승부 보정(ρ)      → **0**(보정한 승무패를 `flat_prob` 가 덮는다)
    #       · 앙상블(E1 격자 혼합) → **0**(혼합한 격자를 비운다)
    #       · 스코어·오버          → **0**(비운다)
    #     ⚠️ 그런데 **승무패(`flat_prob`)도 그 블록 안에 있었다** — 블록만
    #        지우면 승무패가 통째로 사라진다(내가 한 번 그렇게 했다). 🔴 그래서
    #        승무패와 λ 비우기는 **밖으로 꺼내** 늘 돌게 둔다.
    #  ⚠️ `legacy/old_engine`·`drawfix`·`ensemble` **모듈은 안 지웠다** —
    #     백필·비교 도구가 그 모형을 읽는다(운영이 안 부를 뿐이다).
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **승무패 = 초기 1/3 균등 + 변수** — 사용자 지시 2026-10-15
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 변수 넣기전 초기 확률 **33.3 프로로 동등**하게 해라 · 그외에는
    #  > 아무 의미 없다
    said_flat, why_flat = flat_prob(varset, ref=ref)
    got.home = round(float(said_flat["home"]), 6)
    got.draw = round(float(said_flat["draw"]), 6)
    got.away = round(float(said_flat["away"]), 6)
    _note(state, f"S3 {why_flat}")
    # 🔴🔴 **기대 득점(λ)·오버·스코어는 없다**(사용자 결정 2026-10-15 3번 ·
    #    2026-10-17 *"기대득점 지워라"*) — 카드에 **⬜ 로 남는다**(#3).
    got.lam, got.over, got.scores = {}, {}, {}
    got.xg, got.share, got.share_refs = {}, {}, {}
    got.why = (f"🔴🔴 **승무패 = 초기 1/3 균등 + 변수**(사용자 지시 "
               f"2026-10-15) — {why_flat} · 🔴 **기대 득점(λ)·오버·스코어는 "
               f"없다**(2026-10-17 — 승무패는 λ 를 안 본다)")
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
