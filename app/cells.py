"""§19 수집기 — **동적 탐색 세포(cell)망.**

§19 원문: *"수집기는 '소스별 스크래퍼'가 아니다. 페이블이 09-27에 한 것은
**질문 하나를 잡고, 막히면 다른 길로 가는** 과정이었다."*

세포 하나 = 사실 하나를 얻으려는 **질문 + 예산 + 상태기계**다. 소스 하나가
아니다. 그래서 야후뉴스가 막히면 西スポ로, 다음스포츠가 지난주를 주면 연합
순연 기사로 **자동으로** 넘어간다(§19-b-4).

🔴 **세포는 판정하지 않는다**(§19-f). 사실과 hardness 와 unknown 사유만 낸다.
   lean·확신·등급은 `judge.py` 다.
"""
from __future__ import annotations

import functools
import inspect
import logging
import time
from collections.abc import MutableMapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app import cassette, config
from app import rules as _R
from app import verify as V
from app.blackboard import Blackboard, Fact
from app.net import Net, Search, SearchUnavailable
from app.reasons import Reason

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

# ── §19-a 상태 ─────────────────────────────────────────────────────
PENDING = "pending"
SEARCHING = "searching"
FOUND = "found"
UNKNOWN = "unknown"
CONTRADICTED = "contradicted"

# ── §19-a 질문 타입 ────────────────────────────────────────────────
Q_SLATE = "slate"
Q_LINEUP = "lineup"
Q_ABSENCE = "absence"
Q_STARTER_RECENT = "starter_recent"
Q_STANDINGS = "standings"
Q_INTENT = "intent"
Q_LIVE = "live_score"
Q_COUNTER = "counter"
#: 🔴 **질문 id 접미사 — 원본은 여기다.**
#
#  §19-a 의 `Q_TYPES` 에 맞대결·폼·경기통계·선수·순위 질문이 **없다.** 타입을 늘리는
#  것은 규칙 변경이고 사용자 결정이다(단계 5). 그래서 질문 **id 에 접미사**를 붙여
#  가른다 — 저장소가 이미 쓰는 방식이다(`searchcells.coach_cell` 의 `:coach`).
#  ⚠️ 종목마다 파서가 다르지만 **접미사는 같아야 한다** — 다르면 카드·측정이 종목별로
#     갈린다. 축구(fotmob)·야구(statsapi)·하키(api-web)가 이 목록을 함께 쓴다.
SUB_QUESTIONS = ("h2h", "form", "stats", "info", "player",
                 "baseline", "past_stats", "standings",
                 # 🔴 **전반 스코어**(사용자 지적 2026-10-03). 페이로드에 칸이 없어
                 #    과거 경기의 **골 분**에서 유도한다 — `:h2h` 와 다른 사실이다
                 #    (한 경기당 한 건이고, 연속은 `classify` 가 센다).
                 "h2h_half",
                 # 🔴 야구 깊이(2026-10-02~03): 월간 득점·예고 선발·투수 성적
                 "runs_month", "starter", "pitcher_table", "team_pitching",
                 "roster_ids", "starter_stats")

Q_TYPES = (Q_SLATE, Q_LINEUP, Q_ABSENCE, Q_STARTER_RECENT, Q_STANDINGS,
           Q_INTENT, Q_LIVE, Q_COUNTER)


# ══════════════════════════════════════════════════════════════════
# §19-d 시간축 — 세포는 깨어나는 시각이 있다
# ══════════════════════════════════════════════════════════════════

#: 질문 타입 → (T 로부터 몇 분 전에 깨나, 몇 분 간격, 언제까지).
#  🔴 원본은 여기 하나다. 스케줄러가 이것을 읽는다(사본 금지).
WAKE: dict[str, tuple[int | None, int | None, int | None]] = {
    Q_SLATE: (None, None, None),          # 아침 1회
    Q_STANDINGS: (None, None, None),      # 아침 1회
    Q_ABSENCE: (360, None, None),         # T-6h
    Q_STARTER_RECENT: (360, None, None),  # T-6h
    Q_INTENT: (180, 120, 60),             # T-3h · T-1h
    Q_LINEUP: (70, 5, 10),                # T-70분부터 5분 간격, T-10분까지
    Q_LIVE: (0, 10, 0),                   # 판정에 걸린 경기만 10분 간격
    Q_COUNTER: (360, None, None),
}


def awake(qtype: str, starts: datetime, now: datetime) -> bool:
    """이 세포가 지금 깨어 있나.

    🔴 **경기가 시작되면 그 경기의 모든 세포는 종료**다(§19-d). 채점 세포만
       경기 후 깨어난다.
    """
    if now >= starts:
        return qtype == Q_LIVE      # 타 구장 라이브만 계속 본다
    before, _, until = WAKE.get(qtype, (None, None, None))
    if before is None:
        return True                  # 아침 1회 — 언제든 돌려도 된다
    mins = (starts - now).total_seconds() / 60
    if mins > before:
        return False
    return mins >= (until or 0)


# ══════════════════════════════════════════════════════════════════
# §19-a 세포
# ══════════════════════════════════════════════════════════════════


@dataclass
class Question:
    """구조화된 질문. 🔴 `id` 가 블랙보드의 열쇠다."""

    type: str
    subject: str                       # 팀·선수·경기 — 질문을 유일하게 만든다
    game_id: int | None = None
    team: str | None = None
    player_id: int | None = None
    league: str | None = None
    deadline: datetime | None = None
    #: 🔴 §17-g-3 — **상대 팀.** 한 기사가 두 팀을 말할 때 귀속을 판단하려면
    #  상대가 누구인지 알아야 한다. 모르면 귀속 불명 판정을 하지 않는다(M14).
    opponent: str | None = None
    #: 🔴 **현지 약칭.** 기사는 정식명을 거의 안 쓴다 — `福岡ソフトバンクホークス`
    #  대신 `ソフトバンク` 다. 정식명 앞 두 자(`福岡`)로 찾으면 못 맞춘다
    #  (실측 2026-09-27 카세트: 타순이 든 스니펫이 `福岡` 을 안 썼다).
    #  ⚠️ 원본은 리그 어댑터의 약칭 표다(`npb.TEAMS`) — 여기 베끼지 않는다.
    local: str | None = None
    opponent_local: str | None = None
    #: 🔴🔴 **그 경기 종목.** 사용자 수정 ③ (2026-10-04) — 열기 전 **다른 종목
    #  페이지를 버리는** 데 쓴다(`rules.other_sport`).
    #  ⚠️ 종전에 이 값이 세포에 **없었다.** 그래서 스코틀랜드 질의가 럭비 15건을
    #     열었다 — 같은 나라가 여러 종목을 하는데 세포는 종목을 몰랐다.
    #  🔴 비면 **막지 않는다**(`queries.asks` 와 같은 처분 — 모른다고 전부 거부하면
    #     새 종목이 아무것도 못 묻는다).
    sport: str | None = None

    @property
    def id(self) -> str:
        return f"{self.type}:{self.subject}"


#: §12-d 의 **세 모드.** 🔴 원본은 v3 §12-d 한 줄이고 여기 베끼지 않는다 —
#  적는 것은 *그 한 줄이 배치만 가정한다*는 사실과, **사람이 기다리는지**다.
#
#  🔴 **사용자 지시 2026-10-01**(구조):
#
#  > 기존에 **서버에서 분석을 하고 있다** .. 사용자가 경기를 질문을 한다 ..
#  > 아까 내가 보여준 결과물대로 사용자에게 답변을 줘야 한다
#
#  → 분석은 **미리** 서버가 한다. 질문은 그 결과를 **꺼내는 것**이다.
#    ⚠️ 그래서 "질문형이니 빨라야 한다"는 내 첫 판이 틀렸다 — 깊은 분석은
#       **사람이 안 기다리는 경로**에서 돈다. 거기서 시간을 조이면 깊이를 잃는다.
#
#  | 모드 | 누가 기다리나 | 예산 | 시간 상한 |
#  |---|---|---|---|
#  | `SLATE` | 아무도 | 경기별 **고정**(§12-d) — 슬레이트를 고르게 | 없다(개수가 작다) |
#  | `DEEP` | 🔴 **아무도** — 서버가 미리 돈다 | 한 경기에 **몰아준다** | 길다(`DEEP_SECONDS`) |
#  | `ASK` | 🔴 **사람** — 물어 놓고 기다린다 | 같이 몰아준다 | **짧다**(`ASK_SECONDS`) |
#
#  🔴 `ASK` 가 필요한 이유: 미리 분석되지 **않은** 경기를 물을 수 있다(슬레이트 밖,
#     또는 아직 안 돈 경기). 그때는 사람이 기다리므로 얕더라도 빨리 답하고,
#     *"아직 깊이 분석되지 않았다"* 를 함께 적는다(§19-b-6).
#
#  → 결정 기록: `docs/fable/questions/2026-10-01_question_mode.md`
SLATE = "slate"
DEEP = "deep"
ASK = "ask"
MODES = (SLATE, DEEP, ASK)

#: 🔴 깊게 파는 모드의 **열기** 예산. 실측 2026-09-30(필수 8건 ⑤ 세이부 라인업):
#
#     검색 결과 36건 수신 → 열기 3건 소진 → 중단
#     사유: "본문 예산소진 (36건 중 일부만 열었다)"
#
#  맞는 기사는 그 36건 안에 있었다 — **못 찾은 게 아니라 예산이 끊겼다.**
#  ⚠️ 그래도 **상한을 둔다.** 무한히 열면 대상 서버에 부담이고, 실측 2026-09-30 에
#     측정 자체가 SearXNG 엔진 셋을 전부 정지시켰다.
#  🔴 이 숫자는 **사용자 소관**이다(§13-7: 예산은 사용자). 고치려면 여기 한 곳이다.
#: 🔴 §17-b 추출을 부르기 전 **본문 최소 길이**. 짧으면 기사가 아니라 스니펫이다.
#   ⚠️ 7B 급에 두 문장을 주면 없는 것을 만들어 낸다 — 부르지 않는 것이 낫다.
EXTRACT_MIN_CHARS = 400

#: 🔴🔴 **본문 상한** — 사용자 수정 ② (2026-10-04): *"본문 5만 자 이상은 안 받는다
#  (위키 경제 문서 18만 자가 예산을 먹었다)."*
#
#  ⚠️ 실측 2026-10-04(북마케도니아 vs 스코틀랜드) 로그 원문:
#
#     en.wikipedia.org/wiki/North_Macedonia              본문 **109,714자** · 문단 358개
#     en.wikipedia.org/wiki/Macedonia_naming_dispute     본문 **180,470자** · 문단 620개
#     → 둘 다 `추출도 0건 — 산문에 그 사실이 없다` · 그 사이 LLM 60초가 탔다
#
#  🔴 **길다는 것 자체가 신호다** — 그 길이의 페이지는 나라·역사 문서이고 그
#     경기 기사가 아니다. 경기 프리뷰는 실측에서 1,700~7,600자였다.
#  ⚠️ `net.get` 에서 막지 않는다 — 거기서 자르면 **발행 시각 추출**(머리글에 있다)과
#     경기 표(순위표는 길다)가 함께 죽는다. 🔴 막는 자리는 **추출 직전**이다 —
#     돈이 드는 것은 받기가 아니라 trafilatura · BM25 · LLM 이다.
EXTRACT_MAX_CHARS = 50_000

DEEP_FETCHES = 20

#: 🔴 **시간 상한(초).** 개수만으로는 못 막는다.
#
#  ⚠️ 실측 2026-10-01: 열기 예산을 20으로 올리고 녹음을 돌렸더니 라인업 세포 하나가
#     **15분 51초**를 먹었다. 산수가 이것이다 —
#
#         MIN_INTERVAL_SEC 2초 + TIMEOUT_SEC 20초 = 열기 한 건 최악 22초
#         22초 × 20건 = 한 세포 **7분 20초**
#
#     같은 녹음의 다른 경기는 네 세포에 **19초**였다. 🔴 **평균이 아니라 분산이
#     문제다** — 느린 호스트를 만난 세포 하나가 전체를 끈다. 상한은 그 꼬리를 자른다.
#
#  🔴 두 값이 다른 이유는 **기다리는 사람이 있나**다. `DEEP` 은 밤새 돌아도 되고,
#     `ASK` 는 사용자가 화면을 보고 있다.
DEEP_SECONDS = 300.0
ASK_SECONDS = 90.0

#: 🔴 모드별 시간 상한. `None` = 안 건다.
SECONDS_OF = {SLATE: None, DEEP: DEEP_SECONDS, ASK: ASK_SECONDS}


def budget_for(n_sources: int, *, fetches: int, mode: str = SLATE) -> "Budget":
    """§12-d 예산 한 칸. 🔴 모드가 바꾸는 것은 **열기 예산과 시간**이다.

    ⚠️ `searches` 는 이미 소스 수와 같다 — 모드로 늘릴 자리가 없다. 깊게 파려면
       **변형을 늘려**(§19-b-5) 소스 수를 늘리는 것이고, 그것은 이 함수가 아니라
       `app/queries.py` 몫이다. 여기서 있는 척하지 않는다.
    🔴 깊은 모드의 열기 예산은 배치보다 **작아지지 않는다** — 모드를 켜서 더
       얕아지면 그것은 버그다.
    """
    if mode not in MODES:
        raise ValueError(f"모르는 예산 모드: {mode!r} (있는 것: {MODES})")
    # 🔴 ② **빗나간 각도 상한**은 yaml 이 정한다(사용자 지시: 숫자는 실제 테스트로).
    #    ⚠️ `searches` 와 다르다 — 맞힌 각도는 세지 않는다.
    # 🔴 **지역 import** — `app.rules` 가 `app.cells` 를 쓰지는 않지만, 모듈 상단에서
    #    묶으면 import 고리가 생길 위험이 있다(세포는 가장 아래 층이다).
    from app import rules
    pol = rules.catalog_policy()
    angles = int(pol["max_angles"])
    llm_sec = float(pol["llm_seconds"])
    if mode == SLATE:
        return Budget(searches=n_sources or 1, fetches=fetches, angles=angles,
                      llm_seconds=llm_sec)
    # 🔴 개수를 올리면서 **시간 상한을 함께 건다.** 하나만 걸면 못 막는다
    return Budget(searches=n_sources or 1, fetches=max(fetches, DEEP_FETCHES),
                  seconds=SECONDS_OF[mode], angles=angles, llm_seconds=llm_sec)


@dataclass
class Budget:
    """§19-a 예산. 🔴 경기별로 **고정**하고 잔여만 재분배한다(§12-d).

    세포 하나가 슬레이트 전체 예산을 먹지 않게 한다.

    ⚠️ **그 고정은 배치 가정이다.** 질문형은 경기가 하나다 — `budget_for` 를 보라.
    """

    searches: int = 3
    fetches: int = 4
    #: 🔴 **시간 상한(초).** `None` 이면 안 건다(배치는 개수가 작아 필요 없다).
    seconds: float | None = None
    used_searches: int = 0
    used_fetches: int = 0
    #: 🔴🔴 **빗나간 각도 상한**(사용자 설계 2026-10-02 ②).
    #
    #  > 빗나가면 각도를 바꾼다 … 관련 0건이면 다음 템플릿
    #
    #  ⚠️ 전 판은 검색 **횟수**만 셌다 — 템플릿이 4개인 유형은 4번째를 영영 못 던지고,
    #     1번째에서 맞혀도 남은 예산이 돌아오지 않았다.
    #  🔴 이 칸은 **빗나간 각도만** 센다. 맞히면 그 자리에서 멈추므로 남은 각도를 안 쓴다.
    #     `None` 이면 안 건다(배치는 `searches` 로 충분하다).
    angles: int | None = None
    used_angles: int = 0
    #: 🔴🔴 **LLM 총 시간 상한(초)**(사용자 지시 2026-10-02 *"지연 상한 걸고"*).
    #  실측: ③ 한 건에 수 분 — 세포 10개면 질문 하나가 40분이 된다.
    #  ⚠️ 호출 **횟수**만 막던 `llm_budget` 으로는 못 막았다 — 시간을 함께 건다.
    llm_seconds: float | None = None
    llm_spent: float = 0.0
    out_of_llm_time: bool = False

    #: 🔴 각도로 끊겼나 — **횟수·시간으로 끊긴 것과 사유가 다르다**
    out_of_angles: bool = False
    #: 🔴 시간으로 끊겼나 — **개수로 끊긴 것과 사유가 다르다**
    out_of_time: bool = False
    started: float = field(default_factory=time.monotonic)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def _timed_out(self) -> bool:
        if self.seconds is None or self.elapsed <= self.seconds:
            return False
        self.out_of_time = True
        return True

    def take_llm(self, seconds: float) -> bool:
        """🔴 LLM 에 `seconds` 를 더 쓸 수 있나. 못 쓰면 `False` + 사유 칸을 세운다."""
        if self.llm_seconds is None:
            return True
        if self.llm_spent >= self.llm_seconds:
            self.out_of_llm_time = True
            return False
        self.llm_spent += max(0.0, float(seconds))
        return True

    def take_angle(self) -> bool:
        """🔴 **빗나간 각도 하나를 쓴다.** 더 쓸 수 없으면 `False`.

        ⚠️ 맞힌 각도에는 부르지 않는다 — 그것이 이 칸의 뜻이다.
        """
        if self.angles is None:
            return True
        if self.used_angles >= self.angles:
            self.out_of_angles = True
            return False
        self.used_angles += 1
        return True

    def take_search(self) -> bool:
        if self.used_searches >= self.searches or self._timed_out():
            return False
        self.used_searches += 1
        return True

    def take_fetch(self) -> bool:
        if self.used_fetches >= self.fetches or self._timed_out():
            return False
        self.used_fetches += 1
        return True

    @property
    def spent(self) -> str:
        """🔴 **시간까지 적는다.** 이 문장이 블랙보드의 unknown 사유로 간다 —
        거기에 시간이 없으면 *"열기 3/20"* 을 보고 "소스가 없었다"고 읽는다.
        """
        out = (f"검색 {self.used_searches}/{self.searches} · "
               f"열기 {self.used_fetches}/{self.fetches}")
        # 🔴 ② **빗나간 각도를 따로 적는다.** 검색 횟수와 섞으면 *"무엇을 늘려야
        #    하는가"* 를 모른다 — 각도가 모자란 것과 열기가 모자란 것은 다른 처방이다.
        #    ⚠️ 그리고 이 수가 **상한을 정하는 자료**다(사용자 지시: 실제 테스트로 정한다).
        if self.angles is not None:
            out += f" · 빗나간 각도 {self.used_angles}/{self.angles}"
            if self.out_of_angles:
                out += " 🔴 각도 예산 소진"
        # 🔴 LLM 시간을 **따로** 적는다 — 이 수가 상한을 정하는 자료다
        if self.llm_seconds is not None and self.llm_spent:
            out += f" · LLM {self.llm_spent:.0f}/{self.llm_seconds:.0f}초"
            if self.out_of_llm_time:
                out += " 🔴 LLM 시간 소진"
        if self.seconds is not None:
            out += f" · {self.elapsed:.0f}/{self.seconds:.0f}초"
            if self.out_of_time:
                out += " 🔴 시간 예산 소진"
        return out


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **v5 §3-2 — 세포가 본 것을 한 곳에 모은다**(게이트 2)
# ══════════════════════════════════════════════════════════════════
#
#  카드가 스스로 적고 있던 줄: *"§3 에이전트 **도구 미배선** — `Tools.search`/
#  `fetch` 가 실제 통로에 아직 안 꽂혔다."*
#
#  🔴 **무엇을 꽂나** — 새로 긁지 않는다. 세포들이 **이미** 검색하고 본문을
#     받는다(실측 2026-10-04: 깔때기 `queries` 23 · `fetched` 107). ⚠️ 에이전트가
#     또 긁으면 같은 페이지를 **두 배로** 두드리고 예산도 두 배가 된다.
#
#      search  →  그 경기에서 **본 검색 결과**(URL·제목·스니펫)
#      fetch   →  그 URL 의 **이미 받아 둔 본문**
#
#  ⚠️ 그래야 §4-4(*"검색 결과에 있던 URL 만"*)가 **자연히** 지켜진다 — 캐시에
#     없는 URL 은 애초에 줄 것이 없다.
#  🔴 그리고 §5-1(인용 대조)이 **그 본문으로** 돈다 — 받아 두지 않은 본문에 대고
#     인용을 검증할 수는 없다(`verifylayer` 의 fail-closed).
class _Field(MutableMapping):
    """🔴 `Seen.docs` 의 **한 칸을 가리키는 살아 있는 사전**.

    ⚠️ 사본을 돌려주면 `tools.bodies[url] = …` 이 **임시 사전에** 쓰이고 조용히
       사라진다. 🔴 그래서 뷰다 — 읽기·쓰기가 전부 원본 한 곳으로 간다.
    """

    __slots__ = ("_docs", "_key")

    def __init__(self, docs: dict, key: str) -> None:
        self._docs, self._key = docs, key

    def __getitem__(self, url):
        box = self._docs[str(url)]
        got = box.get(self._key)
        if got in (None, ""):
            raise KeyError(url)
        return got

    def __setitem__(self, url, value) -> None:
        self._docs.setdefault(str(url), {})[self._key] = value

    def __delitem__(self, url) -> None:
        self._docs.get(str(url), {}).pop(self._key, None)

    def __iter__(self):
        return (u for u, box in self._docs.items()
                if box.get(self._key) not in (None, ""))

    def __len__(self) -> int:
        return sum(1 for _ in iter(self))

    def __repr__(self) -> str:
        return f"{{{self._key}: {len(self)}건}}"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **본문 저장·날짜 조회는 각각 한 함수다** — 지시서 2026-10-06 §3
# ══════════════════════════════════════════════════════════════════
#
# > 날짜 — 경로를 **하나로** 만든다. 이번 주에 날짜가 끊긴 경로가 **셋**이었다
# > (fetch 신규 · 본문 재사용 · 세포 `_remember_body`). 경로마다 고치는 방식은
# > **네 번째를 또 만든다.**
#
# 🔴 그래서 **이름이 둘**이다: 넣는 곳 `store_doc`, 읽는 곳 `doc_date`.
#    ⚠️ 계약 M130 이 `app/` 어디서든 `…bodies[x] = y` 를 AST 로 잡는다.


def store_doc(seen: object, url: object, body: object = "", *,
              published_at: object = None, date_source: str = "") -> None:
    """🔴🔴 **본문을 저장하는 유일한 자리**(지시서 §3).

    🔴 본문과 발행일을 **같이** 넣는다 — 따로 넣는 길을 두면 또 갈린다.
    ⚠️ `seen` 이 `None` 이면 아무것도 안 한다(호출부가 그것을 묻지 않아도 되게).
    """
    box = getattr(seen, "add_doc", None)
    if box is None:
        return
    box(url, body, published_at=published_at, date_source=date_source)


def doc_date(seen: object, url: object):
    """🔴 그 URL 의 **발행 시각** — 신규·재사용을 **가리지 않는다**(지시서 §3).

    ⚠️ 없으면 `None` 이다 — 그것이 *"그 페이지에 날짜가 없다"* 와 같은 뜻이다.
    """
    got = getattr(seen, "dates", None)
    if got is None:
        return None
    return got.get(str(url or ""))


@dataclass
class Seen:
    """🔴 한 경기에서 **본 것**. ⚠️ 더하기만 한다(빼거나 고치지 않는다)."""

    #: 🔴 순서를 지킨다 — 검색이 먼저 낸 것이 먼저다(에이전트가 그 순서를 본다)
    urls: list = field(default_factory=list)
    #: `url → (제목, 스니펫, 그 URL 을 낸 검색어)`
    meta: dict = field(default_factory=dict)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **받아 둔 문서 — 저장소는 하나다**(사용자 지시 2026-10-06)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 본문 캐시를 `url → {body, published_at, date_source}` 로 바꿔 **Seen
    #  > 하나**에 담는다. `bodies` 와 `dates` 를 **따로 들고 다니는 경로를
    #  > 없앤다.**
    #
    #  ⚠️ 실측 2026-10-06(북아일랜드–조지아): 본문은 `seen.bodies`(하위 과제를
    #     가로질러 쌓인다)에서 오고 날짜는 `Tools.dates`(하위마다 새로 생긴다)에서
    #     왔다. 🔴 그래서 **다른 하위가 받아 둔 본문을 인용한 변수**는 본문·인용은
    #     통과하고 **날짜만 비어** `date_missing` 으로 죽었다 — 그 경기에서 6건.
    #     ⚠️ 받은 문서 24건 **전부** 날짜가 있었다(`발행일 — 없다` 0건).
    #  🔴 한 저장소면 그 병이 **구조적으로 불가능하다.**
    docs: dict = field(default_factory=dict)

    @property
    def bodies(self) -> "_Field":
        """🔴 `url → 본문` — **`docs` 를 가리키는 뷰다**(사본이 아니다)."""
        return _Field(self.docs, "body")

    @property
    def dates(self) -> "_Field":
        """🔴 `url → 발행 시각` — 같은 저장소다. ⚠️ 없는 URL 은 아예 안 보인다."""
        return _Field(self.docs, "published_at")

    @property
    def date_sources(self) -> "_Field":
        """🔴 그 날짜가 **어디서 왔나**(본문·검색·URL) — #3 조용한 0 금지."""
        return _Field(self.docs, "date_source")

    def add_doc(self, url: object, body: object = "", *,
                published_at: object = None, date_source: str = "") -> None:
        """🔴🔴 **받아 둔 문서 한 건** — 본문·발행일·출처를 **같이** 넣는다.

        ⚠️ 셋을 따로 넣는 길을 두면 또 갈린다(그것이 이 결함이었다).
        🔴 **빈 것은 안 넣는다**(없는 것을 있는 척하지 않는다) — 그리고 **이미
           있는 값을 덮지 않는다**(먼저 연 쪽이 원본이다).
        """
        u = str(url or "").strip()
        if not u:
            return
        box = self.docs.setdefault(u, {})
        b = str(body or "")
        if b.strip() and not str(box.get("body") or "").strip():
            box["body"] = b
        if published_at is not None and box.get("published_at") in (None, ""):
            box["published_at"] = published_at
            box["date_source"] = str(date_source or "")

    def add_hit(self, url: object, *, title: str = "", snippet: str = "",
                query: str = "") -> None:
        """🔴 검색 결과 한 줄. ⚠️ 빈 URL 은 **안 넣는다**."""
        u = str(url or "").strip()
        if not u:
            return
        if u not in self.meta:
            self.urls.append(u)
        # ⚠️ 먼저 본 것을 **덮지 않는다** — 그 검색어가 그 URL 을 낸 까닭이다
        self.meta.setdefault(u, {"title": str(title or ""),
                                 "snippet": str(snippet or ""),
                                 "query": str(query or "")})

    def add_body(self, url: object, body: object, *,
                 published_at: object = None, date_source: str = "") -> None:
        """🔴 받아 둔 본문. ⚠️ **빈 본문은 안 넣는다**(없는 것을 있는 척하지 않는다).

        🔴 `add_doc` 의 얇은 겉면이다 — 저장소는 **하나**다(사용자 지시 2026-10-06).
        """
        if not str(body or "").strip():
            return
        self.add_doc(url, body, published_at=published_at,
                     date_source=date_source)

    def line(self) -> str:
        """🔴 카드에 적는 한 줄 — **수를 그대로**(#3).

        🔴 발행일 **채운 수도 함께** 적는다(§8 합격 기준이 `published_at 80%+`다).
        """
        return (f"§3-2 — 본 URL {len(self.urls)}개 · 본문 받은 것 "
                f"{len(self.bodies)}개 · 발행일 있는 것 {len(self.dates)}개")


@dataclass
class Source:
    """후보 소스 하나. §13 에서 뽑고 §19-e 점수표로 재정렬한다."""

    name: str
    kind: str                          # url | search
    url: str | None = None
    query: str | None = None
    #: 🔴🔴 **v5 §4-1 — 그 질의에 무엇을 넣었나.** `{team, opponent, competition,
    #  sport, when}`. ⚠️ 문지기가 **세 요소 이상**을 요구하고, 글에서 짐작하면
    #  상대·대회를 **못 센다**(이름을 모르니까) → 거짓 거부가 난다.
    #  🔴 `queries.variants` 가 이미 그 조각을 들고 있다(`_compose`) — 그대로 싣는다.
    parts: dict | None = None
    lang: str = "ko"
    tier: int = 2                      # §12-c-5 층
    parse: object = None               # (Fetched|list[dict]) -> list[Fact]
    #: 🔴 §19-b-3 — **기사 소스는 검증기를 통과해야 한다.** 공식 API·공식
    #   페이지(tier 1)는 발행 시각이 없으므로 fail-closed 날짜 검증에 걸린다 —
    #   그것은 검증기의 대상이 아니다(§12-c-5 가 공식을 1층으로 둔 이유다).
    verify: bool = False
    #: 🔴 §19-c — *"사실이 사실을 낳는다."* 연 자료가 **다른 자료를 가리킬** 때,
    #  그 주소를 내놓는 함수다. `(Fetched, Question) -> list[str]`.
    #
    #  ⚠️ 왜 파서가 못 하나: 파서는 **동기 함수**라 네트워크에 못 간다. 그래서
    #     "가리키기"와 "열기"를 가른다 — 파서가 가리키고 세포가 연다.
    #  🔴 실측 2026-10-01 이 이것을 요구했다. 사용자가 손으로 한 일이 이것이다:
    #     *"잡힌 건 양 팀 직전 경기 선발 XI라 그걸 기준 XI로 놓고 재작성한다."*
    #     경기 페이지가 `teamForm.linkToMatch` 로 직전 경기를 가리키고 있었다.
    #  ⚠️ **한 번만 따라간다**(2단 금지) — 링크를 계속 따라가면 예산이 샌다.
    follow: object = None              # (Fetched, Question) -> list[str]
    parse_follow: object = None        # (Fetched, Question) -> list[Fact]
    #: 🔴🔴 **그 소스의 따라가기 몫**(2026-10-04). ⚠️ `0` 이면 몫을 안 요구한다.
    #
    #  ⚠️ 실측 2026-10-04(밀워키 vs 샌디에이고): 깊이 세포 예산이
    #     `len(소스)+1 = 3` 이었고 박스스코어의 따라가기 **셋**이 그것을 다 썼다.
    #     그래서 새로 붙인 `MLB 예고 선발` 이 **`예산소진`** 으로 한 번도 안 돌았다 —
    #     즉 ①의 배선이 **예산에 막혀** 값을 못 냈다.
    #  🔴 소스가 **제 몫을 선언**한다. 호출부가 그 합으로 예산을 짓고(`analyze`),
    #     `_follow` 가 그 수로 **자기 소스의 주소를 자른다** — 한 소스가 남의 몫을
    #     먹지 못한다. ⚠️ 선언이 없으면(0) 종전대로 공유 예산을 쓴다.
    follow_max: int = 0
    #: 🔴 §17-b **L1~L3 추출 과제** — 규칙 파서가 못 읽는 형식의 **대체**다(§19-b-5).
    #
    #  ⚠️ 비면 쓰지 않는다. `("L1","L2")` 처럼 적으면 본문을 열었는데 규칙 파서가
    #     0건을 낸 자리에서 그 과제를 돌린다.
    extract_tasks: tuple[str, ...] = ()
    #: 🔴 §19-b-2 — *"스니펫에 답이 보여도 숫자·인용은 본문을 연다(web_fetch)."*
    #  스니펫만 근거면 soft 다(§19-b-3). hard 는 **본문 대조로만** 얻는다 —
    #  그래서 검색이 걸린 뒤 가장 좋은 URL 을 열고 `parse_body` 로 다시 읽는다.
    open_body: bool = False
    parse_body: object = None          # (Fetched, Question) -> list[Fact]
    #: 🔴 **요청 헤더.** 키를 헤더로 받는 무료 API 가 있다(football-data.org 의
    #  `X-Auth-Token`). ⚠️ **카세트에 담기지 않는다** — 열쇠는 url+질의로만
    #  만들고, 저장 본문에도 헤더는 안 들어간다(`app/cassette.py`).
    #  🔴 UA 위장이 아니다(§14-12) — `Net` 이 UA 를 봇으로 유지한다.
    headers: dict | None = None
    #: 🔴 **발행 시각이 없어도 soft 로 남긴다.**
    #
    #  §12-c-1 원문(사용자 결정 2026-09-27): *"날짜를 못 읽는 자료는 통과가 아니라
    #  거부(fail-closed). 일정·라인업 용도로는 쓰지 못하고 **soft 로만 남긴다**."*
    #  🔴 **"버린다"가 아니라 "soft 로만 남긴다"** 다 — 그 문장을 지키는 칸이다.
    #
    #  ⚠️ 실측 2026-09-30(단계 4): transfermarkt 경기 페이지·footboom1 라인업
    #     페이지에는 **발행 시각이 없다**(기사가 아니라 경기 데이터 페이지다).
    #     그래서 §9 필수 8건 ①④ 의 자료를 찾아 놓고 전부 거부했다.
    #  🔴 **이 칸을 켜는 조건**: 그 소스의 파서가 **§13-c ①**(기사에 그 경기 날짜가
    #     있는가)를 이미 적용했을 때만이다. 그것이 "그 경기 것인가"를 답하므로
    #     §12-c-1 의 목적(낡은 자료 배제)이 다른 수단으로 충족된다.
    #     ⚠️ 켜도 **hard 로 올라가지 않는다** — soft 다. 그것이 원문이다.
    dateless_ok: bool = False
    #: 🔴 **열지 않을 URL.** `(url) -> str|None` — 사유를 돌려주면 건너뛴다.
    #  §13-a 가 이름으로 댄 금지 소스가 검색 결과 1순위로 나오므로, 표에 안 넣는
    #  것만으로는 막히지 않는다(실측 2026-09-30).
    deny: object = None
    #: 🔴 **어느 자료를 먼저 열까.** `(text) -> bool` — 참인 것을 앞세운다.
    #  예산이 2~3건이므로 **아무 순서로 열면 맞는 페이지에 닿지 못한다.**
    #  ⚠️ 실측 2026-09-30: 세이부 라인업 검색이 51건을 받았고 그중 맞는 것은
    #     `lions-matome.com` 하나였다(제목에 `2026.9.29` 가 있다). 순서가 없으면
    #     Panasonic 프린터 구인 광고를 먼저 연다.
    prefer: object = None
    #: 🔴 **스니펫 사실을 쓰지 않는다** — URL 을 고르는 데만 쓴다.
    #  §19-g-1 의 일정 페이지가 그렇다: 스니펫에는 날짜가 없고, `slate_date_ok`
    #  는 **페이지 전체**의 날짜 표기를 봐야 판정할 수 있다(§12-c-7). 스니펫
    #  사실을 그대로 쓰면 지난주 일정이 오늘 것으로 들어온다(M13).
    body_only: bool = False
    #: 🔴 **먼저 물을 검색 엔진**(`config/search_routing.yaml`). 비면 지정하지 않는다.
    #
    #  ⚠️ 실측 2026-10-02: 지정 없이 쏘니 **질의를 무시하는 엔진**의 결과가 섞여
    #     들어왔고, 열기 예산 2건이 `viagogo 티켓`·`케이세이 전철 PDF`로 갔다.
    #     기사는 0건이었다. `google news` 로 지정하면 사람이 읽은 기사가 나온다.
    #  🔴 지정이 0건이면 사슬이 **지정 없이 한 번 더** 던진다(§19-b-4 대체) —
    #     그래서 좁게 지정해도 검색 경로가 죽지 않는다.
    engines: tuple[str, ...] = ()


def _new_querylog():
    """🔴 §4-1 검색어 기록. ⚠️ `dataclass` 기본값에 쓰려 함수로 둔다."""
    from app.querygate import QueryLog
    return QueryLog()


def may_search(*, agent_on: bool) -> tuple[bool, str]:
    """🔴🔴 **세포가 검색을 던져도 되나.** `(된다, 사유)` — 결정 ③ (2026-10-04).

    > v5에서 세포는 **계획기가 아니라 장부**다. 에이전트가 켜져 있으면 세포는
    > **검색하지 않고 커버리지 기록만** 한다. — 사용자 결정 2026-10-04

    ⚠️ **스위치를 새로 만들지 않는다** — `AGENT_ENABLED` **하나**가 원본이다.
       🔴 둘로 두면 *"에이전트는 켜고 세포 검색도 켠"* 상태가 생기고, 그것이
       사용자가 끄라고 한 **중복 비용**이다.
    """
    if agent_on:
        return False, ("§3 에이전트가 켜져 있다 — 세포는 **장부**다(검색은 "
                       "에이전트가 한다 · 결정 ③ 2026-10-04)")
    return True, "§3 에이전트가 꺼져 있다 — 세포가 종전대로 찾는다"


@dataclass
class Cell:
    """§19-a — 질문 + 의존 + 소스 + 예산 + 상태기계. `run()` 이 §19-b 루프다."""

    question: Question
    sources: list[Source]
    deps: list[str] = field(default_factory=list)
    budget: Budget = field(default_factory=Budget)
    #: 🔴 **우리 팀 스쿼드 명단**(§17-g-3 · M14). 선수명이 든 사실을 이것으로 가른다.
    #
    #  사용자 설계 2026-10-02: *"fotmob 스쿼드 명단과 기사 속 선수명 대조, 명단 밖
    #  선수뿐이면 폐기"*. ⚠️ 비면 **검사하지 않고 그 사실을 남긴다** — 통과시키는
    #  것이 아니라 "못 쟀다"로 둔다(hardness 를 내린다).
    roster: tuple[str, ...] = ()
    #: 🔴🔴 **v5 §4-1 — 같은 검색어를 두 번 던지지 않는다**(`duplicate_query`).
    #
    #  ⚠️ 세포마다 하나다 — 세포가 다른 질문을 묻는 것은 중복이 아니다.
    #     🔴 같은 세포에서 각도를 바꾼 척하는 것(글자만 다른 질의)을 막는다.
    querylog: object = field(default_factory=lambda: _new_querylog())

    #: 🔴🔴 **답을 찾아도 멈추지 않는다** — 소스마다 **다른 질문**일 때만 켠다.
    #
    #  ⚠️ 실측 2026-10-02 가 이것을 요구했다. 공식 깊이 소스가 여섯이었는데
    #     (순위 ×2 · 월간 득점 ×3 · 예고선발·날씨) 세포는 **첫 성공에서 돌아갔다**.
    #     그래서 순위표만 들어오고 **장소별 득점이 영영 안 와** 포아송 격자가 안 섰다.
    #  🔴 §19-b 의 *"찾으면 멈춘다"* 는 **한 질문**에 대한 규율이다. 한 세포에 담긴
    #     소스들이 서로 다른 사실을 내는 경우(공식 깊이)는 그 전제가 깨진다.
    #  ⚠️ 검색 세포에는 **켜지 않는다** — 켜면 답을 찾고도 남은 각도를 다 태운다.
    collect_all: bool = False

    #: 🔴🔴 **깔때기**(사용자 기술 지시 2026-10-03). 어느 칸에서 0 이 되는지 센다.
    #
    #  ⚠️ 안 주면 **자기 것을 만든다** — 호출부가 안 넘겼다고 세는 것이 멈추면
    #     그때부터 진단이 거짓이 된다(#3 조용한 0 금지).
    #  🔴 **종목 분기가 없다** — 야구·축구·하키 어디서든 같은 칸을 센다
    #     (사용자 지시 2026-10-03: *"야구뿐만 아니라 전경기다"*).
    funnel: object = None

    #: 🔴🔴 **v5 §3-2 — 본 것을 모으는 자리**(게이트 2). `None` 이면 안 모은다.
    #
    #  ⚠️ 깔때기와 같은 결이다 — 경기 하나에 **하나**를 만들어 모든 세포에
    #     넘긴다. 🔴 세포마다 따로 두면 에이전트가 그 중 하나만 본다.
    seen: object = None

    #: 🔴 §17-e **LLM 호출 예산** — 세포마다 따로 센다. 넘으면 **unknown 으로 둔다**
    #  (억지로 부르지 않는다). ⚠️ 검색·열기 예산과 **다른 예산**이다.
    llm_budget: object = None

    def __post_init__(self) -> None:
        # 🔴 §17-e 예산은 **세포마다 하나** — 안 주면 여기서 만든다
        if self.llm_budget is None:
            from app import llm
            self.llm_budget = llm.Budget()
        if self.funnel is None:
            from app.funnel import Funnel
            self.funnel = Funnel()
    state: str = PENDING
    reason: str = ""
    tried: list[str] = field(default_factory=list)

    async def run(self, net: Net, bb: Blackboard, *,
                  search: Search | None = None,
                  scores: "SourceScores | None" = None) -> str:
        """§19-b 탐색 루프. 반환은 최종 상태.

        1 넓게 → 2 좁힘 → 3 검증기 → 4 막히면 **대체** → 5 바꿔서 다시 →
        6 예산 소진이면 **unknown + 사유** → 7 발견은 **방송**.
        """
        if self.deps and not bb.ready(self.deps):
            self.reason = f"의존 미해결: {[d for d in self.deps if d not in bb.slots]}"
            return PENDING

        self.state = SEARCHING
        found_any = False
        order = scores.reorder(self.sources, self.question) if scores \
            else list(self.sources)

        for src in order:
            got = await self._try(src, net, bb, search)
            if scores:
                # 🔴 §19-e — 리그별로 센다. 지연은 **마감이 있을 때만** 잰다.
                scores.record(src.name, self.question.type,
                              self.question.league or "", hit=bool(got),
                              lag_minutes=lag_minutes(self.question)
                              if got else None)
            if not got and src.kind == "search":
                # ══════════════════════════════════════════════════════
                # 🔴 ② **관련 0건이면 다음 각도로** (사용자 설계 2026-10-02)
                # ══════════════════════════════════════════════════════
                #
                #  이 각도가 빗나갔다. 다음 각도를 쓸 수 있나 묻는다.
                #  🔴 **맞혔으면 이 줄에 오지 않는다** — 남은 각도는 안 쓴다.
                #  ⚠️ 끊길 때 **사유가 다르다**: 각도 소진 ≠ 검색 횟수 소진 ≠ 시간 초과.
                #     셋을 한 사유로 적으면 무엇을 늘려야 하는지 모른다.
                if not self.budget.take_angle():
                    self.tried.append(
                        f"각도 소진 — 빗나간 각도 {self.budget.used_angles}개"
                        f"(상한 {self.budget.angles}). 남은 소스 "
                        f"{len(order) - order.index(src) - 1}개를 안 던졌다")
                    break
            if got and self.collect_all:
                # 🔴 모아 두고 **다음 소스로 간다**(위 `collect_all` 주석)
                for f in got:
                    bb.write(f)
                found_any = True
                continue
            if got:
                for f in got:
                    bb.write(f)
                # 🔴 **답을 찾아도 버린 것은 남긴다**(리뷰 B3, 2026-09-30).
                #    종전에는 `self.tried` 에만 적혀 블랙보드·DB·요약에 **아무것도
                #    안 갔다.** 그러면 운영에서 "왜 근거가 이만큼인가"를 되짚을 수
                #    없다 — 계약은 `cell.tried` 객체를 직접 봐서 초록이었다.
                for why in self.tried:
                    bb.note(self.question.id, why)
                slot = bb.get(self.question.id)
                self.state = slot.state if slot else FOUND
                return self.state

        # 🔴 `collect_all` 세포는 **모은 것이 있으면 찾은 것이다**
        if found_any:
            for why in self.tried:
                bb.note(self.question.id, why)
            # ⚠️ **칸의 상태를 읽지 않는다.** 모은 사실은 `{질문}:{접미사}` 칸으로
            #    가고 이 질문 자체의 칸은 비어 있다. 그런데 `bb.note` 가 빈 칸을
            #    만들어 두므로(기본 상태 `unknown`) 그것을 읽으면 **성공을 unknown
            #    으로 적는다** — 실측 2026-10-02 에 카드가 *"깊이: unknown"* 으로
            #    나왔고 사실은 26건이 들어와 있었다.
            self.state = FOUND
            return self.state
        # 🔴 §19-b-6 — 예산 소진·전부 실패면 unknown 이고 **사유를 붙인다.**
        self.state = UNKNOWN
        self.reason = (f"{self.budget.spent} · 시도 {len(self.tried)}건"
                       + (f" ({', '.join(self.tried)})" if self.tried else ""))
        bb.unknown(self.question.id, self.reason)
        return self.state

    async def _try(self, src: Source, net: Net, bb: Blackboard,
                   search: Search | None) -> list[Fact]:
        if src.kind == "url":
            if not self.budget.take_fetch():
                self.tried.append(f"{src.name}:예산소진")
                return []
            got = await net.get(src.url or "", headers=src.headers)
            if got.dead:
                # §19-b-4 막히면 우회가 아니라 **대체**다
                self.tried.append(f"{src.name}:{got.reason}")
                return []
            facts = _parse(src, got, self.question)
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **§19-c 가 여기서 빠져 있었다** (실측 2026-10-02 라이브)
            # ══════════════════════════════════════════════════════════
            #
            #  검색 소스는 *"연 자료가 다른 자료를 가리키면 한 번 따라간다"* 를
            #  하고 있었다(아래 `_open_hits`). 그런데 **직접 주소 소스**는 안 했다.
            #  🔴 그런데 공식 API 깊이가 바로 그 꼴이다(`mlb.sources_context`·
            #     `nhl.sources_context`) — 즉 **야구·하키의 깊이가 통째로 끊겨
            #     있었다.**
            #
            #  실측(NHL 디트로이트 vs 레인저스, 2026-10-02):
            #    전: 박스스코어 1장 → `:info` 하나 → 변수 **0건** → 자료 부족
            #    `nhl.follow_links` 는 일정·선수·순위 **세 주소를 내고 있었고**
            #    아무도 그것을 부르지 않았다.
            #
            #  ⚠️ 축구(fotmob)는 **한 페이지에 다 들어 있어서** 이 구멍이 안 보였다.
            #     처음 실측한 경기가 축구였던 것이 이 결함을 가렸다.
            if facts:
                facts += await self._follow(src, got, net)
            return self._yield(src, got, facts)

        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **에이전트가 켜져 있으면 세포는 안 던진다** — 결정 ③ (2026-10-04)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 세포 검색은 **끈다**. v5에서 세포는 **계획기가 아니라 장부**다.
        #  > 에이전트가 켜져 있으면 세포는 **검색하지 않고 커버리지 기록만** 한다.
        #  > 지금 세포가 먼저 돌며 시간을 먹고 `query_too_bare` 26건을 만드는 건
        #  > **폐기할 경로에 비용을 쓰는 것**이다. — 사용자 결정 2026-10-04
        #
        #  ⚠️ 실측(게이트2 2판): MLB `query_too_bare` **26** · KBO **65**.
        #     그 질의는 **세포 것**이다(에이전트 것은 34/20 · 24/21 로 따로 센다).
        #  🔴 **각도는 그래도 센다** — `funnel.angle` 이 §7-5 R5(*"자료 부족"*
        #     선언 자격)의 재료다. 검색을 끄면서 그 수까지 멈추면 R5 가 **자격
        #     없이** 돌거나 영영 못 돈다.
        ok_s, why_s = may_search(
            agent_on=bool(config.get_settings().agent_enabled))
        if not ok_s:
            self.tried.append(f"{src.name}:{why_s}")
            self.funnel.drop(Reason.CELL_SEARCH_OFF, "queries")
            # 🔴 **장부는 계속 쓴다** — 그 각도를 에이전트가 덮는다는 기록이다
            self.funnel.angle(str(src.name or ""))
            return []

        # 검색 소스 — 🔴 수단이 없으면 **없다고 적는다**
        if not self.budget.take_search():
            self.tried.append(f"{src.name}:예산소진")
            return []
        if search is None or not getattr(search, "available", False):
            self.tried.append(f"{src.name}:검색 수단 미정")
            return []
        # 🔴 질문 타입을 넘긴다 — Google CSE 는 §19-i-3 배정 안에서만 돈다.
        #    ⚠️ 모든 검색 수단이 `qtype` 을 받지는 않는다(`SearxSearch` 는 안 받는다).
        #       **서명을 먼저 본다** — 종전에는 `except TypeError` 로 되시도했고,
        #       그 되시도가 `except SearchUnavailable` **밖**에 있어서 카세트 없음·
        #       예산 소진이 사유로 안 남고 사이클을 통째로 죽였다
        #       (실측 2026-09-30: §19-g 게이트가 이 버그를 잡았다).
        #    ⚠️ `TypeError` 로 가르는 것도 위험하다 — 수단 **안쪽**에서 난 TypeError
        #       를 "서명이 다르다"로 오독해 같은 질의를 두 번 던진다.
        kw = {"lang": src.lang}
        if _takes_qtype(search):
            kw["qtype"] = self.question.type
        # 🔴 **엔진 지정** — 서명을 먼저 본다(위와 같은 이유: TypeError 로 가르면
        #    수단 안쪽의 TypeError 를 오독해 같은 질의를 두 번 던진다).
        if src.engines and _takes_engines(search):
            kw["engines"] = list(src.engines)
        # 🔴 깔때기 ① 던진 검색어 — **던지기 직전**에 센다(실패해도 던진 건 던진 것)
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **v5 §4-1 문지기** — 세 요소 미만·중복은 **던지지 않는다**
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 종전에는 질의를 **던지고 나서** 결과를 걸렀다. 실측 2026-10-04:
        #     hits 1302 중 **1115 건이 쓰레기**(86%)였고 그것이 LLM 예산을 먹었다.
        #  🔴 §4-1 은 **질의 자체를 막는다** — 받고 나서 거르는 것보다 앞이다.
        from app import querygate as _QG
        ok_q, reason_q, why_q = self.querylog.check(
            str(src.query or ""), parts=getattr(src, "parts", None),
            # 🔴 결정 ⑥ — 유형은 **질의가 말한다**(선언된 정규식으로 가른다)
            kind=_QG.kind_of(str(src.query or "")))
        if not ok_q:
            self.tried.append(f"{src.name}:{why_q}")
            self.funnel.drop(reason_q, "queries")
            return []
        self.funnel.add("queries", 1, sample=str(src.query or ""))
        # 🔴🔴 **§7-5 — 사다리 단계(각도)를 센다.** `queries` 와 다른 수다:
        #    같은 각도로 열 번 던져도 **한 단계**다. ⚠️ 이 수가 없으면 R5
        #    *"자료 부족"* 을 선언할 **자격이 없다**(`r5gate`).
        self.funnel.angle(str(src.name or ""))
        try:
            hits = await search.query(src.query or "", **kw)
        except SearchUnavailable as exc:
            self.tried.append(f"{src.name}:{exc}")
            return []
        # 🔴 깔때기 ② 검색이 돌려준 자료
        self.funnel.add("hits", len(hits or []),
                        sample=str(getattr(hits[0], "url", "")) if hits else "")
        # 🔴🔴 **§3-2 — 에이전트가 쓸 수 있게 모아 둔다**(게이트 2).
        #    ⚠️ 새로 긁지 않는다 — **이미 받은 것**을 넘길 뿐이다.
        if self.seen is not None:
            for h in (hits or []):
                self.seen.add_hit(getattr(h, "url", ""),
                                  title=str(getattr(h, "title", "") or ""),
                                  snippet=str(getattr(h, "snippet", "") or ""),
                                  query=str(src.query or ""))
        if src.body_only:
            # 🔴 스니펫은 **URL 고르는 데만** 쓴다(§19-g-1 일정 페이지).
            return await self._open_hits(src, hits, net)
        dateless: list[Fact] = []
        facts = self._yield(src, hits, _parse(src, hits, self.question),
                            dateless=dateless)
        # 🔴 §19-b-2 — *"스니펫에 답이 보여도 숫자·인용은 본문을 연다."*
        #    스니펫 근거는 soft 다. 본문을 열어 hard 를 얻을 수 있으면 연다.
        if facts and src.open_body and src.parse_body is not None:
            harder = await self._open_body(src, facts, net)
            if harder:
                return harder
        if facts:
            # 🔴 **조용한 0 금지.** 날짜 때문에 옆으로 치운 사실이 있으면 그것도
            #    이름으로 남긴다 — 실측 2026-09-30: 날짜 있는 **엉뚱한** 사실 하나가
            #    통과하는 사이 진짜 타순 표 둘이 **사유 없이** 사라졌다. 그러면
            #    "왜 라인업이 한 칸뿐인가"를 되짚을 수 없다.
            #    ⚠️ 예산을 아끼려고 본문은 열지 않는다 — 이미 답이 하나 있다.
            if dateless:
                self.tried.append(
                    f"{src.name}:발행 시각 없어 옆으로 치운 사실 {len(dateless)}건 "
                    f"(§12-c-1 fail-closed · 본문은 안 열었다 — 이미 답이 있다)")
            return facts
        # 🔴 **날짜를 못 읽어서만 전부 떨어졌다.** 포기하지 않는다 — 발행 시각은
        #    페이지에 있다(실측 2026-09-30: SearXNG 는 날짜를 0% 준다).
        #    ⚠️ 여기서 멈추면 검색 경로 전체가 구조적으로 죽는다.
        if dateless:
            self.tried.append(
                f"{src.name}:스니펫에 발행 시각 없음 {len(dateless)}건 → 본문을 연다")
            return await self._open_dateless(src, dateless, net)
        # 🔴 **스니펫이 아무 사실도 못 냈다 — 그래도 본문을 연다**(§19-b-2).
        #    실측 2026-09-30(단계 4): `西武 スタメン 9月29日` 가 맞는 기사
        #    (`【試合実況】西武スタメン …（2026.9.29）`)를 찾았는데 **타순은 본문에
        #    있고 스니펫에는 제목과 광고 문구뿐**이었다. 그래서 사실 0건이 되고,
        #    종전 코드는 `facts` 가 비어 `open_body` 경로를 **건너뛰었다** —
        #    §19-b-2 가 노리는 상황이 정확히 그 반대다("스니펫에 답이 보여도
        #    숫자는 본문을 연다"). 타순은 숫자다.
        # 🔴🔴 **`parse_body` 가 없어도 본문을 연다 — 추출기가 읽기 때문이다.**
        #
        #  ⚠️ 라이브 실측 2026-10-02(소프트뱅크–치바롯데): 카탈로그 세포가
        #     **열기 0/2** 로 끝났다. 검색은 25건을 찾았는데 본문을 **한 번도 안 열어서**
        #     ③ 좁은 질문이 **아예 돌지 않았다.** 조건이 `parse_body is not None` 이라
        #     규칙 파서가 없는 소스는 이 문을 통과할 수 없었다.
        #  🔴 카탈로그 소스는 **규칙 파서가 없는 것이 정상이다** — 산문을 겨냥하므로
        #     읽는 것은 `extract_tasks` 다. 그래서 그 칸도 문을 연다.
        if hits and src.open_body and (src.parse_body is not None
                                       or src.extract_tasks):
            why = ("본문을 연다" if src.parse_body is not None
                   else f"본문을 연다 — 규칙 파서 없음, 추출기 {list(src.extract_tasks)}")
            self.tried.append(
                f"{src.name}:스니펫에 사실 0건 → {why}({len(hits)}건 중)")
            return await self._open_hits(src, hits, net)
        return []

    async def _open_dateless(self, src: Source, dateless: list[Fact],
                             net: Net) -> list[Fact]:
        """날짜만 못 읽은 사실들의 **페이지를 열어 발행 시각을 읽는다**(§19-b-2).

        🔴 페이지가 발행 시각을 안 적으면 **여전히 거부**다(fail-closed 유지).
           여기서 하는 일은 "못 읽었다"를 "읽어 봤다"로 바꾸는 것뿐이고, 날짜를
           만들어 넣는 것이 아니다(§11-3).
        """
        out: list[Fact] = []
        for f in dateless:
            if not f.source:
                continue
            if not self.budget.take_fetch():
                self.tried.append(f"{src.name}:본문 예산소진 "
                                  f"({len(dateless)}건 중 일부만 열었다)")
                break
            got = await net.get(f.source)
            if got.dead:
                self.tried.append(f"{src.name}:{f.source} {got.reason}")
                continue
            if got.published_at is None:
                # 🔴 페이지도 날짜를 안 적었다 — fail-closed 그대로다
                self.tried.append(
                    f"{src.name}:{f.source} 페이지에도 발행 시각이 없다(거부)")
                continue
            f.published_at = got.published_at
            # ⚠️ 본문이 생겼으니 **인용 대조**도 다시 할 수 있다(§12-c-6)
            kept = self._verified(src, [f])
            out.extend(kept)
            if out:
                break          # §12-d 예산 — 한 건 얻으면 충분하다
        return out

    async def _open_hits(self, src: Source, hits, net: Net) -> list[Fact]:
        """검색 결과의 URL 을 **예산 안에서 차례로 연다.**

        🔴 §19-b-4 — 첫 페이지가 검증기에 거부되면 **다음 페이지로 간다.** 그것이
           §19-g-1 의 경로다(다음스포츠 거부 → 다른 소스). 거부 사유는 전부 남는다.
        ⚠️ 자료가 왔는데 사실 0건인 것과 자료가 안 온 것을 구분해 적는다.
        """
        # 🔴 **맞을 것 같은 것을 먼저 연다.** 예산이 2~3건이라 순서가 결과를
        #    정한다 — 실측 2026-09-30: 51건 중 맞는 것은 하나였고, 순서가 없으면
        #    무관한 광고 페이지를 먼저 열어 예산을 버린다.
        #    ⚠️ 안정 정렬 — 같은 순위면 검색 순위를 지킨다.
        # 🔴🔴 **호스트로도 가른다**(실측 2026-10-02). `src.prefer` 는 그 소스만 아는
        #    기준이고, 이것은 **모든 소스에 공통**인 기준이다 — 기사 호스트를 먼저,
        #    티켓·쇼핑·전철 PDF·유소년 명단을 뒤로.
        #    ⚠️ `prefer` 가 이긴다 — 그 소스가 아는 것이 더 구체적이다.
        ranked = list(hits or [])

        # 🔴🔴 **그 팀의 현지 매체를 먼저 연다**(사용자 기술 지시 2026-10-03 · 기술 1).
        #    ⚠️ `rules.host_rank` 는 **전 지구 공용** 목록이다 — 자메이카 기사를
        #       찾는데 `espn.com` 과 `jamaica-gleaner.com` 이 같은 등급이면 순서가
        #       운에 달린다. 선언된 팀 매체는 **그보다 앞**이다.
        from app import entities as _ent
        mine_outlets = [o.lower() for o in _ent.outlets_of(self.question.team or "")]
        # 🔴 상대를 가리키는 **모든 이름**(공식명·별칭·현지 표기) — 귀속이 아니라
        #    **순서**에 쓴다. ⚠️ 비면 이 기준을 적용하지 않는다(상대를 모르는 세포가
        #    있다 — `starter_recent` 은 지난 등판을 묻는다).
        opp_names = [x.lower() for x in
                     (_ent.names_of(self.question.opponent or "")
                      + ([self.question.opponent_local]
                         if self.question.opponent_local else []))
                     if str(x or "").strip()]

        def _key(item):
            i, h = item
            url = str(getattr(h, "url", "") or "")
            pref = 1
            if callable(src.prefer):
                text = f"{getattr(h, 'title', '')} {getattr(h, 'snippet', '')}"
                try:
                    pref = 0 if src.prefer(text) else 1
                except Exception:                       # noqa: BLE001
                    pref = 1
            local = 0 if any(o in url.lower() for o in mine_outlets) else 1
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **양 팀을 함께 말하는 페이지를 먼저** — 사용자 수정 ② (2026-10-04)
            # ══════════════════════════════════════════════════════════
            #
            #  > 신원 필터(두 팀명·대회·날짜)를 제목+스니펫 단계에서 **먼저** 돌리고
            #  > 통과한 것만 본문을 받는다.
            #
            #  🔴 **하드 거부로 하지 않았다** — 그러면 *한 팀만* 말하는 기사가
            #     통째로 죽는다. 그런데 **결장·로테이션·감독 발언은 바로 그 기사에
            #     있다**(`Elmas 결장` 기사에 스코틀랜드는 안 나온다). 그 셋이
            #     지금 0건인 유형들이라 거부하면 고치려는 것을 더 망친다.
            #  ⚠️ 그래서 **순서**로 푼다: 열기 예산이 20인데 결과가 41건이면 순서가
            #     곧 "통과한 것만 받는다"다 — 양 팀 기사를 다 연 뒤에 한 팀
            #     기사가 열린다. 🔴 그리고 쓰레기는 ③(도메인·종목)이 **거부**한다.
            #     실측 2026-10-04 의 76건은 전부 ③에 걸리는 것들이다.
            both = 1
            if opp_names:
                blob = (f"{getattr(h, 'title', '')} "
                        f"{getattr(h, 'snippet', '')} {url}").lower()
                both = 0 if any(o in blob for o in opp_names) else 1
            return (pref, both, local, _R.host_rank(url), i)

        ranked = [h for _, h in sorted(enumerate(ranked), key=_key)]
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **배당 호스트는 아예 뺀다**(절대규칙 6 · 실측 2026-10-03)
        # ══════════════════════════════════════════════════════════════
        #
        #  실측(LG 트윈스 vs 기아 타이거즈): 이 자리를 지나 `intent` 세포가
        #  `888starz.bet/…/lg-twins-kia-tigers` 를 **열었다**. 북메이커 경기 페이지다.
        #  🔴 `host_rank` 의 "뒤로 미룸"으로는 못 막는다 — 예산이 남으면 결국 연다.
        #  ⚠️ 그 페이지가 본문을 안 줘서 이번엔 사고가 안 났을 뿐이다. 상태값은
        #     의도한 것이 동작한다는 증거가 아니다(CLAUDE.md #4).
        #  🔴 **버리되 센다** — 몇 건을 왜 뺐는지가 사유에 남는다(#3).
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **받기 전에 거른다** — 사용자 수정 ②③ (2026-10-04)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 신원 필터를 **제목+스니펫 단계에서 먼저** 돌리고, 통과한 것만 본문을
        #  > 받는다. **지금은 받고 나서 거른다.** / 도메인 등급표 — 스포츠 매체·
        #  > 협회·구단 공식만. rottentomatoes·tripadvisor·법률·SMS 류는 거부.
        #
        #  ⚠️ 종전에 이 자리는 **배당 호스트만** 봤다. 그래서 실측 2026-10-04 에
        #     76건(드라마 출연진·럭비·위키 경제·SMS 판매·법률 사무소)이 열렸고
        #     그것이 LLM 60초를 다 먹어 **진짜 프리뷰에 0초**가 남았다.
        #  🔴 셋을 **같은 자리**에서 본다 — 배당 · 스포츠 아님 · 다른 종목.
        #     목록은 전부 `config/search_routing.yaml` 선언이다(사본 금지).
        sport = str(getattr(self.question, "sport", "") or "")
        # 🔴🔴 **v5 §4-3 도메인 등급표**(2026-10-04) — `config/domains.yaml`.
        #    ⚠️ 종전엔 거부 목록 둘(`not_sport_hosts`·`other_sport_words`)뿐이고
        #       **등급**이 없었다. 🔴 등급이 있으면 `tip`(베팅 팁)을 **본문도
        #       안 받고**, `wiki` 를 배경으로 두고, `official` 에 hardness 2 를
        #       준다 — 거부/허용 두 갈래보다 많은 것을 말한다.
        from app import domains as _D
        kept, banned = [], []
        for h in ranked:
            url = str(getattr(h, "url", "") or "")
            title = str(getattr(h, "title", "") or "")
            why = _R.banned_host(url)
            if not why:
                ok, tier, said = _D.verdict(url, sport=sport, title=title)
                why = "" if ok else f"{said}"
                if ok:
                    # 🔴 등급을 **들고 간다** — §5-5 가 무게를 그것으로 센다
                    try:
                        h.tier_name = tier       # type: ignore[attr-defined]
                    except Exception:            # noqa: BLE001
                        pass
            (banned if why else kept).append((h, why))
        if banned:
            self.tried.append(
                f"{src.name}:{len(banned)}건을 **안 열었다** — {banned[0][1]}")
            logger.info("[%s] 배당 호스트 %d건 제외: %s", self.question.type,
                        len(banned),
                        [str(getattr(h, "url", ""))[:60] for h, _ in banned[:3]])
        ranked = [h for h, _ in kept]
        urls = [u for u in (getattr(h, "url", "") for h in ranked) if u]
        if not urls:
            self.tried.append(f"{src.name}:검색 0건")
            return []
        # 🔴 **팀을 말하지 않는 페이지는 열지 않는다.** 예산을 쓰기 전에 가른다.
        #
        #  ⚠️ 실측 2026-10-01: 새크라멘토 라인업 세포가 열기 20건 중 **9건을**
        #     `airbnb.ca/rooms/…`·`airbnb.gy/rooms/…`·`deadikace.com/concerts/`·
        #     `parissi.app/en/poi/…` 에 태웠다. 같은 세포가 **진짜 라인업 페이지**
        #     (`sportsbencher.com/lineups/sacramento-republic-fc-vs-las-vegas-lights-fc`)
        #     에도 닿았지만, 예산을 먼저 버린 뒤였다.
        #  🔴 판정은 `verify.mentions_team` 한 곳이고, 제목·스니펫·**주소**를 함께
        #     본다 — 위 라인업 주소에는 팀명이 들어 있다.
        #  ⚠️ 걸러낸 **개수만** 남긴다 — 줄마다 적으면 `tried` 가 넘친다.
        team = (self.question.team or "").strip()
        skipped_unrelated = 0
        for url in urls:
            if team:
                h = next((x for x in ranked if getattr(x, "url", "") == url), None)
                blob = (f"{getattr(h, 'title', '')} {getattr(h, 'snippet', '')} "
                        f"{url}") if h is not None else url
                if not _names_match(blob, team, self.question.local):
                    skipped_unrelated += 1
                    continue
            # 🔴 깔때기 ③ **우리 팀을 말하는 자료**만 여기까지 온다
            self.funnel.add("kept_identity", 1, sample=url)
            # 🔴 §13-a — **금지 소스는 열지 않는다.** 예산을 쓰기 전에 가른다.
            if callable(src.deny) and (why := src.deny(url)):
                self.tried.append(f"{src.name}:{url} 건너뜀 — {why}")
                continue
            if not self.budget.take_fetch():
                self.tried.append(f"{src.name}:본문 예산소진 "
                                  f"({len(urls)}건 중 일부만 열었다)")
                return []
            got = await net.get(url)
            # 🔴 §3-2 — 본문을 **받는 자리**에서 모은다(게이트 2 · 아래 함수)
            self._remember_body(url, got)
            if got.dead:
                self.tried.append(f"{src.name}:{url} {got.reason}")
                # 🔴 v5 §8-5·§8-6 — robots·도메인 거부를 **사유 코드로** 센다
                from app.reasons import Reason as _R2
                why = str(got.reason or "")
                self.funnel.drop(
                    _R2.ROBOTS_DENIED if "robots" in why else _R2.DOMAIN_DENIED,
                    "fetched")
                continue
            # 🔴 v5 §8-5 `fetched` — **본문을 실제로 받은** 건수다
            #    ⚠️ `kept_date`(문서) 와 다르다: 고른 것과 받은 것은 다르다
            #       (robots·도메인·상한이 그 사이에서 거른다).
            self.funnel.add("fetched", 1, sample=url)
            # 🔴 규칙 파서가 없으면 **건너뛴다** — 카탈로그 소스가 그 꼴이다.
            #    ⚠️ `src.parse` 를 대신 쓰면 스니펫 파서를 본문에 돌리게 되고,
            #       그것은 다른 일이다(그래서 둘을 가른다).
            parser = src.parse_body or (None if src.extract_tasks else src.parse)
            facts = _parse(src, got, self.question, parser=parser) if parser \
                else []
            if facts:
                # 🔴 §19-c — 연 자료가 **다른 자료를 가리키면** 한 번 따라간다.
                #    ⚠️ 예산 안에서만. 예산이 없으면 사유를 남기고 그만둔다.
                facts += await self._follow(src, got, net)
                return self._verified(src, facts)
            # ══════════════════════════════════════════════════════
            # 🔴🔴 **여기가 추출기 자리다** (사용자 지시 2026-10-02)
            # ══════════════════════════════════════════════════════
            #
            #  > 핵심은 "검색"이 아니라 "읽기"다 … 웹에 변수가 4개 다 있었는데
            #  > 0건을 가져왔다 … 봇이 이걸 못 읽는 한 어떤 리그 규칙을 더해도
            #  > 같은 벽에 부딪힌다
            #
            #  §17-b L1~L3 은 *"규칙 파서가 못 읽는 형식의 **대체**"* 다(§19-b-5).
            #  🔴 그 자리가 **정확히 이 줄**이다 — 열었고, 규칙 파서가 0건을 냈다.
            #  ⚠️ `NOT_WIRED` 에 *"측정 전에 붙이는 것은 추측이다"* 로 미뤄 뒀고,
            #     실측 2026-10-02(여자 아시안게임)이 그 조건을 채웠다: 변수 4개가
            #     전부 산문에 있었는데 가져온 것은 0건이었다.
            got_llm = await self._extracted(src, got, url)
            if got_llm:
                return self._verified(src, got_llm)
            self.tried.append(f"{src.name}:{url} 열었는데 사실 0건(검증거부·파서)")
        if skipped_unrelated:
            # 🔴 **조용히 지우지 않는다** — 몇 건을 왜 건너뛰었는지 남긴다
            self.tried.append(
                f"{src.name}:팀 언급 없어 안 연 자료 {skipped_unrelated}건 "
                f"(열기 예산을 지켰다)")
        return []

    async def _extracted(self, src: Source, got, url: str) -> list[Fact]:
        """§17-b L1~L3 — **산문을 읽는다.** 🔴 규칙 파서가 0건을 낸 뒤에만 부른다.

        ⚠️ **판정은 코드가 한다**(§17-c). LLM 이 하는 일은 *기사에서 사실을 뽑는 것*
           뿐이고 `direction`·`weight`·`strength`·`survival`·`verdict` 에 닿지 않는다.
        🔴 버린 것을 `tried` 에 남긴다 — 개수만 세면 프롬프트를 못 고친다(§19-b-6).
        """
        if not src.extract_tasks:
            return []
        from app import extract, readtext, searchcells
        html = getattr(got, "text", "") or ""
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **본문을 뽑고 관련 문단만 넘긴다** (사용자 기술 지시 2026-10-03)
        # ══════════════════════════════════════════════════════════════
        #
        #  > 나는 검색 요약이 아니라 **본문을 읽는다** … 팀·선수 이름이 나오는 문단만
        #  > 골라 LLM 에 넘긴다. **입력이 짧아야 8B 모델도 정확하다.**
        #
        #  종전: `_strip_tags`(태그만 걷는다) → `body[:4000]`(**앞을 자른다**).
        #  🔴 광고·메뉴가 입력을 채우고, 타순·발언은 기사 **뒤쪽**에 있어 잘렸다 —
        #     실측 로그가 *"본문 3329자 중 2500자만 넘겼다"* 를 네 번 적었고 그 네
        #     번이 전부 `unknown` 이었다.
        #  ⚠️ **규칙 파서는 종전 경로를 그대로 쓴다** — `trafilatura` 는 표를 지우고
        #     타순은 표에 있다. 이 문은 **LLM 추출기 전용**이다.
        #  🔴 질의는 **그 페이지를 찾은 검색어**다(팀·유형 낱말이 이미 들어 있다).
        focus, when_s, why, full_text = readtext.read(
            html, url=url,
            query=(src.query or f"{self.question.team or ''} "
                                f"{self.question.opponent or ''}"))
        # 🔴🔴 **최소 글자 수는 "뽑은 본문"으로 잰다 — 좁힌 글로 재지 않는다.**
        #
        #  ⚠️ 실측 2026-10-03: 이 상한은 **태그만 걷은 수만 자**를 전제로 정해졌다.
        #     `readtext` 가 **질의와 가까운 문단 몇 개**(271자·286자)만 넘기게 되자
        #     그 상한이 **깨끗하고 충분한 글을 거부했다.**
        #  🔴 상한의 뜻은 *"페이지가 너무 얄팍하면 부르지 않는다"* 다 — 그 판단은
        #     **본문 전체**로 해야 맞는다. 좁은 질문은 300자로도 답한다.
        full = full_text or len(searchcells._strip_tags(html))
        if focus:
            body = focus
            self.tried.append(f"{src.name}:본문 — {why}")
        else:
            body = searchcells._strip_tags(html)
            self.tried.append(f"{src.name}:{why} — 태그만 걷은 글로 간다")
        if full < EXTRACT_MIN_CHARS or not body.strip():
            self.tried.append(
                f"{src.name}:{url} 본문이 {full}자뿐 — 추출을 부르지 않았다"
                f"(최소 {EXTRACT_MIN_CHARS}자)")
            return []
        # 🔴🔴 **v5 §4-3 — `wiki` 는 5만 자에서 자른다**(배경이다).
        #    ⚠️ 거부가 아니라 **절단**이다 — 위키 대표팀·감독 문서는 쓸 만하고,
        #       나라·역사 문서가 긴 것이다(실측: 109,714자·180,470자).
        from app import domains as _D3
        cap = _D3.max_chars(_D3.tier_of(url))
        if cap and full > cap:
            self.tried.append(
                f"{src.name}:{url} 본문 {full:,}자 → **{cap:,}자로 잘랐다**"
                f"(§4-3 `wiki` 등급 · 배경이다)")
            body = body[:cap]
            full = min(full, cap)
        # 🔴 **너무 길면 부르지 않는다**(사용자 수정 ② · 2026-10-04)
        if full > EXTRACT_MAX_CHARS:
            self.tried.append(
                f"{src.name}:{url} 본문이 **{full:,}자** — 추출을 부르지 않았다"
                f"(상한 {EXTRACT_MAX_CHARS:,}자). ⚠️ 이 길이는 경기 기사가 아니라 "
                f"나라·역사 문서다 — 실측 2026-10-04 에 위키 18만 자가 LLM 예산을 "
                f"먹었다")
            return []
        out: list[Fact] = []
        pol = __import__("app.rules", fromlist=["x"]).catalog_policy()
        per_call = float(pol.get("llm_timeout_sec") or 30)
        for task in src.extract_tasks:
            # 🔴 **시간을 먼저 본다**(사용자 지시 2026-10-02). 횟수만 막으면 느린
            #    호출 하나가 질문 전체를 잡아먹는다 — 실측에서 그랬다.
            if not self.budget.take_llm(per_call):
                self.tried.append(
                    f"{src.name}:🔴 LLM 시간 소진 — {task} 를 부르지 않았다"
                    f"({self.budget.llm_spent:.0f}/{self.budget.llm_seconds:.0f}초)")
                break
            if not self.llm_budget.take():
                self.tried.append(
                    f"{src.name}:§17-e LLM 예산 소진 — {task} 를 부르지 않았다")
                break
            # 🔴 `take()` 가 셌으므로 돌려준다 — `extract.run` 이 다시 센다
            self.llm_budget.used -= 1
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **③층 — 본문 날짜가 원본이다**(사용자 지시 2026-10-05)
            # ══════════════════════════════════════════════════════════
            #
            #  > `htmldate` 로 뽑은 이 값이 `published_at` 의 **원본**이다.
            #  > 검색 엔진이 준 날짜는 **보조로만** 쓴다.
            #
            #  ⚠️ 실사고: 이 줄이 **거꾸로**였다 —
            #     `getattr(got, "published_at") or _parsed(when_s)` 로 검색
            #     날짜를 **먼저** 쓰고 본문을 퇴로로 썼다.
            #  🔴 어느 쪽이 이기나는 `net.pick_published` **한 곳**이 정한다(#1).
            from app import net as _N
            said, why_date = _N.pick_published(
                when_s, getattr(got, "published_at", "") or "")
            when = _parsed(said) if said else None
            logger.info("[cell] 발행일 — %s (%s)", said or "없다", why_date)
            facts, dropped = await extract.run(
                task, title="", body=body, question_id=self.question.id,
                source=url, published_at=when,
                team=self.question.team, budget=self.llm_budget,
                # 🔴 한 번 부르는 시간도 묶는다 — 둘을 함께 걸어야 막힌다
                timeout=per_call, retry=int(pol.get("llm_retry") or 0))
            out += facts
            for why in dropped:
                self.tried.append(f"{src.name}:추출 {why}")
        if out:
            logger.info("[cell] §17-b 추출 %d건 · %s · %s",
                        len(out), src.extract_tasks, url)
        else:
            self.tried.append(
                f"{src.name}:{url} 추출도 0건 — 산문에 그 사실이 없다"
                f"({list(src.extract_tasks)})")
        return out

    async def _follow(self, src: Source, got, net: Net) -> list[Fact]:
        """§19-c — **자료가 가리킨 자료를 한 번 더 연다.**

        🔴 왜 이 자리인가: 파서는 동기 함수라 네트워크에 못 간다. 그래서 파서가
           *가리키고* 세포가 *연다*. 실측 2026-10-01 — 경기 페이지가
           `teamForm.linkToMatch` 로 직전 경기를 가리키는데 따라갈 길이 없었다.
        ⚠️ **한 번만**이다. 2단을 허용하면 링크를 타고 예산이 샌다.
        """
        if not (callable(src.follow) and callable(src.parse_follow)):
            return []
        try:
            urls = list(src.follow(got, self.question) or [])
        except Exception as exc:                            # noqa: BLE001
            self.tried.append(f"{src.name}:따라갈 주소를 못 냈다 — {exc}")
            return []
        # 🔴 **제 몫만큼만** 따라간다(위 `follow_max` 주석). ⚠️ 자른 것을 적는다.
        cap = int(getattr(src, "follow_max", 0) or 0)
        if cap and len(urls) > cap:
            self.tried.append(
                f"{src.name}:따라갈 주소 {len(urls)}건 중 **{cap}건만** — "
                f"선언한 몫이다(`follow_max`)")
            urls = urls[:cap]
        out: list[Fact] = []
        for url in urls:
            if callable(src.deny) and (why := src.deny(url)):
                self.tried.append(f"{src.name}:따라가기 건너뜀 {url} — {why}")
                continue
            if not self.budget.take_fetch():
                # 🔴 조용히 그만두지 않는다 — 몇 건을 못 따라갔는지 남긴다
                self.tried.append(
                    f"{src.name}:따라가기 예산소진 ({len(urls)}건 중 "
                    f"{len(out)}건만 열었다)")
                break
            nxt = await net.get(url)
            if nxt.dead:
                self.tried.append(f"{src.name}:따라가기 {url} {nxt.reason}")
                continue
            got_facts = _parse(src, nxt, self.question, parser=src.parse_follow)
            if got_facts:
                out += got_facts
            else:
                self.tried.append(f"{src.name}:따라갔는데 사실 0건 {url}")
        if out:
            logger.info("[cell] §19-c 따라가기 — %d건 (%s)", len(out), src.name)
        return out

    async def _open_body(self, src: Source, facts: list[Fact],
                         net: Net) -> list[Fact]:
        """§19-b-2 본문 열기. 🔴 **못 열면 스니펫 사실을 그대로 쓴다**(soft).

        ⚠️ 본문을 못 열었다고 사실을 버리지 않는다 — soft 근거도 근거다(§12-c-3).
           대신 왜 못 열었는지 `tried` 에 남긴다(조용한 0 금지).
        """
        url = next((f.source for f in facts if f.source), "")
        if not url:
            self.tried.append(f"{src.name}:본문 URL 없음")
            return []
        if not self.budget.take_fetch():
            self.tried.append(f"{src.name}:본문 예산소진")
            return []
        got = await net.get(url)
        if got.dead:
            # §19-b-4 — 본문이 막혔다. 스니펫은 살리고 사유를 남긴다
            self.tried.append(f"{src.name}:본문 {got.reason}")
            return []
        out = self._verified(src, _parse(src, got, self.question,
                                        parser=src.parse_body))
        if not out:
            self.tried.append(f"{src.name}:본문 열었는데 사실 0건(파서)")
        return out


    def _yield(self, src: Source, payload, facts: list[Fact], *,
               dateless: list[Fact] | None = None) -> list[Fact]:
        """🔴 **"자료가 안 왔다"와 "왔는데 못 뽑았다"를 구분해 적는다.**

        실측 2026-09-27: 반증 세포가 검색 31건을 받고 파서가 0건을 냈는데 사유가
        "시도 0건"이었다 — **거짓이다.** 어느 쪽인지 모르면 파서를 고칠지
        소스를 바꿀지 판단할 수 없다(§19-b-6 이 사유를 요구하는 이유다).
        """
        out = self._verified(src, facts, dateless=dateless)
        if not out and not facts:
            n = len(payload) if isinstance(payload, list) else 1
            self.tried.append(f"{src.name}:자료 {n}건인데 사실 0건(파서)")
        return out

    def _remember_body(self, url: str, got) -> None:
        """🔴🔴 **§3-2 — 받은 본문을 `Seen` 에 모은다**(게이트 2).

        ══════════════════════════════════════════════════════════════════
        🔴 왜 **따로 함수**인가 — 규칙 파서 경로를 건드리지 않기 위해
        ══════════════════════════════════════════════════════════════════

        ⚠️ 처음에 이 네 줄을 `_open_hits` 안에 **직접** 넣었다. 그러자 기존 계약
           `test_추출기_경로가_본문_추출을_쓴다` 가 빨개졌다 —
           *"규칙 파서는 종전 경로를 그대로 쓴다 — `trafilatura` 는 **표를
           지우고** 타순은 표에 있다. 이 문은 **LLM 추출기 전용**이다."*
        🔴 **그 계약이 맞다.** 내 수집은 규칙 파서가 보는 것을 바꾸지 않지만
           (옆에서 한 번 더 뽑는다), 그 함수 안에 이름이 있으면 **다음 사람이
           규칙 파서를 그 경로로 돌려도 계약이 안 막는다.**
        → 그래서 **옆 함수**로 뺐다. 규칙 파서는 `got.text` 를 그대로 받는다.

        ⚠️ `trafilatura` 로 뽑은 글을 모은다 — 광고·메뉴가 섞인 글에 대고 인용을
           대조하면 엉뚱한 문자열이 맞아 버린다(§5-1).
        🔴 **못 뽑으면 태그만 걷은 글**이라도 모은다 — 빈손보다 낫고, 못 모으면
           §5-1 이 *"인용이 본문에 없다"*(= 지어냈다)로 적어 **거짓 사유**가 된다.
        """
        if self.seen is None:
            return
        html = getattr(got, "text", "") or ""
        if not html:
            return
        from app import readtext, searchcells
        # ══════════════════════════════════════════════════════════════
        # 🔴🔴 **날짜를 버리지 않는다** — 실측 2026-10-06(재실행)
        # ══════════════════════════════════════════════════════════════
        #
        #  ⚠️ 종전 이 줄은 `text, _when = …` 이었다 — 발행일을 **`_when` 으로
        #     버렸다.** 🔴 그 본문은 `seen` 에 날짜 없이 들어가고, 그것을 인용한
        #     변수는 검증층에서 `date_missing` 으로 죽는다.
        #  🔴 실측: 1차 재실행에서 `date_missing` 이 **6 → 20** 으로 **늘었다**.
        #     `Tools._open`(에이전트 경로)만 고쳤고 **이 세포 경로**가 남아
        #     있었기 때문이다 — 그 판에서 에이전트 fetch 가 32 → 9 로 줄어
        #     날짜 없는 본문의 몫이 커졌다.
        #  ⚠️ `extract` 는 `htmldate` 결과를 **이미 들고 있었다** — 또 "돌았는데
        #     결과가 안 쓰인" 자리다(커밋 1370ead 와 같은 병).
        text, when = readtext.extract(html, url=url)
        store_doc(self.seen, url, text or searchcells._strip_tags(html),
                  published_at=when,
                  date_source="본문(세포 fetch · htmldate)")

    def _verified(self, src: Source, facts: list[Fact], *,
                  dateless: list[Fact] | None = None) -> list[Fact]:
        """§19-b-3 검증기 통과. 🔴 **거부된 항목도 사유를 남긴다**(§17-g-4).

        ⚠️ `src.verify` 가 False 인 공식 소스는 그냥 통과한다 — 그 판단은
           `Source` 가 하고, 여기서 층을 다시 짓지 않는다(사본 금지).

        🔴 `dateless` 를 주면 **날짜를 못 읽어서만 떨어진 것**을 거기 담는다.
           실측 2026-09-30: SearXNG 결과 20건 중 발행 시각이 있는 것이 **0건**
           이었다. 스니펫만 보면 §12-c-1 fail-closed 가 검색 근거를 **구조적으로
           전부** 떨어뜨린다 — 그때 갈 곳은 "포기"가 아니라 §19-b-2(본문을 연다)다.
           날짜는 페이지에 있다(`net.published_at_of`).
        """
        if not src.verify or not facts:
            # 🔴 깔때기 ④ — 검증기를 **안 거는** 소스(공식 API)는 그대로 통과다
            self.funnel.add("kept_date", len(facts))
            return facts
        # 🔴 **재현에는 시계가 필요하다.** `replay` 면 카세트가 녹음된 날을 "지금"
        #    으로 삼는다 — 안 그러면 09-27 카세트가 09-30 에 전부 "3일 지난 기사"로
        #    거부된다(실측 2026-09-30, §19-g 게이트가 잡았다).
        #    ⚠️ 운영(`off`)에서는 **진짜 지금**이다 — 과거 시각으로 돌지 않는다.
        now = cassette.reference_now()
        kept: list[Fact] = []
        for f in facts:
            # 🔴 **다른 경기의 기록은 기사 검증기의 대상이 아니다.**
            #    신선도(①)·경기 후 기사(②)는 *기사*를 겨냥한 규칙이고, 기준 XI 는
            #    과거 경기에서 **일부러** 가져온다(사용자 글 첫 문장).
            #    ⚠️ 구멍이 되지 않게 **조건을 확인한다** — 어느 경기에서 왔는지가
            #       없거나 hard 로 들어오면 **거부한다.**
            if f.from_past_match:
                v = f.value if isinstance(f.value, dict) else {}
                if not v.get("from_match"):
                    self.tried.append(
                        f"{src.name}:과거 경기 기록인데 출처 경기가 없다 — 거부")
                    continue
                if f.hardness != "soft":
                    self.tried.append(
                        f"{src.name}:과거 경기 기록이 soft 가 아니다 — 거부")
                    continue
                self.tried.append(
                    f"{src.name}:과거 경기 기록으로 받았다 "
                    f"({v.get('from_match')} · {v.get('from_date')})")
                kept.append(f)
                continue
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **§12-c-2 를 킥오프로 집행한다** (사용자 지시 2026-10-02)
            # ══════════════════════════════════════════════════════════
            #
            #  `V.check_article` 은 **"지금"만** 안다 — *우리 경기가 언제인지*는
            #  모른다. 그래서 *"킥오프 뒤에 나온 자료"* 를 못 걸렀고, 그 검사는
            #  §3 스키마(`types.Variables`)에만 있었다. 그런데 단계 4 **측정은
            #  사실을 직접 센다** → 구멍이 측정에 그대로 비쳤다:
            #
            #    실측 2026-10-02: 경기(3-2 승) **뒤**의 순위표를 경기 **전**
            #    사실로 쓰고 있었다 — 순위가 2위로 들어왔고 경기 전에는 4위였다
            #
            #  🔴 사실이 태어나는 자리에서 막는다. 그러면 사유가 `tried` 에 남고
            #     측정·카드·DB 가 **같은 것을 본다.**
            #  ⚠️ `live_score` 는 예외다 — 그 세포는 **경기 중**을 보라고 있다.
            if (f.published_at is not None and self.question.deadline
                    and self.question.type != Q_LIVE
                    and f.published_at >= self.question.deadline):
                self.tried.append(
                    f"{src.name}:경기 후 자료 — 발행 {f.published_at:%m-%d %H:%M}Z "
                    f"≥ 킥오프 {self.question.deadline:%m-%d %H:%M}Z (§12-c-2)")
                continue
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **명단 대조** — "손흥민이 나오면 버린다"(사용자 설계 2026-10-02)
            # ══════════════════════════════════════════════════════════
            #
            #  실측 2026-10-02: 여자 아시안게임을 물었는데 **남자 대표팀** 자료가
            #  들어왔다. 날짜도 같고 팀 이름도 글자까지 같아 다른 가드로는 못 막았다.
            #  🔴 **명단은 모호하지 않다** — 손흥민은 여자 대표팀 명단에 없다.
            #  ⚠️ 명단을 모르면 **막지 않고 soft 로 내린다**(§12-c-1 과 같은 규율).
            who = _player_of(f)
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **주체 귀속** — 그 기사가 **우리 팀** 이야기인가 (2026-10-03)
            # ══════════════════════════════════════════════════════════
            #
            #  실측(콜롬비아 vs 파라과이): 파라과이 수비 결장을 물었더니 좁은 질문이
            #  `yes` 를 내고 인용이 이것이었다 —
            #    *"Toluca have confirmed **Alexis Vega** has suffered an injury
            #      that will keep him out of **Mexico's** upcoming **November**
            #      international friendlies"*
            #  🔴 멕시코 선수 · 11월 경기다. 인용이 본문에 실재해서 `hard` 로
            #     통과했고 변수가 **거짓으로** 섰다.
            #
            #  🔴 **그 사실을 우리 경기에 붙일 근거가 하나라도 있어야** 한다:
            #       ① 기사가 우리 팀을 말한다           또는
            #       ② 주체(선수)가 우리 **명단**에 있다  (아래 `squad_check` 가 본다)
            #     둘 다 **없으면** 귀속할 근거가 0 이고, 그러면 우리 경기가 아니다.
            #
            #  ⚠️ **추출기 사실에만** 건다 — 규칙 파서는 자기 소스가 어느 팀 것인지
            #     알고 뽑는다(공식 API 의 팀별 표). 거기 걸면 멀쩡한 것을 버린다.
            #  ⚠️ 주체가 **있을 때는 여기서 막지 않는다** — 명단 대조가 그 일을
            #     더 정확히 한다(명단을 모르면 `soft` 로 내리는 규율까지 포함).
            #     🔴 Vega 가 걸리는 자리는 그 명단 대조다(26명 스쿼드 밖이다).
            if _from_extractor(f) and not who:
                mine = (self.question.team or "").strip()
                blob = " ".join(str(x or "") for x in
                                (f.article_title, f.quote, f.article_body))
                # 🔴 **별칭으로도 본다**(기술 1). `Albirroja` 만 적힌 기사가
                #    파라과이 기사가 아니라고 하면 그것이 거짓이다.
                if mine and not _names_match(blob, mine, self.question.local):
                    self.tried.append(
                        f"{src.name}:🔴 주체 귀속 실패 — 기사에 `{mine}` 이 없고 "
                        f"주체(선수)도 없다 → 붙일 근거가 0 이다(§17-g-3)")
                    logger.info("[cell] 주체 귀속 실패 — 팀·주체 둘 다 없다 (%s)",
                                mine)
                    continue
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **두 팀이 다 나오나 · 명단 선수 2명 이상**(기술 5)
            # ══════════════════════════════════════════════════════════
            #
            #  사용자가 엉뚱한 기사를 버리는 기준 넷 중 **둘이 없었다**:
            #    `both_teams_named(article, m, ALIASES)`  두 팀이 다 나오나
            #    `roster_overlap(article, m.squads) >= 2` 명단 선수 2명 이상
            #
            #  ⚠️ 지금까지는 **우리 팀 하나**만 봤다 — 그래서 *"파라과이"* 가 스쳐
            #     나오는 다른 경기 기사가 통과했다.
            #  🔴 **추출기 사실에만** 건다(규칙 파서는 자기 소스가 어느 팀 것인지 안다).
            #  🔴 둘 다 **상대를 알 때만** 센다 — 모르면 검사가 약해지고 그 사실을
            #     사유로 남긴다(§13-c ② 와 같은 규율).
            if _from_extractor(f):
                blob2 = " ".join(str(x or "") for x in
                                 (f.article_title, f.quote, f.article_body))
                other_team = (self.question.opponent or "").strip()
                if other_team and not _names_match(
                        blob2, other_team, self.question.opponent_local):
                    self.tried.append(
                        f"{src.name}:🔴 두 팀 중 **상대({other_team})가 기사에 "
                        f"없다** — 다른 경기 이야기일 수 있다(기술 5)")
                    continue
                if not other_team:
                    self.tried.append(
                        f"{src.name}:⚠️ 상대를 몰라 **두 팀 검사가 약하다**")
                hits = _roster_overlap(blob2, self.roster)
                if self.roster and hits < ROSTER_OVERLAP_MIN:
                    self.tried.append(
                        f"{src.name}:🔴 명단 선수가 {hits}명뿐이다"
                        f"(최소 {ROSTER_OVERLAP_MIN}) — 그 경기 기사가 아니다")
                    continue
                if not self.roster:
                    self.tried.append(
                        f"{src.name}:⚠️ 명단을 몰라 **겹침 검사를 못 했다**")
            if who:
                from app import ids as _ids
                squad = _ids.squad_check(who, self.roster)
                if not squad.ok:
                    self.tried.append(f"{src.name}:{squad.reason}")
                    logger.info("[cell] 명단 밖 선수 — %s", squad.reason)
                    continue
                if squad.unknown:
                    f.hardness = "soft"
                    self.tried.append(
                        f"{src.name}:{who} — {squad.reason}(soft 로 내렸다)")
            # 🔴 **기사를 검사한다 — 우리가 뽑은 값이 아니다.**
            #    실사고 2026-09-30: 종전에는 `str(f.value)` 를 제목으로 넘겼고,
            #    그래서 우리가 추출한 날짜 `2026-09-26` 의 `09-26` 이 **스코어**로
            #    읽혀 경기 후 기사로 판정됐다. 그리고 그 말은 §12-c-2 가 **기사에
            #    적용된 적이 없다**는 뜻이었다.
            #    ⚠️ 기사를 모르면 빈 문자열이다 — **값을 지어내 넘기지 않는다.**
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **출처 층을 호스트가 정한다**(사용자 기술 지시 2026-10-03)
            # ══════════════════════════════════════════════════════════
            #
            #  > 출처 등급도 매긴다. 협회·구단 공식 > 전국지 > 현지지 > … >
            #  > **베팅 팁 사이트.** 봇은 팁 사이트를 최하 등급으로 두고 **단독으로는
            #  > 사실로 안 쓴다**.
            #
            #  ⚠️ 종전에는 `src.tier`(그 **소스가 선언한 층**)를 그대로 썼다 — 즉
            #     검색으로 나온 기사는 **전부 같은 층**이었고, 인도네시아 팁 사이트와
            #     전국지가 구분되지 않았다.
            #  🔴 표에 없는 호스트는 `src.tier` 로 간다(모르는 것을 최하로 떨어뜨리면
            #     멀쩡한 현지지가 죽는다).
            tier, why_t = _R.tier_of_host(str(f.source or ""), int(src.tier))
            if tier != src.tier:
                self.tried.append(f"{src.name}:{f.source} — {why_t} "
                                  f"(선언 {src.tier}층 → {tier}층)")
                f.tier = tier
            art = {"title": f.article_title, "body": f.article_body or f.quote or "",
                   "published_at": f.published_at, "tier": tier,
                   "quote": f.quote}
            got = V.check_article(art, now)
            if not got.ok:
                # 🔴 **날짜만 못 읽은 것**은 되살릴 수 있다 — 본문에 날짜가 있다.
                #    ⚠️ 다른 이유가 하나라도 섞였으면 되살리지 않는다(경기 후
                #       기사·예측 사이트는 본문을 열어도 여전히 부적격이다).
                if (got.unknowns == ["date"] and len(got.reasons) == 1
                        and f.published_at is None):
                    # 🔴 §12-c-1 — *"soft 로만 남긴다."* 파서가 §13-c 로 이미
                    #    "그 경기 것인가"를 답했으면 **버리지 않고 soft 로** 둔다.
                    if src.dateless_ok:
                        f.hardness = "soft"
                        self.tried.append(
                            f"{src.name}:발행 시각 없음 → soft 로 남긴다"
                            f"(§12-c-1 · §13-c 로 그 경기 것임은 확인)")
                        kept.append(f)
                        continue
                    if dateless is not None:
                        dateless.append(f)
                        continue
                self.tried.append(f"{src.name}:검증거부({'; '.join(got.reasons)})")
                logger.info("[cell] %s 검증 거부 — %s", src.name, got.reasons)
                continue
            f.hardness = got.hardness      # 🔴 가장 약한 층으로 내려간다
            kept.append(f)
        # 🔴 깔때기 ④ **검증기를 통과한 사실**(날짜·귀속·명단을 다 넘은 것)
        #    ⚠️ 이름이 `kept_date` 지만 여기서 떨어지는 사유는 날짜 하나가 아니다 —
        #       사용자가 준 칸 이름을 그대로 쓰되, **무엇이 떨어뜨렸는지는 `tried`**
        #       가 줄마다 적는다. 깔때기는 *"어디서"* 를, 사유는 *"왜"* 를 말한다.
        self.funnel.add("kept_date", len(kept))
        return kept


@functools.lru_cache(maxsize=None)
def _takes_qtype_of(cls) -> bool:
    return "qtype" in inspect.signature(cls.query).parameters


def _takes_qtype(search) -> bool:
    """이 검색 수단이 `qtype` 을 받나. 🔴 **서명으로 본다** — 예외로 가르지 않는다."""
    try:
        return _takes_qtype_of(type(search))
    except (TypeError, ValueError):
        return False


@functools.lru_cache(maxsize=None)
def _takes_engines_of(cls) -> bool:
    return "engines" in inspect.signature(cls.query).parameters


def _takes_engines(search) -> bool:
    """이 검색 수단이 `engines` 를 받나. 🔴 같은 이유로 **서명으로 본다**."""
    try:
        return _takes_engines_of(type(search))
    except (TypeError, ValueError):
        return False


#: 🔴 §17-b 추출기 과제 이름. `extract.run` 이 `f"{task}:{llm.MODEL}"` 로 적는다.
#   ⚠️ `extracted_by` 가 비어 있는 사실도 있다(시험 고정물·단순 파서) — 그것을
#      추출기로 보면 멀쩡한 것을 버린다. 그래서 **이름으로 정확히** 가린다.
_EXTRACTOR_MARKS = ("L1:", "L2:", "L3:", "ASK:")


#: 🔴 기사에 **우리 명단 선수가 몇 명** 나와야 그 경기 기사인가(기술 5).
#
#  > `roster_overlap(article, m.squads) >= 2`
#
#  ⚠️ `1` 로 두면 이름이 한 번 스친 기사가 통과한다(실측: `Alexis Vega` 가 그 꼴).
#     🔴 사용자 예시 코드가 `>= 2` 다 — 그것을 그대로 쓴다.
ROSTER_OVERLAP_MIN = 2


def _roster_overlap(blob: str, roster) -> int:
    """🔴 그 글에 **우리 명단 선수가 몇 명** 나오나.

    ⚠️ 이름 대조는 `ids` 가 원본이다 — 성만 적힌 기사도 맞아야 한다.
    """
    if not roster:
        return 0
    low = str(blob or "")
    n = 0
    for name in roster:
        nm = str(name or "").strip()
        if not nm:
            continue
        # 🔴 성명 전체 **또는 그 조각**이 보이면 센다 — 기사는 성만 쓴다
        #    (`Miguel Almirón` → `Almirón`). ⚠️ 한 글자 조각은 안 센다.
        parts = [nm] + [p for p in nm.split() if len(p) > 1]
        if any(p in low for p in parts):
            n += 1
    return n


def _names_match(blob: str, team: str, local: str | None) -> bool:
    """🔴 그 글이 **우리 팀**을 말하나 — 공식명과 **현지 별칭**을 다 본다(기술 1).

    ⚠️ 판정 규칙은 `verify.mentions_team` 이 원본이다 — 여기서 다시 쓰지 않고
       **이름 목록만** 넓힌다(`entities.names_of`).
    """
    from app import entities
    # 🔴 공식명 + 별칭을 **한 목록으로** 본다(`entities.names_of`)
    for i, name in enumerate(entities.names_of(team) or [team]):
        if V.mentions_team(blob, name, local if i == 0 else None):
            return True
    return False


def _parsed(s: str):
    """🔴 `trafilatura` 가 읽은 발행일 문자열 → `datetime`. 못 읽으면 `None`.

    ⚠️ 날짜 파싱 규칙은 `verify.parse_when` 이 원본이다 — 여기서 다시 쓰지 않는다.
    """
    if not str(s or "").strip():
        return None
    return V.parse_when(str(s).strip())


def _from_extractor(f) -> bool:
    """🔴 이 사실이 **LLM 추출기**가 낸 것인가(규칙 파서가 아니라)."""
    return str(getattr(f, "extracted_by", "") or "").startswith(_EXTRACTOR_MARKS)


def _player_of(f) -> str:
    """사실에서 **선수 이름**을 꺼낸다. 🔴 없으면 빈 문자열(명단 검사를 걸지 않는다).

    ⚠️ 칸 이름이 소스마다 다르다 — 추출기는 `player_name`, fotmob 은 `player` 다.
       **둘 다 본다.** 한쪽만 보면 그 소스의 사실이 검사를 비껴간다.
    """
    v = f.value if isinstance(getattr(f, "value", None), dict) else {}
    for key in ("player_name", "player", "name"):
        got = str(v.get(key) or "").strip()
        if got:
            return got
    return ""


def _parse(src: Source, payload, q: Question, *, parser=None) -> list[Fact]:
    """소스의 파서를 부른다. 🔴 파서가 없으면 **사실 0건**이다 — 지어내지 않는다.

    `parser` 를 주면 그것을 쓴다 — §19-b-2 본문 파서(`parse_body`)가 그 길이다.
    """
    fn = parser if parser is not None else src.parse
    if fn is None:
        return []
    try:
        out = fn(payload, q) or []
    except Exception as exc:                        # noqa: BLE001
        logger.warning("[cell] %s 파싱 실패: %s", src.name, exc)
        return []
    for f in out:
        # 🔴 파서가 **자기 질문 id 를 정했으면 그것을 존중한다.** 덮어쓰면 한
        #    소스가 여러 주체를 낼 때(순위 30팀·라이브 5경기) 전부 한 질문에
        #    몰려 **모순으로 판정된다**(실측 2026-09-27 — 계약은 값 하나짜리
        #    대역이라 못 잡았다).
        if not f.question_id:
            f.question_id = q.id
        f.source = f.source or (src.url or src.query or src.name)
        f.publisher = f.publisher or src.name
        # 🔴 층은 **소스가 안다** — 파서가 적지 않았으면 여기서 싣는다.
        #    블랙보드의 모순 처리가 hardness 로 못 가르는 갈림을 이것으로 가른다.
        f.tier = f.tier or src.tier
        if f.fetched_at is None:
            f.fetched_at = datetime.now(timezone.utc)
        if f.team is None:
            f.team = q.team
    return out


# ══════════════════════════════════════════════════════════════════
# §19-e 소스 점수표 — 코드가 §13 순서를 스스로 고친다
# ══════════════════════════════════════════════════════════════════


@dataclass
class Score:
    hit: int = 0
    miss: int = 0
    lag_total: int = 0
    #: 🔴 **지연을 몇 번 실제로 쟀나.** `hit` 로 나누면 안 된다 — 적중했지만
    #  마감(T)을 모르는 질문(아침 1회 순위·슬레이트)은 지연을 **못 잰다**.
    #  그것을 0분으로 때우면 "가장 빠른 소스"로 올라가 순서를 망친다.
    #  `source_score.lag_min` 주석이 *"못 재면 NULL"* 이라고 못 박은 자리다.
    lag_n: int = 0

    @property
    def rate(self) -> float:
        n = self.hit + self.miss
        return self.hit / n if n else 0.5      # 모르면 중간

    @property
    def lag(self) -> float | None:
        """평균 지연(분). 🔴 **한 번도 못 쟀으면 `None`** — 0 이 아니다."""
        return self.lag_total / self.lag_n if self.lag_n else None


class SourceScores:
    """`(source, question_type, league)` 별 적중·지연을 쌓는다.

    🔴 **점수표는 데이터다**(§19-e). 사람 승인 없이 §13 문서를 바꾸지 않는다 —
       문서 갱신은 주간 루프에서 사용자 승인으로 한다.
    🔴 **열쇠에 `league` 가 있다.** §19-e 원문이 셋을 함께 적고, `source_score`
       표의 유일키도 셋이다. 종전 이 클래스는 둘(`source`,`qtype`)만 썼고 —
       그러면 KBO 에서 잘 듣는 매체가 NPB 순서를 밀어 올린다.
    """

    def __init__(self):
        self.table: dict[tuple[str, str, str], Score] = {}

    def record(self, source: str, qtype: str, league: str = "", *,
               hit: bool, lag_minutes: int | None = None) -> None:
        """한 번 시도한 결과. 🔴 `lag_minutes=None` 은 **못 쟀다**는 뜻이다."""
        s = self.table.setdefault((source, qtype, league or ""), Score())
        if hit:
            s.hit += 1
            if lag_minutes is not None:
                s.lag_total += int(lag_minutes)
                s.lag_n += 1
        else:
            s.miss += 1

    def reorder(self, sources: list[Source], q: Question) -> list[Source]:
        """적중률이 높고 빠른 소스를 먼저. ⚠️ **안정 정렬** — 같은 점수면 §13 순서.

        🔴 지연을 **못 잰 소스를 앞세우지 않는다.** `None` 을 0 으로 읽으면
           한 번도 시간을 못 잰 소스가 가장 빠른 것으로 올라간다.
        """
        def key(item):
            i, src = item
            s = self.table.get((src.name, q.type, q.league or ""))
            lag = s.lag if s else None
            return (-(s.rate if s else 0.5),
                    0 if lag is not None else 1,       # 잰 것이 먼저
                    lag if lag is not None else 0.0, i)
        return [src for _, src in sorted(enumerate(sources), key=key)]

    def report(self) -> list[str]:
        """🔴 **못 잰 칸을 이름으로** 낸다 — "평균 0분"으로 때우지 않는다."""
        out = []
        for (name, qtype, league), s in sorted(self.table.items()):
            lag = "지연 못 쟀다" if s.lag is None else f"평균 {s.lag:.0f}분"
            out.append(f"{name} · {qtype}{f' · {league}' if league else ''}: "
                       f"{s.hit}hit/{s.miss}miss ({s.rate:.0%}) {lag}")
        return out

    # ── §19-e 영속 — 🔴 **쌓여야 순서가 고쳐진다** ──────────────────
    async def load(self, pool) -> int:
        """표를 DB 에서 되살린다. 🔴 프로세스가 죽으면 학습이 0 으로 돌아가는
        것을 막는다 — §19-e 는 *"쌓이면 코드가 스스로 고친다"* 다.
        """
        rows = await pool.fetch(
            "SELECT source, question_type, league, hit, miss, lag_min "
            "  FROM source_score")
        for r in rows:
            s = Score(hit=int(r["hit"] or 0), miss=int(r["miss"] or 0))
            if r["lag_min"] is not None:
                # ⚠️ 표는 **평균**을 들고 있다. 되살릴 때 `lag_n=1` 로 두면 그
                #    평균이 다음 실측 한 건과 같은 무게가 된다 — 적중 수를
                #    무게로 쓴다(적중이 0인데 지연이 있는 행은 없다).
                s.lag_n = max(1, s.hit)
                s.lag_total = int(r["lag_min"]) * s.lag_n
            self.table[(r["source"], r["question_type"], r["league"] or "")] = s
        logger.info("[score] DB 에서 %d행 되살렸다", len(rows))
        return len(rows)

    async def flush(self, pool) -> int:
        """표를 DB 에 남긴다. 🔴 `lag_min` 은 **못 재면 NULL** 이다."""
        n = 0
        for (source, qtype, league), s in self.table.items():
            await pool.execute(
                "INSERT INTO source_score (source, question_type, league, "
                "hit, miss, lag_min) VALUES ($1,$2,$3,$4,$5,$6) "
                "ON CONFLICT (source, question_type, league) DO UPDATE "
                "SET hit = EXCLUDED.hit, miss = EXCLUDED.miss, "
                "    lag_min = EXCLUDED.lag_min, updated_at = now()",
                source, qtype, league,
                s.hit, s.miss,
                None if s.lag is None else int(round(s.lag)))
            n += 1
        logger.info("[score] DB 에 %d행 남겼다", n)
        return n


def lag_minutes(q: Question, when: datetime | None = None) -> int | None:
    """§19-e 지연 — **마감(T) 기준 몇 분 전에 답했나**. 🔴 모르면 `None`.

    §19-e 실측 표기가 *"西スポ(SB 라인업, **T-55분** hit)"* 이므로 기준은 경기
    시각이다. 마감이 없는 질문(아침 1회 순위·슬레이트)은 **못 잰다** — 0 이
    아니다(그것이 `source_score.lag_min` 이 NULL 을 받는 이유다).
    """
    if q.deadline is None:
        return None
    now = when or datetime.now(timezone.utc)
    if q.deadline.tzinfo is None or now.tzinfo is None:
        return None                     # 🔴 tz 없이 빼지 않는다 — 9시간 어긋난다
    return int((q.deadline - now).total_seconds() // 60)
