"""[v1.4] `analysis_state` — 노드 간 **유일한** 전달 객체 (지시문 §2).

🔴 **노드는 자기 키(`n0X_*`)만 쓴다.** 다른 노드 키를 고치면 배선 오류다
   (계약 테스트가 잡는다).
🔴 노드 간 전달용 별도 변수·전역·임시 파일을 만들지 않는다.
⚠️ DB 저장은 UTC ISO8601, 비교·표시는 KST (지시문 규율 10).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

#: 🔴 노드가 쓸 수 있는 칸. 이름을 바꾸면 계약 테스트가 깨진다 —
#   `run.py` 의 스냅샷 이름과 **한 글자도 달라선 안 된다**.
NODE_KEYS: tuple = (
    "n01_prior", "n02_market", "n03_gate", "n04_hyp", "n05_evidence",
    "n06_verdict", "n07_adjust", "n08_pcode", "n09_conf", "n10_rejudge",
    "n11_value", "n12_text", "n13_send",
)

#: 멈춤 사유. **멈춤은 실패가 아니다**(지시문 규율 9) — 이 경로에서는
#  카드를 만들지 않는 것이 정상이고, 만들어지면 버그다.
STOP_REASONS: tuple = (
    "n03_freeze", "n06_refuted", "n06_unknown", "n11_no_value",
    "n12_hallucination",
)


@dataclass
class State:
    run_id: str
    game_id: str
    sport: str                      # "baseball" | "soccer"
    league: str
    kickoff_utc: str                # ISO8601 UTC
    home: str
    away: str
    # 🔴 [SIDE-2 2026-09-23] **한 칸이 두 일을 하고 있었다.** 나눈다.
    #
    #  `hyp_side`  — **무엇을 조사할까.** ①사전값이 정한다(`n01_prior`).
    #                ③④⑤가 읽는다. 시장을 보고 정하면 앵커링이고, 그러면
    #                "내가 종가를 이겼다"가 성립하지 않는다(CLAUDE.md
    #                "시장에 끌려가지 않는다" · FORKS F-17).
    #  `pick_side` — **누구를 고르나.** ⑧최종 확률이 정한다(`n08_pcode`).
    #                ⑨⑪⑫⑬·`record`·`narrate` 가 읽는다.
    #
    #  종전에는 **둘 다 ①이 정했다.** 그런데 확률은 시장에서 나오므로
    #  ①과 시장이 갈리면 **고른 쪽의 승률이 50% 미만**이 됐다 —
    #  실측 30일 17/58 = **29.3%**. 근거·자료 → docs/FORKS.md F-22
    hyp_side: str | None = None     # "home" | "away" | None  ← ①이 정한다
    pick_side: str | None = None    # "home" | "away" | None  ← ⑧이 정한다

    n01_prior: dict | None = None
    n02_market: dict | None = None
    n03_gate: dict | None = None
    n04_hyp: list | None = None
    n05_evidence: list | None = None
    n06_verdict: dict | None = None
    n07_adjust: list | None = None
    n08_pcode: dict | None = None
    n09_conf: dict | None = None
    n10_rejudge: dict | None = None
    n11_value: dict | None = None
    n12_text: dict | None = None
    n13_send: dict | None = None

    stop_reason: str | None = None

    #: 🔴 진단 전용. 판정에 쓰지 않는다 — 어느 노드가 돌았는지만 센다.
    trace: list = field(default_factory=list)
    #: [STOP-1] 마지막으로 지난 노드. 🔴 `stop_reason` 에서 파싱하지 않는다.
    stopped_at: str | None = None

    @classmethod
    def new(cls, game: dict) -> State:
        """`games` 행 하나 → 초기 상태. **없는 값을 지어내지 않는다.**"""
        import uuid

        return cls(
            run_id=str(uuid.uuid4()),
            game_id=str(game.get("game_id") or game.get("id") or ""),
            sport=str(game.get("sport") or ""),
            league=str(game.get("league") or ""),
            kickoff_utc=_iso(game.get("kickoff_utc") or game.get("starts_at")),
            home=str(game.get("home") or ""),
            away=str(game.get("away") or ""),
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, default=str)

    @classmethod
    def from_json(cls, raw: str | dict) -> State:
        d = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

    def get_node(self, key: str) -> Any:
        return getattr(self, key, None)

    def stopped(self) -> bool:
        return self.stop_reason is not None


def _iso(v) -> str:
    """`datetime` · 문자열 → ISO8601 UTC 문자열. 모르면 빈 문자열."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    try:
        return v.isoformat()
    except Exception:
        return str(v)
