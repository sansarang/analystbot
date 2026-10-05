"""§5 — **시나리오 A~H 생성**(최대 8 · 결정 ① 2026-10-04). (출력 블록 6)

사용자 지시 2026-10-02: ⑧ → ⑨ → **⑥**. 블록 열 개 중 여섯째다.

⚠️ §9 는 단계 4 게이트(29%) 전에 단계 5·6 코드를 쓰지 말라고 한다. 사용자 지시가
   v4 보다 위다(`CLAUDE.md` 첫 규약) — *"게이트 판정은 나중에 다시 하기로 하고"*.
   → `docs/fable/questions/2026-10-02_stage5_partial.md`

## 🔴 이 파일이 지키는 것

| 규칙 | 어떻게 |
|---|---|
| §5-a 묶음 → A(홈 승)·B(원정 승)·C(무승부) | `classify` 의 방향 묶음을 그대로 받는다 |
| 축구는 C 가 비어도 **floor 로 생성** | *"무승부는 항상 살아 있는 결과"* |
| §5-b 스코어는 **템플릿이 정한다** | `rules.templates()` 를 읽는다 — 스코어를 베끼지 않는다 |
| §5-c 교차 규칙 **여섯 전부** | 발동/미발동과 **사유**를 함께 남긴다 |
| §5-d strength = 변수 weight 합 | 전제가 `replaced` 면 0(아직 `premise_check` 미구현) |
| §5-e narrative | **쓰지 않는다** — LLM L6 이고 미배선이다 |
| §7 R5 자료 부족 | 🔴 **부족이면 시나리오를 만들지 않는다**(R5 계약) |

🔴 **값을 지어내지 않는다.** 템플릿이 없는 종목(하키)·조건을 못 읽는 규칙은
   **이름으로 남기고 건너뛴다**(조용한 0 금지).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app import classify, league, rules, verify

logger = logging.getLogger(__name__)

#: §7 R5 — *"변수 3개 미만·반대 방향 0개면 자료 부족."*
MIN_VARIABLES = 3
MIN_DIRECTIONS = 2

#: 🔴🔴 **§6-2 — *"시나리오는 최소 4개"*.** 🔴 값은 yaml 이 정한다.
#
#  ⚠️ 왜 최소가 있나: 시나리오를 적게 만들면 생존이 **공짜로** 1.0 이 된다 —
#     죽을 자리가 없으니까. §6-7 이 그것을 *"거짓 1.0"* 이라 부른다.
MIN_SCENARIOS = rules.required_min()


def _letters() -> list[str]:
    """🔴 시나리오 글자들. **`types.ScenarioId` 가 원본**이다(사본 금지)."""
    import typing

    from app import types as _T
    return [str(x) for x in typing.get_args(_T.ScenarioId)]


#: 🔴🔴 **상한 8** — 사용자 결정 ① (2026-10-04). ⚠️ 수를 손으로 적지 않는다:
#   글자 수에서 **자라게** 한다(`ScenarioId` 를 늘리면 따라온다).
MAX_SCENARIOS = len(_letters())


def place_required(general: list, required: list, *, cap: int = 0) -> list:
    """🔴🔴 **필수형을 반드시 넣고**, 넘치면 일반 중 최저를 뺀다 — 결정 ①.

    > 필수형은 빈자리가 없으면 넣지 못하는 게 아니라 **항상 들어간다** — 일반
    > 시나리오가 8개를 넘을 때만 **strength 최저인 일반 시나리오**를 뺀다.
    > — 사용자 결정 ① 2026-10-04

    ⚠️ 사용자가 **B 를 거부한 까닭**이 여기 걸려 있다 — *"반대 방향 시나리오가
       빠질 위험"*. 🔴 그래서 빼는 기준은 **`strength` 최저**이고, 방향 묶음도
       센 것이면 안 빠진다.
    🔴 **필수형은 절대 안 뺀다** — 필수형만으로 상한을 넘기면 일반이 다 나간다.

    ⚠️ 받는 것은 `dict` 또는 `Draft` 둘 다다 — 호출부가 섞여 있다.
    """
    cap = int(cap or MAX_SCENARIOS)

    def _f(x, name, default=None):
        return x.get(name, default) if isinstance(x, dict) \
            else getattr(x, name, default)

    def _set_id(x, sid):
        if isinstance(x, dict):
            x["id"] = sid
        else:
            object.__setattr__(x, "id", sid) if getattr(
                type(x), "model_config", None) else setattr(x, "id", sid)

    need = list(required)
    # 🔴 일반은 **센 것부터** 남긴다 — 빠지는 것은 최저다
    rest = sorted(general, key=lambda x: -float(_f(x, "strength", 0.0) or 0.0))
    room = max(0, cap - len(need))
    kept = need + rest[:room]
    # 🔴 **글자를 다시 매긴다** — 남은 것이 `A` 부터 빈틈없이 받는다(출력 규격)
    out = []
    for sid, item in zip(_letters()[:cap], kept, strict=False):
        _set_id(item, sid)
        out.append(item)
    return out


#: 🔴🔴 **난타전을 요구하는 문턱** — 사용자 지시 2026-10-05 ④.
#
#  > 양 팀 최근 평균 득점 **합이 4 이상**이거나 **한쪽 평균 3 이상**이면
#  > **난타전(합계 4골+) 시나리오 필수**. 없으면 `scenario_incomplete`.
#
#  ⚠️ 실측 pn7: 평균이 **2.8 + 3.4 = 6.2** 였는데 난타전 시나리오가 **없었다** —
#     그래서 `언더 3.5` 가 **모든 시나리오에서 살아** 1.0 이 됐다. 🔴 그것이
#     §6-7 이 막으려는 **거짓 1.0** 이다. 🔴 수는 **여기 하나**다.
SLUGFEST_SUM = 4.0
SLUGFEST_ONE = 3.0

#: 🔴 난타전으로 **세는 합계 골** — `합계 4골+`(지시 ④의 글자 그대로).
SLUGFEST_GOALS = 4


def _slugfest_gate(res, game, ctx) -> None:
    """🔴 `ctx` 에서 팀별 평균을 꺼내 `require_slugfest` 에 넘긴다.

    ⚠️ 못 쟀으면 **그렇게 적는다**(#3) — 조용히 통과시키지 않는다.
    """
    avg = dict((ctx or {}).get("avg_goals_by_team") or {})
    if not avg:
        res.notes.append("§6-7 난타전 검사 — ⚠️ 최근 평균 득점을 **못 쟀다**"
                         "(팀별 `recent_avg_goals` 가 없다)")
        return
    keys = list(avg)
    home_avg = (avg.get(game.home) or avg.get(game.home_id)
                or (avg[keys[0]] if keys else 0.0))
    away_avg = (avg.get(game.away) or avg.get(game.away_id)
                or (avg[keys[1]] if len(keys) > 1 else 0.0))
    require_slugfest(res, game, home_avg=home_avg, away_avg=away_avg)


def slugfest_needed(*, home_avg: float, away_avg: float) -> tuple[bool, str]:
    """🔴 난타전 시나리오가 **필요한가**. `(필요, 사유)` — 지시 ④.

    ⚠️ **조용히 판단하지 않는다**(#3) — 어느 조건이 걸렸는지 적는다.
    """
    a, b = float(home_avg or 0), float(away_avg or 0)
    if a + b >= SLUGFEST_SUM:
        return True, (f"최근 평균 합 {a:g}+{b:g}={a + b:g} ≥ {SLUGFEST_SUM:g} — "
                      f"난타전 시나리오가 **필요하다**(지시 ④)")
    if max(a, b) >= SLUGFEST_ONE:
        return True, (f"한쪽 평균 {max(a, b):g} ≥ {SLUGFEST_ONE:g} — "
                      f"난타전 시나리오가 **필요하다**(지시 ④)")
    return False, (f"최근 평균 합 {a + b:g} < {SLUGFEST_SUM:g} 이고 한쪽 최대 "
                   f"{max(a, b):g} < {SLUGFEST_ONE:g} — 난타전은 필수가 아니다")


def _sum_of(score: str) -> int:
    """🔴 `"3-2"` → 5. ⚠️ 못 읽으면 **-1**(없는 것으로 세지 않는다)."""
    try:
        a, b = str(score).split("-", 1)
        return int(a) + int(b)
    except (ValueError, TypeError):
        return -1


#: 🔴 난타전 판정이 **자기 흔적을 찾는** 표식. ⚠️ 사람이 읽는 글이기도 하다 —
#   카드에 그대로 찍힌다(§6-7 조항 번호).
MARK = "§6-7"


def require_slugfest(res, game, *, home_avg: float, away_avg: float) -> bool:
    """🔴🔴 **난타전이 없으면 `incomplete`** — 지시 ④. 돌려주는 것은 *"있다"*.

    ⚠️ 이 함수는 **시나리오를 만들지 않는다** — §6-2 ②(대량득점형)와 §5-c-1
       (난타전)이 그 일을 한다. 🔴 여기는 *"그 결과가 들어왔나"* 를 **본다.**
    🔴 그래서 거짓 1.0 이 **카드로 나가는 것**을 막는다(§6-7).
    """
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **다시 불릴 수 있다** — 실측 2026-10-05 (pn10)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실사고: `generate` 안에서 한 번 돌고 끝났는데, 그 **뒤에** §3 이
    #     시나리오를 DeepSeek 것으로 **갈아 치웠다**(지시 ③). 그래서 카드가
    #     *"합계 4골 이상이 하나도 없다"* 라고 적으면서 바로 아래 `A`(3-1)를
    #     보여 줬다 — **지나간 패를 보고 판정한** 것이다.
    #  🔴 그래서 이 함수는 **자기 흔적을 걷고** 다시 센다. 표식을 문자열로
    #     달아 두고 그것으로 찾는다(목록을 따로 들지 않는다 · 사본 금지).
    res.notes[:] = [n for n in (res.notes or []) if MARK not in str(n)]
    res.incomplete_why[:] = [w for w in (res.incomplete_why or [])
                             if MARK not in str(w)]
    # 🔴 **깃발은 사유에서 자란다** — 실측 pn11: 사유를 걷었는데 깃발이 남아
    #    카드가 `scenario_incomplete` 를 **까닭 한 줄 없이** 찍었다.
    #    ⚠️ 다른 조항이 세운 깃발은 그 사유가 남아 있으니 그대로 선다.
    res.incomplete = bool(res.incomplete_why)
    need, why = slugfest_needed(home_avg=home_avg, away_avg=away_avg)
    res.notes.append(f"{MARK} 난타전 검사 — {why}")
    if not need:
        return True
    have = [d.id for d in (res.drafts or [])
            if any(_sum_of(sc) >= SLUGFEST_GOALS for sc in (d.scores or []))]
    if have:
        res.notes.append(
            f"{MARK} ✅ 합계 {SLUGFEST_GOALS}골+ 시나리오가 있다({have})")
        return True
    res.incomplete = True
    res.incomplete_why.append(
        f"{MARK} 🔴 **난타전 시나리오가 없다**(지시 ④) — {why}. 합계 "
        f"{SLUGFEST_GOALS}골 이상인 스코어가 **하나도 없다**: "
        f"{[sc for d in (res.drafts or []) for sc in d.scores][:8]} → "
        f"`언더` 마켓이 **공짜로 1.0** 을 받는다(§6-7)")
    return False


def from_deepseek(rows: list, game, *, keep: list | None = None) -> list:
    """🔴🔴 **DeepSeek 시나리오 → `Draft` 들** — 지시 ③ (2026-10-05).

    > 카드 시나리오 = **DeepSeek 시나리오**. 각 시나리오에 `driver_vars` 번호와
    > `mechanism` **문장**을 출력. 템플릿 시나리오는 **코드 필수형 보강일 때만**,
    > `added_by:code` 표시와 함께.

    ⚠️ `keep` 은 **코드 필수형 보강**이다(§6-2) — 그것은 남긴다.
    🔴 글자는 **다시 매긴다**(`A`~`H`) — DeepSeek 가 준 id 를 믿지 않는다
       (중복·빈 값이 오면 pydantic 이 터진다).
    🔴 스코어는 **`outcomes`**(`[[2,1],[1,0]]`)에서 만든다 — 지어내지 않는다.
    """
    out: list[Draft] = []
    for row in (rows or []):
        box = row if isinstance(row, dict) else {}
        scores = []
        for pair in (box.get("outcomes") or []):
            try:
                a, b = int(pair[0]), int(pair[1])
            except (TypeError, ValueError, IndexError):
                continue
            sc = f"{a}-{b}"
            if sc not in scores:
                scores.append(sc)
        if not scores:
            continue
        drivers = [str(x) for x in (box.get("driver_vars") or [])]
        out.append(Draft(
            id="A", scores=scores,
            # 🔴 세기는 **변수 hardness 합**이다(§5-a) — 모델이 안 정한다.
            #    ⚠️ 여기서는 변수 번호만 아므로 **개수**로 둔다(0 이면 바닥이
            #       걸린다 · `survive.WEIGHT_FLOOR`).
            strength=float(len(drivers)),
            template_id="deepseek",
            # 🔴 **전개 문장이 먼저**다 — 독자가 읽는 것이고, 지시 ③ 이
            #    *"`mechanism` 문장을 출력"* 이라고 적은 그 문장이다.
            #    ⚠️ 실측 pn10: 여기에 번호만 적어 카드에 **전개가 없었다**.
            why=((" ".join(str(box.get("mechanism") or "").split())
                  or "⚠️ DeepSeek 가 `mechanism` 을 안 줬다")
                 + f" · 근거 변수 {drivers or '없다'}"),
            variables=drivers, added_by="deepseek",
            mechanism=" ".join(str(box.get("mechanism") or "").split()),
            driver_vars=drivers))
    out += list(keep or [])
    if not out:
        return []
    # 🔴 글자를 다시 매긴다 — 상한 안에서(`place_required` 와 같은 규칙)
    return place_required(
        [d for d in out if d.added_by != "required"],
        [d for d in out if d.added_by == "required"], cap=MAX_SCENARIOS)


def _evict_for_required(res, hint: str) -> str | None:
    """🔴 필수형 자리를 만든다 — **일반 중 `strength` 최저**를 뺀다.

    ⚠️ 뺀 사실을 **사유로** 남긴다(#3) — 조용히 지우면 카드가 거짓이 된다.
    🔴 뺄 일반이 없으면 `None`(그때만 불완전이다).
    """
    gens = [d for d in res.drafts if getattr(d, "added_by", "") != "required"]
    if not gens:
        return None
    worst = min(gens, key=lambda d: float(getattr(d, "strength", 0.0) or 0.0))
    res.drafts.remove(worst)
    res.notes.append(
        f"§6-2 — `{hint}` 자리를 만들려고 **일반 시나리오 `{worst.id}`"
        f"(strength {getattr(worst, 'strength', 0):g})를 뺐다** — 필수형은 "
        f"항상 들어간다(결정 ① 2026-10-04 · 상한 {MAX_SCENARIOS})")
    return worst.id


@dataclass
class Draft:
    """만들어진 시나리오 하나(§3 `Scenario` 로 가기 전의 꼴).

    🔴 `types.Scenario` 로 바로 만들지 않는 이유: **사유**(`why`)와 **발동 규칙**을
       들고 다녀야 감사가 된다. §3 스키마에는 그 칸이 없다.
    """

    id: str
    scores: list[str]
    strength: float
    template_id: str
    why: str
    variables: list[str] = field(default_factory=list)
    #: 🔴 **포아송 스코어 격자의 확률 합**(사용자 지시 2026-10-02 3차).
    #
    #  딥서치: *근거 개수는 확률이 아니다* — 적정 채점 규칙은 예측 분포가 참 분포와
    #  같을 때 최적이 된다. §6-b 가 생존 1.0/0.8 로 돈을 걸라 말라를 정하므로 그 수는
    #  확률이어야 뜻을 가진다. 원본 선언은 `scenario_rules.yaml: scenario_weight`.
    #  ⚠️ **못 쟀으면 `None`** — 0 으로 때우지 않는다. 그때 §6 은 `strength` 로 돈다.
    probability: float | None = None
    #: 🔴🔴 **§6-2 — 누가 이 시나리오를 넣었나.** `""`(모른다) · `code`(보강)
    #
    #  ⚠️ 에이전트가 낸 것과 코드가 강제로 넣은 것을 **섞으면 안 된다** — 그
    #     구분이 사라지면 *"에이전트가 반대 시나리오를 생각했나"* 를 못 센다.
    #  🔴 기본값은 **빈 문자열**이다(누가 넣었는지 모른다는 뜻) — `agent` 로
    #     때우지 않는다(조용한 0 금지).
    added_by: str = ""
    #: 🔴🔴 **전개 한두 문장** — 지시 ③ (2026-10-05). DeepSeek 가 쓴다.
    #   ⚠️ 코드가 지어내지 않는다 — 템플릿 시나리오는 **빈 문자열**이고 그
    #      사실이 카드에서 보인다(`added_by` 가 `code`·`template` 이다).
    mechanism: str = ""
    #: 🔴 그 시나리오를 **움직인 변수 번호들**(`R4`·`R7`…) — 지시 ③.
    driver_vars: list = field(default_factory=list)

    def to_scenario(self):
        from app.types import Scenario
        return Scenario(id=self.id, scores=list(self.scores),
                        strength=self.strength, template_id=self.template_id,
                        variables=list(self.variables),
                        # 🔴 §5-e — 문장은 L6 이다. 비워 둔다
                        narrative="")


@dataclass
class Result:
    """§5 산출. 🔴 **못 만든 이유까지** 들고 온다."""

    drafts: list[Draft] = field(default_factory=list)
    #: 🔴 §7 R5 — 자료 부족이면 참. 그때 `drafts` 는 **비어 있다**
    insufficient: bool = False
    #: 🔴🔴 **§6-2 `scenario_incomplete`** — 세트를 다 못 만들었다. **카드 금지.**
    #
    #  ⚠️ `insufficient`(§7 R5)와 **다른 상태**다: R5 는 *"변수가 모자라 시작도
    #     못 했다"* 이고, 이쪽은 *"변수는 있는데 **반대 시나리오를 만들 수 없다**"*
    #     다. 🔴 섞으면 고칠 곳이 사라진다(§8-6).
    incomplete: bool = False
    #: 🔴 **어느 필수형이 없어서인가** — 이름으로 남긴다(#3 조용한 0 금지)
    incomplete_why: list[str] = field(default_factory=list)
    #: 왜 부족한가 · 어느 교차 규칙이 왜 발동/미발동했나 · 무엇을 못 읽었나
    notes: list[str] = field(default_factory=list)
    #: 🔴 **어느 시나리오에도 없는 결과의 확률**(사용자 지시 2026-10-02 3차).
    #
    #  ⚠️ 실측 0.329 — 3-0(0.068) 하나가 D 전체(0.090)에 가깝다. 전 판은 덮은
    #     67% 안에서만 정규화해 *"전부 따졌다"* 로 읽혔다. **그것을 낸다.**
    #  🔴 못 쟀으면 `None`(격자 없음) — 0 이면 "다 덮었다"는 거짓이 된다.
    uncovered: float | None = None
    #: 🔴 덮이지 않은 스코어를 **이름으로** — 확률 큰 것부터(조용한 0 금지)
    uncovered_scores: list[tuple[str, float]] = field(default_factory=list)
    #: 🔴🔴 **접을 마켓 종류**(§4 `attaches_to: fold_win_markets`).
    #
    #  ⚠️ 2026-10-02 까지 이 칸이 **없었다.** `event_match` 의 `attaches_to` 에
    #     `fold_win_markets` 라고 적혀 있었고 **그 이름을 읽는 코드가 없었다** —
    #     즉 "행사 경기면 승패를 접는다"는 규칙이 장식이었다.
    #  🔴 접는다 = 생존을 **세긴 하지만 결론에 이름을 적지 않는다**. 지우지 않는다 —
    #     지우면 왜 안 적었는지 알 수 없다(#3 조용한 0 금지).
    fold_markets: set[str] = field(default_factory=set)

    @property
    def total_strength(self) -> float:
        return round(sum(d.strength for d in self.drafts), 3)

    @property
    def total_probability(self) -> float | None:
        """덮은 확률 합. 🔴 한 칸이라도 못 쟀으면 `None` — 반쪽으로 세지 않는다."""
        if not self.drafts or any(d.probability is None for d in self.drafts):
            return None
        return round(sum(d.probability or 0.0 for d in self.drafts), 4)


FOLD_WIN = "fold_win_markets"
#: 🔴 접는 대상 — 승패(더블찬스 포함). ⚠️ 총점·핸디는 접지 않는다(행사 경기에서도
#   득점은 난다). 원본은 `survive.WIN_MARKETS` 이고 여기서 베끼지 않는다.


def _fold_markets(res: Result, items: list) -> None:
    """§4 `attaches_to: fold_win_markets` 를 가진 유형이 **발동했나**.

    🔴 발동 = 규칙이 그 사실을 인정했다. `Classified.why` 가 `§4 <유형>` 으로
       시작하면 규칙이 돌아 결론을 적은 것이다(미결정은 `undecided` 에 적힌다).
    ⚠️ 유형 이름을 손으로 적지 않는다 — §4 표에서 자란다(사본 금지).
    """
    from app import survive
    types = [v for v in rules.variable_types()
             if rules.attaches_to(v) == FOLD_WIN]
    for c in items:
        if c.type not in types or c.undecided:
            continue
        if not str(c.why or "").startswith(f"§4 {c.type}"):
            continue
        res.fold_markets |= set(survive.WIN_MARKETS)
        res.notes.append(
            f"§4 {c.type} 발동 → **승패 마켓을 접는다**(`{FOLD_WIN}`) — "
            f"{str(c.why)[:90]}")
        return
    if types:
        res.notes.append(
            f"`{FOLD_WIN}` 유형({', '.join(sorted(types))})이 발동하지 않았다 — "
            f"승패 마켓을 그대로 센다")


def _tpl(name: str) -> dict:
    """§5-b 템플릿 하나. 🔴 없으면 터진다 — 조용히 빈 스코어를 쓰지 않는다."""
    got = rules.templates().get(name)
    if not got:
        raise KeyError(f"§5-b 에 템플릿 {name!r} 이 없다")
    return got


#: §5-c-5 가 말하는 **2골 차**. 🔴 핸디 ±1.5 의 기준이다(§6-a).
TWO_GOAL = 2


def _margin(score: str) -> int:
    """`"3-1"` → 2. 🔴 못 읽으면 0 — 지어내지 않는다."""
    import re as _re
    m = _re.match(r"\s*(\d+)\s*-\s*(\d+)\s*$", str(score or ""))
    return abs(int(m.group(1)) - int(m.group(2))) if m else 0


def _rule_scores(rule_id: str) -> list[str]:
    """§5-c 규칙이 지정한 스코어. 🔴 **yaml 이 원본이다** — 코드에 박지 않는다."""
    got = [str(x) for x in (rules.cross_rule(rule_id).get("scores") or [])]
    if not got:
        raise ValueError(f"§5-c {rule_id} 에 `scores` 가 없다")
    return got


def _scores(name: str) -> list[str]:
    got = [str(x) for x in (_tpl(name).get("scores") or [])]
    if not got:
        raise ValueError(f"템플릿 {name!r} 의 스코어 집합이 비었다(§1)")
    return got


def generate(items: list[classify.Classified], game: classify.Game, *,
             standings: dict | None = None,
             board: list[str] | None = None) -> Result:
    """§5-a~§5-c 를 적용해 시나리오를 만든다.

    `standings` 는 순위표 사실의 `value` — 리그 평균·난타전 문턱이 거기 있다.
    `board` 는 보드에 있는 줄 이름들. 🔴 `None` 이면 **보드 없음**이고 §6-c-3 대로
    핸디 ±0.5/±1.5 만 후보가 된다(그래서 §5-c-5 가 발동한다).
    """
    res = Result()
    varis = [c for c in items if c.is_variable]
    groups: dict[str, list[classify.Classified]] = {"home": [], "away": [], "draw": []}
    for c in varis:
        groups[c.direction].append(c)
    dirs = {k: v for k, v in groups.items() if v}

    # 🔴 §7 R5 먼저 — *"부족이면 시나리오를 만들지 않는다"*(R5 계약)
    if len(varis) < MIN_VARIABLES or len(dirs) < MIN_DIRECTIONS:
        res.insufficient = True
        res.notes.append(
            f"§7 R5 자료 부족 — 방향 있는 변수 {len(varis)}개(최소 "
            f"{MIN_VARIABLES}) · 방향 {len(dirs)}종(최소 {MIN_DIRECTIONS}). "
            f"§5-c-6: STEP 3 으로 되돌려 반대 변수를 다시 찾는다")
        return res

    # 🔴 **스코어 격자를 먼저 만든다** — 5c-1 의 비교 대상이 이미 둔 시나리오의
    #    확률이고, 무게도 여기서 나온다(사용자 지시 2026-10-02 3차).
    probs = _grid(res, game, standings)

    # 🔴🔴 §4 `attaches_to: fold_win_markets` — **여기서 읽는다**
    _fold_markets(res, items)

    sports = sorted({str(t.get("sport")) for t in rules.templates().values()})
    if game.sport not in sports:
        # ══════════════════════════════════════════════════════════════
        # 🔴 §5-b 에 템플릿이 없는 종목 — **격자에서 뽑는다**(사용자 지시 2026-10-02)
        # ══════════════════════════════════════════════════════════════
        #
        #  전 판은 여기서 멈췄다(*"'hockey' 템플릿이 없다 — 지어내지 않는다"*).
        #  그것이 맞았다 — **스코어를 손으로 적으면 지어내는 것**이고, 리그가 바뀌면
        #  따라가지 않는다. 그런데 이제 **격자가 있다**: 그 종목·그 경기의 포아송
        #  분포에서 **가장 그럴듯한 스코어**를 뽑으면 손으로 적을 것이 없다.
        #  🔴 개수도 안 고른다 — v4 §5-b 축구 템플릿이 *방향마다 2개, 난타전 3개* 를
        #     쓰고 그 수를 **그 표에서 세어** 쓴다(`rules.derived_shape`).
        #  ⚠️ 격자가 없으면 여전히 **멈춘다** — 그때는 뽑을 분포가 없다.
        if not probs:
            res.insufficient = True
            res.notes.append(
                f"§5-b 에 '{game.sport}' 템플릿이 없고(있는 종목: {sports}) "
                f"확률 격자도 못 만들었다 — 시나리오를 지어내지 않는다")
            return res
        res.notes.append(
            f"§5-b 에 '{game.sport}' 템플릿이 없다 — **격자에서 뽑는다**"
            f"(방향마다 {rules.derived_shape()['direction']}개 · v4 §5-b 축구 "
            f"템플릿의 개수를 세어 쓴다)")

    _base(res, groups, game, probs)
    _fill_probability(res, probs)          # A·B·C 에 먼저 채운다 — 5c-1 이 쓴다
    _cross(res, varis, groups, game, standings, board, probs)
    _fill_probability(res, probs)          # 교차로 더 생긴 것까지
    _uncovered(res, probs)
    _single_direction_guard(res)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **§6-2 — 세트 자동 보강은 맨 마지막이다**
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 순서가 중요하다: 교차 규칙(§5-c)이 만든 것까지 **다 센 뒤에** 보강해야
    #     한다. 먼저 보강하면 5c-1 이 난타전을 만든 뒤 개수가 또 바뀐다.
    #  🔴 후보 핸디를 **여기서 지어내지 않는다** — 보드가 있으면 그 줄이고,
    #     없으면 §6-c-3 의 ±0.5·±1.5 다. 그 표가 `rules` 에 있다.
    # ⚠️ 무승부 걷기는 **`require_set` 이 앞뒤로** 한다(한 곳에 둔다) — 여기서
    #    또 부르면 같은 규칙이 두 군데 살게 된다(#1 사본 금지).
    require_set(res, game, varis, handicaps=_handicap_candidates(board),
                standings=standings)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **난타전이 없으면 카드를 막는다** — 지시 ④ (2026-10-05)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 pn7: 최근 평균 **2.8 + 3.4 = 6.2** 인데 합계 4골 이상 시나리오가
    #     **하나도 없었다** → `언더 3.5` 가 **모든 시나리오에서 살아 1.0**.
    #  🔴 여기서 시나리오를 **만들지 않는다** — §6-2 ②·§5-c-1 이 만들고, 여기는
    #     *"그 결과가 들어왔나"* 를 본다(사본 금지).
    #    ⚠️ 평균은 `standings`(= `analyze.context()` 결과)에 있다
    _slugfest_gate(res, game, standings)
    # 🔴 보강으로 생긴 것에도 확률을 채운다 — 안 채우면 그 시나리오만 `None` 이고
    #    `total_probability` 가 통째로 `None` 이 된다(반쪽으로 세지 않는다).
    _fill_probability(res, probs)
    return res


def _handicap_candidates(board: list[str] | None) -> list[float]:
    """🔴 §6-2 ④ 가 보는 **후보 핸디 줄**.

    ⚠️ 보드가 왔으면 그 줄만이다(§6-3: *"보드 캡처가 온 경기는 보드 줄만"*).
    🔴 보드가 없으면 §6-c-3 의 기준선이고, 그 수는 **`survive.OUR_HANDICAP_LINES` 가 원본이다 —
       여기서 베끼지 않는다(#1 사본 금지).
    """
    if board:
        # ⚠️ 보드 줄 이름에서 수를 읽는 일은 아직 **안 한다** — 그 파서가 없다.
        #    🔴 없는 것을 있는 척하지 않는다(#3): 빈 목록이고, 사유는 호출부가
        #       남긴다(그때 ④ 보강이 안 돈다).
        return []
    from app import survive
    return [float(x) for x in survive.OUR_HANDICAP_LINES]


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **§6-2 — 시나리오 세트 자동 보강**
# ══════════════════════════════════════════════════════════════════
#
#  > 에이전트 초안(§3-5)을 받아 **코드가 다음을 강제한다.** 하나라도 못 만들면
#  > 그 경기는 `scenario_incomplete` 로 **카드 금지.**
#
#  🔴 **왜** — §6-7: *"생존 1.0 은 **시나리오를 다 만든 뒤**에만 성립한다."*
#     ⚠️ 실측 2026-10-02: `2-0` 하나만 있는 경기에서 `언더 2.5` 가 1.0 을 받았다.
#        `2-1` 이 세트에 있으면 그 마켓은 **죽는다.**
#  🔴 표는 `config/scenario_required.yaml` 이다 — 여기 베끼지 않는다(#1).


#: 🔴🔴 **`driver_vars` 를 요구하지 않는 출처.** `added_by` 가 이 중 하나면
#  변수 없이도 시나리오로 남는다.
#
#  ══════════════════════════════════════════════════════════════════
#  🔴 **§6-2 와 §5-c-5 가 충돌한다 — 실측이 그 충돌을 드러냈다**
#  ══════════════════════════════════════════════════════════════════
#
#  §6-2: *"각각 `driver_vars`·`mechanism`·`outcomes` 가 **비면 무효**."*
#  §5-c-5: *"상대가 2골 차로 이기는 시나리오를 반드시 하나 만든다. **근거 변수가
#           없어도 없애지 않는다**(floor)."*
#
#  ⚠️ 처음에 §6-2 를 그대로 걸었더니 **5c-5 가 세운 2골 차 시나리오가 지워졌다**
#     (실측 2026-10-04: `테스트 2골 차 시나리오가 없다`). 🔴 그 시나리오가 바로
#     핸디 ±1.5 를 **죽이는 자리**다 — 지우면 §6-2 가 막으려던 거짓 1.0 이
#     오히려 **생긴다.**
#
#  🔴 그래서 §6-2 의 그 문장은 **에이전트 초안**을 가리킨다고 읽는다 — 그 조항
#     첫 문장이 *"에이전트 초안(§3-5)을 받아 코드가 다음을 강제한다"* 다.
#     규칙·템플릿이 **일부러** 변수 없이 세운 바닥 시나리오는 그 대상이 아니다.
#  ⚠️ `""`(출처 모름)은 **요구한다** — fail-closed. 모르는 것을 봐 주면
#     에이전트 초안이 그 틈으로 들어온다.
#   🔴 `required` 는 **결정 ① 이 생긴 이름**이다(2026-10-04) — §6-2 보강에
#      붙는다. ⚠️ 종전에는 그것도 `code` 였고 **면제였다**: 이름만 갈렸으므로
#      면제도 따라가야 한다(안 그러면 보강이 조용히 `driver_vars` 바닥에 걸린다).
FLOOR_ORIGINS = ("template", "code", "required")


def draft_valid(d: Draft) -> tuple[bool, str]:
    """🔴 §6-2 — *"각각 `driver_vars`·`mechanism`·`outcomes` 가 비면 무효."*

    ⚠️ 지시문의 이름과 우리 칸 이름이 다르다 — 그 대응은 **yaml** 이 들고 있다
       (`rules.required_fields`). 🔴 이름이 다르다고 검사를 빼지 않는다.
    🔴 `driver_vars` 만 **출처에 따라 면제**된다(위 `FLOOR_ORIGINS`) —
       `mechanism`·`outcomes` 는 **누가 넣었든** 있어야 한다(까닭 없는 시나리오와
       스코어 없는 시나리오는 어느 출처에서도 쓸 수 없다).
    """
    origin = str(d.added_by or "")
    exempt = origin in FLOOR_ORIGINS or origin.startswith("rule:")
    for said, ours in rules.required_fields().items():
        got = getattr(d, ours, None)
        if got:
            continue
        if said == "driver_vars" and exempt:
            continue
        return False, (f"§6-2 — `{said}`(우리 칸 `{ours}`)가 비었다. "
                       f"시나리오 `{d.id}` 는 무효다(출처 `{origin or '미상'}`)")
    return True, ""


def _margin_of(score: str) -> int:
    h, a = _goals_pair(score)
    return abs(h - a)


def _goals_pair(score: str) -> tuple[int, int]:
    """🔴 `"2-1"` → `(2, 1)`. 못 읽으면 `(0, 0)` 이 아니라 **터진다**."""
    parts = str(score or "").split("-")
    if len(parts) != 2:
        raise ValueError(f"스코어 꼴이 아니다: {score!r}")
    return int(parts[0]), int(parts[1])


def _conceding_scores(scores: list[str]) -> list[str]:
    """🔴 §6-2 ① — *"이긴 쪽 점수 유지 · 실점 1"*(`2-0` → `2-1`).

    ⚠️ **스코어를 지어내지 않는다** — 이미 있는 시나리오의 이긴 쪽 점수를 그대로
       쓰고 실점만 1 로 올린다. 그 산수가 전부다.
    🔴 이미 실점이 있는 스코어(`2-1`)는 **그대로 둔다** — 보강할 것이 없다.

    ══════════════════════════════════════════════════════════════════
    🔴 **1점 차 승리에서는 실점을 동반할 수 없다**(실측 2026-10-04)
    ══════════════════════════════════════════════════════════════════

    처음에 `0-1` 을 `1-1` 로 바꿨다 — 🔴 그것은 **무승부**다. *"우세팀이 이기면서
    한 점을 준다"* 가 아니라 **이기지 못하는** 스코어가 된다.
    ⚠️ NHL(무승부 없음) 계약이 그 `1-1` 을 잡아냈다 — 안 잡혔으면 카드가
       **일어날 수 없는 결과**를 필수형이라고 적었다.
    🔴 그래서 **이긴 쪽이 2점 이상**일 때만 만든다.
    """
    out: list[str] = []
    for sc in scores:
        try:
            h, a = _goals_pair(sc)
        except ValueError:
            continue
        # 🔴 이긴 쪽이 **2점 이상**이어야 1점을 주고도 이긴다
        if h > a and a == 0 and h >= 2:
            out.append(f"{h}-1")
        elif a > h and h == 0 and a >= 2:
            out.append(f"1-{a}")
    return out


def _has_form(res: Result, word: str) -> bool:
    """그 필수형이 **이미 세트에 있나**. 🔴 id 에 그 이름이 적혀 있다."""
    return any(word in d.id for d in res.drafts)


def _add(res: Result, *, claim, hint: str, scores: list[str], why: str,
         variables: list[str], template_id: str = "code",
         game: classify.Game | None = None) -> bool:
    """🔴 코드가 넣는다 — **`added_by="required"` 로 표시**한다(§6-2).

    ⚠️ 종전 표시는 `"code"` 였다. 🔴 **결정 ①**(2026-10-04)이 *"필수형은 항상
       들어간다 · 넘치면 **일반** 중 strength 최저를 뺀다"* 를 요구하므로,
       필수형과 일반을 **이름으로 가를 수 있어야** 한다.

    ⚠️ 스코어가 비면 **넣지 않는다**(지어낸 시나리오가 된다) — 그 사실을 사유로.
    🔴 id 는 **글자**다(`A`~`E`) — 설명은 `why` 에 들어간다(§1 · `types.ScenarioId`).
       ⚠️ 실측 2026-10-04: 설명을 id 에 넣었더니 `MarketSurvival` 이 터졌다.
    """
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **보강이 무승부를 다시 넣지 못하게** — 관문은 **여기 하나**다
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-04(돌연변이 E): `0-1`(1점 차 승)에서 X-1 을 만들면
    #     `1-1` 이 나온다 — **무승부**다. 1점 차 승에서는 실점을 동반할 수 없고,
    #     NHL 은 무승부가 **일어날 수 없다.**
    #  🔴 산수는 `_conceding_scores` 가 고쳤다(`h >= 2`). 그래도 **보강은 네
    #     가지**이고 앞으로 더 생긴다 — 그래서 **모든 보강이 지나는 자리**에
    #     관문을 둔다. ⚠️ `require_set` 뒤에 한 번 더 걷는 식으로 두면 그 호출이
    #     **무엇도 막지 않는 방어**가 된다(돌연변이 L 이 통과했다).
    if game is not None and rules.draw_possible(game.league)[0] is False:
        ties = [sc for sc in scores
                if len(str(sc).split("-")) == 2
                and str(sc).split("-")[0] == str(sc).split("-")[1]]
        if ties:
            scores = [sc for sc in scores if sc not in ties]
            res.notes.append(
                f"§6-2 — `{hint}` 의 무승부 스코어 {ties} 를 **걷었다**"
                f"(`{game.league}` 는 무승부가 없다)")
    if not scores:
        res.notes.append(f"§6-2 — `{hint}` 를 넣을 스코어가 없다. 만들지 않는다")
        return False
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **필수형은 자리를 묻지 않는다** — 사용자 결정 ① (2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 필수형은 빈자리가 없으면 넣지 못하는 게 아니라 **항상 들어간다** —
    #  > 일반 시나리오가 8개를 넘을 때만 **strength 최저인 일반 시나리오**를 뺀다.
    #
    #  ⚠️ 종전엔 `claim` 이 `None` 을 주면 *"글자가 없다"* 로 **포기**했다.
    #     🔴 그래서 대량득점형·난타전이 영영 안 섰다(정답지 재현 2/3 실패).
    sid = claim(hint)
    if sid is None:
        # 🔴 **자리를 비운다** — 일반 중 `strength` 최저를 뺀다(필수형은 안 뺀다)
        sid = _evict_for_required(res, hint)
    if sid is None:
        # 🔴 뺄 **일반이 하나도 없다**(전부 필수형이다) — 그때만 불완전이다
        res.incomplete_why.append(
            f"§6-2 — `{hint}` 를 넣을 자리가 없다(**전부 필수형**이라 뺄 일반 "
            f"시나리오가 없다 · 상한 {MAX_SCENARIOS})")
        res.incomplete = True
        return False
    res.drafts.append(Draft(
        id=sid, scores=list(dict.fromkeys(scores)), strength=0.0,
        template_id=template_id, why=f"{hint} — {why}",
        variables=list(variables), added_by="required"))
    res.notes.append(f"§6-2 보강 — `{sid}`({hint}) 를 **코드가** 넣었다")
    return True


def require_set(res: Result, game: classify.Game, varis: list,
                *, handicaps: list[float] | None = None,
                standings: dict | None = None) -> None:
    """🔴🔴 **§6-2 전부.** 보강하고, 못 하면 `incomplete` 를 세운다.

    ══════════════════════════════════════════════════════════════════
    🔴 **표 여섯 줄 중 둘은 이미 §5-c 가 한다** — 사본을 만들지 않는다
    ══════════════════════════════════════════════════════════════════

    | §6-2 | 어디서 하나 |
    |---|---|
    | ① 우세팀 실점 동반형 (X-1) | 🔴 **여기** — §5-c 에 없다 |
    | ② 대량득점형 | 🔴 **§5-c-2** 다(`_c2_rout`). 종전에 조건을 못 읽어 |
    |              | **한 번도 발동하지 못했다** — §6-2 의 네 방아쇠가 그 고침이다 |
    | ③ 회귀 반전형 | 🔴 **여기** — §5-c 에 없다 |
    | ④ 핸디 ±N.5 대응형 | ✅ **§5-c-5** 가 이미 한다(`_c5_two_goal`) |
    | ⑤ 반대 방향 | ✅ **§5-c-6**(`_single_direction_guard`)가 만들고 |
    |             | 🔴 여기서 **`incomplete` 로 올린다**(§6-2 는 *실패*라 했다) |
    | ⑥ 양방향 변수 | 🔴 **여기** — 어디에도 없었다 |

    ⚠️ `handicaps` 는 **④ 를 위해 받지 않는다**(5c-5 가 보드를 직접 본다) —
       계약이 *"④ 가 어디서 되나"* 를 묻기 위한 자리다.
    """
    forms = rules.required_forms()
    # 🔴 `Classified` 의 칸은 **`type`** 이다(`vtype`·`name` 이라는 칸은 없다).
    #    ⚠️ `Draft.variables` 에 들어가는 열쇠도 그 유형 이름이다
    #       (`_base` 가 `variables=[c.type …]` 로 적는다) — 새 열쇠를 만들지 않는다.
    types = {str(getattr(v, "type", "") or "") for v in varis}
    all_vars = sorted(types - {""})
    # 🔴 **보강 전에** 걷는다 — 걷지 않으면 회귀 지속형이 그 무승부를 **복사한다**
    drop_impossible_draws(res, game)
    claim = _claimer(res)

    # 🔴🔴 **결정 ⑦ — 야구 템플릿 셋을 먼저 채운다**(2026-10-04)
    #    ⚠️ ①~⑥ 보강보다 **앞**이다: 야구가 둘뿐이라 `markets_graded 0` 이 된
    #       자리가 여기다(실측 2026-10-04 밀워키 vs 샌디에이고).
    baseball_templates(res, game, varis)

    # ── ① 우세팀 실점 동반형 (X-1) — **항상**
    row = forms["우세팀_실점_동반형"]
    win = [d for d in res.drafts
           if any(_margin_of(sc) > 0 for sc in d.scores if "-" in sc)]
    got = _conceding_scores([sc for d in win for sc in d.scores])
    have = {sc for d in res.drafts for sc in d.scores}
    got = [sc for sc in got if sc not in have]
    if win and got:
        _add(res, claim=claim, hint="X-1(우세팀 실점 동반)", scores=got, game=game,
             why=("§6-2 ① 우세팀 실점 동반 — 우세팀이 이기면서 한 점을 준다. "
                  "🔴 그 꼴이 없으면 `언더`·`클린시트` 가 죽을 자리가 없어 "
                  "공짜로 1.0 을 받는다(§6-7)"),
             variables=sorted({v for d in win for v in d.variables}))
    elif win:
        res.notes.append(
            "§6-2 ① — 실점 동반 스코어가 **이미 세트에 있다**(보강 없음)")

    # ── ② 대량득점형 — 🔴 **§5-c-2 를 되살린다**(사본을 만들지 않는다)
    row = forms["대량득점형"]
    hit = _blowout_trigger(res, game, varis, row, standings)
    th = (row.get("thresholds") or {}).get(str(game.sport))
    if hit and th:
        got = _blowout_scores(res, game, row)
        got = [sc for sc in got if sc not in have]
        if got:
            _add(res, claim=claim, hint="대량득점형", scores=got, game=game,
                 why=f"§6-2 ② (= §5-c-2 대량 득점) — {hit}",
                 variables=all_vars)

    # ── ③ 회귀 반전형 — **둘 다**
    row = forms["회귀_반전형"]
    reg = [t for t in (row.get("types") or []) if str(t) in types]
    if reg:
        base = [sc for d in res.drafts for sc in d.scores]
        for which in (row.get("both") or []):
            tag = f"회귀 {which}"
            if any(tag in str(d.why) for d in res.drafts):
                continue
            # 🔴 반전형은 **뒤집은 스코어**(지속형은 그대로) — 그 산수가 전부다
            want = list(base) if str(which) == "지속형" else _mirror(base)
            want = [sc for sc in want if sc not in have]
            if not want:
                res.notes.append(
                    f"§6-2 ③ {tag} — 넣을 **새 스코어가 없다**(세트가 이미 "
                    f"그 꼴을 덮는다)")
                continue
            _add(res, claim=claim, hint=tag, scores=want, game=game,
                 why=(f"§6-2 ③ {tag} — `{reg[0]}` 변수가 있다. 🔴 회귀는 어느 "
                      f"방향인지 말하지 않으므로 **둘 다** 넣는다"),
                 variables=[reg[0]])

    # ── ④ 핸디 ±N.5 대응형 — ✅ **§5-c-5 가 한다.** 여기서 또 만들지 않는다.
    row = forms["핸디_대응형"]
    res.notes.append(
        f"§6-2 ④ 핸디 대응형 — **§5-c-5 가 만든다**(후보 핸디 "
        f"{[f'{x:g}' for x in (handicaps or [])] or '보드 줄'}). "
        f"🔴 여기서 다시 만들지 않는다(사본 금지)")

    # ── ⑤ 반대 방향 — §6-2 는 **실패**라고 했다(§5-c-6 은 사유만 남겼다)
    row = forms["반대_방향"]
    dirs = {str(getattr(v, "direction", "") or "") for v in varis} - {""}
    if len(dirs) < MIN_DIRECTIONS:
        res.incomplete = True
        res.incomplete_why.append(
            f"§6-2 ⑤ 반대 방향 — 변수 방향이 {sorted(dirs) or '없음'} 뿐이다. "
            f"🔴 반대 시나리오는 **지어낼 수 없다**(§5-c-6: STEP 3 으로 되돌려 "
            f"반대 변수를 다시 찾는다)")

    # ── ⑥ 양방향 변수 — **두 시나리오에 모두** 부착(못 하면 실패)
    row = forms["양방향_변수"]
    for t in (row.get("types") or []):
        key = str(t)
        if key not in types:
            continue
        where = [d for d in res.drafts if key in d.variables]
        if len(where) >= 2:
            continue
        # 🔴 **방향이 다른 두 시나리오**에 붙인다 — 양방향이 뜻하는 것이 그것이다
        by_dir: dict[int, Draft] = {}
        for d in res.drafts:
            for sc in d.scores:
                try:
                    h, a = _goals_pair(sc)
                except ValueError:
                    continue
                by_dir.setdefault((h > a) - (h < a), d)
                break
        picked = list(by_dir.values())[:2]
        if len(picked) < 2:
            res.incomplete = True
            res.incomplete_why.append(
                f"§6-2 ⑥ 양방향 변수 `{key}` — 붙일 **방향이 다른 두 시나리오**가 "
                f"없다. 🔴 한쪽에만 붙이면 그것이 한 방향 근거가 된다")
            continue
        for d in picked:
            if key not in d.variables:
                d.variables.append(key)
        res.notes.append(
            f"§6-2 ⑥ — 양방향 변수 `{key}` 를 **두 시나리오**에 붙였다"
            f"({', '.join(d.id for d in picked)})")

    # ── 🔴 무효 시나리오를 **이름으로** 떨어뜨린다
    kept = []
    for d in res.drafts:
        ok, why = draft_valid(d)
        if ok:
            kept.append(d)
        else:
            res.notes.append(f"§6-2 무효 — {why}")
            res.incomplete_why.append(why)
    res.drafts = kept

    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **상한 8 을 여기서 건다** — 사용자 결정 ① (2026-10-04)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `_evict_for_required` 는 **보강이 자리를 못 얻을 때** 하나씩 비운다.
    #     🔴 그것만으로는 **들어온 뒤 늘어난 경우**(교차 규칙·양방향 보강이
    #     글자를 다 쓴 뒤)를 못 막는다 — 그래서 **마지막에 한 번 더** 건다.
    #  🔴 필수형은 **절대 안 뺀다**. 넘치면 일반 중 `strength` 최저가 나간다.
    if len(res.drafts) > MAX_SCENARIOS:
        before = [d.id for d in res.drafts]
        need = [d for d in res.drafts if getattr(d, "added_by", "") == "required"]
        gen = [d for d in res.drafts if getattr(d, "added_by", "") != "required"]
        res.drafts = place_required(gen, need, cap=MAX_SCENARIOS)
        gone = sorted(set(before) - {d.id for d in res.drafts})
        res.notes.append(
            f"§6-2 — 시나리오가 **상한 {MAX_SCENARIOS}개를 넘었다**"
            f"({len(before)}개) → 일반 중 `strength` 최저를 뺐다. "
            f"필수형 {len(need)}개는 **그대로**다(결정 ① 2026-10-04)"
            + (f" · 글자 재배치로 사라진 id: {gone}" if gone else ""))

    # ── 🔴 최소 개수
    if len(res.drafts) < MIN_SCENARIOS:
        res.incomplete = True
        res.incomplete_why.append(
            f"§6-2 — 시나리오 {len(res.drafts)}개로 **최소 {MIN_SCENARIOS}개**에 "
            f"못 미친다. 🔴 적게 만들면 생존이 **공짜로** 1.0 이 된다(§6-7)")
    if res.incomplete:
        res.notes.append(
            "🔴🔴 **`scenario_incomplete` — 카드 금지**(§6-2): "
            + " · ".join(res.incomplete_why))


def _blowout_trigger(res: Result, game: classify.Game, varis: list,
                     row: dict, standings: dict | None) -> str:
    """🔴🔴 **§6-2 ② 의 네 방아쇠** 중 무엇이 걸렸나(안 걸리면 `""`).

    ══════════════════════════════════════════════════════════════════
    🔴 이것이 **죽어 있던 §5-c-2 의 고침**이다
    ══════════════════════════════════════════════════════════════════

    §5-c-2(대량 득점 생성)의 조건은 *"`strength_gap` ≥ 2단계이고 강팀이 주력
    기용(`lineup_intent` 총력 …)"* 이었고, 그 두 유형이 **둘 다 미구현**이라
    `_c2_rout` 은 *"조건을 읽을 수 없다 — 발동하지 않는다"* 만 적고 있었다.
    🔴 **한 번도 발동한 적이 없다**(09-29 르방컵이 그 규칙 부재였다).

    §6-2 ② 가 **읽을 수 있는 네 방아쇠**를 줬다:

        ① 약팀 수비 결장 2명+        ← `absence` 변수 개수
        ② 랭킹 차 50+                ← 순위표
        ③ 직전 대패(0-3 이상)        ← 폼(최근 경기 스코어)
        ④ 양 팀 연속 득점 폼         ← 폼

    ⚠️ 못 잰 방아쇠는 **이름으로 남긴다**(#3) — *"조건이 없다"* 와 *"조건을 못
       쟀다"* 는 다른 말이고 고칠 곳이 다르다.
    """
    tg = row.get("triggers") or {}
    unmeasured: list[str] = []

    # ── ① 약팀 수비 결장 2명+
    need = int(tg.get("absence_count") or 0)
    out = [v for v in varis if str(getattr(v, "type", "")) == "absence"]
    if need and len(out) >= need:
        return f"약팀 수비 결장 {len(out)}명(문턱 {need})"

    # ── ② 랭킹 차 50+
    gap_need = tg.get("rank_gap")
    if gap_need is not None:
        gap = _rank_gap(standings, game)
        if gap is None:
            unmeasured.append("rank_gap(순위표에 순위가 없다)")
        elif gap >= int(gap_need):
            return f"랭킹 차 {gap}(문턱 {gap_need})"

    # ── ③ 직전 대패(0-3 이상) · ④ 양 팀 연속 득점 폼
    #  🔴 재료는 **폼 변수**다. `classify` 가 `recent_pattern` 에 최근 스코어를
    #     넣지 않으므로(폼 글자만 있다) **지금은 못 잰다.** 그 사실을 적는다.
    #  ⚠️ 0 으로 때우지 않는다 — 그러면 *"조건이 안 걸렸다"* 로 읽힌다.
    for key in ("last_loss_margin", "both_scoring_streak"):
        if key in tg:
            unmeasured.append(f"{key}(폼 변수에 스코어가 없다)")

    if unmeasured:
        res.notes.append(
            f"§6-2 ② 대량득점형 — 방아쇠 {unmeasured} 를 **못 쟀다**. "
            f"🔴 0 으로 때우지 않는다(조용한 0 금지)")
    return ""


def _rank_gap(standings: dict | None, game: classify.Game) -> int | None:
    """🔴 두 팀 **순위 차**. 못 읽으면 `None` — 0 으로 때우지 않는다.

    ⚠️ 순위표 꼴은 종목마다 다르다 — `classify` 가 쓰는 길을 그대로 쓴다
       (`rows` 안의 `team`·`rank`). 🔴 새 파서를 짓지 않는다(#1).
    """
    rows = (standings or {}).get("rows") or []
    got: dict[str, int] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        team = str(r.get("team") or "")
        rank = r.get("rank")
        if team and isinstance(rank, int):
            got[team] = rank
    h, a = got.get(game.home), got.get(game.away)
    if h is None or a is None:
        return None
    return abs(h - a)


def _blowout_scores(res: Result, game: classify.Game, row: dict) -> list[str]:
    """🔴 §6-2 ② — 그 종목의 **대량 문턱**을 넘는 스코어.

    ⚠️ 종목이 표에 없으면 **만들지 않는다**(하키는 §6-2 가 말하지 않았다).
    """
    th = (row.get("thresholds") or {}).get(str(game.sport))
    if not th:
        res.notes.append(
            f"§6-2 ② — `{game.sport}` 의 대량 문턱이 표에 없다. 만들지 않는다")
        return []
    n = int(th)
    # 🔴 **합이 문턱 이상**인 가장 가까운 꼴 둘. ⚠️ 지어내는 것이 아니라 산수다
    return [f"{n - 1}-1", f"{n - 2}-2"] if n >= 4 else []


def _grid(res: Result, game: classify.Game, standings: dict | None) -> dict | None:
    """포아송 스코어 격자. 🔴 **못 만들면 사유를 남긴다** — 조용히 빠지면 §6 이
    `strength` 로 돌고 있다는 것을 아무도 모른다."""
    avgs = (standings or {}).get("venue_averages")
    hr = _venue_row(standings, "home", game.home)
    ar = _venue_row(standings, "away", game.away)
    # 🔴🔴 **선발 보정을 넘긴다**(딥서치 2026-10-03 · A) — `analyze.grid` 와 **같은
    #    입력**이어야 한다. 한쪽만 보정하면 카드의 λ 와 시나리오의 λ 가 갈린다.
    exp = league.expected_goals(
        hr or {}, ar or {}, avgs,
        starters=classify.starters_for(standings, game)) if avgs else None
    got = league.score_probabilities(
        (exp or {}).get("home"), (exp or {}).get("away"))
    # 🔴 보정이 걸렸나·왜 안 걸렸나를 **카드에 적는다**(조용한 0 금지)
    for why in ((exp or {}).get("starter_notes") or []):
        res.notes.append(f"§5-c-1 ① 선발 보정 — {why}")
    if got is None:
        # 🔴 **대타가 무엇인지 yaml 이 말한다** — 코드가 혼자 정하지 않는다
        cfg = rules.scenario_weight()
        res.notes.append(
            f"확률 격자를 못 만들었다 — 홈/원정 쪼갠 표가 없다. 무게는 "
            f"{cfg['fallback']}")
    return got


def attach_probability(res: Result, game, ctx) -> None:
    """🔴 **격자를 (다시) 붙인다** — 시나리오를 갈아 치운 뒤에 쓴다.

    ⚠️ `_grid` 는 `res.notes` 에 격자 사유를 적는다 — 두 번 적히지 않게
       **그 사이에 새로 붙은 줄을 걷는다**(첫 판의 사유가 이미 있다).
    🔴 못 만들면 **아무것도 안 붙인다** — 0 으로 때우지 않는다(#3).
    """
    before = len(res.notes or [])
    probs = _grid(res, game, ctx)
    if probs is None:
        # ⚠️ 격자가 없으면 `_grid` 가 그 까닭을 적었다 — 그대로 둔다
        return
    del res.notes[before:]      # 🔴 같은 사유를 두 번 적지 않는다
    _fill_probability(res, probs)


def _fill_probability(res: Result, probs: dict | None) -> None:
    """🔴 무게 = 스코어 집합의 확률 합. 격자가 없으면 칸은 `None` 으로 남는다."""
    for d in res.drafts:
        if d.probability is None:
            d.probability = league.scores_mass(probs, d.scores)


def _uncovered(res: Result, probs: dict | None) -> None:
    """🔴 **어느 시나리오에도 없는 결과**를 수와 이름으로 낸다.

    ⚠️ 실측 0.329. 가장 큰 누락이 `3-0`(0.068)이고 §5-b 의 `soccer_home_dominant`
       가 그것을 들고 있는데 **생성되지 않는다**. `3-1`(0.063)은 §5-b 에 템플릿이
       아예 없다 — 지어내지 않고 이름으로 남긴다.
    """
    if not probs:
        return
    taken = {s for d in res.drafts for s in d.scores}
    rest = [(k, v) for k, v in (probs.get("scores") or {}).items()
            if k not in taken]
    rest.sort(key=lambda kv: -kv[1])
    res.uncovered = round(sum(v for _, v in rest) + float(probs.get("tail") or 0.0), 4)
    res.uncovered_scores = [(k, round(v, 4)) for k, v in rest[:6]]
    if res.uncovered:
        res.notes.append(
            f"어느 시나리오에도 없는 결과 {res.uncovered} — "
            f"{' · '.join(f'{k} {v}' for k, v in res.uncovered_scores)}"
            f"(격자 밖 꼬리 {probs.get('tail')})")


# ══════════════════════════════════════════════════════════════════
# §5-a 기본 생성 + §5-b 스코어
# ══════════════════════════════════════════════════════════════════


def _derived_set(res: Result, game: classify.Game, probs: dict | None,
                 side: str) -> list[str]:
    """§5-b 에 템플릿이 없을 때 **격자에서 뽑은** 스코어 집합."""
    n = rules.derived_shape()
    k = n["open"] if str(side).startswith("open:") else n["direction"]
    got = league.top_scores(probs, side, k)
    if not got:
        res.notes.append(f"파생 스코어({side})를 못 뽑았다 — 격자가 없거나 비었다")
    return got


def _mirror(scores: list[str]) -> list[str]:
    """🔴 스코어를 **뒤집는다**(`3-1` → `1-3`).

    ⚠️ 지어낸 방법이 아니다 — §5-b 의 축구 쌍이 **서로 거울상**이다
       (`soccer_home_normal` 2-1·1-0 ↔ `soccer_away_normal` 1-2·0-1).
       그래서 원정 템플릿이 없는 종목은 홈 템플릿을 뒤집어 쓴다.
    """
    out = []
    for sc in scores:
        got = _margin  # noqa: F841 — 아래에서 숫자로 다시 읽는다
        import re as _re
        m = _re.match(r"\s*(\d+)\s*-\s*(\d+)\s*$", str(sc))
        out.append(f"{m.group(2)}-{m.group(1)}" if m else str(sc))
    return out


def _tpl_or_derived(res: Result, game: classify.Game, probs: dict | None,
                    tpl: str, side: str) -> tuple[list[str], str]:
    """§5-b 템플릿이 그 종목에 있으면 그것, 없으면 **격자에서**.

    🔴 `template_id` 를 바꿔 돌려준다 — 카드·DB 가 *"어디서 온 스코어인가"* 를
       들고 있어야 감사가 된다.
    """
    have = {str(t.get("sport")) for t in rules.templates().values()}
    # 🔴🔴 **그 종목에 그 방향 선언이 없으면 격자로 내려간다**(실측 2026-10-02).
    #    ⚠️ 종전에는 "그 종목에 §5-b 템플릿이 **하나라도** 있으면" 템플릿 경로로
    #       갔다. 야구는 `baseball_ace_low` 가 있으므로 그 문을 통과했고, 그래서
    #       난타전에 **축구 스코어**가 들어갔다. 선언이 `null` 이면 격자가 답이다.
    if game.sport in have and tpl:
        if tpl == "mirror":
            # 🔴 홈 템플릿을 뒤집는다 — v4 축구 쌍이 그 방법이다
            home_tpl = rules.direction_templates(game.sport).get("home")
            if not home_tpl:
                res.notes.append(
                    f"{side}: `mirror` 인데 홈 템플릿 선언이 없다 — 만들지 않는다")
                return [], "mirror:없음"
            return _mirror(_scores(home_tpl)), f"mirror:{home_tpl}"
        if not tpl:
            res.notes.append(f"{side}: §5-b 에 그 방향 템플릿이 없다 — 만들지 않는다")
            return [], "없음"
        return _scores(tpl), tpl
    return _derived_set(res, game, probs, side), f"derived:{side}"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **야구 네 템플릿** — 사용자 결정 ⑦ (2026-10-04)
# ══════════════════════════════════════════════════════════════════
#
# > v5 §6-2의 **최소 4개는 야구에도 적용**한다. v4 템플릿(**에이스 저득점·불펜
# > 데이·난타전·전날 재현**)이 있으니 **코드 보강으로 채우고**, 2개만 나오면
# > `scenario_incomplete`. — 사용자 결정 ⑦
#
# ⚠️ 실측 2026-10-04(밀워키 vs 샌디에이고): 변수 5개가 섰는데 시나리오가 **둘**
#    이라 `markets_graded 0` 이었다 — `baseball_ace_low` 한 쌍만 섰다.
# 🔴 나머지 셋은 **조건을 읽는 코드가 없어서** 안 섰다(yaml 주석이 *"둘 다
#    미구현"* 이라 적었지만 그 유형들은 **지금 구현돼 있다**).


def _said(varis: list, types: tuple[str, ...]) -> list:
    """🔴 그 유형의 변수들. ⚠️ 없으면 **빈 목록**(0 이 아니라 *"못 쟀다"* 다)."""
    return [v for v in (varis or [])
            if str(getattr(v, "type", "") or "") in types]


def bullpen_day(varis: list) -> tuple[bool, str]:
    """🔴 `baseball_bullpen_day` 조건 — *"한쪽 pitcher_state 가 불펜 데이/첫
    선발/이틀 휴식"*(§5-b 선언).

    ⚠️ 낱말을 **여기 적지 않는다** — `variable_types.yaml` 의 `pitcher_state`
       가 `불펜\s*데이|bullpen day` 를 **이미** 정규식으로 들고 있다.
    🔴 못 읽으면 `(False, 사유)` 다 — 추측으로 세우지 않는다(#4).
    """
    got = _said(varis, ("pitcher_state",))
    if not got:
        return False, "`pitcher_state` 변수가 없다 — 불펜 데이를 **못 쟀다**"
    import re as _re
    pats = (rules.variable_types().get("pitcher_state") or {}).get("match") or []
    want = [p for p in pats if "불펜" in str(p) or "bullpen" in str(p)]
    for v in got:
        text = " ".join(str(x) for x in (
            getattr(v, "quote", ""), getattr(v, "claim", ""),
            getattr(v, "why", "")) if x)
        for p in want:
            try:
                if _re.search(str(p), text, _re.I):
                    return True, (f"`pitcher_state` 가 **불펜 데이**를 말한다"
                                  f"({text[:40]}…)")
            except _re.error:                           # pragma: no cover
                continue
    return False, "`pitcher_state` 가 불펜 데이를 말하지 않는다"


def repeat_yesterday(varis: list) -> tuple[bool, str]:
    """🔴 `baseball_repeat_yesterday` 조건 — *"전날 같은 팀이 같은 패턴으로 짐"*.

    ⚠️ 스코어가 **고정이 아니다**(`reuse_yesterday: true`) — 전날 스코어를
       쓴다. 🔴 그 수가 변수에 없으면 **세우지 않는다**(지어내지 않는다).
    """
    got = _said(varis, ("recent_pattern",))
    if not got:
        return False, "`recent_pattern` 변수가 없다 — 전날 재현을 **못 쟀다**"
    import re as _re
    for v in got:
        text = " ".join(str(x) for x in (
            getattr(v, "quote", ""), getattr(v, "claim", "")) if x)
        m = _re.search(r"\b(\d{1,2})\s*[-:]\s*(\d{1,2})\b", text)
        if m:
            return True, f"`recent_pattern` 이 전날 스코어 `{m.group(0)}` 를 든다"
    return False, ("`recent_pattern` 에 **전날 스코어**가 없다 — 재사용할 수가 "
                   "없다(지어내지 않는다)")


def baseball_templates(res: Result, game: classify.Game, varis: list,
                       probs: dict | None = None) -> int:
    """🔴🔴 **야구 템플릿 셋을 더 세운다** — 결정 ⑦. 돌려주는 것은 **더한 수**.

    `baseball_ace_low` 는 `_base` 가 이미 쌍으로 세운다. 여기서 채우는 것은:

        baseball_bullpen_day       한쪽이 불펜 데이 → **그 상대가 이긴다**
        baseball_slugfest          양 선발 약 + 타자 구장 → 난타전
        baseball_repeat_yesterday  전날 스코어 재사용

    ⚠️ **조건을 못 읽으면 안 세운다** — 사유를 `notes` 에 남긴다(#3). 🔴 그래야
       *"야구는 둘뿐"* 이 **왜** 인지 카드에 남는다.
    """
    if str(game.sport) != "baseball":
        return 0
    claim = _claimer(res)
    tpls = rules.templates()
    n = 0
    for name, cond in (("baseball_bullpen_day", bullpen_day),
                       ("baseball_repeat_yesterday", repeat_yesterday)):
        row = tpls.get(name) or {}
        ok, why = cond(varis)
        if not ok:
            res.notes.append(f"§6-2 ⑦ `{name}` 안 세웠다 — {why}")
            continue
        scores = [str(x) for x in (row.get("scores") or [])]
        if not scores and row.get("reuse_yesterday"):
            # 🔴 전날 스코어를 **변수에서** 꺼낸다(고정 스코어가 없다)
            import re as _re
            found = []
            for v in _said(varis, ("recent_pattern",)):
                text = " ".join(str(x) for x in (
                    getattr(v, "quote", ""), getattr(v, "claim", "")) if x)
                for m in _re.finditer(r"\b(\d{1,2})\s*[-:]\s*(\d{1,2})\b",
                                      text):
                    sc = f"{m.group(1)}-{m.group(2)}"
                    if sc not in found:
                        found.append(sc)
            scores = found[:2]
        have = {sc for d in res.drafts for sc in d.scores}
        scores = [sc for sc in scores if sc not in have]
        if not scores:
            res.notes.append(
                f"§6-2 ⑦ `{name}` 안 세웠다 — 그 스코어가 **이미 세트에 있다**")
            continue
        sid = claim(name) or _evict_for_required(res, name)
        if sid is None:
            res.notes.append(f"§6-2 ⑦ `{name}` 자리가 없다(상한 {MAX_SCENARIOS})")
            continue
        res.drafts.append(Draft(
            id=sid, scores=scores, strength=0.0, template_id=name,
            why=f"§6-2 ⑦ {name} — {why}",
            variables=[str(getattr(v, "type", "") or "")
                       for v in _said(varis, ("pitcher_state",
                                              "recent_pattern"))],
            added_by="required"))
        n += 1
    # ── 난타전 — 🔴 §5-c-1 이 이미 다룬다(여기서 또 만들지 않는다 · 사본 금지)
    if not any(str(d.template_id) == "baseball_slugfest" for d in res.drafts):
        res.notes.append(
            "§6-2 ⑦ `baseball_slugfest` 는 **§5-c-1 난타전**이 같은 자리다 — "
            "거기서 안 섰으면 포아송 기대 총득점이 문턱 아래다(두 번 만들지 "
            "않는다)")
    return n


def _base(res: Result, groups: dict, game: classify.Game,
          probs: dict | None = None) -> None:
    """§5-a — direction 별로 묶어 A·B·C. 🔴 묶음이 비면 그 시나리오는 없다.

    ⚠️ **축구는 C 가 예외다** — §5-a: *"축구는 C 가 비어도 최소 strength 0.4 로
       생성 — 무승부는 항상 살아 있는 결과."*
    """
    soccer = game.sport == "soccer"
    # 🔴🔴 **종목이 템플릿을 정한다**(사용자 지시 2026-10-02). 실측: 이름을 박아 써서
    #    **야구 경기에 축구 스코어 2-1·1-0** 이 나갔다.
    #    ⚠️ 조건을 읽을 수 없는 템플릿은 그 사실을 **기록으로 남기고** 쓴다.
    dirs_tpl = rules.direction_templates(game.sport)
    if not dirs_tpl:
        dirs_tpl = rules.direction_templates("soccer")
        res.notes.append(
            f"§5-b 에 '{game.sport}' 방향 템플릿 선언이 없다 — 격자에서 뽑거나 "
            f"(없으면) 축구 꼴을 쓴다. 🔴 스코어가 그 종목의 꼴이 아닐 수 있다")
    if dirs_tpl.get("unread_condition"):
        res.notes.append(f"§5-b 조건을 읽을 수 없다 — {dirs_tpl['unread_condition']}")
    for sid, key, tpl in (("A", "home", dirs_tpl.get("home")),
                          ("B", "away", dirs_tpl.get("away"))):
        if not groups[key]:
            res.notes.append(f"{sid}: {key} 묶음이 비어 생성하지 않았다(§5-a)")
            continue
        # ⚠️ `soccer_home_dominant` 는 *"strength_gap ≥ 2단계"* 조건이다.
        #    `strength_gap` 유형은 **아직 미구현**이라(§4 · classify.NOT_CLASSIFIED)
        #    그 조건을 읽을 수 없다 → 항상 `normal` 이다. 그 사실을 남긴다.
        if sid == "A" and soccer:
            res.notes.append(
                "A: `soccer_home_dominant`(strength_gap ≥ 2단계) 조건을 읽을 수 "
                "없다 — `strength_gap` 유형이 미구현이라 `normal` 을 쓴다")
        sc, tid = _tpl_or_derived(res, game, probs, tpl, key)
        if not sc:
            res.notes.append(f"{sid}: 스코어 집합을 못 만들었다 — 생성하지 않는다")
            continue
        res.drafts.append(Draft(
            id=sid, scores=sc,
            strength=round(sum(c.weight for c in groups[key]), 3),
            template_id=tid,
            why=f"§5-a {key} 묶음 {len(groups[key])}개의 weight 합",
            variables=[c.type for c in groups[key] if c.type],
            added_by="template"))

    floor = float((rules._load(rules.SCENARIO_RULES).get("base") or {})
                  .get("soccer_draw_floor") or 0.0)
    draw_w = round(sum(c.weight for c in groups["draw"]), 3)
    # 🔴🔴 **무승부가 최종 결과로 날 수 있는 리그에서만 C 를 만든다.**
    #
    #  ⚠️ 라이브 실측 2026-10-02: 격자에서 하키 스코어를 뽑으니 무승부 `3-3`·`2-2`
    #     가 나왔다 — **NHL 은 슛아웃으로 반드시 승자를 가린다.** 그 시나리오를 내면
    #     카드가 **일어날 수 없는 결과**를 적고, 그 확률이 다른 마켓의 생존을 깎는다.
    #  🔴 규정은 `config/league_rules.yaml` 이 들고 있다(출처·확인 날짜 붙음).
    #     모르면 **만들지 않는다** — 사유를 남긴다.
    can_draw, why_draw = rules.draw_possible(game.league)
    if can_draw is False:
        res.notes.append(f"C: `{game.league}` 는 최종 결과에 무승부가 없다 — "
                         f"무승부 시나리오를 만들지 않는다({why_draw})")
    elif can_draw is None and game.sport != "soccer":
        # 🔴 **v5 §6-4** — *"야구 무승부는 KBO·NPB 만(연장 상한 리그)."*
        #    ⚠️ 선언이 없으면 만들지 않는 것이 맞지만, **어느 리그면 가능한지**를
        #       함께 적어야 다음 사람이 그 선언을 채울 수 있다(#3 조용한 0 금지).
        #    🔴 실측 2026-10-04: **KBO 가 선언에 없었다** — §6-4 가 이름 댔는데도
        #       `None` 이라 무승부를 안 만들고 있었다. 그 줄을 채웠다.
        allow = rules.draw_leagues(game.sport)
        res.notes.append(
            f"C: {why_draw} — 무승부 시나리오를 만들지 않는다"
            + (f". ⚠️ `{game.sport}` 에서 무승부가 **가능한 리그**는 {allow} 다"
               f"(v5 §6-4) — 그 목록에 있는데 선언이 비었다면 "
               f"`config/league_rules.yaml` 을 채워라" if allow else ""))
    if can_draw is not False and (groups["draw"] or (soccer and floor > 0)
                                  or (can_draw and groups["draw"])):
        # 🔴 `soccer_lock` 은 §5-b 의 **유일한 무승부 템플릿**이다. 조건
        #    (*"무득점/무승부 연속 또는 단판"*)이 안 맞아도 다른 선택지가 없다 —
        #    ⚠️ 조건 충족 여부를 **남긴다**. 템플릿을 지어내지 않는다.
        if soccer:
            lock = _lock_condition_met(groups)
            res.notes.append(
                f"C: `soccer_lock` 조건({_tpl('soccer_lock')['condition']}) "
                f"{'충족' if lock else '🔴 미충족 — 그래도 §5-b 에 다른 무승부 템플릿이 없다'}")
        sc, tid = _tpl_or_derived(res, game, probs,
                                  dirs_tpl.get("draw") or "", "draw")
        if not sc:
            return
        res.drafts.append(Draft(
            id="C", scores=sc,
            strength=draw_w if groups["draw"] else floor,
            template_id=tid,
            why=(f"§5-a draw 묶음 weight 합" if groups["draw"]
                 else f"§5-a 축구 draw floor {floor} — 무승부는 항상 살아 있는 결과"),
            variables=[c.type for c in groups["draw"] if c.type],
            added_by="template"))


def _lock_condition_met(groups: dict) -> bool:
    """`soccer_lock` 조건 — *"무득점/무승부 연속 또는 단판"*.

    🔴 변수의 `why` 가 아니라 **유형**으로 본다. `match_type` 이 draw 를 밀면 단판·
       친선이고, `recent_pattern` 이 draw 를 밀면 무승부 연속이다.
    """
    kinds = {c.type for c in groups["draw"]}
    return bool(kinds & {"match_type", "recent_pattern"})


# ══════════════════════════════════════════════════════════════════
# §5-c 교차 규칙 여섯 — 🔴 09-28~29 실패에서 나온 것. 발동·미발동을 다 남긴다
# ══════════════════════════════════════════════════════════════════


#: 🔴 §1 — 시나리오 id 는 **`A`~`E` 글자**다(`types.ScenarioId`). ⚠️ 설명을 id 에
#  넣으면 pydantic 이 거부한다(실측 2026-10-04: `X-1(우세팀 실점 동반)` 가
#  `MarketSurvival.dead_scenarios` 에서 터졌다). 🔴 **글자는 `types` 가 원본**이다.
def drop_impossible_draws(res: Result, game: classify.Game) -> None:
    """🔴🔴 **무승부가 없는 리그에서 무승부 스코어를 걷는다.**

    ══════════════════════════════════════════════════════════════════
    🔴 이 결함은 **처음부터 있었고 계약이 눈이 멀어 있었다**(2026-10-04)
    ══════════════════════════════════════════════════════════════════

    종전 가드는 **`C` 슬롯에만** 걸려 있었다(*"무승부 시나리오를 만들지 않는다"*).
    ⚠️ 그런데 무승부 스코어는 **다른 시나리오 안에도** 들어온다:

        난타전(5c-1, 격자 파생)   `['3-1', **'2-2'**, '3-2']`   ← NHL
        저득점(5c-3)              `[**'1-1'**, '0-0']`

    🔴 NHL 은 슛아웃으로 반드시 승자를 가린다 — 그 스코어는 **일어날 수 없다.**
       카드가 그것을 적고, 그 확률이 다른 마켓의 생존을 **깎는다.**
    ⚠️ 종전 계약은 `d.id == "C"` 를 봤고, 난타전이 `D` 를 쓰는 동안 그 안의
       `2-2` 를 **한 번도 보지 않았다.** §6-2 가 글자 배정을 한 곳으로 모으자
       난타전이 `C` 를 집었고 그 순간 계약이 터졌다.

    🔴 **시나리오를 지우지 않는다** — 스코어만 걷고 그 사실을 사유로 남긴다.
       ⚠️ 스코어가 **전부** 걷혀 빈 시나리오가 되면 그때 떨어뜨린다(§6-2 가
          `outcomes` 가 빈 시나리오를 무효로 본다).
    """
    can_draw, why = rules.draw_possible(game.league)
    if can_draw is not False:
        return
    kept: list[Draft] = []
    for d in res.drafts:
        ties = [sc for sc in d.scores
                if len(str(sc).split("-")) == 2
                and str(sc).split("-")[0] == str(sc).split("-")[1]]
        if not ties:
            kept.append(d)
            continue
        d.scores = [sc for sc in d.scores if sc not in ties]
        res.notes.append(
            f"🔴 `{d.id}` 에서 무승부 스코어 {ties} 를 **걷었다** — "
            f"`{game.league}` 는 최종 결과에 무승부가 없다({why})")
        if d.scores:
            kept.append(d)
        else:
            res.notes.append(
                f"🔴 `{d.id}` 는 스코어가 **전부** 무승부였다 — 시나리오를 "
                f"떨어뜨린다(§6-2 `outcomes` 가 빈 시나리오는 무효다)")
    res.drafts = kept


def _claimer(res: Result):
    """🔴 **비어 있는 시나리오 글자를 준다.** 다 차면 `None`.

    ⚠️ 종전엔 `_cross` 가 `("D", "E")` 를 **글자로 박고** 자기 안에서만 썼다.
       §6-2 보강이 글자를 또 집어야 하므로 **한 곳에서** 낸다 — 두 곳이 따로
       세면 같은 글자를 두 번 주고 pydantic 이 터진다.
    🔴 목록을 베끼지 않는다 — `types.ScenarioId` 가 원본이다.
    """
    import typing

    from app import types as _t
    allowed = list(typing.get_args(_t.ScenarioId))
    used = {d.id for d in res.drafts}
    nxt = iter([x for x in allowed if x not in used])

    def claim(sid_hint: str) -> str | None:
        try:
            return next(nxt)
        except StopIteration:
            res.notes.append(
                f"{sid_hint}: 시나리오 글자({''.join(allowed)})가 다 찼다 — "
                f"더 만들지 못한다")
            return None

    return claim


def _cross(res: Result, varis: list, groups: dict, game: classify.Game,
           standings: dict | None, board: list[str] | None,
           probs: dict | None = None) -> None:
    """§5-c 1~5 를 적용한다(6 은 `_single_direction_guard`).

    🔴 **발동하지 않은 규칙도 사유를 남긴다.** 09-28~29 의 실패가 전부 *"규칙이
       있었는데 안 돌았다"* 였고, 안 돈 것이 보이지 않으면 또 그렇게 된다.
    """
    claim = _claimer(res)

    _c1_open(res, varis, groups, game, standings, claim, probs)
    _c2_rout(res)
    _c3_low(res, varis, game, claim)
    _c4_repeat(res, game)
    _c5_two_goal(res, board, claim)


def _feeders(rule_id: str, varis: list) -> list:
    """🔴 그 교차 규칙에 **붙는 변수들**(§4 카탈로그의 `attaches_to`).

    사용자 설계 2026-10-02: *"작동: 상대 득점 상향 시나리오에 **부착**"*.
    ⚠️ 카탈로그 유형이 아직 미구현이면 **빈 목록**이고, 호출부가 그 사실을 남긴다 —
       규칙이 돌았는지 안 돌았는지가 보여야 한다(09-28~29 실패가 전부 그 꼴이었다).
    """
    return [c for c in varis
            if c.type and rules.attaches_to(c.type) == rule_id]


def _c1_open(res: Result, varis: list, groups: dict, game: classify.Game,
             standings: dict | None, claim, probs: dict | None = None) -> None:
    """§5-c-1 난타전 — `soccer_open`.

    발동 조건:
      ① 수비 약화 + 공격 강화(`lineup_intent`)              ← v4 원문
      ② **포아송 기대 총득점의 P(총 ≥ 4) ÷ 리그 기준 ≥ 1.0** ← 2차 지시로 더한 것
      ③ 맞대결/최근 평균 총득점 ≥ 리그 평균 + 여유            ← 1차 지시 · **약한 예측자**

    🔴 09-28 아르메니아–몬테네그로 **2-3** 이 이 규칙 부재로 빠졌고, 규칙을 만든 뒤에도
       실측 경기(새크라멘토 vs 라스베이거스) 에서 **또** 안 섰다 — 그 경기는
       **3-2(5골)** 였다. 그래서 ② 를 더했다 — ③ 은 장소를
       섞고 표본이 작아 틀렸다(`config/scenario_rules.yaml` 의 측정).
    ⚠️ 순서가 뜻을 가진다: ② 가 서면 ③ 은 보지 않는다. ③ 은 홈/원정 표가 없을
       때의 대타다.
    """
    cfg = rules.cross_rule("5c-1")
    # ① v4 원문 — `lineup_intent` 는 미구현이라 사실상 안 걸린다. 그 사실을 남긴다
    has_intent = any(c.type == "lineup_intent" for c in varis)
    if not has_intent:
        res.notes.append(
            "5c-1 ①(수비 약화 + 공격 강화): `lineup_intent` 변수가 없다 — "
            "그 유형이 미구현이라 이 조건은 사실상 안 걸린다")
    # 🔴 **카탈로그가 붙이는 변수**(사용자 설계의 *"작동"*) — `def_absence` 가 여기다.
    #    ⚠️ 그 유형이 아직 미구현이라 지금은 비어 있다. **그 사실을 남긴다** — 안 남기면
    #       "규칙이 돌았다"로 읽힌다.
    fed = _feeders("5c-1", varis)
    if fed:
        res.notes.append(
            f"5c-1 ⓐ 카탈로그 부착 {len(fed)}건 — "
            f"{[c.type for c in fed]}(§4 `attaches_to: 5c-1`)")
    else:
        res.notes.append(
            "5c-1 ⓐ 카탈로그 부착 0건 — `attaches_to: 5c-1` 유형(def_absence)이 "
            "아직 미구현이다")
    # ② 🔴 포아송 모형 — **1순위**
    if _c1_model(res, game, standings, claim, cfg, probs):
        return
    # ③ 평균 기반 대타
    thr = (standings or {}).get("open_game_threshold")
    if thr is None:
        res.notes.append(
            f"5c-1 ③: 리그 평균을 못 구했다 — 발동하지 않는다"
            f"({cfg.get('no_league_avg')})")
        return
    got = _open_signals(standings, cfg, res)
    hits = [(lbl, v) for lbl, v in got if v is not None and v >= float(thr)]
    if not hits:
        res.notes.append(
            f"5c-1 ③: 문턱 {thr} 미달 — "
            f"{', '.join(f'{l} {v}' for l, v in got if v is not None) or '신호 없음'}")
        return
    sid = claim("D(난타전)")
    if sid is None:
        return
    # 🔴 §5-d — strength 는 **발동 근거가 된 배경의 weight 합**이다(사용자 지시
    #    2026-10-02). 근거의 hardness 를 못 읽으면 바닥값을 쓴다.
    w = round(sum(_signal_weight(standings, lbl) for lbl, _ in hits), 3) \
        or float(cfg.get("floor_strength") or 0.3)
    # 🔴 **난타전 템플릿도 종목별이다**(실측 2026-10-02: 야구에 `soccer_open`
    #    2-2·2-3·3-2 가 들어갔다 — 야구 총점 기준선은 7.5 다).
    sc, tid = _tpl_or_derived(res, game, probs,
                              rules.direction_templates(game.sport).get("open"),
                              "open:3")
    if not sc:
        res.notes.append("5c-1 ③: 난타전 스코어를 못 만들었다 — 만들지 않는다")
        return
    res.drafts.append(Draft(
        id=sid, scores=sc, strength=w, template_id=tid,
        probability=league.scores_mass(probs, sc),
        why=("§5-c-1 난타전 ③ — " + " · ".join(f"{l} 평균 {v}" for l, v in hits)
             + f" ≥ 리그 평균 기준 {thr}"),
        added_by="rule:5c-1"))


def _venue_row(standings: dict | None, side: str, team: str) -> dict | None:
    """`venue_rows` 에서 **그 팀의 그 장소 줄**을 고른다.

    🔴 홈팀은 **홈 표**, 원정팀은 **원정 표** 다 — 섞으면 조용히 틀린다.
    ⚠️ 못 찾으면 `None` 이고 호출부가 사유를 남긴다(조용한 0 금지).
    """
    rows = ((standings or {}).get("venue_rows") or {}).get(side) or []
    for r in rows:
        if verify.mentions_team(str(r.get("team") or ""), team, None):
            return r
    return None


def _c1_model(res: Result, game: classify.Game, standings: dict | None,
              claim, cfg: dict, probs: dict | None = None) -> bool:
    """§5-c-1 ② — **포아송.** 섰으면 `True`.

    🔴 **안 섰으면 왜 안 섰는지 남긴다** — 모형이 조용히 빠지면 ③ 이 발동한 것으로
       읽힌다(09-28~29 실패가 전부 그 꼴이었다).
    """
    model = (cfg or {}).get("model") or {}
    avgs = (standings or {}).get("venue_averages")
    hr = _venue_row(standings, "home", game.home)
    ar = _venue_row(standings, "away", game.away)
    if not avgs or hr is None or ar is None:
        miss = [n for n, v in (("리그 홈/원정 평균", avgs),
                               (f"{game.home} 홈 줄", hr),
                               (f"{game.away} 원정 줄", ar)) if not v]
        res.notes.append(
            f"5c-1 ②(포아송): {' · '.join(miss)} 이 없다 — "
            f"{model.get('no_venue_tables') or '발동하지 않는다'}")
        return False
    got = league.open_game_ratio(hr, ar, avgs)
    if got is None:
        res.notes.append("5c-1 ②(포아송): 기대 득점을 계산하지 못했다 — "
                         "홈/원정 줄에 경기수나 득실이 비어 있다")
        return False
    # 🔴 **비교 대상은 리그 평균이 아니라 "이미 둔 시나리오"다**(3차 지시).
    #    딥서치: 물어야 할 것은 *"이 밴드가 이미 내고 있는 시나리오만큼 그럴듯한가"*.
    #    ⚠️ 격자를 못 만들면 그 비교를 할 수 없다 — 그때만 비율로 묻는다.
    kept = [d.probability for d in res.drafts if d.probability is not None]
    if probs and kept:
        low = min(kept)
        shown = (f"기대 총득점 {got['total']} · P(총 ≥ {got['goals']}) {got['p']} "
                 f"vs 이미 둔 시나리오 최소 확률 {round(low, 4)}")
        if got["p"] < low:
            res.notes.append(
                f"5c-1 ②(포아송): 이미 둔 시나리오보다 덜 그럴듯하다 — {shown}")
            return False
    else:
        need = model.get("prob_ratio")
        if need is None:
            raise ValueError("§5-c-1 model.prob_ratio 가 없다")
        shown = (f"기대 총득점 {got['total']} (리그 {got['league_total']}) · "
                 f"P(총 ≥ {got['goals']}) {got['p']} vs 리그 기준 "
                 f"{got['league_p']} → 비율 {got['ratio']}")
        if got["ratio"] < float(need):
            res.notes.append(
                f"5c-1 ②(포아송): 격자가 없어 리그 기준으로 물었고 비율 문턱 "
                f"{need} 미달 — {shown}")
            return False
    sid = claim("D(난타전)")
    if sid is None:
        return False
    w = _signal_weight(standings, "포아송") \
        or float(cfg.get("floor_strength") or 0.3)
    n = (cfg.get("model") or {}).get("open_goals")
    sc, tid = _tpl_or_derived(res, game, probs,
                              rules.direction_templates(game.sport).get("open"),
                              f"open:{n}")
    if not sc:
        return False
    res.drafts.append(Draft(
        id=sid, scores=sc, strength=round(w, 3), template_id=tid,
        # 🔴 무게는 **확률**이다(3차 지시). `strength` 는 §5-d 로 남는다
        probability=league.scores_mass(probs, sc),
        why=f"§5-c-1 난타전 ② 포아송 — {shown}",
        added_by="rule:5c-1"))
    return True


def _open_signals(standings: dict | None, cfg: dict | None = None,
                  res: Result | None = None) -> list[tuple[str, float | None]]:
    """난타전 ③ 신호값. 🔴 지금은 리그 평균만 있고 **맞대결·최근 평균은 호출부가
    넣어 줘야 한다** — 없으면 `None` 이고 그 사실이 사유로 남는다.

    🔴 **맞대결은 표본이 모자라면 쓰지 않는다**(`h2h_min_games`). 딥서치가 못 박았다:
       8경기 미만이면 한 경기가 평균을 통째로 왜곡한다. 실측 그 경기의 맞대결에
       5-0 이 끼어 있다 — 바로 그 예다.
    """
    s = standings or {}
    h2h = s.get("h2h_window_avg_goals")
    need = (cfg or {}).get("h2h_min_games")
    n = s.get("h2h_window_games")
    if h2h is not None and need is not None and (n is None or n < int(need)):
        if res is not None:
            res.notes.append(
                f"5c-1 ③ 맞대결 평균을 버린다 — 표본 {n if n is not None else '미상'}"
                f"경기로 {need}경기에 못 미친다(한 경기가 평균을 왜곡한다)")
        h2h = None
    return [("맞대결 창", h2h), ("최근 5경기", s.get("recent_avg_goals"))]


def _signal_weight(standings: dict | None, label: str) -> float:
    """근거 배경의 weight. 🔴 순위표·폼은 공시이나 발행 시각이 없어 soft 다."""
    from app.types import WEIGHT_OF
    return WEIGHT_OF["soft"] if (standings or {}).get("league_avg_goals") else 0.0


def _c2_rout(res: Result) -> None:
    """§5-c-2 대량 득점 — `strength_gap ≥ 2단계` + 주력 기용.

    🔴 **발동할 수 없다** — `strength_gap`·`lineup_intent` 둘 다 미구현이다.
       ⚠️ 그 사실을 남긴다. 안 남기면 *"규칙이 돌았다"* 로 읽힌다(09-29 르방컵).
    """
    res.notes.append(
        "5c-2 대량 득점: `strength_gap`·`lineup_intent` 가 둘 다 미구현이라 "
        "원문 조건을 읽을 수 없다. 🔴 **v5 §6-2 ② 가 읽을 수 있는 네 방아쇠를 "
        "줬다**(수비 결장 2명+ · 랭킹 차 50+ · 직전 대패 · 양 팀 연속 득점 폼) — "
        "그 판정은 `require_set` 이 한다(09-29 르방컵이 이 규칙 부재였다)")


def _c3_low(res: Result, varis: list, game: classify.Game, claim) -> None:
    """§5-c-3 저득점 — `recent_pattern` 무득점 2경기 이상 **또는** 단판/결승.

    🔴 09-29 레온–아메리카 오버 3.5 철회가 이 규칙 부재였다.
    """
    # 🔴 카탈로그 부착 — `squad_rotation` 이 여기다(우세팀 하향 · 무득점 시나리오)
    fed = _feeders("5c-3", varis)
    res.notes.append(
        f"5c-3 ⓐ 카탈로그 부착 {len(fed)}건"
        + (f" — {[c.type for c in fed]}" if fed
           else " — `attaches_to: 5c-3` 유형(squad_rotation)이 아직 미구현이다"))
    single = any(c.type == "match_type" for c in varis)
    if not single:
        res.notes.append(
            "5c-3 저득점: 무득점 연속은 **총점 패턴이라 변수가 아니다**(§4) — "
            "지금은 `match_type`(단판·친선)만으로 판단한다. 그것도 없다")
        return
    sid = claim("E(저득점)")
    if sid is None:
        return
    cfg = rules.cross_rule("5c-3")
    res.drafts.append(Draft(
        # 🔴 스코어·바닥값은 **yaml 이 원본이다** — 코드에 박지 않는다
        id=sid, scores=_rule_scores("5c-3"),
        strength=float(cfg.get("floor_strength") or 0.3),
        template_id="5c-3",
        why="§5-c-3 저득점 생성 — `match_type`(단판/친선) 변수가 있다",
        added_by="rule:5c-3"))


def _c4_repeat(res: Result, game: classify.Game) -> None:
    """§5-c-4 전날 재현 — 야구 전용. 🔴 전날 스코어가 필요하다."""
    if game.sport != "baseball":
        # 🔴 **종목이 달라도 기록을 남긴다.** 안 남기면 *"그 규칙이 돌았다"* 로
        #    읽힌다 — 09-28~29 실패가 전부 그 모양이었다.
        res.notes.append(
            f"5c-4 전날 재현: 야구 전용 규칙이고 이 경기는 '{game.sport}' 다 — "
            f"발동하지 않는다")
        return
    res.notes.append(
        "5c-4 전날 재현: 전날 같은 팀의 스코어·패턴을 아직 자료로 안 받는다 — "
        "발동하지 않는다(09-28 세이부가 실제로 그렇게 졌다)")


def _c5_two_goal(res: Result, board: list[str] | None, claim) -> None:
    """§5-c-5 — *"핸디 +1.5 가 후보 마켓이면 상대가 2골 차로 이기는 시나리오를
    반드시 하나 만든다."* 근거 변수가 없어도 **없애지 않는다**(floor).

    🔴 보드가 없으면 §6-c-3 대로 **핸디 ±0.5/±1.5 만** 후보다 → 항상 발동한다.
    """
    cfg = rules.cross_rule("5c-5")
    if board is not None and not any("1.5" in str(b) for b in board):
        res.notes.append("5c-5: 보드에 ±1.5 줄이 없다 — 발동하지 않는다(§6-c-1)")
        return
    sides = cfg.get("two_goal_scores") or {}
    if not sides:
        raise ValueError("§5-c-5 에 `two_goal_scores` 가 없다")
    for side in ("home", "away"):
        want = [str(x) for x in (sides.get(side) or [])]
        if not want:
            continue
        # 🔴 **방향마다 따로 본다.** 전 판은 *"2골 차 스코어가 하나라도 있으면
        #    건너뛴다"* 였고, 그러면 `3-0` 이 있을 때 `0-2` 를 영영 안 만든다 —
        #    그러면 홈 +1.5 가 깨질 시나리오 없이 생존 1.0 을 받는다(사용자 지시 ⑪).
        if any(_wins_by(x, side, TWO_GOAL) for d in res.drafts for x in d.scores):
            res.notes.append(
                f"5c-5({side}): 이미 {side} 가 2골 차로 이기는 시나리오가 있다")
            continue
        sid = claim(f"2골 차({side})")
        if sid is None:
            # 🔴 **자리가 없다** — 지어내 넣지 않고 이름으로 남긴다. §6 이 그
            #    핸디를 등급 없이 둔다(§7 R6: 그 시나리오가 없으면 계산이 실패한다)
            res.notes.append(
                f"🔴 5c-5({side}): 시나리오 자리 {cfg.get('slots')}개가 다 찼다 — "
                f"{side} 2골 차 승 시나리오를 못 넣었다. §7 R6 대로 그 쪽 ±1.5 "
                f"핸디는 **등급을 매기지 않는다**")
            continue
        res.drafts.append(Draft(
            id=sid, scores=want,
            strength=float(cfg.get("floor_strength") or 0.3),
            template_id="5c-5",
            why=(f"§5-c-5 — 핸디 ±1.5 가 후보이므로 {side} 2골 차 승 시나리오를 "
                 f"만든다" + ("(보드 없음 · §6-c-3)" if board is None else "")),
            added_by="rule:5c-5"))


def _wins_by(score: str, side: str, margin: int) -> bool:
    """그 스코어에서 `side` 가 `margin` 골 이상 차로 이기나.

    🔴 스코어 리터럴을 코드에 박지 않는다 — 숫자로 센다.
    """
    import re as _re
    m = _re.match(r"\s*(\d+)\s*-\s*(\d+)\s*$", str(score or ""))
    if not m:
        return False
    h, a = int(m.group(1)), int(m.group(2))
    return (h - a >= margin) if side == "home" else (a - h >= margin)


def _single_direction_guard(res: Result) -> None:
    """§5-c-6 · §7 R5 — *"모든 시나리오가 한 방향이면"* 되돌린다.

    🔴 `types.Scenarios` 검증기도 같은 것을 막는다(두 겹). 여기서 **먼저** 잡아
       사유를 남긴다 — 스키마 예외만 터지면 왜인지 안 보인다.
    """
    if len(res.drafts) < 2:
        res.insufficient = True
        res.notes.append(
            f"시나리오가 {len(res.drafts)}개다 — §3 STEP 5 는 2 이상을 요구한다")
        return
    if not rules.all_one_direction([d.scores for d in res.drafts]):
        # 🔴 **통과한 것도 기록한다** — 이 규칙이 돌았는지 안 돌았는지가 보여야 한다
        res.notes.append(
            f"5c-6 단일 방향 금지: 시나리오 {len(res.drafts)}개가 한 방향이 아니다 "
            f"— 통과")
        return
    if rules.all_one_direction([d.scores for d in res.drafts]):
        res.insufficient = True
        res.drafts = []
        res.notes.append(
            "§5-c-6 단일 방향 금지 — 모든 시나리오가 한 방향이다. STEP 3 으로 "
            "되돌려 반대 변수를 다시 찾고, 그래도 없으면 자료 부족이다")
