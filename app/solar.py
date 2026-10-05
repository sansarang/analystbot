"""🔴🔴 **Solar(Upstage) 통로 + 예산 가드** — v5 §2.

사용자 지시 2026-10-04: *"solar api 키 … **한도 정하고** 테스트 해라."*
⚠️ 지시문 제목·§0 의 `DeepSeek` 는 **Solar** 로 읽는다(사용자 지시 2026-10-04).

══════════════════════════════════════════════════════════════════
🔴 §0 — 유료 0건 규칙이 **하나만** 열렸다
══════════════════════════════════════════════════════════════════

> 「유료 API·MCP·커넥터 0건」은 **Upstage Solar API 하나만** 예외로 바꾼다.
> 다른 유료 서비스는 여전히 0건이다. 결제는 사용자가 Upstage 콘솔에서 직접
> 하고, 봇은 §2 의 예산 가드로 **그 한도 안에서만** 돈다.

🔴 그래서 이 파일의 알맹이는 통로가 아니라 **가드**다. 한도를 yaml 에 적어 두고
   세는 코드가 없으면 그 한도는 **없는 것**이다(CLAUDE.md #2 배선).

══════════════════════════════════════════════════════════════════
🔴 §2 — *"코드가 센다, 에이전트는 모른다"*
══════════════════════════════════════════════════════════════════

| 상한 | 값 | 초과 시 |
|---|---|---|
| 경기당 입력 토큰 | 150,000 | 에이전트 중단 · 모은 변수로 §5 · `budget_cut` |
| 경기당 출력(추론 포함) | 20,000 | 같음 |
| 경기당 도구 호출 | search 24 · fetch 16 | 같음 |
| 하루 비용 | $3.0 | 그날 나머지 경기 자료 부족 · 사용자 알림 |
| 월 비용 | $40 | 🔴 **봇 정지** · 사용자 승인 전 재개 금지 |

⚠️ **수를 여기 적지 않는다** — `config/llm.yaml` 이 원본이다(사본 금지).

══════════════════════════════════════════════════════════════════
🔴 실측 2026-10-04 — 추론 토큰이 **출력으로 과금된다**
══════════════════════════════════════════════════════════════════

```
한국어 결장 추출 1회 · reasoning_effort=low
  completion_tokens 1014  중  reasoning_tokens **1001**
```
🔴 즉 짧은 답에도 출력이 1000 단위로 나간다. 경기당 20,000 이면 **약 20회**다.
⚠️ 그리고 추론 강도가 비용을 **단조롭게 줄이지 않는다**(low 219 · medium 178 ·
   high 159 — 같은 질문). *"low 가 싸다"* 를 전제로 예산을 짜면 안 된다.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
LLM_YAML = "config/llm.yaml"

#: 🔴 §8-6 사유 코드 — **실패한 조건이 돌려준다.** 문자열을 지어내지 않는다.
BUDGET_CUT = "budget_cut"
LLM_UNAVAILABLE = "llm_unavailable"
MONTH_STOP = "month_cap_stop"
DAY_STOP = "day_cap_stop"


def cfg() -> dict:
    """🔴 `config/llm.yaml` 이 원본이다 — 수를 코드에 적지 않는다."""
    from app import rules
    return dict(rules._load(LLM_YAML) or {})


def price() -> dict:
    return dict((cfg().get("price_usd_per_1m") or {}))


def budget_cfg() -> dict:
    return dict((cfg().get("budget") or {}))


def cost_usd(usage: dict) -> float:
    """🔴 그 호출의 **비용**. ⚠️ 캐시 적중분은 싼 단가로 센다(§2).

    `usage` 는 OpenAI 호환 꼴이다(실측 2026-10-04 에 네 칸이 다 온다):
      `prompt_tokens` · `completion_tokens` ·
      `prompt_tokens_details.cached_tokens` ·
      `completion_tokens_details.reasoning_tokens`
    ⚠️ **추론 토큰을 따로 더하지 않는다** — 이미 `completion_tokens` 안에 있다
       (실측: 1014 중 1001). 두 번 세면 비용이 두 배로 보인다.
    """
    p = price()
    u = usage or {}
    cached = int(((u.get("prompt_tokens_details") or {}).get("cached_tokens")
                  or 0))
    fresh = max(int(u.get("prompt_tokens") or 0) - cached, 0)
    out = int(u.get("completion_tokens") or 0)
    return round(
        (fresh * float(p.get("input") or 0)
         + cached * float(p.get("cached_input") or 0)
         + out * float(p.get("output") or 0)) / 1_000_000, 6)


@dataclass
class MatchPot:
    """🔴🔴 **경기 합계 지갑** — 지시서(오픈월드) §1-4 (2026-10-05).

    > 경기당 출력 **40k 유지**, **팀별 상한 25k**, **합계 40k 초과 금지**.

    ⚠️ `25k × 2 = 50k` 이므로 쪽 상한만으로는 합계를 못 막는다. 🔴 두 쪽이
       **같은 지갑**을 함께 보게 한다 — 한 쪽이 25k 를 다 쓰면 다른 쪽에
       **15k** 가 남고, 둘이 균등히 쓰면 각 20k 다.
    🔴 종전 `share=0.5`(20k 고정)는 상대가 쉬어도 그 몫을 **못 쓰게** 했다.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0


@dataclass
class MatchBudget:
    """🔴 **경기 하나의 예산.** 넘으면 `blocked` 가 사유를 든다.

    ⚠️ 호출 **전에** 묻는다(`can_call`) — 쓴 뒤에 세면 이미 넘긴 것이다.
    """

    #: 🔴 **새로 보낸** 입력만 센다(캐시는 아래 칸으로 따로) — 실측 2026-10-04
    input_tokens: int = 0
    output_tokens: int = 0
    #: 🔴 캐시된 입력. ⚠️ **조용히 빼지 않는다** — 수로 남겨 카드가 적는다(#3)
    cached_tokens: int = 0
    tool_calls: dict = field(default_factory=dict)
    usd: float = 0.0
    blocked: str = ""
    #: 🔴 밟은 자취 — 몇 번 썼고 어디서 멈췄나(#3 조용한 0 금지)
    calls: int = 0
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **몫** — 한 쪽이 다 써서 다른 쪽이 0개가 되는 것을 막는다
    # ══════════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-04(게이트2 2판) — **두 경기가 같은 자리에서 다쳤다**:
    #
    #      MLB  밀워키 budget_cut 출력 20,312/20,000 → 변수 **0개** · 파드리스 6
    #      KBO  한화   budget_cut 출력 20,682/20,000 → 변수 **0개** · 키움   2
    #
    #     🔴 MLB 는 반대쪽이 많이 건져 11개가 됐지만 **KBO 는 2개로 끝났다.**
    #  🔴 사용자 결정 2026-10-04: *"한 팀 에이전트가 예산을 다 써서 다른 팀이
    #     0개가 되는 일이 없도록 **팀별로 예산을 반씩 나눈다**."*
    #  ⚠️ `1.0` 이 기본이다 — 쪽을 안 나누는 호출부(스케줄러·카드 한 줄)는
    #     종전대로 돈다.
    share: float = 1.0
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **쪽 예산 + 경기 합계 지갑** — 지시서 §1-4 (2026-10-05)
    # ══════════════════════════════════════════════════════════════════
    #
    #  `side=True`  → 쪽 상한(`per_side_*`)을 쓴다. ⚠️ `share` 보다 **먼저**다.
    #  `pot`        → 두 쪽이 **함께 보는** 경기 합계(없으면 합계 벽이 없다).
    side: bool = False
    pot: "MatchPot | None" = None

    @property
    def caps(self) -> dict:
        return dict((budget_cfg().get("per_match") or {}))

    @property
    def max_in(self) -> int:
        """🔴 **내 몫**의 입력 상한. ⚠️ 상한 자체는 `config/llm.yaml` 이 든다."""
        c = self.caps
        if self.side:
            return int(c.get("per_side_input_tokens")
                       or int(c.get("input_tokens") or 0))
        return int(int(c.get("input_tokens") or 0) * self.share)

    @property
    def max_out(self) -> int:
        """🔴 **내 몫**의 출력 상한(추론 포함)."""
        c = self.caps
        if self.side:
            return int(c.get("per_side_output_tokens")
                       or int(c.get("output_tokens") or 0))
        return int(int(c.get("output_tokens") or 0) * self.share)

    def _pot_full(self) -> str:
        """🔴 **경기 합계**가 찼나 — 쪽 상한과 **따로** 본다(§1-4)."""
        if self.pot is None:
            return ""
        c = self.caps
        cap_out = int(c.get("output_tokens") or 0)
        cap_in = int(c.get("input_tokens") or 0)
        if cap_out and self.pot.output_tokens >= cap_out:
            return (f"{BUDGET_CUT}: 경기 **합계** 출력 "
                    f"{self.pot.output_tokens}/{cap_out} 토큰(지시서 §1-4)")
        if cap_in and self.pot.input_tokens >= cap_in:
            return (f"{BUDGET_CUT}: 경기 **합계** 입력 "
                    f"{self.pot.input_tokens}/{cap_in} 토큰(지시서 §1-4)")
        return ""

    def can_call(self) -> tuple[bool, str]:
        """🔴 다음 호출을 해도 되나. `(가능, 사유)`."""
        if self.blocked:
            return False, self.blocked
        # 🔴 **합계 벽을 먼저** 본다(§1-4) — 쪽 몫이 남아도 경기 합계가 벽이다
        full = self._pot_full()
        if full:
            return False, full
        # 🔴 **내 몫**으로 센다 — 쪽을 나눴으면 그 반이다
        if self.input_tokens >= self.max_in > 0:
            return False, (f"{BUDGET_CUT}: 경기당 입력 "
                           f"{self.input_tokens}/{self.max_in} 토큰"
                           + (f" (몫 {self.share:g})" if self.share != 1 else ""))
        if self.output_tokens >= self.max_out > 0:
            return False, (f"{BUDGET_CUT}: 경기당 출력(추론 포함) "
                           f"{self.output_tokens}/{self.max_out} 토큰"
                           + (f" (몫 {self.share:g})" if self.share != 1 else ""))
        return True, ""

    def can_tool(self, name: str) -> tuple[bool, str]:
        """🔴 그 도구를 한 번 더 불러도 되나(§2 — search 24 · fetch 16)."""
        # 🔴 도구 횟수도 **몫**으로 나눈다(한 쪽이 24회를 다 쓰면 같은 병이다)
        cap = int(int(((self.caps.get("tool_calls") or {}).get(name) or 0))
                  * self.share)
        used = int(self.tool_calls.get(name) or 0)
        if cap and used >= cap:
            return False, f"{BUDGET_CUT}: 도구 `{name}` {used}/{cap}회"
        return True, ""

    def took_tool(self, name: str) -> None:
        self.tool_calls[name] = int(self.tool_calls.get(name) or 0) + 1

    def took(self, usage: dict) -> float:
        """🔴 한 호출을 **쓴 뒤** 더한다. 반환은 그 호출의 비용.

        ══════════════════════════════════════════════════════════════════
        🔴🔴 **캐시된 입력을 제값으로 세지 않는다**(실측 2026-10-04)
        ══════════════════════════════════════════════════════════════════

        게이트 2 를 켜니 `budget_cut: 경기당 입력 162946/150000` 으로 **열여덟
        턴**에서 끊겼다. 원장을 읽어 보니(호출 20회):

            입력 합  179,344 토큰
            캐시 합  120,768 토큰   🔴 **67%가 캐시다**
            비용 합  $0.0448         ⚠️ 하루 상한 $3 의 **1.5%**

        🔴 도구 루프는 턴마다 대화를 **다시 보낸다** — 그 앞부분은 §2 가 노린
           **캐시**다(`cached_input: 0.06` vs `input: 0.30` · 다섯 배 싸다).
        ⚠️ 그것을 제값으로 세면 조사가 아니라 **세는 방법**이 막는다.
        🔴 그래서 **새로 보낸 입력**만 센다. ⚠️ 비용(`usd`)은 그대로 제값이다 —
           캐시도 돈을 내고, `cost_usd` 가 그 단가를 쓴다.
        """
        u = usage or {}
        cached = int((u.get("prompt_tokens_details") or {})
                     .get("cached_tokens") or 0)
        self.cached_tokens += cached
        self.input_tokens += max(0, int(u.get("prompt_tokens") or 0) - cached)
        self.output_tokens += int(u.get("completion_tokens") or 0)
        self.calls += 1
        got = cost_usd(u)
        self.usd = round(self.usd + got, 6)
        ok, why = self.can_call()
        if not ok and not self.blocked:
            self.blocked = why
        return got

    def line(self) -> str:
        """카드 머리에 적을 한 줄(§2 *"카드 머리에 그 경기 비용을 적는다"*)."""
        c = self.caps
        out = (f"Solar {self.calls}회 · 입력(새로) {self.input_tokens:,}/"
               f"{int(c.get('input_tokens') or 0):,} · 출력 "
               f"{self.output_tokens:,}/{int(c.get('output_tokens') or 0):,} · "
               f"캐시 {self.cached_tokens:,} · ${self.usd:.4f}")
        if not price().get("verified_by_user"):
            # 🔴 단가를 콘솔로 확인하지 못했다 — 그 사실을 숨기지 않는다
            out += " ⚠️ 단가 미확인(§2)"
        if self.blocked:
            out += f" · 🔴 {self.blocked}"
        return out


def _ledger_path(now: datetime | None = None) -> Path:
    when = now or datetime.now(timezone.utc)
    tpl = str(budget_cfg().get("ledger_path") or "ledger/cost_{YYYYMM}.jsonl")
    return ROOT / tpl.replace("{YYYYMM}", when.strftime("%Y%m"))


def spent(*, now: datetime | None = None) -> tuple[float, float]:
    """🔴 **이번 달·오늘 쓴 돈**(원장을 읽어 센다). `(월, 일)`.

    ⚠️ 원장이 없으면 `(0, 0)` 이다 — 그것이 *"아직 안 썼다"* 와 같은 뜻이다.
    🔴 메모리에 들고 다니지 않는다 — 프로세스가 죽으면 한도가 리셋되고,
       그러면 월 상한이 **없는 것**이 된다.
    """
    when = now or datetime.now(timezone.utc)
    path = _ledger_path(when)
    if not path.is_file():
        return 0.0, 0.0
    day = when.strftime("%Y-%m-%d")
    mo = d = 0.0
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        got = float(row.get("usd") or 0)
        mo += got
        if str(row.get("at") or "").startswith(day):
            d += got
    return round(mo, 6), round(d, 6)


def gate(*, now: datetime | None = None) -> tuple[bool, str]:
    """🔴🔴 **하루·월 상한.** 넘으면 호출 자체를 막는다(§2).

    > 하루 $3.0 → 그날 나머지 경기 자료 부족, 사용자에게 알림
    > 월 $40 → 🔴 **봇 정지, 사용자 승인 전 재개 금지**
    """
    b = budget_cfg()
    mo, day = spent(now=now)
    cap_m = float(b.get("per_month_usd") or 0)
    cap_d = float(b.get("per_day_usd") or 0)
    if cap_m and mo >= cap_m:
        return False, (f"{MONTH_STOP}: 이번 달 ${mo:.4f} / 상한 ${cap_m:.2f} — "
                       f"🔴 **봇 정지.** 사용자 승인 전 재개하지 않는다(§2)")
    if cap_d and day >= cap_d:
        return False, (f"{DAY_STOP}: 오늘 ${day:.4f} / 상한 ${cap_d:.2f} — "
                       f"그날 나머지 경기는 자료 부족으로 둔다(§2)")
    return True, ""


#: 🔴🔴 **M49 — 원장 줄의 필수 칸**(작업 지시서 §1).
#
#  > 원장 매 줄에 `in`·`cache`·`out` 토큰과 USD **필수** — `None` 이면 기록 실패
#
#  ⚠️ 실측 2026-10-04: 원장을 읽으려 하니 `in`·`out` 이 **없었다**(칸 이름이
#     `prompt_tokens` 였다). 🔴 그리고 `ledgerkind.cost_of` 는 `cost_usd` 를
#     찾는데 원장은 `usd` 를 적었다 — **늘 0 이었다.** 이름이 갈리면 그 기록은
#     있어도 없는 것이다.
LEDGER_REQUIRED: tuple[str, ...] = ("in", "cache", "out", "usd")

#: 🔴 **Solar 에만** 필수인 칸 — 지시서 §1-4 (2026-10-05).
#
#  > 추론 강도가 low 인지 **원장에 기록해** 확인한다.
#
#  ⚠️ 설정에 적혀 있는 것과 **실제로 보낸 것**이 같은지는 원장만 말한다(실측
#     2026-10-04: 출력이 상한을 넘은 까닭이 추론 토큰이었고 확인할 길이 없었다).
#  🔴 `LEDGER_REQUIRED` 에 넣지 **않는다** — 그 목록은 **모든 공급자**에
#     적용되고, DeepSeek 는 추론 강도 손잡이가 없다(그 줄이 터진다).
LEDGER_REQUIRED_SOLAR: tuple[str, ...] = ("reasoning_effort",)


def write_ledger(row: dict, *, now: datetime | None = None,
                 root: Path | None = None) -> Path:
    """🔴 매 호출 한 줄(§2). ⚠️ **고치지 않는다 — 더하기만 한다.**

    🔴 **M49** — `in`·`cache`·`out`·`usd` 가 없거나 `None` 이면 **터진다.**
       ⚠️ 조용히 빈 줄을 쌓으면 그 원장으로는 아무것도 못 잰다(#3).
    """
    need = list(LEDGER_REQUIRED)
    # 🔴 공급자마다 더 요구하는 칸이 있다(§1-4: Solar 는 추론 강도를 적는다)
    if str(row.get("provider") or "") == "solar":
        need += list(LEDGER_REQUIRED_SOLAR)
    missing = [k for k in need if row.get(k) is None]
    if missing:
        raise ValueError(
            f"🔴 M49 — 원장 줄에 필수 칸이 없다(`None`): {missing} · "
            f"있는 칸 {sorted(row)}")
    path = _ledger_path(now) if root is None else (
        root / _ledger_path(now).name)
    path.parent.mkdir(parents=True, exist_ok=True)
    when = now or datetime.now(timezone.utc)
    out = {"at": when.isoformat(), **row}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False) + "\n")
    return path


class SolarUnavailable(RuntimeError):
    """🔴 §2 — 타임아웃·재시도 소진·키 없음. 사유는 `llm_unavailable`."""


def chat(messages: list[dict], *, tools: list | None = None,
         schema: dict | None = None, budget: MatchBudget | None = None,
         match: str = "", now: datetime | None = None,
         _net=None) -> dict:
    """🔴 한 번 호출한다. **가드를 먼저 묻고**, 쓴 뒤 원장에 적는다.

    ⚠️ `_net` 은 시험용 대역이다 — 운영에서는 `None` 이고 실제로 나간다.
    🔴 `tools` 와 `schema` 를 **함께 주지 않는다** — 도구를 쓰는 턴은 도구 호출로
       끝나고, 마지막 `done` 턴에서만 스키마를 강제한다(§3-2).
    """
    from app.config import get_settings
    s = get_settings()
    if not s.solar_ready:
        raise SolarUnavailable(f"{LLM_UNAVAILABLE}: UPSTAGE_API_KEY 가 없다")
    ok, why = gate(now=now)
    if not ok:
        raise SolarUnavailable(why)
    if budget is not None:
        ok, why = budget.can_call()
        if not ok:
            raise SolarUnavailable(why)

    c = cfg()
    m = dict(c.get("model") or {})
    body = {"model": str(m.get("name") or "solar-pro4"),
            "messages": list(messages),
            "max_tokens": int((budget_cfg().get("per_match") or {})
                              .get("output_tokens") or 20_000)}
    if m.get("reasoning_effort"):
        body["reasoning_effort"] = str(m["reasoning_effort"])
    if tools:
        body["tools"] = list(tools)
    if schema:
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": schema}

    got = (_net or _post)(str(m.get("base_url")), s.upstage_api_key, body,
                          int(m.get("timeout_sec") or 120),
                          int(m.get("retries") or 2))
    usage = dict(got.get("usage") or {})
    usd = budget.took(usage) if budget is not None else cost_usd(usage)
    # 🔴🔴 **M49** — `in`·`cache`·`out`·`usd` 를 **그 이름으로** 적는다.
    #    ⚠️ 종전 이름(`prompt_tokens` …)은 읽는 쪽과 갈렸다(실측 2026-10-04).
    cached = int((usage.get("prompt_tokens_details") or {})
                 .get("cached_tokens") or 0)
    write_ledger({"match": match, "provider": "solar",
                  "model": got.get("model") or body["model"],
                  "usd": usd,
                  # 🔴 `in` 은 **새로 보낸 것**(캐시를 뺀 것)이다 — 예산이
                  #    세는 것과 같은 수여야 둘이 안 갈린다.
                  "in": max(0, int(usage.get("prompt_tokens") or 0) - cached),
                  "cache": cached,
                  "out": int(usage.get("completion_tokens") or 0),
                  "reasoning": int((usage.get("completion_tokens_details")
                                    or {}).get("reasoning_tokens") or 0),
                  # 🔴🔴 **추론 강도를 원장에 적는다** — 지시서 §1-4 (2026-10-05).
                  #    ⚠️ 설정에 `low` 라 적혀 있어도 **실제로 보낸 것**이 그것
                  #       인지는 원장만 말한다(실측 2026-10-04: 출력이 상한을
                  #       넘은 까닭이 추론 토큰이었고 확인할 길이 없었다).
                  #    🔴 `body` 에 실린 값을 그대로 적는다 — 설정을 다시 읽지
                  #       않는다(그러면 *보낸 것*이 아니라 *적힌 것*이 남는다).
                  "reasoning_effort": str(body.get("reasoning_effort") or ""),
                  "price_verified": bool(price().get("verified_by_user"))},
                 now=now)
    return got


def _post(base_url: str, key: str, body: dict, timeout: int,
          retries: int) -> dict:
    """🔴 §2 — 타임아웃 120초 · 재시도 2회(지수 대기). 그래도 실패면 사유."""
    url = base_url.rstrip("/") + "/chat/completions"
    last = ""
    for i in range(max(retries, 0) + 1):
        try:
            req = urllib.request.Request(
                url, data=json.dumps(body).encode(),
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as exc:                            # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
            logger.info("[solar] 호출 실패 %d/%d — %s", i + 1, retries + 1, last)
            if i < retries:
                time.sleep(2 ** i)
    raise SolarUnavailable(f"{LLM_UNAVAILABLE}: {last}")


#: 🔴 §2 — 보내지 않는 것. ⚠️ 절대규칙 6(배당 접근 0건)과 같은 결이다.
NEVER_SEND = tuple(cfg().get("never_send") or ())


def env_key_present() -> bool:
    """⚠️ 시험이 키 유무로 건너뛸 때 쓴다 — 키를 로그에 찍지 않는다."""
    return bool((os.getenv("UPSTAGE_API_KEY") or "").strip())
