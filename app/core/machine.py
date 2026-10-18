"""🔴🔴 **1단 기계 점검**(의심 검증 통합본 v2 · 2026-10-14i §2).

> 입력 완전성 · 버그 반영 여부 · 신선도를 보고
> **정상 → 2단 / 고장 → 고쳐서 재계산 / 못 고치면 기계 보류**.
> 🔴 **기계 보류면 확신·역배 둘 다 금지**(칠 표에서 빠진다).

## 이 파일이 지키는 것

| 조항 | 어떻게 |
|---|---|
| §2 세 묶음 | `ROWS` 가 **입력·버그·신선** 셋으로 나뉘어 있다 |
| §2 판정 | 버그 거짓 → **고장** · 필수 입력 빠짐·보드 묵음 → **기계 보류** |
| §4 보류 | `hold()` 가 참이면 `core/picks` 가 그 경기를 **안 받는다** |
| CLAUDE.md #3 | **빠짐(🔴)과 못 쟀다(⬜)를 가른다** — 둘을 섞지 않는다 |

🔴 표는 `config/machine_check.yaml` 이다 — 값을 코드에 적지 않는다.
🔴 **확률에 닿지 않는다** — 이 모듈은 글자와 보류 깃발만 만든다(계약 MC4).
⚠️ 재료를 **새로 받지 않는다** — 그 실행이 이미 아는 것만 본다(`pipeline._machine_of`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

#: 🔴 값 규약 — `True` = ✅ 정상 · `False` = 🔴 빠짐/고장 · `None` = ⬜ **못 쟀다**
OK, BAD, UNKNOWN = True, False, None

#: 🔴🔴 **해당 없음**(➖) — 그 경기에 그 칸이 **아예 없는** 것이다.
#:
#:  ⚠️ 실측 2026-10-14(챔피언십 카드): `리그 오프셋`·`대회 이력` 은 **대륙 대회
#:     에서만** 선다(`s2_facts` 의 `club_continental` 분기 안이다). 국내 리그
#:     카드에서 그 둘을 ⬜ 로 적으니 모든 카드가 *"못 쟨 칸 둘"* 을 달았고,
#:     **진짜 못 잰 칸**이 그 소음에 묻혔다.
#:  🔴 CLAUDE.md #3 은 *"자료가 안 왔다"* 와 *"왔는데 못 뽑았다"* 를 가르라고
#:     한다 — **"해당 없다"** 는 그 둘 **어느 쪽도 아니다**.
NA = "➖"

#: 🔴 판정 글자 셋(§2) — 다른 글자를 쓰지 않는다
NORMAL, BROKEN, HOLD = "정상", "고장", "기계 보류"

#: 🔴🔴 점검 칸 — `(열쇠, 카드에 적을 이름, 묶음)`. 묶음은 §2 의 세 줄이다.
ROWS: tuple[tuple[str, str, str], ...] = (
    # ── 입력 완전성
    # ══════════════════════════════════════════════════════════════
    # 🔴🔴 **Elo·축 칸을 걷었다** — 사용자 지시 2026-10-18(*"m5 elo 삭제"*)
    # ══════════════════════════════════════════════════════════════
    #
    #  ⚠️ 실측 2026-10-18(모든 경기): 1단 점검이
    #       `🔴 필수 입력 빠짐 — Elo 바닥 승무패 · 축0(Elo 대비 잔차)(⬜)`
    #     으로 **영구히 `기계 보류`** 였다.
    #  🔴 까닭 — Elo(2026-10-17 *"elo 지워라"*)와 상성 축(같은 날 *"상성
    #     삭제해라"*)을 **지웠는데** 이 표가 그 둘을 **필수 입력**으로 두고
    #     있었다. 없는 것을 요구하면 판정이 영구히 멈춘다(CLAUDE.md #2 의 결).
    #  🔴 그래서 다섯 칸(`elo_floor`·`axis0`~`axis3`)을 **걷는다**.
    #     ⚠️ 확률은 이제 `probmodel.flat_prob`(1/3 균등 + 변수) 하나가 낸다 —
    #        그 재료(`form_n`·`xi`·`absence_rung` …)는 아래에 그대로 남는다.
    ("form_n", "폼 표본 수", "입력"),
    ("xi", "XI(확정/예상)", "입력"),
    ("absence_rung", "결장 원천 등급", "입력"),
    ("coach", "감독 신원(경기 페이지 isCoach)", "입력"),
    ("league_offset", "리그 오프셋", "입력"),
    ("comp_history", "대회 이력(기간·0-0)", "입력"),
    ("board_lines", "보드(출처·시각)", "입력"),
    # ── 버그 반영(§2 둘째 줄) — 이름은 `config/machine_check.yaml` 이 든다
    ("axis3_sign", "", "버그"),
    ("weight_renorm", "", "버그"),
    ("home_mul_a", "", "버그"),
    ("axis0_scale_decided", "", "버그"),
)

#: 🔴🔴 **대회 이력 대조는 `버그` 가 아니라 `입력` 이다**(수정 지시 2026-10-14 3번)
#:
#:  > 불일치 있으면 **대회 이력 칸만 ⬜**(1단 전체를 막지 않는다).
#:
#:  ⚠️ 종전엔 `comp_record_verified` 가 **버그 칸**이라 거짓이면 **고장**이 되고
#:     1단이 통째로 멈췄다 — 실측 2026-10-14(10-15 슬레이트): UCL·ACLE **11경기**
#:     가 그 한 칸 때문에 전부 보류였다. 🔴 외부 대조는 **대회 이력 칸의 신뢰도**
#:     이지 기계의 고장이 아니다.
ROWS = ROWS + (("comp_record_verified", "", "입력"),)


def table() -> dict:
    """🔴 표 하나 — `config/machine_check.yaml`. ⚠️ 없으면 **빈 표**(점검이 멈춘다)."""
    from pathlib import Path

    import yaml
    path = Path(__file__).resolve().parents[2] / "config/machine_check.yaml"
    if not path.is_file():
        return {}
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


@dataclass
class Machine:
    """🔴 1단 결과 — **판정 하나 + 칸마다의 상태**."""

    verdict: str = NORMAL
    rows: list = field(default_factory=list)      # [{열쇠, 이름, 묶음, 상태, 말}]
    broken: list = field(default_factory=list)    # 🔴 고장 칸 이름
    missing: list = field(default_factory=list)   # 🔴 빠진 **필수** 입력
    thin: list = field(default_factory=list)      # ⚠️ 빠진 그 밖의 입력
    unknown: list = field(default_factory=list)   # ⬜ 못 쟨 칸
    stale: list = field(default_factory=list)     # ⏰ 창을 넘은 칸
    na: list = field(default_factory=list)        # ➖ 그 경기에 없는 칸
    why: str = ""

    def hold(self) -> bool:
        """🔴🔴 §4 — 참이면 **확신·역배 둘 다 금지**(보류만 남는다)."""
        return self.verdict != NORMAL


def _state(val: object) -> str:
    if val is NA:
        return NA
    return "✅" if val is OK else ("⬜" if val is UNKNOWN else "🔴")


def age_hours(at: object, *, now: datetime | None = None) -> float | None:
    """🔴 그 시각이 **몇 시간 전**인가. 시각이 없거나 못 읽으면 `None`(⬜).

    ⚠️ 시간대 없는 값은 **안 받는다**(절대규칙 2) — 조용히 서버 시간대로
       가정되면 그 가정이 어긋나도 아무 데도 안 적힌다.
    """
    said = at
    if isinstance(said, str):
        try:
            said = datetime.fromisoformat(said.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(said, datetime):
        return None
    if said.tzinfo is None or said.tzinfo.utcoffset(said) is None:
        return None
    base = now or datetime.now(timezone.utc)
    return (base - said).total_seconds() / 3600.0


def hard_of(conf: dict, *, kind: str = "") -> set:
    """🔴🔴 그 **대회 유형**의 필수 칸(수정 지시 2026-10-14 2번).

    `hard` 에서 `hard_except[칸]` 에 그 유형이 적힌 칸을 뺀다.
    🔴 면제는 **설정이 든다** — 코드에 대회 유형을 적지 않는다.
    """
    got = set(dict(conf or {}).get("hard") or ())
    for key, kinds in dict(dict(conf or {}).get("hard_except") or {}).items():
        if str(kind or "") in {str(x) for x in (kinds or [])}:
            got.discard(str(key))
    return got


def check(box: dict, *, ages: dict | None = None,
          now: datetime | None = None, kind: str = "") -> Machine:
    """🔴🔴 §2 — 점검 한 번. `box` 는 칸마다 `True/False/None` 이다.

    `ages` 는 `{칸: 시각}`(또는 `{칸: 시간수}`) — 신선도 창을 그것으로 잰다.

    판정(§2):
      · 버그 칸이 **거짓** → `고장`(고쳐서 재계산한 뒤 다시 1단)
      · 필수 입력(`hard`)이 **빠짐 또는 ⬜** → `기계 보류`
      · `hold: true` 인 신선도 창을 넘음 → `기계 보류`
      · 나머지 → `정상`
    """
    conf = table()
    names = dict(conf.get("bugs") or {})
    # 🔴 대회 유형이 오면 그 유형의 면제를 뺀 필수 칸을 쓴다(지시 2번)
    hard = hard_of(conf, kind=str(kind or ""))
    said = dict(box or {})
    got = Machine()
    for key, name, group in ROWS:
        val = said.get(key, UNKNOWN)
        label = name or str(names.get(key) or key)
        got.rows.append({"key": key, "name": label, "group": group,
                         "state": _state(val)})
        # 🔴 **해당 없음**은 통과도 빠짐도 아니다 — 어느 목록에도 안 들어간다
        if val is NA:
            # 🔴🔴 **필수 칸은 "해당 없음" 이 될 수 없다** — Elo 바닥·축0·보드가
            #    *"이 경기엔 없다"* 면 그것은 **확률이 서지 않는다**는 뜻이다.
            #    ⚠️ 여기서 막지 않으면 ➖ 하나로 보류가 뚫린다(계약이 그것을 본다).
            if key in hard:
                got.missing.append(f"{label}(➖ — 필수 칸은 해당 없음이 될 수 "
                                   f"없다)")
            else:
                got.na.append(label)
            continue
        if val is OK:
            continue
        if val is UNKNOWN:
            got.unknown.append(label)
            if key in hard:
                got.missing.append(f"{label}(⬜)")
            continue
        if group == "버그":
            got.broken.append(label)
        elif key in hard:
            got.missing.append(label)
        else:
            got.thin.append(label)
    # ── 신선도
    for key, rule in dict(conf.get("fresh") or {}).items():
        want = float(dict(rule).get("hours") or 0) or None
        if want is None:
            continue
        said_age = (ages or {}).get(key)
        age = (float(said_age) if isinstance(said_age, (int, float))
               else age_hours(said_age, now=now))
        if age is None:
            continue
        if age > want:
            got.stale.append(
                f"{key} {age:.1f}시간 전(창 {want:g}시간"
                + (" · 🔴 보류" if dict(rule).get("hold") else " · 표시만")
                + ")")
            if dict(rule).get("hold"):
                got.missing.append(f"{key} 가 창을 넘었다({age:.1f}시간 전)")
    # ── 판정
    # 🔴 면제가 걸렸으면 **그 사실을 적는다**(조용히 통과시키지 않는다 · #3)
    said_free = set(conf.get("hard") or ()) - hard
    if said_free:
        got.na.append(f"필수 면제({kind}): " + " · ".join(sorted(said_free)))
    if got.broken:
        got.verdict = BROKEN
    elif got.missing:
        got.verdict = HOLD
    else:
        got.verdict = NORMAL
    got.why = said_of(got)
    return got


def said_of(got: Machine) -> str:
    """🔴 §7 — 카드 **의심 블록 머리**. 한 줄 + 걸린 것만 이름으로."""
    mark = {NORMAL: "✅", BROKEN: "🔴", HOLD: "🔴"}.get(got.verdict, "⚠️")
    n_ok = sum(1 for r in got.rows if r["state"] == "✅")
    n_all = len(got.rows) - len(got.na)
    parts = [f"{mark} **1단 기계 점검 — {got.verdict}**"
             f"({n_ok}/{n_all} 칸 ✅"
             + (f" · ➖ 해당 없음 {len(got.na)}" if got.na else "") + ")"]
    if got.broken:
        parts.append("🔴 **버그 미반영** " + " · ".join(got.broken))
    if got.missing:
        parts.append("🔴 **필수 입력 빠짐** " + " · ".join(got.missing))
    if got.stale:
        parts.append("⏰ " + " · ".join(got.stale))
    if got.thin:
        parts.append("⚠️ 빠진 칸 " + " · ".join(got.thin))
    if got.unknown:
        parts.append("⬜ 못 쟨 칸 " + " · ".join(got.unknown))
    if got.hold():
        parts.append("🔴🔴 **확신·역배 둘 다 금지**(칠 표에서 빠진다 · §4)")
    return " — ".join(parts)


def held(why: str) -> Machine:
    """🔴🔴 **점검 전에 멈춘 경기**(§2) — 그대로 `기계 보류` 다.

    ⚠️ 실측 2026-10-14: 신원 검문(모순된 XI)이 걸린 카드는 파이프라인이 **보드
       블록 앞에서 돌아 나가** 1단 점검이 **아예 안 돌았다** — 그러면 카드에 점검
       줄이 없고, 칠 표는 그 경기를 *"보드 없음"* 으로만 뺐다. 🔴 멈춘 것은
       **정상이 아니다** — 보류라고 적는다(#3 조용한 0 금지).
    """
    got = Machine(verdict=HOLD)
    got.rows = [{"key": key, "name": name or key, "group": group,
                 "state": "⬜"} for key, name, group in ROWS]
    got.missing = [f"1단 점검 전에 멈췄다 — {why}"]
    got.why = said_of(got)
    return got


def bug_box() -> dict:
    """🔴🔴 §2 둘째 줄 — **버그가 반영돼 있나**를 설정·판에서 읽는다.

    🔴 플래그의 원본은 `config/m1v2.yaml` 이다(`core/m1v2.table`) — 여기서 값을
       다시 적지 않는다(사본 금지). ⚠️ `comp_record_verified` 는 대회마다 다르니
       호출부가 덮는다(`pipeline._machine_of`).
    """
    from app.core import m1v2 as _m
    flags = dict(_m.table().get("flags") or {})
    got = {
        "axis3_sign": bool(flags.get("axis3_sign")),
        "weight_renorm": bool(flags.get("weight_renorm")),
        # 🔴 ③ 은 **끄기(a)** 가 판정 결과다 — `""`(옛 판)이면 아직 안 고친 것이다
        "home_mul_a": str(flags.get("home_mul") or "") == "a",
        # 🔴 ④ 는 **판정이 끝났나**를 본다 — 켜거나 끈 상태가 적혀 있으면 끝이다
        "axis0_scale_decided": flags.get("axis0_scale") is not None,
    }
    return got
