"""변수의 원천 자료형 — v3 §4·§5·§6 이 **유지**된 부분만 남았다.

🔴 **v4 단계 1(폐기 코드 제거)에서 판정 로직을 전부 지웠다.** v4 §8 폐기 목록:

> 동기 4등급, lean, 확신 상/중/낮, 간다/조건부/접는다, 방아쇠 통과에 따른 등급
> 상향/하향 · 세 축(동기·폼·결장) 판정 규칙과 "둘 이상 한쪽이면" 규칙 ·
> 반증 추적의 "확신 갱신" 로직(5-d) · v3 §9 방아쇠 유형표 ·
> v3 §15 정답지의 "승자·확신·등급" 열 · min_win_prob 비계, p_claude 앙상블

🔴 **v4 는 승자를 고르지 않는다. 자리를 고른다**(§0). 그 자리는 STEP 5(시나리오)·
   STEP 6(생존)이고, 단계 6·7 에서 짓는다. **그 전에는 판정 코드가 없는 것이 맞다.**

여기 남은 것은 v4 §8 "유지"가 지목한 셋의 자료형이다:
  `Absence`  ← v3 §4 결장 원장 → **absence 변수**의 원천
  `Starter`  ← v3 §5 선발 카드 → **pitcher_state 변수**의 원천
  `Intent`   ← v3 §6 감독 의도 → **lineup_intent 변수**의 원천

⚠️ 이 셋은 **변수가 아니다.** v4 §1 의 변수 타입(`type`·`direction`·`weight`)은
   단계 2 에서 짓는다. 여기 있는 것은 그 변수를 만들 **재료**다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ══════════════════════════════════════════════════════════════════
# 라벨 — 🔴 원본은 여기 하나다 (사본 금지)
# ══════════════════════════════════════════════════════════════════

#: v3 §4 결장 basis 7종.
BASES = ("injury", "national_team", "suspension", "deregistered",
         "rest", "gone", "personal")
#: v3 §4 결장 라인. 🔴 결장은 **수가 아니라 위치**다.
LINES = ("midfield", "defense", "lineup_core", "starter", "bullpen")
#: v3 §6 감독 의도 유형 8종.
INTENT_TYPES = ("조정_등판", "육성_검증", "주전_휴식", "CS_대비", "총력전",
                "복귀_관리", "로테이션_땜질", "소집_전_마지막")

#: v4 §1 변수의 방향. 🔴 **방향이 없는 사실은 배경이지 변수가 아니다.**
#   (전체 enum 은 단계 2 에서 타입으로 세운다 — 여기는 자료형이 쓰는 값만.)
HOME, AWAY, DRAW = "home", "away", "draw"


# ══════════════════════════════════════════════════════════════════
# 변수의 원천 (v4 §8 유지)
# ══════════════════════════════════════════════════════════════════


@dataclass
class Absence:
    """v3 §4 결장 한 줄. 🔴 `line` 이 없으면 저장하지 않는다.

    결장의 무게는 수가 아니라 **어느 라인인가**다 — 09-27 강원-인천 판정 근거가
    그것이었다(강원 결장은 중원, 인천은 센터백).
    """

    side: str
    player_name: str
    basis: str
    line: str
    confidence: str = "soft"       # hard | likely | soft (v3 §4 용어)
    player_id: int | None = None
    replacement: str | None = None
    source_url: str | None = None

    def __post_init__(self):
        if self.basis not in BASES:
            raise ValueError(f"basis 7종 밖이다: {self.basis}")
        if self.line not in LINES:
            raise ValueError(f"line 이 없다: {self.line}")


@dataclass
class Starter:
    """v3 §5 선발 카드. 🔴 **시즌 누적은 판정 입력이 아니다** — 최근 창만."""

    side: str
    name: str | None = None
    status: str = "unknown"        # probable | confirmed | unknown
    recent: list[dict] = field(default_factory=list)
    vs_opponent: dict | None = None      # {"games": n, "era": x}
    flags: list[str] = field(default_factory=list)

    @property
    def known(self) -> bool:
        return bool(self.name) and self.status != "unknown"

    @property
    def recent_era(self) -> float | None:
        """최근 창 평균자책. 표본이 없으면 None — **지어내지 않는다**."""
        ip = sum(float(r.get("ip") or 0) for r in self.recent)
        er = sum(float(r.get("er") or 0) for r in self.recent)
        return round(er * 9 / ip, 2) if ip >= 3 else None

    @property
    def vs_opponent_usable(self) -> bool:
        """v3 §5 — 상대전은 **3경기 이상만** 판정 입력. 미만이면 표기만."""
        return bool(self.vs_opponent
                    and int(self.vs_opponent.get("games") or 0) >= 3)


@dataclass
class Intent:
    """v3 §6 감독 의도. 🔴 인용이 본문에 실재할 때만 hard."""

    side: str
    type: str
    quote: str | None = None
    speaker: str | None = None
    hardness: str = "soft"


# ══════════════════════════════════════════════════════════════════
# 이관 대기 — v4 §8 "이관" 목록
# ══════════════════════════════════════════════════════════════════

#: 🔴 **v4 §8 이관**: *"`hypothesis_table.yaml`(반증 조건) →
#   `opposite_search_rules.yaml`(STEP 3 반대 방향 검색어 규칙)"* ·
#   *"judge.py의 '반증 1:1' → STEP 3 세포 생성"*.
#
#   그 이관은 **단계 5**(STEP 1~3 변수 수집·전제 재검증·반대 검색)에서 한다.
#   여기서는 표만 남긴다 — 🔴 이것을 읽는 코드는 아직 없다. 단계 5 가 이 표를
#   `opposite_search_rules.yaml` 로 옮기고 세포가 읽게 한다.
#
# ⚠️ 종전 `build_counters(hypothesis)` 는 삭제했다 — `Hypothesis`·`lean` 이
#    폐기 대상이어서 그 함수만 남기면 없는 타입을 가리킨다.
OPPOSITE_SEED: dict[str, tuple[str, ...]] = {
    "standings": ("상대도 걸린 게 생겼나 (타 구장 결과)",
                  "우리 팀이 이미 확정·탈락했나"),
    "pitcher_state": ("우리 선발 최근 등판이 무너졌나",
                      "투구수 제한·이닝 제한이 있나",
                      "상대 선발이 최근 급상승했나"),
    "absence": ("상대 결장자가 복귀 가능한가",
                "우리 쪽에 새 결장이 생겼나"),
    "venue": ("구장이 변경됐나", "우천·지연인가",
              "원정팀의 이 구장 상대 전적이 좋은가"),
    "lineup_intent": ("그 의도가 오늘 라인업으로 확인되나",),
}
