"""🔴🔴 **순서 재편 계약** — 사용자 지시 2026-10-10(다섯째).

> ━━ 계약 ━━
> · 단계 순서: 단계 2(가설)는 단계 3(시뮬) 결과를 **입력으로 받지 않는다**
>   (가설이 결과를 보고 쓰이면 **실패**).
> · 가설마다 **예측 신호**가 있고, 신호 지표가 **허용 목록 안**.
> · **재실행 ≤ 1회**, 재실행 **사유 기록**.
> · 최종 평의 근거 id ⊂ **지지된 가설·변수**.
> · LLM 출력이 **확률을 바꾸지 않는다**.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "app" / "core"


def _tree(p: Path) -> ast.Module:
    return ast.parse(p.read_text(encoding="utf-8"))


def _fn(p: Path, name: str):
    got = [n for n in ast.walk(_tree(p))
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
           and n.name == name]
    assert got, f"🔴 `{p.name}` 에 `{name}` 이 없다"
    return got[0]


def _ref():
    from app.core.schema import MatchRef
    return MatchRef(id="x:1", sport="soccer", competition="K-League 1",
                    competition_short="K리그1", home="team:000318",
                    away="team:000320", home_name="Gangwon FC",
                    away_name="Bucheon FC 1995",
                    kickoff_utc=datetime.now(timezone.utc) + timedelta(hours=2))


# ══════════════════════════════════════════════════════════════════
# 🔴🔴 계약 ① — 단계 2 는 시뮬 결과를 **안 받는다**
# ══════════════════════════════════════════════════════════════════

# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_v6_가설_단계가_시뮬_결과를_안_받는다`

# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_v6_가설_입력에_확률이_없다`

# ⚠️ **걷은 시험** — 그 단계가 지시서 2026-10-12(셋째) §1 처분으로 지워졌다
#    (⑭ 가설 · ⑮ 무너뜨릴 조건 · ⑰ 가설 검증 · ⑱ 반증 딥서치 · ⑳ 시나리오·
#    재가중 · ㉒ 반증 판정). 🔴 보장이 어디로 갔는지는
#    `docs/fable/stages/2026-10-12_dropped_contracts.md` 가 든다.
#    걷은 시험: `test_v6_신호_지표는_허용_목록_안이다`

# ⚠️ **걷은 시험** — §1 처분(2026-10-12 셋째)으로 그 입구가 바뀌었다
#    (`our_board(drafts=)` → `fav=/dog=` · `s7_judge.run(hypo)` → 격자).
#    걷은 시험: `test_v6_시뮬_표가_검증이_읽는_네_칸을_든다`

# ⚠️ **걷은 시험** — §1 처분(2026-10-12 셋째)으로 그 입구가 바뀌었다
#    (`our_board(drafts=)` → `fav=/dog=` · `s7_judge.run(hypo)` → 격자).
#    걷은 시험: `test_v6_카드_순서가_지시서대로다`
