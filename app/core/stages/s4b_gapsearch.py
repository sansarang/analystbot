"""🔴🔴 **딥서치가 못 찾으면 LLM 이 검색한다** — 사용자 지시 2026-10-14.

> 3번(감독 이름)·4번(감독 부임후 성적)·5번(팀내 불화)은 딥서치에서 못 찾으면
> **llm 이 찾게 한다** … 그래서 llm 을 **전략예측 및 서치**로 쓰는 거다.
> 🔴 *"llm 회상하는게 아니라 **서치**하는거라고 … llm이 **서치**하는거라고"*

## 🔴🔴 LLM 은 **질의를 쓴다. 사실을 말하지 않는다.**
⚠️ 내가 처음 만든 판은 모델 **기억**을 사실로 받았다(`s4b_recall`) — 사용자가
   그것을 바로잡았다. 🔴 사실은 **문서에서만** 온다.

```
빈 칸을 센다  →  LLM 이 그 칸을 겨냥한 **질의**를 쓴다  →  우리 검색 사슬이
던진다  →  문서를 받는다  →  s4 추출·s5 검증이 **사실**로 만든다
```

🔴 그래서 이 파일은 `core/querywriter` 와 **같은 잠금**을 쓴다:
  ① LLM 출력은 **글자(질의·매체)뿐**이다 — 사실·숫자·판정 칸이 없다
  ② 던지는 통로는 **기존 사슬**이다(새 엔진을 만들지 않는다)
  ③ 매체는 robots 확인 뒤에만 쓴다(`querywriter.check_hosts`)
  ④ 무엇을 던졌고 무엇을 받았는지 카드가 적는다(#3)

## 🔴🔴 **겨냥하는 것은 "변수"다** — 사용자 지시 2026-10-14
> llm이 검색할 대상은 **변수에 관련된 내용**이다 … **x search 가 약해서** 하는거다

🔴 그래서 세 칸(감독·성적·불화)만이 아니라 **빈손으로 돌아온 하위 과제의 유형**
   전부를 겨냥한다. 하위 묶음은 `config/subtask_groups.yaml` 이 들고 있고
   (A 결장·피로 / B 로테이션·감독 / C 동기·순위 / D 일정·경기외 / F 복귀·명단),
   그 묶음이 **변수를 0개** 냈으면 그 유형이 *"검색이 약한 자리"* 다.
⚠️ 묶음 목록을 여기 베끼지 않는다 — `research.subtasks.groups()` 가 원본이다.

## 세 칸 — 늘 겨냥하는 것(통로가 아예 없거나 1차 경로가 비는 칸)
| 칸 | 딥서치 1차 경로 | 여기서 겨냥하는 질의 |
|---|---|---|
| 감독 이름 | 경기 페이지 `isCoach` | `{팀} manager` · `{팀} head coach` |
| 부임 후 성적 | 🔴 통로 없음 | `{팀} {감독} record since appointed` |
| 팀내 불화 | 하위 B(`coach_conflict`) | `{팀} row with coach` · 현지어 |

⚠️ 질의가 0건을 받아도 **지어내지 않는다** — 그 사실만 적는다.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.core.schema import MatchRef
from app.core.state import RunState

logger = logging.getLogger(__name__)

#: 🔴🔴 **LLM 서치에서 찾을 것**(사용자 지시 2026-10-14) — 그 순서로 묶는다
#
#  > 1. 경기에 따른 **팀순위** · 2. 각팀의 **최근 3경기 일정에 따른 피로도** ·
#  > 3. **홈까지의 거리** · 4. **기본팀의 전술** · 5. **포메이션**
#
#  ⚠️ 앞서 받던 셋(감독 이름·부임 후 성적·팀내 불화)도 **그대로** 둔다.
#  🔴 칸 이름 → 그 칸을 **어디서 보나**(이미 있으면 LLM 에 안 묻는다).
GAPS: tuple[tuple[str, str], ...] = (
    ("팀 순위", "standings"),
    ("피로도(최근 3경기)", "schedule"),
    ("홈까지 거리", "venue"),
    ("기본 전술", "past_xi"),
    ("포메이션", "xi"),
    ("감독 이름", "coach"),
    ("부임 후 성적", "coach_record"),
    ("팀내 불화", "conflict"),
)

#: 🔴 공급자 둘 — **순서대로 시도**한다(사용자 지시 2026-10-14: *"deepseek,
#   solar pro 둘다 api가 있다"*). 앞이 0개를 내면 뒤로 간다.
PROVIDERS: tuple[str, ...] = ("deepseek", "solar")

#: 🔴🔴 **검색 언어 순서** — *"현지어 영어등 순으로"*(지시 2026-10-14).
#   ⚠️ 코드를 **열거로 잠근다** — 모델이 낼 수 있는 것은 이 글자들뿐이다.
LANGS: tuple[str, ...] = ("nl", "it", "es", "de", "fr", "pt", "ja", "ko",
                          "zh", "tr", "ru", "ar", "en")

#: 🔴 질의 상한 — `querywriter.MAX_QUERIES` 와 **따로** 둔다(이쪽은 표적이라 적다)
MAX_Q = 6
#: 🔴 질의 글자 상한(`app/llm.query_ok` 의 1~6낱말 규칙과 맞춘다)
MAX_LEN = 80

#: 🔴 마지막 호출이 고른 **언어 순서** — 부르는 쪽이 사슬에 그 순서로 던진다.
#   ⚠️ 글자(코드)뿐이다 — 사실이 아니다.
_LAST_LANGS: list[str] = []


def langs_of() -> list[str]:
    """🔴 마지막 `ask` 가 고른 언어 순서(현지어 먼저). 없으면 `["en"]`."""
    return list(_LAST_LANGS) or ["en"]


class GapQueries(BaseModel):
    """🔴🔴 LLM 이 내는 것 — **질의 글자와 언어 코드뿐**이다.

    ⚠️ 사실·수·이름 칸을 두지 않는다. 두는 순간 모델 기억이 사실로 들어온다
       (사용자가 바로잡은 그 지점이다).
    🔴 `langs` 는 **사실이 아니다** — 검색 통로에 줄 **언어 힌트**다. 그래도
       `enums` 로 `LANGS` 안에 **잠근다**(모델이 아무 글자나 못 넣는다).
       사용자 지시 2026-10-14: *"검색은 현지어 영어등 순으로 해라"* — 현지어를
       **아는 것이 모델이고**(코모=이탈리아어·페예노르트=네덜란드어), 우리
       `queries.langs_for` 는 클럽의 나라를 모른다(실측: UCL 은 `('en',)` 만).
    """

    queries: list[str] = Field(default_factory=list)
    langs: list[str] = Field(default_factory=list)


def need(facts, *, keys: list[str], conflict_docs: int = 0,
         names: dict | None = None) -> dict[str, list[str]]:
    """🔴🔴 **무엇이 비었나** — 팀마다 못 받은 칸. 전부 찼으면 빈 표다.

    🔴 이 함수가 *"딥서치가 못 찾았다"* 의 **단일 판정**이다(사본 금지).
    🔴 칸은 `GAPS` 여덟이고, **이미 받은 칸은 묻지 않는다**(지시 2026-10-14:
       1 팀순위 · 2 피로도 · 3 홈까지 거리 · 4 기본 전술 · 5 포메이션 + 감독 셋).
    ⚠️ 열쇠가 아니라 **이름**으로 적는다 — 카드·프롬프트가 사람 글자를 쓴다.
    """
    out: dict[str, list[str]] = {}
    said = dict(names or {})
    coach = dict(getattr(facts, "coach", None) or {})
    std = dict(getattr(facts, "standings", None) or {})
    sched = dict(getattr(facts, "schedule", None) or {})
    past = dict(getattr(facts, "past_xi", None) or {})
    xi = dict(getattr(facts, "xi", None) or {})
    ctx = dict(getattr(facts, "context", None) or {})
    for key in keys:
        one = coach.get(key)
        miss: list[str] = []
        # ① 팀 순위 — 그 대회 순위표
        if not std.get(key) and not std.get("rows") and not std:
            miss.append("팀 순위")
        # ② 피로도 — 최근 3경기 일정(휴식일·14일 내 경기 수)
        if not sched.get(key):
            miss.append("피로도(최근 3경기)")
        # ③ 홈까지 거리 — 경기장 좌표·이동
        if not ctx.get("venue") and not ctx.get("travel"):
            miss.append("홈까지 거리")
        # ④ 기본 전술 — 평소 XI(그 팀이 늘 쓰는 꼴)
        if len(list(past.get(key) or [])) < 3:
            miss.append("기본 전술")
        # ⑤ 포메이션 — 오늘 XI 의 꼴
        got_xi = xi.get(key)
        if got_xi is None or not str(getattr(got_xi, "formation", "") or ""):
            miss.append("포메이션")
        # ⑥⑦ 감독 이름 · 부임 후 성적
        if one is None or not str(getattr(one, "name", "") or ""):
            miss.append("감독 이름")
        if one is None or not str(getattr(one, "record", "") or ""):
            miss.append("부임 후 성적")
        # ⑧ 팀내 불화
        if not conflict_docs:
            miss.append("팀내 불화")
        if miss:
            out[str(said.get(key) or key)] = miss
    return out


def thin_kinds(variables, *, floor: int = 1) -> dict[str, list[str]]:
    """🔴🔴 **변수가 얇은 하위 묶음** — `{묶음 열쇠: [유형 …]}`.

    > llm이 검색할 대상은 **변수에 관련된 내용**이다 … **x search 가 약해서**
    > 하는거다 (지시 2026-10-14)

    🔴 묶음·유형 목록은 `research.subtasks.groups()` 에서 읽는다(사본 금지).
    🔴 그 묶음이 낸 변수가 `floor` 미만이면 *"검색이 약한 자리"* 로 센다.
    ⚠️ 규칙으로 지은 변수(`from_rule`)는 **검색이 찾은 것이 아니다** — 안 센다.
    """
    from app.research import subtasks as _sub
    got: dict[str, int] = {}
    kinds: dict[str, list[str]] = {}
    for one in (_sub.groups() or []):
        key = str(dict(one).get("key") or "")
        if not key:
            continue
        kinds[key] = [str(x) for x in (dict(one).get("kinds") or [])]
        got[key] = 0
    for v in (variables or []):
        if str(getattr(v, "from_rule", "") or ""):
            continue
        sub = str(getattr(v, "subtask", "") or "")
        head = sub.split("-", 1)[0] if sub else ""
        if head in got:
            got[head] += 1
    return {k: kinds[k] for k, n in got.items() if n < floor and kinds.get(k)}


def _coach_name(facts, key: str) -> str:
    """🔴 이미 받은 감독 이름(있으면 질의를 그 이름으로 좁힌다)."""
    one = dict(getattr(facts, "coach", None) or {}).get(key)
    return str(getattr(one, "name", "") or "") if one is not None else ""


def ask(ref: MatchRef, facts, *, state: RunState, want: dict,
        thin: dict | None = None,
        langs: list[str] | None = None) -> tuple[list[str], str]:
    """🔴🔴 **LLM 1회로 표적 질의를 받는다**. `(질의 목록, 사유)`.

    ⚠️ 실패하면 **빈 목록**이다 — 이 단계가 조용히 거짓을 만들지 않는다.
    🔴 받은 질의는 `app.llm.query_ok`(1~6낱말·연산자 금지·연도 금지)와
       `querywriter.keep`(팀 표기 포함)으로 **걸러서** 쓴다 — 사본 금지.
    """
    from app.core import llm, querywriter
    from app.core import discover as _d
    if not want and not dict(thin or {}):
        return [], "✅ 빈 칸도 얇은 묶음도 없다 — LLM 에 안 물었다"
    names = [str(getattr(ref, f"{s}_name", "") or "") or str(getattr(ref, s, "") or "")
             for s in ("home", "away")]
    # 🔴🔴 **이름으로 별칭을 뽑는다** — `ref.home` 은 `team:000455`(내부 열쇠)다.
    #    ⚠️ 실사고 2026-10-14(페예노르트–코모): 열쇠로 뽑아 별칭이 쓰레기가 되고
    #       LLM 질의 **6개가 전부** `팀 표기 없음`으로 버려졌다 → 표적 검색 0건.
    aliases: list[str] = []
    for one in names:
        if not one:
            continue
        aliases.append(one)
        aliases += [str(x) for x in (_d.aliases_of(one) or [])][:6]
    # 🔴 팀 이름의 **낱말 하나**도 표기로 받는다(`Como 1907` → `Como`) — 그렇지
    #    않으면 사람이 쓰는 꼴의 질의가 전부 버려진다.
    for one in list(names):
        for bit in str(one).split():
            if len(bit) >= 4 and not bit.isdigit():
                aliases.append(bit)
    aliases = list(dict.fromkeys(x for x in aliases if x))
    said_want = " · ".join(f"{k}: {', '.join(v)}" for k, v in want.items())
    said_coach = " · ".join(
        f"{n}={_coach_name(facts, str(getattr(ref, s, '') or '')) or '모른다'}"
        for s, n in (("home", names[0]), ("away", names[1])))
    msgs = [
        llm.Message(role="system", content=(
            "너는 검색 질의를 쓰는 사람이다. 🔴 **사실을 말하지 않는다** — "
            "감독 이름·성적·불화를 **아는 척하지 말고**, 그것을 찾을 "
            "**검색어만** 만든다. 네가 모르는 것을 질의로 적는 것이 네 일이다.")),
        llm.Message(role="user", content=(
            f"경기: {names[0]} vs {names[1]} · {getattr(ref, 'competition', '')}\n"
            f"팀 표기(이 글자들만 쓴다): {' · '.join(aliases[:12])}\n"
            f"이미 아는 감독: {said_coach}\n"
            f"🔴 **못 찾은 칸**: {said_want or '없다'}\n"
            + (f"🔴 **검색이 얇은 자리**(변수 0개인 묶음): "
               + " · ".join(f"{k}({', '.join(v[:4])})"
                            for k, v in dict(thin or {}).items()) + "\n"
               if dict(thin or {}) else "")
            + f"쓸 언어: {', '.join(langs or ['en'])}\n\n"
            f"🔴 `queries` — 위 **못 찾은 칸을 겨냥한** 검색어 {MAX_Q}개 이하.\n"
            "   · 팀 순위 → `{팀} standings` · `{팀} classifica` 꼴\n"
            "   · 피로도 → `{팀} fixtures schedule` · `{팀} rotation rest`\n"
            "   · 홈까지 거리 → `{팀} away travel` · `{팀} trasferta`\n"
            "   · 기본 전술 → `{팀} tactics style` · `{팀} modulo`\n"
            "   · 포메이션 → `{팀} formation` · `{팀} formazione`\n"
            "   · 감독 이름 → `{팀} manager` · `{팀} head coach`\n"
            "   · 부임 후 성적 → `{팀} {감독} record since`(감독을 알 때만)\n"
            "   · 팀내 불화 → `{팀} row with coach` · 현지어 표현\n"
            "   · **검색이 얇은 자리** → 그 유형을 찾을 검색어(예 `absence` →\n"
            "     `{팀} injury news`, `stakes` → `{팀} qualification race`)\n"
            "🔴 각 질의에 **위 팀 표기 중 하나를 반드시** 넣는다.\n"
            "🔴🔴 **현지어를 먼저** 쓴다 — 그 팀 나라의 말이다(네가 안다). 그다음\n"
            "   영어다. `langs` 에 **그 순서로** 언어 코드를 적는다(예 "
            "`[\"it\", \"nl\", \"en\"]`).\n"
            f"   ⚠️ 쓸 수 있는 코드: {', '.join(LANGS)}\n"
            "🔴 1~6낱말 · 연산자(`site:`·따옴표·마이너스) 금지 · **연도 금지**.\n"
            "⚠️ 숫자·이름·상태를 **답으로** 쓰지 마라 — 질의 글자만 낸다.")),
    ]
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **공급자 둘을 순서대로**(지시 2026-10-14: *"deepseek, solar pro 둘다
    #    api가 있다"*)
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-14(페예노르트–코모): `deepseek` 가 질의를 **0개** 냈다.
    #     🔴 그래서 앞 공급자가 비면 **뒤로 간다** — 한 공급자에 매달지 않는다.
    rows: list[str] = []
    langs_got: list[str] = []
    tried: list[str] = []
    for pv in PROVIDERS:
        got = llm.ask(provider=pv, purpose="query", messages=msgs,
                      out=GapQueries, state=state,
                      enums={"langs": list(LANGS)})
        if not isinstance(got, GapQueries):
            tried.append(f"{pv} 🔴 실패({getattr(got, 'reason', '?')})")
            continue
        rows = [str(x).strip()[:MAX_LEN] for x in (got.queries or [])
                if str(x).strip()]
        langs_got = [str(x) for x in (got.langs or []) if str(x) in set(LANGS)]
        tried.append(f"{pv} 질의 {len(rows)}개")
        if rows:
            break
    if not rows:
        why = ("🔴 **두 공급자 다 질의를 못 냈다** — " + " · ".join(tried)
               + " · 표적 검색을 안 돌린다")
        state.note(f"s4b 표적 검색 — {why}")
        return [], why
    kept, bad = querywriter.keep(rows, aliases=aliases)
    # 🔴 글자 규칙은 `app.llm.query_ok` 하나다(사본 금지)
    from app import llm as _lq
    ok = [q for q in kept if _lq.query_ok(q)]
    n_cut = len(kept) - len(ok)
    why = (f"빈 칸 {said_want or '없다'}"
           + (f" · 얇은 묶음 {list(dict(thin or {}))}" if dict(thin or {}) else "")
           + f" → LLM 질의 **{len(rows)}개** 중 "
           + f"**{len(ok)}개**를 쓴다"
           + (f" · 🔴 팀 표기 없어 버림 {len(bad)}" if bad else "")
           + (f" · 🔴 글자 규칙에서 버림 {n_cut}" if n_cut else "")
           + f" · 공급자 {' → '.join(tried)}"
           + f" · 언어 순서 {langs_got or list(langs or ['en'])}"
           + " · 🔴 사실은 **문서에서만** 온다(모델 기억 안 씀)")
    state.note(f"s4b 표적 검색 — {why}")
    _LAST_LANGS.clear()
    _LAST_LANGS.extend(langs_got or list(langs or ["en"]))
    return ok[:MAX_Q], why
