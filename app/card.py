"""출력 — v4 단계 1 기준 **수집 나열까지만.**

🔴 **v4 §8 폐기로 판정 블록을 걷어냈다.** 종전 이 파일은 "판정: {승자} 승, 확신
   {낮/중/상}" · "등급: 간다/조건부/접는다" 를 찍었다. v4 는 그 셋을 전부
   폐기했고, §3 STEP 7 계약이 **카드에 "확신"·"동기 등급"·"승자" 단어 0건**을
   요구한다.

🔴 v4 §7 의 4블록 카드(변수 목록 → 시나리오 → 생존표 → 결론)는 **단계 8** 에서
   짓는다. 지금 그 형식을 흉내 내면 근거 없이 이름을 적는 것이 된다.

⚠️ 그래서 지금 출력은 **모은 재료와 못 잰 칸을 그대로 나열하는 것**이다.
   보기 좋게 만들지 않았다 — 이 단계에서 예쁜 카드는 거짓이다.
"""
from __future__ import annotations

from app.judge import Absence, Intent, Starter

#: 🔴 출력에 절대 들어가면 안 되는 어구. 계약이 이 목록을 쓴다(사본 금지).
#   배당(v4 §0) + v4 §3 STEP 7 이 금지한 판정 어휘.
BANNED = (
    # 배당 — v4 §0 "판정 입력에 배당 숫자는 없다"
    "배당", "디빅", "devig", "priced", "CLV", "기대 이득", "기대이득",
    "엣지", "edge", "오즈", "odds", "북메이커",
    # v4 §3 STEP 7 — 폐기된 판정 어휘
    "확신", "동기 등급", "승자", "간다", "조건부", "접는다",
)


def render_collected(*, home: str, away: str, venue: str | None, kst: str,
                     status: str, absences: list[Absence],
                     starters: dict[str, Starter], intents: list[Intent],
                     facts: list[str], unknowns: list[str],
                     score: str | None = None, idx: int = 1) -> str:
    """경기 하나 — 모은 재료와 **못 잰 칸**.

    🔴 `unknowns` 를 그대로 적는다. 조용히 빼면 실제보다 근거가 많아 보인다.
    """
    head = f"## {_n(idx)} {away} @ {home}"
    if venue or kst:
        head += f" ({' '.join(x for x in (venue, kst) if x)})"

    if status == "inprogress":
        return f"{head}\n진행 중{f'({score})' if score else ''}"
    if status == "final":
        return f"{head}\n종료{f'({score})' if score else ''} — 채점 대상"
    if status in ("postponed", "delayed"):
        return f"{head}\n{'순연' if status == 'postponed' else '지연'}"

    lines = [head]
    if absences:
        lines.append("결장: " + ", ".join(
            f"{a.player_name}({_basis_kr(a.basis)}·{a.line})" for a in absences))
    for side in ("home", "away"):
        st = starters.get(side)
        if not st or not st.known:
            continue
        era = st.recent_era
        piece = f"{side} 선발 {st.name} 최근 {len(st.recent)}등판"
        piece += f" ERA {era}" if era is not None else " 기록 미확인"
        if st.vs_opponent_usable:
            piece += (f", 상대전 {st.vs_opponent['games']}경기 "
                      f"{st.vs_opponent['era']}")
        lines.append(piece)
    for it in intents:
        if it.quote:
            lines.append(f'{it.speaker or "감독"}: "{it.quote}" ({it.type})')
    lines.extend(facts)
    if unknowns:
        lines.append(f"**못 잰 칸**: {', '.join(unknowns)}")
    return "\n".join(lines)


def render_slate(blocks: list[str], *, n_games: int) -> str:
    """슬레이트 나열.

    ⚠️ **결론 줄이 없다.** "낸다/소액/없음"은 v4 STEP 6 생존 계산의 산출이고
       단계 7 에서 짓는다. 지금 그 줄을 만들면 근거 없이 이름을 적는 것이다.
    """
    out = list(blocks)
    out.append(f"\n— 수집 {n_games}경기. "
               "시나리오·생존·결론은 아직 없다(v4 단계 6·7).")
    return "\n".join(out)


_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_BASIS_KR = {"injury": "부상", "national_team": "대표팀", "suspension": "징계",
             "deregistered": "말소", "rest": "휴식", "gone": "이적",
             "personal": "개인사"}


def _n(i: int) -> str:
    return _CIRCLED[i - 1] if 1 <= i <= len(_CIRCLED) else f"{i}."


def _basis_kr(b: str) -> str:
    return _BASIS_KR.get(b, b)


def has_banned(text: str) -> list[str]:
    """🔴 계약이 부른다 — 출력에 금지 어구가 들어갔나."""
    low = (text or "").lower()
    return [w for w in BANNED if w.lower() in low]
