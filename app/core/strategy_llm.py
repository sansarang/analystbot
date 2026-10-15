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
)
#: 🔴 배치표가 아는 유형으로 **코드가** 적는다(축2 — 스타일 조정·전략 판정)
VAR_TYPE = "lineup_intent"
#: 🔴 변수 수 상한 — 한 경기에서 이만큼만(예산)
MAX_ROWS = 4
#: 🔴 자리 변화 문턱 — 이만큼 바뀌면 전략이 바뀐 것으로 보고 묻는다
SWAP_CUT = 3


class StrategyRow(BaseModel):
    """🔴 전략 읽기 한 줄 — **수 칸이 없다**(모델이 수를 적을 자리가 없다)."""

    side: str = ""
    kind: str = ""
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
        return False, "⬜ 트리거 없음(핵심 결장·포메이션 변화·자리 변화 모두 아니다)"
    return True, " · ".join(said[:3])


def ask(ref: MatchRef, facts: Facts, plan: object, *, state: RunState,
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
    said_xi = "\n".join(
        f"- {str(getattr(ref, f'{s}_name', '') or '')}: "
        f"{getattr(xi.get(str(getattr(ref, s, '') or '')), 'formation', '') or '⬜'}"
        for s in ("home", "away"))
    msgs = [
        llm.Message(role="system", content=(
            "너는 **축구 전술 분석 전문가**다. 아래는 오늘 라인업·포메이션·결장이 "
            "만든 **사실 목록**이다. 네 일은 그 사실에서 **무엇이 달라지는지** "
            "한 줄씩 읽어 주는 것이다.\n"
            "🔴 **수를 쓰지 마라** — 확률·골 수·배율·퍼센트를 적지 않는다. "
            "어느 쪽이 유리한지도 **네가 정하지 않는다**(코드가 정한다).\n"
            "🔴 **사실 목록에 없는 선수·사건을 지어내지 마라.**")),
        llm.Message(role="user", content=(
            f"경기: {getattr(ref, 'home_name', '')} vs "
            f"{getattr(ref, 'away_name', '')}\n"
            f"포메이션:\n{said_xi}\n"
            f"오늘 라인업 사실:\n{said_facts}\n\n"
            f"🔴 `rows` — **{MAX_ROWS}개 이하**. 각 줄은\n"
            "  · `side` — `home` 또는 `away`(그 읽기가 어느 팀 것인가)\n"
            f"  · `kind` — 다음 중 하나: {' · '.join(KINDS)}\n"
            "  · `text` — **한 문장**(80자 안). 위 사실의 선수 이름·포메이션을 "
            "근거로 든다.\n"
            "⚠️ 사실이 얇으면 줄을 **적게** 낸다(빈 목록도 된다 · 지어내지 않는다).")),
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


def _dir_of(kind: str, side: str) -> tuple[str, str, str]:
    """🔴 그 갈래의 `(favors, goals, 근거 꼬리)`. 표에 없거나 **승인 전**이면
    방향 없음이다."""
    row = dict(dirs().get(kind) or {})
    if row and not approved(row):
        return "both", "none", f" · ⬜ 방향 표 **승인 전**({kind})"
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


def vars_of(got: StrategyRead, ref: MatchRef, *, why: str = "") -> list[Variable]:
    """🔴🔴 모델 글 → `Variable`. **방향·가중은 코드가 넣는다**(잠금 ①②).

    🔴 방향은 **표**(`config/strategy_dirs.yaml`)가 준다 — 모델이 아니다.
    """
    out: list[Variable] = []
    for i, row in enumerate(list(got.rows or [])[:MAX_ROWS], 1):
        side = str(row.side or "").strip().lower()
        if side not in ("home", "away"):
            continue
        kind = str(row.kind or "").strip()
        text = str(row.text or "").strip()
        if not text or kind not in KINDS:
            continue              # 🔴 표에 없는 갈래는 **버린다**(지어내기 금지)
        key = str(getattr(ref, side, "") or "")
        # 🔴🔴 **방향은 표가 준다** — 모델 글이 이 두 칸에 닿지 않는다
        fav, goals, tail = _dir_of(kind, side)
        out.append(Variable(
            id=f"SL{i}-{side}", type=VAR_TYPE, subject=key,
            favors=fav, goals=goals,                        # type: ignore[arg-type]
            target=f"strategy:{kind}", hardness="soft", weight=0.0,
            claim=f"🟡 전략 읽기(LLM · {kind}) — {text}{tail}",
            quote=text, doc_ids=[], from_rule="SLLM",
            usable_as_basis=False))
    return out
