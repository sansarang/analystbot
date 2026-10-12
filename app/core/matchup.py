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
from contextlib import contextmanager
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

CONF = "config/matchup_model.yaml"
#: 🔴 강도 글자(지시서 종합 판정) — `강`·`중`·`약`·`없음`
STRONG, MID, WEAK, NONE = "강", "중", "약", "없음"
#: 🔴 카드가 붙이는 표시 — 적합 전 계수를 쓸 때(C10)
PROVISIONAL = "🔴 임시"


#: 🔴🔴 **xG 판 패스 중인가** — 사용자 지시 2026-10-12 ③(계수를 섞지 않는다)
#
#  ⚠️ 전역 상태다. 🔴 그래서 **쓰는 범위를 못 박는다**: `xg_coeffs()` 안에서
#     도는 것은 `matchup.report`·`probmodel.run` **둘뿐이고 둘 다 동기 함수**다
#     (await 가 없다 → 다른 경기의 계산이 그 사이에 끼어들 수 없다).
#     계약 `test_v10_13_two_boards` 가 그 둘에 `await` 가 없음을 센다.
#  🔴 왜 인자로 안 넘기나: `table()` 을 부르는 자리가 **열 곳**이고(축0·축1·축2·
#     강도·비중·λ) 전부에 깃발을 끼우면 사본이 열 개가 된다(#1).
_XG_PASS = False


@contextmanager
def xg_coeffs():
    """🔴 이 블록 안에서 `table()` 은 **xG 판 계수**를 돌려준다."""
    global _XG_PASS
    said = _XG_PASS
    _XG_PASS = True
    try:
        yield
    finally:
        _XG_PASS = said


def table(*, xg: bool | None = None) -> dict:
    """🔴 축 비중·임시 계수 — `config/matchup_model.yaml` 하나가 든다.

    🔴🔴 **두 판의 계수는 섞지 않는다**(사용자 지시 2026-10-12 ③): `xg=True` 면
       `xg:` 블록의 `weights`·`lambda_model`·`fit` 이 **위 칸을 덮는다**.
    ⚠️ 덮지 않은 칸(축별 `scale`·강도 문턱 등)은 **공용**이다 — 그 칸은 단위
       변환이라 판에 따라 달라질 이유가 없다. 달라져야 할 칸이 생기면 `xg:` 에
       **그 칸을 적는 것**으로 갈린다(코드를 바꾸지 않는다).
    """
    from app import rules
    got = dict(rules._load(CONF) or {})
    if not (_XG_PASS if xg is None else xg):
        return got
    said = dict(got.get("xg") or {})
    for key in ("weights", "lambda_model", "fit"):
        if said.get(key) is not None:
            got[key] = said[key]
    return got


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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **F3 — 공격 특징·수비 특징을 쪽별로**(지시서 2026-10-11)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > log λ홈 = … + Σ_축 β_축 ·(**홈 공격**_축 − **원정 수비**_축)
    #  > log λ원정 = … + Σ_축 β_축 ·(**원정 공격**_축 − **홈 수비**_축)
    #  > 축 종합 숫자 **하나로 두 λ 를 만들지 않는다**.
    #
    #  ⚠️ 공격·수비를 **가를 자료가 없는 축**은 그 팀의 값 하나를 둘 다로 쓴다
    #     (그러면 `홈공격 − 원정수비 = gap` 이라 종전과 **같은 수**다). 🔴 그
    #     사실을 `split` 이 들고 `why` 가 적는다 — 가른 척하지 않는다(#4).
    att: dict = field(default_factory=dict)
    dfn: dict = field(default_factory=dict)
    #: 🔴 공격·수비를 **실제로 갈랐나**(거짓이면 값 하나를 둘 다로 썼다)
    split: bool = False

    def ok(self) -> bool:
        return self.home is not None and self.away is not None

    def sides(self) -> dict:
        """🔴 F3 — `{"att": {home, away}, "dfn": {home, away}}`.

        🔴 안 갈린 축은 **그 팀의 값**을 둘 다로 쓴다(= 종전과 같은 수).
        """
        base = {"home": self.home, "away": self.away}
        return {"att": dict(self.att or base), "dfn": dict(self.dfn or base)}


@dataclass
class MatchupReport:
    """🔴 S2 산출 — 축 넷 + 전략 판정 + 종합 판정."""

    #: 🔴 F1/R1 — 그 판정이 **어떤 XI 로** 나왔나(`confirmed`·`predicted`·`none`)
    xi_state: str = ""

    axes: dict = field(default_factory=dict)
    #: 🔴 축2 가 든 것 — 발동 규칙·꺼진 무기·후반 무기·전략 판정
    fired: list = field(default_factory=list)
    off_weapons: dict = field(default_factory=dict)
    #: 🔴 #3 — **왜 그만큼 꺼졌나**(평소 XI 수·오늘 빠짐·비중·문턱)
    off_why: dict = field(default_factory=dict)
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

#: 🔴🔴 D — **빠진 주전**이 축0 을 내리는 크기(비중 1.0 당). ⚠️ **임시값**이다.
#
#  > 결장을 λ 에 닿게 한다 · **결장선수가 핵심선수인지 확인하고** 닿게 해라.
#  >   — 사용자 지시 2026-10-11
#
#  ⚠️ 실측 2026-10-11: 카드가 *"라인업 보정 -0.3% — 확률은 **안 움직였다**(환산
#     계수 없음)"* 라고 적었다. 핵심 공격수가 빠져도 λ 가 그대로였다 — 결장이
#     닿는 길이 **선수 가치 로그합** 하나뿐이고 그 차가 작아서다.
#  🔴 축0 은 지시서가 *"오늘 XI 전력: **빠진 선수 가치**"* 로 정한 자리다 — 그래서
#     새 경로를 만들지 않고 **이 축 안에서** 센다(C7: 확률에 닿는 길은 상성 축뿐).
MISS_W = 2.0
#: 🔴 한 팀에서 깎는 **상한**(여러 명이 빠져도 팀을 지우지 않는다)
MISS_CAP = 1.0
#: 🔴 "핵심"의 문턱 ① — 그 팀 공격 기여(득점+도움)의 이 몫 이상이면 핵심이다
#   ⚠️ 수는 `style.OFF_SMALL`(무기 꺼짐 문턱) 하나를 쓴다 — 사본 금지.
KEY_SHARE_SRC = "style.OFF_SMALL"


def key_share() -> float:
    """🔴 핵심 문턱 — `style.OFF_SMALL` 하나가 든다(사본 금지)."""
    from app.core import style as _st
    return float(_st.OFF_SMALL)


def miss_move(share: float) -> float:
    """🔴 D — 빠진 주전 비중 → **축0 이동**(음수). 상한 `MISS_CAP`."""
    got = MISS_W * max(0.0, float(share or 0.0))
    return -round(min(got, MISS_CAP), 4)


def key_miss(*, shares: dict, keys: set, table: int) -> tuple[float, str]:
    """🔴🔴 D — **핵심 선수만** 센다. `(비중 합, 사유)`.

    `shares` — `{id: 그 팀 공격 기여 비중}`(오늘 빠진 주전들)
    `keys`   — 리그 페이지가 꼽은 **핵심 선수** id 들(`strategy.key_state`)
    `table`  — 기여표에 수가 있는 선수 수(0 이면 **못 쟀다**)

    🔴 핵심의 뜻 둘(하나면 된다): ① 비중 ≥ `key_share()` · ② `keys` 에 있다.
    ⚠️ 기여표가 비면(0명) **0 이고 그 사실을 적는다** — 0 으로 보지 않는다(#3).
    """
    if not int(table or 0):
        return 0.0, "🔴 공격 기여표가 비었다 — 빠진 주전의 무게를 **못 쟀다**"
    want = key_share()
    said: list[str] = []
    got = 0.0
    for ident, share in dict(shares or {}).items():
        val = float(share or 0.0)
        is_key = ident in set(keys or ())
        if val >= want:
            got += val
            said.append(f"`{ident}` 비중 {val:.0%}(≥{want:.0%})")
        elif is_key:
            got += val
            said.append(f"`{ident}` **핵심 선수**(비중 {val:.0%})")
    if not said:
        return 0.0, (f"빠진 주전이 핵심이 아니다(비중 <{want:.0%} · 리그 핵심 "
                     f"목록에도 없다) — 축0 을 안 움직인다")
    return round(got, 4), " · ".join(said)


def axis0(ref, facts, varset, *, r: dict | None = None,
          miss_share: dict | None = None) -> Axis:
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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **가치 없는 선수를 0 으로 더하지 않는다**(사용자 지시 2026-10-12 1번)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 대체값 = 같은 리그·같은 포지션 **선발 선수 가치 중앙값**, 카드에
    #  > "대체값 — 누구" 🔴.
    #
    #  🔴 실측(ⓓ 감사 2026-10-12): 가와사키 `Pedro Romano` 가 가치 없음이라
    #     그 팀 합이 조용히 깎였다. 영입 직후·하위 리그 출신은 **늘** 그렇게 된다.
    #  ⚠️ 중앙값 표본은 **그 경기 양 팀 선발**이다(같은 리그 · as-of 정합 · L2).
    from app.core import playervalue as _pv
    pos_box = dict(getattr(facts, "player_pos", None) or {})
    said_rows = {side: [{"name": nm, "pos": str(pos_box.get(nm) or ""),
                         "value": val.get(nm)} for nm in names]
                 for side, names in rows.items()}
    pool = [*said_rows["home"], *said_rows["away"]]
    sums = {}
    fill_why: list[str] = []
    for side, names in rows.items():
        said_fill, why_fill = _pv.fill(said_rows[side], pool=pool)
        got_sum, n_got = _pv.log_sum(said_fill)
        sums[side] = got_sum
        if why_fill:
            fill_why.append(f"{side} {why_fill}")
        if n_got and n_got < len(names):
            fill_why.append(f"{side} ⚠️ 가치 {n_got}/{len(names)}명")
    if sums.get("home") is None or sums.get("away") is None:
        got.why = "🔴 한쪽 XI 의 가치를 하나도 못 찾았다 — 축0 을 안 센다"
        return got
    # 🔴 **호흡** — 오늘 선발끼리 함께 선발로 뛴 경기 수(평균). 교체된 팀은 낮다.
    fit = {side: _together(facts, str(getattr(ref, side)), rows[side])
           for side in ("home", "away")}
    box = dict(table().get("axis0") or {})
    w_fit = float(box.get("together_weight") or 0.0)
    # 🔴🔴 D — **빠진 주전(핵심)**이 그 팀 축0 을 내린다
    miss = {side: float(dict(miss_share or {}).get(side) or 0.0)
            for side in ("home", "away")}
    got.home = round(float(sums["home"]) + w_fit * float(fit["home"])
                     + miss_move(miss["home"]), 4)
    got.away = round(float(sums["away"]) + w_fit * float(fit["away"])
                     + miss_move(miss["away"]), 4)
    got.refs = [one.id for one in varset.of(routing.AXES[0])] if varset else []
    # 🔴 1번 — **대체값을 쓴 사실을 카드가 적는다**(누구인지까지)
    got.why = ((" · ".join(fill_why) + " · " if fill_why else "")
               + f"선수 가치 로그합 홈 {sums['home']:.3f} · 원정 "
               f"{sums['away']:.3f} · 호흡(함께 선발 경기 평균) 홈 "
               f"{fit['home']:.2f} · 원정 {fit['away']:.2f}"
               f"(무게 {w_fit:g} · {PROVISIONAL})"
               # 🔴 D — **빠진 주전**을 적는다(조용히 깎지 않는다 · #3)
               + (f" · 빠진 주전 비중 홈 {miss['home']:.0%} → "
                  f"{miss_move(miss['home']):+.3f} · 원정 "
                  f"{miss['away']:.0%} → {miss_move(miss['away']):+.3f}"
                  f"(무게 {MISS_W:g} · 상한 {MISS_CAP:g} · {PROVISIONAL})"
                  if any(miss.values()) else " · 빠진 주전 없다(또는 핵심 아니다)"))
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
    from app.core import form as _form
    from app.core import routing
    got = Axis(name="axis1")
    form = dict(box.get("form") or {})
    vals = {side: (form[side].index() if form.get(side) else None)
            for side in ("home", "away")}
    if vals["home"] is None or vals["away"] is None:
        got.why = "🔴 보정 폼을 못 셌다 — 축1 을 안 센다"
        return got
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **창이 어긋나면 축1 을 안 센다**(사용자 지시 2026-10-11 ①)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 계약: 최근 n경기 합 ≤ 최근 m경기 합(n<m, 득·실 각각).
    #  > 어기면 **축1 미계산 + 운영자 알림**.
    #
    #  🔴 알림은 `s2e_matchup` 이 `state.note` 로 적고, 이 함수는 **수를 안 낸다** —
    #     틀린 수가 λ 로 가는 길을 여기서 끊는다(조용히 쓰지 않는다 · #3).
    bad = dict(box.get("window_bad") or {})
    if any(bad.values()):
        got.why = ("🔴 **경기 목록의 두 창이 어긋났다 — 축1 미계산** · "
                   + " · ".join(f"{k} {v}" for k, v in bad.items() if v))
        return got
    # 🔴 r 가중 — 교체 팀의 폼을 **0 쪽으로** 당긴다(그 기록이 오늘 팀의 것이 아니다)
    pulled = {side: float(vals[side]) * float(dict(r or {}).get(side, 1.0))
              for side in ("home", "away")}
    got.home, got.away = round(pulled["home"], 4), round(pulled["away"], 4)
    got.refs = [one.id for one in varset.of("axis1")] if varset else []
    said_r = " · ".join(f"{k} r={float(dict(r or {}).get(k, 1.0)):g}"
                        for k in ("home", "away"))
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **창과 산술을 적는다**(사용자 지시 2026-10-11 ②)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고 2026-10-11(LAFC): 카드의 **폼 블록은 최근 5경기**, 축1 은
    #     **최근 10경기**였다. 그래서 사용자가 *"밴쿠버 실점 2.0 인데 왜 앞서나"*
    #     를 물을 수밖에 없었다 — **두 수가 다른 창**이었고 카드는 그 말을 안 했다.
    #  🔴 그래서 축1 사유에 **경기 수·원본 득실·운 할인**을 적는다.
    said_box = []
    warn = ""
    raw = {}
    for side in ("home", "away"):
        one = form.get(side)
        if one is None or not getattr(one, "n", 0):
            continue
        n = int(one.n)
        raw[side] = (float(one.gf) - float(one.ga)) / n
        cut = getattr(one, "gf_after_luck", None)
        k = float(getattr(one, "luck_cut_goals", 0.0) or 0.0)
        # 🔴 ① — **두 창을 나란히 적는다**(한 목록에서 잘린 것임을 카드가 말한다)
        wins = dict(getattr(one, "windows", None) or {})
        if not wins:
            # 🔴 ① — 폼이 창을 안 들고 있으면 **경기 목록에서 직접 자른다**
            #    (창을 세는 함수는 `form.window_sums` 하나다 · 사본 금지)
            rows = list(dict(box.get("games") or {}).get(side) or [])
            wins = {str(w): _form.window_sums(rows, w)
                    for w in _form.WINDOWS} if rows else {}
        said_win = " · ".join(
            f"최근 {int(w['n'])}경기 득 {float(w['gf']):.0f}·실 "
            f"{float(w['ga']):.0f}"
            for w in (wins.get(str(x)) for x in _form.WINDOWS)
            if w and int(w.get("n") or 0))
        said_box.append(
            f"{side} " + (said_win or f"최근 {n}경기 득 {one.gf:.0f}·"
                          f"실 {one.ga:.0f}")
            + (f" · 운 요소 골 {k:g}개를 뺐다(득 {one.gf:.0f} → "
               f"{one.gf - k:.0f})" if k else "")
            + (f" · 보정·할인 뒤 득 {float(cut):.1f}" if cut is not None else "")
            + f" → 지수 {vals[side]}")
    # 🔴 **경고 줄** — 원본 득실이 더 나쁜 팀이 축1 에서 **크게 앞서면** 적는다
    if len(raw) == 2:
        lead = "home" if float(vals["home"]) > float(vals["away"]) else "away"
        other = "away" if lead == "home" else "home"
        if raw[lead] < raw[other] and abs(float(vals[lead]) - float(vals[other])) >= 0.3:
            warn = (f" · ⚠️ **원본 득실은 {other} 가 더 좋은데**({raw[other]:+.2f} "
                    f"vs {raw[lead]:+.2f}) 축1 은 {lead} 가 앞선다 — 보정·운 할인이"
                    f" 뒤집었다(까닭을 위 줄에서 본다)")
    got.why = (f"보정 득실차/경기 홈 {vals['home']} · 원정 {vals['away']}"
               f" → r 가중 {said_r}"
               + (" · " + " · ".join(said_box) if said_box else "") + warn)
    return _settle(got, scale=float(dict(table().get("axis1") or {})
                                    .get("scale") or 1.0))


#: 🔴🔴 B — **막는 쪽 축**(그 값이 높을수록 *상대 공격*을 막는다 → 내 우위다)
#
#  🔴 축 **이름 목록은 `style.axes()`(설정 표) 하나가 든다** — 여기 베껴 적지
#     않는다(#1 사본 금지). ⚠️ 실사고 2026-10-11: 여섯째를 `wide` 로 적었는데
#     실제 표는 **`setpiece`** 였다 — 그래서 축2 가 계속 ⬜ 였다.
#  ⚠️ `setpiece` 는 공격 쪽이다(세트플레이 xG 비중) — 막는 쪽은 둘뿐이다.
SIX_DEF: frozenset[str] = frozenset({"press", "low_block"})


def _six_gap(box: dict, *, per: float) -> float | None:
    """🔴🔴 B — **6축 차**(홈 − 원정)를 한 수로. 자료가 없으면 `None`.

    🔴 공격 축은 *내 값 − 상대 값*, 수비 축은 *상대 값 − 내 값*(막는 쪽이 높을수록
       내 우위다). 둘을 더해 축 수로 나누고 `per`(규칙당 크기)를 곱한다 — **새 계수를
       만들지 않는다**.
    ⚠️ 두 팀 중 한쪽이라도 그 축이 없으면 그 축은 **건너뛴다**(0 으로 보지 않는다).
    """
    rows = dict(box.get("style") or {})
    home, away = rows.get("home"), rows.get("away")
    if home is None or away is None:
        return None
    from app.core import style as _st
    a = dict(getattr(home, "axis", None) or {})
    b = dict(getattr(away, "axis", None) or {})
    got: list[float] = []
    for key in _st.axes():                     # 🔴 표가 이름을 준다(사본 금지)
        if key not in a or key not in b:
            continue                            # ⚠️ 한쪽이 없으면 건너뛴다(#3)
        if key in SIX_DEF:
            got.append(float(b[key]) - float(a[key]))
        else:
            got.append(float(a[key]) - float(b[key]))
    if not got:
        return None
    return round(per * sum(got) / len(got), 4)


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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 B **6축 차를 직접 쓴다**(사용자 지시 2026-10-11) — 상쇄를 막는다
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-11(가와사키): `T1 home`·`T1 away`·`T3 home`·`T3 away` 가 다
    #     터져 양 팀 값이 같아지고 **차 0.0** 이 됐다. 쇼난은 `발동 0건`으로 축2 가
    #     ⬜ 였다. 즉 비중 0.2 짜리 축이 **거의 늘 죽어 있었다**.
    #  🔴 규칙 발동은 **문턱을 넘은 것만** 센다 — 그래서 넘지 못한 차는 전부
    #     버려졌다. 스타일 6축의 raw 값은 **이미 있다**(`forward 0.47` vs `0.44`).
    #     그 **차**를 직접 가중합으로 쓰면 상쇄가 아니라 실제 우위가 남는다.
    #  🔴 계수를 새로 짓지 않는다 — 공격 축은 `+`, 수비 축은 **상대의 공격을
    #     막는 쪽**이므로 `-` 로 넣고 크기는 `per_rule` 하나를 쓴다(사본 금지).
    base = _six_gap(box, per=per)
    if not fired and not any(offs.values()) and base is None:
        from app.core import goals as _g
        got.why = ("🔴 **발동 0건 · 6축 차도 못 셌다** — T1~T6 의 문턱"
                   f"({float(dict(_g.table()).get('matchup_gap') or 0.25):g})을"
                   " 넘은 축 차가 없고 6축 raw 값도 비었다 · 문턱은 적합 전이다")
        return got
    val = {"home": 0.0, "away": 0.0}
    if base is not None:
        val["home"] += base
        said_six = f"6축 차 {base:+.4f}(공격 − 상대 수비 · 크기 {per:g})"
    else:
        said_six = "6축 차 ⬜ 못 셌다"
    for f in fired:
        val[str(f.side)] = val.get(str(f.side), 0.0) + per
    for side, rows in offs.items():
        # 🔴 꺼진 무기는 **그 팀을 깎는다**(상대를 올리지 않는다)
        val[side] = val.get(side, 0.0) - per_off * len(list(rows or []))
    got.home, got.away = round(val["home"], 4), round(val["away"], 4)
    got.refs = [one.id for one in varset.of("axis2")] if varset else []
    got.why = (f"{said_six} · 발동 {len(fired)}건(규칙당 {per:g}) · 꺼진 무기 "
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


def fingerprint(mr: object) -> str:
    """🔴🔴 **계약 R1** — 그 상성 판정의 지문. 같은 XI 면 같은 글자다.

    > 같은 경기에서 XI 가 예상→확정으로 바뀌면 `MatchupReport` 해시가 **다시
    > 계산된다**(같은 XI 면 같은 해시).  — 지시서 2026-10-11 F1

    🔴 축 네 개의 **차**와 종합·판정·XI 상태를 센다. ⚠️ 상수를 돌려주면 그
       순간 이 계약이 거짓말이 된다(돌연변이 시험이 그것을 본다).
    """
    import hashlib
    got = []
    for key in ("axis0", "axis1", "axis2", "axis3"):
        try:
            one = mr.axis(key)                              # type: ignore[attr-defined]
        except Exception:                                   # noqa: BLE001
            one = None
        gap = getattr(one, "gap", None)
        got.append("⬜" if gap is None else f"{float(gap):.4f}")
    got.append(f"{float(getattr(mr, 'total', 0.0) or 0.0):.4f}")
    said = dict(getattr(mr, "verdict", None) or {})
    got.append(f"{said.get('who')}/{said.get('strength')}")
    got.append(str(getattr(mr, "xi_state", "") or ""))
    return hashlib.sha1("|".join(got).encode()).hexdigest()[:12]


def report(ref, facts, box: dict, varset, *, strategy=None,
           turnover: dict | None = None) -> MatchupReport:
    """🔴🔴 **S2 산출** — 축 넷 + 전략 판정 + 종합 판정.

    `box` 는 `s2e_matchup` 이 모은 재료다(폼·스타일·프로필·발동 규칙).
    🔴 **확률을 세지 않는다** — S3 가 `gaps()` 를 받아 λ 를 만든다.
    """
    r = r_of(varset, ref, turnover=turnover)
    # 🔴 D — 빠진 주전(핵심) 비중을 축0 에 넘긴다(`s2e_matchup` 이 센 것)
    axes = {"axis0": axis0(ref, facts, varset, r=r,
                           miss_share=dict(box.get("miss_share") or {})),
            "axis1": axis1(box, varset, r=r),
            "axis2": axis2(box, varset),
            "axis3": axis3(box, varset, r=r)}
    got = MatchupReport(
        axes=axes, fired=[*(box.get("fired2") or []), *(box.get("fired") or [])],
        off_weapons=dict(box.get("off") or {}),
        off_why=dict(box.get("off_why") or {}),
        late_weapons=dict(box.get("late") or {}),
        strategy=strategy, r=r, verdict=combine(axes),
        # 🔴 F1/R1 — **어떤 XI 로** 센 판정인가(예상→확정이면 지문이 바뀐다)
        xi_state=" · ".join(
            sorted({str(getattr(v, "state", "") or "없음")
                    for v in (dict(getattr(facts, "xi", None) or {})).values()})
            or ["없음"]))
    got.why = (" · ".join(f"{k} {v.gap:+.2f}" if v.gap is not None
                          else f"{k} ⬜" for k, v in axes.items())
               + f" → 종합 {got.verdict.get('edge') or '가리지 못함'} "
               + f"{got.verdict.get('strength')}")
    got.why += f" · XI {got.xi_state} · 지문 {fingerprint(got)}"
    logger.info("[S2] 상성 — %s", got.why)
    return got
