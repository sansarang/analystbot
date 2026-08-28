"""[§9-라인업 의도] **신호는 라인업이 아니라 평소와의 차이다.**

명단 자체는 정보가 얇다. "오늘 1번은 김현수"는 매일 같으면 아무것도 말하지 않는다.
평소와 무엇이 달라졌는지가 감독의 의도이고, 그것이 신호다.

⚠️ **이 모듈은 사실만 만든다.** "4번 타자가 빠졌다"까지가 여기 일이고,
   "체력 관리다 / 부상 은폐다"는 2단의 일이다. 섞으면 3단이 추측을 사실로 읽는다.

⚠️ **평소 라인업이 없으면 변경점도 없다.** 이력이 쌓이기 전에는 "비교 불가"로
   정직하게 남긴다 — 첫 관측을 "변경 없음"으로 적으면 거짓이 된다.
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# 평소 라인업을 만들 최소 경기 수. 이하면 비교하지 않는다.
#   ⚠️ 실측값이 아니라 **판단 유보선**이다. 3경기로 "평소"를 말하면 그 3경기의
#      우연이 기준이 된다. 이력이 쌓이면 몇 경기가 적당한지 재서 교체한다.
MIN_HISTORY = 5
USUAL_WINDOW = 10          # 최근 몇 경기를 평소로 볼 것인가

# 타순 상위/하위 경계 — 야구의 통상 구분(클린업 1~5번).
TOP_ORDER = 5

CHANGE_TYPES = ("regular_out", "order_demote", "order_promote", "new_starter",
                "position_change", "dh_rest", "bullpen_out")

# 변경 유형 → 어느 칸에 반영되는가 [4]
TYPE_TO_CELL = {
    "regular_out": "batting",
    "order_demote": "batting",
    "order_promote": "batting",
    "new_starter": "batting",
    "position_change": "batting",
    "dh_rest": "weight",        # 주전을 쉬게 하는 신호 — 이 경기의 무게
    "bullpen_out": "bullpen",
}

_POS = re.compile(r"^(.*?)\s*\((.*?)\)\s*$")
# 이름 표기 흔들림 — 소스마다 점·중점·공백이 붙는다.
#   🔴 실측 2026-08-27: 이름 뒤에 점 하나만 달라도 **주전 5명이 거짓 결장**으로
#      잡혔다. 매칭 실패가 곧 거짓 결장 신호가 된다 — 가장 위험한 오류다.
_NAME_NOISE = re.compile(r"[\s.·・,'\"`~\-–—]+")


def canon_name(name: str) -> str:
    """이름 표기를 하나로 맞춘다. 비교는 **항상 이것으로** 한다.

    ⚠️ 표시는 원문을 쓰고 비교만 정규화한다 — 정규화한 이름을 사용자에게
       보여주면 실제 표기와 달라 혼란을 준다.
    """
    return _NAME_NOISE.sub("", (name or "")).strip()
_DH_WORDS = ("지명타자", "지명", "DH")


def parse_order(text: str | list | None) -> list[tuple[str, str]]:
    """`"이름(포지션)-이름(포지션)"` → [(이름, 포지션), ...].

    포지션이 없는 소스(구형 크롤러·MLB)도 받는다 — 그때는 포지션이 빈 문자열이다.
    """
    if isinstance(text, str) and text.strip().startswith("["):
        try:
            text = json.loads(text)
        except ValueError:
            pass
    items = text if isinstance(text, list) else (text or "").split("-")
    out = []
    for raw in items:
        s = str(raw).strip()
        if not s:
            continue
        m = _POS.match(s)
        out.append((m.group(1).strip(), m.group(2).strip()) if m else (s, ""))
    return out


def usual_from(history: list[list[tuple[str, str]]]) -> dict:
    """과거 라인업들 → 평소 모습.

    반환 {"slots": {이름: 평소 타순}, "regulars": set, "positions": {이름: 포지션},
          "games": n}
    ⚠️ 표본이 얇으면 빈 dict — 없는 기준으로 비교하면 잡음이 신호가 된다.
    """
    rows = [r for r in history if r]
    if len(rows) < MIN_HISTORY:
        return {}
    slots: dict[str, list[int]] = {}
    pos: dict[str, list[str]] = {}
    appear: dict[str, int] = {}
    display: dict[str, str] = {}
    for order in rows[:USUAL_WINDOW]:
        for i, (name, p) in enumerate(order, 1):
            key = canon_name(name)      # 🔴 표기 흔들림을 흡수한 키로 집계한다
            display.setdefault(key, name)
            slots.setdefault(key, []).append(i)
            appear[key] = appear.get(key, 0) + 1
            if p:
                pos.setdefault(key, []).append(p)
    n = min(len(rows), USUAL_WINDOW)

    def _mode(vals):
        return max(set(vals), key=vals.count)

    return {
        "slots": {k: _mode(v) for k, v in slots.items()},
        # 절반 이상 나온 선수를 주전으로 본다 — 대타 1회 출전과 구분해야 한다.
        "regulars": {k for k, c in appear.items() if c * 2 >= n},
        "positions": {k: _mode(v) for k, v in pos.items()},
        "display": display,          # 정규화 키 → 원문 표기(표시용)
        "games": n,
    }


def _is_dh(position: str) -> bool:
    return any(w in (position or "") for w in _DH_WORDS)


def diff_lineup(today: list[tuple[str, str]], usual: dict) -> list[dict]:
    """오늘 라인업 vs 평소 → 변경점 목록(사실).

    각 항목 {"type", "detail", "who", "cell"}.
    ⚠️ 해석하지 않는다. detail은 무슨 일이 있었는지만 적는다.
    """
    if not today or not usual or not usual.get("slots"):
        return []
    out = []
    # 🔴 비교는 **정규화 이름**으로 한다. 표기 차이가 곧 거짓 결장이 된다.
    today_slot = {canon_name(name): i for i, (name, _) in enumerate(today, 1)}
    today_pos = {canon_name(name): p for name, p in today}
    show = dict(usual.get("display") or {})
    show.update({canon_name(n): n for n, _ in today})

    # ① 평소 주전이 오늘 없다
    for key in sorted(usual["regulars"] - set(today_slot)):
        name = show.get(key, key)
        out.append({"type": "regular_out", "who": name,
                    "detail": f"평소 {usual['slots'].get(key, '?')}번 {name}이(가) "
                              f"선발 라인업에서 빠짐"})
    # ② 타순 이동
    for key, slot in today_slot.items():
        name = show.get(key, key)
        was = usual["slots"].get(key)
        if was is None:
            continue
        if was <= TOP_ORDER < slot:
            out.append({"type": "order_demote", "who": name,
                        "detail": f"{name} {was}번 → {slot}번 (상위타순에서 하위로)"})
        elif slot <= TOP_ORDER < was:
            out.append({"type": "order_promote", "who": name,
                        "detail": f"{name} {was}번 → {slot}번 (하위타순에서 상위로)"})
    # ③ 신규 투입 — 평소 명단에 아예 없던 선수
    for key, slot in sorted(today_slot.items(), key=lambda kv: kv[1]):
        name = show.get(key, key)
        if key not in usual["slots"]:
            out.append({"type": "new_starter", "who": name,
                        "detail": f"{name} {slot}번 — 최근 {usual['games']}경기 "
                                  f"선발 라인업에 없던 선수"})
    # ④ 포지션 변경 / 지명타자 배치
    for key, p in today_pos.items():
        name = show.get(key, key)
        was = (usual.get("positions") or {}).get(key)
        if not p or not was or p == was:
            continue
        if _is_dh(p) and not _is_dh(was):
            out.append({"type": "dh_rest", "who": name,
                        "detail": f"{name} 평소 {was} → 오늘 {p} (수비 면제)"})
        else:
            out.append({"type": "position_change", "who": name,
                        "detail": f"{name} 평소 {was} → 오늘 {p}"})
    for c in out:
        c["cell"] = TYPE_TO_CELL.get(c["type"], "batting")
    return out


def bullpen_absences(today_roster: list[str] | None,
                     key_relievers: list[str] | None) -> list[dict]:
    """오늘 1군 엔트리에 없는 **핵심 불펜**.

    ⚠️ 누가 '핵심'인지는 이 층이 정하지 않는다 — 호출부가 등판 기록에서 산출해
       넘긴다(`kbo_usage.key_relievers`). 역할(마무리·셋업)은 추정이지만
       등판 횟수는 관측이다. 관측만으로 정의한다.
    ⚠️ 엔트리를 못 받았으면 **판단하지 않는다.** 빈 명단을 "전원 말소"로 읽으면
       매일 거짓 신호가 난다(`kbo_roster`에서 이미 겪은 유형이다).
    """
    if not today_roster or not key_relievers:
        return []
    have = {canon_name(x) for x in today_roster}     # 표기 차이 흡수
    return [{"type": "bullpen_out", "who": n, "cell": "bullpen",
             "detail": f"핵심 불펜 {n}이(가) 1군 엔트리에 없음"}
            for n in key_relievers if canon_name(n) not in have]


def merge_absences_from_diff(research: dict, team: str, changes: list[dict],
                             usual: dict | None = None) -> list[str]:
    """평소 대비 빠진 주전·핵심 불펜을 λ가 읽는 `absences` 문장으로 옮긴다.

    새 계수를 만들지 않는다. scoring._absence_factors가 이미 읽는 표지
    (`중심 타선` → absence_top_hitter, 그 외 주전 → absence_hitter,
     `핵심 불펜` → absence_reliever)만 쓴다.

    ⚠️ 말소 목록에 이미 있으면 넣지 않는다 — 같은 선수를 두 번 깎으면 안 된다.
    ⚠️ 평소 타순이 없으면 중심/주전을 구분하지 못하고 주전 결장으로 둔다.
    """
    slots = (usual or {}).get("slots") or {}
    lines = list(research.get("absences") or [])
    known = " ".join(canon_name(str(x)) for x in lines)
    added: list[str] = []
    for c in changes or []:
        who = (c.get("who") or "").strip()
        if not who:
            continue
        key = canon_name(who)
        if key and key in known:
            continue
        typ = c.get("type")
        if typ == "regular_out":
            slot = slots.get(key)
            if slot is not None and slot <= TOP_ORDER:
                line = (f"{team}의 {who} 중심 타선 결장 — "
                        f"평소 {slot}번, 오늘 라인업에서 빠짐")
            else:
                line = f"{team}의 {who} 주전 결장 — 오늘 라인업에서 빠짐"
        elif typ == "bullpen_out":
            line = f"{team}의 {who} 핵심 불펜 결장 — 1군 엔트리에 없음"
        else:
            continue
        lines.append(line)
        added.append(line)
        known += " " + key
    if added:
        research["absences"] = lines
    return added


def summarize(changes: list[dict], usual: dict | None) -> dict:
    """변경점 → 칸별 사실 목록 + 요약 문구.

    반환 {"by_cell": {cell: [detail...]}, "headline": str, "types": [...]}
    ⚠️ 변경이 없으면 **"평소 라인업"으로 기록한다** — 변화 없음도 정보다.
    ⚠️ 비교 기준이 없으면 "비교 불가"다. '변경 없음'과 구분해야 한다.
    """
    if not usual or not usual.get("slots"):
        return {"by_cell": {}, "types": [],
                "headline": f"평소 라인업 비교 불가 (이력 {(usual or {}).get('games', 0)}경기 "
                            f"· 최소 {MIN_HISTORY}경기 필요)"}
    src = f" · {usual['source_note']}" if usual.get("source_note") else ""
    if not changes:
        return {"by_cell": {}, "types": [],
                "headline": f"평소 라인업 그대로 "
                            f"(최근 {usual['games']}경기 대비 변경 없음{src})"}
    by_cell: dict[str, list[str]] = {}
    for c in changes:
        by_cell.setdefault(c["cell"], []).append(c["detail"])
    kinds = sorted({c["type"] for c in changes})
    return {"by_cell": by_cell, "types": kinds,
            "headline": f"평소 대비 변경 {len(changes)}건 "
                        f"(최근 {usual['games']}경기 기준{src})"}
