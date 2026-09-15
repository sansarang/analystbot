"""[U12 2026-09-15] 사례집 — **닮은 과거 경기**를 분석 프롬프트에 3건 넣는다.

🔴 유사도는 **네 축**이다(엔진 사양 5절):
     리그군 · gap 버킷 · confirmed 집합 · 휴식 버킷
   퍼지 문자열 유사도를 쓰지 않는다 — 그건 AC밀란 오매칭의 원인이었다.

⚠️ 값(24건)은 **사용자가 채운다.** 골격만 만들고 대기한다.
⚠️ 순수 함수다. DB·HTTP 를 부르지 않는다.
"""
from __future__ import annotations

import functools
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CASES_PATH = Path("config/fable_cases.yaml")

#: 프롬프트에 넣는 개수. 늘리면 토큰이 는다.
TOP_N = 3

# 🔴 [U13] 값은 `config/rules.yaml` 이 원본이다. 여기에 숫자를 **다시
#    적지 마라** — 두 곳에 적으면 사본이 되고, 사본은 원본이 바뀔 때
#    따라가지 않는다(실사고 2026-09-02 워치독 오탐 4건).
from app.engine import rules as _R

#: 축별 배점. 합이 1.0 이다.
WEIGHTS = dict(_R.get("cases.weights"))


def gap_bucket(gap_pp: float | None) -> str | None:
    """gap 을 구간으로. 숫자를 그대로 비교하면 닮은 것이 하나도 없다."""
    if gap_pp is None:
        return None
    a = abs(float(gap_pp))
    if a < 4:
        return "0-4"
    if a < 8:
        return "4-8"
    if a < 15:
        return "8-15"
    return "15+"


def rest_bucket(days: int | None) -> str | None:
    if days is None:
        return None
    d = int(days)
    return "짧음" if d <= 3 else ("보통" if d <= 6 else "충분")


@functools.lru_cache(maxsize=1)
def load() -> list:
    """사례집. 파일이 없거나 비면 **빈 목록**(없는 것을 만들지 않는다)."""
    if not CASES_PATH.exists():
        logger.info("[cases] 사례집 없음: %s", CASES_PATH)
        return []
    try:
        import yaml

        doc = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("[cases] 읽기 실패 %s: %s", CASES_PATH, exc)
        return []
    return list(doc.get("cases") or [])


def score(case: dict, *, league_group: str | None, gap_pp: float | None,
          confirmed: list | None, rest_days: int | None) -> float:
    """유사도 0~1. 🔴 **축별 일치**를 더한다. 문자열 거리를 쓰지 않는다."""
    c = case or {}
    s = 0.0
    if league_group and c.get("league_group") == league_group:
        s += WEIGHTS["league_group"]
    gb = gap_bucket(gap_pp)
    if gb and c.get("gap_bucket") == gb:
        s += WEIGHTS["gap_bucket"]
    want = set(confirmed or [])
    have = set(c.get("confirmed") or [])
    if want and have:
        s += WEIGHTS["confirmed"] * (len(want & have) / len(want | have))
    rb = rest_bucket(rest_days)
    if rb and c.get("rest_bucket") == rb:
        s += WEIGHTS["rest_bucket"]
    return round(s, 4)


def similar(*, league_group: str | None = None, gap_pp: float | None = None,
            confirmed: list | None = None, rest_days: int | None = None,
            n: int = TOP_N) -> list:
    """닮은 사례 상위 n. 사례집이 비면 **빈 목록**이다."""
    rows = load()
    if not rows:
        return []
    scored = [(score(c, league_group=league_group, gap_pp=gap_pp,
                     confirmed=confirmed, rest_days=rest_days), c)
              for c in rows]
    scored = [(s, c) for s, c in scored if s > 0]
    scored.sort(key=lambda sc: -sc[0])
    return [dict(c, _score=s) for s, c in scored[:n]]


# ═══════════════ [U13] outcome 자동 채움
#
# 🔴 사례집은 **끝난 경기**로만 배운다. 채점되지 않은 행을 넣으면 사례집이
#    "그때 그렇게 봤다"는 기록이 아니라 **바람**이 된다.
# ⚠️ 파일을 쓰지 않는다 — 채워진 사례 목록을 **돌려줄 뿐**이다. 값 변경은
#    사용자가 한다(`config/rules.yaml` 과 같은 규약).

#: 결과 라벨. 🔴 '무승부'는 적중도 실패도 아니다 — 축구는 셋이다.
WON, LOST, PUSH = "적중", "실패", "무효"


def fill_outcome(cases: list | None, ledger: list | None) -> list:
    """사례 + 채점된 원장 → `outcome`·`clv` 가 채워진 사례 목록.

    대조 키는 `game_id` 다. 🔴 **채점 안 된 행은 건너뛴다** — `hit` 가
    None 이면 아직 결과가 없다는 뜻이고, 그걸 실패로 세면 사례집이 거짓이 된다.
    """
    by_id = {}
    for r in (ledger or []):
        gid = r.get("game_id")
        if gid is not None and r.get("hit") is not None:
            by_id[gid] = r

    out = []
    for c in (cases or []):
        c = dict(c)
        row = by_id.get(c.get("game_id"))
        if row is None:
            out.append(c)          # 그대로 둔다. 지어내지 않는다.
            continue
        hit = row.get("hit")
        c["outcome"] = (PUSH if row.get("void") else
                        (WON if int(hit) == 1 else LOST))
        if row.get("clv") is not None:
            c["clv"] = row["clv"]
        out.append(c)
    return out
