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
# ══════════════════════════════════════════════════════════════════════
# 🔴🔴 **상성·시뮬과 함께 지웠다** — 사용자 지시 2026-10-17
# ══════════════════════════════════════════════════════════════════════
#
#  > 상성이 왜 들어가 있냐?? · **상성 삭제해라** · **시뮬도 삭제해라**
#
#  🔴 아래 함수들은 λ(기대 득점)를 세우던 재료다 — 리그 평균·홈/원정 배율·
#     λ 기울기 이분법. 승무패가 `flat_prob`(1/3 균등 + 변수)로 바뀌고
#     λ·오버·스코어가 비워지면서 **부르는 곳이 0** 이 됐다(#2).
#  ⚠️ `app/core/sim.py`(몬테카를로) 모듈은 **안 지웠다** — `tools/` 의 백필·
#     비교 측정 도구들이 그 모형을 읽는다(운영이 안 부를 뿐이다).



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
# ══════════════════════════════════════════════════════════════════════
# 🔴🔴 **상성·시뮬과 함께 지웠다** — 사용자 지시 2026-10-17
# ══════════════════════════════════════════════════════════════════════
#
#  > 상성이 왜 들어가 있냐?? · **상성 삭제해라** · **시뮬도 삭제해라**
#
#  🔴 아래 함수들은 **상성 축(축0~축3)이 쓰던 부품**이다 — 스타일 6축·무기 표·
#     백분위·창 검사·공격 기여·중심화. 상성 단계를 지우자 **부르는 곳이 0**
#     이 됐다(`tests/test_wiring.py` 가 고아로 잡았다 · #2).



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


def _layers() -> dict:
    """🔴 두 층의 크기 표 — `lambda_rules.by_layer`(없으면 빈 표)."""
    from app.core import routing as _rt
    box = dict(_rt.table().get("lambda_rules") or {})
    return dict(box.get("by_layer") or {})


def _is_past(kind: str) -> bool:
    """🔴 그 유형이 **과거(경기력)** 인가 — 표가 든다(사본 금지)."""
    said = {str(x) for x in (_layers().get("past_types") or [])}
    return str(kind) in said


def _layer_mul(kind: str, f_box: dict) -> float:
    """🔴🔴 그 변수의 **크기** — 과거는 바탕, 오늘은 조정(지시 2026-10-18).

    ⚠️ 표가 없으면 종전 값(`favors.mul`)을 쓴다 — 조용히 1.0 으로 때우지 않는다.
    """
    box = _layers()
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **유형별 크기 덮어쓰기**(사용자 지시 2026-10-19 — *"1번해라"*)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-19 — `strength_gap`(순위표 누적 승점 `TB1`)이 **혼자
    #     ×1.05** 를 쓰며 오늘 층 네 표(가치·능력치·갈래·동기 · 각 ×1.03)를
    #     눌렀다:
    #       · 벨그라노 vs 리버 — 리버 쪽 네 표 ↔ `TB1` 홈 → 홈 34.0% 1위
    #         → 결과 **0-3 원정 완승**(리버 선발 가치는 **5.08배** 였다)
    #       · 즈볼러 vs 고 어헤드 — `TB1` 이 원정을 밀었다 → 결과 4-1 홈 승
    #  🔴 그래서 **그 유형만** 크기를 내린다. 층 이름(과거)은 그대로다 —
    #     자료는 과거이고 크기만 조정이다(글자가 사실을 바꾸지 않게).
    #  🔴 되돌리려면 표에서 그 줄을 지우면 된다(코드는 표가 없으면 종전대로).
    said_by_type = dict(box.get("mul_by_type") or {})
    if str(kind) in said_by_type:
        try:
            return float(said_by_type[str(kind)])
        except (TypeError, ValueError):
            pass
    key = "past" if _is_past(kind) else "today"
    try:
        return float(box[key])
    except (KeyError, TypeError, ValueError):
        return float(f_box.get("mul") or 1.05)


# ══════════════════════════════════════════════════════════════════════
# 🔴🔴 **기대 득점(λ)을 기준점으로 되살린다** — 사용자 지시 2026-10-20
# ══════════════════════════════════════════════════════════════════════
#
#  > **기대득점 넣어라**
#
#  🔴 **왜 — 1/3 균등이 홈 이점을 통째로 버렸다**(실측 2026-10-20 몬차 4-0):
#     `push_home 0` · `push_away 4` → 원정 39.7% 였고 실제는 **4-0 홈 완승**.
#     홈을 밀 수 있던 변수 셋 중 `S03`(홈 이점)은 **일부러 꺼져 있었다**
#     (`variable_routing.home_field.places = [hypo]` · 2026-10-18 M26 —
#     *"구조 상수가 오늘 층 한 표(×1.03)로 선다"* 는 올바른 까닭이었다).
#     ⚠️ 그런데 λ 쪽 통로도 2026-10-17 에 지워져서 **어디에도 안 들어갔다**.
#  🔴 그래서 홈 이점을 **변수 한 표가 아니라 기준점**으로 넣는다 — 그것이
#     2026-10-19 밤에 적은 그 진단이다(*"뿌리는 경기마다 다른 기준점이 없다"*).
#
#  🔴🔴 **새 계수를 만들지 않는다** — 실측 표 두 칸이 λ 둘을 그대로 준다:
#     `config/goal_baselines.yaml`
#        `goals_per_match` = 두 팀 총골 · `home_share` = **홈 팀** 평균 득점
#     → λ홈 = `home_share` · λ원정 = `goals_per_match` − `home_share`
#     보기(세리에A · 표본 810): 2.5185 · 1.3185 → λ 1.3185 ↔ 1.2000
#
#  ⚠️ **기본 포아송이다** — Dixon-Coles 의 `ρ`(저득점 무 보정)는 **안 넣는다**.
#     그 수는 적합이 필요한 계수인데 우리에겐 그 판이 없다(측정 없이 수를 짓지
#     않는다 · #4). 🔴 그래서 **저득점 경기의 무를 과소평가한다** — 그 사실을
#     사유에 적는다(#3 조용한 치우침 금지).
#  ⚠️ 표가 없으면 **1/3 균등 그대로**다(다른 대회에서 빌리지 않는다 · CC1).

#: 🔴 격자 상한 — 한 팀 득점을 이만큼까지 센다(그 위는 꼬리라 버린다)
GRID_MAX = 10


def _poisson(lam: float, k: int) -> float:
    """🔴 포아송 확률 — 계수가 아니라 **수식**이다(지어낸 수 0개)."""
    return math.exp(-lam) * lam ** k / math.factorial(k)


def base_lambda(ref, facts=None) -> tuple[dict | None, str]:
    """🔴🔴 **리그 실측 λ 로 만든 기준점** — `({home,draw,away}, 사유)`.

    🔴 못 만들면 `(None, 사유)` 다 — 그때는 부르는 쪽이 1/3 균등을 쓴다.
    """
    from app import rules
    kind = _kind(ref, facts)
    said = rules.goal_baseline(kind)
    mu = said.get("goals_per_match")
    share = said.get("home_share")
    if not isinstance(mu, (int, float)) or not isinstance(share, (int, float)):
        return None, (f"⬜ `{kind}` 득점 기준이 없다 — 1/3 균등에서 "
                      f"출발한다(다른 대회에서 빌리지 않는다 · CC1)")
    lam_h = float(share)
    lam_a = float(mu) - float(share)
    if lam_h <= 0 or lam_a <= 0:
        return None, (f"⬜ `{kind}` λ 가 꼴이 아니다"
                      f"(총골 {mu} · 홈 몫 {share}) — 1/3 균등")
    ph = [_poisson(lam_h, k) for k in range(GRID_MAX + 1)]
    pa = [_poisson(lam_a, k) for k in range(GRID_MAX + 1)]
    out = {"home": 0.0, "draw": 0.0, "away": 0.0}
    for i, x in enumerate(ph):
        for j, y in enumerate(pa):
            out["home" if i > j else ("away" if i < j else "draw")] += x * y
    total = sum(out.values()) or 1.0
    out = {k: v / total for k, v in out.items()}
    return out, (f"🎯 **기준점 = 리그 실측 λ**(`{kind}` · 표본 "
                 f"{said.get('n') or '?'}) — λ홈 **{lam_h:.3f}** ↔ λ원정 "
                 f"**{lam_a:.3f}**(총골 {float(mu):.3f} · 홈 몫 {lam_h:.3f}) "
                 f"→ 홈 {out['home']:.1%} · 무 {out['draw']:.1%} · 원정 "
                 f"{out['away']:.1%} · ⚠️ **기본 포아송**이라 저득점 경기의 "
                 f"무를 과소평가한다(Dixon-Coles `ρ` 는 적합 판이 없어 안 쓴다)")


def flat_prob(varset, *, ref, facts=None) -> tuple[dict, str]:
    """🔴 **리그 실측 λ 기준점**에서 변수만 움직인 승무패. `({home,draw,away}, 사유)`.

    ⚠️ 종전에는 **1/3 균등**에서 출발했다 — 그래서 경기가 달라도 쏠림 단계가
       같으면 **같은 수**가 나왔고(실측 2026-10-19: 14판에 네 값뿐), 홈 이점이
       통째로 빠졌다. 🔴 기준점이 바뀐 것뿐이고 **미는 방식은 그대로**다.
    """
    from app.core import routing as _rt
    box = dict(_rt.table().get("lambda_rules") or {})
    by = dict(box.get("by_var") or {})
    # 🔴 **기준점** — 리그 실측 λ 로 세운다(없으면 1/3 균등 · 위 `base_lambda`)
    #  🔴 `facts` 를 넘긴다 — 대회 열쇠는 **리그 번호**로 갈린다(`comp_kind`).
    #     ⚠️ 안 넘기면 `_kind` 가 빈 글자를 주고 득점 기준이 통째로 비었다
    #        (실측 2026-10-20: λ 를 넣었는데 확률이 **한 칸도 안 바뀌었다**).
    seed, why_base = base_lambda(ref, facts)
    got = dict(seed) if seed else {"home": 1.0 / 3.0, "draw": 1.0 / 3.0,
                                   "away": 1.0 / 3.0}
    #: 🔴 쏠림을 세는 칸 — 어느 쪽을 몇 번 밀었나(무를 깎는 데 쓴다)
    net: dict = {"home": 0, "away": 0}
    if not by:
        return got, f"{why_base} · ⬜ 변수 보정표가 없다 — 기준점 그대로"
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
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **과거는 바탕 · 오늘은 조정** — 사용자 지시 2026-10-18
        # ══════════════════════════════════════════════════════════════
        #
        #  > 지난경기를 가지고 **오늘 경기에 대입하는거다** .. **경기력**이고 ..
        #  > 오늘 경기력의 변수는 **오늘 라인업·날씨·피로도** 등이다
        #
        #  🔴 크기는 **표가 든다**(`lambda_rules.by_layer`) — 코드에 박지 않는다.
        #  ⚠️ 표가 없으면 종전처럼 `favors.mul` 하나를 쓴다(조용히 1.0 로
        #     때우지 않는다 · #3).
        mul = _layer_mul(kind, f_box)
        other = "away" if want == "home" else "home"
        got[want] *= mul
        got[other] /= mul
        said_l = "과거" if _is_past(kind) else "오늘"
        said.append(f"[{rid}] {want} ×{mul:g}({why} · {said_l})")
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
        # 🔴 무를 깎는 크기는 **기본값 하나**다(층과 무관) — 쏠림은 층이 아니라
        #    **방향**의 이야기다. ⚠️ 그 사실을 사유에 적는다.
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
    """🔴🔴 S3 — **승무패 = 초기 1/3 균등 + 변수**. 그것뿐이다.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **상성·시뮬을 지웠다** — 사용자 지시 2026-10-17
    ══════════════════════════════════════════════════════════════════

    > 상성이 왜 들어가 있냐?? · **상성 삭제해라** · **시뮬도 삭제해라**

    ⚠️ 종전에는 이 함수가 **237줄**을 돌았다: 리그 평균 → 홈 배율 → 축 차로
       λ 기울기 → 분 단위 몬테카를로 시뮬 → 축별 기여 분해 → 그림자 확률.
    🔴 **그 결과가 전부 버려지고 있었다.** 마지막 세 줄이 승무패를
       `flat_prob` 으로 덮고 `lam`·`over`·`scores` 를 비웠기 때문이다
       (2026-10-15 *"33.3 프로로 동등하게"* · 2026-10-17 *"기대득점 지워라"*).
       그래서 `eloratings.net` 통신과 시뮬을 돌리고 **버렸다**.
    🔴 지금 하는 일은 하나다 — `flat_prob(varset)`.
       ⚠️ `mr`·`edge`·`floor` 는 **안 읽는다**(인자는 부르는 쪽 때문에 남긴다 —
          카드·러너가 같은 꼴로 부른다). 그 사실을 사유에 적는다(#3).
    """
    got = ProbOut()
    said_flat, why_flat = flat_prob(varset, ref=ref, facts=facts)
    got.home = round(float(said_flat["home"]), 6)
    got.draw = round(float(said_flat["draw"]), 6)
    got.away = round(float(said_flat["away"]), 6)
    # 🔴 **기대 득점(λ)·오버·스코어는 없다** — 카드에 ⬜ 로 남는다(#3)
    got.lam, got.over, got.scores = {}, {}, {}
    got.xg, got.share, got.share_refs = {}, {}, {}
    got.shadow = {}
    got.why = (f"🔴🔴 **승무패 = 초기 1/3 균등 + 변수**(사용자 지시 "
               f"2026-10-15) — {why_flat} · 🔴 **기대 득점(λ)·오버·스코어는 "
               f"없다**(2026-10-17) · 🔴 **상성·시뮬은 지웠다**"
               f"(2026-10-17 — 결과가 버려지는 계산이었다)")
    _note(state, f"S3 {why_flat}")
    _note(state, f"S3 확률 — 홈 {got.home:.1%} · 무 {got.draw:.1%} · "
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
# ══════════════════════════════════════════════════════════════════════
# 🔴🔴 **`_share`·`league_base` 를 지웠다** — 사용자 지시 2026-10-17
# ══════════════════════════════════════════════════════════════════════
#
#  > 상성 삭제해라 · **시뮬도 삭제해라**
#
#  ⚠️ `_share` 는 **축별 기여 분해**(리그 평균 대비)였고 `run` 의 삭제된 몸통
#     하나만 불렀다 — 부르는 곳이 0 이 됐다(#2).
#  ⚠️ `league_base` 는 기여 분해의 **잠정 열**(리그 평균 확률)을 시뮬로 만들던
#     함수다. 기여(`share`)가 비었으니 그 열도 뜻이 없다.
#  🔴 둘 다 `app/core/sim.py`(몬테카를로)를 부르던 자리다.



def _note(state, said: str) -> None:
    if state is not None:
        state.note(said)
