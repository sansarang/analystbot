"""🔴🔴 **v6 §3 — 단계 경계 타입 전부.** 여기 밖의 꼴은 단계 사이를 못 다닌다.

지시서 §3: *"모든 모델은 pydantic v2 `BaseModel`,
`model_config = ConfigDict(extra="forbid", frozen=True)`. 열거값은 `Literal`
또는 `Enum` — **자유 문자열 금지.**"*

══════════════════════════════════════════════════════════════════
🔴 왜 **얼리고**(frozen) **금지하나**(extra="forbid")
══════════════════════════════════════════════════════════════════

⚠️ 실사고 2026-10-04~06: 같은 값이 자리마다 다른 꼴로 다녀서 카드가 죽었다 —
   `Game` 을 dict 로 아는 호출부, 반증 폐기를 dict 로 읽은 렌더러(`AttributeError:
   'tuple' object has no attribute 'get'` → **카드 전체가 안 나왔다**), 어댑터마다
   다른 `players`(dict/list).
🔴 `extra="forbid"` 는 **모르는 칸을 조용히 받지 않게** 한다. 칸 이름이 갈리면
   그 자리에서 터지고, 그것이 카드가 죽는 것보다 낫다(그때 고칠 곳이 보인다).
🔴 `frozen=True` 는 **지나간 단계가 앞 단계 값을 못 고치게** 한다 — 판정층이
   변수를 고치면 *"무엇으로 판정했나"* 가 사라진다.

🔴 **LLM 출력 모델에는 코드가 정할 칸을 두지 않는다**(§3) — `favors`·`weight`·
   `strength`·`grade`. 모델이 그 칸을 채울 **길 자체**를 없앤다.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ══════════════════════════════════════════════════════════════════
# 열거값 — 🔴 자유 문자열 금지(§3)
# ══════════════════════════════════════════════════════════════════

Sport = Literal["soccer", "baseball", "hockey", "basketball", "volleyball"]

#: 🔴 경기 형식 — 90분 무승부 필수형의 방아쇠다(§6 `draw_90`)
MatchFormat = Literal["league", "group", "knockout_single", "two_leg_1st",
                      "two_leg_2nd", "final_single", "friendly", "unknown"]

#: 🔴 하위 과제 **여덟** — 유형군 4 × 팀 2(§2 s3)
SubtaskId = Literal["A-home", "A-away", "B-home", "B-away",
                    "C-home", "C-away", "D-home", "D-away"]

#: 🔴 출처 등급 — 도메인 등급표가 든다
Tier = Literal["official", "national", "local", "aggregator", "tip", "dead"]

#: 🔴 **발행일을 어디서 얻었나** — `none` 이면 그 Doc 은 근거가 못 된다(불변식 9)
DateSource = Literal["meta", "jsonld", "time_tag", "engine", "htmldate", "none"]

#: 🔴 **누구에게 유리한가**(승패) — 방향은 **코드가** 정한다(모델이 못 적는다)
#
#  ══════════════════════════════════════════════════════════════════
#  🔴🔴 **둘로 갈랐다** — 사용자 지시 2026-10-06 ④
#  ══════════════════════════════════════════════════════════════════
#
#  > `Variable.favors`(승패: home/away/both)와 `Variable.goals`(득점: up/down/none)
#  > 를 분리. 결장 → `favors=상대`, `goals=`수비 결장이면 `up` / 공격 결장이면 `down`.
#  > *"자료 얇음"* 판정은 **`favors` 기준으로.**
#
#  ⚠️ 종전에는 `goals_up` 이 **승패 칸에** 들어 있었다 — 그래서 수비 결장 변수가
#     *"어느 팀 쪽인가"* 를 말하지 못했고, §7 R5 가 *"방향 1종"* 으로 등급을 거뒀다
#     (실측 2026-10-06: 변수 15개 전부 한 방향).
Favors = Literal["home", "away", "both"]

#: 🔴 **득점이 오르나 내리나** — 승패와 **따로** 센다(총점·양팀득점 마켓이 이것을 본다)
Goals = Literal["up", "down", "none"]

Hardness = Literal["hard", "soft"]

XIState = Literal["confirmed", "predicted", "none"]

#: 🔴 마켓 — 배당 칸은 **없다**(절대규칙 6)
Market = Literal["win", "draw", "unbeaten", "handicap", "total", "btts"]

Mark = Literal["○", "△", "✗"]

#: 🔴 등급 — ⚠️ **`자료부족` 은 "없음" 과 다르다**(§8-6 이 막는 섞임이다).
#
#  `없음`      재 봤는데 **안 섰다**(수가 문턱 아래다)
#  `자료부족`  **애초에 등급을 매길 수 없었다**(변수가 모자라다 · §7 R5)
#  ⚠️ 둘을 한 글자로 적으면 *"우리가 안 했다"* 와 *"해 봤는데 없다"* 가 같아진다.
Grade = Literal["낸다", "소액", "소액하단", "없음", "자료부족"]

AddedBy = Literal["deepseek", "code", "redteam"]

ScenarioType = Literal["home_win", "away_win", "draw", "open", "lock",
                       "conceding", "blowout", "regression", "reverse",
                       "draw_90", "other"]


class DropReason(str, Enum):
    """🔴 **버린 까닭** — §8-6: 사유를 지어 쓰지 않는다. 열거값이 원본이다.

    ⚠️ 여기 없는 말로 버리면 `Drop` 이 만들어지지 않는다(그래서 사유가 늘 남는다).
    """

    QUOTE_NOT_FOUND = "quote_not_found"
    BODY_MISSING = "body_missing"
    DATE_MISSING = "date_missing"
    STALE = "stale"
    POST_MATCH = "post_match"
    IDENTITY_MISMATCH = "identity_mismatch"
    #: 🔴 `stakes` 인데 **구체적 동기가 없다**(사용자 지시 2026-10-06(2차) ③)
    #  ⚠️ *"10월에 친선 둘을 치른다"* 는 동기가 아니다 — 진출·탈락·우승·기록·감독
    #     거취·순위 중 하나가 claim 에 있어야 그 유형이다.
    STAKES_VAGUE = "stakes_vague"
    #: 🔴 그 종목 낱말이 본문에 없다 — 남의 종목 기사다(사용자 지시 2026-10-06 ②)
    #  ⚠️ 실측: 권순우 **테니스** 기사가 축구 결장 변수로 들어왔다(두 나라 이름이
    #     둘 다 있어서 신원 선필터를 통과했다).
    SPORT_MISMATCH = "sport_mismatch"
    SIDE_MISMATCH = "side_mismatch"
    TYPE_OFF_CATALOG = "type_off_catalog"
    THIN_SAMPLE = "thin_sample"
    CONFLICT = "conflict"
    DUPLICATE = "duplicate"
    CITED_EXCLUDED = "cited_excluded"
    UNKNOWN_VAR = "unknown_var"
    NEW_FACT = "new_fact"
    LLM_TRUNCATED = "llm_truncated"
    LLM_SCHEMA = "llm_schema"
    LLM_TIMEOUT = "llm_timeout"
    LLM_HTTP_5XX = "llm_http_5xx"
    LLM_429 = "llm_429"
    BUDGET_CUT = "budget_cut"
    REPLAY_MISS = "replay_miss"
    NO_DOC = "no_doc"
    AGENT_ZERO = "agent_zero"


#: 🔴 팀 **열쇠**다 — 이름이 아니다. 이름은 **렌더할 때만** 쓴다(§3).
#
#  ⚠️ 실사고 2026-10-06: 모델이 `team: "Jamaica"` 를 적어 전부 폐기됐다
#     (`name_not_key`). 🔴 v6 는 스키마의 `enum` 으로 **그 경기 두 열쇠만**
#     허용하므로 그 일이 **구조적으로 불가능**하다(§4).
TeamKey = Annotated[str, Field(pattern=r"^team:\d{6}$")]


class Frozen(BaseModel):
    """🔴 모든 경계 타입의 어버이 — 얼리고, 모르는 칸을 금지한다(§3)."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Question(Frozen):
    """🔴 사용자가 물은 것 — 파이프라인의 **유일한 입구**."""

    raw: str
    team: str = ""
    opponent: str = ""
    asked_at: datetime


class MatchRef(Frozen):
    """🔴 s1 산출 — **그 경기 하나**. ⚠️ 이름은 렌더용 칸에만 둔다."""

    id: str
    sport: Sport
    competition: str
    competition_short: str
    home: TeamKey
    away: TeamKey
    home_name: str
    away_name: str
    kickoff_utc: datetime
    venue: str = ""
    langs: list[str] = Field(default_factory=list)
    #: 🔴 오픈월드 ⑥단을 타고 들어왔나 — 상한이 그것을 본다(§7)
    openworld: bool = False

    @field_validator("kickoff_utc")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        """🔴 절대규칙 2 — **시간대 없는 킥오프는 받지 않는다.**

        ⚠️ naive 값은 조용히 서버 시간대로 가정되고, 그 가정이 어긋나도 아무 데도
           안 적힌다(그래서 경기를 잃었다 · 실측 2026-10-03).
        """
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError(f"시간대 없는 킥오프다: {v!r}")
        return v


class Ambiguous(Frozen):
    """🔴 s1 이 **못 고를 때** — 고르는 것은 사용자다(§17-g-3 · M14).

    ⚠️ 하나를 골라 주면 **남의 경기**를 분석할 수 있고, 그 카드는 통째로 거짓이다.
    """

    why: str
    candidates: list[str] = Field(default_factory=list)


class XI(Frozen):
    """🔴 그 팀의 XI — 어댑터별 모양 차이는 `adapt.py` 가 흡수한다."""

    team: TeamKey
    state: XIState
    formation: str | None = None
    players: list[str] = Field(default_factory=list)
    bench: list[str] = Field(default_factory=list)
    source_url: str = ""


class Facts(Frozen):
    """🔴 s2 산출 — 구조 사실. ⚠️ **없으면 `None`**(지어내지 않는다 · §3)."""

    standings: dict = Field(default_factory=dict)
    #: 🔴 팀별 최근 N경기 스코어 목록
    recent: dict = Field(default_factory=dict)
    h2h: dict = Field(default_factory=dict)
    xi: dict[str, XI] = Field(default_factory=dict)
    match_format: MatchFormat = "unknown"
    extra_time: bool | None = None
    sources: list[str] = Field(default_factory=list)


class Doc(Frozen):
    """🔴 받아 둔 문서 하나 — **본문과 발행일이 한 몸**이다(§3).

    ⚠️ 실사고 2026-10-05~06: 본문과 날짜를 **따로** 들고 다녀 날짜가 **세 경로**
       에서 끊겼다(`date_missing` 20건). 🔴 한 몸이면 그 병이 불가능하다.
    """

    id: str
    url: str
    domain: str
    tier: Tier
    lang: str
    title: str = ""
    body: str
    published_at: datetime | None = None
    date_source: DateSource = "none"
    subtask: SubtaskId


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **LLM 출력 모델** — `llm.py` 만 이것을 스키마로 바꿔 보낸다(§4)
# ══════════════════════════════════════════════════════════════════
#
# 🔴 코드가 정할 칸(`favors`·`weight`·`strength`·`grade`)을 **두지 않는다** —
#    모델이 그 칸을 채울 길 자체를 없앤다(§3 · §9 금지).


class VarCandidate(Frozen):
    """🔴 s4 — 모델이 내는 변수 후보. ⚠️ **방향 칸이 없다**(코드가 정한다)."""

    subtask: SubtaskId
    #: 🔴 그 하위 과제 담당 유형만 — 요청마다 `enum` 으로 박는다(§4)
    type: str
    #: 🔴 **그 경기 두 열쇠만** — 요청마다 `enum` 으로 박는다
    subject: TeamKey
    claim: str
    #: 🔴🔴 **그 사실의 핵심 대상**(선수명 또는 사건 한 낱말) — 사용자 지시 2026-10-06 ①
    #
    #  > 같은 subject + 같은 type + 같은 **핵심 대상**(선수명·사건)이면 하나의
    #  > `Variable` 로 합치고 `doc_ids` 를 모은다 … 문장 유사도(MinHash)가 아니라
    #  > **"누가·무엇" 열쇠**로 묶는다.
    #
    #  ⚠️ 실측 2026-10-06: 김민재 결장이라는 **한 사실**이 변수 11개로 셌다 —
    #     문장이 저마다 달라 MinHash 가 묶지 못했다. 🔴 이 칸이 그 열쇠다.
    target: str
    #: 🔴 본문의 글자 **그대로** — s5 가 Doc 본문에 대고 맞춰 본다
    quote: str
    #: 🔴 어느 Doc 인가 — 요청마다 **그 하위에 넘긴 id 만** `enum` 으로 박는다
    doc_id: str


class VarCandidates(Frozen):
    """🔴 구조화 출력은 **object 로만** 받는다 — 최상위 배열은 스키마가 못 받는다."""

    variables: list[VarCandidate] = Field(default_factory=list)


class HypoLine(Frozen):
    """🔴 가설 한 줄 — 문장 + **근거 변수 번호**. ⚠️ 번호만 적으면 안 된다."""

    text: str
    var_ids: list[str] = Field(default_factory=list)


class Hypothesis(Frozen):
    """🔴 한 팀의 가설. 열쇠는 **`home`·`away` 두 글자**(팀 이름이 아니다)."""

    team: Literal["home", "away"]
    reasons: list[HypoLine] = Field(default_factory=list)
    breaks: list[HypoLine] = Field(default_factory=list)


class ScenarioOut(Frozen):
    """🔴 s6 — 모델이 내는 시나리오. ⚠️ `strength` 는 **코드가** 센다."""

    id: str
    outcomes: list[tuple[int, int]] = Field(default_factory=list)
    driver_vars: list[str] = Field(default_factory=list)
    mechanism: str


class HypoOut(Frozen):
    """🔴 DeepSeek 단계 3 출력."""

    hypotheses: list[Hypothesis] = Field(default_factory=list)
    scenarios: list[ScenarioOut] = Field(default_factory=list)


class RedTeamLine(Frozen):
    """🔴 반증 한 줄 — **추가만** 한다(생존율 상승 금지 · §5 s6)."""

    market: str
    says: str
    scenario_id: str | None = None


class RedTeamOut(Frozen):
    """🔴 DeepSeek 단계 4 출력."""

    lines: list[RedTeamLine] = Field(default_factory=list)


class SpellOut(Frozen):
    """🔴 오픈월드 ⑥-1 — 철자 후보. ⚠️ 이것도 구조화 출력이다(§5 s1)."""

    candidates: list[str] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════
# 판정층 타입
# ══════════════════════════════════════════════════════════════════


class Variable(Frozen):
    """🔴 s5 산출 — **검증을 지난** 변수. `favors`·`weight` 는 코드가 계산했다."""

    id: str
    type: str
    subject: TeamKey
    #: 🔴 승패 방향(카탈로그 규칙이 정한다)
    favors: Favors
    #: 🔴 득점 방향 — 승패와 **따로**다(사용자 지시 2026-10-06 ④)
    goals: Goals = "none"
    #: 🔴 그 사실의 핵심 대상 — **병합 열쇠**다(같은 subject·type·target = 한 사실)
    target: str = ""
    hardness: Hardness
    weight: float
    claim: str
    quote: str
    doc_ids: list[str] = Field(default_factory=list)
    #: 🔴 해석 규칙이 만든 변수면 그 규칙 번호(`IR08`) — 사람이 되짚을 수 있게
    from_rule: str | None = None
    #: 🔴🔴 **가설 근거로 쓸 수 있나** — 표본 부족·충돌이면 `False`(§5 s5).
    #
    #  ⚠️ 실사고 2026-10-06: 근거에서 뺀 `R1`(맞대결 표본 1경기)을 DeepSeek 문장이
    #     그대로 인용했다. 🔴 이 칸이 그 분리의 **단일 원본**이다.
    usable_as_basis: bool = True


class Drop(Frozen):
    """🔴 **버린 것** — 까닭이 반드시 남는다(#3 조용한 0 금지)."""

    what: str
    reason: DropReason
    detail: str = ""


class Scenario(Frozen):
    """🔴 판정에 들어가는 시나리오 — `strength` 는 코드가 센다."""

    id: str
    outcomes: list[tuple[int, int]] = Field(default_factory=list)
    driver_vars: list[str] = Field(default_factory=list)
    mechanism: str
    type: ScenarioType = "other"
    added_by: AddedBy = "deepseek"
    strength: float = 0.0


class HypoSet(Frozen):
    """🔴 s6 산출."""

    hypotheses: list[Hypothesis] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(default_factory=list)
    redteam: list[RedTeamLine] = Field(default_factory=list)
    drops: list[Drop] = Field(default_factory=list)


class BoardLine(Frozen):
    """🔴 보드 한 줄 — **배당 칸이 없다**(절대규칙 6)."""

    market: Market
    side: str
    point: float | None = None


class Board(Frozen):
    """🔴 캡처한 보드. ⚠️ 없으면 `None` 이고 s7 이 기준선으로 간다."""

    lines: list[BoardLine] = Field(default_factory=list)


class MarketEval(Frozen):
    """🔴 s7 — 마켓 한 줄의 대입 결과."""

    line: BoardLine
    #: `시나리오 id → ○ △ ✗`
    marks: dict[str, Mark] = Field(default_factory=dict)
    survival: float
    cap: float
    grade: Grade
    #: 🔴 **죽은 시나리오들** — `✗` 와 `△` 를 **둘 다** 담는다(§3)
    dead: list[str] = Field(default_factory=list)


class Judgement(Frozen):
    """🔴🔴 **s7 산출** — 마켓 대입·방향·결론·방아쇠가 **한 타입**이다(§3).

    ⚠️ 단계 함수가 `tuple` 을 돌려주면 받는 쪽이 꼴을 **외워야** 한다 — 그것이
       결함 ①의 뿌리였다(§7 정적 검사가 그 서명을 막는다).
    """

    evals: list[MarketEval] = Field(default_factory=list)
    #: 🔴 블록 9 — **등급과 무관하게 매 경기 한 줄**(지시서 §2-2)
    direction: str = ""
    conclusion: str = ""
    triggers: list[str] = Field(default_factory=list)
    #: 🔴 이미 시작한 경기면 등급이 없다(M97) — 그 사유가 여기 든다
    started: bool = False
    started_why: str = ""
    #: 🔴 **왜 그 상한인가** — 사람이 되짚을 수 있게 수와 사유를 함께 든다
    notes: list[str] = Field(default_factory=list)


class Funnel(Frozen):
    """🔴 깔때기 — 칸마다 **센 수**와 **버린 사유**. ⚠️ 안 잰 칸은 `None` 이다."""

    counts: dict[str, int | None] = Field(default_factory=dict)
    drops: list[Drop] = Field(default_factory=list)


class Cost(Frozen):
    """🔴 그 경기에 쓴 돈 — 카드 머리에 적는다(§2)."""

    usd: float = 0.0
    calls: int = 0
    in_tokens: int = 0
    out_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0


class Card(Frozen):
    """🔴🔴 **파이프라인의 산출** — `render.py` 의 유일한 입력(§3)."""

    match: MatchRef
    facts: Facts
    variables: list[Variable] = Field(default_factory=list)
    drops: list[Drop] = Field(default_factory=list)
    hypo: HypoSet | None = None
    evals: list[MarketEval] = Field(default_factory=list)
    direction: str = ""
    conclusion: str = ""
    triggers: list[str] = Field(default_factory=list)
    funnel: Funnel = Field(default_factory=Funnel)
    cost: Cost = Field(default_factory=Cost)
    #: 🔴 **이미 시작한 경기인가** — 그러면 등급이 없다(M97)
    started: bool = False


class LlmFail(Frozen):
    """🔴 LLM 이 답을 못 줬다 — **사유가 갈려 있다**(§4).

    ⚠️ 타임아웃·5xx·429·잘림·스키마는 **고칠 곳이 다르다**(망/서버/속도/입력/
       프롬프트). 하나로 묶으면 어디를 고칠지 못 고른다.
    """

    reason: DropReason
    detail: str = ""
    status: int | None = None
