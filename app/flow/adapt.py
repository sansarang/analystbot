"""[SWAP-2] 흐름 산출 → 위성이 아는 모양. **번역만 한다.**

사용자 2026-09-22: "바꿔끼우기 진행해라" · 갈림길 (가) — **양 팀 다 찾는다**

🔴 **왜 어댑터인가.** 두 경로가 **서로 다른 어휘**를 쓴다. 그게 지금까지
   안 이어진 진짜 이유다(CLAUDE.md 가 "순서가 끊겨 있다"고 적은 자리):

```
구경로 gate.py     "동의" · "시장 과대" · "가치 의심" · "보드 고정"
흐름  labels.py    "동의" · "시장과대"  · "가치의심"  · "보드고정" + "사전값단독"
                             ↑ 공백 없음    ↑ 공백 없음
```
🔴 **띄어쓰기가 다르다.** 그대로 이으면 `gate.select` 이 `_G.OVER`("시장 과대")
   와 비교해 **전건 미일치**가 되고, 대상이 **조용히 0** 이 된다.

```
구경로 가설  {"need": [{"field": "out", "side": "home", …}]}   → 키 "home.out"
흐름  가설   [{"id": "H_break", "vars": [{"var": "lineup_out", …}]}]  ← side 없음
```

⚠️ **어휘를 한쪽으로 통일하지 않는다.** 통일은 더 큰 결정이고 지금 근거가
   없다(어느 사전값이 나은지 아직 안 쟀다). 여기서는 **번역만** 한다.
⚠️ 순수 함수다 — DB·HTTP·LLM 0건. 계약이 잠근다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: 흐름 라벨 → 구경로 라벨. 🔴 **양쪽 상수를 import 해서 만든다** —
#  문자열을 손으로 적으면 어느 쪽이 바뀔 때 조용히 어긋난다(사본 금지).
def _label_map() -> dict:
    from app.engine import gate as G
    from app.flow import labels as L

    return {
        L.OVER: G.OVER,        # "시장과대"  → "시장 과대"
        L.DOUBT: G.DOUBT,      # "가치의심"  → "가치 의심"
        L.AGREE: G.AGREE,      # "동의"      → "동의"
        L.BOARD: G.BOARD,      # "보드고정"  → "보드 고정"
        # 🔴 `사전값단독` 은 구경로에 **대응이 없다**(시장이 아직 없을 때).
        #    지어내지 않고 None 으로 둔다 — 그 경기는 종전대로 빅매치 판정으로
        #    간다(`select_search_targets` 가 라벨 없는 행을 그렇게 다룬다).
        L.PRIOR_ONLY: None,
    }


def gate_label(flow_gate) -> str | None:
    """흐름 `n03_gate` → 구경로 라벨. 모르면 **None**(지어내지 않는다)."""
    if not isinstance(flow_gate, dict):
        return None
    return _label_map().get(str(flow_gate.get("gate") or ""))


def gate_gap_pp(flow_gate):
    """괴리(%p). 흐름이 안 냈으면 None."""
    if not isinstance(flow_gate, dict):
        return None
    v = flow_gate.get("gap_pp")
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


#: 흐름 변수 → 구경로 `hypothesis.FIELDS` 항목.
#  🔴 **실측으로 맞춘 표다.** 흐름 변수의 원본은 `config/rules.yaml` 의
#     `flow.adjust_prior_pp` 이고(야구 6개·축구 5개), 구경로 필드의 원본은
#     `hypothesis.FIELDS` 다(8개). 두 목록은 **겹치지 않는다** — 그래서 표가
#     필요하다.
#  ⚠️ 대응이 없는 변수는 **빼지 않고 여기 없음**으로 둔다. 억지로 붙이면
#     위성이 엉뚱한 칸을 찾는다.
VAR_TO_FIELD = {
    # 야구
    "lineup_out": "out",            # 결장
    "starter_recent3": "last3",     # 선발 최근 3등판
    "bullpen_3d": "last3",          # 불펜 3일 — 같은 "최근" 칸을 본다
    # 축구
    "xi_confirmed": "xi_status",
    "rotation_risk": "midweek",
    "form_recent5": "last3",
    # park_factor · weather · travel · travel_backtoback · motivation 은
    # 구경로 위성이 찾는 칸이 아니다(기사에서 못 뽑는다) — 대응 없음.
}

_SIDES = ("home", "away")


def need_from_hyp(flow_hyp, *, sides=_SIDES) -> list:
    """흐름 `n04_hyp` → 구경로 `{"need": [...]}` 모양.

    🔴 **양 팀 다 찾는다**(사용자 결정 2026-09-22, 갈림길 (가)).
       흐름 변수에는 side 가 없다. "우리 픽을 무너뜨릴 근거"는 우리 쪽 악재일
       수도 상대 쪽 호재일 수도 있어서 **한쪽만 보면 놓친다.**
       ⚠️ 수집량이 2배가 되지만 수집은 기사 읽기이고, LLM 추출은 §3 상한이
          따로 막는다.

    ⚠️ 대응 없는 변수는 **조용히 버리지 않는다** — 로그로 센다.
    """
    if not flow_hyp:
        return []
    fields, unknown = [], []
    for h in (flow_hyp if isinstance(flow_hyp, list) else [flow_hyp]):
        if not isinstance(h, dict):
            continue
        for v in (h.get("vars") or []):
            name = str((v or {}).get("var") or "")
            f = VAR_TO_FIELD.get(name)
            if f is None:
                if name:
                    unknown.append(name)
                continue
            why = str(h.get("text") or "")[:80]
            for side in sides:
                row = {"field": f, "side": side, "why": why}
                if row not in fields:
                    fields.append(row)
    if unknown:
        logger.info("[flow:adapt] 대응 없는 변수 %s — 위성이 찾는 칸이 아니다",
                    sorted(set(unknown)))
    return fields


def to_row(flow_gate, flow_hyp) -> dict:
    """위성의 슬레이트 행에 얹을 칸들.

    반환 `{"gate_label", "gate_gap_pp", "hypothesis"}` — `satellite._DUE_SQL`
    이 `pick_ledger` 에서 읽던 것과 **같은 이름·같은 모양**이다. 그래야
    `select_search_targets`·`_need_of` 를 한 줄도 안 고쳐도 된다.
    """
    need = need_from_hyp(flow_hyp)
    return {
        "gate_label": gate_label(flow_gate),
        "gate_gap_pp": gate_gap_pp(flow_gate),
        # ⚠️ `_need_of` 는 `{"need": [...]}` 를 기대한다. 빈 목록과 None 은
        #    다르다 — 빈 목록은 "찾을 것 없음", None 은 "가설 없음"이다.
        "hypothesis": ({"need": need} if need else None),
    }


#: 경기별 **가장 최근** 흐름 산출. 🔴 `analysis_runs.game_id` 는 **TEXT** 다
#  (`db/schema.sql:939`) — 숫자로 비교하면 안 맞는다.
#  ⚠️ `run_id` 는 UUID 라 문자열 연산을 걸면 터진다
#     (실측: `operator does not exist: uuid ~~ unknown`).
_LATEST_SQL = """
    SELECT DISTINCT ON (a.game_id, a.node)
           a.game_id, a.node, a.snapshot_json
      FROM analysis_runs a
     WHERE a.node = ANY($2::text[])
       AND a.game_id = ANY($1::text[])
     ORDER BY a.game_id, a.node, a.id DESC
"""


async def latest_for(pool, game_ids) -> dict:
    """`{game_id(int): {"gate_label", "gate_gap_pp", "hypothesis"}}`.

    🔴 **읽기 전용이다.** 흐름을 여기서 돌리지 않는다 — 흐름은 자기 잡
       (`flow_shadow_15m`)이 돌리고, 위성은 그 결과를 **본다.**
    ⚠️ 못 읽으면 **빈 dict** 다. 그 경기는 종전대로 빅매치 판정으로 간다
       — 구경로 게이트로 되돌아가지 않는다(사용자 지시).
    """
    import json

    ids = [str(g) for g in (game_ids or []) if g is not None]
    if not ids or pool is None:
        return {}
    try:
        rows = await pool.fetch(_LATEST_SQL, ids, ["n03_gate", "n04_hyp"])
    except Exception as exc:
        logger.warning("[flow:adapt] 흐름 산출 조회 실패: %s", exc)
        return {}
    bag: dict = {}
    for r in rows:
        snap = r["snapshot_json"]
        if isinstance(snap, str):
            try:
                snap = json.loads(snap)
            except Exception:
                continue
        if not isinstance(snap, dict):
            continue
        bag.setdefault(str(r["game_id"]), {})[r["node"]] = snap.get(r["node"])
    out: dict = {}
    for gid, nodes in bag.items():
        try:
            key = int(gid)
        except (TypeError, ValueError):
            continue
        out[key] = to_row(nodes.get("n03_gate"), nodes.get("n04_hyp"))
    return out
