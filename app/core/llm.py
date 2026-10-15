"""🔴🔴 **v6 §4 — LLM 호출 함수 하나.** 앱 어디서든 LLM 은 `ask` 로만 부른다.

지시서 §4: *"`openai` SDK·`httpx` 로 LLM 을 직접 부르는 코드가 `app/` 에 남아
있으면 **빌드 실패**(§7 정적 검사)."*

══════════════════════════════════════════════════════════════════
🔴 왜 **구조화 출력**인가 — 10-06 결함 ②의 전부가 여기서 사라진다
══════════════════════════════════════════════════════════════════

산문 파싱이 만든 실측 결함들:

| 무엇 | 어떻게 막히나 |
|---|---|
| `team: "Jamaica"`(이름) | `subject` 를 **그 경기 두 열쇠만** 허용하는 enum 으로 |
| `url: "en.wikipedia.org"`(머리표 아님) | `doc_id` 를 **그 하위에 넘긴 id 만** 허용하는 enum 으로 |
| `type` 이 카탈로그 밖 | `type` 을 **그 하위 담당 유형만** 허용하는 enum 으로 |
| `direction_hint` 자유 문장 | 출력 모델에 **방향 칸이 없다**(코드가 정한다) |
| 산문 속 ```json · `done` 미호출 | `response_format=json_schema(strict)` |
| 추론이 출력 상한을 다 먹고 content 0자 | `purpose` 별 추론 강도 + `length` 는 **실패**로 |

🔴 **모델이 다른 값을 낼 길이 없다** — 그것이 이 파일의 값어치다.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ValidationError

from app.core.schema import DropReason, LlmFail
from app.core.state import RunState

T = TypeVar("T", bound=BaseModel)

Provider = Literal["solar", "deepseek"]


class Message(BaseModel):
    """🔴 보내는 한 줄. ⚠️ 사전을 직접 넘기지 않는다(§9: 경계에 dict 금지)."""

    role: Literal["system", "user", "assistant"]
    content: str


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **스키마 변환** — Upstage strict 규칙(§4)
# ══════════════════════════════════════════════════════════════════
#
# > 모든 object 에 `additionalProperties: false`, 모든 속성을 `required` 에 넣고,
# > 선택 칸은 타입에 `null` 을 더해 표현한다.
#
# ⚠️ pydantic 의 `model_json_schema()` 는 그 규칙을 **안 지킨다** — 선택 칸을
#    `required` 에서 빼고 `$defs` 로 참조를 만든다. 🔴 그래서 변환이 필요하다.


def strict_schema(model: type[BaseModel], *,
                  enums: dict[str, list[str]] | None = None) -> dict:
    """🔴🔴 pydantic 모델 → **strict JSON 스키마**(§4 규칙 그대로).

    `enums` 는 **그 요청에서만** 쓰는 열거값이다 — `{"subject": [열쇠 둘],
    "doc_id": [그 하위 문서 id], "type": [담당 유형]}`.
    🔴 경기마다 달라지는 값을 **요청마다 스키마에 박는다**(§4) — 그러면 모델이
       다른 값을 낼 길이 없다.
    """
    raw = model.model_json_schema()
    defs = dict(raw.pop("$defs", {}) or {})
    out = _inline(raw, defs, enums or {})
    return _strictify(out, enums or {})


def _inline(node: Any, defs: dict, enums: dict) -> Any:
    """🔴 `$ref` 를 펼친다 — strict 스키마는 참조를 받지 않는 쪽이 안전하다.

    ⚠️ 재귀 모델은 펼칠 수 없다 — 지금 경계 타입에 재귀는 없고, 생기면 여기서
       터진다(조용히 틀린 스키마를 보내지 않는다).
    """
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            name = ref.split("/")[-1]
            if name not in defs:
                raise KeyError(f"🔴 스키마 참조를 못 찾았다: {ref}")
            return _inline(dict(defs[name]), defs, enums)
        return {k: _inline(v, defs, enums) for k, v in node.items()}
    if isinstance(node, list):
        return [_inline(x, defs, enums) for x in node]
    return node


def _strictify(node: Any, enums: dict, *, key: str = "") -> Any:
    """🔴 object 마다 `additionalProperties: false` + 전 속성 `required`.

    🔴 **선택 칸은 타입에 `null` 을 더한다** — `required` 에서 빼지 않는다(§4).
    ⚠️ `enums` 에 이름이 있으면 그 자리의 타입을 **열거값으로 갈아 끼운다.**
    """
    if isinstance(node, list):
        return [_strictify(x, enums) for x in node]
    if not isinstance(node, dict):
        return node
    box = {k: _strictify(v, enums, key=k if k == "properties" else key)
           for k, v in node.items()}
    props = box.get("properties")
    if isinstance(props, dict):
        new_props = {}
        for name, sub in props.items():
            if name in enums:
                # 🔴 **그 요청만의 열거값** — 설명은 지킨다(모델이 읽는다)
                said_desc = ({"description": sub["description"]}
                             if isinstance(sub, dict) and "description" in sub
                             else {})
                # ══════════════════════════════════════════════════════
                # 🔴🔴 **배열 칸이면 `items` 에 넣는다** — 실사고 2026-10-14
                # ══════════════════════════════════════════════════════
                #
                #  ⚠️ 종전엔 열거 칸을 **무조건 `string`** 으로 갈아끼웠다. 그래서
                #     `list[str]` 칸(`langs`)이 **스칼라가 됐고**, 모델이
                #     `["nl","it"]` 를 내면 strict 스키마가 거부했다 —
                #     `solar` 가 `LLM_SCHEMA` 로 떨어진 그 까닭이다(실측).
                #  🔴 배열인지는 **원래 스키마의 `type`** 으로 가린다(추측 금지).
                if isinstance(sub, dict) and str(sub.get("type")) == "array":
                    sub = {"type": "array",
                           "items": {"type": "string",
                                     "enum": list(enums[name])},
                           **said_desc}
                else:
                    sub = {"type": "string", "enum": list(enums[name]),
                           **said_desc}
            new_props[name] = sub
        box["properties"] = new_props
        box["additionalProperties"] = False
        # 🔴 **전부 required** — 선택 칸은 타입에 `null` 이 들어 있다
        box["required"] = list(new_props)
        # ⚠️ `default` 는 strict 가 안 받는다 — 걷는다(값은 코드가 채운다)
        for sub in new_props.values():
            if isinstance(sub, dict):
                sub.pop("default", None)
    return box


# ══════════════════════════════════════════════════════════════════
# 설정 — 🔴 숫자는 `config/llm.yaml` 하나가 든다(§0 원칙 5)
# ══════════════════════════════════════════════════════════════════


def cfg() -> dict:
    from app import rules
    return dict(rules._load("config/llm.yaml") or {})


def purpose_cfg(purpose: str) -> dict:
    """🔴 그 용도의 수 — 추론 강도·출력 상한·타임아웃·재시도.

    ⚠️ 표에 없으면 **기본값**이 아니라 터진다 — 용도를 늘릴 때 수를 같이 적게
       만든다(실측 없이 숫자를 정하지 않는다 · §9).
    """
    box = ((cfg().get("v6") or {}).get("purposes") or {}).get(str(purpose))
    if not box:
        raise KeyError(
            f"🔴 `config/llm.yaml` 의 `v6.purposes.{purpose}` 가 없다 — "
            f"용도를 늘릴 때 수(추론 강도·상한)를 **실측으로** 같이 적는다(§9)")
    return dict(box)


def provider_cfg(provider: str) -> dict:
    box = (cfg().get("v6") or {}).get("providers") or {}
    got = dict(box.get(str(provider)) or {})
    if not got:
        raise KeyError(f"🔴 `v6.providers.{provider}` 가 설정에 없다")
    return got


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 **호출 — 이 함수 하나다**
# ══════════════════════════════════════════════════════════════════


def ask(*, provider: Provider, purpose: str, messages: list[Message],
        out: type[T], state: RunState,
        enums: dict[str, list[str]] | None = None,
        _post=None) -> T | LlmFail:
    """🔴🔴 **LLM 을 부르는 유일한 자리**(§4). `out` 타입 또는 `LlmFail`.

    🔴 **예외를 위로 던지지 않는다** — 단계가 빈 출력 + 사유로 계속 가야 하고,
       카드는 **항상** 나와야 한다(§5).
    """
    p = purpose_cfg(purpose)
    pv = provider_cfg(provider)
    schema = strict_schema(out, enums=enums)
    body = _body(pv, p, messages, schema, provider=provider)
    ok, why = _wallet_ok(state)
    if not ok:
        return LlmFail(reason=DropReason.BUDGET_CUT, detail=why)

    said = ""
    for attempt in (0, 1):                 # 🔴 검증 실패는 **1회만** 재요청(§4)
        t0 = time.monotonic()
        got, fail = _send(body, pv, provider=provider, purpose=purpose,
                          state=state, secs0=t0, _post=_post)
        if fail is not None:
            return fail
        said = got
        try:
            return out.model_validate_json(said)
        except ValidationError as exc:
            if attempt == 1:
                return LlmFail(
                    reason=DropReason.LLM_SCHEMA,
                    detail=f"두 번 다 스키마에 안 맞았다: {exc.errors()[:2]}")
            # 🔴 상한을 넘겼으면 **다시 묻지 않는다**(지시 2026-10-15) —
            #    재요청 한 번이 남은 예산을 통째로 먹던 자리다
            got_clock = getattr(state, "clock", None)
            if got_clock is not None and getattr(got_clock, "over", bool)():
                return LlmFail(
                    reason=DropReason.LLM_TIMEOUT,
                    detail=("⏱ 상한을 넘겨 **스키마 재요청을 건너뛴다** — "
                            f"{exc.errors()[:1]}"))
            # 🔴 **오류 문장을 붙여** 다시 묻는다 — 무엇이 틀렸는지 알려 준다
            body = dict(body)
            body["messages"] = [*body["messages"],
                                {"role": "assistant", "content": said},
                                {"role": "user",
                                 "content": ("🔴 위 JSON 이 스키마에 안 맞는다. "
                                             f"오류: {exc.errors()[:3]} — "
                                             "같은 내용을 스키마대로 다시 내라.")}]
    return LlmFail(reason=DropReason.LLM_SCHEMA, detail="재요청도 실패했다")


def _body(pv: dict, p: dict, messages: list[Message], schema: dict, *,
          provider: str) -> dict:
    """🔴 보내는 몸통. ⚠️ `tools` 는 **없다** — v6 에 도구 루프가 없다(§6)."""
    body: dict[str, Any] = {
        "model": str(pv.get("model") or ""),
        "messages": [m.model_dump() for m in messages],
        "max_tokens": int(p.get("max_tokens") or 0)}
    eff = str(p.get("reasoning_effort") or "")
    if eff:
        body["reasoning_effort"] = eff
    # ══════════════════════════════════════════════════════════════════
    # 🔴🔴 **온도를 설정이 정한다** — 사용자 지시 2026-10-06 ⑤
    # ══════════════════════════════════════════════════════════════════
    #
    #  > 추출 `temperature=0` 고정, 같은 입력이면 같은 출력인지 2회 실측해 보고.
    #
    #  ⚠️ 실측 2026-10-06: 같은 경기를 여섯 번 돌렸더니 변수가 14·5·18·19·15·19 로
    #     갈렸다 — 그래서 등급이 서기도 안 서기도 했다(`자료부족` ↔ `소액하단`).
    #  🔴 `0` 과 "안 보냄"은 다르다 — `None` 이면 보내지 않는다(공급자 기본값).
    if p.get("temperature") is not None:
        body["temperature"] = float(p["temperature"])
    mode = str(pv.get("structured") or "json_schema")
    if mode == "json_schema":
        # 🔴 Solar 실측 2026-10-04: `json_schema(strict)` 가 **듣는다**
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "out", "strict": True, "schema": schema}}
    else:
        # ⚠️ `json_object` 만 되는 공급자 — 스키마를 **프롬프트에 붙이고**
        #    돌아온 것을 `model_validate_json` 이 검증한다(§4).
        body["response_format"] = {"type": "json_object"}
        body["messages"] = [*body["messages"], {
            "role": "user",
            "content": ("🔴 아래 JSON 스키마를 **정확히** 지켜 답한다(다른 칸을 "
                        "더하지 않는다):\n" + json.dumps(schema,
                                                      ensure_ascii=False))}]
    return body


def _wallet_ok(state: RunState) -> tuple[bool, str]:
    """🔴 예산 판정은 **지갑 하나**로(§4)."""
    if state.wallet.blocked:
        return False, state.wallet.blocked
    from app import solar
    ok, why = solar.gate()
    if not ok:
        state.wallet.blocked = why
        return False, why
    cap = float((cfg().get("v6") or {}).get("per_match_usd") or 0)
    if cap and state.wallet.usd >= cap:
        why = (f"budget_cut: 이 경기에 ${state.wallet.usd:.4f} 를 썼다 "
               f"(상한 ${cap:.2f})")
        state.wallet.blocked = why
        return False, why
    return True, ""


def _send(body: dict, pv: dict, *, provider: str, purpose: str,
          state: RunState, secs0: float, _post) -> tuple[str, LlmFail | None]:
    """🔴 한 번 보낸다 — 카세트를 거치고 원장에 적는다. `(글, 실패)`."""
    from app import cassette
    url = str(pv.get("base_url") or "").rstrip("/") + "/chat/completions"
    qs = _key_of(body)
    if cassette.mode() == cassette.REPLAY:
        try:
            got = cassette.load("llm", url, qs)
        except cassette.CassetteMiss as exc:
            if not cassette.fallthrough():
                return "", LlmFail(reason=DropReason.REPLAY_MISS,
                                   detail=str(exc))
            got = None
        if got is not None:
            return _read(got, provider=provider, purpose=purpose, state=state,
                         secs0=secs0, body=body, replayed=True)
    # 🔴🔴 **타임아웃은 남은 예산 안이다** — 사용자 지시 2026-10-15.
    #    ⚠️ 실사고 2026-10-15: 공급자가 응답을 안 끊어 한 호출이 4분(소켓 120초
    #       × 스키마 재요청 2회)을 먹었고, 카드 하나가 **27분**이 됐다.
    #    🔴 상한을 세는 곳은 `core/deadline` 하나다(사본 금지).
    from app.core import deadline as _dl
    secs, said_cap = _dl.call_cap_sec(getattr(state, "clock", None),
                                      int(pv.get("timeout_sec") or 120))
    if said_cap:
        # 🔴 사유는 **상태 수첩**에 남긴다 — 카드·보고가 그것을 적는다
        state.note(f"llm {purpose} — {said_cap}")
    if secs <= 0:
        # 🔴 **안 부른다** — 사유를 남긴다(#3 조용한 0 금지)
        return "", LlmFail(reason=DropReason.LLM_TIMEOUT, detail=said_cap)
    try:
        raw = (_post or _http)(url, _key(provider), body, int(secs))
    except _Fail as exc:
        return "", LlmFail(reason=exc.reason, detail=str(exc),
                           status=exc.status)
    if cassette.mode() in (cassette.RECORD, cassette.REPLAY):
        cassette.save("llm", url, qs, dict(raw))
    return _read(raw, provider=provider, purpose=purpose, state=state,
                 secs0=secs0, body=body, replayed=False)


def _read(raw: dict, *, provider: str, purpose: str, state: RunState,
          secs0: float, body: dict, replayed: bool
          ) -> tuple[str, LlmFail | None]:
    """🔴 응답을 읽고 **원장에 한 줄** 적는다(§4). `length` 면 **실패**다."""
    ch = (raw.get("choices") or [{}])[0] or {}
    msg = dict(ch.get("message") or {})
    usage = dict(raw.get("usage") or {})
    cached = int((usage.get("prompt_tokens_details") or {})
                 .get("cached_tokens") or 0)
    out_n = int(usage.get("completion_tokens") or 0)
    reason_n = int((usage.get("completion_tokens_details") or {})
                   .get("reasoning_tokens") or 0)
    usd = _usd(provider, usage)
    if not replayed:
        state.wallet.took(usd=usd, in_=max(0, int(usage.get("prompt_tokens")
                                                  or 0) - cached),
                          out=out_n, cached=cached, reasoning=reason_n)
    finish = str(ch.get("finish_reason") or "")
    _ledger({"at": datetime.now(timezone.utc).isoformat(),
             "match": state.match_key, "provider": provider,
             "purpose": purpose, "model": raw.get("model") or body["model"],
             "reasoning_effort": str(body.get("reasoning_effort") or ""),
             "in": max(0, int(usage.get("prompt_tokens") or 0) - cached),
             "cache": cached, "out": out_n, "reasoning": reason_n,
             "usd": usd, "finish_reason": finish,
             "secs": round(time.monotonic() - secs0, 2),
             "replayed": replayed})
    if finish == "length":
        # 🔴🔴 **잘린 JSON 을 고치려 하지 않는다**(§4) — 실측 2026-10-06:
        #    `low` 가 출력 4,000 을 전부 추론에 쓰고 content 0자를 냈다.
        #    ⚠️ 상한을 올려서 해결하는 것은 §9 금지다 — 추론 강도·입력 크기다.
        return "", LlmFail(
            reason=DropReason.LLM_TRUNCATED,
            detail=(f"출력이 잘렸다 — out {out_n}(추론 {reason_n}) · "
                    f"추론 강도 {body.get('reasoning_effort') or '없음'}"))
    return str(msg.get("content") or ""), None


def _key_of(body: dict) -> str:
    """🔴 카세트 열쇠 — 같은 요청이면 같은 글자. **비밀은 가린다.**"""
    from app.secrets_mask import mask_secrets
    return mask_secrets(json.dumps(body, ensure_ascii=False, sort_keys=True))


class _Fail(RuntimeError):
    """🔴 전송 실패 — **사유가 갈려 있다**(§4)."""

    def __init__(self, said: str, *, reason: DropReason,
                 status: int | None = None) -> None:
        super().__init__(said)
        self.reason, self.status = reason, status


def _http(url: str, key: str, body: dict, timeout: int) -> dict:
    """🔴 **실제로 망에 나가는 자리 — `app/` 에 이것 하나다**(§7 정적 검사)."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        code = int(getattr(exc, "code", 0) or 0)
        if code == 429:
            raise _Fail(f"429: {exc}", reason=DropReason.LLM_429,
                        status=code) from exc
        if 500 <= code < 600:
            raise _Fail(f"HTTP {code}: {exc}",
                        reason=DropReason.LLM_HTTP_5XX, status=code) from exc
        raise _Fail(f"HTTP {code}: {exc}", reason=DropReason.LLM_HTTP_5XX,
                    status=code) from exc
    except Exception as exc:                                # noqa: BLE001
        # 🔴 응답조차 못 받았다 — **망**이다(타임아웃·DNS·끊김)
        raise _Fail(f"{type(exc).__name__}: {exc}",
                    reason=DropReason.LLM_TIMEOUT) from exc


def _key(provider: str) -> str:
    from app.config import get_settings
    s = get_settings()
    got = (s.upstage_api_key if provider == "solar" else s.deepseek_api_key)
    if not got:
        raise _Fail(f"{provider} 키가 없다", reason=DropReason.LLM_TIMEOUT)
    return str(got)


def _usd(provider: str, usage: dict) -> float:
    """🔴 단가는 설정이 든다 — 매체 수치를 쓰지 않는다(§2)."""
    price = dict(provider_cfg(provider).get("price_usd_per_1m") or {})
    cached = int((usage.get("prompt_tokens_details") or {})
                 .get("cached_tokens") or 0)
    fresh = max(0, int(usage.get("prompt_tokens") or 0) - cached)
    out_n = int(usage.get("completion_tokens") or 0)
    got = (fresh * float(price.get("input") or 0)
           + cached * float(price.get("cached_input") or price.get("input") or 0)
           + out_n * float(price.get("output") or 0)) / 1_000_000
    return round(got, 8)


def _ledger(row: dict) -> None:
    """🔴 원장 한 줄 — **성공·실패 모두** 적는다(§4)."""
    from app import solar
    path = solar._ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
