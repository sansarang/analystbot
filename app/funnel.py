"""🔴🔴 **깔때기 아홉 칸** — v5 §8-5.

> 경기마다 한 줄: `queries → hits → kept_identity → kept_date → fetched →
> agent_vars → verified_vars → scenarios → markets_graded`.
> 단계 간 탈락은 **사유 코드별 개수**를 같이 적는다. 변수가 0 이 되는 자리를
> 숫자로 보기 위한 것이고, 카드 하단에 요약을 붙인다.

══════════════════════════════════════════════════════════════════
🔴 v4 의 일곱 칸에서 **무엇이 바뀌었나**
══════════════════════════════════════════════════════════════════

```
v4  queries → hits → kept_identity → kept_date → facts → typed → variables
v5  queries → hits → kept_identity → kept_date → fetched
                  → agent_vars → verified_vars → scenarios → markets_graded
```
⚠️ `facts`·`typed` 가 빠졌다 — §1 이 *"정규식 유형표로 사실→유형"* 을 **버리는
   것**에 넣었고, 읽기 주체가 에이전트로 옮겨간다.
🔴 그래서 진단이 *"typed 20 → variables 3"* 에서
   *"agent_vars 9 → verified_vars 2 (quote_not_found 5 · date_missing 2)"* 로
   바뀐다 — **사유 코드별 개수**가 그 자리를 말한다.

══════════════════════════════════════════════════════════════════
🔴🔴 **안 잰 칸과 0 인 칸은 다르다**
══════════════════════════════════════════════════════════════════

§3 에이전트가 아직 없다(적용 순서: §8 → §2 → **§3**). 그 사이 v4 규칙 경로가
돌고, `agent_vars` 는 *"에이전트가 낸 변수"* 가 아니라 **규칙 경로가 낸 후보**다.
⚠️ 그 사실을 적지 않으면 카드가 매번 *"`agent_vars` 에서 0 이 됐다"* 고 거짓
   경고를 낸다 — v4 에서 같은 잘못을 한 번 했다(`log(judge=False)` 주석).
🔴 그래서 **아무도 안 센 칸**은 `broke_at` 에서 빼고 **이름으로** 적는다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.reasons import Reason

logger = logging.getLogger(__name__)

#: 🔴 §8-5 의 **순서 그대로**. ⚠️ 순서가 뜻이다 — `broke_at` 이 *"처음으로 0 이
#   된 칸"* 을 찾는다. 목록을 손으로 지키지 않는다:
#   `tests/contracts/test_v5_8_funnel.py` 가 문서에서 읽어 대조한다.
STAGES: tuple[str, ...] = (
    "queries",         # 던진 검색어
    "hits",            # 검색이 돌려준 자료
    "kept_identity",   # §5-2 신원 필터를 지난 **문서**
    "kept_date",       # §5-3 날짜를 지난 것
    "fetched",         # 🔴 본문을 **실제로 받은** 건수(§4-5 상한 뒤)
    "agent_vars",      # 에이전트가 낸 변수 후보(§3-6) — 지금은 규칙 경로의 후보
    "verified_vars",   # 🔴 §5 여섯 검사를 **전부** 지난 것만
    "scenarios",       # §6-2 보강까지 끝난 시나리오 수
    "markets_graded",  # 등급이 **선** 마켓 수
)

#: 🔴 **단위**. ⚠️ 안 적으면 문서 수와 사실 수를 같은 자로 잰다 — 실측
#   2026-10-03 에 그렇게 읽을 뻔했다(*"97% 가 날짜에서 떨어졌다"*).
UNITS: dict[str, str] = {
    "queries": "검색어", "hits": "검색결과", "kept_identity": "문서",
    "kept_date": "문서", "fetched": "문서", "agent_vars": "변수",
    "verified_vars": "변수", "scenarios": "시나리오", "markets_graded": "마켓",
}

#: 🔴 그 칸이 0 이면 **무엇을 봐야 하나**. ⚠️ 사유 코드와 다른 것이다 — 이쪽은
#   *"어느 단계가 막혔나"* 이고 사유 코드는 *"무엇이 그것을 막았나"* 다.
WHY_ZERO: dict[str, str] = {
    "queries": "검색어를 **하나도 못 만들었다** — §4-1 세 요소 규칙·핵심어 표를 본다",
    "hits": "검색어는 나갔는데 **결과가 0** 이다 — 통로(SearXNG·GDELT·Bing)를 본다",
    "kept_identity":
        "자료는 왔는데 **우리 경기 것이 하나도 없다** — §5-2 신원 필터·검색어를 본다",
    "kept_date":
        "우리 경기 문서는 있는데 **날짜가 다 틀렸다** — §5-3·발행 시각 추출을 본다",
    "fetched":
        "열 문서는 골랐는데 **본문을 하나도 못 받았다** — robots·도메인 등급·상한을 본다",
    "agent_vars":
        "본문은 받았는데 **변수 후보가 0** 이다 — §3 에이전트 프롬프트·카탈로그를 본다",
    "verified_vars":
        "후보는 있는데 **검증을 하나도 못 지났다** — §5 여섯 검사의 사유 개수를 본다",
    "scenarios":
        "변수는 있는데 **시나리오가 0** 이다 — §6-2 보강·필수형 조건을 본다",
    "markets_graded":
        "시나리오는 있는데 **등급이 선 마켓이 0** 이다 — 상한·§6-7·M18 을 본다",
}


@dataclass
class Funnel:
    """한 경기의 깔때기. 🔴 **더하기만 한다** — 빼거나 고치지 않는다."""

    counts: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(STAGES, 0))
    #: 칸마다 **무엇이 거기까지 왔나**(앞 몇 개만) — 수가 거짓인지 눈으로 본다
    samples: dict[str, list[str]] = field(
        default_factory=lambda: {k: [] for k in STAGES})
    #: 🔴🔴 **사유 코드별 탈락 개수**(§8-5). ⚠️ 문장 목록이 아니다 — v4 에서
    #  문장으로 뒀더니 열일곱 줄이 카드를 덮었고 *"몇 건인지"* 가 안 보였다.
    drops: dict[str, dict[Reason, int]] = field(
        default_factory=lambda: {k: {} for k in STAGES})
    #: 🔴 **누가 이 칸을 한 번이라도 셌나.** ⚠️ 안 센 칸을 0 이라고 말하면 거짓
    #  경고가 된다(§3 이 아직 없어 `agent_vars` 가 그 꼴이다).
    measured: set[str] = field(default_factory=set)
    #: ⚠️ 오타난 칸 이름 — **조용히 사라지지 않게** 남긴다
    unknown_stages: list[str] = field(default_factory=list)
    #: 🔴🔴 **§7-5 — 사다리 몇 단계(각도)를 올랐나.** `None` 은 **안 쟀다**는 뜻.
    #
    #  ⚠️ `queries` 와 다른 수다 — 같은 각도로 열 번 던진 것과 두 각도로 두 번
    #     던진 것은 §7-5 에서 다른 뜻이다. 🔴 0 으로 때우지 않는다(#3).
    angles: int | None = None
    #: 🔴 어느 각도를 **실제로** 올랐나 — 이름으로 남긴다(수만 두면 못 되짚는다)
    angle_names: set[str] = field(default_factory=set)

    # ── 세기 ──────────────────────────────────────────────────────

    def set_angles(self, n: int) -> None:
        """🔴🔴 **§7-5 — 사다리 몇 단계를 올랐나**(각도 수).

        ⚠️ `queries`(던진 검색어 수)와 **다른 수**다 — 같은 각도로 열 번 던진
           것과 두 각도로 두 번 던진 것은 §7-5 에서 다른 뜻이다.
        🔴 **안 쟀으면 `None`** 이다(0 으로 때우지 않는다 · #3 조용한 0 금지).
        """
        self.angles = int(n)

    def angle(self, name: str) -> None:
        """🔴🔴 **§7-5 — 사다리 한 단계를 올랐다**(그 각도 이름).

        ⚠️ 같은 각도를 열 번 던져도 **한 단계**다 — 집합으로 센다.
        🔴 한 번이라도 부르면 `angles` 가 수가 된다(그 전에는 `None` = 안 쟀다).
        """
        got = str(name or "").strip()
        if not got:
            return
        self.angle_names.add(got)
        self.angles = len(self.angle_names)

    def add(self, stage: str, n: int = 1, sample: str = "") -> None:
        if stage not in self.counts:
            self._unknown(stage)
            return
        self.counts[stage] += int(n)
        self.measured.add(stage)
        if sample and len(self.samples[stage]) < 3:
            self.samples[stage].append(" ".join(str(sample).split())[:90])

    def set(self, stage: str, n: int) -> None:
        """🔴 이미 센 묶음의 **크기를 그대로** 넣는다(중복 더하기 방지)."""
        if stage not in self.counts:
            self._unknown(stage)
            return
        self.counts[stage] = int(n)
        self.measured.add(stage)

    def drop(self, reason: Reason, stage: str, n: int = 1) -> None:
        """🔴🔴 그 칸에서 **그 사유로** 몇 건 떨어졌나(§8-5).

        ⚠️ `reason` 은 **반드시 `Reason`** 이다 — 날 문자열을 받으면 터진다.
           그것이 §8-6 *"사유를 추정해서 적는 코드는 계약 실패"* 의 기계다.
        """
        if not isinstance(reason, Reason):
            raise TypeError(
                f"🔴 사유는 `Reason` enum 이다(§8-6) — 받은 것: {reason!r}. "
                f"문장을 지어 넣으면 거짓 사유가 된다(실사고 2026-10-03)")
        if stage not in self.drops:
            self._unknown(stage)
            return
        box = self.drops[stage]
        box[reason] = int(box.get(reason) or 0) + int(n)

    def _unknown(self, stage: str) -> None:
        logger.warning("[funnel] 모르는 칸 %r — 세지 않는다", stage)
        if stage not in self.unknown_stages:
            self.unknown_stages.append(str(stage))

    # ── 읽기 ──────────────────────────────────────────────────────

    @property
    def broke_at(self) -> str:
        """🔴 **처음으로 0 이 된 칸.** ⚠️ **안 잰 칸은 건너뛴다.**

        안 잰 것과 0 인 것은 다르다 — v4 에서 그 구분을 안 해 거짓 경고를 냈다.
        """
        seen_any = False
        for k in STAGES:
            if k not in self.measured:
                continue                 # 🔴 안 잰 칸은 판단하지 않는다
            if self.counts[k] > 0:
                seen_any = True
                continue
            if seen_any or k == next((x for x in STAGES
                                      if x in self.measured), ""):
                return k
        return ""

    def line(self) -> str:
        """§8-5 의 **한 줄**. ⚠️ 안 잰 칸은 `-` 로 적는다(0 과 다르다)."""
        bits = []
        for k in STAGES:
            v = self.counts[k] if k in self.measured else "-"
            bits.append(f"{k}:{v}")
        return " → ".join(bits)

    def drop_line(self) -> str:
        """🔴 사유 코드별 개수(§8-5). 많은 쪽부터."""
        out = []
        for k in STAGES:
            box = self.drops.get(k) or {}
            if not box:
                continue
            inner = " · ".join(
                f"{r.value} {n}" for r, n in
                sorted(box.items(), key=lambda x: (-x[1], x[0].value)))
            out.append(f"{k} 탈락: {inner}")
        return " | ".join(out)

    def worst(self) -> str:
        """🔴🔴 **가장 많이 떨어뜨린 사유 하나**를 사람 말로(§8-6).

        ⚠️ 개수 줄(`drop_line`)만 보면 코드 이름뿐이라 *"그래서 뭘 고치나"* 가
           안 보인다. 🔴 `reasons.say` 가 **그 한 표**다 — 여기서 문장을 짓지
           않는다(짓는 순간 §8-6 이 막으려는 거짓 사유가 생긴다).
        """
        from app.reasons import say
        tally: dict[Reason, int] = {}
        for box in self.drops.values():
            for r, n in box.items():
                tally[r] = tally.get(r, 0) + int(n)
        if not tally:
            return ""
        top, n = max(tally.items(), key=lambda x: (x[1], x[0].value))
        return say(top, detail=f"{n}건")

    def fix_where(self) -> str:
        """🔴🔴 §8-6 의 뜻 — *"**어디를 고쳐야 하나**"*. 많은 쪽부터."""
        tally: dict[str, int] = {}
        for box in self.drops.values():
            for r, n in box.items():
                tally[r.fix_where] = tally.get(r.fix_where, 0) + int(n)
        if not tally:
            return ""
        return " · ".join(f"{w} {n}건" for w, n in
                          sorted(tally.items(), key=lambda x: -x[1]))

    def report(self) -> str:
        """카드 하단 요약(§8-5). 🔴 어디서 끊겼는지와 **고칠 곳**을 적는다."""
        out = [self.line()]
        out.append("   (단위: " + " · ".join(
            f"{k} {UNITS[k]}" for k in STAGES) + ")")
        skipped = [k for k in STAGES if k not in self.measured]
        if skipped:
            out.append(f"   ⚠️ **안 잰 칸**: {', '.join(skipped)} — "
                       f"0 이 아니라 **측정하지 않았다**는 뜻이다")
        if (d := self.drop_line()):
            out.append("   🔴 " + d)
        if (w := self.fix_where()):
            out.append(f"   🔴 **고칠 곳**: {w}")
        if (t := self.worst()):
            out.append(f"   🔴 가장 많이 떨어뜨린 것 — {t}")
        where = self.broke_at
        if where:
            out.append(f"🔴 **`{where}` 에서 0 이 됐다** — {WHY_ZERO[where]}")
            i = STAGES.index(where)
            prev = next((x for x in reversed(STAGES[:i])
                         if x in self.measured), "")
            if prev and (got := self.samples.get(prev) or []):
                out.append(f"   ↳ `{prev}` 까지 온 것: " + " · ".join(got))
        return "\n".join(out)

    def merge(self, other: "Funnel") -> None:
        """🔴 세포 하나의 깔때기를 **합친다**. 경기 하나에 세포가 수십 개다."""
        for k in STAGES:
            self.counts[k] += int(other.counts.get(k, 0))
            for x in (other.samples.get(k) or []):
                if len(self.samples[k]) < 3 and x not in self.samples[k]:
                    self.samples[k].append(x)
            for r, n in (other.drops.get(k) or {}).items():
                box = self.drops[k]
                box[r] = int(box.get(r) or 0) + int(n)
        self.measured |= set(other.measured)
        for x in other.unknown_stages:
            if x not in self.unknown_stages:
                self.unknown_stages.append(x)

    def log(self, tag: str = "", *, judge: bool = True) -> None:
        """🔴 `judge=False` 면 **수만 찍는다**(아직 안 잰 칸을 외치지 않는다)."""
        head = f"[funnel]{(' ' + tag) if tag else ''} "
        logger.info("%s%s", head, self.line())
        if (d := self.drop_line()):
            logger.info("%s%s", head, d)
        if judge and (w := self.broke_at):
            logger.info("%s🔴 %s 에서 0 — %s", head, w, WHY_ZERO[w])
