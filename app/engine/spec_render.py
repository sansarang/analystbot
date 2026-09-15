"""[U14 2026-09-15] 출력 규격 렌더 — 확인✔ / 못함✗ (실행판 PART 4).

🔴 **문자열만 만든다.** 발송 경로에 꽂지 않는다 — 꽂는 것은 `order_v3` 전환과
   함께이고 그건 사용자 확인 지점이다. 지금 꽂으면 오늘 밤 카드가 바뀐다.
🔴 **숫자를 지어내지 않는다.** 값이 없으면 줄을 **빼거나 "못함"으로** 쓴다.
   0 으로 채우면 "쟀는데 0"과 "못 쟀다"가 같아진다.
⚠️ 카드·채팅·요약이 **같은 함수**를 쓴다. 표를 세 벌 만들면 곧 세 벌이 갈린다.
"""
from __future__ import annotations

OK, NO = "✔", "✗"

#: 축 이름표. 없는 축은 키 그대로 쓴다 — 표를 손으로 늘리지 않는다.
_SIDE = {"home": "홈", "away": "원정", "draw": "무"}


def _label(key: str) -> str:
    """`"away.out"` → `"원정 결장"`. 모르는 칸은 **그대로 보여준다.**"""
    side, _, field = str(key or "").partition(".")
    return f"{_SIDE.get(side, side)} {field}".strip() if field else str(key)


def checks(confirmed=None, refuted=None, unknown=None) -> list[str]:
    """확인✔ / 반증✗ / 미상✗ 줄. 🔴 반증과 미상을 **같은 ✗ 로 쓰되 말이 다르다.**"""
    lines = []
    for k in (confirmed or []):
        lines.append(f"{OK} {_label(k)} 확인")
    for k in (refuted or []):
        lines.append(f"{NO} {_label(k)} 반대 사실")
    for k in (unknown or []):
        lines.append(f"{NO} {_label(k)} 못 찾음")
    return lines


def flow_line(flow: dict | None) -> str | None:
    """시장 흐름 한 줄. 분류가 없으면 **줄 자체를 안 만든다.**"""
    f = flow or {}
    cls = f.get("class") or f.get("flow_class")
    if not cls:
        return None
    why = f.get("reason") or f.get("why")
    pp = f.get("pp")
    bits = [f"시장 흐름: {cls}"]
    if pp is not None:
        bits.append(f"{float(pp):+.1f}%p")
    if why:
        bits.append(str(why))
    return " · ".join(bits)


def axes_lines(main_axis=None, counter_axis=None) -> list[str]:
    """결정축·반대축. 🔴 반대축이 없으면 "없음"이라고 쓴다 — 빼지 않는다.
    반대축을 안 적으면 한쪽만 본 것처럼 읽힌다."""
    out = []
    if main_axis:
        out.append(f"결정축: {main_axis}")
        out.append(f"반대축: {counter_axis or '없음'}")
    return out


def condition_lines(cond: dict | None) -> list[str]:
    """조건 A·B 통과 여부. 값이 없는 항목은 **빼지 않고 ✗ 로** 쓴다."""
    c = cond or {}
    return [f"{OK if v else NO} {k}" for k, v in c.items()]


def render(blk: dict | None) -> str:
    """한 경기 → 규격 문자열. 카드·채팅·요약 공통이다."""
    b = blk or {}
    lines: list[str] = []
    head = b.get("title") or b.get("head")
    if head:
        lines.append(str(head))

    chk = checks(b.get("confirmed"), b.get("refuted"), b.get("unknown"))
    if chk:
        lines.append("")
        lines.extend(chk)

    fl = flow_line(b.get("flow") or b.get("market_flow"))
    ax = axes_lines(b.get("main_axis"), b.get("counter_axis"))
    cd = condition_lines(b.get("conditions"))
    tail = [x for x in ([fl] + ax) if x] + cd
    if tail:
        lines.append("")
        lines.extend(tail)
    return "\n".join(lines).strip()
