"""[v1.4] 실행 맥락 — 노드가 바깥과 닿는 **유일한** 통로.

🔴 노드는 전역·모듈 캐시로 I/O 하지 않는다. 필요한 핸들은 전부 여기서 온다 —
   그래야 테스트가 그 핸들만 갈아끼워 전 경로를 잴 수 있다.
⚠️ 시각은 [NOW] 훅 규약대로 **KST 기준**으로 넘어온다(지시문 규율 10).
   DB 저장은 UTC ISO8601, 비교·표시는 KST.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Ctx:
    pool: object | None = None          # asyncpg 풀 (없으면 스냅샷·DB 조회 생략)
    redis: object | None = None         # elo 캐시·위성 추출
    now_kst: object | None = None       # datetime (KST). None 이면 노드가 지금을 읽는다
    settings: object | None = None

    #: ⑤ 수집 예산. 슬레이트 단위로 만들어 경기마다 차감한다.
    budget: dict = field(default_factory=lambda: {"searches": 0, "slate_cap": 0})

    #: 테스트·드라이런용 주입구. **운영에서는 비어 있다.**
    #  🔴 값을 넣으면 그 노드는 바깥을 부르지 않는다 — 픽스처가 이것으로 돈다.
    inject: dict = field(default_factory=dict)

    def take_search(self, n: int = 1) -> bool:
        """검색 예산 차감. 남지 않으면 False — 호출부가 `unknown` 으로 적는다."""
        if self.budget.get("slate_cap", 0) <= 0:
            return True                  # 상한 미설정이면 막지 않는다(관측만)
        if self.budget.get("searches", 0) + n > self.budget["slate_cap"]:
            return False
        self.budget["searches"] = self.budget.get("searches", 0) + n
        return True
