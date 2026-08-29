"""[§9 게이트 ①-파이썬] 파이썬 수집기 경로의 물리 검사.

왜 Go 게이트만으로 부족한가 (2026-08-27 측정):
  Go의 `internal/gate`는 **크롤러가 긁은 필드**(선발 이름·라인업·경기상태)만 본다.
  그런데 λ와 카드에 실제로 들어가는 수치 — ERA·WHIP·OPS·평균이닝·순위 — 는
  파이썬 수집기(네이버 preview·KBO 기록실)가 넣으며 **아무 검사도 받지 않았다.**
  오늘 데이터 90개를 실측하니 범위 밖 값은 없었지만, 검사가 없으므로
  Yahoo에서 겪은 ERA 189.00 같은 값이 오면 **그대로 통과한다.**

⚠️ Go 게이트와 **필드 집합이 겹치지 않는다** — Go는 크롤러 필드, 여기는 수집기
   수치 필드다. 같은 규칙을 두 언어에 복제하는 것이 아니므로 드리프트가 없다.

⚠️ 빈 값·미등록 필드는 통과시킨다. 값이 **있는데** 불가능할 때만 버린다
   (새 가드는 반대 방향 위험을 함께 본다 — 규율).
"""

import logging

logger = logging.getLogger(__name__)

# 필드 이름(점 경로의 마지막 조각) → (하한, 상한).
#   근거: 야구 지표의 물리적·실무적 한계. 이 범위를 넘는 값은 "강한 신호"가
#   아니라 **파싱이 깨졌다는 신호**다.
LIMITS: dict[str, tuple[float, float]] = {
    # 투수
    "era_season": (0.0, 15.0),      # 실사고: Yahoo 齋藤 響介 189.00
    "era_recent": (0.0, 15.0),
    "era_vs_opponent": (0.0, 15.0), # 시즌 상대팀 ERA. last-5가 아님.
    "whip": (0.0, 4.0),
    "ip_avg_recent": (0.0, 15.0),
    "team_era": (0.0, 15.0),
    "team_whip": (0.0, 4.0),
    # 타선
    "ops": (0.0, 1.400),
    "obp_30d": (0.0, 0.700),
    "obp": (0.0, 0.700),
    "slg": (0.0, 1.000),
    "avg": (0.0, 0.600),
    "woba": (0.0, 0.600),
    "runs_per_game": (0.0, 15.0),
    "runs_allowed_per_game": (0.0, 15.0),
    # 소모·순위 — MLB 리그 순위는 1~15, KBO/NPB 1~12. 15를 버리면 중하위 팀이 빈칸.
    "relief_ip_l3": (0.0, 30.0),
    "relief_ip_last": (0.0, 12.0),
    "starter_ip_l3": (0.0, 30.0),
    "relief_batters_l3": (0, 120),
    "pitchers_used_last": (0, 15),
    "rank": (1, 15),
    "games_behind": (0.0, 60.0),
    "remaining": (0, 200),
    "park_factor": (0.85, 1.20),
}


def check(dotted: str, value) -> str | None:
    """범위를 벗어나면 사유, 정상이면 None. 미등록 필드·빈 값은 None."""
    leaf = dotted.split(".")[-1]
    limits = LIMITS.get(leaf)
    if limits is None or value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None                      # 문자열 지표는 여기서 다루지 않는다
    lo, hi = limits
    if lo <= value <= hi:
        return None
    return f"{value} — 물리 범위 {lo}~{hi} 밖 (파싱 오류 신호)"


def screen(research: dict, fields: list[str]) -> list[tuple[str, object, str]]:
    """방금 채운 필드들을 검사해 **범위 밖 값을 research에서 제거**한다.

    반환: (필드, 폐기된 값, 사유). 조용히 버리지 않는다 —
    무엇을 왜 버렸는지 남아야 게이트 과잉도 측정할 수 있다.
    """
    dropped = []
    for f in fields or []:
        if f.startswith("-"):
            continue
        parts = f.split(".")
        cur = research
        for p in parts[:-1]:
            cur = cur.get(p) if isinstance(cur, dict) else None
            if cur is None:
                break
        if not isinstance(cur, dict) or parts[-1] not in cur:
            continue
        value = cur[parts[-1]]
        reason = check(f, value)
        if reason:
            cur.pop(parts[-1], None)
            dropped.append((f, value, reason))
            logger.warning("[게이트①] %s=%r 폐기: %s", f, value, reason)
    return dropped
