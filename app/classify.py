"""§4 적용 — **수집한 사실에 유형·방향·가중치를 붙인다.**

사용자 지시 2026-10-02: *"⑧ 변수에 유형·방향·가중치 — 단계 5 코드 구현해라"* ·
*"게이트 판정은 나중에 다시 하기로 하고 8번 해라"*.

⚠️ §9 는 단계 4 게이트(지금 29%) 전에 단계 5 코드를 쓰지 말라고 한다. **사용자
   지시가 v4 보다 위다**(CLAUDE.md 첫 규약). 🔴 그래서 **지시받은 ⑧ 만** 짓는다 —
   §9 단계 5 의 나머지(세포 질문 매핑·`premise_check` 생성·반대 검색)는 짓지 않는다.
   → `docs/fable/questions/2026-10-02_stage5_partial.md`

## 🔴 이 파일이 지키는 것

| 규칙 | 어떻게 |
|---|---|
| 유형은 §4 표에 있는 것만 | `rules.variable_types()` 를 읽는다. 이름을 베끼지 않는다 |
| 방향은 §4 의 `direction_rule` 대로 | 유형마다 함수 하나. 규칙 원문을 독스트링에 인용 |
| 방향이 없으면 **배경** | §1 *"방향이 없는 사실은 배경이지 변수가 아니다"* |
| 총점 방향은 변수에 안 붙인다 | §4 — `total_hint` 유형은 배경으로 간다 |
| 가중치는 hardness 가 정한다 | `types.WEIGHT_OF`. 🔴 **표본이 작으면 hardness 를 깎는다** |
| 못 정하면 **사유를 남긴다** | `undecided` — 조용히 버리지 않는다 |
| LLM 이 닿지 않는다 | 이 파일은 순수 규칙이다(§17-c) |

## 🔴 표본 패널티는 **hardness 를 깎는다** (weight 가 아니다)

`types.Variable` 은 `weight == WEIGHT_OF[hardness]` 를 강제한다. 그래서 §4 의
`sample_weight`(1.0 / 0.7 / 0.4)를 weight 에 직접 넣으면 **스키마가 거부한다.**
⚠️ 그런데 그 셋은 `hard / likely / soft` 의 weight 와 **똑같다** — 즉 같은 규칙을
   hardness 로 말할 수 있다. 작은 표본은 **더 약한 주장**이므로 그것이 더 맞다.

## ⚠️ 발행 시각이 없는 사실은 §3 구조로 못 들어간다

`types.Variable`·`types.Background` 가 `published_at` 을 **필수**로 받는다. 그런데
순위표에는 발행 시각이 없다(fotmob 표·`standings/now` 둘 다). 🔴 **지어내지
않는다** — `Classified` 로 들고 있고 `to_variable()` 이 `None` 과 사유를 돌려준다.
그 자리를 §3 에 어떻게 둘지는 사용자 결정이다(위 questions 문서).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from app import rules
from app.types import WEIGHT_OF, Background, Direction, Hardness, Variable

logger = logging.getLogger(__name__)

#: hardness 를 약한 쪽으로 깎을 때 쓰는 순서. 🔴 원본은 `types.WEIGHT_OF` 다.
_LADDER = ("hard", "likely", "soft")


def _cap(hardness: str, floor: str) -> str:
    """`hardness` 를 `floor` 보다 세지 않게 깎는다. 🔴 올리지 않는다."""
    if hardness not in _LADDER or floor not in _LADDER:
        raise ValueError(f"모르는 hardness: {hardness!r} / {floor!r}")
    return _LADDER[max(_LADDER.index(hardness), _LADDER.index(floor))]


@dataclass
class Game:
    """분류에 필요한 경기 맥락. 🔴 **홈·원정을 알아야 방향을 못 뒤집는다.**"""

    home: str
    away: str
    sport: str = ""
    league: str = ""
    #: §4 `match_type` — 친선·단판 여부. 모르면 빈 문자열(지어내지 않는다)
    match_type: str = ""
    #: 🔴🔴 **팀 열쇠**(3단계 · `teamref`). 이름이 아니라 **이것**이 신원이다.
    #
    #  ⚠️ 비어 있으면 종전처럼 이름으로 가린다 — 그 사실이 사유에 남는다.
    home_id: str = ""
    away_id: str = ""

    def side_of(self, team: str | None) -> Direction | None:
        """이 팀이 홈인가 원정인가. 🔴 모르면 `None` — 아무 쪽에도 안 붙인다.

        ══════════════════════════════════════════════════════════════
        🔴 **ID 를 먼저 본다**(3단계 · 사용자 설계 2026-10-03)
        ══════════════════════════════════════════════════════════════

        > 이후 단계는 이름을 받지 않는다 … **비교에는 절대 안 쓴다.**

        ⚠️ 이름으로 가리면 언어가 갈릴 때 **방향이 통째로 뒤집힌다** — `柏レイソル`
           이 홈인데 `Kashiwa Reysol` 로 물으면 `None` 이 되고, 그 변수는 방향을
           잃는다(실측 2026-10-03 의 병이 여기까지 와 있다).
        🔴 열쇠를 알면 **글자를 안 본다.** 모를 때만 이름으로 떨어진다 —
           ⚠️ 그것은 **대체**이고, 열쇠가 둘 다 있으면 거기서 끝난다.
        """
        from app import verify
        t = (team or "").strip()
        if not t:
            return None
        if self.home_id or self.away_id:
            from app import teamref
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **이미 열쇠면 다시 풀지 않는다**(실측 2026-10-05)
            # ══════════════════════════════════════════════════════════
            #
            #  ⚠️ `teamref.key_of("team:000191")` 는 **빈 문자열**을 준다 —
            #     그 함수는 *이름*을 받는다(`team:000191` 은 이름표에 없다).
            #  🔴 그래서 에이전트가 **열쇠를 바르게 보냈는데** 방향이
            #     `None` 이 됐고, 그 변수들이 전부 `both` 로 떨어졌다.
            #  ⚠️ §8-1 이 *"열쇠로 비교한다"* 고 한 바로 그 자리에서 **열쇠를
            #     이름처럼 다뤘다** — 한 줄로 막는다.
            key = t if t.startswith(teamref.TEAM_KEY_PREFIX) else ""
            if not key:
                key, _why = teamref.key_of(t)
            if key:
                if key == self.home_id:
                    return "home"
                if key == self.away_id:
                    return "away"
                # 🔴 **열쇠가 둘 다 있는데 어느 쪽도 아니면 남의 팀이다.**
                #    ⚠️ 여기서 이름으로 한 번 더 보면 그 판단이 **무효가 된다** —
                #       열쇠가 아니라고 한 것을 글자가 뒤집는 꼴이다.
                if self.home_id and self.away_id:
                    return None
        if verify.mentions_team(self.home, t):
            return "home"
        if verify.mentions_team(self.away, t):
            return "away"
        return None

    def other(self, side: Direction | None) -> Direction | None:
        return {"home": "away", "away": "home"}.get(side or "")


@dataclass
class Classified:
    """§4 적용 결과 하나. 🔴 **세 갈래다 — 셋을 섞지 않는다.**

    | 갈래 | 뜻 | 어떻게 보이나 |
    |---|---|---|
    | **변수** | 유형·방향이 정해졌다 | `is_variable` 이 참 |
    | **배경** | 규칙이 *"방향 없음"으로 **판단**했다* | `why` 에 그 판단 · `undecided` 는 빈칸 |
    | **미결정** | 🔴 **자료가 없어 못 판단했다** | `undecided` 에 사유 |

    ⚠️ 배경과 미결정을 섞으면 *"규칙이 아니라고 했다"* 와 *"자료가 없었다"* 가
       구분되지 않는다 — 고칠 곳이 완전히 다르다(전자는 규칙, 후자는 수집).
    """

    text: str
    source_url: str
    hardness: Hardness
    type: str | None = None
    direction: Direction | None = None
    published_at: datetime | None = None
    #: 🔴 **왜 이 방향인가** — §4 규칙 원문을 인용한다. 없으면 감사할 수 없다
    why: str = ""
    #: 🔴 못 정한 사유. 조용히 버리지 않는다(§19-b-6)
    undecided: str = ""
    #: 🔴🔴 **누구에게 유리한가**(카탈로그 규칙이 정한 값) — 지시 2026-10-05.
    #   ⚠️ `direction` 과 다르다: `direction` 은 **한쪽**(`home`/`away`)이고
    #      `favors` 는 `both`·`goals_up` 같은 **규칙의 답**도 담는다.
    favors: str = ""
    #: 🔴 `published_at` 이 없을 때 **왜 없는지**(안 A — 스키마가 요구한다)
    dateless_reason: str = ""
    team: str | None = None

    @property
    def weight(self) -> float:
        """🔴 무게. ⚠️ **방향이 없으면 0** 이다 — 지시서 §1-2.

        ⚠️ 종전엔 `hardness` 만 봤다. 🔴 그러면 **배경 사실**이 `soft` 무게를
           들고 §5-a 묶음 합에 들어간다 — 실측 2026-10-04: 포르투갈 `A` 가
           근거 **4.8** 이었고 그 중 여섯이 *지난 경기 득점표*였다.
        🔴 *"나머지는 배경 사실(hardness 0, **strength 미반영**)로 내린다"* 가
           지시서의 문구이고, 그것이 **이 한 줄**이다.
        """
        if not self.direction:
            return 0.0
        return WEIGHT_OF[self.hardness]

    @property
    def is_variable(self) -> bool:
        return bool(self.type and self.direction and not self.undecided)

    def to_variable(self, vid: str) -> tuple[Variable | None, str]:
        """§3 `Variable` 로. 🔴 못 만들면 `(None, 사유)` — 지어내지 않는다."""
        if not self.is_variable:
            return None, self.undecided or "방향이 없다 — 배경이다"
        # 🔴 **발행 시각이 없어도 들어간다**(사용자 결정 2026-10-02 안 A).
        #    조건 둘을 채워야 한다: 사유를 적고, **soft** 로 내린다.
        #    §12-c-1 *"날짜를 못 읽는 자료는 soft 로만 남긴다"* 가 그 규칙이다.
        #    ⚠️ 순위표가 그 자리다 — `stakes`·`home_field` 가 거기서 나온다.
        hardness = self.hardness
        reason = ""
        if self.published_at is None:
            reason = (self.dateless_reason
                      or "발행 시각이 없는 자료다(순위표·표) — 지어내지 않는다")
            hardness = "soft"
        return Variable(
            id=vid, type=self.type, direction=self.direction,
            hardness=hardness, weight=WEIGHT_OF[hardness], text=self.text,
            source_url=self.source_url, published_at=self.published_at,
            dateless_reason=reason,
            is_premise=self.type in rules.premise_types()), ""

    def to_background(self, bid: str) -> tuple[Background | None, str]:
        """🔴 배경도 날짜 없이 들어간다 — 사유를 적는다(안 A)."""
        return Background(
            id=bid, text=self.text, source_url=self.source_url,
            published_at=self.published_at,
            dateless_reason=("" if self.published_at is not None
                             else (self.dateless_reason
                                   or "발행 시각이 없는 자료다"))), ""


# ══════════════════════════════════════════════════════════════════
# 🔴 유형별 방향 — §4 `direction_rule` 원문을 그대로 집행한다
# ══════════════════════════════════════════════════════════════════
#
# ⚠️ 각 함수의 독스트링 첫 줄에 **§4 규칙 원문**을 인용한다. 계약이 그 인용이
#    yaml 의 `direction_rule` 과 같은지 대조한다 — 구현이 규칙에서 멀어지면 빨개진다.


def _dir_stakes(val: dict, g: Game) -> tuple[Direction | None, str, str]:
    """걸린 팀 쪽 승리 방향.

    🔴 `splits_direction` — **양쪽이 서로 다른 것을 걸고 있으면 두 항목으로 나눈다**
       (사용자 지시 2026-10-02). ⚠️ 무동기는 변수를 만들지 않는다.
    """
    side = g.side_of(val.get("team"))
    if side is None:
        return None, "", "어느 팀의 순위인지 모른다"
    rank, played = val.get("rank"), val.get("played")
    if rank is None:
        return None, "", "순위를 못 읽었다"
    cut = val.get("playoff_cut")
    if cut is None:
        return None, "", ("플레이오프·강등 경계를 모른다 — 순위만으로는 "
                          "걸렸는지 못 판단한다(리그마다 다르다)")
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **`abs()` 가 경계 안쪽과 밖을 같게 봤다**(실측 2026-10-02)
    # ══════════════════════════════════════════════════════════════
    #
    #  소프트뱅크 **1위**(경계 3위)에 `|1-3| = 2 ≤ 2` 가 걸려 *"걸린 팀"* 이 됐다.
    #  🔴 1위는 안정이다 — 그것을 걸렸다고 보면 **없는 동기를 지어낸** 것이다.
    #  ⚠️ 거꾸로, 경계에서 **아주 먼 밖**(탈락 확정)도 무동기다 — 그 쪽은 전 판도 맞았다.
    #
    #  그래서 안과 밖을 **따로** 본다:
    #    경계 밖(rank > cut)   경계까지 2위 안이면 걸렸다 — 올라갈 수 있다
    #    경계 안(rank <= cut)  **경계 바로 위**(rank == cut)만 걸렸다 — 떨어질 수 있다
    #    그 밖                 무동기(배경)
    #  🔴 `2` 는 전 판이 쓰던 값을 그대로 둔다 — 새 숫자를 만들지 않았다.
    rank_i, cut_i = int(rank), int(cut)
    at_stake = (0 < rank_i - cut_i <= 2) or (rank_i == cut_i)
    if not at_stake:
        # 🔴 **규칙이 "아니다"라고 판단한 것은 배경이다** — 미결정이 아니다.
        #    미결정은 *자료가 없어 못 판단한* 경우뿐이다.
        where = "안쪽으로 안정" if rank_i < cut_i else "밖으로 멀다"
        return None, (f"§4 stakes — {rank}위, 경계 {cut}위 기준 {where} "
                      f"(무동기로 본다)"), ""
    return side, (f"§4 stakes '걸린 팀 쪽 승리 방향' — {val.get('team')} "
                  f"{rank}위, 경계 {cut}위, {played}경기 소화"), ""


def _dir_home_field(val: dict, g: Game) -> tuple[Direction | None, str, str]:
    """홈 팀 쪽.

    🔴 사용자 지시 2026-10-02 로 더한 유형. 실측: MLS 홈 승률 +16.8%p·득점 +0.46골.
    ⚠️ 쪼갠 표가 없으면 변수를 만들지 않는다.
    """
    # 🔴🔴 **중립 구장이면 홈이 없다**(사용자 지시 2026-10-02 · 라이브가 찾았다).
    #
    #  실측: 아시안게임 한국 vs 중국(시즈오카) — 양 팀 다 홈이 아니다. 그런데 이 규칙은
    #  *"홈 팀 쪽"* 으로 방향을 민다 → **거짓 변수**다. 그 경기는 순위표가 없어 우연히
    #  안 섰다. 🔴 우연에 기대지 않는다. 규정은 `config/league_rules.yaml` 이 들고 있다.
    neutral, why_n = rules.neutral_venue(g.league)
    # 🔴🔴 **잰 값이 선언보다 구체적이다**(사용자 지적 2026-10-03). 선언은 리그 단위고
    #    이것은 **그 경기**다 — 친선처럼 선언이 없는 리그를 선언만으로는 못 가른다.
    #    ⚠️ 선언이 중립이라고 하면 그대로 중립이다(둘 중 하나라도 참이면 중립).
    if val.get("neutral_venue"):
        neutral = True
        why_n = str(val.get("neutral_why") or "구장 나라가 홈팀의 나라가 아니다")
    if neutral:
        return None, f"§4 home_field — 중립 구장이라 홈이 없다({why_n})", ""
    ha = val.get("home_advantage")
    if not ha:
        return None, "", "홈/원정 쪼갠 표가 없다 — 홈 우위를 재지 못했다"
    d = ha.get("win_pct_delta")
    if d is None:
        return None, "", "홈 우위를 못 읽었다"
    if d <= 0:
        return None, f"§4 home_field — 이 리그는 홈 우위가 없다({d}%p)", ""
    # 🔴 **득점을 못 잰 리그가 있다**(야구 순위표) — `+None골` 로 찍지 않는다
    gd = ha.get("goals_delta")
    goals = f"득점 +{gd}골 · " if gd is not None else "득점은 표에 없다 · "
    return "home", (f"§4 home_field '홈 팀 쪽' — 리그 홈 승률 +{d}%p · "
                    f"{goals}{ha.get('home_games')}경기"), ""


def _dir_absence(val: dict, g: Game) -> tuple[Direction | None, str, str]:
    """결장 팀 반대 방향."""
    side = g.side_of(val.get("team"))
    if side is None:
        return None, "", "누가 결장하는지(어느 팀) 모른다"
    who = val.get("player") or val.get("player_name") or "이름 미상"
    return g.other(side), (f"§4 absence '결장 팀 반대 방향' — "
                           f"{val.get('team')} {who}"), ""


#: 🔴 **배경으로 내린 사실들** — 지시서 §1-2. ⚠️ 조용히 버리지 않는다(#3):
#   독자가 *"왜 저 선수 얘기가 없나"* 를 물을 수 있어야 한다.
BACKGROUND_NOTE: list[str] = []


def _dir_individual(val: dict, g: Game) -> tuple[Direction | None, str, str]:
    """개인 팀 쪽.

    🔴 기록이 있는 선수만 변수가 된다 — 0골 0도움은 방향을 못 민다.
    """
    side = g.side_of(val.get("team"))
    if side is None:
        return None, "", "어느 팀 선수인지 모른다"
    g_, a_ = val.get("goals") or 0, val.get("assists") or 0
    sg = val.get("season_goals")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **득점·도움 수는 변수가 아니다** — 지시서(오픈월드) §1-2 (2026-10-05)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > `individual` 은 **타이틀 경쟁·연속 기록·복귀·이정표**(은퇴·기록 직전)
    #  > 처럼 **결과에 작동할 때만** 인정하고, 나머지는 **배경 사실**
    #  > (hardness 0, strength 미반영)로 내린다. 포르투갈 카드의
    #  > **R3~R8·R10·R11** 이 이 경우다. — 사용자 지시서 §1-2
    #
    #  ⚠️ 종전 기준은 *"그 경기에서 골·도움을 남겼다"* 였다(①). 🔴 실측
    #     2026-10-04: 그 하나로 **여덟 개**가 변수가 됐고(`Cancelo 1골`…),
    #     §5-a 묶음 weight 를 부풀려 `A` 가 근거 **4.8** 이 됐다 —
    #     *"이기는 이유"* 가 **지난 경기 득점표 나열**이 된다.
    #  🔴 §4 가 든 보기는 *"손흥민 58골 · 기시 41세 계약 · 차나팁 베트남전 2골
    #     이력"* — **이정표·타이틀 경쟁**이고 한 경기 1골이 아니다.
    #
    #  ✅ 변수가 되는 넷(지시서가 이름을 댔다):
    #       타이틀 경쟁   `top_scorer` · `season_goals` 가 선두권
    #       연속 기록     `streak_games`
    #       복귀         `returning`
    #       이정표       `milestone`(은퇴·기록 직전)
    works = [k for k in ("top_scorer", "streak_games", "returning",
                         "milestone") if val.get(k)]
    if not works:
        # 🔴 규칙이 **"결과에 작동하지 않는다"** 고 판단한 것이므로 **배경**이다.
        #    ⚠️ 버리지 않는다 — 사유를 글로 남겨 카드가 배경으로 적는다(#3).
        said = (f"§4 individual — **배경 사실**이다(지시서 §1-2): "
                f"{val.get('player')} {g_}골 {a_}도움"
                + (f" · 시즌 {sg}골" if sg is not None else "")
                + " — 득점·도움 수는 변수가 아니다"
                  "(타이틀 경쟁·연속 기록·복귀·이정표만 변수다)")
        BACKGROUND_NOTE.append(said)
        return None, said, ""
    marks = {"top_scorer": "팀 최다 득점자", "streak_games": "연속 기록",
             "returning": "복귀", "milestone": "이정표"}
    how = " · ".join(f"{marks[k]}" + (f"({val[k]})" if val[k] is not True
                                      else "") for k in works)
    return side, (f"§4 individual '개인 팀 쪽' — {val.get('player')} · {how}"
                  + (f" · 시즌 {sg}골" if sg is not None else "")), ""


def _dir_travel(val: dict, g: Game) -> tuple[Direction | None, str, str]:
    """피로 팀 반대.

    🔴 **양 팀 휴식일을 비교해야 한다.** 한쪽만 알면 누가 피로한지 모른다.
    ⚠️ 하루 차이는 피로로 보지 않는다 — `rest_gap_min` 이 문턱이다.
    """
    mine, theirs = val.get("rest_days"), val.get("opponent_rest_days")
    side = g.side_of(val.get("team"))
    if side is None:
        return None, "", "어느 팀의 휴식일인지 모른다"
    if mine is None or theirs is None:
        return None, "", "양 팀 휴식일을 둘 다 알아야 비교할 수 있다"
    gap = int(theirs) - int(mine)
    if abs(gap) < REST_GAP_MIN:
        return None, (f"§4 travel_schedule — 휴식일 차 {abs(gap)}일, 문턱 "
                      f"{REST_GAP_MIN}일 미만이라 피로로 보지 않는다"), ""
    tired = side if gap > 0 else g.other(side)
    return g.other(tired), (f"§4 travel_schedule '피로 팀 반대' — "
                            f"{val.get('team')} {mine}일 vs 상대 {theirs}일"), ""


#: 🔴 휴식일 차 문턱(일). 하루 차이는 피로로 보지 않는다.
#   ⚠️ 이 값은 **사용자 결정 대기**다 — 실측으로 정할 자료가 아직 없다.
REST_GAP_MIN = 2


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **어댑터마다 폼의 꼴이 다르다** (실측 2026-10-04)
# ══════════════════════════════════════════════════════════════════
#
#  실측(밀워키 브루어스 vs 샌디에이고 파드리스 · MLB): 깊이 소스가 폼을 **받아
#  왔는데** 분류기가 *"최근 **0경기**, 3경기 미만은 패턴이 아니다"* 라고 했다.
#
#      어댑터가 낸 것: `games=18 · last_game=2026-09-30 · recent=[{...}×5]`
#      분류기가 읽은 것: `val["last5"]` → 🔴 **없다**
#
#  🔴 `last5`(`['W','D','L',…]`)를 내는 것은 **`fotmob` 하나**다(실측 전수 조사).
#     `mlb`·`nhl` 은 `recent=[{date, home, away, home_score, away_score, state}]`
#     꼴이고, `npb`·`kbo`·`kleague`·`fdorg`·`espn` 은 폼 사실 자체가 없다.
#
#  ⚠️ 즉 **야구·하키 경기는 `recent_pattern` 변수를 한 번도 못 만들었다.**
#     그 하나가 빠지면 §7 R5(변수 3개·방향 2종)가 거의 늘 자료 부족이 된다 —
#     실측에서 변수가 **1개**였고 시나리오가 아예 안 만들어졌다.
#
#  🔴 **지어내는 것이 하나도 없다** — `W/D/L` 은 그 행의 스코어에서 **계산된다**.
#     ⚠️ `state == "Final"` 인 행만 센다(예정 경기를 승패로 읽으면 거짓이 된다).
#  🔴 고치는 자리를 **여기 하나로** 둔다 — 어댑터마다 `last5` 를 따로 만들면
#     새 어댑터가 또 빠진다(#1 사본 금지 · #2 배선).

#: 🔴 끝난 경기를 뜻하는 말들. ⚠️ 어댑터가 주는 글자를 그대로 적는다(실측):
#   MLB statsapi `abstractGameState` → `"Final"` · NHL `gameState` → `"OFF"`·`"FINAL"`
FINAL_WORDS = ("final", "off", "완료", "종료")


def _same_team(a: str, b: str) -> bool:
    """🔴 두 이름이 **같은 팀**인가 — 이름표 열쇠로 가린다(3단계).

    ⚠️ 열쇠를 **둘 다** 얻어야 열쇠로 가린다. 한쪽이라도 못 풀면 글자 비교로
       떨어지고, 그때는 **정확히 같아야** 한다(부분 일치로 넓히지 않는다).
    """
    x, y = str(a or "").strip(), str(b or "").strip()
    if not x or not y:
        return False
    try:
        from app import teamref
        kx, _ = teamref.key_of(x)
        ky, _ = teamref.key_of(y)
    except Exception:                                   # noqa: BLE001
        return x == y
    if kx and ky:
        return kx == ky
    return x == y


def last5_of(val: dict) -> tuple[list[str], str]:
    """🔴 폼 사실 → `['W','D','L',…]` 와 **어디서 나왔나**.

    ⚠️ `last5` 가 있으면 **그것이 이긴다**(fotmob 이 직접 준다 — 계산이 아니다).
    🔴 없으면 `recent` 행의 **스코어로 계산한다.** 못 계산하면 빈 목록이고,
       호출부가 §7 R7 로 *"패턴이 아니다"* 라고 적는다(지어내지 않는다).
    """
    got = [str(x).upper() for x in (val.get("last5") or []) if str(x).strip()]
    if got:
        return got, str(val.get("last5_how") or "어댑터가 줬다(`last5`)")
    # ⚠️ **대체 경로를 남겨 둔다** — 아직 `last5` 를 안 내는 어댑터가 있을 수
    #    있다(npb·kbo·kleague·fdorg 는 폼 사실 자체가 없다). 🔴 그 경우에도
    #    **정본 이름으로만** 읽는다(§8-3) — 어댑터 고유 칸을 더 보지 않는다.
    rows = [r for r in (val.get("recent") or []) if isinstance(r, dict)]
    if not rows:
        return [], "폼 사실에 `last5` 도 `recent` 도 없다"
    team = str(val.get("team") or "").strip()
    if not team:
        return [], "`recent` 는 있는데 **어느 팀인지** 없다 — 승패를 가릴 수 없다"
    out: list[str] = []
    skipped = 0
    for r in rows:
        state = str(r.get("state") or "").strip().lower()
        if not any(w in state for w in FINAL_WORDS):
            skipped += 1
            continue            # 🔴 예정·중단 경기는 승패가 없다
        home, away = str(r.get("home") or ""), str(r.get("away") or "")
        # 🔴 **같은 접근자**를 쓴다 — 두 곳이 각자 칸 이름을 적으면 갈린다
        hs, as_ = score_of(r)
        if hs is None or as_ is None:
            skipped += 1
            continue
        # ══════════════════════════════════════════════════════════
        # 🔴🔴 **우리가 홈이었나 — 열쇠로 가린다**(3단계 · 계약이 잡았다)
        # ══════════════════════════════════════════════════════════
        #
        #  ⚠️ 첫 판은 `team == home` 이었다 — **이름끼리 비교**다. 같은 어댑터가
        #     양쪽을 주니 실제로는 맞았지만, `tests/test_identity_contract.py` 가
        #     빨개졌고 **그것이 옳다**: 이 저장소가 그 병으로 네 번 다쳤다.
        #  🔴 열쇠로 가리면 `밀워키 브루어스`(질문)와 `Milwaukee Brewers`(어댑터)가
        #     **같은 팀**이 된다 — 이름표가 하는 일이 바로 그것이다.
        #  ⚠️ 열쇠를 못 얻으면 **글자가 정확히 같을 때만** 받는다(부분 일치 금지 —
        #     `Chicago` 가 `Chicago Cubs` 와 `Chicago White Sox` 를 다 집는다).
        if _same_team(team, home):
            mine, theirs = hs, as_
        elif _same_team(team, away):
            mine, theirs = as_, hs
        else:
            skipped += 1
            continue
        out.append("W" if mine > theirs else ("L" if mine < theirs else "D"))
    why = (f"`recent` {len(rows)}행에서 스코어로 계산했다 → {len(out)}경기"
           + (f" (건너뜀 {skipped}행 — 끝나지 않았거나 스코어·팀명이 안 맞는다)"
              if skipped else ""))
    return out, why


def _dir_recent(val: dict, g: Game) -> tuple[Direction | None, str, str]:
    """패턴 방향.

    🔴 **승패 흐름만 방향을 민다.** 득점·실점 패턴은 총점이고 §4 는 *"총점 방향은
       변수에 붙이지 않는다"* 고 했다 → 배경으로 간다.
    """
    side = g.side_of(val.get("team"))
    if side is None:
        return None, "", "어느 팀의 폼인지 모른다"
    # 🔴 **어댑터 꼴을 한 곳에서 고른다**(위 `last5_of` 머리글 · 2026-10-04)
    last5, how = last5_of(val)
    if len(last5) < RECENT_MIN:
        # 🔴 §7 R7 — *"표본 2경기로 정하지 않는다."* 규칙이 배제한 것이므로 배경
        #    ⚠️ **어디서 왔나를 함께 적는다** — *"0경기"* 만 적으면 자료가 안 온
        #       것인지 못 읽은 것인지 알 수 없다(CLAUDE.md #3).
        return None, (f"§7 R7 — 최근 {len(last5)}경기, {RECENT_MIN}경기 미만은 "
                      f"패턴이 아니다 — {how}"), ""
    w, l = last5.count("W"), last5.count("L")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **연속 패턴을 함께 적는다** (사용자 지적 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 파라과이 **원정 8경기 연속 득점** / 콜롬비아 **최근 2경기 무승**
    #
    #  `W/D/L` 다섯 글자로는 못 세는 것이다. `_form_sequence` 가 **스코어 수열**을
    #  내고 `_form_streaks` 가 연속을 센다(fotmob 이 이미 주던 칸이다).
    #  ⚠️ 🔴 **방향은 승패 흐름이 정한다** — 연속 득점은 **총점 쪽** 신호이고 §4 가
    #     *"총점 방향은 변수에 안 붙인다"* 고 했다. 그래서 연속은 **사유에만** 적고
    #     방향을 바꾸지 않는다. 적지 않으면 그 사실이 카드에서 사라진다.
    bits = []
    for key, word in (("streak_winless", "무승"), ("streak_unbeaten", "무패"),
                      ("streak_away_scored", "원정 연속 득점"),
                      ("streak_clean_sheet", "연속 무실점")):
        n = val.get(key)
        if n:
            bits.append(f"{word} {n}경기")
    tail = (" · " + " · ".join(bits)) if bits else ""
    if w == l:
        return None, (f"§4 recent_pattern — 최근 {len(last5)}경기 {w}승 {l}패, "
                      f"흐름이 갈려 방향이 없다{tail}"), ""
    return (side if w > l else g.other(side)), (
        f"§4 recent_pattern '패턴 방향' — {val.get('team')} "
        f"최근 {len(last5)}경기 {w}승 {l}패 ({'·'.join(last5)}){tail}"), ""


#: §7 R7 — *"표본 2경기로 정하지 않는다."* 🔴 3경기 미만은 패턴이 아니다.
RECENT_MIN = 3
#: §7 R7 — 3경기 미만이면 weight 0.4 강제. hardness 로 말하면 `soft` 다.
RECENT_SOFT_UNDER = 3


def forfeit_rows(rows: list) -> tuple[list, list]:
    """🔴🔴 **M17 — 몰수 경기를 뺀다.** `(남은 행, 뺀 행)`.

    ⚠️ 몰수(forfeit)는 **경기가 아니다** — 공식 스코어(야구 9-0)가 실제로
       일어난 일이 아니다. 🔴 맞대결 통계에 넣으면 평균이 거짓이 된다.
    🔴 표기 글자는 **yaml 이 정한다**(`h2h_pattern.forfeit_marks`) — 코드가
       짐작하지 않는다.
    ⚠️ **못 걸러낼 수도 있다**: 자료가 몰수를 표기하지 않으면 우리는 모른다.
       🔴 그때 *"없다"* 가 아니라 **"못 쟀다"** 다 — 호출부가 그 사실을 적는다.
    """
    marks = [str(x).lower() for x in
             ((rules.variable_types().get("h2h_pattern") or {})
              .get("forfeit_marks") or [])]
    if not marks:
        return list(rows or []), []
    keep, dropped = [], []
    for r in (rows or []):
        blob = " ".join(str(v) for v in (r.values() if isinstance(r, dict)
                                         else [r])).lower()
        (dropped if any(m in blob for m in marks) else keep).append(r)
    return keep, dropped


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **v5 §5-4 — 에이전트 변수 → 판정층 변수**(게이트 2 의 다리)
# ══════════════════════════════════════════════════════════════════
#
#  > 에이전트의 `direction_hint` 는 **참고다.** 코드가 방향 규칙으로 **다시
#  > 정한다.** … 양방향 유형은 **두 항목으로 나눈다**. 홈/원정 기록은 오늘
#  > 경기의 홈/원정에 맞는 것만 쓴다(원정 기록을 홈팀 변수로 쓰면
#  > `side_mismatch`).
#
#  🔴 왜 다리가 필요한가: 두 경로가 **다른 꼴**을 낸다.
#
#      규칙 경로   `Classified`  → 판정층(§6)
#      에이전트     `AgentVar`    → **여기를 지나야** 판정층에 닿는다
#
#  ⚠️ 안 지나면 에이전트는 토큰만 쓰고 **카드를 안 바꾼다**(§1 이 막는 것이다).
#  🔴 절대규칙 5 — `direction`·`weight`·`strength` 에 **LLM 출력이 닿지 않는다.**
#     모델이 주는 것은 **사실과 인용**이고, 쪽과 무게는 **코드가** 준다.


def _both_way_types() -> list[str]:
    """🔴 §5-4 가 이름 댄 **양방향 유형**. ⚠️ 우리 §4 이름으로 읽는다.

    지시문은 `coach_crisis`·`event_match`·`lineup_rotation` 이라 적었고 §4 의
    우리 이름은 `coach_conflict`·`event_match`·`squad_rotation` 이다 —
    그 대응은 `config/trigger_conditions.yaml` 의 `v5_names` 가 든다(사본 금지).
    """
    said = (rules.required_forms().get("양방향_변수") or {}).get("types") or []
    return [str(x) for x in said]


#: 🔴 `stakes` 가 **확정·탈락 확정**을 말하는지 — 그러면 동기가 **상대**에 있다.
#
#  ⚠️ 낱말을 여기 적는 것이 사본인가? **아니다** — 이것은 *"이 문장이 확정을
#     말하나"* 를 읽는 **판정**이고, `variable_types.yaml` 의 `match`(그 유형인가)
#     와 **다른 질문**이다. 🔴 그래도 한 곳에만 둔다.
#  🔴 실측 2026-10-05: *"Portugal has secured a spot in the quarterfinals"* 가
#     **포르투갈 근거**로 들어갔다 — 8강을 확정한 팀은 **동기가 낮다.**
#: 🔴🔴 **묶음으로 볼 길이** — 실측 2026-10-05 (프랑스–벨기에).
#  ⚠️ 실사고: `R4` 의 글이 **+617자**였다 — 터키 원정 1-0, 벨기에전 1-0,
#     이탈리아전 1-1, 경기장까지 **한 덩어리**. 변수 하나 = 사실 하나가 깨지면
#     방향·hardness 가 **무엇에 붙은 것인지** 알 수 없다.
#  🔴 버리지 않는다(쓸 사실이 들어 있다) — 카드가 **그 사실을 표시**한다.
#  ⚠️ 수를 어떻게 골랐나: 카드 변수 줄의 표시 한도가 190자다(`var_line`).
#     그 두 배를 넘으면 한 줄로 읽을 수 없는 묶음이다.
LUMP_CHARS = 380


#: 🔴 **무패를 뜻하는 낱말** — 기사가 쓰는 말이다(사전이지 사실이 아니다).
#  ⚠️ 이 목록에 없는 표현은 **안 센다** — 늘릴 때도 실측으로 늘린다.
UNBEATEN_WORDS: tuple[str, ...] = (
    "unbeaten", "no defeat", "without defeat", "perfect record",
    "won all", "무패", "전승", "지지 않", "패배 없")


def clash_with_form(said: object, last5: object) -> str:
    """🔴🔴 **그 주장이 폼 기록과 어긋나나** — 지시 ⑨ (실측 2026-10-05).

    ⚠️ 실사고: 카드가 `France last5 ['L','L','W','W','D']` 를 적고, 같은 카드의
       변수가 *"France have an **unbeaten** start"* 를 적었다. **둘 다 있고
       어느 쪽도 그 어긋남을 말하지 않았다.**
    🔴 **어느 쪽이 맞는지 고르지 않는다** — 정답은 경기 결과가 말한다
       (사용자 지시 2026-10-02). 여기서는 *"어긋났다"* 만 적는다.
    ⚠️ `last5` 가 없으면 **아무 말도 하지 않는다** — 지어내지 않는다(#4).
    """
    rows = [str(x).strip().upper() for x in (last5 or []) if str(x).strip()]
    if not rows:
        return ""
    low = str(said or "").lower()
    hit = [w for w in UNBEATEN_WORDS if w.lower() in low]
    if not hit:
        return ""
    lost = [x for x in rows if x.startswith("L")]
    if not lost:
        return ""
    return (f"🔴 **어긋난다** — 이 글은 `{hit[0]}`(무패)라고 하는데 최근 "
            f"{len(rows)}경기에 패배가 {len(lost)}번 있다({'·'.join(rows)}). "
            f"⚠️ 어느 쪽이 맞는지는 **고르지 않는다** — 대회만 센 것일 수 있다")


def is_lump(said: object) -> bool:
    """🔴 그 변수 글이 **여러 사실 묶음**인가 — 길이로 본다(실측 2026-10-05)."""
    return len(" ".join(str(said or "").split())) > LUMP_CHARS


SETTLED_WORDS: tuple[str, ...] = (
    "secured", "already qualified", "qualified for", "booked their",
    "clinched", "confirmed their place", "through to", "eliminated",
    "knocked out", "cannot qualify", "확정", "탈락", "진출 확정",
)


def favors_of(kind: str, *, subject: str, game: "Game", text: str = "") -> str:
    """🔴🔴 **누구에게 유리한가** — 카탈로그 규칙으로 **코드가** 정한다.

    사용자 지시 2026-10-05:

    > `favors` 는 **코드가 catalog 방향 규칙으로 계산**한다:
    >   - `absence`: favors = **상대**
    >   - `stakes`: 이미 확정·탈락 확정 팀 → favors = **상대**(동기 비대칭).
    >     결과가 필요한 팀 쪽이 근거.
    >   - `coach_conflict`·`event_match`·`squad_rotation`: **both**
    >   - 규칙 없는 유형은 **both**

    돌려주는 것은 `"home"`·`"away"`·`"both"`·`"goals_up"`·`"goals_down"`·`""`.

    ⚠️ **모델 힌트를 보지 않는다** — 그것이 거꾸로였기 때문에 이 함수가 있다.
    """
    from app import rules
    said = str((rules.variable_types().get(str(kind)) or {}).get("favors")
               or "both")
    side = game.side_of(subject)
    # 🔴 `stakes` 는 **문장이 확정을 말하면 뒤집힌다**(동기 비대칭)
    if str(kind) == "stakes" and side in ("home", "away"):
        low = " ".join(str(text or "").lower().split())
        if any(w.lower() in low for w in SETTLED_WORDS):
            said = "opponent"
    if said == "both":
        return "both"
    if said == "none":
        return ""
    if said in ("goals_up", "goals_down"):
        return said
    if side is None:
        return "both"          # 🔴 어느 팀인지 모르면 한쪽으로 밀지 않는다
    if said == "subject":
        return side
    if said == "opponent":
        return "away" if side == "home" else "home"
    return "both"


def from_agent_var(var, g: Game) -> Classified:
    """🔴🔴 **§5-4** — 에이전트 변수 하나를 판정층 꼴로. 🔴 방향은 **코드가** 정한다.

    ⚠️ `direction_hint` 를 **쓰지 않는다** — 그 변수가 적은 **팀 열쇠**가 쪽을
       정한다. 모델이 `away` 라고 적어도 그 팀이 홈이면 **홈**이다. 🔴 힌트를
       그대로 쓰면 그것이 `side_mismatch` 의 입구다(M36).
    🔴 이 경기 팀이 **아닌** 열쇠면 변수가 못 된다 — `undecided` 가 그 사실을
       말한다(조용히 버리지 않는다 · #3).
    """
    from app import domains, verifylayer
    key = str(getattr(var, "team", "") or "")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **누구에 관한** ≠ **누구에게 유리** — 지시 2026-10-05
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전엔 `team` 열쇠를 **그대로 방향**으로 썼다. 🔴 그래서 실측 pn7 에서
    #     *"호날두가 포르투갈에서 이탈"* 이 **포르투갈 근거**가 되고
    #     *"포르투갈 8강 확정"* 도 **포르투갈 근거**가 됐다 — **둘 다 거꾸로**다.
    #  🔴 `subject`(관한) 를 받아 `favors_of`(유리)를 **카탈로그 규칙으로** 계산한다.
    subject = str(getattr(var, "subject", "") or key)
    said = " ".join(str(getattr(var, "claim", "") or "").split()) + " " + \
        " ".join(str(getattr(var, "quote", "") or "").split())
    favors = favors_of(str(getattr(var, "type", "") or ""),
                       subject=subject, game=g, text=said)
    # 🔴 `side` 는 **유리한 쪽**이다. ⚠️ `both`·`""` 는 아래가 따로 다룬다.
    side = favors if favors in ("home", "away") else ""
    if not subject or g.side_of(subject) is None:
        # 🔴 M36 — 어느 팀 사실인지 모르면 **변수가 아니다**(아래가 적는다)
        side = ""
    url = str(getattr(var, "url", "") or "")
    tier = domains.tier_of(url)
    # 🔴 §5-5 — 무게는 **등급**이 준다(모델이 아니다). ⚠️ 미재검증은 한 단계 아래.
    n = verifylayer.hardness_for(
        tier, conflict=bool(getattr(var, "conflict", False)),
        reverified=bool(getattr(var, "reverified", True)))
    hard = "hard" if n >= 2 else "soft"
    text = " ".join(str(getattr(var, "claim", "") or "").split())
    quote = " ".join(str(getattr(var, "quote", "") or "").split())
    out = Classified(
        text=f"{text} — 인용 「{quote}」" if quote else text,
        source_url=url, hardness=hard,
        type=str(getattr(var, "type", "") or ""),
        direction=side or "home",
        favors=favors,
        published_at=getattr(var, "published_at", None),
        team=(g.home if side == "home" else g.away if side == "away" else ""),
        why=(f"§3 에이전트 + §5 검증층 통과 · 등급 `{tier}`(무게 {n}) · "
             f"힌트 `{getattr(var, 'direction_hint', '')}` → **코드가 정한 쪽** "
             f"`{side or '없음'}`(§5-4)"))
    if not side and favors == "both" and g.side_of(subject) is not None:
        # 🔴🔴 **`both` 는 미결정이 아니다** — 지시 2026-10-05 ⑤.
        #    ⚠️ 종전엔 `side` 가 비면 `side_mismatch` 로 찍었다 — 그래서
        #       `coach_conflict`(both)가 **복제되기 전에 버려졌다.**
        #    🔴 `from_agent_vars` 가 **두 항목으로 나눈다** — 여기서는 `home` 을
        #       임시로 두고 그 함수가 양쪽을 만든다(그 사실을 사유에 적는다).
        out.direction = "home"
        out.why += " · 🔴 `favors: both` — **양쪽에 붙인다**(§5-4)"
    elif not side:
        # 🔴 M36 — 이 경기 팀이 아니다. **변수가 아니라고** 적는다.
        out.undecided = (
            f"🔴 `side_mismatch` — 변수가 적은 팀 `{key or '없음'}` 이 이 경기 "
            f"팀이 아니다(홈 `{g.home_id}` · 원정 `{g.away_id}`) · §5-4 · M36")
    return out


def from_agent_vars(vars_: list, g: Game) -> list[Classified]:
    """🔴 §5-4 — 여러 개. **양방향 유형은 두 항목으로 나눈다.**

    ⚠️ 한 쪽에만 붙이면 그 변수가 **한 방향 근거**가 된다 — 양방향은 어느 쪽으로
       갈지 **모르는** 변수다(§6-2 ⑥ 과 같은 까닭).
    🔴 **같은 사실**이 두 쪽에 선다(지어낸 것이 아니다) — `text` 가 같다.
    """
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **양방향 복제는 `favors: both` 유형에만** — 지시 2026-10-05 ⑤
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 종전엔 `required_forms.양방향_변수` 라는 **별도 선언**을 봤다.
    #     🔴 이제 카탈로그의 `favors: both` 가 **원본**이다 — 두 곳에 적으면
    #     한쪽이 늘 한 발 늦는다(사본 금지 · #1).
    #  🔴 `absence` 가 복제되면 **결장이 양쪽 근거**가 된다 — 그것이 지시 ⑤ 가
    #     막는 것이다.
    from app import rules
    both = {t for t, b in (rules.variable_types() or {}).items()
            if str((b or {}).get("favors") or "") == "both"}
    out: list[Classified] = []
    for v in (vars_ or []):
        got = from_agent_var(v, g)
        if str(getattr(v, "type", "")) not in both or got.undecided:
            out.append(got)
            continue
        import dataclasses
        for side in ("home", "away"):
            out.append(dataclasses.replace(
                got, direction=side,
                team=(g.home if side == "home" else g.away),
                why=got.why + f" · §5-4 **양방향 → 두 항목**({side})"))
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **두 매체가 같은 사실을 말하면 `hard`** — 지시 2026-10-05 ⑤
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 같은 URL 두 매체 이상이면 hardness 올림(**R4 가 hard 여야 한다**).
    #
    #  ⚠️ 실측 pn7: 호날두 이탈을 **여러 매체**가 말했는데 전부 `soft` 였다.
    #  🔴 §5-7 이 *"독립 출처"* 를 세는 바로 그 생각이다 — 두 **호스트**가 같은
    #     유형·같은 쪽을 말하면 그것은 단단한 사실이다.
    #  ⚠️ **같은 호스트 두 기사는 한 매체**다(`urlparse().netloc` 으로 센다).
    from urllib.parse import urlparse
    seen: dict = {}
    for c in out:
        host = urlparse(str(c.source_url or "")).netloc.lower()
        if host:
            seen.setdefault((c.type, c.direction), set()).add(host)
    import dataclasses as _dc
    for i, c in enumerate(out):
        hosts = seen.get((c.type, c.direction)) or set()
        if len(hosts) >= 2 and c.hardness != "hard":
            out[i] = _dc.replace(
                c, hardness="hard",
                why=c.why + f" · 🔴 **매체 {len(hosts)}곳**이 같은 말을 한다 → "
                            f"hardness soft→**hard**(§5-7 · 지시 ⑤)")
    return out


def _h2h_tail(val: dict) -> str:
    """🔴 맞대결 사유에 **전반 연속 리드**를 덧붙인다(사용자 지적 2026-10-03).

    ⚠️ 적지 않으면 그 사실이 카드에서 사라진다(#3 조용한 0 금지).
    """
    n, k = val.get("ht_lead_streak"), val.get("ht_sample")
    who = str(val.get("ht_lead_team") or "").strip()
    if n is None:
        return ""
    # 🔴 **누구의 연속인지 적는다** — 안 적으면 카드를 읽는 사람이 못 가린다
    #    (맞대결 사실은 경기 하나에 하나이고, 연속은 팀마다 다르다).
    tag = f"{who} " if who else ""
    if not n:
        return f" · {tag}전반 연속 리드 없음(표본 {k}경기)"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **1 은 연속이 아니다** · 표본 2 로 패턴을 말하지 않는다(§7 R7)
    # ══════════════════════════════════════════════════════════════════
    #
    #  실측 2026-10-03(엘살바도르 vs 자메이카)에서 카드가 이렇게 적었다:
    #    **El Salvador 1경기 연속 전반 리드**(표본 2경기)
    #  🔴 두 군데가 틀렸다. *"1경기 연속"* 은 연속이 아니고(한 번 그랬다는 말이다),
    #     표본 2 는 §7 R7 이 **패턴으로 쓰지 말라고 못 박은** 크기다
    #     (*"표본 2경기로 정하지 않는다"* — 바로 위 `RECENT_MIN` 이 그 수다).
    #  ⚠️ 지우지 않는다 — **굵게 쓰지 않고 사실로만** 적는다(#3 조용한 0 금지).
    #     굵은 글씨가 "이것이 패턴이다"라고 말하는 자리이기 때문이다.
    thin = k is not None and int(k) < RECENT_MIN
    if int(n) < 2 or thin:
        # 🔴 **두 사유를 구분해 적는다** — 처방이 다르다. 표본이 얇은 것은 경기가
        #    더 쌓이면 풀리고, 연속이 1 인 것은 그 자체로 패턴이 아니다.
        why = (f"표본 {RECENT_MIN}경기 미만" if thin else "연속이 1회")
        return (f" · {tag}전반 리드 {n}회/표본 {k}경기 — "
                f"{why}이라 패턴으로 세지 않는다(§7 R7)")
    return f" · **{tag}{n}경기 연속 전반 리드**(표본 {k}경기)"


def score_of(row: dict) -> tuple[int | None, int | None]:
    """🔴🔴 그 경기 행의 **홈·원정 점수**. 못 읽으면 `(None, None)`.

    ══════════════════════════════════════════════════════════════════
    🔴 **칸 이름이 어댑터마다 다르다**(실측 2026-10-04 전수 조사)
    ══════════════════════════════════════════════════════════════════

    ```
    fotmob                                  home_goals / away_goals
    mlb · nhl · npb · kbo · fdorg · espn    home_score / away_score
    ```
    ⚠️ `_dir_h2h` 는 `home_goals` **하나만** 읽었다. 그래서 야구·하키의 맞대결은
       **전부 0승 0패**로 셌다 — 실측 2026-10-04(밀워키 vs 샌디에이고) 카드 원문:

        §4 h2h_pattern — 창 **13경기** 홈 0승 원정 0승, 갈려서 방향이 없다
                           · 맞대결 표본 **0경기**

    🔴 13경기를 받아 놓고 한 경기도 안 센 것이다 — `last5` 와 **같은 꼴 버그**다.
    ⚠️ 그래서 맞대결 변수(`h2h_pattern`)는 **축구에서만** 섰다.
    🔴 고치는 자리를 **하나로** 둔다 — 호출부마다 `or` 를 적으면 새 호출부가 또 빠진다.
    """
    def _one(k: str):
        v = row.get(k) if isinstance(row, dict) else None
        if v is None or v == "":
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    # 🔴🔴 **정본 이름 하나만** 읽는다(§8-3).
    #
    #  ⚠️ 종전에는 `home_goals` 도 함께 봤다 — fotmob 하나가 그 이름을 쓰고
    #     있었기 때문이다. 🔴 §11-1 이 금지한 **증상 수정**이 그것이다: 읽는
    #     쪽에 `or` 를 덧대면 다음 어댑터가 또 다른 이름을 들고 온다.
    #  🔴 이제 fotmob 이 **어댑터 안에서** 바꿔 낸다. 분기를 걷었다.
    #     계약: `tests/contracts/test_v5_8_3_fact_schema.py`
    return _one("home_score"), _one("away_score")


def _dir_h2h(val: dict, g: Game) -> tuple[Direction | None, str, str]:
    """패턴 방향.

    🔴 **창 안의 승패만** 본다(§4 `h2h_pattern.sample_weight.window`). 총골은 배경이다.
    """
    # 🔴🔴 **누적 승패 꼴도 받는다**(사용자 지시 2026-10-02 *"변수 0건은 말이 안된다"*).
    #
    #  야구 순위표(npb.jp)는 경기별 기록이 아니라 **팀별 누적 승패**를 준다(`対ロ 16-6`).
    #  규칙은 같다 — *"패턴 방향"* 이고, 누적이면 그 수로 바로 센다.
    #  ⚠️ 경기 목록을 **지어내지 않는다** — 꼴이 다르면 다르게 읽는다.
    if val.get("shape") == "aggregate":
        w, lo = val.get("h2h_wins"), val.get("h2h_losses")
        if w is None or lo is None:
            return None, "", "맞대결 누적 승패를 못 읽었다"
        mine = g.side_of(val.get("team") or "") or g.side_of(
            str(val.get("h2h_opponent") or "")) and g.other(
            g.side_of(str(val.get("h2h_opponent"))))
        if mine is None:
            return None, "", "맞대결이 어느 팀 것인지 모른다"
        if w == lo:
            return None, (f"§4 h2h_pattern — 누적 {w}승 {lo}패로 갈려서 방향이 없다"), ""
        return (mine if w > lo else g.other(mine)), (
            f"§4 h2h_pattern '패턴 방향' — {val.get('column')} 누적 "
            f"{w}승 {lo}패({val.get('h2h_games')}경기){_h2h_tail(val)}"), ""
    # 🔴 §8-3 — `matches` 는 *"규칙이 세는 것"*(창 안의 경기)이다. fotmob 이
    #    어댑터 안에서 그렇게 바꿔 낸다(종전 `window` 는 고유 칸이었다).
    win = val.get("matches") or []
    if not win:
        return None, "", "맞대결 자료가 없다"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **M17 — 몰수 경기를 뺀다**(§9-2)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 몰수(forfeit)는 **경기가 아니다** — 공식 스코어(야구 9-0)가 실제로
    #     일어난 일이 아니다. 🔴 맞대결 승패에 넣으면 그 수가 거짓이 된다.
    #  🔴 **뺀 것을 수로 남긴다**(#3 조용한 0 금지) — 몇 경기가 빠졌는지 모르면
    #     *"13경기"* 와 *"12경기"* 의 차이를 되짚을 수 없다.
    win, forfeits = forfeit_rows(win)
    if not win:
        return None, "", (f"맞대결 {len(forfeits)}경기가 **전부 몰수**다 — "
                          f"셀 경기가 없다(M17)")
    hw = aw = 0
    for m in win:
        # 🔴 **칸 이름을 한 곳에서 고른다**(위 `score_of` 머리글 · 2026-10-04)
        hg, ag = score_of(m)
        if hg is None or ag is None:
            continue
        who = g.side_of(m.get("home"))
        if who is None:
            continue
        if hg > ag:
            hw += 1 if who == "home" else 0
            aw += 1 if who == "away" else 0
        elif ag > hg:
            aw += 1 if who == "home" else 0
            hw += 1 if who == "away" else 0
    tail = _h2h_tail(val)
    if forfeits:
        # 🔴 M17 — **뺀 수를 적는다**(조용히 빼면 수가 거짓으로 보인다)
        tail += f" · 🔴 몰수 {len(forfeits)}경기를 **뺐다**(M17)"
    if hw == aw:
        return None, (f"§4 h2h_pattern — 창 {len(win)}경기 홈 {hw}승 원정 {aw}승, "
                      f"갈려서 방향이 없다{tail}"), ""
    return ("home" if hw > aw else "away"), (
        f"§4 h2h_pattern '패턴 방향' — 최근 {len(win)}경기 "
        f"홈 {hw}승 원정 {aw}승{tail}"), ""


def _dir_match_type(val: dict, g: Game) -> tuple[Direction | None, str, str]:
    """친선→무동기·무승부, 단판→언더.

    🔴 **단판의 '언더' 는 총점이라 변수에 붙이지 않는다**(§4) → 배경.
       친선의 '무승부' 만 방향이 된다.
    """
    mt = str(val.get("match_type") or g.match_type or "").strip()
    if not mt:
        return None, "", "경기 성격(친선·단판 등)을 모른다"
    if mt == "friendly":
        return "draw", "§4 match_type '친선→무동기·무승부'", ""
    return None, (f"§4 match_type — '{mt}' 는 방향을 밀지 않는다"
                  f"(단판의 '언더' 는 총점이라 변수에 안 붙인다)"), ""


def _dir_coach_change(val: dict, g: Game) -> tuple[Direction | None, str, str]:
    """새 감독 팀 쪽 + 무승부.

    🔴 `splits_direction` — **두 방향을 밀므로 두 항목으로 나눈다.** 여기서는 팀 쪽을
       돌려주고, 나누는 것은 `classify_fact` 가 한다.
    """
    side = g.side_of(val.get("team"))
    if side is None:
        return None, "", "어느 팀의 감독 교체인지 모른다"
    if not val.get("coach_change"):
        return None, "", "감독 교체 사실이 아니다"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **시점이 없으면 변수로 안 세운다** (실측 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  콜롬비아 vs 파라과이에서 봇이 이것을 **변수 둘**로 냈다:
    #    `coach_change=True · left=None · since=None · arrived='named'`
    #  🔴 두 감독 다 유임이다(로렌소·알파로, 2026 월드컵 그대로). 거짓이었다.
    #
    #  원인: `parse_coach_change` 의 둘째 경로가 기사에 *부임/사임* **낱말 하나만**
    #  있으면 `coach_change=True` 를 **날짜 없이** 만든다. 그 낱말은 과거 부임
    #  기사·다른 팀 기사에도 있다.
    #
    #  🔴 §4 가 요구하는 것은 셋이다: *"감독 교체 · **부임 시점** · 첫 경기 여부."*
    #     시점이 없으면 셋 중 둘을 모르는 것이고, 그러면 **미결정**이다.
    #  ⚠️ `splits_direction` 이라 이 사실 하나가 변수 **둘**(팀 쪽 + 무승부)을
    #     만든다 — 거짓이 두 배로 센다. 그래서 여기서 막는 것이 특히 중요하다.
    since = val.get("since") or val.get("days_before_game")
    if not since:
        return None, "", ("감독 교체의 **부임 시점**을 못 읽었다 — §4 는 시점과 "
                          "첫 경기 여부를 함께 요구한다(낱말만으로는 변수가 아니다)")
    return side, (f"§4 coach_change '새 감독 팀 쪽 + 무승부' — "
                  f"{val.get('team')} (부임 {since})"), ""


#: 🔴 **유형 → 방향 함수.** 여기 없는 §4 유형은 **미구현이고 이름으로 남는다**(#7).
#   ⚠️ 목록을 늘릴 때 계약이 "yaml 에 있는 유형인가"를 본다.
# ══════════════════════════════════════════════════════════════════
# 🔴🔴 사용자 지시 2026-10-02 — **"한꺼번에 전부다 수정해라"**
# ══════════════════════════════════════════════════════════════════
#
# 아래 여덟이 그 지시로 생겼다. 왜 전에 없었나와 무엇으로 정하나를 함께 적는다.
#
# ⚠️ **공통 규율**: 자료가 없으면 `undecided`(미결정), 규칙이 "아니다"라고 판단하면
#    `direction=None` + `why`(배경)다. 둘을 섞으면 고칠 곳을 못 찾는다.
# 🔴 **LLM 이 방향을 정하지 않는다**(§17-c). LLM 은 `answer`·`quote` 만 내고,
#    낱말 대조와 방향 판정은 전부 이 파일의 코드가 한다.


def _ask_yes(val: dict) -> bool:
    """좁은 질문(③)의 답이 `yes` 인가. ⚠️ `no`·`unknown` 은 사실이 아니다."""
    return str(val.get("answer") or "").strip().lower() == "yes"


def _other_side(g: Game, team) -> tuple[Direction | None, str]:
    """🔴 그 팀의 **반대 쪽**. 못 가리면 사유를 돌려준다."""
    side = g.side_of(team)
    if side is None:
        return None, f"어느 팀 이야기인지 모른다(team={team!r})"
    return ("away" if side == "home" else "home"), ""


def _dir_pitcher_state(val: dict, g: Game) -> tuple[Direction | None, str, str]:
    """🔴 **방어율이 낮은 선발 쪽** 승리. 차이가 `era_gap_min` 이상일 때만.

    ⚠️ 왜 이제까지 없었나: 예고 선발 **이름조차** 없었다(`starters` 표 14줄이 전부
       MLB). npb.jp 일정 페이지가 `先発：前田悠` 로 주고 있었는데 파서가 끝난 경기의
       `勝：`·`敗：` 와 섞어 쓰고 있었고, 수집은 9/30 에 멈춰 있었다.
    🔴 **승패가 아니라 방어율로** 정한다 — 승패는 타선이 섞인다(마에다 12승 1패는
       소프트뱅크 타선이 함께 만든 수다).
    ⚠️ 둘 다 알아야 한다. 하나만 알고 방향을 고르면 그것은 추측이다.
    """
    mine, theirs = val.get("era"), val.get("opponent_era")
    if mine is None or theirs is None:
        miss = "우리" if mine is None else "상대"
        return None, "", (f"선발 방어율을 둘 다 알아야 한다 — {miss} 쪽을 못 읽었다 "
                          f"(이름만 안다: {val.get('player') or '?'})")
    side = g.side_of(val.get("team"))
    if side is None:
        return None, "", f"어느 팀 선발인지 모른다(team={val.get('team')!r})"
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **v5 §5-6 — 임의 문턱을 걷었다** (2026-10-04) [#23]
    # ══════════════════════════════════════════════════════════════════
    #
    #  > **ERA 차 0.75 같은 임의 상수로 방향을 정하지 않는다.** `pitcher_state` 는
    #  > 두 투수의 **사실을 변수로 보존**하고, 방향은 **시나리오 단계에서 변수
    #  > 조합으로** 나타난다.
    #
    #  ⚠️ 실측 2026-10-04(밀워키 vs 샌디에이고): ERA 2.47 vs 3.21 — 차이 **0.74**
    #     가 문턱 **0.75** 에 **0.01** 모자라 선발이 배경으로 떨어졌고, 그래서
    #     M18 이 총점·핸디를 통째로 거뒀다.
    #  🔴 그 `0.75` 는 **내가 고른 수**다 — 어디서도 재지 않았다.
    #     `config/thresholds.yaml` 의 `era_gap_min` 이 `null` 로 남아 그 사실을 적는다.
    #
    #  🔴 **지금 하는 것은 산수뿐이다** — 낮은 쪽이 좋은 선발이다. 같으면 방향이
    #     없다(그것은 임의 문턱이 아니라 등식이다).
    #  ⚠️ *"얼마나 차이 나면 뜻이 있나"* 는 **§6 이 무게로** 말한다 — 작은 차이는
    #     작은 무게의 변수 하나이고, 시나리오가 그것을 다른 변수와 함께 센다.
    gap = round(float(theirs) - float(mine), 3)
    if gap == 0:
        return None, (f"§4 pitcher_state — 선발 방어율이 **같다**"
                      f"({mine} vs {theirs}) · 방향이 없다"), ""
    better = side if gap > 0 else ("away" if side == "home" else "home")
    return better, (f"§4 pitcher_state '좋은 쪽 승리' — {val.get('player')} "
                    f"방어율 {mine} vs 상대 {theirs}(차이 {abs(gap)}) "
                    f"· §5-6 임의 문턱 없음"), ""


def _dir_lineup_intent(val: dict, g: Game) -> tuple[Direction | None, str, str]:
    """🔴 감독 발언 — `best` 면 **그 팀 쪽**, `rest` 면 **상대 쪽**.

    ⚠️ 전에 *"'내용대로'를 규칙으로 못 읽는다"* 로 비워 뒀다. 전부는 지금도 못 읽는다 —
       그러나 승부에 닿는 갈래는 둘뿐이고, 그 둘은 낱말로 갈린다.
    🔴 낱말 목록은 **yaml 이 원본이다**(`intent_words`) — 여기 적지 않는다.
    """
    quote = " ".join(str(val.get("quote") or "").split())
    if not quote:
        return None, "", "감독 발언 원문이 없다 — 낱말을 대조할 수 없다"
    words = (rules.variable_types().get("lineup_intent") or {}) \
        .get("intent_words") or {}
    low = quote.lower()
    hit = {}
    for kind in ("best", "rest"):
        for w in (words.get(kind) or []):
            if str(w).lower() in low:
                hit[kind] = str(w)
                break
    if len(hit) != 1:
        why = ("두 갈래 낱말이 함께 있다" if len(hit) > 1
               else "총력·휴식 어느 갈래 낱말도 없다")
        return None, "", f"감독 발언을 한 갈래로 못 읽는다 — {why}: {quote[:60]}"
    kind, word = next(iter(hit.items()))
    team = val.get("team") or val.get("speaker_team")
    side = g.side_of(team)
    if side is None:
        return None, "", f"어느 팀 감독인지 모른다(team={team!r})"
    if kind == "best":
        return side, (f"§4 lineup_intent '발언 내용대로' — 총력(`{word}`) "
                      f"→ {team} 쪽"), ""
    other = "away" if side == "home" else "home"
    return other, (f"§4 lineup_intent '발언 내용대로' — 휴식·로테이션(`{word}`) "
                   f"→ 상대 쪽"), ""


def _dir_event_match(val: dict, g: Game) -> tuple[Direction | None, str, str]:
    """🔴 **방향 없음이 규칙이다** — 행사 경기면 승패 마켓을 접는다.

    ⚠️ 전에 `NOT_CLASSIFIED` 에 있었다. 그러면 *"자료가 없어 못 판단"* 으로 적히는데
       사실은 **규칙이 방향을 안 만드는 것**이다. 그 둘을 가른다(§4 배경 vs 미결정).
    🔴 마켓을 접는 일은 §5-c 의 `fold_win_markets` 가 한다(`attaches_to`) — 여기서는
       **배경으로 적고 사유를 남긴다.**
    """
    if not _ask_yes(val):
        return None, "", ("행사·자선 경기라는 보도를 못 찾았다 — 정식 경기로 본다"
                          if val.get("answer") else "행사 여부를 못 읽었다")
    return None, (f"§4 event_match '방향 없음 — 승패 마켓을 접는다' "
                  f"(근거: {str(val.get('quote') or '')[:60]})"), ""


def _dir_emotion(val: dict, g: Game) -> tuple[Direction | None, str, str]:
    """🔴 승리 극대화가 아닌 기용을 하는 팀의 **상대 쪽**.

    ⚠️ `event_match` 와 다르다: 대회 자체가 행사인 것이 아니라 **정식 경기인데 한
       팀이** 다른 것을 앞세운 경우다(은퇴 경기·헹가래 대기·소화 경기).
    🔴 실측 2026-10-02 가 요구했다 — 사람이 찾은 변수 둘(가쿠나카 은퇴 경기 선발
       기용 · 다음 날 은퇴 등판 탓에 불펜 아낌)이 전부 이 꼴이었다.
    """
    if not _ask_yes(val):
        return None, "", ("결과보다 다른 것을 앞세운다는 보도를 못 찾았다"
                          if val.get("answer") else "상황을 못 읽었다")
    other, bad = _other_side(g, val.get("team"))
    if other is None:
        return None, "", bad
    return other, (f"§4 emotion '상황별' — 승리 극대화가 아닌 기용 "
                   f"→ 상대 쪽 (근거: {str(val.get('quote') or '')[:60]})"), ""


def _dir_venue_weather(val: dict, g: Game) -> tuple[Direction | None, str, str]:
    """🔴 **승패 방향이 없다** — 날씨는 총점 힌트다(§4 `total_hint`).

    ⚠️ 비가 온다고 홈이 이기지 않는다. 방향을 붙이면 그것이 지어내는 것이다.
    🔴 전에 빠져 있던 것은 방향이 아니라 **힌트가 카드에 한 줄도 안 올라간 것**이다.
       실측 2026-10-02: 사용자가 확정 사실로 쓴 *"흐리고 한때 비"* 가 우리가 이미
       여는 페이지에 있었다(`npb.jp` 일정의 `img alt`).
    ⚠️ **맑음을 오버로 읽지 않는다** — 그 쪽은 근거가 없다(한쪽만 아는 것을 양쪽
       아는 것처럼 쓰지 않는다).
    """
    text = " ".join(str(val.get("weather") or val.get("note") or "").split())
    if not text:
        return None, "", "날씨 표기가 없다"
    words = (rules.variable_types().get("venue_weather") or {}) \
        .get("under_words") or []
    low = text.lower()
    hit = next((str(w) for w in words if str(w).lower() in low), "")
    if not hit:
        return None, (f"§4 venue_weather(total_hint) — 날씨 `{text}` · "
                      f"언더 쪽 낱말 없음(힌트 없다)"), ""
    return None, (f"§4 venue_weather(total_hint) — 날씨 `{text}` → "
                  f"**언더 쪽 힌트**(`{hit}`)"
                  + ("" if _weather_has_number(text)
                     else " · 🔴 **수치가 없다 → soft**(M16)")), ""


def _weather_has_number(text: str) -> bool:
    """🔴🔴 **M16 — 날씨에 수치가 있나.** 없으면 그 변수는 `soft` 다.

    ⚠️ *"비가 온다"* 와 *"강수 8mm"* 는 다르다 — 수가 없으면 그 변수가 **얼마나
       센지 모른다**. 🔴 모르는 것을 hard 로 쓰면 그 모름이 사라진다.
    🔴 표기 글자는 **yaml 이 정한다**(지어내지 않는다 · `number_marks`).
    """
    marks = (rules.variable_types().get("venue_weather") or {}) \
        .get("number_marks") or []
    low = str(text or "").lower()
    if not any(str(m).lower() in low for m in marks):
        return False
    # ⚠️ 글자만 있고 **수가 없으면** 수치가 아니다(`mm` 라고만 적힌 표)
    import re as _re
    return bool(_re.search(r"\d", low))


def _dir_def_absence(val: dict, g: Game) -> tuple[Direction | None, str, str]:
    """🔴 수비수·GK 가 빠진 팀의 **반대 방향**(§4 `direction_rule` 그대로).

    ⚠️ 전에 *"결장 선수의 자리(DF·GK)를 아는 길이 없다"* 로 비워 뒀다. 🔴 그런데
       ③ 좁은 질문이 **바로 그것을 묻는다**(`asks`: 수비수나 골키퍼가 못 나오나).
       자리를 따로 알아낼 필요가 없었다 — 질문이 이미 자리를 담고 있었다.
    """
    if not _ask_yes(val):
        return None, "", ("수비수·골키퍼 결장 보도를 못 찾았다"
                          if val.get("answer") else "결장 여부를 못 읽었다")
    other, bad = _other_side(g, val.get("team"))
    if other is None:
        return None, "", bad
    return other, (f"§4 def_absence '결장 팀 반대 방향' — "
                   f"{val.get('player_name') or '수비 자원'} 결장 "
                   f"(근거: {str(val.get('quote') or '')[:60]})"), ""


def _dir_squad_rotation(val: dict, g: Game) -> tuple[Direction | None, str, str]:
    """🔴 로테이션 하는 팀의 **반대 방향**(§4 `direction_rule` 그대로).

    ⚠️ 전에 *"직전 선발과 대조하는 길이 없다"* 로 비워 뒀다 — `def_absence` 와 같은
       오독이다. ③ 좁은 질문이 *"선발을 여러 명 바꾸나"* 를 직접 묻는다.
    """
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **숫자 자료를 먼저 본다**(명단 대조 · 사용자 지적 2026-10-03)
    # ══════════════════════════════════════════════════════════════════
    #
    #  yaml 이 적어 둔 막힘이 *"직전 선발과 대조하는 길이 없다"* 였다. 🔴 이제 있다 —
    #  `_fill_squad_change` 가 오늘 선발과 기준 선발을 대조해 **명수**를 낸다.
    #  ⚠️ 기사의 yes/no 보다 **센 근거**다(숫자고, 모델이 읽은 것이 아니다).
    if val.get("xi_changes") is not None:
        n = int(val["xi_changes"])
        floor = int((rules.variable_types().get("squad_rotation") or {})
                    .get("xi_change_min") or 0)
        if n < floor:
            return None, (f"§4 squad_rotation — 선발 교체 {n}명(문턱 {floor}) · "
                          f"평소와 비슷하다고 본다"), ""
        other, bad = _other_side(g, val.get("team"))
        if other is None:
            return None, "", bad
        drop = val.get("dropped") or []
        return other, (f"§4 squad_rotation '로테이션 하는 팀 반대 방향' — "
                       f"{val.get('team')} 선발 {n}명 교체"
                       + (f" · 스쿼드에서 사라진 {len(drop)}명"
                          f"({', '.join(map(str, drop[:3]))})" if drop else "")), ""
    # 🔴 **확정 XI 가 없으면** 숫자를 못 센다 — 그 사실을 적는다(기사 쪽으로 간다)
    if "xi_changes" in val:
        drop = val.get("dropped") or []
        return None, "", (
            f"오늘 확정 XI 가 없어 선발 교체를 못 셌다"
            + (f" · 스쿼드에서 사라진 {len(drop)}명"
               f"({', '.join(map(str, drop[:3]))})" if drop else ""))
    if not _ask_yes(val):
        return None, "", ("선발 대폭 교체 보도를 못 찾았다"
                          if val.get("answer") else "로테이션 여부를 못 읽었다")
    other, bad = _other_side(g, val.get("team"))
    if other is None:
        return None, "", bad
    return other, (f"§4 squad_rotation '로테이션 하는 팀 반대 방향' "
                   f"(근거: {str(val.get('quote') or '')[:60]})"), ""


def _dir_national_duty(val: dict, g: Game) -> tuple[Direction | None, str, str]:
    """🔴 **방향 없음이 규칙이다** — 최근 N경기 표본을 무효화한다.

    ⚠️ 방향을 만들지 않는다(§4 `direction_rule`: *"recent_pattern 의 표본을
       무효화한다"*). 무효화는 §5-c 의 `invalidate_recent_form` 이 한다.
    """
    if not _ask_yes(val):
        return None, "", ("대표팀 복귀 보도를 못 찾았다"
                          if val.get("answer") else "복귀 여부를 못 읽었다")
    return None, (f"§4 national_duty_return '방향 없음 — recent_pattern 표본 "
                  f"무효화' (근거: {str(val.get('quote') or '')[:60]})"), ""


def _fill_half_time(facts: list, game: Game) -> None:
    """🔴🔴 **전반 연속 리드**를 세어 맞대결 사실에 얹는다(사용자 지적 2026-10-03).

    ══════════════════════════════════════════════════════════════════
    > 콜롬비아가 최근 **4번 연속 전반을 앞섰다**
    ══════════════════════════════════════════════════════════════════

    🔴 **묶음이어야 한다** — 전반 스코어는 과거 경기마다 **따로** 온다
       (`:h2h_half`), 그리고 "연속"은 그것들을 **날짜 순으로 이어야** 나온다.
    ⚠️ 방향을 만들지 않는다 — 이 수는 `h2h_pattern` 변수의 **사유에 얹힌다**.
       새 유형을 만들면 같은 맞대결이 변수 둘로 세어진다(이중 계산).
    """
    rows = []
    seen: set[tuple] = set()
    for f in facts:
        v = f.value if isinstance(f.value, dict) else {}
        if not (str(getattr(f, "question_id", "")).endswith(":h2h_half") and v):
            continue
        # 🔴🔴 **같은 과거 경기를 두 번 세지 않는다**(실측 2026-10-03).
        #    깊이 세포가 **팀마다** 돌므로 같은 맞대결 4경기가 **8건**으로 들어왔고
        #    연속이 `8경기` 로 부풀었다(실제 4경기다).
        key = (str(v.get("date") or ""), str(v.get("home") or ""),
               str(v.get("away") or ""))
        if key in seen:
            continue
        seen.add(key)
        rows.append(v)
    if not rows:
        return
    rows.sort(key=lambda r: str(r.get("date") or ""), reverse=True)
    for side, team in (("home", game.home), ("away", game.away)):
        del side
        streak = 0
        for r in rows:
            mine_home = verify_mentions(str(r.get("home") or ""), team)
            mine_away = verify_mentions(str(r.get("away") or ""), team)
            if mine_home == mine_away:
                break          # 귀속을 못 한다 — 연속이 끊긴 것으로 본다
            mine = r["ht_home"] if mine_home else r["ht_away"]
            theirs = r["ht_away"] if mine_home else r["ht_home"]
            if mine <= theirs:
                break
            streak += 1
        # 🔴 그 팀의 맞대결 사실에 얹는다(없으면 아무 일도 안 한다)
        for f in facts:
            v = f.value if isinstance(f.value, dict) else {}
            if not str(getattr(f, "question_id", "")).endswith(":h2h"):
                continue
            if not verify_mentions(str(getattr(f, "team", "") or ""), team):
                continue
            v["ht_lead_streak"] = streak
            v["ht_sample"] = len(rows)
            v["ht_lead_team"] = team
        logger.info("[classify] %s 전반 연속 리드 %d (표본 %d경기)",
                    team, streak, len(rows))


def _fill_squad_change(facts: list, game: Game) -> None:
    """🔴🔴 **명단 대조** — 오늘 스쿼드 vs 직전 경기 스쿼드(사용자 지적 2026-10-03).

    ══════════════════════════════════════════════════════════════════
    > R1 콜롬비아 **로테이션** … R2 핵심 부재(하메스·킨테로 은퇴, 디아스 **미소집**)
    ══════════════════════════════════════════════════════════════════

    봇은 *"다친다"* 만 물었다(`absence`). 그런데 사용자 변수 둘이 **명단 대조**에서
    나온다 — *"직전에 있었는데 이번엔 없다"*. 그것은 기사가 아니라 **두 명단의 차**다.

    ⚠️ `squad_rotation` 의 yaml 이 적어 둔 막힘이 정확히 이것이었다:
       *"직전 선발과 대조하는 길이 아직 없다(기준 XI 가 필요하다)"*. 🔴 이제 있다 —
       `fotmob.squad_names` 가 선발+교체 26명을 내고, §19-c 가 직전 경기를 따라간다.

    🔴 두 수를 낸다:
        `xi_changes`      오늘 선발 중 직전 선발에 없던 **명수**
        `dropped`         직전 스쿼드에 있었는데 오늘 **사라진** 이름들
    ⚠️ 오늘이 **확정 XI 가 아니면** `xi_changes` 를 세지 않는다 — 예상 XI 로 로테이션을
       말하면 거짓이다. `dropped` 는 스쿼드 단위라 그 제약이 없다.
    """
    today: dict[str, dict] = {}
    base: dict[str, dict] = {}
    for f in facts:
        v = f.value if isinstance(f.value, dict) else {}
        if not isinstance(v, dict) or not v.get("team"):
            continue
        if not (v.get("players") or v.get("squad")):
            continue
        box = base if v.get("lineup_kind") == "baseline" else today
        box.setdefault(str(v["team"]), v)
    if not base:
        return
    for team, was in base.items():
        now = next((n for k, n in today.items() if verify_mentions(k, team)),
                   None)
        old_sq = [str(x) for x in (was.get("squad") or was.get("players") or [])]
        old_xi = [str(x) for x in (was.get("players") or [])]
        if not old_sq:
            continue
        if now is None:
            # 🔴 오늘 명단을 아직 모른다 — **그 사실을 적는다**(조용한 0 금지)
            facts.append(_squad_fact(team, None, old_xi, old_sq, was))
            continue
        new_sq = [str(x) for x in (now.get("squad") or now.get("players") or [])]
        new_xi = [str(x) for x in (now.get("players") or [])]
        confirmed = str(now.get("lineup_kind")) == "confirmed"
        changes = (len([x for x in new_xi if not _in(x, old_xi)])
                   if (confirmed and new_xi and old_xi) else None)
        dropped = [x for x in old_sq if new_sq and not _in(x, new_sq)]
        facts.append(_squad_fact(team, changes, old_xi, old_sq, was,
                                 dropped=dropped,
                                 kind=now.get("lineup_kind")))
        logger.info("[classify] %s 명단 대조 — 선발 교체 %s · 사라진 %d명 %s",
                    team, changes, len(dropped), dropped[:4])


def _in(name: str, pool: list) -> bool:
    """🔴 이름 대조는 `ids.name_key` 가 원본이다 — 표기가 갈려도 같은 사람이다."""
    from app import ids
    key = ids.name_key(name)
    return bool(key) and key in {ids.name_key(x) for x in pool}


def _squad_fact(team: str, changes, old_xi: list, old_sq: list, was: dict,
                *, dropped: list | None = None, kind=None):
    from app.blackboard import Fact
    return Fact(
        question_id="lineup:squad_rotation",
        value={"team": team, "xi_changes": changes,
               "dropped": list(dropped or []),
               "baseline_xi": len(old_xi), "baseline_squad": len(old_sq),
               "from_match": was.get("from_match"),
               "lineup_kind": kind},
        hardness="likely" if changes is not None else "soft",
        source="", publisher="fotmob", published_at=None,
        article_title=f"{team} 명단 대조", extracted_by="rule:squad_change",
        step=2, team=team)


def _dir_lineup_value(val: dict, g: Game) -> tuple[Direction | None, str, str]:
    """🔴 가치가 떨어진 팀의 **반대 방향**(§4 `direction_rule` 그대로).

    ⚠️ **올라간 쪽은 변수로 세지 않는다** — 평소보다 센 XI 를 내는 것은 흔하고
       (복귀·총력) 그것은 `lineup_intent` 가 본다. 여기서 두 번 세면 부풀린다.
    🔴 문턱은 yaml 이 정한다(`value_drop_pct`) — 작은 차이를 변수로 세면 **모든
       경기에 변수가 생기고** 그것은 변수가 아니다.
    """
    pct = val.get("pct")
    if pct is None:
        return None, "", "라인업 가치를 못 쟀다"
    if str(val.get("lineup_kind")) != "confirmed":
        return None, "", ("확정 XI 가 아니다 — 예상 XI 로 가치 하락을 말하지 않는다")
    floor = float((rules.variable_types().get("lineup_value") or {})
                  .get("value_drop_pct") or 0)
    if float(pct) > -floor:
        return None, (f"§4 lineup_value — 오늘 선발 가치 {pct:+.1f}% "
                      f"(문턱 -{floor:g}%) · 평소와 비슷하다고 본다"), ""
    other, bad = _other_side(g, val.get("team"))
    if other is None:
        return None, "", bad
    return other, (f"§4 lineup_value '가치가 떨어진 팀 반대 방향' — "
                   f"{val.get('team')} 선발 가치 {pct:+.1f}% "
                   f"(오늘 {val.get('today_value'):,} · 기준 "
                   f"{val.get('baseline_value'):,})"), ""


DIRECTION_OF = {
    "stakes": _dir_stakes,
    "home_field": _dir_home_field,
    "absence": _dir_absence,
    "individual": _dir_individual,
    "travel_schedule": _dir_travel,
    "recent_pattern": _dir_recent,
    "h2h_pattern": _dir_h2h,
    "match_type": _dir_match_type,
    "coach_change": _dir_coach_change,
    # 🔴 사용자 지시 2026-10-02 — 여덟을 더했다(위 함수들의 독스트링이 근거다)
    "pitcher_state": _dir_pitcher_state,
    "lineup_intent": _dir_lineup_intent,
    "event_match": _dir_event_match,
    "emotion": _dir_emotion,
    "venue_weather": _dir_venue_weather,
    "def_absence": _dir_def_absence,
    "squad_rotation": _dir_squad_rotation,
    "national_duty_return": _dir_national_duty,
    # 🔴 딥서치 2026-10-03 — 라인업 시장가치(λ 에는 안 닿는다 · 변수로만)
    "lineup_value": _dir_lineup_value,
}

#: 🔴 **경기 단위 유형** — 한 경기에 **한 번**인 사실이다.
#
#  `home_field`      리그의 홈 우위. 팀과 무관하다 — 순위표 사실이 팀마다 와도 하나다
#  `travel_schedule` 양 팀 휴식일 **비교**. 비대칭 하나를 두 팀 시선으로 두 번 적을 수 없다
#
#  ⚠️ 나머지는 **팀 단위**다 — `recent_pattern` 은 두 팀의 폼이 각자 다른 사실이고
#     둘이 같은 방향을 밀 수 있다(그것은 이중 계산이 아니다).
#
#  🔴🔴 **`h2h_pattern` 을 더했다**(실측 2026-10-03). 맞대결은 **두 팀 사이의 한
#     사실**이다 — 그런데 깊이 세포가 팀마다 돌아 같은 맞대결이 **사실 둘**로 오고,
#     그 둘이 변수 둘이 됐다:
#       콜–파: `R1 [h2h_pattern·home]` + `R5 [h2h_pattern·home]` (같은 10경기)
#       NPB:  `R3 [h2h_pattern·away]` + `R4 [h2h_pattern·away]` (같은 22경기)
#     → 방향 묶음의 strength 가 그만큼 **부풀었다.**
#  ⚠️ 종전에는 두 사실의 `why` 가 **글자까지 같아서** 우연히 지워지고 있었다.
#     전반 연속 리드를 사유에 적자(팀마다 다르다) 그 우연이 깨져 드러났다.
GAME_LEVEL = frozenset({"home_field", "travel_schedule", "h2h_pattern"})

#: 🔴 **아직 구현하지 않은 §4 유형 — 이름으로 남긴다**(조용한 0 금지 · #7).
#   ⚠️ `pitcher_state`·`venue_weather` 는 `total_hint` 라 §4 가 총점 힌트로 두었고,
#      총점 방향은 변수에 붙이지 않는다 → **배경**으로 갈 자리다.
NOT_CLASSIFIED = {
    # 🔴 **남은 둘만 여기 있다.** 사용자 지시 2026-10-02(*"한꺼번에 전부다 수정"*)로
    #    나머지 여덟은 `DIRECTION_OF` 로 올라갔다 — 각 함수 독스트링이 근거다.
    "strength_gap": "리그 등급 차를 아직 자료로 안 받는다 — 어느 소스도 등급을 안 준다",
    # ⚠️ 이것은 **구현 못 한 것이 아니라 §4 가 양방향으로 못 박은 것**이다.
    #    응집이 오를 수도 분위기가 내릴 수도 있어 한쪽으로 정하면 지어내는 것이다.
    "coach_conflict": "§4 가 양방향으로 둔 유형 — 한쪽으로 정하지 않는다(선언대로)",
}


# ══════════════════════════════════════════════════════════════════
# 사실 → 유형 후보
# ══════════════════════════════════════════════════════════════════
#
# 🔴 우리 사실은 **질문 id 접미사**로 갈려 있다(`cells.SUB_QUESTIONS`). 그 접미사가
#    어떤 §4 유형의 후보인가를 여기서 잇는다.
# ⚠️ **한 사실이 여러 유형을 낼 수 있다.** 순위표 하나가 `stakes`(순위)와
#    `home_field`(홈/원정 쪼갠 기록)를 둘 다 담는다.
# 🔴 **총점 패턴은 유형이 없다 → 배경**(§4: 총점 방향은 변수에 안 붙인다).

TYPES_OF_SUFFIX: dict[str, tuple[str, ...]] = {
    "standings": ("stakes", "home_field"),
    "form": ("recent_pattern", "travel_schedule"),
    "h2h": ("h2h_pattern",),
    "player": ("individual",),
    # 🔴 아래는 **배경**이다 — 방향을 못 미는 자료다
    "stats": (),         # 점유율·유효슛 = 총점·경기 통계
    "past_stats": (),    # 직전 경기 팀 통계 = 같음
    # 🔴 구장·날씨 → `venue_weather`. ⚠️ 전에 `()` 였다 — 그래서 날씨가 **카드에
    #    한 줄도 안 올라갔다**(실측 2026-10-02: 사용자는 그 날씨를 확정 사실로 썼다).
    "info": ("venue_weather",),
    #: 🔴 예고 선발 → `pitcher_state`
    "starter": ("pitcher_state",),
    #: 🔴 묶음이 만든 사실 — 라인업 시장가치(딥서치 2026-10-03)
    "lineup_value": ("lineup_value",),
    #: 🔴 묶음이 만든 사실 — 명단 대조(사용자 지적 2026-10-03)
    "squad_rotation": ("squad_rotation",),
    "baseline": (),      # 기준 XI = 변수의 **바탕**이지 변수가 아니다
}

#: 접미사가 없는 사실(세포의 주 질문)의 유형. 🔴 `cells.Q_*` 어휘다.
TYPES_OF_QTYPE: dict[str, tuple[str, ...]] = {
    "absence": ("absence",),
    "lineup": (),        # 확정 XI 자체는 변수가 아니다 — 바탕이다
    "intent": ("lineup_intent",),       # 🔴 감독 발언 → §4 lineup_intent
    "standings": ("stakes", "home_field"),
    "starter_recent": (),
    "counter": (),
    "live_score": (),
    "slate": (),
}


def types_for(question_id: str) -> tuple[str, ...]:
    """이 사실이 어떤 §4 유형의 후보인가. 🔴 모르면 빈 tuple(= 배경)."""
    head, _, suffix = str(question_id or "").rpartition(":")
    if suffix in TYPES_OF_SUFFIX:
        return TYPES_OF_SUFFIX[suffix]
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **접미사가 §4 유형 이름이면 그것이 유형이다** (실측 2026-10-02)
    # ══════════════════════════════════════════════════════════════════
    #
    #  카탈로그 세포(③ 좁은 질문)의 질문 id 는 `counter:{리그}:{팀}:{날짜}:{유형}` 이다.
    #  🔴 그런데 `TYPES_OF_QTYPE["counter"]` 가 `()` 여서, **좁은 질문이 답을 가져와도
    #     유형이 안 붙고 전부 배경으로 떨어졌다.** 다섯 유형을 새로 구현해도 그
    #     답이 변수가 될 길이 없었다 — 이것이 그 길이다.
    #  ⚠️ **목록을 손으로 적지 않는다** — §4 표(yaml)에서 자란다(CLAUDE.md #1 사본 금지).
    if suffix in rules.variable_types():
        return (suffix,)
    # 🔴 `…:coach` 는 감독 교체다(`searchcells.coach_cell` 의 규약)
    if suffix == "coach":
        return ("coach_change",)
    qtype = str(question_id or "").split(":")[0]
    return TYPES_OF_QTYPE.get(qtype, ())


def _hardness_cap(vtype: str, val: dict, hardness: str) -> tuple[str, str]:
    """표본 수로 hardness 를 깎는다. 🔴 **weight 가 아니라 hardness 다.**

    `types.Variable` 이 `weight == WEIGHT_OF[hardness]` 를 강제하므로 §4 의
    `sample_weight`(1.0/0.7/0.4)를 weight 에 직접 못 넣는다. ⚠️ 그런데 그 셋은
    `hard/likely/soft` 의 weight 와 **똑같다** — 작은 표본은 더 약한 주장이므로
    hardness 로 말하는 것이 더 맞다.
    """
    if vtype == "h2h_pattern":
        from app import league
        # 🔴🔴 **표본 수도 칸 이름이 갈린다**(실측 2026-10-04).
        #    ⚠️ 종전은 `window_games`·`window` **둘만** 봤다. MLB·NHL 은
        #       `matches`·`count` 를 쓴다 — 그래서 13경기를 받아 놓고 표본을
        #       **0경기**로 세어 hardness 를 soft 까지 깎았다(카드 원문:
        #       *"창 13경기 … 맞대결 표본 0경기 → hardness hard→soft"*).
        #    🔴 `_dir_h2h` 가 읽는 칸(`window` 또는 `matches`)과 **같은 것을** 센다.
        # 🔴 **정본 이름만**(§8-3) — `count` 와 `matches` 다. 종전에는
        #    fotmob 고유 칸(`window_games`·`window`)을 먼저 봤다(#6).
        n = int(val.get("count") or len(val.get("matches") or []) or 0)
        w = league.h2h_weight(n)
        floor = {1.0: "hard", 0.7: "likely", 0.4: "soft"}.get(w, "soft")
        got = _cap(hardness, floor)
        if got != hardness:
            return got, f"맞대결 표본 {n}경기 → hardness {hardness}→{got}(§4 sample_weight)"
        return got, ""
    if vtype == "recent_pattern":
        # ══════════════════════════════════════════════════════════
        # 🔴🔴 **표본이 낡으면 약한 주장이다**(사용자 지시 2026-10-04)
        # ══════════════════════════════════════════════════════════
        #
        #  > R1 "밀워키 최근 3경기 3승" 은 **7일 전 정규시즌 마지막 경기들**이다.
        #  > 바이로 쉰 팀의 "최근 폼" 은 표본이 낡았다.
        #
        #  🔴 **날짜를 센다** — `rest_days`(마지막 경기로부터 며칠)가 폼 사실에
        #     이미 들어 있다(`mlb`·`nhl`·`fotmob` 셋 다 낸다).
        #  ⚠️ 문턱·내릴 등급은 **yaml 이 정한다**(사본 금지).
        cfg = rules.variable_types().get("recent_pattern") or {}
        days = val.get("rest_days")
        # 🔴 §5-6 — 수는 `config/thresholds.yaml` 이 들고 **근거를 함께** 든다.
        #    ⚠️ `variable_types.yaml` 의 값이 있으면 그것이 이긴다(유형별 선언) —
        #       없으면 `thresholds` 가 답한다. 🔴 어느 쪽이든 **근거가 있다.**
        floor_days = cfg.get("stale_days")
        if floor_days is None:
            from app import thresholds as _th
            floor_days = _th.value("stale_days")
        # 🔴 **못 쟀으면 이름으로 남긴다**(#3 조용한 0 금지). ⚠️ 조용히
        #    `False` 로 떨어뜨리면 *"낡지 않았다"* 와 *"며칠인지 모른다"* 가
        #    같아 보인다 — 그 둘은 고칠 곳이 다르다(규칙 vs 수집).
        #  ⚠️ 🔴 **여기서 돌아가지 않는다** — 아래 §7 R7(표본 3경기 미만)이
        #     **더 센 조건**이고, 돌아가면 그 검사를 건너뛴다(실측 2026-10-04:
        #     내가 그렇게 짰고 `test_표본이_작으면_hardness_를_깎는다` 가 잡았다).
        stale_note = ""
        if floor_days is not None:
            try:
                n_days = int(days)
            except (TypeError, ValueError):
                stale_note = (f"⚠️ 휴식일을 몰라 **표본 낡음을 못 쟀다**"
                              f"(문턱 {floor_days}일 · rest_days={days!r})")
            else:
                if n_days >= int(floor_days):
                    to = str(cfg.get("stale_hardness") or "soft")
                    got = _cap(hardness, to)
                    if got != hardness:
                        stale_note = (f"마지막 경기가 **{n_days}일 전**이다"
                                      f"(문턱 {floor_days}일) — 표본이 낡았다 → "
                                      f"hardness {hardness}→{got}")
                        hardness = got
        n = len(last5_of(val)[0])
        if 0 < n < RECENT_SOFT_UNDER:
            got = _cap(hardness, "soft")
            why = f"최근 {n}경기 → hardness {hardness}→{got}(§7 R7)"
            # 🔴 **둘을 함께 적는다** — 표본이 작고 **또** 낡았을 수 있다
            return got, (f"{why} · {stale_note}" if stale_note else why)
        if stale_note:
            return hardness, stale_note
    return hardness, ""


def types_from_text(text: str) -> tuple[tuple[str, ...], str]:
    """🔴🔴 **산문 → §4 유형들**(사용자 기술 지시 2026-10-03 · ② 유형 판정).

    > 사건 단어 → 변수 유형. **LLM이 아니라 표로 정한다.**

    돌려주는 것: `((유형, …), 사유)`. 못 정하면 `((), 사유)`.

    ══════════════════════════════════════════════════════════════════
    🔴 왜 **여럿**을 돌려주나 — 회귀 시험이 가르쳐 줬다
    ══════════════════════════════════════════════════════════════════

    처음엔 *"둘 이상 맞으면 모호하니 안 고른다"* 로 짰다. 🔴 그런데 사용자 분석
    자신이 한 문장에서 **둘을 꺼낸다**:

    ```
    이기는 이유: 고영표 다승 동기(individual), **매직+4연승(stakes·recent_pattern)**
    ```
    ⚠️ `KT 매직 넘버 2 … 4연승` 은 모호한 것이 아니라 **사실이 둘**이다. 하나를
       고르는 것이 추측이고, **버리는 것은 더 나쁘다**(그 글이 말한 것을 지운다).

    🔴 그리고 **좁은 유형이 넓은 유형을 이긴다**(`refines:`). 실측 2026-10-03:
       `Jamaica defender ruled out with injury` 가 `absence`·`def_absence` 둘 다에
       맞았다 — 그 둘은 모순이 아니라 **포함 관계**다. 좁은 쪽만 남긴다.
       ⚠️ 그 관계는 **yaml 이 선언한다** — 코드가 유형 이름 쌍을 외우지 않는다.
    """
    body = " ".join(str(text or "").split())
    if not body:
        return (), "글이 비어 유형을 못 정한다"
    hit = [name for name, pats in rules.type_patterns()
           if any(p.search(body) for p in pats)]
    if not hit:
        return (), "유형 규칙표의 어느 낱말도 안 맞았다"
    # 🔴 좁은 유형이 있으면 그것이 가리키는 **넓은 유형을 걷는다**
    narrowed = {str((rules.variable_types().get(n) or {}).get("refines") or "")
                for n in hit}
    kept = tuple(n for n in hit if n not in narrowed)
    why = f"§4 유형 규칙표 — 사건 낱말이 `{'`, `'.join(kept)}` 에 맞았다"
    if len(hit) != len(kept):
        why += f" (넓은 유형 {sorted(narrowed & set(hit))} 는 좁은 쪽이 대신한다)"
    return kept, why


def classify_fact(fact, game: Game) -> list[Classified]:
    """사실 하나 → §4 적용 결과들. 🔴 **못 정한 것도 사유와 함께 돌려준다.**

    ⚠️ 빈 목록을 돌려주지 않는다 — 그러면 "자료가 없었다"와 "분류를 못 했다"가
       구분되지 않는다(조용한 0 금지).
    """
    val = fact.value if isinstance(fact.value, dict) else {}
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **인용이 `Fact.quote` 에 있는데 `value` 가 문자열이면 잃어버린다**
    # ══════════════════════════════════════════════════════════════════
    #
    #  실측 2026-10-03(KBO): 카드가 *"감독 발언 원문이 없다 — 낱말을 대조할 수
    #  없다"* 를 **일곱 번** 적었다. 🔴 그런데 인용은 **있었다**:
    #
    #    [bb] intent:KBO:LG Twins ← We can't avoid getting hit. So we have to
    #                               take control and attack first.
    #
    #  ⚠️ `parse_intent_body` 가 `Fact(value=<인용 문자열>, quote=<인용>)` 로 넣는데
    #     여기서는 `value` 가 dict 가 아니면 **빈 dict** 로 두었다. 그래서 방향
    #     규칙이 `val["quote"]` 를 못 찾았다 — 자료가 아니라 **그릇이 문제였다.**
    #  🔴 `Fact` 가 들고 있는 칸으로 **채워 준다**. 지어내는 것이 아니다 — 같은
    #     사실의 다른 주머니에서 꺼내는 것이다.
    if not val:
        got = {k: v for k, v in (
            ("quote", getattr(fact, "quote", None)),
            ("team", getattr(fact, "team", None)),
            ("player_name", getattr(fact, "player_name", None))) if v}
        if got:
            val = got
    base = dict(text=str(val.get("text") or _summary(fact, val)),
                source_url=str(getattr(fact, "source", "") or ""),
                hardness=str(getattr(fact, "hardness", "soft")),
                published_at=getattr(fact, "published_at", None),
                team=val.get("team") or getattr(fact, "team", None))
    cands = types_for(getattr(fact, "question_id", ""))
    if not cands:
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **질문이 유형을 못 주면 산문을 본다**(사용자 기술 지시 2026-10-03)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 질문 경로가 **먼저**다 — 그 세포는 자기가 뭘 묻는지 안다. 이 표는
        #     그쪽이 비었을 때의 **대체**다(§19-b-4 와 같은 결).
        #  🔴 못 정하면 **그대로 배경**이고, **왜 못 정했는지**가 사유에 남는다 —
        #     "규칙표에 낱말이 없다"와 "두 유형에 걸렸다"는 처방이 다르다.
        guess, why_t = types_from_text(base["text"])
        if guess:
            # 🔴 **여럿이면 여럿 그대로** 넘긴다 — 한 문장이 사실 둘을 말할 수 있다
            #    (사용자 분석: *"매직+4연승(stakes·recent_pattern)"*)
            cands = tuple(guess)
        else:
            return [Classified(**base, undecided="",
                               why=f"§4 유형이 없는 자료 — 배경으로 둔다 "
                                   f"({getattr(fact, 'question_id', '?')} · {why_t})")]
    out: list[Classified] = []
    for vtype in cands:
        if vtype in NOT_CLASSIFIED:
            out.append(Classified(**base, type=vtype,
                                  undecided=NOT_CLASSIFIED[vtype]))
            continue
        fn = DIRECTION_OF.get(vtype)
        if fn is None:
            out.append(Classified(**base, type=vtype,
                                  undecided=f"{vtype} 방향 규칙이 구현되지 않았다"))
            continue
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **발견이 팀을 잃고 있었다** (실측 2026-10-02)
        # ══════════════════════════════════════════════════════════════
        #
        #  좁은 질문(③)의 값에는 `team` 칸이 **없다** — `{ask, answer, quote,
        #  player_name}` 뿐이다. 팀은 **사실(`Fact.team`)** 에 실려 온다.
        #  🔴 그런데 방향 규칙은 `val["team"]` 을 봤다. 그래서 봇이 스스로 찾아낸
        #     `唐川侑己 은퇴 세레머니` 가 *"어느 팀 이야기인지 모른다"* 로 떨어졌다 —
        #     세포는 그 팀을 알고 있었다(`Question.team`).
        #  ⚠️ `val` 을 **덮지 않는다** — 사본을 만들어 넘긴다(사실은 그대로 둔다).
        val_for_rule = val if val.get("team") else {**val, "team": base["team"]}
        direction, why, bad = fn(val_for_rule, game)
        hardness, note = _hardness_cap(vtype, val, base["hardness"])
        item = Classified(**{**base, "hardness": hardness}, type=vtype,
                          direction=direction, why=why, undecided=bad)
        if note:
            item.why = (item.why + " · " + note).strip(" ·")
        out.append(item)
    return out


def _summary(fact, val: dict) -> str:
    """사실을 한 줄로. 🔴 값을 지어내지 않는다 — 있는 칸만 잇는다."""
    qid = str(getattr(fact, "question_id", "") or "?")
    bits = [str(val.get(k)) for k in ("team", "player") if val.get(k)]
    for k in ("rank", "rest_days", "count", "goals", "assists",
              "season_goals", "last5"):
        if val.get(k) is not None:
            bits.append(f"{k}={val[k]}")
    return f"{qid} — " + (" · ".join(bits) if bits else "(칸 없음)")


def split_draw(items: list[Classified]) -> list[Classified]:
    """§4 `splits_direction` — **두 방향을 밀면 두 항목으로 나눈다.**

    🔴 지금 그 유형은 `coach_change` 다(*"새 감독 팀 쪽 **+ 무승부**"*).
    ⚠️ `stakes` 도 `splits_direction` 이지만 나누는 자리가 다르다 — **팀마다 사실이
       하나씩** 오므로(순위표를 팀별로 읽는다) 자연히 두 항목이 된다. 사용자 지시
       2026-10-02 의 `splits_only_when`(양쪽이 서로 다른 것을 걸고 있다)이 그 뜻이다.
    """
    types = rules.variable_types()
    out = list(items)
    for it in items:
        if not (it.type and it.direction and it.direction != "draw"):
            continue
        cfg = types.get(it.type) or {}
        if not cfg.get("splits_direction"):
            continue
        if "무승부" not in str(cfg.get("direction_rule") or ""):
            continue      # 🔴 `stakes` 처럼 무승부를 안 미는 유형은 안 나눈다
        out.append(Classified(
            text=it.text, source_url=it.source_url, hardness=it.hardness,
            type=it.type, direction="draw", published_at=it.published_at,
            why=it.why + " · §4 splits_direction(무승부 쪽)", team=it.team))
    return out


# ══════════════════════════════════════════════════════════════════
# 🔴 묶음 단위 — 한 사실만 보면 못 정하는 것들
# ══════════════════════════════════════════════════════════════════


def classify_facts(facts: list, game: Game) -> list[Classified]:
    """사실 묶음 → §4 적용. 🔴 **묶음을 봐야 정해지는 것이 둘 있다.**

    | 무엇 | 왜 묶음이어야 하나 |
    |---|---|
    | `individual` 의 **팀 최다 득점자** | 한 선수만 보면 '최다'인지 알 수 없다 |
    | `travel_schedule` 의 **양 팀 휴식일** | 한 팀 것만으론 누가 피로한지 모른다 |

    그리고 §12-c-4 — *"같은 보도자료 8건은 원문 1건이다."* 🔴 같은 사실이 여러 번
    오면 **방향 묶음의 strength 가 부풀어** 단계 6 이 속는다. 여기서 지운다.
    """
    seen: set[tuple] = set()
    uniq = []
    for f in facts:
        # 🔴 **내용으로 지운다 — 출처를 열쇠에 넣지 않는다.**
        #    §12-c-4: *"같은 보도자료 8건은 원문 1건이다."* 출처를 열쇠에 넣으면
        #    같은 자료가 주소만 달라도 두 번 센다.
        #    ⚠️ 실측 2026-10-02: fotmob 이 같은 경기를 `/matches/…` 와
        #       `/en-GB/matches/…` 로 준다. 그 둘을 못 지워 모든 변수가 **두 번**
        #       세어졌고, 그 탓에 `individual` 의 **팀 최다 득점자 판정까지 깨졌다**
        #       (같은 이름이 둘이라 '동률'로 읽혔다).
        key = (str(getattr(f, "question_id", "")), str(f.value)[:400])
        if key in seen:
            continue
        seen.add(key)
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **표기만 달라도 같은 보도다**(사용자 기술 지시 2026-10-03 · 기술 6)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 같은 보도자료가 8개 매체에 복사되면 출처 **8개가 아니라 1개**다.
        #  > **문장 유사도**로 묶은 뒤 센다.
        #
        #  ⚠️ 위 열쇠는 **완전 일치**다 — 구두점 하나만 달라도 별건이 되어 같은
        #     보도가 변수 여럿으로 세어졌고 방향 묶음 strength 가 부풀었다.
        #  🔴 같은 질문 안에서 **유사도로** 한 번 더 지운다(묶는 규칙은
        #     `blackboard.similar` 가 원본이다 — 여기서 다시 쓰지 않는다).
        if _same_report(f, uniq):
            continue
        uniq.append(f)
    dropped = len(facts) - len(uniq)
    if dropped:
        logger.info("[classify] §12-c-4 중복 %d건 지웠다(원문 %d건)",
                    dropped, len(facts))

    _mark_top_scorer(uniq, game)
    _fill_rest_days(uniq, game)
    _fill_pitchers(uniq, game)
    _fill_lineup_value(uniq, game)
    _fill_squad_change(uniq, game)
    _fill_half_time(uniq, game)

    out: list[Classified] = []
    for f in uniq:
        out += split_draw(classify_fact(f, game))
    out = _dedupe_variables(out)
    # 🔴🔴 §4 `attaches_to: invalidate_recent_form` — **여기서 읽는다**
    _invalidate_recent(out)
    return out


#: §4 `attaches_to` 의 작동 이름. 🔴 원본은 yaml 이다 — 유형 이름을 손으로 안 적는다.
INVALIDATE_RECENT = "invalidate_recent_form"


def starters_for(standings: dict | None, game: Game) -> dict | None:
    """🔴 **선발 보정의 입력을 홈/원정으로 가른다**(딥서치 2026-10-03 · A).

    돌려주는 꼴은 `league.starter_factor` 가 받는 그대로다:
    `{"home": {era_starter, era_team, innings}, "away": {…}}`.

    ⚠️ **누가 누구를 막나는 `league.expected_goals` 가 교차시킨다** — 여기서는
       *"홈팀의 선발"* · *"원정팀의 선발"* 만 가른다. 두 곳에서 교차하면 두 번
       뒤집혀 조용히 원래대로 돌아간다.
    🔴 한쪽이라도 못 채우면 그 쪽만 비운다 — `starter_factor` 가 `None` 을 내고
       사유가 카드에 남는다(반쪽으로 모형을 돌리지 않는다).
    """
    rows = (standings or {}).get("starter_rows") or []
    out: dict[str, dict] = {}
    for r in rows:
        side = game.side_of(r.get("team"))
        if side is None or side in out:
            continue
        out[side] = {"era_starter": r.get("era"),
                     "era_team": r.get("team_era"),
                     "innings": r.get("innings"),
                     # 🔴 **표본 문턱의 재료** — 그 해 총 투구 이닝
                     "season_innings": r.get("season_innings")}
        # 🔴 상대 칸도 같은 사실에 실려 온다 — 반대쪽이 비면 그것으로 채운다
        other = "away" if side == "home" else "home"
        if other not in out and r.get("opponent_era") is not None:
            out[other] = {"era_starter": r.get("opponent_era"),
                          "era_team": r.get("opponent_team_era"),
                          "innings": r.get("opponent_innings"),
                          "season_innings": r.get("opponent_season_innings")}
    return out or None


def _invalidate_recent(items: list[Classified]) -> None:
    """§4 `invalidate_recent_form` — 최근 N경기 **표본을 무효화한다.**

    ══════════════════════════════════════════════════════════════════
    🔴 왜 이 함수가 생겼나 (2026-10-02)
    ══════════════════════════════════════════════════════════════════

    `national_duty_return` 의 `attaches_to` 에 `invalidate_recent_form` 이라고
    적혀 있었고 **그 이름을 읽는 코드가 없었다.** 즉 *"대표팀에 갔던 선수가
    돌아오면 최근 N경기 표본이 그 선수 없이 쌓인 것이라 무효"* 라는 규칙이
    장식이었다.

    🔴 무효화 = `recent_pattern` 변수를 **미결정으로 내린다**(지우지 않는다).
       사유를 적어 두므로 카드가 *"왜 폼이 변수가 아닌가"* 를 말할 수 있다.
    ⚠️ **그 팀만** 무효화한다 — 상대 팀 폼은 그대로다.
    """
    hits = [c for c in items
            if c.type and rules.attaches_to(c.type) == INVALIDATE_RECENT
            and not c.undecided
            and str(c.why or "").startswith(f"§4 {c.type}")]
    if not hits:
        return
    for h in hits:
        for c in items:
            if c.type != "recent_pattern" or not c.is_variable:
                continue
            # 🔴 같은 팀의 폼만 — 팀을 모르면 **건드리지 않는다**(§11-3)
            if not (h.team and c.team and str(h.team) == str(c.team)):
                continue
            c.undecided = (f"§4 {INVALIDATE_RECENT} — {h.type} 가 발동해 최근 "
                           f"경기 표본이 무효다({str(h.why)[:60]})")
            c.direction = None
            logger.info("[classify] %s 의 recent_pattern 을 무효화했다 — %s",
                        c.team, h.type)


def _same_report(f, kept: list) -> bool:
    """🔴 이미 받은 것 중 **같은 보도**가 있나(기술 6).

    ⚠️ **같은 질문 안에서만** 본다 — 다른 질문의 같은 문장은 다른 사실이다
       (감독 발언 기사가 결장도 말할 수 있다).
    """
    from app.blackboard import DUP_SIMILARITY, similar
    qid = str(getattr(f, "question_id", ""))
    mine = str(getattr(f, "quote", "") or "") or \
        str(getattr(f, "article_title", "") or "")
    if not mine:
        return False
    for g in kept:
        if str(getattr(g, "question_id", "")) != qid:
            continue
        theirs = str(getattr(g, "quote", "") or "") or \
            str(getattr(g, "article_title", "") or "")
        if theirs and similar(mine, theirs) >= DUP_SIMILARITY:
            logger.info("[classify] 같은 보도를 지웠다 — %s", mine[:50])
            return True
    return False


def _dedupe_variables(items: list[Classified]) -> list[Classified]:
    """같은 변수를 두 번 세지 않는다(§12-c-4).

    🔴 **리그 사실은 경기 하나에 한 번이다.** `home_field` 는 리그의 홈 우위이고
       팀과 무관한데, 순위표 사실이 **팀마다 하나씩** 오므로 같은 변수가 두 번 나왔다
       (실측 2026-10-02). 방향 묶음의 strength 가 그만큼 부풀고 단계 6 이 속는다.
    ⚠️ 배경·미결정은 **지우지 않는다** — 그것은 세는 수가 아니라 기록이다.
    """
    seen: set[tuple] = set()
    out: list[Classified] = []
    for it in items:
        if not it.is_variable:
            out.append(it)
            continue
        # 🔴 **경기 단위 유형은 `(유형, 방향)` 으로만 센다.** 한 경기에 한 번인 사실을
        #    양쪽 시선에서 두 번 적으면 그만큼 strength 가 부푼다.
        #    ⚠️ 실측 2026-10-02: `travel_schedule` 이 *"새크라멘토 4일 vs 상대 11일"* 과
        #       *"라스베이거스 11일 vs 상대 4일"* 로 **같은 비대칭을 두 번** 냈다.
        key = ((it.type, it.direction) if it.type in GAME_LEVEL
               else (it.type, it.direction, it.why))
        if key in seen:
            logger.info("[classify] 같은 변수 지웠다 — %s %s", it.type, it.direction)
            continue
        seen.add(key)
        out.append(it)
    return out


def _mark_top_scorer(facts: list, game: Game) -> None:
    """팀마다 **시즌 최다 득점자**를 표시한다. 🔴 동률이면 **아무도 표시하지 않는다** —
    '최다'가 여럿이면 두드러짐이 아니다.
    """
    best: dict[str, tuple[int, list[str]]] = {}
    for f in facts:
        v = f.value if isinstance(f.value, dict) else {}
        if not str(getattr(f, "question_id", "")).endswith(":player"):
            continue
        sg, team, who = v.get("season_goals"), v.get("team"), v.get("player")
        if sg is None or not team or not who:
            continue
        top, names = best.get(team, (-1, []))
        if int(sg) > top:
            best[team] = (int(sg), [who])
        elif int(sg) == top:
            best[team] = (top, names + [who])
    for f in facts:
        v = f.value if isinstance(f.value, dict) else {}
        if not str(getattr(f, "question_id", "")).endswith(":player"):
            continue
        top, names = best.get(v.get("team") or "", (-1, []))
        # 🔴 동률이면 표시하지 않는다
        if len(names) == 1 and v.get("player") == names[0] and top > 0:
            v["top_scorer"] = True


def _fill_pitchers(facts: list, game: Game) -> None:
    """`:starter` 사실에 **두 선발의 방어율**을 채운다(§4 `pitcher_state`).

    🔴 **왜 묶음이어야 하나**: 방어율은 다른 사실(`:pitcher_table`)에 있다. 한 사실만
       보면 선발이 누구인지는 알아도 그가 어떤 투수인지는 모른다.
    ⚠️ 표에 **없는 투수가 있다** — 규정 투구 이닝 미달이면 성적표에 안 실린다
       (실측 2026-10-02: 前田悠伍 12승 1패가 `pit_p.html` 에 없었다). 그러면 채우지
       않고 그대로 둔다 → `_dir_pitcher_state` 가 **미결정**으로 적는다.
    🔴 이름 대조는 **정확 일치 → 성(姓) 일치** 두 단계다. 일정 페이지는 성만 쓴다
       (`先発：田中`)고 성적표는 성명을 쓴다(`田中晴也`). ⚠️ 성이 여럿이면 **아무도
       고르지 않는다** — 동성이 둘이면 누구인지 모르는 것이다.
    """
    table: dict[str, dict] = {}
    teams: dict[str, dict] = {}
    #: 🔴 선수 페이지에서 온 성적 — **리더보드보다 센다**(아래 `table.update`)
    solo: dict[str, dict] = {}
    for f in facts:
        v = f.value if isinstance(f.value, dict) else {}
        qid = str(getattr(f, "question_id", ""))
        if qid.endswith(":pitcher_table"):
            table.update(v.get("pitchers") or {})
        elif qid.endswith(":team_pitching"):
            teams.update(v.get("teams") or {})
        elif qid.endswith(":starter_stats") and v.get("player"):
            # 🔴🔴 **선수 페이지 성적이 리더보드를 이긴다** — 리더보드에는 규정
            #    투구 투수만 있고(실측 2026-10-03: 선발 둘 다 없었다), 선수 페이지는
            #    **그 투수의 그 해** 성적이다. 같은 칸 이름으로 맞춰 둔다.
            solo[" ".join(str(v["player"]).split())] = v
    # 🔴 선수 페이지가 있으면 그것을 표에 얹는다(리더보드를 덮는다)
    table.update(solo)
    if not table:
        return

    def _team_era(team: str) -> float | None:
        """🔴 **팀 ERA** — `league.starter_factor` 의 분모다.

        ⚠️ 팀 표는 **약칭**을 쓴다(`ソフトバンク`)고 경기 표는 정식명이다
           (`福岡ソフトバンクホークス`). 부분 일치로 잇는다 — 정확 일치를 요구하면
           이 칸이 늘 비고, 그러면 선발 보정이 영영 안 걸린다.
        🔴 둘 이상 걸리면 **아무도 고르지 않는다**(누구인지 모르는 것이다).
        """
        want = " ".join(str(team or "").split())
        if not want:
            return None
        hits = [v.get("era") for k, v in teams.items()
                if k and (k in want or want in k)]
        hits = [x for x in hits if x is not None]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            logger.info("[classify] 팀 ERA 가 %s 에 %d개 걸렸다 — 안 쓴다",
                        want, len(hits))
        return None

    def _row(name: str) -> dict:
        """그 투수의 표 줄. 🔴 성만 알 때는 **유일할 때만** 쓴다."""
        nm = " ".join(str(name or "").split())
        if not nm:
            return {}
        got = table.get(nm)
        if got:
            return got
        hits = [v for k, v in table.items() if k.startswith(nm)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            logger.info("[classify] 선발 `%s` 와 성이 같은 투수가 %d명 — "
                        "방어율을 안 채운다", nm, len(hits))
        return {}

    for f in facts:
        v = f.value if isinstance(f.value, dict) else {}
        if not str(getattr(f, "question_id", "")).endswith(":starter"):
            continue
        mine, theirs = _row(v.get("player")), _row(v.get("opponent_player"))
        if v.get("era") is None:
            v["era"] = mine.get("era")
        if v.get("opponent_era") is None:
            v["opponent_era"] = theirs.get("era")
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **λ 보정의 재료**(딥서치 2026-10-03 · A)
        # ══════════════════════════════════════════════════════════════
        #
        #  `league.starter_factor` 가 셋을 받는다: 선발 ERA · 팀 ERA · 기대 이닝.
        #  🔴 셋 다 **관측값**이고 맞출 모수가 없다 — 그래서 지어내는 것이 아니다.
        v.setdefault("innings", mine.get("innings_per_game"))
        v.setdefault("opponent_innings", theirs.get("innings_per_game"))
        v.setdefault("season_innings", mine.get("innings"))
        v.setdefault("opponent_season_innings", theirs.get("innings"))
        v.setdefault("team_era", _team_era(v.get("team")))
        v.setdefault("opponent_team_era", _team_era(v.get("opponent_team")))
        logger.info("[classify] 선발 %s(ERA %s · %s이닝 · 팀 %s) vs "
                    "%s(ERA %s · %s이닝 · 팀 %s)",
                    v.get("player"), v.get("era"), v.get("innings"),
                    v.get("team_era"), v.get("opponent_player"),
                    v.get("opponent_era"), v.get("opponent_innings"),
                    v.get("opponent_team_era"))


def _fill_lineup_value(facts: list, game: Game) -> None:
    """🔴 **오늘 선발 가치 ÷ 기준 선발 가치**를 한 사실에 담는다(§4 `lineup_value`).

    ══════════════════════════════════════════════════════════════════
    🔴 왜 묶음이어야 하나 (딥서치 2026-10-03 · 사용자 지시)
    ══════════════════════════════════════════════════════════════════

    두 수가 **다른 사실**에 있다: 오늘 XI 는 경기 페이지(`:lineup`), 기준 XI 는
    직전 경기 페이지(`:baseline`). 한 사실만 보면 *"가치가 떨어졌나"* 를 모른다.

    🔴 자료는 **이미 손에 있었다** — fotmob 라인업의 `marketValue`(실측: 전원).
    ⚠️ **λ 에는 안 넣는다** — 가치를 골 단위로 바꾸는 계수가 발표된 적이 없다
       (`questions/2026-10-03_weight_deepsearch.md`). 변수로만 쓴다.
    🔴 `confirmed` 가 아니면 쓰지 않는다 — 경기 전 **예상 XI** 로 하락을 말하면
       그것이 거짓이다(사용자 글 첫 문장이 그 구분이다).
    """
    cfg = rules.variable_types().get("lineup_value") or {}
    need = int(cfg.get("min_value_players") or 11)
    today: dict[str, dict] = {}
    base: dict[str, dict] = {}
    for f in facts:
        v = f.value if isinstance(f.value, dict) else {}
        if not isinstance(v, dict) or v.get("value_sum") is None:
            continue
        team = str(v.get("team") or "")
        if not team:
            continue
        box = base if v.get("lineup_kind") == "baseline" else today
        # 🔴 **인원이 모자라면 쓰지 않는다** — 일부만 읽히면 합이 작아져 거짓 하락이다
        if int(v.get("value_players") or 0) < need:
            logger.info("[classify] %s 라인업 가치 %d명만 읽었다(필요 %d) — 안 쓴다",
                        team, int(v.get("value_players") or 0), need)
            continue
        box.setdefault(team, v)
    if not (today and base):
        return
    for team, now in today.items():
        was = next((b for k, b in base.items()
                    if verify_mentions(k, team)), None)
        if was is None:
            continue
        a, b = float(now["value_sum"]), float(was["value_sum"])
        if b <= 0:
            continue
        pct = round((a / b - 1.0) * 100.0, 1)
        facts.append(_value_fact(team, now, was, pct))
        logger.info("[classify] %s 라인업 가치 %+.1f%% (오늘 %d · 기준 %d)",
                    team, pct, int(a), int(b))


def verify_mentions(a: str, b: str) -> bool:
    """🔴 팀 이름 대조는 `verify` 가 원본이다 — 여기서 규칙을 다시 쓰지 않는다."""
    from app import verify
    return verify.mentions_team(a, b, None)


def _value_fact(team: str, now: dict, was: dict, pct: float):
    """🔴 묶음이 만든 **새 사실**. 출처는 두 XI 사실이므로 `soft` 다."""
    from app.blackboard import Fact
    return Fact(
        question_id="lineup:lineup_value",
        value={"team": team, "pct": pct,
               "today_value": int(now["value_sum"]),
               "baseline_value": int(was["value_sum"]),
               "from_match": was.get("from_match"),
               "lineup_kind": now.get("lineup_kind")},
        # 🔴 **확정 XI 일 때만 hard 에 가깝다** — 예상 XI 는 바뀐다
        hardness="likely" if now.get("lineup_kind") == "confirmed" else "soft",
        source="", publisher="fotmob", published_at=None,
        article_title=f"{team} 라인업 가치", extracted_by="rule:lineup_value",
        step=2, team=team)


def _fill_rest_days(facts: list, game: Game) -> None:
    """`:form` 사실에 **상대 휴식일**을 채운다. 🔴 양쪽을 알아야 비교가 된다."""
    rest: dict[str, int] = {}
    for f in facts:
        v = f.value if isinstance(f.value, dict) else {}
        if str(getattr(f, "question_id", "")).endswith(":form") \
                and v.get("rest_days") is not None and v.get("team"):
            rest[str(v["team"])] = int(v["rest_days"])
    for f in facts:
        v = f.value if isinstance(f.value, dict) else {}
        if not str(getattr(f, "question_id", "")).endswith(":form"):
            continue
        mine = str(v.get("team") or "")
        side = game.side_of(mine)
        if side is None:
            continue
        other_name = game.away if side == "home" else game.home
        for name, days in rest.items():
            # 🔴 **쪽으로 가린다**(3단계) — 이름끼리 비교하면 언어가 갈릴 때
            #    같은 팀을 "남"으로 본다. `side_of` 는 열쇠를 먼저 보므로
            #    `柏レイソル` 과 `Kashiwa Reysol` 이 같은 쪽으로 떨어진다.
            if game.side_of(name) == game.other(side):
                v["opponent_rest_days"] = days
                break
        else:
            if other_name not in rest:
                logger.info("[classify] %s 의 상대(%s) 휴식일이 없다 — 비교 못 한다",
                            mine, other_name)


# ══════════════════════════════════════════════════════════════════
# ⑨ 가설 + 무너지는 조건 (사용자 출력 블록 5 · 결정 B)
# ══════════════════════════════════════════════════════════════════
#
# 🔴 **새 규칙이 아니다 — §5-a 묶음의 다시 보기다.**
#
# 사용자가 쓴 블록을 뜯어 보면 구조가 §5-a 그대로다:
#
#     새크라멘토 가설:   홈 수비 + 메모 창출 + 에드워즈 후반    ← home 방향 묶음
#     무너지는 조건:     R1·R9 피로 · R7 중원 열세           ← away 방향 묶음
#     라스베이거스 가설: R1·R2·R4·R7                        ← away 방향 묶음
#     무너지는 조건:     메모·에드워즈에 뚫림(R5·R6)          ← home 방향 묶음
#
# ⚠️ v4 §5·§7 에 이 블록이 **없다**(결함 3 = 결정 B). 그런데 §5-a 가 이미 묶음을
#    만들고 있었으므로 **담을 그릇만 없었던 것**이다. 판단을 더하지 않는다.
#
# 🔴 `draw` 방향 변수는 **양 팀 가설을 둘 다 무너뜨린다** — 승리 가설이 둘이고
#    무승부는 그 둘을 다 깨기 때문이다. 어느 한쪽 가설에 넣으면 거짓이 된다.
#
# ⚠️ **문장(narrative)은 쓰지 않는다.** §5-e 가 그 일을 LLM **L6** 에 뒀다
#    (*"변수 텍스트를 이어 붙여 2~3문장 · 스코어·strength 는 코드 값 인용 ·
#    새 사실 추가 금지"*). 🔴 L6 은 아직 안 이어졌다 — `claim` 은 **빈칸**이고,
#    빈칸인 채로 두는 것이 지어내는 것보다 낫다.


@dataclass
class Hypothesis:
    """한 팀의 가설. 🔴 **받치는 변수와 깨는 변수를 함께** 들고 있다."""

    team: str
    side: Direction                      # "home" | "away"
    supports: list[Classified] = field(default_factory=list)
    breaks: list[Classified] = field(default_factory=list)
    #: 🔴 §5-e — 문장은 **LLM L6** 이 쓴다. 코드가 지어내지 않는다
    claim: str = ""
    claim_by: str = "§5-e L6 미배선 — 빈칸으로 둔다"
    #: 🔴🔴 **"이긴다면 왜"** 문장들 — 지시 ② (2026-10-05). DeepSeek 가 쓴다.
    #   ⚠️ 코드가 지어내지 않는다 — 비면 카드가 **번호만** 적고 그 사실이 보인다.
    win_why: list = field(default_factory=list)
    #: 🔴 **"무너지는 조건"** 문장들 — 같은 출처.
    break_why: list = field(default_factory=list)

    @property
    def strength_for(self) -> float:
        return round(sum(c.weight for c in self.supports), 3)

    @property
    def strength_against(self) -> float:
        return round(sum(c.weight for c in self.breaks), 3)

    @property
    def types_for(self) -> list[str]:
        """🔴 중복 없이, 나온 순서대로 — 카드가 유형 이름을 그대로 적는다."""
        out: list[str] = []
        for c in self.supports:
            if c.type and c.type not in out:
                out.append(c.type)
        return out


def hypotheses(items: list[Classified], game: Game) -> list[Hypothesis]:
    """§5-a 묶음 → 팀별 가설 + 무너지는 조건.

    🔴 **판단을 더하지 않는다.** 묶음을 두 팀 시선으로 다시 보여 줄 뿐이다.
    ⚠️ `draw` 는 **양쪽 '무너지는 조건'** 에 들어간다 — 무승부는 두 승리 가설을
       다 깬다. 어느 한쪽 가설에 넣으면 거짓이다.
    """
    by: dict[str, list[Classified]] = {"home": [], "away": [], "draw": []}
    for c in items:
        if c.is_variable and c.direction in by:
            by[c.direction].append(c)
    out: list[Hypothesis] = []
    for side, team in (("home", game.home), ("away", game.away)):
        other = "away" if side == "home" else "home"
        out.append(Hypothesis(
            team=team, side=side,
            supports=list(by[side]),
            # 🔴 반대 방향 + 무승부가 이 가설을 깬다
            breaks=list(by[other]) + list(by["draw"])))
    if by["draw"]:
        logger.info("[classify] 무승부 방향 변수 %d건 — **양 팀** 무너지는 조건에 넣었다",
                    len(by["draw"]))
    return out
