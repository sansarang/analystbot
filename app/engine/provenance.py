"""[§9 게이트 ③] 출처 대조 — 값마다 **소스명·수집 시각·라벨**을 붙인다.

게이트 ①②(Go, 물리·자기일관성)를 통과한 값이 여기로 온다. 여기서 묻는 것은
"이 값이 물리적으로 가능한가"가 아니라 **"이 값을 믿을 수 있는가"**다.

세 가지를 함께 저장한다 — 값 · 소스명 · 수집 시각(UTC).
시각이 없으면 모순을 풀 수 없다. 값만 저장하면 나중에 어느 쪽이 최신인지
알 방법이 사라진다.

⚠️ **라벨은 값 단위다.** 경기 단위도 소스 단위도 아니다 — 같은 네이버 응답이라도
   선발 이름은 공식 발표를 받아 확정이고, 부상 정보는 그 매체 단독이라 단일일 수
   있다. 소스 하나에 라벨 하나를 붙이면 그 구분이 사라진다.

⚠️ **모순에 다수결을 쓰지 않는다.** 오래된 소스 둘이 신선한 소스 하나를 이기게
   되고, 그것이 정확히 우리가 피하려는 실패다(선발이 경기 30분 전에 바뀌었는데
   낡은 기사 둘이 이겨서 옛 선발로 판정하는 상황).
   → 수집 시각을 비교해 신선한 쪽을 채택한다. 단, 시각 차가 작으면
     (`FRESHNESS_MARGIN` 이내) **어느 쪽도 믿지 않고 "모름"으로 버린다** —
     비슷한 시각의 충돌은 둘 중 하나가 틀렸다는 뜻이지 최신성 문제가 아니다.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.research.crosscheck_sources import SOURCE_RANK, norm_name

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- 라벨

CONFIRMED = "확정"      # 공식 발표 + 게이트 ①② 통과
CROSS = "교차"          # 독립 2소스 이상 일치
SINGLE = "단일"         # 1소스만
UNVERIFIED = "미확인"   # 커뮤니티·목격담 — 확인 전까지 사실이 아니다
CONFLICT = "모순"       # 소스 충돌 — 판정 불가

# 판정에 **쓸 수 있는** 라벨. 미확인·모순은 들어가지 못한다.
USABLE = frozenset({CONFIRMED, CROSS, SINGLE})
# 쓰되 카드에 출처를 표시해야 하는 라벨 — 읽는 사람이 근거의 두께를 알아야 한다.
NEEDS_NOTE = frozenset({SINGLE})

# 공식 발표로 보는 소스. 구단·리그가 직접 낸 것만이다.
#   portal(네이버·Yahoo)은 공식을 받아 싣지만 **그들의 편집이 들어간다** —
#   실제로 예상 라인업을 확정처럼 싣는 사고가 있었다. 공식으로 치지 않는다.
OFFICIAL_SOURCES = frozenset({"official_x", "official_record"})
COMMUNITY_SOURCES = frozenset({"community"})

# 모순 해소의 시각 차 하한. 이보다 가까우면 신선도로 가릴 수 없다고 본다.
FRESHNESS_MARGIN = timedelta(minutes=30)

_PROV_KEY = "_prov"


# ---------------------------------------------------------------- 관측·결과


@dataclass(frozen=True)
class Observation:
    """한 소스가 한 시점에 본 값 하나."""

    value: Any
    source: str
    at: datetime

    def __post_init__(self):
        if self.at.tzinfo is None:
            raise ValueError("수집 시각은 timezone-aware UTC여야 한다")


@dataclass
class Resolved:
    """값 하나에 대한 대조 결과."""

    value: Any | None
    label: str
    detail: str = ""
    sources: list[str] = field(default_factory=list)
    at: datetime | None = None

    @property
    def usable(self) -> bool:
        """판정 입력으로 쓸 수 있는가."""
        return self.label in USABLE and self.value is not None

    @property
    def note(self) -> str:
        """카드에 표시할 출처 문구. 표시가 불필요하면 빈 문자열."""
        if self.label in NEEDS_NOTE:
            return f"({self.label}·{'/'.join(self.sources)})"
        if self.label in (UNVERIFIED, CONFLICT):
            return f"({self.label} — 판정 미사용)"
        return ""

    def as_dict(self) -> dict:
        return {"value": self.value, "label": self.label, "usable": self.usable,
                "detail": self.detail, "sources": list(self.sources),
                "at": self.at.isoformat() if self.at else None}


def _norm(v: Any) -> str:
    """비교용 정규화. 이름은 공백·구두점 무시, 숫자는 소수 4자리까지."""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return f"{float(v):.4f}"
    return norm_name(v)


def resolve(observations: list[Observation]) -> Resolved:
    """같은 항목에 대한 관측들 → 채택값 + 라벨.

    커뮤니티 관측은 **검증 대상에서 분리**한다. 신선하다는 이유만으로 목격담이
    공식 발표를 이기면 안 되기 때문이다 — 신선도는 같은 급끼리 비교하는 기준이다.
    """
    obs = [o for o in observations
           if o.value is not None and str(o.value).strip() != ""]
    if not obs:
        return Resolved(None, UNVERIFIED, "관측 없음")

    verifiable = [o for o in obs if o.source not in COMMUNITY_SOURCES]
    if not verifiable:
        newest = max(obs, key=lambda o: o.at)
        return Resolved(newest.value, UNVERIFIED, "커뮤니티 단독 — 확인 필요",
                        sorted({o.source for o in obs}), newest.at)

    groups: dict[str, list[Observation]] = {}
    for o in verifiable:
        groups.setdefault(_norm(o.value), []).append(o)

    if len(groups) == 1:
        same = next(iter(groups.values()))
        newest = max(same, key=lambda o: o.at)
        srcs = sorted({o.source for o in same})
        if any(o.source in OFFICIAL_SOURCES for o in same):
            return Resolved(newest.value, CONFIRMED, "공식 발표", srcs, newest.at)
        if len(srcs) >= 2:
            return Resolved(newest.value, CROSS, f"{len(srcs)}개 소스 일치",
                            srcs, newest.at)
        return Resolved(newest.value, SINGLE, "단일 소스", srcs, newest.at)

    # ── 충돌 ── 다수결이 아니라 **신선도**로 가른다.
    ranked = sorted(
        ({"newest": max(g, key=lambda o: o.at), "obs": g} for g in groups.values()),
        key=lambda x: x["newest"].at, reverse=True)
    top, second = ranked[0], ranked[1]
    gap = top["newest"].at - second["newest"].at
    if gap <= FRESHNESS_MARGIN:
        return Resolved(
            None, CONFLICT,
            f"{len(groups)}개 값 충돌 · 시각 차 {int(gap.total_seconds() // 60)}분"
            f"({int(FRESHNESS_MARGIN.total_seconds() // 60)}분 이내) — 신선도로 가릴 수 없다",
            sorted({o.source for o in verifiable}), None)
    win = top["newest"]
    srcs = sorted({o.source for o in top["obs"]})
    label = CONFIRMED if any(o.source in OFFICIAL_SOURCES for o in top["obs"]) else SINGLE
    return Resolved(
        win.value, label,
        f"충돌 — 더 신선한 값 채택 (차이 {int(gap.total_seconds() // 60)}분, "
        f"{second['newest'].source}={second['newest'].value!r} 폐기)",
        srcs, win.at)


# ---------------------------------------------------------------- research 부착


def stamp(research: dict, fields: list[str], source: str,
          at: datetime | None = None) -> None:
    """병합된 필드들에 소스·시각을 **누적** 기록한다.

    ⚠️ 덮어쓰지 않고 쌓는다. 마지막 소스만 남기면 두 소스가 같은 값을 줬는지
       (교차) 다른 값을 줬는지(모순) 영원히 알 수 없다 — 게이트 ③이 통째로
       무력해진다.
    """
    fields = [f for f in (fields or []) if not f.startswith("-")]
    if not fields:
        return          # 채운 것이 없으면 기록도 만들지 않는다(빈 _prov 키 방지)
    at = at or datetime.now(UTC)
    book = research.setdefault(_PROV_KEY, {})
    for f in fields:
        if f.startswith("-"):          # 제거된 필드(미공개 지표 등)는 기록 대상 아님
            continue
        value = _dig(research, f)
        book.setdefault(f, []).append(
            {"source": source, "at": at.isoformat(), "value": value})


def _dig(research: dict, dotted: str):
    """'home_pitcher.era_season' 같은 점 경로에서 값을 꺼낸다."""
    cur: Any = research
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def observations_for(research: dict, dotted: str) -> list[Observation]:
    rows = (research.get(_PROV_KEY) or {}).get(dotted) or []
    out = []
    for r in rows:
        try:
            out.append(Observation(r.get("value"), r.get("source") or "unknown",
                                   datetime.fromisoformat(r["at"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def label_field(research: dict, dotted: str) -> Resolved:
    """한 필드의 라벨. 기록이 없으면 미확인(관측 없음)."""
    return resolve(observations_for(research, dotted))


def label_all(research: dict) -> dict[str, Resolved]:
    """기록된 모든 필드의 라벨. 분포 측정·카드 표시에 쓴다."""
    return {f: label_field(research, f)
            for f in (research.get(_PROV_KEY) or {})}


def blocked_fields(research: dict) -> list[str]:
    """판정에 **넣으면 안 되는** 필드 목록 (미확인·모순)."""
    return sorted(f for f, r in label_all(research).items() if not r.usable)


def strip_unusable(research: dict) -> list[str]:
    """미확인·모순 값을 research에서 **제거**한다. 반환: 제거된 필드.

    표시만 하고 남겨두면 다음 단계가 그것을 사실로 읽는다. 판정 입력에서
    실제로 빼야 규율이 지켜진다.
    """
    removed = []
    for dotted in blocked_fields(research):
        parts = dotted.split(".")
        cur: Any = research
        for p in parts[:-1]:
            cur = cur.get(p) if isinstance(cur, dict) else None
            if cur is None:
                break
        if isinstance(cur, dict) and parts[-1] in cur:
            cur.pop(parts[-1], None)
            removed.append(dotted)
    return removed


def distribution(research: dict) -> dict[str, int]:
    """라벨 분포. **단일이 압도적이면 교차검증이 실질적으로 작동하지 않는다는 신호다.**

    ⚠️ `교차` 라벨만 보면 대조가 되고 있는지 알 수 없다. 공식 소스가 끼면
       `확정`이 우선 붙기 때문이다(확정 > 교차). 실측(2026-08-27): 교차 라벨은
       0건인데 실제로는 20개 값을 두 소스가 관측하고 있었다.
       → `대조됨`(2개 이상 소스가 본 값)을 따로 센다. 이것이 교차검증이
         실제로 작동하는지 보는 지표다.
    """
    counts = {CONFIRMED: 0, CROSS: 0, SINGLE: 0, UNVERIFIED: 0, CONFLICT: 0}
    crosschecked = 0
    for f, r in label_all(research).items():
        counts[r.label] = counts.get(r.label, 0) + 1
        if len({o.source for o in observations_for(research, f)}) >= 2:
            crosschecked += 1
    counts["대조됨"] = crosschecked
    return counts
