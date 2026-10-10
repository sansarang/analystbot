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
from typing import Any, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ══════════════════════════════════════════════════════════════════
# 열거값 — 🔴 자유 문자열 금지(§3)
# ══════════════════════════════════════════════════════════════════

Sport = Literal["soccer", "baseball", "hockey", "basketball", "volleyball"]

#: 🔴 경기 형식 — 90분 무승부 필수형의 방아쇠다(§6 `draw_90`)
MatchFormat = Literal["league", "group", "knockout_single", "two_leg_1st",
                      "two_leg_2nd", "final_single", "friendly", "unknown"]

#: 🔴 하위 과제 **여덟** — 유형군 4 × 팀 2(§2 s3)
#: 🔴🔴 **F 를 더했다** — 사용자 지시 2026-10-10(재작성) §3-1(새 사실 72시간).
#  ⚠️ `Literal` 이라 여기 없으면 그 하위의 문서·변수가 **스키마에서 거부된다**
#     (조용히 0건이 아니라 터진다 — 그 쪽이 맞다).
SubtaskId = Literal["A-home", "A-away", "B-home", "B-away",
                    "C-home", "C-away", "D-home", "D-away",
                    "F-home", "F-away"]

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
#: 🔴🔴 `보류` 가 생겼다(사용자 지시 2026-10-07 ②) — **보드가 없으면 등급을 안 붙인다**
#
#  > 둘 다 없으면 기준선 대입표는 *"참고 — 보드 없음"* 으로만 보이고, 등급 칸은 전부
#  > *"보류(보드 없음)"*. 🔴 기준선에 등급을 붙이면 **계약 실패**다.
#
#  ⚠️ `없음`(문턱 미달)과 `보류`(걸 줄이 없다)는 **다른 말**이다 — 섞으면 *"판정했는데
#     안 된다"* 와 *"판정할 줄이 없다"* 가 한 글자가 된다.
Grade = Literal["낸다", "소액", "소액하단", "없음", "자료부족", "보류"]

AddedBy = Literal["deepseek", "code", "redteam"]

#: 🔴 `counter` 는 **역습 필수형**(7차 §4 · 8차 ③) — 이겨야 하는 팀의 상대가 찌르는 갈래
ScenarioType = Literal["home_win", "away_win", "draw", "open", "lock",
                       "conceding", "blowout", "regression", "reverse",
                       "draw_90", "counter", "other"]


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
    #: 🔴🔴 **같은 등급의 팀이 아니다**(사용자 지시 2026-10-06(4차) ①-a)
    #  ⚠️ 실측: A대표 경기 카드에 **아시안게임 금메달 수** 기사가 변수로 들어왔다.
    #     축구 대표팀은 A대표·U-23·아시안게임·올림픽·여자·청소년이 **다른 팀**이다.
    TEAM_TIER_MISMATCH = "team_tier_mismatch"
    #: 🔴🔴 **이 경기와 이어지는 근거가 없다**(사용자 지시 2026-10-06(4차) ①-b)
    #  ⚠️ 상대팀 이름·경기 날짜·경기장·"우즈벡전" 같은 표현이 문단에 있어야 한다.
    OFF_MATCH = "off_match"
    #: 🔴 `stakes` 인데 **구체적 동기가 없다**(사용자 지시 2026-10-06(2차) ③)
    #  ⚠️ *"10월에 친선 둘을 치른다"* 는 동기가 아니다 — 진출·탈락·우승·기록·감독
    #     거취·순위 중 하나가 claim 에 있어야 그 유형이다.
    STAKES_VAGUE = "stakes_vague"
    #: 🔴 *"정보가 없다"* 는 사실이 아니다(9차 ③) — 없음의 보고로는 방향을 못 정한다
    NO_INFO = "no_info"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **결장 선수의 팀 귀속**(사용자 지시 2026-10-07 §결장-귀속-2)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-07(멕시코–칠레): **멕시코** 선수 `Gilberto Mora` 의 결장이
    #     `team:000047`(칠레)에 붙어 `favors=home`·득점↑ 로 뒤집혔다.
    #  🔴 `team_reattached` 는 **고친 것**이다(버린 것이 아니다) — 카드 블록 1 이
    #     그 줄을 적는다. 나머지 둘은 **근거 불가**로 내린 사유다.
    TEAM_REATTACHED = "team_reattached"
    TEAM_UNRESOLVED = "team_unresolved"
    TEAM_AMBIGUOUS = "team_ambiguous"
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
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **킥오프 전인데 최종 스코어를 적는 글**(사용자 결정 2026-10-10 §6)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 경기 전 기사에 **결과 스코어가 적혀 있으면** 그 문서는 버린다
    #  > (`premature_result`).
    #
    #  ⚠️ 그런 글은 **다른 경기**의 결과이거나 예측 사이트의 모의 스코어다.
    #     🔴 그것을 사실로 읽으면 카드가 이미 끝난 경기를 분석하게 된다.
    PREMATURE_RESULT = "premature_result"
    # 🔴🔴 **선발 비중이 낮은 선수의 "선발 제외"**(같은 결정 §6)
    #
    #  > 선발 제외를 결장으로 보지 않는다 — 그 선수의 시즌 **선발 비율이 30%
    #  > 미만**이면. (실례: 가시와 세가와는 교체로 7골을 넣었다.)
    BENCH_REGULAR = "bench_regular"


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
    #: 🔴🔴 **버튼으로 고를 수 있는 후보**(§1-3 · 2026-10-10 재작성)
    #
    #  > 후보 2개 이상 → 텔레그램 버튼으로 고르게 한다(**리그·날짜·시각을 붙여서**).
    #  > 고르기 전에 분석하지 않는다.
    #
    #  칸: `key`(`games.ext_id` — 이것으로 못 박는다) · `home` · `away` ·
    #      `league` · `kst`(사람이 읽는 시각).
    #  ⚠️ `candidates`(글자)는 **그대로 둔다** — 버튼을 못 쓰는 자리(로그·도구)가
    #     그것을 읽는다(칸은 더하기만 한다).
    picks: list[dict] = Field(default_factory=list)


#: 🔴 결장 사유 — 축구 지시서 §2 표가 이름으로 댔다(자유 문자열 금지)
MissReason = Literal["injury", "suspension", "doubtful", "international_duty",
                     "other"]


class Player(Frozen):
    """🔴 선수 한 명 — **이름·포지션·등번호**(축구 완성 지시서 §2).

    ⚠️ 포지션을 못 읽으면 `pos=""` 다 — 지어내지 않는다(§1-1 의 결장 유형 결정이
       이 칸을 보고, 없으면 다수결로 간다).
    """

    name: str
    pos: str = ""
    number: int | None = None
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **세부 자리·측면·나이·시즌 레이팅** — 최종 평 §1-1
    # ══════════════════════════════════════════════════════════════
    #
    #  > 포지션 세부(GK·CB·LB·RB·…)와 **측면(왼/중앙/오른)**.
    #
    #  🔴 칸을 **더하기만** 한다(축구 완성 지시서 §2: 이름 바꾸기·빼기 금지).
    #  ⚠️ 못 읽으면 빈 글자·`None` 이다 — 가운데로 때우지 않는다(#3).
    spot: str = ""
    flank: str = ""
    age: int | None = None
    rating: float | None = None


class Missing(Frozen):
    """🔴🔴 **결장 명단 한 줄**(§2) — 기사에서만 건지지 않는다.

    🔴 실측 2026-10-06: fotmob 경기 페이지 `lineup.{home,away}Team.unavailable` 에
       이름·사유(`unavailability.type`)·복귀 예상(`expectedReturn`)이 **이미 있었다** —
       파서가 그것을 버리고 있었다(그래서 결장이 기사에서만 왔다).
    """

    name: str
    pos: str = ""
    reason: MissReason = "other"
    returns: str = ""
    source_url: str = ""
    #: 🔴 기사에서 온 것인가 — `article` 이면 등급을 **한 단계 낮춘다**(§2)
    source: Literal["page", "article"] = "page"


class Coach(Frozen):
    """🔴 감독(§2) — 이름·부임일·임시 여부."""

    name: str
    since: str = ""
    interim: bool = False


class XI(Frozen):
    """🔴 그 팀의 XI — 어댑터별 모양 차이는 `adapt.py` 가 흡수한다.

    🔴 축구 완성 지시서 §2: `players` 는 **이름+포지션+등번호**이고, `confirmed` 는
       **경기 페이지가 확정 표식을 줄 때만**이다(기사의 *"예상 선발"* 은 `predicted`).
    """

    team: TeamKey
    state: XIState
    formation: str | None = None
    #: ⚠️ 글자 목록은 **남겨 둔다** — 옛 호출부와 카드가 이름만 쓸 때가 있다
    players: list[str] = Field(default_factory=list)
    bench: list[str] = Field(default_factory=list)
    #: 🔴 포지션·등번호가 있는 꼴(§2) — 비면 이름만 받은 것이다
    lineup: list[Player] = Field(default_factory=list)
    source_url: str = ""
    fetched_at: datetime | None = None
    #: 🔴 예상 명단에서 **결장자를 뺀 사실**을 적는다(§2 충돌)
    conflicts: list[str] = Field(default_factory=list)


class Facts(Frozen):
    """🔴 s2 산출 — 구조 사실. ⚠️ **없으면 `None`**(지어내지 않는다 · §3).

    🔴 축구 완성 지시서 §2 가 칸을 더했다 — **이름 바꾸기·빼기는 금지**이고 더하기만
       한다(그 문서가 그렇게 못 박았다).
    """

    standings: dict = Field(default_factory=dict)
    #: 🔴 팀별 최근 N경기 스코어 목록
    recent: dict = Field(default_factory=dict)
    h2h: dict = Field(default_factory=dict)
    xi: dict[str, XI] = Field(default_factory=dict)
    #: 🔴🔴 **결장 명단**(§2) — 기사에서만 건지지 않는다
    missing: dict[str, list[Missing]] = Field(default_factory=dict)
    #: 🔴 감독(§2) — 이름·부임일·임시 여부
    coach: dict[str, Coach] = Field(default_factory=dict)
    #: 🔴 직전 경기 선발(IR02·IR06 용) — 로테이션·주전 이탈을 보려면 이것이 필요하다
    last_xi: dict[str, XI] = Field(default_factory=dict)
    #: 🔴🔴 **과거 경기 선발 여럿**(② 평소 XI · 사용자 승인 2026-10-06(5차) ②)
    #
    #  🔴 최신부터 최대 5경기다(`s2_facts.FOLLOW_CAP`). ⚠️ `last_xi` 는 그중 **첫
    #     번째**이고, 그 둘을 **따로 둔다** — IR02 는 직전 한 경기를 보고 ② 는 여러
    #     경기의 **선발 빈도**를 본다(§4-1). 섞으면 로테이션 한 번이 전력 급락이 된다.
    past_xi: dict[str, list[XI]] = Field(default_factory=dict)
    #: 🔴 일정(IR11 용) — 직전 경기 날짜·장소, 다음 경기 날짜
    schedule: dict = Field(default_factory=dict)
    #: 🔴🔴 **선수 → 포지션 표**(경기 단위 · §2) — §1-1 결장 유형과 IR01·IR02 가 쓴다
    player_pos: dict[str, str] = Field(default_factory=dict)
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **선수별 시즌 기록** — 최종 평 §1-1 의 *"비교 수치"*
    # ══════════════════════════════════════════════════════════════
    #
    #  `{이름: {goals, assists, rating, age, height, injury, role}}`
    #
    #  🔴 출처는 팀 **선수단 페이지**다(robots 허용 HTML · 팀당 한 번).
    #     ⚠️ `standings["key_players"]` 는 팀마다 **상위 2명**뿐이어서 교체된
    #        선수의 수를 못 댔다(실측 2026-10-10) — 그 칸이 이 표로 메워진다.
    #  ⚠️ 태클·가로채기·경합 승률·드리블·크로스는 **이 페이지에도 없다**
    #     (실측 2026-10-10: 선수 칸은 `goals·assists·rating·age·height·injury`
    #     뿐이다). 🔴 그래서 그 지표는 사실 묶음에서 **`없음`** 이다.
    player_stats: dict = Field(default_factory=dict)
    #: 🔴🔴 **소집 명단**(선발+교체 전원 · 사용자 지시 2026-10-06(4차) ①-b·②)
    #
    #  🔴 *"명단에 없음 = 결장, XI 에 없음 = 벤치"* — 그 둘을 가르는 자리다.
    squad: dict[str, list[str]] = Field(default_factory=dict)
    #: 🔴🔴 **선수 시장가치**(② 라인업 전력 · 네 층 지시서 §4-3)
    #
    #  🔴 출처는 **경기 페이지 안의 `marketValue`** 다(실측 2026-10-06 ·
    #     `config/rating_sources.yaml: fotmob_market_value`). ⚠️ 통화 표기가 응답에
    #     없어 **비율로만** 쓴다 — 카드에 통화 기호를 붙이지 않는다.
    player_value: dict[str, float] = Field(default_factory=dict)
    match_format: MatchFormat = "unknown"
    #: 🔴🔴 **그 경기의 fotmob 리그 id**(`general.parentLeagueId`) — 대회 판정의
    #
    #  ⚠️ 실사고 2026-10-10: 대회를 **글자**로만 판정하다 두 번 틀렸다.
    #     ① 엘살바도르 `Primera Division - Apertura` → 스페인 **라리가**
    #     ② 인도네시아 `Super League` → **스위스** 수퍼리그
    #     대회 이름은 **나라를 넘어 겹친다**. 🔴 번호는 겹치지 않는다.
    #  🔴 그래서 `s2_facts` 가 경기 페이지에서 읽어 여기 담고, `comp_kind` 가
    #     그것을 `competition.key_of` 에 넘긴다(판정점은 그대로 하나다).
    league_id: str = ""
    extra_time: bool | None = None
    #: 🔴 1차전/2차전(§3 IR07) — 모르면 `None`
    leg: int | None = None
    sources: list[str] = Field(default_factory=list)
    #: 🔴 **못 받은 칸을 이름으로**(§2) — 블록 1 이 칸별로 적는다(#3 조용한 0 금지)
    gaps: list[str] = Field(default_factory=list)


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
    #: 🔴 그 하위 과제 담당 유형만 — 요청마다 `enum` 으로 박는다(§4).
    #
    #  🔴 **가리기 규칙**(사용자 지시 2026-10-06(3차) ⑥): *"투입된다·선발로 나선다·
    #     골문을 맡긴다"* 는 `lineup_intent` 다. `coach_intent` 는 감독의 **의도**
    #     (점검·실험·전력 숨김), `coach_conflict` 는 감독·선수의 **갈등**이다.
    type: str
    #: 🔴 **그 경기 두 열쇠만** — 요청마다 `enum` 으로 박는다
    #
    #  🔴🔴 **`subject` 는 그 선수가 뛰는 팀이다**(사용자 지시 2026-10-07) —
    #     기사가 함께 언급한 **상대 팀이 아니다**.
    #  ⚠️ 실측 2026-10-07(멕시코–칠레): *"Gilberto Mora will miss Mexico's
    #     friendly against Chile"* 에서 모델이 **칠레**를 적었고, 그 탓에
    #     `favors` 가 뒤집혀 가설·시나리오가 *"상대 결장"* 으로 읽었다.
    #  🔴 코드가 **명단으로 대조해 고친다**(`s5_verify.team_of_player`) — 이 설명은
    #     그 앞단에서 틀릴 확률을 줄이는 자리다(둘 다 있어야 한다).
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
    #: 🔴🔴 **이 경기와 이어지는 근거**(사용자 지시 2026-10-06(4차) ①-b)
    #
    #  > 추출 스키마에 `match_link` 칸(문단에서 이 경기와 이어지는 근거 — 상대팀
    #  > 이름, 경기 날짜, 경기장, *"우즈벡전"* 같은 표현)을 **필수로** 넣는다.
    #  > 코드가 그 근거가 문단에 **실제로 있는지** 확인하고, 없으면 버린다(`off_match`).
    #
    #  ⚠️ 실측 2026-10-06: *"한국 남자축구 4연속 금메달"*·*"금메달 수 49로 급감"* 이
    #     A대표 친선 카드의 변수로 들어왔다 — 그 문단은 **이 경기 이야기가 아니다.**
    #  🔴 예외는 **선수 개인 상태**다(부상·피로·기록 도전): 그 선수가 이번 소집
    #     명단에 있으면 경기 연결로 **인정**한다(s5 가 명단으로 센다).
    match_link: str
    #: 🔴🔴 **기사가 말한 포메이션**(사용자 지시 2026-10-06(7차) §5 · 선택)
    #
    #  > 추출 스키마에 `formation`(선택)과 근거 문장. 경기 페이지에 **확정 XI 가
    #  > 없을 때만** `XI.formation` 으로 쓴다(`source=article`, soft).
    #  ⚠️ 비면 모른다는 뜻이다 — 지어내지 않는다.
    formation: str = ""
    #: 🔴 본문의 글자 **그대로** — s5 가 Doc 본문에 대고 맞춰 본다
    quote: str
    #: 🔴 어느 Doc 인가 — 요청마다 **그 하위에 넘긴 id 만** `enum` 으로 박는다
    doc_id: str


class VarCandidates(Frozen):
    """🔴 구조화 출력은 **object 로만** 받는다 — 최상위 배열은 스키마가 못 받는다."""

    variables: list[VarCandidate] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **예측 신호** — 순서 재편 지시서(2026-10-10 다섯째) §2-2
# ══════════════════════════════════════════════════════════════════
#
#  > 각 가설은 반드시 시뮬레이션으로 **확인할 수 있는 신호**를 단다:
#  > `{가설 문장, 근거 변수 id, 예측 신호 = 지표·방향·기준}`
#  > **쓸 수 있는 지표 목록은 코드가 준다** … 목록 밖 지표 금지.
#
#  🔴 지표 목록·읽는 법·대조는 `app/core/signals.py` 하나가 든다(사본 금지).


class Signal(Frozen):
    """🔴 예측 신호 하나 — **지표·방향·기준**. ⚠️ 확률을 **만들지 않는다**(읽는다)."""

    #: 🔴 허용 목록은 `signals.METRICS` 다 — 그 밖의 글자는 검열이 버린다
    metric: str
    #: 🔴 `>`·`<`·`>=`·`<=`
    direction: str
    #: 🔴 기준 — 수(`0.35`) 또는 `상대`·`리그평균`·`리그평균*0.7`
    ref: str
    #: 🔴 어느 팀 — `home`·`away`(승무패·오버는 빈 글자)
    side: str = ""
    #: 🔴 덧붙는 인자 — 구간(`61-90+`)·오버 줄(`2.5`)·스코어(`1-0`)·결과(`draw`)
    arg: str = ""


class HypoLine(Frozen):
    """🔴 가설 한 줄 — 문장 + **근거 변수 번호** + **예측 신호**(§2-2).

    ⚠️ 번호만 적으면 안 된다. 🔴 신호가 없으면 **검증할 수 없는 가설**이므로
       단계 4 가 `판단 불가` 로 세고 최종 평은 그것을 못 쓴다(§5).
    """

    text: str
    var_ids: list[str] = Field(default_factory=list)
    signal: Signal | None = None


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


class CommentLine(Frozen):
    """🔴 논평 한 문장 — **근거 변수 번호를 함께** 든다(지시 ③)."""

    text: str
    var_ids: list[str] = Field(default_factory=list)


class Commentary(Frozen):
    """🔴🔴 **종합 논평**(사용자 지시 2026-10-07 ③) — DeepSeek 1회 · 구조화 출력.

    🔴 코드가 검사하는 것(어긋나면 그 칸을 버리고 **1회 재요청**, 또 어긋나면 템플릿):
      · `title` 의 양상 = `Card.shape` 의 양상 — **논평이 숫자와 반대로 말하면 안 된다**
      · `score_range` 의 스코어가 **무게 상위 시나리오 스코어 안**에 있다
      · `reasons` 의 `var_ids` 가 **근거 가능 변수**만
      · `lean` 은 **보드에 실제로 있는 줄**만 · 등급과 다른 말 금지
      · 기대값·금액·켈리·**시장 확률을 근거로 쓰는 문장 금지**
    ⚠️ `lean` 이 비면 *"기울기 없음"* 이다 — 빈 값을 **추천으로 읽지 않는다**.
    """

    title: str
    reasons: list[CommentLine] = Field(default_factory=list)
    flow: str = ""
    score_range: list[str] = Field(default_factory=list)
    lean: str = ""


#: 🔴 검열 판정 — 사용자 지시 2026-10-07 §4-2 의 네 값 그대로
AuditVerdict = Literal["ok", "contradicts", "unsupported", "overclaim"]


class AuditLine(Frozen):
    """🔴 문장 하나에 대한 **검열자 판정**(Solar). ⚠️ 새 사실을 쓰지 않는다."""

    #: 🔴 몇 번째 문장인가(0 부터)
    index: int = 0
    verdict: AuditVerdict = "ok"
    #: 🔴 근거가 된 **사실 id**(없으면 빈 글자 — `null` 자리)
    fact_ref: str = ""
    #: ⚠️ 20자 이내(지시 §4-2) — 길면 코드가 자른다
    note: str = ""


class AuditOut(Frozen):
    """🔴 구조화 출력 — 최상위 배열은 스키마가 못 받는다(§4)."""

    lines: list[AuditLine] = Field(default_factory=list)


class ReasonLine(Frozen):
    """🔴🔴 1겹 **이유 문단의 한 문장**(사용자 지시 2026-10-09(3차) §3).

    > 출력: `{sentences: 3~5개, 각 문장 fact_refs(사실 id 1개 이상)}`

    🔴 `fact_refs` 는 **카드 사실의 id** 다 — 변수 id(`S02`·`IR02-home`)이거나
       `layer1.facts_catalog()` 가 짓는 id(`ABS:…`·`RANK:home`·`H2H`·`XI:home`…).
    ⚠️ 하나도 없으면 검열 (j) 가 **위반**으로 잡는다(근거 없는 문장 금지).
    """

    text: str
    fact_refs: list[str] = Field(default_factory=list)


class ReasonPara(Frozen):
    """🔴 1겹 【이유】 문단 — 문장 3~5개. ⚠️ 400자 상한은 렌더러가 센다(§5)."""

    sentences: list[ReasonLine] = Field(default_factory=list)


class ReasonOut(Frozen):
    """🔴 s8b 산출 — 이유 문단과 **검열 결과**. ⚠️ 단계 사이는 타입 하나다(§7)."""

    said: ReasonPara | None = None
    notes: list[str] = Field(default_factory=list)
    #: 🔴 `통과`·`재작성 후 통과`·`템플릿`·`안 돌았다`
    audit: str = "안 돌았다"
    violations: list[str] = Field(default_factory=list)


class CommentOut(Frozen):
    """🔴 s8 산출 — 논평과 **버린 칸 사유**. ⚠️ 단계 사이는 **타입 하나**다(§7)."""

    said: Commentary | None = None
    notes: list[str] = Field(default_factory=list)
    #: 🔴🔴 **검열 결과**(§4-3) — `통과`·`재작성 후 통과`·`템플릿`·`안 돌았다`
    audit: str = "안 돌았다"
    #: 🔴 검열이 **낮춘 양상**(§4-1 (d)) — 카드·논평이 같은 양상을 봐야 한다
    shape_used: dict = Field(default_factory=dict)
    #: 🔴 위반 종류들 — 카드에는 안 나간다(`/디버그` 와 기록용 · §4-4)
    violations: list[str] = Field(default_factory=list)


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


class StrategyLine(Frozen):
    """🔴🔴 §2-2 — **한 팀의 전략 판정**. ⚠️ 모델이 수치를 적을 칸은 **없다**.

    > 팀마다 `strategy` ∈ {공격 위주, 수비 위주(잠그기), 역습, 로테이션·체력
    > 관리, 실험, 평소 그대로} + **근거 사실 id 2개 이상** + 한 줄 이유.

    🔴 **확률 칸이 없다** — 이동량은 `config/strategy_effects.yaml` 과 코드가
       정한다(절대규칙 5: `direction`·`weight`·`strength`·`survival`·`verdict`
       에 LLM 출력이 닿으면 계약 실패).
    """

    side: Literal["home", "away"]
    #: 🔴 여섯 가지뿐이다 — `enum` 으로 박아 모델이 다른 말을 못 하게 한다
    #: 🔴🔴 `squad_turnover` 는 **코드만** 넣는다(사용자 지시 2026-10-10 지적 ③) —
    #  LLM 은 그 값을 못 고른다(프롬프트에 없다). 전역·이적으로 선수단이 바뀐
    #  팀의 판정이고, `로테이션·체력 관리` 를 **덮어쓴다**.
    strategy: Literal["공격 위주", "수비 위주", "역습",
                      "로테이션·체력 관리", "실험", "평소 그대로",
                      "squad_turnover"]
    #: 🔴 §2-2 — **근거 사실 id 2개 이상**(`app/core/strategy.py` 가 발급한 `L*`)
    fact_refs: list[str] = Field(default_factory=list)
    why: str = ""


class StrategyOut(Frozen):
    """🔴 s2d 산출 — 두 팀 전략 + 양상 + **코드 검사 결과**(§7 타입 하나)."""

    lines: list[StrategyLine] = Field(default_factory=list)
    #: 🔴 §2-3 — 코드가 정한 맞대결 양상(모델이 적지 않는다)
    shape: str = ""
    #: 🔴 `통과`·`버렸다`·`확정 XI 전`·`안 돌았다`
    audit: str = "안 돌았다"
    violations: list[str] = Field(default_factory=list)
    #: 🔴 §2-1 사실 — 카드·검열이 id 로 되찾는다
    facts: dict = Field(default_factory=dict)


class TacticLine(Frozen):
    """🔴🔴 §6 — **전술 예측 한 줄**. ⚠️ 모델이 수를 적을 칸은 **없다**.

    > 출력: 팀별 예상 운영, 예상 흐름(전반/후반), **승부처 1개**,
    > **문장마다 근거 id**.

    🔴 확률·λ 칸이 없다 — *"이야기(LLM 문장)는 확률을 움직이지 못한다"*(§4).
    """

    #: 🔴 `운영:home`·`운영:away`·`흐름:전반`·`흐름:후반`·`승부처`
    slot: Literal["운영:home", "운영:away", "흐름:전반", "흐름:후반", "승부처"]
    text: str
    #: 🔴 §6 — **문장마다 근거 id**(`L*`·`A*`·`T9`·`T1` …)
    refs: list[str] = Field(default_factory=list)


class TacticOut(Frozen):
    """🔴 s2f 산출 — 전술 예측 + **검열 결과**(§7 타입 하나)."""

    lines: list[TacticLine] = Field(default_factory=list)
    #: 🔴 `통과`·`재작성 후 통과`·`버렸다`·`확정 XI 전`·`안 돌았다`
    audit: str = "안 돌았다"
    violations: list[str] = Field(default_factory=list)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **최종 평** — 사용자 지시 2026-10-10(넷째) §2
# ══════════════════════════════════════════════════════════════════
#
#  > 출력 칸: `verdict` · `key_points`(3~5개, 각각 주장·메커니즘·근거 id 2개
#  > 이상) · `flow`(전반·후반) · `decisive_moment` · `flip_condition` ·
#  > `one_line`.
#
#  🔴 **확률 칸이 없다** — *"확률도 바꾸지 않는다(확률은 앞 단계가 이미 정했다)"*.


class KeyPoint(Frozen):
    """🔴 §2 — 핵심 주장 하나. ⚠️ **근거 id 2개 이상**이 계약이다(검열 (q))."""

    claim: str
    mechanism: str
    #: 🔴 §1 묶음의 id 들(`X3`·`G7`·`L2`·`T11` …) — 없는 id 면 검열이 버린다
    refs: list[str] = Field(default_factory=list)


class SayOut(Frozen):
    """🔴 s9say 산출 — **최종 평** + 검열 결과(§7 타입 하나)."""

    #: 🔴 §2 — 이길 팀 이름 · `무승부 쪽` · `반반`. 코드 방향과 같아야 한다((u))
    verdict: str = ""
    one_line: str = ""
    key_points: list[KeyPoint] = Field(default_factory=list)
    flow_first: str = ""
    flow_second: str = ""
    decisive_moment: str = ""
    flip_condition: str = ""
    #: 🔴 `통과`·`재작성 후 통과`·`템플릿`·`안 돌았다`
    audit: str = "안 돌았다"
    violations: list[str] = Field(default_factory=list)
    #: 🔴 긴 카드가 적는다 — `{id: 원 사실}`(검열이 쓴 그 묶음)
    used: dict = Field(default_factory=dict)
    #: 🔴 **버린 평**(검열이 두 번 잡은 글) — 긴 카드가 보인다(#3 추적 가능하게)
    dropped: list[str] = Field(default_factory=list)


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
    #: 🔴🔴 **실점 방향**(사용자 지시 2026-10-07 §3) — 득점과 **따로** 단다.
    #
    #  ⚠️ 폼 변수는 *"이 팀이 넣는 골"* 과 *"먹는 골"* 을 **둘 다** 말한다 — 한 칸에
    #     뭉치면 저득점 판정이 거짓이 된다(실측 2026-10-07 멕시코–칠레: 두 팀 보정
    #     득점이 0.667 인데 양상이 **난타전**으로 섰다).
    goals_against: Goals = "none"
    #: 🔴 그 사실의 핵심 대상 — **병합 열쇠**다(같은 subject·type·target = 한 사실)
    target: str = ""
    #: 🔴 이 경기와 이어지는 근거(①-b) — 기사 변수는 **비어 있을 수 없다**
    match_link: str = ""
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
    #: 🔴🔴 **어느 하위 과제가 나른 변수인가**(`F-home` 등) — 사용자 지시
    #  2026-10-10(재작성) §3-4 가 **🆕 새 사실(72시간)** 블록을 요구한다.
    #
    #  ⚠️ `Card` 에는 `docs` 칸이 **없다** — 그래서 문서를 거쳐 세려면 길이 없다.
    #     🔴 그래서 **변수가 자기 하위를 들고 간다**(칸은 더하기만 한다).
    #  ⚠️ 규칙으로 지은 변수(`from_rule`)는 **빈 글자**다(하위가 없다).
    subtask: str = ""
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
    """🔴 보드 한 줄.

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **배당 칸이 생겼다** — 네 층 지시서 §2-6(사용자 결정 2026-10-06)
    ══════════════════════════════════════════════════════════════════

    > 보드 파서는 배당을 **버리지 않고** `BoardLine.price` 에 담는다.
    > 배당 원숫자는 시장·사용자 보드 열에 **괄호로** 보인다.

    ⚠️ 이것은 CLAUDE.md 절대규칙 6(*"배당은 `research` 스키마에만"*)과 충돌한다 —
       🔴 **직접 지시가 이긴다.** 다만 쓰임은 **정보**로만이다:
         · `price` 로 **확률**을 만들어 카드에 나란히 보인다(§7 세 열)
         · 🔴 **기대값·손익분기·켈리·금액은 어디에도 없다**(§0 금지 · 계약이 잠근다)
         · 🔴 등급 계산에 `price` 가 직접 들어가지 않는다(§7 금지)
    """

    market: Market
    side: str
    point: float | None = None
    #: 🔴 소수 배당(1.01 이상). ⚠️ `None` 은 *"배당을 못 읽었다"* 다 — 0 이 아니다
    price: float | None = Field(default=None, ge=1.01)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **네 층 확률**(네 층 지시서 §1) — ①②③④ 가 전부 이 타입을 낸다
# ══════════════════════════════════════════════════════════════════


class ProbTriple(Frozen):
    """🔴 승·무·패 확률 — **합이 1.0** 이다(§1 공통 타입 · 불변식).

    ⚠️ 세 값을 따로 들고 다니다 합이 1 이 아닌 표를 카드에 실은 적이 있다(실측
       2026-10-06 이전 경로). 🔴 타입이 그것을 불가능하게 한다.
    """

    home: float = Field(ge=0.0, le=1.0)
    draw: float = Field(ge=0.0, le=1.0)
    away: float = Field(ge=0.0, le=1.0)

    @field_validator("away")
    @classmethod
    def _sums(cls, v: float, info) -> float:
        box = info.data
        got = float(box.get("home", 0.0)) + float(box.get("draw", 0.0)) + v
        if abs(got - 1.0) > 0.001:
            raise ValueError(f"합이 1.0 이 아니다({got:.4f}) — 세 열 불변식")
        return v


class ProbPair(Frozen):
    """🔴 두 갈래 마켓(핸디·총점·양팀득점) 확률 — **합이 1.0**."""

    side_a: float = Field(ge=0.0, le=1.0)
    side_b: float = Field(ge=0.0, le=1.0)

    @field_validator("side_b")
    @classmethod
    def _sums(cls, v: float, info) -> float:
        got = float(info.data.get("side_a", 0.0)) + v
        if abs(got - 1.0) > 0.001:
            raise ValueError(f"합이 1.0 이 아니다({got:.4f})")
        return v


class BaseProb(Frozen):
    """🔴 ① 기준 확률 — 두 팀 **기본 전력 차**만 본 승·무·패(§3).

    ⚠️ `probs` 가 `None` 이면 *"기준 없음"* 이고 카드의 그 열은 `—` 다. 🔴 사유를
       `why` 에 **이름으로** 적는다(조용한 0 금지).
    """

    probs: ProbTriple | None = None
    why: str = ""
    home_elo: float | None = None
    away_elo: float | None = None
    dr: float | None = None
    #: 🔴 어느 대회 유형 계수를 썼나 — 다른 유형을 빌려 쓰면 카드가 거짓말을 한다
    comp_kind: str = ""
    source: str = ""
    data_date: str = ""
    #: 🔴 `We`(Elo 기대 득점률) — 무승부를 못 나눌 때 **이것만** 보인다(§3-3)
    we: float | None = None


class LineupDelta(Frozen):
    """🔴 ② 선수별 기여 한 줄 — *"김민재 → 김태현: ΔS −0.31 → 한국 승 −4%p"*."""

    team: TeamKey
    out_name: str = ""
    in_name: str = ""
    delta_s: float = 0.0
    delta_home_pct: float | None = None
    estimated: bool = False
    #: 🔴🔴 **포지션**(사용자 지시 2026-10-06(6차) ③) — 같은 포지션끼리만 짝짓는다
    #
    #  ⚠️ 실측 2026-10-06: 센터백 김민재가 **공격수 황희찬**과 짝지어졌다. 그 짝은
    #     *"수비가 약해졌다"* 를 **공격 가치로** 재는 것이어서 뜻이 없다.
    #  🔴 짝이 없으면 `structural=True` 로 *"구조 변경"* 이라고 적는다(지어내지 않는다).
    pos: str = ""
    structural: bool = False


class AdjProb(Frozen):
    """🔴 ② 라인업 보정 — 오늘 XI 가 **평소 XI 보다** 얼마나 약/강한가(§4).

    ⚠️ `probs` 가 비면 보정을 **안 했다**는 뜻이고, 그래도 `why` 는 적는다.
    🔴 `moved` 가 False 면 환산 계수를 못 재서 **확률을 움직이지 않았다**(§4-5).
    """

    probs: ProbTriple | None = None
    why: str = ""
    deltas: list[LineupDelta] = Field(default_factory=list)
    #: 🔴 팀별 `ΔS`(로그 가치 합 차) · 평소 대비 전력 변화율
    delta_s: dict[str, float] = Field(default_factory=dict)
    strength_pct: dict[str, float] = Field(default_factory=dict)
    moved: bool = False
    #: 🔴 ② 가 돌았나 — 돌았으면 결장 계열 변수 무게가 0 이다(§4 마지막)
    measured: bool = False
    estimated_players: int = 0


class MarketQuote(Frozen):
    """🔴 ④ 한 마켓의 **업체 배당 한 묶음** — 디빅 전 원숫자다."""

    market: Market
    side: str
    point: float | None = None
    price: float = Field(ge=1.01)
    bookmaker: str = ""


class MarketProb(Frozen):
    """🔴 ④ 시장 확률 — 봇이 받은 배당을 **공정 확률**로(§2-5).

    ⚠️ 같은 마켓의 결과 배당이 **하나라도 빠지면** 그 마켓은 확률이 없다(§2-5).
    🔴 `vig` 는 업체 몫(역수 합 − 1)이고 마켓마다 적는다.
    """

    #: `(마켓, 쪽, 점)` → 공정 확률
    probs: dict[str, float] = Field(default_factory=dict)
    #: 🔴 승무패는 Shin 방식도 함께 보인다(§2-5)
    shin: dict[str, float] = Field(default_factory=dict)
    vig: dict[str, float] = Field(default_factory=dict)
    quotes: list[MarketQuote] = Field(default_factory=list)
    #: 🔴 "피나클" · "n개 업체 중앙값" · "단일 업체" · "사용자 보드"
    basis: str = ""
    source: str = ""
    captured_at: datetime | None = None
    why: str = ""
    #: 🔴 피드 사용량 — 카드 블록 1 이 적는다(§2-2)
    used: int | None = None
    limit: int | None = None


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
    #: 🔴 등급이 **왜 그런가** — §7 세 열 규칙이 내렸으면 그 사유가 여기 붙는다
    why: str = ""


class Judgement(Frozen):
    """🔴🔴 **s7 산출** — 마켓 대입·방향·결론·방아쇠가 **한 타입**이다(§3).

    ⚠️ 단계 함수가 `tuple` 을 돌려주면 받는 쪽이 꼴을 **외워야** 한다 — 그것이
       결함 ①의 뿌리였다(§7 정적 검사가 그 서명을 막는다).
    """

    evals: list[MarketEval] = Field(default_factory=list)
    #: 🔴🔴 **평가 줄의 출처**(사용자 지시 2026-10-07 ①) — `user_board`·`feed`·`none`
    #
    #  > 출처 순서: **사용자 보드 > 피드의 메인 라인 > 없음.**
    #  ⚠️ `none` 이면 그 표는 **참고**이고 등급은 전부 `보류` 다.
    board_source: str = "none"
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
    #: 🔴🔴 **평가 줄의 출처**(사용자 지시 2026-10-07 ①) — `user_board`·`feed`·`none`
    #
    #  > 출처 순서: **사용자 보드 > 피드의 메인 라인 > 없음.**
    #  ⚠️ `none` 이면 그 표는 **참고**이고 등급은 전부 `보류` 다.
    board_source: str = "none"
    direction: str = ""
    conclusion: str = ""
    triggers: list[str] = Field(default_factory=list)
    funnel: Funnel = Field(default_factory=Funnel)
    cost: Cost = Field(default_factory=Cost)
    #: 🔴 **이미 시작한 경기인가** — 그러면 등급이 없다(M97)
    started: bool = False
    #: 🔴🔴 **재분석에서 바뀐 것**(축구 완성 지시서 §4-4) — 비면 첫 분석이다
    #
    #  > 카드 맨 위에 `재분석 — 바뀐 것:` 한 블록: XI 상태(예상→확정), 새로 생긴·
    #  > 사라진 변수, 등급 변화, 방아쇠 중 걸린 것.
    changed: list[str] = Field(default_factory=list)
    #: 🔴 보드에서 **추가 옵션**으로 들어온 줄(§4) · 못 읽은 줄
    board_extra: list[str] = Field(default_factory=list)
    board_bad: list[str] = Field(default_factory=list)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **네 층 확률**(네 층 지시서 §8) — 블록 3c·7b 가 이것을 그린다
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 세 열을 **한 숫자로 합치지 않는다**(§1) — 나란히 둔다.
    base_prob: BaseProb = Field(default_factory=BaseProb)
    adj_prob: AdjProb = Field(default_factory=AdjProb)
    #: 🔴 피드에서 받은 시장 · 🔴 사용자 보드 시장 — **섞지 않는다**(§2-6 불변식)
    market: MarketProb = Field(default_factory=MarketProb)
    user_market: MarketProb = Field(default_factory=MarketProb)
    #: 🔴 ③ 우리 확률(시나리오 무게 비율) — 블록 9 방향 판정과 **같은 숫자**다
    our_prob: ProbTriple | None = None
    #: 🔴 §6 판정 글자(`세 열 일치`·`우리만 튄다`·…)와 그 설명 줄들
    compare: str = ""
    compare_lines: list[str] = Field(default_factory=list)
    tilt: list[str] = Field(default_factory=list)
    market_why: list[str] = Field(default_factory=list)
    #: 🔴 OCR 로 읽은 보드 **원문**(§2-6: 원문 그대로 보여 준다)
    ocr_text: str = ""
    #: 🔴🔴 **평가 줄의 출처**(2026-10-07 ①) — `user_board`·`feed`·`none`
    board_source: str = "none"
    #: 🔴🔴 **경기 양상**(2026-10-07 ②) — 양상·비중·가장 무거운 스코어 셋
    shape: dict = Field(default_factory=dict)
    #: 🔴🔴 **종합 논평**(2026-10-07 ③) — 없으면 `None`(그 사실을 카드가 적는다)
    commentary: Commentary | None = None
    #: 🔴 논평이 코드 검사에서 **버린 칸**과 사유(디버그 카드가 적는다)
    comment_notes: list[str] = Field(default_factory=list)
    #: 🔴🔴 **총평 검열 결과**(사용자 지시 2026-10-07 §4-3) — 카드 1겹에는 **통과한
    #  논평만** 나가고, 이 칸과 위반 목록은 `/디버그` 에만 보인다.
    comment_audit: str = "안 돌았다"
    comment_violations: list[str] = Field(default_factory=list)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **1겹 【이유】 문단**(사용자 지시 2026-10-09(3차) §1·§3)
    # ══════════════════════════════════════════════════════════════════
    #
    #  🔴 총평(`commentary`)과 **다른 글**이다 — 총평은 깊은 카드(📖 자세히)의
    #     것이고, 이것은 1겹의 첫 세 줄에서 읽히는 글이다.
    #  ⚠️ 비면 1겹이 **코드 템플릿 문단**을 쓴다(§4 마지막 줄).
    reason: ReasonPara | None = None
    reason_audit: str = "안 돌았다"
    reason_violations: list[str] = Field(default_factory=list)
    #: 🔴🔴 **경우의 수**(사용자 지시 2026-10-06(7차) §2) — 블록 3b 가 그린다
    #
    #  꼴: `{"cells": [...], "states": {팀: {state, why, margin}}, "verified": bool,
    #        "source": 규정 주소, "group": 표 이름, "remaining": 남은 경기 수,
    #        "other": [라운드 다른 경기], "final": 최종 확정인가}`
    #  ⚠️ 비면 *"경우의 수를 못 센다"* 다(순위표가 없다 — 지어내지 않는다).
    outlook: dict = Field(default_factory=dict)
    #: 🔴🔴 **확정 라인업 전략**(사용자 지시 2026-10-10(둘째) §2) — `StrategyOut`
    #
    #  ⚠️ 확정 XI 가 아니면 `audit="확정 XI 전"` 이고 카드가 그 사실을 적는다.
    strategy: StrategyOut | None = None
    #: 🔴 §4 — **잠정 확률**(전략을 반영하기 전). `our_prob` 가 **최종**이다.
    #
    #  🔴 둘이 같으면 전략이 확률을 못 움직인 것이고, 카드가 그것도 적는다.
    prob_before: ProbTriple | None = None
    #: 🔴🔴 **상성 세 축**(사용자 지시 2026-10-10(셋째)) — `s2e_matchup` 산출
    #
    #  칸: `form`(축1) · `profile`(축3 프로필) · `fired`(T9~T13) · `axis2_why` ·
    #      `share`(기여 분해) · `why`
    #  ⚠️ 못 모은 축은 **사유 글자**가 들어 있다(조용히 비우지 않는다).
    matchup: dict = Field(default_factory=dict)
    #: 🔴🔴 **전술 전문가 예측**(사용자 지시 2026-10-10(셋째) §6) — `TacticOut`
    #
    #  ⚠️ **글뿐이다** — 확률 칸이 없다(*"이야기는 확률을 움직이지 못한다"* §4).
    tactic: TacticOut | None = None
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **최종 평**(사용자 지시 2026-10-10 넷째) — 카드의 **마지막 단계**
    # ══════════════════════════════════════════════════════════════
    #
    #  🔴 확률을 다 센 **뒤**에 돈다(입력에 최종 확률이 든다) — 평은 글만 낸다.
    say: SayOut | None = None
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **가설 검증표**(순서 재편 지시서 2026-10-10 다섯째 §4-5)
    # ══════════════════════════════════════════════════════════════
    #
    #  `{"rows": […], "supported": […], "counts": {…}, "stale": …,
    #    "rerun": …, "why": …}` — `s6c_check.run` 이 돌려준 그 표다.
    #
    #  🔴 최종 평은 **`supported` 만** 쓴다(§5) · 1겹은 🧪 한 줄씩 상위 셋.
    check: dict = Field(default_factory=dict)
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **변수 배치**(상성 엔진 지시서 2026-10-10 여섯째 V-4)
    # ══════════════════════════════════════════════════════════════
    #
    #  `routing.VariableSet` — 변수마다 배치 자리(①축 ②검증 ③가설)를 든다.
    #  🔴 **확률에 닿는 길은 ① 뿐이다**(C7) · 긴 카드 `🔢 변수` 가 전부 보인다.
    #  ⚠️ `dataclass` 라서 pydantic 칸은 `Any` 다(타입은 그 파일이 든다).
    varset: Any | None = None
    #: 🔴🔴 **③ 이 움직인 양**(사용자 지시 2026-10-06(6차) ③) — 변수별 로그 오즈 이동
    #
    #  ⚠️ 비면 *"③ 이동 없음 — 우리 열 = 기준"* 을 적는다(빈 줄은 "안 봤다"와 같다).
    moves: list[dict] = Field(default_factory=list)


class LlmFail(Frozen):
    """🔴 LLM 이 답을 못 줬다 — **사유가 갈려 있다**(§4).

    ⚠️ 타임아웃·5xx·429·잘림·스키마는 **고칠 곳이 다르다**(망/서버/속도/입력/
       프롬프트). 하나로 묶으면 어디를 고칠지 못 고른다.
    """

    reason: DropReason
    detail: str = ""
    status: int | None = None
