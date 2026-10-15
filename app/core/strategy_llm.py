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
  ③ **트리거가 있어야 부른다** — 핵심 선수가 빠졌거나 포메이션이 바뀌었거나
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
KINDS: tuple[str, ...] = (
    "압박 높이", "수비 라인", "빌드업", "측면 집중", "중원 수싸움",
    "역습 성향", "세트피스", "교체 운용",
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

    묻는 조건(하나라도):
      ① 핵심 선수가 **명단 제외·벤치**다
      ② 포메이션이 **바뀌었다**
      ③ 평소 XI 대비 **바뀐 자리 ≥ `SWAP_CUT`**
    🔴 XI 가 아예 없으면 **안 묻는다**(읽을 판이 없다).
    """
    xi = dict(getattr(facts, "xi", None) or {})
    if not xi:
        return False, "⬜ XI 가 없다 — 전략 전문가를 안 부른다"
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
        return False, ("⬜ 트리거 없음(핵심 결장·포메이션 변화·자리 변화 모두 "
                       "아니다)")
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


def recent_of(variables: list | None) -> list[str]:
    """🔴 최근 5경기·맞대결·연속 기록 변수의 **글**만 추린다(사본 금지)."""
    out: list[str] = []
    for one in list(variables or []):
        rid = str(getattr(one, "id", "") or "")
        if rid.startswith(RECENT_IDS):
            out.append(f"- `{rid}` {str(getattr(one, 'claim', '') or '')[:170]}")
    return out


def ask(ref: MatchRef, facts: Facts, plan: object, *, state: RunState,
        recent: list[str] | None = None, news: list[str] | None = None,
        providers: tuple = ("deepseek", "solar")) -> tuple[list[Variable], str]:
    """🔴 전략 전문가에게 **변수 글**을 받는다. `(변수 목록, 사유)`.

    ⚠️ 실패해도 예외를 안 던진다 — 빈 목록 + 사유다(카드는 항상 나온다).
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
    said_xi = "\n".join(
        f"- {str(getattr(ref, f'{s}_name', '') or '')}: "
        f"{getattr(xi.get(str(getattr(ref, s, '') or '')), 'formation', '') or '⬜'}"
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
            f"{getattr(ref, 'away_name', '')}(원정)\n"
            f"포메이션:\n{said_xi}\n"
            f"오늘 라인업 사실:\n{said_facts}\n"
            # 🔴 **최근 5경기 기준**으로도 갈래를 찾는다(지시 2026-10-15)
            + (f"\n최근 5경기·맞대결 재료:\n{said_recent}\n" if said_recent
               else "\n최근 5경기 재료: ⬜ 없다\n")
            + (f"\n기사에서 나온 사실({len(list(news or []))}줄):\n{said_news}\n"
               if said_news else "\n기사에서 나온 사실: ⬜ 없다\n")
            + "\n🔴 갈래는 **오늘 라인업 · 최근 5경기 · 기사 사실** 셋에서 "
              "찾는다 — 재료에 없는 갈래는 내지 마라.\n"
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
    got, said_pv = llm.ask_first(purpose="recall", messages=msgs,
                                 out=StrategyRead, state=state,
                                 providers=providers)
    if not isinstance(got, StrategyRead):
        return [], f"🔴 전략 전문가 실패({said_pv}) — 변수 0개"
    out = vars_of(got, ref, why=why)
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
        fav = {">": "home", "<": "away"}.get(op, "both")
        goals = {">": "up", "<": "down"}.get(gop, "none")
        if fav == "both" and goals == "none":
            continue              # ⚠️ `=`·`=` 는 변수가 아니다
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
            claim=f"🟢 전략 비교(LLM · {kind}) — {text}{tail}",
            quote=text, doc_ids=[], from_rule="SLLM",
            usable_as_basis=True))
    return out
