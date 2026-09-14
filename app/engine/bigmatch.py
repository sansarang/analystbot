"""[BIG-1] 빅매치 태그 — 예산을 어디에 더 쓸지 정하는 한 줄 (사용자 지시).

셋 중 하나면 빅매치다:
  ① 같은 리그 **순위 3계단 이내** 대결
  ② **더비 목록**(config/derbies.yaml)
  ③ **상위 6팀 간** 대결

🔴 순위표를 이 모듈이 읽지 않는다 — **인자로 받는다.** 그래야 호출부가 어느
   표(리그 순위·Elo·티어)를 쓸지 정하고, 여기서 소스가 고정되지 않는다.
🔴 순위를 모르면 `None` 이다. 0위로 읽지 않는다 — 그때는 더비만 본다.
"""
from __future__ import annotations

import functools
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

#: 순위 차가 이 이내면 빅매치(사용자 지시).
RANK_GAP = 3
#: 둘 다 이 안이면 빅매치(사용자 지시).
TOP_N = 6

CONFIG = Path("config") / "derbies.yaml"


@dataclass(frozen=True)
class Tag:
    big: bool
    reason: str


def _norm(name: str) -> str:
    """비교용. 🔴 `aliases_local` 생성과 같은 규칙 — 악센트·기호를 지운다."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s.lower()).split())


@functools.lru_cache(maxsize=1)
def _derbies() -> dict[str, list[frozenset]]:
    import yaml

    if not CONFIG.exists():
        logger.info("[bigmatch] 더비 표 없음: %s", CONFIG)
        return {}
    try:
        doc = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("[bigmatch] 더비 표 읽기 실패: %s", exc)
        return {}
    out: dict[str, list[frozenset]] = {}
    for lg, pairs in (doc.get("derbies") or {}).items():
        out[lg] = [frozenset((_norm(a), _norm(b)))
                   for a, b in (pairs or []) if a and b]
    return out


def is_derby(league: str, home: str, away: str) -> bool:
    return frozenset((_norm(home), _norm(away))) in set(_derbies().get(league) or [])


def is_big_match(*, league: str, home: str, away: str,
                 rank_home: int | None = None,
                 rank_away: int | None = None) -> Tag:
    """빅매치인가. 반환 `(big, reason)` — **왜인지가 항상 붙는다.**"""
    if is_derby(league, home, away):
        return Tag(True, "더비")
    if rank_home is None or rank_away is None:
        return Tag(False, "순위 모름 · 더비 아님")
    if abs(int(rank_home) - int(rank_away)) <= RANK_GAP:
        return Tag(True, f"순위 {rank_home}위 vs {rank_away}위 ({RANK_GAP}계단 이내)")
    if int(rank_home) <= TOP_N and int(rank_away) <= TOP_N:
        return Tag(True, f"상위 {TOP_N}팀 간 ({rank_home}위 vs {rank_away}위)")
    return Tag(False, f"{rank_home}위 vs {rank_away}위")
