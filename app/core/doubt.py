"""🔴🔴 **§4 판정 — 확신 · 보류 · 역배**(의심 검증 통합본 v2 · 2026-10-14i §4).

> 의심 후 확률 = **그 경기 칸의 실측**이다.
> · **확신** — 1단 정상 + 의심 후 확률 ≥ 확신 문턱 + **구간 하한도 문턱 근처**
> · **역배** — 1단 정상 + **반대쪽** 의심 후 확률 구간 **하한 > 50%** + 다른
>   시즌에서도 유지
> · **보류** — 나머지(기계 보류 포함). *"봇이 이상해 보인다"* 만으로 역배 금지.

## 이 파일이 지키는 것

| 조항 | 어떻게 |
|---|---|
| §4 문턱 | `config/doubt_judge.yaml` 이 든다 — **곡선으로만** 고른 값이다 |
| §4 자 | 🔴 문턱은 **의심 후 확률 자** 위에 있다(봇 원확률과 섞지 않는다) |
| §3-3 보류 | 칸이 `보류` 면 그 줄은 **보류**다(실측을 쓰지 않는다) |
| §4 역배 | **시즌 교차**가 확인된 칸이 아니면 역배를 **내지 않는다** |
| §2 | 1단이 **기계 보류**면 확신·역배 **둘 다 금지** |

🔴 판은 `data/doubt_cal/<줄종류>.yaml` 이고 `tools/fit_doubt.py` 가 적는다
   (`app/` 은 yaml 을 쓰지 않는다).
🔴 **확률을 고치지 않는다** — 봇 확률은 그대로 두고 **그 옆에** 의심 후 확률을
   적는다(계약 DB4: 확률 모듈이 이 파일을 부르면 실패).
⚠️ 칸을 못 찾으면 **보류**다 — 모르는 자리에서 확신하지 않는다(#4).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOX = ROOT / "data/doubt_cal"
CONF = ROOT / "config/doubt_judge.yaml"

#: 🔴 판정 글자 셋 — 다른 글자를 쓰지 않는다
SURE, HOLD, FADE = "확신", "보류", "역배"

#: 🔴 보정표의 **가장 낮은 구간**(§3-3 은 40% 부터다) — 그 아래는 칸이 없다
BAND_LOW = 0.40

#: 🔴 줄 이름 → 줄 종류(`tools/fit_doubt.KINDS` 와 같은 셋)
WIN, AH, OU = "승무패 방향", "보드 핸디", "보드 언오버"


def kind_of(name: str) -> str:
    """🔴🔴 줄 이름이 어느 **줄 종류**인가. 모르면 **빈 글자**(그 줄은 보류다).

    ══════════════════════════════════════════════════════════════════
    🔴🔴 **모르는 줄을 승무패로 떨어뜨리면 거짓 확신이 선다**
    ══════════════════════════════════════════════════════════════════

    ⚠️ 실사고 2026-10-14(구성표 2번): 마지막 줄이 `return WIN if said else ""`
       였다 — 그래서 **`BTTS 예`** 가 승무패 칸으로 들어가 **확신 1,698개**가
       섰고 그 적중은 **55.8%** 였다(승무패 확신은 69.5%). 보정표는 BTTS 를
       **잰 적이 없다**.
    🔴 보정표가 덮는 줄은 **셋뿐**이다(`tools/fit_doubt.KINDS`) — 그 밖은
       *"모른다"* 이고, 모르는 자리에서 확신하지 않는다(#4).
    """
    said = str(name or "").strip()
    if said.startswith("핸디"):
        return AH
    if said.startswith(("오버", "언더")):
        return OU
    if said in ("홈 승", "원정 승", "무"):
        return WIN
    return ""


def table() -> dict:
    """🔴 §4 문턱 표. ⚠️ 없으면 **빈 표**(판정이 전부 보류가 된다)."""
    import yaml
    if not CONF.is_file():
        return {}
    return dict(yaml.safe_load(CONF.read_text(encoding="utf-8")) or {})


def leg_cut() -> float | None:
    """🔴 **다폴 다리 문턱**(의심 후 자 · §5 다폴 규칙). 없으면 `None`."""
    got = dict(table().get("cuts") or {}).get("다리")
    return float(got) if got is not None else None


def live() -> tuple[bool, str]:
    """🔴🔴 **실전인가 기록용인가**(후속 지시 2026-10-14 4번). `(실전, 글자)`.

    🔴 `config/doubt_judge.yaml` 의 `운영` 칸 하나가 정한다 — 봇이 스스로
       바꾸지 않는다(사용자 지시로만). ⚠️ 발송 스위치와는 **다른 칸**이다.
    """
    got = str(table().get("운영") or "기록용")
    if got == "실전":
        return True, ""
    # ⚠️ 한 줄로 짧게 — 표의 **첫 줄**이다(까닭 전문은 설정 파일에 있다)
    return False, (f"🔴🔴 **{got} — 실전 금지** · 기록만 쌓는다"
                   f"(`config/doubt_judge.yaml` 의 `운영`)")


def plates() -> dict:
    """🔴 보정표 셋 — `{줄종류: {의심개수: [칸…]}}`. 없으면 빈 표."""
    import yaml
    out: dict = {}
    for path in sorted(BOX.glob("*.yaml")) if BOX.is_dir() else []:
        got = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        kind = str(dict(got.get("meta") or {}).get("줄종류") or "")
        if kind:
            out[kind] = dict(got.get("칸") or {})
    return out


def bucket_of(n_bad: int) -> str:
    """🔴 §3-3 — 유효 불리 의심 개수를 **0·1·2+** 로 묶는다."""
    got = int(n_bad or 0)
    return "0" if got == 0 else ("1" if got == 1 else "2+")


def cell_for(box: dict, kind: str, p: float, n_bad: int) -> dict | None:
    """🔴🔴 그 경기의 **칸** — `(줄 종류, 봇 확률, 의심 개수)`. 없으면 `None`.

    ⚠️ 경계는 판의 `p_lo`·`p_hi` 를 읽는다 — 글자(`40%~44%`)를 되파싱하지 않는다.
    """
    rows = list(dict(dict(box or {}).get(str(kind)) or {})
                .get(bucket_of(n_bad)) or [])
    for one in rows:
        lo, hi = one.get("p_lo"), one.get("p_hi")
        if lo is None or hi is None:
            continue
        if float(lo) <= float(p) < float(hi):
            return dict(one)
    return None


@dataclass
class Row:
    """🔴 줄 하나의 판정 — 봇 확률 **옆에** 의심 후 확률을 적는다."""

    name: str = ""
    kind: str = ""
    p_bot: float | None = None
    p_after: float | None = None
    lo: float | None = None
    hi: float | None = None
    n: int = 0
    cell: str = ""
    real: str = ""
    verdict: str = HOLD
    why: str = ""

    def said(self) -> str:
        if self.p_after is None:
            return (f"    {self.name} — 봇 "
                    + (f"**{self.p_bot:.1%}**" if self.p_bot is not None
                       else "⬜")
                    + f" · 의심 후 ⬜ · **{self.verdict}** — {self.why}")
        return (f"    {self.name} — 봇 {self.p_bot:.1%} → **의심 후 "
                f"{self.p_after:.1%}**"
                f"[{self.lo:.1%}, {self.hi:.1%}] · 칸 {self.cell}"
                f"({self.n}경기 · {self.real}) · **{self.verdict}**"
                + (f" — {self.why}" if self.why else ""))


@dataclass
class Doubt:
    """🔴 그 경기의 2단 결과."""

    rows: list = field(default_factory=list)
    bad: list = field(default_factory=list)
    hold: bool = False
    why: str = ""

    def picks(self) -> list:
        """🔴🔴 §4 — `core/picks` 가 받는 것은 **확신·역배뿐**이다."""
        if self.hold:
            return []
        return [r for r in self.rows if r.verdict in (SURE, FADE)]


def judge(lines: dict, *, bad: list | None = None, machine_hold: bool = False,
          box: dict | None = None) -> Doubt:
    """🔴🔴 §4 — 줄마다 판정. `lines` 는 `{줄 이름: 봇 확률}` 이다.

    🔴 `machine_hold` 가 참이면 **전부 보류**다(§2 — 확신·역배 둘 다 금지).
    """
    conf = dict(table().get("cuts") or {})
    cut = conf.get("확신")
    slack = float(conf.get("확신_하한_여유") or 0.0)
    fade_lo = float(conf.get("역배_하한") or 0.50)
    need_cross = bool(table().get("역배_시즌교차_필수", True))
    said = plates() if box is None else dict(box)
    got = Doubt(bad=[str(x) for x in (bad or [])], hold=bool(machine_hold))
    n_bad = len(got.bad)
    for name, p in dict(lines or {}).items():
        kind = kind_of(str(name))
        row = Row(name=str(name), kind=kind,
                  p_bot=(float(p) if p is not None else None))
        if machine_hold:
            row.why = "🔴 1단 **기계 보류** — 확신·역배 둘 다 금지(§2)"
            got.rows.append(row)
            continue
        if not said:
            row.why = "⬜ 보정표가 없다 — `tools/fit_doubt.py` 가 아직 안 돌았다"
            got.rows.append(row)
            continue
        if not kind:
            # 🔴 보정표가 **안 덮는 줄 종류**다(BTTS·더블찬스·DNB …) → 보류
            row.why = (f"⬜ `{row.name}` 은 보정표가 **안 다루는 줄 종류**다"
                       f"(덮는 것은 {WIN}·{AH}·{OU} 셋뿐) → 보류")
            got.rows.append(row)
            continue
        cell = cell_for(said, kind, float(p or 0.0), n_bad)
        if cell is None:
            # 🔴 **구간 밖**과 **칸이 비었다**를 가른다(#3) — 40% 아래는
            #    보정표가 아예 다루지 않는 자리다(그 줄은 애초에 고를 줄이 아니다).
            row.why = ((f"⬜ 봇 {float(p or 0):.0%} 는 보정표 **구간 밖**이다"
                        f"(가장 낮은 칸이 {BAND_LOW:.0%}) → 보류")
                       if float(p or 0.0) < BAND_LOW else
                       (f"⬜ `{kind}` 의 {float(p or 0):.0%} · 의심 "
                        f"{bucket_of(n_bad)} 칸이 **없다** → 보류"))
            got.rows.append(row)
            continue
        row.p_after = float(cell["실측"])
        row.lo, row.hi = float(cell["lo"]), float(cell["hi"])
        row.n = int(cell["n"])
        row.cell = str(cell.get("구간") or "")
        row.real = (f"실보드 {cell.get('실보드')}/근사 {cell.get('근사')}"
                    # 🔴 승무패 방향은 **보드와 무관**하다(그 줄은 보드 없이도
                    #    선다) — 그 수를 실보드에 섞어 적지 않는다(§1-4)
                    + (f"/보드무관 {cell.get('보드무관')}"
                       if cell.get("보드무관") else ""))
        if cell.get("보류"):
            row.why = (f"🔴 그 칸이 **보류**다(경기 {row.n} < 최소) — "
                       f"실측을 쓰지 않는다(§3-3)")
            got.rows.append(row)
            continue
        if cut is None:
            row.why = ("⬜ **확신 문턱이 아직 없다** — `tools/cut_curve.py "
                       "--after` 로 곡선을 그려 `config/doubt_judge.yaml` 에 "
                       "적는다(§4)")
            got.rows.append(row)
            continue
        # ── 🔴 역배 — **반대쪽** 구간 하한이 50% 를 넘나
        other_lo = 1.0 - row.hi
        if other_lo > fade_lo:
            if need_cross and not cell.get("시즌교차"):
                row.why = (f"⚠️ 반대쪽 하한 {other_lo:.1%} > "
                           f"{fade_lo:.0%} 인데 그 칸에 **시즌 교차 확인이 "
                           f"없다** → 역배를 내지 않는다(§4)")
            else:
                row.verdict = FADE
                row.why = (f"🔴 **반대쪽**이 더 맞는다 — 반대쪽 구간 하한 "
                           f"{other_lo:.1%} > {fade_lo:.0%}")
            got.rows.append(row)
            continue
        # ── 🔴 확신 — 실측이 문턱 이상이고 **하한도 문턱 근처**
        if row.p_after >= float(cut) and row.lo >= float(cut) - slack:
            row.verdict = SURE
            row.why = (f"의심 후 {row.p_after:.1%} ≥ 문턱 {float(cut):.0%} · "
                       f"하한 {row.lo:.1%} ≥ {float(cut) - slack:.1%}")
        else:
            row.why = (f"문턱 {float(cut):.0%} 미달(의심 후 {row.p_after:.1%} · "
                       f"하한 {row.lo:.1%})")
        got.rows.append(row)
    got.why = said_of(got)
    return got


def said_of(got: Doubt) -> str:
    """🔴 §7 — 카드 **의심 블록**(머리 줄은 1단이 적는다)."""
    head = (f"🧪 **2단 의심** — 유효 불리 의심 "
            + (" · ".join(got.bad) if got.bad else "**없다**")
            + f"(묶음 {bucket_of(len(got.bad))})")
    if got.hold:
        head += " · 🔴 **1단 기계 보류** → 줄 전부 보류"
    rows = [head]
    for r in got.rows:
        rows.append(r.said())
    n_sure = sum(1 for r in got.rows if r.verdict == SURE)
    n_fade = sum(1 for r in got.rows if r.verdict == FADE)
    rows.append(f"    → 확신 **{n_sure}** · 역배 **{n_fade}** · 보류 "
                f"{len(got.rows) - n_sure - n_fade}")
    return "\n".join(rows)
