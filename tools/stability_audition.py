"""[P0 안정성] 같은 재료가 같은 숫자를 내는가 — 모델별 산포 실측.

🔴 **격리다.** 판정 캐시·원장·텔레그램에 아무것도 쓰지 않는다. 표준출력뿐.
   프롬프트는 `render_matchup_prompt` 로 **한 번** 렌더해 전 호출에 그대로
   재사용한다 — 입력이 같아야 산포가 모델 탓임을 말할 수 있다.

합격선 (지시 2026-09-05): 산포(최대-최소) ≤ 2%p **그리고** 우세 뒤집힘 0.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics


def _load_env() -> None:
    """로컬 실행용. `openai_compat` 는 `os.environ` 을 직접 읽는데 `.env` 는
    pydantic Settings 로만 들어와 **키가 없는 것처럼 보였다**(실측 2026-09-05:
    MISTRAL_API_KEY 가 .env 에 있는데 "키 없음"으로 10회 전량 실패).
    Railway 에서는 실환경변수라 이 함수가 아무것도 하지 않는다.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(here, ".env"), override=False)

#: 판정 사슬의 실후보 + 지시가 지정한 비교군.
#  ⚠️ 사본 금지 — 사슬 자체는 config(FREE_JUDGE_MODEL)가 원본이다. 여기 목록은
#     "오디션 대상"이지 운영 사슬이 아니다. `--from-chain` 으로 원본을 읽는다.
EXTRA = [
    ("mistral", "mistral-medium-latest", "Mistral Medium"),
    ("gemini", "", "Gemini Flash"),
]


def build_prompt() -> str:
    """삼성 @ LG 재료로 실판정 프롬프트를 렌더한다. 모델 호출 없음."""
    from app.engine.matchup import render_matchup_prompt

    jg = {
        "sport": "kbo", "league": "KBO", "game_id": 1710,
        "home": "LG Twins", "away": "Samsung Lions",
        "starts_at_kst": "09/05 17:00", "stadium": "잠실",
        "lineup_status": "confirmed", "pick_state": "final",
        "research": {
            "home_pitcher": {"이름": "톨허스트", "throws": "R"},
            "away_pitcher": {"이름": "이승현", "throws": "L"},
            "home_starter_recent": [
                {"opponent": "두산", "innings": 6.667, "r": 1, "hits": 4, "k": 7, "bb": 1},
                {"opponent": "키움", "innings": 6.333, "r": 1, "hits": 5, "k": 5, "bb": 2},
            ],
            "away_starter_recent": [
                {"opponent": "LG", "innings": 2.667, "r": 3, "hits": 5, "k": 2, "bb": 3},
            ],
            "home_lineup": {"order": [
                {"slot": i, "name": f"홈타자{i}", "pos": ps} for i, ps in enumerate(
                    ["CF", "SS", "LF", "1B", "DH", "RF", "3B", "C", "2B"], 1)]},
            "away_lineup": {"order": [
                {"slot": i, "name": f"원정타자{i}", "pos": ps} for i, ps in enumerate(
                    ["LF", "2B", "DH", "1B", "RF", "3B", "CF", "C", "SS"], 1)]},
        },
        "home_recent3": {"results": "WWW", "runs_per_game_l3": 5.0,
                         "runs_allowed_l3": 3.0},
        "away_recent3": {"results": "WLL", "runs_per_game_l3": 3.67,
                         "runs_allowed_l3": 4.33},
    }
    return render_matchup_prompt(jg, boxes={}, news={}, prev=None)


def read_verdict(text: str) -> tuple[float | None, str | None]:
    """응답 → (p_home, 우세). 파싱 실패는 (None, None) — 지어내지 않는다."""
    from app.engine.matchup import parse_json_object

    obj = parse_json_object(text or "")
    if not isinstance(obj, dict):
        return None, None
    p = obj.get("p_home")
    if p is None:
        for k in ("p", "확률", "home_prob"):
            if obj.get(k) is not None:
                p = obj[k]
                break
    try:
        p = float(p)
    except (TypeError, ValueError):
        return None, obj.get("우세")
    if p > 1.0:
        p = p / 100.0
    return round(p, 4), obj.get("우세")


async def call_once(provider: str, model: str, prompt: str, budget: int,
                    seed: int | None = None) -> dict:
    """1콜. **예외를 던지지 않는다** — 실패도 데이터다."""
    if provider == "gemini":
        from app.llm import gemini

        if not gemini.is_available():
            return {"ok": False, "error": "GEMINI_API_KEY 없음"}
        try:
            txt = await gemini.generate(prompt, max_tokens=budget)
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return {"ok": bool(txt), "text": txt or "", "error": None}
    from app.llm.openai_compat import complete

    r = await complete(provider, model, prompt, max_tokens=budget,
                       reasoning=True, seed=seed)
    return {"ok": bool(r["ok"]), "text": r.get("text") or "",
            "error": r.get("error"), "status": r.get("status"),
            "elapsed": r.get("elapsed")}


async def audition(provider: str, model: str, label: str, prompt: str,
                   reps: int, budget: int, seed: int | None = None) -> dict:
    out = {"provider": provider, "model": model, "label": label,
           "ps": [], "sides": [], "fail": 0, "errors": []}
    for i in range(reps):
        r = await call_once(provider, model, prompt, budget, seed)
        if not r.get("ok"):
            out["fail"] += 1
            out["errors"].append(str(r.get("error"))[:100])
            print(f"    {i+1:2d}/{reps}  실패 — {str(r.get('error'))[:70]}",
                  flush=True)
            continue
        p, side = read_verdict(r.get("text") or "")
        if p is None:
            out["fail"] += 1
            out["errors"].append("파싱 실패")
            print(f"    {i+1:2d}/{reps}  파싱 실패 ({len(r.get('text') or '')}자)",
                  flush=True)
            continue
        out["ps"].append(p)
        out["sides"].append(side or ("home" if p >= 0.5 else "away"))
        print(f"    {i+1:2d}/{reps}  p_home={p:.3f}  우세={out['sides'][-1]}",
              flush=True)
    return summarize(out)


def summarize(out: dict) -> dict:
    ps = out["ps"]
    if ps:
        out["n"] = len(ps)
        out["mean"] = round(statistics.fmean(ps), 4)
        out["stdev_pp"] = round(statistics.pstdev(ps) * 100, 2) if len(ps) > 1 else 0.0
        out["range_pp"] = round((max(ps) - min(ps)) * 100, 2)
        out["min"], out["max"] = min(ps), max(ps)
        # 우세 뒤집힘 = 최빈 우세와 다른 회차 수. 50% 선을 넘나든 횟수다.
        top = max(set(out["sides"]), key=out["sides"].count)
        out["flips"] = sum(1 for s in out["sides"] if s != top)
        out["pass"] = out["range_pp"] <= 2.0 and out["flips"] == 0
    else:
        out.update(n=0, mean=None, stdev_pp=None, range_pp=None,
                   flips=None, **{"pass": False})
    return out


def chain_candidates() -> list[tuple[str, str, str]]:
    """운영 사슬을 **원본에서** 읽는다 — 목록을 손으로 적지 않는다."""
    from app.llm.judge_route import chain

    return [(p, m, f"{p}/{m.split('/')[-1]}") for p, m in chain("matchup")]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--budget", type=int, default=0,
                    help="max_tokens. 0이면 config 의 matchup_max_tokens")
    ap.add_argument("--extra", action="store_true", help="mistral·gemini 도 잰다")
    ap.add_argument("--seed", type=int, default=None,
                    help="고정 seed 전송. 미지정이면 종전대로 보내지 않는다")
    a = ap.parse_args()

    _load_env()
    from app.config import get_settings

    budget = a.budget or int(get_settings().matchup_max_tokens)
    prompt = build_prompt()
    print(f"■ 프롬프트 {len(prompt)}자 · 반복 {a.reps}회 · max_tokens={budget}"
          + (f" · seed={a.seed}" if a.seed is not None else " · seed 없음"))
    print("  (전 호출에 동일 프롬프트 재사용 — 입력은 완전히 같다)\n")

    cands = chain_candidates() + (EXTRA if a.extra else [])
    rows = []
    for provider, model, label in cands:
        print(f"── {label} ({provider}/{model or '(config)'})")
        rows.append(await audition(provider, model, label, prompt,
                                   a.reps, budget, a.seed))
        print()

    print("═" * 74)
    print(f"{'모델':28s} {'n':>3s} {'평균':>7s} {'표준편차':>8s} {'최대-최소':>9s} "
          f"{'뒤집힘':>6s} {'합격':>5s}")
    print("─" * 74)
    for r in rows:
        if not r["n"]:
            print(f"{r['label'][:28]:28s} {'0':>3s}  — 전량 실패 "
                  f"({r['errors'][0] if r['errors'] else ''})")
            continue
        print(f"{r['label'][:28]:28s} {r['n']:>3d} {r['mean']:>7.3f} "
              f"{r['stdev_pp']:>7.2f}%p {r['range_pp']:>8.2f}%p "
              f"{r['flips']:>6d} {'✅' if r['pass'] else '❌':>5s}")
    print("═" * 74)
    print("합격선: 최대-최소 ≤ 2.00%p AND 뒤집힘 0")
    print("\nREPORT_JSON " + json.dumps(rows, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
