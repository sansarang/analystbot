"""🔴🔴 **오픈월드 해석기 — 모르는 팀을 그 자리에서 배운다.** 지시서 §2.

> 봇은 사용자가 **묻는 모든 경기**를 예측해야 한다. `config/leagues.yaml` 에
> 선언된 일곱 리그 밖의 경기(예: 콜롬비아 Primera A 라네로스 FC vs 아메리카 데
> 칼리)도 **"이름표 문제"로 멈추지 않고** 분석까지 간다.
> … 오픈월드는 **모르는 걸 지어내는 것이 아니라** 모르는 걸 그 자리에서
> **공개 페이지로 확인해 배우는 것**이다. — 사용자 지시서 §0

══════════════════════════════════════════════════════════════════
🔴 사다리의 **마지막 단**이다 — 순서를 바꾸지 않는다
══════════════════════════════════════════════════════════════════

    ① 질문의 리그 이름 → ② 쌓인 경기 → ③ 이름표 → ④ 팀 조회 → ⑤ 별칭표
    → ⑥ **오픈월드**(여기)

⚠️ 아는 팀은 지금처럼 **빠르고 결정적으로** 풀린다. 🔴 ⑥ 은 **모를 때만** 돈다
   — 돈이 들기 때문이다(Solar 한 번).

🔴 **확정은 코드만 한다.** Solar 는 **철자 후보만** 낸다 — 경기 URL·ID·날짜를
   내도 **버린다**(지시서 금지: *"Solar 가 낸 경기 URL·ID 로 경기를 확정하는
   것"*). 그 까닭은 하나다: 모델이 **그럴듯한 URL 을 지어낼 수 있다.**
"""
from __future__ import annotations

import datetime as dt
import logging

from app import window

logger = logging.getLogger(__name__)

#: 🔴 ⑥-1 출력 상한(토큰). 지시서 §2: *"도구 없음, 출력 1k 토큰 상한."*
MAX_OUT = 1_000

#: 🔴 ⑥-1 은 **도구를 주지 않는다** — 철자만 묻는 좁은 질문이다.
TOOLS = None

#: 🔴🔴 **모델이 내도 버리는 칸들** — 지시서 §5 M54.
#
#  ⚠️ 모델이 `match_url` 을 그럴듯하게 **지어낸다**. 🔴 그것으로 경기를 확정하면
#     남의 경기(또는 없는 경기)를 분석하고, 그 카드는 통째로 거짓이 된다(M14).
BANNED_KEYS: tuple[str, ...] = ("match_url", "match_id", "url", "kickoff",
                                "starts_utc", "game_id", "ext_id", "score")


def may_run(*, resolved_names: list[str], _spy: list | None = None
            ) -> tuple[bool, str]:
    """🔴 ⑥ 을 돌려도 되나 — **하나라도 못 풀렸을 때만**(§5 M53).

    ⚠️ `_spy` 는 시험이 *"Solar 를 불렀나"* 를 보는 자리다. 🔴 운영에서는
       `None` 이고, 이 함수는 **아무것도 부르지 않는다**(판단만 한다).
    """
    unresolved = [i for i, n in enumerate(resolved_names)
                  if not str(n or "").strip()]
    if not unresolved:
        return False, ("이름표가 **두 팀 다** 풀었다 — ⑥ 을 돌리지 않는다"
                       "(돈이 든다 · §5 M53)")
    return True, f"이름표가 {len(unresolved)}팀을 못 풀었다 — ⑥ 으로 간다"


def system_prompt() -> str:
    """🔴 ⑥-1 — **철자 후보만** 묻는다. ⚠️ 경기를 고르라고 하지 않는다."""
    return (
        "너는 스포츠 팀 이름의 **철자 후보**만 낸다. 경기를 고르지 않는다.\n"
        "사용자 문장에서 두 팀을 찾아 JSON 만 낸다:\n"
        '{"teams":[{"ko":"<사용자가 쓴 이름>",'
        '"latin_candidates":["<라틴 표기1>","<표기2>"],'
        '"country_guess":"<ISO 2글자 또는 \\"\\">"}],'
        '"date_hint":"","competition_hint":""}\n'
        "🔴 경기 URL·ID·킥오프를 **넣지 마라** — 코드가 공개 페이지로 확인한다.\n"
        "🔴 모르면 빈 문자열로 둬라. 지어내지 마라.")


def parse_names(said: dict) -> tuple[dict, list[str]]:
    """🔴 ⑥-1 응답 → `(쓸 것, 버린 칸들)`. **§5 M54.**

    🔴 **버린 칸을 로그로 남긴다**(#3) — 모델이 무엇을 넣으려 했는지가 그
       모델을 고칠 재료다. ⚠️ 조용히 버리면 같은 일이 계속 난다.
    """
    dropped: list[str] = []
    out: dict = {"teams": [], "date_hint": "", "competition_hint": ""}
    for k in BANNED_KEYS:
        if said.get(k):
            dropped.append(f"{k}={str(said[k])[:60]}")
    for t in (said.get("teams") or [])[:2]:
        row = {"ko": str((t or {}).get("ko") or "").strip(),
               "latin_candidates": [str(x).strip() for x in
                                    ((t or {}).get("latin_candidates") or [])
                                    if str(x).strip()][:4],
               "country_guess": str((t or {}).get("country_guess")
                                    or "").strip()[:2].upper()}
        for k in BANNED_KEYS:
            if (t or {}).get(k):
                dropped.append(f"teams[].{k}={str(t[k])[:40]}")
        out["teams"].append(row)
    out["date_hint"] = str(said.get("date_hint") or "").strip()[:20]
    out["competition_hint"] = str(said.get("competition_hint") or "").strip()[:60]
    if dropped:
        logger.info("[openworld] ⑥-1 **버린 칸** %d개(§5 M54 — 확정은 코드만): %s",
                    len(dropped), " · ".join(dropped[:4]))
    return out, dropped


def read_names(text: str, *, budget=None, _chat=None
               ) -> tuple[dict, list[str], str]:
    """🔴🔴 ⑥-1 **입력 해석**(Solar, 좁은 질문 하나). `(쓸 것, 버린 칸, 사유)`.

    > 사용자 문장("라네로스 FC vs 아메리카 데 칼리")을 Solar 에 넘겨 다음 JSON
    > 만 받는다 … **Solar 는 경기를 고르지 않는다 — 철자 후보만 낸다.**
    > **도구 없음**, 출력 **1k 토큰 상한.** — 지시서 §2 ⑥-1

    ⚠️ 실패를 **삼키지 않는다** — 장애면 빈 결과와 사유를 돌려주고, 호출부가
       카드에 적는다(#3). 🔴 장애로 끊긴 것은 **재실행 대상**이다(규율 11).
    """
    from app import solar
    said = str(text or "").strip()
    if not said:
        return {}, [], "🔴 물은 문장이 비었다"
    chat = _chat or solar.chat
    try:
        got = chat(
            [{"role": "system", "content": system_prompt()},
             {"role": "user", "content": said}],
            # 🔴 **도구를 안 준다**(지시서: *"도구 없음"*)
            budget=budget, max_tokens=MAX_OUT)
    except Exception as exc:                            # noqa: BLE001
        logger.info("[openworld] ⑥-1 실패: %r", exc)
        return {}, [], f"🔴 ⑥-1 해석 실패({type(exc).__name__}) — {exc}"
    body = ((got.get("choices") or [{}])[0].get("message") or {}
            ).get("content") or ""
    import json
    import re
    m = re.search(r"\{.*\}", str(body), re.S)
    if not m:
        return {}, [], f"🔴 ⑥-1 이 JSON 을 안 냈다: {str(body)[:80]}"
    try:
        box = json.loads(m.group(0))
    except ValueError as exc:
        return {}, [], f"🔴 ⑥-1 JSON 이 깨졌다: {exc}"
    out, dropped = parse_names(box)
    n = len(out.get("teams") or [])
    return out, dropped, (f"⑥-1 철자 후보 {n}팀"
                          + (f" · 버린 칸 {len(dropped)}개" if dropped else ""))


def langs_for(country: str) -> list[str]:
    """🔴 ⑥-5 — `['en'] + babel_likely(country)`. ⚠️ 영어는 **늘 먼저**다.

    🔴 나라→언어는 `queries.langs_from_country` **한 곳**이다(사본 금지).
    """
    out = ["en"]
    code = str(country or "").strip().upper()
    if not code:
        return out
    from app import queries
    # ⚠️ `langs_from_country` 는 **`(언어들, 사유)`** 를 준다(재서 알았다) —
    #    사유를 버리지 않고 로그에 남긴다(#3).
    got, why = queries.langs_from_country(code)
    for lang in (got or []):
        if lang and lang not in out:
            out.append(lang)
    logger.info("[openworld] ⑥-5 언어 %s — %s", out, why)
    return out


def _hit(name: str, cands: list[str]) -> bool:
    """🔴 페이지의 팀명이 후보와 **같은가**. ⚠️ 정규화는 **s5** 것을 쓴다(사본 금지).

    🔴 `verifylayer` 를 지웠다(사용자 지시 2026-10-06 ⑧) — 그 내용은
       `app/core/stages/s5_verify.py` 가 들고 있다.
    """
    from app.core.stages.s5_verify import norm as _norm
    got = _norm(name)
    if not got:
        return False
    for c in cands:
        c2 = _norm(c)
        if c2 and (c2 in got or got in c2):
            return True
    return False


def pick(pages: list[dict], home_cands: list[str], away_cands: list[str], *,
         now: dt.datetime | None = None) -> tuple[dict | None, str]:
    """🔴🔴 ⑥-3 **경기 페이지 확인** — 정확히 하나면 확정. **§5 M55.**

    세 조건(지시서 §2 ⑥-3):
      (a) **두 팀** 이름이 후보와 일치 — 한쪽만 맞으면 남의 경기다
      (b) 킥오프가 **36시간 창** 안(`window.inside`)
      (c) 대회명이 있으면 기록

    🔴 **둘 이상이면 고르지 않는다** — 후보를 돌려주고 멈춘다(자동 선택 금지).
    ⚠️ 그것이 §17-g-3·M14 가 막는 것이다: 남의 경기를 분석하면 **카드 전체가
       거짓**이 된다.
    """
    kept, why = [], []
    for p in (pages or []):
        home, away = str(p.get("home") or ""), str(p.get("away") or "")
        # 🔴 (a) 두 팀 — **양쪽 배치**를 다 본다(홈·원정이 뒤집힌 페이지가 있다)
        straight = _hit(home, home_cands) and _hit(away, away_cands)
        flipped = _hit(home, away_cands) and _hit(away, home_cands)
        if not (straight or flipped):
            why.append(f"{home}–{away}: 두 팀이 후보와 안 맞는다")
            continue
        kick = p.get("kickoff")
        if not isinstance(kick, dt.datetime):
            why.append(f"{home}–{away}: 킥오프 시각이 없다")
            continue
        # 🔴 (b) 36시간 창
        said = window.why_out(kick, now=now)
        if said:
            why.append(f"{home}–{away}: {said}")
            continue
        kept.append(dict(p, flipped=flipped))
    if not kept:
        from app.reasons import Reason
        return None, (f"🔴 `{Reason.OPENWORLD_NOT_FOUND.value}` — 창 안에서 "
                      f"**두 팀이 맞는 경기가 0개**다. 탈락 {len(why)}건: "
                      + " · ".join(why[:3]))
    if len(kept) > 1:
        # 🔴 **고르지 않는다** — 사용자 몫이다(M55)
        rows = " · ".join(f"{k.get('competition') or '대회 미상'} "
                          f"{k.get('url')}" for k in kept[:4])
        return None, (f"🔴 맞는 경기가 **{len(kept)}건**이다 — 고르는 것은 "
                      f"사용자 몫이다(§17-g-3 · M55): {rows}")
    return kept[0], f"✅ 정확히 하나 — {kept[0].get('competition') or '대회 미상'}"


async def pages_from(urls, *, net=None, sport: str = "soccer") -> tuple[
        list[dict], list[str]]:
    """🔴🔴 ⑥-2 결과(URL) → ⑥-3 **후보 경기들**. `(후보, 탈락 사유)` — §3-1.

    > ⑥-3 에서 받은 경기 페이지에 이미 대회·구장·심판·예상/확정 XI·최근 폼·
    > 상대전이 있는 경우가 많다 … 그 페이지를 **기존 fotmob HTML 파서로 그대로
    > 읽어** `Fact`(v5 §8-3)로 만든다. **새 파서를 짓지 않는다.** — 지시서 §3-1

    🔴 **제 파서를 짓지 않는다** — `fotmob.slate_row` 가 그 일을 한다.
    🔴 **§5 M58** — robots·도메인 등급을 **지나야** 한다(`net` 이 robots 를
       보고 `domains.verdict` 가 등급을 본다). ⚠️ 팁 사이트는 근거가 못 된다.
    ⚠️ 탈락을 **사유로** 돌려준다(#3) — *"0개"* 만 적으면 왜인지 모른다.
    """
    from app import domains
    from app.collect import fotmob
    from app.net import Net

    out: list[dict] = []
    why: list[str] = []
    net = net or Net(cache=True)
    for url in (urls or []):
        u = str(url or "")
        if not u:
            continue
        # 🔴 M58 — **도메인 등급**(§4-3). 팁·거부 등급은 안 쓴다
        ok_d, tier, said = domains.verdict(u, sport=sport)
        if not ok_d:
            why.append(f"{u[:60]} — {said[:80]}")
            continue
        if not fotmob.is_match_page(u):
            why.append(f"{u[:60]} — 경기 페이지 꼴이 아니다")
            continue
        got = await net.get(u)        # 🔴 `net` 이 robots 를 본다(절대규칙 3)
        if not getattr(got, "ok", False):
            why.append(f"{u[:60]} — {getattr(got, 'reason', '응답 실패')}")
            continue
        # 🔴 **기존 파서**다 — 새로 짓지 않는다(§3-1)
        row = fotmob.slate_row(got)
        if not row:
            why.append(f"{u[:60]} — 슬레이트 행을 못 만들었다")
            continue
        out.append({"home": row.get("home"), "away": row.get("away"),
                    "kickoff": row.get("starts_utc"),
                    "competition": row.get("league") or row.get("round_note")
                    or "", "url": u, "sport": row.get("sport") or sport,
                    "home_ext": row.get("ext_id") or "",
                    "row": row})
    return out, why


def provision(page: dict, *, ko: list[str], latin: list[list[str]],
              country: str = "") -> list[dict]:
    """🔴🔴 ⑥-4 **임시 열쇠 발급.** `provisional:true`·`learned_from` 필수(M56).

    ⚠️ 열쇠는 **발급기가** 준다(v5 §8-1) — 여기서 번호를 짓지 않는다.
    🔴 별칭은 **그 번호 밑에만** 넣는다 — *"이름끼리 연결하지 않는다"*(지시서).
       그렇게 하면 `아메리카` 가 `América de Cali` 를 거쳐 다른 팀에 붙는 일이
       없다(이름을 신원으로 쓰는 길을 막는다).
    """
    from app import teamref
    reg = teamref.registry()
    url = str(page.get("url") or "")
    comp = str(page.get("competition") or "")
    sides = ("away", "home") if page.get("flipped") else ("home", "away")
    out: list[dict] = []
    for i, which in enumerate(sides):
        name = str(page.get(which) or "").strip()
        if not name:
            continue
        aliases = [name]
        if i < len(ko) and str(ko[i] or "").strip():
            aliases.append(str(ko[i]).strip())
        for c in (latin[i] if i < len(latin) else []):
            # 🔴 **페이지와 맞은 철자만** 넣는다(모델 후보를 전부 믿지 않는다)
            if str(c).strip() and _hit(name, [str(c)]):
                aliases.append(str(c).strip())
        ext = str(page.get(f"{which}_ext") or "")
        if ext:
            aliases.append(ext)
        key = reg.key_for(ext=ext, name=name, league=comp, sport=str(
            page.get("sport") or "soccer"))
        seen, uniq = set(), []
        for a in aliases:
            if a and a not in seen:
                seen.add(a)
                uniq.append(a)
        out.append({"key": key, "name": name, "aliases": uniq,
                    "provisional": True,
                    # 🔴 **어느 경기에서 배웠나** — 없으면 승격도 되돌림도 못 한다
                    "learned_from": url or f"{comp}:{name}",
                    "country": str(country or "").upper(),
                    "league": comp, "langs": langs_for(country)})
    return out
