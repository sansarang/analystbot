"""🔴🔴 **전략 전문가(LLM)가 변수를 짓는다** — 사용자 지시 2026-10-15.

> 라인업 확장 포메이션 결장 선수가 **주요선수가 뜨면** 전략 전문가 deepseek 에게
> **변수 생성하는 프롬프트**를 주입해라.

🔴🔴 **잠금 넷** — 이 통로가 지켜야 하는 것
  ① LLM 이 내는 것은 **글자뿐**이다(`side`·`kind`·`text`). 방향(`favors`)·
     가중(`weight`)·골 방향(`goals`)은 **코드가 정한다**(절대규칙 5 · 계약이
     `direction`·`weight`·`strength`·`survival`·`verdict` 에 LLM 이 닿는 것을
     막는다).
  ② 그래서 기본값은 **`favors="both"`**(방향 없음)이고, 배치표가 주는 자리에
     들어가도 **확률을 밀지 않는다** — 🟡 **표시·검증·가설**이다.
     🔴 확률에 닿게 하려면 **방향 표**를 사용자가 정해야 한다(그때 이 칸을 연다).
  ③ 🔴 **XI 가 있으면 부른다**(사용자 지시 2026-10-16 — 변화가 없어도 돈다) ·
     아래 "트리거" 는 이제 **사유 글**이다: 핵심 선수가 빠졌거나 포메이션이 바뀌었거나
     자리가 많이 바뀐 때만이다. 늘 부르면 예산을 태운다.
  ④ 공급자는 **deepseek 우선**(지시)이고 죽어 있으면 solar 가 받는다
     (`llm.ask_first` 하나가 차례를 돈다 · 사본 금지).

⚠️ 실측 2026-10-15: ⑤-b 는 **코드 판정**이고 LLM 판정을 버린다. 이 통로는 그
   판정을 **대체하지 않는다** — 그 옆에 *"전략 읽기"* 변수를 더할 뿐이다.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.core.schema import Facts, MatchRef, Variable
from app.core.state import RunState

logger = logging.getLogger(__name__)

#: 🔴 LLM 이 고를 수 있는 **전술 읽기 갈래** — 표에 있는 글자만(지어내기 금지)
#: 🔴 **두 모델이 갈린 줄** 표시(맥락 전용으로 내린다)
CONFLICT = "🔴 모델 충돌"
#: 🔴 **한 모델만 낸 줄** — 합의가 아니므로 확률에 안 닿는다(사용자 지시
#   2026-10-16: *"llm 둘 다 **같은 것만** 변수에 반영되어야 한다"*).
#   ⚠️ 버리지 않는다 — 맥락 전용으로 남겨 **어느 쪽이 맞는지 확인**할 거리다.
ALONE = "🟡 한 모델만"

KINDS: tuple[str, ...] = (
    "압박 높이", "수비 라인", "빌드업", "측면 집중", "중원 수싸움",
    "역습 성향", "세트피스", "교체 운용",
    # 🔴🔴 **일정·피로도**(사용자 지시 2026-10-16) — *"그 팀의 **피로도**를
    #    변수에 넣게 한다"*. ⚠️ 재료는 **휴식일·최근 경기 간격**이고 아래
    #    `rest_of` 가 넘긴다(모델이 날짜를 세지 않는다).
    "일정·피로도",
    # 🔴🔴 **기사 사실**(사용자 지시 2026-10-15) — 기사 여러 줄을 **내용으로**
    #    읽어 **한 줄의 부등호**로 정리하는 자리다(개수로 세지 않는다).
    "기사 사실",
)
#: 🔴 배치표가 아는 유형으로 **코드가** 적는다(축2 — 스타일 조정·전략 판정)
VAR_TYPE = "lineup_intent"
#: 🔴 변수 수 상한 — 한 경기에서 이만큼만(예산)
MAX_ROWS = 4
#: 🔴 자리 변화 문턱 — 이만큼 바뀌면 전략이 바뀐 것으로 보고 묻는다
SWAP_CUT = 3


#: 🔴🔴 **부등호** — 사용자 지시 2026-10-15: *"딥시크는 수비·공격·갈래 등을
#   **부등호 표시**를 해서 **어느 값이 크다**는 것을 변수에 제공해야 한다"*.
#   🔴 비교는 **홈 기준**이다 — `>` 면 홈이 크고 `<` 면 원정이 크다.
OPS: tuple[str, ...] = (">", "<", "=")


class StrategyRow(BaseModel):
    """🔴 전략 비교 한 줄 — **수 칸이 없다**. 모델은 **부등호**만 고른다.

    예) `kind="수비 라인"` · `cmp=">"` → *"홈의 수비 라인이 더 높다"*
        `goals_cmp="<"`              → *"총골이 대회 기준보다 적겠다"*
    🔴 크기(가중)는 **코드가** 넣는다 — 모델은 **어느 쪽이 큰지**만 말한다.
    """

    kind: str = ""
    #: 🔴 홈 vs 원정 — `>`(홈이 크다) · `<`(원정이 크다) · `=`(비슷)
    cmp: str = "="
    #: 🔴 총골 vs 대회 기준 — `>`(많겠다) · `<`(적겠다) · `=`(보통)
    goals_cmp: str = "="
    text: str = ""


class StrategyRead(BaseModel):
    rows: list[StrategyRow] = Field(default_factory=list)


def _facts_of(plan: object) -> dict:
    return dict(getattr(plan, "facts", None) or {})


def may_ask(ref: MatchRef, facts: Facts, plan: object) -> tuple[bool, str]:
    """🔴🔴 **물을 자리인가** — `(묻나, 사유)`. ⚠️ 사유는 카드에 그대로 적힌다.

    🔴🔴 **XI 가 있으면 묻는다** — 사용자 지시 2026-10-16:

      > b2 전략 전문가는 **포메이션에 따른 전술**을 말하는 거다 ·
      > **포메이션 변화가 없다고 해서 분석 자체를 하지 않으면 안 된다**

    ⚠️ 실사고 2026-10-16(Saprissa vs Sporting · 코스타리카): XI 2/2 · 감독
       2/2 를 받았는데 양 팀이 **평소 그대로**라 트리거가 하나도 안 걸려
       `🔴 빈손 — ⬜ 트리거 없음` 으로 끝났다. 그런데 **포메이션은 있었다**
       (양 팀 4-4-2 / 4-2-3-1) — 그 모양 자체가 전술 분석의 재료다.
    🔴 그래서 조건을 뒤집는다: **포메이션이나 XI 가 있으면 돈다.**
       `변화`(핵심 결장·포메이션 바뀜·자리 바뀜)는 이제 **묻는 조건이 아니라
       사유에 적는 맥락**이다(있으면 더 할 말이 있다는 뜻).
    🔴 XI 가 아예 없으면 **안 묻는다**(읽을 판이 없다 — 과테말라·온두라스처럼
       fotmob 이 그 리그에 라인업을 안 주는 경우다).
    """
    xi = dict(getattr(facts, "xi", None) or {})
    if not xi:
        return False, "⬜ XI 가 없다 — 전략 전문가를 안 부른다"
    # 🔴 **포메이션이 선 쪽이 있나** — 한쪽이라도 있으면 분석 대상이다
    said_form = [f"{k} {str(getattr(v, 'formation', '') or '?')}"
                 for k, v in xi.items()
                 if str(getattr(v, "formation", "") or "")]
    box = _facts_of(plan)
    said: list[str] = []
    for one in box.values():
        row = dict(one) if isinstance(one, dict) else {}
        kind = str(row.get("kind") or "")
        text = str(row.get("text") or "")
        val = row.get("value")
        if kind == "key_player" and ("명단 제외" in text or "벤치" in text):
            said.append(f"핵심 선수 빠짐 — {text[:40]}")
        elif kind == "formation" and "→" in text:
            said.append(f"포메이션 바뀜 — {text[:40]}")
        elif kind == "rotation" and isinstance(val, (int, float)):
            if float(val) >= SWAP_CUT:
                said.append(f"바뀐 자리 {float(val):g}개")
    if not said:
        # 🔴 **변화가 없어도 돈다**(위 머리말) — 포메이션 모양으로 전술을 말한다
        if said_form:
            return True, ("포메이션 그대로 — " + " · ".join(said_form[:2])
                          + " (변화 없음 · 모양으로 전술을 읽는다)")
        return True, "⬜ 포메이션 글자는 없다 — XI 자리로 전술을 읽는다"
    return True, " · ".join(said[:3])


#: 🔴🔴 **최근 5경기 재료** — 사용자 지시 2026-10-15: *"갈래도 찾아서 넣어야
#   한다 · **최근 5경기 기준으로**"*. 그 재료를 든 변수 id 머리글자다.
#   ⚠️ 여기서 폼을 다시 세지 않는다 — `s5_verify` 가 센 그 변수를 **그대로** 쓴다.
RECENT_IDS: tuple[str, ...] = ("S01", "S02", "IR12")


def news_of(variables: list | None) -> list[str]:
    """🔴🔴 **기사에서 온 변수 글**(사용자 지시 2026-10-15).

    > 기사 **내용으로 판단**을 해야지 기사 횟수로 하는 건 바보 같은 짓이다

    🔴 확률을 세는 쪽은 이 변수를 **안 센다**(`probmodel.flat_prob`) — 대신
       그 글을 여기로 넘겨 모델이 **한 줄의 부등호**로 정리한다.
    """
    out: list[str] = []
    for one in list(variables or []):
        if not list(getattr(one, "doc_ids", None) or []):
            continue
        rid = str(getattr(one, "id", "") or "")
        out.append(f"- `{rid}` {str(getattr(one, 'claim', '') or '')[:200]}")
    return out


def rest_of(ref: MatchRef, facts: Facts) -> list[str]:
    """🔴🔴 **피로도 재료** — 사용자 지시 2026-10-16.

    > 그 일정이 나오면 LLM 전략분석가가 그 팀의 **피로도**를 변수에 넣게 한다

    🔴 코드가 **센 수만** 넘긴다 — 휴식일(`rest_days`)·직전 경기일·최근 창
       경기 수. ⚠️ 모델이 날짜를 세지 않는다(세면 그 수가 거짓이 된다).
    ⚠️ 못 잰 칸은 **이름으로** 적는다(#3) — `⬜ 휴식일 못 쟀다`.
    """
    out: list[str] = []
    box = dict(getattr(facts, "recent", None) or {})
    sched = dict(getattr(facts, "schedule", None) or {})
    for side in ("home", "away"):
        key = str(getattr(ref, side, "") or "")
        nm = str(getattr(ref, f"{side}_name", "") or "") or side
        one = dict(box.get(key) or {})
        said: list[str] = []
        rest = one.get("rest_days")
        said.append(f"휴식 {rest}일" if rest is not None else "⬜ 휴식일 못 쟀다")
        if one.get("last_match_utc"):
            said.append(f"직전 경기 {str(one['last_match_utc'])[:10]}")
        seq = [x for x in (one.get("sequence") or []) if isinstance(x, dict)]
        if seq:
            said.append(f"최근 {len(seq)}경기 치렀다")
        got_s = dict(sched.get(key) or {})
        if got_s.get("games_14d") is not None:
            said.append(f"14일 {got_s['games_14d']}경기")
        out.append(f"- {side} `{nm}` — " + " · ".join(said))
    return out


def recent_of(variables: list | None) -> list[str]:
    """🔴 최근 5경기·맞대결·연속 기록 변수의 **글**만 추린다(사본 금지)."""
    out: list[str] = []
    for one in list(variables or []):
        rid = str(getattr(one, "id", "") or "")
        if rid.startswith(RECENT_IDS):
            out.append(f"- `{rid}` {str(getattr(one, 'claim', '') or '')[:170]}")
    return out


def _add_branch(box: list | None, kind: str, mode: str, rows: list) -> None:
    """🔴🔴 **충돌·단독 갈래를 판정 거리로 담는다**(사용자 지시 2026-10-16).

    > 충돌되는 것·한쪽만 나오는 것도 **버리는 게 아니라 어느 쪽이 맞는지
    > 확인**해야 한다

    ⚠️ 종전엔 두 모델의 주장이 **글자 한 줄로 뭉쳐져** 남았다 — 읽을 수는
       있어도 **어느 주장을 누가 했는지 기계가 가릴 수 없었다**. 🔴 그래서
       주장을 **쪼갠 꼴**(`Claim`)로 담는다 — 판정은 그 꼴을 쓴다.
    """
    if box is None:
        return
    from app.core import branchjudge as _bj
    box.append(_bj.Branch(
        kind=str(kind or ""), mode=str(mode or ""),
        claims=[_bj.Claim(provider=str(pv),
                          cmp=str(getattr(r, "cmp", "=") or "="),
                          goals_cmp=str(getattr(r, "goals_cmp", "=") or "="),
                          text=str(getattr(r, "text", "") or ""))
                for pv, r in rows]))


def ask(ref: MatchRef, facts: Facts, plan: object, *, state: RunState,
        recent: list[str] | None = None, news: list[str] | None = None,
        rest: list[str] | None = None,
        # 🔴🔴 **선수 능력치**(사용자 지시 2026-10-17) — *"핵심선수 결장 ·
        #    후보선수로 대체했을때 가설제공(**숫자가 아닌 능력치**)"*.
        #    ⚠️ 글자뿐이다(`강점/보통/약점`) — 수는 `core/ability` 에서 멈춘다.
        ability: list[str] | None = None,
        # 🔴 **둘 다 쓴다**(사용자 지시 2026-10-16) — 먼저 성공한 하나가
        #    아니라 **같은 묶음으로 둘 다 묻고 대본다**(아래 머리말).
        providers: tuple = ("deepseek", "solar"),
        # 🔴🔴 **갈래를 여기 담는다**(사용자 지시 2026-10-16 · 판정 절차)
        #    ⚠️ 목록을 주면 충돌·단독 갈래가 `branchjudge.Branch` 로 쌓인다 —
        #       그것을 **다른 모델이 서치해서 판정**한다(`core/branchjudge`).
        #    🔴 안 주면 종전과 똑같이 돈다(맥락 전용으로 남는다).
        branches: list | None = None) -> tuple[list[Variable], str]:
    """🔴 전략 전문가에게 **변수 글**을 받는다. `(변수 목록, 사유)`.

    ⚠️ 실패해도 예외를 안 던진다 — 빈 목록 + 사유다(카드는 항상 나온다).
    🔴 `branches` 를 주면 **충돌·단독 갈래**를 그 목록에 담는다 — 판정은
       `core/branchjudge.run` 이 한다(여기서 판정하지 않는다 · 검색이 든다).
    """
    from app.core import llm
    ok, why = may_ask(ref, facts, plan)
    if not ok:
        return [], why
    box = _facts_of(plan)
    said_facts = "\n".join(
        f"- `{rid}` {dict(one).get('text', '')}"
        for rid, one in list(box.items())[:16] if isinstance(one, dict))
    xi = dict(getattr(facts, "xi", None) or {})
    said_recent = "\n".join(list(recent or [])[:8])
    said_news = "\n".join(list(news or [])[:10])
    #: 🔴 **피로도 재료**(사용자 지시 2026-10-16) — `rest_of` 가 센 수다
    said_rest = "\n".join(list(rest or [])[:4])
    #: 🔴🔴 **능력치 재료**(사용자 지시 2026-10-17) — `core/ability` 가 만든 글자
    said_ability = "\n".join(list(ability or [])[:12])
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **라인업을 자리별로 보여 준다** — 사용자 지시 2026-10-16
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 기존 라인업에서 **큰 변화를 준 의도**를 전력분석가가 예측해야 한다 …
    #  > **상대방 라인업과 정밀 비교**해야 한다
    #
    #  ⚠️ 실측 2026-10-16: 이 자리는 **포메이션 글자만** 넘겼다(`4-4-2`) —
    #     선수도 자리도 없으니 *"누가 어디서 누구와 맞붙나"* 를 쓸 재료가
    #     **아예 없었다**. 그래서 평이 늘 *"중원 숫자"* 수준에 머물렀다.
    #  🔴 그래서 **자리(라인)별로 묶어** 선수 이름을 적는다 — 재료는 이미
    #     받는 `xi.players`(이름·포지션·등번호)다.
    def _rows(side: str) -> str:
        one = xi.get(str(getattr(ref, side, "") or ""))
        # ══════════════════════════════════════════════════════════
        # 🔴🔴 **자리는 `lineup` 에 있다** — 실측 2026-10-17
        # ══════════════════════════════════════════════════════════
        #
        #  ⚠️ 실사고: 여기서 `xi.players` 를 읽었는데 그 칸은 **이름 글자
        #     목록**(`list[str]`)이다(`core/adapt.py` 가 그렇게 싣는다).
        #     그래서 `getattr(pl, "pos")` 가 **늘 빈 글자**였고 프롬프트에
        #     `? 이름, 이름, …` 한 덩어리가 갔다 — SL13 이 넘기려던
        #     **자리·측면이 하나도 안 갔다**(어제 §4 그 병: 남겼는데 못 읽는다).
        #  🔴 자리·측면·등번호가 든 칸은 **`lineup`**(`list[Player]`)이다.
        #  ⚠️ `lineup` 이 비면(이름만 받은 출처) 그 사실을 적고 이름만 낸다 —
        #     `?` 로 때우지 않는다(#3).
        got = list(getattr(one, "lineup", None) or [])
        if not got:
            said_names = [str(x) for x in (getattr(one, "players", None) or [])]
            if said_names:
                return ("⬜ 자리 글자 없음(이름만 받았다) — "
                        + ", ".join(said_names[:11]))
            return "⬜ XI 없음"
        box: dict[str, list[str]] = {}
        for pl in got:
            # 🔴 자리 글자는 `pos`(GK·CB·CM…) · 측면은 `flank`(L/R) 가 든다
            said_p = str(getattr(pl, "pos", "") or "?")
            said_f = str(getattr(pl, "flank", "") or "")
            said_n = str(getattr(pl, "name", "") or "?")
            num = str(getattr(pl, "number", "") or "")
            box.setdefault(said_p, []).append(
                said_n + (f"({said_f})" if said_f else "")
                + (f"[{num}]" if num else ""))
        return " · ".join(f"{k} {', '.join(v)}" for k, v in box.items())

    said_xi = "\n".join(
        f"- {str(getattr(ref, f'{s}_name', '') or '')} "
        f"[{getattr(xi.get(str(getattr(ref, s, '') or '')), 'formation', '') or '⬜'}]"
        f" — {_rows(s)}"
        for s in ("home", "away"))
    msgs = [
        llm.Message(role="system", content=(
            "너는 **축구 전술 분석 전문가**다. 아래는 오늘 라인업·포메이션·결장이 "
            "만든 **사실 목록**이다. 네 일은 그 사실을 보고 **두 팀을 견주는 "
            "것**이다 — 어느 쪽 값이 큰지 **부등호로만** 말한다.\n"
            "🔴 **수를 쓰지 마라**(퍼센트·골 수·배율 금지). 크기는 코드가 넣는다.\n"
            "🔴 **사실 목록에 없는 선수·사건을 지어내지 마라.** 모르면 `=` 다.")),
        llm.Message(role="user", content=(
            f"경기: {getattr(ref, 'home_name', '')}(홈) vs "
            f"{getattr(ref, 'away_name', '')}(원정) · "
            f"{getattr(ref, 'competition', '')}\n"
            # 🔴 **그 경기에 맞게 본다**(지시 2026-10-15 · 사본 금지)
            + __import__("app.core.querywriter",
                         fromlist=["x"]).comp_hint(ref)
            + f"포메이션:\n{said_xi}\n"
            f"오늘 라인업 사실:\n{said_facts}\n"
            # 🔴 **최근 5경기 기준**으로도 갈래를 찾는다(지시 2026-10-15)
            + (f"\n최근 5경기·맞대결 재료:\n{said_recent}\n" if said_recent
               else "\n최근 5경기 재료: ⬜ 없다\n")
            # 🔴🔴 **피로도**(사용자 지시 2026-10-16) — 일정 재료를 준다
            + (f"\n일정·피로도 재료(코드가 셌다):\n{said_rest}\n"
               if said_rest else "")
            # ══════════════════════════════════════════════════════
            # 🔴🔴 **선수 능력치**(사용자 지시 2026-10-17)
            # ══════════════════════════════════════════════════════
            #
            #  > 핵심선수 결장 · **후보선수로 대체했을때 가설제공(숫자가 아닌
            #  > 능력치)** … 이거는 전략분석가한테 줘야 하는거다
            #
            #  🔴 재료는 fotmob 선수 페이지의 **자리별 백분위**이고(출처가 비교
            #     묶음을 고른다) 코드가 그것을 `강점/보통/약점` 으로 옮겼다.
            #  ⚠️ 종전엔 이 재료가 **아예 없었다** — 그래서 모델이 대체 선수를
            #     *"가치가 낮다"* 수준으로만 말했다(경합·수비 지표가 선수단
            #     페이지에 없다 · 실측 2026-10-10).
            + (f"\n선수 능력치(자리별 비교 · 코드가 등급을 냈다):\n"
               f"{said_ability}\n" if said_ability else "")
            + (f"\n기사에서 나온 사실({len(list(news or []))}줄):\n{said_news}\n"
               if said_news else "\n기사에서 나온 사실: ⬜ 없다\n")
            # ══════════════════════════════════════════════════════
            # 🔴🔴 **포메이션 모양 자체를 읽는다** — 사용자 지시 2026-10-16
            # ══════════════════════════════════════════════════════
            #
            #  > b2 전략 전문가는 **포메이션에 따른 전술**을 말하는 거다 ·
            #  > **포메이션 변화가 없다고 분석 자체를 하지 않으면 안 된다**
            #
            #  ⚠️ 실사고 2026-10-16(Saprissa 4-4-2 vs Sporting 4-2-3-1):
            #     변화가 없어 아예 안 불렀다 — 그런데 **그 두 모양이 맞붙는
            #     것** 자체가 전술 재료다(중원 숫자·측면·전방 압박 높이).
            # ══════════════════════════════════════════════════════
            # 🔴🔴 **변화의 의도 + 상대와 정밀 비교** — 사용자 지시 2026-10-16
            # ══════════════════════════════════════════════════════
            #
            #  > 기존 라인업에서 **큰 변화를 준 의도**를 전력분석가가 예측해야
            #  > 한다 · 왜 이렇게 라인업과 포메이션을 줬는지 · **상대방 라인업과
            #  > 정밀 비교**해야 한다 · 프롬프트가 **더 정밀해야** 한다
            #
            #  ⚠️ 종전 프롬프트는 *"중원 숫자·측면 폭"* 수준이었고 재료도
            #     포메이션 글자뿐이었다 — 그래서 평이 늘 같은 말을 했다.
            #  🔴 이제 자리별 선수(위 `라인업`)가 가므로 **맞물림**을 묻는다.
            + "\n🔴🔴 **① 왜 이렇게 냈나(의도)를 먼저 읽는다** — `바뀐 자리`·"
              "`ΔA·ΔD`·`전력 누수`·`일정·피로도`·`순위 동기` 를 근거로 **감독이 "
              "무엇을 노렸나**를 한 줄로 짚는다(보기: *로테이션으로 체력을 "
              "아꼈다* · *상대 측면을 지우려 5백을 세웠다* · *결장을 메우려 "
              "자리를 옮겼다* · *이겨야 해서 전방을 늘렸다*). ⚠️ 재료에 없는 "
              "이유(부상설·감독 발언 등)를 **지어내지 마라**.\n"
            + "🔴🔴 **② 상대 라인업과 자리별로 맞붙여 본다** — 위 `라인업` 의 "
              "**선수 이름·자리(GK/DF/MF/FW)·측면(왼·중앙·오른)** 을 써서 "
              "**누가 누구와 부딪히나**를 적는다(보기: *홈 오른 DF ↔ 원정 왼 "
              "FW*). 숫자가 겹치는 자리(중원 3 대 2 등)와 **비는 자리**를 "
              "짚고, 그것이 어느 갈래(`측면 집중`·`중원 수싸움`·`압박 높이`·"
              "`수비 라인`)의 부등호로 이어지는지 말한다.\n"
            + "🔴 **③ 두 포메이션이 맞붙는 모양** — 변화가 "
              "없어도 분석한다. 중원 숫자(예 4-4-2 의 2 vs 4-2-3-1 의 3), "
              "측면 폭, 전방 숫자, 수비 라인 높이를 비교해 **어느 쪽이 어디서 "
              "우세한지** 갈래로 적는다(`중원 수싸움`·`측면 집중`·`압박 높이`· "
              "`수비 라인`).\n"
            + "🔴 갈래는 **오늘 라인업 · 최근 5경기 · 기사 사실** 셋에서 "
              "찾는다 — 재료에 없는 갈래는 내지 마라.\n"
            # ══════════════════════════════════════════════════════════
            # 🔴🔴 **득실점으로 판단해라** — 사용자 지시 2026-10-15
            # ══════════════════════════════════════════════════════════
            #
            #  ⚠️ 실측: 재료(`S01` 최근 5경기 득점·실점 평균)를 **넘겼는데도**
            #     모델이 그것을 쓸 때도 있고 안 쓸 때도 있었다 — 어떤 실행은
            #     수비 라인을 **선수 이탈만** 보고 판단했다(실점 3.2 ↔ 0.8 을
            #     안 들었다).
            + "🔴🔴 **최근 5경기 득점·실점 평균을 반드시 근거로 삼는다**\n"
              "   · **실점** 평균이 높은 쪽 = **수비 불안** → `수비 라인`·"
              "`압박 높이` 갈래로 읽는다\n"
              "   · **득점** 평균이 기준보다 높은 쪽 = **공격력** → `역습 성향`·"
              "`측면 집중`·`빌드업` 갈래로 읽는다\n"
              "   ⚠️ 라인업 이탈만 보고 수비를 판단하지 마라 — **그 팀이 실제로 "
              "얼마나 먹혔나**(실점 평균)가 더 센 증거다.\n"
            # 🔴🔴 **피로도를 갈래로 적는다** — 사용자 지시 2026-10-16
            #  ⚠️ 그 재료는 위 `일정·피로도 재료` 줄이다(코드가 셌다) —
            #     모델이 날짜를 세지 않는다.
            # ══════════════════════════════════════════════════════
            # 🔴🔴 **능력치로 대체 가설을 세운다** — 사용자 지시 2026-10-17
            # ══════════════════════════════════════════════════════
            + "🔴🔴 **빠진 선수 ↔ 들어온 선수의 능력치를 견준다** — 위 `선수 "
              "능력치` 칸을 읽고 **그 자리가 세졌나 약해졌나**를 갈래의 "
              "부등호로 잇는다(`수비 라인`·`측면 집중`·`중원 수싸움`·"
              "`압박 높이`·`세트피스`).\n"
              "   · 같은 자리인데 **유형이 다르면** 그것을 말한다(보기: 공중볼 "
              "**강점**이 빠지고 찬스 창출 **강점**이 들어왔다 → 제공권이 줄고 "
              "연결이 늘었다 → `세트피스` 는 내려가고 `빌드업` 은 올라간다).\n"
              "   · ⚠️ **비교 묶음이 다른 선수를 나란히 세우지 마라** — 골키퍼와 "
              "윙은 **다른 지표**로 재므로 *누가 더 세다*고 말할 수 없다.\n"
              "   · ⚠️ `⬜ 능력치 없음` 인 선수에 대해 **능력을 지어내지 마라** — "
              "그 선수는 그 갈래의 근거로 쓰지 않는다.\n"
              "   · 🔴 **수를 쓰지 마라**(백분위·퍼센트 금지) — 네가 받은 것은 "
              "`강점/보통/약점` 글자뿐이고 그 글자로만 말한다.\n"
            + "🔴🔴 **일정·피로도**를 한 갈래로 적는다 — 위 `일정·피로도 재료` "
              "의 **휴식일·직전 경기일·최근 경기 수**를 견줘 **어느 쪽이 더 "
              "지쳤나**를 부등호로 낸다(`일정·피로도` 갈래). ⚠️ 휴식일이 **짧은 "
              "쪽이 불리**하다 — 그 쪽을 `cmp` 에서 작은 쪽으로 둔다. 재료가 "
              "`⬜ 못 쟀다` 면 그 갈래를 **내지 마라**.\n"
            + "🔴🔴 **기사는 줄 수로 세지 마라** — 같은 이야기가 여러 줄로 쪼개져 "
              "있다. **내용을 읽어** 그 경기에 무엇을 뜻하는지 판단하고 "
              "`기사 사실` 갈래 **한 줄**로 정리한다(여러 줄 금지).\n"
            + f"🔴 `rows` — **{MAX_ROWS}개 이하**. 한 줄은 한 갈래의 **비교**다:\n"
            f"  · `kind` — 다음 중 하나: {' · '.join(KINDS)}\n"
            "  · `cmp` — **홈 vs 원정**: `>`(홈이 크다) · `<`(원정이 크다) · "
            "`=`(비슷·모름)\n"
            "  · `goals_cmp` — **이 경기 총골 vs 대회 기준**: `>`(많겠다) · "
            "`<`(적겠다) · `=`(보통·모름)\n"
            "  · `text` — **한 문장**(80자 안). 위 사실의 선수 이름·포메이션을 "
            "근거로 든다.\n"
            "⚠️ 근거가 없으면 그 줄을 **내지 마라**(`=` 만 가득한 줄은 쓸모없다).")),
    ]
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **둘 다 묻는다 — 한쪽에 치우치지 않는다**(사용자 지시 2026-10-16)
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 전략분석을 deepseek 하나만 하는데 **solar 도 투입해라** · 하나에
    #  > **치우치면 안 된다**
    #
    #  🔴 종전엔 `ask_first` 로 **먼저 성공한 하나**만 썼다(사실상 deepseek).
    #  🔴 이제 **같은 묶음**으로 둘 다 묻고 **대본다** — ⑯ 평에서 두 모델을
    #     견주는 그 규율과 같다.
    #    · 같은 갈래에 **같은 부등호** → 합의다. 그대로 쓴다(`🤝 둘 다`).
    #    · 같은 갈래에 **다른 부등호** → 🔴 **충돌**이다. 같은 재료로 반대
    #      결론이면 믿을 수 없으므로 **맥락 전용으로 내린다**(확률에 안 닿는다).
    #    · 한쪽만 낸 갈래 → 쓰되 **어느 모델인지** 적는다(표본 하나다).
    said_rows: dict[str, list] = {}
    said_ok: list[str] = []
    for pv in providers:
        one = llm.ask(provider=pv, purpose="recall", messages=msgs,
                      out=StrategyRead, state=state)
        if not isinstance(one, StrategyRead):
            state.note(f"⑤-b2 `{pv}` 실패 — {getattr(one, 'reason', '?')}")
            continue
        said_ok.append(pv)
        for row in list(one.rows or []):
            said_rows.setdefault(str(getattr(row, "kind", "") or ""),
                                 []).append((pv, row))
    if not said_ok:
        return [], f"🔴 전략 전문가 실패(둘 다) — 변수 0개"
    keep, said_note = [], []
    for kind, rows in said_rows.items():
        if len(rows) == 1:
            # 🔴 **합의가 아니다** — 다른 모델은 동의한 게 아니라 **안 본**
            #    것이다. 확률에 안 닿게 내린다(위 `ALONE` 머리말).
            pv, row = rows[0]
            # 🔴 **담는 것이 먼저다** — 아래에서 글에 꼬리표를 박으므로, 뒤에
            #    담으면 주장 글이 **꼬리표째** 들어간다(위 충돌 자리의 그 함정).
            _add_branch(branches, kind, "단독", rows)
            row.text = f"{ALONE} [{pv}] {row.text}"
            keep.append(row)
            continue
        cmps = {str(getattr(r, "cmp", "=")) for _pv, r in rows}
        pv0, row0 = rows[0]
        if len(cmps) == 1:
            row0.text = ("[🤝 " + "·".join(p for p, _r in rows) + " 합의] "
                         + row0.text)
            keep.append(row0)
        else:
            # 🔴 **충돌** — 글은 남기되 부등호를 `=`(모름)으로 내린다
            #    ⚠️ 꼬리표를 **먼저** 만든다 — 값을 바꾼 뒤 읽으면 제 값이
            #       아니라 바뀐 `=` 가 찍힌다(실측 2026-10-16).
            # ══════════════════════════════════════════════════════
            # 🔴🔴 **양쪽 글을 다 남긴다** — 사용자 지시 2026-10-16
            # ══════════════════════════════════════════════════════
            #
            #  ⚠️ 실사고(Necaxa vs Atlas): 충돌 줄에 **deepseek 문장만** 남고
            #     solar 는 부등호 한 글자(`<`)로만 남았다 — *"solar 는 왜
            #     반대로 봤나"* 를 **읽을 수 없었다**(어제 안전장치 사유가
            #     잘려 못 읽던 것과 같은 병이다).
            #  🔴 그래서 **두 모델의 문장을 모두** 싣는다.
            said_tag = " ↔ ".join(
                f"{p} `{getattr(r, 'cmp', '=')}` {str(getattr(r, 'text', '') or '')[:90]}"
                for p, r in rows)
            # 🔴 부등호는 **그대로 둔다** — `=` 로 바꾸면 `vars_of` 가 그 줄을
            #    **통째로 버려** 정보가 사라진다(실측 2026-10-16: 변수 0개).
            #    🔴 대신 글에 충돌 표시를 박고, 아래에서 **맥락 전용**으로 내린다.
            # 🔴 **담는 것이 먼저다** — `row0.text` 를 바로 아래에서 덮으므로
            #    뒤에 담으면 deepseek 주장 글이 **충돌 꼬리표**로 바뀐다
            #    (실측 전에 막는다 · 바로 위 `said_tag` 주석의 그 병).
            _add_branch(branches, kind, "충돌", rows)
            row0.text = f"{CONFLICT} — {said_tag}"
            keep.append(row0)
            said_note.append(kind)
    got = StrategyRead(rows=keep[:MAX_ROWS])
    out = vars_of(got, ref, why=why)
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **변수가 안 선 갈래는 판정하지 않는다** — 예산
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ `keep[:MAX_ROWS]` 가 줄을 자르고 `vars_of` 가 표에 없는 갈래·부등호를
    #     버린다. 🔴 그렇게 **변수가 안 선 갈래**를 판정하면 검색·LLM 을 쓰고도
    #     되먹일 자리가 없다(상한이 더 급한 갈래를 밀어낸다).
    #  🔴 그래서 담은 갈래를 **선 변수에 맞춰 깎는다** — 깎은 수는 사유에 남는다.
    said_cut = 0
    if branches is not None:
        said_t = {str(getattr(v, "target", "") or "") for v in out}
        keep_b = [b for b in branches if b.target in said_t]
        said_cut = len(branches) - len(keep_b)
        branches[:] = keep_b
    said_pv = ((f"🔴 변수 안 선 갈래 {said_cut}개는 판정 안 한다 · "
                if said_cut else "")
               + "+".join(said_ok)) + (f" · 🔴 충돌 {len(said_note)}갈래"
                                   f"({' · '.join(said_note[:2])})"
                                   if said_note else " · 충돌 없다")
    logger.info("[전략LLM] %s · 변수 %d개", said_pv, len(out))
    return out, f"{why} → {said_pv} · 변수 {len(out)}개"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **방향 표** — 사용자 지시 2026-10-15
# ══════════════════════════════════════════════════════════════════
#
#  > 예: 수비 라인 낮음 → 총골 down, 압박 높이 낮음 → 상대 유리
#  > **딥서치해서 넣어라**
#
#  🔴 그래서 방향은 **표가 정한다** — 모델은 갈래와 글만 낸다(절대규칙 5 그대로).
#  🔴 표를 채우는 곳은 `tools/fit_strategy_dirs.py` 하나다(딥서치 → 문서 인용).
#  ⚠️ 표가 없거나 그 갈래가 비어 있으면 **방향 없음**이다(both/none) —
#     지어내지 않는다(#4). 카드에는 그 사실이 그대로 적힌다.
DIRS_FILE = "config/strategy_dirs.yaml"
_DIRS: dict | None = None


def dirs() -> dict:
    """🔴 갈래 → `{goals, favors, url, quote}`. 파일이 없으면 **빈 표**다."""
    global _DIRS
    if _DIRS is None:
        import pathlib

        import yaml
        p = pathlib.Path(DIRS_FILE)
        if not p.exists():
            _DIRS = {}
        else:
            box = dict(yaml.safe_load(p.read_text(encoding="utf-8")) or {})
            _DIRS = dict(box.get("rows") or {})
    return dict(_DIRS)


#: 🔴🔴 **승인 전에는 안 쓴다** — 사용자 지시 2026-10-15(값 승인은 사용자 몫).
#   ⚠️ 실측 2026-10-15(1차 딥서치): 여덟 갈래가 다 채워졌는데 근거가
#      **미식축구 기사**(UVA defensive line)·한 팀 일화(아스널 코너 19골)·
#      위키 정의문이었고 `favors` 가 **전부 `subject`** 로 기울었다.
#      🔴 그런 표로 방향을 넣으면 확률이 거짓이 된다 — 그래서 **잠근다**.
#   🔴 켜는 법: 그 줄에 `approved: true` 를 **사용자가** 적는다.
def approved(row: dict) -> bool:
    return bool(row.get("approved"))


def _dir_of(kind: str, side: str, level: str = "") -> tuple[str, str, str]:
    """🔴 `갈래|정도` 의 `(favors, goals, 근거 꼬리)`. 표에 없거나 **승인 전**이면
    방향 없음이다."""
    key = f"{kind}|{level}" if level else kind
    row = dict(dirs().get(key) or dirs().get(kind) or {})
    if row and not approved(row):
        return "both", "none", f" · ⬜ 방향 표 **승인 전**({key})"
    goals = str(row.get("goals") or "none")
    said = str(row.get("favors") or "both")
    # 🔴 표는 **`subject`/`opponent`** 로 적는다 — 쪽으로 옮기는 것은 코드다
    other = "away" if side == "home" else "home"
    fav = {"subject": side, "opponent": other}.get(said, "both")
    tail = ""
    if row.get("url"):
        tail = f" · 근거 {str(row.get('url'))[:60]}"
    elif goals == "none" and fav == "both":
        tail = " · ⬜ 방향 표 없음(표시만)"
    return (fav if fav in ("home", "away", "both") else "both",
            goals if goals in ("up", "down", "none") else "none", tail)


def _weight() -> float:
    """🔴 가중은 **규칙 변수와 같은 자**다 — 여기서 새 수를 짓지 않는다(#1).

    `s5_verify._sample_weight(5)` 가 표본 5건짜리 규칙 변수에 주는 그 값이다.
    """
    from app.core.stages import s5_verify as _s5
    return float(_s5._sample_weight(5)[1])


def dir_of_cmp(op: str, gop: str) -> tuple[str, str]:
    """🔴🔴 **부등호 → 방향**(`favors`, `goals`). 이 표가 **하나**다.

    🔴 왜 함수로 빼나 — **갈래 판정**(`core/branchjudge`)이 채택한 부등호를
       같은 표로 방향으로 옮겨야 한다. 두 자리에 적으면 한쪽이 늦게 바뀐다
       (#1 사본 금지).
    🔴 `>` 면 홈이 큰 갈래다 → 홈 유리 · `goals_cmp` `<` 면 총골 down.
    """
    fav = {">": "home", "<": "away"}.get(str(op or "").strip(), "both")
    goals = {">": "up", "<": "down"}.get(str(gop or "").strip(), "none")
    return fav, goals


def vars_of(got: StrategyRead, ref: MatchRef, *, why: str = "") -> list[Variable]:
    """🔴🔴 **부등호 → 변수**. 방향은 부등호가, **가중은 코드가** 넣는다.

    🔴 `cmp` 가 `>` 면 홈이 큰 갈래다 → 그 갈래에서 **홈 유리**(`favors=home`).
    🔴 `goals_cmp` 가 `<` 면 **총골 down** 이다.
    ⚠️ 둘 다 `=` 인 줄은 **안 쓴다**(방향이 없으면 변수 구실을 못 한다).
    🔴 표(`config/strategy_dirs.yaml`)에 **승인된 줄**이 있으면 그 표가 이긴다 —
       사람이 정한 값이 모델 판단보다 위다.
    """
    out: list[Variable] = []
    for i, row in enumerate(list(got.rows or [])[:MAX_ROWS], 1):
        kind = str(row.kind or "").strip()
        text = str(row.text or "").strip()
        op = str(row.cmp or "=").strip()
        gop = str(row.goals_cmp or "=").strip()
        if not text or kind not in KINDS or op not in OPS or gop not in OPS:
            continue              # 🔴 표에 없는 갈래·부등호는 **버린다**
        fav, goals = dir_of_cmp(op, gop)
        if fav == "both" and goals == "none":
            continue              # ⚠️ `=`·`=` 는 변수가 아니다
        # 🔴🔴 **모델이 갈린 갈래는 확률에 안 닿는다**(사용자 지시 2026-10-16)
        #    ⚠️ 같은 재료로 반대 결론이면 믿을 수 없다. 그래도 **버리지 않고**
        #       맥락 전용으로 남긴다 — 평이 *"두 모델이 갈렸다"* 를 읽어야 한다.
        said_conf = (CONFLICT in text) or (ALONE in text)
        side = fav if fav in ("home", "away") else "home"
        tail = f" [{kind} 홈{op}원정 · 총골{gop}기준]"
        # 🔴 승인된 표가 있으면 **그 표가 이긴다**(사람이 정한 값이 위다)
        said_tbl = dict(dirs().get(kind) or {})
        if said_tbl and approved(said_tbl):
            fav2, goals2, tail2 = _dir_of(kind, side)
            fav, goals, tail = fav2, goals2, tail2 + " · 표가 덮었다"
        out.append(Variable(
            id=f"SL{i}", type=VAR_TYPE,
            subject=str(getattr(ref, side, "") or ""),
            favors=fav, goals=goals,                        # type: ignore[arg-type]
            target=f"strategy:{kind}", hardness="soft",
            # 🔴 가중은 **규칙 변수와 같은 자**다(여기서 새 수를 짓지 않는다)
            weight=_weight(),
            # 🔴 충돌 줄은 **근거 불가**(맥락 전용) — 확률 자리에 못 간다
            usable_as_basis=not said_conf,
            claim=f"🟢 전략 비교(LLM · {kind}) — {text}{tail}",
            quote=text, doc_ids=[], from_rule="SLLM"))
    return out
