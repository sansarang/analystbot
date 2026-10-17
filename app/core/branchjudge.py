"""🔴🔴 **충돌·단독 갈래를 옳다/그르다로 판정한다** — 사용자 지시 2026-10-16.

> 충돌되는 것·한쪽만 나오는 것도 **버리는 게 아니라 어느 쪽이 맞는지 확인**해야
> 한다 … 충돌 갈래 — 각 LLM 이 낸 내용을 **다른 LLM 이 서치해서 검증**하는
> 걸로, **옳다 그르다를 판단**한다

지금까지 `⑤-b2`(`core/strategy_llm`)는 두 모델을 다 묻고 **합의만** 확률에
닿게 했다. `🔴 모델 충돌`·`🟡 한 모델만` 은 맥락 전용으로 내려가 **양쪽 문장만**
남았다 — 판정 절차가 **없었다**. 이 파일이 그 절차다.

```
갈래(충돌·단독)
  │
  ├─ 1단 **코드가 가진 수**로 가린다 ····· 싸고 확실하다(검색 전에)
  │     중원 수 · 측면 선수 수 · 휴식일 · 실점 평균/ΔD
  │     🔴 투표가 아니라 **측정**이다 — 모델이 뭐라 했든 수가 가리킨 쪽이다.
  │
  ├─ 2단 **교차 검증** ···················· 수로 못 가린 갈래만(상한 안에서)
  │     deepseek 의 주장은 **solar 가**, solar 의 주장은 **deepseek 가**
  │     🔴 판정은 **문서로만** — 질의를 쓰고 · 본문을 받고 · 그 안의 글자로
  │        `옳다/그르다/모르겠다` 를 낸다. 모델 기억은 **버린다**(절대규칙 5).
  │     🔴 인용이 **본문에 없으면 버린다**(접지 — `s1_resolve._by_llm` 그 규율).
  │
  └─ 3단 **채택 또는 보류**
        · 한쪽이 옳다(접지 통과) → 그 부등호를 채택 · `usable_as_basis=True`
          로 올리고 **근거(수 또는 인용·주소)를 변수 글에 남긴다**
        · 둘 다 모르겠다 · 근거 불량 → **그대로 맥락 전용**(지어내지 않는다)
        · 서로 옳다가 엇갈린다 → 맥락 전용 유지하고 **그 사실을 적는다**
```

🔴🔴 **잠금 다섯** — 이 통로가 지켜야 하는 것(계약이 검사한다)
  ① **근거 없이 승격하지 않는다** — 잰 수(`num_why`)나 **접지된 인용**
     (`quote`+`url`+`grounded`)이 없으면 `usable_as_basis` 를 못 올린다.
  ② **자기 주장을 자기가 판정하지 않는다**(`judge_pv_of` 가 상대를 고른다).
  ③ LLM 이 내는 것은 **글자뿐**이다 — 질의·판정 글자·인용·주소. 방향은
     부등호 표(`strategy_llm.dir_of_cmp`)가, 가중은 코드가 넣는다.
  ④ 검증에 쓴 **주소와 인용이 변수 글에 남는다**(#3 — 읽을 수 있어야 한다.
     어제 §4 의 그 병: *"남겼다"와 "읽을 수 있다"는 다르다*).
  ⑤ **갈래 수 상한**(`MAX_JUDGE`)이 있다 — 충돌 갈래마다 검색 + 본문 +
     LLM 이 더 드므로 카드 상한(`slate.CARD_CAP_MIN` 20분) 안에서 돌게 한다.
     ⚠️ 상한에 걸려 **안 돌린 갈래는 이름으로** 남긴다(조용한 0 금지).

⚠️ **1단이 재는 것이 무엇인지 글에 그대로 적는다.** 보기 — `수비 라인` 갈래에서
   코드가 잰 것은 **라인 높이가 아니라 수비 상태**(실점 평균·ΔD)다. 그 둘을
   섞어 적으면 그것이 **거짓 수**가 된다(이 저장소가 어제까지 세 번 다친 자리).
   🔴 그래서 사유에 *무엇을 쟀는지*를 쓴다 — 사람이 그 글을 보고 가른다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.core import crosscheck as _cc

logger = logging.getLogger(__name__)

#: 🔴 ⑤ **검증할 갈래 수 상한** — 2단(검색+본문+LLM)까지 가는 갈래다
MAX_JUDGE = 2
#: 🔴 한 갈래에서 **열 문서 수 상한**
DOCS_CAP = 3
#: 🔴 본문이 이보다 짧으면 **읽을 글이 아니다**(껍데기 · `fetch.shell_like` 뒤)
BODY_MIN = 400
#: 🔴 모델에 넘기는 본문 글자 상한(문서 하나)
BODY_CUT = 1800
#: 🔴 한 갈래에 던지는 **질의 수 상한**
MAX_Q = 3
#: 🔴 접지 대조에 쓰는 **인용 앞글자 수** — 이보다 짧은 인용은 근거가 아니다
QUOTE_MIN = 20

#: 🔴 판정 글자 — 표에 없는 글자는 **모르겠다**로 떨어진다(지어내기 금지)
VERDICTS: tuple[str, ...] = ("옳다", "그르다", "모르겠다")
OK, NO, DUNNO = VERDICTS

#: 🔴 공급자 둘 — ⑤-b2 가 묻는 그 둘이다(사본 금지로 기본값만 여기 둔다)
PROVIDERS: tuple[str, ...] = ("deepseek", "solar")

#: ✅ 판정이 **선** 갈래 표시 — 카드·평이 이 글자를 읽는다
#  ⚠️ 꼬리표(`MARK`)가 이미 *"갈래 판정"* 이라고 말한다 — 여기서 같은 말을
#     반복하지 않는다(실측 2026-10-17: `🔎 갈래 판정 ✅ 갈래 판정 ·` 로 찍혔다).
JUDGED = "✅ **채택**"
#: 🔴🔴 **변수 글에서 판정 사유가 시작되는 글자** — 읽는 자리가 여기서 쪼개
#   **둘째 줄로 온전히** 적는다(자르면 근거가 사라진다 · 2026-10-17 실사고).
#   🔴 글자와 쪼개는 함수는 `core/crosscheck` 하나가 든다(#1 사본 금지).
MARK = _cc.JUDGE_MARK
#: 🟡 판정을 못 한 갈래 표시(맥락 전용 유지)
HELD = "🟡 **보류**"

# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **1단 문턱** — 이만큼 차이가 나야 "수로 가려졌다"고 한다
# ══════════════════════════════════════════════════════════════════
#
#  🔴 이 수는 **확률 계수가 아니다** — 갈래를 *판정할 자격이 있나*만 가른다
#     (원장으로 계수를 맞추는 것은 금지다 · CLAUDE.md).
#  ⚠️ 차이가 문턱 아래면 **안 가린다** — `=` 를 채택하지 않는다(방향 없는
#     채택은 변수 구실을 못 한다).
#: 중원 수 차(사람 수) — 포메이션 가운데 칸의 합
MID_GAP = 1
#: 측면 선수 수 차(사람 수) — `flank` 가 왼·오른인 선발 수
FLANK_GAP = 2
#: 휴식일 차(일)
REST_GAP = 2
#: 실점 평균 차(경기당 골)
CONCEDE_GAP = 0.5
#: ΔD(수비 자리 가치 변화) 차(%p)
DD_GAP = 10.0


@dataclass
class Claim:
    """🔴 한 모델이 그 갈래에 낸 **주장 하나**."""

    provider: str
    cmp: str
    goals_cmp: str
    text: str
    #: 🔴 2단 판정 결과(`옳다`·`그르다`·`모르겠다`) · 빈 글자면 **안 물었다**
    verdict: str = ""
    quote: str = ""
    url: str = ""
    #: 🔴 인용이 **받은 본문에 있었나**(접지) — 거짓이면 근거로 안 쓴다
    grounded: bool = False
    #: 🔴 이 주장을 판정한 모델(자기 자신이면 계약이 빨개진다)
    judge_pv: str = ""
    why: str = ""


@dataclass
class Branch:
    """🔴🔴 **판정 대상 갈래 하나** — 충돌(모델 둘) 또는 단독(모델 하나)."""

    kind: str
    #: 🔴 `충돌` · `단독`
    mode: str
    claims: list[Claim] = field(default_factory=list)
    # ── 판정 결과(코드가 채운다) ─────────────────────────────────
    #: 🔴 `수` · `교차` · 빈 글자(판정 못 했다)
    by: str = ""
    picked: str = ""
    picked_goals: str = ""
    picked_pv: str = ""
    #: 🔴 1단이 **잰 수**를 적은 글 — 승격의 근거다(①)
    num_why: str = ""
    #: 🔴 2단이 **접지한 인용**과 그 주소 — 승격의 근거다(①)
    quote: str = ""
    url: str = ""
    judge_pv: str = ""
    grounded: bool = False
    #: 🔴 사람이 읽는 사유 — 카드·변수 글에 그대로 간다(④)
    why: str = ""

    @property
    def target(self) -> str:
        """🔴 `strategy_llm.vars_of` 가 쓴 그 열쇠 — 변수를 찾는 데 쓴다."""
        return f"strategy:{self.kind}"

    def said(self) -> str:
        """🔴 양쪽 주장을 한 줄로(카드가 읽는다)."""
        return " ↔ ".join(f"{c.provider} `{c.cmp}` {c.text[:70]}"
                          for c in self.claims)


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **1단 — 코드가 가진 수로 먼저 가린다**(검색 전에 · 싸고 확실하다)
# ══════════════════════════════════════════════════════════════════


def _xi_of(facts, ref, side: str):
    return dict(getattr(facts, "xi", None) or {}).get(
        str(getattr(ref, side, "") or ""))


def _recent_of(facts, ref, side: str) -> dict:
    return dict(dict(getattr(facts, "recent", None) or {}).get(
        str(getattr(ref, side, "") or "")) or {})


def _plan_val(plan, *, kind: str, side: str) -> float | None:
    """🔴 전략 판정이 **이미 센 수** 하나(`plan.facts` 의 그 칸). 없으면 `None`.

    ⚠️ 여기서 다시 세지 않는다 — `core/strategy` 가 센 값을 **읽기만** 한다.
    """
    for one in dict(getattr(plan, "facts", None) or {}).values():
        row = dict(one) if isinstance(one, dict) else {}
        if str(row.get("kind") or "") != kind:
            continue
        if str(row.get("side") or "") != side:
            continue
        val = row.get("value")
        if isinstance(val, (int, float)):
            return float(val)
    return None


def _pick(h: float | None, a: float | None, *, gap: float,
          home_big: bool) -> str:
    """🔴 두 수 → 부등호. **문턱 아래면 빈 글자**(안 가린다).

    `home_big=True` 면 *홈 수가 클 때* `>` 다. `False` 면 **작을 때** `>` 다
    (실점처럼 **작은 쪽이 좋은** 수가 그렇다).
    """
    if h is None or a is None:
        return ""
    if abs(float(h) - float(a)) < float(gap):
        return ""
    big = float(h) > float(a)
    return (">" if big else "<") if home_big else ("<" if big else ">")


def _flank_n(facts, ref, side: str) -> tuple[int | None, str]:
    """🔴 그 팀 선발에서 **측면 선수 수**. 못 세면 `(None, 사유)`.

    🔴 재료는 `XI.lineup` 의 `flank` 다(`L`·`R`). ⚠️ `XI.players` 는 **이름
       글자 목록**이라 자리가 없다 — 그 칸을 읽으면 0 이 된다(실측 2026-10-17).
    """
    one = _xi_of(facts, ref, side)
    rows = list(getattr(one, "lineup", None) or [])
    if not rows:
        return None, "⬜ 자리 글자가 없다(이름만 받았다)"
    got = [r for r in rows
           if str(getattr(r, "flank", "") or "").strip().upper() in ("L", "R")]
    return len(got), ""


def by_numbers(branch: Branch, ref, facts, plan=None) -> tuple[str, str]:
    """🔴🔴 **1단** — 코드가 가진 수로 그 갈래를 가린다. `(부등호, 사유)`.

    🔴 빈 부등호면 **안 가려졌다**(2단으로 간다). 사유는 늘 돌려준다 — 왜 못
       가렸는지도 카드에 적혀야 한다(#3 조용한 0 금지).
    🔴 **투표가 아니라 측정**이다 — 모델이 뭐라 했든 수가 가리킨 쪽이다.
    """
    kind = str(branch.kind or "")
    # ── 중원 수싸움 — 두 포메이션의 **가운데 수** ─────────────────
    if kind == "중원 수싸움":
        from app.core import strategy as _st
        h = _st.mid_line(getattr(_xi_of(facts, ref, "home"), "formation", ""))
        a = _st.mid_line(getattr(_xi_of(facts, ref, "away"), "formation", ""))
        if h is None or a is None:
            return "", f"⬜ 포메이션에서 중앙 수를 못 읽었다(홈 {h} · 원정 {a})"
        op = _pick(h, a, gap=MID_GAP, home_big=True)
        said = f"중앙 수 홈 **{h}** ↔ 원정 **{a}**"
        return op, (said + (f" → `{op}`" if op
                            else f" — 차이가 {MID_GAP} 미만이다(안 가린다)"))
    # ── 측면 집중 — 선발의 **측면 선수 수** ───────────────────────
    if kind == "측면 집중":
        h, why_h = _flank_n(facts, ref, "home")
        a, why_a = _flank_n(facts, ref, "away")
        if h is None or a is None:
            return "", f"⬜ 측면 선수를 못 셌다(홈 {why_h or h} · 원정 {why_a or a})"
        op = _pick(h, a, gap=FLANK_GAP, home_big=True)
        said = f"측면(왼·오른) 선발 홈 **{h}명** ↔ 원정 **{a}명**"
        return op, (said + (f" → `{op}`" if op
                            else f" — 차이가 {FLANK_GAP}명 미만이다(안 가린다)"))
    # ── 일정·피로도 — **휴식일**(짧은 쪽이 불리 = 작은 쪽) ────────
    if kind == "일정·피로도":
        h = _recent_of(facts, ref, "home").get("rest_days")
        a = _recent_of(facts, ref, "away").get("rest_days")
        if h is None or a is None:
            return "", f"⬜ 휴식일을 못 쟀다(홈 {h} · 원정 {a})"
        op = _pick(float(h), float(a), gap=REST_GAP, home_big=True)
        said = f"휴식 홈 **{h}일** ↔ 원정 **{a}일**(짧은 쪽이 불리)"
        return op, (said + (f" → `{op}`" if op
                            else f" — 차이가 {REST_GAP}일 미만이다(안 가린다)"))
    # ── 수비 라인 — **실점 평균**, 없으면 ΔD ──────────────────────
    #
    #  ⚠️🔴 **무엇을 재는지 적는다** — 이 수는 **라인 높이가 아니다**. 실점
    #     평균·ΔD 는 *그 팀 수비가 어떤 상태인가*를 재고, 아래는 **좋은 쪽을
    #     `cmp` 의 큰 쪽**으로 둔다(`vars_of` 가 `>` 를 홈 유리로 읽는 그 뜻).
    #     그 사실을 사유에 그대로 써서 사람이 가리게 한다(머리말 ⚠️).
    if kind == "수비 라인":
        h = _recent_of(facts, ref, "home").get("recent_conceded_avg")
        a = _recent_of(facts, ref, "away").get("recent_conceded_avg")
        if h is not None and a is not None:
            op = _pick(float(h), float(a), gap=CONCEDE_GAP, home_big=False)
            said = (f"최근 5경기 **실점 평균** 홈 {float(h):.2f} ↔ 원정 "
                    f"{float(a):.2f}(적은 쪽이 낫다) ⚠️ 이 수는 **라인 높이가 "
                    f"아니라 수비 상태**다")
            if op:
                return op, said + f" → `{op}`"
            said_hold = said + f" — 차이가 {CONCEDE_GAP}골 미만이다"
        else:
            said_hold = f"⬜ 실점 평균을 못 쟀다(홈 {h} · 원정 {a})"
        dh = _plan_val(plan, kind="delta_def", side="home")
        da = _plan_val(plan, kind="delta_def", side="away")
        if dh is None or da is None:
            return "", said_hold + f" · ⬜ ΔD 도 없다(홈 {dh} · 원정 {da})"
        op = _pick(dh, da, gap=DD_GAP, home_big=True)
        said2 = (f"ΔD(수비 자리 가치 변화) 홈 {dh:+.0f}% ↔ 원정 {da:+.0f}%"
                 " ⚠️ **평소 XI 대비 변화**다")
        return op, (said_hold + " · " + said2
                    + (f" → `{op}`" if op
                       else f" — 차이가 {DD_GAP:g}%p 미만이다(안 가린다)"))
    return "", f"⬜ `{kind}` 는 코드가 잰 수가 없다 — 2단(교차 검증)으로 간다"


def stage1(branches: list[Branch], ref, facts, plan=None) -> str:
    """🔴 모든 갈래에 **1단**을 돌린다(검색이 없어 공짜다). 사유 한 줄."""
    said: list[str] = []
    for one in branches:
        op, why = by_numbers(one, ref, facts, plan)
        one.num_why = why
        if op not in (">", "<"):
            said.append(f"`{one.kind}` ⬜ 수로 못 가렸다")
            continue
        one.by = "수"
        one.picked = op
        # 🔴 **그 부등호를 낸 모델**이 있나 — 있으면 그 주장의 총골 방향을
        #    같이 쓴다. ⚠️ 없으면 총골은 **방향 없음**이다(수는 총골을 안 잰다).
        hit = [c for c in one.claims if str(c.cmp or "") == op]
        one.picked_pv = hit[0].provider if len(hit) == 1 else ""
        one.picked_goals = hit[0].goals_cmp if len(hit) == 1 else "="
        for c in one.claims:
            c.verdict = OK if str(c.cmp or "") == op else NO
            c.why = f"1단(수) — {why}"
        one.why = (f"{JUDGED} · **1단 측정** — {why}"
                   + (f" · `{one.picked_pv}` 주장이 맞다" if one.picked_pv
                      else " · 🔴 **어느 모델도 이 쪽을 말하지 않았다**"
                           "(수가 가리킨 쪽을 쓴다)"))
        said.append(f"`{one.kind}` ✅ 수로 가렸다(`{op}`)")
    return " · ".join(said) if said else "⬜ 갈래가 없다"


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **2단 — 교차 검증**(상대 모델이 **서치해서** 판정한다)
# ══════════════════════════════════════════════════════════════════


class JQueries(BaseModel):
    """🔴 ③ 판정 모델이 내는 **첫 글자** — 질의와 **언어 코드**뿐이다.

    🔴 `langs` 는 사실이 아니다 — 사슬에 줄 **언어 힌트**다(그 나라 말을 아는
       것이 모델이다). 열거(`s4b_gapsearch.LANGS`)로 **잠근다** — 그 표가
       원본이고 여기서 새로 적지 않는다(#1 사본 금지).
    ⚠️ 종전엔 이 칸이 없어 `lang="en"` 으로만 던졌다 — 일본어 질의
       (`柏レイソル …`)를 영어 창으로 던지던 꼴이다(실측 2026-10-17).
    """

    queries: list[str] = Field(default_factory=list)
    langs: list[str] = Field(default_factory=list)


class JudgeOut(BaseModel):
    """🔴 ③ 판정 모델이 내는 **둘째 글자** — 판정·인용·주소뿐이다.

    🔴 `verdict` 는 표(`VERDICTS`)의 글자만이고, `quote` 는 **본문 한 문장**
       그대로다. 코드가 본문과 대조해 없으면 **버린다**(접지).
    """

    verdict: str = DUNNO
    quote: str = ""
    url: str = ""


#: 🔴 검색 언어 코드 — **표는 `s4b_gapsearch.LANGS` 하나**다(여기서 안 적는다)
def _langs_table() -> tuple[str, ...]:
    from app.core.stages import s4b_gapsearch as _gs
    return tuple(_gs.LANGS)


_LANGS = _langs_table()


def judge_pv_of(claim_pv: str, *, providers: tuple = PROVIDERS) -> str:
    """🔴🔴 ② **자기 주장은 자기가 판정하지 않는다** — 상대 모델을 돌려준다.

    > deepseek 의 주장을 **solar 가** 검증하고, solar 의 주장을 **deepseek
    > 가** 검증한다(자기 주장은 자기가 판정하지 않는다 — 그래야 치우치지 않는다)

    ⚠️ 상대가 없으면 **빈 글자**다(판정하지 않는다 — 자기 검증은 금지다).
    """
    said = [str(p) for p in (providers or ()) if str(p) != str(claim_pv or "")]
    return said[0] if said else ""


def _aliases(ref) -> list[str]:
    """🔴 질의 검열에 쓸 **팀 표기** — `s4b_gapsearch.ask` 와 같은 길이다.

    ⚠️ `ref.home` 은 내부 열쇠(`team:000455`)다 — **이름**으로 뽑는다
       (실사고 2026-10-14: 열쇠로 뽑아 질의가 전부 버려졌다).
    """
    from app.core import discover as _d
    names = [str(getattr(ref, f"{s}_name", "") or "") for s in ("home", "away")]
    out: list[str] = []
    for one in names:
        if not one:
            continue
        out.append(one)
        out += [str(x) for x in (_d.aliases_of(one) or [])][:6]
        for bit in str(one).split():
            if len(bit) >= 4 and not bit.isdigit():
                out.append(bit)
    return list(dict.fromkeys(x for x in out if x))


def _queries(branch: Branch, ref, *, pv: str, state
             ) -> tuple[list[str], list[str], str]:
    """🔴🔴 2단-①: **판정 모델이 질의를 쓴다**(사실을 말하지 않는다).

    🔴 걸러내는 곳은 `querywriter.keep`(팀 표기)과 `app.llm.query_ok`
       (낱말 수·연산자·연도) **둘뿐**이다 — 새 규칙을 짓지 않는다(사본 금지).
    🔴 돌려주는 것은 `(질의, 언어 순서, 사유)` 다.
    """
    from app import llm as _lq
    from app.core import llm, querywriter
    said_claims = "\n".join(f"- `{c.provider}` 주장: {c.text}"
                            for c in branch.claims)
    msgs = [
        llm.Message(role="system", content=(
            "너는 **검색 질의를 쓰는 사람**이다. 🔴 아래 주장이 맞는지 "
            "**네 기억으로 답하지 마라** — 그것을 **문서로 확인할 검색어**만 "
            "만든다. 네가 모르는 것을 질의로 적는 것이 네 일이다.")),
        llm.Message(role="user", content=(
            f"경기: {getattr(ref, 'home_name', '')}(홈) vs "
            f"{getattr(ref, 'away_name', '')}(원정) · "
            f"{getattr(ref, 'competition', '')}\n"
            + __import__("app.core.querywriter",
                         fromlist=["x"]).comp_hint(ref)
            + f"확인할 갈래: **{branch.kind}**\n{said_claims}\n\n"
            f"🔴 `queries` — 위 주장을 **기사·기록으로 확인할** 검색어 "
            f"{MAX_Q}개 이하.\n"
            "🔴 각 질의에 **팀 이름**을 반드시 넣는다"
            f"(쓸 표기: {' · '.join(_aliases(ref)[:10])}).\n"
            # ══════════════════════════════════════════════════════
            # 🔴🔴 **전술 용어를 질의에 넣지 마라** — 실측 2026-10-17
            # ══════════════════════════════════════════════════════
            #
            #  ⚠️ 처음 판은 갈래 이름을 그대로 질의에 넣었다(`柏レイソル 逆襲
            #     得点 近況` · `… 守備ライン 失点 直近5試合`). 그 말로는 기사가
            #     안 걸리고 **포털 첫 화면**이 걸렸다 — 실제로 받은 본문이
            #     `jleague.jp`(5,174자) · DAZN 중계 안내 · **8월 25일 묵은
            #     기사**였고, 판정은 당연히 `모르겠다` 로 끝났다.
            #  🔴 그래서 **주장 안의 확인 가능한 알맹이**를 겨냥하게 한다 —
            #     선수 이름 · 결장·부상 · 선발 명단 · 순위·승점 · 최근 경기.
            "🔴🔴 **전술 용어를 질의에 쓰지 마라**(`압박`·`수비 라인`·`역습`·"
            "`빌드업`·`중원` 같은 말) — 그런 말로는 기사가 안 걸리고 **포털 첫 "
            "화면**이 걸린다(실측).\n"
            # ⚠️ 실측 2026-10-17: 아래 보기를 **한국어로만** 적었더니 모델이
            #    그 낱말을 일본어 질의에 섞었다(`柏レイソル 柏田 선발`) —
            #    그런 질의는 그 나라 매체에서 안 걸린다. 🔴 그래서 **그 나라
            #    말의 실제 표현**을 보기로 준다(`s4b_gapsearch` 의 그 목록).
            "🔴🔴 그 대신 주장 안의 **확인 가능한 알맹이**를 질의로 만든다 — "
            "⚠️ **질의 전체를 한 언어로** 쓴다(낱말을 섞지 마라):\n"
            "   · 선수 이름이 있으면 → 결장·부상·선발 여부를 묻는다"
            "(`<이름> 欠場`·`<이름> 負傷`·`<이름> 부상`·`<name> injury`·"
            "`<nombre> lesión`)\n"
            "   · 선발·포메이션 주장이면 → 선발 명단을 묻는다"
            "(`<팀> 予想スタメン`·`<팀> 先発`·`<팀> 예상 선발`·"
            "`<team> starting XI`·`<equipo> alineación probable`)\n"
            "   · 성적·득실 주장이면 → 최근 경기·순위를 묻는다"
            "(`<팀> 試合結果`·`<팀> 順位 勝点`·`<team> recent results`·"
            "`<squadra> classifica punti`)\n"
            "   · 일정·피로 주장이면 → 일정을 묻는다"
            "(`<팀> 日程`·`<team> fixtures`)\n"
            "🔴🔴 **현지어를 먼저** 쓴다 — 그 팀 나라의 말이다(네가 안다). "
            "그다음 영어다. `langs` 에 **그 순서로** 언어 코드를 적는다"
            "(보기 `[\"ja\", \"en\"]`).\n"
            f"   ⚠️ 쓸 수 있는 코드: {', '.join(_LANGS)}\n"
            "🔴 1~6낱말 · 연산자(`site:`·따옴표·마이너스) 금지 · **연도 금지**.\n"
            "⚠️ 사실·숫자·판정을 **답으로 쓰지 마라** — 질의 글자만 낸다.")),
    ]
    got = llm.ask(provider=pv, purpose="query", messages=msgs, out=JQueries,
                  state=state, enums={"langs": list(_LANGS)})
    if not isinstance(got, JQueries):
        return [], [], f"🔴 `{pv}` 가 질의를 못 냈다({getattr(got, 'reason', '?')})"
    rows = [str(x).strip() for x in (got.queries or []) if str(x).strip()]
    langs = [str(x) for x in (got.langs or []) if str(x) in set(_LANGS)]
    kept, bad = querywriter.keep(rows, aliases=_aliases(ref))
    ok = [q for q in kept if _lq.query_ok(q)]
    return ok[:MAX_Q], (langs or ["en"]), (
        f"`{pv}` 질의 {len(rows)}개 → 쓸 것 {len(ok)}개"
        + (f" · 🔴 팀 표기 없어 버림 {len(bad)}" if bad else "")
        + (f" · 🔴 글자 규칙에서 버림 {len(kept) - len(ok)}"
           if len(kept) != len(ok) else "")
        + f" · 언어 {langs or ['en']}")


def _about(body: str, aliases: list[str]) -> bool:
    """🔴🔴 **그 경기 글인가** — 본문에 팀 표기가 한 글자라도 있나.

    ⚠️ 실측 2026-10-17(Kashiwa vs Nagoya): 받은 본문 셋이 `jleague.jp` **포털
       첫 화면**(5,174자) · DAZN 중계 안내 · **8월 25일 묵은 기사**였다 —
       길이 문턱(`BODY_MIN`)만으로는 그것이 다 통과한다. 🔴 그 글을 모델에
       넘기면 `모르겠다` 가 나오는데, 그 `모르겠다` 는 *"글이 그 말을 안
       했다"* 가 아니라 **"엉뚱한 글을 읽었다"** 다 — 둘을 가려야 한다.
    🔴 그래서 **팀 표기 선필터**를 둔다(딥서치의 신원 선필터와 같은 뜻).
    ⚠️ 표기를 못 만들었으면 **거르지 않는다**(없는 검문으로 다 버리지 않는다).
    """
    want = [a.lower() for a in (aliases or []) if len(str(a)) >= 3]
    if not want:
        return True
    low = str(body or "").lower()
    return any(a in low for a in want)


async def _docs(queries: list[str], *, net, chain, state,
                langs: list[str] | None = None,
                aliases: list[str] | None = None
                ) -> tuple[list[tuple[str, str]], str]:
    """🔴🔴 2단-②: 질의를 **기존 사슬**에 던져 **본문**을 받는다.

    🔴 새 엔진·새 fetch 경로를 만들지 않는다 — `search.build_chain` 과
       `core.search.fetch.body_of` 가 그 하나다(`s1_resolve._by_llm` 과 같은 길).
    🔴 **엔진을 지정한다** — 표는 `rules.news_engines()` 하나다(사본 금지).
       ⚠️ 지정 없이 쏘면 *"질의를 무시하는 엔진"* 의 결과가 섞여 열기 예산을
          포털·티켓 페이지에 태운다(이 저장소의 실측 2026-10-02). 지정이 0건이면
          사슬이 **지정 없이 한 번 더** 던진다(§19-b-4 대체 · 우회가 아니다).
    🔴 **현지어 먼저** 던진다(`langs`) — 일본 경기 질의를 영어 창으로 던지던
       것을 고쳤다(실측 2026-10-17).
    ⚠️ 껍데기(광고·로그인)는 `body_of` 가 가려 주고, 짧은 글은 `BODY_MIN` 이,
       **엉뚱한 글**은 `_about`(팀 표기)이 버린다 — 버린 수를 사유에 적는다(#3).
    """
    from app import rules
    from app.core.search import fetch as _ft
    eng = list(rules.news_engines())
    said_langs = [x for x in (langs or []) if x] or ["en"]
    got: list[tuple[str, str]] = []
    said: list[str] = []
    n_off = 0
    for one in list(queries or [])[:MAX_Q]:
        hits: list = []
        for lang in said_langs[:2]:
            try:
                hits = await chain.query(one, lang=lang, engines=eng or None)
            except Exception as exc:                        # noqa: BLE001
                said.append(f"`{one}`({lang}) 🔴 검색 실패 {exc!r}")
                continue
            if hits:
                said.append(f"`{one}`({lang}) {len(hits)}건")
                break
        if not hits:
            said.append(f"`{one}` ⬜ 0건")
            continue
        for h in list(hits)[:4]:
            url = str(getattr(h, "url", "") or "")
            if not url or any(url == u for u, _b in got):
                continue
            try:
                body, _when, _rungs = await _ft.body_of(net, url)
            except Exception:                               # noqa: BLE001
                continue
            if len(str(body or "")) < BODY_MIN:
                continue
            # 🔴 **그 경기 글이 아니면 버린다**(위 `_about` 머리말)
            if not _about(str(body), list(aliases or [])):
                n_off += 1
                continue
            got.append((url, str(body)))
            if len(got) >= DOCS_CAP:
                break
        if len(got) >= DOCS_CAP:
            break
    if n_off:
        said.append(f"🔴 팀 표기 없어 버린 본문 {n_off}건")
    # 🔴🔴 **무엇을 읽었는지 적는다**(④ · #3) — ⚠️ 실측 2026-10-17: 사유에
    #    질의와 **건수만** 있어서, 판정이 `모르겠다` 로 끝났을 때 *"그래서 어떤
    #    글을 읽고 못 가린 건가"* 를 사람이 알 길이 없었다(조용한 0 의 사촌).
    return got, (" · ".join(said) + f" → 본문 **{len(got)}건**"
                 + (" — " + " · ".join(f"{u[:70]}({len(b)}자)" for u, b in got)
                    if got else "")
                 if said else "⬜ 던질 질의가 없다")


def _ground(quote: str, docs: list[tuple[str, str]]) -> tuple[bool, str]:
    """🔴🔴 2단-③ **접지** — 인용이 **받은 본문에 있나**. `(있나, 그 주소)`.

    🔴 대조하는 함수는 `verify.quote_grounded` 하나다(사본 금지) — 공백·
       따옴표 표기를 정규화해 본다.
    ⚠️ 너무 짧은 인용은 **근거가 아니다**(`QUOTE_MIN`) — 아무 글에나 들어 있다.
    """
    from app import verify
    said = str(quote or "").strip()
    if len(said) < QUOTE_MIN:
        return False, ""
    for url, body in docs:
        if verify.quote_grounded(said, body).ok:
            return True, url
    return False, ""


def _verdict(claim: Claim, branch: Branch, ref, *, pv: str,
             docs: list[tuple[str, str]], state) -> str:
    """🔴🔴 2단-③: **판정 모델이 본문을 읽고** 옳다/그르다/모르겠다를 낸다.

    🔴 판정은 **문서로만** 한다 — 인용이 본문에 없으면 **버린다**(접지).
    """
    from app.core import llm
    said_body = "\n\n".join(f"[{i + 1}] {u}\n{b[:BODY_CUT]}"
                            for i, (u, b) in enumerate(docs))
    msgs = [
        llm.Message(role="system", content=(
            "너는 **글에 적힌 것만 보는 심판**이다. 🔴 네 기억으로 판정하지 "
            "마라 — 아래 **문서 본문**에 그 말을 받치는 글자가 있을 때만 "
            "`옳다`·`그르다`를 낸다. 없으면 `모르겠다` 다. "
            "🔴 `quote` 는 본문에 **글자 그대로** 있는 한 문장이어야 한다 — "
            "코드가 본문과 대조해서 없으면 네 판정을 **버린다**.")),
        llm.Message(role="user", content=(
            f"경기: {getattr(ref, 'home_name', '')}(홈) vs "
            f"{getattr(ref, 'away_name', '')}(원정)\n"
            f"갈래: **{branch.kind}**\n"
            f"🔴 판정할 주장(`{claim.provider}` 가 냈다): {claim.text}\n"
            f"   그 주장의 부등호: `{claim.cmp}`"
            "(`>` 홈이 크다 · `<` 원정이 크다)\n\n"
            f"문서 {len(docs)}건:\n{said_body}\n\n"
            "🔴 `verdict` — 위 문서 본문을 근거로:\n"
            "  · `옳다` — 본문이 그 주장을 **받친다**\n"
            "  · `그르다` — 본문이 그 주장과 **어긋난다**\n"
            "  · `모르겠다` — 본문에 그 말을 가릴 글자가 **없다**\n"
            "🔴 `quote` — 그 판정의 근거가 된 **원문 한 문장**(글자 그대로)\n"
            "🔴 `url` — 그 문장이 있던 문서 주소\n"
            "⚠️ 본문에 없으면 **`모르겠다` 로 두고 인용을 비워라** — "
            "지어내면 버려진다(코드가 대조한다).")),
    ]
    got = llm.ask(provider=pv, purpose="judge", messages=msgs, out=JudgeOut,
                  state=state, enums={"verdict": list(VERDICTS)})
    claim.judge_pv = pv
    if not isinstance(got, JudgeOut):
        claim.verdict = DUNNO
        claim.why = f"🔴 `{pv}` 판정 실패({getattr(got, 'reason', '?')})"
        return claim.why
    said = str(got.verdict or "").strip()
    claim.verdict = said if said in VERDICTS else DUNNO
    claim.quote = str(got.quote or "").strip()
    ok, url = _ground(claim.quote, docs)
    claim.grounded = ok
    claim.url = url or str(got.url or "").strip()
    if claim.verdict in (OK, NO) and not ok:
        # 🔴 **지어낸 인용이다** — 본문에 그 글자가 없다(절대규칙 5 · 접지)
        claim.why = (f"🔴 `{pv}` 가 `{claim.verdict}` 라 했지만 **인용이 본문에 "
                     f"없다** — 버린다(`{claim.quote[:40]}`)")
        claim.verdict = DUNNO
        return claim.why
    claim.why = (f"`{pv}` 판정 **{claim.verdict}**"
                 + (f" · 인용 「{claim.quote[:80]}」 · {claim.url[:60]}"
                    if ok else " · ⬜ 인용 없음"))
    return claim.why


async def cross(branch: Branch, ref, *, state, net, chain=None) -> str:
    """🔴🔴 **2단 한 갈래** — 상대 모델이 서치해서 판정한다. 사유 한 줄.

    🔴 결과 처리(사용자 지시 2026-10-16):
       · 한쪽만 **옳다**(접지 통과) → 그 부등호를 **채택**
       · 둘 다 모르겠다·근거 불량 → **그대로 맥락 전용**
       · 서로 **옳다**가 엇갈린다 → 맥락 전용 유지 + **그 사실을 적는다**
    """
    if chain is None:
        from app import search as _search
        chain = _search.build_chain()
    # 🔴 질의는 **첫 주장의 상대 모델**이 쓴다(한 갈래에 한 번 · 예산)
    pv_q = judge_pv_of(branch.claims[0].provider) if branch.claims else ""
    if not pv_q:
        branch.why = f"{HELD} · 🔴 판정할 **상대 모델이 없다**(자기 검증 금지)"
        return branch.why
    qs, said_langs, said_q = _queries(branch, ref, pv=pv_q, state=state)
    if not qs:
        branch.why = f"{HELD} · 🔴 질의 0개 — {said_q}"
        return branch.why
    docs, said_d = await _docs(qs, net=net, chain=chain, state=state,
                               langs=said_langs, aliases=_aliases(ref))
    if not docs:
        branch.why = f"{HELD} · 🔴 본문 0건 — {said_q} · {said_d}"
        return branch.why
    said_each: list[str] = []
    for one in branch.claims:
        pv = judge_pv_of(one.provider)
        if not pv:
            one.verdict = DUNNO
            one.why = "🔴 상대 모델이 없다(자기 검증 금지)"
            said_each.append(one.why)
            continue
        said_each.append(_verdict(one, branch, ref, pv=pv, docs=docs,
                                  state=state))
    good = [c for c in branch.claims if c.verdict == OK and c.grounded]
    head = f"{said_q} · {said_d} · " + " · ".join(said_each)
    if len(good) == 1:
        one = good[0]
        branch.by = "교차"
        branch.picked = str(one.cmp or "")
        branch.picked_goals = str(one.goals_cmp or "=")
        branch.picked_pv = one.provider
        branch.judge_pv = one.judge_pv
        branch.quote = one.quote
        branch.url = one.url
        branch.grounded = True
        branch.why = (f"{JUDGED} · **2단 교차** — `{one.judge_pv}` 가 문서로 "
                      f"`{one.provider}` 주장을 **옳다**고 봤다 · 인용 "
                      f"「{one.quote[:90]}」 · {one.url}")
        return branch.why + " · " + head
    if len(good) > 1:
        branch.why = (f"{HELD} · 🔴 **서로 옳다가 엇갈렸다**(" +
                      " ↔ ".join(f"{c.provider}=`{c.cmp}`(판정 {c.judge_pv})"
                                 for c in good)
                      + ") — 맥락 전용으로 둔다")
        return branch.why + " · " + head
    # 🔴 보류여도 **무엇을 읽었나**가 변수 글에 남아야 한다(④) — 그래야 다음
    #    사람이 *"질의가 나빴나 · 글이 그 말을 안 했나"* 를 가릴 수 있다.
    branch.why = (f"{HELD} · 문서로 못 가렸다 — " + " · ".join(said_each)
                  + f" · 읽은 것 {said_d}")
    return branch.why


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **3단 — 채택(승격) 또는 보류**. 근거 없이는 못 올린다(①)
# ══════════════════════════════════════════════════════════════════


def may_promote(branch: Branch) -> tuple[bool, str]:
    """🔴🔴 ① **근거 없이 승격하지 않는다** — `(올리나, 사유)`.

    올릴 수 있는 길은 **둘뿐**이다:
      · `by="수"` — 1단이 **잰 수**가 사유에 있다(`num_why`)
      · `by="교차"` — 2단의 **인용이 접지됐고** 주소가 있다
    ⚠️ 그 밖은 전부 **보류**다(맥락 전용 유지 · 지어내지 않는다).
    """
    if str(branch.picked or "") not in (">", "<"):
        return False, "부등호가 없다(방향 없는 채택은 변수가 아니다)"
    if branch.by == "수":
        if not str(branch.num_why or "").strip():
            return False, "🔴 1단 채택인데 **잰 수가 없다**"
        return True, f"수 — {branch.num_why}"
    if branch.by == "교차":
        if not (branch.grounded and str(branch.quote or "").strip()
                and str(branch.url or "").strip()):
            return False, "🔴 2단 채택인데 **접지된 인용·주소가 없다**"
        if not str(branch.judge_pv or "").strip():
            return False, "🔴 판정한 모델이 없다"
        if branch.judge_pv == branch.picked_pv:
            # 🔴 ② 자기 주장을 자기가 판정했다 — 있을 수 없는 꼴이다
            return False, (f"🔴 **자기 검증**이다(`{branch.judge_pv}` 가 자기 "
                           f"주장을 판정했다)")
        return True, f"인용 — 「{branch.quote[:60]}」 {branch.url[:60]}"
    return False, "판정 수단이 없다(1단·2단 둘 다 못 가렸다)"


def apply(branches: list[Branch], variables: list) -> tuple[list, str]:
    """🔴🔴 **3단** — 판정이 선 갈래를 변수에 **되먹인다**. `(변수, 사유)`.

    🔴 바뀌는 것은 넷이다 — `favors`·`goals`(부등호 표가 옮긴다) ·
       `usable_as_basis`(근거로 쓸 수 있다) · `claim`(근거 글을 **남긴다**).
    🔴 방향 표는 `strategy_llm.dir_of_cmp` **하나**다(사본 금지).
    ⚠️ 판정이 안 선 갈래도 **글은 바뀐다** — 왜 보류인지 읽혀야 한다(④).
    """
    from app.core import strategy_llm as _sl
    box = {str(b.target): b for b in (branches or [])}
    out: list = []
    said: list[str] = []
    for v in list(variables or []):
        one = box.get(str(getattr(v, "target", "") or ""))
        if one is None:
            out.append(v)
            continue
        ok, why = may_promote(one)
        if not ok:
            # 🔴 보류 — 맥락 전용 그대로이고 **사유를 글에 남긴다**
            #    ⚠️ 꼬리표(`MARK`)를 달아 **읽는 자리가 안 자르게** 한다
            out.append(v.model_copy(update={
                "claim": (str(getattr(v, "claim", "") or "")
                          + f" {MARK} {one.why or f'{HELD} · {why}'}"),
                "usable_as_basis": False}))
            # 🔴 요약에도 **실제 사유**를 쓴다 — `may_promote` 의 글은 *"부등호가
            #    없다"* 처럼 결과만 말해 왜 보류인지 안 보인다(실측 2026-10-17).
            said.append(f"`{one.kind}` " + (one.why or f"{HELD} · {why}"))
            continue
        fav, goals = _sl.dir_of_cmp(one.picked, one.picked_goals)
        # 🔴 **근거를 두 번 적지 않는다** — `one.why` 가 이미 잰 수(1단)나
        #    인용·주소(2단)를 들고 있다. ⚠️ 실측 2026-10-17: `… 중앙 수 홈 5 ↔
        #    원정 4 → > · 근거 수 — 중앙 수 홈 5 ↔ 원정 4 → >` 로 **같은 수가
        #    두 번** 찍혔다. 🔴 글에 없을 때만 덧붙인다(그래야 ④ 가 늘 선다).
        said_ev = ("" if str(one.quote or "") and str(one.quote) in str(one.why)
                   else "" if one.by == "수" and str(one.num_why or "")
                   and str(one.num_why) in str(one.why)
                   else f" · 근거 {why}")
        out.append(v.model_copy(update={
            "favors": fav, "goals": goals, "usable_as_basis": True,
            # 🔴 **근거를 글에 남긴다**(④) — 인용·주소·잰 수가 끝까지 읽힌다
            #    ⚠️ 꼬리표를 달아 **읽는 자리가 안 자르게** 한다(2026-10-17)
            "claim": (str(getattr(v, "claim", "") or "")
                      + f" {MARK} {one.why}{said_ev}"),
            # 🔴 인용은 `quote` 칸에도 둔다(변수 스키마의 그 자리)
            "quote": (one.quote or str(getattr(v, "quote", "") or "")),
        }))
        said.append(f"`{one.kind}` {JUDGED} `{one.picked}`→{fav}"
                    f"({one.by})")
    return out, (" · ".join(said) if said else "⬜ 되먹일 갈래가 없다")


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **한 번에 돌리는 자리** — 1단 → 2단(상한 안) → 3단
# ══════════════════════════════════════════════════════════════════


def _order(branches: list[Branch]) -> list[Branch]:
    """🔴 2단에 보낼 차례 — **충돌이 먼저**다(같은 재료로 반대 결론이므로).

    ⚠️ 뒤로 밀린 갈래는 상한에 걸려 **안 돌 수 있다** — 그 이름을 남긴다(⑤).
    """
    return sorted(branches, key=lambda b: 0 if b.mode == "충돌" else 1)


async def run(branches: list[Branch], variables: list, ref, facts,
              plan=None, *, state, net, chain=None,
              cap: int = MAX_JUDGE) -> tuple[list, str]:
    """🔴🔴 **갈래 판정 한 번** — `(변수, 사유)`. ⚠️ 예외를 안 던진다.

    🔴 순서는 **1단(공짜) → 2단(상한 안) → 3단**이다. 2단은 카드 상한
       (`state.clock`)이 바닥이면 **안 돈다** — 그 사실을 사유에 적는다.
    """
    if not branches:
        return list(variables or []), "⬜ 충돌·단독 갈래가 없다 — 판정할 것이 없다"
    said = [f"갈래 {len(branches)}개(" +
            " · ".join(f"{b.mode} `{b.kind}`" for b in branches) + ")"]
    said.append("1단 " + stage1(branches, ref, facts, plan))
    left = [b for b in _order(branches) if not b.picked]
    done = 0
    for one in left:
        if done >= int(cap):
            one.why = one.why or (f"{HELD} · ⬜ **갈래 상한 {cap}개**를 넘겨 "
                                  f"2단을 안 돌렸다 — {one.num_why}")
            said.append(f"`{one.kind}` ⬜ 상한으로 건너뜀")
            continue
        clock = getattr(state, "clock", None)
        if clock is not None and getattr(clock, "over", lambda: False)():
            one.why = one.why or (f"{HELD} · ⬜ **카드 상한**을 넘겨 2단을 안 "
                                  f"돌렸다 — {one.num_why}")
            said.append(f"`{one.kind}` ⬜ 시간 상한으로 건너뜀")
            continue
        try:
            said.append(f"2단 `{one.kind}` — "
                        + await cross(one, ref, state=state, net=net,
                                      chain=chain))
        except Exception as exc:                            # noqa: BLE001
            # ⚠️ 카드는 **항상** 나와야 한다 — 실패도 사유로 남긴다
            one.why = f"{HELD} · 🔴 2단이 터졌다 — {exc!r}"
            said.append(f"2단 `{one.kind}` 🔴 {exc!r}")
        done += 1
    got, said_apply = apply(branches, variables)
    said.append("3단 " + said_apply)
    why = " · ".join(said)
    logger.info("[갈래판정] %s", why[:400])
    state.note(f"⑤-b3 갈래 판정 — {why}")
    return got, why
