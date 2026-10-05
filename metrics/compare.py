"""🔴🔴 **켜기 전·후를 나란히 잰다** — v5-A §6 / 작업지시 §5.

> DeepSeek 가 적중을 올리는지는 같은 정답지로 켜기 전·후를 나란히 재서
> 판단한다. **감으로 켜지 않는다.** — v5-A §6

══════════════════════════════════════════════════════════════════
🔴 세 파일 · 한 표
══════════════════════════════════════════════════════════════════

    ① enabled: false    → metrics/baseline_solar.json   (Solar 단독 기준선)
    ② enabled: stage3   → metrics/stage3.json           (가설·시나리오만)
    ③ enabled: stage3+4 → metrics/stage34.json          (반증까지)

⚠️ **없는 파일을 0 으로 때우지 않는다**(CLAUDE.md #3) — *"안 쟀다"* 와 0 은
   다른 사실이고, 섞으면 *"올랐다"* 가 거짓이 된다.

🔴 **이 파일은 원장을 읽지 않는다.** 재는 것은 *우리 로직이 제 말대로 했나*
   뿐이고(지시 2026-10-02), 여기서 나온 수로 **계수를 맞추지 않는다** — 답하는
   것은 *"단계 3 을 켤 수 있나"* 하나다. 그 판단도 **사용자가** 한다.
"""
from __future__ import annotations

import json
import pathlib

#: 🔴 지시서가 적은 **그 이름들**이다(v5-A §6 ①②③ · 작업지시 §5-2~§5-4).
FILES = ("baseline_solar.json", "stage3.json", "stage34.json")

#: 🔴 **안 쟀다**를 적는 한 낱말. ⚠️ 0 으로 적지 않는다.
UNMEASURED = "안 쟀다"

_HERE = pathlib.Path(__file__).resolve().parent


def spec() -> dict:
    """`metrics/spec.yaml` — 🔴 지표·방향·켜는 기준의 **원본**."""
    import yaml
    return yaml.safe_load((_HERE / "spec.yaml").read_text(encoding="utf-8"))


def day_cap() -> float:
    """하루 상한 USD. 🔴 **§2 예산이 원본**이다 — 여기 베끼지 않는다."""
    from app import rules
    return float(rules.llm_budget()["per_day_usd"])


def load(root: pathlib.Path | str | None = None) -> dict[str, dict | None]:
    """세 파일을 읽는다. 🔴 **없는 것은 `None`**(0 이 아니다)."""
    base = pathlib.Path(root or _HERE)
    out: dict[str, dict | None] = {}
    for name in FILES:
        p = base / name
        if not p.exists():
            out[name] = None
            continue
        try:
            out[name] = json.loads(p.read_text(encoding="utf-8"))
        except ValueError as exc:
            # 🔴 깨진 파일을 0 으로 읽지 않는다 — 그 사실을 들고 간다
            out[name] = {"_broken": f"{exc}"}
    return out


def _num(box: dict | None, key: str):
    """지표 하나. 🔴 `None` 은 **못 쟀다**다(0 이 아니다)."""
    if not box:
        return None
    got = box.get("summary", box).get(key)
    return None if got is None else float(got)


def table(boxes: dict[str, dict | None]) -> list[str]:
    """🔴 **표 한 장**(마크다운 줄 목록). 안 쟀으면 그렇게 적는다."""
    sp = spec()["metrics"]
    head = ["| 지표 | 방향 | " + " | ".join(
        n.replace(".json", "") for n in FILES) + " |",
        "|---|---|" + "---|" * len(FILES)]
    rows = []
    for key, meta in sp.items():
        cells = []
        for name in FILES:
            got = _num(boxes.get(name), key)
            cells.append(UNMEASURED if got is None else f"{got:g}")
        arrow = {"down": "↓", "up": "↑", "watch": "⚠️"}[meta["direction"]]
        rows.append(f"| `{key}` | {arrow} | " + " | ".join(cells) + " |")
    missing = [n for n in FILES if boxes.get(n) is None]
    tail = []
    if missing:
        tail = ["", f"🔴 **{UNMEASURED}**: {', '.join(missing)} — "
                    f"작업지시 §5 순서로 재야 비교가 뜻을 얻는다."]
    return head + rows + tail


def may_enable(stage: str, base: dict | None,
               after: dict | None) -> tuple[bool, str]:
    """🔴🔴 **켤 수 있나** — v5-A §6 기준이 수로 답한다.

    ⚠️ 돌려주는 것은 *"켤 수 있다"* 이고 **"켜라"가 아니다** — 켜는 결정은
       사용자다(지시 2026-09-30). 기준을 못 넘으면 사유에 `questions/` 를 적어
       *"사용자 판단을 받는다"* 를 가리킨다(v5-A §6 마지막 문장).
    """
    g = spec()["gates"].get(stage)
    if g is None:
        return False, f"🔴 `{stage}` 는 선언된 게이트가 아니다"
    if base is None or after is None:
        # 🔴 **안 쟀으면 못 켠다**(#3 · 조용한 0 금지)
        return False, (f"🔴 {UNMEASURED} — 기준선 또는 측정이 없다. "
                       f"결과를 `questions/` 에 적고 사용자 판단을 받는다")
    bad: list[str] = []
    if g.get("outcome_hit_rate") == "up":
        b, a = _num(base, "outcome_hit_rate"), _num(after, "outcome_hit_rate")
        if b is None or a is None:
            bad.append(f"결과 갈래 포함률을 {UNMEASURED}")
        elif not a > b:
            bad.append(f"결과 갈래 포함률이 **안 올랐다**({b:g} → {a:g})")
    want = g.get("wrong_repro")
    if want in ("down", "same_or_down"):
        b, a = _num(base, "wrong_repro"), _num(after, "wrong_repro")
        if b is None or a is None:
            bad.append(f"오답 재현 수를 {UNMEASURED}")
        elif a > b or (want == "down" and a >= b):
            bad.append(f"오답 재현 수가 **안 줄었다**({b:g} → {a:g})")
    want = g.get("false_confidence")
    if want in ("down", "same_or_down"):
        b, a = _num(base, "false_confidence"), _num(after, "false_confidence")
        if b is None or a is None:
            bad.append(f"거짓 확신 수를 {UNMEASURED}")
        elif a > b or (want == "down" and a >= b):
            bad.append(f"🔴 거짓 확신 수가 **안 줄었다**({b:g} → {a:g}) — "
                       f"v5-A §6 은 단계 4 를 그때만 켠다")
    floor = g.get("graded_markets_min_ratio")
    if floor is not None:
        b, a = _num(base, "graded_markets"), _num(after, "graded_markets")
        if b is None or a is None:
            bad.append(f"등급 마켓 수를 {UNMEASURED}")
        elif b > 0 and a < float(floor) * b:
            bad.append(f"등급 마켓 수가 기준선의 **{float(floor) * 100:g}% 아래**"
                       f"({b:g} → {a:g}) — 반증이 다 깎았다")
    if bad:
        return False, ("🔴 기준 미달: " + " · ".join(bad)
                       + " → 결과를 `docs/fable/questions/` 에 적고 "
                         "**사용자 판단**을 받는다(v5-A §6)")
    return True, (f"✅ `{stage}` 기준을 넘었다 — "
                  f"🔴 그래도 **켜는 것은 사용자다**(지시 2026-09-30)")


def report(root: pathlib.Path | str | None = None) -> str:
    """🔴 한 장 보고 — 표 + 두 게이트 판정."""
    boxes = load(root)
    out = ["# DeepSeek 켜기 전·후 (v5-A §6)", ""]
    out += table(boxes)
    base = boxes.get("baseline_solar.json")
    for stage, name in (("stage3", "stage3.json"), ("stage4", "stage34.json")):
        ok, why = may_enable(stage, base, boxes.get(name))
        out += ["", f"## `{stage}`", "", f"{'✅' if ok else '🔴'} {why}"]
    out += ["", f"⚠️ 하루 상한 ${day_cap():g} (§2 예산이 원본)"]
    return "\n".join(out)


if __name__ == "__main__":        # pragma: no cover
    print(report())
