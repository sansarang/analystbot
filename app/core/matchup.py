"""🔴🔴 **S2 — 상성 판정**. 상성 중심 확률 엔진 지시서(2026-10-10 여섯째) S2.

> 각 축은 **홈 관점·원정 관점 값, 우위 쪽, 강도, 근거 변수 id** 를 낸다.
>  축0 오늘 XI 전력 · 축1 보정 폼 · 축2 전술 상성 · 축3 골 내용 상성
> 종합 판정: 축별 우위·강도를 **적합된 비중**으로 합쳐 {상성 우위 팀, 강도}.

🔴 **수는 이미 있는 모듈이 센다**(사본 금지):
   축1 `app/core/form.py` · 축2 `app/core/style.py` · 축3 `app/core/goals.py`
   축0 은 여기서 센다(선수 가치·결장/복귀·**호흡**) — 다른 곳에 없다.
🔴 입력은 **FactBundle + VariableSet 의 ① 배치 변수**뿐이다(지시서 S2 머리줄).
   ⚠️ Elo·동기·일정·감독 발언·맞대결·시장은 **들어오지 않는다**(C1 이 센다).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

CONF = "config/matchup_model.yaml"
#: 🔴 강도 글자(지시서 종합 판정) — `강`·`중`·`약`·`없음`
STRONG, MID, WEAK, NONE = "강", "중", "약", "없음"
#: 🔴 카드가 붙이는 표시 — 적합 전 계수를 쓸 때(C10)
PROVISIONAL = "🔴 임시"


def table() -> dict:
    """🔴 축 비중·임시 계수 — `config/matchup_model.yaml` 하나가 든다."""
    from app import rules
    return dict(rules._load(CONF) or {})


@dataclass
class Axis:
    """🔴 축 하나 — **두 관점 값·우위·강도·근거 변수**."""

    name: str = ""
    home: float | None = None
    away: float | None = None
    edge: str = ""              # `home`·`away`·빈 글자(가리지 못함)
    strength: str = NONE
    refs: list = field(default_factory=list)
    why: str = ""
    #: 🔴 표준화한 차(홈 − 원정) — S3 가 λ 를 세는 재료다
    gap: float | None = None

    def ok(self) -> bool:
        return self.home is not None and self.away is not None


@dataclass
class MatchupReport:
    """🔴 S2 산출 — 축 넷 + 전략 판정 + 종합 판정."""

    axes: dict = field(default_factory=dict)
    #: 🔴 축2 가 든 것 — 발동 규칙·꺼진 무기·후반 무기·전략 판정
    fired: list = field(default_factory=list)
    off_weapons: dict = field(default_factory=dict)
    late_weapons: dict = field(default_factory=dict)
    strategy: object = None
    #: 🔴 종합 — `{"edge": "home"|"away"|"", "strength": 강·중·약·없음, "why": …}`
    verdict: dict = field(default_factory=dict)
    #: 🔴 r 가중(선수단 교체) — `{"home": r, "away": r}`. 1.0 이면 안 깎았다
    r: dict = field(default_factory=dict)
    why: str = ""

    def axis(self, name: str) -> Axis:
        return self.axes.get(name) or Axis(name=name)

    def gaps(self) -> dict:
        """🔴 S3 가 쓰는 **축별 표준화 차**(없는 축은 0)."""
        return {k: (float(v.gap) if v.gap is not None else 0.0)
                for k, v in self.axes.items()}

    def edge_of(self) -> str:
        return str(self.verdict.get("edge") or "")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 축0 — **오늘 XI 전력**
# ══════════════════════════════════════════════════════════════════
#
#  > 선수 가치 합(오늘 XI vs 상대 오늘 XI, **로그**), 결장·복귀 변수 반영(빠진·
#  > 들어온 선수 가치), **호흡**(오늘 선발끼리 함께 선발로 뛴 경기 수 평균).

def axis0(ref, facts, varset, *, r: dict | None = None) -> Axis:
    """🔴 축0 — 전력·호흡. ⚠️ 가치 자료가 없으면 **두 값이 `None`**(#3)."""
    from app.core import routing
    got = Axis(name="axis0")
    val = dict(getattr(facts, "player_value", None) or {})
    rows = {side: _xi_names(facts, str(getattr(ref, side)))
            for side in ("home", "away")}
    if not val or not all(rows.values()):
        got.why = ("🔴 선수 가치나 오늘 XI 가 없다 — 축0 을 **안 센다**"
                   f"(가치 {len(val)}명 · XI {{{', '.join(f'{k} {len(v)}' for k, v in rows.items())}}})")
        return got
    sums = {}
    for side, names in rows.items():
        hit = [float(val[nm]) for nm in names if nm in val]
        sums[side] = (math.log1p(sum(hit)) if hit else None)
    if sums.get("home") is None or sums.get("away") is None:
        got.why = "🔴 한쪽 XI 의 가치를 하나도 못 찾았다 — 축0 을 안 센다"
        return got
    # 🔴 **호흡** — 오늘 선발끼리 함께 선발로 뛴 경기 수(평균). 교체된 팀은 낮다.
    fit = {side: _together(facts, str(getattr(ref, side)), rows[side])
           for side in ("home", "away")}
    box = dict(table().get("axis0") or {})
    w_fit = float(box.get("together_weight") or 0.0)
    got.home = round(float(sums["home"]) + w_fit * float(fit["home"]), 4)
    got.away = round(float(sums["away"]) + w_fit * float(fit["away"]), 4)
    got.refs = [one.id for one in varset.of(routing.AXES[0])] if varset else []
    got.why = (f"선수 가치 로그합 홈 {sums['home']:.3f} · 원정 "
               f"{sums['away']:.3f} · 호흡(함께 선발 경기 평균) 홈 "
               f"{fit['home']:.2f} · 원정 {fit['away']:.2f}"
               f"(무게 {w_fit:g} · {PROVISIONAL})")
    return _settle(got, scale=float(box.get("scale") or 1.0))


def _xi_names(facts, key: str) -> list:
    xi = (getattr(facts, "xi", None) or {}).get(key)
    return [str(x) for x in (getattr(xi, "players", None) or [])]


def _together(facts, key: str, names: list) -> float:
    """🔴 **호흡** — 오늘 선발이 과거 경기에 함께 선발로 나온 **평균 수**.

    🔴 재료는 `facts.past_xi` 다(새 통신 0건). ⚠️ 과거 XI 가 없으면 **0.0** 이고
       그 사실은 축0 사유에 수로 남는다(0 이 "호흡 없음"이라는 뜻이다).
    """
    from app.core import discover as _d
    rows = list((getattr(facts, "past_xi", None) or {}).get(key) or [])
    if not rows or not names:
        return 0.0
    want = {_d.name_key(x) for x in names}
    hit = 0
    for one in rows:
        said = {_d.name_key(x) for x in (getattr(one, "players", None) or [])}
        hit += len(want & said)
    return round(hit / max(1, len(rows) * len(want)) * len(want), 3)


# ══════════════════════════════════════════════════════════════════
# 🔴 강도·우위 — 축마다 같은 규칙으로
# ══════════════════════════════════════════════════════════════════

def _settle(got: Axis, *, scale: float) -> Axis:
    """🔴 두 값 → **표준화 차·우위·강도**. ⚠️ 문턱은 표가 든다."""
    box = dict(table().get("strength") or {})
    if not got.ok():
        return got
    gap = (float(got.home) - float(got.away)) / (scale or 1.0)
    got.gap = round(gap, 4)
    mid = float(box.get("mid") or 0.3)
    strong = float(box.get("strong") or 0.8)
    weak = float(box.get("weak") or 0.1)
    size = abs(gap)
    got.strength = (STRONG if size >= strong else MID if size >= mid
                    else WEAK if size >= weak else NONE)
    got.edge = "" if got.strength == NONE else ("home" if gap > 0 else "away")
    return got


def combine(axes: dict) -> dict:
    """🔴🔴 **종합 판정** — 축별 차를 표의 비중으로 합친다.

    > 축별 우위·강도를 **적합된 비중**으로 합쳐 {상성 우위 팀, 강도}.
    ⚠️ 비중은 **적합 전이면 임시값**이고 그 사실이 사유에 남는다(C10).
    """
    box = dict(table().get("weights") or {})
    fit = dict(table().get("fit") or {})
    total = 0.0
    said: list[str] = []
    for name, one in axes.items():
        if one.gap is None:
            said.append(f"{name} ⬜")
            continue
        w = float(box.get(name) or 0.0)
        total += w * float(one.gap)
        said.append(f"{name} {one.gap:+.2f}×{w:g}")
    got = Axis(name="종합", home=total, away=0.0)
    got = _settle(got, scale=1.0)
    return {"edge": got.edge, "strength": got.strength, "score": round(total, 4),
            "why": (" · ".join(said)
                    + (f" → 합 {total:+.3f} · {PROVISIONAL}"
                       if fit.get("provisional") else f" → 합 {total:+.3f}"))}


def r_of(varset, ref, *, turnover: dict | None = None) -> dict:
    """🔴🔴 **r 가중**(C8) — 선수단 교체 팀의 과거 경기를 얼마나 믿나.

    > squad_turnover: 과거 경기 가중 = **그 경기 선발 중 오늘 명단에 있는 비율 r**.

    🔴 여기서는 **팀마다 하나의 r** 을 센다(축1·축3 이 그것으로 과거를 깎는다).
       ⚠️ 경기별 r 은 축1 이 자기 경기 목록으로 센다 — 이 수는 **그 팀이 교체
       상태인가**를 말하는 요약이다(교체 아니면 1.0).
    """
    out = {"home": 1.0, "away": 1.0}
    # 🔴🔴 **깃발이 센 r 을 쓴다**(사용자 결정 2026-10-10 (a)): *"r 도 **오늘 경기
    #    명단 기준**으로 계산한다"*. ⚠️ 종전에는 표의 고정값(0.5)이었다 — 그것은
    #    §2 가 지운 *"고정 배율"* 과 같은 병이다.
    box_t = dict(turnover or {})
    for side in ("home", "away"):
        one = dict(box_t.get(side) or {})
        if one.get("on") and one.get("r") is not None:
            out[side] = float(one["r"])
    if any(v != 1.0 for v in out.values()) or varset is None:
        return out
    # ⚠️ 깃발 표가 없을 때만 변수로 떨어진다(표 기본값 · 그 사실이 사유에 남는다)
    for one in varset.of("axis1"):
        if str(one.type) != "squad_rotation":
            continue
        side = "home" if str(one.subject) == str(getattr(ref, "home", "")) \
            else "away"
        out[side] = float(dict(table().get("axis1") or {})
                          .get("turnover_r") or 0.5)
    return out


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 축1·축2·축3 — **이미 센 것을 축으로 담는다**(사본 금지)
# ══════════════════════════════════════════════════════════════════

def axis1(box: dict, varset, *, r: dict) -> Axis:
    """🔴 축1 — 보정 폼. 수는 `form.form_of` 가 이미 셌다.

    🔴 C8 — **선수단 교체 팀은 r 로 깎는다**(과거가 오늘 선수단의 기록이 아니다).
    """
    from app.core import routing
    got = Axis(name="axis1")
    form = dict(box.get("form") or {})
    vals = {side: (form[side].index() if form.get(side) else None)
            for side in ("home", "away")}
    if vals["home"] is None or vals["away"] is None:
        got.why = "🔴 보정 폼을 못 셌다 — 축1 을 안 센다"
        return got
    # 🔴 r 가중 — 교체 팀의 폼을 **0 쪽으로** 당긴다(그 기록이 오늘 팀의 것이 아니다)
    pulled = {side: float(vals[side]) * float(dict(r or {}).get(side, 1.0))
              for side in ("home", "away")}
    got.home, got.away = round(pulled["home"], 4), round(pulled["away"], 4)
    got.refs = [one.id for one in varset.of("axis1")] if varset else []
    said_r = " · ".join(f"{k} r={float(dict(r or {}).get(k, 1.0)):g}"
                        for k in ("home", "away"))
    got.why = (f"보정 득실차/경기 홈 {vals['home']} · 원정 {vals['away']}"
               f" → r 가중 {said_r}")
    return _settle(got, scale=float(dict(table().get("axis1") or {})
                                    .get("scale") or 1.0))


def axis2(box: dict, varset) -> Axis:
    """🔴 축2 — 전술 상성. 발동 규칙(T1~T6)과 **꺼진 무기**로 센다."""
    from app.core import routing
    got = Axis(name="axis2")
    conf = dict(table().get("axis2") or {})
    fired = [f for f in (box.get("fired2") or []) if not f.watch_only]
    offs = dict(box.get("off") or {})
    if not box.get("style"):
        got.why = "🔴 스타일 6축을 못 셌다 — 축2 를 안 센다"
        return got
    per = float(conf.get("per_rule") or 0.0)
    per_off = float(conf.get("per_off_weapon") or 0.0)
    # 🔴🔴 **발동 0건 + 꺼진 무기 0개면 "못 셌다"** 다(값 0 이 아니다 · #3).
    #    ⚠️ 실측 2026-10-10(K리그1 백필 123경기 · 라이브 김천–안양): 축2 가 **늘
    #       0.000** 이었다 — 스타일 여섯 축은 6/6 으로 재는데 T1~T6 의 문턱
    #       (`tactical_rules.yaml: matchup_gap` 0.25)을 넘은 축 차가 **한 번도**
    #       없었다. 🔴 그것을 `0.0` 으로 적으면 *"차이가 없다"* 로 읽히지만 실은
    #       *"규칙이 아무 말도 안 했다"* 다. 문턱을 감으로 낮추지 않는다(적합 전).
    if not fired and not any(offs.values()):
        from app.core import goals as _g
        got.why = ("🔴 **발동 0건** — T1~T6 의 문턱"
                   f"({float(dict(_g.table()).get('matchup_gap') or 0.25):g})을"
                   " 넘은 축 차가 없다(스타일 6축은 쟀다) · 문턱은 적합 전이다")
        return got
    val = {"home": 0.0, "away": 0.0}
    for f in fired:
        val[str(f.side)] = val.get(str(f.side), 0.0) + per
    for side, rows in offs.items():
        # 🔴 꺼진 무기는 **그 팀을 깎는다**(상대를 올리지 않는다)
        val[side] = val.get(side, 0.0) - per_off * len(list(rows or []))
    got.home, got.away = round(val["home"], 4), round(val["away"], 4)
    got.refs = [one.id for one in varset.of("axis2")] if varset else []
    got.why = (f"발동 {len(fired)}건(규칙당 {per:g}) · 꺼진 무기 "
               + " · ".join(f"{k} {len(list(v or []))}" for k, v in offs.items())
               + f"(하나당 −{per_off:g}) · {PROVISIONAL}")
    return _settle(got, scale=1.0)


def axis3(box: dict, varset, *, r: dict) -> Axis:
    """🔴 축3 — 골 내용. T9~T13 발동(관찰만은 빼고)으로 센다.

    🔴 C8 — 교체 팀의 골 프로필도 과거다 → r 로 깎는다.
    """
    got = Axis(name="axis3")
    conf = dict(table().get("axis3") or {})
    fired = [f for f in (box.get("fired") or []) if not f.watch_only]
    if not box.get("profile"):
        got.why = "🔴 골 프로필이 없다 — 축3 을 안 센다"
        return got
    per = float(conf.get("per_rule") or 0.0)
    val = {"home": 0.0, "away": 0.0}
    for f in fired:
        val[str(f.side)] = val.get(str(f.side), 0.0) + per
    for side in ("home", "away"):
        val[side] *= float(dict(r or {}).get(side, 1.0))
    got.home, got.away = round(val["home"], 4), round(val["away"], 4)
    got.refs = [one.id for one in varset.of("axis3")] if varset else []
    watch = [f.rule for f in (box.get("fired") or []) if f.watch_only]
    got.why = (f"발동 {len(fired)}건(규칙당 {per:g})"
               + (f" · 관찰만 {watch}(λ 에 안 들어간다 · C9)" if watch else "")
               + f" · {PROVISIONAL}")
    return _settle(got, scale=1.0)


def report(ref, facts, box: dict, varset, *, strategy=None,
           turnover: dict | None = None) -> MatchupReport:
    """🔴🔴 **S2 산출** — 축 넷 + 전략 판정 + 종합 판정.

    `box` 는 `s2e_matchup` 이 모은 재료다(폼·스타일·프로필·발동 규칙).
    🔴 **확률을 세지 않는다** — S3 가 `gaps()` 를 받아 λ 를 만든다.
    """
    r = r_of(varset, ref, turnover=turnover)
    axes = {"axis0": axis0(ref, facts, varset, r=r),
            "axis1": axis1(box, varset, r=r),
            "axis2": axis2(box, varset),
            "axis3": axis3(box, varset, r=r)}
    got = MatchupReport(
        axes=axes, fired=[*(box.get("fired2") or []), *(box.get("fired") or [])],
        off_weapons=dict(box.get("off") or {}),
        late_weapons=dict(box.get("late") or {}),
        strategy=strategy, r=r, verdict=combine(axes))
    got.why = (" · ".join(f"{k} {v.gap:+.2f}" if v.gap is not None
                          else f"{k} ⬜" for k, v in axes.items())
               + f" → 종합 {got.verdict.get('edge') or '가리지 못함'} "
               + f"{got.verdict.get('strength')}")
    logger.info("[S2] 상성 — %s", got.why)
    return got
