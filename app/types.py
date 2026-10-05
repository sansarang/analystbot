"""v4 §1 용어 · §3 STEP 스키마 — **코드의 타입이 정의와 일치해야 한다.**

🔴 **이 파일이 v4 §3 의 "파일·필드 이름은 이대로"를 집행한다.** STEP 마다 산출
파일이 하나씩 있고, 그 파일의 모양이 여기 7종이다.

| 종 | STEP | 산출 |
|---|---|---|
| `Slate` | 0 | `slate.json` |
| `Variables` | 1~3 | `variables.json` |
| `PremiseCheck` | 2 | `premise_check.json` |
| `Sufficiency` | 4 | `sufficiency.json` |
| `Scenarios` | 5 | `scenarios.json` |
| `Survival` | 6 | `survival.json` |
| `Ledger` | 8 | 채점 원장 |

🔴 **모든 모델이 `extra="forbid"` 다.** 그래서 스키마에 없는 칸 — 특히 **배당
   숫자** — 을 넣으면 그 자리에서 터진다(§0 · §11-9 · §3 STEP 0 계약).

🔴 **LLM 이 쓰면 안 되는 칸**(§3 마지막 · §14-5): `direction`·`weight`·
   `strength`·`survival`·`verdict`. 이 파일은 그 칸들을 **규칙으로** 정한다 —
   `weight` 는 `hardness` 에서 파생되고(§4 가중치), `verdict` 는 `survival` 이
   정한다(§6). 값이 어긋나면 저장이 실패하므로 LLM 출력이 흘러들 수 없다.

⚠️ **경기 후 기사 판별은 여기 베끼지 않는다.** v3 §12-c 검증기가
   `app/verify.py` 에 살아 있고 §3 이 *"그대로"* 라고 했다 — `verify.parse_when`
   을 **부른다.**
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app import rules, verify

# ══════════════════════════════════════════════════════════════════
# §1 용어의 값 집합 — 🔴 **문자열을 자유롭게 두지 않는다.**
#    v3 에서 `stance`·`gate_label` 이 자유 문자열이라 값이 갈렸다.
# ══════════════════════════════════════════════════════════════════

#: §1 변수 — 이 경기 결과를 한쪽으로 기울이는 방향
Direction = Literal["home", "away", "draw", "over", "under"]

#: §4 가중치 — hardness 가 weight 를 정한다
Hardness = Literal["hard", "likely", "soft"]
WEIGHT_OF: dict[str, float] = {"hard": 1.0, "likely": 0.7, "soft": 0.4}

#: §1 마켓 — **보드에 실제로 있는 줄만**
#
#  🔴 `btts` 는 사용자 지적 2026-10-03 으로 더했다 — 사용자가 손으로 쓴 보드에
#     *"양팀득점"* 줄이 있었고 우리 보드에는 **그 마켓 자체가 없었다**.
#     ⚠️ v4 §1 에 없는 마켓이다. 선언은 `config/scenario_rules.yaml` 의
#        `board_markets` 에 있고, DB CHECK 도 함께 넓혔다.
MarketType = Literal["home", "draw", "away", "home_dc", "away_dc",
                     "handicap", "total", "btts"]

#: 🔴 `btts` 의 **두 쪽**. `Market.team` 칸에 온다(`total` 과 같은 규약).
BTTS_SIDES = ("yes", "no")

#: 🔴 §1 — `total(over/under, 기준선)` 의 **방향**. `Market.team` 칸에 온다.
#   ⚠️ 칸을 새로 만들지 않았다 — §1 이 마켓의 칸을 셋으로 못 박았다(사본 금지).
TOTAL_SIDES = ("over", "under")

#: §1 이름 적기 — survival 1.0 만 "낸다", 0.8 이상은 "소액", 그 미만은 이름 없음
Verdict = Literal["name", "small", "none"]

#: §3 STEP 0
GameStatus = Literal["scheduled", "postponed", "inprogress"]
MatchType = Literal["league", "cup_single", "friendly", "qualifier",
                    "final_group"]

#: §1 시나리오 — A~E
# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **글자는 여덟이다** — 사용자 결정 ① (2026-10-04)
# ══════════════════════════════════════════════════════════════════
#
# > 시나리오 글자 → **A(늘린다), 단 상한 8**. ID를 A~E 고정이 아니라 **A~H**로
# > 바꾸고, 필수형은 빈자리가 없으면 넣지 못하는 게 아니라 **항상 들어간다** —
# > 일반 시나리오가 8개를 넘을 때만 **strength 최저인 일반 시나리오**를 뺀다.
#
# ⚠️ 왜 — 다섯이면 §6-2 보강이 **자리를 못 얻었다**: `A·B` 방향 · `C` 무승부 ·
#    `D·E` 교차 규칙으로 다 찼고, 대량득점형·난타전이 영영 안 섰다.
#    🔴 v5-A §5 정답지 재현 계약이 셋 중 **둘**에서 그 자리를 집었다
#    (남아공 5-0 · 크로아티아 2-2).
# 🔴 사용자가 **B·C 를 거부한 까닭**도 남긴다: B(필수형이 일반을 밀어냄)는
#    *"반대 방향 시나리오가 빠질 위험"*, C(한 글자에 여러 스코어)는
#    *"'하나라도 죽으면 사망' 규칙과 섞여 생존이 왜곡된다."*
ScenarioId = Literal["A", "B", "C", "D", "E", "F", "G", "H"]

#: §6 이름 적기 문턱 — `verdict` 는 이 값들이 정한다. LLM 이 아니다.
NAME_AT = 1.0
SMALL_AT = 0.8


class _Strict(BaseModel):
    """🔴 스키마에 없는 칸을 거부한다 — **배당 숫자가 들어올 문을 닫는다.**

    v4 §3 STEP 0: *"배당 숫자 필드는 존재하지 않는다(계약: 숫자 필드가 있으면
    실패)."* `extra="forbid"` 가 그것을 **모든** 모델에서 집행한다 —
    금칙 이름 목록을 손으로 유지하지 않는다(그런 목록은 언제나 한 발 늦는다).
    """

    model_config = ConfigDict(extra="forbid", frozen=False)


# ══════════════════════════════════════════════════════════════════
# STEP 0 → slate.json
# ══════════════════════════════════════════════════════════════════

class Market(_Strict):
    """§1 마켓 — 종류 + 기준선. 🔴 **가격이 없다.**"""

    market_type: MarketType
    team: str | None = None
    line: float | None = None

    @model_validator(mode="after")
    def _line_where_needed(self):
        """🔴 핸디·총점은 기준선이 없으면 생존을 셀 수 없다(§1 시나리오).

        🔴 **총점은 `over`/`under` 도 있어야 한다**(사용자 지시 2026-10-02 ⑪).
           §1 이 마켓을 *"total(**over/under**, 기준선)"* 으로 적었고 칸은
           `market_type`·`team`·`line` 셋뿐이다 → 방향은 `team` 칸에 온다.
           ⚠️ 비면 §6-a 대입이 *"오버인가 언더인가"* 를 모른 채 돌고, 그러면
              생존이 **조용히** 한쪽으로 계산된다. 그래서 막는다.
        """
        if self.market_type in ("handicap", "total") and self.line is None:
            raise ValueError(f"{self.market_type} 는 line 이 있어야 한다")
        if self.market_type == "handicap" and not self.team:
            raise ValueError("handicap 은 team 이 있어야 한다")
        if self.market_type == "total" and self.team not in TOTAL_SIDES:
            raise ValueError(
                f"total 은 team 칸에 {TOTAL_SIDES} 중 하나가 있어야 한다 "
                f"(받은 값 {self.team!r}) — §1 'total(over/under, 기준선)'")
        return self


class Slate(_Strict):
    """STEP 0 — 경기와 보드. §2 *"DB 는 UTC 저장, 표시만 KST"*."""

    game_id: int
    league: str
    home: str
    away: str
    kst_time: datetime
    venue: str | None = None
    status: GameStatus = "scheduled"
    match_type: MatchType = "league"
    board: list[Market] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════
# STEP 1~3 → variables.json
# ══════════════════════════════════════════════════════════════════

class Variable(_Strict):
    """§1 변수 — **출처가 있는 사실 한 줄.**

    🔴 *"방향이 없는 사실은 배경이지 변수가 아니다"*(§1). 그래서 `direction` 이
       필수다 — 없는 항목은 `Variables.background` 로 간다(§3 STEP 1~3).
    """

    id: str
    #: 🔴 **§4 유형 13종.** 값 집합은 `config/variable_types.yaml` 이 원본이고
    #: 그 파일은 `test_variable_types_가_v4_4절_표를_전부_담았다` 로 v4 §4 표에서
    #: 자란다 — 여기 13개를 베끼지 않는다.
    #: ⚠️ 종전 판은 `type: str` 에 *"값 검사는 yaml 이 한다"* 는 **주석만** 달고
    #:    실제 대조가 없었다(리뷰 B2). `type="오타"` 가 저장됐고, 그 오타는 단계
    #:    5·6 의 §5-c 유형 매칭에서 **조용히 안 걸린다**(§12 M6 재발 경로).
    type: str
    direction: Direction
    hardness: Hardness
    weight: float
    text: str
    source_url: str
    #: 🔴 **`None` 이 허용된다 — 사용자 결정 2026-10-02(안 A).**
    #
    #  순위표에는 발행 시각이 **없다**(fotmob 표·`standings/now` 둘 다). 그런데
    #  §4 `stakes`·`home_field` 가 거기서 나온다 — 필수로 두면 그 두 유형이 §3
    #  구조에 **영영 못 들어간다**(실측 2026-10-02, `app/classify.py` 를 지으며 드러났다).
    #
    #  ⚠️ **그냥 열면 구멍이다.** 이 칸은 §12-c-2(경기 후 기사 배제)가 쓰는 칸이라,
    #     날짜 없는 **기사**가 그 검사를 비껴간다.
    #  🔴 그래서 조건을 둘 건다(아래 `_rules` 가 집행한다):
    #     ① `dateless_reason` 이 **반드시** 있어야 한다 — 조용히 비울 수 없다
    #     ② `hardness` 는 **soft** 여야 한다 — §12-c-1 *"날짜를 못 읽는 자료는
    #        soft 로만 남긴다"* 가 이미 그 규칙이다
    published_at: datetime | None
    #: 🔴 `published_at` 이 `None` 일 때 **왜 없는지.** 비면 저장 실패다.
    dateless_reason: str = ""
    is_premise: bool = False
    collected_at_step: Literal[1, 2, 3] = 1

    @model_validator(mode="after")
    def _rules(self):
        """🔴 §4 — `type` 은 유형표에 있는 것만, `weight` 는 `hardness` 가 정한다."""
        known = rules.variable_types()
        if self.type not in known:
            raise ValueError(
                f"§4 유형표에 없는 type 이다: {self.type!r} "
                f"(있는 것: {', '.join(sorted(known))})")
        want = WEIGHT_OF[self.hardness]
        if self.weight != want:
            raise ValueError(
                f"{self.hardness} 의 weight 는 {want} 다 (받은 값 {self.weight})")
        # 🔴 §3 — 출처 없는 변수는 저장하지 않는다. 빈 문자열도 없는 것이다.
        if not self.source_url.strip():
            raise ValueError("source_url 이 없다 — 출처 없는 변수는 저장하지 않는다")
        if not self.text.strip():
            raise ValueError("text 가 없다")
        # 🔴 날짜가 없으면 **사유가 있어야 하고 soft 여야 한다**(§12-c-1 · 안 A)
        if self.published_at is None:
            if not self.dateless_reason.strip():
                raise ValueError(
                    "published_at 이 없으면 `dateless_reason` 을 적어야 한다 — "
                    "조용히 비우면 §12-c-2(경기 후 기사 배제)가 비껴간다")
            if self.hardness != "soft":
                raise ValueError(
                    f"published_at 이 없는 자료는 soft 다 (받은 값 "
                    f"{self.hardness}) — §12-c-1 *\"날짜를 못 읽는 자료는 soft 로만 "
                    f"남긴다\"*")
        elif self.dateless_reason.strip():
            raise ValueError(
                "published_at 이 있는데 `dateless_reason` 이 적혀 있다 — 둘 중 하나다")
        return self


class Background(_Strict):
    """§3 STEP 1~3 — *"direction 없는 항목은 `background[]` 로 분리 저장"*.

    ⚠️ **버리지 않는다.** 방향이 없다고 지우면 "자료가 안 왔다"와 "왔는데 방향이
       없다"를 구분할 수 없다(조용한 0 금지).
    """

    id: str
    text: str
    source_url: str
    #: 🔴 `Variable` 과 같은 규약 — 사용자 결정 2026-10-02(안 A)
    published_at: datetime | None
    dateless_reason: str = ""

    @model_validator(mode="after")
    def _dateless(self):
        if self.published_at is None and not self.dateless_reason.strip():
            raise ValueError(
                "published_at 이 없으면 `dateless_reason` 을 적어야 한다")
        return self


class Variables(_Strict):
    """STEP 1~3 산출. 🔴 경기 시각을 함께 들고 있어야 **경기 후 기사**를 막는다."""

    game_id: int
    kst_time: datetime
    variables: list[Variable] = Field(default_factory=list)
    background: list[Background] = Field(default_factory=list)

    @property
    def dateless(self) -> list[str]:
        """🔴 **발행 시각 없이 들어온 항목의 이름.** 조용히 넘기지 않는다.

        사용자 결정 2026-10-02(안 A)로 `published_at` 이 `None` 일 수 있게 됐고,
        그 항목은 §12-c-2(경기 후 기사 배제) 검사를 **건너뛴다.** 건너뛴 것이
        보이지 않으면 *"검사를 다 했다"* 로 읽힌다.
        ⚠️ 카드·보고가 이 목록을 그대로 적는다.
        """
        return [f"{v.id}: {v.dateless_reason}"
                for v in (*self.variables, *self.background)
                if v.published_at is None]

    @model_validator(mode="after")
    def _no_post_game(self):
        """🔴 §3 — *"published_at 이 경기 이후면 저장 실패"*(v3 §12-c 그대로).

        ⚠️ 판별 로직을 여기 베끼지 않는다 — `verify.parse_when` 을 **부른다.**
           시각 문자열의 온갖 모양(타임존 없음·ISO·한글)을 그 함수가 이미 안다.
        """
        game = verify.parse_when(self.kst_time)
        if game is None:
            raise ValueError("kst_time 을 읽을 수 없다")
        for v in (*self.variables, *self.background):
            # 🔴 **날짜가 없는 자료는 이 검사를 건너뛴다**(사용자 결정 2026-10-02 안 A).
            #    ⚠️ 그래도 **조용히** 건너뛰지 않는다 — `dateless` 가 이름으로 들고
            #       있고 카드·보고가 그것을 적는다(조용한 0 금지).
            #    🔴 `Variable._rules` 가 "사유 필수 + soft 필수" 를 이미 걸었다.
            if v.published_at is None:
                continue
            when = verify.parse_when(v.published_at, assume_tz=game.tzinfo)
            if when is None:
                raise ValueError(f"{v.id}: published_at 을 읽을 수 없다")
            if when > game:
                raise ValueError(
                    f"{v.id}: 경기 후 기사다 ({when.isoformat()} > "
                    f"{game.isoformat()}) — 경기 전 판정에 쓸 수 없다")
        return self


# ══════════════════════════════════════════════════════════════════
# STEP 2 → premise_check.json
# ══════════════════════════════════════════════════════════════════

class PremiseCheckItem(_Strict):
    """전제 하나의 재검증 결과. §3: `kept` 면 대체 변수가 없어야 한다."""

    premise_id: str
    query_used: list[str] = Field(default_factory=list)
    result: Literal["kept", "replaced"]
    replacement_variable_id: str | None = None

    @model_validator(mode="after")
    def _replacement_only_when_replaced(self):
        if self.result == "replaced" and not self.replacement_variable_id:
            raise ValueError(f"{self.premise_id}: replaced 인데 대체 변수가 없다")
        if self.result == "kept" and self.replacement_variable_id:
            raise ValueError(f"{self.premise_id}: kept 인데 대체 변수가 있다")
        return self


class PremiseCheck(_Strict):
    """STEP 2 산출.

    🔴 §3: *"is_premise=true 인 변수마다 항목이 하나씩 있어야 한다
       (0건이면 STEP 5 진입 불가)."* 그 대조는 `Variables` 를 함께 받는
       `covers()` 가 한다 — 파일 하나만 보고는 알 수 없다.
    """

    game_id: int
    items: list[PremiseCheckItem] = Field(default_factory=list)

    def covers(self, vars_: Variables) -> list[str]:
        """재검증이 **빠진** 전제의 id. 🔴 빈 목록이어야 STEP 5 로 간다.

        ⚠️ 이름으로 돌려준다 — 개수만 세면 어느 전제가 빠졌는지 사라진다.
        """
        done = {i.premise_id for i in self.items}
        return [v.id for v in vars_.variables if v.is_premise
                and v.id not in done]


# ══════════════════════════════════════════════════════════════════
# STEP 4 → sufficiency.json
# ══════════════════════════════════════════════════════════════════

#: §1 자료 부족 — 방향 있는 변수 3개 미만이거나 반대 방향 변수가 0개
MIN_DIRECTIONAL = 3


class Sufficiency(_Strict):
    """STEP 4 — 시나리오를 만들 자료가 있나.

    🔴 `verdict` 는 **수가 정한다**(§1 자료 부족). LLM 이 쓸 수 없다.
    """

    game_id: int
    n_directional: int
    n_opposite: int
    verdict: Literal["pass", "insufficient"]
    reason: str = ""

    @model_validator(mode="after")
    def _verdict_follows_counts(self):
        want = ("insufficient"
                if self.n_directional < MIN_DIRECTIONAL or self.n_opposite == 0
                else "pass")
        if self.verdict != want:
            raise ValueError(
                f"n_directional={self.n_directional}·n_opposite="
                f"{self.n_opposite} 면 verdict 는 {want} 다 (받은 값 "
                f"{self.verdict}) — §1 자료 부족은 수가 정한다")
        if self.verdict == "insufficient" and not self.reason.strip():
            raise ValueError("insufficient 인데 reason 이 없다 — 조용한 0 금지")
        return self


# ══════════════════════════════════════════════════════════════════
# STEP 5 → scenarios.json
# ══════════════════════════════════════════════════════════════════

class Scenario(_Strict):
    """§1 시나리오 — 같은 방향을 미는 변수 묶음 하나.

    🔴 *"반드시 구체 스코어 집합을 가진다 — 스코어 없으면 총점·핸디 생존을
       셀 수 없다"*(§1).
    ⚠️ `direction` 은 v4 §3 의 필드 목록에 **없다.** 방향은 `template_id` 가
       정한다(§5-b 표) — 그 대조는 `scenario_rules.yaml` 이 붙는 단계에서 한다.
    """

    id: ScenarioId
    variables: list[str] = Field(default_factory=list)
    scores: list[str] = Field(default_factory=list)
    strength: float
    template_id: str
    narrative: str = ""

    @model_validator(mode="after")
    def _rules(self):
        if not self.scores:
            raise ValueError(
                f"시나리오 {self.id}: scores 가 비었다 — 생존을 셀 수 없다")
        if self.strength < 0:
            raise ValueError(f"시나리오 {self.id}: strength 가 음수다")
        return self


class Scenarios(_Strict):
    """STEP 5 산출. 🔴 §3: *"scenarios 수 2 미만 실패."*"""

    game_id: int
    scenarios: list[Scenario] = Field(default_factory=list)

    @model_validator(mode="after")
    def _at_least_two(self):
        if len(self.scenarios) < 2:
            raise ValueError(
                f"시나리오가 {len(self.scenarios)}개다 — 2 미만이면 "
                "예측불허를 셀 수 없다(§3 STEP 5)")
        ids = [s.id for s in self.scenarios]
        if len(set(ids)) != len(ids):
            raise ValueError(f"시나리오 id 가 겹친다: {ids}")
        # 🔴 §3 STEP 5 셋째 계약 — *"모든 시나리오가 같은 direction 이면 실패
        #    (반대 방향 시나리오 최소 1개)."* §5-c-6 이 같은 것을 규칙으로 적었다.
        # ⚠️ 방향은 **스코어에서 계산한다**(§4) — 표에 적지 않는다.
        #    난타전처럼 결과가 섞인 묶음은 방향이 `None` 이고, 그것이 하나라도
        #    있으면 "전부 한 방향"이 아니다 — 이미 반대 결과를 품기 때문이다.
        if rules.all_one_direction([s.scores for s in self.scenarios]):
            one = rules.direction_of(self.scenarios[0].scores)
            raise ValueError(
                f"모든 시나리오가 {one} 방향이다 — 반대 방향 시나리오가 최소 "
                "하나 있어야 한다(§3 STEP 5 · §5-c-6). STEP 3 으로 되돌려 "
                "반대 변수를 찾고, 그래도 없으면 '자료 부족'이다")
        return self


# ══════════════════════════════════════════════════════════════════
# STEP 6 → survival.json
# ══════════════════════════════════════════════════════════════════

class MarketSurvival(_Strict):
    """마켓 하나의 생존. §1: *"살아남는 시나리오의 strength 합 / 전체 합."*

    🔴 §3 계약 둘을 여기서 집행한다:
       - `survival < 1.0` 인데 `verdict=name` 이면 실패
       - `survival < 0.8` 인데 `verdict=small` 이면 실패
    """

    market_type: MarketType
    team: str | None = None
    line: float | None = None
    alive_scenarios: list[ScenarioId] = Field(default_factory=list)
    dead_scenarios: list[ScenarioId] = Field(default_factory=list)
    survival: float = Field(ge=0.0, le=1.0)
    verdict: Verdict

    @model_validator(mode="after")
    def _verdict_follows_survival(self):
        """🔴 **`verdict` 는 `survival` 이 정한다 — LLM 도 사람도 못 고른다.**

        §12 가 금지한 실수가 이것이다(아르메니아 +0.5 — 생존이 1.0 이 아닌데
        이름을 적었다).
        """
        if self.verdict == "name" and self.survival < NAME_AT:
            raise ValueError(
                f"{self.market_type}: survival={self.survival} 인데 name 이다 — "
                f"{NAME_AT} 만 이름을 적는다(§6)")
        if self.verdict == "small" and self.survival < SMALL_AT:
            raise ValueError(
                f"{self.market_type}: survival={self.survival} 인데 small 이다 — "
                f"{SMALL_AT} 이상만 소액이다(§6)")
        if set(self.alive_scenarios) & set(self.dead_scenarios):
            raise ValueError(
                f"{self.market_type}: 같은 시나리오가 alive 와 dead 에 둘 다 있다")
        return self


class Survival(_Strict):
    """STEP 6 산출.

    🔴 §3: *"보드에 없는 market_type 이 verdict name/small 이면 실패
       (보드 없는 경기 예외, §6-c)."* 그 대조는 보드를 함께 받는
       `off_board()` 가 한다 — 파일 하나만 보고는 알 수 없다.
    """

    game_id: int
    markets: list[MarketSurvival] = Field(default_factory=list)

    def off_board(self, board: list[Market]) -> list[str]:
        """보드에 없는데 이름이 적힌 마켓. 🔴 빈 목록이어야 카드를 낸다.

        ⚠️ **보드가 비면 검사하지 않는다**(§6-c 예외) — 사용자가 보드를 주지
           않은 경기다. 보드가 없는 것과 마켓이 보드 밖인 것은 다르다.
        """
        if not board:
            return []
        have = {(m.market_type, m.team, m.line) for m in board}
        return [f"{m.market_type}/{m.team}/{m.line}" for m in self.markets
                if m.verdict in ("name", "small")
                and (m.market_type, m.team, m.line) not in have]


# ══════════════════════════════════════════════════════════════════
# STEP 8 → ledger
# ══════════════════════════════════════════════════════════════════

class CardVerdictResult(_Strict):
    """카드가 적은 마켓 하나의 결과."""

    market: str
    hit: bool


class Ledger(_Strict):
    """STEP 8 채점 원장.

    🔴 §3: *"결과 후 survival.json 수정 금지(불변)."* 그래서 원장은 **따로**
       쌓인다 — 채점이 판정을 덮어쓰지 않는다.
    ⚠️ `missed_variables` 는 **경기 후 드러난 변수 중 경기 전 미수집**이다.
       비어 있는 것과 안 재 본 것이 다르므로 이름으로 남긴다.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: int
    realized_scenario_id: ScenarioId | None = None
    missed_variables: list[str] = Field(default_factory=list)
    card_verdicts_result: list[CardVerdictResult] = Field(default_factory=list)
    premise_failures: list[str] = Field(default_factory=list)


#: 🔴 v4 §3 의 STEP 산출 7종. 계약이 이 표에서 자란다 — 손으로 세지 않는다.
STEP_PAYLOADS: dict[str, type[_Strict]] = {
    "slate": Slate,
    "variables": Variables,
    "premise_check": PremiseCheck,
    "sufficiency": Sufficiency,
    "scenarios": Scenarios,
    "survival": Survival,
    "ledger": Ledger,
}
