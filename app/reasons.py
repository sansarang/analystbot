"""🔴🔴 **사유 코드 한 표** — v5 §8-6.

> 실패 사유는 사람이 쓰는 문자열이 아니라 **실패한 조건이 돌려주는 enum** 이다.
> … **사유를 추정해서 적는 코드는 계약 실패**("날짜 창"이라 적었는데 실제는
> 이름 문제였던 사례). [#28]

══════════════════════════════════════════════════════════════════
🔴 왜 — 실사고 2026-10-03
══════════════════════════════════════════════════════════════════

`slate.find` 가 못 찾은 경기에 *"창 밖"*(`out_of_window`)이라 적었다. 🔴 실제는
**이름 문제**(`name_unresolved`)였다. 그 둘은 고칠 곳이 완전히 다르다 —
수집 vs 이름표. ⚠️ 사용자가 그 거짓 사유로 **두 번** 헛돌았다.

══════════════════════════════════════════════════════════════════
🔴 이 파일이 드는 것은 셋이다
══════════════════════════════════════════════════════════════════

```
Reason        기계가 비교하는 값        (`.value` 가 §8-6 목록의 글자다)
.fix_where    🔴 **어디를 고쳐야 하나** — 사유의 뜻이 거기 있다
SAY           사람이 읽을 한 줄        (호출부가 짓지 않는다 → 거짓 사유를 막는다)
```

⚠️ 목록을 **손으로 지키지 않는다** — `tests/contracts/test_v5_8_reasons.py` 가
   `docs/fable/inbox/2026-10-04_v5_solar.md` 의 §8-6 줄을 읽어 대조한다. 문서가
   사유를 더하면 그 계약이 **먼저** 빨개진다(CLAUDE.md #1 사본 금지).

⚠️ `app/matchref.Reason` 은 **입구 전용**(v4 §17-g-3)이고 일곱뿐이다. 그쪽은
   `Lookup` 이 쓰고, 이 표는 **전 구간**(검색·읽기·검증·판정·예산)을 덮는다.
   🔴 겹치는 다섯(`ok`·`no_query`·`match_not_found`·`not_collected`·`ambiguous`)은
   같은 글자로 둔다 — 두 표가 같은 사실을 다른 글자로 말하면 그것이 또 거짓이다.
"""
from __future__ import annotations

from enum import Enum

#: 🔴 **고칠 곳**의 집합. ⚠️ 여기 없는 말을 쓰면 계약이 빨개진다 —
#   *"어디를 고치나"* 가 흐려지면 사유가 장식이 된다.
# 🔴🔴 **망·서버·속도를 더했다** — 지시서 2026-10-06 §3 (M136).
#    > `llm_timeout`·`llm_http_5xx`·`llm_429`·`budget_cut` 은 서로 다른 사유다.
#    ⚠️ 셋을 `예산` 으로 묶으면 *"전송 실패 14건"* 같은 거짓이 난다(실측
#       2026-10-06: 실제 전송 실패는 1건이고 나머지는 예산이었다).
WHERE = ("수집", "이름표", "검색", "읽기", "검증", "규칙", "판정", "예산",
         "망", "서버", "속도",
         "에이전트", "없음")

#: 🔴🔴 **사용자에게 무엇을 말하나** — v4 §17-g-3 의 두 성질.
#
#  ⚠️ 내 첫 판은 이것을 `fix_where` 에서 **파생**했다. 계약이 잡았다:
#     `AMBIGUOUS`(이름표)는 **다시 물으면 풀리고**, `NOT_COLLECTED`(수집)는
#     **우리가 고쳐야** 풀린다 — 파생으로는 그 둘이 뒤집힌다.
#  🔴 그래서 **별개 축**이다. 선언으로 둔다(겹칠 수가 없다).
#     `ask`      사용자가 다시 물으면 풀릴 수 있다
#     `bug`      🔴 우리가 고쳐야 풀린다 — **다시 물어도 같다**
#     `verdict`  규칙·검증이 그렇게 **판단한** 것이다(결함이 아니다)
#     `none`     해당 없음(`OK`)
KIND = ("ask", "bug", "verdict", "none")


class Reason(Enum):
    """§8-6 사유 코드. 🔴 `(값, 고칠 곳)` 을 함께 든다."""

    # ── 입구(v4 §17-g-3 · §8-6 이 지우지 않았다)
    OK = ("ok", "없음", "none")
    NO_QUERY = ("no_query", "없음", "ask")
    NAME_UNRESOLVED = ("name_unresolved", "이름표", "bug")
    MATCH_NOT_FOUND = ("match_not_found", "수집", "verdict")
    NOT_COLLECTED = ("not_collected", "수집", "bug")
    OUT_OF_WINDOW = ("out_of_window", "수집", "ask")
    #: 🔴🔴 **이미 킥오프했다** — 사용자 지시 2026-10-10(재작성) §1-3
    #
    #  > 이미 킥오프 지남 → *"이미 시작한 경기 — 예측 아님"*(등급 없음).
    #  > 결과가 나왔으면 결과를 보여 준다.
    #
    #  ⚠️ `OUT_OF_WINDOW`(창 밖 — 너무 먼 미래)와 **다른 일**이다. 섞으면 사용자가
    #     *"날짜를 지정해 다시 물어라"* 를 듣는데, 그래도 그 경기는 지났다.
    ALREADY_STARTED = ("already_started", "수집", "ask")
    AMBIGUOUS = ("ambiguous", "이름표", "ask")

    # ── §4 검색·읽기 도구
    QUERY_TOO_BARE = ("query_too_bare", "검색", "bug")
    DUPLICATE_QUERY = ("duplicate_query", "검색", "bug")
    ROBOTS_DENIED = ("robots_denied", "읽기", "verdict")
    DOMAIN_DENIED = ("domain_denied", "읽기", "verdict")
    SIZE_CUT = ("size_cut", "읽기", "verdict")

    # ── §5 검증층
    DATE_MISSING = ("date_missing", "검증", "verdict")
    POST_MATCH = ("post_match", "검증", "verdict")
    IDENTITY_MISMATCH = ("identity_mismatch", "검증", "verdict")
    OFF_MATCH = ("off_match", "검증", "verdict")
    QUOTE_NOT_FOUND = ("quote_not_found", "검증", "verdict")
    QUOTE_MISMATCH = ("quote_mismatch", "검증", "verdict")
    SIDE_MISMATCH = ("side_mismatch", "규칙", "bug")
    TIP_SOURCE = ("tip_source", "검증", "verdict")
    H2H_ZEROED = ("h2h_zeroed", "규칙", "verdict")
    STALE_SAMPLE = ("stale_sample", "규칙", "verdict")
    CONFLICT = ("conflict", "검증", "verdict")

    # ── §2 예산 · §3 에이전트
    BUDGET_CUT = ("budget_cut", "예산", "ask")
    LLM_UNAVAILABLE = ("llm_unavailable", "예산", "ask")
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **전송 사유 셋** — 지시서 2026-10-06 §3 (M136)
    # ══════════════════════════════════════════════════════════════
    #
    #  > 사유 분리 유지: `llm_timeout`·`llm_http_5xx`·`llm_429`·`budget_cut` 은
    #  > 서로 **다른 사유**다.
    #
    #  🔴 **고칠 곳이 다르다**: 타임아웃은 **망**(또는 응답이 너무 길다),
    #     5xx 는 **서버**, 429 는 **속도**, `budget_cut` 은 **예산**이다.
    #  ⚠️ 실측 2026-10-06: 넷이 전부 `llm_unavailable` 로 세어져 *"전송 실패
    #     14건"* 이 됐고, 실제 전송 실패는 **1건**이었다(나머지는 예산).
    #     그 거짓은 CLAUDE.md #11(장애로 끊긴 실행은 재실행)을 **잘못 발동**시켜
    #     정상 종료를 다시 돌리게 만든다.
    LLM_TIMEOUT = ("llm_timeout", "망", "ask")
    LLM_HTTP_5XX = ("llm_http_5xx", "서버", "ask")
    LLM_429 = ("llm_429", "속도", "ask")
    AGENT_ZERO = ("agent_zero", "에이전트", "ask")

    # ── §6·§7 판정
    SCENARIO_INCOMPLETE = ("scenario_incomplete", "판정", "bug")
    INSUFFICIENT = ("insufficient", "수집", "ask")
    PREMATURE_INSUFFICIENT = ("premature_insufficient", "판정", "bug")
    TRIGGER_UNRESOLVED = ("trigger_unresolved", "판정", "bug")
    # ══════════════════════════════════════════════════════════════
    # 🔴 **§7-3 라이브 재판정** — 셋 다 *거절*에 관한 것이다
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ `LIVE_NO_INPUT` 은 **우리 버그가 아니다** — 스코어·경과 분이 안 온
    #     것이다(수집). 🔴 그리고 **다시 물으면 온다**(경기가 진행된다) — 그래서
    #     `ask` 다. ⚠️ 처음에 `bug` 로 적었더니 v4 계약이 *"다시 물어도 같다를
    #     안 적었다"* 고 빨개졌다 — **그 계약이 맞았다**(분류가 틀렸다).
    #  🔴 나머지 둘은 **판정**이다: 약한 지표로 지우려 했거나 라이브로 새 마켓을
    #     만들려 한 것이고, 둘 다 우리 코드가 하는 일이다.
    # ══════════════════════════════════════════════════════════════
    # 🔴 **§3-8 모델 인터페이스**(작업 지시서 §1 · M47·M48)
    # ══════════════════════════════════════════════════════════════
    #
    #  🔴 둘 다 **판정**이다 — 모델이 낸 것을 우리가 못 읽거나 규격을 안 지킨
    #     것이고, 다시 물어도 같다(프롬프트·파서를 고쳐야 풀린다).
    # ══════════════════════════════════════════════════════════════
    # 🔴 **v5-A DeepSeek**(작업 지시서 §4-6 · 여섯 종)
    # ══════════════════════════════════════════════════════════════
    #
    #  🔴 `unknown_var`·`new_fact` 는 **에이전트**다 — 모델이 규격을 벗어난
    #     것이고 우리 코드도 자료도 아니다. ⚠️ `판정` 으로 적으면 우리 코드를
    #     뒤지게 된다(§8-6 이 막는 섞임이다).
    #  ⚠️ `deepseek_unavailable` 은 **수집**이다(그쪽이 안 왔다) 그리고
    #     **다시 물으면 올 수 있다**(`ask`) — 장애는 지나간다.
    UNKNOWN_VAR = ("unknown_var", "에이전트", "bug")
    NEW_FACT = ("new_fact", "에이전트", "bug")
    REDTEAM_SKIPPED = ("redteam_skipped", "예산", "none")
    REDTEAM_OVERRULED = ("redteam_overruled", "규칙", "verdict")
    DEEPSEEK_UNAVAILABLE = ("deepseek_unavailable", "수집", "ask")
    DEEPSEEK_MISSED_REQUIRED = ("deepseek_missed_required", "에이전트", "bug")
    DONE_PARSE_FAIL = ("done_parse_fail", "판정", "bug")
    NAME_NOT_KEY = ("name_not_key", "판정", "bug")
    LIVE_NO_INPUT = ("live_no_input", "수집", "ask")
    LIVE_WEAK_METRIC = ("live_weak_metric", "판정", "verdict")
    LIVE_NEW_MARKET = ("live_new_market", "판정", "bug")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **세포 검색을 끈 자리** — 결정 ③ (사용자 2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ **고칠 곳이 `없음`** 이고 **종류가 `none`** 이다 — 결함이 아니라
    #     **설계로 끊은 경로**다. 🔴 그래서 카드의 *"고칠 곳"* 집계에 안 들어간다.
    #     그 수를 `검색` 으로 세면 *"검색이 26건 실패했다"* 로 읽혀 거짓이 된다.
    #  🔴 그래도 **이름으로 남긴다**(#3) — 0 으로 두면 세포가 안 돈 것처럼 보인다.
    CELL_SEARCH_OFF = ("cell_search_off", "없음", "none")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **본문 부재** — 지시서(오픈월드) §1-1 (2026-10-05)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측: 포르투갈 후보 **12건 전부**가 `quote_not_found` 였는데 내용은
    #     *"본문을 받아 두지 않았다"* 였다 — 인용을 **대조조차 못 했다.**
    #  🔴 한 사유로 묶으면 **고칠 곳이 가려진다**(§8-6): 본문 부재는 **수집**
    #     (또는 배선)이고, 인용 부재는 **에이전트**다.
    BODY_MISSING = ("body_missing", "수집", "bug")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **오픈월드가 경기를 못 찾았다** — 지시서 §2 ⑥-3 (2026-10-05)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `name_unresolved`(이름표 문제)와 **다르다**: 이름은 풀어 봤고 공개
    #     페이지까지 찾아봤는데 **창 안에 그 경기가 없었다.**
    #  🔴 고칠 곳은 `검색` 이다 — 철자 후보를 바꾸거나 다른 통로를 써야 한다.
    #     ⚠️ 그래서 **다시 물으면 풀릴 수 있다**(사용자가 철자를 바꿔 주면).
    OPENWORLD_NOT_FOUND = ("openworld_not_found", "검색", "ask")
    TYPE_OFF_CATALOG = ("type_off_catalog", "에이전트", "bug")
    # 🔴🔴 **DeepSeek 시나리오가 0개** — 지시 ③ (2026-10-05).
    #    ⚠️ 템플릿으로 돌아가는 것은 **퇴로**(M45)이지 성공이 아니다 — 카드가
    #       *"분석했다"* 고 거짓말하지 않게 **이름으로** 남긴다.
    DEEPSEEK_NO_SCENARIO = ("deepseek_no_scenario", "에이전트", "ask")
    #: 🔴 킥오프가 지나 **등급을 거뒀다**(지시 ③ 2026-10-05).
    #   ⚠️ 고칠 곳은 **없다** — 결함이 아니라 *"예측할 때가 지났다"* 다.
    #      🔴 `scenario_incomplete`(시나리오 모자람)와 **섞으면** 카드를 읽는
    #         사람이 고칠 것이 있다고 오해한다.
    KICKOFF_PASSED = ("kickoff_passed", "없음", "none")
    #: 🔴 §3 에이전트가 **예외로 끊겼다**(실측 2026-10-05: 프랑스 쪽이 터졌다).
    #   ⚠️ `agent_zero`(돌았는데 0개)와 **고칠 곳이 다르다** — 이것은 코드 결함이다.
    AGENT_CRASHED = ("agent_crashed", "에이전트", "bug")
    #: 🔴 질의가 **10단어 초과**다(딥서치 재구축 §4-3 · M61).
    #   ⚠️ 실측: 긴 문장 질의가 **0건**을 만들었다. 🔴 `query_too_bare`(너무
    #      넓다)와 **반대 방향**이라 사유를 가른다 — 고칠 곳이 다르다.
    QUERY_TOO_LONG = ("query_too_long", "검색", "ask")
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **결장 변수의 팀 귀속** — 사용자 지시 2026-10-07(결장 귀속)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-07(멕시코–칠레): **멕시코** 선수 `Gilberto Mora` 의 결장이
    #     s4 출력에서 `team:000047`(칠레)로 붙어 `favors=home`·`득점↑` 로 뒤집혔고,
    #     가설·시나리오가 그것을 *"상대 결장"* 으로 읽었다.
    #  🔴 그래서 **선수 → 팀 대조를 코드가** 한다(LLM 에게 다시 묻지 않는다).
    #     세 결과를 **이름으로** 가른다 — 고칠 곳이 다르다:
    #       `team_reattached` 모델이 틀렸고 **명단으로 고쳤다**(카드에 적는다)
    #       `team_unresolved` 두 팀 명단에도, 기사 문장에도 없다 → 근거 불가
    #       `team_ambiguous`  **두 팀 다** 그 이름이 있다(동명이인) → 근거 불가
    TEAM_REATTACHED = ("team_reattached", "에이전트", "bug")
    TEAM_UNRESOLVED = ("team_unresolved", "검증", "verdict")
    TEAM_AMBIGUOUS = ("team_ambiguous", "검증", "verdict")

    def __init__(self, value: str, fix_where: str, kind: str):
        self._value_ = value
        self.fix_where = fix_where
        self.kind = kind

    @property
    def is_our_bug(self) -> bool:
        """🔴 **우리가 고쳐야 풀리나.** ⚠️ 다시 물어도 같은 사유들이다."""
        return self.kind == "bug"

    @property
    def fixable_by_asking_again(self) -> bool:
        """⚠️ 사용자가 다시 물으면 풀릴 수 있나.

        🔴 `is_our_bug` 와 **겹칠 수가 없다** — 한 칸(`kind`)에서 나온다.
           v4 계약이 그 겹침을 금지했고, 파생으로 두면 그 둘이 뒤집혔다.
        """
        return self.kind == "ask"


#: 🔴 사람이 읽을 한 줄. ⚠️ **호출부가 짓지 않는다** — 같은 사유가 자리마다 다른
#   말로 적히면 그것이 §8-6 이 막으려는 *"추정해서 적는"* 것이다.
SAY: dict[Reason, str] = {
    # ⚠️ `Reason.OK` 는 **여기 없다** — 실패 사유 표이고 `OK` 는 실패가 아니다.
    #    🔴 계약이 그것을 전제한다(`r is not Reason.OK`).
    Reason.NO_QUERY: "🔴 **무엇을 물었는지 모르겠다** — 팀 이름을 적어 달라",
    Reason.NAME_UNRESOLVED:
        "🔴 그 이름을 **아는 이름으로 못 바꿨다** — 자료가 아니라 **이름표 문제**다"
        "(`app/bot/aliases.py` · `config/entities.yaml`). ⚠️ 다시 물어도 같다",
    Reason.MATCH_NOT_FOUND:
        "🔴 그 경기를 **못 찾았다** — 자료가 안 잡혔다",
    Reason.NOT_COLLECTED:
        "🔴 그 날짜가 **아직 안 쌓였다** — 스케줄러가 돌아야 한다"
        "(자료가 없는 것과 다르다). ⚠️ 다시 물어도 같다",
    Reason.OUT_OF_WINDOW:
        "🔴 찾았는데 **질문 창 밖**이다 — 날짜를 지정해 다시 물어라",
    Reason.ALREADY_STARTED:
        "⏱ **이미 시작한 경기다 — 예측이 아니다**(등급 없음). "
        "🔴 경기 전에 적지 않은 것을 뒤에 적으면 그것은 예측이 아니다(§3 불변)",
    Reason.AMBIGUOUS:
        "🔴 **여러 경기가 맞는다** — 하나를 지목해라(§17-g-3)",
    Reason.QUERY_TOO_BARE:
        "🔴 검색어가 **이름 하나짜리**다 — §4-1 은 세 요소 이상을 요구한다"
        "(팀·상대·대회·종목 낱말·날짜 중). ⚠️ 다시 물어도 같다 — 검색어를 짓는 쪽을 고친다",
    Reason.DUPLICATE_QUERY:
        "🔴 같은 검색어를 **두 번째**로 던졌다 — 각도를 바꿔야 한다(§4-1). "
        "⚠️ 다시 물어도 같다",
    Reason.ROBOTS_DENIED:
        "🔴 `robots.txt` 가 막는다 — **dead 처리뿐**이다(우회·UA 위장·프록시 금지)",
    Reason.DOMAIN_DENIED:
        "🔴 도메인 등급표가 **거부**한 호스트다(§4-3) — 스포츠 매체가 아니거나 "
        "다른 종목이다",
    Reason.SIZE_CUT:
        "🔴 본문이 상한을 넘어 **잘렸다**(§4-5) — 그 길이는 경기 기사가 아니다",
    Reason.DATE_MISSING:
        "🔴 발행 시각이 **없다** — 본문은 받았지만 변수로 못 쓴다(§5-3 fail-closed)",
    Reason.POST_MATCH: "🔴 **킥오프 뒤** 기사다 — 예측의 근거가 아니다(§5-3)",
    Reason.IDENTITY_MISMATCH:
        "🔴 그 경기 이야기가 **아니다** — 남녀·연령 표식이나 종목이 안 맞는다(§5-2)",
    Reason.OFF_MATCH:
        "🔴 그 경기와 **무관한 발언**이다(다른 대회·다른 상대 이야기 · §5-2)",
    Reason.QUOTE_NOT_FOUND:
        "🔴 인용이 **그 본문에 없다** — 지어낸 것이다(§5-1)",
    Reason.QUOTE_MISMATCH:
        "🔴 인용은 있는데 **주장을 뒷받침하지 않는다**(§5-1 2차 확인)",
    Reason.SIDE_MISMATCH:
        "🔴 **원정 기록을 홈팀 변수로** 쓰려 했다 — 오늘 경기의 쪽에 맞는 것만 "
        "쓴다(§5-4 · M36). ⚠️ 다시 물어도 같다",
    Reason.TIP_SOURCE:
        "🔴 베팅 팁·예측 사이트다 — **변수 근거가 못 된다**(§4-3 `tip` 등급)",
    Reason.H2H_ZEROED:
        "🔴 맞대결인데 **감독 또는 주전 절반이 바뀌었다** — 무게 0(§5-5)",
    Reason.STALE_SAMPLE:
        "🔴 표본이 **낡았다**(마지막 경기가 문턱 일수 이상 전) — 약한 주장이다(§5-5)",
    Reason.CONFLICT:
        "🔴 두 매체가 **다른 상태**를 말한다 — 양쪽을 산 채로 두고 무게 0(§5-7)",
    Reason.BUDGET_CUT:
        "🔴 **예산 상한**에 닿았다(§2) — 그때까지 모은 변수로 간다",
    Reason.LLM_UNAVAILABLE:
        "🔴 에이전트를 **못 불렀다**(키 없음·재시도 소진 · §2)",
    Reason.LLM_TIMEOUT:
        "🔴 LLM 이 **응답 안에 답하지 못했다**(타임아웃·끊김) — 고칠 곳은 "
        "**망 또는 응답 길이**다. ⚠️ 예산이 아니다(§3 · M136)",
    Reason.LLM_HTTP_5XX:
        "🔴 LLM **서버가 5xx** 를 냈다 — 우리 쪽 결함이 아니다. 재시도 뒤에도 "
        "실패하면 그 하위는 2차 보충 대상이다(§3)",
    Reason.LLM_429:
        "🔴 LLM 이 **너무 빠르다고 했다**(429) — 동시 호출을 낮추고 "
        "`Retry-After` 를 따른다(§3 · M66)",
    Reason.AGENT_ZERO:
        "🔴 에이전트가 변수를 **0개** 돌려줬다 — 그 경기는 자료 부족이다(§3-7)",
    Reason.QUERY_TOO_LONG:
        "🔴 검색어가 **너무 길다**(10단어 초과) — 긴 문장 질의는 결과를 "
        "**0건**으로 만든다(실측). ⚠️ 넓게 시작해 판을 본 뒤 좁혀라",
    Reason.TEAM_REATTACHED:
        "🔴 **결장 선수의 팀이 뒤집혀 있었다** — 명단 대조로 고쳤다. ⚠️ 고칠 곳은 "
        "**추출 프롬프트**다(모델이 상대 팀을 적었다) — **다시 물어도 같다**",
    Reason.TEAM_UNRESOLVED:
        "🔴 그 선수가 **어느 팀인지 못 가렸다**(두 팀 명단에도, 기사 문장에도 없다) "
        "— 그 변수는 **근거로 쓰지 않는다**(맥락으로만)",
    Reason.TEAM_AMBIGUOUS:
        "🔴 **두 팀 다** 그 이름이 있다(동명이인) — 방향을 정할 수 없어 "
        "**근거로 쓰지 않는다**",
    Reason.AGENT_CRASHED:
        "🔴 **§3 에이전트가 예외로 끊겼다** — 그 팀 변수가 통째로 없다. "
        "⚠️ `agent_zero`(돌았는데 0개)와 다르다: 이것은 **코드 결함**이고 "
        "**다시 물어도 같다**(코드를 고쳐야 한다)",
    Reason.KICKOFF_PASSED:
        "🔴 **킥오프가 지났다** — 분석은 그대로 내지만 **등급은 내지 않는다**. "
        "⚠️ 고칠 것이 아니라 **예측할 때가 지난 것**이다(지시 ③ 2026-10-05)",
    Reason.DEEPSEEK_NO_SCENARIO:
        "⚠️ 단계 3(DeepSeek)이 **시나리오를 0개** 냈다 — 템플릿으로 돌았다"
        "(v5-A M45 퇴로 · 지시 ③ 2026-10-05)",
    Reason.TYPE_OFF_CATALOG:
        "🔴 **카탈로그에 없는 유형**이다 — §4 유형표의 방향·hardness 규칙이 "
        "안 걸린다. **다시 물어도 같다**(프롬프트를 고쳐야 한다)",
    Reason.OPENWORLD_NOT_FOUND:
        "🔴 그 경기를 **공개 페이지에서도 못 찾았다**(오픈월드 ⑥-3) — "
        "철자를 다르게 **적어 달라**(예: 현지 표기·정식명)",
    Reason.BODY_MISSING:
        "🔴 그 기사 **본문을 못 받았다** — 인용을 대조할 수 없다. "
        "고칠 곳은 **수집·배선**이다(지시서 §1-1) — **다시 물어도 같다**",
    Reason.CELL_SEARCH_OFF:
        "⚠️ §3 에이전트가 검색을 맡았다 — 세포는 **장부**다"
        "(사용자 결정 ③ 2026-10-04)",
    Reason.SCENARIO_INCOMPLETE:
        "🔴 시나리오 세트가 **불완전**하다 — 카드를 내지 않는다(§6-2 · §6-7). "
        "⚠️ 다시 물어도 같다",
    Reason.INSUFFICIENT:
        "🔴 **자료 부족**(R5) — 변수 3개 미만 또는 반대 방향 0개",
    Reason.PREMATURE_INSUFFICIENT:
        "🔴 사다리 2단계·도구 6회를 **돌기 전에** 자료 부족을 선언했다(§7-5) — "
        "그것은 우리 결함이다. ⚠️ 다시 물어도 같다",
    Reason.TRIGGER_UNRESOLVED:
        "🔴 방아쇠 조건을 **평가하지 못했다** — 베팅 등급이 아니다(§7-2 · M28). "
        "⚠️ 다시 물어도 같다 — **§7-1 T-60 재실행**이 확정 명단을 받아야 풀린다",
    Reason.UNKNOWN_VAR:
        "🔴 시나리오의 `driver_vars` 에 **검증된 변수가 아닌 ID** 가 있다"
        "(v5-A M41) — 그 시나리오를 폐기한다. ⚠️ 다시 물어도 같다 — "
        "프롬프트가 ID 목록을 제대로 주는지 보라",
    Reason.NEW_FACT:
        "🔴 `mechanism` 에 **입력에 없는 고유명사**가 있다(v5-A M41) — 모델이 "
        "사실을 지어냈다. 그 시나리오를 폐기한다. ⚠️ 다시 물어도 같다",
    Reason.REDTEAM_SKIPPED:
        "⚠️ 반증 단계를 **건너뛰었다**(v5-A §4) — 생존 0.8 이상 마켓이 없거나 "
        "DeepSeek 예산을 넘었다. 🔴 반증할 결론이 없으면 비용을 쓰지 않는다",
    Reason.REDTEAM_OVERRULED:
        "🔴 반증이 `impossible` 이라 했지만 **필수형 조건이 걸린다**"
        "(v5-A M46) — 코드가 템플릿 시나리오를 넣었다",
    Reason.DEEPSEEK_UNAVAILABLE:
        "⚠️ DeepSeek 를 **못 불렀다**(키 없음·꺼짐·타임아웃) — v5 원래 경로"
        "(Solar 초안 + 코드 필수형 보강)로 판정이 끝까지 돈다(v5-A M45)",
    Reason.DEEPSEEK_MISSED_REQUIRED:
        "🔴 DeepSeek 가 **필수형을 빠뜨렸다** — 코드가 템플릿으로 보강했다"
        "(§6-2 · `added_by:code`). ⚠️ 다시 물어도 같다 — 그 수가 §6 측정의 "
        "**필수형 누락률**이다",
    Reason.DONE_PARSE_FAIL:
        "🔴 `done` 출력을 **못 읽었다**(§3-8 M47) — 산문 속 JSON 블록도 두 번 "
        "찾아봤다. ⚠️ 다시 물어도 같다 — 프롬프트·파서를 고쳐야 풀린다",
    Reason.NAME_NOT_KEY:
        "🔴 변수의 `team` 이 **이름**이다(§3-8 M48) — 열쇠(`team:NNNNNN`)만 "
        "받는다. ⚠️ 다시 물어도 같다 — 옮기지 않고 폐기한다(그 버릇이 숨으면 "
        "프롬프트를 못 고친다)",
    Reason.LIVE_NO_INPUT:
        "🔴 **스코어·경과 분이 없다** — §7-3 은 그 둘 없이 재판정을 금지한다"
        "(지표만으로는 무엇이 일어났는지 모른다)",
    Reason.LIVE_WEAK_METRIC:
        "⚠️ 지표가 **약하다** — §7-3 은 *지표 2개 이상이 같은 메커니즘을 가리킬 "
        "때만* 인정한다. 🔴 지표로는 **약화만** 하고 제거하지 않는다",
    Reason.LIVE_NEW_MARKET:
        "🔴 **라이브로 새 마켓을 만들려 했다** — §7-3 금지다. 있던 마켓의 "
        "생존만 갱신한다. ⚠️ 다시 물어도 같다 — 그 마켓을 만드는 자리는 "
        "**경기 전**(§6-3)이다",
}


def say(reason: Reason, *, detail: str = "") -> str:
    """🔴 그 사유의 한 줄. ⚠️ `detail` 은 **곁들이는 사실**이고 사유를 대신하지 않는다."""
    base = SAY.get(reason) or f"사유 `{reason.value}`"
    out = f"{base} (`{reason.value}` · 고칠 곳 **{reason.fix_where}**)"
    return f"{out} — {detail}" if str(detail or "").strip() else out


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **§6-7 손실 깔때기 — 사유를 "단계"로 묶는다**(지시서 2026-10-13 밤 셋째)
# ══════════════════════════════════════════════════════════════════
#
#  > 잃는 단계(원천/질의/본문/신원/추출)별 **손실 깔때기**.
#  🔴 묶음은 **여기 하나**다 — 카드(`render`)와 측정 도구(`tools/search_funnel`)가
#     같은 표를 읽는다(사본 금지 · #1). ⚠️ 모르는 사유는 **⬜ 미분류**로 센다.
#  🔴 기준선(2026-10-13 · 카드 49장 · 버린 문서 10,257건): ④ 신원 52.9% ·
#     ② 질의·날짜 34.1% · ① 원천 7.2% · ③ 본문 3.6% · ⑤ 추출 1.7%.

STAGE_OF: dict[str, str] = {
    "type_off_catalog": "① 원천",
    "domain_denied": "① 원천",
    "sport_mismatch": "① 원천",
    "tip_source": "① 원천",
    "stale": "② 질의·날짜",
    "date_missing": "② 질의·날짜",
    "stale_sample": "② 질의·날짜",
    "body_missing": "③ 본문",
    "size_cut": "③ 본문",
    "identity_mismatch": "④ 신원",
    "team_tier_mismatch": "④ 신원",
    "team_reattached": "④ 신원",
    "team_unresolved": "④ 신원",
    "off_match": "④ 신원",
    "side_mismatch": "④ 신원",
    "llm_schema": "⑤ 추출",
    "llm_truncated": "⑤ 추출",
    "llm_unavailable": "⑤ 추출",
    "type_content_mismatch": "⑤ 추출",
    "type_off_catalog_fact": "⑤ 추출",
    "stakes_vague": "⑤ 추출",
    "premature_result": "⑤ 추출",
    "post_match": "⑤ 추출",
    "quote_not_found": "⑤ 추출",
    "quote_mismatch": "⑤ 추출",
    "conflict": "⑤ 추출",
    "no_info": "⑤ 추출",
    "duplicate": "— 중복",
}


def stage_of(reason: str) -> str:
    """🔴 그 사유가 **어느 단계의 손실**인가. 모르면 `⬜ 미분류(<사유>)`."""
    said = str(reason or "").strip()
    return STAGE_OF.get(said, f"⬜ 미분류({said or '?'})")
